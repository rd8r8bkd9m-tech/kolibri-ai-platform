import importlib.util
import time
from datetime import datetime, timedelta, timezone
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


def test_queue_guardian_detects_expired_stuck_and_duplicate_entries():
    control = load_control()
    current = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc).timestamp()
    old_heartbeat = (datetime.fromtimestamp(current, timezone.utc) - timedelta(seconds=control.TASK_STUCK_RUNNING_AFTER + 5)).isoformat()
    tasks = [
        {
            "task_id": "LEASE-1",
            "state": control.STATE_RUNNING,
            "attempt": 1,
            "max_retries": 2,
            "lease_owner": "9fts:agent",
            "lease_until": current - 10,
            "heartbeat_at": old_heartbeat,
            "envelope": {},
        },
        {
            "task_id": "QUEUE-1",
            "state": control.STATE_QUEUED,
            "attempt": 0,
            "max_retries": 1,
            "envelope": {},
        },
    ]

    report = control.inspect_queue_lease_health(
        tasks=tasks,
        queue=["QUEUE-1", "QUEUE-1", "LEASE-1", "MISSING"],
        dead_letter=[],
        current=current,
    )

    kinds = {finding["kind"] for finding in report["findings"]}
    assert report["status"] == "repair_required"
    assert "expired_lease" in kinds
    assert "stuck_running_task" in kinds
    assert "duplicate_queue_entry" in kinds
    assert "non_queued_task_in_queue" in kinds
    assert "orphan_queue_entry" in kinds
    assert report["summary"]["duplicate_queue_entries"] == ["QUEUE-1"]
    assert any(task["kind"] == "queue_lease_repair" for task in report["repair_tasks"])


def test_queue_guardian_generates_idempotent_repair_envelopes():
    control = load_control()
    findings = [
        {"kind": "expired_lease", "task_id": "TASK-1", "node": "main", "recommended_action": "requeue expired lease"},
        {"kind": "expired_lease", "task_id": "TASK-1", "node": "main", "recommended_action": "requeue expired lease"},
    ]

    repairs = control.queue_guardian_repair_envelopes(findings)

    assert len(repairs) == 1
    assert repairs[0]["idempotency_key"] == "queue-lease-guardian:expired_lease:TASK-1"
    assert repairs[0]["target_node"] == "main"
    assert repairs[0]["constraints"]["no_secrets"] is True
