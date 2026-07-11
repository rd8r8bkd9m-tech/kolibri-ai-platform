import importlib.util
import http.client
import io
import json
import threading
from pathlib import Path
from datetime import datetime, timedelta, timezone


ROOT = Path(__file__).resolve().parents[1]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_dispatcher_exposes_required_commands():
    dispatch = (ROOT / "ops" / "kolibri-dispatch").read_text(encoding="utf-8")
    for command in ["doctor", "nodes", "submit", "status", "collect", "cancel", "drain"]:
        assert f'"{command}"' in dispatch


def test_control_plane_states_are_declared():
    control = load_module(ROOT / "ops" / "factory_control.py")
    assert {
        control.STATE_QUEUED,
        control.STATE_LEASED,
        control.STATE_RUNNING,
        control.STATE_WAITING_REVIEW,
        control.STATE_REVIEW,
        control.STATE_COMPLETED,
        control.STATE_FAILED,
        control.STATE_CANCELLED,
        control.STATE_RETRY,
        control.STATE_DEAD,
    } == {
        "queued",
        "leased",
        "running",
        "waiting_review",
        "review",
        "completed",
        "failed",
        "cancelled",
        "retry_scheduled",
        "dead_letter",
    }


def test_control_plane_classifies_stale_online_heartbeat_as_stale():
    control = load_module(ROOT / "ops" / "factory_control.py")
    now = datetime.now(timezone.utc)
    node = control.classify_node_freshness(
        {
            "node_id": "worker-1",
            "health": "online",
            "heartbeat_at": (now - timedelta(seconds=600)).isoformat(),
        },
        now.timestamp(),
    )

    assert node["reported_health"] == "online"
    assert node["freshness"] == "stale"
    assert node["health"] == "stale"
    assert node["heartbeat_age_seconds"] == 600
    assert control.node_health_counts([node]) == {"fresh": 0, "degraded": 0, "stale": 1, "online": 0, "total": 1}


def test_control_plane_counts_fresh_degraded_and_stale_nodes():
    control = load_module(ROOT / "ops" / "factory_control.py")
    now = datetime.now(timezone.utc)
    nodes = [
        control.classify_node_freshness({"node_id": "fresh", "health": "online", "heartbeat_at": (now - timedelta(seconds=5)).isoformat()}, now.timestamp()),
        control.classify_node_freshness({"node_id": "degraded", "health": "online", "heartbeat_at": (now - timedelta(seconds=45)).isoformat()}, now.timestamp()),
        control.classify_node_freshness({"node_id": "stale", "health": "online", "heartbeat_at": (now - timedelta(seconds=120)).isoformat()}, now.timestamp()),
    ]

    assert [node["freshness"] for node in nodes] == ["fresh", "degraded", "stale"]
    assert control.node_health_counts(nodes) == {"fresh": 1, "degraded": 1, "stale": 1, "online": 1, "total": 3}


def test_agent_host_supports_required_task_kinds():
    agent = (ROOT / "ops" / "agent_host.py").read_text(encoding="utf-8")
    assert "impl_factory_smoke" in agent
    assert "impl_retry_error_clearance" in agent
    assert "telegram_chat_response" in agent
    assert "orchestrator_chat_response" in agent
    assert "telegram_image_generation" in agent
    assert "review_pr" in agent
    assert "read_only_probe" in agent
    memory = (ROOT / "ops" / "orchestrator_memory.py").read_text(encoding="utf-8")
    assert "last_work_request" in memory
    assert "open_expectations" in memory



def test_orchestrator_roster_has_human_role_cards():
    roster = load_module(ROOT / "ops" / "orchestrator_roster.py")
    assert roster.ORCHESTRATOR_CARD["name"] == "Директор"
    engineer = roster.node_card({"node_id": "dynamic-a", "health": "online", "capabilities": ["implementation"]})
    reviewer = roster.node_card({"node_id": "dynamic-b", "health": "online", "capabilities": ["review"]})
    assert engineer["name"] == "Инженер"
    assert reviewer["name"] == "Ревьюер"
    assert engineer["health"] == "online"
    source = (ROOT / "ops" / "orchestrator_roster.py").read_text(encoding="utf-8")
    assert "NODE_CARDS" not in source


def test_control_plane_runner_compatibility_filters_blocked_and_avoided_nodes():
    control = load_module(ROOT / "ops" / "factory_control.py")
    task = control.normalize_task({
        "kind": "owner_remote_task",
        "runner": "mimo",
        "required_capability": "generic_implementation",
        "avoid_nodes": ["avoid-me"],
    })

    assert control.compatible(
        task,
        "healthy",
        ["generic_implementation", "runner:mimo"],
        {"runners": {"mimo": {"status": "available"}}},
    ) is True
    assert control.compatible(
        task,
        "missing-runner-cap",
        ["generic_implementation"],
        {"runners": {"mimo": {"status": "available"}}},
    ) is False
    assert control.compatible(
        task,
        "blocked",
        ["generic_implementation", "runner:mimo"],
        {"runners": {"mimo": {"status": "blocked"}}},
    ) is False
    assert control.compatible(
        task,
        "avoid-me",
        ["generic_implementation", "runner:mimo"],
        {"runners": {"mimo": {"status": "available"}}},
    ) is False


def test_orchestrator_chat_runner_gate_rejects_node_without_requested_runner():
    control = load_module(ROOT / "ops" / "factory_control.py")
    task = control.normalize_task({"kind": "orchestrator_chat_response", "runner": "mimo"})

    assert control.compatible(
        task,
        "mimo-node",
        ["orchestrator", "runner:mimo"],
        {"runners": {"mimo": {"status": "available"}}},
    ) is True
    assert control.compatible(task, "generic-node", ["orchestrator"], {}) is False


def test_policy_blocked_runner_is_quarantined_on_the_lease_node(monkeypatch):
    control = load_module(ROOT / "ops" / "factory_control.py")
    state = {
        "node_id": "home",
        "runners": {"mimo": {"status": "available"}},
    }

    monkeypatch.setattr(control, "get_json", lambda *_args, **_kwargs: dict(state))

    def save(_key, value):
        state.clear()
        state.update(value)

    monkeypatch.setattr(control, "set_json", save)
    task = {
        "lease_owner": "home:agent-host-home",
        "envelope": {"runner": "mimo"},
    }

    control.mark_node_runner_failure(
        task,
        {"error_type": "runner_policy_blocked", "result": {"runner": "mimo"}},
    )

    assert state["runners"]["mimo"]["status"] == "blocked"
    assert state["runners"]["mimo"]["error_type"] == "runner_policy_blocked"


def test_control_plane_rejects_missing_or_mismatched_result_runner():
    control = load_module(ROOT / "ops" / "factory_control.py")
    task = {"envelope": {"runner": "codex"}}

    assert control.runner_result_binding_error(task, {"result": {}}) == {
        "error": "runner_result_mismatch",
        "requested_runner": "codex",
        "result_runner": "missing",
    }
    assert control.runner_result_binding_error(task, {"result": {"runner": "mimo"}}) == {
        "error": "runner_result_mismatch",
        "requested_runner": "codex",
        "result_runner": "mimo",
    }
    assert control.runner_result_binding_error(task, {"result": {"runner": "codex"}}) is None


def test_redis_connection_pool_reuses_a_healthy_connection(monkeypatch):
    control = load_module(ROOT / "ops" / "factory_control.py")

    class FakeSocket:
        def __init__(self):
            self.reader = io.BytesIO(b"+PONG\r\n+OK\r\n")
            self.closed = False

        def sendall(self, _payload):
            if self.closed:
                raise ConnectionResetError("closed")

        def close(self):
            self.closed = True

    created = []

    def connect():
        sock = FakeSocket()
        created.append(sock)
        return sock, sock.reader

    client = control.Redis(pool_size=2)
    monkeypatch.setattr(client, "_connect", connect)
    assert client.command("PING") == "PONG"
    assert client.command("SET", "a", "b") == "OK"
    assert len(created) == 1


def test_lease_maintenance_compatibility_routes(monkeypatch):
    control = load_module(ROOT / "ops" / "factory_control.py")
    monkeypatch.setattr(control, "requeue_expired_leases", lambda limit=None: {"expired": 0, "scan_limit": limit})
    monkeypatch.setattr(
        control,
        "sweep_stuck_tasks",
        lambda limit=None, stale_after=None: {"stuck": 0, "scan_limit": limit, "stale_after_seconds": stale_after},
    )
    monkeypatch.setattr(
        control,
        "queue_maintenance_diagnostics",
        lambda stale_after=None: {"redis": "PONG", "expired_leases": 0, "stale_after_seconds": stale_after or 3600},
    )
    monkeypatch.setattr(
        control,
        "failure_task_listing",
        lambda error_type, limit: {"error_type": error_type, "total": 0, "returned": 0, "tasks": [], "limit": limit},
    )

    server = control.ThreadingHTTPServer(("127.0.0.1", 0), control.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address

        def request(method, path, body=None):
            connection = http.client.HTTPConnection(host, port, timeout=2)
            payload = None if body is None else json.dumps(body)
            connection.request(method, path, body=payload, headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            data = json.loads(response.read().decode("utf-8"))
            connection.close()
            return response.status, data

        status, payload = request("POST", "/v1/tasks/reap-expired", {"limit": 17})
        assert status == 200
        assert payload == {"expired": 0, "scan_limit": 17}

        status, payload = request(
            "POST",
            "/v1/tasks/sweep-stuck",
            {"limit": 19, "stale_after_seconds": 900},
        )
        assert status == 200
        assert payload == {"stuck": 0, "scan_limit": 19, "stale_after_seconds": 900}

        status, payload = request("GET", "/v1/tasks/queue/diagnostics?stale_after_seconds=600")
        assert status == 200
        assert payload["redis"] == "PONG"
        assert payload["stale_after_seconds"] == 600

        status, payload = request("GET", "/v1/tasks/failures?error_type=deliverable_gate_failed&limit=25")
        assert status == 200
        assert payload["error_type"] == "deliverable_gate_failed"
        assert payload["limit"] == 25
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_queue_maintenance_diagnostics_distinguishes_zero_from_missing_heartbeat(monkeypatch):
    control = load_module(ROOT / "ops" / "factory_control.py")
    now = datetime.now(timezone.utc)
    tasks = {
        "fresh": {
            "task_id": "fresh",
            "state": control.STATE_RUNNING,
            "lease_until": now.timestamp() + 60,
            "heartbeat_at": now.isoformat(),
        },
        "missing": {
            "task_id": "missing",
            "state": control.STATE_RUNNING,
            "lease_until": now.timestamp() + 60,
            "heartbeat_at": None,
        },
    }
    monkeypatch.setattr(control, "active_lease_ids", lambda: sorted(tasks))
    monkeypatch.setattr(control, "all_task_ids", lambda: sorted(tasks))
    monkeypatch.setattr(control, "queue_ids", lambda: [])
    monkeypatch.setattr(control, "load_task", lambda task_id: dict(tasks[task_id]))

    diagnostics = control.queue_maintenance_diagnostics(stale_after=60)

    assert diagnostics["redis"] == "PONG"
    assert diagnostics["task_total"] == 2
    assert diagnostics["lease_index_total"] == 2
    assert diagnostics["expired_leases"] == 0
    assert diagnostics["stuck_heartbeat_tasks"] == 0
    assert diagnostics["stale_after_seconds"] == 60
