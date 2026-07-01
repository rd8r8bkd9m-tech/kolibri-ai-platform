import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_control():
    spec = importlib.util.spec_from_file_location("factory_control", ROOT / "ops" / "factory_control.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_node_capacity_caps_xlarge_nodes_at_twenty_logical_agents():
    control = load_control()
    capacity = control.node_capacity(
        {
            "node_id": "big",
            "health": "online",
            "cpu": 32,
            "ram": {"MemAvailable": "67108864 kB"},
            "disk": {"free": 100 * 1024**3},
        },
        per_server_limit=20,
    )
    assert capacity["capacity_class"] == "xlarge"
    assert capacity["logical_agent_capacity"] == 20
    assert capacity["blockers"] == []


def test_logical_scheduler_creates_bounded_remote_child_tasks(monkeypatch):
    control = load_control()
    created = []

    monkeypatch.setattr(
        control,
        "load_nodes",
        lambda: [
            {
                "node_id": "n1",
                "health": "online",
                "cpu": 16,
                "ram": {"MemAvailable": "33554432 kB"},
                "disk": {"free": 60 * 1024**3},
            }
        ],
    )
    monkeypatch.setattr(control, "set_json", lambda redis_key, value: None)
    monkeypatch.setattr(control, "logical_schedule_task_count", lambda schedule_id, node_id=None: 0)

    def fake_create_task(envelope):
        created.append(envelope)
        return {"task_id": envelope["task_id"], "state": control.STATE_QUEUED, "envelope": envelope}

    monkeypatch.setattr(control, "create_task", fake_create_task)
    result = control.create_logical_scheduler_wave(
        {"target": 1000, "per_server_limit": 20, "wave_limit": 2, "schedule_id": "test-wave"}
    )

    assert result["status"] == "started"
    assert result["target"] == 1000
    assert result["per_server_limit"] == 20
    assert len(result["created_task_ids"]) == 2
    assert all(item["kind"] == "read_only_probe" for item in created)
    assert all(item["target_node"] == "n1" for item in created)
    assert all(item["scheduler_action"] == "logical_agent_slot_probe" for item in created)


def test_logical_scheduler_classifies_fresh_node_with_probe_task(monkeypatch):
    control = load_control()
    created = []

    monkeypatch.setattr(
        control,
        "load_nodes",
        lambda: [{"node_id": "fresh", "health": "online", "cpu": None, "ram": {}, "disk": {}}],
    )
    monkeypatch.setattr(control, "set_json", lambda redis_key, value: None)
    monkeypatch.setattr(control, "logical_schedule_task_count", lambda schedule_id, node_id=None: 0)

    def fake_create_task(envelope):
        created.append(envelope)
        return {"task_id": envelope["task_id"], "state": control.STATE_QUEUED, "envelope": envelope}

    monkeypatch.setattr(control, "create_task", fake_create_task)
    result = control.create_logical_scheduler_wave(
        {"target": 1000, "per_server_limit": 20, "wave_limit": 5, "schedule_id": "fresh-wave"}
    )

    assert result["status"] == "blocked"
    assert result["created_task_ids"] == ["CAPACITY-PROBE-fresh-wave-fresh"]
    assert created[0]["scheduler_action"] == "capacity_classification_probe"
    assert result["blockers"][0]["node_id"] == "fresh"
