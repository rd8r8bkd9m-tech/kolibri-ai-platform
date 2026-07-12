"""Execution bridge for tools requested through ``POST /v1/responses``."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from estimate_price_research import (
    build_estimate_price_queries,
    estimate_price_citations,
    estimate_price_provider_context,
)
from project_knowledge_gateway import (
    TOOL_ID as PROJECT_KNOWLEDGE_TOOL_ID,
    ProjectKnowledgeAuthorization,
    get_project_knowledge_gateway,
)
from web_search_gateway import (
    TOOL_ID as WEB_SEARCH_TOOL_ID,
    WebSearchAuthorization,
    WebSearchError,
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
    estimate_task: dict[str, Any] | None = None,
    cancel_event: Any = None,
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
    project_executions: list[dict[str, Any]] = []
    web_executions: list[dict[str, Any]] = []
    controlled_search_failures: list[dict[str, Any]] = []
    if project_bindings:
        project_executions.append(get_project_knowledge_gateway().execute(
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
        authorization = WebSearchAuthorization(
            principal=principal,
            response_id=response_id,
            task_id=task_id,
            session_id=session_id,
            project_id=project_id,
            workstream_id=workstream_id,
            allowed_tool_ids=allowed_tool_ids,
        )
        queries = (
            build_estimate_price_queries(estimate_task)
            if isinstance(estimate_task, dict) and estimate_task.get("intent") == "estimate"
            else [query_from_response_input(input_value)]
        )
        try:
            research_budget = max(
                1.0,
                min(float(os.environ.get("KOLIBRI_ESTIMATE_PRICE_RESEARCH_BUDGET_SECONDS", "4")), 15.0),
            )
        except ValueError:
            research_budget = 4.0
        research_deadline = time.monotonic() + research_budget
        last_error: WebSearchError | None = None
        for query in queries:
            if cancel_event is not None and cancel_event.is_set():
                last_error = WebSearchError("web_search_cancelled", retryable=False)
                break
            if time.monotonic() >= research_deadline:
                last_error = WebSearchError("web_search_timeout", retryable=True)
                break
            try:
                gateway = get_web_search_gateway()
                try:
                    execution = gateway.execute(
                        query,
                        authorization=authorization,
                        result_limit=_web_result_limit(raw_tools),
                        deadline_monotonic=research_deadline,
                    )
                except TypeError as exc:
                    if "deadline_monotonic" not in str(exc):
                        raise
                    execution = gateway.execute(
                        query,
                        authorization=authorization,
                        result_limit=_web_result_limit(raw_tools),
                    )
                if (
                    isinstance(estimate_task, dict)
                    and not estimate_price_citations(execution.get("citations"))
                ):
                    last_error = WebSearchError("web_search_no_price_evidence", retryable=True)
                    controlled_search_failures.append({
                        "provider": "controlled-search",
                        "status": "failed",
                        "error_type": "web_search_no_price_evidence",
                        "retryable": True,
                    })
                    continue
                web_executions.append(execution)
            except WebSearchError as exc:
                # A construction estimate uses several independent searches.
                # One empty category must not discard already bound material or
                # labour evidence; total exhaustion still follows the existing
                # typed web-search failure path.
                last_error = exc
                controlled_search_failures.extend(
                    dict(item) for item in getattr(exc, "attempts", [])
                    if isinstance(item, dict)
                )
            except Exception:
                # Provider adapters are an untrusted boundary.  A malformed or
                # unexpected adapter exception must not turn an otherwise
                # usable preliminary estimate into an untyped HTTP 503.  Keep
                # the failure content-free and continue to the bounded native
                # provider fallback below.
                last_error = WebSearchError(
                    "web_search_provider_failed", retryable=True,
                )
                controlled_search_failures.append({
                    "provider": "controlled-search",
                    "status": "failed",
                    "error_type": "web_search_provider_failed",
                    "retryable": True,
                })
        if not web_executions and last_error is not None:
            if isinstance(estimate_task, dict) and estimate_task.get("intent") == "estimate":
                # The native Codex route is a bounded second source acquisition
                # path.  Its JSONL web_search event proves execution but not the
                # fetched page body, so downstream labels every resulting URL
                # and quote provider_asserted_unverified.
                provider_tools = [{
                    "id": WEB_SEARCH_TOOL_ID,
                    "kind": "tool",
                    "name": "web_search",
                    "status": "available",
                    "source": {"type": "native-provider-fallback"},
                    "_aliases": ("web_search", WEB_SEARCH_TOOL_ID),
                    "_providers": ("factory", "codex"),
                }]
            else:
                raise last_error
    executions.extend(project_executions)
    executions.extend(web_executions)
    citations: list[dict[str, Any]] = []
    seen_citations: set[tuple[str, ...]] = set()
    for execution in executions:
        for raw in execution["citations"]:
            url = str(raw.get("url") or "")
            if url:
                identity = ("url", url)
            else:
                identity = (
                    "project",
                    str(raw.get("policy_version") or ""),
                    str(raw.get("path") or ""),
                    str(raw.get("span_sha256") or ""),
                    str(raw.get("marker") or ""),
                )
            if identity in seen_citations:
                continue
            seen_citations.add(identity)
            citation = dict(raw)
            citation["id"] = f"cite_{len(citations) + 1}"
            citations.append(citation)
    contexts = [str(execution["provider_context"]) for execution in project_executions]
    if web_executions:
        if isinstance(estimate_task, dict) and estimate_task.get("intent") == "estimate":
            contexts.append(estimate_price_provider_context(citations))
        else:
            contexts.extend(str(execution["provider_context"]) for execution in web_executions)
    elif provider_tools and isinstance(estimate_task, dict):
        contexts.append(
            "Controlled search providers were exhausted. Use the native web_search tool to enrich "
            "the primary estimate, then return the complete v2 estimate proposal JSON. Attach an "
            "HTTPS source_url, exact source_quote, captured_at, price_level_date, region and "
            "VAT/delivery/specification assumptions only to lines supported by that search. If a "
            "usable source is unavailable, omit that line's provenance objects but keep the full "
            "editable line as a preliminary model suggestion. Native search proves that research "
            "ran, but its URLs and quotes remain provider assertions; never label them independently "
            "verified or normative."
        )
    combined_instructions = "\n\n".join(
        part for part in (instructions, *contexts) if part
    )
    return ResponseToolExecution(
        provider_tools=provider_tools,
        provider_instructions=combined_instructions,
        tool_calls=[dict(execution["tool_call"]) for execution in executions],
        evidence=[dict(execution["evidence"]) for execution in executions],
        citations=citations,
        attempts=[
            *controlled_search_failures,
            *(dict(item) for execution in executions for item in execution["attempts"]),
        ],
        formulalm_taps=[dict(execution["formulalm_tap"]) for execution in executions],
    )
