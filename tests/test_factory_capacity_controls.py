import argparse
import concurrent.futures
import importlib.util
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_control():
    spec = importlib.util.spec_from_file_location("factory_control", ROOT / "ops" / "factory_control.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_agent_host():
    spec = importlib.util.spec_from_file_location("agent_host", ROOT / "ops" / "agent_host.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class InMemoryRedis:
    def __init__(self):
        self.values = {}
        self.sets = {}
        self.lists = {}
        self.commands = []
        self.lock = threading.RLock()

    def command(self, *parts):
        with self.lock:
            self.commands.append(parts)
            op = str(parts[0]).upper()
            if op == "GET":
                return self.values.get(parts[1])
            if op == "SET":
                key, value = parts[1], parts[2]
                flags = {str(part).upper() for part in parts[3:]}
                if "NX" in flags and key in self.values:
                    return None
                self.values[key] = value
                return "OK"
            if op == "SADD":
                before = len(self.sets.setdefault(parts[1], set()))
                self.sets[parts[1]].add(parts[2])
                return int(len(self.sets[parts[1]]) > before)
            if op == "SREM":
                items = self.sets.setdefault(parts[1], set())
                if parts[2] not in items:
                    return 0
                items.remove(parts[2])
                return 1
            if op == "SMEMBERS":
                return list(self.sets.get(parts[1], set()))
            if op == "SRANDMEMBER":
                items = sorted(self.sets.get(parts[1], set()))
                if len(parts) == 2:
                    return items[0] if items else None
                return items[:max(0, int(parts[2]))]
            if op == "RPUSH":
                self.lists.setdefault(parts[1], []).append(parts[2])
                return len(self.lists[parts[1]])
            if op == "LPOP":
                items = self.lists.setdefault(parts[1], [])
                return items.pop(0) if items else None
            if op == "LREM":
                list_key, count, value = parts[1], int(parts[2]), parts[3]
                items = self.lists.setdefault(list_key, [])
                removed = 0
                kept = []
                for item in items:
                    if item == value and (count == 0 or removed < abs(count)):
                        removed += 1
                        continue
                    kept.append(item)
                self.lists[list_key] = kept
                return removed
            if op == "LRANGE":
                items = self.lists.get(parts[1], [])
                start, stop = int(parts[2]), int(parts[3])
                if stop == -1:
                    return list(items[start:])
                return list(items[start:stop + 1])
            if op == "PING":
                return "PONG"
            raise AssertionError(f"unsupported redis command: {parts}")


def test_1000_logical_lease_polls_do_not_spawn_processes_or_scan_unbounded_queue(monkeypatch):
    control = load_control()
    fake = InMemoryRedis()
    monkeypatch.setattr(control, "redis", fake)
    monkeypatch.setattr(control, "LEASE_QUEUE_SCAN_LIMIT", 8)

    for index in range(1200):
        control.create_task({
            "task_id": f"CAP-{index}",
            "idempotency_key": f"cap-{index}",
            "kind": "read_only_probe",
            "required_capability": "read_only_probe",
        })

    leased = []
    for index in range(1000):
        node_id = f"logical-{index}"
        task = control.lease_next_task(
            node_id,
            f"agent-{index}",
            ["read_only_probe"],
            {"node_id": node_id, "capabilities": ["read_only_probe"]},
        )
        assert task is not None
        leased.append(task["task_id"])

    assert len(set(leased)) == 1000
    assert len(fake.lists[control.key("queue")]) == 200
    assert not any(command[0] in {"Popen", "THREAD"} for command in fake.commands)
    lpop_count = sum(1 for command in fake.commands if command[0] == "LPOP")
    assert lpop_count == 1000


def test_lease_recovers_persisted_queued_task_when_queue_index_loses_one_entry(monkeypatch):
    control = load_control()
    fake = InMemoryRedis()
    monkeypatch.setattr(control, "redis", fake)
    monkeypatch.setattr(control, "LEASE_QUEUE_SCAN_LIMIT", 8)

    for index in range(10):
        control.create_task({
            "task_id": f"STRICT-{index}",
            "idempotency_key": f"strict-{index}",
            "kind": "read_only_probe",
            "required_capability": "read_only_probe",
        })
    fake.lists[control.key("queue")].remove("STRICT-9")

    leased = []
    for index in range(10):
        task = control.lease_next_task(
            f"logical-{index}",
            f"agent-{index}",
            ["read_only_probe"],
            {"node_id": f"logical-{index}", "capabilities": ["read_only_probe"]},
        )
        assert task is not None
        leased.append(task["task_id"])

    assert len(set(leased)) == 10
    assert "STRICT-9" in leased


def test_concurrent_empty_lease_polls_return_no_task_without_historical_scan(monkeypatch):
    control = load_control()
    fake = InMemoryRedis()
    monkeypatch.setattr(control, "redis", fake)
    monkeypatch.setattr(control, "LEASE_QUEUE_SCAN_LIMIT", 8)

    for index in range(1000):
        task = control.normalize_task({
            "task_id": f"HIST-{index}",
            "idempotency_key": f"hist-{index}",
        })
        task["state"] = control.STATE_COMPLETED
        control.save_task(task)
    fake.commands.clear()

    def empty_poll(index):
        task = control.lease_next_task(
            f"logical-empty-{index}",
            f"agent-empty-{index}",
            ["read_only_probe"],
            {"node_id": f"logical-empty-{index}", "capabilities": ["read_only_probe"]},
        )
        return control.lease_no_task_response() if task is None else task

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        envelopes = list(pool.map(empty_poll, range(64)))
    assert control.maybe_requeue_expired_leases() == 0

    assert all(envelope["status"] == "no_task" for envelope in envelopes)
    assert all(envelope["task"] is None for envelope in envelopes)
    assert not any(command == ("SMEMBERS", control.key("task_ids")) for command in fake.commands)
    assert not any(command[0] == "LRANGE" for command in fake.commands)


def test_lease_reaper_is_lock_gated_and_batched(monkeypatch):
    control = load_control()
    fake = InMemoryRedis()
    monkeypatch.setattr(control, "redis", fake)
    monkeypatch.setattr(control, "LEASE_REAPER_BATCH_LIMIT", 10)

    for index in range(25):
        task = control.normalize_task({
            "task_id": f"EXP-{index}",
            "idempotency_key": f"exp-{index}",
        })
        task["state"] = control.STATE_RUNNING
        task["attempt"] = 1
        task["lease_until"] = 1
        control.save_task(task)

    assert control.maybe_requeue_expired_leases() == 10
    assert control.maybe_requeue_expired_leases() == 0
    loaded = [control.load_task(f"EXP-{index}") for index in range(25)]
    assert sum(1 for task in loaded if task["state"] == control.STATE_QUEUED) == 10


class PONGReader:
    def read(self, size):
        assert size == 1
        return b"+"

    def readline(self):
        return b"PONG\r\n"

    def close(self):
        pass


class PONGSocket:
    def __init__(self):
        self.sent = []

    def settimeout(self, timeout):
        self.timeout = timeout

    def makefile(self, mode):
        assert mode == "rb"
        return PONGReader()

    def sendall(self, payload):
        self.sent.append(payload)

    def close(self):
        pass


def test_redis_client_reuses_one_socket_per_thread(monkeypatch):
    control = load_control()
    sockets = []

    def fake_create_connection(address, timeout):
        del address, timeout
        sock = PONGSocket()
        sockets.append(sock)
        return sock

    monkeypatch.setattr(control.socket, "create_connection", fake_create_connection)
    client = control.Redis()
    assert client.command("PING") == "PONG"
    assert client.command("PING") == "PONG"

    assert len(sockets) == 1
    assert len(sockets[0].sent) == 2


def test_lease_empty_poll_returns_structured_no_task_envelope():
    control = load_control()
    envelope = control.lease_no_task_response()

    assert envelope["status"] == "no_task"
    assert envelope["task"] is None
    assert envelope["reason"] == "queue_empty"
    assert envelope["retry_after_seconds"] >= 0
    assert envelope["lease_queue_scan_limit"] == control.LEASE_QUEUE_SCAN_LIMIT


def test_agent_host_treats_structured_no_task_lease_as_idle_poll(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    monkeypatch.setattr(agent_host.AgentHost, "detect_runner_status", lambda self: {})

    args = argparse.Namespace(
        control_url="http://127.0.0.1:9101",
        control_urls="http://127.0.0.1:9101",
        node_id="logical-empty",
        agent_id="agent-host-empty",
        capabilities="read_only_probe",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
        lease_idle_min=1.0,
        lease_idle_max=15.0,
        lease_empty_backoff_factor=1.35,
        lease_error_backoff=5.0,
    )
    host = agent_host.AgentHost(args)
    monkeypatch.setattr(host, "post", lambda path, body: {"status": "no_task", "task": None})

    assert host.lease() is None


class BrokenPipeWriter:
    def write(self, payload):
        del payload
        raise BrokenPipeError()


class BrokenPipeHandler:
    wfile = BrokenPipeWriter()

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        del name, value

    def end_headers(self):
        pass


def test_response_write_broken_pipe_is_client_disconnect_not_500_loop():
    control = load_control()

    try:
        control.response(BrokenPipeHandler(), 200, {"status": "ok"})
    except Exception as exc:
        assert isinstance(exc, control.ClientDisconnected)
    else:
        raise AssertionError("broken pipe must be classified as client disconnect")


def test_factory_control_does_not_install_runtime_503_worker_gate():
    control = load_control()

    assert not hasattr(control, "BoundedThreadingHTTPServer")
    assert not hasattr(control, "lease_overload_response")


def test_lease_canary_classifier_fails_any_lease_5xx():
    control = load_control()

    for status_code in (500, 502, 503, 599):
        classified = control.classify_lease_canary_response(status_code, {"status": "no_task"})
        assert classified["status"] == "failed"
        assert classified["reason"] == "lease_5xx"


def test_lease_canary_classifier_fails_transport_status_zero():
    control = load_control()

    classified = control.classify_lease_canary_response(0, None)

    assert classified["status"] == "failed"
    assert classified["reason"] == "lease_transport_error"


def test_lease_canary_stage_classifier_fails_under_leasing_and_empty_poll_transport_errors():
    control = load_control()

    under_leased = control.classify_lease_canary_stage(stage=1000, created_tasks=1000, leased_tasks=999)
    assert under_leased["status"] == "failed"
    assert under_leased["reason"] == "lease_under_completion"
    assert under_leased["missing_leases"] == 1

    empty_poll_transport = control.classify_lease_canary_stage(
        stage=500,
        created_tasks=500,
        leased_tasks=500,
        empty_poll_statuses=[200, 0, 200],
    )
    assert empty_poll_transport["status"] == "failed"
    assert empty_poll_transport["reason"] == "empty_poll_transport_error"
    assert empty_poll_transport["transport_error_count"] == 1


def test_agent_host_poll_jitter_spreads_1000_logical_hosts_without_process_spawn(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    monkeypatch.setattr(agent_host.AgentHost, "detect_runner_status", lambda self: {})

    sleeps = []
    for index in range(1000):
        args = argparse.Namespace(
            control_url="http://127.0.0.1:9101",
            control_urls="http://127.0.0.1:9101",
            node_id=f"logical-{index}",
            agent_id=f"agent-host-{index}",
            capabilities="read_only_probe",
            repo_url="https://example.invalid/repo.git",
            work_root=str(tmp_path / "work"),
            artifact_root=str(tmp_path / "artifacts"),
            heartbeat_interval=10,
            lease_refresh=20,
            max_inflight=1,
            lease_idle_min=1.0,
            lease_idle_max=15.0,
            lease_empty_backoff_factor=1.35,
            lease_error_backoff=5.0,
        )
        host = agent_host.AgentHost(args)
        assert host.max_inflight == 1
        sleeps.append(round(host.idle_poll_sleep(empty_polls=8), 3))

    assert len(set(sleeps)) > 900
    assert min(sleeps) >= 1.0
    assert max(sleeps) <= 15.0
