#!/usr/bin/env python3
"""Memory System — long-term memory for fleet operations."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

CONTROL_PLANE = "http://192.168.88.210:9101"

MEMORY_TYPES = ["episodic", "semantic", "procedural", "autobiographic"]


@dataclass
class Memory:
    memory_id: str
    memory_type: str
    key: str
    value: str
    created_at: str
    accessed_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


_memories: list[Memory] = []


def _request(method: str, url: str, data: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


def store(memory_type: str, key: str, value: str) -> Memory:
    mem = Memory(
        memory_id=f"MEM-{int(datetime.now(timezone.utc).timestamp())}",
        memory_type=memory_type,
        key=key,
        value=value,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    _memories.append(mem)
    if len(_memories) > 10000:
        _memories.pop(0)
    return mem


def recall(query: str) -> list[Memory]:
    return [m for m in _memories if query.lower() in m.key.lower() or query.lower() in m.value.lower()]


def forget(older_than_days: int | None = None) -> int:
    if older_than_days is None:
        count = len(_memories)
        _memories.clear()
        return count
    cutoff = datetime.now(timezone.utc).timestamp() - (older_than_days * 86400)
    before = len(_memories)
    _memories[:] = [m for m in _memories if datetime.fromisoformat(m.created_at.replace("Z", "+00:00")).timestamp() > cutoff]
    return before - len(_memories)


def get_stats() -> dict:
    by_type = {}
    for m in _memories:
        by_type[m.memory_type] = by_type.get(m.memory_type, 0) + 1
    return {"total": len(_memories), "by_type": by_type}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: memory_system.py <store|recall|forget|stats> [args]")
        sys.exit(1)

    action = sys.argv[1]
    if action == "store" and len(sys.argv) > 4:
        mem = store(sys.argv[2], sys.argv[3], sys.argv[4])
        print(f"  Stored: {mem.to_dict()}")
    elif action == "recall" and len(sys.argv) > 2:
        results = recall(sys.argv[2])
        for m in results:
            print(f"  {m.memory_id}: [{m.memory_type}] {m.key} = {m.value[:80]}")
    elif action == "forget":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else None
        removed = forget(days)
        print(f"  Removed {removed} memories")
    elif action == "stats":
        print(json.dumps(get_stats(), indent=2))
