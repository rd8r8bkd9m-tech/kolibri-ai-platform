import argparse
import importlib.util
import json
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


def test_visible_mimo_session_uses_limited_visible_session_permissions():
    control = load_control()
    task = control.normalize_task(
        {
            "task_id": "VISIBLE-MIMO-1",
            "kind": "visible_mimo_session",
            "required_capability": "visible_mimo_session",
        }
    )

    assert task["permission_pack"] == "visible_session"
    assert set(task["required_permissions"]) == {"read_system", "shell", "write_artifacts"}
    assert control.task_requires_deliverable_evidence(task) is True
    assert (
        control.compatible(
            task,
            "home",
            ["visible_mimo_session"],
            permissions=["read_system", "shell", "write_artifacts"],
        )
        is True
    )
    assert control.compatible(task, "home", ["read_only_probe"], permissions=["read_system"]) is False


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


def test_summarize_nodes_deduplicates_mesh_shadows_and_hostname_twins():
    control = load_control()
    nodes = [
        {
            "node_id": "home",
            "hostname": "plastilin",
            "fresh": True,
            "draining": False,
            "capabilities": ["generic_implementation"],
            "heartbeat_at": "2026-06-29T06:00:00+00:00",
        },
        {
            "node_id": "home-live",
            "hostname": "plastilin",
            "fresh": True,
            "draining": True,
            "capabilities": ["generic_implementation"],
            "heartbeat_at": "2026-06-29T06:01:00+00:00",
        },
        {
            "node_id": "mesh-home",
            "hostname": "home",
            "fresh": False,
            "draining": False,
            "capabilities": ["mesh_node"],
            "heartbeat_at": "2026-06-29T05:00:00+00:00",
        },
        {
            "node_id": "server-kfrm",
            "hostname": "server-kfrm",
            "fresh": False,
            "draining": False,
            "capabilities": ["generic_implementation"],
            "heartbeat_at": "2026-06-29T05:00:00+00:00",
        },
        {
            "node_id": "mesh-server-kfrm",
            "hostname": "server-kfrm",
            "fresh": False,
            "draining": False,
            "capabilities": ["mesh_node"],
            "heartbeat_at": "2026-06-29T05:01:00+00:00",
        },
        {
            "node_id": "new",
            "hostname": "kolibri-worker-backup",
            "fresh": True,
            "draining": False,
            "capabilities": ["review"],
            "heartbeat_at": "2026-06-29T06:02:00+00:00",
        },
    ]

    summary = control.summarize_nodes(nodes)

    assert summary["registered_nodes"] == 6
    assert summary["canonical_nodes"] == 3
    assert summary["fresh_nodes"] == 3
    assert summary["fresh_non_draining_nodes"] == 2
    assert summary["fresh_canonical_nodes"] == 2
    assert summary["fresh_canonical_generic_implementation_nodes"] == 1
    assert summary["mesh_shadow_duplicates"] == 2
    assert summary["duplicate_hostname_groups"] == 2
    assert summary["duplicate_hostnames"]["plastilin"] == ["home", "home-live"]
    assert summary["mesh_shadow_duplicate_nodes"] == [
        {"node_id": "mesh-home", "shadows": "home"},
        {"node_id": "mesh-server-kfrm", "shadows": "server-kfrm"},
    ]


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


def test_agent_host_visible_mimo_session_runner_builds_openvt_artifact(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    project = tmp_path / "repo"
    project.mkdir()
    monkeypatch.setattr(
        agent_host.shutil,
        "which",
        lambda name: {"mimo": "/usr/local/bin/mimo", "openvt": "/usr/bin/openvt"}.get(name),
    )
    monkeypatch.setattr(agent_host.os, "geteuid", lambda: 0)

    class Completed:
        returncode = 0

    def fake_run(command, cwd, stdout, stderr, text):
        del cwd, stderr, text
        assert command[:3] == ["ps", "-t", "tty9"]
        stdout.write(b"USER PID COMMAND\nladik 123 mimo --trust repo\n")
        return Completed()

    monkeypatch.setattr(agent_host.subprocess, "run", fake_run)

    class Host(agent_host.AgentHost):
        def __init__(self, args):
            super().__init__(args)
            self.posts = []
            self.commands = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

        def run_command(self, command, cwd, stdout_path, stderr_path, task, branch, logs, env=None, command_label=None):
            del cwd, task, branch, logs, env, command_label
            self.commands.append(command)
            stdout_path.write_text("$ openvt\n", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")

    args = argparse.Namespace(
        control_url="http://127.0.0.1:9101",
        control_urls="http://127.0.0.1:9101",
        node_id="home",
        agent_id="agent-home",
        capabilities="visible_mimo_session",
        permissions="read_system,shell,write_artifacts",
        permission_packs="visible_session",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
    )
    host = Host(args)
    task = {
        "task_id": "VISIBLE-MIMO-1",
        "attempt": 1,
        "attempt_id": "VISIBLE-MIMO-1-attempt-1",
        "envelope": {
            "kind": "visible_mimo_session",
            "session_name": "kolibri-visible-demo",
            "tty_number": 9,
            "project_path": str(project),
            "run_user": "ladik",
        },
    }

    result = host.run_visible_mimo_session(task)

    assert host.commands
    assert host.commands[0][:6] == ["/usr/bin/openvt", "-f", "-c", "9", "-s", "--"]
    assert result["kind"] == "visible_mimo_session"
    assert result["tty_number"] == 9
    assert result["project_path"] == str(project)
    assert result["artifacts"]
    assert result["checks"] == ["ps -t tty9 -o user,pid,ppid,stat,pcpu,pmem,etime,args"]
    assert Path(result["result_path"]).exists()
    assert any(path.endswith("/heartbeat") for path, _body in host.posts)


def test_generic_runner_falls_back_to_codex_when_mimo_returns_empty_text(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    monkeypatch.setenv("KOLIBRI_MIMO_COMMAND", "chat")
    monkeypatch.setattr(agent_host.shutil, "which", lambda name: f"/usr/bin/{name}" if name in {"mimo", "codex"} else None)

    class Host(agent_host.AgentHost):
        def __init__(self, args):
            super().__init__(args)
            self.posts = []
            self.commands = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

        def run_command(self, command, cwd, stdout_path, stderr_path, task, branch, logs, env=None, command_label=None):
            del cwd, task, branch, logs, env
            self.commands.append((command, command_label))
            if command[0] == "/usr/bin/mimo":
                stdout_path.write_text("$ mimo\n", encoding="utf-8")
                stderr_path.write_text("", encoding="utf-8")
                return
            with stdout_path.open("a", encoding="utf-8") as stdout:
                stdout.write(json.dumps({"msg": {"type": "agent_message", "message": "Codex fallback completed."}}) + "\n")
            stderr_path.write_text("", encoding="utf-8")

    args = argparse.Namespace(
        control_url="http://127.0.0.1:9101",
        control_urls="http://127.0.0.1:9101",
        node_id="node-a",
        agent_id="agent-node-a",
        capabilities="generic_implementation",
        permissions="read_repo,write_worktree",
        permission_packs="full_autonomy",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
    )
    host = Host(args)
    stdout_path = tmp_path / "stdout.log"
    stderr_path = tmp_path / "stderr.log"

    response = host.run_generic_ai_runner(
        "mimo",
        "do work",
        tmp_path,
        stdout_path,
        stderr_path,
        {"task_id": "AUTO-FALLBACK"},
        "agent/AUTO-FALLBACK/generic",
        {"stdout": str(stdout_path), "stderr": str(stderr_path)},
    )

    assert response == "Codex fallback completed."
    assert [command[0][0] for command in host.commands] == ["/usr/bin/mimo", "/usr/bin/codex"]
    assert host.commands[0][0][:3] == ["/usr/bin/mimo", "chat", "--message"]
    assert host.commands[0][0][-2:] == ["--json", "--no-stream"]
    assert host.commands[0][1] == "/usr/bin/mimo chat --message <prompt> --json --no-stream"
    assert "retrying with codex fallback" in stdout_path.read_text(encoding="utf-8")


def test_agent_host_failure_payload_marks_empty_runner_response(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    monkeypatch.setattr(agent_host.shutil, "which", lambda name: "/usr/bin/mimo" if name == "mimo" else None)

    class Host(agent_host.AgentHost):
        def __init__(self, args):
            super().__init__(args)
            self.posts = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

        def run_command(self, command, cwd, stdout_path, stderr_path, task, branch, logs, env=None, command_label=None):
            del command, cwd, task, branch, logs, env
            stdout_path.write_text(f"$ {command_label}\n", encoding="utf-8")
            stderr_path.write_text("runner exited with no text\n", encoding="utf-8")

        def run_generic_implementation(self, task):
            worktree, artifact_dir, logs = self.prepare_dirs(task)
            stdout_path = Path(logs["stdout"])
            stderr_path = Path(logs["stderr"])
            self.run_json_text_command(
                ["/usr/bin/mimo", "chat", "--message", "<prompt>", "--json", "--no-stream"],
                "/usr/bin/mimo chat --message <prompt> --json --no-stream",
                "mimo",
                worktree,
                stdout_path,
                stderr_path,
                task,
                None,
                logs,
            )

    args = argparse.Namespace(
        control_url="http://127.0.0.1:9101",
        control_urls="http://127.0.0.1:9101",
        node_id="node-a",
        agent_id="agent-node-a",
        capabilities="generic_implementation",
        permissions="read_repo,write_worktree",
        permission_packs="full_autonomy",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
    )
    host = Host(args)
    task = {
        "task_id": "AUTO-EMPTY",
        "kind": "generic_implementation",
        "attempt": 1,
        "attempt_id": "AUTO-EMPTY-attempt-1",
        "max_retries": 2,
        "envelope": {"kind": "generic_implementation"},
    }

    host.run_task(task)

    fail_posts = [(path, body) for path, body in host.posts if path.endswith("/fail")]
    assert len(fail_posts) == 1
    _, fail_body = fail_posts[0]
    assert fail_body["error_type"] == "runner_empty_response"
    assert fail_body["retry"] is True
    assert fail_body["result"]["error_type"] == "runner_empty_response"
    assert "stdout_tail" in fail_body["result"]
    assert "stderr_tail" in fail_body["result"]
    result_path = Path(fail_body["result_reference"])
    written = json.loads(result_path.read_text(encoding="utf-8"))
    assert written["error_type"] == "runner_empty_response"
    assert written["stderr_tail"] == "runner exited with no text\n"
