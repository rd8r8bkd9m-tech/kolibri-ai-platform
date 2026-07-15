#!/usr/bin/env python3
"""Remote execution engine — sends commands to fleet nodes via Control Plane API.

No SSH. All execution goes through HTTP API on Home (192.168.88.210:9101).
"""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from typing import Any
from datetime import datetime, timezone

CONTROL_PLANE = "http://192.168.88.210:9101"


@dataclass
class ExecResult:
    node_id: str
    task_id: str
    status: str  # "submitted" | "running" | "completed" | "failed"
    submitted_at: str
    completed_at: str | None = None
    output: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _request(method: str, url: str, data: dict | None = None, timeout: int = 30) -> dict:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"http_{e.code}", "detail": e.read().decode()[:500]}
    except urllib.error.URLError as e:
        return {"error": "connection_failed", "detail": str(e.reason)}
    except Exception as e:
        return {"error": "unknown", "detail": str(e)}


def submit_task(node_id: str, command: str, payload: dict | None = None, timeout_sec: int = 300) -> ExecResult:
    task_body = {
        "node_id": node_id,
        "command": command,
        "payload": payload or {},
        "timeout_sec": timeout_sec,
    }
    resp = _request("POST", f"{CONTROL_PLANE}/v1/tasks", task_body)
    task_id = resp.get("task_id") or resp.get("id", "unknown")
    return ExecResult(
        node_id=node_id,
        task_id=task_id,
        status="submitted",
        submitted_at=datetime.now(timezone.utc).isoformat(),
    )


def poll_task(task_id: str) -> dict:
    return _request("GET", f"{CONTROL_PLANE}/v1/tasks/{task_id}")


def wait_for_task(task_id: str, poll_interval: float = 2.0, max_wait: float = 600.0) -> dict:
    start = time.time()
    while time.time() - start < max_wait:
        task = poll_task(task_id)
        state = task.get("state", "")
        if state in ("completed", "failed"):
            return task
        time.sleep(poll_interval)
    return {"error": "timeout", "task_id": task_id}


def exec_on_node(node_id: str, command: str, payload: dict | None = None,
                 poll: bool = True, max_wait: float = 600.0) -> ExecResult | dict:
    result = submit_task(node_id, command, payload)
    if not poll:
        return result
    task = wait_for_task(result.task_id, max_wait=max_wait)
    result.status = task.get("state", "unknown")
    result.output = task.get("result")
    result.error = task.get("error")
    result.completed_at = task.get("completed_at")
    return result


def register_node(node_id: str, hostname: str, capabilities: list[str] | None = None,
                  api_port: int = 8001, agent_id: str | None = None) -> dict:
    body = {
        "node_id": node_id,
        "hostname": hostname,
        "capabilities": capabilities or ["generic"],
        "api_port": api_port,
        "agent_id": agent_id,
    }
    return _request("POST", f"{CONTROL_PLANE}/v1/nodes/register", body)


def heartbeat(node_id: str, health_data: dict | None = None) -> dict:
    return _request("POST", f"{CONTROL_PLANE}/v1/nodes/{node_id}/heartbeat", health_data or {})


def get_fleet_nodes() -> list[dict]:
    resp = _request("GET", f"{CONTROL_PLANE}/v1/fleet/nodes")
    return resp.get("data", {}).get("nodes", [])


def get_route(target_node: str | None = None, required_capability: str | None = None) -> dict:
    params = []
    if target_node:
        params.append(f"target_node={target_node}")
    if required_capability:
        params.append(f"required_capability={required_capability}")
    query = f"?{'&'.join(params)}" if params else ""
    return _request("GET", f"{CONTROL_PLANE}/v1/fleet/route{query}")


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "health"
    if cmd == "health":
        print(json.dumps(_request("GET", f"{CONTROL_PLANE}/v1/health"), indent=2))
    elif cmd == "nodes":
        nodes = get_fleet_nodes()
        print(f"Fleet: {len(nodes)} nodes")
        for n in nodes:
            print(f"  {n.get('node_id', '?'):<20} {n.get('hostname', '?'):<30} {n.get('status', '?')}")
    elif cmd == "register-all":
        from fleet_classification import build_fleet_classification
        fc = build_fleet_classification()
        for nid, s in fc.servers.items():
            resp = register_node(nid, s.canonical_name, ["generic"], s.api_port or 8001)
            print(f"  {nid}: {resp.get('node_id', resp.get('error', 'ok'))}")
        print(f"Registered {len(fc.servers)} nodes")
    else:
        print(f"Usage: remote_exec.py [health|nodes|register-all]")
