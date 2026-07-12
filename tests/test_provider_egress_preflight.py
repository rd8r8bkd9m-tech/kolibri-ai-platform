from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ops import provider_egress_preflight as preflight


def completed(command, payload):
    return subprocess.CompletedProcess(
        command,
        0,
        stdout=json.dumps(payload).encode("utf-8"),
        stderr=b"",
    )


def healthy_runner(command, **_kwargs):
    arguments = command[2:]
    if arguments[:3] == ["link", "show", "dev"]:
        return completed(command, [{
            "ifname": "wg-awg-out",
            "flags": ["POINTOPOINT", "UP", "LOWER_UP"],
            "operstate": "UNKNOWN",
        }])
    if arguments == ["rule", "show"]:
        return completed(command, [{"fwmark": "0x66", "table": 1066}])
    if arguments == ["route", "show", "table", "1066"]:
        return completed(command, [{"dst": "default", "dev": "wg-awg-out"}])
    if arguments == ["route", "get", "1.1.1.1", "mark", "0x66"]:
        return completed(command, [{"dst": "1.1.1.1", "dev": "wg-awg-out"}])
    raise AssertionError(command)


def test_preflight_proves_existing_amnezia_policy_without_mutation():
    marks = []
    evidence = preflight.preflight(
        preflight.EgressRouteContract(),
        ip_command=Path("/usr/sbin/ip"),
        runner=healthy_runner,
        kernel_release="6.8.0-home",
        mark_probe=marks.append,
    )

    assert marks == [0x66]
    assert evidence == {
        "schema_version": preflight.SCHEMA_VERSION,
        "status": "ready",
        "authority": "home",
        "lane": "bypass_amnezia",
        "interface": "wg-awg-out",
        "mark": "0x66",
        "table": 1066,
        "default_route_changed": False,
    }


@pytest.mark.parametrize(
    ("field", "payload", "reason"),
    [
        (
            "rules",
            [],
            "provider_egress_policy_rule_missing_or_ambiguous",
        ),
        (
            "routes",
            [{"dst": "default", "dev": "eth0"}],
            "provider_egress_policy_table_invalid",
        ),
        (
            "route_get",
            [{"dst": "1.1.1.1", "dev": "eth0"}],
            "provider_egress_marked_route_mismatch",
        ),
    ],
)
def test_preflight_fails_closed_on_policy_mismatch(field, payload, reason):
    def runner(command, **kwargs):
        arguments = command[2:]
        if field == "rules" and arguments == ["rule", "show"]:
            return completed(command, payload)
        if field == "routes" and arguments == ["route", "show", "table", "1066"]:
            return completed(command, payload)
        if field == "route_get" and arguments[:2] == ["route", "get"]:
            return completed(command, payload)
        return healthy_runner(command, **kwargs)

    with pytest.raises(preflight.ProviderEgressPreflightError, match=reason):
        preflight.preflight(
            preflight.EgressRouteContract(),
            runner=runner,
            kernel_release="6.8.0",
            mark_probe=lambda _mark: None,
        )


def test_cap_net_raw_contract_requires_linux_5_17_or_newer():
    with pytest.raises(
        preflight.ProviderEgressPreflightError,
        match="requires_cap_net_admin",
    ):
        preflight.require_cap_net_raw_kernel("5.15.0")
    preflight.require_cap_net_raw_kernel("5.17.0")
