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


def test_owner_server_repair_plan_covers_canonical_20_and_creates_repair_envelopes():
    control = load_control()
    plan = control.owner_server_repair_plan(
        [
            {"node_id": "main", "health": "online", "capabilities": ["devops", "runner:codex"]},
            {"node_id": "mesh-agent-01", "health": "online", "capabilities": ["devops", "runner:codex"]},
            {"node_id": "uiap", "health": "online", "disk": {"free_gb": 0}, "capabilities": ["read_only_probe"]},
        ],
        task_id_prefix="P0_TEST_REPAIR",
    )

    assert plan["summary"]["canonical_servers"] == 20
    assert len(plan["matrix"]) == 20
    uiap = next(item for item in plan["matrix"] if item["node_id"] == "uiap")
    assert uiap["status"] == "blocked"
    assert "disk_full" in uiap["reasons"]
    assert uiap["repair_task_id"] == "P0_TEST_REPAIR-UIAP"
    assert uiap["exact_repair_command"].endswith("/repair-envelopes/uiap.json")
    assert any(task["target_node"] == "uiap" for task in plan["repair_tasks"])


def test_owner_server_repair_plan_treats_fresh_alias_as_repair_pending_identity_gap():
    control = load_control()
    plan = control.owner_server_repair_plan(
        [
            {"node_id": "main", "health": "online", "capabilities": ["devops", "runner:codex"]},
            {"node_id": "mesh-agent-01", "health": "online", "capabilities": ["devops", "runner:codex"]},
        ],
        task_id_prefix="P0_TEST_REPAIR",
    )

    agent = next(item for item in plan["matrix"] if item["node_id"] == "agent-01")
    assert agent["observed_node"] == "mesh-agent-01"
    assert agent["status"] == "repair_pending"
    assert "canonical_identity_alias_only" in agent["reasons"]
