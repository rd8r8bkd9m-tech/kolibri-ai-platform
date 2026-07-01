from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

CONTROL_PLANE_URL = os.getenv("KOLIBRI_FACTORY_CONTROL_URL", "http://control.kolibri.internal:9101")


def _control_plane_v1_url(path: str) -> str:
    base = CONTROL_PLANE_URL.rstrip("/")
    suffix = path if path.startswith("/") else f"/{path}"
    if base.endswith("/v1"):
        return f"{base}{suffix}"
    return f"{base}/v1{suffix}"


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
    scheduler_capacity = node.get("scheduler_capacity") or {}
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
        "scheduler_capacity": scheduler_capacity,
        "capacity": scheduler_capacity.get("capacity", 0),
        "available_capacity": scheduler_capacity.get("available", 0),
        "readiness": scheduler_capacity.get("readiness", "unknown"),
        "blockers": scheduler_capacity.get("blockers", []),
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


def build_factory_status(
    nodes_payload: Any,
    tasks_payload: Any | None = None,
    health_payload: dict[str, Any] | None = None,
    mesh_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    live_tasks = (mesh_payload or {}).get("live_tasks")
    if not isinstance(live_tasks, list):
        live_tasks = [
            {
                "task_id": task.get("task_id"),
                "state": task.get("state"),
                "kind": task.get("kind") or (task.get("envelope") or {}).get("kind"),
                "lease_owner": task.get("lease_owner"),
                "result_reference": task.get("result_reference"),
                "error_type": task.get("error_type"),
            }
            for task in tasks
            if isinstance(task, dict) and task.get("state") not in {"completed", "failed", "cancelled", "dead_letter"}
        ]
    scheduler_capacity = sum(int((node.get("scheduler_capacity") or {}).get("capacity") or 0) for node in node_list)
    available_capacity = sum(int((node.get("scheduler_capacity") or {}).get("available") or 0) for node in node_list)
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
        "queue_size": (
            sum(task_states.get(state, 0) for state in ("queued", "leased", "running"))
            if task_states
            else int((health_payload or {}).get("queue") or 0)
        ),
        "task_states": task_states,
        "live_tasks": live_tasks,
        "blockers": (mesh_payload or {}).get("blockers") or [
            {"node_id": node["node_id"], "blockers": node.get("blockers", [])}
            for node in node_list
            if node.get("blockers")
        ],
        "global_logical_agent_target": (mesh_payload or health_payload or {}).get("global_logical_agent_target", 1000),
        "global_scheduler_capacity": (mesh_payload or {}).get("global_scheduler_capacity", scheduler_capacity),
        "global_available_capacity": (mesh_payload or {}).get("global_available_capacity", available_capacity),
        "max_node_subagent_target": (mesh_payload or {}).get("max_node_subagent_target", 20),
        "next_dispatch_wave": (mesh_payload or {}).get("next_dispatch_wave", {
            "available_slots": available_capacity,
            "queued": task_states.get("queued", 0),
            "dispatchable": min(available_capacity, task_states.get("queued", 0)),
        }),
        "nodes": nodes,
        "node_list": node_list,
    }


async def fetch_factory_status() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(4.0, connect=2.0)) as client:
        health_response = await client.get(_control_plane_v1_url("/health"))
        nodes_response = await client.get(_control_plane_v1_url("/nodes"))
        health_response.raise_for_status()
        nodes_response.raise_for_status()

    tasks_payload: Any = {"tasks": []}
    mesh_payload: dict[str, Any] = {}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(1.5, connect=1.0)) as client:
            tasks_response = await client.get(_control_plane_v1_url("/tasks"))
            if tasks_response.status_code == 200:
                tasks_payload = tasks_response.json()
    except Exception:
        tasks_payload = {"tasks": []}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(1.5, connect=1.0)) as client:
            mesh_response = await client.get(_control_plane_v1_url("/mesh/status"))
            if mesh_response.status_code == 200:
                mesh_payload = mesh_response.json()
    except Exception:
        mesh_payload = {}

    return build_factory_status(nodes_response.json(), tasks_payload, health_response.json(), mesh_payload)
