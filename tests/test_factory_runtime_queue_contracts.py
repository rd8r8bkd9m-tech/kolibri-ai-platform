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


def test_home_node_has_agent_host_api():
    control = load_control()
    nodes = control.fabric_nodes([])
    home = next((n for n in nodes if n['node_id'] == 'home'), None)
    assert home is not None, 'home node missing from fabric catalog'
    assert 'agent_host_api' in home.get('api_paths', []), f'home node missing agent_host_api: {home}'


def test_home_compatible_owner_remote_task_with_runner_mimo():
    control = load_control()
    task = control.normalize_task({
        'task_id': 'HOME-LEASE-1',
        'kind': 'owner_remote_task',
        'runner': 'mimo',
        'target_node': 'home',
        'required_capability': 'generic_implementation',
        'objective': 'deploy kiosk to home',
    })
    caps = ['read_only_probe', 'runner:mimo', 'generic_implementation']
    assert control.compatible(task, 'home', caps), \
        'home node should be compatible with owner_remote_task targeting home with runner:mimo'


def test_home_compatible_rejects_wrong_target_node():
    control = load_control()
    task = control.normalize_task({
        'task_id': 'HOME-LEASE-2',
        'kind': 'owner_remote_task',
        'runner': 'mimo',
        'target_node': '9fts',
        'required_capability': 'generic_implementation',
    })
    caps = ['read_only_probe', 'runner:mimo', 'generic_implementation']
    assert not control.compatible(task, 'home', caps), \
        'home should not be compatible with task targeted to 9fts'


def test_home_compatible_rejects_missing_required_capability():
    control = load_control()
    task = control.normalize_task({
        'task_id': 'HOME-LEASE-3',
        'kind': 'owner_remote_task',
        'runner': 'mimo',
        'target_node': 'home',
        'required_capability': 'missing_capability',
    })
    caps = ['read_only_probe', 'runner:mimo', 'generic_implementation']
    assert not control.compatible(task, 'home', caps), \
        'home should not be compatible when required_capability is missing'


def test_runner_capability_names_mimo():
    control = load_control()
    names = control.runner_capability_names('mimo')
    assert 'runner:mimo' in names
    assert 'runner_mimo' in names
    assert 'mimo_runner' in names
