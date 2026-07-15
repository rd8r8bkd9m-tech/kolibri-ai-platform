#!/usr/bin/env python3
"""Redis-backed task queue for fleet execution.

Supports priority queues, deduplication, and state machine transitions.
Runs locally — talks to Control Plane on Home via remote_exec.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Literal
from datetime import datetime, timezone

Priority = Literal["critical", "high", "normal", "low", "background"]
TaskState = Literal["pending", "queued", "leased", "running", "completed", "failed", "cancelled"]

PRIORITY_WEIGHT = {"critical": 0, "high": 1, "normal": 2, "low": 3, "background": 4}


@dataclass
class TaskEnvelope:
    task_id: str
    node_id: str | None
    command: str
    payload: dict = field(default_factory=dict)
    priority: Priority = "normal"
    state: TaskState = "pending"
    created_at: str = ""
    leased_at: str | None = None
    completed_at: str | None = None
    timeout_sec: int = 300
    retry_count: int = 0
    max_retries: int = 2
    result: dict | None = None
    error: str | None = None
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> TaskEnvelope:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})


class TaskQueue:
    """Local in-memory task queue with priority ordering."""

    def __init__(self):
        self._tasks: dict[str, TaskEnvelope] = {}
        self._queue: list[str] = []  # task_ids in priority order

    def enqueue(self, command: str, node_id: str | None = None, payload: dict | None = None,
                priority: Priority = "normal", tags: list[str] | None = None,
                timeout_sec: int = 300) -> TaskEnvelope:
        task = TaskEnvelope(
            task_id=str(uuid.uuid4())[:12],
            node_id=node_id,
            command=command,
            payload=payload or {},
            priority=priority,
            state="queued",
            timeout_sec=timeout_sec,
            tags=tags or [],
        )
        self._tasks[task.task_id] = task
        self._insert_by_priority(task.task_id)
        return task

    def _insert_by_priority(self, task_id: str):
        task = self._tasks[task_id]
        pw = PRIORITY_WEIGHT[task.priority]
        for i, tid in enumerate(self._queue):
            t = self._tasks.get(tid)
            if t and PRIORITY_WEIGHT[t.priority] > pw:
                self._queue.insert(i, task_id)
                return
        self._queue.append(task_id)

    def dequeue(self, node_id: str | None = None) -> TaskEnvelope | None:
        for i, task_id in enumerate(self._queue):
            task = self._tasks[task_id]
            if task.state != "queued":
                self._queue.pop(i)
                continue
            if node_id and task.node_id and task.node_id != node_id:
                continue
            self._queue.pop(i)
            task.state = "leased"
            task.leased_at = datetime.now(timezone.utc).isoformat()
            return task
        return None

    def complete(self, task_id: str, result: dict | None = None):
        task = self._tasks.get(task_id)
        if task:
            task.state = "completed"
            task.result = result
            task.completed_at = datetime.now(timezone.utc).isoformat()

    def fail(self, task_id: str, error: str):
        task = self._tasks.get(task_id)
        if task:
            task.state = "failed"
            task.error = error
            task.completed_at = datetime.now(timezone.utc).isoformat()
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.state = "queued"
                task.leased_at = None
                task.completed_at = None
                self._insert_by_priority(task_id)

    def cancel(self, task_id: str):
        task = self._tasks.get(task_id)
        if task:
            task.state = "cancelled"

    def get(self, task_id: str) -> TaskEnvelope | None:
        return self._tasks.get(task_id)

    def pending_count(self) -> int:
        return sum(1 for t in self._tasks.values() if t.state in ("pending", "queued"))

    def stats(self) -> dict:
        counts: dict[str, int] = {}
        for t in self._tasks.values():
            counts[t.state] = counts.get(t.state, 0) + 1
        return {"total": len(self._tasks), **counts, "queue_depth": len(self._queue)}

    def all_tasks(self) -> list[dict]:
        return [t.to_dict() for t in self._tasks.values()]

    def queue_ids(self) -> list[str]:
        return list(self._queue)


if __name__ == "__main__":
    q = TaskQueue()
    t1 = q.enqueue("build", priority="high", tags=["build"])
    t2 = q.enqueue("test", priority="normal", tags=["test"])
    t3 = q.enqueue("deploy", priority="critical", tags=["deploy"])
    print(f"Enqueued 3 tasks: {q.stats()}")
    while task := q.dequeue():
        print(f"  Dequeued: {task.task_id} priority={task.priority} command={task.command}")
        q.complete(task.task_id, {"output": "done"})
    print(f"After drain: {q.stats()}")
