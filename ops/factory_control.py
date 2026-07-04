#!/usr/bin/env python3
"""Minimal Kolibri Factory control plane sidecar.

The sidecar intentionally uses only the Python standard library. It stores all
task and node state in the existing local Redis server through a tiny RESP
client so it can run next to the legacy control plane without adding packages.

Integrates Truth Factory: claims, evidence, and verdict ledgers for
adversarial review of task outcomes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse


NAMESPACE = os.environ.get("FACTORY_NAMESPACE", "kolibri_factory")
REDIS_HOST = os.environ.get("FACTORY_REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("FACTORY_REDIS_PORT", "6379"))
LEASE_DURATION = int(os.environ.get("FACTORY_LEASE_DURATION", "60"))
MAX_RETRIES = int(os.environ.get("FACTORY_MAX_RETRIES", "3"))

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
                response(self, 200, {"status": "ok", "redis": pong, "queue_backend": "redis", "time": utc_now(), "truth_factory": "enabled"})
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
            if path == "/v1/nodes":
                nodes = []
                for node_id in sorted(redis.command("SMEMBERS", key("node_ids")) or []):
                    node = get_json(node_key(node_id), {})
                    node["draining"] = bool(redis.command("GET", drain_key(node_id)))
                    nodes.append(node)
                response(self, 200, {"nodes": nodes})
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
                error_type = body.get("error_type", "runtime_error")
                error = body.get("error", "")
                task["error_type"] = error_type
                task["error"] = error
                task["result"] = body.get("result")
                task["result_reference"] = body.get("result_reference")
                task["lease_until"] = None
                # Truth gate: log contradiction on failure
                task = truth_gate_on_fail(task, error_type, error)
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
