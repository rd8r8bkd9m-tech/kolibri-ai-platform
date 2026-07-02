import importlib.util
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load_control():
    spec = importlib.util.spec_from_file_location('factory_control', ROOT / 'ops' / 'factory_control.py')
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.sets = {}
        self.lists = {}

    def command(self, *parts):
        command = str(parts[0]).upper()
        if command == "GET":
            return self.values.get(parts[1])
        if command == "SET":
            self.values[parts[1]] = str(parts[2])
            return "OK"
        if command == "SADD":
            self.sets.setdefault(parts[1], set()).add(str(parts[2]))
            return 1
        if command == "SMEMBERS":
            return sorted(self.sets.get(parts[1], set()))
        if command == "RPUSH":
            self.lists.setdefault(parts[1], []).append(str(parts[2]))
            return len(self.lists[parts[1]])
        if command == "LRANGE":
            values = self.lists.get(parts[1], [])
            start = int(parts[2])
            end = int(parts[3])
            if end == -1:
                return values[start:]
            return values[start : end + 1]
        if command == "LREM":
            key, _, value = parts[1], int(parts[2]), str(parts[3])
            current = self.lists.get(key, [])
            removed = len([item for item in current if item == value])
            self.lists[key] = [item for item in current if item != value]
            return removed
        if command == "DEL":
            self.values.pop(parts[1], None)
            return 1
        raise AssertionError(f"unsupported fake redis command: {parts}")


def load_control_with_fake_redis():
    control = load_control()
    control.redis = FakeRedis()
    return control

def test_task_envelope_schema_and_idempotency_key():
    control = load_control()
    task = control.normalize_task({'task_id': 'SCHEMA-1', 'idempotency_key': 'idem-1', 'kind': 'read_only_probe'})
    for key in ['task_id', 'idempotency_key', 'kind', 'state', 'attempt', 'lease_owner', 'lease_until', 'result_reference', 'error_type']:
        assert key in task
    assert task['idempotency_key'] == 'idem-1'
    assert task['state'] == 'queued'

def test_heartbeat_payload_schema():
    payload = {'node_id': '9fts', 'agent_id': 'agent-host-9fts', 'pid': 123, 'capabilities': ['implementation'], 'active_task': None}
    assert {'node_id', 'agent_id', 'pid', 'capabilities'} <= set(payload)
    assert isinstance(payload['capabilities'], list)

def test_result_envelope_schema():
    result = {'node_id': '9fts', 'agent_id': 'agent-host-9fts', 'task_id': 'SCHEMA-1', 'status': 'completed', 'result_path': '/tmp/result.json'}
    assert {'node_id', 'agent_id', 'task_id', 'status', 'result_path'} <= set(result)

def test_lease_expiry_calculation():
    control = load_control()
    lease_until = time.time() + control.LEASE_DURATION
    assert lease_until > time.time()
    assert control.LEASE_DURATION >= 60


def test_expired_lease_is_requeued_once_with_runtime_event():
    control = load_control_with_fake_redis()
    task = control.normalize_task({"task_id": "LEASE-REQUEUE-1", "max_retries": 2})
    task["state"] = control.STATE_RUNNING
    task["attempt"] = 1
    task["lease_owner"] = "worker-1:agent-host"
    task["lease_until"] = time.time() - 1
    control.save_task(task)

    summary = control.requeue_expired_leases()
    summary_again = control.requeue_expired_leases()
    updated = control.load_task("LEASE-REQUEUE-1")

    assert summary == {"inspected": 1, "requeued": 1, "dead_lettered": 0}
    assert summary_again == {"inspected": 0, "requeued": 0, "dead_lettered": 0}
    assert updated["state"] == control.STATE_QUEUED
    assert updated["lease_owner"] is None
    assert updated["lease_until"] is None
    assert updated["error_type"] == "lease_expired"
    assert updated["runtime_events"][-1]["event"] == "lease_expired_requeued"
    assert control.queue_ids() == ["LEASE-REQUEUE-1"]


def test_expired_lease_dead_letters_when_retry_budget_is_exhausted():
    control = load_control_with_fake_redis()
    task = control.normalize_task({"task_id": "LEASE-DEAD-1", "max_retries": 1})
    task["state"] = control.STATE_LEASED
    task["attempt"] = 1
    task["lease_owner"] = "worker-1:agent-host"
    task["lease_until"] = time.time() - 1
    control.save_task(task)

    summary = control.requeue_expired_leases()
    updated = control.load_task("LEASE-DEAD-1")

    assert summary == {"inspected": 1, "requeued": 0, "dead_lettered": 1}
    assert updated["state"] == control.STATE_DEAD
    assert updated["error_type"] == "lease_expired"
    assert updated["runtime_events"][-1]["event"] == "lease_expired_dead_lettered"
    assert control.queue_ids() == []
    assert control.dead_letter_ids() == ["LEASE-DEAD-1"]


def test_superfactory_status_reconciles_expired_leases_and_exposes_dead_letter():
    control = load_control_with_fake_redis()
    task = control.normalize_task({"task_id": "LEASE-STATUS-1", "max_retries": 1})
    task["state"] = control.STATE_REVIEW
    task["attempt"] = 1
    task["lease_owner"] = "reviewer:agent-host"
    task["lease_until"] = time.time() - 1
    control.save_task(task)

    status = control.superfactory_status()

    assert status["runtime_reconciliation"] == {"inspected": 1, "requeued": 0, "dead_lettered": 1}
    assert status["task_counts"][control.STATE_DEAD] == 1
    assert status["queue"] == []
    assert status["dead_letter"] == ["LEASE-STATUS-1"]
