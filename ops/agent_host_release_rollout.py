#!/usr/bin/env python3
"""Signed, API-only progressive rollout for the Agent Host runtime.

The generic release controller owns signature/approval/task/rollback mechanics.
This module adds the Agent Host-specific gates that it cannot infer:

* runtime membership is discovered from Home for every campaign;
* rollout waves are selected deterministically without per-node stage labels;
* a successful release must cause the bootstrap Agent Host to re-exec the
  release-bound runtime;
* a targeted read-only probe proves the exact runner completion payload;
* the pre-switch proof and the strict Control Plane proof are separate
  campaigns, preventing a circular dependency or a fabricated verifier.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

try:
    from ops.release_controller import (
        RELEASE_SCHEMA,
        TERMINAL_TASK_STATES,
        ControlPlaneClient,
        FleetNode,
        ReleaseError,
        RolloutWave,
        VerifiedRelease,
        canonical_fleet,
        load_release_manifest,
        verify_ssh_signature,
    )
    from ops.release_authority import canonical_rollout_plan
except ImportError:  # installed standalone beside the release controller
    from release_controller import (  # type: ignore[no-redef]
        RELEASE_SCHEMA,
        TERMINAL_TASK_STATES,
        ControlPlaneClient,
        FleetNode,
        ReleaseError,
        RolloutWave,
        VerifiedRelease,
        canonical_fleet,
        load_release_manifest,
        verify_ssh_signature,
    )
    from release_authority import canonical_rollout_plan  # type: ignore[no-redef]


AGENT_HOST_ROLLOUT_SCHEMA = "kolibri.agent-host-rollout.v1"
AGENT_HOST_RUNTIME_SCHEMA = "kolibri.agent-host-runtime.v1"
AGENT_HOST_RUNTIME_PATH = "ops/agent_host.py"
MIMO_RESPONSE_AGENT_PROFILE_PATH = "ops/mimo/kolibri-response-only.md"
HANDSHAKE_TASK_SCHEMA = "kolibri.agent-host-handshake.v1"
HANDSHAKE_TASK_KIND = "read_only_probe"
HANDSHAKE_CAPABILITY = "read_only_probe"
PRE_SWITCH_PHASE = "pre_switch"
STRICT_PHASE = "strict"
COMPLETION_EVIDENCE_SCHEMA = "kolibri.task-completion-evidence.v1"
COMPLETION_BINDING_SCHEMA = "kolibri.task-completion-binding.v1"
COMPLETION_VERIFIER_SCHEMA = "kolibri.control-plane-completion-verifier.v1"
SAFE_CAMPAIGN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}")


def _canonical_json_sha256(value: Any) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ReleaseError("handshake result is not canonical JSON") from exc
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _binding_sha256(task: dict[str, Any], result_reference: str, result_sha256: str) -> str:
    payload: dict[str, Any] = {
        "schema_version": COMPLETION_BINDING_SCHEMA,
        "task_id": str(task.get("task_id") or ""),
        "attempt_id": str(task.get("attempt_id") or ""),
        "lease_owner": str(task.get("lease_owner") or ""),
        "result_reference": result_reference,
        "result_sha256": result_sha256,
    }
    if "fencing_token" in task:
        payload["fencing_token"] = task.get("fencing_token")
    return _canonical_json_sha256(payload)


def _runtime_record(verified: VerifiedRelease) -> tuple[str, str]:
    records = [item for item in verified.manifest.files if item.path == AGENT_HOST_RUNTIME_PATH]
    if len(records) != 1:
        raise ReleaseError("signed release must contain exactly one ops/agent_host.py runtime")
    return records[0].path, records[0].sha256


def _response_profile_record(verified: VerifiedRelease) -> tuple[str, str]:
    records = [
        item
        for item in verified.manifest.files
        if item.path == MIMO_RESPONSE_AGENT_PROFILE_PATH
    ]
    if len(records) != 1:
        raise ReleaseError(
            "signed Agent Host release must contain exactly one "
            "ops/mimo/kolibri-response-only.md profile"
        )
    return records[0].path, records[0].sha256


def _require_campaign_id(campaign_id: str) -> str:
    if not SAFE_CAMPAIGN_ID.fullmatch(campaign_id):
        raise ReleaseError("Agent Host handshake campaign id is invalid")
    return campaign_id


def _rollback_campaign_id(campaign_id: str) -> str:
    candidate = f"{campaign_id}:rollback"
    if SAFE_CAMPAIGN_ID.fullmatch(candidate):
        return candidate
    return f"rollback:{hashlib.sha256(campaign_id.encode('utf-8')).hexdigest()}"


def _semantic_nodes_payload(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        raise ReleaseError("Control Plane returned an invalid semantic fleet payload")
    data = value.get("data")
    nodes = data.get("nodes") if isinstance(data, dict) else None
    if not isinstance(nodes, list) or any(not isinstance(item, dict) for item in nodes):
        raise ReleaseError("Control Plane returned an invalid semantic fleet payload")
    return nodes


def discover_agent_host_fleet(client: ControlPlaneClient) -> list[FleetNode]:
    """Join canonical active membership with semantic roles from Home."""

    active = client.fleet()
    semantic = _semantic_nodes_payload(client.request("GET", "/v1/fleet/nodes"))
    semantic_by_id: dict[str, dict[str, Any]] = {}
    for value in semantic:
        node_id = str(value.get("node_id") or "").strip()
        if not node_id or node_id in semantic_by_id:
            raise ReleaseError("semantic fleet contains an ambiguous node identity")
        semantic_by_id[node_id] = value
    active_ids = {node.node_id for node in active}
    if active_ids != set(semantic_by_id):
        raise ReleaseError("canonical and semantic fleet snapshots do not match")

    joined: list[FleetNode] = []
    for node in active:
        semantic_node = semantic_by_id[node.node_id]
        labels = semantic_node.get("labels") if isinstance(semantic_node.get("labels"), dict) else {}
        role = str(semantic_node.get("role") or labels.get("role") or "worker").strip().lower()
        failure_domain = str(
            semantic_node.get("failure_domain")
            or labels.get("failure_domain")
            or ""
        ).strip() or None
        joined.append(replace(node, role=role, failure_domain=failure_domain))
    return sorted(joined, key=lambda item: item.physical_node_id)


def _stable_worker_order(nodes: Iterable[FleetNode], seed: str) -> list[FleetNode]:
    return sorted(
        nodes,
        key=lambda node: (
            hashlib.sha256(f"{seed}:{node.physical_node_id}".encode("utf-8")).hexdigest(),
            node.physical_node_id,
        ),
    )


def _take_quorum(workers: list[FleetNode], count: int) -> tuple[list[FleetNode], list[FleetNode]]:
    """Prefer distinct declared failure domains, then fill deterministically."""

    selected: list[FleetNode] = []
    selected_ids: set[str] = set()
    domains: set[str] = set()
    for node in workers:
        domain = str(node.failure_domain or "")
        if domain and domain not in domains:
            selected.append(node)
            selected_ids.add(node.physical_node_id)
            domains.add(domain)
            if len(selected) == count:
                break
    for node in workers:
        if len(selected) == count:
            break
        if node.physical_node_id not in selected_ids:
            selected.append(node)
            selected_ids.add(node.physical_node_id)
    remaining = [node for node in workers if node.physical_node_id not in selected_ids]
    return selected, remaining


def plan_dynamic_agent_host_rollout(
    nodes: Iterable[FleetNode],
    *,
    release_digest: str,
    minimum_nodes: int = 21,
) -> list[RolloutWave]:
    """Plan 21/22+ membership without node names or rollout-stage labels."""

    fleet = list(nodes)
    if minimum_nodes < 1 or len(fleet) < minimum_nodes:
        raise ReleaseError(
            f"canonical fleet size is {len(fleet)}, below required minimum {minimum_nodes}"
        )
    physical_ids = [node.physical_node_id for node in fleet]
    if len(physical_ids) != len(set(physical_ids)):
        raise ReleaseError("canonical fleet contains duplicate physical identities")
    blocked = [
        node.node_id
        for node in fleet
        if not node.schedulable or HANDSHAKE_CAPABILITY not in node.capabilities
    ]
    if blocked:
        raise ReleaseError(
            "Agent Host rollout blocked by non-fresh or incapable nodes: "
            + ", ".join(sorted(blocked))
        )
    authorities = [node for node in fleet if node.role == "control_plane"]
    if len(authorities) != 1:
        raise ReleaseError("Agent Host rollout requires exactly one semantic control_plane role")
    workers = [node for node in fleet if node.role != "control_plane"]
    if len(workers) < 3:
        raise ReleaseError("Agent Host rollout requires at least three worker nodes")
    ordered = _stable_worker_order(workers, release_digest)
    canary, remaining = ordered[0], ordered[1:]
    quorum, remaining = _take_quorum(remaining, min(2, len(remaining)))
    waves = [
        RolloutWave("agent-host-canary", (canary,)),
        RolloutWave("agent-host-quorum", tuple(quorum)),
        RolloutWave("agent-host-workers-3", tuple(remaining[:3])),
        RolloutWave("agent-host-workers-5", tuple(remaining[3:8])),
        RolloutWave("agent-host-workers-rest", tuple(remaining[8:])),
        RolloutWave("agent-host-control-plane-last", tuple(authorities)),
    ]
    waves = [wave for wave in waves if wave.nodes]
    planned = [node.physical_node_id for wave in waves for node in wave.nodes]
    if len(planned) != len(fleet) or len(planned) != len(set(planned)):
        raise ReleaseError("Agent Host rollout did not assign every physical node exactly once")
    return waves


def rollout_plan(waves: Iterable[RolloutWave]) -> list[dict[str, Any]]:
    return canonical_rollout_plan([
        {"name": wave.name, "nodes": [node.node_id for node in wave.nodes]}
        for wave in waves
    ])


def membership_fingerprint(waves: Iterable[RolloutWave]) -> str:
    records = sorted(
        (
            node.physical_node_id,
            node.node_id,
            node.role,
        )
        for wave in waves
        for node in wave.nodes
    )
    identities = [
        {"physical_node_id": physical, "node_id": node_id, "role": role}
        for physical, node_id, role in records
    ]
    return _canonical_json_sha256(identities)


def require_membership_snapshot(
    client: ControlPlaneClient,
    waves: Iterable[RolloutWave],
) -> str:
    """Fail a campaign if dynamic membership changed after plan approval."""

    waves = tuple(waves)
    expected = sorted(
        (node.physical_node_id, node.node_id, node.role)
        for wave in waves
        for node in wave.nodes
    )
    observed = sorted(
        (node.physical_node_id, node.node_id, node.role)
        for node in discover_agent_host_fleet(client)
    )
    if observed != expected:
        raise ReleaseError(
            "dynamic membership changed during Agent Host campaign; re-plan and re-approve"
        )
    return membership_fingerprint(waves)


def submit_handshake_task(
    client: ControlPlaneClient,
    verified: VerifiedRelease,
    node: FleetNode,
    *,
    phase: str,
    campaign_id: str,
) -> dict[str, Any]:
    if phase not in {PRE_SWITCH_PHASE, STRICT_PHASE}:
        raise ReleaseError("unknown Agent Host handshake phase")
    _require_campaign_id(campaign_id)
    runtime_path, runtime_sha256 = _runtime_record(verified)
    response_profile_path, response_profile_sha256 = _response_profile_record(verified)
    return client.request("POST", "/v1/tasks", {
        "schema_version": HANDSHAKE_TASK_SCHEMA,
        "idempotency_key": (
            f"agent-host-handshake:{phase}:{campaign_id}:"
            f"{verified.manifest.digest}:{node.physical_node_id}"
        ),
        "kind": HANDSHAKE_TASK_KIND,
        "required_capability": HANDSHAKE_CAPABILITY,
        "target_node": node.node_id,
        "permission_pack": "read_only",
        "read_only": True,
        "no_push": True,
        "write_scope": [],
        "proof_phase": phase,
        "expected_agent_host_runtime": {
            "schema_version": AGENT_HOST_RUNTIME_SCHEMA,
            "release_id": verified.manifest.release_id,
            "manifest_digest": verified.manifest.digest,
            "runtime_path": runtime_path,
            "runtime_sha256": runtime_sha256,
            "response_profile_path": response_profile_path,
            "response_profile_sha256": response_profile_sha256,
        },
        "max_attempts": 2,
    })


def _validate_raw_handshake(
    task: dict[str, Any],
    node: FleetNode,
    verified: VerifiedRelease,
) -> dict[str, Any]:
    runtime_path, runtime_sha256 = _runtime_record(verified)
    response_profile_path, response_profile_sha256 = _response_profile_record(verified)
    result = task.get("result")
    if task.get("state") != "completed" or not isinstance(result, dict):
        raise ReleaseError(f"Agent Host handshake did not complete on {node.node_id}")
    task_id = str(task.get("task_id") or "")
    attempt_id = str(task.get("attempt_id") or "")
    lease_owner = str(task.get("lease_owner") or "")
    lease_node, separator, lease_agent = lease_owner.partition(":")
    result_reference = str(task.get("result_reference") or "").strip()
    envelope = task.get("envelope") if isinstance(task.get("envelope"), dict) else {}
    runtime = result.get("agent_host_runtime")
    checks = {
        "task": bool(task_id and str(result.get("task_id") or "") == task_id),
        "attempt": bool(attempt_id and str(result.get("attempt_id") or "") == attempt_id),
        "node": bool(
            separator
            and lease_node == node.node_id
            and str(result.get("node_id") or "") == node.node_id
            and envelope.get("target_node") == node.node_id
        ),
        "agent": bool(lease_agent and str(result.get("agent_id") or "") == lease_agent),
        "status": result.get("status") == "completed",
        "result_reference": bool(
            result_reference and str(result.get("result_path") or "") == result_reference
        ),
        "runtime": bool(
            isinstance(runtime, dict)
            and runtime.get("schema_version") == AGENT_HOST_RUNTIME_SCHEMA
            and runtime.get("status") == "release_bound"
            and runtime.get("release_id") == verified.manifest.release_id
            and runtime.get("manifest_digest") == verified.manifest.digest
            and runtime.get("runtime_path") == runtime_path
            and runtime.get("runtime_sha256") == runtime_sha256
            and runtime.get("response_profile_path") == response_profile_path
            and runtime.get("response_profile_sha256") == response_profile_sha256
        ),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise ReleaseError(
            f"Agent Host raw completion handshake failed on {node.node_id}: {','.join(failed)}"
        )
    return {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "node_id": node.node_id,
        "agent_id": lease_agent,
        "status": "completed",
        "result_reference": result_reference,
        "runtime": runtime,
        "raw_checks": checks,
    }


def _validate_strict_control_plane_proof(
    task: dict[str, Any],
    raw: dict[str, Any],
) -> dict[str, Any]:
    evidence = task.get("completion_evidence")
    verifier = task.get("completion_verifier")
    if not isinstance(evidence, dict) or not isinstance(verifier, dict):
        raise ReleaseError("strict Control Plane completion proof is absent")
    result_sha256 = _canonical_json_sha256(task.get("result"))
    binding_sha256 = _binding_sha256(task, raw["result_reference"], result_sha256)
    verifier_checks = verifier.get("checks")
    checks = {
        "evidence_schema": evidence.get("schema_version") == COMPLETION_EVIDENCE_SCHEMA,
        "verifier_schema": verifier.get("schema_version") == COMPLETION_VERIFIER_SCHEMA,
        "independent_home_verifier": bool(
            verifier.get("verifier") == "control-plane/home"
            and verifier.get("independent") is True
            and verifier.get("verdict") == "passed"
        ),
        "verifier_checks": bool(
            isinstance(verifier_checks, dict)
            and verifier_checks
            and all(value is True for value in verifier_checks.values())
            and not verifier.get("failed_checks")
        ),
        "identity_binding": bool(
            evidence.get("task_id") == raw["task_id"]
            and evidence.get("attempt_id") == raw["attempt_id"]
            and evidence.get("lease_owner") == task.get("lease_owner")
            and evidence.get("node_id") == raw["node_id"]
            and evidence.get("agent_id") == raw["agent_id"]
            and evidence.get("result_reference") == raw["result_reference"]
        ),
        "fencing_token": bool(
            "fencing_token" not in task
            or (
                type(task.get("fencing_token")) is int
                and task.get("fencing_token") > 0
                and isinstance(task.get("result"), dict)
                and task.get("result", {}).get("fencing_token") == task.get("fencing_token")
                and evidence.get("fencing_token") == task.get("fencing_token")
                and verifier.get("fencing_token") == task.get("fencing_token")
            )
        ),
        "content_hash": bool(
            evidence.get("result_sha256") == result_sha256
            and verifier.get("result_sha256") == result_sha256
        ),
        "binding_hash": bool(
            evidence.get("binding_sha256") == binding_sha256
            and verifier.get("binding_sha256") == binding_sha256
        ),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise ReleaseError("strict Control Plane completion proof failed: " + ",".join(failed))
    return {
        "schema_version": COMPLETION_VERIFIER_SCHEMA,
        "verdict": "passed",
        "result_sha256": result_sha256,
        "binding_sha256": binding_sha256,
        "checks": checks,
    }


def validate_handshake(
    task: dict[str, Any],
    node: FleetNode,
    verified: VerifiedRelease,
    *,
    phase: str,
) -> dict[str, Any]:
    raw = _validate_raw_handshake(task, node, verified)
    if phase == PRE_SWITCH_PHASE:
        # Old Control Plane may not know the strict verifier schema.  This gate
        # proves only runner-owned fields and release identity; it never creates
        # or treats a local imitation as an independent verifier.
        return {
            **raw,
            "proof_phase": PRE_SWITCH_PHASE,
            "control_plane_verifier": "not_required_pre_switch",
        }
    if phase != STRICT_PHASE:
        raise ReleaseError("unknown Agent Host handshake phase")
    return {
        **raw,
        "proof_phase": STRICT_PHASE,
        "control_plane_verifier": _validate_strict_control_plane_proof(task, raw),
    }


def _require_release_activation_result(
    task: dict[str, Any],
    node: FleetNode,
    verified: VerifiedRelease,
) -> None:
    result = task.get("result")
    runtime_path, runtime_sha256 = _runtime_record(verified)
    response_profile_path, response_profile_sha256 = _response_profile_record(verified)
    activation = result.get("agent_host_runtime") if isinstance(result, dict) else None
    if not (
        task.get("state") == "completed"
        and isinstance(activation, dict)
        and activation.get("included") is True
        and activation.get("release_id") == verified.manifest.release_id
        and activation.get("manifest_digest") == verified.manifest.digest
        and activation.get("runtime_path") == runtime_path
        and activation.get("runtime_sha256") == runtime_sha256
        and activation.get("response_profile_included") is True
        and activation.get("response_profile_path") == response_profile_path
        and activation.get("response_profile_sha256") == response_profile_sha256
    ):
        raise ReleaseError(f"Agent Host release activation evidence failed on {node.node_id}")


def _cancel_pending(client: ControlPlaneClient, task_ids: Iterable[str], reason: str) -> list[str]:
    return client.cancel_and_fence_release_tasks(task_ids, reason)


def _rollback_attempted(
    client: ControlPlaneClient,
    failed_release: VerifiedRelease,
    rollback_release: VerifiedRelease,
    attempted: list[FleetNode],
    approval_id: str,
    plan: list[dict[str, Any]],
    reason: str,
    campaign_id: str,
) -> tuple[bool, list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    failed = False
    for node in reversed(attempted):
        try:
            submitted = client.submit_rollback_task(
                failed_release,
                rollback_release,
                node,
                approval_id,
                reason,
                plan,
            )
            task_id = str(submitted.get("task_id") or "")
            if not task_id:
                raise ReleaseError("rollback submission returned no task_id")
            task = client.wait_for_task(task_id)
            _require_release_activation_result(task, node, rollback_release)
            client.require_release_health(rollback_release, node)
            probe = submit_handshake_task(
                client,
                rollback_release,
                node,
                phase=PRE_SWITCH_PHASE,
                campaign_id=_rollback_campaign_id(campaign_id),
            )
            probe_id = str(probe.get("task_id") or "")
            if not probe_id:
                raise ReleaseError("rollback handshake returned no task_id")
            proof = validate_handshake(
                client.wait_for_task(probe_id),
                node,
                rollback_release,
                phase=PRE_SWITCH_PHASE,
            )
            results.append({"node": node.node_id, "status": "completed", "proof": proof})
        except Exception as exc:
            failed = True
            results.append({
                "node": node.node_id,
                "status": "failed",
                "reason": str(exc)[:500],
            })
    return failed, results


def execute_pre_switch_rollout(
    client: ControlPlaneClient,
    verified: VerifiedRelease,
    rollback_release: VerifiedRelease,
    waves: Iterable[RolloutWave],
    approval_id: str,
    *,
    campaign_id: str,
    enforce_membership_snapshot: bool = True,
) -> dict[str, Any]:
    """Apply Agent Host waves, proving raw payloads before a strict CP switch."""

    _runtime_record(verified)
    _runtime_record(rollback_release)
    _response_profile_record(verified)
    _response_profile_record(rollback_release)
    _require_campaign_id(campaign_id)
    waves = tuple(waves)
    plan = rollout_plan(waves)
    client.require_owner_approval(
        approval_id,
        verified,
        rollback_release=rollback_release,
        rollout_plan=plan,
    )
    attempted: list[FleetNode] = []
    all_task_ids: list[str] = []
    wave_results: list[dict[str, Any]] = []
    try:
        if enforce_membership_snapshot:
            require_membership_snapshot(client, waves)
        for wave in waves:
            if enforce_membership_snapshot:
                require_membership_snapshot(client, waves)
            release_tasks: list[tuple[FleetNode, str]] = []
            for node in wave.nodes:
                submitted = client.submit_release_task(
                    verified, node, wave.name, approval_id, plan
                )
                task_id = str(submitted.get("task_id") or "")
                if not task_id:
                    raise ReleaseError(f"release task returned no task_id for {node.node_id}")
                attempted.append(node)
                all_task_ids.append(task_id)
                release_tasks.append((node, task_id))
            for node, task_id in release_tasks:
                task = client.wait_for_task(task_id)
                _require_release_activation_result(task, node, verified)
                client.require_release_health(verified, node)

            handshakes: list[tuple[FleetNode, str]] = []
            for node, _task_id in release_tasks:
                submitted = submit_handshake_task(
                    client,
                    verified,
                    node,
                    phase=PRE_SWITCH_PHASE,
                    campaign_id=campaign_id,
                )
                probe_id = str(submitted.get("task_id") or "")
                if not probe_id:
                    raise ReleaseError(f"handshake returned no task_id for {node.node_id}")
                all_task_ids.append(probe_id)
                handshakes.append((node, probe_id))
            proofs = [
                validate_handshake(
                    client.wait_for_task(task_id),
                    node,
                    verified,
                    phase=PRE_SWITCH_PHASE,
                )
                for node, task_id in handshakes
            ]
            wave_results.append({
                "wave": wave.name,
                "status": "completed",
                "nodes": [node.node_id for node in wave.nodes],
                "proof_phase": PRE_SWITCH_PHASE,
                "proofs": proofs,
            })
        if enforce_membership_snapshot:
            require_membership_snapshot(client, waves)
        return {
            "schema_version": AGENT_HOST_ROLLOUT_SCHEMA,
            "status": "pre_switch_completed",
            "release_id": verified.manifest.release_id,
            "membership_fingerprint": membership_fingerprint(waves),
            "summary": {
                "canonical_total": sum(len(wave.nodes) for wave in waves),
                "raw_verified_total": sum(len(wave.nodes) for wave in waves),
                "strict_verified_total": 0,
            },
            "waves": wave_results,
            "strict_completion_proven": False,
            "next_gate": "switch strict Control Plane canary, then run a new strict handshake campaign",
            "rollback": {"status": "not_required", "nodes": []},
        }
    except Exception as exc:
        try:
            cancelled = _cancel_pending(client, all_task_ids, str(exc))
        except Exception as cancel_exc:
            return {
                "schema_version": AGENT_HOST_ROLLOUT_SCHEMA,
                "status": "rollback_blocked",
                "failed_reason": str(exc)[:500],
                "cancel_fence_error": str(cancel_exc)[:500],
                "rollback": {"status": "blocked", "nodes": []},
            }
        rollback_failed, rollback_nodes = _rollback_attempted(
            client,
            verified,
            rollback_release,
            attempted,
            approval_id,
            plan,
            str(exc),
            campaign_id,
        )
        return {
            "schema_version": AGENT_HOST_ROLLOUT_SCHEMA,
            "status": "rollback_failed" if rollback_failed else "rolled_back",
            "release_id": verified.manifest.release_id,
            "failed_reason": str(exc)[:500],
            "cancelled_tasks": cancelled,
            "strict_completion_proven": False,
            "rollback": {
                "status": "failed" if rollback_failed else "completed",
                "nodes": rollback_nodes,
            },
        }


def execute_strict_handshake_campaign(
    client: ControlPlaneClient,
    verified: VerifiedRelease,
    waves: Iterable[RolloutWave],
    *,
    campaign_id: str,
    enforce_membership_snapshot: bool = True,
) -> dict[str, Any]:
    """After CP strict canary, independently re-prove every dynamic member."""

    _runtime_record(verified)
    _response_profile_record(verified)
    _require_campaign_id(campaign_id)
    waves = tuple(waves)
    task_ids: list[str] = []
    results: list[dict[str, Any]] = []
    try:
        if enforce_membership_snapshot:
            require_membership_snapshot(client, waves)
        for wave in waves:
            if enforce_membership_snapshot:
                require_membership_snapshot(client, waves)
            submitted: list[tuple[FleetNode, str]] = []
            for node in wave.nodes:
                task = submit_handshake_task(
                    client,
                    verified,
                    node,
                    phase=STRICT_PHASE,
                    campaign_id=campaign_id,
                )
                task_id = str(task.get("task_id") or "")
                if not task_id:
                    raise ReleaseError(f"strict handshake returned no task_id for {node.node_id}")
                task_ids.append(task_id)
                submitted.append((node, task_id))
            proofs = [
                validate_handshake(
                    client.wait_for_task(task_id),
                    node,
                    verified,
                    phase=STRICT_PHASE,
                )
                for node, task_id in submitted
            ]
            results.append({
                "wave": wave.name,
                "status": "completed",
                "nodes": [node.node_id for node in wave.nodes],
                "proof_phase": STRICT_PHASE,
                "proofs": proofs,
            })
        if enforce_membership_snapshot:
            require_membership_snapshot(client, waves)
        return {
            "schema_version": AGENT_HOST_ROLLOUT_SCHEMA,
            "status": "completed",
            "release_id": verified.manifest.release_id,
            "membership_fingerprint": membership_fingerprint(waves),
            "summary": {
                "canonical_total": sum(len(wave.nodes) for wave in waves),
                "raw_verified_total": sum(len(wave.nodes) for wave in waves),
                "strict_verified_total": sum(len(wave.nodes) for wave in waves),
            },
            "strict_completion_proven": True,
            "waves": results,
        }
    except Exception as exc:
        try:
            cancelled = _cancel_pending(client, task_ids, str(exc))
        except Exception as cancel_exc:
            return {
                "schema_version": AGENT_HOST_ROLLOUT_SCHEMA,
                "status": "blocked",
                "failed_reason": str(exc)[:500],
                "cancel_fence_error": str(cancel_exc)[:500],
                "strict_completion_proven": False,
            }
        return {
            "schema_version": AGENT_HOST_ROLLOUT_SCHEMA,
            "status": "blocked",
            "failed_reason": str(exc)[:500],
            "cancelled_tasks": cancelled,
            "strict_completion_proven": False,
        }


def plan_payload(verified: VerifiedRelease, waves: Iterable[RolloutWave]) -> dict[str, Any]:
    waves = tuple(waves)
    return {
        "schema_version": AGENT_HOST_ROLLOUT_SCHEMA,
        "status": "planned",
        "release_id": verified.manifest.release_id,
        "manifest_digest": verified.manifest.digest,
        "membership_source": "control-plane/home dynamic canonical membership",
        "membership_fingerprint": membership_fingerprint(waves),
        "transport": "control-plane-api-only",
        "waves": rollout_plan(waves),
        "proof_campaigns": [PRE_SWITCH_PHASE, STRICT_PHASE],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "apply-pre-switch", "verify-strict"):
        command = commands.add_parser(name)
        command.add_argument("--manifest", required=True)
        command.add_argument("--signature", required=True)
        command.add_argument("--allowed-signers", required=True)
        command.add_argument("--signer-identity", required=True)
        command.add_argument("--minimum-nodes", type=int, default=21)
        command.add_argument("--control-url")
        command.add_argument("--timeout", type=float, default=10.0)
        if name != "plan":
            command.add_argument("--campaign-id", required=True)
        if name == "apply-pre-switch":
            command.add_argument("--rollback-manifest", required=True)
            command.add_argument("--rollback-signature", required=True)
            command.add_argument("--rollback-signer-identity")
            command.add_argument("--approval-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = load_release_manifest(args.manifest)
        verified = verify_ssh_signature(
            manifest,
            Path(args.signature),
            Path(args.allowed_signers),
            args.signer_identity,
        )
        _runtime_record(verified)
        _response_profile_record(verified)
        client = ControlPlaneClient.from_environment(
            timeout=args.timeout,
            control_url=args.control_url,
        )
        fleet = discover_agent_host_fleet(client)
        waves = plan_dynamic_agent_host_rollout(
            fleet,
            release_digest=manifest.digest,
            minimum_nodes=args.minimum_nodes,
        )
        if args.command == "plan":
            result = plan_payload(verified, waves)
        elif args.command == "verify-strict":
            result = execute_strict_handshake_campaign(
                client, verified, waves, campaign_id=args.campaign_id
            )
        else:
            rollback_manifest = load_release_manifest(args.rollback_manifest)
            rollback_verified = verify_ssh_signature(
                rollback_manifest,
                Path(args.rollback_signature),
                Path(args.allowed_signers),
                args.rollback_signer_identity or args.signer_identity,
            )
            result = execute_pre_switch_rollout(
                client,
                verified,
                rollback_verified,
                waves,
                args.approval_id,
                campaign_id=args.campaign_id,
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("status") in {"planned", "pre_switch_completed", "completed"} else 1
    except ReleaseError as exc:
        print(json.dumps({
            "schema_version": AGENT_HOST_ROLLOUT_SCHEMA,
            "status": "blocked",
            "reason": str(exc),
        }, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
