#!/usr/bin/env python3
"""Build and verify an immutable, paired frontend/backend P7 release.

This tool is deliberately incapable of changing nginx, systemd, a symlink, a
database, or a remote host.  It produces a content-addressed release directory
and an activation *plan*.  The separate owner-approved release controller is
responsible for applying that plan.

``build`` requires a clean committed Git worktree and binds the generated
frontend, backend and Git bundle to one release identity.  Signing is optional
for a local candidate, but ``plan-switch`` always requires and verifies owner,
collector, approval and rollback signatures against pinned trust roots before
it emits an activation plan.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from typing import Any, Callable, Iterable, Sequence


SCHEMA_VERSION = "kolibri.p7.release.v1"
GATE_SCHEMA_VERSION = "kolibri.p7.functional-gates.v3"
ROLLBACK_HEALTH_SCHEMA_VERSION = "kolibri.p7.rollback-health.v1"
APPROVAL_SCHEMA_VERSION = "kolibri.p7.owner-approval.v1"
PLAN_SCHEMA_VERSION = "kolibri.p7.paired-switch-plan.v2"
RELEASE_SIGNATURE_NAMESPACE = "kolibri-p7-release"
GATE_SIGNATURE_NAMESPACE = "kolibri-p7-functional-gates"
ROLLBACK_HEALTH_SIGNATURE_NAMESPACE = "kolibri-p7-rollback-health"
APPROVAL_SIGNATURE_NAMESPACE = "kolibri-p7-owner-approval"

# These paths and identities are release-controller policy, not command-line
# inputs. Production installs the public trust roots as root-owned,
# non-writable files. Tests replace the constants with isolated fixtures.
OWNER_TRUST_ROOT = Path("/etc/kolibri/trust/p7-owner.allowed_signers")
COLLECTOR_TRUST_ROOT = Path("/etc/kolibri/trust/p7-gate-collector.allowed_signers")
OWNER_SIGNER_IDENTITY = "kolibri-owner"
COLLECTOR_SIGNER_IDENTITY = "kolibri-p7-gate-collector"
TRUST_ROOT_REQUIRED_UID = 0
APPROVAL_BINDING_KEYS = frozenset(
    {
        "release_id",
        "manifest_sha256",
        "gate_evidence_sha256",
        "rollback_release_id",
        "rollback_manifest_sha256",
        "rollback_health_evidence_sha256",
        "previous_route_config_sha256",
    }
)
DEFAULT_BACKEND_PORT = 18018
DEFAULT_FRONTEND_PORT = 15194
BACKEND_ROUTES = ("/api/v1/", "/api/", "/v1/", "/ws/")
FRONTEND_ROUTES = ("/",)
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_OBJECT = re.compile(r"^[0-9a-f]{40,64}$")
TOOL_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")
MAX_ARCHIVE_FILES = 30_000
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
APPLE_CAPABILITY_WORKER_ENV = "KOLIBRI_APPLE_CAPABILITY_WORKER"

EXCLUDED_COMPONENTS = frozenset(
    {
        ".git",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "node_modules",
        "venv",
    }
)
EXCLUDED_RUNTIME_COMPONENTS = frozenset(
    {"artifacts", "cache", "data", "logs", "output", "test-results", "tmp"}
)
SECRET_NAMES = frozenset(
    {
        ".env",
        "auth.json",
        "cookies.json",
        "credentials.json",
        "id_ed25519",
        "id_rsa",
        "secrets.json",
        "telegram.env",
        "tokens.json",
    }
)
SECRET_SUFFIXES = (".key", ".pem", ".p12", ".pfx", ".jks")
RUNTIME_SUFFIXES = (
    ".db",
    ".db-journal",
    ".db-shm",
    ".db-wal",
    ".schema.lock",
    ".sqlite",
    ".sqlite-journal",
    ".sqlite-shm",
    ".sqlite-wal",
    ".sqlite3",
)
LOCKFILE_CANDIDATES = (
    "kolibri-v2/package-lock.json",
    "kolibri-v2/pnpm-lock.yaml",
    "kolibri-v2/yarn.lock",
    "kolibri-backend/requirements.txt",
    "kolibri-backend/requirements.lock",
    "kolibri-backend/uv.lock",
    "kolibri-backend/poetry.lock",
)


class P7ReleaseError(RuntimeError):
    """A sanitized fail-closed release error."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _apple_capability_worker_enabled() -> bool:
    return os.getenv(APPLE_CAPABILITY_WORKER_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def require_p7_release_host() -> None:
    if platform.system() == "Darwin" and not _apple_capability_worker_enabled():
        raise P7ReleaseError("p7_darwin_requires_apple_capability_worker")


@dataclasses.dataclass(frozen=True)
class Artifact:
    name: str
    sha256: str
    size_bytes: int

    def payload(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class CanonicalSnapshot:
    path: Path
    payload: dict[str, Any]
    raw: bytes
    sha256: str


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise P7ReleaseError("p7_json_not_canonicalizable") from exc


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise P7ReleaseError("p7_artifact_not_regular")
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
            after = os.fstat(stream.fileno())
    except P7ReleaseError:
        raise
    except OSError as exc:
        raise P7ReleaseError("p7_artifact_unreadable") from exc
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise P7ReleaseError("p7_artifact_changed_during_hash")
    return digest.hexdigest()


def _run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input_bytes: bytes | None = None,
    timeout: float = 120,
) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            list(command),
            cwd=cwd,
            env=env,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise P7ReleaseError("p7_required_tool_unavailable") from exc
    if result.returncode != 0:
        raise P7ReleaseError("p7_command_failed")
    return result


def _git(repo: Path, *args: str) -> bytes:
    return _run(("git", "-C", str(repo), *args), timeout=180).stdout


def require_clean_commit(repo: Path) -> tuple[str, str]:
    try:
        repo = repo.resolve(strict=True)
    except OSError as exc:
        raise P7ReleaseError("p7_repo_missing") from exc
    if _git(repo, "rev-parse", "--is-inside-work-tree").strip() != b"true":
        raise P7ReleaseError("p7_repo_not_git_worktree")
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    if status.strip():
        raise P7ReleaseError("p7_git_worktree_not_clean")
    commit = _git(repo, "rev-parse", "HEAD").decode("ascii").strip().lower()
    if not GIT_OBJECT.fullmatch(commit):
        raise P7ReleaseError("p7_git_head_invalid")
    if _git(repo, "cat-file", "-t", commit).strip() != b"commit":
        raise P7ReleaseError("p7_git_head_not_commit")
    branch = _git(repo, "branch", "--show-current").decode("utf-8").strip()
    return commit, branch or "detached"


def _validate_release_id(value: str) -> str:
    if not SAFE_ID.fullmatch(value):
        raise P7ReleaseError("p7_release_id_invalid")
    return value


def _validate_port(value: int, label: str) -> int:
    if not 1024 <= value <= 65535:
        raise P7ReleaseError(f"p7_{label}_port_invalid")
    return value


def _safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise P7ReleaseError("p7_archive_path_invalid")
    return path.as_posix()


def _excluded(relative: str) -> bool:
    parts = tuple(part.lower() for part in PurePosixPath(relative).parts)
    name = parts[-1]
    return (
        any(part in EXCLUDED_COMPONENTS for part in parts)
        or any(part in EXCLUDED_RUNTIME_COMPONENTS for part in parts)
        or name in SECRET_NAMES
        or name.startswith(".env.")
        or name.endswith(SECRET_SUFFIXES)
        or name.endswith(RUNTIME_SUFFIXES)
        or ".private." in name
    )


def _tracked_files(repo: Path, root_name: str) -> list[tuple[Path, str]]:
    safe_root = _safe_relative(root_name)
    result: list[tuple[Path, str]] = []
    try:
        values = _git(repo, "ls-files", "-z", "--", safe_root).split(b"\0")
        relative_values = [value.decode("utf-8", errors="strict") for value in values if value]
    except UnicodeDecodeError as exc:
        raise P7ReleaseError("p7_tracked_path_invalid") from exc
    for value in sorted(relative_values, key=lambda item: item.encode("utf-8")):
        relative = _safe_relative(value)
        if _excluded(relative):
            continue
        path = repo.joinpath(*PurePosixPath(relative).parts)
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise P7ReleaseError("p7_tracked_payload_missing") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise P7ReleaseError("p7_payload_symlink_forbidden")
        if not stat.S_ISREG(metadata.st_mode):
            raise P7ReleaseError("p7_payload_not_regular")
        result.append((path, relative))
    return result


def _selected_files(
    repo: Path,
    roots: Iterable[str],
    *,
    tracked_only: bool = False,
) -> list[tuple[Path, str]]:
    result: list[tuple[Path, str]] = []
    for root_name in roots:
        if tracked_only:
            result.extend(_tracked_files(repo, root_name))
            continue
        safe_root = _safe_relative(root_name)
        root = repo.joinpath(*PurePosixPath(safe_root).parts)
        if not root.is_dir() or root.is_symlink():
            raise P7ReleaseError("p7_payload_root_invalid")
        for directory, dirnames, filenames in os.walk(root, followlinks=False):
            base = Path(directory)
            retained: list[str] = []
            for name in sorted(dirnames):
                path = base / name
                if path.is_symlink():
                    raise P7ReleaseError("p7_payload_symlink_forbidden")
                if not _excluded(path.relative_to(repo).as_posix()):
                    retained.append(name)
            dirnames[:] = retained
            for name in sorted(filenames):
                path = base / name
                relative = _safe_relative(path.relative_to(repo).as_posix())
                if _excluded(relative):
                    continue
                value = path.lstat()
                if stat.S_ISLNK(value.st_mode):
                    raise P7ReleaseError("p7_payload_symlink_forbidden")
                if not stat.S_ISREG(value.st_mode):
                    raise P7ReleaseError("p7_payload_not_regular")
                result.append((path, relative))
    result.sort(key=lambda item: item[1].encode("utf-8"))
    if not result or len(result) > MAX_ARCHIVE_FILES:
        raise P7ReleaseError("p7_payload_file_count_invalid")
    if sum(path.stat().st_size for path, _ in result) > MAX_ARCHIVE_BYTES:
        raise P7ReleaseError("p7_payload_too_large")
    return result


def deterministic_tar(
    repo: Path,
    roots: Iterable[str],
    output: Path,
    *,
    tracked_only: bool = False,
) -> Artifact:
    files = _selected_files(repo, roots, tracked_only=tracked_only)
    with tarfile.open(output, "w", format=tarfile.PAX_FORMAT) as archive:
        for source, relative in files:
            info = tarfile.TarInfo(relative)
            value = source.stat()
            info.size = value.st_size
            info.mode = 0o755 if value.st_mode & 0o111 else 0o644
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with source.open("rb") as stream:
                archive.addfile(info, stream)
    return Artifact(output.name, sha256_file(output), output.stat().st_size)


def _filter_commit_archive(source: Path, output: Path, roots: Iterable[str]) -> None:
    """Copy allowed exact-commit blobs into a deterministic release archive.

    ``git archive`` is the immutable source of bytes.  The second archive pass
    applies the same secret/runtime exclusions as the previous tracked-file
    packager without falling back to mutable worktree files.
    """

    safe_roots = tuple(PurePosixPath(_safe_relative(root)) for root in roots)
    file_count = 0
    total_bytes = 0
    seen: set[str] = set()
    descriptor: int | None = None
    try:
        with tarfile.open(source, "r") as source_archive:
            selected: list[tuple[str, tarfile.TarInfo]] = []
            for member in source_archive.getmembers():
                relative = _safe_relative(member.name)
                path = PurePosixPath(relative)
                if not any(path == root or root in path.parents for root in safe_roots):
                    raise P7ReleaseError("p7_commit_archive_path_invalid")
                if member.isdir() or _excluded(relative):
                    continue
                if not member.isfile():
                    raise P7ReleaseError("p7_payload_symlink_forbidden")
                if relative in seen:
                    raise P7ReleaseError("p7_commit_archive_duplicate_path")
                seen.add(relative)
                file_count += 1
                total_bytes += member.size
                if file_count > MAX_ARCHIVE_FILES:
                    raise P7ReleaseError("p7_payload_file_count_invalid")
                if total_bytes > MAX_ARCHIVE_BYTES:
                    raise P7ReleaseError("p7_payload_too_large")
                selected.append((relative, member))

            if file_count == 0:
                raise P7ReleaseError("p7_payload_file_count_invalid")

            descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "wb") as destination_stream:
                descriptor = None
                with tarfile.open(
                    fileobj=destination_stream,
                    mode="w",
                    format=tarfile.PAX_FORMAT,
                ) as destination_archive:
                    for relative, member in sorted(
                        selected,
                        key=lambda item: item[0].encode("utf-8"),
                    ):
                        payload = source_archive.extractfile(member)
                        if payload is None:
                            raise P7ReleaseError("p7_commit_archive_invalid")
                        info = tarfile.TarInfo(relative)
                        info.size = member.size
                        info.mode = 0o755 if member.mode & 0o111 else 0o644
                        info.mtime = 0
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        with payload:
                            destination_archive.addfile(info, payload)
                destination_stream.flush()
                os.fsync(destination_stream.fileno())
    except P7ReleaseError:
        output.unlink(missing_ok=True)
        raise
    except (OSError, tarfile.TarError) as exc:
        output.unlink(missing_ok=True)
        raise P7ReleaseError("p7_commit_archive_invalid") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def deterministic_commit_tar(
    repo: Path,
    commit: str,
    roots: Iterable[str],
    output: Path,
) -> Artifact:
    """Archive exact Git blobs from ``commit`` without reading the worktree."""

    safe_roots = tuple(_safe_relative(root) for root in roots)
    if output.exists():
        raise P7ReleaseError("p7_commit_archive_unavailable")
    try:
        descriptor, raw_name = tempfile.mkstemp(
            prefix=f".{output.name}.git-archive.",
            dir=output.parent,
        )
    except OSError as exc:
        raise P7ReleaseError("p7_commit_archive_unavailable") from exc
    raw_archive = Path(raw_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            result = subprocess.run(
                (
                    "git",
                    "-C",
                    str(repo),
                    "archive",
                    "--format=tar",
                    commit,
                    "--",
                    *safe_roots,
                ),
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.PIPE,
                check=False,
                timeout=300,
            )
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, subprocess.SubprocessError) as exc:
        raw_archive.unlink(missing_ok=True)
        raise P7ReleaseError("p7_commit_archive_unavailable") from exc
    if result.returncode != 0:
        raw_archive.unlink(missing_ok=True)
        raise P7ReleaseError("p7_commit_archive_failed")
    try:
        _filter_commit_archive(raw_archive, output, safe_roots)
    finally:
        raw_archive.unlink(missing_ok=True)
    return Artifact(output.name, sha256_file(output), output.stat().st_size)


def _create_build_worktree(repo: Path, commit: str, destination: Path) -> None:
    """Materialize an isolated detached source tree at the exact release commit."""

    if destination.exists():
        raise P7ReleaseError("p7_build_snapshot_exists")
    created = False
    try:
        _git(
            repo,
            "worktree",
            "add",
            "--detach",
            "--force",
            str(destination),
            commit,
        )
        created = True
        snapshot_commit = _git(destination, "rev-parse", "HEAD").decode("ascii").strip().lower()
        if snapshot_commit != commit:
            raise P7ReleaseError("p7_build_snapshot_commit_mismatch")

        # Reuse the already locked dependency installation without copying it
        # into the release or the snapshot.  The lockfile/toolchain hashes remain
        # part of the signed manifest.
        dependencies = repo / "kolibri-v2" / "node_modules"
        snapshot_dependencies = destination / "kolibri-v2" / "node_modules"
        if dependencies.is_dir() and not dependencies.is_symlink():
            snapshot_dependencies.symlink_to(
                dependencies.resolve(strict=True),
                target_is_directory=True,
            )
    except Exception:
        if created:
            try:
                _git(repo, "worktree", "remove", "--force", str(destination))
            except P7ReleaseError:
                pass
        raise


def _remove_build_worktree(repo: Path, destination: Path) -> None:
    _git(repo, "worktree", "remove", "--force", str(destination))


def _stage_frontend_dist(build_worktree: Path, staging_root: Path) -> Path:
    """Atomically detach build output from its producer into a private snapshot."""

    source = build_worktree / "kolibri-v2" / "dist"
    if not source.is_dir() or source.is_symlink():
        raise P7ReleaseError("p7_frontend_dist_missing")
    destination = staging_root / "kolibri-v2" / "dist"
    destination.parent.mkdir(parents=True, mode=0o700)
    try:
        os.replace(source, destination)
    except OSError as exc:
        raise P7ReleaseError("p7_frontend_snapshot_failed") from exc
    return destination


def _tree_fingerprint(repo: Path, roots: Iterable[str]) -> tuple[tuple[str, int, int, str], ...]:
    """Return a stable content/mode closure and reject files changing mid-hash."""

    return tuple(
        (
            relative,
            stat.S_IMODE(path.stat().st_mode),
            path.stat().st_size,
            sha256_file(path),
        )
        for path, relative in _selected_files(repo, roots)
    )


def _frontend_build(repo: Path, release_id: str, npm_binary: str) -> None:
    environment = dict(os.environ)
    environment["VITE_KOLIBRI_RELEASE_ID"] = release_id
    _run(
        (npm_binary, "--prefix", "kolibri-v2", "run", "build"),
        cwd=repo,
        env=environment,
        timeout=900,
    )


def _tool_version(command: Sequence[str]) -> str:
    raw = _run(command, timeout=30).stdout.decode("utf-8", errors="strict").strip().splitlines()
    value = raw[0].strip() if raw else ""
    if not TOOL_VERSION.fullmatch(value):
        raise P7ReleaseError("p7_toolchain_version_invalid")
    return value


def toolchain_evidence(repo: Path, npm_binary: str) -> dict[str, Any]:
    python_version = platform.python_version()
    if not TOOL_VERSION.fullmatch(python_version):
        raise P7ReleaseError("p7_toolchain_version_invalid")
    lockfiles: dict[str, dict[str, Any]] = {}
    tracked = set(
        _git(repo, "ls-files", "--", *LOCKFILE_CANDIDATES)
        .decode("utf-8", errors="strict")
        .splitlines()
    )
    for relative in LOCKFILE_CANDIDATES:
        path = repo / relative
        if relative in tracked and path.is_file() and not path.is_symlink():
            lockfiles[relative] = {
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
    return {
        "python": python_version,
        "node": _tool_version(("node", "--version")),
        "npm": _tool_version((npm_binary, "--version")),
        "lockfiles": lockfiles,
    }


def _require_frontend_release_marker(dist: Path, release_id: str) -> None:
    marker = release_id.encode("utf-8")
    if not dist.is_dir():
        raise P7ReleaseError("p7_frontend_dist_missing")
    found = False
    for path in sorted(dist.rglob("*")):
        if path.is_symlink():
            raise P7ReleaseError("p7_frontend_dist_symlink_forbidden")
        if path.is_file() and path.stat().st_size <= 32 * 1024 * 1024:
            with path.open("rb") as stream:
                if marker in stream.read():
                    found = True
                    break
    if not found:
        raise P7ReleaseError("p7_frontend_release_identity_missing")


def _create_source_bundle(repo: Path, output: Path, commit: str) -> Artifact:
    _git(repo, "bundle", "create", str(output), "HEAD")
    _git(repo, "bundle", "verify", str(output))
    heads = _git(repo, "bundle", "list-heads", str(output)).decode("utf-8").splitlines()
    if not any(line.split(maxsplit=1)[0].lower() == commit for line in heads if line.strip()):
        raise P7ReleaseError("p7_source_bundle_commit_missing")
    return Artifact(output.name, sha256_file(output), output.stat().st_size)


def functional_gate_contract() -> list[dict[str, Any]]:
    return [
        {
            "id": "release_identity",
            "required": True,
            "assertions": [
                "backend_health_release_id_matches",
                "backend_x_kolibri_release_matches",
                "frontend_build_release_id_matches",
            ],
        },
        {
            "id": "estimate_create_regional",
            "required": True,
            "route": "POST /api/v1/estimates",
            "assertions": [
                "http_201",
                "individualized_scope",
                "no_fixed_template_reuse",
                "truth_status_present",
            ],
        },
        {
            "id": "estimate_recalculate",
            "required": True,
            "route": "PUT /api/v1/estimates/{id} with If-Match",
            "assertions": [
                "http_200",
                "server_decimal_recalculation",
                "version_incremented",
                "changed_total_persisted",
            ],
        },
        {
            "id": "estimate_revisions",
            "required": True,
            "route": "GET /api/v1/estimates/{id}/revisions",
            "assertions": ["http_200", "at_least_two_revisions", "previous_revision_immutable"],
        },
        {
            "id": "estimate_pdf",
            "required": True,
            "route": "GET /api/v1/estimates/{id}/pdf?version={version}",
            "assertions": [
                "http_200",
                "content_type_application_pdf",
                "pdf_magic_bytes",
                "nonempty_sha256_bound_bytes",
            ],
        },
        {
            "id": "capability_registry",
            "required": True,
            "route": "GET /v1/capabilities",
            "assertions": [
                "http_200",
                "dynamic_backend_registry",
                "tri_state_statuses",
                "invocable_requires_live_probe",
                "release_identity_matches",
            ],
        },
        {
            "id": "chat_durable_stream",
            "required": True,
            "route": "POST /v1/responses + events/cancel/retry + project reload",
            "assertions": [
                "first_delta_observed",
                "terminal_completed",
                "history_persisted_after_reload",
                "cancel_terminal",
                "retry_completed_without_duplicate_assistant",
            ],
        },
        {
            "id": "web_search_sources",
            "required": True,
            "route": "POST /v1/tools/invoke (web.search)",
            "assertions": [
                "http_200",
                "real_provider_invocation",
                "dated_sources_with_https_urls",
                "persisted_result_reopened",
            ],
        },
        {
            "id": "file_lifecycle",
            "required": True,
            "route": "upload -> analyze -> search -> reopen/download",
            "assertions": [
                "uploaded_bytes_hash_matches",
                "analysis_artifact_persisted",
                "search_finds_uploaded_content",
                "reopened_bytes_hash_matches",
            ],
        },
        {
            "id": "document_artifacts",
            "required": True,
            "route": "POST /v1/tools/invoke (PDF/DOCX/XLSX/PPTX)",
            "assertions": [
                "all_four_formats_created",
                "mime_magic_and_sha256_verified",
                "download_bytes_match",
                "reopen_bytes_match",
            ],
        },
        {
            "id": "image_lifecycle",
            "required": True,
            "route": "generate -> edit -> persist -> render/download -> reopen",
            "assertions": [
                "provider_tool_invoked",
                "raster_bytes_verified",
                "edited_artifact_is_distinct",
                "download_and_reopen_hash_match",
            ],
        },
        {
            "id": "site_app_lifecycle",
            "required": True,
            "route": "site.create/app.create -> ZIP -> sandbox preview -> reopen/download",
            "assertions": [
                "site_and_app_archives_verified",
                "preview_http_200_html",
                "download_and_reopen_hash_match",
                "sandbox_headers_verified",
            ],
        },
        {
            "id": "developer_api_keys",
            "required": True,
            "route": "create -> use -> list-without-secret -> revoke -> reject",
            "assertions": [
                "secret_shown_once",
                "created_key_authorizes_request",
                "stored_listing_has_no_secret",
                "revoked_key_is_rejected",
            ],
        },
        {
            "id": "structured_apis",
            "required": True,
            "route": "Responses + Chat Completions streaming and structured JSON",
            "assertions": [
                "responses_stream_valid",
                "chat_stream_valid",
                "structured_json_schema_valid",
                "public_model_is_kolibri",
            ],
        },
        {
            "id": "shell_desktop_mobile",
            "required": True,
            "route": "browser E2E at 1440x900, 390x844 and 360x800",
            "assertions": [
                "zero_console_errors",
                "zero_unexplained_network_failures",
                "all_visible_controls_actionable",
                "mobile_no_horizontal_overflow",
                "reload_reopens_chat_files_images_and_artifacts",
            ],
        },
        {
            "id": "optional_capability_gates",
            "required": True,
            "route": "capability registry + visible tool menu",
            "assertions": [
                "unavailable_capabilities_hidden",
                "degraded_capabilities_have_technical_reason",
                "external_integrations_require_owner_auth",
                "no_placeholder_or_fake_success",
            ],
        },
    ]


def _targets(backend_port: int, frontend_port: int) -> dict[str, Any]:
    backend = f"http://127.0.0.1:{backend_port}"
    frontend = f"http://127.0.0.1:{frontend_port}"
    return {
        "backend": {
            "port": backend_port,
            "origin": backend,
            "service": "kolibri-backend-p7.service",
            "routes": {route: backend for route in BACKEND_ROUTES},
        },
        "frontend": {
            "port": frontend_port,
            "origin": frontend,
            "service": "kolibri-frontend-p7.service",
            "routes": {route: frontend for route in FRONTEND_ROUTES},
        },
    }


def _artifact(path: Path) -> Artifact:
    return Artifact(path.name, sha256_file(path), path.stat().st_size)


def _signature_environment() -> dict[str, str]:
    result = {key: value for key, value in os.environ.items() if key in {"HOME", "LANG", "LC_ALL", "PATH", "TMPDIR"}}
    result["SSH_ASKPASS_REQUIRE"] = "never"
    result.pop("DISPLAY", None)
    return result


def _require_executable(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise P7ReleaseError("p7_signature_tool_unavailable")
    return path


def _require_pinned_trust_root(path: Path) -> Path:
    if not path.is_absolute():
        raise P7ReleaseError("p7_trust_root_not_pinned")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise P7ReleaseError("p7_trust_root_missing") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != TRUST_ROOT_REQUIRED_UID
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise P7ReleaseError("p7_trust_root_permissions_invalid")
    return path


def _verify_pinned_signature(
    content_bytes: bytes,
    signature_path: Path,
    *,
    trust_root: Path,
    signer_identity: str,
    namespace: str,
    ssh_keygen: str | None = None,
) -> None:
    allowed_signers = _require_pinned_trust_root(trust_root)
    if not signature_path.is_file() or signature_path.is_symlink():
        raise P7ReleaseError("p7_signature_material_missing")
    binary = ssh_keygen or _require_executable("ssh-keygen")
    try:
        result = subprocess.run(
            (
                binary,
                "-Y",
                "verify",
                "-f",
                str(allowed_signers),
                "-I",
                signer_identity,
                "-n",
                namespace,
                "-s",
                str(signature_path),
            ),
            input=content_bytes,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=_signature_environment(),
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise P7ReleaseError("p7_signature_verification_unavailable") from exc
    if result.returncode != 0:
        raise P7ReleaseError("p7_signature_verification_failed")


def verify_owner_signature(
    content_bytes: bytes,
    signature_path: Path,
    *,
    namespace: str,
    ssh_keygen: str | None = None,
) -> None:
    _verify_pinned_signature(
        content_bytes,
        signature_path,
        trust_root=OWNER_TRUST_ROOT,
        signer_identity=OWNER_SIGNER_IDENTITY,
        namespace=namespace,
        ssh_keygen=ssh_keygen,
    )


def verify_collector_signature(
    content_bytes: bytes,
    signature_path: Path,
    *,
    namespace: str,
    ssh_keygen: str | None = None,
) -> None:
    _verify_pinned_signature(
        content_bytes,
        signature_path,
        trust_root=COLLECTOR_TRUST_ROOT,
        signer_identity=COLLECTOR_SIGNER_IDENTITY,
        namespace=namespace,
        ssh_keygen=ssh_keygen,
    )


def sign_and_verify(
    manifest_path: Path,
    *,
    manifest_bytes: bytes,
    signing_key: Path,
    ssh_keygen: str | None = None,
) -> Path:
    binary = ssh_keygen or _require_executable("ssh-keygen")
    if not signing_key.is_file() or stat.S_IMODE(signing_key.stat().st_mode) & 0o077:
        raise P7ReleaseError("p7_signing_key_permissions_invalid")
    signature = Path(f"{manifest_path}.sig")
    try:
        result = subprocess.run(
            (
                binary,
                "-Y",
                "sign",
                "-f",
                str(signing_key),
                "-n",
                RELEASE_SIGNATURE_NAMESPACE,
                str(manifest_path),
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=_signature_environment(),
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise P7ReleaseError("p7_signature_tool_unavailable") from exc
    if result.returncode != 0 or not signature.is_file():
        raise P7ReleaseError("p7_manifest_signing_failed")
    verify_owner_signature(
        manifest_bytes,
        signature,
        namespace=RELEASE_SIGNATURE_NAMESPACE,
        ssh_keygen=binary,
    )
    return signature


def _write_exclusive(path: Path, value: bytes, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def build_release(
    *,
    repo: Path,
    output_root: Path,
    release_id: str,
    backend_port: int = DEFAULT_BACKEND_PORT,
    frontend_port: int = DEFAULT_FRONTEND_PORT,
    npm_binary: str = "npm",
    frontend_builder: Callable[[Path, str, str], None] | None = None,
    signing_key: Path | None = None,
    ssh_keygen: str | None = None,
) -> dict[str, Any]:
    require_p7_release_host()
    release_id = _validate_release_id(release_id)
    backend_port = _validate_port(backend_port, "backend")
    frontend_port = _validate_port(frontend_port, "frontend")
    if backend_port == frontend_port:
        raise P7ReleaseError("p7_target_ports_must_differ")
    commit, branch = require_clean_commit(repo)
    repo = repo.resolve()
    output_root = output_root.resolve()
    final = output_root / release_id
    if final.exists():
        raise P7ReleaseError("p7_release_output_exists")
    output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = Path(tempfile.mkdtemp(prefix=f".{release_id}.", dir=output_root))
    published = False
    build_worktree = temporary / ".source-worktree"
    frontend_staging = temporary / ".frontend-snapshot"
    try:
        source = _create_source_bundle(repo, temporary / "source.bundle", commit)
        _create_build_worktree(repo, commit, build_worktree)
        try:
            (frontend_builder or _frontend_build)(build_worktree, release_id, npm_binary)
            staged_dist = _stage_frontend_dist(build_worktree, frontend_staging)
            _require_frontend_release_marker(staged_dist, release_id)
        finally:
            _remove_build_worktree(repo, build_worktree)
        # The source closure must remain exactly the clean commit after build.
        after_commit, _ = require_clean_commit(repo)
        if after_commit != commit:
            raise P7ReleaseError("p7_git_head_changed_during_build")
        backend = deterministic_commit_tar(
            repo,
            commit,
            ("kolibri-backend",),
            temporary / "backend.tar",
        )
        frontend_before = _tree_fingerprint(frontend_staging, ("kolibri-v2/dist",))
        frontend = deterministic_tar(
            frontend_staging,
            ("kolibri-v2/dist",),
            temporary / "frontend.tar",
        )
        if _tree_fingerprint(frontend_staging, ("kolibri-v2/dist",)) != frontend_before:
            raise P7ReleaseError("p7_frontend_snapshot_changed_during_archive")
        shutil.rmtree(frontend_staging)
        artifacts = [source, backend, frontend]
        targets = _targets(backend_port, frontend_port)
        toolchain = toolchain_evidence(repo, npm_binary)
        # This is the final read from the mutable source worktree.  From here on
        # the manifest references only commit-bound or private snapshot bytes.
        final_commit, _ = require_clean_commit(repo)
        if final_commit != commit:
            raise P7ReleaseError("p7_git_head_changed_during_archive")
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "release_id": release_id,
            "source": {
                "commit": commit,
                "branch": branch,
                "worktree_clean": True,
                "git_bundle": source.name,
                "git_bundle_sha256": source.sha256,
            },
            "release_identity": {
                "backend_environment": {"KOLIBRI_RELEASE_ID": release_id},
                "frontend_build_environment": {"VITE_KOLIBRI_RELEASE_ID": release_id},
                "required_response_header": {"X-Kolibri-Release": release_id},
                "paired_identity_required": True,
            },
            "runtime_requirements": {
                "required_backend_secret_names": [
                    "JWT_SECRET_KEY",
                    "KOLIBRI_EVIDENCE_SIGNING_KEY",
                ],
                "secret_values_forbidden_in_manifest": True,
                "minimum_secret_bytes": 32,
            },
            "artifacts": [item.payload() for item in artifacts],
            "toolchain": toolchain,
            "targets": targets,
            "functional_gates": functional_gate_contract(),
            "activation_policy": {
                "owner_approval_required": True,
                "detached_signature_required": True,
                "atomic_paired_switch_required": True,
                "automatic_rollback_required": True,
                "tool_can_apply": False,
            },
        }
        manifest_path = temporary / "release-manifest.json"
        manifest_bytes = canonical_json(manifest) + b"\n"
        _write_exclusive(manifest_path, manifest_bytes)
        signature_path: Path | None = None
        if signing_key is not None:
            signature_path = sign_and_verify(
                manifest_path,
                manifest_bytes=manifest_bytes,
                signing_key=signing_key,
                ssh_keygen=ssh_keygen,
            )
        manifest_sha = sha256_bytes(manifest_bytes)
        checksums = [
            f"{item.sha256}  {item.name}" for item in artifacts
        ] + [f"{manifest_sha}  {manifest_path.name}"]
        if signature_path is not None:
            checksums.append(f"{sha256_file(signature_path)}  {signature_path.name}")
        _write_exclusive(temporary / "SHA256SUMS", ("\n".join(checksums) + "\n").encode("utf-8"))
        os.replace(temporary, final)
        published = True
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "built_signed" if signature_path else "built_unsigned_candidate",
            "release_id": release_id,
            "source_commit": commit,
            "manifest_sha256": manifest_sha,
            "release_dir": str(final),
            "signature_verified": signature_path is not None,
            "production_applied": False,
        }
    finally:
        if not published:
            shutil.rmtree(temporary, ignore_errors=True)


def _read_canonical_snapshot(path: Path, code: str) -> CanonicalSnapshot:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise P7ReleaseError(code) from exc
    if not isinstance(payload, dict) or raw != canonical_json(payload) + b"\n":
        raise P7ReleaseError(code)
    return CanonicalSnapshot(path=path, payload=payload, raw=raw, sha256=sha256_bytes(raw))


def load_manifest_snapshot(release_dir: Path) -> CanonicalSnapshot:
    manifest_path = release_dir / "release-manifest.json"
    snapshot = _read_canonical_snapshot(manifest_path, "p7_manifest_unreadable")
    payload = snapshot.payload
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise P7ReleaseError("p7_manifest_schema_invalid")
    _validate_release_id(str(payload.get("release_id") or ""))
    validate_manifest_contract(payload)
    return snapshot


def load_manifest(release_dir: Path) -> tuple[dict[str, Any], Path, str]:
    snapshot = load_manifest_snapshot(release_dir)
    return snapshot.payload, snapshot.path, snapshot.sha256


def validate_manifest_contract(payload: dict[str, Any]) -> None:
    release_id = str(payload.get("release_id") or "")
    identity = payload.get("release_identity")
    if not isinstance(identity, dict) or identity != {
        "backend_environment": {"KOLIBRI_RELEASE_ID": release_id},
        "frontend_build_environment": {"VITE_KOLIBRI_RELEASE_ID": release_id},
        "paired_identity_required": True,
        "required_response_header": {"X-Kolibri-Release": release_id},
    }:
        raise P7ReleaseError("p7_manifest_release_identity_invalid")
    if payload.get("runtime_requirements") != {
        "required_backend_secret_names": [
            "JWT_SECRET_KEY",
            "KOLIBRI_EVIDENCE_SIGNING_KEY",
        ],
        "secret_values_forbidden_in_manifest": True,
        "minimum_secret_bytes": 32,
    }:
        raise P7ReleaseError("p7_manifest_runtime_requirements_invalid")
    targets = payload.get("targets")
    if not isinstance(targets, dict):
        raise P7ReleaseError("p7_manifest_targets_invalid")
    backend = targets.get("backend") if isinstance(targets.get("backend"), dict) else {}
    frontend = targets.get("frontend") if isinstance(targets.get("frontend"), dict) else {}
    backend_port = backend.get("port")
    frontend_port = frontend.get("port")
    if not isinstance(backend_port, int) or not isinstance(frontend_port, int):
        raise P7ReleaseError("p7_manifest_targets_invalid")
    _validate_port(backend_port, "backend")
    _validate_port(frontend_port, "frontend")
    if backend_port == frontend_port:
        raise P7ReleaseError("p7_target_ports_must_differ")
    if targets != _targets(backend_port, frontend_port):
        raise P7ReleaseError("p7_manifest_routes_invalid")
    if payload.get("functional_gates") != functional_gate_contract():
        raise P7ReleaseError("p7_manifest_functional_gates_invalid")
    toolchain = payload.get("toolchain")
    if not isinstance(toolchain, dict) or set(toolchain) != {"python", "node", "npm", "lockfiles"}:
        raise P7ReleaseError("p7_manifest_toolchain_invalid")
    if any(not TOOL_VERSION.fullmatch(str(toolchain.get(key) or "")) for key in ("python", "node", "npm")):
        raise P7ReleaseError("p7_manifest_toolchain_invalid")
    lockfiles = toolchain.get("lockfiles")
    if not isinstance(lockfiles, dict):
        raise P7ReleaseError("p7_manifest_lockfiles_invalid")
    for relative, record in lockfiles.items():
        if (
            relative not in LOCKFILE_CANDIDATES
            or not isinstance(record, dict)
            or set(record) != {"sha256", "size_bytes"}
            or not SHA256.fullmatch(str(record.get("sha256") or ""))
            or not isinstance(record.get("size_bytes"), int)
            or record["size_bytes"] < 0
        ):
            raise P7ReleaseError("p7_manifest_lockfiles_invalid")
    policy = payload.get("activation_policy")
    if not isinstance(policy, dict) or any(
        policy.get(key) is not True
        for key in (
            "owner_approval_required",
            "detached_signature_required",
            "atomic_paired_switch_required",
            "automatic_rollback_required",
        )
    ) or policy.get("tool_can_apply") is not False:
        raise P7ReleaseError("p7_manifest_activation_policy_invalid")
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise P7ReleaseError("p7_manifest_artifacts_invalid")
    artifact_map = {
        str(record.get("name") or ""): record
        for record in artifacts
        if isinstance(record, dict)
    }
    if set(artifact_map) != {"source.bundle", "backend.tar", "frontend.tar"}:
        raise P7ReleaseError("p7_manifest_artifact_set_invalid")
    if (
        source.get("worktree_clean") is not True
        or source.get("git_bundle") != "source.bundle"
        or source.get("git_bundle_sha256") != artifact_map["source.bundle"].get("sha256")
    ):
        raise P7ReleaseError("p7_manifest_source_binding_invalid")


def _verify_release_snapshot(
    release_dir: Path,
    *,
    repo: Path | None = None,
    require_signature: bool = False,
    signature_path: Path | None = None,
    ssh_keygen: str | None = None,
) -> tuple[dict[str, Any], CanonicalSnapshot]:
    snapshot = load_manifest_snapshot(release_dir)
    manifest = snapshot.payload
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise P7ReleaseError("p7_manifest_artifacts_invalid")
    seen: set[str] = set()
    for record in artifacts:
        if not isinstance(record, dict):
            raise P7ReleaseError("p7_manifest_artifact_invalid")
        name = _safe_relative(str(record.get("name") or ""))
        if "/" in name or name in seen:
            raise P7ReleaseError("p7_manifest_artifact_name_invalid")
        seen.add(name)
        path = release_dir / name
        expected_size = record.get("size_bytes")
        expected_sha = str(record.get("sha256") or "")
        if (
            not path.is_file()
            or not isinstance(expected_size, int)
            or path.stat().st_size != expected_size
            or not SHA256.fullmatch(expected_sha)
            or sha256_file(path) != expected_sha
        ):
            raise P7ReleaseError("p7_artifact_integrity_failed")
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    commit = str(source.get("commit") or "")
    if not GIT_OBJECT.fullmatch(commit):
        raise P7ReleaseError("p7_manifest_source_commit_invalid")
    bundle = release_dir / str(source.get("git_bundle") or "")
    if repo is not None:
        _git(repo, "bundle", "verify", str(bundle))
        heads = _git(repo, "bundle", "list-heads", str(bundle)).decode("utf-8").splitlines()
        if not any(line.split(maxsplit=1)[0].lower() == commit for line in heads if line.strip()):
            raise P7ReleaseError("p7_bundle_source_commit_mismatch")
    signature_requested = signature_path is not None
    if require_signature and not signature_requested:
        raise P7ReleaseError("p7_signature_required")
    verified = False
    if signature_requested:
        verify_owner_signature(
            snapshot.raw,
            signature_path,  # type: ignore[arg-type]
            namespace=RELEASE_SIGNATURE_NAMESPACE,
            ssh_keygen=ssh_keygen,
        )
        verified = True
    result = {
        "status": "verified",
        "release_id": manifest["release_id"],
        "source_commit": commit,
        "manifest_sha256": snapshot.sha256,
        "artifact_count": len(artifacts),
        "signature_verified": verified,
        "production_applied": False,
    }
    return result, snapshot


def verify_release(
    release_dir: Path,
    *,
    repo: Path | None = None,
    require_signature: bool = False,
    signature_path: Path | None = None,
    ssh_keygen: str | None = None,
) -> dict[str, Any]:
    require_p7_release_host()
    result, _snapshot = _verify_release_snapshot(
        release_dir,
        repo=repo,
        require_signature=require_signature,
        signature_path=signature_path,
        ssh_keygen=ssh_keygen,
    )
    return result


def _validate_collector_binding(
    payload: dict[str, Any],
    manifest: dict[str, Any],
    manifest_sha: str,
) -> None:
    collector = payload.get("collector")
    if not isinstance(collector, dict) or set(collector) != {
        "identity",
        "implementation",
        "version",
        "run_id",
        "target",
    }:
        raise P7ReleaseError("p7_collector_binding_invalid")
    if (
        collector.get("identity") != COLLECTOR_SIGNER_IDENTITY
        or collector.get("implementation") != "kolibri-p7-gate-collector"
        or not TOOL_VERSION.fullmatch(str(collector.get("version") or ""))
        or not SAFE_ID.fullmatch(str(collector.get("run_id") or ""))
    ):
        raise P7ReleaseError("p7_collector_binding_invalid")
    targets = manifest["targets"]
    expected_target = {
        "release_id": manifest["release_id"],
        "manifest_sha256": manifest_sha,
        "backend_origin": targets["backend"]["origin"],
        "frontend_origin": targets["frontend"]["origin"],
    }
    if collector.get("target") != expected_target:
        raise P7ReleaseError("p7_collector_target_mismatch")


def _validate_gate_payload(
    evidence: dict[str, Any],
    manifest: dict[str, Any],
    manifest_sha: str,
    evidence_sha: str,
) -> dict[str, Any]:
    if evidence.get("schema_version") != GATE_SCHEMA_VERSION:
        raise P7ReleaseError("p7_gate_evidence_schema_invalid")
    if evidence.get("release_id") != manifest.get("release_id"):
        raise P7ReleaseError("p7_gate_release_identity_mismatch")
    if evidence.get("manifest_sha256") != manifest_sha:
        raise P7ReleaseError("p7_gate_manifest_binding_mismatch")
    _validate_collector_binding(evidence, manifest, manifest_sha)
    results = evidence.get("results")
    if not isinstance(results, dict):
        raise P7ReleaseError("p7_gate_results_invalid")
    required = {item["id"] for item in functional_gate_contract() if item["required"]}
    if set(results) != required:
        raise P7ReleaseError("p7_gate_results_incomplete")
    for gate_id, value in results.items():
        if not isinstance(value, dict) or value.get("status") != "passed":
            raise P7ReleaseError(f"p7_gate_{gate_id}_failed")
    release_id = manifest["release_id"]
    identity = results["release_identity"]
    if any(identity.get(key) != release_id for key in ("backend_release_id", "frontend_release_id", "response_header_release_id")):
        raise P7ReleaseError("p7_gate_release_identity_failed")
    created = results["estimate_create_regional"]
    if (
        created.get("http_status") != 201
        or not str(created.get("estimate_id") or "")
        or created.get("individualized_scope") is not True
        or created.get("template_reuse_detected") is not False
        or created.get("truth_status") not in {"source_backed", "verified"}
        or int(created.get("evidence_count") or 0) < 1
    ):
        raise P7ReleaseError("p7_gate_estimate_create_failed")
    recalculated = results["estimate_recalculate"]
    if (
        recalculated.get("http_status") != 200
        or recalculated.get("server_decimal_recalculation") is not True
        or not isinstance(recalculated.get("version_before"), int)
        or not isinstance(recalculated.get("version_after"), int)
        or recalculated["version_after"] <= recalculated["version_before"]
        or str(recalculated.get("total_after") or "") == str(recalculated.get("total_before") or "")
        or recalculated.get("persisted_after_reload") is not True
    ):
        raise P7ReleaseError("p7_gate_estimate_recalculation_failed")
    revisions = results["estimate_revisions"]
    if revisions.get("http_status") != 200 or int(revisions.get("revision_count") or 0) < 2 or revisions.get("previous_revision_immutable") is not True:
        raise P7ReleaseError("p7_gate_estimate_revisions_failed")
    pdf = results["estimate_pdf"]
    if (
        pdf.get("http_status") != 200
        or pdf.get("content_type") != "application/pdf"
        or pdf.get("magic") != "%PDF-"
        or int(pdf.get("size_bytes") or 0) <= 1024
        or not SHA256.fullmatch(str(pdf.get("sha256") or ""))
    ):
        raise P7ReleaseError("p7_gate_estimate_pdf_failed")

    registry = results["capability_registry"]
    if (
        registry.get("http_status") != 200
        or registry.get("source") != "backend_runtime_registry"
        or registry.get("release_id") != release_id
        or registry.get("release_bound") is not True
        or int(registry.get("probe_ttl_seconds") or 0) < 7 * 60 * 60
        or registry.get("statuses") != ["available", "degraded", "unavailable"]
        or registry.get("invocable_requires_live_probe") is not True
        or int(registry.get("capability_count") or 0) < 10
    ):
        raise P7ReleaseError("p7_gate_capability_registry_failed")

    chat = results["chat_durable_stream"]
    if (
        chat.get("create_http_status") not in {200, 201}
        or int(chat.get("text_delta_count") or 0) < 1
        or chat.get("terminal_state") != "completed"
        or chat.get("history_persisted_after_reload") is not True
        or chat.get("cancel_terminal_state") != "cancelled"
        or chat.get("retry_terminal_state") != "completed"
        or chat.get("duplicate_assistant_detected") is not False
        or not SAFE_ID.fullmatch(str(chat.get("project_id") or ""))
        or not SAFE_ID.fullmatch(str(chat.get("response_id") or ""))
    ):
        raise P7ReleaseError("p7_gate_chat_durable_stream_failed")

    web = results["web_search_sources"]
    sources = web.get("sources")
    if (
        web.get("http_status") != 200
        or web.get("provider_invoked") is not True
        or web.get("persisted_after_reload") is not True
        or not isinstance(sources, list)
        or not sources
        or any(
            not isinstance(source, dict)
            or not str(source.get("url") or "").startswith("https://")
            or not str(source.get("title") or "").strip()
            or not str(source.get("retrieved_at") or "").strip()
            for source in sources
        )
    ):
        raise P7ReleaseError("p7_gate_web_search_sources_failed")

    files = results["file_lifecycle"]
    file_sha = str(files.get("upload_sha256") or "")
    if (
        files.get("upload_http_status") != 201
        or not SHA256.fullmatch(file_sha)
        or files.get("analysis_http_status") != 201
        or not SHA256.fullmatch(str(files.get("analysis_sha256") or ""))
        or files.get("search_http_status") != 200
        or files.get("search_found_uploaded_content") is not True
        or files.get("reopen_http_status") != 200
        or files.get("download_http_status") != 200
        or files.get("reopen_sha256") != file_sha
        or files.get("download_sha256") != file_sha
    ):
        raise P7ReleaseError("p7_gate_file_lifecycle_failed")

    documents = results["document_artifacts"]
    document_formats = documents.get("formats")
    expected_document_formats = {
        "pdf": ("application/pdf", "%PDF-"),
        "docx": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "PK",
        ),
        "xlsx": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "PK",
        ),
        "pptx": (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "PK",
        ),
    }
    if not isinstance(document_formats, dict) or set(document_formats) != set(expected_document_formats):
        raise P7ReleaseError("p7_gate_document_artifacts_failed")
    for format_id, (mime_type, magic) in expected_document_formats.items():
        artifact = document_formats[format_id]
        sha = str(artifact.get("sha256") or "") if isinstance(artifact, dict) else ""
        if (
            not isinstance(artifact, dict)
            or artifact.get("http_status") not in {200, 201}
            or artifact.get("mime_type") != mime_type
            or artifact.get("magic") != magic
            or int(artifact.get("size_bytes") or 0) <= 256
            or not SHA256.fullmatch(sha)
            or artifact.get("download_sha256") != sha
            or artifact.get("reopen_sha256") != sha
        ):
            raise P7ReleaseError("p7_gate_document_artifacts_failed")

    image = results["image_lifecycle"]
    generated_sha = str(image.get("generated_sha256") or "")
    edited_sha = str(image.get("edited_sha256") or "")
    if (
        image.get("generate_http_status") not in {200, 201}
        or image.get("edit_http_status") not in {200, 201}
        or image.get("provider_tool_invoked") is not True
        or image.get("mime_type") not in {"image/png", "image/jpeg", "image/webp"}
        or int(image.get("width") or 0) < 64
        or int(image.get("height") or 0) < 64
        or not SHA256.fullmatch(generated_sha)
        or not SHA256.fullmatch(edited_sha)
        or edited_sha == generated_sha
        or image.get("download_sha256") != edited_sha
        or image.get("reopen_sha256") != edited_sha
        or image.get("rendered_in_shell") is not True
    ):
        raise P7ReleaseError("p7_gate_image_lifecycle_failed")

    projects = results["site_app_lifecycle"]
    project_artifacts = projects.get("artifacts")
    if not isinstance(project_artifacts, dict) or set(project_artifacts) != {"site", "app"}:
        raise P7ReleaseError("p7_gate_site_app_lifecycle_failed")
    for artifact in project_artifacts.values():
        sha = str(artifact.get("sha256") or "") if isinstance(artifact, dict) else ""
        if (
            not isinstance(artifact, dict)
            or artifact.get("http_status") not in {200, 201}
            or artifact.get("mime_type") != "application/zip"
            or artifact.get("magic") != "PK"
            or int(artifact.get("size_bytes") or 0) <= 256
            or not SHA256.fullmatch(sha)
            or artifact.get("preview_http_status") != 200
            or artifact.get("preview_content_type") != "text/html"
            or artifact.get("sandbox_headers_verified") is not True
            or artifact.get("download_sha256") != sha
            or artifact.get("reopen_sha256") != sha
        ):
            raise P7ReleaseError("p7_gate_site_app_lifecycle_failed")

    keys = results["developer_api_keys"]
    if (
        keys.get("create_http_status") != 201
        or keys.get("secret_shown_once") is not True
        or keys.get("created_key_request_http_status") != 200
        or keys.get("list_http_status") != 200
        or keys.get("secret_present_in_list") is not False
        or keys.get("revoke_http_status") != 200
        or keys.get("revoked_key_request_http_status") not in {401, 403}
    ):
        raise P7ReleaseError("p7_gate_developer_api_keys_failed")

    structured = results["structured_apis"]
    if (
        structured.get("responses_http_status") != 200
        or structured.get("responses_stream_valid") is not True
        or structured.get("chat_http_status") != 200
        or structured.get("chat_stream_valid") is not True
        or structured.get("structured_json_schema_valid") is not True
        or structured.get("model") != "kolibri"
    ):
        raise P7ReleaseError("p7_gate_structured_apis_failed")

    shell = results["shell_desktop_mobile"]
    viewports = shell.get("viewports")
    if (
        not isinstance(viewports, dict)
        or set(viewports)
        != {"desktop_1440", "tablet_768", "mobile_390", "mobile_360"}
        or any(
            not isinstance(value, dict)
            or value.get("status") != "passed"
            or int(value.get("console_errors") or 0) != 0
            or int(value.get("unexplained_failed_requests") or 0) != 0
            or value.get("visible_controls_actionable") is not True
            or value.get("horizontal_overflow") is not False
            for viewport_id, value in viewports.items()
        )
        or shell.get("reload_reopens_all_artifact_types") is not True
    ):
        raise P7ReleaseError("p7_gate_shell_desktop_mobile_failed")

    optional = results["optional_capability_gates"]
    if (
        optional.get("unavailable_capabilities_hidden") is not True
        or optional.get("degraded_reasons_are_technical") is not True
        or optional.get("external_integrations_owner_gated") is not True
        or optional.get("placeholder_or_fake_success_detected") is not False
    ):
        raise P7ReleaseError("p7_gate_optional_capability_gates_failed")
    return {
        "schema_version": GATE_SCHEMA_VERSION,
        "status": "verified",
        "release_id": release_id,
        "manifest_sha256": manifest_sha,
        "evidence_sha256": evidence_sha,
        "collector_identity": COLLECTOR_SIGNER_IDENTITY,
        "collector_run_id": evidence["collector"]["run_id"],
        "collector_signature_verified": True,
        "gates": sorted(required),
    }


def verify_gate_evidence(
    evidence_path: Path,
    signature_path: Path,
    manifest: dict[str, Any],
    manifest_sha: str,
    *,
    ssh_keygen: str | None = None,
) -> dict[str, Any]:
    require_p7_release_host()
    snapshot = _read_canonical_snapshot(evidence_path, "p7_gate_evidence_unreadable")
    verify_collector_signature(
        snapshot.raw,
        signature_path,
        namespace=GATE_SIGNATURE_NAMESPACE,
        ssh_keygen=ssh_keygen,
    )
    return _validate_gate_payload(
        snapshot.payload,
        manifest,
        manifest_sha,
        snapshot.sha256,
    )


def verify_rollback_health_evidence(
    evidence_path: Path,
    signature_path: Path,
    manifest: dict[str, Any],
    manifest_sha: str,
    previous_route_config_sha256: str,
    *,
    ssh_keygen: str | None = None,
) -> dict[str, Any]:
    require_p7_release_host()
    snapshot = _read_canonical_snapshot(evidence_path, "p7_rollback_health_evidence_invalid")
    evidence = snapshot.payload
    verify_collector_signature(
        snapshot.raw,
        signature_path,
        namespace=ROLLBACK_HEALTH_SIGNATURE_NAMESPACE,
        ssh_keygen=ssh_keygen,
    )
    if (
        evidence.get("schema_version") != ROLLBACK_HEALTH_SCHEMA_VERSION
        or evidence.get("release_id") != manifest.get("release_id")
        or evidence.get("manifest_sha256") != manifest_sha
        or evidence.get("route_config_sha256") != previous_route_config_sha256
    ):
        raise P7ReleaseError("p7_rollback_health_binding_mismatch")
    _validate_collector_binding(evidence, manifest, manifest_sha)
    results = evidence.get("results")
    if not isinstance(results, dict) or set(results) != {
        "release_identity",
        "backend_health",
        "frontend_health",
        "routes",
    }:
        raise P7ReleaseError("p7_rollback_health_results_invalid")
    if any(not isinstance(value, dict) or value.get("status") != "passed" for value in results.values()):
        raise P7ReleaseError("p7_rollback_health_failed")
    release_id = manifest["release_id"]
    identity = results["release_identity"]
    if any(identity.get(key) != release_id for key in ("backend_release_id", "frontend_release_id", "response_header_release_id")):
        raise P7ReleaseError("p7_rollback_release_identity_failed")
    backend = results["backend_health"]
    frontend = results["frontend_health"]
    if (
        backend.get("http_status") != 200
        or backend.get("release_id") != release_id
        or backend.get("origin") != manifest["targets"]["backend"]["origin"]
        or frontend.get("http_status") != 200
        or frontend.get("release_id") != release_id
        or frontend.get("origin") != manifest["targets"]["frontend"]["origin"]
    ):
        raise P7ReleaseError("p7_rollback_health_failed")
    expected_routes = sorted(
        {
            *manifest["targets"]["backend"]["routes"],
            *manifest["targets"]["frontend"]["routes"],
        }
    )
    routes = results["routes"]
    route_statuses = routes.get("http_statuses")
    if (
        routes.get("checked_routes") != expected_routes
        or not isinstance(route_statuses, dict)
        or sorted(route_statuses) != expected_routes
        or any(not isinstance(value, int) or not 200 <= value < 300 for value in route_statuses.values())
    ):
        raise P7ReleaseError("p7_rollback_routes_failed")
    return {
        "schema_version": ROLLBACK_HEALTH_SCHEMA_VERSION,
        "status": "verified",
        "release_id": release_id,
        "manifest_sha256": manifest_sha,
        "evidence_sha256": snapshot.sha256,
        "collector_identity": COLLECTOR_SIGNER_IDENTITY,
        "collector_run_id": evidence["collector"]["run_id"],
        "collector_signature_verified": True,
        "route_config_sha256": previous_route_config_sha256,
    }


def verify_owner_approval(
    approval_path: Path,
    signature_path: Path,
    expected_bindings: dict[str, str],
    *,
    ssh_keygen: str | None = None,
) -> dict[str, Any]:
    require_p7_release_host()
    if set(expected_bindings) != APPROVAL_BINDING_KEYS:
        raise P7ReleaseError("p7_owner_approval_binding_set_invalid")
    snapshot = _read_canonical_snapshot(approval_path, "p7_owner_approval_invalid")
    approval = snapshot.payload
    verify_owner_signature(
        snapshot.raw,
        signature_path,
        namespace=APPROVAL_SIGNATURE_NAMESPACE,
        ssh_keygen=ssh_keygen,
    )
    required_keys = {"schema_version", "action", "approval_id", *expected_bindings}
    if (
        set(approval) != required_keys
        or approval.get("schema_version") != APPROVAL_SCHEMA_VERSION
        or approval.get("action") != "paired_switch"
        or not SAFE_ID.fullmatch(str(approval.get("approval_id") or ""))
        or any(approval.get(key) != value for key, value in expected_bindings.items())
    ):
        raise P7ReleaseError("p7_owner_approval_binding_mismatch")
    return {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "approval_id": approval["approval_id"],
        "approval_sha256": snapshot.sha256,
        "signer_identity": OWNER_SIGNER_IDENTITY,
        "signature_verified": True,
    }


def paired_switch_plan(
    *,
    release_dir: Path,
    rollback_release_dir: Path,
    gate_evidence_path: Path,
    gate_evidence_signature_path: Path,
    rollback_signature_path: Path,
    rollback_health_evidence_path: Path,
    rollback_health_signature_path: Path,
    previous_route_config_sha256: str,
    owner_approval_path: Path,
    owner_approval_signature_path: Path,
    signature_path: Path,
    repo: Path | None = None,
    ssh_keygen: str | None = None,
) -> dict[str, Any]:
    require_p7_release_host()
    if not SHA256.fullmatch(previous_route_config_sha256):
        raise P7ReleaseError("p7_previous_route_config_sha_invalid")
    verified, manifest_snapshot = _verify_release_snapshot(
        release_dir,
        repo=repo,
        require_signature=True,
        signature_path=signature_path,
        ssh_keygen=ssh_keygen,
    )
    manifest = manifest_snapshot.payload
    manifest_sha = manifest_snapshot.sha256
    gate_attestation = verify_gate_evidence(
        gate_evidence_path,
        gate_evidence_signature_path,
        manifest,
        manifest_sha,
        ssh_keygen=ssh_keygen,
    )
    rollback_verified, rollback_snapshot = _verify_release_snapshot(
        rollback_release_dir,
        repo=repo,
        require_signature=True,
        signature_path=rollback_signature_path,
        ssh_keygen=ssh_keygen,
    )
    rollback = rollback_snapshot.payload
    rollback_sha = rollback_snapshot.sha256
    rollback_release_id = rollback["release_id"]
    if rollback_release_id == manifest["release_id"]:
        raise P7ReleaseError("p7_rollback_release_must_differ")
    rollback_health = verify_rollback_health_evidence(
        rollback_health_evidence_path,
        rollback_health_signature_path,
        rollback,
        rollback_sha,
        previous_route_config_sha256,
        ssh_keygen=ssh_keygen,
    )
    approval = verify_owner_approval(
        owner_approval_path,
        owner_approval_signature_path,
        {
            "release_id": manifest["release_id"],
            "manifest_sha256": manifest_sha,
            "gate_evidence_sha256": gate_attestation["evidence_sha256"],
            "rollback_release_id": rollback_release_id,
            "rollback_manifest_sha256": rollback_sha,
            "rollback_health_evidence_sha256": rollback_health["evidence_sha256"],
            "previous_route_config_sha256": previous_route_config_sha256,
        },
        ssh_keygen=ssh_keygen,
    )
    targets = manifest["targets"]
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "status": "planned_not_applied",
        "production_applied": False,
        "release_id": manifest["release_id"],
        "source_commit": verified["source_commit"],
        "manifest_sha256": manifest_sha,
        "signature": {
            "verified": True,
            "namespace": RELEASE_SIGNATURE_NAMESPACE,
            "signer_identity": OWNER_SIGNER_IDENTITY,
            "trust_root": str(OWNER_TRUST_ROOT),
        },
        "owner_approval": approval,
        "targets": targets,
        "candidate_routes": {
            **targets["backend"]["routes"],
            **targets["frontend"]["routes"],
        },
        "functional_gate_attestation": gate_attestation,
        "atomic_switch": {
            "single_site_config_replacement": True,
            "frontend_and_backend_must_switch_together": True,
            "expected_previous_config_sha256": previous_route_config_sha256,
            "steps": [
                "verify candidate manifest, artifacts and pinned-owner signature",
                "verify collector-signed P7 functional gate evidence",
                "verify signed rollback manifest artifacts and collector-signed health evidence",
                "verify the signed owner approval binds every candidate and rollback digest",
                "start both side-by-side services on the explicit loopback ports",
                "require direct health and identical frontend/backend release identity",
                "copy the active site config and verify its exact SHA-256",
                "render one candidate site config containing every frontend/backend route",
                "validate the complete candidate config",
                "atomically replace the one site config and reload once",
                "repeat release identity, estimate, revision and PDF gates publicly",
            ],
        },
        "rollback": {
            "release_id": rollback_release_id,
            "manifest_sha256": rollback_sha,
            "artifact_count": rollback_verified["artifact_count"],
            "signature_verified": True,
            "health_attestation": rollback_health,
            "restore_config_sha256": previous_route_config_sha256,
            "bound_candidate_manifest_sha256": manifest_sha,
            "trigger": "any failed switch step or post-switch functional gate",
            "steps": [
                "restore the byte-for-byte saved site config",
                "verify restored config SHA-256",
                "validate config and reload once",
                "verify rollback release identity, health and prior routes",
            ],
        },
        "executor_contract": {
            "this_tool_can_apply": False,
            "root_required_by_downstream_executor": True,
            "owner_approval_and_all_bindings_must_be_reverified": True,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build")
    build.add_argument("--repo", required=True)
    build.add_argument("--output-root", required=True)
    build.add_argument("--release-id", required=True)
    build.add_argument("--backend-port", type=int, default=DEFAULT_BACKEND_PORT)
    build.add_argument("--frontend-port", type=int, default=DEFAULT_FRONTEND_PORT)
    build.add_argument("--npm-binary", default="npm")
    build.add_argument("--signing-key", default="")

    verify = subparsers.add_parser("verify")
    verify.add_argument("--release-dir", required=True)
    verify.add_argument("--repo", default="")
    verify.add_argument("--require-signature", action="store_true")
    verify.add_argument("--signature", default="")

    gates = subparsers.add_parser("verify-gates")
    gates.add_argument("--release-dir", required=True)
    gates.add_argument("--evidence", required=True)
    gates.add_argument("--signature", required=True)

    plan = subparsers.add_parser("plan-switch")
    plan.add_argument("--release-dir", required=True)
    plan.add_argument("--rollback-release-dir", required=True)
    plan.add_argument("--gate-evidence", required=True)
    plan.add_argument("--gate-evidence-signature", required=True)
    plan.add_argument("--rollback-signature", required=True)
    plan.add_argument("--rollback-health-evidence", required=True)
    plan.add_argument("--rollback-health-signature", required=True)
    plan.add_argument("--previous-route-config-sha256", required=True)
    plan.add_argument("--owner-approval", required=True)
    plan.add_argument("--owner-approval-signature", required=True)
    plan.add_argument("--signature", required=True)
    plan.add_argument("--repo", default="")
    return parser


def _optional_path(value: str) -> Path | None:
    return Path(value) if value else None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build":
            result = build_release(
                repo=Path(args.repo),
                output_root=Path(args.output_root),
                release_id=args.release_id,
                backend_port=args.backend_port,
                frontend_port=args.frontend_port,
                npm_binary=args.npm_binary,
                signing_key=_optional_path(args.signing_key),
            )
        elif args.command == "verify":
            result = verify_release(
                Path(args.release_dir),
                repo=_optional_path(args.repo),
                require_signature=args.require_signature,
                signature_path=_optional_path(args.signature),
            )
        elif args.command == "verify-gates":
            manifest, _, manifest_sha = load_manifest(Path(args.release_dir))
            result = verify_gate_evidence(
                Path(args.evidence),
                Path(args.signature),
                manifest,
                manifest_sha,
            )
        else:
            result = paired_switch_plan(
                release_dir=Path(args.release_dir),
                rollback_release_dir=Path(args.rollback_release_dir),
                gate_evidence_path=Path(args.gate_evidence),
                gate_evidence_signature_path=Path(args.gate_evidence_signature),
                rollback_signature_path=Path(args.rollback_signature),
                rollback_health_evidence_path=Path(args.rollback_health_evidence),
                rollback_health_signature_path=Path(args.rollback_health_signature),
                previous_route_config_sha256=args.previous_route_config_sha256,
                owner_approval_path=Path(args.owner_approval),
                owner_approval_signature_path=Path(args.owner_approval_signature),
                signature_path=Path(args.signature),
                repo=_optional_path(args.repo),
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (P7ReleaseError, OSError, ValueError, subprocess.SubprocessError) as exc:
        code = exc.code if isinstance(exc, P7ReleaseError) else "p7_release_unexpected_failure"
        print(json.dumps({"status": "failed", "reason": code}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
