#!/usr/bin/env python3
"""Log Collector — centralized logging from fleet nodes."""

from __future__ import annotations

import json
import urllib.request

CONTROL_PLANE = "http://192.168.88.210:9101"


def _request(method: str, url: str, data: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def get_logs(node_id: str, service: str | None = None, lines: int = 100) -> dict:
    cmd = f"journalctl --no-pager -n {lines}"
    if service:
        cmd += f" -u {service}"
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": cmd,
        "objective": f"Get logs from {node_id}",
        "kind": "read_only_probe",
    })


def search_logs(node_id: str, query: str, lines: int = 100) -> dict:
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": f"journalctl --no-pager -n {lines} | grep '{query}'",
        "objective": f"Search logs for '{query}' on {node_id}",
        "kind": "read_only_probe",
    })


def get_error_stats(node_id: str) -> dict:
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": "journalctl --no-pager -p err -n 100 --no-hostname | awk '{print $5}' | sort | uniq -c | sort -rn | head -10",
        "objective": f"Get error stats from {node_id}",
        "kind": "read_only_probe",
    })


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: log_collector.py <logs|search|errors> <node_id> [query]")
        sys.exit(1)

    action = sys.argv[1]
    node_id = sys.argv[2]

    if action == "logs":
        print(json.dumps(get_logs(node_id), indent=2))
    elif action == "search" and len(sys.argv) > 3:
        print(json.dumps(search_logs(node_id, sys.argv[3]), indent=2))
    elif action == "errors":
        print(json.dumps(get_error_stats(node_id), indent=2))
