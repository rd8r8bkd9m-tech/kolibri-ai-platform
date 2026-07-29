from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Mapping


ObservationSource = Literal[
    "ai_preliminary",
    "user_edit",
    "official_reference",
    "supplier_offer",
    "customer_approved",
    "contract_price",
]
ObservationLifecycle = Literal["draft", "shared", "approved", "contracted"]
TOKEN_PATTERN = re.compile(r"[0-9a-zа-яё]+", re.IGNORECASE)


def normalized_market_text(value: str) -> str:
    normalized = (
        unicodedata.normalize("NFKC", value)
        .casefold()
        .replace("ё", "е")
        .replace("²", "2")
        .replace("³", "3")
    )
    return " ".join(TOKEN_PATTERN.findall(normalized))


def market_item_key(*, kind: str, description: str, unit: str) -> str:
    canonical = json.dumps(
        {
            "kind": kind,
            "description": normalized_market_text(description),
            "unit": normalized_market_text(unit),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8", "strict")).hexdigest()
    return f"sha256:{digest}"


def _season(observed_at: str) -> str:
    try:
        month = datetime.fromisoformat(observed_at.replace("Z", "+00:00")).month
    except ValueError:
        return "unknown"
    if month in {12, 1, 2}:
        return "winter"
    if month in {3, 4, 5}:
        return "spring"
    if month in {6, 7, 8}:
        return "summer"
    return "autumn"


def record_price_observations(
    database: Any,
    *,
    tenant_id: str,
    project_id: str,
    document_id: str,
    estimate_version: int,
    previous_document: Mapping[str, Any] | None,
    document: Mapping[str, Any],
    source_type: ObservationSource,
    lifecycle: ObservationLifecycle,
    created_by_user_id: str,
    observed_at: str,
    quote_ids_by_row: Mapping[str, str] | None = None,
) -> int:
    previous_rows = {
        str(row.get("id")): row
        for row in (previous_document or {}).get("rows", [])
        if isinstance(row, Mapping) and isinstance(row.get("id"), str)
    }
    quote_ids = quote_ids_by_row or {}
    region = (
        str(document.get("region"))
        if isinstance(document.get("region"), str)
        else "Регион не указан"
    )
    inserted = 0
    for raw_row in document.get("rows", []):
        if not isinstance(raw_row, Mapping):
            continue
        row_id = str(raw_row.get("id") or "")
        if quote_ids and row_id not in quote_ids:
            continue
        description = str(raw_row.get("description") or "").strip()
        unit = str(raw_row.get("unit") or "").strip()
        kind = str(raw_row.get("kind") or "service")
        observed_price = str(raw_row.get("unit_price") or "")
        if (
            not row_id
            or not description
            or not unit
            or kind not in {"work", "material", "equipment", "service"}
        ):
            continue
        try:
            parsed_price = Decimal(observed_price)
        except InvalidOperation:
            continue
        if not parsed_price.is_finite() or parsed_price < 0:
            continue
        previous = previous_rows.get(row_id)
        previous_price = (
            str(previous.get("unit_price"))
            if isinstance(previous, Mapping)
            and previous.get("unit_price") is not None
            else None
        )
        if source_type == "user_edit" and previous_price == observed_price:
            continue
        context = {
            "season": _season(observed_at),
            "quantityBasis": str(raw_row.get("quantity_basis") or ""),
            "priceBasis": str(raw_row.get("price_basis") or ""),
            "sourceScope": "tenant_private",
        }
        database.execute(
            """
            INSERT INTO price_observations (
                tenant_id, id, project_id, document_id, estimate_version,
                row_id, item_key, item_kind, description,
                normalized_description, region, unit,
                previous_unit_price_rub, observed_unit_price_rub,
                currency, source_type, lifecycle, context_json,
                evidence_quote_id, aggregate_eligible,
                created_by_user_id, observed_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                'RUB', ?, ?, ?, ?, 0, ?, ?
            )
            """,
            (
                tenant_id,
                f"price_observation_{uuid.uuid4().hex}",
                project_id,
                document_id,
                estimate_version,
                row_id,
                market_item_key(
                    kind=kind,
                    description=description,
                    unit=unit,
                ),
                kind,
                description,
                normalized_market_text(description),
                region,
                unit,
                previous_price,
                observed_price,
                source_type,
                lifecycle,
                json.dumps(
                    context,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                quote_ids.get(row_id),
                created_by_user_id,
                observed_at,
            ),
        )
        inserted += 1
    return inserted


def percentile(values: list[Decimal], ratio: Decimal) -> Decimal:
    if not values:
        raise ValueError("price sample is empty")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = ratio * Decimal(len(ordered) - 1)
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - Decimal(lower)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
