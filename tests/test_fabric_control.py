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
    assert envelope["target_control_url"] == "http://control:9101"
    assert envelope["fallback_route"]["endpoint"] == "/v1/fabric/relay"
    assert envelope["repair_task"]["kind"] == "repair_control_plane_api"
    assert envelope["can_continue_elsewhere"] is True


def test_dispatcher_control_request_fails_over_to_next_control_url(monkeypatch):
    dispatch = load_dispatch()
    calls = []

    def fake_http_json(method, url, body=None, ok_empty=False):
        del ok_empty
        calls.append((method, url, body))
        if url.startswith("http://down"):
            raise dispatch.FabricApiUnavailable(
                dispatch.blocked_envelope("fabric_api_unreachable", "down", "http://down:9101")
            )
        return {"status": "ok", "url": url}

    monkeypatch.setattr(dispatch, "http_json", fake_http_json)
    args = type("Args", (), {
        "control_url": "http://down:9101",
        "control_urls": "http://down:9101,http://alive:9101",
    })()

    result = dispatch.control_request(args, "GET", "/v1/nodes")

    assert result == {"status": "ok", "url": "http://alive:9101/v1/nodes"}
    assert calls == [
        ("GET", "http://down:9101/v1/nodes", None),
        ("GET", "http://alive:9101/v1/nodes", None),
    ]
    assert args.control_url == "http://alive:9101"


def test_dispatcher_control_request_reports_all_failed_control_urls(monkeypatch):
    dispatch = load_dispatch()

    def fake_http_json(method, url, body=None, ok_empty=False):
        del method, body, ok_empty
        base = url.split("/v1/", 1)[0]
        raise dispatch.FabricApiUnavailable(
            dispatch.blocked_envelope("fabric_api_unreachable", "down", base)
        )

    monkeypatch.setattr(dispatch, "http_json", fake_http_json)
    args = type("Args", (), {
        "control_url": "http://down-a:9101",
        "control_urls": "http://down-a:9101,http://down-b:9101",
    })()

    try:
        dispatch.control_request(args, "GET", "/v1/nodes")
    except dispatch.FabricApiUnavailable as exc:
        envelope = exc.envelope
    else:
        raise AssertionError("all failed control URLs should raise FabricApiUnavailable")

    assert envelope["status"] == "blocked"
    assert envelope["attempted_control_urls"] == ["http://down-a:9101", "http://down-b:9101"]
    assert [attempt["target_control_url"] for attempt in envelope["attempts"]] == [
        "http://down-a:9101",
        "http://down-b:9101",
    ]
