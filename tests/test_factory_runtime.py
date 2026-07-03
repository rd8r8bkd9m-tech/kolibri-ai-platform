import importlib.util
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone


ROOT = Path(__file__).resolve().parents[1]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeRedis:
    def __init__(self, values=None, sets=None, lists=None, zsets=None):
        self.values = values or {}
        self.sets = sets or {}
        self.lists = lists or {}
        self.zsets = zsets or {}

    def command(self, command, *parts):
        command = command.upper()
        if command == "GET":
            return self.values.get(parts[0])
        if command == "SMEMBERS":
            return sorted(self.sets.get(parts[0], set()))
        if command == "SADD":
            self.sets.setdefault(parts[0], set()).update(str(part) for part in parts[1:])
            return len(parts) - 1
        if command == "LRANGE":
            return list(self.lists.get(parts[0], []))
        if command == "ZRANGE":
            return list(self.zsets.get(parts[0], []))
        if command == "TYPE":
            redis_key = parts[0]
            if redis_key in self.sets:
                return "set"
            if redis_key in self.lists:
                return "list"
            if redis_key in self.zsets:
                return "zset"
            if redis_key in self.values:
                return "string"
            return "none"
        if command == "SCAN":
            cursor = str(parts[0])
            assert cursor == "0"
            pattern = parts[2]
            prefix = pattern[:-1]
            return ["0", sorted(key for key in self.values if key.startswith(prefix))]
        raise AssertionError(f"unexpected redis command: {command} {parts}")


def task_json(control, task_id, **overrides):
    task = {
        "task_id": task_id,
        "kind": "owner_remote_task",
        "state": control.STATE_RUNNING,
        "attempt": 1,
        "lease_owner": "main:agent-host-main",
        "lease_until": 1000.0,
        "heartbeat_at": datetime.fromtimestamp(990, timezone.utc).isoformat(),
        "updated_at": datetime.fromtimestamp(990, timezone.utc).isoformat(),
        "envelope": {"objective": "repair Agent Host"},
    }
    task.update(overrides)
    return json.dumps(task)


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


def test_task_list_reconciles_authoritative_records_when_active_index_is_stale(monkeypatch):
    control = load_module(ROOT / "ops" / "factory_control.py")
    task_ids_key = control.key("task_ids")
    queue_key = control.key("queue")
    active_index_key = control.key("queue_active_index")
    redis = FakeRedis(
        values={
            control.task_key("RUN-INDEXED"): task_json(control, "RUN-INDEXED"),
            control.task_key("RUN-MISSING-FROM-INDEX"): task_json(
                control,
                "RUN-MISSING-FROM-INDEX",
                lease_owner="primary-candidate:agent-host-primary",
            ),
            control.task_key("RUN-EXPIRED"): task_json(
                control,
                "RUN-EXPIRED",
                lease_until=900.0,
                heartbeat_at=datetime.fromtimestamp(900, timezone.utc).isoformat(),
            ),
            control.task_key("DONE-FRESH"): task_json(
                control,
                "DONE-FRESH",
                state=control.STATE_COMPLETED,
                lease_until=None,
            ),
        },
        sets={task_ids_key: {"RUN-INDEXED"}},
        lists={queue_key: []},
        zsets={active_index_key: ["RUN-INDEXED"]},
    )
    monkeypatch.setattr(control, "redis", redis)
    monkeypatch.setattr(control, "now_ts", lambda: 1000.0)

    payload = control.task_list_payload(compact=True, include_summary=True)
    task_ids = [task["task_id"] for task in payload["tasks"]]

    assert task_ids == ["DONE-FRESH", "RUN-EXPIRED", "RUN-INDEXED", "RUN-MISSING-FROM-INDEX"]
    assert {"RUN-INDEXED", "RUN-MISSING-FROM-INDEX"} <= redis.sets[task_ids_key]
    assert all("envelope" not in task for task in payload["tasks"])
    assert payload["summary"]["counts_by_state"] == {"completed": 1, "running": 3}
    assert payload["active_total"] == 2
    assert payload["running_total"] == 2
    assert payload["repair_total"] == 2
    assert payload["stale_active_records"] == 1


def test_task_summary_does_not_count_finished_or_expired_tasks_as_active():
    control = load_module(ROOT / "ops" / "factory_control.py")
    tasks = [
        json.loads(task_json(control, "QUEUED", state=control.STATE_QUEUED, lease_until=None, heartbeat_at=None)),
        json.loads(task_json(control, "RUNNING-FRESH")),
        json.loads(task_json(control, "RUNNING-EXPIRED", lease_until=900.0, heartbeat_at=datetime.fromtimestamp(900, timezone.utc).isoformat())),
        json.loads(task_json(control, "FAILED", state=control.STATE_FAILED, lease_until=None)),
        json.loads(task_json(control, "COMPLETED", state=control.STATE_COMPLETED, lease_until=None)),
    ]

    summary = control.task_summary(tasks, current=1000.0)

    assert summary["active_total"] == 2
    assert summary["queued_total"] == 1
    assert summary["running_total"] == 1
    assert summary["failed_total"] == 1
    assert summary["stale_active_records"] == 1


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
