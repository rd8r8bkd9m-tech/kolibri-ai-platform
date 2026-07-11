#!/usr/bin/env python3
"""API-only, signature-gated progressive release controller.

This module never opens SSH sessions and never restarts a service itself.  It
discovers current membership from the Control Plane and submits one fenced
release task per physical node.  The actual installer remains a worker
capability and therefore produces the same lease, event and evidence records
as every other factory task.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:
    from ops.control_plane_endpoint import ControlPlaneEndpointError, resolve_home_control_plane_url
except ImportError:  # installed standalone beside this script
    from control_plane_endpoint import ControlPlaneEndpointError, resolve_home_control_plane_url

try:
    from ops.release_authority import (
        ReleaseAuthorityError,
        approval_attestation_digest,
        canonical_owner_approval_attestation,
        canonical_rollout_plan,
    )
except ImportError:  # installed standalone beside this script
    from release_authority import (
        ReleaseAuthorityError,
        approval_attestation_digest,
        canonical_owner_approval_attestation,
        canonical_rollout_plan,
    )


RELEASE_SCHEMA = "kolibri.release.v1"
RELEASE_TASK_KIND = "release_bundle_apply"
ROLLBACK_TASK_KIND = "release_bundle_rollback"
RELEASE_CAPABILITY = "release_apply_v1"
SIGNATURE_NAMESPACE = "kolibri-release"
TERMINAL_TASK_STATES = {"completed", "failed", "cancelled", "dead_letter"}
SECRET_METADATA_KEYS = {
    "access_token", "api_key", "authorization", "cookie", "credential", "password",
    "private_key", "refresh_token", "secret", "secret_key", "token",
}


class ReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseFile:
    path: str
    sha256: str
    size_bytes: int
    mode: str = "0644"

    def validate(self) -> None:
        candidate = Path(self.path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ReleaseError(f"unsafe release path: {self.path}")
        if len(self.sha256) != 64 or any(char not in "0123456789abcdef" for char in self.sha256):
            raise ReleaseError(f"invalid sha256 for {self.path}")
        if self.size_bytes < 0:
            raise ReleaseError(f"invalid size for {self.path}")


@dataclass(frozen=True)
class ReleaseManifest:
    release_id: str
    source_commit: str
    artifact_uri: str
    files: tuple[ReleaseFile, ...]
    schema_version: str = RELEASE_SCHEMA
    compatibility_epoch: str = "kolibri-os-v1"
    metadata: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "release_id": self.release_id,
            "source_commit": self.source_commit,
            "artifact_uri": self.artifact_uri,
            "compatibility_epoch": self.compatibility_epoch,
            "files": [
                {
                    "path": item.path,
                    "sha256": item.sha256,
                    "size_bytes": item.size_bytes,
                    "mode": item.mode,
                }
                for item in sorted(self.files, key=lambda item: item.path)
            ],
            "metadata": self.metadata,
        }

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @property
    def digest(self) -> str:
        return f"sha256:{hashlib.sha256(self.canonical_bytes()).hexdigest()}"

    def validate(self) -> None:
        if self.schema_version != RELEASE_SCHEMA:
            raise ReleaseError(f"unsupported release schema: {self.schema_version}")
        if not self.release_id.strip():
            raise ReleaseError("release_id is required")
        if len(self.source_commit) < 7 or any(char not in "0123456789abcdef" for char in self.source_commit.lower()):
            raise ReleaseError("source_commit must be a hexadecimal git object id")
        if not self.artifact_uri.startswith("artifact://"):
            raise ReleaseError("artifact_uri must use worker-local artifact addressing")
        parsed_uri = urllib.parse.urlsplit(self.artifact_uri)
        if (
            parsed_uri.scheme != "artifact"
            or parsed_uri.username
            or parsed_uri.password
            or parsed_uri.query
            or parsed_uri.fragment
        ):
            raise ReleaseError("artifact_uri must use strict worker-local artifact addressing")
        if not self.files:
            raise ReleaseError("release manifest is empty")
        paths: set[str] = set()
        for item in self.files:
            item.validate()
            if item.path in paths:
                raise ReleaseError(f"duplicate release path: {item.path}")
            paths.add(item.path)
        metadata_keys = {_normalized_key(key) for key in _walk_keys(self.metadata)}
        if metadata_keys & SECRET_METADATA_KEYS:
            raise ReleaseError("release metadata must not contain secret-bearing fields")

    @classmethod
    def from_payload(cls, value: dict[str, Any]) -> "ReleaseManifest":
        return cls(
            schema_version=str(value.get("schema_version") or ""),
            release_id=str(value.get("release_id") or ""),
            source_commit=str(value.get("source_commit") or ""),
            artifact_uri=str(value.get("artifact_uri") or ""),
            compatibility_epoch=str(value.get("compatibility_epoch") or ""),
            files=tuple(ReleaseFile(**item) for item in value.get("files") or []),
            metadata=dict(value.get("metadata") or {}),
        )


@dataclass(frozen=True)
class VerifiedRelease:
    manifest: ReleaseManifest
    signer_identity: str
    namespace: str = SIGNATURE_NAMESPACE


def _normalized_key(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_")


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_keys(child)


def verify_ssh_signature(
    manifest: ReleaseManifest,
    signature_path: Path,
    allowed_signers_path: Path,
    signer_identity: str,
) -> VerifiedRelease:
    """Verify a detached OpenSSH signature without accessing a private key."""
    manifest.validate()
    if not signer_identity.strip():
        raise ReleaseError("signer identity is required")
    if not signature_path.is_file() or not allowed_signers_path.is_file():
        raise ReleaseError("signature or allowed-signers file is missing")
    try:
        completed = subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "verify",
                "-f",
                str(allowed_signers_path),
                "-I",
                signer_identity,
                "-n",
                SIGNATURE_NAMESPACE,
                "-s",
                str(signature_path),
            ],
            input=manifest.canonical_bytes(),
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseError("release signature verification unavailable") from exc
    if completed.returncode != 0:
        raise ReleaseError("release signature verification failed")
    return VerifiedRelease(manifest=manifest, signer_identity=signer_identity)


@dataclass(frozen=True)
class FleetNode:
    node_id: str
    physical_node_id: str
    freshness: str
    health: str
    draining: bool
    capabilities: tuple[str, ...]
    agent_live: bool
    rollout_stage: str | None = None

    @property
    def schedulable(self) -> bool:
        return (
            self.freshness == "fresh"
            and self.health == "online"
            and not self.draining
            and self.agent_live
            and RELEASE_CAPABILITY in self.capabilities
        )


@dataclass(frozen=True)
class RolloutWave:
    name: str
    nodes: tuple[FleetNode, ...]


def node_from_api(value: dict[str, Any]) -> FleetNode:
    node_id = str(value.get("node_id") or "").strip()
    if not node_id:
        raise ReleaseError("fleet node has no node_id")
    labels = value.get("labels") if isinstance(value.get("labels"), dict) else {}
    physical_node_id = str(
        value.get("physical_node_id")
        or labels.get("physical_node_id")
        or value.get("canonical_node_id")
        or node_id
    )
    return FleetNode(
        node_id=node_id,
        physical_node_id=physical_node_id,
        freshness=str(value.get("freshness") or "stale"),
        health=str(value.get("health") or "unknown"),
        draining=bool(value.get("draining")),
        capabilities=tuple(sorted(str(item) for item in value.get("capabilities") or [])),
        agent_live=bool(value.get("agent_id") and value.get("pid")),
        rollout_stage=str(labels.get("rollout_stage")) if labels.get("rollout_stage") else None,
    )


def canonical_fleet(values: Iterable[dict[str, Any]]) -> list[FleetNode]:
    """Collapse duplicate cards by physical identity, preferring live agents."""
    selected: dict[str, FleetNode] = {}
    for value in values:
        node = node_from_api(value)
        current = selected.get(node.physical_node_id)
        if current is None:
            selected[node.physical_node_id] = node
            continue
        rank = (
            int(node.schedulable),
            int(node.agent_live),
            int(not node.node_id.startswith("mesh-")),
            node.node_id,
        )
        current_rank = (
            int(current.schedulable),
            int(current.agent_live),
            int(not current.node_id.startswith("mesh-")),
            current.node_id,
        )
        if rank > current_rank:
            selected[node.physical_node_id] = node
    return sorted(selected.values(), key=lambda item: item.node_id)


def rollout_stage(node: FleetNode) -> str:
    stage = str(node.rollout_stage or "").strip().lower()
    if stage not in {"canary", "quorum", "standard", "last"}:
        raise ReleaseError(f"node {node.node_id} has no valid runtime rollout_stage label")
    return stage


def plan_progressive_rollout(nodes: Iterable[FleetNode], expected_nodes: int | None = None) -> list[RolloutWave]:
    fleet = list(nodes)
    if expected_nodes is not None and len(fleet) != expected_nodes:
        raise ReleaseError(f"canonical fleet size is {len(fleet)}, expected {expected_nodes}")
    unschedulable = [node.node_id for node in fleet if not node.schedulable]
    if unschedulable:
        raise ReleaseError(f"release blocked by non-fresh nodes: {', '.join(sorted(unschedulable))}")
    grouped = {stage: [] for stage in ("canary", "quorum", "standard", "last")}
    for node in fleet:
        grouped.setdefault(rollout_stage(node), []).append(node)
    for values in grouped.values():
        values.sort(key=lambda item: item.node_id)

    for required_stage in ("canary", "quorum", "last"):
        if not grouped[required_stage]:
            raise ReleaseError(f"release plan has no {required_stage} stage")
    if len(grouped["last"]) != 1:
        raise ReleaseError("release plan requires exactly one runtime-labelled last node")

    standard = grouped["standard"]
    waves = [
        RolloutWave("canary", tuple(grouped["canary"])),
        RolloutWave("quorum", tuple(grouped["quorum"])),
        RolloutWave("workers-3", tuple(standard[:3])),
        RolloutWave("workers-5", tuple(standard[3:8])),
        RolloutWave("workers-rest", tuple(standard[8:])),
        RolloutWave("home-control-plane-last", tuple(grouped["last"])),
    ]
    planned_ids = [node.physical_node_id for wave in waves for node in wave.nodes]
    if len(planned_ids) != len(set(planned_ids)) or len(planned_ids) != len(fleet):
        raise ReleaseError("rollout plan did not assign every physical node exactly once")
    return [wave for wave in waves if wave.nodes]


def plan_home_canary(
    nodes: Iterable[FleetNode],
    expected_nodes: int | None = None,
) -> list[RolloutWave]:
    """Select exactly the canonical Home worker for a release canary.

    This is deliberately a separate scope from the progressive fleet plan.
    ``expected_nodes`` still checks the complete canonical membership, while
    only Home must currently advertise the release capability.  That lets the
    owner prove the immutable backend release on the authority host before any
    other worker is submitted a mutation task.
    """

    fleet = list(nodes)
    if expected_nodes is not None and len(fleet) != expected_nodes:
        raise ReleaseError(f"canonical fleet size is {len(fleet)}, expected {expected_nodes}")
    home = [
        node
        for node in fleet
        if node.node_id.strip().lower() == "home"
        or node.physical_node_id.strip().lower() == "home"
    ]
    if len(home) != 1:
        raise ReleaseError("Home-only canary requires exactly one canonical Home node")
    target = home[0]
    if not target.schedulable:
        raise ReleaseError("Home-only canary blocked by non-fresh Home release worker")
    return [RolloutWave("home-canary", (target,))]


def rollout_wave_for_node(
    rollout_plan: Iterable[dict[str, Any]],
    node_id: str,
) -> str:
    canonical = canonical_rollout_plan(list(rollout_plan))
    matches = [wave["name"] for wave in canonical if node_id in wave["nodes"]]
    if len(matches) != 1:
        raise ReleaseError("release node is not uniquely bound to the rollout plan")
    return matches[0]


class ControlPlaneClient:
    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._approved_releases: dict[tuple[str, str], dict[str, Any]] = {}

    @classmethod
    def from_environment(
        cls,
        timeout: float = 10.0,
        control_url: str | None = None,
        control_urls: str | None = None,
    ) -> "ControlPlaneClient":
        """Bind releases to the one canonical Home Control Plane endpoint."""
        try:
            base_url = resolve_home_control_plane_url(control_url, control_urls)
        except ControlPlaneEndpointError as exc:
            raise ReleaseError(f"canonical Home Control Plane unresolved: {exc}") from exc
        return cls(base_url, timeout=timeout)

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ReleaseError(f"Control Plane request failed: {path}") from exc
        try:
            return json.loads(raw) if raw else None
        except json.JSONDecodeError as exc:
            raise ReleaseError(f"Control Plane returned invalid JSON: {path}") from exc

    def fleet(self) -> list[FleetNode]:
        payload = self.request("GET", "/v1/nodes?scope=active&limit=250")
        if not isinstance(payload, dict):
            raise ReleaseError("Control Plane returned an invalid fleet payload")
        return canonical_fleet(payload.get("nodes") or [])

    def require_owner_approval(
        self,
        approval_id: str,
        release: str | VerifiedRelease,
        *,
        rollback_release: VerifiedRelease | None = None,
        rollout_plan: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not approval_id.strip():
            raise ReleaseError("owner approval id is required")
        release_id = release.manifest.release_id if isinstance(release, VerifiedRelease) else str(release)
        cache_key = (approval_id, release_id)
        approval = self._approved_releases.get(cache_key)
        if approval is None:
            quoted = urllib.parse.quote(approval_id, safe="")
            approval = self.request("GET", f"/v1/approvals/{quoted}") or {}
        decision = str(approval.get("decision") or approval.get("status") or "").lower()
        approved_by = approval.get("approved_by") if isinstance(approval.get("approved_by"), dict) else {}
        role = str(approved_by.get("role") or approval.get("approved_by_role") or "").lower()
        approved_release = str(approval.get("release_id") or "")
        if decision != "approved" or role not in {"owner", "owner_root"} or approved_release != release_id:
            raise ReleaseError("release is not covered by an approved owner decision")
        try:
            attestation = canonical_owner_approval_attestation(approval.get("attestation"))
        except ReleaseAuthorityError as exc:
            raise ReleaseError("release approval attestation is invalid or expired") from exc
        if approval.get("attestation_digest") != approval_attestation_digest(attestation):
            raise ReleaseError("release approval attestation digest mismatch")
        payload = attestation["payload"]
        if isinstance(release, VerifiedRelease) and (
            payload["manifest_digest"] != release.manifest.digest
            or payload["release_signature_namespace"] != release.namespace
            or payload["release_signer_identity"] != release.signer_identity
        ):
            raise ReleaseError("release approval does not bind the signed release")
        if rollout_plan is not None and payload["rollout_plan"] != canonical_rollout_plan(rollout_plan):
            raise ReleaseError("release approval does not bind the rollout plan")
        if rollback_release is not None:
            rollback = payload.get("rollback")
            if payload.get("allow_rollback") is not True or not isinstance(rollback, dict):
                raise ReleaseError("release approval does not authorize rollback")
            if (
                rollback["release_id"] != rollback_release.manifest.release_id
                or rollback["manifest_digest"] != rollback_release.manifest.digest
                or rollback["signature_namespace"] != rollback_release.namespace
                or rollback["signer_identity"] != rollback_release.signer_identity
            ):
                raise ReleaseError("release approval does not bind the rollback release")
        self._approved_releases[cache_key] = approval
        return approval

    def submit_release_task(
        self,
        verified: VerifiedRelease,
        node: FleetNode,
        wave: str,
        approval_id: str,
        rollout_plan: list[dict[str, Any]],
    ) -> dict[str, Any]:
        manifest = verified.manifest
        self.require_owner_approval(approval_id, verified, rollout_plan=rollout_plan)
        return self.request("POST", "/v1/tasks", {
            "schema_version": RELEASE_SCHEMA,
            "idempotency_key": f"release:{manifest.digest}:{node.physical_node_id}",
            "kind": RELEASE_TASK_KIND,
            "required_capability": RELEASE_CAPABILITY,
            "target_node": node.node_id,
            "release_id": manifest.release_id,
            "manifest_digest": manifest.digest,
            "artifact_uri": manifest.artifact_uri,
            "source_commit": manifest.source_commit,
            "rollout_wave": wave,
            "approval_id": approval_id,
            "signature": {
                "format": "sshsig",
                "namespace": verified.namespace,
                "signer_identity": verified.signer_identity,
            },
            "max_retries": 1,
        })

    def submit_rollback_task(
        self,
        failed_release: VerifiedRelease,
        rollback_release: VerifiedRelease,
        node: FleetNode,
        approval_id: str,
        reason: str,
        rollout_plan: list[dict[str, Any]],
    ) -> dict[str, Any]:
        approval = self.require_owner_approval(
            approval_id,
            failed_release,
            rollback_release=rollback_release,
            rollout_plan=rollout_plan,
        )
        if approval.get("allow_rollback") is not True:
            raise ReleaseError("owner approval does not authorize rollback")
        target = rollback_release.manifest
        rollout_wave = rollout_wave_for_node(rollout_plan, node.node_id)
        return self.request("POST", "/v1/tasks", {
            "schema_version": RELEASE_SCHEMA,
            "idempotency_key": f"rollback:{failed_release.manifest.digest}:{target.digest}:{node.physical_node_id}",
            "kind": ROLLBACK_TASK_KIND,
            "required_capability": RELEASE_CAPABILITY,
            "target_node": node.node_id,
            "failed_release_id": failed_release.manifest.release_id,
            "rollback_to_release_id": target.release_id,
            "manifest_digest": target.digest,
            "artifact_uri": target.artifact_uri,
            "source_commit": target.source_commit,
            "approval_id": approval_id,
            "rollback_reason": reason[:500],
            "rollout_wave": rollout_wave,
            "signature": {
                "format": "sshsig",
                "namespace": rollback_release.namespace,
                "signer_identity": rollback_release.signer_identity,
            },
            "max_retries": 1,
        })

    def wait_for_task(self, task_id: str, timeout: float = 600.0, poll_interval: float = 2.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        quoted = urllib.parse.quote(task_id, safe="")
        while time.monotonic() < deadline:
            task = self.request("GET", f"/v1/tasks/{quoted}") or {}
            if task.get("state") in TERMINAL_TASK_STATES:
                return task
            time.sleep(poll_interval)
        raise ReleaseError(f"release task timed out: {task_id}")

    def cancel_task(self, task_id: str, reason: str) -> dict[str, Any]:
        quoted = urllib.parse.quote(task_id, safe="")
        result = self.request(
            "POST",
            f"/v1/tasks/{quoted}/cancel",
            {"reason": reason[:500], "requested_by": "release_controller"},
        ) or {}
        if not isinstance(result, dict):
            raise ReleaseError(f"release task cancellation returned invalid data: {task_id}")
        return result

    def wait_for_cancel_fence(
        self,
        task_id: str,
        timeout: float = 120.0,
        poll_interval: float = 0.5,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        quoted = urllib.parse.quote(task_id, safe="")
        while time.monotonic() < deadline:
            task = self.request("GET", f"/v1/tasks/{quoted}") or {}
            state = task.get("state")
            if state in TERMINAL_TASK_STATES:
                if state != "cancelled" or task.get("cancel_was_active") is not True:
                    return task
                if task.get("cancel_acknowledged_at"):
                    return task
            time.sleep(poll_interval)
        raise ReleaseError(f"release task cancellation fence timed out: {task_id}")

    def cancel_and_fence_release_tasks(self, task_ids: Iterable[str], reason: str) -> list[str]:
        cancelled: list[str] = []
        for task_id in dict.fromkeys(task_ids):
            quoted = urllib.parse.quote(task_id, safe="")
            task = self.request("GET", f"/v1/tasks/{quoted}") or {}
            if task.get("state") not in TERMINAL_TASK_STATES:
                self.cancel_task(task_id, reason)
                cancelled.append(task_id)
        for task_id in cancelled:
            self.wait_for_cancel_fence(task_id)
        return cancelled

    def require_release_health(self, verified: VerifiedRelease, node: FleetNode) -> dict[str, Any]:
        release_id = urllib.parse.quote(verified.manifest.release_id, safe="")
        node_id = urllib.parse.quote(node.node_id, safe="")
        health = self.request("GET", f"/v1/releases/{release_id}/nodes/{node_id}/health") or {}
        if health.get("status") != "healthy" or health.get("manifest_digest") != verified.manifest.digest:
            raise ReleaseError(f"release health gate failed on {node.node_id}")
        return health


def execute_progressive_release(
    client: ControlPlaneClient,
    verified: VerifiedRelease,
    rollback_release: VerifiedRelease,
    waves: Iterable[RolloutWave],
    approval_id: str,
) -> dict[str, Any]:
    """Run API-only waves and rollback every attempted node on the first failure."""
    waves = tuple(waves)
    rollout_plan = canonical_rollout_plan(
        [{"name": wave.name, "nodes": [node.node_id for node in wave.nodes]} for wave in waves]
    )
    client.require_owner_approval(
        approval_id,
        verified,
        rollback_release=rollback_release,
        rollout_plan=rollout_plan,
    )
    attempted: list[FleetNode] = []
    completed: list[FleetNode] = []
    apply_task_ids: list[str] = []
    wave_results: list[dict[str, Any]] = []
    try:
        for wave in waves:
            submitted: list[tuple[FleetNode, str]] = []
            for node in wave.nodes:
                task = client.submit_release_task(
                    verified,
                    node,
                    wave.name,
                    approval_id,
                    rollout_plan,
                )
                task_id = str(task.get("task_id") or "")
                if not task_id:
                    raise ReleaseError(f"release task submission returned no task_id for {node.node_id}")
                attempted.append(node)
                apply_task_ids.append(task_id)
                submitted.append((node, task_id))
            for node, task_id in submitted:
                result = client.wait_for_task(task_id)
                if result.get("state") != "completed":
                    raise ReleaseError(f"release task failed on {node.node_id}")
                client.require_release_health(verified, node)
                completed.append(node)
            wave_results.append({"wave": wave.name, "status": "completed", "nodes": [node.node_id for node, _ in submitted]})
        return {
            "schema_version": RELEASE_SCHEMA,
            "status": "completed",
            "release_id": verified.manifest.release_id,
            "waves": wave_results,
            "rollback": {"status": "not_required", "nodes": []},
        }
    except Exception as exc:
        try:
            cancelled_tasks = client.cancel_and_fence_release_tasks(apply_task_ids, str(exc))
        except Exception as cancel_exc:
            return {
                "schema_version": RELEASE_SCHEMA,
                "status": "rollback_blocked",
                "release_id": verified.manifest.release_id,
                "failed_reason": str(exc)[:500],
                "cancel_fence_error": str(cancel_exc)[:500],
                "rollback": {"status": "blocked", "nodes": []},
            }
        rollback_results = []
        rollback_failed = False
        for node in reversed(attempted):
            try:
                task = client.submit_rollback_task(
                    verified,
                    rollback_release,
                    node,
                    approval_id,
                    str(exc),
                    rollout_plan,
                )
                task_id = str(task.get("task_id") or "")
                if not task_id:
                    raise ReleaseError(f"rollback submission returned no task_id for {node.node_id}")
                result = client.wait_for_task(task_id)
                if result.get("state") != "completed":
                    raise ReleaseError(f"rollback task failed on {node.node_id}")
                client.require_release_health(rollback_release, node)
                rollback_results.append({"node": node.node_id, "status": "completed"})
            except Exception as rollback_exc:
                rollback_failed = True
                rollback_results.append({"node": node.node_id, "status": "failed", "reason": str(rollback_exc)[:500]})
        return {
            "schema_version": RELEASE_SCHEMA,
            "status": "rollback_failed" if rollback_failed else "rolled_back",
            "release_id": verified.manifest.release_id,
            "failed_reason": str(exc)[:500],
            "completed_before_failure": [node.node_id for node in completed],
            "cancelled_apply_tasks": cancelled_tasks,
            "rollback": {"status": "failed" if rollback_failed else "completed", "nodes": rollback_results},
        }


def release_plan_payload(manifest: ReleaseManifest, waves: Iterable[RolloutWave]) -> dict[str, Any]:
    return {
        "schema_version": RELEASE_SCHEMA,
        "release_id": manifest.release_id,
        "manifest_digest": manifest.digest,
        "transport": "control-plane-api-only",
        "waves": [
            {"name": wave.name, "nodes": [node.node_id for node in wave.nodes]}
            for wave in waves
        ],
    }


def load_release_manifest(path: str | Path) -> ReleaseManifest:
    candidate = Path(path)
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReleaseError(f"release manifest is missing: {candidate}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"release manifest is invalid: {candidate}") from exc
    if not isinstance(payload, dict):
        raise ReleaseError("release manifest root must be an object")
    try:
        manifest = ReleaseManifest.from_payload(payload)
    except (TypeError, ValueError) as exc:
        raise ReleaseError("release manifest schema is invalid") from exc
    manifest.validate()
    return manifest


def _add_control_plane_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--control-url", help="explicit canonical Home runtime URL")
    parser.add_argument("--timeout", type=float, default=10.0, help="Control Plane request timeout")


def _add_rollout_scope_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--home-only",
        action="store_true",
        help="plan or apply only the canonical Home canary while checking full membership",
    )


def _selected_rollout_plan(
    client: ControlPlaneClient,
    *,
    expected_nodes: int | None,
    home_only: bool,
) -> list[RolloutWave]:
    fleet = client.fleet()
    if home_only:
        return plan_home_canary(fleet, expected_nodes=expected_nodes)
    return plan_progressive_rollout(fleet, expected_nodes=expected_nodes)


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate a release manifest without mutation")
    validate.add_argument("--manifest", required=True)

    plan = commands.add_parser("plan", help="build a read-only progressive fleet plan")
    plan.add_argument("--manifest", required=True)
    plan.add_argument("--expected-nodes", type=int)
    _add_rollout_scope_arguments(plan)
    _add_control_plane_arguments(plan)

    apply = commands.add_parser("apply", help="submit an owner-approved API-only progressive release")
    apply.add_argument("--manifest", required=True)
    apply.add_argument("--signature", required=True)
    apply.add_argument("--rollback-manifest", required=True)
    apply.add_argument("--rollback-signature", required=True)
    apply.add_argument("--allowed-signers", required=True)
    apply.add_argument("--signer-identity", required=True)
    apply.add_argument("--rollback-signer-identity")
    apply.add_argument("--approval-id", required=True)
    apply.add_argument("--expected-nodes", type=int)
    _add_rollout_scope_arguments(apply)
    _add_control_plane_arguments(apply)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_cli_parser().parse_args(argv)
    try:
        manifest = load_release_manifest(args.manifest)
        if args.command == "validate":
            print(json.dumps({
                "schema_version": manifest.schema_version,
                "status": "valid",
                "release_id": manifest.release_id,
                "manifest_digest": manifest.digest,
            }, indent=2, sort_keys=True))
            return 0

        if args.command == "plan":
            client = ControlPlaneClient.from_environment(timeout=args.timeout, control_url=args.control_url)
            waves = _selected_rollout_plan(
                client,
                expected_nodes=args.expected_nodes,
                home_only=args.home_only,
            )
            print(json.dumps(release_plan_payload(manifest, waves), indent=2, sort_keys=True))
            return 0

        verified = verify_ssh_signature(
            manifest,
            Path(args.signature),
            Path(args.allowed_signers),
            args.signer_identity,
        )
        rollback_manifest = load_release_manifest(args.rollback_manifest)
        rollback_verified = verify_ssh_signature(
            rollback_manifest,
            Path(args.rollback_signature),
            Path(args.allowed_signers),
            args.rollback_signer_identity or args.signer_identity,
        )
        client = ControlPlaneClient.from_environment(timeout=args.timeout, control_url=args.control_url)
        waves = _selected_rollout_plan(
            client,
            expected_nodes=args.expected_nodes,
            home_only=args.home_only,
        )
        result = execute_progressive_release(
            client,
            verified,
            rollback_verified,
            waves,
            args.approval_id,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("status") == "completed" else 1
    except ReleaseError as exc:
        print(json.dumps({
            "status": "blocked",
            "reason": "release_controller_error",
            "detail": str(exc),
        }, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
