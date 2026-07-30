"""Typed virtual procurement agent for estimate resource rows.

The agent does not invent availability or prices.  It asks the official FGIS
collector first, then the bounded commercial-source collector, and returns a
server-derived report with row-level evidence coverage.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProcurementOutcome:
    draft: dict[str, Any]
    evidence: list[dict[str, Any]]
    report: dict[str, Any]


async def research_estimate_resources(
    draft: dict[str, Any],
    *,
    request_text: str,
    source_backed_required: bool,
    official_enabled: bool,
    commercial_enabled: bool,
) -> ProcurementOutcome:
    working = deepcopy(draft)
    evidence: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []

    if official_enabled:
        try:
            from app.fgiscs_client import FgisCsClient

            working, official = await FgisCsClient().enrich_draft(
                working,
                request_text=request_text,
                source_backed_required=source_backed_required,
            )
            evidence.extend(official)
            attempts.append({"source": "fgis_cs", "status": "completed", "matched": len(official)})
        except Exception as exc:
            attempts.append(
                {
                    "source": "fgis_cs",
                    "status": "failed",
                    "failure_kind": type(exc).__name__,
                }
            )

    if commercial_enabled:
        try:
            from app.commercial_price_research import CommercialPriceResearchClient

            working, commercial = await CommercialPriceResearchClient().enrich_draft(working)
            evidence.extend(commercial)
            attempts.append(
                {"source": "commercial_market", "status": "completed", "matched": len(commercial)}
            )
        except Exception as exc:
            attempts.append(
                {
                    "source": "commercial_market",
                    "status": "failed",
                    "failure_kind": type(exc).__name__,
                }
            )

    requested_codes = [
        str(position.get("code") or "")
        for section in working.get("sections", [])
        if isinstance(section, dict)
        for position in section.get("positions", [])
        if isinstance(position, dict)
    ]
    matched_codes = {
        str(record.get("position_code") or "")
        for record in evidence
        if isinstance(record, dict) and record.get("position_code")
    }
    rows = [
        {
            "position_code": code,
            "availability": "source_confirmed" if code in matched_codes else "not_confirmed",
        }
        for code in requested_codes
    ]
    report = {
        "schema_version": "1.0",
        "requested_rows": len(requested_codes),
        "source_confirmed_rows": len(matched_codes),
        "unconfirmed_rows": max(0, len(requested_codes) - len(matched_codes)),
        "attempts": attempts,
        "rows": rows,
    }
    return ProcurementOutcome(draft=working, evidence=evidence, report=report)
