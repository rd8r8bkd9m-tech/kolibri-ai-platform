#!/usr/bin/env python3
"""Process Manager — systemd control for fleet services."""

from __future__ import annotations

import json
import re
import shlex
import time
import urllib.request

CONTROL_PLANE = "http://192.168.88.210:9101"
MAX_RETRIES = 3
RETRY_DELAY_S = 2

_SERVICE_RE = re.compile(r'^[a-zA-Z0-9._-]+$')


def _request(method: str, url: str, data: dict | None = None, timeout: int = 30) -> dict:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def _validate_service(service: str) -> str | None:
    if not _SERVICE_RE.match(service):
        return f"Invalid service name: {service}"
    return None


def _submit_with_retry(command: str, objective: str, kind: str = "generic_implementation") -> dict:
    for attempt in range(MAX_RETRIES):
        result = _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
            "command": command,
            "objective": objective,
            "kind": kind,
        })
        if "error" not in result:
            return result
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY_S * (attempt + 1))
    return result


def start_service(node_id: str, service: str) -> dict:
    err = _validate_service(service)
    if err:
        return {"error": err}
    safe_svc = shlex.quote(service)
    return _submit_with_retry(
        f"systemctl start {safe_svc} && systemctl is-active {safe_svc}",
        f"Start {service} on {node_id}",
    )


def stop_service(node_id: str, service: str) -> dict:
    err = _validate_service(service)
    if err:
        return {"error": err}
    safe_svc = shlex.quote(service)
    return _submit_with_retry(
        f"systemctl stop {safe_svc}",
        f"Stop {service} on {node_id}",
    )


def restart_service(node_id: str, service: str) -> dict:
    err = _validate_service(service)
    if err:
        return {"error": err}
    safe_svc = shlex.quote(service)
    return _submit_with_retry(
        f"systemctl restart {safe_svc} && systemctl is-active {safe_svc}",
        f"Restart {service} on {node_id}",
    )


def get_status(node_id: str, service: str) -> dict:
    err = _validate_service(service)
    if err:
        return {"error": err}
    safe_svc = shlex.quote(service)
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": f"systemctl is-active {safe_svc} 2>/dev/null; echo '---'; systemctl status {safe_svc} --no-pager 2>/dev/null | head -20",
        "objective": f"Get status of {service} on {node_id}",
        "kind": "read_only_probe",
    })


def get_logs(node_id: str, service: str, lines: int = 50) -> dict:
    err = _validate_service(service)
    if err:
        return {"error": err}
    safe_svc = shlex.quote(service)
    lines = max(1, min(lines, 500))
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": f"journalctl -u {safe_svc} --no-pager -n {lines} 2>/dev/null",
        "objective": f"Get logs of {service} on {node_id}",
        "kind": "read_only_probe",
    })


def batch_status(node_id: str, services: list[str]) -> dict:
    cmds = []
    for svc in services:
        if _validate_service(svc):
            continue
        safe = shlex.quote(svc)
        cmds.append(f"echo '=== {svc} ==='; systemctl is-active {safe} 2>/dev/null || echo 'inactive'")
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": " && ".join(cmds),
        "objective": f"Batch status check on {node_id}",
        "kind": "read_only_probe",
    }, timeout=60)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("Usage: process_manager.py <start|stop|restart|status|logs> <node_id> <service> [lines]")
        sys.exit(1)

    action = sys.argv[1]
    node_id = sys.argv[2]
    service = sys.argv[3]

    if action == "start":
        print(json.dumps(start_service(node_id, service), indent=2))
    elif action == "stop":
        print(json.dumps(stop_service(node_id, service), indent=2))
    elif action == "restart":
        print(json.dumps(restart_service(node_id, service), indent=2))
    elif action == "status":
        print(json.dumps(get_status(node_id, service), indent=2))
    elif action == "logs":
        lines = int(sys.argv[4]) if len(sys.argv) > 4 else 50
        print(json.dumps(get_logs(node_id, service, lines), indent=2))
