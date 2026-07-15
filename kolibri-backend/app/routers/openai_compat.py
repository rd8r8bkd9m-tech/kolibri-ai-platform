"""Sanitised OpenAI-compatible public surface for the ``kolibri`` model.

Provider identities and raw upstream payloads never cross this boundary.
Response ownership, idempotency and ordered public events are persisted by the
SQL response authority; process memory is only a bounded read-through cache.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app import ai_provider
from app.database import get_db
from app.models import PublicApiKeyDB
from app.project_schemas import PersistedFileAction
from app.public_scope import authorize_public_scope as _authorize_public
from app.openai_responses import cancel_response, retrieve_response
from app.response_store import (
    ResponseIdempotencyConflict,
    find_idempotent_response,
    load_response_record,
    save_response_record,
)
from app.structured_output import (
    StructuredOutputError,
    StructuredOutputSpec,
    chat_spec,
    instruction as structured_instruction,
    parse_and_validate,
    responses_spec,
)
from sqlalchemy.orm import Session


router = APIRouter()
_records: OrderedDict[str, dict[str, Any]] = OrderedDict()
_idempotency: dict[tuple[str, str], tuple[str, str]] = {}
_inflight: dict[tuple[str, str], tuple[str, Future[dict[str, Any]]]] = {}
_inflight_lock = threading.Lock()
_MAX_RECORDS = 1_000
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
_FAILED_RESULT_STATUSES = {"error", "failed", "incomplete", "unavailable", "capability_unavailable"}
_TERMINAL_RESPONSE_STATUSES = {"cancelled", "completed", "failed"}
_NONTERMINAL_RESPONSE_STATUSES = {
    "queued",
    "planning",
    "in_progress",
    "running",
    "waiting_for_input",
    "approval_required",
    "verifying",
}
_PUBLIC_ACTION_TYPES = {
    "create_estimate",
    "create_document",
    "present_image",
    "present_artifact",
}
_PUBLIC_WORK_STAGES = {
    "accepted",
    "planning",
    "provider_route",
    "provider_attempt",
    "response_received",
    "tool_execution",
    "source_retrieval",
    "calculation",
    "artifact_materialization",
    "artifact_verification",
    "background",
    "resuming",
    "verification",
    "cancelled",
    "reasoning_summary",
}
_PUBLIC_WORK_STAGE_ALIASES = {
    "answer": "response_received",
    "calculating": "tool_execution",
    "sourcing": "source_retrieval",
    "verifying": "verification",
    "retrying": "resuming",
    "factory_dispatch": "provider_route",
    "factory_verified": "verification",
    "codex_turn": "tool_execution",
    "plan_updated": "planning",
}
_PUBLIC_WORK_STATUS_ALIASES = {
    "queued": "active",
    "in_progress": "active",
    "running": "active",
    "success": "completed",
    "ready": "completed",
    "idle": "completed",
    "error": "failed",
    "unavailable": "failed",
    "retrying": "active",
    "waiting": "active",
    "recovering": "active",
}
_PUBLIC_WORK_STATUSES = {
    "active",
    "completed",
    "failed",
}
_PUBLIC_WORK_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_PUBLIC_SUMMARY_SECRET = re.compile(
    r"(?i)(?:bearer\s+\S+|(?:sk|koli)[_-][A-Za-z0-9._-]{12,}|"
    r"(?:api[_ -]?key|token|password|secret)\s*[:=]\s*\S+|"
    r"https?://\S+|/(?:Users|home|srv|etc)/\S+|"
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b|"
    r"\b(?:home|control[\s_-]*plane|"
    r"(?:node|agent)(?:[\s_-]*\d+|[\s_-]+[A-Za-z0-9._-]+)|"
    r"mimo|deepseek|codex|kimi|openai|anthropic|claude|gemini|"
    r"gpt-[A-Za-z0-9._-]+)\b)"
)
_FORBIDDEN_WORK_SUMMARY_KEYS = {
    "reasoning",
    "reasoning_content",
    "reasoning_text",
    "prompt",
    "prompts",
    "tool_arguments",
    "credentials",
}


def _public_actions(value: Any) -> list[dict[str, Any]]:
    """Return only the bounded, user-facing action contract.

    Provider routing metadata must never cross the public compatibility
    boundary.  Action data is already normalised by ``ai_provider``; this
    final copy constrains the top-level shape and makes the stored value
    independent from a mutable provider result.
    """
    if not isinstance(value, list):
        return []

    actions: list[dict[str, Any]] = []
    for candidate in value:
        if not isinstance(candidate, dict):
            continue
        action_type = str(candidate.get("type") or "")
        label = str(candidate.get("label") or "").strip()
        data = candidate.get("data")
        if (
            action_type not in _PUBLIC_ACTION_TYPES
            or not label
            or len(label) > 120
            or not isinstance(data, dict)
        ):
            continue
        try:
            if action_type == "present_artifact":
                # Generic files/sites/apps cross a stricter boundary than
                # legacy inline drafts: exact MIME, producer, digest and
                # canonical retrieval URLs are required before the action is
                # allowed into durable Responses or SSE.
                validated = PersistedFileAction.model_validate(candidate)
                actions.append(validated.model_dump(mode="json", exclude_none=True))
                continue
            public_data = json.loads(json.dumps(data, ensure_ascii=False))
        except (TypeError, ValueError):
            continue
        actions.append({"type": action_type, "label": label, "data": public_data})
    return actions


def _public_sources(value: Any) -> list[dict[str, Any]]:
    """Return bounded source evidence without provider or request metadata."""

    if not isinstance(value, list):
        return []
    sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for candidate in value[:20]:
        if not isinstance(candidate, dict):
            continue
        title = " ".join(str(candidate.get("title") or "").split())[:240]
        url = str(candidate.get("url") or "").strip()[:2_000]
        parsed = urlparse(url)
        if (
            not title
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or url in seen_urls
        ):
            continue
        seen_urls.add(url)
        source: dict[str, Any] = {
            "citation": len(sources) + 1,
            "title": title,
            "url": url,
        }
        snippet = " ".join(str(candidate.get("snippet") or "").split())[:1_000]
        if snippet:
            source["snippet"] = snippet
        retrieved_at = str(candidate.get("retrieved_at") or "")
        if retrieved_at:
            try:
                parsed_at = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
                if parsed_at.tzinfo is not None:
                    source["retrieved_at"] = parsed_at.isoformat()
            except ValueError:
                pass
        sources.append(source)
    return sources


def _public_work_identifier(value: Any, *, fallback: str) -> str:
    candidate = str(value or "")
    if _PUBLIC_WORK_ID.fullmatch(candidate):
        return candidate
    digest = hashlib.sha256(fallback.encode("utf-8")).hexdigest()[:24]
    return f"step_{digest}"


def _public_work_timestamp(value: Any) -> str:
    candidate = str(value or "")
    if candidate:
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).isoformat()


def _sanitize_public_work_summary(
    response_id: str,
    value: dict[str, Any],
) -> dict[str, Any] | None:
    """Build the only public/durable Work Trace payload.

    Internal provenance and raw reasoning-shaped values are rejected before
    persistence.  Unknown internal stages collapse to the bounded background
    stage rather than expanding the public contract.
    """

    if _FORBIDDEN_WORK_SUMMARY_KEYS.intersection(value):
        return None
    raw_stage = str(value.get("stage") or "background").strip().lower()
    if raw_stage in {"reasoning_content", "reasoning_text", "chain_of_thought"}:
        return None
    stage = _PUBLIC_WORK_STAGE_ALIASES.get(raw_stage, raw_stage)
    if stage not in _PUBLIC_WORK_STAGES:
        stage = "background"

    raw_status = str(value.get("status") or "active").strip().lower()
    status = "completed" if raw_status == "cancelled" and stage == "cancelled" else (
        "failed" if raw_status == "cancelled" else _PUBLIC_WORK_STATUS_ALIASES.get(raw_status, raw_status)
    )
    if status not in _PUBLIC_WORK_STATUSES:
        status = "active"

    summary = " ".join(str(value.get("summary") or "").split())
    summary = _PUBLIC_SUMMARY_SECRET.sub("[скрыто]", summary)[:600].strip()
    if not summary:
        return None

    kind = "reasoning_excerpt" if stage == "reasoning_summary" else "stage"
    step_id = _public_work_identifier(
        value.get("step_id"),
        fallback=f"{response_id}:{stage}",
    )
    summary_id: str | None = None
    if kind == "reasoning_excerpt":
        summary_id = _public_work_identifier(
            value.get("summary_id"),
            fallback=f"{response_id}:reasoning_summary",
        ).replace("step_", "summary_", 1)
    public = {
        "kind": kind,
        "step_id": step_id,
        "summary_id": summary_id,
        "stage": stage,
        "status": status,
        "summary": summary,
        "occurred_at": _public_work_timestamp(value.get("occurred_at")),
    }
    artifact_type = str(value.get("artifact_type") or "")
    artifact_id = str(value.get("artifact_id") or "")
    if re.fullmatch(r"[a-z0-9._-]{1,40}", artifact_type):
        public["artifact_type"] = artifact_type
    if re.fullmatch(r"[A-Za-z0-9_-]{1,160}", artifact_id):
        public["artifact_id"] = artifact_id
    return public


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
    text: dict[str, Any] | None = None
    policy: PublicPolicy | None = None


class ChatCompletionsRequest(BaseModel):
    model: str = "kolibri"
    messages: list[dict[str, Any]]
    stream: bool = False
    response_format: dict[str, Any] | None = None
    policy: PublicPolicy | None = None


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ApiKeyResponse(BaseModel):
    id: str
    object: Literal["api_key"] = "api_key"
    name: str
    prefix: str
    created_at: int
    last_used_at: int | None
    revoked: bool
    revoked_at: int | None


class ApiKeyCreatedResponse(ApiKeyResponse):
    secret: str
    secret_shown_once: Literal[True] = True


class ApiKeyListResponse(BaseModel):
    object: Literal["list"] = "list"
    data: list[ApiKeyResponse]


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


def _prevent_owner_response_storage(response: Response) -> None:
    """Owner metadata and one-time secrets must not enter HTTP caches."""

    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def developer_api_keys_capability() -> dict[str, Any] | None:
    """Compatibility wrapper around the canonical runtime verdict."""

    from app.capability_runtime import capability_by_id

    return capability_by_id("developer.api_keys")


def developer_response_capabilities() -> list[dict[str, Any]]:
    """Compatibility wrapper; no static ``live`` claims remain here."""

    from app.capability_runtime import capability_by_id

    return [
        capability
        for capability_id in ("developer.responses", "developer.chat_completions")
        if (capability := capability_by_id(capability_id)) is not None
    ]


@router.post(
    "/api/v1/developer/api-keys",
    status_code=201,
    dependencies=[Depends(_authorize_api_key_admin)],
    response_model=ApiKeyCreatedResponse,
)
@router.post(
    "/v1/api-keys",
    status_code=201,
    dependencies=[Depends(_authorize_api_key_admin)],
    response_model=ApiKeyCreatedResponse,
)
async def create_api_key(
    request: ApiKeyCreateRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    _prevent_owner_response_storage(response)
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
    from app.capability_runtime import try_record_capability_invocation

    try_record_capability_invocation(
        "developer.api_keys",
        succeeded=True,
        provider="kolibri-api-key-create",
        evidence_id=str(row.id),
    )
    return {**_public_api_key(row), "secret": plaintext, "secret_shown_once": True}


@router.get(
    "/api/v1/developer/api-keys",
    dependencies=[Depends(_authorize_api_key_admin)],
    response_model=ApiKeyListResponse,
)
@router.get(
    "/v1/api-keys",
    dependencies=[Depends(_authorize_api_key_admin)],
    response_model=ApiKeyListResponse,
)
async def list_api_keys(response: Response, db: Session = Depends(get_db)):
    _prevent_owner_response_storage(response)
    rows = db.query(PublicApiKeyDB).filter(
        PublicApiKeyDB.owner_scope == _owner_scope()
    ).order_by(PublicApiKeyDB.created_at.desc(), PublicApiKeyDB.id.desc()).all()
    return {"object": "list", "data": [_public_api_key(row) for row in rows]}


@router.delete(
    "/api/v1/developer/api-keys/{key_id}",
    dependencies=[Depends(_authorize_api_key_admin)],
    response_model=ApiKeyResponse,
)
@router.delete(
    "/v1/api-keys/{key_id}",
    dependencies=[Depends(_authorize_api_key_admin)],
    response_model=ApiKeyResponse,
)
async def revoke_api_key(
    key_id: str,
    response: Response,
    db: Session = Depends(get_db),
):
    _prevent_owner_response_storage(response)
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
    from app.capability_runtime import try_record_capability_invocation

    try_record_capability_invocation(
        "developer.api_keys",
        succeeded=True,
        provider="kolibri-api-key-revoke",
        evidence_id=str(row.id),
    )
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
    owner_scope: str | None = None,
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
            scope_id=owner_scope,
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
    actions = _public_actions(record.get("actions"))
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
    payload = {
        "id": record["id"],
        "object": "response",
        "created_at": record["created_at"],
        "status": record["status"],
        "model": "kolibri",
        "output": output,
        "output_text": content,
        "error": record.get("error"),
        "artifacts": [artifact] if isinstance(artifact, dict) else [],
        "actions": actions,
        "sources": _public_sources(record.get("sources")),
    }
    if "structured_output" in record:
        payload["output_parsed"] = record["structured_output"]
    if record.get("retry_of"):
        payload["retry_of"] = record["retry_of"]
    return payload


def _store(record: dict[str, Any]) -> None:
    record.setdefault("events", [])
    record.setdefault("last_sequence", 0)
    save_response_record(record)
    _records[record["id"]] = record
    _records.move_to_end(record["id"])
    while len(_records) > _MAX_RECORDS:
        response_id, _ = _records.popitem(last=False)
        for key, (_, stored_id) in list(_idempotency.items()):
            if stored_id == response_id:
                _idempotency.pop(key, None)


def _request_owner_scope(request: Request) -> str:
    scope = getattr(request.state, "kolibri_response_scope", None)
    if not isinstance(scope, str) or not scope:
        raise HTTPException(status_code=500, detail={"code": "response_scope_missing"})
    return scope


def _owned_record(response_id: str, owner_scope: str) -> dict[str, Any] | None:
    record = _records.get(response_id)
    if record is None:
        record = load_response_record(response_id)
        if record is not None:
            _records[response_id] = record
    if record is None or not hmac.compare_digest(
        str(record.get("owner_scope") or ""), owner_scope
    ):
        return None
    return record


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


def begin_public_response(
    messages: list[dict[str, str]],
    *,
    owner_scope: str = "internal:legacy",
    idempotency_key: str | None = None,
    request_hash: str | None = None,
) -> str:
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
        "owner_scope": owner_scope,
        "idempotency_key": idempotency_key,
        "request_hash": request_hash,
        "actions": [],
        "sources": [],
        "events": [],
        "last_sequence": 0,
    }
    _store(record)
    _append_event(record, "response.created", {"response": _public_response(record)})
    return response_id


def record_public_stream_chunk(
    response_id: str,
    chunk: dict[str, Any],
) -> list[dict[str, Any]]:
    """Persist one provider chunk and return the exact appended public events."""

    appended: list[dict[str, Any]] = []
    record = _records.get(response_id)
    if not record or record["status"] in _TERMINAL_RESPONSE_STATUSES:
        return appended
    if chunk.get("content"):
        delta = str(chunk["content"])
        record["content"] = str(record.get("content") or "") + delta
        appended.append(
            _append_event(record, "response.output_text.delta", {"delta": delta})
        )
    if isinstance(chunk.get("work_summary"), dict):
        summary = _sanitize_public_work_summary(response_id, chunk["work_summary"])
        if summary is not None:
            appended.append(
                _append_event(
                    record,
                    "response.work_summary.updated",
                    {"work_summary": summary},
                )
            )
    if isinstance(chunk.get("tool_event"), dict):
        tool = chunk["tool_event"]
        event_type = "response.tool.completed" if tool.get("type") == "tool.completed" else "response.tool.started"
        appended.append(
            _append_event(record, event_type, {
                "name": tool.get("tool"),
                "status": tool.get("status"),
            })
        )
    if isinstance(chunk.get("actions"), list):
        record["actions"] = _public_actions(chunk["actions"])
    if isinstance(chunk.get("sources"), list):
        record["sources"] = _public_sources(chunk["sources"])
        for source in record["sources"]:
            appended.append(
                _append_event(
                    record,
                    "response.source.added",
                    {
                        "citation": source["citation"],
                        "title": source["title"],
                        "url": source["url"],
                        "source": source,
                    },
                )
            )
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
                    appended.append(
                        _append_event(record, "response.artifact.ready", {
                            "artifact_type": "image",
                            "artifact_id": action["data"].get("id"),
                            "artifact": action["data"],
                        })
                    )
                    break
        status = str(chunk.get("status") or "completed")
        if status in _NONTERMINAL_RESPONSE_STATUSES:
            record["status"] = status
            record["error"] = None
            appended.append(
                _append_event(
                    record,
                    "response.status.updated",
                    {
                        "response": _public_response(record),
                        "status": status,
                        "actions": _public_actions(record.get("actions")),
                        "sources": _public_sources(record.get("sources")),
                    },
                )
            )
            return appended
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
        appended.append(
            _append_event(record, event_type, {
                "response": _public_response(record),
                "actions": _public_actions(record.get("actions")),
                "sources": _public_sources(record.get("sources")),
            })
        )
    return appended


def _request_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _structured_request_error(exc: StructuredOutputError) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"code": exc.code, "path": exc.path},
    )


def _structured_provider_error(exc: StructuredOutputError) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={
            "code": "structured_output_validation_failed",
            "reason_code": exc.code,
            "path": exc.path,
            "recoverable": True,
        },
    )


def _record_structured_verdict(
    *,
    succeeded: bool,
    response_id: str,
    provider: str,
    model: str = "",
    error_code: str | None = None,
) -> None:
    from app.capability_runtime import try_record_capability_invocation

    try_record_capability_invocation(
        "developer.structured_json",
        succeeded=succeeded,
        error_code=error_code,
        provider=provider,
        model=model or None,
        evidence_id=response_id,
    )


def _validate_structured_result(
    raw: str,
    spec: StructuredOutputSpec,
    *,
    response_id: str,
    provider: str,
    model: str = "",
) -> tuple[str, Any]:
    try:
        canonical, parsed = parse_and_validate(raw, spec)
    except StructuredOutputError as exc:
        _record_structured_verdict(
            succeeded=False,
            response_id=response_id,
            provider=provider,
            model=model,
            error_code=exc.code,
        )
        raise _structured_provider_error(exc) from exc
    _record_structured_verdict(
        succeeded=True,
        response_id=response_id,
        provider=provider,
        model=model,
    )
    return canonical, parsed


def _idempotent_record(
    key: str | None,
    request_hash: str,
    owner_scope: str,
) -> dict[str, Any] | None:
    if not key:
        return None
    existing = _idempotency.get((owner_scope, key))
    if not existing:
        record = find_idempotent_response(owner_scope, key)
        if record is None:
            return None
        previous_hash = str(record.get("request_hash") or "")
        response_id = str(record["id"])
        _records[response_id] = record
        _idempotency[(owner_scope, key)] = (previous_hash, response_id)
    else:
        previous_hash, response_id = existing
    if previous_hash != request_hash:
        raise HTTPException(status_code=409, detail={"code": "idempotency_conflict"})
    return _records.get(response_id) or load_response_record(response_id)


def _record_result(
    response_id: str,
    result: dict[str, Any],
    messages: list[dict[str, str]],
    *,
    owner_scope: str,
) -> dict[str, Any]:
    status = str(result.get("status") or "completed")
    if status in {"idle", "ready", "source_backed", "preliminary"}:
        status = "completed"
    elif status in _FAILED_RESULT_STATUSES:
        status = "failed"
    record = _records.get(response_id) or load_response_record(response_id) or {}
    # Cancellation is a terminal user decision. A provider that finishes (or
    # fails) after the cancellation transition must not replace it.
    if record.get("status") == "cancelled":
        return record
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
        "actions": _public_actions(result.get("actions")),
        "upstream_response_id": result.get("response_id"),
        "provider_route": result.get("provider"),
        "messages": messages,
        "owner_scope": owner_scope,
    })
    had_events = bool(record.get("events"))
    _store(record)
    if not had_events:
        _append_event(record, "response.created", {"response": _public_response(record)})
    if record["content"]:
        _append_event(record, "response.output_text.delta", {"delta": record["content"]})
    if isinstance(record.get("artifact"), dict):
        _append_event(record, "response.artifact.ready", {
            "artifact_type": "image",
            "artifact_id": record["artifact"].get("id"),
            "artifact": record["artifact"],
        })
    terminal = f"response.{record['status']}" if record["status"] in _TERMINAL_RESPONSE_STATUSES else "response.status.updated"
    _append_event(record, terminal, {
        "response": _public_response(record),
        "status": record["status"],
        "actions": _public_actions(record.get("actions")),
    })
    return record


async def _execute_response(
    request: ResponsesRequest,
    *,
    idempotency_key: str | None,
    owner_scope: str,
) -> tuple[
    dict[str, Any],
    list[dict[str, str]],
    dict[str, Any] | None,
    str,
    StructuredOutputSpec | None,
]:
    _ensure_public_model(request.model)
    try:
        structured = responses_spec(request.text)
    except StructuredOutputError as exc:
        raise _structured_request_error(exc) from exc
    messages = _normalise_messages(request.input)
    previous_upstream_id = None
    if request.previous_response_id:
        previous = _owned_record(request.previous_response_id, owner_scope)
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
        "text": request.text,
    })
    existing = _idempotent_record(idempotency_key, fingerprint, owner_scope)
    if existing:
        return existing, messages, policy, fingerprint, structured
    return {}, messages, policy, fingerprint, structured


async def execute_kolibri_response(
    request: ResponsesRequest,
    *,
    idempotency_key: str | None = None,
    owner_scope: str = "internal:service",
) -> dict[str, Any]:
    """Execute one non-streaming response through the canonical provider path.

    Browser, API and non-HTTP channel adapters (currently Telegram) call this
    function instead of reimplementing provider selection, image routing or
    response recording.  The returned value is the internal response record;
    callers must expose only a channel-appropriate sanitized representation.
    """

    _validate_idempotency_key(idempotency_key)
    existing, messages, policy, fingerprint, structured = await _execute_response(
        request,
        idempotency_key=idempotency_key,
        owner_scope=owner_scope,
    )
    if existing:
        return existing

    inflight_key: tuple[str, str] | None = None
    inflight_future: Future[dict[str, Any]] | None = None
    inflight_leader = True
    if idempotency_key:
        inflight_key = (owner_scope, idempotency_key)
        with _inflight_lock:
            current = _inflight.get(inflight_key)
            if current is None:
                inflight_future = Future()
                _inflight[inflight_key] = (fingerprint, inflight_future)
            else:
                current_fingerprint, inflight_future = current
                if current_fingerprint != fingerprint:
                    raise HTTPException(
                        status_code=409,
                        detail={"code": "idempotency_conflict"},
                    )
                inflight_leader = False
        if not inflight_leader:
            return await asyncio.wrap_future(inflight_future)

    try:
        try:
            response_id = begin_public_response(
                messages,
                owner_scope=owner_scope,
                idempotency_key=idempotency_key,
                request_hash=fingerprint if idempotency_key else None,
            )
        except ResponseIdempotencyConflict:
            existing = _idempotent_record(idempotency_key, fingerprint, owner_scope)
            if existing is None:
                raise
            if inflight_future is not None and not inflight_future.done():
                inflight_future.set_result(existing)
            return existing
        if idempotency_key:
            _idempotency[(owner_scope, idempotency_key)] = (fingerprint, response_id)
        task_type = "analyze" if policy and policy["mode"] == "deep" else "fast" if policy else "chat"
        result = await _image_result_if_requested(
            messages,
            policy,
            run_id=response_id,
            owner_scope=owner_scope,
        )
        if structured and result is not None:
            raise HTTPException(
                status_code=422,
                detail={"code": "structured_output_incompatible_with_image"},
            )
        if result is None:
            result = await ai_provider.chat_completion(
                messages,
                task_type=task_type,
                previous_response_id=(
                    (_owned_record(request.previous_response_id, owner_scope) or {}).get("upstream_response_id")
                    if request.previous_response_id else None
                ),
                background=request.background,
                policy=policy,
                idempotency_key=idempotency_key,
                system=structured_instruction(structured) if structured else None,
                raw_json_output=structured is not None,
            )
        if structured and str(result.get("status") or "") not in _FAILED_RESULT_STATUSES:
            result = dict(result)
            canonical, parsed = _validate_structured_result(
                str(result.get("content") or ""),
                structured,
                response_id=response_id,
                provider=str(result.get("provider") or "kolibri"),
                model=str(result.get("model") or ""),
            )
            result["content"] = canonical
            result["structured_output"] = parsed
        record = _record_result(
            response_id,
            result,
            messages,
            owner_scope=owner_scope,
        )
        if structured and "structured_output" in result:
            record["structured_output"] = result["structured_output"]
            record["structured_request"] = request.text
            _store(record)
        if record.get("status") == "completed":
            from app.capability_runtime import try_record_capability_invocation

            try_record_capability_invocation(
                "developer.responses",
                succeeded=True,
                provider=str(result.get("provider") or "kolibri"),
                model=str(result.get("model") or "kolibri"),
                evidence_id=response_id,
            )
        if inflight_future is not None and not inflight_future.done():
            inflight_future.set_result(record)
        return record
    except BaseException as exc:
        response_id = locals().get("response_id")
        if isinstance(response_id, str):
            pending = _owned_record(response_id, owner_scope)
            if pending is not None and pending.get("status") not in _TERMINAL_RESPONSE_STATUSES:
                _record_result(
                    response_id,
                    {
                        "content": "",
                        "status": "failed",
                        "error_code": "response_execution_failed",
                        "recoverable": True,
                    },
                    messages,
                    owner_scope=owner_scope,
                )
        if inflight_future is not None and not inflight_future.done():
            inflight_future.set_exception(exc)
        raise
    finally:
        if inflight_key is not None and inflight_future is not None:
            with _inflight_lock:
                current = _inflight.get(inflight_key)
                if current is not None and current[1] is inflight_future:
                    _inflight.pop(inflight_key, None)


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
        return await _streaming_response(
            request,
            idempotency_key,
            owner_scope=_request_owner_scope(http_request),
        )
    record = await execute_kolibri_response(
        request,
        idempotency_key=idempotency_key,
        owner_scope=_request_owner_scope(http_request),
    )
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
    return await _streaming_response(
        request,
        idempotency_key,
        owner_scope=_request_owner_scope(http_request),
    )


async def _streaming_response(
    request: ResponsesRequest,
    idempotency_key: str | None,
    *,
    owner_scope: str,
):
    existing, messages, policy, fingerprint, structured = await _execute_response(
        request,
        idempotency_key=idempotency_key,
        owner_scope=owner_scope,
    )
    if existing:
        response_id = str(existing["id"])
    else:
        try:
            response_id = begin_public_response(
                messages,
                owner_scope=owner_scope,
                idempotency_key=idempotency_key,
                request_hash=fingerprint if idempotency_key else None,
            )
        except ResponseIdempotencyConflict:
            existing = _idempotent_record(idempotency_key, fingerprint, owner_scope)
            if existing is None:
                raise
            response_id = str(existing["id"])
    if structured and not existing:
        _records[response_id]["structured_request"] = request.text
        _store(_records[response_id])
    if idempotency_key and not existing:
        _idempotency[(owner_scope, idempotency_key)] = (fingerprint, response_id)
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
            yield _sse(existing_event, {
                "type": existing_event,
                "response": created,
                "actions": _public_actions(existing.get("actions")),
            })
            return

        image_result = await _image_result_if_requested(
            messages,
            policy,
            run_id=response_id,
            owner_scope=owner_scope,
        )
        if image_result is not None:
            if structured:
                failure = {
                    "content": "",
                    "done": True,
                    "status": "failed",
                    "error_code": "structured_output_incompatible_with_image",
                    "recoverable": False,
                }
                record_public_stream_chunk(response_id, failure)
                record = _records[response_id]
                yield _sse("response.failed", {
                    "type": "response.failed",
                    "response": _public_response(record),
                })
                return
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
            if record["status"] == "completed":
                from app.capability_runtime import try_record_capability_invocation
                try_record_capability_invocation(
                    "developer.responses",
                    succeeded=True,
                    provider=str(image_result.get("provider") or "kolibri"),
                    model=str(image_result.get("model") or "kolibri"),
                    evidence_id=response_id,
                )
            yield _sse(event_type, {
                "type": event_type,
                "response": _public_response(record),
                "actions": _public_actions(record.get("actions")),
            })
            return

        text_parts: list[str] = []
        final_internal: dict[str, Any] = {}
        async for chunk in _safe_provider_stream(
            messages,
            task_type=task_type,
            previous_response_id=(
                (_owned_record(request.previous_response_id, owner_scope) or {}).get("upstream_response_id")
                if request.previous_response_id else None
            ),
            background=request.background,
            policy=policy,
            idempotency_key=idempotency_key,
            run_id=response_id,
            system=structured_instruction(structured) if structured else None,
            raw_json_output=structured is not None,
        ):
            if chunk.get("content"):
                delta = str(chunk["content"])
                text_parts.append(delta)
                if not structured:
                    persisted_events = record_public_stream_chunk(response_id, chunk)
                    yield _sse("response.output_text.delta", {
                        "type": "response.output_text.delta",
                        "response_id": response_id,
                        "delta": delta,
                    })
                    for persisted_event in persisted_events:
                        if persisted_event.get("type") == "response.work_summary.updated":
                            yield _sse(
                                "response.work_summary.updated",
                                persisted_event,
                            )
            elif isinstance(chunk.get("work_summary"), dict):
                persisted_events = record_public_stream_chunk(response_id, chunk)
                for persisted_event in persisted_events:
                    if persisted_event.get("type") == "response.work_summary.updated":
                        # Live delivery and durable replay share this exact
                        # nested envelope, including response_id + sequence.
                        yield _sse("response.work_summary.updated", persisted_event)
            elif isinstance(chunk.get("tool_event"), dict):
                record_public_stream_chunk(response_id, chunk)
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
                if (
                    not structured
                    and not chunk.get("content")
                    and not isinstance(chunk.get("work_summary"), dict)
                    and not isinstance(chunk.get("tool_event"), dict)
                ):
                    record_public_stream_chunk(response_id, chunk)
        if not final_internal:
            final_internal = {
                "content": "",
                "done": True,
                "status": "failed",
                "error_code": "provider_stream_failed",
            }
            if not structured:
                record_public_stream_chunk(response_id, final_internal)
        if structured:
            final_status = str(final_internal.get("status") or "completed")
            if final_status not in _FAILED_RESULT_STATUSES and final_status != "cancelled":
                try:
                    canonical, parsed = _validate_structured_result(
                        "".join(text_parts),
                        structured,
                        response_id=response_id,
                        provider=str(final_internal.get("provider") or "kolibri"),
                        model=str(final_internal.get("model") or ""),
                    )
                except HTTPException as exc:
                    detail = exc.detail if isinstance(exc.detail, dict) else {}
                    failure = {
                        "content": "",
                        "done": True,
                        "status": "failed",
                        "error_code": "structured_output_validation_failed",
                        "recoverable": True,
                    }
                    record_public_stream_chunk(response_id, failure)
                    record = _records[response_id]
                    yield _sse("response.failed", {
                        "type": "response.failed",
                        "response": _public_response(record),
                        "error": {
                            "code": "structured_output_validation_failed",
                            "reason_code": detail.get("reason_code"),
                            "path": detail.get("path"),
                        },
                    })
                    return
                record_public_stream_chunk(
                    response_id,
                    {"content": canonical, "done": False},
                )
                record = _records[response_id]
                record["structured_output"] = parsed
                _store(record)
                yield _sse("response.output_text.delta", {
                    "type": "response.output_text.delta",
                    "response_id": response_id,
                    "delta": canonical,
                })
            record_public_stream_chunk(
                response_id,
                {**final_internal, "content": "", "done": True},
            )
        record = _records[response_id]
        if record["status"] == "completed":
            from app.capability_runtime import try_record_capability_invocation
            try_record_capability_invocation(
                "developer.responses",
                succeeded=True,
                provider=str(final_internal.get("provider") or "kolibri"),
                model=str(final_internal.get("model") or "kolibri"),
                evidence_id=response_id,
            )
        event_type = (
            f"response.{record['status']}"
            if record["status"] in _TERMINAL_RESPONSE_STATUSES
            else "response.status.updated"
        )
        yield _sse(event_type, {
            "type": event_type,
            "response": _public_response(record),
            "status": record["status"],
            "actions": _public_actions(record.get("actions")),
        })

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


async def _safe_provider_stream(*args: Any, **kwargs: Any):
    """Convert provider transport failures into one bounded terminal event."""

    try:
        async for chunk in ai_provider.chat_completion_stream(*args, **kwargs):
            yield chunk
    except asyncio.CancelledError:
        raise
    except Exception:
        # Do not leak provider URLs, credentials or transport exception text.
        # The canonical response recorder turns this into response.failed.
        yield {
            "content": "",
            "done": True,
            "status": "failed",
            "error_code": "provider_stream_failed",
            "recoverable": True,
        }


def _sse(event_type: str, payload: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/api/v1/responses/{response_id}", include_in_schema=False, dependencies=_PUBLIC_AUTH)
@router.get("/v1/responses/{response_id}", dependencies=_PUBLIC_AUTH)
async def get_public_response(response_id: str, request: Request):
    record = _owned_record(response_id, _request_owner_scope(request))
    if not record:
        raise HTTPException(status_code=404, detail={"code": "response_not_found"})
    if record["status"] in _NONTERMINAL_RESPONSE_STATUSES and record.get("provider_route") == "openai_codex":
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
async def public_response_events(
    response_id: str,
    request: Request,
    starting_after: int = 0,
):
    owner_scope = _request_owner_scope(request)
    if _owned_record(response_id, owner_scope) is None:
        raise HTTPException(status_code=404, detail={"code": "response_not_found"})

    async def events():
        sequence = max(0, int(starting_after))
        while True:
            record = _owned_record(response_id, owner_scope)
            if not record:
                return
            if record["status"] in _NONTERMINAL_RESPONSE_STATUSES and record.get("provider_route") == "openai_codex":
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
async def cancel_public_response(response_id: str, request: Request):
    record = _owned_record(response_id, _request_owner_scope(request))
    if not record:
        raise HTTPException(status_code=404, detail={"code": "response_not_found"})
    if record["status"] not in _TERMINAL_RESPONSE_STATUSES:
        from app.codex_cli_provider import cancel_codex_cli_run
        from app.codex_cli_image_provider import cancel_codex_cli_image_run

        # Commit the scope-checked terminal transition before awaiting process
        # or provider I/O. Provider streams observe this status and cannot
        # overwrite it while cancellation is in flight.
        record["status"] = "cancelled"
        record["error"] = None
        _append_event(record, "response.cancelled", {"response": _public_response(record)})

        # Cleanup is best effort. The public state is already terminal, so a
        # transport error must not turn cancel into a 5xx or let a late result
        # win the race.
        cancel_operations = [
            cancel_codex_cli_run(response_id),
            cancel_codex_cli_image_run(response_id),
        ]
        upstream_id = record.get("upstream_response_id")
        if upstream_id and record.get("provider_route") == "openai_codex":
            cancel_operations.append(
                cancel_response(ai_provider.PROVIDERS["openai_codex"], upstream_id)
            )
        await asyncio.gather(*cancel_operations, return_exceptions=True)
    from app.capability_runtime import try_record_capability_invocation

    try_record_capability_invocation(
        "response.cancel",
        succeeded=True,
        provider="openai-compatible-responses",
        evidence_id=response_id,
    )
    return _public_response(record)


@router.post(
    "/api/v1/responses/{response_id}/retry",
    include_in_schema=False,
    dependencies=_PUBLIC_AUTH,
)
@router.post("/v1/responses/{response_id}/retry", dependencies=_PUBLIC_AUTH)
async def retry_public_response(
    response_id: str,
    http_request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Create a fresh response attempt from one terminal response context."""

    from app.capability_runtime import try_record_capability_invocation
    from app.rate_limiter import chat_limiter, check_rate_limit

    await check_rate_limit(http_request, chat_limiter)
    _validate_idempotency_key(idempotency_key)
    owner_scope = _request_owner_scope(http_request)
    source = _owned_record(response_id, owner_scope)
    if source is None:
        raise HTTPException(status_code=404, detail={"code": "response_not_found"})
    if source.get("status") not in {"completed", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail={"code": "response_not_terminal"})
    messages = source.get("messages")
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=409, detail={"code": "response_context_unavailable"})

    scoped_key = None
    if idempotency_key:
        scoped_digest = hashlib.sha256(
            f"{response_id}\0{idempotency_key}".encode()
        ).hexdigest()
        scoped_key = f"retry:{scoped_digest}"
    retry_request = ResponsesRequest(
        model="kolibri",
        input=messages,
        text=source.get("structured_request"),
    )
    record = await execute_kolibri_response(
        retry_request,
        idempotency_key=scoped_key,
        owner_scope=owner_scope,
    )
    record["retry_of"] = response_id
    _store(record)
    try_record_capability_invocation(
        "response.retry",
        succeeded=True,
        provider="openai-compatible-responses",
        evidence_id=record["id"],
    )
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
    try:
        structured = chat_spec(request.response_format)
    except StructuredOutputError as exc:
        raise _structured_request_error(exc) from exc
    policy = _policy(request.policy)
    task_type = "analyze" if policy and policy["mode"] == "deep" else "fast" if policy else "chat"
    completion_id = f"chatcmpl_{secrets.token_hex(12)}"
    image_result = await _image_result_if_requested(
        messages,
        policy,
        run_id=completion_id,
        owner_scope=_request_owner_scope(http_request),
    )
    if image_result is not None and image_result.get("status") in _FAILED_RESULT_STATUSES:
        raise HTTPException(status_code=503, detail={
            "code": image_result.get("error_code") or "capability_unavailable",
            "capability": image_result.get("capability"),
            "recoverable": image_result.get("recoverable") is True,
        })
    if structured and image_result is not None:
        raise HTTPException(
            status_code=422,
            detail={"code": "structured_output_incompatible_with_image"},
        )
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
                from app.capability_runtime import record_capability_invocation
                record_capability_invocation(
                    "developer.chat_completions",
                    succeeded=True,
                    provider=str(image_result.get("provider") or "kolibri"),
                    model=str(image_result.get("model") or "kolibri"),
                    evidence_id=completion_id,
                )
                yield "data: [DONE]\n\n"
                return
            text_parts: list[str] = []
            final_chunk: dict[str, Any] = {}
            async for chunk in _safe_provider_stream(
                messages,
                task_type=task_type,
                policy=policy,
                idempotency_key=idempotency_key,
                system=structured_instruction(structured) if structured else None,
                raw_json_output=structured is not None,
            ):
                if chunk.get("content"):
                    text_parts.append(str(chunk["content"]))
                    if structured:
                        continue
                    failed = (
                        str(chunk.get("status") or "") in _FAILED_RESULT_STATUSES
                        or str(chunk.get("status") or "") == "cancelled"
                    )
                    payload = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": "kolibri",
                        "choices": [{"index": 0, "delta": {"content": chunk["content"]}, "finish_reason": None}],
                    }
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if chunk.get("done"):
                    final_chunk = chunk
                    if structured:
                        continue
                    payload = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": "kolibri",
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "finish_reason": "error" if failed else "stop",
                        }],
                        **(
                            {"error": {"code": chunk.get("error_code") or "provider_stream_failed"}}
                            if failed else {}
                        ),
                    }
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    if str(chunk.get("status") or "") not in _FAILED_RESULT_STATUSES:
                        from app.capability_runtime import record_capability_invocation
                        record_capability_invocation(
                            "developer.chat_completions",
                            succeeded=True,
                            provider=str(chunk.get("provider") or "kolibri"),
                            model=str(chunk.get("model") or "kolibri"),
                            evidence_id=completion_id,
                        )
            if structured:
                status = str(final_chunk.get("status") or "failed")
                if status in _FAILED_RESULT_STATUSES or status == "cancelled":
                    payload = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": "kolibri",
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
                        "error": {"code": "provider_stream_failed"},
                    }
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                else:
                    try:
                        canonical, parsed = _validate_structured_result(
                            "".join(text_parts),
                            structured,
                            response_id=completion_id,
                            provider=str(final_chunk.get("provider") or "kolibri"),
                            model=str(final_chunk.get("model") or ""),
                        )
                    except HTTPException as exc:
                        detail = exc.detail if isinstance(exc.detail, dict) else {}
                        payload = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": "kolibri",
                            "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
                            "error": detail,
                        }
                        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    else:
                        payload = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": "kolibri",
                            "choices": [{
                                "index": 0,
                                "delta": {"content": canonical, "parsed": parsed},
                                "finish_reason": None,
                            }],
                        }
                        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
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
        system=structured_instruction(structured) if structured else None,
        raw_json_output=structured is not None,
    )
    parsed_output: Any = None
    if structured and str(result.get("status") or "") not in _FAILED_RESULT_STATUSES:
        result = dict(result)
        canonical, parsed_output = _validate_structured_result(
            str(result.get("content") or ""),
            structured,
            response_id=completion_id,
            provider=str(result.get("provider") or "kolibri"),
            model=str(result.get("model") or ""),
        )
        result["content"] = canonical
    if str(result.get("status") or "") not in _FAILED_RESULT_STATUSES:
        from app.capability_runtime import record_capability_invocation
        record_capability_invocation(
            "developer.chat_completions",
            succeeded=True,
            provider=str(result.get("provider") or "kolibri"),
            model=str(result.get("model") or "kolibri"),
            evidence_id=completion_id,
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
                **({"parsed": parsed_output} if structured else {}),
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
