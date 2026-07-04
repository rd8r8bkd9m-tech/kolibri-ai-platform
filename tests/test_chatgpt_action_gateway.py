import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_gateway():
    spec = importlib.util.spec_from_file_location("chatgpt_action_gateway", ROOT / "ops" / "chatgpt_action_gateway.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_gateway_requires_bearer_token_when_configured(monkeypatch):
    gateway = load_gateway()
    monkeypatch.setenv(gateway.AUTH_TOKEN_ENV, "expected")

    class Headers(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    assert gateway.authorized(Headers({"Authorization": "Bearer expected"})) is True
    assert gateway.authorized(Headers({"Authorization": "Bearer wrong"})) is False


def test_health_does_not_expose_token(monkeypatch):
    gateway = load_gateway()
    monkeypatch.setenv(gateway.AUTH_TOKEN_ENV, "super-secret-value")
    monkeypatch.setattr(
        gateway,
        "control_request",
        lambda *args, **kwargs: (503, {"status": "blocked", "blocked_reason": "down"}, {"control_plane_used": "", "failed_candidates": []}),
    )
    status, payload = gateway.route("GET", "/v1/action/health")
    assert status == 200
    assert payload["data"]["token_present"] is True
    assert "super-secret-value" not in str(payload)
    assert {"status", "request_id", "control_plane_used", "artifacts", "blocked_reason", "fallback_nodes", "repair_task", "next_action"} <= set(payload)


def test_factory_start_blocks_when_control_plane_unreachable(monkeypatch):
    gateway = load_gateway()
    monkeypatch.setattr(
        gateway,
        "control_request",
        lambda *args, **kwargs: (
            503,
            {"blocked_reason": "control_plane_unavailable"},
            {"control_plane_used": "", "failed_candidates": [{"url": "http://bad", "reason": "timed out"}]},
        ),
    )
    status, payload = gateway.route("POST", "/v1/factory/start", {"mode": "dry_run"})
    assert status == 503
    assert payload["status"] == "blocked"
    assert payload["blocked_reason"] == "factory_control_unreachable"
    assert payload["repair_task"] == "P0_REPAIR_CONTROL_PLANE_API"
    assert payload["fallback_nodes"] == [{"url": "http://bad", "reason": "timed out"}]


def test_dangerous_submit_creates_approval_not_execution(monkeypatch):
    gateway = load_gateway()

    def fail_if_called(*args, **kwargs):
        raise AssertionError("control plane must not be called for dangerous actions")

    monkeypatch.setattr(gateway, "control_request", fail_if_called)
    status, payload = gateway.route("POST", "/v1/tasks/submit", {"action": "systemctl restart service"})
    assert status == 202
    assert payload["status"] == "blocked"
    assert payload["data"]["approval_id"]


def test_task_submit_proxies_to_agents_tasks(monkeypatch):
    gateway = load_gateway()
    calls = []

    def fake_request(method, path, body=None, timeout=gateway.TIMEOUT):
        calls.append((method, path, body))
        return 201, {"task_id": "T1", "status": "running"}, {"control_plane_used": "http://ok", "failed_candidates": []}

    monkeypatch.setattr(gateway, "control_request", fake_request)
    status, payload = gateway.route("POST", "/v1/tasks/submit", {"kind": "read_only_probe"})
    assert status == 201
    assert payload["task_id"] == "T1"
    assert payload["control_plane_used"] == "http://ok"
    assert calls == [("POST", "/v1/agents/tasks", {"kind": "read_only_probe"})]


def test_approval_request_is_local_only(monkeypatch):
    gateway = load_gateway()
    monkeypatch.delenv(gateway.AUTH_TOKEN_ENV, raising=False)
    status, payload = gateway.route("POST", "/v1/approvals/request", {"action": "restart"})
    assert status == 202
    assert payload["status"] == "blocked"
    assert payload["data"]["requested_action"] == "restart"


def test_control_request_falls_back_after_dead_endpoint(monkeypatch):
    gateway = load_gateway()
    monkeypatch.setenv(gateway.CONTROL_URLS_ENV, "http://bad,http://good")
    calls = []

    def fake_http_json(base_url, method, path, body=None, timeout=gateway.TIMEOUT):
        calls.append((base_url, method, path))
        if base_url == "http://bad":
            raise TimeoutError("timed out")
        return 200, {"status": "ok"}

    monkeypatch.setattr(gateway, "_http_json", fake_http_json)
    status, payload, meta = gateway.control_request("GET", "/v1/health", timeout=1)

    assert status == 200
    assert payload == {"status": "ok"}
    assert meta["control_plane_used"] == "http://good"
    assert meta["failed_candidates"] == [{"url": "http://bad", "reason": "timed out"}]
    assert calls == [("http://bad", "GET", "/v1/health"), ("http://good", "GET", "/v1/health")]


def test_control_request_blocks_when_all_endpoints_dead(monkeypatch):
    gateway = load_gateway()
    monkeypatch.setenv(gateway.CONTROL_URLS_ENV, "http://bad1,http://bad2")

    def fake_http_json(base_url, method, path, body=None, timeout=gateway.TIMEOUT):
        raise TimeoutError(f"{base_url} down")

    monkeypatch.setattr(gateway, "_http_json", fake_http_json)
    status, payload, meta = gateway.control_request("GET", "/v1/health", timeout=1)

    assert status == 503
    assert payload["status"] == "blocked"
    assert payload["repair_task"] == "P0_REPAIR_CONTROL_PLANE_API"
    assert meta["control_plane_used"] == ""
    assert len(meta["failed_candidates"]) == 2


def test_factory_start_submits_safe_canary_after_health(monkeypatch):
    gateway = load_gateway()
    calls = []

    def fake_control_request(method, path, body=None, timeout=gateway.TIMEOUT):
        calls.append((method, path, body))
        if path == "/v1/health":
            return 200, {"status": "ok"}, {"control_plane_used": "http://ok", "failed_candidates": []}
        assert path == "/v1/agents/tasks"
        assert body["constraints"]["read_only"] is True
        assert body["write_scope"] == []
        return 201, {"task_id": body["task_id"], "status": "running"}, {"control_plane_used": "http://ok", "failed_candidates": []}

    monkeypatch.setattr(gateway, "control_request", fake_control_request)
    status, payload = gateway.route("POST", "/v1/factory/start", {"autopilot": "A1"})

    assert status == 202
    assert payload["status"] == "running"
    assert payload["task_id"].startswith("START_FACTORY_CANARY_")
    assert payload["control_plane_used"] == "http://ok"
    assert [call[1] for call in calls] == ["/v1/health", "/v1/agents/tasks"]
