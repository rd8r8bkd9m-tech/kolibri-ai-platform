from __future__ import annotations

from pathlib import Path

import pytest

from ops import artifact_scanner
from ops.factory_registry import AssetRecord


def server(node_id: str, mesh_ip: str | None) -> AssetRecord:
    return AssetRecord(
        node_id=node_id,
        canonical_name=node_id,
        asset_class="physical_server",
        internal_ip=mesh_ip,
    )


def test_scanner_discovers_registered_nodes_and_mesh_addresses_dynamically():
    calls = []

    def loader(control_url, *, manifest_path):
        calls.append((control_url, manifest_path))
        return [server("home", "10.99.0.1"), server("worker-22", "10.99.0.22")]

    targets = artifact_scanner.discover_scan_targets(
        control_url="http://home-control:9101",
        manifest_path=Path("/tmp/peers.json"),
        loader=loader,
    )

    assert targets == [("home", "10.99.0.1"), ("worker-22", "10.99.0.22")]
    assert calls == [("http://home-control:9101", Path("/tmp/peers.json"))]


def test_scanner_filters_only_after_dynamic_membership_lookup():
    targets = artifact_scanner.discover_scan_targets(
        server_id="worker-22",
        loader=lambda *_args, **_kwargs: [
            server("home", "10.99.0.1"),
            server("worker-22", "10.99.0.22"),
        ],
    )

    assert targets == [("worker-22", "10.99.0.22")]


def test_scanner_fails_closed_for_unregistered_or_addressless_node():
    with pytest.raises(RuntimeError, match="server_not_registered:missing"):
        artifact_scanner.discover_scan_targets(
            server_id="missing",
            loader=lambda *_args, **_kwargs: [server("home", "10.99.0.1")],
        )

    with pytest.raises(RuntimeError, match="mesh_address_missing_or_invalid:worker-22"):
        artifact_scanner.discover_scan_targets(
            loader=lambda *_args, **_kwargs: [server("worker-22", None)],
        )


def test_scanner_source_has_no_historical_ssh_target_catalog():
    source = (Path(__file__).resolve().parents[1] / "ops" / "artifact_scanner.py").read_text(encoding="utf-8")

    assert "kolibri-main" not in source
    assert "kolibri-primary" not in source
    assert "load_registered_servers" in source
