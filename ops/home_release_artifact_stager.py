#!/usr/bin/env python3
"""Inspect and immutably stage a signed bundle in Home's root-only store.

The program never activates a release.  ``inspect`` is local and read-only.
``stage`` is also read-only unless ``--apply`` is explicit; apply publishes a
new root-owned file without replacing any existing artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import tarfile
import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

try:
    from ops.release_controller import ReleaseManifest
    from ops.release_installer import (
        MANIFEST_MEMBER,
        SIGNATURE_MEMBER,
        ReleaseInstallError,
        _safe_relative_path,
        _validate_artifact_uri,
        load_canonical_manifest,
    )
except ImportError:  # installed standalone beside release modules
    from release_controller import ReleaseManifest  # type: ignore[no-redef]
    from release_installer import (  # type: ignore[no-redef]
        MANIFEST_MEMBER,
        SIGNATURE_MEMBER,
        ReleaseInstallError,
        _safe_relative_path,
        _validate_artifact_uri,
        load_canonical_manifest,
    )


SCHEMA_VERSION = "kolibri.home-release-artifact-stage.v1"
DEFAULT_ROOT = Path("/var/lib/kolibri-release/artifacts")
HASH_CHUNK_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_BUNDLE_BYTES = 2 * 1024 * 1024 * 1024


class ArtifactStageError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class BundleInspection:
    release_id: str
    artifact_uri: str
    artifact_relative: str
    manifest_digest: str
    bundle_sha256: str
    size_bytes: int

    def payload(self, *, status: str = "inspected") -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "writes_performed": False,
            "release_id": self.release_id,
            "artifact_uri": self.artifact_uri,
            "artifact_relative": self.artifact_relative,
            "manifest_digest": self.manifest_digest,
            "bundle_sha256": self.bundle_sha256,
            "size_bytes": self.size_bytes,
        }


def _open_stable_regular(path: Path, *, code: str) -> tuple[BinaryIO, os.stat_result]:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        handle = os.fdopen(descriptor, "rb")
        value = os.fstat(handle.fileno())
    except OSError as exc:
        raise ArtifactStageError(code) from exc
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_nlink < 1
        or value.st_size <= 0
        or value.st_size > MAX_BUNDLE_BYTES
    ):
        handle.close()
        raise ArtifactStageError(code)
    return handle, value


def _require_unchanged(handle: BinaryIO, before: os.stat_result, *, code: str) -> None:
    try:
        after = os.fstat(handle.fileno())
    except OSError as exc:
        raise ArtifactStageError(code) from exc
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ArtifactStageError(code)


def _artifact_relative(uri: str) -> str:
    try:
        parsed = _validate_artifact_uri(uri)
        logical = "/".join(part for part in (parsed.netloc, parsed.path.lstrip("/")) if part)
        return _safe_relative_path(urllib.parse.unquote(logical))
    except ReleaseInstallError as exc:
        raise ArtifactStageError("release_artifact_uri_invalid") from exc


def inspect_bundle(path: Path) -> BundleInspection:
    handle, before = _open_stable_regular(path, code="release_stage_bundle_invalid")
    digest = hashlib.sha256()
    try:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
        _require_unchanged(handle, before, code="release_stage_bundle_unstable")
        handle.seek(0)
        try:
            with tarfile.open(fileobj=handle, mode="r:gz") as archive:
                members = archive.getmembers()
                manifest_members = [item for item in members if item.name == MANIFEST_MEMBER]
                signature_members = [item for item in members if item.name == SIGNATURE_MEMBER]
                if (
                    len(manifest_members) != 1
                    or len(signature_members) != 1
                    or not manifest_members[0].isfile()
                    or not signature_members[0].isfile()
                    or manifest_members[0].size <= 0
                    or manifest_members[0].size > MAX_MANIFEST_BYTES
                    or signature_members[0].size <= 0
                ):
                    raise ArtifactStageError("release_stage_bundle_control_members_invalid")
                extracted = archive.extractfile(manifest_members[0])
                if extracted is None:
                    raise ArtifactStageError("release_stage_bundle_manifest_invalid")
                manifest_bytes = extracted.read(MAX_MANIFEST_BYTES + 1)
        except ArtifactStageError:
            raise
        except (OSError, tarfile.TarError) as exc:
            raise ArtifactStageError("release_stage_bundle_archive_invalid") from exc
        _require_unchanged(handle, before, code="release_stage_bundle_unstable")
    finally:
        handle.close()
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise ArtifactStageError("release_stage_bundle_manifest_invalid")
    try:
        with tempfile.TemporaryDirectory(prefix="kolibri-release-stage-inspect-") as temporary:
            manifest_path = Path(temporary) / "manifest.json"
            descriptor = os.open(manifest_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(manifest_bytes)
            parsed = load_canonical_manifest(manifest_path)
        manifest = ReleaseManifest.from_payload(parsed.payload)
        manifest.validate()
    except ArtifactStageError:
        raise
    except (OSError, TypeError, ValueError, ReleaseInstallError) as exc:
        raise ArtifactStageError("release_stage_bundle_manifest_invalid") from exc
    relative = _artifact_relative(manifest.artifact_uri)
    return BundleInspection(
        release_id=manifest.release_id,
        artifact_uri=manifest.artifact_uri,
        artifact_relative=relative,
        manifest_digest=manifest.digest,
        bundle_sha256=digest.hexdigest(),
        size_bytes=before.st_size,
    )


def _require_root(root: Path) -> tuple[Path, os.stat_result]:
    try:
        value = root.lstat()
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise ArtifactStageError("release_stage_artifact_root_unavailable") from exc
    trusted_uid = 0 if root == DEFAULT_ROOT else os.geteuid()
    if (
        not stat.S_ISDIR(value.st_mode)
        or value.st_uid != trusted_uid
        or stat.S_IMODE(value.st_mode) & 0o077
        or resolved != root.absolute()
    ):
        raise ArtifactStageError("release_stage_artifact_root_unsafe")
    return resolved, value


def _safe_relative(value: str) -> str:
    try:
        relative = _safe_relative_path(value)
    except ReleaseInstallError as exc:
        raise ArtifactStageError("release_stage_artifact_relative_invalid") from exc
    if not relative.startswith("bundles/") or not re.fullmatch(r"[A-Za-z0-9._/-]+", relative):
        raise ArtifactStageError("release_stage_artifact_relative_invalid")
    return relative


def _hash_descriptor(descriptor: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with os.fdopen(os.dup(descriptor), "rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def _validate_existing_descriptor(
    descriptor: int,
    *,
    trusted_uid: int,
    expected_sha256: str,
    expected_size: int,
) -> None:
    try:
        value = os.fstat(descriptor)
    except OSError as exc:
        raise ArtifactStageError("release_stage_existing_artifact_unsafe") from exc
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_nlink < 1
        or value.st_uid != trusted_uid
        or stat.S_IMODE(value.st_mode) & 0o077
    ):
        raise ArtifactStageError("release_stage_existing_artifact_unsafe")
    digest, size = _hash_descriptor(descriptor)
    if digest != expected_sha256 or size != expected_size:
        raise ArtifactStageError("release_stage_artifact_collision")


def _read_existing_destination(
    root: Path,
    relative: str,
    *,
    expected_sha256: str,
    expected_size: int,
) -> bool:
    trusted_uid = 0 if root == DEFAULT_ROOT else os.geteuid()
    current_fd = os.open(
        root,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        parts = PurePosixPath(relative).parts
        for component in parts[:-1]:
            try:
                next_fd = os.open(
                    component,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=current_fd,
                )
            except FileNotFoundError:
                return False
            value = os.fstat(next_fd)
            if value.st_uid != trusted_uid or stat.S_IMODE(value.st_mode) & 0o077:
                os.close(next_fd)
                raise ArtifactStageError("release_stage_artifact_directory_unsafe")
            os.close(current_fd)
            current_fd = next_fd
        try:
            existing = os.open(
                parts[-1],
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current_fd,
            )
        except FileNotFoundError:
            return False
        try:
            _validate_existing_descriptor(
                existing,
                trusted_uid=trusted_uid,
                expected_sha256=expected_sha256,
                expected_size=expected_size,
            )
        finally:
            os.close(existing)
        return True
    except OSError as exc:
        raise ArtifactStageError("release_stage_existing_artifact_unsafe") from exc
    finally:
        os.close(current_fd)


def _source_descriptor(
    source: Path,
    *,
    expected_sha256: str,
    expected_size: int,
) -> int:
    if len(expected_sha256) != 64 or any(char not in "0123456789abcdef" for char in expected_sha256):
        raise ArtifactStageError("release_stage_expected_digest_invalid")
    if not 0 < expected_size <= MAX_BUNDLE_BYTES:
        raise ArtifactStageError("release_stage_expected_size_invalid")
    try:
        descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        value = os.fstat(descriptor)
    except OSError as exc:
        raise ArtifactStageError("release_stage_source_invalid") from exc
    trusted_uid = 0 if os.geteuid() == 0 else os.geteuid()
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_nlink != 1
        or value.st_uid != trusted_uid
        or value.st_size != expected_size
        or stat.S_IMODE(value.st_mode) & 0o077
    ):
        os.close(descriptor)
        raise ArtifactStageError("release_stage_source_invalid")
    digest, size = _hash_descriptor(descriptor)
    if digest != expected_sha256 or size != expected_size:
        os.close(descriptor)
        raise ArtifactStageError("release_stage_source_digest_mismatch")
    os.lseek(descriptor, 0, os.SEEK_SET)
    return descriptor


def _open_or_create_directories(root: Path, parts: tuple[str, ...]) -> tuple[int, int]:
    trusted_uid = 0 if root == DEFAULT_ROOT else os.geteuid()
    root_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    current_fd = root_fd
    try:
        for component in parts:
            try:
                os.mkdir(component, mode=0o700, dir_fd=current_fd)
            except FileExistsError:
                pass
            next_fd = os.open(
                component,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current_fd,
            )
            value = os.fstat(next_fd)
            if value.st_uid != trusted_uid or stat.S_IMODE(value.st_mode) & 0o077:
                os.close(next_fd)
                raise ArtifactStageError("release_stage_artifact_directory_unsafe")
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
        return root_fd, current_fd
    except Exception:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)
        raise


def stage_artifact(
    *,
    source: Path | None,
    artifact_relative: str,
    expected_sha256: str,
    expected_size: int,
    root: Path = DEFAULT_ROOT,
    apply: bool = False,
) -> dict[str, Any]:
    root, _root_value = _require_root(root)
    relative = _safe_relative(artifact_relative)
    if not apply:
        exists = _read_existing_destination(
            root,
            relative,
            expected_sha256=expected_sha256,
            expected_size=expected_size,
        )
        status = "already_staged" if exists else "planned"
        return {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "writes_performed": False,
            "artifact_relative": relative,
            "bundle_sha256": expected_sha256,
            "size_bytes": expected_size,
            "target_node": "home",
        }
    if source is None:
        raise ArtifactStageError("release_stage_source_required")
    source_fd = _source_descriptor(
        source,
        expected_sha256=expected_sha256,
        expected_size=expected_size,
    )
    root_fd: int | None = None
    directory_fd: int | None = None
    temporary_name: str | None = None
    try:
        parts = PurePosixPath(relative).parts
        root_fd, directory_fd = _open_or_create_directories(root, parts[:-1])
        final_name = parts[-1]
        try:
            existing = os.open(
                final_name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
        except FileNotFoundError:
            existing = None
        if existing is not None:
            try:
                _validate_existing_descriptor(
                    existing,
                    trusted_uid=0 if root == DEFAULT_ROOT else os.geteuid(),
                    expected_sha256=expected_sha256,
                    expected_size=expected_size,
                )
            finally:
                os.close(existing)
            return {
                "schema_version": SCHEMA_VERSION,
                "status": "already_staged",
                "writes_performed": False,
                "artifact_relative": relative,
                "bundle_sha256": expected_sha256,
                "size_bytes": expected_size,
                "target_node": "home",
            }
        temporary_name = f".stage-{secrets.token_hex(12)}.tmp"
        output_fd = os.open(
            temporary_name,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory_fd,
        )
        try:
            digest = hashlib.sha256()
            total = 0
            while True:
                chunk = os.read(source_fd, HASH_CHUNK_BYTES)
                if not chunk:
                    break
                view = memoryview(chunk)
                while view:
                    written = os.write(output_fd, view)
                    view = view[written:]
                digest.update(chunk)
                total += len(chunk)
            os.fsync(output_fd)
        finally:
            os.close(output_fd)
        if digest.hexdigest() != expected_sha256 or total != expected_size:
            raise ArtifactStageError("release_stage_copy_digest_mismatch")
        try:
            os.link(
                temporary_name,
                final_name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise ArtifactStageError("release_stage_artifact_collision") from exc
        os.unlink(temporary_name, dir_fd=directory_fd)
        temporary_name = None
        os.fsync(directory_fd)
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "staged",
            "writes_performed": True,
            "artifact_relative": relative,
            "bundle_sha256": expected_sha256,
            "size_bytes": expected_size,
            "target_node": "home",
        }
    finally:
        os.close(source_fd)
        if temporary_name is not None and directory_fd is not None:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except OSError:
                pass
        if directory_fd is not None and directory_fd != root_fd:
            os.close(directory_fd)
        if root_fd is not None:
            os.close(root_fd)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--bundle", required=True)
    stage = commands.add_parser("stage")
    stage.add_argument("--source")
    stage.add_argument("--artifact-relative", required=True)
    stage.add_argument("--expected-sha256", required=True)
    stage.add_argument("--expected-size", type=int, required=True)
    stage.add_argument("--root", default=str(DEFAULT_ROOT))
    stage.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "inspect":
            result = inspect_bundle(Path(args.bundle)).payload()
        else:
            result = stage_artifact(
                source=Path(args.source) if args.source else None,
                artifact_relative=args.artifact_relative,
                expected_sha256=args.expected_sha256,
                expected_size=args.expected_size,
                root=Path(args.root),
                apply=args.apply,
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except ArtifactStageError as exc:
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "error_type": exc.code,
        }, sort_keys=True), file=sys.stderr)
        return 2
    except (OSError, ValueError, tarfile.TarError):
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "error_type": "release_stage_failed",
        }, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
