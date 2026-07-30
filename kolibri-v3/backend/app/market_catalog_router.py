from __future__ import annotations

import sqlite3
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any

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
    region: Annotated[str | None, Query(min_length=1, max_length=160)] = None,
    query: Annotated[str | None, Query(min_length=1, max_length=160)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, Any]:
    predicates = ["tenant_id = ?", "created_by_user_id = ?"]
    parameters: list[Any] = [identity.tenant_id, identity.user_id]
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
        SELECT item_key, item_kind, description, region, unit,
               previous_unit_price_rub, observed_unit_price_rub,
               source_type, lifecycle, observed_at
        FROM price_observations
        WHERE {' AND '.join(predicates)}
        ORDER BY observed_at DESC, id DESC
        LIMIT ?
        """,
        parameters,
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[str(row["item_key"])].append(row)
    entries: list[dict[str, Any]] = []
    for item_key, observations in grouped.items():
        prices = [
            Decimal(str(observation["observed_unit_price_rub"]))
            for observation in observations
        ]
        latest = observations[0]
        entries.append(
            {
                "itemKey": item_key,
                "kind": str(latest["item_kind"]),
                "description": str(latest["description"]),
                "region": str(latest["region"]),
                "unit": str(latest["unit"]),
                "latestPrice": _money(prices[0]),
                "medianPrice": _money(percentile(prices, Decimal("0.5"))),
                "lowerQuartile": _money(percentile(prices, Decimal("0.25"))),
                "upperQuartile": _money(percentile(prices, Decimal("0.75"))),
                "sampleSize": len(prices),
                "latestSource": str(latest["source_type"]),
                "latestLifecycle": str(latest["lifecycle"]),
                "latestObservedAt": str(latest["observed_at"]),
            }
        )
    return {
        "scope": "personal",
        "aggregation": {
            "method": "median_iqr",
            "crossTenantEnabled": False,
            "minimumAnonymousCohort": None,
        },
        "entries": entries[:limit],
    }
