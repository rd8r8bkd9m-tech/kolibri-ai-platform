"""Scoped browser access to the canonical OpenAI-compatible Responses API.

Owner API keys continue to use the durable execution store.  A browser gets a
short-lived, same-origin, HttpOnly session which can see only its own ephemeral
project and responses.  Session tokens are opaque and only their SHA-256 hash
is persisted.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from capability_gateway import CapabilityRequestError, get_capability_gateway
from data_paths import DB_PATH
from estimate_artifacts import EstimateArtifactError, materialize_public_estimate_task
from execution_api import (
    ResponseCreate,
    cancel_response as cancel_owner_response,
    create_response as create_owner_response,
    get_learning_boundary,
    get_response as get_owner_response,
    list_response_input_items as list_owner_response_input_items,
    list_responses as list_owner_responses,
    require_execution_auth,
    sanitize_learning_value,
)
from formulalm_boundary import (
    FormulaLMConflictError,
    FormulaLMPolicyError,
    scan_learning_payload,
)
from openai_compatibility import response_input_item_list
from public_chat_stream import verified_public_payload
from providers import ProviderGatewayError
from response_tool_gateway import ResponseToolExecution, execute_response_tools
from vertical_tasks import (
    build_deterministic_estimate_fallback,
    build_vertical_result,
    deterministic_estimate_fallback_text,
    deterministic_estimate_fallback_verification,
    deterministic_estimate_result_text,
    deterministic_estimate_result_verification,
    failed_vertical_result,
    prepare_vertical_task,
)
from web_search_gateway import TOOL_ID as WEB_SEARCH_TOOL_ID
from web_search_gateway import WebSearchError, WebSearchPolicyError
from work_summary import (
    build_work_summary,
    reasoning_output_item,
    summary_metadata,
)


COOKIE_NAME = "kolibri_public_session"
MAX_REQUEST_BYTES = 1024 * 1024
MAX_MESSAGES = 100
MAX_SESSION_COOKIE_CANDIDATES = 8
PUBLIC_TOOL_ALIASES = frozenset({
    WEB_SEARCH_TOOL_ID, "web_search", "web_search_preview", "search_web",
})
_CANONICAL_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_PUBLIC_SESSION_TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,128}$")


def _now() -> float:
    return time.time()


def _opaque_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _provider_routing(value: Any) -> dict[str, Any]:
    """Return the internal routing envelope without ever exposing it publicly."""

    if not isinstance(value, dict):
        return {}
    technical = value.get("technical")
    if isinstance(technical, dict) and isinstance(technical.get("provider_routing"), dict):
        return technical["provider_routing"]
    return value if any(key in value for key in ("attempts", "evidence", "error_type")) else {}


def _sha256_artifact_hashes(*values: Any) -> list[str]:
    """Collect only canonical content digests from already bounded evidence."""

    found: set[str] = set()

    def walk(value: Any, *, key: str = "", depth: int = 0) -> None:
        if depth > 12:
            return
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, key=str(child_key).lower(), depth=depth + 1)
            return
        if isinstance(value, (list, tuple)):
            for child in value:
                walk(child, key=key, depth=depth + 1)
            return
        if not isinstance(value, str):
            return
        digest = value.lower().removeprefix("sha256:")
        if (
            _CANONICAL_SHA256.fullmatch(digest)
            and any(marker in key for marker in ("sha256", "digest", "content_hash"))
            and not any(marker in key for marker in ("binding", "idempotency", "authorization"))
        ):
            found.add(f"sha256:{digest}")

    for item in values:
        walk(item)
    return sorted(found)


def _record_public_learning_tap(
    *,
    session: dict[str, Any],
    body: ResponseCreate,
    response_id: str,
    response_status: str,
    response_text: str,
    verification: dict[str, Any] | None,
    provider_routing: dict[str, Any] | None,
    tool_execution: ResponseToolExecution,
    task: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a candidate-only FormulaLM tap isolated from public execution.

    Raw session identifiers never cross the learning boundary.  The trace binds
    the exact ephemeral response, session, project and provider/tool attempt
    evidence by hashes.  ``enqueue_trace`` performs the strict secret/PII scan
    and stores no trace content when consent, licence, retention or quality
    policy rejects it.  It cannot train, create a candidate or promote weights
    in the request path.
    """

    session_sha256 = _sha256(str(session["id"]))
    project_sha256 = _sha256(str(session["project_id"]))
    routing = provider_routing if isinstance(provider_routing, dict) else {}
    attempts = routing.get("attempts") if isinstance(routing.get("attempts"), list) else []
    evidence = routing.get("evidence") if isinstance(routing.get("evidence"), list) else []
    tool_attempts = list(tool_execution.attempts)
    tool_calls = list(tool_execution.tool_calls)
    formula_tool_taps = list(tool_execution.formulalm_taps)
    verification = verification if isinstance(verification, dict) else {}
    attempt_binding = {
        "schema_version": "kolibri.public-learning-binding.v1",
        "response_id": response_id,
        "public_session_sha256": session_sha256,
        "project_sha256": project_sha256,
        "execution_mode": body.execution_mode,
        "provider_attempts": attempts,
        "provider_evidence": evidence,
        "tool_attempts": tool_attempts,
        "tool_calls": tool_calls,
        "verification": verification,
    }
    # Hash sanitized structures so even a malicious provider error cannot turn
    # a secret or PII value into a durable/public correlation oracle.  The raw
    # trace still goes to ``enqueue_trace`` so its scanner rejects the intake.
    attempt_binding_sha256 = _json_hash(scan_learning_payload(attempt_binding).sanitized)
    trace = {
        "request": {
            "input": body.input,
            "instructions": body.instructions,
            "tools": body.tools,
        },
        "response": {
            "status": response_status,
            "output_text": response_text if response_status == "completed" else "",
            "task": task,
        },
        "decisions": {
            "selected_provider": routing.get("selected_provider"),
            "fallback_used": routing.get("fallback_used"),
            "provider_attempts": attempts,
            "tool_attempts": tool_attempts,
            "tool_calls": tool_calls,
            "formulalm_tool_taps": formula_tool_taps,
        },
        "binding": {
            "response_id": response_id,
            "public_session_sha256": session_sha256,
            "project_sha256": project_sha256,
            "attempt_evidence_sha256": attempt_binding_sha256,
            "verification": verification,
        },
    }
    content_sha256 = _json_hash(scan_learning_payload(trace).sanitized)
    passed = response_status == "completed" and verification.get("status") == "passed"
    verification_type = str(verification.get("type") or "provider_response")
    deterministic_engine_passed = passed and verification_type == "deterministic_estimate_engine"
    provider_passed = passed and not deterministic_engine_passed
    quality = {
        "response_status": response_status,
        "quality_verdict": "passed" if passed else "failed",
        "verifier_verdict": "passed" if passed else "failed",
        "credit_assignment": {
            "provider_execution": 1.0 if provider_passed and evidence else 0.0,
            "deterministic_estimate_engine": 1.0 if deterministic_engine_passed else 0.0,
            "tool_execution": 1.0 if provider_passed and tool_calls else 0.0,
            "verifier": 1.0 if passed else 0.0,
        },
    }
    policy = body.learning.model_dump(mode="json")
    artifact_hashes = _sha256_artifact_hashes(evidence, tool_execution.evidence, task)
    base = {
        "content_sha256": content_sha256,
        "attempt_evidence_sha256": attempt_binding_sha256,
        "candidate_only": True,
        "async_queue": False,
        "auto_promote": False,
        "request_path_training": False,
        "production_weight_mutation": False,
    }
    try:
        intake = get_learning_boundary().enqueue_trace(
            idempotency_key=f"public-trace:{response_id}",
            source_trace_id=response_id,
            source_response_id=response_id,
            capability=policy["capability"],
            trace=trace,
            provenance={
                "actor": (
                    "public-deterministic-estimate-engine"
                    if deterministic_engine_passed
                    else "public-provider-gateway"
                ),
                "principal": f"public-session:{session_sha256[:16]}",
                "policy_version": "kolibri.formulalm-public-policy.v1",
                "response_id": response_id,
                "public_session_sha256": session_sha256,
                "project_sha256": project_sha256,
                "attempt_evidence_sha256": attempt_binding_sha256,
            },
            policy=policy,
            quality=quality,
            artifact_hashes=artifact_hashes,
        )
        return {
            **base,
            "status": intake["status"],
            "rejection_code": intake.get("rejection_code"),
            "async_queue": intake["status"] == "queued",
        }
    except (FormulaLMPolicyError, FormulaLMConflictError) as exc:
        return {**base, "status": "rejected", "rejection_code": exc.code}
    except Exception:
        # Learning is deliberately fail-isolated from customer inference.  The
        # public result stays truthful and records no synthetic success claim.
        return {
            **base,
            "status": "unavailable",
            "rejection_code": "learning_boundary_unavailable",
        }


def _normalized_origin(value: str) -> str:
    text = value.strip().rstrip("/")
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
        raise HTTPException(status_code=403, detail="public_session_origin_invalid")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise HTTPException(status_code=403, detail="public_session_origin_invalid")
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _configured_origins() -> frozenset[str]:
    raw = os.environ.get(
        "KOLIBRI_PUBLIC_SESSION_ORIGINS",
        os.environ.get(
            "KOLIBRI_CORS_ORIGINS",
            "https://kolibriai.ru,https://www.kolibriai.ru,"
            "http://127.0.0.1:5174,http://localhost:5174,"
            "http://127.0.0.1:4174,http://localhost:4174",
        ),
    )
    values: set[str] = set()
    for item in raw.split(","):
        if not item.strip() or item.strip() == "*":
            continue
        try:
            values.add(_normalized_origin(item))
        except HTTPException:
            continue
    return frozenset(values)


_PUBLIC_ORIGINS = _configured_origins()


def configure_public_response_origins(origins: list[str] | tuple[str, ...]) -> None:
    global _PUBLIC_ORIGINS
    _PUBLIC_ORIGINS = frozenset(_normalized_origin(item) for item in origins)


def _required_origin(request: Request) -> str:
    raw = request.headers.get("Origin", "")
    if not raw:
        raise HTTPException(status_code=403, detail="public_session_origin_required")
    origin = _normalized_origin(raw)
    if origin not in _PUBLIC_ORIGINS:
        raise HTTPException(status_code=403, detail="public_session_origin_forbidden")
    return origin


def _validate_session_origin(request: Request, session: dict[str, Any], *, required: bool) -> None:
    fetch_site = request.headers.get("Sec-Fetch-Site", "").strip().lower()
    if fetch_site in {"cross-site", "none"}:
        raise HTTPException(status_code=403, detail="public_session_cross_site_forbidden")
    raw = request.headers.get("Origin", "")
    if required and not raw:
        raise HTTPException(status_code=403, detail="public_session_origin_required")
    if raw:
        origin = _normalized_origin(raw)
        if origin not in _PUBLIC_ORIGINS or not hmac.compare_digest(origin, session["origin"]):
            raise HTTPException(status_code=403, detail="public_session_origin_mismatch")


def _session_ttl_seconds() -> int:
    try:
        value = int(os.environ.get("KOLIBRI_PUBLIC_SESSION_TTL_SECONDS", "900"))
    except ValueError:
        value = 900
    return min(3600, max(60, value))


def _response_rate_limit() -> int:
    try:
        value = int(os.environ.get("KOLIBRI_PUBLIC_SESSION_REQUESTS_PER_MINUTE", "30"))
    except ValueError:
        value = 30
    return min(300, max(1, value))


class PublicResponseStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._lock, self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS public_response_sessions (
                    session_id TEXT PRIMARY KEY,
                    token_sha256 TEXT NOT NULL UNIQUE,
                    origin TEXT NOT NULL,
                    project_id TEXT NOT NULL UNIQUE,
                    issued_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS public_session_responses (
                    response_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    input_json TEXT,
                    http_status INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    UNIQUE(session_id, idempotency_key),
                    FOREIGN KEY(session_id) REFERENCES public_response_sessions(session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_public_responses_session
                    ON public_session_responses(session_id, created_at);
                CREATE TABLE IF NOT EXISTS public_session_rate_limits (
                    subject_sha256 TEXT PRIMARY KEY,
                    window_started REAL NOT NULL,
                    request_count INTEGER NOT NULL
                );
                """
            )
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(public_session_responses)")
            }
            if "input_json" not in columns:
                # Existing public responses expire quickly.  Do not backfill
                # this field from context_json because that value can contain
                # previous-response history and provider-only instructions.
                connection.execute(
                    "ALTER TABLE public_session_responses ADD COLUMN input_json TEXT"
                )

    @staticmethod
    def _session_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["session_id"],
            "origin": row["origin"],
            "project_id": row["project_id"],
            "issued_at": float(row["issued_at"]),
            "expires_at": float(row["expires_at"]),
        }

    def _cleanup(self, connection: sqlite3.Connection, now: float) -> None:
        connection.execute("DELETE FROM public_session_responses WHERE expires_at <= ?", (now,))
        connection.execute("DELETE FROM public_response_sessions WHERE expires_at <= ? OR revoked = 1", (now,))
        connection.execute("DELETE FROM public_session_rate_limits WHERE window_started < ?", (now - 120,))

    def consume_rate(self, subject: str, *, limit: int, window_seconds: int = 60) -> bool:
        now = _now()
        subject_hash = _sha256(subject)
        with self._lock, self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup(connection, now)
            row = connection.execute(
                "SELECT window_started, request_count FROM public_session_rate_limits WHERE subject_sha256 = ?",
                (subject_hash,),
            ).fetchone()
            if row is None or now - float(row["window_started"]) >= window_seconds:
                connection.execute(
                    "INSERT OR REPLACE INTO public_session_rate_limits(subject_sha256, window_started, request_count) VALUES (?, ?, 1)",
                    (subject_hash, now),
                )
                return True
            if int(row["request_count"]) >= limit:
                return False
            connection.execute(
                "UPDATE public_session_rate_limits SET request_count = request_count + 1 WHERE subject_sha256 = ?",
                (subject_hash,),
            )
            return True

    def issue(self, origin: str, *, ttl_seconds: int) -> tuple[dict[str, Any], str]:
        now = _now()
        token = secrets.token_urlsafe(32)
        session = {
            "id": _opaque_id("psess"),
            "origin": origin,
            "project_id": _opaque_id("project_ephemeral"),
            "issued_at": now,
            "expires_at": now + ttl_seconds,
        }
        with self._lock, self.connect() as connection:
            self._cleanup(connection, now)
            connection.execute(
                """INSERT INTO public_response_sessions
                   (session_id, token_sha256, origin, project_id, issued_at, expires_at, revoked)
                   VALUES (?, ?, ?, ?, ?, ?, 0)""",
                (
                    session["id"], _sha256(token), origin, session["project_id"],
                    session["issued_at"], session["expires_at"],
                ),
            )
        return session, token

    def resolve(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        now = _now()
        token_hash = _sha256(token)
        with self._lock, self.connect() as connection:
            self._cleanup(connection, now)
            row = connection.execute(
                """SELECT * FROM public_response_sessions
                   WHERE token_sha256 = ? AND revoked = 0 AND expires_at > ?""",
                (token_hash, now),
            ).fetchone()
        return self._session_row(row) if row is not None else None

    def begin_response(
        self,
        session: dict[str, Any],
        *,
        response_id: str,
        idempotency_key: str,
        request_sha256: str,
        payload: dict[str, Any],
        context: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], bool, int]:
        now = _now()
        idempotency_hash = _sha256(idempotency_key)
        with self._lock, self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup(connection, now)
            row = connection.execute(
                """SELECT request_sha256, payload, http_status FROM public_session_responses
                   WHERE session_id = ? AND idempotency_key = ?""",
                (session["id"], idempotency_hash),
            ).fetchone()
            if row is not None:
                if not hmac.compare_digest(row["request_sha256"], request_sha256):
                    raise HTTPException(status_code=409, detail="idempotency_key_reused_with_different_payload")
                return json.loads(row["payload"]), False, int(row["http_status"])
            connection.execute(
                """INSERT INTO public_session_responses
                   (response_id, session_id, project_id, idempotency_key, request_sha256,
                    payload, context_json, input_json, http_status, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 202, ?, ?)""",
                (
                    response_id, session["id"], session["project_id"], idempotency_hash,
                    request_sha256, json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    json.dumps(context, ensure_ascii=False, sort_keys=True),
                    json.dumps(context, ensure_ascii=False, sort_keys=True), now,
                    session["expires_at"],
                ),
            )
        return payload, True, 202

    def finish_response(
        self,
        session_id: str,
        response_id: str,
        payload: dict[str, Any],
        context: list[dict[str, Any]],
        *,
        http_status: int,
    ) -> dict[str, Any]:
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                """UPDATE public_session_responses
                   SET payload = ?, context_json = ?, http_status = ?
                   WHERE response_id = ? AND session_id = ?""",
                (
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    json.dumps(context, ensure_ascii=False, sort_keys=True),
                    http_status, response_id, session_id,
                ),
            )
            if cursor.rowcount != 1:
                raise HTTPException(status_code=404, detail="response_not_found")
        return payload

    def get_response(self, session_id: str, response_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], int] | None:
        now = _now()
        with self._lock, self.connect() as connection:
            self._cleanup(connection, now)
            row = connection.execute(
                """SELECT payload, context_json, http_status FROM public_session_responses
                   WHERE session_id = ? AND response_id = ? AND expires_at > ?""",
                (session_id, response_id, now),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload"]), json.loads(row["context_json"]), int(row["http_status"])

    def list_responses(self, session_id: str) -> list[dict[str, Any]]:
        now = _now()
        with self._lock, self.connect() as connection:
            self._cleanup(connection, now)
            rows = connection.execute(
                """SELECT payload FROM public_session_responses
                   WHERE session_id = ? AND expires_at > ? ORDER BY created_at DESC""",
                (session_id, now),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def get_response_input(self, session_id: str, response_id: str) -> list[dict[str, Any]]:
        now = _now()
        with self._lock, self.connect() as connection:
            self._cleanup(connection, now)
            row = connection.execute(
                """SELECT input_json FROM public_session_responses
                   WHERE session_id = ? AND response_id = ? AND expires_at > ?""",
                (session_id, response_id, now),
            ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=404,
                detail="response_not_found",
                headers={"Cache-Control": "no-store"},
            )
        if row["input_json"] is None:
            raise HTTPException(
                status_code=409,
                detail="input_items_not_recorded_for_legacy_response",
                headers={"Cache-Control": "no-store"},
            )
        value = json.loads(row["input_json"])
        return value if isinstance(value, list) else []

    def expire_session_for_test(self, session_id: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                "UPDATE public_response_sessions SET expires_at = 0 WHERE session_id = ?",
                (session_id,),
            )


_STORE = PublicResponseStore(DB_PATH)


def configure_public_response_store(path: str | Path) -> PublicResponseStore:
    global _STORE
    _STORE = PublicResponseStore(path)
    return _STORE


PublicExecutor = Callable[..., Awaitable[dict[str, Any]]]
_EXECUTOR: PublicExecutor | None = None


def configure_public_response_executor(executor: PublicExecutor | None) -> None:
    global _EXECUTOR
    _EXECUTOR = executor


def _owner_principal(request: Request) -> str | None:
    if request.headers.get("Authorization", "").strip():
        return require_execution_auth(request)
    return None


def _session_cookie_candidates(request: Request) -> list[str]:
    """Return bounded duplicate cookie values in wire order.

    Browsers may retain an older cookie with the same name on ``Path=/`` while
    the current session uses ``Path=/v1``. Starlette's cookie mapping collapses
    duplicate names, so a stale shorter-path value can shadow the valid token.
    Trying each bounded opaque candidate recovers the valid session without
    exposing, logging or weakening validation of either token.
    """

    candidates: list[str] = []
    seen: set[str] = set()
    for raw_name, raw_value in request.scope.get("headers", []):
        if raw_name.lower() != b"cookie":
            continue
        header = raw_value.decode("latin-1", errors="ignore")[:4096]
        for item in header.split(";"):
            name, separator, value = item.partition("=")
            token = value.strip()
            if (
                separator
                and name.strip() == COOKIE_NAME
                and token not in seen
                and _PUBLIC_SESSION_TOKEN.fullmatch(token)
            ):
                seen.add(token)
                candidates.append(token)
                if len(candidates) >= MAX_SESSION_COOKIE_CANDIDATES:
                    return candidates
    parsed = request.cookies.get(COOKIE_NAME, "")
    if parsed not in seen and _PUBLIC_SESSION_TOKEN.fullmatch(parsed):
        candidates.append(parsed)
    return candidates


def _require_session(request: Request, *, mutating: bool) -> dict[str, Any]:
    session = None
    for token in _session_cookie_candidates(request):
        session = _STORE.resolve(token)
        if session is not None:
            break
    if session is None:
        # An expired session is an authentication state transition, never a
        # cacheable API result.  This also prevents a retired browser cache or
        # intermediary from replaying the marker after the Shell has issued a
        # fresh cookie and retried the idempotent request.
        raise HTTPException(
            status_code=401,
            detail="public_session_required_or_expired",
            headers={"Cache-Control": "no-store"},
        )
    _validate_session_origin(request, session, required=mutating)
    return session


def require_public_response_session(request: Request, *, mutating: bool = False) -> dict[str, Any]:
    """Shared session boundary for same-origin public V1 extensions."""

    return _require_session(request, mutating=mutating)


def _input_messages(input_value: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
    messages = [{"role": "user", "content": input_value}] if isinstance(input_value, str) else input_value
    if not messages or len(messages) > MAX_MESSAGES:
        raise HTTPException(status_code=422, detail="input must contain between 1 and 100 messages")
    normalized: list[dict[str, Any]] = []
    for item in messages:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant", "system", "developer"}:
            raise HTTPException(status_code=422, detail="input contains an invalid message")
        if "content" not in item:
            raise HTTPException(status_code=422, detail="input message content is required")
        normalized.append({"role": item["role"], "content": item["content"]})
    if len(json.dumps(normalized, ensure_ascii=False).encode("utf-8")) > MAX_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="response input exceeds 1 MiB")
    return normalized


def _response_shell(
    response_id: str,
    body: ResponseCreate,
    project_id: str,
    *,
    status: str,
    public_tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    task = body.task.model_dump(mode="json") if body.task is not None else None
    work_summary = build_work_summary(
        response_status=status,
        task=task,
        requested_tools=public_tools,
    )
    return {
        "id": response_id,
        "object": "response",
        "created_at": int(_now()),
        "status": status,
        "completed_at": None,
        "error": None,
        "incomplete_details": None,
        "instructions": body.instructions,
        "max_output_tokens": None,
        "model": "kolibri",
        "output": [],
        "parallel_tool_calls": True,
        "previous_response_id": body.previous_response_id,
        "reasoning": {"effort": None, "summary": None},
        "store": False,
        "temperature": None,
        "text": {"format": {"type": "text"}},
        "tool_choice": "auto",
        "tools": list(public_tools or []),
        "top_p": None,
        "truncation": "disabled",
        "usage": None,
        "metadata": summary_metadata(
            sanitize_learning_value(body.metadata),
            work_summary,
        ),
        "project_id": project_id,
        "execution_mode": body.execution_mode,
    }


def _decorate_response_work_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Add the public summary to owner responses without exposing technical data."""

    response = dict(payload)
    technical = response.get("technical")
    routing = (
        technical.get("provider_routing")
        if isinstance(technical, dict) and isinstance(technical.get("provider_routing"), dict)
        else {}
    )
    verification = response.get("verification")
    if not isinstance(verification, dict):
        candidate = routing.get("verifier_evidence")
        verification = candidate if isinstance(candidate, dict) else None
    task = response.get("task") if isinstance(response.get("task"), dict) else None
    requested_tools = response.get("tools") if isinstance(response.get("tools"), list) else []
    tool_calls = routing.get("tool_calls") if isinstance(routing.get("tool_calls"), list) else []
    citations = response.get("citations") if isinstance(response.get("citations"), list) else []
    work_summary = build_work_summary(
        response_status=str(response.get("status") or "in_progress"),
        task=task,
        requested_tools=requested_tools,
        tool_calls=tool_calls,
        citations=citations,
        verification=verification,
    )
    response["metadata"] = summary_metadata(
        response.get("metadata") if isinstance(response.get("metadata"), dict) else {},
        work_summary,
    )
    output = list(response.get("output") or [])
    if response.get("id") and not any(
        isinstance(item, dict) and item.get("type") == "reasoning" for item in output
    ):
        output.append(reasoning_output_item(str(response["id"]), work_summary))
    response["output"] = output
    return response


def _public_tool_identifier(item: dict[str, Any]) -> str:
    request_type = str(item.get("type") or "").strip().lower()
    if request_type in {"function", "skill", "tool"}:
        # Public sessions never invoke user-defined functions, skills, or a
        # generic tool envelope. Only the built-in scoped search declaration
        # is accepted.
        return ""
    return str(item.get("id") or item.get("name") or request_type).strip().lower()


def _validate_public_tools(
    raw_tools: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not raw_tools:
        return [], []
    if len(raw_tools) != 1 or not isinstance(raw_tools[0], dict):
        raise HTTPException(status_code=422, detail="public_session_tool_not_allowed")
    raw = raw_tools[0]
    identifier = _public_tool_identifier(raw)
    if identifier not in PUBLIC_TOOL_ALIASES:
        raise HTTPException(status_code=422, detail="public_session_tool_not_allowed")
    context_size = str(raw.get("search_context_size") or "medium").strip().lower()
    if context_size not in {"low", "medium", "high"}:
        raise HTTPException(status_code=422, detail="web_search_context_size_invalid")
    try:
        bindings = get_capability_gateway().validate_requested_tools(raw_tools)
    except CapabilityRequestError as exc:
        raise HTTPException(status_code=422, detail=exc.public_detail()) from exc
    if len(bindings) != 1 or bindings[0].get("id") != WEB_SEARCH_TOOL_ID:
        raise HTTPException(status_code=422, detail="public_session_tool_not_allowed")
    declaration = {"type": "web_search", "search_context_size": context_size}
    return bindings, [declaration]


def _request_key(body: ResponseCreate, request: Request) -> str:
    value = body.idempotency_key or request.headers.get("Idempotency-Key", "")
    if not value or len(value) > 300 or not value.strip():
        raise HTTPException(status_code=422, detail="idempotency_key_required_for_public_session")
    return value.strip()


def _request_semantics(body: ResponseCreate) -> dict[str, Any]:
    return body.model_dump(mode="json", exclude={"idempotency_key", "stream"})


def _provider_failure_reason(routing: dict[str, Any]) -> str:
    """Return a bounded non-secret reason for deterministic fallback proof."""

    value = str(routing.get("error_type") or "").strip().lower()
    if not value:
        attempts = routing.get("attempts") if isinstance(routing.get("attempts"), list) else []
        failed = [
            str(item.get("error_type") or "").strip().lower()
            for item in attempts
            if isinstance(item, dict) and item.get("status") in {"failed", "skipped"}
        ]
        value = failed[-1] if failed else "provider_unavailable"
    return value if re.fullmatch(r"[a-z0-9_]{1,80}", value) else "provider_unavailable"


def _complete_deterministic_estimate_fallback(
    *,
    session: dict[str, Any],
    body: ResponseCreate,
    response_id: str,
    base: dict[str, Any],
    context: list[dict[str, Any]],
    provider_routing: dict[str, Any],
    tool_execution: ResponseToolExecution,
) -> tuple[dict[str, Any], int] | None:
    """Complete a narrow estimate with a truthfully bound local engine.

    The caller invokes this only after ``ProviderGatewayError``, which means
    the configured provider gateway already exhausted its allowed routes.  An
    explicitly requested web/tool capability disables the assumption fallback:
    current-source requests must not be replaced with a local price template.
    """

    if body.task is None or body.tools or tool_execution.tool_calls:
        return None
    task_payload = build_deterministic_estimate_fallback(
        body.task,
        reason=_provider_failure_reason(provider_routing),
    )
    if task_payload is None:
        return None
    try:
        task_payload = materialize_public_estimate_task(
            session=session,
            response_id=response_id,
            task=task_payload,
            request_metadata=body.metadata,
        )
    except EstimateArtifactError:
        # The editable calculation remains verified.  Artifact delivery stays
        # incomplete, and no PDF claim is made without persisted bytes.
        pass
    verification = deterministic_estimate_fallback_verification(task_payload)
    text = deterministic_estimate_fallback_text(task_payload)
    verification = {**verification, "output_sha256": _sha256(text)}
    work_summary = build_work_summary(
        response_status="completed",
        task=task_payload,
        requested_tools=[],
        tool_calls=[],
        citations=[],
        verification=verification,
    )
    payload = {
        **base,
        "status": "completed",
        "completed_at": int(_now()),
        "output": [{
            "id": _opaque_id("msg"),
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{
                "type": "output_text",
                "text": text,
                "annotations": [],
            }],
        }],
        "output_text": text,
        "verification": verification,
        "citations": [],
        "tool_calls": [],
        "task": task_payload,
        "metadata": summary_metadata(base.get("metadata"), work_summary),
    }
    payload["output"].append(reasoning_output_item(response_id, work_summary))
    payload["learning_tap"] = _record_public_learning_tap(
        session=session,
        body=body,
        response_id=response_id,
        response_status="completed",
        response_text=text,
        verification=verification,
        provider_routing=provider_routing,
        tool_execution=tool_execution,
        task=task_payload,
    )
    _STORE.finish_response(session["id"], response_id, payload, context, http_status=200)
    return payload, 200


async def _complete_public_response(
    session: dict[str, Any],
    body: ResponseCreate,
    response_id: str,
    current_context: list[dict[str, Any]],
    requested_tools: list[dict[str, Any]],
    public_tools: list[dict[str, Any]],
) -> tuple[dict[str, Any], int]:
    context = list(current_context)
    if body.previous_response_id:
        previous = _STORE.get_response(session["id"], body.previous_response_id)
        if previous is None:
            raise HTTPException(status_code=404, detail="previous_response_not_found_in_session")
        _, previous_context, _ = previous
        context = [*previous_context, *context]
    if body.instructions:
        context.insert(0, {"role": "system", "content": body.instructions})
    calculation = None
    if body.task is not None:
        task_instructions, calculation = prepare_vertical_task(body.task)
        context.insert(0, {"role": "system", "content": task_instructions})
    if len(json.dumps(context, ensure_ascii=False).encode("utf-8")) > MAX_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="response context exceeds 1 MiB")

    base = _response_shell(
        response_id,
        body,
        session["project_id"],
        status="in_progress",
        public_tools=public_tools,
    )
    provider_routing: dict[str, Any] = {}
    tool_execution = ResponseToolExecution(
        provider_tools=requested_tools,
        provider_instructions=None,
        tool_calls=[],
        evidence=[],
        citations=[],
        attempts=[],
        formulalm_taps=[],
    )
    try:
        if requested_tools:
            tool_execution = await run_in_threadpool(partial(
                execute_response_tools,
                input_value=body.input,
                instructions=None,
                response_id=response_id,
                principal=f"public-session:{_sha256(session['id'])}",
                requested_tools=requested_tools,
                raw_tools=body.tools,
                project_id=session["project_id"],
                session_id=session["id"],
            ))
        if tool_execution.provider_tools:
            raise WebSearchPolicyError("public_session_tool_not_allowed")
        execution_context = list(context)
        if tool_execution.provider_instructions:
            execution_context.insert(0, {
                "role": "system",
                "content": tool_execution.provider_instructions,
            })
        if _EXECUTOR is None:
            raise RuntimeError("public_response_executor_not_configured")
        result = await _EXECUTOR(
            messages=execution_context,
            model="kolibri",
            execution_mode=body.execution_mode,
            response_id=response_id,
        )
        provider_routing = _provider_routing(result)
        if body.task is not None:
            task_payload = build_vertical_result(body.task, result, calculation)
            try:
                task_payload = materialize_public_estimate_task(
                    session=session,
                    response_id=response_id,
                    task=task_payload,
                    request_metadata=body.metadata,
                )
            except EstimateArtifactError:
                # The typed result may remain usable, but no artifact or saved
                # revision is claimed unless content-bound materialization
                # actually succeeded.
                pass
            result = {**result, "task": task_payload}
        public = verified_public_payload(result)
        public_task = public.get("task") if isinstance(public.get("task"), dict) else None
        readiness_result = (
            public_task.get("result")
            if isinstance(public_task, dict) and isinstance(public_task.get("result"), dict)
            else None
        )
        if isinstance(readiness_result, dict) and readiness_result.get("type") == "estimate_readiness":
            # The verified provider proposal remains hash-bound inside the task
            # proof, but its untrusted prices must never become public answer
            # text.  Present only the deterministic non-monetary gate summary.
            provider_output_verification = dict(public["verification"])
            text = deterministic_estimate_fallback_text(public_task)
            public["verification"] = {
                **deterministic_estimate_fallback_verification(public_task),
                "output_sha256": _sha256(text),
                "provider_output_sha256": provider_output_verification["output_sha256"],
                "provider_verifier_binding_sha256": provider_output_verification["binding_sha256"],
            }
        elif isinstance(readiness_result, dict) and readiness_result.get("type") == "deterministic_estimate":
            provider_output_verification = dict(public["verification"])
            text = deterministic_estimate_result_text(public_task)
            public["verification"] = {
                **deterministic_estimate_result_verification(public_task),
                "output_sha256": _sha256(text),
                "provider_output_sha256": provider_output_verification["output_sha256"],
                "provider_verifier_binding_sha256": provider_output_verification["binding_sha256"],
            }
        else:
            text = str(public["response"])
        message_id = _opaque_id("msg")
        payload = {
            **base,
            "status": "completed",
            "completed_at": int(_now()),
            "output": [{
                "id": message_id,
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{
                    "type": "output_text",
                    "text": text,
                    "annotations": [],
                }],
            }],
            "output_text": text,
            "verification": public["verification"],
            "citations": tool_execution.citations,
            "tool_calls": tool_execution.tool_calls,
        }
        if isinstance(public.get("task"), dict):
            payload["task"] = public["task"]
        work_summary = build_work_summary(
            response_status="completed",
            task=payload.get("task") or (
                body.task.model_dump(mode="json") if body.task is not None else None
            ),
            requested_tools=public_tools,
            tool_calls=tool_execution.tool_calls,
            citations=tool_execution.citations,
            verification=public["verification"],
        )
        payload["metadata"] = summary_metadata(base.get("metadata"), work_summary)
        payload["output"].append(reasoning_output_item(response_id, work_summary))
        payload["learning_tap"] = _record_public_learning_tap(
            session=session,
            body=body,
            response_id=response_id,
            response_status="completed",
            response_text=text,
            verification=public["verification"],
            provider_routing=provider_routing,
            tool_execution=tool_execution,
            task=payload.get("task"),
        )
        _STORE.finish_response(session["id"], response_id, payload, context, http_status=200)
        return payload, 200
    except HTTPException:
        raise
    except WebSearchError as exc:
        http_status = 422 if isinstance(exc, WebSearchPolicyError) else 503
        if isinstance(exc, WebSearchError):
            tool_execution = ResponseToolExecution(
                provider_tools=[],
                provider_instructions=None,
                tool_calls=[],
                evidence=[],
                citations=[],
                attempts=list(getattr(exc, "attempts", []) or []),
                formulalm_taps=[],
            )
        payload = {
            **base,
            "status": "failed",
            "completed_at": int(_now()),
            "error": {
                "type": "tool_error",
                "code": exc.code,
                "message": "Kolibri web search could not produce verified evidence",
            },
            "citations": [],
            "tool_calls": [],
        }
        if body.task is not None:
            payload["task"] = failed_vertical_result(body.task, exc.code)
        work_summary = build_work_summary(
            response_status="failed",
            task=payload.get("task") or (
                body.task.model_dump(mode="json") if body.task is not None else None
            ),
            requested_tools=public_tools,
            tool_calls=[],
            citations=[],
            verification=None,
        )
        payload["metadata"] = summary_metadata(base.get("metadata"), work_summary)
        payload["output"] = [reasoning_output_item(response_id, work_summary)]
        payload["learning_tap"] = _record_public_learning_tap(
            session=session,
            body=body,
            response_id=response_id,
            response_status="failed",
            response_text="",
            verification=None,
            provider_routing=provider_routing,
            tool_execution=tool_execution,
            task=payload.get("task"),
        )
        _STORE.finish_response(
            session["id"], response_id, payload, context, http_status=http_status,
        )
        return payload, http_status
    except Exception as exc:
        provider_routing = provider_routing or _provider_routing(
            getattr(exc, "technical", None)
        )
        if isinstance(exc, ProviderGatewayError):
            fallback = _complete_deterministic_estimate_fallback(
                session=session,
                body=body,
                response_id=response_id,
                base=base,
                context=context,
                provider_routing=provider_routing,
                tool_execution=tool_execution,
            )
            if fallback is not None:
                return fallback
        payload = {
            **base,
            "status": "failed",
            "completed_at": int(_now()),
            "error": {
                "type": "provider_unavailable",
                "code": "provider_unavailable",
                "message": "Kolibri could not produce a verified response",
            },
            "citations": [],
            "tool_calls": [],
        }
        if body.task is not None:
            payload["task"] = failed_vertical_result(body.task, "provider_unavailable")
        work_summary = build_work_summary(
            response_status="failed",
            task=payload.get("task") or (
                body.task.model_dump(mode="json") if body.task is not None else None
            ),
            requested_tools=public_tools,
            tool_calls=[],
            citations=[],
            verification=None,
        )
        payload["metadata"] = summary_metadata(base.get("metadata"), work_summary)
        payload["output"] = [reasoning_output_item(response_id, work_summary)]
        payload["learning_tap"] = _record_public_learning_tap(
            session=session,
            body=body,
            response_id=response_id,
            response_status="failed",
            response_text="",
            verification=None,
            provider_routing=provider_routing,
            tool_execution=tool_execution,
            task=payload.get("task"),
        )
        _STORE.finish_response(session["id"], response_id, payload, context, http_status=503)
        return payload, 503


def _sse(event_type: str, payload: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


async def _response_sse(
    initial: dict[str, Any],
    execute: Callable[[], Awaitable[tuple[dict[str, Any], int]]] | None,
):
    created = {**initial, "status": "in_progress", "output": [], "error": None}
    sequence = 0
    yield _sse("response.created", {
        "type": "response.created", "sequence_number": sequence, "response": created,
    })
    sequence += 1
    yield _sse("response.in_progress", {
        "type": "response.in_progress", "sequence_number": sequence, "response": created,
    })
    final, _ = await execute() if execute is not None else (initial, 200 if initial.get("status") == "completed" else 503)
    if final.get("status") != "completed":
        sequence += 1
        yield _sse("response.failed", {
            "type": "response.failed", "sequence_number": sequence, "response": final,
        })
        return

    message_index, item = next(
        (index, item)
        for index, item in enumerate(final["output"])
        if isinstance(item, dict) and item.get("type") == "message"
    )
    part = item["content"][0]
    sequence += 1
    yield _sse("response.output_item.added", {
        "type": "response.output_item.added", "sequence_number": sequence,
        "output_index": message_index, "item": {**item, "status": "in_progress", "content": []},
    })
    sequence += 1
    yield _sse("response.content_part.added", {
        "type": "response.content_part.added", "sequence_number": sequence,
        "item_id": item["id"], "output_index": message_index, "content_index": 0,
        "part": {"type": "output_text", "text": "", "annotations": []},
    })
    sequence += 1
    yield _sse("response.output_text.delta", {
        "type": "response.output_text.delta", "sequence_number": sequence,
        "item_id": item["id"], "output_index": message_index, "content_index": 0,
        "delta": part["text"],
    })
    sequence += 1
    yield _sse("response.output_text.done", {
        "type": "response.output_text.done", "sequence_number": sequence,
        "item_id": item["id"], "output_index": message_index, "content_index": 0,
        "text": part["text"],
    })
    sequence += 1
    yield _sse("response.content_part.done", {
        "type": "response.content_part.done", "sequence_number": sequence,
        "item_id": item["id"], "output_index": message_index, "content_index": 0, "part": part,
    })
    sequence += 1
    yield _sse("response.output_item.done", {
        "type": "response.output_item.done", "sequence_number": sequence,
        "output_index": message_index, "item": item,
    })

    reasoning = next((
        (index, output_item)
        for index, output_item in enumerate(final["output"])
        if isinstance(output_item, dict) and output_item.get("type") == "reasoning"
    ), None)
    if reasoning is not None:
        reasoning_index, reasoning_item = reasoning
        sequence += 1
        yield _sse("response.output_item.added", {
            "type": "response.output_item.added", "sequence_number": sequence,
            "output_index": reasoning_index,
            "item": {**reasoning_item, "summary": []},
        })
        for summary_index, summary_part in enumerate(reasoning_item.get("summary", [])):
            sequence += 1
            yield _sse("response.reasoning_summary_part.added", {
                "type": "response.reasoning_summary_part.added",
                "sequence_number": sequence,
                "item_id": reasoning_item["id"],
                "output_index": reasoning_index,
                "summary_index": summary_index,
                "part": {"type": "summary_text", "text": ""},
            })
            sequence += 1
            yield _sse("response.reasoning_summary_text.delta", {
                "type": "response.reasoning_summary_text.delta",
                "sequence_number": sequence,
                "item_id": reasoning_item["id"],
                "output_index": reasoning_index,
                "summary_index": summary_index,
                "delta": summary_part["text"],
            })
            sequence += 1
            yield _sse("response.reasoning_summary_text.done", {
                "type": "response.reasoning_summary_text.done",
                "sequence_number": sequence,
                "item_id": reasoning_item["id"],
                "output_index": reasoning_index,
                "summary_index": summary_index,
                "text": summary_part["text"],
            })
            sequence += 1
            yield _sse("response.reasoning_summary_part.done", {
                "type": "response.reasoning_summary_part.done",
                "sequence_number": sequence,
                "item_id": reasoning_item["id"],
                "output_index": reasoning_index,
                "summary_index": summary_index,
                "part": summary_part,
            })
        sequence += 1
        yield _sse("response.output_item.done", {
            "type": "response.output_item.done", "sequence_number": sequence,
            "output_index": reasoning_index, "item": reasoning_item,
        })
    sequence += 1
    yield _sse("response.completed", {
        "type": "response.completed", "sequence_number": sequence, "response": final,
    })


router = APIRouter(tags=["Kolibri Public Responses V1"])


@router.post("/v1/public/session")
def create_public_session(request: Request):
    origin = _required_origin(request)
    client = request.client.host if request.client else "unknown"
    if not _STORE.consume_rate(f"issue:{origin}:{client}", limit=20):
        raise HTTPException(status_code=429, detail="public_session_rate_limit_exceeded")
    ttl = _session_ttl_seconds()
    session, token = _STORE.issue(origin, ttl_seconds=ttl)
    payload = {
        "id": session["id"],
        "object": "public.session",
        "active": True,
        "expires_at": int(session["expires_at"]),
        "project": {
            "id": session["project_id"],
            "object": "project.ephemeral",
            "durable": False,
        },
        "model": "kolibri",
    }
    response = JSONResponse(payload, headers={"Cache-Control": "no-store"})
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=ttl,
        secure=origin.startswith("https://"),
        httponly=True,
        samesite="strict",
        path="/v1",
    )
    return response


@router.get("/v1/public/session")
def get_public_session(request: Request):
    # A cold browser start is discovery, not an authentication failure. Return
    # a non-cacheable inactive marker when no cookie was presented so the
    # Shell can issue its first session without producing a noisy expected 401
    # in DevTools. A syntactically valid but expired/revoked cookie still goes
    # through _require_session and remains a real 401 state transition.
    if not _session_cookie_candidates(request):
        return JSONResponse(
            {"object": "public.session", "active": False, "model": "kolibri"},
            headers={"Cache-Control": "no-store"},
        )
    session = _require_session(request, mutating=False)
    payload = {
        "id": session["id"],
        "object": "public.session",
        "active": True,
        "expires_at": int(session["expires_at"]),
        "project": {"id": session["project_id"], "object": "project.ephemeral", "durable": False},
        "model": "kolibri",
    }
    # This response is bound to an opaque browser cookie.  It must never be
    # reused from a browser/proxy cache after the backing session has expired
    # or after an immutable backend release has replaced the session store.
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@router.post("/v1/responses")
async def create_public_or_owner_response(body: ResponseCreate, request: Request):
    owner = _owner_principal(request)
    if owner is not None:
        owner_body = body.model_copy(update={"stream": False})
        response = _decorate_response_work_summary(
            await run_in_threadpool(create_owner_response, owner_body, request)
        )
        if not body.stream:
            return response
        return StreamingResponse(
            _response_sse(response, None),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
        )

    session = _require_session(request, mutating=True)
    if body.project_id or body.workstream_id:
        raise HTTPException(status_code=403, detail="public_session_durable_scope_forbidden")
    requested_tools, public_tools = _validate_public_tools(body.tools)
    if not _STORE.consume_rate(f"response:{session['id']}", limit=_response_rate_limit()):
        raise HTTPException(status_code=429, detail="public_session_rate_limit_exceeded")

    messages = _input_messages(body.input)
    if body.previous_response_id and _STORE.get_response(session["id"], body.previous_response_id) is None:
        raise HTTPException(status_code=404, detail="previous_response_not_found_in_session")
    idempotency_key = _request_key(body, request)
    response_id = _opaque_id("resp")
    initial = _response_shell(
        response_id,
        body,
        session["project_id"],
        status="in_progress",
        public_tools=public_tools,
    )
    existing, created, existing_status = _STORE.begin_response(
        session,
        response_id=response_id,
        idempotency_key=idempotency_key,
        request_sha256=_json_hash(_request_semantics(body)),
        payload=initial,
        context=messages,
    )
    if not created:
        if existing.get("status") == "in_progress":
            raise HTTPException(status_code=409, detail="idempotent_response_still_in_progress")
        if body.stream:
            return StreamingResponse(
                _response_sse(existing, None),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
            )
        return JSONResponse(existing, status_code=existing_status, headers={"Cache-Control": "no-store"})

    async def execute() -> tuple[dict[str, Any], int]:
        return await _complete_public_response(
            session,
            body,
            response_id,
            messages,
            requested_tools,
            public_tools,
        )

    if body.stream:
        return StreamingResponse(
            _response_sse(initial, execute),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
        )
    payload, http_status = await execute()
    return JSONResponse(payload, status_code=http_status, headers={"Cache-Control": "no-store"})


@router.get("/v1/responses")
def list_public_or_owner_responses(request: Request):
    if _owner_principal(request) is not None:
        result = list_owner_responses()
        return {
            **result,
            "data": [
                _decorate_response_work_summary(item)
                for item in result.get("data", [])
                if isinstance(item, dict)
            ],
        }
    session = _require_session(request, mutating=False)
    return {"object": "list", "data": _STORE.list_responses(session["id"]), "has_more": False}


@router.get("/v1/responses/{response_id}")
def get_public_or_owner_response(response_id: str, request: Request):
    if _owner_principal(request) is not None:
        return _decorate_response_work_summary(get_owner_response(response_id))
    session = _require_session(request, mutating=False)
    record = _STORE.get_response(session["id"], response_id)
    if record is None:
        raise HTTPException(status_code=404, detail="response_not_found")
    return record[0]


@router.get("/v1/responses/{response_id}/input_items")
def list_public_or_owner_response_input_items(
    response_id: str,
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    order: Literal["asc", "desc"] = "desc",
    after: str | None = None,
    include: list[str] | None = Query(default=None),
):
    if _owner_principal(request) is not None:
        return list_owner_response_input_items(
            response_id=response_id,
            limit=limit,
            order=order,
            after=after,
            include=include,
        )
    session = _require_session(request, mutating=False)
    input_items = _STORE.get_response_input(session["id"], response_id)
    payload = response_input_item_list(
        response_id,
        input_items,
        limit=limit,
        order=order,
        after=after,
    )
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@router.post("/v1/responses/{response_id}/cancel")
def cancel_public_or_owner_response(response_id: str, request: Request):
    if _owner_principal(request) is not None:
        return _decorate_response_work_summary(cancel_owner_response(response_id))
    session = _require_session(request, mutating=True)
    record = _STORE.get_response(session["id"], response_id)
    if record is None:
        raise HTTPException(status_code=404, detail="response_not_found")
    payload, context, _ = record
    if payload.get("status") in {"completed", "failed", "cancelled", "incomplete"}:
        return payload
    cancelled = {
        **payload,
        "status": "cancelled",
        "completed_at": int(_now()),
        "error": None,
    }
    return _STORE.finish_response(
        session["id"], response_id, cancelled, context, http_status=200,
    )
