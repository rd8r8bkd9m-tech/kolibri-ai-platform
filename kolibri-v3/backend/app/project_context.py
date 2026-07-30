from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .database import get_database, transaction
from .estimate_artifact import (
    canonical_estimate_json,
    estimate_content_hash,
    record_estimate_version,
)
from .product_access import ConstructionEstimateAccessDependency
from .security import require_mutation_auth

router = APIRouter(prefix="/v1/projects", tags=["project-context"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = ConstructionEstimateAccessDependency
MutationAuthDependency = Annotated[None, Depends(require_mutation_auth)]
PROJECT_ID = re.compile(r"^project_[A-Za-z0-9._~-]{8,96}$")
PARTY_ROLE = re.compile(r"^(client|contractor)$")
DOCUMENT_SLOTS = (
    "source-data",
    "estimate",
    "commercial-proposal",
    "contract",
)


class ProjectContextModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


DisplayName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=240),
]


class ProjectPartyInput(ProjectContextModel):
    display_name: DisplayName = Field(alias="displayName")
    entity_type: Literal["person", "organization"] = Field(alias="entityType")
    tax_id: str | None = Field(
        default=None,
        alias="taxId",
        pattern=r"^(?:[0-9]{10}|[0-9]{12})$",
    )
    registration_code: str | None = Field(
        default=None,
        alias="registrationCode",
        pattern=r"^[0-9]{9}$",
    )


class EstimateCopyInput(ProjectContextModel):
    project_name: str = Field(
        alias="projectName",
        min_length=1,
        max_length=240,
    )
    object_name: str = Field(
        alias="objectName",
        min_length=1,
        max_length=240,
    )
    client: ProjectPartyInput
    retain_source_contractor: bool = Field(
        default=True,
        alias="retainSourceContractor",
    )


IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9._~-]+$",
    ),
]


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "project_not_found", "message": "Проект не найден."},
    )


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_hash(project_id: str, payload: EstimateCopyInput) -> str:
    canonical = json.dumps(
        {
            "projectId": project_id,
            "payload": payload.model_dump(by_alias=True, mode="json"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _project_row(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
) -> sqlite3.Row:
    if not PROJECT_ID.fullmatch(project_id):
        raise _not_found()
    row = database.execute(
        """
        SELECT id, title, status, primary_thread_id, created_at, updated_at
        FROM projects
        WHERE tenant_id = ? AND id = ?
        LIMIT 1
        """,
        (tenant_id, project_id),
    ).fetchone()
    if row is None:
        raise _not_found()
    return row


def _party_view(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "role": str(row["role"]),
        "isPrimary": bool(row["is_primary"]),
        "status": str(row["status"]),
        "entityType": str(row["entity_type"]),
        "displayName": str(row["display_name"]),
        "taxId": str(row["tax_id"]) if row["tax_id"] is not None else None,
        "registrationCode": (
            str(row["registration_code"])
            if row["registration_code"] is not None
            else None
        ),
        "sourceType": str(row["source_type"]),
    }


def _find_or_create_counterparty(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str,
    payload: ProjectPartyInput,
    now: str,
) -> str:
    if payload.tax_id is not None:
        existing = database.execute(
            """
            SELECT id
            FROM counterparties
            WHERE tenant_id = ? AND tax_id = ?
            ORDER BY updated_at DESC, id
            LIMIT 1
            """,
            (tenant_id, payload.tax_id),
        ).fetchone()
    else:
        existing = database.execute(
            """
            SELECT id
            FROM counterparties
            WHERE tenant_id = ?
              AND entity_type = ?
              AND display_name = ?
              AND tax_id IS NULL
              AND registration_code IS ?
            ORDER BY updated_at DESC, id
            LIMIT 1
            """,
            (
                tenant_id,
                payload.entity_type,
                payload.display_name,
                payload.registration_code,
            ),
        ).fetchone()
    if existing is not None:
        counterparty_id = str(existing["id"])
        database.execute(
            """
            UPDATE counterparties
            SET entity_type = ?, display_name = ?, tax_id = ?,
                registration_code = ?, updated_at = ?
            WHERE tenant_id = ? AND id = ?
            """,
            (
                payload.entity_type,
                payload.display_name,
                payload.tax_id,
                payload.registration_code,
                now,
                tenant_id,
                counterparty_id,
            ),
        )
        return counterparty_id
    counterparty_id = _new_id("counterparty")
    database.execute(
        """
        INSERT INTO counterparties (
            tenant_id, id, entity_type, display_name, tax_id,
            registration_code, source_type, created_by_user_id,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'user', ?, ?, ?)
        """,
        (
            tenant_id,
            counterparty_id,
            payload.entity_type,
            payload.display_name,
            payload.tax_id,
            payload.registration_code,
            user_id,
            now,
            now,
        ),
    )
    return counterparty_id


def _assign_counterparty(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    counterparty_id: str,
    role: Literal["client", "contractor"],
    now: str,
) -> None:
    database.execute(
        """
        UPDATE project_parties
        SET is_primary = 0, status = 'inactive', updated_at = ?
        WHERE tenant_id = ? AND project_id = ? AND role = ?
          AND status = 'active'
        """,
        (now, tenant_id, project_id, role),
    )
    database.execute(
        """
        INSERT INTO project_parties (
            tenant_id, project_id, counterparty_id, role,
            is_primary, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 1, 'active', ?, ?)
        ON CONFLICT (tenant_id, project_id, counterparty_id, role)
        DO UPDATE SET
            is_primary = 1,
            status = 'active',
            updated_at = excluded.updated_at
        """,
        (tenant_id, project_id, counterparty_id, role, now, now),
    )


def _primary_party_row(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    role: Literal["client", "contractor"],
) -> sqlite3.Row | None:
    return database.execute(
        """
        SELECT links.role, links.is_primary, links.status,
               counterparties.id, counterparties.entity_type,
               counterparties.display_name, counterparties.tax_id,
               counterparties.registration_code,
               counterparties.source_type
        FROM project_parties AS links
        JOIN counterparties
          ON counterparties.tenant_id = links.tenant_id
         AND counterparties.id = links.counterparty_id
        WHERE links.tenant_id = ? AND links.project_id = ?
          AND links.role = ? AND links.is_primary = 1
          AND links.status = 'active'
        LIMIT 1
        """,
        (tenant_id, project_id, role),
    ).fetchone()


def _document_title(raw: object, slot_type: str) -> str:
    default_titles = {
        "source-data": "Исходные данные",
        "estimate": "Черновик сметы",
        "commercial-proposal": "Коммерческое предложение",
        "contract": "Договор",
    }
    if not isinstance(raw, str):
        return default_titles.get(slot_type, "Документ")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return default_titles.get(slot_type, "Документ")
    if isinstance(value, dict) and isinstance(value.get("title"), str):
        return str(value["title"])
    return default_titles.get(slot_type, "Документ")


@router.get("/{project_id}/context")
def get_project_context(
    project_id: str,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, Any]:
    project = _project_row(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
    )
    construction_object = database.execute(
        """
        SELECT id, name, name_source, created_at, updated_at
        FROM construction_objects
        WHERE tenant_id = ? AND project_id = ?
        LIMIT 1
        """,
        (identity.tenant_id, project_id),
    ).fetchone()
    parties = database.execute(
        """
        SELECT links.role, links.is_primary, links.status,
               counterparties.id, counterparties.entity_type,
               counterparties.display_name, counterparties.tax_id,
               counterparties.registration_code,
               counterparties.source_type
        FROM project_parties AS links
        JOIN counterparties
          ON counterparties.tenant_id = links.tenant_id
         AND counterparties.id = links.counterparty_id
        WHERE links.tenant_id = ? AND links.project_id = ?
        ORDER BY links.role, links.is_primary DESC, counterparties.display_name
        """,
        (identity.tenant_id, project_id),
    ).fetchall()
    documents = database.execute(
        """
        SELECT id, slot_type, version, status, content_json, updated_at
        FROM document_slots
        WHERE tenant_id = ? AND project_id = ?
        ORDER BY slot_type, id
        """,
        (identity.tenant_id, project_id),
    ).fetchall()
    return {
        "project": {
            "id": str(project["id"]),
            "name": str(project["title"]),
            "status": str(project["status"]),
            "createdAt": str(project["created_at"]),
            "updatedAt": str(project["updated_at"]),
        },
        "object": (
            {
                "id": str(construction_object["id"]),
                "name": str(construction_object["name"]),
                "nameSource": str(construction_object["name_source"]),
                "createdAt": str(construction_object["created_at"]),
                "updatedAt": str(construction_object["updated_at"]),
            }
            if construction_object is not None
            else None
        ),
        "parties": [_party_view(row) for row in parties],
        "documents": [
            {
                "id": str(row["id"]),
                "type": str(row["slot_type"]),
                "name": _document_title(
                    row["content_json"],
                    str(row["slot_type"]),
                ),
                "version": int(row["version"]),
                "status": str(row["status"]),
                "updatedAt": str(row["updated_at"]),
            }
            for row in documents
        ],
    }


@router.put("/{project_id}/parties/{role}")
def assign_project_party(
    project_id: str,
    role: str,
    payload: ProjectPartyInput,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _auth: MutationAuthDependency,
) -> dict[str, Any]:
    if not PARTY_ROLE.fullmatch(role):
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "project_party_role_not_found",
            "Роль участника не найдена.",
        )
    typed_role: Literal["client", "contractor"] = (
        "client" if role == "client" else "contractor"
    )
    now = _utc_now()
    with transaction(database, immediate=True):
        _project_row(
            database,
            tenant_id=identity.tenant_id,
            project_id=project_id,
        )
        counterparty_id = _find_or_create_counterparty(
            database,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            payload=payload,
            now=now,
        )
        _assign_counterparty(
            database,
            tenant_id=identity.tenant_id,
            project_id=project_id,
            counterparty_id=counterparty_id,
            role=typed_role,
            now=now,
        )
        database.execute(
            """
            UPDATE projects
            SET updated_at = ?
            WHERE tenant_id = ? AND id = ?
            """,
            (now, identity.tenant_id, project_id),
        )
    assigned = _primary_party_row(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
        role=typed_role,
    )
    if assigned is None:
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "project_party_not_saved",
            "Участник проекта не был сохранён.",
        )
    return {"projectId": project_id, "party": _party_view(assigned)}


def _copy_result(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    idempotency_key: str,
) -> dict[str, Any] | None:
    row = database.execute(
        """
        SELECT lineage.source_project_id, lineage.source_document_id,
               lineage.source_version, lineage.source_content_hash,
               lineage.target_project_id, lineage.target_document_id,
               lineage.target_version, lineage.target_content_hash,
               lineage.request_hash, projects.title, projects.primary_thread_id,
               objects.name AS object_name
        FROM estimate_copy_lineage AS lineage
        JOIN projects
          ON projects.tenant_id = lineage.tenant_id
         AND projects.id = lineage.target_project_id
        JOIN construction_objects AS objects
          ON objects.tenant_id = lineage.tenant_id
         AND objects.project_id = lineage.target_project_id
        WHERE lineage.tenant_id = ? AND lineage.idempotency_key = ?
        LIMIT 1
        """,
        (tenant_id, idempotency_key),
    ).fetchone()
    if row is None:
        return None
    target_project_id = str(row["target_project_id"])
    client = _primary_party_row(
        database,
        tenant_id=tenant_id,
        project_id=target_project_id,
        role="client",
    )
    contractor = _primary_party_row(
        database,
        tenant_id=tenant_id,
        project_id=target_project_id,
        role="contractor",
    )
    return {
        "project": {
            "id": target_project_id,
            "name": str(row["title"]),
            "objectName": str(row["object_name"]),
            "threadId": str(row["primary_thread_id"]),
        },
        "document": {
            "id": str(row["target_document_id"]),
            "version": int(row["target_version"]),
            "contentHash": str(row["target_content_hash"]),
        },
        "client": _party_view(client) if client is not None else None,
        "contractor": (
            _party_view(contractor) if contractor is not None else None
        ),
        "lineage": {
            "sourceProjectId": str(row["source_project_id"]),
            "sourceDocumentId": str(row["source_document_id"]),
            "sourceVersion": int(row["source_version"]),
            "sourceContentHash": str(row["source_content_hash"]),
        },
        "requestHash": str(row["request_hash"]),
    }


@router.post("/{project_id}/estimate/copies", status_code=status.HTTP_201_CREATED)
def copy_estimate_for_client(
    project_id: str,
    payload: EstimateCopyInput,
    idempotency_key: IdempotencyKey,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _auth: MutationAuthDependency,
) -> dict[str, Any]:
    incoming_hash = _request_hash(project_id, payload)
    now = _utc_now()
    with transaction(database, immediate=True):
        _project_row(
            database,
            tenant_id=identity.tenant_id,
            project_id=project_id,
        )
        replay = _copy_result(
            database,
            tenant_id=identity.tenant_id,
            idempotency_key=idempotency_key,
        )
        if replay is not None:
            if replay["requestHash"] != incoming_hash:
                raise _error(
                    status.HTTP_409_CONFLICT,
                    "idempotency_conflict",
                    "Этот ключ повтора уже использован для другой операции.",
                )
            return replay

        source = database.execute(
            """
            SELECT slots.id, slots.version, slots.status, slots.content_json,
                   versions.content_hash
            FROM document_slots AS slots
            JOIN estimate_versions AS versions
              ON versions.tenant_id = slots.tenant_id
             AND versions.document_id = slots.id
             AND versions.version = slots.version
            WHERE slots.tenant_id = ? AND slots.project_id = ?
              AND slots.slot_type = 'estimate'
              AND slots.status != 'empty'
            LIMIT 1
            """,
            (identity.tenant_id, project_id),
        ).fetchone()
        if source is None or not isinstance(source["content_json"], str):
            raise _error(
                status.HTTP_404_NOT_FOUND,
                "estimate_not_found",
                "Смета для повторения не найдена.",
            )
        try:
            cloned_document = json.loads(str(source["content_json"]))
        except (TypeError, ValueError) as exc:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "estimate_invalid",
                "Исходная смета повреждена.",
            ) from exc
        if not isinstance(cloned_document, dict):
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "estimate_invalid",
                "Исходная смета повреждена.",
            )
        cloned_document["updated_at"] = now

        target_project_id = _new_id("project")
        target_object_id = _new_id("object")
        target_thread_id = _new_id("thread")
        target_goal_id = _new_id("goal")
        target_case_id = f"case_{target_goal_id}"
        target_document_id = _new_id("document")
        database.execute(
            """
            INSERT INTO projects (
                tenant_id, id, created_by_user_id, title, status,
                primary_thread_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                identity.tenant_id,
                target_project_id,
                identity.user_id,
                payload.project_name,
                target_thread_id,
                now,
                now,
            ),
        )
        database.execute(
            """
            INSERT INTO construction_objects (
                tenant_id, id, project_id, name, name_source,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'user', ?, ?)
            """,
            (
                identity.tenant_id,
                target_object_id,
                target_project_id,
                payload.object_name,
                now,
                now,
            ),
        )
        database.execute(
            """
            INSERT INTO chat_threads (
                tenant_id, id, project_id, kind, title, status,
                message_count, run_count, last_message_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, 'primary', ?, 'regular', 0, 0, NULL, ?, ?)
            """,
            (
                identity.tenant_id,
                target_thread_id,
                target_project_id,
                payload.project_name,
                now,
                now,
            ),
        )
        for slot_type in DOCUMENT_SLOTS:
            document_id = (
                target_document_id
                if slot_type == "estimate"
                else _new_id("document")
            )
            database.execute(
                """
                INSERT INTO document_slots (
                    tenant_id, id, project_id, slot_type, version, status,
                    content_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (
                    identity.tenant_id,
                    document_id,
                    target_project_id,
                    slot_type,
                    "draft" if slot_type == "estimate" else "empty",
                    (
                        canonical_estimate_json(cloned_document)
                        if slot_type == "estimate"
                        else None
                    ),
                    now,
                    now,
                ),
            )
        database.execute(
            """
            INSERT INTO product_project_runtime (
                tenant_id, project_id, goal_id, case_id, goal_state,
                goal_error_code, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'pending', NULL, ?, ?)
            """,
            (
                identity.tenant_id,
                target_project_id,
                target_goal_id,
                target_case_id,
                now,
                now,
            ),
        )
        target_hash = estimate_content_hash(cloned_document)
        record_estimate_version(
            database,
            tenant_id=identity.tenant_id,
            project_id=target_project_id,
            document_id=target_document_id,
            version=1,
            status="draft",
            document=cloned_document,
            origin_type="manual_edit",
            origin_run_id=None,
            created_by_user_id=identity.user_id,
            created_at=now,
        )
        client_id = _find_or_create_counterparty(
            database,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            payload=payload.client,
            now=now,
        )
        _assign_counterparty(
            database,
            tenant_id=identity.tenant_id,
            project_id=target_project_id,
            counterparty_id=client_id,
            role="client",
            now=now,
        )
        if payload.retain_source_contractor:
            source_contractor = _primary_party_row(
                database,
                tenant_id=identity.tenant_id,
                project_id=project_id,
                role="contractor",
            )
            if source_contractor is not None:
                _assign_counterparty(
                    database,
                    tenant_id=identity.tenant_id,
                    project_id=target_project_id,
                    counterparty_id=str(source_contractor["id"]),
                    role="contractor",
                    now=now,
                )
        database.execute(
            """
            INSERT INTO estimate_copy_lineage (
                tenant_id, id, idempotency_key, request_hash,
                source_project_id, source_document_id, source_version,
                source_content_hash, target_project_id, target_document_id,
                target_version, target_content_hash,
                created_by_user_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                identity.tenant_id,
                _new_id("estimate_copy"),
                idempotency_key,
                incoming_hash,
                project_id,
                str(source["id"]),
                int(source["version"]),
                str(source["content_hash"]),
                target_project_id,
                target_document_id,
                target_hash,
                identity.user_id,
                now,
            ),
        )
    result = _copy_result(
        database,
        tenant_id=identity.tenant_id,
        idempotency_key=idempotency_key,
    )
    if result is None:
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "estimate_copy_not_saved",
            "Копия сметы не была сохранена.",
        )
    return result
