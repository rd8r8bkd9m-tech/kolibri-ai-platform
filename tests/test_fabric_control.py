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

    for health in ["fresh", "online", "ok", "running"]:
        route = control.fabric_route(
            target_node="9fts",
            registered_nodes=[{"node_id": "9fts", "health": health, "capabilities": ["implementation"]}],
        )

        assert route["status"] == "ok"
        assert route["route"]["type"] == "direct_fabric_api"
        assert route["route"]["target_node"] == "9fts"
        assert route["can_continue_elsewhere"] is True


def test_fabric_route_blocks_stale_degraded_offline_and_drained_targets():
    control = load_control()

    for health in ["stale", "degraded", "offline", "drained"]:
        route = control.fabric_route(
            target_node="9fts",
            required_capability="implementation",
            registered_nodes=[
                {"node_id": "9fts", "health": health, "capabilities": ["implementation"]},
                {"node_id": "new", "health": "ok", "capabilities": ["implementation", "review"]},
            ],
        )

        assert route["status"] == "blocked"
        assert route["reason"] == "target_node_unavailable"
        assert route["fallback_nodes"] == ["new"]

    route = control.fabric_route(
        target_node="9fts",
        required_capability="implementation",
        registered_nodes=[
            {"node_id": "9fts", "health": "online", "draining": True, "capabilities": ["implementation"]},
            {"node_id": "new", "health": "running", "capabilities": ["implementation", "review"]},
        ],
    )

    assert route["status"] == "blocked"
    assert route["reason"] == "target_node_unavailable"
    assert route["fallback_nodes"] == ["new"]


def test_fabric_route_blocks_missing_capability_even_when_health_is_routable():
    control = load_control()
    route = control.fabric_route(
        target_node="9fts",
        required_capability="review",
        registered_nodes=[{"node_id": "9fts", "health": "running", "capabilities": ["implementation"]}],
    )

    assert route["status"] == "blocked"
    assert route["reason"] == "target_node_unavailable"
    assert route["fallback_nodes"] == []


def test_fabric_route_target_node_uses_authoritative_record_outside_fallback_sample():
    control = load_control()
    sampled_nodes = [
        {"node_id": f"sample-{index:02d}", "health": "online", "capabilities": ["runner:mimo"]}
        for index in range(40)
    ]

    without_authoritative_target = control.fabric_route(
        target_node="new",
        required_capability="runner:mimo",
        registered_nodes=sampled_nodes,
        fallback_limit=26,
    )
    route = control.fabric_route(
        target_node="new",
        required_capability="runner:mimo",
        registered_nodes=sampled_nodes,
        target_node_record={
            "node_id": "new",
            "health": "online",
            "active_task": None,
            "capabilities": ["runner:mimo"],
        },
        fallback_limit=26,
    )

    assert without_authoritative_target["status"] == "blocked"
    assert without_authoritative_target["reason"] == "target_node_unavailable"
    assert len(without_authoritative_target["fallback_nodes"]) == 26
    assert route["status"] == "ok"
    assert route["route"]["target_node"] == "new"
    assert route["route"]["endpoint"] == "/v1/nodes/new"
    assert len(route["fallback_nodes"]) == 26
    assert "new" not in route["fallback_nodes"]


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
