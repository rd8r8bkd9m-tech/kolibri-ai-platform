import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_bot():
    spec = importlib.util.spec_from_file_location("github_release_train_bot", ROOT / "ops" / "github_release_train_bot.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fresh(ok=True):
    bot = load_bot()
    return bot.MainFreshness(ok=ok, local_sha="abc", remote_sha="abc" if ok else "def", reason="fresh" if ok else "stale")


def pr(**overrides):
    bot = load_bot()
    values = {
        "number": 101,
        "title": "P0 repair",
        "head_ref": "p0/repair",
        "base_ref": "main",
        "draft": False,
        "mergeable": "MERGEABLE",
        "merge_state_status": "CLEAN",
        "review_decision": "",
        "checks": bot.CheckSummary("SUCCESS"),
    }
    values.update(overrides)
    return bot.PullRequest(**values)


def test_green_pr_still_requires_owner_approval():
    bot = load_bot()

    classification = bot.classify_pr(pr(), fresh())

    assert classification.state == "owner_approval_required"
    assert classification.owner_gate is True
    assert classification.repair_required is False
    assert any("Owner approval required" in reason for reason in classification.reasons)


def test_approved_green_pr_is_owner_merge_only():
    bot = load_bot()

    classification = bot.classify_pr(pr(review_decision="APPROVED"), fresh())

    assert classification.state == "release_ready_owner_merge_only"
    assert classification.owner_gate is True
    assert "owner" in classification.next_action.lower()


def test_failing_checks_create_repair_required_classification():
    bot = load_bot()
    failing_pr = pr(checks=bot.CheckSummary("FAILURE", failing=("unit-tests",)))

    classification = bot.classify_pr(failing_pr, fresh())
    payload = bot.repair_task_payload(classification, Path("docs/agent/repair_tasks"))

    assert classification.state == "repair_required"
    assert classification.repair_required is True
    assert payload["kind"] == "github_pr_repair"
    assert payload["failing_checks"] == ["unit-tests"]
    assert "push_to_main" in payload["forbidden_actions"]


def test_stale_main_blocks_train_before_pr_status():
    bot = load_bot()
    failing_pr = pr(checks=bot.CheckSummary("FAILURE", failing=("unit-tests",)))

    classification = bot.classify_pr(failing_pr, fresh(ok=False))

    assert classification.state == "blocked_main_freshness"
    assert classification.repair_required is False
    assert "freshness" in classification.next_action


def test_release_train_body_block_is_idempotently_replaced():
    bot = load_bot()
    classification = bot.classify_pr(pr(), fresh())
    first_block = bot.render_train_block(classification, fresh())
    existing = f"hello\n\n{first_block}\nold trailer\n"
    second_block = first_block.replace("owner_approval_required", "waiting_for_ci")

    updated = bot.update_body(existing, second_block)

    assert updated.count(bot.BOT_BLOCK_START) == 1
    assert updated.count(bot.BOT_BLOCK_END) == 1
    assert "waiting_for_ci" in updated
    assert "owner_approval_required" not in updated
    assert updated.startswith("hello")
    assert updated.rstrip().endswith("old trailer")


def test_gh_pr_parser_summarizes_check_rollup():
    bot = load_bot()

    parsed = bot.pr_from_gh({
        "number": 7,
        "title": "Example",
        "headRefName": "feature",
        "baseRefName": "main",
        "statusCheckRollup": [
            {"name": "lint", "conclusion": "SUCCESS"},
            {"name": "tests", "conclusion": "FAILURE"},
            {"name": "build", "status": "IN_PROGRESS"},
        ],
    })

    assert parsed.checks.conclusion == "FAILURE"
    assert parsed.checks.failing == ("tests",)
    assert parsed.checks.pending == ("build",)
