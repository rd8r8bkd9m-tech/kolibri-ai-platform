#!/usr/bin/env python3
"""Human-readable classification of the live Kolibri membership snapshot."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable, Literal

try:
    from factory_registry import AssetRecord, load_registered_servers
except ImportError:  # pragma: no cover - package import
    from ops.factory_registry import AssetRecord, load_registered_servers


ServerTier = Literal["control", "execution", "model", "reserve"]

SERVER_TIER_RU: dict[str, str] = {
    "control": "Управление",
    "execution": "Вычисление",
    "model": "Модельный",
    "reserve": "Резервный",
}


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
    schedulable: bool
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
    generated_at: str

    def to_dict(self) -> dict:
        return {
            "servers": {key: value.to_dict() for key, value in self.servers.items()},
            "subnets": {key: value.to_dict() for key, value in self.subnets.items()},
            "generated_at": self.generated_at,
            "source": "home_mesh_manifest_canonical_membership",
        }

    def summary_table(self) -> str:
        lines = [
            "=" * 96,
            "KOLIBRI LIVE FLEET CLASSIFICATION",
            "=" * 96,
            f"{'Node ID':<24} {'Name':<30} {'Tier':<14} {'Mesh IP':<16} {'State':<10}",
            "-" * 96,
        ]
        for tier in ["control", "model", "execution", "reserve"]:
            for server in self.servers.values():
                if server.tier != tier:
                    continue
                lines.append(
                    f"{server.node_id:<24} {server.canonical_name:<30} "
                    f"{server.tier_ru:<14} {(server.internal_ip or '—'):<16} {server.lifecycle:<10}"
                )
        lines.extend(["=" * 96, f"Registered servers: {len(self.servers)}"])
        return "\n".join(lines)


def build_fleet_classification(
    records: Iterable[AssetRecord] | None = None,
) -> FleetClassification:
    current = list(records) if records is not None else load_registered_servers()
    servers: dict[str, ServerClassification] = {}
    for record in current:
        tier: ServerTier = (
            record.role if record.role in SERVER_TIER_RU else "execution"
        )  # type: ignore[assignment]
        endpoint = (
            f"http://{record.internal_ip}:{record.api_port}"
            if record.internal_ip and record.api_port
            else None
        )
        servers[record.node_id] = ServerClassification(
            node_id=record.node_id,
            canonical_name=record.canonical_name,
            tier=tier,
            tier_ru=SERVER_TIER_RU[tier],
            internal_ip=record.internal_ip,
            external_ip=record.external_ip,
            ssh_alias=record.ssh_alias,
            lifecycle=record.lifecycle,
            schedulable=record.safe_to_schedule,
            api_port=record.api_port,
            api_endpoint=endpoint,
        )

    mesh_members = sum(
        1 for server in servers.values() if (server.internal_ip or "").startswith("10.99.0.")
    )
    subnets = {
        "wireguard_mesh": SubnetDefinition(
            "wireguard_mesh",
            "10.99.0.0/24",
            "Распределённая WireGuard mesh-сеть",
            "10.99.0.1",
            mesh_members,
        ),
        "lan": SubnetDefinition(
            "lan", "192.168.88.0/24", "Локальная сеть Home", "192.168.88.1", 0
        ),
    }
    return FleetClassification(
        servers=servers,
        subnets=subnets,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


if __name__ == "__main__":
    classification = build_fleet_classification()
    print(classification.summary_table())
    print(json.dumps(classification.to_dict(), indent=2, ensure_ascii=False))
