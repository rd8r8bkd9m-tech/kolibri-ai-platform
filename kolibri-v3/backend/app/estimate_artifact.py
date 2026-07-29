from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Annotated, Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


DECIMAL_TEXT = re.compile(r"^(?:0|[1-9]\d{0,11})(?:\.\d{1,6})?$")
MONEY_TEXT = re.compile(r"^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$")
ROW_ID = re.compile(r"^row_[A-Za-z0-9._~-]{8,96}$")
MONEY_QUANTUM = Decimal("0.01")
EstimateLineKind = Literal["work", "material", "equipment", "service"]
PriceSourceType = Literal["fgis_cs", "supplier_offer"]


class EstimateModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


ShortText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
]
BasisText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


class GeneratedEstimateRow(EstimateModel):
    section: str = Field(min_length=1, max_length=120)
    kind: EstimateLineKind
    description: ShortText
    unit: str = Field(min_length=1, max_length=32)
    quantity: str = Field(pattern=DECIMAL_TEXT.pattern)
    unit_price: str = Field(alias="unitPrice", pattern=MONEY_TEXT.pattern)
    quantity_basis: BasisText = Field(alias="quantityBasis")
    price_basis: BasisText = Field(alias="priceBasis")


class GeneratedEstimateProposal(EstimateModel):
    title: str = Field(min_length=1, max_length=240)
    region: str = Field(min_length=1, max_length=160)
    assumptions: list[ShortText] = Field(min_length=1, max_length=20)
    rows: list[GeneratedEstimateRow] = Field(min_length=1, max_length=24)


class EstimateRowInput(EstimateModel):
    id: str = Field(pattern=r"^row_[A-Za-z0-9._~-]{8,96}$")
    section: str = Field(min_length=1, max_length=120)
    kind: EstimateLineKind
    description: ShortText
    unit: str = Field(min_length=1, max_length=32)
    quantity: str = Field(pattern=DECIMAL_TEXT.pattern)
    unit_price: str = Field(alias="unitPrice", pattern=MONEY_TEXT.pattern)
    quantity_basis: BasisText = Field(alias="quantityBasis")
    price_basis: BasisText = Field(alias="priceBasis")


class EstimatePatch(EstimateModel):
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=240)
    currency: Literal["RUB"]
    rows: list[EstimateRowInput] = Field(max_length=200)


ESTIMATE_PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "minLength": 1, "maxLength": 240},
        "region": {"type": "string", "minLength": 1, "maxLength": 160},
        "assumptions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "items": {"type": "string", "minLength": 1, "maxLength": 300},
        },
        "rows": {
            "type": "array",
            "minItems": 1,
            "maxItems": 24,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "section": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 120,
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["work", "material", "equipment", "service"],
                    },
                    "description": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 300,
                    },
                    "unit": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 32,
                    },
                    "quantity": {
                        "type": "string",
                        "pattern": DECIMAL_TEXT.pattern,
                    },
                    "unitPrice": {
                        "type": "string",
                        "pattern": MONEY_TEXT.pattern,
                    },
                    "quantityBasis": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 500,
                    },
                    "priceBasis": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 500,
                    },
                },
                "required": [
                    "section",
                    "kind",
                    "description",
                    "unit",
                    "quantity",
                    "unitPrice",
                    "quantityBasis",
                    "priceBasis",
                ],
            },
        },
    },
    "required": ["title", "region", "assumptions", "rows"],
}


def estimate_proposal_instructions(*, today: str) -> str:
    return f"""
Ты формируешь предварительный редактируемый черновик сметы для Kolibri.
Верни только JSON по переданной schema.

Правила:
- Преврати последний запрос пользователя в подробную смету из 12–20 строк,
  если предмет запроса позволяет такую детализацию.
- Разделяй работы и материалы на отдельные строки, группируй их в section.
- Не вычисляй итоги: сервер Kolibri выполнит всю арифметику Decimal.
- Не выдавай цену за проверенный рыночный факт. Если пользователь не дал цену,
  поставь разумную предварительную оценку в рублях и явно напиши в priceBasis:
  "Предварительная оценка AI на {today}; проверить по прайсам поставщиков".
- В quantityBasis укажи, что взято из запроса, что рассчитано из него и что
  является допущением. Не скрывай выведенные площади, запасы и коэффициенты.
- В assumptions перечисли все недостающие исходные данные и принятые
  допущения. Черновик должен быть полезным уже сейчас, а не пустым.
- region заполни регионом пользователя либо строкой "Регион не указан".
- Используй только неотрицательные decimal-строки с точкой: "6", "12.5",
  "3500.00". Не добавляй markdown и пояснения вне JSON.
""".strip()


def parse_generated_estimate(text: str) -> GeneratedEstimateProposal:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError("estimate proposal is not valid JSON") from None
    return GeneratedEstimateProposal.model_validate(value)


def _money(value: Decimal) -> str:
    return format(value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP), ".2f")


def _quantity(value: str) -> str:
    normalized = format(Decimal(value), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def canonical_estimate_json(document: dict[str, Any]) -> str:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def estimate_content_hash(document: dict[str, Any]) -> str:
    payload = canonical_estimate_json(document).encode("utf-8", "strict")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def empty_estimate_document(now: str) -> dict[str, Any]:
    return {
        "schema_id": "kolibri.estimate_draft",
        "schema_version": "1.2",
        "title": "Черновик сметы",
        "currency": "RUB",
        "region": None,
        "assumptions": [],
        "generation": None,
        "rows": [],
        "pricing": {
            "status": "unpriced",
            "sourced_rows": 0,
            "stale_rows": 0,
            "total_rows": 0,
            "last_checked_at": None,
        },
        "totals": {"subtotal": "0.00", "total": "0.00"},
        "updated_at": now,
    }


def _price_basis_from_evidence(evidence: Mapping[str, Any]) -> str:
    source_type = evidence.get("source_type")
    if source_type == "fgis_cs":
        tax_label = {
            "included": "НДС включён",
            "excluded": "без НДС",
            "unknown": "НДС не указан",
        }.get(str(evidence.get("tax_status")), "НДС не указан")
        return (
            f"ФГИС ЦС · {evidence.get('period') or 'период не указан'} · "
            f"{evidence.get('price_zone') or evidence.get('region') or 'регион не указан'} · "
            f"{evidence.get('source_reference') or 'код не указан'} · "
            f"справочная цена, логистика отдельно не рассчитана · {tax_label}"
        )[:500]
    if source_type == "supplier_offer":
        tax_label = {
            "included": "НДС включён",
            "excluded": "без НДС",
            "unknown": "НДС не указан",
        }.get(str(evidence.get("tax_status")), "НДС не указан")
        return (
            f"Предложение {evidence.get('source_label') or 'поставщика'} · "
            f"{evidence.get('source_reference') or 'без номера'} · "
            f"от {evidence.get('price_date') or 'дата не указана'} · {tax_label}"
        )[:500]
    raise ValueError("unsupported price evidence source")


def _normalized_price_evidence(
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    source_type = str(evidence.get("source_type") or "")
    if source_type not in {"fgis_cs", "supplier_offer"}:
        raise ValueError("unsupported price evidence source")
    required_text = (
        "source_label",
        "source_url",
        "source_reference",
        "snapshot_hash",
        "quote_id",
        "region",
        "price_date",
        "retrieved_at",
        "fresh_until",
        "freshness_basis",
        "tax_status",
        "price_scope",
        "unit_price",
        "delivery_per_unit",
        "landed_unit_price",
        "landed_cost_status",
        "binding_status",
        "availability",
    )
    normalized = {key: evidence.get(key) for key in evidence}
    if source_type == "fgis_cs":
        normalized.setdefault("freshness_basis", "kolibri_policy_window")
        normalized.setdefault("price_scope", "official_reference")
        normalized.setdefault("landed_cost_status", "not_calculated")
    else:
        normalized.setdefault("freshness_basis", "supplier_valid_until")
        normalized.setdefault("price_scope", "landed")
        normalized.setdefault("landed_cost_status", "calculated")
    if any(
        not isinstance(normalized.get(key), str)
        or not str(normalized[key]).strip()
        for key in required_text
    ):
        raise ValueError("price evidence is incomplete")
    for money_field in ("unit_price", "delivery_per_unit", "landed_unit_price"):
        value = str(normalized[money_field])
        if MONEY_TEXT.fullmatch(value) is None:
            raise ValueError("price evidence money is invalid")
        normalized[money_field] = _money(Decimal(value))
    snapshot_hash = str(normalized["snapshot_hash"])
    if (
        len(snapshot_hash) != 71
        or not snapshot_hash.startswith("sha256:")
        or any(
            character not in "0123456789abcdef"
            for character in snapshot_hash[7:]
        )
    ):
        raise ValueError("price evidence snapshot hash is invalid")
    normalized["source_type"] = source_type
    if normalized["freshness_basis"] not in {
        "kolibri_policy_window",
        "supplier_valid_until",
    }:
        raise ValueError("price evidence freshness basis is invalid")
    if normalized["price_scope"] not in {"official_reference", "landed"}:
        raise ValueError("price evidence scope is invalid")
    if normalized["landed_cost_status"] not in {
        "not_calculated",
        "calculated",
    }:
        raise ValueError("price evidence landed cost status is invalid")
    normalized["status"] = (
        "stale"
        if date.fromisoformat(str(normalized["fresh_until"])) < date.today()
        else "current"
    )
    normalized.setdefault("material_code", None)
    normalized.setdefault("material_name", None)
    normalized.setdefault("price_zone", None)
    normalized.setdefault("period", None)
    normalized.setdefault("lead_time_days", None)
    normalized.setdefault("source_distance_price", None)
    normalized.setdefault("source_procurement_storage_percent", None)
    return normalized


def _pricing_summary(
    rows: list[dict[str, Any]],
    *,
    last_checked_at: str | None,
) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    for row in rows:
        legacy = row.get("price_evidence")
        if isinstance(legacy, dict):
            evidence.append(legacy)
            continue
        engine = row.get("engine_price_provenance")
        if not isinstance(engine, dict) or engine.get("verified") is not True:
            continue
        engine_status = "current"
        valid_until = engine.get("validUntil")
        checked_date = (
            last_checked_at[:10]
            if isinstance(last_checked_at, str) and len(last_checked_at) >= 10
            else None
        )
        if (
            isinstance(valid_until, str)
            and checked_date is not None
            and valid_until < checked_date
        ):
            engine_status = "stale"
        evidence.append({"status": engine_status})
    stale_rows = sum(1 for item in evidence if item.get("status") == "stale")
    current_rows = len(evidence) - stale_rows
    if stale_rows:
        status = "stale"
    elif current_rows == 0:
        status = "unpriced"
    elif current_rows == len(rows):
        status = "sourced"
    else:
        status = "partially_sourced"
    return {
        "status": status,
        "sourced_rows": current_rows,
        "stale_rows": stale_rows,
        "total_rows": len(rows),
        "last_checked_at": last_checked_at,
    }


def normalize_estimate_document(
    *,
    title: str,
    currency: str,
    rows: list[EstimateRowInput],
    now: str,
    region: str | None = None,
    assumptions: list[str] | None = None,
    generation: dict[str, str] | None = None,
    price_evidence_by_row: Mapping[str, Mapping[str, Any]] | None = None,
    pricing_checked_at: str | None = None,
) -> dict[str, Any]:
    if currency != "RUB":
        raise ValueError("unsupported estimate currency")
    normalized_rows: list[dict[str, str]] = []
    subtotal = Decimal("0")
    seen_ids: set[str] = set()
    trusted_evidence = price_evidence_by_row or {}
    for row in rows:
        if row.id in seen_ids:
            raise ValueError("estimate row IDs must be unique")
        seen_ids.add(row.id)
        try:
            quantity = Decimal(row.quantity)
            unit_price = Decimal(row.unit_price)
        except InvalidOperation:
            raise ValueError("estimate values must be decimal strings") from None
        if quantity < 0 or unit_price < 0:
            raise ValueError("estimate values cannot be negative")
        line_total = (quantity * unit_price).quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        subtotal += line_total
        normalized_row: dict[str, Any] = {
                "id": row.id,
                "section": row.section,
                "kind": row.kind,
                "description": row.description,
                "unit": row.unit,
                "quantity": _quantity(row.quantity),
                "unit_price": _money(unit_price),
                "line_total": _money(line_total),
                "quantity_basis": row.quantity_basis,
                "price_basis": row.price_basis,
        }
        evidence = trusted_evidence.get(row.id)
        if evidence is not None:
            normalized_evidence = _normalized_price_evidence(evidence)
            if normalized_evidence["landed_unit_price"] != _money(unit_price):
                raise ValueError("price evidence does not match applied unit price")
            normalized_row["price_basis"] = _price_basis_from_evidence(
                normalized_evidence
            )
            normalized_row["price_evidence"] = normalized_evidence
        normalized_rows.append(normalized_row)
    total = subtotal.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    return {
        "schema_id": "kolibri.estimate_draft",
        "schema_version": "1.2",
        "title": title,
        "currency": currency,
        "region": region,
        "assumptions": list(assumptions or []),
        "generation": generation,
        "rows": normalized_rows,
        "pricing": _pricing_summary(
            normalized_rows,
            last_checked_at=pricing_checked_at,
        ),
        "totals": {
            "subtotal": _money(subtotal),
            "total": _money(total),
        },
        "updated_at": now,
    }


def estimate_document_from_proposal(
    proposal: GeneratedEstimateProposal,
    *,
    now: str,
    provider_profile: str,
    run_id: str,
) -> dict[str, Any]:
    rows = [
        EstimateRowInput(
            id=f"row_{uuid.uuid4().hex}",
            section=row.section,
            kind=row.kind,
            description=row.description,
            unit=row.unit,
            quantity=row.quantity,
            unitPrice=row.unit_price,
            quantityBasis=row.quantity_basis,
            priceBasis=row.price_basis,
        )
        for row in proposal.rows
    ]
    return normalize_estimate_document(
        title=proposal.title,
        currency="RUB",
        rows=rows,
        now=now,
        region=proposal.region,
        assumptions=proposal.assumptions,
        generation={
            "provider_profile": provider_profile,
            "run_id": run_id,
        },
    )


def parse_estimate_document(raw: object, *, now: str) -> dict[str, Any]:
    if not isinstance(raw, str):
        return empty_estimate_document(now)
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return empty_estimate_document(now)
    if (
        not isinstance(value, dict)
        or value.get("schema_id") != "kolibri.estimate_draft"
        or value.get("schema_version") not in {"1.0", "1.1", "1.2"}
        or not isinstance(value.get("title"), str)
        or value.get("currency") != "RUB"
        or not isinstance(value.get("rows"), list)
        or not isinstance(value.get("totals"), dict)
    ):
        return empty_estimate_document(now)
    value["schema_version"] = "1.2"
    value.setdefault("region", None)
    value.setdefault("assumptions", [])
    value.setdefault("generation", None)
    existing_pricing = value.get("pricing")
    for row in value["rows"]:
        if not isinstance(row, dict):
            continue
        row.setdefault("section", "Прочее")
        row.setdefault("kind", "service")
        row.setdefault("quantity_basis", "Введено вручную")
        row.setdefault("price_basis", "Введено вручную")
        evidence = row.get("price_evidence")
        if isinstance(evidence, dict):
            try:
                row["price_evidence"] = _normalized_price_evidence(evidence)
            except (TypeError, ValueError):
                row.pop("price_evidence", None)
    value["pricing"] = _pricing_summary(
        [
            row
            for row in value["rows"]
            if isinstance(row, dict)
        ],
        last_checked_at=(
            str(existing_pricing.get("last_checked_at"))
            if isinstance(existing_pricing, dict)
            and isinstance(existing_pricing.get("last_checked_at"), str)
            else None
        ),
    )
    return value


def estimate_document_with_prices(
    document: Mapping[str, Any],
    *,
    evidence_by_row: Mapping[str, Mapping[str, Any]],
    now: str,
) -> dict[str, Any]:
    existing_rows = document.get("rows")
    if not isinstance(existing_rows, list):
        raise ValueError("estimate rows are missing")
    row_inputs: list[EstimateRowInput] = []
    retained_evidence: dict[str, Mapping[str, Any]] = {}
    for raw_row in existing_rows:
        if not isinstance(raw_row, dict):
            continue
        row_id = str(raw_row.get("id") or "")
        evidence = evidence_by_row.get(row_id)
        unit_price = (
            str(evidence.get("landed_unit_price"))
            if evidence is not None
            else str(raw_row.get("unit_price") or "0.00")
        )
        row_inputs.append(
            EstimateRowInput(
                id=row_id,
                section=str(raw_row.get("section") or "Прочее"),
                kind=str(raw_row.get("kind") or "service"),
                description=str(raw_row.get("description") or ""),
                unit=str(raw_row.get("unit") or ""),
                quantity=str(raw_row.get("quantity") or "0"),
                unitPrice=unit_price,
                quantityBasis=str(
                    raw_row.get("quantity_basis") or "Введено вручную"
                ),
                priceBasis=str(
                    raw_row.get("price_basis") or "Введено вручную"
                ),
            )
        )
        if evidence is not None:
            retained_evidence[row_id] = evidence
        elif isinstance(raw_row.get("price_evidence"), dict):
            retained_evidence[row_id] = raw_row["price_evidence"]
    return normalize_estimate_document(
        title=str(document.get("title") or "Черновик сметы"),
        currency="RUB",
        rows=row_inputs,
        now=now,
        region=(
            str(document["region"])
            if isinstance(document.get("region"), str)
            else None
        ),
        assumptions=[
            str(item)
            for item in document.get("assumptions", [])
            if isinstance(item, str)
        ],
        generation=(
            {
                "provider_profile": str(
                    document["generation"].get("provider_profile") or ""
                ),
                "run_id": str(document["generation"].get("run_id") or ""),
            }
            if isinstance(document.get("generation"), dict)
            else None
        ),
        price_evidence_by_row=retained_evidence,
        pricing_checked_at=now,
    )


def estimate_view(
    *,
    project_id: str,
    document_id: str,
    version: int,
    status: str,
    document: dict[str, Any],
) -> dict[str, Any]:
    rows = document.get("rows")
    totals = document.get("totals")
    generation = document.get("generation")
    return {
        "schemaId": "kolibri.estimate_draft",
        "schemaVersion": "1.2",
        "projectId": project_id,
        "documentId": document_id,
        "version": version,
        "status": status,
        "estimateTitle": str(document.get("title") or "Черновик сметы"),
        "currency": "RUB",
        "estimateRegion": (
            str(document["region"])
            if isinstance(document.get("region"), str)
            else None
        ),
        "assumptions": [
            str(item)
            for item in document.get("assumptions", [])
            if isinstance(item, str)
        ][:20],
        "generation": (
            {
                "providerProfile": str(generation.get("provider_profile") or ""),
                "runId": str(generation.get("run_id") or ""),
            }
            if isinstance(generation, dict)
            else None
        ),
        "rows": [
            {
                "id": str(row.get("id")),
                "section": str(row.get("section") or "Прочее"),
                "kind": str(row.get("kind") or "service"),
                "description": str(row.get("description")),
                "unit": str(row.get("unit")),
                "quantity": str(row.get("quantity")),
                "unitPrice": str(row.get("unit_price")),
                "lineTotal": str(row.get("line_total")),
                "quantityBasis": str(
                    row.get("quantity_basis") or "Введено вручную"
                ),
                "priceBasis": str(row.get("price_basis") or "Введено вручную"),
                "priceEvidence": (
                    {
                        "status": str(row["price_evidence"]["status"]),
                        "sourceType": str(row["price_evidence"]["source_type"]),
                        "sourceLabel": str(row["price_evidence"]["source_label"]),
                        "sourceUrl": str(row["price_evidence"]["source_url"]),
                        "sourceReference": str(
                            row["price_evidence"]["source_reference"]
                        ),
                        "snapshotHash": str(
                            row["price_evidence"]["snapshot_hash"]
                        ),
                        "quoteId": str(row["price_evidence"]["quote_id"]),
                        "materialCode": row["price_evidence"].get("material_code"),
                        "materialName": row["price_evidence"].get("material_name"),
                        "region": str(row["price_evidence"]["region"]),
                        "priceZone": row["price_evidence"].get("price_zone"),
                        "period": row["price_evidence"].get("period"),
                        "priceDate": str(row["price_evidence"]["price_date"]),
                        "retrievedAt": str(row["price_evidence"]["retrieved_at"]),
                        "freshUntil": str(row["price_evidence"]["fresh_until"]),
                        "freshnessBasis": str(
                            row["price_evidence"]["freshness_basis"]
                        ),
                        "taxStatus": str(row["price_evidence"]["tax_status"]),
                        "priceScope": str(row["price_evidence"]["price_scope"]),
                        "unitPrice": str(row["price_evidence"]["unit_price"]),
                        "deliveryPerUnit": str(
                            row["price_evidence"]["delivery_per_unit"]
                        ),
                        "landedUnitPrice": str(
                            row["price_evidence"]["landed_unit_price"]
                        ),
                        "landedCostStatus": str(
                            row["price_evidence"]["landed_cost_status"]
                        ),
                        "sourceDistancePrice": row["price_evidence"].get(
                            "source_distance_price"
                        ),
                        "sourceProcurementStoragePercent": row[
                            "price_evidence"
                        ].get("source_procurement_storage_percent"),
                        "bindingStatus": str(
                            row["price_evidence"]["binding_status"]
                        ),
                        "availability": str(
                            row["price_evidence"]["availability"]
                        ),
                        "leadTimeDays": row["price_evidence"].get(
                            "lead_time_days"
                        ),
                    }
                    if isinstance(row.get("price_evidence"), dict)
                    else None
                ),
                **(
                    {
                        "enginePriceProvenance": {
                            **{
                                key: value
                                for key, value in row[
                                    "engine_price_provenance"
                                ].items()
                                if key != "url"
                            },
                            "sourceUrl": row[
                                "engine_price_provenance"
                            ].get("sourceUrl")
                            or row["engine_price_provenance"].get("url"),
                        }
                    }
                    if isinstance(row.get("engine_price_provenance"), dict)
                    else {}
                ),
            }
            for row in rows
            if isinstance(row, dict)
        ]
        if isinstance(rows, list)
        else [],
        "pricing": {
            "status": str(
                document.get("pricing", {}).get("status") or "unpriced"
            ),
            "sourcedRows": int(
                document.get("pricing", {}).get("sourced_rows") or 0
            ),
            "staleRows": int(
                document.get("pricing", {}).get("stale_rows") or 0
            ),
            "totalRows": int(
                document.get("pricing", {}).get("total_rows") or 0
            ),
            "lastCheckedAt": document.get("pricing", {}).get(
                "last_checked_at"
            ),
        },
        "totals": {
            "subtotal": str(totals.get("subtotal") or "0.00"),
            "total": str(totals.get("total") or "0.00"),
        }
        if isinstance(totals, dict)
        else {"subtotal": "0.00", "total": "0.00"},
        "updatedAt": str(document.get("updated_at") or ""),
    }


def record_estimate_version(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    document_id: str,
    version: int,
    status: str,
    document: dict[str, Any],
    origin_type: Literal["ai_proposal", "manual_edit", "engine_calculation"],
    origin_run_id: str | None,
    created_by_user_id: str,
    created_at: str,
) -> None:
    database.execute(
        """
        INSERT INTO estimate_versions (
            tenant_id, id, project_id, document_id, version, status,
            content_json, content_hash, origin_type, origin_run_id,
            created_by_user_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tenant_id,
            f"estimate_version_{uuid.uuid4().hex}",
            project_id,
            document_id,
            version,
            status,
            canonical_estimate_json(document),
            estimate_content_hash(document),
            origin_type,
            origin_run_id,
            created_by_user_id,
            created_at,
        ),
    )


def load_estimate_slot(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
) -> sqlite3.Row | None:
    return database.execute(
        """
        SELECT id, version, status, content_json, updated_at
        FROM document_slots
        WHERE tenant_id = ? AND project_id = ? AND slot_type = 'estimate'
        LIMIT 1
        """,
        (tenant_id, project_id),
    ).fetchone()
