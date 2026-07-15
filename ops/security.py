#!/usr/bin/env python3
"""Security — RBAC + audit logging for fleet operations."""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CONTROL_PLANE = "http://192.168.88.210:9101"
AUDIT_LOG_PATH = Path(os.environ.get("KOLIBRI_AUDIT_LOG", "/tmp/kolibri_audit.jsonl"))

ROLES = {
    "owner": {"description": "Full access to everything", "level": 100},
    "admin": {"description": "Fleet management", "level": 80},
    "operator": {"description": "Start/stop agents", "level": 60},
    "viewer": {"description": "Read-only access", "level": 40},
    "agent": {"description": "Access to own server only", "level": 20},
}

ACTION_LEVELS = {
    "fleet:read": 20,
    "fleet:write": 80,
    "task:submit": 40,
    "task:cancel": 60,
    "node:drain": 80,
    "node:delete": 100,
    "auth:grant": 100,
    "process:start": 60,
    "process:stop": 60,
    "package:install": 60,
    "package:remove": 80,
    "backup:create": 40,
    "backup:restore": 80,
    "fs:write": 60,
    "fs:delete": 80,
}

_audit_log: list[dict] = []


def _load_persistent_log() -> None:
    global _audit_log
    if AUDIT_LOG_PATH.exists():
        try:
            lines = AUDIT_LOG_PATH.read_text().strip().split("\n")
            loaded = [json.loads(line) for line in lines[-500:] if line.strip()]
            _audit_log.extend(loaded)
        except Exception:
            pass


def check_permission(role: str, action: str) -> bool:
    role_level = ROLES.get(role, {}).get("level", 0)
    required = ACTION_LEVELS.get(action, 50)
    return role_level >= required


def audit_log(actor: str, action: str, target: str, result: str, details: dict | None = None) -> None:
    global _audit_log
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "target": target,
        "result": result,
    }
    if details:
        entry["details"] = details
    _audit_log.append(entry)
    if len(_audit_log) > 1000:
        _audit_log = _audit_log[-500:]
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def get_audit_log(limit: int = 50, action_filter: str | None = None) -> list[dict]:
    logs = _audit_log
    if action_filter:
        logs = [e for e in logs if e.get("action") == action_filter]
    return logs[-limit:]


_load_persistent_log()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: security.py <check|log> <role> [action]")
        sys.exit(1)

    action = sys.argv[1]
    if action == "check":
        role = sys.argv[2]
        act = sys.argv[3] if len(sys.argv) > 3 else "fleet:read"
        allowed = check_permission(role, act)
        print(f"  {role} -> {act}: {'✅ allowed' if allowed else '❌ denied'}")
    elif action == "log":
        logs = get_audit_log()
        for entry in logs:
            print(f"  [{entry['timestamp']}] {entry['actor']} {entry['action']} {entry['target']}: {entry['result']}")
