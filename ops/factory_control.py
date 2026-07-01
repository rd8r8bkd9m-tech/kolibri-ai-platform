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
LOGICAL_AGENT_TARGET = int(os.environ.get("FACTORY_LOGICAL_AGENT_TARGET", "1000"))
LOGICAL_AGENT_NODE_LIMIT = int(os.environ.get("FACTORY_LOGICAL_AGENT_NODE_LIMIT", "20"))
LOGICAL_AGENT_WAVE_LIMIT = int(os.environ.get("FACTORY_LOGICAL_AGENT_WAVE_LIMIT", "20"))
LOGICAL_AGENT_QUEUE_LIMIT = int(os.environ.get("FACTORY_LOGICAL_AGENT_QUEUE_LIMIT", "50"))

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
ACTIVE_STATES = {STATE_QUEUED, STATE_LEASED, STATE_RUNNING, STATE_REVIEW, STATE_RETRY}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_ts() -> float:
    return time.time()


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


def all_task_ids() -> list[str]:
    values = redis.command("SMEMBERS", key("task_ids")) or []
    return sorted(values)


def queue_ids() -> list[str]:
    return redis.command("LRANGE", key("queue"), 0, -1) or []


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


def compatible(task: dict[str, Any], node_id: str, capabilities: list[str]) -> bool:
    envelope = task.get("envelope", {})
    target_node = envelope.get("target_node") or envelope.get("required_node")
    if target_node and target_node != node_id:
        return False
    allowed = envelope.get("allowed_nodes")
    if allowed and node_id not in allowed:
        return False
    required = envelope.get("required_capability")
    if required and required not in capabilities:
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


def parse_kib_value(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return None
    parts = value.strip().split()
    if not parts:
        return None
    try:
        number = float(parts[0])
    except ValueError:
        return None
    unit = parts[1].lower() if len(parts) > 1 else "kb"
    factor = 1
    if unit in {"mb", "mib"}:
        factor = 1024
    elif unit in {"gb", "gib"}:
        factor = 1024 * 1024
    return int(number * factor)


def node_capacity(node: dict[str, Any], per_server_limit: int = LOGICAL_AGENT_NODE_LIMIT) -> dict[str, Any]:
    node_id = str(node.get("node_id") or "")
    blockers: list[str] = []
    if node.get("health") != "online":
        blockers.append("node_not_online")

    cpu = int(node.get("cpu") or 0)
    ram = node.get("ram") if isinstance(node.get("ram"), dict) else {}
    disk = node.get("disk") if isinstance(node.get("disk"), dict) else {}
    mem_available_kib = parse_kib_value(ram.get("MemAvailable"))
    disk_free_bytes = int(disk.get("free") or 0)
    if cpu <= 0:
        blockers.append("missing_cpu_measurement")
    if not mem_available_kib:
        blockers.append("missing_ram_measurement")
    if disk_free_bytes <= 0:
        blockers.append("missing_disk_measurement")

    mem_gib = (mem_available_kib or 0) / (1024 * 1024)
    disk_free_gib = disk_free_bytes / (1024 ** 3)
    measured = not any(item.startswith("missing_") for item in blockers)
    slots = 0
    capacity_class = "blocked"
    if node.get("health") == "online" and measured:
        if cpu >= 16 and mem_gib >= 32 and disk_free_gib >= 40:
            slots = 20
            capacity_class = "xlarge"
        elif cpu >= 8 and mem_gib >= 16 and disk_free_gib >= 20:
            slots = 10
            capacity_class = "large"
        elif cpu >= 4 and mem_gib >= 8 and disk_free_gib >= 10:
            slots = 4
            capacity_class = "medium"
        elif cpu >= 2 and mem_gib >= 4 and disk_free_gib >= 5:
            slots = 1
            capacity_class = "small"
        else:
            blockers.append("measured_capacity_below_minimum")
    slots = max(0, min(slots, per_server_limit))
    return {
        "node_id": node_id,
        "capacity_class": capacity_class,
        "logical_agent_capacity": slots,
        "cpu": cpu,
        "mem_available_gib": round(mem_gib, 2),
        "disk_free_gib": round(disk_free_gib, 2),
        "measured": measured,
        "blockers": blockers,
    }


def load_nodes() -> list[dict[str, Any]]:
    nodes = []
    for node_id in sorted(redis.command("SMEMBERS", key("node_ids")) or []):
        node = get_json(node_key(node_id), {})
        node["draining"] = bool(redis.command("GET", drain_key(node_id)))
        nodes.append(node)
    return nodes


def logical_schedule_task_count(schedule_id: str, node_id: str | None = None) -> int:
    count = 0
    for task_id in all_task_ids():
        task = load_task(task_id)
        if not task or task.get("state") not in ACTIVE_STATES:
            continue
        envelope = task.get("envelope", {})
        if envelope.get("schedule_id") != schedule_id:
            continue
        if node_id and envelope.get("target_node") != node_id:
            continue
        count += 1
    return count


def create_logical_scheduler_wave(request: dict[str, Any]) -> dict[str, Any]:
    target = min(max(int(request.get("target", LOGICAL_AGENT_TARGET)), 1), LOGICAL_AGENT_TARGET)
    per_server_limit = min(max(int(request.get("per_server_limit", LOGICAL_AGENT_NODE_LIMIT)), 1), LOGICAL_AGENT_NODE_LIMIT)
    wave_limit = min(max(int(request.get("wave_limit", LOGICAL_AGENT_WAVE_LIMIT)), 1), LOGICAL_AGENT_QUEUE_LIMIT)
    schedule_id = str(request.get("schedule_id") or f"logical-agents-{target}")
    created_tasks: list[str] = []
    blockers: list[dict[str, Any]] = []
    capacities: list[dict[str, Any]] = []

    global_active = logical_schedule_task_count(schedule_id)
    create_budget = max(0, min(wave_limit, target - global_active, LOGICAL_AGENT_QUEUE_LIMIT - global_active))
    nodes = load_nodes()
    if not nodes:
        return {
            "schedule_id": schedule_id,
            "status": "blocked",
            "target": target,
            "per_server_limit": per_server_limit,
            "wave_limit": wave_limit,
            "created_task_ids": [],
            "node_capacities": [],
            "blockers": [{"scope": "control_plane", "reason": "no_registered_nodes"}],
            "next_wave": {"remaining_target": target, "available_create_budget": 0, "recommended_wave_limit": 0},
        }

    for node in nodes:
        capacity = node_capacity(node, per_server_limit)
        active_on_node = logical_schedule_task_count(schedule_id, capacity["node_id"])
        capacity["active_logical_tasks"] = active_on_node
        capacity["available_slots"] = max(0, capacity["logical_agent_capacity"] - active_on_node)
        capacities.append(capacity)
        node["capacity_classification"] = capacity
        node["capacity_classified_at"] = utc_now()
        set_json(node_key(capacity["node_id"]), node)

    for capacity in capacities:
        node_id = capacity["node_id"]
        if create_budget <= 0:
            break
        if capacity["blockers"]:
            blockers.append({"node_id": node_id, "reasons": capacity["blockers"]})
            if capacity.get("measured") is False and "node_not_online" not in capacity["blockers"]:
                probe = create_task({
                    "task_id": f"CAPACITY-PROBE-{schedule_id}-{node_id}",
                    "idempotency_key": f"capacity-probe:{schedule_id}:{node_id}",
                    "kind": "read_only_probe",
                    "target_node": node_id,
                    "scheduler_action": "capacity_classification_probe",
                    "schedule_id": schedule_id,
                    "max_retries": 1,
                })
                if probe["task_id"] not in created_tasks:
                    created_tasks.append(probe["task_id"])
                    create_budget -= 1
            continue
        for _ in range(min(capacity["available_slots"], create_budget)):
            ordinal = global_active + len(created_tasks) + 1
            task = create_task({
                "task_id": f"LOGICAL-AGENT-{schedule_id}-{node_id}-{ordinal}",
                "idempotency_key": f"logical-agent:{schedule_id}:{node_id}:{ordinal}",
                "kind": "read_only_probe",
                "target_node": node_id,
                "scheduler_action": "logical_agent_slot_probe",
                "schedule_id": schedule_id,
                "logical_target": target,
                "per_server_limit": per_server_limit,
                "max_retries": 1,
            })
            if task["task_id"] not in created_tasks:
                created_tasks.append(task["task_id"])
            create_budget -= 1
            if create_budget <= 0:
                break

    updated_active = logical_schedule_task_count(schedule_id)
    remaining = max(0, target - updated_active)
    total_available_slots = sum(item["available_slots"] for item in capacities if not item["blockers"])
    logical_children_created = any(task_id.startswith("LOGICAL-AGENT-") for task_id in created_tasks)
    status = "started" if logical_children_created else ("blocked" if blockers and total_available_slots == 0 else "at_capacity")
    return {
        "schedule_id": schedule_id,
        "status": status,
        "target": target,
        "per_server_limit": per_server_limit,
        "wave_limit": wave_limit,
        "queue_limit": LOGICAL_AGENT_QUEUE_LIMIT,
        "created_task_ids": created_tasks,
        "node_capacities": capacities,
        "blockers": blockers,
        "next_wave": {
            "remaining_target": remaining,
            "active_logical_tasks": updated_active,
            "available_create_budget": max(0, min(wave_limit, remaining, LOGICAL_AGENT_QUEUE_LIMIT - updated_active)),
            "recommended_wave_limit": min(LOGICAL_AGENT_WAVE_LIMIT, max(0, remaining)),
        },
    }


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
                response(self, 200, {"nodes": load_nodes()})
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
            if path == "/v1/scheduler/logical-agents":
                result = create_logical_scheduler_wave(body)
                response(self, 200, result)
                return
            if path == "/v1/tasks/lease":
                requeue_expired_leases()
                node_id = body["node_id"]
                if redis.command("GET", drain_key(node_id)):
                    response(self, 204, {})
                    return
                capabilities = body.get("capabilities", [])
                agent_id = body.get("agent_id", node_id)
                for task_id in queue_ids():
                    task = load_task(task_id)
                    if not task or task.get("state") not in {STATE_QUEUED, STATE_REVIEW}:
                        remove_from_queue(task_id)
                        continue
                    if not compatible(task, node_id, capabilities):
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
