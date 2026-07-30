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
    monkeypatch.setenv("CODEX_CLI_ENABLED", "false")
    for provider in ai_provider.PROVIDERS.values():
        monkeypatch.setitem(provider, "key", "")

    assert ai_provider._get_providers_for_task("chat") == []


def test_gpt_56_prompt_is_outcome_first_without_repeated_tool_rule(monkeypatch):
    monkeypatch.setattr(ai_provider, "_live_capability_names", lambda: ["Веб-поиск"])

    prompt = ai_provider._kolibri_system_prompt()

    assert "Критерии готовности:" in prompt
    assert "после чего работа остановлена без лишних циклов" in prompt
    assert prompt.count("проверь capability/инструмент") == 1
    assert "если результат пустой, частичный или сомнительный" in prompt


def test_chat_prefers_working_official_route(monkeypatch):
    monkeypatch.setenv("CODEX_CLI_ENABLED", "false")
    for provider in ai_provider.PROVIDERS.values():
        monkeypatch.setitem(provider, "key", "")
    monkeypatch.setitem(ai_provider.PROVIDERS["deepseek_flash"], "key", "configured")
    monkeypatch.setitem(ai_provider.PROVIDERS["kimi_code"], "key", "configured")
    monkeypatch.setitem(ai_provider.PROVIDERS["openai_codex"], "key", "configured")

    assert [p["model"] for p in ai_provider._get_providers_for_task("chat")] == [
        ai_provider.PROVIDERS["openai_codex"]["model"],
        ai_provider.PROVIDERS["deepseek_flash"]["model"],
        ai_provider.PROVIDERS["kimi_code"]["model"],
    ]


def test_factory_execution_mode_uses_policy_auto_route_for_estimates():
    assert ai_provider._factory_execution_mode("chat", False) == "mimo"
    assert ai_provider._factory_execution_mode("fast", False) == "mimo"
    assert ai_provider._factory_execution_mode("analyze", True) == "fast"
    assert ai_provider._factory_execution_mode("analyze", False) == "codex"


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
    result = asyncio.run(ai_provider.chat_completion([{"role": "user", "content": "Ответь"}]))

    assert result["content"] == "Готово"
    assert result["fallback_used"] is True
    assert not ai_provider._provider_is_healthy(failing)
    assert ai_provider._provider_is_healthy(working)


def test_async_cancellation_does_not_open_provider_circuit(monkeypatch):
    provider = dict(
        ai_provider.PROVIDERS["deepseek_flash"],
        id="cancelled-provider",
        key="configured",
    )
    monkeypatch.setattr(
        ai_provider, "_get_providers_for_task", lambda _task_type: [provider]
    )

    async def cancelled_call(selected, messages, system=None):
        assert selected is provider
        raise asyncio.CancelledError

    monkeypatch.setattr(ai_provider, "_call_ai", cancelled_call)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            ai_provider.chat_completion([{"role": "user", "content": "Отмени"}])
        )

    assert ai_provider._provider_is_healthy(provider)


def test_exhausted_routes_never_expose_upstream_url(monkeypatch):
    failed = dict(ai_provider.PROVIDERS["cfbt"], id="failed", key="configured")
    monkeypatch.setattr(ai_provider, "_get_providers_for_task", lambda _: [failed])

    async def fake_call(provider, messages, system=None):
        request = httpx.Request("POST", "https://secret-upstream.invalid/v1/chat/completions")
        response = httpx.Response(502, request=request)
        raise httpx.HTTPStatusError("bad gateway", request=request, response=response)

    monkeypatch.setattr(ai_provider, "_call_ai", fake_call)
    result = asyncio.run(ai_provider.chat_completion([{"role": "user", "content": "Ответь"}]))
    assert result["status"] == "error"
    assert result["error_code"] == "provider_routes_exhausted"
    assert "secret-upstream" not in result["content"]
    assert "502" not in result["content"]


def test_greeting_is_answered_via_provider(monkeypatch):
    provider = dict(ai_provider.PROVIDERS["deepseek_flash"], id="prov", key="configured")
    monkeypatch.setattr(ai_provider, "_get_providers_for_task", lambda _task: [provider])

    async def fake_call(selected, messages, **_kwargs):
        assert selected is provider
        return {
            "content": "Привет",
            "reasoning": "",
            "actions": [],
            "status": "idle",
            "provider": "deepseek_flash",
            "model": selected["model"],
            "speed_ms": 12,
        }

    monkeypatch.setattr(ai_provider, "_call_ai", fake_call)
    result = asyncio.run(ai_provider.chat_completion([{"role": "user", "content": "Привет"}]))

    assert result["content"] == "Привет"
    assert result["provider"] == "deepseek_flash"
    assert result["speed_ms"] == 12


def test_greeting_stream_yields_visible_text_immediately_without_factory(monkeypatch):
    provider = dict(ai_provider.PROVIDERS["deepseek_flash"], id="prov", key="configured")
    monkeypatch.setattr(ai_provider, "_get_providers_for_task", lambda _task: [provider])

    async def fake_stream(*_args, **_kwargs):
        yield {"content": "Привет"}
        yield {"content": ""}

    async def fake_call(*_args, **_kwargs):
        raise AssertionError("sync branch should not be used in stream path")

    monkeypatch.setattr(ai_provider, "_stream_ai", fake_stream)
    monkeypatch.setattr(ai_provider, "_call_ai", fake_call)

    async def first_event():
        stream = ai_provider.chat_completion_stream(
            [{"role": "user", "content": "Привет"}]
        )
        first = await asyncio.wait_for(anext(stream), timeout=0.1)
        await stream.aclose()
        return first

    assert asyncio.run(first_event()) == {"content": "Привет", "done": False}


@pytest.mark.parametrize(
    "prompt",
    (
        "Расскажи о себе",
        "Какая модель сейчас отвечает?",
        "Какие модели у тебя подключены?",
        "Tell me about yourself",
    ),
)
def test_extended_identity_queries_go_through_provider(monkeypatch, prompt):
    provider = dict(ai_provider.PROVIDERS["deepseek_flash"], id="prov", key="configured")
    monkeypatch.setattr(ai_provider, "_get_providers_for_task", lambda _task: [provider])

    async def fake_call(selected, messages, **_kwargs):
        return {
            "content": "Я обрабатываю запрос через провайдера",
            "reasoning": "",
            "actions": [],
            "status": "idle",
            "provider": "deepseek_flash",
            "model": selected["model"],
            "speed_ms": 15,
        }

    async def fake_stream(*_args, **_kwargs):
        yield {"content": "Я обрабатываю запрос через провайдера"}

    monkeypatch.setattr(ai_provider, "_call_ai", fake_call)
    monkeypatch.setattr(ai_provider, "_stream_ai", fake_stream)

    async def execute():
        messages = [{"role": "user", "content": prompt}]
        result = await ai_provider.chat_completion(messages)
        stream = [event async for event in ai_provider.chat_completion_stream(messages)]
        return result, stream

    result, stream = asyncio.run(execute())

    assert result["provider"] == "deepseek_flash"
    assert result["content"] == "Я обрабатываю запрос через провайдера"
    assert stream[0] == {"content": "Я обрабатываю запрос через провайдера", "done": False}
    assert stream[-1]["done"] is True
    assert stream[-1]["provider"] == "deepseek_flash"
