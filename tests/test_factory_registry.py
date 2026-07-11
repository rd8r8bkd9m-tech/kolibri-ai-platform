#!/usr/bin/env python3
"""Dynamic physical membership and legacy-path retirement contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops"))

from factory_registry import (  # noqa: E402
    COMMAND_NODES,
    NETWORK_NODES,
    OPERATOR_ASSETS,
    all_assets,
    canonical_server_count,
    load_registered_servers,
    records_from_membership,
    scheduleable_servers,
)
from fleet_classification import build_fleet_classification  # noqa: E402
from mimo_client import MimoClient  # noqa: E402


def membership_nodes():
    return [
        {
            "node_id": "home",
            "hostname": "plastilin",
            "health": "online",
            "schedulable": True,
            "capabilities": ["control_plane", "redis"],
        },
        {
            "node_id": "main",
            "hostname": "api-worker",
            "health": "online",
            "schedulable": True,
            "capabilities": ["control_plane", "nginx"],
        },
        {
            "node_id": "new-node-22",
            "hostname": "new-node-22",
            "health": "online",
            "schedulable": True,
            "capabilities": ["build"],
        },
        {
            "node_id": "stale-node",
            "hostname": "stale-node",
            "health": "stale",
            "schedulable": False,
            "capabilities": ["model"],
        },
    ]


def test_membership_is_dynamic_and_only_home_is_control_plane():
    records = records_from_membership(
        membership_nodes(),
        mesh_addresses={
            "home": "10.99.0.1",
            "main": "10.99.0.2",
            "new-node-22": "10.99.0.22",
        },
    )
    by_id = {record.node_id: record for record in records}

    assert set(by_id) == {"home", "main", "new-node-22", "stale-node"}
    assert by_id["home"].role == "control"
    assert by_id["main"].role == "execution"
    assert by_id["new-node-22"].internal_ip == "10.99.0.22"
    assert by_id["stale-node"].safe_to_schedule is False
    assert canonical_server_count(records) == 4
    assert {item.node_id for item in scheduleable_servers(records)} == {
        "home",
        "main",
        "new-node-22",
    }


def test_classification_uses_supplied_live_snapshot_without_static_catalog():
    records = records_from_membership(membership_nodes())
    fleet = build_fleet_classification(records)
    assert fleet.to_dict()["source"] == "home_mesh_manifest_canonical_membership"
    assert fleet.servers["main"].tier == "execution"
    assert fleet.servers["home"].tier == "control"
    assert fleet.servers["new-node-22"].schedulable is True


def test_non_server_assets_do_not_participate_in_scheduling():
    records = records_from_membership(membership_nodes())
    assets = all_assets(records)
    assert len(assets) == len(records) + 3
    assert COMMAND_NODES[0].asset_class == "command_node"
    assert NETWORK_NODES[0].asset_class == "network_node"
    assert OPERATOR_ASSETS[0].asset_class == "operator_kit"
    assert all(not item.safe_to_schedule for item in COMMAND_NODES + NETWORK_NODES + OPERATOR_ASSETS)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_home_membership_loader_paginates_and_accepts_new_nodes(tmp_path):
    manifest = tmp_path / "peers.json"
    manifest.write_text(
        json.dumps(
            {
                "peers": {
                    "10.99.0.1": {"node_id": "home", "mesh_ip": "10.99.0.1"},
                    "10.99.0.22": {"node_id": "new-node-22", "mesh_ip": "10.99.0.22"},
                }
            }
        ),
        encoding="utf-8",
    )
    calls = []

    def opener(url, timeout):
        calls.append((url, timeout))
        return FakeResponse(
            {
                "nodes": membership_nodes(),
                "pagination": {"returned": 4, "total_indexed": 4},
            }
        )

    records = load_registered_servers(manifest_path=manifest, opener=opener)
    assert len(calls) == 1
    assert "scope=active" in calls[0][0]
    assert {record.node_id for record in records} >= {"home", "new-node-22"}


def test_legacy_mimo_client_cannot_select_a_worker():
    client = MimoClient(base_url="https://kolibriai.ru")
    with pytest.raises(ValueError, match="direct_worker_selection_forbidden"):
        client.chat("main", "hello")
    with pytest.raises(ValueError, match="public_model_must_be_kolibri"):
        client.chat("kolibri", "hello", model="provider-model")
    assert client.list_agents()[0]["provider_hidden"] is True


def test_legacy_fleet_api_has_no_ssh_or_scp_deployer():
    source = (ROOT / "ops" / "fleet_api.py").read_text(encoding="utf-8")
    assert "StrictHostKeyChecking" not in source
    assert "scp" not in source
    assert "ssh_exec" not in source
    assert "legacy_fleet_mutation_retired" in source
