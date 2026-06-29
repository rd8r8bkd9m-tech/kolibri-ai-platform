#!/usr/bin/env python3
"""Publish the MacBook filesystem namespace to Kolibri Control Plane.

This process is intentionally a thin-client publisher. It does not execute
factory tasks locally and it does not expose a writable shared root.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FILESYSTEM_MODE = "mesh_api_namespace"
FILESYSTEM_WRITE_POLICY = "read-only MacBook namespace; writes require an explicit task lease"
DEFAULT_CONTROL_URL = os.environ.get("KOLIBRI_FACTORY_CONTROL_URL", "http://10.99.0.2:9101").rstrip("/")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def namespace_segment(value: str, fallback: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "_.-" else "-" for ch in str(value).strip())
    return safe or fallback


def disk_usage(path: Path) -> dict[str, int] | None:
    try:
        target = path if path.is_dir() else path.parent
        usage = shutil.disk_usage(str(target))
        return {"total": usage.total, "used": usage.used, "free": usage.free}
    except OSError:
        return None


def machine_stats() -> dict[str, Any]:
    disk = shutil.disk_usage("/")
    ram: dict[str, Any] = {}
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        ram["MemTotal"] = f"{pages * page_size // 1024} kB"
    except (AttributeError, OSError, ValueError):
        pass
    return {
        "cpu": os.cpu_count(),
        "ram": ram,
        "disk": {"total": disk.total, "used": disk.used, "free": disk.free},
    }


def filesystem_root(name: str, path: Path, purpose: str) -> dict[str, Any]:
    safe_name = namespace_segment(name, "root")
    resolved = path.expanduser()
    item: dict[str, Any] = {
        "name": safe_name,
        "path": str(resolved),
        "purpose": purpose,
        "exists": resolved.exists(),
        "writable": False,
        "sensitive": True,
    }
    if item["exists"]:
        item["disk"] = disk_usage(resolved)
    return item


def build_filesystem_manifest(node_id: str, project_path: Path | None = None) -> dict[str, Any]:
    namespace_prefix = f"/kolibri/nodes/{namespace_segment(node_id, 'macbook')}"
    roots = [
        filesystem_root("root", Path("/"), "MacBook full filesystem read-only namespace"),
        filesystem_root("home", Path.home(), "MacBook owner home read-only namespace"),
    ]
    if project_path is not None:
        roots.append(filesystem_root("project", project_path, "current Kolibri project read-only namespace"))
    for root in roots:
        root["namespace"] = f"{namespace_prefix}/{root['name']}"
    return {
        "namespace_prefix": namespace_prefix,
        "mode": FILESYSTEM_MODE,
        "write_policy": FILESYSTEM_WRITE_POLICY,
        "roots": roots,
    }


def request(method: str, url: str, body: dict[str, Any], timeout: int = 20) -> Any:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8")
            return json.loads(payload) if payload else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {detail}") from exc


def build_node_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "node_id": args.node_id,
        "hostname": platform.node(),
        "agent_id": args.agent_id,
        "pid": os.getpid(),
        "capabilities": ["filesystem_namespace", "macbook_thin_client", "owner_workspace"],
        "active_task": None,
        "filesystem": build_filesystem_manifest(args.node_id, Path(args.project_path) if args.project_path else None),
        **machine_stats(),
    }


def publish_once(args: argparse.Namespace) -> dict[str, Any]:
    control_url = args.control_url.rstrip("/")
    payload = build_node_payload(args)
    request("POST", f"{control_url}/v1/nodes/register", payload)
    heartbeat = request("POST", f"{control_url}/v1/nodes/{args.node_id}/heartbeat", payload)
    return {
        "status": "published",
        "control_url": control_url,
        "node_id": args.node_id,
        "agent_id": args.agent_id,
        "pid": os.getpid(),
        "namespace_prefix": payload["filesystem"]["namespace_prefix"],
        "heartbeat_at": heartbeat.get("heartbeat_at") if isinstance(heartbeat, dict) else utc_now(),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish MacBook filesystem namespace to Kolibri Control Plane.")
    parser.add_argument("--control-url", default=DEFAULT_CONTROL_URL)
    parser.add_argument("--node-id", default=os.environ.get("KOLIBRI_MACBOOK_NODE_ID", "macbook"))
    parser.add_argument("--agent-id", default=os.environ.get("KOLIBRI_MACBOOK_AGENT_ID", "macbook-filesystem-publisher"))
    parser.add_argument("--project-path", default=os.environ.get("KOLIBRI_OWNER_PROJECT_PATH", str(Path.cwd())))
    parser.add_argument("--interval", type=int, default=int(os.environ.get("KOLIBRI_MACBOOK_PUBLISH_INTERVAL", "30")))
    parser.add_argument("--once", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    while True:
        result = publish_once(args)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        sys.stdout.flush()
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
