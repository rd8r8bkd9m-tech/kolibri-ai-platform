"""Read-only adapter from the Home Control Plane to the portal API schema.

The portal database contains demo rows for local product development.  Those
rows must never be used as evidence about the live factory.  This module is the
only read path for portal node/task views and deliberately fails closed when
the configured Home Control Plane cannot be reached or returns an invalid
contract.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx


CONTROL_PLANE_ENV = "KOLIBRI_CONTROL_PLANE_URL"
CONTROL_PLANE_SOURCE = "home_control_plane"
DEFAULT_TIMEOUT_SECONDS = 2.0
MAX_TIMEOUT_SECONDS = 10.0


class ControlPlaneUnavailable(RuntimeError):
    """The authoritative read model is unavailable or failed validation."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_timeout(value: str | None) -> float:
    if value is None or not value.strip():
        return DEFAULT_TIMEOUT_SECONDS
    try:
        timeout = float(value)
    except ValueError as exc:
        raise ControlPlaneUnavailable("control_plane_timeout_invalid") from exc
    if timeout <= 0 or timeout > MAX_TIMEOUT_SECONDS:
        raise ControlPlaneUnavailable("control_plane_timeout_invalid")
    return timeout


def _validated_base_url(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ControlPlaneUnavailable("control_plane_not_configured")
    parsed = urlsplit(raw)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ControlPlaneUnavailable("control_plane_url_invalid")
    return raw.rstrip("/")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _to_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _percentage(used: Any, total: Any) -> str | None:
    try:
        used_value = float(used)
        total_value = float(total)
    except (TypeError, ValueError):
        return None
    if total_value <= 0 or used_value < 0:
        return None
    return f"{min(100.0, max(0.0, used_value / total_value * 100.0)):.1f}"


def _memory_kib(value: Any) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    if not isinstance(value, str):
        return None
    token = value.strip().split(maxsplit=1)[0]
    try:
        return int(token)
    except ValueError:
        return None


def _node_status(node: dict[str, Any]) -> str:
    health = str(node.get("health") or "").lower()
    freshness = str(node.get("freshness") or "stale").lower()
    if not node.get("registered") or health == "quarantined":
        return "quarantined"
    if freshness == "stale":
        return "offline"
    if node.get("draining"):
        return "draining"
    if freshness == "degraded":
        return "degraded"
    if freshness == "fresh" and health in {"online", "healthy", "ready"}:
        return "healthy"
    return "degraded"


def _agent_status(node: dict[str, Any]) -> str:
    freshness = str(node.get("freshness") or "stale").lower()
    health = str(node.get("health") or "").lower()
    if freshness == "stale" or health not in {"online", "healthy", "ready"}:
        return "error"
    if node.get("draining"):
        return "paused"
    return "active" if node.get("active_task") else "idle"


def _task_state(value: Any) -> str:
    state = str(value or "").lower()
    return {
        "leased": "assigned",
        "review": "assigned",
        "waiting_review": "waiting",
        "retry_scheduled": "waiting",
        "dead_letter": "failed",
    }.get(state, state or "unknown")


def _priority(value: Any) -> int:
    if isinstance(value, str):
        symbolic = {"P0": 5, "P1": 4, "P2": 3, "P3": 2, "P4": 1}
        if value.upper() in symbolic:
            return symbolic[value.upper()]
    return max(1, min(5, _to_int(value, 1)))


@dataclass(frozen=True)
class HomeControlPlaneAdapter:
    base_url: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    transport: httpx.AsyncBaseTransport | None = None

    @classmethod
    def from_environment(cls) -> "HomeControlPlaneAdapter":
        return cls(
            base_url=_validated_base_url(os.getenv(CONTROL_PLANE_ENV)),
            timeout_seconds=_bounded_timeout(
                os.getenv("KOLIBRI_CONTROL_PLANE_TIMEOUT_SECONDS")
            ),
        )

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        timeout = httpx.Timeout(
            self.timeout_seconds,
            connect=min(1.0, self.timeout_seconds),
            pool=min(1.0, self.timeout_seconds),
        )
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=timeout,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                response = await client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise ControlPlaneUnavailable("control_plane_timeout") from exc
        except httpx.RequestError as exc:
            raise ControlPlaneUnavailable("control_plane_unreachable") from exc
        if response.status_code != 200:
            raise ControlPlaneUnavailable("control_plane_bad_status")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ControlPlaneUnavailable("control_plane_invalid_json") from exc
        if not isinstance(payload, dict):
            raise ControlPlaneUnavailable("control_plane_contract_invalid")
        return payload

    async def list_nodes(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None,
    ) -> dict[str, Any]:
        offset = (page - 1) * page_size
        control_plane_limit = 250 if status else page_size
        control_plane_offset = 0 if status else offset
        payload = await self._get(
            "/v1/nodes",
            {
                "scope": "active",
                "limit": control_plane_limit,
                "offset": control_plane_offset,
            },
        )
        raw_nodes = payload.get("nodes")
        pagination = _as_dict(payload.get("pagination"))
        if not isinstance(raw_nodes, list) or "total_indexed" not in pagination:
            raise ControlPlaneUnavailable("control_plane_nodes_contract_invalid")

        observed_at = _utc_now()
        items = [self._map_node(_as_dict(node), observed_at) for node in raw_nodes]
        if status:
            items = [node for node in items if node["status"] == status]
            total = len(items)
            items = items[offset:offset + page_size]
        else:
            total = _to_int(pagination.get("total_indexed"), len(items))
        availabilities = [
            _as_dict(_as_dict(item.get("capabilities")).get("_truth")).get("availability")
            for item in items
        ]
        availability = "live" if "live" in availabilities else "stale"
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "truth": {
                "availability": availability,
                "source": CONTROL_PLANE_SOURCE,
                "as_of": observed_at,
                "membership": _as_dict(payload.get("membership")),
                "freshness": _as_dict(payload.get("counts")),
            },
        }

    async def list_agents(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None,
    ) -> dict[str, Any]:
        """Derive one truthful Agent Host record per active mesh node."""

        offset = (page - 1) * page_size
        control_plane_limit = 250 if status else page_size
        control_plane_offset = 0 if status else offset
        payload = await self._get(
            "/v1/nodes",
            {
                "scope": "active",
                "limit": control_plane_limit,
                "offset": control_plane_offset,
            },
        )
        raw_nodes = payload.get("nodes")
        pagination = _as_dict(payload.get("pagination"))
        if not isinstance(raw_nodes, list) or "total_indexed" not in pagination:
            raise ControlPlaneUnavailable("control_plane_agents_contract_invalid")

        observed_at = _utc_now()
        items = [self._map_agent(_as_dict(node), observed_at) for node in raw_nodes]
        if status:
            items = [agent for agent in items if agent["status"] == status]
            total = len(items)
            items = items[offset:offset + page_size]
        else:
            total = _to_int(pagination.get("total_indexed"), len(items))
        availabilities = [
            _as_dict(_as_dict(item.get("capabilities")).get("_truth")).get("availability")
            for item in items
        ]
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "truth": {
                "availability": "live" if "live" in availabilities else "stale",
                "source": CONTROL_PLANE_SOURCE,
                "as_of": observed_at,
                "membership": _as_dict(payload.get("membership")),
                "freshness": _as_dict(payload.get("counts")),
                "derivation": "one_agent_host_per_active_node",
            },
        }

    async def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        result = await self.list_agents(page=1, page_size=100, status=None)
        return next(
            (agent for agent in result["items"] if agent["id"] == agent_id),
            None,
        )

    def _map_agent(self, node: dict[str, Any], observed_at: str) -> dict[str, Any]:
        node_id = str(node.get("node_id") or "").strip()
        if not node_id:
            raise ControlPlaneUnavailable("control_plane_agent_node_id_missing")
        agent_id = str(node.get("agent_id") or node_id).strip()
        freshness = str(node.get("freshness") or "stale").lower()
        availability = "live" if freshness == "fresh" else "stale"
        raw_active_task = node.get("active_task")
        if isinstance(raw_active_task, dict):
            current_task = str(
                raw_active_task.get("task_id")
                or raw_active_task.get("id")
                or ""
            ).strip() or None
        else:
            current_task = str(raw_active_task or "").strip() or None

        runner_summary: dict[str, dict[str, Any]] = {}
        for runner_name, runner_value in _as_dict(node.get("runners")).items():
            runner = _as_dict(runner_value)
            runner_summary[str(runner_name)] = {
                key: runner.get(key)
                for key in (
                    "status", "provider", "model", "model_version",
                    "login_status", "error_type",
                )
                if runner.get(key) is not None
            }

        return {
            "id": agent_id,
            "name": str(node.get("hostname") or node_id),
            "role": "agent_host",
            "status": _agent_status(node),
            "node_id": node_id,
            "current_task": current_task,
            "progress": 0,
            "model": None,
            "capabilities": {
                "items": [str(value) for value in _as_list(node.get("capabilities"))],
                "runners": runner_summary,
                "progress_availability": "unavailable",
                "_truth": {
                    "availability": availability,
                    "source": CONTROL_PLANE_SOURCE,
                    "as_of": node.get("heartbeat_at"),
                    "observed_at": observed_at,
                    "freshness": freshness,
                    "heartbeat_age_seconds": node.get("heartbeat_age_seconds"),
                    "registered": bool(node.get("registered")),
                    "schedulable": bool(node.get("schedulable")),
                    "activity_source": "active_task" if current_task else "none",
                },
            },
            "cost_accumulated": "unavailable",
            "heartbeat_at": node.get("heartbeat_at"),
        }

    def _map_node(self, node: dict[str, Any], observed_at: str) -> dict[str, Any]:
        node_id = str(node.get("node_id") or "").strip()
        if not node_id:
            raise ControlPlaneUnavailable("control_plane_node_id_missing")
        freshness = str(node.get("freshness") or "stale").lower()
        truth_availability = "live" if freshness == "fresh" else "stale"

        disk = _as_dict(node.get("disk"))
        disk_percent = _percentage(disk.get("used"), disk.get("total"))
        ram = _as_dict(node.get("ram"))
        total_ram = _memory_kib(ram.get("MemTotal"))
        available_ram = _memory_kib(ram.get("MemAvailable"))
        ram_percent = None
        if total_ram is not None and available_ram is not None:
            ram_percent = _percentage(total_ram - available_ram, total_ram)

        raw_capabilities = node.get("capabilities")
        capability_items = [str(value) for value in _as_list(raw_capabilities)]
        capabilities = {
            "items": capability_items,
            "runners": _as_dict(node.get("runners")),
            "cpu_cores": node.get("cpu"),
            "metrics_availability": {
                "cpu_percent": "live" if node.get("cpu_percent") is not None else "unavailable",
                "ram_percent": "live" if ram_percent is not None else "unavailable",
                "disk_percent": "live" if disk_percent is not None else "unavailable",
                "network_mbps": "live" if node.get("network_mbps") is not None else "unavailable",
                "ping_ms": "live" if node.get("ping_ms") is not None else "unavailable",
            },
            "_truth": {
                "availability": truth_availability,
                "source": CONTROL_PLANE_SOURCE,
                "as_of": node.get("heartbeat_at"),
                "observed_at": observed_at,
                "freshness": freshness,
                "heartbeat_age_seconds": node.get("heartbeat_age_seconds"),
                "registered": bool(node.get("registered")),
                "schedulable": bool(node.get("schedulable")),
                "reported_health": node.get("reported_health"),
            },
        }
        lease_owner = str(node.get("agent_id") or "")
        return {
            "id": node_id,
            "name": str(node.get("hostname") or node_id),
            "region": str(_as_dict(node.get("labels")).get("region") or ""),
            "ip_address": str(node.get("mesh_ip") or node.get("internal_ip") or ""),
            "status": _node_status(node),
            "cpu_percent": str(node.get("cpu_percent")) if node.get("cpu_percent") is not None else "unavailable",
            "ram_percent": ram_percent or "unavailable",
            "disk_percent": disk_percent or "unavailable",
            "network_mbps": str(node.get("network_mbps")) if node.get("network_mbps") is not None else "unavailable",
            "agent_count": 1 if lease_owner else 0,
            "task_count": 1 if node.get("active_task") else 0,
            "ping_ms": _to_int(node.get("ping_ms"), -1),
            "max_agents": _to_int(node.get("max_agents"), 0),
            "capabilities": capabilities,
        }

    async def list_tasks(
        self,
        *,
        page: int,
        page_size: int,
        state: str | None,
    ) -> dict[str, Any]:
        offset = (page - 1) * page_size
        params: dict[str, Any] = {"limit": page_size, "offset": offset}
        if state:
            reverse_state = {
                "assigned": "leased",
                "waiting": "waiting_review",
            }
            params["state"] = reverse_state.get(state, state)
        payload = await self._get("/v1/tasks", params)
        raw_tasks = payload.get("tasks")
        pagination = _as_dict(payload.get("pagination"))
        if not isinstance(raw_tasks, list) or "total_indexed" not in pagination:
            raise ControlPlaneUnavailable("control_plane_tasks_contract_invalid")
        observed_at = _utc_now()
        items = [self._map_task(_as_dict(task), observed_at) for task in raw_tasks]
        total = (
            len(items)
            if state
            else _to_int(pagination.get("total_indexed"), len(items))
        )
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "truth": {
                "availability": "live",
                "source": CONTROL_PLANE_SOURCE,
                "as_of": observed_at,
                "queue_total": _to_int(payload.get("queue_total"), 0),
                "total_scope": "returned_page" if state else "all_indexed_tasks",
            },
        }

    def _map_task(self, task: dict[str, Any], observed_at: str) -> dict[str, Any]:
        task_id = str(task.get("task_id") or "").strip()
        if not task_id:
            raise ControlPlaneUnavailable("control_plane_task_id_missing")
        envelope = _as_dict(task.get("envelope"))
        lease_owner = str(task.get("lease_owner") or "")
        lease_node, separator, lease_agent = lease_owner.partition(":")
        node_id = str(envelope.get("target_node") or lease_node or "").strip() or None
        owner_agent_id = (lease_agent if separator else lease_owner).strip() or None
        raw_result = task.get("result")
        result = dict(raw_result) if isinstance(raw_result, dict) else {}
        result["_truth"] = {
            "availability": "live",
            "source": CONTROL_PLANE_SOURCE,
            "as_of": task.get("updated_at") or task.get("created_at"),
            "observed_at": observed_at,
            "truth_gate": _as_dict(task.get("truth_gate")),
            "result_reference": task.get("result_reference"),
        }
        workflow_id = (
            envelope.get("workflow_id")
            or envelope.get("title")
            or envelope.get("objective")
            or envelope.get("kind")
            or task_id
        )
        raw_priority = envelope.get("priority", task.get("priority"))
        return {
            "id": task_id,
            "workflow_id": str(workflow_id),
            "state": _task_state(task.get("state")),
            "priority": _priority(raw_priority),
            "owner_agent_id": owner_agent_id,
            "node_id": node_id,
            "budget_limit": (
                str(envelope.get("budget_limit"))
                if envelope.get("budget_limit") is not None
                else None
            ),
            "attempts": _to_int(task.get("attempt"), 0),
            "max_retries": _to_int(
                envelope.get("max_retries", task.get("max_retries")), 0
            ),
            "result": result,
            "created_at": str(task.get("created_at") or ""),
            "updated_at": str(task.get("updated_at") or task.get("created_at") or ""),
        }


def unavailable_detail(reason: str) -> dict[str, Any]:
    return {
        "error": "home_control_plane_unavailable",
        "availability": "unavailable",
        "source": CONTROL_PLANE_SOURCE,
        "reason": reason,
        "as_of": _utc_now(),
    }
