"""Tenant-scoped API for immutable official estimate document packs."""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import stat
from datetime import datetime, timezone
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .attachment_store import AttachmentStorageError, resolve_storage_path
from .database import get_database, transaction
from .estimate_artifact import load_estimate_slot
from .estimate_document_pack import (
    DocumentPackError,
    get_document_artifact,
    issue_document_pack,
    load_document_issue,
)
from .product_access import ConstructionEstimateAccessDependency
from .security import require_mutation_auth


router = APIRouter(prefix="/v1/projects", tags=["estimate-document-pack"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = ConstructionEstimateAccessDependency
MutationAuthDependency = Annotated[None, Depends(require_mutation_auth)]
IdempotencyDependency = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=16, max_length=160),
]
PROJECT_ID = re.compile(r"^project_[A-Za-z0-9._~-]{8,96}$")
ARTIFACT_ID = re.compile(r"^estimate_artifact_[A-Za-z0-9]{32}$")
ISSUE_ID = re.compile(r"^estimate_issue_[A-Za-z0-9]{32}$")


class DocumentPackRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    estimate_version: int = Field(alias="estimateVersion", ge=1)
    requested_kinds: list[
        Literal[
            "pack",
            "commercial_offer",
            "local_estimate",
            "resource_statement",
            "conjunctural_analysis",
            "appendix",
            "invoice",
        ]
    ] = Field(default_factory=lambda: ["pack"], alias="requestedKinds", min_length=1, max_length=10)
    mode: Literal["preliminary", "issue"] = "preliminary"


class CounterpartyRequisitesInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    legal_name: Annotated[str, StringConstraints(min_length=1, max_length=240)] = Field(alias="legalName")
    tax_id: Annotated[str, StringConstraints(pattern=r"^(?:[0-9]{10}|[0-9]{12})$")] = Field(alias="taxId")
    registration_code: Annotated[str | None, StringConstraints(pattern=r"^[0-9]{9}$")] = Field(default=None, alias="registrationCode")
    bank_name: Annotated[str, StringConstraints(min_length=1, max_length=240)] = Field(alias="bankName")
    bank_identification_code: Annotated[str, StringConstraints(pattern=r"^[0-9]{9}$")] = Field(alias="bankIdentificationCode")
    settlement_account: Annotated[str, StringConstraints(pattern=r"^[0-9]{20}$")] = Field(alias="settlementAccount")
    correspondent_account: Annotated[str, StringConstraints(pattern=r"^[0-9]{20}$")] = Field(alias="correspondentAccount")
    legal_address: Annotated[str | None, StringConstraints(max_length=500)] = Field(default=None, alias="legalAddress")
    basis: Annotated[str, StringConstraints(min_length=1, max_length=500)]


def _error(status_code: int, code: str, message: str, **extra: object) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, **extra})


def _project_id(project_id: str) -> None:
    if PROJECT_ID.fullmatch(project_id) is None:
        raise _error(status.HTTP_404_NOT_FOUND, "project_not_found", "Проект не найден.")


def _issue_id(issue_id: str) -> None:
    if ISSUE_ID.fullmatch(issue_id) is None:
        raise _error(status.HTTP_404_NOT_FOUND, "document_issue_not_found", "Выпуск документа не найден.")


def _artifact_id(artifact_id: str) -> None:
    if ARTIFACT_ID.fullmatch(artifact_id) is None:
        raise _error(status.HTTP_404_NOT_FOUND, "document_artifact_not_found", "Файл документа не найден.")


def _document_error(exc: DocumentPackError) -> HTTPException:
    extra: dict[str, object] = {}
    if exc.required_fields:
        extra["requiredFields"] = list(exc.required_fields)
    return _error(exc.status_code, exc.code, exc.message, **extra)


@router.post("/{project_id}/estimate/document-pack", status_code=status.HTTP_201_CREATED)
def create_document_pack(
    project_id: str,
    payload: DocumentPackRequest,
    request: Request,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _auth: MutationAuthDependency,
    idempotency_key: IdempotencyDependency,
) -> dict[str, object]:
    _project_id(project_id)
    slot = load_estimate_slot(database, tenant_id=identity.tenant_id, project_id=project_id)
    if slot is None:
        raise _error(status.HTTP_404_NOT_FOUND, "estimate_not_found", "Смета проекта не найдена.")
    document_id = str(slot["id"])
    try:
        issue = issue_document_pack(
            database,
            settings=request.app.state.settings,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            project_id=project_id,
            document_id=document_id,
            estimate_version=payload.estimate_version,
            requested_kinds=payload.requested_kinds,
            mode=payload.mode,
            idempotency_key=idempotency_key,
        )
    except DocumentPackError as exc:
        raise _document_error(exc) from exc
    return issue.view()


@router.get("/{project_id}/estimate/document-pack")
def list_document_packs(
    project_id: str,
    database: DatabaseDependency,
    identity: IdentityDependency,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> dict[str, object]:
    _project_id(project_id)
    rows = database.execute(
        """
        SELECT * FROM estimate_document_issues
        WHERE tenant_id = ? AND project_id = ?
        ORDER BY created_at DESC, id DESC LIMIT ?
        """,
        (identity.tenant_id, project_id, limit),
    ).fetchall()
    return {
        "projectId": project_id,
        "issues": [load_document_issue(database, tenant_id=identity.tenant_id, project_id=project_id, issue_id=str(row["id"])).view() for row in rows],
    }


@router.get("/{project_id}/estimate/document-pack/{issue_id}")
def get_document_pack(
    project_id: str,
    issue_id: str,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, object]:
    _project_id(project_id)
    _issue_id(issue_id)
    issue = load_document_issue(database, tenant_id=identity.tenant_id, project_id=project_id, issue_id=issue_id)
    if issue is None:
        raise _error(status.HTTP_404_NOT_FOUND, "document_issue_not_found", "Выпуск документа не найден.")
    return issue.view()


def _open_verified_content(path: str, *, expected_size: int, expected_hash: str) -> int:
    if expected_size <= 0 or expected_size > 50 * 1024 * 1024:
        raise AttachmentStorageError("document artifact size is invalid")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != expected_size:
            raise AttachmentStorageError("document artifact metadata changed")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        if f"sha256:{digest.hexdigest()}" != expected_hash:
            raise AttachmentStorageError("document artifact hash changed")
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _content_stream(descriptor: int):
    try:
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                return
            yield chunk
    finally:
        os.close(descriptor)


@router.get("/{project_id}/estimate/document-pack/{issue_id}/artifacts/{artifact_id}")
def download_document_artifact(
    project_id: str,
    issue_id: str,
    artifact_id: str,
    request: Request,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> StreamingResponse:
    _project_id(project_id)
    _issue_id(issue_id)
    _artifact_id(artifact_id)
    artifact = get_document_artifact(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
        issue_id=issue_id,
        artifact_id=artifact_id,
    )
    if artifact is None:
        raise _error(status.HTTP_404_NOT_FOUND, "document_artifact_not_found", "Файл документа не найден.")
    try:
        path = resolve_storage_path(request.app.state.settings, str(artifact["storage_ref"]))
        descriptor = _open_verified_content(path.as_posix(), expected_size=int(artifact["size_bytes"]), expected_hash=str(artifact["artifact_hash"]))
    except (AttachmentStorageError, FileNotFoundError, OSError) as exc:
        raise _error(status.HTTP_410_GONE, "document_artifact_missing", "Файл документа больше недоступен.") from exc
    disposition_kind = "inline" if str(artifact["artifact_kind"]) == "pdf" else "attachment"
    return StreamingResponse(
        _content_stream(descriptor),
        media_type=str(artifact["media_type"]),
        headers={
            "Content-Disposition": f'{disposition_kind}; filename="document"; filename*=UTF-8\'\'{quote(str(artifact["filename"]))}',
            "Content-Length": str(artifact["size_bytes"]),
            "ETag": f'"{str(artifact["artifact_hash"]).removeprefix("sha256:")}"',
            "X-Kolibri-Content-SHA256": str(artifact["artifact_hash"]),
            "X-Kolibri-Renderer-Version": str(database.execute("SELECT renderer_version FROM estimate_document_issues WHERE tenant_id = ? AND id = ?", (identity.tenant_id, issue_id)).fetchone()[0]),
        },
    )


@router.post("/{project_id}/parties/{role}/requisites")
def save_counterparty_requisites(
    project_id: str,
    role: Literal["client", "contractor"],
    payload: CounterpartyRequisitesInput,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _auth: MutationAuthDependency,
) -> dict[str, object]:
    _project_id(project_id)
    party = database.execute(
        """
        SELECT counterparty_id FROM project_parties
        WHERE tenant_id = ? AND project_id = ? AND role = ?
          AND status = 'active' AND is_primary = 1 LIMIT 1
        """,
        (identity.tenant_id, project_id, role),
    ).fetchone()
    if party is None:
        raise _error(status.HTTP_404_NOT_FOUND, "counterparty_not_found", "Основная сторона проекта не найдена.")
    now = datetime.now(timezone.utc).isoformat()
    with transaction(database, immediate=True):
        database.execute(
            """
            INSERT INTO counterparty_requisites(
                tenant_id, counterparty_id, legal_name, tax_id,
                registration_code, bank_name, bank_identification_code,
                settlement_account, correspondent_account, legal_address,
                basis, created_by_user_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, counterparty_id) DO UPDATE SET
                legal_name = excluded.legal_name,
                tax_id = excluded.tax_id,
                registration_code = excluded.registration_code,
                bank_name = excluded.bank_name,
                bank_identification_code = excluded.bank_identification_code,
                settlement_account = excluded.settlement_account,
                correspondent_account = excluded.correspondent_account,
                legal_address = excluded.legal_address,
                basis = excluded.basis,
                updated_at = excluded.updated_at
            """,
            (
                identity.tenant_id,
                str(party["counterparty_id"]),
                payload.legal_name,
                payload.tax_id,
                payload.registration_code,
                payload.bank_name,
                payload.bank_identification_code,
                payload.settlement_account,
                payload.correspondent_account,
                payload.legal_address,
                payload.basis,
                identity.user_id,
                now,
                now,
            ),
        )
    return {"projectId": project_id, "role": role, "saved": True}


__all__ = ["router"]
