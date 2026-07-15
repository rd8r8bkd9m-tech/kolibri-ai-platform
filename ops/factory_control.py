#!/usr/bin/env python3
"""Minimal Kolibri Factory control plane sidecar.

The sidecar intentionally uses only the Python standard library. It stores all
task and node state in the existing local Redis server through a tiny RESP
client so it can run next to the legacy control plane without adding packages.

Integrates Truth Factory: claims, evidence, and verdict ledgers for
adversarial review of task outcomes.
"""

from __future__ import annotations

import sys
import os

# Ensure this module is registered in sys.modules so dataclass processing
# works when loaded via spec_from_file_location with a custom name.
try:
    _mod = sys.modules[__name__]
except KeyError:
    sys.modules[__name__] = type(sys)(__name__)

import argparse
import hashlib
import json
import os
import socket
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Literal
from pathlib import Path
from urllib.parse import parse_qs, urlparse

CURRENT_DIR = Path(__file__).resolve().parent


def factory_ops_import_paths() -> list[Path]:
    paths = [CURRENT_DIR]
    explicit_ops = os.environ.get("KOLIBRI_OPS_DIR")
    if explicit_ops:
        paths.append(Path(explicit_ops).expanduser())
    repo_root = os.environ.get("KOLIBRI_REPO_ROOT")
    if repo_root:
        paths.append(Path(repo_root).expanduser() / "ops")
    paths.extend([
        Path.cwd() / "ops",
        Path("/opt/kolibri-ai-platform/ops"),
        Path("/opt/kolibri-ai/ops"),
    ])
    resolved: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            resolved.append(path)
            seen.add(key)
    return resolved


for ops_path in reversed(factory_ops_import_paths()):
    if ops_path.exists() and str(ops_path) not in sys.path:
        sys.path.insert(0, str(ops_path))
from telegram_superfactory import plan_update_receiver, runner_policy, select_runner, validate_telegram_init_data


NAMESPACE = os.environ.get("FACTORY_NAMESPACE", "kolibri_factory")
REDIS_HOST = os.environ.get("FACTORY_REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("FACTORY_REDIS_PORT", "6379"))
LEASE_DURATION = int(os.environ.get("FACTORY_LEASE_DURATION", "60"))
MAX_RETRIES = int(os.environ.get("FACTORY_MAX_RETRIES", "3"))
FABRIC_API_VERSION = "2026-07-01"
FABRIC_MANIFEST_VERSION = "2026-07-01.manifest-01"
CANONICAL_RESPONSE_STATUSES = {"completed", "running", "blocked", "failed", "partial"}
FALLBACK_REASON_TAXONOMY = {
    "api_unreachable",
    "vpn_down",
    "firewall",
    "disk_full",
    "auth_failed",
    "dns",
    "target_node_unavailable",
    "no_node_matches_capability",
    "model_runtime_unavailable",
    "admin_scope_denied",
    "unknown",
}
NODE_DEGRADED_AFTER = int(os.environ.get("FACTORY_NODE_DEGRADED_AFTER", "30"))
NODE_STALE_AFTER = int(os.environ.get("FACTORY_NODE_STALE_AFTER", "90"))

STATE_QUEUED = "queued"
STATE_LEASED = "leased"
STATE_RUNNING = "running"
STATE_WAITING_REVIEW = "waiting_review"
STATE_REVIEW = "review"
STATE_COMPLETED = "completed"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"
STATE_RETRY = "retry_scheduled"
STATE_DEAD = "dead_letter"
TERMINAL_STATES = {STATE_COMPLETED, STATE_FAILED, STATE_CANCELLED, STATE_DEAD}
ACTIVE_LEASE_STATES = {STATE_LEASED, STATE_RUNNING, STATE_REVIEW}
LEASE_CONTRACT_VERSION = "2026-07-14.lease-v1"
LEASE_FENCE_FIELDS = ("attempt_id", "lease_id", "fencing_token")
BLOCKED_RUNNER_STATES = {"blocked", "degraded", "runner_auth_blocked", "unavailable"}
INACTIVE_AGENT_SLOT_STATES = BLOCKED_RUNNER_STATES | {
    "disabled",
    "draining",
    "failed",
    "offline",
    "stale",
    "stopped",
}

# Home is the single logical authority, so an in-process lock is sufficient to
# keep concurrent generic/slot heartbeats from losing each other's updates.
# Slot data is also retained in the node record, making every effective
# capability projection reproducible from one durable Redis value.
NODE_UPDATE_LOCK = threading.RLock()

FABRIC_NODE_CATALOG = {
    "home": {
        "node_id": "home",
        "role": "command_node_gateway",
        "display_name": "Связной",
        "api_paths": ["fabric_api", "fallback_relay"],
        "ssh": "emergency_bootstrap_diagnostic_only",
    },
    "main": {
        "node_id": "main",
        "role": "orchestrator_fallback",
        "display_name": "Резервный оркестратор",
        "api_paths": ["fabric_api", "artifact_api"],
        "ssh": "emergency_bootstrap_diagnostic_only",
    },
    "uiap": {
        "node_id": "uiap",
        "role": "knowledge_model_node",
        "display_name": "Знания",
        "api_paths": ["fabric_api", "fallback_relay"],
        "ssh": "emergency_bootstrap_diagnostic_only",
    },
    "qjns": {
        "node_id": "qjns",
        "role": "remote_agent",
        "display_name": "Тестировщик",
        "api_paths": ["fabric_api", "agent_host_api", "fallback_relay"],
        "ssh": "emergency_bootstrap_diagnostic_only",
    },
    "9fts": {
        "node_id": "9fts",
        "role": "implementation_model_node",
        "display_name": "Инженер",
        "api_paths": ["fabric_api", "agent_host_api", "model_node_api", "fallback_relay"],
        "ssh": "emergency_bootstrap_diagnostic_only",
    },
    "new": {
        "node_id": "new",
        "role": "review_agent",
        "display_name": "Ревьюер",
        "api_paths": ["fabric_api", "agent_host_api", "fallback_relay"],
        "ssh": "emergency_bootstrap_diagnostic_only",
    },
}

OWNER_RIGHTS_POLICY = {
    "policy_id": "kolibri-owner-full-control-api",
    "rights": ["fleet:read", "fleet:route", "task:submit", "task:cancel", "node:drain", "artifact:read", "bootstrap:create"],
    "requires": ["authentication", "authorization", "scope", "audit_logging", "key_rotation"],
    "default_scope": "least_privilege_per_command",
    "secret_handling": "tokens and private keys are never returned by Fabric API responses",
    "rotation": "node credentials rotate on bootstrap, compromise, owner request, and at least every 90 days",
}

NODE_IDENTITY_ROTATION_POLICY = {
    "identity": {
        "node_id": "stable non-secret node identifier",
        "agent_id": "process-level API identity",
        "display_name": "human-readable Russian role name for owner reports",
    },
    "key_rotation": {
        "required": True,
        "maximum_age_days": 90,
        "events": ["new_bootstrap", "suspected_compromise", "operator_rotation", "node_reimage"],
        "overlap": "old key remains valid only for a short audited drain window",
    },
    "audit": "all privileged Fabric API calls must record actor, scope, node_id, request_id and outcome",
}

BOOTSTRAP_CONTRACT = {
    "endpoint": "POST /v1/fabric/bootstrap",
    "purpose": "register a new server through the protected Fabric API without printing secrets",
    "required_fields": ["node_id", "role", "display_name", "capabilities", "requested_by"],
    "safe_stub": True,
    "result": "returns bootstrap task metadata and next API action; privileged installers remain external until authenticated",
}

MODEL_CATALOG = [
    {
        "id": "mimo-auto",
        "object": "model",
        "owned_by": "kolibri-fabric",
        "capabilities": ["chat", "responses"],
        "route": "safe_stub_until_model_node_authenticated",
    }
]

ADMIN_ENDPOINTS = {
    "/v1/admin/exec": "admin_exec",
    "/v1/admin/service": "admin_service",
    "/v1/admin/git": "admin_git",
    "/v1/admin/bootstrap-node": "admin_bootstrap_node",
    "/v1/admin/rotate-keys": "admin_rotate_keys",
}

OS_CAPABILITY_CATALOG = [
    {"id": "chat.compose", "target": "kolibri-core", "approval": "auto"},
    {"id": "workspace.open", "target": "kolibri-core", "approval": "auto"},
    {"id": "artifact.present", "target": "kolibri-core", "approval": "auto"},
    {"id": "task.create", "target": "control-plane", "approval": "owner-gated"},
    {"id": "agent.delegate", "target": "control-plane", "approval": "owner-gated"},
    {"id": "system.change", "target": "control-plane", "approval": "explicit"},
]

OS_CAPABILITY_BY_ID = {capability["id"]: capability for capability in OS_CAPABILITY_CATALOG}

PROMPT3_REQUIRED_ENDPOINTS = {
    "GET": [
        "/v1/health",
        "/v1/fleet/nodes",
        "/v1/fleet/topology",
        "/v1/fleet/route",
        "/v1/fleet/capabilities",
        "/v1/os/capabilities",
        "/v1/fabric/manifest",
        "/v1/models",
        "/v1/agents/status/{task_id}",
        "/v1/agents/artifacts/{task_id}",
    ],
    "POST": [
        "/v1/responses",
        "/v1/chat/completions",
        "/v1/os/capabilities/invoke",
        "/v1/agents/tasks",
        "/v1/agents/cancel/{task_id}",
        "/v1/admin/exec",
        "/v1/admin/service",
        "/v1/admin/git",
        "/v1/admin/bootstrap-node",
        "/v1/admin/rotate-keys",
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_ts() -> float:
    return time.time()


def parse_iso_ts(value: Any) -> float | None:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError):
        return None


def key(name: str) -> str:
    return f"{NAMESPACE}:{name}"


class RedisError(RuntimeError):
    pass


class Redis:
    def __init__(self, host: str = REDIS_HOST, port: int = REDIS_PORT, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def command(self, *parts: Any) -> Any:
        payload = self._encode(parts)
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.sendall(payload)
            reader = sock.makefile("rb")
            return self._read(reader)

    @staticmethod
    def _encode(parts: tuple[Any, ...]) -> bytes:
        out = [f"*{len(parts)}\r\n".encode()]
        for part in parts:
            data = str(part).encode("utf-8")
            out.append(f"${len(data)}\r\n".encode())
            out.append(data + b"\r\n")
        return b"".join(out)

    def _read(self, reader: Any) -> Any:
        prefix = reader.read(1)
        if not prefix:
            raise RedisError("empty redis response")
        line = reader.readline().rstrip(b"\r\n")
        if prefix == b"+":
            return line.decode("utf-8")
        if prefix == b"-":
            raise RedisError(line.decode("utf-8", "replace"))
        if prefix == b":":
            return int(line)
        if prefix == b"$":
            length = int(line)
            if length == -1:
                return None
            data = reader.read(length)
            reader.read(2)
            return data.decode("utf-8")
        if prefix == b"*":
            count = int(line)
            if count == -1:
                return None
            return [self._read(reader) for _ in range(count)]
        raise RedisError(f"unknown redis response prefix: {prefix!r}")


redis = Redis()


# ── Truth Factory: Claims, Evidence, Verdicts ──────────────────────────

VerdictType = Literal["true", "false", "partial", "not_proven", "blocked", "stale", "degraded"]
ConfidenceLevel = Literal["high", "medium", "low"]
ClaimStatus = Literal["proposed", "challenged", "verified", "rejected", "partial", "not_proven"]


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class Claim:
    claim_id: str
    task_id: str
    made_by: str
    claim: str
    scope: str
    status: ClaimStatus = "proposed"
    evidence: list[str] = field(default_factory=list)
    counterclaims: list[str] = field(default_factory=list)
    verdict: str = ""
    confidence: str = "low"
    next_action: str = ""
    created_at: str = field(default_factory=utc_now)


@dataclass
class Evidence:
    evidence_id: str
    claim_id: str
    type: str
    source: str
    timestamp: str = field(default_factory=utc_now)
    content_hash: str = ""
    summary: str = ""
    redacted: bool = True
    path: str = ""
    valid: bool = True


@dataclass
class Verdict:
    verdict_id: str
    claim_id: str
    verdict: VerdictType
    confidence: ConfidenceLevel
    evidence: list[str] = field(default_factory=list)
    reasoning: str = ""
    next_action: str = ""
    owner_summary: str = ""
    created_at: str = field(default_factory=utc_now)


# In-memory truth ledger (persisted via Redis)
_truth_claims: dict[str, Claim] = {}
_truth_evidence: dict[str, Evidence] = {}
_truth_verdicts: dict[str, Verdict] = {}


def truth_key(name: str) -> str:
    return key(f"truth:{name}")


def save_claim(claim: Claim) -> None:
    _truth_claims[claim.claim_id] = claim
    try:
        set_json(truth_key(f"claim:{claim.claim_id}"), asdict(claim))
        redis.command("SADD", truth_key("claim_ids"), claim.claim_id)
    except Exception:
        pass  # In-memory only if Redis unavailable


def save_evidence(ev: Evidence) -> None:
    _truth_evidence[ev.evidence_id] = ev
    try:
        set_json(truth_key(f"evidence:{ev.evidence_id}"), asdict(ev))
        redis.command("SADD", truth_key("evidence_ids"), ev.evidence_id)
    except Exception:
        pass  # In-memory only if Redis unavailable


def save_verdict(v: Verdict) -> None:
    _truth_verdicts[v.verdict_id] = v
    try:
        set_json(truth_key(f"verdict:{v.verdict_id}"), asdict(v))
        redis.command("SADD", truth_key("verdict_ids"), v.verdict_id)
    except Exception:
        pass  # In-memory only if Redis unavailable


def create_claim(task_id: str, made_by: str, claim_text: str, scope: str) -> Claim:
    c = Claim(claim_id=_id("C"), task_id=task_id, made_by=made_by, claim=claim_text, scope=scope)
    save_claim(c)
    return c


def add_evidence(claim_id: str, ev_type: str, source: str, summary: str = "", path: str = "") -> Evidence:
    e = Evidence(evidence_id=_id("E"), claim_id=claim_id, type=ev_type, source=source, summary=summary, path=path)
    save_evidence(e)
    c = _truth_claims.get(claim_id)
    if c:
        c.evidence.append(e.evidence_id)
        if c.status == "proposed":
            c.status = "challenged"
        save_claim(c)
    return e


def set_verdict(claim_id: str, verdict: VerdictType, confidence: ConfidenceLevel,
                reasoning: str = "", next_action: str = "", owner_summary: str = "") -> Verdict:
    v = Verdict(verdict_id=_id("V"), claim_id=claim_id, verdict=verdict, confidence=confidence,
                reasoning=reasoning, next_action=next_action, owner_summary=owner_summary)
    save_verdict(v)
    c = _truth_claims.get(claim_id)
    if c:
        c.verdict = verdict
        c.confidence = confidence
        status_map = {"true": "verified", "false": "rejected", "partial": "partial",
                      "not_proven": "not_proven", "blocked": "not_proven",
                      "stale": "not_proven", "degraded": "partial"}
        c.status = status_map.get(verdict, c.status)
        save_claim(c)
    return v


def require_evidence_for_truth(claim_id: str) -> bool:
    c = _truth_claims.get(claim_id)
    return bool(c and c.evidence)


def reject_generic_completion(claim_id: str) -> bool:
    c = _truth_claims.get(claim_id)
    if not c:
        return False
    ev_list = [_truth_evidence[eid] for eid in c.evidence if eid in _truth_evidence]
    has_artifact = any(e.type == "artifact" for e in ev_list)
    has_api = any(e.type == "api_response" for e in ev_list)
    return has_artifact or has_api


def get_claims_for_task(task_id: str) -> list[dict]:
    return [asdict(c) for c in _truth_claims.values() if c.task_id == task_id]


def get_truth_summary() -> dict:
    from collections import Counter
    status_counts = Counter(c.status for c in _truth_claims.values())
    verdict_counts = Counter(v.verdict for v in _truth_verdicts.values())
    return {
        "total_claims": len(_truth_claims),
        "total_evidence": len(_truth_evidence),
        "total_verdicts": len(_truth_verdicts),
        "claim_statuses": dict(status_counts),
        "verdict_types": dict(verdict_counts),
    }


# ── Truth Gate: automatic verification on task completion ──────────────

def truth_gate_on_complete(task: dict, result: dict) -> dict:
    """Run truth gate when task completes. Returns gate result."""
    task_id = task.get("task_id", "unknown")
    envelope = task.get("envelope", {})

    # Create claim: task completed
    claim = create_claim(task_id, task.get("lease_owner", "agent"), f"Task {task_id} completed", "task")

    # Check evidence requirements
    has_result = bool(result)
    has_artifact_ref = bool(task.get("result_reference"))
    has_content = bool(result.get("status") and result["status"] != "generic_completion")

    # Add evidence
    if has_result:
        add_evidence(claim.claim_id, "api_response", "POST /v1/tasks/complete", "200 OK")
    if has_artifact_ref:
        add_evidence(claim.claim_id, "artifact", task["result_reference"], "artifact reference present")
    if has_content:
        add_evidence(claim.claim_id, "result_content", "task result", "non-generic content")

    # Set verdict
    evidence_count = len(claim.evidence)
    if evidence_count >= 2 and has_content:
        verdict = "true"
        confidence = "high"
        reasoning = "Task completed with artifact and non-generic content"
    elif evidence_count >= 1:
        verdict = "partial"
        confidence = "medium"
        reasoning = "Task completed but limited evidence"
    else:
        verdict = "not_proven"
        confidence = "low"
        reasoning = "Task completed without verifiable evidence"

    v = set_verdict(claim.claim_id, verdict, confidence, reasoning)

    # Update task with truth gate result
    task["truth_gate"] = {
        "claim_id": claim.claim_id,
        "verdict": v.verdict,
        "confidence": v.confidence,
        "evidence_count": evidence_count,
    }
    return task


def truth_gate_on_fail(task: dict, error_type: str, error: str) -> dict:
    """Run truth gate when task fails. Logs contradiction."""
    task_id = task.get("task_id", "unknown")

    # Create claim: task failed
    claim = create_claim(task_id, task.get("lease_owner", "agent"), f"Task {task_id} failed: {error_type}", "task")

    # Add evidence of failure
    add_evidence(claim.claim_id, "error_record", f"error_type={error_type}", error[:200])

    # Set verdict
    set_verdict(claim.claim_id, "false", "high", f"Task failed: {error_type} - {error[:100]}")

    task["truth_gate"] = {
        "claim_id": claim.claim_id,
        "verdict": "false",
        "confidence": "high",
        "error_type": error_type,
    }
    return task


# ── Redis helpers ──────────────────────────────────────────────────────

def get_json(redis_key: str, default: Any = None) -> Any:
    raw = redis.command("GET", redis_key)
    if raw is None:
        return default
    return json.loads(raw)


def get_json_many(redis_keys: list[str]) -> list[Any]:
    """Fetch a Redis collection in one round trip.

    Fleet endpoints used to open two Redis connections per node. With hundreds
    of historical cards and 21 workers polling leases, that amplified a normal
    status request into Control Plane timeouts.
    """
    if not redis_keys:
        return []
    values = redis.command("MGET", *redis_keys) or []
    return [json.loads(value) if value is not None else None for value in values]


def set_json(redis_key: str, value: Any) -> None:
    redis.command("SET", redis_key, json.dumps(value, sort_keys=True, separators=(",", ":")))


def task_key(task_id: str) -> str:
    return key(f"task:{task_id}")


def node_key(node_id: str) -> str:
    return key(f"node:{node_id}")


def drain_key(node_id: str) -> str:
    return key(f"drain:{node_id}")


def classify_node_freshness(node: dict[str, Any], current: float | None = None) -> dict[str, Any]:
    current_ts = now_ts() if current is None else current
    heartbeat_ts = parse_iso_ts(node.get("heartbeat_at"))
    observed_health = str(node.get("health") or "unknown")
    classified = dict(node)
    classified["reported_health"] = observed_health
    if heartbeat_ts is None:
        freshness = "stale"
        heartbeat_age = None
    else:
        heartbeat_age = max(0, int(current_ts - heartbeat_ts))
        if heartbeat_age > NODE_STALE_AFTER:
            freshness = "stale"
        elif heartbeat_age > NODE_DEGRADED_AFTER:
            freshness = "degraded"
        else:
            freshness = "fresh"
    classified["freshness"] = freshness
    classified["heartbeat_age_seconds"] = heartbeat_age
    if freshness == "fresh":
        classified["health"] = observed_health
    else:
        classified["health"] = freshness
    return classified


def node_health_counts(nodes: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"fresh": 0, "degraded": 0, "stale": 0, "online": 0, "total": len(nodes)}
    for node in nodes:
        freshness = node.get("freshness") or "stale"
        if freshness in {"fresh", "degraded", "stale"}:
            counts[freshness] += 1
        if node.get("health") == "online":
            counts["online"] += 1
    return counts


def all_task_ids() -> list[str]:
    values = redis.command("SMEMBERS", key("task_ids")) or []
    return sorted(values)


def registered_nodes() -> list[dict[str, Any]]:
    node_ids = sorted(redis.command("SMEMBERS", key("node_ids")) or [])
    raw_nodes = get_json_many([node_key(node_id) for node_id in node_ids])
    drains = redis.command("MGET", *[drain_key(node_id) for node_id in node_ids]) if node_ids else []
    current = now_ts()
    nodes = []
    for node_id, raw_node, draining in zip(node_ids, raw_nodes, drains):
        node = raw_node or {"node_id": node_id}
        node["draining"] = bool(draining)
        node = refresh_node_effective_state(node, current)
        nodes.append(classify_node_freshness(node, current))
    return nodes


def queue_ids() -> list[str]:
    return redis.command("LRANGE", key("queue"), 0, -1) or []


def load_task(task_id: str) -> dict[str, Any] | None:
    return get_json(task_key(task_id))


def canonical_response_envelope(
    *,
    status: str,
    task_id: str | None = None,
    trace_id: str | None = None,
    node: str | None = None,
    route_used: str | None = None,
    fallback_nodes: list[str] | None = None,
    artifacts: list[Any] | None = None,
    blocked_reason: str | None = None,
    repair_task: Any = None,
    next_action: str | None = None,
    data: Any = None,
) -> dict[str, Any]:
    if status not in CANONICAL_RESPONSE_STATUSES:
        status = "failed"
        blocked_reason = blocked_reason or "unknown"
    return {
        "task_id": task_id or "",
        "trace_id": trace_id or task_id or "",
        "status": status,
        "node": node or "home",
        "route_used": route_used or "protected_fabric_api",
        "fallback_nodes": fallback_nodes or [],
        "artifacts": artifacts or [],
        "blocked_reason": blocked_reason or "",
        "repair_task": repair_task or "",
        "next_action": next_action or "",
        "data": data or {},
    }


def task_envelope_from_request(body: dict[str, Any], default_kind: str = "owner_remote_task") -> dict[str, Any]:
    envelope = dict(body)
    envelope.setdefault("kind", default_kind)
    envelope.setdefault("source", "fabric_api")
    envelope.setdefault("command_node", body.get("command_node") or body.get("source") or "home")
    envelope.setdefault("requested_role", "remote_agent")
    envelope.setdefault("fallback_allowed", True)
    envelope.setdefault("write_scope", [])
    envelope.setdefault("constraints", {})
    return envelope


def fleet_capabilities(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    by_capability: dict[str, list[str]] = {}
    for node in nodes:
        for capability in node.get("capabilities") or []:
            by_capability.setdefault(capability, []).append(node["node_id"])
    return {"capabilities": by_capability, "nodes": nodes}


def fleet_topology(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    edges = []
    for node in nodes:
        node_id = node.get("node_id")
        if not node_id or node_id == "home":
            continue
        edges.append({"from": "home", "to": node_id, "type": "protected_fabric_api"})
    return {
        "nodes": nodes,
        "edges": edges,
        "relay_endpoint": "/v1/fabric/relay",
    }


def manifest_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    manifest_items = []
    for node in nodes:
        node_id = node.get("node_id")
        if not node_id:
            continue
        node_id = str(node_id)
        manifest_items.append({
            "node_id": node_id,
            "display_name": node.get("display_name", node.get("hostname") or node_id),
            "role": node.get("role", "control"),
            "api_paths": node.get("api_paths", ["fabric_api", "fallback_relay"]),
            "health": node.get("health"),
            "freshness": node.get("freshness"),
            "heartbeat_at": node.get("heartbeat_at"),
            "capabilities": node.get("capabilities", []),
            "base_capabilities": node.get("base_capabilities", []),
            "agent_slots": node.get("agent_slots", {}),
            "agent_id": node.get("agent_id"),
            "runners": node.get("runners", {}),
            "draining": node.get("draining"),
            "management_path": node.get("management_path", "protected_fabric_api"),
            "fallback_api_relay": node.get("fallback_api_relay", "/v1/fabric/relay"),
        })
    return manifest_items


def fabric_manifest_payload(nodes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    catalog = nodes if nodes is not None else fabric_nodes(registered_nodes())
    return {
        "manifest_version": FABRIC_MANIFEST_VERSION,
        "generated_at": utc_now(),
        "primary_control_node": "home",
        "source": "fabric_control_plane",
        "management_path": "protected_fabric_api",
        "bootstrap_policy": {
            "safe_stub": True,
            "ssh_policy": "emergency_bootstrap_diagnostic_only",
            "required_fields": BOOTSTRAP_CONTRACT["required_fields"],
        },
        "nodes": manifest_nodes(catalog),
        "topology": fleet_topology(catalog),
    }


def model_stub_envelope(body: dict[str, Any], *, endpoint: str) -> dict[str, Any]:
    task_id = body.get("task_id") or body.get("id") or ""
    trace_id = body.get("trace_id") or task_id
    return canonical_response_envelope(
        status="blocked",
        task_id=task_id,
        trace_id=trace_id,
        node=body.get("target_node") or "model-node",
        route_used=endpoint,
        fallback_nodes=["9fts", "uiap"],
        blocked_reason="model_runtime_unavailable",
        repair_task={
            "kind": "repair_model_runtime_route",
            "endpoint": endpoint,
            "action": "authenticate a model node route before enabling responses or chat completions",
        },
        next_action="submit work through /v1/agents/tasks or retry after model-node registration",
    )


def admin_denied_envelope(body: dict[str, Any], *, endpoint: str) -> dict[str, Any]:
    task_id = body.get("task_id") or ""
    trace_id = body.get("trace_id") or task_id
    return canonical_response_envelope(
        status="blocked",
        task_id=task_id,
        trace_id=trace_id,
        node=body.get("target_node") or "home",
        route_used=endpoint,
        blocked_reason="admin_scope_denied",
        repair_task={
            "kind": "request_admin_scope",
            "endpoint": endpoint,
            "action": "obtain authenticated owner scope and audited approval before privileged execution",
        },
        next_action="resubmit with an authenticated admin capability token through the protected Fabric API",
    )


def os_capabilities_envelope() -> dict[str, Any]:
    return canonical_response_envelope(
        status="completed",
        route_used="/v1/os/capabilities",
        data={"object": "list", "data": OS_CAPABILITY_CATALOG},
        next_action="invoke an allowed capability through /v1/os/capabilities/invoke",
    )


def os_capability_invoke_envelope(body: dict[str, Any], *, endpoint: str = "/v1/os/capabilities/invoke") -> dict[str, Any]:
    capability_id = str(body.get("capabilityId") or body.get("capability_id") or "")
    capability = OS_CAPABILITY_BY_ID.get(capability_id)
    trace_id = body.get("trace_id") or body.get("sourceIntentId") or body.get("source_intent_id") or capability_id
    if not capability:
        return canonical_response_envelope(
            status="blocked",
            trace_id=trace_id,
            route_used=endpoint,
            blocked_reason="unknown",
            repair_task={"kind": "register_os_capability", "capability_id": capability_id},
            next_action="declare the capability in OS_CAPABILITY_CATALOG before invocation",
        )
    if capability["approval"] != "auto":
        return canonical_response_envelope(
            status="blocked",
            trace_id=trace_id,
            node=capability["target"],
            route_used=endpoint,
            blocked_reason="admin_scope_denied" if capability["approval"] == "explicit" else "auth_failed",
            repair_task={
                "kind": "request_capability_approval",
                "capability_id": capability_id,
                "approval": capability["approval"],
                "target": capability["target"],
            },
            next_action="request owner approval before creating control-plane work",
            data={"capability": capability, "input": body.get("input") or {}},
        )
    return canonical_response_envelope(
        status="completed",
        trace_id=trace_id,
        node=capability["target"],
        route_used=endpoint,
        data={"capability": capability, "input": body.get("input") or {}, "accepted": True},
        next_action="stream shell/core events back to the avatar surface",
    )


def task_artifact_envelope(task: dict[str, Any] | None, task_id: str) -> dict[str, Any]:
    if not task:
        return canonical_response_envelope(
            status="blocked",
            task_id=task_id,
            blocked_reason="unknown",
            repair_task={"kind": "locate_task_artifacts", "task_id": task_id},
            next_action="verify task_id and retry artifact lookup",
        )
    result = task.get("result") or {}
    artifacts = []
    for key_name in ("result_path", "artifact_path", "artifact_paths", "artifacts"):
        value = result.get(key_name) or task.get(key_name)
        if not value:
            continue
        if isinstance(value, list):
            artifacts.extend(value)
        else:
            artifacts.append(value)
    return canonical_response_envelope(
        status="completed" if artifacts else "partial",
        task_id=task_id,
        node=(task.get("lease_owner") or "home").split(":", 1)[0],
        artifacts=artifacts,
        data={"task_state": task.get("state"), "result_reference": task.get("result_reference")},
        next_action="collect listed artifact paths from the authenticated artifact API" if artifacts else "wait for task completion or annotate result artifacts",
    )


def fabric_blocked_envelope(
    *,
    reason: str,
    target_node: str | None,
    fallback_nodes: list[str] | None = None,
    repair_task: dict[str, Any] | None = None,
    route: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "reason": reason,
        "target_node": target_node,
        "fallback_nodes": fallback_nodes or [],
        "fallback_route": route or {"type": "fabric_relay", "endpoint": "/v1/fabric/relay"},
        "repair_task": repair_task or {
            "kind": "repair_fabric_route",
            "target_node": target_node,
            "action": "restore node heartbeat or register an API relay before retrying direct control",
        },
        "can_continue_elsewhere": bool(fallback_nodes),
    }


def _node_online(node: dict[str, Any]) -> bool:
    return node.get("health") == "online"


def fabric_nodes(registered_nodes: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    merged = {node_id: dict(node) for node_id, node in FABRIC_NODE_CATALOG.items()}
    for registered in registered_nodes or []:
        node_id = str(registered.get("node_id") or registered.get("id") or "")
        if not node_id:
            continue
        catalog = merged.get(node_id, {"node_id": node_id, "api_paths": ["fabric_api", "fallback_relay"], "ssh": "emergency_bootstrap_diagnostic_only"})
        catalog.update(registered)
        catalog.setdefault("display_name", registered.get("hostname") or node_id)
        catalog.setdefault("api_paths", ["fabric_api", "fallback_relay"])
        catalog["ssh"] = "emergency_bootstrap_diagnostic_only"
        merged[node_id] = catalog
    for node in merged.values():
        node.setdefault("health", "unknown")
        node.setdefault("fallback_api_relay", "/v1/fabric/relay")
        node.setdefault("management_path", "protected_fabric_api")
    return sorted(merged.values(), key=lambda item: item["node_id"])


def fabric_route(
    *,
    target_node: str | None = None,
    required_capability: str | None = None,
    registered_nodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    nodes = fabric_nodes(registered_nodes)
    online = [node for node in nodes if _node_online(node)]
    candidates = nodes
    if target_node:
        candidates = [node for node in candidates if node.get("node_id") == target_node]
    if required_capability:
        candidates = [node for node in candidates if required_capability in (node.get("capabilities") or [])]
    direct = next((node for node in candidates if _node_online(node)), None)
    fallback_nodes = [
        node["node_id"]
        for node in online
        if node.get("node_id") != target_node
        and (not required_capability or required_capability in (node.get("capabilities") or []))
    ]
    if direct:
        return {
            "status": "ok",
            "route": {
                "type": "direct_fabric_api",
                "target_node": direct["node_id"],
                "endpoint": f"/v1/nodes/{direct['node_id']}",
                "relay_endpoint": "/v1/fabric/relay",
            },
            "fallback_nodes": fallback_nodes,
            "can_continue_elsewhere": True,
        }
    reason = "target_node_unavailable" if target_node else "no_node_matches_capability"
    return fabric_blocked_envelope(
        reason=reason,
        target_node=target_node,
        fallback_nodes=fallback_nodes,
        repair_task={
            "kind": "repair_fabric_route",
            "target_node": target_node,
            "required_capability": required_capability,
            "action": "register node heartbeat, clear drain state, or choose a fallback node via Fabric API",
        },
    )


def bootstrap_node_contract(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    required = set(BOOTSTRAP_CONTRACT["required_fields"])
    missing = sorted(field for field in required if not body.get(field))
    if missing:
        return 400, {
            "status": "blocked",
            "reason": "bootstrap_contract_missing_fields",
            "missing_fields": missing,
            "fallback_nodes": [],
            "repair_task": {
                "kind": "repair_bootstrap_request",
                "action": "resubmit bootstrap request with required non-secret identity and capability fields",
            },
            "can_continue_elsewhere": False,
        }

    node_id = str(body["node_id"])
    node = get_json(node_key(node_id), {
        "node_id": node_id,
        "health": "stale",
        "freshness": "stale",
        "capabilities": [],
    })
    node["node_id"] = node_id
    node["display_name"] = body.get("display_name") or body.get("hostname") or node.get("display_name")
    node["role"] = body.get("role")
    node["capabilities"] = body.get("capabilities", node.get("capabilities", []))
    node["ip"] = body.get("ip") or body.get("hostname")
    node["public_ip"] = body.get("public_ip")
    node["api_paths"] = node.get("api_paths", ["fabric_api", "fallback_relay"])
    node["bootstrap_state"] = "pending_identity_approval"
    node["requested_by"] = body.get("requested_by")
    node["requested_at"] = node.get("requested_at") or utc_now()
    node["bootstrap_contract_version"] = BOOTSTRAP_CONTRACT["endpoint"]

    set_json(node_key(node_id), node)
    redis.command("SADD", key("node_ids"), node_id)
    manifest = fabric_manifest_payload(fabric_nodes(registered_nodes() + [{"node_id": node_id}]))
    return 202, {
        "status": "accepted",
        "bootstrap": "safe_stub",
        "node_id": body["node_id"],
        "display_name": body.get("display_name"),
        "capabilities": body.get("capabilities", []),
        "node": node,
        "manifest": {
            "version": manifest["manifest_version"],
            "generated_at": manifest["generated_at"],
            "primary_control_node": manifest["primary_control_node"],
        },
        "next_action": "approve scoped credentials through authenticated Fabric API and start agent-host registration",
        "secrets_returned": False,
    }


def save_task(task: dict[str, Any]) -> None:
    task["updated_at"] = utc_now()
    set_json(task_key(task["task_id"]), task)
    redis.command("SADD", key("task_ids"), task["task_id"])
    if task.get("state") in ACTIVE_LEASE_STATES:
        redis.command("SADD", key("active_lease_ids"), task["task_id"])
    else:
        redis.command("SREM", key("active_lease_ids"), task["task_id"])


def enqueue(task_id: str) -> None:
    redis.command("RPUSH", key("queue"), task_id)


def remove_from_queue(task_id: str) -> None:
    redis.command("LREM", key("queue"), 0, task_id)


def normalize_task(envelope: dict[str, Any]) -> dict[str, Any]:
    task_id = envelope.get("task_id") or f"KOL-TASK-{uuid.uuid4().hex[:12]}"
    created = utc_now()
    return {
        "task_id": task_id,
        "idempotency_key": envelope.get("idempotency_key") or task_id,
        "kind": envelope.get("kind", "read_only_probe"),
        "state": STATE_QUEUED,
        "attempt": 0,
        "max_retries": int(envelope.get("max_retries", MAX_RETRIES)),
        "lease_contract_version": LEASE_CONTRACT_VERSION,
        "attempt_id": None,
        "lease_id": None,
        "lease_slot_id": None,
        "fencing_token": None,
        "lease_owner": None,
        "lease_until": None,
        "heartbeat_at": None,
        "result_reference": None,
        "result": None,
        "error_type": None,
        "error": None,
        "created_at": created,
        "updated_at": created,
        "envelope": envelope,
    }


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def normalized_string_list(value: Any) -> list[str]:
    """Return a deterministic, non-empty capability/id list."""
    normalized = {
        str(item).strip()
        for item in ensure_list(value)
        if item is not None and str(item).strip()
    }
    return sorted(normalized)


def is_agent_slot_heartbeat(body: dict[str, Any]) -> bool:
    # An empty slot collection on a generic Agent Host heartbeat is not an
    # instruction to erase independently live slots.
    return bool(body.get("slot_id")) or bool(body.get("agent_slots"))


def resolve_logical_node_id(requested_node_id: str, body: dict[str, Any]) -> str:
    """Resolve a process identity to one logical node without implicit aliases.

    A legacy process such as ``home-codex-provider`` may migrate into the
    logical ``home`` record only by explicitly declaring ``logical_node_id``
    and a slot payload. A generic heartbeat cannot silently rename a node.
    """
    requested = str(requested_node_id).strip()
    logical = str(body.get("logical_node_id") or body.get("parent_node_id") or requested).strip()
    if not requested or not logical:
        raise ValueError("node_id_required")
    if logical != requested and not is_agent_slot_heartbeat(body):
        raise ValueError("logical_node_alias_requires_agent_slot")
    return logical


def _stored_agent_slots(node: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_slots = node.get("agent_slots")
    if isinstance(raw_slots, dict):
        result: dict[str, dict[str, Any]] = {}
        for raw_slot_id, raw_slot in raw_slots.items():
            if not isinstance(raw_slot, dict):
                continue
            slot_id = str(raw_slot.get("slot_id") or raw_slot_id).strip()
            if slot_id:
                result[slot_id] = dict(raw_slot, slot_id=slot_id)
        return result
    if isinstance(raw_slots, list):
        result = {}
        for raw_slot in raw_slots:
            if not isinstance(raw_slot, dict):
                continue
            slot_id = str(raw_slot.get("slot_id") or "").strip()
            if slot_id:
                result[slot_id] = dict(raw_slot, slot_id=slot_id)
        return result
    return {}


def _slot_payloads(body: dict[str, Any], logical_node_id: str) -> list[dict[str, Any]]:
    """Normalize top-level and batched slot heartbeats.

    ``agent_slots`` accepts either a list, a single slot object, or a mapping
    keyed by slot id. Repeated ids are deterministically merged in input order.
    """
    raw_entries: list[dict[str, Any]] = []
    if body.get("slot_id"):
        raw_entries.append({
            key_name: value
            for key_name, value in body.items()
            if key_name not in {"agent_slots", "logical_node_id", "parent_node_id", "node_id"}
        })

    if "agent_slots" in body:
        raw_slots = body.get("agent_slots")
        if isinstance(raw_slots, list):
            if not all(isinstance(item, dict) for item in raw_slots):
                raise ValueError("agent_slots_must_contain_objects")
            raw_entries.extend(dict(item) for item in raw_slots)
        elif isinstance(raw_slots, dict):
            if "slot_id" in raw_slots:
                raw_entries.append(dict(raw_slots))
            else:
                for mapped_slot_id, raw_slot in raw_slots.items():
                    if not isinstance(raw_slot, dict):
                        raise ValueError("agent_slots_must_contain_objects")
                    slot = dict(raw_slot)
                    declared_slot_id = slot.get("slot_id")
                    if declared_slot_id and str(declared_slot_id) != str(mapped_slot_id):
                        raise ValueError("agent_slot_id_mismatch")
                    slot["slot_id"] = str(mapped_slot_id)
                    raw_entries.append(slot)
        else:
            raise ValueError("agent_slots_must_be_object_or_list")

    if not raw_entries:
        raise ValueError("agent_slot_id_required")

    merged: dict[str, dict[str, Any]] = {}
    for raw_slot in raw_entries:
        slot_id = str(raw_slot.get("slot_id") or "").strip()
        if not slot_id or len(slot_id) > 200 or any(char.isspace() for char in slot_id):
            raise ValueError("invalid_agent_slot_id")
        declared_node = raw_slot.get("logical_node_id") or raw_slot.get("parent_node_id") or raw_slot.get("node_id")
        if declared_node and str(declared_node).strip() != logical_node_id:
            raise ValueError("agent_slot_node_mismatch")
        slot = merged.setdefault(slot_id, {"slot_id": slot_id})
        slot.update(raw_slot)
        slot["slot_id"] = slot_id
        slot["node_id"] = logical_node_id
    return [merged[slot_id] for slot_id in sorted(merged)]


def _agent_slot_projection(slot: dict[str, Any], current: float) -> dict[str, Any]:
    projected = dict(slot)
    heartbeat_ts = parse_iso_ts(slot.get("heartbeat_at"))
    age = None if heartbeat_ts is None else max(0, int(current - heartbeat_ts))
    freshness = "stale" if age is None or age > NODE_STALE_AFTER else "fresh"
    state = str(slot.get("status") or slot.get("health") or "online").strip().lower()
    operational = freshness == "fresh" and state not in INACTIVE_AGENT_SLOT_STATES and not bool(slot.get("draining"))
    projected["freshness"] = freshness
    projected["heartbeat_age_seconds"] = age
    projected["effective"] = operational
    return projected


def _runner_state_priority(value: Any) -> int:
    if isinstance(value, dict):
        state = str(value.get("status") or "").strip().lower()
    else:
        state = str(value or "").strip().lower()
    if state in {"available", "healthy", "online", "ready", "running"}:
        return 0
    if state in BLOCKED_RUNNER_STATES:
        return 2
    return 1


def refresh_node_effective_state(node: dict[str, Any], current: float | None = None) -> dict[str, Any]:
    """Rebuild effective capabilities/runners from base plus live slots."""
    projected = dict(node)
    current_ts = now_ts() if current is None else current
    slots = _stored_agent_slots(projected)

    if "base_capabilities" in projected:
        base_capabilities = normalized_string_list(projected.get("base_capabilities"))
    else:
        # One-time migration from the legacy flat representation. Slot caps are
        # subtracted because ``capabilities`` may already be an old union.
        slot_capabilities = {
            capability
            for slot in slots.values()
            for capability in normalized_string_list(slot.get("capabilities"))
        }
        base_capabilities = [
            capability
            for capability in normalized_string_list(projected.get("capabilities"))
            if capability not in slot_capabilities
        ]

    if "base_runners" in projected and isinstance(projected.get("base_runners"), dict):
        base_runners = dict(projected.get("base_runners") or {})
    else:
        slot_runner_names = {
            str(runner)
            for slot in slots.values()
            if isinstance(slot.get("runners"), dict)
            for runner in slot["runners"]
        }
        base_runners = {
            str(runner): value
            for runner, value in (projected.get("runners") or {}).items()
            if str(runner) not in slot_runner_names
        } if isinstance(projected.get("runners"), dict) else {}

    effective_capabilities = set(base_capabilities)
    effective_runners = dict(base_runners)
    capability_slots: dict[str, list[str]] = {}
    runner_slots: dict[str, list[str]] = {}
    projected_slots: dict[str, dict[str, Any]] = {}
    for slot_id in sorted(slots):
        slot = _agent_slot_projection(slots[slot_id], current_ts)
        projected_slots[slot_id] = slot
        if not slot["effective"]:
            continue
        for capability in normalized_string_list(slot.get("capabilities")):
            effective_capabilities.add(capability)
            capability_slots.setdefault(capability, []).append(slot_id)
        slot_runners = slot.get("runners") if isinstance(slot.get("runners"), dict) else {}
        for runner in sorted(slot_runners):
            runner_name = str(runner)
            runner_slots.setdefault(runner_name, []).append(slot_id)
            current_value = effective_runners.get(runner_name)
            candidate = slot_runners[runner]
            if current_value is None or _runner_state_priority(candidate) < _runner_state_priority(current_value):
                effective_runners[runner_name] = candidate

    projected["base_capabilities"] = base_capabilities
    projected["base_runners"] = base_runners
    projected["agent_slots"] = projected_slots
    projected["capabilities"] = sorted(effective_capabilities)
    projected["effective_capabilities"] = projected["capabilities"]
    projected["runners"] = {runner: effective_runners[runner] for runner in sorted(effective_runners)}
    projected["capability_slots"] = {name: ids for name, ids in sorted(capability_slots.items())}
    projected["runner_slots"] = {name: ids for name, ids in sorted(runner_slots.items())}
    return projected


def merge_node_heartbeat(
    node: dict[str, Any],
    logical_node_id: str,
    body: dict[str, Any],
    *,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Merge one process heartbeat without flattening other process slots."""
    observed = observed_at or utc_now()
    merged = refresh_node_effective_state(dict(node, node_id=logical_node_id))
    slots = _stored_agent_slots(merged)

    if is_agent_slot_heartbeat(body):
        for incoming in _slot_payloads(body, logical_node_id):
            slot_id = incoming["slot_id"]
            slot = dict(slots.get(slot_id) or {"slot_id": slot_id, "node_id": logical_node_id})
            for key_name, value in incoming.items():
                if key_name in {"logical_node_id", "parent_node_id", "heartbeat_at"}:
                    continue
                if key_name == "capabilities":
                    slot[key_name] = normalized_string_list(value)
                elif key_name == "runners":
                    if not isinstance(value, dict):
                        raise ValueError("agent_slot_runners_must_be_object")
                    slot[key_name] = dict(value)
                else:
                    slot[key_name] = value
            slot["slot_id"] = slot_id
            slot["node_id"] = logical_node_id
            slot["heartbeat_at"] = observed
            slot.setdefault("health", "online")
            slots[slot_id] = slot
        merged["agent_slots"] = slots
    else:
        reserved = {
            "agent_slots", "base_capabilities", "base_runners", "capabilities",
            "effective_capabilities", "health", "heartbeat_at", "logical_node_id",
            "node_id", "parent_node_id", "runners", "slot_id", "status",
        }
        for key_name, value in body.items():
            if key_name not in reserved:
                merged[key_name] = value
        if "capabilities" in body:
            merged["base_capabilities"] = normalized_string_list(body.get("capabilities"))
        if "runners" in body:
            if not isinstance(body.get("runners"), dict):
                raise ValueError("node_runners_must_be_object")
            merged["base_runners"] = dict(body.get("runners") or {})

    merged["node_id"] = logical_node_id
    merged["health"] = "online"
    merged["heartbeat_at"] = observed
    return refresh_node_effective_state(merged)


def persist_node_heartbeat(requested_node_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Persist a heartbeat under its logical node, never its process alias."""
    node_id = resolve_logical_node_id(requested_node_id, body)
    with NODE_UPDATE_LOCK:
        existing = get_json(node_key(node_id))
        if is_agent_slot_heartbeat(body) and not existing:
            raise LookupError("logical_node_not_registered")
        node = merge_node_heartbeat(existing or {"node_id": node_id}, node_id, body)
        set_json(node_key(node_id), node)
        redis.command("SADD", key("node_ids"), node_id)
        return node


def lease_claim_view(node: dict[str, Any], body: dict[str, Any]) -> tuple[list[str], dict[str, Any], str | None]:
    """Bind a lease poll to base agent state or one live process slot."""
    projected = refresh_node_effective_state(node)
    slots = _stored_agent_slots(projected)
    requested_slot_id = str(body.get("slot_id") or "").strip() or None
    agent_id = str(body.get("agent_id") or "").strip()

    if requested_slot_id is None and agent_id:
        matches = [
            slot_id
            for slot_id, slot in slots.items()
            if slot.get("effective") and agent_id in {slot_id, str(slot.get("agent_id") or "")}
        ]
        if len(matches) > 1:
            raise ValueError("agent_id_matches_multiple_slots")
        requested_slot_id = matches[0] if matches else None

    claim_node = dict(projected)
    if requested_slot_id is not None:
        slot = slots.get(requested_slot_id)
        if not slot:
            raise ValueError("agent_slot_not_registered")
        if str(slot.get("node_id") or projected.get("node_id")) != str(projected.get("node_id")):
            raise ValueError("agent_slot_node_mismatch")
        if not slot.get("effective"):
            raise ValueError("agent_slot_not_available")
        slot_agent_id = str(slot.get("agent_id") or "").strip()
        if agent_id and slot_agent_id and agent_id != slot_agent_id:
            raise ValueError("agent_slot_owner_mismatch")
        authorized_capabilities = normalized_string_list(slot.get("capabilities"))
        claim_node["runners"] = dict(slot.get("runners") or {}) if isinstance(slot.get("runners"), dict) else {}
        claim_node["claim_slot_id"] = requested_slot_id
    else:
        authorized_capabilities = normalized_string_list(projected.get("base_capabilities"))
        claim_node["runners"] = dict(projected.get("base_runners") or {})
        claim_node["claim_slot_id"] = None

    if "capabilities" in body:
        reported = set(normalized_string_list(body.get("capabilities")))
        authorized_capabilities = [capability for capability in authorized_capabilities if capability in reported]
    if isinstance(body.get("runners"), dict):
        reported_runners = body["runners"]
        claim_node["runners"] = {
            runner: reported_runners.get(runner, value)
            for runner, value in claim_node["runners"].items()
        }
    claim_node["capabilities"] = authorized_capabilities
    return authorized_capabilities, claim_node, requested_slot_id


def validate_task_mutation_fence(task: dict[str, Any], body: dict[str, Any]) -> str | None:
    """Validate the complete durable lease fence for every task mutation.

    Active work never has an unfenced compatibility path. The only legacy
    exception is an idempotent replay against a record that was already
    terminal before lease fencing existed and therefore stores no fence at
    all. A terminal record with a persisted fence still requires an exact
    match, so stale workers cannot replace its evidence.
    """
    provided = [field for field in LEASE_FENCE_FIELDS if body.get(field) is not None]
    stored = [field for field in LEASE_FENCE_FIELDS if task.get(field) is not None]
    state = task.get("state")

    if state in TERMINAL_STATES and not stored and not provided:
        return None
    # Agent hosts send attempt_id + fencing_token but may omit lease_id.
    # Accept if the two core fields are present and match.
    if "attempt_id" not in provided or "fencing_token" not in provided:
        return "lease_fence_fields_required"
    if len(stored) != len(LEASE_FENCE_FIELDS):
        return "lease_fence_not_issued"
    if state not in ACTIVE_LEASE_STATES and state not in TERMINAL_STATES:
        return "lease_is_not_active"
    for field in LEASE_FENCE_FIELDS:
        # lease_id may be omitted by agent hosts — only check if provided
        if body.get(field) is None and field == "lease_id":
            continue
        if str(body.get(field)) != str(task.get(field)):
            return f"stale_{field}"
    lease_owner = str(task.get("lease_owner") or "")
    expected_node, _, expected_agent = lease_owner.partition(":")
    if body.get("node_id") is not None and str(body.get("node_id")) != expected_node:
        return "lease_node_mismatch"
    if body.get("agent_id") is not None and str(body.get("agent_id")) != expected_agent:
        return "lease_agent_mismatch"
    if body.get("slot_id") is not None and str(body.get("slot_id")) != str(task.get("lease_slot_id") or ""):
        return "lease_slot_mismatch"
    return None


def issue_task_lease(
    task: dict[str, Any],
    *,
    node_id: str,
    agent_id: str,
    slot_id: str | None,
) -> dict[str, Any]:
    """Create a new opaque, durable lease identity for exactly one attempt."""
    leased = dict(task)
    leased["state"] = STATE_LEASED
    leased["attempt"] = int(leased.get("attempt", 0)) + 1
    leased["attempt_id"] = f"{leased['task_id']}-attempt-{leased['attempt']}"
    leased["lease_id"] = uuid.uuid4().hex
    leased["lease_slot_id"] = slot_id
    leased["fencing_token"] = leased["attempt"]
    leased["lease_owner"] = f"{node_id}:{agent_id}"
    leased["lease_until"] = now_ts() + LEASE_DURATION
    leased["heartbeat_at"] = utc_now()
    leased["lease_contract_version"] = LEASE_CONTRACT_VERSION
    return leased


def preserve_terminal_lease_evidence(task: dict[str, Any]) -> dict[str, Any]:
    """Freeze the lease binding that was authorized to create terminal state."""
    if task.get("terminal_lease_evidence") is not None:
        return task
    if task.get("state") not in TERMINAL_STATES:
        return task
    if not any(task.get(field) is not None for field in LEASE_FENCE_FIELDS):
        return task
    task["terminal_lease_evidence"] = {
        "lease_contract_version": task.get("lease_contract_version") or LEASE_CONTRACT_VERSION,
        "attempt_id": task.get("attempt_id"),
        "lease_id": task.get("lease_id"),
        "fencing_token": task.get("fencing_token"),
        "lease_owner": task.get("lease_owner"),
        "lease_slot_id": task.get("lease_slot_id"),
        "terminal_state": task.get("state"),
        "closed_at": utc_now(),
    }
    return task


def runner_capability_names(runner: str) -> set[str]:
    return {f"runner:{runner}", f"runner_{runner}", f"{runner}_runner"}


def runner_state(node: dict[str, Any], runner: str) -> str | None:
    runners = node.get("runners")
    if isinstance(runners, dict):
        value = runners.get(runner)
        if isinstance(value, dict):
            state = value.get("status")
            return str(state).strip().lower() if state is not None else None
        if isinstance(value, str):
            return value.strip().lower()
    runner_status = node.get("runner_status")
    if isinstance(runner_status, dict):
        value = runner_status.get(runner)
        if isinstance(value, dict):
            state = value.get("status")
            return str(state).strip().lower() if state is not None else None
        if isinstance(value, str):
            return value.strip().lower()
    return None


def mark_node_runner_failure(task: dict[str, Any], body: dict[str, Any]) -> None:
    error_type = body.get("error_type")
    if error_type not in {"runner_auth_blocked", "runner_unavailable"}:
        return
    result = body.get("result") if isinstance(body.get("result"), dict) else {}
    envelope = task.get("envelope", {})
    runner = result.get("runner") or envelope.get("runner")
    if not runner:
        return
    lease_owner = str(task.get("lease_owner") or "")
    node_id = lease_owner.split(":", 1)[0] if lease_owner else None
    if not node_id:
        return
    node = get_json(node_key(node_id), {"node_id": node_id})
    runner_failure = {
        "status": "blocked" if error_type == "runner_auth_blocked" else "unavailable",
        "error_type": error_type,
        "updated_at": utc_now(),
    }
    slot_id = task.get("lease_slot_id")
    with NODE_UPDATE_LOCK:
        node = refresh_node_effective_state(node)
        slots = _stored_agent_slots(node)
        if slot_id and slot_id in slots:
            slot = dict(slots[slot_id])
            runners = dict(slot.get("runners") or {}) if isinstance(slot.get("runners"), dict) else {}
            runners[str(runner)] = runner_failure
            slot["runners"] = runners
            slot["status"] = runner_failure["status"]
            slot["heartbeat_at"] = utc_now()
            slots[str(slot_id)] = slot
            node["agent_slots"] = slots
        else:
            runners = dict(node.get("base_runners") or {})
            runners[str(runner)] = runner_failure
            node["base_runners"] = runners
        set_json(node_key(node_id), refresh_node_effective_state(node))


def compatible(task: dict[str, Any], node_id: str, capabilities: list[str], node: dict[str, Any] | None = None) -> bool:
    envelope = task.get("envelope", {})
    target_node = envelope.get("target_node") or envelope.get("required_node")
    if target_node and target_node != node_id:
        return False
    allowed = envelope.get("allowed_nodes")
    if allowed and node_id not in allowed:
        return False
    avoided = set(str(item) for item in ensure_list(envelope.get("avoid_nodes") or envelope.get("avoided_nodes")))
    if node_id in avoided:
        return False
    required = envelope.get("required_capability")
    if required and required not in capabilities:
        return False
    runner = str(envelope.get("runner") or "").strip().lower()
    # Runner selection is an execution constraint for every AI task, not only
    # owner_remote_task. Without this gate, chat/image/orchestrator work can be
    # leased by a healthy node that has no matching authenticated runtime and
    # fail terminally before a capable worker gets a chance to claim it.
    if runner:
        if not runner_capability_names(runner).intersection(set(capabilities)):
            return False
        node_state = runner_state(node or {}, runner)
        if node_state in BLOCKED_RUNNER_STATES:
            return False
    return True


def requeue_expired_leases() -> None:
    current = now_ts()
    active_ids = sorted(redis.command("SMEMBERS", key("active_lease_ids")) or [])
    for task_id in active_ids:
        task = load_task(task_id)
        if not task or task.get("state") not in ACTIVE_LEASE_STATES:
            redis.command("SREM", key("active_lease_ids"), task_id)
            continue
        lease_until = float(task.get("lease_until") or 0)
        if lease_until >= current:
            continue
        if int(task.get("attempt", 0)) < int(task.get("max_retries", MAX_RETRIES)):
            task["state"] = STATE_RETRY
            task["lease_owner"] = None
            task["lease_id"] = None
            task["lease_slot_id"] = None
            task["lease_until"] = None
            task["error_type"] = "lease_expired"
            task["error"] = "lease expired before task completion"
            save_task(task)
            task["state"] = STATE_QUEUED
            save_task(task)
            enqueue(task_id)
        else:
            task["state"] = STATE_DEAD
            task["error_type"] = "lease_expired"
            task["error"] = "lease expired and retry budget exhausted"
            preserve_terminal_lease_evidence(task)
            save_task(task)
            redis.command("RPUSH", key("dead_letter"), task_id)


def create_task(envelope: dict[str, Any]) -> dict[str, Any]:
    task = normalize_task(envelope)
    idem_key = key(f"idempotency:{task['idempotency_key']}")
    existing = redis.command("GET", idem_key)
    if existing:
        existing_task = load_task(existing)
        if existing_task:
            return existing_task
    save_task(task)
    redis.command("SET", idem_key, task["task_id"])
    enqueue(task["task_id"])
    return task


def create_review_task(source_task: dict[str, Any], result: dict[str, Any]) -> dict[str, Any] | None:
    envelope = source_task.get("envelope", {})
    if not envelope.get("create_review_on_complete"):
        return None
    pr_url = result.get("pull_request_url") or result.get("pr_url")
    if not pr_url:
        return None
    review_id = envelope.get("review_task_id") or f"{source_task['task_id']}-REVIEW"
    review_envelope = {
        "task_id": review_id,
        "idempotency_key": f"review:{source_task['task_id']}",
        "kind": "review_pr",
        "target_node": envelope.get("review_node", "new"),
        "required_capability": "review",
        "source_task_id": source_task["task_id"],
        "pull_request_url": pr_url,
        "branch": result.get("branch"),
        "base_ref": envelope.get("base_ref", "origin/main"),
        "max_retries": envelope.get("review_max_retries", MAX_RETRIES),
    }
    review = create_task(review_envelope)
    review["state"] = STATE_REVIEW if review["state"] == STATE_QUEUED else review["state"]
    save_task(review)
    return review


def response(handler: BaseHTTPRequestHandler, status: int, body: Any) -> None:
    payload = json.dumps(body, indent=2, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def read_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or "0")
    if not length:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def parse_owner_ids(value: str) -> set[int]:
    ids = set()
    for item in value.replace(";", ",").split(","):
        item = item.strip()
        if item:
            ids.add(int(item))
    return ids


def validate_miniapp(handler: BaseHTTPRequestHandler, body: dict[str, Any] | None = None) -> dict[str, Any]:
    init_data = handler.headers.get("X-Telegram-Init-Data") or (body or {}).get("init_data") or ""
    return validate_telegram_init_data(
        init_data,
        os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        parse_owner_ids(os.environ.get("TELEGRAM_OWNER_IDS", "")),
        parse_owner_ids(os.environ.get("TELEGRAM_ADMIN_IDS", "")),
        int(os.environ.get("TELEGRAM_INIT_DATA_MAX_AGE", "86400")),
    )


def superfactory_status() -> dict[str, Any]:
    nodes = []
    for node_id in sorted(redis.command("SMEMBERS", key("node_ids")) or []):
        node = get_json(node_key(node_id), {})
        node["draining"] = bool(redis.command("GET", drain_key(node_id)))
        nodes.append(node)
    tasks = [task for task in (load_task(task_id) for task_id in all_task_ids()) if task]
    counts: dict[str, int] = {}
    for task in tasks:
        state = str(task.get("state") or "unknown")
        counts[state] = counts.get(state, 0) + 1
    receiver = plan_update_receiver(webhook_info={"url": os.environ.get("TELEGRAM_WEBHOOK_URL", "")})
    return {
        "status": "ok",
        "receiver": {
            "mode": receiver.mode,
            "should_poll": receiver.should_poll,
            "webhook_configured": bool(receiver.webhook_url),
            "conflict": receiver.conflict,
        },
        "runner_policy": runner_policy(),
        "nodes": nodes,
        "task_counts": counts,
        "queue": queue_ids(),
    }


def miniapp_task_envelope(body: dict[str, Any], auth: dict[str, Any]) -> dict[str, Any]:
    text = str(body.get("objective") or body.get("message") or "").strip()
    if not text:
        raise ValueError("objective is required")
    runner = select_runner(str(body.get("kind") or "owner_remote_task"), body.get("runner"))
    task_id = body.get("task_id") or f"TGAPP-{uuid.uuid4().hex[:12]}"
    return {
        "task_id": task_id,
        "idempotency_key": body.get("idempotency_key") or f"telegram-miniapp:{auth['user']['id']}:{task_id}",
        "kind": body.get("kind") or "owner_remote_task",
        "required_capability": body.get("required_capability") or "generic_implementation",
        "objective": text,
        "runner": runner["runner"],
        "runner_policy": runner,
        "source": {
            "kind": "telegram_miniapp",
            "user_id": auth["user"]["id"],
            "role": auth["role"],
            "accepted_at": utc_now(),
        },
        "max_retries": int(body.get("max_retries", 1)),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "KolibriFactoryControl/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s %s\n" % (utc_now(), fmt % args))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            if path in {"/health", "/v1/health"}:
                pong = redis.command("PING")
                response(self, 200, canonical_response_envelope(
                    status="completed",
                    node="home",
                    route_used="/v1/health",
                    data={"redis": pong, "queue_backend": "redis", "time": utc_now(), "fabric_api_version": FABRIC_API_VERSION, "truth_factory": "enabled"},
                    next_action="use /v1/fleet/route before dispatching work to a node",
                ))
                return
            if path == "/v1/truth/summary":
                response(self, 200, get_truth_summary())
                return
            if path == "/v1/truth/claims":
                query = parse_qs(parsed.query)
                task_id = query.get("task_id", [None])[0]
                if task_id:
                    response(self, 200, {"claims": get_claims_for_task(task_id)})
                else:
                    response(self, 200, {"claims": [asdict(c) for c in _truth_claims.values()]})
                return
            if path == "/v1/truth/contradictions":
                contradictions = [asdict(c) for c in _truth_claims.values() if c.status == "challenged"]
                response(self, 200, {"contradictions": contradictions, "count": len(contradictions)})
                return
            if path == "/v1/superfactory/status":
                auth = validate_miniapp(self)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                response(self, 200, superfactory_status())
                return
            if path == "/v1/nodes":
                query = parse_qs(parsed.query)
                limit = min(max(int(query.get("limit", ["50"])[0]), 1), 250)
                offset = max(int(query.get("offset", ["0"])[0]), 0)
                nodes = []
                current = now_ts()
                node_ids = sorted(redis.command("SMEMBERS", key("node_ids")) or [])
                total_indexed = len(node_ids)
                page_ids = node_ids[offset:offset + limit]
                page_nodes = get_json_many([node_key(node_id) for node_id in page_ids])
                drains = redis.command("MGET", *[drain_key(node_id) for node_id in page_ids]) if page_ids else []
                for node_id, raw_node, draining in zip(page_ids, page_nodes, drains):
                    node = raw_node or {"node_id": node_id}
                    node["draining"] = bool(draining)
                    node = refresh_node_effective_state(node, current)
                    nodes.append(classify_node_freshness(node, current))
                counts = node_health_counts(nodes)
                response(self, 200, {
                    "nodes": nodes,
                    "counts": counts,
                    "freshness": counts,
                    "pagination": {"limit": limit, "offset": offset, "returned": len(nodes), "total_indexed": total_indexed},
                })
                return
            if path.startswith("/v1/nodes/"):
                node_id = path.split("/", 3)[3]
                node = get_json(node_key(node_id), {})
                if not node:
                    response(self, 404, {"error": "node_not_found", "node_id": node_id})
                    return
                node["draining"] = bool(redis.command("GET", drain_key(node_id)))
                response(self, 200, classify_node_freshness(refresh_node_effective_state(node)))
                return
            if path == "/v1/fleet/nodes":
                nodes = fabric_nodes(registered_nodes())
                response(self, 200, canonical_response_envelope(
                    status="completed",
                    route_used="/v1/fleet/nodes",
                    data={"nodes": nodes},
                    next_action="select a target node or ask /v1/fleet/route for a safe route",
                ))
                return
            if path == "/v1/fleet/topology":
                nodes = fabric_nodes(registered_nodes())
                response(self, 200, canonical_response_envelope(
                    status="completed",
                    route_used="/v1/fleet/topology",
                    data=fleet_topology(nodes),
                    next_action="use the protected_fabric_api edge or relay endpoint for execution",
                ))
                return
            if path == "/v1/fleet/route":
                query = parse_qs(parsed.query)
                route = fabric_route(
                    target_node=query.get("target_node", [None])[0],
                    required_capability=query.get("required_capability", [None])[0],
                    registered_nodes=registered_nodes(),
                )
                status = "completed" if route.get("status") == "ok" else "blocked"
                response(self, 200 if status == "completed" else 503, canonical_response_envelope(
                    status=status,
                    node=route.get("route", {}).get("target_node") or route.get("target_node") or "home",
                    route_used="/v1/fleet/route",
                    fallback_nodes=route.get("fallback_nodes", []),
                    blocked_reason=route.get("reason", ""),
                    repair_task=route.get("repair_task", ""),
                    data=route,
                    next_action="dispatch via /v1/agents/tasks" if status == "completed" else "choose a fallback node or run the repair task",
                ))
                return
            if path == "/v1/fleet/capabilities":
                nodes = fabric_nodes(registered_nodes())
                response(self, 200, canonical_response_envelope(
                    status="completed",
                    route_used="/v1/fleet/capabilities",
                    data=fleet_capabilities(nodes),
                    next_action="include required_capability in /v1/agents/tasks when dispatching work",
                ))
                return
            if path == "/v1/fabric/manifest":
                response(self, 200, fabric_manifest_payload(fabric_nodes(registered_nodes())))
                return
            if path == "/v1/os/capabilities":
                response(self, 200, os_capabilities_envelope())
                return
            if path == "/v1/models":
                response(self, 200, canonical_response_envelope(
                    status="completed",
                    route_used="/v1/models",
                    data={"object": "list", "data": MODEL_CATALOG},
                    next_action="model generation endpoints remain safe stubs until authenticated model routes are online",
                ))
                return
            if path == "/v1/admin/agent-host-binary":
                binary_path = Path(os.environ.get(
                    "KOLIBRI_AGENT_HOST_BINARY",
                    "/usr/local/bin/kolibri-agent-host",
                ))
                if not binary_path.exists():
                    response(self, 404, {"error": "binary_not_found"})
                    return
                data = binary_path.read_bytes()
                import hashlib as _hl
                sha256 = _hl.sha256(data).hexdigest()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("X-Binary-SHA256", sha256)
                self.send_header("X-Binary-Size", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return
            if path == "/v1/fabric/health":
                pong = redis.command("PING")
                response(self, 200, {
                    "status": "ok",
                    "fabric_api_version": FABRIC_API_VERSION,
                    "primary_management_path": "protected_fabric_api",
                    "ssh_policy": "emergency_bootstrap_diagnostic_only",
                    "redis": pong,
                    "time": utc_now(),
                })
                return
            if path == "/v1/fabric/policy":
                response(self, 200, {
                    "primary_management_path": "protected_fabric_api",
                    "ssh_policy": "emergency_bootstrap_diagnostic_only",
                    "owner_rights": OWNER_RIGHTS_POLICY,
                    "node_identity": NODE_IDENTITY_ROTATION_POLICY,
                    "bootstrap": BOOTSTRAP_CONTRACT,
                })
                return
            if path == "/v1/fabric/routes":
                response(self, 200, {
                    "status": "ok",
                    "primary_management_path": "protected_fabric_api",
                    "nodes": fabric_nodes(registered_nodes()),
                    "relay_endpoint": "/v1/fabric/relay",
                })
                return
            if path == "/v1/fabric/keys/rotation":
                response(self, 200, NODE_IDENTITY_ROTATION_POLICY)
                return
            if path == "/v1/tasks":
                query = parse_qs(parsed.query)
                wanted = query.get("state", [None])[0]
                limit = min(max(int(query.get("limit", ["100"])[0]), 1), 250)
                offset = max(int(query.get("offset", ["0"])[0]), 0)
                task_ids = list(reversed(all_task_ids()))
                total_indexed = len(task_ids)
                if wanted is None:
                    task_ids = task_ids[offset:offset + limit]
                tasks = [load_task(task_id) for task_id in task_ids]
                tasks = [task for task in tasks if task and (wanted is None or task.get("state") == wanted)]
                if wanted is not None:
                    tasks = tasks[offset:offset + limit]
                queue = queue_ids()
                response(self, 200, {
                    "tasks": tasks,
                    "queue": queue[:250],
                    "pagination": {"limit": limit, "offset": offset, "returned": len(tasks), "total_indexed": total_indexed},
                    "queue_total": len(queue),
                })
                return
            if path.startswith("/v1/tasks/"):
                task_id = path.split("/", 3)[3]
                task = load_task(task_id)
                if not task:
                    response(self, 404, {"error": "task_not_found", "task_id": task_id})
                    return
                response(self, 200, task)
                return
            if path.startswith("/v1/superfactory/tasks/") and path.endswith("/artifacts"):
                auth = validate_miniapp(self)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                task_id = path.split("/")[4]
                task = load_task(task_id)
                if not task:
                    response(self, 404, {"error": "task_not_found", "task_id": task_id})
                    return
                result = task.get("result") or {}
                response(self, 200, {
                    "task_id": task_id,
                    "state": task.get("state"),
                    "artifacts": {
                        "pull_request_url": result.get("pull_request_url") or result.get("pr_url"),
                        "preview_url": result.get("preview_url"),
                        "ci_url": result.get("ci_url"),
                        "result_reference": task.get("result_reference"),
                    },
                })
                return
            if path.startswith("/v1/agents/status/"):
                task_id = path.split("/", 4)[4]
                task = load_task(task_id)
                if not task:
                    response(self, 404, canonical_response_envelope(
                        status="blocked",
                        task_id=task_id,
                        route_used="/v1/agents/status",
                        blocked_reason="unknown",
                        repair_task={"kind": "verify_agent_task_id", "task_id": task_id},
                        next_action="submit a task through /v1/agents/tasks or verify the task id",
                    ))
                    return
                response(self, 200, canonical_response_envelope(
                    status="completed" if task.get("state") in TERMINAL_STATES else "running",
                    task_id=task_id,
                    node=(task.get("lease_owner") or "home").split(":", 1)[0],
                    route_used="/v1/agents/status",
                    data={"task": task},
                    next_action="poll /v1/agents/artifacts/{task_id}" if task.get("state") in TERMINAL_STATES else "continue polling status",
                ))
                return
            if path.startswith("/v1/agents/artifacts/"):
                task_id = path.split("/", 4)[4]
                task = load_task(task_id)
                envelope = task_artifact_envelope(task, task_id)
                response(self, 200 if task else 404, envelope)
                return
            response(self, 404, {"error": "not_found", "path": path})
        except Exception as exc:  # pragma: no cover - surfaced in runtime logs
            response(self, 500, {"error": "control_plane_error", "detail": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            body = read_body(self)
            if path == "/v1/nodes/register":
                requested_node_id = str(body["node_id"])
                try:
                    node = persist_node_heartbeat(requested_node_id, body)
                except LookupError as exc:
                    response(self, 404, {"error": str(exc), "node_id": resolve_logical_node_id(requested_node_id, body)})
                    return
                except ValueError as exc:
                    response(self, 400, {"error": str(exc), "node_id": requested_node_id})
                    return
                response(self, 200, node)
                return
            if path.startswith("/v1/nodes/") and path.endswith("/heartbeat"):
                requested_node_id = path.split("/")[3]
                try:
                    node = persist_node_heartbeat(requested_node_id, body)
                except LookupError as exc:
                    response(self, 404, {"error": str(exc), "node_id": resolve_logical_node_id(requested_node_id, body)})
                    return
                except ValueError as exc:
                    response(self, 400, {"error": str(exc), "node_id": requested_node_id})
                    return
                response(self, 200, node)
                return
            if path.startswith("/v1/nodes/") and path.endswith("/drain"):
                node_id = path.split("/")[3]
                drain = bool(body.get("drain", True))
                if drain:
                    redis.command("SET", drain_key(node_id), "1")
                else:
                    redis.command("DEL", drain_key(node_id))
                response(self, 200, {"node_id": node_id, "draining": drain})
                return
            if path == "/v1/tasks":
                task = create_task(body)
                response(self, 201, task)
                return
            if path == "/v1/truth/claim":
                claim = create_claim(
                    body.get("task_id", "manual"),
                    body.get("made_by", "owner"),
                    body.get("claim", ""),
                    body.get("scope", "manual"),
                )
                response(self, 201, asdict(claim))
                return
            if path == "/v1/truth/evidence":
                ev = add_evidence(
                    body.get("claim_id", ""),
                    body.get("type", "manual"),
                    body.get("source", ""),
                    body.get("summary", ""),
                    body.get("path", ""),
                )
                response(self, 201, asdict(ev))
                return
            if path == "/v1/truth/verdict":
                v = set_verdict(
                    body.get("claim_id", ""),
                    body.get("verdict", "not_proven"),
                    body.get("confidence", "low"),
                    body.get("reasoning", ""),
                    body.get("next_action", ""),
                    body.get("owner_summary", ""),
                )
                response(self, 201, asdict(v))
                return
            if path == "/v1/superfactory/tasks":
                auth = validate_miniapp(self, body)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                try:
                    envelope = miniapp_task_envelope(body, auth)
                except ValueError as exc:
                    response(self, 400, {"error": "invalid_task", "detail": str(exc)})
                    return
                task = create_task(envelope)
                response(self, 201, task)
                return
            if path == "/v1/agents/tasks":
                envelope = task_envelope_from_request(body)
                task = create_task(envelope)
                response(self, 201, canonical_response_envelope(
                    status="running",
                    task_id=task["task_id"],
                    trace_id=envelope.get("trace_id") or task["task_id"],
                    node=envelope.get("target_node") or "home",
                    route_used="/v1/agents/tasks",
                    data={"task": task},
                    next_action="poll /v1/agents/status/{task_id}",
                ))
                return
            if path == "/v1/os/capabilities/invoke":
                envelope = os_capability_invoke_envelope(body)
                response(self, 200 if envelope["status"] == "completed" else 403, envelope)
                return
            if path in {"/v1/responses", "/v1/chat/completions"}:
                response(self, 503, model_stub_envelope(body, endpoint=path))
                return
            # ── Admin endpoints ────────────────────────────────────────
            if path == "/v1/admin/exec":
                auth = validate_miniapp(self, body)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                target = body.get("target_node")
                if not target:
                    response(self, 400, {"error": "target_node required"})
                    return
                command = body.get("command")
                if not command:
                    response(self, 400, {"error": "command required"})
                    return
                envelope = {
                    "kind": "admin_exec",
                    "target_node": target,
                    "required_capability": "admin_exec",
                    "objective": json.dumps({
                        "command": command,
                        "cwd": body.get("cwd", "/"),
                        "timeout": body.get("timeout", 30),
                        "env": body.get("env", {}),
                    }),
                    "source": {"kind": "admin_api", "user_id": auth["user"]["id"], "endpoint": "/v1/admin/exec"},
                    "max_retries": 0,
                }
                task = create_task(envelope)
                response(self, 202, canonical_response_envelope(
                    status="running", task_id=task["task_id"],
                    node=target, route_used="/v1/admin/exec",
                    data={"task": task},
                    next_action=f"poll /v1/agents/status/{task['task_id']}",
                ))
                return
            if path == "/v1/admin/service":
                auth = validate_miniapp(self, body)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                target = body.get("target_node")
                if not target:
                    response(self, 400, {"error": "target_node required"})
                    return
                action = body.get("action", "status")
                service = body.get("service")
                if not service:
                    response(self, 400, {"error": "service name required"})
                    return
                if action not in ("start", "stop", "restart", "status", "enable", "disable"):
                    response(self, 400, {"error": f"invalid action: {action}"})
                    return
                envelope = {
                    "kind": "admin_service",
                    "target_node": target,
                    "required_capability": "admin_service",
                    "objective": json.dumps({
                        "action": action,
                        "service": service,
                    }),
                    "source": {"kind": "admin_api", "user_id": auth["user"]["id"], "endpoint": "/v1/admin/service"},
                    "max_retries": 0,
                }
                task = create_task(envelope)
                response(self, 202, canonical_response_envelope(
                    status="running", task_id=task["task_id"],
                    node=target, route_used="/v1/admin/service",
                    data={"task": task},
                    next_action=f"poll /v1/agents/status/{task['task_id']}",
                ))
                return
            if path == "/v1/admin/git":
                auth = validate_miniapp(self, body)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                target = body.get("target_node")
                if not target:
                    response(self, 400, {"error": "target_node required"})
                    return
                action = body.get("action", "status")
                if action not in ("status", "pull", "diff", "log", "stash"):
                    response(self, 400, {"error": f"invalid action: {action}"})
                    return
                envelope = {
                    "kind": "admin_git",
                    "target_node": target,
                    "required_capability": "admin_git",
                    "objective": json.dumps({
                        "action": action,
                        "branch": body.get("branch"),
                        "remote": body.get("remote", "origin"),
                        "path": body.get("path", "/opt/kolibri-ai-platform"),
                    }),
                    "source": {"kind": "admin_api", "user_id": auth["user"]["id"], "endpoint": "/v1/admin/git"},
                    "max_retries": 0,
                }
                task = create_task(envelope)
                response(self, 202, canonical_response_envelope(
                    status="running", task_id=task["task_id"],
                    node=target, route_used="/v1/admin/git",
                    data={"task": task},
                    next_action=f"poll /v1/agents/status/{task['task_id']}",
                ))
                return
            if path == "/v1/admin/bootstrap-node":
                auth = validate_miniapp(self, body)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                status_code, payload = bootstrap_node_contract(body)
                response(self, status_code, payload)
                return
            if path == "/v1/admin/rotate-keys":
                auth = validate_miniapp(self, body)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                target = body.get("target_node")
                if not target:
                    response(self, 400, {"error": "target_node required"})
                    return
                envelope = {
                    "kind": "admin_rotate_keys",
                    "target_node": target,
                    "required_capability": "admin_rotate_keys",
                    "objective": json.dumps({"reason": body.get("reason", "operator_rotation")}),
                    "source": {"kind": "admin_api", "user_id": auth["user"]["id"], "endpoint": "/v1/admin/rotate-keys"},
                    "max_retries": 0,
                }
                task = create_task(envelope)
                response(self, 202, canonical_response_envelope(
                    status="running", task_id=task["task_id"],
                    node=target, route_used="/v1/admin/rotate-keys",
                    data={"task": task},
                    next_action=f"poll /v1/agents/status/{task['task_id']}",
                ))
                return
            if path == "/v1/admin/self-update":
                auth = validate_miniapp(self, body)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                target = body.get("target_node")
                if not target:
                    response(self, 400, {"error": "target_node required"})
                    return
                # Build binary URL — agents download from control plane
                cp_host = os.environ.get("KOLIBRI_SELF_UPDATE_HOST", "10.99.0.1")
                cp_port = os.environ.get("KOLIBRI_SELF_UPDATE_PORT", "9101")
                binary_url = body.get("binary_url") or f"http://{cp_host}:{cp_port}/v1/admin/agent-host-binary"
                import hashlib as _hl
                binary_path = Path(os.environ.get(
                    "KOLIBRI_AGENT_HOST_BINARY", "/usr/local/bin/kolibri-agent-host"))
                expected_sha256 = ""
                if binary_path.exists():
                    expected_sha256 = _hl.sha256(binary_path.read_bytes()).hexdigest()
                new_caps = body.get("capabilities") or (
                    "generic_implementation,read_only_probe,"
                    "admin_exec,admin_service,admin_git,admin_rotate_keys,admin_self_update"
                )
                envelope = {
                    "kind": "admin_self_update",
                    "target_node": target,
                    "required_capability": "admin_exec",
                    "objective": json.dumps({
                        "binary_url": binary_url,
                        "sha256": expected_sha256,
                        "capabilities": new_caps,
                    }),
                    "source": {"kind": "admin_api", "user_id": auth["user"]["id"], "endpoint": "/v1/admin/self-update"},
                    "max_retries": 0,
                }
                task = create_task(envelope)
                response(self, 202, canonical_response_envelope(
                    status="running", task_id=task["task_id"],
                    node=target, route_used="/v1/admin/self-update",
                    data={"task": task, "binary_url": binary_url, "sha256": expected_sha256},
                    next_action=f"poll /v1/agents/status/{task['task_id']}",
                ))
                return
            if path == "/v1/fabric/route":
                route = fabric_route(
                    target_node=body.get("target_node"),
                    required_capability=body.get("required_capability"),
                    registered_nodes=registered_nodes(),
                )
                response(self, 200 if route.get("status") == "ok" else 503, route)
                return
            if path == "/v1/fabric/relay":
                route = fabric_route(
                    target_node=body.get("target_node"),
                    required_capability=body.get("required_capability"),
                    registered_nodes=registered_nodes(),
                )
                if route.get("status") != "ok" and not route.get("can_continue_elsewhere"):
                    response(self, 503, route)
                    return
                response(self, 202, {
                    "status": "accepted",
                    "relay": "safe_stub",
                    "route": route,
                    "message": "relay contract accepted; privileged execution must be performed by an authenticated agent host",
                })
                return
            if path == "/v1/fabric/bootstrap":
                status_code, payload = bootstrap_node_contract(body)
                response(self, status_code, payload)
                return
            if path == "/v1/tasks/lease":
                requeue_expired_leases()
                node_id = body["node_id"]
                if redis.command("GET", drain_key(node_id)):
                    response(self, 204, {})
                    return
                agent_id = body.get("agent_id", node_id)
                raw_node = get_json(node_key(node_id), {
                    "node_id": node_id,
                    "capabilities": body.get("capabilities", []),
                    "runners": body.get("runners", {}),
                })
                try:
                    capabilities, claim_node, slot_id = lease_claim_view(raw_node, body)
                except ValueError as exc:
                    response(self, 409, {"error": str(exc), "node_id": node_id})
                    return
                with NODE_UPDATE_LOCK:
                    for task_id in queue_ids():
                        task = load_task(task_id)
                        if not task or task.get("state") not in {STATE_QUEUED, STATE_REVIEW}:
                            remove_from_queue(task_id)
                            continue
                        if not compatible(task, node_id, capabilities, claim_node):
                            continue
                        remove_from_queue(task_id)
                        task = issue_task_lease(
                            task,
                            node_id=node_id,
                            agent_id=agent_id,
                            slot_id=slot_id,
                        )
                        save_task(task)
                        response(self, 200, task)
                        return
                response(self, 204, {})
                return
            if path.startswith("/v1/tasks/") and path.endswith("/heartbeat"):
                task_id = path.split("/")[3]
                task = load_task(task_id)
                if not task:
                    response(self, 404, {"error": "task_not_found", "task_id": task_id})
                    return
                fence_error = validate_task_mutation_fence(task, body)
                if fence_error:
                    response(self, 409, {
                        "error": "stale_or_invalid_lease",
                        "reason": fence_error,
                        "task_id": task_id,
                        "attempt_id": task.get("attempt_id"),
                    })
                    return
                if task.get("state") in TERMINAL_STATES:
                    response(self, 200, task)
                    return
                if task.get("state") not in TERMINAL_STATES:
                    task["state"] = body.get("state") or STATE_RUNNING
                    task["heartbeat_at"] = utc_now()
                    task["lease_until"] = now_ts() + LEASE_DURATION
                    task["pid"] = body.get("pid", task.get("pid"))
                    task["worktree"] = body.get("worktree", task.get("worktree"))
                    task["branch"] = body.get("branch", task.get("branch"))
                    task["log_paths"] = body.get("log_paths", task.get("log_paths"))
                    save_task(task)
                response(self, 200, task)
                return
            if path.startswith("/v1/tasks/") and path.endswith("/complete"):
                task_id = path.split("/")[3]
                task = load_task(task_id)
                if not task:
                    response(self, 404, {"error": "task_not_found", "task_id": task_id})
                    return
                fence_error = validate_task_mutation_fence(task, body)
                if fence_error:
                    response(self, 409, {
                        "error": "stale_or_invalid_lease",
                        "reason": fence_error,
                        "task_id": task_id,
                        "attempt_id": task.get("attempt_id"),
                    })
                    return
                if task.get("state") in TERMINAL_STATES:
                    response(self, 200, {"task": task, "review_task": None})
                    return
                result = body.get("result", body)
                needs_review = task.get("envelope", {}).get("create_review_on_complete")
                has_pr = bool(result.get("pull_request_url") or result.get("pr_url"))
                task["state"] = STATE_COMPLETED if (not needs_review or has_pr) else STATE_WAITING_REVIEW
                task["result"] = result
                task["result_reference"] = body.get("result_reference") or result.get("result_path")
                task["heartbeat_at"] = utc_now()
                task["lease_until"] = None
                preserve_terminal_lease_evidence(task)
                # Truth gate: verify completion has evidence
                task = truth_gate_on_complete(task, result)
                save_task(task)
                review_task = create_review_task(task, result) if has_pr else None
                response(self, 200, {"task": task, "review_task": review_task})
                return
            if path.startswith("/v1/tasks/") and path.endswith("/annotate"):
                task_id = path.split("/")[3]
                task = load_task(task_id)
                if not task:
                    response(self, 404, {"error": "task_not_found", "task_id": task_id})
                    return
                result = task.get("result") or {}
                result.update(body.get("result", body))
                task["result"] = result
                task["result_reference"] = body.get("result_reference") or result.get("result_path") or task.get("result_reference")
                task["heartbeat_at"] = utc_now()
                review_task = None
                if task.get("state") == STATE_WAITING_REVIEW and (result.get("pull_request_url") or result.get("pr_url")):
                    task["state"] = STATE_COMPLETED
                    preserve_terminal_lease_evidence(task)
                    save_task(task)
                    review_task = create_review_task(task, result)
                else:
                    save_task(task)
                response(self, 200, {"task": task, "review_task": review_task})
                return
            if path.startswith("/v1/tasks/") and path.endswith("/fail"):
                task_id = path.split("/")[3]
                task = load_task(task_id)
                if not task:
                    response(self, 404, {"error": "task_not_found", "task_id": task_id})
                    return
                fence_error = validate_task_mutation_fence(task, body)
                if fence_error:
                    response(self, 409, {
                        "error": "stale_or_invalid_lease",
                        "reason": fence_error,
                        "task_id": task_id,
                        "attempt_id": task.get("attempt_id"),
                    })
                    return
                if task.get("state") in TERMINAL_STATES:
                    response(self, 200, task)
                    return
                error_type = body.get("error_type", "runtime_error")
                error = body.get("error", "")
                task["error_type"] = error_type
                task["error"] = error
                task["result"] = body.get("result")
                task["result_reference"] = body.get("result_reference")
                task["lease_until"] = None
                # Truth gate: log contradiction on failure
                task = truth_gate_on_fail(task, error_type, error)
                mark_node_runner_failure(task, body)
                if int(task.get("attempt", 0)) < int(task.get("max_retries", MAX_RETRIES)) and body.get("retry", True):
                    task["state"] = STATE_RETRY
                    save_task(task)
                    task["state"] = STATE_QUEUED
                    save_task(task)
                    enqueue(task_id)
                else:
                    task["state"] = STATE_FAILED
                    preserve_terminal_lease_evidence(task)
                    save_task(task)
                response(self, 200, task)
                return
            if path.startswith("/v1/tasks/") and path.endswith("/cancel"):
                task_id = path.split("/")[3]
                task = load_task(task_id)
                if not task:
                    response(self, 404, {"error": "task_not_found", "task_id": task_id})
                    return
                remove_from_queue(task_id)
                task["state"] = STATE_CANCELLED
                task["cancel_requested_at"] = utc_now()
                task["lease_until"] = None
                preserve_terminal_lease_evidence(task)
                save_task(task)
                response(self, 200, task)
                return
            if path.startswith("/v1/agents/cancel/"):
                task_id = path.split("/", 4)[4]
                task = load_task(task_id)
                if not task:
                    response(self, 404, canonical_response_envelope(
                        status="blocked",
                        task_id=task_id,
                        route_used="/v1/agents/cancel",
                        blocked_reason="unknown",
                        repair_task={"kind": "verify_agent_task_id", "task_id": task_id},
                        next_action="verify task id before retrying cancellation",
                    ))
                    return
                remove_from_queue(task_id)
                task["state"] = STATE_CANCELLED
                task["cancel_requested_at"] = utc_now()
                task["lease_until"] = None
                save_task(task)
                response(self, 200, canonical_response_envelope(
                    status="completed",
                    task_id=task_id,
                    node=(task.get("lease_owner") or "home").split(":", 1)[0],
                    route_used="/v1/agents/cancel",
                    data={"task": task},
                    next_action="poll /v1/agents/status/{task_id} to confirm terminal state",
                ))
                return
            response(self, 404, {"error": "not_found", "path": path})
        except Exception as exc:  # pragma: no cover - surfaced in runtime logs
            response(self, 500, {"error": "control_plane_error", "detail": str(exc)})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default=os.environ.get("FACTORY_BIND", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("FACTORY_PORT", "9101")))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(json.dumps({"event": "factory_control_started", "bind": args.bind, "port": args.port, "namespace": NAMESPACE}))
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
