#!/usr/bin/env python3
"""Task Scheduler — cron-like scheduling for fleet operations."""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

CONTROL_PLANE = "http://192.168.88.210:9101"


@dataclass
class Schedule:
    schedule_id: str
    cron: str
    task: str
    node_id: str
    last_run: str | None = None
    next_run: str | None = None
    status: str = "active"

    def to_dict(self) -> dict:
        return asdict(self)


_schedules: dict[str, Schedule] = {}


def _request(method: str, url: str, data: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def add_schedule(cron: str, task: str, node_id: str) -> Schedule:
    schedule_id = f"SCHED-{int(datetime.now(timezone.utc).timestamp())}"
    schedule = Schedule(
        schedule_id=schedule_id,
        cron=cron,
        task=task,
        node_id=node_id,
    )
    _schedules[schedule_id] = schedule
    return schedule


def list_schedules() -> list[Schedule]:
    return list(_schedules.values())


def run_schedule(schedule_id: str) -> dict:
    schedule = _schedules.get(schedule_id)
    if not schedule:
        return {"error": "Schedule not found"}
    schedule.last_run = datetime.now(timezone.utc).isoformat()
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": schedule.node_id,
        "command": schedule.task,
        "objective": f"Scheduled task: {schedule.task}",
        "kind": "generic_implementation",
    })


def remove_schedule(schedule_id: str) -> bool:
    return _schedules.pop(schedule_id, None) is not None


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: task_scheduler.py <list|run> [schedule_id]")
        sys.exit(1)

    action = sys.argv[1]
    if action == "list":
        for s in list_schedules():
            print(f"  {s.schedule_id}: {s.cron} -> {s.task} on {s.node_id}")
    elif action == "run" and len(sys.argv) > 2:
        print(json.dumps(run_schedule(sys.argv[2]), indent=2))
