import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_registry():
    spec = importlib.util.spec_from_file_location("factory_registry", ROOT / "ops" / "factory_registry.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_registry_validates_without_internal_errors():
    registry = load_registry()

    assert registry.validate_registry() == []
    assert registry.SOURCE_OF_TRUTH_VERSION == "2026-07-03-p0"
    assert 9101 in registry.PORT_REGISTRY
    assert {"control_plane", "mesh_bridge"} <= set(registry.PORT_REGISTRY[9101]["services"])


def test_node_aliases_are_canonical_without_agent_alias_drift():
    registry = load_registry()

    assert registry.canonical_node_id("home-live") == "home"
    assert registry.canonical_node_id("mesh-home") == "home"
    assert registry.canonical_node_id("primary") == "primary-candidate"
    assert registry.canonical_node_id("mesh-primary") == "primary-candidate"
    assert registry.canonical_node_id("mesh-agent-01") == "mesh-agent-01"
    assert registry.target_node_matches("home-live", "mesh-home") is True
    assert registry.target_node_matches("mesh-agent-01", "agent-01") is False


def test_capability_aliases_are_explicit_and_bounded():
    registry = load_registry()

    assert registry.capability_satisfied("devops", ["permission:*"]) is True
    assert registry.capability_satisfied("github_review", ["generic_review"]) is True
    assert registry.capability_satisfied("runner:codex", ["runner_codex"]) is True
    assert registry.capability_satisfied("review", ["runner:codex"]) is False


def test_fabric_node_catalog_exposes_full_canonical_server_inventory():
    registry = load_registry()
    catalog = registry.fabric_node_catalog()

    assert set(catalog) == set(registry.CANONICAL_NODE_REGISTRY)
    assert "agent-10" in catalog
    assert catalog["agent-10"]["external_ips"] == ["217.60.38.191"]
    assert catalog["agent-10"]["internal_ips"] == ["10.99.0.18"]
    assert catalog["agent-10"]["safe_to_schedule"] is False
    assert catalog["agent-10"]["source"] == "registry_catalog"
    assert catalog["agent-10"]["lifecycle"] == "active"
    assert catalog["agent-10"]["network_status_override"] is None
    assert catalog["agent-10"]["ssh_access"]["mode"] == "internal_via_main"
    assert catalog["agent-10"]["ssh_access"]["target"] == "10.99.0.18"
    assert catalog["home"]["ssh_access"]["identity"] == "kolibri_ai_platform_deploy_ed25519"
    assert catalog["qjns"]["ssh_access"]["mode"] == "internal_via_home"
    assert catalog["uiap"]["ssh_access"]["mode"] == "internal_via_main"


def test_fleet_summary_separates_physical_logical_and_stale_records():
    registry = load_registry()
    summary = registry.fleet_summary(
        [
            {"node_id": "home", "health": "online", "freshness": "fresh"},
            {"node_id": "mesh-home", "health": "online", "freshness": "fresh"},
            {"node_id": "mesh-agent-01", "health": "online", "freshness": "fresh"},
            {"node_id": "old-node", "health": "stale", "freshness": "stale"},
        ]
    )

    assert summary["physical_servers_total"] == 1
    assert summary["logical_workers_total"] == 1
    assert summary["aliases_total"] == 1
    assert summary["stale_records"] >= 1


def test_fleet_drift_marks_unknown_and_stale_reported_online_records():
    registry = load_registry()
    drift = registry.fleet_drift(
        [
            {"node_id": "home", "health": "online", "freshness": "fresh"},
            {"node_id": "unknown-node", "health": "online", "freshness": "fresh"},
            {"node_id": "mesh-home", "health": "online", "freshness": "fresh"},
            {"node_id": "old", "reported_health": "online", "health": "stale", "freshness": "stale"},
        ]
    )

    assert "unknown-node" in drift["control_plane_records_not_in_registry"]
    assert "old" in drift["stale_reported_online"]
    assert drift["duplicate_canonical_records"]["home"] == ["home", "mesh-home"]


def test_fleet_drift_does_not_count_registry_only_records_as_control_plane_present():
    registry = load_registry()
    catalog = registry.fabric_node_catalog()
    drift = registry.fleet_drift(list(catalog.values()))

    assert "agent-10" in drift["registry_nodes_missing_in_control_plane"]
    assert "agent-10" in drift["registry_only_records"]
