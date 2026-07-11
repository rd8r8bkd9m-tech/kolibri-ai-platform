#!/usr/bin/env python3
"""Deterministic, fail-closed builder for signed Kolibri release bundles.

The default CLI mode is a read-only validation/plan.  Producing a bundle and
using a signing key require the separate ``--build`` and ``--sign`` opt-ins.
Private key bytes are never opened by this process; the supplied path is passed
only to ``ssh-keygen`` and is never included in output or error messages.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Callable, Iterable

try:
    from ops.release_installer import (
        MANIFEST_MEMBER,
        PAYLOAD_PREFIX,
        RELEASE_SCHEMA,
        RELEASE_SIGNATURE_NAMESPACE,
        SAFE_RECORD_ID,
        SIGNATURE_MEMBER,
        ProgressReporter,
        ReleaseInstallError,
        ReleaseInstaller,
        ReleaseInstallerConfig,
        _safe_relative_path,
        load_canonical_manifest,
    )
except ImportError:  # standalone execution from the installed ops directory
    from release_installer import (  # type: ignore[no-redef]
        MANIFEST_MEMBER,
        PAYLOAD_PREFIX,
        RELEASE_SCHEMA,
        RELEASE_SIGNATURE_NAMESPACE,
        SAFE_RECORD_ID,
        SIGNATURE_MEMBER,
        ProgressReporter,
        ReleaseInstallError,
        ReleaseInstaller,
        ReleaseInstallerConfig,
        _safe_relative_path,
        load_canonical_manifest,
    )


BUILDER_CONTRACT = "kolibri.release-builder.v1"
DEFAULT_COMPATIBILITY_EPOCH = "kolibri-os-v1"
MAX_FILES = 20_000
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024 * 1024
MAX_SIGNATURE_BYTES = 64 * 1024
HASH_CHUNK_BYTES = 1024 * 1024

EXCLUDED_COMPONENTS = frozenset(
    {
        ".codex",
        ".codex-runtime",
        ".factory",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "node_modules",
        "venv",
    }
)
ROOT_RUNTIME_COMPONENTS = frozenset({"artifacts", "data", "logs", "output", "tmp"})
RUNTIME_DATA_COMPONENTS = frozenset({".run", "artifacts", "cache", "logs", "output", "tmp"})
SECRET_FILENAMES = frozenset(
    {
        "auth.json",
        "cookies.json",
        "credentials.json",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
        "secret.json",
        "secrets.json",
        "telegram.env",
        "tokens.json",
    }
)
SECRET_SUFFIXES = (".key", ".pem", ".p12", ".pfx", ".jks")
PUBLIC_KEY_TYPE = re.compile(r"^(?:ssh-|ecdsa-|sk-)[A-Za-z0-9@._+-]+$")
PUBLIC_KEY_BODY = re.compile(r"^[A-Za-z0-9+/]+={0,3}$")


class ReleaseBuildError(RuntimeError):
    """Sanitized builder failure suitable for CLI output."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class PayloadFile:
    path: str
    source: Path
    sha256: str
    size_bytes: int
    mode: int
    device: int
    inode: int
    mtime_ns: int

    def manifest_record(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "mode": f"{self.mode:04o}",
        }


@dataclass(frozen=True)
class ReleasePlan:
    root: Path
    output: Path
    manifest: dict[str, Any]
    canonical_manifest: bytes
    manifest_digest: str
    files: tuple[PayloadFile, ...]

    @property
    def total_size_bytes(self) -> int:
        return sum(item.size_bytes for item in self.files)

    def public_summary(self, *, status: str = "planned") -> dict[str, Any]:
        return {
            "schema_version": BUILDER_CONTRACT,
            "status": status,
            "writes_performed": status == "built",
            "release_id": self.manifest["release_id"],
            "source_commit": self.manifest["source_commit"],
            "artifact_uri": self.manifest["artifact_uri"],
            "compatibility_epoch": self.manifest["compatibility_epoch"],
            "manifest_digest": self.manifest_digest,
            "output": str(self.output),
            "file_count": len(self.files),
            "total_size_bytes": self.total_size_bytes,
            "files": [item.manifest_record() for item in self.files],
            "signing_required_for_build": True,
        }


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ReleaseBuildError("release_builder_manifest_invalid") from exc


def _is_excluded(relative: str) -> bool:
    parts = tuple(part.lower() for part in PurePosixPath(relative).parts)
    if not parts:
        return True
    if any(part in EXCLUDED_COMPONENTS for part in parts):
        return True
    if any(part in RUNTIME_DATA_COMPONENTS for part in parts):
        return True
    if parts[0] in ROOT_RUNTIME_COMPONENTS:
        return True
    if len(parts) >= 2 and parts[0] == "backend" and parts[1] in ROOT_RUNTIME_COMPONENTS:
        return True
    name = parts[-1]
    if name == ".env" or name.startswith(".env.") or name in SECRET_FILENAMES:
        return True
    if name.endswith(SECRET_SUFFIXES) or ".private." in name:
        return True
    return False


def _normalize_mode(source_mode: int) -> int:
    return 0o755 if source_mode & 0o111 else 0o644


def _stable_file_digest(path: Path, relative: str) -> PayloadFile:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise ReleaseBuildError("release_builder_source_unreadable") from exc
    digest = hashlib.sha256()
    try:
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink < 1:
                raise ReleaseBuildError("release_builder_source_not_regular")
            for chunk in iter(lambda: handle.read(HASH_CHUNK_BYTES), b""):
                digest.update(chunk)
            after = os.fstat(handle.fileno())
    except ReleaseBuildError:
        raise
    except OSError as exc:
        raise ReleaseBuildError("release_builder_source_unreadable") from exc
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ReleaseBuildError("release_builder_source_unstable")
    return PayloadFile(
        path=relative,
        source=path,
        sha256=digest.hexdigest(),
        size_bytes=before.st_size,
        mode=_normalize_mode(before.st_mode),
        device=before.st_dev,
        inode=before.st_ino,
        mtime_ns=before.st_mtime_ns,
    )


def _assert_relative_source(root: Path, relative: str) -> Path:
    try:
        normalized = _safe_relative_path(relative)
    except ReleaseInstallError as exc:
        raise ReleaseBuildError("release_builder_source_path_invalid") from exc
    current = root
    for part in PurePosixPath(normalized).parts:
        current = current / part
        try:
            value = current.lstat()
        except OSError as exc:
            raise ReleaseBuildError("release_builder_source_missing") from exc
        if stat.S_ISLNK(value.st_mode):
            raise ReleaseBuildError("release_builder_symlink_forbidden")
    return current


def _walk_selected_tree(
    root: Path,
    base_relative: str,
    predicate: Callable[[str], bool],
) -> list[str]:
    base = _assert_relative_source(root, base_relative)
    if not base.is_dir():
        raise ReleaseBuildError("release_builder_source_missing")
    selected: list[str] = []

    def visit(directory: Path) -> None:
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda item: item.name.encode("utf-8"))
        except OSError as exc:
            raise ReleaseBuildError("release_builder_source_unreadable") from exc
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            try:
                relative = _safe_relative_path(relative)
            except ReleaseInstallError as exc:
                raise ReleaseBuildError("release_builder_source_path_invalid") from exc
            if _is_excluded(relative):
                continue
            if entry.is_symlink():
                raise ReleaseBuildError("release_builder_symlink_forbidden")
            if entry.is_dir(follow_symlinks=False):
                visit(path)
            elif entry.is_file(follow_symlinks=False):
                if predicate(relative):
                    selected.append(relative)
            elif predicate(relative):
                raise ReleaseBuildError("release_builder_source_not_regular")

    visit(base)
    return selected


def _backend_payload(relative: str) -> bool:
    path = PurePosixPath(relative)
    if "tests" in tuple(part.lower() for part in path.parts[1:-1]):
        return False
    return path.suffix.lower() in {".py", ".json"} or (
        path.name.lower().startswith("requirements")
        and path.suffix.lower() in {".txt", ".in", ".lock"}
    )


def _all_files(_relative: str) -> bool:
    return True


def _collect_runtime_path(root: Path, requested: str) -> list[str]:
    try:
        normalized = _safe_relative_path(requested)
    except ReleaseInstallError as exc:
        raise ReleaseBuildError("release_builder_runtime_path_invalid") from exc
    if _is_excluded(normalized):
        raise ReleaseBuildError("release_builder_runtime_path_forbidden")
    source = _assert_relative_source(root, normalized)
    if source.is_dir():
        return _walk_selected_tree(root, normalized, _all_files)
    if not source.is_file():
        raise ReleaseBuildError("release_builder_source_not_regular")
    return [normalized]


def collect_payload(
    root: Path,
    *,
    include_backend: bool = True,
    include_frontend: bool = True,
    runtime_paths: Iterable[str] = (),
) -> tuple[tuple[PayloadFile, ...], tuple[str, ...]]:
    root = root.resolve(strict=True)
    selected: set[str] = set()
    profiles: list[str] = []
    if include_backend:
        backend = _walk_selected_tree(root, "backend", _backend_payload)
        if not backend:
            raise ReleaseBuildError("release_builder_backend_payload_empty")
        selected.update(backend)
        profiles.append("backend")
    if include_frontend:
        frontend = _walk_selected_tree(root, "frontend/dist", _all_files)
        if not frontend:
            raise ReleaseBuildError("release_builder_frontend_payload_empty")
        selected.update(frontend)
        profiles.append("frontend-dist")
    runtime_requested = tuple(dict.fromkeys(str(item) for item in runtime_paths))
    for requested in runtime_requested:
        selected.update(_collect_runtime_path(root, requested))
    if runtime_requested:
        profiles.append("runtime")
    if not selected:
        raise ReleaseBuildError("release_builder_payload_empty")
    if len(selected) > MAX_FILES:
        raise ReleaseBuildError("release_builder_file_limit_exceeded")
    snapshots = tuple(
        _stable_file_digest(root.joinpath(*PurePosixPath(relative).parts), relative)
        for relative in sorted(selected)
    )
    if sum(item.size_bytes for item in snapshots) > MAX_PAYLOAD_BYTES:
        raise ReleaseBuildError("release_builder_payload_limit_exceeded")
    return snapshots, tuple(sorted(profiles))


def _validate_manifest_bytes(canonical: bytes) -> tuple[str, dict[str, Any]]:
    try:
        with tempfile.TemporaryDirectory(prefix="kolibri-release-manifest-") as temporary:
            path = Path(temporary) / "manifest.json"
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(canonical)
                handle.flush()
                os.fsync(handle.fileno())
            parsed = load_canonical_manifest(path)
    except ReleaseInstallError as exc:
        raise ReleaseBuildError(exc.code) from exc
    return parsed.digest, parsed.payload


def plan_release(
    *,
    root: Path,
    output: Path,
    release_id: str,
    source_commit: str,
    artifact_uri: str,
    compatibility_epoch: str = DEFAULT_COMPATIBILITY_EPOCH,
    include_backend: bool = True,
    include_frontend: bool = True,
    runtime_paths: Iterable[str] = (),
) -> ReleasePlan:
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        raise ReleaseBuildError("release_builder_root_invalid") from exc
    output = output if output.is_absolute() else root / output
    if not output.name.endswith(".tar.gz"):
        raise ReleaseBuildError("release_builder_output_invalid")
    files, profiles = collect_payload(
        root,
        include_backend=include_backend,
        include_frontend=include_frontend,
        runtime_paths=runtime_paths,
    )
    manifest = {
        "schema_version": RELEASE_SCHEMA,
        "release_id": str(release_id),
        "source_commit": str(source_commit).lower(),
        "artifact_uri": str(artifact_uri),
        "compatibility_epoch": str(compatibility_epoch),
        "files": [item.manifest_record() for item in files],
        "metadata": {
            "builder_contract": BUILDER_CONTRACT,
            "payload_profiles": list(profiles),
        },
    }
    canonical = _canonical_json(manifest)
    digest, normalized = _validate_manifest_bytes(canonical)
    return ReleasePlan(
        root=root,
        output=output,
        manifest=normalized,
        canonical_manifest=canonical,
        manifest_digest=digest,
        files=files,
    )


def _safe_signing_environment() -> dict[str, str]:
    result = {
        key: value
        for key, value in os.environ.items()
        if key in {"HOME", "LANG", "LC_ALL", "PATH", "TMPDIR"}
    }
    result["SSH_ASKPASS_REQUIRE"] = "never"
    result.pop("DISPLAY", None)
    return result


def _validate_ssh_keygen(path: Path) -> Path:
    try:
        value = path.lstat()
    except OSError as exc:
        raise ReleaseBuildError("release_builder_ssh_keygen_unavailable") from exc
    if not stat.S_ISREG(value.st_mode) or not value.st_mode & 0o111:
        raise ReleaseBuildError("release_builder_ssh_keygen_unavailable")
    return path


def _validate_signing_key(path: Path) -> Path:
    try:
        value = path.lstat()
        parent = path.parent.lstat()
    except OSError as exc:
        raise ReleaseBuildError("release_builder_signing_key_unavailable") from exc
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_nlink < 1
        or value.st_uid != os.geteuid()
        or stat.S_IMODE(value.st_mode) & 0o077
        or not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid not in {0, os.geteuid()}
        or stat.S_IMODE(parent.st_mode) & 0o022
    ):
        raise ReleaseBuildError("release_builder_signing_key_permissions_invalid")
    return path


def _run_ssh_keygen(command: list[str], *, capture_stdout: bool = False) -> bytes:
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=_safe_signing_environment(),
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseBuildError("release_builder_signing_failed") from exc
    if completed.returncode != 0:
        raise ReleaseBuildError("release_builder_signing_failed")
    return bytes(completed.stdout or b"")


def _sign_manifest(
    manifest_path: Path,
    *,
    signing_key: Path,
    ssh_keygen: Path,
) -> tuple[bytes, bytes]:
    try:
        key_before = signing_key.lstat()
    except OSError as exc:
        raise ReleaseBuildError("release_builder_signing_key_unavailable") from exc
    _run_ssh_keygen(
        [
            str(ssh_keygen),
            "-Y",
            "sign",
            "-f",
            str(signing_key),
            "-n",
            RELEASE_SIGNATURE_NAMESPACE,
            str(manifest_path),
        ]
    )
    generated = Path(f"{manifest_path}.sig")
    try:
        descriptor = os.open(generated, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            value = os.fstat(handle.fileno())
            if not stat.S_ISREG(value.st_mode) or not 0 < value.st_size <= MAX_SIGNATURE_BYTES:
                raise ReleaseBuildError("release_builder_signature_invalid")
            signature = handle.read(MAX_SIGNATURE_BYTES + 1)
    except ReleaseBuildError:
        raise
    except OSError as exc:
        raise ReleaseBuildError("release_builder_signature_invalid") from exc
    finally:
        try:
            generated.unlink(missing_ok=True)
        except OSError:
            pass
    public_key = _run_ssh_keygen(
        [str(ssh_keygen), "-y", "-f", str(signing_key)],
        capture_stdout=True,
    ).strip()
    public_parts = public_key.split()
    if (
        len(public_parts) < 2
        or not PUBLIC_KEY_TYPE.fullmatch(public_parts[0].decode("ascii", errors="ignore"))
        or not PUBLIC_KEY_BODY.fullmatch(public_parts[1].decode("ascii", errors="ignore"))
    ):
        raise ReleaseBuildError("release_builder_public_key_invalid")
    try:
        key_after = signing_key.lstat()
    except OSError as exc:
        raise ReleaseBuildError("release_builder_signing_key_unstable") from exc
    if (
        key_before.st_dev != key_after.st_dev
        or key_before.st_ino != key_after.st_ino
        or key_before.st_size != key_after.st_size
        or key_before.st_mtime_ns != key_after.st_mtime_ns
        or stat.S_IMODE(key_before.st_mode) != stat.S_IMODE(key_after.st_mode)
    ):
        raise ReleaseBuildError("release_builder_signing_key_unstable")
    # Comments emitted by ``ssh-keygen -y`` may contain a local key path.  The
    # allowed-signers snapshot needs only the public algorithm and key body.
    return signature, b" ".join(public_parts[:2])


def _tar_info(name: str, size: int, mode: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mode = mode
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.type = tarfile.REGTYPE
    info.pax_headers = {}
    return info


def _add_bytes(archive: tarfile.TarFile, name: str, content: bytes, mode: int) -> None:
    import io

    archive.addfile(_tar_info(name, len(content), mode), io.BytesIO(content))


def _open_snapshot(snapshot: PayloadFile) -> BinaryIO:
    try:
        descriptor = os.open(snapshot.source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        handle = os.fdopen(descriptor, "rb")
        value = os.fstat(handle.fileno())
    except OSError as exc:
        raise ReleaseBuildError("release_builder_source_unreadable") from exc
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_dev != snapshot.device
        or value.st_ino != snapshot.inode
        or value.st_size != snapshot.size_bytes
        or value.st_mtime_ns != snapshot.mtime_ns
    ):
        handle.close()
        raise ReleaseBuildError("release_builder_source_unstable")
    return handle


def _write_deterministic_bundle(
    destination: Path,
    plan: ReleasePlan,
    signature: bytes,
) -> None:
    try:
        descriptor = os.open(
            destination,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as raw:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                compresslevel=9,
                fileobj=raw,
                mtime=0,
            ) as compressed:
                with tarfile.open(
                    fileobj=compressed,
                    mode="w|",
                    format=tarfile.PAX_FORMAT,
                ) as archive:
                    _add_bytes(archive, MANIFEST_MEMBER, plan.canonical_manifest, 0o600)
                    _add_bytes(archive, SIGNATURE_MEMBER, signature, 0o600)
                    for snapshot in plan.files:
                        handle = _open_snapshot(snapshot)
                        try:
                            archive.addfile(
                                _tar_info(
                                    f"{PAYLOAD_PREFIX}{snapshot.path}",
                                    snapshot.size_bytes,
                                    snapshot.mode,
                                ),
                                handle,
                            )
                            after = os.fstat(handle.fileno())
                        finally:
                            handle.close()
                        if (
                            after.st_dev != snapshot.device
                            or after.st_ino != snapshot.inode
                            or after.st_size != snapshot.size_bytes
                            or after.st_mtime_ns != snapshot.mtime_ns
                        ):
                            raise ReleaseBuildError("release_builder_source_unstable")
            raw.flush()
            os.fsync(raw.fileno())
        destination.chmod(0o644)
    except ReleaseBuildError:
        raise
    except (OSError, tarfile.TarError) as exc:
        raise ReleaseBuildError("release_builder_archive_failed") from exc


def _write_private_file(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def self_verify_bundle(
    bundle: Path,
    plan: ReleasePlan,
    *,
    signer_identity: str,
    public_key: bytes,
    ssh_keygen: Path,
) -> None:
    if not SAFE_RECORD_ID.fullmatch(signer_identity):
        raise ReleaseBuildError("release_builder_signer_identity_invalid")
    try:
        with tempfile.TemporaryDirectory(prefix="kolibri-release-self-verify-") as temporary:
            root = Path(temporary)
            release_root = root / "releases"
            release_root.mkdir(mode=0o700)
            allowed_signers = root / "allowed_signers"
            _write_private_file(
                allowed_signers,
                signer_identity.encode("utf-8") + b" " + public_key + b"\n",
            )
            config = ReleaseInstallerConfig(
                artifact_root=root / "artifacts",
                release_root=release_root,
                current_link=root / "current",
                allowed_signers=allowed_signers,
                policy_path=root / "unused-policy.json",
                ssh_keygen=ssh_keygen,
                systemctl=Path("/usr/bin/false"),
                owner_allowed_signers=root / "unused-owner-signers",
                max_bundle_bytes=max(bundle.stat().st_size + 1, 1024),
                max_unpacked_bytes=max(plan.total_size_bytes + 4 * 1024 * 1024, 4 * 1024 * 1024),
                max_members=max(len(plan.files) + 4, 16),
            )
            installer = ReleaseInstaller(config)
            staging = root / "staging"
            progress = ProgressReporter(None)
            member_modes = installer._extract_bundle(bundle, staging, progress)
            parsed = load_canonical_manifest(staging / MANIFEST_MEMBER)
            if (
                parsed.digest != plan.manifest_digest
                or parsed.canonical_bytes != plan.canonical_manifest
                or parsed.payload != plan.manifest
            ):
                raise ReleaseBuildError("release_builder_self_verify_manifest_mismatch")
            installer._verify_signature(
                staging / SIGNATURE_MEMBER,
                parsed,
                signer_identity,
                progress,
            )
            installer._validate_payload(staging, parsed, member_modes, progress)
    except ReleaseBuildError:
        raise
    except ReleaseInstallError as exc:
        raise ReleaseBuildError(exc.code) from exc
    except OSError as exc:
        raise ReleaseBuildError("release_builder_self_verify_failed") from exc


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(HASH_CHUNK_BYTES), b""):
                digest.update(chunk)
                total += len(chunk)
    except OSError as exc:
        raise ReleaseBuildError("release_builder_output_unreadable") from exc
    return digest.hexdigest(), total


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise ReleaseBuildError("release_builder_output_sync_failed") from exc


def _publish_without_overwrite(temporary: Path, output: Path) -> None:
    if os.path.lexists(output):
        raise ReleaseBuildError("release_builder_output_exists")
    try:
        os.link(temporary, output, follow_symlinks=False)
        temporary.unlink()
        _fsync_directory(output.parent)
    except FileExistsError as exc:
        raise ReleaseBuildError("release_builder_output_exists") from exc
    except OSError as exc:
        raise ReleaseBuildError("release_builder_output_publish_failed") from exc


def build_release(
    plan: ReleasePlan,
    *,
    signing_key: Path,
    signer_identity: str,
    ssh_keygen: Path,
) -> dict[str, Any]:
    if not SAFE_RECORD_ID.fullmatch(signer_identity):
        raise ReleaseBuildError("release_builder_signer_identity_invalid")
    ssh_keygen = _validate_ssh_keygen(ssh_keygen)
    signing_key = _validate_signing_key(signing_key)
    try:
        plan.output.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        output_parent = plan.output.parent.resolve(strict=True)
    except OSError as exc:
        raise ReleaseBuildError("release_builder_output_invalid") from exc
    output = output_parent / plan.output.name
    if os.path.lexists(output):
        raise ReleaseBuildError("release_builder_output_exists")
    temporary_output: Path | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="kolibri-release-sign-") as temporary:
            manifest_path = Path(temporary) / "manifest.json"
            _write_private_file(manifest_path, plan.canonical_manifest)
            signature, public_key = _sign_manifest(
                manifest_path,
                signing_key=signing_key,
                ssh_keygen=ssh_keygen,
            )
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{output.name}.",
                suffix=".tmp",
                dir=output_parent,
            )
            os.close(descriptor)
            temporary_output = Path(temporary_name)
            temporary_output.unlink()
            _write_deterministic_bundle(temporary_output, plan, signature)
            self_verify_bundle(
                temporary_output,
                plan,
                signer_identity=signer_identity,
                public_key=public_key,
                ssh_keygen=ssh_keygen,
            )
            bundle_sha256, bundle_size = _sha256_file(temporary_output)
            _publish_without_overwrite(temporary_output, output)
            temporary_output = None
    finally:
        if temporary_output is not None:
            try:
                temporary_output.unlink(missing_ok=True)
            except OSError:
                pass
    result = plan.public_summary(status="built")
    result.update(
        {
            "output": str(output),
            "bundle_sha256": bundle_sha256,
            "bundle_size_bytes": bundle_size,
            "signature": {
                "format": "sshsig",
                "namespace": RELEASE_SIGNATURE_NAMESPACE,
                "signer_identity": signer_identity,
            },
            "self_verified": True,
        }
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a signed deterministic Kolibri release bundle")
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--artifact-uri")
    parser.add_argument("--compatibility-epoch", default=DEFAULT_COMPATIBILITY_EPOCH)
    parser.add_argument("--output")
    parser.add_argument("--backend", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--frontend", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--runtime-path", action="append", default=[])
    parser.add_argument("--build", action="store_true", help="permit writing the bundle")
    parser.add_argument("--sign", action="store_true", help="permit use of the supplied signing key")
    parser.add_argument("--signing-key")
    parser.add_argument("--signer-identity")
    parser.add_argument("--ssh-keygen", default=shutil.which("ssh-keygen") or "/usr/bin/ssh-keygen")
    return parser


def _error(code: str) -> str:
    return _canonical_json(
        {"schema_version": BUILDER_CONTRACT, "status": "failed", "error_type": code}
    ).decode("utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.sign and not args.build:
            raise ReleaseBuildError("release_builder_sign_requires_build")
        if args.build and not args.sign:
            raise ReleaseBuildError("release_builder_build_requires_sign")
        if args.sign and (not args.signing_key or not args.signer_identity):
            raise ReleaseBuildError("release_builder_signing_options_missing")
        if not args.sign and (args.signing_key or args.signer_identity):
            raise ReleaseBuildError("release_builder_signing_options_without_sign")
        release_id = str(args.release_id)
        output_value = args.output or f"release/bundles/{release_id}.tar.gz"
        artifact_uri = args.artifact_uri or f"artifact://bundles/{release_id}.tar.gz"
        plan = plan_release(
            root=Path(args.root),
            output=Path(output_value),
            release_id=release_id,
            source_commit=str(args.source_commit),
            artifact_uri=artifact_uri,
            compatibility_epoch=str(args.compatibility_epoch),
            include_backend=bool(args.backend),
            include_frontend=bool(args.frontend),
            runtime_paths=tuple(args.runtime_path),
        )
        if not args.build:
            print(_canonical_json(plan.public_summary()).decode("utf-8"))
            return 0
        result = build_release(
            plan,
            signing_key=Path(args.signing_key),
            signer_identity=str(args.signer_identity),
            ssh_keygen=Path(args.ssh_keygen),
        )
        print(_canonical_json(result).decode("utf-8"))
        return 0
    except ReleaseBuildError as exc:
        print(_error(exc.code), file=sys.stderr)
        return 2
    except ReleaseInstallError as exc:
        print(_error(exc.code), file=sys.stderr)
        return 2
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError):
        print(_error("release_builder_failed"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
