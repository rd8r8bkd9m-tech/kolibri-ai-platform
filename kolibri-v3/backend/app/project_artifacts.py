from __future__ import annotations

import re
import sqlite3
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, status

from .database import get_database, transaction
from .estimate_artifact import (
    EstimatePatch,
    canonical_estimate_json,
    estimate_view,
    load_estimate_slot,
    normalize_estimate_document,
    parse_estimate_document,
    record_estimate_version,
)
from .estimate_exports import (
    EXPORT_MEDIA_TYPES,
    build_or_load_estimate_export,
)
from .market_pricing import record_price_observations
from .product_access import ConstructionEstimateAccessDependency
from .security import require_mutation_auth

router = APIRouter(prefix="/v1/projects", tags=["project-artifacts"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = ConstructionEstimateAccessDependency
MutationAuthDependency = Annotated[None, Depends(require_mutation_auth)]
PROJECT_ID = re.compile(r"^project_[A-Za-z0-9._~-]{8,96}$")


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _require_slot(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
) -> sqlite3.Row:
    if not PROJECT_ID.fullmatch(project_id):
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "estimate_not_found",
            "Смета не найдена.",
        )
    row = load_estimate_slot(
        database,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    if row is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "estimate_not_found",
            "Смета не найдена.",
        )
    return row


@router.get("/{project_id}/estimate")
def get_estimate(
    project_id: str,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, object]:
    row = _require_slot(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
    )
    document = parse_estimate_document(
        row["content_json"],
        now=str(row["updated_at"]),
    )
    return estimate_view(
        project_id=project_id,
        document_id=str(row["id"]),
        version=int(row["version"]),
        status=str(row["status"]),
        document=document,
    )


@router.get("/{project_id}/estimate/versions")
def list_estimate_versions(
    project_id: str,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, object]:
    slot = _require_slot(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
    )
    rows = database.execute(
        """
        SELECT versions.version, versions.status, versions.content_hash,
               CASE
                   WHEN lineage.id IS NOT NULL THEN 'copied_from_estimate'
                   ELSE versions.origin_type
               END AS effective_origin_type,
               versions.origin_run_id, versions.created_at,
               lineage.source_project_id, lineage.source_document_id,
               lineage.source_version, lineage.source_content_hash
        FROM estimate_versions AS versions
        LEFT JOIN estimate_copy_lineage AS lineage
          ON lineage.tenant_id = versions.tenant_id
         AND lineage.target_document_id = versions.document_id
         AND lineage.target_version = versions.version
        WHERE versions.tenant_id = ? AND versions.document_id = ?
        ORDER BY version DESC
        LIMIT 200
        """,
        (identity.tenant_id, slot["id"]),
    ).fetchall()
    return {
        "projectId": project_id,
        "documentId": str(slot["id"]),
        "versions": [
            {
                "version": int(row["version"]),
                "status": str(row["status"]),
                "contentHash": str(row["content_hash"]),
                "originType": str(row["effective_origin_type"]),
                "originRunId": (
                    str(row["origin_run_id"])
                    if row["origin_run_id"] is not None
                    else None
                ),
                "lineage": (
                    {
                        "sourceProjectId": str(row["source_project_id"]),
                        "sourceDocumentId": str(row["source_document_id"]),
                        "sourceVersion": int(row["source_version"]),
                        "sourceContentHash": str(row["source_content_hash"]),
                    }
                    if row["source_project_id"] is not None
                    else None
                ),
                "createdAt": str(row["created_at"]),
            }
            for row in rows
        ],
    }


@router.get("/{project_id}/estimate/export/{export_format}")
def export_estimate(
    project_id: str,
    export_format: str,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> Response:
    if export_format not in EXPORT_MEDIA_TYPES:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "estimate_export_not_found",
            "Формат экспорта не поддерживается.",
        )
    with transaction(database, immediate=True):
        slot = _require_slot(
            database,
            tenant_id=identity.tenant_id,
            project_id=project_id,
        )
        if str(slot["status"]) == "empty" or slot["content_json"] is None:
            raise _error(
                status.HTTP_409_CONFLICT,
                "estimate_empty",
                "Сначала сформируйте и сохраните смету.",
            )
        version_row = database.execute(
            """
            SELECT content_json, content_hash, created_at
            FROM estimate_versions
            WHERE tenant_id = ? AND document_id = ? AND version = ?
            LIMIT 1
            """,
            (identity.tenant_id, slot["id"], slot["version"]),
        ).fetchone()
        if version_row is None:
            raise _error(
                status.HTTP_409_CONFLICT,
                "estimate_version_missing",
                "Сохранённая версия сметы недоступна для экспорта.",
            )
        document = parse_estimate_document(
            version_row["content_json"],
            now=str(version_row["created_at"]),
        )
        project = database.execute(
            """
            SELECT title
            FROM projects
            WHERE tenant_id = ? AND id = ?
            LIMIT 1
            """,
            (identity.tenant_id, project_id),
        ).fetchone()
        artifact = build_or_load_estimate_export(
            database,
            tenant_id=identity.tenant_id,
            project_id=project_id,
            document_id=str(slot["id"]),
            version=int(slot["version"]),
            export_format=export_format,
            document=document,
            project_title=str(project["title"]) if project is not None else "Проект",
            created_by_user_id=identity.user_id,
            created_at=str(version_row["created_at"]),
        )
    ascii_filename = f"estimate-v{artifact.version}.{artifact.format}"
    disposition = (
        f'attachment; filename="{ascii_filename}"; '
        f"filename*=UTF-8''{quote(artifact.filename)}"
    )
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": disposition,
            "Content-Length": str(len(artifact.content)),
            "ETag": f'"{artifact.artifact_hash.removeprefix("sha256:")}"',
            "X-Kolibri-Content-SHA256": artifact.artifact_hash,
            "X-Kolibri-Source-SHA256": artifact.source_content_hash,
            "X-Kolibri-Estimate-Version": str(artifact.version),
        },
    )


@router.patch("/{project_id}/estimate")
def update_estimate(
    project_id: str,
    payload: EstimatePatch,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _auth: MutationAuthDependency,
) -> dict[str, object]:
    with transaction(database, immediate=True):
        row = _require_slot(
            database,
            tenant_id=identity.tenant_id,
            project_id=project_id,
        )
        if int(row["version"]) != payload.version:
            raise _error(
                status.HTTP_409_CONFLICT,
                "estimate_version_conflict",
                "Смета уже изменилась. Обновите данные перед сохранением.",
            )
        current = parse_estimate_document(
            row["content_json"],
            now=str(row["updated_at"]),
        )
        current_rows = {
            str(item.get("id")): item
            for item in current.get("rows", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        retained_price_evidence: dict[str, dict[str, object]] = {}
        for payload_row in payload.rows:
            previous = current_rows.get(payload_row.id)
            evidence = (
                previous.get("price_evidence")
                if isinstance(previous, dict)
                else None
            )
            if (
                isinstance(evidence, dict)
                and str(previous.get("description")) == payload_row.description
                and str(previous.get("unit")) == payload_row.unit
                and str(previous.get("unit_price")) == payload_row.unit_price
            ):
                retained_price_evidence[payload_row.id] = evidence
        try:
            document = normalize_estimate_document(
                title=payload.title,
                currency=payload.currency,
                rows=payload.rows,
                now=str(
                    database.execute(
                        "SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
                    ).fetchone()[0]
                ),
                region=(
                    str(current["region"])
                    if isinstance(current.get("region"), str)
                    else None
                ),
                assumptions=[
                    str(item)
                    for item in current.get("assumptions", [])
                    if isinstance(item, str)
                ],
                generation=(
                    {
                        "provider_profile": str(
                            current["generation"].get("provider_profile") or ""
                        ),
                        "run_id": str(current["generation"].get("run_id") or ""),
                    }
                    if isinstance(current.get("generation"), dict)
                    else None
                ),
                price_evidence_by_row=retained_price_evidence,
                pricing_checked_at=(
                    str(current["pricing"].get("last_checked_at"))
                    if isinstance(current.get("pricing"), dict)
                    and isinstance(
                        current["pricing"].get("last_checked_at"),
                        str,
                    )
                    else None
                ),
            )
        except ValueError as exc:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "estimate_invalid",
                str(exc),
            ) from exc
        next_version = int(row["version"]) + 1
        database.execute(
            """
            UPDATE document_slots
            SET version = ?, status = 'draft', content_json = ?, updated_at = ?
            WHERE tenant_id = ? AND id = ? AND version = ?
            """,
            (
                next_version,
                canonical_estimate_json(document),
                document["updated_at"],
                identity.tenant_id,
                row["id"],
                payload.version,
            ),
        )
        record_estimate_version(
            database,
            tenant_id=identity.tenant_id,
            project_id=project_id,
            document_id=str(row["id"]),
            version=next_version,
            status="draft",
            document=document,
            origin_type="manual_edit",
            origin_run_id=None,
            created_by_user_id=identity.user_id,
            created_at=str(document["updated_at"]),
        )
        record_price_observations(
            database,
            tenant_id=identity.tenant_id,
            project_id=project_id,
            document_id=str(row["id"]),
            estimate_version=next_version,
            previous_document=current,
            document=document,
            source_type="user_edit",
            lifecycle="draft",
            created_by_user_id=identity.user_id,
            observed_at=str(document["updated_at"]),
        )
        database.execute(
            """
            UPDATE projects
            SET updated_at = ?
            WHERE tenant_id = ? AND id = ?
            """,
            (document["updated_at"], identity.tenant_id, project_id),
        )
    return estimate_view(
        project_id=project_id,
        document_id=str(row["id"]),
        version=next_version,
        status="draft",
        document=document,
    )
