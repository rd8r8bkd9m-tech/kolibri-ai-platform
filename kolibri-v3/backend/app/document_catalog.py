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


def _estimate_summary(raw: object) -> tuple[str, int, str]:
    if not isinstance(raw, str):
        return "Черновик сметы", 0, "0.00"
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return "Черновик сметы", 0, "0.00"
    if not isinstance(value, dict):
        return "Черновик сметы", 0, "0.00"
    rows = value.get("rows")
    totals = value.get("totals")
    return (
        str(value.get("title") or "Черновик сметы"),
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
        if str(row["slot_type"]) != "estimate":
            continue
        title, row_count, total = _estimate_summary(row["content_json"])
        documents.append(
            {
                "id": str(row["id"]),
                "projectId": str(row["project_id"]),
                "projectName": str(row["project_title"]),
                "category": "estimates",
                "kind": "estimate",
                "name": title,
                "status": str(row["status"]),
                "version": int(row["version"]),
                "updatedAt": str(row["updated_at"]),
                "rowCount": row_count,
                "total": total,
                "currency": "RUB",
                "editable": True,
            }
        )
    return {"documents": documents}
