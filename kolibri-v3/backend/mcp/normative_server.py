"""MCP server for normative document search.

Wraps CNTD (normative documents) and construction registry lookups.
Compatible with Codex CLI and MiMo Code MCP support.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.mcp.base import MCPServer

import httpx

server = MCPServer(name="kolibri-normative", version="1.0.0")

CNTD_BASE = "https://docs.cntd.ru"
USER_AGENT = "Kolibri-Normative-MCP/1.0"

# Common normative documents for construction
NORMATIVE_INDEX = {
    "ГЭСН": {
        "full_name": "Государственные элементные сметные нормы",
        "description": "Базовые нормы для составления смет строительных работ",
        "url": f"{CNTD_BASE}/document/1200119138",
    },
    "ТЕР": {
        "full_name": "Территориальные единичные расценки",
        "description": "Расценки на строительные работы по регионам",
        "url": f"{CNTD_BASE}/document/1200119139",
    },
    "ФЕР": {
        "full_name": "Федеральные единичные расценки",
        "description": "Федеральные расценки на строительные работы",
        "url": f"{CNTD_BASE}/document/1200119140",
    },
    "СП": {
        "full_name": "Своды правил",
        "description": "Строительные правила и нормы проектирования",
        "url": f"{CNTD_BASE}/document/1200119141",
    },
    "СНиП": {
        "full_name": "Строительные нормы и правила",
        "description": "Обязательные требования к строительству",
        "url": f"{CNTD_BASE}/document/1200119138",
    },
}


@server.tool(
    name="search_normative",
    description=(
        "Найти нормативный документ по строительству (ГЭСН, ТЕР, ФЕР, СП, СНиП). "
        "Возвращает ссылки на документы и краткое описание."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Поисковый запрос (например: 'ГЭСН штукатурка', 'ТЕР бетонные работы')",
            },
            "document_type": {
                "type": "string",
                "description": "Тип документа для фильтрации",
                "enum": ["ГЭСН", "ТЕР", "ФЕР", "СП", "СНиП", ""],
                "default": "",
            },
        },
        "required": ["query"],
    },
)
def search_normative(query: str, document_type: str = "") -> dict:
    """Search for normative construction documents."""
    results = []
    query_upper = query.upper()

    # Search in local index first
    for code, info in NORMATIVE_INDEX.items():
        if document_type and code != document_type:
            continue
        if (
            code in query_upper
            or info["full_name"].lower() in query.lower()
            or any(word in info["full_name"].lower() for word in query.lower().split())
        ):
            results.append({
                "code": code,
                "full_name": info["full_name"],
                "description": info["description"],
                "url": info["url"],
                "source": "CNTD",
            })

    # If no local matches, try web search via CNTD
    if not results:
        try:
            with httpx.Client(
                timeout=15,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                # Try CNTD search
                search_url = f"{CNTD_BASE}/search"
                response = client.get(
                    search_url,
                    params={"q": query, "type": "document"},
                )
                if response.status_code == 200:
                    # Parse results from HTML (simplified)
                    text = response.text
                    # Look for document links
                    import re
                    doc_links = re.findall(
                        r'href="(/document/\d+)"[^>]*>([^<]+)',
                        text,
                    )
                    for href, title in doc_links[:5]:
                        results.append({
                            "code": "DOC",
                            "full_name": title.strip(),
                            "description": "",
                            "url": f"{CNTD_BASE}{href}",
                            "source": "CNTD search",
                        })
        except Exception:
            pass

    # Fallback: return relevant known documents
    if not results:
        if document_type:
            info = NORMATIVE_INDEX.get(document_type)
            if info:
                results.append({
                    "code": document_type,
                    "full_name": info["full_name"],
                    "description": info["description"],
                    "url": info["url"],
                    "source": "CNTD (default)",
                })
        else:
            # Return most relevant defaults
            for code in ["ГЭСН", "ТЕР"]:
                info = NORMATIVE_INDEX[code]
                results.append({
                    "code": code,
                    "full_name": info["full_name"],
                    "description": info["description"],
                    "url": info["url"],
                    "source": "CNTD (default)",
                })

    return {
        "query": query,
        "document_type": document_type or "all",
        "count": len(results),
        "documents": results,
    }


@server.tool(
    name="get_normative_document",
    description=(
        "Получить информацию о конкретном нормативном документе по коду. "
        "Возвращает полное название, описание и ссылку."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Код документа (ГЭСН, ТЕР, ФЕР, СП, СНиП)",
                "enum": ["ГЭСН", "ТЕР", "ФЕР", "СП", "СНиП"],
            },
        },
        "required": ["code"],
    },
)
def get_normative_document(code: str) -> dict:
    """Get normative document info by code."""
    info = NORMATIVE_INDEX.get(code)
    if not info:
        return {"error": f"Документ '{code}' не найден."}

    return {
        "code": code,
        "full_name": info["full_name"],
        "description": info["description"],
        "url": info["url"],
        "source": "CNTD",
    }


if __name__ == "__main__":
    server.run()
