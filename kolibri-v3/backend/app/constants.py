"""Single source of truth for repeated constants across Kolibri V3 backend.

Every module that needs a URL, timeout, model name, or domain constant
imports from here instead of hardcoding the value.  Environment variables
still override these at runtime via ``config.py`` — this module provides
the *defaults* only.
"""

from __future__ import annotations

from decimal import Decimal

# ---------------------------------------------------------------------------
# AI provider URLs and model identifiers
# ---------------------------------------------------------------------------

MIMO_BASE_URL_DEFAULT: str = (
    "https://token-plan-sgp.xiaomimimo.com/v1"
)
MIMO_MODEL_DEFAULT: str = "mimo-v2.5-pro"
MIMO_MODEL_DISPLAY: str = "MiMo 2.5 Pro"
MIMO_DEVELOPER_MODEL_DEFAULT: str = (
    "xiaomi-token-plan-sgp/mimo-v2.5-pro"
)

CODEX_MODEL_DEFAULT: str = "gpt-5.5"

# ---------------------------------------------------------------------------
# External service URLs
# ---------------------------------------------------------------------------

FGIS_API_ORIGIN: str = "https://fgiscs.minstroyrf.ru"
FGIS_HOST: str = "fgiscs.minstroyrf.ru"
FGIS_PUBLIC_PRICES_URL: str = f"{FGIS_API_ORIGIN}/prices"
FGIS_AUTHORITY_INFO_URL: str = (
    "https://minstroyrf.gov.ru/trades/tsenoobrazovanie/"
)

OPEN_METEO_GEOCODING_URL: str = (
    "https://geocoding-api.open-meteo.com/v1/search"
)
OPEN_METEO_FORECAST_URL: str = (
    "https://api.open-meteo.com/v1/forecast"
)
OPEN_METEO_SOURCE_URL: str = "https://open-meteo.com/"

# ---------------------------------------------------------------------------
# User-Agent strings
# ---------------------------------------------------------------------------

USER_AGENT_KOLIBRI_ESTIMATE: str = (
    "KolibriAI-Estimate/1.0 (+https://kolibriai.ru)"
)
USER_AGENT_RELEASE_MONITOR: str = "kolibri-monitor/1"
USER_AGENT_NORMATIVE_CORPUS: str = "Kolibri-Normative-Corpus/1.0"

# ---------------------------------------------------------------------------
# HTTP timeouts (seconds)
# ---------------------------------------------------------------------------

TIMEOUT_HTTP_DEFAULT: float = 15.0
TIMEOUT_HTTP_CONNECT: float = 8.0
TIMEOUT_FGIS: float = 12.0
TIMEOUT_FGIS_CONNECT: float = 4.0
TIMEOUT_NORMATIVE: float = 20.0
TIMEOUT_NORMATIVE_CONNECT: float = 8.0
TIMEOUT_MODEL_CATALOG: float = 10.0
TIMEOUT_MIMO_CLIENT_CONNECT: float = 10.0
TIMEOUT_WEATHER_MIN: float = 5.0
TIMEOUT_WEATHER_MAX: float = 15.0
TIMEOUT_WEATHER_CONNECT: float = 5.0

# ---------------------------------------------------------------------------
# PDF theme colours (ReportLab HexColor)
# ---------------------------------------------------------------------------

PDF_COLOR_INK: str = "#10241D"
PDF_COLOR_TEAL: str = "#128F88"
PDF_COLOR_MUTED: str = "#66756D"
PDF_COLOR_BORDER_LIGHT: str = "#D7DEDA"
PDF_COLOR_SURFACE: str = "#F2F5F3"
PDF_COLOR_DIVIDER: str = "#E5EBE8"
PDF_COLOR_BORDER: str = "#A8B4AE"
PDF_COLOR_TEXT: str = "#111111"

# ---------------------------------------------------------------------------
# Construction estimate defaults (Decimal for precise arithmetic)
# ---------------------------------------------------------------------------

# Plastering intake defaults
DEFAULT_PLASTER_THICKNESS_MM: Decimal = Decimal("15")
DEFAULT_WASTE_PCT: Decimal = Decimal("10")
DEFAULT_WALL_AREA_MULTIPLIER: Decimal = Decimal("0.25")
DEFAULT_ROOM_HEIGHT_M: Decimal = Decimal("3")
DEFAULT_BEACON_SPACING_M: Decimal = Decimal("1.5")
DEFAULT_MESH_COVERAGE: Decimal = Decimal("10")
DEFAULT_BAG_WEIGHT_KG: Decimal = Decimal("30")

# Catalog statistics
CATALOG_PERCENTILE_Q1: Decimal = Decimal("0.25")
CATALOG_IQR_FENCE: Decimal = Decimal("1.5")
