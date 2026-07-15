"""Web search — multiple live backends with sanitised source metadata."""
from datetime import datetime, timezone
import html as html_lib
import os
import re
from typing import Dict, List
from urllib.parse import parse_qs, unquote, urljoin, urlparse, urlunparse
from xml.etree import ElementTree

import httpx

SEARCH_TIMEOUT = int(os.getenv("SEARCH_TIMEOUT", "15"))
MAX_SEARCH_RESPONSE_BYTES = 2 * 1024 * 1024
_TEXT_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


async def web_search(query: str, num_results: int = 5) -> List[Dict[str, str]]:
    """Search the web — tries multiple backends."""
    # Try Searx first (most reliable)
    results = await _search_searx(query, num_results)
    if results:
        return results

    # Try DuckDuckGo HTML
    results = await _search_ddg_html(query, num_results)
    if results:
        return results

    # Try Bing RSS XML. This is a real HTTPS result feed and is more stable
    # than scraping another full HTML page.
    results = await _search_bing_rss(query, num_results)
    if results:
        return results

    # Try Google
    results = await _search_google(query, num_results)
    if results:
        return results

    return []


async def _search_searx(query: str, num: int) -> List[Dict[str, str]]:
    """Search via public Searx instances."""
    instances = [
        "https://searx.be/search",
        "https://search.sapti.me/search",
        "https://searx.tiekoetter.com/search",
    ]
    for instance in instances:
        try:
            async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(
                    instance,
                    params={"q": query, "format": "json", "categories": "general"},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = []
                    retrieved_at = _retrieved_at()
                    for item in data.get("results", [])[:num]:
                        result = _result(
                            item.get("title", ""),
                            item.get("content", ""),
                            item.get("url", ""),
                            retrieved_at=retrieved_at,
                        )
                        if result:
                            results.append(result)
                    if results:
                        return results
        except Exception:
            continue
    return []


async def _search_ddg_html(query: str, num: int) -> List[Dict[str, str]]:
    """Search via DuckDuckGo HTML scraping."""
    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            )
            if resp.status_code == 200:
                return _parse_ddg_html(_bounded_text(resp), num)
    except Exception:
        pass
    return []


def _parse_ddg_html(html: str, num: int, *, retrieved_at: str | None = None) -> List[Dict[str, str]]:
    """Parse DuckDuckGo HTML results."""
    results = []
    observed_at = retrieved_at or _retrieved_at()
    # Find result blocks
    blocks = re.findall(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</(?:a|td|span)', html, re.DOTALL)
    for url, title, snippet in blocks:
        result = _result(title, snippet, url, retrieved_at=observed_at)
        if result:
            results.append(result)
        if len(results) >= num:
            break
    return results


async def _search_bing_rss(query: str, num: int) -> List[Dict[str, str]]:
    """Search via Bing RSS XML over HTTPS."""
    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(
                "https://www.bing.com/search",
                params={"q": query, "format": "rss"},
                headers={"User-Agent": "Mozilla/5.0 (compatible; KolibriBot/1.0)"},
            )
            if resp.status_code == 200:
                return _parse_bing_rss(_bounded_text(resp), num)
    except Exception:
        pass
    return []


def _parse_bing_rss(xml_text: str, num: int, *, retrieved_at: str | None = None) -> List[Dict[str, str]]:
    """Parse Bing RSS search results without returning unsafe URLs or markup."""
    observed_at = retrieved_at or _retrieved_at()
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []

    results: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        result = _result(
            item.findtext("title", default=""),
            item.findtext("description", default=""),
            item.findtext("link", default=""),
            retrieved_at=observed_at,
        )
        if result:
            results.append(result)
        if len(results) >= num:
            break
    return results


async def _search_google(query: str, num: int) -> List[Dict[str, str]]:
    """Search via Google."""
    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(
                "https://www.google.com/search",
                params={"q": query, "num": num, "hl": "ru"},
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
            )
            if resp.status_code == 200:
                return _parse_google_html(_bounded_text(resp), num)
    except Exception:
        pass
    return []


def _parse_google_html(html: str, num: int, *, retrieved_at: str | None = None) -> List[Dict[str, str]]:
    """Parse Google HTML results."""
    results = []
    observed_at = retrieved_at or _retrieved_at()
    # Find title + URL pairs
    blocks = re.findall(r'<a[^>]*href="/url\?q=([^&"]+)[^"]*"[^>]*><h3[^>]*>(.*?)</h3>', html)
    for url, title in blocks:
        result = _result(title, "", unquote(url), retrieved_at=observed_at)
        if result:
            results.append(result)
        if len(results) >= num:
            break
    return results


def _retrieved_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_text(response: httpx.Response) -> str:
    content = response.content[:MAX_SEARCH_RESPONSE_BYTES]
    return content.decode(response.encoding or "utf-8", errors="replace")


def _clean_text(value: object, *, maximum: int) -> str:
    text = html_lib.unescape(str(value or ""))
    text = _TEXT_TAG_RE.sub(" ", text)
    text = "".join(ch if ch >= " " or ch in "\t\n\r" else " " for ch in text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text[:maximum]


def _clean_url(value: object) -> str:
    raw = html_lib.unescape(str(value or "")).strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        raw = "https:" + raw
    if raw.startswith("/"):
        raw = urljoin("https://duckduckgo.com", raw)

    parsed = urlparse(raw)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return _clean_url(target)
    if parsed.netloc.endswith("google.com") and parsed.path == "/url":
        target = parse_qs(parsed.query).get("q", [""])[0]
        return _clean_url(target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.username is not None or parsed.password is not None:
        return ""
    clean = parsed._replace(fragment="")
    return urlunparse(clean)[:2_000]


def _result(
    title: object,
    snippet: object,
    url: object,
    *,
    retrieved_at: str,
) -> dict[str, str] | None:
    clean_url = _clean_url(url)
    clean_title = _clean_text(title, maximum=500)
    if not clean_title:
        clean_title = clean_url
    if not clean_url:
        return None
    return {
        "title": clean_title,
        "snippet": _clean_text(snippet, maximum=4_000),
        "url": clean_url,
        "retrieved_at": retrieved_at,
    }


async def search_and_summarize(query: str) -> str:
    """Search and return formatted results for AI context."""
    results = await web_search(query)
    if not results:
        return f"По запросу '{query}' ничего не найдено."

    lines = [f"Результаты поиска по запросу '{query}':\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r['title']}**")
        if r.get('snippet'):
            lines.append(f"   {r['snippet']}")
        if r.get('url'):
            lines.append(f"   Источник: {r['url']}")
        lines.append("")

    return "\n".join(lines)
