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
PRICEBOOK_VERSION = "kolibri-ru-2026q2-v1"
DETERMINISTIC_TIMESTAMP = "2026-06-29T00:00:00+00:00"
REGION_PROFILES = {
    "татарстан": {"label": "Республика Татарстан", "labor_coeff": Decimal("1.00"), "material_coeff": Decimal("1.00")},
    "республика татарстан": {"label": "Республика Татарстан", "labor_coeff": Decimal("1.00"), "material_coeff": Decimal("1.00")},
    "москва": {"label": "Москва", "labor_coeff": Decimal("1.28"), "material_coeff": Decimal("1.12")},
    "санкт-петербург": {"label": "Санкт-Петербург", "labor_coeff": Decimal("1.18"), "material_coeff": Decimal("1.08")},
    "россия": {"label": "Россия", "labor_coeff": Decimal("1.00"), "material_coeff": Decimal("1.00")},
}


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
    region: str = "Россия"
    currency: str = "RUB"
    pricebook_version: str = PRICEBOOK_VERSION
    input_hash: str | None = None
    deterministic: bool = False
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


def canonical_text(value: str) -> str:
    return " ".join(value.strip().lower().replace("ё", "е").split())


def canonical_input_hash(payload: dict[str, Any]) -> str:
    return _fingerprint(payload)


def deterministic_estimate_id(input_hash: str) -> str:
    return f"EST-{input_hash[:10].upper()}"


def region_profile(region: str) -> dict[str, Decimal | str]:
    return REGION_PROFILES.get(canonical_text(region), REGION_PROFILES["россия"])


def fixed_price_provenance(region: str, confidence: str = "0.98") -> PriceProvenance:
    profile = region_profile(region)
    return PriceProvenance(
        source="kolibri_pricebook",
        label=f"{profile['label']} / {PRICEBOOK_VERSION}",
        captured_at=DETERMINISTIC_TIMESTAMP,
        confidence=Decimal(confidence),
    )


def priced(value: Decimal | int | float | str, coeff: Decimal) -> Decimal:
    return money(decimal_value(value) * coeff)


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
        "calculated_at": DETERMINISTIC_TIMESTAMP if estimate.deterministic else utc_now(),
        "formula": "labor + materials + overhead + tax",
        "pricebook_version": estimate.pricebook_version,
        "input_hash": estimate.input_hash,
    }]
    estimate.updated_at = DETERMINISTIC_TIMESTAMP if estimate.deterministic else utc_now()
    return estimate


def detect_area(prompt: str, fallback: Decimal = Decimal("20.00")) -> Decimal:
    match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:м2|м²|кв\.?\s*м|m2)", prompt, flags=re.IGNORECASE)
    if not match:
        return fallback
    return decimal_value(match.group(1))


def detect_region(prompt: str, fallback: str = "Россия") -> str:
    normalized = canonical_text(prompt)
    for key, profile in REGION_PROFILES.items():
        if key != "россия" and key in normalized:
            return str(profile["label"])
    return fallback


def plastering_sections(area: Decimal, region: str) -> list[EstimateSection]:
    profile = region_profile(region)
    labor_coeff = profile["labor_coeff"]
    material_coeff = profile["material_coeff"]
    provenance = fixed_price_provenance(region)
    return [
        EstimateSection(title="Подготовка основания", items=[
            EstimateItem(
                name="Грунтование стен под штукатурку",
                unit="м2",
                quantity=area,
                labor_unit_price=priced("95.00", labor_coeff),
                material_unit_price=priced("38.00", material_coeff),
                provenance=provenance,
            ),
            EstimateItem(
                name="Установка штукатурных маяков",
                unit="м2",
                quantity=area,
                labor_unit_price=priced("140.00", labor_coeff),
                material_unit_price=priced("42.00", material_coeff),
                provenance=provenance,
            ),
        ]),
        EstimateSection(title="Штукатурные работы", items=[
            EstimateItem(
                name="Штукатурка стен гипсовой смесью до 20 мм",
                unit="м2",
                quantity=area,
                labor_unit_price=priced("620.00", labor_coeff),
                material_unit_price=priced("285.00", material_coeff),
                provenance=provenance,
            ),
            EstimateItem(
                name="Финишное выравнивание под шпаклевание",
                unit="м2",
                quantity=area,
                labor_unit_price=priced("210.00", labor_coeff),
                material_unit_price=priced("75.00", material_coeff),
                provenance=provenance,
            ),
        ]),
    ]


def create_estimate_from_prompt(prompt: str, *, client_name: str = "Клиент", region: str | None = None, quality_level: str = "standard") -> Estimate:
    normalized = prompt.lower()
    area = detect_area(prompt)
    detected_region = region or detect_region(prompt)
    canonical_payload = {
        "prompt": canonical_text(prompt),
        "client_name": canonical_text(client_name),
        "region": canonical_text(detected_region),
        "area": str(area),
        "quality_level": canonical_text(quality_level),
        "pricebook_version": PRICEBOOK_VERSION,
    }
    input_hash = canonical_input_hash(canonical_payload)
    title = "Смета на ремонт"
    if "кух" in normalized:
        title = "Смета на ремонт кухни"
    elif "ван" in normalized or "сануз" in normalized:
        title = "Смета на ремонт санузла"
    elif "кварт" in normalized:
        title = "Смета на ремонт квартиры"
    multiplier = max(area, Decimal("1.00"))
    profile = region_profile(detected_region)
    labor_coeff = profile["labor_coeff"]
    material_coeff = profile["material_coeff"]
    provenance = fixed_price_provenance(detected_region, "0.98")
    if "штукатур" in normalized:
        title = "Смета на штукатурные работы"
        sections = plastering_sections(multiplier, detected_region)
    else:
        sections = [
            EstimateSection(title="Подготовка", items=[
                EstimateItem(name="Защита поверхностей и подготовка", unit="м2", quantity=multiplier, labor_unit_price=priced("180.00", labor_coeff), material_unit_price=priced("45.00", material_coeff), provenance=provenance),
                EstimateItem(name="Демонтажные работы", unit="м2", quantity=multiplier, labor_unit_price=priced("320.00", labor_coeff), material_unit_price=Decimal("0.00"), provenance=provenance),
            ]),
            EstimateSection(title="Отделка", items=[
                EstimateItem(name="Выравнивание стен", unit="м2", quantity=multiplier, labor_unit_price=priced("520.00", labor_coeff), material_unit_price=priced("210.00", material_coeff), provenance=provenance),
                EstimateItem(name="Финишная отделка", unit="м2", quantity=multiplier, labor_unit_price=priced("680.00", labor_coeff), material_unit_price=priced("360.00", material_coeff), provenance=provenance),
            ]),
        ]
    estimate = Estimate(
        estimate_id=deterministic_estimate_id(input_hash),
        title=title,
        client_name=client_name,
        region=str(profile["label"]),
        pricebook_version=PRICEBOOK_VERSION,
        input_hash=input_hash,
        deterministic=True,
        sections=sections,
        overhead_rate=Decimal("7.00"),
        tax_rate=Decimal("0.00"),
        created_at=DETERMINISTIC_TIMESTAMP,
        updated_at=DETERMINISTIC_TIMESTAMP,
    )
    return recalculate_estimate(estimate)


def normalize_estimate_payload(payload: dict[str, Any]) -> Estimate:
    estimate = Estimate.model_validate(payload)
    return recalculate_estimate(estimate)
