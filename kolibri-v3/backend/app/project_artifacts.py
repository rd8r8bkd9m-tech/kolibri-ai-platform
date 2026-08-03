from __future__ import annotations

import re
import sqlite3
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from .database import get_database, transaction
from .estimate_artifact import (
    EstimatePatch,
    EstimateRowInput,
    EstimateRowsPatch,
    canonical_estimate_json,
    estimate_view,
    estimate_lifecycle_status,
    load_estimate_slot,
    normalize_estimate_document,
    parse_estimate_document,
    record_estimate_version,
)
from .estimate_exports import (
    EXPORT_MEDIA_TYPES,
    build_or_load_estimate_export,
)
from .attachment_store import AttachmentStorageError, resolve_storage_path
from .estimate_document_router import _content_stream, _open_verified_content
from .market_pricing import record_price_observations
from .product_access import ConstructionEstimateAccessDependency
from .security import require_mutation_auth

router = APIRouter(prefix="/v1/projects", tags=["project-artifacts"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = ConstructionEstimateAccessDependency
MutationAuthDependency = Annotated[None, Depends(require_mutation_auth)]
PROJECT_ID = re.compile(r"^project_[A-Za-z0-9._~-]{8,96}$")


def _error(
    status_code: int,
    code: str,
    message: str,
    **details: int,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, **details},
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


def _row_with_server_provenance(
    candidate: EstimateRowInput,
    previous: dict[str, object] | None,
) -> EstimateRowInput:
    """Keep lineage server-owned across both legacy and delta mutations."""

    values: dict[str, object] = {
        "catalog_entry_id": None,
        "catalog_entry_version": None,
        "technology_card_version": None,
        "operation_id": None,
        "resource_id": None,
        "evidence_id": None,
        "price_observation_id": None,
        "market_aggregate_id": None,
        "line_confidence": "missing",
    }
    if previous is not None:
        values.update(
            {
                "catalog_entry_id": previous.get("catalog_entry_id"),
                "catalog_entry_version": previous.get("catalog_entry_version"),
                "technology_card_version": previous.get("technology_card_version"),
                "operation_id": previous.get("operation_id"),
                "resource_id": previous.get("resource_id"),
                "evidence_id": previous.get("evidence_id"),
                "price_observation_id": previous.get("price_observation_id"),
                "market_aggregate_id": previous.get("market_aggregate_id"),
                "line_confidence": previous.get("line_confidence") or "missing",
            }
        )
    return candidate.model_copy(update=values)


@router.get("/{project_id}/estimate")
def get_estimate(
    project_id: str,
    database: DatabaseDependency,
    identity: IdentityDependency,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=0, le=100),
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
        row_offset=offset,
        row_limit=limit,
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
        SELECT versions.version,
               COALESCE(versions.lifecycle_status, versions.status) AS status,
               versions.content_hash,
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
    request: Request,
    database: DatabaseDependency,
    identity: IdentityDependency,
    version: int | None = Query(default=None, ge=1),
    kind: str | None = Query(default=None, min_length=1, max_length=64),
) -> Response:
    if export_format not in EXPORT_MEDIA_TYPES:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "estimate_export_not_found",
            "Формат экспорта не поддерживается.",
        )
    # A version/kind query selects an already-issued official artifact.  The
    # legacy no-query path below continues to build the original estimate
    # export for clients that have not adopted document-pack issues yet.
    if version is not None or kind is not None:
        slot = _require_slot(
            database,
            tenant_id=identity.tenant_id,
            project_id=project_id,
        )
        requested_kind = kind or "pack"
        issue_row = database.execute(
            """
            SELECT id
            FROM estimate_document_issues
            WHERE tenant_id = ? AND project_id = ? AND document_id = ?
              AND estimate_version = ? AND document_kind = ?
              AND mode IN ('preliminary', 'issue')
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (
                identity.tenant_id,
                project_id,
                str(slot["id"]),
                int(version if version is not None else slot["version"]),
                requested_kind,
            ),
        ).fetchone()
        if issue_row is None:
            raise _error(
                status.HTTP_404_NOT_FOUND,
                "estimate_document_not_found",
                "Официальный выпуск для указанной версии не найден.",
            )
        effective_version = int(version if version is not None else slot["version"])
        artifact = database.execute(
            """
            SELECT id, filename, media_type, size_bytes, storage_ref, artifact_hash
            FROM estimate_document_artifacts
            WHERE tenant_id = ? AND project_id = ? AND issue_id = ? AND artifact_kind = ?
            LIMIT 1
            """,
            (identity.tenant_id, project_id, str(issue_row["id"]), export_format),
        ).fetchone()
        if artifact is None:
            raise _error(
                status.HTTP_404_NOT_FOUND,
                "estimate_document_artifact_not_found",
                "Файл официального выпуска не найден.",
            )
        try:
            path = resolve_storage_path(
                request.app.state.settings,
                str(artifact["storage_ref"]),
            )
            descriptor = _open_verified_content(
                path.as_posix(),
                expected_size=int(artifact["size_bytes"]),
                expected_hash=str(artifact["artifact_hash"]),
            )
        except (AttachmentStorageError, FileNotFoundError, OSError) as exc:
            raise _error(
                status.HTTP_410_GONE,
                "estimate_document_artifact_missing",
                "Файл официального выпуска больше недоступен.",
            ) from exc
        return StreamingResponse(
            _content_stream(descriptor),
            media_type=str(artifact["media_type"]),
            headers={
                "Content-Disposition": f'attachment; filename="estimate-v{effective_version}.{export_format}"; filename*=UTF-8\'\'{quote(str(artifact["filename"]))}',
                "Content-Length": str(artifact["size_bytes"]),
                "ETag": f'"{str(artifact["artifact_hash"]).removeprefix("sha256:")}"',
                "X-Kolibri-Content-SHA256": str(artifact["artifact_hash"]),
                "X-Kolibri-Estimate-Version": str(effective_version),
            },
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


@router.patch("/{project_id}/estimate", deprecated=True)
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
                expected_version=payload.version,
                current_version=int(row["version"]),
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
        authoritative_rows: list[EstimateRowInput] = []
        for payload_row in payload.rows:
            previous = current_rows.get(payload_row.id)
            authoritative_row = _row_with_server_provenance(
                payload_row,
                previous if isinstance(previous, dict) else None,
            )
            authoritative_rows.append(authoritative_row)
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
                rows=authoritative_rows,
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
                        key: str(current["generation"].get(key) or "")
                        for key in (
                            "provider_profile",
                            "run_id",
                            "estimate_generation_run_id",
                            "technology_card_revision_id",
                            "technology_card_hash",
                            "quality_status",
                        )
                        if current["generation"].get(key) is not None
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
        lifecycle_status = estimate_lifecycle_status(document, "draft")
        database.execute(
            """
            UPDATE document_slots
            SET version = ?, status = 'draft', estimate_lifecycle_status = ?,
                content_json = ?, updated_at = ?
            WHERE tenant_id = ? AND id = ? AND version = ?
            """,
            (
                next_version,
                lifecycle_status,
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
        status=lifecycle_status,
        document=document,
    )


def _editable_row_input(raw_row: dict[str, object]) -> EstimateRowInput:
    return EstimateRowInput(
        id=str(raw_row.get("id") or ""),
        section=str(raw_row.get("section") or "Прочее"),
        kind=str(raw_row.get("kind") or "service"),
        description=str(raw_row.get("description") or ""),
        unit=str(raw_row.get("unit") or "шт."),
        quantity=str(raw_row.get("quantity") or "0"),
        unitPrice=str(raw_row.get("unit_price") or "0.00"),
        quantityBasis=str(raw_row.get("quantity_basis") or "Введено вручную"),
        priceBasis=str(raw_row.get("price_basis") or "Введено вручную"),
        wbsPath=(
            str(raw_row["wbs_path"])
            if raw_row.get("wbs_path") is not None
            else None
        ),
        specification=(
            str(raw_row["specification"])
            if raw_row.get("specification") is not None
            else None
        ),
        quantityFormula=(
            str(raw_row["quantity_formula"])
            if raw_row.get("quantity_formula") is not None
            else None
        ),
        catalogEntryId=(
            str(raw_row["catalog_entry_id"])
            if raw_row.get("catalog_entry_id") is not None
            else None
        ),
        catalogEntryVersion=(
            int(raw_row["catalog_entry_version"])
            if raw_row.get("catalog_entry_version") is not None
            else None
        ),
        technologyCardVersion=(
            str(raw_row["technology_card_version"])
            if raw_row.get("technology_card_version") is not None
            else None
        ),
        operationId=(
            str(raw_row["operation_id"])
            if raw_row.get("operation_id") is not None
            else None
        ),
        resourceId=(
            str(raw_row["resource_id"])
            if raw_row.get("resource_id") is not None
            else None
        ),
        evidenceId=(
            str(raw_row["evidence_id"])
            if raw_row.get("evidence_id") is not None
            else None
        ),
        priceObservationId=(
            str(raw_row["price_observation_id"])
            if raw_row.get("price_observation_id") is not None
            else None
        ),
        marketAggregateId=(
            str(raw_row["market_aggregate_id"])
            if raw_row.get("market_aggregate_id") is not None
            else None
        ),
        lineConfidence=str(raw_row.get("line_confidence") or "missing"),
    )


def _page_estimate_response(
    view: dict[str, object],
    *,
    offset: int,
    limit: int,
) -> dict[str, object]:
    raw_rows = view.get("rows")
    rows = raw_rows if isinstance(raw_rows, list) else []
    total_rows = int(
        (view.get("pricing") or {}).get("totalRows", len(rows))
        if isinstance(view.get("pricing"), dict)
        else len(rows)
    )
    if total_rows == 0:
        effective_offset = 0
    elif limit > 0:
        last_page_offset = ((total_rows - 1) // limit) * limit
        effective_offset = min(offset, last_page_offset)
    else:
        effective_offset = min(offset, total_rows)
    page_rows = rows[effective_offset : effective_offset + limit]
    view["rows"] = page_rows
    view["rowPage"] = {
        "offset": effective_offset,
        "limit": limit,
        "totalRows": total_rows,
        "hasMore": effective_offset + len(page_rows) < total_rows,
    }
    view["schemaVersion"] = "1.4"
    return view


@router.patch("/{project_id}/estimate/rows")
def update_estimate_rows(
    project_id: str,
    payload: EstimateRowsPatch,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _auth: MutationAuthDependency,
) -> dict[str, object]:
    slot = _require_slot(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
    )
    if int(slot["version"]) != payload.version:
        raise _error(
            status.HTTP_409_CONFLICT,
            "estimate_version_conflict",
            "Смета уже изменилась. Обновите данные перед сохранением.",
            expected_version=payload.version,
            current_version=int(slot["version"]),
        )
    current = parse_estimate_document(
        slot["content_json"],
        now=str(slot["updated_at"]),
    )
    raw_rows = [
        item
        for item in current.get("rows", [])
        if isinstance(item, dict)
    ]
    current_ids = {str(item.get("id") or "") for item in raw_rows}
    unknown_deletes = set(payload.delete_row_ids).difference(current_ids)
    if unknown_deletes:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "estimate_row_not_found",
            "Одна или несколько удаляемых строк не найдены.",
        )
    upserts = {item.id: item for item in payload.upsert_rows}
    deletes = set(payload.delete_row_ids)
    merged_rows: list[EstimateRowInput] = []
    for raw_row in raw_rows:
        row_id = str(raw_row.get("id") or "")
        if row_id in deletes:
            continue
        merged_rows.append(upserts.pop(row_id, _editable_row_input(raw_row)))
    merged_rows.extend(upserts.values())
    full_view = update_estimate(
        project_id=project_id,
        payload=EstimatePatch(
            version=payload.version,
            title=payload.title or str(current.get("title") or "Черновик сметы"),
            currency="RUB",
            rows=merged_rows,
        ),
        database=database,
        identity=identity,
        _auth=_auth,
    )
    return _page_estimate_response(
        full_view,
        offset=payload.return_page.offset,
        limit=payload.return_page.limit,
    )
