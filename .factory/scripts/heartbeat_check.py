#!/usr/bin/env python3
"""Check task heartbeat files for stale state."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from common import FACTORY, load_json


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stale-seconds", type=int, default=900)
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    statuses = []
    for path in (FACTORY / "runs" / "status").glob("*.json"):
        payload = load_json(path)
        heartbeat = payload.get("heartbeat_at")
        age = None
        stale = True
        if heartbeat:
            age = (now - parse_iso(heartbeat)).total_seconds()
            stale = age > args.stale_seconds
        statuses.append({"path": str(path), "task_id": payload.get("task_id"), "state": payload.get("state"), "age_seconds": age, "stale": stale})

    print(json.dumps({"checked": len(statuses), "statuses": statuses}, ensure_ascii=True, indent=2))
    return 1 if any(item["stale"] for item in statuses) else 0


if __name__ == "__main__":
    raise SystemExit(main())
