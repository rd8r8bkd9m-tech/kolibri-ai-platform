from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json

import httpx
import pytest

from app import ai_provider
from app.estimate_action import build_estimate_action
from app.estimate_evidence import attest_price_evidence
from app.fgiscs_client import FgisCsClient
from app.project_facts import resolve_project_region
from app.project_schemas import PersistedEstimateAction


REGION_CASES = (
    (
        "Составь смету на ремонт офиса 80 м² в Москве",
        "Москва",
        "Москва",
    ),
    (
        "Составь смету на монтаж вентиляции в Самарской области",
        "Самарская область",
        "Самарская область",
    ),
    (
        "Составь смету на дом 100 м², Лениногорск, Татарстан",
        "Лениногорск, Татарстан",
        "Республика Татарстан (Татарстан)",
    ),
)


def _provider_action(region: str = "Республика Татарстан") -> dict:
    return {
        "type": "create_estimate",
        "label": "draft",
        "data": {
            "title": "Смета объекта",
            "region": region,
            "sections": [
                {
                    "title": "Материалы",
                    "positions": [
                        {
                            "code": "TEST-REGION-001",
                            "name": "Кирпич керамический рядовой полнотелый М125",
                            "unit": "шт",
                            "quantity": "10",
                            "price": "999999",
                        }
                    ],
                }
            ],
        },
    }


@pytest.mark.parametrize(("prompt", "expected_region", "_source_region"), REGION_CASES)
def test_current_request_region_overrides_stale_provider_region(
    prompt: str,
    expected_region: str,
    _source_region: str,
):
    action = build_estimate_action(prompt, _provider_action()["data"])

    assert action["data"]["region"] == expected_region


def test_persisted_project_fact_supplies_region_when_request_omits_it():
    fact = resolve_project_region(
        "Составь смету на монтаж вентиляции",
        project_fact={"region": "Новосибирская область"},
        candidate_region="Татарстан",
    )
    action = build_estimate_action(
        "Составь смету на монтаж вентиляции",
        _provider_action()["data"],
        project_fact={"region": "Новосибирская область"},
    )

    assert fact.region == "Новосибирская область"
    assert fact.source == "project_fact"
    assert action["data"]["region"] == "Новосибирская область"


@pytest.mark.parametrize(("prompt", "expected_region", "source_region"), REGION_CASES)
def test_materialization_routes_exact_project_region_and_persists_price_region(
    monkeypatch,
    prompt: str,
    expected_region: str,
    source_region: str,
):
    monkeypatch.setenv("KOLIBRI_ESTIMATE_FGIS_ENABLED", "true")
    observed_regions: list[str] = []

    async def fake_enrich(self, draft, **_kwargs):
        observed_regions.append(draft["region"])
        position = draft["sections"][0]["positions"][0]
        position["price"] = "125.50"
        now = datetime.now(timezone.utc)
        evidence = attest_price_evidence(
            {
                "position_code": position["code"],
                "source_id": f"official-region:{source_region}",
                "url": "https://fgiscs.minstroyrf.ru/api/EstimatedPrice/BuildingResources/Search/Materials",
                "source_title": f"ФГИС ЦС — {source_region}",
                "source_type": "official_catalog",
                "region": source_region,
                "project_region": expected_region,
                "observed_at": now.isoformat().replace("+00:00", "Z"),
                "price_date": now.date().isoformat(),
                "unit": "шт",
                "vat_status": "excluded",
                "quote": "Официальная ставка 125.50 руб./шт, без НДС.",
                "unit_price": "125.50",
                "currency": "RUB",
                "content_sha256": "a" * 64,
                "verification": "verified",
            }
        )
        return draft, [evidence]

    monkeypatch.setattr(FgisCsClient, "enrich_draft", fake_enrich)
    actions = asyncio.run(
        ai_provider._materialize_estimate_actions(
            [{"role": "user", "content": prompt}],
            [_provider_action()],
        )
    )

    assert observed_regions == [expected_region]
    data = actions[0]["data"]
    assert data["region"] == expected_region
    assert data["price_sources"][0]["region"] == source_region
    assert data["price_sources"][0]["project_region"] == expected_region
    assert data["sections"][0]["positions"][0]["price_evidence"][0]["region"] == source_region

    persisted = PersistedEstimateAction.model_validate(actions[0])
    persisted_evidence = persisted.data.sections[0].positions[0].price_evidence[0]
    assert persisted.data.region == expected_region
    assert persisted_evidence.region == source_region
    assert persisted_evidence.project_region == expected_region


@pytest.mark.parametrize(
    ("requested_region", "subject_id", "subject_name", "price_zone_id"),
    (
        ("Москва", 77, "Москва", 770),
        ("Самарская область", 63, "Самарская область", 630),
        ("Лениногорск, Татарстан", 16, "Республика Татарстан (Татарстан)", 160),
    ),
)
def test_fgis_lookup_uses_requested_subject_and_binds_source_region_to_price(
    requested_region: str,
    subject_id: int,
    subject_name: str,
    price_zone_id: int,
):
    requests: list[tuple[str, dict[str, str]]] = []
    subjects = [
        {"id": 77, "name": "Москва"},
        {"id": 50, "name": "Московская область"},
        {"id": 63, "name": "Самарская область"},
        {"id": 16, "name": "Республика Татарстан (Татарстан)"},
    ]

    def response(payload, status_code=200):
        return httpx.Response(
            status_code,
            headers={"content-type": "application/json; charset=utf-8"},
            content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params.multi_items())
        requests.append((request.url.path, params))
        if request.url.path.endswith("/EstimatedPrice/CountrySubjects"):
            return response(subjects)
        if request.url.path.endswith("/EstimatedPrice/PriceZones"):
            if params.get("subjectId") != str(subject_id):
                return response([], 200)
            return response([{"id": price_zone_id, "name": subject_name}])
        if request.url.path.endswith("/EstimatedPrice/Periods"):
            return response([{"id": 426, "name": "2 квартал 2026 г."}])
        if request.url.path.endswith("/Search/Materials"):
            return response(
                {
                    "items": [
                        {
                            "items": [
                                {
                                    "code": "TEST-REGION-001",
                                    "name": "Кирпич керамический рядовой полнотелый М125",
                                    "unitName": "шт",
                                    "aggregatedPrice": "125.50",
                                    "distancePrice": "0",
                                    "procureStorageCostPercent": "0",
                                    "estimatedPrice": "125.50",
                                }
                            ]
                        }
                    ]
                }
            )
        if request.url.path.endswith("/Search/Machines") or request.url.path.endswith(
            "/EstimatedPrice/RimWorkerSalaryRegistry"
        ):
            return response({"items": []})
        return response({"detail": "not found"}, 404)

    async def scenario():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            return await FgisCsClient(client=http_client).enrich_draft(
                {
                    "region": requested_region,
                    "sections": [
                        {
                            "title": "Материалы",
                            "positions": [
                                {
                                    "code": "TEST-REGION-001",
                                    "name": "Кирпич керамический рядовой полнотелый М125",
                                    "unit": "шт",
                                    "quantity": "10",
                                    "price": "0",
                                }
                            ],
                        }
                    ],
                },
                observed_at=datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc),
            )

    draft, evidence = asyncio.run(scenario())

    assert draft["sections"][0]["positions"][0]["price"] == "125.5"
    assert evidence[0]["region"] == subject_name
    assert evidence[0]["project_region"] == requested_region
    assert evidence[0]["unit_price"] == "125.5"
    assert any(
        path.endswith("/EstimatedPrice/PriceZones")
        and params == {"subjectId": str(subject_id)}
        for path, params in requests
    )
    assert any(
        path.endswith("/Search/Materials")
        and params.get("priceZoneId") == str(price_zone_id)
        for path, params in requests
    )
