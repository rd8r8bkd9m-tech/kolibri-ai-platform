import argparse
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_agent_host():
    spec = importlib.util.spec_from_file_location("agent_host", ROOT / "ops" / "agent_host.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_args(tmp_path):
    return argparse.Namespace(
        control_url="http://127.0.0.1:9101",
        node_id="primary-candidate",
        agent_id="agent-host-primary",
        capabilities="generic_implementation",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
    )


def make_direct_task(task_id, objective="repair the contract"):
    return {
        "task_id": task_id,
        "kind": "owner_remote_task",
        "attempt": 1,
        "attempt_id": f"{task_id}-attempt-1",
        "max_retries": 1,
        "envelope": {
            "kind": "owner_remote_task",
            "runner": "mimo",
            "objective": objective,
            "branch": f"agent/{task_id}/impl/direct-mimo",
            "base_ref": "origin/main",
        },
    }


def artifact_files(tmp_path, task_id):
    artifact_dir = tmp_path / "artifacts" / task_id / f"{task_id}-attempt-1"
    return sorted(path.name for path in artifact_dir.iterdir() if path.is_file())


def test_direct_mimo_stdout_useful_json_completes_with_non_empty_response(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    monkeypatch.setattr(agent_host.shutil, "which", lambda name: "/usr/bin/mimo" if name == "mimo" else None)

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
            stdout_path.write_text(
                f"$ {command_label}\n"
                + json.dumps(
                    {
                        "status": "completed",
                        "branch": "agent/P0/impl/direct-mimo",
                        "pull_request_url": "https://github.example/pull/1",
                        "tests": ["pytest -q tests/test_agent_host_direct_mimo.py"],
                        "blockers": [],
                        "next_action": "request central review",
                        "changed_files": ["ops/agent_host.py", "tests/test_agent_host_direct_mimo.py"],
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            stderr_path.write_text("", encoding="utf-8")

    host = Host(make_args(tmp_path))
    host.run_task(make_direct_task("MIMO-SUCCESS"))

    command, command_label = host.commands[0]
    assert command[command.index("--model") + 1] == "mimo/mimo-auto"
    assert "--dangerously-skip-permissions" in command
    assert Path(command[command.index("--dir") + 1]).is_relative_to(tmp_path / "work")
    assert "--password" not in command
    assert "repair the contract" not in command_label

    complete_posts = [(path, body) for path, body in host.posts if path.endswith("/complete")]
    fail_posts = [(path, body) for path, body in host.posts if path.endswith("/fail")]
    assert len(complete_posts) == 1
    assert fail_posts == []
    result = complete_posts[0][1]["result"]
    assert result["status"] == "completed"
    assert result["runner"] == "mimo"
    assert result["runner_contract"]["cli_contract"] == "mimo-auto25-no-user-auth-v1"
    assert result["response"]
    assert result["branch"] == "agent/P0/impl/direct-mimo"
    assert result["pull_request_url"] == "https://github.example/pull/1"
    assert result["tests"] == ["pytest -q tests/test_agent_host_direct_mimo.py"]
    assert result["blockers"] == []
    assert result["next_action"] == "request central review"
    assert artifact_files(tmp_path, "MIMO-SUCCESS") == [
        "artifact-manifest.json",
        "result.json",
        "runner-contract.json",
        "stderr.log",
        "stdout.log",
    ]
    runner_contract_path = tmp_path / "artifacts" / "MIMO-SUCCESS" / "MIMO-SUCCESS-attempt-1" / "runner-contract.json"
    runner_contract = json.loads(runner_contract_path.read_text(encoding="utf-8"))
    assert runner_contract["model"] == "mimo/mimo-auto"
    assert runner_contract["user_authorization_required"] is False


def test_direct_mimo_http_401_is_runner_auth_failed_without_prompt_leak(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    monkeypatch.setattr(agent_host.shutil, "which", lambda name: "/usr/bin/mimo" if name == "mimo" else None)
    secret_prompt = "repair with owner private context"

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
            stderr_path.write_text("request failed: HTTP 401 Unauthorized\n", encoding="utf-8")
            raise RuntimeError(f"command failed with rc=1: {command_label}")

    host = Host(make_args(tmp_path))
    host.run_task(make_direct_task("MIMO-401", secret_prompt))

    fail_posts = [(path, body) for path, body in host.posts if path.endswith("/fail")]
    assert len(fail_posts) == 1
    fail_body = fail_posts[0][1]
    assert fail_body["error_type"] == "runner_auth_failed"
    assert fail_body["retry"] is False
    service_payload = json.dumps(fail_body, ensure_ascii=False)
    assert secret_prompt not in service_payload
    assert "HTTP 401" in service_payload
    assert artifact_files(tmp_path, "MIMO-401") == [
        "artifact-manifest.json",
        "result.json",
        "runner-contract.json",
        "stderr.log",
        "stdout.log",
    ]


def test_direct_mimo_http_403_illegal_access_is_policy_blocked_without_prompt_leak(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    monkeypatch.setattr(agent_host.shutil, "which", lambda name: "/usr/bin/mimo" if name == "mimo" else None)
    secret_prompt = "owner-only prompt details"

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
            stderr_path.write_text('request failed: HTTP 403 {"error":"illegal_access"}\n', encoding="utf-8")
            raise RuntimeError(f"command failed with rc=1: {command_label}")

    host = Host(make_args(tmp_path))
    host.run_task(make_direct_task("MIMO-403", secret_prompt))

    fail_posts = [(path, body) for path, body in host.posts if path.endswith("/fail")]
    assert len(fail_posts) == 1
    fail_body = fail_posts[0][1]
    assert fail_body["error_type"] == "runner_policy_blocked"
    assert fail_body["retry"] is False
    service_payload = json.dumps(fail_body, ensure_ascii=False)
    assert secret_prompt not in service_payload
    assert "illegal_access" in service_payload
    assert artifact_files(tmp_path, "MIMO-403") == [
        "artifact-manifest.json",
        "result.json",
        "runner-contract.json",
        "stderr.log",
        "stdout.log",
    ]
