import importlib.machinery
import importlib.util
from pathlib import Path
from datetime import datetime, timedelta, timezone


ROOT = Path(__file__).resolve().parents[1]


def load_control():
    spec = importlib.util.spec_from_file_location("factory_control", ROOT / "ops" / "factory_control.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_dispatch():
    path = ROOT / "ops" / "kolibri-dispatch"
    loader = importlib.machinery.SourceFileLoader("kolibri_dispatch", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_fabric_catalog_represents_every_server_through_api_or_relay():
    control = load_control()
    nodes = {node["node_id"]: node for node in control.fabric_nodes([])}

    assert {"home", "main", "uiap", "qjns", "9fts", "new"} <= set(nodes)
    for node in nodes.values():
        assert node["management_path"] == "protected_fabric_api"
        assert node["fallback_api_relay"] == "/v1/fabric/relay"
        assert node["ssh"] == "emergency_bootstrap_diagnostic_only"
        assert "fabric_api" in node["api_paths"] or "fallback_relay" in node["api_paths"]


def test_fabric_route_returns_direct_route_when_target_is_online():
    control = load_control()
    now = datetime.now(timezone.utc)
    route = control.fabric_route(
        target_node="9fts",
        registered_nodes=[{"node_id": "9fts", "health": "online", "heartbeat_at": now.isoformat(), "capabilities": ["implementation"]}],
    )

    assert route["status"] == "ok"
    assert route["route"]["type"] == "direct_fabric_api"
    assert route["route"]["target_node"] == "9fts"
    assert route["can_continue_elsewhere"] is True


def test_fabric_route_returns_structured_blocked_status_with_fallback_and_repair_task():
    control = load_control()
    now = datetime.now(timezone.utc)
    route = control.fabric_route(
        target_node="9fts",
        required_capability="implementation",
        registered_nodes=[
            {"node_id": "9fts", "health": "offline", "heartbeat_at": now.isoformat(), "capabilities": ["implementation"]},
            {"node_id": "new", "health": "online", "heartbeat_at": now.isoformat(), "capabilities": ["implementation", "review"]},
        ],
    )

    assert route["status"] == "blocked"
    assert route["reason"] == "target_node_unavailable"
    assert route["target_node"] == "9fts"
    assert route["fallback_nodes"] == ["new"]
    assert route["fallback_route"]["endpoint"] == "/v1/fabric/relay"
    assert route["repair_task"]["kind"] == "repair_fabric_route"
    assert route["can_continue_elsewhere"] is True


def test_fabric_summary_registry_and_drift_use_single_source_of_truth():
    control = load_control()
    nodes = control.fabric_nodes(
        [
            {"node_id": "home-live", "health": "online", "freshness": "fresh", "capabilities": ["home"]},
            {"node_id": "mesh-agent-01", "health": "online", "freshness": "fresh", "capabilities": ["runner:mimo"]},
            {"node_id": "stale-old", "health": "stale", "freshness": "stale"},
        ]
    )
    summary = control.fleet_summary(nodes)
    drift = control.fleet_drift(nodes)

    assert control.validate_registry() == []
    assert summary["logical_workers_total"] == 1
    assert summary["physical_servers_total"] >= 1
    assert "stale-old" in drift["control_plane_records_not_in_registry"]
    assert "frontend_dev" in control.SERVICE_ENDPOINT_REGISTRY
    assert 5173 in control.PORT_REGISTRY


def test_fabric_drift_keeps_registry_only_nodes_missing_until_heartbeat_arrives():
    control = load_control()
    nodes = control.fabric_nodes([])
    drift = control.fleet_drift(nodes)

    assert "agent-10" in drift["registry_nodes_missing_in_control_plane"]
    assert "agent-10" in drift["registry_only_records"]


def test_fabric_nodes_apply_freshness_before_summary_counts():
    control = load_control()
    now = datetime.now(timezone.utc)
    nodes = control.fabric_nodes(
        [
            {
                "node_id": "9fts",
                "health": "online",
                "heartbeat_at": (now - timedelta(seconds=600)).isoformat(),
                "capabilities": ["implementation"],
            }
        ]
    )
    node = next(item for item in nodes if item["node_id"] == "9fts")
    summary = control.fleet_summary(nodes)

    assert node["reported_health"] == "online"
    assert node["freshness"] == "stale"
    assert node["health"] == "stale"
    assert summary["stale_records"] >= 1
    assert summary["stale_records"] == summary["stale_record"]


def test_fabric_nodes_do_not_mutate_canonical_record_when_alias_arrives():
    control = load_control()
    now = datetime.now(timezone.utc).isoformat()
    nodes = control.fabric_nodes(
        [
            {"node_id": "home", "health": "online", "heartbeat_at": now, "capabilities": ["home", "runner:mimo"]},
            {"node_id": "home-live", "health": "online", "heartbeat_at": now, "capabilities": ["home"]},
            {"node_id": "mesh-home", "health": "online", "heartbeat_at": now, "capabilities": ["mesh"]},
        ]
    )
    by_id = {node["node_id"]: node for node in nodes}
    task = control.normalize_task({
        "target_node": "home-live",
        "allowed_nodes": ["home-live", "home"],
        "required_capability": "home",
        "runner": "mimo",
    })

    assert "home" in by_id
    assert "runner:mimo" in by_id["home"]["capabilities"]
    assert control.compatible(task, "home", by_id["home"]["capabilities"], by_id["home"]) is True


def test_owner_policy_requires_auth_scope_logging_and_rotation():
    control = load_control()

    assert {"authentication", "authorization", "scope", "audit_logging", "key_rotation"} <= set(control.OWNER_RIGHTS_POLICY["requires"])
    assert control.NODE_IDENTITY_ROTATION_POLICY["key_rotation"]["required"] is True
    assert control.BOOTSTRAP_CONTRACT["endpoint"] == "POST /v1/fabric/bootstrap"
    assert control.BOOTSTRAP_CONTRACT["safe_stub"] is True


def test_dispatcher_unreachable_control_plane_uses_blocked_envelope():
    dispatch = load_dispatch()
    envelope = dispatch.blocked_envelope("fabric_api_unreachable", "connection refused", "http://control:9101")

    assert envelope["status"] == "blocked"
    assert envelope["reason"] == "fabric_api_unreachable"
    assert envelope["fallback_route"]["endpoint"] == "/v1/fabric/relay"
    assert envelope["repair_task"]["kind"] == "repair_control_plane_api"
    assert envelope["can_continue_elsewhere"] is True
