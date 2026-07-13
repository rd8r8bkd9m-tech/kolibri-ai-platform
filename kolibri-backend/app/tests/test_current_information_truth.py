import asyncio
import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app import ai_provider, truth_policy
from app.main import app


QUESTION = "Какая сейчас погода в Москве? Покажи источники."
NOW = datetime(2026, 7, 13, 9, 30, tzinfo=timezone.utc)


def _payloads(response) -> list[dict]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_current_question_is_classified_but_stable_question_is_not():
    assert truth_policy.requires_current_evidence(
        [{"role": "user", "content": QUESTION}]
    )
    assert not truth_policy.requires_current_evidence(
        [{"role": "user", "content": "Объясни, почему меняются времена года"}]
    )


def test_no_web_evidence_returns_needs_tool_without_invented_weather():
    async def no_results(query: str, limit: int):
        assert query == QUESTION
        assert limit == 5
        return []

    result = asyncio.run(
        truth_policy.resolve_current_information(
            [{"role": "user", "content": QUESTION}], searcher=no_results, now=NOW
        )
    )

    assert result["status"] == "needs_tool"
    assert result["error_code"] == "current_information_evidence_unavailable"
    assert result["sources"] == []
    assert result["truth"] == {
        "current_information": True,
        "evidence_status": "unavailable",
    }
    assert "+4" not in result["content"]
    assert "не буду подставлять" in result["content"]


def test_web_evidence_has_url_observation_date_and_citation():
    async def results(query: str, limit: int):
        return [
            {
                "title": "Погода в Москве",
                "snippet": "В Москве температура 21 °C, данные метеостанции.",
                "url": "https://weather.example/moscow",
            },
            {
                "title": "Опасный результат",
                "snippet": "Погода в Москве 99 °C",
                "url": "javascript:alert(1)",
            },
        ]

    result = asyncio.run(
        truth_policy.resolve_current_information(
            [{"role": "user", "content": QUESTION}], searcher=results, now=NOW
        )
    )

    assert result["status"] == "source_backed"
    assert result["provider"] == "web_search"
    assert result["sources"] == [
        {
            "citation": 1,
            "title": "Погода в Москве",
            "snippet": "В Москве температура 21 °C, данные метеостанции.",
            "url": "https://weather.example/moscow",
            "retrieved_at": "2026-07-13T09:30:00+00:00",
        }
    ]
    assert "13.07.2026 09:30 UTC" in result["content"]
    assert "Источник [1]: https://weather.example/moscow" in result["content"]
    assert "99 °C" not in result["content"]


def test_stream_current_question_falls_back_to_tool_enabled_provider(monkeypatch):
    async def no_results(query: str, limit: int):
        return []

    async def provider_with_search(*args, **kwargs):
        yield {
            "content": "По данным web search: https://weather.example/current/moscow",
            "done": False,
        }
        yield {
            "content": "",
            "done": True,
            "status": "idle",
            "provider": "codex_cli",
            "model": "account-default",
            "actions": [],
            "fallback_used": False,
        }

    monkeypatch.setattr(truth_policy, "web_search", no_results)
    monkeypatch.setattr(ai_provider, "chat_completion_stream", provider_with_search)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": QUESTION}]},
            headers={"X-Forwarded-For": "truth-no-evidence"},
        )

    payloads = _payloads(response)
    assert response.status_code == 200
    assert payloads[0]["done"] is False
    assert payloads[-1]["done"] is True
    assert payloads[-1]["status"] == "idle"
    assert payloads[-1]["provider"] == "codex_cli"
    content = "".join(str(payload.get("content") or "") for payload in payloads)
    assert "https://weather.example/current/moscow" in content
    assert any(
        "Codex web search" in str((payload.get("work_summary") or {}).get("summary") or "")
        for payload in payloads
    )


def test_stream_current_question_returns_structured_sources(monkeypatch):
    async def results(query: str, limit: int):
        return [
            {
                "title": "Погода в Москве сейчас",
                "snippet": "Температура 20 °C по данным наблюдения.",
                "url": "https://weather.example/current/moscow",
            }
        ]

    monkeypatch.setattr(truth_policy, "web_search", results)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": QUESTION}]},
            headers={"X-Forwarded-For": "truth-with-evidence"},
        )

    payloads = _payloads(response)
    assert payloads[-1]["status"] == "source_backed"
    assert payloads[-1]["provider"] == "web_search"
    assert payloads[-1]["sources"][0]["citation"] == 1
    assert payloads[-1]["sources"][0]["url"] == "https://weather.example/current/moscow"
    content = "".join(str(payload.get("content") or "") for payload in payloads)
    assert "Источник [1]" in content
