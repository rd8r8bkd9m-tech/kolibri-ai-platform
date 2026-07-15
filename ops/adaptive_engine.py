#!/usr/bin/env python3
"""Adaptive Engine — change behavior based on experience."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, asdict

CONTROL_PLANE = "http://192.168.88.210:9101"


@dataclass
class AdaptiveRule:
    rule_id: str
    condition: str
    action: str
    params: dict
    triggered_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


_rules: list[AdaptiveRule] = []


def _request(method: str, url: str, data: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


def add_rule(condition: str, action: str, params: dict | None = None) -> AdaptiveRule:
    rule = AdaptiveRule(
        rule_id=f"RULE-{len(_rules)+1}",
        condition=condition,
        action=action,
        params=params or {},
    )
    _rules.append(rule)
    return rule


def evaluate_rules(metrics: dict) -> list[dict]:
    triggered = []
    for rule in _rules:
        if "error_rate" in rule.condition and metrics.get("error_rate", 0) > 5:
            triggered.append({"rule": rule.to_dict(), "action": rule.action})
            rule.triggered_count += 1
        elif "disk_full" in rule.condition and metrics.get("disk_usage", 0) > 90:
            triggered.append({"rule": rule.to_dict(), "action": rule.action})
            rule.triggered_count += 1
        elif "latency" in rule.condition and metrics.get("latency_ms", 0) > 2000:
            triggered.append({"rule": rule.to_dict(), "action": rule.action})
            rule.triggered_count += 1
    return triggered


def get_rules() -> list[AdaptiveRule]:
    return _rules


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: adaptive_engine.py <list|add|evaluate> [args]")
        sys.exit(1)

    action = sys.argv[1]
    if action == "list":
        for r in _rules:
            print(f"  {r.rule_id}: {r.condition} -> {r.action} (triggered {r.triggered_count}x)")
    elif action == "add" and len(sys.argv) > 3:
        rule = add_rule(sys.argv[2], sys.argv[3])
        print(f"  Added: {rule.to_dict()}")
    elif action == "evaluate":
        print(json.dumps(evaluate_rules({"error_rate": 10, "disk_usage": 95, "latency_ms": 3000}), indent=2))
