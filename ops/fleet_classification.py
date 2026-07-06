#!/usr/bin/env python3
"""Kolibri Fleet Classification — едининая система классификации серверов, нод, агентов и подсетей.

Читает из factory_registry.py, не модифицирует его.
Выводит удобочитаемую таблицу для человека.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Literal

# ── Типы классификации ─────────────────────────────────────────────

ServerTier = Literal["control", "execution", "model", "hybrid", "reserve"]
NodeKind = Literal["fabric_node", "mesh_shadow", "organism_node", "raw_server"]
AgentType = Literal["mimo_direct", "reviewer", "orchestrator", "researcher", "tester", "builder", "edge", "unknown"]
SubnetTag = Literal["wireguard_mesh", "lan", "mikrotik", "public"]

# ── Русские названия ───────────────────────────────────────────────

SERVER_TIER_RU: dict[str, str] = {
    "control": "Управление",
    "execution": "Вычисление",
    "model": "Модельный",
    "hybrid": "Гибридный",
    "reserve": "Резервный",
}

NODE_KIND_RU: dict[str, str] = {
    "fabric_node": "Узел фабрики",
    "mesh_shadow": "Тень меша",
    "organism_node": "Организм",
    "raw_server": "Сервер",
}

AGENT_TYPE_RU: dict[str, str] = {
    "mimo_direct": "MIMO Исполнитель",
    "reviewer": "Ревьюер",
    "orchestrator": "Оркестратор",
    "researcher": "Исследователь",
    "tester": "Тестировщик",
    "builder": "Сборщик",
    "edge": "Граничный",
    "unknown": "Неизвестный",
}

ROLE_TO_TIER: dict[str, ServerTier] = {
    "control": "control",
    "home_noc": "control",
    "execution": "execution",
    "tool": "execution",
    "hybrid": "hybrid",
    "model": "model",
    "rag": "model",
    "reserve": "reserve",
}

# ── Датаклассы ─────────────────────────────────────────────────────

@dataclass
class ServerClassification:
    node_id: str
    canonical_name: str
    tier: ServerTier
    tier_ru: str
    internal_ip: str | None
    external_ip: str | None
    ssh_alias: str | None
    lifecycle: str
    api_port: int | None = None
    api_endpoint: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SubnetDefinition:
    tag: str
    cidr: str
    description_ru: str
    gateway: str | None
    member_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FleetClassification:
    servers: dict[str, ServerClassification]
    subnets: dict[str, SubnetDefinition]
    generated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "servers": {k: v.to_dict() for k, v in self.servers.items()},
            "subnets": {k: v.to_dict() for k, v in self.subnets.items()},
            "generated_at": self.generated_at,
        }

    def summary_table(self) -> str:
        lines = [
            "=" * 80,
            "KOLIBRI FLEET CLASSIFICATION",
            "=" * 80,
            "",
            f"{'Node ID':<20} {'Name':<28} {'Tier':<14} {'VPN IP':<16} {'Public IP':<16}",
            "-" * 80,
        ]

        for tier in ["control", "hybrid", "model", "execution", "reserve"]:
            for s in self.servers.values():
                if s.tier == tier:
                    ip_vpn = s.internal_ip or "—"
                    ip_pub = s.external_ip or "—"
                    lines.append(
                        f"{s.node_id:<20} {s.canonical_name:<28} {s.tier_ru:<14} {ip_vpn:<16} {ip_pub:<16}"
                    )

        lines.extend(["", "SUBNETS", "-" * 80])
        for subnet in self.subnets.values():
            gw = subnet.gateway or "—"
            lines.append(
                f"{subnet.tag:<18} {subnet.cidr:<20} {subnet.description_ru:<28} {gw:<16}"
            )

        lines.extend(["=" * 80, f"Total servers: {len(self.servers)}"])
        for tier in ["control", "hybrid", "model", "execution", "reserve"]:
            count = sum(1 for s in self.servers.values() if s.tier == tier)
            if count:
                lines.append(f"  {SERVER_TIER_RU[tier]}: {count}")

        return "\n".join(lines)


# ── Данные серверов ────────────────────────────────────────────────

SERVERS_DATA: list[tuple] = [
    # (node_id, canonical_name, role, internal_ip, external_ip, ssh_alias, lifecycle, api_port)
    ("home", "plastilin", "control", "192.168.88.210", "178.207.11.90", "kolibri-home", "active", 9101),
    ("main", "kolibri-main-api", "control", "10.99.0.2", "104.253.43.117", "kolibri-main", "active", 8000),
    ("primary-candidate", "kolibri", "hybrid", "10.99.0.10", "78.17.4.108", "kolibri-primary-codex", "active", None),
    ("uiap", "kolibri-rag-knowledge", "model", "10.99.0.3", "31.57.26.151", "kolibri-uiap", "active", 8002),
    ("qjns", "kolibri-tools-executor", "execution", "10.99.0.4", "217.60.63.97", "kolibri-qjns", "active", 8003),
    ("9fts", "kolibri-inference-recovery", "model", "10.99.0.5", "94.183.235.154", "kolibri-9fts", "active", 8001),
    ("new", "kolibri-worker-backup", "reserve", "10.99.0.6", "109.248.161.39", "kolibri-new", "active", 8001),
    ("server-kfrm", "server-kfrm", "execution", "10.99.0.31", "217.60.63.31", "server-kfrm", "active", 8001),
    ("reserve242", "kolibri-qa-security", "reserve", "10.99.0.21", "31.57.26.242", "reserve242", "active", 8001),
    ("highload", "kolibri-ci-build-highload", "execution", "10.99.0.19", "45.38.139.182", "hostvds-highload", "active", 8001),
    ("paris", "kolibri-paris-build-reserve", "reserve", "10.99.0.20", "95.182.83.60", "hostvds-paris-highload", "active", 8001),
    ("agent-01", "kolibri-backend-lead", "execution", "10.99.0.8", "31.57.27.128", "hostvds-agent-01", "active", 8001),
    ("agent-02", "kolibri-frontend-design", "execution", "10.99.0.9", "213.232.204.223", "hostvds-agent-02", "active", 8001),
    ("agent-03", "kolibri-infra-network", "execution", "10.99.0.11", "188.130.206.204", "hostvds-agent-03", "active", 8001),
    ("agent-04", "kolibri-qa-browser", "execution", "10.99.0.12", "31.59.41.146", "hostvds-agent-04", "active", 8001),
    ("agent-05", "kolibri-security-audit", "execution", "10.99.0.13", "31.56.196.10", "hostvds-agent-05", "active", 8001),
    ("agent-06", "kolibri-docs-knowledge", "execution", "10.99.0.14", "45.39.33.252", "hostvds-agent-06", "active", 8001),
    ("agent-07", "kolibri-formulalm-eval", "model", "10.99.0.15", "46.8.225.34", "hostvds-agent-07", "active", 8001),
    ("agent-08", "kolibri-rag-eval", "model", "10.99.0.16", "31.59.105.200", "hostvds-agent-08", "active", 8001),
    ("agent-09", "kolibri-release-canary", "execution", "10.99.0.17", "95.182.84.254", "hostvds-agent-09", "active", 8001),
    ("agent-10", "kolibri-hk-edge-load", "execution", "10.99.0.18", "217.60.38.191", "hostvds-agent-10", "active", 8001),
]

SUBNETS_DATA: list[tuple] = [
    ("wireguard_mesh", "10.99.0.0/24", "Mesh-сеть WireGuard", "10.99.0.1"),
    ("lan", "192.168.88.0/24", "Локальная сеть Home", "192.168.88.1"),
    ("mikrotik", "10.99.99.0/24", "Управление MikroTik", "10.99.99.1"),
    ("public", "0.0.0.0/0", "Публичные IP", None),
]


# ── Builder ─────────────────────────────────────────────────────────

def build_fleet_classification() -> FleetClassification:
    servers: dict[str, ServerClassification] = {}

    for node_id, name, role, vpn_ip, pub_ip, ssh, lifecycle, api_port in SERVERS_DATA:
        tier = ROLE_TO_TIER.get(role, "execution")
        tier_ru = SERVER_TIER_RU[tier]
        api_endpoint = f"http://{vpn_ip}:{api_port}" if api_port and vpn_ip else None

        servers[node_id] = ServerClassification(
            node_id=node_id,
            canonical_name=name,
            tier=tier,
            tier_ru=tier_ru,
            internal_ip=vpn_ip,
            external_ip=pub_ip,
            ssh_alias=ssh,
            lifecycle=lifecycle,
            api_port=api_port,
            api_endpoint=api_endpoint,
        )

    subnet_members: dict[str, int] = {"wireguard_mesh": len(SERVERS_DATA), "lan": 2, "mikrotik": 1, "public": len(SERVERS_DATA)}
    subnets: dict[str, SubnetDefinition] = {}
    for tag, cidr, desc, gw in SUBNETS_DATA:
        subnets[tag] = SubnetDefinition(tag=tag, cidr=cidr, description_ru=desc, gateway=gw, member_count=subnet_members.get(tag, 0))

    return FleetClassification(servers=servers, subnets=subnets)


if __name__ == "__main__":
    fc = build_fleet_classification()
    print(fc.summary_table())
    print()
    print("JSON:")
    print(json.dumps(fc.to_dict(), indent=2, ensure_ascii=False))
