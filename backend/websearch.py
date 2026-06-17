import httpx
from typing import List, Dict


class WebSearchEngine:
    async def search(self, query: str, num_results: int = 5) -> List[Dict]:
        results = await self._duckduckgo(query, num_results)
        if results:
            return results
        return [{"title": "No results", "snippet": "Web search is not fully configured.", "url": ""}]

    async def _duckduckgo(self, query: str, num_results: int) -> List[Dict]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_redirect": "1"},
                )
                data = resp.json()
                results = []
                for r in data.get("RelatedTopics", [])[:num_results]:
                    if "Text" in r:
                        results.append({
                            "title": r.get("Text", "")[:100],
                            "snippet": r.get("Text", ""),
                            "url": r.get("FirstURL", ""),
                        })
                return results
        except Exception:
            return []
