import argparse
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_agent_host():
    spec = importlib.util.spec_from_file_location("agent_host", ROOT / "ops" / "agent_host.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_factory_control():
    spec = importlib.util.spec_from_file_location(
        "factory_control_for_agent_host_failure",
        ROOT / "ops" / "factory_control.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_args(tmp_path):
    mesh_manifest = tmp_path / "mesh-peers.json"
    mesh_manifest.parent.mkdir(parents=True, exist_ok=True)
    mesh_manifest.write_text(
        json.dumps({"peers": [{"node_id": "home", "mesh_ip": "10.99.0.1"}]}),
        encoding="utf-8",
    )
    return argparse.Namespace(
        control_url="http://10.99.0.1:9101",
        mesh_membership_manifest=str(mesh_manifest),
        node_id="worker-test",
        agent_id="agent-host-test",
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
            del task, branch, logs, env
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
    assert result["runner_contract"]["cli_contract"] == (
        "mimo-auto25-direct-permission-bypass-v1"
    )
    assert result["runner_contract"]["permission_mode"] == (
        "dangerously_skip_permissions"
    )
    assert result["runner_contract"]["prompt_transport"] == "argv"
    assert result["runner_contract"]["sandbox"] == "none"
    assert result["runner_contract"]["worktree_scoped"] is False
    assert "factory_provider_contract" not in result["runner_contract"]
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


def test_direct_mimo_generic_rc1_posts_strict_runner_bound_fail_and_returns(
    tmp_path, monkeypatch
):
    agent_host = load_agent_host()
    factory_control = load_factory_control()
    monkeypatch.setattr(
        agent_host.shutil,
        "which",
        lambda name: "/usr/bin/mimo" if name == "mimo" else None,
    )
    # Keep the leak sentinel realistic without making a tracked test fixture
    # indistinguishable from a credential assignment to the repository scan.
    raw_secret = "api_key=" + "provider-private-value-must-not-leak"
    task = make_direct_task("MIMO-GENERIC-RC1", "harmless owner request")

    class Host(agent_host.AgentHost):
        def __init__(self, args):
            super().__init__(args)
            self.posts = []
            self.fail_ack = None

        def post(self, path, body):
            self.posts.append((path, body))
            if path.endswith("/fail"):
                assert factory_control.runner_result_binding_error(task, body) is None
                self.fail_ack = {
                    "task_id": task["task_id"],
                    "state": "queued" if body["retry"] else "failed",
                    "lease_until": None,
                }
                return self.fail_ack
            return body

        def run_command(
            self, command, cwd, stdout_path, stderr_path, task, branch, logs,
            env=None, command_label=None,
        ):
            del command, cwd, task, branch, logs, env
            stdout_path.write_text(f"$ {command_label}\n", encoding="utf-8")
            stderr_path.write_text(f"provider failed: {raw_secret}\n", encoding="utf-8")
            raise RuntimeError(f"command failed with rc=1: {command_label}")

    host = Host(make_args(tmp_path))

    host.run_task(task)

    assert not [item for item in host.posts if item[0].endswith("/complete")]
    failures = [item for item in host.posts if item[0].endswith("/fail")]
    assert len(failures) == 1
    fail_body = failures[0][1]
    assert fail_body["error_type"] == "runtime_error"
    assert fail_body["result"]["status"] == "failed"
    assert fail_body["result"]["runner"] == "mimo"
    assert fail_body["result"]["requested_runner"] == "mimo"
    assert fail_body["result"]["runner_binding_verified"] is True
    assert host.fail_ack == {
        "task_id": task["task_id"],
        "state": "queued",
        "lease_until": None,
    }
    artifact_dir = (
        tmp_path / "artifacts" / task["task_id"] / task["attempt_id"]
    )
    retained = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            artifact_dir / "result.json",
            artifact_dir / "stdout.log",
            artifact_dir / "stderr.log",
        )
    )
    assert raw_secret not in json.dumps(fail_body, ensure_ascii=False)
    assert raw_secret not in retained
    assert "[redacted sensitive runner output]" in retained


def test_fail_binding_does_not_overwrite_explicit_runner_mismatch(
    tmp_path, monkeypatch
):
    agent_host = load_agent_host()
    factory_control = load_factory_control()
    monkeypatch.setattr(
        agent_host.shutil,
        "which",
        lambda name: "/usr/bin/mimo" if name == "mimo" else None,
    )

    class Host(agent_host.AgentHost):
        def __init__(self, args):
            super().__init__(args)
            self.posts = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

    host = Host(make_args(tmp_path))
    task = make_direct_task("MIMO-EXPLICIT-MISMATCH")

    host.fail(
        task,
        "runtime_error",
        "explicit runner mismatch",
        {"status": "failed", "runner": "codex"},
        None,
        retry=False,
    )

    fail_body = host.posts[0][1]
    assert fail_body["result"]["runner"] == "codex"
    assert fail_body["result"]["requested_runner"] == "mimo"
    assert fail_body["result"]["runner_binding_verified"] is False
    assert factory_control.runner_result_binding_error(task, fail_body) == {
        "error": "runner_result_mismatch",
        "requested_runner": "mimo",
        "result_runner": "codex",
    }


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


def test_direct_mimo_zero_exit_json_risk_event_is_policy_blocked(tmp_path, monkeypatch):
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
            event = {
                "type": "error",
                "error": {
                    "name": "APIError",
                    "data": {
                        "message": "Request blocked by risk control",
                        "statusCode": 400,
                        "isRetryable": False,
                        "responseHeaders": {"authorization": "must-not-leak"},
                        "responseBody": "provider-internal-body",
                    },
                },
            }
            stdout_path.write_text(f"$ {command_label}\n" + json.dumps(event) + "\n", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")

    host = Host(make_args(tmp_path))
    host.run_task(make_direct_task("MIMO-RISK-JSON", "harmless prompt"))

    fail_body = [(path, body) for path, body in host.posts if path.endswith("/fail")][0][1]
    assert fail_body["error_type"] == "provider_risk_control"
    assert fail_body["retry"] is False
    assert host.runner_status["mimo"]["status"] == "blocked"
    assert host.runner_status["mimo"]["error_type"] == "provider_risk_control"
    assert "runner:mimo" not in host.capabilities
    host.node_heartbeat()
    heartbeat = [(path, body) for path, body in host.posts if path.endswith("/heartbeat")][-1][1]
    assert heartbeat["runners"]["mimo"]["status"] == "blocked"
    serialized = json.dumps(fail_body, ensure_ascii=False)
    assert "must-not-leak" not in serialized
    assert "provider-internal-body" not in serialized


def test_orchestrator_chat_result_preserves_runner_for_factory_verification(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    monkeypatch.setattr(agent_host.shutil, "which", lambda name: "/usr/bin/mimo" if name == "mimo" else None)

    class Host(agent_host.AgentHost):
        def post(self, _path, body):
            return body

        def run_requested_ai_runner(self, runner, *_args, **_kwargs):
            assert runner == "mimo"
            return "MIMO_FACTORY_OK"

    host = Host(make_args(tmp_path))
    task = make_direct_task("MIMO-ORCHESTRATOR")
    task["kind"] = "orchestrator_chat_response"
    task["envelope"] = {
        "kind": "orchestrator_chat_response",
        "runner": "mimo",
        "message": "Ответь только MIMO_FACTORY_OK",
        "constraints": {"read_only": True},
        "write_scope": [],
    }
    result = host.run_telegram_chat_response(task)
    assert result["status"] == "completed"
    assert result["runner"] == "mimo"
    assert result["response"] == "MIMO_FACTORY_OK"
    assert result["runner_contract"]["model"] == "mimo/mimo-auto"


def test_orchestrator_mimo_uses_readonly_file_transport_and_cleans_prompt(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    monkeypatch.setattr(agent_host.shutil, "which", lambda name: "/usr/bin/mimo" if name == "mimo" else None)
    secret = "private owner prompt must not enter argv"
    observed_prompt_path = None

    class Host(agent_host.AgentHost):
        def post(self, _path, body):
            return body

        def run_command(self, command, cwd, stdout_path, stderr_path, task, branch, logs, env=None, command_label=None):
            nonlocal observed_prompt_path
            del task, branch, logs, env
            assert secret not in command
            assert secret not in str(command_label)
            assert "--dangerously-skip-permissions" not in command
            assert command[command.index("--agent") + 1] == "kolibri-response-only"
            assert "--pure" in command
            profile = Path(cwd) / ".mimocode" / "agents" / "kolibri-response-only.md"
            assert profile.is_file()
            profile_text = profile.read_text(encoding="utf-8")
            assert "tool_allowlist: []" in profile_text
            assert "  bash: false" in profile_text
            assert "  write: false" in profile_text
            assert '  "*": deny' in profile_text
            observed_prompt_path = Path(command[command.index("--file") + 1])
            assert observed_prompt_path.read_text(encoding="utf-8").find(secret) >= 0
            stdout_path.write_text(
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "SAFE"}}) + "\n",
                encoding="utf-8",
            )
            stderr_path.write_text("", encoding="utf-8")

    host = Host(make_args(tmp_path))
    task = make_direct_task("MIMO-FILE-TRANSPORT")
    task["kind"] = "orchestrator_chat_response"
    task["envelope"] = {
        "kind": "orchestrator_chat_response",
        "runner": "mimo",
        "message": secret,
        "write_scope": [],
    }
    result = host.run_telegram_chat_response(task)
    assert result["response"] == "SAFE"
    assert observed_prompt_path is not None
    assert not observed_prompt_path.exists()
    assert not (Path(result["worktree"]) / ".mimocode").exists()
    assert result["runner_contract"]["prompt_transport"] == "file"
    assert result["runner_contract"]["sandbox"] == "read-only"


def test_orchestrator_mimo_rejects_tool_event_and_withholds_raw_payload(
    tmp_path, monkeypatch
):
    agent_host = load_agent_host()
    monkeypatch.setattr(
        agent_host.shutil,
        "which",
        lambda name: "/usr/bin/mimo" if name == "mimo" else None,
    )
    forbidden_detail = "private-command-argument-must-not-leak"

    class Host(agent_host.AgentHost):
        def __init__(self, args):
            super().__init__(args)
            self.posts = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

        def run_command(
            self, command, cwd, stdout_path, stderr_path, task, branch, logs,
            env=None, command_label=None,
        ):
            del self, command, cwd, task, branch, logs, env, command_label
            events = [
                {"type": "message", "text": "partial response"},
                {
                    "type": "tool_call",
                    "tool": "bash",
                    "arguments": {"command": forbidden_detail},
                },
                {"type": "message", "text": "must not be accepted"},
            ]
            stdout_path.write_text(
                "\n".join(json.dumps(event) for event in events) + "\n",
                encoding="utf-8",
            )
            stderr_path.write_text(forbidden_detail, encoding="utf-8")

    host = Host(make_args(tmp_path))
    task = make_direct_task("MIMO-RESPONSE-ONLY-TOOL-EVENT", forbidden_detail)
    task["kind"] = "orchestrator_chat_response"
    task["envelope"] = {
        "kind": "orchestrator_chat_response",
        "runner": "mimo",
        "message": forbidden_detail,
        "constraints": {"read_only": True},
        "write_scope": [],
    }

    host.run_task(task)

    assert not [item for item in host.posts if item[0].endswith("/complete")]
    failures = [item for item in host.posts if item[0].endswith("/fail")]
    assert len(failures) == 1
    assert failures[0][1]["error_type"] == "runner_policy_blocked"
    assert failures[0][1]["retry"] is False
    assert forbidden_detail not in json.dumps(failures[0][1], ensure_ascii=False)
    artifact_dir = (
        tmp_path / "artifacts" / "MIMO-RESPONSE-ONLY-TOOL-EVENT"
        / "MIMO-RESPONSE-ONLY-TOOL-EVENT-attempt-1"
    )
    assert forbidden_detail not in (artifact_dir / "stdout.log").read_text(encoding="utf-8")
    assert forbidden_detail not in (artifact_dir / "stderr.log").read_text(encoding="utf-8")
    assert not (tmp_path / "work" / "MIMO-RESPONSE-ONLY-TOOL-EVENT" / ".mimocode").exists()


@pytest.mark.parametrize(
    ("runner", "serialized_output"),
    [
        (
            "mimo",
            '<tool_call>{"name":"web_search","arguments":{"query":"private-marker"}}</tool_call>',
        ),
        (
            "codex",
            json.dumps({
                "tool_calls": [{
                    "id": "call-private-marker",
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "arguments": '{"query":"private-marker"}',
                    },
                }],
            }),
        ),
    ],
)
def test_response_only_mimo_and_codex_reject_serialized_tool_call_text(
    tmp_path, monkeypatch, runner, serialized_output
):
    agent_host = load_agent_host()
    monkeypatch.setattr(
        agent_host.shutil,
        "which",
        lambda name: f"/usr/local/bin/{name}" if name == runner else None,
    )
    monkeypatch.setattr(
        agent_host.AgentHost,
        "detect_codex_runner_status",
        lambda _self, path: {
            "status": "available",
            "path": path,
            "login_status": "authenticated",
            "probe": {
                "model": agent_host.CODEX_TASK_MODEL,
                "sandbox": "read-only",
                "status": "passed",
            },
        },
    )

    class Host(agent_host.AgentHost):
        def __init__(self, args):
            super().__init__(args)
            self.posts = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

        def run_command(
            self, command, cwd, stdout_path, stderr_path, task, branch, logs,
            **_kwargs,
        ):
            del self, command, cwd, task, branch, logs
            stdout_path.write_text(
                json.dumps({
                    "type": "item.completed",
                    "item": {
                        "type": "agent_message",
                        "text": serialized_output,
                    },
                }) + "\n",
                encoding="utf-8",
            )
            stderr_path.write_text("", encoding="utf-8")

    task_id = f"{runner.upper()}-SERIALIZED-TOOL-CALL"
    task = make_direct_task(task_id, "return a final response")
    task["envelope"].update({
        "runner": runner,
        "constraints": {"read_only": True},
        "write_scope": [],
    })
    host = Host(make_args(tmp_path))

    host.run_task(task)

    assert not [item for item in host.posts if item[0].endswith("/complete")]
    failures = [item for item in host.posts if item[0].endswith("/fail")]
    assert len(failures) == 1
    assert failures[0][1]["error_type"] == "response_only_tool_call_output"
    assert failures[0][1]["retry"] is False
    assert "private-marker" not in json.dumps(failures[0][1], ensure_ascii=False)
    artifact_dir = tmp_path / "artifacts" / task_id / f"{task_id}-attempt-1"
    assert "private-marker" not in (
        artifact_dir / "stdout.log"
    ).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "response_text",
    [
        "Инструменты обсуждаются как концепция; вызовов инструментов не было.",
        "Тег <tool_call>...</tool_call> в документации обозначает вызов инструмента.",
        '{"topic":"tool_call","description":"ordinary documentation"}',
        '```json\n{"name":"web_search","arguments":{"query":"example"}}\n```',
    ],
)
def test_serialized_tool_call_detector_allows_ordinary_tool_discussion(
    response_text,
):
    agent_host = load_agent_host()

    assert agent_host.serialized_tool_call_output_name(response_text) is None


def test_mimo_response_profile_is_digest_pinned_and_fails_closed_on_mutation(
    tmp_path,
):
    agent_host = load_agent_host()
    profile = ROOT / "ops" / "mimo" / "kolibri-response-only.md"
    payload, digest = agent_host.load_mimo_response_agent_profile(profile)
    assert payload == profile.read_bytes()
    assert digest == agent_host.MIMO_RESPONSE_PROFILE_SHA256

    mutated = tmp_path / "kolibri-response-only.md"
    mutated.write_bytes(payload + b"\n# mutation\n")
    mutated.chmod(0o600)
    with pytest.raises(RuntimeError, match="contract_invalid"):
        agent_host.load_mimo_response_agent_profile(mutated)


def test_mimo_response_profile_and_prompt_are_cleaned_when_readiness_digest_drifts(
    tmp_path, monkeypatch
):
    agent_host = load_agent_host()
    monkeypatch.setattr(
        agent_host.shutil,
        "which",
        lambda name: "/usr/bin/mimo" if name == "mimo" else None,
    )

    class Host(agent_host.AgentHost):
        def post(self, _path, body):
            return body

    host = Host(make_args(tmp_path))
    host.runner_status["mimo"]["response_profile_sha256"] = "0" * 64
    task = make_direct_task("MIMO-PROFILE-DRIFT")
    task["kind"] = "orchestrator_chat_response"
    task["envelope"] = {
        "kind": "orchestrator_chat_response",
        "runner": "mimo",
        "message": "response only",
        "write_scope": [],
    }

    with pytest.raises(
        agent_host.RunnerExecutionError,
        match="changed after readiness",
    ) as failure:
        host.run_telegram_chat_response(task)

    assert failure.value.error_type == "mimo_response_profile_unavailable"
    assert host.runner_status["mimo"]["status"] == "unavailable"
    assert host.runner_status["mimo"]["error_type"] == (
        "mimo_response_profile_unavailable"
    )
    assert "runner:mimo" not in host.capabilities
    worktree = (
        tmp_path / "work" / "MIMO-PROFILE-DRIFT"
        / "MIMO-PROFILE-DRIFT-attempt-1" / "repo"
    )
    assert not (worktree / ".kolibri-provider-prompt").exists()
    assert not (worktree / ".mimocode").exists()


def test_factory_codex_uses_stdin_readonly_contract_and_cleans_prompt(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    monkeypatch.setattr(
        agent_host,
        "resolve_home_control_plane_url",
        lambda *_args, **_kwargs: "http://127.0.0.1:9101",
    )
    monkeypatch.setattr(
        agent_host.shutil,
        "which",
        lambda name: "/usr/local/bin/codex" if name == "codex" else None,
    )
    monkeypatch.setattr(
        agent_host.AgentHost,
        "detect_codex_runner_status",
        lambda _self, path: {
            "status": "available",
            "path": path,
            "login_status": "authenticated",
            "probe": {"model": "gpt-5.5", "sandbox": "read-only", "status": "passed"},
        },
    )
    observed_prompt = None

    class Host(agent_host.AgentHost):
        def post(self, _path, body):
            return body

        def run_command(
            self, command, cwd, stdout_path, stderr_path, task, branch, logs,
            env=None, command_label=None, stdin_path=None,
        ):
            del self, cwd, task, branch, logs, env
            nonlocal observed_prompt
            assert command[-1] == "-"
            assert command[:3] == ["/usr/local/bin/codex", "--search", "exec"]
            assert command[command.index("--sandbox") + 1] == "read-only"
            assert command[command.index("--model") + 1] == "gpt-5.5"
            assert "--ephemeral" in command
            assert "--ignore-user-config" in command
            assert "--ignore-rules" in command
            assert command[command.index("--color") + 1] == "never"
            assert "danger-full-access" not in command
            assert command_label.endswith("<prompt-file>")
            assert stdin_path is not None
            observed_prompt = stdin_path.read_text(encoding="utf-8")
            stdout_path.write_text(
                json.dumps({
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "SAFE CODEX"},
                }) + "\n",
                encoding="utf-8",
            )
            stderr_path.write_text("", encoding="utf-8")

    host = Host(make_args(tmp_path))
    task = make_direct_task("CODEX-FACTORY-READONLY")
    task["kind"] = "owner_remote_task"
    task["envelope"] = {
        "kind": "owner_remote_task",
        "runner": "codex",
        "objective": "private factory prompt",
        "constraints": {"read_only": True},
        "write_scope": [],
    }
    result = host.run_owner_remote_task(task)

    assert observed_prompt is not None
    assert observed_prompt.startswith(agent_host.CODEX_PROVIDER_NETWORK_INSTRUCTION)
    assert "Do not run curl" in observed_prompt
    assert observed_prompt.endswith("private factory prompt")
    assert result["response"] == "SAFE CODEX"
    assert not (Path(result["worktree"]) / ".kolibri-provider-prompt").exists()
    assert result["runner_contract"]["factory_provider_contract"] == "kolibri.factory-provider.readonly.v1"
    assert result["runner_contract"]["prompt_transport"] == "stdin"
    assert result["runner_contract"]["sandbox"] == "read-only"
    assert result["runner_contract"]["network_access"] == "provider_managed_search"


def test_home_factory_provider_task_is_distinct_from_legacy_direct_mimo_task():
    agent_host = load_agent_host()
    factory_task = make_direct_task("FACTORY-PROVIDER-ROUTING")
    factory_task["envelope"].update({
        "constraints": {"read_only": True},
        "write_scope": [],
        "source": {
            "kind": "kolibri_provider_gateway",
            "control_plane": "home",
            "response_id": "resp-safe",
        },
    })

    assert agent_host.is_factory_provider_task(factory_task) is True
    assert agent_host.is_factory_provider_task(make_direct_task("LEGACY-DIRECT")) is False


def test_home_factory_provider_run_task_is_bound_to_response_only_mimo(
    tmp_path, monkeypatch
):
    agent_host = load_agent_host()
    monkeypatch.setattr(
        agent_host.shutil,
        "which",
        lambda name: "/usr/bin/mimo" if name == "mimo" else None,
    )

    class Host(agent_host.AgentHost):
        def __init__(self, args):
            super().__init__(args)
            self.posts = []
            self.commands = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

        def run_command(
            self, command, cwd, stdout_path, stderr_path, task, branch, logs,
            env=None, command_label=None,
        ):
            del task, branch, logs, env
            self.commands.append(command)
            assert "--pure" in command
            assert "--dangerously-skip-permissions" not in command
            assert command[command.index("--agent") + 1] == "kolibri-response-only"
            profile = (
                Path(cwd) / ".mimocode" / "agents" / "kolibri-response-only.md"
            )
            assert "tool_allowlist: []" in profile.read_text(encoding="utf-8")
            prompt_path = Path(command[command.index("--file") + 1])
            assert prompt_path.read_text(encoding="utf-8") == "private response prompt"
            assert "private response prompt" not in command
            assert "private response prompt" not in str(command_label)
            stdout_path.write_text(
                json.dumps({
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "SAFE FACTORY RESPONSE"},
                }) + "\n",
                encoding="utf-8",
            )
            stderr_path.write_text("", encoding="utf-8")

    task = make_direct_task("FACTORY-PROVIDER-RESPONSE-ONLY", "private response prompt")
    task["envelope"].update({
        "target_node": "worker-test",
        "required_capability": "runner:mimo",
        "constraints": {
            "read_only": True,
            "max_wall_seconds": 45,
            "network": "provider_managed_only",
        },
        "write_scope": [],
        "max_retries": 0,
        "fallback_allowed": False,
        "source": {
            "kind": "kolibri_provider_gateway",
            "control_plane": "home",
            "response_id": "resp-factory-safe",
            "identity_contract": "kolibri.public-identity.v1",
        },
    })
    host = Host(make_args(tmp_path))

    host.run_task(task)

    assert len(host.commands) == 1
    complete = [body for path, body in host.posts if path.endswith("/complete")]
    assert len(complete) == 1
    assert complete[0]["result"]["response"] == "SAFE FACTORY RESPONSE"
    assert complete[0]["result"]["runner_contract"]["cli_contract"] == (
        "mimo-auto25-response-only-v2"
    )
    assert complete[0]["result"]["runner_contract"]["permission_mode"] == (
        "deny_all_response_only"
    )
    assert complete[0]["result"]["runner_contract"]["response_agent_tools"] == []
    worktree = (
        tmp_path / "work" / "FACTORY-PROVIDER-RESPONSE-ONLY"
        / "FACTORY-PROVIDER-RESPONSE-ONLY-attempt-1" / "repo"
    )
    assert not (worktree / ".kolibri-provider-prompt").exists()
    assert not (worktree / ".mimocode").exists()
