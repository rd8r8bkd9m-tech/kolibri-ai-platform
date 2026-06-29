#!/usr/bin/env python3
"""Create GitHub PRs for Control Plane tasks that reached waiting_review.

This is the central GitHub gate for the factory: a pushed agent branch is not a
complete visible handoff until GitHub has a PR and Control Plane stores that PR
URL back on the task result.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.request
from typing import Any


DEFAULT_CONTROL_URL = "http://10.99.0.2:9101"
DEFAULT_REPO = "rd8r8bkd9m-tech/kolibri-ai-platform"


def http_json(method: str, url: str, body: dict[str, Any] | None = None, timeout: int = 30) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
        return json.loads(payload) if payload else {}


def normalize_base_ref(base_ref: str | None, fallback: str = "main") -> str:
    value = (base_ref or fallback).strip()
    for prefix in ("origin/", "refs/heads/"):
        if value.startswith(prefix):
            return value.removeprefix(prefix)
    return value or fallback


def task_pr_url(task: dict[str, Any]) -> str | None:
    result = task.get("result") or {}
    return result.get("pull_request_url") or result.get("pr_url")


def task_needs_central_pr(task: dict[str, Any]) -> bool:
    result = task.get("result") or {}
    return (
        task.get("state") == "waiting_review"
        and bool(result.get("needs_central_pr"))
        and bool(result.get("branch") or task.get("branch") or task.get("envelope", {}).get("branch"))
        and not task_pr_url(task)
    )


def branch_for_task(task: dict[str, Any]) -> str:
    result = task.get("result") or {}
    envelope = task.get("envelope") or {}
    return str(result.get("branch") or task.get("branch") or envelope.get("branch") or "")


def base_for_task(task: dict[str, Any], fallback: str) -> str:
    result = task.get("result") or {}
    envelope = task.get("envelope") or {}
    return normalize_base_ref(str(result.get("base_ref") or envelope.get("base_ref") or ""), fallback=fallback)


def pr_title(task: dict[str, Any]) -> str:
    task_id = str(task.get("task_id") or "factory-task")
    role = (task.get("envelope") or {}).get("role_slot")
    return f"factory: {task_id}" if not role else f"factory: {task_id} ({role})"


def pr_body(task: dict[str, Any]) -> str:
    result = task.get("result") or {}
    changed = result.get("changed_files") or []
    checks = result.get("checks") or []
    lines = [
        "## Factory handoff",
        "",
        f"- task_id: `{task.get('task_id')}`",
        f"- node_id: `{result.get('node_id')}`",
        f"- runner: `{result.get('runner')}`",
        f"- branch: `{branch_for_task(task)}`",
        f"- commit: `{result.get('commit')}`",
        f"- state before PR: `{task.get('state')}`",
        "",
        "## Changed files",
        "",
    ]
    lines.extend(f"- `{path}`" for path in changed) if changed else lines.append("- pending")
    lines.extend(["", "## Checks", ""])
    lines.extend(f"- `{check}`" for check in checks) if checks else lines.append("- pending")
    lines.extend(
        [
            "",
            "## Gate",
            "",
            "Created by `ops/github_pr_gate.py` so Control Plane, GitHub PRs, and review tasks stay in one visible workflow.",
        ]
    )
    return "\n".join(lines) + "\n"


def gh_json(args: list[str]) -> Any:
    completed = subprocess.run(["gh", *args], text=True, capture_output=True, check=True)
    return json.loads(completed.stdout or "null")


def existing_pr(repo: str, head: str, base: str) -> dict[str, Any] | None:
    prs = gh_json(["pr", "list", "--repo", repo, "--head", head, "--base", base, "--state", "open", "--json", "number,url"])
    return prs[0] if prs else None


def create_pr(repo: str, task: dict[str, Any], base: str, dry_run: bool = False) -> dict[str, Any]:
    head = branch_for_task(task)
    current = existing_pr(repo, head, base)
    if current:
        return {"url": current["url"], "number": current["number"], "created": False}
    if dry_run:
        return {"url": None, "number": None, "created": False, "dry_run": True}
    completed = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            repo,
            "--base",
            base,
            "--head",
            head,
            "--title",
            pr_title(task),
            "--body",
            pr_body(task),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    url = completed.stdout.strip().splitlines()[-1]
    number = int(url.rstrip("/").split("/")[-1])
    return {"url": url, "number": number, "created": True}


def annotate_task(control_url: str, task_id: str, pr: dict[str, Any], timeout: int = 30) -> Any:
    body = {
        "result": {
            "pull_request_url": pr["url"],
            "pr_url": pr["url"],
            "github_pr_number": pr["number"],
            "github_sync_status": "pr_created" if pr.get("created") else "pr_existing",
        }
    }
    return http_json("POST", f"{control_url}/v1/tasks/{task_id}/annotate", body, timeout=timeout)


def waiting_review_tasks(control_url: str, limit: int, timeout: int) -> list[dict[str, Any]]:
    payload = http_json("GET", f"{control_url}/v1/tasks?state=waiting_review&limit={limit}", timeout=timeout)
    return payload.get("tasks", [])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-url", default=DEFAULT_CONTROL_URL)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--base", default="codex/factory-autonomy-pwa-billing")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    report: dict[str, Any] = {"checked": 0, "created": [], "existing": [], "skipped": []}
    for task in waiting_review_tasks(args.control_url, args.limit, args.timeout):
        report["checked"] += 1
        if not task_needs_central_pr(task):
            report["skipped"].append({"task_id": task.get("task_id"), "reason": "not_needing_pr"})
            continue
        base = base_for_task(task, args.base)
        pr = create_pr(args.repo, task, base, dry_run=args.dry_run)
        if pr.get("url") and not args.dry_run:
            annotate_task(args.control_url, str(task["task_id"]), pr, timeout=args.timeout)
        target = "created" if pr.get("created") else "existing"
        report[target].append({"task_id": task.get("task_id"), "branch": branch_for_task(task), "base": base, **pr})
    report["created_total"] = len(report["created"])
    report["existing_total"] = len(report["existing"])
    report["skipped_total"] = len(report["skipped"])
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
