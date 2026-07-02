from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

CONTROL_PLANE_URL = os.getenv("KOLIBRI_FACTORY_CONTROL_URL", "http://control.kolibri.internal:9101")
NODE_DEGRADED_AFTER = int(os.getenv("FACTORY_NODE_DEGRADED_AFTER", "30"))
NODE_STALE_AFTER = int(os.getenv("FACTORY_NODE_STALE_AFTER", "90"))


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


def _parse_iso_ts(value: Any) -> float | None:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError):
        return None


def _node_freshness(node: dict[str, Any], generated_at: str | None = None) -> tuple[str, int | None]:
    current = _parse_iso_ts(generated_at) or datetime.now(timezone.utc).timestamp()
    heartbeat = _parse_iso_ts(node.get("heartbeat_at"))
    if heartbeat is None:
        return "stale", None
    age = max(0, int(current - heartbeat))
    if age > NODE_STALE_AFTER:
        return "stale", age
    if age > NODE_DEGRADED_AFTER:
        return "degraded", age
    return "fresh", age


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


def _node_card(node: dict[str, Any], generated_at: str | None = None) -> dict[str, Any]:
    ram = node.get("ram") or {}
    disk = node.get("disk") or {}
    capabilities = node.get("capabilities") or []
    total_kb = _parse_mem_kb(ram.get("MemTotal") if isinstance(ram, dict) else None)
    available_kb = _parse_mem_kb(ram.get("MemAvailable") if isinstance(ram, dict) else None)
    node_id = str(node.get("node_id") or node.get("id") or "unknown")
    freshness = node.get("freshness")
    heartbeat_age = node.get("heartbeat_age_seconds")
    if freshness not in {"fresh", "degraded", "stale"}:
        freshness, heartbeat_age = _node_freshness(node, generated_at)
    reported_health = node.get("reported_health") or node.get("health") or "unknown"
    status = reported_health if freshness == "fresh" else freshness
    return {
        "id": node_id,
        "node_id": node_id,
        "name": _human_name(node),
        "hostname": node.get("hostname") or node_id,
        "status": status,
        "health": status,
        "reported_health": reported_health,
        "freshness": freshness,
        "heartbeat_age_seconds": heartbeat_age,
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


def _task_title(task: dict[str, Any]) -> str:
    envelope = task.get("envelope") if isinstance(task.get("envelope"), dict) else {}
    for key_name in ("title", "objective", "message", "kind"):
        value = envelope.get(key_name) or task.get(key_name)
        if value:
            return str(value)
    return str(task.get("task_id") or "Factory task")


def _task_node(task: dict[str, Any]) -> str:
    lease_owner = str(task.get("lease_owner") or "")
    if lease_owner:
        return lease_owner.split(":", 1)[0]
    envelope = task.get("envelope") if isinstance(task.get("envelope"), dict) else {}
    return str(envelope.get("target_node") or envelope.get("required_node") or "unassigned")


def _task_pr_url(task: dict[str, Any]) -> str:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    envelope = task.get("envelope") if isinstance(task.get("envelope"), dict) else {}
    return str(
        result.get("pull_request_url")
        or result.get("pr_url")
        or envelope.get("pull_request_url")
        or envelope.get("pr_url")
        or ""
    )


def _task_branch(task: dict[str, Any]) -> str:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    envelope = task.get("envelope") if isinstance(task.get("envelope"), dict) else {}
    return str(result.get("branch") or envelope.get("branch") or "")


def _task_card(task: dict[str, Any]) -> dict[str, Any]:
    state = str(task.get("state") or "unknown")
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    error = task.get("error") or result.get("error") or ""
    error_type = task.get("error_type") or result.get("error_type") or ""
    blocked = state in {"blocked", "failed", "dead_letter"} or bool(error_type)
    return {
        "task_id": str(task.get("task_id") or task.get("id") or ""),
        "title": _task_title(task),
        "kind": str(task.get("kind") or (task.get("envelope") or {}).get("kind") or "task"),
        "state": state,
        "node": _task_node(task),
        "updated_at": task.get("updated_at") or task.get("created_at"),
        "created_at": task.get("created_at"),
        "attempt": task.get("attempt"),
        "max_retries": task.get("max_retries"),
        "pr_url": _task_pr_url(task),
        "branch": _task_branch(task),
        "blocked": blocked,
        "blocker": {
            "task_id": str(task.get("task_id") or task.get("id") or ""),
            "reason": str(error_type or state if blocked else ""),
            "detail": str(error or ""),
            "node": _task_node(task),
            "repair_task": result.get("repair_task") if isinstance(result.get("repair_task"), dict) else None,
        } if blocked else None,
    }


def _pr_cards(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prs = []
    for task in tasks:
        pr_url = _task_pr_url(task)
        if not pr_url:
            continue
        prs.append({
            "task_id": str(task.get("task_id") or task.get("id") or ""),
            "title": _task_title(task),
            "url": pr_url,
            "branch": _task_branch(task),
            "state": str(task.get("state") or "unknown"),
            "node": _task_node(task),
            "updated_at": task.get("updated_at") or task.get("created_at"),
        })
    return prs


def _dashboard_actions(status: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "refresh_status",
            "label": "Refresh status",
            "method": "GET",
            "safe": True,
            "enabled": True,
            "description": "Reload fleet, task, PR, and blocker data.",
        },
        {
            "id": "launch_readiness_probe",
            "label": "Launch readiness probe",
            "method": "POST",
            "safe": True,
            "enabled": status != "offline",
            "description": "Queue a read-only factory probe through the control plane.",
        },
    ]


def build_factory_status(nodes_payload: Any, tasks_payload: Any | None = None, health_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    raw_nodes = nodes_payload.get("nodes", []) if isinstance(nodes_payload, dict) else nodes_payload if isinstance(nodes_payload, list) else []
    generated_at = (health_payload or {}).get("time") or datetime.now(timezone.utc).isoformat()
    node_list = [_node_card(node, generated_at) for node in raw_nodes if isinstance(node, dict)]
    nodes = {node["node_id"]: node for node in node_list}
    online_nodes = [node for node in node_list if node.get("status") == "online"]
    fresh_nodes = [node for node in node_list if node.get("freshness") == "fresh"]
    degraded_nodes = [node for node in node_list if node.get("freshness") == "degraded"]
    stale_nodes = [node for node in node_list if node.get("freshness") == "stale"]
    total_ram_kb = sum(_parse_mem_kb((node.get("ram") or {}).get("MemTotal")) for node in raw_nodes if isinstance(node, dict))
    available_ram_kb = sum(_parse_mem_kb((node.get("ram") or {}).get("MemAvailable")) for node in raw_nodes if isinstance(node, dict))
    cpu_values = [node.get("cpu") for node in raw_nodes if isinstance(node, dict) and isinstance(node.get("cpu"), (int, float))]
    tasks = _extract_tasks(tasks_payload)
    task_cards = [_task_card(task) for task in tasks if isinstance(task, dict)]
    blockers = [task["blocker"] for task in task_cards if task.get("blocker")]
    pr_cards = _pr_cards(tasks)
    task_states: dict[str, int] = {}
    for task in task_cards:
        state = str(task.get("state") or "unknown")
        task_states[state] = task_states.get(state, 0) + 1
    normalized_status = "online" if online_nodes else "degraded"
    return {
        "status": normalized_status,
        "source": "control-plane",
        "generated_at": generated_at,
        "control_plane": {
            "url": CONTROL_PLANE_URL,
            "status": (health_payload or {}).get("status", "unknown"),
            "queue_backend": (health_payload or {}).get("queue_backend"),
            "redis": (health_payload or {}).get("redis"),
        },
        "total_nodes": len(node_list),
        "online_nodes": len(online_nodes),
        "fresh_nodes": len(fresh_nodes),
        "degraded_nodes": len(degraded_nodes),
        "stale_nodes": len(stale_nodes),
        "node_freshness": {
            "fresh": len(fresh_nodes),
            "degraded": len(degraded_nodes),
            "stale": len(stale_nodes),
            "online": len(online_nodes),
            "total": len(node_list),
        },
        "free_ram_gb": _gb_from_kb(available_ram_kb),
        "total_ram_gb": _gb_from_kb(total_ram_kb),
        "avg_cpu_percent": round(sum(cpu_values) / len(cpu_values), 1) if cpu_values else 0,
        "queue_size": (
            sum(task_states.get(state, 0) for state in ("queued", "leased", "running"))
            if task_states
            else int((health_payload or {}).get("queue") or 0)
        ),
        "task_states": task_states,
        "tasks": task_cards,
        "recent_tasks": task_cards[:12],
        "pull_requests": pr_cards,
        "blockers": blockers,
        "agents": node_list,
        "safe_actions": _dashboard_actions(normalized_status),
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
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(1.5, connect=1.0)) as client:
            tasks_response = await client.get(_control_plane_v1_url("/tasks"))
            if tasks_response.status_code == 200:
                tasks_payload = tasks_response.json()
    except Exception:
        tasks_payload = {"tasks": []}

    return build_factory_status(nodes_response.json(), tasks_payload, health_response.json())


async def submit_factory_dashboard_action(action: str) -> dict[str, Any]:
    if action != "launch_readiness_probe":
        raise ValueError("unsupported_factory_dashboard_action")

    payload = {
        "kind": "read_only_probe",
        "objective": "Collect a read-only Kolibri Factory readiness snapshot for the owner dashboard.",
        "required_capability": "generic_implementation",
        "source": "kolibri_factory_dashboard",
        "write_scope": [],
        "fallback_allowed": True,
        "max_retries": 1,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(4.0, connect=2.0)) as client:
        response = await client.post(_control_plane_v1_url("/agents/tasks"), json=payload)
        response.raise_for_status()
        return response.json()
