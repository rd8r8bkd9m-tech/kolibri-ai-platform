#!/usr/bin/env python3
"""Fail closed unless every canonical node has a content-bound campaign result."""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


SHA256 = re.compile(r"^[a-f0-9]{64}$")


def get_json(control_url: str, path: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{control_url.rstrip('/')}{path}",
        method="GET",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"factory_campaign_api_unavailable:{path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"factory_campaign_payload_invalid:{path}")
    return payload


def canonical_node_ids(control_url: str) -> list[str]:
    payload = get_json(control_url, "/v1/nodes?scope=active&limit=250")
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        raise RuntimeError("canonical_fleet_unavailable")
    ids = sorted(
        str(node.get("node_id") or "")
        for node in nodes
        if isinstance(node, dict) and node.get("schedulable") is True
    )
    if not ids or any(not node_id for node_id in ids) or len(ids) != len(set(ids)):
        raise RuntimeError("canonical_fleet_invalid")
    return ids


def proof_failures(task: dict[str, Any], node_id: str) -> list[str]:
    failures: list[str] = []
    result = task.get("result")
    evidence = task.get("completion_evidence")
    verifier = task.get("completion_verifier")
    fencing_token = task.get("fencing_token")
    lease_owner = str(task.get("lease_owner") or "")

    checks = {
        "state": task.get("state") == "completed",
        "attempt_id": bool(task.get("attempt_id")),
        "fencing_token": type(fencing_token) is int and fencing_token > 0,
        "target_node": task.get("envelope", {}).get("target_node") == node_id,
        "lease_owner": lease_owner.startswith(f"{node_id}:"),
        "result": isinstance(result, dict) and bool(result),
        "result_reference": bool(str(task.get("result_reference") or "").strip()),
        "evidence": isinstance(evidence, dict),
        "verifier": isinstance(verifier, dict),
    }
    if isinstance(evidence, dict):
        checks.update(
            {
                "evidence_attempt": evidence.get("attempt_id") == task.get("attempt_id"),
                "evidence_fence": evidence.get("fencing_token") == fencing_token,
                "result_sha256": bool(SHA256.fullmatch(str(evidence.get("result_sha256") or ""))),
                "binding_sha256": bool(SHA256.fullmatch(str(evidence.get("binding_sha256") or ""))),
            }
        )
    if isinstance(verifier, dict):
        verifier_checks = verifier.get("checks")
        checks.update(
            {
                "verifier_authority": verifier.get("verifier") == "control-plane/home",
                "verifier_independent": verifier.get("independent") is True,
                "verifier_verdict": verifier.get("verdict") == "passed",
                "verifier_checks": isinstance(verifier_checks, dict)
                and bool(verifier_checks)
                and all(value is True for value in verifier_checks.values()),
            }
        )
    failures.extend(name for name, passed in checks.items() if not passed)
    return sorted(failures)


def verify_campaign(control_url: str, prefix: str) -> dict[str, Any]:
    nodes = canonical_node_ids(control_url)
    rows = []
    for node_id in nodes:
        task_id = f"{prefix}{node_id}"
        path = f"/v1/tasks/{urllib.parse.quote(task_id, safe='')}"
        task = get_json(control_url, path)
        failures = proof_failures(task, node_id)
        rows.append(
            {
                "node_id": node_id,
                "task_id": task_id,
                "state": task.get("state"),
                "verdict": "passed" if not failures else "failed",
                "failed_checks": failures,
            }
        )
    passed = sum(row["verdict"] == "passed" for row in rows)
    return {
        "schema_version": "kolibri.factory-campaign-verification.v1",
        "status": "passed" if passed == len(rows) else "failed",
        "canonical_nodes": len(rows),
        "verified_nodes": passed,
        "failed_nodes": len(rows) - passed,
        "tasks": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-url", required=True)
    parser.add_argument("--task-prefix", required=True)
    args = parser.parse_args()
    report = verify_campaign(args.control_url, args.task_prefix)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
