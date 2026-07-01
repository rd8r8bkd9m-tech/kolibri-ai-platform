import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_control():
    spec = importlib.util.spec_from_file_location("factory_control", ROOT / "ops" / "factory_control.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MemoryRedis:
    def __init__(self):
        self.values = {}
        self.sets = {}
        self.lists = {}

    def command(self, *parts):
        command = parts[0]
        if command == "GET":
            return self.values.get(parts[1])
        if command == "SET":
            self.values[parts[1]] = parts[2]
            return "OK"
        if command == "SADD":
            self.sets.setdefault(parts[1], set()).add(parts[2])
            return 1
        if command == "SMEMBERS":
            return sorted(self.sets.get(parts[1], set()))
        if command == "RPUSH":
            self.lists.setdefault(parts[1], []).append(parts[2])
            return len(self.lists[parts[1]])
        if command == "LRANGE":
            return list(self.lists.get(parts[1], []))
        if command == "LREM":
            self.lists[parts[1]] = [item for item in self.lists.get(parts[1], []) if item != parts[3]]
            return 1
        if command == "INCR":
            self.values[parts[1]] = str(int(self.values.get(parts[1], "0")) + 1)
            return int(self.values[parts[1]])
        if command == "EXPIRE":
            return 1
        if command == "PING":
            return "PONG"
        if command == "DEL":
            self.values.pop(parts[1], None)
            return 1
        raise AssertionError(f"unexpected redis command: {parts}")


def test_scheduler_capacity_is_gated_and_logical_not_process_count():
    control = load_control()
    capacity = control.scheduler_capacity_for_node(
        {
            "node_id": "server-a",
            "health": "online",
            "agent_id": "agent-a",
            "heartbeat_at": "now",
            "capabilities": ["implementation"],
            "cpu": 64,
            "max_inflight": 50,
            "subagent_target": 100,
        },
        active_tasks=3,
    )

    assert capacity["capacity"] == 20
    assert capacity["available"] == 17
    assert capacity["max_subagent_target"] == 20
    assert control.GLOBAL_LOGICAL_AGENT_TARGET == 1000


def test_fresh_node_without_agent_is_classified_as_blocked():
    control = load_control()
    readiness, blockers = control.classify_node_readiness({"node_id": "fresh", "health": "online"})

    assert readiness == "blocked"
    assert "agent_not_registered" in blockers
    assert "heartbeat_missing" in blockers
    assert "capabilities_missing" in blockers


def test_followup_task_requires_idempotency_and_rate_limits(monkeypatch):
    control = load_control()
    memory = MemoryRedis()
    monkeypatch.setattr(control, "redis", memory)
    monkeypatch.setattr(control, "FOLLOWUP_RATE_LIMIT", 1)

    source = control.normalize_task({"task_id": "PARENT-1", "kind": "read_only_probe"})
    source["state"] = control.STATE_RUNNING
    source["lease_owner"] = "node-a:agent-a"
    control.save_task(source)

    child = control.create_followup_task(
        "PARENT-1",
        {
            "agent_id": "node-a:agent-a",
            "idempotency_key": "repair-runtime-error",
            "envelope": {"kind": "read_only_probe", "required_capability": "implementation"},
        },
    )

    assert child["envelope"]["parent_task_id"] == "PARENT-1"
    assert child["envelope"]["idempotency_key"] == "followup:PARENT-1:repair-runtime-error"
    assert child["state"] == control.STATE_QUEUED

    try:
        control.create_followup_task(
            "PARENT-1",
            {
                "agent_id": "node-a:agent-a",
                "idempotency_key": "second",
                "envelope": {"kind": "read_only_probe"},
            },
        )
    except OverflowError as exc:
        assert str(exc) == "followup_rate_limited"
    else:
        raise AssertionError("expected followup rate limit")
