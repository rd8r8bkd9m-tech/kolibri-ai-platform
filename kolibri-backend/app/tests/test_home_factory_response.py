from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.home_factory_response import (
    HomeFactoryResponseClient,
    HomeFactoryResponseError,
    HomeFactoryResponseSettings,
)


def _settings() -> HomeFactoryResponseSettings:
    return HomeFactoryResponseSettings(
        control_plane_url="http://home-control:9101",
        release_id="kolibri-r17-test",
        timeout_seconds=10,
        poll_seconds=0.05,
        request_timeout_seconds=2,
    )


def _completed(task_id: str, *, verified: bool = True) -> dict:
    attempt_id = f"{task_id}-attempt-1"
    binding = "sha256:" + "b" * 64
    result_sha = "sha256:" + "a" * 64
    checks = {
        name: True
        for name in (
            "agent",
            "attempt",
            "binding_sha256",
            "fencing_token",
            "lease_actor",
            "lease_slot",
            "node",
            "result",
            "result_reference",
            "result_sha256",
            "status",
            "task",
        )
    }
    return {
        "task_id": task_id,
        "state": "completed",
        "attempt_id": attempt_id,
        "fencing_token": 1,
        "lease_owner": "home:home-codex-provider",
        "result": {
            "status": "completed",
            "response": "Проверенный ответ",
            "model": "gpt-5.5",
        },
        "completion_evidence": {
            "node_id": "home",
            "agent_id": "home-codex-provider",
            "attempt_id": attempt_id,
            "fencing_token": 1,
            "result_reference": "/artifacts/result.json",
            "result_sha256": result_sha,
            "binding_sha256": binding,
        },
        "completion_verifier": {
            "verdict": "passed" if verified else "failed",
            "independent": True,
            "verifier": "control-plane/home",
            "binding_sha256": binding,
            "checks": checks,
        },
    }


def test_submit_uses_home_control_plane_and_requires_independent_verifier():
    calls: list[tuple[str, str, dict | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        if request.method == "POST":
            return httpx.Response(201, json={"task_id": body["task_id"], "state": "queued"})
        task_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=_completed(task_id))

    client = HomeFactoryResponseClient(
        _settings(), transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(
        client.submit(
            [{"role": "user", "content": "Привет"}],
            run_id="resp_test",
            idempotency_key="idem-test",
        )
    )

    assert result["content"] == "Проверенный ответ"
    assert result["task_id"] == "KOL-RESP-resp_test"
    assert result["executor_node"] == "home"
    assert result["verifier_node"] == "control-plane/home"
    assert calls[0][0:2] == ("POST", "/v1/tasks")
    assert calls[0][2]["target_node"] == "home"
    assert calls[0][2]["runner"] == "codex"
    assert calls[0][2]["required_capability"] == "runner:codex"
    assert "required_capabilities" not in calls[0][2]
    assert calls[0][2]["idempotency_key"] == "idem-test"
    assert calls[0][2]["max_attempts"] == 2
    assert calls[0][2]["fallback_allowed"] is False
    assert calls[0][2]["source"] == {
        "kind": "kolibri_provider_gateway",
        "control_plane": "home",
        "response_id": "resp_test",
        "identity_contract": "kolibri.public-identity.v1",
        "provider_actor_node_id": "home-codex-provider",
        "provider_slot_id": "home-codex-provider",
    }
    assert calls[1][0:2] == ("GET", "/v1/tasks/KOL-RESP-resp_test")


def test_submit_fails_closed_when_completion_is_not_verified():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = json.loads(request.content)
            return httpx.Response(201, json={"task_id": body["task_id"], "state": "queued"})
        return httpx.Response(200, json=_completed(request.url.path.rsplit("/", 1)[-1], verified=False))

    client = HomeFactoryResponseClient(
        _settings(), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(HomeFactoryResponseError, match="home_factory_completion_unverified"):
        asyncio.run(
            client.submit([{"role": "user", "content": "Привет"}], run_id="bad")
        )


def test_stream_emits_factory_stages_then_verified_text_deltas():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = json.loads(request.content)
            return httpx.Response(201, json={"task_id": body["task_id"], "state": "queued"})
        return httpx.Response(200, json=_completed(request.url.path.rsplit("/", 1)[-1]))

    client = HomeFactoryResponseClient(
        _settings(), transport=httpx.MockTransport(handler)
    )

    async def collect():
        return [event async for event in client.stream([{"role": "user", "content": "Привет"}], run_id="stream")]

    events = asyncio.run(collect())
    assert events[0]["work_summary"]["stage"] == "factory_dispatch"
    assert events[1]["work_summary"]["stage"] == "factory_verified"
    assert "Проверенный ответ" == "".join(
        str(event.get("content") or "") for event in events
    )
    assert events[-1]["response_meta"]["task_id"] == "KOL-RESP-stream"
