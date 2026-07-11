import json
from pathlib import Path
from types import SimpleNamespace
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient
import provider_gateway
from provider_gateway import (
    DEFAULT_CODEX_MODELS,
    ProviderGateway,
    _factory_control_endpoint,
    _factory_health_response_records,
    classify_failure,
    extract_assistant_text,
    public_identity_contract_violation,
    safe_runner_environment,
    structured_error_type,
)
from providers import AIProviderManager


def executable(path: Path, body: str) -> str:
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def configure_local_home_control(monkeypatch, tmp_path: Path, endpoint_url: str) -> Path:
    """Configure a loopback test server through the real Home identity guard.

    Production does not receive a localhost exception.  The resolver reads a
    valid dynamic membership manifest and loopback is accepted only after the
    injected local-address proof shows this test host owns Home's mesh IP.
    """

    manifest = tmp_path / "home-peers.json"
    manifest.write_text(
        json.dumps({
            "peers": {
                "dynamic-home-record": {
                    "node_id": "home",
                    "mesh_ip": "10.99.0.1",
                }
            }
        }),
        encoding="utf-8",
    )
    real_resolver = provider_gateway.resolve_home_control_plane_url

    def resolve_test_home(*, control_url=None, control_urls=None):
        return real_resolver(
            control_url=control_url,
            control_urls=control_urls,
            manifest_path=manifest,
            local_addresses=["10.99.0.1/24"],
        )

    monkeypatch.setattr(provider_gateway, "resolve_home_control_plane_url", resolve_test_home)
    monkeypatch.setenv("KOLIBRI_FACTORY_CONTROL_URL", endpoint_url)
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URLS", raising=False)
    return manifest


def factory_control_server(state):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            state.setdefault("authorization", []).append(self.headers.get("Authorization"))
            if state.get("http_error"):
                self._send(state["http_error"], {"error": state.get("secret_body", "failure")})
                return
            if self.path.startswith("/v1/nodes"):
                self._send(200, {"nodes": state["nodes"]})
                return
            if self.path.startswith("/v1/runtime/provider-actors"):
                records = state.get("provider_actors", [])
                binding = state.get(
                    "provider_auth_binding",
                    records[0].get("external_provider_auth") if records else None,
                )
                self._send(200, {
                    "runner": "codex",
                    "auth_configured": bool(binding),
                    "auth_binding": binding,
                    "records": records,
                })
                return
            if self.path.startswith("/v1/runtime/provider-health?"):
                runner = "codex" if "runner=codex" in self.path else "mimo"
                self._send(200, {
                    "runner": runner,
                    "records": state.get("provider_health", {}).get(runner, []),
                })
                return
            if self.path.startswith("/v1/tasks/"):
                state["polls"] = state.get("polls", 0) + 1
                submitted = state["submitted"][-1]
                task_id = submitted["task_id"]
                node_id = submitted["target_node"]
                runner = submitted["runner"]
                attempt_id = f"{task_id}-attempt-1"
                if runner in state.get("failed_runners", set()):
                    self._send(200, {
                        "task_id": task_id,
                        "state": "failed",
                        "attempt": 1,
                        "attempt_id": attempt_id,
                        "lease_owner": f"{node_id}:agent-live",
                        "error_type": "runner_auth_failed",
                        "result": {
                            "status": "blocked",
                            "attempt_id": attempt_id,
                            "node_id": node_id,
                            "agent_id": "agent-live",
                            "runner": runner,
                        },
                    })
                    return
                if state.get("mode") == "running":
                    self._send(200, {
                        "task_id": task_id, "state": "running", "attempt": 1,
                        "attempt_id": attempt_id, "lease_owner": f"{node_id}:agent-live",
                    })
                    return
                result_attempt = "wrong-attempt" if state.get("mode") == "bad_fence" else attempt_id
                self._send(200, {
                    "task_id": task_id,
                    "state": "completed",
                    "attempt": 1,
                    "attempt_id": attempt_id,
                    "lease_owner": f"{node_id}:agent-live",
                    "error_type": None,
                    "result": {
                        "status": "completed",
                        "attempt_id": result_attempt,
                        "node_id": node_id,
                        "agent_id": "agent-live",
                        "runner": runner,
                        "response": state.get("answers_by_runner", {}).get(
                            runner, state.get("answer", "factory verified")
                        ),
                        "write_scope_violations": [],
                        "product_code_changed": False,
                    },
                })
                return
            self._send(404, {"error": "not_found"})

        def do_POST(self):  # noqa: N802
            state.setdefault("authorization", []).append(self.headers.get("Authorization"))
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if self.path.endswith("/cancel"):
                state.setdefault("cancelled", []).append(payload)
                self._send(200, {"status": "cancelled"})
                return
            state.setdefault("submitted", []).append(payload)
            self._send(201, {"task_id": payload["task_id"], "state": "queued"})

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def fresh_factory_node(node_id="ephemeral-worker-7"):
    secure_runner = {
        "status": "available",
        "factory_provider_contract": "kolibri.factory-provider.readonly.v1",
        "prompt_transport": "stdin",
        "sandbox": "read-only",
        "worktree_scoped": True,
        "output_format": "jsonl",
    }
    return {
        "node_id": node_id,
        "hostname": f"host-{node_id}",
        "health": "online",
        "freshness": "fresh",
        "heartbeat_age_seconds": 2,
        "active_task": None,
        "draining": False,
        "capabilities": ["generic_implementation", "runner:mimo", "runner:codex"],
        "runners": {
            "mimo": dict(secure_runner),
            "codex": dict(secure_runner),
        },
    }


def external_factory_codex_actor(node_id="dynamic-owner-codex-broker"):
    checked_at = datetime.now(timezone.utc).isoformat()
    probe = {
        "model": "gpt-5.5",
        "sandbox": "read-only",
        "status": "passed",
        "duration_ms": 1200,
        "output_sha256": "a" * 64,
    }
    runner = {
        "provider": "codex",
        "model": "gpt-5.5",
        "display_name": "Codex authenticated runner",
        "authorization_mode": "node_managed",
        "authorization_flow": "browser_device",
        "user_authorization_required": False,
        "permission_mode": "task_contract",
        "output_format": "jsonl",
        "worktree_scoped": True,
        "factory_provider_contract": "kolibri.factory-provider.readonly.v1",
        "prompt_transport": "stdin",
        "sandbox": "read-only",
        "network_access": "provider_managed_search",
        "status": "available",
        "checked_at": checked_at,
        "readiness_contract": "kolibri.codex-readiness.v1",
        "access_mode": "local_service_account",
        "login_status": "authenticated",
        "error_type": None,
        "probe": dict(probe),
    }
    marker = {
        "actor_scope": "external_provider_actor",
        "bound_node_id": node_id,
        "credential_id": "test-codex-audit-v1",
        "epoch": 1,
    }
    return {
        "node_id": node_id,
        "hostname": "owner-provider-host",
        "membership_scope": "audit",
        "schedulable": False,
        "health": "online",
        "freshness": "fresh",
        "heartbeat_age_seconds": 1,
        "active_task": None,
        "draining": False,
        "labels": {
            "provider": "codex",
            "runtime": "macos_launchagent",
            "physical_node_id": node_id,
        },
        "capabilities": ["codex_provider_broker", "runner:codex"],
        "runners": {"codex": runner},
        "runner_readiness": {"codex": {
            "schema_version": "kolibri.codex-readiness.v1",
            "node_id": node_id,
            "checked_at": checked_at,
            "access_mode": "local_service_account",
            "status": "available",
            "login_status": "authenticated",
            "error_type": None,
            "probe": dict(probe),
        }},
        "external_provider_auth": marker,
    }


def factory_health_record(
    node_id: str,
    *,
    observed_at: datetime,
    duration_seconds: float = 30.0,
    status: str,
    reason: str,
):
    return {
        "node_id": node_id,
        "status": status,
        "reason": reason,
        "observed_at": observed_at.isoformat(),
        "latency_seconds": duration_seconds,
    }


def test_factory_health_projection_ignores_unrelated_cancellation_and_prompt_fields():
    now = datetime.now(timezone.utc)
    payload = {"runner": "mimo", "records": [{
        **factory_health_record(
            "healthy-node", observed_at=now, status="ignored",
            reason="owner_cancelled",
        ),
        "objective": "private prompt must never enter route health",
    }]}

    assert _factory_health_response_records(
        payload, "mimo", now=now.timestamp(), cooldown_seconds=300,
    ) == {}


def test_factory_timeout_circuit_half_opens_after_short_backpressure_window():
    now = datetime.now(timezone.utc)
    payload = {"runner": "codex", "records": [factory_health_record(
        "mac-provider",
        observed_at=now - timedelta(seconds=6),
        duration_seconds=45,
        status="open",
        reason="provider_timeout",
    )]}

    assert _factory_health_response_records(
        payload,
        "codex",
        now=now.timestamp(),
        cooldown_seconds=300,
        transient_timeout_cooldown_seconds=5,
    ) == {}


def test_factory_nontransient_circuit_keeps_normal_cooldown():
    now = datetime.now(timezone.utc)
    payload = {"runner": "codex", "records": [factory_health_record(
        "mac-provider",
        observed_at=now - timedelta(seconds=6),
        duration_seconds=1,
        status="open",
        reason="provider_auth_failed",
    )]}

    records = _factory_health_response_records(
        payload,
        "codex",
        now=now.timestamp(),
        cooldown_seconds=300,
        transient_timeout_cooldown_seconds=5,
    )
    assert records["mac-provider"]["status"] == "open"
    assert records["mac-provider"]["reason"] == "provider_auth_failed"


def test_factory_default_deadline_scales_for_codex_schema_tasks():
    assert ProviderGateway._factory_default_task_timeout("short", "codex") == 90
    assert ProviderGateway._factory_default_task_timeout("x" * 8_193, "codex") == 180
    assert ProviderGateway._factory_default_task_timeout("short", "mimo") == 75


def test_gateway_falls_back_and_requires_verified_nonempty_output(tmp_path, monkeypatch):
    mimo = executable(tmp_path / "mimo", "echo provider-failed >&2\nexit 2\n")
    answer = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "4"}})
    codex = executable(tmp_path / "codex", f"printf '%s\\n' '{answer}'\n")
    monkeypatch.setenv("KOLIBRI_MIMO_BIN", mimo)
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", codex)
    monkeypatch.setenv("KOLIBRI_CODEX_MODEL", "gpt-5.4")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))

    result = ProviderGateway(timeout=5).generate("2+2?", "Answer briefly", "resp-test")
    assert result.status == "completed" and result.text == "4"
    assert result.technical["selected_provider"] == "codex"
    assert result.technical["fallback_used"] is True
    assert result.technical["evidence"][0]["output_sha256"]


def test_zero_exit_empty_output_is_failure_not_fake_completion(tmp_path, monkeypatch):
    empty = executable(tmp_path / "mimo", "exit 0\n")
    monkeypatch.setenv("KOLIBRI_MIMO_BIN", empty)
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    result = ProviderGateway(provider_order=("mimo",), timeout=5).generate("question", None, "resp-test")
    assert result.status == "failed" and result.text == ""
    assert result.technical["evidence"] == []
    assert result.technical["attempts"][0]["error_type"] == "provider_empty_output"


def test_request_timeout_is_total_and_kills_cli_process_group(tmp_path, monkeypatch):
    leaked_marker = tmp_path / "provider-child-leaked"
    codex = executable(
        tmp_path / "codex",
        f"(sleep 0.35; touch '{leaked_marker}') &\nsleep 10\n",
    )
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", codex)
    monkeypatch.setenv("KOLIBRI_CODEX_MODELS", "gpt-5.5,gpt-5.4")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))

    started = time.monotonic()
    result = ProviderGateway(provider_order=("codex",), timeout=5).generate(
        "bounded answer",
        None,
        "resp-total-timeout",
        timeout_seconds=0.1,
    )
    elapsed = time.monotonic() - started
    time.sleep(0.45)

    assert result.status == "failed"
    assert result.technical["error_type"] == "provider_timeout"
    assert len(result.technical["attempts"]) == 1
    assert result.technical["attempts"][0]["provider_model"] == "gpt-5.5"
    assert elapsed < 0.8
    assert not leaked_marker.exists()


def test_runner_commands_are_sandboxed_and_prompt_never_appears_in_argv(tmp_path, monkeypatch):
    runner = executable(tmp_path / "runner", "exit 0\n")
    monkeypatch.setenv("KOLIBRI_MIMO_BIN", runner)
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    gateway = ProviderGateway(timeout=5)
    secret_prompt = "private prompt must travel over stdin only"
    mimo_command, _ = gateway._command("mimo", runner, "resp-test", tmp_path)
    codex_command, _ = gateway._command("codex", runner, "resp-test", tmp_path, "gpt-5.4")
    for command in (mimo_command, codex_command):
        serialized = " ".join(command).lower()
        assert secret_prompt not in serialized
        assert "dangerously" not in serialized
        assert "skip-permissions" not in serialized
    assert codex_command[-1] == "-"
    assert "--ignore-user-config" in codex_command
    assert "--ignore-rules" in codex_command
    assert 'shell_environment_policy.inherit="none"' in codex_command

    stdin_probe = executable(
        tmp_path / "stdin-probe",
        "prompt=$(cat)\n"
        "case \"$prompt\" in *\"private prompt must travel over stdin only\"*) ;; *) exit 8 ;; esac\n"
        "case \"$prompt\" in *\"Execution identity contract:\"*) ;; *) exit 9 ;; esac\n"
        "printf '%s\\n' '{\"type\":\"item.completed\",\"item\":{\"type\":\"agent_message\",\"text\":\"safe\"}}'\n",
    )
    monkeypatch.setenv("KOLIBRI_MIMO_BIN", stdin_probe)
    result = ProviderGateway(provider_order=("mimo",), timeout=5).generate(
        secret_prompt, None, "resp-stdin",
    )
    assert result.status == "completed" and result.text == "safe"


def test_jsonl_parser_ignores_non_assistant_metadata():
    stdout = '\n'.join([
        json.dumps({"type": "thread.started", "thread_id": "abc"}),
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "answer"}}),
    ])
    assert extract_assistant_text(stdout) == "answer"


def test_public_identity_guard_is_scoped_to_executor_self_identification():
    assert public_identity_contract_violation("Я — MiMo Code Agent.") is True
    assert public_identity_contract_violation("Я — MiMoCode.") is True
    assert public_identity_contract_violation("I am MimoCode Agent.") is True
    assert public_identity_contract_violation("I am Codex.") is True
    assert public_identity_contract_violation("Я Kolibri. Чем помочь?") is False
    assert public_identity_contract_violation(
        '{"schema_version":"kolibri.estimate-proposal.v1","title":"Смета"}'
    ) is False
    assert public_identity_contract_violation(
        "Сравните Codex и Mimo для внутреннего технического отчёта."
    ) is False
    assert public_identity_contract_violation("Мой совет — использовать Codex для кода.") is False
    assert public_identity_contract_violation("My recommendation is to compare Mimo and Codex.") is False
    assert public_identity_contract_violation("Codex.") is False


def test_jsonl_error_event_blocks_success_even_when_runner_exits_zero():
    stdout = json.dumps({
        "type": "error",
        "error": {"data": {"message": "Request blocked by risk control", "responseBody": '{"code":"441","type":"risk_control"}'}},
    })
    assert extract_assistant_text(stdout) == ""
    assert structured_error_type(stdout) == "provider_risk_control"


def test_numeric_441_and_stderr_only_risk_control_are_normalized():
    stdout = json.dumps({
        "type": "error",
        "error": {"data": {"message": "request rejected", "code": 441}},
    })
    assert structured_error_type(stdout) == "provider_risk_control"
    assert classify_failure('APIError: {"code":441}', 1) == "provider_risk_control"


def test_codex_capability_probe_falls_back_between_configured_models(tmp_path, monkeypatch):
    codex = executable(tmp_path / "codex", """
case "$*" in
  *gpt-5.5*) printf '%s\\n' '{"type":"error","message":"requires a newer version"}'; exit 1 ;;
  *) printf '%s\\n' '{"type":"item.completed","item":{"type":"agent_message","text":"4"}}' ;;
esac
""")
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", codex)
    monkeypatch.setenv("KOLIBRI_CODEX_MODELS", "gpt-5.5,gpt-5.4")
    monkeypatch.delenv("KOLIBRI_CODEX_MODEL", raising=False)
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    result = ProviderGateway(provider_order=("codex",), timeout=5).generate("2+2?", None, "resp-test")
    assert result.status == "completed" and result.text == "4"
    assert [attempt["provider_model"] for attempt in result.technical["attempts"]] == ["gpt-5.5", "gpt-5.4"]
    assert result.technical["attempts"][0]["error_type"] == "provider_runner_outdated"


def test_default_codex_internal_route_order_starts_with_56_then_55_54(monkeypatch):
    monkeypatch.delenv("KOLIBRI_CODEX_MODEL", raising=False)
    monkeypatch.delenv("KOLIBRI_CODEX_MODELS", raising=False)
    assert ProviderGateway._models("codex") == DEFAULT_CODEX_MODELS
    assert DEFAULT_CODEX_MODELS == (
        "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5", "gpt-5.4",
        "gpt-5.3-codex-spark",
    )


def test_default_codex_routes_are_execution_probed_in_order(tmp_path, monkeypatch):
    codex = executable(tmp_path / "codex", """
case "$*" in
  *gpt-5.4*) printf '%s\n' '{"type":"item.completed","item":{"type":"agent_message","text":"fallback"}}' ;;
  *) printf '%s\n' '{"type":"error","message":"model is not available"}'; exit 1 ;;
esac
""")
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", codex)
    monkeypatch.delenv("KOLIBRI_CODEX_MODEL", raising=False)
    monkeypatch.delenv("KOLIBRI_CODEX_MODELS", raising=False)
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))

    result = ProviderGateway(provider_order=("codex",), timeout=5).generate("answer", None, "resp-routes")
    assert result.status == "completed" and result.text == "fallback"
    assert [item["provider_model"] for item in result.technical["attempts"]] == list(DEFAULT_CODEX_MODELS[:5])
    assert [item["route_capability"]["status"] for item in result.technical["attempts"]] == [
        "unavailable", "unavailable", "unavailable", "unavailable", "available",
    ]


def test_provider_order_cannot_enable_direct_openai_route(monkeypatch):
    monkeypatch.setenv("KOLIBRI_PROVIDER_ORDER", "openai,codex")
    gateway = ProviderGateway(timeout=5)
    assert gateway.provider_order == ("codex",)


def test_verified_loopback_local_model_is_last_resort_without_secret_leak(tmp_path, monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length))
            assert self.headers.get("Authorization") == "Bearer local-test-secret"
            assert request["model"] == "qwen3.6-plus#kolibriai.ru"
            payload = json.dumps({
                "choices": [{"message": {"role": "assistant", "content": "local verified"}}]
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv(
        "KOLIBRI_LOCAL_LLM_ENDPOINT",
        f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
    )
    monkeypatch.setenv("KOLIBRI_LOCAL_LLM_MODEL", "qwen3.6-plus#kolibriai.ru")
    monkeypatch.setenv("KOLIBRI_LOCAL_LLM_API_KEY", "local-test-secret")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(provider_order=("local",), timeout=5).generate(
            "answer locally", None, "resp-local",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "completed" and result.text == "local verified"
    assert result.technical["selected_provider"] == "local"
    assert result.technical["evidence"][1]["verdict"] == "passed"
    assert "local-test-secret" not in json.dumps(result.technical)


def test_local_model_endpoint_must_be_literal_loopback(tmp_path, monkeypatch):
    monkeypatch.setenv("KOLIBRI_LOCAL_LLM_ENDPOINT", "http://10.99.0.5:8787/v1/chat/completions")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    gateway = ProviderGateway(provider_order=("local",), timeout=1)
    assert gateway.available() == {"local": False}
    result = gateway.generate("no ssrf", None, "resp-no-ssrf")
    assert result.status == "failed"
    assert result.technical["attempts"][0]["error_type"] == "provider_endpoint_invalid"


def test_deepseek_verified_fallback_uses_fixed_https_origin_and_v4_model(tmp_path, monkeypatch):
    captured = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return json.dumps({
                "choices": [{"message": {"role": "assistant", "content": "deepseek verified"}}]
            }).encode()

    class Opener:
        def open(self, request, timeout):
            captured["url"] = request.full_url
            captured["authorization"] = request.headers.get("Authorization")
            captured["payload"] = json.loads(request.data)
            captured["timeout"] = timeout
            return Response()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-secret")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.delenv("KOLIBRI_DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.setattr("provider_gateway.urllib.request.build_opener", lambda *_args: Opener())

    result = ProviderGateway(provider_order=("deepseek",), timeout=7).generate(
        "answer", None, "resp-deepseek",
    )
    assert result.status == "completed" and result.text == "deepseek verified"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["authorization"] == "Bearer deepseek-test-secret"
    assert captured["timeout"] == 7
    assert captured["payload"]["model"] == "deepseek-v4-pro"
    assert captured["payload"]["stream"] is False
    deepseek_prompt = captured["payload"]["messages"][0]
    assert deepseek_prompt["role"] == "user"
    assert deepseek_prompt["content"].endswith("\n\nanswer")
    assert "Execution identity contract:" in deepseek_prompt["content"]
    assert "deepseek-test-secret" not in json.dumps(result.technical)


def test_deepseek_endpoint_override_cannot_escape_official_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "present")
    monkeypatch.setenv("KOLIBRI_DEEPSEEK_ENDPOINT", "https://example.com/chat/completions")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    gateway = ProviderGateway(provider_order=("deepseek",), timeout=1)
    assert gateway.available() == {"deepseek": False}
    result = gateway.generate("no ssrf", None, "resp-deepseek-origin")
    assert result.status == "failed"
    assert result.technical["attempts"][0]["error_type"] == "provider_endpoint_invalid"


def test_specialized_spark_route_follows_56_55_54_failures(tmp_path, monkeypatch):
    codex = executable(tmp_path / "codex", """
case "$*" in
  *gpt-5.3-codex-spark*) printf '%s\n' '{"type":"item.completed","item":{"type":"agent_message","text":"spark"}}' ;;
  *gpt-5.5*|*gpt-5.4*) printf '%s\n' '{"type":"error","message":"usage limit reached"}'; exit 1 ;;
  *) printf '%s\n' '{"type":"error","message":"requires a newer version"}'; exit 1 ;;
esac
""")
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", codex)
    monkeypatch.delenv("KOLIBRI_CODEX_MODEL", raising=False)
    monkeypatch.delenv("KOLIBRI_CODEX_MODELS", raising=False)
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))

    result = ProviderGateway(provider_order=("codex",), timeout=5).generate("answer", None, "resp-spark")
    assert result.status == "completed" and result.text == "spark"
    assert [item["provider_model"] for item in result.technical["attempts"]] == list(DEFAULT_CODEX_MODELS)
    assert [item.get("error_type") for item in result.technical["attempts"][:-1]] == [
        "provider_runner_outdated", "provider_runner_outdated", "provider_runner_outdated",
        "provider_usage_limit", "provider_usage_limit",
    ]
    assert result.technical["attempts"][-1]["route_capability"]["status"] == "available"


def test_runner_environment_is_allowlisted_and_drops_direct_api_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-service-secret-never-inherit")
    monkeypatch.setenv("MIMO_API_KEY", "mimo-service-secret-never-inherit")
    monkeypatch.setenv("DATABASE_URL", "postgres://secret")
    monkeypatch.setenv("CODEX_HOME", "/tmp/codex-home")
    environment = safe_runner_environment()
    assert environment["CODEX_HOME"] == "/tmp/codex-home"
    assert "OPENAI_API_KEY" not in environment
    assert "MIMO_API_KEY" not in environment
    assert "DATABASE_URL" not in environment


def test_subprocess_does_not_inherit_service_secret(tmp_path, monkeypatch):
    codex = executable(tmp_path / "codex", """
if [ -n "$OPENAI_API_KEY" ] || [ -n "$MIMO_API_KEY" ]; then exit 9; fi
printf '%s\n' '{"type":"item.completed","item":{"type":"agent_message","text":"safe"}}'
""")
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", codex)
    monkeypatch.setenv("KOLIBRI_CODEX_MODEL", "gpt-5.4")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-service-secret-never-inherit")
    monkeypatch.setenv("MIMO_API_KEY", "mimo-service-secret-never-inherit")

    result = ProviderGateway(provider_order=("codex",), timeout=5).generate("answer", None, "resp-env")
    assert result.status == "completed"
    assert result.text == "safe"
    assert result.technical["evidence"][1]["type"] == "deterministic_verifier"
    assert result.technical["evidence"][1]["verdict"] == "passed"


def test_tool_request_requires_jsonl_tool_provenance_and_captures_safe_artifacts(tmp_path, monkeypatch):
    tool_event = json.dumps({
        "type": "item.completed",
        "item": {
            "type": "mcp_tool_call", "id": "call-1", "name": "search", "status": "completed",
            "arguments": {"authorization": "Bearer never-store-this-value"},
            "result": {"text": "private tool result"},
            "artifacts": [{
                "url": "https://user:password@example.com/report.pdf?token=never-store-this-value",
                "sha256": "b" * 64, "size_bytes": 12,
            }],
        },
    })
    answer = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "verified answer"}})
    codex = executable(tmp_path / "codex", f"printf '%s\\n' '{tool_event}' '{answer}'\n")
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", codex)
    monkeypatch.setenv("KOLIBRI_CODEX_MODEL", "gpt-5.4")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    binding = {
        "id": "tool:search", "name": "search", "kind": "tool", "status": "available",
        "_aliases": ("search", "tool:search"), "_providers": ("codex",),
    }

    result = ProviderGateway(provider_order=("codex",), timeout=5).generate(
        "research", None, "resp-tool", requested_tools=[binding],
    )
    serialized = json.dumps(result.technical)
    assert result.status == "completed" and result.text == "verified answer"
    assert result.technical["tool_calls"][0]["tool"] == "search"
    assert result.technical["tool_calls"][0]["status"] == "succeeded"
    assert result.technical["artifact_refs"][0]["origin"] == "https://example.com"
    assert result.technical["artifact_refs"][0]["name"] == "report.pdf"
    assert "never-store-this-value" not in serialized
    assert "private tool result" not in serialized
    assert result.technical["verifier_evidence"]["verdict"] == "passed"
    assert result.technical["tool_event_summary"] == {
        "count": 1, "event_types": ["mcp_tool_call"], "tool_names": ["search"],
        "statuses": {"running": 0, "succeeded": 1, "failed": 0},
    }


def test_tool_request_cannot_complete_when_runner_omits_tool_event(tmp_path, monkeypatch):
    answer = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "unverified"}})
    codex = executable(tmp_path / "codex", f"printf '%s\\n' '{answer}'\n")
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", codex)
    monkeypatch.setenv("KOLIBRI_CODEX_MODEL", "gpt-5.4")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    binding = {
        "id": "tool:search", "name": "search", "kind": "tool", "status": "available",
        "_aliases": ("search", "tool:search"), "_providers": ("codex",),
    }

    result = ProviderGateway(provider_order=("codex",), timeout=5).generate(
        "research", None, "resp-tool-missing", requested_tools=[binding],
    )
    assert result.status == "failed" and result.text == ""
    assert result.technical["attempts"][0]["error_type"] == "tool_verification_failed"
    assert result.technical["attempts"][0]["verifier_evidence"]["checks"]["requested_tools_executed"] is False


def test_internal_skill_plan_routes_to_codex_without_becoming_tool_request(tmp_path, monkeypatch):
    mimo = executable(tmp_path / "mimo", "exit 9\n")
    answer = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "planned"}})
    codex = executable(tmp_path / "codex", f"printf '%s\\n' '{answer}'\n")
    monkeypatch.setenv("KOLIBRI_MIMO_BIN", mimo)
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", codex)
    monkeypatch.setenv("KOLIBRI_CODEX_MODEL", "gpt-5.4")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    skill = {
        "id": "skill:pdf", "name": "pdf", "kind": "skill", "status": "available",
        "source": {"type": "codex_skill_frontmatter", "manifest_sha256": "e" * 64},
        "_providers": ("codex",),
    }
    result = ProviderGateway(timeout=5).generate(
        "inspect PDF", None, "resp-skill", requested_tools=[], planned_skills=[skill],
    )
    assert result.status == "completed"
    assert result.technical["attempts"][0]["provider"] == "mimo"
    assert result.technical["attempts"][0]["error_type"] == "planned_skill_not_supported_by_route"
    assert result.technical["attempts"][1]["provider"] == "codex"
    assert result.technical["tool_calls"] == []
    assert result.technical["skill_routing"]["selected"][0]["id"] == "skill:pdf"


def test_api_chat_compatibility_uses_shared_verified_gateway(monkeypatch):
    output_sha = __import__("hashlib").sha256(b"4").hexdigest()
    evidence = [{
        "type": "provider_execution", "provider": "codex", "provider_model": "gpt-test",
        "exit_code": 0, "output_sha256": output_sha, "output_bytes": 1,
        "completion_signal": "non_empty_assistant_output",
    }, {
        "type": "deterministic_verifier", "verifier": "kolibri.gateway.contract.v1",
        "verdict": "passed", "binding_sha256": "b" * 64,
    }]

    class FakeGateway:
        def available(self):
            return {"codex": True}

        def generate(self, input_value, instructions, response_id):
            return SimpleNamespace(status="completed", text="4", technical={
                "selected_provider": "codex", "fallback_used": False,
                "attempts": [{"attempt": 1, "provider": "codex", "status": "succeeded", "evidence": evidence}],
                "evidence": evidence,
            })

    import main
    monkeypatch.setattr(main, "ai_manager", AIProviderManager(FakeGateway()))
    monkeypatch.setattr(main, "get_cached_response", lambda _key: None)
    response = TestClient(main.app).post("/api/chat", json={
        "messages": [{"role": "user", "content": "compatibility-gateway-contract-2+2"}],
        "model": "kolibri",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "4" and body["model"] == "kolibri"
    assert "provider" not in body
    assert body["technical"]["provider_routing"]["evidence"] == evidence


def test_factory_provider_uses_dynamic_fresh_capability_and_fenced_evidence(tmp_path, monkeypatch):
    live_node = fresh_factory_node("newly-enrolled-worker")
    state = {
        "nodes": [
            {**fresh_factory_node("stale-worker"), "freshness": "stale", "heartbeat_age_seconds": 900},
            {**fresh_factory_node("busy-worker"), "active_task": "other-task"},
            {**fresh_factory_node("home-authority"), "capabilities": ["home", "runner:mimo"]},
            live_node,
        ],
        "answer": "real factory answer",
    }
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_FACTORY_POLL_INTERVAL", "0.01")
    monkeypatch.setenv("KOLIBRI_FACTORY_TASK_TIMEOUT", "1")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(
            provider_order=("factory",),
            model_overrides={"factory": ("mimo",)},
            timeout=2,
        ).generate("answer through Home", None, "resp-factory")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "completed" and result.text == "real factory answer"
    assert result.technical["selected_provider"] == "factory"
    assert result.technical["selected_runner"] == "mimo"
    assert state["submitted"][0]["target_node"] == "newly-enrolled-worker"
    assert state["submitted"][0]["required_capability"] == "runner:mimo"
    assert state["submitted"][0]["write_scope"] == []
    provider_evidence = result.technical["evidence"][0]
    assert provider_evidence["route_transport"] == "home_control_plane"
    assert provider_evidence["node_ref"].startswith("node:")
    assert "newly-enrolled-worker" not in json.dumps(result.technical)
    assert provider_evidence["fence_verified"] is True
    assert provider_evidence["checks"]["attempt_fenced"] is True
    assert provider_evidence["checks"]["node_bound"] is True
    assert result.technical["verifier_evidence"]["verdict"] == "passed"


def test_factory_health_routes_around_recent_timeout_before_heartbeat_age(
    tmp_path, monkeypatch,
):
    now = datetime.now(timezone.utc)
    timed_out = fresh_factory_node("recently-timed-out")
    timed_out["heartbeat_age_seconds"] = 1
    proven = fresh_factory_node("recently-proven")
    proven["heartbeat_age_seconds"] = 20
    state = {
        "nodes": [timed_out, proven],
        "provider_health": {"mimo": [
            factory_health_record(
                "recently-timed-out", observed_at=now, duration_seconds=45,
                status="open", reason="provider_timeout",
            ),
            factory_health_record(
                "recently-proven", observed_at=now - timedelta(seconds=5),
                duration_seconds=28, status="healthy", reason="verified_completion",
            ),
        ]},
        "answer": "healthy route answer",
    }
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_FACTORY_POLL_INTERVAL", "0.01")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(
            provider_order=("factory",), model_overrides={"factory": ("mimo",)}, timeout=2,
        ).generate("avoid known timeout", None, "resp-health-order")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "completed"
    assert [task["target_node"] for task in state["submitted"]] == ["recently-proven"]
    assert result.technical["selected_runner"] == "mimo"


def test_factory_single_codex_actor_recovers_after_transient_timeout_cooldown(
    tmp_path, monkeypatch,
):
    now = datetime.now(timezone.utc)
    actor = fresh_factory_node("sole-codex-actor")
    state = {
        "nodes": [actor],
        "provider_health": {"codex": [
            factory_health_record(
                "sole-codex-actor",
                observed_at=now - timedelta(seconds=6),
                duration_seconds=45,
                status="open",
                reason="provider_timeout",
            ),
        ]},
        "answer": "recovered codex answer",
    }
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_FACTORY_TIMEOUT_COOLDOWN", "5")
    monkeypatch.setenv("KOLIBRI_FACTORY_POLL_INTERVAL", "0.01")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(
            provider_order=("factory",),
            model_overrides={"factory": ("codex",)},
            timeout=2,
        ).generate(
            "retry after a request-specific timeout",
            None,
            "resp-timeout-recovery",
            execution_mode="codex",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "completed"
    assert result.text == "recovered codex answer"
    assert [task["target_node"] for task in state["submitted"]] == ["sole-codex-actor"]


def test_factory_codex_discovers_dynamic_audit_actor_with_strict_contract(
    tmp_path, monkeypatch,
):
    actor_id = "dynamic-codex-broker-7"
    state = {
        "nodes": [],
        "provider_actors": [external_factory_codex_actor(actor_id)],
        "answer": "dynamic external Codex answer",
    }
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_FACTORY_POLL_INTERVAL", "0.01")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(
            provider_order=("factory",), model_overrides={"factory": ("codex",)}, timeout=2,
        ).generate("use dynamic broker", None, "resp-dynamic-broker", execution_mode="codex")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "completed"
    assert result.technical["selected_runner"] == "codex"
    assert [task["target_node"] for task in state["submitted"]] == [actor_id]


def test_factory_codex_rejects_dedicated_actor_with_stale_auth_marker(tmp_path, monkeypatch):
    actor = external_factory_codex_actor("dynamic-codex-broker-old-epoch")
    current_binding = {**actor["external_provider_auth"], "credential_id": "current-v2", "epoch": 2}
    state = {
        "nodes": [],
        "provider_actors": [actor],
        "provider_auth_binding": current_binding,
        "answer": "must not execute",
    }
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(
            provider_order=("factory",), model_overrides={"factory": ("codex",)}, timeout=2,
        ).generate("reject stale marker", None, "resp-stale-marker", execution_mode="codex")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "failed"
    assert state.get("submitted", []) == []
    assert result.technical["attempts"][0]["error_type"] == "factory_no_fresh_capable_worker"


def test_factory_external_actor_readiness_drift_fails_closed(
    tmp_path, monkeypatch,
):
    actor = external_factory_codex_actor("dynamic-codex-broker-invalid")
    actor["runner_readiness"]["codex"]["login_status"] = "unauthenticated"
    state = {"nodes": [actor], "answer": "must not execute"}
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(
            provider_order=("factory",), model_overrides={"factory": ("codex",)}, timeout=2,
        ).generate("reject drift", None, "resp-broker-drift", execution_mode="codex")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "failed"
    assert state.get("submitted", []) == []
    assert result.technical["attempts"][0]["error_type"] == "factory_no_fresh_capable_worker"


def test_factory_external_actor_stale_attestation_fails_closed(tmp_path, monkeypatch):
    actor = external_factory_codex_actor("dynamic-codex-broker-stale")
    stale = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
    actor["runner_readiness"]["codex"]["checked_at"] = stale
    actor["runners"]["codex"]["checked_at"] = stale
    state = {"nodes": [actor], "answer": "must not execute"}
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(
            provider_order=("factory",), model_overrides={"factory": ("codex",)}, timeout=2,
        ).generate("reject stale broker", None, "resp-broker-stale", execution_mode="codex")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "failed"
    assert state.get("submitted", []) == []
    assert result.technical["attempts"][0]["error_type"] == "factory_no_fresh_capable_worker"


def test_factory_runner_route_budget_prevents_three_serial_timeout_taxes(
    tmp_path, monkeypatch,
):
    state = {
        "nodes": [fresh_factory_node(f"timeout-worker-{index}") for index in range(3)],
        "mode": "running",
    }
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_FACTORY_TASK_TIMEOUT", "0.2")
    monkeypatch.setenv("KOLIBRI_FACTORY_POLL_INTERVAL", "0.01")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(
            provider_order=("factory",), model_overrides={"factory": ("mimo",)}, timeout=2,
        ).generate("bounded timeout", None, "resp-bounded-timeout")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "failed"
    assert len(state.get("submitted", [])) == 1
    assert result.technical["attempts"][0]["error_type"] == "provider_timeout"


def test_factory_known_unhealthy_mimo_falls_through_to_codex_without_doomed_task(
    tmp_path, monkeypatch,
):
    now = datetime.now(timezone.utc)
    node = fresh_factory_node("dual-runner-worker")
    state = {
        "nodes": [node],
        "provider_health": {"mimo": [
            factory_health_record(
                "dual-runner-worker", observed_at=now, duration_seconds=45,
                status="open", reason="provider_timeout",
            ),
        ]},
        "answer": "codex without timeout tax",
    }
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_FACTORY_PROVIDER_RUNNERS", "mimo,codex")
    monkeypatch.setenv("KOLIBRI_FACTORY_POLL_INTERVAL", "0.01")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(timeout=2).generate(
            "Mimo first, health aware", None, "resp-health-fallback",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "completed"
    assert result.text == "codex without timeout tax"
    assert [attempt["provider_model"] for attempt in result.technical["attempts"]] == [
        "mimo", "codex",
    ]
    assert result.technical["attempts"][0]["error_type"] == (
        "factory_no_healthy_capable_worker"
    )
    assert result.technical["selected_runner"] == "codex"
    assert [task["runner"] for task in state["submitted"]] == ["codex"]


def test_later_verified_mimo_completion_closes_prior_timeout_circuit(
    tmp_path, monkeypatch,
):
    now = datetime.now(timezone.utc)
    node = fresh_factory_node("recovered-mimo-worker")
    state = {
        "nodes": [node],
        "provider_health": {"mimo": [
            factory_health_record(
                "recovered-mimo-worker", observed_at=now - timedelta(seconds=30),
                duration_seconds=45, status="open", reason="provider_timeout",
            ),
            factory_health_record(
                "recovered-mimo-worker", observed_at=now, duration_seconds=27,
                status="healthy", reason="verified_completion",
            ),
        ]},
        "answer": "Mimo recovered",
    }
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_FACTORY_POLL_INTERVAL", "0.01")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(
            provider_order=("factory",), model_overrides={"factory": ("mimo",)}, timeout=2,
        ).generate("use recovered Mimo", None, "resp-health-recovered")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "completed"
    assert result.technical["selected_runner"] == "mimo"
    assert [task["target_node"] for task in state["submitted"]] == [
        "recovered-mimo-worker"
    ]


def test_factory_provider_idempotency_is_stable_and_does_not_embed_prompt(tmp_path, monkeypatch):
    state = {"nodes": [fresh_factory_node()], "answer": "stable"}
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_FACTORY_POLL_INTERVAL", "0.01")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    gateway = ProviderGateway(
        provider_order=("factory",), model_overrides={"factory": ("mimo",)}, timeout=2,
    )
    prompt = "private prompt must not appear in idempotency metadata"
    try:
        first = gateway.generate(prompt, None, "same-response")
        second = gateway.generate(prompt, None, "same-response")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert first.status == second.status == "completed"
    assert state["submitted"][0]["task_id"] == state["submitted"][1]["task_id"]
    assert state["submitted"][0]["idempotency_key"] == state["submitted"][1]["idempotency_key"]
    assert prompt not in state["submitted"][0]["idempotency_key"]
    route = first.technical["attempts"][0]["factory_route_attempts"][0]
    assert "idempotency_key" not in route
    assert len(route["idempotency_sha256"]) == 64


def test_factory_provider_rejects_unfenced_completed_task(tmp_path, monkeypatch):
    state = {"nodes": [fresh_factory_node()], "mode": "bad_fence"}
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_FACTORY_POLL_INTERVAL", "0.01")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(
            provider_order=("factory",), model_overrides={"factory": ("mimo",)}, timeout=2,
        ).generate("must be fenced", None, "resp-bad-fence")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "failed" and result.text == ""
    assert result.technical["attempts"][0]["error_type"] == "factory_evidence_invalid"
    assert result.technical["evidence"] == []


def test_factory_provider_rejects_legacy_dangerous_runner_contract(tmp_path, monkeypatch):
    unsafe = fresh_factory_node("legacy-worker")
    unsafe["runners"]["mimo"] = {
        "status": "available",
        "permission_mode": "auto_approve_with_task_contract",
        "output_format": "json",
        "worktree_scoped": True,
    }
    state = {"nodes": [unsafe]}
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(
            provider_order=("factory",), model_overrides={"factory": ("mimo",)}, timeout=1,
        ).generate("never enter argv", None, "resp-unsafe-runner")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "failed"
    assert result.technical["attempts"][0]["error_type"] == "factory_no_fresh_capable_worker"
    assert state.get("submitted") is None


def test_factory_provider_poll_is_bounded_and_cancels_its_task(tmp_path, monkeypatch):
    state = {"nodes": [fresh_factory_node()], "mode": "running"}
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_FACTORY_POLL_INTERVAL", "0.01")
    monkeypatch.setenv("KOLIBRI_FACTORY_TASK_TIMEOUT", "0.1")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    started = __import__("time").monotonic()
    try:
        result = ProviderGateway(
            provider_order=("factory",), model_overrides={"factory": ("mimo",)}, timeout=1,
        ).generate("bounded", None, "resp-timeout")
    finally:
        elapsed = __import__("time").monotonic() - started
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert elapsed < 1
    assert result.status == "failed"
    assert result.technical["attempts"][0]["error_type"] == "provider_timeout"
    assert state["cancelled"] == [{"reason": "factory_provider_poll_timeout"}]


def test_factory_control_secret_and_error_body_never_enter_provenance(tmp_path, monkeypatch):
    secret = "factory-secret-never-log"
    state = {
        "nodes": [], "http_error": 401,
        "secret_body": f"Bearer {secret} internal upstream details",
    }
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_FACTORY_CONTROL_TOKEN", secret)
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(
            provider_order=("factory",), model_overrides={"factory": ("mimo",)}, timeout=1,
        ).generate("safe", None, "resp-auth")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert state["authorization"][0] == f"Bearer {secret}"
    assert result.technical["attempts"][0]["error_type"] == "factory_control_auth_failed"
    assert secret not in json.dumps(result.technical)
    assert "internal upstream details" not in json.dumps(result.technical)


def test_factory_control_endpoint_fails_closed_for_non_home_or_multiple_authorities(
    tmp_path, monkeypatch,
):
    configure_local_home_control(monkeypatch, tmp_path, "http://127.0.0.1:9101")
    monkeypatch.setenv("KOLIBRI_FACTORY_CONTROL_URL", "http://10.99.0.77:9101")
    assert _factory_control_endpoint() is None
    monkeypatch.setenv("KOLIBRI_FACTORY_CONTROL_URL", "http://127.0.0.1:9101")
    monkeypatch.setenv("KOLIBRI_FACTORY_CONTROL_URLS", "http://10.99.0.1:9101")
    assert _factory_control_endpoint() is None


def test_factory_default_route_activates_only_with_single_home_endpoint(tmp_path, monkeypatch):
    monkeypatch.delenv("KOLIBRI_PROVIDER_ORDER", raising=False)
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URL", raising=False)
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URLS", raising=False)
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work-a"))
    assert "factory" not in ProviderGateway(timeout=1).provider_order
    configure_local_home_control(monkeypatch, tmp_path, "http://127.0.0.1:9101")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work-b"))
    assert ProviderGateway(timeout=1).provider_order == ("factory",)


def test_configured_factory_never_falls_through_to_direct_backend_runners(tmp_path, monkeypatch):
    mimo_marker = tmp_path / "mimo-direct-ran"
    codex_marker = tmp_path / "codex-direct-ran"
    mimo = executable(tmp_path / "mimo", f"touch '{mimo_marker}'\nexit 0\n")
    codex = executable(tmp_path / "codex", f"touch '{codex_marker}'\nexit 0\n")
    monkeypatch.setenv("KOLIBRI_MIMO_BIN", mimo)
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", codex)
    configure_local_home_control(monkeypatch, tmp_path, "http://10.99.0.77:9101")
    monkeypatch.setenv("KOLIBRI_PROVIDER_ORDER", "factory,mimo,codex")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))

    result = ProviderGateway(timeout=0.1).generate("never bypass Home", None, "resp-no-bypass")

    assert result.status == "failed"
    assert [attempt["provider"] for attempt in result.technical["attempts"]] == ["factory", "factory"]
    assert [attempt["provider_model"] for attempt in result.technical["attempts"]] == ["mimo", "codex"]
    assert {attempt["error_type"] for attempt in result.technical["attempts"]} == {
        "factory_control_endpoint_invalid",
    }
    assert not mimo_marker.exists()
    assert not codex_marker.exists()


def test_factory_fallback_is_mimo_then_codex_as_separate_home_tasks(tmp_path, monkeypatch):
    state = {
        "nodes": [fresh_factory_node("dynamic-provider-worker")],
        "failed_runners": {"mimo"},
        "answer": "codex factory fallback",
    }
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_PROVIDER_ORDER", "factory,mimo,codex")
    monkeypatch.setenv("KOLIBRI_FACTORY_PROVIDER_RUNNERS", "mimo,codex")
    monkeypatch.setenv("KOLIBRI_FACTORY_POLL_INTERVAL", "0.01")
    monkeypatch.setenv("KOLIBRI_FACTORY_TASK_TIMEOUT", "1")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(timeout=2).generate(
            "use real Home fallback", None, "resp-home-fallback",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "completed"
    assert result.text == "codex factory fallback"
    assert result.technical["selected_provider"] == "factory"
    assert result.technical["selected_runner"] == "codex"
    assert result.technical["fallback_used"] is True
    assert [task["runner"] for task in state["submitted"]] == ["mimo", "codex"]
    assert {task["source"]["control_plane"] for task in state["submitted"]} == {"home"}
    assert all(task["fallback_allowed"] is False for task in state["submitted"])
    assert [attempt["provider"] for attempt in result.technical["attempts"]] == ["factory", "factory"]


def test_fast_mode_preserves_configured_home_runner_order(tmp_path, monkeypatch):
    state = {
        "nodes": [fresh_factory_node("fast-mode-worker")],
        "failed_runners": {"codex"},
        "answer": "mimo after configured codex",
    }
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_FACTORY_PROVIDER_RUNNERS", "codex,mimo")
    monkeypatch.setenv("KOLIBRI_FACTORY_POLL_INTERVAL", "0.01")
    monkeypatch.setenv("KOLIBRI_FACTORY_TASK_TIMEOUT", "1")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(timeout=2).generate(
            "preserve the Home runner policy", None, "resp-fast-order",
            execution_mode="fast",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "completed"
    assert result.technical["selected_provider"] == "factory"
    assert result.technical["selected_runner"] == "mimo"
    assert [task["runner"] for task in state["submitted"]] == ["codex", "mimo"]
    assert {task["source"]["control_plane"] for task in state["submitted"]} == {"home"}


def test_fast_mode_rejects_mimo_identity_leak_and_falls_back_to_codex(tmp_path, monkeypatch):
    state = {
        "nodes": [fresh_factory_node("identity-contract-worker")],
        "answers_by_runner": {
            "mimo": "Я — MiMo Code Agent.",
            "codex": "Я Kolibri. Чем помочь?",
        },
    }
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_FACTORY_PROVIDER_RUNNERS", "mimo,codex")
    monkeypatch.setenv("KOLIBRI_FACTORY_POLL_INTERVAL", "0.01")
    monkeypatch.setenv("KOLIBRI_FACTORY_TASK_TIMEOUT", "1")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    typed_instruction = "Return one JSON object only, without Markdown fences or commentary."
    try:
        result = ProviderGateway(timeout=2).generate(
            "Кто ты?", typed_instruction, "resp-fast-identity-contract",
            execution_mode="fast",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "completed"
    assert result.text == "Я Kolibri. Чем помочь?"
    assert result.technical["selected_runner"] == "codex"
    assert result.technical["attempts"][0]["error_type"] == "provider_identity_contract_violation"
    assert result.technical["attempts"][1]["status"] == "succeeded"
    assert [task["runner"] for task in state["submitted"]] == ["mimo", "codex"]
    assert all(
        task["source"]["identity_contract"] == "kolibri.public-identity.v1"
        for task in state["submitted"]
    )
    assert all(typed_instruction in task["objective"] for task in state["submitted"])
    assert all("You are Kolibri" in task["objective"] for task in state["submitted"])


def test_codex_mode_rejects_identity_leak_without_silent_mimo_fallback(tmp_path, monkeypatch):
    state = {
        "nodes": [fresh_factory_node("identity-contract-worker")],
        "answers_by_runner": {
            "codex": "I am Codex.",
            "mimo": "Я Kolibri. Чем помочь?",
        },
    }
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_FACTORY_PROVIDER_RUNNERS", "mimo,codex")
    monkeypatch.setenv("KOLIBRI_FACTORY_POLL_INTERVAL", "0.01")
    monkeypatch.setenv("KOLIBRI_FACTORY_TASK_TIMEOUT", "1")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(timeout=2).generate(
            "Who are you?", None, "resp-codex-identity-contract",
            execution_mode="codex",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "failed"
    assert result.text == ""
    assert result.technical["selected_provider"] is None
    assert result.technical["attempts"][0]["error_type"] == "provider_identity_contract_violation"
    assert len(result.technical["attempts"]) == 1
    assert [task["runner"] for task in state["submitted"]] == ["codex"]


def test_codex_mode_is_strict_when_codex_runner_fails(tmp_path, monkeypatch):
    state = {
        "nodes": [fresh_factory_node("codex-mode-worker")],
        "failed_runners": {"codex"},
        "answer": "mimo fallback after codex",
    }
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_FACTORY_PROVIDER_RUNNERS", "mimo,codex")
    monkeypatch.setenv("KOLIBRI_FACTORY_POLL_INTERVAL", "0.01")
    monkeypatch.setenv("KOLIBRI_FACTORY_TASK_TIMEOUT", "1")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(timeout=2).generate(
            "prefer Codex but remain on Home", None, "resp-codex-order",
            execution_mode="codex",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "failed"
    assert result.technical["selected_provider"] is None
    assert result.technical["fallback_used"] is False
    assert [task["runner"] for task in state["submitted"]] == ["codex"]
    assert {task["source"]["control_plane"] for task in state["submitted"]} == {"home"}
    assert all(task["fallback_allowed"] is False for task in state["submitted"])


def test_codex_mode_with_zero_eligible_codex_never_submits_mimo(tmp_path, monkeypatch):
    mimo_only = fresh_factory_node("mimo-only-worker")
    mimo_only["capabilities"] = ["generic_implementation", "runner:mimo"]
    mimo_only["runners"].pop("codex")
    state = {"nodes": [mimo_only], "answer": "must not be used"}
    server, thread = factory_control_server(state)
    configure_local_home_control(
        monkeypatch, tmp_path, f"http://127.0.0.1:{server.server_port}",
    )
    monkeypatch.setenv("KOLIBRI_FACTORY_PROVIDER_RUNNERS", "mimo,codex")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))
    try:
        result = ProviderGateway(timeout=2).generate(
            "strict Codex", None, "resp-codex-zero-eligible", execution_mode="codex",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == "failed"
    assert result.technical["fallback_used"] is False
    assert [attempt["provider_model"] for attempt in result.technical["attempts"]] == [
        "codex"
    ]
    assert result.technical["attempts"][0]["error_type"] == (
        "factory_no_fresh_capable_worker"
    )
    assert state.get("submitted") is None


def test_codex_mode_never_bypasses_an_invalid_configured_home_boundary(tmp_path, monkeypatch):
    mimo_marker = tmp_path / "mimo-direct-ran"
    codex_marker = tmp_path / "codex-direct-ran"
    mimo = executable(tmp_path / "mimo", f"touch '{mimo_marker}'\nexit 0\n")
    codex = executable(tmp_path / "codex", f"touch '{codex_marker}'\nexit 0\n")
    monkeypatch.setenv("KOLIBRI_MIMO_BIN", mimo)
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", codex)
    configure_local_home_control(monkeypatch, tmp_path, "http://10.99.0.77:9101")
    monkeypatch.setenv("KOLIBRI_PROVIDER_ORDER", "factory,mimo,codex")
    monkeypatch.setenv("KOLIBRI_FACTORY_PROVIDER_RUNNERS", "mimo,codex")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))

    result = ProviderGateway(timeout=0.1).generate(
        "never bypass Home for Codex", None, "resp-codex-no-bypass",
        execution_mode="codex",
    )

    assert result.status == "failed"
    assert [attempt["provider"] for attempt in result.technical["attempts"]] == ["factory"]
    assert [attempt["provider_model"] for attempt in result.technical["attempts"]] == ["codex"]
    assert {attempt["error_type"] for attempt in result.technical["attempts"]} == {
        "factory_control_endpoint_invalid",
    }
    assert not mimo_marker.exists()
    assert not codex_marker.exists()


def test_production_without_home_endpoint_fails_closed_before_direct_runners(tmp_path, monkeypatch):
    mimo_marker = tmp_path / "mimo-direct-ran"
    codex_marker = tmp_path / "codex-direct-ran"
    mimo = executable(tmp_path / "mimo", f"touch '{mimo_marker}'\nexit 0\n")
    codex = executable(tmp_path / "codex", f"touch '{codex_marker}'\nexit 0\n")
    monkeypatch.setenv("KOLIBRI_ENV", "production")
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URL", raising=False)
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URLS", raising=False)
    monkeypatch.setenv("KOLIBRI_MIMO_BIN", mimo)
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", codex)
    monkeypatch.setenv("KOLIBRI_PROVIDER_ORDER", "mimo,codex")
    monkeypatch.setenv("KOLIBRI_PROVIDER_WORK_DIR", str(tmp_path / "work"))

    gateway = ProviderGateway(timeout=0.1)
    result = gateway.generate(
        "production requires Home", None, "resp-production-no-home",
        execution_mode="codex",
    )

    assert gateway.provider_order == ("factory",)
    assert result.status == "failed"
    assert [attempt["provider"] for attempt in result.technical["attempts"]] == ["factory"]
    assert [attempt["provider_model"] for attempt in result.technical["attempts"]] == ["codex"]
    assert {attempt["error_type"] for attempt in result.technical["attempts"]} == {
        "factory_control_endpoint_invalid",
    }
    assert not mimo_marker.exists()
    assert not codex_marker.exists()
