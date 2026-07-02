#!/usr/bin/env python3
"""Minimal Kolibri Factory control plane sidecar.

The sidecar intentionally uses only the Python standard library. It stores all
task and node state in the existing local Redis server through a tiny RESP
client so it can run next to the legacy control plane without adding packages.
"""

from __future__ import annotations

import argparse
import json
import os
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

OWNER_SERVER_CATALOG = [
    {"node_id": "home", "role": "owner_gateway", "repair_capability": "devops"},
    {"node_id": "main", "role": "control_plane", "repair_capability": "devops"},
    {"node_id": "uiap", "role": "rag_knowledge_node", "repair_capability": "devops"},
    {"node_id": "qjns", "role": "tools_executor", "repair_capability": "devops"},
    {"node_id": "9fts", "role": "inference_implementation_worker", "repair_capability": "devops"},
    {"node_id": "new", "role": "review_worker", "repair_capability": "devops"},
    {"node_id": "primary-candidate", "role": "control_standby", "repair_capability": "devops"},
    {"node_id": "agent-01", "role": "backend_worker", "repair_capability": "devops"},
    {"node_id": "agent-02", "role": "frontend_worker", "repair_capability": "devops"},
    {"node_id": "agent-03", "role": "infra_worker", "repair_capability": "devops"},
    {"node_id": "agent-04", "role": "qa_browser_worker", "repair_capability": "devops"},
    {"node_id": "agent-05", "role": "security_worker", "repair_capability": "devops"},
    {"node_id": "agent-06", "role": "docs_knowledge_worker", "repair_capability": "devops"},
    {"node_id": "agent-07", "role": "formulalm_eval_worker", "repair_capability": "devops"},
    {"node_id": "agent-08", "role": "rag_eval_worker", "repair_capability": "devops"},
    {"node_id": "agent-09", "role": "release_canary_worker", "repair_capability": "devops"},
    {"node_id": "highload", "role": "ci_build_highload", "repair_capability": "devops"},
    {"node_id": "paris", "role": "paris_build_reserve", "repair_capability": "devops"},
    {"node_id": "reserve242", "role": "qa_security_reserve", "repair_capability": "devops"},
    {"node_id": "server-kfrm", "role": "heavy_tests_formulalm_candidate", "repair_capability": "devops"},
]

OWNER_SERVER_IDENTITY_ALIASES = {
    "9fts": ["mesh-9fts"],
    "agent-01": ["mesh-agent-01"],
    "agent-02": ["mesh-agent-02"],
    "agent-03": ["mesh-agent-03"],
    "agent-04": ["mesh-agent-04"],
    "agent-05": ["mesh-agent-05"],
    "agent-06": ["mesh-agent-06"],
    "agent-07": ["mesh-agent-07"],
    "agent-08": ["mesh-agent-08"],
    "agent-09": ["mesh-agent-09"],
    "highload": ["mesh-highload"],
    "paris": ["mesh-paris"],
    "reserve242": ["mesh-reserve242"],
    "server-kfrm": ["mesh-server-kfrm"],
    "home": ["home-live", "mesh-home"],
    "main": ["mesh-main"],
    "new": ["mesh-new"],
    "primary-candidate": ["mesh-primary"],
    "qjns": ["mesh-qjns"],
    "uiap": ["mesh-uiap"],
}

REPAIR_FALLBACK_NODES = ["primary-candidate", "main", "mesh-agent-01", "mesh-agent-02", "mesh-agent-03", "mesh-9fts", "new"]

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
        "/v1/models",
        "/v1/agents/status/{task_id}",
        "/v1/agents/artifacts/{task_id}",
    ],
    "POST": [
        "/v1/responses",
        "/v1/chat/completions",
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


def _node_disk_free_gb(node: dict[str, Any]) -> float | None:
    for key_name in ("disk_free_gb", "free_gb"):
        value = node.get(key_name)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    disk = node.get("disk")
    if isinstance(disk, dict):
        for key_name in ("free_gb", "available_gb", "disk_free_gb"):
            value = disk.get(key_name)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None
    return None


def _runner_available(node: dict[str, Any]) -> bool:
    capabilities = set(node.get("capabilities") or [])
    if capabilities.intersection(runner_capability_names("codex") | runner_capability_names("mimo")):
        return True
    runners = node.get("runners")
    if isinstance(runners, dict):
        for runner_name in ("codex", "mimo"):
            state = runner_state(node, runner_name)
            if state and state not in BLOCKED_RUNNER_STATES:
                return True
    return False


def owner_server_node_candidates(server_id: str, nodes_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    ids = [server_id, *OWNER_SERVER_IDENTITY_ALIASES.get(server_id, [])]
    return [nodes_by_id[node_id] for node_id in ids if node_id in nodes_by_id]


def repair_envelope_for_owner_server(
    *,
    node_id: str,
    reason: str,
    task_id_prefix: str,
    fallback_nodes: list[str],
    required_capability: str = "devops",
) -> dict[str, Any]:
    task_id = f"{task_id_prefix}-{node_id.upper().replace('-', '_')}"
    return {
        "task_id": task_id,
        "idempotency_key": f"owner-server-repair:{task_id_prefix}:{node_id}",
        "kind": "owner_remote_task",
        "priority": "P0",
        "required_capability": required_capability,
        "runner": "codex",
        "agent_type": "server_connectivity_repair",
        "agent_display_name": "Ремонтник связи",
        "target_node": node_id,
        "fallback_nodes": fallback_nodes,
        "branch": "p0/server-connectivity-repair-loop-2026-07-02",
        "base_ref": "origin/main",
        "write_scope": [
            f"docs/agent/runs/{task_id}/**",
            f"docs/agent/intelligence/{task_id}/**",
        ],
        "max_retries": 1,
        "objective": (
            "Repair this owner server enough for API reachability, Agent Host heartbeat, "
            "and non-interactive GitHub auth smoke where possible. Do not print secrets. "
            "Prefer reversible service/config checks; if blocked, return the exact owner "
            "command needed."
        ),
        "repair_reason": reason,
        "constraints": {
            "secrets_redaction_required": True,
            "destructive_commands_forbidden": True,
            "force_push_forbidden": True,
            "push_to_main_forbidden": True,
            "credential_value_printing_forbidden": True,
            "production_restart_requires_owner_approval": True,
            "artifact_backed_result_required": True,
        },
        "required_outputs": ["PLAN.md", "ACTIONS.md", "TESTS.md", "RESULT.md", "NEXT.md"],
        "acceptance": [
            "API reachability is restored or an exact safe repair command is returned.",
            "Agent Host heartbeat is fresh or the blocker is classified with fallback nodes.",
            "GitHub auth is verified with a non-secret read-only smoke or classified as blocked.",
            "No secrets, credential values, force pushes, main pushes, or destructive commands are used.",
            "PLAN.md, ACTIONS.md, TESTS.md, RESULT.md, and NEXT.md are produced for this node.",
        ],
        "verification_commands": [
            "GET /v1/health through Fabric API or local relay",
            "GET /v1/nodes and confirm fresh heartbeat for target identity",
            "systemctl is-active kolibri-agent-host without restarting unless explicitly approved",
            "git ls-remote --exit-code origin HEAD without printing credentials",
            "return exact blocker command when repair cannot be completed safely",
        ],
    }


def owner_server_repair_plan(
    registered_nodes: list[dict[str, Any]] | None = None,
    *,
    task_id_prefix: str = "P0_OWNER_SERVER_REPAIR",
) -> dict[str, Any]:
    nodes = fabric_nodes(registered_nodes)
    nodes_by_id = {node["node_id"]: node for node in nodes}
    usable_fallbacks = [
        node_id for node_id in REPAIR_FALLBACK_NODES
        if (node := nodes_by_id.get(node_id)) and node.get("health") == "online"
    ] or ["main", "primary-candidate"]
    matrix = []
    repair_tasks = []
    working = 0
    blocked = 0
    degraded = 0
    for server in OWNER_SERVER_CATALOG:
        node_id = server["node_id"]
        candidates = owner_server_node_candidates(node_id, nodes_by_id)
        best = next((node for node in candidates if node.get("health") == "online"), None)
        best = best or (candidates[0] if candidates else None)
        reasons = []
        if not best:
            reasons.append("missing_control_plane_card")
        else:
            health = str(best.get("health") or "unknown")
            freshness = str(best.get("freshness") or "")
            disk_free = _node_disk_free_gb(best)
            if health != "online":
                reasons.append(f"health_{health}")
            if freshness in {"stale", "degraded"}:
                reasons.append(f"heartbeat_{freshness}")
            if disk_free is not None and disk_free <= 0:
                reasons.append("disk_full")
            if node_id in {"qjns", "main", "primary-candidate"} and not _runner_available(best):
                reasons.append("github_or_runner_auth_unverified")
            if node_id in {"home"} and freshness != "fresh":
                reasons.append("owner_gateway_heartbeat_unverified")
            if best.get("node_id") != node_id:
                reasons.append("canonical_identity_alias_only")
        if not reasons:
            status = "working"
            working += 1
        else:
            status = "blocked" if "missing_control_plane_card" in reasons or "disk_full" in reasons else "repair_pending"
            if status == "blocked":
                blocked += 1
            else:
                degraded += 1
        repair_task = None
        exact_command = ""
        if reasons:
            repair_task = repair_envelope_for_owner_server(
                node_id=node_id,
                reason=", ".join(reasons),
                task_id_prefix=task_id_prefix,
                fallback_nodes=[item for item in usable_fallbacks if item != node_id],
                required_capability=server["repair_capability"],
            )
            repair_tasks.append(repair_task)
            exact_command = f"./ops/kolibri-dispatch submit --file docs/agent/runs/{task_id_prefix}/repair-envelopes/{node_id}.json"
        matrix.append({
            "node_id": node_id,
            "role": server["role"],
            "status": status,
            "observed_node": best.get("node_id") if best else "",
            "health": best.get("health") if best else "missing",
            "freshness": best.get("freshness", "") if best else "",
            "reasons": reasons,
            "fallback_nodes": [item for item in usable_fallbacks if item != node_id],
            "repair_task_id": repair_task["task_id"] if repair_task else "",
            "exact_repair_command": exact_command,
        })
    return {
        "status": "partial" if repair_tasks else "completed",
        "task_id_prefix": task_id_prefix,
        "summary": {
            "canonical_servers": len(OWNER_SERVER_CATALOG),
            "working": working,
            "repair_pending": degraded,
            "blocked": blocked,
            "repair_tasks": len(repair_tasks),
        },
        "matrix": matrix,
        "repair_tasks": repair_tasks,
        "next_action": "dispatch repair_tasks through /v1/tasks, then rerun this plan until working equals canonical_servers",
    }


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
    if envelope.get("kind") == "owner_remote_task" and runner:
        if not runner_capability_names(runner).intersection(set(capabilities)):
            return False
        node_state = runner_state(node or {}, runner)
        if node_state in BLOCKED_RUNNER_STATES:
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
            if path == "/v1/fleet/repair-plan":
                query = parse_qs(parsed.query)
                plan = owner_server_repair_plan(
                    registered_nodes(),
                    task_id_prefix=query.get("task_id_prefix", ["P0_OWNER_SERVER_REPAIR"])[0],
                )
                response(self, 200, canonical_response_envelope(
                    status=plan["status"],
                    route_used="/v1/fleet/repair-plan",
                    fallback_nodes=REPAIR_FALLBACK_NODES,
                    data=plan,
                    next_action=plan["next_action"],
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
            response(self, 404, {"error": "not_found", "path": path})
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
