"""Truthful, allowlisted OpenAI wire-compatibility discovery.

Kolibri implements a deliberately small subset of the OpenAI HTTP surface.
This module is the single registry for that subset and owns the explicit
unavailable boundary for Realtime.  It never forwards arbitrary ``/v1`` paths
and never treats organization or administration routes as proxy candidates.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse


COMPATIBILITY_SCHEMA_VERSION = "kolibri.openai-compatibility.v1"
OPENAI_OPENAPI_VERSION = "2.3.0"
OPENAI_REFERENCE_DATE = "2026-07-11"


OPENAI_COMPATIBILITY_OPERATIONS: tuple[dict[str, Any], ...] = (
    {
        "path": "/v1/models",
        "method": "GET",
        "operation": "models.list",
        "available": True,
        "conformance": "supported_subset",
        "auth": ["public"],
        "limitations": ["Only the policy-routed `kolibri` model is exposed."],
    },
    {
        "path": "/v1/models/{model}",
        "method": "GET",
        "operation": "models.retrieve",
        "available": True,
        "conformance": "supported_subset",
        "auth": ["owner_bearer"],
        "limitations": ["Only model id `kolibri` can be retrieved."],
    },
    {
        "path": "/v1/chat/completions",
        "method": "POST",
        "operation": "chat.completions.create",
        "available": True,
        "conformance": "supported_subset",
        "auth": ["owner_bearer"],
        "features": ["json", "sse"],
        "limitations": [
            "Only model `kolibri` is accepted.",
            "Provider selection remains server policy and is not client-controlled.",
            "SSE compatibility chunks are emitted after the current synchronous execution path completes; live token streaming is not claimed.",
        ],
    },
    {
        "path": "/v1/responses",
        "method": "POST",
        "operation": "responses.create",
        "available": True,
        "conformance": "supported_subset",
        "auth": ["owner_bearer", "public_session_cookie"],
        "features": [
            "json",
            "sse",
            "previous_response_id",
            "scoped_tools",
            "reasoning_summary_opt_in",
            "public_session_background_execution",
            "public_session_resumable_sse_sequence_number",
        ],
        "limitations": [
            "Only model `kolibri` is accepted.",
            "The accepted tool set is the Kolibri capability allowlist.",
            "Durable owner creation returns HTTP 201; public-session creation returns HTTP 200.",
            "Raw reasoning tokens are never exposed; only a provider-authored reasoning summary is streamed when explicitly requested.",
            "Durable background execution and cursor-based stream resumption are currently implemented for public-session responses; owner bearer execution remains synchronous.",
        ],
    },
    {
        "path": "/v1/responses",
        "method": "GET",
        "operation": "kolibri.responses.list",
        "available": True,
        "conformance": "kolibri_extension",
        "auth": ["owner_bearer", "public_session_cookie"],
        "limitations": [
            "OpenAI OpenAPI 2.3.0 defines response creation at this path, not response listing."
        ],
    },
    {
        "path": "/v1/responses/{response_id}",
        "method": "GET",
        "operation": "responses.retrieve",
        "available": True,
        "conformance": "supported_subset",
        "auth": ["owner_bearer", "public_session_cookie"],
        "features": [
            "json",
            "public_session_stream_replay",
            "public_session_starting_after_sequence_number",
        ],
        "limitations": [
            "Retrieval is scoped to the authenticated owner or public session.",
            "Live cursor resumption is durable only for public-session responses.",
        ],
    },
    {
        "path": "/v1/responses/{response_id}/cancel",
        "method": "POST",
        "operation": "responses.cancel",
        "available": True,
        "conformance": "supported_subset",
        "auth": ["owner_bearer", "public_session_cookie"],
        "limitations": [
            "Terminal Kolibri responses are returned unchanged; no background execution is invented."
        ],
    },
    {
        "path": "/v1/responses/{response_id}/input_items",
        "method": "GET",
        "operation": "responses.input_items.list",
        "available": True,
        "conformance": "supported_subset",
        "auth": ["owner_bearer", "public_session_cookie"],
        "features": ["limit_1_100", "order_asc_desc", "after_cursor"],
        "limitations": [
            "Only input items durably recorded by Kolibri are returned.",
            "Optional `include` fields are not synthesized when no such data was recorded.",
        ],
    },
    {
        "path": "/v1/realtime",
        "method": "GET",
        "operation": "kolibri.realtime.probe",
        "available": False,
        "conformance": "kolibri_boundary",
        "auth": ["public"],
        "limitations": ["Returns HTTP 501 and never creates a Realtime session."],
        "error_code": "realtime_unavailable",
    },
    {
        "path": "/v1/realtime",
        "method": "POST",
        "operation": "kolibri.realtime.http_boundary",
        "available": False,
        "conformance": "kolibri_boundary",
        "auth": ["public"],
        "limitations": ["Returns HTTP 501 and never creates a Realtime session."],
        "error_code": "realtime_unavailable",
    },
    {
        "path": "/v1/realtime/client_secrets",
        "method": "POST",
        "operation": "realtime.client_secrets.create",
        "available": False,
        "conformance": "unavailable",
        "auth": [],
        "limitations": ["No ephemeral Realtime credentials are issued."],
        "error_code": "realtime_unavailable",
    },
    {
        "path": "/v1/realtime/sessions",
        "method": "POST",
        "operation": "realtime.sessions.create_legacy",
        "available": False,
        "conformance": "unavailable",
        "auth": [],
        "limitations": ["The legacy Realtime session bootstrap is not deployed."],
        "error_code": "realtime_unavailable",
    },
    {
        "path": "/v1/realtime/transcription_sessions",
        "method": "POST",
        "operation": "realtime.transcription_sessions.create",
        "available": False,
        "conformance": "unavailable",
        "auth": [],
        "limitations": ["Realtime transcription is not deployed."],
        "error_code": "realtime_unavailable",
    },
    {
        "path": "/v1/realtime/calls",
        "method": "POST",
        "operation": "realtime.calls.create",
        "available": False,
        "conformance": "unavailable",
        "auth": [],
        "limitations": ["WebRTC call establishment is not deployed."],
        "error_code": "realtime_unavailable",
    },
    {
        "path": "/v1/realtime/translations/client_secrets",
        "method": "POST",
        "operation": "realtime.translations.client_secrets.create",
        "available": False,
        "conformance": "unavailable",
        "auth": [],
        "limitations": ["Realtime translation is not deployed."],
        "error_code": "realtime_unavailable",
    },
    {
        "path": "/v1/realtime",
        "method": "WEBSOCKET",
        "operation": "realtime.connect",
        "available": False,
        "conformance": "unavailable",
        "auth": [],
        "limitations": [
            "No Kolibri Realtime session backend, audio transport, or event engine is deployed."
        ],
        "error_code": "realtime_unavailable",
    },
)


router = APIRouter(tags=["Kolibri OpenAI Compatibility"])


def compatibility_registry() -> dict[str, Any]:
    """Return a defensive copy so request handlers cannot mutate policy."""

    return {
        "object": "kolibri.openai_compatibility",
        "schema_version": COMPATIBILITY_SCHEMA_VERSION,
        "reference": {
            "openapi_version": OPENAI_OPENAPI_VERSION,
            "verified_on": OPENAI_REFERENCE_DATE,
            "input_items": (
                "https://developers.openai.com/api/reference/resources/responses/"
                "subresources/input_items/methods/list"
            ),
            "reasoning_summaries": (
                "https://developers.openai.com/api/docs/guides/reasoning"
                "#reasoning-summaries"
            ),
            "background_streaming": (
                "https://developers.openai.com/api/docs/guides/background"
                "#streaming-a-background-response"
            ),
            "realtime": "https://developers.openai.com/api/docs/guides/realtime",
        },
        "routing_policy": {
            "mode": "explicit_allowlist",
            "wildcard_v1_proxy": False,
            "organization_proxy": False,
            "admin_proxy": False,
            "proxied_paths": [],
            "explicitly_not_proxied": ["/v1/organization/*", "/v1/admin/*"],
            "unlisted_openai_operations": "unavailable_404",
        },
        "operations": copy.deepcopy(list(OPENAI_COMPATIBILITY_OPERATIONS)),
    }


@router.get("/v1/kolibri/openai-compatibility")
def get_openai_compatibility() -> JSONResponse:
    return JSONResponse(
        compatibility_registry(),
        headers={"Cache-Control": "no-store"},
    )


def realtime_unavailable_error(
    *,
    surface: str = "/v1/realtime",
    transport: str = "websocket",
) -> dict[str, Any]:
    return {
        "error": {
            "message": "Kolibri Realtime is unavailable because no Realtime session backend is deployed.",
            "type": "not_implemented_error",
            "param": None,
            "code": "realtime_unavailable",
        },
        "available": False,
        "surface": surface,
        "transport": transport,
        "retryable": False,
        "supported_alternative": {
            "path": "/v1/responses",
            "features": ["text_sse", "background", "resumable_sequence_number"],
        },
        "discovery": "/v1/kolibri/openai-compatibility",
    }


@router.get("/v1/realtime")
def get_realtime_boundary() -> JSONResponse:
    """Truthful HTTP response for clients that probe the WebSocket path."""

    return JSONResponse(
        realtime_unavailable_error(),
        status_code=501,
        headers={"Cache-Control": "no-store"},
    )


def _realtime_rest_boundary(path: str) -> JSONResponse:
    """Return one stable JSON error instead of route-specific 404/405/422."""

    return JSONResponse(
        realtime_unavailable_error(surface=path, transport="http"),
        status_code=501,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/v1/realtime")
async def post_realtime_boundary(request: Request) -> JSONResponse:
    del request
    return _realtime_rest_boundary("/v1/realtime")


@router.post("/v1/realtime/client_secrets")
async def create_realtime_client_secret_boundary(request: Request) -> JSONResponse:
    del request
    return _realtime_rest_boundary("/v1/realtime/client_secrets")


@router.post("/v1/realtime/sessions")
async def create_realtime_session_boundary(request: Request) -> JSONResponse:
    del request
    return _realtime_rest_boundary("/v1/realtime/sessions")


@router.post("/v1/realtime/transcription_sessions")
async def create_realtime_transcription_session_boundary(
    request: Request,
) -> JSONResponse:
    del request
    return _realtime_rest_boundary("/v1/realtime/transcription_sessions")


@router.post("/v1/realtime/calls")
async def create_realtime_call_boundary(request: Request) -> JSONResponse:
    del request
    return _realtime_rest_boundary("/v1/realtime/calls")


@router.post("/v1/realtime/translations/client_secrets")
async def create_realtime_translation_secret_boundary(
    request: Request,
) -> JSONResponse:
    del request
    return _realtime_rest_boundary("/v1/realtime/translations/client_secrets")


@router.websocket("/v1/realtime")
async def websocket_realtime_boundary(websocket: WebSocket) -> None:
    """Emit an explicit error and close without claiming a Realtime session."""

    await websocket.accept()
    await websocket.send_json({"type": "error", **realtime_unavailable_error()})
    await websocket.close(code=1013, reason="realtime_unavailable")


def _canonical_item_id(response_id: str, index: int, item: Any, prefix: str) -> str:
    encoded = json.dumps(
        {"response_id": response_id, "index": index, "item": item},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:32]}"


def _input_content_parts(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "input_text", "text": content}]
    if isinstance(content, list):
        parts: list[dict[str, Any]] = []
        for part in content:
            if isinstance(part, str):
                parts.append({"type": "input_text", "text": part})
                continue
            if not isinstance(part, dict):
                parts.append({
                    "type": "input_text",
                    "text": json.dumps(part, ensure_ascii=False, default=str),
                })
                continue
            normalized = copy.deepcopy(part)
            if normalized.get("type") == "text":
                normalized["type"] = "input_text"
            parts.append(normalized)
        return parts
    return [{
        "type": "input_text",
        "text": json.dumps(content, ensure_ascii=False, default=str),
    }]


def response_input_items(response_id: str, input_value: Any) -> list[dict[str, Any]]:
    """Convert the exact stored request input into stable Response items."""

    raw_items: list[Any]
    if isinstance(input_value, str):
        raw_items = [{"role": "user", "content": input_value}]
    elif isinstance(input_value, list):
        raw_items = list(input_value)
    else:
        raw_items = [{"role": "user", "content": input_value}]

    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_items):
        if isinstance(raw, dict) and ("role" in raw or raw.get("type") == "message"):
            item = {
                "id": str(raw.get("id") or _canonical_item_id(response_id, index, raw, "msg")),
                "type": "message",
                "role": str(raw.get("role") or "user"),
                "content": _input_content_parts(raw.get("content", "")),
            }
        elif isinstance(raw, dict):
            item = copy.deepcopy(raw)
            item_type = str(item.get("type") or "input_item")
            item["type"] = item_type
            item["id"] = str(
                item.get("id") or _canonical_item_id(response_id, index, raw, "item")
            )
        else:
            item = {
                "id": _canonical_item_id(response_id, index, raw, "msg"),
                "type": "message",
                "role": "user",
                "content": _input_content_parts(raw),
            }

        if item["id"] in seen_ids:
            item["id"] = _canonical_item_id(response_id, index, raw, "item")
        seen_ids.add(item["id"])
        items.append(item)
    return items


def response_input_item_list(
    response_id: str,
    input_value: Any,
    *,
    limit: int = 20,
    order: Literal["asc", "desc"] = "desc",
    after: str | None = None,
) -> dict[str, Any]:
    """Build the OpenAI pagination envelope for recorded response inputs."""

    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")
    if order not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="order must be `asc` or `desc`")

    ordered = response_input_items(response_id, input_value)
    if order == "desc":
        ordered.reverse()

    start = 0
    if after is not None:
        try:
            start = next(index for index, item in enumerate(ordered) if item["id"] == after) + 1
        except StopIteration as exc:
            raise HTTPException(status_code=400, detail="input item cursor not found") from exc

    page = ordered[start:start + limit]
    return {
        "object": "list",
        "data": page,
        "first_id": page[0]["id"] if page else None,
        "last_id": page[-1]["id"] if page else None,
        "has_more": start + len(page) < len(ordered),
    }
