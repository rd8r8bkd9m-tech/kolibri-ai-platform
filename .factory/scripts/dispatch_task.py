#!/usr/bin/env python3
"""Dispatch one task envelope or produce a dry-run dispatch artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from common import FACTORY, load_json, required_fields, write_json


TASK_REQUIRED = [
    "factory_run_id",
    "task_id",
    "server_id",
    "agent_role",
    "objective",
    "repository",
    "base_commit",
    "branch",
    "allowed_paths",
    "protected_paths",
    "acceptance_criteria",
    "required_tests",
    "resource_limits",
    "security_rules",
    "report_path",
]


def validate_task(task: dict) -> list[str]:
    errors = required_fields(task, TASK_REQUIRED)
    if not str(task.get("branch", "")).startswith("factory/"):
        errors.append("branch must start with factory/")
    if not task.get("allowed_paths"):
        errors.append("allowed_paths must not be empty")
    if not task.get("acceptance_criteria"):
        errors.append("acceptance_criteria must not be empty")
    if not task.get("security_rules"):
        errors.append("security_rules must not be empty")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    path = Path(args.task)
    task = load_json(path)
    errors = validate_task(task)
    if errors:
        print(json.dumps({"dispatched": False, "errors": errors}, ensure_ascii=True, indent=2))
        return 1

    if not args.dry_run:
        print(json.dumps({
            "dispatched": False,
            "blocked": "live SSH dispatch is gated until two dry-run canaries and schema checks pass",
            "task_id": task["task_id"]
        }, ensure_ascii=True, indent=2))
        return 2

    raw = path.read_bytes()
    artifact = {
        "dispatched": False,
        "dry_run": True,
        "task_id": task["task_id"],
        "server_id": task["server_id"],
        "agent_role": task["agent_role"],
        "task_sha256": hashlib.sha256(raw).hexdigest(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "next_action": "ready for Codex review before live SSH dispatch"
    }
    out = FACTORY / "runs" / f"{task['task_id']}.dry_run.json"
    write_json(out, artifact)
    print(json.dumps({"ok": True, "artifact": str(out), **artifact}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
