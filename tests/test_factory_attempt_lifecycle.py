from __future__ import annotations

import http.client
import importlib.util
import json
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_control(name: str):
    path = ROOT / "ops" / "factory_control.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_max_attempts_is_total_budget_and_legacy_retries_translate_once() -> None:
    control = load_control("factory_attempt_budget_contract")

    assert control.LEASE_DURATION <= 60

    canonical = control.normalize_task({"task_id": "canonical", "max_attempts": 2})
    legacy = control.normalize_task({"task_id": "legacy", "max_retries": 1})

    assert canonical["max_attempts"] == 2
    assert legacy["max_attempts"] == 2
    assert canonical["lease_fencing_schema"] == control.LEASE_FENCING_SCHEMA
    assert canonical["fencing_token"] == 0
    assert "max_retries" not in canonical
    canonical["attempt"] = 1
    assert control.task_has_attempt_budget(canonical) is True
    canonical["attempt"] = 2
    assert control.task_has_attempt_budget(canonical) is False
    with pytest.raises(ValueError, match="fields_conflict"):
        control.normalize_task({"max_attempts": 3, "max_retries": 1})


def test_expired_first_attempt_requeues_and_second_exhausts_budget(monkeypatch) -> None:
    control = load_control("factory_attempt_recovery_contract")
    task = control.normalize_task({"task_id": "recover", "max_attempts": 2})
    task.update({
        "attempt": 1,
        "attempt_id": "recover-attempt-1",
        "fencing_token": 1,
        "state": control.STATE_RUNNING,
        "lease_owner": "worker-a:agent-a",
        "lease_until": 1,
    })
    saved: list[str] = []
    queued: list[str] = []

    class Redis:
        def __init__(self):
            self.calls = []

        def command(self, *parts):
            self.calls.append(parts)
            return 1

    redis = Redis()
    monkeypatch.setattr(control, "redis", redis)
    monkeypatch.setattr(control, "ensure_active_lease_index", lambda: None)
    monkeypatch.setattr(control, "active_lease_ids", lambda: ["recover"])
    monkeypatch.setattr(control, "all_task_ids", lambda: ["recover"])
    monkeypatch.setattr(control, "load_task", lambda _task_id: task)
    monkeypatch.setattr(control, "save_task", lambda value: saved.append(value["state"]))
    monkeypatch.setattr(control, "remove_from_queue", lambda _task_id: None)
    monkeypatch.setattr(control, "enqueue", queued.append)
    monkeypatch.setattr(control, "now_ts", lambda: 100.0)

    first = control.requeue_expired_leases()
    assert first["requeued"] == ["recover"]
    assert first["dead_lettered"] == []
    assert saved[-2:] == [control.STATE_RETRY, control.STATE_QUEUED]
    assert queued == ["recover"]

    task.update({
        "attempt": 2,
        "attempt_id": "recover-attempt-2",
        "fencing_token": 2,
        "state": control.STATE_RUNNING,
        "lease_owner": "worker-b:agent-b",
        "lease_until": 1,
    })
    second = control.requeue_expired_leases()
    assert second["requeued"] == []
    assert second["dead_lettered"] == ["recover"]
    assert task["state"] == control.STATE_DEAD


def test_late_completion_from_expired_attempt_is_http_409(monkeypatch) -> None:
    control = load_control("factory_late_completion_contract")
    task = control.normalize_task({"task_id": "late", "max_attempts": 2})
    task.update({
        "attempt": 2,
        "attempt_id": "late-attempt-2",
        "fencing_token": 2,
        "state": control.STATE_RUNNING,
        "lease_owner": "worker-b:agent-b",
        "lease_until": control.now_ts() + 60,
    })
    monkeypatch.setattr(control, "load_task", lambda _task_id: task)
    monkeypatch.setattr(control, "get_json", lambda *_args, **_kwargs: {})

    server = control.ThreadingHTTPServer(("127.0.0.1", 0), control.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        body = json.dumps({
            "attempt_id": "late-attempt-1",
            "fencing_token": 1,
            "node_id": "worker-a",
            "agent_id": "agent-a",
            "result": {"status": "completed"},
        })
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request(
            "POST",
            "/v1/tasks/late/complete",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        connection.close()

        assert response.status == 409
        assert payload["error"] == "lease_fence_rejected"
        assert payload["reason"] == "attempt_id_mismatch"
        assert task["state"] == control.STATE_RUNNING
        assert task["attempt_id"] == "late-attempt-2"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_fencing_token_allocation_is_monotonic_and_migrates_only_legacy_tasks() -> None:
    control = load_control("factory_fencing_token_allocation_contract")
    task = control.normalize_task({"task_id": "tokened", "max_attempts": 3})
    task["attempt"] = 1
    assert control.allocate_next_fencing_token(task) == 1
    task["attempt"] = 2
    assert control.allocate_next_fencing_token(task) == 2

    legacy = {"task_id": "legacy", "attempt": 4}
    assert control.is_pre_migration_fencing_task(legacy) is True
    assert control.allocate_next_fencing_token(legacy) == 4
    assert legacy["lease_fencing_schema"] == control.LEASE_FENCING_SCHEMA
    assert legacy["lease_fencing_migrated_from"] == control.LEGACY_LEASE_FENCING_COMPATIBILITY
    legacy["attempt"] = 5
    assert control.allocate_next_fencing_token(legacy) == 5


def test_lease_api_allocates_and_returns_a_new_token_on_every_attempt(monkeypatch) -> None:
    control = load_control("factory_fencing_lease_api_contract")
    current = control.normalize_task({
        "task_id": "lease-token",
        "kind": "read_only_probe",
        "max_attempts": 5,
    })
    monkeypatch.setattr(control, "get_json", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(control, "require_external_provider_actor_auth", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(control, "requeue_expired_leases", lambda: {})
    monkeypatch.setattr(
        control,
        "lease_node_eligibility",
        lambda _node_id: {
            "eligible": True,
            "lease_scope": "canonical_mesh",
            "node": {"node_id": "worker-a", "capabilities": ["read_only_probe"]},
        },
    )
    monkeypatch.setattr(control, "queue_ids", lambda: [current["task_id"]])
    monkeypatch.setattr(control, "acquire_lease_claim", lambda *_args: True)
    monkeypatch.setattr(control, "release_lease_claim", lambda *_args: None)
    monkeypatch.setattr(control, "load_task", lambda _task_id: current)
    monkeypatch.setattr(control, "compatible", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(control, "save_task", lambda value: current.update(value))
    monkeypatch.setattr(control, "remove_from_queue", lambda *_args: None)

    server = control.ThreadingHTTPServer(("127.0.0.1", 0), control.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def lease() -> tuple[int, dict]:
        host, port = server.server_address
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request(
            "POST",
            "/v1/tasks/lease",
            body=json.dumps({
                "node_id": "worker-a",
                "agent_id": "agent-a",
                "capabilities": ["read_only_probe"],
            }),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        connection.close()
        return response.status, payload

    try:
        status, first = lease()
        assert status == 200
        assert first["attempt_id"] == "lease-token-attempt-1"
        assert first["fencing_token"] == 1
        assert first["lease_fencing_schema"] == control.LEASE_FENCING_SCHEMA

        current["state"] = control.STATE_QUEUED
        current["lease_owner"] = None
        status, second = lease()
        assert status == 200
        assert second["attempt_id"] == "lease-token-attempt-2"
        assert second["fencing_token"] == 2

        current.clear()
        current.update({
            "task_id": "legacy-lease-token",
            "kind": "read_only_probe",
            "state": control.STATE_QUEUED,
            "attempt": 3,
            "max_attempts": 5,
            "envelope": {"kind": "read_only_probe"},
        })
        status, migrated = lease()
        assert status == 200
        assert migrated["attempt_id"] == "legacy-lease-token-attempt-4"
        assert migrated["fencing_token"] == 4
        assert migrated["lease_fencing_migrated_from"] == control.LEGACY_LEASE_FENCING_COMPATIBILITY
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize(
    ("suffix", "extra"),
    [
        ("heartbeat", {"state": "running"}),
        ("complete", {"result_reference": "/tmp/result.json", "result": {"status": "completed"}}),
        ("fail", {"error_type": "synthetic", "error": "bounded", "retry": False}),
    ],
)
@pytest.mark.parametrize(
    ("token_value", "reason"),
    [
        (None, "fencing_token_missing"),
        (1, "fencing_token_mismatch"),
    ],
)
def test_new_contract_mutations_reject_missing_or_stale_fencing_token(
    monkeypatch,
    suffix: str,
    extra: dict,
    token_value: int | None,
    reason: str,
) -> None:
    control = load_control(f"factory_fencing_http_{suffix}_{reason}")
    task = control.normalize_task({"task_id": "fenced-http", "max_attempts": 2})
    task.update({
        "attempt": 2,
        "attempt_id": "fenced-http-attempt-2",
        "fencing_token": 2,
        "state": control.STATE_RUNNING,
        "lease_owner": "worker-b:agent-b",
        "lease_until": control.now_ts() + 60,
    })
    monkeypatch.setattr(control, "load_task", lambda _task_id: task)
    monkeypatch.setattr(control, "get_json", lambda *_args, **_kwargs: {})

    server = control.ThreadingHTTPServer(("127.0.0.1", 0), control.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = {
            "attempt_id": task["attempt_id"],
            "node_id": "worker-b",
            "agent_id": "agent-b",
            **extra,
        }
        if token_value is not None:
            body["fencing_token"] = token_value
        host, port = server.server_address
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request(
            "POST",
            f"/v1/tasks/{task['task_id']}/{suffix}",
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        connection.close()

        assert response.status == 409
        assert payload["error"] == "lease_fence_rejected"
        assert payload["reason"] == reason
        assert payload["fencing_token"] == 2
        assert task["state"] == control.STATE_RUNNING
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
