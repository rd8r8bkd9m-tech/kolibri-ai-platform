#!/usr/bin/env python3
"""Backup Manager — full/incremental backups for fleet nodes."""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone

CONTROL_PLANE = "http://192.168.88.210:9101"
BACKUP_DIR = "/var/backups/kolibri"


def _request(method: str, url: str, data: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def create_backup(node_id: str, backup_type: str = "full") -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_name = f"backup-{node_id}-{ts}"
    if backup_type == "full":
        cmd = f"mkdir -p {BACKUP_DIR} && tar czf {BACKUP_DIR}/{backup_name}.tar.gz /etc /opt/kolibri 2>/dev/null || true"
    elif backup_type == "incremental":
        cmd = f"mkdir -p {BACKUP_DIR} && find /opt/kolibri -mtime -1 -type f | tar czf {BACKUP_DIR}/{backup_name}-incr.tar.gz -T - 2>/dev/null || true"
    else:
        cmd = f"mkdir -p {BACKUP_DIR} && tar czf {BACKUP_DIR}/{backup_name}.tar.gz /etc/kolibri 2>/dev/null || true"

    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": cmd,
        "objective": f"Create {backup_type} backup on {node_id}",
        "kind": "generic_implementation",
    })


def list_backups(node_id: str) -> dict:
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": f"ls -lh {BACKUP_DIR}/*.tar.gz 2>/dev/null || echo 'No backups found'",
        "objective": f"List backups on {node_id}",
        "kind": "read_only_probe",
    })


def restore_backup(node_id: str, backup_name: str) -> dict:
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": f"tar xzf {BACKUP_DIR}/{backup_name} -C / 2>/dev/null || echo 'Restore failed'",
        "objective": f"Restore {backup_name} on {node_id}",
        "kind": "generic_implementation",
    })


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: backup_manager.py <create|list|restore> <node_id> [backup_name]")
        sys.exit(1)

    action = sys.argv[1]
    node_id = sys.argv[2]

    if action == "create":
        btype = sys.argv[3] if len(sys.argv) > 3 else "full"
        print(json.dumps(create_backup(node_id, btype), indent=2))
    elif action == "list":
        print(json.dumps(list_backups(node_id), indent=2))
    elif action == "restore" and len(sys.argv) > 3:
        print(json.dumps(restore_backup(node_id, sys.argv[3]), indent=2))
