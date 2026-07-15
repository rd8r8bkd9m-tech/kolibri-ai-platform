#!/usr/bin/env python3
"""Root-only, signed and rollback-gated P7 paired release executor.

This program is intentionally separate from the candidate builder.  It accepts
only an already generated P7 plan and all signed inputs needed to recompute it.
Before the first live mutation it snapshots those inputs, calls
``kolibri_p7_release.paired_switch_plan`` again, requires byte-for-byte equality
with the supplied canonical plan, and verifies the current nginx SHA-256.

The live sequence is deliberately small: drain the single previous SQLite
writer, take an online SQLite backup, migrate the copy to revision 009, start
the immutable side-by-side pair on 18018/15194, validate nginx, replace one
site file atomically, reload once, and run public routing/identity gates.  Any
failure restores the exact prior site bytes and previous backend service.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import fcntl
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
import os
import platform
from pathlib import Path, PurePosixPath
import grp
import pwd
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
import urllib.error
import urllib.parse
import urllib.request


EXECUTOR_SCHEMA_VERSION = "kolibri.p7.executor-result.v1"
EXPECTED_PLAN_SCHEMA = "kolibri.p7.paired-switch-plan.v3"
EXPECTED_BACKEND_PORT = 18018
EXPECTED_FRONTEND_PORT = 15194
EXPECTED_SCHEMA_HEAD = "010_durable_responses"
BACKEND_ROUTES = ("/api/v1/", "/api/", "/v1/", "/ws/")
FRONTEND_ROUTE = "/"
CANARY_PREFIX = "/__canary"
ACTIVATION_MODES = frozenset({"production", "canary"})
BACKEND_SERVICE = "kolibri-backend-p7.service"
FRONTEND_SERVICE = "kolibri-frontend-p7.service"
REQUIREMENTS_LOCK = "kolibri-backend/requirements.lock"
RELEASE_FILES = (
    "release-manifest.json",
    "source.bundle",
    "backend.tar",
    "frontend.tar",
)
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
SAFE_SERVICE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@:-]{0,159}\.service$")
SAFE_PREVIOUS_BACKEND_SERVICE = re.compile(r"^kolibri-backend[A-Za-z0-9_.@:-]{0,143}\.service$")
SAFE_ACCOUNT = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_INPUT_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_FILES = 30_000
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
HASHED_FRONTEND_ASSET = re.compile(r"(?:^|[-.])[A-Za-z0-9_-]{8,}\.(?:js|css)$", re.IGNORECASE)
JAVASCRIPT_MIME_TYPES = frozenset(
    {
        "application/ecmascript",
        "application/javascript",
        "text/ecmascript",
        "text/javascript",
    }
)


class P7ExecutorError(RuntimeError):
    """A stable, non-secret release failure code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _apple_capability_worker_enabled() -> bool:
    return os.getenv("KOLIBRI_APPLE_CAPABILITY_WORKER", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def require_p7_runtime_host() -> None:
    if platform.system() == "Darwin" and not _apple_capability_worker_enabled():
        raise P7ExecutorError("p7_darwin_requires_apple_capability_worker")


@dataclasses.dataclass(frozen=True)
class SignedInputs:
    plan: Path
    release_dir: Path
    release_signature: Path
    rollback_release_dir: Path
    rollback_signature: Path
    gate_evidence: Path
    gate_evidence_signature: Path
    rollback_health_evidence: Path
    rollback_health_signature: Path
    owner_approval: Path
    owner_approval_signature: Path


@dataclasses.dataclass(frozen=True)
class ExecutorConfig:
    inputs: SignedInputs
    active_site: Path
    nginx_main: Path
    sites_enabled_dir: Path
    source_database: Path
    previous_backend_service: str
    runtime_secret_file: Path
    release_root: Path
    data_root: Path
    backup_root: Path
    state_root: Path
    systemd_dir: Path
    lock_path: Path
    public_base_url: str = "https://kolibriai.ru"
    frontend_base_path: str = "/"
    python_binary: str = "/usr/bin/python3"
    nginx_binary: str = "/usr/sbin/nginx"
    systemctl_binary: str = "/usr/bin/systemctl"
    runtime_user: str = "ladik"
    runtime_group: str = "ladik"


@dataclasses.dataclass(frozen=True)
class SnapshotInputs:
    plan: Path
    release_dir: Path
    release_signature: Path
    rollback_release_dir: Path
    rollback_signature: Path
    gate_evidence: Path
    gate_evidence_signature: Path
    rollback_health_evidence: Path
    rollback_health_signature: Path
    owner_approval: Path
    owner_approval_signature: Path
    digests: Mapping[str, str]


@dataclasses.dataclass(frozen=True)
class VerifiedPlan:
    plan: dict[str, Any]
    manifest: dict[str, Any]
    rollback_manifest: dict[str, Any]
    snapshot: SnapshotInputs


@dataclasses.dataclass(frozen=True)
class RuntimePaths:
    release_dir: Path
    backend_dir: Path
    frontend_dir: Path
    data_dir: Path
    database: Path
    venv_dir: Path
    runtime_uid: int | None = None
    runtime_gid: int | None = None
    runtime_home: Path | None = None


@dataclasses.dataclass
class UnitBackup:
    path: Path
    existed: bool
    content: bytes | None
    metadata: os.stat_result | None


@dataclasses.dataclass(frozen=True)
class HttpResult:
    status: int
    headers: Mapping[str, str]
    body: bytes


class CommandRunner:
    """Subprocess boundary whose failures never echo secret-bearing output."""

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float = 120,
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                tuple(command),
                cwd=cwd,
                env=dict(env) if env is not None else None,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise P7ExecutorError("p7_executor_command_unavailable") from exc
        if result.returncode != 0:
            raise P7ExecutorError("p7_executor_command_failed")
        return result


class HttpClient:
    def __init__(self, base_url: str, timeout: float = 30) -> None:
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
            raise P7ExecutorError("p7_public_base_url_invalid")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> HttpResult:
        url = urllib.parse.urljoin(f"{self.base_url}/", path.lstrip("/"))
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return HttpResult(
                    response.status,
                    {key.lower(): value for key, value in response.headers.items()},
                    response.read(),
                )
        except urllib.error.HTTPError as exc:
            return HttpResult(
                exc.code,
                {key.lower(): value for key, value in exc.headers.items()},
                exc.read(),
            )
        except (OSError, urllib.error.URLError) as exc:
            raise P7ExecutorError("p7_http_probe_unavailable") from exc


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _require_absolute(path: Path, code: str) -> Path:
    if not path.is_absolute():
        raise P7ExecutorError(code)
    return path


def _regular_metadata(path: Path, code: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise P7ExecutorError(code) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise P7ExecutorError(code)
    return metadata


def _copy_regular(source: Path, target: Path, *, max_bytes: int = MAX_INPUT_BYTES) -> str:
    before = _regular_metadata(source, "p7_input_not_regular")
    if before.st_size < 0 or before.st_size > max_bytes:
        raise P7ExecutorError("p7_input_size_invalid")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(source_fd)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size):
            raise P7ExecutorError("p7_input_changed_during_snapshot")
        target_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        digest = hashlib.sha256()
        copied = 0
        try:
            while True:
                chunk = os.read(source_fd, 1024 * 1024)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > max_bytes:
                    raise P7ExecutorError("p7_input_size_invalid")
                digest.update(chunk)
                view = memoryview(chunk)
                while view:
                    written = os.write(target_fd, view)
                    view = view[written:]
            os.fsync(target_fd)
        finally:
            os.close(target_fd)
        after = os.fstat(source_fd)
        if (
            copied != before.st_size
            or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        ):
            raise P7ExecutorError("p7_input_changed_during_snapshot")
        return digest.hexdigest()
    finally:
        os.close(source_fd)


def _copy_release_snapshot(source: Path, signature: Path, target: Path) -> dict[str, str]:
    _require_absolute(source, "p7_release_dir_not_absolute")
    if not source.is_dir() or source.is_symlink():
        raise P7ExecutorError("p7_release_dir_invalid")
    target.mkdir(parents=True, mode=0o700)
    digests: dict[str, str] = {}
    for name in RELEASE_FILES:
        digests[name] = _copy_regular(source / name, target / name)
    digests["release-manifest.json.sig"] = _copy_regular(
        signature, target / "release-manifest.json.sig", max_bytes=1024 * 1024
    )
    _fsync_directory(target)
    return digests


def snapshot_inputs(inputs: SignedInputs, execution_dir: Path) -> SnapshotInputs:
    root = execution_dir / "inputs"
    root.mkdir(parents=True, mode=0o700)
    candidate = root / "candidate"
    rollback = root / "rollback"
    digests = {
        f"candidate/{key}": value
        for key, value in _copy_release_snapshot(inputs.release_dir, inputs.release_signature, candidate).items()
    }
    digests.update(
        {
            f"rollback/{key}": value
            for key, value in _copy_release_snapshot(
                inputs.rollback_release_dir, inputs.rollback_signature, rollback
            ).items()
        }
    )

    documents = {
        "plan.json": inputs.plan,
        "gate-evidence.json": inputs.gate_evidence,
        "gate-evidence.json.sig": inputs.gate_evidence_signature,
        "rollback-health.json": inputs.rollback_health_evidence,
        "rollback-health.json.sig": inputs.rollback_health_signature,
        "owner-approval.json": inputs.owner_approval,
        "owner-approval.json.sig": inputs.owner_approval_signature,
    }
    for name, source in documents.items():
        digests[name] = _copy_regular(source, root / name, max_bytes=16 * 1024 * 1024)
    _fsync_directory(root)
    return SnapshotInputs(
        plan=root / "plan.json",
        release_dir=candidate,
        release_signature=candidate / "release-manifest.json.sig",
        rollback_release_dir=rollback,
        rollback_signature=rollback / "release-manifest.json.sig",
        gate_evidence=root / "gate-evidence.json",
        gate_evidence_signature=root / "gate-evidence.json.sig",
        rollback_health_evidence=root / "rollback-health.json",
        rollback_health_signature=root / "rollback-health.json.sig",
        owner_approval=root / "owner-approval.json",
        owner_approval_signature=root / "owner-approval.json.sig",
        digests=dict(sorted(digests.items())),
    )


def load_p7_module(path: Path | None = None):
    script = path or Path(__file__).with_name("kolibri_p7_release.py")
    spec = importlib.util.spec_from_file_location("kolibri_p7_release_executor_binding", script)
    if not spec or not spec.loader:
        raise P7ExecutorError("p7_verifier_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _read_canonical(path: Path, p7, code: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise P7ExecutorError(code) from exc
    if not isinstance(payload, dict) or raw != p7.canonical_json(payload) + b"\n":
        raise P7ExecutorError(code)
    return payload


def reverify_plan(snapshot: SnapshotInputs, p7) -> VerifiedPlan:
    supplied = _read_canonical(snapshot.plan, p7, "p7_plan_not_canonical")
    try:
        recomputed = p7.paired_switch_plan(
            release_dir=snapshot.release_dir,
            rollback_release_dir=snapshot.rollback_release_dir,
            gate_evidence_path=snapshot.gate_evidence,
            gate_evidence_signature_path=snapshot.gate_evidence_signature,
            rollback_signature_path=snapshot.rollback_signature,
            rollback_health_evidence_path=snapshot.rollback_health_evidence,
            rollback_health_signature_path=snapshot.rollback_health_signature,
            previous_route_config_sha256=str(
                supplied.get("atomic_switch", {}).get("expected_previous_config_sha256", "")
            ),
            owner_approval_path=snapshot.owner_approval,
            owner_approval_signature_path=snapshot.owner_approval_signature,
            signature_path=snapshot.release_signature,
        )
    except Exception as exc:  # sanitized at this trust boundary
        raise P7ExecutorError("p7_signed_plan_reverification_failed") from exc
    if supplied != recomputed:
        raise P7ExecutorError("p7_plan_recomputation_mismatch")
    if (
        recomputed.get("schema_version") != EXPECTED_PLAN_SCHEMA
        or recomputed.get("status") != "planned_not_applied"
        or recomputed.get("production_applied") is not False
        or recomputed.get("executor_contract")
        != {
            "this_tool_can_apply": False,
            "root_required_by_downstream_executor": True,
            "owner_approval_and_all_bindings_must_be_reverified": True,
        }
    ):
        raise P7ExecutorError("p7_plan_contract_invalid")
    manifest, _, manifest_sha = p7.load_manifest(snapshot.release_dir)
    rollback_manifest, _, rollback_sha = p7.load_manifest(snapshot.rollback_release_dir)
    release_id = str(recomputed.get("release_id") or "")
    activation_mode = _activation_mode(recomputed.get("activation_mode"))
    _plan_canary_base_path(recomputed, release_id, activation_mode)
    targets = manifest.get("targets", {})
    if (
        targets.get("backend", {}).get("port") != EXPECTED_BACKEND_PORT
        or targets.get("frontend", {}).get("port") != EXPECTED_FRONTEND_PORT
        or recomputed.get("manifest_sha256") != manifest_sha
        or recomputed.get("rollback", {}).get("manifest_sha256") != rollback_sha
    ):
        raise P7ExecutorError("p7_exact_runtime_target_invalid")
    if recomputed.get("release_id") == rollback_manifest.get("release_id"):
        raise P7ExecutorError("p7_rollback_release_invalid")
    lock_record = manifest.get("toolchain", {}).get("lockfiles", {}).get(REQUIREMENTS_LOCK)
    if not isinstance(lock_record, dict) or not SHA256.fullmatch(str(lock_record.get("sha256", ""))):
        raise P7ExecutorError("p7_requirements_lock_unbound")
    return VerifiedPlan(recomputed, manifest, rollback_manifest, snapshot)


def _safe_archive_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise P7ExecutorError("p7_archive_path_invalid")
    return path


def safe_extract_tar(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False, mode=0o755)
    file_count = 0
    total_bytes = 0
    try:
        with tarfile.open(archive_path, "r:*") as archive:
            for member in archive:
                file_count += 1
                if file_count > MAX_ARCHIVE_FILES:
                    raise P7ExecutorError("p7_archive_limits_exceeded")
                relative = _safe_archive_name(member.name)
                if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                    raise P7ExecutorError("p7_archive_special_file_forbidden")
                target = destination.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True, mode=0o755)
                    continue
                if not member.isfile():
                    raise P7ExecutorError("p7_archive_member_invalid")
                total_bytes += member.size
                if total_bytes > MAX_ARCHIVE_BYTES:
                    raise P7ExecutorError("p7_archive_limits_exceeded")
                source = archive.extractfile(member)
                if source is None:
                    raise P7ExecutorError("p7_archive_member_unreadable")
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o755 if member.mode & 0o111 else 0o644)
                try:
                    copied = 0
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        copied += len(chunk)
                        view = memoryview(chunk)
                        while view:
                            written = os.write(descriptor, view)
                            view = view[written:]
                    if copied != member.size:
                        raise P7ExecutorError("p7_archive_member_size_mismatch")
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def _runtime_identity(user: str, group: str) -> tuple[int, int, Path]:
    if not SAFE_ACCOUNT.fullmatch(user) or not SAFE_ACCOUNT.fullmatch(group):
        raise P7ExecutorError("p7_runtime_account_invalid")
    try:
        account = pwd.getpwnam(user)
        group_record = grp.getgrnam(group)
    except KeyError as exc:
        raise P7ExecutorError("p7_runtime_account_missing") from exc
    home = Path(account.pw_dir)
    if not home.is_absolute():
        raise P7ExecutorError("p7_runtime_home_invalid")
    return account.pw_uid, group_record.gr_gid, home


def _prepare_runtime_parent(path: Path, uid: int, gid: int) -> None:
    existed = path.exists()
    path.mkdir(parents=True, exist_ok=True, mode=0o755)
    if not existed:
        os.chmod(path, 0o755)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise P7ExecutorError("p7_runtime_parent_invalid") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise P7ExecutorError("p7_runtime_parent_invalid")
    for current in (path, *path.parents):
        current_metadata = current.stat()
        mode = stat.S_IMODE(current_metadata.st_mode)
        execute_bit = 0o100 if current_metadata.st_uid == uid else 0o010 if current_metadata.st_gid == gid else 0o001
        if not mode & execute_bit:
            raise P7ExecutorError("p7_runtime_parent_not_traversable")


def stage_release(
    verified: VerifiedPlan,
    release_root: Path,
    data_root: Path,
    *,
    runtime_user: str,
    runtime_group: str,
) -> RuntimePaths:
    release_id = str(verified.plan["release_id"])
    if not SAFE_ID.fullmatch(release_id):
        raise P7ExecutorError("p7_release_id_invalid")
    runtime_uid, runtime_gid, runtime_home = _runtime_identity(runtime_user, runtime_group)
    _prepare_runtime_parent(release_root, runtime_uid, runtime_gid)
    _prepare_runtime_parent(data_root, runtime_uid, runtime_gid)
    final = release_root / release_id
    if final.exists():
        raise P7ExecutorError("p7_release_already_staged")
    data_dir = data_root / release_id
    if data_dir.exists():
        raise P7ExecutorError("p7_release_data_already_staged")
    temporary = release_root / f".{release_id}.staging-{os.getpid()}"
    if temporary.exists():
        raise P7ExecutorError("p7_release_staging_exists")
    temporary.mkdir(mode=0o700)
    published = False
    try:
        safe_extract_tar(verified.snapshot.release_dir / "backend.tar", temporary / "backend")
        safe_extract_tar(verified.snapshot.release_dir / "frontend.tar", temporary / "frontend")
        backend_dir = temporary / "backend" / "kolibri-backend"
        frontend_dir = temporary / "frontend" / "kolibri-v2" / "dist"
        lock = backend_dir / "requirements.lock"
        expected_lock = verified.manifest["toolchain"]["lockfiles"][REQUIREMENTS_LOCK]
        if (
            not backend_dir.is_dir()
            or not frontend_dir.is_dir()
            or not (frontend_dir / "index.html").is_file()
            or not lock.is_file()
            or lock.is_symlink()
            or lock.stat().st_size != expected_lock.get("size_bytes")
            or sha256_file(lock) != expected_lock.get("sha256")
        ):
            raise P7ExecutorError("p7_staged_release_integrity_failed")
        data_dir.mkdir(parents=True, exist_ok=False, mode=0o750)
        try:
            for relative in ("artifacts", "cache", "tmp"):
                child = data_dir / relative
                child.mkdir(mode=0o750)
                os.chown(child, runtime_uid, runtime_gid)
            os.chown(data_dir, runtime_uid, runtime_gid)
            # The immutable payload remains root-owned, but the unprivileged
            # runtime account must be able to traverse and read its contents.
            os.chmod(temporary, 0o755)
            os.replace(temporary, final)
            published = True
            _fsync_directory(release_root)
            _fsync_directory(data_root)
        except Exception:
            shutil.rmtree(data_dir, ignore_errors=True)
            if published:
                shutil.rmtree(final, ignore_errors=True)
            raise
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return RuntimePaths(
        release_dir=final,
        backend_dir=final / "backend" / "kolibri-backend",
        frontend_dir=final / "frontend" / "kolibri-v2" / "dist",
        data_dir=data_dir,
        database=data_dir / "kolibri.db",
        venv_dir=data_dir / "venv",
        runtime_uid=runtime_uid,
        runtime_gid=runtime_gid,
        runtime_home=runtime_home,
    )


def _parse_environment_file(path: Path) -> dict[str, str]:
    metadata = _regular_metadata(path, "p7_runtime_secret_file_invalid")
    if metadata.st_size > 1024 * 1024:
        raise P7ExecutorError("p7_runtime_secret_file_invalid")
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise P7ExecutorError("p7_runtime_secret_file_invalid") from exc
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def require_runtime_secrets(path: Path, manifest: Mapping[str, Any]) -> None:
    requirements = manifest.get("runtime_requirements", {})
    names = requirements.get("required_backend_secret_names")
    minimum = requirements.get("minimum_secret_bytes")
    if not isinstance(names, list) or not isinstance(minimum, int) or minimum < 32:
        raise P7ExecutorError("p7_runtime_secret_contract_invalid")
    values = _parse_environment_file(path)
    if any(len(values.get(str(name), "").encode("utf-8")) < minimum for name in names):
        raise P7ExecutorError("p7_required_runtime_secret_missing")


def install_locked_environment(
    runtime: RuntimePaths,
    config: ExecutorConfig,
    runner: CommandRunner,
    expected_python: str,
) -> None:
    lock = runtime.backend_dir / "requirements.lock"
    actual_python = runner.run(
        (
            config.python_binary,
            "-I",
            "-c",
            "import platform; print(platform.python_version())",
        ),
        timeout=30,
    ).stdout.strip()
    if actual_python != expected_python:
        raise P7ExecutorError("p7_runtime_python_version_mismatch")
    runner.run((config.python_binary, "-m", "venv", str(runtime.venv_dir)), timeout=180)
    python = runtime.venv_dir / "bin" / "python"
    runner.run(
        (
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--require-hashes",
            "--no-deps",
            "-r",
            str(lock),
        ),
        cwd=runtime.backend_dir,
        timeout=1800,
    )
    runner.run((str(python), "-m", "pip", "check"), cwd=runtime.backend_dir, timeout=120)


def render_unit(template: Path, values: Mapping[str, str]) -> bytes:
    _regular_metadata(template, "p7_unit_template_invalid")
    text = template.read_text(encoding="utf-8")
    for key, value in values.items():
        if any(character in value for character in ("\n", "\r", "\x00", "%")):
            raise P7ExecutorError("p7_unit_value_invalid")
        text = text.replace(f"@@{key}@@", value)
    if re.search(r"@@[A-Z0-9_]+@@", text):
        raise P7ExecutorError("p7_unit_template_unresolved")
    return text.encode("utf-8")


def canary_base_path(release_id: str) -> str:
    if not SAFE_ID.fullmatch(release_id):
        raise P7ExecutorError("p7_release_id_invalid")
    return f"{CANARY_PREFIX}/{release_id}/"


def _activation_mode(value: Any) -> str:
    if not isinstance(value, str) or value not in ACTIVATION_MODES:
        raise P7ExecutorError("p7_activation_mode_invalid")
    return value


def _plan_canary_base_path(plan: Mapping[str, Any], release_id: str, activation_mode: str) -> str | None:
    if activation_mode == "production":
        if "canary_base_path" in plan:
            raise P7ExecutorError("p7_plan_canary_base_path_invalid")
        return None
    value = plan.get("canary_base_path")
    expected = canary_base_path(release_id)
    if not isinstance(value, str) or value != expected:
        raise P7ExecutorError("p7_plan_canary_base_path_invalid")
    return value


def _canary_public_path(base_path: str, relative: str) -> str:
    if (
        not base_path.startswith("/")
        or not base_path.endswith("/")
        or "//" in base_path
        or "?" in base_path
        or "#" in base_path
    ):
        raise P7ExecutorError("p7_canary_base_path_invalid")
    if any(character in relative for character in ("\x00", "?", "#")) or "//" in relative:
        raise P7ExecutorError("p7_canary_probe_path_invalid")
    raw = relative.strip()
    if raw.startswith(("http://", "https://")):
        raise P7ExecutorError("p7_canary_probe_path_invalid")
    path = PurePosixPath("/" + raw.lstrip("/"))
    if any(part in {"", ".", ".."} for part in path.parts[1:]):
        raise P7ExecutorError("p7_canary_probe_path_invalid")
    suffix = path.as_posix().lstrip("/")
    return base_path + suffix if suffix else base_path


def _validated_frontend_base_path(raw: str, release_id: str) -> str:
    if raw == "/":
        return raw
    expected = canary_base_path(release_id)
    if raw != expected:
        raise P7ExecutorError("p7_frontend_base_path_invalid")
    return raw


def atomic_write(path: Path, content: bytes, *, mode: int, reference: os.stat_result | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    temporary = path.with_name(f".{path.name}.p7-{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        if reference is not None:
            os.chmod(temporary, stat.S_IMODE(reference.st_mode))
            os.chown(temporary, reference.st_uid, reference.st_gid)
        else:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def install_runtime_units(runtime: RuntimePaths, config: ExecutorConfig) -> list[UnitBackup]:
    if runtime.runtime_uid is None or runtime.runtime_gid is None or runtime.runtime_home is None:
        raise P7ExecutorError("p7_runtime_account_binding_missing")
    templates = runtime.backend_dir / "ops" / "release" / "templates"
    frontend_base_path = _validated_frontend_base_path(config.frontend_base_path, runtime.release_dir.name)
    values = {
        "RELEASE_ID": runtime.release_dir.name,
        "BACKEND_DIR": str(runtime.backend_dir),
        "FRONTEND_DIR": str(runtime.frontend_dir),
        "DATA_DIR": str(runtime.data_dir),
        "DATABASE_PATH": str(runtime.database),
        "VENV_DIR": str(runtime.venv_dir),
        "STATIC_SERVER": str(runtime.backend_dir / "ops" / "release" / "kolibri_p7_static_server.py"),
        "RUNTIME_SECRET_FILE": str(config.runtime_secret_file),
        "BACKEND_PORT": str(EXPECTED_BACKEND_PORT),
        "FRONTEND_PORT": str(EXPECTED_FRONTEND_PORT),
        "FRONTEND_BASE_PATH": frontend_base_path,
        "RUNTIME_USER": config.runtime_user,
        "RUNTIME_GROUP": config.runtime_group,
        "RUNTIME_HOME": str(runtime.runtime_home) if runtime.runtime_home is not None else "",
    }
    definitions = (
        ("kolibri-backend-p7.service.in", BACKEND_SERVICE),
        ("kolibri-frontend-p7.service.in", FRONTEND_SERVICE),
    )
    backups: list[UnitBackup] = []
    for template_name, unit_name in definitions:
        path = config.systemd_dir / unit_name
        metadata = path.lstat() if path.exists() else None
        if metadata is not None and (stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode)):
            raise P7ExecutorError("p7_existing_unit_invalid")
        backups.append(
            UnitBackup(path, metadata is not None, path.read_bytes() if metadata is not None else None, metadata)
        )
        atomic_write(
            path,
            render_unit(templates / template_name, values),
            mode=0o644,
            reference=metadata,
        )
    return backups


def restore_runtime_units(backups: Iterable[UnitBackup]) -> None:
    for backup in backups:
        if backup.existed:
            assert backup.content is not None and backup.metadata is not None
            atomic_write(
                backup.path,
                backup.content,
                mode=stat.S_IMODE(backup.metadata.st_mode),
                reference=backup.metadata,
            )
        else:
            backup.path.unlink(missing_ok=True)
            _fsync_directory(backup.path.parent)


def consistent_sqlite_backup(source: Path, destination: Path) -> dict[str, Any]:
    metadata = _regular_metadata(source, "p7_source_database_invalid")
    if destination.exists():
        raise P7ExecutorError("p7_candidate_database_exists")
    # The previous backend service has already been stopped.  An exclusive
    # transaction proves that no unknown writer still owns the SQLite file.
    try:
        with sqlite3.connect(source, timeout=0.25) as probe:
            probe.execute("BEGIN EXCLUSIVE")
            if probe.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise P7ExecutorError("p7_source_database_integrity_failed")
            probe.rollback()
    except sqlite3.Error as exc:
        raise P7ExecutorError("p7_sqlite_write_drain_not_proven") from exc

    temporary = destination.with_name(f".{destination.name}.backup-{os.getpid()}")
    try:
        source_uri = f"file:{urllib.parse.quote(str(source))}?mode=ro"
        with sqlite3.connect(source_uri, uri=True) as source_connection, sqlite3.connect(temporary) as target:
            source_connection.execute("PRAGMA query_only=ON")
            source_connection.backup(target, pages=1024, sleep=0.01)
            target.commit()
            if target.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise P7ExecutorError("p7_database_backup_integrity_failed")
        os.chmod(temporary, 0o600)
        with contextlib.suppress(PermissionError):
            os.chown(temporary, metadata.st_uid, metadata.st_gid)
        os.replace(temporary, destination)
        _fsync_directory(destination.parent)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "source_sha256": sha256_file(source),
        "backup_sha256": sha256_file(destination),
        "size_bytes": destination.stat().st_size,
        "quick_check": "ok",
        "writer_drained": True,
    }


def online_sqlite_snapshot(
    source: Path,
    destination: Path,
    *,
    deadline_seconds: float = 30.0,
    backup_pages: int = 1024,
    backup_sleep: float = 0.01,
    progress_hook: Callable[[int, int, int], None] | None = None,
) -> dict[str, Any]:
    metadata = _regular_metadata(source, "p7_source_database_invalid")
    if destination.exists():
        raise P7ExecutorError("p7_candidate_database_exists")
    if deadline_seconds <= 0 or backup_pages <= 0 or backup_sleep < 0:
        raise P7ExecutorError("p7_sqlite_online_snapshot_options_invalid")
    deadline = time.monotonic() + deadline_seconds
    deadline_exceeded = False

    def deadline_expired() -> bool:
        nonlocal deadline_exceeded
        if time.monotonic() >= deadline:
            deadline_exceeded = True
            return True
        return False

    def require_deadline() -> None:
        if deadline_expired():
            raise sqlite3.OperationalError("sqlite online backup deadline exceeded")

    def progress(status: int, remaining: int, total: int) -> None:
        require_deadline()
        if progress_hook is not None:
            progress_hook(status, remaining, total)
        require_deadline()

    def pragma_progress() -> int:
        return 1 if deadline_expired() else 0

    temporary = destination.with_name(f".{destination.name}.online-{os.getpid()}")
    try:
        source_uri = f"file:{urllib.parse.quote(str(source))}?mode=ro"
        with sqlite3.connect(source_uri, uri=True, timeout=5.0) as source_connection, sqlite3.connect(temporary) as target:
            source_connection.execute("PRAGMA query_only=ON")
            require_deadline()
            source_connection.backup(target, pages=backup_pages, progress=progress, sleep=backup_sleep)
            target.commit()
            require_deadline()
            target.set_progress_handler(pragma_progress, 1)
            try:
                if target.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise P7ExecutorError("p7_database_backup_integrity_failed")
                if target.execute("PRAGMA foreign_key_check").fetchall():
                    raise P7ExecutorError("p7_database_backup_foreign_key_failed")
            finally:
                target.set_progress_handler(None, 0)
            require_deadline()
        os.chmod(temporary, 0o600)
        with contextlib.suppress(PermissionError):
            os.chown(temporary, metadata.st_uid, metadata.st_gid)
        os.replace(temporary, destination)
        _fsync_directory(destination.parent)
    except sqlite3.Error as exc:
        if deadline_exceeded:
            raise P7ExecutorError("p7_sqlite_online_snapshot_deadline_exceeded") from exc
        raise P7ExecutorError("p7_sqlite_online_snapshot_failed") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "backup_sha256": sha256_file(destination),
        "size_bytes": destination.stat().st_size,
        "quick_check": "ok",
        "foreign_key_check": "ok",
        "writer_drained": False,
        "online_snapshot": True,
    }


def migrate_candidate_database(runtime: RuntimePaths, runner: CommandRunner) -> dict[str, Any]:
    helper = runtime.backend_dir / "ops" / "release" / "kolibri_p7_migrate.py"
    result = runner.run(
        (
            str(runtime.venv_dir / "bin" / "python"),
            "-B",
            str(helper),
            "--database",
            str(runtime.database),
            "--expected-head",
            EXPECTED_SCHEMA_HEAD,
        ),
        cwd=runtime.backend_dir,
        timeout=600,
    )
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise P7ExecutorError("p7_migration_evidence_invalid") from exc
    if payload.get("status") != "migrated_verified" or payload.get("schema_head") != EXPECTED_SCHEMA_HEAD:
        raise P7ExecutorError("p7_migration_evidence_invalid")
    with sqlite3.connect(f"file:{urllib.parse.quote(str(runtime.database))}?mode=ro", uri=True) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        quick = connection.execute("PRAGMA quick_check").fetchone()
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    if revision != (EXPECTED_SCHEMA_HEAD,) or quick != ("ok",) or foreign_keys:
        raise P7ExecutorError("p7_migrated_database_verification_failed")
    if payload.get("database_sha256") != sha256_file(runtime.database):
        raise P7ExecutorError("p7_migration_evidence_invalid")
    return payload


def _location_blocks(text: str) -> dict[str, tuple[int, int, str]]:
    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line)
    matcher = re.compile(r"^(?P<indent>\s*)location\s+(?:(?:=|\^~)\s+)?(?P<path>/\S*)\s*\{")
    blocks: dict[str, tuple[int, int, str]] = {}
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
                raise P7ExecutorError("p7_nginx_location_unclosed")
            depth += lines[end].count("{") - lines[end].count("}")
        if path in blocks:
            raise P7ExecutorError("p7_nginx_location_duplicate")
        blocks[path] = (offsets[index], offsets[end] + len(lines[end]), match.group("indent"))
        index = end + 1
    return blocks


def _directive_spans(block: str, name: str) -> list[tuple[int, int, str]]:
    """Return non-commented nginx directive value spans.

    Nginx permits directives on the same line as a location opening brace.
    Parsing each line only up to its first ``#`` keeps comments from becoming
    mutation targets while supporting both canonical multiline and compact
    configurations.
    """

    matcher = re.compile(rf"\b{re.escape(name)}\s+([^;\s]+)\s*;")
    spans: list[tuple[int, int, str]] = []
    offset = 0
    for line in block.splitlines(keepends=True):
        code = line.split("#", 1)[0]
        for match in matcher.finditer(code):
            spans.append((offset + match.start(1), offset + match.end(1), match.group(1)))
        offset += len(line)
    return spans


def _proxy_pass(block: str) -> str | None:
    matches = _directive_spans(block, "proxy_pass")
    if len(matches) > 1:
        raise P7ExecutorError("p7_nginx_proxy_ambiguous")
    return matches[0][2] if matches else None


def _replace_proxy_pass(block: str, target: str) -> str:
    matches = _directive_spans(block, "proxy_pass")
    if len(matches) != 1:
        raise P7ExecutorError("p7_nginx_proxy_ambiguous")
    start, end, _ = matches[0]
    return block[:start] + target + block[end:]


def render_paired_site(
    active: bytes,
    *,
    release_id: str,
    candidate_backend: str,
    candidate_frontend: str,
    rollback_backend: str,
    rollback_frontend: str,
) -> bytes:
    try:
        text = active.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise P7ExecutorError("p7_nginx_site_not_utf8") from exc
    blocks = _location_blocks(text)
    missing = [route for route in (*BACKEND_ROUTES, FRONTEND_ROUTE) if route not in blocks]
    if missing:
        raise P7ExecutorError("p7_nginx_routes_missing")
    for route in BACKEND_ROUTES:
        start, end, _ = blocks[route]
        if _proxy_pass(text[start:end]) != rollback_backend:
            raise P7ExecutorError("p7_active_backend_route_drift")
    frontend_start, frontend_end, indent = blocks[FRONTEND_ROUTE]
    frontend_block = text[frontend_start:frontend_end]
    frontend_proxy = _proxy_pass(frontend_block)
    root_directives = _directive_spans(frontend_block, "root")
    if frontend_proxy is not None:
        if frontend_proxy != rollback_frontend:
            raise P7ExecutorError("p7_active_frontend_route_drift")
    elif len(root_directives) != 1:
        raise P7ExecutorError("p7_active_frontend_route_ambiguous")

    candidate = text
    replacements: list[tuple[int, int, str]] = []
    for route in BACKEND_ROUTES:
        start, end, _ = blocks[route]
        block = candidate[start:end]
        updated = _replace_proxy_pass(block, candidate_backend)
        replacements.append((start, end, updated))
    inner = indent + "    "
    frontend_replacement = (
        f"{indent}location / {{\n"
        f"{inner}# Kolibri immutable paired release {release_id}\n"
        f"{inner}proxy_http_version 1.1;\n"
        f"{inner}proxy_set_header Host $host;\n"
        f"{inner}proxy_set_header X-Real-IP $remote_addr;\n"
        f"{inner}proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
        f"{inner}proxy_set_header X-Forwarded-Proto $scheme;\n"
        f"{inner}proxy_pass {candidate_frontend};\n"
        f"{indent}}}\n"
    )
    replacements.append((frontend_start, frontend_end, frontend_replacement))
    for start, end, value in sorted(replacements, reverse=True):
        candidate = candidate[:start] + value + candidate[end:]

    rendered = _location_blocks(candidate)
    for route in BACKEND_ROUTES:
        start, end, _ = rendered[route]
        if _proxy_pass(candidate[start:end]) != candidate_backend:
            raise P7ExecutorError("p7_nginx_backend_render_failed")
    start, end, _ = rendered[FRONTEND_ROUTE]
    if _proxy_pass(candidate[start:end]) != candidate_frontend:
        raise P7ExecutorError("p7_nginx_frontend_render_failed")
    return candidate.encode("utf-8")


def _proxy_common_headers(indent: str) -> str:
    return (
        f"{indent}proxy_http_version 1.1;\n"
        f"{indent}proxy_set_header Host $host;\n"
        f"{indent}proxy_set_header X-Real-IP $remote_addr;\n"
        f"{indent}proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
        f"{indent}proxy_set_header X-Forwarded-Proto $scheme;\n"
    )


def _canary_backend_location(
    *,
    indent: str,
    release_id: str,
    route: str,
    candidate_backend: str,
) -> str:
    base = canary_base_path(release_id)
    location = f"{base}{route.lstrip('/')}"
    target = f"{candidate_backend.rstrip('/')}{route}"
    inner = indent + "    "
    websocket_headers = ""
    if route == "/ws/":
        websocket_headers = (
            f"{inner}proxy_set_header Upgrade $http_upgrade;\n"
            f"{inner}proxy_set_header Connection \"upgrade\";\n"
        )
    return (
        f"{indent}location ^~ {location} {{\n"
        f"{inner}# Kolibri isolated P7 canary {release_id}\n"
        f"{_proxy_common_headers(inner)}"
        f"{inner}proxy_set_header X-Forwarded-Prefix {base.rstrip('/')};\n"
        f"{websocket_headers}"
        f"{inner}proxy_pass {target};\n"
        f"{indent}}}\n"
    )


def _canary_frontend_location(
    *,
    indent: str,
    release_id: str,
    candidate_frontend: str,
) -> str:
    base = canary_base_path(release_id)
    inner = indent + "    "
    return (
        f"{indent}location ^~ {base} {{\n"
        f"{inner}# Kolibri isolated P7 canary {release_id}\n"
        f"{_proxy_common_headers(inner)}"
        f"{inner}proxy_set_header X-Forwarded-Prefix {base.rstrip('/')};\n"
        f"{inner}proxy_pass {candidate_frontend.rstrip('/')};\n"
        f"{indent}}}\n"
    )


def render_canary_site(
    active: bytes,
    *,
    release_id: str,
    candidate_backend: str,
    candidate_frontend: str,
) -> bytes:
    try:
        text = active.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise P7ExecutorError("p7_nginx_site_not_utf8") from exc
    blocks = _location_blocks(text)
    if FRONTEND_ROUTE not in blocks:
        raise P7ExecutorError("p7_nginx_routes_missing")
    base = canary_base_path(release_id)
    canary_routes = tuple(f"{base}{route.lstrip('/')}" for route in BACKEND_ROUTES) + (base,)
    if any(route in blocks for route in canary_routes):
        raise P7ExecutorError("p7_canary_route_already_exists")

    frontend_start, _frontend_end, indent = blocks[FRONTEND_ROUTE]
    rendered_blocks = [
        _canary_backend_location(
            indent=indent,
            release_id=release_id,
            route=route,
            candidate_backend=candidate_backend,
        )
        for route in BACKEND_ROUTES
    ]
    rendered_blocks.append(
        _canary_frontend_location(
            indent=indent,
            release_id=release_id,
            candidate_frontend=candidate_frontend,
        )
    )
    insertion = "".join(rendered_blocks)
    candidate = text[:frontend_start] + insertion + text[frontend_start:]

    rendered = _location_blocks(candidate)
    for route in BACKEND_ROUTES:
        canary_route = f"{base}{route.lstrip('/')}"
        start, end, _ = rendered[canary_route]
        if _proxy_pass(candidate[start:end]) != f"{candidate_backend.rstrip('/')}{route}":
            raise P7ExecutorError("p7_canary_backend_render_failed")
    start, end, _ = rendered[base]
    if _proxy_pass(candidate[start:end]) != candidate_frontend.rstrip("/"):
        raise P7ExecutorError("p7_canary_frontend_render_failed")
    for route, (start, end, _) in blocks.items():
        shift = len(insertion) if start >= frontend_start else 0
        if candidate[start + shift : end + shift] != text[start:end]:
            raise P7ExecutorError("p7_canary_modified_existing_route")
    return candidate.encode("utf-8")


def isolated_nginx_test(
    candidate: bytes,
    *,
    active_site: Path,
    nginx_main: Path,
    sites_enabled_dir: Path,
    nginx_binary: str,
    runner: CommandRunner,
) -> None:
    main = _regular_metadata(nginx_main, "p7_nginx_main_invalid")
    del main
    text = nginx_main.read_text(encoding="utf-8")
    include_pattern = re.compile(
        r"(?m)^(?P<indent>\s*)include\s+" + re.escape(str(sites_enabled_dir)) + r"/\*\s*;\s*$"
    )
    matches = list(include_pattern.finditer(text))
    if len(matches) != 1:
        raise P7ExecutorError("p7_nginx_include_contract_invalid")
    with tempfile.TemporaryDirectory(prefix="kolibri-p7-nginx-") as directory:
        root = Path(directory)
        candidate_path = root / "candidate.conf"
        candidate_path.write_bytes(candidate)
        includes: list[Path] = []
        for path in sorted(sites_enabled_dir.iterdir()):
            try:
                if path.resolve() == active_site.resolve():
                    continue
            except OSError as exc:
                raise P7ExecutorError("p7_nginx_include_invalid") from exc
            includes.append(path.resolve())
        includes.append(candidate_path)
        replacement = "\n".join(
            f"{matches[0].group('indent')}include {path};" for path in includes
        )
        test_main = include_pattern.sub(replacement, text, count=1)
        test_path = root / "nginx.conf"
        test_path.write_text(test_main, encoding="utf-8")
        runner.run((nginx_binary, "-t", "-c", str(test_path), "-p", "/"), timeout=30)


def _json_object(result: HttpResult, code: str) -> dict[str, Any]:
    try:
        payload = json.loads(result.body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise P7ExecutorError(code) from exc
    if not isinstance(payload, dict):
        raise P7ExecutorError(code)
    return payload


def _release_header(headers: Mapping[str, str]) -> str | None:
    return headers.get("x-kolibri-release")


def _release_header_matches(result: HttpResult, release_id: str) -> bool:
    canonical = _release_header(result.headers)
    alias = result.headers.get("x-kolibri-release-id")
    return canonical == release_id and alias in {None, release_id}


class _FrontendAssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value for name, value in attrs if value is not None}
        if tag.lower() == "script" and "src" in values:
            self.assets.append(values["src"])
        elif tag.lower() == "link" and "href" in values:
            self.assets.append(values["href"])


def _normalized_public_path(path: str) -> str | None:
    if not path.startswith("/") or "//" in path or "\x00" in path:
        return None
    try:
        decoded = urllib.parse.unquote(path)
    except ValueError:
        return None
    if "\x00" in decoded:
        return None
    candidate = PurePosixPath(decoded)
    if not candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts[1:]):
        return None
    return candidate.as_posix()


def _asset_extension(path: str) -> str | None:
    suffix = PurePosixPath(urllib.parse.unquote(path)).suffix.lower()
    return suffix[1:] if suffix in {".js", ".css"} else None


def _is_hashed_frontend_asset(path: str) -> bool:
    if _asset_extension(path) is None:
        return False
    name = PurePosixPath(urllib.parse.unquote(path)).name
    return HASHED_FRONTEND_ASSET.search(name) is not None


def _frontend_asset_paths(raw_asset: str, *, base_path: str) -> tuple[str, str] | None:
    raw = raw_asset.strip()
    if not raw:
        return None
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        return None
    if not parsed.path:
        return None
    public_path = parsed.path
    is_absolute_asset = public_path.startswith("/")
    if not is_absolute_asset:
        public_path = urllib.parse.urljoin(base_path, public_path)
    public_path = _normalized_public_path(public_path)
    if public_path is None:
        return None
    if base_path != "/":
        if is_absolute_asset and not public_path.startswith(base_path):
            return None
        if not public_path.startswith(base_path):
            return None
        suffix = public_path[len(base_path) :]
        production_path = "/" + suffix.lstrip("/")
    else:
        production_path = public_path
    production_path = _normalized_public_path(production_path)
    if production_path is None or not _is_hashed_frontend_asset(production_path):
        return None
    request_path = production_path if base_path == "/" else _canary_public_path(base_path, production_path)
    return production_path, request_path


def _extract_frontend_asset(html: bytes, *, base_path: str) -> tuple[str, str]:
    try:
        text = html.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise P7ExecutorError("p7_frontend_html_invalid") from exc
    parser = _FrontendAssetParser()
    try:
        parser.feed(text)
    except (ValueError, AssertionError) as exc:
        raise P7ExecutorError("p7_frontend_html_invalid") from exc
    for raw_asset in parser.assets:
        paths = _frontend_asset_paths(raw_asset, base_path=base_path)
        if paths is not None:
            return paths
    raise P7ExecutorError("p7_frontend_hashed_asset_missing")


def _asset_mime_matches(path: str, content_type: str) -> bool:
    mime = content_type.split(";", 1)[0].strip().lower()
    extension = _asset_extension(path)
    if extension == "css":
        return mime == "text/css"
    if extension == "js":
        return mime in JAVASCRIPT_MIME_TYPES
    return False


def _probe_frontend_asset(
    client: HttpClient,
    frontend: HttpResult,
    release_id: str,
    *,
    base_path: str,
) -> dict[str, Any]:
    production_path, request_path = _extract_frontend_asset(frontend.body, base_path=base_path)
    asset = client.request("GET", request_path)
    content_type = asset.headers.get("content-type", "")
    if (
        asset.status != 200
        or not _release_header_matches(asset, release_id)
        or not _asset_mime_matches(production_path, content_type)
        or not asset.body
        or "text/html" in content_type.lower()
    ):
        raise P7ExecutorError("p7_public_asset_gate_failed")
    return {
        "status": "passed",
        "production_path": production_path,
        "request_path": request_path,
        "http_status": asset.status,
        "content_type": content_type.split(";", 1)[0].strip().lower(),
        "size_bytes": len(asset.body),
        "release_id": release_id,
    }


def probe_release_identity(
    backend_url: str,
    frontend_url: str,
    release_id: str,
    *,
    frontend_path: str = "/",
    client_factory: Callable[[str], HttpClient] = HttpClient,
) -> dict[str, Any]:
    backend = client_factory(backend_url).request("GET", "/api/health")
    payload = _json_object(backend, "p7_backend_health_invalid")
    frontend = client_factory(frontend_url).request("GET", frontend_path)
    if (
        backend.status != 200
        or payload.get("status") != "ok"
        or payload.get("release_id") != release_id
        or not _release_header_matches(backend, release_id)
        or frontend.status != 200
        or not _release_header_matches(frontend, release_id)
        or release_id.encode("utf-8") not in frontend.body
    ):
        raise P7ExecutorError("p7_release_identity_probe_failed")
    return {
        "status": "passed",
        "release_id": release_id,
        "backend_http_status": backend.status,
        "frontend_http_status": frontend.status,
    }


def probe_rollback_identity(
    base_url: str,
    release_id: str,
    *,
    client_factory: Callable[[str], HttpClient] = HttpClient,
) -> dict[str, Any]:
    """Prove the restored P6 backend and frontend without assuming its old
    static nginx surface emits the new frontend response header.
    """

    client = client_factory(base_url)
    backend = client.request("GET", "/api/health")
    payload = _json_object(backend, "p7_rollback_health_invalid")
    frontend = client.request("GET", "/")
    if (
        backend.status != 200
        or payload.get("status") != "ok"
        or payload.get("release_id") != release_id
        or not _release_header_matches(backend, release_id)
        or frontend.status != 200
        or release_id.encode("utf-8") not in frontend.body
    ):
        raise P7ExecutorError("p7_rollback_identity_probe_failed")
    return {"status": "passed", "release_id": release_id}


def public_post_gates(
    base_url: str,
    release_id: str,
    *,
    base_path: str = "/",
    client_factory: Callable[[str], HttpClient] = HttpClient,
) -> dict[str, Any]:
    client = client_factory(base_url)
    if base_path == "/":
        frontend_path = "/"
        health_path = "/api/health"
        missing_path = "/api/v1/__kolibri_p7_missing__"
        bootstrap_path = "/api/v1/shell/bootstrap"
    else:
        if base_path != canary_base_path(release_id):
            raise P7ExecutorError("p7_canary_base_path_invalid")
        frontend_path = _canary_public_path(base_path, "/")
        health_path = _canary_public_path(base_path, "/api/health")
        missing_path = _canary_public_path(base_path, "/api/v1/__kolibri_p7_missing__")
        bootstrap_path = _canary_public_path(base_path, "/api/v1/shell/bootstrap")
    health = client.request("GET", health_path)
    health_payload = _json_object(health, "p7_public_health_invalid")
    frontend = client.request("GET", frontend_path)
    if (
        health.status != 200
        or health_payload.get("status") != "ok"
        or health_payload.get("release_id") != release_id
        or not _release_header_matches(health, release_id)
        or frontend.status != 200
        or not _release_header_matches(frontend, release_id)
        or release_id.encode("utf-8") not in frontend.body
    ):
        raise P7ExecutorError("p7_public_post_gate_failed")
    frontend_asset = _probe_frontend_asset(client, frontend, release_id, base_path=base_path)
    missing = client.request("GET", missing_path)
    bootstrap = client.request("POST", bootstrap_path, {})
    bootstrap_payload = _json_object(bootstrap, "p7_public_bootstrap_invalid")
    if (
        missing.status != 404
        or "application/json" not in missing.headers.get("content-type", "")
        or not _release_header_matches(missing, release_id)
        or bootstrap.status != 200
        or not _release_header_matches(bootstrap, release_id)
        or bootstrap_payload.get("session_type") not in {"anonymous", "authenticated"}
    ):
        raise P7ExecutorError("p7_public_post_gate_failed")
    return {
        "status": "passed",
        "release_id": release_id,
        "frontend": frontend.status,
        "frontend_asset": frontend_asset,
        "health": health.status,
        "json_404": missing.status,
        "session_bootstrap": bootstrap.status,
    }


def _service_active(runner: CommandRunner, systemctl: str, service: str) -> None:
    result = runner.run((systemctl, "is-active", service), timeout=30)
    if result.stdout.strip() != "active":
        raise P7ExecutorError("p7_service_not_active")


def _candidate_units_quiescent(runner: CommandRunner, systemctl: str) -> None:
    for service in (BACKEND_SERVICE, FRONTEND_SERVICE):
        active = runner.run(
            (systemctl, "show", "--property=ActiveState", "--value", service),
            timeout=30,
        ).stdout.strip()
        enabled = runner.run(
            (systemctl, "show", "--property=UnitFileState", "--value", service),
            timeout=30,
        ).stdout.strip()
        if active not in {"", "inactive", "failed"} or enabled not in {"", "disabled", "not-found"}:
            raise P7ExecutorError("p7_candidate_unit_not_quiescent")


def _write_audit(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    if path.exists():
        raise P7ExecutorError("p7_audit_already_exists")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def execute(
    config: ExecutorConfig,
    *,
    runner: CommandRunner | None = None,
    p7_module=None,
    client_factory: Callable[[str], HttpClient] = HttpClient,
    migrate_hook: Callable[[RuntimePaths, CommandRunner], dict[str, Any]] = migrate_candidate_database,
) -> dict[str, Any]:
    require_p7_runtime_host()
    if os.geteuid() != 0:
        raise P7ExecutorError("p7_executor_root_required")
    if not SAFE_SERVICE.fullmatch(config.previous_backend_service) or not SAFE_PREVIOUS_BACKEND_SERVICE.fullmatch(
        config.previous_backend_service
    ):
        raise P7ExecutorError("p7_previous_backend_service_invalid")
    if config.previous_backend_service == BACKEND_SERVICE:
        raise P7ExecutorError("p7_previous_backend_service_conflicts_with_candidate")
    for path in (
        config.active_site,
        config.nginx_main,
        config.source_database,
        config.runtime_secret_file,
        config.release_root,
        config.data_root,
        config.backup_root,
        config.state_root,
        config.systemd_dir,
        config.lock_path,
    ):
        _require_absolute(path, "p7_executor_path_not_absolute")

    runner = runner or CommandRunner()
    p7 = p7_module or load_p7_module()
    config.lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    lock_descriptor = os.open(config.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise P7ExecutorError("p7_executor_already_running") from exc

        run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        execution_dir = config.state_root / f"p7-{run_id}-{os.getpid()}"
        execution_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        snapshot = snapshot_inputs(config.inputs, execution_dir)
        verified = reverify_plan(snapshot, p7)
        release_id = str(verified.plan["release_id"])
        activation_mode = _activation_mode(verified.plan.get("activation_mode"))
        canary_path = _plan_canary_base_path(verified.plan, release_id, activation_mode)
        frontend_base_path = canary_path or "/"
        expected_previous_sha = str(
            verified.plan["atomic_switch"]["expected_previous_config_sha256"]
        )
        active_metadata = _regular_metadata(config.active_site, "p7_active_site_invalid")
        active_bytes = config.active_site.read_bytes()
        if sha256_bytes(active_bytes) != expected_previous_sha:
            raise P7ExecutorError("p7_active_site_sha_mismatch")

        backup_dir = config.backup_root / f"{run_id}-{release_id}"
        backup_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        backup_site = backup_dir / "kolibriai.nginx.previous"
        _copy_regular(config.active_site, backup_site, max_bytes=32 * 1024 * 1024)
        if backup_site.read_bytes() != active_bytes:
            raise P7ExecutorError("p7_active_site_backup_mismatch")

        runtime: RuntimePaths | None = None
        unit_backups: list[UnitBackup] = []
        previous_stopped = False
        candidate_start_attempted = False
        site_replaced = False
        reload_attempted = False
        database_evidence: dict[str, Any] | None = None
        migration_evidence: dict[str, Any] | None = None
        try:
            runtime = stage_release(
                verified,
                config.release_root,
                config.data_root,
                runtime_user=config.runtime_user,
                runtime_group=config.runtime_group,
            )
            require_runtime_secrets(config.runtime_secret_file, verified.manifest)
            install_locked_environment(
                runtime,
                config,
                runner,
                str(verified.manifest["toolchain"]["python"]),
            )
            _candidate_units_quiescent(runner, config.systemctl_binary)
            runtime_config = dataclasses.replace(
                config,
                frontend_base_path=frontend_base_path,
            )
            unit_backups = install_runtime_units(runtime, runtime_config)
            runner.run((config.systemctl_binary, "daemon-reload"), timeout=30)

            if activation_mode == "production":
                runner.run((config.systemctl_binary, "stop", config.previous_backend_service), timeout=60)
                previous_stopped = True
                database_evidence = consistent_sqlite_backup(config.source_database, runtime.database)
            else:
                database_evidence = online_sqlite_snapshot(config.source_database, runtime.database)
            if runtime.runtime_uid is None or runtime.runtime_gid is None:
                raise P7ExecutorError("p7_runtime_account_binding_missing")
            os.chown(runtime.database, runtime.runtime_uid, runtime.runtime_gid)
            os.chmod(runtime.database, 0o600)
            migration_evidence = migrate_hook(runtime, runner)

            # Mark the attempt before systemd is invoked: `enable --now` may
            # start one unit and still return a failure for the second one.
            # Rollback must therefore stop both exact candidate units even on
            # a partially successful command.
            candidate_start_attempted = True
            runner.run(
                (
                    config.systemctl_binary,
                    "enable",
                    "--now",
                    BACKEND_SERVICE,
                    FRONTEND_SERVICE,
                ),
                timeout=120,
            )
            _service_active(runner, config.systemctl_binary, BACKEND_SERVICE)
            _service_active(runner, config.systemctl_binary, FRONTEND_SERVICE)

            backend_origin = verified.manifest["targets"]["backend"]["origin"]
            frontend_origin = verified.manifest["targets"]["frontend"]["origin"]
            direct_gate = probe_release_identity(
                backend_origin,
                frontend_origin,
                release_id,
                frontend_path=frontend_base_path,
                client_factory=client_factory,
            )
            if activation_mode == "production":
                rollback_backend = verified.rollback_manifest["targets"]["backend"]["origin"]
                rollback_frontend = verified.rollback_manifest["targets"]["frontend"]["origin"]
                candidate_site = render_paired_site(
                    active_bytes,
                    release_id=release_id,
                    candidate_backend=backend_origin,
                    candidate_frontend=frontend_origin,
                    rollback_backend=rollback_backend,
                    rollback_frontend=rollback_frontend,
                )
            else:
                candidate_site = render_canary_site(
                    active_bytes,
                    release_id=release_id,
                    candidate_backend=backend_origin,
                    candidate_frontend=frontend_origin,
                )
            isolated_nginx_test(
                candidate_site,
                active_site=config.active_site,
                nginx_main=config.nginx_main,
                sites_enabled_dir=config.sites_enabled_dir,
                nginx_binary=config.nginx_binary,
                runner=runner,
            )
            # Final TOCTOU guard immediately before the only production route
            # mutation.
            if sha256_file(config.active_site) != expected_previous_sha:
                raise P7ExecutorError("p7_active_site_changed_before_switch")
            atomic_write(
                config.active_site,
                candidate_site,
                mode=stat.S_IMODE(active_metadata.st_mode),
                reference=active_metadata,
            )
            site_replaced = True
            runner.run((config.nginx_binary, "-t"), timeout=30)
            reload_attempted = True
            runner.run((config.systemctl_binary, "reload", "nginx"), timeout=30)
            public_gate = public_post_gates(
                config.public_base_url,
                release_id,
                base_path=frontend_base_path,
                client_factory=client_factory,
            )
            production_regression_gate: dict[str, Any] | None = None
            if activation_mode == "canary":
                production_regression_gate = probe_rollback_identity(
                    config.public_base_url,
                    str(verified.rollback_manifest["release_id"]),
                    client_factory=client_factory,
                )
            audit = {
                "schema_version": EXECUTOR_SCHEMA_VERSION,
                "status": "canary_applied_verified" if activation_mode == "canary" else "applied_verified",
                "activation_mode": activation_mode,
                "production_applied": activation_mode == "production",
                "release_id": release_id,
                "manifest_sha256": verified.plan["manifest_sha256"],
                "source_commit": verified.plan["source_commit"],
                "previous_release_id": verified.rollback_manifest["release_id"],
                "previous_site_sha256": expected_previous_sha,
                "active_site_sha256": sha256_file(config.active_site),
                "input_digests": snapshot.digests,
                "database_backup": database_evidence,
                "migration": migration_evidence,
                "direct_gate": direct_gate,
                "public_post_gates": public_gate,
                "nginx_reload_count": 1,
                "rollback_ready": True,
            }
            if production_regression_gate is not None:
                audit["production_regression_gate"] = production_regression_gate
            if canary_path is not None:
                audit["canary_base_path"] = canary_path
            _write_audit(execution_dir / "result.json", audit)
            return audit
        except Exception as original:
            original_code = original.code if isinstance(original, P7ExecutorError) else "p7_executor_unexpected_failure"
            rollback_errors: list[str] = []
            site_restore_ready = False
            if site_replaced:
                try:
                    atomic_write(
                        config.active_site,
                        active_bytes,
                        mode=stat.S_IMODE(active_metadata.st_mode),
                        reference=active_metadata,
                    )
                    if config.active_site.read_bytes() != active_bytes or sha256_file(config.active_site) != expected_previous_sha:
                        raise P7ExecutorError("p7_rollback_site_bytes_mismatch")
                    runner.run((config.nginx_binary, "-t"), timeout=30)
                    site_restore_ready = True
                except Exception:
                    rollback_errors.append("site_restore_failed")
            # Restore the old writer before reloading nginx to the old route.
            # The candidate remains available until that hand-back completes,
            # avoiding a route that points at an intentionally stopped unit.
            if previous_stopped:
                try:
                    runner.run((config.systemctl_binary, "start", config.previous_backend_service), timeout=60)
                    _service_active(runner, config.systemctl_binary, config.previous_backend_service)
                except Exception:
                    rollback_errors.append("previous_backend_restart_failed")
            if site_restore_ready and reload_attempted:
                try:
                    runner.run((config.systemctl_binary, "reload", "nginx"), timeout=30)
                except Exception:
                    rollback_errors.append("site_reload_failed")
            if candidate_start_attempted:
                try:
                    runner.run(
                        (
                            config.systemctl_binary,
                            "disable",
                            "--now",
                            FRONTEND_SERVICE,
                            BACKEND_SERVICE,
                        ),
                        timeout=120,
                    )
                except Exception:
                    rollback_errors.append("candidate_stop_failed")
            if unit_backups:
                try:
                    restore_runtime_units(unit_backups)
                    runner.run((config.systemctl_binary, "daemon-reload"), timeout=30)
                except Exception:
                    rollback_errors.append("unit_restore_failed")
            live_mutation_attempted = previous_stopped or candidate_start_attempted or site_replaced
            if live_mutation_attempted and not rollback_errors:
                try:
                    probe_rollback_identity(
                        config.public_base_url,
                        str(verified.rollback_manifest["release_id"]),
                        client_factory=client_factory,
                    )
                except Exception:
                    rollback_errors.append("public_rollback_identity_failed")
            rollback_status = "rollback_failed" if rollback_errors else "rolled_back_verified"
            if activation_mode == "canary":
                rollback_status = "canary_rollback_failed" if rollback_errors else "canary_rolled_back_verified"
            failure_audit = {
                "schema_version": EXECUTOR_SCHEMA_VERSION,
                "status": rollback_status,
                "activation_mode": activation_mode,
                "production_applied": False,
                "release_id": release_id,
                "previous_release_id": verified.rollback_manifest["release_id"],
                "failure_code": original_code,
                "rollback_errors": rollback_errors,
                "previous_site_sha256": expected_previous_sha,
                "restored_site_sha256": sha256_file(config.active_site) if config.active_site.is_file() else None,
                "input_digests": snapshot.digests,
            }
            if canary_path is not None:
                failure_audit["canary_base_path"] = canary_path
            with contextlib.suppress(Exception):
                _write_audit(execution_dir / "result.json", failure_audit)
            if rollback_errors:
                raise P7ExecutorError("p7_automatic_rollback_failed") from original
            raise P7ExecutorError(original_code) from original
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        os.close(lock_descriptor)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--release-dir", required=True)
    parser.add_argument("--release-signature", required=True)
    parser.add_argument("--rollback-release-dir", required=True)
    parser.add_argument("--rollback-signature", required=True)
    parser.add_argument("--gate-evidence", required=True)
    parser.add_argument("--gate-evidence-signature", required=True)
    parser.add_argument("--rollback-health-evidence", required=True)
    parser.add_argument("--rollback-health-signature", required=True)
    parser.add_argument("--owner-approval", required=True)
    parser.add_argument("--owner-approval-signature", required=True)
    parser.add_argument("--active-site", default="/etc/nginx/sites-available/kolibriai.ru")
    parser.add_argument("--nginx-main", default="/etc/nginx/nginx.conf")
    parser.add_argument("--sites-enabled-dir", default="/etc/nginx/sites-enabled")
    parser.add_argument("--source-database", default="/var/lib/kolibri/backend-r9/kolibri.db")
    parser.add_argument("--previous-backend-service", required=True)
    parser.add_argument("--runtime-secret-file", default="/etc/kolibri/backend.env")
    parser.add_argument("--release-root", default="/opt/kolibri-ai/releases")
    parser.add_argument("--data-root", default="/var/lib/kolibri/releases")
    parser.add_argument("--backup-root", default="/var/lib/kolibri/release-backups/p7")
    parser.add_argument("--state-root", default="/var/lib/kolibri/release-evidence/p7")
    parser.add_argument("--systemd-dir", default="/etc/systemd/system")
    parser.add_argument("--lock-path", default="/run/lock/kolibri-p7-executor.lock")
    parser.add_argument("--public-base-url", default="https://kolibriai.ru")
    parser.add_argument("--frontend-base-path", default="/")
    parser.add_argument("--python-binary", default="/usr/bin/python3")
    parser.add_argument("--nginx-binary", default="/usr/sbin/nginx")
    parser.add_argument("--systemctl-binary", default="/usr/bin/systemctl")
    parser.add_argument("--runtime-user", default="ladik")
    parser.add_argument("--runtime-group", default="ladik")
    return parser


def config_from_args(args: argparse.Namespace) -> ExecutorConfig:
    inputs = SignedInputs(
        plan=Path(args.plan),
        release_dir=Path(args.release_dir),
        release_signature=Path(args.release_signature),
        rollback_release_dir=Path(args.rollback_release_dir),
        rollback_signature=Path(args.rollback_signature),
        gate_evidence=Path(args.gate_evidence),
        gate_evidence_signature=Path(args.gate_evidence_signature),
        rollback_health_evidence=Path(args.rollback_health_evidence),
        rollback_health_signature=Path(args.rollback_health_signature),
        owner_approval=Path(args.owner_approval),
        owner_approval_signature=Path(args.owner_approval_signature),
    )
    return ExecutorConfig(
        inputs=inputs,
        active_site=Path(args.active_site),
        nginx_main=Path(args.nginx_main),
        sites_enabled_dir=Path(args.sites_enabled_dir),
        source_database=Path(args.source_database),
        previous_backend_service=args.previous_backend_service,
        runtime_secret_file=Path(args.runtime_secret_file),
        release_root=Path(args.release_root),
        data_root=Path(args.data_root),
        backup_root=Path(args.backup_root),
        state_root=Path(args.state_root),
        systemd_dir=Path(args.systemd_dir),
        lock_path=Path(args.lock_path),
        public_base_url=args.public_base_url,
        frontend_base_path=args.frontend_base_path,
        python_binary=args.python_binary,
        nginx_binary=args.nginx_binary,
        systemctl_binary=args.systemctl_binary,
        runtime_user=args.runtime_user,
        runtime_group=args.runtime_group,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = execute(config_from_args(args))
    except P7ExecutorError as exc:
        print(json.dumps({"status": "failed", "reason": exc.code}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    os.umask(0o027)
    raise SystemExit(main())
