#!/usr/bin/env python3
"""Shared helpers for Kolibri Factory v1 scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FACTORY = ROOT / ".factory"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp.replace(path)


def required_fields(payload: dict[str, Any], fields: list[str]) -> list[str]:
    return [field for field in fields if field not in payload]


def count_task_files() -> dict[str, int]:
    task_root = FACTORY / "tasks"
    states = ["ready", "running", "review", "blocked", "completed", "failed"]
    return {
        state: len(list((task_root / state).glob("*.json"))) if (task_root / state).exists() else 0
        for state in states
    }
