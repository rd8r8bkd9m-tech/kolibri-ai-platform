"""Web search — multiple backends: DuckDuckGo, Google, Searx."""
import os
import re
import httpx
from typing import List, Dict

SEARCH_TIMEOUT = int(os.getenv("SEARCH_TIMEOUT", "15"))


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
                    for item in data.get("results", [])[:num]:
                        results.append({
                            "title": item.get("title", ""),
                            "snippet": item.get("content", ""),
                            "url": item.get("url", ""),
                        })
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
                return _parse_ddg_html(resp.text, num)
    except Exception:
        pass
    return []


def _parse_ddg_html(html: str, num: int) -> List[Dict[str, str]]:
    """Parse DuckDuckGo HTML results."""
    results = []
    # Find result blocks
    blocks = re.findall(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</(?:a|td|span)', html, re.DOTALL)
    for url, title, snippet in blocks[:num]:
        # Clean HTML tags
        title = re.sub(r'<[^>]+>', '', title).strip()
        snippet = re.sub(r'<[^>]+>', '', snippet).strip()
        if title and url:
            results.append({"title": title, "snippet": snippet, "url": url})
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
                return _parse_google_html(resp.text, num)
    except Exception:
        pass
    return []


def _parse_google_html(html: str, num: int) -> List[Dict[str, str]]:
    """Parse Google HTML results."""
    results = []
    # Find title + URL pairs
    blocks = re.findall(r'<a[^>]*href="/url\?q=([^&"]+)[^"]*"[^>]*><h3[^>]*>(.*?)</h3>', html)
    for url, title in blocks[:num]:
        title = re.sub(r'<[^>]+>', '', title).strip()
        if title and url:
            results.append({"title": title, "snippet": "", "url": url})
    return results


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
