from pathlib import Path

from ops.production_result_aggregator import (
    aggregate,
    classify_row,
    parse_markdown_table,
    redispatch_envelope,
)


def write_ledger(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "ledger.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_aggregates_only_production_outcomes_from_wave(tmp_path):
    ledger = write_ledger(
        tmp_path,
        """# Queue

| Task ID | Status | Summary | Blockers |
| --- | --- | --- | --- |
| `P0_LIVE_REPAIR_2026_07_02` | `dead_letter_rollback_applied` | Live service rollback applied; `/health` HTTP 200; next `P0_IMPORT_FIX_2026_07_02` | Fabric routes still 404 |
| `P0_AUDIT_2026_07_02` | `completed` | diagnostic only report; no live mutation and no product code | none |
| `P0_OLD_PR_2026_07_01` | `completed` | PR #88 CI passed | none |
""",
    )

    report = aggregate(parse_markdown_table(ledger), "2026_07_02")

    assert [item["task_id"] for item in report["production_outcomes"]] == ["P0_LIVE_REPAIR_2026_07_02"]
    assert report["deploy_blockers"][0]["task_id"] == "P0_LIVE_REPAIR_2026_07_02"
    assert report["next_execution_tasks"] == ["P0_IMPORT_FIX_2026_07_02"]
    assert [item["task_id"] for item in report["audit_only_failures"]] == ["P0_AUDIT_2026_07_02"]


def test_pr_urls_and_tests_are_preserved_in_production_result(tmp_path):
    ledger = write_ledger(
        tmp_path,
        """| Task ID | Status | Branch/PR | Tests | Summary | Blockers |
| --- | --- | --- | --- | --- | --- |
| `P0_PR_REPAIR_2026_07_02` | `completed_pr_ci_green` | PR `https://github.com/acme/repo/pull/123`, branch `p0/fix`, head `abc123` | focused `11 passed`; full `71 passed, 1 warning` | Production PR branch pushed | none |
""",
    )

    report = aggregate(parse_markdown_table(ledger), "2026_07_02")

    assert report["pr_urls"] == ["https://github.com/acme/repo/pull/123"]
    assert report["tests"] == ["11 passed", "71 passed, 1 warning"]
    assert report["production_outcomes"][0]["kind"] == "pr_branch"


def test_audit_only_row_builds_redispatch_envelope(tmp_path):
    ledger = write_ledger(
        tmp_path,
        """| Task ID | Status | Summary | Blockers |
| --- | --- | --- | --- |
| `P0_DIAGNOSTIC_ONLY_2026_07_02` | `completed` | read-only diagnostic only, no production exposure | none |
""",
    )
    row = parse_markdown_table(ledger)[0]
    classification = classify_row(row)

    envelope = redispatch_envelope(classification, "2026_07_02")

    assert classification["audit_only"] is True
    assert envelope["task_id"] == "P0_REDISPATCH_PRODUCTION_REPAIR_FOR_P0_DIAGNOSTIC_ONLY_2026_07_02_2026_07_02"
    assert envelope["constraints"]["audit_only_result_forbidden"] is True
    assert "Implement a live repair" in envelope["objective"]


def test_prepared_next_task_is_not_counted_as_production(tmp_path):
    ledger = write_ledger(
        tmp_path,
        """| Task ID | Status | Summary | Blockers |
| --- | --- | --- | --- |
| `P0_NEXT_DIAGNOSTIC_2026_07_02` | `next_prepared` | Factory Control deploy canary passed; next diagnose ownership without mutation | none |
""",
    )

    report = aggregate(parse_markdown_table(ledger), "2026_07_02")

    assert report["production_outcomes"] == []
    assert report["audit_only_failures"] == []
