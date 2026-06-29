from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

TWOPLACES = Decimal("0.01")
ESTIMATE_API_CONTRACT_VERSION = "estimate-api-contract/v1"
CANONICAL_HASH_ALGORITHM = "sha256"
CLAIM_ACCURACY_MIN = Decimal("98.00")
CLAIM_ACCURACY_MAX = Decimal("99.00")
MUTABLE_ESTIMATE_ROOTS = {"title", "client_name", "object_address", "currency", "sections", "overhead_rate", "tax_rate"}
DERIVED_ESTIMATE_FIELDS = {"estimate_id", "totals", "calculation_audit", "created_at", "updated_at"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def decimal_value(value: Decimal | int | float | str) -> Decimal:
    if isinstance(value, Decimal):
        raw = value
    else:
        raw = Decimal(str(value).replace(",", "."))
    return raw.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def money(value: Decimal | int | float | str) -> Decimal:
    return decimal_value(value)


class PriceProvenance(BaseModel):
    source: str = "manual"
    label: str = "Ручной ввод"
    captured_at: str = Field(default_factory=utc_now)
    confidence: Decimal = Decimal("1.00")


class EstimateItem(BaseModel):
    name: str
    unit: str = "шт"
    quantity: Decimal = Decimal("1.00")
    labor_unit_price: Decimal = Decimal("0.00")
    material_unit_price: Decimal = Decimal("0.00")
    note: str | None = None
    provenance: PriceProvenance = Field(default_factory=PriceProvenance)

    def labor_total(self) -> Decimal:
        return money(self.quantity * self.labor_unit_price)

    def material_total(self) -> Decimal:
        return money(self.quantity * self.material_unit_price)

    def line_total(self) -> Decimal:
        return money(self.labor_total() + self.material_total())


class EstimateSection(BaseModel):
    title: str
    items: list[EstimateItem] = Field(default_factory=list)


class EstimateTotals(BaseModel):
    labor: Decimal = Decimal("0.00")
    materials: Decimal = Decimal("0.00")
    subtotal: Decimal = Decimal("0.00")
    overhead: Decimal = Decimal("0.00")
    tax: Decimal = Decimal("0.00")
    grand_total: Decimal = Decimal("0.00")


class Estimate(BaseModel):
    estimate_id: str = Field(default_factory=lambda: f"EST-{uuid.uuid4().hex[:10].upper()}")
    title: str = "Смета"
    client_name: str = "Клиент"
    object_address: str = "Адрес объекта не указан"
    currency: str = "RUB"
    sections: list[EstimateSection] = Field(default_factory=list)
    overhead_rate: Decimal = Decimal("0.00")
    tax_rate: Decimal = Decimal("0.00")
    totals: EstimateTotals = Field(default_factory=EstimateTotals)
    calculation_audit: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def canonical_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def claim_accuracy_percent(value: Decimal | int | float | str) -> Decimal:
    if isinstance(value, Decimal):
        raw = value
    else:
        raw = Decimal(str(value).replace(",", "."))
    if raw < CLAIM_ACCURACY_MIN or raw > CLAIM_ACCURACY_MAX:
        raise ValueError("claim_accuracy_percent must be between 98.00 and 99.00 inclusive")
    return raw.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def claim_constraints_payload() -> dict[str, str | bool]:
    return {
        "allowed_accuracy_percent_min": str(CLAIM_ACCURACY_MIN),
        "allowed_accuracy_percent_max": str(CLAIM_ACCURACY_MAX),
        "requires_human_review": True,
        "claim_scope": "deterministic arithmetic and canonical hash integrity only",
    }


def _normalize_text(value: Any, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} must not be empty")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _normalize_currency(value: Any) -> str:
    if value is None:
        raise ValueError("currency must not be empty")
    normalized = str(value).strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", normalized):
        raise ValueError("currency must be an ISO-4217 style 3-letter code")
    return normalized


class EstimateGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    client_name: str = Field(default="Клиент", min_length=1, max_length=200)
    object_address: str = Field(default="Адрес объекта не указан", min_length=1, max_length=500)
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    claim_accuracy_percent: Decimal = Field(default=CLAIM_ACCURACY_MIN)

    @field_validator("prompt", "client_name", "object_address", mode="before")
    @classmethod
    def _strip_required_text(cls, value: Any) -> str:
        return _normalize_text(value, "text")

    @field_validator("currency", mode="before")
    @classmethod
    def _strip_currency(cls, value: Any) -> str:
        return _normalize_currency(value)

    @field_validator("claim_accuracy_percent")
    @classmethod
    def _validate_claim_accuracy(cls, value: Decimal | int | float | str) -> Decimal:
        return claim_accuracy_percent(value)


class EstimateEditOperation(BaseModel):
    op: Literal["add", "replace", "remove"]
    path: str = Field(..., description="RFC-6901 JSON pointer into mutable estimate fields.")
    value: Any | None = None

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("path must be an absolute JSON pointer")
        return value


class EstimateEditRequest(BaseModel):
    estimate: Estimate
    edits: list[EstimateEditOperation] = Field(..., min_length=1, max_length=100)
    base_canonical_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    claim_accuracy_percent: Decimal = Field(default=CLAIM_ACCURACY_MIN)

    @field_validator("claim_accuracy_percent")
    @classmethod
    def _validate_claim_accuracy(cls, value: Decimal | int | float | str) -> Decimal:
        return claim_accuracy_percent(value)


class EstimateApiResponse(BaseModel):
    contract_version: str = ESTIMATE_API_CONTRACT_VERSION
    hash_algorithm: str = CANONICAL_HASH_ALGORITHM
    estimate: Estimate
    canonical_json: str
    canonical_hash: str
    input_hash: str
    previous_hash: str | None = None
    claim_accuracy_percent: Decimal
    claim_constraints: dict[str, str | bool] = Field(default_factory=claim_constraints_payload)
    edit_audit: list[dict[str, Any]] = Field(default_factory=list)


def _fingerprint(payload: dict[str, Any]) -> str:
    return canonical_hash(payload)


def recalculate_estimate(estimate: Estimate) -> Estimate:
    labor = Decimal("0.00")
    materials = Decimal("0.00")
    audit: list[dict[str, Any]] = []
    for section in estimate.sections:
        for item in section.items:
            item.quantity = decimal_value(item.quantity)
            item.labor_unit_price = decimal_value(item.labor_unit_price)
            item.material_unit_price = decimal_value(item.material_unit_price)
            labor_line = item.labor_total()
            material_line = item.material_total()
            labor += labor_line
            materials += material_line
            audit.append({
                "section": section.title,
                "item": item.name,
                "quantity": str(item.quantity),
                "labor_unit_price": str(item.labor_unit_price),
                "material_unit_price": str(item.material_unit_price),
                "labor_total": str(labor_line),
                "material_total": str(material_line),
                "line_total": str(item.line_total()),
                "source": item.provenance.source,
            })
    labor = money(labor)
    materials = money(materials)
    subtotal = money(labor + materials)
    overhead = money(subtotal * decimal_value(estimate.overhead_rate) / Decimal("100"))
    tax = money((subtotal + overhead) * decimal_value(estimate.tax_rate) / Decimal("100"))
    grand_total = money(subtotal + overhead + tax)
    estimate.totals = EstimateTotals(labor=labor, materials=materials, subtotal=subtotal, overhead=overhead, tax=tax, grand_total=grand_total)
    audit_payload = {
        "estimate_id": estimate.estimate_id,
        "sections": audit,
        "overhead_rate": str(decimal_value(estimate.overhead_rate)),
        "tax_rate": str(decimal_value(estimate.tax_rate)),
        "totals": estimate.totals.model_dump(mode="json"),
    }
    estimate.calculation_audit = audit + [{
        "kind": "totals",
        "fingerprint": _fingerprint(audit_payload),
        "calculated_at": utc_now(),
        "formula": "labor + materials + overhead + tax",
    }]
    estimate.updated_at = utc_now()
    return estimate


def estimate_contract_schema() -> dict[str, Any]:
    return {
        "contract_version": ESTIMATE_API_CONTRACT_VERSION,
        "hash_algorithm": CANONICAL_HASH_ALGORITHM,
        "canonicalization": {
            "json": "json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "excluded_estimate_fields": sorted(DERIVED_ESTIMATE_FIELDS | {"provenance.captured_at"}),
            "decimal_format": "fixed two decimal string for money, quantities, rates, and totals",
        },
        "claim_constraints": claim_constraints_payload(),
        "endpoints": {
            "generate": "POST /api/v1/estimate/generate",
            "edit": "POST /api/v1/estimate/edit",
            "schema": "GET /api/v1/estimate/schema",
        },
        "schemas": {
            "EstimateGenerateRequest": EstimateGenerateRequest.model_json_schema(),
            "EstimateEditRequest": EstimateEditRequest.model_json_schema(),
            "EstimateApiResponse": EstimateApiResponse.model_json_schema(),
            "Estimate": Estimate.model_json_schema(),
        },
    }


def estimate_generate_input_payload(request: EstimateGenerateRequest) -> dict[str, Any]:
    return {
        "contract_version": ESTIMATE_API_CONTRACT_VERSION,
        "prompt": request.prompt,
        "client_name": request.client_name,
        "object_address": request.object_address,
        "currency": request.currency,
    }


def estimate_edit_input_payload(request: EstimateEditRequest, base_hash: str) -> dict[str, Any]:
    return {
        "contract_version": ESTIMATE_API_CONTRACT_VERSION,
        "base_canonical_hash": base_hash,
        "edits": [edit.model_dump(mode="json") for edit in request.edits],
    }


def _canonical_provenance(provenance: PriceProvenance) -> dict[str, str]:
    return {
        "source": provenance.source,
        "label": provenance.label,
        "confidence": str(decimal_value(provenance.confidence)),
    }


def canonical_estimate_payload(estimate: Estimate) -> dict[str, Any]:
    calculated = recalculate_estimate(estimate.model_copy(deep=True))
    sections: list[dict[str, Any]] = []
    for section in calculated.sections:
        items: list[dict[str, Any]] = []
        for item in section.items:
            items.append({
                "name": item.name,
                "unit": item.unit,
                "quantity": str(decimal_value(item.quantity)),
                "labor_unit_price": str(decimal_value(item.labor_unit_price)),
                "material_unit_price": str(decimal_value(item.material_unit_price)),
                "note": item.note,
                "provenance": _canonical_provenance(item.provenance),
                "labor_total": str(item.labor_total()),
                "material_total": str(item.material_total()),
                "line_total": str(item.line_total()),
            })
        sections.append({"title": section.title, "items": items})
    return {
        "contract_version": ESTIMATE_API_CONTRACT_VERSION,
        "estimate": {
            "estimate_id": calculated.estimate_id,
            "title": calculated.title,
            "client_name": calculated.client_name,
            "object_address": calculated.object_address,
            "currency": calculated.currency,
            "sections": sections,
            "overhead_rate": str(decimal_value(calculated.overhead_rate)),
            "tax_rate": str(decimal_value(calculated.tax_rate)),
            "totals": {
                "labor": str(decimal_value(calculated.totals.labor)),
                "materials": str(decimal_value(calculated.totals.materials)),
                "subtotal": str(decimal_value(calculated.totals.subtotal)),
                "overhead": str(decimal_value(calculated.totals.overhead)),
                "tax": str(decimal_value(calculated.totals.tax)),
                "grand_total": str(decimal_value(calculated.totals.grand_total)),
            },
        },
    }


def canonical_estimate_hash(estimate: Estimate) -> str:
    return canonical_hash(canonical_estimate_payload(estimate))


def estimate_api_response(
    estimate: Estimate,
    *,
    input_hash: str,
    claim_accuracy: Decimal | int | float | str = CLAIM_ACCURACY_MIN,
    previous_hash: str | None = None,
    edit_audit: list[dict[str, Any]] | None = None,
) -> EstimateApiResponse:
    calculated = recalculate_estimate(estimate.model_copy(deep=True))
    payload = canonical_estimate_payload(calculated)
    return EstimateApiResponse(
        estimate=calculated,
        canonical_json=canonical_json(payload),
        canonical_hash=canonical_hash(payload),
        input_hash=input_hash,
        previous_hash=previous_hash,
        claim_accuracy_percent=claim_accuracy_percent(claim_accuracy),
        edit_audit=edit_audit or [],
    )


def create_estimate_api_from_prompt(request: EstimateGenerateRequest | dict[str, Any]) -> EstimateApiResponse:
    if isinstance(request, dict):
        request = EstimateGenerateRequest.model_validate(request)
    input_payload = estimate_generate_input_payload(request)
    input_hash = canonical_hash(input_payload)
    estimate = create_estimate_from_prompt(
        request.prompt,
        client_name=request.client_name,
        estimate_id=f"EST-{input_hash[:10].upper()}",
        object_address=request.object_address,
        currency=request.currency,
    )
    return estimate_api_response(estimate, input_hash=input_hash, claim_accuracy=request.claim_accuracy_percent)


def _json_pointer_tokens(path: str) -> list[str]:
    if path == "":
        raise ValueError("path must not be empty")
    if not path.startswith("/"):
        raise ValueError("path must be an absolute JSON pointer")
    return [token.replace("~1", "/").replace("~0", "~") for token in path[1:].split("/")]


def _assert_mutable_path(tokens: list[str]) -> None:
    if not tokens:
        raise ValueError("path must target a mutable estimate field")
    root = tokens[0]
    if root not in MUTABLE_ESTIMATE_ROOTS:
        raise ValueError(f"edits may only target: {', '.join(sorted(MUTABLE_ESTIMATE_ROOTS))}")
    if any(token in DERIVED_ESTIMATE_FIELDS for token in tokens):
        raise ValueError("estimate_id, totals, timestamps, and calculation_audit are derived or immutable")


def _list_index(token: str, length: int, *, allow_end: bool = False) -> int:
    if token == "-" and allow_end:
        return length
    if not token.isdigit():
        raise ValueError("list path token must be a non-negative integer")
    index = int(token)
    max_index = length if allow_end else length - 1
    if index < 0 or index > max_index:
        raise ValueError("list path index is out of range")
    return index


def _resolve_parent(document: dict[str, Any], tokens: list[str]) -> tuple[Any, str]:
    target: Any = document
    for token in tokens[:-1]:
        if isinstance(target, list):
            target = target[_list_index(token, len(target))]
        elif isinstance(target, dict):
            if token not in target:
                raise ValueError(f"path segment does not exist: {token}")
            target = target[token]
        else:
            raise ValueError("path traverses a scalar value")
    return target, tokens[-1]


def _apply_edit_operation(document: dict[str, Any], edit: EstimateEditOperation) -> None:
    tokens = _json_pointer_tokens(edit.path)
    _assert_mutable_path(tokens)
    parent, key = _resolve_parent(document, tokens)
    if edit.op == "add":
        if edit.value is None:
            raise ValueError("add requires value")
        if isinstance(parent, list):
            parent.insert(_list_index(key, len(parent), allow_end=True), edit.value)
            return
        if isinstance(parent, dict):
            parent[key] = edit.value
            return
    if edit.op == "replace":
        if isinstance(parent, list):
            parent[_list_index(key, len(parent))] = edit.value
            return
        if isinstance(parent, dict):
            if key not in parent:
                raise ValueError(f"path segment does not exist: {key}")
            parent[key] = edit.value
            return
    if edit.op == "remove":
        if isinstance(parent, list):
            parent.pop(_list_index(key, len(parent)))
            return
        if isinstance(parent, dict):
            if key not in parent:
                raise ValueError(f"path segment does not exist: {key}")
            parent.pop(key)
            return
    raise ValueError("path does not target a list or object")


def apply_estimate_edits(estimate: Estimate, edits: list[EstimateEditOperation]) -> tuple[Estimate, list[dict[str, Any]]]:
    payload = estimate.model_dump(mode="json")
    audit: list[dict[str, Any]] = []
    for edit in edits:
        _apply_edit_operation(payload, edit)
        audit.append({"op": edit.op, "path": edit.path})
    updated = Estimate.model_validate(payload)
    return recalculate_estimate(updated), audit


def edit_estimate_api(request: EstimateEditRequest | dict[str, Any]) -> EstimateApiResponse:
    if isinstance(request, dict):
        request = EstimateEditRequest.model_validate(request)
    base_hash = canonical_estimate_hash(request.estimate)
    if request.base_canonical_hash and request.base_canonical_hash != base_hash:
        raise ValueError("base_canonical_hash does not match estimate canonical_hash")
    estimate, audit = apply_estimate_edits(request.estimate, request.edits)
    input_hash = canonical_hash(estimate_edit_input_payload(request, base_hash))
    return estimate_api_response(
        estimate,
        input_hash=input_hash,
        claim_accuracy=request.claim_accuracy_percent,
        previous_hash=base_hash,
        edit_audit=audit,
    )


def detect_area(prompt: str, fallback: Decimal = Decimal("20.00")) -> Decimal:
    match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:м2|м²|кв\.?\s*м|m2)", prompt, flags=re.IGNORECASE)
    if not match:
        return fallback
    return decimal_value(match.group(1))


def create_estimate_from_prompt(
    prompt: str,
    *,
    client_name: str = "Клиент",
    estimate_id: str | None = None,
    object_address: str = "Адрес объекта не указан",
    currency: str = "RUB",
) -> Estimate:
    normalized = prompt.lower()
    area = detect_area(prompt)
    title = "Смета на ремонт"
    if "кух" in normalized:
        title = "Смета на ремонт кухни"
    elif "ван" in normalized or "сануз" in normalized:
        title = "Смета на ремонт санузла"
    elif "кварт" in normalized:
        title = "Смета на ремонт квартиры"
    multiplier = max(area, Decimal("1.00"))
    sections = [
        EstimateSection(title="Подготовка", items=[
            EstimateItem(name="Защита поверхностей и подготовка", unit="м2", quantity=multiplier, labor_unit_price=Decimal("180.00"), material_unit_price=Decimal("45.00")),
            EstimateItem(name="Демонтажные работы", unit="м2", quantity=multiplier, labor_unit_price=Decimal("320.00"), material_unit_price=Decimal("0.00")),
        ]),
        EstimateSection(title="Отделка", items=[
            EstimateItem(name="Выравнивание стен", unit="м2", quantity=multiplier, labor_unit_price=Decimal("520.00"), material_unit_price=Decimal("210.00")),
            EstimateItem(name="Финишная отделка", unit="м2", quantity=multiplier, labor_unit_price=Decimal("680.00"), material_unit_price=Decimal("360.00")),
        ]),
    ]
    estimate = Estimate(
        estimate_id=estimate_id or f"EST-{uuid.uuid4().hex[:10].upper()}",
        title=title,
        client_name=client_name,
        object_address=object_address,
        currency=currency,
        sections=sections,
        overhead_rate=Decimal("7.00"),
        tax_rate=Decimal("0.00"),
    )
    return recalculate_estimate(estimate)


def normalize_estimate_payload(payload: dict[str, Any]) -> Estimate:
    estimate = Estimate.model_validate(payload)
    return recalculate_estimate(estimate)
