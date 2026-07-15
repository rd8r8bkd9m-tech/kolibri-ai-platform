#!/usr/bin/env python3
"""Virtual File System — unified namespace across fleet nodes."""

from __future__ import annotations

import json
import shlex
import urllib.request
from typing import Any

CONTROL_PLANE = "http://192.168.88.210:9101"

# Paths that are safe for write/rm operations
ALLOWED_WRITE_PREFIXES = ("/var/lib/kolibri", "/tmp/kolibri", "/srv/kolibri")
FORBIDDEN_PATHS = ("/etc/passwd", "/etc/shadow", "/root/.ssh", "/boot")


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


def _validate_path(path: str, allow_write: bool = False) -> str | None:
    """Validate path is safe. Returns error message or None if OK."""
    import os
    normalized = os.path.normpath(path)
    for forbidden in FORBIDDEN_PATHS:
        if normalized.startswith(forbidden):
            return f"Access denied: {normalized} is in forbidden zone"
    if allow_write and not any(normalized.startswith(p) for p in ALLOWED_WRITE_PREFIXES):
        return f"Write denied: {normalized} outside allowed prefixes {ALLOWED_WRITE_PREFIXES}"
    return None


def ls(node_id: str, path: str) -> dict:
    err = _validate_path(path)
    if err:
        return {"error": err}
    safe_path = shlex.quote(path)
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": f"ls -la {safe_path}",
        "objective": f"List files at {path} on {node_id}",
        "kind": "read_only_probe",
    })


def cat(node_id: str, path: str) -> dict:
    err = _validate_path(path)
    if err:
        return {"error": err}
    safe_path = shlex.quote(path)
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": f"cat {safe_path}",
        "objective": f"Read {path} on {node_id}",
        "kind": "read_only_probe",
    })


def write(node_id: str, path: str, content: str) -> dict:
    err = _validate_path(path, allow_write=True)
    if err:
        return {"error": err}
    safe_path = shlex.quote(path)
    safe_content = shlex.quote(content)
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": f"python3 -c \"import os,sys; os.makedirs(os.path.dirname({safe_path}),exist_ok=True); open({safe_path},'w').write(sys.stdin.read())\" <<'KOLIBRI_EOF'\n{content}\nKOLIBRI_EOF",
        "objective": f"Write to {path} on {node_id}",
        "kind": "generic_implementation",
    })


def rm(node_id: str, path: str) -> dict:
    err = _validate_path(path, allow_write=True)
    if err:
        return {"error": err}
    safe_path = shlex.quote(path)
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": f"rm -f {safe_path}",
        "objective": f"Remove {path} on {node_id}",
        "kind": "generic_implementation",
    })


def find(node_id: str, name: str, older_than: str | None = None) -> dict:
    safe_name = shlex.quote(name)
    search_roots = "/var/lib/kolibri /srv/kolibri /tmp/kolibri"
    cmd = f"find {search_roots} -name {safe_name} -type f 2>/dev/null | head -20"
    if older_than:
        import re
        days = re.sub(r'[^0-9]', '', older_than)
        cmd = f"find {search_roots} -name {safe_name} -type f -mtime +{days} 2>/dev/null | head -20"
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": cmd,
        "objective": f"Find {name} on {node_id}",
        "kind": "read_only_probe",
    })


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("Usage: virtual_fs.py <ls|cat|write|rm|find> <node_id> <path> [content]")
        sys.exit(1)

    action = sys.argv[1]
    node_id = sys.argv[2]
    path = sys.argv[3]

    if action == "ls":
        print(json.dumps(ls(node_id, path), indent=2))
    elif action == "cat":
        print(json.dumps(cat(node_id, path), indent=2))
    elif action == "write":
        content = sys.argv[4] if len(sys.argv) > 4 else ""
        print(json.dumps(write(node_id, path, content), indent=2))
    elif action == "rm":
        print(json.dumps(rm(node_id, path), indent=2))
    elif action == "find":
        print(json.dumps(find(node_id, path), indent=2))
