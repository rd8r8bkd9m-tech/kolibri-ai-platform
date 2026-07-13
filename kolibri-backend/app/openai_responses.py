"""Official OpenAI Responses API adapter.

The public Kolibri stream receives only output text, observable tool lifecycle
events, and provider-authored reasoning *summaries*.  Raw reasoning content is
never forwarded.  Capability availability is promoted to ``live`` only after
an actual completed output item has been observed.
"""

from __future__ import annotations

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
                        yield {
                            "content": "",
                            "done": False,
                            "work_summary": {
                                "stage": "reasoning_summary",
                                "summary": delta,
                                "status": "active",
                            },
                        }
                elif event_type in {"response.output_item.added", "response.output_item.done"}:
                    item = event.get("item")
                    if isinstance(item, dict):
                        tool_event = _tool_event(item, "started" if event_type.endswith("added") else "completed")
                        if tool_event:
                            yield {"content": "", "done": False, "tool_event": tool_event}
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
