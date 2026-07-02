from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

CONTROL_PLANE_URL = os.getenv("KOLIBRI_FACTORY_CONTROL_URL", "http://control.kolibri.internal:9101")
NODE_DEGRADED_AFTER = int(os.getenv("FACTORY_NODE_DEGRADED_AFTER", "30"))
NODE_STALE_AFTER = int(os.getenv("FACTORY_NODE_STALE_AFTER", "90"))
RECENT_LIMIT = int(os.getenv("FACTORY_WALLBOARD_RECENT_LIMIT", "8"))
REPO_ROOT = Path(os.getenv("KOLIBRI_REPO_ROOT", Path(__file__).resolve().parents[1]))


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


def _short_text(value: Any, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    return text[: limit - 1] + "…" if len(text) > limit else text


def _normalize_tasks(tasks_payload: Any) -> list[dict[str, Any]]:
    tasks = _extract_tasks(tasks_payload)
    normalized = []
    for index, task in enumerate(tasks[:RECENT_LIMIT]):
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id") or task.get("task_id") or task.get("lease_id") or f"task-{index + 1}")
        state = str(task.get("state") or task.get("status") or "unknown")
        normalized.append(
            {
                "id": task_id,
                "title": _short_text(task.get("title") or task.get("goal") or task.get("role_goal") or task_id, 96),
                "state": state,
                "assignee": task.get("assignee") or task.get("node_id") or task.get("leased_by") or task.get("agent_id"),
                "updated_at": task.get("updated_at") or task.get("leased_at") or task.get("created_at"),
                "priority": task.get("priority") or task.get("severity"),
            }
        )
    return normalized


def _extract_items(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in keys:
            items = payload.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
            if isinstance(items, dict):
                return [item for item in items.values() if isinstance(item, dict)]
    return []


def _read_recent_run_results(limit: int = RECENT_LIMIT) -> list[dict[str, Any]]:
    runs_dir = REPO_ROOT / "docs" / "agent" / "runs"
    if not runs_dir.exists():
        return []
    results = []
    for result_path in sorted(runs_dir.glob("*/RESULT.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            text = result_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = [line.strip(" #*\t") for line in text.splitlines() if line.strip()]
        title = lines[0] if lines else result_path.parent.name
        lower = text.lower()
        status = "blocked" if "blocked" in lower or "блок" in lower else "done" if "complete" in lower or "готов" in lower else "note"
        results.append(
            {
                "id": result_path.parent.name,
                "title": _short_text(title, 110),
                "status": status,
                "path": str(result_path.relative_to(REPO_ROOT)),
                "summary": _short_text(" ".join(lines[1:4]) if len(lines) > 1 else title, 220),
            }
        )
    return results


def _normalize_blockers(blockers_payload: Any | None, health_payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    blockers = _extract_items(blockers_payload, ("blockers", "items", "problems"))
    normalized = []
    for index, blocker in enumerate(blockers[:RECENT_LIMIT]):
        normalized.append(
            {
                "id": str(blocker.get("id") or blocker.get("key") or f"blocker-{index + 1}"),
                "title": _short_text(blocker.get("title") or blocker.get("reason") or blocker.get("summary") or "Блокер", 110),
                "severity": blocker.get("severity") or blocker.get("priority") or "unknown",
                "owner": blocker.get("owner") or blocker.get("node_id") or blocker.get("assignee"),
                "repair": _short_text(blocker.get("repair") or blocker.get("repair_command") or blocker.get("next_action"), 180),
            }
        )
    cp_status = (health_payload or {}).get("status")
    if cp_status and cp_status != "ok":
        normalized.insert(
            0,
            {
                "id": "control-plane-health",
                "title": "Control Plane сообщает о деградации",
                "severity": "high",
                "owner": "factory-control",
                "repair": "Проверить /v1/health, очередь и systemd-сервис kolibri-factory-control.",
            },
        )
    return normalized[:RECENT_LIMIT]


def _normalize_prs(prs_payload: Any | None) -> list[dict[str, Any]]:
    prs = _extract_items(prs_payload, ("prs", "pull_requests", "items"))
    normalized = []
    for index, pr in enumerate(prs[:RECENT_LIMIT]):
        number = pr.get("number") or pr.get("id") or index + 1
        normalized.append(
            {
                "number": number,
                "title": _short_text(pr.get("title") or pr.get("head") or f"PR {number}", 110),
                "state": pr.get("state") or pr.get("status") or "unknown",
                "checks": pr.get("checks") or pr.get("ci") or pr.get("check_state"),
                "url": pr.get("url") or pr.get("html_url"),
                "updated_at": pr.get("updated_at") or pr.get("created_at"),
            }
        )
    return normalized


def _normalize_logs(logs_payload: Any | None, fallback_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    logs = _extract_items(logs_payload, ("logs", "events", "items"))
    normalized = []
    for index, log in enumerate(logs[:RECENT_LIMIT]):
        normalized.append(
            {
                "id": str(log.get("id") or f"log-{index + 1}"),
                "level": log.get("level") or log.get("severity") or "info",
                "source": log.get("source") or log.get("service") or log.get("node_id") or "control-plane",
                "message": _short_text(log.get("message") or log.get("summary") or log.get("event"), 160),
                "time": log.get("time") or log.get("timestamp") or log.get("created_at"),
            }
        )
    if normalized:
        return normalized
    return [
        {
            "id": item["id"],
            "level": "blocked" if item["status"] == "blocked" else "info",
            "source": "run-artifact",
            "message": item["title"],
            "time": item["path"],
        }
        for item in fallback_results[:RECENT_LIMIT]
    ]


def _server_health(node_list: list[dict[str, Any]], health_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    services = [
        {
            "name": "Control Plane",
            "status": (health_payload or {}).get("status", "unknown"),
            "detail": f"queue={((health_payload or {}).get('queue') if (health_payload or {}).get('queue') is not None else 'n/a')} backend={(health_payload or {}).get('queue_backend') or 'unknown'}",
        },
        {
            "name": "Redis",
            "status": (health_payload or {}).get("redis", "unknown"),
            "detail": "Очередь задач и lease-состояния",
        },
        {
            "name": "Agent Host",
            "status": "online" if any(node.get("freshness") == "fresh" for node in node_list) else "degraded",
            "detail": f"fresh={sum(1 for node in node_list if node.get('freshness') == 'fresh')} stale={sum(1 for node in node_list if node.get('freshness') == 'stale')}",
        },
        {
            "name": "Frontend API",
            "status": "ok",
            "detail": "/api/factory/status отвечает",
        },
    ]
    return services


def build_factory_status(nodes_payload: Any, tasks_payload: Any | None = None, health_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if tasks_payload is None:
        tasks_payload = {"tasks": []}
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
    task_states: dict[str, int] = {}
    for task in tasks:
        state = str(task.get("state") or "unknown")
        task_states[state] = task_states.get(state, 0) + 1
    artifact_results = _read_recent_run_results()
    blockers_payload = tasks_payload.get("blockers") if isinstance(tasks_payload, dict) else None
    prs_payload = tasks_payload.get("prs") or tasks_payload.get("pull_requests") if isinstance(tasks_payload, dict) else None
    logs_payload = tasks_payload.get("logs") or tasks_payload.get("events") if isinstance(tasks_payload, dict) else None
    return {
        "status": "online" if online_nodes else "degraded",
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
        "tasks": _normalize_tasks(tasks_payload),
        "blockers": _normalize_blockers(blockers_payload, health_payload),
        "prs": _normalize_prs(prs_payload),
        "logs": _normalize_logs(logs_payload, artifact_results),
        "recent_runs": artifact_results,
        "server_health": _server_health(node_list, health_payload),
        "nodes": nodes,
        "node_list": node_list,
    }


async def fetch_factory_status() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(4.0, connect=2.0)) as client:
        health_response = await client.get(_control_plane_v1_url("/health"))
        nodes_response = await client.get(_control_plane_v1_url("/nodes"))
        health_response.raise_for_status()
        nodes_response.raise_for_status()

    tasks_payload: dict[str, Any] = {"tasks": []}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(1.5, connect=1.0)) as client:
            tasks_response = await client.get(_control_plane_v1_url("/tasks"))
            if tasks_response.status_code == 200:
                tasks_payload = tasks_response.json()
    except Exception:
        tasks_payload = {"tasks": []}

    async def fetch_optional(path: str) -> Any:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(1.2, connect=0.8)) as client:
                response = await client.get(_control_plane_v1_url(path))
                if response.status_code == 200:
                    return response.json()
        except Exception:
            return None
        return None

    optional_payloads = {
        "blockers": await fetch_optional("/blockers"),
        "prs": await fetch_optional("/prs"),
        "logs": await fetch_optional("/logs"),
    }
    for key, value in optional_payloads.items():
        if value is not None:
            tasks_payload[key] = value

    return build_factory_status(nodes_response.json(), tasks_payload, health_response.json())
