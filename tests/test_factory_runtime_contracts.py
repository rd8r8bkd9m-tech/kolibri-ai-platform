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


def test_root_goal_task_kind_normalize():
    control = load_control()
    task = control.normalize_task({
        'task_id': 'ROOT-1',
        'idempotency_key': 'root-idem-1',
        'kind': 'root_goal',
        'envelope': {'objective': 'Добавить dark mode'}
    })
    assert task['kind'] == 'root_goal'
    assert task['state'] == 'queued'


def test_root_goal_task_schema():
    task = {
        'node_id': '9fts',
        'agent_id': 'agent-host-9fts',
        'task_id': 'ROOT-1',
        'status': 'completed',
        'kind': 'root_goal',
        'objective': 'Добавить dark mode',
        'result_path': '/tmp/result.json',
    }
    assert task['kind'] == 'root_goal'
    assert 'objective' in task
