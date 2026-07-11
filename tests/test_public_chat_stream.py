from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import main
import public_chat_stream
from providers import ProviderGatewayError


def _verified_result(text: str, *, evidence_text: str | None = None) -> dict:
    bound_text = text if evidence_text is None else evidence_text
    output = bound_text.encode("utf-8")
    evidence = [
        {
            "type": "provider_execution",
            "provider": "factory",
            "provider_model": "codex",
            "route_transport": "home_control_plane",
            "node_ref": "node:private-topology-ref",
            "exit_code": 0,
            "output_sha256": hashlib.sha256(output).hexdigest(),
            "output_bytes": len(output),
        },
        {
            "type": "deterministic_verifier",
            "verdict": "passed",
            "binding_sha256": "b" * 64,
        },
    ]
    return {
        "response": text,
        "model": "kolibri",
        "technical": {
            "provider_routing": {
                "selected_provider": "factory",
                "selected_runner": "codex",
                "control_plane_url": "http://10.99.0.1:9101",
                "upstream_error": "Bearer server-secret-must-not-leak",
                "evidence": evidence,
            }
        },
    }


class RecordingManager:
    def __init__(self, result: dict):
        self.result = result
        self.calls: list[dict] = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def _events(response_text: str) -> list[tuple[str, dict]]:
    events = []
    for frame in response_text.strip().split("\n\n"):
        lines = frame.splitlines()
        event = next(line.removeprefix("event: ") for line in lines if line.startswith("event: "))
        data = next(line.removeprefix("data: ") for line in lines if line.startswith("data: "))
        events.append((event, json.loads(data)))
    return events


def _client(monkeypatch, manager: RecordingManager) -> TestClient:
    monkeypatch.setattr(main, "ai_manager", manager)
    monkeypatch.setattr(main, "check_rate_limit", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main, "cache_response", lambda *_args, **_kwargs: None)
    return TestClient(main.app)


def test_public_stream_emits_immediate_lifecycle_then_one_verified_answer(monkeypatch):
    answer = "Готов подтверждённый ответ."
    manager = RecordingManager(_verified_result(answer))

    response = _client(monkeypatch, manager).post(
        "/api/chat/stream?timeout_seconds=5",
        json={
            "messages": [{"role": "user", "content": "Продолжай"}],
            "model": "untrusted-provider-model",
            "provider": "untrusted-provider",
            "execution_mode": "codex",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store, no-transform"
    assert response.headers["x-accel-buffering"] == "no"
    events = _events(response.text)
    assert [event for event, _ in events] == ["accepted", "progress", "completed", "done"]
    assert [data["status"] for _, data in events] == ["accepted", "running", "completed", "completed"]
    terminal = events[2][1]
    assert terminal["response"] == answer
    assert terminal["model"] == "kolibri"
    assert terminal["verification"]["status"] == "passed"
    assert terminal["verification"]["output_sha256"] == hashlib.sha256(answer.encode("utf-8")).hexdigest()
    assert "delta" not in response.text
    assert "technical" not in response.text
    assert "10.99.0.1" not in response.text
    assert "server-secret-must-not-leak" not in response.text
    assert "private-topology-ref" not in response.text
    assert len(manager.calls) == 1
    assert manager.calls[0]["model"] == "kolibri"
    assert manager.calls[0]["provider"] is None
    assert manager.calls[0]["execution_mode"] == "codex"


@pytest.mark.parametrize("path", ["/api/v1/chat/stream", "/api/v1/ai/chat/stream"])
def test_public_stream_supports_fast_alias_and_never_completes_unbound_output(monkeypatch, path):
    answer = "Этот текст не связан с evidence."
    manager = RecordingManager(_verified_result(answer, evidence_text="другой ответ"))

    response = _client(monkeypatch, manager).post(
        path,
        json={
            "messages": [{"role": "user", "content": "Быстро"}],
            "execution_mode": "fast",
        },
    )

    events = _events(response.text)
    assert [event for event, _ in events] == ["accepted", "progress", "failed", "done"]
    assert events[2][1]["error"] == {
        "code": "verification_failed",
        "message": "Kolibri could not produce a verified answer",
        "retryable": False,
    }
    assert answer not in response.text
    assert manager.calls[0]["execution_mode"] == "fast"


def test_public_stream_timeout_cancels_transport_task_without_false_success(monkeypatch):
    cancelled = asyncio.Event()

    async def execute():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(public_chat_stream, "stream_timeout_seconds", lambda _value=None: 0.01)

    async def collect():
        return [
            item
            async for item in public_chat_stream.public_chat_event_stream(
                stream_id="stream_test",
                execution_mode="fast",
                execute=execute,
                timeout_seconds=1,
            )
        ]

    output = "".join(asyncio.run(collect()))
    events = _events(output)
    assert [event for event, _ in events] == ["accepted", "progress", "timeout", "done"]
    assert events[2][1]["error"]["code"] == "timeout"
    assert events[2][1]["status"] == "failed"
    assert "completed" not in [event for event, _ in events]
    assert cancelled.is_set()


def test_public_stream_flushes_status_before_waiting_for_provider():
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def execute():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def probe():
        stream = public_chat_stream.public_chat_event_stream(
            stream_id="stream_immediate",
            execution_mode="codex",
            execute=execute,
            timeout_seconds=30,
        )
        accepted = await asyncio.wait_for(anext(stream), timeout=0.1)
        progress = await asyncio.wait_for(anext(stream), timeout=0.1)
        await asyncio.sleep(0)
        assert started.is_set()
        await stream.aclose()
        return accepted + progress

    output = asyncio.run(probe())
    assert [event for event, _ in _events(output)] == ["accepted", "progress"]
    assert cancelled.is_set()


def test_public_stream_redacts_provider_failure_details(monkeypatch):
    secret = "Bearer private-upstream-secret"

    class FailedManager:
        calls = []

        async def generate(self, **kwargs):
            self.calls.append(kwargs)
            raise ProviderGatewayError({
                "error_type": "factory_control_auth_failed",
                "upstream_body": secret,
                "node_id": "internal-worker-name",
            })

    response = _client(monkeypatch, FailedManager()).post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "Ответь"}]},
    )

    events = _events(response.text)
    assert [event for event, _ in events] == ["accepted", "progress", "failed", "done"]
    assert events[2][1]["error"]["code"] == "provider_unavailable"
    assert secret not in response.text
    assert "internal-worker-name" not in response.text
    assert "factory_control_auth_failed" not in response.text


def test_public_stream_rejects_unknown_mode_before_starting_provider(monkeypatch):
    manager = RecordingManager(_verified_result("unused"))
    response = _client(monkeypatch, manager).post(
        "/api/chat/stream",
        json={
            "messages": [{"role": "user", "content": "Привет"}],
            "execution_mode": "direct-provider",
        },
    )

    assert response.status_code == 422
    assert manager.calls == []
