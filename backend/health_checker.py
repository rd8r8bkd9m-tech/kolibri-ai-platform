"""Periodic health checker for Kolibri cluster nodes.

Pings all cluster nodes via VPN every 30 seconds and caches their status.
The cached status is used by /api/v1/cluster to avoid blocking requests.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Dict, Any

import httpx

from logging_config import get_logger

logger = get_logger("health_checker")

CHECK_INTERVAL = 30
HEALTH_TIMEOUT = 5.0

_cache: Dict[str, Dict[str, Any]] = {}
_lock = asyncio.Lock()

CONFIG_PATH = Path(__file__).parent.parent / "infra" / "network" / "config.json"


def _load_server_list() -> list[dict]:
    try:
        config = json.loads(CONFIG_PATH.read_text())
        servers = config.get("servers", {})
        return [
            {"name": name, "vpn_ip": s.get("vpn_ip", ""), "role": s.get("role", "unknown")}
            for name, s in servers.items()
            if s.get("vpn_ip")
        ]
    except Exception as exc:
        logger.error(f"Failed to load cluster config: {exc}")
        return []


async def _check_node(vpn_ip: str) -> Dict[str, Any]:
    """Ping a single node's common health endpoints."""
    endpoints = [
        f"http://{vpn_ip}:8000/api/health",
        f"http://{vpn_ip}:8001/inference/health",
        f"http://{vpn_ip}:8002/rag/health",
        f"http://{vpn_ip}:8003/agent/health",
    ]
    async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT) as client:
        for url in endpoints:
            try:
                start = time.time()
                resp = await client.get(url)
                latency_ms = round((time.time() - start) * 1000, 1)
                if resp.status_code == 200:
                    return {"status": "ok", "latency_ms": latency_ms, "last_check": time.time()}
            except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
                continue
    return {"status": "down", "latency_ms": None, "last_check": time.time()}


async def _run_check_cycle():
    """Check all nodes and update cache."""
    servers = _load_server_list()
    if not servers:
        return

    results = await asyncio.gather(
        *[_check_node(s["vpn_ip"]) for s in servers],
        return_exceptions=True,
    )

    async with _lock:
        for server, result in zip(servers, results):
            if isinstance(result, Exception):
                _cache[server["vpn_ip"]] = {
                    "status": "error",
                    "latency_ms": None,
                    "last_check": time.time(),
                }
            else:
                _cache[server["vpn_ip"]] = result


async def _checker_loop():
    """Run health checks in a loop."""
    while True:
        try:
            await _run_check_cycle()
        except Exception as exc:
            logger.error(f"Health check cycle failed: {exc}", exc_info=True)
        await asyncio.sleep(CHECK_INTERVAL)


async def start_health_checker() -> asyncio.Task:
    """Start the background health checker. Returns the task for cancellation."""
    logger.info("Starting cluster health checker")
    task = asyncio.create_task(_checker_loop())
    return task


def get_cached_health() -> Dict[str, Dict[str, Any]]:
    """Return the current cached health status for all nodes."""
    return dict(_cache)
