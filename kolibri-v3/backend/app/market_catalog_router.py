from __future__ import annotations

import sqlite3
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query

from .database import get_database
from .market_pricing import normalized_market_text, percentile
from .product_access import ConstructionEstimateAccessDependency

router = APIRouter(prefix="/v1/pricing", tags=["pricing"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = ConstructionEstimateAccessDependency
MONEY = Decimal("0.01")


def _money(value: Decimal) -> str:
    return format(value.quantize(MONEY, rounding=ROUND_HALF_UP), ".2f")


@router.get("/catalog")
def personal_price_catalog(
    database: DatabaseDependency,
    identity: IdentityDependency,
    project_id: Annotated[
        str,
        Query(alias="projectId", min_length=1, max_length=120),
    ],
    category: Annotated[
        Literal["work", "material", "equipment", "service"] | None,
        Query(),
    ] = None,
    source: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    region: Annotated[str | None, Query(min_length=1, max_length=160)] = None,
    query: Annotated[str | None, Query(min_length=1, max_length=160)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, Any]:
    project = database.execute(
        "SELECT 1 FROM projects WHERE tenant_id = ? AND id = ? LIMIT 1",
        (identity.tenant_id, project_id),
    ).fetchone()
    if project is None:
        return {
            "scope": "personal",
            "projectId": project_id,
            "aggregation": {
                "method": "median_iqr",
                "crossTenantEnabled": False,
                "crossProjectEnabled": False,
                "minimumAnonymousCohort": None,
            },
            "entries": [],
        }
    predicates = [
        "tenant_id = ?",
        "created_by_user_id = ?",
        "project_id = ?",
    ]
    parameters: list[Any] = [identity.tenant_id, identity.user_id, project_id]
    if category:
        predicates.append("item_kind = ?")
        parameters.append(category)
    if source:
        predicates.append("source_type = ?")
        parameters.append(source.strip())
    if region:
        predicates.append("region = ?")
        parameters.append(region.strip())
    if query:
        predicates.append("normalized_description LIKE ? ESCAPE '\\'")
        escaped = (
            normalized_market_text(query)
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        parameters.append(f"%{escaped}%")
    parameters.append(limit * 40)
    rows = database.execute(
        f"""
        SELECT project_id, item_key, item_kind, description, region, unit,
               previous_unit_price_rub, observed_unit_price_rub,
               source_type, lifecycle, observed_at
        FROM price_observations
        WHERE {' AND '.join(predicates)}
        ORDER BY observed_at DESC, id DESC
        LIMIT ?
        """,
        parameters,
    ).fetchall()
    grouped: dict[tuple[str, str, str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        key = (
            str(row["item_key"]),
            str(row["item_kind"]),
            str(row["region"]),
            str(row["source_type"]),
        )
        grouped[key].append(row)
    entries: list[dict[str, Any]] = []
    confidence_by_source = {
        "contract_price": 1.0,
        "customer_approved": 0.95,
        "official_reference": 0.95,
        "supplier_offer": 0.9,
        "user_edit": 0.7,
        "ai_preliminary": 0.35,
    }
    for (item_key, item_kind, item_region, item_source), observations in grouped.items():
        prices = [
            Decimal(str(observation["observed_unit_price_rub"]))
            for observation in observations
        ]
        latest = observations[0]
        entries.append(
            {
                "itemKey": item_key,
                "projectId": str(latest["project_id"]),
                "kind": item_kind,
                "category": item_kind,
                "description": str(latest["description"]),
                "region": item_region,
                "unit": str(latest["unit"]),
                "latestPrice": _money(prices[0]),
                "medianPrice": _money(percentile(prices, Decimal("0.5"))),
                "lowerQuartile": _money(percentile(prices, Decimal("0.25"))),
                "upperQuartile": _money(percentile(prices, Decimal("0.75"))),
                "sampleSize": len(prices),
                "latestSource": str(latest["source_type"]),
                "source": item_source,
                "latestLifecycle": str(latest["lifecycle"]),
                "latestObservedAt": str(latest["observed_at"]),
                "priceDate": str(latest["observed_at"]),
                "confidence": confidence_by_source.get(item_source, 0.5),
                "aiPreliminary": item_source == "ai_preliminary",
            }
        )
    return {
        "scope": "personal",
        "projectId": project_id,
        "aggregation": {
            "method": "median_iqr",
            "crossTenantEnabled": False,
            "crossProjectEnabled": False,
            "minimumAnonymousCohort": None,
        },
        "entries": entries[:limit],
    }
