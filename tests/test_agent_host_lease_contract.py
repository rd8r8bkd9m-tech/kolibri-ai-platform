import argparse
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_agent_host():
    spec = importlib.util.spec_from_file_location("agent_host_lease_contract", ROOT / "ops" / "agent_host.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def args_for(tmp_path):
    return argparse.Namespace(
        control_url="http://127.0.0.1:9101",
        node_id="agent-01",
        agent_id="agent-host-agent-01",
        capabilities="generic_implementation",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
        runtime_release_id="worker-release-1",
    )


def leased_task():
    return {
        "task_id": "PAIRED-LEASE-1",
        "attempt": 1,
        "attempt_id": "PAIRED-LEASE-1-attempt-1",
        "lease_id": "22a6153693dd4e439c7e6d3212bc73e1",
        "fencing_token": 1,
        "lease_slot_id": "mimo-01",
        "executor_release_id": "worker-release-1",
        "envelope": {"kind": "read_only_probe"},
    }


def test_lease_fence_is_remembered_and_sent_on_mutations(tmp_path, monkeypatch):
    agent_host = load_agent_host()

    class Host(agent_host.AgentHost):
        def __init__(self):
            super().__init__(args_for(tmp_path))
            self.posts = []

        def post(self, path, body):
            self.posts.append((path, body))
            return leased_task() if path == "/v1/tasks/lease" else body

    host = Host()
    task = host.lease()
    assert task is not None
    expected = host._active_lease_fences[task["task_id"]]
    assert expected["runtime_release_id"] == "worker-release-1"
    assert expected["slot_id"] == "mimo-01"

    monkeypatch.setattr(agent_host.time, "time", lambda: 1.0)
    host._last_node_heartbeat = 1.0
    host.task_heartbeat(task, tmp_path, None, {})
    assert all(host.posts[-1][1][key] == value for key, value in expected.items())

    host.complete(task, {"status": "completed"}, tmp_path / "result.json")
    assert all(host.posts[-1][1][key] == value for key, value in expected.items())
    assert task["task_id"] not in host._active_lease_fences


def test_lease_rejects_missing_or_wrong_release_fence(tmp_path):
    agent_host = load_agent_host()

    class MissingFence(agent_host.AgentHost):
        def post(self, path, body):
            return {"task_id": "UNFENCED", "attempt_id": "UNFENCED-attempt-1", "envelope": {}}

    with pytest.raises(agent_host.LeaseContractError, match="lease_id, fencing_token"):
        MissingFence(args_for(tmp_path)).lease()

    class WrongRelease(agent_host.AgentHost):
        def post(self, path, body):
            return {**leased_task(), "executor_release_id": "worker-release-other"}

    with pytest.raises(agent_host.LeaseContractError, match="targets runtime release"):
        WrongRelease(args_for(tmp_path)).lease()


def test_remembered_fence_cannot_change(tmp_path):
    agent_host = load_agent_host()

    class Host(agent_host.AgentHost):
        def post(self, path, body):
            return body

    host = Host(args_for(tmp_path))
    host._last_node_heartbeat = agent_host.time.time()
    task = leased_task()
    host._remember_lease_fence(task)
    task["lease_id"] = "stale"
    with pytest.raises(agent_host.LeaseContractError, match="no longer matches"):
        host.task_heartbeat(task, tmp_path, None, {})
