import asyncio

import httpx
import pytest

from app import ai_provider


@pytest.fixture(autouse=True)
def reset_provider_circuits(monkeypatch):
    ai_provider._provider_blocked_until.clear()
    monkeypatch.delenv("KIMI_CFBT_ENABLED", raising=False)
    yield
    ai_provider._provider_blocked_until.clear()


def test_uncredentialed_cfbt_is_not_a_route(monkeypatch):
    for provider in ai_provider.PROVIDERS.values():
        monkeypatch.setitem(provider, "key", "")

    assert ai_provider._get_providers_for_task("chat") == []


def test_chat_prefers_working_official_route(monkeypatch):
    for provider in ai_provider.PROVIDERS.values():
        monkeypatch.setitem(provider, "key", "")
    monkeypatch.setitem(ai_provider.PROVIDERS["deepseek_flash"], "key", "configured")
    monkeypatch.setitem(ai_provider.PROVIDERS["kimi_code"], "key", "configured")

    assert [p["model"] for p in ai_provider._get_providers_for_task("chat")] == [
        ai_provider.PROVIDERS["deepseek_flash"]["model"],
        ai_provider.PROVIDERS["kimi_code"]["model"],
    ]


def test_failed_route_is_circuited_and_next_route_completes(monkeypatch):
    failing = dict(ai_provider.PROVIDERS["deepseek_flash"], id="failing", key="configured")
    working = dict(ai_provider.PROVIDERS["kimi_code"], id="working", key="configured")
    monkeypatch.setattr(ai_provider, "_get_providers_for_task", lambda _: [failing, working])

    async def fake_call(provider, messages, system=None):
        if provider["id"] == "failing":
            request = httpx.Request("POST", "https://provider.invalid/v1/chat/completions")
            response = httpx.Response(502, request=request)
            raise httpx.HTTPStatusError("upstream failed", request=request, response=response)
        return {
            "content": "Готово",
            "reasoning": "",
            "actions": [],
            "status": "idle",
            "provider": "official",
            "model": provider["model"],
            "speed_ms": 10,
        }

    monkeypatch.setattr(ai_provider, "_call_ai", fake_call)
    result = asyncio.run(ai_provider.chat_completion([{"role": "user", "content": "Привет"}]))

    assert result["content"] == "Готово"
    assert result["fallback_used"] is True
    assert not ai_provider._provider_is_healthy(failing)
    assert ai_provider._provider_is_healthy(working)


def test_exhausted_routes_never_expose_upstream_url(monkeypatch):
    failed = dict(ai_provider.PROVIDERS["cfbt"], id="failed", key="configured")
    monkeypatch.setattr(ai_provider, "_get_providers_for_task", lambda _: [failed])

    async def fake_call(provider, messages, system=None):
        request = httpx.Request("POST", "https://secret-upstream.invalid/v1/chat/completions")
        response = httpx.Response(502, request=request)
        raise httpx.HTTPStatusError("bad gateway", request=request, response=response)

    monkeypatch.setattr(ai_provider, "_call_ai", fake_call)
    result = asyncio.run(ai_provider.chat_completion([{"role": "user", "content": "Привет"}]))

    assert result["status"] == "error"
    assert result["error_code"] == "provider_routes_exhausted"
    assert "secret-upstream" not in result["content"]
    assert "502" not in result["content"]
