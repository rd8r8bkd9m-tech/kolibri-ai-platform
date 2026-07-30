#!/usr/bin/env python3
"""Atomic, rollback-gated kolibriai.ru API cutover to the r9 canary.

This operator tool deliberately keeps the Vite frontend route unchanged.  It
only rewrites the four backend locations in the active Kolibri nginx site,
tests the rendered candidate in an isolated nginx configuration, snapshots the
exact previous file, and reloads nginx only after all preflight gates pass.

``plan`` is read-only.  ``apply`` and ``rollback`` require root plus an explicit
owner approval identifier.  A failed nginx reload or post-cutover functional
smoke automatically restores the byte-for-byte previous configuration.

No credential is accepted on the command line and no environment value is
printed.  Browser smoke tests use the anonymous HttpOnly session contract.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import fcntl
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable
import urllib.error
import urllib.parse
import urllib.request


BACKEND_LOCATIONS = ("/api/v1/", "/api/", "/v1/", "/ws/")
LEGACY_PORTS = (8001, 18013)
DEFAULT_TARGET = "http://127.0.0.1:18014"
DEFAULT_FRONTEND = "http://127.0.0.1:15193"
FAILED_STATUSES = {
    "error",
    "failed",
    "incomplete",
    "unavailable",
    "capability_unavailable",
}
SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")


class CutoverError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class RouteSnapshot:
    backend: dict[str, str]
    frontend: str


@dataclasses.dataclass(frozen=True)
class HttpResult:
    status: int
    headers: dict[str, str]
    body: bytes


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _location_blocks(text: str) -> dict[str, tuple[int, int]]:
    """Return character spans for top-level location blocks.

    The active site has no nested location blocks.  This parser still counts
    braces so a future multiline location remains safe to rewrite.
    """

    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line)

    blocks: dict[str, tuple[int, int]] = {}
    matcher = re.compile(r"^\s*location\s+(?:=\s+)?(?P<path>/\S*)\s*\{")
    index = 0
    while index < len(lines):
        match = matcher.match(lines[index])
        if not match:
            index += 1
            continue
        path = match.group("path")
        depth = lines[index].count("{") - lines[index].count("}")
        end = index
        while depth > 0:
            end += 1
            if end >= len(lines):
                raise CutoverError(f"unclosed nginx location block: {path}")
            depth += lines[end].count("{") - lines[end].count("}")
        if path in blocks:
            raise CutoverError(f"duplicate nginx location block: {path}")
        blocks[path] = (offsets[index], offsets[end] + len(lines[end]))
        index = end + 1
    return blocks


def _proxy_pass(block: str, *, location: str) -> str:
    matches = re.findall(r"(?m)^\s*proxy_pass\s+([^;\s]+)\s*;", block)
    if len(matches) != 1:
        raise CutoverError(
            f"location {location} must contain exactly one proxy_pass; found {len(matches)}"
        )
    return matches[0]


def inspect_routes(text: str) -> RouteSnapshot:
    blocks = _location_blocks(text)
    missing = [path for path in (*BACKEND_LOCATIONS, "/") if path not in blocks]
    if missing:
        raise CutoverError(f"required nginx locations are missing: {', '.join(missing)}")
    backend = {
        path: _proxy_pass(text[start:end], location=path)
        for path, (start, end) in blocks.items()
        if path in BACKEND_LOCATIONS
    }
    start, end = blocks["/"]
    frontend = _proxy_pass(text[start:end], location="/")
    return RouteSnapshot(backend=backend, frontend=frontend)


def render_candidate(
    text: str,
    *,
    target: str = DEFAULT_TARGET,
    expected_frontend: str = DEFAULT_FRONTEND,
) -> str:
    snapshot = inspect_routes(text)
    if snapshot.frontend != expected_frontend:
        raise CutoverError(
            f"frontend route drift: expected {expected_frontend}, observed {snapshot.frontend}"
        )
    blocks = _location_blocks(text)
    candidate = text
    for location in sorted(BACKEND_LOCATIONS, key=lambda item: blocks[item][0], reverse=True):
        start, end = blocks[location]
        block = candidate[start:end]
        updated, count = re.subn(
            r"(?m)^(\s*proxy_pass\s+)[^;\s]+(\s*;)",
            rf"\g<1>{target}\g<2>",
            block,
            count=1,
        )
        if count != 1:
            raise CutoverError(f"could not rewrite proxy_pass for {location}")
        candidate = candidate[:start] + updated + candidate[end:]

    rendered = inspect_routes(candidate)
    if rendered.frontend != expected_frontend:
        raise CutoverError("candidate changed the Vite frontend route")
    if any(upstream != target for upstream in rendered.backend.values()):
        raise CutoverError("candidate did not converge every backend route")
    legacy_pattern = re.compile(
        r"(?m)^\s*proxy_pass\s+https?://[^;\s]+:(?:"
        + "|".join(str(port) for port in LEGACY_PORTS)
        + r")(?:/)?\s*;"
    )
    if legacy_pattern.search(candidate):
        raise CutoverError("candidate still contains a legacy backend proxy_pass")
    return candidate


def run_checked(command: Iterable[str], *, timeout: float = 30) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        output = result.stdout.strip()[-2000:]
        raise CutoverError(f"command failed ({result.returncode}): {' '.join(command)}\n{output}")
    return result


def service_snapshot(service: str) -> dict[str, Any]:
    active = run_checked(("systemctl", "is-active", service)).stdout.strip()
    if active != "active":
        raise CutoverError(f"candidate service is not active: {service}={active}")
    raw_properties = run_checked(
        (
            "systemctl",
            "show",
            service,
            "--property=NRestarts,ActiveEnterTimestampMonotonic,ExecMainStatus",
        )
    ).stdout.splitlines()
    properties = {
        key: value
        for line in raw_properties
        if "=" in line
        for key, value in (line.split("=", 1),)
    }
    required = {"NRestarts", "ActiveEnterTimestampMonotonic", "ExecMainStatus"}
    if not required.issubset(properties):
        raise CutoverError(f"could not read stable service properties for {service}")
    return {
        "active": active,
        "nrestarts": int(properties["NRestarts"] or "0"),
        "active_enter_timestamp_monotonic": properties["ActiveEnterTimestampMonotonic"],
        "exec_main_status": int(properties["ExecMainStatus"] or "0"),
    }


def isolated_nginx_test(
    candidate: str,
    *,
    site_path: Path,
    nginx_main: Path,
    nginx_binary: str,
) -> None:
    """Parse the candidate without replacing the live site file."""

    main = nginx_main.read_text(encoding="utf-8")
    include_pattern = re.compile(
        r"(?m)^(?P<indent>\s*)include\s+/etc/nginx/sites-enabled/\*\s*;\s*$"
    )
    matches = list(include_pattern.finditer(main))
    if len(matches) != 1:
        raise CutoverError("nginx.conf must contain exactly one sites-enabled wildcard include")

    with tempfile.TemporaryDirectory(prefix="kolibri-nginx-cutover-") as directory:
        root = Path(directory)
        candidate_path = root / "kolibri.candidate.conf"
        candidate_path.write_text(candidate, encoding="utf-8")
        os.chmod(candidate_path, 0o600)

        includes: list[Path] = []
        for path in sorted(Path("/etc/nginx/sites-enabled").iterdir()):
            try:
                same = path.resolve() == site_path.resolve()
            except FileNotFoundError:
                same = path == site_path
            if not same:
                includes.append(path.resolve())
        includes.append(candidate_path)
        replacement = "\n".join(
            f"{matches[0].group('indent')}include {path};" for path in includes
        )
        test_main = include_pattern.sub(replacement, main, count=1)
        test_main_path = root / "nginx.conf"
        test_main_path.write_text(test_main, encoding="utf-8")
        run_checked((nginx_binary, "-t", "-c", str(test_main_path), "-p", "/"))


class HttpClient:
    def __init__(self, base_url: str, *, timeout: float = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.cookies = http.cookiejar.CookieJar()
        context = ssl.create_default_context()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies),
            urllib.request.HTTPSHandler(context=context),
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        timeout: float | None = None,
        accept: str = "application/json",
    ) -> HttpResult:
        url = urllib.parse.urljoin(f"{self.base_url}/", path.lstrip("/"))
        data = None
        headers = {"Accept": accept}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=timeout or self.timeout) as response:
                return HttpResult(
                    status=response.status,
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=response.read(),
                )
        except urllib.error.HTTPError as exc:
            return HttpResult(
                status=exc.code,
                headers={key.lower(): value for key, value in exc.headers.items()},
                body=exc.read(),
            )


def require_status(result: HttpResult, expected: int, label: str) -> None:
    if result.status != expected:
        raise CutoverError(f"{label}: expected HTTP {expected}, received {result.status}")


def json_body(result: HttpResult, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(result.body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CutoverError(f"{label}: response is not JSON") from exc
    if not isinstance(payload, dict):
        raise CutoverError(f"{label}: expected a JSON object")
    return payload


def sse_payloads(result: HttpResult, label: str) -> list[dict[str, Any]]:
    require_status(result, 200, label)
    content_type = result.headers.get("content-type", "")
    if not content_type.startswith("text/event-stream"):
        raise CutoverError(f"{label}: expected text/event-stream, received {content_type!r}")
    payloads: list[dict[str, Any]] = []
    for line in result.body.decode("utf-8", errors="strict").splitlines():
        if not line.startswith("data: "):
            continue
        raw = line[6:]
        if raw == "[DONE]":
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CutoverError(f"{label}: invalid JSON SSE event") from exc
        if isinstance(payload, dict):
            payloads.append(payload)
    if not payloads:
        raise CutoverError(f"{label}: no SSE payloads received")
    return payloads


def _terminal_event(payloads: list[dict[str, Any]], label: str) -> dict[str, Any]:
    terminals = [payload for payload in payloads if payload.get("done") is True]
    if not terminals:
        raise CutoverError(f"{label}: stream has no terminal event")
    terminal = terminals[-1]
    status = str(terminal.get("status") or "")
    if status in FAILED_STATUSES or terminal.get("error_code"):
        raise CutoverError(f"{label}: terminal status is {status or 'unknown'}")
    return terminal


def smoke_health(client: HttpClient) -> dict[str, Any]:
    health = client.request("GET", "/api/health")
    require_status(health, 200, "health")
    payload = json_body(health, "health")
    if payload.get("status") != "ok":
        raise CutoverError("health: status is not ok")
    return {"status": "ok", "version": payload.get("version")}


def smoke_frontend(client: HttpClient) -> dict[str, Any]:
    result = client.request("GET", "/", accept="text/html")
    require_status(result, 200, "frontend")
    content_type = result.headers.get("content-type", "")
    if "text/html" not in content_type or b"<html" not in result.body.lower():
        raise CutoverError("frontend: Vite HTML was not returned")
    return {"status": "ok", "bytes": len(result.body)}


def smoke_route_isolation(client: HttpClient) -> dict[str, Any]:
    results: dict[str, int] = {}
    for path in ("/api/v1/__kolibri_cutover_missing__", "/ws/__kolibri_cutover_missing__"):
        response = client.request("GET", path)
        if response.status != 404:
            raise CutoverError(f"route isolation: {path} must return HTTP 404")
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            raise CutoverError(f"route isolation: {path} fell through to non-JSON content")
        results[path] = response.status
    return {"status": "ok", "routes": results}


def smoke_session_history(client: HttpClient, release_id: str) -> dict[str, Any]:
    bootstrap = client.request("POST", "/api/v1/shell/bootstrap", payload={})
    require_status(bootstrap, 200, "session bootstrap")
    bootstrap_payload = json_body(bootstrap, "session bootstrap")
    if bootstrap_payload.get("session_type") not in {"anonymous", "authenticated"}:
        raise CutoverError("session bootstrap: invalid session_type")
    if not any(cookie.name == "kolibri_session" for cookie in client.cookies) and bootstrap_payload.get(
        "session_type"
    ) == "anonymous":
        raise CutoverError("session bootstrap: anonymous HttpOnly cookie was not stored")

    smoke_run_id = f"{release_id}:{time.time_ns()}"
    idempotency_suffix = sha256_bytes(smoke_run_id.encode("utf-8"))[:16]
    title = f"Cutover smoke {release_id} {idempotency_suffix}"
    create_path = "/api/v1/projects"
    create_url = urllib.parse.urljoin(f"{client.base_url}/", create_path.lstrip("/"))
    request = urllib.request.Request(
        create_url,
        data=json.dumps({"title": title}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Idempotency-Key": f"cutover-project-{idempotency_suffix}",
        },
        method="POST",
    )
    try:
        with client.opener.open(request, timeout=client.timeout) as response:
            created = HttpResult(
                status=response.status,
                headers={key.lower(): value for key, value in response.headers.items()},
                body=response.read(),
            )
    except urllib.error.HTTPError as exc:
        created = HttpResult(
            status=exc.code,
            headers={key.lower(): value for key, value in exc.headers.items()},
            body=exc.read(),
        )
    if created.status not in {200, 201}:
        raise CutoverError(f"project create: expected HTTP 200/201, received {created.status}")
    project = json_body(created, "project create")
    project_id = str(project.get("id") or "")
    if not project_id:
        raise CutoverError("project create: missing id")

    try:
        message = client.request(
            "POST",
            f"/api/v1/projects/{urllib.parse.quote(project_id)}/messages",
            payload={"role": "user", "content": "cutover history verification"},
        )
        require_status(message, 201, "project message append")
        listed = client.request(
            "GET", f"/api/v1/projects/{urllib.parse.quote(project_id)}/messages"
        )
        require_status(listed, 200, "project message list")
        items = json_body(listed, "project message list").get("items")
        if not isinstance(items, list) or len(items) != 1:
            raise CutoverError("project history: appended message was not durable")

        deleted = client.request("DELETE", f"/api/v1/projects/{urllib.parse.quote(project_id)}")
        require_status(deleted, 200, "project delete")
        missing = client.request("GET", f"/api/v1/projects/{urllib.parse.quote(project_id)}")
        require_status(missing, 404, "project soft delete visibility")
        restored = client.request(
            "POST", f"/api/v1/projects/{urllib.parse.quote(project_id)}/restore", payload={}
        )
        require_status(restored, 200, "project restore")
        reloaded = client.request("GET", f"/api/v1/projects/{urllib.parse.quote(project_id)}")
        require_status(reloaded, 200, "project reload after restore")
    finally:
        # A final soft delete keeps the production history list clean while
        # preserving an auditable smoke-test record.
        with contextlib.suppress(Exception):
            client.request("DELETE", f"/api/v1/projects/{urllib.parse.quote(project_id)}")

    return {
        "status": "ok",
        "session_type": bootstrap_payload.get("session_type"),
        "project_lifecycle": "create-message-delete-restore-reload-delete",
    }


def _chat_stream(client: HttpClient, prompt: str, *, timeout: float) -> list[dict[str, Any]]:
    result = client.request(
        "POST",
        "/api/v1/chat/stream",
        payload={"messages": [{"role": "user", "content": prompt}]},
        timeout=timeout,
    )
    return sse_payloads(result, "chat stream")


def smoke_text(client: HttpClient, timeout: float) -> dict[str, Any]:
    payloads = _chat_stream(client, "Ответь только числом: 56+67", timeout=timeout)
    terminal = _terminal_event(payloads, "text")
    output = "".join(str(payload.get("content") or "") for payload in payloads)
    if "123" not in output:
        raise CutoverError("text: expected deterministic answer 123")
    return {
        "status": "ok",
        "event_count": len(payloads),
        "terminal_status": terminal.get("status"),
    }


def smoke_web(client: HttpClient, timeout: float) -> dict[str, Any]:
    prompt = (
        "Какое сейчас точное время в Москве? Используй интернет, укажи дату проверки "
        "и дай прямую ссылку на источник."
    )
    payloads = _chat_stream(client, prompt, timeout=timeout)
    terminal = _terminal_event(payloads, "web")
    output = "".join(str(payload.get("content") or "") for payload in payloads)
    if not re.search(r"https?://", output):
        raise CutoverError("web: response contains no direct source URL")
    tool_completed = any(
        isinstance(payload.get("tool_event"), dict)
        and payload["tool_event"].get("status") == "completed"
        and "web_search" in str(payload["tool_event"].get("tool") or "")
        for payload in payloads
    )
    source_backed = str(terminal.get("status") or "") == "source_backed"
    if not (tool_completed or source_backed):
        raise CutoverError("web: no completed web-search evidence")
    return {
        "status": "ok",
        "event_count": len(payloads),
        "source_url_present": True,
        "web_search_completed": tool_completed,
    }


def smoke_image(client: HttpClient, timeout: float) -> dict[str, Any]:
    payloads = _chat_stream(
        client,
        "Сгенерируй изображение одного красного цветка на белом фоне",
        timeout=timeout,
    )
    terminal = _terminal_event(payloads, "image")
    actions = terminal.get("actions")
    image_actions = [
        action
        for action in actions or []
        if isinstance(action, dict) and action.get("type") == "present_image"
    ]
    if len(image_actions) != 1 or not isinstance(image_actions[0].get("data"), dict):
        raise CutoverError("image: terminal event contains no verified present_image action")
    artifact = image_actions[0]["data"]
    url = str(artifact.get("url") or "")
    expected_sha = str(artifact.get("sha256") or "")
    expected_size = int(artifact.get("size_bytes") or 0)
    expected_mime = str(artifact.get("mime_type") or "")
    if not url.startswith("/api/v1/artifacts/images/"):
        raise CutoverError("image: artifact URL is outside the verified image route")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise CutoverError("image: artifact SHA-256 is invalid")
    if expected_size < 1024 or not expected_mime.startswith("image/"):
        raise CutoverError("image: artifact metadata is not a real raster payload")
    content = client.request("GET", url, timeout=timeout)
    require_status(content, 200, "image artifact download")
    observed_mime = content.headers.get("content-type", "").split(";", 1)[0]
    if observed_mime != expected_mime:
        raise CutoverError("image: downloaded MIME does not match metadata")
    if len(content.body) != expected_size or sha256_bytes(content.body) != expected_sha:
        raise CutoverError("image: downloaded bytes do not match size/SHA-256 metadata")
    signatures = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"RIFF")
    if not content.body.startswith(signatures):
        raise CutoverError("image: downloaded bytes are not a supported raster signature")
    return {
        "status": "ok",
        "event_count": len(payloads),
        "artifact_id": artifact.get("id"),
        "bytes": len(content.body),
        "sha256": expected_sha,
    }


def full_smoke(
    base_url: str,
    *,
    frontend_base_url: str | None,
    release_id: str,
    text_timeout: float,
    web_timeout: float,
    image_timeout: float,
) -> dict[str, Any]:
    client = HttpClient(base_url)
    frontend_client = HttpClient(frontend_base_url or base_url)
    started = time.monotonic()
    result = {
        "frontend": smoke_frontend(frontend_client),
        "health": smoke_health(client),
        "route_isolation": smoke_route_isolation(client),
        "session_history": smoke_session_history(client, release_id),
        "text": smoke_text(client, text_timeout),
        "web": smoke_web(client, web_timeout),
        "image": smoke_image(client, image_timeout),
    }
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def atomic_write(path: Path, content: bytes, *, reference: os.stat_result) -> None:
    temporary = path.with_name(f".{path.name}.cutover-{os.getpid()}")
    try:
        with temporary.open("wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, reference.st_mode & 0o7777)
        os.chown(temporary, reference.st_uid, reference.st_gid)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def backup_config(
    site_path: Path,
    *,
    backup_root: Path,
    release_id: str,
    candidate_sha256: str,
) -> Path:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    original_sha = sha256_file(site_path)
    directory = backup_root / f"{timestamp}-{release_id}-{original_sha[:12]}"
    directory.mkdir(parents=True, mode=0o700)
    backup_path = directory / "kolibri.nginx.previous"
    shutil.copy2(site_path, backup_path)
    if sha256_file(backup_path) != original_sha:
        raise CutoverError("backup checksum does not match the active nginx config")
    manifest = {
        "schema_version": "2026-07-13",
        "release_id": release_id,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "site_path": str(site_path),
        "previous_sha256": original_sha,
        "candidate_sha256": candidate_sha256,
        "backup_file": backup_path.name,
        "frontend_upstream": DEFAULT_FRONTEND,
        "backend_upstream": DEFAULT_TARGET,
    }
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(manifest_path, 0o600)
    (directory / "SHA256SUMS").write_text(
        f"{original_sha}  {backup_path.name}\n{sha256_file(manifest_path)}  {manifest_path.name}\n",
        encoding="utf-8",
    )
    os.chmod(directory / "SHA256SUMS", 0o600)
    return directory


def restore_backup(
    backup_dir: Path,
    *,
    nginx_binary: str,
    reload_command: tuple[str, ...],
) -> dict[str, Any]:
    manifest_path = backup_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    site_path = Path(manifest["site_path"])
    backup_path = backup_dir / manifest["backup_file"]
    expected = str(manifest["previous_sha256"])
    if sha256_file(backup_path) != expected:
        raise CutoverError("rollback backup checksum mismatch")
    reference = site_path.stat()
    atomic_write(site_path, backup_path.read_bytes(), reference=reference)
    if sha256_file(site_path) != expected:
        raise CutoverError("rollback did not restore the expected nginx config")
    run_checked((nginx_binary, "-t"))
    run_checked(reload_command)
    return {"status": "rolled_back", "restored_sha256": expected, "backup_dir": str(backup_dir)}


def validate_id(value: str, label: str) -> None:
    if not SAFE_ID.fullmatch(value):
        raise CutoverError(f"{label} must match {SAFE_ID.pattern}")


def preflight(args: argparse.Namespace) -> dict[str, Any]:
    site_path = Path(args.site_path)
    if not site_path.is_file():
        raise CutoverError(f"active nginx site does not exist: {site_path}")
    source = site_path.read_text(encoding="utf-8")
    current = inspect_routes(source)
    candidate = render_candidate(
        source,
        target=args.target,
        expected_frontend=args.frontend,
    )
    current_sha = sha256_bytes(source.encode("utf-8"))
    candidate_sha = sha256_bytes(candidate.encode("utf-8"))
    service_before = service_snapshot(args.service)
    if service_before["nrestarts"] != 0 or service_before["exec_main_status"] != 0:
        raise CutoverError(
            f"candidate service is unstable: NRestarts={service_before['nrestarts']} "
            f"ExecMainStatus={service_before['exec_main_status']}"
        )
    direct = HttpClient(args.direct_base_url, timeout=10)
    direct_health = smoke_health(direct)
    run_checked((args.nginx_binary, "-t"))
    isolated_nginx_test(
        candidate,
        site_path=site_path,
        nginx_main=Path(args.nginx_main),
        nginx_binary=args.nginx_binary,
    )
    service_after = service_snapshot(args.service)
    if service_after != service_before:
        raise CutoverError("candidate service changed during preflight")
    return {
        "status": "ready" if current_sha != candidate_sha else "already_applied",
        "site_path": str(site_path),
        "current_sha256": current_sha,
        "candidate_sha256": candidate_sha,
        "current_routes": dataclasses.asdict(current),
        "candidate_routes": dataclasses.asdict(inspect_routes(candidate)),
        "candidate_service": service_after,
        "direct_health": direct_health,
        "nginx_current_test": "passed",
        "nginx_candidate_test": "passed",
    }


def apply_cutover(args: argparse.Namespace) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise CutoverError("apply requires root")
    validate_id(args.release_id, "release-id")
    validate_id(args.owner_approval, "owner-approval")
    if not args.expected_current_sha256 or not re.fullmatch(
        r"[0-9a-f]{64}", args.expected_current_sha256
    ):
        raise CutoverError("apply requires --expected-current-sha256 from the approved plan")

    lock_path = Path(args.lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        plan = preflight(args)
        if plan["current_sha256"] != args.expected_current_sha256:
            raise CutoverError(
                "active nginx config changed after approval; render a new plan before apply"
            )
        if plan["status"] == "already_applied":
            raise CutoverError("candidate routes are already active; refusing a duplicate apply")

        site_path = Path(args.site_path)
        source = site_path.read_text(encoding="utf-8")
        candidate = render_candidate(source, target=args.target, expected_frontend=args.frontend)
        candidate_bytes = candidate.encode("utf-8")
        candidate_sha = sha256_bytes(candidate_bytes)
        backup_dir = backup_config(
            site_path,
            backup_root=Path(args.backup_root),
            release_id=args.release_id,
            candidate_sha256=candidate_sha,
        )
        previous_stat = site_path.stat()
        switched = False
        try:
            atomic_write(site_path, candidate_bytes, reference=previous_stat)
            switched = True
            if sha256_file(site_path) != candidate_sha:
                raise CutoverError("active nginx config does not match the approved candidate")
            run_checked((args.nginx_binary, "-t"))
            run_checked(tuple(args.reload_command))
            smoke = full_smoke(
                args.public_base_url,
                frontend_base_url=args.frontend_base_url,
                release_id=args.release_id,
                text_timeout=args.text_timeout,
                web_timeout=args.web_timeout,
                image_timeout=args.image_timeout,
            )
            after = service_snapshot(args.service)
            if after != plan["candidate_service"]:
                raise CutoverError("candidate service restarted or changed during cutover")
            active = inspect_routes(site_path.read_text(encoding="utf-8"))
            if active.frontend != args.frontend or any(
                upstream != args.target for upstream in active.backend.values()
            ):
                raise CutoverError("post-cutover nginx routes do not match the approved plan")
        except Exception as exc:
            rollback: dict[str, Any] | None = None
            if switched:
                rollback = restore_backup(
                    backup_dir,
                    nginx_binary=args.nginx_binary,
                    reload_command=tuple(args.reload_command),
                )
            raise CutoverError(
                f"cutover failed and was rolled back: {exc}; rollback={rollback}"
            ) from exc

        result = {
            "status": "applied",
            "release_id": args.release_id,
            "owner_approval": args.owner_approval,
            "previous_sha256": plan["current_sha256"],
            "active_sha256": candidate_sha,
            "backup_dir": str(backup_dir),
            "frontend_upstream": args.frontend,
            "backend_upstream": args.target,
            "smoke": smoke,
        }
        result_path = backup_dir / "result.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(result_path, 0o600)
        return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "check", "apply", "rollback"))
    parser.add_argument("--site-path", default="/etc/nginx/sites-enabled/kolibri")
    parser.add_argument("--nginx-main", default="/etc/nginx/nginx.conf")
    parser.add_argument("--nginx-binary", default="nginx")
    parser.add_argument("--service", default="kolibri-backend-r9.service")
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--frontend", default=DEFAULT_FRONTEND)
    parser.add_argument("--direct-base-url", default=DEFAULT_TARGET)
    parser.add_argument("--public-base-url", default="https://kolibriai.ru")
    parser.add_argument(
        "--frontend-base-url",
        default="",
        help="optional separate Vite origin for direct pre-cutover checks",
    )
    parser.add_argument("--release-id", default="")
    parser.add_argument("--owner-approval", default="")
    parser.add_argument("--expected-current-sha256", default="")
    parser.add_argument("--backup-root", default="/var/lib/kolibri/release-backups/api-cutover")
    parser.add_argument("--backup-dir", default="")
    parser.add_argument("--lock-path", default="/run/lock/kolibri-domain-api-cutover.lock")
    parser.add_argument(
        "--reload-command",
        nargs="+",
        default=("systemctl", "reload", "nginx"),
    )
    parser.add_argument("--text-timeout", type=float, default=45)
    parser.add_argument("--web-timeout", type=float, default=180)
    parser.add_argument("--image-timeout", type=float, default=600)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "plan":
            result = preflight(args)
        elif args.command == "check":
            if not args.release_id:
                raise CutoverError("check requires --release-id")
            validate_id(args.release_id, "release-id")
            result = {
                "status": "passed",
                "base_url": args.public_base_url,
                "smoke": full_smoke(
                    args.public_base_url,
                    frontend_base_url=args.frontend_base_url,
                    release_id=args.release_id,
                    text_timeout=args.text_timeout,
                    web_timeout=args.web_timeout,
                    image_timeout=args.image_timeout,
                ),
            }
        elif args.command == "apply":
            result = apply_cutover(args)
        else:
            if os.geteuid() != 0:
                raise CutoverError("rollback requires root")
            if not args.owner_approval:
                raise CutoverError("rollback requires --owner-approval")
            validate_id(args.owner_approval, "owner-approval")
            if not args.backup_dir:
                raise CutoverError("rollback requires --backup-dir")
            result = restore_backup(
                Path(args.backup_dir),
                nginx_binary=args.nginx_binary,
                reload_command=tuple(args.reload_command),
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (CutoverError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(
            json.dumps(
                {"status": "failed", "error": type(exc).__name__, "reason": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
