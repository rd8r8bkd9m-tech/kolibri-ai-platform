"""Official OpenAI Responses API adapter.

The public Kolibri stream receives only output text, observable tool lifecycle
events, and provider-authored reasoning *summaries*.  Raw reasoning content is
never forwarded.  Capability availability is promoted to ``live`` only after
an actual completed output item has been observed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Iterable
from urllib.parse import urlparse

import httpx


_RESPONSE_ID = re.compile(r"^resp_[A-Za-z0-9_-]+$")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
_REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}
_REASONING_CONTEXTS = {"auto", "all_turns", "current_turn"}
_REASONING_SUMMARIES = {"auto", "concise", "detailed"}
_MAX_REASONING_BUFFER_CHARS = 2_400
_MAX_PUBLIC_REASONING_SUMMARY_CHARS = 600
_SECRET_IN_SUMMARY = re.compile(
    r"(?i)(?:bearer\s+\S+|(?:sk|koli)[_-][A-Za-z0-9._-]{12,}|"
    r"(?:api[_ -]?key|token|password|secret)\s*[:=]\s*\S+|"
    r"https?://\S+|/(?:Users|home|srv|etc)/\S+|"
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b|"
    r"\b(?:home|control[\s_-]*plane|"
    r"(?:node|agent)(?:[\s_-]*\d+|[\s_-]+[A-Za-z0-9._-]+)|"
    r"mimo|deepseek|codex|kimi|openai|anthropic|claude|gemini|"
    r"gpt-[A-Za-z0-9._-]+)\b)"
)
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
_PUBLIC_WORK_STATUSES = {
    "active",
    "completed",
    "failed",
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
_FORBIDDEN_WORK_SUMMARY_KEYS = {
    "reasoning",
    "reasoning_content",
    "reasoning_text",
    "prompt",
    "prompts",
    "tool_arguments",
    "credentials",
}
_TOOL_ITEM_CAPABILITY = {
    "web_search_call": "web_search",
    "file_search_call": "file_search",
    "code_interpreter_call": "code_interpreter",
    "image_generation_call": "image_generation",
    "mcp_list_tools": "remote_mcp",
    "mcp_call": "remote_mcp",
    "computer_call": "computer",
    "multi_agent_call": "multi_agent",
}
_TOOL_LABELS = {
    "web_search": "Веб-поиск",
    "file_search": "Поиск по файлам",
    "code_interpreter": "Вычисления",
    "image_generation": "Генерация изображения",
    "remote_mcp": "Подключённый MCP-инструмент",
    "computer": "Управление компьютером",
    "multi_agent": "Субагенты",
}
_tool_probe_state: dict[str, dict[str, str | None]] = {}


def _enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def _reasoning_config() -> dict[str, str]:
    effort = os.getenv("OPENAI_REASONING_EFFORT", "medium").strip().lower()
    context = os.getenv("OPENAI_REASONING_CONTEXT", "auto").strip().lower()
    summary = os.getenv("OPENAI_REASONING_SUMMARY", "auto").strip().lower()
    mode = os.getenv("OPENAI_REASONING_MODE", "").strip().lower()
    result = {
        "effort": effort if effort in _REASONING_EFFORTS else "medium",
        "context": context if context in _REASONING_CONTEXTS else "auto",
        "summary": summary if summary in _REASONING_SUMMARIES else "auto",
    }
    if mode == "pro":
        result["mode"] = "pro"
    return result


def _reasoning_summary_identity(event: dict[str, Any]) -> tuple[str, str, str]:
    """Return stable opaque IDs for one official summary item.

    Upstream item IDs are deliberately not exposed.  The output and summary
    indices keep fragmented delta and done events attached to the same public
    excerpt when an item ID is absent.
    """

    source_key = ":".join(
        (
            str(event.get("item_id") or "item"),
            str(event.get("output_index") or 0),
            str(event.get("summary_index") or 0),
        )
    )
    digest = hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:24]
    return source_key, f"summary_{digest}", f"step_{digest}"


def _sanitize_reasoning_summary(value: str) -> str:
    """Bound an official provider summary without exposing secret-like data."""

    cleaned = _SECRET_IN_SUMMARY.sub("[скрыто]", value)
    cleaned = " ".join(cleaned.split())
    return cleaned[:_MAX_PUBLIC_REASONING_SUMMARY_CHARS].strip()


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


def _public_work_summary_identity(
    event: dict[str, Any],
    summary: dict[str, Any],
    *,
    stage: str,
) -> tuple[str, str | None]:
    response_id = str(event.get("response_id") or "")
    upstream_summary_id = str(summary.get("summary_id") or "")
    upstream_step_id = str(summary.get("step_id") or "")
    upstream_item_id = str(event.get("item_id") or "")
    if upstream_summary_id:
        source_key = f"{response_id}:summary:{upstream_summary_id}"
    elif upstream_step_id:
        source_key = f"{response_id}:step:{upstream_step_id}"
    elif upstream_item_id:
        source_key = f"{response_id}:item:{upstream_item_id}"
    else:
        source_key = ":".join(
            (
                response_id,
                "stage",
                stage,
                str(summary.get("artifact_type") or ""),
                str(summary.get("artifact_id") or ""),
            )
        )
    digest = hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:24]
    step_id = f"step_{digest}"
    summary_id = (
        f"summary_{digest}"
        if stage == "reasoning_summary" or summary.get("summary_id") is not None
        else None
    )
    return step_id, summary_id


def _sanitize_upstream_work_summary(
    event: dict[str, Any],
    value: dict[str, Any],
) -> dict[str, Any] | None:
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

    summary = _sanitize_reasoning_summary(str(value.get("summary") or ""))
    if not summary:
        return None

    step_id, summary_id = _public_work_summary_identity(event, value, stage=stage)
    public: dict[str, Any] = {
        "kind": "reasoning_excerpt" if stage == "reasoning_summary" else "stage",
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


def _remote_mcp_tool() -> dict[str, Any] | None:
    server_url = os.getenv("OPENAI_MCP_SERVER_URL", "").strip()
    server_label = os.getenv("OPENAI_MCP_SERVER_LABEL", "kolibri_mcp").strip()
    allowed_tools = _csv("OPENAI_MCP_ALLOWED_TOOLS")
    parsed = urlparse(server_url)
    if parsed.scheme != "https" or not parsed.netloc or not server_label or not allowed_tools:
        return None
    return {
        "type": "mcp",
        "server_label": server_label,
        "server_url": server_url,
        "allowed_tools": allowed_tools,
        "require_approval": "always",
    }


def _allowed_capabilities(policy: dict[str, Any] | None) -> set[str] | None:
    if policy is None:
        return None
    allowed = policy.get("allowed_capabilities")
    if not isinstance(allowed, list):
        return set()
    return {str(item) for item in allowed if isinstance(item, str)}


def configured_tools(policy: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return policy-permitted tool declarations, without claiming health."""
    tools: list[dict[str, Any]] = []
    allowed = _allowed_capabilities(policy)

    def permitted(capability: str) -> bool:
        return allowed is None or f"openai.{capability}" in allowed

    if _enabled("OPENAI_WEB_SEARCH_ENABLED", True) and permitted("web_search"):
        tools.append({"type": "web_search"})
    vector_store_ids = _csv("OPENAI_VECTOR_STORE_IDS")
    if vector_store_ids and permitted("file_search"):
        tools.append({"type": "file_search", "vector_store_ids": vector_store_ids})
    if _enabled("OPENAI_CODE_INTERPRETER_ENABLED", True) and permitted("code_interpreter"):
        tools.append({"type": "code_interpreter", "container": {"type": "auto"}})
    if _enabled("OPENAI_IMAGE_GENERATION_ENABLED", True) and permitted("image_generation"):
        tools.append({"type": "image_generation"})
    mcp_tool = _remote_mcp_tool()
    if mcp_tool and permitted("remote_mcp"):
        tools.append(mcp_tool)
    if (
        _enabled("OPENAI_COMPUTER_ENABLED")
        and _enabled("OPENAI_COMPUTER_SANDBOX_ATTESTED")
        and permitted("computer")
    ):
        tools.append({"type": "computer"})
    return tools


def _configured_capability_ids() -> set[str]:
    configured = {
        {
            "web_search": "web_search",
            "file_search": "file_search",
            "code_interpreter": "code_interpreter",
            "image_generation": "image_generation",
            "mcp": "remote_mcp",
            "computer": "computer",
        }[tool["type"]]
        for tool in configured_tools()
    }
    if _enabled("OPENAI_MULTI_AGENT_BETA_ENABLED"):
        configured.add("multi_agent")
    return configured


def _mark_tool_verified(capability: str) -> None:
    _tool_probe_state[capability] = {
        "status": "live",
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def reset_tool_probe_state() -> None:
    """Test helper; production availability is otherwise process-local."""
    _tool_probe_state.clear()


def responses_capability_manifest() -> dict[str, Any]:
    configured = _configured_capability_ids()
    capabilities = []
    for capability in (
        "web_search",
        "file_search",
        "code_interpreter",
        "image_generation",
        "remote_mcp",
        "computer",
        "multi_agent",
    ):
        is_configured = capability in configured
        probe = _tool_probe_state.get(capability, {})
        live = is_configured and probe.get("status") == "live"
        status = "live" if live else "unverified" if is_configured else "unavailable"
        capabilities.append({
            "id": f"openai.{capability}",
            "name": _TOOL_LABELS[capability],
            "kind": "provider_tool",
            "configured": is_configured,
            "status": status,
            "invocable": live,
            "verified_at": probe.get("verified_at") if live else None,
            "source": {"type": "live_invocation" if live else "configuration"},
            "beta": capability == "multi_agent",
        })
    if any(item["status"] == "live" for item in capabilities):
        status = "live"
    elif any(item["configured"] for item in capabilities):
        status = "partial"
    else:
        status = "unavailable"
    return {
        "schema_version": "2026-07-13",
        "status": status,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "capabilities": capabilities,
    }


def _split_messages(messages: Iterable[dict[str, Any]], explicit_system: str | None) -> tuple[str | None, list[dict[str, Any]]]:
    instructions: list[str] = [explicit_system] if explicit_system else []
    input_items: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "user")
        content = message.get("content")
        if role in {"system", "developer"}:
            if isinstance(content, str) and content.strip():
                instructions.append(content)
            continue
        input_items.append({"role": role, "content": content if isinstance(content, str) else str(content or "")})
    return "\n\n".join(instructions) or None, input_items


def build_response_payload(
    provider: dict[str, Any],
    messages: Iterable[dict[str, Any]],
    *,
    system: str | None = None,
    stream: bool = False,
    background: bool = False,
    previous_response_id: str | None = None,
    policy: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    instructions, input_items = _split_messages(messages, system)
    payload: dict[str, Any] = {
        "model": str(provider.get("model") or "gpt-5.6-sol"),
        "input": input_items,
        "store": True,
        "stream": stream,
        "reasoning": _reasoning_config(),
    }
    if policy:
        # Client policy may reduce server capability and select one of two
        # bounded UX modes.  It cannot enable a tool or a reasoning mode that
        # the server did not configure.
        mode = str(policy.get("mode") or "fast")
        payload["reasoning"]["effort"] = "high" if mode == "deep" else "low"
        payload["reasoning"]["summary"] = "auto" if mode == "deep" else "concise"
        background = background or (mode == "deep" and bool(policy.get("background")))
    if instructions:
        payload["instructions"] = instructions
    if background:
        payload["background"] = True
    if previous_response_id:
        if not _RESPONSE_ID.fullmatch(previous_response_id):
            raise ValueError("invalid_previous_response_id")
        payload["previous_response_id"] = previous_response_id
    tools = configured_tools(policy)
    if tools:
        payload["tools"] = tools

    headers = {"Content-Type": "application/json"}
    key = str(provider.get("key") or "")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if idempotency_key:
        if not _IDEMPOTENCY_KEY.fullmatch(idempotency_key):
            raise ValueError("invalid_idempotency_key")
        headers["Idempotency-Key"] = idempotency_key
    allowed = _allowed_capabilities(policy)
    multi_agent_permitted = allowed is None or "openai.multi_agent" in allowed
    if _enabled("OPENAI_MULTI_AGENT_BETA_ENABLED") and multi_agent_permitted:
        headers["OpenAI-Beta"] = "responses_multi_agent=v1"
        payload["multi_agent"] = {
            "enabled": True,
            "max_concurrent_subagents": max(1, min(10, int(os.getenv("OPENAI_MULTI_AGENT_MAX_CONCURRENCY", "3")))),
        }
    return payload, headers


def _tool_event(item: dict[str, Any], phase: str) -> dict[str, Any] | None:
    item_type = str(item.get("type") or "")
    capability = _TOOL_ITEM_CAPABILITY.get(item_type)
    if not capability:
        return None
    if phase == "completed" and str(item.get("status") or "completed") == "completed":
        _mark_tool_verified(capability)
    return {
        "type": f"tool.{phase}",
        "tool": capability,
        "label": _TOOL_LABELS[capability],
        "call_id": str(item.get("id") or item.get("call_id") or ""),
        "status": "active" if phase == "started" else str(item.get("status") or "completed"),
    }


def parse_response(payload: dict[str, Any]) -> dict[str, Any]:
    text_parts: list[str] = []
    summary_parts: list[str] = []
    tool_events: list[dict[str, Any]] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            for content in item.get("content") or []:
                if isinstance(content, dict) and content.get("type") == "output_text":
                    text_parts.append(str(content.get("text") or ""))
        elif item.get("type") == "reasoning":
            for summary in item.get("summary") or []:
                if isinstance(summary, dict) and summary.get("type") == "summary_text":
                    summary_parts.append(str(summary.get("text") or ""))
        event = _tool_event(item, "completed")
        if event:
            tool_events.append(event)
    return {
        "id": str(payload.get("id") or ""),
        "status": str(payload.get("status") or "completed"),
        "model": str(payload.get("model") or ""),
        "content": "".join(text_parts),
        "reasoning_summary": "".join(summary_parts),
        "tool_events": tool_events,
    }


async def create_response(
    provider: dict[str, Any],
    messages: Iterable[dict[str, Any]],
    *,
    system: str | None = None,
    background: bool = False,
    previous_response_id: str | None = None,
    policy: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    payload, headers = build_response_payload(
        provider,
        messages,
        system=system,
        background=background,
        previous_response_id=previous_response_id,
        policy=policy,
        idempotency_key=idempotency_key,
    )
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
        response = await client.post(str(provider["url"]), json=payload, headers=headers)
        response.raise_for_status()
        return parse_response(response.json())


async def stream_response(
    provider: dict[str, Any],
    messages: Iterable[dict[str, Any]],
    *,
    system: str | None = None,
    background: bool = False,
    previous_response_id: str | None = None,
    policy: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    payload, headers = build_response_payload(
        provider,
        messages,
        system=system,
        stream=True,
        background=background,
        previous_response_id=previous_response_id,
        policy=policy,
        idempotency_key=idempotency_key,
    )
    summary_buffers: dict[str, str] = {}
    work_summary_sequence = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
        async with client.stream("POST", str(provider["url"]), json=payload, headers=headers) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw or raw == "[DONE]":
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                event_type = str(event.get("type") or "")
                if event_type in {"response.created", "response.queued", "response.in_progress"}:
                    response_payload = event.get("response") if isinstance(event.get("response"), dict) else {}
                    yield {
                        "content": "",
                        "done": False,
                        "response_meta": {
                            "id": str(response_payload.get("id") or ""),
                            "status": str(response_payload.get("status") or event_type.removeprefix("response.")),
                        },
                    }
                elif event_type == "response.output_text.delta":
                    delta = str(event.get("delta") or "")
                    if delta:
                        yield {"content": delta, "done": False}
                elif event_type == "response.reasoning_summary_text.delta":
                    delta = str(event.get("delta") or "")
                    if delta:
                        source_key, summary_id, step_id = _reasoning_summary_identity(event)
                        accumulated = (summary_buffers.get(source_key, "") + delta)[
                            :_MAX_REASONING_BUFFER_CHARS
                        ]
                        summary_buffers[source_key] = accumulated
                        public_summary = _sanitize_reasoning_summary(accumulated)
                        if not public_summary:
                            continue
                        work_summary_sequence += 1
                        yield {
                            "content": "",
                            "done": False,
                            "response_id": str(event.get("response_id") or ""),
                            "sequence": work_summary_sequence,
                            "work_summary": {
                                "kind": "reasoning_excerpt",
                                "step_id": step_id,
                                "summary_id": summary_id,
                                "stage": "reasoning_summary",
                                "summary": public_summary,
                                "status": "active",
                                "occurred_at": datetime.now(timezone.utc).isoformat(),
                            },
                        }
                elif event_type == "response.reasoning_summary_text.done":
                    source_key, summary_id, step_id = _reasoning_summary_identity(event)
                    upstream_text = str(event.get("text") or "")
                    accumulated = summary_buffers.get(source_key, "")
                    if upstream_text:
                        accumulated = upstream_text[:_MAX_REASONING_BUFFER_CHARS]
                    public_summary = _sanitize_reasoning_summary(accumulated)
                    if public_summary:
                        summary_buffers[source_key] = accumulated
                        work_summary_sequence += 1
                        yield {
                            "content": "",
                            "done": False,
                            "response_id": str(event.get("response_id") or ""),
                            "sequence": work_summary_sequence,
                            "work_summary": {
                                "kind": "reasoning_excerpt",
                                "step_id": step_id,
                                "summary_id": summary_id,
                                "stage": "reasoning_summary",
                                "summary": public_summary,
                                "status": "completed",
                                "occurred_at": datetime.now(timezone.utc).isoformat(),
                            },
                        }
                elif event_type in {"response.output_item.added", "response.output_item.done"}:
                    item = event.get("item")
                    if isinstance(item, dict):
                        tool_event = _tool_event(item, "started" if event_type.endswith("added") else "completed")
                        if tool_event:
                            yield {"content": "", "done": False, "tool_event": tool_event}
                elif event_type == "response.work_summary.updated":
                    candidate = event.get("work_summary")
                    if isinstance(candidate, dict):
                        public_summary = _sanitize_upstream_work_summary(event, candidate)
                        if public_summary is not None:
                            work_summary_sequence += 1
                            yield {
                                "content": "",
                                "done": False,
                                "response_id": str(event.get("response_id") or ""),
                                "sequence": work_summary_sequence,
                                "work_summary": public_summary,
                            }
                elif event_type == "response.completed":
                    response_payload = event.get("response") if isinstance(event.get("response"), dict) else {}
                    yield {
                        "content": "",
                        "done": False,
                        "response_meta": {
                            "id": str(response_payload.get("id") or ""),
                            "status": str(response_payload.get("status") or "completed"),
                        },
                    }
                elif event_type in {"response.failed", "error"}:
                    raise ValueError("openai_response_failed")


def _response_url(provider: dict[str, Any], response_id: str) -> str:
    if not _RESPONSE_ID.fullmatch(response_id):
        raise ValueError("invalid_response_id")
    return f"{str(provider['url']).rstrip('/')}/{response_id}"


async def retrieve_response(
    provider: dict[str, Any],
    response_id: str,
    *,
    stream: bool = False,
    starting_after: int | None = None,
) -> dict[str, Any] | httpx.Response:
    url = _response_url(provider, response_id)
    _, headers = build_response_payload(provider, [], stream=stream)
    params: dict[str, Any] = {}
    if stream:
        params["stream"] = "true"
    if starting_after is not None:
        params["starting_after"] = max(0, int(starting_after))
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response if stream else parse_response(response.json())


async def cancel_response(provider: dict[str, Any], response_id: str) -> dict[str, Any]:
    url = f"{_response_url(provider, response_id)}/cancel"
    _, headers = build_response_payload(provider, [])
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        response = await client.post(url, headers=headers)
        response.raise_for_status()
        return parse_response(response.json())
