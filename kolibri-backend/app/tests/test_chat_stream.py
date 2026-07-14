import json
from decimal import Decimal

import httpx
from fastapi.testclient import TestClient

from app import ai_provider
from app.fgiscs_client import FgisCsClient
from app.main import app


def _bootstrap(client: TestClient) -> None:
    response = client.post("/api/v1/shell/bootstrap")
    assert response.status_code == 200, response.text


def _sse_payloads(response) -> list[dict]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def _content_payloads(response) -> list[dict]:
    return [payload for payload in _sse_payloads(response) if payload.get("content")]


def _work_summaries(response) -> list[dict]:
    return [
        payload["work_summary"]
        for payload in _sse_payloads(response)
        if isinstance(payload.get("work_summary"), dict)
    ]


def _provider(provider_id: str, model: str) -> dict:
    return {
        "id": provider_id,
        "model": model,
        "key": "configured",
        "url": "https://provider.invalid/v1/chat/completions",
    }


def test_chat_stream_emits_token_deltas_and_structured_final_event(monkeypatch):
    provider = _provider("primary", "primary-model")
    monkeypatch.setattr(ai_provider, "_get_providers_for_task", lambda _: [provider])

    async def fake_stream(selected, messages, system=None):
        yield {"content": "При", "done": False}
        yield {"content": "вет", "done": False}
        yield {"content": "", "done": True}

    monkeypatch.setattr(ai_provider, "_stream_ai", fake_stream)

    with TestClient(app) as client:
        _bootstrap(client)
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "Привет"}]},
            headers={"X-Forwarded-For": "stream-normal"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    payloads = _sse_payloads(response)
    assert "".join(payload["content"] for payload in payloads[:-1]) == "Привет"
    assert all(payload["done"] is False for payload in payloads[:-1])
    assert payloads[-1] == {
        "content": "",
        "done": True,
        "actions": [],
        "status": "idle",
        "provider": "primary",
        "model": "primary-model",
        "fallback_used": False,
    }
    summaries = _work_summaries(response)
    assert [(summary["stage"], summary["status"]) for summary in summaries] == [
        ("accepted", "completed"),
        ("provider_route", "active"),
        ("response_received", "completed"),
    ]
    assert summaries[1]["provider"] == "primary"
    assert summaries[1]["model"] == "primary-model"
    assert all("reasoning" not in payload for payload in payloads)
    serialized = json.dumps(payloads, ensure_ascii=False).casefold()
    assert "chain-of-thought" not in serialized
    assert "private reasoning" not in serialized


def test_chat_stream_falls_back_before_first_token(monkeypatch):
    failing = _provider("failing", "failing-model")
    working = _provider("fallback", "fallback-model")
    monkeypatch.setattr(ai_provider, "_get_providers_for_task", lambda _: [failing, working])

    async def fake_stream(selected, messages, system=None):
        if selected["id"] == "failing":
            request = httpx.Request("POST", selected["url"])
            response = httpx.Response(502, request=request)
            raise httpx.HTTPStatusError("upstream failed", request=request, response=response)
        yield {"content": "Ответ", "done": False}
        yield {"content": "", "done": True}

    monkeypatch.setattr(ai_provider, "_stream_ai", fake_stream)

    with TestClient(app) as client:
        _bootstrap(client)
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "Ответь"}]},
            headers={"X-Forwarded-For": "stream-fallback"},
        )

    payloads = _sse_payloads(response)
    assert [payload["content"] for payload in _content_payloads(response)] == ["Ответ"]
    assert payloads[-1]["done"] is True
    assert payloads[-1]["status"] == "idle"
    assert payloads[-1]["provider"] == "fallback"
    assert payloads[-1]["model"] == "fallback-model"
    assert payloads[-1]["fallback_used"] is True
    assert not ai_provider._provider_is_healthy(failing)
    assert ai_provider._provider_is_healthy(working)
    summaries = _work_summaries(response)
    assert [summary["stage"] for summary in summaries] == [
        "accepted",
        "provider_route",
        "provider_route",
        "response_received",
    ]
    assert summaries[1]["status"] == "active"
    assert summaries[1]["provider"] == "failing"
    assert summaries[2]["provider"] == "fallback"
    assert summaries[-1]["status"] == "completed"
    assert all("reasoning" not in summary for summary in summaries)
    assert all("prompt" not in summary for summary in summaries)
    provider_events = [
        payload["provider_event"]
        for payload in payloads
        if isinstance(payload.get("provider_event"), dict)
    ]
    assert provider_events == [{
        "type": "provider.attempt.failed",
        "provider": "failing",
        "model": "failing-model",
        "failure_kind": "http_502",
        "will_retry": True,
    }]
    serialized = json.dumps(provider_events, ensure_ascii=False)
    assert "provider.invalid" not in serialized
    assert "upstream failed" not in serialized


def test_chat_stream_extracts_create_estimate_action_in_final_event(monkeypatch):
    provider = _provider("estimate-provider", "estimate-model")
    monkeypatch.setattr(ai_provider, "_get_providers_for_task", lambda _: [provider])
    content = (
        "Подготовил смету.\n```json\n"
        '{"action":"create_estimate","title":"Дом 100 м² — Лениногорск",'
        '"sections":[{"title":"Фундамент","positions":['
        '{"code":"Ф-01","name":"Плита","unit":"м2","quantity":"100",'
        '"price":"15000","sum":"1","source":"Несуществующий прайс 2026"}]}]}'
        "\n```"
    )

    async def fake_stream(selected, messages, system=None):
        midpoint = len(content) // 2
        yield {"content": content[:midpoint], "done": False}
        yield {"content": content[midpoint:], "done": False}
        yield {"content": "", "done": True}

    monkeypatch.setattr(ai_provider, "_stream_ai", fake_stream)

    with TestClient(app) as client:
        _bootstrap(client)
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "Составь смету"}]},
            headers={"X-Forwarded-For": "stream-estimate"},
        )

    final = _sse_payloads(response)[-1]
    assert _sse_payloads(response)[-2] == {
        "content": (
            "Готовой сметы пока нет: исполнитель не сформировал достаточный "
            "индивидуальный состав либо не найдены подтверждённые цены. "
            "Откройте результат и уточните исходные данные."
        ),
        "done": False,
    }
    assert final["done"] is True
    assert final["status"] == "ready"
    assert final["provider"] == "estimate-provider"
    assert final["model"] == "estimate-model"
    assert len(final["actions"]) == 1
    action = final["actions"][0]
    assert action["type"] == "create_estimate"
    assert action["label"] == "Уточнить данные для сметы"
    assert action["data"]["title"] == "Дом 100 м² — Лениногорск"
    assert action["data"]["estimate_status"] == "needs_input"
    assert action["data"]["pricing_status"] == "needs_input"
    assert action["data"]["price_sources"] == []
    position = action["data"]["sections"][0]["positions"][0]
    assert position["unit"] == "м²"
    assert position["price"] == "0"
    assert position["sum"] == "0.00"
    assert position["source"] == ""
    assert action["data"]["totals"] == {
        "subtotal": "0.00",
        "overhead_amount": "0.00",
        "vat_amount": "0.00",
        "total": "0.00",
    }
    assert "reasoning" not in final


def test_chat_stream_synthesizes_typed_estimate_for_plain_text_provider_response(monkeypatch):
    provider = _provider("plain-provider", "plain-model")
    monkeypatch.setattr(ai_provider, "_get_providers_for_task", lambda _: [provider])

    async def fake_stream(selected, messages, system=None):
        yield {"content": "Для точной сметы нужен проект и прайсы.", "done": False}
        yield {"content": "", "done": True}

    monkeypatch.setattr(ai_provider, "_stream_ai", fake_stream)
    prompt = (
        "Составь предварительную смету на строительство одноэтажного дома "
        "100 м² в Лениногорске, Татарстан. Покажи расчёт и источники цен."
    )

    with TestClient(app) as client:
        _bootstrap(client)
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": prompt}]},
            headers={"X-Forwarded-For": "stream-estimate-plain-text"},
        )

    payloads = _sse_payloads(response)
    final = payloads[-1]
    assert response.status_code == 200
    assert final["done"] is True
    assert final["status"] == "ready"
    assert final["provider"] == "plain-provider"
    assert len(final["actions"]) == 1
    action = final["actions"][0]
    data = action["data"]
    assert action["type"] == "create_estimate"
    assert data["title"] == "Смета: одноэтажный дом 100 м² — Лениногорск, Татарстан"
    assert data["object_name"] == "Одноэтажный дом 100 м²"
    assert data["region"] == "Лениногорск, Татарстан"
    assert data["pricing_status"] == "needs_input"
    assert data["estimate_status"] == "needs_input"
    assert data["price_sources"] == []
    assert data["sections"] == []
    assert data["totals"]["total"] == "0.00"
    assert data["vat_rate"] == "0"


def test_chat_nonstream_never_exposes_raw_estimate_json(monkeypatch):
    provider = _provider("estimate-provider", "estimate-model")
    monkeypatch.setattr(ai_provider, "_get_providers_for_task", lambda _: [provider])

    async def fake_call(selected, messages, system=None):
        return {
            "content": "```json\n{\"action\":\"create_estimate\",\"sections\":[]}\n```",
            "reasoning": "private provider trace",
            "actions": [],
            "status": "idle",
            "provider": "estimate-provider",
            "model": "estimate-model",
        }

    monkeypatch.setattr(ai_provider, "_call_ai", fake_call)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "user", "content": "Составь смету на дом 100 м²"}]},
            headers={"X-Forwarded-For": "nonstream-estimate-json"},
        )

    result = response.json()
    assert response.status_code == 200
    assert "```" not in result["content"]
    assert "create_estimate" not in result["content"]
    assert result["reasoning"] == ""
    assert result["actions"][0]["type"] == "create_estimate"
    assert result["status"] == "ready"


def test_chat_preserves_zero_price_provider_draft_as_needs_input(monkeypatch):
    provider = _provider("zero-provider", "zero-model")
    monkeypatch.setattr(ai_provider, "_get_providers_for_task", lambda _: [provider])

    async def fake_call(selected, messages, system=None):
        return {
            "content": "Черновик позиций подготовлен.",
            "reasoning": "",
            "actions": [{
                "type": "create_estimate",
                "label": "Открыть смету",
                "data": {
                    "title": "Дом",
                    "sections": [{
                        "title": "Фундамент",
                        "positions": [{
                            "name": "Плита",
                            "unit": "м2",
                            "quantity": "100",
                            "price": "0",
                        }],
                    }],
                },
            }],
            "status": "idle",
            "provider": "zero-provider",
            "model": "zero-model",
        }

    monkeypatch.setattr(ai_provider, "_call_ai", fake_call)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "user", "content": "Составь смету на дом 100 м² в Лениногорске"}]},
            headers={"X-Forwarded-For": "zero-price-estimate"},
        )

    result = response.json()
    action = result["actions"][0]
    assert action["data"]["pricing_status"] == "needs_input"
    assert action["data"]["estimate_status"] == "needs_input"
    assert Decimal(action["data"]["totals"]["total"]) == 0
    positions = [position for section in action["data"]["sections"] for position in section["positions"]]
    assert len(positions) == 1
    assert positions[0]["name"] == "Плита"
    assert positions[0]["price"] == "0"


def test_chat_stream_returns_needs_input_action_when_routes_are_exhausted(monkeypatch):
    monkeypatch.setattr(ai_provider, "_get_providers_for_task", lambda _: [])

    with TestClient(app) as client:
        _bootstrap(client)
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "Составь смету на дом 100 м²"}]},
            headers={"X-Forwarded-For": "stream-estimate-local-contract"},
        )

    final = _sse_payloads(response)[-1]
    assert final["status"] == "ready"
    assert final["provider"] == "local_contract"
    assert final["model"] == "deterministic-estimate-v1"
    assert final["fallback_used"] is False
    assert final["actions"][0]["data"]["pricing_status"] == "needs_input"
    assert final["actions"][0]["data"]["sections"] == []


def test_chat_stream_interruption_survives_estimate_attestation_runtime_error(monkeypatch):
    provider = _provider("interrupted-provider", "interrupted-model")
    monkeypatch.setattr(ai_provider, "_get_providers_for_task", lambda _: [provider])
    monkeypatch.setenv("KOLIBRI_ESTIMATE_FGIS_ENABLED", "true")
    content = (
        "```json\n"
        '{"action":"create_estimate","title":"Дом 100 м² — Лениногорск",'
        '"region":"Лениногорск, Татарстан","sections":[{"title":"Материалы",'
        '"positions":[{"code":"01.2.03.03-0064","name":"Мастика",'
        '"unit":"т","quantity":"2","price":"999999"}]}]}'
        "\n```"
    )

    async def interrupted_stream(selected, messages, system=None):
        yield {"content": content, "done": False}
        request = httpx.Request("POST", selected["url"])
        raise httpx.ReadError("stream interrupted", request=request)

    async def failing_enrich(self, draft, **_kwargs):
        draft["sections"][0]["positions"][0]["price"] = "46445.29"
        raise RuntimeError("estimate_evidence_signing_key_not_configured")

    monkeypatch.setattr(ai_provider, "_stream_ai", interrupted_stream)
    monkeypatch.setattr(FgisCsClient, "enrich_draft", failing_enrich)

    with TestClient(app) as client:
        _bootstrap(client)
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "Составь смету на дом 100 м²"}]},
            headers={"X-Forwarded-For": "stream-estimate-attestation-failure"},
        )

    final = _sse_payloads(response)[-1]
    assert response.status_code == 200
    assert final["done"] is True
    assert final["status"] == "ready"
    assert final["error_code"] == "provider_stream_interrupted"
    action = final["actions"][0]
    position = action["data"]["sections"][0]["positions"][0]
    assert position["price"] == "0"
    assert position["sum"] == "0.00"
    assert position["price_evidence"] == []
    assert action["data"]["pricing_status"] == "needs_input"
    assert action["data"]["totals"]["total"] == "0.00"


def test_chat_stream_extracts_safe_document_content(monkeypatch):
    provider = _provider("document-provider", "document-model")
    monkeypatch.setattr(ai_provider, "_get_providers_for_task", lambda _: [provider])
    content = (
        "```json\n"
        '{"action":"create_document","title":"Договор подряда","type":"contract",'
        '"content":"1. Предмет договора\\n<script>alert(1)</script>"}'
        "\n```"
    )

    async def fake_stream(selected, messages, system=None):
        yield {"content": content, "done": False}
        yield {"content": "", "done": True}

    monkeypatch.setattr(ai_provider, "_stream_ai", fake_stream)

    with TestClient(app) as client:
        _bootstrap(client)
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "Подготовь договор"}]},
            headers={"X-Forwarded-For": "stream-document"},
        )

    payloads = _sse_payloads(response)
    assert payloads[-2] == {
        "content": "Документ подготовлен для сохранения в текущем проекте.",
        "done": False,
    }
    assert payloads[-1]["actions"] == [
        {
            "type": "create_document",
            "label": "Создать Договор подряда",
            "data": {
                "title": "Договор подряда",
                "type": "contract",
                "content": "<p>1. Предмет договора</p><p>&lt;script&gt;alert(1)&lt;/script&gt;</p>",
            },
        }
    ]
