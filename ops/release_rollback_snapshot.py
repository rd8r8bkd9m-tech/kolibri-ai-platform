#!/usr/bin/env python3
"""Create a fail-closed first-migration rollback source snapshot.

This helper does not sign, stage, activate, or deploy a release.  It assembles
an isolated local source tree from two explicit sources:

* product files whose bytes are bound by the currently installed signed
  release manifest; and
* the exact effective split-runtime files mapped by the operator.

Unbound entries in the installed release (including ``__pycache__``) are never
copied.  They also cannot be ignored accidentally: capture is blocked until
the operator supplies the digest emitted by the read-only plan.  The required
Mimo response profile may be supplied as a compatibility sentinel only when
its committed source and expected digest are declared; provenance states that
the sentinel was not effective at capture time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

try:
    from ops.release_installer import (
        MANIFEST_MEMBER,
        MIMO_RESPONSE_AGENT_PROFILE_PATH,
        RELEASE_SIGNATURE_NAMESPACE,
        SAFE_FILE_MODES,
        SAFE_RECORD_ID,
        SAFE_RELEASE_ID,
        SIGNATURE_MEMBER,
        CanonicalManifest,
        ReleaseInstallError,
        _safe_relative_path,
        load_canonical_manifest,
    )
    from ops.release_snapshot_marker import SnapshotMarkerError, create_release_marker
except ImportError:  # standalone execution beside the installed release modules
    from release_installer import (  # type: ignore[no-redef]
        MANIFEST_MEMBER,
        MIMO_RESPONSE_AGENT_PROFILE_PATH,
        RELEASE_SIGNATURE_NAMESPACE,
        SAFE_FILE_MODES,
        SAFE_RECORD_ID,
        SAFE_RELEASE_ID,
        SIGNATURE_MEMBER,
        CanonicalManifest,
        ReleaseInstallError,
        _safe_relative_path,
        load_canonical_manifest,
    )
    from release_snapshot_marker import (  # type: ignore[no-redef]
        SnapshotMarkerError,
        create_release_marker,
    )


SNAPSHOT_SCHEMA = "kolibri.rollback-snapshot.v1"
PROVENANCE_NAME = "ROLLBACK_PROVENANCE.json"
HASH_CHUNK_BYTES = 1024 * 1024
MAX_UNBOUND_ENTRIES = 20_000
PRODUCT_PREFIXES = ("backend/", "frontend/dist/")
SPLIT_RUNTIME_PATHS = (
    "ops/agent_host.py",
    "ops/control_plane_endpoint.py",
    "ops/factory_control.py",
    "ops/fleet_membership.py",
    "ops/immutable_release_preflight.py",
    "ops/marked_connect_proxy.py",
    MIMO_RESPONSE_AGENT_PROFILE_PATH,
    "ops/provider_egress_policy.py",
    "ops/provider_egress_preflight.py",
    "ops/provider_egress_tunnel.py",
    "ops/release_authority.py",
    "ops/release_helper.py",
    "ops/release_installer.py",
    "ops/runner_access.py",
    "ops/systemd/kolibri-agent-host-provider-egress.conf",
    "ops/systemd/kolibri-provider-egress-proxy.service",
    "ops/systemd/kolibri-provider-egress-tunnel.service",
    "ops/telegram_superfactory.py",
)
EFFECTIVE_RUNTIME_PATHS = tuple(
    path for path in SPLIT_RUNTIME_PATHS if path != MIMO_RESPONSE_AGENT_PROFILE_PATH
)
SAFE_COMMIT = re.compile(r"[0-9a-f]{7,64}\Z")
SAFE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class RollbackSnapshotError(RuntimeError):
    """Sanitized snapshot failure suitable for release evidence."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class BoundFile:
    destination: str
    source: Path
    sha256: str
    size_bytes: int
    mode: int
    device: int
    inode: int
    mtime_ns: int
    role: str
    effective_at_capture: bool
    source_commit: str | None = None

    def provenance(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "destination": self.destination,
            "effective_at_capture": self.effective_at_capture,
            "mode": f"{self.mode:04o}",
            "role": self.role,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "source_path": str(self.source),
        }
        if self.source_commit is not None:
            value["source_commit"] = self.source_commit
        return value


@dataclass(frozen=True)
class UnboundEntry:
    path: str
    kind: str
    mode: int
    size_bytes: int
    mtime_ns: int

    def record(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "mode": f"{self.mode:04o}",
            "mtime_ns": self.mtime_ns,
            "path": self.path,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class SnapshotPlan:
    current_root: Path
    snapshot_root: Path
    rollback_release_id: str
    signer_identity: str
    source_manifest: CanonicalManifest
    product_files: tuple[BoundFile, ...]
    runtime_files: tuple[BoundFile, ...]
    unbound_entries: tuple[UnboundEntry, ...]
    unbound_digest: str

    @property
    def blocked(self) -> bool:
        return bool(self.unbound_entries)

    def public_summary(self, *, acknowledged_digest: str | None = None) -> dict[str, Any]:
        acknowledged = not self.unbound_entries or acknowledged_digest == self.unbound_digest
        return {
            "schema_version": SNAPSHOT_SCHEMA,
            "status": "planned" if acknowledged else "blocked",
            "writes_performed": False,
            "rollback_release_id": self.rollback_release_id,
            "source_release": {
                "release_id": self.source_manifest.release_id,
                "manifest_digest": self.source_manifest.digest,
                "source_commit": self.source_manifest.source_commit,
                "signer_identity": self.signer_identity,
            },
            "snapshot_root": str(self.snapshot_root),
            "product_file_count": len(self.product_files),
            "runtime_file_count": len(self.runtime_files),
            "unbound_entries": {
                "acknowledged": acknowledged,
                "count": len(self.unbound_entries),
                "digest": self.unbound_digest,
                "records": [item.record() for item in self.unbound_entries],
            },
            "required_builder_runtime_paths": [
                "RELEASE_ID",
                PROVENANCE_NAME,
                *SPLIT_RUNTIME_PATHS,
            ],
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
        raise RollbackSnapshotError("rollback_snapshot_provenance_invalid") from exc


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _validate_direct_directory(path: Path, code: str) -> Path:
    try:
        info = path.lstat()
    except OSError as exc:
        raise RollbackSnapshotError(code) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RollbackSnapshotError(code)
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise RollbackSnapshotError(code) from exc


def _safe_source(root: Path, relative: str) -> Path:
    if relative in {MANIFEST_MEMBER, SIGNATURE_MEMBER}:
        normalized = relative
    else:
        try:
            normalized = _safe_relative_path(relative)
        except ReleaseInstallError as exc:
            raise RollbackSnapshotError("rollback_snapshot_path_invalid") from exc
    cursor = root
    for part in PurePosixPath(normalized).parts:
        cursor /= part
        try:
            info = cursor.lstat()
        except OSError as exc:
            raise RollbackSnapshotError("rollback_snapshot_bound_file_missing") from exc
        if stat.S_ISLNK(info.st_mode):
            raise RollbackSnapshotError("rollback_snapshot_symlink_forbidden")
    return cursor


def _stable_bound_file(
    source: Path,
    *,
    destination: str,
    role: str,
    effective_at_capture: bool,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
    expected_mode: int | None = None,
    source_commit: str | None = None,
) -> BoundFile:
    try:
        descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise RollbackSnapshotError("rollback_snapshot_bound_file_unreadable") from exc
    digest = hashlib.sha256()
    try:
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise RollbackSnapshotError("rollback_snapshot_bound_file_unsafe")
            for chunk in iter(lambda: handle.read(HASH_CHUNK_BYTES), b""):
                digest.update(chunk)
            after = os.fstat(handle.fileno())
    except RollbackSnapshotError:
        raise
    except OSError as exc:
        raise RollbackSnapshotError("rollback_snapshot_bound_file_unreadable") from exc
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise RollbackSnapshotError("rollback_snapshot_bound_file_unstable")
    actual_digest = digest.hexdigest()
    actual_mode = stat.S_IMODE(before.st_mode)
    normalized_mode = 0o755 if actual_mode & 0o111 else 0o644
    if expected_sha256 is not None and actual_digest != expected_sha256:
        raise RollbackSnapshotError("rollback_snapshot_bound_file_digest_mismatch")
    if expected_size is not None and before.st_size != expected_size:
        raise RollbackSnapshotError("rollback_snapshot_bound_file_size_mismatch")
    if expected_mode is not None and actual_mode != expected_mode:
        raise RollbackSnapshotError("rollback_snapshot_bound_file_mode_mismatch")
    return BoundFile(
        destination=destination,
        source=source,
        sha256=actual_digest,
        size_bytes=before.st_size,
        mode=expected_mode if expected_mode is not None else normalized_mode,
        device=before.st_dev,
        inode=before.st_ino,
        mtime_ns=before.st_mtime_ns,
        role=role,
        effective_at_capture=effective_at_capture,
        source_commit=source_commit,
    )


def _verify_source_signature(
    manifest: CanonicalManifest,
    signature: Path,
    *,
    allowed_signers: Path,
    signer_identity: str,
    ssh_keygen: Path,
) -> None:
    if not SAFE_RECORD_ID.fullmatch(signer_identity):
        raise RollbackSnapshotError("rollback_snapshot_signer_identity_invalid")
    for path, code, executable in (
        (signature, "rollback_snapshot_signature_invalid", False),
        (allowed_signers, "rollback_snapshot_allowed_signers_invalid", False),
        (ssh_keygen, "rollback_snapshot_signature_verifier_unavailable", True),
    ):
        try:
            info = path.lstat()
        except OSError as exc:
            raise RollbackSnapshotError(code) from exc
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or (executable and not info.st_mode & 0o111)
        ):
            raise RollbackSnapshotError(code)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"HOME", "LANG", "LC_ALL", "PATH", "TMPDIR"}
    }
    environment["SSH_ASKPASS_REQUIRE"] = "never"
    environment.pop("DISPLAY", None)
    try:
        completed = subprocess.run(
            [
                str(ssh_keygen),
                "-Y",
                "verify",
                "-f",
                str(allowed_signers),
                "-I",
                signer_identity,
                "-n",
                RELEASE_SIGNATURE_NAMESPACE,
                "-s",
                str(signature),
            ],
            input=manifest.canonical_bytes,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RollbackSnapshotError("rollback_snapshot_signature_verification_failed") from exc
    if completed.returncode != 0:
        raise RollbackSnapshotError("rollback_snapshot_signature_verification_failed")


def _entry_kind(mode: int) -> str:
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISLNK(mode):
        return "symlink"
    return "special"


def _inventory_relative_path(value: str) -> str:
    text = str(value or "")
    if (
        not text
        or "\\" in text
        or "\x00" in text
        or len(text.encode("utf-8")) > 4096
        or any(part in {"", ".", ".."} for part in text.split("/"))
        or PurePosixPath(text).is_absolute()
    ):
        raise RollbackSnapshotError("rollback_snapshot_source_inventory_failed")
    return text


def _scan_unbound_entries(
    root: Path,
    expected_files: Iterable[str],
    *,
    ignore_git_metadata: bool = False,
) -> tuple[UnboundEntry, ...]:
    expected_file_set = set(expected_files)
    expected_directories: set[str] = set()
    for relative in expected_file_set:
        path = PurePosixPath(relative)
        for parent in path.parents:
            value = parent.as_posix()
            if value != ".":
                expected_directories.add(value)
    records: list[UnboundEntry] = []

    def visit(directory: Path) -> None:
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda item: item.name.encode("utf-8"))
        except OSError as exc:
            raise RollbackSnapshotError("rollback_snapshot_source_inventory_failed") from exc
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            try:
                relative = _inventory_relative_path(relative)
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise RollbackSnapshotError("rollback_snapshot_source_inventory_failed") from exc
            kind = _entry_kind(info.st_mode)
            if ignore_git_metadata and relative == ".git":
                if kind != "directory" or stat.S_IMODE(info.st_mode) & 0o022:
                    raise RollbackSnapshotError("rollback_snapshot_git_metadata_unsafe")
                continue
            expected = (
                kind == "directory" and relative in expected_directories
            ) or (kind == "file" and relative in expected_file_set)
            if not expected:
                records.append(
                    UnboundEntry(
                        path=relative,
                        kind=kind,
                        mode=stat.S_IMODE(info.st_mode),
                        size_bytes=info.st_size if kind != "directory" else 0,
                        mtime_ns=info.st_mtime_ns,
                    )
                )
                if len(records) > MAX_UNBOUND_ENTRIES:
                    raise RollbackSnapshotError("rollback_snapshot_unbound_entry_limit")
            if kind == "directory":
                visit(path)

    visit(root)
    return tuple(sorted(records, key=lambda item: item.path))


def _unbound_digest(entries: Iterable[UnboundEntry]) -> str:
    return _sha256_bytes(_canonical_json([entry.record() for entry in entries]))


def _parse_runtime_maps(values: Iterable[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        destination, separator, source_text = str(value).partition("=")
        if not separator or destination not in EFFECTIVE_RUNTIME_PATHS or destination in result:
            raise RollbackSnapshotError("rollback_snapshot_runtime_map_invalid")
        source = Path(source_text)
        if not source.is_absolute():
            raise RollbackSnapshotError("rollback_snapshot_runtime_map_invalid")
        result[destination] = source
    if set(result) != set(EFFECTIVE_RUNTIME_PATHS):
        raise RollbackSnapshotError("rollback_snapshot_runtime_map_incomplete")
    return result


def _runtime_files(
    runtime_maps: dict[str, Path],
    *,
    mimo_effective_source: Path | None,
    mimo_sentinel_source: Path | None,
    mimo_sentinel_commit: str | None,
    mimo_sentinel_sha256: str | None,
) -> tuple[BoundFile, ...]:
    if (mimo_effective_source is None) == (mimo_sentinel_source is None):
        raise RollbackSnapshotError("rollback_snapshot_mimo_source_ambiguous")
    files = [
        _stable_bound_file(
            source,
            destination=destination,
            role="effective-split-runtime",
            effective_at_capture=True,
        )
        for destination, source in sorted(runtime_maps.items())
    ]
    if mimo_effective_source is not None:
        if not mimo_effective_source.is_absolute():
            raise RollbackSnapshotError("rollback_snapshot_mimo_source_invalid")
        files.append(
            _stable_bound_file(
                mimo_effective_source,
                destination=MIMO_RESPONSE_AGENT_PROFILE_PATH,
                role="effective-split-runtime",
                effective_at_capture=True,
            )
        )
    else:
        commit = str(mimo_sentinel_commit or "").lower()
        digest = str(mimo_sentinel_sha256 or "").lower()
        if (
            mimo_sentinel_source is None
            or not mimo_sentinel_source.is_absolute()
            or not SAFE_COMMIT.fullmatch(commit)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise RollbackSnapshotError("rollback_snapshot_mimo_sentinel_provenance_invalid")
        files.append(
            _stable_bound_file(
                mimo_sentinel_source,
                destination=MIMO_RESPONSE_AGENT_PROFILE_PATH,
                role="compatibility-sentinel-not-active-at-capture",
                effective_at_capture=False,
                expected_sha256=digest,
                source_commit=commit,
            )
        )
    return tuple(sorted(files, key=lambda item: item.destination))


def plan_snapshot(
    *,
    current_root: Path,
    snapshot_root: Path,
    rollback_release_id: str,
    allowed_signers: Path,
    signer_identity: str,
    ssh_keygen: Path,
    runtime_maps: dict[str, Path],
    mimo_effective_source: Path | None = None,
    mimo_sentinel_source: Path | None = None,
    mimo_sentinel_commit: str | None = None,
    mimo_sentinel_sha256: str | None = None,
) -> SnapshotPlan:
    if not SAFE_RELEASE_ID.fullmatch(str(rollback_release_id)):
        raise RollbackSnapshotError("rollback_snapshot_release_id_invalid")
    current_root = _validate_direct_directory(current_root, "rollback_snapshot_current_root_invalid")
    snapshot_root = snapshot_root if snapshot_root.is_absolute() else Path.cwd() / snapshot_root
    try:
        snapshot_parent = snapshot_root.parent.resolve(strict=True)
    except OSError as exc:
        raise RollbackSnapshotError("rollback_snapshot_output_parent_invalid") from exc
    snapshot_root = snapshot_parent / snapshot_root.name
    try:
        snapshot_root.relative_to(current_root)
    except ValueError:
        pass
    else:
        raise RollbackSnapshotError("rollback_snapshot_output_overlaps_source")
    manifest_path = _safe_source(current_root, MANIFEST_MEMBER)
    signature_path = _safe_source(current_root, SIGNATURE_MEMBER)
    try:
        manifest = load_canonical_manifest(manifest_path)
    except ReleaseInstallError as exc:
        raise RollbackSnapshotError(exc.code) from exc
    _verify_source_signature(
        manifest,
        signature_path,
        allowed_signers=allowed_signers,
        signer_identity=signer_identity,
        ssh_keygen=ssh_keygen,
    )
    if set(SPLIT_RUNTIME_PATHS).issubset({item.path for item in manifest.files}):
        raise RollbackSnapshotError("rollback_snapshot_source_already_unified")

    manifest_bound: list[BoundFile] = []
    for record in manifest.files:
        source = _safe_source(current_root, record.path)
        manifest_bound.append(
            _stable_bound_file(
                source,
                destination=record.path,
                role="signed-source-manifest",
                effective_at_capture=record.path.startswith(PRODUCT_PREFIXES),
                expected_sha256=record.sha256,
                expected_size=record.size_bytes,
                expected_mode=record.mode,
                source_commit=manifest.source_commit,
            )
        )
    product_files = tuple(
        item
        for item in manifest_bound
        if item.destination.startswith(PRODUCT_PREFIXES)
    )
    if (
        not any(item.destination == "backend/main.py" for item in product_files)
        or not any(item.destination == "frontend/dist/index.html" for item in product_files)
    ):
        raise RollbackSnapshotError("rollback_snapshot_product_profile_incomplete")
    source_marker = next(
        (item for item in manifest_bound if item.destination == "RELEASE_ID"),
        None,
    )
    expected_source_marker = f"{manifest.release_id}\n".encode("ascii")
    if (
        source_marker is None
        or source_marker.size_bytes != len(expected_source_marker)
        or source_marker.sha256 != hashlib.sha256(expected_source_marker).hexdigest()
    ):
        raise RollbackSnapshotError("rollback_snapshot_source_release_id_marker_invalid")

    runtime_files = _runtime_files(
        runtime_maps,
        mimo_effective_source=mimo_effective_source,
        mimo_sentinel_source=mimo_sentinel_source,
        mimo_sentinel_commit=mimo_sentinel_commit,
        mimo_sentinel_sha256=mimo_sentinel_sha256,
    )
    destinations = [item.destination for item in (*product_files, *runtime_files)]
    if len(destinations) != len(set(destinations)):
        raise RollbackSnapshotError("rollback_snapshot_destination_collision")

    expected_source_files = {
        MANIFEST_MEMBER,
        SIGNATURE_MEMBER,
        *(item.path for item in manifest.files),
    }
    unbound_entries = _scan_unbound_entries(current_root, expected_source_files)
    return SnapshotPlan(
        current_root=current_root,
        snapshot_root=snapshot_root,
        rollback_release_id=str(rollback_release_id),
        signer_identity=signer_identity,
        source_manifest=manifest,
        product_files=product_files,
        runtime_files=runtime_files,
        unbound_entries=unbound_entries,
        unbound_digest=_unbound_digest(unbound_entries),
    )


def _copy_bound_file(item: BoundFile, root: Path) -> None:
    target = root.joinpath(*PurePosixPath(item.destination).parts)
    target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    source_fd: int | None = None
    target_fd: int | None = None
    try:
        source_fd = os.open(item.source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        target_fd = os.open(
            target,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError as exc:
        if source_fd is not None:
            os.close(source_fd)
        if target_fd is not None:
            os.close(target_fd)
        raise RollbackSnapshotError("rollback_snapshot_copy_failed") from exc
    digest = hashlib.sha256()
    try:
        assert source_fd is not None and target_fd is not None
        with os.fdopen(source_fd, "rb") as source, os.fdopen(target_fd, "wb") as output:
            before = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or before.st_dev != item.device
                or before.st_ino != item.inode
                or before.st_size != item.size_bytes
                or before.st_mtime_ns != item.mtime_ns
            ):
                raise RollbackSnapshotError("rollback_snapshot_bound_file_changed")
            for chunk in iter(lambda: source.read(HASH_CHUNK_BYTES), b""):
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
            after = os.fstat(source.fileno())
            if (
                before.st_dev != after.st_dev
                or before.st_ino != after.st_ino
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or digest.hexdigest() != item.sha256
            ):
                raise RollbackSnapshotError("rollback_snapshot_bound_file_changed")
        target.chmod(item.mode)
    except RollbackSnapshotError:
        raise
    except OSError as exc:
        raise RollbackSnapshotError("rollback_snapshot_copy_failed") from exc


def _provenance(plan: SnapshotPlan) -> dict[str, Any]:
    mimo = next(
        item
        for item in plan.runtime_files
        if item.destination == MIMO_RESPONSE_AGENT_PROFILE_PATH
    )
    source_manifest_paths = {item.path for item in plan.source_manifest.files}
    selected_product_paths = {item.destination for item in plan.product_files}
    return {
        "schema_version": SNAPSHOT_SCHEMA,
        "rollback_release_id": plan.rollback_release_id,
        "source_release": {
            "current_root": str(plan.current_root),
            "release_id": plan.source_manifest.release_id,
            "manifest_digest": plan.source_manifest.digest,
            "source_commit": plan.source_manifest.source_commit,
            "signature_namespace": RELEASE_SIGNATURE_NAMESPACE,
            "signer_identity": plan.signer_identity,
            "manifest_paths_not_selected_as_product": sorted(
                source_manifest_paths - selected_product_paths
            ),
        },
        "product_files": [item.provenance() for item in plan.product_files],
        "split_runtime_files": [item.provenance() for item in plan.runtime_files],
        "mimo_profile_disclosure": {
            "destination": MIMO_RESPONSE_AGENT_PROFILE_PATH,
            "effective_at_capture": mimo.effective_at_capture,
            "role": mimo.role,
            "statement": (
                "The profile was effective in the captured split runtime."
                if mimo.effective_at_capture
                else "The profile was absent from the effective split runtime and is included "
                "only as a committed compatibility sentinel required by the unified release "
                "profile; it is not evidence that the profile was previously active."
            ),
        },
        "excluded_unbound_entries": {
            "acknowledged": True,
            "acknowledgement_required": bool(plan.unbound_entries),
            "contents_read": False,
            "count": len(plan.unbound_entries),
            "digest": plan.unbound_digest,
            "records": [item.record() for item in plan.unbound_entries],
        },
    }


def _validate_private_parent(path: Path) -> Path:
    parent = path.parent
    try:
        parent = parent.resolve(strict=True)
        info = parent.lstat()
    except OSError as exc:
        raise RollbackSnapshotError("rollback_snapshot_output_parent_invalid") from exc
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid not in {0, os.geteuid()}
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        raise RollbackSnapshotError("rollback_snapshot_output_parent_invalid")
    return parent


def capture_snapshot(plan: SnapshotPlan, *, acknowledge_unbound_digest: str | None) -> dict[str, Any]:
    if acknowledge_unbound_digest is not None and not SAFE_DIGEST.fullmatch(acknowledge_unbound_digest):
        raise RollbackSnapshotError("rollback_snapshot_unbound_ack_invalid")
    if plan.unbound_entries and acknowledge_unbound_digest != plan.unbound_digest:
        raise RollbackSnapshotError("rollback_snapshot_unbound_ack_required")
    if os.path.lexists(plan.snapshot_root):
        raise RollbackSnapshotError("rollback_snapshot_output_exists")
    parent = _validate_private_parent(plan.snapshot_root)
    temporary: Path | None = parent / f".{plan.snapshot_root.name}.capture-{uuid.uuid4().hex}"
    try:
        assert temporary is not None
        temporary.mkdir(mode=0o700)
        for item in (*plan.product_files, *plan.runtime_files):
            _copy_bound_file(item, temporary)
        create_release_marker(temporary, plan.rollback_release_id)
        provenance_bytes = _canonical_json(_provenance(plan))
        provenance_path = temporary / PROVENANCE_NAME
        descriptor = os.open(
            provenance_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(provenance_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        provenance_path.chmod(0o644)
        if _scan_unbound_entries(plan.current_root, {
            MANIFEST_MEMBER,
            SIGNATURE_MEMBER,
            *(item.path for item in plan.source_manifest.files),
        }) != plan.unbound_entries:
            raise RollbackSnapshotError("rollback_snapshot_source_inventory_changed")
        verify_snapshot(temporary, allow_git_metadata=False)
        if os.path.lexists(plan.snapshot_root):
            raise RollbackSnapshotError("rollback_snapshot_output_exists")
        os.rename(temporary, plan.snapshot_root)
        temporary = None
        directory_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except SnapshotMarkerError as exc:
        raise RollbackSnapshotError(exc.code) from exc
    except RollbackSnapshotError:
        raise
    except OSError as exc:
        raise RollbackSnapshotError("rollback_snapshot_capture_failed") from exc
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
    result = plan.public_summary(acknowledged_digest=acknowledge_unbound_digest)
    result.update(
        {
            "status": "captured",
            "writes_performed": True,
            "provenance_path": PROVENANCE_NAME,
            "provenance_digest": _sha256_bytes(provenance_bytes),
            "release_id_marker": plan.rollback_release_id,
        }
    )
    return result


def _load_provenance(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 4 * 1024 * 1024:
                raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
            raw = handle.read(4 * 1024 * 1024 + 1)
        value = json.loads(raw.decode("utf-8"))
    except RollbackSnapshotError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise RollbackSnapshotError("rollback_snapshot_provenance_invalid") from exc
    if not isinstance(value, dict) or value.get("schema_version") != SNAPSHOT_SCHEMA:
        raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
    if raw != _canonical_json(value):
        raise RollbackSnapshotError("rollback_snapshot_provenance_not_canonical")
    return value, raw


def _validate_provenance(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if set(value) != {
        "schema_version",
        "rollback_release_id",
        "source_release",
        "product_files",
        "split_runtime_files",
        "mimo_profile_disclosure",
        "excluded_unbound_entries",
    }:
        raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
    rollback_release_id = str(value.get("rollback_release_id") or "")
    if not SAFE_RELEASE_ID.fullmatch(rollback_release_id):
        raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")

    source_release = value.get("source_release")
    if not isinstance(source_release, dict) or set(source_release) != {
        "current_root",
        "release_id",
        "manifest_digest",
        "source_commit",
        "signature_namespace",
        "signer_identity",
        "manifest_paths_not_selected_as_product",
    }:
        raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
    ignored_manifest_paths = source_release.get("manifest_paths_not_selected_as_product")
    if (
        not Path(str(source_release.get("current_root") or "")).is_absolute()
        or not SAFE_RELEASE_ID.fullmatch(str(source_release.get("release_id") or ""))
        or not SAFE_DIGEST.fullmatch(str(source_release.get("manifest_digest") or ""))
        or not SAFE_COMMIT.fullmatch(str(source_release.get("source_commit") or ""))
        or source_release.get("signature_namespace") != RELEASE_SIGNATURE_NAMESPACE
        or not SAFE_RECORD_ID.fullmatch(str(source_release.get("signer_identity") or ""))
        or not isinstance(ignored_manifest_paths, list)
        or ignored_manifest_paths != sorted(set(str(item) for item in ignored_manifest_paths))
    ):
        raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
    try:
        for path in ignored_manifest_paths:
            _safe_relative_path(path)
    except ReleaseInstallError as exc:
        raise RollbackSnapshotError("rollback_snapshot_provenance_invalid") from exc

    product = value.get("product_files")
    runtime = value.get("split_runtime_files")
    if not isinstance(product, list) or not isinstance(runtime, list) or not product or not runtime:
        raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
    records: dict[str, dict[str, Any]] = {}
    for record, expected_group in [
        *((item, "product") for item in product),
        *((item, "runtime") for item in runtime),
    ]:
        if not isinstance(record, dict) or set(record) not in (
            {
                "destination",
                "effective_at_capture",
                "mode",
                "role",
                "sha256",
                "size_bytes",
                "source_path",
            },
            {
                "destination",
                "effective_at_capture",
                "mode",
                "role",
                "sha256",
                "size_bytes",
                "source_path",
                "source_commit",
            },
        ):
            raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
        destination = str(record.get("destination") or "")
        try:
            destination = _safe_relative_path(destination)
        except ReleaseInstallError as exc:
            raise RollbackSnapshotError("rollback_snapshot_provenance_invalid") from exc
        source_path = Path(str(record.get("source_path") or ""))
        digest = str(record.get("sha256") or "")
        mode_text = str(record.get("mode") or "")
        size = record.get("size_bytes")
        effective = record.get("effective_at_capture")
        commit = record.get("source_commit")
        if (
            destination in records
            or not source_path.is_absolute()
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not re.fullmatch(r"0[0-7]{3}", mode_text)
            or int(mode_text, 8) not in SAFE_FILE_MODES
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or not isinstance(effective, bool)
            or (commit is not None and not SAFE_COMMIT.fullmatch(str(commit)))
        ):
            raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
        if expected_group == "product":
            if (
                not destination.startswith(PRODUCT_PREFIXES)
                or record.get("role") != "signed-source-manifest"
                or effective is not True
                or commit is None
            ):
                raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
        elif destination not in SPLIT_RUNTIME_PATHS:
            raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
        records[destination] = record
    if (
        not {"backend/main.py", "frontend/dist/index.html"}.issubset(records)
        or set(SPLIT_RUNTIME_PATHS) - set(records)
    ):
        raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")

    mimo_record = records[MIMO_RESPONSE_AGENT_PROFILE_PATH]
    mimo_disclosure = value.get("mimo_profile_disclosure")
    if not isinstance(mimo_disclosure, dict) or set(mimo_disclosure) != {
        "destination",
        "effective_at_capture",
        "role",
        "statement",
    }:
        raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
    expected_statement = (
        "The profile was effective in the captured split runtime."
        if mimo_record["effective_at_capture"]
        else "The profile was absent from the effective split runtime and is included "
        "only as a committed compatibility sentinel required by the unified release "
        "profile; it is not evidence that the profile was previously active."
    )
    if (
        mimo_disclosure.get("destination") != MIMO_RESPONSE_AGENT_PROFILE_PATH
        or mimo_disclosure.get("effective_at_capture")
        is not mimo_record["effective_at_capture"]
        or mimo_disclosure.get("role") != mimo_record.get("role")
        or mimo_disclosure.get("statement") != expected_statement
        or (
            mimo_record["effective_at_capture"] is True
            and mimo_record.get("role") != "effective-split-runtime"
        )
        or (
            mimo_record["effective_at_capture"] is False
            and (
                mimo_record.get("role") != "compatibility-sentinel-not-active-at-capture"
                or mimo_record.get("source_commit") is None
            )
        )
    ):
        raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
    for destination in EFFECTIVE_RUNTIME_PATHS:
        record = records[destination]
        if (
            record.get("role") != "effective-split-runtime"
            or record.get("effective_at_capture") is not True
        ):
            raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")

    excluded = value.get("excluded_unbound_entries")
    if not isinstance(excluded, dict) or set(excluded) != {
        "acknowledged",
        "acknowledgement_required",
        "contents_read",
        "count",
        "digest",
        "records",
    }:
        raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
    unbound_records = excluded.get("records")
    if (
        excluded.get("acknowledged") is not True
        or excluded.get("contents_read") is not False
        or not isinstance(unbound_records, list)
        or isinstance(excluded.get("count"), bool)
        or excluded.get("count") != len(unbound_records)
        or excluded.get("acknowledgement_required") is not bool(unbound_records)
        or excluded.get("digest") != _sha256_bytes(_canonical_json(unbound_records))
    ):
        raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
    for record in unbound_records:
        if not isinstance(record, dict) or set(record) != {
            "kind",
            "mode",
            "mtime_ns",
            "path",
            "size_bytes",
        }:
            raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
        try:
            _inventory_relative_path(str(record.get("path") or ""))
        except RollbackSnapshotError as exc:
            raise RollbackSnapshotError("rollback_snapshot_provenance_invalid") from exc
        if (
            record.get("kind") not in {"directory", "file", "symlink", "special"}
            or not re.fullmatch(r"0[0-7]{3,5}", str(record.get("mode") or ""))
            or isinstance(record.get("mtime_ns"), bool)
            or not isinstance(record.get("mtime_ns"), int)
            or isinstance(record.get("size_bytes"), bool)
            or not isinstance(record.get("size_bytes"), int)
            or record.get("size_bytes") < 0
        ):
            raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
    return records


def verify_snapshot(snapshot_root: Path, *, allow_git_metadata: bool = True) -> dict[str, Any]:
    snapshot_root = _validate_direct_directory(snapshot_root, "rollback_snapshot_root_invalid")
    provenance, raw_provenance = _load_provenance(snapshot_root / PROVENANCE_NAME)
    rollback_release_id = str(provenance.get("rollback_release_id") or "")
    if not SAFE_RELEASE_ID.fullmatch(rollback_release_id):
        raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
    records = _validate_provenance(provenance)
    expected_files = {PROVENANCE_NAME, "RELEASE_ID", *records}
    actual_entries = _scan_unbound_entries(
        snapshot_root,
        expected_files,
        ignore_git_metadata=allow_git_metadata,
    )
    if actual_entries:
        raise RollbackSnapshotError("rollback_snapshot_output_file_set_mismatch")
    try:
        marker = (snapshot_root / "RELEASE_ID").read_bytes()
    except OSError as exc:
        raise RollbackSnapshotError("rollback_snapshot_release_id_marker_invalid") from exc
    if marker != f"{rollback_release_id}\n".encode("ascii"):
        raise RollbackSnapshotError("rollback_snapshot_release_id_marker_invalid")
    for destination, value in records.items():
        digest = str(value.get("sha256") or "")
        mode_text = str(value.get("mode") or "")
        size = value.get("size_bytes")
        if (
            not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not re.fullmatch(r"0[0-7]{3}", mode_text)
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
        ):
            raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
        mode = int(mode_text, 8)
        if mode not in SAFE_FILE_MODES:
            raise RollbackSnapshotError("rollback_snapshot_provenance_invalid")
        _stable_bound_file(
            _safe_source(snapshot_root, destination),
            destination=destination,
            role="snapshot-verification",
            effective_at_capture=bool(value.get("effective_at_capture")),
            expected_sha256=digest,
            expected_size=size,
            expected_mode=mode,
        )
    return {
        "schema_version": SNAPSHOT_SCHEMA,
        "status": "verified",
        "writes_performed": False,
        "rollback_release_id": rollback_release_id,
        "file_count": len(expected_files),
        "provenance_digest": _sha256_bytes(raw_provenance),
        "git_metadata_excluded": bool(allow_git_metadata and (snapshot_root / ".git").exists()),
    }


def _common_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--current-root", required=True, type=Path)
    parser.add_argument("--snapshot-root", required=True, type=Path)
    parser.add_argument("--rollback-release-id", required=True)
    parser.add_argument("--allowed-signers", required=True, type=Path)
    parser.add_argument("--signer-identity", required=True)
    parser.add_argument("--ssh-keygen", type=Path, default=Path(shutil.which("ssh-keygen") or "/usr/bin/ssh-keygen"))
    parser.add_argument("--runtime-map", action="append", default=[])
    mimo = parser.add_mutually_exclusive_group(required=True)
    mimo.add_argument("--mimo-effective-source", type=Path)
    mimo.add_argument("--mimo-sentinel-source", type=Path)
    parser.add_argument("--mimo-sentinel-commit")
    parser.add_argument("--mimo-sentinel-sha256")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="read-only validation and pollution inventory")
    _common_parser(plan)
    plan.add_argument("--acknowledge-unbound-digest")
    capture = commands.add_parser("capture", help="write one isolated local snapshot")
    _common_parser(capture)
    capture.add_argument("--acknowledge-unbound-digest")
    verify = commands.add_parser("verify", help="verify an existing snapshot tree")
    verify.add_argument("--snapshot-root", required=True, type=Path)
    verify.add_argument("--no-git-metadata", action="store_true")
    return parser


def _plan_from_args(args: argparse.Namespace) -> SnapshotPlan:
    return plan_snapshot(
        current_root=args.current_root,
        snapshot_root=args.snapshot_root,
        rollback_release_id=args.rollback_release_id,
        allowed_signers=args.allowed_signers,
        signer_identity=args.signer_identity,
        ssh_keygen=args.ssh_keygen,
        runtime_maps=_parse_runtime_maps(args.runtime_map),
        mimo_effective_source=args.mimo_effective_source,
        mimo_sentinel_source=args.mimo_sentinel_source,
        mimo_sentinel_commit=args.mimo_sentinel_commit,
        mimo_sentinel_sha256=args.mimo_sentinel_sha256,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "verify":
            result = verify_snapshot(
                args.snapshot_root,
                allow_git_metadata=not args.no_git_metadata,
            )
        else:
            plan = _plan_from_args(args)
            if args.command == "plan":
                result = plan.public_summary(
                    acknowledged_digest=args.acknowledge_unbound_digest
                )
            else:
                result = capture_snapshot(
                    plan,
                    acknowledge_unbound_digest=args.acknowledge_unbound_digest,
                )
        print(_canonical_json(result).decode("utf-8"))
        return 0 if result.get("status") != "blocked" else 2
    except (RollbackSnapshotError, SnapshotMarkerError, ReleaseInstallError) as exc:
        code = getattr(exc, "code", "rollback_snapshot_failed")
        print(
            _canonical_json(
                {"schema_version": SNAPSHOT_SCHEMA, "status": "failed", "error_type": code}
            ).decode("utf-8"),
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError, subprocess.SubprocessError):
        print(
            _canonical_json(
                {
                    "schema_version": SNAPSHOT_SCHEMA,
                    "status": "failed",
                    "error_type": "rollback_snapshot_failed",
                }
            ).decode("utf-8"),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
