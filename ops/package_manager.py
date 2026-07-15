#!/usr/bin/env python3
"""Package Manager — install/update/remove services on fleet nodes."""

from __future__ import annotations

import json
import re
import shlex
import urllib.request

CONTROL_PLANE = "http://192.168.88.210:9101"

PACKAGES = {
    "kolibri-agent": "Base agent (heartbeat + task execution)",
    "kolibri-agent-api": "API wrapper (mimo serve)",
    "kolibri-formulalm": "Inference server",
    "kolibri-mesh": "Mesh agent",
    "kolibri-nginx": "Reverse proxy",
}

# Only allow known package name patterns
_PACKAGE_RE = re.compile(r'^kolibri-[a-z0-9._-]+$')


def _request(method: str, url: str, data: dict | None = None, timeout: int = 60) -> dict:
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


def _validate_package(package: str) -> str | None:
    if not _PACKAGE_RE.match(package):
        return f"Invalid package name: {package}. Must match kolibri-[a-z0-9._-]+"
    return None


def install(node_id: str, package: str) -> dict:
    err = _validate_package(package)
    if err:
        return {"error": err}
    safe_pkg = shlex.quote(package)
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": f"pip3 install {safe_pkg} 2>&1 || echo 'Package {safe_pkg} not found via pip'",
        "objective": f"Install {package} on {node_id}",
        "kind": "generic_implementation",
    })


def update(node_id: str, package: str) -> dict:
    err = _validate_package(package)
    if err:
        return {"error": err}
    safe_pkg = shlex.quote(package)
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": f"pip3 install --upgrade {safe_pkg} 2>&1 || echo 'Update not available'",
        "objective": f"Update {package} on {node_id}",
        "kind": "generic_implementation",
    })


def remove(node_id: str, package: str) -> dict:
    err = _validate_package(package)
    if err:
        return {"error": err}
    safe_pkg = shlex.quote(package)
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": f"pip3 uninstall -y {safe_pkg} 2>&1 || echo 'Package not installed'",
        "objective": f"Remove {package} from {node_id}",
        "kind": "generic_implementation",
    })


def list_installed(node_id: str) -> dict:
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": "pip3 list 2>/dev/null | grep -i kolibri || echo 'No kolibri packages found'",
        "objective": f"List installed packages on {node_id}",
        "kind": "read_only_probe",
    })


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("Usage: package_manager.py <install|update|remove|list> <node_id> <package>")
        print("Available packages:", ", ".join(PACKAGES.keys()))
        sys.exit(1)

    action = sys.argv[1]
    node_id = sys.argv[2]
    package = sys.argv[3]

    if action == "install":
        print(json.dumps(install(node_id, package), indent=2))
    elif action == "update":
        print(json.dumps(update(node_id, package), indent=2))
    elif action == "remove":
        print(json.dumps(remove(node_id, package), indent=2))
    elif action == "list":
        print(json.dumps(list_installed(node_id), indent=2))
