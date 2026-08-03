"""MCP server configuration for Codex CLI and MiMo Code runtimes.

Builds the MCP server configuration that Codex CLI and MiMo Code
use to discover and connect to Kolibri's MCP tool servers.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


# Default MCP server scripts (relative to kolibri-v3/)
_MCP_DIR = Path(__file__).resolve().parents[1] / "mcp"


def _mcp_server_path(name: str) -> str:
    """Get absolute path to an MCP server script."""
    return str(_MCP_DIR / f"{name}_server.py")


def build_mcp_servers_config() -> dict[str, Any]:
    """Build MCP servers configuration for Codex CLI.

    Returns a dict suitable for `-c mcp_servers=...` argument.
    Each server runs as a stdio subprocess.
    """
    servers: dict[str, Any] = {}

    # Weather MCP server
    weather_path = _mcp_server_path("weather")
    if os.path.exists(weather_path):
        servers["kolibri-weather"] = {
            "command": "python3",
            "args": [weather_path],
        }

    # Pricing MCP server
    pricing_path = _mcp_server_path("pricing")
    if os.path.exists(pricing_path):
        servers["kolibri-pricing"] = {
            "command": "python3",
            "args": [pricing_path],
        }

    # Normative MCP server
    normative_path = _mcp_server_path("normative")
    if os.path.exists(normative_path):
        servers["kolibri-normative"] = {
            "command": "python3",
            "args": [normative_path],
        }

    return servers


def mcp_servers_json() -> str:
    """Return MCP servers config as JSON string for CLI argument."""
    return json.dumps(build_mcp_servers_config(), ensure_ascii=False)
