#!/usr/bin/env python3
"""Collect current local/legacy factory result summaries."""

from __future__ import annotations

import json
from pathlib import Path

from common import FACTORY, ROOT, count_task_files, load_json, write_json


def main() -> int:
    legacy_state = ROOT / "logs" / "agent-factory" / "state.json"
    summary = {
        "collected_at": None,
        "legacy_state": str(legacy_state),
        "legacy_exists": legacy_state.exists(),
        "task_files": count_task_files(),
        "legacy_counts": {}
    }
    if legacy_state.exists():
        state = load_json(legacy_state)
        counts: dict[str, int] = {}
        for task in state.get("tasks", {}).values():
            status = task.get("status", "unknown")
            counts[status] = counts.get(status, 0) + 1
        summary["legacy_counts"] = counts
        summary["collected_at"] = state.get("updated_at")
    out = FACTORY / "runs" / "collect_summary.json"
    write_json(out, summary)
    print(json.dumps({"ok": True, "artifact": str(out), **summary}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
