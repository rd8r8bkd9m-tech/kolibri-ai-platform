import json
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from app import ai_provider, capability_runtime, truth_policy
from app.fgiscs_client import FgisCsClient
from app.main import app
from app.routers import openai_compat


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


def _work_events(response) -> list[dict]:
    return [
        payload
        for payload in _sse_payloads(response)
        if payload.get("type") == "response.work_summary.updated"
    ]


def _provider(provider_id: str, model: str) -> dict:
    return {
        "id": provider_id,
        "model": model,
        "key": "configured",
        "url": "https://provider.invalid/v1/chat/completions",
    }


def test_estimate_with_current_web_prices_keeps_estimate_vertical(monkeypatch):
    prompt = (
        "создай настоящую предварительную смету на строительство забора "
        "9 погонных метров высота 2 метра из профлиста в городе Лениногорск, "
        "Татарстан; используй актуальные цены из интернета по региону и покажи источники"
    )
    truth_calls: list[str] = []
    estimate_calls: list[str] = []

    async def generic_truth(messages, **kwargs):
        truth_calls.append(messages[-1]["content"])
        return {
            "content": "Только ссылки из общего веб-поиска",
            "actions": [],
            "status": "source_backed",
            "provider": "web_search",
            "model": "deterministic-evidence-renderer",
            "sources": [{"url": "https://prices.example/profnastil"}],
        }

    async def estimate_stream(messages, **kwargs):
        estimate_calls.append(messages[-1]["content"])
        yield {
            "content": "",
            "done": True,
            "actions": [{
                "type": "create_estimate",
                "label": "Открыть предварительную смету",
                "data": {
                    "title": "Смета: забор — Лениногорск",
                    "region": "Лениногорск, Татарстан",
                },
            }],
            "status": "ready",
            "provider": "estimate-provider",
            "model": "estimate-model",
            "fallback_used": False,
        }

    monkeypatch.setattr(truth_policy, "resolve_current_information", generic_truth)
    monkeypatch.setattr(ai_provider, "chat_completion_stream", estimate_stream)

    with TestClient(app) as client:
        _bootstrap(client)
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": prompt}]},
            headers={"X-Forwarded-For": "estimate-current-prices-routing"},
        )

    assert response.status_code == 200
    assert truth_calls == []
    assert estimate_calls == [prompt]
    payloads = _sse_payloads(response)
    final = next(
        payload for payload in reversed(payloads)
        if payload.get("done") is True and "type" not in payload
    )
    assert final["actions"][0]["type"] == "create_estimate"
    assert final["actions"][0]["data"]["region"] == "Лениногорск, Татарстан"
    assert "Только ссылки" not in json.dumps(payloads, ensure_ascii=False)


def test_pure_current_web_query_keeps_generic_truth_route(monkeypatch):
    prompt = "Найди актуальные цены на профлист в Лениногорске и покажи источники"
    truth_calls: list[str] = []
    provider_calls: list[str] = []

    async def generic_truth(messages, **kwargs):
        truth_calls.append(messages[-1]["content"])
        return {
            "content": "Источник: https://prices.example/profnastil",
            "actions": [],
            "status": "source_backed",
            "provider": "web_search",
            "model": "deterministic-evidence-renderer",
            "sources": [{"url": "https://prices.example/profnastil"}],
        }

    async def provider_stream(messages, **kwargs):
        provider_calls.append(messages[-1]["content"])
        yield {"content": "Неверный маршрут", "done": True, "actions": []}

    monkeypatch.setattr(truth_policy, "resolve_current_information", generic_truth)
    monkeypatch.setattr(ai_provider, "chat_completion_stream", provider_stream)

    with TestClient(app) as client:
        _bootstrap(client)
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": prompt}]},
            headers={"X-Forwarded-For": "pure-current-web-routing"},
        )

    assert response.status_code == 200
    assert truth_calls == [prompt]
    assert provider_calls == []
    payloads = _sse_payloads(response)
    assert "https://prices.example/profnastil" in "".join(
        str(payload.get("content") or "") for payload in payloads
    )
    assert all(
        action.get("type") != "create_estimate"
        for payload in payloads
        for action in payload.get("actions", [])
    )


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
        response_id = next(
            payload["response"]["id"]
            for payload in _sse_payloads(response)
            if payload.get("type") == "response.created"
        )
        replay = client.get(
            f"/api/v1/responses/{response_id}/events?starting_after=0"
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    payloads = _sse_payloads(response)
    live_deltas = [payload["content"] for payload in _content_payloads(response)]
    assert "".join(live_deltas) == "Привет"
    assert sum(1 for payload in payloads if payload.get("done") is True) == 1
    assert payloads[-1] == {
        "content": "",
        "done": True,
        "actions": [],
        "status": "idle",
        "provider": "kolibri",
        "model": "kolibri",
        "fallback_used": False,
    }
    replay_payloads = _sse_payloads(replay)
    canonical_types = {
        "response.created",
        "response.output_text.delta",
        "response.artifact.ready",
        "response.completed",
        "response.failed",
        "response.cancelled",
    }
    live_canonical = [
        payload for payload in payloads if payload.get("type") in canonical_types
    ]
    replay_canonical = [
        payload for payload in replay_payloads if payload.get("type") in canonical_types
    ]
    assert live_canonical == replay_canonical
    assert [payload["sequence"] for payload in live_canonical] == sorted(
        payload["sequence"] for payload in live_canonical
    )
    replay_deltas = [
        payload["delta"]
        for payload in replay_payloads
        if payload.get("type") == "response.output_text.delta"
    ]
    assert "".join(replay_deltas) == "Привет"
    assert replay_deltas == live_deltas
    assert [
        payload["type"]
        for payload in replay_payloads
        if payload.get("type") in {
            "response.completed",
            "response.failed",
            "response.cancelled",
        }
    ] == ["response.completed"]
    summaries = _work_summaries(response)
    assert [(summary["stage"], summary["status"]) for summary in summaries] == [
        ("accepted", "completed"),
        ("provider_route", "active"),
        ("response_received", "completed"),
    ]
    assert all("provider" not in summary for summary in summaries)
    assert all("model" not in summary for summary in summaries)
    live_work_events = _work_events(response)
    replay_work_events = _work_events(replay)
    assert live_work_events == replay_work_events
    assert [event["sequence"] for event in live_work_events] == sorted(
        event["sequence"] for event in live_work_events
    )
    assert all(event["response_id"] == response_id for event in live_work_events)
    assert all(event["work_summary"]["kind"] == "stage" for event in live_work_events)
    assert all(event["work_summary"]["occurred_at"] for event in live_work_events)
    assert all("reasoning" not in payload for payload in payloads)
    serialized = json.dumps(payloads, ensure_ascii=False).casefold()
    assert "chain-of-thought" not in serialized
    assert "private reasoning" not in serialized


def test_legacy_chat_surfaces_hide_provider_identity_but_keep_internal_telemetry(monkeypatch):
    recorded: list[tuple[str, str | None, str | None]] = []

    async def fake_completion(messages, **kwargs):
        return {
            "content": "Синхронный ответ",
            "actions": [],
            "status": "ready",
            "provider": "private-provider",
            "model": "private-model",
            "_provider": "private-route",
            "_model": "private-upstream-model",
        }

    async def fake_stream(messages, **kwargs):
        yield {"content": "Потоковый ответ", "done": False}
        yield {
            "content": "",
            "done": True,
            "actions": [],
            "status": "ready",
            "provider": "private-provider",
            "model": "private-model",
            "_provider": "private-route",
            "_model": "private-upstream-model",
        }

    def record(capability_id, **kwargs):
        recorded.append((capability_id, kwargs.get("provider"), kwargs.get("model")))

    monkeypatch.setattr(ai_provider, "chat_completion", fake_completion)
    monkeypatch.setattr(ai_provider, "chat_completion_stream", fake_stream)
    monkeypatch.setattr(capability_runtime, "record_capability_invocation", record)

    with TestClient(app) as client:
        _bootstrap(client)
        sync = client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "user", "content": "Ответь коротко"}]},
            headers={"X-Forwarded-For": "legacy-public-identity-sync"},
        )
        streamed = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "Продолжи коротко"}]},
            headers={"X-Forwarded-For": "legacy-public-identity-stream"},
        )

    assert sync.status_code == 200
    assert sync.json()["provider"] == "kolibri"
    assert sync.json()["model"] == "kolibri"
    stream_payloads = _sse_payloads(streamed)
    legacy_final = next(payload for payload in reversed(stream_payloads) if payload.get("done") is True)
    assert legacy_final["provider"] == "kolibri"
    assert legacy_final["model"] == "kolibri"
    public_bytes = json.dumps([sync.json(), stream_payloads], ensure_ascii=False)
    assert "private-provider" not in public_bytes
    assert "private-model" not in public_bytes
    assert "private-route" not in public_bytes
    assert ("chat.responses", "private-provider", "private-model") in recorded
    assert ("chat.streaming", "private-provider", "private-model") in recorded


@pytest.mark.parametrize(
    "nonterminal_status",
    [
        "queued",
        "planning",
        "in_progress",
        "running",
        "waiting_for_input",
        "approval_required",
        "verifying",
    ],
)
def test_chat_stream_background_handoff_is_not_a_legacy_terminal(
    monkeypatch,
    nonterminal_status,
):
    async def fake_stream(messages, **kwargs):
        assert kwargs["background"] is True
        yield {
            "content": "",
            "done": True,
            "status": nonterminal_status,
            "provider": "openai_codex",
            "model": "account-default",
            "response_id": f"resp_upstream_{nonterminal_status}",
        }

    recorded_capabilities: list[str] = []

    def record_evidence(capability_id, **kwargs):
        recorded_capabilities.append(capability_id)

    monkeypatch.setattr(ai_provider, "chat_completion_stream", fake_stream)
    monkeypatch.setattr(
        capability_runtime,
        "record_capability_invocation",
        record_evidence,
    )

    with TestClient(app) as client:
        _bootstrap(client)
        response = client.post(
            "/api/v1/chat/stream",
            json={
                "messages": [{"role": "user", "content": "Долгая задача"}],
                "background": True,
            },
            headers={"X-Forwarded-For": f"background-{nonterminal_status}"},
        )

    payloads = _sse_payloads(response)
    created = next(
        payload for payload in payloads if payload.get("type") == "response.created"
    )
    public_response_id = created["response"]["id"]
    status_event = next(
        payload
        for payload in payloads
        if payload.get("type") == "response.status.updated"
    )

    assert response.status_code == 200
    assert not any(payload.get("done") is True for payload in payloads)
    assert status_event["response_id"] == public_response_id
    assert status_event["status"] == nonterminal_status
    assert status_event["response"]["status"] == nonterminal_status
    assert isinstance(status_event["sequence"], int)
    assert openai_compat._records[public_response_id]["status"] == nonterminal_status
    assert "chat.streaming" not in recorded_capabilities


def test_chat_stream_background_handoff_replays_to_terminal_without_duplicates(
    monkeypatch,
):
    async def fake_stream(messages, **kwargs):
        yield {
            "content": "",
            "done": True,
            "status": "queued",
            "provider": "openai_codex",
            "model": "account-default",
            "response_id": "resp_upstream_background_replay",
        }

    async def fake_retrieve(provider, response_id):
        assert response_id == "resp_upstream_background_replay"
        return {"status": "completed", "content": "Фоновый ответ готов"}

    monkeypatch.setattr(ai_provider, "chat_completion_stream", fake_stream)
    monkeypatch.setattr(openai_compat, "retrieve_response", fake_retrieve)

    with TestClient(app) as client:
        _bootstrap(client)
        response = client.post(
            "/api/v1/chat/stream",
            json={
                "messages": [{"role": "user", "content": "Долгая задача"}],
                "background": True,
            },
            headers={"X-Forwarded-For": "background-terminal-replay"},
        )
        payloads = _sse_payloads(response)
        public_response_id = next(
            payload["response"]["id"]
            for payload in payloads
            if payload.get("type") == "response.created"
        )
        status_event = next(
            payload
            for payload in payloads
            if payload.get("type") == "response.status.updated"
        )
        replay = client.get(
            f"/api/v1/responses/{public_response_id}/events"
            f"?starting_after={status_event['sequence']}"
        )

    replay_payloads = _sse_payloads(replay)
    assert not any(payload.get("done") is True for payload in payloads)
    assert [
        payload["delta"]
        for payload in replay_payloads
        if payload.get("type") == "response.output_text.delta"
    ] == ["Фоновый ответ готов"]
    assert [
        payload["type"]
        for payload in replay_payloads
        if payload.get("type") in {
            "response.completed",
            "response.failed",
            "response.cancelled",
        }
    ] == ["response.completed"]
    sequences = [payload["sequence"] for payload in replay_payloads]
    assert sequences == sorted(set(sequences))


def test_chat_stream_success_survives_optional_evidence_ledger_failure(monkeypatch):
    async def fake_stream(messages, **kwargs):
        yield {"content": "Ответ", "done": False}
        yield {
            "content": "",
            "done": True,
            "actions": [],
            "status": "idle",
            "provider": "primary",
            "model": "primary-model",
            "fallback_used": False,
        }

    def fail_evidence(*args, **kwargs):
        raise OSError("evidence ledger unavailable")

    monkeypatch.setattr(ai_provider, "chat_completion_stream", fake_stream)
    monkeypatch.setattr(capability_runtime, "record_capability_invocation", fail_evidence)

    with TestClient(app) as client:
        _bootstrap(client)
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "Ответь"}]},
            headers={"X-Forwarded-For": "stream-evidence-outage-success"},
        )
        payloads = _sse_payloads(response)
        response_id = next(
            payload["response"]["id"]
            for payload in payloads
            if payload.get("type") == "response.created"
        )
        replay = client.get(
            f"/api/v1/responses/{response_id}/events?starting_after=0"
        )

    assert [payload["content"] for payload in _content_payloads(response)] == ["Ответ"]
    assert sum(1 for payload in payloads if payload.get("done") is True) == 1
    assert payloads[-1]["status"] == "idle"
    assert [
        payload["type"]
        for payload in _sse_payloads(replay)
        if payload.get("type") in {"response.completed", "response.failed"}
    ] == ["response.completed"]


def test_chat_stream_error_survives_optional_evidence_ledger_failure(monkeypatch):
    async def failing_stream(messages, **kwargs):
        raise RuntimeError("provider stream exploded")
        yield  # pragma: no cover

    def fail_evidence(*args, **kwargs):
        raise OSError("evidence ledger unavailable")

    monkeypatch.setattr(ai_provider, "chat_completion_stream", failing_stream)
    monkeypatch.setattr(capability_runtime, "record_capability_invocation", fail_evidence)

    with TestClient(app) as client:
        _bootstrap(client)
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "Ответь"}]},
            headers={"X-Forwarded-For": "stream-evidence-outage-error"},
        )
        payloads = _sse_payloads(response)
        response_id = next(
            payload["response"]["id"]
            for payload in payloads
            if payload.get("type") == "response.created"
        )
        replay = client.get(
            f"/api/v1/responses/{response_id}/events?starting_after=0"
        )

    assert sum(1 for payload in payloads if payload.get("done") is True) == 1
    assert payloads[-1]["status"] == "error"
    assert payloads[-1]["error_code"] == "provider_stream_failed"
    assert payloads[-1]["provider"] == "kolibri"
    assert payloads[-1]["model"] == "kolibri"
    assert [
        payload["type"]
        for payload in _sse_payloads(replay)
        if payload.get("type") in {"response.completed", "response.failed"}
    ] == ["response.failed"]


def test_chat_stream_reasoning_excerpt_is_canonical_and_replayable(monkeypatch):
    async def fake_chat_completion_stream(messages, **kwargs):
        base = {
            "kind": "reasoning_excerpt",
            "step_id": "step_reasoning_live",
            "summary_id": "summary_reasoning_live",
            "stage": "reasoning_summary",
            "summary": "Сверяю источники",
            "occurred_at": "2026-07-14T12:00:00+00:00",
        }
        yield {
            "content": "",
            "done": False,
            "work_summary": {**base, "status": "active"},
        }
        yield {
            "content": "",
            "done": False,
            "work_summary": {**base, "status": "completed"},
        }
        yield {"content": "Ответ", "done": False}
        yield {
            "content": "",
            "done": True,
            "status": "idle",
            "provider": "private-provider",
            "model": "private-model",
        }

    monkeypatch.setattr(
        ai_provider,
        "chat_completion_stream",
        fake_chat_completion_stream,
    )
    with TestClient(app) as client:
        _bootstrap(client)
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "Проверь"}]},
            headers={"X-Forwarded-For": "stream-reasoning-summary"},
        )
        response_id = next(
            payload["response"]["id"]
            for payload in _sse_payloads(response)
            if payload.get("type") == "response.created"
        )
        replay = client.get(
            f"/api/v1/responses/{response_id}/events?starting_after=0"
        )

    reasoning = [
        event
        for event in _work_events(response)
        if event["work_summary"]["stage"] == "reasoning_summary"
    ]
    replay_reasoning = [
        event
        for event in _work_events(replay)
        if event["work_summary"]["stage"] == "reasoning_summary"
    ]
    assert reasoning == replay_reasoning
    assert [event["work_summary"]["status"] for event in reasoning] == [
        "active",
        "completed",
    ]
    assert {event["work_summary"]["summary_id"] for event in reasoning} == {
        "summary_reasoning_live"
    }
    assert all(
        event["work_summary"]["kind"] == "reasoning_excerpt"
        for event in reasoning
    )


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
        response_id = next(
            payload["response"]["id"]
            for payload in _sse_payloads(response)
            if payload.get("type") == "response.created"
        )
        replay = client.get(
            f"/api/v1/responses/{response_id}/events?starting_after=0"
        )

    payloads = _sse_payloads(response)
    assert [payload["content"] for payload in _content_payloads(response)] == ["Ответ"]
    assert payloads[-1]["done"] is True
    assert payloads[-1]["status"] == "idle"
    assert payloads[-1]["provider"] == "kolibri"
    assert payloads[-1]["model"] == "kolibri"
    assert payloads[-1]["fallback_used"] is True
    assert not ai_provider._provider_is_healthy(failing)
    assert ai_provider._provider_is_healthy(working)
    summaries = _work_summaries(response)
    assert [summary["stage"] for summary in summaries] == [
        "accepted",
        "provider_route",
        "provider_attempt",
        "provider_route",
        "response_received",
    ]
    assert summaries[1]["status"] == "active"
    assert all("provider" not in summary for summary in summaries)
    assert all("model" not in summary for summary in summaries)
    assert summaries[-1]["status"] == "completed"
    assert _work_events(response) == _work_events(replay)
    assert all("reasoning" not in summary for summary in summaries)
    assert all("prompt" not in summary for summary in summaries)
    provider_events = [
        payload["provider_event"]
        for payload in payloads
        if isinstance(payload.get("provider_event"), dict)
    ]
    assert provider_events == [{
        "type": "provider.attempt.failed",
        "failure_kind": "http_502",
        "will_retry": True,
    }]
    serialized = json.dumps(provider_events, ensure_ascii=False)
    assert "failing-model" not in serialized
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

    legacy_payloads = [
        payload for payload in _sse_payloads(response) if "type" not in payload
    ]
    final = legacy_payloads[-1]
    assert legacy_payloads[-2] == {
        "content": (
            "Предварительная смета рассчитана по профессиональным допущениям "
            "и готова к редактированию. Проверьте допущения и цены перед договором."
        ),
        "done": False,
    }
    assert final["done"] is True
    assert final["status"] == "ready"
    assert final["provider"] == "kolibri"
    assert final["model"] == "kolibri"
    assert len(final["actions"]) == 1
    action = final["actions"][0]
    assert action["type"] == "create_estimate"
    assert action["label"] == "Открыть предварительную смету"
    assert action["data"]["title"] == "Дом 100 м² — Лениногорск"
    assert action["data"]["estimate_status"] == "preliminary"
    assert action["data"]["pricing_status"] == "preliminary"
    assert action["data"]["price_sources"] == []
    position = action["data"]["sections"][0]["positions"][0]
    assert position["unit"] == "м²"
    assert position["price"] == "15000"
    assert position["sum"] == "1500000.00"
    assert position["source"] == ""
    assert action["data"]["totals"] == {
        "subtotal": "1500000.00",
        "overhead_amount": "0.00",
        "vat_amount": "0.00",
        "total": "1500000.00",
    }
    price_research = [
        summary
        for summary in _work_summaries(response)
        if summary["stage"] == "source_retrieval"
        and summary["summary"] in {
            "Подбираю актуальные региональные цены",
            "Предварительные цены рассчитаны по профессиональным допущениям",
        }
    ]
    assert [
        (summary["status"], summary["summary"])
        for summary in price_research
    ] == [
        ("active", "Подбираю актуальные региональные цены"),
        ("completed", "Предварительные цены рассчитаны по профессиональным допущениям"),
    ]
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
    assert final["provider"] == "kolibri"
    assert final["model"] == "kolibri"
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
    assert final["provider"] == "kolibri"
    assert final["model"] == "kolibri"
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
    assert position["price"] == "999999"
    assert position["sum"] == "1999998.00"
    assert position["price_evidence"] == []
    assert action["data"]["pricing_status"] == "preliminary"
    assert action["data"]["totals"]["total"] == "1999998.00"


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
    legacy_payloads = [payload for payload in payloads if "type" not in payload]
    assert legacy_payloads[-2] == {
        "content": "Документ подготовлен для сохранения в текущем проекте.",
        "done": False,
    }
    assert legacy_payloads[-1]["actions"] == [
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
