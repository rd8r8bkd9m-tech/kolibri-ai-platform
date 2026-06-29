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
from typing import Any
from urllib.parse import parse_qs, urlparse


NAMESPACE = os.environ.get("FACTORY_NAMESPACE", "kolibri_factory")
REDIS_HOST = os.environ.get("FACTORY_REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("FACTORY_REDIS_PORT", "6379"))
LEASE_DURATION = int(os.environ.get("FACTORY_LEASE_DURATION", "60"))
MAX_RETRIES = int(os.environ.get("FACTORY_MAX_RETRIES", "3"))
NODE_STALE_AFTER = int(os.environ.get("FACTORY_NODE_STALE_AFTER", "120"))
DEFAULT_TASK_LIST_LIMIT = int(os.environ.get("FACTORY_DEFAULT_TASK_LIST_LIMIT", "200"))
MAX_TASK_LIST_LIMIT = int(os.environ.get("FACTORY_MAX_TASK_LIST_LIMIT", "500"))
MAX_TASK_SUMMARY_SCAN = int(os.environ.get("FACTORY_MAX_TASK_SUMMARY_SCAN", "2000"))
LEASE_EXPIRING_SOON_SECONDS = int(os.environ.get("FACTORY_LEASE_EXPIRING_SOON_SECONDS", "30"))

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
AUTONOMOUS_TASK_KINDS = {"owner_remote_task", "generic_implementation"}
RUNTIME_CAPABILITY_COMPAT = {
    "remote_implementation_runner_ready": {"implementation", "generic_implementation"},
}
RUNTIME_KIND_COMPAT = {
    "remote_implementation_runner_ready": "generic_implementation",
}
PERMISSION_PACKS = {
    "read_only": {"read_repo", "read_system", "write_artifacts"},
    "ai_chat": {"ai_runner", "write_artifacts"},
    "media_generation": {"ai_runner", "network", "write_artifacts"},
    "implementation": {"read_repo", "write_worktree", "run_tests", "network", "git_push", "write_artifacts"},
    "review": {"read_repo", "run_tests", "network", "github_review", "write_artifacts"},
    "full_autonomy": {
        "ai_runner",
        "git_push",
        "github_review",
        "network",
        "read_repo",
        "run_tests",
        "shell",
        "spawn_subagents",
        "write_artifacts",
        "write_worktree",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_ts() -> float:
    return time.time()


def key(name: str) -> str:
    return f"{NAMESPACE}:{name}"


def parse_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def expand_permission_packs(packs: Any) -> set[str]:
    permissions: set[str] = set()
    for pack in parse_list(packs):
        permissions.update(PERMISSION_PACKS.get(pack, {pack}))
    return permissions


def default_permission_pack(kind: str) -> str | None:
    if kind in AUTONOMOUS_TASK_KINDS:
        return "full_autonomy"
    return None


def task_permission_pack(envelope: dict[str, Any]) -> str | None:
    pack = envelope.get("permission_pack") or envelope.get("autonomy_pack")
    return str(pack) if pack else default_permission_pack(str(envelope.get("kind") or ""))


def task_required_permissions(envelope: dict[str, Any]) -> list[str]:
    explicit = parse_list(envelope.get("required_permissions"))
    if explicit:
        return sorted(set(explicit))
    pack = task_permission_pack(envelope)
    return sorted(expand_permission_packs(pack)) if pack else []


def available_permissions(capabilities: list[str], permissions: list[str] | None = None) -> set[str]:
    values = set(parse_list(permissions))
    for capability in parse_list(capabilities):
        if capability.startswith("permission:"):
            values.add(capability.removeprefix("permission:"))
    return values


def granted_permissions(task: dict[str, Any], capabilities: list[str], permissions: list[str] | None = None) -> list[str]:
    required = set(parse_list(task.get("required_permissions")))
    if not required:
        required = set(task_required_permissions(task.get("envelope", {})))
    node_permissions = available_permissions(capabilities, permissions)
    if "*" in node_permissions:
        return sorted(required)
    return sorted(required & node_permissions)


def compatible_capability(required: Any, capabilities: list[str]) -> bool:
    required_name = str(required or "").strip()
    if not required_name:
        return True
    available = set(parse_list(capabilities))
    if required_name in available:
        return True
    return bool(RUNTIME_CAPABILITY_COMPAT.get(required_name, set()) & available)


def runtime_runner_kind(task_or_envelope: dict[str, Any]) -> str:
    kind = str(task_or_envelope.get("kind") or "read_only_probe")
    return RUNTIME_KIND_COMPAT.get(kind, kind)


def parse_iso_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def heartbeat_age_seconds(value: Any, current: datetime | None = None) -> float | None:
    heartbeat = parse_iso_ts(value)
    if not heartbeat:
        return None
    current = current or datetime.now(timezone.utc)
    return max(0.0, (current - heartbeat).total_seconds())


def decorate_node(node: dict[str, Any], current: datetime | None = None) -> dict[str, Any]:
    decorated = dict(node)
    age = heartbeat_age_seconds(decorated.get("heartbeat_at"), current)
    decorated["heartbeat_age_seconds"] = age
    decorated["fresh"] = age is not None and age <= NODE_STALE_AFTER
    if not decorated["fresh"]:
        decorated["health"] = "stale"

    active_task = decorated.get("active_task")
    if active_task:
        task = load_task(str(active_task))
        if task:
            state = task.get("state")
            decorated["active_task_state"] = state
            decorated["active_task_terminal"] = state in TERMINAL_STATES
    return decorated


def summarize_nodes(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    node_ids = {str(node.get("node_id") or "") for node in nodes if node.get("node_id")}
    parent: dict[str, str] = {}

    def find(name: str) -> str:
        parent.setdefault(name, name)
        if parent[name] != name:
            parent[name] = find(parent[name])
        return parent[name]

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for node in nodes:
        node_id = str(node.get("node_id") or "")
        if node_id:
            find(node_id)

    hostname_groups: dict[str, list[str]] = {}
    mesh_shadow_duplicates: list[dict[str, str]] = []
    for node in nodes:
        node_id = str(node.get("node_id") or "")
        hostname = str(node.get("hostname") or "").strip()
        if hostname:
            hostname_groups.setdefault(hostname, []).append(node_id)
        if node_id.startswith("mesh-"):
            base_id = node_id.removeprefix("mesh-")
            if base_id in node_ids:
                union(base_id, node_id)
                mesh_shadow_duplicates.append({"node_id": node_id, "shadows": base_id})

    duplicate_hostname_groups = {
        hostname: ids
        for hostname, ids in hostname_groups.items()
        if hostname and len([node_id for node_id in ids if node_id]) > 1
    }
    for ids in duplicate_hostname_groups.values():
        real_ids = [node_id for node_id in ids if node_id]
        for node_id in real_ids[1:]:
            union(real_ids[0], node_id)

    groups: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        node_id = str(node.get("node_id") or "")
        if not node_id:
            continue
        groups.setdefault(find(node_id), []).append(node)

    def node_score(node: dict[str, Any]) -> tuple[int, int, int, str]:
        node_id = str(node.get("node_id") or "")
        return (
            int(bool(node.get("fresh") and not node.get("draining"))),
            int(bool(node.get("fresh"))),
            int(not node_id.startswith("mesh-")),
            str(node.get("heartbeat_at") or ""),
        )

    canonical_nodes = [max(group, key=node_score) for group in groups.values()]
    fresh_canonical_nodes = [
        node for node in canonical_nodes if node.get("fresh") and not node.get("draining")
    ]
    fresh_canonical_generic_implementation_nodes = [
        node
        for node in fresh_canonical_nodes
        if "generic_implementation" in parse_list(node.get("capabilities"))
    ]

    return {
        "registered_nodes": len(nodes),
        "canonical_nodes": len(canonical_nodes),
        "fresh_nodes": sum(1 for node in nodes if node.get("fresh")),
        "fresh_non_draining_nodes": sum(1 for node in nodes if node.get("fresh") and not node.get("draining")),
        "fresh_canonical_nodes": len(fresh_canonical_nodes),
        "fresh_canonical_generic_implementation_nodes": len(fresh_canonical_generic_implementation_nodes),
        "mesh_shadow_duplicates": len(mesh_shadow_duplicates),
        "mesh_shadow_duplicate_nodes": mesh_shadow_duplicates,
        "duplicate_hostname_groups": len(duplicate_hostname_groups),
        "duplicate_hostnames": duplicate_hostname_groups,
    }


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


def agent_feed_key(target: str) -> str:
    return key(f"agent_feed:{target}")


def all_task_ids() -> list[str]:
    values = redis.command("SMEMBERS", key("task_ids")) or []
    return sorted(values)


def queue_ids() -> list[str]:
    return redis.command("LRANGE", key("queue"), 0, -1) or []


def queue_length() -> int:
    return int(redis.command("LLEN", key("queue")) or 0)


def queue_prefix(limit: int) -> list[str]:
    if limit <= 0:
        return []
    return redis.command("LRANGE", key("queue"), 0, limit - 1) or []


def load_task(task_id: str) -> dict[str, Any] | None:
    return get_json(task_key(task_id))


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
    kind = envelope.get("kind", "read_only_probe")
    normalized_envelope = dict(envelope)
    normalized_envelope["kind"] = kind
    permission_pack = task_permission_pack(normalized_envelope)
    required_permissions = task_required_permissions(normalized_envelope)
    return {
        "task_id": task_id,
        "idempotency_key": envelope.get("idempotency_key") or task_id,
        "kind": kind,
        "permission_pack": permission_pack,
        "required_permissions": required_permissions,
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
        "envelope": normalized_envelope,
    }


def compatible(task: dict[str, Any], node_id: str, capabilities: list[str], permissions: list[str] | None = None) -> bool:
    envelope = task.get("envelope", {})
    target_node = envelope.get("target_node") or envelope.get("required_node")
    if target_node and target_node != node_id:
        return False
    allowed = envelope.get("allowed_nodes")
    if allowed and node_id not in allowed:
        return False
    required = envelope.get("required_capability")
    if required and not compatible_capability(required, capabilities):
        return False
    required_permissions = set(parse_list(task.get("required_permissions")) or task_required_permissions(envelope))
    node_permissions = available_permissions(capabilities, permissions)
    if required_permissions and "*" not in node_permissions and not required_permissions <= node_permissions:
        return False
    return True


def compact_task(task: dict[str, Any]) -> dict[str, Any]:
    envelope = task.get("envelope", {})
    return {
        "task_id": task.get("task_id"),
        "kind": task.get("kind"),
        "runner_kind": runtime_runner_kind(task),
        "state": task.get("state"),
        "target_node": envelope.get("target_node") or envelope.get("required_node"),
        "required_capability": envelope.get("required_capability"),
        "permission_pack": task.get("permission_pack"),
        "required_permissions": task.get("required_permissions", []),
        "attempt": task.get("attempt"),
        "max_retries": task.get("max_retries"),
        "lease_owner": task.get("lease_owner"),
        "lease_until": task.get("lease_until"),
        "error_type": task.get("error_type"),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
    }


def summarize_tasks(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    active_total = 0
    expired_lease_total = 0
    lease_expiring_soon_total = 0
    current = now_ts()
    for task in tasks:
        state = str(task.get("state") or "unknown")
        counts[state] = counts.get(state, 0) + 1
        if state in {STATE_LEASED, STATE_RUNNING, STATE_REVIEW, STATE_WAITING_REVIEW}:
            active_total += 1
        lease_until = task.get("lease_until")
        if state in {STATE_LEASED, STATE_RUNNING, STATE_REVIEW} and lease_until:
            try:
                lease_remaining = float(lease_until) - current
            except (TypeError, ValueError):
                continue
            if lease_remaining < 0:
                expired_lease_total += 1
            elif lease_remaining <= LEASE_EXPIRING_SOON_SECONDS:
                lease_expiring_soon_total += 1
    active = [
        compact_task(task)
        for task in tasks
        if task.get("state") in {STATE_LEASED, STATE_RUNNING, STATE_REVIEW, STATE_WAITING_REVIEW}
    ]
    return {
        "total": len(tasks),
        "states": counts,
        "active": active,
        "active_total": active_total,
        "expired_lease_total": expired_lease_total,
        "lease_expiring_soon_total": lease_expiring_soon_total,
    }


def bounded_limit(raw: str | None, default: int = DEFAULT_TASK_LIST_LIMIT) -> int:
    if raw is None or raw == "":
        return min(default, MAX_TASK_LIST_LIMIT)
    try:
        value = int(raw)
    except ValueError:
        return min(default, MAX_TASK_LIST_LIMIT)
    return max(0, min(value, MAX_TASK_LIST_LIMIT))


def task_sample(
    wanted: str | None = None,
    limit: int = DEFAULT_TASK_LIST_LIMIT,
    compact: bool = False,
    scan_limit: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tasks = []
    seen = 0
    matched = 0
    for task_id in all_task_ids():
        if scan_limit is not None and seen >= scan_limit:
            break
        seen += 1
        task = load_task(task_id)
        if not task or (wanted is not None and task.get("state") != wanted):
            continue
        matched += 1
        tasks.append(compact_task(task) if compact else task)
    tasks.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return tasks[:limit], {
        "tasks_scanned": seen,
        "tasks_matched": matched,
        "tasks_returned": min(len(tasks), limit),
        "tasks_truncated": len(tasks) > limit,
        "scan_truncated": scan_limit is not None and seen >= scan_limit,
    }


def limited_tasks(wanted: str | None = None, limit: int | None = None, compact: bool = False) -> list[dict[str, Any]]:
    sample, _meta = task_sample(
        wanted=wanted,
        limit=limit if limit is not None else DEFAULT_TASK_LIST_LIMIT,
        compact=compact,
    )
    return sample


def compact_task_listing(wanted: str | None, limit: int) -> dict[str, Any]:
    q_len = queue_length()
    q_prefix = queue_prefix(limit)
    tasks = []
    for task_id in q_prefix:
        task = load_task(task_id)
        if not task or (wanted is not None and task.get("state") != wanted):
            continue
        tasks.append(compact_task(task))
    summary = summarize_tasks(tasks)
    summary.update({
        "tasks_scanned": len(q_prefix),
        "tasks_matched": len(tasks),
        "scan_truncated": q_len > len(q_prefix),
    })
    summary["tasks_returned"] = len(tasks)
    summary["tasks_truncated"] = q_len > len(q_prefix)
    summary["queue_total"] = q_len
    summary["queue_returned"] = len(q_prefix)
    summary["queue_truncated"] = q_len > len(q_prefix)
    summary["limit"] = limit
    summary["max_limit"] = MAX_TASK_LIST_LIMIT
    summary["summary_scope"] = "queue_prefix"
    return {
        "summary": summary,
        "queue_length": q_len,
        "queue": q_prefix,
        "tasks": tasks,
    }


def normalize_agent_message(body: dict[str, Any]) -> dict[str, Any]:
    created = utc_now()
    message_id = body.get("message_id") or f"MSG-{uuid.uuid4().hex[:16]}"
    sender = str(body.get("sender") or body.get("from") or "unknown")
    recipients = parse_list(body.get("recipients") or body.get("to") or "all")
    if not recipients:
        recipients = ["all"]
    return {
        "message_id": message_id,
        "sender": sender,
        "recipients": recipients,
        "kind": body.get("kind", "status"),
        "topic": body.get("topic"),
        "task_id": body.get("task_id"),
        "body": body.get("body", body.get("message", "")),
        "artifacts": body.get("artifacts", []),
        "created_at": created,
    }


def publish_agent_message(message: dict[str, Any]) -> dict[str, Any]:
    targets = sorted(set(["all", *parse_list(message.get("recipients"))]))
    payload = json.dumps(message, sort_keys=True, separators=(",", ":"))
    for target in targets:
        redis.command("LPUSH", agent_feed_key(target), payload)
        redis.command("LTRIM", agent_feed_key(target), 0, 499)
    return message


def load_agent_messages(target: str, limit: int = 50) -> list[dict[str, Any]]:
    raw_items = redis.command("LRANGE", agent_feed_key(target), 0, max(0, limit - 1)) or []
    messages = []
    for raw in raw_items:
        try:
            messages.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return messages


def requeue_expired_leases(limit: int | None = None) -> dict[str, Any]:
    current = now_ts()
    task_ids = all_task_ids()
    if limit is not None:
        limit = max(0, int(limit))
        selected_task_ids = task_ids[:limit]
    else:
        selected_task_ids = task_ids
    summary: dict[str, Any] = {
        "task_total": len(task_ids),
        "scan_limit": limit,
        "scan_truncated": limit is not None and len(task_ids) > limit,
        "checked": 0,
        "expired": 0,
        "requeued": [],
        "dead_lettered": [],
        "skipped": [],
    }
    for task_id in selected_task_ids:
        task = load_task(task_id)
        if not task or task.get("state") not in {STATE_LEASED, STATE_RUNNING, STATE_REVIEW}:
            continue
        summary["checked"] += 1
        try:
            lease_until = float(task.get("lease_until") or 0)
        except (TypeError, ValueError):
            summary["skipped"].append({"task_id": task_id, "reason": "invalid_lease_until"})
            continue
        if lease_until >= current:
            continue
        summary["expired"] += 1
        task["lease_owner"] = None
        task["lease_until"] = None
        task["error_type"] = "lease_expired"
        if int(task.get("attempt", 0)) < int(task.get("max_retries", MAX_RETRIES)):
            task["state"] = STATE_RETRY
            task["error"] = "lease expired before task completion"
            append_attempt_history(task, "lease_expired", task.get("error_type"), task.get("error"), task.get("result_reference"))
            save_task(task)
            task["state"] = STATE_QUEUED
            save_task(task)
            remove_from_queue(task_id)
            enqueue(task_id)
            summary["requeued"].append(task_id)
        else:
            task["state"] = STATE_DEAD
            task["error"] = "lease expired and retry budget exhausted"
            append_attempt_history(task, "dead_letter", task.get("error_type"), task.get("error"), task.get("result_reference"))
            save_task(task)
            redis.command("RPUSH", key("dead_letter"), task_id)
            summary["dead_lettered"].append(task_id)
    summary["requeued_total"] = len(summary["requeued"])
    summary["dead_lettered_total"] = len(summary["dead_lettered"])
    summary["skipped_total"] = len(summary["skipped"])
    return summary


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


def append_attempt_history(task: dict[str, Any], status: str, error_type: str | None, error: str | None, result_reference: str | None) -> None:
    attempt = {
        "attempt": task.get("attempt"),
        "attempt_id": task.get("attempt_id"),
        "status": status,
        "error_type": error_type,
        "error": error,
        "result_reference": result_reference,
        "recorded_at": utc_now(),
    }
    history = task.setdefault("attempt_history", [])
    attempt_id = attempt.get("attempt_id")
    if attempt_id:
        history[:] = [item for item in history if item.get("attempt_id") != attempt_id]
    history.append(attempt)


def apply_task_completion(task: dict[str, Any], body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], bool]:
    result = body.get("result", body)
    needs_review = task.get("envelope", {}).get("create_review_on_complete")
    has_pr = bool(result.get("pull_request_url") or result.get("pr_url"))
    task["state"] = STATE_COMPLETED if (not needs_review or has_pr) else STATE_WAITING_REVIEW
    task["result"] = result
    task["result_reference"] = body.get("result_reference") or result.get("result_path")
    task["heartbeat_at"] = utc_now()
    task["lease_until"] = None
    task["error_type"] = None
    task["error"] = None
    append_attempt_history(task, "completed", None, None, task.get("result_reference"))
    return task, result, has_pr


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
                response(self, 200, {"status": "ok", "redis": pong, "queue_backend": "redis", "time": utc_now()})
                return
            if path == "/v1/nodes":
                nodes = []
                current = datetime.now(timezone.utc)
                for node_id in sorted(redis.command("SMEMBERS", key("node_ids")) or []):
                    node = get_json(node_key(node_id), {})
                    node["draining"] = bool(redis.command("GET", drain_key(node_id)))
                    nodes.append(decorate_node(node, current))
                response(self, 200, {"nodes": nodes, "summary": summarize_nodes(nodes)})
                return
            if path == "/v1/tasks":
                query = parse_qs(parsed.query)
                wanted = query.get("state", [None])[0]
                summary = query.get("summary", ["0"])[0].lower() in {"1", "true", "yes"}
                compact = query.get("compact", ["0"])[0].lower() in {"1", "true", "yes"}
                limit = bounded_limit(query.get("limit", [None])[0])
                if summary and compact:
                    response(self, 200, compact_task_listing(wanted, limit))
                    return
                tasks, meta = task_sample(wanted=wanted, limit=limit, compact=compact)
                if summary:
                    payload = {"summary": summarize_tasks(tasks), "queue_length": queue_length(), "limits": meta}
                    response(self, 200, payload)
                    return
                q_len = queue_length()
                q_prefix = queue_prefix(limit)
                response(
                    self,
                    200,
                    {
                        "tasks": tasks,
                        "queue": q_prefix,
                        "queue_length": q_len,
                        "queue_truncated": q_len > len(q_prefix),
                        "limits": meta,
                    },
                )
                return
            if path == "/v1/agent-messages":
                query = parse_qs(parsed.query)
                target = query.get("target", ["all"])[0]
                limit = int(query.get("limit", ["50"])[0])
                response(self, 200, {"target": target, "messages": load_agent_messages(target, limit)})
                return
            if path.startswith("/v1/tasks/"):
                task_id = path.split("/", 3)[3]
                task = load_task(task_id)
                if not task:
                    response(self, 404, {"error": "task_not_found", "task_id": task_id})
                    return
                response(self, 200, task)
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
                    "permissions": parse_list(body.get("permissions")),
                    "permission_packs": parse_list(body.get("permission_packs")),
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
                node["permissions"] = parse_list(node.get("permissions"))
                node["permission_packs"] = parse_list(node.get("permission_packs"))
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
            if path == "/v1/tasks/reap-expired":
                limit = body.get("limit")
                response(self, 200, requeue_expired_leases(int(limit) if limit is not None else None))
                return
            if path == "/v1/agent-messages":
                message = publish_agent_message(normalize_agent_message(body))
                response(self, 201, message)
                return
            if path == "/v1/tasks/lease":
                requeue_expired_leases()
                node_id = body["node_id"]
                if redis.command("GET", drain_key(node_id)):
                    response(self, 204, {})
                    return
                capabilities = body.get("capabilities", [])
                permissions = parse_list(body.get("permissions"))
                agent_id = body.get("agent_id", node_id)
                for task_id in queue_ids():
                    task = load_task(task_id)
                    if not task or task.get("state") not in {STATE_QUEUED, STATE_REVIEW}:
                        remove_from_queue(task_id)
                        continue
                    if not compatible(task, node_id, capabilities, permissions):
                        continue
                    remove_from_queue(task_id)
                    task["state"] = STATE_LEASED
                    task["attempt"] = int(task.get("attempt", 0)) + 1
                    task["attempt_id"] = f"{task_id}-attempt-{task['attempt']}"
                    task["lease_owner"] = f"{node_id}:{agent_id}"
                    task["lease_until"] = now_ts() + LEASE_DURATION
                    task["heartbeat_at"] = utc_now()
                    task["granted_permissions"] = granted_permissions(task, capabilities, permissions)
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
                task, result, has_pr = apply_task_completion(task, body)
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
                append_attempt_history(task, "failed", task.get("error_type"), task.get("error"), task.get("result_reference"))
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
