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

def test_queue_guardian_classifies_core_backlog_and_first_repair_queue():
    control = load_control()
    current = 1_000.0
    queued = control.normalize_task({'task_id': 'QUEUE-1'})
    failed = control.normalize_task({'task_id': 'FAIL-1', 'max_retries': 2})
    failed.update({'state': control.STATE_FAILED, 'attempt': 1, 'error_type': 'runtime_error'})
    running = control.normalize_task({'task_id': 'RUN-1', 'max_retries': 2})
    running.update({'state': control.STATE_RUNNING, 'attempt': 1, 'lease_owner': '9fts:agent-host-9fts', 'lease_until': current - 1})
    dead = control.normalize_task({'task_id': 'DEAD-1'})
    dead.update({'state': control.STATE_DEAD, 'attempt': 3, 'max_retries': 3})

    snapshot = control.queue_guardian_snapshot(
        [queued, failed, running, dead],
        queue=['QUEUE-1'],
        dead_letter=['DEAD-1'],
        current=current,
    )

    assert snapshot['counts'] == {'queued': 1, 'failed': 1, 'running': 1, 'dead_letter': 1}
    by_id = {item['task_id']: item for item in snapshot['backlog']}
    assert by_id['QUEUE-1']['policy']['action'] == 'lease'
    assert by_id['FAIL-1']['blockers'] == ['missing_failure_artifact']
    assert by_id['FAIL-1']['policy']['action'] == 'retry'
    assert by_id['RUN-1']['blockers'] == ['lease_expired']
    assert by_id['RUN-1']['policy']['action'] == 'retry'
    assert by_id['DEAD-1']['policy']['action'] == 'supersede'
    assert by_id['DEAD-1']['policy']['owner_gate_required'] is True
    assert snapshot['first_repair_queue'][0]['task_id'] == 'DEAD-1'

def test_queue_guardian_owner_gates_broad_retry_supersede_cancel_policy():
    control = load_control()
    failed = control.normalize_task({'task_id': 'EXHAUSTED-1', 'max_retries': 1})
    failed.update({'state': control.STATE_FAILED, 'attempt': 1})
    dead = control.normalize_task({'task_id': 'DEAD-MISSING-INDEX'})
    dead.update({'state': control.STATE_DEAD})

    failed_policy = control.queue_guardian_policy(failed, queued_task_ids=set(), dead_letter_task_ids=set(), current=1_000.0)
    dead_policy = control.queue_guardian_policy(dead, queued_task_ids=set(), dead_letter_task_ids=set(), current=1_000.0)

    assert failed_policy['policy']['action'] == 'supersede'
    assert failed_policy['policy']['owner_gate_required'] is True
    assert failed_policy['policy']['broad_action_forbidden_without_owner_gate'] is True
    assert dead_policy['blockers'] == ['dead_letter_index_missing']
    assert dead_policy['policy']['owner_gate_required'] is True
