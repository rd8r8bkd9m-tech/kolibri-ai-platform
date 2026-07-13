"""Contract and bounded-runtime tests for the Home Codex broker."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from app.codex_cli_provider import CodexCLIError
from app.home_factory_contract import (
    HOME_CODEX_CAPABILITIES,
    HOME_CODEX_SLOT_ID,
    HomeFactoryContractError,
    build_home_codex_task,
    home_broker_heartbeat,
    home_codex_route_readiness,
    validate_home_control_plane_url,
)
from app.home_factory_orchestrator import (
    HomeBrokerSettings,
    HomeCodexBroker,
    HomeFactoryRuntimeError,
)


LIVE_PROBE = {
    "status": "live",
    "entitlement": "granted",
    "checked_at": "2026-07-13T14:00:00Z",
    "model": "account-default",
    "tests": {
        "login": {"ok": True},
        "binary": {"ok": True},
        "cwd": {"ok": True},
    },
}


def test_control_plane_has_no_default_and_rejects_legacy_authorities():
    with pytest.raises(HomeFactoryContractError, match="not_configured"):
        validate_home_control_plane_url(None)
    for value in (
        "http://10.99.0.2:9101",
        "http://10.99.0.10:9101",
        "https://main:9101",
        "https://primary:9101",
    ):
        with pytest.raises(HomeFactoryContractError, match="legacy_control_plane"):
            validate_home_control_plane_url(value)
    assert validate_home_control_plane_url("http://10.99.0.1:9101/") == "http://10.99.0.1:9101"


def test_live_probe_adds_home_slot_without_replacing_primary_agent():
    body = home_broker_heartbeat(
        {
            "node_id": "home",
            "agent_id": "home-agent-host",
            "capabilities": ["read_only_probe", "generic_implementation"],
            "runners": {"mimo": {"status": "blocked"}},
        },
        LIVE_PROBE,
    )

    assert "agent_id" not in body
    assert body["provider_broker_status"] == "live"
    assert set(HOME_CODEX_CAPABILITIES) <= set(body["capabilities"])
    assert body["runners"]["codex"]["status"] == "available"
    assert body["agent_slots"][HOME_CODEX_SLOT_ID]["status"] == "live"
    assert body["runners"]["mimo"] == {"status": "blocked"}


def test_failed_probe_removes_stale_codex_capabilities():
    body = home_broker_heartbeat(
        {
            "node_id": "home",
            "capabilities": ["read_only_probe", *HOME_CODEX_CAPABILITIES],
            "runners": {"codex": {"status": "available"}},
        },
        {
            **LIVE_PROBE,
            "status": "unavailable",
            "entitlement": "denied",
            "error_code": "codex_cli_login_required",
            "tests": {**LIVE_PROBE["tests"], "login": {"ok": False}},
        },
    )

    assert body["provider_broker_status"] == "blocked"
    assert set(HOME_CODEX_CAPABILITIES).isdisjoint(body["capabilities"])
    assert body["runners"]["codex"]["status"] == "blocked"
    assert body["agent_slots"][HOME_CODEX_SLOT_ID]["capabilities"] == []


def test_route_readiness_requires_slot_capabilities_and_live_runner():
    heartbeat = home_broker_heartbeat(
        {
            "node_id": "home",
            "capabilities": ["read_only_probe"],
            "runners": {},
        },
        LIVE_PROBE,
    )
    verdict = home_codex_route_readiness(
        {
            **heartbeat,
            "health": "online",
            "freshness": "fresh",
            "schedulable": True,
            "draining": False,
        }
    )
    assert verdict["ready"] is True
    assert verdict["missing"] == []

    heartbeat["capabilities"].remove("orchestrator")
    blocked = home_codex_route_readiness(heartbeat)
    assert blocked["ready"] is False
    assert "orchestrator" in blocked["missing"]


def test_task_envelope_binds_home_codex_and_maps_attempt_compatibility():
    envelope = build_home_codex_task(
        "Ответь на проверочный вопрос",
        task_id="KOL-HOME-CODEX-TEST",
        max_attempts=2,
    )
    assert envelope["target_node"] == "home"
    assert envelope["required_capability"] == "codex_provider_broker"
    assert envelope["required_capabilities"] == list(HOME_CODEX_CAPABILITIES)
    assert envelope["runner"] == "codex"
    assert envelope["public_model"] == "kolibri"
    assert envelope["max_attempts"] == 2
    assert envelope["max_retries"] == 1
    assert envelope["verifier_policy"]["independent_identity"] is True


class FakeCodexProvider:
    async def probe_health(self):
        return LIVE_PROBE

    async def invoke(self, messages, *, policy=None, run_id=None):
        assert messages == [{"role": "user", "content": "Сколько будет 56+67?"}]
        assert policy == {"read_only": True, "public_model": "kolibri"}
        assert run_id == "factory_KOL-HOME-CODEX-BOUND-attempt-1"
        return {
            "content": "123",
            "model": "account-default",
            "tool_events": [],
            "work_summaries": [{"stage": "answer", "status": "completed"}],
        }


def test_broker_leases_bound_task_persists_hash_and_completes(tmp_path: Path):
    calls: list[tuple[str, str, dict | None]] = []
    task = {
        "task_id": "KOL-HOME-CODEX-BOUND",
        "kind": "owner_remote_task",
        "state": "leased",
        "attempt_id": "KOL-HOME-CODEX-BOUND-attempt-1",
        "fencing_token": 7,
        "lease_owner": f"home:{HOME_CODEX_SLOT_ID}",
        "envelope": build_home_codex_task(
            "Сколько будет 56+67?",
            task_id="KOL-HOME-CODEX-BOUND",
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        if request.method == "GET" and request.url.path == "/v1/nodes/home":
            return httpx.Response(
                200,
                json={
                    "node_id": "home",
                    "agent_id": "home-agent-host",
                    "health": "online",
                    "freshness": "fresh",
                    "schedulable": True,
                    "capabilities": ["read_only_probe"],
                    "runners": {},
                },
            )
        if request.method == "POST" and request.url.path == "/v1/nodes/home/heartbeat":
            return httpx.Response(200, json=body)
        if request.method == "POST" and request.url.path == "/v1/tasks/lease":
            assert body["agent_id"] == HOME_CODEX_SLOT_ID
            assert set(body["capabilities"]) == set(HOME_CODEX_CAPABILITIES)
            return httpx.Response(200, json=task)
        if request.method == "GET" and request.url.path == "/v1/tasks/KOL-HOME-CODEX-BOUND":
            return httpx.Response(200, json=task)
        if request.method == "POST" and request.url.path.endswith("/complete"):
            assert body["result"]["response"] == "123"
            assert body["result"]["attempt_id"] == task["attempt_id"]
            assert body["result"]["fencing_token"] == 7
            assert body["agent_id"] == HOME_CODEX_SLOT_ID
            assert body["slot_id"] == HOME_CODEX_SLOT_ID
            assert body["fencing_token"] == 7
            assert body["lease_owner"] == f"home:{HOME_CODEX_SLOT_ID}"
            return httpx.Response(200, json={"task": {**task, "state": "completed"}})
        raise AssertionError(f"unexpected request {request.method} {request.url.path}")

    settings = HomeBrokerSettings(
        control_plane_url="http://10.99.0.1:9101",
        artifact_root=tmp_path,
        request_timeout_seconds=1,
        lease_heartbeat_seconds=30,
    )
    broker = HomeCodexBroker(
        settings,
        FakeCodexProvider(),
        transport=httpx.MockTransport(handler),
    )
    completed = asyncio.run(broker.run_once())

    assert completed is not None
    result = completed["result"]
    assert result["result_sha256"] == hashlib.sha256(b"123").hexdigest()
    artifact_path = Path(result["artifact"]["uri"])
    assert artifact_path.is_file()
    artifact_bytes = artifact_path.read_bytes()
    assert result["artifact"]["sha256"] == hashlib.sha256(artifact_bytes).hexdigest()
    assert any(path.endswith("/complete") for _, path, _ in calls)


class FailingProbeProvider:
    async def probe_health(self):
        raise CodexCLIError("codex_cli_probe_failed")

    async def invoke(self, messages, *, policy=None, run_id=None):
        raise AssertionError("a blocked provider must not lease or invoke")


def test_probe_failure_advertises_blocked_slot_without_leasing(tmp_path: Path):
    advertised: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        if request.method == "GET" and request.url.path == "/v1/nodes/home":
            return httpx.Response(
                200,
                json={
                    "node_id": "home",
                    "health": "online",
                    "capabilities": ["read_only_probe", *HOME_CODEX_CAPABILITIES],
                    "runners": {"codex": {"status": "available"}},
                },
            )
        if request.method == "POST" and request.url.path == "/v1/nodes/home/heartbeat":
            advertised.append(body)
            return httpx.Response(200, json=body)
        if request.url.path == "/v1/tasks/lease":
            raise AssertionError("blocked health must prevent leasing")
        raise AssertionError(f"unexpected request {request.method} {request.url.path}")

    broker = HomeCodexBroker(
        HomeBrokerSettings(
            control_plane_url="http://10.99.0.1:9101",
            artifact_root=tmp_path,
            request_timeout_seconds=1,
        ),
        FailingProbeProvider(),
        transport=httpx.MockTransport(handler),
    )

    assert asyncio.run(broker.run_once()) is None
    assert len(advertised) == 1
    assert advertised[0]["provider_broker_status"] == "blocked"
    assert set(HOME_CODEX_CAPABILITIES).isdisjoint(advertised[0]["capabilities"])
    assert advertised[0]["agent_slots"][HOME_CODEX_SLOT_ID]["status"] == "blocked"
    assert advertised[0]["runners"]["codex"]["error_type"] == "codex_cli_probe_failed"


def test_provider_attempt_failure_requests_bounded_task_retry(tmp_path: Path):
    task = {
        "task_id": "KOL-HOME-CODEX-RETRY",
        "kind": "owner_remote_task",
        "state": "leased",
        "attempt_id": "KOL-HOME-CODEX-RETRY-attempt-1",
        "fencing_token": 3,
        "lease_owner": f"home:{HOME_CODEX_SLOT_ID}",
        "envelope": build_home_codex_task(
            "Проверка повторной попытки",
            task_id="KOL-HOME-CODEX-RETRY",
        ),
    }
    failure_bodies: list[dict] = []

    class FailingInvokeProvider(FakeCodexProvider):
        async def invoke(self, messages, *, policy=None, run_id=None):
            raise CodexCLIError("codex_cli_unavailable")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        if request.method == "GET" and request.url.path == "/v1/nodes/home":
            return httpx.Response(
                200,
                json={
                    "node_id": "home",
                    "health": "online",
                    "capabilities": ["read_only_probe"],
                    "runners": {},
                },
            )
        if request.method == "POST" and request.url.path == "/v1/nodes/home/heartbeat":
            return httpx.Response(200, json=body)
        if request.method == "POST" and request.url.path == "/v1/tasks/lease":
            return httpx.Response(200, json=task)
        if request.method == "POST" and request.url.path.endswith("/fail"):
            failure_bodies.append(body)
            return httpx.Response(200, json={"task": {**task, "state": "retry_wait"}})
        raise AssertionError(f"unexpected request {request.method} {request.url.path}")

    broker = HomeCodexBroker(
        HomeBrokerSettings(
            control_plane_url="http://10.99.0.1:9101",
            artifact_root=tmp_path,
            request_timeout_seconds=1,
            lease_heartbeat_seconds=30,
        ),
        FailingInvokeProvider(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(CodexCLIError, match="codex_cli_unavailable"):
        asyncio.run(broker.run_once())
    assert len(failure_bodies) == 1
    assert failure_bodies[0]["retry"] is True
    assert failure_bodies[0]["error_type"] == "codex_cli_unavailable"
    assert failure_bodies[0]["agent_id"] == HOME_CODEX_SLOT_ID
    assert failure_bodies[0]["slot_id"] == HOME_CODEX_SLOT_ID
    assert failure_bodies[0]["fencing_token"] == 3
    assert broker._advertisement is None


def test_lease_heartbeat_recovers_after_transient_control_plane_errors(tmp_path: Path):
    settings = HomeBrokerSettings(
        control_plane_url="http://10.99.0.1:9101",
        artifact_root=tmp_path,
        lease_heartbeat_seconds=0.01,
        retry_backoff_initial_seconds=0.001,
        retry_backoff_max_seconds=0.002,
    )
    broker = HomeCodexBroker(settings, FakeCodexProvider())
    stop = asyncio.Event()
    attempts = 0

    async def heartbeat_task(task_id, attempt_id, fencing_token):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise HomeFactoryRuntimeError("home_control_plane_unreachable")
        stop.set()
        return {"ok": True}

    broker.control.heartbeat_task = heartbeat_task  # type: ignore[method-assign]

    asyncio.run(
        asyncio.wait_for(
            broker._lease_heartbeat("task-1", "attempt-1", 1, stop),
            timeout=1,
        )
    )
    assert attempts == 3


def test_run_forever_retries_transient_cycles_with_bounded_backoff(tmp_path: Path):
    class RecoveringBroker(HomeCodexBroker):
        def __init__(self):
            super().__init__(
                HomeBrokerSettings(
                    control_plane_url="http://10.99.0.1:9101",
                    artifact_root=tmp_path,
                    idle_poll_seconds=60,
                    retry_backoff_initial_seconds=0.001,
                    retry_backoff_max_seconds=0.002,
                ),
                FakeCodexProvider(),
            )
            self.calls = 0
            self.recovered = asyncio.Event()

        async def run_once(self):
            self.calls += 1
            if self.calls == 1:
                raise HomeFactoryRuntimeError("home_control_plane_unreachable")
            if self.calls == 2:
                raise CodexCLIError("codex_cli_unavailable")
            self.recovered.set()
            return None

    async def scenario():
        broker = RecoveringBroker()
        assert broker.retry_delay(1) == 0.001
        assert broker.retry_delay(2) == 0.002
        assert broker.retry_delay(1000) == 0.002
        daemon = asyncio.create_task(broker.run_forever())
        await asyncio.wait_for(broker.recovered.wait(), timeout=1)
        daemon.cancel()
        with pytest.raises(asyncio.CancelledError):
            await daemon
        return broker.calls

    assert asyncio.run(scenario()) >= 3


def test_systemd_unit_runs_owner_session_broker_with_home_only_contract():
    backend_root = Path(__file__).resolve().parents[2]
    unit = (
        backend_root / "ops/systemd/kolibri-home-codex-broker.service"
    ).read_text(encoding="utf-8")
    lines = {line.strip() for line in unit.splitlines() if line.strip()}

    assert "User=ladik" in lines
    assert "Group=ladik" in lines
    assert "WorkingDirectory=/opt/kolibri-ai/canary-r9/backend" in lines
    assert (
        "ExecStart=/opt/kolibri-ai/canary-r9/backend/.venv/bin/python -B -m "
        "app.home_factory_orchestrator"
    ) in lines
    assert "EnvironmentFile=/etc/kolibri/home-control-plane.env" in lines
    assert not any(
        line.startswith("Environment=KOLIBRI_CONTROL_PLANE_URL=") for line in lines
    )
    assert "Environment=HOME=/home/ladik" in lines
    assert "Environment=CODEX_HOME=/home/ladik/.codex" in lines
    assert "StateDirectory=kolibri/home-codex-broker" in lines
    assert "Restart=always" in lines
    assert "NoNewPrivileges=yes" in lines
    assert "ProtectSystem=strict" in lines
    assert "ProtectHome=read-only" in lines
    assert "EnvironmentFile=/etc/kolibri/backend.env" not in lines
    assert not any(line.startswith("Environment=OPENAI_API_KEY=") for line in lines)
    assert not any(line.startswith("Environment=TELEGRAM_BOT_TOKEN=") for line in lines)
