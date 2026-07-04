#!/usr/bin/env python3
"""Kolibri Factory physical foundation registry.

Defines the 21 canonical physical servers, command nodes, network nodes,
and operator assets. This is the single source of truth for what exists
in the physical infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

AssetClass = Literal[
    "physical_server",
    "command_node",
    "network_node",
    "operator_kit",
    "logical_worker",
    "mesh_alias",
]

ServerRole = Literal[
    "control",
    "execution",
    "hybrid",
    "reserve",
    "model",
    "tool",
    "rag",
    "home_noc",
]

Lifecycle = Literal[
    "active",
    "degraded",
    "stale",
    "quarantined",
    "retired",
]


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


# ── 21 Canonical Physical Servers ──────────────────────────────────────

CANONICAL_SERVERS: list[AssetRecord] = [
    AssetRecord("home", "plastilin", "physical_server",
                aliases=["kolibri-home", "coordinator"],
                role="hybrid", internal_ip="10.99.0.1", external_ip="178.207.11.90",
                ssh_alias="kolibri-home", ssh_user="ladik"),
    AssetRecord("main", "kolibri-main-api", "physical_server",
                aliases=["kolibri-main"],
                role="control", internal_ip="10.99.0.2", external_ip="104.253.43.117",
                ssh_alias="kolibri-main"),
    AssetRecord("primary-candidate", "kolibri", "physical_server",
                aliases=["kolibri-primary-codex", "primary"],
                role="hybrid", internal_ip="10.99.0.10", external_ip="78.17.4.108",
                ssh_alias="kolibri-primary-codex"),
    AssetRecord("uiap", "kolibri-rag-knowledge", "physical_server",
                aliases=["kolibri-uiap", "rag"],
                role="rag", internal_ip="10.99.0.3", external_ip="31.57.26.151",
                ssh_alias="kolibri-uiap"),
    AssetRecord("qjns", "kolibri-tools-executor", "physical_server",
                aliases=["kolibri-qjns"],
                role="tool", internal_ip="10.99.0.4", external_ip="217.60.63.97",
                ssh_alias="kolibri-qjns"),
    AssetRecord("9fts", "kolibri-inference-recovery", "physical_server",
                aliases=["kolibri-9fts", "inference"],
                role="model", internal_ip="10.99.0.5", external_ip="94.183.235.154",
                ssh_alias="kolibri-9fts"),
    AssetRecord("new", "kolibri-worker-backup", "physical_server",
                aliases=["kolibri-new", "worker-backup"],
                role="reserve", internal_ip="10.99.0.6", external_ip="109.248.161.39",
                ssh_alias="kolibri-new"),
    AssetRecord("server-kfrm", "server-kfrm", "physical_server",
                aliases=[],
                role="execution", internal_ip="10.99.0.7", external_ip="217.60.63.31",
                ssh_alias="server-kfrm"),
    AssetRecord("reserve242", "kolibri-qa-security", "physical_server",
                aliases=["reserve"],
                role="reserve", external_ip="31.57.26.242",
                ssh_alias="reserve242"),
    AssetRecord("highload", "kolibri-ci-build-highload", "physical_server",
                aliases=["hostvds-highload"],
                role="execution", external_ip="45.38.139.182",
                ssh_alias="hostvds-highload"),
    AssetRecord("paris", "kolibri-paris-build-reserve", "physical_server",
                aliases=["hostvds-paris-highload"],
                role="reserve", external_ip="95.182.83.60",
                ssh_alias="hostvds-paris-highload"),
    AssetRecord("agent-01", "kolibri-backend-lead", "physical_server",
                aliases=["hostvds-agent-01"],
                role="execution", external_ip="31.57.27.128",
                ssh_alias="hostvds-agent-01"),
    AssetRecord("agent-02", "kolibri-frontend-design", "physical_server",
                aliases=["hostvds-agent-02"],
                role="execution", external_ip="213.232.204.223",
                ssh_alias="hostvds-agent-02"),
    AssetRecord("agent-03", "kolibri-infra-network", "physical_server",
                aliases=["hostvds-agent-03"],
                role="execution", external_ip="188.130.206.204",
                ssh_alias="hostvds-agent-03"),
    AssetRecord("agent-04", "kolibri-qa-browser", "physical_server",
                aliases=["hostvds-agent-04"],
                role="execution", external_ip="31.59.41.146",
                ssh_alias="hostvds-agent-04"),
    AssetRecord("agent-05", "kolibri-security-audit", "physical_server",
                aliases=["hostvds-agent-05"],
                role="execution", external_ip="31.56.196.10",
                ssh_alias="hostvds-agent-05"),
    AssetRecord("agent-06", "kolibri-docs-knowledge", "physical_server",
                aliases=["hostvds-agent-06"],
                role="execution", external_ip="94.183.236.19",
                ssh_alias="hostvds-agent-06"),
    AssetRecord("agent-07", "kolibri-formulalm-eval", "physical_server",
                aliases=["hostvds-agent-07"],
                role="model", external_ip="31.56.225.35",
                ssh_alias="hostvds-agent-07"),
    AssetRecord("agent-08", "kolibri-rag-eval", "physical_server",
                aliases=["hostvds-agent-08"],
                role="rag", external_ip="94.183.229.121",
                ssh_alias="hostvds-agent-08"),
    AssetRecord("agent-09", "kolibri-release-canary", "physical_server",
                aliases=["hostvds-agent-09"],
                role="execution", external_ip="45.38.137.104",
                ssh_alias="hostvds-agent-09"),
    AssetRecord("agent-10", "kolibri-hk-edge-load", "physical_server",
                aliases=["hostvds-agent-10"],
                role="execution", external_ip="217.60.38.191",
                ssh_alias="hostvds-agent-10",
                lifecycle="quarantined",
                safe_to_schedule=False,
                next_action="restore provider connectivity"),
]

# ── Command Nodes ──────────────────────────────────────────────────────

COMMAND_NODES: list[AssetRecord] = [
    AssetRecord("mac-owner", "MacBook-Air-Vladislav", "command_node",
                role="owner_command_client", internal_ip="10.99.0.100",
                safe_to_schedule=False,
                next_action="not required for factory runtime"),
]

# ── Network Nodes ──────────────────────────────────────────────────────

NETWORK_NODES: list[AssetRecord] = [
    AssetRecord("mikrotik-router", "MikroTik hAP ac^2", "network_node",
                role="home_network_router|vpn_gateway",
                internal_ip="10.99.99.1", external_ip="178.207.11.90",
                safe_to_schedule=False,
                next_action="monitor only, no changes without approval"),
]

# ── Operator Assets ────────────────────────────────────────────────────

OPERATOR_ASSETS: list[AssetRecord] = [
    AssetRecord("usb-operator-kit", "Kolibri SSH Key + Recovery Docs", "operator_kit",
                role="emergency_recovery_package",
                safe_to_schedule=False,
                next_action="maintain offline recovery runbook"),
]


def all_assets() -> list[AssetRecord]:
    """Return all registered assets."""
    return (
        CANONICAL_SERVERS
        + COMMAND_NODES
        + NETWORK_NODES
        + OPERATOR_ASSETS
    )


def canonical_server_count() -> int:
    """Return the number of canonical physical servers."""
    return len(CANONICAL_SERVERS)


def scheduleable_servers() -> list[AssetRecord]:
    """Return servers safe for task scheduling."""
    return [s for s in CANONICAL_SERVERS if s.safe_to_schedule]


if __name__ == "__main__":
    print(f"Canonical servers: {canonical_server_count()}")
    print(f"Command nodes: {len(COMMAND_NODES)}")
    print(f"Network nodes: {len(NETWORK_NODES)}")
    print(f"Operator assets: {len(OPERATOR_ASSETS)}")
    print(f"Total assets: {len(all_assets())}")
    print(f"Scheduleable: {len(scheduleable_servers())}")
