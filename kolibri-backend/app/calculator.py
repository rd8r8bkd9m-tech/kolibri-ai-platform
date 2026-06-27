"""Deterministic calculator engine for Kolibri estimates. 100% arithmetic accuracy."""
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
import json
import csv
import io

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_UNITS = {"м", "м²", "м³", "шт", "компл", "кг", "т", "км", "га", "чел-дн", "маш-час"}
D = Decimal


class EstimateStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    APPROVED = "approved"
    ARCHIVED = "archived"


class VATRate:
    ZERO = D("0")
    TEN = D("10")
    TWENTY = D("20")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EstimatePosition:
    id: str
    code: str
    name: str
    unit: str
    quantity: D
    price: D
    source: str = ""
    comment: str = ""
    sum: D = field(default=D("0"))

    def __post_init__(self):
        self.quantity = D(str(self.quantity))
        self.price = D(str(self.price))
        self.sum = D(str(self.sum))


@dataclass
class EstimateSection:
    id: str
    title: str
    positions: List[EstimatePosition] = field(default_factory=list)
    subtotal: D = field(default=D("0"))


@dataclass
class Estimate:
    id: str
    title: str
    status: EstimateStatus = EstimateStatus.DRAFT
    sections: List[EstimateSection] = field(default_factory=list)
    client: str = ""
    object_name: str = ""
    region: str = ""
    currency: str = "RUB"
    overhead_rate: D = field(default=D("0"))
    vat_rate: D = field(default=D("20"))
    subtotal: D = field(default=D("0"))
    overhead_amount: D = field(default=D("0"))
    vat_amount: D = field(default=D("0"))
    total: D = field(default=D("0"))

    def __post_init__(self):
        self.overhead_rate = D(str(self.overhead_rate))
        self.vat_rate = D(str(self.vat_rate))


@dataclass
class ValidationError:
    field: str
    code: str
    message: str


# ---------------------------------------------------------------------------
# Calculation functions
# ---------------------------------------------------------------------------

def _round(value: D) -> D:
    """Round to 2 decimal places using HALF_UP."""
    return value.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def calculate_position(position: EstimatePosition) -> EstimatePosition:
    """quantity * price = sum (exact Decimal arithmetic)."""
    position.sum = _round(position.quantity * position.price)
    return position


def calculate_section(section: EstimateSection) -> EstimateSection:
    """Sum all position sums into section.subtotal."""
    for pos in section.positions:
        calculate_position(pos)
    section.subtotal = _round(sum((p.sum for p in section.positions), D("0")))
    return section


def calculate_estimate(estimate: Estimate) -> Estimate:
    """Full recalculation pipeline:
    positions -> sections -> subtotal -> overhead -> VAT -> total.
    """
    for section in estimate.sections:
        calculate_section(section)

    estimate.subtotal = _round(sum((s.subtotal for s in estimate.sections), D("0")))
    estimate.overhead_amount = _round(estimate.subtotal * estimate.overhead_rate / D("100"))
    vat_base = estimate.subtotal + estimate.overhead_amount
    estimate.vat_amount = _round(vat_base * estimate.vat_rate / D("100"))
    estimate.total = _round(vat_base + estimate.vat_amount)
    return estimate


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_estimate(estimate: Estimate) -> List[ValidationError]:
    """Comprehensive validation — returns list of errors (empty = valid)."""
    errors: List[ValidationError] = []

    # 1. Negative values
    for si, section in enumerate(estimate.sections):
        for pi, pos in enumerate(section.positions):
            prefix = f"sections[{si}].positions[{pi}]"
            if pos.quantity < D("0"):
                errors.append(ValidationError(f"{prefix}.quantity", "NEGATIVE", "Quantity must be >= 0"))
            if pos.price < D("0"):
                errors.append(ValidationError(f"{prefix}.price", "NEGATIVE", "Price must be >= 0"))
            if pos.sum < D("0"):
                errors.append(ValidationError(f"{prefix}.sum", "NEGATIVE", "Sum must be >= 0"))

    # 2. Empty/zero prices
    for si, section in enumerate(estimate.sections):
        for pi, pos in enumerate(section.positions):
            prefix = f"sections[{si}].positions[{pi}]"
            if pos.price == D("0"):
                errors.append(ValidationError(f"{prefix}.price", "ZERO_PRICE", "Price cannot be zero"))

    # 3. Unknown units
    for si, section in enumerate(estimate.sections):
        for pi, pos in enumerate(section.positions):
            prefix = f"sections[{si}].positions[{pi}]"
            if pos.unit not in ALLOWED_UNITS:
                errors.append(ValidationError(f"{prefix}.unit", "INVALID_UNIT",
                    f"Unit '{pos.unit}' not in allowed: {ALLOWED_UNITS}"))

    # 4. Duplicate codes
    seen_codes: Dict[str, List[str]] = {}
    for si, section in enumerate(estimate.sections):
        for pos in section.positions:
            seen_codes.setdefault(pos.code, []).append(f"section {si}")
    for code, locations in seen_codes.items():
        if len(locations) > 1:
            errors.append(ValidationError("code", "DUPLICATE",
                f"Position code '{code}' duplicated in {locations}"))

    # 5. Duplicate names
    seen_names: Dict[str, int] = {}
    for section in estimate.sections:
        for pos in section.positions:
            seen_names[pos.name] = seen_names.get(pos.name, 0) + 1
    for name, count in seen_names.items():
        if count > 1:
            errors.append(ValidationError("name", "DUPLICATE",
                f"Position name '{name}' appears {count} times"))

    # 6. Verify calculated totals
    calc = calculate_estimate(estimate)
    recalc_total = calc.total
    if estimate.total != D("0") and estimate.total != recalc_total:
        errors.append(ValidationError("total", "MISMATCH",
            f"Total mismatch: stored {estimate.total}, calculated {recalc_total}"))

    # 7. Missing required fields
    if not estimate.title.strip():
        errors.append(ValidationError("title", "REQUIRED", "Estimate title is required"))

    return errors


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_decimal(value: D) -> str:
    """Russian locale: 1 234,56"""
    s = f"{value:.2f}"
    int_part, dec_part = s.split(".")
    int_part = int(int_part)
    sign = ""
    if int_part < 0:
        sign = "-"
        int_part = -int_part
    groups = []
    while int_part >= 1000:
        groups.append(f"{int_part % 1000:03d}")
        int_part //= 1000
    groups.append(str(int_part))
    groups.reverse()
    return f"{sign}{' '.join(groups)},{dec_part}"


def format_currency(amount: D, currency: str = "RUB") -> str:
    """Format with currency symbol."""
    formatted = format_decimal(amount)
    symbols = {"RUB": "₽", "USD": "$", "EUR": "€"}
    sym = symbols.get(currency, currency)
    if currency == "USD":
        return f"${formatted.replace(' ', ',').replace(',', 'X', 1).replace('X', '.', 1)[:-3]}"
    return f"{formatted} {sym}"


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def estimate_to_dict(estimate: Estimate) -> dict:
    """Convert estimate to dict/JSON-serializable format."""
    def pos_dict(p: EstimatePosition):
        return {"id": p.id, "code": p.code, "name": p.name, "unit": p.unit,
                "quantity": str(p.quantity), "price": str(p.price),
                "sum": str(p.sum), "source": p.source, "comment": p.comment}
    def sec_dict(s: EstimateSection):
        return {"id": s.id, "title": s.title, "subtotal": str(s.subtotal),
                "positions": [pos_dict(p) for p in s.positions]}
    return {
        "id": estimate.id, "title": estimate.title, "status": estimate.status.value,
        "client": estimate.client, "object_name": estimate.object_name,
        "region": estimate.region, "currency": estimate.currency,
        "overhead_rate": str(estimate.overhead_rate), "vat_rate": str(estimate.vat_rate),
        "subtotal": str(estimate.subtotal), "overhead_amount": str(estimate.overhead_amount),
        "vat_amount": str(estimate.vat_amount), "total": str(estimate.total),
        "sections": [sec_dict(s) for s in estimate.sections],
    }


def export_to_csv(estimate: Estimate) -> str:
    """Export estimate positions to CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Section", "Code", "Name", "Unit", "Quantity", "Price", "Sum", "Source"])
    for section in estimate.sections:
        for pos in section.positions:
            writer.writerow([section.title, pos.code, pos.name, pos.unit,
                           str(pos.quantity), str(pos.price), str(pos.sum), pos.source])
    return output.getvalue()


def export_to_json(estimate: Estimate) -> dict:
    """Export estimate to dict (with strings for Decimals)."""
    return estimate_to_dict(estimate)
