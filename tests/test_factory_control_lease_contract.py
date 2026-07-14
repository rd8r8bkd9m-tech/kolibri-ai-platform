import importlib.util
import json
import threading
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_control():
    spec = importlib.util.spec_from_file_location("factory_control_lease_contract", ROOT / "ops" / "factory_control.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeRedis:
    def __init__(self):
        self.kv = {}
        self.sets = defaultdict(set)
        self.lists = defaultdict(list)

    def command(self, *parts):
        action = str(parts[0]).upper()
        if action == "PING":
            return "PONG"
        if action == "GET":
            return self.kv.get(parts[1])
        if action == "SET":
            self.kv[parts[1]] = parts[2]
            return "OK"
        if action == "MGET":
            return [self.kv.get(item) for item in parts[1:]]
        if action == "SADD":
            before = len(self.sets[parts[1]])
            self.sets[parts[1]].update(str(value) for value in parts[2:])
            return len(self.sets[parts[1]]) - before
        if action == "SMEMBERS":
            return sorted(self.sets[parts[1]])
        if action == "RPUSH":
            self.lists[parts[1]].extend(str(value) for value in parts[2:])
            return len(self.lists[parts[1]])
        if action == "LRANGE":
            values = self.lists[parts[1]]
            return values[int(parts[2]):] if int(parts[3]) == -1 else values[int(parts[2]):int(parts[3]) + 1]
        if action == "LREM":
            values = self.lists[parts[1]]
            target = str(parts[3])
            self.lists[parts[1]] = [value for value in values if value != target]
            return len(values) - len(self.lists[parts[1]])
        raise AssertionError(parts)


def post_json(base_url, path, payload):
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, json.loads(raw) if raw else None


def get_json(base_url, path):
    with urllib.request.urlopen(f"{base_url}{path}", timeout=2) as response:
        return response.status, json.loads(response.read())


def test_issue_task_lease_is_unique_monotonic_and_release_bound(monkeypatch):
    control = load_control()
    monkeypatch.setattr(control, "RUNTIME_RELEASE_ID", "control-release-1")
    monkeypatch.setattr(control, "now_ts", lambda: 1_800_000_000.0)
    task = control.normalize_task({"task_id": "LEASE-1"})

    first = control.issue_task_lease(task, node_id="home", agent_id="agent-01", executor_release_id="worker-release-1")
    second = control.issue_task_lease(dict(first, state=control.STATE_QUEUED), node_id="home", agent_id="agent-01", executor_release_id="worker-release-1")

    assert len(first["lease_id"]) == 32
    assert first["lease_id"] != second["lease_id"]
    assert first["attempt_id"] == "LEASE-1-attempt-1"
    assert second["attempt_id"] == "LEASE-1-attempt-2"
    assert (first["fencing_token"], second["fencing_token"]) == (1, 2)
    assert first["control_release_id"] == "control-release-1"
    assert first["executor_release_id"] == "worker-release-1"


def test_mutations_require_matching_fence_owner_and_release(monkeypatch):
    control = load_control()
    task = control.issue_task_lease(
        control.normalize_task({"task_id": "LEASE-2"}),
        node_id="home",
        agent_id="agent-01",
        executor_release_id="worker-release-2",
    )
    body = {
        "attempt_id": task["attempt_id"],
        "lease_id": task["lease_id"],
        "fencing_token": task["fencing_token"],
        "node_id": "home",
        "agent_id": "agent-01",
        "runtime_release_id": "worker-release-2",
    }

    assert control.validate_task_mutation_fence(task, body) is None
    assert control.validate_task_mutation_fence(task, {}) == "lease_fence_fields_required"
    assert control.validate_task_mutation_fence(task, dict(body, lease_id="stale")) == "stale_lease_id"
    assert control.validate_task_mutation_fence(task, dict(body, node_id="other")) == "lease_node_mismatch"
    assert control.validate_task_mutation_fence(task, dict(body, runtime_release_id="other")) == "executor_release_mismatch"

    task["state"] = control.STATE_COMPLETED
    monkeypatch.setattr(control, "utc_now", lambda: "2027-01-15T08:01:00+00:00")
    control.preserve_terminal_lease_evidence(task)
    frozen = dict(task["terminal_lease_evidence"])
    control.preserve_terminal_lease_evidence(task)
    assert task["terminal_lease_evidence"] == frozen
    assert frozen["executor_release_id"] == "worker-release-2"


def test_http_rejects_unfenced_and_stale_completion_and_replays_matching(monkeypatch):
    control = load_control()
    fake = FakeRedis()
    monkeypatch.setattr(control, "redis", fake)
    server = control.ThreadingHTTPServer(("127.0.0.1", 0), control.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        control.create_task({"task_id": "HTTP-LEASE-1", "required_capability": "generic_implementation"})
        status, leased = post_json(base_url, "/v1/tasks/lease", {
            "node_id": "agent-01",
            "agent_id": "agent-01",
            "capabilities": ["generic_implementation"],
            "runtime_release_id": "worker-release-http",
        })
        assert status == 200
        assert json.loads(fake.kv[control.task_key("HTTP-LEASE-1")])["lease_id"] == leased["lease_id"]

        status, error = post_json(base_url, "/v1/tasks/HTTP-LEASE-1/heartbeat", {})
        assert (status, error["reason"]) == (409, "lease_fence_fields_required")

        fence = {
            "attempt_id": leased["attempt_id"],
            "lease_id": leased["lease_id"],
            "fencing_token": leased["fencing_token"],
            "node_id": "agent-01",
            "agent_id": "agent-01",
            "runtime_release_id": "worker-release-http",
        }
        status, running = post_json(base_url, "/v1/tasks/HTTP-LEASE-1/heartbeat", fence)
        assert status == 200 and running["state"] == control.STATE_RUNNING

        status, error = post_json(base_url, "/v1/tasks/HTTP-LEASE-1/complete", {**fence, "lease_id": "stale"})
        assert (status, error["reason"]) == (409, "stale_lease_id")

        completion = {**fence, "result": {"status": "completed", "text": "verified"}}
        status, payload = post_json(base_url, "/v1/tasks/HTTP-LEASE-1/complete", completion)
        assert status == 200
        assert payload["task"]["terminal_lease_evidence"]["lease_id"] == leased["lease_id"]
        status, replay = post_json(base_url, "/v1/tasks/HTTP-LEASE-1/complete", completion)
        assert status == 200
        assert replay["task"]["result"] == payload["task"]["result"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_rejects_serialized_tool_call_from_response_only_runner(monkeypatch):
    control = load_control()
    fake = FakeRedis()
    monkeypatch.setattr(control, "redis", fake)
    server = control.ThreadingHTTPServer(("127.0.0.1", 0), control.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        control.create_task({"task_id": "HTTP-RESPONSE-ONLY-1", "required_capability": "generic_implementation"})
        status, leased = post_json(base_url, "/v1/tasks/lease", {
            "node_id": "agent-01",
            "agent_id": "agent-01",
            "capabilities": ["generic_implementation"],
            "runtime_release_id": "worker-release-http",
        })
        assert status == 200
        fence = {
            "attempt_id": leased["attempt_id"],
            "lease_id": leased["lease_id"],
            "fencing_token": leased["fencing_token"],
            "node_id": "agent-01",
            "agent_id": "agent-01",
            "runtime_release_id": "worker-release-http",
        }
        result = {
            "status": "completed",
            "runner_contract": {"execution_scope": "response_only"},
            "response": "Checking production. <tool_call>{\"name\":\"shell\"}</tool_call>",
        }
        status, error = post_json(base_url, "/v1/tasks/HTTP-RESPONSE-ONLY-1/complete", {**fence, "result": result})
        assert status == 422
        assert error["error"] == "unexecuted_tool_call_output"
        stored = json.loads(fake.kv[control.task_key("HTTP-RESPONSE-ONLY-1")])
        assert stored["state"] == control.STATE_LEASED
        assert "truth_gate" not in stored
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_health_and_node_status_expose_truthful_release_identity(monkeypatch):
    control = load_control()
    fake = FakeRedis()
    monkeypatch.setattr(control, "redis", fake)
    monkeypatch.setattr(control, "RUNTIME_RELEASE_ID", "control-release-status")
    server = control.ThreadingHTTPServer(("127.0.0.1", 0), control.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, health = get_json(base_url, "/v1/health")
        data = health["data"]
        assert status == 200
        assert data["authority"] == "home"
        assert data["runtime_release_id"] == "control-release-status"
        assert data["status_semantics"]["active"] != data["status_semantics"]["online"]

        status, node = post_json(base_url, "/v1/nodes/register", {
            "node_id": "agent-status",
            "agent_id": "agent-host-status",
            "runtime_release_id": "worker-release-status",
        })
        assert status == 200
        assert node["execution_status"] == "idle"
        assert node["runtime_release_id"] == "worker-release-status"

        status, node = post_json(base_url, "/v1/nodes/agent-status/heartbeat", {
            "active_task": "REAL-TASK-1",
            "runtime_release_id": "worker-release-status",
        })
        assert status == 200
        assert node["execution_status"] == "active"
        assert node["active_task"] == "REAL-TASK-1"

        status, node = post_json(base_url, "/v1/nodes/agent-status/heartbeat", {
            "active_task": None,
            "runtime_release_id": "worker-release-status",
        })
        assert status == 200
        assert node["execution_status"] == "idle"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
