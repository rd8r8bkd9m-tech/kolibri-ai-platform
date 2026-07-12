from __future__ import annotations

import json

import pytest

from ops.provider_egress_policy import (
    EgressLane,
    FleetEgressPolicy,
    ProviderEgressPolicyError,
)


def membership(tmp_path):
    path = tmp_path / "peers.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "epoch": 9,
        "cluster_id": "test",
        "peers": {
            "home": {"node_id": "home", "mesh_ip": "10.99.0.1"},
            "worker-a": {"node_id": "worker-a", "mesh_ip": "10.99.0.21"},
            "worker-b": {"node_id": "worker-b", "mesh_ip": "10.99.0.22"},
        },
    }), encoding="utf-8")
    return path


def test_two_lane_policy_keeps_control_direct_and_providers_on_amnezia(tmp_path):
    policy = FleetEgressPolicy.from_manifest(membership(tmp_path))

    assert policy.classify(runner="codex", destination=None) is EgressLane.BYPASS
    assert policy.classify(runner="mimo", destination=None) is EgressLane.BYPASS
    assert policy.classify(runner=None, destination="api.openai.com") is EgressLane.BYPASS
    assert policy.classify(runner=None, destination="platform.xiaomimimo.com") is EgressLane.BYPASS
    assert policy.classify(runner=None, destination="api.telegram.org") is EgressLane.DIRECT
    assert policy.classify(runner=None, destination="10.99.0.22") is EgressLane.DIRECT
    assert policy.classify(runner=None, destination="github.com") is EgressLane.RU


def test_rollout_plan_uses_dynamic_membership_and_has_bounded_rollback(tmp_path):
    policy = FleetEgressPolicy.from_manifest(membership(tmp_path))
    plan = policy.rollout_plan(["worker-a"])
    serialized = json.dumps(plan, sort_keys=True)

    assert plan["status"] == "staged_not_applied"
    assert plan["canonical_total"] == 3
    assert plan["home_mesh_ip"] == "10.99.0.1"
    assert plan["lanes"]["home_amnezia"]["fwmark"] == "0x66"
    assert plan["lanes"]["home_amnezia"]["table"] == 1066
    assert plan["lanes"]["home_ru"]["egress_node_id"] == "home"
    assert plan["rollback"]["default_route_restore_required"] is False
    assert plan["rollback"]["control_plane_changed"] is False
    assert "api.telegram.org" in plan["no_proxy"].split(",")
    assert "10.99.0.21" in plan["no_proxy"].split(",")
    assert "178.207.11.90" not in serialized
    assert "kolibri-main" not in serialized
    assert "kolibri-primary" not in serialized


def test_rollout_rejects_noncanonical_canary(tmp_path):
    policy = FleetEgressPolicy.from_manifest(membership(tmp_path))
    with pytest.raises(ProviderEgressPolicyError, match="canary_not_canonical"):
        policy.rollout_plan(["unknown-node"])
