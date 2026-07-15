import asyncio
from datetime import datetime, timezone

from app import ai_provider
from app.estimate_action import build_estimate_action
from app.estimate_evidence import attest_price_evidence
from app.fgiscs_client import FgisCsClient
from app.project_schemas import PersistedEstimateAction


MESSAGES = [{
    "role": "user",
    "content": "Составь смету на строительство дома 100 м², Лениногорск, Татарстан",
}]


def _provider_action(price: str = "999999") -> dict:
    return {
        "type": "create_estimate",
        "label": "fake",
        "data": {
            "title": "Индивидуальная смета дома",
            "region": "Лениногорск, Татарстан",
            "sections": [{
                "title": "Материалы",
                "positions": [{
                    "code": "01.2.03.03-0064",
                    "name": "Мастика битумно-резиновая изоляционная МБР-75",
                    "unit": "т",
                    "quantity": "2",
                    "price": price,
                    "source": "https://provider.invalid/fake",
                }],
            }],
        },
    }


async def _collect_streamed_materialization(actions: list[dict]):
    trace: list[dict] = []
    materialized: list[dict] | None = None
    async for event, result in ai_provider._stream_estimate_materialization(
        MESSAGES, actions
    ):
        if event is not None:
            trace.append(event["work_summary"])
        if result is not None:
            materialized = result
    assert materialized is not None
    return materialized, trace


def test_materialization_replaces_provider_price_only_with_trusted_source(monkeypatch):
    monkeypatch.setenv("KOLIBRI_ESTIMATE_FGIS_ENABLED", "true")

    async def fake_enrich(self, draft, **_kwargs):
        position = draft["sections"][0]["positions"][0]
        now = datetime.now(timezone.utc)
        assert position["price"] == "0.00"
        assert position["source"] == ""
        position["price"] = "46445.29"
        return draft, [attest_price_evidence({
            "position_code": position["code"],
            "source_id": "fgiscs:426:202:01.2.03.03-0064",
            "url": (
                "https://fgiscs.minstroyrf.ru/api/EstimatedPrice/BuildingResources/"
                "Search/Materials?periodId=426&priceZoneId=202&materials=true"
            ),
            "source_title": "ФГИС ЦС — Татарстан, II квартал 2026",
            "source_type": "official_catalog",
            "region": "Республика Татарстан (Татарстан)",
            "observed_at": now.isoformat().replace("+00:00", "Z"),
            "price_date": now.date().isoformat(),
            "unit": "т",
            "vat_status": "excluded",
            "quote": "Сметная цена 46445.29 руб./т, без НДС.",
            "unit_price": "46445.29",
            "currency": "RUB",
            "content_sha256": "a" * 64,
            "verification": "verified",
        })]

    monkeypatch.setattr(FgisCsClient, "enrich_draft", fake_enrich)
    actions, trace = asyncio.run(
        _collect_streamed_materialization([_provider_action()])
    )

    data = actions[0]["data"]
    position = data["sections"][0]["positions"][0]
    assert position["price"] == "46445.29"
    assert position["sum"] == "92890.58"
    assert data["totals"]["total"] == "92890.58"
    assert data["pricing_status"] == "verified"
    assert data["estimate_status"] == "source_backed"
    assert position["source"].startswith("https://fgiscs.minstroyrf.ru/")
    assert trace == [
        {
            "stage": "source_retrieval",
            "summary": "Подбираю актуальные региональные цены",
            "status": "active",
        },
        {
            "stage": "source_retrieval",
            "summary": "Актуальные цены подтверждены источниками",
            "status": "completed",
        },
    ]


def test_materialization_keeps_partial_real_prices_as_preliminary_editor(monkeypatch):
    monkeypatch.setenv("KOLIBRI_ESTIMATE_FGIS_ENABLED", "true")
    monkeypatch.setenv("KOLIBRI_ESTIMATE_COMMERCIAL_FALLBACK_ENABLED", "false")
    provider_action = _provider_action()
    provider_action["data"]["sections"][0]["positions"].append({
        "code": "UNKNOWN-02",
        "name": "Неисследованный дополнительный материал",
        "unit": "шт",
        "quantity": "3",
        "price": "777",
    })

    async def fake_enrich(self, draft, **_kwargs):
        position = draft["sections"][0]["positions"][0]
        unknown = draft["sections"][0]["positions"][1]
        now = datetime.now(timezone.utc)
        assert position["price"] == "0.00"
        assert unknown["price"] == "0.00"
        position["price"] = "46445.29"
        return draft, [attest_price_evidence({
            "position_code": position["code"],
            "source_id": "fgiscs:426:202:01.2.03.03-0064",
            "url": "https://fgiscs.minstroyrf.ru/catalog/01.2.03.03-0064",
            "source_title": "ФГИС ЦС — Татарстан, II квартал 2026",
            "source_type": "official_catalog",
            "region": "Республика Татарстан",
            "observed_at": now.isoformat().replace("+00:00", "Z"),
            "price_date": now.date().isoformat(),
            "unit": "т",
            "vat_status": "excluded",
            "quote": "Сметная цена 46445.29 руб./т, без НДС.",
            "unit_price": "46445.29",
            "currency": "RUB",
            "content_sha256": "c" * 64,
            "verification": "verified",
        })]

    monkeypatch.setattr(FgisCsClient, "enrich_draft", fake_enrich)
    actions, trace = asyncio.run(_collect_streamed_materialization([provider_action]))

    data = actions[0]["data"]
    first, unknown = data["sections"][0]["positions"]
    assert actions[0]["label"] == "Открыть предварительную смету"
    assert data["pricing_status"] == "preliminary"
    assert data["estimate_status"] == "preliminary"
    assert first["price"] == "46445.29"
    assert first["sum"] == "92890.58"
    assert first["price_evidence"]
    assert unknown["price"] == "0"
    assert unknown["sum"] == "0.00"
    assert unknown["price_evidence"] == []
    assert data["totals"]["total"] == "92890.58"
    assert any("в сумму не включены" in item.casefold() for item in data["assumptions"])
    assert trace[-1] == {
        "stage": "source_retrieval",
        "summary": "Часть цен подтверждена; неизвестные строки исключены из итога",
        "status": "completed",
    }
    assert PersistedEstimateAction.model_validate(actions[0]).data.pricing_status == "preliminary"


def test_materialization_never_retains_unverified_provider_price(monkeypatch):
    monkeypatch.setenv("KOLIBRI_ESTIMATE_FGIS_ENABLED", "false")
    actions, trace = asyncio.run(
        _collect_streamed_materialization([_provider_action()])
    )

    data = actions[0]["data"]
    position = data["sections"][0]["positions"][0]
    assert position["price"] == "0"
    assert position["sum"] == "0.00"
    assert position["source"] == ""
    assert data["totals"]["total"] == "0.00"
    assert data["pricing_status"] == "needs_input"
    assert data["estimate_status"] == "needs_input"
    assert trace == [
        {
            "stage": "source_retrieval",
            "summary": "Подбираю актуальные региональные цены",
            "status": "active",
        },
        {
            "stage": "source_retrieval",
            "summary": "Не удалось подтвердить цены — нужны уточнения",
            "status": "failed",
        },
    ]


def test_action_total_equals_sum_of_rounded_money_lines():
    candidate = {
        "sections": [{
            "title": "Проверка округления",
            "positions": [
                {
                    "code": f"ROUND-{index}",
                    "name": f"Строка {index}",
                    "unit": "шт",
                    "quantity": "1",
                    "price": "0.005",
                }
                for index in range(1, 4)
            ],
        }],
    }

    action = build_estimate_action(MESSAGES[0]["content"], candidate)
    lines = action["data"]["sections"][0]["positions"]

    assert [line["sum"] for line in lines] == ["0.01", "0.01", "0.01"]
    assert action["data"]["totals"]["subtotal"] == "0.03"
    assert action["data"]["totals"]["total"] == "0.03"
    # The durable message-action contract must use the same arithmetic as the
    # estimate editor/storage engine, otherwise a valid provider action is
    # rejected before the user can open it.
    assert PersistedEstimateAction.model_validate(action).data.totals.total == "0.03"


def test_materialization_zeroes_collector_price_when_evidence_is_rejected(monkeypatch):
    monkeypatch.setenv("KOLIBRI_ESTIMATE_FGIS_ENABLED", "true")

    async def fake_enrich(self, draft, **_kwargs):
        position = draft["sections"][0]["positions"][0]
        now = datetime.now(timezone.utc)
        position["price"] = "46445.29"
        # Structurally valid, but not emitted by the trusted collector
        # boundary: public/provider data cannot mint this attestation.
        return draft, [{
            "position_code": position["code"],
            "source_id": "forged:fgiscs:01.2.03.03-0064",
            "url": "https://fgiscs.minstroyrf.ru/prices/forged",
            "source_title": "Неподтверждённая запись",
            "source_type": "official_catalog",
            "region": "Республика Татарстан",
            "observed_at": now.isoformat().replace("+00:00", "Z"),
            "price_date": now.date().isoformat(),
            "unit": "т",
            "vat_status": "excluded",
            "quote": "Сметная цена 46445.29 руб./т, без НДС.",
            "unit_price": "46445.29",
            "currency": "RUB",
            "content_sha256": "b" * 64,
            "verification": "verified",
        }]

    monkeypatch.setattr(FgisCsClient, "enrich_draft", fake_enrich)
    actions = asyncio.run(ai_provider._materialize_estimate_actions(MESSAGES, [_provider_action()]))

    data = actions[0]["data"]
    position = data["sections"][0]["positions"][0]
    assert position["price"] == "0"
    assert position["sum"] == "0.00"
    assert position["source"] == ""
    assert position["price_evidence"] == []
    assert data["totals"]["total"] == "0.00"
    assert data["pricing_status"] == "needs_input"
    assert data["estimate_status"] == "needs_input"
    assert any(issue["code"] == "untrusted_evidence" for issue in data["evidence_issues"])


def test_materialization_fails_closed_when_attestation_configuration_raises(monkeypatch):
    monkeypatch.setenv("KOLIBRI_ESTIMATE_FGIS_ENABLED", "true")

    async def failing_enrich(self, draft, **_kwargs):
        # A collector may have populated part of a draft before the evidence
        # signer rejects its runtime configuration.  None of that partial price
        # state may cross the trust boundary.
        draft["sections"][0]["positions"][0]["price"] = "46445.29"
        raise RuntimeError("estimate_evidence_signing_key_not_configured")

    monkeypatch.setattr(FgisCsClient, "enrich_draft", failing_enrich)
    actions = asyncio.run(
        ai_provider._materialize_estimate_actions(MESSAGES, [_provider_action()])
    )

    data = actions[0]["data"]
    position = data["sections"][0]["positions"][0]
    assert position["price"] == "0"
    assert position["sum"] == "0.00"
    assert position["source"] == ""
    assert position["price_evidence"] == []
    assert data["totals"]["total"] == "0.00"
    assert data["pricing_status"] == "needs_input"
    assert data["estimate_status"] == "needs_input"
