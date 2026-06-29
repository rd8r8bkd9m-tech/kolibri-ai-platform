import importlib.util
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load_control():
    spec = importlib.util.spec_from_file_location('factory_control', ROOT / 'ops' / 'factory_control.py')
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

def load_agent_host():
    spec = importlib.util.spec_from_file_location('agent_host', ROOT / 'ops' / 'agent_host.py')
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


def test_state_filtered_task_sample_uses_state_index_without_full_task_scan(monkeypatch):
    control = load_control()
    tasks = {
        "WAITING-1": {
            "task_id": "WAITING-1",
            "kind": "generic_implementation",
            "state": control.STATE_WAITING_REVIEW,
            "updated_at": "2026-06-29T00:03:00+00:00",
            "envelope": {"branch": "agent/waiting-1"},
        }
    }

    def fail_full_scan():
        raise AssertionError("state-filtered listing must not call all_task_ids")

    monkeypatch.setattr(control, "all_task_ids", fail_full_scan)
    monkeypatch.setattr(control, "indexed_task_ids_for_state", lambda state: ["WAITING-1"])
    monkeypatch.setattr(control, "load_task", lambda task_id: tasks[task_id])

    sample, meta = control.task_sample(wanted=control.STATE_WAITING_REVIEW, limit=10, compact=True)

    assert [task["task_id"] for task in sample] == ["WAITING-1"]
    assert meta["source"] == "state_index"
    assert meta["candidate_total"] == 1
    assert "envelope" not in sample[0]


def test_task_sample_supports_offset_for_state_pagination(monkeypatch):
    control = load_control()
    tasks = {
        f"WAITING-{idx}": {
            "task_id": f"WAITING-{idx}",
            "kind": "generic_implementation",
            "state": control.STATE_WAITING_REVIEW,
            "updated_at": f"2026-06-29T00:0{idx}:00+00:00",
            "envelope": {},
        }
        for idx in range(1, 4)
    }

    monkeypatch.setattr(control, "indexed_task_ids_for_state", lambda state: list(tasks))
    monkeypatch.setattr(control, "load_task", lambda task_id: tasks[task_id])

    sample, meta = control.task_sample(wanted=control.STATE_WAITING_REVIEW, limit=1, compact=True, offset=1)

    assert [task["task_id"] for task in sample] == ["WAITING-2"]
    assert meta["offset"] == 1
    assert meta["tasks_truncated"] is True


def test_requeue_expired_leases_returns_stuck_tasks_to_queue(monkeypatch):
    control = load_control()
    current = time.time()
    tasks = {
        "TASK-EXPIRED": {
            "task_id": "TASK-EXPIRED",
            "kind": "generic_implementation",
            "state": control.STATE_RUNNING,
            "attempt": 1,
            "max_retries": 2,
            "lease_owner": "home:agent-host-home",
            "lease_until": current - 10,
            "result_reference": "/tmp/result.json",
            "envelope": {"task_id": "TASK-EXPIRED"},
        },
        "TASK-LIVE": {
            "task_id": "TASK-LIVE",
            "kind": "generic_implementation",
            "state": control.STATE_RUNNING,
            "attempt": 1,
            "max_retries": 2,
            "lease_owner": "home:agent-host-home",
            "lease_until": current + 30,
            "envelope": {"task_id": "TASK-LIVE"},
        },
    }
    saved = []
    removed = []
    enqueued = []

    monkeypatch.setattr(control, "now_ts", lambda: current)
    monkeypatch.setattr(control, "all_task_ids", lambda: list(tasks))
    monkeypatch.setattr(control, "leased_task_ids", lambda: list(tasks))
    monkeypatch.setattr(control, "load_task", lambda task_id: tasks[task_id])
    monkeypatch.setattr(control, "save_task", lambda task: saved.append((task["task_id"], task["state"])) or tasks.__setitem__(task["task_id"], dict(task)))
    monkeypatch.setattr(control, "remove_from_queue", lambda task_id: removed.append(task_id))
    monkeypatch.setattr(control, "enqueue", lambda task_id: enqueued.append(task_id))

    summary = control.requeue_expired_leases()

    assert summary["checked"] == 2
    assert summary["lease_index_total"] == 2
    assert summary["expired"] == 1
    assert summary["requeued"] == ["TASK-EXPIRED"]
    assert summary["dead_lettered"] == []
    assert tasks["TASK-EXPIRED"]["state"] == control.STATE_QUEUED
    assert tasks["TASK-EXPIRED"]["lease_owner"] is None
    assert tasks["TASK-EXPIRED"]["lease_until"] is None
    assert tasks["TASK-EXPIRED"]["error_type"] == "lease_expired"
    assert tasks["TASK-EXPIRED"]["attempt_history"][-1]["status"] == "lease_expired"
    assert removed == ["TASK-EXPIRED"]
    assert enqueued == ["TASK-EXPIRED"]
    assert (("TASK-EXPIRED", control.STATE_RETRY) in saved)
    assert (("TASK-EXPIRED", control.STATE_QUEUED) in saved)


def test_requeue_expired_leases_dead_letters_exhausted_tasks(monkeypatch):
    control = load_control()
    current = time.time()
    tasks = {
        "TASK-EXHAUSTED": {
            "task_id": "TASK-EXHAUSTED",
            "kind": "generic_implementation",
            "state": control.STATE_REVIEW,
            "attempt": 2,
            "max_retries": 2,
            "lease_owner": "home:agent-host-home",
            "lease_until": current - 10,
            "envelope": {"task_id": "TASK-EXHAUSTED"},
        },
    }
    saved = []
    dead = []

    class FakeRedis:
        def command(self, command, redis_key, task_id):
            assert command == "RPUSH"
            assert redis_key == control.key("dead_letter")
            dead.append(task_id)

    monkeypatch.setattr(control, "now_ts", lambda: current)
    monkeypatch.setattr(control, "all_task_ids", lambda: list(tasks))
    monkeypatch.setattr(control, "leased_task_ids", lambda: list(tasks))
    monkeypatch.setattr(control, "load_task", lambda task_id: tasks[task_id])
    monkeypatch.setattr(control, "save_task", lambda task: saved.append((task["task_id"], task["state"])) or tasks.__setitem__(task["task_id"], dict(task)))
    monkeypatch.setattr(control, "redis", FakeRedis())

    summary = control.requeue_expired_leases()

    assert summary["checked"] == 1
    assert summary["lease_index_total"] == 1
    assert summary["expired"] == 1
    assert summary["requeued"] == []
    assert summary["dead_lettered"] == ["TASK-EXHAUSTED"]
    assert tasks["TASK-EXHAUSTED"]["state"] == control.STATE_DEAD
    assert tasks["TASK-EXHAUSTED"]["lease_owner"] is None
    assert tasks["TASK-EXHAUSTED"]["lease_until"] is None
    assert tasks["TASK-EXHAUSTED"]["attempt_history"][-1]["status"] == "dead_letter"
    assert dead == ["TASK-EXHAUSTED"]
    assert saved == [("TASK-EXHAUSTED", control.STATE_DEAD)]


def test_sweep_stuck_tasks_requeues_stale_heartbeat_with_live_lease(monkeypatch):
    control = load_control()
    current = control.datetime.fromisoformat("2026-06-29T07:30:00+00:00")
    stale_heartbeat = "2026-06-29T07:20:00+00:00"
    tasks = {
        "TASK-STUCK": {
            "task_id": "TASK-STUCK",
            "kind": "generic_implementation",
            "state": control.STATE_RUNNING,
            "attempt": 1,
            "max_retries": 2,
            "lease_owner": "main:agent-host-main",
            "lease_until": current.timestamp() + 600,
            "heartbeat_at": stale_heartbeat,
            "result_reference": "/tmp/result.json",
            "envelope": {"task_id": "TASK-STUCK"},
        },
        "TASK-FRESH": {
            "task_id": "TASK-FRESH",
            "kind": "generic_implementation",
            "state": control.STATE_RUNNING,
            "attempt": 1,
            "max_retries": 2,
            "lease_owner": "main:agent-host-main",
            "lease_until": current.timestamp() + 600,
            "heartbeat_at": current.isoformat(),
            "envelope": {"task_id": "TASK-FRESH"},
        },
    }
    saved = []
    removed = []
    enqueued = []

    class FixedDateTime(control.datetime):
        @classmethod
        def now(cls, tz=None):
            return current if tz else current.replace(tzinfo=None)

    monkeypatch.setattr(control, "datetime", FixedDateTime)
    monkeypatch.setattr(control, "all_task_ids", lambda: list(tasks))
    monkeypatch.setattr(control, "leased_task_ids", lambda: list(tasks))
    monkeypatch.setattr(control, "load_task", lambda task_id: tasks[task_id])
    monkeypatch.setattr(control, "save_task", lambda task: saved.append((task["task_id"], task["state"])) or tasks.__setitem__(task["task_id"], dict(task)))
    monkeypatch.setattr(control, "remove_from_queue", lambda task_id: removed.append(task_id))
    monkeypatch.setattr(control, "enqueue", lambda task_id: enqueued.append(task_id))

    summary = control.sweep_stuck_tasks(limit=10, stale_after=120)

    assert summary["checked"] == 2
    assert summary["stuck"] == 1
    assert summary["requeued"][0]["task_id"] == "TASK-STUCK"
    assert summary["dead_lettered"] == []
    assert tasks["TASK-STUCK"]["state"] == control.STATE_QUEUED
    assert tasks["TASK-STUCK"]["lease_owner"] is None
    assert tasks["TASK-STUCK"]["lease_until"] is None
    assert tasks["TASK-STUCK"]["error_type"] == "stuck_no_heartbeat"
    assert tasks["TASK-STUCK"]["attempt_history"][-1]["status"] == "stuck_no_heartbeat"
    assert removed == ["TASK-STUCK"]
    assert enqueued == ["TASK-STUCK"]


def test_sweep_stuck_tasks_dead_letters_when_retry_budget_exhausted(monkeypatch):
    control = load_control()
    current = control.datetime.fromisoformat("2026-06-29T07:30:00+00:00")
    tasks = {
        "TASK-STUCK-DEAD": {
            "task_id": "TASK-STUCK-DEAD",
            "kind": "generic_implementation",
            "state": control.STATE_REVIEW,
            "attempt": 2,
            "max_retries": 2,
            "lease_owner": "new:agent-host-new",
            "lease_until": current.timestamp() + 600,
            "heartbeat_at": "2026-06-29T07:00:00+00:00",
            "envelope": {"task_id": "TASK-STUCK-DEAD"},
        },
    }
    saved = []
    dead = []

    class FixedDateTime(control.datetime):
        @classmethod
        def now(cls, tz=None):
            return current if tz else current.replace(tzinfo=None)

    class FakeRedis:
        def command(self, command, redis_key, task_id):
            assert command == "RPUSH"
            assert redis_key == control.key("dead_letter")
            dead.append(task_id)

    monkeypatch.setattr(control, "datetime", FixedDateTime)
    monkeypatch.setattr(control, "all_task_ids", lambda: list(tasks))
    monkeypatch.setattr(control, "leased_task_ids", lambda: list(tasks))
    monkeypatch.setattr(control, "load_task", lambda task_id: tasks[task_id])
    monkeypatch.setattr(control, "save_task", lambda task: saved.append((task["task_id"], task["state"])) or tasks.__setitem__(task["task_id"], dict(task)))
    monkeypatch.setattr(control, "redis", FakeRedis())

    summary = control.sweep_stuck_tasks(limit=10, stale_after=120)

    assert summary["checked"] == 1
    assert summary["stuck"] == 1
    assert summary["requeued"] == []
    assert summary["dead_lettered"][0]["task_id"] == "TASK-STUCK-DEAD"
    assert tasks["TASK-STUCK-DEAD"]["state"] == control.STATE_DEAD
    assert tasks["TASK-STUCK-DEAD"]["lease_owner"] is None
    assert tasks["TASK-STUCK-DEAD"]["lease_until"] is None
    assert tasks["TASK-STUCK-DEAD"]["error_type"] == "stuck_no_heartbeat"
    assert tasks["TASK-STUCK-DEAD"]["attempt_history"][-1]["status"] == "dead_letter_stuck"
    assert dead == ["TASK-STUCK-DEAD"]
    assert saved == [("TASK-STUCK-DEAD", control.STATE_DEAD)]


def test_legacy_remote_implementation_capability_can_route_to_supported_runner():
    control = load_control()
    task = control.normalize_task(
        {
            "task_id": "LEGACY-REMOTE-IMPL",
            "kind": "generic_implementation",
            "required_capability": "remote_implementation_runner_ready",
            "permission_pack": "implementation",
        }
    )

    implementation_permissions = ["git_push", "network", "read_repo", "run_tests", "write_artifacts", "write_worktree"]

    assert control.compatible(task, "main", ["implementation"], permissions=implementation_permissions) is True
    assert control.compatible(task, "review", ["review"], permissions=implementation_permissions) is False
    assert control.compact_task(task)["runner_kind"] == "generic_implementation"


def test_legacy_remote_implementation_kind_is_classified_without_queue_mutation():
    control = load_control()
    agent_host = load_agent_host()
    task = control.normalize_task(
        {
            "task_id": "LEGACY-KIND",
            "kind": "remote_implementation_runner_ready",
            "required_capability": "implementation",
            "permission_pack": "implementation",
        }
    )

    assert task["kind"] == "remote_implementation_runner_ready"
    assert task["state"] == control.STATE_QUEUED
    assert control.runtime_runner_kind(task) == "generic_implementation"
    assert agent_host.RUNTIME_KIND_COMPAT["remote_implementation_runner_ready"] == "generic_implementation"
    assert "remote_implementation_runner_ready" in agent_host.DEFAULT_AGENT_CAPABILITIES


def test_agent_host_detects_runner_committed_and_pushed_changes(tmp_path):
    agent_host = load_agent_host()
    origin = tmp_path / "origin.git"
    repo = tmp_path / "repo"

    subprocess.run(["git", "init", "--bare", str(origin)], check=True)
    subprocess.run(["git", "clone", str(origin), str(repo)], check=True)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True)
    subprocess.run(["git", "push", "-u", "origin", "HEAD:main"], cwd=repo, check=True)

    branch = "agent/test-runner-commit"
    subprocess.run(["git", "checkout", "-B", branch, "origin/main"], cwd=repo, check=True)
    base_commit = agent_host.git_output(["rev-parse", "HEAD"], repo)
    (repo / "docs.md").write_text("runner artifact\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "runner commit"], cwd=repo, check=True)
    runner_commit = agent_host.git_output(["rev-parse", "HEAD"], repo)
    subprocess.run(["git", "push", "-u", "origin", branch], cwd=repo, check=True)

    assert subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).splitlines() == []
    assert agent_host.git_diff_paths(repo, base_commit, runner_commit) == ["docs.md"]
    assert agent_host.git_remote_branch_matches(repo, branch, runner_commit) is True
