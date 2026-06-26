from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

CONTROL_PLANE_URL = os.environ.get("KOLIBRI_FACTORY_CONTROL_URL", "http://control.kolibri.internal:9101")


def _parse_mem_kb(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    parts = str(value).strip().split()
    if not parts:
        return 0
    try:
        number = float(parts[0])
    except ValueError:
        return 0
    unit = parts[1].lower() if len(parts) > 1 else "kb"
    if unit.startswith("gb"):
        return int(number * 1024 * 1024)
    if unit.startswith("mb"):
        return int(number * 1024)
    return int(number)


def _gb_from_kb(value: int) -> float:
    return round(value / 1024 / 1024, 1) if value else 0.0


def _gb_from_bytes(value: Any) -> float:
    if not isinstance(value, (int, float)):
        return 0.0
    return round(float(value) / 1024 / 1024 / 1024, 1)


def _role_from_capabilities(capabilities: list[str]) -> str:
    caps = set(capabilities or [])
    if "primary" in caps:
        return "Директор"
    if "orchestrator" in caps:
        return "Оркестратор"
    if "implementation" in caps or "generic_implementation" in caps:
        return "Инженер"
    if "review" in caps or "generic_review" in caps:
        return "Ревьюер"
    if "qa" in caps:
        return "Тестировщик"
    if "research" in caps or "knowledge-base" in caps:
        return "Исследователь"
    return "Наблюдатель"


def _human_name(node: dict[str, Any]) -> str:
    node_id = str(node.get("node_id") or node.get("id") or "node")
    names = {
        "primary-candidate": "Директор",
        "main": "Координатор",
        "new": "Ревьюер",
        "9fts": "Инженер",
        "uiap": "Знания",
        "qjns": "Тестировщик",
    }
    return names.get(node_id, node.get("hostname") or node_id)


def _node_card(node: dict[str, Any]) -> dict[str, Any]:
    ram = node.get("ram") or {}
    disk = node.get("disk") or {}
    capabilities = node.get("capabilities") or []
    total_kb = _parse_mem_kb(ram.get("MemTotal") if isinstance(ram, dict) else None)
    available_kb = _parse_mem_kb(ram.get("MemAvailable") if isinstance(ram, dict) else None)
    node_id = str(node.get("node_id") or node.get("id") or "unknown")
    return {
        "id": node_id,
        "node_id": node_id,
        "name": _human_name(node),
        "hostname": node.get("hostname") or node_id,
        "status": node.get("health") or "unknown",
        "role": _role_from_capabilities(capabilities),
        "agent_id": node.get("agent_id"),
        "pid": node.get("pid"),
        "cpu": node.get("cpu"),
        "ip": node.get("internal_ip") or node.get("ip") or node.get("hostname") or node_id,
        "ram": f"{_gb_from_kb(available_kb)}/{_gb_from_kb(total_kb)} GB",
        "ram_total_gb": _gb_from_kb(total_kb),
        "ram_available_gb": _gb_from_kb(available_kb),
        "disk_free_gb": _gb_from_bytes(disk.get("free") if isinstance(disk, dict) else None),
        "disk_total_gb": _gb_from_bytes(disk.get("total") if isinstance(disk, dict) else None),
        "capabilities": capabilities,
        "heartbeat_at": node.get("heartbeat_at"),
        "active_task": node.get("active_task"),
    }


def _extract_tasks(tasks_payload: Any) -> list[dict[str, Any]]:
    if isinstance(tasks_payload, list):
        return tasks_payload
    if isinstance(tasks_payload, dict):
        tasks = tasks_payload.get("tasks") or tasks_payload.get("items") or []
        if isinstance(tasks, dict):
            return list(tasks.values())
        if isinstance(tasks, list):
            return tasks
    return []


def build_factory_status(nodes_payload: Any, tasks_payload: Any | None = None, health_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    raw_nodes = nodes_payload.get("nodes", []) if isinstance(nodes_payload, dict) else nodes_payload if isinstance(nodes_payload, list) else []
    node_list = [_node_card(node) for node in raw_nodes if isinstance(node, dict)]
    nodes = {node["node_id"]: node for node in node_list}
    online_nodes = [node for node in node_list if node.get("status") == "online"]
    total_ram_kb = sum(_parse_mem_kb((node.get("ram") or {}).get("MemTotal")) for node in raw_nodes if isinstance(node, dict))
    available_ram_kb = sum(_parse_mem_kb((node.get("ram") or {}).get("MemAvailable")) for node in raw_nodes if isinstance(node, dict))
    cpu_values = [node.get("cpu") for node in raw_nodes if isinstance(node, dict) and isinstance(node.get("cpu"), (int, float))]
    tasks = _extract_tasks(tasks_payload)
    task_states: dict[str, int] = {}
    for task in tasks:
        state = str(task.get("state") or "unknown")
        task_states[state] = task_states.get(state, 0) + 1
    return {
        "status": "online" if online_nodes else "degraded",
        "source": "control-plane",
        "generated_at": (health_payload or {}).get("time") or datetime.now(timezone.utc).isoformat(),
        "control_plane": {
            "url": CONTROL_PLANE_URL,
            "status": (health_payload or {}).get("status", "unknown"),
            "queue_backend": (health_payload or {}).get("queue_backend"),
            "redis": (health_payload or {}).get("redis"),
        },
        "total_nodes": len(node_list),
        "online_nodes": len(online_nodes),
        "free_ram_gb": _gb_from_kb(available_ram_kb),
        "total_ram_gb": _gb_from_kb(total_ram_kb),
        "avg_cpu_percent": round(sum(cpu_values) / len(cpu_values), 1) if cpu_values else 0,
        "queue_size": sum(task_states.get(state, 0) for state in ("queued", "leased", "running")),
        "task_states": task_states,
        "nodes": nodes,
        "node_list": node_list,
    }


async def fetch_factory_status() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=8.0) as client:
        health_response = await client.get(f"{CONTROL_PLANE_URL}/health")
        nodes_response = await client.get(f"{CONTROL_PLANE_URL}/v1/nodes")
        health_response.raise_for_status()
        nodes_response.raise_for_status()
        try:
            tasks_response = await client.get(f"{CONTROL_PLANE_URL}/v1/tasks")
            tasks_payload: Any = tasks_response.json() if tasks_response.status_code == 200 else {"tasks": []}
        except Exception:
            tasks_payload = {"tasks": []}
    return build_factory_status(nodes_response.json(), tasks_payload, health_response.json())
