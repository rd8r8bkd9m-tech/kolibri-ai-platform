"""Execution bridge for tools requested through ``POST /v1/responses``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from project_knowledge_gateway import (
    TOOL_ID as PROJECT_KNOWLEDGE_TOOL_ID,
    ProjectKnowledgeAuthorization,
    get_project_knowledge_gateway,
)
from web_search_gateway import (
    TOOL_ID as WEB_SEARCH_TOOL_ID,
    WebSearchAuthorization,
    get_web_search_gateway,
    query_from_response_input,
)


@dataclass(frozen=True)
class ResponseToolExecution:
    provider_tools: list[dict[str, Any]]
    provider_instructions: str | None
    tool_calls: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    attempts: list[dict[str, Any]]
    formulalm_taps: list[dict[str, Any]]


def _web_result_limit(raw_tools: list[dict[str, Any]]) -> int:
    sizes = {"low": 3, "medium": 5, "high": 8}
    for item in raw_tools:
        if not isinstance(item, dict):
            continue
        request_type = str(item.get("type") or item.get("name") or item.get("id") or "").lower()
        if request_type not in {
            "web_search", "web_search_preview", "tool:web_search", "search_web",
        }:
            continue
        size = str(item.get("search_context_size") or "medium").lower()
        return sizes.get(size, 5)
    return 5


def _project_result_limit(raw_tools: list[dict[str, Any]]) -> int:
    for item in raw_tools:
        if not isinstance(item, dict):
            continue
        request_type = str(item.get("type") or item.get("name") or item.get("id") or "").lower()
        if request_type not in {
            "project_knowledge", "project_docs", "repository_context",
            PROJECT_KNOWLEDGE_TOOL_ID,
        }:
            continue
        value = item.get("max_results", 5)
        return value if isinstance(value, int) and 1 <= value <= 8 else 5
    return 5


def execute_response_tools(
    *,
    input_value: str | list[dict[str, Any]],
    instructions: str | None,
    response_id: str,
    principal: str,
    requested_tools: list[dict[str, Any]],
    raw_tools: list[dict[str, Any]],
    project_id: str | None = None,
    workstream_id: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
) -> ResponseToolExecution:
    web_bindings = [item for item in requested_tools if item.get("id") == WEB_SEARCH_TOOL_ID]
    project_bindings = [
        item for item in requested_tools if item.get("id") == PROJECT_KNOWLEDGE_TOOL_ID
    ]
    gateway_tool_ids = {WEB_SEARCH_TOOL_ID, PROJECT_KNOWLEDGE_TOOL_ID}
    provider_tools = [item for item in requested_tools if item.get("id") not in gateway_tool_ids]
    if not web_bindings and not project_bindings:
        return ResponseToolExecution(provider_tools, instructions, [], [], [], [], [])

    allowed_tool_ids = tuple(str(item.get("id") or "") for item in requested_tools)
    executions: list[dict[str, Any]] = []
    if project_bindings:
        executions.append(get_project_knowledge_gateway().execute(
            input_value,
            authorization=ProjectKnowledgeAuthorization(
                principal=principal,
                response_id=response_id,
                task_id=task_id,
                project_id=project_id,
                workstream_id=workstream_id,
                allowed_tool_ids=allowed_tool_ids,
            ),
            result_limit=_project_result_limit(raw_tools),
        ))
    if web_bindings:
        executions.append(get_web_search_gateway().execute(
            query_from_response_input(input_value),
            authorization=WebSearchAuthorization(
                principal=principal,
                response_id=response_id,
                task_id=task_id,
                session_id=session_id,
                project_id=project_id,
                workstream_id=workstream_id,
                allowed_tool_ids=allowed_tool_ids,
            ),
            result_limit=_web_result_limit(raw_tools),
        ))
    contexts = [str(execution["provider_context"]) for execution in executions]
    combined_instructions = "\n\n".join(
        part for part in (instructions, *contexts) if part
    )
    return ResponseToolExecution(
        provider_tools=provider_tools,
        provider_instructions=combined_instructions,
        tool_calls=[dict(execution["tool_call"]) for execution in executions],
        evidence=[dict(execution["evidence"]) for execution in executions],
        citations=[
            dict(item) for execution in executions for item in execution["citations"]
        ],
        attempts=[
            dict(item) for execution in executions for item in execution["attempts"]
        ],
        formulalm_taps=[dict(execution["formulalm_tap"]) for execution in executions],
    )
