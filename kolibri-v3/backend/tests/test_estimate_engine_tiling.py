"""Tests for the tiling estimate engine (calculate_tiling_estimate)."""

from __future__ import annotations

import copy
import json
from decimal import Decimal, ROUND_HALF_UP

import pytest

from app.estimate_engine import (
    CommercialTerms,
    EstimateEngineError,
    MissingPriceError,
    PriceQuote,
    PriceSource,
    ProjectCaseRef,
    TilingScope,
    calculate_tiling_estimate,
    canonical_json,
    content_hash,
)


REGION = "Москва"

TILING_PRICE_FIXTURE: dict[str, tuple[str, str]] = {
    "survey": ("m2", "50.00"),
    "surface_cleaning": ("m2", "80.00"),
    "leveling": ("m2", "350.00"),
    "protection": ("m2", "60.00"),
    "primer_application": ("m2", "90.00"),
    "primer_material": ("l", "150.00"),
    "waterproofing_work": ("m2", "450.00"),
    "waterproofing_material": ("kg", "180.00"),
    "floor_tile_work": ("m2", "1200.00"),
    "floor_tile_material": ("m2", "1800.00"),
    "wall_tile_work": ("m2", "1500.00"),
    "wall_tile_material": ("m2", "1800.00"),
    "adhesive_work": ("m2", "120.00"),
    "adhesive_material": ("bag", "450.00"),
    "grouting_work": ("m2", "250.00"),
    "grouting_material": ("bag", "650.00"),
    "sealant_work": ("m", "180.00"),
    "sealant_material": ("ea", "350.00"),
    "delivery": ("trip", "3500.00"),
    "lifting": ("t", "2000.00"),
    "quality_control": ("m2", "80.00"),
    "cleanup": ("m2", "70.00"),
    "waste_removal": ("trip", "5000.00"),
    "consumables": ("set", "4500.00"),
}


def project_case() -> ProjectCaseRef:
    return ProjectCaseRef(
        tenant_id="tenant_test",
        project_id="project_tiling_001",
        case_id="case_tiling_001",
        version=1,
        region=REGION,
    )


def price_source(*, verified: bool = True) -> PriceSource:
    return PriceSource(
        source_id="source_fixture_moscow_2026_07_31",
        source_type="supplier_offer",
        label="Moscow supplier fixture",
        reference="quote-2026-07-31",
        url="https://supplier.example/quotes/2026-07-31",
        region=REGION,
        observed_at="2026-07-31T00:00:00+00:00",
        valid_until="2026-08-31",
        verified=verified,
    )


def quotes(*, omit: set[str] | None = None) -> list[PriceQuote]:
    omitted = omit or set()
    source = price_source()
    return [
        PriceQuote(
            item_code=code,
            unit=unit,
            unit_price=Decimal(price),
            currency="RUB",
            vat_mode="included",
            confidence=Decimal("0.90"),
            source=source,
        )
        for code, (unit, price) in sorted(TILING_PRICE_FIXTURE.items())
        if code not in omitted
    ]


def scope(**overrides: object) -> TilingScope:
    values: dict[str, object] = {
        "floor_area_m2": Decimal("6"),
        "wall_area_m2": Decimal("25.4"),
        "tile_format_mm": 600,
        "work_type": "floor_and_walls",
        "grout_joint_width_mm": Decimal("2"),
        "trowel_notch_mm": Decimal("6"),
        "tile_thickness_mm": Decimal("8"),
        "waste_percent": Decimal("10"),
        "waterproofing_area_m2": Decimal("9"),
        "waterproofing_coats": 2,
        "deduct_area_m2": Decimal("1.6"),
        "adhesive_bag_weight_kg": Decimal("25"),
        "grout_bag_weight_kg": Decimal("5"),
    }
    values.update(overrides)
    return TilingScope(**values)  # type: ignore[arg-type]


def item(result: dict[str, object], code: str) -> dict[str, object]:
    items = result["items"]
    assert isinstance(items, list)
    return next(value for value in items if value["code"] == code)


# ---------------------------------------------------------------------------
# Golden test: bathroom 2×3 m, floor+walls, 600×600 porcelain
# ---------------------------------------------------------------------------


def test_golden_bathroom_floor_and_walls() -> None:
    result = calculate_tiling_estimate(
        project_case=project_case(),
        scope=scope(),
        prices=quotes(),
        terms=CommercialTerms(
            overhead_percent=Decimal("10"),
            profit_percent=Decimal("15"),
            discount_percent=Decimal("5"),
            tax_percent=Decimal("20"),
        ),
        require_complete_prices=True,
    )

    # Floor area = 6 m², wall area = 25.4 m², deduct = 1.6 m²
    # total = 6 + 25.4 - 1.6 = 29.8 m²
    assert item(result, "survey")["normalizedQuantity"] == "29.8"

    # Floor tile with 10% waste: 6 × 1.1 = 6.6
    assert item(result, "floor_tile_material")["normalizedQuantity"] == "6.6"

    # Wall tile with 10% waste: 25.4 × 1.1 = 27.94
    assert item(result, "wall_tile_material")["normalizedQuantity"] == "27.94"

    # Adhesive: norm = 6² / 2 × 1.3 = 23.4 kg/m²
    # mass = 29.8 × 23.4 × 1.1 = 764.652 kg
    # bags = ceil(764.652 / 25) = 31
    assert item(result, "adhesive_material")["normalizedQuantity"] == "31"

    # Grout: norm = ((600+600)/(600×600)) × 2 × 8 × 1.6 = 0.085333 kg/m²
    # mass = 29.8 × 0.085333 × 1.1 ≈ 2.794133 kg
    # bags = ceil(2.794133 / 5) = 1
    assert item(result, "grouting_material")["normalizedQuantity"] == "1"

    # Waterproofing: 9 × 1.0 × 2 × 1.1 = 19.8 kg
    assert item(result, "waterproofing_material")["normalizedQuantity"] == "19.8"

    # Sealant: 12 m work, 3 ea material (constants)
    assert item(result, "sealant_work")["normalizedQuantity"] == "12"
    assert item(result, "sealant_material")["normalizedQuantity"] == "3"

    # Verify totals are computed
    assert Decimal(result["totals"]["directCost"]) > 0
    assert Decimal(result["totals"]["total"]) > 0
    assert result["totals"]["complete"] is True


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_input_and_rules_are_byte_for_byte_reproducible() -> None:
    first = calculate_tiling_estimate(
        project_case=project_case(),
        scope=scope(),
        prices=quotes(),
    )
    second = calculate_tiling_estimate(
        project_case=project_case(),
        scope=scope(),
        prices=list(reversed(quotes())),
    )

    assert canonical_json(first).encode() == canonical_json(second).encode()
    assert first["resultHash"] == second["resultHash"]


# ---------------------------------------------------------------------------
# Work type variants
# ---------------------------------------------------------------------------


def test_floor_only_excludes_wall_items() -> None:
    result = calculate_tiling_estimate(
        project_case=project_case(),
        scope=scope(work_type="floor_only"),
        prices=quotes(),
    )
    codes = {value["code"] for value in result["items"]}
    assert "floor_tile_work" in codes
    assert "wall_tile_work" not in codes
    assert "wall_tile_material" not in codes

    decisions = {
        value["item_code"]: value
        for value in result["technologyCard"]["decisions"]
    }
    assert decisions["floor_tile"]["included"] is True
    assert decisions["wall_tile"]["included"] is False


def test_walls_only_excludes_floor_items() -> None:
    result = calculate_tiling_estimate(
        project_case=project_case(),
        scope=scope(work_type="walls_only"),
        prices=quotes(),
    )
    codes = {value["code"] for value in result["items"]}
    assert "wall_tile_work" in codes
    assert "floor_tile_work" not in codes
    assert "floor_tile_material" not in codes


def test_no_waterproofing_excludes_waterproofing_items() -> None:
    result = calculate_tiling_estimate(
        project_case=project_case(),
        scope=scope(waterproofing_area_m2=Decimal("0")),
        prices=quotes(),
    )
    codes = {value["code"] for value in result["items"]}
    assert "waterproofing_work" not in codes
    assert "waterproofing_material" not in codes


# ---------------------------------------------------------------------------
# Tile format variants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("trowel_notch", "expected_adhesive_norm"),
    [
        # norm = trowel_notch² / 2 × 1.3 kg/m²
        (Decimal("4"), "10.4"),    # 4² / 2 × 1.3 = 10.4
        (Decimal("6"), "23.4"),    # 6² / 2 × 1.3 = 23.4
        (Decimal("8"), "41.6"),    # 8² / 2 × 1.3 = 41.6
        (Decimal("10"), "65"),     # 10² / 2 × 1.3 = 65
    ],
)
def test_adhesive_norm_depends_on_trowel_notch(
    trowel_notch: Decimal,
    expected_adhesive_norm: str,
) -> None:
    """Adhesive norm = trowel_notch² / 2 × 1.3 kg/m²."""
    result = calculate_tiling_estimate(
        project_case=project_case(),
        scope=scope(trowel_notch_mm=trowel_notch),
        prices=quotes(),
    )
    adhesive = item(result, "adhesive_material")
    assert expected_adhesive_norm in str(adhesive["consumptionNorm"])


# ---------------------------------------------------------------------------
# Missing and unverified prices
# ---------------------------------------------------------------------------


def test_missing_price_is_explicit_and_blocks_release_mode() -> None:
    result = calculate_tiling_estimate(
        project_case=project_case(),
        scope=scope(),
        prices=quotes(omit={"adhesive_material"}),
    )
    assert result["totals"]["complete"] is False
    assert result["validation"] == {
        "status": "blocked",
        "missingPriceItemCodes": ["adhesive_material"],
    }
    assert item(result, "adhesive_material")["unitPrice"] is None
    assert item(result, "adhesive_material")["subtotal"] is None

    with pytest.raises(MissingPriceError, match="adhesive_material"):
        calculate_tiling_estimate(
            project_case=project_case(),
            scope=scope(),
            prices=quotes(omit={"adhesive_material"}),
            require_complete_prices=True,
        )


def test_unverified_candidate_price_cannot_pass_release_gate() -> None:
    candidate_source = price_source(verified=False)
    candidate_quotes = quotes()
    candidate_quotes[0] = PriceQuote(
        item_code=candidate_quotes[0].item_code,
        unit=candidate_quotes[0].unit,
        unit_price=candidate_quotes[0].unit_price,
        currency="RUB",
        vat_mode="included",
        confidence=Decimal("0.75"),
        source=candidate_source,
    )
    result = calculate_tiling_estimate(
        project_case=project_case(),
        scope=scope(),
        prices=candidate_quotes,
    )
    assert result["validation"]["status"] == "blocked"
    assert result["validation"]["unverifiedPriceItemCodes"] == [
        candidate_quotes[0].item_code
    ]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_negative_and_invalid_inputs_are_rejected() -> None:
    with pytest.raises(EstimateEngineError, match="floor_area_m2"):
        scope(floor_area_m2=Decimal("-1"))
    with pytest.raises(EstimateEngineError, match="waste_percent"):
        scope(waste_percent=Decimal("101"))
    with pytest.raises(EstimateEngineError, match="waterproofing_coats"):
        scope(waterproofing_coats=0)
    with pytest.raises(EstimateEngineError, match="tile_format_mm"):
        scope(tile_format_mm=999)


def test_duplicate_price_is_rejected() -> None:
    duplicate = quotes()
    duplicate.append(duplicate[0])
    with pytest.raises(EstimateEngineError, match="duplicate price"):
        calculate_tiling_estimate(
            project_case=project_case(),
            scope=scope(),
            prices=duplicate,
        )


def test_price_dimension_mismatch_is_rejected() -> None:
    invalid = [
        (
            PriceQuote(
                item_code=quote.item_code,
                unit="kg",
                unit_price=quote.unit_price,
                currency=quote.currency,
                vat_mode=quote.vat_mode,
                confidence=quote.confidence,
                source=quote.source,
            )
            if quote.item_code == "adhesive_material"
            else quote
        )
        for quote in quotes()
    ]
    with pytest.raises(EstimateEngineError, match="price unit mismatch"):
        calculate_tiling_estimate(
            project_case=project_case(),
            scope=scope(),
            prices=invalid,
        )


# ---------------------------------------------------------------------------
# Result hash integrity
# ---------------------------------------------------------------------------


def test_result_hash_detects_document_divergence() -> None:
    result = calculate_tiling_estimate(
        project_case=project_case(),
        scope=scope(),
        prices=quotes(),
    )
    stored_hash = result["resultHash"]
    unsigned = {key: value for key, value in result.items() if key != "resultHash"}
    assert content_hash(unsigned) == stored_hash

    changed = copy.deepcopy(unsigned)
    changed["items"][0]["subtotal"] = "0.01"
    assert content_hash(changed) != stored_hash


# ---------------------------------------------------------------------------
# Property: no floats, no NaN, totals = sum of line items
# ---------------------------------------------------------------------------


def test_property_arithmetic_and_totals_invariants_without_float() -> None:
    for floor in ("4", "6", "12"):
        for wall in ("18", "25.4", "36"):
            for waste in ("0", "10", "15"):
                result = calculate_tiling_estimate(
                    project_case=project_case(),
                    scope=scope(
                        floor_area_m2=Decimal(floor),
                        wall_area_m2=Decimal(wall),
                        waste_percent=Decimal(waste),
                    ),
                    prices=quotes(),
                    require_complete_prices=True,
                )
                direct = Decimal("0")
                for row in result["items"]:
                    quantity = Decimal(row["normalizedQuantity"])
                    price = Decimal(row["unitPrice"])
                    expected = (quantity * price).quantize(
                        Decimal("0.01"),
                        rounding=ROUND_HALF_UP,
                    )
                    assert Decimal(row["subtotal"]) == expected
                    direct += expected
                assert Decimal(result["totals"]["directCost"]) == direct
                serialized = canonical_json(result)
                assert "NaN" not in serialized
                assert "Infinity" not in serialized
                assert not any(
                    isinstance(value, float)
                    for value in json.loads(serialized)["totals"].values()
                )
