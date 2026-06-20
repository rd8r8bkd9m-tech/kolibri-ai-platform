#!/usr/bin/env python3
"""Smoke tests for Factory v1 contract files."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FACTORY = ROOT / ".factory"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_server_inventory_has_19_unique_servers() -> None:
    inventory = load(FACTORY / "server_inventory.json")
    ids = [server["id"] for server in inventory["servers"]]
    assert len(ids) == 19
    assert len(set(ids)) == 19


def test_canary_tasks_have_distinct_servers() -> None:
    canary1 = load(FACTORY / "tasks" / "ready" / "KOL-CANARY-001.json")
    canary2 = load(FACTORY / "tasks" / "ready" / "KOL-CANARY-002.json")
    assert canary1["server_id"] != canary2["server_id"]
    assert canary1["branch"].startswith("factory/")
    assert canary2["branch"].startswith("factory/")


def test_result_fixture_contract() -> None:
    result = load(FACTORY / "templates" / "result_envelope.json")
    required = {
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
    }
    assert required.issubset(result)
    assert result["status"] in {"completed", "blocked", "failed"}


if __name__ == "__main__":
    test_server_inventory_has_19_unique_servers()
    test_canary_tasks_have_distinct_servers()
    test_result_fixture_contract()
    print("factory contract tests passed")
