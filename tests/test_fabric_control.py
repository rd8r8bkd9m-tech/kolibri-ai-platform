import importlib.machinery
import importlib.util
from pathlib import Path


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
    route = control.fabric_route(
        target_node="9fts",
        registered_nodes=[{"node_id": "9fts", "health": "online", "capabilities": ["implementation"]}],
    )

    assert route["status"] == "ok"
    assert route["route"]["type"] == "direct_fabric_api"
    assert route["route"]["target_node"] == "9fts"
    assert route["can_continue_elsewhere"] is True


def test_fabric_route_returns_structured_blocked_status_with_fallback_and_repair_task():
    control = load_control()
    route = control.fabric_route(
        target_node="9fts",
        required_capability="implementation",
        registered_nodes=[
            {"node_id": "9fts", "health": "offline", "capabilities": ["implementation"]},
            {"node_id": "new", "health": "online", "capabilities": ["implementation", "review"]},
        ],
    )

    assert route["status"] == "blocked"
    assert route["reason"] == "target_node_unavailable"
    assert route["target_node"] == "9fts"
    assert route["fallback_nodes"] == ["new"]
    assert route["fallback_route"]["endpoint"] == "/v1/fabric/relay"
    assert route["repair_task"]["kind"] == "repair_fabric_route"
    assert route["can_continue_elsewhere"] is True


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


def test_fleet_summary_returns_bounded_node_and_task_data():
    control = load_control()
    registered = [
        {"node_id": "9fts", "health": "online", "heartbeat_at": control.utc_now(), "capabilities": ["implementation"]},
        {"node_id": "new", "health": "online", "heartbeat_at": control.utc_now(), "capabilities": ["review"]},
    ]
    summary = control.fleet_summary(registered)

    assert "nodes" in summary
    assert "counts" in summary
    assert "task_counts" in summary
    assert "queue_length" in summary
    assert "active_tasks" in summary
    assert "generated_at" in summary
    assert summary["counts"]["total"] >= 6
    assert summary["counts"]["online"] >= 2
    assert isinstance(summary["task_counts"], dict)
    assert isinstance(summary["queue_length"], int)
    assert isinstance(summary["active_tasks"], list)


def test_fleet_summary_node_has_required_fields():
    control = load_control()
    summary = control.fleet_summary([{"node_id": "9fts", "health": "online", "heartbeat_at": control.utc_now()}])
    node_9fts = next((n for n in summary["nodes"] if n["node_id"] == "9fts"), None)
    assert node_9fts is not None
    assert "health" in node_9fts
    assert "freshness" in node_9fts
    assert "draining" in node_9fts
    assert "capabilities" in node_9fts
    assert "runners" in node_9fts


def test_fleet_incidents_detects_stale_node():
    control = load_control()
    stale_time = control.utc_now().replace("T", "T00:00:00")
    registered = [
        {"node_id": "9fts", "health": "online", "heartbeat_at": stale_time, "capabilities": ["implementation"]},
    ]
    incidents = control.fleet_incidents(registered)
    stale_incidents = [i for i in incidents if i["kind"] == "node_stale" and i["node_id"] == "9fts"]
    assert len(stale_incidents) >= 1
    assert stale_incidents[0]["severity"] == "high"


def test_fleet_incidents_returns_list():
    control = load_control()
    incidents = control.fleet_incidents([])
    assert isinstance(incidents, list)


def test_prompt3_required_endpoints_include_fleet_summary_and_incidents():
    control = load_control()
    assert "/v1/fleet/summary" in control.PROMPT3_REQUIRED_ENDPOINTS["GET"]
    assert "/v1/fleet/incidents" in control.PROMPT3_REQUIRED_ENDPOINTS["GET"]
