#!/usr/bin/env python3
"""Minimal Kolibri Factory control plane sidecar.

The sidecar intentionally uses only the Python standard library. It stores all
task and node state in the existing local Redis server through a tiny RESP
client so it can run next to the legacy control plane without adding packages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sys
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
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
    "not_found",
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
BLOCKED_RUNNER_STATES = {"blocked", "degraded", "runner_auth_blocked", "unavailable"}
DEFAULT_MIMO_TASK_KINDS = {"owner_remote_task", "direct_mimo", "mimo_direct", "mimo_task"}
OWNER_NOTIFICATION_STATUSES = {"pending", "delivered", "failed"}
OWNER_NOTIFICATION_SEVERITIES = {"info", "success", "warning", "critical"}
TOKEN_LIKE_RE = re.compile(
    r"(?i)(?:\b\d{6,}:[A-Za-z0-9_-]{20,}\b|\b(?:ghp|github_pat|xox[baprs]|sk)-[A-Za-z0-9_-]{16,}\b)"
)
SECRET_FIELD_HINTS = ("authorization", "cookie", "key", "password", "secret", "token")

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
        "role": "control_plane",
        "display_name": "Директор",
        "api_paths": ["fabric_api", "control_plane_api", "artifact_api"],
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

PROMPT3_REQUIRED_ENDPOINTS = {
    "GET": [
        "/v1/health",
        "/v1/fleet/nodes",
        "/v1/fleet/topology",
        "/v1/fleet/route",
        "/v1/fleet/capabilities",
        "/v1/filesystem",
        "/v1/models",
        "/v1/agents/status/{task_id}",
        "/v1/agents/artifacts/{task_id}",
        "/v1/owner/notifications",
    ],
    "POST": [
        "/v1/responses",
        "/v1/chat/completions",
        "/v1/agents/tasks",
        "/v1/agents/cancel/{task_id}",
        "/v1/owner/notifications",
        "/v1/owner/notifications/{notification_id}/ack",
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


def get_json(redis_key: str, default: Any = None) -> Any:
    raw = redis.command("GET", redis_key)
    if raw is None:
        return default
    return json.loads(raw)


def set_json(redis_key: str, value: Any) -> None:
    redis.command("SET", redis_key, json.dumps(value, sort_keys=True, separators=(",", ":")))


def task_key(task_id: str) -> str:
    return key(f"task:{task_id}")


def node_key(node_id: str) -> str:
    return key(f"node:{node_id}")


def owner_notification_key(notification_id: str) -> str:
    return key(f"owner_notification:{notification_id}")


def owner_notification_idempotency_key(idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    return key(f"owner_notification_idem:{digest}")


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


def all_owner_notification_ids() -> list[str]:
    values = redis.command("SMEMBERS", key("owner_notification_ids")) or []
    return sorted(values)


def registered_nodes() -> list[dict[str, Any]]:
    nodes = []
    for node_id in sorted(redis.command("SMEMBERS", key("node_ids")) or []):
        node = get_json(node_key(node_id), {})
        node["draining"] = bool(redis.command("GET", drain_key(node_id)))
        nodes.append(node)
    return nodes


def queue_ids() -> list[str]:
    return redis.command("LRANGE", key("queue"), 0, -1) or []


def load_task(task_id: str) -> dict[str, Any] | None:
    return get_json(task_key(task_id))


def load_owner_notification(notification_id: str) -> dict[str, Any] | None:
    return get_json(owner_notification_key(notification_id))


def redact_secret_like_text(text: str) -> str:
    return TOKEN_LIKE_RE.sub("[redacted]", text)


def contains_secret_field(body: dict[str, Any]) -> bool:
    for name, value in body.items():
        lowered = str(name).lower()
        if any(hint in lowered for hint in SECRET_FIELD_HINTS):
            if value not in (None, "", False):
                return True
    return False


def owner_notification_from_request(body: dict[str, Any]) -> dict[str, Any]:
    text = str(body.get("message") or body.get("text") or body.get("summary") or "").strip()
    if not text:
        raise ValueError("message is required")
    severity = str(body.get("severity") or "info").strip().lower()
    if severity not in OWNER_NOTIFICATION_SEVERITIES:
        severity = "info"
    source_node = str(body.get("source_node") or body.get("node_id") or "unknown").strip() or "unknown"
    task_id = str(body.get("task_id") or "").strip()
    redacted_text = redact_secret_like_text(text)[:3900]
    base_idem = body.get("idempotency_key") or f"{source_node}:{task_id}:{hashlib.sha256(redacted_text.encode('utf-8')).hexdigest()}"
    notification_id = str(body.get("notification_id") or f"OWNOTIFY-{uuid.uuid4().hex[:12]}")
    return {
        "notification_id": notification_id,
        "idempotency_key": str(base_idem),
        "channel": "telegram_owner",
        "delivery_state": "pending",
        "severity": severity,
        "source_node": source_node,
        "source_agent": body.get("source_agent") or body.get("agent_id") or "",
        "task_id": task_id,
        "title": redact_secret_like_text(str(body.get("title") or "")).strip()[:160],
        "message": redacted_text,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "secrets_redacted": redacted_text != text or contains_secret_field(body),
        "secrets_returned": False,
        "secret_ref": "telegram_owner_bot_token",
    }


def create_owner_notification(body: dict[str, Any]) -> dict[str, Any]:
    notification = owner_notification_from_request(body)
    idem_key = owner_notification_idempotency_key(notification["idempotency_key"])
    existing = redis.command("GET", idem_key)
    if existing:
        existing_notification = load_owner_notification(existing)
        if existing_notification:
            return existing_notification
    set_json(owner_notification_key(notification["notification_id"]), notification)
    redis.command("SADD", key("owner_notification_ids"), notification["notification_id"])
    redis.command("SET", idem_key, notification["notification_id"])
    return notification


def list_owner_notifications(state: str = "pending", limit: int = 50) -> list[dict[str, Any]]:
    if state not in OWNER_NOTIFICATION_STATUSES:
        state = "pending"
    notifications = []
    for notification_id in all_owner_notification_ids():
        notification = load_owner_notification(notification_id)
        if not notification or notification.get("delivery_state") != state:
            continue
        notifications.append(notification)
    notifications.sort(key=lambda item: str(item.get("created_at") or ""))
    return notifications[: max(1, min(limit, 100))]


def ack_owner_notification(notification_id: str, body: dict[str, Any]) -> dict[str, Any] | None:
    notification = load_owner_notification(notification_id)
    if not notification:
        return None
    delivered = body.get("delivered", True)
    notification["delivery_state"] = "delivered" if delivered else "failed"
    notification["updated_at"] = utc_now()
    notification["delivery"] = {
        "gateway": body.get("gateway") or "telegram_gateway",
        "delivered": bool(delivered),
        "error": redact_secret_like_text(str(body.get("error") or ""))[:500],
    }
    set_json(owner_notification_key(notification_id), notification)
    return notification


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
        "node": node or "main",
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
    envelope.setdefault("command_node", body.get("command_node") or body.get("source") or "unknown")
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
    edges = [{"from": "home", "to": "main", "type": "command_api"}]
    edges.extend(
        {"from": "main", "to": node["node_id"], "type": "protected_fabric_api"}
        for node in nodes
        if node["node_id"] != "main"
    )
    return {
        "nodes": nodes,
        "edges": edges,
        "relay_endpoint": "/v1/fabric/relay",
    }


def namespace_segment(value: str, fallback: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "_.-" else "-" for ch in value.strip())
    return safe or fallback


def safe_filesystem_root(
    node_id: str,
    node_namespace: str,
    root: dict[str, Any],
    *,
    include_paths: bool = False,
) -> dict[str, Any]:
    name = namespace_segment(str(root.get("name") or "root"), "root")
    safe_root: dict[str, Any] = {
        "name": name,
        "namespace": root.get("namespace") or f"{node_namespace}/{name}",
        "purpose": root.get("purpose") or "node filesystem root",
        "exists": bool(root.get("exists")),
        "writable": bool(root.get("writable")),
    }
    if isinstance(root.get("disk"), dict):
        safe_root["disk"] = root["disk"]
    if include_paths and root.get("path"):
        safe_root["path"] = str(root["path"])
    if not safe_root["exists"]:
        safe_root["repair_task"] = {
            "kind": "repair_filesystem_root",
            "node_id": node_id,
            "root": name,
            "action": "restore the declared node-local root or update the node filesystem manifest",
        }
    return safe_root


def filesystem_namespace(nodes: list[dict[str, Any]], *, include_paths: bool = False) -> dict[str, Any]:
    """Return the federated filesystem namespace from node-published manifests.

    The Control Plane must never walk remote disks here. It only aggregates
    metadata that Agent Hosts already heartbeat in their node cards.
    """

    namespace_nodes = []
    flat_roots = []
    repair_tasks = []
    current = now_ts()
    for raw_node in nodes:
        node = classify_node_freshness(raw_node, current)
        node_id = str(node.get("node_id") or node.get("id") or "unknown")
        filesystem = node.get("filesystem") if isinstance(node.get("filesystem"), dict) else {}
        node_namespace = filesystem.get("namespace_prefix") or f"/kolibri/nodes/{namespace_segment(node_id, 'node')}"
        roots = []
        for root in ensure_list(filesystem.get("roots")):
            if not isinstance(root, dict):
                continue
            safe_root = safe_filesystem_root(node_id, node_namespace, root, include_paths=include_paths)
            roots.append(safe_root)
            flat_roots.append({"node_id": node_id, **safe_root})
            if safe_root.get("repair_task"):
                repair_tasks.append(safe_root["repair_task"])
        missing_manifest = not filesystem
        if missing_manifest:
            repair_tasks.append({
                "kind": "repair_node_filesystem_manifest",
                "node_id": node_id,
                "action": "restart or upgrade Agent Host so heartbeat includes filesystem.namespace_prefix and roots",
            })
        namespace_nodes.append({
            "node_id": node_id,
            "health": node.get("health"),
            "freshness": node.get("freshness"),
            "heartbeat_age_seconds": node.get("heartbeat_age_seconds"),
            "namespace_prefix": node_namespace,
            "mode": filesystem.get("mode") or "mesh_api_namespace",
            "write_policy": filesystem.get("write_policy") or "node-local writes only; no shared writable root disk; shared roots require leases",
            "missing_manifest": missing_manifest,
            "roots": roots,
        })
    counts = {
        "nodes_total": len(namespace_nodes),
        "nodes_with_filesystem": sum(1 for node in namespace_nodes if not node["missing_manifest"]),
        "nodes_missing_filesystem": sum(1 for node in namespace_nodes if node["missing_manifest"]),
        "roots_total": len(flat_roots),
        "writable_roots": sum(1 for root in flat_roots if root.get("writable")),
    }
    return {
        "mode": "mesh_api_namespace",
        "namespace_prefix": "/kolibri/nodes",
        "write_policy": "node-local writes only; no shared writable root disk; shared roots require leases",
        "counts": counts,
        "nodes": namespace_nodes,
        "roots": flat_roots,
        "repair_tasks": repair_tasks,
        "metadata_only": True,
        "local_paths_included": include_paths,
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
        node=body.get("target_node") or "main",
        route_used=endpoint,
        blocked_reason="admin_scope_denied",
        repair_task={
            "kind": "request_admin_scope",
            "endpoint": endpoint,
            "action": "obtain authenticated owner scope and audited approval before privileged execution",
        },
        next_action="resubmit with an authenticated admin capability token through the protected Fabric API",
    )


def not_found_envelope(path: str, *, method: str) -> dict[str, Any]:
    return canonical_response_envelope(
        status="blocked",
        route_used=path,
        blocked_reason="not_found",
        repair_task={
            "kind": "repair_fabric_api_route",
            "method": method,
            "path": path,
            "action": "verify the endpoint contract, deploy the matching Control Plane build, or use a listed Fabric fallback route",
        },
        next_action="check /v1/health, /v1/fleet/route, and the API contract before retrying this route",
        data={"error": "not_found", "method": method, "path": path},
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
        node=(task.get("lease_owner") or "main").split(":", 1)[0],
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


def save_task(task: dict[str, Any]) -> None:
    task["updated_at"] = utc_now()
    set_json(task_key(task["task_id"]), task)
    redis.command("SADD", key("task_ids"), task["task_id"])


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
        "attempt_id": None,
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


def task_envelope_value(task: dict[str, Any], *names: str, default: Any = None) -> Any:
    envelope = task.get("envelope") if isinstance(task.get("envelope"), dict) else {}
    for name in names:
        value = task.get(name)
        if value not in (None, "", []):
            return value
        value = envelope.get(name)
        if value not in (None, "", []):
            return value
    return default


def effective_task_runner(task: dict[str, Any]) -> str | None:
    runner = task_envelope_value(task, "runner")
    kind = str(task_envelope_value(task, "kind", default=task.get("kind") or "") or "").strip().lower()
    if runner is None and kind in DEFAULT_MIMO_TASK_KINDS:
        runner = "mimo"
    if runner is None:
        return None
    normalized = str(runner).strip().lower()
    return normalized or None


def repair_slug(value: Any) -> str:
    parts = []
    current = []
    for char in str(value or "runtime_error").lower():
        if char.isalnum():
            current.append(char)
        elif current:
            parts.append("".join(current))
            current = []
    if current:
        parts.append("".join(current))
    return "_".join(parts) or "runtime_error"


def is_auto_repair_task(task: dict[str, Any]) -> bool:
    kind = str(task_envelope_value(task, "kind", default=task.get("kind") or "") or "").strip().lower()
    idempotency_key = str(task.get("idempotency_key") or "")
    return (
        kind.startswith("repair_")
        or bool(task_envelope_value(task, "auto_repair", "repair_for_task_id"))
        or idempotency_key.startswith("repair:")
    )


def failure_result(task: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    for value in (body.get("result"), task.get("result")):
        if isinstance(value, dict):
            return value
    return {}


def failure_repair_kind(error_type: str, result: dict[str, Any]) -> str:
    missing_artifacts = ensure_list(result.get("required_artifacts_missing"))
    if error_type == "runner_contract_blocked" and missing_artifacts:
        return "repair_required_artifacts"
    if error_type == "runner_contract_blocked":
        return "repair_runner_contract"
    if error_type == "lease_expired":
        return "repair_expired_lease"
    return "repair_failed_task"


def failure_repair_task_envelope(task: dict[str, Any], body: dict[str, Any]) -> dict[str, Any] | None:
    if is_auto_repair_task(task):
        return None
    source_task_id = str(task.get("task_id") or "")
    if not source_task_id:
        return None
    result = failure_result(task, body)
    error_type = str(body.get("error_type") or task.get("error_type") or "runtime_error")
    error = body.get("error") or task.get("error") or result.get("failure_reason") or error_type
    missing_artifacts = [str(item) for item in ensure_list(result.get("required_artifacts_missing")) if str(item)]
    repair_kind = failure_repair_kind(error_type, result)
    slug = repair_slug(error_type).upper()
    envelope = task.get("envelope") if isinstance(task.get("envelope"), dict) else {}
    target_node = task_envelope_value(task, "repair_target_node", "target_node", "required_node")
    if not target_node and error_type == "runner_contract_blocked":
        lease_owner = str(task.get("lease_owner") or "")
        target_node = lease_owner.split(":", 1)[0] if lease_owner else None
    runner = task_envelope_value(task, "repair_runner", "runner") or effective_task_runner(task) or "mimo"
    required_capability = task_envelope_value(task, "repair_required_capability", "required_capability")
    objective = (
        f"Repair failed Kolibri AI factory task {source_task_id}. "
        f"Failure type: {error_type}. Error: {error}. "
        "Produce a bounded repair result and state the safe rerun path through the Fabric API."
    )
    acceptance = [
        f"Inspect source task {source_task_id}, its result_reference, and failure payload without bypassing Control Plane contracts.",
        "Classify whether the task can be repaired automatically or needs operator/manual intervention.",
        "Return a RESULT/NEXT style artifact or structured response with the exact rerun, cancel, or operator action.",
    ]
    if missing_artifacts:
        acceptance.insert(1, f"Produce or correct missing required artifacts: {', '.join(missing_artifacts)}.")
    repair_envelope: dict[str, Any] = {
        "task_id": f"{source_task_id}-REPAIR-{slug}",
        "idempotency_key": f"repair:{source_task_id}:{repair_slug(error_type)}",
        "kind": "owner_remote_task",
        "source": "control_plane_auto_repair",
        "auto_repair": True,
        "repair_for_task_id": source_task_id,
        "repair": {
            "kind": repair_kind,
            "source_task_id": source_task_id,
            "source_task_kind": task.get("kind") or envelope.get("kind"),
            "error_type": error_type,
            "error": error,
            "blocked_reason": result.get("blocked_reason") or error,
            "required_artifacts_missing": missing_artifacts,
            "result_reference": body.get("result_reference") or task.get("result_reference"),
        },
        "objective": objective,
        "acceptance": acceptance,
        "runner": str(runner),
        "max_retries": 1,
        "control_center": {
            "surface": ["incidents", "tasks"],
            "incident_type": "task_failed",
            "manual_intervention_candidate": bool(result.get("manual_intervention_required")),
        },
    }
    if target_node:
        repair_envelope["target_node"] = target_node
    if required_capability:
        repair_envelope["required_capability"] = required_capability
    for key_name in ("branch", "base_ref", "write_scope", "allowed_files"):
        if envelope.get(key_name):
            repair_envelope[key_name] = envelope[key_name]
    return repair_envelope


def create_failure_repair_task(task: dict[str, Any], body: dict[str, Any]) -> dict[str, Any] | None:
    repair_envelope = failure_repair_task_envelope(task, body)
    if not repair_envelope:
        return None
    repair_task = create_task(repair_envelope)
    repair = repair_envelope["repair"]
    task["repair_task_id"] = repair_task["task_id"]
    task["repair_task"] = {
        "task_id": repair_task["task_id"],
        "state": repair_task.get("state"),
        "kind": repair["kind"],
        "idempotency_key": repair_envelope["idempotency_key"],
        "source_task_id": task["task_id"],
        "required_artifacts_missing": repair.get("required_artifacts_missing", []),
    }
    return repair_task


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
    runners = node.get("runners") if isinstance(node.get("runners"), dict) else {}
    runners[str(runner)] = {
        "status": "blocked" if error_type == "runner_auth_blocked" else "unavailable",
        "error_type": error_type,
        "updated_at": utc_now(),
    }
    node["runners"] = runners
    set_json(node_key(node_id), node)


def compatible(task: dict[str, Any], node_id: str, capabilities: list[str], node: dict[str, Any] | None = None) -> bool:
    target_node = task_envelope_value(task, "target_node", "required_node")
    if target_node and target_node != node_id:
        return False
    allowed = task_envelope_value(task, "allowed_nodes")
    if allowed and node_id not in allowed:
        return False
    avoided = set(str(item) for item in ensure_list(task_envelope_value(task, "avoid_nodes", "avoided_nodes")))
    if node_id in avoided:
        return False
    required = task_envelope_value(task, "required_capability")
    if required and required not in capabilities:
        return False
    runner = effective_task_runner(task)
    if runner:
        node_state = runner_state(node or {}, runner)
        if node_state in BLOCKED_RUNNER_STATES:
            return False
        if not runner_capability_names(runner).intersection(set(capabilities)):
            return False
    return True


def requeue_expired_leases() -> None:
    current = now_ts()
    for task_id in all_task_ids():
        task = load_task(task_id)
        if not task or task.get("state") not in {STATE_LEASED, STATE_RUNNING, STATE_REVIEW}:
            continue
        lease_until = float(task.get("lease_until") or 0)
        if lease_until >= current:
            continue
        if int(task.get("attempt", 0)) < int(task.get("max_retries", MAX_RETRIES)):
            task["state"] = STATE_RETRY
            task["lease_owner"] = None
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
            create_failure_repair_task(task, {
                "error_type": task["error_type"],
                "error": task["error"],
                "retry": False,
            })
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
                    node="main",
                    route_used="/v1/health",
                    data={"redis": pong, "queue_backend": "redis", "time": utc_now(), "fabric_api_version": FABRIC_API_VERSION},
                    next_action="use /v1/fleet/route before dispatching work to a node",
                ))
                return
            if path == "/v1/superfactory/status":
                auth = validate_miniapp(self)
                if not auth.get("ok"):
                    response(self, 401, {"error": auth.get("error", "unauthorized")})
                    return
                response(self, 200, superfactory_status())
                return
            if path == "/v1/nodes":
                nodes = []
                current = now_ts()
                for node_id in sorted(redis.command("SMEMBERS", key("node_ids")) or []):
                    node = get_json(node_key(node_id), {})
                    node["draining"] = bool(redis.command("GET", drain_key(node_id)))
                    nodes.append(classify_node_freshness(node, current))
                counts = node_health_counts(nodes)
                response(self, 200, {"nodes": nodes, "counts": counts, "freshness": counts})
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
                    node=route.get("route", {}).get("target_node") or route.get("target_node") or "main",
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
            if path in {"/v1/filesystem", "/v1/fleet/filesystem"}:
                query = parse_qs(parsed.query)
                include_paths = str(query.get("include_paths", ["false"])[0]).lower() in {"1", "true", "yes"}
                namespace = filesystem_namespace(registered_nodes(), include_paths=include_paths)
                response(self, 200, canonical_response_envelope(
                    status="completed",
                    route_used=path,
                    data=namespace,
                    repair_task=namespace["repair_tasks"],
                    next_action="use namespace paths for artifact discovery; request include_paths=true only for authenticated diagnostics",
                ))
                return
            if path == "/v1/models":
                response(self, 200, canonical_response_envelope(
                    status="completed",
                    route_used="/v1/models",
                    data={"object": "list", "data": MODEL_CATALOG},
                    next_action="model generation endpoints remain safe stubs until authenticated model routes are online",
                ))
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
                tasks = [load_task(task_id) for task_id in all_task_ids()]
                tasks = [task for task in tasks if task and (wanted is None or task.get("state") == wanted)]
                response(self, 200, {"tasks": tasks, "queue": queue_ids()})
                return
            if path == "/v1/owner/notifications":
                query = parse_qs(parsed.query)
                state = query.get("state", ["pending"])[0]
                try:
                    limit = int(query.get("limit", ["50"])[0])
                except ValueError:
                    limit = 50
                notifications = list_owner_notifications(state=state, limit=limit)
                response(self, 200, canonical_response_envelope(
                    status="completed",
                    route_used="/v1/owner/notifications",
                    data={"notifications": notifications},
                    next_action="telegram gateway should deliver pending notifications and ack them",
                ))
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
                    node=(task.get("lease_owner") or "main").split(":", 1)[0],
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
            response(self, 404, not_found_envelope(path, method="GET"))
        except Exception as exc:  # pragma: no cover - surfaced in runtime logs
            response(self, 500, {"error": "control_plane_error", "detail": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            body = read_body(self)
            if path == "/v1/nodes/register":
                node_id = body["node_id"]
                node = {
                    "node_id": node_id,
                    "hostname": body.get("hostname"),
                    "capabilities": body.get("capabilities", []),
                    "runners": body.get("runners", {}),
                    "health": "online",
                    "heartbeat_at": utc_now(),
                    "pid": body.get("pid"),
                    "cpu": body.get("cpu"),
                    "ram": body.get("ram"),
                    "disk": body.get("disk"),
                    "agent_id": body.get("agent_id"),
                }
                set_json(node_key(node_id), node)
                redis.command("SADD", key("node_ids"), node_id)
                response(self, 200, node)
                return
            if path.startswith("/v1/nodes/") and path.endswith("/heartbeat"):
                node_id = path.split("/")[3]
                node = get_json(node_key(node_id), {"node_id": node_id})
                node.update(body)
                node["health"] = "online"
                node["heartbeat_at"] = utc_now()
                set_json(node_key(node_id), node)
                redis.command("SADD", key("node_ids"), node_id)
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
                    node=envelope.get("target_node") or "main",
                    route_used="/v1/agents/tasks",
                    data={"task": task},
                    next_action="poll /v1/agents/status/{task_id}",
                ))
                return
            if path == "/v1/owner/notifications":
                try:
                    notification = create_owner_notification(body)
                except ValueError as exc:
                    response(self, 400, canonical_response_envelope(
                        status="blocked",
                        route_used="/v1/owner/notifications",
                        blocked_reason="unknown",
                        data={"error": str(exc), "secrets_returned": False},
                        next_action="resubmit with a non-empty message and without raw secrets",
                    ))
                    return
                response(self, 201, canonical_response_envelope(
                    status="completed",
                    task_id=notification.get("task_id") or notification["notification_id"],
                    route_used="/v1/owner/notifications",
                    data={"notification": notification},
                    next_action="telegram gateway will deliver this through its configured secret_ref",
                ))
                return
            if path.startswith("/v1/owner/notifications/") and path.endswith("/ack"):
                notification_id = path.split("/")[4]
                notification = ack_owner_notification(notification_id, body)
                if not notification:
                    response(self, 404, canonical_response_envelope(
                        status="blocked",
                        task_id=notification_id,
                        route_used="/v1/owner/notifications/{notification_id}/ack",
                        blocked_reason="not_found",
                        next_action="verify notification_id before retrying ack",
                    ))
                    return
                response(self, 200, canonical_response_envelope(
                    status="completed",
                    task_id=notification.get("task_id") or notification_id,
                    route_used="/v1/owner/notifications/{notification_id}/ack",
                    data={"notification": notification},
                ))
                return
            if path in {"/v1/responses", "/v1/chat/completions"}:
                response(self, 503, model_stub_envelope(body, endpoint=path))
                return
            if path in ADMIN_ENDPOINTS:
                response(self, 403, admin_denied_envelope(body, endpoint=path))
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
                required = set(BOOTSTRAP_CONTRACT["required_fields"])
                missing = sorted(field for field in required if not body.get(field))
                if missing:
                    response(self, 400, {
                        "status": "blocked",
                        "reason": "bootstrap_contract_missing_fields",
                        "missing_fields": missing,
                        "fallback_nodes": [],
                        "repair_task": {
                            "kind": "repair_bootstrap_request",
                            "action": "resubmit bootstrap request with required non-secret identity and capability fields",
                        },
                        "can_continue_elsewhere": False,
                    })
                    return
                response(self, 202, {
                    "status": "accepted",
                    "bootstrap": "safe_stub",
                    "node_id": body["node_id"],
                    "display_name": body.get("display_name"),
                    "capabilities": body.get("capabilities", []),
                    "next_action": "approve scoped credentials through authenticated Fabric API and start agent-host registration",
                    "secrets_returned": False,
                })
                return
            if path == "/v1/tasks/lease":
                requeue_expired_leases()
                node_id = body["node_id"]
                if redis.command("GET", drain_key(node_id)):
                    response(self, 204, {})
                    return
                capabilities = body.get("capabilities", [])
                agent_id = body.get("agent_id", node_id)
                node = get_json(node_key(node_id), {"node_id": node_id, "capabilities": capabilities})
                if isinstance(body.get("runners"), dict):
                    node["runners"] = body["runners"]
                    set_json(node_key(node_id), node)
                for task_id in queue_ids():
                    task = load_task(task_id)
                    if not task or task.get("state") not in {STATE_QUEUED, STATE_REVIEW}:
                        remove_from_queue(task_id)
                        continue
                    if not compatible(task, node_id, capabilities, node):
                        continue
                    remove_from_queue(task_id)
                    task["state"] = STATE_LEASED
                    task["attempt"] = int(task.get("attempt", 0)) + 1
                    task["attempt_id"] = f"{task_id}-attempt-{task['attempt']}"
                    task["lease_owner"] = f"{node_id}:{agent_id}"
                    task["lease_until"] = now_ts() + LEASE_DURATION
                    task["heartbeat_at"] = utc_now()
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
                result = body.get("result", body)
                needs_review = task.get("envelope", {}).get("create_review_on_complete")
                has_pr = bool(result.get("pull_request_url") or result.get("pr_url"))
                task["state"] = STATE_COMPLETED if (not needs_review or has_pr) else STATE_WAITING_REVIEW
                task["result"] = result
                task["result_reference"] = body.get("result_reference") or result.get("result_path")
                task["heartbeat_at"] = utc_now()
                task["lease_until"] = None
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
                task["error_type"] = body.get("error_type", "runtime_error")
                task["error"] = body.get("error")
                task["result"] = body.get("result")
                task["result_reference"] = body.get("result_reference")
                task["lease_until"] = None
                mark_node_runner_failure(task, body)
                if int(task.get("attempt", 0)) < int(task.get("max_retries", MAX_RETRIES)) and body.get("retry", True):
                    task["state"] = STATE_RETRY
                    save_task(task)
                    task["state"] = STATE_QUEUED
                    save_task(task)
                    enqueue(task_id)
                else:
                    task["state"] = STATE_FAILED
                    create_failure_repair_task(task, body)
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
                    node=(task.get("lease_owner") or "main").split(":", 1)[0],
                    route_used="/v1/agents/cancel",
                    data={"task": task},
                    next_action="poll /v1/agents/status/{task_id} to confirm terminal state",
                ))
                return
            response(self, 404, not_found_envelope(path, method="POST"))
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
