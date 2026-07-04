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
    monkeypatch.setattr(gateway, "control_request", lambda *args, **kwargs: (503, {"status": "blocked", "reason": "down"}))
    status, payload = gateway.route("GET", "/v1/action/health")
    assert status == 200
    assert payload["auth_token_configured"] is True
    assert "super-secret-value" not in str(payload)


def test_factory_start_blocks_when_control_plane_unreachable(monkeypatch):
    gateway = load_gateway()
    monkeypatch.setattr(gateway, "control_request", lambda *args, **kwargs: (503, {"detail": "timed out"}))
    status, payload = gateway.route("POST", "/v1/factory/start", {"mode": "dry_run"})
    assert status == 503
    assert payload["status"] == "blocked"
    assert payload["reason"] == "factory_control_unreachable"
    assert payload["repair_task"]["kind"] == "repair_control_plane_api"


def test_dangerous_submit_creates_approval_not_execution(monkeypatch):
    gateway = load_gateway()

    def fail_if_called(*args, **kwargs):
        raise AssertionError("control plane must not be called for dangerous actions")

    monkeypatch.setattr(gateway, "control_request", fail_if_called)
    status, payload = gateway.route("POST", "/v1/tasks/submit", {"action": "systemctl restart service"})
    assert status == 202
    assert payload["status"] == "approval_required"
    assert payload["approval_id"]


def test_task_submit_proxies_to_agents_tasks(monkeypatch):
    gateway = load_gateway()
    calls = []

    def fake_request(method, path, body=None, timeout=gateway.TIMEOUT):
        calls.append((method, path, body))
        return 201, {"task_id": "T1", "status": "running"}

    monkeypatch.setattr(gateway, "control_request", fake_request)
    status, payload = gateway.route("POST", "/v1/tasks/submit", {"kind": "read_only_probe"})
    assert status == 201
    assert payload["task_id"] == "T1"
    assert calls == [("POST", "/v1/agents/tasks", {"kind": "read_only_probe"})]


def test_approval_request_is_local_only(monkeypatch):
    gateway = load_gateway()
    monkeypatch.delenv(gateway.AUTH_TOKEN_ENV, raising=False)
    status, payload = gateway.route("POST", "/v1/approvals/request", {"action": "restart"})
    assert status == 202
    assert payload["status"] == "approval_required"
    assert payload["requested_action"] == "restart"
