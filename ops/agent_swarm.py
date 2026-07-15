#!/usr/bin/env python3
"""Agent Swarm — coordinated multi-agent execution."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

CONTROL_PLANE = "http://192.168.88.210:9101"

AGENT_ROLES = ["architect", "implementer", "reviewer", "tester", "debater"]


@dataclass
class SwarmTask:
    swarm_id: str
    objective: str
    agents: list[dict]
    votes: dict
    status: str  # "forming" | "executing" | "debating" | "completed"
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


def create_swarm(objective: str, num_agents: int = 3) -> SwarmTask:
    swarm_id = f"SWARM-{int(datetime.now(timezone.utc).timestamp())}"
    agents = []
    for i in range(min(num_agents, len(AGENT_ROLES))):
        agents.append({
            "role": AGENT_ROLES[i],
            "node_id": f"agent-0{i+1}",
            "status": "idle",
        })
    return SwarmTask(
        swarm_id=swarm_id,
        objective=objective,
        agents=agents,
        votes={},
        status="forming",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def execute_swarm(swarm: SwarmTask) -> SwarmTask:
    swarm.status = "executing"
    for agent in swarm.agents:
        result = _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
            "node_id": agent["node_id"],
            "command": f"echo '{agent['role']}: working on {swarm.objective}'",
            "objective": f"{agent['role']} task in swarm {swarm.swarm_id}",
            "kind": "generic_implementation",
        })
        agent["status"] = "completed" if "error" not in result else "failed"
    swarm.status = "completed"
    return swarm


def vote(swarm: SwarmTask, agent_role: str, decision: str) -> SwarmTask:
    swarm.votes[agent_role] = decision
    return swarm


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: agent_swarm.py <create|execute> <objective> [num_agents]")
        sys.exit(1)

    action = sys.argv[1]
    objective = sys.argv[2]
    num = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    if action == "create":
        swarm = create_swarm(objective, num)
        print(json.dumps(swarm.to_dict(), indent=2))
    elif action == "execute":
        swarm = create_swarm(objective, num)
        swarm = execute_swarm(swarm)
        print(json.dumps(swarm.to_dict(), indent=2))
