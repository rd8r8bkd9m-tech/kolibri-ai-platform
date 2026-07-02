import argparse
import importlib.util
import json
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

    def command(self, *parts):
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
            self.sets.setdefault(parts[1], set()).add(parts[2])
            return 1
        if op == "SMEMBERS":
            return list(self.sets.get(parts[1], set()))
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


class CaptureRequest:
    def __init__(self, request_head=b""):
        self.payload = b""
        self.request_head = request_head

    def sendall(self, payload):
        self.payload += payload

    def recv(self, size, flags):
        del flags
        return self.request_head[:size]


def test_overload_response_is_bounded_structured_json():
    control = load_control()
    request = CaptureRequest(b"GET /v1/health HTTP/1.1\r\nHost: test\r\n\r\n")

    control.BoundedThreadingHTTPServer._send_overloaded(request)
    head, body = request.payload.split(b"\r\n\r\n", 1)

    assert b"503 Service Unavailable" in head
    assert b"Content-Type: application/json" in head
    payload = json.loads(body.decode("utf-8"))
    assert payload["status"] == "overloaded"
    assert payload["task"] is None
    assert payload["error"] == "control_plane_overloaded"
    assert payload["retry_after_seconds"] >= 0


def test_lease_overload_response_is_http_200_idle_backoff_envelope():
    control = load_control()
    request = CaptureRequest(b"POST /v1/tasks/lease HTTP/1.1\r\nHost: test\r\n\r\n")

    control.BoundedThreadingHTTPServer._send_overloaded(request)
    head, body = request.payload.split(b"\r\n\r\n", 1)

    assert b"200 OK" in head
    assert b"503" not in head
    payload = json.loads(body.decode("utf-8"))
    assert payload["status"] == "overloaded"
    assert payload["task"] is None
    assert payload["error"] == "control_plane_overloaded"
    assert payload["retry_after_seconds"] == control.LEASE_OVERLOAD_RETRY_AFTER


def test_lease_canary_classifier_fails_any_lease_5xx():
    control = load_control()

    for status_code in (500, 502, 503, 599):
        classified = control.classify_lease_canary_response(status_code, {"status": "no_task"})
        assert classified["status"] == "failed"
        assert classified["reason"] == "lease_5xx"


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
