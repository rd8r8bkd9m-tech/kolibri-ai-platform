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
import ipaddress
import json
import re
from datetime import date
from typing import Any, Literal
from urllib.parse import unquote, urlsplit, urlunsplit


SCHEMA_VERSION = "kolibri.work-summary.v1"
METADATA_KEY = "kolibri_work_summary"
SOURCES_METADATA_KEY = "kolibri_work_sources"
POLICY_METADATA_KEY = "kolibri_reasoning_policy"
METADATA_VALUE_MAX_CHARS = 512
MAX_ITEMS = 5
MAX_DETAIL_CHARS = 92
MAX_SOURCE_REFS = 4
MAX_SOURCE_URL_CHARS = 280
_SUMMARY_KINDS = {"plan", "tool", "source", "check", "verdict"}
_SUMMARY_STATUSES = {
    "pending", "running", "passed", "failed", "skipped", "available", "incomplete", "blocked",
}

SummaryKind = Literal["plan", "tool", "source", "check", "verdict"]
SummaryStatus = Literal[
    "pending", "running", "passed", "failed", "skipped", "available", "incomplete", "blocked",
]

_SAFE_HOST = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)
_SENSITIVE_URL_PATH = re.compile(
    r"(?:\bsk-[a-z0-9_-]{8,}|\b(?:api[_-]?key|password|secret|token)[=/:_-][^/?#]{4,})",
    re.IGNORECASE,
)
_PRIVATE_SOURCE_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa")
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


def _safe_public_source_host(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    host = value.strip().lower().rstrip(".")
    if not host or not _SAFE_HOST.fullmatch(host):
        return None
    if host == "localhost" or host.endswith(_PRIVATE_SOURCE_SUFFIXES):
        return None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    return host if address.is_global else None


def _safe_source_host(citation: dict[str, Any]) -> str | None:
    candidates = [citation.get("source_host")]
    value = citation.get("url")
    if isinstance(value, str):
        try:
            candidates.append(urlsplit(value).hostname)
        except ValueError:
            pass
    for candidate in candidates:
        host = _safe_public_source_host(candidate)
        if host:
            return host
    return None


def _safe_source_url(value: Any) -> str | None:
    """Return a credential-free canonical HTTP(S) URL without query secrets."""

    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except (ValueError, TypeError):
        return None
    host = _safe_public_source_host(parsed.hostname)
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    netloc = host if port is None else f"{host}:{port}"
    path = parsed.path or "/"
    if _SENSITIVE_URL_PATH.search(unquote(path)):
        path = "/"
    canonical = urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))
    return canonical if len(canonical) <= MAX_SOURCE_URL_CHARS else None


def _safe_source_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if re.fullmatch(r"\d{4}-Q[1-4]", candidate):
        return candidate
    try:
        date.fromisoformat(candidate)
    except ValueError:
        return None
    return candidate


def _source_ref(
    value: Any,
    *,
    price_level_date: Any = None,
    captured_at: Any = None,
) -> dict[str, str] | None:
    url = _safe_source_url(value)
    if url is None:
        return None
    host = urlsplit(url).hostname
    if not host:  # pragma: no cover - guaranteed by _safe_source_url
        return None
    reference = {"url": url, "domain": host}
    safe_price_date = _safe_source_date(price_level_date)
    safe_capture_date = _safe_source_date(captured_at)
    if safe_price_date:
        reference["price_level_date"] = safe_price_date
    if safe_capture_date:
        reference["captured_at"] = safe_capture_date
    return reference


def _dedupe_source_refs(values: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for value in values:
        key = value["url"]
        current = merged.setdefault(key, {"url": key, "domain": value["domain"]})
        for field in ("price_level_date", "captured_at"):
            if value.get(field) and not current.get(field):
                current[field] = value[field]
    return list(merged.values())[:MAX_SOURCE_REFS]


def _source_hosts(citations: Any) -> list[str]:
    hosts: list[str] = []
    for raw in citations if isinstance(citations, list) else []:
        if not isinstance(raw, dict):
            continue
        host = _safe_source_host(raw)
        if host and host not in hosts:
            hosts.append(host)
    return hosts[:3]


def _task_source_facts(task: Any) -> list[dict[str, str]]:
    """Project bounded, credential-free source references from an estimate."""

    if not isinstance(task, dict):
        return []
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    estimate = result.get("estimate") if isinstance(result.get("estimate"), dict) else {}
    references: list[dict[str, str]] = []
    basis = estimate.get("normative_basis") if isinstance(estimate.get("normative_basis"), dict) else {}
    for value in basis.get("source_urls", []) if isinstance(basis.get("source_urls"), list) else []:
        reference = _source_ref(value, price_level_date=basis.get("price_level_date"))
        if reference:
            references.append(reference)
    for line in estimate.get("lines", []) if isinstance(estimate.get("lines"), list) else []:
        if not isinstance(line, dict):
            continue
        provenance = line.get("provenance") if isinstance(line.get("provenance"), dict) else {}
        price_reference = _source_ref(
            provenance.get("source_url"),
            price_level_date=provenance.get("price_level_date"),
            captured_at=provenance.get("captured_at"),
        )
        quantity_reference = _source_ref(provenance.get("quantity_source_url"))
        if price_reference:
            references.append(price_reference)
        if quantity_reference:
            references.append(quantity_reference)
    return _dedupe_source_refs(references)


def _citation_source_facts(citations: Any) -> list[dict[str, str]]:
    references = []
    for citation in citations if isinstance(citations, list) else []:
        if not isinstance(citation, dict):
            continue
        reference = _source_ref(citation.get("url"))
        if reference:
            references.append(reference)
    return _dedupe_source_refs(references)


def _estimate_source_blocked(task: Any) -> bool:
    """Missing mandatory estimate provenance remains a blocker even with money."""

    if not isinstance(task, dict):
        return False
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    if result.get("type") != "deterministic_estimate":
        return False
    verification = result.get("verification") if isinstance(result.get("verification"), dict) else {}
    coverage_missing = verification.get("coverage_missing")
    has_coverage_missing = bool(coverage_missing) if isinstance(coverage_missing, list) else False
    return verification.get("source_coverage_complete") is False or has_coverage_missing


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
    source_blocked = needs_input or _estimate_source_blocked(task)
    task_completed = _task_completed(task)
    completed = response_completed and task_completed and not source_blocked
    intent = _task_intent(task)
    plan_status: SummaryStatus = (
        "incomplete" if source_blocked
        else "passed" if completed
        else "failed" if terminal
        else "running"
    )
    plan_detail = (
        (
            "Черновик исходных данных подготовлен; для расчёта нужны уточнения."
            if needs_input
            else "Расчёт подготовлен; обязательные источники требуют дополнения."
        )
        if source_blocked else _PLAN_DETAILS[intent]
    )
    items: list[dict[str, Any]] = [
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
        tools_status = "available"
        tools_detail = "Инструментальный контур подключён; для этого запроса вызов не потребовался."
    items.append(_item("tool", tools_status, tools_detail))

    citation_hosts = _source_hosts(citations)
    source_refs = _dedupe_source_refs([
        *_citation_source_facts(citations),
        *_task_source_facts(task),
    ])
    source_domains = [reference["domain"] for reference in source_refs]
    orphan_hosts = [host for host in citation_hosts if host not in source_domains]
    hosts = list(dict.fromkeys([*source_domains, *orphan_hosts]))[:3]
    source_dates = list(dict.fromkeys([
        value
        for reference in source_refs
        for value in (reference.get("price_level_date"), reference.get("captured_at"))
        if value
    ]))[:3]
    source_count = len(source_refs) + len(orphan_hosts)
    if source_blocked:
        source_status: SummaryStatus = "blocked"
        source_detail = (
            "Нужны исходные документы и подтверждённые источники цен."
            if needs_input
            else "Часть обязательных ссылок на источники отсутствует; требуется дополнение."
        )
    elif hosts:
        source_status: SummaryStatus = "passed" if completed else "failed"
        date_detail = f" · даты: {', '.join(source_dates)}" if source_dates else ""
        source_detail = (
            f"Источники: {source_count} · {', '.join(hosts)}"
            f"{date_detail}."
        )
    elif requested:
        source_status = "failed" if terminal else "pending"
        source_detail = "Источники ещё не подтверждены."
    else:
        source_status = "available"
        source_detail = "Контур источников подключён; для этого запроса ссылки не использовались."
    source_item: dict[str, Any] = _item("source", source_status, source_detail)
    if source_refs:
        source_item["sources"] = source_refs
    items.append(source_item)

    passed = _verification_passed(verification)
    verified_complete = completed and passed
    if source_blocked:
        check_status: SummaryStatus = "blocked"
        check_detail = (
            "Проверка денежного расчёта ожидает исходных данных."
            if needs_input
            else "Проверка результата заблокирована неполным покрытием источников."
        )
    elif terminal:
        check_status: SummaryStatus = "passed" if passed else "failed"
        check_detail = "Проверка результата пройдена." if passed else "Проверка результата не пройдена."
    else:
        check_status = "pending"
        check_detail = "Проверка результата ожидается."
    items.append(_item("check", check_status, check_detail))

    if source_blocked:
        verdict_status: SummaryStatus = "incomplete"
        verdict_detail = (
            "Черновик исходных данных подготовлен; денежный итог не рассчитан."
            if needs_input
            else "Предварительный расчёт подготовлен; обязательные источники нужно дополнить."
        )
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
    merged.pop(SOURCES_METADATA_KEY, None)
    source_item = next((
        item for item in summary.get("items", [])
        if isinstance(item, dict) and item.get("kind") == "source"
    ), {})
    source_refs = source_item.get("sources") if isinstance(source_item, dict) else None
    compact_sources: list[dict[str, str]] = []
    for source in source_refs if isinstance(source_refs, list) else []:
        if not isinstance(source, dict):
            continue
        projected = {
            key: source[key]
            for key in ("url", "domain", "price_level_date", "captured_at")
            if isinstance(source.get(key), str) and source[key]
        }
        candidate = json.dumps(
            {"v": 1, "sources": [*compact_sources, projected]},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(candidate) > METADATA_VALUE_MAX_CHARS:
            continue
        compact_sources.append(projected)
    if compact_sources:
        merged[SOURCES_METADATA_KEY] = json.dumps(
            {"v": 1, "sources": compact_sources},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    merged[POLICY_METADATA_KEY] = "summary_only_no_raw_chain_of_thought"
    return merged


def summary_from_metadata(metadata: Any) -> dict[str, Any] | None:
    """Decode only the server-authored, bounded summary projection."""

    if not isinstance(metadata, dict):
        return None
    encoded = metadata.get(METADATA_KEY)
    if not isinstance(encoded, str) or len(encoded) > METADATA_VALUE_MAX_CHARS:
        return None
    try:
        compact = json.loads(encoded)
    except (TypeError, ValueError):
        return None
    if not isinstance(compact, dict) or compact.get("v") != 1 or compact.get("mode") != "summary_only":
        return None
    raw_items = compact.get("items")
    if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= MAX_ITEMS:
        return None
    items: list[dict[str, Any]] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            return None
        kind = raw.get("kind")
        status = raw.get("status")
        detail = raw.get("detail", "")
        if kind not in _SUMMARY_KINDS or status not in _SUMMARY_STATUSES or not isinstance(detail, str):
            return None
        items.append({"kind": kind, "status": status, "detail": _bounded(detail)})

    source_refs: list[dict[str, str]] = []
    encoded_sources = metadata.get(SOURCES_METADATA_KEY)
    if encoded_sources is not None:
        if not isinstance(encoded_sources, str) or len(encoded_sources) > METADATA_VALUE_MAX_CHARS:
            return None
        try:
            sources_payload = json.loads(encoded_sources)
        except (TypeError, ValueError):
            return None
        if not isinstance(sources_payload, dict):
            return None
        raw_sources = sources_payload.get("sources")
        if sources_payload.get("v") != 1 or not isinstance(raw_sources, list):
            return None
        for raw in raw_sources[:MAX_SOURCE_REFS]:
            if not isinstance(raw, dict):
                return None
            reference = _source_ref(
                raw.get("url"),
                price_level_date=raw.get("price_level_date"),
                captured_at=raw.get("captured_at"),
            )
            if reference is None or reference.get("domain") != raw.get("domain"):
                return None
            source_refs.append(reference)
    if source_refs:
        source_item = next((item for item in items if item["kind"] == "source"), None)
        if source_item is not None:
            source_item["sources"] = source_refs
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "summary_only",
        "raw_reasoning_exposed": False,
        "items": items,
    }


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
