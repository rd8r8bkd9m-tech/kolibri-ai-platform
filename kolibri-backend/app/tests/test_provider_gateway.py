import asyncio
import json
import sys

import httpx
import pytest

from app import ai_provider, healthcheck
from app.providers import get_provider, list_providers


@pytest.fixture(autouse=True)
def reset_runtime_state(monkeypatch):
    ai_provider._provider_blocked_until.clear()
    ai_provider._provider_route_state.clear()
    for provider in ai_provider.PROVIDERS.values():
        monkeypatch.setitem(provider, "key", "")
    yield
    ai_provider._provider_blocked_until.clear()
    ai_provider._provider_route_state.clear()


def test_codex_mimo_deepseek_routing_is_task_aware(monkeypatch):
    # Routing tests only need a resolvable executable; invocation semantics are
    # covered by the dedicated Codex CLI adapter suite.
    monkeypatch.setenv("CODEX_CLI_BINARY", sys.executable)
    for provider_id in ("openai_codex", "mimo", "deepseek_pro", "deepseek_flash"):
        monkeypatch.setitem(ai_provider.PROVIDERS[provider_id], "key", "server-credential")

    assert [item["id"] for item in ai_provider._get_providers_for_task("chat")[:4]] == [
        "codex_cli",
        "mimo",
        "deepseek_flash",
        "deepseek_pro",
    ]
    assert [item["id"] for item in ai_provider._get_providers_for_task("code")[:4]] == [
        "codex_cli",
        "mimo",
        "deepseek_pro",
        "deepseek_flash",
    ]


def test_browser_session_provider_is_never_routable(monkeypatch):
    monkeypatch.setenv("QWEN_API_KEY", "consumer-browser-session")

    class ForbiddenClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("browser session route must never be probed")

    monkeypatch.setattr(healthcheck.httpx, "AsyncClient", ForbiddenClient)

    item = next(provider for provider in list_providers() if provider["id"] == "qwen")
    probe = asyncio.run(healthcheck.probe_provider("qwen"))

    assert item["credential_source"] == "browser_session_forbidden"
    assert item["routing_enabled"] is False
    assert item["route"]["routable"] is False
    assert probe["error_code"] == "provider_route_not_permitted"


def test_route_snapshot_requires_server_credential_and_live_success(monkeypatch):
    provider = ai_provider.PROVIDERS["openai_codex"]
    assert ai_provider.provider_route_snapshot(provider)["status"] == "unavailable"

    monkeypatch.setitem(provider, "routable", True)
    monkeypatch.setitem(provider, "key", "server-credential")
    assert ai_provider.provider_route_snapshot(provider)["status"] == "unverified"

    ai_provider._record_provider_success(provider)
    snapshot = ai_provider.provider_route_snapshot(provider)
    assert snapshot["status"] == "live"
    assert snapshot["routable"] is True
    assert snapshot["verified_at"]


def test_missing_server_credential_fails_before_network(monkeypatch):
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    class ForbiddenClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("network must not run without a server credential")

    monkeypatch.setattr(healthcheck.httpx, "AsyncClient", ForbiddenClient)
    result = asyncio.run(healthcheck.probe_provider("mimo"))

    assert result["status"] == "unavailable"
    assert result["error_code"] == "server_credential_missing"
    assert result["secret_exposed"] is False


def test_live_probe_records_entitlement_without_echoing_provider_content(monkeypatch):
    monkeypatch.setenv("MIMO_API_KEY", "server-credential")
    provider = get_provider("mimo")
    assert provider is not None

    async def upstream(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": provider.default_model}]})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "PRIVATE-PROBE-CONTENT"}}]},
        )

    transport = httpx.MockTransport(upstream)
    real_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return real_client(transport=transport, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(healthcheck.httpx, "AsyncClient", client_factory)
    result = asyncio.run(healthcheck.probe_provider("mimo"))

    assert result["status"] == "live"
    assert result["entitlement"] == "granted"
    assert result["tests"]["chat"] == {"ok": True, "status": 200}
    assert "PRIVATE-PROBE-CONTENT" not in json.dumps(result)


def test_failed_probe_returns_sanitized_failure(monkeypatch):
    monkeypatch.setenv("MIMO_API_KEY", "server-credential")

    async def upstream(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(401, text="SECRET-UPSTREAM-BODY")

    transport = httpx.MockTransport(upstream)
    real_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return real_client(transport=transport, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(healthcheck.httpx, "AsyncClient", client_factory)
    result = asyncio.run(healthcheck.probe_provider("mimo"))

    assert result["status"] == "unavailable"
    assert result["entitlement"] == "denied"
    assert result["error_code"] == "http_401"
    assert "SECRET-UPSTREAM-BODY" not in json.dumps(result)
