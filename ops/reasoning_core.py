#!/usr/bin/env python3
"""Reasoning Engine — task decomposition and planning."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

CONTROL_PLANE = "http://192.168.88.210:9101"


@dataclass
class Plan:
    plan_id: str
    objective: str
    steps: list[dict]
    status: str  # "planning" | "executing" | "completed" | "failed"
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)


def _request(method: str, url: str, data: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def create_plan(objective: str, available_nodes: list[str]) -> Plan:
    plan_id = f"PLAN-{int(datetime.now(timezone.utc).timestamp())}"
    steps = []

    for i, node in enumerate(available_nodes):
        steps.append({
            "step": i + 1,
            "node_id": node,
            "action": f"Execute part of objective on {node}",
            "status": "pending",
        })

    return Plan(
        plan_id=plan_id,
        objective=objective,
        steps=steps,
        status="planning",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def execute_plan(plan: Plan) -> Plan:
    plan.status = "executing"
    for step in plan.steps:
        if step["status"] == "pending":
            result = _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
                "node_id": step["node_id"],
                "command": f"echo 'Executing: {step['action']}'",
                "objective": step["action"],
                "kind": "generic_implementation",
            })
            step["status"] = "completed" if "error" not in result else "failed"
            step["result"] = result
    plan.status = "completed"
    return plan


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: reasoning_core.py <plan|execute> <objective> [node1,node2,...]")
        sys.exit(1)

    action = sys.argv[1]
    objective = sys.argv[2]
    nodes = sys.argv[3].split(",") if len(sys.argv) > 3 else ["agent-01"]

    if action == "plan":
        plan = create_plan(objective, nodes)
        print(json.dumps(plan.to_dict(), indent=2))
    elif action == "execute":
        plan = create_plan(objective, nodes)
        plan = execute_plan(plan)
        print(json.dumps(plan.to_dict(), indent=2))
