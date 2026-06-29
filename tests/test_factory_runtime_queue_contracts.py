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


def test_compact_task_listing_bounds_payload_and_exposes_queue_and_leases(monkeypatch):
    control = load_control()
    current = time.time()
    noisy_payload = {"prompt": "x" * 10000, "result_blob": "y" * 10000}
    tasks = {
        "TASK-QUEUED": {
            "task_id": "TASK-QUEUED",
            "kind": "generic_implementation",
            "state": control.STATE_QUEUED,
            "created_at": "2026-06-29T00:00:00+00:00",
            "updated_at": "2026-06-29T00:00:00+00:00",
            "envelope": noisy_payload,
            "result": noisy_payload,
        },
        "TASK-RUNNING": {
            "task_id": "TASK-RUNNING",
            "kind": "generic_implementation",
            "state": control.STATE_RUNNING,
            "lease_owner": "node-a:agent-a",
            "lease_until": current - 5,
            "created_at": "2026-06-29T00:01:00+00:00",
            "updated_at": "2026-06-29T00:01:00+00:00",
            "envelope": {"target_node": "node-a", **noisy_payload},
            "result": noisy_payload,
        },
        "TASK-DONE": {
            "task_id": "TASK-DONE",
            "kind": "read_only_probe",
            "state": control.STATE_COMPLETED,
            "created_at": "2026-06-29T00:02:00+00:00",
            "updated_at": "2026-06-29T00:02:00+00:00",
            "envelope": noisy_payload,
            "result": noisy_payload,
        },
    }

    monkeypatch.setattr(control, "all_task_ids", lambda: list(tasks))
    monkeypatch.setattr(control, "load_task", lambda task_id: tasks[task_id])
    monkeypatch.setattr(control, "queue_length", lambda: 3)
    monkeypatch.setattr(control, "queue_prefix", lambda limit: ["TASK-QUEUED", "TASK-RUNNING"][:limit])

    listing = control.compact_task_listing(wanted=None, limit=2)

    assert len(listing["tasks"]) == 2
    assert "envelope" not in listing["tasks"][0]
    assert "result" not in listing["tasks"][0]
    assert listing["queue_length"] == 3
    assert listing["summary"]["queue_total"] == 3
    assert listing["summary"]["queue_returned"] == 2
    assert listing["summary"]["queue_truncated"] is True
    assert listing["summary"]["tasks_returned"] == 2
    assert listing["summary"]["tasks_truncated"] is True
    assert listing["summary"]["states"][control.STATE_RUNNING] == 1
    assert listing["summary"]["expired_lease_total"] == 1
    assert listing["summary"]["active_total"] == 1
