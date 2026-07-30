"""Generic, assignment-bound Provider Execution Authority.

This module is deliberately provider-neutral.  Logical Home chooses a real
AgentCard and freezes the runtime profile, model configuration, access policy,
assignment, A2A request and lease fence.  This service validates that complete
projection, executes the exact registered profile once, and durably journals
the external effect before returning a normalized result.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import hmac
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import threading
import time
from types import ModuleType
from typing import Any, Callable, Mapping
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .agent_runtime import (
    AgentAccessPolicy,
    AgentExecutionConfiguration,
    AgentModelSelection,
    AgentRuntimeError,
    AgentRuntimeMessage,
    AgentRuntimeRegistry,
    AgentRuntimeRequest,
    AgentRuntimeResult,
    AgentWorkspace,
)
from .config import Settings
from .database import connect_database, transaction


PROVIDER_EXECUTION_PATH = "/v1/runtime/provider-executions"
PROVIDER_EXECUTION_REQUEST_SCHEMA_ID = (
    "kolibri.provider_execution.request"
)
PROVIDER_EXECUTION_RESULT_SCHEMA_ID = "kolibri.provider_execution.result"
PROVIDER_EXECUTION_CATALOG_SCHEMA_ID = (
    "kolibri.provider_execution.catalog"
)
PROVIDER_EXECUTION_SCHEMA_VERSION = "1.0"
_MAX_REQUEST_BYTES = 512 * 1024
_MAX_ACTIVITY_EVENTS = 128
_MAX_ACTIVITY_BYTES = 256 * 1024
_MAX_ACTIVITY_STRING = 4_000
_MAX_RESPONSE_BYTES = 512 * 1024
_EXECUTION_HEARTBEAT_SECONDS = 5.0
_EXECUTION_STALE_SECONDS = 30.0
_AUTH_WINDOW_SECONDS = 60
_TOKEN_FILE_ENV = "KOLIBRI_V3_PROVIDER_EXECUTION_TOKEN_FILE"
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._~+/=-]{32,512}$")
_IDENTITY_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$"
)
_NONCE_PATTERN = re.compile(r"^[A-Za-z0-9._~-]{16,160}$")
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_PUBLIC_ERROR_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{2,95}$")
_RUNTIME_PROFILE_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9._-]{1,95}$"
)
_EFFECT_KEY_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:~-]{15,199}$"
)
_EFFECT_ID_PATTERN = re.compile(r"^effect_[0-9a-f]{40}$")
_SOURCE_COMMAND_REF_PATTERN = re.compile(r"^sourcecmd_[0-9a-f]{40}$")
_SECRET_KEY_PATTERN = re.compile(
    r"(authorization|bearer|cookie|credential|password|secret|token|api[_-]?key)",
    re.IGNORECASE,
)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
    re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{8,}", re.IGNORECASE),
)
_SOURCE_SIDECAR_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "source_command_ref",
        "canonical_request_hash",
        "source_command_hash",
        "tenant_id",
        "task_id",
        "task_version",
        "attempt_id",
        "assignment_id",
        "effect_id",
        "lease_id",
        "fencing_token",
        "runtime_profile",
        "access_policy",
        "source_command",
    }
)
_TRUSTED_AGENT_BINDING_FIELDS = frozenset(
    {
        "trusted_agent_profile_id",
        "trusted_agent_profile_epoch",
        "trusted_agent_workspace_binding_id",
        "trusted_agent_workspace_binding_epoch",
    }
)
_REQUEST_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "effect_key",
        "task",
        "agent_assignment",
        "requester_assignment",
        "a2a_request",
        "source_command_sidecar",
    }
)
_ACCESS_POLICIES: dict[
    tuple[str, str, str, str | None],
    dict[str, Any],
] = {
    ("auto", "workspace-write", "on-request", "auto_review"): {
        "policy_id": "developer.workspace_guarded",
        "tool_ids": [
            "tool.repository.read",
            "tool.repository.write",
            "tool.shell.workspace",
        ],
        "compute_units_limit": 100_000,
        "tool_calls_limit": 2_000,
    },
    ("full", "danger-full-access", "never", None): {
        "policy_id": "developer.full_owner_approved",
        "tool_ids": [
            "tool.filesystem.full",
            "tool.network.full",
            "tool.shell.full",
        ],
        "compute_units_limit": 1_000_000,
        "tool_calls_limit": 20_000,
    },
}
_DEVELOPER_INSTRUCTIONS = (
    "Execute the exact owner-approved developer request inside the assigned "
    "repository. Obey the frozen access policy and tool limits. Return a "
    "concise user-facing result with verification evidence. Never reveal "
    "credentials, secret material, or private reasoning."
)


class ProviderExecutionError(RuntimeError):
    """Public-safe provider execution failure."""

    def __init__(
        self,
        code: str,
        *,
        status_code: int = 422,
        message: str = "Provider execution request was rejected.",
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True, slots=True)
class ValidatedProviderExecution:
    effect_key: str
    request_hash: str
    effect_hash: str
    tenant_id: str
    task_id: str
    attempt_id: str
    assignment_id: str
    lease_id: str
    fencing_token: int
    slot_id: str
    runtime_profile: str
    execution_deadline_at: datetime
    runtime_request: AgentRuntimeRequest


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProviderExecutionError(
            "provider_execution_json_invalid"
        ) from exc


def _sha256_json(value: Any) -> str:
    return (
        "sha256:"
        + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    )


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def developer_runtime_capability(runtime_profile: str) -> str:
    digest = hashlib.sha256(runtime_profile.encode("utf-8")).hexdigest()
    return f"developer.runtime.execute.{digest[:32]}"


def _stable_digest(*values: Any) -> str:
    return hashlib.sha256(
        "\0".join(str(value) for value in values).encode("utf-8")
    ).hexdigest()


def _claim_constraint(kind: str, value: str) -> str:
    return (
        f"claim.{kind}_sha256:"
        f"{hashlib.sha256(value.encode('utf-8')).hexdigest()}"
    )


def _canonical_product_request_hash(command: Mapping[str, Any]) -> str:
    identity = command["identity"]
    idempotency = command["idempotency"]
    effect = {
        "schema_id": command["schema_id"],
        "schema_version": command["schema_version"],
        "command_name": command["command_name"],
        "payload_schema_id": command["payload_schema_id"],
        "payload_schema_version": command["payload_schema_version"],
        "target_owner": command["target_owner"],
        "tenant_id": identity["tenant_id"],
        "user_id": identity["user_id"],
        "actor": identity["actor"],
        "subject_refs": identity["subject_refs"],
        "idempotency_scope": idempotency["scope"],
        "idempotency_scope_id": idempotency["scope_id"],
        "payload": command["payload"],
    }
    return _sha256_json(effect)


def _a2a_content_hash(message: Mapping[str, Any]) -> str:
    canonical = {
        "tenant_id": message["tenant_id"],
        "goal_id": message["goal_id"],
        "case_id": message["case_id"],
        "task_id": message["task_id"],
        "task_version": message["task_version"],
        "channel_id": message["channel_id"],
        "sequence": message["sequence"],
        "previous_message_id": message["previous_message_id"],
        "sender_actor_id": message["sender_actor_id"],
        "sender_assignment_id": message["sender_assignment_id"],
        "recipient_assignment_ids": message["recipient_assignment_ids"],
        "recipient_capability": message["recipient_capability"],
        "message_type": message["message_type"],
        "purpose": message["purpose"],
        "response_to_message_id": message["response_to_message_id"],
        "content": message["content"],
    }
    return _sha256_json(canonical)


@lru_cache(maxsize=1)
def _generated_contracts() -> ModuleType:
    """Load the canonical generated validator from this immutable release."""

    generated_path = (
        Path(__file__).resolve().parents[2]
        / "server"
        / "contracts_runtime.py"
    )
    if not generated_path.is_file():
        raise ProviderExecutionError(
            "provider_execution_contract_runtime_missing",
            status_code=503,
        )
    spec = importlib.util.spec_from_file_location(
        "_kolibri_v3_provider_contracts_v1",
        generated_path,
    )
    if spec is None or spec.loader is None:
        raise ProviderExecutionError(
            "provider_execution_contract_runtime_missing",
            status_code=503,
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _contract(value: Any, schema_id: str) -> dict[str, Any]:
    client = _generated_contracts().ContractBoundaryClient(
        "provider_execution_authority"
    )
    result = client.validate_inbound(value, schema_id)
    if not result.ok:
        raise ProviderExecutionError(
            "provider_execution_contract_invalid"
        )
    return client.prepare_outbound(value, schema_id)


def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise ProviderExecutionError("provider_execution_time_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProviderExecutionError(
            "provider_execution_time_invalid"
        ) from exc
    if parsed.tzinfo is None:
        raise ProviderExecutionError("provider_execution_time_invalid")
    return parsed


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _strict_mapping(
    value: Any,
    fields: frozenset[str],
    *,
    code: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or frozenset(value) != fields:
        raise ProviderExecutionError(code)
    return value


def _bounded_identifier(value: Any, *, code: str) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 512
        or "\x00" in value
    ):
        raise ProviderExecutionError(code)
    return value


def _is_loopback(value: str) -> bool:
    normalized = value.lower().rstrip(".")
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _load_secret_file() -> bytes:
    file_name = os.getenv(_TOKEN_FILE_ENV, "").strip()
    if not file_name or not os.path.isabs(file_name):
        raise ProviderExecutionError(
            "provider_execution_token_file_invalid",
            status_code=503,
        )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(file_name, flags)
    except OSError:
        raise ProviderExecutionError(
            "provider_execution_token_file_invalid",
            status_code=503,
        ) from None
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid not in {0, os.geteuid()}
            or metadata.st_mode & 0o077
            or not 32 <= metadata.st_size <= 514
        ):
            raise ProviderExecutionError(
                "provider_execution_token_file_invalid",
                status_code=503,
            )
        payload = os.read(descriptor, 515)
    finally:
        os.close(descriptor)
    if len(payload) > 514:
        raise ProviderExecutionError(
            "provider_execution_token_file_invalid",
            status_code=503,
        )
    payload = payload.rstrip(b"\r\n")
    try:
        value = payload.decode("ascii")
    except UnicodeError:
        raise ProviderExecutionError(
            "provider_execution_token_file_invalid",
            status_code=503,
        ) from None
    if not _TOKEN_PATTERN.fullmatch(value):
        raise ProviderExecutionError(
            "provider_execution_token_file_invalid",
            status_code=503,
        )
    return payload


def provider_execution_signature_payload(
    *,
    method: str,
    logical_path: str,
    timestamp: str,
    nonce: str,
    node_id: str,
    agent_id: str,
    body_sha256: str,
) -> bytes:
    return "\n".join(
        (
            method.upper(),
            logical_path,
            timestamp,
            nonce,
            node_id,
            agent_id,
            body_sha256,
        )
    ).encode("utf-8")


class ProviderExecutionSecurity:
    """Loopback-only bearer plus request-bound HMAC verifier."""

    _HEADER_NAMES = (
        "Authorization",
        "X-Kolibri-Timestamp",
        "X-Kolibri-Nonce",
        "X-Kolibri-Node-Id",
        "X-Kolibri-Agent-Id",
        "X-Kolibri-Body-SHA256",
        "X-Kolibri-Signature",
    )

    def __init__(
        self,
        *,
        secret: bytes,
        allowed_node_id: str,
        allowed_agent_id: str,
        now: Callable[[], float] = time.time,
    ) -> None:
        try:
            token = secret.decode("ascii")
        except UnicodeError:
            raise ProviderExecutionError(
                "provider_execution_token_invalid",
                status_code=503,
            ) from None
        if (
            not _TOKEN_PATTERN.fullmatch(token)
            or not _IDENTITY_PATTERN.fullmatch(allowed_node_id)
            or not _IDENTITY_PATTERN.fullmatch(allowed_agent_id)
        ):
            raise ProviderExecutionError(
                "provider_execution_security_invalid",
                status_code=503,
            )
        self._secret = secret
        self._allowed_node_id = allowed_node_id
        self._allowed_agent_id = allowed_agent_id
        self._now = now
        self._nonces: dict[str, float] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_settings(cls, settings: Settings) -> "ProviderExecutionSecurity":
        if (
            not settings.provider_execution_enabled
            or settings.provider_execution_allowed_node_id is None
            or settings.provider_execution_allowed_agent_id is None
        ):
            raise ProviderExecutionError(
                "provider_execution_not_configured",
                status_code=503,
            )
        return cls(
            secret=_load_secret_file(),
            allowed_node_id=settings.provider_execution_allowed_node_id,
            allowed_agent_id=settings.provider_execution_allowed_agent_id,
        )

    def authenticate(
        self,
        request: Request,
        body: bytes,
    ) -> tuple[str, str]:
        client_host = request.client.host if request.client is not None else ""
        if not client_host or not _is_loopback(client_host):
            raise ProviderExecutionError(
                "provider_execution_loopback_required",
                status_code=403,
            )
        if any(
            len(request.headers.getlist(header_name)) != 1
            for header_name in self._HEADER_NAMES
        ):
            raise ProviderExecutionError(
                "provider_execution_auth_required",
                status_code=401,
            )
        authorization = request.headers["Authorization"]
        timestamp = request.headers["X-Kolibri-Timestamp"]
        nonce = request.headers["X-Kolibri-Nonce"]
        node_id = request.headers["X-Kolibri-Node-Id"]
        agent_id = request.headers["X-Kolibri-Agent-Id"]
        body_sha256 = request.headers["X-Kolibri-Body-SHA256"]
        signature = request.headers["X-Kolibri-Signature"]
        if (
            not timestamp.isascii()
            or not timestamp.isdigit()
            or len(timestamp) > 12
            or not _NONCE_PATTERN.fullmatch(nonce)
            or not _IDENTITY_PATTERN.fullmatch(node_id)
            or not _IDENTITY_PATTERN.fullmatch(agent_id)
            or not _DIGEST_PATTERN.fullmatch(body_sha256)
            or not _DIGEST_PATTERN.fullmatch(signature)
        ):
            raise ProviderExecutionError(
                "provider_execution_auth_invalid",
                status_code=401,
            )
        now = self._now()
        if abs(int(now) - int(timestamp)) > _AUTH_WINDOW_SECONDS:
            raise ProviderExecutionError(
                "provider_execution_auth_expired",
                status_code=401,
            )
        provided_token = (
            authorization.removeprefix("Bearer ").encode("ascii", "ignore")
            if authorization.startswith("Bearer ")
            else b""
        )
        expected_body_sha256 = hashlib.sha256(body).hexdigest()
        expected_signature = hmac.new(
            self._secret,
            provider_execution_signature_payload(
                method=request.method,
                logical_path=request.url.path,
                timestamp=timestamp,
                nonce=nonce,
                node_id=node_id,
                agent_id=agent_id,
                body_sha256=body_sha256,
            ),
            hashlib.sha256,
        ).hexdigest()
        if (
            not hmac.compare_digest(provided_token, self._secret)
            or not hmac.compare_digest(body_sha256, expected_body_sha256)
            or not hmac.compare_digest(signature, expected_signature)
        ):
            raise ProviderExecutionError(
                "provider_execution_auth_invalid",
                status_code=401,
            )
        if (
            not hmac.compare_digest(node_id, self._allowed_node_id)
            or not hmac.compare_digest(agent_id, self._allowed_agent_id)
        ):
            raise ProviderExecutionError(
                "provider_execution_identity_not_allowed",
                status_code=403,
            )
        nonce_key = hashlib.sha256(
            f"{node_id}\0{agent_id}\0{nonce}".encode("utf-8")
        ).hexdigest()
        with self._lock:
            self._nonces = {
                key: expires_at
                for key, expires_at in self._nonces.items()
                if expires_at > now
            }
            if nonce_key in self._nonces:
                raise ProviderExecutionError(
                    "provider_execution_auth_replay",
                    status_code=409,
                )
            self._nonces[nonce_key] = now + (_AUTH_WINDOW_SECONDS * 2)
        return node_id, agent_id


def _redact_text(
    value: str,
    *,
    limit: int = _MAX_ACTIVITY_STRING,
) -> str:
    bounded = value[:limit]
    for pattern in _SECRET_VALUE_PATTERNS:
        bounded = pattern.sub("[REDACTED]", bounded)
    return bounded


def _sanitize_activity_value(
    value: Any,
    *,
    workspace_root: Path,
    depth: int = 0,
) -> Any:
    if depth >= 5:
        return "[TRUNCATED]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        candidate = value
        if len(candidate) <= 2_048:
            path = Path(candidate)
            if path.is_absolute():
                try:
                    return str(path.resolve().relative_to(workspace_root))
                except (OSError, ValueError):
                    return "[outside-workspace]"
        return _redact_text(candidate)
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for raw_key in list(value)[:64]:
            key = str(raw_key)[:160]
            if _SECRET_KEY_PATTERN.search(key):
                output[key] = "[REDACTED]"
            else:
                output[key] = _sanitize_activity_value(
                    value[raw_key],
                    workspace_root=workspace_root,
                    depth=depth + 1,
                )
        return output
    if isinstance(value, (list, tuple)):
        return [
            _sanitize_activity_value(
                item,
                workspace_root=workspace_root,
                depth=depth + 1,
            )
            for item in value[:64]
        ]
    return _redact_text(str(value))


def _normalize_runtime_error(error: BaseException) -> dict[str, Any]:
    if isinstance(error, AgentRuntimeError):
        code = (
            error.code
            if _PUBLIC_ERROR_CODE_PATTERN.fullmatch(error.code)
            else "agent_runtime_execution_failed"
        )
        return {
            "code": code,
            "category": error.category,
            "retryable": bool(error.retryable),
            "safe_message": "The selected runtime could not complete the task.",
        }
    return {
        "code": "agent_runtime_execution_failed",
        "category": "execution",
        "retryable": False,
        "safe_message": "The selected runtime could not complete the task.",
    }


class ProviderExecutionJournal:
    """Durable exactly-once reservation for one provider-side effect key."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def reserve(
        self,
        execution: ValidatedProviderExecution,
        *,
        owner_id: str,
        now: datetime,
    ) -> tuple[bool, sqlite3.Row | None]:
        now_text = _utc_text(now)
        stale_before = _utc_text(
            now - timedelta(seconds=_EXECUTION_STALE_SECONDS)
        )
        interrupted_error = _canonical_json(
            {
                "code": "provider_execution_interrupted",
                "category": "unavailable",
                "retryable": False,
                "safe_message": (
                    "The selected runtime was interrupted before a terminal "
                    "result was recorded."
                ),
            }
        )
        database = connect_database(self.database_url)
        try:
            with transaction(database, immediate=True):
                database.execute(
                    """
                    UPDATE provider_execution_effects
                    SET state = 'failed',
                        result_json = NULL,
                        error_json = ?,
                        updated_at = ?,
                        completed_at = ?
                    WHERE state = 'executing'
                      AND (
                          execution_deadline_at <= ?
                          OR execution_heartbeat_at <= ?
                      )
                    """,
                    (
                        interrupted_error,
                        now_text,
                        now_text,
                        now_text,
                        stale_before,
                    ),
                )
                row = database.execute(
                    """
                    SELECT *
                    FROM provider_execution_effects
                    WHERE tenant_id = ? AND effect_key = ?
                    """,
                    (execution.tenant_id, execution.effect_key),
                ).fetchone()
                if row is not None:
                    exact_bindings = (
                        ("effect_hash", execution.effect_hash),
                        ("runtime_profile", execution.runtime_profile),
                        ("task_id", execution.task_id),
                        ("attempt_id", execution.attempt_id),
                        ("assignment_id", execution.assignment_id),
                        ("lease_id", execution.lease_id),
                        ("fencing_token", execution.fencing_token),
                        ("slot_id", execution.slot_id),
                    )
                    if any(
                        (
                            not hmac.compare_digest(
                                str(row[field]),
                                str(expected),
                            )
                            if isinstance(expected, str)
                            else int(row[field]) != expected
                        )
                        for field, expected in exact_bindings
                    ):
                        raise ProviderExecutionError(
                            "provider_execution_idempotency_conflict",
                            status_code=409,
                        )
                    return False, row
                try:
                    database.execute(
                        """
                        INSERT INTO provider_execution_effects (
                            tenant_id,
                            effect_key,
                            effect_hash,
                            runtime_profile,
                            task_id,
                            attempt_id,
                            assignment_id,
                            lease_id,
                            fencing_token,
                            slot_id,
                            execution_owner_id,
                            execution_heartbeat_at,
                            execution_deadline_at,
                            state,
                            result_json,
                            error_json,
                            activity_json,
                            created_at,
                            updated_at,
                            completed_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                  'executing', NULL, NULL, '[]', ?, ?, NULL)
                        """,
                        (
                            execution.tenant_id,
                            execution.effect_key,
                            execution.effect_hash,
                            execution.runtime_profile,
                            execution.task_id,
                            execution.attempt_id,
                            execution.assignment_id,
                            execution.lease_id,
                            execution.fencing_token,
                            execution.slot_id,
                            owner_id,
                            now_text,
                            _utc_text(execution.execution_deadline_at),
                            now_text,
                            now_text,
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    raise ProviderExecutionError(
                        "provider_execution_capacity_exhausted",
                        status_code=409,
                    ) from exc
            return True, None
        finally:
            database.close()

    def heartbeat(
        self,
        execution: ValidatedProviderExecution,
        *,
        owner_id: str,
        now: datetime,
    ) -> None:
        database = connect_database(self.database_url)
        try:
            with transaction(database, immediate=True):
                cursor = database.execute(
                    """
                    UPDATE provider_execution_effects
                    SET execution_heartbeat_at = ?,
                        updated_at = ?
                    WHERE tenant_id = ?
                      AND effect_key = ?
                      AND effect_hash = ?
                      AND execution_owner_id = ?
                      AND state = 'executing'
                    """,
                    (
                        _utc_text(now),
                        _utc_text(now),
                        execution.tenant_id,
                        execution.effect_key,
                        execution.effect_hash,
                        owner_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ProviderExecutionError(
                        "provider_execution_authority_lost",
                        status_code=409,
                    )
        finally:
            database.close()

    def succeed(
        self,
        execution: ValidatedProviderExecution,
        result: Mapping[str, Any],
        activity: list[dict[str, Any]],
        *,
        owner_id: str,
        now: str,
    ) -> None:
        database = connect_database(self.database_url)
        try:
            with transaction(database, immediate=True):
                cursor = database.execute(
                    """
                    UPDATE provider_execution_effects
                    SET state = 'succeeded',
                        result_json = ?,
                        error_json = NULL,
                        activity_json = ?,
                        updated_at = ?,
                        completed_at = ?
                    WHERE tenant_id = ?
                      AND effect_key = ?
                      AND effect_hash = ?
                      AND execution_owner_id = ?
                      AND state = 'executing'
                    """,
                    (
                        _canonical_json(result),
                        _canonical_json(activity),
                        now,
                        now,
                        execution.tenant_id,
                        execution.effect_key,
                        execution.effect_hash,
                        owner_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ProviderExecutionError(
                        "provider_execution_journal_conflict",
                        status_code=409,
                    )
        finally:
            database.close()

    def fail(
        self,
        execution: ValidatedProviderExecution,
        error: Mapping[str, Any],
        activity: list[dict[str, Any]],
        *,
        owner_id: str,
        now: str,
    ) -> None:
        database = connect_database(self.database_url)
        try:
            with transaction(database, immediate=True):
                cursor = database.execute(
                    """
                    UPDATE provider_execution_effects
                    SET state = 'failed',
                        result_json = NULL,
                        error_json = ?,
                        activity_json = ?,
                        updated_at = ?,
                        completed_at = ?
                    WHERE tenant_id = ?
                      AND effect_key = ?
                      AND effect_hash = ?
                      AND execution_owner_id = ?
                      AND state = 'executing'
                    """,
                    (
                        _canonical_json(error),
                        _canonical_json(activity),
                        now,
                        now,
                        execution.tenant_id,
                        execution.effect_key,
                        execution.effect_hash,
                        owner_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ProviderExecutionError(
                        "provider_execution_journal_conflict",
                        status_code=409,
                    )
        finally:
            database.close()


class ProviderExecutionService:
    def __init__(
        self,
        *,
        settings: Settings,
        runtime_registry: AgentRuntimeRegistry,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not settings.provider_execution_enabled:
            raise ProviderExecutionError(
                "provider_execution_not_configured",
                status_code=503,
            )
        self.settings = settings
        self.runtime_registry = runtime_registry
        self.journal = ProviderExecutionJournal(settings.database_url)
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.execution_owner_id = f"provider_{uuid.uuid4().hex}"

    def _agent_card(self, runtime_profile: str) -> dict[str, Any]:
        try:
            runtime = self.runtime_registry.require(runtime_profile)
        except AgentRuntimeError as exc:
            raise ProviderExecutionError(
                "provider_execution_runtime_unavailable",
                status_code=503,
            ) from exc
        descriptor = runtime.descriptor
        capability = developer_runtime_capability(runtime_profile)
        digest = hashlib.sha256(
            _canonical_json(
                {
                    "profile_id": descriptor.profile_id,
                    "caller_node_id": (
                        self.settings.provider_execution_allowed_node_id
                    ),
                    "caller_agent_id": (
                        self.settings.provider_execution_allowed_agent_id
                    ),
                    "caller_slot_id": (
                        self.settings.provider_execution_allowed_slot_id
                    ),
                    "version": self.settings.provider_execution_card_version,
                }
            ).encode("utf-8")
        ).hexdigest()
        available = (
            "developer" in descriptor.capabilities.modes
            and descriptor.capabilities.activity_events
            and descriptor.capabilities.persistent_sessions
            and runtime_profile not in self.runtime_registry.start_errors()
        )
        card = {
            "schema_id": "kolibri.agent_card",
            "schema_version": "1.0",
            "agent_card_id": f"agentcard_{digest[:40]}",
            "tenant_scope": "platform",
            "display_name": descriptor.display_name,
            "agent_kind": "worker",
            "capabilities": sorted(
                {
                    "a2a.message.append",
                    "task_owner_state",
                    capability,
                }
            ),
            "skills": [],
            "model_profiles": [],
            "tool_ids": sorted(
                self.settings.provider_execution_allowed_tool_ids
            ),
            "jurisdictions": [],
            "domain_tags": ["developer.runtime"],
            "limits": {
                "max_concurrent_assignments": 1,
                "max_context_bytes": _MAX_REQUEST_BYTES,
                "max_external_spend_minor": 0,
                "currency": "RUB",
                "latency_slo_ms": int(
                    self.settings.provider_execution_timeout_seconds * 1_000
                ),
            },
            "availability": "available" if available else "offline",
            "policy_constraints": [
                "assignment_required",
                _claim_constraint(
                    "agent",
                    self.settings.provider_execution_allowed_agent_id or "",
                ),
                _claim_constraint(
                    "node",
                    self.settings.provider_execution_allowed_node_id or "",
                ),
                _claim_constraint(
                    "slot",
                    self.settings.provider_execution_allowed_slot_id or "",
                ),
                "lease_fence_required",
                "provider_execution_authority",
                f"runtime.profile:{runtime_profile}",
            ],
            "version": self.settings.provider_execution_card_version,
            "updated_at": self.settings.provider_execution_card_updated_at,
        }
        return _contract(card, "kolibri.agent_card")

    def catalog(self) -> dict[str, Any]:
        cards = [
            self._agent_card(descriptor.profile_id)
            for descriptor in self.runtime_registry.descriptors()
            if "developer" in descriptor.capabilities.modes
        ]
        available_cards = [
            card for card in cards if card["availability"] == "available"
        ]
        capabilities = [
            capability
            for card in available_cards
            for capability in card["capabilities"]
            if capability.startswith("developer.runtime.execute.")
        ]
        if len(capabilities) != len(set(capabilities)):
            raise ProviderExecutionError(
                "provider_execution_catalog_ambiguous",
                status_code=503,
            )
        return {
            "schema_id": PROVIDER_EXECUTION_CATALOG_SCHEMA_ID,
            "schema_version": PROVIDER_EXECUTION_SCHEMA_VERSION,
            "agent_cards": available_cards,
        }

    def _validate(
        self,
        value: Any,
        *,
        caller_node_id: str,
        caller_agent_id: str,
    ) -> ValidatedProviderExecution:
        request_value = _strict_mapping(
            value,
            _REQUEST_FIELDS,
            code="provider_execution_request_invalid",
        )
        if (
            request_value["schema_id"]
            != PROVIDER_EXECUTION_REQUEST_SCHEMA_ID
            or request_value["schema_version"]
            != PROVIDER_EXECUTION_SCHEMA_VERSION
            or not isinstance(request_value["effect_key"], str)
            or _EFFECT_KEY_PATTERN.fullmatch(request_value["effect_key"])
            is None
        ):
            raise ProviderExecutionError(
                "provider_execution_request_invalid"
            )
        task = request_value["task"]
        if not isinstance(task, dict):
            raise ProviderExecutionError("provider_execution_task_invalid")
        envelope = task.get("envelope")
        if not isinstance(envelope, dict):
            raise ProviderExecutionError("provider_execution_task_invalid")
        canonical_task = _contract(
            envelope.get("contract_v1"),
            "kolibri.task",
        )
        assignment = _contract(
            request_value["agent_assignment"],
            "kolibri.agent_assignment",
        )
        requester_assignment = _contract(
            request_value["requester_assignment"],
            "kolibri.agent_assignment",
        )
        a2a_request = _contract(
            request_value["a2a_request"],
            "kolibri.a2a.message_appended.event",
        )
        sidecar_value = request_value["source_command_sidecar"]
        if not isinstance(sidecar_value, dict):
            raise ProviderExecutionError(
                "provider_execution_source_sidecar_invalid"
            )
        command = _contract(
            sidecar_value.get("source_command"),
            "kolibri.command",
        )
        payload_contract = (
            command.get("payload_schema_id"),
            command.get("payload_schema_version"),
        )
        trusted_bound = payload_contract == (
            "kolibri.product.run.execute.v1_3.command",
            "1.3",
        )
        if payload_contract not in {
            ("kolibri.product.run.execute.v1_2.command", "1.2"),
            ("kolibri.product.run.execute.v1_3.command", "1.3"),
        }:
            raise ProviderExecutionError(
                "provider_execution_contract_invalid"
            )
        sidecar = _strict_mapping(
            sidecar_value,
            (
                _SOURCE_SIDECAR_FIELDS | _TRUSTED_AGENT_BINDING_FIELDS
                if trusted_bound
                else _SOURCE_SIDECAR_FIELDS
            ),
            code="provider_execution_source_sidecar_invalid",
        )
        if (
            not isinstance(sidecar["source_command_ref"], str)
            or _SOURCE_COMMAND_REF_PATTERN.fullmatch(
                sidecar["source_command_ref"]
            )
            is None
        ):
            raise ProviderExecutionError(
                "provider_execution_source_sidecar_invalid"
            )
        payload = _contract(
            command["payload"],
            str(command["payload_schema_id"]),
        )
        command["payload"] = payload

        task_id = _bounded_identifier(
            task.get("task_id"),
            code="provider_execution_task_invalid",
        )
        attempt_id = _bounded_identifier(
            task.get("attempt_id"),
            code="provider_execution_lease_invalid",
        )
        assignment_id = _bounded_identifier(
            task.get("assignment_id"),
            code="provider_execution_lease_invalid",
        )
        effect_id = _bounded_identifier(
            task.get("effect_id"),
            code="provider_execution_effect_invalid",
        )
        if _EFFECT_ID_PATTERN.fullmatch(effect_id) is None:
            raise ProviderExecutionError(
                "provider_execution_effect_invalid"
            )
        lease_id = _bounded_identifier(
            task.get("lease_id"),
            code="provider_execution_lease_invalid",
        )
        fencing_token = task.get("fencing_token")
        if (
            isinstance(fencing_token, bool)
            or not isinstance(fencing_token, int)
            or fencing_token < 1
            or task.get("state") not in {"leased", "running"}
            or task.get("lease_owner")
            != f"{caller_node_id}:{caller_agent_id}"
            or task.get("lease_slot_id")
            != self.settings.provider_execution_allowed_slot_id
        ):
            raise ProviderExecutionError("provider_execution_lease_invalid")
        try:
            lease_until = float(task["lease_until"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderExecutionError(
                "provider_execution_lease_invalid"
            ) from exc
        now = self.now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        if lease_until <= now.timestamp():
            raise ProviderExecutionError(
                "provider_execution_lease_expired",
                status_code=409,
            )

        runtime_profile = payload["runtime_profile"]
        if (
            runtime_profile == "auto"
            or _RUNTIME_PROFILE_PATTERN.fullmatch(runtime_profile) is None
        ):
            raise ProviderExecutionError(
                "provider_execution_runtime_profile_invalid"
            )
        try:
            runtime = self.runtime_registry.require(runtime_profile)
        except AgentRuntimeError as exc:
            raise ProviderExecutionError(
                "provider_execution_runtime_unavailable",
                status_code=503,
            ) from exc
        descriptor = runtime.descriptor
        if (
            descriptor.profile_id != runtime_profile
            or "developer" not in descriptor.capabilities.modes
            or not descriptor.capabilities.activity_events
            or not descriptor.capabilities.persistent_sessions
            or runtime_profile in self.runtime_registry.start_errors()
        ):
            raise ProviderExecutionError(
                "provider_execution_runtime_unavailable",
                status_code=503,
            )
        card = self._agent_card(runtime_profile)
        expected_constraints = {
            "assignment_required",
            "lease_fence_required",
            "provider_execution_authority",
            _claim_constraint("node", caller_node_id),
            _claim_constraint("agent", caller_agent_id),
            _claim_constraint(
                "slot",
                self.settings.provider_execution_allowed_slot_id or "",
            ),
            f"runtime.profile:{runtime_profile}",
        }
        if (
            set(card["policy_constraints"]) != expected_constraints
            or card["limits"]["max_concurrent_assignments"] != 1
        ):
            raise ProviderExecutionError(
                "provider_execution_agent_card_invalid",
                status_code=503,
            )
        runtime_capability = developer_runtime_capability(runtime_profile)
        access_key = (
            payload["access_mode"],
            payload["sandbox"],
            payload["approval_policy"],
            payload["reviewer"],
        )
        access_policy = _ACCESS_POLICIES.get(access_key)
        if access_policy is None:
            raise ProviderExecutionError(
                "provider_execution_access_policy_invalid"
            )
        if not set(access_policy["tool_ids"]).issubset(
            self.settings.provider_execution_allowed_tool_ids
        ):
            raise ProviderExecutionError(
                "provider_execution_tool_not_allowed",
                status_code=403,
            )

        trusted_binding = (
            {
                field_name: payload[field_name]
                for field_name in _TRUSTED_AGENT_BINDING_FIELDS
            }
            if trusted_bound
            else {}
        )
        expected_source = {
            "kind": (
                "product_run_execute_v1_3"
                if trusted_bound
                else "product_run_execute_v1_2"
            ),
            "message_id": command["message_id"],
            "source_command_ref": sidecar["source_command_ref"],
            "accepted_by": "logical_home_control_plane",
        }
        expected_dispatch = {
            "schema_id": (
                "kolibri.product.developer_dispatch.v1_1"
                if trusted_bound
                else "kolibri.product.developer_dispatch"
            ),
            "schema_version": "1.1" if trusted_bound else "1.0",
            "source_command_ref": sidecar["source_command_ref"],
            "run_id": payload["run_id"],
            "project_id": payload["project_id"],
            "thread_id": payload["thread_id"],
            "input_message_id": payload["input_message_id"],
            "runtime_profile": runtime_profile,
            "runtime_capability": runtime_capability,
            "model": payload["model"],
            "reasoning_effort": payload["reasoning_effort"],
            "service_tier": payload["service_tier"],
            "workspace_ref": payload["workspace_ref"],
            "access_mode": payload["access_mode"],
            "sandbox": payload["sandbox"],
            "approval_policy": payload["approval_policy"],
            "reviewer": payload["reviewer"],
            **trusted_binding,
        }
        expected_command_hash = _sha256_json(command)
        expected_request_hash = _canonical_product_request_hash(command)
        expected_sidecar = {
            "schema_id": (
                "kolibri.product.developer_lease_source.v1_1"
                if trusted_bound
                else "kolibri.product.developer_lease_source"
            ),
            "schema_version": "1.1" if trusted_bound else "1.0",
            "source_command_ref": sidecar["source_command_ref"],
            "canonical_request_hash": expected_request_hash,
            "source_command_hash": expected_command_hash,
            "tenant_id": canonical_task["tenant_id"],
            "task_id": task_id,
            "task_version": canonical_task["version"],
            "attempt_id": attempt_id,
            "assignment_id": assignment_id,
            "effect_id": effect_id,
            "lease_id": lease_id,
            "fencing_token": fencing_token,
            "runtime_profile": runtime_profile,
            "access_policy": access_policy,
            **trusted_binding,
            "source_command": command,
        }
        if sidecar != expected_sidecar:
            raise ProviderExecutionError(
                "provider_execution_source_sidecar_mismatch"
            )
        if (
            envelope.get("source") != expected_source
            or envelope.get("developer_dispatch") != expected_dispatch
            or "source_command" in envelope
            or task.get("kind") != "developer.runtime.execute"
            or canonical_task["kind"] != "developer.runtime.execute"
            or canonical_task["state"] != "leased"
            or canonical_task["task_id"] != task_id
            or canonical_task["current_attempt_id"] != attempt_id
            or canonical_task["current_assignment_id"] != assignment_id
            or canonical_task["tenant_id"] != payload["tenant_id"]
            or canonical_task["goal_id"] != payload["goal_id"]
            or canonical_task["case_id"] != payload["case_id"]
            or canonical_task["required_capabilities"]
            != [runtime_capability]
        ):
            raise ProviderExecutionError(
                "provider_execution_task_binding_mismatch"
            )
        identity = command["identity"]
        if (
            command["command_name"] != "product.run.execute"
            or command["payload_schema_id"] != payload["schema_id"]
            or (
                command["payload_schema_id"],
                command["payload_schema_version"],
            )
            != payload_contract
            or command["target_owner"] != "logical_home_control_plane"
            or identity["tenant_id"] != payload["tenant_id"]
            or identity["authority"]["authority_role"]
            != "product_data_authority"
            or "product.developer.run.execute.request"
            not in identity["authority"]["capabilities"]
            or identity["subject_refs"]["goal_id"] != payload["goal_id"]
            or identity["subject_refs"]["case_id"] != payload["case_id"]
            or identity["subject_refs"]["task_id"] is not None
            or command["trace"]["correlation_id"] != payload["run_id"]
            or command["trace"]["causation_id"]
            != payload["input_message_id"]
            or command["idempotency"]["scope"] != "aggregate"
            or command["idempotency"]["scope_id"] != payload["run_id"]
            or request_value["effect_key"] != effect_id
            or not hmac.compare_digest(
                command["idempotency"]["canonical_request_hash"],
                expected_request_hash,
            )
            or not hmac.compare_digest(
                payload["prompt_hash"],
                _sha256_text(payload["prompt"]),
            )
            or payload["execution_mode"] != "developer"
            or payload["requester_role"] != "owner"
            or payload["workspace_ref"]
            != self.settings.provider_execution_workspace_ref
        ):
            raise ProviderExecutionError(
                "provider_execution_command_binding_mismatch"
            )
        command_deadline = _parse_datetime(command["deadline_at"])
        if command_deadline <= now:
            raise ProviderExecutionError(
                "provider_execution_command_expired",
                status_code=409,
            )
        execution_deadline = min(
            command_deadline,
            now
            + timedelta(
                seconds=self.settings.provider_execution_timeout_seconds
            ),
        )

        common_binding = (
            ("tenant_id", canonical_task["tenant_id"]),
            ("goal_id", canonical_task["goal_id"]),
            ("case_id", canonical_task["case_id"]),
            ("task_id", task_id),
            ("task_version", canonical_task["version"]),
            ("attempt_id", attempt_id),
            ("lease_id", lease_id),
        )
        if any(
            assignment[field] != expected
            or requester_assignment[field] != expected
            for field, expected in common_binding
        ):
            raise ProviderExecutionError(
                "provider_execution_assignment_binding_mismatch"
            )
        assignment_authority = assignment["authority_profile"]
        requester_authority = requester_assignment["authority_profile"]
        expected_resource_refs = sorted(
            {
                canonical_task["goal_id"],
                canonical_task["case_id"],
                task_id,
                sidecar["source_command_ref"],
                *(
                    (
                        payload["trusted_agent_profile_id"],
                        payload["trusted_agent_workspace_binding_id"],
                    )
                    if trusted_bound
                    else ()
                ),
            }
        )
        expected_output_ids = [
            output["output_id"]
            for output in canonical_task["expected_outputs"]
        ]
        expected_runtime_actor = (
            "agent_"
            + _stable_digest(
                card["agent_card_id"],
                card["version"],
                runtime_profile,
            )[:40]
        )
        expected_requester_actor = (
            "service_"
            + _stable_digest(
                requester_assignment["agent_card_id"],
                requester_assignment["agent_card_version"],
            )[:40]
        )
        if (
            assignment["assignment_id"] != assignment_id
            or assignment["status"] != "active"
            or assignment["assignee_actor_id"] != expected_runtime_actor
            or assignment["temporary_role"]
            != "developer.runtime.executor"
            or assignment["agent_card_id"] != card["agent_card_id"]
            or assignment["agent_card_version"] != card["version"]
            or assignment_authority["authority_role"]
            != "logical_home_control_plane"
            or set(assignment_authority["capabilities"])
            != {
                "a2a.message.append",
                "task_owner_state",
                runtime_capability,
            }
            or assignment_authority["allowed_tool_ids"]
            != access_policy["tool_ids"]
            or assignment_authority["allowed_resource_refs"]
            != expected_resource_refs
            or assignment["budget"]
            != {
                "compute_units_limit": access_policy[
                    "compute_units_limit"
                ],
                "tool_calls_limit": access_policy[
                    "tool_calls_limit"
                ],
                "external_spend_limit_minor": 0,
                "currency": "RUB",
            }
            or assignment["context_slice"]["artifact_refs"]
            != [sidecar["source_command_ref"]]
            or assignment["context_slice"]["classification"]
            != "restricted"
            or assignment["context_slice"]["max_bytes"]
            > card["limits"]["max_context_bytes"]
            or assignment["required_output_ids"] != expected_output_ids
            or assignment["required_evidence_types"]
            != ["a2a.handoff_or_rejection"]
            or requester_assignment["assignment_id"] == assignment_id
            or requester_assignment["assignee_actor_id"]
            != expected_requester_actor
            or requester_assignment["assignee_actor_id"]
            == assignment["assignee_actor_id"]
            or requester_assignment["temporary_role"]
            != "developer.requester"
            or requester_assignment["status"] != "active"
            or requester_authority["authority_role"]
            != "logical_home_control_plane"
            or set(requester_authority["capabilities"])
            != {"a2a.message.append", "task_owner_state"}
            or requester_authority["allowed_tool_ids"] != []
            or requester_authority["allowed_resource_refs"]
            != expected_resource_refs
            or requester_assignment["budget"]
            != {
                "compute_units_limit": 0,
                "tool_calls_limit": 0,
                "external_spend_limit_minor": 0,
                "currency": "RUB",
            }
            or requester_assignment["context_slice"]["artifact_refs"]
            != [sidecar["source_command_ref"]]
            or requester_assignment["context_slice"]["classification"]
            != "restricted"
            or requester_assignment["required_output_ids"]
            != expected_output_ids
            or requester_assignment["required_evidence_types"]
            != ["a2a.handoff_or_rejection"]
        ):
            raise ProviderExecutionError(
                "provider_execution_assignment_binding_mismatch"
            )
        if (
            abs(
                _parse_datetime(assignment["deadline_at"]).timestamp()
                - lease_until
            )
            > 0.001
            or abs(
                _parse_datetime(
                    assignment_authority["expires_at"]
                ).timestamp()
                - lease_until
            )
            > 0.001
            or abs(
                _parse_datetime(
                    requester_assignment["deadline_at"]
                ).timestamp()
                - lease_until
            )
            > 0.001
            or abs(
                _parse_datetime(
                    requester_authority["expires_at"]
                ).timestamp()
                - lease_until
            )
            > 0.001
        ):
            raise ProviderExecutionError(
                "provider_execution_assignment_expired",
                status_code=409,
            )

        expected_structured = {
            "expected_response": "a2a.handoff_or_rejection",
            "status": "requested",
            "source_command_ref": sidecar["source_command_ref"],
            "runtime_profile": runtime_profile,
            "model": payload["model"],
            "reasoning_effort": payload["reasoning_effort"],
            "service_tier": payload["service_tier"],
            "workspace_ref": payload["workspace_ref"],
            "access_mode": payload["access_mode"],
            "sandbox": payload["sandbox"],
            "approval_policy": payload["approval_policy"],
            "reviewer": payload["reviewer"],
            **trusted_binding,
            "source_command_hash": expected_command_hash,
            "canonical_request_hash": expected_request_hash,
            "lease": {
                "attempt_id": attempt_id,
                "lease_id": lease_id,
                "fencing_token": fencing_token,
            },
        }
        channel_id = (
            "channel_"
            + _stable_digest(
                canonical_task["tenant_id"],
                payload["run_id"],
                task_id,
            )[:40]
        )
        expected_message_id = (
            "a2amsg_" + _stable_digest(channel_id, "1")[:40]
        )
        expected_content = {
            "trust": "untrusted_content",
            "text": canonical_task["objective"],
            "structured_data": expected_structured,
            "reference_ids": sorted(
                {
                    sidecar["source_command_ref"],
                    task_id,
                    attempt_id,
                    *(
                        (
                            payload["trusted_agent_profile_id"],
                            payload[
                                "trusted_agent_workspace_binding_id"
                            ],
                        )
                        if trusted_bound
                        else ()
                    ),
                }
            ),
        }
        if (
            a2a_request["a2a_message_id"] != expected_message_id
            or a2a_request["tenant_id"] != canonical_task["tenant_id"]
            or a2a_request["goal_id"] != canonical_task["goal_id"]
            or a2a_request["case_id"] != canonical_task["case_id"]
            or a2a_request["task_id"] != task_id
            or a2a_request["task_version"] != canonical_task["version"]
            or a2a_request["channel_id"] != channel_id
            or a2a_request["sequence"] != 1
            or a2a_request["previous_message_id"] is not None
            or a2a_request["sender_assignment_id"]
            != requester_assignment["assignment_id"]
            or a2a_request["sender_actor_id"]
            != requester_assignment["assignee_actor_id"]
            or a2a_request["recipient_assignment_ids"] != [assignment_id]
            or a2a_request["recipient_capability"] != runtime_capability
            or a2a_request["message_type"] != "request"
            or a2a_request["purpose"]
            != "Execute the Home-owned developer task."
            or a2a_request["response_to_message_id"] is not None
            or a2a_request["content"] != expected_content
            or a2a_request["deduplication_key"]
            != (
                "a2a:developer-request:"
                + _stable_digest(
                    canonical_task["tenant_id"],
                    task_id,
                    attempt_id,
                )
            )
            or a2a_request["sent_at"] != assignment["created_at"]
            or a2a_request["sent_at"]
            != requester_assignment["created_at"]
            or _parse_datetime(a2a_request["expires_at"]) <= now
            or not hmac.compare_digest(
                a2a_request["content_hash"],
                _a2a_content_hash(a2a_request),
            )
        ):
            raise ProviderExecutionError(
                "provider_execution_a2a_binding_mismatch"
            )

        workspace_root = self.settings.provider_execution_workspace_root
        if workspace_root is None:
            raise ProviderExecutionError(
                "provider_execution_workspace_unavailable",
                status_code=503,
            )
        access = AgentAccessPolicy(
            mode=payload["access_mode"],
            sandbox=payload["sandbox"],
            approval_policy=payload["approval_policy"],
            approvals_reviewer=payload["reviewer"],
        )
        runtime_request = AgentRuntimeRequest(
            tenant_id=payload["tenant_id"],
            thread_id=payload["thread_id"],
            run_id=payload["run_id"],
            credential_tenant_id=payload["tenant_id"],
            mode="developer",
            execution_profile="developer",
            messages=(
                AgentRuntimeMessage(
                    role="user",
                    content=payload["prompt"],
                ),
            ),
            initial_prompt=payload["prompt"],
            followup_prompt=payload["prompt"],
            instructions=_DEVELOPER_INSTRUCTIONS,
            timeout_seconds=max(
                0.001,
                (execution_deadline - now).total_seconds(),
            ),
            configuration=AgentExecutionConfiguration(
                selection=AgentModelSelection(
                    model_id=payload["model"],
                    reasoning_effort=payload["reasoning_effort"],
                    service_tier=payload["service_tier"],
                    explicit_profile=True,
                ),
                access=access,
                workspace=AgentWorkspace(
                    reference="repository",
                    root=workspace_root,
                ),
            ),
        )
        return ValidatedProviderExecution(
            effect_key=request_value["effect_key"],
            request_hash=_sha256_json(request_value),
            effect_hash=expected_command_hash,
            tenant_id=payload["tenant_id"],
            task_id=task_id,
            attempt_id=attempt_id,
            assignment_id=assignment_id,
            lease_id=lease_id,
            fencing_token=fencing_token,
            slot_id=(
                self.settings.provider_execution_allowed_slot_id or ""
            ),
            runtime_profile=runtime_profile,
            execution_deadline_at=execution_deadline,
            runtime_request=runtime_request,
        )

    @staticmethod
    def _response(
        execution: ValidatedProviderExecution,
        *,
        status: str,
        replayed: bool,
        output: Mapping[str, Any] | None,
        activity: list[dict[str, Any]],
        error: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "schema_id": PROVIDER_EXECUTION_RESULT_SCHEMA_ID,
            "schema_version": PROVIDER_EXECUTION_SCHEMA_VERSION,
            "effect_key": execution.effect_key,
            "request_hash": execution.request_hash,
            "task_id": execution.task_id,
            "attempt_id": execution.attempt_id,
            "assignment_id": execution.assignment_id,
            "lease_id": execution.lease_id,
            "fencing_token": execution.fencing_token,
            "runtime_profile": execution.runtime_profile,
            "status": status,
            "replayed": replayed,
            "output": dict(output) if output is not None else None,
            "activity": activity,
            "error": dict(error) if error is not None else None,
        }

    def execute(
        self,
        value: Any,
        *,
        caller_node_id: str,
        caller_agent_id: str,
    ) -> dict[str, Any]:
        execution = self._validate(
            value,
            caller_node_id=caller_node_id,
            caller_agent_id=caller_agent_id,
        )
        reservation_now = self.now()
        if reservation_now.tzinfo is None:
            reservation_now = reservation_now.replace(tzinfo=timezone.utc)
        reserved, existing = self.journal.reserve(
            execution,
            owner_id=self.execution_owner_id,
            now=reservation_now,
        )
        if not reserved:
            assert existing is not None
            if existing["state"] == "executing":
                raise ProviderExecutionError(
                    "provider_execution_effect_in_progress",
                    status_code=409,
                    message=(
                        "This effect is already executing; retry the same "
                        "fenced request to reconcile its terminal result."
                    ),
                )
            activity = json.loads(str(existing["activity_json"]))
            if existing["state"] == "succeeded":
                output = json.loads(str(existing["result_json"]))
                return self._response(
                    execution,
                    status="completed",
                    replayed=True,
                    output=output,
                    activity=activity,
                    error=None,
                )
            error = json.loads(str(existing["error_json"]))
            return self._response(
                execution,
                status="failed",
                replayed=True,
                output=None,
                activity=activity,
                error=error,
            )

        activity: list[dict[str, Any]] = []
        activity_bytes = 2
        activity_lock = threading.Lock()
        activity_closed = False
        workspace_root = (
            self.settings.provider_execution_workspace_root
            or Path("/")
        )

        def on_activity(phase: str, item: dict[str, Any]) -> None:
            nonlocal activity_bytes
            event = {
                "phase": _redact_text(str(phase))[:120],
                "payload": _sanitize_activity_value(
                    item,
                    workspace_root=workspace_root,
                ),
            }
            encoded = _canonical_json(event).encode("utf-8")
            with activity_lock:
                if (
                    activity_closed
                    or len(activity) >= _MAX_ACTIVITY_EVENTS
                    or activity_bytes + len(encoded)
                    > _MAX_ACTIVITY_BYTES
                ):
                    return
                activity.append(event)
                activity_bytes += len(encoded)

        def close_activity() -> list[dict[str, Any]]:
            nonlocal activity_closed
            with activity_lock:
                activity_closed = True
                return list(activity)

        request = execution.runtime_request
        request = AgentRuntimeRequest(
            tenant_id=request.tenant_id,
            thread_id=request.thread_id,
            run_id=request.run_id,
            credential_tenant_id=request.credential_tenant_id,
            mode=request.mode,
            execution_profile=request.execution_profile,
            messages=request.messages,
            initial_prompt=request.initial_prompt,
            followup_prompt=request.followup_prompt,
            instructions=request.instructions,
            timeout_seconds=request.timeout_seconds,
            guidance=request.guidance,
            configuration=request.configuration,
            output_schema=request.output_schema,
            on_activity=on_activity,
        )
        journal_stop = threading.Event()
        journal_heartbeat_errors: list[BaseException] = []

        def journal_heartbeat_loop() -> None:
            while not journal_stop.wait(_EXECUTION_HEARTBEAT_SECONDS):
                try:
                    self.journal.heartbeat(
                        execution,
                        owner_id=self.execution_owner_id,
                        now=self.now(),
                    )
                except BaseException as exc:
                    journal_heartbeat_errors.append(exc)
                    return

        journal_thread = threading.Thread(
            target=journal_heartbeat_loop,
            name=f"provider-journal-{execution.effect_key[:32]}",
            daemon=True,
        )
        journal_thread.start()
        output: dict[str, Any] | None = None
        runtime_error: BaseException | None = None
        try:
            runtime = self.runtime_registry.require(execution.runtime_profile)
            runtime_result = runtime.execute(request)
            output = self._normalize_result(
                runtime_result,
                workspace_root=workspace_root,
            )
        except Exception as exc:
            runtime_error = exc
        finally:
            journal_stop.set()
            journal_thread.join(
                timeout=_EXECUTION_HEARTBEAT_SECONDS + 1.0
            )

        terminal_now = self.now()
        if terminal_now.tzinfo is None:
            terminal_now = terminal_now.replace(tzinfo=timezone.utc)
        if runtime_error is None and terminal_now >= execution.execution_deadline_at:
            runtime_error = AgentRuntimeError(
                "provider_execution_authority_expired",
                "Provider execution authority expired before completion.",
                category="unavailable",
            )
        if runtime_error is None:
            try:
                # A final durable heartbeat proves that no other reconciler
                # expired or replaced this owner while the runtime was active.
                self.journal.heartbeat(
                    execution,
                    owner_id=self.execution_owner_id,
                    now=terminal_now,
                )
            except ProviderExecutionError as exc:
                runtime_error = AgentRuntimeError(
                    "provider_execution_authority_lost",
                    "Provider execution authority was lost before completion.",
                    category="unavailable",
                )
                runtime_error.__cause__ = exc

        activity_snapshot = close_activity()
        if runtime_error is None:
            assert output is not None
            completed_response = self._response(
                execution,
                status="completed",
                replayed=False,
                output=output,
                activity=activity_snapshot,
                error=None,
            )
            if (
                len(_canonical_json(completed_response).encode("utf-8"))
                > _MAX_RESPONSE_BYTES
            ):
                runtime_error = AgentRuntimeError(
                    "provider_execution_result_too_large",
                    "Provider execution result exceeded the response budget.",
                    category="invalid_output",
                )

        terminal_text = _utc_text(terminal_now)
        if runtime_error is not None:
            error = _normalize_runtime_error(runtime_error)
            self.journal.fail(
                execution,
                error,
                activity_snapshot,
                owner_id=self.execution_owner_id,
                now=terminal_text,
            )
            return self._response(
                execution,
                status="failed",
                replayed=False,
                output=None,
                activity=activity_snapshot,
                error=error,
            )
        assert output is not None
        self.journal.succeed(
            execution,
            output,
            activity_snapshot,
            owner_id=self.execution_owner_id,
            now=terminal_text,
        )
        return completed_response

    @staticmethod
    def _normalize_result(
        result: AgentRuntimeResult,
        *,
        workspace_root: Path,
    ) -> dict[str, Any]:
        if result.text is not None:
            return {
                "response": _redact_text(result.text, limit=200_000),
                "session_id": (
                    _redact_text(result.session_id, limit=256)
                    if result.session_id is not None
                    else None
                ),
                "tool_call": None,
            }
        assert result.tool_call is not None
        return {
            "response": None,
            "session_id": (
                _redact_text(result.session_id, limit=256)
                if result.session_id is not None
                else None
            ),
            "tool_call": {
                "name": result.tool_call.name,
                "arguments": _sanitize_activity_value(
                    dict(result.tool_call.arguments),
                    workspace_root=workspace_root,
                ),
            },
        }


router = APIRouter(tags=["provider execution"])


def _error_response(error: ProviderExecutionError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"code": error.code, "message": error.message},
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _service(request: Request) -> ProviderExecutionService:
    service = getattr(
        request.app.state,
        "provider_execution_service",
        None,
    )
    if not isinstance(service, ProviderExecutionService):
        raise ProviderExecutionError(
            "provider_execution_not_configured",
            status_code=503,
        )
    registry = getattr(
        request.app.state,
        "agent_runtime_registry",
        None,
    )
    if (
        not isinstance(registry, AgentRuntimeRegistry)
        or service.runtime_registry is not registry
    ):
        raise ProviderExecutionError(
            "provider_execution_registry_mismatch",
            status_code=503,
        )
    return service


def _security(request: Request) -> ProviderExecutionSecurity:
    security = getattr(
        request.app.state,
        "provider_execution_security",
        None,
    )
    if not isinstance(security, ProviderExecutionSecurity):
        raise ProviderExecutionError(
            "provider_execution_not_configured",
            status_code=503,
        )
    return security


@router.get(PROVIDER_EXECUTION_PATH)
async def provider_execution_catalog(request: Request) -> JSONResponse:
    try:
        identity = _security(request).authenticate(request, b"")
        del identity
        return JSONResponse(_service(request).catalog())
    except ProviderExecutionError as error:
        return _error_response(error)


@router.post(PROVIDER_EXECUTION_PATH)
async def execute_provider_request(request: Request) -> JSONResponse:
    try:
        body = await request.body()
        if not body or len(body) > _MAX_REQUEST_BYTES:
            raise ProviderExecutionError(
                "provider_execution_request_too_large",
                status_code=413,
            )
        node_id, agent_id = _security(request).authenticate(request, body)
        try:
            value = json.loads(body.decode("utf-8", "strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderExecutionError(
                "provider_execution_request_invalid"
            ) from exc
        result = _service(request).execute(
            value,
            caller_node_id=node_id,
            caller_agent_id=agent_id,
        )
        encoded = _canonical_json(result).encode("utf-8")
        if len(encoded) > _MAX_RESPONSE_BYTES:
            raise ProviderExecutionError(
                "provider_execution_response_too_large",
                status_code=502,
            )
        return JSONResponse(result)
    except ProviderExecutionError as error:
        return _error_response(error)
