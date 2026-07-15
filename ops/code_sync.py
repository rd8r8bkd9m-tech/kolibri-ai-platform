#!/usr/bin/env python3
"""Code synchronization — git operations on fleet nodes via Control Plane API.

Usage:
    python3 code_sync.py pull <node_id> <repo_url> <branch>
    python3 code_sync.py status <node_id>
    python3 code_sync.py diff <node_id>
"""

from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error

CONTROL_PLANE = "http://192.168.88.210:9101"


def _request(method: str, url: str, data: dict | None = None, timeout: int = 60) -> dict:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def git_pull(node_id: str, repo_url: str, branch: str = "main") -> dict:
    command = f"cd /opt/kolibri-ai && git pull {repo_url} {branch}"
    task_body = {
        "node_id": node_id,
        "command": command,
        "objective": f"git pull {branch} on {node_id}",
        "kind": "generic_implementation",
    }
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", task_body)


def git_status(node_id: str) -> dict:
    command = "cd /opt/kolibri-ai && git status --porcelain && git log --oneline -5"
    task_body = {
        "node_id": node_id,
        "command": command,
        "objective": f"git status on {node_id}",
        "kind": "read_only_probe",
    }
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", task_body)


def git_diff(node_id: str) -> dict:
    command = "cd /opt/kolibri-ai && git diff --stat"
    task_body = {
        "node_id": node_id,
        "command": command,
        "objective": f"git diff on {node_id}",
        "kind": "read_only_probe",
    }
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", task_body)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: code_sync.py <pull|status|diff> <node_id> [repo_url] [branch]")
        sys.exit(1)

    action = sys.argv[1]
    node_id = sys.argv[2]

    if action == "pull":
        repo = sys.argv[3] if len(sys.argv) > 3 else "https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform"
        branch = sys.argv[4] if len(sys.argv) > 4 else "main"
        result = git_pull(node_id, repo, branch)
    elif action == "status":
        result = git_status(node_id)
    elif action == "diff":
        result = git_diff(node_id)
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)

    print(json.dumps(result, indent=2))
