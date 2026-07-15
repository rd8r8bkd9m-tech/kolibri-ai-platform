import asyncio
import json
import hashlib
import stat
import textwrap
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.main import app
from app.codex_cli_provider import get_codex_cli_provider
from app.project_schemas import ProjectMessageMetadata
from app.routers import openai_compat

_API_KEY = "public-test-key"
_AUTH = {"Authorization": f"Bearer {_API_KEY}"}
_API_SCOPE = f"api-key-sha256:{hashlib.sha256(_API_KEY.encode()).hexdigest()}"
_RESPONSE_TEXT_SCHEMA = {
    "format": {
        "type": "json_schema",
        "name": "answer",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "score": {"type": "integer", "minimum": 0, "maximum": 10},
            },
            "required": ["answer", "score"],
            "additionalProperties": False,
        },
    }
}
_CHAT_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        key: value
        for key, value in _RESPONSE_TEXT_SCHEMA["format"].items()
        if key != "type"
    },
}


def _typed_sse_events(raw: str, event_type: str) -> list[dict]:
    events: list[dict] = []
    for block in raw.split("\n\n"):
        lines = block.splitlines()
        if f"event: {event_type}" not in lines:
            continue
        data = next((line[6:] for line in lines if line.startswith("data: ")), None)
        if data:
            events.append(json.loads(data))
    return events


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


def _wait_for_background_tasks(timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with openai_compat._background_tasks_lock:
            tasks = list(openai_compat._background_tasks.values())
        if not tasks or all(task.done() for task in tasks):
            return
        time.sleep(0.02)
    with openai_compat._background_tasks_lock:
        pending = [task for task in openai_compat._background_tasks.values() if not task.done()]
    assert not pending


@pytest.fixture(autouse=True)
def reset_registry(monkeypatch):
    from app.rate_limiter import chat_limiter

    monkeypatch.setenv("KOLIBRI_PUBLIC_API_KEY_SHA256", hashlib.sha256(_API_KEY.encode()).hexdigest())
    openai_compat._records.clear()
    openai_compat._idempotency.clear()
    openai_compat._inflight.clear()
    openai_compat._background_tasks.clear()
    chat_limiter._requests.clear()
    yield
    with openai_compat._background_tasks_lock:
        for task in openai_compat._background_tasks.values():
            if not task.done():
                task.cancel()
        openai_compat._background_tasks.clear()
    openai_compat._records.clear()
    openai_compat._idempotency.clear()
    openai_compat._inflight.clear()
    chat_limiter._requests.clear()


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


def test_responses_sync_preserves_only_public_actions(monkeypatch):
    action = {
        "type": "create_estimate",
        "label": "Открыть предварительную смету",
        "data": {
            "title": "Предварительная смета: дом 100 м² — Лениногорск",
            "region": "Лениногорск, Татарстан",
            "sections": [],
        },
    }

    async def fake_completion(messages, **kwargs):
        return {
            "content": "Смета подготовлена.",
            "actions": [
                action,
                {"type": "internal_provider_action", "label": "secret", "data": {}},
            ],
            "status": "ready",
            "provider": "private-provider",
        }

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", fake_completion)
    with TestClient(app) as client:
        created = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "Составь смету"},
            headers=_AUTH,
        )
        fetched = client.get(f"/v1/responses/{created.json()['id']}", headers=_AUTH)

    assert created.status_code == 200
    assert fetched.status_code == 200
    assert created.json()["actions"] == [action]
    assert fetched.json()["actions"] == [action]
    assert "private-provider" not in json.dumps(created.json())
    terminal = openai_compat._records[created.json()["id"]]["events"][-1]
    assert terminal["type"] == "response.completed"
    assert terminal["actions"] == [action]
    assert terminal["response"]["actions"] == [action]


def test_responses_preserves_only_contract_valid_present_artifact(monkeypatch):
    artifact_id = "d7950ed4-c855-4754-883c-a63af2b85a0b"
    canonical = f"/api/v1/artifacts/{artifact_id}"
    artifact = {
        "id": artifact_id,
        "type": "document.pdf",
        "revision": 1,
        "title": "Проверенный PDF",
        "filename": "report.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 42,
        "sha256": "a" * 64,
        "created_at": "2026-07-14T10:00:00+00:00",
        "updated_at": "2026-07-14T10:00:00+00:00",
        "metadata": {
            "scope_key": "b" * 64,
            "producer_capability": "document.pdf",
        },
        "url": canonical,
        "download_url": f"{canonical}?download=true",
        "revision_url": f"{canonical}?revision=1",
        "revision_download_url": f"{canonical}?revision=1&download=true",
        "reopen_url": f"{canonical}/reopen",
        "history_url": f"{canonical}/history",
    }
    action = {
        "type": "present_artifact",
        "label": "Открыть PDF",
        "data": artifact,
    }

    async def fake_completion(messages, **kwargs):
        malformed = {
            **action,
            "data": {**artifact, "mime_type": "text/html"},
        }
        return {
            "content": "PDF готов.",
            "actions": [action, malformed],
            "status": "ready",
            "provider": "private-provider",
        }

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", fake_completion)
    with TestClient(app) as client:
        created = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "Создай PDF"},
            headers=_AUTH,
        )
        fetched = client.get(f"/v1/responses/{created.json()['id']}", headers=_AUTH)

    assert created.status_code == 200
    assert created.json()["actions"] == [action]
    assert fetched.json()["actions"] == [action]
    assert openai_compat._records[created.json()["id"]]["events"][-1]["actions"] == [action]


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


def test_concurrent_idempotent_responses_invoke_provider_once(monkeypatch):
    calls = 0

    async def fake_completion(messages, **kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return {"content": "Один ответ", "status": "idle"}

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", fake_completion)

    async def execute():
        request = openai_compat.ResponsesRequest(model="kolibri", input="Один запрос")
        return await asyncio.gather(
            openai_compat.execute_kolibri_response(
                request,
                idempotency_key="concurrent-key",
                owner_scope=_API_SCOPE,
            ),
            openai_compat.execute_kolibri_response(
                request,
                idempotency_key="concurrent-key",
                owner_scope=_API_SCOPE,
            ),
        )

    first, second = asyncio.run(execute())
    assert calls == 1
    assert first["id"] == second["id"]
    assert first["content"] == "Один ответ"


def test_response_events_and_scoped_idempotency_survive_backend_restart(monkeypatch):
    calls = 0

    async def fake_completion(messages, **kwargs):
        nonlocal calls
        calls += 1
        return {"content": "Пережил перезапуск", "status": "idle"}

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", fake_completion)
    body = {"model": "kolibri", "input": "Долговечный ответ"}
    headers = {**_AUTH, "Idempotency-Key": "restart-proof"}
    with TestClient(app) as first_process:
        created = first_process.post("/v1/responses", json=body, headers=headers)
    assert created.status_code == 200
    response_id = created.json()["id"]

    # A fresh app lifespan with empty process caches must recover the response,
    # ordered event stream and idempotency claim from SQL authority alone.
    openai_compat._records.clear()
    openai_compat._idempotency.clear()
    openai_compat._inflight.clear()
    with TestClient(app) as restarted_process:
        fetched = restarted_process.get(f"/v1/responses/{response_id}", headers=_AUTH)
        events = restarted_process.get(
            f"/v1/responses/{response_id}/events?starting_after=0",
            headers=_AUTH,
        )
        replay = restarted_process.post("/v1/responses", json=body, headers=headers)

    assert fetched.status_code == 200
    assert fetched.json() == created.json()
    assert "event: response.created" in events.text
    assert "event: response.output_text.delta" in events.text
    assert "event: response.completed" in events.text
    assert replay.status_code == 200
    assert replay.json()["id"] == response_id
    assert calls == 1


def test_response_ownership_and_idempotency_are_scoped_per_api_key(monkeypatch):
    other_key = "second-public-test-key"
    monkeypatch.setenv(
        "KOLIBRI_PUBLIC_API_KEY_SHA256",
        ",".join([
            hashlib.sha256(_API_KEY.encode()).hexdigest(),
            hashlib.sha256(other_key.encode()).hexdigest(),
        ]),
    )
    calls = 0

    async def fake_completion(messages, **kwargs):
        nonlocal calls
        calls += 1
        return {"content": messages[-1]["content"], "status": "idle"}

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", fake_completion)
    other_auth = {"Authorization": f"Bearer {other_key}"}
    with TestClient(app) as client:
        first = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "Первый владелец"},
            headers={**_AUTH, "Idempotency-Key": "shared-key"},
        )
        second = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "Второй владелец"},
            headers={**other_auth, "Idempotency-Key": "shared-key"},
        )
        replay = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "Первый владелец"},
            headers={**_AUTH, "Idempotency-Key": "shared-key"},
        )
        cross_get = client.get(
            f"/v1/responses/{first.json()['id']}", headers=other_auth
        )
        cross_cancel = client.post(
            f"/v1/responses/{first.json()['id']}/cancel", headers=other_auth
        )
        cross_previous = client.post(
            "/v1/responses",
            json={
                "model": "kolibri",
                "input": "Продолжить чужой ответ",
                "previous_response_id": first.json()["id"],
            },
            headers=other_auth,
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] != second.json()["id"]
    assert replay.json()["id"] == first.json()["id"]
    assert calls == 2
    assert cross_get.status_code == 404
    assert cross_cancel.status_code == 404
    assert cross_previous.status_code == 404


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
        live_work_events = _typed_sse_events(
            response.text,
            "response.work_summary.updated",
        )
        response_id = _typed_sse_events(response.text, "response.created")[0][
            "response"
        ]["id"]
        replay = client.get(
            f"/v1/responses/{response_id}/events?starting_after=0",
            headers=_AUTH,
        )
        replay_work_events = _typed_sse_events(
            replay.text,
            "response.work_summary.updated",
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
    assert len(live_work_events) == 1
    assert live_work_events == replay_work_events
    assert live_work_events[0] == next(
        event
        for event in openai_compat._records[response_id]["events"]
        if event["type"] == "response.work_summary.updated"
    )
    assert live_work_events[0]["response_id"] == response_id
    assert isinstance(live_work_events[0]["sequence"], int)
    assert live_work_events[0]["work_summary"] == {
        "kind": "stage",
        "step_id": live_work_events[0]["work_summary"]["step_id"],
        "summary_id": None,
        "stage": "provider_route",
        "status": "active",
        "summary": "Ищу",
        "occurred_at": live_work_events[0]["work_summary"]["occurred_at"],
    }


def test_work_summary_sanitizer_bounds_stage_and_rejects_raw_reasoning():
    response_id = openai_compat.begin_public_response(
        [{"role": "user", "content": "Проверка"}],
        owner_scope=_API_SCOPE,
    )
    appended = openai_compat.record_public_stream_chunk(
        response_id,
        {
            "work_summary": {
                "stage": "private_internal_stage",
                "status": "running",
                "summary": "Codex читает https://secret.example и Bearer abcdefghijklmnop",
                "provider": "mimo",
                "model": "private-model",
            }
        },
    )
    rejected = openai_compat.record_public_stream_chunk(
        response_id,
        {
            "work_summary": {
                "stage": "reasoning_summary",
                "status": "active",
                "summary": "Нельзя сохранять",
                "reasoning_content": "PRIVATE CHAIN OF THOUGHT",
            }
        },
    )

    assert len(appended) == 1
    assert rejected == []
    public = appended[0]["work_summary"]
    assert public["stage"] == "background"
    assert public["status"] == "active"
    assert "Codex" not in public["summary"]
    assert "https://" not in public["summary"]
    assert "Bearer" not in public["summary"]
    serialized = json.dumps(openai_compat._records[response_id], ensure_ascii=False)
    assert "PRIVATE CHAIN" not in serialized
    assert "mimo" not in serialized
    assert "private-model" not in serialized


def test_work_summary_sanitizer_maps_backend_aliases_to_canonical_contract():
    response_id = openai_compat.begin_public_response(
        [{"role": "user", "content": "Проверка"}],
        owner_scope=_API_SCOPE,
    )
    appended: list[dict] = []
    for summary in (
        {
            "stage": "factory_dispatch",
            "status": "waiting",
            "summary": "Задача передана Home Control Plane",
        },
        {
            "stage": "factory_verified",
            "status": "completed",
            "summary": "Результат проверен",
        },
        {
            "stage": "codex_turn",
            "status": "recovering",
            "summary": "Codex продолжает выполнение",
        },
        {
            "stage": "plan_updated",
            "status": "cancelled",
            "summary": "План остановлен",
        },
    ):
        appended.extend(
            openai_compat.record_public_stream_chunk(
                response_id,
                {"work_summary": summary},
            )
        )

    assert [
        (event["work_summary"]["stage"], event["work_summary"]["status"])
        for event in appended
    ] == [
        ("provider_route", "active"),
        ("verification", "completed"),
        ("tool_execution", "active"),
        ("planning", "failed"),
    ]
    public_dump = json.dumps(appended, ensure_ascii=False)
    assert "Home" not in public_dump
    assert "Control Plane" not in public_dump
    assert "Codex" not in public_dump

    metadata = ProjectMessageMetadata(
        work_events=[event["work_summary"] for event in appended]
    ).model_dump(exclude_none=True, exclude_defaults=True)
    assert [
        (event["stage"], event["status"])
        for event in metadata["work_events"]
    ] == [
        ("provider_route", "active"),
        ("verification", "completed"),
        ("tool_execution", "active"),
        ("planning", "failed"),
    ]


def test_persisted_work_trace_metadata_uses_strict_canonical_schema():
    event = {
        "kind": "reasoning_excerpt",
        "step_id": "step_reasoning_1",
        "summary_id": "summary_reasoning_1",
        "stage": "reasoning_summary",
        "status": "completed",
        "summary": "Сверяю источники",
        "occurred_at": "2026-07-14T12:00:00+00:00",
        "provider": "must-not-persist",
        "model": "must-not-persist",
    }
    metadata = ProjectMessageMetadata(work_events=[event]).model_dump(
        exclude_none=True,
        exclude_defaults=True,
    )
    assert metadata["work_events"][0]["summary_id"] == "summary_reasoning_1"
    assert "provider" not in metadata["work_events"][0]
    assert "model" not in metadata["work_events"][0]

    with pytest.raises(ValidationError):
        ProjectMessageMetadata(work_events=[{**event, "stage": "private_stage"}])
    with pytest.raises(ValidationError):
        ProjectMessageMetadata(work_events=[{**event, "summary_id": None}])
    with pytest.raises(ValidationError):
        ProjectMessageMetadata(
            work_events=[{**event, "reasoning_content": "PRIVATE"}]
        )


def test_responses_stream_provider_exception_becomes_terminal_sanitized_failure(monkeypatch):
    async def fake_stream(messages, **kwargs):
        yield {"content": "Частичный ответ", "done": False}
        raise RuntimeError("SECRET provider URL and credential")

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion_stream", fake_stream)
    with TestClient(app) as client:
        response = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "Привет", "stream": True},
            headers=_AUTH,
        )
        response_id = next(iter(openai_compat._records))
        fetched = client.get(f"/v1/responses/{response_id}", headers=_AUTH)

    assert response.status_code == 200
    assert "event: response.output_text.delta" in response.text
    assert "event: response.failed" in response.text
    assert "SECRET" not in response.text
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "failed"
    assert fetched.json()["error"] == {
        "code": "provider_stream_failed",
        "recoverable": True,
        "capability": None,
    }


def test_responses_stream_terminal_event_and_status_preserve_actions(monkeypatch):
    action = {
        "type": "create_document",
        "label": "Создать договор",
        "data": {
            "title": "Договор подряда",
            "type": "contract",
            "content": "<p>Проверенный текст</p>",
        },
    }

    async def fake_stream(messages, **kwargs):
        yield {"content": "Документ подготовлен.", "done": False}
        yield {
            "content": "",
            "done": True,
            "status": "ready",
            "actions": [action],
            "provider": "private-provider",
        }

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion_stream", fake_stream)
    with TestClient(app) as client:
        streamed = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "Подготовь договор", "stream": True},
            headers=_AUTH,
        )
        terminal = next(
            json.loads(line.removeprefix("data: "))
            for line in streamed.text.splitlines()
            if line.startswith("data: ") and '"type": "response.completed"' in line
        )
        fetched = client.get(f"/v1/responses/{terminal['response']['id']}", headers=_AUTH)

    assert streamed.status_code == 200
    assert terminal["actions"] == [action]
    assert terminal["response"]["actions"] == [action]
    assert fetched.json()["actions"] == [action]
    assert "private-provider" not in streamed.text


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
        _wait_for_background_tasks()
        status = client.get(f"/v1/responses/{response_id}", headers=_AUTH)
        cancel = client.post(f"/v1/responses/{response_id}/cancel", headers=_AUTH)
        repeat = client.post(f"/v1/responses/{response_id}/cancel", headers=_AUTH)

    assert created.json()["status"] in {"queued", "in_progress"}
    assert status.json()["status"] == "in_progress"
    assert cancel.json()["status"] == "cancelled"
    assert repeat.json()["status"] == "cancelled"
    assert cancelled == ["resp_upstream_bg"]


def test_background_response_returns_before_completion_cancel_wins_and_retry_completes(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    calls: list[bool] = []

    async def fake_completion(messages, **kwargs):
        is_background = bool(kwargs["background"])
        calls.append(is_background)
        if is_background:
            started.set()
            await asyncio.to_thread(release.wait)
            return {
                "content": "Поздний фоновый результат",
                "status": "idle",
                "provider": "test-provider",
            }
        return {
            "content": "Повтор выполнен",
            "status": "idle",
            "provider": "test-provider",
        }

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", fake_completion)
    body = {"model": "kolibri", "input": "Долгая фоновая задача", "background": True}
    headers = {**_AUTH, "Idempotency-Key": "background-create"}

    with TestClient(app) as client:
        created = client.post("/v1/responses", json=body, headers=headers)
        replay = client.post("/v1/responses", json=body, headers=headers)
        conflict = client.post(
            "/v1/responses",
            json={**body, "input": "Другая фоновая задача"},
            headers=headers,
        )
        response_id = created.json()["id"]
        assert started.wait(1)
        cancelled = client.post(f"/v1/responses/{response_id}/cancel", headers=_AUTH)
        release.set()
        _wait_for_background_tasks()
        fetched = client.get(f"/v1/responses/{response_id}", headers=_AUTH)
        retried = client.post(
            f"/v1/responses/{response_id}/retry",
            headers={**_AUTH, "Idempotency-Key": "retry-background"},
        )
        retry_replay = client.post(
            f"/v1/responses/{response_id}/retry",
            headers={**_AUTH, "Idempotency-Key": "retry-background"},
        )

    assert created.status_code == 200
    assert created.json()["status"] in {"queued", "in_progress"}
    assert created.json()["output_text"] == ""
    assert replay.status_code == 200
    assert replay.json()["id"] == response_id
    assert conflict.status_code == 409
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert fetched.json()["status"] == "cancelled"
    assert fetched.json()["output_text"] == ""
    terminal_types = [event["type"] for event in openai_compat._records[response_id]["events"]]
    assert terminal_types.count("response.cancelled") == 1
    assert "response.completed" not in terminal_types
    assert retried.status_code == 200
    assert retried.json()["status"] == "completed"
    assert retried.json()["output_text"] == "Повтор выполнен"
    assert retried.json()["retry_of"] == response_id
    assert retry_replay.json()["id"] == retried.json()["id"]
    assert calls == [True, False]


def test_streaming_background_response_remains_nonterminal_and_replayable(monkeypatch):
    async def fake_stream(messages, **kwargs):
        assert kwargs["background"] is True
        yield {
            "content": "",
            "done": True,
            "status": "queued",
            "provider": "openai_codex",
            "response_id": "resp_upstream_stream_bg",
        }

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion_stream", fake_stream)
    with TestClient(app) as client:
        streamed = client.post(
            "/v1/responses",
            json={
                "model": "kolibri",
                "input": "Долгая потоковая задача",
                "background": True,
                "stream": True,
            },
            headers=_AUTH,
        )

    created = _typed_sse_events(streamed.text, "response.created")
    updates = _typed_sse_events(streamed.text, "response.status.updated")
    assert streamed.status_code == 200
    assert len(created) == 1
    response_id = created[0]["response"]["id"]
    assert updates[-1]["status"] == "queued"
    assert updates[-1]["response"]["status"] == "queued"
    assert "event: response.completed" not in streamed.text
    assert "event: response.failed" not in streamed.text
    assert "event: response.cancelled" not in streamed.text
    assert openai_compat._records[response_id]["status"] == "queued"
    assert openai_compat._records[response_id]["upstream_response_id"] == "resp_upstream_stream_bg"
    assert [event["type"] for event in openai_compat._records[response_id]["events"]][-1] == "response.status.updated"


def test_legacy_chat_recorder_keeps_background_status_nonterminal():
    response_id = openai_compat.begin_public_response(
        [{"role": "user", "content": "Долгая задача"}],
        owner_scope=_API_SCOPE,
    )

    queued = openai_compat.record_public_stream_chunk(
        response_id,
        {
            "content": "",
            "done": True,
            "status": "in_progress",
            "provider": "openai_codex",
            "response_id": "resp_upstream_legacy_bg",
        },
    )

    assert [event["type"] for event in queued] == ["response.status.updated"]
    assert openai_compat._records[response_id]["status"] == "in_progress"
    assert not any(
        event["type"] in {"response.completed", "response.failed", "response.cancelled"}
        for event in openai_compat._records[response_id]["events"]
    )

    terminal = openai_compat.record_public_stream_chunk(
        response_id,
        {"content": "Готово", "done": True, "status": "completed"},
    )
    assert terminal[-1]["type"] == "response.completed"
    assert openai_compat._records[response_id]["status"] == "completed"


def test_cancel_wins_provider_terminal_race_and_is_idempotent(monkeypatch):
    response_id = openai_compat.begin_public_response(
        [{"role": "user", "content": "Долгая задача"}],
        owner_scope=_API_SCOPE,
    )

    async def racing_cancel(run_id):
        assert run_id == response_id
        # Reproduce the live race: the executor reports a terminal provider
        # failure while process cancellation is awaiting I/O.
        openai_compat.record_public_stream_chunk(
            response_id,
            {
                "done": True,
                "status": "failed",
                "error_code": "late_provider_failure",
            },
        )
        return True

    async def image_cancel(run_id):
        assert run_id == response_id
        return False

    monkeypatch.setattr(
        "app.codex_cli_provider.cancel_codex_cli_run",
        racing_cancel,
    )
    monkeypatch.setattr(
        "app.codex_cli_image_provider.cancel_codex_cli_image_run",
        image_cancel,
    )

    with TestClient(app) as client:
        first = client.post(f"/v1/responses/{response_id}/cancel", headers=_AUTH)
        second = client.post(f"/v1/responses/{response_id}/cancel", headers=_AUTH)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "cancelled"
    assert second.json()["status"] == "cancelled"
    record = openai_compat._records[response_id]
    assert record["status"] == "cancelled"
    assert record["error"] is None
    terminal_types = [event["type"] for event in record["events"]]
    assert terminal_types.count("response.cancelled") == 1
    assert "response.failed" not in terminal_types


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
        assert client.post("/api/v1/shell/bootstrap").status_code == 200
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


def test_responses_strict_json_is_validated_canonical_and_idempotent(monkeypatch):
    captured: list[dict] = []

    async def fake_completion(messages, **kwargs):
        captured.append(kwargs)
        assert kwargs["raw_json_output"] is True
        return {
            "content": '{"score":7,"answer":"точно"}',
            "status": "idle",
            "provider": "test-provider",
            "model": "test-model",
        }

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", fake_completion)
    body = {
        "model": "kolibri",
        "input": "Верни JSON",
        "text": _RESPONSE_TEXT_SCHEMA,
    }
    with TestClient(app) as client:
        created = client.post(
            "/v1/responses",
            json=body,
            headers={**_AUTH, "Idempotency-Key": "structured-1"},
        )
        replay = client.post(
            "/v1/responses",
            json=body,
            headers={**_AUTH, "Idempotency-Key": "structured-1"},
        )
        conflict = client.post(
            "/v1/responses",
            json={
                **body,
                "text": {
                    "format": {
                        **_RESPONSE_TEXT_SCHEMA["format"],
                        "name": "different",
                    }
                },
            },
            headers={**_AUTH, "Idempotency-Key": "structured-1"},
        )

    assert created.status_code == 200, created.text
    assert created.json()["output_text"] == '{"answer":"точно","score":7}'
    assert created.json()["output_parsed"] == {"answer": "точно", "score": 7}
    assert replay.json()["id"] == created.json()["id"]
    assert conflict.status_code == 409
    assert len(captured) == 1
    assert "additionalProperties" in captured[0]["system"]


def test_structured_json_rejects_unsupported_schema_and_invalid_provider_output(monkeypatch):
    async def invalid_completion(messages, **kwargs):
        return {
            "content": '{"answer":"missing score"}',
            "status": "idle",
            "provider": "test-provider",
        }

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", invalid_completion)
    unsupported = {
        "format": {
            "type": "json_schema",
            "name": "bad",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"value": {"type": "string", "pattern": "x"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        }
    }
    with TestClient(app) as client:
        bad_schema = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "x", "text": unsupported},
            headers=_AUTH,
        )
        bad_output = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "x", "text": _RESPONSE_TEXT_SCHEMA},
            headers=_AUTH,
        )

    assert bad_schema.status_code == 422
    assert bad_schema.json()["detail"]["code"] == "json_schema_keyword_unsupported"
    assert bad_output.status_code == 502
    assert bad_output.json()["detail"]["code"] == "structured_output_validation_failed"
    assert bad_output.json()["detail"]["reason_code"] == "structured_output_properties_mismatch"


def test_structured_primary_outcome_survives_evidence_write_failure(monkeypatch):
    from app import capability_runtime

    def fail_evidence(*args, **kwargs):
        raise OSError("probe ledger unavailable")

    async def valid_completion(messages, **kwargs):
        return {
            "content": '{"answer":"ok","score":8}',
            "status": "completed",
            "provider": "test-provider",
        }

    monkeypatch.setattr(capability_runtime, "record_capability_invocation", fail_evidence)
    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", valid_completion)
    with TestClient(app) as client:
        succeeded = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "x", "text": _RESPONSE_TEXT_SCHEMA},
            headers={**_AUTH, "Idempotency-Key": "structured-evidence-success"},
        )

    assert succeeded.status_code == 200, succeeded.text
    assert succeeded.json()["output_parsed"] == {"answer": "ok", "score": 8}

    async def invalid_completion(messages, **kwargs):
        return {
            "content": '{"answer":"missing score"}',
            "status": "completed",
            "provider": "test-provider",
        }

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", invalid_completion)
    with TestClient(app) as client:
        failed = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "x", "text": _RESPONSE_TEXT_SCHEMA},
            headers={**_AUTH, "Idempotency-Key": "structured-evidence-failure"},
        )

    assert failed.status_code == 502
    assert failed.json()["detail"]["code"] == "structured_output_validation_failed"


def test_responses_structured_stream_buffers_until_schema_validation(monkeypatch):
    async def fake_stream(messages, **kwargs):
        assert kwargs["raw_json_output"] is True
        assert "JSON" in kwargs["system"]
        yield {"content": '{"score":4,', "done": False}
        yield {"content": '"answer":"ok"}', "done": False}
        yield {
            "content": "",
            "done": True,
            "status": "idle",
            "provider": "test-provider",
            "model": "test-model",
        }

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion_stream", fake_stream)
    with TestClient(app) as client:
        streamed = client.post(
            "/v1/responses",
            json={
                "model": "kolibri",
                "input": "JSON",
                "stream": True,
                "text": _RESPONSE_TEXT_SCHEMA,
            },
            headers=_AUTH,
        )

    deltas = [
        json.loads(line[6:])["delta"]
        for line in streamed.text.splitlines()
        if line.startswith("data: ") and '"type": "response.output_text.delta"' in line
    ]
    assert streamed.status_code == 200
    assert deltas == ['{"answer":"ok","score":4}']
    assert "event: response.completed" in streamed.text


def test_chat_completions_strict_json_sync_and_stream(monkeypatch):
    async def fake_completion(messages, **kwargs):
        assert kwargs["raw_json_output"] is True
        return {
            "content": '{"score":8,"answer":"chat"}',
            "status": "idle",
            "provider": "test-provider",
        }

    async def fake_stream(messages, **kwargs):
        assert kwargs["raw_json_output"] is True
        yield {"content": '{"score":9,', "done": False}
        yield {"content": '"answer":"stream"}', "done": False}
        yield {"content": "", "done": True, "status": "idle", "provider": "test-provider"}

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", fake_completion)
    with TestClient(app) as client:
        sync = client.post(
            "/v1/chat/completions",
            json={
                "model": "kolibri",
                "messages": [{"role": "user", "content": "JSON"}],
                "response_format": _CHAT_RESPONSE_FORMAT,
            },
            headers=_AUTH,
        )
        monkeypatch.setattr(openai_compat.ai_provider, "chat_completion_stream", fake_stream)
        streamed = client.post(
            "/v1/chat/completions",
            json={
                "model": "kolibri",
                "messages": [{"role": "user", "content": "JSON"}],
                "response_format": _CHAT_RESPONSE_FORMAT,
                "stream": True,
            },
            headers=_AUTH,
        )

    message = sync.json()["choices"][0]["message"]
    assert sync.status_code == 200
    assert message["content"] == '{"answer":"chat","score":8}'
    assert message["parsed"] == {"answer": "chat", "score": 8}
    assert '{\\"answer\\":\\"stream\\",\\"score\\":9}' in streamed.text
    assert streamed.text.rstrip().endswith("data: [DONE]")


def test_response_retry_creates_fresh_id_and_is_idempotent(monkeypatch):
    calls = 0

    async def fake_completion(messages, **kwargs):
        nonlocal calls
        calls += 1
        return {
            "content": f"Ответ {calls}",
            "status": "idle",
            "provider": "test-provider",
        }

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", fake_completion)
    with TestClient(app) as client:
        original = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "Повтори"},
            headers=_AUTH,
        )
        response_id = original.json()["id"]
        first = client.post(
            f"/v1/responses/{response_id}/retry",
            headers={**_AUTH, "Idempotency-Key": "retry-one"},
        )
        replay = client.post(
            f"/v1/responses/{response_id}/retry",
            headers={**_AUTH, "Idempotency-Key": "retry-one"},
        )
        second = client.post(
            f"/v1/responses/{response_id}/retry",
            headers={**_AUTH, "Idempotency-Key": "retry-two"},
        )
        missing = client.post("/v1/responses/missing/retry", headers=_AUTH)

    assert first.status_code == 200, first.text
    assert first.json()["id"] != response_id
    assert first.json()["retry_of"] == response_id
    assert replay.json()["id"] == first.json()["id"]
    assert second.json()["id"] not in {response_id, first.json()["id"]}
    assert calls == 3
    assert missing.status_code == 404


def test_cancel_and_retry_are_not_masked_by_optional_evidence_failure(monkeypatch):
    from app import capability_runtime

    def fail_evidence_write(*args, **kwargs):
        raise OSError("evidence ledger unavailable")

    calls = 0

    async def fake_completion(messages, **kwargs):
        nonlocal calls
        calls += 1
        return {
            "content": "Повтор выполнен",
            "status": "idle",
            "provider": "test-provider",
        }

    monkeypatch.setattr(capability_runtime, "record_capability_invocation", fail_evidence_write)
    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", fake_completion)

    with TestClient(app) as client:
        cancellable_id = openai_compat.begin_public_response(
            [{"role": "user", "content": "Отмени"}],
            owner_scope=_API_SCOPE,
        )
        cancelled = client.post(f"/v1/responses/{cancellable_id}/cancel", headers=_AUTH)

        source_id = openai_compat.begin_public_response(
            [{"role": "user", "content": "Повтори"}],
            owner_scope=_API_SCOPE,
        )
        openai_compat.record_public_stream_chunk(
            source_id,
            {"content": "Первый ответ", "done": True, "status": "completed"},
        )
        retried = client.post(
            f"/v1/responses/{source_id}/retry",
            headers={**_AUTH, "Idempotency-Key": "retry-evidence-failure"},
        )
        replayed = client.post(
            f"/v1/responses/{source_id}/retry",
            headers={**_AUTH, "Idempotency-Key": "retry-evidence-failure"},
        )

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert openai_compat._records[cancellable_id]["status"] == "cancelled"
    assert retried.status_code == 200
    assert retried.json()["status"] == "completed"
    assert retried.json()["retry_of"] == source_id
    assert replayed.status_code == 200
    assert replayed.json()["id"] == retried.json()["id"]
    assert calls == 1


def test_response_retry_rejects_nonterminal_context(monkeypatch):
    with TestClient(app) as client:
        response_id = openai_compat.begin_public_response(
            [{"role": "user", "content": "ещё выполняется"}],
            owner_scope=_API_SCOPE,
        )
        response = client.post(f"/v1/responses/{response_id}/retry", headers=_AUTH)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "response_not_terminal"


def test_interrupted_response_is_failed_once_on_restart_and_can_be_retried(monkeypatch):
    async def fake_completion(messages, **kwargs):
        return {"content": "recovered", "status": "idle", "provider": "test-provider"}

    monkeypatch.setattr(openai_compat.ai_provider, "chat_completion", fake_completion)
    with TestClient(app):
        response_id = openai_compat.begin_public_response(
            [{"role": "user", "content": "crash me"}],
            owner_scope=_API_SCOPE,
        )

    openai_compat._records.clear()
    openai_compat._idempotency.clear()
    with TestClient(app) as restarted:
        fetched = restarted.get(f"/v1/responses/{response_id}", headers=_AUTH)
        events = restarted.get(f"/v1/responses/{response_id}/events", headers=_AUTH)
        retried = restarted.post(f"/v1/responses/{response_id}/retry", headers=_AUTH)

    assert fetched.status_code == 200
    assert fetched.json()["status"] == "failed"
    assert fetched.json()["error"] == {
        "code": "response_interrupted",
        "recoverable": True,
        "capability": None,
    }
    event_payloads = [
        json.loads(line.removeprefix("data: "))
        for line in events.text.splitlines()
        if line.startswith("data: ")
    ]
    interrupted = [
        item for item in event_payloads
        if item["type"] == "response.failed"
        and item.get("error", {}).get("code") == "response_interrupted"
    ]
    assert len(interrupted) == 1
    assert retried.status_code == 200
    assert retried.json()["retry_of"] == response_id

    openai_compat._records.clear()
    with TestClient(app) as restarted_again:
        events_again = restarted_again.get(
            f"/v1/responses/{response_id}/events",
            headers=_AUTH,
        )
    event_payloads_again = [
        json.loads(line.removeprefix("data: "))
        for line in events_again.text.splitlines()
        if line.startswith("data: ")
    ]
    assert len([
        item for item in event_payloads_again
        if item["type"] == "response.failed"
        and item.get("error", {}).get("code") == "response_interrupted"
    ]) == 1
