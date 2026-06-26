from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from pydantic import BaseModel, Field

TWOPLACES = Decimal("0.01")


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


def _fingerprint(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


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
