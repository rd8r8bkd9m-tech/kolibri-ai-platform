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


def test_autorepair_classifies_stale_disk_and_auth_failures():
    control = load_module(ROOT / "ops" / "factory_control.py")
    now = datetime.now(timezone.utc)
    stale = control.classify_node_freshness(
        {
            "node_id": "stale-worker",
            "health": "online",
            "heartbeat_at": (now - timedelta(seconds=600)).isoformat(),
        },
        now.timestamp(),
    )
    disk_full = control.classify_node_freshness(
        {
            "node_id": "disk-worker",
            "health": "online",
            "heartbeat_at": now.isoformat(),
            "disk": {"free": 1024, "total": 100 * 1024 * 1024 * 1024},
        },
        now.timestamp(),
    )
    auth_down = control.classify_node_freshness(
        {
            "node_id": "auth-worker",
            "health": "online",
            "heartbeat_at": now.isoformat(),
            "runners": {"mimo": {"status": "blocked", "error_type": "runner_auth_blocked"}},
        },
        now.timestamp(),
    )

    assert control.node_repair_reasons(stale) == ["node_stale"]
    assert control.node_repair_reasons(disk_full) == ["disk_full"]
    assert control.node_repair_reasons(auth_down) == ["auth_failed"]


def test_autorepair_enqueues_scoped_idempotent_task_with_fallback(monkeypatch):
    control = load_module(ROOT / "ops" / "factory_control.py")
    now = datetime.now(timezone.utc)
    broken = control.classify_node_freshness(
        {
            "node_id": "qjns",
            "health": "online",
            "heartbeat_at": (now - timedelta(seconds=600)).isoformat(),
            "capabilities": ["review"],
        },
        now.timestamp(),
    )
    healthy = control.classify_node_freshness(
        {
            "node_id": "primary-candidate",
            "health": "online",
            "heartbeat_at": now.isoformat(),
            "capabilities": ["generic_implementation", "implementation"],
        },
        now.timestamp(),
    )
    created = []

    def fake_create_task(envelope):
        created.append(envelope)
        task = control.normalize_task(envelope)
        task["state"] = control.STATE_QUEUED
        return task

    monkeypatch.setattr(control, "create_task", fake_create_task)
    repair_tasks = control.ensure_autorepair_tasks_for_nodes([broken, healthy])

    assert len(repair_tasks) == 1
    assert repair_tasks[0]["target_repair_node"] == "qjns"
    assert repair_tasks[0]["repair_reason"] == "node_stale"
    assert repair_tasks[0]["fallback_nodes"] == ["primary-candidate"]
    assert created[0]["kind"] == "owner_remote_task"
    assert created[0]["idempotency_key"] == "autorepair:qjns:node_stale"
    assert created[0]["allowed_nodes"] == ["primary-candidate"]
    assert created[0]["avoid_nodes"] == ["qjns"]
    assert created[0]["fallback_route"]["endpoint"] == "/v1/fabric/relay"
    assert created[0]["constraints"]["no_secrets"] is True


def test_fabric_route_blocks_stale_target_and_returns_fallback_repair():
    control = load_module(ROOT / "ops" / "factory_control.py")
    now = datetime.now(timezone.utc)
    route = control.fabric_route(
        target_node="qjns",
        required_capability="review",
        registered_nodes=[
            {
                "node_id": "qjns",
                "health": "online",
                "heartbeat_at": (now - timedelta(seconds=600)).isoformat(),
                "capabilities": ["review"],
            },
            {
                "node_id": "new",
                "health": "online",
                "heartbeat_at": now.isoformat(),
                "capabilities": ["review", "generic_implementation"],
            },
        ],
    )

    assert route["status"] == "blocked"
    assert route["reason"] == "target_node_unavailable"
    assert route["fallback_nodes"] == ["new"]
    assert route["repair_task"]["kind"] == "owner_remote_task"
    assert route["repair_task"]["target_repair_node"] == "qjns"
    assert route["repair_task"]["allowed_nodes"] == ["new"]
