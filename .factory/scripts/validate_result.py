#!/usr/bin/env python3
"""Validate a RESULT_ENVELOPE with local checks and no external dependency."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import required_fields


REQUIRED = [
    "task_id",
    "server_id",
    "status",
    "summary",
    "base_commit",
    "result_commit",
    "changed_files",
    "tests",
    "metrics",
    "artifacts",
    "warnings",
    "errors",
    "recommended_next_action",
]


def validate(payload: dict[str, Any]) -> list[str]:
    errors = required_fields(payload, REQUIRED)
    if payload.get("status") not in {"completed", "blocked", "failed"}:
        errors.append("status must be completed|blocked|failed")
    for field in ["changed_files", "tests", "artifacts", "warnings", "errors"]:
        if field in payload and not isinstance(payload[field], list):
            errors.append(f"{field} must be a list")
    for test in payload.get("tests", []):
        if not isinstance(test, dict):
            errors.append("tests[] must be an object")
            continue
        missing = required_fields(test, ["command", "status", "details"])
        errors.extend(f"tests[].{field} missing" for field in missing)
        if test.get("status") not in {"passed", "failed", "not_run"}:
            errors.append("tests[].status must be passed|failed|not_run")
    for artifact in payload.get("artifacts", []):
        if not isinstance(artifact, dict):
            errors.append("artifacts[] must be an object")
            continue
        missing = required_fields(artifact, ["path", "sha256", "size_bytes"])
        errors.extend(f"artifacts[].{field} missing" for field in missing)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result")
    args = parser.parse_args()

    path = Path(args.result)
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors = validate(payload)
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, ensure_ascii=True, indent=2))
        return 1
    print(json.dumps({"valid": True, "result": str(path)}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
