from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest


SCRIPT = Path(__file__).parents[1] / "kolibri_domain_api_cutover.py"
SPEC = importlib.util.spec_from_file_location("kolibri_domain_api_cutover", SCRIPT)
assert SPEC and SPEC.loader
cutover = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cutover
SPEC.loader.exec_module(cutover)


LIVE_SITE = """server {
    server_name kolibriai.ru www.kolibriai.ru;

    location /api/v1/ {
        proxy_pass http://127.0.0.1:18013;
        include /etc/nginx/proxy_params;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        include /etc/nginx/proxy_params;
    }

    location /v1/ {
        proxy_pass http://127.0.0.1:8001;
        include /etc/nginx/proxy_params;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
    }

    location / {
        proxy_pass http://127.0.0.1:15193;
        proxy_http_version 1.1;
    }
}
"""


def test_render_candidate_moves_every_backend_route_and_preserves_vite():
    candidate = cutover.render_candidate(LIVE_SITE)
    routes = cutover.inspect_routes(candidate)

    assert routes.backend == {
        "/api/v1/": "http://127.0.0.1:18014",
        "/api/": "http://127.0.0.1:18014",
        "/v1/": "http://127.0.0.1:18014",
        "/ws/": "http://127.0.0.1:18014",
    }
    assert routes.frontend == "http://127.0.0.1:15193"
    assert ":8001" not in candidate
    assert ":18013" not in candidate


def test_render_candidate_rejects_frontend_drift():
    changed = LIVE_SITE.replace("127.0.0.1:15193", "127.0.0.1:9999")
    with pytest.raises(cutover.CutoverError, match="frontend route drift"):
        cutover.render_candidate(changed)


def test_render_candidate_rejects_missing_or_duplicate_backend_locations():
    missing = LIVE_SITE.replace(
        "    location /v1/ {\n        proxy_pass http://127.0.0.1:8001;\n"
        "        include /etc/nginx/proxy_params;\n    }\n\n",
        "",
    )
    with pytest.raises(cutover.CutoverError, match="required nginx locations are missing"):
        cutover.render_candidate(missing)

    duplicate = LIVE_SITE.replace(
        "    location / {",
        "    location /api/ {\n        proxy_pass http://127.0.0.1:8001;\n    }\n\n"
        "    location / {",
    )
    with pytest.raises(cutover.CutoverError, match="duplicate nginx location block"):
        cutover.render_candidate(duplicate)


def test_atomic_write_keeps_mode_owner_and_exact_bytes(tmp_path: Path):
    path = tmp_path / "kolibri"
    path.write_bytes(b"old\n")
    path.chmod(0o640)
    before = path.stat()

    cutover.atomic_write(path, b"new\n", reference=before)

    after = path.stat()
    assert path.read_bytes() == b"new\n"
    assert after.st_mode & 0o777 == 0o640
    assert after.st_uid == before.st_uid
    assert after.st_gid == before.st_gid
    assert list(tmp_path.glob(".kolibri.cutover-*")) == []


def test_backup_and_rollback_are_checksum_bound(monkeypatch, tmp_path: Path):
    site = tmp_path / "kolibri"
    original = LIVE_SITE.encode()
    site.write_bytes(original)
    site.chmod(0o640)
    backup_root = tmp_path / "backups"

    backup_dir = cutover.backup_config(
        site,
        backup_root=backup_root,
        release_id="r9-test",
        candidate_sha256=cutover.sha256_bytes(b"candidate"),
    )
    site.write_bytes(b"changed\n")
    commands: list[tuple[str, ...]] = []

    def fake_run(command, *, timeout=30):
        commands.append(tuple(command))
        return type("Result", (), {"stdout": "", "returncode": 0})()

    monkeypatch.setattr(cutover, "run_checked", fake_run)
    result = cutover.restore_backup(
        backup_dir,
        nginx_binary="nginx",
        reload_command=("systemctl", "reload", "nginx"),
    )

    assert result["status"] == "rolled_back"
    assert site.read_bytes() == original
    assert cutover.sha256_file(site) == json.loads(
        (backup_dir / "manifest.json").read_text()
    )["previous_sha256"]
    assert commands == [("nginx", "-t"), ("systemctl", "reload", "nginx")]


def test_rollback_refuses_tampered_backup(monkeypatch, tmp_path: Path):
    site = tmp_path / "kolibri"
    site.write_text(LIVE_SITE)
    backup_dir = cutover.backup_config(
        site,
        backup_root=tmp_path / "backups",
        release_id="r9-test",
        candidate_sha256="0" * 64,
    )
    (backup_dir / "kolibri.nginx.previous").write_text("tampered")
    monkeypatch.setattr(cutover, "run_checked", lambda *_args, **_kwargs: None)

    with pytest.raises(cutover.CutoverError, match="checksum mismatch"):
        cutover.restore_backup(
            backup_dir,
            nginx_binary="nginx",
            reload_command=("systemctl", "reload", "nginx"),
        )


def test_sse_parser_requires_real_terminal_and_rejects_error():
    response = cutover.HttpResult(
        status=200,
        headers={"content-type": "text/event-stream; charset=utf-8"},
        body=(
            b'data: {"content":"123","done":false}\n\n'
            b'data: {"content":"","done":true,"status":"idle"}\n\n'
        ),
    )
    payloads = cutover.sse_payloads(response, "text")
    assert cutover._terminal_event(payloads, "text")["status"] == "idle"

    failed = [{"content": "", "done": True, "status": "failed"}]
    with pytest.raises(cutover.CutoverError, match="terminal status"):
        cutover._terminal_event(failed, "text")


def test_route_isolation_rejects_spa_html_fallback():
    class Client:
        def request(self, _method, path):
            if path.startswith("/api/"):
                return cutover.HttpResult(404, {"content-type": "application/json"}, b"{}")
            return cutover.HttpResult(404, {"content-type": "text/html"}, b"<html></html>")

    with pytest.raises(cutover.CutoverError, match="fell through to non-JSON"):
        cutover.smoke_route_isolation(Client())


def test_apply_requires_approved_current_checksum_before_any_write(monkeypatch):
    args = cutover.build_parser().parse_args(
        [
            "apply",
            "--release-id",
            "r9-test",
            "--owner-approval",
            "owner-approved",
        ]
    )
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with pytest.raises(cutover.CutoverError, match="expected-current-sha256"):
        cutover.apply_cutover(args)
