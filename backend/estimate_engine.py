from __future__ import annotations

import hashlib
import json
import re
import uuid
from enum import Enum
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from pydantic import BaseModel, Field

TWOPLACES = Decimal("0.01")
CALCULATION_ENGINE_VERSION = "est-calc-v1.0.0"
COEFFICIENT_SCALE = Decimal("100")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CalculationCoefficient(BaseModel):
    code: str
    percent: Decimal
    basis: Decimal
    amount: Decimal


def decimal_value(
    value: Decimal | int | float | str,
    *,
    precision: int = 2,
    rounding: str | RoundingMode = "half_up",
) -> Decimal:
    rounding_mode = _coerce_rounding(rounding)
    if isinstance(value, Decimal):
        raw = value
    else:
        raw = Decimal(str(value).replace(",", "."))
    scale = Decimal(1).scaleb(-max(precision, 0))
    if rounding_mode != RoundingMode.HALF_UP:
        raise ValueError(f"Unsupported rounding mode: {rounding_mode}")
    return raw.quantize(scale, rounding=ROUND_HALF_UP)


def money(
    value: Decimal | int | float | str,
    *,
    precision: int = 2,
    rounding: str | RoundingMode = "half_up",
) -> Decimal:
    return decimal_value(value, precision=precision, rounding=rounding)


def _line_total(quantity: Decimal, unit_price: Decimal, *, precision: int, rounding: RoundingMode) -> Decimal:
    return money(quantity * unit_price, precision=precision, rounding=rounding)


def _apply_rate(
    basis: Decimal,
    percent: Decimal,
    *,
    precision: int,
    rounding: RoundingMode,
    code: str,
) -> tuple[Decimal, CalculationCoefficient]:
    normalized_percent = money(percent, precision=2, rounding=rounding)
    if normalized_percent == 0:
        return (
            money(Decimal("0.00"), precision=precision, rounding=rounding),
            CalculationCoefficient(code=f"{code}:0", percent=normalized_percent, basis=money(basis, precision=precision, rounding=rounding), amount=Decimal("0")),
        )
    amount = money((basis * normalized_percent) / COEFFICIENT_SCALE, precision=precision, rounding=rounding)
    return amount, CalculationCoefficient(
        code=code,
        percent=normalized_percent,
        basis=money(basis, precision=precision, rounding=rounding),
        amount=amount,
    )


class PriceProvenance(BaseModel):
    source: str = "manual"
    source_type: str = "manual"
    label: str = "Ручной ввод"
    source_record_id: str | None = None
    region: str | None = None
    publisher: str | None = None
    price_period: str | None = None
    price_date: str | None = None
    captured_at: str = Field(default_factory=utc_now)
    confidence: Decimal = Decimal("1.00")
    snapshot_sha256: str | None = None
    raw_snapshot_sha256: str | None = None
    url: str | None = None


class EstimateUnitCode(str, Enum):
    COUNT = "шт"
    SQUARE_METER = "м2"
    CUBIC_METER = "м3"
    KILOGRAM = "кг"
    MANHOUR = "чел.-ч"
    METER = "м"


class RoundingMode(str, Enum):
    HALF_UP = "half_up"


class EstimateJurisdictionPolicy(BaseModel):
    code: str = "RU"
    rounding_mode: RoundingMode = RoundingMode.HALF_UP
    quantity_precision: int = 2
    money_precision: int = 2


class EstimateStatus(str, Enum):
    needs_input = "needs_input"
    preliminary = "preliminary"
    source_backed = "source_backed"
    verified = "verified"


class VerificationStatus(str, Enum):
    unknown = "unknown"
    failed = "failed"
    partial = "partial"
    passed = "passed"


class EstimateItem(BaseModel):
    name: str
    unit: str = "шт"
    unit_code: EstimateUnitCode = EstimateUnitCode.COUNT
    quantity: Decimal = Decimal("1.00")
    labor_unit_price: Decimal = Decimal("0.00")
    material_unit_price: Decimal = Decimal("0.00")
    note: str | None = None
    provenance: PriceProvenance = Field(default_factory=PriceProvenance)
    wbs_code: str | None = None
    line_id: str = Field(default_factory=lambda: f"EL-{uuid.uuid4().hex[:12].upper()}")

    def labor_total(self) -> Decimal:
        return money(self.quantity * self.labor_unit_price)

    def material_total(self) -> Decimal:
        return money(self.quantity * self.material_unit_price)

    def line_total(self) -> Decimal:
        return money(self.labor_total() + self.material_total())


class EstimateSection(BaseModel):
    title: str
    items: list[EstimateItem] = Field(default_factory=list)
    section_id: str = Field(default_factory=lambda: f"ES-{uuid.uuid4().hex[:12].upper()}")
    wbs_code: str | None = None


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
    schema_version: str = "est-1.0"
    sections: list[EstimateSection] = Field(default_factory=list)
    overhead_rate: Decimal = Decimal("0.00")
    tax_rate: Decimal = Decimal("0.00")
    status: EstimateStatus = EstimateStatus.preliminary
    verification_status: VerificationStatus = VerificationStatus.unknown
    assumptions: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    object_type: str = "project"
    region: str | None = None
    municipality: str | None = None
    area_m2: Decimal | None = None
    price_basis_date: str | None = None
    source_coverage: Decimal = Decimal("1.00")
    totals: EstimateTotals = Field(default_factory=EstimateTotals)
    calculation_audit: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    jurisdiction: EstimateJurisdictionPolicy = Field(default_factory=EstimateJurisdictionPolicy)


def _fingerprint(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _coerce_rounding(value: RoundingMode | str) -> RoundingMode:
    if isinstance(value, RoundingMode):
        return value
    return RoundingMode(value)


def recalculate_estimate(estimate: Estimate) -> Estimate:
    qty_precision = max(int(estimate.jurisdiction.quantity_precision), 0)
    money_precision = max(int(estimate.jurisdiction.money_precision), 0)
    rounding = _coerce_rounding(estimate.jurisdiction.rounding_mode)

    labor = Decimal("0.00")
    materials = Decimal("0.00")
    source_rows = Decimal("0")
    source_backed_rows = Decimal("0")
    audit: list[dict[str, Any]] = []

    for section in estimate.sections:
        for item in section.items:
            source_rows += Decimal("1")
            if item.provenance.source_type == "official_fgis":
                source_backed_rows += Decimal("1")
            item.quantity = decimal_value(item.quantity, precision=qty_precision, rounding=rounding)
            item.labor_unit_price = decimal_value(item.labor_unit_price, precision=money_precision, rounding=rounding)
            item.material_unit_price = decimal_value(item.material_unit_price, precision=money_precision, rounding=rounding)
            labor_line = _line_total(item.quantity, item.labor_unit_price, precision=money_precision, rounding=rounding)
            material_line = _line_total(item.quantity, item.material_unit_price, precision=money_precision, rounding=rounding)
            labor += labor_line
            materials += material_line
            audit.append({
                "section": section.title,
                "section_id": section.section_id,
                "line_id": item.line_id,
                "item": item.name,
                "line_num": len(audit) + 1,
                "quantity": str(item.quantity),
                "labor_unit_price": str(item.labor_unit_price),
                "material_unit_price": str(item.material_unit_price),
                "labor_total": str(labor_line),
                "material_total": str(material_line),
                "line_total": str(_line_total(item.quantity, item.labor_unit_price + item.material_unit_price, precision=money_precision, rounding=rounding)),
                "source": item.provenance.source,
            })

    labor = money(labor, precision=money_precision, rounding=rounding)
    materials = money(materials, precision=money_precision, rounding=rounding)
    subtotal = money(labor + materials, precision=money_precision, rounding=rounding)
    overhead, overhead_coeff = _apply_rate(subtotal, estimate.overhead_rate, precision=money_precision, rounding=rounding, code="overhead")
    tax_basis = subtotal + overhead
    tax, tax_coeff = _apply_rate(tax_basis, estimate.tax_rate, precision=money_precision, rounding=rounding, code="tax")
    grand_total = money(subtotal + overhead + tax, precision=money_precision, rounding=rounding)
    coefficients = [overhead_coeff, tax_coeff]
    estimate.totals = EstimateTotals(labor=labor, materials=materials, subtotal=subtotal, overhead=overhead, tax=tax, grand_total=grand_total)
    if source_rows:
        estimate.source_coverage = decimal_value(source_backed_rows / source_rows, precision=2, rounding=rounding)

    coefficients_payload = [
        {
            "code": coeff.code,
            "percent": str(coeff.percent),
            "basis": str(coeff.basis),
            "amount": str(coeff.amount),
        }
        for coeff in coefficients
    ]
    audit_payload = {
        "estimate_id": estimate.estimate_id,
        "engine_version": CALCULATION_ENGINE_VERSION,
        "jurisdiction": estimate.jurisdiction.code,
        "quantity_precision": qty_precision,
        "money_precision": money_precision,
        "rounding_mode": estimate.jurisdiction.rounding_mode,
        "coefficients": coefficients_payload,
        "sections": audit,
        "overhead_rate": str(decimal_value(estimate.overhead_rate)),
        "tax_rate": str(decimal_value(estimate.tax_rate)),
        "totals": estimate.totals.model_dump(mode="json"),
    }
    estimate.calculation_audit = audit + [{
        "kind": "totals",
        "fingerprint": _fingerprint(audit_payload),
        "engine_version": CALCULATION_ENGINE_VERSION,
        "coefficients": coefficients_payload,
        "calculated_at": utc_now(),
        "formula": "labor + materials + overhead + tax",
    }]
    estimate.updated_at = utc_now()
    return estimate


def detect_area(prompt: str, fallback: Decimal = Decimal("20.00")) -> Decimal:
    match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:м2|м²|кв\.?\s*м|m2)", prompt, flags=re.IGNORECASE)
    if not match:
        return fallback
    return decimal_value(match.group(1))


def create_estimate_from_prompt(prompt: str, *, client_name: str = "Клиент") -> Estimate:
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
    estimate = Estimate(title=title, client_name=client_name, sections=sections, overhead_rate=Decimal("7.00"), tax_rate=Decimal("0.00"))
    return recalculate_estimate(estimate)


def normalize_estimate_payload(payload: dict[str, Any]) -> Estimate:
    estimate = Estimate.model_validate(payload)
    return recalculate_estimate(estimate)
