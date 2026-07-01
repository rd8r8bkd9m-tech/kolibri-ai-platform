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


def make_paths(tmp_path):
    worktree = tmp_path / "repo"
    artifact_dir = tmp_path / "artifacts"
    worktree.mkdir(parents=True)
    artifact_dir.mkdir(parents=True)
    return worktree, artifact_dir


def make_task(envelope=None):
    task_id = "CONTRACT-1"
    return {
        "task_id": task_id,
        "kind": (envelope or {}).get("kind", "read_only_probe"),
        "attempt": 1,
        "attempt_id": f"{task_id}-attempt-1",
        "envelope": envelope or {},
    }


def make_args(tmp_path, capabilities="read_only_probe"):
    return argparse.Namespace(
        control_url="http://127.0.0.1:9101",
        node_id="primary-candidate",
        agent_id="agent-host-primary",
        capabilities=capabilities,
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
    )


def make_host(agent_host, tmp_path, capabilities="read_only_probe"):
    class Host(agent_host.AgentHost):
        def __init__(self):
            super().__init__(make_args(tmp_path, capabilities))
            self.posts = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

    return Host()


def finalize(agent_host, tmp_path, envelope=None, changed_files=None, push_attempted=None):
    worktree, artifact_dir = make_paths(tmp_path)
    task = make_task(envelope or {})
    result = {"task_id": task["task_id"], "status": "completed", "changed_files": changed_files or []}
    return agent_host.finalize_runner_contract(
        task,
        result,
        artifact_dir,
        worktree=worktree,
        changed_files=changed_files or [],
        push_attempted=push_attempted,
    )


def test_no_push_enforcement_blocks_push_without_attempting_it(tmp_path):
    agent_host = load_agent_host()

    result = finalize(agent_host, tmp_path, {"no_push": True}, changed_files=[])

    assert result["status"] == "completed"
    assert result["push_attempted"] is False
    assert result["push_blocked"] is True
    assert result["push_block_reason"] == "no_push"


def test_forbidden_push_attempt_cannot_complete(tmp_path):
    agent_host = load_agent_host()

    result = finalize(agent_host, tmp_path, {"git_push_forbidden": True}, changed_files=[], push_attempted=True)

    assert result["status"] == "blocked"
    assert "forbidden_push_attempted" in result["blocked_reason"]


def test_read_only_product_code_change_is_blocked(tmp_path):
    agent_host = load_agent_host()

    result = finalize(agent_host, tmp_path, {"read_only": True}, changed_files=["ops/agent_host.py"])

    assert result["status"] == "blocked"
    assert result["product_code_changed"] is True
    assert "read_only_product_code_changed" in result["blocked_reason"]


def test_product_code_modification_forbidden_blocks_non_docs_change(tmp_path):
    agent_host = load_agent_host()

    result = finalize(
        agent_host,
        tmp_path,
        {"product_code_modification_forbidden": True},
        changed_files=["backend/providers.py"],
    )

    assert result["status"] == "blocked"
    assert "product_code_modification_forbidden" in result["blocked_reason"]


def test_documentation_artifacts_only_allows_docs_output(tmp_path):
    agent_host = load_agent_host()

    result = finalize(
        agent_host,
        tmp_path,
        {"documentation_artifacts_only": True, "read_only": True},
        changed_files=["docs/agent/report.md"],
    )

    assert result["status"] == "completed"
    assert result["write_scope_violations"] == []
    assert result["product_code_changed"] is False


def test_write_scope_enforcement_blocks_files_outside_scope(tmp_path):
    agent_host = load_agent_host()

    result = finalize(
        agent_host,
        tmp_path,
        {"write_scope": ["docs/agent/allowed/**"]},
        changed_files=["docs/agent/other/report.md"],
    )

    assert result["status"] == "blocked"
    assert result["write_scope_violations"] == ["docs/agent/other/report.md"]
    assert "write_scope_violations" in result["blocked_reason"]


def test_required_artifacts_present_allows_completion(tmp_path):
    agent_host = load_agent_host()
    worktree, artifact_dir = make_paths(tmp_path)
    required = worktree / "docs" / "agent" / "RESULT.md"
    required.parent.mkdir(parents=True)
    required.write_text("ok\n", encoding="utf-8")
    task = make_task({"required_artifacts": ["docs/agent/RESULT.md"]})

    result = agent_host.finalize_runner_contract(
        task,
        {"task_id": task["task_id"], "status": "completed", "changed_files": ["docs/agent/RESULT.md"]},
        artifact_dir,
        worktree=worktree,
        changed_files=["docs/agent/RESULT.md"],
    )

    assert result["status"] == "completed"
    assert result["required_artifacts_present"] == ["docs/agent/RESULT.md"]
    assert result["required_artifacts_missing"] == []


def test_missing_required_artifact_blocks_completion(tmp_path):
    agent_host = load_agent_host()

    result = finalize(agent_host, tmp_path, {"required_artifacts": ["docs/agent/MISSING.md"]}, changed_files=[])

    assert result["status"] == "blocked"
    assert result["required_artifacts_missing"] == ["docs/agent/MISSING.md"]
    assert "required_artifacts_missing" in result["blocked_reason"]


def test_unsupported_task_kind_returns_structured_blocked_result(tmp_path):
    agent_host = load_agent_host()
    worktree, artifact_dir = make_paths(tmp_path)
    task = make_task({"kind": "owner_remote_task", "required_capability": "generic_implementation"})

    result = agent_host.unsupported_task_result(task, artifact_dir, "unsupported_task_kind:owner_remote_task", worktree)

    assert result["status"] == "blocked"
    assert result["changed_files"] == []
    assert "unsupported_task_kind:owner_remote_task" in result["blocked_reason"]
    assert result["next_recommended_task"] == "enable a supported read-only runner for this task kind before resubmitting"


def test_p0_integration_audit_artifact_path_drift_is_blocked(tmp_path):
    agent_host = load_agent_host()
    missing_contract = "docs/agent/integration/2026-06-30-p0-integration-contract-audit/FRONTEND_BACKEND_CONTRACT.md"

    result = finalize(agent_host, tmp_path, {"required_outputs": [missing_contract]}, changed_files=[])

    assert result["status"] == "blocked"
    assert result["required_artifacts_missing"] == [missing_contract]


def test_runner_contract_result_schema_fields_are_always_present(tmp_path):
    agent_host = load_agent_host()

    result = finalize(agent_host, tmp_path, {"read_only": True}, changed_files=["docs/agent/report.md"])

    for field in agent_host.CONTRACT_RESULT_FIELDS:
        assert field in result


def test_run_task_unsupported_kind_posts_blocked_fail_not_complete(tmp_path):
    agent_host = load_agent_host()
    host = make_host(agent_host, tmp_path, capabilities="generic_implementation")
    task = make_task({"kind": "owner_remote_task", "required_capability": "generic_implementation"})
    task["kind"] = "owner_remote_task"

    host.run_task(task)

    assert not [path for path, _ in host.posts if path.endswith("/complete")]
    fail_posts = [(path, body) for path, body in host.posts if path.endswith("/fail")]
    assert len(fail_posts) == 1
    _, fail_body = fail_posts[0]
    assert fail_body["error_type"] == "runner_contract_blocked"
    assert fail_body["retry"] is False
    assert fail_body["result"]["status"] == "blocked"
    assert "unsupported_task_kind:owner_remote_task" in fail_body["result"]["blocked_reason"]
    result_path = Path(fail_body["result_reference"])
    persisted = json.loads(result_path.read_text(encoding="utf-8"))
    for field in agent_host.CONTRACT_RESULT_FIELDS:
        assert field in persisted


def test_run_task_missing_required_artifact_posts_blocked_fail_not_complete(tmp_path):
    agent_host = load_agent_host()
    host = make_host(agent_host, tmp_path, capabilities="read_only_probe")
    task = make_task({"kind": "read_only_probe", "required_artifacts": ["docs/agent/MISSING.md"]})
    task["kind"] = "read_only_probe"

    host.run_task(task)

    assert not [path for path, _ in host.posts if path.endswith("/complete")]
    fail_posts = [(path, body) for path, body in host.posts if path.endswith("/fail")]
    assert len(fail_posts) == 1
    _, fail_body = fail_posts[0]
    assert fail_body["error_type"] == "runner_contract_blocked"
    assert fail_body["retry"] is False
    assert fail_body["result"]["status"] == "blocked"
    assert fail_body["result"]["required_artifacts_missing"] == ["docs/agent/MISSING.md"]
    assert "required_artifacts_missing" in fail_body["result"]["blocked_reason"]


def test_publish_gate_skips_git_push_when_required_artifact_is_missing(tmp_path):
    agent_host = load_agent_host()
    host = make_host(agent_host, tmp_path, capabilities="impl_factory_smoke")
    worktree, artifact_dir = make_paths(tmp_path / "gate")
    stdout_path = artifact_dir / "stdout.log"
    stderr_path = artifact_dir / "stderr.log"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    task = make_task({"required_artifacts": ["docs/agent/MISSING.md"]})
    result = {"task_id": task["task_id"], "status": "completed", "changed_files": ["tests/test_factory_runtime_contracts.py"]}

    gated = host.git_push_after_contract_verification(
        task,
        ["git", "push", "-u", "origin", "branch"],
        worktree,
        stdout_path,
        stderr_path,
        "branch",
        {"stdout": str(stdout_path), "stderr": str(stderr_path)},
        result,
        artifact_dir,
        ["tests/test_factory_runtime_contracts.py"],
        {"GIT_TERMINAL_PROMPT": "0"},
    )

    assert gated["status"] == "blocked"
    assert gated["push_attempted"] is False
    assert gated["push_blocked"] is True
    assert "required_artifacts_missing" in gated["push_block_reason"]
    assert "git push skipped by runner contract preflight" in stdout_path.read_text(encoding="utf-8")


def test_publish_gate_allows_git_push_after_contract_verification_passes(tmp_path):
    agent_host = load_agent_host()

    class Host(agent_host.AgentHost):
        def __init__(self):
            super().__init__(make_args(tmp_path, capabilities="impl_factory_smoke"))
            self.commands = []

        def post(self, path, body):
            return body

        def run_command(self, command, cwd, stdout_path, stderr_path, task, branch=None, logs=None, env=None):
            self.commands.append(command)

    host = Host()
    worktree, artifact_dir = make_paths(tmp_path / "gate")
    required = worktree / "docs" / "agent" / "RESULT.md"
    required.parent.mkdir(parents=True)
    required.write_text("ok\n", encoding="utf-8")
    stdout_path = artifact_dir / "stdout.log"
    stderr_path = artifact_dir / "stderr.log"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    task = make_task({"required_artifacts": ["docs/agent/RESULT.md"]})
    result = {"task_id": task["task_id"], "status": "completed", "changed_files": ["docs/agent/RESULT.md"]}

    gated = host.git_push_after_contract_verification(
        task,
        ["git", "push", "-u", "origin", "branch"],
        worktree,
        stdout_path,
        stderr_path,
        "branch",
        {"stdout": str(stdout_path), "stderr": str(stderr_path)},
        result,
        artifact_dir,
        ["docs/agent/RESULT.md"],
        {"GIT_TERMINAL_PROMPT": "0"},
    )

    assert host.commands == [["git", "push", "-u", "origin", "branch"]]
    assert gated["status"] == "completed"
    assert gated["push_attempted"] is True
    assert gated["push_blocked"] is False
    assert gated["required_artifacts_missing"] == []
