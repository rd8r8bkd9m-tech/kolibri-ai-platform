import argparse
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_control():
    return load_module("factory_control", ROOT / "ops" / "factory_control.py")


def load_agent_host():
    return load_module("agent_host", ROOT / "ops" / "agent_host.py")


def test_owner_remote_task_defaults_to_full_autonomy_required_permissions():
    control = load_control()

    task = control.normalize_task({"task_id": "AUTO-1", "kind": "owner_remote_task"})
    full_autonomy = set(control.PERMISSION_PACKS["full_autonomy"])

    assert task["permission_pack"] == "full_autonomy"
    assert set(task["required_permissions"]) == full_autonomy
    assert set(control.task_required_permissions(task["envelope"])) == full_autonomy


def test_compatible_requires_required_permissions_from_capability_or_permissions_list():
    control = load_control()
    task = control.normalize_task(
        {
            "task_id": "AUTO-2",
            "kind": "generic_implementation",
            "required_permissions": ["read_repo", "write_worktree"],
        }
    )

    assert control.compatible(task, "node-a", ["generic_implementation"]) is False
    assert control.compatible(task, "node-a", ["generic_implementation", "permission:read_repo"]) is False
    assert (
        control.compatible(
            task,
            "node-a",
            ["generic_implementation", "permission:read_repo", "permission:write_worktree"],
        )
        is True
    )
    assert (
        control.compatible(
            task,
            "node-a",
            ["generic_implementation"],
            permissions=["read_repo", "write_worktree"],
        )
        is True
    )


def test_decorate_node_marks_stale_heartbeats_without_downgrading_fresh_nodes():
    control = load_control()
    current = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)

    stale = control.decorate_node(
        {
            "node_id": "stale-node",
            "health": "online",
            "heartbeat_at": (current - timedelta(seconds=control.NODE_STALE_AFTER + 5)).isoformat(),
        },
        current=current,
    )
    fresh = control.decorate_node(
        {
            "node_id": "fresh-node",
            "health": "online",
            "heartbeat_at": (current - timedelta(seconds=5)).isoformat(),
        },
        current=current,
    )

    assert stale["fresh"] is False
    assert stale["health"] == "stale"
    assert stale["heartbeat_age_seconds"] > control.NODE_STALE_AFTER
    assert fresh["fresh"] is True
    assert fresh["health"] == "online"


def test_summarize_tasks_counts_states_without_full_task_payloads():
    control = load_control()
    noisy_payload = {"prompt": "x" * 1000, "private": True}
    tasks = [
        {
            "task_id": "AUTO-Q",
            "kind": "owner_remote_task",
            "state": control.STATE_QUEUED,
            "envelope": noisy_payload,
            "result": noisy_payload,
        },
        {
            "task_id": "AUTO-R",
            "kind": "generic_implementation",
            "state": control.STATE_RUNNING,
            "permission_pack": "full_autonomy",
            "required_permissions": ["read_repo"],
            "envelope": {"target_node": "node-a", **noisy_payload},
            "result": noisy_payload,
        },
        {
            "task_id": "AUTO-DONE",
            "kind": "generic_implementation",
            "state": control.STATE_COMPLETED,
            "envelope": noisy_payload,
            "result": noisy_payload,
        },
    ]

    summary = control.summarize_tasks(tasks)

    assert summary["total"] == 3
    assert summary["states"] == {control.STATE_QUEUED: 1, control.STATE_RUNNING: 1, control.STATE_COMPLETED: 1}
    assert "tasks" not in summary
    assert len(summary["active"]) == 1
    assert summary["active"][0]["task_id"] == "AUTO-R"
    assert summary["active"][0]["required_permissions"] == ["read_repo"]
    assert "envelope" not in summary["active"][0]
    assert "result" not in summary["active"][0]


def test_agent_host_register_heartbeat_and_lease_include_permissions_payloads(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    monkeypatch.setattr(agent_host, "machine_stats", lambda: {"cpu": 2, "ram": {}, "disk": {}})

    class CapturingHost(agent_host.AgentHost):
        def __init__(self, args):
            super().__init__(args)
            self.posts = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

    args = argparse.Namespace(
        control_url="http://127.0.0.1:9101",
        control_urls="http://127.0.0.1:9101",
        node_id="node-a",
        agent_id="agent-node-a",
        capabilities="generic_implementation",
        permissions="read_repo,write_worktree",
        permission_packs="full_autonomy,implementation",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
    )
    host = CapturingHost(args)

    host.register()
    host.node_heartbeat(active_task="AUTO-R")
    host.lease()

    register_body = next(body for path, body in host.posts if path == "/v1/nodes/register")
    heartbeat_body = next(body for path, body in host.posts if path.endswith("/heartbeat"))
    lease_body = next(body for path, body in host.posts if path == "/v1/tasks/lease")

    for body in (register_body, heartbeat_body, lease_body):
        assert set(body["permissions"]) == {"read_repo", "write_worktree"}
        assert set(body["permission_packs"]) == {"full_autonomy", "implementation"}
