"""Authenticated bounded attachment upload and retrieval API."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
from typing import Annotated
from urllib.parse import quote, unquote_to_bytes

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import StreamingResponse

from .attachment_service import (
    ATTACHMENT_ACCEPT_ATTRIBUTE,
    AttachmentConflictError,
    AttachmentMetadataError,
    AttachmentScopeError,
    attachment_view,
    find_idempotent_attachment,
    get_attachment,
    normalize_filename,
    normalize_mime_type,
    persist_attachment_record,
    validate_attachment_id,
    validate_content_signature,
)
from .attachment_store import (
    USER_ATTACHMENT_MAX_BYTES,
    AttachmentEmptyError,
    AttachmentStorageError,
    AttachmentTooLargeError,
    resolve_storage_path,
    store_content_stream,
)
from .chat.service import resolve_thread, utc_now
from .config import Settings
from .database import get_database, transaction
from .identity import require_user
from .schemas import UserSession
from .security import require_mutation_auth


router = APIRouter(prefix="/v1/attachments", tags=["attachments"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = Annotated[UserSession, Depends(require_user)]
MutationAuthDependency = Annotated[None, Depends(require_mutation_auth)]
_STREAM_CHUNK_BYTES = 64 * 1024


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _request_filename(request: Request, *, mime_type: str) -> str:
    raw = request.headers.get("x-kolibri-filename")
    if raw is None or len(raw) > 2_048:
        raise AttachmentMetadataError("attachment filename is required")
    try:
        decoded = unquote_to_bytes(raw).decode("utf-8", "strict")
    except UnicodeError as exc:
        raise AttachmentMetadataError(
            "attachment filename encoding is invalid"
        ) from exc
    return normalize_filename(decoded, mime_type=mime_type)


def _declared_size(request: Request) -> int | None:
    raw = request.headers.get("content-length")
    if raw is None:
        return None
    if not raw.isascii() or not raw.isdecimal() or len(raw) > 12:
        raise AttachmentMetadataError("attachment Content-Length is invalid")
    value = int(raw)
    if value > USER_ATTACHMENT_MAX_BYTES:
        raise AttachmentTooLargeError("attachment exceeds the R1 byte limit")
    if value < 1:
        raise AttachmentEmptyError("attachment is empty")
    return value


def _owned_thread(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    public_thread_id: str,
    project_id: str,
) -> sqlite3.Row:
    thread = resolve_thread(
        database,
        tenant_id=identity.tenant_id,
        public_thread_id=public_thread_id,
    )
    if thread is None or str(thread["project_id"]) != project_id:
        raise AttachmentScopeError("attachment project scope was not found")
    return thread


@router.get("/capabilities")
def attachment_capabilities(
    database: DatabaseDependency,
    identity: IdentityDependency,
    project_id: Annotated[str, Query(alias="projectId", min_length=8, max_length=160)],
    thread_id: Annotated[str, Query(alias="threadId", min_length=8, max_length=160)],
) -> dict[str, object]:
    try:
        thread = _owned_thread(
            database,
            identity=identity,
            public_thread_id=thread_id,
            project_id=project_id,
        )
    except AttachmentScopeError as exc:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "attachment_scope_not_found",
            "Attachment upload is unavailable for this project.",
        ) from exc
    return {
        "schemaId": "kolibri.product.attachment-capabilities",
        "schemaVersion": "1.0",
        "enabled": True,
        "projectId": project_id,
        "threadId": thread_id,
        "canonicalThreadId": str(thread["id"]),
        "accept": ATTACHMENT_ACCEPT_ATTRIBUTE,
        "maxSizeBytes": USER_ATTACHMENT_MAX_BYTES,
        "maxAttachmentsPerMessage": 10,
    }


@router.post("")
async def upload_attachment(
    request: Request,
    response: Response,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _auth: MutationAuthDependency,
) -> dict[str, object]:
    project_id = request.headers.get("x-kolibri-project-id", "")
    public_thread_id = request.headers.get("x-kolibri-thread-id", "")
    idempotency_key = request.headers.get("idempotency-key", "")
    try:
        attachment_id = validate_attachment_id(idempotency_key)
        mime_type = normalize_mime_type(
            request.headers.get("content-type", "")
        )
        filename = _request_filename(request, mime_type=mime_type)
        declared_size = _declared_size(request)
        thread = _owned_thread(
            database,
            identity=identity,
            public_thread_id=public_thread_id,
            project_id=project_id,
        )
    except AttachmentTooLargeError as exc:
        raise _error(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "attachment_too_large",
            "R1 accepts attachments up to 10 MiB.",
        ) from exc
    except AttachmentEmptyError as exc:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "attachment_empty",
            "Attachment content cannot be empty.",
        ) from exc
    except AttachmentMetadataError as exc:
        raise _error(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "attachment_unsupported",
            str(exc),
        ) from exc
    except AttachmentScopeError as exc:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "attachment_scope_not_found",
            "Attachment upload is unavailable for this project.",
        ) from exc

    settings: Settings = request.app.state.settings
    try:
        stored = await store_content_stream(
            settings,
            tenant_id=identity.tenant_id,
            chunks=request.stream(),
            max_bytes=USER_ATTACHMENT_MAX_BYTES,
        )
        if declared_size is not None and declared_size != stored.size_bytes:
            raise AttachmentMetadataError(
                "attachment Content-Length does not match the received bytes"
            )
        validate_content_signature(
            settings,
            stored=stored,
            mime_type=mime_type,
        )
    except AttachmentTooLargeError as exc:
        raise _error(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "attachment_too_large",
            "R1 accepts attachments up to 10 MiB.",
        ) from exc
    except AttachmentEmptyError as exc:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "attachment_empty",
            "Attachment content cannot be empty.",
        ) from exc
    except AttachmentMetadataError as exc:
        raise _error(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "attachment_content_mismatch",
            str(exc),
        ) from exc
    except AttachmentStorageError as exc:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "attachment_storage_unavailable",
            "Attachment storage is temporarily unavailable.",
        ) from exc

    canonical_thread_id = str(thread["id"])
    created = False
    try:
        with transaction(database, immediate=True):
            # Re-check the scope after streaming: project deletion or a tenant
            # switch cannot race the durable metadata commit.
            _owned_thread(
                database,
                identity=identity,
                public_thread_id=public_thread_id,
                project_id=project_id,
            )
            record = find_idempotent_attachment(
                database,
                tenant_id=identity.tenant_id,
                user_id=identity.user_id,
                idempotency_key=idempotency_key,
            )
            if record is None:
                record = persist_attachment_record(
                    database,
                    tenant_id=identity.tenant_id,
                    user_id=identity.user_id,
                    project_id=project_id,
                    thread_id=canonical_thread_id,
                    filename=filename,
                    mime_type=mime_type,
                    stored=stored,
                    idempotency_key=idempotency_key,
                    attachment_id=attachment_id,
                    created_at=utc_now(),
                )
                created = True
            elif (
                record.project_id != project_id
                or record.thread_id != canonical_thread_id
                or record.filename != filename
                or record.mime_type != mime_type
                or record.content_hash != stored.content_hash
                or record.size_bytes != stored.size_bytes
            ):
                raise AttachmentConflictError(
                    "idempotency key was reused with different attachment data"
                )
    except AttachmentConflictError as exc:
        raise _error(
            status.HTTP_409_CONFLICT,
            "attachment_idempotency_conflict",
            "The attachment retry does not match the original upload.",
        ) from exc
    except (AttachmentScopeError, sqlite3.IntegrityError) as exc:
        raise _error(
            status.HTTP_409_CONFLICT,
            "attachment_scope_conflict",
            "Attachment scope changed before it could be saved.",
        ) from exc

    response.status_code = (
        status.HTTP_201_CREATED if created else status.HTTP_200_OK
    )
    response.headers["Location"] = record.content_path
    response.headers["X-Kolibri-Content-SHA256"] = record.content_hash
    return attachment_view(record)


def _open_verified_content(
    path: str,
    *,
    expected_size: int,
    expected_hash: str,
) -> int:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size != expected_size
        ):
            raise AttachmentStorageError("attachment content metadata changed")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, _STREAM_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
        if f"sha256:{digest.hexdigest()}" != expected_hash:
            raise AttachmentStorageError("attachment content hash changed")
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _content_stream(descriptor: int):
    try:
        while True:
            chunk = os.read(descriptor, _STREAM_CHUNK_BYTES)
            if not chunk:
                return
            yield chunk
    finally:
        os.close(descriptor)


@router.get("/{attachment_id}/content")
def attachment_content(
    attachment_id: str,
    request: Request,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> StreamingResponse:
    try:
        attachment_id = validate_attachment_id(attachment_id)
    except AttachmentMetadataError as exc:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "attachment_not_found",
            "Attachment was not found.",
        ) from exc
    record = get_attachment(
        database,
        tenant_id=identity.tenant_id,
        user_id=identity.user_id,
        attachment_id=attachment_id,
    )
    if record is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "attachment_not_found",
            "Attachment was not found.",
        )
    try:
        path = resolve_storage_path(
            request.app.state.settings,
            record.storage_ref,
        )
        descriptor = _open_verified_content(
            str(path),
            expected_size=record.size_bytes,
            expected_hash=record.content_hash,
        )
    except (AttachmentStorageError, FileNotFoundError, OSError) as exc:
        raise _error(
            status.HTTP_410_GONE,
            "attachment_content_missing",
            "Attachment content is no longer available.",
        ) from exc

    disposition = (
        f'inline; filename="attachment"; '
        f"filename*=UTF-8''{quote(record.filename)}"
    )
    return StreamingResponse(
        _content_stream(descriptor),
        media_type=record.mime_type,
        headers={
            "Content-Disposition": disposition,
            "Content-Length": str(record.size_bytes),
            "ETag": f'"{record.content_hash.removeprefix("sha256:")}"',
            "X-Kolibri-Content-SHA256": record.content_hash,
        },
    )


__all__ = ["router"]
