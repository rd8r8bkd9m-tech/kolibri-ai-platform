"""Immutable metadata and message references for bounded attachments."""

from __future__ import annotations

import hashlib
import re
import sqlite3
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

from .attachment_store import StoredContent, resolve_storage_path
from .config import Settings


ALLOWED_USER_MIME_TYPES: dict[str, frozenset[str]] = {
    "application/json": frozenset({".json"}),
    "application/pdf": frozenset({".pdf"}),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (
        frozenset({".xlsx"})
    ),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        frozenset({".docx"})
    ),
    "image/gif": frozenset({".gif"}),
    "image/heic": frozenset({".heic"}),
    "image/heif": frozenset({".heif"}),
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "image/png": frozenset({".png"}),
    "image/webp": frozenset({".webp"}),
    "text/csv": frozenset({".csv"}),
    "text/markdown": frozenset({".md", ".markdown"}),
    "text/plain": frozenset({".txt", ".log"}),
}
ATTACHMENT_ACCEPT_ATTRIBUTE = ",".join(sorted(ALLOWED_USER_MIME_TYPES))
MAX_ATTACHMENTS_PER_MESSAGE = 10
_ATTACHMENT_ID = re.compile(
    r"^attachment_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$"
)
_ARTIFACT_ID = re.compile(
    r"^artifact_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$"
)
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{15,159}$")
_CONTENT_PATH = re.compile(
    r"^/api/product/v1/attachments/"
    r"(?P<attachment_id>attachment_[A-Za-z0-9][A-Za-z0-9._~-]{5,127})"
    r"/content$"
)


class AttachmentMetadataError(ValueError):
    pass


class AttachmentScopeError(LookupError):
    pass


class AttachmentConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AttachmentRecord:
    tenant_id: str
    user_id: str
    project_id: str
    thread_id: str
    attachment_id: str
    artifact_id: str
    artifact_version: int
    content_hash: str
    filename: str
    mime_type: str
    size_bytes: int
    storage_ref: str
    status: str
    created_by_user_id: str
    created_at: str

    @property
    def content_path(self) -> str:
        return (
            f"/api/product/v1/attachments/{self.attachment_id}/content"
        )


@dataclass(frozen=True, slots=True)
class RequestedAttachmentRef:
    attachment_id: str
    filename: str
    mime_type: str


def normalize_mime_type(value: str) -> str:
    mime_type = value.split(";", 1)[0].strip().lower()
    if mime_type not in ALLOWED_USER_MIME_TYPES:
        raise AttachmentMetadataError("attachment MIME type is not supported")
    return mime_type


def normalize_filename(value: str, *, mime_type: str) -> str:
    filename = unicodedata.normalize("NFC", value).strip()
    if (
        not 1 <= len(filename) <= 240
        or filename in {".", ".."}
        or any(
            character in filename
            for character in ("/", "\\", "\0", "\r", "\n")
        )
    ):
        raise AttachmentMetadataError("attachment filename is invalid")
    suffix = Path(filename).suffix.casefold()
    if suffix not in ALLOWED_USER_MIME_TYPES[mime_type]:
        raise AttachmentMetadataError(
            "attachment filename does not match its MIME type"
        )
    return filename


def validate_idempotency_key(value: str) -> str:
    if _IDEMPOTENCY_KEY.fullmatch(value) is None:
        raise AttachmentMetadataError("attachment idempotency key is invalid")
    return value


def validate_attachment_id(value: str) -> str:
    if _ATTACHMENT_ID.fullmatch(value) is None:
        raise AttachmentMetadataError("attachment identifier is invalid")
    return value


def _row_record(row: sqlite3.Row) -> AttachmentRecord:
    return AttachmentRecord(
        tenant_id=str(row["tenant_id"]),
        user_id=str(row["user_id"]),
        project_id=str(row["project_id"]),
        thread_id=str(row["thread_id"]),
        attachment_id=str(row["id"]),
        artifact_id=str(row["artifact_id"]),
        artifact_version=int(row["artifact_version"]),
        content_hash=str(row["content_hash"]),
        filename=str(row["filename"]),
        mime_type=str(row["mime_type"]),
        size_bytes=int(row["size_bytes"]),
        storage_ref=str(row["storage_ref"]),
        status=str(row["status"]),
        created_by_user_id=str(row["created_by_user_id"]),
        created_at=str(row["created_at"]),
    )


def find_idempotent_attachment(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str,
    idempotency_key: str,
) -> AttachmentRecord | None:
    row = database.execute(
        """
        SELECT *
        FROM product_attachments
        WHERE tenant_id = ? AND user_id = ? AND upload_idempotency_key = ?
        LIMIT 1
        """,
        (tenant_id, user_id, idempotency_key),
    ).fetchone()
    return None if row is None else _row_record(row)


def get_attachment(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str,
    attachment_id: str,
) -> AttachmentRecord | None:
    row = database.execute(
        """
        SELECT *
        FROM product_attachments
        WHERE tenant_id = ? AND user_id = ? AND id = ? AND status = 'available'
        LIMIT 1
        """,
        (tenant_id, user_id, attachment_id),
    ).fetchone()
    return None if row is None else _row_record(row)


def persist_attachment_record(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str,
    project_id: str,
    thread_id: str,
    filename: str,
    mime_type: str,
    stored: StoredContent,
    idempotency_key: str,
    created_at: str,
    attachment_id: str | None = None,
    artifact_id: str | None = None,
    artifact_version: int = 1,
    created_by_user_id: str | None = None,
) -> AttachmentRecord:
    """Insert immutable metadata inside the caller's existing transaction."""

    idempotency_key = validate_idempotency_key(idempotency_key)
    attachment_id = validate_attachment_id(
        attachment_id or f"attachment_{uuid.uuid4().hex}"
    )
    artifact_id = artifact_id or f"artifact_{uuid.uuid4().hex}"
    if _ARTIFACT_ID.fullmatch(artifact_id) is None:
        raise AttachmentMetadataError("artifact identifier is invalid")
    if (
        isinstance(artifact_version, bool)
        or not isinstance(artifact_version, int)
        or artifact_version < 1
    ):
        raise AttachmentMetadataError("artifact version is invalid")
    mime_type = normalize_mime_type(mime_type)
    filename = normalize_filename(filename, mime_type=mime_type)
    creator = created_by_user_id or user_id

    scope = database.execute(
        """
        SELECT 1
        FROM projects AS project
        JOIN chat_threads AS thread
          ON thread.tenant_id = project.tenant_id
         AND thread.project_id = project.id
        WHERE project.tenant_id = ?
          AND project.id = ?
          AND thread.id = ?
        LIMIT 1
        """,
        (tenant_id, project_id, thread_id),
    ).fetchone()
    if scope is None:
        raise AttachmentScopeError("attachment project scope was not found")

    database.execute(
        """
        INSERT INTO product_attachments (
            tenant_id, id, user_id, project_id, thread_id,
            artifact_id, artifact_version, content_hash, filename,
            mime_type, size_bytes, storage_ref, upload_idempotency_key,
            status, created_by_user_id, created_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'available', ?, ?
        )
        """,
        (
            tenant_id,
            attachment_id,
            user_id,
            project_id,
            thread_id,
            artifact_id,
            artifact_version,
            stored.content_hash,
            filename,
            mime_type,
            stored.size_bytes,
            stored.storage_ref,
            idempotency_key,
            creator,
            created_at,
        ),
    )
    record = get_attachment(
        database,
        tenant_id=tenant_id,
        user_id=user_id,
        attachment_id=attachment_id,
    )
    if record is None:
        raise AttachmentConflictError("attachment metadata was not persisted")
    return record


def attachment_view(record: AttachmentRecord) -> dict[str, object]:
    def contract_identity(prefix: str, value: str) -> str:
        if re.fullmatch(
            r"^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$",
            value,
        ):
            return value
        try:
            suffix = uuid.UUID(value).hex
        except ValueError:
            suffix = hashlib.sha256(
                value.encode("utf-8", "strict")
            ).hexdigest()
        return f"{prefix}_{suffix}"

    return {
        "schema_id": "kolibri.product.attachment",
        "schema_version": "1.0",
        "tenant_id": contract_identity("tenant", record.tenant_id),
        "user_id": contract_identity("user", record.user_id),
        "project_id": record.project_id,
        "attachment_id": record.attachment_id,
        "artifact_id": record.artifact_id,
        "artifact_version": record.artifact_version,
        "content_hash": record.content_hash,
        "filename": record.filename,
        "mime_type": record.mime_type,
        "size_bytes": record.size_bytes,
        "content_path": record.content_path,
        "status": record.status,
        "created_by": contract_identity("actor", record.created_by_user_id),
        "created_at": record.created_at,
    }


def parse_requested_attachment(
    *,
    data: str,
    filename: str,
    mime_type: str,
) -> RequestedAttachmentRef:
    match = _CONTENT_PATH.fullmatch(data)
    if match is None:
        raise AttachmentMetadataError("attachment content path is invalid")
    normalized_mime = normalize_mime_type(mime_type)
    return RequestedAttachmentRef(
        attachment_id=match.group("attachment_id"),
        filename=normalize_filename(filename, mime_type=normalized_mime),
        mime_type=normalized_mime,
    )


def resolve_requested_attachments(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str,
    project_id: str,
    thread_id: str,
    requested: list[RequestedAttachmentRef],
) -> list[AttachmentRecord]:
    if len(requested) > MAX_ATTACHMENTS_PER_MESSAGE:
        raise AttachmentMetadataError("too many attachments in one message")
    if len({item.attachment_id for item in requested}) != len(requested):
        raise AttachmentMetadataError("attachment references must be unique")

    records: list[AttachmentRecord] = []
    for item in requested:
        record = get_attachment(
            database,
            tenant_id=tenant_id,
            user_id=user_id,
            attachment_id=item.attachment_id,
        )
        if (
            record is None
            or record.project_id != project_id
            or record.thread_id != thread_id
        ):
            raise AttachmentScopeError("attachment was not found in this scope")
        if (
            record.filename != item.filename
            or record.mime_type != item.mime_type
        ):
            raise AttachmentConflictError("attachment metadata does not match")
        records.append(record)
    return records


def bind_message_attachment_refs(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    message_id: str,
    records: list[AttachmentRecord],
    created_at: str,
) -> None:
    existing = database.execute(
        """
        SELECT attachment_id
        FROM chat_message_attachment_refs
        WHERE tenant_id = ? AND message_id = ?
        ORDER BY position
        """,
        (tenant_id, message_id),
    ).fetchall()
    existing_ids = [str(row["attachment_id"]) for row in existing]
    requested_ids = [record.attachment_id for record in records]
    if existing_ids:
        if existing_ids != requested_ids:
            raise AttachmentConflictError(
                "message attachment references do not match"
            )
        return
    if not records:
        return
    database.executemany(
        """
        INSERT INTO chat_message_attachment_refs (
            tenant_id, message_id, position, attachment_id, artifact_id,
            artifact_version, content_hash, filename, mime_type, size_bytes,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                tenant_id,
                message_id,
                position,
                record.attachment_id,
                record.artifact_id,
                record.artifact_version,
                record.content_hash,
                record.filename,
                record.mime_type,
                record.size_bytes,
                created_at,
            )
            for position, record in enumerate(records)
        ],
    )


def validate_content_signature(
    settings: Settings,
    *,
    stored: StoredContent,
    mime_type: str,
) -> None:
    """Reject common active-content spoofing for structured binary formats."""

    path = resolve_storage_path(settings, stored.storage_ref)
    with path.open("rb") as stream:
        prefix = stream.read(16)
    valid = {
        "application/pdf": prefix.startswith(b"%PDF-"),
        "image/gif": prefix.startswith((b"GIF87a", b"GIF89a")),
        "image/jpeg": prefix.startswith(b"\xff\xd8\xff"),
        "image/png": prefix.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": (
            len(prefix) >= 12
            and prefix[:4] == b"RIFF"
            and prefix[8:12] == b"WEBP"
        ),
        "image/heic": len(prefix) >= 12 and prefix[4:8] == b"ftyp",
        "image/heif": len(prefix) >= 12 and prefix[4:8] == b"ftyp",
        (
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ): prefix.startswith(b"PK\x03\x04"),
        (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ): prefix.startswith(b"PK\x03\x04"),
    }.get(mime_type, True)
    if not valid:
        raise AttachmentMetadataError(
            "attachment bytes do not match the declared MIME type"
        )


__all__ = [
    "ALLOWED_USER_MIME_TYPES",
    "ATTACHMENT_ACCEPT_ATTRIBUTE",
    "MAX_ATTACHMENTS_PER_MESSAGE",
    "AttachmentConflictError",
    "AttachmentMetadataError",
    "AttachmentRecord",
    "AttachmentScopeError",
    "RequestedAttachmentRef",
    "attachment_view",
    "bind_message_attachment_refs",
    "find_idempotent_attachment",
    "get_attachment",
    "normalize_filename",
    "normalize_mime_type",
    "parse_requested_attachment",
    "persist_attachment_record",
    "resolve_requested_attachments",
    "validate_attachment_id",
    "validate_content_signature",
    "validate_idempotency_key",
]
