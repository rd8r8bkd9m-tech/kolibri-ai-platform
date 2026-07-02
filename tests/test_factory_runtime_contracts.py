import importlib.util
import hashlib
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

def test_filesystem_manifest_reports_repo_file_sha(tmp_path):
    control = load_control()
    repo = tmp_path / "repo"
    target = repo / "ops" / "factory_control.py"
    target.parent.mkdir(parents=True)
    target.write_text("runtime-version\n", encoding="utf-8")

    manifest = control.filesystem_manifest(["ops/factory_control.py"], repo_root=repo)

    assert manifest["missing"] == []
    assert manifest["files"][0]["exists"] is True
    assert manifest["files"][0]["sha256"] == hashlib.sha256(b"runtime-version\n").hexdigest()

def test_filesystem_manifest_rejects_paths_outside_repo(tmp_path):
    control = load_control()

    entry = control.filesystem_entry("../secret.txt", repo_root=tmp_path)

    assert entry["exists"] is False
    assert entry["error"] == "path_outside_repo"

def test_task_page_prefilters_state_before_pagination():
    control = load_control()
    tasks = [
        {"task_id": "queued-1", "state": control.STATE_QUEUED},
        {"task_id": "running-1", "state": control.STATE_RUNNING},
        {"task_id": "running-2", "state": control.STATE_RUNNING},
        {"task_id": "done-1", "state": control.STATE_COMPLETED},
    ]

    page = control.task_page(tasks, state=control.STATE_RUNNING, limit=1, cursor=1)

    assert [task["task_id"] for task in page["tasks"]] == ["running-2"]
    assert page["total"] == 2
    assert page["next_cursor"] is None

def test_registry_hygiene_flags_synthetic_duplicates_and_namespace_drift():
    control = load_control()

    report = control.registry_hygiene_report([
        {"node_id": "10-99-0-10", "namespace": control.NAMESPACE},
        {"node_id": "canary-fixture-1", "namespace": control.NAMESPACE},
        {"node_id": "10-99-0-10", "namespace": "old_namespace"},
        {"agent_id": "missing-node-id"},
    ])

    assert report["status"] == "needs_cleanup"
    assert report["issues"]["synthetic_nodes"] == ["canary-fixture-1"]
    assert report["issues"]["duplicate_node_ids"] == ["10-99-0-10"]
    assert report["issues"]["missing_node_id_count"] == 1
    assert report["issues"]["wrong_namespace"] == [{"node_id": "10-99-0-10", "namespace": "old_namespace"}]
