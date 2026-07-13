from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

MONEY = Decimal("0.01")


def D(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0").replace(",", "."))
    except Exception:
        return Decimal("0")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def calculate(estimate: dict[str, Any]) -> dict[str, Any]:
    lines: list[dict[str, Any]] = []
    subtotal = Decimal("0")
    sources = {source["id"]: source for source in estimate.get("sources", [])}
    all_verified = bool(estimate.get("items"))
    for item in estimate.get("items", []):
        quantity = D(item.get("quantity"))
        unit_price = D(item.get("unit_price"))
        coefficient = D(item.get("coefficient") or "1")
        line_total = money(quantity * unit_price * coefficient)
        subtotal += line_total
        source = sources.get(item.get("source_id"))
        verified = bool(source and source.get("verification_status") == "verified" and unit_price > 0)
        all_verified = all_verified and verified
        lines.append({**item, "line_total": str(line_total), "source": source, "verified": verified})

    overhead = money(subtotal * D(estimate.get("overhead_pct")) / Decimal("100"))
    margin_base = subtotal + overhead
    margin = money(margin_base * D(estimate.get("margin_pct")) / Decimal("100"))
    discount = money((margin_base + margin) * D(estimate.get("discount_pct")) / Decimal("100"))
    before_tax = subtotal + overhead + margin - discount
    tax = money(before_tax * D(estimate.get("tax_pct")) / Decimal("100"))
    total = money(before_tax + tax)
    status = "needs_input" if not lines else ("verified" if all_verified else "preliminary")
    return {
        **estimate,
        "items": lines,
        "subtotal": str(money(subtotal)),
        "overhead": str(overhead),
        "margin": str(margin),
        "discount": str(discount),
        "tax": str(tax),
        "total": str(total),
        "status": status,
    }
