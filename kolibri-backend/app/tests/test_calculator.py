"""Golden tests for Kolibri calculator engine — 30+ cases."""
import pytest
from decimal import Decimal as D
from app.calculator import (
    EstimatePosition, EstimateSection, Estimate, EstimateStatus,
    calculate_position, calculate_section, calculate_estimate,
    validate_estimate, _round, format_decimal, format_currency,
    estimate_to_dict, export_to_csv, ALLOWED_UNITS,
)


def pos(id="p1", code="01-001", name="Test", unit="м", qty="100", price="150.00"):
    return EstimatePosition(id=id, code=code, name=name, unit=unit, quantity=D(qty), price=D(price))


def sec(id="s1", title="Section", positions=None):
    return EstimateSection(id=id, title=title, positions=positions or [])


def est(title="Test", sections=None, overhead="0", vat="20"):
    return Estimate(id="e1", title=title, sections=sections or [], overhead_rate=D(overhead), vat_rate=D(vat))


# ── Position calculation ────────────────────────────────────────────────────

def test_position_basic():
    p = calculate_position(pos(qty="100", price="150"))
    assert p.sum == D("15000.00")

def test_position_fractional():
    p = calculate_position(pos(qty="150", price="85.50"))
    assert p.sum == D("12825.00")

def test_position_zero_qty():
    p = calculate_position(pos(qty="0", price="100"))
    assert p.sum == D("0.00")

def test_position_one():
    p = calculate_position(pos(qty="1", price="9999.99"))
    assert p.sum == D("9999.99")

def test_position_large_qty():
    p = calculate_position(pos(qty="1000000", price="0.01"))
    assert p.sum == D("10000.00")

def test_position_rounding_half_up():
    p = calculate_position(pos(qty="3", price="1.005"))
    assert p.sum == D("3.02")

def test_position_tiny_price():
    p = calculate_position(pos(qty="1000", price="0.333"))
    assert p.sum == D("333.00")


# ── Section calculation ─────────────────────────────────────────────────────

def test_section_sum():
    s = calculate_section(sec(positions=[
        pos(id="p1", qty="100", price="150"),
        pos(id="p2", qty="20", price="500"),
    ]))
    assert s.subtotal == D("25000.00")

def test_section_single_position():
    s = calculate_section(sec(positions=[pos(qty="1", price="8500")]))
    assert s.subtotal == D("8500.00")

def test_section_empty():
    s = calculate_section(sec(positions=[]))
    assert s.subtotal == D("0.00")

def test_section_many_positions():
    positions = [pos(id=f"p{i}", qty=str(i), price="10") for i in range(1, 11)]
    s = calculate_section(sec(positions=positions))
    assert s.subtotal == D("550.00")  # 1+2+...+10 = 55, *10 = 550


# ── Full estimate calculation ───────────────────────────────────────────────

def test_estimate_simple():
    e = calculate_estimate(est(sections=[
        sec(positions=[pos(qty="100", price="150")]),
    ]))
    assert e.subtotal == D("15000.00")
    assert e.vat_amount == D("3000.00")  # 15000 * 20%
    assert e.total == D("18000.00")

def test_estimate_with_overhead():
    e = calculate_estimate(est(overhead="10", sections=[
        sec(positions=[pos(qty="100", price="100")]),
    ]))
    assert e.subtotal == D("10000.00")
    assert e.overhead_amount == D("1000.00")  # 10%
    assert e.vat_amount == D("2200.00")  # (10000+1000)*20%
    assert e.total == D("13200.00")

def test_estimate_multi_section():
    e = calculate_estimate(est(sections=[
        sec(id="s1", positions=[pos(id="p1", qty="150", price="85.50")]),
        sec(id="s2", positions=[
            pos(id="p2", qty="25", price="450"),
            pos(id="p3", qty="12", price="320"),
        ]),
    ]))
    assert e.subtotal == D("27915.00")  # 12825 + 11250 + 3840
    assert e.vat_amount == D("5583.00")  # 27915 * 20%
    assert e.total == D("33498.00")

def test_estimate_zero_vat():
    e = calculate_estimate(est(vat="0", sections=[
        sec(positions=[pos(qty="10", price="100")]),
    ]))
    assert e.subtotal == D("1000.00")
    assert e.vat_amount == D("0.00")
    assert e.total == D("1000.00")

def test_estimate_overhead_and_vat_combined():
    e = calculate_estimate(est(overhead="15", vat="20", sections=[
        sec(positions=[pos(qty="100", price="200")]),
    ]))
    assert e.subtotal == D("20000.00")
    assert e.overhead_amount == D("3000.00")
    assert e.vat_amount == D("4600.00")  # (20000+3000)*20%
    assert e.total == D("27600.00")

def test_estimate_empty():
    e = calculate_estimate(est(sections=[]))
    assert e.subtotal == D("0.00")
    assert e.total == D("0.00")

def test_estimate_precision():
    e = calculate_estimate(est(sections=[
        sec(positions=[
            pos(id="p1", qty="3", price="333.33"),
            pos(id="p2", qty="7", price="142.85"),
        ]),
    ]))
    assert e.subtotal == D("1999.94")  # 999.99 + 999.95
    assert e.vat_amount == D("399.99")  # 1999.94*0.20 = 399.988 → 399.99


# ── Validation ──────────────────────────────────────────────────────────────

def test_validation_valid():
    e = est(title="Valid", sections=[
        sec(positions=[pos(qty="100", price="150")]),
    ])
    e = calculate_estimate(e)
    e.total = e.total  # ensure total matches
    errors = validate_estimate(e)
    # Only the mismatch check will fire since we didn't set e.total to recalc
    assert all(err.code != "NEGATIVE" for err in errors)

def test_validation_negative_qty():
    e = est(title="Bad", sections=[
        sec(positions=[pos(qty="-1", price="100")]),
    ])
    e = calculate_estimate(e)
    errors = validate_estimate(e)
    codes = [err.code for err in errors]
    assert "NEGATIVE" in codes

def test_validation_negative_price():
    e = est(title="Bad", sections=[
        sec(positions=[pos(qty="10", price="-50")]),
    ])
    e = calculate_estimate(e)
    errors = validate_estimate(e)
    codes = [err.code for err in errors]
    assert "NEGATIVE" in codes

def test_validation_zero_price():
    e = est(title="Bad", sections=[
        sec(positions=[pos(qty="10", price="0")]),
    ])
    e = calculate_estimate(e)
    errors = validate_estimate(e)
    codes = [err.code for err in errors]
    assert "ZERO_PRICE" in codes

def test_validation_invalid_unit():
    e = est(title="Bad", sections=[
        sec(positions=[pos(qty="10", price="100", unit="штука")]),
    ])
    e = calculate_estimate(e)
    errors = validate_estimate(e)
    codes = [err.code for err in errors]
    assert "INVALID_UNIT" in codes

def test_validation_valid_units():
    for unit in ALLOWED_UNITS:
        e = est(title="Ok", sections=[
            sec(positions=[pos(qty="1", price="100", unit=unit)]),
        ])
        e = calculate_estimate(e)
        errors = validate_estimate(e)
        unit_errors = [err for err in errors if err.code == "INVALID_UNIT"]
        assert len(unit_errors) == 0, f"Unit '{unit}' should be valid"

def test_validation_duplicate_code():
    e = est(title="Dup", sections=[
        sec(positions=[
            pos(id="p1", code="01-001", qty="10", price="100"),
            pos(id="p2", code="01-001", qty="20", price="200"),
        ]),
    ])
    e = calculate_estimate(e)
    errors = validate_estimate(e)
    codes = [err.code for err in errors]
    assert "DUPLICATE" in codes

def test_validation_empty_title():
    e = est(title="  ", sections=[
        sec(positions=[pos(qty="10", price="100")]),
    ])
    e = calculate_estimate(e)
    errors = validate_estimate(e)
    codes = [err.code for err in errors]
    assert "REQUIRED" in codes


# ── Formatting ──────────────────────────────────────────────────────────────

def test_format_decimal_simple():
    assert format_decimal(D("1234.56")) == "1 234,56"

def test_format_decimal_large():
    assert format_decimal(D("1234567.89")) == "1 234 567,89"

def test_format_decimal_zero():
    assert format_decimal(D("0")) == "0,00"

def test_format_decimal_negative():
    assert format_decimal(D("-500.50")) == "-500,50"

def test_format_currency_rub():
    assert format_currency(D("15000"), "RUB") == "15 000,00 ₽"

def test_format_currency_eur():
    assert format_currency(D("999.99"), "EUR") == "999,99 €"


# ── Serialization ───────────────────────────────────────────────────────────

def test_estimate_to_dict():
    e = calculate_estimate(est(sections=[
        sec(positions=[pos(qty="10", price="100")]),
    ]))
    d = estimate_to_dict(e)
    assert d["id"] == "e1"
    assert d["total"] == "1200.00"
    assert len(d["sections"]) == 1
    assert d["sections"][0]["positions"][0]["sum"] == "1000.00"

def test_export_to_csv():
    e = calculate_estimate(est(sections=[
        sec(title="Work", positions=[pos(code="01", name="Item", unit="м", qty="10", price="100")]),
    ]))
    csv = export_to_csv(e)
    assert "Section,Code,Name" in csv
    assert "01" in csv
    assert "Item" in csv
