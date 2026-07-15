#!/usr/bin/env python3
"""Load balancer — distributes tasks across fleet nodes by load, capability, and tier.

Strategies: least-loaded, round-robin, capability-match, tier-preference.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal
from datetime import datetime, timezone

Strategy = Literal["least_loaded", "round_robin", "capability_match", "tier_preference"]


@dataclass
class NodeLoad:
    node_id: str
    tier: str
    allocated: int = 0
    max_slots: int = 50
    capabilities: list[str] | None = None
    health: str = "online"
    last_task_at: str = ""

    @property
    def load_ratio(self) -> float:
        return self.allocated / self.max_slots if self.max_slots > 0 else 1.0

    @property
    def free(self) -> int:
        return self.max_slots - self.allocated


class LoadBalancer:
    """Fleet-wide load balancer with pluggable strategies."""

    def __init__(self, strategy: Strategy = "least_loaded"):
        self._strategy = strategy
        self._nodes: dict[str, NodeLoad] = {}
        self._rr_index = 0
        self._history: list[dict] = []

    def register(self, node_id: str, tier: str, max_slots: int = 50,
                 capabilities: list[str] | None = None, health: str = "online"):
        self._nodes[node_id] = NodeLoad(
            node_id=node_id, tier=tier, max_slots=max_slots,
            capabilities=capabilities or ["generic"], health=health,
        )

    def update_load(self, node_id: str, allocated: int, health: str | None = None):
        node = self._nodes.get(node_id)
        if node:
            node.allocated = allocated
            if health:
                node.health = health
            node.last_task_at = datetime.now(timezone.utc).isoformat()

    def select(self, required_capability: str | None = None,
               preferred_tier: str | None = None) -> str | None:
        candidates = self._available_nodes(required_capability)
        if not candidates:
            return None

        if preferred_tier:
            tier_matches = [n for n in candidates if n.tier == preferred_tier]
            if tier_matches:
                candidates = tier_matches

        if self._strategy == "least_loaded":
            node = min(candidates, key=lambda n: n.load_ratio)
        elif self._strategy == "round_robin":
            node = candidates[self._rr_index % len(candidates)]
            self._rr_index += 1
        elif self._strategy == "capability_match":
            if required_capability:
                cap_matches = [n for n in candidates if required_capability in (n.capabilities or [])]
                node = min(cap_matches, key=lambda n: n.load_ratio) if cap_matches else min(candidates, key=lambda n: n.load_ratio)
            else:
                node = min(candidates, key=lambda n: n.load_ratio)
        else:
            node = min(candidates, key=lambda n: n.load_ratio)

        self._history.append({
            "node_id": node.node_id,
            "strategy": self._strategy,
            "load_ratio": node.load_ratio,
            "time": datetime.now(timezone.utc).isoformat(),
        })
        if len(self._history) > 1000:
            self._history = self._history[-500:]

        return node.node_id

    def _available_nodes(self, capability: str | None = None) -> list[NodeLoad]:
        result = []
        for node in self._nodes.values():
            if node.health not in ("online", "degraded"):
                continue
            if node.free <= 0:
                continue
            if capability and capability not in (node.capabilities or []):
                continue
            result.append(node)
        return result

    def distribute(self, tasks: list[dict]) -> list[dict]:
        assignments = []
        for task in tasks:
            node_id = self.select(
                required_capability=task.get("required_capability"),
                preferred_tier=task.get("preferred_tier"),
            )
            assignments.append({**task, "assigned_node": node_id})
        return assignments

    def stats(self) -> dict:
        nodes = list(self._nodes.values())
        return {
            "strategy": self._strategy,
            "nodes": len(nodes),
            "total_slots": sum(n.max_slots for n in nodes),
            "used_slots": sum(n.allocated for n in nodes),
            "avg_load": round(sum(n.load_ratio for n in nodes) / len(nodes), 3) if nodes else 0,
            "history_len": len(self._history),
        }

    def set_strategy(self, strategy: Strategy):
        self._strategy = strategy


if __name__ == "__main__":
    from fleet_classification import build_fleet_classification

    fc = build_fleet_classification()
    lb = LoadBalancer(strategy="least_loaded")

    for nid, s in fc.servers.items():
        lb.register(nid, s.tier, 50, ["generic"])

    print(f"Load balancer: {lb.stats()}")

    tasks = [{"command": f"task-{i}", "required_capability": None} for i in range(5)]
    assigned = lb.distribute(tasks)
    for a in assigned:
        print(f"  {a['command']} -> {a['assigned_node']}")
