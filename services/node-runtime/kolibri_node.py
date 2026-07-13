#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path

import httpx


def headers(token: str | None) -> dict[str, str]:
    return {"X-Kolibri-Node-Token": token} if token else {}


def execute(task: dict, workdir: Path) -> tuple[str, bytes, str, dict]:
    kind = task.get("kind")
    workdir.mkdir(parents=True, exist_ok=True)
    if kind == "health_probe":
        content = (
            "# Kolibri node health proof\n\n"
            f"node: {socket.gethostname()}\n"
            f"task: {task['id']}\n"
            "status: healthy\n"
        ).encode()
        return "RESULT.md", content, "text/markdown", {"status": "healthy", "proof": "non_empty_artifact"}
    if kind == "capability_probe":
        content = json.dumps(
            {"node": socket.gethostname(), "task_id": task["id"], "capabilities": task.get("required_capabilities", []), "verified": True},
            ensure_ascii=False,
            indent=2,
        ).encode()
        return "RESULT.json", content, "application/json", {"verified": True}
    raise RuntimeError(f"Unsupported task kind: {kind}")


def run(args: argparse.Namespace) -> int:
    token = args.token or os.environ.get("KOLIBRI_NODE_JOIN_TOKEN")
    client = httpx.Client(base_url=args.control_url.rstrip("/"), headers=headers(token), timeout=30)
    registration = client.post(
        "/v1/nodes/register",
        json={"node_id": args.node_id, "hostname": socket.gethostname(), "capabilities": args.capability},
    )
    registration.raise_for_status()
    while True:
        client.post(
            f"/v1/nodes/{args.node_id}/heartbeat",
            json={"status": "online", "capabilities": args.capability, "active_attempts": []},
        ).raise_for_status()
        lease_response = client.post(
            "/v1/tasks/lease",
            json={"node_id": args.node_id, "capabilities": args.capability, "lease_seconds": args.lease_seconds},
        )
        lease_response.raise_for_status()
        task = lease_response.json().get("task")
        if not task:
            if args.once:
                return 0
            time.sleep(args.poll_seconds)
            continue
        try:
            client.post(
                f"/v1/tasks/{task['id']}/heartbeat",
                json={"node_id": args.node_id, "lease_id": task["lease_id"], "fencing_token": task["fencing_token"], "lease_seconds": args.lease_seconds},
            ).raise_for_status()
            name, content, mime, result = execute(task, Path(args.workdir) / task["id"])
            upload = client.post(
                f"/v1/tasks/{task['id']}/artifacts",
                data={"node_id": args.node_id, "lease_id": task["lease_id"], "fencing_token": str(task["fencing_token"])},
                files={"file": (name, content, mime)},
            )
            upload.raise_for_status()
            complete = client.post(
                f"/v1/tasks/{task['id']}/complete",
                json={"node_id": args.node_id, "lease_id": task["lease_id"], "fencing_token": task["fencing_token"], "result": result},
            )
            complete.raise_for_status()
            print(json.dumps({"node_id": args.node_id, "task_id": task["id"], "status": complete.json()["status"]}, ensure_ascii=False))
        except Exception as exc:
            client.post(f"/v1/tasks/{task['id']}/fail", json={"reason": str(exc)})
            print(f"task failed: {exc}", file=sys.stderr)
            if args.once:
                return 1
        if args.once:
            return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Kolibri V2.1 safe node runtime")
    p.add_argument("--control-url", default=os.environ.get("KOLIBRI_CONTROL_URL", "http://127.0.0.1:8191"))
    p.add_argument("--node-id", default=os.environ.get("KOLIBRI_NODE_ID", socket.gethostname()))
    p.add_argument("--token", default=None)
    p.add_argument("--capability", action="append", default=["health.probe"])
    p.add_argument("--workdir", default=os.environ.get("KOLIBRI_NODE_WORKDIR", "data/node-work"))
    p.add_argument("--poll-seconds", type=float, default=2.0)
    p.add_argument("--lease-seconds", type=int, default=60)
    p.add_argument("--once", action="store_true")
    return p


if __name__ == "__main__":
    raise SystemExit(run(parser().parse_args()))
