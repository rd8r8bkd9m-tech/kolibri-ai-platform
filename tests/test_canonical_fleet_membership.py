from __future__ import annotations

import importlib.util
import http.client
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_control(name: str = "factory_control_canonical_membership"):
    spec = importlib.util.spec_from_file_location(name, ROOT / "ops" / "factory_control.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_manifest(path: Path, count: int = 21) -> list[str]:
    node_ids = ["home", *[f"worker-{index:02d}" for index in range(1, count)]]
    peers = {
        f"10.99.0.{index}": {
            "node_id": node_id,
            "mesh_ip": f"10.99.0.{index}",
        }
        for index, node_id in enumerate(node_ids, start=1)
    }
    path.write_text(
        json.dumps({
            "schema_version": 3,
            "cluster_id": "kolibri",
            "epoch": 42,
            "peers": peers,
            # Historical/tombstoned records deliberately do not create active
            # physical membership.
            "records": {
                "retired-worker": {
                    "node_id": "retired-worker",
                    "mesh_ip": "10.99.0.99",
                    "tombstone": True,
                }
            },
        }),
        encoding="utf-8",
    )
    return node_ids


def runtime_node(node_id: str, *, heartbeat_at: str) -> dict:
    return {
        "node_id": node_id,
        "hostname": node_id,
        "health": "online",
        "heartbeat_at": heartbeat_at,
        "capabilities": ["generic_implementation"],
        "draining": False,
    }


def test_active_view_is_exactly_21_manifest_members_and_preserves_legacy_audit(tmp_path):
    manifest = tmp_path / "peers.json"
    canonical_ids = write_manifest(manifest)
    control = load_control("factory_control_canonical_21")
    control.configure_mesh_membership(manifest)
    now = datetime.now(timezone.utc)
    observed = [runtime_node(node_id, heartbeat_at=now.isoformat()) for node_id in canonical_ids[:-1]]
    observed.extend([
        runtime_node("mesh-home-shadow", heartbeat_at=now.isoformat()),
        runtime_node("worker-copy", heartbeat_at=now.isoformat()),
    ])

    view = control.build_canonical_fleet_view(
        audit_nodes=observed,
        current=now.timestamp(),
    )

    assert [node["node_id"] for node in view["active"]] == canonical_ids
    assert len(view["active"]) == 21
    assert {node["node_id"] for node in view["historical"]} == {
        "mesh-home-shadow",
        "worker-copy",
    }
    assert all(node["archived"] is True for node in view["historical"])
    assert all(node["schedulable"] is False for node in view["historical"])
    assert view["membership"]["registered_total"] == 20
    assert view["membership"]["missing_total"] == 1
    assert view["membership"]["historical_total"] == 2

    missing = view["active"][-1]
    assert missing["node_id"] == canonical_ids[-1]
    assert missing["health"] == "quarantined"
    assert missing["freshness"] == "stale"
    assert missing["schedulable"] is False
    assert missing["membership_state"] == "missing_agent_host_registration"


def test_default_nodes_scope_is_canonical_and_audit_is_explicit(tmp_path, monkeypatch):
    manifest = tmp_path / "peers.json"
    canonical_ids = write_manifest(manifest)
    control = load_control("factory_control_membership_scopes")
    control.configure_mesh_membership(manifest)
    now = datetime.now(timezone.utc)
    observed = [runtime_node(node_id, heartbeat_at=now.isoformat()) for node_id in canonical_ids]
    observed.append(runtime_node("legacy-shadow", heartbeat_at=now.isoformat()))
    monkeypatch.setattr(control, "audit_registered_nodes", lambda current=None: list(observed))

    active = control.canonical_nodes_payload()
    audit = control.canonical_nodes_payload("audit")
    combined = control.canonical_nodes_payload("all")

    assert active["scope"] == "active"
    assert active["pagination"]["total_indexed"] == 21
    assert {node["node_id"] for node in active["nodes"]} == set(canonical_ids)
    assert audit["pagination"]["total_indexed"] == 1
    assert audit["nodes"][0]["node_id"] == "legacy-shadow"
    assert audit["nodes"][0]["membership_scope"] == "audit"
    assert combined["pagination"]["total_indexed"] == 22
    with pytest.raises(ValueError, match="node_membership_scope_invalid"):
        control.canonical_nodes_payload("legacy")


def test_manifest_records_do_not_create_membership_and_missing_home_fails_closed(tmp_path):
    manifest = tmp_path / "peers.json"
    manifest.write_text(
        json.dumps({
            "schema_version": 3,
            "peers": {
                "10.99.0.2": {"node_id": "worker-01", "mesh_ip": "10.99.0.2"},
            },
            "records": {
                "home": {"node_id": "home", "mesh_ip": "10.99.0.1", "tombstone": True},
            },
        }),
        encoding="utf-8",
    )
    control = load_control("factory_control_missing_home")
    control.configure_mesh_membership(manifest)

    with pytest.raises(control.MembershipError, match="canonical_home_not_in_mesh_membership"):
        control.build_canonical_fleet_view(audit_nodes=[])


def test_runtime_identity_cannot_self_promote_into_scheduler(tmp_path):
    manifest = tmp_path / "peers.json"
    canonical_ids = write_manifest(manifest)
    control = load_control("factory_control_membership_annotation")
    control.configure_mesh_membership(manifest)

    assert control.node_membership_annotation(canonical_ids[1])["membership_scope"] == "active"
    rejected = control.node_membership_annotation("mesh-worker-01")
    assert rejected["membership_scope"] == "audit"
    assert rejected["archived"] is True
    assert rejected["schedulable"] is False


def test_lease_gate_rejects_a_fresh_redis_shadow_not_in_manifest(tmp_path, monkeypatch):
    manifest = tmp_path / "peers.json"
    write_manifest(manifest)
    control = load_control("factory_control_lease_membership_gate")
    control.configure_mesh_membership(manifest)

    class NoRedisAccess:
        def command(self, *_parts):
            raise AssertionError("noncanonical identity must be rejected before Redis scheduling state")

    monkeypatch.setattr(control, "redis", NoRedisAccess())
    result = control.lease_node_eligibility("legacy-shadow")

    assert result == {
        "eligible": False,
        "reason": "node_not_in_canonical_mesh_membership",
    }


def test_nodes_http_default_is_active_and_audit_requires_explicit_scope(tmp_path, monkeypatch):
    manifest = tmp_path / "peers.json"
    canonical_ids = write_manifest(manifest)
    control = load_control("factory_control_http_membership_scope")
    control.configure_mesh_membership(manifest)
    heartbeat = datetime.now(timezone.utc).isoformat()
    records = {
        node_id: runtime_node(node_id, heartbeat_at=heartbeat)
        for node_id in canonical_ids
    }
    records["legacy-shadow"] = runtime_node("legacy-shadow", heartbeat_at=heartbeat)

    class FakeRedis:
        def command(self, *parts):
            if parts[:2] == ("SMEMBERS", control.key("node_ids")):
                return sorted(records)
            if parts[0] == "MGET":
                values = []
                for redis_key in parts[1:]:
                    marker = f"{control.NAMESPACE}:node:"
                    if str(redis_key).startswith(marker):
                        values.append(json.dumps(records[str(redis_key)[len(marker):]]))
                    else:
                        values.append(None)
                return values
            raise AssertionError(parts)

    monkeypatch.setattr(control, "redis", FakeRedis())
    server = control.ThreadingHTTPServer(("127.0.0.1", 0), control.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address

        def get(path):
            connection = http.client.HTTPConnection(host, port, timeout=2)
            connection.request("GET", path)
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            connection.close()
            return response.status, payload

        status, active = get("/v1/nodes")
        assert status == 200
        assert active["scope"] == "active"
        assert active["pagination"]["total_indexed"] == 21
        assert "legacy-shadow" not in {node["node_id"] for node in active["nodes"]}

        status, audit = get("/v1/nodes?scope=audit")
        assert status == 200
        assert audit["scope"] == "audit"
        assert audit["pagination"]["total_indexed"] == 1
        assert audit["nodes"][0]["node_id"] == "legacy-shadow"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
