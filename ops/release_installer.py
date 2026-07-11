#!/usr/bin/env python3
"""Fail-closed immutable release installer used by the persistent Agent Host.

The Control Plane may authorize and route a release, but the worker repeats
every trust decision locally: source boundary, bundle limits, tar safety,
manifest digest, detached sshsig, file hashes/sizes/modes, local service
policy, health gates, atomic activation, and rollback.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import signal
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Callable, Iterable

try:
    from ops.release_authority import (
        OWNER_APPROVAL_NAMESPACE,
        ReleaseAuthorityError,
        approval_attestation_digest,
        canonical_owner_approval_attestation,
        canonical_owner_approval_bytes,
        validate_approval_for_task,
    )
except ImportError:  # installed standalone beside this module
    from release_authority import (
        OWNER_APPROVAL_NAMESPACE,
        ReleaseAuthorityError,
        approval_attestation_digest,
        canonical_owner_approval_attestation,
        canonical_owner_approval_bytes,
        validate_approval_for_task,
    )


RELEASE_SCHEMA = "kolibri.release.v1"
RELEASE_POLICY_SCHEMA = "kolibri.release-policy.v1"
RELEASE_SIGNATURE_NAMESPACE = "kolibri-release"
RELEASE_CAPABILITY = "release_apply_v1"
RELEASE_TASK_KINDS = frozenset({"release_bundle_apply", "release_bundle_rollback"})
AGENT_HOST_RUNTIME_PATH = "ops/agent_host.py"
MIMO_RESPONSE_AGENT_PROFILE_PATH = "ops/mimo/kolibri-response-only.md"
MANIFEST_MEMBER = ".kolibri-release/manifest.json"
SIGNATURE_MEMBER = ".kolibri-release/manifest.sig"
PAYLOAD_PREFIX = "payload/"
SAFE_RELEASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
SAFE_RECORD_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}")
SAFE_SERVICE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@:-]{0,127}\.service")
SAFE_CHECK_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
SAFE_FILE_MODES = frozenset({0o400, 0o440, 0o444, 0o500, 0o550, 0o555, 0o600, 0o640, 0o644, 0o700, 0o750, 0o755})
FORBIDDEN_TASK_COMMAND_KEYS = frozenset(
    {
        "command",
        "commands",
        "exec",
        "health_command",
        "health_commands",
        "post_health",
        "pre_health",
        "script",
        "service_command",
        "shell",
    }
)
FORBIDDEN_HEALTH_EXECUTABLES = frozenset(
    {"bash", "dash", "env", "fish", "sh", "sudo", "zsh"}
)
FORBIDDEN_RELEASE_SERVICES = frozenset({"kolibri-agent-host.service"})
HEALTH_RETRY_DELAY_SECONDS = 0.25
SECRET_METADATA_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "authorization",
        "cookie",
        "credential",
        "password",
        "private_key",
        "refresh_token",
        "secret",
        "secret_key",
        "token",
    }
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReleaseInstallError(RuntimeError):
    """A sanitized release failure safe to return to the Control Plane."""

    def __init__(
        self,
        code: str,
        *,
        retryable: bool = False,
        evidence: dict[str, Any] | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.evidence = dict(evidence or {})


@dataclass(frozen=True)
class ReleaseInstallerConfig:
    artifact_root: Path
    release_root: Path
    current_link: Path
    allowed_signers: Path
    policy_path: Path
    ssh_keygen: Path
    systemctl: Path
    owner_allowed_signers: Path
    max_bundle_bytes: int = 512 * 1024 * 1024
    max_unpacked_bytes: int = 2 * 1024 * 1024 * 1024
    max_members: int = 20_000
    download_timeout_seconds: int = 60
    lock_timeout_seconds: int = 300

    @classmethod
    def from_environment(cls, *, artifact_root: str | Path | None = None) -> "ReleaseInstallerConfig":
        configured_artifact_root = (
            os.environ.get("KOLIBRI_ARTIFACT_ROOT")
            or artifact_root
            or "/var/lib/kolibri-agent/artifacts"
        )
        try:
            discovered_ssh_keygen = shutil.which("ssh-keygen")
            discovered_systemctl = shutil.which("systemctl")
        except RecursionError:
            discovered_ssh_keygen = None
            discovered_systemctl = None
        ssh_keygen = os.environ.get("KOLIBRI_RELEASE_SSH_KEYGEN") or discovered_ssh_keygen or "/usr/bin/ssh-keygen"
        systemctl = os.environ.get("KOLIBRI_RELEASE_SYSTEMCTL") or discovered_systemctl or "/usr/bin/systemctl"
        return cls(
            artifact_root=Path(configured_artifact_root),
            release_root=Path(os.environ.get("KOLIBRI_RELEASE_ROOT", "/opt/kolibri-ai/releases")),
            current_link=Path(os.environ.get("KOLIBRI_RELEASE_CURRENT_LINK", "/opt/kolibri-ai/current")),
            allowed_signers=Path(
                os.environ.get("KOLIBRI_RELEASE_ALLOWED_SIGNERS", "/etc/kolibri/release_allowed_signers")
            ),
            policy_path=Path(os.environ.get("KOLIBRI_RELEASE_POLICY", "/etc/kolibri/release-policy.json")),
            ssh_keygen=Path(ssh_keygen),
            systemctl=Path(systemctl),
            owner_allowed_signers=Path(
                os.environ.get(
                    "KOLIBRI_OWNER_APPROVAL_ALLOWED_SIGNERS",
                    "/etc/kolibri/owner_allowed_signers",
                )
            ),
            max_bundle_bytes=_positive_env_int("KOLIBRI_RELEASE_MAX_BUNDLE_BYTES", 512 * 1024 * 1024),
            max_unpacked_bytes=_positive_env_int("KOLIBRI_RELEASE_MAX_UNPACKED_BYTES", 2 * 1024 * 1024 * 1024),
            max_members=_positive_env_int("KOLIBRI_RELEASE_MAX_MEMBERS", 20_000),
            download_timeout_seconds=_positive_env_int("KOLIBRI_RELEASE_DOWNLOAD_TIMEOUT", 60),
            lock_timeout_seconds=_positive_env_int("KOLIBRI_RELEASE_LOCK_TIMEOUT", 300),
        )


@dataclass(frozen=True)
class HealthCheck:
    name: str
    argv: tuple[str, ...]
    timeout_seconds: int


@dataclass(frozen=True)
class ReleasePolicy:
    services: frozenset[str]
    default_services: tuple[str, ...]
    required_payload_paths: tuple[str, ...]
    pre_health: tuple[HealthCheck, ...]
    pre_activate: tuple[HealthCheck, ...]
    post_health: tuple[HealthCheck, ...]
    service_timeout_seconds: int


@dataclass(frozen=True)
class ManifestFile:
    path: str
    sha256: str
    size_bytes: int
    mode: int


@dataclass(frozen=True)
class CanonicalManifest:
    payload: dict[str, Any]
    canonical_bytes: bytes
    digest: str
    release_id: str
    artifact_uri: str
    source_commit: str
    files: tuple[ManifestFile, ...]


@dataclass(frozen=True)
class ReleaseRequest:
    kind: str
    release_id: str
    manifest_digest: str
    artifact_uri: str
    source_commit: str
    signer_identity: str
    approval_id: str
    services: tuple[str, ...] | None


class ProgressReporter:
    """Throttle lease refreshes while keeping long local operations observable."""

    def __init__(self, callback: Callable[[], None] | None, *, interval_seconds: float = 5.0):
        self.callback = callback
        self.interval_seconds = interval_seconds
        self.last_reported = 0.0

    def pulse(self, *, force: bool = False) -> None:
        if self.callback is None:
            return
        now = time.monotonic()
        if not force and now - self.last_reported < self.interval_seconds:
            return
        try:
            self.callback()
        except Exception as exc:
            self.callback = None
            raise ReleaseInstallError("release_lease_heartbeat_failed", retryable=True) from exc
        self.last_reported = now


def _positive_env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ReleaseInstallError("release_installer_configuration_invalid") from exc
    if value <= 0:
        raise ReleaseInstallError("release_installer_configuration_invalid")
    return value


def _path_is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _trusted_owner(stat_result: os.stat_result) -> bool:
    return stat_result.st_uid in {0, os.geteuid()} and stat.S_IMODE(stat_result.st_mode) & 0o022 == 0


def _trusted_regular_file(path: Path, *, executable: bool = False, nonempty: bool = False) -> bool:
    try:
        value = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISREG(value.st_mode)
        and _trusted_owner(value)
        and (not executable or bool(value.st_mode & 0o111))
        and (not nonempty or value.st_size > 0)
    )


def _trusted_executable_file(path: Path) -> bool:
    """Accept a regular executable or a root-controlled executable symlink.

    Debian and Ubuntu expose ``/usr/bin/python3`` as a versioned symlink.  The
    release policy is intentionally portable and names that stable path, so a
    blanket symlink rejection makes the policy impossible to load on Home.
    We only follow the link when the link, every containing directory, and the
    final executable are owned by root/current euid and non-writable by group
    or world.
    """

    if _trusted_regular_file(path, executable=True):
        return True
    try:
        link = path.lstat()
        if not stat.S_ISLNK(link.st_mode) or link.st_uid not in {0, os.geteuid()}:
            return False
        for parent in path.parents:
            value = parent.lstat()
            sticky_root_boundary = (
                value.st_uid == 0 and stat.S_IMODE(value.st_mode) == 0o1777
            )
            if (
                not stat.S_ISDIR(value.st_mode)
                or (not _trusted_owner(value) and not sticky_root_boundary)
            ):
                return False
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    return resolved.is_absolute() and _trusted_regular_file(resolved, executable=True)


def _trusted_directory(path: Path, *, writable: bool) -> bool:
    try:
        value = path.lstat()
    except OSError:
        return False
    required_access = os.R_OK | os.X_OK | (os.W_OK if writable else 0)
    return stat.S_ISDIR(value.st_mode) and _trusted_owner(value) and os.access(path, required_access)


def _normalized_key(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_")


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_keys(child)


def _safe_relative_path(value: Any) -> str:
    text = str(value or "")
    if not text or "\\" in text or "\x00" in text or len(text.encode("utf-8")) > 4096:
        raise ReleaseInstallError("release_manifest_path_invalid")
    if any(part in {"", ".", ".."} for part in text.split("/")):
        raise ReleaseInstallError("release_manifest_path_invalid")
    candidate = PurePosixPath(text)
    if candidate.is_absolute():
        raise ReleaseInstallError("release_manifest_path_invalid")
    if candidate.parts[0] == ".kolibri-release":
        raise ReleaseInstallError("release_manifest_path_reserved")
    if any(len(part.encode("utf-8")) > 255 for part in candidate.parts):
        raise ReleaseInstallError("release_manifest_path_invalid")
    return candidate.as_posix()


def _validate_artifact_uri(uri: str) -> urllib.parse.SplitResult:
    if not uri or len(uri) > 8192 or any(char in uri for char in ("\x00", "\r", "\n")):
        raise ReleaseInstallError("release_artifact_uri_invalid")
    parsed = urllib.parse.urlsplit(uri)
    if parsed.scheme != "artifact" or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ReleaseInstallError("release_artifact_uri_invalid")
    logical = "/".join(part for part in (parsed.netloc, parsed.path.lstrip("/")) if part)
    _safe_relative_path(urllib.parse.unquote(logical))
    return parsed


def _read_json_object(
    path: Path,
    *,
    max_bytes: int,
    error_code: str,
    require_trusted_owner: bool = False,
) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_nonfinite(value: str) -> None:
        raise ValueError(f"non-finite JSON value: {value}")

    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            value = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(value.st_mode)
                or value.st_size > max_bytes
                or (require_trusted_owner and not _trusted_owner(value))
                or (require_trusted_owner and value.st_nlink != 1)
            ):
                raise ReleaseInstallError(error_code)
            raw = handle.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ReleaseInstallError(error_code)
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonfinite,
        )
    except ReleaseInstallError:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise ReleaseInstallError(error_code) from exc
    if not isinstance(payload, dict):
        raise ReleaseInstallError(error_code)
    return payload


def _read_trusted_bytes(path: Path, *, max_bytes: int, error_code: str) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            value = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(value.st_mode)
                or not _trusted_owner(value)
                or value.st_nlink != 1
                or not 0 < value.st_size <= max_bytes
            ):
                raise ReleaseInstallError(error_code)
            raw = handle.read(max_bytes + 1)
        if not raw or len(raw) > max_bytes:
            raise ReleaseInstallError(error_code)
        return raw
    except ReleaseInstallError:
        raise
    except OSError as exc:
        raise ReleaseInstallError(error_code) from exc


def _load_health_checks(
    value: Any,
    *,
    phase: str,
    allow_empty: bool = False,
) -> tuple[HealthCheck, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ReleaseInstallError("release_policy_health_checks_missing")
    checks: list[HealthCheck] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"name", "argv", "timeout_seconds"}:
            raise ReleaseInstallError("release_policy_health_check_invalid")
        name = str(item.get("name") or "")
        argv_value = item.get("argv")
        timeout = item.get("timeout_seconds")
        if not SAFE_CHECK_NAME.fullmatch(name) or name in seen:
            raise ReleaseInstallError("release_policy_health_check_invalid")
        if not isinstance(argv_value, list) or not 1 <= len(argv_value) <= 32:
            raise ReleaseInstallError("release_policy_health_check_invalid")
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 120:
            raise ReleaseInstallError("release_policy_health_check_invalid")
        argv = tuple(str(part) for part in argv_value)
        if any(not part or "\x00" in part or "\n" in part or len(part) > 2048 for part in argv):
            raise ReleaseInstallError("release_policy_health_check_invalid")
        executable = Path(argv[0])
        if (
            not executable.is_absolute()
            or not _trusted_executable_file(executable)
            or executable.name.lower() in FORBIDDEN_HEALTH_EXECUTABLES
        ):
            raise ReleaseInstallError("release_policy_health_executable_unavailable")
        seen.add(name)
        checks.append(HealthCheck(name=f"{phase}:{name}", argv=argv, timeout_seconds=timeout))
    return tuple(checks)


def load_release_policy(path: Path) -> ReleasePolicy:
    payload = _read_json_object(
        path,
        max_bytes=1024 * 1024,
        error_code="release_policy_invalid",
        require_trusted_owner=True,
    )
    required_keys = {
        "schema_version",
        "services",
        "default_services",
        "pre_health",
        "post_health",
        "service_timeout_seconds",
    }
    allowed_keys = required_keys | {"pre_activate", "required_payload_paths"}
    if (
        not required_keys.issubset(payload)
        or not set(payload).issubset(allowed_keys)
        or payload.get("schema_version") != RELEASE_POLICY_SCHEMA
    ):
        raise ReleaseInstallError("release_policy_invalid")
    services_value = payload.get("services")
    defaults_value = payload.get("default_services")
    service_timeout = payload.get("service_timeout_seconds")
    if not isinstance(services_value, list) or not isinstance(defaults_value, list):
        raise ReleaseInstallError("release_policy_services_invalid")
    services = tuple(str(item) for item in services_value)
    defaults = tuple(str(item) for item in defaults_value)
    if (
        len(set(services)) != len(services)
        or any(not SAFE_SERVICE.fullmatch(item) for item in services)
        or set(services) & FORBIDDEN_RELEASE_SERVICES
    ):
        raise ReleaseInstallError("release_policy_services_invalid")
    if len(set(defaults)) != len(defaults) or not set(defaults).issubset(set(services)):
        raise ReleaseInstallError("release_policy_services_invalid")
    if isinstance(service_timeout, bool) or not isinstance(service_timeout, int) or not 1 <= service_timeout <= 120:
        raise ReleaseInstallError("release_policy_services_invalid")
    required_payload_value = payload.get("required_payload_paths", [])
    if not isinstance(required_payload_value, list):
        raise ReleaseInstallError("release_policy_required_payload_invalid")
    try:
        required_payload_paths = tuple(
            _safe_relative_path(item) for item in required_payload_value
        )
    except ReleaseInstallError as exc:
        raise ReleaseInstallError("release_policy_required_payload_invalid") from exc
    if len(required_payload_paths) != len(set(required_payload_paths)):
        raise ReleaseInstallError("release_policy_required_payload_invalid")
    return ReleasePolicy(
        services=frozenset(services),
        default_services=defaults,
        required_payload_paths=required_payload_paths,
        pre_health=_load_health_checks(payload.get("pre_health"), phase="pre"),
        pre_activate=_load_health_checks(
            payload.get("pre_activate", []),
            phase="candidate",
            allow_empty=True,
        ),
        post_health=_load_health_checks(payload.get("post_health"), phase="post"),
        service_timeout_seconds=service_timeout,
    )


def load_canonical_manifest(path: Path) -> CanonicalManifest:
    raw_manifest = _read_trusted_bytes(
        path,
        max_bytes=2 * 1024 * 1024,
        error_code="release_manifest_invalid",
    )
    value = _read_json_object(path, max_bytes=2 * 1024 * 1024, error_code="release_manifest_invalid")
    expected_keys = {
        "schema_version",
        "release_id",
        "source_commit",
        "artifact_uri",
        "compatibility_epoch",
        "files",
        "metadata",
    }
    if set(value) != expected_keys or value.get("schema_version") != RELEASE_SCHEMA:
        raise ReleaseInstallError("release_manifest_invalid")
    release_id = str(value.get("release_id") or "")
    source_commit = str(value.get("source_commit") or "").lower()
    artifact_uri = str(value.get("artifact_uri") or "")
    compatibility_epoch = str(value.get("compatibility_epoch") or "")
    metadata = value.get("metadata")
    files_value = value.get("files")
    if not SAFE_RELEASE_ID.fullmatch(release_id):
        raise ReleaseInstallError("release_manifest_id_invalid")
    if not 7 <= len(source_commit) <= 64 or any(char not in "0123456789abcdef" for char in source_commit):
        raise ReleaseInstallError("release_manifest_source_commit_invalid")
    _validate_artifact_uri(artifact_uri)
    if not compatibility_epoch or len(compatibility_epoch) > 128:
        raise ReleaseInstallError("release_manifest_compatibility_invalid")
    if not isinstance(metadata, dict):
        raise ReleaseInstallError("release_manifest_metadata_invalid")
    if {_normalized_key(key) for key in _walk_keys(metadata)} & SECRET_METADATA_KEYS:
        raise ReleaseInstallError("release_manifest_metadata_secret_forbidden")
    if not isinstance(files_value, list) or not files_value:
        raise ReleaseInstallError("release_manifest_files_invalid")

    files: list[ManifestFile] = []
    normalized_files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in files_value:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "size_bytes", "mode"}:
            raise ReleaseInstallError("release_manifest_file_invalid")
        relative = _safe_relative_path(item.get("path"))
        digest = str(item.get("sha256") or "").lower()
        size = item.get("size_bytes")
        mode_text = str(item.get("mode") or "")
        if relative in seen or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ReleaseInstallError("release_manifest_file_invalid")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ReleaseInstallError("release_manifest_file_invalid")
        try:
            mode = int(mode_text, 8)
        except ValueError as exc:
            raise ReleaseInstallError("release_manifest_file_invalid") from exc
        if mode not in SAFE_FILE_MODES or mode_text != f"{mode:04o}":
            raise ReleaseInstallError("release_manifest_file_mode_invalid")
        seen.add(relative)
        files.append(ManifestFile(relative, digest, size, mode))
        normalized_files.append(
            {"path": relative, "sha256": digest, "size_bytes": size, "mode": mode_text}
        )

    payload = {
        "schema_version": RELEASE_SCHEMA,
        "release_id": release_id,
        "source_commit": source_commit,
        "artifact_uri": artifact_uri,
        "compatibility_epoch": compatibility_epoch,
        "files": sorted(normalized_files, key=lambda item: item["path"]),
        "metadata": metadata,
    }
    canonical_bytes = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if raw_manifest != canonical_bytes:
        raise ReleaseInstallError("release_manifest_not_canonical")
    digest = f"sha256:{hashlib.sha256(canonical_bytes).hexdigest()}"
    return CanonicalManifest(
        payload=payload,
        canonical_bytes=canonical_bytes,
        digest=digest,
        release_id=release_id,
        artifact_uri=artifact_uri,
        source_commit=source_commit,
        files=tuple(sorted(files, key=lambda item: item.path)),
    )


class ReleaseInstaller:
    def __init__(self, config: ReleaseInstallerConfig):
        self.config = config

    @classmethod
    def from_environment(cls, *, artifact_root: str | Path | None = None) -> "ReleaseInstaller":
        return cls(ReleaseInstallerConfig.from_environment(artifact_root=artifact_root))

    def prerequisite_status(self) -> dict[str, Any]:
        reasons: list[str] = []
        policy: ReleasePolicy | None = None
        for path, reason in (
            (self.config.artifact_root, "artifact_root_unavailable"),
            (self.config.release_root, "release_root_unavailable"),
            (self.config.current_link.parent, "release_switch_parent_unavailable"),
        ):
            if not _trusted_directory(path, writable=True):
                reasons.append(reason)
        try:
            _read_trusted_bytes(
                self.config.allowed_signers,
                max_bytes=1024 * 1024,
                error_code="release_allowed_signers_unavailable",
            )
        except ReleaseInstallError:
            reasons.append("release_allowed_signers_unavailable")
        try:
            _read_trusted_bytes(
                self.config.owner_allowed_signers,
                max_bytes=1024 * 1024,
                error_code="owner_allowed_signers_unavailable",
            )
        except ReleaseInstallError:
            reasons.append("owner_allowed_signers_unavailable")
        if not _trusted_regular_file(self.config.ssh_keygen, executable=True):
            reasons.append("release_signature_verifier_unavailable")
        try:
            policy = load_release_policy(self.config.policy_path)
        except (OSError, ReleaseInstallError):
            reasons.append("release_policy_unavailable")
        if policy and policy.services:
            if not _trusted_regular_file(self.config.systemctl, executable=True):
                reasons.append("release_service_manager_unavailable")
        lock_path = self.config.release_root / ".installer.lock"
        if os.path.lexists(lock_path) and not _trusted_regular_file(lock_path):
            reasons.append("release_installer_lock_unsafe")
        try:
            self._current_target()
        except ReleaseInstallError:
            reasons.append("release_current_link_unsafe")
        return {
            "status": "available" if not reasons else "unavailable",
            "capability": RELEASE_CAPABILITY,
            "reasons": sorted(set(reasons)),
            "policy_loaded": policy is not None,
        }

    def execute(
        self,
        kind: str,
        envelope: dict[str, Any],
        evidence_dir: Path,
        *,
        progress_callback: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        try:
            return self._execute(kind, envelope, evidence_dir, progress_callback=progress_callback)
        except ReleaseInstallError:
            raise
        except Exception as exc:
            raise ReleaseInstallError("release_install_internal_error", retryable=True) from exc

    def _execute(
        self,
        kind: str,
        envelope: dict[str, Any],
        evidence_dir: Path,
        *,
        progress_callback: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        progress = ProgressReporter(progress_callback)
        progress.pulse(force=True)
        request = self._validate_request(kind, envelope)
        prerequisite = self.prerequisite_status()
        if prerequisite["status"] != "available":
            raise ReleaseInstallError(
                "release_installer_prerequisites_unavailable",
                evidence={"prerequisite_status": prerequisite},
            )
        self._verify_owner_approval_attestation(envelope, progress)
        policy = load_release_policy(self.config.policy_path)
        selected_services = self._selected_services(request.services, policy)
        self._validate_evidence_dir(evidence_dir)
        self._audit(evidence_dir, "release_started", release_id=request.release_id, kind=kind)
        progress.pulse(force=True)

        lock_path = self.config.release_root / ".installer.lock"
        try:
            lock_fd = os.open(
                lock_path,
                os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
        except OSError as exc:
            raise ReleaseInstallError("release_installer_lock_unavailable", retryable=True) from exc
        with os.fdopen(lock_fd, "a+b") as lock_handle:
            lock_stat = os.fstat(lock_handle.fileno())
            if (
                not stat.S_ISREG(lock_stat.st_mode)
                or not _trusted_owner(lock_stat)
                or lock_stat.st_nlink != 1
            ):
                raise ReleaseInstallError("release_installer_lock_unsafe")
            deadline = time.monotonic() + self.config.lock_timeout_seconds
            while True:
                try:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise ReleaseInstallError("release_installer_lock_timeout", retryable=True)
                    progress.pulse()
                    time.sleep(0.25)
            progress.pulse(force=True)
            return self._execute_locked(request, policy, selected_services, evidence_dir, progress)

    def _validate_request(self, kind: str, envelope: dict[str, Any]) -> ReleaseRequest:
        if kind not in RELEASE_TASK_KINDS or not isinstance(envelope, dict):
            raise ReleaseInstallError("release_task_kind_invalid")
        forbidden = {_normalized_key(key) for key in _walk_keys(envelope)} & FORBIDDEN_TASK_COMMAND_KEYS
        if forbidden:
            raise ReleaseInstallError("release_task_command_forbidden")
        if envelope.get("required_capability") != RELEASE_CAPABILITY:
            raise ReleaseInstallError("release_task_capability_invalid")
        release_id_key = "release_id" if kind == "release_bundle_apply" else "rollback_to_release_id"
        release_id = str(envelope.get(release_id_key) or "")
        manifest_digest = str(envelope.get("manifest_digest") or "").lower()
        artifact_uri = str(envelope.get("artifact_uri") or "")
        source_commit = str(envelope.get("source_commit") or "").lower()
        approval_id = str(envelope.get("approval_id") or "")
        signature = envelope.get("signature")
        if not SAFE_RELEASE_ID.fullmatch(release_id):
            raise ReleaseInstallError("release_task_id_invalid")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", manifest_digest):
            raise ReleaseInstallError("release_task_manifest_digest_invalid")
        _validate_artifact_uri(artifact_uri)
        if not 7 <= len(source_commit) <= 64 or any(char not in "0123456789abcdef" for char in source_commit):
            raise ReleaseInstallError("release_task_source_commit_invalid")
        if not SAFE_RECORD_ID.fullmatch(approval_id):
            raise ReleaseInstallError("release_task_approval_invalid")
        if not isinstance(signature, dict):
            raise ReleaseInstallError("release_task_signature_contract_invalid")
        signer_identity = str(signature.get("signer_identity") or "")
        if (
            signature.get("format") != "sshsig"
            or signature.get("namespace") != RELEASE_SIGNATURE_NAMESPACE
            or not SAFE_RECORD_ID.fullmatch(signer_identity)
        ):
            raise ReleaseInstallError("release_task_signature_contract_invalid")
        services_value = envelope.get("services")
        services: tuple[str, ...] | None = None
        if services_value is not None:
            if not isinstance(services_value, list):
                raise ReleaseInstallError("release_task_services_invalid")
            services = tuple(str(item) for item in services_value)
            if len(set(services)) != len(services) or any(not SAFE_SERVICE.fullmatch(item) for item in services):
                raise ReleaseInstallError("release_task_services_invalid")
        return ReleaseRequest(
            kind=kind,
            release_id=release_id,
            manifest_digest=manifest_digest,
            artifact_uri=artifact_uri,
            source_commit=source_commit,
            signer_identity=signer_identity,
            approval_id=approval_id,
            services=services,
        )

    def _selected_services(self, requested: tuple[str, ...] | None, policy: ReleasePolicy) -> tuple[str, ...]:
        selected = requested if requested is not None else policy.default_services
        if not set(selected).issubset(policy.services):
            raise ReleaseInstallError("release_service_not_allowed")
        if policy.pre_activate and selected != policy.default_services:
            raise ReleaseInstallError("release_service_profile_mismatch")
        return selected

    def _validate_evidence_dir(self, evidence_dir: Path) -> None:
        try:
            root = self.config.artifact_root.resolve(strict=True)
            configured_root = self.config.artifact_root.absolute()
            candidate = evidence_dir.absolute()
            if not _path_is_within(candidate, configured_root):
                raise ReleaseInstallError("release_evidence_dir_invalid")
            relative = candidate.relative_to(configured_root)
            resolved = evidence_dir.resolve(strict=True)
        except OSError as exc:
            raise ReleaseInstallError("release_evidence_dir_invalid") from exc
        if resolved != root.joinpath(relative) or not _trusted_directory(resolved, writable=True):
            raise ReleaseInstallError("release_evidence_dir_invalid")
        cursor = root
        for component in relative.parts:
            cursor /= component
            if not _trusted_directory(cursor, writable=True):
                raise ReleaseInstallError("release_evidence_dir_invalid")

    def _execute_locked(
        self,
        request: ReleaseRequest,
        policy: ReleasePolicy,
        selected_services: tuple[str, ...],
        evidence_dir: Path,
        progress: ProgressReporter,
    ) -> dict[str, Any]:
        pre_health = self._run_health_checks(policy.pre_health, progress)
        if not all(item["status"] == "passed" for item in pre_health):
            raise ReleaseInstallError(
                "release_pre_health_failed",
                retryable=True,
                evidence={"health_checks": {"pre": pre_health}},
            )

        bundle_path = evidence_dir / f".release-bundle-{uuid.uuid4().hex}.tar"
        staging: Path | None = self.config.release_root / f".staging-{request.release_id}-{uuid.uuid4().hex}"
        bundle_sha256 = ""
        manifest: CanonicalManifest | None = None
        try:
            bundle_sha256 = self._materialize_bundle(request.artifact_uri, bundle_path, progress)
            try:
                member_modes = self._extract_bundle(bundle_path, staging, progress)
            except ReleaseInstallError:
                raise
            except (OSError, tarfile.TarError, EOFError, ValueError) as exc:
                raise ReleaseInstallError("release_bundle_archive_invalid") from exc
            manifest = load_canonical_manifest(staging / MANIFEST_MEMBER)
            self._validate_manifest_against_request(manifest, request)
            self._verify_signature(staging / SIGNATURE_MEMBER, manifest, request.signer_identity, progress)
            self._validate_payload(staging, manifest, member_modes, progress)
            manifest_paths = {item.path for item in manifest.files}
            if (
                AGENT_HOST_RUNTIME_PATH in manifest_paths
                and MIMO_RESPONSE_AGENT_PROFILE_PATH not in manifest_paths
            ):
                raise ReleaseInstallError("release_agent_host_profile_missing")
            if not set(policy.required_payload_paths).issubset(manifest_paths):
                raise ReleaseInstallError("release_required_payload_missing")
            if "RELEASE_ID" in policy.required_payload_paths:
                try:
                    release_marker = (staging / "RELEASE_ID").read_bytes()
                except OSError as exc:
                    raise ReleaseInstallError("release_id_marker_invalid") from exc
                if release_marker != f"{manifest.release_id}\n".encode("ascii"):
                    raise ReleaseInstallError("release_id_marker_invalid")

            final_dir, idempotent_install = self._publish_immutable_release(
                staging,
                manifest,
                request.signer_identity,
                progress,
            )
            staging = None
            health_replacements = {
                "{release_dir}": str(final_dir),
                "{release_kind}": (
                    "rollback" if request.kind == "release_bundle_rollback" else "apply"
                ),
            }
            candidate_health = self._run_health_checks(
                policy.pre_activate,
                progress,
                replacements=health_replacements,
            )
            if not all(item["status"] == "passed" for item in candidate_health):
                self._audit(
                    evidence_dir,
                    "release_candidate_failed",
                    release_id=request.release_id,
                    code="release_candidate_health_failed",
                )
                raise ReleaseInstallError(
                    "release_candidate_health_failed",
                    retryable=True,
                    evidence={
                        "manifest_digest": manifest.digest,
                        "release_health": {
                            "status": "failed",
                            "manifest_digest": manifest.digest,
                            "release_id": manifest.release_id,
                        },
                        "health_checks": {
                            "pre": pre_health,
                            "candidate": candidate_health,
                            "post": [],
                        },
                        "service_results": [],
                        "rollback": {
                            "status": "not_required",
                            "reason": "activation_not_started",
                        },
                    },
                )
            previous = self._current_target()
            already_current = previous == final_dir
            service_results: list[dict[str, Any]] = []
            post_health: list[dict[str, Any]] = []
            try:
                if not already_current:
                    self._atomic_switch(final_dir)
                service_results = self._restart_services(selected_services, policy, progress)
                post_health = self._run_health_checks(
                    policy.post_health,
                    progress,
                    replacements=health_replacements,
                )
                if not all(item["status"] == "passed" for item in service_results + post_health):
                    raise ReleaseInstallError("release_post_health_failed", retryable=True)
            except ReleaseInstallError as activation_error:
                rollback = self._rollback_activation(previous, selected_services, policy, progress)
                self._audit(
                    evidence_dir,
                    "release_activation_failed",
                    release_id=request.release_id,
                    code=activation_error.code,
                    rollback_status=rollback["status"],
                )
                raise ReleaseInstallError(
                    activation_error.code,
                    retryable=activation_error.retryable,
                    evidence={
                        "manifest_digest": manifest.digest,
                        "release_health": {
                            "status": "failed",
                            "manifest_digest": manifest.digest,
                            "release_id": manifest.release_id,
                        },
                        "health_checks": {
                            "pre": pre_health,
                            "candidate": candidate_health,
                            "post": post_health,
                        },
                        "service_results": service_results,
                        "rollback": rollback,
                    },
                ) from activation_error

            self._audit(
                evidence_dir,
                "release_completed",
                release_id=request.release_id,
                manifest_digest=manifest.digest,
            )
            agent_host_files = [
                item for item in manifest.files if item.path == AGENT_HOST_RUNTIME_PATH
            ]
            response_profile_files = [
                item
                for item in manifest.files
                if item.path == MIMO_RESPONSE_AGENT_PROFILE_PATH
            ]
            agent_host_runtime = {
                "included": len(agent_host_files) == 1,
                "runtime_path": AGENT_HOST_RUNTIME_PATH,
                "runtime_sha256": (
                    agent_host_files[0].sha256 if len(agent_host_files) == 1 else None
                ),
                "response_profile_included": len(response_profile_files) == 1,
                "response_profile_path": MIMO_RESPONSE_AGENT_PROFILE_PATH,
                "response_profile_sha256": (
                    response_profile_files[0].sha256
                    if len(response_profile_files) == 1
                    else None
                ),
                "release_id": manifest.release_id,
                "manifest_digest": manifest.digest,
            }
            return {
                "status": "completed",
                "kind": request.kind,
                "release_id": manifest.release_id,
                "manifest_digest": manifest.digest,
                "bundle_sha256": bundle_sha256,
                "installed_release_path": str(final_dir),
                "current_release_path": str(final_dir),
                "idempotent_reapply": bool(idempotent_install and already_current),
                "immutable_release_reused": idempotent_install,
                "atomic_switch_performed": not already_current,
                "services": list(selected_services),
                "service_results": service_results,
                "health_checks": {
                    "pre": pre_health,
                    "candidate": candidate_health,
                    "post": post_health,
                },
                "release_health": {
                    "status": "healthy",
                    "release_id": manifest.release_id,
                    "manifest_digest": manifest.digest,
                    "checked_at": utc_now(),
                },
                "agent_host_runtime": agent_host_runtime,
                "rollback": {
                    "status": "completed" if request.kind == "release_bundle_rollback" else "not_required",
                    "from_release_id": previous.name if previous else None,
                    "to_release_id": manifest.release_id,
                },
                "checks": [
                    "source_boundary",
                    "bundle_limits",
                    "tar_member_safety",
                    "manifest_digest",
                    "worker_sshsig",
                    "file_hash_size_mode",
                    "pre_health",
                    "candidate_health_before_switch",
                    "post_health",
                    "atomic_current_switch",
                ],
                "changed_files": [],
                "retryable": False,
            }
        finally:
            try:
                bundle_path.unlink(missing_ok=True)
            except OSError:
                pass
            if staging is not None and staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    def _open_local_artifact(self, relative: str) -> int:
        parts = PurePosixPath(relative).parts
        directory_fd: int | None = None
        try:
            directory_fd = os.open(
                self.config.artifact_root,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            root_stat = os.fstat(directory_fd)
            if not stat.S_ISDIR(root_stat.st_mode) or not _trusted_owner(root_stat):
                raise ReleaseInstallError("release_artifact_boundary_violation")
            for component in parts[:-1]:
                next_fd = os.open(
                    component,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd,
                )
                os.close(directory_fd)
                directory_fd = next_fd
            source_fd = os.open(
                parts[-1],
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
            source_stat = os.fstat(source_fd)
            if not stat.S_ISREG(source_stat.st_mode):
                os.close(source_fd)
                raise ReleaseInstallError("release_artifact_boundary_violation")
            if source_stat.st_size > self.config.max_bundle_bytes:
                os.close(source_fd)
                raise ReleaseInstallError("release_bundle_too_large")
            return source_fd
        except ReleaseInstallError:
            raise
        except OSError as exc:
            raise ReleaseInstallError("release_artifact_boundary_violation") from exc
        finally:
            if directory_fd is not None:
                os.close(directory_fd)

    def _materialize_bundle(
        self,
        uri: str,
        destination: Path,
        progress: ProgressReporter,
    ) -> str:
        parsed = _validate_artifact_uri(uri)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            destination_fd = os.open(destination, flags, 0o600)
        except OSError as exc:
            raise ReleaseInstallError("release_bundle_staging_failed") from exc
        try:
            with os.fdopen(destination_fd, "wb") as output:
                logical = "/".join(part for part in (parsed.netloc, parsed.path.lstrip("/")) if part)
                relative = _safe_relative_path(urllib.parse.unquote(logical))
                source_fd = self._open_local_artifact(relative)
                with os.fdopen(source_fd, "rb") as input_stream:
                    digest, _ = self._copy_limited(input_stream, output, progress)
                    return digest
        except Exception:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _copy_limited(
        self,
        source: BinaryIO,
        destination: BinaryIO,
        progress: ProgressReporter,
        *,
        deadline: float | None = None,
    ) -> tuple[str, int]:
        digest = hashlib.sha256()
        total = 0
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                raise ReleaseInstallError("release_download_timeout", retryable=True)
            progress.pulse()
            chunk = source.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > self.config.max_bundle_bytes:
                raise ReleaseInstallError("release_bundle_too_large")
            digest.update(chunk)
            destination.write(chunk)
        progress.pulse(force=True)
        destination.flush()
        os.fsync(destination.fileno())
        return digest.hexdigest(), total

    def _extract_bundle(
        self,
        bundle_path: Path,
        staging: Path,
        progress: ProgressReporter,
    ) -> dict[str, int]:
        try:
            staging.mkdir(mode=0o700)
        except OSError as exc:
            raise ReleaseInstallError("release_bundle_staging_failed") from exc
        try:
            archive = tarfile.open(bundle_path, mode="r|*")
        except (OSError, tarfile.TarError) as exc:
            raise ReleaseInstallError("release_bundle_archive_invalid") from exc
        with archive:
            names: set[str] = set()
            normalized_names: set[str] = set()
            total_size = 0
            member_count = 0
            member_modes: dict[str, int] = {}
            for member in archive:
                member_count += 1
                if member_count > self.config.max_members:
                    raise ReleaseInstallError("release_bundle_member_limit_exceeded")
                name = member.name
                raw_parts = name.split("/") if name else []
                if member.isdir() and raw_parts and raw_parts[-1] == "":
                    raw_parts = raw_parts[:-1]
                canonical_name = "/".join(raw_parts)
                if not name or "\\" in name or "\x00" in name or name in names:
                    raise ReleaseInstallError("release_bundle_member_invalid")
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in raw_parts:
                    raise ReleaseInstallError("release_bundle_path_traversal")
                if any(part in {"", "."} for part in raw_parts) or canonical_name in normalized_names:
                    raise ReleaseInstallError("release_bundle_member_invalid")
                if member.issym() or member.islnk() or member.isdev() or not (member.isdir() or member.isreg()):
                    raise ReleaseInstallError("release_bundle_unsafe_member_type")
                if member.size < 0 or (member.isdir() and member.size != 0):
                    raise ReleaseInstallError("release_bundle_member_invalid")
                names.add(name)
                normalized_names.add(canonical_name)
                total_size += max(0, member.size)
                if total_size > self.config.max_unpacked_bytes:
                    raise ReleaseInstallError("release_bundle_unpacked_limit_exceeded")
                mapped: str | None
                if name in {MANIFEST_MEMBER, SIGNATURE_MEMBER}:
                    if not member.isreg():
                        raise ReleaseInstallError("release_bundle_metadata_invalid")
                    if (name == MANIFEST_MEMBER and member.size > 2 * 1024 * 1024) or (
                        name == SIGNATURE_MEMBER and member.size > 64 * 1024
                    ):
                        raise ReleaseInstallError("release_bundle_metadata_invalid")
                    mapped = name
                elif name.startswith(PAYLOAD_PREFIX):
                    suffix = name[len(PAYLOAD_PREFIX):].rstrip("/")
                    mapped = _safe_relative_path(suffix) if suffix else None
                    if member.isreg() and mapped is None:
                        raise ReleaseInstallError("release_bundle_member_invalid")
                    if member.isreg() and mapped is not None:
                        member_modes[mapped] = stat.S_IMODE(member.mode)
                elif member.isdir() and name.rstrip("/") in {"payload", ".kolibri-release"}:
                    mapped = None
                else:
                    raise ReleaseInstallError("release_bundle_layout_invalid")
                progress.pulse()
                if member.isdir() or mapped is None:
                    continue
                destination_relative = member.name if member.name in {MANIFEST_MEMBER, SIGNATURE_MEMBER} else mapped
                assert destination_relative is not None
                target = staging.joinpath(*PurePosixPath(destination_relative).parts)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                try:
                    source = archive.extractfile(member)
                    if source is None:
                        raise ReleaseInstallError("release_bundle_member_unreadable")
                    fd = os.open(
                        target,
                        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                    )
                    written = 0
                    with source, os.fdopen(fd, "wb") as output:
                        while True:
                            progress.pulse()
                            chunk = source.read(64 * 1024)
                            if not chunk:
                                break
                            written += len(chunk)
                            if written > member.size:
                                raise ReleaseInstallError("release_bundle_member_size_mismatch")
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                    if written != member.size:
                        raise ReleaseInstallError("release_bundle_member_size_mismatch")
                    progress.pulse()
                except ReleaseInstallError:
                    raise
                except OSError as exc:
                    raise ReleaseInstallError("release_bundle_extract_failed") from exc
            if member_count == 0:
                raise ReleaseInstallError("release_bundle_member_limit_exceeded")
            if MANIFEST_MEMBER not in names or SIGNATURE_MEMBER not in names:
                raise ReleaseInstallError("release_bundle_metadata_missing")
        return member_modes

    def _validate_manifest_against_request(self, manifest: CanonicalManifest, request: ReleaseRequest) -> None:
        if manifest.release_id != request.release_id:
            raise ReleaseInstallError("release_manifest_release_id_mismatch")
        if manifest.digest != request.manifest_digest:
            raise ReleaseInstallError("release_manifest_digest_mismatch")
        if manifest.artifact_uri != request.artifact_uri:
            raise ReleaseInstallError("release_manifest_artifact_uri_mismatch")
        if manifest.source_commit != request.source_commit:
            raise ReleaseInstallError("release_manifest_source_commit_mismatch")

    def _verify_sshsig(
        self,
        signature_path: Path,
        message: bytes,
        signer_identity: str,
        namespace: str,
        allowed_signers_path: Path,
        progress: ProgressReporter,
        *,
        invalid_code: str,
    ) -> None:
        try:
            signature_stat = signature_path.lstat()
        except OSError as exc:
            raise ReleaseInstallError(invalid_code) from exc
        if (
            not stat.S_ISREG(signature_stat.st_mode)
            or signature_stat.st_nlink != 1
            or not 0 < signature_stat.st_size <= 64 * 1024
        ):
            raise ReleaseInstallError(invalid_code)
        if not _trusted_regular_file(self.config.ssh_keygen, executable=True):
            raise ReleaseInstallError("release_signature_verifier_unavailable")
        allowed_signers = _read_trusted_bytes(
            allowed_signers_path,
            max_bytes=1024 * 1024,
            error_code="release_signature_trust_unavailable",
        )
        snapshot_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".allowed-signers-",
                dir=self.config.release_root,
                delete=False,
            ) as snapshot:
                snapshot_path = Path(snapshot.name)
                os.fchmod(snapshot.fileno(), 0o600)
                snapshot.write(allowed_signers)
                snapshot.flush()
                os.fsync(snapshot.fileno())
            progress.pulse(force=True)
            completed = subprocess.run(
                [
                    str(self.config.ssh_keygen),
                    "-Y",
                    "verify",
                    "-f",
                    str(snapshot_path),
                    "-I",
                    signer_identity,
                    "-n",
                    namespace,
                    "-s",
                    str(signature_path),
                ],
                input=message,
                capture_output=True,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ReleaseInstallError("release_signature_verifier_unavailable") from exc
        finally:
            if snapshot_path is not None:
                try:
                    snapshot_path.unlink(missing_ok=True)
                except OSError as exc:
                    raise ReleaseInstallError("release_signature_snapshot_cleanup_failed") from exc
        progress.pulse(force=True)
        if completed.returncode != 0:
            raise ReleaseInstallError(invalid_code)

    def _verify_signature(
        self,
        signature_path: Path,
        manifest: CanonicalManifest,
        signer_identity: str,
        progress: ProgressReporter,
    ) -> None:
        self._verify_sshsig(
            signature_path,
            manifest.canonical_bytes,
            signer_identity,
            RELEASE_SIGNATURE_NAMESPACE,
            self.config.allowed_signers,
            progress,
            invalid_code="release_signature_invalid",
        )

    def _verify_owner_approval_attestation(
        self,
        envelope: dict[str, Any],
        progress: ProgressReporter,
    ) -> None:
        try:
            attestation = canonical_owner_approval_attestation(
                envelope.get("approval_attestation")
            )
            if envelope.get("approval_attestation_digest") != approval_attestation_digest(attestation):
                raise ReleaseAuthorityError("owner_approval_attestation_digest_mismatch")
            validate_approval_for_task(attestation["payload"], envelope)
        except ReleaseAuthorityError as exc:
            raise ReleaseInstallError("release_owner_approval_invalid") from exc

        signature_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=".owner-approval-",
                suffix=".sig",
                dir=self.config.release_root,
                delete=False,
            ) as handle:
                signature_path = Path(handle.name)
                os.fchmod(handle.fileno(), 0o600)
                handle.write(attestation["signature"])
                handle.flush()
                os.fsync(handle.fileno())
            self._verify_sshsig(
                signature_path,
                canonical_owner_approval_bytes(attestation["payload"]),
                attestation["payload"]["signer_identity"],
                OWNER_APPROVAL_NAMESPACE,
                self.config.owner_allowed_signers,
                progress,
                invalid_code="release_owner_approval_signature_invalid",
            )
        finally:
            if signature_path is not None:
                try:
                    signature_path.unlink(missing_ok=True)
                except OSError as exc:
                    raise ReleaseInstallError("release_signature_snapshot_cleanup_failed") from exc

    def _validate_payload(
        self,
        staging: Path,
        manifest: CanonicalManifest,
        member_modes: dict[str, int],
        progress: ProgressReporter,
    ) -> None:
        expected = {item.path: item for item in manifest.files}
        actual: dict[str, Path] = {}
        metadata_files: set[str] = set()
        for path in staging.rglob("*"):
            if path.is_symlink():
                raise ReleaseInstallError("release_payload_unsafe_file")
            if path.is_dir():
                continue
            relative = path.relative_to(staging).as_posix()
            if relative.startswith(".kolibri-release/"):
                if path.lstat().st_nlink != 1:
                    raise ReleaseInstallError("release_bundle_metadata_invalid")
                metadata_files.add(relative)
                continue
            if not path.is_file():
                raise ReleaseInstallError("release_payload_unsafe_file")
            actual[relative] = path
            progress.pulse()
        if metadata_files != {MANIFEST_MEMBER, SIGNATURE_MEMBER}:
            raise ReleaseInstallError("release_bundle_metadata_invalid")
        if set(actual) != set(expected) or set(member_modes) != set(expected):
            raise ReleaseInstallError("release_payload_file_set_mismatch")
        for relative, item in expected.items():
            path = actual[relative]
            if member_modes[relative] != item.mode:
                raise ReleaseInstallError("release_payload_mode_mismatch")
            if path.lstat().st_size != item.size_bytes:
                raise ReleaseInstallError("release_payload_size_mismatch")
            if self._sha256_file(path, progress) != item.sha256:
                raise ReleaseInstallError("release_payload_digest_mismatch")
            path.chmod(item.mode)
            if stat.S_IMODE(path.stat().st_mode) != item.mode:
                raise ReleaseInstallError("release_payload_mode_mismatch")
            progress.pulse()
        (staging / MANIFEST_MEMBER).chmod(0o444)
        (staging / SIGNATURE_MEMBER).chmod(0o444)
        for directory in sorted((path for path in staging.rglob("*") if path.is_dir()), reverse=True):
            directory.chmod(0o755)
        staging.chmod(0o755)

    @staticmethod
    def _sha256_file(path: Path, progress: ProgressReporter) -> str:
        digest = hashlib.sha256()
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except OSError as exc:
            raise ReleaseInstallError("release_payload_unsafe_file") from exc
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ReleaseInstallError("release_payload_unsafe_file")
            for chunk in iter(lambda: handle.read(64 * 1024), b""):
                digest.update(chunk)
                progress.pulse()
            after = os.fstat(handle.fileno())
        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise ReleaseInstallError("release_payload_unstable")
        return digest.hexdigest()

    def _publish_immutable_release(
        self,
        staging: Path,
        manifest: CanonicalManifest,
        signer_identity: str,
        progress: ProgressReporter,
    ) -> tuple[Path, bool]:
        final_dir = self.config.release_root / manifest.release_id
        if os.path.lexists(final_dir):
            if not _trusted_directory(final_dir, writable=False):
                raise ReleaseInstallError("release_id_collision")
            existing = load_canonical_manifest(final_dir / MANIFEST_MEMBER)
            if existing.digest != manifest.digest:
                raise ReleaseInstallError("release_id_collision")
            self._verify_signature(
                final_dir / SIGNATURE_MEMBER,
                existing,
                signer_identity,
                progress,
            )
            self._validate_existing_release(final_dir, existing, progress)
            try:
                shutil.rmtree(staging)
            except OSError as exc:
                raise ReleaseInstallError("release_bundle_staging_cleanup_failed") from exc
            return final_dir.resolve(), True
        try:
            os.rename(staging, final_dir)
            self._fsync_dir(self.config.release_root)
        except FileExistsError:
            return self._publish_immutable_release(staging, manifest, signer_identity, progress)
        except OSError as exc:
            raise ReleaseInstallError("release_publish_failed") from exc
        return final_dir.resolve(), False

    def _validate_existing_release(
        self,
        release_dir: Path,
        manifest: CanonicalManifest,
        progress: ProgressReporter,
    ) -> None:
        expected = {item.path: item for item in manifest.files}
        actual: dict[str, Path] = {}
        metadata_files: set[str] = set()
        for path in release_dir.rglob("*"):
            relative = path.relative_to(release_dir).as_posix()
            if path.is_symlink():
                raise ReleaseInstallError("installed_release_integrity_failed")
            if path.is_dir():
                continue
            if not path.is_file():
                raise ReleaseInstallError("installed_release_integrity_failed")
            if path.lstat().st_nlink != 1:
                raise ReleaseInstallError("installed_release_integrity_failed")
            if relative.startswith(".kolibri-release/"):
                metadata_files.add(relative)
            else:
                actual[relative] = path
            progress.pulse()
        if metadata_files != {MANIFEST_MEMBER, SIGNATURE_MEMBER}:
            raise ReleaseInstallError("installed_release_integrity_failed")
        if set(actual) != set(expected):
            raise ReleaseInstallError("installed_release_file_set_mismatch")
        for relative, item in expected.items():
            path = actual[relative]
            if path.lstat().st_size != item.size_bytes:
                raise ReleaseInstallError("installed_release_integrity_failed")
            if stat.S_IMODE(path.lstat().st_mode) != item.mode or self._sha256_file(path, progress) != item.sha256:
                raise ReleaseInstallError("installed_release_integrity_failed")

    def _current_target(self) -> Path | None:
        current = self.config.current_link
        if not os.path.lexists(current):
            return None
        if not current.is_symlink():
            raise ReleaseInstallError("release_current_link_unsafe")
        raw_target = Path(os.readlink(current))
        candidate = raw_target if raw_target.is_absolute() else current.parent / raw_target
        try:
            resolved = candidate.resolve(strict=True)
            root = self.config.release_root.resolve(strict=True)
        except OSError as exc:
            raise ReleaseInstallError("release_current_link_broken") from exc
        if resolved.parent != root or not _trusted_directory(resolved, writable=False):
            raise ReleaseInstallError("release_current_link_unsafe")
        return resolved

    def _atomic_switch(self, target: Path) -> None:
        root = self.config.release_root.resolve(strict=True)
        target = target.resolve(strict=True)
        if target.parent != root or not target.is_dir():
            raise ReleaseInstallError("release_switch_target_invalid")
        current = self.config.current_link
        if os.path.lexists(current) and not current.is_symlink():
            raise ReleaseInstallError("release_current_link_unsafe")
        temporary = current.parent / f".{current.name}.switch-{uuid.uuid4().hex}"
        try:
            os.symlink(str(target), temporary)
            os.replace(temporary, current)
            self._fsync_dir(current.parent)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise ReleaseInstallError("release_atomic_switch_failed") from exc

    @staticmethod
    def _stop_process(process: subprocess.Popen[Any]) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=1)
        except (OSError, subprocess.SubprocessError):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                process.kill()
            try:
                process.wait(timeout=1)
            except subprocess.SubprocessError:
                pass

    @classmethod
    def _run_bounded_process(
        cls,
        argv: tuple[str, ...] | list[str],
        timeout_seconds: float,
        progress: ProgressReporter,
    ) -> int | None:
        try:
            process = subprocess.Popen(
                list(argv),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
        except OSError:
            return None
        deadline = time.monotonic() + timeout_seconds
        try:
            while True:
                return_code = process.poll()
                if return_code is not None:
                    return return_code
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    cls._stop_process(process)
                    return None
                progress.pulse()
                time.sleep(min(0.25, remaining))
        except ReleaseInstallError:
            cls._stop_process(process)
            raise

    def _restart_services(
        self,
        services: tuple[str, ...],
        policy: ReleasePolicy,
        progress: ProgressReporter,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for service in services:
            started = time.monotonic()
            if not _trusted_regular_file(self.config.systemctl, executable=True):
                return_code = None
            else:
                return_code = self._run_bounded_process(
                    (str(self.config.systemctl), "try-restart", service),
                    policy.service_timeout_seconds,
                    progress,
                )
            status_value = "passed" if return_code == 0 else "failed"
            results.append(
                {
                    "service": service,
                    "action": "try-restart",
                    "status": status_value,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                }
            )
        return results

    @classmethod
    def _run_health_checks(
        cls,
        checks: tuple[HealthCheck, ...],
        progress: ProgressReporter,
        *,
        replacements: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for check in checks:
            started = time.monotonic()
            deadline = started + check.timeout_seconds
            executable = Path(check.argv[0])
            executable_available = _trusted_regular_file(executable, executable=True)
            argv = tuple((replacements or {}).get(part, part) for part in check.argv)
            legacy_rollback_compatibility_allowed = bool(
                (replacements or {}).get("{release_kind}") == "rollback"
                and "{release_kind}" in check.argv
            )
            attempts = 0
            passed = False
            legacy_compatibility_used = False
            while executable_available:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                attempts += 1
                return_code = cls._run_bounded_process(argv, remaining, progress)
                if return_code == 0:
                    passed = True
                    break
                if return_code == 10 and legacy_rollback_compatibility_allowed:
                    passed = True
                    legacy_compatibility_used = True
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                progress.pulse()
                time.sleep(min(HEALTH_RETRY_DELAY_SECONDS, remaining))
            result = {
                "name": check.name,
                "status": "passed" if passed else "failed",
                "attempts": attempts,
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
            if legacy_compatibility_used:
                result["compatibility_mode"] = "legacy-rollback-contract"
            results.append(result)
        return results

    def _rollback_activation(
        self,
        previous: Path | None,
        services: tuple[str, ...],
        policy: ReleasePolicy,
        progress: ProgressReporter,
    ) -> dict[str, Any]:
        switch_status = "completed"
        try:
            if previous is None:
                if os.path.lexists(self.config.current_link):
                    if not self.config.current_link.is_symlink():
                        raise ReleaseInstallError("release_current_link_unsafe")
                    self.config.current_link.unlink()
                    self._fsync_dir(self.config.current_link.parent)
            else:
                self._atomic_switch(previous)
        except (OSError, ReleaseInstallError):
            switch_status = "failed"
        try:
            service_results = self._restart_services(services, policy, progress)
        except ReleaseInstallError as exc:
            service_results = [{"status": "failed", "error_type": exc.code}]
        try:
            health_results = self._run_health_checks(
                policy.post_health,
                progress,
                replacements={
                    "{release_dir}": str(previous),
                    "{release_kind}": "rollback",
                } if previous is not None else None,
            )
        except ReleaseInstallError as exc:
            health_results = [{"status": "failed", "error_type": exc.code}]
        healthy = all(item["status"] == "passed" for item in service_results + health_results)
        return {
            "status": "completed" if switch_status == "completed" and healthy else "failed",
            "atomic_switch": switch_status,
            "restored_release_id": previous.name if previous else None,
            "service_results": service_results,
            "health_checks": health_results,
        }

    @staticmethod
    def _fsync_dir(path: Path) -> None:
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError as exc:
            raise ReleaseInstallError("release_filesystem_sync_failed") from exc

    @staticmethod
    def _audit(evidence_dir: Path, event: str, **fields: Any) -> None:
        safe_fields = {
            key: value
            for key, value in fields.items()
            if key in {"code", "kind", "manifest_digest", "release_id", "rollback_status"}
        }
        record = {"time": utc_now(), "event": event, **safe_fields}
        audit_path = evidence_dir / "release-installer.jsonl"
        try:
            descriptor = os.open(
                audit_path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
                value = os.fstat(handle.fileno())
                if (
                    not stat.S_ISREG(value.st_mode)
                    or not _trusted_owner(value)
                    or value.st_nlink != 1
                ):
                    raise ReleaseInstallError("release_audit_log_unsafe")
                handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except ReleaseInstallError:
            raise
        except OSError as exc:
            raise ReleaseInstallError("release_audit_log_unavailable", retryable=True) from exc
