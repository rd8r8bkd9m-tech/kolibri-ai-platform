import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_control():
    spec = importlib.util.spec_from_file_location("factory_control", ROOT / "ops" / "factory_control.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.sets = {}
        self.lists = {}

    def command(self, command, *parts):
        command = command.upper()
        if command == "PING":
            return "PONG"
        if command == "GET":
            return self.values.get(parts[0])
        if command == "SET":
            self.values[parts[0]] = parts[1]
            return "OK"
        if command == "DEL":
            self.values.pop(parts[0], None)
            return 1
        if command == "SADD":
            self.sets.setdefault(parts[0], set()).add(parts[1])
            return 1
        if command == "SMEMBERS":
            return sorted(self.sets.get(parts[0], set()))
        if command == "RPUSH":
            self.lists.setdefault(parts[0], []).append(parts[1])
            return len(self.lists[parts[0]])
        if command == "LRANGE":
            values = self.lists.get(parts[0], [])
            start = int(parts[1])
            stop = int(parts[2])
            if stop == -1:
                return values[start:]
            return values[start : stop + 1]
        if command == "LREM":
            values = self.lists.get(parts[0], [])
            target = parts[2]
            self.lists[parts[0]] = [value for value in values if value != target]
            return len(values) - len(self.lists[parts[0]])
        raise AssertionError(f"unsupported redis command: {command}")


def seed_json(control, redis, redis_key, value):
    redis.values[redis_key] = json.dumps(value, sort_keys=True, separators=(",", ":"))


def test_supervisor_repair_budget_is_capped_at_50_percent():
    control = load_control()

    assert control.repair_dispatch_budget(0) == 0
    assert control.repair_dispatch_budget(1) == 0
    assert control.repair_dispatch_budget(2) == 1
    assert control.repair_dispatch_budget(5) == 2
    assert control.repair_dispatch_budget(10, ratio=1.0) == 5


def test_supervisor_cycle_marks_dead_agents_and_dispatches_repair_with_cap():
    control = load_control()
    fake = FakeRedis()
    control.redis = fake
    old = datetime.now(timezone.utc) - timedelta(seconds=control.SUPERVISOR_AGENT_DEAD_AFTER + 30)
    fresh = datetime.now(timezone.utc)

    for node_id, heartbeat in {
        "dead-a": old,
        "dead-b": old,
        "fresh-a": fresh,
        "fresh-b": fresh,
    }.items():
        fake.command("SADD", control.key("node_ids"), node_id)
        seed_json(
            control,
            fake,
            control.node_key(node_id),
            {
                "node_id": node_id,
                "health": "online",
                "heartbeat_at": heartbeat.isoformat(),
                "capabilities": ["generic_implementation"],
            },
        )

    report = control.supervisor_cycle()

    assert report["health"]["redis"] == "PONG"
    assert len(report["dead_agents"]) == 2
    assert report["repair_dispatch_cap"] == 2
    assert len(report["repair_tasks_dispatched"]) == 2
    assert "потолок 50%" in report["owner_summary_ru"]
    assert json.loads(fake.values[control.node_key("dead-a")])["health"] == "dead"


def test_supervisor_requeues_stuck_running_task_once():
    control = load_control()
    fake = FakeRedis()
    control.redis = fake
    stale = datetime.now(timezone.utc) - timedelta(seconds=control.SUPERVISOR_TASK_STUCK_AFTER + 10)
    task = control.normalize_task({"task_id": "TASK-STUCK-1", "kind": "read_only_probe", "max_retries": 2})
    task.update({
        "state": control.STATE_RUNNING,
        "attempt": 1,
        "lease_owner": "dead-a:agent",
        "lease_until": control.now_ts() + 3600,
        "heartbeat_at": stale.isoformat(),
    })
    seed_json(control, fake, control.task_key(task["task_id"]), task)
    fake.command("SADD", control.key("task_ids"), task["task_id"])

    repaired = control.requeue_stuck_tasks()

    stored = json.loads(fake.values[control.task_key(task["task_id"])])
    assert repaired == [
        {
            "task_id": "TASK-STUCK-1",
            "action": "requeued",
            "heartbeat_age_seconds": repaired[0]["heartbeat_age_seconds"],
            "attempt": 1,
            "max_retries": 2,
        }
    ]
    assert stored["state"] == control.STATE_QUEUED
    assert stored["lease_owner"] is None
    assert fake.lists[control.key("queue")] == ["TASK-STUCK-1"]
