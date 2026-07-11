#!/usr/bin/env python3
"""Dynamic Kolibri fleet inventory backed by Home Control Plane membership.

Physical workers are never declared in this module.  The replicated mesh
manifest is the authority for active physical membership; Agent Host
registration and fresh heartbeats determine whether a canonical member may be
scheduled.  Redis-only identities remain historical audit records.
Home is the sole Control Plane authority.  Every other registered server is
classified as an execution/model/reserve worker from its advertised
capabilities.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal
from urllib.parse import urlencode
from urllib.request import urlopen

try:
    from control_plane_endpoint import DEFAULT_MESH_MANIFEST, resolve_home_control_plane_url
except ImportError:  # pragma: no cover - package import
    from ops.control_plane_endpoint import DEFAULT_MESH_MANIFEST, resolve_home_control_plane_url


AssetClass = Literal[
    "physical_server",
    "command_node",
    "network_node",
    "operator_kit",
]

Lifecycle = Literal["active", "degraded", "stale", "quarantined", "retired"]


@dataclass
class AssetRecord:
    node_id: str
    canonical_name: str
    asset_class: AssetClass
    aliases: list[str] = field(default_factory=list)
    role: str = ""
    internal_ip: str | None = None
    external_ip: str | None = None
    ssh_alias: str | None = None
    ssh_user: str = "root"
    lifecycle: Lifecycle = "active"
    safe_to_schedule: bool = True
    next_action: str = ""
    api_port: int | None = None


# Operator/network assets are not factory membership and remain explicit.
COMMAND_NODES: list[AssetRecord] = [
    AssetRecord(
        "mac-owner",
        "MacBook-Air-Vladislav",
        "command_node",
        role="owner_command_client",
        safe_to_schedule=False,
        next_action="not a factory worker",
    ),
]

NETWORK_NODES: list[AssetRecord] = [
    AssetRecord(
        "mikrotik-router",
        "MikroTik",
        "network_node",
        role="home_network_router|vpn_gateway",
        safe_to_schedule=False,
        next_action="monitor only; changes require owner approval",
    ),
]

OPERATOR_ASSETS: list[AssetRecord] = [
    AssetRecord(
        "usb-operator-kit",
        "Kolibri recovery kit",
        "operator_kit",
        role="emergency_recovery_package",
        safe_to_schedule=False,
        next_action="maintain offline recovery runbook",
    ),
]


def _mesh_addresses(manifest_path: str | Path | None = None) -> dict[str, str]:
    path = Path(
        manifest_path
        or os.environ.get("KOLIBRI_MESH_MEMBERSHIP_MANIFEST")
        or DEFAULT_MESH_MANIFEST
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    peers = payload.get("peers", {}) if isinstance(payload, dict) else {}
    records = peers.values() if isinstance(peers, dict) else peers if isinstance(peers, list) else []
    result: dict[str, str] = {}
    for peer in records:
        if not isinstance(peer, dict):
            continue
        node_id = str(peer.get("node_id") or "").strip()
        mesh_ip = str(peer.get("mesh_ip") or "").strip()
        if node_id and mesh_ip:
            result[node_id] = mesh_ip
    return result


def _role_for(node_id: str, capabilities: set[str]) -> str:
    if node_id == "home":
        return "control"
    # A worker cannot promote itself to Control Plane through registration.
    if capabilities & {"formulalm", "model", "training", "inference"}:
        return "model"
    if capabilities & {"reserve", "backup"}:
        return "reserve"
    return "execution"


def records_from_membership(
    nodes: Iterable[dict[str, Any]],
    *,
    mesh_addresses: dict[str, str] | None = None,
) -> list[AssetRecord]:
    """Convert truthful Control Plane node records into schedulable assets."""

    addresses = mesh_addresses or {}
    result: list[AssetRecord] = []
    seen: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("membership_scope") not in {None, "active"}:
            continue
        node_id = str(node.get("node_id") or "").strip()
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        capabilities = {
            str(item).strip().lower()
            for item in node.get("capabilities", [])
            if str(item).strip()
        }
        health = str(node.get("health") or "unknown").strip().lower()
        draining = bool(node.get("draining"))
        membership_state = str(node.get("membership_state") or "registered")
        schedulable = node.get("schedulable") is True
        if membership_state == "missing_agent_host_registration" or health == "quarantined":
            lifecycle: Lifecycle = "quarantined"
        elif schedulable:
            lifecycle = "active"
        elif health in {"online", "healthy", "ready", "degraded"}:
            lifecycle = "degraded"
        else:
            lifecycle = "stale"
        canonical_name = str(node.get("hostname") or node.get("display_name") or node_id).strip()
        result.append(
            AssetRecord(
                node_id=node_id,
                canonical_name=canonical_name,
                asset_class="physical_server",
                aliases=[],
                role=_role_for(node_id, capabilities),
                internal_ip=addresses.get(node_id),
                lifecycle=lifecycle,
                safe_to_schedule=schedulable and not draining,
                next_action=(
                    ""
                    if schedulable and not draining
                    else "undrain after verification"
                    if draining
                    else "restore canonical Agent Host registration"
                    if lifecycle == "quarantined"
                    else "restore Agent Host heartbeat"
                ),
                api_port=9101 if node_id == "home" else None,
            )
        )
    return sorted(result, key=lambda item: (item.node_id != "home", item.node_id))


def load_registered_servers(
    control_url: str | None = None,
    *,
    manifest_path: str | Path | None = None,
    opener=urlopen,
) -> list[AssetRecord]:
    """Read the full, paginated membership snapshot from canonical Home."""

    base_url = resolve_home_control_plane_url(control_url, manifest_path=manifest_path)
    nodes: list[dict[str, Any]] = []
    offset = 0
    limit = 250
    while True:
        query = urlencode({"scope": "active", "limit": limit, "offset": offset})
        with opener(f"{base_url}/v1/nodes?{query}", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        page = payload.get("nodes", []) if isinstance(payload, dict) else []
        if not isinstance(page, list):
            raise ValueError("home_membership_payload_invalid")
        nodes.extend(item for item in page if isinstance(item, dict))
        pagination = payload.get("pagination", {}) if isinstance(payload, dict) else {}
        returned = int(pagination.get("returned", len(page)))
        total = int(pagination.get("total_indexed", len(nodes)))
        offset += returned
        if returned == 0 or offset >= total:
            break
    return records_from_membership(nodes, mesh_addresses=_mesh_addresses(manifest_path))


def all_assets(servers: Iterable[AssetRecord] | None = None) -> list[AssetRecord]:
    current_servers = list(servers) if servers is not None else load_registered_servers()
    return current_servers + COMMAND_NODES + NETWORK_NODES + OPERATOR_ASSETS


def canonical_server_count(servers: Iterable[AssetRecord] | None = None) -> int:
    return len(list(servers) if servers is not None else load_registered_servers())


def scheduleable_servers(servers: Iterable[AssetRecord] | None = None) -> list[AssetRecord]:
    current_servers = list(servers) if servers is not None else load_registered_servers()
    return [server for server in current_servers if server.safe_to_schedule]


if __name__ == "__main__":
    snapshot = load_registered_servers()
    print(f"Registered physical servers: {len(snapshot)}")
    print(f"Scheduleable: {len(scheduleable_servers(snapshot))}")
