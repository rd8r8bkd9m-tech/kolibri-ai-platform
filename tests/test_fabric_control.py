import importlib.machinery
import importlib.util
import json
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


def test_fabric_membership_is_registration_driven_and_home_is_only_control_plane():
    control = load_control()
    assert control.fabric_nodes([]) == []
    registered = [
        {"node_id": "home", "hostname": "plastilin", "health": "online"},
        {"node_id": "main", "hostname": "main", "health": "online", "role": "control_plane"},
        {"node_id": "dynamic-worker", "health": "online", "capabilities": ["implementation"]},
    ]
    nodes = {node["node_id"]: node for node in control.fabric_nodes(registered)}

    assert set(nodes) == {"home", "main", "dynamic-worker"}
    assert nodes["home"]["role"] == "control_plane"
    assert "control_plane_api" in nodes["home"]["api_paths"]
    assert nodes["main"]["role"] == "worker"
    assert nodes["main"]["authority_rejected"] is True
    assert "control_plane_api" not in nodes["main"]["api_paths"]
    for node in nodes.values():
        assert node["management_path"] == "protected_fabric_api"
        assert node["fallback_api_relay"] == "/v1/fabric/relay"
        assert node["ssh"] == "emergency_bootstrap_diagnostic_only"
        assert "fabric_api" in node["api_paths"] or "fallback_relay" in node["api_paths"]


def test_fabric_topology_has_home_as_the_only_authoritative_source():
    control = load_control()
    topology = control.fleet_topology(control.fabric_nodes([
        {"node_id": "home", "health": "online"},
        {"node_id": "main", "health": "online"},
        {"node_id": "new-worker", "health": "online"},
    ]))

    assert topology["nodes"]
    assert topology["edges"]
    assert all(edge["from"] == "home" for edge in topology["edges"])
    assert all(edge["to"] != "home" for edge in topology["edges"])
    assert any(edge["to"] == "main" for edge in topology["edges"])


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
    assert envelope["fallback_nodes"] == []
    assert envelope["fallback_route"] is None
    assert envelope["repair_task"]["kind"] == "repair_control_plane_api"
    assert envelope["can_continue_elsewhere"] is False


def test_dispatcher_rejects_multiple_control_plane_authorities_before_network(monkeypatch, capsys):
    dispatch = load_dispatch()
    monkeypatch.setenv("KOLIBRI_FACTORY_CONTROL_URL", "http://home-control:9101")
    monkeypatch.setenv(
        "KOLIBRI_FACTORY_CONTROL_URLS",
        "http://home-control:9101,http://legacy-control:9101",
    )

    def fail_urlopen(*_args, **_kwargs):
        raise AssertionError("network must not be called")

    monkeypatch.setattr(dispatch.urllib.request, "urlopen", fail_urlopen)

    assert dispatch.main(["nodes"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "canonical_home_control_plane_unresolved"
    assert "multiple_control_plane_authorities_forbidden" in payload["detail"]
