import importlib.util
import json
import threading
from pathlib import Path
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer


ROOT = Path(__file__).resolve().parents[1]


def load_control():
    spec = importlib.util.spec_from_file_location("factory_control", ROOT / "ops" / "factory_control.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.sets = {}
        self.lists = {}

    def command(self, name, *args):
        command = name.upper()
        if command == "PING":
            return "PONG"
        if command == "GET":
            return self.values.get(args[0])
        if command == "SET":
            self.values[args[0]] = args[1]
            return "OK"
        if command == "DEL":
            return 1 if self.values.pop(args[0], None) is not None else 0
        if command == "SADD":
            self.sets.setdefault(args[0], set()).add(args[1])
            return 1
        if command == "SMEMBERS":
            return sorted(self.sets.get(args[0], set()))
        if command == "RPUSH":
            self.lists.setdefault(args[0], []).append(args[1])
            return len(self.lists[args[0]])
        if command == "LRANGE":
            values = self.lists.get(args[0], [])
            start = int(args[1])
            stop = int(args[2])
            if stop == -1:
                return values[start:]
            return values[start : stop + 1]
        if command == "LREM":
            values = self.lists.get(args[0], [])
            target = args[2]
            self.lists[args[0]] = [value for value in values if value != target]
            return len(values) - len(self.lists[args[0]])
        raise AssertionError(f"unsupported redis command: {command}")


class ControlServer:
    def __init__(self, control):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), control.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, method, path, body=None):
        payload = b""
        headers = {}
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        host, port = self.server.server_address
        conn = HTTPConnection(host, port, timeout=5)
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        conn.close()
        return response.status, data


def test_prompt3_required_endpoint_surface_is_declared():
    control = load_control()
    assert control.PROMPT3_REQUIRED_ENDPOINTS == {
        "GET": [
            "/v1/health",
            "/v1/fleet/nodes",
            "/v1/fleet/topology",
            "/v1/fleet/route",
            "/v1/fleet/capabilities",
            "/v1/models",
            "/v1/agents/status/{task_id}",
            "/v1/agents/artifacts/{task_id}",
        ],
        "POST": [
            "/v1/responses",
            "/v1/chat/completions",
            "/v1/agents/tasks",
            "/v1/agents/cancel/{task_id}",
            "/v1/admin/exec",
            "/v1/admin/service",
            "/v1/admin/git",
            "/v1/admin/bootstrap-node",
            "/v1/admin/rotate-keys",
        ],
    }


def test_fleet_aliases_return_catalog_topology_capabilities_and_routes():
    control = load_control()
    registered = [
        {"node_id": "9fts", "health": "online", "capabilities": ["implementation", "model"]},
        {"node_id": "qjns", "health": "online", "capabilities": ["review"]},
    ]
    nodes = control.fabric_nodes(registered)
    capability_map = control.fleet_capabilities(nodes)["capabilities"]
    topology = control.fleet_topology(nodes)
    route = control.fabric_route(target_node="9fts", required_capability="implementation", registered_nodes=registered)

    assert {"home", "main", "uiap", "qjns", "9fts", "new"} <= {node["node_id"] for node in nodes}
    assert capability_map["implementation"] == ["9fts"]
    assert {"from": "main", "to": "9fts", "type": "protected_fabric_api"} in topology["edges"]
    assert topology["relay_endpoint"] == "/v1/fabric/relay"
    assert route["route"]["endpoint"] == "/v1/nodes/9fts"


def test_model_responses_and_chat_completions_are_safe_blocked_stubs():
    control = load_control()
    for endpoint in ["/v1/responses", "/v1/chat/completions"]:
        envelope = control.model_stub_envelope({"task_id": "MODEL-1", "trace_id": "TRACE-1"}, endpoint=endpoint)
        assert envelope["status"] == "blocked"
        assert envelope["route_used"] == endpoint
        assert envelope["blocked_reason"] == "model_runtime_unavailable"
        assert envelope["repair_task"]["kind"] == "repair_model_runtime_route"
        assert "9fts" in envelope["fallback_nodes"]


def test_agents_aliases_normalize_envelope_and_artifacts():
    control = load_control()
    envelope = control.task_envelope_from_request({"task_id": "AGENT-1", "target_node": "9fts"})
    assert envelope["kind"] == "owner_remote_task"
    assert envelope["source"] == "fabric_api"
    assert envelope["requested_role"] == "remote_agent"
    assert envelope["fallback_allowed"] is True

    artifacts = control.task_artifact_envelope(
        {
            "task_id": "AGENT-1",
            "state": "completed",
            "lease_owner": "9fts:agent-host-9fts",
            "result": {"artifact_paths": ["docs/agent/runs/run/result.json"]},
        },
        "AGENT-1",
    )
    assert artifacts["status"] == "completed"
    assert artifacts["node"] == "9fts"
    assert artifacts["artifacts"] == ["docs/agent/runs/run/result.json"]


def test_admin_endpoints_are_deny_by_default_stubs():
    control = load_control()
    for endpoint in control.ADMIN_ENDPOINTS:
        envelope = control.admin_denied_envelope({"task_id": "ADMIN-1", "target_node": "main"}, endpoint=endpoint)
        assert envelope["status"] == "blocked"
        assert envelope["blocked_reason"] == "admin_scope_denied"
        assert envelope["repair_task"]["kind"] == "request_admin_scope"
        assert envelope["artifacts"] == []


def test_canonical_envelope_and_fallback_reason_taxonomy():
    control = load_control()
    envelope = control.canonical_response_envelope(
        status="blocked",
        task_id="CANON-1",
        trace_id="TRACE-1",
        node="main",
        route_used="/v1/fleet/route",
        fallback_nodes=["qjns"],
        blocked_reason="target_node_unavailable",
        repair_task={"kind": "repair_fabric_route"},
        next_action="choose a fallback node",
    )
    assert set(envelope) == {
        "task_id",
        "trace_id",
        "status",
        "node",
        "route_used",
        "fallback_nodes",
        "artifacts",
        "blocked_reason",
        "repair_task",
        "next_action",
        "data",
    }
    assert envelope["status"] in control.CANONICAL_RESPONSE_STATUSES
    assert envelope["blocked_reason"] in control.FALLBACK_REASON_TAXONOMY
    assert {
        "api_unreachable",
        "vpn_down",
        "firewall",
        "disk_full",
        "auth_failed",
        "dns",
        "unknown",
    } <= control.FALLBACK_REASON_TAXONOMY


def test_prompt3_fabric_surface_is_live_over_http_without_transport_failure():
    control = load_control()
    control.redis = FakeRedis()

    with ControlServer(control) as server:
        status, health = server.request("GET", "/v1/health")
        assert status == 200
        assert health["status"] == "completed"

        status, task_envelope = server.request(
            "POST",
            "/v1/agents/tasks",
            {"task_id": "HTTP-1", "target_node": "9fts", "required_capability": "implementation"},
        )
        assert status == 201
        assert task_envelope["status"] == "running"
        assert task_envelope["route_used"] == "/v1/agents/tasks"

        status, status_envelope = server.request("GET", "/v1/agents/status/HTTP-1")
        assert status == 200
        assert status_envelope["task_id"] == "HTTP-1"
        assert status_envelope["status"] == "running"

        status, nodes = server.request("GET", "/v1/fleet/nodes")
        assert status == 200
        assert {"home", "main", "uiap", "qjns", "9fts", "new"} <= {
            node["node_id"] for node in nodes["data"]["nodes"]
        }

        status, capabilities = server.request("GET", "/v1/fleet/capabilities")
        assert status == 200
        assert capabilities["route_used"] == "/v1/fleet/capabilities"

        status, topology = server.request("GET", "/v1/fleet/topology")
        assert status == 200
        assert topology["data"]["relay_endpoint"] == "/v1/fabric/relay"

        status, route = server.request("GET", "/v1/fleet/route?target_node=missing")
        assert status == 200
        assert route["status"] == "blocked"
        assert route["blocked_reason"] == "target_node_unavailable"
        assert route["repair_task"]["kind"] == "repair_fabric_route"

        status, models = server.request("GET", "/v1/models")
        assert status == 200
        assert models["data"]["object"] == "list"

        for endpoint in ["/v1/responses", "/v1/chat/completions"]:
            status, model_stub = server.request("POST", endpoint, {"task_id": "MODEL-HTTP-1"})
            assert status == 503
            assert model_stub["status"] == "blocked"
            assert model_stub["blocked_reason"] == "model_runtime_unavailable"

        for endpoint in control.ADMIN_ENDPOINTS:
            status, admin_stub = server.request("POST", endpoint, {"task_id": "ADMIN-HTTP-1"})
            assert status == 403
            assert admin_stub["status"] == "blocked"
            assert admin_stub["blocked_reason"] == "admin_scope_denied"
