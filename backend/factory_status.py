from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

CONTROL_PLANE_URL = os.getenv("KOLIBRI_FACTORY_CONTROL_URL", "http://control.kolibri.internal:9101")
CONTROL_PLANE_FALLBACK_URLS = ("http://10.99.0.2:9101", "http://127.0.0.1:9101")
WATCHDOG_REPORT_DIR = Path(os.getenv("KOLIBRI_FACTORY_WATCHDOG_REPORT_DIR", "/var/lib/kolibri-factory-control/watchdog"))


def _configured_control_plane_urls() -> list[str]:
    raw_urls = os.getenv("KOLIBRI_FACTORY_CONTROL_URLS")
    configured_primary = os.getenv("KOLIBRI_FACTORY_CONTROL_URL")
    if raw_urls:
        candidates = raw_urls.split(",")
    elif configured_primary:
        candidates = [configured_primary, *CONTROL_PLANE_FALLBACK_URLS, CONTROL_PLANE_URL]
    else:
        candidates = [*CONTROL_PLANE_FALLBACK_URLS, CONTROL_PLANE_URL]
    urls: list[str] = []
    for candidate in candidates:
        url = candidate.strip().rstrip("/")
        if url and url not in urls:
            urls.append(url)
    return urls or [CONTROL_PLANE_URL]


def _control_plane_v1_url(path: str, base_url: str | None = None) -> str:
    base = (base_url or CONTROL_PLANE_URL).rstrip("/")
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


def merge_tasks_by_id(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for tasks in groups:
        for task in tasks:
            if not isinstance(task, dict):
                continue
            merged[_task_identifier(task)] = task
    return list(merged.values())


def _task_identifier(task: dict[str, Any]) -> str:
    return str(task.get("task_id") or task.get("id") or task.get("name") or "unknown")


def summarize_factory_failures(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    error_types: dict[str, int] = {}
    deliverable_gate_recent: list[dict[str, Any]] = []
    failed_total = 0
    for task in tasks:
        state = str(task.get("state") or "")
        error_type = str(task.get("error_type") or "")
        if state in {"failed", "dead_letter"}:
            failed_total += 1
        if error_type:
            error_types[error_type] = error_types.get(error_type, 0) + 1
        if error_type == "deliverable_gate_failed":
            envelope = task.get("envelope") if isinstance(task.get("envelope"), dict) else {}
            result = task.get("result") if isinstance(task.get("result"), dict) else {}
            deliverable_gate_recent.append(
                {
                    "task_id": _task_identifier(task),
                    "state": state or "unknown",
                    "kind": task.get("kind") or envelope.get("kind") or "unknown",
                    "updated_at": task.get("updated_at") or task.get("heartbeat_at") or task.get("created_at"),
                    "error": str(task.get("error") or "")[:240],
                    "result_reference": task.get("result_reference") or result.get("result_path"),
                }
            )
    deliverable_gate_recent.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    deliverable_gate_total = error_types.get("deliverable_gate_failed", 0)
    return {
        "failed_total": failed_total,
        "error_types": error_types,
        "deliverable_gate_failed": deliverable_gate_total,
        "deliverable_gate_recent": deliverable_gate_recent[:5],
        "needs_attention": deliverable_gate_total > 0,
    }


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        value = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def load_watchdog_status(report_dir: Path | None = None) -> dict[str, Any]:
    root = report_dir or WATCHDOG_REPORT_DIR
    rollup = _read_json_file(root / "summary.json") or {}
    latest = _read_json_file(root / "latest.json") or {}
    latest_summary = latest.get("summary") if isinstance(latest.get("summary"), dict) else {}
    telegram = latest.get("telegram") if isinstance(latest.get("telegram"), dict) else {}
    return {
        "available": bool(rollup or latest),
        "report_dir": str(root),
        "latest_report": latest.get("report_paths") if isinstance(latest.get("report_paths"), dict) else None,
        "latest_summary": latest_summary,
        "telegram": telegram,
        "rollup": {
            "runs_total": int(rollup.get("runs_total") or 0),
            "runs_ok": int(rollup.get("runs_ok") or 0),
            "runs_degraded": int(rollup.get("runs_degraded") or 0),
            "runs_failed": int(rollup.get("runs_failed") or 0),
            "actions_total": int(rollup.get("actions_total") or 0),
            "totals": rollup.get("totals") if isinstance(rollup.get("totals"), dict) else {},
            "recent_actions": rollup.get("recent_actions") if isinstance(rollup.get("recent_actions"), list) else [],
            "updated_at": rollup.get("updated_at"),
        },
    }


def build_factory_status(
    nodes_payload: Any,
    tasks_payload: Any | None = None,
    health_payload: dict[str, Any] | None = None,
    watchdog_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_nodes = nodes_payload.get("nodes", []) if isinstance(nodes_payload, dict) else nodes_payload if isinstance(nodes_payload, list) else []
    raw_summary = nodes_payload.get("summary", {}) if isinstance(nodes_payload, dict) else {}
    summary = raw_summary if isinstance(raw_summary, dict) else {}
    node_list = [_node_card(node) for node in raw_nodes if isinstance(node, dict)]
    nodes = {node["node_id"]: node for node in node_list}
    online_nodes = [node for node in node_list if node.get("status") == "online"]
    fresh_nodes = int(summary.get("fresh_nodes", len(online_nodes)) or 0)
    fresh_non_draining_nodes = int(summary.get("fresh_non_draining_nodes", fresh_nodes) or 0)
    registered_nodes = int(summary.get("registered_nodes", len(node_list)) or 0)
    canonical_nodes = int(summary.get("canonical_nodes", len(node_list)) or 0)
    draining_nodes = sum(1 for node in raw_nodes if isinstance(node, dict) and node.get("draining"))
    mesh_shadow_duplicates = int(summary.get("mesh_shadow_duplicates", 0) or 0)
    total_ram_kb = sum(_parse_mem_kb((node.get("ram") or {}).get("MemTotal")) for node in raw_nodes if isinstance(node, dict))
    available_ram_kb = sum(_parse_mem_kb((node.get("ram") or {}).get("MemAvailable")) for node in raw_nodes if isinstance(node, dict))
    cpu_values = [node.get("cpu") for node in raw_nodes if isinstance(node, dict) and isinstance(node.get("cpu"), (int, float))]
    tasks = _extract_tasks(tasks_payload)
    task_states: dict[str, int] = {}
    for task in tasks:
        state = str(task.get("state") or "unknown")
        task_states[state] = task_states.get(state, 0) + 1
    factory_failures = summarize_factory_failures(tasks)
    return {
        "status": "online" if fresh_nodes else "degraded",
        "source": "control-plane",
        "generated_at": (health_payload or {}).get("time") or datetime.now(timezone.utc).isoformat(),
        "control_plane": {
            "url": (health_payload or {}).get("url") or CONTROL_PLANE_URL,
            "status": (health_payload or {}).get("status", "unknown"),
            "queue_backend": (health_payload or {}).get("queue_backend"),
            "redis": (health_payload or {}).get("redis"),
        },
        "node_summary": {
            **summary,
            "registered_nodes": registered_nodes,
            "canonical_nodes": canonical_nodes,
            "fresh_nodes": fresh_nodes,
            "fresh_non_draining_nodes": fresh_non_draining_nodes,
            "stale_nodes": max(registered_nodes - fresh_nodes, 0),
            "draining_nodes": draining_nodes,
            "duplicate_nodes": max(registered_nodes - canonical_nodes, mesh_shadow_duplicates),
        },
        "total_nodes": registered_nodes,
        "online_nodes": fresh_nodes,
        "canonical_nodes": canonical_nodes,
        "fresh_non_draining_nodes": fresh_non_draining_nodes,
        "ready_generic_implementation_nodes": int(summary.get("fresh_canonical_generic_implementation_nodes", 0) or 0),
        "stale_nodes": max(registered_nodes - fresh_nodes, 0),
        "draining_nodes": draining_nodes,
        "mesh_shadow_duplicates": mesh_shadow_duplicates,
        "duplicate_nodes": max(registered_nodes - canonical_nodes, mesh_shadow_duplicates),
        "free_ram_gb": _gb_from_kb(available_ram_kb),
        "total_ram_gb": _gb_from_kb(total_ram_kb),
        "avg_cpu_percent": round(sum(cpu_values) / len(cpu_values), 1) if cpu_values else 0,
        "queue_size": (
            sum(task_states.get(state, 0) for state in ("queued", "leased", "running"))
            if task_states
            else int((health_payload or {}).get("queue") or 0)
        ),
        "task_states": task_states,
        "factory_failures": factory_failures,
        "watchdog": watchdog_payload or load_watchdog_status(),
        "nodes": nodes,
        "node_list": node_list,
    }


def build_degraded_factory_status(error: str, control_plane_url: str | None = None) -> dict[str, Any]:
    return {
        "status": "degraded",
        "source": "control-plane",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "error": error,
        "control_plane": {
            "url": control_plane_url or CONTROL_PLANE_URL,
            "status": "unavailable",
        },
        "node_summary": {
            "registered_nodes": 0,
            "canonical_nodes": 0,
            "fresh_nodes": 0,
            "fresh_non_draining_nodes": 0,
            "stale_nodes": 0,
            "draining_nodes": 0,
            "duplicate_nodes": 0,
            "mesh_shadow_duplicates": 0,
        },
        "total_nodes": 0,
        "online_nodes": 0,
        "canonical_nodes": 0,
        "fresh_non_draining_nodes": 0,
        "ready_generic_implementation_nodes": 0,
        "stale_nodes": 0,
        "draining_nodes": 0,
        "mesh_shadow_duplicates": 0,
        "duplicate_nodes": 0,
        "free_ram_gb": 0,
        "total_ram_gb": 0,
        "avg_cpu_percent": 0,
        "queue_size": 0,
        "task_states": {},
        "factory_failures": {
            "failed_total": 0,
            "error_types": {},
            "deliverable_gate_failed": 0,
            "deliverable_gate_recent": [],
            "needs_attention": False,
        },
        "watchdog": load_watchdog_status(),
        "nodes": {},
        "node_list": [],
    }


async def fetch_factory_status() -> dict[str, Any]:
    selected_url: str | None = None
    last_exc: Exception | None = None
    health_payload: dict[str, Any] | None = None
    nodes_payload: Any = None

    for control_url in _configured_control_plane_urls():
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=2.0), trust_env=False) as client:
                health_response = await client.get(_control_plane_v1_url("/health", control_url))
                nodes_response = await client.get(_control_plane_v1_url("/nodes", control_url))
                health_response.raise_for_status()
                nodes_response.raise_for_status()
            selected_url = control_url
            health_payload = health_response.json()
            health_payload["url"] = control_url
            nodes_payload = nodes_response.json()
            break
        except Exception as exc:
            last_exc = exc

    if selected_url is None or health_payload is None:
        assert last_exc is not None
        raise last_exc

    tasks_payload: Any = {"tasks": []}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(1.5, connect=1.0), trust_env=False) as client:
            tasks_response = await client.get(_control_plane_v1_url("/tasks?summary=1&compact=1&limit=500", selected_url))
            if tasks_response.status_code == 200:
                tasks_payload = tasks_response.json()
    except Exception:
        tasks_payload = {"tasks": []}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=1.0), trust_env=False) as client:
            failed_response = await client.get(_control_plane_v1_url("/tasks/failures?error_type=deliverable_gate_failed&limit=100", selected_url))
            if failed_response.status_code == 200:
                tasks_payload = {
                    "tasks": merge_tasks_by_id(
                        _extract_tasks(tasks_payload),
                        _extract_tasks(failed_response.json()),
                    )
                }
    except Exception:
        pass

    return build_factory_status(nodes_payload, tasks_payload, health_payload)
