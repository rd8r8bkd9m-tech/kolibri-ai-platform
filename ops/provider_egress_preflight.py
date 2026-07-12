#!/usr/bin/env python3
"""Fail-closed preflight for Home's marked provider-egress lane.

The program is deliberately read-only.  It proves that the already-managed
AmneziaWG policy route exists and that this process can apply ``SO_MARK``.  It
never creates links, rules, routes, firewall entries, or a default-route
override.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence


SCHEMA_VERSION = "kolibri.provider-egress-preflight.v1"
SO_MARK = getattr(socket, "SO_MARK", 36)
MINIMUM_CAP_NET_RAW_KERNEL = (5, 17)
MAX_IP_OUTPUT_BYTES = 256 * 1024


class ProviderEgressPreflightError(RuntimeError):
    """Stable, non-secret reason why the bypass lane must stay stopped."""


@dataclass(frozen=True)
class EgressRouteContract:
    interface: str = "wg-awg-out"
    mark: int = 0x66
    table: int = 1066
    route_probe: str = "1.1.1.1"

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", self.interface):
            raise ProviderEgressPreflightError("provider_egress_interface_invalid")
        if not 0 < self.mark <= 0xFFFFFFFF:
            raise ProviderEgressPreflightError("provider_egress_mark_invalid")
        if not 1 <= self.table <= 0xFFFFFFFF:
            raise ProviderEgressPreflightError("provider_egress_table_invalid")
        try:
            socket.inet_pton(socket.AF_INET, self.route_probe)
        except OSError as exc:
            raise ProviderEgressPreflightError(
                "provider_egress_route_probe_invalid"
            ) from exc


def kernel_version(release: str | None = None) -> tuple[int, int]:
    value = release if release is not None else platform.release()
    match = re.match(r"^(\d+)\.(\d+)", value)
    if match is None:
        raise ProviderEgressPreflightError("provider_egress_kernel_version_unknown")
    return int(match.group(1)), int(match.group(2))


def require_cap_net_raw_kernel(release: str | None = None) -> None:
    if kernel_version(release) < MINIMUM_CAP_NET_RAW_KERNEL:
        raise ProviderEgressPreflightError(
            "provider_egress_kernel_requires_cap_net_admin"
        )


def _load_json_output(payload: bytes, reason: str) -> list[dict[str, Any]]:
    if not payload or len(payload) > MAX_IP_OUTPUT_BYTES:
        raise ProviderEgressPreflightError(reason)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProviderEgressPreflightError(reason) from exc
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ProviderEgressPreflightError(reason)
    return value


def run_ip_json(
    arguments: Sequence[str],
    *,
    ip_command: Path = Path("/usr/sbin/ip"),
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> list[dict[str, Any]]:
    command = [str(ip_command), "-j", *arguments]
    try:
        completed = runner(
            command,
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProviderEgressPreflightError("provider_egress_ip_unavailable") from exc
    if completed.returncode != 0:
        raise ProviderEgressPreflightError("provider_egress_ip_query_failed")
    return _load_json_output(
        completed.stdout,
        "provider_egress_ip_output_invalid",
    )


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip(), 0)
        except ValueError:
            return None
    return None


def _rule_mark(value: object) -> int | None:
    if not isinstance(value, str):
        return _integer(value)
    return _integer(value.split("/", 1)[0])


def verify_snapshot(
    contract: EgressRouteContract,
    *,
    links: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    table_routes: list[dict[str, Any]],
    route_result: list[dict[str, Any]],
) -> None:
    link = next(
        (item for item in links if item.get("ifname") == contract.interface),
        None,
    )
    flags = set(link.get("flags") or ()) if isinstance(link, dict) else set()
    if (
        link is None
        or "UP" not in flags
        or str(link.get("operstate") or "").upper() == "DOWN"
    ):
        raise ProviderEgressPreflightError("provider_egress_interface_not_up")

    matching_rules = [
        item
        for item in rules
        if _rule_mark(item.get("fwmark")) == contract.mark
        and _integer(
            item.get("table") if item.get("table") is not None else item.get("lookup")
        ) == contract.table
    ]
    if len(matching_rules) != 1:
        raise ProviderEgressPreflightError(
            "provider_egress_policy_rule_missing_or_ambiguous"
        )

    default_routes = [
        item
        for item in table_routes
        if item.get("dst") == "default"
        and item.get("dev") == contract.interface
    ]
    if len(default_routes) != 1:
        raise ProviderEgressPreflightError("provider_egress_policy_table_invalid")

    if len(route_result) != 1 or route_result[0].get("dev") != contract.interface:
        raise ProviderEgressPreflightError("provider_egress_marked_route_mismatch")


def prove_so_mark(mark: int) -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.setsockopt(socket.SOL_SOCKET, SO_MARK, mark)
    except OSError as exc:
        raise ProviderEgressPreflightError(
            "provider_egress_so_mark_capability_missing"
        ) from exc
    finally:
        probe.close()


def preflight(
    contract: EgressRouteContract,
    *,
    ip_command: Path = Path("/usr/sbin/ip"),
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    kernel_release: str | None = None,
    mark_probe: Callable[[int], None] = prove_so_mark,
) -> dict[str, Any]:
    require_cap_net_raw_kernel(kernel_release)
    links = run_ip_json(
        ["link", "show", "dev", contract.interface],
        ip_command=ip_command,
        runner=runner,
    )
    rules = run_ip_json(["rule", "show"], ip_command=ip_command, runner=runner)
    table_routes = run_ip_json(
        ["route", "show", "table", str(contract.table)],
        ip_command=ip_command,
        runner=runner,
    )
    route_result = run_ip_json(
        [
            "route",
            "get",
            contract.route_probe,
            "mark",
            hex(contract.mark),
        ],
        ip_command=ip_command,
        runner=runner,
    )
    verify_snapshot(
        contract,
        links=links,
        rules=rules,
        table_routes=table_routes,
        route_result=route_result,
    )
    mark_probe(contract.mark)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready",
        "authority": "home",
        "lane": "bypass_amnezia",
        "interface": contract.interface,
        "mark": hex(contract.mark),
        "table": contract.table,
        "default_route_changed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interface", default="wg-awg-out")
    parser.add_argument("--mark", type=lambda value: int(value, 0), default=0x66)
    parser.add_argument("--table", type=int, default=1066)
    parser.add_argument("--route-probe", default="1.1.1.1")
    parser.add_argument("--ip-command", type=Path, default=Path("/usr/sbin/ip"))
    args = parser.parse_args(argv)
    try:
        evidence = preflight(
            EgressRouteContract(
                interface=args.interface,
                mark=args.mark,
                table=args.table,
                route_probe=args.route_probe,
            ),
            ip_command=args.ip_command,
        )
    except ProviderEgressPreflightError as exc:
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "reason": str(exc),
        }, sort_keys=True))
        return 2
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
