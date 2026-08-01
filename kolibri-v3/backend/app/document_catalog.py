from __future__ import annotations

import json
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from .database import get_database
from .product_access import ConstructionEstimateAccessDependency

router = APIRouter(prefix="/v1/documents", tags=["documents"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = ConstructionEstimateAccessDependency

_DOCUMENT_PRESENTATION = {
    "source-data": {
        "category": "documents",
        "kind": "document",
        "default_name": "Исходные данные",
    },
    "estimate": {
        "category": "estimates",
        "kind": "estimate",
        "default_name": "Черновик сметы",
    },
    "commercial-proposal": {
        "category": "documents",
        "kind": "document",
        "default_name": "Коммерческое предложение",
    },
    "contract": {
        "category": "contracts",
        "kind": "contract",
        "default_name": "Договор",
    },
}


def _document_content(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _document_name(raw: object, slot_type: str) -> str:
    presentation = _DOCUMENT_PRESENTATION[slot_type]
    value = _document_content(raw)
    if value is not None:
        title = value.get("title")
        if (
            isinstance(title, str)
            and title.strip()
            and len(title.strip()) <= 240
        ):
            return title.strip()
    return presentation["default_name"]


def _estimate_summary(raw: object) -> tuple[str, int, str]:
    value = _document_content(raw)
    if value is None:
        return "Черновик сметы", 0, "0.00"
    rows = value.get("rows")
    totals = value.get("totals")
    return (
        _document_name(raw, "estimate"),
        len(rows) if isinstance(rows, list) else 0,
        str(totals.get("total") or "0.00")
        if isinstance(totals, dict)
        else "0.00",
    )


@router.get("")
def list_documents(
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, list[dict[str, Any]]]:
    rows = database.execute(
        """
        SELECT slots.id, slots.project_id, slots.slot_type, slots.version,
               slots.status, slots.content_json, slots.updated_at,
               projects.title AS project_title
        FROM document_slots AS slots
        JOIN projects
          ON projects.tenant_id = slots.tenant_id
         AND projects.id = slots.project_id
        WHERE slots.tenant_id = ?
          AND slots.status != 'empty'
          AND slots.content_json IS NOT NULL
        ORDER BY slots.updated_at DESC, slots.id
        LIMIT 500
        """,
        (identity.tenant_id,),
    ).fetchall()
    documents: list[dict[str, Any]] = []
    for row in rows:
        slot_type = str(row["slot_type"])
        presentation = _DOCUMENT_PRESENTATION.get(slot_type)
        if presentation is None:
            continue
        status = str(row["status"])
        document: dict[str, Any] = {
            "id": str(row["id"]),
            "projectId": str(row["project_id"]),
            "projectName": str(row["project_title"]),
            "slotType": slot_type,
            "category": presentation["category"],
            "kind": presentation["kind"],
            "name": _document_name(row["content_json"], slot_type),
            "status": status,
            "version": int(row["version"]),
            "updatedAt": str(row["updated_at"]),
            "editable": slot_type == "estimate" and status != "revoked",
        }
        if slot_type == "estimate":
            title, row_count, total = _estimate_summary(row["content_json"])
            document.update(
                {
                    "name": title,
                    "rowCount": row_count,
                    "total": total,
                    "currency": "RUB",
                }
            )
        documents.append(document)
    return {"documents": documents}
