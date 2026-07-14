import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json

import httpx
from app.fgiscs_client import FgisCsClient, FgisResource


def _json_response(payload, status_code=200):
    return httpx.Response(
        status_code,
        headers={"content-type": "application/json; charset=utf-8"},
        content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )


def test_enrich_draft_does_not_backfill_previous_period_when_latest_is_empty():
    requests: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params.multi_items())
        requests.append((request.url.path, params))
        if request.url.path.endswith("/EstimatedPrice/CountrySubjects"):
            return _json_response([{"id": 296, "name": "Республика Татарстан (Татарстан)"}])
        if request.url.path.endswith("/EstimatedPrice/PriceZones"):
            return _json_response([{"id": 202, "name": "Республика Татарстан"}])
        if request.url.path.endswith("/EstimatedPrice/Periods"):
            return _json_response([
                {"id": 426, "name": "2 квартал 2026 г."},
                {"id": 425, "name": "1 квартал 2026 г."},
            ])
        if request.url.path.endswith("/EstimatedPrice/BuildingResources/Search"):
            return _json_response([
                {
                    "id": 3146000,
                    "title": "06.1.01.05-0036",
                    "description": (
                        "Кирпич керамический рядовой полнотелый одинарный, "
                        "размеры 250х120х65 мм, марка М125"
                    ),
                }
            ])
        if request.url.path.endswith("/EstimatedPrice/BuildingResources/Search/Materials"):
            if params.get("periodId") == "426":
                return _json_response({"items": []})
            return _json_response({
                "items": [{
                    "id": 1,
                    "items": [{
                        "id": 3146000,
                        "code": "06.1.01.05-0036",
                        "name": (
                            "Кирпич керамический рядовой полнотелый одинарный, "
                            "размеры 250х120х65 мм, марка М125"
                        ),
                        "unitName": "шт",
                        "aggregatedPrice": "25.62",
                        "distancePrice": "0",
                        "procureStorageCostPercent": "2.00",
                        "estimatedPrice": "26.13",
                    }],
                }]
            })
        return _json_response({"detail": "not found"}, status_code=404)

    async def scenario():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = FgisCsClient(client=http_client)
            return await client.enrich_draft({
                "region": "Лениногорск, Татарстан",
                "sections": [{
                    "title": "Стены",
                    "positions": [{
                        "code": "AI-01-001",
                        "name": (
                            "Кирпич керамический рядовой полнотелый одинарный "
                            "250х120х65 мм М125"
                        ),
                        "unit": "шт",
                        "quantity": "1000",
                        "price": "1",
                    }],
                }],
            }, observed_at=datetime(2026, 7, 14, 7, 30, tzinfo=timezone.utc))

    draft, evidence = asyncio.run(scenario())

    position = draft["sections"][0]["positions"][0]
    assert position["price"] == "1"
    assert "comment" not in position
    assert evidence == []
    detail_periods = [
        params["periodId"]
        for path, params in requests
        if path.endswith("/Search/Materials")
    ]
    assert detail_periods == ["426"]


def test_enrich_draft_rejects_official_row_with_wrong_unit():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/EstimatedPrice/CountrySubjects"):
            return _json_response([{"id": 296, "name": "Республика Татарстан (Татарстан)"}])
        if request.url.path.endswith("/EstimatedPrice/PriceZones"):
            return _json_response([{"id": 202, "name": "Республика Татарстан"}])
        if request.url.path.endswith("/EstimatedPrice/Periods"):
            return _json_response([{"id": 425, "name": "1 квартал 2026 г."}])
        if request.url.path.endswith("/EstimatedPrice/BuildingResources/Search"):
            return _json_response([{
                "id": 1,
                "title": "04.1.02.01-0005",
                "description": "Смеси бетонные мелкозернистого бетона, класс В12,5",
            }])
        if request.url.path.endswith("/EstimatedPrice/BuildingResources/Search/Materials"):
            return _json_response({"items": [{"items": [{
                "code": "04.1.02.01-0005",
                "name": "Смеси бетонные мелкозернистого бетона, класс В12,5",
                "unitName": "м3",
                "estimatedPrice": "6835.67",
            }]}]})
        return _json_response({}, 404)

    async def scenario():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = FgisCsClient(client=http_client)
            return await client.enrich_draft(draft)

    draft = {
        "region": "Татарстан",
        "sections": [{"title": "Материалы", "positions": [{
            "code": "AI-01-001",
            "name": "Смеси бетонные мелкозернистого бетона, класс В12,5",
            "unit": "кг",
            "quantity": "100",
            "price": "999",
        }]}],
    }
    enriched, evidence = asyncio.run(scenario())

    assert evidence == []
    assert enriched["sections"][0]["positions"][0]["price"] == "999"


def test_enrich_draft_fails_closed_when_region_is_unknown():
    async def scenario():
        transport = httpx.MockTransport(
            lambda _request: _json_response([{"id": 296, "name": "Республика Татарстан (Татарстан)"}])
        )
        async with httpx.AsyncClient(transport=transport) as http_client:
            return await FgisCsClient(client=http_client).enrich_draft(draft)

    draft = {
        "region": "Неизвестная территория",
        "sections": [{"title": "Материалы", "positions": [{
            "code": "AI-01-001", "name": "Кирпич", "unit": "шт", "quantity": "1", "price": "7",
        }]}],
    }
    enriched, evidence = asyncio.run(scenario())
    assert enriched == draft
    assert evidence == []


def test_exact_fgis_code_and_unit_still_require_consistent_resource_name():
    resource = FgisResource(
        code="01.2.03.03-0064",
        name="Мастика битумно-резиновая изоляционная МБР-75",
        unit="т",
        estimated_price=Decimal("46445.29"),
        raw={"id": 42},
        match_score=Decimal("1"),
        kind="material",
        endpoint="/EstimatedPrice/BuildingResources/Search/Materials",
        flag="materials",
    )

    match = FgisCsClient()._match_position(
        {
            "code": resource.code,
            "name": "Кирпич керамический рядовой полнотелый М125",
            "unit": "т",
        },
        [resource],
    )

    assert match is None
