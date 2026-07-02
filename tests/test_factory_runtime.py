import importlib.util
from pathlib import Path
from datetime import datetime, timedelta, timezone


ROOT = Path(__file__).resolve().parents[1]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_dispatcher_exposes_required_commands():
    dispatch = (ROOT / "ops" / "kolibri-dispatch").read_text(encoding="utf-8")
    for command in ["doctor", "nodes", "submit", "status", "collect", "cancel", "drain"]:
        assert f'"{command}"' in dispatch


def test_control_plane_states_are_declared():
    control = load_module(ROOT / "ops" / "factory_control.py")
    assert {
        control.STATE_QUEUED,
        control.STATE_LEASED,
        control.STATE_RUNNING,
        control.STATE_WAITING_REVIEW,
        control.STATE_REVIEW,
        control.STATE_COMPLETED,
        control.STATE_FAILED,
        control.STATE_CANCELLED,
        control.STATE_RETRY,
        control.STATE_DEAD,
    } == {
        "queued",
        "leased",
        "running",
        "waiting_review",
        "review",
        "completed",
        "failed",
        "cancelled",
        "retry_scheduled",
        "dead_letter",
    }


def test_control_plane_classifies_stale_online_heartbeat_as_stale():
    control = load_module(ROOT / "ops" / "factory_control.py")
    now = datetime.now(timezone.utc)
    node = control.classify_node_freshness(
        {
            "node_id": "worker-1",
            "health": "online",
            "heartbeat_at": (now - timedelta(seconds=600)).isoformat(),
        },
        now.timestamp(),
    )

    assert node["reported_health"] == "online"
    assert node["freshness"] == "stale"
    assert node["health"] == "stale"
    assert node["heartbeat_age_seconds"] == 600
    assert control.node_health_counts([node]) == {"fresh": 0, "degraded": 0, "stale": 1, "online": 0, "total": 1}


def test_control_plane_counts_fresh_degraded_and_stale_nodes():
    control = load_module(ROOT / "ops" / "factory_control.py")
    now = datetime.now(timezone.utc)
    nodes = [
        control.classify_node_freshness({"node_id": "fresh", "health": "online", "heartbeat_at": (now - timedelta(seconds=5)).isoformat()}, now.timestamp()),
        control.classify_node_freshness({"node_id": "degraded", "health": "online", "heartbeat_at": (now - timedelta(seconds=45)).isoformat()}, now.timestamp()),
        control.classify_node_freshness({"node_id": "stale", "health": "online", "heartbeat_at": (now - timedelta(seconds=120)).isoformat()}, now.timestamp()),
    ]

    assert [node["freshness"] for node in nodes] == ["fresh", "degraded", "stale"]
    assert control.node_health_counts(nodes) == {"fresh": 1, "degraded": 1, "stale": 1, "online": 1, "total": 3}


def test_agent_host_supports_required_task_kinds():
    agent = (ROOT / "ops" / "agent_host.py").read_text(encoding="utf-8")
    assert "impl_factory_smoke" in agent
    assert "impl_retry_error_clearance" in agent
    assert "telegram_chat_response" in agent
    assert "orchestrator_chat_response" in agent
    assert "telegram_image_generation" in agent
    assert "review_pr" in agent
    assert "read_only_probe" in agent
    memory = (ROOT / "ops" / "orchestrator_memory.py").read_text(encoding="utf-8")
    assert "last_work_request" in memory
    assert "open_expectations" in memory



def test_orchestrator_roster_has_human_role_cards():
    roster = load_module(ROOT / "ops" / "orchestrator_roster.py")
    assert roster.ORCHESTRATOR_CARD["name"] == "Директор"
    engineer = roster.node_card({"node_id": "9fts", "health": "online", "capabilities": ["implementation"]})
    reviewer = roster.node_card({"node_id": "new", "health": "online", "capabilities": ["review"]})
    assert engineer["name"] == "Инженер"
    assert reviewer["name"] == "Ревьюер"
    assert engineer["health"] == "online"


def test_control_plane_runner_compatibility_filters_blocked_and_avoided_nodes():
    control = load_module(ROOT / "ops" / "factory_control.py")
    task = control.normalize_task({
        "kind": "owner_remote_task",
        "runner": "mimo",
        "required_capability": "generic_implementation",
        "avoid_nodes": ["avoid-me"],
    })

    assert control.compatible(
        task,
        "healthy",
        ["generic_implementation", "runner:mimo"],
        {"runners": {"mimo": {"status": "available"}}},
    ) is True
    assert control.compatible(
        task,
        "missing-runner-cap",
        ["generic_implementation"],
        {"runners": {"mimo": {"status": "available"}}},
    ) is False
    assert control.compatible(
        task,
        "blocked",
        ["generic_implementation", "runner:mimo"],
        {"runners": {"mimo": {"status": "blocked"}}},
    ) is False
    assert control.compatible(
        task,
        "avoid-me",
        ["generic_implementation", "runner:mimo"],
        {"runners": {"mimo": {"status": "available"}}},
    ) is False


def test_expired_running_task_with_fresh_heartbeat_is_renewed_not_dead_lettered(monkeypatch):
    control = load_module(ROOT / "ops" / "factory_control.py")
    now = datetime.now(timezone.utc)
    task = {
        "task_id": "LONG-RUN-1",
        "state": control.STATE_RUNNING,
        "attempt": 1,
        "max_retries": 1,
        "lease_until": now.timestamp() - 5,
        "heartbeat_at": now.isoformat(),
    }
    saved = []
    dead_letters = []

    monkeypatch.setattr(control, "LEASE_DURATION", 1)
    monkeypatch.setattr(control, "now_ts", lambda: now.timestamp())
    monkeypatch.setattr(control, "all_task_ids", lambda: ["LONG-RUN-1"])
    monkeypatch.setattr(control, "load_task", lambda task_id: task if task_id == "LONG-RUN-1" else None)
    monkeypatch.setattr(control, "save_task", lambda value: saved.append(dict(value)))
    monkeypatch.setattr(control, "enqueue", lambda task_id: None)

    class Redis:
        def command(self, *parts):
            if parts[:2] == ("RPUSH", control.key("dead_letter")):
                dead_letters.append(parts[2])

    monkeypatch.setattr(control, "redis", Redis())

    control.requeue_expired_leases()

    assert saved
    assert saved[-1]["state"] == control.STATE_RUNNING
    assert saved[-1]["lease_until"] > now.timestamp()
    assert saved[-1]["lease_status"] == "leased"
    assert saved[-1]["heartbeat_status"] == "heartbeating"
    assert dead_letters == []


def test_task_status_view_exposes_lease_expired_and_heartbeating_states():
    control = load_module(ROOT / "ops" / "factory_control.py")
    now = datetime.now(timezone.utc)

    running = control.task_status_view(
        {
            "task_id": "RUNNING-1",
            "state": control.STATE_RUNNING,
            "lease_until": now.timestamp() + 30,
            "heartbeat_at": now.isoformat(),
        },
        now.timestamp(),
    )
    expired = control.task_status_view(
        {
            "task_id": "EXPIRED-1",
            "state": control.STATE_RUNNING,
            "lease_until": now.timestamp() - 30,
            "heartbeat_at": (now - timedelta(seconds=control.LEASE_HEARTBEAT_GRACE + 5)).isoformat(),
        },
        now.timestamp(),
    )

    assert running["lease_status"] == "leased"
    assert running["heartbeat_status"] == "heartbeating"
    assert expired["lease_status"] == "lease_expired"
    assert expired["heartbeat_status"] == "heartbeat_stale"
