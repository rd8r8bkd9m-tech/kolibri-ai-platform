#!/usr/bin/env python3
"""Improvement Proposer — generates AI PRs for detected issues."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

CONTROL_PLANE = "http://192.168.88.210:9101"

MAX_IMPROVEMENTS_PER_HOUR = 3


@dataclass
class Improvement:
    improvement_id: str
    issue_type: str
    description: str
    proposed_action: str
    target_node: str
    status: str  # "proposed" | "approved" | "executed" | "verified" | "rejected"
    created_at: str
    executed_at: str | None = None
    verified_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _request(method: str, url: str, data: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def propose_improvement(issue: dict) -> Improvement:
    now = datetime.now(timezone.utc).isoformat()
    improvement_id = f"IMP-{int(datetime.now(timezone.utc).timestamp())}"

    action_map = {
        "stale_node": "Restart heartbeat service on the node",
        "degraded_node": "Check and repair node configuration",
        "high_error_rate": "Investigate error logs and fix root cause",
        "disk_full": "Clean old logs and artifacts",
        "latency_high": "Optimize network routing or upgrade resources",
    }

    return Improvement(
        improvement_id=improvement_id,
        issue_type=issue.get("issue_type", "unknown"),
        description=action_map.get(issue.get("issue_type"), "Investigate and fix"),
        proposed_action=f"Execute fix for {issue.get('issue_type')} on {issue.get('node_id')}",
        target_node=issue.get("node_id", "unknown"),
        status="proposed",
        created_at=now,
    )


def approve_improvement(improvement: Improvement) -> Improvement:
    improvement.status = "approved"
    return improvement


def execute_improvement(improvement: Improvement) -> Improvement:
    improvement.status = "executed"
    improvement.executed_at = datetime.now(timezone.utc).isoformat()

    task_body = {
        "node_id": improvement.target_node,
        "command": f"echo 'Executing improvement: {improvement.description}'",
        "objective": improvement.description,
        "kind": "generic_implementation",
    }
    _request("POST", f"{CONTROL_PLANE}/v1/tasks", task_body)

    return improvement


def verify_improvement(improvement: Improvement) -> Improvement:
    improvement.status = "verified"
    improvement.verified_at = datetime.now(timezone.utc).isoformat()
    return improvement


if __name__ == "__main__":
    from issue_detector import detect_issues

    issues = detect_issues()
    print(f"Detected {len(issues)} issues")

    improvements = []
    for issue in issues:
        imp = propose_improvement(issue.to_dict())
        improvements.append(imp)
        print(f"  Proposed: {imp.improvement_id} - {imp.description}")

    print(f"\n{len(improvements)} improvements proposed")
