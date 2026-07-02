#!/usr/bin/env python3
"""Aggregate production outcomes from a Kolibri execution wave.

The dispatcher ledgers mix live repairs, PR work, deploy blockers, diagnostics,
and audit-only reports. This module keeps the production rollup narrow: only
outcomes with a PR, live runtime repair, verified canary, useful tests, or an
exact deploy blocker are treated as production output. Audit-only rows are
converted into redispatch repair envelopes so the next wave does implementation
instead of another report.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASK_RE = re.compile(r"\b[A-Z0-9][A-Z0-9_-]*_2026_07_02\b")
PR_RE = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/\d+")
TEST_RE = re.compile(r"\b\d+\s+passed(?:,\s*\d+\s+warning)?\b")

PRODUCTION_MARKERS = (
    "pull/",
    "pr #",
    "branch ",
    "head ",
    "merged_to_main",
    "live ",
    "runtime ",
    "deploy",
    "canary",
    "rollback",
    "service active",
    "active/running",
    "http 200",
    "passed",
    "blocked",
    "blocker",
)

AUDIT_ONLY_MARKERS = (
    "audit-only",
    "report-only",
    "docs/audit",
    "diagnostic only",
    "read-only diagnostic",
    "read-only probe",
    "inventory",
    "readiness report",
    "planning task",
    "plan only",
    "no production exposure",
    "no product code",
    "no live",
    "no mutation",
)

BLOCKER_MARKERS = (
    "blocked",
    "blocker",
    "404",
    "missing",
    "inactive",
    "dead_letter",
    "rollback",
    "module not found",
    "modulenotfounderror",
    "auth",
)


@dataclass(frozen=True)
class LedgerRow:
    source: str
    columns: dict[str, str]

    @property
    def task_id(self) -> str:
        return strip_markdown(self.columns.get("Task ID") or self.columns.get("task_id") or "")

    @property
    def status(self) -> str:
        return strip_markdown(self.columns.get("Status") or "")

    @property
    def text(self) -> str:
        return " ".join(self.columns.values())


def strip_markdown(value: str) -> str:
    return value.replace("`", "").strip()


def split_markdown_row(line: str) -> list[str]:
    return [part.strip() for part in line.strip().strip("|").split("|")]


def parse_markdown_table(path: Path) -> list[LedgerRow]:
    rows: list[LedgerRow] = []
    headers: list[str] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = split_markdown_row(line)
        if not cells:
            continue
        if headers is None:
            headers = [strip_markdown(cell) for cell in cells]
            continue
        if all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        if len(cells) != len(headers):
            continue
        rows.append(LedgerRow(source=str(path), columns=dict(zip(headers, cells))))
    return rows


def rows_for_wave(rows: list[LedgerRow], wave_token: str) -> list[LedgerRow]:
    date_token = wave_token.replace("_", "-")
    return [
        row
        for row in rows
        if wave_token in row.task_id or wave_token in row.text or date_token in row.text
    ]


def classify_row(row: LedgerRow) -> dict[str, Any]:
    text = row.text.lower()
    task_id = row.task_id
    status_text = row.status.lower()
    pr_urls = sorted(set(PR_RE.findall(row.text)))
    tests = sorted(set(TEST_RE.findall(row.text)))
    next_tasks = sorted(set(task for task in TASK_RE.findall(row.text) if task != task_id))
    blocker = any(marker in text for marker in BLOCKER_MARKERS)
    audit_only = any(marker in text for marker in AUDIT_ONLY_MARKERS)
    has_production_marker = any(marker in text for marker in PRODUCTION_MARKERS)

    if status_text in {"prepared", "next_prepared"} and not pr_urls and not tests:
        kind = "next_task"
    elif pr_urls or ("pr #" in text and ("passed" in text or "ci" in text)):
        kind = "pr_branch"
    elif "rollback" in text or "active/running" in text or "service active" in text or "http 200" in text:
        kind = "live_repair"
    elif "canary" in text and ("passed" in text or "http 200" in text or "preflight ok" in text):
        kind = "verified_canary"
    elif blocker and has_production_marker:
        kind = "deploy_blocker"
    elif audit_only:
        kind = "audit_only"
    else:
        kind = "non_production"

    is_production = kind in {"pr_branch", "live_repair", "verified_canary", "deploy_blocker"}
    return {
        "task_id": task_id,
        "status": row.status,
        "kind": kind,
        "is_production": is_production,
        "audit_only": audit_only and not is_production,
        "pr_urls": pr_urls,
        "tests": tests,
        "next_tasks": next_tasks,
        "blocker": blocker,
        "source": row.source,
        "summary": strip_markdown(row.columns.get("Summary") or row.columns.get("Next action") or row.text),
        "blockers": strip_markdown(row.columns.get("Blockers") or ""),
    }


def redispatch_envelope(classification: dict[str, Any], wave_token: str) -> dict[str, Any]:
    source_task = classification["task_id"]
    task_id = f"P0_REDISPATCH_PRODUCTION_REPAIR_FOR_{source_task}_{wave_token}"
    safe_branch = task_id.lower().replace("_", "-")
    return {
        "task_id": task_id,
        "idempotency_key": task_id,
        "kind": "owner_remote_task",
        "priority": "P0",
        "required_capability": "generic_implementation",
        "runner": "codex",
        "agent_type": "production_repair",
        "agent_display_name": "Никита - Production Repair Engineer",
        "target_node_pool": "healthy_server_implementation_nodes",
        "preferred_nodes": ["primary-candidate", "home", "mesh-agent-01"],
        "allowed_nodes": ["primary-candidate", "home", "mesh-agent-01"],
        "avoid_nodes": ["main", "qjns", "uiap", "new"],
        "branch": f"agent/{safe_branch}",
        "base_branch": "main",
        "base_ref": "origin/main",
        "max_retries": 1,
        "create_review_on_complete": True,
        "goal": "Replace audit-only output with a production repair result.",
        "objective": (
            f"Source task {source_task} returned audit/report-only output. Implement a live repair, "
            "PR branch with tests, deployable artifact, or exact hard blocker with the command to unblock."
        ),
        "constraints": {
            "server_execution_required": True,
            "audit_only_result_forbidden": True,
            "hard_external_blocker_must_include_unblock_command": True,
            "secrets_redaction_required": True,
            "do_not_print_env": True,
            "do_not_print_keys_tokens_cookies_or_credentials": True,
            "destructive_git_commands_forbidden": True,
            "git_reset_forbidden": True,
            "git_clean_forbidden": True,
            "force_push_forbidden": True,
            "push_to_main_forbidden": True,
            "merge_forbidden": True,
            "use_clean_remote_worktree": True,
            "exact_run_artifacts_required": True,
        },
        "write_scope": [
            "ops/**",
            "backend/**",
            "frontend/**",
            "tests/**",
            f"docs/agent/runs/{task_id.lower().replace('_', '-')}/**",
        ],
        "required_outputs": [
            f"docs/agent/runs/{task_id.lower().replace('_', '-')}/PLAN.md",
            f"docs/agent/runs/{task_id.lower().replace('_', '-')}/ACTIONS.md",
            f"docs/agent/runs/{task_id.lower().replace('_', '-')}/TESTS.md",
            f"docs/agent/runs/{task_id.lower().replace('_', '-')}/RESULT.md",
            f"docs/agent/runs/{task_id.lower().replace('_', '-')}/NEXT.md",
        ],
        "source": {
            "kind": "production_result_aggregator",
            "source_task_id": source_task,
            "source_status": classification["status"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def aggregate(rows: list[LedgerRow], wave_token: str) -> dict[str, Any]:
    classifications = [classify_row(row) for row in rows_for_wave(rows, wave_token)]
    production = [item for item in classifications if item["is_production"]]
    audit_only = [item for item in classifications if item["audit_only"]]
    next_tasks = sorted({task for item in production for task in item["next_tasks"]})
    return {
        "wave_token": wave_token,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_outcomes": production,
        "audit_only_failures": audit_only,
        "redispatch_envelopes": [redispatch_envelope(item, wave_token) for item in audit_only],
        "next_execution_tasks": next_tasks,
        "pr_urls": sorted({url for item in production for url in item["pr_urls"]}),
        "tests": sorted({test for item in production for test in item["tests"]}),
        "deploy_blockers": [item for item in production if item["kind"] == "deploy_blocker" or item["blocker"]],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Production Execution Wave Result",
        "",
        f"Wave: `{report['wave_token']}`",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Production outcomes",
        "",
    ]
    if not report["production_outcomes"]:
        lines.append("- None.")
    for item in report["production_outcomes"]:
        lines.append(f"- `{item['task_id']}`: `{item['kind']}` / `{item['status']}` - {item['summary']}")
    lines.extend(["", "## PR URLs", ""])
    if not report["pr_urls"]:
        lines.append("- None in this wave.")
    else:
        lines.extend(f"- {url}" for url in report["pr_urls"])
    lines.extend(["", "## Tests", ""])
    if not report["tests"]:
        lines.append("- No explicit pass-count strings found in production rows.")
    else:
        lines.extend(f"- `{test}`" for test in report["tests"])
    lines.extend(["", "## Deploy blockers", ""])
    if not report["deploy_blockers"]:
        lines.append("- None.")
    for item in report["deploy_blockers"]:
        detail = item["blockers"] or item["summary"]
        lines.append(f"- `{item['task_id']}`: {detail}")
    lines.extend(["", "## Audit-only redispatch", ""])
    if not report["audit_only_failures"]:
        lines.append("- No audit-only failures found in this wave.")
    for envelope in report["redispatch_envelopes"]:
        lines.append(
            f"- `{envelope['task_id']}` redispatches `{envelope['source']['source_task_id']}` "
            "with `audit_only_result_forbidden=true`."
        )
    lines.extend(["", "## Next execution tasks", ""])
    if not report["next_execution_tasks"]:
        lines.append("- None extracted from production rows.")
    else:
        lines.extend(f"- `{task}`" for task in report["next_execution_tasks"])
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "PRODUCTION_WAVE_SUMMARY.md").write_text(render_markdown(report), encoding="utf-8")
    (output_dir / "production_wave_summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for envelope in report["redispatch_envelopes"]:
        path = output_dir / f"{envelope['task_id']}.json"
        path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wave-token", default="2026_07_02")
    parser.add_argument("--ledger", action="append", type=Path, default=[])
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)

    ledgers = args.ledger or [
        Path("docs/agent/dispatcher/REMOTE_RESULTS.md"),
        Path("docs/agent/dispatcher/QUEUE.md"),
    ]
    rows: list[LedgerRow] = []
    for ledger in ledgers:
        if ledger.exists():
            rows.extend(parse_markdown_table(ledger))
    report = aggregate(rows, args.wave_token)
    if args.output_dir:
        write_outputs(report, args.output_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
