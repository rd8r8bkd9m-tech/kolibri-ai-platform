"""Fail-closed truth policy for time-sensitive chat requests.

Language models are not a source of current facts.  This module keeps volatile
questions out of the provider-only chat path and renders only evidence returned
by the web-search tool.  If the tool cannot produce a usable URL, the public
contract is ``needs_tool`` rather than a plausible-looking answer.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from html import unescape
from typing import Any, Awaitable, Callable, Iterable
from urllib.parse import urlparse

from app.web_search import web_search


Search = Callable[[str, int], Awaitable[list[dict[str, str]]]]

_EXPLICIT_CURRENT_MARKERS = (
    "сейчас",
    "сегодня",
    "на данный момент",
    "в реальном времени",
    "актуаль",
    "последн",
    "текущ",
    "на этой неделе",
    "this week",
    "currently",
    "right now",
    "today",
    "latest",
)

_VOLATILE_SUBJECTS = (
    "погод",
    "температур",
    "курс валют",
    "котиров",
    "новост",
    "пробк",
    "расписан",
    "weather",
    "exchange rate",
    "stock price",
    "traffic",
    "schedule",
)

_WEB_RESEARCH_MARKERS = (
    "открой сайт",
    "открой ссылку",
    "посмотри сайт",
    "посмотри по ссылке",
    "проанализируй сайт",
    "изучи сайт",
    "найди в интернете",
    "веб-поиск",
    "web search",
    "open the site",
    "open the link",
    "review the site",
)

_HTTP_URL_PATTERN = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_BARE_DOMAIN_PATTERN = re.compile(
    r"(?<![@\w-])(?:www\.)?[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)+"
    r"(?:/[^\s<>()]*)?",
    re.IGNORECASE,
)

_STOP_WORDS = {
    "какая",
    "какой",
    "какие",
    "сейчас",
    "сегодня",
    "покажи",
    "источники",
    "источник",
    "please",
    "show",
    "source",
    "sources",
    "what",
    "where",
    "when",
}


def _last_user_text(messages: Iterable[dict[str, Any]]) -> str:
    for message in reversed(list(messages)):
        if str(message.get("role", "")).lower() == "user":
            return str(message.get("content") or "").strip()
    return ""


def requires_current_evidence(messages: Iterable[dict[str, Any]]) -> bool:
    """Return True for volatile facts and explicit requests to inspect the web."""
    text = _last_user_text(messages).casefold()
    if not text:
        return False
    return (
        any(marker in text for marker in _EXPLICIT_CURRENT_MARKERS)
        or any(subject in text for subject in _VOLATILE_SUBJECTS)
        or any(marker in text for marker in _WEB_RESEARCH_MARKERS)
        or bool(_HTTP_URL_PATTERN.search(text))
        or bool(_BARE_DOMAIN_PATTERN.search(text))
    )


def _plain_text(value: Any, *, limit: int) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _safe_http_url(value: Any) -> str | None:
    candidate = str(value or "").strip()
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username or parsed.password:
        return None
    return candidate


def _query_terms(query: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\wа-яё-]{4,}", query.casefold())
        if token not in _STOP_WORDS
    }


def normalize_web_evidence(
    query: str,
    raw_results: Iterable[dict[str, Any]],
    *,
    retrieved_at: datetime,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Validate, sanitize and number web-search results for public output."""
    terms = _query_terms(query)
    evidence: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for raw in raw_results:
        url = _safe_http_url(raw.get("url"))
        title = _plain_text(raw.get("title"), limit=180)
        snippet = _plain_text(raw.get("snippet"), limit=500)
        searchable = f"{title} {snippet}".casefold()
        if not url or not title or url in seen_urls:
            continue
        if terms and not any(term in searchable for term in terms):
            continue

        seen_urls.add(url)
        evidence.append(
            {
                "citation": len(evidence) + 1,
                "title": title,
                "url": url,
                "snippet": snippet,
                "retrieved_at": retrieved_at.astimezone(timezone.utc).isoformat(),
            }
        )
        if len(evidence) >= limit:
            break
    return evidence


def _source_backed_content(evidence: list[dict[str, Any]], retrieved_at: datetime) -> str:
    observed = retrieved_at.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    lines = [
        f"Выполнил веб-поиск. Источники получены {observed}.",
        "Ниже — данные непосредственно из найденных источников, без догадок модели:",
    ]
    for item in evidence:
        citation = item["citation"]
        line = f"[{citation}] {item['title']}"
        if item["snippet"]:
            line += f" — {item['snippet']}"
        lines.extend((line, f"Источник [{citation}]: {item['url']}"))
    return "\n\n".join(lines)


def _unavailable_result() -> dict[str, Any]:
    return {
        "content": (
            "Не могу достоверно ответить на актуальный запрос: веб-поиск не вернул "
            "проверяемых источников. Я не буду подставлять температуру, цену, курс или "
            "другие текущие данные из памяти модели. Повторите запрос позже."
        ),
        "reasoning": "",
        "actions": [],
        "status": "needs_tool",
        "provider": "web_search",
        "model": "deterministic-evidence-renderer",
        "speed_ms": 0,
        "fallback_used": False,
        "error_code": "current_information_evidence_unavailable",
        "sources": [],
        "truth": {
            "current_information": True,
            "evidence_status": "unavailable",
        },
    }


async def resolve_current_information(
    messages: Iterable[dict[str, Any]],
    *,
    searcher: Search | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Resolve a volatile query from web evidence or fail closed.

    ``None`` means the normal provider route may be used.  A returned mapping is
    a complete public chat result and must not be overwritten by a model answer.
    """
    materialized = list(messages)
    if not requires_current_evidence(materialized):
        return None

    query = _last_user_text(materialized)
    retrieved_at = now or datetime.now(timezone.utc)
    tool = searcher or web_search
    try:
        raw_results = await tool(query, 5)
    except Exception:
        return _unavailable_result()

    evidence = normalize_web_evidence(query, raw_results, retrieved_at=retrieved_at)
    if not evidence:
        return _unavailable_result()

    return {
        "content": _source_backed_content(evidence, retrieved_at),
        "reasoning": "",
        "actions": [],
        "status": "source_backed",
        "provider": "web_search",
        "model": "deterministic-evidence-renderer",
        "speed_ms": 0,
        "fallback_used": False,
        "sources": evidence,
        "truth": {
            "current_information": True,
            "evidence_status": "source_backed",
            "retrieved_at": retrieved_at.astimezone(timezone.utc).isoformat(),
        },
    }
