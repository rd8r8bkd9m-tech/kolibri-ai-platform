from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

CONTROL_PLANE_URL = os.getenv("KOLIBRI_FACTORY_CONTROL_URL", "http://control.kolibri.internal:9101")
NODE_DEGRADED_AFTER = int(os.getenv("FACTORY_NODE_DEGRADED_AFTER", "30"))
NODE_STALE_AFTER = int(os.getenv("FACTORY_NODE_STALE_AFTER", "90"))
ACTIVE_TASK_STATES = {"queued", "leased", "running", "review", "waiting_review"}
ATTENTION_TASK_STATES = {"failed", "dead_letter", "auth_failed", "blocked"}
BLOCK_WORDS = ("auth", "runner_auth", "token", "permission", "forbidden", "unauthorized", "credential")
TOPOLOGY_LEVELS = ("global", "region", "provider", "cluster", "cell", "node", "agent", "task")


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


def _first_text(source: dict[str, Any], keys: tuple[str, ...], fallback: str) -> str:
    for key in keys:
        value = source.get(key)
        if value:
            return str(value)
    return fallback


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
        "topology": {
            "global": _first_text(node, ("global", "environment", "fabric"), "kolibri-ai"),
            "region": _first_text(node, ("region", "geo", "location"), "unknown-region"),
            "provider": _first_text(node, ("provider", "cloud", "provider_name"), "unknown-provider"),
            "cluster": _first_text(node, ("cluster", "cluster_id", "pool"), "control-plane"),
            "cell": _first_text(node, ("cell", "cell_id", "rack", "zone"), "core"),
        },
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


def _task_id(task: dict[str, Any]) -> str:
    return str(task.get("task_id") or task.get("id") or task.get("name") or "task")


def _task_state(task: dict[str, Any]) -> str:
    return str(task.get("state") or task.get("status") or "unknown")


def _task_kind(task: dict[str, Any]) -> str:
    envelope = task.get("envelope") if isinstance(task.get("envelope"), dict) else {}
    return str(task.get("kind") or envelope.get("kind") or "")


def _task_assignee(task: dict[str, Any]) -> str | None:
    lease = task.get("lease") if isinstance(task.get("lease"), dict) else {}
    return task.get("node_id") or task.get("assignee") or task.get("agent_id") or lease.get("node_id") or lease.get("agent_id")


def _task_summary(task: dict[str, Any]) -> dict[str, Any]:
    state = _task_state(task)
    kind = _task_kind(task)
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    envelope = task.get("envelope") if isinstance(task.get("envelope"), dict) else {}
    return {
        "task_id": _task_id(task),
        "state": state,
        "kind": kind or "unknown",
        "title": task.get("title") or envelope.get("title") or envelope.get("objective") or _task_id(task),
        "assignee": _task_assignee(task) or "unassigned",
        "blocked_reason": task.get("blocked_reason") or result.get("blocked_reason") or task.get("error_type"),
        "updated_at": task.get("updated_at") or task.get("heartbeat_at") or task.get("created_at"),
    }


def _contains_blocker(value: Any) -> bool:
    text = str(value or "").lower()
    return any(word in text for word in BLOCK_WORDS)


def _is_runner_auth_block(task: dict[str, Any]) -> bool:
    state = _task_state(task)
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    fields = [
        state,
        task.get("error_type"),
        task.get("blocked_reason"),
        result.get("error_type"),
        result.get("blocked_reason"),
    ]
    return state == "auth_failed" or any(_contains_blocker(field) for field in fields)


def _is_repair_task(task: dict[str, Any]) -> bool:
    joined = " ".join(
        str(part or "")
        for part in (_task_id(task), _task_kind(task), task.get("title"), task.get("objective"))
    ).lower()
    return "repair" in joined or "restore" in joined or "rollback" in joined


def _empty_rollup() -> dict[str, int]:
    return {
        "total": 0,
        "online": 0,
        "fresh": 0,
        "degraded": 0,
        "stale": 0,
        "offline": 0,
        "active_tasks": 0,
        "active_repairs": 0,
        "runner_auth_blocks": 0,
    }


def _apply_node_rollup(rollup: dict[str, int], node: dict[str, Any]) -> None:
    rollup["total"] += 1
    freshness = node.get("freshness")
    status = node.get("status")
    if status == "online":
        rollup["online"] += 1
    if freshness in {"fresh", "degraded", "stale"}:
        rollup[freshness] += 1
    if status == "offline" or node.get("reported_health") == "offline":
        rollup["offline"] += 1


def _build_topology(node_list: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    task_by_assignee: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        assignee = _task_assignee(task)
        if assignee:
            task_by_assignee.setdefault(str(assignee), []).append(task)

    root = {
        "id": "global:kolibri-ai",
        "level": "global",
        "name": "Kolibri AI Global Control Plane",
        "path": ["kolibri-ai"],
        "rollup": _empty_rollup(),
        "children": [],
    }
    index = {tuple(root["path"]): root}

    for node in node_list:
        topo = node.get("topology") or {}
        path_values = [
            topo.get("global") or "kolibri-ai",
            topo.get("region") or "unknown-region",
            topo.get("provider") or "unknown-provider",
            topo.get("cluster") or "control-plane",
            topo.get("cell") or "core",
            node.get("node_id") or "unknown-node",
            node.get("agent_id") or "unregistered-agent",
        ]
        current = root
        for level, value in zip(TOPOLOGY_LEVELS[1:7], path_values[1:], strict=False):
            path = [*current["path"], str(value)]
            key = tuple(path)
            if key not in index:
                child = {
                    "id": f"{level}:{'/'.join(path)}",
                    "level": level,
                    "name": str(value),
                    "path": path,
                    "rollup": _empty_rollup(),
                    "children": [],
                }
                current["children"].append(child)
                index[key] = child
            current = index[key]
            _apply_node_rollup(current["rollup"], node)
        _apply_node_rollup(root["rollup"], node)
        for task in task_by_assignee.get(str(node.get("node_id")), []) + task_by_assignee.get(str(node.get("agent_id")), []):
            summary = _task_summary(task)
            task_node = {
                "id": f"task:{summary['task_id']}",
                "level": "task",
                "name": summary["task_id"],
                "path": [*current["path"], summary["task_id"]],
                "rollup": _empty_rollup(),
                "task": summary,
                "children": [],
            }
            task_node["rollup"]["active_tasks"] = 1 if summary["state"] in ACTIVE_TASK_STATES else 0
            task_node["rollup"]["active_repairs"] = 1 if _is_repair_task(task) and summary["state"] in ACTIVE_TASK_STATES else 0
            task_node["rollup"]["runner_auth_blocks"] = 1 if _is_runner_auth_block(task) else 0
            current["children"].append(task_node)
            for ancestor_path in [tuple(current["path"][:i]) for i in range(1, len(current["path"]) + 1)]:
                ancestor = index.get(ancestor_path)
                if ancestor:
                    ancestor["rollup"]["active_tasks"] += task_node["rollup"]["active_tasks"]
                    ancestor["rollup"]["active_repairs"] += task_node["rollup"]["active_repairs"]
                    ancestor["rollup"]["runner_auth_blocks"] += task_node["rollup"]["runner_auth_blocks"]

    return root


def _queue_pressure(queue_size: int, task_states: dict[str, int]) -> dict[str, Any]:
    running = sum(task_states.get(state, 0) for state in ("leased", "running"))
    blocked = sum(task_states.get(state, 0) for state in ATTENTION_TASK_STATES)
    if queue_size >= 1000 or blocked:
        level = "critical"
    elif queue_size >= 100:
        level = "high"
    elif queue_size >= 20:
        level = "elevated"
    else:
        level = "normal"
    return {"level": level, "queued_or_running": queue_size, "running": running, "blocked": blocked}


def _telegram_ha(health_payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = health_payload or {}
    explicit = payload.get("telegram_ha") or payload.get("telegram") or payload.get("telegram_gateway")
    if isinstance(explicit, dict):
        primary = explicit.get("primary") or explicit.get("primary_state") or explicit.get("status")
        standby = explicit.get("standby") or explicit.get("standby_state")
        promotion = explicit.get("promotion") or explicit.get("failover")
    else:
        primary = payload.get("telegram_primary")
        standby = payload.get("telegram_standby")
        promotion = payload.get("telegram_failover")
    status = "unknown"
    if primary in {"active", "running", "ok", "online"} and standby in {"ready", "standby", "ok", "online"}:
        status = "ready"
    elif primary in {"active", "running", "ok", "online"}:
        status = "primary-only"
    elif primary or standby or promotion:
        status = "attention"
    return {"status": status, "primary": primary or "unknown", "standby": standby or "unknown", "promotion": promotion or "unknown"}


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
    task_states: dict[str, int] = {}
    for task in tasks:
        state = _task_state(task)
        task_states[state] = task_states.get(state, 0) + 1
    queue_size = (
        sum(task_states.get(state, 0) for state in ("queued", "leased", "running"))
        if task_states
        else int((health_payload or {}).get("queue") or 0)
    )
    active_tasks = [_task_summary(task) for task in tasks if _task_state(task) in ACTIVE_TASK_STATES]
    active_repairs = [_task_summary(task) for task in tasks if _is_repair_task(task) and _task_state(task) in ACTIVE_TASK_STATES]
    runner_auth_blocks = [_task_summary(task) for task in tasks if _is_runner_auth_block(task)]
    offline_nodes = [node for node in node_list if node.get("status") == "offline" or node.get("reported_health") == "offline"]
    telegram_ha = _telegram_ha(health_payload)
    queue_pressure = _queue_pressure(queue_size, task_states)
    owner_attention = {
        "count": len(stale_nodes)
        + len(degraded_nodes)
        + len(offline_nodes)
        + len(active_repairs)
        + len(runner_auth_blocks)
        + (1 if queue_pressure["level"] in {"high", "critical"} else 0)
        + (1 if telegram_ha["status"] in {"attention", "unknown"} else 0),
        "stale_nodes": len(stale_nodes),
        "degraded_nodes": len(degraded_nodes),
        "offline_nodes": len(offline_nodes),
        "active_repairs": len(active_repairs),
        "runner_auth_blocks": len(runner_auth_blocks),
        "queue_pressure": queue_pressure["level"],
        "telegram_ha": telegram_ha["status"],
    }
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
        "offline_nodes": len(offline_nodes),
        "node_freshness": {
            "fresh": len(fresh_nodes),
            "degraded": len(degraded_nodes),
            "stale": len(stale_nodes),
            "online": len(online_nodes),
            "offline": len(offline_nodes),
            "total": len(node_list),
        },
        "free_ram_gb": _gb_from_kb(available_ram_kb),
        "total_ram_gb": _gb_from_kb(total_ram_kb),
        "avg_cpu_percent": round(sum(cpu_values) / len(cpu_values), 1) if cpu_values else 0,
        "queue_size": queue_size,
        "queue_pressure": queue_pressure,
        "task_states": task_states,
        "active_tasks": active_tasks[:50],
        "active_task_count": len(active_tasks),
        "active_repairs": active_repairs[:50],
        "active_repair_count": len(active_repairs),
        "runner_auth_blocks": runner_auth_blocks[:50],
        "runner_auth_block_count": len(runner_auth_blocks),
        "telegram_ha": telegram_ha,
        "owner_attention": owner_attention,
        "topology_levels": list(TOPOLOGY_LEVELS),
        "topology": _build_topology(node_list, tasks),
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
