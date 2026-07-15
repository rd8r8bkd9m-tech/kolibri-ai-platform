#!/usr/bin/env python3
"""Result collector — aggregates task results from fleet nodes.

Tracks completions, failures, timeouts, and produces fleet-wide execution reports.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any
from datetime import datetime, timezone


@dataclass
class TaskResult:
    task_id: str
    node_id: str
    command: str
    state: str  # completed | failed | timeout
    submitted_at: str
    completed_at: str
    duration_sec: float
    output: Any = None
    error: str | None = None
    artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class ResultCollector:
    """Fleet-wide result aggregation and reporting."""

    def __init__(self):
        self._results: dict[str, TaskResult] = {}
        self._node_stats: dict[str, dict] = {}
        self._timeline: list[dict] = []

    def record(self, task_id: str, node_id: str, command: str, state: str,
               submitted_at: str, output: Any = None, error: str | None = None,
               artifacts: list[str] | None = None):
        now = datetime.now(timezone.utc).isoformat()
        try:
            sub = datetime.fromisoformat(submitted_at)
            comp = datetime.fromisoformat(now)
            duration = (comp - sub).total_seconds()
        except Exception:
            duration = 0.0

        result = TaskResult(
            task_id=task_id,
            node_id=node_id,
            command=command,
            state=state,
            submitted_at=submitted_at,
            completed_at=now,
            duration_sec=round(duration, 3),
            output=output,
            error=error,
            artifacts=artifacts or [],
        )
        self._results[task_id] = result

        ns = self._node_stats.setdefault(node_id, {
            "completed": 0, "failed": 0, "timeout": 0, "total": 0, "total_duration": 0.0,
        })
        ns[state] = ns.get(state, 0) + 1
        ns["total"] += 1
        ns["total_duration"] += duration

        self._timeline.append({
            "task_id": task_id,
            "node_id": node_id,
            "state": state,
            "time": now,
        })

    def get(self, task_id: str) -> TaskResult | None:
        return self._results.get(task_id)

    def node_report(self, node_id: str) -> dict:
        ns = self._node_stats.get(node_id, {})
        avg = ns["total_duration"] / ns["total"] if ns.get("total", 0) > 0 else 0
        return {
            "node_id": node_id,
            **ns,
            "avg_duration_sec": round(avg, 3),
        }

    def fleet_report(self) -> dict:
        total_completed = sum(s.get("completed", 0) for s in self._node_stats.values())
        total_failed = sum(s.get("failed", 0) for s in self._node_stats.values())
        total_timeout = sum(s.get("timeout", 0) for s in self._node_stats.values())
        total_tasks = total_completed + total_failed + total_timeout
        total_duration = sum(s.get("total_duration", 0) for s in self._node_stats.values())

        return {
            "total_tasks": total_tasks,
            "completed": total_completed,
            "failed": total_failed,
            "timeout": total_timeout,
            "success_rate": round(total_completed / total_tasks, 3) if total_tasks > 0 else 0,
            "avg_duration_sec": round(total_duration / total_tasks, 3) if total_tasks > 0 else 0,
            "nodes_used": len(self._node_stats),
        }

    def recent(self, limit: int = 20) -> list[dict]:
        return [r.to_dict() for r in list(self._results.values())[-limit:]]

    def failures(self) -> list[dict]:
        return [r.to_dict() for r in self._results.values() if r.state in ("failed", "timeout")]

    def clear(self):
        self._results.clear()
        self._node_stats.clear()
        self._timeline.clear()

    def export_json(self) -> str:
        return json.dumps({
            "report": self.fleet_report(),
            "results": [r.to_dict() for r in self._results.values()],
            "timeline": self._timeline,
        }, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    import random

    rc = ResultCollector()

    nodes = ["home", "main", "uiap", "qjns", "9fts"]
    for i in range(20):
        node = random.choice(nodes)
        state = random.choice(["completed", "completed", "completed", "failed"])
        rc.record(
            task_id=f"task-{i:03d}",
            node_id=node,
            command=f"build-module-{i}",
            state=state,
            submitted_at=datetime.now(timezone.utc).isoformat(),
            output={"status": state} if state == "completed" else None,
            error="build failed" if state == "failed" else None,
        )

    report = rc.fleet_report()
    print(f"Fleet report: {report}")

    for node in nodes:
        nr = rc.node_report(node)
        if nr.get("total", 0) > 0:
            print(f"  {node}: {nr}")
