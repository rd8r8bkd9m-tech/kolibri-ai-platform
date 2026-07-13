import json
import hashlib
import stat
import textwrap
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.codex_cli_provider import get_codex_cli_provider
from app.routers import openai_compat

_API_KEY = "public-test-key"
_AUTH = {"Authorization": f"Bearer {_API_KEY}"}


def _fake_codex(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "codex-public-fake"
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys, time\n"
        + textwrap.dedent(body),
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _configure_fake_codex(monkeypatch, binary: Path, cwd: Path) -> None:
    monkeypatch.setenv("CODEX_CLI_BINARY", str(binary))
    monkeypatch.setenv("CODEX_CLI_CWD", str(cwd))
    monkeypatch.setenv("CODEX_CLI_WEB_SEARCH", "disabled")
    monkeypatch.setenv("CODEX_CLI_ATTEMPT_TIMEOUT_SECONDS", "20")
    openai_compat.ai_provider._provider_blocked_until.pop("codex_cli", None)


@pytest.fixture(autouse=True)
def reset_registry(monkeypatch):
    monkeypatch.setenv("KOLIBRI_PUBLIC_API_KEY_SHA256", hashlib.sha256(_API_KEY.encode()).hexdigest())
    openai_compat._records.clear()
    openai_compat._idempotency.clear()
    yield
    openai_compat._records.clear()
    openai_compat._idempotency.clear()


def test_models_exposes_only_public_kolibri_model():
    with TestClient(app) as client:
        response = client.get("/v1/models", headers=_AUTH)

    assert response.status_code == 200
    assert response.json() == {
        "object": "list",
        "data": [{"id": "kolibri", "object": "model", "created": 0, "owned_by": "kolibri"}],
    }


def test_responses_sync_is_sanitized_and_retrievable(monkeypatch):
    captured = {}

    async def fake_completion(messages, **kwargs):
        captured.update(kwargs)
        return {
            "content": "Проверенный ответ",
            "status": "idle",
            "provider": "openai_codex",
            "model": "gpt-5.6-sol",
            "response_id": "resp_upstream_1",
        }

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", fake_completion)
    body = {
        "model": "kolibri",
        "input": "Привет",
        "policy": {
            "mode": "deep",
            "reasoning_effort": "high",
            "tool_choice": "auto",
            "background": False,
            "allowed_capabilities": ["openai.web_search"],
        },
    }
    with TestClient(app) as client:
        created = client.post("/v1/responses", json=body, headers={**_AUTH, "Idempotency-Key": "request-1"})
        fetched = client.get(f"/v1/responses/{created.json()['id']}", headers=_AUTH)

    assert created.status_code == 200
    assert fetched.status_code == 200
    assert created.json() == fetched.json()
    payload = created.json()
    assert payload["model"] == "kolibri"
    assert payload["status"] == "completed"
    assert payload["output_text"] == "Проверенный ответ"
    serialized = json.dumps(payload)
    assert "openai_codex" not in serialized
    assert "gpt-5.6-sol" not in serialized
    assert captured["task_type"] == "analyze"
    assert captured["policy"]["allowed_capabilities"] == ["openai.web_search"]
    assert captured["idempotency_key"] == "request-1"


def test_responses_idempotency_replays_and_conflicts(monkeypatch):
    calls = 0

    async def fake_completion(messages, **kwargs):
        nonlocal calls
        calls += 1
        return {"content": "Один ответ", "status": "idle", "provider": "mimo"}

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", fake_completion)
    with TestClient(app) as client:
        first = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "Один запрос"},
            headers={**_AUTH, "Idempotency-Key": "same-key"},
        )
        replay = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "Один запрос"},
            headers={**_AUTH, "Idempotency-Key": "same-key"},
        )
        conflict = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "Другой запрос"},
            headers={**_AUTH, "Idempotency-Key": "same-key"},
        )

    assert first.json()["id"] == replay.json()["id"]
    assert calls == 1
    assert conflict.status_code == 409


def test_responses_stream_uses_typed_sse_and_hides_provider(monkeypatch):
    captured = {}

    async def fake_stream(messages, **kwargs):
        captured.update(kwargs)
        yield {
            "content": "",
            "done": False,
            "work_summary": {"stage": "provider_route", "summary": "Ищу", "status": "active", "provider": "secret"},
        }
        yield {
            "content": "",
            "done": False,
            "tool_event": {
                "type": "tool.started",
                "tool": "codex.web_search",
                "label": "Ищу актуальные источники",
                "status": "active",
            },
        }
        yield {
            "content": "",
            "done": False,
            "tool_event": {
                "type": "tool.completed",
                "tool": "codex.web_search",
                "label": "Ищу актуальные источники",
                "status": "completed",
            },
        }
        yield {"content": "При", "done": False}
        yield {"content": "вет", "done": False}
        yield {"content": "", "done": True, "status": "idle", "provider": "mimo", "model": "private"}

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion_stream", fake_stream)
    with TestClient(app) as client:
        response = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "Привет", "stream": True},
            headers=_AUTH,
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: response.created" in response.text
    assert "event: response.work_summary.updated" in response.text
    assert "event: response.tool.started" in response.text
    assert "event: response.tool.completed" in response.text
    assert response.text.count("event: response.output_text.delta") == 2
    assert "event: response.completed" in response.text
    assert "mimo" not in response.text
    assert "private" not in response.text
    assert "secret" not in response.text
    assert captured["run_id"].startswith("resp_kolibri_")


def test_public_stream_maps_real_codex_cli_jsonl_events(monkeypatch, tmp_path):
    binary = _fake_codex(
        tmp_path,
        """
        _ = sys.stdin.read()
        print(json.dumps({'type':'thread.started','thread_id':'private'}), flush=True)
        print(json.dumps({'type':'turn.started'}), flush=True)
        print(json.dumps({'type':'item.started','item':{'id':'cmd','type':'command_execution','command':'hidden'}}), flush=True)
        print(json.dumps({'type':'item.completed','item':{'id':'cmd','type':'command_execution','command':'hidden'}}), flush=True)
        print(json.dumps({'type':'item.completed','item':{'id':'answer','type':'agent_message','text':'Привет'}}), flush=True)
        print(json.dumps({'type':'turn.completed'}), flush=True)
        """,
    )
    _configure_fake_codex(monkeypatch, binary, tmp_path)

    with TestClient(app) as client:
        response = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "Ответь", "stream": True},
            headers=_AUTH,
        )

    assert response.status_code == 200
    assert "event: response.work_summary.updated" in response.text
    assert "event: response.tool.started" in response.text
    assert "event: response.tool.completed" in response.text
    assert "event: response.output_text.delta" in response.text
    assert "event: response.completed" in response.text
    assert "hidden" not in response.text
    assert "private" not in response.text


def test_cancel_endpoint_terminates_running_codex_process_and_is_idempotent(
    monkeypatch, tmp_path
):
    marker = tmp_path / "late-result"
    binary = _fake_codex(
        tmp_path,
        f"""
        _ = sys.stdin.read()
        print(json.dumps({{'type':'thread.started','thread_id':'private'}}), flush=True)
        print(json.dumps({{'type':'turn.started'}}), flush=True)
        time.sleep(15)
        open({str(marker)!r}, 'w', encoding='utf-8').write('should-not-exist')
        print(json.dumps({{'type':'item.completed','item':{{'id':'answer','type':'agent_message','text':'late'}}}}), flush=True)
        print(json.dumps({{'type':'turn.completed'}}), flush=True)
        """,
    )
    _configure_fake_codex(monkeypatch, binary, tmp_path)
    result: dict[str, object] = {}

    with TestClient(app) as client:
        def request_worker() -> None:
            result["response"] = client.post(
                "/v1/responses",
                json={"model": "kolibri", "input": "Долгая операция", "stream": True},
                headers=_AUTH,
            )

        worker = threading.Thread(target=request_worker, daemon=True)
        worker.start()
        deadline = time.monotonic() + 5
        response_id = ""
        provider = get_codex_cli_provider()
        while time.monotonic() < deadline:
            active_ids = list(provider._active)  # exact process ownership is the tested invariant
            if active_ids:
                response_id = active_ids[0]
                break
            time.sleep(0.02)
        assert response_id.startswith("resp_kolibri_")

        cancelled = client.post(f"/v1/responses/{response_id}/cancel", headers=_AUTH)
        repeated = client.post(f"/v1/responses/{response_id}/cancel", headers=_AUTH)
        unknown = client.post("/v1/responses/resp_kolibri_unknown/cancel", headers=_AUTH)
        worker.join(timeout=5)

    assert not worker.is_alive()
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "cancelled"
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["code"] == "response_not_found"
    assert not marker.exists()
    streamed = result["response"]
    assert "event: response.cancelled" in streamed.text
    terminal_events = openai_compat._records[response_id]["events"]
    assert [event["type"] for event in terminal_events].count("response.cancelled") == 1


def test_background_response_status_and_cancel_are_truthful(monkeypatch):
    async def fake_completion(messages, **kwargs):
        return {
            "content": "",
            "status": "queued",
            "provider": "openai_codex",
            "response_id": "resp_upstream_bg",
        }

    async def fake_retrieve(provider, response_id):
        assert response_id == "resp_upstream_bg"
        return {
            "id": response_id,
            "status": "in_progress",
            "content": "",
            "reasoning_summary": "",
            "tool_events": [],
        }

    cancelled = []

    async def fake_cancel(provider, response_id):
        cancelled.append(response_id)
        return {"id": response_id, "status": "cancelled", "content": ""}

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", fake_completion)
    monkeypatch.setattr(openai_compat, "retrieve_response", fake_retrieve)
    monkeypatch.setattr(openai_compat, "cancel_response", fake_cancel)
    with TestClient(app) as client:
        created = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "Долгая задача", "background": True},
            headers=_AUTH,
        )
        response_id = created.json()["id"]
        status = client.get(f"/v1/responses/{response_id}", headers=_AUTH)
        cancel = client.post(f"/v1/responses/{response_id}/cancel", headers=_AUTH)
        repeat = client.post(f"/v1/responses/{response_id}/cancel", headers=_AUTH)

    assert created.json()["status"] == "queued"
    assert status.json()["status"] == "in_progress"
    assert cancel.json()["status"] == "cancelled"
    assert repeat.json()["status"] == "cancelled"
    assert cancelled == ["resp_upstream_bg"]


def test_chat_completions_and_realtime_contracts(monkeypatch):
    async def fake_completion(messages, **kwargs):
        return {"content": "Ответ", "status": "idle"}

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", fake_completion)
    with TestClient(app) as client:
        chat = client.post(
            "/v1/chat/completions",
            json={"model": "kolibri", "messages": [{"role": "user", "content": "Привет"}]},
            headers=_AUTH,
        )
        realtime = client.post("/v1/realtime", json={}, headers=_AUTH)
        unknown = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-private", "messages": [{"role": "user", "content": "Привет"}]},
            headers=_AUTH,
        )

    assert chat.status_code == 200
    assert chat.json()["model"] == "kolibri"
    assert chat.json()["choices"][0]["message"]["content"] == "Ответ"
    assert realtime.status_code == 501
    assert realtime.headers["content-type"].startswith("application/json")
    assert unknown.status_code == 404


def test_public_api_auth_fails_closed_before_provider(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("provider must not be called before public API authentication")

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", forbidden)
    monkeypatch.delenv("KOLIBRI_PUBLIC_API_KEY_SHA256", raising=False)
    with TestClient(app) as client:
        unconfigured = client.post("/v1/responses", json={"model": "kolibri", "input": "Hello"})

    monkeypatch.setenv("KOLIBRI_PUBLIC_API_KEY_SHA256", hashlib.sha256(_API_KEY.encode()).hexdigest())
    with TestClient(app) as client:
        missing = client.post("/v1/responses", json={"model": "kolibri", "input": "Hello"})
        invalid = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "Hello"},
            headers={"Authorization": "Bearer wrong-key"},
        )

    assert unconfigured.status_code == 503
    assert unconfigured.json()["detail"]["code"] == "public_api_not_configured"
    assert missing.status_code == 401
    assert invalid.status_code == 401


def test_internal_response_alias_has_resume_events_and_chat_rate_limit(monkeypatch):
    async def fake_completion(messages, **kwargs):
        return {"content": "Alias answer", "status": "idle", "provider": "mimo"}

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", fake_completion)
    from app.rate_limiter import chat_limiter

    rate_key = "compat-rate-test"
    chat_limiter._requests.pop(rate_key, None)
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/responses",
            json={"model": "kolibri", "input": "Hello"},
            headers={"X-Forwarded-For": rate_key},
        )
        response_id = created.json()["id"]
        events = client.get(
            f"/api/v1/responses/{response_id}/events?starting_after=0",
            headers={"X-Forwarded-For": rate_key},
        )

        chat_limiter._requests[rate_key] = [openai_compat.time.time()] * chat_limiter.rpm
        limited = client.post(
            "/api/v1/responses",
            json={"model": "kolibri", "input": "Blocked"},
            headers={"X-Forwarded-For": rate_key},
        )
    chat_limiter._requests.pop(rate_key, None)

    assert created.status_code == 200
    assert events.status_code == 200
    assert "event: response.created" in events.text
    assert "event: response.output_text.delta" in events.text
    assert "event: response.completed" in events.text
    assert limited.status_code == 429


def test_invalid_idempotency_key_is_rejected_before_provider(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("provider must not be called for invalid idempotency key")

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", forbidden)
    with TestClient(app) as client:
        response = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "Hello"},
            headers={**_AUTH, "Idempotency-Key": "bad key with spaces"},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_idempotency_key"
