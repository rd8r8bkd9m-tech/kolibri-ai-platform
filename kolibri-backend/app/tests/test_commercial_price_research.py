from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import hashlib

import httpx

from app import ai_provider
from app.commercial_price_research import CommercialPriceResearchClient
from app.estimate_action import build_estimate_action
from app.fgiscs_client import FgisCsClient
from app.project_schemas import PersistedEstimateAction


NOW = datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc)


def _html_response(html: str, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        headers={"content-type": "text/html; charset=utf-8"},
        content=html.encode("utf-8"),
    )


def _draft(*, region: str = "Москва", unit: str = "м³", price: str = "0") -> dict:
    return {
        "title": "Смета",
        "region": region,
        "sections": [
            {
                "title": "Материалы",
                "positions": [
                    {
                        "code": "AI-01-001",
                        "name": "Бетон товарный В25",
                        "unit": unit,
                        "quantity": "10",
                        "price": price,
                    }
                ],
            }
        ],
    }


async def _run_collector(
    draft: dict,
    *,
    html: str,
    url: str = "https://supplier.example/catalog/beton-v25",
    title: str = "Бетон товарный В25",
    snippet: str = "",
):
    queries: list[str] = []

    async def searcher(query: str, limit: int):
        queries.append(query)
        assert limit == 5
        return [{"title": title, "snippet": snippet, "url": url}]

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == url
        return _html_response(html)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as http_client:
        client = CommercialPriceResearchClient(searcher=searcher, client=http_client)
        enriched, evidence = await client.enrich_draft(draft, observed_at=NOW)
    return enriched, evidence, queries


def test_commercial_fallback_extracts_real_https_prices_for_multiple_regions():
    cases = [
        (
            "Москва",
            "7 800",
            "<html><title>Бетон товарный В25 — Москва</title>"
            "<body>Москва. Бетон товарный В25, цена 7 800 руб./м3, с НДС. "
            "Обновлено 15.07.2026.</body></html>",
        ),
        (
            "Самарская область",
            "8 150",
            "<html><title>Бетон В25 Самарская область</title>"
            "<body>Самарская область. Бетон товарный В25: 8 150 руб./м3, без НДС. "
            "Обновлено 15.07.2026.</body></html>",
        ),
    ]

    for region, price_text, html in cases:
        enriched, evidence, queries = asyncio.run(_run_collector(_draft(region=region), html=html))
        position = enriched["sections"][0]["positions"][0]

        assert price_text.replace(" ", "") in position["price"]
        assert len(evidence) == 1
        assert evidence[0]["region"] == region
        assert evidence[0]["project_region"] == region
        assert region in queries[0]
        assert "Татарстан" not in queries[0]


def test_commercial_fallback_rejects_snippet_rank_and_malformed_page_price():
    html = (
        "<html><title>Бетон товарный В25 Москва</title>"
        "<body>Москва. Бетон товарный В25. Результат 1 в каталоге. Цена по запросу.</body></html>"
    )

    enriched, evidence, _queries = asyncio.run(
        _run_collector(
            _draft(region="Москва"),
            html=html,
            snippet="Бетон В25 7 800 руб./м3",
        )
    )

    assert evidence == []
    assert enriched["sections"][0]["positions"][0]["price"] == "0"


def test_commercial_fallback_rejects_price_with_wrong_unit():
    html = (
        "<html><title>Бетон товарный В25 Москва</title>"
        "<body>Москва. Бетон товарный В25 7 800 руб./м3, с НДС. "
        "Обновлено 15.07.2026.</body></html>"
    )

    enriched, evidence, _queries = asyncio.run(
        _run_collector(_draft(region="Москва", unit="м²"), html=html)
    )

    assert evidence == []
    assert enriched["sections"][0]["positions"][0]["price"] == "0"


def test_commercial_fallback_rejects_stale_source_ttl():
    html = (
        "<html><title>Бетон товарный В25 Москва</title>"
        "<body>Москва. Бетон товарный В25 7 800 руб./м3, с НДС. "
        "Обновлено 01.05.2026.</body></html>"
    )

    enriched, evidence, _queries = asyncio.run(_run_collector(_draft(region="Москва"), html=html))

    assert evidence == []
    assert enriched["sections"][0]["positions"][0]["price"] == "0"


def test_commercial_fallback_no_results_keeps_rows_needing_input():
    async def no_results(query: str, limit: int):
        assert "Москва" in query
        return []

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: _html_response(""))) as http_client:
            client = CommercialPriceResearchClient(searcher=no_results, client=http_client)
            return await client.enrich_draft(_draft(region="Москва"), observed_at=NOW)

    enriched, evidence = asyncio.run(scenario())
    action = build_estimate_action(
        "Составь смету на бетон в Москве",
        enriched,
        verified_evidence=evidence,
    )

    assert evidence == []
    assert action["data"]["pricing_status"] == "needs_input"
    assert action["data"]["estimate_status"] == "needs_input"
    assert action["data"]["sections"][0]["positions"][0]["price"] == "0"


def test_commercial_fallback_release_gate_truth_fields_and_binding():
    html = (
        "<html><title>Бетон товарный В25 — Москва, прайс</title>"
        "<body>Москва. Бетон товарный В25 для монолитных работ. "
        "Цена 7 800 руб./м3, с НДС. Обновлено 15.07.2026.</body></html>"
    )
    body_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()

    enriched, evidence, _queries = asyncio.run(_run_collector(_draft(region="Москва"), html=html))
    action = build_estimate_action(
        "Составь смету на бетон в Москве",
        enriched,
        verified_evidence=evidence,
    )
    data = action["data"]
    record = data["price_sources"][0]
    position = data["sections"][0]["positions"][0]

    assert data["pricing_status"] == "source_backed"
    assert data["estimate_status"] == "source_backed"
    assert record["url"] == "https://supplier.example/catalog/beton-v25"
    assert record["source_title"] == "Бетон товарный В25 — Москва, прайс"
    assert record["source_name"] == "supplier.example"
    assert record["retrieved_at"] == "2026-07-15T09:00:00Z"
    assert record["region"] == "Москва"
    assert record["unit"] == "м³"
    assert record["vat_status"] == "included"
    assert Decimal(record["confidence"]) > Decimal("0")
    assert record["ttl_days"] == 30
    assert record["fresh_until"] == "2026-08-14"
    assert record["content_sha256"] == body_hash
    assert len(record["attestation"]) == 64
    assert position["source"] == record["url"]
    assert position["price_evidence"] == [record]

    persisted = PersistedEstimateAction.model_validate(action)
    persisted_record = persisted.data.sections[0].positions[0].price_evidence[0]
    assert persisted_record.source_name == "supplier.example"
    assert persisted_record.fresh_until == "2026-08-14"
    assert persisted_record.ttl_days == 30


def test_commercial_fallback_does_not_override_existing_official_price():
    async def forbidden_search(_query: str, _limit: int):
        raise AssertionError("commercial search must not run for already priced rows")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: _html_response(""))) as http_client:
            client = CommercialPriceResearchClient(searcher=forbidden_search, client=http_client)
            return await client.enrich_draft(
                _draft(region="Москва", price="125.50"),
                observed_at=NOW,
            )

    enriched, evidence = asyncio.run(scenario())

    assert evidence == []
    assert enriched["sections"][0]["positions"][0]["price"] == "125.50"


def test_materialization_uses_requested_region_and_clears_state_when_fallback_has_no_result(
    monkeypatch,
):
    monkeypatch.setenv("KOLIBRI_ESTIMATE_FGIS_ENABLED", "true")
    monkeypatch.setenv("KOLIBRI_ESTIMATE_COMMERCIAL_FALLBACK_ENABLED", "true")

    async def no_fgis(self, draft, **_kwargs):
        return draft, []

    async def no_commercial(self, draft, **_kwargs):
        assert draft["region"] == "Москва"
        return draft, []

    monkeypatch.setattr(FgisCsClient, "enrich_draft", no_fgis)
    monkeypatch.setattr(CommercialPriceResearchClient, "enrich_draft", no_commercial)

    actions = asyncio.run(
        ai_provider._materialize_estimate_actions(
            [{"role": "user", "content": "Составь смету на бетон в Москве"}],
            [
                {
                    "type": "create_estimate",
                    "label": "draft",
                    "data": _draft(region="Татарстан", price="999999"),
                }
            ],
        )
    )

    data = actions[0]["data"]
    assert data["region"] == "Москва"
    assert data["pricing_status"] == "needs_input"
    assert data["estimate_status"] == "needs_input"
    assert data["sections"][0]["positions"][0]["price"] == "0"
