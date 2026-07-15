#!/usr/bin/env python3
"""Stream output — real-time task monitoring via Control Plane API.

Usage:
    python3 stream_output.py watch <task_id>
    python3 stream_output.py logs <node_id> [lines]
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request

CONTROL_PLANE = "http://192.168.88.210:9101"


def _request(url: str, timeout: int = 10) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


def watch_task(task_id: str, poll_interval: float = 1.0) -> None:
    print(f"Watching task {task_id}...")
    last_state = ""
    while True:
        task = _request(f"{CONTROL_PLANE}/v1/tasks/{task_id}")
        state = task.get("state", "unknown")
        result = task.get("result")

        if state != last_state:
            print(f"[{state}]")
            last_state = state

        if state == "completed":
            if result:
                print(json.dumps(result, indent=2))
            break
        elif state == "failed":
            print(f"Error: {task.get('error', 'unknown')}")
            break

        time.sleep(poll_interval)


def get_node_logs(node_id: str, lines: int = 50) -> dict:
    command = f"journalctl -u kolibri-heartbeat --no-pager -n {lines}"
    task_body = {
        "node_id": node_id,
        "command": command,
        "objective": f"get logs from {node_id}",
        "kind": "read_only_probe",
    }
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", task_body)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: stream_output.py <watch|logs> <task_id|node_id> [lines]")
        sys.exit(1)

    action = sys.argv[1]
    target = sys.argv[2]

    if action == "watch":
        watch_task(target)
    elif action == "logs":
        lines = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        result = get_node_logs(target, lines)
        print(json.dumps(result, indent=2))
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
