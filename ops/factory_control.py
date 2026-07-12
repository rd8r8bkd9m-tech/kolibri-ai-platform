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
import hmac
import json
import os
import queue
import re
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Literal
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

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
from release_authority import (
    OWNER_APPROVAL_ATTESTATION_SCHEMA,
    OWNER_APPROVAL_NAMESPACE,
    OWNER_APPROVAL_SCHEMA,
    RELEASE_CAPABILITY,
    RELEASE_TASK_KINDS,
    ReleaseAuthorityError,
    approval_attestation_digest,
    canonical_owner_approval_attestation,
    canonical_owner_approval_bytes as authority_owner_approval_bytes,
    canonical_owner_approval_payload as authority_owner_approval_payload,
    validate_approval_for_task,
)
from fleet_membership import MembershipError, MeshMembershipSource


NAMESPACE = os.environ.get("FACTORY_NAMESPACE", "kolibri_factory")
REDIS_HOST = os.environ.get("FACTORY_REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("FACTORY_REDIS_PORT", "6379"))
CANARY_READ_ONLY = os.environ.get("FACTORY_CANARY_READ_ONLY", "0").strip().lower() in {
    "1", "true", "yes",
}
ACTIVE_RELEASE_ID = str(os.environ.get("KOLIBRI_ACTIVE_RELEASE_ID") or "").strip()
CANARY_REDIS_READ_COMMANDS = frozenset({
    "GET", "LRANGE", "MGET", "PING", "SMEMBERS", "ZREVRANGE",
})
LEASE_DURATION = int(os.environ.get("FACTORY_LEASE_DURATION", "60"))
LEASE_CLAIM_TTL = int(os.environ.get("FACTORY_LEASE_CLAIM_TTL", "15"))
REQUIRE_LEASE_FENCING = os.environ.get("FACTORY_REQUIRE_LEASE_FENCING", "1").strip().lower() not in {"0", "false", "no"}
DEFAULT_MAX_ATTEMPTS = int(os.environ.get("FACTORY_MAX_ATTEMPTS", "4"))
MAX_ATTEMPTS_LIMIT = 100
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
TASK_HEARTBEAT_STALE_AFTER = int(os.environ.get("FACTORY_TASK_HEARTBEAT_STALE_AFTER", "30"))
OWNER_APPROVAL_MAX_TTL = int(os.environ.get("FACTORY_OWNER_APPROVAL_MAX_TTL", "86400"))
OWNER_ALLOWED_SIGNERS = Path(os.environ.get(
    "FACTORY_OWNER_ALLOWED_SIGNERS",
    "/etc/kolibri/owner_allowed_signers",
))

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
COMPLETION_EVIDENCE_SCHEMA = "kolibri.task-completion-evidence.v1"
COMPLETION_BINDING_SCHEMA = "kolibri.task-completion-binding.v1"
COMPLETION_VERIFIER_SCHEMA = "kolibri.control-plane-completion-verifier.v1"
LEASE_FENCING_SCHEMA = "kolibri.lease-fencing.v1"
LEGACY_LEASE_FENCING_COMPATIBILITY = "pre_migration_attempt_id_owner_only"
COMPLETION_SUCCESS_STATUSES = frozenset({
    "completed", "healthy", "ok", "passed", "ready", "success",
})
FLEET_PROOF_SCHEMA = "kolibri.fleet-capability-proof.v1"
DEFAULT_FLEET_PROOF_QUEUE_AGE_SECONDS = 3600

# Non-mesh provider actors are execution adapters, not physical fleet members.
# The first supported adapter is the owner-session Mac Codex LaunchAgent.  Its
# identity is discovered from its signed/runtime registration labels; no node
# ID or IP address is embedded in the scheduler.
EXTERNAL_PROVIDER_ACTOR_SCOPE = "external_provider_actor"
FACTORY_PROVIDER_RUNNER_CONTRACT = "kolibri.factory-provider.readonly.v1"
CODEX_READINESS_SCHEMA = "kolibri.codex-readiness.v1"
CODEX_PROVIDER_MODEL = "gpt-5.5"
EXTERNAL_PROVIDER_READINESS_MAX_AGE_SECONDS = 300
EXTERNAL_PROVIDER_READINESS_FUTURE_GRACE_SECONDS = 60
EXTERNAL_PROVIDER_AUTH_CLOCK_SKEW_SECONDS = 60
EXTERNAL_PROVIDER_AUTH_NONCE_TTL_SECONDS = 180
EXTERNAL_PROVIDER_AUTH_HMAC_CONTRACT = "kolibri.external-provider-hmac.v1"
EXTERNAL_PROVIDER_AUTH_HASH_FILE = Path(os.environ.get(
    "FACTORY_EXTERNAL_PROVIDER_ACTOR_TOKEN_SHA256_FILE",
    "/etc/kolibri/external-provider-actor.sha256",
))
EXTERNAL_PROVIDER_ACTOR_SPECS = {
    "codex": {
        "runtime": "macos_launchagent",
        "broker_capability": "codex_provider_broker",
        "runner_capability": "runner:codex",
        "readiness_schema": CODEX_READINESS_SCHEMA,
    },
}
CODEX_FACTORY_RUNNER_CONTRACT = {
    "provider": "codex",
    "model": CODEX_PROVIDER_MODEL,
    "display_name": "Codex authenticated runner",
    "authorization_mode": "node_managed",
    "authorization_flow": "browser_device",
    "user_authorization_required": False,
    "permission_mode": "task_contract",
    "output_format": "jsonl",
    "worktree_scoped": True,
    "factory_provider_contract": FACTORY_PROVIDER_RUNNER_CONTRACT,
    "prompt_transport": "stdin",
    "sandbox": "read-only",
    "network_access": "provider_managed_search",
}


def load_external_provider_actor_auth_record() -> dict[str, Any] | None:
    configured = str(os.environ.get("FACTORY_EXTERNAL_PROVIDER_ACTOR_TOKEN_SHA256") or "").strip().lower()
    if configured:
        node_id = str(os.environ.get("FACTORY_EXTERNAL_PROVIDER_ACTOR_NODE_ID") or "").strip()
        credential_id = str(os.environ.get("FACTORY_EXTERNAL_PROVIDER_ACTOR_CREDENTIAL_ID") or "").strip()
        if not (
            re.fullmatch(r"[a-f0-9]{64}", configured)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", node_id)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", credential_id)
        ):
            return None
        try:
            epoch = max(1, int(os.environ.get("FACTORY_EXTERNAL_PROVIDER_ACTOR_EPOCH", "1")))
        except ValueError:
            return None
        return {
            "token_sha256": configured,
            "node_id": node_id,
            "credential_id": credential_id,
            "epoch": epoch,
        }
    try:
        info = EXTERNAL_PROVIDER_AUTH_HASH_FILE.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != 0
            or info.st_size > 1024
        ):
            return None
        payload = json.loads(EXTERNAL_PROVIDER_AUTH_HASH_FILE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version", "credential_id", "node_id", "epoch", "token_sha256",
    }:
        return None
    if payload.get("schema_version") != "kolibri.external-provider-credential.v1":
        return None
    token_hash = str(payload.get("token_sha256") or "").lower()
    node_id = str(payload.get("node_id") or "")
    credential_id = str(payload.get("credential_id") or "")
    epoch = payload.get("epoch")
    if not (
        re.fullmatch(r"[a-f0-9]{64}", token_hash)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", node_id)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", credential_id)
        and type(epoch) is int and epoch >= 1
    ):
        return None
    return {
        "token_sha256": token_hash,
        "node_id": node_id,
        "credential_id": credential_id,
        "epoch": epoch,
    }


_external_provider_actor_auth_record = load_external_provider_actor_auth_record()


def configure_external_provider_actor_token_sha256(
    value: str | None,
    *,
    node_id: str = "mac-codex-provider",
    credential_id: str = "mac-codex-provider-v1",
    epoch: int = 1,
) -> None:
    """Test/configuration seam. The raw bearer is never accepted here."""

    global _external_provider_actor_auth_record
    normalized = str(value or "").strip().lower()
    _external_provider_actor_auth_record = (
        {
            "token_sha256": normalized,
            "node_id": node_id,
            "credential_id": credential_id,
            "epoch": epoch,
        }
        if (
            re.fullmatch(r"[a-f0-9]{64}", normalized)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", node_id)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", credential_id)
            and type(epoch) is int and epoch >= 1
        )
        else None
    )


class IdempotencyConflict(ValueError):
    def __init__(self, idempotency_key: str, existing_task_id: str):
        super().__init__("idempotency_key_payload_conflict")
        self.idempotency_key = idempotency_key
        self.existing_task_id = existing_task_id


class TaskTargetValidationError(ValueError):
    """A task names a target outside the current authenticated scheduler view."""

    code = "task_target_not_canonical"

    def __init__(self, target_node: str, reason: str):
        super().__init__(self.code)
        self.target_node = target_node
        self.reason = reason

    def as_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "target_node": self.target_node,
            "reason": self.reason,
            "membership_authority": "replicated_mesh_manifest",
            "normalization_performed": False,
        }

DEFAULT_WORKER_API_PATHS = ["fabric_api", "agent_host_api", "fallback_relay"]
HOME_CONTROL_PLANE_API_PATHS = ["fabric_api", "control_plane_api", "artifact_api"]

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


def _safe_record_id(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", text):
        raise ValueError(f"invalid_{field_name}")
    return text


def owner_approval_key(approval_id: str) -> str:
    return key(f"owner_approval:{approval_id}")


def release_task_ids_key(release_id: str) -> str:
    return key(f"release:{release_id}:task_ids")


def canonical_owner_approval_payload(body: dict[str, Any]) -> dict[str, Any]:
    return authority_owner_approval_payload(
        body,
        now=now_ts(),
        max_ttl_seconds=OWNER_APPROVAL_MAX_TTL,
    )


def canonical_owner_approval_bytes(payload: dict[str, Any]) -> bytes:
    return authority_owner_approval_bytes(payload)


def verify_owner_approval(body: dict[str, Any]) -> dict[str, Any]:
    payload = canonical_owner_approval_payload(body)
    signature = body.get("signature")
    if not isinstance(signature, str) or not signature.startswith("-----BEGIN SSH SIGNATURE-----"):
        raise ValueError("owner_approval_signature_missing")
    if len(signature.encode("utf-8")) > 32 * 1024:
        raise ValueError("owner_approval_signature_too_large")
    if not OWNER_ALLOWED_SIGNERS.is_file():
        raise ValueError("owner_allowed_signers_unavailable")
    signature_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="kolibri-owner-approval-",
            suffix=".sig",
            delete=False,
        ) as handle:
            handle.write(signature)
            signature_path = handle.name
        os.chmod(signature_path, 0o600)
        completed = subprocess.run(
            [
                "ssh-keygen", "-Y", "verify",
                "-f", str(OWNER_ALLOWED_SIGNERS),
                "-I", payload["signer_identity"],
                "-n", OWNER_APPROVAL_NAMESPACE,
                "-s", signature_path,
            ],
            input=canonical_owner_approval_bytes(payload),
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("owner_approval_verifier_unavailable") from exc
    finally:
        if signature_path:
            try:
                Path(signature_path).unlink()
            except OSError:
                pass
    if completed.returncode != 0:
        raise ValueError("owner_approval_signature_invalid")
    created_at = utc_now()
    attestation = {
        "schema_version": OWNER_APPROVAL_ATTESTATION_SCHEMA,
        "payload": payload,
        "signature": signature,
    }
    return {
        **payload,
        "status": payload["decision"],
        "approved_by": {
            "role": "owner",
            "identity": payload["signer_identity"],
        },
        "signature": {
            "format": "sshsig",
            "namespace": OWNER_APPROVAL_NAMESPACE,
            "sha256": hashlib.sha256(signature.encode("utf-8")).hexdigest(),
        },
        "attestation": attestation,
        "attestation_digest": approval_attestation_digest(attestation),
        "created_at": created_at,
    }


def save_owner_approval(record: dict[str, Any]) -> None:
    expires_ts = parse_iso_ts(record.get("expires_at"))
    if expires_ts is None:
        raise ValueError("owner_approval_expiry_invalid")
    existing = get_json(owner_approval_key(record["approval_id"]), {})
    if existing and existing.get("attestation_digest") != record.get("attestation_digest"):
        raise ValueError("owner_approval_id_collision")
    ttl = max(1, min(OWNER_APPROVAL_MAX_TTL, int(expires_ts - now_ts())))
    redis.command(
        "SET",
        owner_approval_key(record["approval_id"]),
        json.dumps(record, sort_keys=True, separators=(",", ":")),
        "EX",
        ttl,
    )
    redis.command("SADD", key("owner_approval_ids"), record["approval_id"])


def list_owner_approvals() -> list[dict[str, Any]]:
    approval_ids = sorted(redis.command("SMEMBERS", key("owner_approval_ids")) or [])
    values = get_json_many([owner_approval_key(approval_id) for approval_id in approval_ids])
    return sorted(
        (value for value in values if isinstance(value, dict)),
        key=lambda item: str(item.get("created_at") or ""),
        reverse=True,
    )


def verify_stored_owner_approval(record: dict[str, Any]) -> dict[str, Any]:
    try:
        attestation = canonical_owner_approval_attestation(
            record.get("attestation"),
            now=now_ts(),
            max_ttl_seconds=OWNER_APPROVAL_MAX_TTL,
        )
    except ReleaseAuthorityError as exc:
        raise ValueError(str(exc)) from exc
    if record.get("attestation_digest") != approval_attestation_digest(attestation):
        raise ValueError("owner_approval_attestation_digest_mismatch")
    verified = verify_owner_approval({**attestation["payload"], "signature": attestation["signature"]})
    if (
        verified["approval_id"] != record.get("approval_id")
        or verified["attestation_digest"] != record.get("attestation_digest")
    ):
        raise ValueError("owner_approval_record_mismatch")
    return verified


def authorize_release_task(envelope: dict[str, Any]) -> dict[str, Any]:
    value = dict(envelope)
    approval_id = _safe_record_id(value.get("approval_id"), "approval_id")
    stored = get_json(owner_approval_key(approval_id), {})
    if not stored:
        raise ValueError("release_owner_approval_not_found")
    approval = verify_stored_owner_approval(stored)
    artifact_uri = str(value.get("artifact_uri") or "")
    parsed_artifact = urlparse(artifact_uri)
    if (
        parsed_artifact.scheme != "artifact"
        or parsed_artifact.query
        or parsed_artifact.fragment
        or parsed_artifact.username
        or parsed_artifact.password
    ):
        raise ValueError("release_artifact_transport_forbidden")
    signature = value.get("signature")
    if not isinstance(signature, dict):
        raise ValueError("release_task_signature_contract_invalid")
    value["signature"] = {
        "format": signature.get("format"),
        "namespace": signature.get("namespace"),
        "signer_identity": signature.get("signer_identity"),
    }
    try:
        validate_approval_for_task(approval, value)
    except ReleaseAuthorityError as exc:
        raise ValueError(str(exc)) from exc
    value["approval_attestation"] = approval["attestation"]
    value["approval_attestation_digest"] = approval["attestation_digest"]
    return value


def release_health(release_id: str, node_id: str) -> dict[str, Any]:
    release_id = _safe_record_id(release_id, "release_id")
    node_id = _safe_record_id(node_id, "node_id")
    task_ids = redis.command("SMEMBERS", release_task_ids_key(release_id)) or []
    tasks = [task for task in get_json_many([task_key(task_id) for task_id in task_ids]) if task]
    matching = []
    for task in tasks:
        envelope = task.get("envelope") if isinstance(task.get("envelope"), dict) else {}
        target = str(envelope.get("target_node") or "")
        task_release = str(envelope.get("release_id") or envelope.get("rollback_to_release_id") or "")
        if target == node_id and task_release == release_id:
            matching.append(task)
    matching.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    if not matching:
        return {
            "status": "unknown",
            "release_id": release_id,
            "node_id": node_id,
            "reason": "release_task_not_found",
        }
    latest = matching[0]
    result = latest.get("result") if isinstance(latest.get("result"), dict) else {}
    health = result.get("release_health") if isinstance(result.get("release_health"), dict) else {}
    manifest_digest = str(result.get("manifest_digest") or health.get("manifest_digest") or "")
    healthy = (
        latest.get("state") == STATE_COMPLETED
        and result.get("status") == "completed"
        and health.get("status") == "healthy"
        and bool(manifest_digest)
    )
    return {
        "status": "healthy" if healthy else "pending" if latest.get("state") not in TERMINAL_STATES else "failed",
        "release_id": release_id,
        "node_id": node_id,
        "manifest_digest": manifest_digest,
        "task_id": latest.get("task_id"),
        "task_state": latest.get("state"),
        "checked_at": utc_now(),
    }


def key(name: str) -> str:
    return f"{NAMESPACE}:{name}"


class RedisError(RuntimeError):
    pass


class Redis:
    def __init__(
        self,
        host: str = REDIS_HOST,
        port: int = REDIS_PORT,
        timeout: float = 5.0,
        pool_size: int = 64,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.pool_size = max(1, int(pool_size))
        self._pool: queue.LifoQueue[tuple[socket.socket, Any]] = queue.LifoQueue(self.pool_size)
        self._slots = threading.BoundedSemaphore(self.pool_size)

    def _connect(self) -> tuple[socket.socket, Any]:
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.settimeout(self.timeout)
        return sock, sock.makefile("rb")

    @staticmethod
    def _close(connection: tuple[socket.socket, Any]) -> None:
        sock, reader = connection
        try:
            reader.close()
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    def command(self, *parts: Any) -> Any:
        command_name = str(parts[0] if parts else "").strip().upper()
        if CANARY_READ_ONLY and command_name not in CANARY_REDIS_READ_COMMANDS:
            raise RedisError("factory_canary_read_only_command_forbidden")
        payload = self._encode(parts)
        last_error: Exception | None = None
        for _attempt in range(2):
            with self._slots:
                try:
                    connection = self._pool.get_nowait()
                except queue.Empty:
                    connection = self._connect()
                sock, reader = connection
                try:
                    sock.sendall(payload)
                    result = self._read(reader)
                except (OSError, RedisError, ValueError) as exc:
                    last_error = exc
                    self._close(connection)
                    continue
                try:
                    self._pool.put_nowait(connection)
                except queue.Full:  # pragma: no cover - defensive only
                    self._close(connection)
                return result
        raise RedisError(f"redis command failed after reconnect: {last_error}") from last_error

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
mesh_membership = MeshMembershipSource()


def configure_mesh_membership(path: str | Path) -> None:
    """Replace the manifest source (used by tests and controlled startup)."""

    global mesh_membership
    mesh_membership = MeshMembershipSource(path)


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


def add_evidence(
    claim_id: str,
    ev_type: str,
    source: str,
    summary: str = "",
    path: str = "",
    *,
    content_hash: str = "",
) -> Evidence:
    e = Evidence(
        evidence_id=_id("E"),
        claim_id=claim_id,
        type=ev_type,
        source=source,
        summary=summary,
        path=path,
        content_hash=content_hash,
    )
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


def canonical_json_sha256(value: Any) -> str:
    """Hash one JSON value using a stable, whitespace-free representation."""

    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("completion_result_not_canonical_json") from exc
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def completion_binding_payload(
    task: dict[str, Any],
    result_reference: str,
    result_sha256: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": COMPLETION_BINDING_SCHEMA,
        "task_id": str(task.get("task_id") or ""),
        "attempt_id": str(task.get("attempt_id") or ""),
        "lease_owner": str(task.get("lease_owner") or ""),
        "result_reference": result_reference,
        "result_sha256": result_sha256,
    }
    # Pre-migration task proofs used this schema without a numeric fencing
    # token. Keep those persisted proofs verifiable, but bind every task
    # created or re-leased by this runtime to its authoritative token.
    if task_requires_fencing_token(task):
        payload["fencing_token"] = task.get("fencing_token")
    return payload


def completion_binding_sha256(
    task: dict[str, Any],
    result_reference: str,
    result_sha256: str,
) -> str:
    return canonical_json_sha256(
        completion_binding_payload(task, result_reference, result_sha256)
    )


def _supplied_completion_digest(body: dict[str, Any], name: str) -> str | None:
    direct = body.get(name)
    supplied = body.get("completion_evidence")
    nested = supplied.get(name) if isinstance(supplied, dict) else None
    values = [str(value).strip().lower() for value in (direct, nested) if value is not None]
    if len(set(values)) > 1:
        return "__conflicting__"
    return values[0] if values else None


def verify_task_completion(
    task: dict[str, Any],
    result: Any,
    body: dict[str, Any],
    result_reference: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Independently bind a completion to the authoritative task attempt."""

    task_id = str(task.get("task_id") or "")
    attempt_id = str(task.get("attempt_id") or "")
    lease_owner = str(task.get("lease_owner") or "")
    expected_node, separator, expected_agent = lease_owner.partition(":")
    node_id = str(body.get("node_id") or "")
    agent_id = str(body.get("agent_id") or "")
    reference = str(result_reference or "").strip()
    result_is_object = isinstance(result, dict) and bool(result)
    result_object = result if isinstance(result, dict) else {}
    try:
        result_digest = canonical_json_sha256(result)
    except ValueError:
        result_digest = ""
    binding_digest = (
        completion_binding_sha256(task, reference, result_digest)
        if result_digest and reference
        else ""
    )
    target_node = str(
        (task.get("envelope") or {}).get("target_node")
        or (task.get("envelope") or {}).get("required_node")
        or ""
    )
    status = str(result_object.get("status") or "").strip().lower()
    result_path = result_object.get("result_path")
    token_required = task_requires_fencing_token(task)
    expected_fencing_token = task.get("fencing_token")
    checks = {
        "task": bool(
            task_id
            and task.get("state") in {STATE_LEASED, STATE_RUNNING, STATE_REVIEW}
            and (body.get("task_id") is None or str(body.get("task_id")) == task_id)
            and (result_object.get("task_id") is None or str(result_object.get("task_id")) == task_id)
        ),
        "result": result_is_object,
        "attempt": bool(
            attempt_id
            and str(body.get("attempt_id") or "") == attempt_id
            and (
                result_object.get("attempt_id") is None
                or str(result_object.get("attempt_id")) == attempt_id
            )
        ),
        "node": bool(
            expected_node
            and separator
            and node_id == expected_node
            and (not target_node or target_node == node_id)
            and (result_object.get("node_id") is None or str(result_object.get("node_id")) == node_id)
        ),
        "agent": bool(
            expected_agent
            and agent_id == expected_agent
            and (result_object.get("agent_id") is None or str(result_object.get("agent_id")) == agent_id)
        ),
        "status": status in COMPLETION_SUCCESS_STATUSES,
        "result_reference": bool(
            reference
            and (result_path is None or str(result_path).strip() == reference)
        ),
        "result_sha256": bool(result_digest),
        "binding_sha256": bool(binding_digest),
    }
    if token_required:
        checks["fencing_token"] = bool(
            type(expected_fencing_token) is int
            and expected_fencing_token > 0
            and type(body.get("fencing_token")) is int
            and body.get("fencing_token") == expected_fencing_token
            and type(result_object.get("fencing_token")) is int
            and result_object.get("fencing_token") == expected_fencing_token
        )
    supplied_result_digest = _supplied_completion_digest(body, "result_sha256")
    supplied_binding_digest = _supplied_completion_digest(body, "binding_sha256")
    if supplied_result_digest is not None:
        checks["result_sha256"] = bool(
            checks["result_sha256"] and supplied_result_digest == result_digest
        )
    if supplied_binding_digest is not None:
        checks["binding_sha256"] = bool(
            checks["binding_sha256"] and supplied_binding_digest == binding_digest
        )
    failed_checks = sorted(name for name, passed in checks.items() if not passed)
    evidence = {
        "schema_version": COMPLETION_EVIDENCE_SCHEMA,
        "task_id": task_id,
        "attempt_id": attempt_id,
        "lease_owner": lease_owner,
        "node_id": node_id,
        "agent_id": agent_id,
        "result_reference": reference,
        "result_sha256": result_digest,
        "binding_sha256": binding_digest,
    }
    verifier = {
        "schema_version": COMPLETION_VERIFIER_SCHEMA,
        "verifier": "control-plane/home",
        "independent": True,
        "verdict": "passed" if not failed_checks else "failed",
        "checked_at": utc_now(),
        "task_id": task_id,
        "attempt_id": attempt_id,
        "lease_owner": lease_owner,
        "node_id": node_id,
        "agent_id": agent_id,
        "result_reference": reference,
        "result_sha256": result_digest,
        "binding_sha256": binding_digest,
        "checks": checks,
        "failed_checks": failed_checks,
    }
    if token_required:
        evidence["fencing_token"] = expected_fencing_token
        verifier["fencing_token"] = expected_fencing_token
    return evidence, verifier


def strict_completion_proof(task: dict[str, Any]) -> bool:
    """Recompute stored hashes; never trust a persisted verdict by itself."""

    if task.get("state") != STATE_COMPLETED or not isinstance(task.get("result"), dict):
        return False
    evidence = task.get("completion_evidence")
    verifier = task.get("completion_verifier")
    if not isinstance(evidence, dict) or not isinstance(verifier, dict):
        return False
    reference = str(task.get("result_reference") or "").strip()
    try:
        result_digest = canonical_json_sha256(task["result"])
        binding_digest = completion_binding_sha256(task, reference, result_digest)
    except ValueError:
        return False
    checks = verifier.get("checks") if isinstance(verifier.get("checks"), dict) else {}
    token_required = task_requires_fencing_token(task)
    token_binding_valid = True
    if token_required:
        expected_fencing_token = task.get("fencing_token")
        token_binding_valid = bool(
            type(expected_fencing_token) is int
            and expected_fencing_token > 0
            and task["result"].get("fencing_token") == expected_fencing_token
            and evidence.get("fencing_token") == expected_fencing_token
            and verifier.get("fencing_token") == expected_fencing_token
            and checks.get("fencing_token") is True
        )
    return bool(
        evidence.get("schema_version") == COMPLETION_EVIDENCE_SCHEMA
        and verifier.get("schema_version") == COMPLETION_VERIFIER_SCHEMA
        and verifier.get("verifier") == "control-plane/home"
        and verifier.get("independent") is True
        and verifier.get("verdict") == "passed"
        and checks
        and all(value is True for value in checks.values())
        and evidence.get("task_id") == task.get("task_id")
        and evidence.get("attempt_id") == task.get("attempt_id")
        and evidence.get("lease_owner") == task.get("lease_owner")
        and evidence.get("result_reference") == reference
        and evidence.get("result_sha256") == result_digest
        and evidence.get("binding_sha256") == binding_digest
        and verifier.get("result_sha256") == result_digest
        and verifier.get("binding_sha256") == binding_digest
        and token_binding_valid
    )

def truth_gate_on_complete(task: dict, result: dict) -> dict:
    """Persist the independent completion verifier in the Truth ledger."""
    task_id = task.get("task_id", "unknown")
    claim = create_claim(task_id, task.get("lease_owner", "agent"), f"Task {task_id} completed", "task")
    verifier = task.get("completion_verifier") or {}
    evidence = task.get("completion_evidence") or {}
    passed = bool(
        verifier.get("verdict") == "passed"
        and evidence.get("result_sha256")
        and evidence.get("binding_sha256")
    )
    if evidence.get("result_sha256"):
        add_evidence(
            claim.claim_id,
            "result_content",
            "canonical task result",
            "canonical result payload hash",
            content_hash=str(evidence["result_sha256"]),
        )
    if evidence.get("binding_sha256"):
        add_evidence(
            claim.claim_id,
            "attempt_binding",
            "control-plane/home",
            "task/attempt/lease/result-reference binding",
            content_hash=str(evidence["binding_sha256"]),
        )
    add_evidence(
        claim.claim_id,
        "control_plane_verifier",
        "control-plane/home",
        f"verdict={verifier.get('verdict', 'failed')}",
        content_hash=str(evidence.get("binding_sha256") or ""),
    )
    v = set_verdict(
        claim.claim_id,
        "true" if passed else "not_proven",
        "high" if passed else "low",
        "Independent Control Plane completion verifier passed"
        if passed else "Independent Control Plane completion verifier failed",
    )
    task["truth_gate"] = {
        "claim_id": claim.claim_id,
        "verdict": v.verdict,
        "confidence": v.confidence,
        "evidence_count": len(claim.evidence),
        "verifier_schema": verifier.get("schema_version"),
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


def enforce_completion_truth_state(task: dict[str, Any], desired_state: str) -> dict[str, Any]:
    """Prevent a terminal completion claim when its evidence is insufficient."""
    verdict = (task.get("truth_gate") or {}).get("verdict")
    if desired_state == STATE_COMPLETED and verdict != "true":
        task["state"] = STATE_WAITING_REVIEW
        task["error_type"] = "completion_not_verified"
        task["error"] = "completion evidence did not pass the truth gate"
    else:
        task["state"] = desired_state
        if desired_state == STATE_COMPLETED:
            task["error_type"] = None
            task["error"] = None
    return task


# ── Redis helpers ──────────────────────────────────────────────────────

def get_json(redis_key: str, default: Any = None) -> Any:
    raw = redis.command("GET", redis_key)
    if raw is None:
        return default
    return json.loads(raw)


def get_json_many(redis_keys: list[str]) -> list[Any]:
    """Fetch a Redis collection in one round trip.

    Fleet and task views are polled continuously by both the UI and workers.
    Batching avoids turning a status request into hundreds of Redis
    connections when historical node cards are present.
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


def audit_registered_nodes(current: float | None = None) -> list[dict[str, Any]]:
    """Return every Agent Host card retained in Redis for audit purposes."""

    node_ids = sorted(redis.command("SMEMBERS", key("node_ids")) or [])
    raw_nodes = get_json_many([node_key(node_id) for node_id in node_ids])
    drains = redis.command("MGET", *[drain_key(node_id) for node_id in node_ids]) if node_ids else []
    observed_at = now_ts() if current is None else current
    nodes = []
    for node_id, raw_node, draining in zip(node_ids, raw_nodes, drains):
        record_present = isinstance(raw_node, dict)
        node = dict(raw_node) if record_present else {}
        # The Redis set member is the immutable audit identity.  A payload may
        # not impersonate another canonical member by changing ``node_id``.
        node["node_id"] = node_id
        node["runtime_record_present"] = record_present
        node["draining"] = bool(draining)
        nodes.append(classify_node_freshness(node, observed_at))
    return nodes


def build_canonical_fleet_view(
    *,
    audit_nodes: list[dict[str, Any]] | None = None,
    current: float | None = None,
) -> dict[str, Any]:
    """Reconcile mesh authority with Redis observations without deleting audit.

    The active list always has exactly one row per live mesh peer.  A peer
    without an Agent Host observation is represented by a non-schedulable,
    quarantined placeholder.  Redis-only identities are retained solely in
    ``historical``.
    """

    snapshot = mesh_membership.load()
    observed_at = now_ts() if current is None else current
    audit = audit_registered_nodes(observed_at) if audit_nodes is None else [dict(item) for item in audit_nodes]
    audit_by_id = {
        str(node.get("node_id") or ""): node
        for node in audit
        if str(node.get("node_id") or "")
    }
    canonical_ids = set(snapshot.by_id)
    active: list[dict[str, Any]] = []
    registered_total = 0
    missing_total = 0

    for member in snapshot.members:
        raw = audit_by_id.get(member.node_id)
        if raw is None or raw.get("runtime_record_present") is False:
            missing_total += 1
            active.append({
                "node_id": member.node_id,
                "hostname": member.node_id,
                "mesh_ip": member.mesh_ip,
                "internal_ip": member.mesh_ip,
                "capabilities": [],
                "runners": {},
                "health": "quarantined",
                "reported_health": "missing",
                "freshness": "stale",
                "heartbeat_age_seconds": None,
                "heartbeat_at": None,
                "draining": False,
                "registered": False,
                "schedulable": False,
                "lifecycle": "quarantined",
                "membership_scope": "active",
                "membership_state": "missing_agent_host_registration",
                "quarantine_reason": "canonical_member_missing_agent_host_registration",
            })
            continue

        registered_total += 1
        node = dict(raw)
        # ``audit_nodes`` is an injection seam for pure tests, so ensure its
        # records receive the same freshness classification as Redis records.
        if node.get("freshness") not in {"fresh", "degraded", "stale"}:
            node = classify_node_freshness(node, observed_at)
        node.update({
            "node_id": member.node_id,
            "mesh_ip": member.mesh_ip,
            "internal_ip": member.mesh_ip,
            "registered": True,
            "membership_scope": "active",
            "membership_state": "registered",
            "archived": False,
        })
        ready_health = str(node.get("health") or "").lower() in {"online", "healthy", "ready"}
        node["schedulable"] = bool(
            node.get("freshness") == "fresh"
            and ready_health
            and not node.get("draining")
        )
        if node["schedulable"]:
            node["lifecycle"] = "active"
        elif node.get("freshness") == "stale":
            node["lifecycle"] = "stale"
        else:
            node["lifecycle"] = "degraded"
        active.append(node)

    historical: list[dict[str, Any]] = []
    for raw in audit:
        node_id = str(raw.get("node_id") or "")
        if node_id in canonical_ids:
            continue
        node = dict(raw)
        if node.get("freshness") not in {"fresh", "degraded", "stale"}:
            node = classify_node_freshness(node, observed_at)
        node.update({
            "node_id": node_id,
            "registered": node.get("runtime_record_present") is not False,
            "schedulable": False,
            "membership_scope": "audit",
            "membership_state": "archived",
            "lifecycle": "archived",
            "archived": True,
            "archive_reason": "not_in_canonical_mesh_manifest",
        })
        historical.append(node)

    active.sort(key=lambda item: (item.get("node_id") != "home", str(item.get("node_id"))))
    historical.sort(key=lambda item: str(item.get("node_id")))
    membership = {
        **snapshot.metadata(),
        "registered_total": registered_total,
        "missing_total": missing_total,
        "historical_total": len(historical),
        "archived_total": len(historical),
        "schedulable_total": sum(1 for node in active if node.get("schedulable") is True),
    }
    return {"active": active, "historical": historical, "membership": membership}


def registered_nodes() -> list[dict[str, Any]]:
    """Return canonical active membership only (including safe placeholders)."""

    return build_canonical_fleet_view()["active"]


def node_membership_annotation(node_id: str) -> dict[str, Any]:
    """Classify a runtime observation without allowing it to create membership."""

    snapshot = mesh_membership.load()
    member = snapshot.by_id.get(node_id) if node_id == str(node_id).strip() else None
    if member is None:
        return {
            "membership_scope": "audit",
            "membership_state": "archived",
            "archived": True,
            "schedulable": False,
            "archive_reason": "not_in_canonical_mesh_manifest",
        }
    return {
        "membership_scope": "active",
        "membership_state": "registered",
        "archived": False,
        "mesh_ip": member.mesh_ip,
        "internal_ip": member.mesh_ip,
    }


def canonical_nodes_payload(
    scope: str = "active",
    *,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Build the paginated public/audit membership contract."""

    if scope not in {"active", "audit", "all"}:
        raise ValueError("node_membership_scope_invalid")
    view = build_canonical_fleet_view()
    selected = (
        view["active"]
        if scope == "active"
        else view["historical"]
        if scope == "audit"
        else view["active"] + view["historical"]
    )
    bounded_limit = min(max(int(limit), 1), 250)
    bounded_offset = max(int(offset), 0)
    page = selected[bounded_offset:bounded_offset + bounded_limit]
    counts = node_health_counts(selected)
    return {
        "nodes": page,
        "scope": scope,
        "counts": counts,
        "freshness": counts,
        "active_counts": node_health_counts(view["active"]),
        "audit_counts": node_health_counts(view["historical"]),
        "membership": view["membership"],
        "pagination": {
            "limit": bounded_limit,
            "offset": bounded_offset,
            "returned": len(page),
            "total_indexed": len(selected),
        },
    }


def _passed_codex_probe(probe: Any) -> bool:
    if not isinstance(probe, dict) or set(probe) != {
        "model", "sandbox", "status", "duration_ms", "output_sha256",
    }:
        return False
    duration = probe.get("duration_ms")
    return bool(
        probe.get("model") == CODEX_PROVIDER_MODEL
        and probe.get("sandbox") == "read-only"
        and probe.get("status") == "passed"
        and type(duration) is int
        and 0 <= duration <= 60_000
        and re.fullmatch(r"[a-f0-9]{64}", str(probe.get("output_sha256") or ""))
    )


def _passed_codex_readiness(node_id: str, readiness: Any) -> bool:
    """Validate the strict, redacted readiness evidence used for leasing."""

    allowed = {
        "schema_version", "node_id", "checked_at", "access_mode", "status",
        "login_status", "error_type", "broker_ref", "probe",
    }
    required = {
        "schema_version", "node_id", "checked_at", "access_mode", "status",
        "login_status", "probe",
    }
    if not isinstance(readiness, dict):
        return False
    if set(readiness) - allowed or not required.issubset(readiness):
        return False
    checked_at = parse_iso_ts(readiness.get("checked_at"))
    current = now_ts()
    if (
        checked_at is None
        or checked_at > current + EXTERNAL_PROVIDER_READINESS_FUTURE_GRACE_SECONDS
        or current - checked_at > EXTERNAL_PROVIDER_READINESS_MAX_AGE_SECONDS
    ):
        return False
    if readiness.get("schema_version") != CODEX_READINESS_SCHEMA:
        return False
    if readiness.get("node_id") != node_id:
        return False
    if readiness.get("access_mode") != "local_service_account":
        return False
    if readiness.get("status") != "available" or readiness.get("login_status") != "authenticated":
        return False
    if readiness.get("error_type") not in {None, ""} or readiness.get("broker_ref") is not None:
        return False
    return _passed_codex_probe(readiness.get("probe"))


def _exact_codex_runner_contract(runner: Any) -> bool:
    if not isinstance(runner, dict):
        return False
    if any(runner.get(field) != expected for field, expected in CODEX_FACTORY_RUNNER_CONTRACT.items()):
        return False
    if runner.get("status") != "available":
        return False
    if runner.get("readiness_contract") != CODEX_READINESS_SCHEMA:
        return False
    if runner.get("access_mode") != "local_service_account":
        return False
    if runner.get("login_status") != "authenticated":
        return False
    if runner.get("error_type") not in {None, ""}:
        return False
    checked_at = parse_iso_ts(runner.get("checked_at"))
    current = now_ts()
    if (
        checked_at is None
        or checked_at > current + EXTERNAL_PROVIDER_READINESS_FUTURE_GRACE_SECONDS
        or current - checked_at > EXTERNAL_PROVIDER_READINESS_MAX_AGE_SECONDS
    ):
        return False
    return _passed_codex_probe(runner.get("probe"))


def external_provider_actor_identity(node_id: str, node: Any) -> str | None:
    if not isinstance(node, dict):
        return None
    labels = node.get("labels") if isinstance(node.get("labels"), dict) else {}
    provider = str(labels.get("provider") or "").strip().lower()
    spec = EXTERNAL_PROVIDER_ACTOR_SPECS.get(provider)
    if not spec:
        return None
    if labels.get("runtime") != spec["runtime"] or labels.get("physical_node_id") != node_id:
        return None
    return provider


def external_provider_actor_auth_marker(node_id: str) -> dict[str, Any] | None:
    record = _external_provider_actor_auth_record
    if record is None or record.get("node_id") != node_id:
        return None
    return {
        "actor_scope": EXTERNAL_PROVIDER_ACTOR_SCOPE,
        "bound_node_id": node_id,
        "credential_id": record["credential_id"],
        "epoch": record["epoch"],
    }


def has_external_provider_actor_marker(node_id: str, node: Any) -> bool:
    marker = node.get("external_provider_auth") if isinstance(node, dict) else None
    return bool(
        isinstance(marker, dict)
        and marker.get("actor_scope") == EXTERNAL_PROVIDER_ACTOR_SCOPE
        and marker.get("bound_node_id") == node_id
    )


def require_external_provider_actor_auth(
    handler: BaseHTTPRequestHandler,
    node_id: str,
    node: Any,
    body: dict[str, Any],
    *,
    allow_marker_upgrade: bool = False,
) -> bool:
    """Authenticate an audit-only provider mutation without reflecting secrets."""

    is_external = (
        external_provider_actor_identity(node_id, node) is not None
        or has_external_provider_actor_marker(node_id, node)
    )
    if not is_external:
        return True
    record = _external_provider_actor_auth_record
    if record is None:
        response(handler, 503, {"error": "external_provider_actor_auth_unconfigured"})
        return False
    if record.get("node_id") != node_id:
        response(handler, 403, {"error": "external_provider_actor_node_binding_invalid"})
        return False
    marker = node.get("external_provider_auth") if isinstance(node, dict) else None
    marker_mismatch = isinstance(marker, dict) and (
        marker.get("credential_id") != record.get("credential_id")
        or marker.get("epoch") != record.get("epoch")
    )
    if marker_mismatch and not (
        allow_marker_upgrade
        and type(marker.get("epoch")) is int
        and int(record.get("epoch") or 0) > marker["epoch"]
    ):
        response(handler, 403, {"error": "external_provider_actor_credential_epoch_invalid"})
        return False
    authorization = str(handler.headers.get("Authorization") or "")
    scheme, separator, bearer_credential = authorization.partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not re.fullmatch(r"[A-Za-z0-9._~-]{32,512}", bearer_credential)
    ):
        response(handler, 401, {"error": "external_provider_actor_auth_required"})
        return False
    candidate = hashlib.sha256(bearer_credential.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(candidate, str(record["token_sha256"])):
        response(handler, 401, {"error": "external_provider_actor_auth_invalid"})
        return False
    timestamp_raw = str(handler.headers.get("X-Kolibri-Actor-Timestamp") or "")
    nonce = str(handler.headers.get("X-Kolibri-Actor-Nonce") or "")
    signature = str(handler.headers.get("X-Kolibri-Actor-Signature") or "").lower()
    signed_node = str(handler.headers.get("X-Kolibri-Actor-Node") or "")
    signed_contract = str(handler.headers.get("X-Kolibri-Actor-Contract") or "")
    signed_credential_id = str(handler.headers.get("X-Kolibri-Actor-Credential") or "")
    signed_epoch = str(handler.headers.get("X-Kolibri-Actor-Epoch") or "")
    try:
        timestamp = int(timestamp_raw)
    except ValueError:
        timestamp = 0
    if (
        signed_node != node_id
        or signed_contract != EXTERNAL_PROVIDER_AUTH_HMAC_CONTRACT
        or signed_credential_id != str(record["credential_id"])
        or signed_epoch != str(record["epoch"])
        or abs(int(now_ts()) - timestamp) > EXTERNAL_PROVIDER_AUTH_CLOCK_SKEW_SECONDS
        or not re.fullmatch(r"[a-f0-9]{32}", nonce)
        or not re.fullmatch(r"[a-f0-9]{64}", signature)
    ):
        response(handler, 401, {"error": "external_provider_actor_signature_required"})
        return False
    body_sha256 = getattr(handler, "_kolibri_wire_body_sha256", None)
    if not isinstance(body_sha256, str):
        response(handler, 401, {"error": "external_provider_actor_wire_body_unavailable"})
        return False
    canonical = "\n".join((
        EXTERNAL_PROVIDER_AUTH_HMAC_CONTRACT,
        handler.command.upper(),
        handler.path,
        body_sha256,
        timestamp_raw,
        nonce,
        node_id,
        str(record["credential_id"]),
        str(record["epoch"]),
    ))
    expected_signature = hmac.new(
        bytes.fromhex(str(record["token_sha256"])),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        response(handler, 401, {"error": "external_provider_actor_signature_invalid"})
        return False
    nonce_key = key(
        f"external_provider_nonce:{record['credential_id']}:{record['epoch']}:{node_id}:{nonce}"
    )
    if redis.command(
        "SET", nonce_key, "1", "NX", "EX", EXTERNAL_PROVIDER_AUTH_NONCE_TTL_SECONDS,
    ) != "OK":
        response(handler, 409, {"error": "external_provider_actor_replay_rejected"})
        return False
    return True


def external_provider_actor_eligibility(
    node_id: str,
    node: Any,
    *,
    current: float | None = None,
) -> dict[str, Any]:
    """Classify one non-mesh provider adapter without promoting fleet membership."""

    if not isinstance(node, dict) or not node:
        return {"eligible": False, "reason": "external_provider_actor_not_registered"}
    expected_marker = external_provider_actor_auth_marker(node_id)
    if (
        expected_marker is None
        or node.get("external_provider_auth") != expected_marker
    ):
        return {"eligible": False, "reason": "external_provider_actor_auth_not_bound"}
    classified = classify_node_freshness({**node, "node_id": node_id}, current)
    labels = classified.get("labels") if isinstance(classified.get("labels"), dict) else {}
    provider = str(labels.get("provider") or "").strip().lower()
    spec = EXTERNAL_PROVIDER_ACTOR_SPECS.get(provider)
    if spec is None:
        return {"eligible": False, "reason": "node_not_in_canonical_mesh_membership"}
    if labels.get("runtime") != spec["runtime"]:
        return {"eligible": False, "reason": "external_provider_actor_runtime_invalid"}
    if labels.get("physical_node_id") != node_id:
        return {"eligible": False, "reason": "external_provider_actor_physical_identity_mismatch"}
    if classified.get("freshness") != "fresh":
        return {
            "eligible": False,
            "reason": "external_provider_actor_heartbeat_not_fresh",
            "node": classified,
        }
    if str(classified.get("health") or "").lower() not in {"online", "healthy", "ready"}:
        return {
            "eligible": False,
            "reason": "external_provider_actor_not_healthy",
            "node": classified,
        }
    capabilities = {
        str(item).strip().lower()
        for item in classified.get("capabilities") or []
        if isinstance(item, str)
    }
    if not {spec["broker_capability"], spec["runner_capability"]}.issubset(capabilities):
        return {"eligible": False, "reason": "external_provider_actor_capability_missing"}
    runners = classified.get("runners") if isinstance(classified.get("runners"), dict) else {}
    if provider != "codex" or not _exact_codex_runner_contract(runners.get(provider)):
        return {"eligible": False, "reason": "external_provider_actor_runner_contract_invalid"}
    readiness_map = (
        classified.get("runner_readiness")
        if isinstance(classified.get("runner_readiness"), dict)
        else {}
    )
    if not _passed_codex_readiness(node_id, readiness_map.get(provider)):
        return {"eligible": False, "reason": "external_provider_actor_readiness_invalid"}
    return {
        "eligible": True,
        "reason": "external_provider_actor_ready",
        "lease_scope": EXTERNAL_PROVIDER_ACTOR_SCOPE,
        "provider": provider,
        "node": classified,
    }


def external_provider_actor_records(runner: str, limit: int = 64) -> dict[str, Any]:
    normalized_runner = str(runner or "").strip().lower()
    if normalized_runner not in EXTERNAL_PROVIDER_ACTOR_SPECS:
        raise ValueError("provider_actor_runner_invalid")
    bounded_limit = min(max(int(limit), 1), 128)
    records: list[dict[str, Any]] = []
    if _external_provider_actor_auth_record is not None:
        for node in audit_registered_nodes():
            node_id = str(node.get("node_id") or "")
            if external_provider_actor_identity(node_id, node) != normalized_runner:
                continue
            eligibility = external_provider_actor_eligibility(node_id, node)
            if eligibility.get("eligible") is not True or node.get("draining"):
                continue
            current = eligibility["node"]
            records.append({
                "node_id": node_id,
                "hostname": str(current.get("hostname") or ""),
                "health": str(current.get("health") or ""),
                "freshness": str(current.get("freshness") or ""),
                "heartbeat_age_seconds": current.get("heartbeat_age_seconds"),
                "active_task": current.get("active_task"),
                "draining": False,
                "membership_scope": "audit",
                "actor_scope": EXTERNAL_PROVIDER_ACTOR_SCOPE,
                "external_provider_auth": dict(current["external_provider_auth"]),
                "labels": dict(current.get("labels") or {}),
                "capabilities": list(current.get("capabilities") or []),
                "runners": {normalized_runner: dict(current["runners"][normalized_runner])},
                "runner_readiness": {
                    normalized_runner: dict(current["runner_readiness"][normalized_runner])
                },
            })
    records.sort(key=lambda item: (item["heartbeat_age_seconds"], item["node_id"]))
    return {
        "runner": normalized_runner,
        "records": records[:bounded_limit],
        "auth_configured": _external_provider_actor_auth_record is not None,
        "auth_binding": (
            external_provider_actor_auth_marker(str(_external_provider_actor_auth_record["node_id"]))
            if _external_provider_actor_auth_record is not None
            else None
        ),
    }


def lease_node_eligibility(node_id: str) -> dict[str, Any]:
    """Fail closed for physical workers and tightly-scoped provider actors."""

    membership = node_membership_annotation(node_id)
    if membership.get("membership_scope") != "active":
        node = get_json(node_key(node_id), {})
        external = external_provider_actor_eligibility(node_id, node)
        if external.get("eligible") is not True:
            return external
        if redis.command("GET", drain_key(node_id)):
            return {"eligible": False, "reason": "node_draining"}
        return external
    if redis.command("GET", drain_key(node_id)):
        return {"eligible": False, "reason": "node_draining"}
    node = get_json(node_key(node_id), {})
    if not node:
        return {"eligible": False, "reason": "canonical_node_not_registered"}
    classified = classify_node_freshness({**node, "node_id": node_id})
    if classified.get("freshness") != "fresh":
        return {"eligible": False, "reason": "canonical_node_heartbeat_not_fresh", "node": classified}
    if str(classified.get("health") or "").lower() not in {"online", "healthy", "ready"}:
        return {"eligible": False, "reason": "canonical_node_not_healthy", "node": classified}
    return {
        "eligible": True,
        "reason": "canonical_node_ready",
        "lease_scope": "canonical_mesh",
        "node": node,
    }


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
    # This process is allowed to run only on canonical Home. Request payloads
    # cannot claim another Control Plane identity.
    envelope["command_node"] = "home"
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
    edges = [
        {"from": "home", "to": node["node_id"], "type": "protected_fabric_api"}
        for node in nodes
        if node["node_id"] != "home"
    ]
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
        fallback_nodes=[],
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
    if "schedulable" in node and node.get("schedulable") is not True:
        return False
    return node.get("health") == "online"


def fabric_nodes(registered_nodes: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    # Callers supply the canonical mesh-derived view.  Missing canonical
    # members remain visible as quarantined placeholders; Redis-only audit
    # identities never reach this function through ``registered_nodes()``.
    merged: dict[str, dict[str, Any]] = {}
    for registered in registered_nodes or []:
        node_id = str(registered.get("node_id") or registered.get("id") or "")
        if not node_id:
            continue
        node = {"node_id": node_id}
        node.update(registered)
        node.setdefault("display_name", registered.get("hostname") or node_id)
        if node_id == "home":
            node["role"] = "control_plane"
            node["api_paths"] = list(HOME_CONTROL_PLANE_API_PATHS)
        else:
            if node.get("role") == "control_plane":
                node["authority_rejected"] = True
            node["role"] = str(node.get("role") or "worker")
            if node["role"] == "control_plane":
                node["role"] = "worker"
            node.setdefault("api_paths", list(DEFAULT_WORKER_API_PATHS))
            node["api_paths"] = [
                path for path in node["api_paths"]
                if path not in {"control_plane_api", "artifact_api"}
            ]
        node["ssh"] = "emergency_bootstrap_diagnostic_only"
        merged[node_id] = node
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
    index_provider_health_task(task)
    if task.get("state") in {STATE_LEASED, STATE_RUNNING, STATE_REVIEW}:
        redis.command("SADD", key("active_lease_ids"), task["task_id"])
    else:
        redis.command("SREM", key("active_lease_ids"), task["task_id"])


def enqueue(task_id: str) -> None:
    redis.command("RPUSH", key("queue"), task_id)


def remove_from_queue(task_id: str) -> None:
    redis.command("LREM", key("queue"), 0, task_id)


def cancel_task_record(task: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    if task.get("state") in TERMINAL_STATES:
        return task
    was_active = task.get("state") in {STATE_LEASED, STATE_RUNNING, STATE_REVIEW}
    remove_from_queue(task["task_id"])
    task["state"] = STATE_CANCELLED
    task["cancel_requested_at"] = utc_now()
    task["cancel_requested_by"] = str(body.get("requested_by") or "owner")[:80]
    task["cancel_reason"] = str(body.get("reason") or "release_fence")[:500]
    task["cancel_fence_id"] = uuid.uuid4().hex
    task["cancel_was_active"] = was_active
    task["lease_until"] = None
    if not was_active:
        task["cancel_acknowledged_at"] = utc_now()
    save_task(task)
    return task


def acknowledge_cancelled_task(task: dict[str, Any]) -> dict[str, Any]:
    if task.get("state") == STATE_CANCELLED and not task.get("cancel_acknowledged_at"):
        task["cancel_acknowledged_at"] = utc_now()
        save_task(task)
    return task


def lease_claim_key(task_id: str) -> str:
    return key(f"lease_claim:{task_id}")


def acquire_lease_claim(task_id: str, claim_id: str) -> bool:
    return redis.command("SET", lease_claim_key(task_id), claim_id, "NX", "EX", LEASE_CLAIM_TTL) == "OK"


def release_lease_claim(task_id: str, claim_id: str) -> None:
    # Delete only our own short-lived claim. The Lua compare-and-delete keeps a
    # delayed worker from removing a newer claim after its TTL elapsed.
    redis.command(
        "EVAL",
        "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end",
        1,
        lease_claim_key(task_id),
        claim_id,
    )


def task_requires_fencing_token(task: dict[str, Any]) -> bool:
    """Return whether the task is on the monotonic fencing contract.

    The only compatibility exception is an authoritative Redis record created
    before this contract existed: it has neither the schema marker nor the
    token field. New tasks always carry both fields, so deleting or corrupting
    just one of them can never silently downgrade fencing.
    """

    return "lease_fencing_schema" in task or "fencing_token" in task


def is_pre_migration_fencing_task(task: dict[str, Any]) -> bool:
    return not task_requires_fencing_token(task)


def allocate_next_fencing_token(task: dict[str, Any]) -> int:
    """Allocate and persist-in-record the next monotonic lease token.

    Callers hold the per-task lease claim while invoking this helper. A queued
    pre-migration record is upgraded when it is next leased; an already active
    pre-migration attempt remains compatible until that attempt terminates.
    """

    if is_pre_migration_fencing_task(task):
        # The attempt counter predates fencing and is the only durable lower
        # bound available during migration. The lease path increments attempt
        # before calling us, so this never reuses an earlier conceptual token.
        token = max(1, int(task.get("attempt", 0)))
        task["lease_fencing_migrated_from"] = LEGACY_LEASE_FENCING_COMPATIBILITY
    else:
        if task.get("lease_fencing_schema") != LEASE_FENCING_SCHEMA:
            raise ValueError("lease_fencing_schema_invalid")
        current = task.get("fencing_token")
        if type(current) is not int or current < 0:
            raise ValueError("fencing_token_invalid")
        token = current + 1
    task["lease_fencing_schema"] = LEASE_FENCING_SCHEMA
    task["fencing_token"] = token
    return token


def lease_fence_error(task: dict[str, Any], body: dict[str, Any]) -> str | None:
    if not REQUIRE_LEASE_FENCING:
        return None
    expected_attempt = str(task.get("attempt_id") or "")
    if not expected_attempt or str(body.get("attempt_id") or "") != expected_attempt:
        return "attempt_id_mismatch"
    if task_requires_fencing_token(task):
        if task.get("lease_fencing_schema") != LEASE_FENCING_SCHEMA:
            return "lease_fencing_schema_invalid"
        expected_token = task.get("fencing_token")
        if type(expected_token) is not int or expected_token <= 0:
            return "fencing_token_invalid"
        if "fencing_token" not in body:
            return "fencing_token_missing"
        supplied_token = body.get("fencing_token")
        if type(supplied_token) is not int or supplied_token != expected_token:
            return "fencing_token_mismatch"
    lease_owner = str(task.get("lease_owner") or "")
    expected_node, _, expected_agent = lease_owner.partition(":")
    if not expected_node or str(body.get("node_id") or "") != expected_node:
        return "lease_node_mismatch"
    if expected_agent and str(body.get("agent_id") or "") != expected_agent:
        return "lease_agent_mismatch"
    return None


def canonical_max_attempts(
    value: dict[str, Any],
    *,
    default: int = DEFAULT_MAX_ATTEMPTS,
) -> int:
    """Return the total attempt budget for a task.

    ``max_attempts`` is the only canonical runtime field.  During the two-wave
    compatibility window an incoming legacy ``max_retries`` value is accepted
    at the HTTP boundary and translated as ``initial attempt + retries``.  A
    request carrying both spellings must describe the same budget.
    """

    raw_attempts = value.get("max_attempts")
    raw_retries = value.get("max_retries")
    if raw_attempts is None and raw_retries is None:
        raw_attempts = default
    if raw_attempts is not None and (
        isinstance(raw_attempts, bool) or not isinstance(raw_attempts, int)
    ):
        raise ValueError("max_attempts_must_be_an_integer")
    if raw_retries is not None and (
        isinstance(raw_retries, bool) or not isinstance(raw_retries, int)
    ):
        raise ValueError("max_retries_must_be_an_integer")
    if raw_retries is not None and raw_retries < 0:
        raise ValueError("max_retries_must_be_nonnegative")
    legacy_attempts = raw_retries + 1 if raw_retries is not None else None
    if raw_attempts is None:
        raw_attempts = legacy_attempts
    if legacy_attempts is not None and raw_attempts != legacy_attempts:
        raise ValueError("attempt_budget_fields_conflict")
    if raw_attempts is None or not 1 <= raw_attempts <= MAX_ATTEMPTS_LIMIT:
        raise ValueError("max_attempts_out_of_range")
    return raw_attempts


def task_max_attempts(task: dict[str, Any]) -> int:
    """Read canonical tasks and retained pre-migration Redis records safely."""

    return canonical_max_attempts(task)


def task_has_attempt_budget(task: dict[str, Any]) -> bool:
    return int(task.get("attempt", 0)) < task_max_attempts(task)


def reject_invalid_lease_fence(handler: BaseHTTPRequestHandler, task: dict[str, Any], body: dict[str, Any]) -> bool:
    reason = lease_fence_error(task, body)
    if reason is None:
        return False
    response(handler, 409, {
        "error": "lease_fence_rejected",
        "reason": reason,
        "task_id": task.get("task_id"),
        "state": task.get("state"),
        "attempt_id": task.get("attempt_id"),
        "fencing_token": task.get("fencing_token"),
    })
    return True


def normalize_task(envelope: dict[str, Any]) -> dict[str, Any]:
    task_id = envelope.get("task_id") or f"KOL-TASK-{uuid.uuid4().hex[:12]}"
    created = utc_now()
    return {
        "task_id": task_id,
        "idempotency_key": envelope.get("idempotency_key") or task_id,
        "kind": envelope.get("kind", "read_only_probe"),
        "state": STATE_QUEUED,
        "attempt": 0,
        "max_attempts": canonical_max_attempts(envelope),
        "attempt_id": None,
        "lease_fencing_schema": LEASE_FENCING_SCHEMA,
        "fencing_token": 0,
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


def runner_result_binding_error(task: dict[str, Any], body: dict[str, Any]) -> dict[str, str] | None:
    envelope = task.get("envelope") if isinstance(task.get("envelope"), dict) else {}
    requested = str(envelope.get("runner") or "").strip().lower()
    if not requested:
        return None
    result = body.get("result") if isinstance(body.get("result"), dict) else body
    actual = str(result.get("runner") or "").strip().lower()
    if actual == requested:
        return None
    return {
        "error": "runner_result_mismatch",
        "requested_runner": requested,
        "result_runner": actual or "missing",
    }


def mark_node_runner_failure(task: dict[str, Any], body: dict[str, Any]) -> None:
    error_type = body.get("error_type")
    blocked_failures = {
        "runner_auth_blocked",
        "runner_auth_failed",
        "runner_access_denied",
        "runner_policy_blocked",
        "provider_risk_control",
    }
    if error_type not in blocked_failures | {"runner_unavailable", "provider_runner_outdated"}:
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
        "status": "blocked" if error_type in blocked_failures else "unavailable",
        "error_type": error_type,
        "updated_at": utc_now(),
    }
    node["runners"] = runners
    set_json(node_key(node_id), node)


def external_provider_task_compatible(
    task: dict[str, Any],
    node_id: str,
    provider: str,
) -> bool:
    """Permit only the exact read-only Home provider-gateway envelope."""

    envelope = task.get("envelope") if isinstance(task.get("envelope"), dict) else {}
    allowed_fields = {
        "task_id", "idempotency_key", "kind", "target_node", "required_capability",
        "runner", "objective", "write_scope", "constraints", "max_attempts",
        "fallback_allowed", "source",
    }
    if set(envelope) != allowed_fields:
        return False
    if str(task.get("kind") or envelope.get("kind") or "") != "owner_remote_task":
        return False
    if envelope.get("kind") != "owner_remote_task":
        return False
    if envelope.get("target_node") != node_id:
        return False
    if envelope.get("runner") != provider:
        return False
    if envelope.get("required_capability") != f"runner:{provider}":
        return False
    if not isinstance(envelope.get("objective"), str) or not envelope["objective"].strip():
        return False
    if envelope.get("write_scope") != []:
        return False
    if type(envelope.get("max_attempts")) is not int or envelope.get("max_attempts") != 1:
        return False
    if envelope.get("fallback_allowed") is not False:
        return False
    constraints = envelope.get("constraints")
    if not isinstance(constraints, dict) or set(constraints) != {
        "read_only", "max_wall_seconds", "network",
    }:
        return False
    wall_seconds = constraints.get("max_wall_seconds")
    if not (
        constraints.get("read_only") is True
        and constraints.get("network") == "provider_managed_only"
        and type(wall_seconds) is int
        # A provider response may be a durable background task. The Agent
        # Host still fences it at one day and the gateway cancels stalled
        # attempts by heartbeat; do not impose the old ten-minute user wall.
        and 1 <= wall_seconds <= 86_400
    ):
        return False
    source = envelope.get("source")
    if not isinstance(source, dict) or set(source) != {
        "kind", "control_plane", "response_id", "identity_contract",
    }:
        return False
    return bool(
        source.get("kind") == "kolibri_provider_gateway"
        and source.get("control_plane") == "home"
        and source.get("identity_contract") == "kolibri.public-identity.v1"
        and isinstance(source.get("response_id"), str)
        and source["response_id"].strip()
    )


def compatible(
    task: dict[str, Any],
    node_id: str,
    capabilities: list[str],
    node: dict[str, Any] | None = None,
    lease_context: dict[str, Any] | None = None,
) -> bool:
    if (lease_context or {}).get("lease_scope") == EXTERNAL_PROVIDER_ACTOR_SCOPE:
        provider = str((lease_context or {}).get("provider") or "").strip().lower()
        return bool(provider and external_provider_task_compatible(task, node_id, provider))
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
    if runner:
        if not runner_capability_names(runner).intersection(set(capabilities)):
            return False
        node_state = runner_state(node or {}, runner)
        if node_state in BLOCKED_RUNNER_STATES:
            return False
    return True


def ensure_active_lease_index() -> None:
    """Migrate legacy leased tasks into the bounded active-lease index once."""
    if CANARY_READ_ONLY:
        return
    marker = key("active_lease_index_v1")
    if redis.command("GET", marker):
        return
    task_ids = all_task_ids()
    active_ids: list[str] = []
    for start in range(0, len(task_ids), 500):
        page_ids = task_ids[start:start + 500]
        tasks = get_json_many([task_key(task_id) for task_id in page_ids])
        active_ids.extend(
            task_id
            for task_id, task in zip(page_ids, tasks)
            if task and task.get("state") in {STATE_LEASED, STATE_RUNNING, STATE_REVIEW}
        )
    if active_ids:
        redis.command("SADD", key("active_lease_ids"), *active_ids)
    redis.command("SET", marker, utc_now())


def active_lease_ids() -> list[str]:
    ensure_active_lease_index()
    return sorted(redis.command("SMEMBERS", key("active_lease_ids")) or [])


def _task_heartbeat_age_seconds(task: dict[str, Any], current: datetime | None = None) -> float | None:
    raw = task.get("heartbeat_at")
    if not raw:
        return None
    try:
        value = str(raw).replace("Z", "+00:00")
        observed = datetime.fromisoformat(value)
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        return max(0.0, ((current or datetime.now(timezone.utc)) - observed).total_seconds())
    except (TypeError, ValueError):
        return None


def requeue_expired_leases(limit: int | None = None) -> dict[str, Any]:
    ensure_active_lease_index()
    current = now_ts()
    lease_ids = active_lease_ids()
    bounded_limit = None if limit is None else max(0, int(limit))
    selected_ids = lease_ids if bounded_limit is None else lease_ids[:bounded_limit]
    summary: dict[str, Any] = {
        "task_total": len(all_task_ids()),
        "lease_index_total": len(lease_ids),
        "scan_limit": bounded_limit,
        "scan_truncated": bounded_limit is not None and len(lease_ids) > bounded_limit,
        "checked": 0,
        "expired": 0,
        "requeued": [],
        "dead_lettered": [],
        "skipped": [],
    }
    for task_id in selected_ids:
        task = load_task(task_id)
        if not task or task.get("state") not in {STATE_LEASED, STATE_RUNNING, STATE_REVIEW}:
            redis.command("SREM", key("active_lease_ids"), task_id)
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
        if task_has_attempt_budget(task):
            task["state"] = STATE_RETRY
            task["error_type"] = "lease_expired"
            task["error"] = "lease expired before task completion"
            save_task(task)
            task["state"] = STATE_QUEUED
            save_task(task)
            remove_from_queue(task_id)
            enqueue(task_id)
            summary["requeued"].append(task_id)
        else:
            task["state"] = STATE_DEAD
            task["error_type"] = "lease_expired"
            task["error"] = "lease expired and retry budget exhausted"
            save_task(task)
            redis.command("RPUSH", key("dead_letter"), task_id)
            summary["dead_lettered"].append(task_id)
    summary["requeued_total"] = len(summary["requeued"])
    summary["dead_lettered_total"] = len(summary["dead_lettered"])
    summary["skipped_total"] = len(summary["skipped"])
    return summary


def sweep_stuck_tasks(limit: int | None = None, stale_after: int | None = None) -> dict[str, Any]:
    threshold = max(1, int(stale_after if stale_after is not None else TASK_HEARTBEAT_STALE_AFTER))
    lease_ids = active_lease_ids()
    bounded_limit = None if limit is None else max(0, int(limit))
    selected_ids = lease_ids if bounded_limit is None else lease_ids[:bounded_limit]
    summary: dict[str, Any] = {
        "task_total": len(all_task_ids()),
        "lease_index_total": len(lease_ids),
        "scan_limit": bounded_limit,
        "stale_after_seconds": threshold,
        "scan_truncated": bounded_limit is not None and len(lease_ids) > bounded_limit,
        "checked": 0,
        "stuck": 0,
        "requeued": [],
        "dead_lettered": [],
        "skipped": [],
    }
    current = datetime.now(timezone.utc)
    for task_id in selected_ids:
        task = load_task(task_id)
        if not task or task.get("state") not in {STATE_LEASED, STATE_RUNNING, STATE_REVIEW}:
            redis.command("SREM", key("active_lease_ids"), task_id)
            continue
        summary["checked"] += 1
        age = _task_heartbeat_age_seconds(task, current)
        if age is None:
            summary["skipped"].append({"task_id": task_id, "reason": "missing_or_invalid_heartbeat"})
            continue
        if age <= threshold:
            continue
        summary["stuck"] += 1
        task["lease_owner"] = None
        task["lease_until"] = None
        task["error_type"] = "stuck_no_heartbeat"
        if task_has_attempt_budget(task):
            task["state"] = STATE_RETRY
            task["error"] = f"task heartbeat stale for {int(age)}s"
            save_task(task)
            task["state"] = STATE_QUEUED
            save_task(task)
            remove_from_queue(task_id)
            enqueue(task_id)
            summary["requeued"].append({"task_id": task_id, "heartbeat_age_seconds": int(age)})
        else:
            task["state"] = STATE_DEAD
            task["error"] = f"task heartbeat stale for {int(age)}s and retry budget exhausted"
            save_task(task)
            redis.command("RPUSH", key("dead_letter"), task_id)
            summary["dead_lettered"].append({"task_id": task_id, "heartbeat_age_seconds": int(age)})
    summary["requeued_total"] = len(summary["requeued"])
    summary["dead_lettered_total"] = len(summary["dead_lettered"])
    summary["skipped_total"] = len(summary["skipped"])
    return summary


def queue_maintenance_diagnostics(stale_after: int | None = None) -> dict[str, Any]:
    threshold = max(1, int(stale_after if stale_after is not None else TASK_HEARTBEAT_STALE_AFTER))
    lease_ids = active_lease_ids()
    current_ts = now_ts()
    current_dt = datetime.now(timezone.utc)
    expired = 0
    stuck = 0
    for task_id in lease_ids:
        task = load_task(task_id)
        if not task or task.get("state") not in {STATE_LEASED, STATE_RUNNING, STATE_REVIEW}:
            continue
        try:
            if float(task.get("lease_until") or 0) < current_ts:
                expired += 1
        except (TypeError, ValueError):
            pass
        age = _task_heartbeat_age_seconds(task, current_dt)
        if age is not None and age > threshold:
            stuck += 1
    return {
        "redis": "PONG",
        "task_total": len(all_task_ids()),
        "queue_total": len(queue_ids()),
        "lease_index_total": len(lease_ids),
        "expired_leases": expired,
        "stuck_heartbeat_tasks": stuck,
        "stale_after_seconds": threshold,
    }


def _task_age_seconds(task: dict[str, Any], current: float) -> int | None:
    observed = parse_iso_ts(task.get("updated_at") or task.get("created_at"))
    return None if observed is None else max(0, int(current - observed))


def _queued_task_routability(
    task: dict[str, Any],
    active_by_id: dict[str, dict[str, Any]],
) -> tuple[bool, str]:
    envelope = task.get("envelope") if isinstance(task.get("envelope"), dict) else {}
    target = str(envelope.get("target_node") or envelope.get("required_node") or "")
    if target:
        node = active_by_id.get(target)
        if node is not None:
            if node.get("schedulable") is not True:
                return False, "target_not_schedulable"
            if not compatible(task, target, list(node.get("capabilities") or []), node):
                return False, "target_capability_or_runner_mismatch"
            return True, "exact_canonical_target_ready"
        actor = get_json(node_key(target), {})
        external = external_provider_actor_eligibility(target, actor)
        if external.get("eligible") is True and compatible(
            task,
            target,
            list(external["node"].get("capabilities") or []),
            external["node"],
            external,
        ):
            return True, "authenticated_external_provider_actor_ready"
        return False, "target_not_in_canonical_membership"
    for node_id, node in active_by_id.items():
        if node.get("schedulable") is not True:
            continue
        if compatible(task, node_id, list(node.get("capabilities") or []), node):
            return True, "untargeted_task_has_candidate"
    return False, "no_canonical_node_matches_task"


def fleet_proof_payload(
    *,
    aged_after_seconds: int = DEFAULT_FLEET_PROOF_QUEUE_AGE_SECONDS,
    current: float | None = None,
    fleet_view: dict[str, Any] | None = None,
    tasks: list[dict[str, Any]] | None = None,
    queued_task_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return physical freshness and strict execution proof as separate facts."""

    threshold = min(max(int(aged_after_seconds), 1), 30 * 24 * 60 * 60)
    observed_at = now_ts() if current is None else float(current)
    view = fleet_view or build_canonical_fleet_view(current=observed_at)
    active = list(view.get("active") or [])
    if tasks is None:
        task_ids = all_task_ids()
        loaded = get_json_many([task_key(task_id) for task_id in task_ids])
        tasks = [task for task in loaded if isinstance(task, dict) and task]
    else:
        tasks = [task for task in tasks if isinstance(task, dict) and task]
    if queued_task_ids is None:
        queued_task_ids = queue_ids()
    queued = set(str(task_id) for task_id in queued_task_ids)

    strict_tasks_by_node: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        if not strict_completion_proof(task):
            continue
        verifier = task.get("completion_verifier") or {}
        node_id = str(verifier.get("node_id") or "")
        strict_tasks_by_node.setdefault(node_id, []).append(task)

    matrix: list[dict[str, Any]] = []
    for node in active:
        node_id = str(node.get("node_id") or "")
        matches = strict_tasks_by_node.get(node_id, [])
        matches.sort(
            key=lambda item: parse_iso_ts(item.get("updated_at")) or 0.0,
            reverse=True,
        )
        latest = matches[0] if matches else None
        proof = latest.get("completion_evidence") if latest else {}
        verifier = latest.get("completion_verifier") if latest else {}
        matrix.append({
            "node_id": node_id,
            "freshness": node.get("freshness"),
            "health": node.get("health"),
            "schedulable": node.get("schedulable") is True,
            "runtime_record_present": node.get("runtime_record_present") is True,
            "capabilities": list(node.get("capabilities") or []),
            "strict_verified_completion": {
                "proven": latest is not None,
                "task_id": latest.get("task_id") if latest else None,
                "kind": latest.get("kind") if latest else None,
                "attempt_id": latest.get("attempt_id") if latest else None,
                "completed_at": latest.get("updated_at") if latest else None,
                "result_sha256": proof.get("result_sha256") if latest else None,
                "binding_sha256": proof.get("binding_sha256") if latest else None,
                "verifier": verifier.get("verifier") if latest else None,
                "verifier_schema": verifier.get("schema_version") if latest else None,
            },
        })

    active_by_id = {str(node.get("node_id") or ""): node for node in active}
    queued_issues: list[dict[str, Any]] = []
    for task in tasks:
        task_id = str(task.get("task_id") or "")
        if task_id not in queued or task.get("state") != STATE_QUEUED:
            continue
        envelope = task.get("envelope") if isinstance(task.get("envelope"), dict) else {}
        age = _task_age_seconds(task, observed_at)
        routable, reason = _queued_task_routability(task, active_by_id)
        aged = age is not None and age > threshold
        if aged or not routable:
            queued_issues.append({
                "task_id": task_id,
                "target_node": envelope.get("target_node") or envelope.get("required_node"),
                "required_capability": envelope.get("required_capability"),
                "runner": envelope.get("runner"),
                "age_seconds": age,
                "aged": aged,
                "routable": routable,
                "reason": reason,
            })
    queued_issues.sort(key=lambda item: (-int(item.get("age_seconds") or 0), item["task_id"]))
    verified_total = sum(
        1 for row in matrix if row["strict_verified_completion"]["proven"]
    )
    fresh_total = sum(1 for row in matrix if row.get("freshness") == "fresh")
    missing = [
        row["node_id"]
        for row in matrix
        if not row["strict_verified_completion"]["proven"]
    ]
    return {
        "schema_version": FLEET_PROOF_SCHEMA,
        "status": "complete" if matrix and verified_total == len(matrix) else "incomplete",
        "source": "control-plane/home",
        "observed_at": datetime.fromtimestamp(observed_at, timezone.utc).isoformat(),
        "membership": dict(view.get("membership") or {}),
        "summary": {
            "canonical_total": len(matrix),
            "fresh_total": fresh_total,
            "strict_verified_total": verified_total,
            "missing_strict_verified_total": len(missing),
            "queued_total": len(queued),
            "queued_issue_total": len(queued_issues),
            "aged_after_seconds": threshold,
        },
        "missing_strict_verified_nodes": missing,
        "nodes": matrix,
        "queued_issues": queued_issues,
    }


def failure_task_listing(error_type: str, limit: int) -> dict[str, Any]:
    matched: list[dict[str, Any]] = []
    for task_id in all_task_ids():
        task = load_task(task_id)
        if task and str(task.get("error_type") or "") == error_type:
            matched.append({
                "task_id": task.get("task_id"),
                "state": task.get("state"),
                "error_type": task.get("error_type"),
                "error": task.get("error"),
                "updated_at": task.get("updated_at"),
            })
    matched.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    bounded = max(0, min(int(limit), 250))
    returned = matched[:bounded]
    return {
        "error_type": error_type,
        "total": len(matched),
        "returned": len(returned),
        "truncated": len(matched) > len(returned),
        "tasks": returned,
    }


PROVIDER_HEALTH_OPEN_REASONS = frozenset({
    "lease_expired", "provider_access_denied", "provider_auth_failed",
    "provider_risk_control", "provider_runner_missing", "provider_runner_outdated",
    "provider_timeout", "provider_usage_limit", "rate_limited", "runner_access_denied",
    "runner_auth_blocked", "runner_auth_failed", "runner_policy_blocked",
    "runner_unavailable",
})
PROVIDER_HEALTH_TERMINAL_STATES = frozenset({
    "blocked", "cancelled", "canceled", "completed", "dead", "dead_letter", "failed",
})
PROVIDER_HEALTH_SCAN_LIMIT = 2048
PROVIDER_HEALTH_INDEX_RETAIN = 4096


def provider_health_index_key() -> str:
    return key("runtime:provider_health_task_updates")


def is_provider_gateway_task(task: Any) -> bool:
    if not isinstance(task, dict):
        return False
    envelope = task.get("envelope") if isinstance(task.get("envelope"), dict) else {}
    source = envelope.get("source") if isinstance(envelope.get("source"), dict) else {}
    return bool(
        str(task.get("task_id") or "").startswith("KOL-PROVIDER-")
        or source.get("kind") == "kolibri_provider_gateway"
    )


def index_provider_health_task(task: Any) -> None:
    if not is_provider_gateway_task(task):
        return
    task_id = str(task.get("task_id") or "")
    observed_at = parse_iso_ts(task.get("updated_at") or task.get("created_at")) or now_ts()
    try:
        redis.command("ZADD", provider_health_index_key(), observed_at, task_id)
        # Auxiliary routing health must remain bounded and must never turn a
        # successfully persisted task transition into a false API failure.
        redis.command(
            "ZREMRANGEBYRANK", provider_health_index_key(), 0,
            -(PROVIDER_HEALTH_INDEX_RETAIN + 1),
        )
    except (RedisError, OSError, ValueError):
        return


def provider_health_projection(
    tasks: list[Any],
    runner: str,
    *,
    limit: int = 64,
) -> list[dict[str, Any]]:
    """Reduce provider task history to a prompt-free latest node outcome."""

    normalized_runner = str(runner or "").strip().lower()
    if normalized_runner not in {"mimo", "codex"}:
        raise ValueError("provider_health_runner_invalid")
    bounded_limit = min(max(int(limit), 1), 128)
    latest: dict[str, tuple[float, str, dict[str, Any]]] = {}
    for task in tasks:
        if not is_provider_gateway_task(task):
            continue
        envelope = task.get("envelope") if isinstance(task.get("envelope"), dict) else {}
        task_runner = str(task.get("runner") or envelope.get("runner") or "").strip().lower()
        if task_runner != normalized_runner:
            continue
        state = str(task.get("state") or "").strip().lower()
        if state not in PROVIDER_HEALTH_TERMINAL_STATES:
            continue
        observed_ts = parse_iso_ts(
            task.get("updated_at") or task.get("heartbeat_at") or task.get("created_at")
        )
        if observed_ts is None:
            continue
        node_id = str(envelope.get("target_node") or "").strip()
        if not node_id:
            node_id = str(task.get("lease_owner") or "").partition(":")[0].strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", node_id):
            continue
        result = task.get("result") if isinstance(task.get("result"), dict) else {}
        result_status = str(result.get("status") or "").strip().lower()
        raw_error = str(task.get("error_type") or result.get("error_type") or "").strip().lower()
        cancel_reason = str(task.get("cancel_reason") or "").strip().lower()
        status = ""
        reason = ""
        if state == "completed" and result_status == "completed" and not raw_error:
            status, reason = "healthy", "verified_completion"
        elif cancel_reason == "factory_provider_poll_timeout":
            status, reason = "open", "provider_timeout"
        elif raw_error in PROVIDER_HEALTH_OPEN_REASONS:
            status, reason = "open", raw_error
        elif state in {"blocked", "dead", "dead_letter", "failed"}:
            status, reason = "open", "provider_runtime_failed"
        if not status:
            # In particular, an ordinary owner cancellation is not evidence
            # that the provider route is unhealthy.
            continue
        created_ts = parse_iso_ts(task.get("created_at"))
        latency = (
            round(max(0.0, observed_ts - created_ts), 3)
            if created_ts is not None and observed_ts >= created_ts
            else None
        )
        record = {
            "node_id": node_id,
            "status": status,
            "reason": reason,
            "observed_at": datetime.fromtimestamp(observed_ts, timezone.utc).isoformat(),
            "latency_seconds": latency,
        }
        task_id = str(task.get("task_id") or "")
        previous = latest.get(node_id)
        if previous is None or (observed_ts, task_id) > (previous[0], previous[1]):
            latest[node_id] = (observed_ts, task_id, record)
    ordered = sorted(latest.values(), key=lambda item: (-item[0], item[2]["node_id"]))
    return [record for _timestamp, _task_id, record in ordered[:bounded_limit]]


def provider_health_records(runner: str, limit: int = 64) -> dict[str, Any]:
    normalized_runner = str(runner or "").strip().lower()
    if normalized_runner not in {"mimo", "codex"}:
        raise ValueError("provider_health_runner_invalid")
    bounded_limit = min(max(int(limit), 1), 128)
    indexed_ids = redis.command(
        "ZREVRANGE", provider_health_index_key(), 0, PROVIDER_HEALTH_SCAN_LIMIT - 1,
    ) or []
    if indexed_ids:
        task_ids = list(dict.fromkeys(str(item) for item in indexed_ids))
    else:
        # Compatibility migration for pre-index tasks is permitted only when
        # the whole set fits the hard scan bound; arbitrary SMEMBERS order is
        # never treated as chronological recency.
        legacy_ids = redis.command("SMEMBERS", key("task_ids")) or []
        task_ids = list(dict.fromkeys(str(item) for item in legacy_ids))
        if len(task_ids) > PROVIDER_HEALTH_SCAN_LIMIT:
            task_ids = []
    tasks = get_json_many([task_key(task_id) for task_id in task_ids])
    return {
        "runner": normalized_runner,
        "records": provider_health_projection(tasks, normalized_runner, limit=bounded_limit),
    }


def validate_task_target(envelope: dict[str, Any]) -> str | None:
    """Accept only an exact current mesh ID or an authenticated provider actor."""

    field_name = "target_node" if "target_node" in envelope else "required_node"
    raw_target = envelope.get(field_name)
    if raw_target is None:
        return None
    if not isinstance(raw_target, str) or not raw_target or raw_target != raw_target.strip():
        raise TaskTargetValidationError(str(raw_target or ""), "target_node_format_invalid")
    target_node = raw_target
    snapshot = mesh_membership.load()
    if target_node in snapshot.by_id:
        return target_node
    actor = get_json(node_key(target_node), {})
    external = external_provider_actor_eligibility(target_node, actor)
    if external.get("eligible") is True:
        return target_node
    raise TaskTargetValidationError(
        target_node,
        str(external.get("reason") or "target_not_in_canonical_mesh_membership"),
    )


def create_task(envelope: dict[str, Any]) -> dict[str, Any]:
    if envelope.get("kind") in RELEASE_TASK_KINDS:
        envelope = authorize_release_task(envelope)
    validate_task_target(envelope)
    task = normalize_task(envelope)
    idem_key = key(f"idempotency:{task['idempotency_key']}")
    request_hash = hashlib.sha256(
        json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    claim = json.dumps(
        {"request_hash": request_hash, "task_id": task["task_id"]},
        sort_keys=True,
        separators=(",", ":"),
    )
    release_id = ""
    if task.get("kind") in RELEASE_TASK_KINDS:
        release_id = str(
            envelope.get("release_id")
            or envelope.get("rollback_to_release_id")
            or ""
        ).strip()
    task_json = json.dumps(task, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    release_index_key = release_task_ids_key(release_id) if release_id else key("release:no_index")
    script = (
        "local existing=redis.call('GET',KEYS[1]);"
        "if existing then return {0,existing}; end;"
        "redis.call('SET',KEYS[1],ARGV[1]);"
        "redis.call('SET',KEYS[2],ARGV[2]);"
        "redis.call('SADD',KEYS[3],ARGV[3]);"
        "redis.call('RPUSH',KEYS[4],ARGV[3]);"
        "if ARGV[4]=='1' then redis.call('SADD',KEYS[5],ARGV[3]); end;"
        "return {1,ARGV[2]};"
    )
    result = redis.command(
        "EVAL",
        script,
        5,
        idem_key,
        task_key(task["task_id"]),
        key("task_ids"),
        key("queue"),
        release_index_key,
        claim,
        task_json,
        task["task_id"],
        "1" if release_id else "0",
    )
    if not isinstance(result, list) or len(result) != 2:
        raise RuntimeError("idempotency_claim_failed")
    if int(result[0]) == 1:
        created_task = json.loads(result[1])
        index_provider_health_task(created_task)
        return created_task

    existing_raw = str(result[1])
    try:
        existing_claim = json.loads(existing_raw)
    except json.JSONDecodeError:
        existing_claim = {"task_id": existing_raw, "request_hash": None}
    existing_task_id = str(existing_claim.get("task_id") or "")
    existing_task = load_task(existing_task_id) if existing_task_id else None
    existing_hash = existing_claim.get("request_hash")
    if existing_hash is None and existing_task:
        existing_hash = hashlib.sha256(
            json.dumps(
                existing_task.get("envelope") or {},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    if existing_hash != request_hash or not existing_task:
        raise IdempotencyConflict(str(task["idempotency_key"]), existing_task_id)
    return existing_task


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
        "required_capability": "review",
        "source_task_id": source_task["task_id"],
        "pull_request_url": pr_url,
        "branch": result.get("branch"),
        "base_ref": envelope.get("base_ref", "origin/main"),
        "max_attempts": int(envelope.get("review_max_attempts", DEFAULT_MAX_ATTEMPTS)),
    }
    review_node = envelope.get("review_node")
    if review_node:
        review_envelope["target_node"] = review_node
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
        handler._kolibri_wire_body_sha256 = hashlib.sha256(b"").hexdigest()
        return {}
    payload = handler.rfile.read(length)
    handler._kolibri_wire_body_sha256 = hashlib.sha256(payload).hexdigest()
    return json.loads(payload.decode("utf-8"))


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
    fleet = build_canonical_fleet_view()
    nodes = fleet["active"]
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
        "membership": fleet["membership"],
        "historical_nodes": len(fleet["historical"]),
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
        "max_attempts": int(body.get("max_attempts", 2)),
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
                    data={
                        "redis": pong,
                        "queue_backend": "redis",
                        "time": utc_now(),
                        "fabric_api_version": FABRIC_API_VERSION,
                        "truth_factory": "enabled",
                        "state_namespace": NAMESPACE,
                        "active_release_id": ACTIVE_RELEASE_ID or None,
                        "canary_read_only": CANARY_READ_ONLY,
                    },
                    next_action="use /v1/fleet/route before dispatching work to a node",
                ))
                return
            if path == "/v1/approvals":
                approvals = list_owner_approvals()
                response(self, 200, {"approvals": approvals, "count": len(approvals)})
                return
            if path.startswith("/v1/approvals/"):
                approval_id = _safe_record_id(unquote(path.split("/", 3)[3]), "approval_id")
                approval = get_json(owner_approval_key(approval_id), {})
                if not approval:
                    response(self, 404, {"error": "approval_not_found", "approval_id": approval_id})
                    return
                response(self, 200, approval)
                return
            if path.startswith("/v1/releases/") and path.endswith("/health"):
                parts = path.split("/")
                if len(parts) != 7 or parts[4] != "nodes":
                    response(self, 404, {"error": "invalid_release_health_path"})
                    return
                health = release_health(unquote(parts[3]), unquote(parts[5]))
                status_code = 404 if health["status"] == "unknown" else 200
                response(self, status_code, health)
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
                scope = str(query.get("scope", ["active"])[0]).strip().lower()
                try:
                    payload = canonical_nodes_payload(
                        scope,
                        limit=int(query.get("limit", ["50"])[0]),
                        offset=int(query.get("offset", ["0"])[0]),
                    )
                except ValueError as exc:
                    response(self, 400, {"error": str(exc)})
                    return
                response(self, 200, payload)
                return
            if path.startswith("/v1/nodes/"):
                query = parse_qs(parsed.query)
                scope = str(query.get("scope", ["active"])[0]).strip().lower()
                if scope not in {"active", "audit", "all"}:
                    response(self, 400, {"error": "node_membership_scope_invalid"})
                    return
                node_id = unquote(path.split("/", 3)[3])
                view = build_canonical_fleet_view()
                candidates = (
                    view["active"]
                    if scope == "active"
                    else view["historical"]
                    if scope == "audit"
                    else view["active"] + view["historical"]
                )
                node = next((item for item in candidates if item.get("node_id") == node_id), None)
                if node is None:
                    response(self, 404, {"error": "node_not_found", "node_id": node_id})
                    return
                response(self, 200, node)
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
            if path == "/v1/runtime/provider-health":
                query = parse_qs(parsed.query)
                runner = str(query.get("runner", [""])[0] or "").strip().lower()
                try:
                    payload = provider_health_records(
                        runner,
                        int(query.get("limit", ["64"])[0]),
                    )
                except (TypeError, ValueError) as exc:
                    response(self, 400, {"error": str(exc)})
                    return
                response(self, 200, payload)
                return
            if path == "/v1/runtime/provider-actors":
                query = parse_qs(parsed.query)
                runner = str(query.get("runner", [""])[0] or "").strip().lower()
                try:
                    payload = external_provider_actor_records(
                        runner,
                        int(query.get("limit", ["64"])[0]),
                    )
                except (TypeError, ValueError) as exc:
                    response(self, 400, {"error": str(exc)})
                    return
                response(self, 200, payload)
                return
            if path == "/v1/runtime/fleet-proof":
                query = parse_qs(parsed.query)
                try:
                    aged_after = int(query.get(
                        "aged_after_seconds",
                        [str(DEFAULT_FLEET_PROOF_QUEUE_AGE_SECONDS)],
                    )[0])
                    payload = fleet_proof_payload(aged_after_seconds=aged_after)
                except (TypeError, ValueError) as exc:
                    response(self, 400, {"error": str(exc)})
                    return
                response(self, 200, payload)
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
                    "pagination": {
                        "limit": limit,
                        "offset": offset,
                        "returned": len(tasks),
                        "total_indexed": total_indexed,
                    },
                    "queue_total": len(queue),
                })
                return
            if path == "/v1/tasks/queue/diagnostics":
                query = parse_qs(parsed.query)
                stale_after_raw = query.get("stale_after_seconds", [None])[0]
                stale_after = int(stale_after_raw) if stale_after_raw is not None else None
                response(self, 200, queue_maintenance_diagnostics(stale_after))
                return
            if path == "/v1/tasks/failures":
                query = parse_qs(parsed.query)
                error_type = str(query.get("error_type", ["deliverable_gate_failed"])[0] or "deliverable_gate_failed")
                limit = min(max(int(query.get("limit", ["50"])[0]), 0), 250)
                response(self, 200, failure_task_listing(error_type, limit))
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
        except MembershipError as exc:
            response(self, 503, {
                "error": "canonical_mesh_membership_unavailable",
                "detail": str(exc),
                "scheduler": "fail_closed",
            })
        except Exception as exc:  # pragma: no cover - surfaced in runtime logs
            response(self, 500, {"error": "control_plane_error", "detail": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if CANARY_READ_ONLY:
            response(self, 405, {
                "error": "factory_canary_read_only",
                "path": path,
            })
            return
        try:
            body = read_body(self)
            if path == "/v1/approvals":
                try:
                    approval = verify_owner_approval(body)
                    save_owner_approval(approval)
                except ValueError as exc:
                    response(self, 422, {"error": str(exc)})
                    return
                response(self, 201, approval)
                return
            if path == "/v1/nodes/register":
                node_id = body["node_id"]
                if body.get("external_provider_auth") is not None:
                    response(self, 400, {"error": "external_provider_actor_server_marker_forbidden"})
                    return
                existing_node = get_json(node_key(node_id), {})
                existing_external = external_provider_actor_identity(node_id, existing_node) is not None
                existing_marked = has_external_provider_actor_marker(node_id, existing_node)
                auth_node = existing_node if (existing_external or existing_marked) else body
                if existing_marked:
                    auth_node = {**auth_node, "external_provider_auth": existing_node["external_provider_auth"]}
                if existing_external or existing_marked:
                    if external_provider_actor_identity(node_id, body) is None:
                        response(self, 409, {"error": "external_provider_actor_identity_immutable"})
                        return
                if not require_external_provider_actor_auth(
                    self, node_id, auth_node, body, allow_marker_upgrade=True,
                ):
                    return
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
                    "labels": body.get("labels") if isinstance(body.get("labels"), dict) else {},
                    "runner_readiness": (
                        body.get("runner_readiness")
                        if isinstance(body.get("runner_readiness"), dict)
                        else {}
                    ),
                }
                marker = external_provider_actor_auth_marker(node_id)
                if external_provider_actor_identity(node_id, node) is not None:
                    if not re.fullmatch(
                        r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}",
                        str(node.get("agent_id") or ""),
                    ):
                        response(self, 400, {"error": "external_provider_actor_agent_id_invalid"})
                        return
                    if marker is None:
                        response(self, 403, {"error": "external_provider_actor_node_binding_invalid"})
                        return
                    node["external_provider_auth"] = marker
                set_json(node_key(node_id), node)
                redis.command("SADD", key("node_ids"), node_id)
                annotation = node_membership_annotation(node_id)
                response(self, 200, {**node, **annotation})
                return
            if path.startswith("/v1/nodes/") and path.endswith("/heartbeat"):
                node_id = path.split("/")[3]
                if body.get("node_id") not in {None, node_id} or body.get("external_provider_auth") is not None:
                    response(self, 400, {"error": "external_provider_actor_identity_payload_invalid"})
                    return
                node = get_json(node_key(node_id), {"node_id": node_id})
                existing_external = external_provider_actor_identity(node_id, node) is not None
                existing_marked = has_external_provider_actor_marker(node_id, node)
                if existing_external or existing_marked:
                    allowed_heartbeat_fields = {
                        "node_id", "hostname", "agent_id", "pid", "capabilities", "runners",
                        "runner_readiness", "release_installer", "labels", "active_task",
                        "cpu", "ram", "disk",
                    }
                    if set(body) - allowed_heartbeat_fields:
                        response(self, 400, {"error": "external_provider_actor_heartbeat_field_forbidden"})
                        return
                    if body.get("agent_id") != node.get("agent_id"):
                        response(self, 409, {"error": "external_provider_actor_agent_id_immutable"})
                        return
                if (existing_external or existing_marked) and external_provider_actor_identity(node_id, body) is None:
                    response(self, 409, {"error": "external_provider_actor_identity_immutable"})
                    return
                auth_node = node if (existing_external or existing_marked) else {**node, **body}
                if existing_marked:
                    auth_node["external_provider_auth"] = node["external_provider_auth"]
                if not require_external_provider_actor_auth(self, node_id, auth_node, body):
                    return
                node.update(body)
                if has_external_provider_actor_marker(node_id, auth_node):
                    node["external_provider_auth"] = auth_node["external_provider_auth"]
                elif existing_external:
                    marker = external_provider_actor_auth_marker(node_id)
                    if marker is None:
                        response(self, 403, {"error": "external_provider_actor_node_binding_invalid"})
                        return
                    node["external_provider_auth"] = marker
                node["health"] = "online"
                node["heartbeat_at"] = utc_now()
                set_json(node_key(node_id), node)
                redis.command("SADD", key("node_ids"), node_id)
                annotation = node_membership_annotation(node_id)
                response(self, 200, {**node, **annotation})
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
                try:
                    task = create_task(body)
                except IdempotencyConflict as exc:
                    response(self, 409, {
                        "error": str(exc),
                        "idempotency_key": exc.idempotency_key,
                        "existing_task_id": exc.existing_task_id,
                    })
                    return
                except TaskTargetValidationError as exc:
                    response(self, 422, exc.as_dict())
                    return
                except ValueError as exc:
                    response(self, 422, {"error": str(exc)})
                    return
                response(self, 201, task)
                return
            if path == "/v1/tasks/reap-expired":
                limit = body.get("limit")
                response(self, 200, requeue_expired_leases(int(limit) if limit is not None else None))
                return
            if path == "/v1/tasks/sweep-stuck":
                limit = body.get("limit")
                stale_after = body.get("stale_after_seconds")
                response(
                    self,
                    200,
                    sweep_stuck_tasks(
                        int(limit) if limit is not None else None,
                        int(stale_after) if stale_after is not None else None,
                    ),
                )
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
                node_id = body["node_id"]
                lease_node = get_json(node_key(node_id), {})
                if not require_external_provider_actor_auth(self, node_id, lease_node, body):
                    return
                requeue_expired_leases()
                eligibility = lease_node_eligibility(node_id)
                if eligibility.get("eligible") is not True:
                    # Preserve the Redis audit card, but a legacy/duplicate,
                    # missing, drained, or stale identity receives no work.
                    response(self, 204, {})
                    return
                capabilities = body.get("capabilities", [])
                agent_id = body.get("agent_id", node_id)
                node = eligibility["node"]
                if eligibility.get("lease_scope") == EXTERNAL_PROVIDER_ACTOR_SCOPE:
                    # Registration/heartbeat is the external actor's audited
                    # readiness authority. A lease request cannot self-upgrade
                    # capabilities or runner state just before scheduling.
                    registered_capabilities = [
                        str(item)
                        for item in node.get("capabilities") or []
                        if isinstance(item, str)
                    ]
                    if {
                        str(item).strip().lower()
                        for item in capabilities
                        if isinstance(item, str)
                    } != {
                        item.strip().lower() for item in registered_capabilities
                    }:
                        response(self, 204, {})
                        return
                    if agent_id != node.get("agent_id"):
                        response(self, 401, {"error": "external_provider_actor_agent_id_invalid"})
                        return
                    capabilities = registered_capabilities
                elif isinstance(body.get("runners"), dict):
                    node["runners"] = body["runners"]
                    set_json(node_key(node_id), node)
                for task_id in queue_ids():
                    claim_id = f"{node_id}:{agent_id}:{uuid.uuid4().hex}"
                    if not acquire_lease_claim(task_id, claim_id):
                        continue
                    try:
                        # Reload only after acquiring the per-task claim. This
                        # fences concurrent workers that read the same queue
                        # snapshot without requiring a global scheduler lock.
                        task = load_task(task_id)
                        if not task or task.get("state") not in {STATE_QUEUED, STATE_REVIEW}:
                            remove_from_queue(task_id)
                            continue
                        if not compatible(task, node_id, capabilities, node, eligibility):
                            continue
                        task["state"] = STATE_LEASED
                        task["attempt"] = int(task.get("attempt", 0)) + 1
                        task["attempt_id"] = f"{task_id}-attempt-{task['attempt']}"
                        try:
                            allocate_next_fencing_token(task)
                        except (TypeError, ValueError) as exc:
                            task["state"] = STATE_DEAD
                            task["error_type"] = "lease_fencing_contract_invalid"
                            task["error"] = str(exc)
                            save_task(task)
                            remove_from_queue(task_id)
                            redis.command("RPUSH", key("dead_letter"), task_id)
                            continue
                        task["lease_owner"] = f"{node_id}:{agent_id}"
                        task["lease_actor_scope"] = eligibility.get("lease_scope") or "canonical_mesh"
                        if eligibility.get("lease_scope") == EXTERNAL_PROVIDER_ACTOR_SCOPE:
                            task["lease_external_auth"] = dict(node.get("external_provider_auth") or {})
                        task["lease_until"] = now_ts() + LEASE_DURATION
                        task["heartbeat_at"] = utc_now()
                        save_task(task)
                        remove_from_queue(task_id)
                        response(self, 200, task)
                        return
                    finally:
                        release_lease_claim(task_id, claim_id)
                response(self, 204, {})
                return
            if path.startswith("/v1/tasks/") and path.endswith("/heartbeat"):
                task_id = path.split("/")[3]
                task = load_task(task_id)
                if not task:
                    response(self, 404, {"error": "task_not_found", "task_id": task_id})
                    return
                lease_node_id = str(task.get("lease_owner") or "").partition(":")[0]
                lease_node = get_json(node_key(lease_node_id), {})
                if task.get("lease_actor_scope") == EXTERNAL_PROVIDER_ACTOR_SCOPE:
                    lease_node = {
                        **lease_node,
                        "external_provider_auth": dict(task.get("lease_external_auth") or {}),
                    }
                if not require_external_provider_actor_auth(
                    self, lease_node_id, lease_node, body,
                ):
                    return
                if reject_invalid_lease_fence(self, task, body):
                    return
                if task.get("state") not in TERMINAL_STATES:
                    progress = body.get("progress")
                    if progress is not None:
                        if not (
                            isinstance(progress, dict)
                            and set(progress) == {
                                "schema_version", "type", "sequence", "delta",
                            }
                            and progress.get("schema_version") == "kolibri.public-progress.v1"
                            and progress.get("type") == "reasoning_summary_delta"
                            and type(progress.get("sequence")) is int
                            and 1 <= progress["sequence"] <= 1_000_000
                            and isinstance(progress.get("delta"), str)
                            and 0 < len(progress["delta"].encode("utf-8")) <= 16_384
                        ):
                            response(self, 400, {"error": "task_progress_contract_invalid"})
                            return
                        previous_progress = task.get("progress")
                        previous_sequence = (
                            previous_progress.get("sequence", 0)
                            if isinstance(previous_progress, dict)
                            else 0
                        )
                        if progress["sequence"] > previous_sequence:
                            task["progress"] = progress
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
                lease_node_id = str(task.get("lease_owner") or "").partition(":")[0]
                lease_node = get_json(node_key(lease_node_id), {})
                if task.get("lease_actor_scope") == EXTERNAL_PROVIDER_ACTOR_SCOPE:
                    lease_node = {
                        **lease_node,
                        "external_provider_auth": dict(task.get("lease_external_auth") or {}),
                    }
                if not require_external_provider_actor_auth(
                    self, lease_node_id, lease_node, body,
                ):
                    return
                if reject_invalid_lease_fence(self, task, body):
                    return
                binding_error = runner_result_binding_error(task, body)
                if binding_error:
                    response(self, 409, binding_error)
                    return
                if task.get("state") in TERMINAL_STATES:
                    task = acknowledge_cancelled_task(task)
                    response(self, 200, {"task": task, "review_task": None})
                    return
                result = body.get("result", body)
                result_reference = body.get("result_reference") or (
                    result.get("result_path") if isinstance(result, dict) else None
                )
                evidence, verifier = verify_task_completion(
                    task,
                    result,
                    body,
                    result_reference,
                )
                task["completion_evidence"] = evidence
                task["completion_verifier"] = verifier
                if verifier["verdict"] != "passed":
                    task["error_type"] = "completion_verification_failed"
                    task["error"] = ",".join(verifier["failed_checks"])
                    save_task(task)
                    response(self, 409, {
                        "error": "completion_verification_failed",
                        "task_id": task_id,
                        "state": task.get("state"),
                        "verifier": verifier,
                    })
                    return
                needs_review = task.get("envelope", {}).get("create_review_on_complete")
                has_pr = bool(result.get("pull_request_url") or result.get("pr_url"))
                desired_state = STATE_COMPLETED if (not needs_review or has_pr) else STATE_WAITING_REVIEW
                task["result"] = result
                task["result_reference"] = str(result_reference)
                task["heartbeat_at"] = utc_now()
                task["lease_until"] = None
                task["error_type"] = None
                task["error"] = None
                task = truth_gate_on_complete(task, result)
                task = enforce_completion_truth_state(task, desired_state)
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
                if task.get("lease_actor_scope") == EXTERNAL_PROVIDER_ACTOR_SCOPE:
                    response(self, 403, {"error": "external_provider_actor_annotate_forbidden"})
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
                lease_node_id = str(task.get("lease_owner") or "").partition(":")[0]
                lease_node = get_json(node_key(lease_node_id), {})
                if task.get("lease_actor_scope") == EXTERNAL_PROVIDER_ACTOR_SCOPE:
                    lease_node = {
                        **lease_node,
                        "external_provider_auth": dict(task.get("lease_external_auth") or {}),
                    }
                if not require_external_provider_actor_auth(
                    self, lease_node_id, lease_node, body,
                ):
                    return
                if reject_invalid_lease_fence(self, task, body):
                    return
                binding_error = runner_result_binding_error(task, body)
                if binding_error:
                    response(self, 409, binding_error)
                    return
                if task.get("state") in TERMINAL_STATES:
                    task = acknowledge_cancelled_task(task)
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
                if task_has_attempt_budget(task) and body.get("retry", True):
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
                task = cancel_task_record(task, body)
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
                task = cancel_task_record(task, body)
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
        except TaskTargetValidationError as exc:
            response(self, 422, exc.as_dict())
        except MembershipError as exc:
            response(self, 503, {
                "error": "canonical_mesh_membership_unavailable",
                "detail": str(exc),
                "scheduler": "fail_closed",
            })
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
