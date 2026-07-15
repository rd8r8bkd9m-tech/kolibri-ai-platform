#!/usr/bin/env python3
"""Issue Detector — identifies problems based on thresholds."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, asdict

CONTROL_PLANE = "http://192.168.88.210:9101"

THRESHOLDS = {
    "latency_ms": 2000,
    "error_rate_pct": 5,
    "disk_usage_pct": 90,
    "ram_usage_pct": 85,
    "heartbeat_age_s": 120,
}


@dataclass
class Issue:
    issue_type: str
    severity: str  # "info" | "warning" | "critical"
    node_id: str
    message: str
    metric_value: float
    threshold: float

    def to_dict(self) -> dict:
        return asdict(self)


def _request(url: str, timeout: int = 10) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


def detect_issues() -> list[Issue]:
    issues = []
    nodes_resp = _request(f"{CONTROL_PLANE}/v1/nodes")
    nodes = nodes_resp.get("nodes", [])

    for node in nodes:
        node_id = node.get("node_id", "?")
        hb_age = node.get("heartbeat_age_seconds", 0)
        freshness = node.get("freshness", "unknown")

        if hb_age > THRESHOLDS["heartbeat_age_s"]:
            issues.append(Issue(
                issue_type="stale_node",
                severity="critical" if hb_age > 300 else "warning",
                node_id=node_id,
                message=f"Heartbeat age {hb_age}s exceeds threshold",
                metric_value=hb_age,
                threshold=THRESHOLDS["heartbeat_age_s"],
            ))

        if freshness == "degraded":
            issues.append(Issue(
                issue_type="degraded_node",
                severity="warning",
                node_id=node_id,
                message=f"Node is degraded",
                metric_value=0,
                threshold=0,
            ))

    return issues


def suggest_fixes(issues: list[Issue]) -> list[dict]:
    fixes = []
    for issue in issues:
        if issue.issue_type == "stale_node":
            fixes.append({
                "issue": issue.to_dict(),
                "action": "restart_heartbeat",
                "command": f"ssh {issue.node_id} 'systemctl restart kolibri-heartbeat'",
            })
        elif issue.issue_type == "degraded_node":
            fixes.append({
                "issue": issue.to_dict(),
                "action": "check_logs",
                "command": f"ssh {issue.node_id} 'journalctl -u kolibri-heartbeat --no-pager -n 20'",
            })
    return fixes


if __name__ == "__main__":
    issues = detect_issues()
    print(f"Found {len(issues)} issues")
    for issue in issues:
        print(f"  [{issue.severity.upper()}] {issue.node_id}: {issue.message}")

    fixes = suggest_fixes(issues)
    if fixes:
        print(f"\nSuggested fixes:")
        for fix in fixes:
            print(f"  {fix['action']}: {fix['command']}")
