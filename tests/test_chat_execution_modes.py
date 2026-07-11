from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import main
import providers
from providers import AIProviderManager


def _verified_routing(text: str, *, runner: str) -> dict:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    evidence = [
        {
            "type": "provider_execution",
            "provider": "factory",
            "provider_model": runner,
            "provider_runner": runner,
            "route_transport": "home_control_plane",
            "exit_code": 0,
            "output_sha256": digest,
            "output_bytes": len(text.encode("utf-8")),
            "completion_signal": "fenced_non_empty_assistant_output",
        },
        {
            "type": "deterministic_verifier",
            "verifier": "kolibri.gateway.contract.v1",
            "verdict": "passed",
            "binding_sha256": "b" * 64,
        },
    ]
    return {
        "selected_provider": "factory",
        "selected_runner": runner,
        "attempts": [{"attempt": 1, "provider": "factory", "status": "succeeded"}],
        "fallback_used": False,
        "evidence": evidence,
    }


class RecordingManager:
    def __init__(self):
        self.calls: list[dict] = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        mode = kwargs["execution_mode"]
        runner = "codex" if mode == "codex" else "mimo"
        text = f"answer-from-{mode}"
        return {
            "response": text,
            "model": "kolibri",
            "technical": {"provider_routing": _verified_routing(text, runner=runner)},
        }


def test_public_chat_forwards_execution_mode_and_isolates_cache(monkeypatch):
    manager = RecordingManager()
    cache: dict[str, dict[str, str]] = {}
    monkeypatch.setattr(main, "ai_manager", manager)
    monkeypatch.setattr(main, "check_rate_limit", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main, "get_cached_response", lambda key: cache.get(key))
    monkeypatch.setattr(
        main,
        "cache_response",
        lambda key, response, provider: cache.__setitem__(
            key, {"response": response, "provider": provider}
        ),
    )
    client = TestClient(main.app)
    base = {
        "messages": [{"role": "user", "content": "Один и тот же вопрос"}],
        # Provider-shaped model names are never exposed or forwarded.
        "model": "some-client-provider-model",
        "provider": "untrusted-client-provider",
    }

    fast_first = client.post("/api/chat", json={**base, "execution_mode": "fast"})
    codex_first = client.post("/api/v1/chat", json={**base, "execution_mode": "codex"})
    fast_cached = client.post("/api/chat", json={**base, "execution_mode": "fast"})
    codex_cached = client.post("/api/v1/chat", json={**base, "execution_mode": "codex"})

    assert [response.status_code for response in (
        fast_first, codex_first, fast_cached, codex_cached,
    )] == [200, 200, 200, 200]
    assert fast_first.json()["response"] == fast_cached.json()["response"] == "answer-from-fast"
    assert codex_first.json()["response"] == codex_cached.json()["response"] == "answer-from-codex"
    assert fast_first.json()["cached"] is False
    assert codex_first.json()["cached"] is False
    assert fast_cached.json()["cached"] is True
    assert codex_cached.json()["cached"] is True
    assert [call["execution_mode"] for call in manager.calls] == ["fast", "codex"]
    assert all(call["model"] == "kolibri" for call in manager.calls)
    assert all(call["provider"] is None for call in manager.calls)
    assert len(cache) == 2
    for response in (fast_first, codex_first, fast_cached, codex_cached):
        payload = response.json()
        assert payload["model"] == "kolibri"
        assert "provider" not in payload


def test_public_chat_rejects_unknown_execution_mode_with_422(monkeypatch):
    manager = RecordingManager()
    monkeypatch.setattr(main, "ai_manager", manager)
    monkeypatch.setattr(main, "check_rate_limit", lambda *_args, **_kwargs: True)

    response = TestClient(main.app).post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "Привет"}],
            "execution_mode": "direct-provider",
        },
    )

    assert response.status_code == 422
    assert manager.calls == []


def test_public_model_catalog_advertises_supported_modes_without_provider_catalog():
    client = TestClient(main.app)

    compatibility = client.get("/api/models")
    openai_catalog = client.get("/v1/models")

    assert compatibility.status_code == openai_catalog.status_code == 200
    for response in (compatibility, openai_catalog):
        payload = response.json()
        assert payload["supported_execution_modes"] == ["fast", "codex"]
        assert [item["id"] for item in payload["data"]] == ["kolibri"]
        assert "providers" not in payload


def test_manager_keeps_legacy_gateway_without_optional_keywords(monkeypatch):
    text = "legacy gateway answer"
    technical = _verified_routing(text, runner="codex")

    class LegacyGateway:
        def __init__(self):
            self.calls = []

        def generate(self, input_value, instructions, response_id):
            self.calls.append((input_value, instructions, response_id))
            return SimpleNamespace(status="completed", text=text, technical=technical)

    gateway = LegacyGateway()
    monkeypatch.setattr(
        providers,
        "get_capability_gateway",
        lambda: SimpleNamespace(plan_skills=lambda _request: []),
    )

    result = asyncio.run(AIProviderManager(gateway).generate(
        messages=[{"role": "user", "content": "Продолжай"}],
        model="kolibri",
        execution_mode="codex",
    ))

    assert result["response"] == text
    assert result["model"] == "kolibri"
    assert len(gateway.calls) == 1


def test_manager_does_not_mask_internal_type_error(monkeypatch):
    class BrokenGateway:
        def generate(
            self, input_value, instructions, response_id,
            *, planned_skills=None, execution_mode="fast",
        ):
            del input_value, instructions, response_id, planned_skills, execution_mode
            raise TypeError("internal execution_mode failure")

    monkeypatch.setattr(
        providers,
        "get_capability_gateway",
        lambda: SimpleNamespace(plan_skills=lambda _request: []),
    )

    with pytest.raises(TypeError, match="internal execution_mode failure"):
        asyncio.run(AIProviderManager(BrokenGateway()).generate(
            messages=[{"role": "user", "content": "Продолжай"}],
            model="kolibri",
            execution_mode="codex",
        ))
