from __future__ import annotations

import ipaddress
import re
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit

import httpx

from .core import (
    CoreError,
    CoreEvent,
    PublicPrincipal,
    PublicSession,
    PublicSessionIssue,
)


SESSION_CREDENTIAL = re.compile(r"^[A-Za-z0-9_-]{20,256}$")
CORE_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_.-]{1,99}$")
SAFE_EVENT_TYPES = {
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
SAFE_RESPONSE_KEYS = {
    "id",
    "object",
    "created_at",
    "completed_at",
    "status",
    "model",
    "project_id",
    "previous_response_id",
    "output",
    "output_text",
    "task",
    "error",
    "metadata",
    "last_sequence",
}
PRIVATE_KEY_MARKERS = {
    "analysis",
    "chain_of_thought",
    "credential",
    "internal_reasoning",
    "password",
    "private_reasoning",
    "prompt",
    "provider",
    "secret",
    "stderr",
    "technical",
    "token",
}


class HttpCoreClient:
    """Production-shaped HTTP adapter for the loopback Rust response core.

    The adapter owns no durable state and never logs request or response bodies.
    The public-session credential is sent only to the dedicated resolve RPC.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        _validate_client(client)
        self._client = client

    async def resolve_public_session(self, credential: str) -> PublicSession | None:
        if not SESSION_CREDENTIAL.fullmatch(credential):
            return None
        payload = await self._post(
            "/internal/v1/public-sessions/resolve",
            {"credential": credential},
            none_codes={"public_session_required_or_expired"},
        )
        return None if payload is None else _public_session(payload)

    async def create_public_session(self, origin: str) -> PublicSessionIssue:
        payload = await self._post(
            "/internal/v1/public-sessions",
            {"origin": origin},
        )
        if payload is None or not isinstance(payload.get("session"), dict):
            raise _protocol_error()
        credential = payload.get("credential")
        if not isinstance(credential, str) or not SESSION_CREDENTIAL.fullmatch(
            credential
        ):
            raise _protocol_error()
        return PublicSessionIssue(
            session=_public_session(payload["session"]),
            credential=credential,
        )

    async def create_response(
        self,
        principal: PublicPrincipal,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        request_sha256: str,
    ) -> dict[str, Any]:
        payload = await self._post(
            "/internal/v1/responses",
            {
                "principal": _principal_payload(principal),
                "request": request,
                "idempotency_key": idempotency_key,
                "request_sha256": request_sha256,
            },
        )
        if payload is None:
            raise _protocol_error()
        return _public_response(payload)

    async def get_response(
        self,
        principal: PublicPrincipal,
        response_id: str,
    ) -> dict[str, Any] | None:
        payload = await self._post(
            "/internal/v1/responses/get",
            {
                "principal": _principal_payload(principal),
                "response_id": response_id,
            },
            none_codes={"response_not_found"},
        )
        return None if payload is None else _public_response(payload)

    async def list_response_events(
        self,
        principal: PublicPrincipal,
        response_id: str,
        *,
        after: int,
        limit: int,
    ) -> Sequence[CoreEvent]:
        return await self._response_events(
            principal,
            response_id,
            after=after,
            limit=limit,
            wait_seconds=0.0,
        )

    async def wait_response_events(
        self,
        principal: PublicPrincipal,
        response_id: str,
        *,
        after: int,
        timeout_seconds: float,
    ) -> Sequence[CoreEvent]:
        if not 0.0 <= timeout_seconds <= 30.0:
            raise CoreError(
                "core_wait_timeout_invalid",
                "Core event wait timeout is invalid.",
                status_code=500,
            )
        return await self._response_events(
            principal,
            response_id,
            after=after,
            limit=200,
            wait_seconds=timeout_seconds,
        )

    async def cancel_response(
        self,
        principal: PublicPrincipal,
        response_id: str,
        *,
        idempotency_key: str,
        request_sha256: str,
    ) -> dict[str, Any] | None:
        payload = await self._post(
            "/internal/v1/responses/cancel",
            {
                "principal": _principal_payload(principal),
                "response_id": response_id,
                "idempotency_key": idempotency_key,
                "request_sha256": request_sha256,
            },
            none_codes={"response_not_found"},
        )
        return None if payload is None else _public_response(payload)

    async def _response_events(
        self,
        principal: PublicPrincipal,
        response_id: str,
        *,
        after: int,
        limit: int,
        wait_seconds: float,
    ) -> list[CoreEvent]:
        payload = await self._post(
            "/internal/v1/responses/events",
            {
                "principal": _principal_payload(principal),
                "response_id": response_id,
                "after": after,
                "limit": limit,
                "wait_seconds": wait_seconds,
            },
        )
        if payload is None or payload.get("response_id") != response_id:
            raise _protocol_error()
        data = payload.get("data")
        if not isinstance(data, list):
            raise _protocol_error()
        events: list[CoreEvent] = []
        last_sequence = after
        for item in data:
            if not isinstance(item, dict):
                raise _protocol_error()
            sequence = item.get("sequence")
            event_type = item.get("event_type")
            event_payload = item.get("payload")
            if (
                not isinstance(sequence, int)
                or isinstance(sequence, bool)
                or sequence <= last_sequence
                or event_type not in SAFE_EVENT_TYPES
                or not isinstance(event_payload, dict)
            ):
                raise _protocol_error()
            events.append(
                CoreEvent(
                    sequence=sequence,
                    event_type=event_type,
                    payload=_sanitize_mapping(event_payload),
                )
            )
            last_sequence = sequence
        return events

    async def _post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        none_codes: set[str] | None = None,
    ) -> dict[str, Any] | None:
        try:
            response = await self._client.post(path, json=payload)
        except httpx.ReadTimeout as exc:
            raise CoreError(
                "core_read_timeout",
                "The durable Core did not respond in time.",
                status_code=504,
                retryable=True,
            ) from exc
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            raise CoreError(
                "core_unavailable",
                "The durable Core is unavailable.",
                status_code=503,
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise CoreError(
                "core_transport_failed",
                "The durable Core transport failed.",
                status_code=502,
                retryable=True,
            ) from exc

        decoded = _json_object(response)
        if response.is_error:
            error = decoded.get("error")
            if not isinstance(error, dict):
                raise _protocol_error()
            code = error.get("code")
            if none_codes and isinstance(code, str) and code in none_codes:
                return None
            message = error.get("message")
            retryable = error.get("retryable", False)
            if (
                not isinstance(code, str)
                or not CORE_ERROR_CODE.fullmatch(code)
                or not isinstance(message, str)
            ):
                raise _protocol_error()
            raise CoreError(
                code,
                _safe_error_message(code),
                status_code=response.status_code,
                retryable=retryable if isinstance(retryable, bool) else False,
            )
        return decoded


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except (ValueError, TypeError) as exc:
        raise _protocol_error() from exc
    if not isinstance(payload, dict):
        raise _protocol_error()
    return payload


def _validate_client(client: httpx.AsyncClient) -> None:
    try:
        parsed = urlsplit(str(client.base_url))
        port = parsed.port
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError as exc:
        raise ValueError("an explicit loopback Core base URL is required") from exc
    if (
        parsed.scheme != "http"
        or port is None
        or not address.is_loopback
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or client.follow_redirects
    ):
        raise ValueError("an explicit loopback Core base URL is required")
    for name, value, maximum in [
        ("connect", client.timeout.connect, 5.0),
        ("read", client.timeout.read, 40.0),
    ]:
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not 0 < value <= maximum
        ):
            raise ValueError(f"Core {name} timeout must be finite and bounded")


def _public_session(payload: dict[str, Any]) -> PublicSession:
    session_id = payload.get("id")
    origin = payload.get("origin")
    expires_at = payload.get("expires_at")
    project_id = payload.get("current_project_id")
    if (
        not isinstance(session_id, str)
        or not isinstance(origin, str)
        or not isinstance(expires_at, (int, float))
        or isinstance(expires_at, bool)
        or (project_id is not None and not isinstance(project_id, str))
    ):
        raise _protocol_error()
    return PublicSession(
        id=session_id,
        origin=origin,
        expires_at=float(expires_at),
        current_project_id=project_id,
    )


def _principal_payload(principal: PublicPrincipal) -> dict[str, str]:
    return {
        "session_id": principal.session_id,
        "origin": principal.origin,
    }


def _public_response(payload: dict[str, Any]) -> dict[str, Any]:
    response_id = payload.get("id")
    status = payload.get("status")
    model = payload.get("model")
    if (
        not isinstance(response_id, str)
        or not isinstance(status, str)
        or model not in {None, "kolibri"}
    ):
        raise _protocol_error()
    public = {
        key: _sanitize_value(value)
        for key, value in payload.items()
        if key in SAFE_RESPONSE_KEYS
    }
    public.update(
        {"id": response_id, "object": "response", "model": "kolibri", "status": status}
    )
    return public


def _sanitize_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _sanitize_value(item)
        for key, item in value.items()
        if isinstance(key, str) and not _private_key(key)
    }


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _sanitize_mapping(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value


def _private_key(value: str) -> bool:
    normalized = value.lower().replace("-", "_")
    return any(marker in normalized for marker in PRIVATE_KEY_MARKERS)


def _protocol_error() -> CoreError:
    return CoreError(
        "core_protocol_invalid",
        "The durable Core returned an invalid response.",
        status_code=502,
        retryable=True,
    )


def _safe_error_message(code: str) -> str:
    messages = {
        "idempotency_conflict": "The idempotency key is bound to another request.",
        "public_session_required_or_expired": "Create a new public session.",
        "response_not_found": "Response not found for this public session.",
    }
    return messages.get(code, "The durable Core rejected the request.")
