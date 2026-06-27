import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_generic_implementation_envelope_is_normalized():
    control = load_module("factory_control", ROOT / "ops" / "factory_control.py")
    task = control.normalize_task(
        {
            "task_id": "GENERIC-1",
            "root_goal_id": "ROOT-1",
            "kind": "generic_implementation",
            "repository": "ssh://git@example.invalid/repo.git",
            "base_ref": "origin/main",
            "base_commit": "abc123",
            "branch": "factory/generic-1",
            "objective": "change the runner",
            "allowed_paths": "ops",
            "protected_paths": ["ops/secret.py"],
            "required_tests": "python3 -m pytest -q tests/test_generic_runner_contract.py",
            "acceptance_criteria": "runner returns structured result",
            "model_policy": {"runner": "codex"},
            "limits": {"model_timeout_seconds": 60},
        }
    )

    envelope = task["envelope"]
    assert task["kind"] == control.GENERIC_IMPLEMENTATION_KIND
    assert task["idempotency_key"] == "GENERIC-1"
    assert envelope["required_capability"] == control.GENERIC_IMPLEMENTATION_KIND
    assert envelope["allowed_paths"] == ["ops"]
    assert envelope["protected_paths"] == ["ops/secret.py"]
    assert envelope["required_tests"] == ["python3 -m pytest -q tests/test_generic_runner_contract.py"]
    assert envelope["acceptance_criteria"] == ["runner returns structured result"]
    for field in control.GENERIC_IMPLEMENTATION_FIELDS:
        assert field in envelope


def test_agent_host_dispatches_generic_implementation(tmp_path):
    agent = load_module("agent_host", ROOT / "ops" / "agent_host.py")

    class FakeHost(agent.AgentHost):
        def __init__(self):
            self.node_id = "primary-candidate"
            self.hostname = "kolibri"
            self.agent_id = "agent-host-primary"
            self.pid = 123
            self.artifact_root = tmp_path
            self.completed = None
            self.dispatched = None

        def run_generic_implementation(self, task):
            self.dispatched = task
            result_path = tmp_path / "result.json"
            result_path.write_text("{}", encoding="utf-8")
            return {"status": "completed", "result_path": str(result_path)}

        def complete(self, task, result, result_path):
            self.completed = (task, result, result_path)

    host = FakeHost()
    task = {"task_id": "GENERIC-2", "kind": agent.GENERIC_IMPLEMENTATION_KIND, "attempt": 1, "envelope": {}}
    host.run_task(task)

    assert host.dispatched is task
    assert host.completed[0] is task
    assert host.completed[1]["status"] == "completed"


def test_generic_prompt_is_passed_on_stdin_not_argv():
    agent = load_module("agent_host_prompt", ROOT / "ops" / "agent_host.py")
    marker = "DO_NOT_PUT_THIS_PROMPT_IN_ARGV"
    envelope = agent.normalize_generic_envelope(
        {
            "kind": "generic_implementation",
            "objective": f"Implement this exact marker: {marker}",
            "model_policy": {"runner": "codex", "executable": "/usr/local/bin/codex"},
        },
        "GENERIC-3",
        "ssh://git@example.invalid/repo.git",
    )

    command, prompt, runner = agent.build_generic_model_invocation(envelope)

    assert runner == "codex"
    assert marker in prompt
    assert command[-1] == "-"
    assert all(marker not in part for part in command)
    assert all("Implement this exact marker" not in part for part in command)


def test_protected_paths_block_generic_changes():
    agent = load_module("agent_host_paths", ROOT / "ops" / "agent_host.py")
    allowed_paths, protected_paths = agent.normalize_path_policy(
        {"allowed_paths": ["ops"], "protected_paths": ["ops/agent_host.py"]}
    )

    agent.validate_changed_paths(["ops/factory_control.py"], allowed_paths, protected_paths)
    with pytest.raises(RuntimeError, match="path policy violation"):
        agent.validate_changed_paths(["ops/agent_host.py"], allowed_paths, protected_paths)


def test_root_goal_records_are_not_worker_tasks():
    control = load_module("factory_control_root_goal", ROOT / "ops" / "factory_control.py")
    root_goal = control.normalize_root_goal(
        {"kind": "root_goal", "root_goal_id": "ROOT-GOAL-1", "objective": "long running owner goal"}
    )

    assert root_goal["record_type"] == control.ROOT_GOAL_RECORD_TYPE
    assert root_goal["state"] == control.STATE_ACTIVE
    assert root_goal["lease_owner"] is None
    assert root_goal["lease_until"] is None
    assert control.is_leaseable_task(root_goal) is False
