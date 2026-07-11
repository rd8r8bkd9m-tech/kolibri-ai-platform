from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_bridge(tmp_path, monkeypatch):
    monkeypatch.setenv("KOLIBRI_MESH_BRIDGE_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("KOLIBRI_MESH_BRIDGE_LOG", str(tmp_path / "bridge.jsonl"))
    spec = importlib.util.spec_from_file_location("mesh_control_bridge", ROOT / "ops" / "mesh_control_bridge.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_create_task_from_mesh_message_builds_control_plane_envelope(tmp_path, monkeypatch):
    bridge = load_bridge(tmp_path, monkeypatch)
    captured = {}

    def fake_post(path, payload):
        captured["path"] = path
        captured["payload"] = payload
        return {"task_id": payload["task_id"], "lease_owner": None}

    monkeypatch.setattr(bridge, "post_control", fake_post)
    monkeypatch.setattr(bridge, "DEFAULT_EXECUTOR", "home-live")

    task_id, created = bridge.create_task_from_message(
        {
            "id": "owner-msg-1",
            "from": "owner",
            "to": "orchestrator",
            "role": "director",
            "task": "Проверь фабрику через mesh",
            "payload": {"priority": "P0", "required_capability": "generic_implementation"},
        }
    )

    assert task_id == "MESH-owner-msg-1"
    assert created["task_id"] == "MESH-owner-msg-1"
    assert captured["path"] == "/v1/tasks"
    assert captured["payload"]["objective"] == "Проверь фабрику через mesh"
    assert captured["payload"]["target_node"] == "home-live"
    assert captured["payload"]["mesh_first"] is True
    assert "result_path" in captured["payload"]["evidence_required"]


def test_chat_only_message_is_ignored_without_creating_task(tmp_path, monkeypatch):
    bridge = load_bridge(tmp_path, monkeypatch)

    def fail_post(*_args, **_kwargs):
        raise AssertionError("chat-only messages must not create control-plane tasks")

    monkeypatch.setattr(bridge, "post_control", fail_post)

    task_id, result = bridge.create_task_from_message(
        {"id": "chat-1", "task": "Привет", "payload": {"kind": "owner_chat_message"}}
    )

    assert task_id is None
    assert result == {"chat_only": True, "status": "ignored"}


def test_sync_mesh_nodes_keeps_observations_local_without_shadow_registration(tmp_path, monkeypatch):
    bridge = load_bridge(tmp_path, monkeypatch)
    posts = []

    def fake_request(method, url, payload=None, timeout=8):
        assert method == "GET"
        assert url.endswith("/api/nodes")
        return [
            {"id": "home", "name": "home", "ip": "10.99.0.1", "role": "agent", "status": "online", "last_seen": "now"},
            {"id": "cold", "name": "cold", "ip": "10.99.0.99", "role": "agent", "status": "offline", "last_seen": "old"},
        ]

    def fake_post(path, payload):
        posts.append((path, payload))
        return payload

    monkeypatch.setattr(bridge, "request_json", fake_request)
    monkeypatch.setattr(bridge, "post_control", fake_post)

    state = {}
    assert bridge.sync_mesh_nodes(state) == 2
    assert state["mesh_nodes"]["home"]["status"] == "online"
    assert state["mesh_nodes"]["cold"]["status"] == "offline"
    assert posts == []


def test_bridge_rejects_multiple_control_plane_authorities_before_network(tmp_path, monkeypatch):
    monkeypatch.setenv("KOLIBRI_FACTORY_CONTROL_URL", "http://home-control:9101")
    monkeypatch.setenv(
        "KOLIBRI_FACTORY_CONTROL_URLS",
        "http://home-control:9101,http://legacy-control:9101",
    )
    bridge = load_bridge(tmp_path, monkeypatch)

    with pytest.raises(RuntimeError, match="multiple_control_plane_authorities_forbidden"):
        bridge.control_url()
