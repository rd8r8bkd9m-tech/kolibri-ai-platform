from __future__ import annotations

import copy
import json
from decimal import Decimal, ROUND_HALF_UP

import pytest

from app.estimate_engine import (
    CommercialTerms,
    EstimateEngineError,
    FormulaError,
    MissingPriceError,
    PlasteringScope,
    PriceQuote,
    PriceSource,
    ProjectCaseRef,
    Quantity,
    calculate_plastering_estimate,
    canonical_json,
    content_hash,
    evaluate_formula,
)


REGION = "Республика Татарстан"
PRICE_FIXTURE: dict[str, tuple[str, str]] = {
    "survey": ("m2", "35.00"),
    "surface_cleaning": ("m2", "90.00"),
    "protection": ("m2", "48.00"),
    "primer_application": ("m2", "75.00"),
    "primer_material": ("l", "120.00"),
    "beacon_installation": ("m2", "160.00"),
    "beacon_profile": ("ea", "85.00"),
    "corner_installation": ("m", "95.00"),
    "corner_profile": ("ea", "95.00"),
    "mesh_installation": ("m2", "220.00"),
    "reinforcing_mesh": ("m2", "75.00"),
    "plaster_application": ("m2", "520.00"),
    "plaster_mix": ("bag", "470.00"),
    "water": ("m3", "180.00"),
    "electricity": ("kWh", "8.50"),
    "plaster_machine": ("shift", "8500.00"),
    "delivery": ("trip", "3500.00"),
    "lifting": ("t", "1800.00"),
    "slopes": ("m2", "1450.00"),
    "smoothing": ("m2", "140.00"),
    "quality_control": ("m2", "65.00"),
    "cleanup": ("m2", "65.00"),
    "waste_removal": ("trip", "6500.00"),
    "consumables": ("set", "8500.00"),
}


def project_case() -> ProjectCaseRef:
    return ProjectCaseRef(
        tenant_id="tenant_test",
        project_id="project_plaster_358",
        case_id="case_plaster_358",
        version=1,
        region=REGION,
    )


def scope(**overrides: object) -> PlasteringScope:
    values: dict[str, object] = {
        "wall_area_m2": Decimal("358"),
        "average_thickness_mm": Decimal("15"),
        "material": "gypsum",
        "application_method": "mechanized",
        "waste_percent": Decimal("10"),
        "protection_area_m2": Decimal("80"),
        "wall_height_m": Decimal("3"),
        "beacon_spacing_m": Decimal("1.5"),
        "corner_length_m": Decimal("60"),
        "mesh_area_percent": Decimal("10"),
        "slopes_area_m2": Decimal("24"),
        "plaster_bag_weight_kg": Decimal("30"),
        "primer_passes": 1,
        "waste_removal_trips": Decimal("1"),
    }
    values.update(overrides)
    return PlasteringScope(**values)  # type: ignore[arg-type]


def price_source(*, verified: bool = True) -> PriceSource:
    return PriceSource(
        source_id="source_fixture_tatarstan_2026_07_29",
        source_type="supplier_offer",
        label="Golden supplier fixture",
        reference="quote-2026-07-29",
        url="https://supplier.example/quotes/2026-07-29",
        region=REGION,
        observed_at="2026-07-29T00:00:00+00:00",
        valid_until="2026-08-29",
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
            confidence=Decimal("0.95"),
            source=source,
        )
        for code, (unit, price) in sorted(PRICE_FIXTURE.items())
        if code not in omitted
    ]


def item(result: dict[str, object], code: str) -> dict[str, object]:
    items = result["items"]
    assert isinstance(items, list)
    return next(value for value in items if value["code"] == code)


def test_golden_mechanized_gypsum_358_m2_15_mm() -> None:
    result = calculate_plastering_estimate(
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

    assert item(result, "plaster_mix")["normalizedQuantity"] == "168"
    assert item(result, "primer_material")["normalizedQuantity"] == "59.07"
    assert item(result, "beacon_profile")["normalizedQuantity"] == "88"
    assert item(result, "corner_profile")["normalizedQuantity"] == "22"
    assert item(result, "reinforcing_mesh")["normalizedQuantity"] == "39.38"
    assert item(result, "water")["normalizedQuantity"] == "2.761523"
    assert item(result, "electricity")["normalizedQuantity"] == "19.69"
    assert item(result, "plaster_machine")["normalizedQuantity"] == "2"
    assert item(result, "delivery")["normalizedQuantity"] == "4"
    assert item(result, "lifting")["normalizedQuantity"] == "5.02095"
    assert result["totals"] == {
        "directCost": "618190.05",
        "overhead": "61819.01",
        "profit": "102001.36",
        "discount": "39100.52",
        "tax": "148581.98",
        "total": "891491.88",
        "complete": True,
    }
    assert result["validation"] == {
        "status": "passed",
        "missingPriceItemCodes": [],
    }


def test_same_input_and_rules_are_byte_for_byte_reproducible() -> None:
    first = calculate_plastering_estimate(
        project_case=project_case(),
        scope=scope(),
        prices=quotes(),
    )
    second = calculate_plastering_estimate(
        project_case=project_case(),
        scope=scope(),
        prices=list(reversed(quotes())),
    )

    assert canonical_json(first).encode() == canonical_json(second).encode()
    assert first["resultHash"] == second["resultHash"]


@pytest.mark.parametrize(
    ("material", "thickness", "bag_weight", "expected_bags"),
    [
        ("gypsum", "10", "30", "112"),
        ("gypsum", "15", "30", "168"),
        ("gypsum", "20", "30", "224"),
        ("cement", "15", "25", "402"),
    ],
)
def test_bag_rounding_for_material_and_thickness(
    material: str,
    thickness: str,
    bag_weight: str,
    expected_bags: str,
) -> None:
    result = calculate_plastering_estimate(
        project_case=project_case(),
        scope=scope(
            material=material,
            average_thickness_mm=Decimal(thickness),
            plaster_bag_weight_kg=Decimal(bag_weight),
        ),
        prices=quotes(),
    )
    assert item(result, "plaster_mix")["normalizedQuantity"] == expected_bags


def test_conditional_slopes_machine_and_mesh_are_explained() -> None:
    result = calculate_plastering_estimate(
        project_case=project_case(),
        scope=scope(
            application_method="manual",
            slopes_area_m2=Decimal("0"),
            mesh_area_percent=Decimal("0"),
        ),
        prices=quotes(),
    )
    codes = {value["code"] for value in result["items"]}
    assert "slopes" not in codes
    assert "plaster_machine" not in codes
    assert "water" not in codes
    assert "electricity" not in codes
    assert "reinforcing_mesh" not in codes
    decisions = {
        value["item_code"]: value
        for value in result["technologyCard"]["decisions"]
    }
    assert decisions["slopes"]["included"] is False
    assert decisions["plaster_machine"]["included"] is False
    assert decisions["reinforcing_mesh"]["included"] is False


def test_missing_price_is_explicit_and_blocks_release_mode() -> None:
    result = calculate_plastering_estimate(
        project_case=project_case(),
        scope=scope(),
        prices=quotes(omit={"plaster_mix"}),
    )
    assert result["totals"]["complete"] is False
    assert result["validation"] == {
        "status": "blocked",
        "missingPriceItemCodes": ["plaster_mix"],
    }
    assert item(result, "plaster_mix")["unitPrice"] is None
    assert item(result, "plaster_mix")["subtotal"] is None

    with pytest.raises(MissingPriceError, match="plaster_mix"):
        calculate_plastering_estimate(
            project_case=project_case(),
            scope=scope(),
            prices=quotes(omit={"plaster_mix"}),
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
    result = calculate_plastering_estimate(
        project_case=project_case(),
        scope=scope(),
        prices=candidate_quotes,
    )
    assert result["validation"]["status"] == "blocked"
    assert result["validation"]["unverifiedPriceItemCodes"] == [
        candidate_quotes[0].item_code
    ]

    with pytest.raises(EstimateEngineError, match="unverified prices"):
        calculate_plastering_estimate(
            project_case=project_case(),
            scope=scope(),
            prices=candidate_quotes,
            require_complete_prices=True,
        )


def test_ai_candidate_price_cannot_participate_in_arithmetic() -> None:
    source = PriceSource(
        source_id="source_model_candidate_2026_07_29",
        source_type="ai_candidate",
        label="MiMo preliminary candidate",
        reference="run_model_candidate_2026_07_29",
        url="document://chat-run/run_model_candidate_2026_07_29",
        region=REGION,
        observed_at="2026-07-29T00:00:00+00:00",
        valid_until=None,
        verified=False,
    )
    dangerous_candidate = PriceQuote(
        item_code="survey",
        unit="m2",
        unit_price=Decimal("15000.00"),
        currency="RUB",
        vat_mode="unknown",
        confidence=Decimal("0.35"),
        source=source,
    )

    with pytest.raises(
        EstimateEngineError,
        match="AI candidate prices cannot participate",
    ):
        calculate_plastering_estimate(
            project_case=project_case(),
            scope=scope(),
            prices=[dangerous_candidate],
        )


def test_duplicate_price_is_rejected() -> None:
    duplicate = quotes()
    duplicate.append(duplicate[0])
    with pytest.raises(EstimateEngineError, match="duplicate price"):
        calculate_plastering_estimate(
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
            if quote.item_code == "plaster_mix"
            else quote
        )
        for quote in quotes()
    ]
    with pytest.raises(EstimateEngineError, match="price unit mismatch"):
        calculate_plastering_estimate(
            project_case=project_case(),
            scope=scope(),
            prices=invalid,
        )


def test_negative_and_invalid_percent_inputs_are_rejected() -> None:
    with pytest.raises(EstimateEngineError, match="wall_area_m2"):
        scope(wall_area_m2=Decimal("-1"))
    with pytest.raises(EstimateEngineError, match="waste_percent"):
        scope(waste_percent=Decimal("101"))
    with pytest.raises(EstimateEngineError, match="primer_passes"):
        scope(primer_passes=0)


def test_formula_allowlist_dimension_and_zero_division() -> None:
    variables = {"area": Quantity.of("358", "m2")}
    with pytest.raises(FormulaError, match="not allowlisted"):
        evaluate_formula(
            {"op": "eval", "code": "__import__('os')"},
            variables,
            target_unit="m2",
        )
    with pytest.raises(FormulaError, match="dimension mismatch"):
        evaluate_formula(
            {"op": "variable", "name": "area"},
            variables,
            target_unit="kg",
        )
    with pytest.raises(FormulaError, match="division by zero"):
        evaluate_formula(
            {
                "op": "divide",
                "numerator": {"op": "variable", "name": "area"},
                "denominator": {
                    "op": "constant",
                    "value": "0",
                    "unit": "m2",
                },
            },
            variables,
            target_unit="1",
        )


def test_result_hash_detects_document_divergence() -> None:
    result = calculate_plastering_estimate(
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


def test_property_arithmetic_and_totals_invariants_without_float() -> None:
    for area in ("1", "17.25", "358", "9999.99"):
        for thickness in ("5", "10", "15", "37.5"):
            for waste in ("0", "10", "23.75"):
                result = calculate_plastering_estimate(
                    project_case=project_case(),
                    scope=scope(
                        wall_area_m2=Decimal(area),
                        average_thickness_mm=Decimal(thickness),
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
