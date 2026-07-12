import argparse
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def agent_args(tmp_path):
    manifest = tmp_path / "mesh-peers.json"
    manifest.write_text(
        json.dumps({"peers": [{"node_id": "home", "mesh_ip": "10.99.0.1"}]}),
        encoding="utf-8",
    )
    return argparse.Namespace(
        control_url="http://10.99.0.1:9101",
        control_urls="http://10.99.0.1:9101",
        mesh_membership_manifest=str(manifest),
        node_id="agent-02",
        agent_id="agent-host-agent-02",
        capabilities="generic_implementation,read_only_probe",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
    )


def test_task_heartbeat_keeps_busy_node_fresh(tmp_path, monkeypatch):
    agent_host = load_module("agent_host_execution_contract", ROOT / "ops" / "agent_host.py")

    class Host(agent_host.AgentHost):
        def __init__(self, args):
            super().__init__(args)
            self.posts = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

    host = Host(agent_args(tmp_path))
    monkeypatch.setattr(agent_host.time, "time", lambda: 100.0)
    host._last_node_heartbeat = 0.0
    task = {
        "task_id": "LONG-RUN-1",
        "attempt_id": "LONG-RUN-1-attempt-2",
        "fencing_token": 2,
    }
    host.task_heartbeat(task, tmp_path, None, {})

    assert host.posts[0][0] == "/v1/nodes/agent-02/heartbeat"
    assert host.posts[0][1]["active_task"] == "LONG-RUN-1"
    assert host.posts[1][0] == "/v1/tasks/LONG-RUN-1/heartbeat"
    assert host.posts[1][1]["fencing_token"] == 2


def test_multiple_control_plane_authorities_are_rejected(tmp_path):
    agent_host = load_module("agent_host_home_only_contract", ROOT / "ops" / "agent_host.py")
    args = agent_args(tmp_path)
    args.control_urls = "http://home-control:9101,http://legacy-control:9101"

    with pytest.raises(RuntimeError, match="multiple_control_plane_authorities_forbidden"):
        agent_host.AgentHost(args)


def test_agent_host_rejects_heartbeat_interval_above_ten_seconds(tmp_path):
    agent_host = load_module("agent_host_heartbeat_contract", ROOT / "ops" / "agent_host.py")
    args = agent_args(tmp_path)
    args.heartbeat_interval = 11

    with pytest.raises(RuntimeError, match="between_1_and_10_seconds"):
        agent_host.AgentHost(args)


def test_agent_host_fences_heartbeat_completion_and_failure(tmp_path):
    agent_host = load_module("agent_host_fencing_contract", ROOT / "ops" / "agent_host.py")

    class Host(agent_host.AgentHost):
        def __init__(self, args):
            super().__init__(args)
            self.posts = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

    host = Host(agent_args(tmp_path))
    host._last_node_heartbeat = agent_host.time.time()
    task = {
        "task_id": "FENCED-1",
        "attempt_id": "FENCED-1-attempt-2",
        "fencing_token": 2,
    }
    host.task_heartbeat(task, tmp_path, None, {})
    host.complete(task, {"status": "completed"}, tmp_path / "result.json")
    host.fail(task, "test", "failed", None, None, retry=False)

    for _, body in host.posts:
        assert body["attempt_id"] == "FENCED-1-attempt-2"
        assert body["fencing_token"] == 2
        assert body["node_id"] == "agent-02"
        assert body["agent_id"] == "agent-host-agent-02"
    assert host.posts[1][1]["result"]["fencing_token"] == 2


def test_registered_nodes_are_batched_and_stale_nodes_are_not_routable(tmp_path, monkeypatch):
    manifest = tmp_path / "fleet-peers.json"
    manifest.write_text(
        json.dumps({
            "peers": [
                {"node_id": "home", "mesh_ip": "10.99.0.1"},
                {"node_id": "fresh", "mesh_ip": "10.99.0.2"},
                {"node_id": "stale", "mesh_ip": "10.99.0.3"},
            ]
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("KOLIBRI_MESH_MEMBERSHIP_MANIFEST", str(manifest))
    control = load_module("factory_control_execution_contract", ROOT / "ops" / "factory_control.py")
    now = control.now_ts()

    class FakeRedis:
        def __init__(self):
            self.calls = []

        def command(self, *parts):
            self.calls.append(parts)
            if parts[:2] == ("SMEMBERS", control.key("node_ids")):
                return ["fresh", "stale"]
            if parts[0] == "MGET" and "node:" in parts[1]:
                fresh_at = control.datetime.fromtimestamp(now, control.timezone.utc).isoformat()
                stale_at = control.datetime.fromtimestamp(now - 3600, control.timezone.utc).isoformat()
                return [
                    f'{{"node_id":"fresh","health":"online","heartbeat_at":"{fresh_at}","capabilities":["build"]}}',
                    f'{{"node_id":"stale","health":"online","heartbeat_at":"{stale_at}","capabilities":["build"]}}',
                ]
            if parts[0] == "MGET":
                return [None, None]
            raise AssertionError(parts)

    fake = FakeRedis()
    monkeypatch.setattr(control, "redis", fake)
    nodes = control.registered_nodes()

    assert len(fake.calls) == 3
    assert {node["node_id"]: node["health"] for node in nodes} == {
        "home": "quarantined",
        "fresh": "online",
        "stale": "stale",
    }
    route = control.fabric_route(target_node="stale", required_capability="build", registered_nodes=nodes)
    assert route["status"] == "blocked"
    assert route["fallback_nodes"] == ["fresh"]


def test_save_task_maintains_bounded_active_lease_index(monkeypatch):
    control = load_module("factory_control_lease_index_contract", ROOT / "ops" / "factory_control.py")

    class FakeRedis:
        def __init__(self):
            self.calls = []

        def command(self, *parts):
            self.calls.append(parts)
            return 1

    fake = FakeRedis()
    monkeypatch.setattr(control, "redis", fake)
    monkeypatch.setattr(control, "set_json", lambda *_args: None)

    task = {"task_id": "LEASE-1", "state": control.STATE_RUNNING}
    control.save_task(task)
    assert ("SADD", control.key("active_lease_ids"), "LEASE-1") in fake.calls

    fake.calls.clear()
    task["state"] = control.STATE_COMPLETED
    control.save_task(task)
    assert ("SREM", control.key("active_lease_ids"), "LEASE-1") in fake.calls


def test_lease_claim_and_attempt_fence_prevent_duplicate_or_late_writes(monkeypatch):
    control = load_module("factory_control_fencing_contract", ROOT / "ops" / "factory_control.py")

    class FakeRedis:
        def __init__(self):
            self.calls = []

        def command(self, *parts):
            self.calls.append(parts)
            return "OK" if parts[0] == "SET" else 1

    fake = FakeRedis()
    monkeypatch.setattr(control, "redis", fake)
    monkeypatch.setattr(control, "REQUIRE_LEASE_FENCING", True)

    assert control.acquire_lease_claim("TASK-1", "claim-a") is True
    control.release_lease_claim("TASK-1", "claim-a")
    assert fake.calls[0] == (
        "SET",
        control.lease_claim_key("TASK-1"),
        "claim-a",
        "NX",
        "EX",
        control.LEASE_CLAIM_TTL,
    )
    assert fake.calls[1][0] == "EVAL"
    assert "redis.call('get'" in fake.calls[1][1]

    task = {
        "task_id": "TASK-1",
        "attempt_id": "TASK-1-attempt-3",
        "lease_fencing_schema": control.LEASE_FENCING_SCHEMA,
        "fencing_token": 3,
        "lease_owner": "agent-02:agent-host-agent-02",
    }
    valid = {
        "attempt_id": "TASK-1-attempt-3",
        "fencing_token": 3,
        "node_id": "agent-02",
        "agent_id": "agent-host-agent-02",
    }
    assert control.lease_fence_error(task, valid) is None
    assert control.lease_fence_error(task, {**valid, "attempt_id": "TASK-1-attempt-2"}) == "attempt_id_mismatch"
    assert control.lease_fence_error(task, {key: value for key, value in valid.items() if key != "fencing_token"}) == "fencing_token_missing"
    assert control.lease_fence_error(task, {**valid, "fencing_token": 2}) == "fencing_token_mismatch"
    assert control.lease_fence_error(task, {**valid, "node_id": "agent-03"}) == "lease_node_mismatch"
    assert control.lease_fence_error(task, {**valid, "agent_id": "other"}) == "lease_agent_mismatch"

    legacy = {
        "task_id": "TASK-LEGACY",
        "attempt_id": "TASK-LEGACY-attempt-1",
        "lease_owner": "agent-02:agent-host-agent-02",
    }
    legacy_body = {
        "attempt_id": legacy["attempt_id"],
        "node_id": "agent-02",
        "agent_id": "agent-host-agent-02",
    }
    assert control.is_pre_migration_fencing_task(legacy) is True
    assert control.lease_fence_error(legacy, legacy_body) is None


def test_unverified_completion_cannot_enter_terminal_completed_state():
    control = load_module("factory_control_completion_truth_contract", ROOT / "ops" / "factory_control.py")

    insufficient = {"task_id": "TASK-LOW", "truth_gate": {"verdict": "not_proven"}}
    gated = control.enforce_completion_truth_state(insufficient, control.STATE_COMPLETED)
    assert gated["state"] == control.STATE_WAITING_REVIEW
    assert gated["error_type"] == "completion_not_verified"

    verified = {"task_id": "TASK-OK", "truth_gate": {"verdict": "true"}, "error": "old"}
    completed = control.enforce_completion_truth_state(verified, control.STATE_COMPLETED)
    assert completed["state"] == control.STATE_COMPLETED
    assert completed["error"] is None
