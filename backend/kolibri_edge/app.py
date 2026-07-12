from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any, AsyncContextManager
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .contracts import ResponseCreate, validate_idempotency_key
from .core import CoreClient, CoreError, CoreEvent, PublicPrincipal, PublicSession


TERMINAL_RESPONSE_STATES = {"completed", "failed", "cancelled", "incomplete"}
PUBLIC_RESPONSE_STATES = {
    "queued",
    "planning",
    "running",
    "verifying",
    "completed",
    "failed",
    "cancelled",
    "incomplete",
}
PUBLIC_EVENT_TYPES = {
    "response.created",
    "response.status.updated",
    "response.output_text.delta",
    "response.reasoning_summary_text.delta",
    "response.tool.started",
    "response.tool.completed",
    "response.work_summary.updated",
    "response.source.added",
    "response.artifact.ready",
    "response.approval.required",
    "response.verification.updated",
    "response.completed",
    "response.failed",
    "response.cancelled",
    "response.incomplete",
}
RESPONSE_ID = re.compile(r"^resp_[A-Za-z0-9._:-]{1,150}$")
ARTIFACT_ID = re.compile(r"^artifact_[A-Za-z0-9._:-]{1,150}$")
SHA256_HEX = re.compile(r"^[a-f0-9]{64}$")
SESSION_CREDENTIAL = re.compile(r"^[A-Za-z0-9_-]{20,256}$")
UNSAFE_REASONING_SUMMARY = re.compile(
    r"(?:\bsk-[A-Za-z0-9_-]{8,}\b|"
    r"\b(?:authorization|api[-_ ]?key|password|secret|token)\s*[:=]|"
    r"<\/?analysis>|\bchain[-_ ]?of[-_ ]?thought\b|"
    r"\b(?:hidden|private|internal)\s+reasoning\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EdgeSettings:
    allowed_origins: tuple[str, ...]
    cookie_name: str = "kolibri_session"
    cookie_path: str = "/v1"
    force_secure_cookie: bool = False
    event_batch_size: int = 200
    sse_wait_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not self.allowed_origins:
            raise ValueError("at least one exact public origin is required")
        normalized = tuple(_normalize_origin(origin) for origin in self.allowed_origins)
        if len(set(normalized)) != len(normalized):
            raise ValueError("duplicate public origin")
        if self.event_batch_size < 1 or self.event_batch_size > 500:
            raise ValueError("event_batch_size must be between 1 and 500")
        if self.sse_wait_seconds <= 0 or self.sse_wait_seconds > 30:
            raise ValueError("sse_wait_seconds must be between 0 and 30")
        object.__setattr__(self, "allowed_origins", normalized)


class EdgeError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        error_type: str = "request_error",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.error_type = error_type
        self.retryable = retryable


def _normalize_origin(value: str) -> str:
    raw = str(value or "").strip()
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid origin") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid origin")
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    default_port = 80 if parsed.scheme == "http" else 443
    authority = host if port in {None, default_port} else f"{host}:{port}"
    return f"{parsed.scheme}://{authority}"


def _error_payload(
    *,
    error_type: str,
    code: str,
    message: str,
    retryable: bool,
) -> dict[str, Any]:
    return {
        "error": {
            "type": error_type,
            "code": code,
            "message": message,
            "retryable": retryable,
        }
    }


def _json_error(error: EdgeError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content=_error_payload(
            error_type=error.error_type,
            code=error.code,
            message=error.message,
            retryable=error.retryable,
        ),
        headers={"Cache-Control": "no-store"},
    )


def _request_origin(request: Request, settings: EdgeSettings, *, required: bool) -> str | None:
    raw = request.headers.get("Origin")
    if not raw:
        if required:
            raise EdgeError(403, "origin_required", "An exact Origin header is required.")
        return None
    try:
        origin = _normalize_origin(raw)
    except ValueError as exc:
        raise EdgeError(403, "origin_not_allowed", "The request Origin is not allowed.") from exc
    if origin not in settings.allowed_origins:
        raise EdgeError(403, "origin_not_allowed", "The request Origin is not allowed.")
    return origin


def _validate_session(session: PublicSession) -> PublicSession:
    if not session.id or session.expires_at <= time.time():
        raise EdgeError(
            401,
            "public_session_required_or_expired",
            "Create a new public session.",
        )
    try:
        _normalize_origin(session.origin)
    except ValueError as exc:
        raise EdgeError(502, "core_session_invalid", "Core returned an invalid session.") from exc
    return session


def _session_payload(session: PublicSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "object": "public.session",
        "active": True,
        "origin": session.origin,
        "expires_at": int(session.expires_at),
        "current_project_id": session.current_project_id,
        "model": "kolibri",
    }


def _canonical_request_hash(method: str, path: str, body: dict[str, Any]) -> str:
    envelope = {"method": method.upper(), "path": path, "body": body}
    encoded = json.dumps(
        envelope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _idempotency_key(value: str | None) -> str:
    try:
        return validate_idempotency_key(value)
    except ValueError as exc:
        code = str(exc)
        message = (
            "Idempotency-Key is required for this mutation."
            if code == "idempotency_key_required"
            else "Idempotency-Key has an invalid format."
        )
        raise EdgeError(400, code, message) from exc


def _response_id(value: str) -> str:
    if not RESPONSE_ID.fullmatch(value):
        raise EdgeError(400, "invalid_response_id", "Response id is invalid.")
    return value


def _public_response(value: dict[str, Any], *, expected_id: str | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EdgeError(502, "core_response_invalid", "Core returned an invalid response.")
    response_id = str(value.get("id") or "")
    if not RESPONSE_ID.fullmatch(response_id) or (expected_id and response_id != expected_id):
        raise EdgeError(502, "core_response_invalid", "Core returned an invalid response id.")
    status = str(value.get("status") or "")
    if status not in PUBLIC_RESPONSE_STATES:
        raise EdgeError(502, "core_response_invalid", "Core returned an invalid response state.")
    allowed = {
        "id",
        "object",
        "created_at",
        "completed_at",
        "status",
        "project_id",
        "previous_response_id",
        "output",
        "output_text",
        "task",
        "error",
        "metadata",
        "last_sequence",
    }
    public = {key: value[key] for key in allowed if key in value}
    public.update({"id": response_id, "object": "response", "model": "kolibri", "status": status})
    return public


def _public_event(event: CoreEvent, *, expected_response_id: str) -> tuple[int, str, dict[str, Any]]:
    if event.sequence < 1 or event.event_type not in PUBLIC_EVENT_TYPES:
        raise EdgeError(502, "core_event_invalid", "Core returned an invalid response event.")
    raw_payload = dict(event.payload or {})
    if "analysis" in event.event_type or "chain_of_thought" in event.event_type:
        raise EdgeError(502, "core_event_invalid", "Core returned a private event type.")
    payload: dict[str, Any] = {
        "type": event.event_type,
        "sequence": event.sequence,
    }
    event_response_id = raw_payload.get("id")
    if event_response_id is not None:
        if str(event_response_id) != expected_response_id:
            raise EdgeError(502, "core_event_invalid", "Core returned an event for another response.")
        payload["id"] = expected_response_id
    response = raw_payload.get("response")
    if isinstance(response, dict):
        payload["response"] = _public_response(response, expected_id=expected_response_id)
    if event.event_type in {
        "response.output_text.delta",
        "response.reasoning_summary_text.delta",
    }:
        delta = str(raw_payload.get("delta") or "")
        if not delta:
            raise EdgeError(502, "core_event_invalid", "Core returned an empty text event.")
        if event.event_type == "response.reasoning_summary_text.delta":
            if len(delta) > 1_000 or UNSAFE_REASONING_SUMMARY.search(delta):
                raise EdgeError(502, "core_event_invalid", "Core returned an unsafe reasoning summary.")
        payload["delta"] = delta[:50_000]
    elif event.event_type == "response.status.updated":
        for key in ("status", "stage"):
            if raw_payload.get(key) is not None:
                payload[key] = str(raw_payload[key])[:120]
    elif event.event_type == "response.work_summary.updated":
        if isinstance(raw_payload.get("summary"), dict):
            payload["summary"] = raw_payload["summary"]
        elif raw_payload.get("stage") is not None:
            payload["stage"] = str(raw_payload["stage"])[:180]
    elif event.event_type in {"response.tool.started", "response.tool.completed"}:
        for key in ("tool_call_id", "tool", "name", "status", "summary"):
            if raw_payload.get(key) is not None:
                payload[key] = str(raw_payload[key])[:300]
    elif event.event_type == "response.artifact.ready":
        artifact = raw_payload.get("artifact")
        if not isinstance(artifact, dict):
            raise EdgeError(502, "core_event_invalid", "Core returned an invalid artifact event.")
        artifact_id = str(artifact.get("id") or "")
        name = str(artifact.get("name") or "")
        kind = str(artifact.get("kind") or "")
        status = str(artifact.get("status") or "")
        media_type = str(artifact.get("media_type") or "")
        content_sha256 = str(artifact.get("content_sha256") or "")
        evidence_sha256 = str(artifact.get("evidence_binding_sha256") or "")
        locator = str(artifact.get("locator") or "")
        size_bytes = artifact.get("size_bytes")
        if (
            not ARTIFACT_ID.fullmatch(artifact_id)
            or not name.strip()
            or len(name) > 300
            or not kind.strip()
            or status not in {"ready", "verified"}
            or "/" not in media_type
            or isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or size_bytes < 1
            or not SHA256_HEX.fullmatch(content_sha256)
            or not SHA256_HEX.fullmatch(evidence_sha256)
            or artifact.get("immutable") is not True
            or not locator.startswith(f"/v1/artifacts/{artifact_id}/")
        ):
            raise EdgeError(
                502,
                "core_event_invalid",
                "Core returned an artifact without verified immutable bytes.",
            )
        artifact_keys = {
            "id",
            "object",
            "kind",
            "name",
            "status",
            "media_type",
            "size_bytes",
            "content_sha256",
            "evidence_binding_sha256",
            "locator",
            "immutable",
        }
        payload["artifact"] = {
            key: artifact[key] for key in artifact_keys if key in artifact
        }
    elif event.event_type == "response.source.added":
        source = raw_payload.get("source")
        if not isinstance(source, dict):
            raise EdgeError(502, "core_event_invalid", "Core returned an invalid source event.")
        source_keys = {"id", "title", "url", "domain", "published_at", "accessed_at"}
        payload["source"] = {key: source[key] for key in source_keys if key in source}
    elif event.event_type == "response.approval.required":
        approval = raw_payload.get("approval")
        if not isinstance(approval, dict):
            raise EdgeError(502, "core_event_invalid", "Core returned an invalid approval event.")
        approval_keys = {"id", "class", "summary", "expires_at"}
        payload["approval"] = {
            key: approval[key] for key in approval_keys if key in approval
        }
    elif event.event_type == "response.verification.updated":
        verification = raw_payload.get("verification")
        if not isinstance(verification, dict):
            raise EdgeError(
                502,
                "core_event_invalid",
                "Core returned an invalid verification event.",
            )
        verification_keys = {"status", "verdict", "summary", "evidence_sha256"}
        payload["verification"] = {
            key: verification[key] for key in verification_keys if key in verification
        }
    return event.sequence, event.event_type, payload


def _sse(sequence: int, event_type: str, payload: dict[str, Any]) -> str:
    return (
        f"id: {sequence}\n"
        f"event: {event_type}\n"
        f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


def _resume_cursor(starting_after: int, last_event_id: str | None) -> int:
    cursor = max(0, starting_after)
    if last_event_id is None or not last_event_id.strip():
        return cursor
    if not last_event_id.isdigit():
        raise EdgeError(400, "invalid_event_cursor", "Last-Event-ID must be a non-negative integer.")
    parsed = int(last_event_id)
    if parsed > 2**63 - 1:
        raise EdgeError(400, "invalid_event_cursor", "Last-Event-ID is too large.")
    return max(cursor, parsed)


def create_app(
    *,
    core: CoreClient,
    settings: EdgeSettings,
    lifespan: Callable[[FastAPI], AsyncContextManager[None]] | None = None,
) -> FastAPI:
    """Create the stateless edge application around an authoritative Core client."""

    app = FastAPI(title="Kolibri Edge Gateway", version="0.1.0", lifespan=lifespan)
    app.state.core = core
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Idempotency-Key", "Last-Event-ID"],
    )

    @app.exception_handler(EdgeError)
    async def edge_error_handler(_request: Request, error: EdgeError) -> JSONResponse:
        return _json_error(error)

    @app.exception_handler(CoreError)
    async def core_error_handler(_request: Request, error: CoreError) -> JSONResponse:
        return _json_error(
            EdgeError(
                error.status_code,
                error.code,
                error.message,
                error_type="core_error",
                retryable=error.retryable,
            )
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        return _json_error(
            EdgeError(422, "request_validation_failed", "The request body is invalid.")
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        _request: Request,
        error: StarletteHTTPException,
    ) -> JSONResponse:
        code = "route_not_found" if error.status_code == 404 else "method_not_allowed"
        message = "API route not found." if error.status_code == 404 else "HTTP method is not allowed."
        if error.status_code not in {404, 405}:
            code = "http_error"
            message = "The request could not be completed."
        return _json_error(EdgeError(error.status_code, code, message))

    @app.exception_handler(Exception)
    async def unexpected_error_handler(
        _request: Request,
        _error: Exception,
    ) -> JSONResponse:
        return _json_error(
            EdgeError(
                500,
                "edge_internal_error",
                "The edge gateway could not complete the request.",
                error_type="internal_error",
                retryable=True,
            )
        )

    async def principal(request: Request, *, mutating: bool) -> PublicPrincipal:
        credential = request.cookies.get(settings.cookie_name)
        if not credential or not SESSION_CREDENTIAL.fullmatch(credential):
            raise EdgeError(
                401,
                "public_session_required_or_expired",
                "Create a public session first.",
            )
        session = await core.resolve_public_session(credential)
        if session is None:
            raise EdgeError(
                401,
                "public_session_required_or_expired",
                "Create a public session first.",
            )
        session = _validate_session(session)
        origin = _request_origin(request, settings, required=mutating)
        if origin is not None and origin != _normalize_origin(session.origin):
            raise EdgeError(403, "session_origin_mismatch", "Session is bound to another Origin.")
        return PublicPrincipal(session_id=session.id, origin=session.origin)

    async def event_stream(
        public_principal: PublicPrincipal,
        response_id: str,
        *,
        after: int,
    ) -> AsyncIterator[str]:
        cursor = after
        while True:
            events = await core.list_response_events(
                public_principal,
                response_id,
                after=cursor,
                limit=settings.event_batch_size,
            )
            terminal_seen = False
            for raw_event in events:
                sequence, event_type, payload = _public_event(
                    raw_event,
                    expected_response_id=response_id,
                )
                if sequence <= cursor:
                    continue
                cursor = sequence
                yield _sse(sequence, event_type, payload)
                terminal_seen = event_type in {
                    "response.completed",
                    "response.failed",
                    "response.cancelled",
                    "response.incomplete",
                }
            if terminal_seen:
                return
            current = await core.get_response(public_principal, response_id)
            if current is None:
                return
            public = _public_response(current, expected_id=response_id)
            if public["status"] in TERMINAL_RESPONSE_STATES:
                # Core owns the terminal event.  Never fabricate one at the edge.
                return
            started = time.monotonic()
            waited = await core.wait_response_events(
                public_principal,
                response_id,
                after=cursor,
                timeout_seconds=settings.sse_wait_seconds,
            )
            if waited:
                # The next iteration applies one ordering and validation path.
                continue
            elapsed = time.monotonic() - started
            if elapsed < 0.01:
                await asyncio.sleep(0.01)
            yield ": keep-alive\n\n"

    def sse_response(iterator: AsyncIterator[str]) -> StreamingResponse:
        return StreamingResponse(
            iterator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-store",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "kolibri-edge",
            "authority": "injected-core",
            "model": "kolibri",
        }

    @app.get("/v1/models")
    async def models() -> dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {
                    "id": "kolibri",
                    "object": "model",
                    "created": 0,
                    "owned_by": "kolibri",
                }
            ],
        }

    @app.post("/v1/shell/bootstrap")
    @app.post("/v1/public/session")
    async def create_public_session(request: Request) -> JSONResponse:
        origin = _request_origin(request, settings, required=True)
        assert origin is not None
        credential = request.cookies.get(settings.cookie_name)
        current = (
            await core.resolve_public_session(credential)
            if credential and SESSION_CREDENTIAL.fullmatch(credential)
            else None
        )
        if current is not None:
            current = _validate_session(current)
            if _normalize_origin(current.origin) != origin:
                raise EdgeError(403, "session_origin_mismatch", "Session is bound to another Origin.")
            return JSONResponse(
                _session_payload(current),
                headers={"Cache-Control": "no-store"},
            )
        issue = await core.create_public_session(origin)
        session = _validate_session(issue.session)
        if _normalize_origin(session.origin) != origin:
            raise EdgeError(502, "core_session_invalid", "Core returned a session for another Origin.")
        if not SESSION_CREDENTIAL.fullmatch(issue.credential):
            raise EdgeError(502, "core_session_invalid", "Core returned an invalid session credential.")
        max_age = max(1, math.floor(session.expires_at - time.time()))
        response = JSONResponse(
            _session_payload(session),
            headers={"Cache-Control": "no-store"},
        )
        response.set_cookie(
            settings.cookie_name,
            issue.credential,
            max_age=max_age,
            secure=settings.force_secure_cookie or origin.startswith("https://"),
            httponly=True,
            samesite="strict",
            path=settings.cookie_path,
        )
        return response

    @app.get("/v1/public/session")
    async def get_public_session(request: Request) -> JSONResponse:
        credential = request.cookies.get(settings.cookie_name)
        if not credential:
            return JSONResponse(
                {"object": "public.session", "active": False, "model": "kolibri"},
                headers={"Cache-Control": "no-store"},
            )
        if not SESSION_CREDENTIAL.fullmatch(credential):
            raise EdgeError(
                401,
                "public_session_required_or_expired",
                "Create a new public session.",
            )
        session = await core.resolve_public_session(credential)
        if session is None:
            raise EdgeError(
                401,
                "public_session_required_or_expired",
                "Create a new public session.",
            )
        session = _validate_session(session)
        origin = _request_origin(request, settings, required=False)
        if origin is not None and origin != _normalize_origin(session.origin):
            raise EdgeError(403, "session_origin_mismatch", "Session is bound to another Origin.")
        return JSONResponse(_session_payload(session), headers={"Cache-Control": "no-store"})

    @app.post("/v1/responses")
    async def create_response(
        body: ResponseCreate,
        request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        public_principal = await principal(request, mutating=True)
        key = _idempotency_key(idempotency_key)
        request_body = body.model_dump(mode="json", exclude_none=True)
        request_hash = _canonical_request_hash("POST", "/v1/responses", request_body)
        created = await core.create_response(
            public_principal,
            request_body,
            idempotency_key=key,
            request_sha256=request_hash,
        )
        response = _public_response(created)
        if body.stream:
            return sse_response(
                event_stream(public_principal, response["id"], after=0)
            )
        status_code = 200 if response["status"] in TERMINAL_RESPONSE_STATES else 202
        return JSONResponse(response, status_code=status_code, headers={"Cache-Control": "no-store"})

    @app.get("/v1/responses/{response_id}")
    async def get_response(
        response_id: str,
        request: Request,
        stream: bool = False,
        starting_after: int = Query(default=0, ge=0),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ):
        response_id = _response_id(response_id)
        public_principal = await principal(request, mutating=False)
        current = await core.get_response(public_principal, response_id)
        if current is None:
            raise EdgeError(404, "response_not_found", "Response was not found in this session.")
        response = _public_response(current, expected_id=response_id)
        if stream:
            cursor = _resume_cursor(starting_after, last_event_id)
            return sse_response(event_stream(public_principal, response_id, after=cursor))
        return JSONResponse(response, headers={"Cache-Control": "no-store"})

    @app.get("/v1/responses/{response_id}/events")
    async def list_response_events(
        response_id: str,
        request: Request,
        starting_after: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> JSONResponse:
        response_id = _response_id(response_id)
        public_principal = await principal(request, mutating=False)
        current = await core.get_response(public_principal, response_id)
        if current is None:
            raise EdgeError(404, "response_not_found", "Response was not found in this session.")
        raw_events = await core.list_response_events(
            public_principal,
            response_id,
            after=starting_after,
            limit=limit,
        )
        data = []
        for raw_event in raw_events:
            sequence, event_type, payload = _public_event(
                raw_event,
                expected_response_id=response_id,
            )
            if sequence <= starting_after:
                continue
            data.append({"sequence": sequence, "type": event_type, "data": payload})
        return JSONResponse(
            {"object": "list", "response_id": response_id, "data": data},
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/v1/responses/{response_id}/cancel")
    async def cancel_response(
        response_id: str,
        request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> JSONResponse:
        response_id = _response_id(response_id)
        public_principal = await principal(request, mutating=True)
        key = _idempotency_key(idempotency_key)
        path = f"/v1/responses/{response_id}/cancel"
        request_hash = _canonical_request_hash("POST", path, {})
        cancelled = await core.cancel_response(
            public_principal,
            response_id,
            idempotency_key=key,
            request_sha256=request_hash,
        )
        if cancelled is None:
            raise EdgeError(404, "response_not_found", "Response was not found in this session.")
        response = _public_response(cancelled, expected_id=response_id)
        return JSONResponse(response, headers={"Cache-Control": "no-store"})

    return app
