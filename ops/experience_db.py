#!/usr/bin/env python3
"""Experience Database — learn from past actions."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

CONTROL_PLANE = "http://192.168.88.210:9101"


@dataclass
class Experience:
    experience_id: str
    action: str
    context: dict
    result: str
    duration_s: float
    feedback: str | None = None
    learned: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


_experiences: list[Experience] = []


def _request(method: str, url: str, data: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


def log_experience(action: str, context: dict, result: str, duration: float) -> Experience:
    exp = Experience(
        experience_id=f"EXP-{int(datetime.now(timezone.utc).timestamp())}",
        action=action,
        context=context,
        result=result,
        duration_s=duration,
    )
    _experiences.append(exp)
    if len(_experiences) > 1000:
        _experiences.pop(0)
    return exp


def search_experiences(action: str | None = None, result: str | None = None) -> list[Experience]:
    filtered = _experiences
    if action:
        filtered = [e for e in filtered if e.action == action]
    if result:
        filtered = [e for e in filtered if e.result == result]
    return filtered


def get_stats() -> dict:
    total = len(_experiences)
    by_result = {}
    for e in _experiences:
        by_result[e.result] = by_result.get(e.result, 0) + 1
    return {"total": total, "by_result": by_result}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: experience_db.py <log|search|stats> [action]")
        sys.exit(1)

    action = sys.argv[1]
    if action == "log" and len(sys.argv) > 3:
        exp = log_experience(sys.argv[2], {}, sys.argv[3], 0)
        print(f"  Logged: {exp.to_dict()}")
    elif action == "search":
        results = search_experiences(sys.argv[2] if len(sys.argv) > 2 else None)
        for e in results:
            print(f"  {e.experience_id}: {e.action} -> {e.result}")
    elif action == "stats":
        print(json.dumps(get_stats(), indent=2))
