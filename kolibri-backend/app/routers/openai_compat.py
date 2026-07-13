"""Sanitised OpenAI-compatible public surface for the ``kolibri`` model.

Provider identities and raw upstream payloads never cross this boundary.  The
current compatibility registry is process-local; durable response ownership
belongs to the forthcoming Rust/PostgreSQL response authority.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import ai_provider
from app.database import get_db
from app.models import PublicApiKeyDB
from app.openai_responses import cancel_response, retrieve_response
from sqlalchemy.orm import Session


router = APIRouter()
_records: OrderedDict[str, dict[str, Any]] = OrderedDict()
_idempotency: dict[str, tuple[str, str]] = {}
_MAX_RECORDS = 1_000
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
_FAILED_RESULT_STATUSES = {"error", "failed", "incomplete", "unavailable", "capability_unavailable"}


async def _authorize_public(request: Request, db: Session = Depends(get_db)) -> None:
    """Fail closed for paid public API routes; browser aliases are separate."""
    if request.url.path.startswith("/api/v1/"):
        return
    configured = [
        item.strip().lower()
        for item in os.getenv("KOLIBRI_PUBLIC_API_KEY_SHA256", "").split(",")
        if item.strip()
    ]
    database_configured = db.query(PublicApiKeyDB.id).first() is not None
    if not configured and not database_configured:
        raise HTTPException(
            status_code=503,
            detail={"code": "public_api_not_configured"},
        )
    authorization = request.headers.get("Authorization", "")
    token = authorization[7:] if authorization.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail={"code": "invalid_api_key"})
    digest = hashlib.sha256(token.encode()).hexdigest()
    env_match = any(hmac.compare_digest(digest, expected) for expected in configured)
    key = db.query(PublicApiKeyDB).filter(PublicApiKeyDB.secret_hash == digest).first()
    database_match = bool(
        key is not None
        and key.revoked_at is None
        and hmac.compare_digest(str(key.secret_hash), digest)
    )
    if not env_match and not database_match:
        raise HTTPException(status_code=401, detail={"code": "invalid_api_key"})
    if database_match:
        key.last_used_at = datetime.now(timezone.utc)
        db.commit()


_PUBLIC_AUTH = [Depends(_authorize_public)]


def _validate_idempotency_key(value: str | None) -> None:
    if value and not _IDEMPOTENCY_KEY.fullmatch(value):
        raise HTTPException(status_code=400, detail={"code": "invalid_idempotency_key"})


class PublicPolicy(BaseModel):
    mode: Literal["fast", "deep"] = "fast"
    reasoning_effort: Literal["low", "high"] = "low"
    tool_choice: Literal["auto"] = "auto"
    background: bool = False
    allowed_capabilities: list[str] = Field(default_factory=list, max_length=32)


class ResponsesRequest(BaseModel):
    model: str = "kolibri"
    input: str | list[dict[str, Any]]
    stream: bool = False
    background: bool = False
    previous_response_id: str | None = None
    reasoning: dict[str, Any] = Field(default_factory=dict)
    tools: list[dict[str, Any]] | None = None
    policy: PublicPolicy | None = None


class ChatCompletionsRequest(BaseModel):
    model: str = "kolibri"
    messages: list[dict[str, Any]]
    stream: bool = False
    policy: PublicPolicy | None = None


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


def _owner_scope() -> str:
    return "owner"


async def _authorize_api_key_admin(
    owner_token: str | None = Header(default=None, alias="X-Kolibri-Owner-Token"),
) -> None:
    expected = os.getenv("KOLIBRI_OWNER_API_ADMIN_TOKEN_SHA256", "").strip().lower()
    if not expected or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise HTTPException(status_code=503, detail={"code": "api_key_admin_not_configured"})
    supplied = owner_token or ""
    digest = hashlib.sha256(supplied.encode()).hexdigest()
    if not supplied or not hmac.compare_digest(digest, expected):
        raise HTTPException(status_code=401, detail={"code": "owner_authentication_required"})


def _public_api_key(row: PublicApiKeyDB) -> dict[str, Any]:
    return {
        "id": row.id,
        "object": "api_key",
        "name": row.name,
        "prefix": row.key_prefix,
        "created_at": int(row.created_at.replace(tzinfo=timezone.utc).timestamp()),
        "last_used_at": (
            int(row.last_used_at.replace(tzinfo=timezone.utc).timestamp())
            if row.last_used_at else None
        ),
        "revoked": row.revoked_at is not None,
        "revoked_at": (
            int(row.revoked_at.replace(tzinfo=timezone.utc).timestamp())
            if row.revoked_at else None
        ),
    }


def developer_api_keys_capability() -> dict[str, Any] | None:
    """Advertise the renderer only when owner auth makes routes invocable."""

    expected = os.getenv("KOLIBRI_OWNER_API_ADMIN_TOKEN_SHA256", "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        return None
    return {
        "id": "developer.api_keys",
        "name": "API-ключи",
        "description": "Создание, список и отзыв owner-scoped API-ключей.",
        "kind": "developer",
        "status": "live",
        "availability_reason": None,
        "invocable": True,
        "permitted": True,
        "route": {
            "configured": True,
            "healthy": True,
            "status": "live",
        },
        "renderer": {
            "available": True,
            "id": "developer_api_keys",
            "status": "live",
        },
        "source": {"type": "route_and_owner_auth_configuration"},
    }


@router.post(
    "/api/v1/developer/api-keys",
    status_code=201,
    dependencies=[Depends(_authorize_api_key_admin)],
)
@router.post("/v1/api-keys", status_code=201, dependencies=[Depends(_authorize_api_key_admin)])
async def create_api_key(request: ApiKeyCreateRequest, db: Session = Depends(get_db)):
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail={"code": "api_key_name_required"})
    plaintext = f"koli_live_{secrets.token_urlsafe(32)}"
    digest = hashlib.sha256(plaintext.encode()).hexdigest()
    row = PublicApiKeyDB(
        id=f"key_{secrets.token_hex(12)}",
        owner_scope=_owner_scope(),
        name=name,
        key_prefix=plaintext[:14],
        secret_hash=digest,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {**_public_api_key(row), "secret": plaintext, "secret_shown_once": True}


@router.get(
    "/api/v1/developer/api-keys",
    dependencies=[Depends(_authorize_api_key_admin)],
)
@router.get("/v1/api-keys", dependencies=[Depends(_authorize_api_key_admin)])
async def list_api_keys(db: Session = Depends(get_db)):
    rows = db.query(PublicApiKeyDB).filter(
        PublicApiKeyDB.owner_scope == _owner_scope()
    ).order_by(PublicApiKeyDB.created_at.desc(), PublicApiKeyDB.id.desc()).all()
    return {"object": "list", "data": [_public_api_key(row) for row in rows]}


@router.delete(
    "/api/v1/developer/api-keys/{key_id}",
    dependencies=[Depends(_authorize_api_key_admin)],
)
@router.delete("/v1/api-keys/{key_id}", dependencies=[Depends(_authorize_api_key_admin)])
async def revoke_api_key(key_id: str, db: Session = Depends(get_db)):
    row = db.query(PublicApiKeyDB).filter(
        PublicApiKeyDB.id == key_id,
        PublicApiKeyDB.owner_scope == _owner_scope(),
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "api_key_not_found"})
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return _public_api_key(row)


_TOOL_CAPABILITIES = {
    "web_search": "openai.web_search",
    "file_search": "openai.file_search",
    "code_interpreter": "openai.code_interpreter",
    "image_generation": "openai.image_generation",
    "mcp": "openai.remote_mcp",
    "computer": "openai.computer",
}


def _ensure_public_model(model: str) -> None:
    if model != "kolibri":
        raise HTTPException(status_code=404, detail={"code": "model_not_found", "message": "Model not found"})


def _normalise_messages(value: str | list[dict[str, Any]]) -> list[dict[str, str]]:
    if isinstance(value, str):
        return [{"role": "user", "content": value}]
    messages: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user")
        content = item.get("content")
        if isinstance(content, list):
            text_parts = [
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict) and part.get("type") in {"input_text", "text"}
            ]
            content = "".join(text_parts)
        messages.append({"role": role, "content": str(content or "")})
    if not messages:
        raise HTTPException(status_code=422, detail="input must contain at least one text message")
    return messages


def _policy(
    supplied: PublicPolicy | None,
    *,
    reasoning: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    background: bool = False,
) -> dict[str, Any] | None:
    if supplied:
        policy = supplied.model_dump()
    elif reasoning or tools is not None or background:
        effort = str((reasoning or {}).get("effort") or "low")
        policy = {
            "mode": "deep" if effort in {"high", "xhigh", "max"} or background else "fast",
            "reasoning_effort": "high" if effort in {"high", "xhigh", "max"} else "low",
            "tool_choice": "auto",
            "background": background,
            "allowed_capabilities": [],
        }
    else:
        return None

    if tools is not None:
        requested = {
            _TOOL_CAPABILITIES[str(tool.get("type") or "")]
            for tool in tools
            if isinstance(tool, dict) and str(tool.get("type") or "") in _TOOL_CAPABILITIES
        }
        if supplied:
            policy["allowed_capabilities"] = sorted(
                requested.intersection(set(policy["allowed_capabilities"]))
            )
        else:
            policy["allowed_capabilities"] = sorted(requested)
    policy["background"] = bool(policy.get("background")) and policy["mode"] == "deep"
    return policy


async def _image_result_if_requested(
    messages: list[dict[str, str]],
    policy: dict[str, Any] | None,
    *,
    run_id: str | None = None,
) -> dict[str, Any] | None:
    """Route image intent exclusively through the verified artifact service."""
    from app.image_artifacts import (
        IMAGE_CAPABILITY_ID,
        ImageCapabilityUnavailable,
        ImageGenerationFailed,
        ImageGenerationRequest,
        generate_invocable_image,
        image_execution_identity,
        is_image_generation_request,
    )

    prompt = next(
        (str(message.get("content") or "") for message in reversed(messages) if message.get("role") == "user"),
        "",
    )
    if not is_image_generation_request(prompt):
        return None
    try:
        artifact = await generate_invocable_image(
            ImageGenerationRequest(prompt=prompt),
            policy=policy,
            run_id=run_id,
        )
    except ImageCapabilityUnavailable:
        return {
            "content": "",
            "actions": [],
            "status": "capability_unavailable",
            "error_code": "capability_unavailable",
            "recoverable": True,
            "capability": IMAGE_CAPABILITY_ID,
            "provider": "none",
        }
    except ImageGenerationFailed:
        image_identity = image_execution_identity()
        return {
            "content": "",
            "actions": [],
            "status": "failed",
            "error_code": "image_artifact_verification_failed",
            "recoverable": True,
            "capability": IMAGE_CAPABILITY_ID,
            "provider": image_identity["provider"],
            "model": image_identity["model"],
        }
    image_identity = image_execution_identity()
    return {
        "content": "Изображение создано и проверено.",
        "actions": [{"type": "present_image", "label": "Открыть изображение", "data": artifact}],
        "artifact": artifact,
        "status": "ready",
        "provider": image_identity["provider"],
        "model": artifact["model"],
    }


def _new_id() -> str:
    return f"resp_kolibri_{secrets.token_hex(12)}"


def _public_response(record: dict[str, Any]) -> dict[str, Any]:
    content = str(record.get("content") or "")
    output = []
    if content:
        output.append({
            "id": f"msg_{record['id'].removeprefix('resp_')}",
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": content, "annotations": []}],
        })
    artifact = record.get("artifact")
    if isinstance(artifact, dict):
        output.append({
            "id": f"artifact_{artifact.get('id')}",
            "type": "artifact",
            "status": "completed",
            "artifact": artifact,
        })
    return {
        "id": record["id"],
        "object": "response",
        "created_at": record["created_at"],
        "status": record["status"],
        "model": "kolibri",
        "output": output,
        "output_text": content,
        "error": record.get("error"),
        "artifacts": [artifact] if isinstance(artifact, dict) else [],
    }


def _store(record: dict[str, Any]) -> None:
    record.setdefault("events", [])
    record.setdefault("last_sequence", 0)
    _records[record["id"]] = record
    _records.move_to_end(record["id"])
    while len(_records) > _MAX_RECORDS:
        response_id, _ = _records.popitem(last=False)
        for key, (_, stored_id) in list(_idempotency.items()):
            if stored_id == response_id:
                _idempotency.pop(key, None)


def _append_event(record: dict[str, Any], event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    record["last_sequence"] = int(record.get("last_sequence") or 0) + 1
    event = {
        "type": event_type,
        "response_id": record["id"],
        "sequence": record["last_sequence"],
        **payload,
    }
    record.setdefault("events", []).append(event)
    _store(record)
    return event


def begin_public_response(messages: list[dict[str, str]]) -> str:
    """Create the canonical Kolibri response ID used by legacy chat streams."""
    response_id = _new_id()
    record = {
        "id": response_id,
        "created_at": int(time.time()),
        "status": "in_progress",
        "content": "",
        "error": None,
        "upstream_response_id": None,
        "provider_route": None,
        "messages": messages,
        "events": [],
        "last_sequence": 0,
    }
    _store(record)
    _append_event(record, "response.created", {"response": _public_response(record)})
    return response_id


def record_public_stream_chunk(response_id: str, chunk: dict[str, Any]) -> None:
    record = _records.get(response_id)
    if not record or record["status"] in {"cancelled", "completed", "failed"}:
        return
    if chunk.get("content"):
        delta = str(chunk["content"])
        record["content"] = str(record.get("content") or "") + delta
        _append_event(record, "response.output_text.delta", {"delta": delta})
    if isinstance(chunk.get("work_summary"), dict):
        summary = chunk["work_summary"]
        _append_event(record, "response.work_summary.updated", {
            "work_summary": {
                "stage": summary.get("stage"),
                "summary": summary.get("summary"),
                "status": summary.get("status"),
            },
        })
    if isinstance(chunk.get("tool_event"), dict):
        tool = chunk["tool_event"]
        event_type = "response.tool.completed" if tool.get("type") == "tool.completed" else "response.tool.started"
        _append_event(record, event_type, {
            "name": tool.get("tool"),
            "status": tool.get("status"),
        })
    if chunk.get("done"):
        record["upstream_response_id"] = chunk.get("response_id")
        record["provider_route"] = chunk.get("provider")
        actions = chunk.get("actions")
        if isinstance(actions, list):
            for action in actions:
                if (
                    isinstance(action, dict)
                    and action.get("type") == "present_image"
                    and isinstance(action.get("data"), dict)
                ):
                    record["artifact"] = action["data"]
                    _append_event(record, "response.artifact.ready", {
                        "artifact_type": "image",
                        "artifact_id": action["data"].get("id"),
                        "artifact": action["data"],
                    })
                    break
        status = str(chunk.get("status") or "completed")
        record["status"] = "failed" if status in _FAILED_RESULT_STATUSES else "cancelled" if status == "cancelled" else "completed"
        record["error"] = (
            {
                "code": chunk.get("error_code") or "response_failed",
                "recoverable": chunk.get("recoverable") is True,
                "capability": chunk.get("capability"),
            }
            if record["status"] == "failed" else None
        )
        event_type = f"response.{record['status']}"
        _append_event(record, event_type, {"response": _public_response(record)})


def _request_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _idempotent_record(key: str | None, request_hash: str) -> dict[str, Any] | None:
    if not key:
        return None
    existing = _idempotency.get(key)
    if not existing:
        return None
    previous_hash, response_id = existing
    if previous_hash != request_hash:
        raise HTTPException(status_code=409, detail={"code": "idempotency_conflict"})
    return _records.get(response_id)


def _record_result(response_id: str, result: dict[str, Any], messages: list[dict[str, str]]) -> dict[str, Any]:
    status = str(result.get("status") or "completed")
    if status in {"idle", "ready", "source_backed", "preliminary"}:
        status = "completed"
    elif status in _FAILED_RESULT_STATUSES:
        status = "failed"
    record = _records.get(response_id, {})
    record.update({
        "id": response_id,
        "created_at": record.get("created_at", int(time.time())),
        "status": status,
        "content": str(result.get("content") or ""),
        "error": {
            "code": result.get("error_code") or "response_failed",
            "recoverable": result.get("recoverable") is True,
            "capability": result.get("capability"),
        } if status == "failed" else None,
        "artifact": result.get("artifact"),
        "upstream_response_id": result.get("response_id"),
        "provider_route": result.get("provider"),
        "messages": messages,
    })
    _store(record)
    if not record.get("events"):
        _append_event(record, "response.created", {"response": _public_response(record)})
        if record["content"]:
            _append_event(record, "response.output_text.delta", {"delta": record["content"]})
        if isinstance(record.get("artifact"), dict):
            _append_event(record, "response.artifact.ready", {
                "artifact_type": "image",
                "artifact_id": record["artifact"].get("id"),
                "artifact": record["artifact"],
            })
        terminal = f"response.{record['status']}" if record["status"] in {"completed", "failed", "cancelled"} else "response.status.updated"
        _append_event(record, terminal, {
            "response": _public_response(record),
            "status": record["status"],
        })
    return record


async def _execute_response(
    request: ResponsesRequest,
    *,
    idempotency_key: str | None,
) -> tuple[dict[str, Any], list[dict[str, str]], dict[str, Any] | None, str]:
    _ensure_public_model(request.model)
    messages = _normalise_messages(request.input)
    previous_upstream_id = None
    if request.previous_response_id:
        previous = _records.get(request.previous_response_id)
        if not previous:
            raise HTTPException(status_code=404, detail={"code": "response_not_found"})
        previous_upstream_id = previous.get("upstream_response_id")
        if not previous_upstream_id:
            messages = [*previous.get("messages", []), {"role": "assistant", "content": previous.get("content", "")}, *messages]
    policy = _policy(
        request.policy,
        reasoning=request.reasoning,
        tools=request.tools,
        background=request.background,
    )
    fingerprint = _request_hash({
        "model": request.model,
        "messages": messages,
        "previous": request.previous_response_id,
        "policy": policy,
        "background": request.background,
    })
    existing = _idempotent_record(idempotency_key, fingerprint)
    if existing:
        return existing, messages, policy, fingerprint
    return {}, messages, policy, fingerprint


async def execute_kolibri_response(
    request: ResponsesRequest,
    *,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Execute one non-streaming response through the canonical provider path.

    Browser, API and non-HTTP channel adapters (currently Telegram) call this
    function instead of reimplementing provider selection, image routing or
    response recording.  The returned value is the internal response record;
    callers must expose only a channel-appropriate sanitized representation.
    """

    _validate_idempotency_key(idempotency_key)
    existing, messages, policy, fingerprint = await _execute_response(
        request,
        idempotency_key=idempotency_key,
    )
    if existing:
        return existing

    response_id = _new_id()
    task_type = "analyze" if policy and policy["mode"] == "deep" else "fast" if policy else "chat"
    result = await _image_result_if_requested(messages, policy, run_id=response_id)
    if result is None:
        result = await ai_provider.chat_completion(
            messages,
            task_type=task_type,
            previous_response_id=(
                _records.get(request.previous_response_id, {}).get("upstream_response_id")
                if request.previous_response_id else None
            ),
            background=request.background,
            policy=policy,
            idempotency_key=idempotency_key,
        )
    record = _record_result(response_id, result, messages)
    if idempotency_key:
        _idempotency[idempotency_key] = (fingerprint, response_id)
    return record


@router.post("/api/v1/responses", include_in_schema=False, dependencies=_PUBLIC_AUTH)
@router.post("/v1/responses", dependencies=_PUBLIC_AUTH)
async def create_public_response(
    request: ResponsesRequest,
    http_request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    from app.rate_limiter import chat_limiter, check_rate_limit

    await check_rate_limit(http_request, chat_limiter)
    if request.stream:
        _validate_idempotency_key(idempotency_key)
        return await _streaming_response(request, idempotency_key)
    record = await execute_kolibri_response(request, idempotency_key=idempotency_key)
    return _public_response(record)


@router.post("/v1/responses/stream", dependencies=_PUBLIC_AUTH)
async def stream_public_response(
    request: ResponsesRequest,
    http_request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Compatibility helper; POST /v1/responses with stream=true delegates here."""
    from app.rate_limiter import chat_limiter, check_rate_limit

    await check_rate_limit(http_request, chat_limiter)
    _validate_idempotency_key(idempotency_key)
    request.stream = True
    return await _streaming_response(request, idempotency_key)


async def _streaming_response(request: ResponsesRequest, idempotency_key: str | None):
    existing, messages, policy, fingerprint = await _execute_response(
        request, idempotency_key=idempotency_key
    )
    response_id = existing.get("id") or begin_public_response(messages)
    if idempotency_key and not existing:
        _idempotency[idempotency_key] = (fingerprint, response_id)
    task_type = "analyze" if policy and policy["mode"] == "deep" else "fast" if policy else "chat"
    async def events():
        created = _public_response(existing or _records[response_id])
        yield _sse("response.created", {"type": "response.created", "response": created})
        if existing:
            existing_status = str(existing.get("status") or "in_progress")
            existing_event = (
                f"response.{existing_status}"
                if existing_status in {"completed", "failed", "cancelled"}
                else "response.status.updated"
            )
            yield _sse(existing_event, {"type": existing_event, "response": created})
            return

        image_result = await _image_result_if_requested(
            messages, policy, run_id=response_id
        )
        if image_result is not None:
            if image_result.get("content"):
                content_chunk = {"content": str(image_result["content"]), "done": False}
                record_public_stream_chunk(response_id, content_chunk)
                yield _sse("response.output_text.delta", {
                    "type": "response.output_text.delta",
                    "response_id": response_id,
                    "delta": str(image_result["content"]),
                })
            final_image = {**image_result, "content": "", "done": True}
            record_public_stream_chunk(response_id, final_image)
            record = _records[response_id]
            if isinstance(record.get("artifact"), dict):
                yield _sse("response.artifact.ready", {
                    "type": "response.artifact.ready",
                    "response_id": response_id,
                    "artifact_type": "image",
                    "artifact_id": record["artifact"].get("id"),
                    "artifact": record["artifact"],
                })
            event_type = f"response.{record['status']}"
            yield _sse(event_type, {"type": event_type, "response": _public_response(record)})
            return

        text_parts: list[str] = []
        final_internal: dict[str, Any] = {}
        async for chunk in ai_provider.chat_completion_stream(
            messages,
            task_type=task_type,
            previous_response_id=(
                _records.get(request.previous_response_id, {}).get("upstream_response_id")
                if request.previous_response_id else None
            ),
            background=request.background,
            policy=policy,
            idempotency_key=idempotency_key,
            run_id=response_id,
        ):
            record_public_stream_chunk(response_id, chunk)
            if chunk.get("content"):
                delta = str(chunk["content"])
                text_parts.append(delta)
                yield _sse("response.output_text.delta", {
                    "type": "response.output_text.delta",
                    "response_id": response_id,
                    "delta": delta,
                })
            elif isinstance(chunk.get("work_summary"), dict):
                summary = chunk["work_summary"]
                yield _sse("response.work_summary.updated", {
                    "type": "response.work_summary.updated",
                    "response_id": response_id,
                    "stage": summary.get("stage"),
                    "summary": summary.get("summary"),
                    "status": summary.get("status"),
                })
            elif isinstance(chunk.get("tool_event"), dict):
                tool = chunk["tool_event"]
                event_type = "response.tool.completed" if tool.get("type") == "tool.completed" else "response.tool.started"
                yield _sse(event_type, {
                    "type": event_type,
                    "response_id": response_id,
                    "tool": tool.get("tool"),
                    "label": tool.get("label"),
                    "status": tool.get("status"),
                })
            if chunk.get("done"):
                final_internal = chunk
        if not final_internal:
            final_internal = {
                "content": "",
                "done": True,
                "status": "failed",
                "error_code": "provider_stream_failed",
            }
            record_public_stream_chunk(response_id, final_internal)
        record = _records[response_id]
        event_type = f"response.{record['status']}"
        yield _sse(event_type, {"type": event_type, "response": _public_response(record)})

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


def _sse(event_type: str, payload: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/api/v1/responses/{response_id}", include_in_schema=False, dependencies=_PUBLIC_AUTH)
@router.get("/v1/responses/{response_id}", dependencies=_PUBLIC_AUTH)
async def get_public_response(response_id: str):
    record = _records.get(response_id)
    if not record:
        raise HTTPException(status_code=404, detail={"code": "response_not_found"})
    if record["status"] in {"queued", "in_progress"} and record.get("provider_route") == "openai_codex":
        upstream_id = record.get("upstream_response_id")
        if upstream_id:
            provider = ai_provider.PROVIDERS["openai_codex"]
            parsed = await retrieve_response(provider, upstream_id)
            record["status"] = parsed["status"]
            record["content"] = parsed["content"]
            _store(record)
    return _public_response(record)


@router.get("/api/v1/responses/{response_id}/events", include_in_schema=False, dependencies=_PUBLIC_AUTH)
@router.get("/v1/responses/{response_id}/events", dependencies=_PUBLIC_AUTH)
async def public_response_events(response_id: str, starting_after: int = 0):
    if response_id not in _records:
        raise HTTPException(status_code=404, detail={"code": "response_not_found"})

    async def events():
        sequence = max(0, int(starting_after))
        while True:
            record = _records.get(response_id)
            if not record:
                return
            if record["status"] in {"queued", "in_progress"} and record.get("provider_route") == "openai_codex":
                upstream_id = record.get("upstream_response_id")
                if upstream_id:
                    try:
                        parsed = await retrieve_response(ai_provider.PROVIDERS["openai_codex"], upstream_id)
                        if parsed["status"] != record["status"]:
                            record["status"] = parsed["status"]
                            if parsed.get("content") and not record.get("content"):
                                record["content"] = parsed["content"]
                                _append_event(record, "response.output_text.delta", {"delta": parsed["content"]})
                            terminal = parsed["status"] in {"completed", "failed", "cancelled"}
                            event_type = f"response.{parsed['status']}" if terminal else "response.status.updated"
                            _append_event(record, event_type, {
                                "status": parsed["status"],
                                "response": _public_response(record),
                            })
                    except Exception:
                        # A transient status-poll error is not a terminal task
                        # failure; the next resume call may recover it.
                        pass
            pending = [event for event in record.get("events", []) if int(event["sequence"]) > sequence]
            for event in pending:
                sequence = int(event["sequence"])
                yield _sse(str(event["type"]), event)
            if record["status"] in {"completed", "failed", "cancelled"}:
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@router.post("/api/v1/responses/{response_id}/cancel", include_in_schema=False, dependencies=_PUBLIC_AUTH)
@router.post("/v1/responses/{response_id}/cancel", dependencies=_PUBLIC_AUTH)
async def cancel_public_response(response_id: str):
    record = _records.get(response_id)
    if not record:
        raise HTTPException(status_code=404, detail={"code": "response_not_found"})
    if record["status"] not in {"completed", "failed", "cancelled"}:
        from app.codex_cli_provider import cancel_codex_cli_run
        from app.codex_cli_image_provider import cancel_codex_cli_image_run

        # The call is safe even when the selected route is not Codex CLI: in
        # that case no process owns this public response ID and it is a no-op.
        await cancel_codex_cli_run(response_id)
        await cancel_codex_cli_image_run(response_id)
        upstream_id = record.get("upstream_response_id")
        if upstream_id and record.get("provider_route") == "openai_codex":
            await cancel_response(ai_provider.PROVIDERS["openai_codex"], upstream_id)
        # The execution stream may have reached a terminal state while the
        # process/provider cancellation was in flight. Never overwrite it or
        # append a duplicate terminal event.
        if record["status"] not in {"completed", "failed", "cancelled"}:
            record["status"] = "cancelled"
            _append_event(record, "response.cancelled", {"response": _public_response(record)})
    return _public_response(record)


@router.post("/v1/chat/completions", dependencies=_PUBLIC_AUTH)
async def chat_completions(
    request: ChatCompletionsRequest,
    http_request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    from app.rate_limiter import chat_limiter, check_rate_limit

    await check_rate_limit(http_request, chat_limiter)
    _validate_idempotency_key(idempotency_key)
    _ensure_public_model(request.model)
    messages = _normalise_messages(request.messages)
    policy = _policy(request.policy)
    task_type = "analyze" if policy and policy["mode"] == "deep" else "fast" if policy else "chat"
    completion_id = f"chatcmpl_{secrets.token_hex(12)}"
    image_result = await _image_result_if_requested(
        messages, policy, run_id=completion_id
    )
    if image_result is not None and image_result.get("status") in _FAILED_RESULT_STATUSES:
        raise HTTPException(status_code=503, detail={
            "code": image_result.get("error_code") or "capability_unavailable",
            "capability": image_result.get("capability"),
            "recoverable": image_result.get("recoverable") is True,
        })
    if request.stream:
        async def events():
            if image_result is not None:
                artifact = image_result.get("artifact")
                payload = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": "kolibri",
                    "choices": [{
                        "index": 0,
                        "delta": {"content": str(image_result.get("content") or "")},
                        "finish_reason": "stop",
                    }],
                    "artifact": artifact,
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return
            async for chunk in ai_provider.chat_completion_stream(
                messages,
                task_type=task_type,
                policy=policy,
                idempotency_key=idempotency_key,
            ):
                if chunk.get("content"):
                    payload = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": "kolibri",
                        "choices": [{"index": 0, "delta": {"content": chunk["content"]}, "finish_reason": None}],
                    }
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if chunk.get("done"):
                    payload = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": "kolibri",
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    }
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    result = image_result or await ai_provider.chat_completion(
        messages,
        task_type=task_type,
        policy=policy,
        idempotency_key=idempotency_key,
    )
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "kolibri",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": str(result.get("content") or ""),
                **({"artifact": result["artifact"]} if isinstance(result.get("artifact"), dict) else {}),
            },
            "finish_reason": "stop" if result.get("status") != "error" else "content_filter",
        }],
    }


@router.get("/v1/models", dependencies=_PUBLIC_AUTH)
async def models():
    return {"object": "list", "data": [{
        "id": "kolibri",
        "object": "model",
        "created": 0,
        "owned_by": "kolibri",
    }]}


@router.post("/v1/realtime", dependencies=_PUBLIC_AUTH)
@router.post("/v1/realtime/sessions", dependencies=_PUBLIC_AUTH)
async def realtime_unavailable():
    raise HTTPException(status_code=501, detail={
        "code": "realtime_not_implemented",
        "message": "Kolibri Realtime is not available in this release.",
    })
