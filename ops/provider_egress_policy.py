#!/usr/bin/env python3
"""Deterministic two-lane provider-egress policy derived from mesh membership.

This module plans routing; it does not mutate routes or start tunnels.  Home's
normal Internet path is the RU lane.  Only approved provider destinations use
the Amnezia-marked BYPASS lane.  Control, mesh, SSH and Telegram stay DIRECT.
"""

from __future__ import annotations

import argparse
import enum
import ipaddress
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    from ops.fleet_membership import MeshMembershipSource, MembershipError
    from ops.marked_connect_proxy import DEFAULT_ALLOWED_SUFFIXES, normalize_host
except ImportError:  # installed standalone beside dependencies
    from fleet_membership import MeshMembershipSource, MembershipError
    from marked_connect_proxy import DEFAULT_ALLOWED_SUFFIXES, normalize_host


SCHEMA_VERSION = "kolibri.provider-egress-policy.v1"
DIRECT_HOSTS = ("api.telegram.org", "kolibriai.ru", "localhost", "home")
BYPASS_RUNNERS = frozenset({"codex", "mimo"})


class ProviderEgressPolicyError(RuntimeError):
    pass


class EgressLane(str, enum.Enum):
    DIRECT = "direct_control"
    RU = "home_ru"
    BYPASS = "home_amnezia"


@dataclass(frozen=True)
class FleetEgressPolicy:
    home_mesh_ip: str
    member_ids: tuple[str, ...]
    member_ips: tuple[str, ...]
    membership_digest: str
    bypass_suffixes: tuple[str, ...] = DEFAULT_ALLOWED_SUFFIXES

    @classmethod
    def from_manifest(cls, path: str | Path) -> "FleetEgressPolicy":
        try:
            snapshot = MeshMembershipSource(path).load()
            home = snapshot.by_id["home"]
        except (MembershipError, KeyError) as exc:
            raise ProviderEgressPolicyError(
                "provider_egress_membership_unavailable"
            ) from exc
        return cls(
            home_mesh_ip=home.mesh_ip,
            member_ids=tuple(member.node_id for member in snapshot.members),
            member_ips=tuple(member.mesh_ip for member in snapshot.members),
            membership_digest=snapshot.digest,
        )

    def no_proxy(self) -> str:
        values = (
            "localhost",
            "127.0.0.1",
            "::1",
            "home",
            "api.telegram.org",
            "kolibriai.ru",
            *self.member_ids,
            *self.member_ips,
        )
        return ",".join(dict.fromkeys(values))

    def classify(self, *, runner: str | None, destination: str | None) -> EgressLane:
        normalized_runner = str(runner or "").strip().lower()
        if destination:
            raw_host = str(destination).strip().rstrip(".").strip("[]")
            try:
                address = ipaddress.ip_address(raw_host)
            except ValueError:
                address = None
            try:
                host = str(address) if address is not None else normalize_host(raw_host)
            except ValueError as exc:
                raise ProviderEgressPolicyError(
                    "provider_egress_destination_invalid"
                ) from exc
            if (
                host in DIRECT_HOSTS
                or host.endswith(".kolibriai.ru")
                or address is not None
                and (address.is_loopback or str(address) in self.member_ips)
            ):
                return EgressLane.DIRECT
            if any(
                host == suffix or host.endswith(f".{suffix}")
                for suffix in self.bypass_suffixes
            ):
                return EgressLane.BYPASS
            return EgressLane.RU
        if normalized_runner in BYPASS_RUNNERS:
            return EgressLane.BYPASS
        return EgressLane.RU

    def rollout_plan(self, canary_nodes: Iterable[str]) -> dict[str, Any]:
        canaries = tuple(dict.fromkeys(
            str(item).strip()
            for item in canary_nodes
            if str(item).strip()
        ))
        if not canaries or any(item not in self.member_ids for item in canaries):
            raise ProviderEgressPolicyError("provider_egress_canary_not_canonical")
        remaining = tuple(
            item
            for item in self.member_ids
            if item not in canaries and item != "home"
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "staged_not_applied",
            "authority": "home",
            "membership_digest": self.membership_digest,
            "canonical_total": len(self.member_ids),
            "home_endpoint_source": "canonical_mesh_manifest",
            "home_mesh_ip": self.home_mesh_ip,
            "lanes": {
                EgressLane.DIRECT.value: {
                    "scope": "control_mesh_ssh_telegram",
                    "proxy": False,
                },
                EgressLane.RU.value: {
                    "scope": "ordinary_public_destinations",
                    "egress_node_id": "home",
                    "default_route_mutation": False,
                    "fleet_transport": "signed_local_forward_pending_canary",
                },
                EgressLane.BYPASS.value: {
                    "scope": "allowlisted_provider_destinations",
                    "egress_node_id": "home",
                    "home_proxy": "http://127.0.0.1:18080",
                    "interface": "wg-awg-out",
                    "fwmark": "0x66",
                    "table": 1066,
                    "fallback": "signed_dynamic_ssh_socks_optional",
                },
            },
            "bypass_runners": sorted(BYPASS_RUNNERS),
            "bypass_suffixes": list(self.bypass_suffixes),
            "no_proxy": self.no_proxy(),
            "rollout": {
                "waves": [
                    {"name": "home_canary", "nodes": ["home"]},
                    {"name": "worker_canary", "nodes": list(canaries)},
                    {"name": "remaining", "nodes": list(remaining)},
                ],
                "gate": "real_provider_response_with_egress_evidence",
            },
            "rollback": {
                "action": "remove_provider_child_binding_and_stop_local_forward",
                "default_route_restore_required": False,
                "control_plane_changed": False,
                "mesh_changed": False,
            },
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--canary", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        plan = FleetEgressPolicy.from_manifest(args.manifest).rollout_plan(args.canary)
    except ProviderEgressPolicyError as exc:
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "reason": str(exc),
        }, sort_keys=True))
        return 2
    print(json.dumps(plan, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
