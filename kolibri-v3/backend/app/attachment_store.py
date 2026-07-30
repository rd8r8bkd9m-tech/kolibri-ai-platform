"""Bounded content-addressed storage for Product Chat attachments.

The database owns authorization metadata.  This module owns opaque CAS
references and never accepts a caller-supplied filesystem path.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
from collections.abc import AsyncIterable, Iterable
from dataclasses import dataclass
from pathlib import Path

from .config import Settings


ATTACHMENT_CONTRACT_MAX_BYTES = 50 * 1024 * 1024
USER_ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024
_STORAGE_REF = re.compile(
    r"^cas://sha256/(?P<tenant>[0-9a-f]{32})/(?P<digest>[0-9a-f]{64})$"
)


class AttachmentStorageError(RuntimeError):
    pass


class AttachmentTooLargeError(AttachmentStorageError):
    pass


class AttachmentEmptyError(AttachmentStorageError):
    pass


@dataclass(frozen=True, slots=True)
class StoredContent:
    storage_ref: str
    content_hash: str
    size_bytes: int


def _root(settings: Settings) -> Path:
    root = settings.attachment_storage_root
    if root is None:
        raise AttachmentStorageError("attachment storage is not configured")
    return root


def _ensure_private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise AttachmentStorageError(
            "attachment storage directory is not a real directory"
        )
    os.chmod(path, 0o700)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)
    finally:
        os.close(descriptor)


def _prepare_temp(settings: Settings) -> tuple[int, Path]:
    descriptor = -1
    filename: str | None = None
    try:
        root = _root(settings)
        _ensure_private_directory(root)
        temp_root = root / ".tmp"
        _ensure_private_directory(temp_root)
        descriptor, filename = tempfile.mkstemp(
            prefix=".attachment-",
            dir=temp_root,
        )
        os.fchmod(descriptor, 0o600)
        return descriptor, Path(filename)
    except OSError as exc:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if filename is not None:
            try:
                Path(filename).unlink(missing_ok=True)
            except OSError:
                pass
        raise AttachmentStorageError(
            "attachment storage could not create a temporary file"
        ) from exc


def _discard_temp(descriptor: int, temp_path: Path) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass
    try:
        temp_path.unlink(missing_ok=True)
    except OSError:
        pass


def _validated_limit(max_bytes: int) -> int:
    if (
        isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or not 1 <= max_bytes <= ATTACHMENT_CONTRACT_MAX_BYTES
    ):
        raise ValueError("attachment byte limit is invalid")
    return max_bytes


def _write_chunk(
    descriptor: int,
    digest: hashlib._Hash,
    chunk: bytes | bytearray | memoryview,
    *,
    size_bytes: int,
    max_bytes: int,
) -> int:
    if not isinstance(chunk, (bytes, bytearray, memoryview)):
        raise AttachmentStorageError("attachment stream yielded non-bytes")
    value = bytes(chunk)
    next_size = size_bytes + len(value)
    if next_size > max_bytes:
        raise AttachmentTooLargeError("attachment exceeds the byte limit")
    if value:
        digest.update(value)
        view = memoryview(value)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise AttachmentStorageError("attachment write failed")
            view = view[written:]
    return next_size


def _finalize(
    settings: Settings,
    *,
    tenant_id: str,
    descriptor: int,
    temp_path: Path,
    digest: hashlib._Hash,
    size_bytes: int,
) -> StoredContent:
    if size_bytes < 1:
        raise AttachmentEmptyError("attachment is empty")
    os.fsync(descriptor)
    os.close(descriptor)
    descriptor = -1

    content_digest = digest.hexdigest()
    tenant_digest = hashlib.sha256(
        tenant_id.encode("utf-8", "strict")
    ).hexdigest()[:32]
    root = _root(settings)
    destination = root / tenant_digest / content_digest[:2] / content_digest
    _ensure_private_directory(root / tenant_digest)
    _ensure_private_directory(destination.parent)

    try:
        os.link(temp_path, destination)
        os.chmod(destination, 0o600)
    except FileExistsError:
        metadata = destination.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size != size_bytes
            or _hash_file(destination) != content_digest
        ):
            raise AttachmentStorageError(
                "content-addressed attachment collision"
            ) from None
    finally:
        temp_path.unlink(missing_ok=True)

    return StoredContent(
        storage_ref=f"cas://sha256/{tenant_digest}/{content_digest}",
        content_hash=f"sha256:{content_digest}",
        size_bytes=size_bytes,
    )


def store_content_bytes(
    settings: Settings,
    *,
    tenant_id: str,
    content: bytes,
    max_bytes: int = ATTACHMENT_CONTRACT_MAX_BYTES,
) -> StoredContent:
    """Persist one already-materialized bounded artifact in the shared CAS."""

    limit = _validated_limit(max_bytes)
    descriptor, temp_path = _prepare_temp(settings)
    digest = hashlib.sha256()
    size_bytes = 0
    try:
        size_bytes = _write_chunk(
            descriptor,
            digest,
            content,
            size_bytes=size_bytes,
            max_bytes=limit,
        )
        return _finalize(
            settings,
            tenant_id=tenant_id,
            descriptor=descriptor,
            temp_path=temp_path,
            digest=digest,
            size_bytes=size_bytes,
        )
    except OSError as exc:
        _discard_temp(descriptor, temp_path)
        raise AttachmentStorageError(
            "attachment storage write failed"
        ) from exc
    except BaseException:
        _discard_temp(descriptor, temp_path)
        raise


def store_content_chunks(
    settings: Settings,
    *,
    tenant_id: str,
    chunks: Iterable[bytes],
    max_bytes: int = ATTACHMENT_CONTRACT_MAX_BYTES,
) -> StoredContent:
    limit = _validated_limit(max_bytes)
    descriptor, temp_path = _prepare_temp(settings)
    digest = hashlib.sha256()
    size_bytes = 0
    try:
        for chunk in chunks:
            size_bytes = _write_chunk(
                descriptor,
                digest,
                chunk,
                size_bytes=size_bytes,
                max_bytes=limit,
            )
        return _finalize(
            settings,
            tenant_id=tenant_id,
            descriptor=descriptor,
            temp_path=temp_path,
            digest=digest,
            size_bytes=size_bytes,
        )
    except OSError as exc:
        _discard_temp(descriptor, temp_path)
        raise AttachmentStorageError(
            "attachment storage write failed"
        ) from exc
    except BaseException:
        _discard_temp(descriptor, temp_path)
        raise


async def store_content_stream(
    settings: Settings,
    *,
    tenant_id: str,
    chunks: AsyncIterable[bytes],
    max_bytes: int = ATTACHMENT_CONTRACT_MAX_BYTES,
) -> StoredContent:
    """Stream request bytes to disk while hashing and enforcing the hard cap."""

    limit = _validated_limit(max_bytes)
    descriptor, temp_path = _prepare_temp(settings)
    digest = hashlib.sha256()
    size_bytes = 0
    try:
        async for chunk in chunks:
            size_bytes = _write_chunk(
                descriptor,
                digest,
                chunk,
                size_bytes=size_bytes,
                max_bytes=limit,
            )
        return _finalize(
            settings,
            tenant_id=tenant_id,
            descriptor=descriptor,
            temp_path=temp_path,
            digest=digest,
            size_bytes=size_bytes,
        )
    except OSError as exc:
        _discard_temp(descriptor, temp_path)
        raise AttachmentStorageError(
            "attachment storage write failed"
        ) from exc
    except BaseException:
        _discard_temp(descriptor, temp_path)
        raise


def resolve_storage_path(settings: Settings, storage_ref: str) -> Path:
    """Resolve only a server-created CAS reference beneath the configured root."""

    match = _STORAGE_REF.fullmatch(storage_ref)
    if match is None:
        raise AttachmentStorageError("attachment storage reference is invalid")
    root = _root(settings).resolve()
    path = (
        root
        / match.group("tenant")
        / match.group("digest")[:2]
        / match.group("digest")
    ).resolve()
    if not path.is_relative_to(root):
        raise AttachmentStorageError("attachment storage reference escaped root")
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise AttachmentStorageError("attachment content is not a regular file")
    return path


__all__ = [
    "ATTACHMENT_CONTRACT_MAX_BYTES",
    "USER_ATTACHMENT_MAX_BYTES",
    "AttachmentEmptyError",
    "AttachmentStorageError",
    "AttachmentTooLargeError",
    "StoredContent",
    "resolve_storage_path",
    "store_content_bytes",
    "store_content_chunks",
    "store_content_stream",
]
