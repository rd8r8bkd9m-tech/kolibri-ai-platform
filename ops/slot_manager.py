#!/usr/bin/env python3
"""Slot manager — fine-grained slot allocation across fleet nodes.

Tracks individual slot state: free, allocated, reserved, blocked.
Supports slot reservation for long-running tasks and slot rebalancing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal
from datetime import datetime, timezone

SlotState = Literal["free", "allocated", "reserved", "blocked"]


@dataclass
class Slot:
    slot_id: str
    node_id: str
    state: SlotState = "free"
    task_id: str | None = None
    allocated_at: str | None = None
    capability: str = "generic"

    def to_dict(self) -> dict:
        return {
            "slot_id": self.slot_id,
            "node_id": self.node_id,
            "state": self.state,
            "task_id": self.task_id,
            "capability": self.capability,
        }


class SlotManager:
    """Per-node slot manager with fleet-wide allocation tracking."""

    def __init__(self, slots_per_node: int = 50):
        self._slots_per_node = slots_per_node
        self._slots: dict[str, Slot] = {}  # slot_id -> Slot
        self._node_slots: dict[str, list[str]] = {}  # node_id -> [slot_ids]

    def init_node(self, node_id: str):
        if node_id in self._node_slots:
            return
        slot_ids = []
        for i in range(self._slots_per_node):
            slot_id = f"{node_id}:s{i:03d}"
            slot = Slot(slot_id=slot_id, node_id=node_id)
            self._slots[slot_id] = slot
            slot_ids.append(slot_id)
        self._node_slots[node_id] = slot_ids

    def acquire(self, node_id: str, task_id: str, capability: str = "generic") -> Slot | None:
        for slot_id in self._node_slots.get(node_id, []):
            slot = self._slots[slot_id]
            if slot.state == "free":
                slot.state = "allocated"
                slot.task_id = task_id
                slot.allocated_at = datetime.now(timezone.utc).isoformat()
                slot.capability = capability
                return slot
        return None

    def release(self, slot_id: str):
        slot = self._slots.get(slot_id)
        if slot:
            slot.state = "free"
            slot.task_id = None
            slot.allocated_at = None

    def release_by_task(self, task_id: str) -> str | None:
        for slot in self._slots.values():
            if slot.task_id == task_id:
                self.release(slot.slot_id)
                return slot.slot_id
        return None

    def reserve(self, node_id: str, count: int = 1) -> list[Slot]:
        reserved = []
        for slot_id in self._node_slots.get(node_id, []):
            if len(reserved) >= count:
                break
            slot = self._slots[slot_id]
            if slot.state == "free":
                slot.state = "reserved"
                reserved.append(slot)
        return reserved

    def block(self, slot_id: str):
        slot = self._slots.get(slot_id)
        if slot:
            slot.state = "blocked"

    def free_count(self, node_id: str) -> int:
        return sum(1 for sid in self._node_slots.get(node_id, [])
                   if self._slots[sid].state == "free")

    def allocated_count(self, node_id: str) -> int:
        return sum(1 for sid in self._node_slots.get(node_id, [])
                   if self._slots[sid].state == "allocated")

    def node_stats(self, node_id: str) -> dict:
        slots = [self._slots[sid] for sid in self._node_slots.get(node_id, [])]
        states = {}
        for s in slots:
            states[s.state] = states.get(s.state, 0) + 1
        return {"node_id": node_id, "total": len(slots), **states}

    def fleet_stats(self) -> dict:
        total = len(self._slots)
        states: dict[str, int] = {}
        for s in self._slots.values():
            states[s.state] = states.get(s.state, 0) + 1
        return {"total": total, "nodes": len(self._node_slots), **states}

    def remove_node(self, node_id: str):
        for slot_id in self._node_slots.pop(node_id, []):
            self._slots.pop(slot_id, None)

    def all_allocated(self) -> list[dict]:
        return [s.to_dict() for s in self._slots.values() if s.state == "allocated"]


if __name__ == "__main__":
    from fleet_classification import build_fleet_classification

    fc = build_fleet_classification()
    sm = SlotManager(slots_per_node=50)

    for nid in fc.servers:
        sm.init_node(nid)

    stats = sm.fleet_stats()
    print(f"Slot manager: {stats['total']} slots across {stats['nodes']} nodes")

    slot = sm.acquire("home", "test-001")
    if slot:
        print(f"Acquired: {slot.slot_id} on {slot.node_id}")
    print(f"After acquire: {sm.fleet_stats()}")
