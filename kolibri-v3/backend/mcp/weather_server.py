"""MCP server for weather queries.

Wraps Open-Meteo API for geocoding and weather forecasting.
Compatible with Codex CLI and MiMo Code MCP support.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.mcp.base import MCPServer

import httpx

server = MCPServer(name="kolibri-weather", version="1.0.0")

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE_URL = "https://open-meteo.com/"


@server.tool(
    name="get_weather",
    description=(
        "Получить текущую погоду и прогноз для любого населённого пункта. "
        "Возвращает температуру, влажность, осадки, ветер и прогноз на несколько дней."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "Название населённого пункта (например: Москва, Санкт-Петербург, Казань)",
            },
            "forecast_days": {
                "type": "integer",
                "description": "Количество дней прогноза (1-7, по умолчанию 5)",
                "minimum": 1,
                "maximum": 7,
                "default": 5,
            },
        },
        "required": ["location"],
    },
)
def get_weather(location: str, forecast_days: int = 5) -> dict:
    """Fetch weather from Open-Meteo API."""
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        # Geocode
        geo = client.get(
            GEOCODING_URL,
            params={
                "name": location,
                "count": 3,
                "language": "ru",
                "format": "json",
            },
        )
        geo.raise_for_status()
        geo_data = geo.json()

        results = geo_data.get("results", [])
        if not results:
            return {"error": f"Населённый пункт «{location}» не найден."}

        place = results[0]
        lat = place.get("latitude")
        lon = place.get("longitude")
        place_name = place.get("name", location)
        country = place.get("country", "")

        # Forecast
        forecast = client.get(
            FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": (
                    "temperature_2m,apparent_temperature,"
                    "relative_humidity_2m,precipitation,"
                    "weather_code,wind_speed_10m,is_day"
                ),
                "daily": (
                    "temperature_2m_max,temperature_2m_min,"
                    "precipitation_sum,weather_code,wind_speed_10m_max"
                ),
                "forecast_days": forecast_days,
                "timezone": "auto",
            },
        )
        forecast.raise_for_status()
        data = forecast.json()

        current = data.get("current", {})
        daily = data.get("daily", {})

        # Build daily forecast
        daily_forecast = []
        dates = daily.get("time", [])
        for i, date in enumerate(dates):
            daily_forecast.append({
                "date": date,
                "temp_max": daily.get("temperature_2m_max", [None])[i],
                "temp_min": daily.get("temperature_2m_min", [None])[i],
                "precipitation_mm": daily.get("precipitation_sum", [0])[i],
                "wind_max_kmh": daily.get("wind_speed_10m_max", [None])[i],
            })

        return {
            "location": f"{place_name}, {country}" if country else place_name,
            "coordinates": {"latitude": lat, "longitude": lon},
            "current": {
                "temperature_c": current.get("temperature_2m"),
                "feels_like_c": current.get("apparent_temperature"),
                "humidity_pct": current.get("relative_humidity_2m"),
                "precipitation_mm": current.get("precipitation"),
                "wind_speed_kmh": current.get("wind_speed_10m"),
                "is_day": bool(current.get("is_day")),
            },
            "forecast": daily_forecast,
            "sources": [{"label": "Open-Meteo", "url": SOURCE_URL}],
        }


if __name__ == "__main__":
    server.run()
