from __future__ import annotations

import hashlib
import sqlite3
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import execution_api
import public_responses_api


ORIGIN = "http://testserver"


def _evidence(text: str) -> list[dict]:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return [
        {
            "type": "provider_execution",
            "provider": "factory",
            "provider_model": "test-runner",
            "exit_code": 0,
            "output_sha256": digest,
            "output_bytes": len(text.encode("utf-8")),
        },
        {
            "type": "deterministic_verifier",
            "verdict": "passed",
            "binding_sha256": "a" * 64,
        },
    ]


class FakeExecutor:
    def __init__(self):
        self.calls = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        serialized = str(kwargs.get("messages") or [])
        text = "123" if "56+67" in serialized else f"verified:{kwargs['execution_mode']}"
        return {
            "response": text,
            "model": "kolibri",
            "technical": {"provider_routing": {"evidence": _evidence(text)}},
        }


def make_app(tmp_path):
    executor = FakeExecutor()
    public_responses_api.configure_public_response_store(tmp_path / "public.db")
    public_responses_api.configure_public_response_origins([ORIGIN])
    public_responses_api.configure_public_response_executor(executor)
    execution_api.configure_execution_store(tmp_path / "execution.db")
    execution_api.configure_execution_auth(["owner-key"])
    app = FastAPI()
    # The scoped router deliberately wins only for the overlapping Responses
    # routes. The durable execution router still owns Projects/Artifacts/etc.
    app.include_router(public_responses_api.router)
    app.include_router(execution_api.router)
    return app, executor


def issue_session(client: TestClient) -> dict:
    response = client.post("/v1/public/session", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    return response.json()


def post_response(client: TestClient, text: str, *, key: str, **extra):
    return client.post(
        "/v1/responses",
        headers={"Origin": ORIGIN, "Idempotency-Key": key},
        json={"model": "kolibri", "input": text, **extra},
    )


def test_session_cookie_is_http_only_same_site_scoped_and_only_hash_is_stored(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    response = client.post("/v1/public/session", headers={"Origin": ORIGIN})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    cookie_header = response.headers["set-cookie"]
    assert "HttpOnly" in cookie_header
    assert "SameSite=strict" in cookie_header
    assert "Path=/v1" in cookie_header
    assert "Secure" not in cookie_header  # local HTTP only; HTTPS sessions set it.
    token = client.cookies.get(public_responses_api.COOKIE_NAME)
    assert token and token not in response.text

    raw_database = (tmp_path / "public.db").read_bytes()
    assert token.encode() not in raw_database
    with sqlite3.connect(tmp_path / "public.db") as connection:
        token_hash = connection.execute(
            "SELECT token_sha256 FROM public_response_sessions"
        ).fetchone()[0]
    assert token_hash == hashlib.sha256(token.encode()).hexdigest()


def test_origin_and_csrf_checks_fail_closed(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)

    assert client.post("/v1/public/session").status_code == 403
    assert client.post(
        "/v1/public/session", headers={"Origin": "https://attacker.example"},
    ).status_code == 403
    issue_session(client)
    assert client.post(
        "/v1/responses",
        headers={"Idempotency-Key": "csrf-missing"},
        json={"model": "kolibri", "input": "hello"},
    ).status_code == 403
    assert client.post(
        "/v1/responses",
        headers={"Origin": "https://attacker.example", "Idempotency-Key": "csrf-wrong"},
        json={"model": "kolibri", "input": "hello"},
    ).status_code == 403


def test_sessions_are_isolated_and_cannot_read_another_response(tmp_path):
    app, executor = make_app(tmp_path)
    first = TestClient(app)
    second = TestClient(app)
    issue_session(first)
    issue_session(second)

    created = post_response(first, "private-a", key="isolated-a")
    assert created.status_code == 200
    response_id = created.json()["id"]
    assert executor.calls[0]["response_id"] == response_id
    assert first.get(f"/v1/responses/{response_id}").status_code == 200
    assert second.get(f"/v1/responses/{response_id}").status_code == 404
    assert second.get("/v1/responses").json()["data"] == []
    assert post_response(
        second,
        "continue чужой ответ",
        key="cross-session-previous",
        previous_response_id=response_id,
    ).status_code == 404


def test_expired_session_is_rejected(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    session = issue_session(client)
    current = client.get("/v1/public/session")
    assert current.status_code == 200
    assert current.headers["cache-control"] == "no-store"
    public_responses_api._STORE.expire_session_for_test(session["id"])

    expired_discovery = client.get("/v1/public/session")
    assert expired_discovery.status_code == 401
    assert expired_discovery.headers["cache-control"] == "no-store"
    expired_response = post_response(client, "hello", key="expired-request")
    assert expired_response.status_code == 401
    assert expired_response.headers["cache-control"] == "no-store"


def test_public_cookie_has_no_projects_artifacts_or_admin_authority(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)

    assert client.get("/v1/projects").status_code == 401
    assert client.get("/v1/artifacts").status_code == 401
    assert client.get("/v1/runtime/swarm").status_code == 401
    assert client.get(
        "/v1/projects", headers={"Authorization": "Bearer owner-key"},
    ).status_code == 200


def test_public_response_idempotency_is_session_scoped_and_conflict_safe(tmp_path):
    app, executor = make_app(tmp_path)
    first = TestClient(app)
    second = TestClient(app)
    issue_session(first)
    issue_session(second)

    first_a = post_response(first, "same", key="stable-key")
    first_b = post_response(first, "same", key="stable-key")
    conflict = post_response(first, "changed", key="stable-key")
    second_a = post_response(second, "same", key="stable-key")

    assert first_a.status_code == first_b.status_code == second_a.status_code == 200
    assert first_a.json()["id"] == first_b.json()["id"]
    assert second_a.json()["id"] != first_a.json()["id"]
    assert conflict.status_code == 409
    assert len(executor.calls) == 2


def test_public_session_rate_limit_is_enforced(tmp_path, monkeypatch):
    monkeypatch.setenv("KOLIBRI_PUBLIC_SESSION_REQUESTS_PER_MINUTE", "1")
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)

    assert post_response(client, "first", key="rate-first").status_code == 200
    limited = post_response(client, "second", key="rate-second")
    assert limited.status_code == 429
    assert limited.json()["detail"] == "public_session_rate_limit_exceeded"


def test_openai_response_shape_and_standard_input_are_supported(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    session = issue_session(client)
    response = client.post(
        "/v1/responses",
        headers={"Origin": ORIGIN, "Idempotency-Key": "sdk-shape"},
        json={
            "model": "kolibri",
            "input": [{"role": "user", "content": "Hello from an OpenAI SDK payload"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"].startswith("resp_")
    assert payload["object"] == "response"
    assert isinstance(payload["created_at"], int)
    assert payload["status"] == "completed"
    assert payload["model"] == "kolibri"
    assert payload["project_id"] == session["project"]["id"]
    message = payload["output"][0]
    assert message["type"] == "message"
    assert message["role"] == "assistant"
    assert message["status"] == "completed"
    assert message["content"][0] == {
        "type": "output_text",
        "text": "verified:fast",
        "annotations": [],
    }
    assert payload["output_text"] == "verified:fast"
    assert "provider" not in response.text.lower()


def test_responses_sse_uses_official_typed_event_names(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)
    response = post_response(client, "stream", key="stream-one", stream=True)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: response.created" in response.text
    assert "event: response.in_progress" in response.text
    assert "event: response.output_text.delta" in response.text
    assert '"delta":"verified:fast"' in response.text
    assert "event: response.completed" in response.text
    assert "data: [DONE]" not in response.text


def test_live_regression_chat_and_arithmetic_are_posted_to_responses_not_blank(tmp_path):
    app, executor = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)

    chat = post_response(client, "как дела в москве?", key="regression-kak-dela")
    arithmetic = post_response(
        client,
        "56+67",
        key="regression-56-plus-67",
        stream=True,
        execution_mode="codex",
    )

    assert chat.status_code == 200
    assert chat.json()["output_text"].strip()
    assert arithmetic.status_code == 200
    assert 'event: response.output_text.delta' in arithmetic.text
    assert '"delta":"123"' in arithmetic.text
    assert 'event: response.completed' in arithmetic.text
    assert all(call["model"] == "kolibri" for call in executor.calls)
    assert [call["execution_mode"] for call in executor.calls] == ["fast", "codex"]


def test_codex_mode_and_typed_estimate_preserve_deterministic_money(tmp_path):
    app, executor = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)
    estimate = {
        "intent": "estimate",
        "spec": {
            "title": "Кухня",
            "currency": "RUB",
            "minor_unit": 2,
            "lines": [{
                "id": "labor-1",
                "description": "Монтаж",
                "category": "labor",
                "unit": "м2",
                "quantity": "2",
                "unit_price_minor": 15_000,
                "provenance": {"source": "manual"},
            }],
            "overhead_rate_bps": 1_000,
            "tax_rate_bps": 2_000,
        },
        "requested_artifacts": [],
    }
    response = post_response(
        client,
        "Рассчитай смету",
        key="typed-estimate",
        execution_mode="codex",
        task=estimate,
    )

    assert response.status_code == 200
    payload = response.json()
    assert executor.calls[-1]["execution_mode"] == "codex"
    calculation = payload["task"]["result"]["calculation"]
    assert calculation["money_authority"] == "deterministic_calculator"
    assert calculation["llm_calculates_money"] is False
    assert calculation["totals"]["grand_total_minor"] == 39_600


def test_invalid_bearer_does_not_fall_back_to_a_valid_browser_cookie(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)
    response = client.post(
        "/v1/responses",
        headers={
            "Authorization": "Bearer wrong-owner-key",
            "Origin": ORIGIN,
            "Idempotency-Key": "must-not-fallback",
        },
        json={"model": "kolibri", "input": "hello"},
    )
    assert response.status_code == 401
