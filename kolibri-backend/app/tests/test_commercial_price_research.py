from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import re
import time

import httpx

from app import ai_provider
from app.commercial_price_research import CommercialPriceResearchClient
from app.estimate_action import build_estimate_action
from app.fgiscs_client import FgisCsClient
from app.project_schemas import PersistedEstimateAction


NOW = datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc)
PUBLIC_TEST_IP = "93.184.216.34"


async def _public_resolver(_hostname: str):
    return [PUBLIC_TEST_IP]


def _html_response(html: str, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        headers={"content-type": "text/html; charset=utf-8"},
        content=html.encode("utf-8"),
    )


def _draft(
    *,
    region: str = "Москва",
    unit: str = "м³",
    price: str = "0",
    name: str = "Бетон товарный В25",
) -> dict:
    return {
        "title": "Смета",
        "region": region,
        "sections": [
            {
                "title": "Материалы",
                "positions": [
                    {
                        "code": "AI-01-001",
                        "name": name,
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
        client = CommercialPriceResearchClient(
            searcher=searcher,
            client=http_client,
            dns_resolver=_public_resolver,
        )
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


def test_search_queries_are_normalized_and_follow_exact_subject_federal_order():
    queries: list[str] = []

    async def searcher(query: str, limit: int):
        queries.append(query)
        assert limit == 5
        return []

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: _html_response(""))) as http_client:
            client = CommercialPriceResearchClient(
                searcher=searcher,
                client=http_client,
                dns_resolver=_public_resolver,
            )
            return await client.enrich_draft(
                _draft(
                    region="Лениногорск, Татарстан",
                    unit="пог.м",
                    name="  Профилированный лист С8!!! для забора; профлист С8  ",
                ),
                observed_at=NOW,
            )

    enriched, evidence = asyncio.run(scenario())

    assert evidence == []
    assert enriched["sections"][0]["positions"][0]["price"] == "0"
    assert len(queries) == 3
    assert queries[0].endswith("Лениногорск Татарстан")
    assert "профнастил с8" in queries[0]
    assert queries[1].endswith("поставщик Татарстан")
    assert "доставка по России Лениногорск Татарстан" in queries[2]
    assert "!!!" not in " ".join(queries)


def test_verbose_provider_rows_match_real_visible_supplier_labels():
    cases = [
        (
            "Профилированный лист стеновой оцинкованный или с полимерным "
            "покрытием для забора высотой 2 м",
            "м²",
            "312",
            "<html><title>Профнастил С8 — Казань</title><body>"
            "Казань. Профнастил С8 оцинкованный 0,45 мм: "
            "312 руб./м2, с НДС. Обновлено 15.07.2026.</body></html>",
        ),
        (
            "Труба стальная профильная для столбов забора",
            "м",
            "331",
            "<html><title>Труба профильная 60x60 — Казань</title><body>"
            "Казань. Труба стальная профильная 60x60: "
            "331 руб./м, с НДС. Обновлено 15.07.2026.</body></html>",
        ),
    ]

    for name, unit, expected_price, html in cases:
        enriched, evidence, _queries = asyncio.run(
            _run_collector(
                _draft(
                    region="Лениногорск, Республика Татарстан",
                    unit=unit,
                    name=name,
                ),
                html=html,
                title="Каталог поставщика — Татарстан",
            )
        )

        position = enriched["sections"][0]["positions"][0]
        assert position["price"] == expected_price
        assert len(evidence) == 1
        assert evidence[0]["region"] == "Татарстан"
        assert evidence[0]["project_region"] == "Лениногорск, Республика Татарстан"
        assert evidence[0]["unit"] == unit
        assert evidence[0]["unit_price"] == expected_price
        assert evidence[0]["content_sha256"] == hashlib.sha256(html.encode("utf-8")).hexdigest()
        assert evidence[0]["price_date"] == "2026-07-15"
        assert evidence[0]["vat_status"] == "included"


def test_known_city_subject_alias_never_crosses_project_region():
    html = (
        "<html><title>Профнастил С8 — Казань</title><body>"
        "Казань. Профнастил С8 312 руб./м2, с НДС. "
        "Обновлено 15.07.2026.</body></html>"
    )

    enriched, evidence, _queries = asyncio.run(
        _run_collector(
            _draft(region="Самарская область", unit="м²", name="Профнастил С8"),
            html=html,
        )
    )

    assert evidence == []
    assert enriched["sections"][0]["positions"][0]["price"] == "0"


def test_semantic_resource_match_fails_closed_for_related_but_wrong_prices():
    cases = [
        (
            "Профнастил С8",
            "м²",
            "<html><title>Профнастил С21</title><body>Татарстан. "
            "Профнастил С21 450 руб./м2, с НДС. Обновлено 15.07.2026.</body></html>",
        ),
        (
            "Труба профильная 60x60",
            "м",
            "<html><title>Труба профильная 40x20</title><body>Татарстан. "
            "Труба профильная 40x20 331 руб./м, с НДС. Обновлено 15.07.2026.</body></html>",
        ),
        (
            "Профнастил",
            "м²",
            "<html><title>Монтаж профнастила</title><body>Татарстан. "
            "Монтаж профнастила 312 руб./м2, с НДС. Обновлено 15.07.2026.</body></html>",
        ),
        (
            "Труба стальная профильная для столбов забора",
            "м",
            "<html><title>Труба медная круглая</title><body>Татарстан. "
            "Труба медная круглая 331 руб./м, с НДС. Обновлено 15.07.2026.</body></html>",
        ),
    ]

    for name, unit, html in cases:
        enriched, evidence, _queries = asyncio.run(
            _run_collector(
                _draft(region="Лениногорск, Татарстан", unit=unit, name=name),
                html=html,
            )
        )
        assert evidence == []
        assert enriched["sections"][0]["positions"][0]["price"] == "0"


def test_schema_org_product_offer_is_bound_to_requested_region_unit_and_fetched_bytes():
    html = """
    <html><head><title>Каталог строительного поставщика</title>
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Product",
      "name": "Профнастил С8 для забора",
      "areaServed": {"@type": "AdministrativeArea", "name": "Екатеринбург"},
      "dateModified": "2026-07-15",
      "offers": {
        "@type": "Offer",
        "price": "785.40",
        "priceCurrency": "RUB",
        "priceValidUntil": "2026-08-10",
        "valueAddedTaxIncluded": true,
        "priceSpecification": {
          "@type": "UnitPriceSpecification",
          "price": "785.40",
          "priceCurrency": "RUB",
          "unitCode": "MTK"
        }
      }
    }
    </script></head><body>Доставка заказов в Екатеринбурге.</body></html>
    """
    url = "https://supplier.example/catalog/profnastil-c8"
    enriched, evidence, queries = asyncio.run(
        _run_collector(
            _draft(
                region="Екатеринбург",
                unit="м²",
                name="Профнастил С8 для забора",
            ),
            html=html,
            url=url,
            title="Профнастил С8 — Екатеринбург",
        )
    )

    record = evidence[0]
    assert enriched["sections"][0]["positions"][0]["price"] == "785.4"
    assert record["url"] == url
    assert record["region"] == "Екатеринбург"
    assert record["project_region"] == "Екатеринбург"
    assert record["unit"] == "м²"
    assert record["vat_status"] == "included"
    assert record["price_date"] == "2026-07-15"
    assert record["fresh_until"] == "2026-08-10"
    assert record["retrieved_at"] == "2026-07-15T09:00:00Z"
    assert record["content_sha256"] == hashlib.sha256(html.encode("utf-8")).hexdigest()
    assert "Schema.org Product/Offer" in record["quote"]
    assert "Екатеринбург" in queries[0]


def test_schema_org_nationwide_offer_is_honest_federal_evidence_with_lower_confidence():
    html = """
    <html><head><title>Столб профильный 60x60 3 м</title>
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Product",
      "name": "Столб профильный 60x60 3 м",
      "offers": {
        "@type": "Offer",
        "price": 2140,
        "priceCurrency": "RUB",
        "unitText": "шт",
        "valueAddedTaxIncluded": false,
        "areaServed": "Россия"
      }
    }
    </script></head><body>Доставка по всей России. Актуальная цена.</body></html>
    """
    enriched, evidence, _queries = asyncio.run(
        _run_collector(
            _draft(
                region="Владивосток, Приморский край",
                unit="шт",
                name="Столб профильный 60x60 3 м",
            ),
            html=html,
            title="Столб профильный 60x60 3 м",
        )
    )

    record = evidence[0]
    assert enriched["sections"][0]["positions"][0]["price"] == "2140"
    assert record["region"] == "Россия"
    assert record["project_region"] == "Владивосток, Приморский край"
    assert record["vat_status"] == "excluded"
    assert Decimal(record["confidence"]) <= Decimal("0.78")

    action = build_estimate_action(
        "Составь смету на забор во Владивостоке",
        enriched,
        verified_evidence=evidence,
    )
    assert action["data"]["pricing_status"] == "source_backed"
    assert action["data"]["evidence_issues"][0]["code"] == "federal_price_scope"


def test_local_result_wins_over_higher_ranked_nationwide_result():
    federal_url = "https://federal.example/profnastil"
    local_url = "https://local.example/profnastil"

    async def searcher(_query: str, _limit: int):
        return [
            {"title": "Профнастил С8 Россия", "url": federal_url},
            {"title": "Профнастил С8 Татарстан", "url": local_url},
        ]

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == federal_url:
            return _html_response(
                "<html><title>Профнастил С8</title><body>Доставка по всей России. "
                "Профнастил С8 700 руб./м2, с НДС. Обновлено 15.07.2026.</body></html>"
            )
        return _html_response(
            "<html><title>Профнастил С8 Татарстан</title><body>Татарстан. "
            "Профнастил С8 745 руб./м2, с НДС. Обновлено 15.07.2026.</body></html>"
        )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = CommercialPriceResearchClient(
                searcher=searcher,
                client=http_client,
                dns_resolver=_public_resolver,
            )
            return await client.enrich_draft(
                _draft(
                    region="Лениногорск, Татарстан",
                    unit="м²",
                    name="Профнастил С8",
                ),
                observed_at=NOW,
            )

    enriched, evidence = asyncio.run(scenario())

    assert enriched["sections"][0]["positions"][0]["price"] == "745"
    assert evidence[0]["url"] == local_url
    assert evidence[0]["region"] == "Татарстан"


def test_commercial_fallback_rejects_moscow_oblast_for_moscow_city():
    html = (
        "<html><title>Бетон товарный В25 — Московская область</title>"
        "<body>Московская область. Бетон товарный В25 7 800 руб./м3, с НДС. "
        "Обновлено 15.07.2026.</body></html>"
    )

    enriched, evidence, _queries = asyncio.run(_run_collector(_draft(region="Москва"), html=html))

    assert evidence == []
    assert enriched["sections"][0]["positions"][0]["price"] == "0"


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


def test_commercial_fallback_rejects_private_literal_https_url():
    async def searcher(_query: str, _limit: int):
        return [{"title": "Бетон товарный В25", "url": "https://127.0.0.1/catalog"}]

    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("private literal URL must not be fetched")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = CommercialPriceResearchClient(
                searcher=searcher,
                client=http_client,
                dns_resolver=_public_resolver,
            )
            return await client.enrich_draft(_draft(region="Москва"), observed_at=NOW)

    enriched, evidence = asyncio.run(scenario())

    assert evidence == []
    assert enriched["sections"][0]["positions"][0]["price"] == "0"


def test_commercial_fallback_rejects_dns_resolution_to_private_address():
    async def searcher(_query: str, _limit: int):
        return [{"title": "Бетон товарный В25", "url": "https://supplier.example/catalog"}]

    async def private_resolver(hostname: str):
        assert hostname == "supplier.example"
        return ["10.10.10.10"]

    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("host resolving to private address must not be fetched")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = CommercialPriceResearchClient(
                searcher=searcher,
                client=http_client,
                dns_resolver=private_resolver,
            )
            return await client.enrich_draft(_draft(region="Москва"), observed_at=NOW)

    enriched, evidence = asyncio.run(scenario())

    assert evidence == []
    assert enriched["sections"][0]["positions"][0]["price"] == "0"


def test_commercial_fallback_revalidates_redirect_target_before_following():
    public_url = "https://supplier.example/catalog"
    requests: list[str] = []

    async def searcher(_query: str, _limit: int):
        return [{"title": "Бетон товарный В25", "url": public_url}]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url) == public_url:
            return httpx.Response(
                302,
                headers={"location": "https://127.0.0.1/private"},
            )
        raise AssertionError("private redirect target must not be fetched")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as http_client:
            client = CommercialPriceResearchClient(
                searcher=searcher,
                client=http_client,
                dns_resolver=_public_resolver,
            )
            return await client.enrich_draft(_draft(region="Москва"), observed_at=NOW)

    enriched, evidence = asyncio.run(scenario())

    assert requests == [public_url]
    assert evidence == []
    assert enriched["sections"][0]["positions"][0]["price"] == "0"


def test_commercial_fallback_rejects_unrelated_price_elsewhere_on_page():
    filler = " Подробное техническое описание." * 12
    html = (
        "<html><title>Бетон товарный В25 Москва</title><body>"
        f"Москва. Бетон товарный В25 поставляется по запросу.{filler} "
        "Песок карьерный: 7 800 руб./м3, с НДС. "
        "Обновлено 15.07.2026.</body></html>"
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
            client = CommercialPriceResearchClient(
                searcher=no_results,
                client=http_client,
                dns_resolver=_public_resolver,
            )
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


def test_commercial_fallback_bounds_row_concurrency_and_keeps_output_order():
    row_count = 8
    draft = {
        "title": "Смета",
        "region": "Москва",
        "sections": [
            {
                "title": "Материалы",
                "positions": [
                    {
                        "code": f"AI-{index:02}",
                        "name": f"Бетон товарный В25 позиция {index}",
                        "unit": "м³",
                        "quantity": "1",
                        "price": "0",
                    }
                    for index in range(row_count)
                ],
            }
        ],
    }
    active = 0
    max_active = 0

    async def searcher(query: str, limit: int):
        nonlocal active, max_active
        assert limit == 5
        match = re.search(r"позиция\s+(\d+)", query)
        assert match is not None
        index = int(match.group(1))
        active += 1
        max_active = max(max_active, active)
        try:
            await asyncio.sleep((row_count - index) * 0.01)
        finally:
            active -= 1
        return [{
            "title": f"Бетон товарный В25 позиция {index}",
            "url": f"https://supplier.example/catalog/{index}",
        }]

    def handler(request: httpx.Request) -> httpx.Response:
        index = int(str(request.url).rstrip("/").rsplit("/", 1)[1])
        price = 7000 + index
        html = (
            f"<html><title>Бетон товарный В25 позиция {index} Москва</title>"
            f"<body>Москва. Бетон товарный В25 позиция {index}: "
            f"{price} руб./м3, с НДС. Обновлено 15.07.2026.</body></html>"
        )
        return _html_response(html)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = CommercialPriceResearchClient(
                searcher=searcher,
                client=http_client,
                dns_resolver=_public_resolver,
                max_concurrent_rows=99,
            )
            return await client.enrich_draft(draft, observed_at=NOW)

    enriched, evidence = asyncio.run(scenario())

    assert max_active == 6
    assert [record["position_code"] for record in evidence] == [
        f"AI-{index:02}" for index in range(row_count)
    ]
    assert [
        position["price"]
        for position in enriched["sections"][0]["positions"]
    ] == [str(7000 + index) for index in range(row_count)]


def test_commercial_fallback_budget_expiry_cancels_remaining_work_without_result():
    started = 0
    cancelled = 0

    async def slow_searcher(_query: str, _limit: int):
        nonlocal started, cancelled
        started += 1
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            cancelled += 1
            raise
        return [{"title": "Бетон товарный В25", "url": "https://supplier.example/catalog"}]

    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("budget expiry must cancel before fetch")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = CommercialPriceResearchClient(
                searcher=slow_searcher,
                client=http_client,
                dns_resolver=_public_resolver,
                research_budget_seconds=0.01,
            )
            return await client.enrich_draft(_draft(region="Москва"), observed_at=NOW)

    started_at = time.perf_counter()
    enriched, evidence = asyncio.run(scenario())
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.5
    assert started == 1
    assert cancelled == 1
    assert evidence == []
    assert enriched["sections"][0]["positions"][0]["price"] == "0"


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
            client = CommercialPriceResearchClient(
                searcher=forbidden_search,
                client=http_client,
                dns_resolver=_public_resolver,
            )
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
    assert data["pricing_status"] == "preliminary"
    assert data["estimate_status"] == "preliminary"
    assert Decimal(data["sections"][0]["positions"][0]["price"]) > 0
