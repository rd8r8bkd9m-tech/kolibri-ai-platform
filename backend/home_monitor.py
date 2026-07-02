from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from factory_status import (
    build_factory_status,
    fetch_factory_status,
)

HOME_MONITOR_PREFERENCES = {
    "ai_runner": "mimo-auto",
    "owner_language": "ru",
    "display_format": "wallboard",
    "auto_refresh_seconds": 15,
    "default_task_runner": "mimo",
}

WALLBOARD_STATUS_LABELS = {
    "fresh": "Онлайн",
    "degraded": "Деградация",
    "stale": "Устарел",
    "online": "Онлайн",
    "unknown": "Неизвестно",
}

TASK_STATE_LABELS = {
    "queued": "В очереди",
    "leased": "Арендован",
    "running": "Выполняется",
    "waiting_review": "Ожидает ревью",
    "review": "На ревью",
    "completed": "Завершена",
    "failed": "Ошибка",
    "cancelled": "Отменена",
    "retry_scheduled": "Повтор",
    "dead_letter": "Мёртвая очередь",
}


def _task_summary(task: dict[str, Any]) -> dict[str, Any]:
    state = str(task.get("state") or "unknown")
    lease_owner = task.get("lease_owner") or ""
    node_id = lease_owner.split(":", 1)[0] if lease_owner else None
    return {
        "task_id": task.get("task_id", ""),
        "kind": task.get("kind", ""),
        "state": state,
        "state_label": TASK_STATE_LABELS.get(state, state),
        "node_id": node_id,
        "attempt": task.get("attempt", 0),
        "created_at": task.get("created_at", ""),
        "updated_at": task.get("updated_at", ""),
        "objective": (task.get("envelope") or {}).get("objective", ""),
        "error_type": task.get("error_type"),
    }


def build_home_monitor_status(factory_status: dict[str, Any]) -> dict[str, Any]:
    node_list = factory_status.get("node_list", [])
    task_states = factory_status.get("task_states", {})
    nodes_with_tasks: list[dict[str, Any]] = []
    for node in node_list:
        active = node.get("active_task")
        nodes_with_tasks.append({
            "node_id": node.get("node_id", ""),
            "name": node.get("name", ""),
            "role": node.get("role", ""),
            "status": node.get("status", "unknown"),
            "freshness": node.get("freshness", "unknown"),
            "health": node.get("health", "unknown"),
            "status_label": WALLBOARD_STATUS_LABELS.get(node.get("freshness", "unknown"), "Неизвестно"),
            "active_task": active,
            "ram": node.get("ram", "0/0 GB"),
            "cpu": node.get("cpu"),
        })

    total_tasks = sum(task_states.values()) if task_states else 0
    active_tasks = sum(task_states.get(s, 0) for s in ("queued", "leased", "running", "review", "waiting_review"))
    completed_tasks = task_states.get("completed", 0)
    failed_tasks = task_states.get("failed", 0)

    return {
        "status": factory_status.get("status", "unknown"),
        "generated_at": factory_status.get("generated_at", datetime.now(timezone.utc).isoformat()),
        "preferences": HOME_MONITOR_PREFERENCES,
        "fleet": {
            "total_nodes": factory_status.get("total_nodes", 0),
            "fresh_nodes": factory_status.get("fresh_nodes", 0),
            "degraded_nodes": factory_status.get("degraded_nodes", 0),
            "stale_nodes": factory_status.get("stale_nodes", 0),
            "free_ram_gb": factory_status.get("free_ram_gb", 0),
            "total_ram_gb": factory_status.get("total_ram_gb", 0),
            "avg_cpu_percent": factory_status.get("avg_cpu_percent", 0),
        },
        "tasks": {
            "total": total_tasks,
            "active": active_tasks,
            "completed": completed_tasks,
            "failed": failed_tasks,
            "queue_size": factory_status.get("queue_size", 0),
            "states": task_states,
        },
        "nodes": nodes_with_tasks,
        "control_plane": factory_status.get("control_plane", {}),
    }


def build_wallboard(factory_status: dict[str, Any], tasks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    monitor = build_home_monitor_status(factory_status)
    wallboard_tasks = [_task_summary(t) for t in (tasks or [])]
    wallboard_tasks.sort(key=lambda t: (
        {"queued": 0, "leased": 1, "running": 2, "waiting_review": 3, "review": 4,
         "completed": 5, "failed": 6, "cancelled": 7, "retry_scheduled": 8, "dead_letter": 9
         }.get(t["state"], 5),
        t.get("updated_at", ""),
    ))
    monitor["wallboard"] = {
        "tasks": wallboard_tasks,
        "task_count": len(wallboard_tasks),
    }
    return monitor


async def fetch_home_monitor() -> dict[str, Any]:
    factory_status = await fetch_factory_status()
    return build_home_monitor_status(factory_status)


async def fetch_wallboard() -> dict[str, Any]:
    factory_status = await fetch_factory_status()
    tasks_raw = factory_status.get("task_states", {})
    return build_wallboard(factory_status, [])
