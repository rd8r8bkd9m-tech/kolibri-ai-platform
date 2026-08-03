"""MCP server for construction pricing queries.

Wraps FGIS CS (ФГИС ЦС) public pricing API and reference price snapshots.
Compatible with Codex CLI and MiMo Code MCP support.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.mcp.base import MCPServer

import httpx

server = MCPServer(name="kolibri-pricing", version="1.0.0")

FGIS_API_ORIGIN = "https://fgiscs.minstroyrf.ru"
FGIS_HOST = "fgiscs.minstroyrf.ru"
USER_AGENT = "KolibriAI-MCP/1.0 (+https://kolibriai.ru)"


# Reference prices for plastering (versioned snapshot)
PLASTERING_PRICES = {
    "survey": ("m2", "35.00"),
    "surface_cleaning": ("m2", "90.00"),
    "protection": ("m2", "48.00"),
    "primer_application": ("m2", "75.00"),
    "primer_material": ("l", "120.00"),
    "beacon_installation": ("m2", "160.00"),
    "beacon_profile": ("ea", "85.00"),
    "corner_installation": ("m", "95.00"),
    "corner_profile": ("ea", "95.00"),
    "mesh_installation": ("m2", "220.00"),
    "reinforcing_mesh": ("m2", "75.00"),
    "plaster_application": ("m2", "520.00"),
    "plaster_mix": ("bag", "470.00"),
    "water": ("m3", "180.00"),
    "electricity": ("kWh", "8.50"),
    "plaster_machine": ("shift", "8500.00"),
    "delivery": ("trip", "3500.00"),
    "lifting": ("t", "1800.00"),
    "slopes": ("m2", "1450.00"),
    "smoothing": ("m2", "140.00"),
    "quality_control": ("m2", "65.00"),
    "cleanup": ("m2", "65.00"),
    "waste_removal": ("trip", "6500.00"),
    "consumables": ("set", "8500.00"),
}


@server.tool(
    name="search_prices",
    description=(
        "Найти актуальные расценки на строительные работы и материалы. "
        "Ищет в ФГИС ЦС (федеральная система) и возвращает цены с источниками."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Поисковый запрос (например: 'штукатурка стен', 'бетон М300')",
            },
            "region": {
                "type": "string",
                "description": "Регион для поиска цен (например: 'Москва', 'Санкт-Петербург')",
                "default": "",
            },
        },
        "required": ["query"],
    },
)
def search_prices(query: str, region: str = "") -> dict:
    """Search FGIS CS for construction prices."""
    try:
        with httpx.Client(
            timeout=12,
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        ) as client:
            # Search FGIS CS
            search_url = f"{FGIS_API_ORIGIN}/api/prices/search"
            params = {"q": query, "limit": 10}
            if region:
                params["region"] = region

            response = client.get(search_url, params=params)

            if response.status_code == 200 and response.url.host == FGIS_HOST:
                data = response.json()
                items = data.get("items", data.get("results", []))

                prices = []
                for item in items[:10]:
                    prices.append({
                        "code": item.get("code", ""),
                        "name": item.get("name", item.get("title", "")),
                        "unit": item.get("unit", ""),
                        "price": item.get("price", item.get("basePrice", "")),
                        "region": item.get("region", region),
                        "source": "FGIS CS",
                    })

                if prices:
                    return {
                        "query": query,
                        "region": region or "all",
                        "count": len(prices),
                        "prices": prices,
                        "source_url": f"{FGIS_API_ORIGIN}/prices",
                    }

    except Exception:
        pass  # Fall through to reference prices

    # Fallback to reference prices
    matching = []
    query_lower = query.lower()
    for code, (unit, price) in PLASTERING_PRICES.items():
        if any(word in code or word in query_lower for word in query_lower.split()):
            matching.append({
                "code": code,
                "name": code.replace("_", " ").title(),
                "unit": unit,
                "price": price,
                "region": "reference",
                "source": "Kolibri reference snapshot (2026-07-29)",
            })

    return {
        "query": query,
        "region": region or "all",
        "count": len(matching),
        "prices": matching if matching else [
            {
                "code": "note",
                "name": "Расценки не найдены. Попробуйте более конкретный запрос.",
                "unit": "",
                "price": "",
                "region": "",
                "source": "",
            }
        ],
        "source_url": f"{FGIS_API_ORIGIN}/prices",
    }


@server.tool(
    name="get_reference_prices",
    description=(
        "Получить справочные расценки на штукатурные работы. "
        "Возвращает версионный снимок цен для типовых позиций."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "item_code": {
                "type": "string",
                "description": "Код позиции (например: 'plaster_application', 'primer_material'). Оставить пустым для всех позиций.",
                "default": "",
            },
        },
    },
)
def get_reference_prices(item_code: str = "") -> dict:
    """Get reference plastering prices."""
    if item_code:
        item = PLASTERING_PRICES.get(item_code)
        if item:
            unit, price = item
            return {
                "version": "plastering-reference/2026-07-29.1",
                "item": {
                    "code": item_code,
                    "name": item_code.replace("_", " ").title(),
                    "unit": unit,
                    "price": price,
                },
            }
        return {"error": f"Позиция '{item_code}' не найдена."}

    return {
        "version": "plastering-reference/2026-07-29.1",
        "valid_until": "2026-08-29",
        "items": [
            {
                "code": code,
                "name": code.replace("_", " ").title(),
                "unit": unit,
                "price": price,
            }
            for code, (unit, price) in sorted(PLASTERING_PRICES.items())
        ],
    }


if __name__ == "__main__":
    server.run()
