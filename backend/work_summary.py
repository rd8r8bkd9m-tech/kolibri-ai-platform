"""Public, non-chain-of-thought execution summaries for Responses API clients.

The provider's hidden reasoning, raw prompts, tool arguments, tool results and
technical routing envelope are intentionally not inputs to this module.  It
builds a small, deterministic summary from already verified lifecycle facts so
the Shell can explain *what* happened without exposing *how the model thought*.

The compact JSON is stored in OpenAI-compatible response ``metadata``.  A
standard Responses API ``reasoning`` output item mirrors the same safe text for
clients that understand reasoning-summary streaming events.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal
from urllib.parse import urlsplit


SCHEMA_VERSION = "kolibri.work-summary.v1"
METADATA_KEY = "kolibri_work_summary"
POLICY_METADATA_KEY = "kolibri_reasoning_policy"
METADATA_VALUE_MAX_CHARS = 512
MAX_ITEMS = 5
MAX_DETAIL_CHARS = 92

SummaryKind = Literal["plan", "tool", "source", "check", "verdict"]
SummaryStatus = Literal[
    "pending", "running", "passed", "failed", "skipped", "incomplete", "blocked",
]

_SAFE_HOST = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)
_SAFE_TOOL_LABELS = {
    "tool:web_search": "Веб-поиск",
    "web_search": "Веб-поиск",
    "web_search_preview": "Веб-поиск",
    "tool:project_knowledge": "Документы проекта",
    "project_knowledge": "Документы проекта",
    "tool:code_inspection": "Проверка кода",
    "code_inspection": "Проверка кода",
}
_PLAN_DETAILS = {
    "estimate": "Подготовить структуру сметы, пересчитать итог и проверить источники.",
    "document": "Подготовить документ, проверить структуру и доступные результаты.",
    "site": "Собрать результат, проверить файлы и готовность предпросмотра.",
    "app": "Собрать результат, проверить файлы, тесты и готовность запуска.",
    "response": "Подготовить ответ, подключить нужные инструменты и проверить результат.",
}


def _bounded(value: str, limit: int = MAX_DETAIL_CHARS) -> str:
    compact = " ".join(str(value).split())
    if len(compact) <= limit:
        return compact
    return compact[: max(1, limit - 1)].rstrip() + "…"


def _item(kind: SummaryKind, status: SummaryStatus, detail: str) -> dict[str, str]:
    return {"kind": kind, "status": status, "detail": _bounded(detail)}


def _task_intent(task: Any) -> str:
    if not isinstance(task, dict):
        return "response"
    intent = str(task.get("intent") or "").strip().lower()
    return intent if intent in _PLAN_DETAILS else "response"


def _task_needs_input(task: Any) -> bool:
    if not isinstance(task, dict):
        return False
    status = str(task.get("status") or "").strip().lower()
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    result_type = str(result.get("type") or "").strip().lower()
    result_status = str(result.get("status") or "").strip().lower()
    return (
        status in {"incomplete", "needs_input", "blocked"}
        or result_type == "estimate_readiness"
        or result_status in {"incomplete", "needs_input", "blocked"}
    )


def _task_completed(task: Any) -> bool:
    if not isinstance(task, dict):
        return True
    status = str(task.get("status") or "").strip().lower()
    # Request-time task declarations do not have a lifecycle status yet.
    return not status or status == "completed"


def _requested_tool_ids(tools: Any) -> list[str]:
    values: list[str] = []
    for raw in tools if isinstance(tools, list) else []:
        if not isinstance(raw, dict):
            continue
        identifier = str(raw.get("id") or raw.get("type") or raw.get("name") or "").strip().lower()
        if identifier:
            values.append(identifier)
    return values


def _executed_tool_ids(tool_calls: Any) -> list[str]:
    values: list[str] = []
    for raw in tool_calls if isinstance(tool_calls, list) else []:
        if not isinstance(raw, dict):
            continue
        identifier = str(raw.get("capability_id") or raw.get("tool_id") or raw.get("name") or "").strip().lower()
        if identifier:
            values.append(identifier)
    return values


def _tool_labels(tool_ids: list[str]) -> list[str]:
    labels: list[str] = []
    for identifier in tool_ids:
        label = _SAFE_TOOL_LABELS.get(identifier, "Подключённый инструмент")
        if label not in labels:
            labels.append(label)
    return labels[:3]


def _safe_source_host(citation: dict[str, Any]) -> str | None:
    candidates = [citation.get("source_host")]
    value = citation.get("url")
    if isinstance(value, str):
        try:
            candidates.append(urlsplit(value).hostname)
        except ValueError:
            pass
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        host = candidate.strip().lower().rstrip(".")
        if host and _SAFE_HOST.fullmatch(host):
            return host
    return None


def _source_hosts(citations: Any) -> list[str]:
    hosts: list[str] = []
    for raw in citations if isinstance(citations, list) else []:
        if not isinstance(raw, dict):
            continue
        host = _safe_source_host(raw)
        if host and host not in hosts:
            hosts.append(host)
    return hosts[:3]


def _verification_passed(verification: Any) -> bool:
    if not isinstance(verification, dict):
        return False
    status = str(verification.get("status") or verification.get("verdict") or "").strip().lower()
    return status in {"passed", "verified"}


def build_work_summary(
    *,
    response_status: str,
    task: dict[str, Any] | None = None,
    requested_tools: list[dict[str, Any]] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    citations: list[dict[str, Any]] | None = None,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build five allowlisted lifecycle facts; never accept prompt or trace text."""

    terminal = response_status in {"completed", "failed", "incomplete", "cancelled"}
    response_completed = response_status == "completed"
    needs_input = _task_needs_input(task)
    task_completed = _task_completed(task)
    completed = response_completed and task_completed and not needs_input
    intent = _task_intent(task)
    plan_status: SummaryStatus = (
        "incomplete" if needs_input
        else "passed" if completed
        else "failed" if terminal
        else "running"
    )
    plan_detail = (
        "Черновик исходных данных подготовлен; для расчёта нужны уточнения."
        if needs_input else _PLAN_DETAILS[intent]
    )
    items: list[dict[str, str]] = [
        _item("plan", plan_status, plan_detail),
    ]

    requested = _requested_tool_ids(requested_tools)
    executed = _executed_tool_ids(tool_calls)
    labels = _tool_labels(executed or requested)
    if executed:
        tools_status: SummaryStatus = "passed" if response_completed else "failed"
        tools_detail = "Выполнено: " + ", ".join(labels) + "."
    elif requested:
        tools_status = "failed" if terminal else "pending"
        tools_detail = "Ожидается: " + ", ".join(labels) + "."
    else:
        tools_status = "skipped"
        tools_detail = "Дополнительные инструменты не потребовались."
    items.append(_item("tool", tools_status, tools_detail))

    hosts = _source_hosts(citations)
    if needs_input:
        source_status: SummaryStatus = "blocked"
        source_detail = "Нужны исходные документы и подтверждённые источники цен."
    elif hosts:
        source_status: SummaryStatus = "passed" if completed else "failed"
        source_detail = f"Проверено источников: {len(citations or [])}. Домены: {', '.join(hosts)}."
    elif requested:
        source_status = "failed" if terminal else "pending"
        source_detail = "Источники ещё не подтверждены."
    else:
        source_status = "skipped"
        source_detail = "Внешние источники не требовались."
    items.append(_item("source", source_status, source_detail))

    passed = _verification_passed(verification)
    verified_complete = completed and passed
    if needs_input:
        check_status: SummaryStatus = "blocked"
        check_detail = "Проверка денежного расчёта ожидает исходных данных."
    elif terminal:
        check_status: SummaryStatus = "passed" if passed else "failed"
        check_detail = "Проверка результата пройдена." if passed else "Проверка результата не пройдена."
    else:
        check_status = "pending"
        check_detail = "Проверка результата ожидается."
    items.append(_item("check", check_status, check_detail))

    if needs_input:
        verdict_status: SummaryStatus = "incomplete"
        verdict_detail = "Черновик исходных данных подготовлен; денежный итог не рассчитан."
    elif not terminal:
        verdict_status: SummaryStatus = "pending"
        verdict_detail = "Итог появится после проверки."
    elif verified_complete:
        verdict_status = "passed"
        verdict_detail = "Проверенный результат готов."
    else:
        verdict_status = "failed"
        verdict_detail = "Проверенный результат не получен."
    items.append(_item("verdict", verdict_status, verdict_detail))

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "summary_only",
        "raw_reasoning_exposed": False,
        "items": items[:MAX_ITEMS],
    }


def _compact_payload(summary: dict[str, Any], detail_limit: int) -> dict[str, Any]:
    compact_items = []
    for item in summary.get("items", [])[:MAX_ITEMS]:
        compact_items.append({
            "kind": item["kind"],
            "status": item["status"],
            "detail": _bounded(item["detail"], detail_limit),
        })
    return {"v": 1, "mode": "summary_only", "items": compact_items}


def summary_metadata(
    metadata: dict[str, Any] | None,
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Attach one <=512-character string without breaking OpenAI metadata."""

    merged = dict(metadata or {})
    encoded = ""
    for detail_limit in (MAX_DETAIL_CHARS, 64, 48, 32, 0):
        compact = _compact_payload(summary, max(1, detail_limit))
        if detail_limit == 0:
            for item in compact["items"]:
                item.pop("detail", None)
        encoded = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) <= METADATA_VALUE_MAX_CHARS:
            break
    if len(encoded) > METADATA_VALUE_MAX_CHARS:  # pragma: no cover - invariant guard
        encoded = '{"v":1,"mode":"summary_only","items":[]}'
    merged[METADATA_KEY] = encoded
    merged[POLICY_METADATA_KEY] = "summary_only_no_raw_chain_of_thought"
    return merged


def summary_text_parts(summary: dict[str, Any]) -> list[dict[str, str]]:
    labels = {
        "plan": "План",
        "tool": "Инструменты",
        "source": "Источники",
        "check": "Проверка",
        "verdict": "Итог",
    }
    return [
        {"type": "summary_text", "text": f"{labels[item['kind']]}: {item['detail']}"}
        for item in summary.get("items", [])[:MAX_ITEMS]
        if item.get("kind") in labels and isinstance(item.get("detail"), str)
    ]


def reasoning_output_item(response_id: str, summary: dict[str, Any]) -> dict[str, Any]:
    digest = hashlib.sha256(f"{response_id}:{SCHEMA_VERSION}".encode("utf-8")).hexdigest()[:32]
    return {
        "id": f"rs_{digest}",
        "type": "reasoning",
        "summary": summary_text_parts(summary),
    }
