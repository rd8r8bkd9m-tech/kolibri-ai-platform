#!/usr/bin/env python3
"""GitHub release-train steward for Kolibri pull requests.

The bot is intentionally conservative:

* dry-run is the default;
* PR mutation requires ``--apply``;
* owner approval is always a merge blocker, never inferred;
* no merge, approval, mark-ready, close, or push operation is implemented here.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OWNER_GATE_TEXT = "Owner approval required before merge. This bot never merges to main."
BOT_BLOCK_START = "<!-- kolibri-release-train:start -->"
BOT_BLOCK_END = "<!-- kolibri-release-train:end -->"
DEFAULT_TASK_DIR = Path("docs/agent/repair_tasks")

PASSING_CHECKS = {"SUCCESS", "PASS", "PASSED", "NEUTRAL", "SKIPPED"}
FAILING_CHECKS = {"FAILURE", "FAILED", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"}
PENDING_CHECKS = {"PENDING", "QUEUED", "IN_PROGRESS", "WAITING", "REQUESTED", "EXPECTED"}


@dataclass(frozen=True)
class CheckSummary:
    conclusion: str
    failing: tuple[str, ...] = ()
    pending: tuple[str, ...] = ()


@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    head_ref: str
    base_ref: str = "main"
    body: str = ""
    draft: bool = False
    mergeable: str = "UNKNOWN"
    merge_state_status: str = "UNKNOWN"
    review_decision: str = ""
    labels: tuple[str, ...] = ()
    updated_at: str = ""
    checks: CheckSummary = field(default_factory=lambda: CheckSummary("UNKNOWN"))


@dataclass(frozen=True)
class MainFreshness:
    ok: bool
    local_sha: str
    remote_sha: str
    reason: str


@dataclass(frozen=True)
class Classification:
    pr: PullRequest
    state: str
    owner_gate: bool
    repair_required: bool
    reasons: tuple[str, ...]
    next_action: str


def run_command(args: list[str], cwd: Path | None = None) -> str:
    try:
        proc = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError(f"required executable not found: {exc.filename}") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def git_output(args: list[str], repo: Path) -> str:
    return run_command(["git", *args], cwd=repo).strip()


def main_freshness(repo: Path) -> MainFreshness:
    local_sha = git_output(["rev-parse", "origin/main"], repo)
    remote_line = git_output(["ls-remote", "origin", "refs/heads/main"], repo)
    remote_sha = remote_line.split()[0] if remote_line else ""
    if not remote_sha:
        return MainFreshness(False, local_sha, remote_sha, "remote main SHA unavailable")
    if local_sha != remote_sha:
        return MainFreshness(False, local_sha, remote_sha, "origin/main is stale versus remote refs/heads/main")
    return MainFreshness(True, local_sha, remote_sha, "origin/main matches remote refs/heads/main")


def _status_name(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("context") or item.get("workflowName") or item.get("displayName") or "unnamed-check")


def summarize_checks(status_rollup: Any) -> CheckSummary:
    if not isinstance(status_rollup, list):
        return CheckSummary("UNKNOWN")

    failing: list[str] = []
    pending: list[str] = []
    saw_check = False
    for item in status_rollup:
        if not isinstance(item, dict):
            continue
        saw_check = True
        conclusion = str(item.get("conclusion") or item.get("state") or item.get("status") or "").upper()
        name = _status_name(item)
        if conclusion in FAILING_CHECKS:
            failing.append(name)
        elif conclusion in PENDING_CHECKS or not conclusion:
            pending.append(name)
        elif conclusion not in PASSING_CHECKS:
            pending.append(name)

    if failing:
        return CheckSummary("FAILURE", tuple(sorted(failing)), tuple(sorted(pending)))
    if pending:
        return CheckSummary("PENDING", (), tuple(sorted(pending)))
    if saw_check:
        return CheckSummary("SUCCESS")
    return CheckSummary("UNKNOWN")


def pr_from_gh(raw: dict[str, Any]) -> PullRequest:
    labels = tuple(sorted(str(label.get("name") or label) for label in raw.get("labels") or []))
    return PullRequest(
        number=int(raw["number"]),
        title=str(raw.get("title") or ""),
        head_ref=str(raw.get("headRefName") or ""),
        base_ref=str(raw.get("baseRefName") or "main"),
        body=str(raw.get("body") or ""),
        draft=bool(raw.get("isDraft")),
        mergeable=str(raw.get("mergeable") or "UNKNOWN").upper(),
        merge_state_status=str(raw.get("mergeStateStatus") or "UNKNOWN").upper(),
        review_decision=str(raw.get("reviewDecision") or "").upper(),
        labels=labels,
        updated_at=str(raw.get("updatedAt") or ""),
        checks=summarize_checks(raw.get("statusCheckRollup")),
    )


def classify_pr(pr: PullRequest, freshness: MainFreshness) -> Classification:
    reasons: list[str] = [OWNER_GATE_TEXT]
    repair_required = False

    if pr.base_ref != "main":
        reasons.append(f"base branch is {pr.base_ref}, not main")
        return Classification(pr, "out_of_train", True, False, tuple(reasons), "leave outside main release train")

    if not freshness.ok:
        reasons.append(f"main freshness blocked: {freshness.reason}")
        return Classification(pr, "blocked_main_freshness", True, False, tuple(reasons), "refresh main freshness before train mutation")

    if pr.checks.conclusion == "FAILURE":
        repair_required = True
        reasons.append("one or more required checks failed")
        return Classification(pr, "repair_required", True, repair_required, tuple(reasons), "open repair task for failing checks")

    if pr.checks.conclusion in {"PENDING", "UNKNOWN"}:
        reasons.append(f"checks are {pr.checks.conclusion.lower()}")
        return Classification(pr, "waiting_for_ci", True, False, tuple(reasons), "wait for CI to complete before release ordering")

    if pr.mergeable not in {"MERGEABLE", "YES", "CLEAN", "TRUE"} and pr.merge_state_status not in {"CLEAN", "HAS_HOOKS"}:
        reasons.append(f"mergeability is {pr.mergeable}/{pr.merge_state_status}")
        return Classification(pr, "blocked_mergeability", True, False, tuple(reasons), "repair merge conflicts or branch protection blockers")

    if pr.draft:
        reasons.append("PR is still draft")
        return Classification(pr, "owner_review_ready_draft", True, False, tuple(reasons), "owner may review and decide whether to mark ready")

    if pr.review_decision not in {"APPROVED"}:
        reasons.append("owner approval is not recorded")
        return Classification(pr, "owner_approval_required", True, False, tuple(reasons), "request explicit owner approval")

    reasons.append("green, non-draft, approved; merge still requires owner-controlled release action")
    return Classification(pr, "release_ready_owner_merge_only", True, False, tuple(reasons), "owner may merge from GitHub UI or approved release command")


def render_train_block(classification: Classification, freshness: MainFreshness, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    pr = classification.pr
    checks = pr.checks
    failing = ", ".join(checks.failing) if checks.failing else "none"
    pending = ", ".join(checks.pending) if checks.pending else "none"
    reasons = "\n".join(f"- {reason}" for reason in classification.reasons)
    checklist = [
        f"- [{'x' if freshness.ok else ' '}] `origin/main` matches remote `main`",
        f"- [{'x' if checks.conclusion == 'SUCCESS' else ' '}] CI checks are green",
        f"- [{'x' if not pr.draft else ' '}] PR is not draft",
        f"- [{'x' if pr.review_decision == 'APPROVED' else ' '}] Owner approval recorded",
        "- [ ] Owner-approved merge performed outside this bot",
    ]
    return "\n".join([
        BOT_BLOCK_START,
        "## Kolibri Release Train",
        "",
        f"Updated: `{timestamp}`",
        f"Classification: `{classification.state}`",
        f"Next action: `{classification.next_action}`",
        "",
        *checklist,
        "",
        "Reasons:",
        reasons,
        "",
        f"Checks: `{checks.conclusion}`; failing: {failing}; pending: {pending}",
        f"Main freshness: `{freshness.reason}`",
        "",
        f"Policy: {OWNER_GATE_TEXT}",
        BOT_BLOCK_END,
    ])


def update_body(existing: str, block: str) -> str:
    if BOT_BLOCK_START in existing and BOT_BLOCK_END in existing:
        before, rest = existing.split(BOT_BLOCK_START, 1)
        _, after = rest.split(BOT_BLOCK_END, 1)
        return f"{before.rstrip()}\n\n{block}\n{after.lstrip()}".strip() + "\n"
    if existing.strip():
        return f"{existing.rstrip()}\n\n{block}\n"
    return f"{block}\n"


def repair_task_payload(classification: Classification, task_dir: Path) -> dict[str, Any]:
    pr = classification.pr
    task_id = f"P0_REPAIR_PR_{pr.number}_CI_RELEASE_TRAIN"
    return {
        "task_id": task_id,
        "idempotency_key": task_id,
        "kind": "github_pr_repair",
        "priority": "p0",
        "pr": {
            "number": pr.number,
            "title": pr.title,
            "head_ref": pr.head_ref,
            "base_ref": pr.base_ref,
        },
        "failing_checks": list(pr.checks.failing),
        "pending_checks": list(pr.checks.pending),
        "classification": classification.state,
        "repair_goal": "repair failing checks on the PR branch; do not merge to main without owner approval",
        "canonical_run_artifact_dir": f"docs/agent/runs/{task_id}",
        "output_path": str(task_dir / f"pr-{pr.number}-repair-task.json"),
        "forbidden_actions": ["print_secrets", "force_push", "push_to_main", "merge_without_owner_approval"],
    }


def load_prs_with_gh(repo: Path) -> list[PullRequest]:
    fields = [
        "number",
        "title",
        "isDraft",
        "mergeable",
        "mergeStateStatus",
        "headRefName",
        "baseRefName",
        "body",
        "labels",
        "reviewDecision",
        "updatedAt",
        "statusCheckRollup",
    ]
    raw = run_command(["gh", "pr", "list", "--state", "open", "--limit", "100", "--json", ",".join(fields)], cwd=repo)
    return [pr_from_gh(item) for item in json.loads(raw)]


def edit_pr_body(repo: Path, pr_number: int, body: str) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(body)
        body_path = handle.name
    try:
        run_command(["gh", "pr", "edit", str(pr_number), "--body-file", body_path], cwd=repo)
    finally:
        Path(body_path).unlink(missing_ok=True)


def open_repair_issue(repo: Path, payload: dict[str, Any]) -> None:
    title = f"[release-train] Repair PR #{payload['pr']['number']} failing checks"
    body = json.dumps(payload, indent=2, sort_keys=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write("```json\n")
        handle.write(body)
        handle.write("\n```\n")
        body_path = handle.name
    try:
        run_command(["gh", "issue", "create", "--title", title, "--body-file", body_path, "--label", "release-train,repair"], cwd=repo)
    finally:
        Path(body_path).unlink(missing_ok=True)


def write_repair_task(task_dir: Path, payload: dict[str, Any]) -> Path:
    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / f"pr-{payload['pr']['number']}-repair-task.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def execute(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    freshness = main_freshness(repo)
    prs = load_prs_with_gh(repo)
    selected = {int(value) for value in args.pr} if args.pr else None
    classifications = [classify_pr(pr, freshness) for pr in prs if selected is None or pr.number in selected]

    result: dict[str, Any] = {
        "mode": "apply" if args.apply else "dry-run",
        "main_freshness": freshness.__dict__,
        "classifications": [],
        "mutations": [],
    }

    for classification in classifications:
        pr = classification.pr
        block = render_train_block(classification, freshness)
        new_body = update_body(pr.body, block)
        result["classifications"].append({
            "pr": pr.number,
            "title": pr.title,
            "state": classification.state,
            "next_action": classification.next_action,
            "repair_required": classification.repair_required,
            "owner_gate": classification.owner_gate,
            "reasons": list(classification.reasons),
        })

        if args.apply and args.update_bodies:
            edit_pr_body(repo, pr.number, new_body)
            result["mutations"].append({"kind": "pr_body_updated", "pr": pr.number})
        elif args.update_bodies:
            result["mutations"].append({"kind": "would_update_pr_body", "pr": pr.number})

        if classification.repair_required:
            payload = repair_task_payload(classification, Path(args.repair_task_dir))
            if args.apply and args.repair_task_mode == "issue":
                open_repair_issue(repo, payload)
                result["mutations"].append({"kind": "repair_issue_opened", "pr": pr.number})
            elif args.apply and args.repair_task_mode == "artifact":
                path = write_repair_task(Path(args.repair_task_dir), payload)
                result["mutations"].append({"kind": "repair_task_written", "pr": pr.number, "path": str(path)})
            else:
                result["mutations"].append({"kind": "would_open_repair_task", "pr": pr.number, "mode": args.repair_task_mode})

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if freshness.ok else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Classify and maintain the Kolibri GitHub release train.")
    parser.add_argument("--repo", default=".", help="repository checkout")
    parser.add_argument("--pr", action="append", default=[], help="limit to one PR number; can be repeated")
    parser.add_argument("--apply", action="store_true", help="perform allowed mutations; dry-run is default")
    parser.add_argument("--update-bodies", action="store_true", help="insert/update release-train block in PR bodies")
    parser.add_argument("--repair-task-mode", choices=("artifact", "issue"), default="artifact")
    parser.add_argument("--repair-task-dir", default=str(DEFAULT_TASK_DIR))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return execute(args)
    except RuntimeError as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
