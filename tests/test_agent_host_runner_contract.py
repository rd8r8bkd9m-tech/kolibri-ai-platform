import argparse
import importlib.util
import json
import subprocess
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


def write_local_python_package(package_root, package_name):
    package_dir = package_root / package_name
    package_dir.mkdir(parents=True)
    (package_root / "pyproject.toml").write_text(
        "[build-system]\n"
        "requires = [\"setuptools\"]\n"
        "build-backend = \"setuptools.build_meta\"\n\n"
        "[project]\n"
        f"name = \"{package_name.replace('_', '-')}\"\n"
        "version = \"0.0.1\"\n",
        encoding="utf-8",
    )
    (package_dir / "__init__.py").write_text("VALUE = 'backend-env-ok'\n", encoding="utf-8")


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


def test_read_only_envelope_does_not_receive_push_or_full_autonomy_permissions(tmp_path):
    agent_host = load_agent_host()
    task = make_task({
        "read_only": True,
        "permission_pack": "full_autonomy",
        "permissions": ["read", "git_push", "full_autonomy"],
    })

    sanitized = agent_host.sanitize_task_permissions(task)

    assert sanitized["envelope"]["permission_pack"] == "read_only"
    assert sanitized["envelope"]["permissions"] == ["read"]
    assert sanitized["effective_permissions"]["permission_pack"] == "read_only"
    assert sanitized["effective_permissions"]["permissions"] == ["read"]
    assert sanitized["effective_permissions"]["git_push_allowed"] is False


def test_git_push_forbidden_lease_sanitizes_full_autonomy_pack(tmp_path):
    agent_host = load_agent_host()

    class Host(agent_host.AgentHost):
        def __init__(self):
            super().__init__(make_args(tmp_path, capabilities="generic_implementation"))

        def post(self, path, body):
            assert path == "/v1/tasks/lease"
            return make_task({
                "git_push_forbidden": True,
                "permission_pack": "full_autonomy",
                "allowed_permissions": ["read", "git_push"],
            })

    leased = Host().lease()

    assert leased["envelope"]["permission_pack"] == "read_only"
    assert leased["envelope"]["allowed_permissions"] == ["read"]
    assert leased["effective_permissions"]["git_push_allowed"] is False


def test_push_allowed_envelope_keeps_git_push_permission(tmp_path):
    agent_host = load_agent_host()
    task = make_task({
        "permission_pack": "full_autonomy",
        "permissions": ["read", "git_push"],
    })

    sanitized = agent_host.sanitize_task_permissions(task)

    assert sanitized["envelope"]["permission_pack"] == "full_autonomy"
    assert sanitized["envelope"]["permissions"] == ["read", "git_push"]
    assert sanitized["effective_permissions"]["git_push_allowed"] is True


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


def write_run_artifacts(run_dir, filenames=None):
    filenames = filenames or agent_host_files()
    run_dir.mkdir(parents=True, exist_ok=True)
    for filename in filenames:
        (run_dir / filename).write_text(f"{filename}\n", encoding="utf-8")


def agent_host_files():
    agent_host = load_agent_host()
    return agent_host.CANONICAL_RUN_ARTIFACT_FILES


def test_canonical_run_artifact_contract_requires_exact_five_outputs(tmp_path):
    agent_host = load_agent_host()
    worktree, artifact_dir = make_paths(tmp_path)
    run_dir = "docs/agent/runs/2026-07-01-contract"
    write_run_artifacts(worktree / run_dir)
    task = make_task({"canonical_run_artifact_dir": run_dir})

    result = agent_host.finalize_runner_contract(
        task,
        {"task_id": task["task_id"], "status": "completed", "changed_files": []},
        artifact_dir,
        worktree=worktree,
        changed_files=[],
    )

    assert result["status"] == "completed"
    assert result["canonical_run_artifact_dir"] == run_dir
    assert result["canonical_run_artifact_alias_used"] is None
    assert result["canonical_run_artifacts_missing"] == []
    assert result["required_artifacts_missing"] == []
    assert result["canonical_run_artifacts_present"] == [
        f"{run_dir}/PLAN.md",
        f"{run_dir}/ACTIONS.md",
        f"{run_dir}/TESTS.md",
        f"{run_dir}/RESULT.md",
        f"{run_dir}/NEXT.md",
    ]


def test_canonical_run_artifact_contract_blocks_near_miss_directory_without_explicit_alias(tmp_path):
    agent_host = load_agent_host()
    worktree, artifact_dir = make_paths(tmp_path)
    run_dir = "docs/agent/runs/2026-07-01-contract"
    near_miss = "docs/agent/runs/2026-07-01-contract-audit"
    write_run_artifacts(worktree / near_miss)
    task = make_task({"canonical_run_artifact_dir": run_dir})

    result = agent_host.finalize_runner_contract(
        task,
        {"task_id": task["task_id"], "status": "completed", "changed_files": []},
        artifact_dir,
        worktree=worktree,
        changed_files=[],
    )

    assert result["status"] == "blocked"
    assert result["canonical_run_artifact_aliases"] == []
    assert result["canonical_run_artifact_alias_used"] is None
    assert result["canonical_run_artifacts_present"] == []
    assert result["canonical_run_artifacts_missing"] == [
        f"{run_dir}/PLAN.md",
        f"{run_dir}/ACTIONS.md",
        f"{run_dir}/TESTS.md",
        f"{run_dir}/RESULT.md",
        f"{run_dir}/NEXT.md",
    ]
    assert "required_artifacts_missing" in result["blocked_reason"]


def test_canonical_run_artifact_contract_blocks_missing_next_md(tmp_path):
    agent_host = load_agent_host()
    worktree, artifact_dir = make_paths(tmp_path)
    run_dir = "docs/agent/runs/2026-07-01-contract"
    write_run_artifacts(worktree / run_dir, filenames=("PLAN.md", "ACTIONS.md", "TESTS.md", "RESULT.md"))
    task = make_task({"canonical_run_artifact_dir": run_dir})

    result = agent_host.finalize_runner_contract(
        task,
        {"task_id": task["task_id"], "status": "completed", "changed_files": []},
        artifact_dir,
        worktree=worktree,
        changed_files=[],
    )

    assert result["status"] == "blocked"
    assert result["canonical_run_artifacts_missing"] == [f"{run_dir}/NEXT.md"]
    assert result["required_artifacts_missing"] == [f"{run_dir}/NEXT.md"]
    assert "required_artifacts_missing" in result["blocked_reason"]


def test_complete_explicit_run_artifact_alias_is_logged_and_materialized(tmp_path):
    agent_host = load_agent_host()
    worktree, artifact_dir = make_paths(tmp_path)
    run_dir = "docs/agent/runs/2026-07-01-contract"
    alias_dir = "docs/agent/runs/2026-07-01-contract-final"
    write_run_artifacts(worktree / alias_dir)
    task = make_task({
        "canonical_run_artifact_dir": run_dir,
        "canonical_run_artifact_aliases": [alias_dir],
    })

    result = agent_host.finalize_runner_contract(
        task,
        {"task_id": task["task_id"], "status": "completed", "changed_files": []},
        artifact_dir,
        worktree=worktree,
        changed_files=[],
    )

    assert result["status"] == "completed"
    assert result["canonical_run_artifact_alias_used"] == alias_dir
    assert result["canonical_run_artifacts_missing"] == []
    assert (worktree / run_dir / "NEXT.md").is_file()
    assert result["canonical_run_artifact_alias_log"] == [{
        "alias": alias_dir,
        "canonical": run_dir,
        "complete": True,
        "action": "copied_to_canonical",
    }]
    assert (artifact_dir / "run-artifact-aliases.json").is_file()


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


def test_no_push_task_cannot_publish_central_branch_after_artifact_verification(tmp_path):
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
    worktree, artifact_dir = make_paths(tmp_path / "central-no-push")
    run_dir = "docs/agent/runs/2026-07-01-contract"
    write_run_artifacts(worktree / run_dir)
    stdout_path = artifact_dir / "stdout.log"
    stderr_path = artifact_dir / "stderr.log"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    task = make_task({"no_push": True, "canonical_run_artifact_dir": run_dir})
    result = {"task_id": task["task_id"], "status": "completed", "changed_files": [f"{run_dir}/RESULT.md"]}

    gated = host.git_push_after_contract_verification(
        task,
        ["git", "push", "-u", "origin", "main"],
        worktree,
        stdout_path,
        stderr_path,
        "main",
        {"stdout": str(stdout_path), "stderr": str(stderr_path)},
        result,
        artifact_dir,
        [f"{run_dir}/RESULT.md"],
        {"GIT_TERMINAL_PROMPT": "0"},
    )

    assert host.commands == []
    assert gated["status"] == "completed"
    assert gated["push_attempted"] is False
    assert gated["push_blocked"] is True
    assert gated["push_block_reason"] == "no_push"
    assert "git push skipped by runner contract: no_push" in stdout_path.read_text(encoding="utf-8")


def test_publish_gate_skips_git_push_when_canonical_next_md_is_missing(tmp_path):
    agent_host = load_agent_host()
    host = make_host(agent_host, tmp_path, capabilities="impl_factory_smoke")
    worktree, artifact_dir = make_paths(tmp_path / "gate-canonical")
    stdout_path = artifact_dir / "stdout.log"
    stderr_path = artifact_dir / "stderr.log"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    run_dir = "docs/agent/runs/2026-07-01-contract"
    write_run_artifacts(worktree / run_dir, filenames=("PLAN.md", "ACTIONS.md", "TESTS.md", "RESULT.md"))
    task = make_task({"canonical_run_artifact_dir": run_dir})
    result = {"task_id": task["task_id"], "status": "completed", "changed_files": [f"{run_dir}/RESULT.md"]}

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
        [f"{run_dir}/RESULT.md"],
        {"GIT_TERMINAL_PROMPT": "0"},
    )

    assert gated["status"] == "blocked"
    assert gated["push_attempted"] is False
    assert gated["push_blocked"] is True
    assert gated["canonical_run_artifacts_missing"] == [f"{run_dir}/NEXT.md"]
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


def test_review_clone_auth_failure_posts_result_json_with_credential_repair(tmp_path):
    agent_host = load_agent_host()

    class Host(agent_host.AgentHost):
        def __init__(self):
            super().__init__(make_args(tmp_path, capabilities="review"))
            self.posts = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

        def run_command(self, command, cwd, stdout_path, stderr_path, task, branch=None, logs=None, env=None, command_label=None):
            if command[:2] == ["git", "clone"]:
                stderr_path.write_text(
                    "git@github.com: Permission denied (publickey).\n"
                    "fatal: Could not read from remote repository.\n",
                    encoding="utf-8",
                )
                raise RuntimeError("command failed with rc=128: git clone")
            raise AssertionError(f"unexpected command: {command}")

    task = make_task({
        "kind": "review_pr",
        "branch": "p0/agent-host-runner-contract-hardening-2026-06-30",
        "pull_request_url": "https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/83",
    })
    task["kind"] = "review_pr"

    host = Host()
    host.run_task(task)

    assert not [path for path, _ in host.posts if path.endswith("/complete")]
    fail_posts = [(path, body) for path, body in host.posts if path.endswith("/fail")]
    assert len(fail_posts) == 1
    _, fail_body = fail_posts[0]
    assert fail_body["error_type"] == "review_clone_auth_failed"
    assert fail_body["retry"] is False
    assert "repair Agent Host git credentials" in fail_body["error"]
    result_path = Path(fail_body["result_reference"])
    assert result_path.is_file()
    persisted = json.loads(result_path.read_text(encoding="utf-8"))
    assert persisted["status"] == "failed"
    assert persisted["result_path"] == str(result_path)
    assert persisted["required_artifacts_missing"] == []
    assert persisted["next_recommended_task"] == "repair Agent Host git credentials, then rerun the review task"


def test_read_only_review_pr_separates_reviewed_diff_from_runner_changes(tmp_path, monkeypatch):
    agent_host = load_agent_host()

    class Host(agent_host.AgentHost):
        def __init__(self):
            super().__init__(make_args(tmp_path, capabilities="review"))
            self.commands = []

        def post(self, path, body):
            return body

        def run_command(self, command, cwd, stdout_path, stderr_path, task, branch=None, logs=None, env=None, command_label=None):
            self.commands.append(command)
            if command[:2] == ["git", "clone"]:
                worktree = Path(command[-1])
                worktree.mkdir(parents=True)
                (worktree / ".git").mkdir()
                (worktree / "backend").mkdir()
                (worktree / "backend" / "providers.py").write_text("VALUE = 'reviewed'\n", encoding="utf-8")

    def fake_check_output(command, cwd=None, text=None):
        assert command[:3] == ["git", "diff", "--name-only"]
        return "backend/providers.py\n"

    monkeypatch.setattr(agent_host.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(agent_host.shutil, "which", lambda name: None if name == "gh" else agent_host.shutil.which(name))

    task = make_task({
        "kind": "review_pr",
        "read_only": True,
        "branch": "product-code-pr",
        "base_ref": "origin/main",
        "pull_request_url": "https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/83",
    })
    task["kind"] = "review_pr"

    result = Host().run_review_pr(task)

    assert result["status"] == "completed"
    assert result["runner_status"] == "APPROVED"
    assert result["changed_files"] == []
    assert result["reviewed_diff_files"] == ["backend/providers.py"]
    assert result["product_code_changed"] is False
    assert result["blocked_reason"] is None


def test_backend_verifier_uses_declared_backend_python_environment_for_dependencies(tmp_path):
    agent_host = load_agent_host()
    package_name = "kolibri_backend_contract_dep_20260701"
    dependency_src = tmp_path / "dependency-src"
    write_local_python_package(dependency_src, package_name)
    worktree, artifact_dir = make_paths(tmp_path)
    (worktree / "backend").mkdir()
    (worktree / "backend" / "requirements.txt").write_text(f"{dependency_src}\n", encoding="utf-8")
    stdout_path = artifact_dir / "stdout.log"
    stderr_path = artifact_dir / "stderr.log"
    task = make_task({
        "backend_python_verification_env": {
            "type": "backend_python",
            "requirements": ["backend/requirements.txt"],
            "cleanup": True,
        },
    })

    raw = subprocess.run(
        ["python3", "-c", f"import {package_name}"],
        cwd=str(worktree),
        text=True,
        capture_output=True,
        check=False,
    )
    assert raw.returncode != 0

    host = make_host(agent_host, tmp_path, capabilities="review")
    metadata = host.run_backend_verification_commands(
        [["python3", "-c", f"import {package_name}; assert {package_name}.VALUE == 'backend-env-ok'"]],
        worktree,
        artifact_dir,
        stdout_path,
        stderr_path,
        task,
        "branch",
        {"stdout": str(stdout_path), "stderr": str(stderr_path)},
    )

    assert metadata["enabled"] is True
    assert metadata["status"] == "passed"
    assert metadata["requirements"] == ["backend/requirements.txt"]
    assert metadata["cleaned"] is True
    assert not Path(metadata["path"]).exists()
    assert "backend-test-env/bin/python -c" in stdout_path.read_text(encoding="utf-8")


def test_backend_verification_environment_is_not_in_worktree_and_cleanup_is_enforced(tmp_path):
    agent_host = load_agent_host()
    package_name = "kolibri_backend_contract_cleanup_dep_20260701"
    dependency_src = tmp_path / "dependency-src"
    write_local_python_package(dependency_src, package_name)
    worktree, artifact_dir = make_paths(tmp_path)
    (worktree / "backend").mkdir()
    (worktree / "backend" / "requirements.txt").write_text(f"{dependency_src}\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=str(worktree), check=True, capture_output=True)
    subprocess.run(["git", "add", "backend/requirements.txt"], cwd=str(worktree), check=True, capture_output=True)
    stdout_path = artifact_dir / "stdout.log"
    stderr_path = artifact_dir / "stderr.log"
    task = make_task({
        "backend_test_environment": {
            "type": "backend_python",
            "path": "declared-backend-test-env",
            "requirements": ["backend/requirements.txt"],
            "cleanup": True,
        },
    })

    host = make_host(agent_host, tmp_path, capabilities="review")
    metadata = host.run_backend_verification_commands(
        [["python3", "-c", f"import {package_name}"]],
        worktree,
        artifact_dir,
        stdout_path,
        stderr_path,
        task,
        "branch",
        {"stdout": str(stdout_path), "stderr": str(stderr_path)},
    )

    env_path = Path(metadata["path"])
    assert metadata["cleaned"] is True
    assert not env_path.exists()
    assert agent_host.path_is_under(env_path, artifact_dir)
    assert not agent_host.path_is_under(env_path, worktree)
    changed = agent_host.collect_git_changed_files(worktree)
    assert all("backend-test-env" not in item and "declared-backend-test-env" not in item for item in changed)


def test_backend_verification_environment_setup_failure_is_structured_blocker(tmp_path):
    agent_host = load_agent_host()

    class Host(agent_host.AgentHost):
        def __init__(self):
            super().__init__(make_args(tmp_path, capabilities="review_pr"))
            self.posts = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

        def run_review_pr(self, task):
            raise agent_host.BackendTestEnvironmentError(
                "backend_test_environment_failed: command failed with rc=1: python3 -m venv"
            )

    task = make_task({"kind": "review_pr"})
    task["kind"] = "review_pr"

    host = Host()
    host.run_task(task)
    assert not [path for path, _ in host.posts if path.endswith("/complete")]
    fail_posts = [(path, body) for path, body in host.posts if path.endswith("/fail")]
    assert len(fail_posts) == 1
    _, fail_body = fail_posts[0]
    assert fail_body["error_type"] == "backend_test_environment_failed"
    assert fail_body["retry"] is False
    assert fail_body["result"]["status"] == "blocked"
    assert fail_body["result"]["blocked_reason"] == "backend_test_environment_failed"
    assert "backend test environment" in fail_body["result"]["next_recommended_task"]
