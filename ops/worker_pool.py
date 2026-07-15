#!/usr/bin/env python3
"""Worker pool — manages execution capacity across fleet nodes.

Each node has N slots (default 50). Pool tracks allocation, health,
and provides acquire/release semantics for task execution.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime, timezone

DEFAULT_SLOTS_PER_NODE = 50
HEALTH_CHECK_INTERVAL = 30


@dataclass
class NodeCapacity:
    node_id: str
    hostname: str
    max_slots: int = DEFAULT_SLOTS_PER_NODE
    allocated_slots: int = 0
    health: str = "online"  # online | degraded | offline | draining
    last_heartbeat: str = ""
    tier: str = "execution"
    capabilities: list[str] = field(default_factory=lambda: ["generic"])

    @property
    def free_slots(self) -> int:
        return self.max_slots - self.allocated_slots

    @property
    def utilization(self) -> float:
        return self.allocated_slots / self.max_slots if self.max_slots > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "max_slots": self.max_slots,
            "allocated_slots": self.allocated_slots,
            "free_slots": self.free_slots,
            "utilization": round(self.utilization, 3),
            "health": self.health,
            "tier": self.tier,
            "capabilities": self.capabilities,
        }


class WorkerPool:
    """Fleet-wide worker pool with slot-based capacity management."""

    def __init__(self, slots_per_node: int = DEFAULT_SLOTS_PER_NODE):
        self._nodes: dict[str, NodeCapacity] = {}
        self._slots_per_node = slots_per_node
        self._task分配: dict[str, str] = {}  # task_id -> node_id

    def register_node(self, node_id: str, hostname: str, tier: str = "execution",
                      capabilities: list[str] | None = None, max_slots: int | None = None):
        self._nodes[node_id] = NodeCapacity(
            node_id=node_id,
            hostname=hostname,
            max_slots=max_slots or self._slots_per_node,
            tier=tier,
            capabilities=capabilities or ["generic"],
            last_heartbeat=datetime.now(timezone.utc).isoformat(),
        )

    def remove_node(self, node_id: str):
        self._nodes.pop(node_id, None)

    def acquire(self, node_id: str, task_id: str) -> bool:
        node = self._nodes.get(node_id)
        if not node or node.health not in ("online", "degraded") or node.free_slots <= 0:
            return False
        node.allocated_slots += 1
        self._task分配[task_id] = node_id
        return True

    def release(self, task_id: str):
        node_id = self._task分配.pop(task_id, None)
        if node_id:
            node = self._nodes.get(node_id)
            if node and node.allocated_slots > 0:
                node.allocated_slots -= 1

    def best_node(self, required_capability: str | None = None,
                  prefer_tier: str | None = None) -> NodeCapacity | None:
        candidates = []
        for node in self._nodes.values():
            if node.health not in ("online", "degraded"):
                continue
            if node.free_slots <= 0:
                continue
            if required_capability and required_capability not in node.capabilities:
                continue
            candidates.append(node)

        if prefer_tier:
            tier_matches = [n for n in candidates if n.tier == prefer_tier]
            if tier_matches:
                candidates = tier_matches

        if not candidates:
            return None

        candidates.sort(key=lambda n: (n.utilization, n.allocated_slots))
        return candidates[0]

    def update_health(self, node_id: str, health: str):
        node = self._nodes.get(node_id)
        if node:
            node.health = health
            node.last_heartbeat = datetime.now(timezone.utc).isoformat()

    def fleet_stats(self) -> dict:
        total_slots = sum(n.max_slots for n in self._nodes.values())
        used_slots = sum(n.allocated_slots for n in self._nodes.values())
        return {
            "nodes": len(self._nodes),
            "total_slots": total_slots,
            "used_slots": used_slots,
            "free_slots": total_slots - used_slots,
            "utilization": round(used_slots / total_slots, 3) if total_slots > 0 else 0,
            "online": sum(1 for n in self._nodes.values() if n.health == "online"),
            "degraded": sum(1 for n in self._nodes.values() if n.health == "degraded"),
            "offline": sum(1 for n in self._nodes.values() if n.health in ("offline", "draining")),
        }

    def node_details(self) -> list[dict]:
        return sorted([n.to_dict() for n in self._nodes.values()],
                      key=lambda x: x["node_id"])

    def drain_node(self, node_id: str):
        node = self._nodes.get(node_id)
        if node:
            node.health = "draining"

    def nodes_by_tier(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for node in self._nodes.values():
            result.setdefault(node.tier, []).append(node.node_id)
        return result


if __name__ == "__main__":
    from fleet_classification import build_fleet_classification

    fc = build_fleet_classification()
    pool = WorkerPool(slots_per_node=50)

    for nid, s in fc.servers.items():
        pool.register_node(nid, s.canonical_name, s.tier, ["generic"])

    stats = pool.fleet_stats()
    print(f"Fleet pool: {stats['nodes']} nodes, {stats['total_slots']} total slots")
    print(f"By tier: {pool.nodes_by_tier()}")

    best = pool.best_node()
    if best:
        print(f"Best node: {best.node_id} (utilization={best.utilization})")
