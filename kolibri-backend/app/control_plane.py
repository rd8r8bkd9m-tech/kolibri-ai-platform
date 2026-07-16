"""Read-only adapter from the Home Control Plane to the portal API schema.

The portal database contains demo rows for local product development.  Those
rows must never be used as evidence about the live factory.  This module is the
only read path for portal node/task views and deliberately fails closed when
the configured Home Control Plane cannot be reached or returns an invalid
contract.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx


CONTROL_PLANE_ENV = "KOLIBRI_CONTROL_PLANE_URL"
CONTROL_PLANE_TOKEN_FILE_ENV = "KOLIBRI_CONTROL_PLANE_TOKEN_FILE"
CONTROL_PLANE_SOURCE = "home_control_plane"
DEFAULT_TIMEOUT_SECONDS = 2.0
MAX_TIMEOUT_SECONDS = 10.0
FLEET_PROOF_PATH = "/v1/runtime/fleet-proof"
SHA256_PATTERN = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
BEARER_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._~+/=-]{32,512}$")
CONNECTED_HEALTH_STATES = frozenset({"online", "healthy", "ready"})
DISCONNECTED_HEALTH_STATES = frozenset({"offline", "disconnected", "failed"})
RUNNER_EXECUTABLE_STATES = frozenset({
    "available", "healthy", "online", "ready", "running",
})
RUNNER_BLOCKED_STATES = frozenset({
    "blocked", "degraded", "disabled", "runner_auth_blocked", "unavailable",
})


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


def _optional_bearer_token(path_value: str | None) -> str | None:
    raw = str(path_value or "").strip()
    if not raw:
        return None
    path = Path(raw)
    try:
        info = path.lstat()
    except OSError as exc:
        raise ControlPlaneUnavailable("control_plane_token_unreadable") from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) not in {0o600, 0o640}
        or info.st_uid not in {0, os.geteuid()}
        or not 1 <= info.st_size <= 4096
    ):
        raise ControlPlaneUnavailable("control_plane_token_file_unsafe")
    try:
        token = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise ControlPlaneUnavailable("control_plane_token_unreadable") from exc
    if not BEARER_TOKEN_PATTERN.fullmatch(token):
        raise ControlPlaneUnavailable("control_plane_token_invalid")
    return token


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
    if not node.get("registered") or health == "quarantined":
        return "quarantined"
    if node.get("draining"):
        return "draining"
    if health in CONNECTED_HEALTH_STATES:
        return "connected"
    if health in DISCONNECTED_HEALTH_STATES:
        return "disconnected"
    return "degraded" if health == "degraded" else "unknown"


def _agent_status(node: dict[str, Any]) -> str:
    freshness = str(node.get("freshness") or "stale").lower()
    health = str(node.get("health") or "").lower()
    if freshness == "stale" or health not in CONNECTED_HEALTH_STATES:
        return "error"
    if node.get("draining"):
        return "paused"
    return "active" if node.get("active_task") else "idle"


def _connection_truth(node: dict[str, Any]) -> dict[str, Any]:
    health = str(node.get("health") or "").strip().lower()
    if health in CONNECTED_HEALTH_STATES:
        status = "online"
        connected = True
    elif health in DISCONNECTED_HEALTH_STATES:
        status = "offline"
        connected = False
    else:
        status = "unknown"
        connected = False
    return {
        "status": status,
        "connected": connected,
        "reported_health": node.get("reported_health") or node.get("health"),
        "source": "node_health_report",
    }


def _freshness_truth(node: dict[str, Any]) -> dict[str, Any]:
    raw = str(node.get("freshness") or "unknown").strip().lower()
    status = raw if raw in {"fresh", "degraded", "stale"} else "unknown"
    return {
        "status": status,
        "fresh": status == "fresh",
        "heartbeat_at": node.get("heartbeat_at"),
        "heartbeat_age_seconds": node.get("heartbeat_age_seconds"),
    }


def _active_task_id(node: dict[str, Any]) -> str | None:
    value = node.get("active_task")
    if isinstance(value, dict):
        token = value.get("task_id") or value.get("id")
    else:
        token = value
    return str(token or "").strip() or None


def _runner_for_capability(capability: str) -> str | None:
    value = capability.strip().lower()
    if value.startswith("runner:"):
        return value.partition(":")[2] or None
    if value.startswith("runner_"):
        return value.removeprefix("runner_") or None
    if value.endswith("_runner"):
        return value.removesuffix("_runner") or None
    return None


def _runner_status(node: dict[str, Any], runner_name: str) -> str | None:
    for collection_name in ("runners", "runner_status"):
        raw = _as_dict(node.get(collection_name)).get(runner_name)
        if isinstance(raw, dict):
            raw = raw.get("status")
        if raw is not None:
            return str(raw).strip().lower() or None
    return None


def _capability_execution(node: dict[str, Any]) -> list[dict[str, Any]]:
    connection = _connection_truth(node)
    freshness = _freshness_truth(node)
    health = str(node.get("health") or "").strip().lower()
    quarantined = bool(
        not node.get("registered")
        or health == "quarantined"
        or node.get("lifecycle") == "quarantined"
        or node.get("quarantine_reason")
    )
    base_reasons: list[str] = []
    if quarantined:
        base_reasons.append("quarantined")
    if not connection["connected"]:
        base_reasons.append("not_connected")
    if not freshness["fresh"]:
        base_reasons.append("heartbeat_not_fresh")
    if not node.get("schedulable"):
        base_reasons.append("not_schedulable")
    if node.get("draining"):
        base_reasons.append("draining")

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_capability in _as_list(node.get("capabilities")):
        capability = str(raw_capability).strip()
        if not capability or capability in seen:
            continue
        seen.add(capability)
        runner = _runner_for_capability(capability)
        runner_status = _runner_status(node, runner) if runner else None
        reasons = list(base_reasons)
        if runner and runner_status not in RUNNER_EXECUTABLE_STATES:
            reasons.append(
                "runner_status_unavailable"
                if runner_status is None
                else f"runner_{runner_status}"
            )
        result.append({
            "name": capability,
            "runner": runner,
            "runner_status": runner_status,
            "executable": not reasons,
            "reasons": reasons,
        })
    return result


def _execution_truth(node: dict[str, Any], capability_execution: list[dict[str, Any]]) -> dict[str, Any]:
    connection = _connection_truth(node)
    freshness = _freshness_truth(node)
    task_id = _active_task_id(node)
    health = str(node.get("health") or "").strip().lower()
    quarantined = bool(
        not node.get("registered")
        or health == "quarantined"
        or node.get("lifecycle") == "quarantined"
        or node.get("quarantine_reason")
    )
    executable_items = [
        item["name"] for item in capability_execution if item["executable"]
    ]
    runner_blocked = bool(capability_execution) and not executable_items and any(
        item.get("runner_status") in RUNNER_BLOCKED_STATES
        for item in capability_execution
    )
    blocked_reasons: list[str] = []
    if node.get("draining"):
        blocked_reasons.append("draining")
    if health == "blocked":
        blocked_reasons.append("reported_blocked")
    if runner_blocked:
        blocked_reasons.append("all_reported_runner_capabilities_blocked")
    blocked = bool(blocked_reasons) and not quarantined
    reported_active = task_id is not None
    active = bool(
        reported_active
        and connection["connected"]
        and freshness["fresh"]
        and not quarantined
    )
    if quarantined:
        status = "quarantined"
    elif blocked:
        status = "blocked"
    elif active:
        status = "active"
    elif executable_items:
        status = "ready"
    else:
        status = "unavailable"
    return {
        "status": status,
        "active": active,
        "reported_active": reported_active,
        "active_task_id": task_id,
        "executable": bool(executable_items),
        "executable_capabilities": executable_items,
        "blocked": blocked,
        "blocked_reasons": blocked_reasons,
        "quarantined": quarantined,
        "quarantine_reason": node.get("quarantine_reason"),
        "schedulable": bool(node.get("schedulable")),
    }


def _verification_truth(
    proof: dict[str, Any] | None,
    proof_truth: dict[str, Any] | None,
) -> dict[str, Any]:
    source = "home_control_plane_fleet_proof"
    truth = proof_truth or {}
    if truth.get("availability") != "live":
        return {
            "status": "unavailable",
            "verified": False,
            "last_successful_task": None,
            "source": source,
            "as_of": truth.get("as_of"),
            "reason": truth.get("reason") or "fleet_proof_unavailable",
        }
    completion = _as_dict((proof or {}).get("strict_verified_completion"))
    result_sha256 = str(completion.get("result_sha256") or "").strip().lower()
    binding_sha256 = str(completion.get("binding_sha256") or "").strip().lower()
    valid = bool(
        completion.get("proven") is True
        and completion.get("task_id")
        and SHA256_PATTERN.fullmatch(result_sha256)
        and SHA256_PATTERN.fullmatch(binding_sha256)
        and completion.get("verifier") == "control-plane/home"
        and completion.get("verifier_schema")
        == "kolibri.control-plane-completion-verifier.v1"
    )
    last_successful_task = None
    if valid:
        last_successful_task = {
            "task_id": str(completion["task_id"]),
            "capability": completion.get("kind"),
            "attempt_id": completion.get("attempt_id"),
            "completed_at": completion.get("completed_at"),
            "result_sha256": result_sha256,
            "binding_sha256": binding_sha256,
            "verifier": completion.get("verifier"),
            "verifier_schema": completion.get("verifier_schema"),
            "evidence_source": FLEET_PROOF_PATH,
        }
    return {
        "status": "verified" if valid else "unverified",
        "verified": valid,
        "last_successful_task": last_successful_task,
        "source": source,
        "as_of": truth.get("as_of"),
        "reason": None if valid else "no_strict_verified_completion",
    }


def _list_availability(items: list[dict[str, Any]]) -> str:
    values = {
        str(_as_dict(_as_dict(item.get("capabilities")).get("_truth")).get("availability"))
        for item in items
    }
    if not values:
        return "live"
    if values == {"live"}:
        return "live"
    if "live" in values:
        return "partial"
    return "stale"


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
    bearer_token: str | None = field(default=None, repr=False)

    @classmethod
    def from_environment(cls) -> "HomeControlPlaneAdapter":
        return cls(
            base_url=_validated_base_url(os.getenv(CONTROL_PLANE_ENV)),
            timeout_seconds=_bounded_timeout(
                os.getenv("KOLIBRI_CONTROL_PLANE_TIMEOUT_SECONDS")
            ),
            bearer_token=_optional_bearer_token(
                os.getenv(CONTROL_PLANE_TOKEN_FILE_ENV)
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
                headers = (
                    {"Authorization": f"Bearer {self.bearer_token}"}
                    if self.bearer_token else None
                )
                response = await client.get(path, params=params, headers=headers)
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

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if not self.bearer_token:
            raise ControlPlaneUnavailable("control_plane_token_not_configured")
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
                response = await client.post(
                    path,
                    json=body,
                    headers={"Authorization": f"Bearer {self.bearer_token}"},
                )
        except httpx.TimeoutException as exc:
            raise ControlPlaneUnavailable("control_plane_timeout") from exc
        except httpx.RequestError as exc:
            raise ControlPlaneUnavailable("control_plane_unreachable") from exc
        if response.status_code not in {200, 201, 202}:
            reason = {
                401: "control_plane_auth_invalid",
                403: "control_plane_scope_denied",
                404: "control_plane_resource_not_found",
                409: "control_plane_conflict",
                422: "control_plane_request_rejected",
            }.get(response.status_code, "control_plane_bad_status")
            raise ControlPlaneUnavailable(reason)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ControlPlaneUnavailable("control_plane_invalid_json") from exc
        if not isinstance(payload, dict):
            raise ControlPlaneUnavailable("control_plane_contract_invalid")
        return payload

    async def _fleet_proof_optional(
        self,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Read strict execution proof without hiding otherwise valid fleet data.

        Older or temporarily degraded Home deployments may still serve the
        membership endpoint while the proof endpoint is unavailable.  In that
        case the portal may show membership/freshness, but verification remains
        explicitly unavailable and can never be inferred from a heartbeat.
        """

        observed_at = _utc_now()
        try:
            payload = await self._get(FLEET_PROOF_PATH, {})
        except ControlPlaneUnavailable as exc:
            return {}, {
                "availability": "unavailable",
                "source": CONTROL_PLANE_SOURCE,
                "as_of": observed_at,
                "reason": exc.reason,
            }
        rows = payload.get("nodes")
        if (
            payload.get("schema_version") != "kolibri.fleet-capability-proof.v1"
            or not isinstance(rows, list)
        ):
            return {}, {
                "availability": "unavailable",
                "source": CONTROL_PLANE_SOURCE,
                "as_of": observed_at,
                "reason": "control_plane_fleet_proof_contract_invalid",
            }
        by_node: dict[str, dict[str, Any]] = {}
        for raw in rows:
            row = _as_dict(raw)
            node_id = str(row.get("node_id") or "").strip()
            if node_id:
                by_node[node_id] = row
        return by_node, {
            "availability": "live",
            "source": CONTROL_PLANE_SOURCE,
            "as_of": payload.get("observed_at") or observed_at,
            "status": payload.get("status"),
            "summary": _as_dict(payload.get("summary")),
        }

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
        payload, proof_result = await asyncio.gather(
            self._get(
                "/v1/nodes",
                {
                    "scope": "active",
                    "limit": control_plane_limit,
                    "offset": control_plane_offset,
                },
            ),
            self._fleet_proof_optional(),
        )
        proof_by_node, proof_truth = proof_result
        raw_nodes = payload.get("nodes")
        pagination = _as_dict(payload.get("pagination"))
        if not isinstance(raw_nodes, list) or "total_indexed" not in pagination:
            raise ControlPlaneUnavailable("control_plane_nodes_contract_invalid")

        observed_at = _utc_now()
        items = [
            self._map_node(
                _as_dict(node),
                observed_at,
                proof_by_node.get(str(_as_dict(node).get("node_id") or "")),
                proof_truth,
            )
            for node in raw_nodes
        ]
        if status:
            items = [node for node in items if node["status"] == status]
            total = len(items)
            items = items[offset:offset + page_size]
        else:
            total = _to_int(pagination.get("total_indexed"), len(items))
        availability = _list_availability(items)
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
                "verification": proof_truth,
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
        payload, proof_result = await asyncio.gather(
            self._get(
                "/v1/nodes",
                {
                    "scope": "active",
                    "limit": control_plane_limit,
                    "offset": control_plane_offset,
                },
            ),
            self._fleet_proof_optional(),
        )
        proof_by_node, proof_truth = proof_result
        raw_nodes = payload.get("nodes")
        pagination = _as_dict(payload.get("pagination"))
        if not isinstance(raw_nodes, list) or "total_indexed" not in pagination:
            raise ControlPlaneUnavailable("control_plane_agents_contract_invalid")

        observed_at = _utc_now()
        items = [
            self._map_agent(
                _as_dict(node),
                observed_at,
                proof_by_node.get(str(_as_dict(node).get("node_id") or "")),
                proof_truth,
            )
            for node in raw_nodes
        ]
        if status:
            items = [agent for agent in items if agent["status"] == status]
            total = len(items)
            items = items[offset:offset + page_size]
        else:
            total = _to_int(pagination.get("total_indexed"), len(items))
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "truth": {
                "availability": _list_availability(items),
                "source": CONTROL_PLANE_SOURCE,
                "as_of": observed_at,
                "membership": _as_dict(payload.get("membership")),
                "freshness": _as_dict(payload.get("counts")),
                "derivation": "one_agent_host_per_active_node",
                "verification": proof_truth,
            },
        }

    async def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        result = await self.list_agents(page=1, page_size=100, status=None)
        return next(
            (agent for agent in result["items"] if agent["id"] == agent_id),
            None,
        )

    def _map_agent(
        self,
        node: dict[str, Any],
        observed_at: str,
        proof: dict[str, Any] | None = None,
        proof_truth: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        node_id = str(node.get("node_id") or "").strip()
        if not node_id:
            raise ControlPlaneUnavailable("control_plane_agent_node_id_missing")
        agent_id = str(node.get("agent_id") or node_id).strip()
        freshness = str(node.get("freshness") or "stale").lower()
        availability = "live" if freshness == "fresh" else "stale"
        current_task = _active_task_id(node)
        capability_execution = _capability_execution(node)
        execution = _execution_truth(node, capability_execution)

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
            "progress": None,
            "model": None,
            "connection": _connection_truth(node),
            "freshness": _freshness_truth(node),
            "execution": execution,
            "verification": _verification_truth(proof, proof_truth),
            "capabilities": {
                "items": [str(value) for value in _as_list(node.get("capabilities"))],
                "runners": runner_summary,
                "execution": capability_execution,
                "executable_items": execution["executable_capabilities"],
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

    def _map_node(
        self,
        node: dict[str, Any],
        observed_at: str,
        proof: dict[str, Any] | None = None,
        proof_truth: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
        capability_execution = _capability_execution(node)
        execution = _execution_truth(node, capability_execution)
        capabilities = {
            "items": capability_items,
            "runners": _as_dict(node.get("runners")),
            "execution": capability_execution,
            "executable_items": execution["executable_capabilities"],
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
        return {
            "id": node_id,
            "name": str(node.get("hostname") or node_id),
            "region": str(_as_dict(node.get("labels")).get("region") or ""),
            "ip_address": str(node.get("mesh_ip") or node.get("internal_ip") or ""),
            "status": _node_status(node),
            "connection": _connection_truth(node),
            "freshness": _freshness_truth(node),
            "execution": execution,
            "verification": _verification_truth(proof, proof_truth),
            "cpu_percent": str(node.get("cpu_percent")) if node.get("cpu_percent") is not None else "unavailable",
            "ram_percent": ram_percent or "unavailable",
            "disk_percent": disk_percent or "unavailable",
            "network_mbps": str(node.get("network_mbps")) if node.get("network_mbps") is not None else "unavailable",
            "agent_count": 1 if node.get("agent_id") else 0,
            "task_count": 1 if execution["reported_active"] else 0,
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

    async def task_summary(self) -> dict[str, Any]:
        payload = await self._get("/v1/tasks/summary", {})
        if (
            payload.get("schema_version") != "kolibri.task-summary.v1"
            or payload.get("authority") != "control-plane/home"
            or not isinstance(payload.get("by_state"), dict)
        ):
            raise ControlPlaneUnavailable("control_plane_task_summary_contract_invalid")
        by_state = _as_dict(payload.get("by_state"))
        return {
            "total": _to_int(payload.get("total"), 0),
            "queued": _to_int(by_state.get("queued"), 0),
            "running": _to_int(by_state.get("running"), 0),
            "waiting_review": _to_int(by_state.get("waiting_review"), 0),
            "completed": _to_int(by_state.get("completed"), 0),
            "failed": _to_int(by_state.get("failed"), 0),
            "cancelled": _to_int(by_state.get("cancelled"), 0),
            "dead_letter": _to_int(by_state.get("dead_letter"), 0),
            "as_of": str(payload.get("generated_at") or _utc_now()),
            "queue_total": _to_int(payload.get("queue_total"), 0),
            "active": _to_int(payload.get("active"), 0),
            "latest_event_cursor": _to_int(payload.get("latest_event_cursor"), 0),
            "source": CONTROL_PLANE_SOURCE,
        }

    async def list_events(
        self,
        *,
        after_cursor: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        payload = await self._get(
            "/v1/events",
            {"after_cursor": max(0, int(after_cursor)), "limit": max(1, min(int(limit), 500))},
        )
        rows = payload.get("data")
        if payload.get("object") != "list" or not isinstance(rows, list):
            raise ControlPlaneUnavailable("control_plane_events_contract_invalid")
        items = [self._map_event(_as_dict(row)) for row in rows]
        next_cursor = payload.get("next_cursor")
        return {
            "items": items,
            "total": len(items),
            "next_cursor": str(next_cursor) if next_cursor is not None else None,
            "as_of": _utc_now(),
            "source": CONTROL_PLANE_SOURCE,
        }

    async def submit_owner_task(self, envelope: dict[str, Any]) -> dict[str, Any]:
        payload = await self._post("/v1/tasks", envelope)
        if (
            str(payload.get("task_id") or "") != str(envelope.get("task_id") or "")
            or payload.get("state") not in {"queued", "leased", "running"}
        ):
            raise ControlPlaneUnavailable("control_plane_task_create_contract_invalid")
        return self._map_task(payload, _utc_now())

    async def get_task_detail(self, task_id: str) -> dict[str, Any]:
        payload = await self._get(f"/v1/tasks/{task_id}", {})
        if str(payload.get("task_id") or "") != task_id:
            raise ControlPlaneUnavailable("control_plane_task_detail_contract_invalid")
        envelope = _as_dict(payload.get("envelope"))
        verifier = _as_dict(payload.get("completion_verifier"))
        evidence = _as_dict(payload.get("completion_evidence"))
        result_reference = str(payload.get("result_reference") or "")
        safe_reference = (
            result_reference
            if result_reference.startswith(("artifact://sha256/", "sha256:"))
            else None
        )
        mapped = self._map_task(payload, _utc_now())
        mapped.update({
            "kind": str(payload.get("kind") or envelope.get("kind") or "unknown"),
            "objective": str(envelope.get("objective") or envelope.get("message") or ""),
            "runner": str(envelope.get("runner") or "") or None,
            "required_capability": str(envelope.get("required_capability") or "") or None,
            "attempt_id": str(payload.get("attempt_id") or "") or None,
            "fencing_token": payload.get("fencing_token"),
            "result_reference": safe_reference,
            "verification": {
                "verdict": verifier.get("verdict"),
                "failed_checks": _as_list(verifier.get("failed_checks")),
                "result_sha256": evidence.get("result_sha256"),
                "binding_sha256": evidence.get("binding_sha256"),
            },
        })
        return mapped

    async def list_task_events(
        self,
        task_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        payload = await self._get(
            f"/v1/tasks/{task_id}/events",
            {
                "after_sequence": max(0, int(after_sequence)),
                "limit": max(1, min(int(limit), 500)),
            },
        )
        rows = payload.get("data")
        if (
            payload.get("object") != "list"
            or str(payload.get("task_id") or "") != task_id
            or not isinstance(rows, list)
        ):
            raise ControlPlaneUnavailable("control_plane_task_events_contract_invalid")
        items = [self._map_event(_as_dict(row)) for row in rows]
        return {
            "items": items,
            "total": len(items),
            "next_sequence": _to_int(payload.get("next_sequence"), after_sequence),
            "as_of": _utc_now(),
            "source": CONTROL_PLANE_SOURCE,
        }

    async def cancel_task(self, task_id: str, *, reason: str) -> dict[str, Any]:
        payload = await self._post(
            f"/v1/tasks/{task_id}/cancel",
            {"reason": reason},
        )
        if str(payload.get("task_id") or "") != task_id:
            raise ControlPlaneUnavailable("control_plane_task_cancel_contract_invalid")
        return self._map_task(payload, _utc_now())

    @staticmethod
    def _map_event(event: dict[str, Any]) -> dict[str, Any]:
        if event.get("schema_version") != "kolibri.event.v1":
            raise ControlPlaneUnavailable("control_plane_event_contract_invalid")
        event_id = str(event.get("id") or "").strip()
        subject = str(event.get("subject") or "").strip()
        event_type = str(event.get("type") or "").strip()
        occurred_at = str(event.get("occurred_at") or "").strip()
        sequence = _to_int(event.get("sequence"), -1)
        cursor = _to_int(event.get("cursor"), -1)
        if (
            not event_id
            or not subject.startswith("task/")
            or not event_type
            or not occurred_at
            or sequence < 1
            or cursor < 1
        ):
            raise ControlPlaneUnavailable("control_plane_event_contract_invalid")
        data = _as_dict(event.get("data"))
        provenance = _as_dict(event.get("provenance"))
        payload_sha256 = hashlib.sha256(
            json.dumps(
                event,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return {
            "event_id": event_id,
            "task_id": subject.removeprefix("task/"),
            "event_type": event_type,
            "state": data.get("to_state"),
            "actor": provenance.get("actor"),
            "node_id": data.get("lease_owner"),
            "attempt_id": data.get("attempt_id"),
            "occurred_at": occurred_at,
            "sequence": sequence,
            "cursor": cursor,
            "payload_sha256": payload_sha256,
            "data": data,
        }

    async def cluster_stats(self) -> dict[str, Any]:
        """Build cluster aggregates only from the authoritative Home API."""

        nodes_payload, first_tasks, proof_result = await asyncio.gather(
            self._get("/v1/nodes", {"scope": "active", "limit": 250, "offset": 0}),
            self._get("/v1/tasks", {"limit": 250, "offset": 0}),
            self._fleet_proof_optional(),
        )
        proof_by_node, proof_truth = proof_result
        raw_nodes = nodes_payload.get("nodes")
        node_pagination = _as_dict(nodes_payload.get("pagination"))
        raw_tasks = first_tasks.get("tasks")
        task_pagination = _as_dict(first_tasks.get("pagination"))
        if not isinstance(raw_nodes, list) or "total_indexed" not in node_pagination:
            raise ControlPlaneUnavailable("control_plane_nodes_contract_invalid")
        if not isinstance(raw_tasks, list) or "total_indexed" not in task_pagination:
            raise ControlPlaneUnavailable("control_plane_tasks_contract_invalid")

        total_tasks = _to_int(task_pagination.get("total_indexed"), len(raw_tasks))
        task_pages = [raw_tasks]
        for offset in range(250, total_tasks, 250):
            page = await self._get("/v1/tasks", {"limit": 250, "offset": offset})
            values = page.get("tasks")
            if not isinstance(values, list):
                raise ControlPlaneUnavailable("control_plane_tasks_contract_invalid")
            task_pages.append(values)
        tasks = [_as_dict(task) for page in task_pages for task in page]
        if len(tasks) != total_tasks:
            raise ControlPlaneUnavailable("control_plane_tasks_pagination_incomplete")

        observed_at = _utc_now()
        nodes = [
            self._map_node(
                _as_dict(node),
                observed_at,
                proof_by_node.get(str(_as_dict(node).get("node_id") or "")),
                proof_truth,
            )
            for node in raw_nodes
        ]
        agents = [
            self._map_agent(
                _as_dict(node),
                observed_at,
                proof_by_node.get(str(_as_dict(node).get("node_id") or "")),
                proof_truth,
            )
            for node in raw_nodes
        ]
        mapped_tasks = [self._map_task(task, observed_at) for task in tasks]

        def count(values: list[dict[str, Any]], key: str, states: set[str]) -> int:
            return sum(1 for value in values if str(value.get(key)) in states)

        def average(field: str) -> float | None:
            values: list[float] = []
            for node in nodes:
                raw = node.get(field)
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    continue
                values.append(value)
            return round(sum(values) / len(values), 1) if values else None

        availability = _list_availability(nodes)
        strict_working = sum(
            1
            for node in nodes
            if _as_dict(node.get("connection")).get("connected") is True
            and _as_dict(node.get("freshness")).get("fresh") is True
            and _as_dict(node.get("execution")).get("executable") is True
            and _as_dict(node.get("execution")).get("blocked") is not True
            and _as_dict(node.get("execution")).get("quarantined") is not True
            and _as_dict(node.get("verification")).get("verified") is True
        )
        unavailable_nodes = sum(
            1
            for node in nodes
            if _as_dict(node.get("connection")).get("connected") is not True
            or _as_dict(node.get("freshness")).get("status") == "stale"
            or _as_dict(node.get("execution")).get("quarantined") is True
        )
        return {
            "nodes": {
                "membership_total": len(nodes),
                "connected": sum(
                    1 for node in nodes
                    if _as_dict(node.get("connection")).get("connected") is True
                ),
                "fresh": sum(
                    1 for node in nodes
                    if _as_dict(node.get("freshness")).get("fresh") is True
                ),
                "capability_executable": sum(
                    1 for node in nodes
                    if _as_dict(node.get("execution")).get("executable") is True
                ),
                "active": sum(
                    1 for node in nodes
                    if _as_dict(node.get("execution")).get("active") is True
                ),
                "verified": sum(
                    1 for node in nodes
                    if _as_dict(node.get("verification")).get("verified") is True
                ),
                "blocked": sum(
                    1 for node in nodes
                    if _as_dict(node.get("execution")).get("blocked") is True
                ),
                "quarantined": sum(
                    1 for node in nodes
                    if _as_dict(node.get("execution")).get("quarantined") is True
                ),
                "stale": sum(
                    1 for node in nodes
                    if _as_dict(node.get("freshness")).get("status") == "stale"
                ),
                # Compatibility aliases are intentionally stricter than the
                # old heartbeat-derived meaning.  ``healthy`` now requires a
                # fresh, executable node and a strict verified completion.
                "total": len(nodes),
                "healthy": strict_working,
                "degraded": max(0, len(nodes) - strict_working - unavailable_nodes),
                "offline": unavailable_nodes,
            },
            "agents": {
                "membership_total": len(agents),
                "active": count(agents, "status", {"active"}),
                "idle": count(agents, "status", {"idle"}),
                "paused": count(agents, "status", {"paused"}),
                "executable": sum(
                    1 for agent in agents
                    if _as_dict(agent.get("execution")).get("executable") is True
                ),
                "verified": sum(
                    1 for agent in agents
                    if _as_dict(agent.get("verification")).get("verified") is True
                ),
            },
            "tasks": {
                "total": len(mapped_tasks),
                "running": count(mapped_tasks, "state", {"running", "assigned"}),
                "queued": count(mapped_tasks, "state", {"queued", "waiting"}),
                "completed": count(mapped_tasks, "state", {"completed"}),
                "failed": count(mapped_tasks, "state", {"failed"}),
                "cancelled": count(mapped_tasks, "state", {"cancelled"}),
            },
            "resources": {
                "avg_cpu": average("cpu_percent"),
                "avg_ram": average("ram_percent"),
                "avg_disk": average("disk_percent"),
            },
            "truth": {
                "availability": availability,
                "source": CONTROL_PLANE_SOURCE,
                "as_of": observed_at,
                "membership": _as_dict(nodes_payload.get("membership")),
                "task_pages": len(task_pages),
                "verification": proof_truth,
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
