"""Versioned preliminary prices used before a verified catalog is available.

The snapshot is server-owned and immutable.  Model output may describe scope,
but it cannot choose prices that participate in Estimate Engine arithmetic.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping


PLASTERING_REFERENCE_PRICE_SNAPSHOT_VERSION = (
    "plastering-reference/2026-07-29.1"
)
PLASTERING_REFERENCE_PRICE_OBSERVED_AT = "2026-07-29T00:00:00+00:00"
PLASTERING_REFERENCE_PRICE_VALID_UNTIL = "2026-08-29"

# Preliminary regional benchmark in RUB per canonical unit.  These values are
# intentionally versioned and unverified: they make draft calculations
# reproducible but cannot pass the release gate until replaced by approved
# catalog or supplier evidence.
PLASTERING_REFERENCE_PRICES: dict[str, tuple[str, str]] = {
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


def plastering_reference_price_quotes(
    *,
    active_units: Mapping[str, str],
    region: str,
) -> list[dict[str, object]]:
    """Return a stable price snapshot for the active deterministic line plan."""

    quotes: list[dict[str, object]] = []
    for item_code in sorted(active_units):
        configured = PLASTERING_REFERENCE_PRICES.get(item_code)
        if configured is None:
            continue
        configured_unit, unit_price = configured
        if active_units[item_code] != configured_unit:
            raise ValueError(
                f"reference price unit mismatch for {item_code}: "
                f"{configured_unit} != {active_units[item_code]}"
            )
        quotes.append(
            {
                "itemCode": item_code,
                "unit": configured_unit,
                "unitPrice": unit_price,
                "currency": "RUB",
                "vatMode": "included",
                "confidence": "0.50",
                "source": {
                    "sourceId": "source_plastering_reference_2026_07_29_1",
                    "sourceType": "regional_catalog",
                    "label": (
                        "Kolibri · предварительный региональный ориентир"
                    ),
                    "reference": PLASTERING_REFERENCE_PRICE_SNAPSHOT_VERSION,
                    "url": (
                        "document://regional-price-snapshot/"
                        "plastering-reference-2026-07-29-1"
                    ),
                    "region": region,
                    "observedAt": PLASTERING_REFERENCE_PRICE_OBSERVED_AT,
                    "validUntil": PLASTERING_REFERENCE_PRICE_VALID_UNTIL,
                    "verified": False,
                },
            }
        )
    return quotes


def plastering_reference_price_assumption() -> str:
    return (
        "Черновые цены рассчитаны по фиксированному ориентиру Kolibri "
        f"{PLASTERING_REFERENCE_PRICE_SNAPSHOT_VERSION}; перед выпуском их "
        "нужно заменить подтверждёнными предложениями для региона."
    )


def verify_plastering_model_price_candidates(
    candidate_prices: Mapping[str, str],
) -> list[dict[str, str]]:
    """Compare model research candidates with an independent benchmark.

    A candidate remains evidence only. Passing the reference-band check does
    not turn it into a verified supplier price and does not let it replace the
    server-owned calculation snapshot.
    """

    checks: list[dict[str, str]] = []
    for item_code in sorted(candidate_prices):
        configured = PLASTERING_REFERENCE_PRICES.get(item_code)
        if configured is None:
            continue
        _unit, reference_text = configured
        candidate = Decimal(candidate_prices[item_code])
        reference = Decimal(reference_text)
        deviation = (
            abs(candidate - reference) / reference * Decimal("100")
            if reference
            else Decimal("0")
        )
        checks.append(
            {
                "itemCode": item_code,
                "candidateUnitPrice": format(candidate, "f"),
                "referenceUnitPrice": format(reference, "f"),
                "deviationPercent": format(
                    deviation.quantize(
                        Decimal("0.01"),
                        rounding=ROUND_HALF_UP,
                    ),
                    "f",
                ),
                "verdict": (
                    "within_reference_range"
                    if deviation <= Decimal("30")
                    else "outlier"
                ),
                "publicationStatus": "candidate_only",
            }
        )
    return checks
