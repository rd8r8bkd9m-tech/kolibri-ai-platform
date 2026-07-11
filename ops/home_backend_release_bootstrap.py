#!/usr/bin/env python3
"""One-time, reversible Home backend release drop-in bootstrap.

The program is streamed to the manifest-selected Home host for read-only
planning, then copied there only when the owner explicitly requests
``--apply``.  It never changes the release ``current`` link and never reads or
prints service environment files, provider credentials, or secret material.
"""

from __future__ import annotations

import argparse
import fcntl
import grp
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


SCHEMA_VERSION = "kolibri.home-backend-release-bootstrap.v1"
SERVICE = "kolibri-backend.service"
CURRENT = "/opt/kolibri-ai/current"
RELEASES = "/opt/kolibri-ai/releases"
BACKEND_WORKING_DIRECTORY = f"{CURRENT}/backend"
FRONTEND_DIST = f"{CURRENT}/frontend/dist"
DROPIN_DIRECTORY = "/etc/systemd/system/kolibri-backend.service.d"
DROPIN_PATH = f"{DROPIN_DIRECTORY}/10-release.conf"
BACKUP_BASE = "/var/backups/kolibri/backend-release-dropin"
VENV_PYTHON = "/srv/kolibri/repo/.venv/bin/python"
VENV_UVICORN = "/srv/kolibri/repo/.venv/bin/uvicorn"
SYSTEMCTL = "/usr/bin/systemctl"
CURL = "/usr/bin/curl"
HEALTH_URL = "http://127.0.0.1:8001/api/health"
LOCK_PATH = "/run/lock/kolibri-home-backend-release-bootstrap.lock"
OWNER_TOKEN_FILE = "/etc/kolibri/owner-api-token"
OWNER_TOKEN_GROUP = "kolibri-agent"
OWNER_TOKEN_MODE = 0o640
MAX_OWNER_TOKEN_BYTES = 4 * 1024
SAFE_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}")
MAX_FILE_BYTES = 256 * 1024
MAX_COMMAND_OUTPUT = 256 * 1024
HEALTH_ATTEMPTS = 6
HEALTH_RETRY_DELAY_SECONDS = 0.5

CANONICAL_DROPIN = """[Service]
SupplementaryGroups=kolibri-agent
WorkingDirectory=/opt/kolibri-ai/current/backend
ExecStart=
ExecStart=/srv/kolibri/repo/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8001
Environment=KOLIBRI_ENV=production
Environment=KOLIBRI_FACTORY_CONTROL_URL=http://127.0.0.1:9101
Environment=KOLIBRI_FRONTEND_DIST=/opt/kolibri-ai/current/frontend/dist
Environment=KOLIBRI_OWNER_API_TOKEN_FILE=/etc/kolibri/owner-api-token
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONPATH=/opt/kolibri-ai/current/backend:/opt/kolibri-ai/current
""".encode("utf-8")


class BackendBootstrapError(RuntimeError):
    """Sanitized error suitable for the operator-facing JSON envelope."""

    def __init__(self, code: str, *, rollback: str | None = None):
        super().__init__(code)
        self.code = code
        self.rollback = rollback


class CommandRunner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout: int = 30,
    ) -> subprocess.CompletedProcess[str]: ...


class SubprocessCommandRunner:
    """Run fixed argv while keeping all command output private."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout: int = 30,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [str(item) for item in argv],
                check=False,
                capture_output=True,
                text=True,
                cwd=cwd,
                env=dict(env) if env is not None else None,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise BackendBootstrapError("backend_bootstrap_command_unavailable") from exc


@dataclass(frozen=True)
class CurrentRelease:
    link_text: str
    resolved: Path
    backend: Path
    frontend_dist: Path
    release_id: str


@dataclass(frozen=True)
class DropinRecord:
    existed: bool
    directory_existed: bool
    mode: int | None = None
    uid: int | None = None
    gid: int | None = None
    digest: str | None = None


@dataclass(frozen=True)
class PreflightState:
    current: CurrentRelease
    dropin: DropinRecord
    unit_metadata: dict[str, str]
    unit_metadata_raw: str
    effective_release_layout: bool
    effective_dropin_count: int


def _rooted(root: Path, logical: str | Path) -> Path:
    path = Path(logical)
    if not path.is_absolute():
        raise BackendBootstrapError("backend_bootstrap_path_invalid")
    return root / path.relative_to("/")


def _owner_uid(root: Path) -> int:
    return 0 if root == Path("/") else os.geteuid()


def _owner_gid(root: Path) -> int:
    return 0 if root == Path("/") else os.getegid()


def _read_regular(path: Path, *, code: str, max_bytes: int = MAX_FILE_BYTES) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or before.st_size <= 0
                or before.st_size > max_bytes
            ):
                raise BackendBootstrapError(code)
            payload = handle.read(max_bytes + 1)
            after = os.fstat(handle.fileno())
        if (
            len(payload) > max_bytes
            or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise BackendBootstrapError(code)
        return payload
    except BackendBootstrapError:
        raise
    except OSError as exc:
        raise BackendBootstrapError(code) from exc


def _digest(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _require_safe_directory(path: Path, *, root: Path, code: str) -> None:
    try:
        value = path.lstat()
    except OSError as exc:
        raise BackendBootstrapError(code) from exc
    if not stat.S_ISDIR(value.st_mode):
        raise BackendBootstrapError(code)
    if root == Path("/") and value.st_uid != 0:
        raise BackendBootstrapError(code)
    if stat.S_IMODE(value.st_mode) & 0o022:
        raise BackendBootstrapError(code)


def _require_executable(path: Path, *, code: str) -> None:
    try:
        resolved = path.resolve(strict=True)
        value = resolved.stat()
    except OSError as exc:
        raise BackendBootstrapError(code) from exc
    if not stat.S_ISREG(value.st_mode) or not os.access(resolved, os.X_OK):
        raise BackendBootstrapError(code)


def _run_checked(
    runner: CommandRunner,
    argv: Sequence[str],
    *,
    code: str,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = runner.run(argv, cwd=cwd, env=env, timeout=timeout)
    except BackendBootstrapError:
        raise
    except Exception as exc:  # pragma: no cover - defensive adapter boundary
        raise BackendBootstrapError(code) from exc
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if (
        completed.returncode != 0
        or len(stdout.encode("utf-8", errors="ignore")) > MAX_COMMAND_OUTPUT
        or len(stderr.encode("utf-8", errors="ignore")) > MAX_COMMAND_OUTPUT
    ):
        raise BackendBootstrapError(code)
    return completed


def _validate_current(root: Path) -> CurrentRelease:
    releases = _rooted(root, RELEASES)
    current = _rooted(root, CURRENT)
    _require_safe_directory(releases, root=root, code="release_releases_root_unsafe")
    try:
        current_value = current.lstat()
        link_text = os.readlink(current)
        resolved_releases = releases.resolve(strict=True)
        resolved = current.resolve(strict=True)
    except OSError as exc:
        raise BackendBootstrapError("release_current_link_unsafe") from exc
    if (
        not stat.S_ISLNK(current_value.st_mode)
        or resolved.parent != resolved_releases
        or not resolved.is_dir()
    ):
        raise BackendBootstrapError("release_current_not_direct_release_child")
    release_value = resolved.lstat()
    if (
        not stat.S_ISDIR(release_value.st_mode)
        or (root == Path("/") and release_value.st_uid != 0)
        or stat.S_IMODE(release_value.st_mode) & 0o022
    ):
        raise BackendBootstrapError("release_current_target_unsafe")
    backend_resolved = resolved / "backend"
    frontend_resolved = resolved / "frontend"
    frontend_dist_resolved = frontend_resolved / "dist"
    for path, code in (
        (backend_resolved, "release_current_backend_missing"),
        (frontend_resolved, "release_current_frontend_missing"),
        (frontend_dist_resolved, "release_current_frontend_dist_missing"),
    ):
        try:
            value = path.lstat()
        except OSError as exc:
            raise BackendBootstrapError(code) from exc
        if (
            not stat.S_ISDIR(value.st_mode)
            or (root == Path("/") and value.st_uid != 0)
            or stat.S_IMODE(value.st_mode) & 0o022
        ):
            raise BackendBootstrapError(code)
    backend = current / "backend"
    frontend_dist = current / "frontend" / "dist"
    if not backend.is_dir():
        raise BackendBootstrapError("release_current_backend_missing")
    if not frontend_dist.is_dir():
        raise BackendBootstrapError("release_current_frontend_dist_missing")
    return CurrentRelease(
        link_text=link_text,
        resolved=resolved,
        backend=backend,
        frontend_dist=frontend_dist,
        release_id=resolved.name,
    )


def _dropin_record(root: Path) -> DropinRecord:
    directory = _rooted(root, DROPIN_DIRECTORY)
    path = _rooted(root, DROPIN_PATH)
    directory_existed = os.path.lexists(directory)
    if directory_existed:
        _require_safe_directory(
            directory,
            root=root,
            code="backend_dropin_directory_unsafe",
        )
    if not os.path.lexists(path):
        return DropinRecord(existed=False, directory_existed=directory_existed)
    try:
        value = path.lstat()
    except OSError as exc:
        raise BackendBootstrapError("backend_dropin_path_unsafe") from exc
    if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
        raise BackendBootstrapError("backend_dropin_path_unsafe")
    payload = _read_regular(path, code="backend_dropin_path_unsafe")
    return DropinRecord(
        existed=True,
        directory_existed=directory_existed,
        mode=stat.S_IMODE(value.st_mode),
        uid=value.st_uid,
        gid=value.st_gid,
        digest=_digest(payload),
    )


def _unit_metadata(runner: CommandRunner) -> tuple[dict[str, str], str]:
    properties = (
        "LoadState",
        "ActiveState",
        "SubState",
        "UnitFileState",
        "FragmentPath",
        "DropInPaths",
        "WorkingDirectory",
        "MainPID",
    )
    argv = [SYSTEMCTL, "show", SERVICE]
    argv.extend(f"--property={item}" for item in properties)
    completed = _run_checked(
        runner,
        argv,
        code="backend_unit_metadata_unavailable",
        timeout=15,
    )
    raw = completed.stdout or ""
    metadata: dict[str, str] = {}
    for line in raw.splitlines():
        name, separator, value = line.partition("=")
        if separator and name in properties:
            metadata[name] = value
    if metadata.get("LoadState") != "loaded" or metadata.get("ActiveState") != "active":
        raise BackendBootstrapError("backend_unit_not_active")
    if not metadata.get("FragmentPath", "").startswith("/"):
        raise BackendBootstrapError("backend_unit_fragment_unavailable")
    return metadata, raw


def _validate_backend_import(root: Path, runner: CommandRunner, current: CurrentRelease) -> None:
    python = _rooted(root, VENV_PYTHON)
    uvicorn = _rooted(root, VENV_UVICORN)
    _require_executable(python, code="backend_existing_venv_python_unavailable")
    _require_executable(uvicorn, code="backend_existing_venv_uvicorn_unavailable")
    environment = {
        "HOME": "/nonexistent",
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": f"{current.backend}:{current.backend.parent}",
        "KOLIBRI_ENV": "production",
        "KOLIBRI_FACTORY_CONTROL_URL": "http://127.0.0.1:9101",
        "KOLIBRI_FRONTEND_DIST": str(current.frontend_dist),
        "KOLIBRI_OWNER_API_TOKEN_FILE": "/etc/kolibri/owner-api-token",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    _run_checked(
        runner,
        [
            str(python),
            "-B",
            "-c",
            "import main; assert getattr(main, 'app', None) is not None",
        ],
        cwd=str(current.backend),
        env=environment,
        timeout=45,
        code="backend_current_import_probe_failed",
    )


def _validate_owner_token_file(root: Path) -> None:
    path = _rooted(root, OWNER_TOKEN_FILE)
    try:
        value = path.lstat()
    except FileNotFoundError as exc:
        raise BackendBootstrapError("backend_owner_token_file_missing") from exc
    except OSError as exc:
        raise BackendBootstrapError("backend_owner_token_file_unavailable") from exc
    if root == Path("/"):
        try:
            expected_gid = grp.getgrnam(OWNER_TOKEN_GROUP).gr_gid
        except KeyError as exc:
            raise BackendBootstrapError("backend_owner_token_group_missing") from exc
        expected_uid = 0
    else:
        expected_uid = os.geteuid()
        expected_gid = os.getegid()
    if (
        not stat.S_ISREG(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or value.st_nlink != 1
        or value.st_uid != expected_uid
        or value.st_gid != expected_gid
        or stat.S_IMODE(value.st_mode) != OWNER_TOKEN_MODE
        or not 1 <= value.st_size <= MAX_OWNER_TOKEN_BYTES
    ):
        raise BackendBootstrapError("backend_owner_token_file_permissions_invalid")


def _validate_backup_boundary(root: Path) -> None:
    backups = _rooted(root, "/var/backups")
    _require_safe_directory(backups, root=root, code="backend_backup_root_unsafe")
    cursor = backups
    for component in ("kolibri", "backend-release-dropin"):
        cursor /= component
        if os.path.lexists(cursor):
            _require_safe_directory(cursor, root=root, code="backend_backup_root_unsafe")


def preflight(
    *,
    root: Path = Path("/"),
    runner: CommandRunner | None = None,
) -> PreflightState:
    runner = runner or SubprocessCommandRunner()
    for logical, code in (
        (SYSTEMCTL, "backend_systemctl_unavailable"),
        (CURL, "backend_curl_unavailable"),
    ):
        _require_executable(_rooted(root, logical), code=code)
    _require_safe_directory(
        _rooted(root, "/etc/systemd/system"),
        root=root,
        code="backend_systemd_directory_unsafe",
    )
    current = _validate_current(root)
    _validate_owner_token_file(root)
    dropin = _dropin_record(root)
    _validate_backup_boundary(root)
    metadata, raw = _unit_metadata(runner)
    _validate_backend_import(root, runner, current)
    _health_gate(runner)
    environment = _systemd_value(
        runner,
        "Environment",
        code="backend_effective_environment_unavailable",
    )
    try:
        environment_tokens = shlex.split(environment)
        dropin_tokens = shlex.split(metadata.get("DropInPaths", ""))
    except ValueError as exc:
        raise BackendBootstrapError("backend_effective_unit_metadata_invalid") from exc
    expected_frontend = f"KOLIBRI_FRONTEND_DIST={FRONTEND_DIST}"
    expected_owner_token_file = "KOLIBRI_OWNER_API_TOKEN_FILE=/etc/kolibri/owner-api-token"
    expected_no_bytecode = "PYTHONDONTWRITEBYTECODE=1"
    effective_release_layout = (
        metadata.get("WorkingDirectory") == BACKEND_WORKING_DIRECTORY
        and expected_frontend in environment_tokens
        and expected_owner_token_file in environment_tokens
        and expected_no_bytecode in environment_tokens
        and bool(dropin_tokens)
        and all(value.startswith("/") for value in dropin_tokens)
    )
    return PreflightState(
        current=current,
        dropin=dropin,
        unit_metadata=metadata,
        unit_metadata_raw=raw,
        effective_release_layout=effective_release_layout,
        effective_dropin_count=len(dropin_tokens),
    )


def _mkdir_secure(path: Path, *, root: Path, mode: int) -> None:
    if os.path.lexists(path):
        _require_safe_directory(path, root=root, code="backend_bootstrap_directory_unsafe")
        return
    try:
        path.mkdir(mode=mode)
        os.chmod(path, mode)
        if root == Path("/"):
            os.chown(path, 0, 0)
    except OSError as exc:
        raise BackendBootstrapError("backend_bootstrap_directory_create_failed") from exc


def _prepare_backup_directory(root: Path, run_id: str) -> Path:
    cursor = _rooted(root, "/var/backups")
    for component in ("kolibri", "backend-release-dropin"):
        cursor /= component
        _mkdir_secure(cursor, root=root, mode=0o700)
    backup = cursor / run_id
    if os.path.lexists(backup):
        raise BackendBootstrapError("backend_backup_run_exists")
    _mkdir_secure(backup, root=root, mode=0o700)
    return backup


def _atomic_write(
    path: Path,
    payload: bytes,
    *,
    root: Path,
    mode: int,
    uid: int | None = None,
    gid: int | None = None,
) -> None:
    descriptor: int | None = None
    temporary = ""
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.chown(
            temporary,
            _owner_uid(root) if uid is None else uid,
            _owner_gid(root) if gid is None else gid,
        )
        os.replace(temporary, path)
        temporary = ""
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise BackendBootstrapError("backend_bootstrap_atomic_write_failed") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _write_json(path: Path, payload: dict[str, Any], *, root: Path) -> None:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    _atomic_write(path, serialized, root=root, mode=0o600)


def _snapshot(root: Path, run_id: str, state: PreflightState) -> Path:
    backup = _prepare_backup_directory(root, run_id)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "service": SERVICE,
        "current_link_text": state.current.link_text,
        "current_release_digest": _digest(str(state.current.resolved).encode("utf-8")),
        "dropin": {
            "existed": state.dropin.existed,
            "directory_existed": state.dropin.directory_existed,
            "mode": state.dropin.mode,
            "uid": state.dropin.uid,
            "gid": state.dropin.gid,
            "digest": state.dropin.digest,
        },
        "unit": state.unit_metadata,
    }
    _write_json(backup / "metadata.json", metadata, root=root)
    _atomic_write(
        backup / "unit.before",
        state.unit_metadata_raw.encode("utf-8"),
        root=root,
        mode=0o600,
    )
    if state.dropin.existed:
        original = _read_regular(
            _rooted(root, DROPIN_PATH),
            code="backend_dropin_backup_failed",
        )
        _atomic_write(backup / "dropin.before", original, root=root, mode=0o600)
    _atomic_write(backup / "status", b"prepared\n", root=root, mode=0o600)
    return backup


def _validate_source(path: Path) -> bytes:
    payload = _read_regular(path, code="backend_dropin_source_invalid")
    if payload != CANONICAL_DROPIN:
        raise BackendBootstrapError("backend_dropin_source_contract_mismatch")
    return payload


def _install_dropin(root: Path, payload: bytes) -> None:
    directory = _rooted(root, DROPIN_DIRECTORY)
    _mkdir_secure(directory, root=root, mode=0o755)
    destination = _rooted(root, DROPIN_PATH)
    if os.path.lexists(destination):
        try:
            value = destination.lstat()
        except OSError as exc:
            raise BackendBootstrapError("backend_dropin_path_unsafe") from exc
        if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
            raise BackendBootstrapError("backend_dropin_path_unsafe")
    _atomic_write(destination, payload, root=root, mode=0o644)


def _assert_current_unchanged(root: Path, before: CurrentRelease) -> None:
    after = _validate_current(root)
    if after.link_text != before.link_text or after.resolved != before.resolved:
        raise BackendBootstrapError("release_current_changed_during_backend_bootstrap")


def _health_gate(runner: CommandRunner) -> None:
    last_code = "backend_health_gate_failed"
    for attempt in range(HEALTH_ATTEMPTS):
        try:
            completed = runner.run(
                [
                    CURL,
                    "--fail",
                    "--silent",
                    "--show-error",
                    "--max-time",
                    "2",
                    HEALTH_URL,
                ],
                timeout=4,
            )
        except Exception:
            completed = None
        if completed is not None:
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            bounded = (
                len(stdout.encode("utf-8", errors="ignore")) <= MAX_COMMAND_OUTPUT
                and len(stderr.encode("utf-8", errors="ignore")) <= MAX_COMMAND_OUTPUT
            )
            if completed.returncode == 0 and bounded:
                try:
                    payload = json.loads(stdout)
                except json.JSONDecodeError:
                    last_code = "backend_health_payload_invalid"
                else:
                    if isinstance(payload, dict):
                        return
                    last_code = "backend_health_payload_invalid"
        if attempt + 1 < HEALTH_ATTEMPTS:
            time.sleep(HEALTH_RETRY_DELAY_SECONDS)
    raise BackendBootstrapError(last_code)


def _systemd_value(runner: CommandRunner, property_name: str, *, code: str) -> str:
    completed = _run_checked(
        runner,
        [SYSTEMCTL, "show", SERVICE, f"--property={property_name}", "--value"],
        timeout=15,
        code=code,
    )
    return (completed.stdout or "").strip()


def _verify_activated(root: Path, runner: CommandRunner, current: CurrentRelease) -> None:
    _assert_current_unchanged(root, current)
    _run_checked(
        runner,
        [SYSTEMCTL, "is-active", "--quiet", SERVICE],
        timeout=15,
        code="backend_not_active_after_restart",
    )
    working_directory = _systemd_value(
        runner,
        "WorkingDirectory",
        code="backend_working_directory_unavailable",
    )
    if working_directory != BACKEND_WORKING_DIRECTORY:
        raise BackendBootstrapError("backend_working_directory_not_current")
    dropins = _systemd_value(
        runner,
        "DropInPaths",
        code="backend_dropin_paths_unavailable",
    )
    if DROPIN_PATH not in shlex.split(dropins):
        raise BackendBootstrapError("backend_release_dropin_not_effective")
    environment = _systemd_value(
        runner,
        "Environment",
        code="backend_effective_environment_unavailable",
    )
    try:
        environment_tokens = shlex.split(environment)
    except ValueError as exc:
        raise BackendBootstrapError("backend_effective_environment_invalid") from exc
    expected = f"KOLIBRI_FRONTEND_DIST={FRONTEND_DIST}"
    if expected not in environment_tokens:
        raise BackendBootstrapError("backend_frontend_dist_not_current")
    if "KOLIBRI_OWNER_API_TOKEN_FILE=/etc/kolibri/owner-api-token" not in environment_tokens:
        raise BackendBootstrapError("backend_owner_token_file_not_configured")
    if "PYTHONDONTWRITEBYTECODE=1" not in environment_tokens:
        raise BackendBootstrapError("backend_bytecode_write_fence_not_configured")
    _health_gate(runner)


def _activate(runner: CommandRunner) -> None:
    _run_checked(
        runner,
        [SYSTEMCTL, "daemon-reload"],
        timeout=30,
        code="backend_daemon_reload_failed",
    )
    _run_checked(
        runner,
        [SYSTEMCTL, "restart", SERVICE],
        timeout=60,
        code="backend_restart_failed",
    )


def _rollback(
    *,
    root: Path,
    runner: CommandRunner,
    state: PreflightState,
    backup: Path,
) -> None:
    destination = _rooted(root, DROPIN_PATH)
    if state.dropin.existed:
        payload = _read_regular(backup / "dropin.before", code="backend_rollback_backup_invalid")
        _atomic_write(
            destination,
            payload,
            root=root,
            mode=state.dropin.mode or 0o644,
            uid=state.dropin.uid,
            gid=state.dropin.gid,
        )
    elif os.path.lexists(destination):
        try:
            value = destination.lstat()
            if not stat.S_ISREG(value.st_mode):
                raise BackendBootstrapError("backend_rollback_destination_unsafe")
            destination.unlink()
        except BackendBootstrapError:
            raise
        except OSError as exc:
            raise BackendBootstrapError("backend_rollback_remove_failed") from exc
    directory = _rooted(root, DROPIN_DIRECTORY)
    if not state.dropin.directory_existed and directory.is_dir():
        try:
            directory.rmdir()
        except OSError:
            pass
    _activate(runner)
    _assert_current_unchanged(root, state.current)
    _run_checked(
        runner,
        [SYSTEMCTL, "is-active", "--quiet", SERVICE],
        timeout=15,
        code="backend_rollback_service_not_active",
    )
    _health_gate(runner)
    _atomic_write(backup / "status", b"rolled_back\n", root=root, mode=0o600)


def plan(
    *,
    root: Path = Path("/"),
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    state = preflight(root=root, runner=runner)
    existing = "absent"
    if state.dropin.existed:
        existing = "matching" if state.dropin.digest == _digest(CANONICAL_DROPIN) else "different"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "already_configured" if state.effective_release_layout else "planned"
        ),
        "mode": "dry-run",
        "target_node": "home",
        "service": SERVICE,
        "current_release": state.current.release_id,
        "current_link": "contained_direct_release_child",
        "backend_import": "verified_existing_venv",
        "owner_token_file": "metadata_verified_without_secret_read",
        "health_baseline": "passed",
        "dropin": (
            "effective_existing" if state.effective_release_layout else existing
        ),
        "effective_dropin_count": state.effective_dropin_count,
        "mutation": "none",
    }


def apply(
    source_dropin: Path,
    run_id: str,
    *,
    root: Path = Path("/"),
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    if not SAFE_RUN_ID.fullmatch(run_id):
        raise BackendBootstrapError("backend_bootstrap_run_id_invalid")
    runner = runner or SubprocessCommandRunner()
    payload = _validate_source(source_dropin)
    state = preflight(root=root, runner=runner)
    if state.effective_release_layout:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "already_configured",
            "mode": "apply",
            "target_node": "home",
            "service": SERVICE,
            "current_release": state.current.release_id,
            "current_link": "unchanged",
            "restart_performed": False,
            "effective_dropin_count": state.effective_dropin_count,
        }
    backup = _snapshot(root, run_id, state)
    try:
        _install_dropin(root, payload)
        _activate(runner)
        _verify_activated(root, runner, state.current)
        _atomic_write(backup / "status", b"applied\n", root=root, mode=0o600)
    except BackendBootstrapError as exc:
        try:
            _rollback(root=root, runner=runner, state=state, backup=backup)
        except BackendBootstrapError as rollback_exc:
            raise BackendBootstrapError(exc.code, rollback=rollback_exc.code) from exc
        raise BackendBootstrapError(exc.code, rollback="complete") from exc
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "applied",
        "mode": "apply",
        "target_node": "home",
        "service": SERVICE,
        "current_release": state.current.release_id,
        "current_link": "unchanged",
        "dropin_digest": _digest(payload),
        "backup": str(backup),
        "restart_performed": True,
        "health_gate": "passed",
        "working_directory": BACKEND_WORKING_DIRECTORY,
        "frontend_dist": FRONTEND_DIST,
    }


def _apply_lock() -> Any:
    try:
        lock_parent = Path(LOCK_PATH).parent
        value = lock_parent.lstat()
        if (
            not stat.S_ISDIR(value.st_mode)
            or value.st_uid != 0
            or stat.S_IMODE(value.st_mode) != 0o1777
        ):
            raise BackendBootstrapError("backend_bootstrap_lock_parent_unsafe")
        descriptor = os.open(
            LOCK_PATH,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        handle = os.fdopen(descriptor, "w", encoding="utf-8")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except BackendBootstrapError:
        raise
    except OSError as exc:
        raise BackendBootstrapError("backend_bootstrap_lock_unavailable") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--source-dropin")
    parser.add_argument("--run-id", default="home-backend-release-bootstrap")
    args = parser.parse_args(argv)
    lock = None
    try:
        if args.apply:
            if os.geteuid() != 0:
                raise BackendBootstrapError("backend_bootstrap_requires_root")
            if not args.source_dropin:
                raise BackendBootstrapError("backend_dropin_source_required")
            lock = _apply_lock()
            result = apply(Path(args.source_dropin), args.run_id)
        else:
            result = plan()
    except BackendBootstrapError as exc:
        result = {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "error_code": exc.code,
        }
        if exc.rollback is not None:
            result["rollback"] = exc.rollback
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 1
    except Exception:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "failed",
                    "error_code": "backend_bootstrap_internal_error",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1
    finally:
        if lock is not None:
            lock.close()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
