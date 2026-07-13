#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

import httpx


def run(control_url: str, token: str, owner_token: str) -> dict:
    node_headers = {"X-Kolibri-Node-Token": token}
    client = httpx.Client(base_url=control_url.rstrip("/"), timeout=30)
    boot = client.post("/v1/shell/bootstrap", headers={"X-Kolibri-Access-Token": owner_token}, json={"role": "owner"})
    boot.raise_for_status()
    session_token = boot.json()["session"]["token"]
    project_id = boot.json()["active_project"]["id"]
    owner_headers = {"Authorization": f"Bearer {session_token}"}
    task = client.post(
        "/v1/tasks",
        headers=owner_headers,
        json={
            "project_id": project_id,
            "kind": "health_probe",
            "title": "V2.1 factory canary",
            "required_capabilities": ["health.probe"],
            "required_artifacts": ["RESULT.md"],
        },
    )
    task.raise_for_status()
    task_id = task.json()["id"]
    with tempfile.TemporaryDirectory() as workdir:
        command = [
            sys.executable,
            "services/node-runtime/kolibri_node.py",
            "--control-url", control_url,
            "--node-id", "canary-worker",
            "--token", token,
            "--workdir", workdir,
            "--once",
        ]
        subprocess.run(command, check=True)
    completed = client.get(f"/v1/tasks/{task_id}", headers=owner_headers)
    completed.raise_for_status()
    events = client.get(f"/v1/tasks/{task_id}/events", headers=owner_headers).json()["data"]
    required = {"task.created", "lease.granted", "lease.heartbeat", "artifact.written", "worker.executed", "verifier.checked", "task.completed"}
    event_types = {event["type"] for event in events}
    if completed.json()["status"] != "completed" or not required.issubset(event_types):
        raise RuntimeError({"task": completed.json(), "events": events})
    return {"status": "passed", "task_id": task_id, "event_types": sorted(event_types), "result_hash": completed.json()["result_hash"], "verifier_binding": completed.json()["verifier_binding"]}


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--control-url", default="http://127.0.0.1:8191"); p.add_argument("--token", default=os.environ.get("KOLIBRI_NODE_JOIN_TOKEN", "canary-secret")); p.add_argument("--owner-token", default=os.environ.get("KOLIBRI_OWNER_ACCESS_TOKEN", "canary-owner-secret")); args=p.parse_args()
    print(json.dumps(run(args.control_url, args.token, args.owner_token), ensure_ascii=False, indent=2))
