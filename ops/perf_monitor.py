#!/usr/bin/env python3
"""Performance Monitor — collects metrics from fleet nodes every 5 minutes."""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone

CONTROL_PLANE = "http://192.168.88.210:9101"
COLLECT_INTERVAL = 300  # 5 minutes


def _request(url: str, timeout: int = 10) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


def collect_metrics() -> dict:
    nodes_resp = _request(f"{CONTROL_PLANE}/v1/nodes")
    nodes = nodes_resp.get("nodes", [])

    metrics = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_nodes": len(nodes),
        "fresh": sum(1 for n in nodes if n.get("freshness") == "fresh"),
        "degraded": sum(1 for n in nodes if n.get("freshness") == "degraded"),
        "stale": sum(1 for n in nodes if n.get("freshness") == "stale"),
        "avg_heartbeat_age": 0,
        "nodes": [],
    }

    total_hb = 0
    for n in nodes:
        hb = n.get("heartbeat_age_seconds", 0)
        total_hb += hb
        metrics["nodes"].append({
            "node_id": n.get("node_id"),
            "freshness": n.get("freshness"),
            "heartbeat_age": hb,
        })

    if nodes:
        metrics["avg_heartbeat_age"] = round(total_hb / len(nodes), 1)

    return metrics


def check_thresholds(metrics: dict) -> list[dict]:
    issues = []

    if metrics["stale"] > 0:
        issues.append({
            "type": "stale_nodes",
            "severity": "warning",
            "message": f"{metrics['stale']} nodes are stale",
        })

    if metrics["avg_heartbeat_age"] > 120:
        issues.append({
            "type": "high_heartbeat_age",
            "severity": "warning",
            "message": f"Average heartbeat age: {metrics['avg_heartbeat_age']}s",
        })

    if metrics["fresh"] < 5:
        issues.append({
            "type": "low_fresh_nodes",
            "severity": "critical",
            "message": f"Only {metrics['fresh']} fresh nodes",
        })

    return issues


if __name__ == "__main__":
    print("Performance Monitor started")
    while True:
        metrics = collect_metrics()
        issues = check_thresholds(metrics)

        print(f"[{metrics['timestamp']}] Nodes: {metrics['total_nodes']} total, "
              f"{metrics['fresh']} fresh, {metrics['degraded']} degraded, {metrics['stale']} stale")

        for issue in issues:
            print(f"  [{issue['severity'].upper()}] {issue['message']}")

        time.sleep(COLLECT_INTERVAL)
