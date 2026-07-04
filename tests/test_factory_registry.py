#!/usr/bin/env python3
"""Tests for factory_registry.py — physical foundation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops"))

from factory_registry import (
    CANONICAL_SERVERS,
    COMMAND_NODES,
    NETWORK_NODES,
    OPERATOR_ASSETS,
    all_assets,
    canonical_server_count,
    scheduleable_servers,
)


def test_canonical_server_count():
    assert canonical_server_count() == 21


def test_all_assets_count():
    assert len(all_assets()) == 24


def test_mac_is_command_node():
    mac = [n for n in COMMAND_NODES if n.node_id == "mac-owner"]
    assert len(mac) == 1
    assert mac[0].asset_class == "command_node"
    assert mac[0].safe_to_schedule is False


def test_mikrotik_is_network_node():
    router = [n for n in NETWORK_NODES if n.node_id == "mikrotik-router"]
    assert len(router) == 1
    assert router[0].asset_class == "network_node"
    assert router[0].safe_to_schedule is False


def test_usb_kit_is_operator():
    kit = [n for n in OPERATOR_ASSETS if n.node_id == "usb-operator-kit"]
    assert len(kit) == 1
    assert kit[0].asset_class == "operator_kit"
    assert kit[0].safe_to_schedule is False


def test_agent10_quarantined():
    a10 = [s for s in CANONICAL_SERVERS if s.node_id == "agent-10"]
    assert len(a10) == 1
    assert a10[0].lifecycle == "quarantined"
    assert a10[0].safe_to_schedule is False


def test_scheduleable_count():
    assert len(scheduleable_servers()) == 20


def test_no_server_is_command_node():
    for s in CANONICAL_SERVERS:
        assert s.asset_class == "physical_server"


def test_all_servers_have_external_ip():
    for s in CANONICAL_SERVERS:
        assert s.external_ip is not None, f"{s.node_id} missing external_ip"
