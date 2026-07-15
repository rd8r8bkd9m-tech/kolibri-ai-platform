#!/usr/bin/env python3
"""Fleet orchestrator — unified interface for fleet execution.

Brings together: fleet_classification, remote_exec, task_queue,
worker_pool, slot_manager, load_balancer, result_collector.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from datetime import datetime, timezone

from fleet_classification import build_fleet_classification
from task_queue import TaskQueue
from worker_pool import WorkerPool
from slot_manager import SlotManager
from load_balancer import LoadBalancer
from result_collector import ResultCollector
from remote_exec import submit_task, wait_for_task, register_node, heartbeat


class FleetOrchestrator:
    """Unified fleet orchestration — register, schedule, execute, collect."""

    def __init__(self, slots_per_node: int = 50, strategy: str = "least_loaded"):
        self.fc = build_fleet_classification()
        self.queue = TaskQueue()
        self.pool = WorkerPool(slots_per_node=slots_per_node)
        self.slots = SlotManager(slots_per_node=slots_per_node)
        self.balancer = LoadBalancer(strategy=strategy)
        self.collector = ResultCollector()
        self._registered = False

    def register_fleet(self) -> dict:
        results = {"registered": 0, "failed": 0, "nodes": []}
        for nid, s in self.fc.servers.items():
            resp = register_node(nid, s.canonical_name, ["generic"], s.api_port or 8001)
            ok = "node_id" in resp
            if ok:
                self.pool.register_node(nid, s.canonical_name, s.tier, ["generic"])
                self.slots.init_node(nid)
                self.balancer.register(nid, s.tier, slots_per_node := 50, ["generic"])
                results["registered"] += 1
            else:
                results["failed"] += 1
            results["nodes"].append({"node_id": nid, "ok": ok})
        self._registered = True
        return results

    def submit(self, command: str, node_id: str | None = None, payload: dict | None = None,
               priority: str = "normal", tags: list[str] | None = None) -> dict:
        task = self.queue.enqueue(command, node_id, payload, priority, tags or [])
        node = node_id or self.balancer.select()
        if not node:
            return {"error": "no_available_node", "task_id": task.task_id}

        slot = self.slots.acquire(node, task.task_id)
        if not slot:
            return {"error": "no_free_slots", "node_id": node, "task_id": task.task_id}

        acquired = self.pool.acquire(node, task.task_id)
        if not acquired:
            self.slots.release(slot.slot_id)
            return {"error": "pool_acquire_failed", "node_id": node, "task_id": task.task_id}

        resp = submit_task(node, command, payload)
        return {
            "task_id": task.task_id,
            "node_id": node,
            "slot_id": slot.slot_id,
            "remote_task_id": resp.task_id,
            "status": "submitted",
        }

    def submit_parallel(self, command: str, payload: dict | None = None,
                        count: int = 1, priority: str = "normal") -> list[dict]:
        results = []
        for i in range(count):
            r = self.submit(f"{command}-{i}", payload=payload, priority=priority)
            results.append(r)
        return results

    def collect_result(self, task_id: str) -> dict:
        task = self.queue.get(task_id)
        if not task:
            return {"error": "task_not_found"}

        remote_task_id = task.result.get("remote_task_id") if task.result else task_id
        remote = wait_for_task(remote_task_id, max_wait=5.0)

        state = remote.get("state", "unknown")
        self.queue.complete(task_id, remote) if state == "completed" else self.queue.fail(task_id, str(remote.get("error", "failed")))

        node_id = ""
        for sid, nid in self.pool._task分配.items():
            if sid == task_id:
                node_id = nid
                break

        self.collector.record(task_id, node_id, task.command, state, task.created_at,
                              output=remote.get("result"), error=remote.get("error"))

        self.pool.release(task_id)
        self.slots.release_by_task(task_id)

        return {"task_id": task_id, "state": state, "result": remote}

    def fleet_status(self) -> dict:
        return {
            "fleet": self.fc.summary_table(),
            "pool": self.pool.fleet_stats(),
            "slots": self.slots.fleet_stats(),
            "queue": self.queue.stats(),
            "balancer": self.balancer.stats(),
            "report": self.collector.fleet_report(),
        }


if __name__ == "__main__":
    orch = FleetOrchestrator(slots_per_node=50)

    print("=== Fleet Classification ===")
    print(orch.fc.summary_table())
    print()

    print("=== Fleet Status ===")
    status = orch.fleet_status()
    print(json.dumps({k: v for k, v in status.items() if k != "fleet"}, indent=2))
    print()

    print("=== Test Submit ===")
    for i in range(3):
        r = orch.submit(f"test-task-{i}", priority="normal")
        print(f"  {r}")
