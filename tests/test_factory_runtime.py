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


def test_dead_letter_rerun_requeues_task():
    control = load_module(ROOT / "ops" / "factory_control.py")
    task = control.normalize_task({
        "task_id": "DEAD-RERUN-1",
        "idempotency_key": "dead-rerun-1",
        "kind": "read_only_probe",
    })
    task["state"] = control.STATE_DEAD
    task["error_type"] = "lease_expired"
    task["error"] = "lease expired and retry budget exhausted"
    task["attempt"] = 3
    task["attempt_id"] = "DEAD-RERUN-1-attempt-3"
    task["lease_owner"] = "home:agent-host-home"
    task["lease_until"] = 9999999999.0
    control.save_task(task)
    control.redis.command("RPUSH", control.key("dead_letter"), "DEAD-RERUN-1")

    result = control.rerun_dead_letter_task("DEAD-RERUN-1")
    assert result is not None
    assert result["state"] == control.STATE_QUEUED
    assert result["attempt"] == 0
    assert result["attempt_id"] is None
    assert result["lease_owner"] is None
    assert result["lease_until"] is None
    assert result["error_type"] is None
    assert result["error"] is None
    assert "DEAD-RERUN-1" not in control.dead_letter_ids()


def test_dead_letter_rerun_returns_none_for_missing_task():
    control = load_module(ROOT / "ops" / "factory_control.py")
    assert control.rerun_dead_letter_task("NONEXISTENT") is None


def test_dead_letter_rerun_returns_none_for_non_dead_task():
    control = load_module(ROOT / "ops" / "factory_control.py")
    task = control.normalize_task({
        "task_id": "ALIVE-1",
        "idempotency_key": "alive-1",
        "kind": "read_only_probe",
    })
    task["state"] = control.STATE_QUEUED
    control.save_task(task)
    assert control.rerun_dead_letter_task("ALIVE-1") is None


def test_dead_letter_ids_lists_dead_tasks():
    control = load_module(ROOT / "ops" / "factory_control.py")
    for tid in ["DL-1", "DL-2"]:
        task = control.normalize_task({"task_id": tid, "idempotency_key": tid, "kind": "read_only_probe"})
        task["state"] = control.STATE_DEAD
        control.save_task(task)
        control.redis.command("RPUSH", control.key("dead_letter"), tid)
    ids = control.dead_letter_ids()
    assert "DL-1" in ids
    assert "DL-2" in ids


def test_factory_control_source_has_dead_letter_rerun_endpoint():
    source = (ROOT / "ops" / "factory_control.py").read_text(encoding="utf-8")
    assert "/v1/tasks/dead-letter" in source
    assert "/rerun" in source
    assert "rerun_dead_letter_task" in source
    assert "dead_letter_ids" in source
