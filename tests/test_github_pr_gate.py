import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_gate():
    spec = importlib.util.spec_from_file_location("github_pr_gate", ROOT / "ops" / "github_pr_gate.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_github_pr_gate_detects_waiting_review_task_that_needs_pr():
    gate = load_gate()
    task = {
        "task_id": "KOL-AGENT-RESULT",
        "state": "waiting_review",
        "branch": "agent/KOL-AGENT-RESULT/work",
        "envelope": {"base_ref": "origin/codex/factory-autonomy-pwa-billing"},
        "result": {
            "needs_central_pr": True,
            "pushed": True,
            "commit": "abc123",
            "changed_files": ["docs/agent-work/result.md"],
        },
    }

    assert gate.task_needs_central_pr(task) is True
    assert gate.branch_for_task(task) == "agent/KOL-AGENT-RESULT/work"
    assert gate.base_for_task(task, "main") == "codex/factory-autonomy-pwa-billing"


def test_github_pr_gate_skips_tasks_that_already_have_pr():
    gate = load_gate()
    task = {
        "task_id": "KOL-AGENT-RESULT",
        "state": "waiting_review",
        "branch": "agent/KOL-AGENT-RESULT/work",
        "result": {
            "needs_central_pr": True,
            "pull_request_url": "https://github.com/owner/repo/pull/60",
        },
    }

    assert gate.task_pr_url(task) == "https://github.com/owner/repo/pull/60"
    assert gate.task_needs_central_pr(task) is False


def test_github_pr_gate_pr_body_contains_factory_trace():
    gate = load_gate()
    task = {
        "task_id": "KOL-AGENT-RESULT",
        "state": "waiting_review",
        "branch": "agent/KOL-AGENT-RESULT/work",
        "result": {
            "node_id": "home",
            "runner": "codex",
            "commit": "abc123",
            "changed_files": ["docs/agent-work/result.md"],
            "checks": ["python3 -m pytest -q tests/test_factory_status.py"],
        },
    }

    body = gate.pr_body(task)

    assert "KOL-AGENT-RESULT" in body
    assert "agent/KOL-AGENT-RESULT/work" in body
    assert "docs/agent-work/result.md" in body
    assert "python3 -m pytest -q tests/test_factory_status.py" in body
