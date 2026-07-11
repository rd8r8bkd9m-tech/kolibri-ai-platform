#!/usr/bin/env python3
"""Plan or run an API-only, per-node factory capability proof campaign.

The default command is read-only ``plan``.  ``run``/``apply`` require an
explicit confirmation flag and submit only ``read_only_probe`` tasks through
the canonical Home Control Plane API.  Node identities always come from the
live replicated mesh projection; this module contains no fleet aliases.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from control_plane_endpoint import (  # noqa: E402
    ControlPlaneEndpointError,
    resolve_home_control_plane_url,
)


PLAN_SCHEMA = "kolibri.fleet-capability-proof-plan.v1"
REPORT_SCHEMA = "kolibri.fleet-capability-proof-campaign.v1"
EVIDENCE_SCHEMA = "kolibri.task-completion-evidence.v1"
VERIFIER_SCHEMA = "kolibri.control-plane-completion-verifier.v1"
BINDING_SCHEMA = "kolibri.task-completion-binding.v1"
TERMINAL_STATES = frozenset({"cancelled", "completed", "dead_letter", "failed"})


class CampaignError(RuntimeError):
    """Stable failure that contains no response body or credential material."""


def canonical_json_sha256(value: Any) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CampaignError("campaign_result_not_canonical_json") from exc
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def completion_binding_sha256(task: dict[str, Any], result_sha256: str) -> str:
    return canonical_json_sha256({
        "schema_version": BINDING_SCHEMA,
        "task_id": str(task.get("task_id") or ""),
        "attempt_id": str(task.get("attempt_id") or ""),
        "lease_owner": str(task.get("lease_owner") or ""),
        "result_reference": str(task.get("result_reference") or ""),
        "result_sha256": result_sha256,
    })


class ControlPlaneClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        bearer_token: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.bearer_token = bearer_token

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        data = None
        headers = {"Accept": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, method=method, headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise CampaignError(f"control_plane_request_failed:{method}:{path}") from exc
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise CampaignError(f"control_plane_invalid_json:{method}:{path}") from exc


def _safe_node_id(value: Any) -> str:
    node_id = str(value or "")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?", node_id):
        raise CampaignError("campaign_canonical_node_id_invalid")
    return node_id


def build_campaign_plan(
    fleet_payload: dict[str, Any],
    *,
    expected_nodes: int | None = None,
    campaign_id: str | None = None,
) -> dict[str, Any]:
    nodes = fleet_payload.get("nodes")
    membership = fleet_payload.get("membership")
    if not isinstance(nodes, list) or not isinstance(membership, dict):
        raise CampaignError("campaign_fleet_payload_invalid")
    if membership.get("authority") != "replicated_mesh_manifest":
        raise CampaignError("campaign_membership_authority_invalid")
    digest = str(membership.get("digest") or "").lower()
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise CampaignError("campaign_membership_digest_invalid")
    canonical_total = membership.get("canonical_total")
    if type(canonical_total) is not int or canonical_total < 1 or len(nodes) != canonical_total:
        raise CampaignError("campaign_canonical_fleet_size_mismatch")
    if expected_nodes is not None and expected_nodes < 0:
        raise CampaignError("campaign_operator_expected_fleet_size_invalid")
    if expected_nodes not in {None, 0} and canonical_total != expected_nodes:
        raise CampaignError("campaign_operator_expected_fleet_size_mismatch")
    node_ids = [_safe_node_id(node.get("node_id")) for node in nodes if isinstance(node, dict)]
    if len(node_ids) != canonical_total or len(set(node_ids)) != canonical_total:
        raise CampaignError("campaign_canonical_node_identity_ambiguous")

    if campaign_id is None:
        campaign_id = f"fleet-proof-{digest[:12]}-{uuid.uuid4().hex[:16]}"
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9._-]{0,78}[a-z0-9])?", campaign_id):
        raise CampaignError("campaign_id_invalid")
    rows: list[dict[str, Any]] = []
    blockers: list[dict[str, str]] = []
    by_id = {str(node.get("node_id")): node for node in nodes}
    for node_id in sorted(node_ids):
        node = by_id[node_id]
        capabilities = [
            str(item) for item in node.get("capabilities") or [] if isinstance(item, str)
        ]
        reasons: list[str] = []
        if node.get("freshness") != "fresh":
            reasons.append("node_not_fresh")
        if node.get("schedulable") is not True:
            reasons.append("node_not_schedulable")
        if "read_only_probe" not in capabilities:
            reasons.append("read_only_probe_capability_missing")
        task_digest = hashlib.sha256(
            f"{campaign_id}\0{node_id}".encode("utf-8")
        ).hexdigest()[:16]
        task_id = f"KOL-FLEET-PROOF-{digest[:12]}-{task_digest}"
        envelope = {
            "schema_version": "kolibri.factory-task.v1",
            "task_id": task_id,
            "idempotency_key": f"{campaign_id}:{node_id}",
            "kind": "read_only_probe",
            "objective": "Produce attempt-bound, content-verified read-only capability evidence.",
            "target_node": node_id,
            "required_capability": "read_only_probe",
            "read_only": True,
            "fallback_allowed": False,
            "max_retries": 1,
            "source": {
                "kind": "fleet_capability_proof_campaign",
                "campaign_id": campaign_id,
                "membership_digest": digest,
            },
            "acceptance": [
                "result status is completed",
                "result payload has a canonical SHA-256",
                "attempt/lease/result binding verifier passes",
            ],
        }
        rows.append({
            "node_id": node_id,
            "freshness": node.get("freshness"),
            "schedulable": node.get("schedulable") is True,
            "ready": not reasons,
            "blockers": reasons,
            "task_id": task_id,
            "envelope": envelope,
        })
        blockers.extend({"node_id": node_id, "reason": reason} for reason in reasons)
    return {
        "schema_version": PLAN_SCHEMA,
        "status": "ready" if not blockers else "blocked",
        "mode": "read_only_plan",
        "campaign_id": campaign_id,
        "membership": {
            "authority": membership["authority"],
            "digest": digest,
            "canonical_total": canonical_total,
            "epoch": membership.get("epoch"),
        },
        "summary": {
            "canonical_total": canonical_total,
            "ready_total": sum(1 for row in rows if row["ready"]),
            "blocked_total": len(blockers),
        },
        "blockers": blockers,
        "nodes": rows,
    }


def validate_completed_task(
    task: dict[str, Any],
    node_id: str,
    *,
    campaign_id: str | None = None,
    membership_digest: str | None = None,
) -> dict[str, Any]:
    evidence = task.get("completion_evidence")
    verifier = task.get("completion_verifier")
    result = task.get("result")
    reasons: list[str] = []
    if task.get("state") != "completed":
        reasons.append(f"terminal_state_{task.get('state') or 'unknown'}")
    if not isinstance(result, dict) or not result:
        reasons.append("result_missing")
    if not isinstance(evidence, dict) or evidence.get("schema_version") != EVIDENCE_SCHEMA:
        reasons.append("completion_evidence_invalid")
    if not isinstance(verifier, dict) or verifier.get("schema_version") != VERIFIER_SCHEMA:
        reasons.append("completion_verifier_invalid")
    if isinstance(verifier, dict):
        if verifier.get("verdict") != "passed" or verifier.get("independent") is not True:
            reasons.append("completion_verifier_not_passed")
        if verifier.get("node_id") != node_id:
            reasons.append("completion_verifier_node_mismatch")
        checks = verifier.get("checks")
        if not isinstance(checks, dict) or not checks or not all(value is True for value in checks.values()):
            reasons.append("completion_verifier_checks_failed")
    if isinstance(result, dict) and isinstance(evidence, dict) and isinstance(verifier, dict):
        result_digest = canonical_json_sha256(result)
        binding_digest = completion_binding_sha256(task, result_digest)
        if evidence.get("result_sha256") != result_digest or verifier.get("result_sha256") != result_digest:
            reasons.append("result_sha256_mismatch")
        if evidence.get("binding_sha256") != binding_digest or verifier.get("binding_sha256") != binding_digest:
            reasons.append("binding_sha256_mismatch")
        if evidence.get("task_id") != task.get("task_id"):
            reasons.append("evidence_task_mismatch")
        if evidence.get("attempt_id") != task.get("attempt_id"):
            reasons.append("evidence_attempt_mismatch")
        if evidence.get("lease_owner") != task.get("lease_owner"):
            reasons.append("evidence_lease_owner_mismatch")
    target = (task.get("envelope") or {}).get("target_node")
    if target != node_id:
        reasons.append("task_target_mismatch")
    source = (task.get("envelope") or {}).get("source")
    if campaign_id is not None or membership_digest is not None:
        if not isinstance(source, dict) or source.get("kind") != "fleet_capability_proof_campaign":
            reasons.append("campaign_source_invalid")
        else:
            if source.get("campaign_id") != campaign_id:
                reasons.append("campaign_id_mismatch")
            if source.get("membership_digest") != membership_digest:
                reasons.append("campaign_membership_digest_mismatch")
    proof = evidence if isinstance(evidence, dict) else {}
    return {
        "node_id": node_id,
        "task_id": task.get("task_id"),
        "state": task.get("state"),
        "verified": not reasons,
        "reasons": sorted(set(reasons)),
        "attempt_id": task.get("attempt_id"),
        "result_sha256": proof.get("result_sha256"),
        "binding_sha256": proof.get("binding_sha256"),
    }


def execute_campaign(
    client: ControlPlaneClient,
    plan: dict[str, Any],
    *,
    timeout_seconds: float = 180.0,
    poll_interval_seconds: float = 1.0,
) -> dict[str, Any]:
    if plan.get("status") != "ready":
        raise CampaignError("campaign_plan_not_ready")
    task_to_node: dict[str, str] = {}
    for row in plan["nodes"]:
        created = client.request("POST", "/v1/tasks", row["envelope"])
        task_id = str(created.get("task_id") or "")
        if task_id != row["task_id"]:
            raise CampaignError("campaign_task_identity_mismatch")
        task_to_node[task_id] = row["node_id"]

    deadline = time.monotonic() + max(1.0, float(timeout_seconds))
    terminal: dict[str, dict[str, Any]] = {}
    while len(terminal) < len(task_to_node) and time.monotonic() < deadline:
        for task_id in sorted(set(task_to_node) - set(terminal)):
            task = client.request("GET", f"/v1/tasks/{urllib.parse.quote(task_id, safe='')}")
            if task.get("state") in TERMINAL_STATES:
                terminal[task_id] = task
        if len(terminal) < len(task_to_node):
            time.sleep(max(0.05, float(poll_interval_seconds)))

    rows: list[dict[str, Any]] = []
    for task_id, node_id in sorted(task_to_node.items(), key=lambda item: item[1]):
        task = terminal.get(task_id)
        if task is None:
            rows.append({
                "node_id": node_id,
                "task_id": task_id,
                "state": "timeout",
                "verified": False,
                "reasons": ["campaign_timeout"],
                "attempt_id": None,
                "result_sha256": None,
                "binding_sha256": None,
            })
        else:
            rows.append(validate_completed_task(
                task,
                node_id,
                campaign_id=str(plan["campaign_id"]),
                membership_digest=str(plan["membership"]["digest"]),
            ))
    verified_total = sum(1 for row in rows if row["verified"])
    return {
        "schema_version": REPORT_SCHEMA,
        "status": "completed" if verified_total == len(rows) else "incomplete",
        "campaign_id": plan["campaign_id"],
        "membership": dict(plan["membership"]),
        "summary": {
            "canonical_total": len(rows),
            "verified_total": verified_total,
            "failed_total": len(rows) - verified_total,
        },
        "nodes": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("plan", "run", "apply"), default="plan")
    parser.add_argument("--control-url", default=os.environ.get("KOLIBRI_FACTORY_CONTROL_URL"))
    parser.add_argument("--control-urls", default=os.environ.get("KOLIBRI_FACTORY_CONTROL_URLS"))
    parser.add_argument("--manifest", default=os.environ.get("KOLIBRI_MESH_MEMBERSHIP_MANIFEST"))
    parser.add_argument(
        "--expected-nodes",
        type=int,
        help="optional operator assertion; membership size is dynamic by default",
    )
    parser.add_argument(
        "--campaign-id",
        help="optional bounded ID for reproducible idempotent replay; generated otherwise",
    )
    parser.add_argument(
        "--auth-token-file",
        default=os.environ.get("KOLIBRI_FACTORY_API_TOKEN_FILE"),
        help="0600 bearer-token file; required for run/apply and never printed",
    )
    parser.add_argument("--request-timeout", type=float, default=10.0)
    parser.add_argument("--campaign-timeout", type=float, default=180.0)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument(
        "--confirm-run",
        action="store_true",
        help="required with run/apply; confirms submission of read-only tasks",
    )
    return parser


def read_bearer_token(path_value: str | None, *, required: bool) -> str | None:
    if not path_value:
        if required:
            raise CampaignError("campaign_api_auth_token_file_required")
        return None
    path = Path(path_value).expanduser()
    try:
        info = path.stat()
    except OSError as exc:
        raise CampaignError("campaign_api_auth_token_file_unreadable") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise CampaignError("campaign_api_auth_token_file_permissions_invalid")
    try:
        token = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise CampaignError("campaign_api_auth_token_file_unreadable") from exc
    if not re.fullmatch(r"[^\s]{24,4096}", token):
        raise CampaignError("campaign_api_auth_token_invalid")
    return token


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        control_url = resolve_home_control_plane_url(
            args.control_url,
            args.control_urls,
            manifest_path=args.manifest,
        )
        bearer_token = read_bearer_token(
            args.auth_token_file,
            required=args.command in {"run", "apply"},
        )
        client = ControlPlaneClient(
            control_url,
            timeout=args.request_timeout,
            bearer_token=bearer_token,
        )
        fleet = client.request("GET", "/v1/nodes?scope=active&limit=250")
        plan = build_campaign_plan(
            fleet,
            expected_nodes=args.expected_nodes,
            campaign_id=args.campaign_id,
        )
        if args.command == "plan":
            print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if plan["status"] == "ready" else 2
        if not args.confirm_run:
            raise CampaignError("campaign_explicit_confirmation_required")
        report = execute_campaign(
            client,
            plan,
            timeout_seconds=args.campaign_timeout,
            poll_interval_seconds=args.poll_interval,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["status"] == "completed" else 2
    except (CampaignError, ControlPlaneEndpointError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
