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
import secrets
import sqlite3
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from capability_gateway import CapabilityRequestError, get_capability_gateway
from data_paths import DB_PATH
from estimate_artifacts import EstimateArtifactError, materialize_public_estimate_task
from execution_api import (
    ResponseCreate,
    cancel_response as cancel_owner_response,
    create_response as create_owner_response,
    get_response as get_owner_response,
    list_responses as list_owner_responses,
    require_execution_auth,
    sanitize_learning_value,
)
from public_chat_stream import verified_public_payload
from response_tool_gateway import ResponseToolExecution, execute_response_tools
from vertical_tasks import build_vertical_result, failed_vertical_result, prepare_vertical_task
from web_search_gateway import TOOL_ID as WEB_SEARCH_TOOL_ID
from web_search_gateway import WebSearchError, WebSearchPolicyError


COOKIE_NAME = "kolibri_public_session"
MAX_REQUEST_BYTES = 1024 * 1024
MAX_MESSAGES = 100
PUBLIC_TOOL_ALIASES = frozenset({
    WEB_SEARCH_TOOL_ID, "web_search", "web_search_preview", "search_web",
})


def _now() -> float:
    return time.time()


def _opaque_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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
                    payload, context_json, http_status, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 202, ?, ?)""",
                (
                    response_id, session["id"], session["project_id"], idempotency_hash,
                    request_sha256, json.dumps(payload, ensure_ascii=False, sort_keys=True),
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


def _require_session(request: Request, *, mutating: bool) -> dict[str, Any]:
    token = request.cookies.get(COOKIE_NAME, "")
    session = _STORE.resolve(token)
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
        "metadata": sanitize_learning_value(body.metadata),
        "project_id": project_id,
        "execution_mode": body.execution_mode,
    }


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
    try:
        tool_execution = ResponseToolExecution(
            provider_tools=requested_tools,
            provider_instructions=None,
            tool_calls=[],
            evidence=[],
            citations=[],
            attempts=[],
            formulalm_taps=[],
        )
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
        _STORE.finish_response(session["id"], response_id, payload, context, http_status=200)
        return payload, 200
    except HTTPException:
        raise
    except WebSearchError as exc:
        http_status = 422 if isinstance(exc, WebSearchPolicyError) else 503
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
        _STORE.finish_response(
            session["id"], response_id, payload, context, http_status=http_status,
        )
        return payload, http_status
    except Exception:
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

    item = final["output"][0]
    part = item["content"][0]
    sequence += 1
    yield _sse("response.output_item.added", {
        "type": "response.output_item.added", "sequence_number": sequence,
        "output_index": 0, "item": {**item, "status": "in_progress", "content": []},
    })
    sequence += 1
    yield _sse("response.content_part.added", {
        "type": "response.content_part.added", "sequence_number": sequence,
        "item_id": item["id"], "output_index": 0, "content_index": 0,
        "part": {"type": "output_text", "text": "", "annotations": []},
    })
    sequence += 1
    yield _sse("response.output_text.delta", {
        "type": "response.output_text.delta", "sequence_number": sequence,
        "item_id": item["id"], "output_index": 0, "content_index": 0,
        "delta": part["text"],
    })
    sequence += 1
    yield _sse("response.output_text.done", {
        "type": "response.output_text.done", "sequence_number": sequence,
        "item_id": item["id"], "output_index": 0, "content_index": 0,
        "text": part["text"],
    })
    sequence += 1
    yield _sse("response.content_part.done", {
        "type": "response.content_part.done", "sequence_number": sequence,
        "item_id": item["id"], "output_index": 0, "content_index": 0, "part": part,
    })
    sequence += 1
    yield _sse("response.output_item.done", {
        "type": "response.output_item.done", "sequence_number": sequence,
        "output_index": 0, "item": item,
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
    session = _require_session(request, mutating=False)
    payload = {
        "id": session["id"],
        "object": "public.session",
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
        response = await run_in_threadpool(create_owner_response, owner_body, request)
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
        return list_owner_responses()
    session = _require_session(request, mutating=False)
    return {"object": "list", "data": _STORE.list_responses(session["id"]), "has_more": False}


@router.get("/v1/responses/{response_id}")
def get_public_or_owner_response(response_id: str, request: Request):
    if _owner_principal(request) is not None:
        return get_owner_response(response_id)
    session = _require_session(request, mutating=False)
    record = _STORE.get_response(session["id"], response_id)
    if record is None:
        raise HTTPException(status_code=404, detail="response_not_found")
    return record[0]


@router.post("/v1/responses/{response_id}/cancel")
def cancel_public_or_owner_response(response_id: str, request: Request):
    if _owner_principal(request) is not None:
        return cancel_owner_response(response_id)
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
