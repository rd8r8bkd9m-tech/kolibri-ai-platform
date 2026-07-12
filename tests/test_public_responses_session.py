from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import sqlite3
import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import execution_api
import image_artifacts
import public_image_api
import public_responses_api
from product_capabilities import build_product_capability_matrix, verified_provider_health


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
            "technical": {"provider_routing": {
                "selected_provider": "factory",
                "fallback_used": True,
                "attempts": [
                    {
                        "attempt": 1,
                        "provider": "factory",
                        "provider_model": "mimo",
                        "status": "failed",
                        "error_type": "provider_timeout",
                    },
                    {
                        "attempt": 2,
                        "provider": "factory",
                        "provider_model": "codex",
                        "status": "succeeded",
                        "evidence": _evidence(text),
                    },
                ],
                "evidence": _evidence(text),
            }},
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


def test_cold_session_discovery_is_a_non_cacheable_inactive_200(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)

    response = client.get("/v1/public/session")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "object": "public.session",
        "active": False,
        "model": "kolibri",
    }


def post_response(client: TestClient, text: str, *, key: str, **extra):
    return client.post(
        "/v1/responses",
        headers={"Origin": ORIGIN, "Idempotency-Key": key},
        json={"model": "kolibri", "input": text, **extra},
    )


def test_unavailable_image_route_never_returns_provider_prose_as_completion(tmp_path):
    app, executor = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)

    response = post_response(
        client,
        "Сгенерируй изображение колибри на прозрачном фоне",
        key="image-must-materialize",
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["output"] == []
    assert payload["error"]["code"] == "capability_unavailable"
    assert "image" not in payload["error"]
    assert executor.calls == []


def test_first_image_request_runs_fenced_canary_materializes_and_promotes(
    tmp_path, monkeypatch
):
    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )

    class ImageGateway:
        def __init__(self):
            self.verified = False
            self.calls = []

        def verified_product_health(self):
            return {
                "general": True,
                "code": True,
                "image_generation": self.verified,
            }

        @staticmethod
        def image_route_invocable():
            return True

        def generate_image(self, prompt, response_id, **_kwargs):
            self.calls.append((prompt, response_id))
            self.verified = True
            return type("Completion", (), {
                "status": "completed",
                "content": tiny_png,
                "media_type": "image/png",
                "content_sha256": hashlib.sha256(tiny_png).hexdigest(),
                "factory_binding_sha256": "f" * 64,
                "technical": {"task_id": "image-task", "attempt_id": "image-attempt-1"},
            })()

    gateway = ImageGateway()
    app, executor = make_app(tmp_path)
    image_artifacts.configure_public_image_artifact_store(
        tmp_path / "public.db", tmp_path / "image-artifacts",
    )
    app.include_router(public_image_api.router)
    monkeypatch.setattr(public_responses_api, "get_provider_gateway", lambda: gateway)
    client = TestClient(app)
    issue_session(client)

    response = post_response(
        client,
        "Сгенерируй изображение колибри на прозрачном фоне",
        key="first-image-canary",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["output_text"] == "Изображение создано и готово к просмотру."
    assert payload["task"]["intent"] == "image"
    assert payload["task"]["status"] == "completed"
    artifact = payload["task"]["artifacts"][0]
    assert artifact["kind"] == "image"
    assert artifact["media_type"] == "image/png"
    assert artifact["content_sha256"] == hashlib.sha256(tiny_png).hexdigest()
    assert artifact["size_bytes"] == len(tiny_png)
    assert artifact["status"] == "materialized"
    content = client.get(artifact["locator"])
    assert content.status_code == 200
    assert content.headers["content-type"] == "image/png"
    assert content.headers["x-content-sha256"] == artifact["content_sha256"]
    assert content.content == tiny_png
    assert len(gateway.calls) == 1
    assert executor.calls == []

    promoted = build_product_capability_matrix(
        routes=[("POST", "/v1/responses")],
        capability_envelope={"data": []},
        provider_health=verified_provider_health(gateway),
        built_in_tools={"tool:image_generation": True},
    )
    image = next(item for item in promoted["data"] if item["id"] == "image")
    assert image["available"] is True

    streamed = post_response(
        client,
        "Создай портрет птицы в акварельном стиле",
        key="image-artifact-ready-event",
        stream=True,
    )
    assert streamed.status_code == 200
    artifact_event = streamed.text.find("event: response.artifact.ready")
    completed_event = streamed.text.find("event: response.completed")
    assert 0 <= artifact_event < completed_event


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


def test_public_cookie_has_only_session_scoped_projects_and_no_privileged_authority(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)

    projects = client.get("/v1/projects")
    assert projects.status_code == 200
    assert len(projects.json()["data"]) == 1
    assert projects.json()["data"][0]["object"] == "project.ephemeral"
    assert projects.json()["data"][0]["durable"] is False
    assert client.get("/v1/artifacts").status_code == 401
    assert client.get("/v1/runtime/swarm").status_code == 401
    assert client.get(
        "/v1/projects", headers={"Authorization": "Bearer owner-key"},
    ).status_code == 200


def test_post_first_session_reuses_project_and_messages(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    first = issue_session(client)
    created = client.post(
        "/v1/projects",
        headers={"Origin": ORIGIN, "Idempotency-Key": "project-post-first"},
        json={"title": "Продолжаемый проект"},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]
    message = client.post(
        f"/v1/projects/{project_id}/messages",
        headers={"Origin": ORIGIN, "Idempotency-Key": "message-post-first"},
        json={"role": "user", "content": "Продолжай здесь"},
    )
    assert message.status_code == 201

    repeated = client.post("/v1/public/session", headers={"Origin": ORIGIN})

    assert repeated.status_code == 200
    assert repeated.json()["id"] == first["id"]
    assert repeated.json()["project"]["id"] == first["project"]["id"]
    assert "set-cookie" not in repeated.headers
    assert client.get(f"/v1/projects/{project_id}").status_code == 200
    messages = client.get(f"/v1/projects/{project_id}/messages").json()["data"]
    assert [item["content"] for item in messages] == ["Продолжай здесь"]


def test_public_project_message_crud_is_idempotent_soft_deleted_and_owned(tmp_path):
    app, _ = make_app(tmp_path)
    first = TestClient(app)
    second = TestClient(app)
    issue_session(first)
    issue_session(second)
    create_headers = {"Origin": ORIGIN, "Idempotency-Key": "project-crud"}
    created = first.post(
        "/v1/projects", headers=create_headers, json={"title": "Alpha"},
    )
    repeated = first.post(
        "/v1/projects", headers=create_headers, json={"title": "Alpha"},
    )
    conflict = first.post(
        "/v1/projects", headers=create_headers, json={"title": "Changed"},
    )
    project_id = created.json()["id"]
    assert created.status_code == 201
    assert repeated.status_code == 200
    assert repeated.json()["id"] == project_id
    assert conflict.status_code == 409
    assert second.get(f"/v1/projects/{project_id}").status_code == 404

    updated = first.post(
        f"/v1/projects/{project_id}",
        headers={"Origin": ORIGIN, "Idempotency-Key": "project-update"},
        json={"title": "Alpha 2", "metadata": {"view_mode": "dialog"}},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Alpha 2"

    message_headers = {"Origin": ORIGIN, "Idempotency-Key": "message-crud"}
    message = first.post(
        f"/v1/projects/{project_id}/messages",
        headers=message_headers,
        json={"role": "assistant", "content": "Черновик", "status": "running"},
    )
    duplicate = first.post(
        f"/v1/projects/{project_id}/messages",
        headers=message_headers,
        json={"role": "assistant", "content": "Черновик", "status": "running"},
    )
    message_id = message.json()["id"]
    assert message.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == message_id
    assert second.get(
        f"/v1/projects/{project_id}/messages/{message_id}",
    ).status_code == 404

    finished = first.post(
        f"/v1/projects/{project_id}/messages/{message_id}",
        headers={"Origin": ORIGIN, "Idempotency-Key": "message-finish"},
        json={"content": "Готово", "status": "completed"},
    )
    assert finished.json()["content"] == "Готово"
    deleted = first.post(
        f"/v1/projects/{project_id}/messages/{message_id}/delete",
        headers={"Origin": ORIGIN, "Idempotency-Key": "message-delete"},
    )
    assert deleted.json()["status"] == "deleted"
    assert first.get(
        f"/v1/projects/{project_id}/messages/{message_id}",
    ).status_code == 404
    assert first.get(
        f"/v1/projects/{project_id}/messages/{message_id}?include_deleted=true",
    ).json()["deleted_at"] is not None
    restored = first.post(
        f"/v1/projects/{project_id}/messages/{message_id}/restore",
        headers={"Origin": ORIGIN, "Idempotency-Key": "message-restore"},
    )
    assert restored.json()["status"] == "completed"

    removed_project = first.post(
        f"/v1/projects/{project_id}/delete",
        headers={"Origin": ORIGIN, "Idempotency-Key": "project-delete"},
    )
    assert removed_project.json()["status"] == "deleted"
    assert first.get(f"/v1/projects/{project_id}").status_code == 404
    assert first.get(
        f"/v1/projects/{project_id}?include_deleted=true",
    ).json()["deleted_at"] is not None
    restored_project = first.post(
        f"/v1/projects/{project_id}/restore",
        headers={"Origin": ORIGIN, "Idempotency-Key": "project-restore"},
    )
    assert restored_project.json()["status"] == "active"


def test_explicit_public_project_aliases_are_cookie_only_owned_and_idempotent(tmp_path):
    app, _ = make_app(tmp_path)
    first = TestClient(app)
    second = TestClient(app)
    issue_session(first)
    issue_session(second)

    # The durable compatibility route keeps accepting the owner token, while
    # the explicit public namespace refuses bearer authority even if the same
    # request also carries a valid public-session cookie.
    assert first.get(
        "/v1/projects",
        headers={"Authorization": "Bearer owner-key"},
    ).status_code == 200
    assert first.get(
        "/v1/public/projects",
        headers={"Authorization": "Bearer owner-key"},
    ).status_code == 403
    denied_write = first.post(
        "/v1/public/projects",
        headers={
            "Origin": ORIGIN,
            "Authorization": "Bearer owner-key",
            "Idempotency-Key": "owner-must-not-enter-public",
        },
        json={"title": "Forbidden owner write"},
    )
    assert denied_write.status_code == 403
    assert denied_write.json()["detail"] == "owner_authorization_not_allowed_on_public_route"

    headers = {"Origin": ORIGIN, "Idempotency-Key": "public-alias-project"}
    created = first.post(
        "/v1/public/projects", headers=headers, json={"title": "Public alias"},
    )
    repeated = first.post(
        "/v1/public/projects", headers=headers, json={"title": "Public alias"},
    )
    conflict = first.post(
        "/v1/public/projects", headers=headers, json={"title": "Different"},
    )
    assert created.status_code == 201
    assert repeated.status_code == 200
    assert repeated.json()["id"] == created.json()["id"]
    assert conflict.status_code == 409
    project_id = created.json()["id"]
    assert second.get(f"/v1/public/projects/{project_id}").status_code == 404

    updated = first.post(
        f"/v1/public/projects/{project_id}",
        headers={"Origin": ORIGIN, "Idempotency-Key": "public-alias-update"},
        json={"title": "Public alias updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Public alias updated"

    message_headers = {
        "Origin": ORIGIN,
        "Idempotency-Key": "public-alias-message",
    }
    message = first.post(
        f"/v1/public/projects/{project_id}/messages",
        headers=message_headers,
        json={"role": "user", "content": "Сохрани это сообщение"},
    )
    repeated_message = first.post(
        f"/v1/public/projects/{project_id}/messages",
        headers=message_headers,
        json={"role": "user", "content": "Сохрани это сообщение"},
    )
    conflicting_message = first.post(
        f"/v1/public/projects/{project_id}/messages",
        headers=message_headers,
        json={"role": "user", "content": "Другой текст"},
    )
    assert message.status_code == 201
    assert repeated_message.status_code == 200
    assert repeated_message.json()["id"] == message.json()["id"]
    assert conflicting_message.status_code == 409
    message_id = message.json()["id"]
    assert second.get(
        f"/v1/public/projects/{project_id}/messages/{message_id}",
    ).status_code == 404
    assert first.get(
        f"/v1/public/projects/{project_id}/messages",
    ).json()["data"][0]["id"] == message_id

    removed_message = first.post(
        f"/v1/public/projects/{project_id}/messages/{message_id}/delete",
        headers={"Origin": ORIGIN, "Idempotency-Key": "public-alias-message-delete"},
    )
    assert removed_message.json()["status"] == "deleted"
    restored_message = first.post(
        f"/v1/public/projects/{project_id}/messages/{message_id}/restore",
        headers={"Origin": ORIGIN, "Idempotency-Key": "public-alias-message-restore"},
    )
    assert restored_message.json()["status"] == "completed"

    removed_project = first.post(
        f"/v1/public/projects/{project_id}/delete",
        headers={"Origin": ORIGIN, "Idempotency-Key": "public-alias-project-delete"},
    )
    assert removed_project.json()["status"] == "deleted"
    assert first.get(f"/v1/public/projects/{project_id}").status_code == 404
    restored_project = first.post(
        f"/v1/public/projects/{project_id}/restore",
        headers={"Origin": ORIGIN, "Idempotency-Key": "public-alias-project-restore"},
    )
    assert restored_project.json()["status"] == "active"


def test_public_response_is_bound_to_owned_active_project(tmp_path):
    app, _ = make_app(tmp_path)
    first = TestClient(app)
    second = TestClient(app)
    issue_session(first)
    issue_session(second)
    projects = []
    for index in range(2):
        projects.append(first.post(
            "/v1/projects",
            headers={"Origin": ORIGIN, "Idempotency-Key": f"bound-project-{index}"},
            json={"title": f"Project {index}"},
        ).json())

    response = post_response(
        first,
        "project-bound",
        key="project-bound-response",
        project_id=projects[0]["id"],
    )
    assert response.status_code == 200
    assert response.json()["project_id"] == projects[0]["id"]
    filtered = first.get(
        f"/v1/responses?project_id={projects[0]['id']}",
    ).json()["data"]
    assert [item["id"] for item in filtered] == [response.json()["id"]]
    assert post_response(
        second,
        "foreign",
        key="foreign-project-response",
        project_id=projects[0]["id"],
    ).status_code == 404
    crossed = post_response(
        first,
        "wrong continuation",
        key="cross-project-response",
        project_id=projects[1]["id"],
        previous_response_id=response.json()["id"],
    )
    assert crossed.status_code == 409
    assert crossed.json()["detail"] == "previous_response_belongs_to_another_project"


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


def test_public_response_default_policy_records_content_free_formula_rejection(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)

    response = post_response(client, "safe but not opted in", key="public-no-consent")
    repeated = post_response(client, "safe but not opted in", key="public-no-consent")

    assert response.status_code == repeated.status_code == 200
    assert response.json()["id"] == repeated.json()["id"]
    tap = response.json()["learning_tap"]
    assert tap["status"] == "rejected"
    assert tap["rejection_code"] == "learning_consent_required"
    assert tap["candidate_only"] is True
    assert tap["async_queue"] is False
    assert tap["auto_promote"] is False
    assert tap["request_path_training"] is False
    assert tap["production_weight_mutation"] is False
    intakes = execution_api.get_learning_boundary().list_intakes(status="rejected")
    assert len(intakes) == 1
    assert intakes[0]["source_response_id"] == response.json()["id"]
    assert intakes[0]["content_persisted"] is False
    assert execution_api.get_learning_boundary().list_candidates() == []


def test_public_formula_tap_can_share_the_production_sqlite_store(tmp_path):
    database = tmp_path / "combined.db"
    executor = FakeExecutor()
    public_responses_api.configure_public_response_store(database)
    public_responses_api.configure_public_response_origins([ORIGIN])
    public_responses_api.configure_public_response_executor(executor)
    execution_api.configure_execution_store(database)
    execution_api.configure_execution_auth(["owner-key"])
    app = FastAPI()
    app.include_router(public_responses_api.router)
    app.include_router(execution_api.router)
    client = TestClient(app)
    issue_session(client)

    response = post_response(client, "same sqlite", key="public-shared-store")

    assert response.status_code == 200
    assert response.json()["learning_tap"]["status"] == "rejected"
    assert len(execution_api.get_learning_boundary().list_intakes()) == 1


def test_public_formula_tap_is_sanitized_bound_and_candidate_only(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    session = issue_session(client)
    cookie = client.cookies.get(public_responses_api.COOKIE_NAME)
    learning = {
        "consent": "explicit",
        "license": "permitted",
        "retention_class": "training-approved",
        "data_classification": "internal",
        "capability": "general.response",
    }

    response = post_response(
        client,
        "safe candidate trace",
        key="public-learning-opt-in",
        learning=learning,
    )

    assert response.status_code == 200
    payload = response.json()
    tap = payload["learning_tap"]
    assert tap["status"] == "queued"
    assert tap["rejection_code"] is None
    assert tap["async_queue"] is True
    assert tap["candidate_only"] is True
    assert tap["auto_promote"] is False
    assert tap["request_path_training"] is False
    assert tap["production_weight_mutation"] is False
    assert len(tap["attempt_evidence_sha256"]) == 64
    assert "provider" not in json.dumps(tap).lower()

    boundary = execution_api.get_learning_boundary()
    intakes = boundary.list_intakes(status="queued")
    assert len(intakes) == 1
    assert intakes[0]["source_response_id"] == payload["id"]
    assert intakes[0]["content_persisted"] is True
    assert boundary.list_candidates() == []

    with sqlite3.connect(tmp_path / "execution.db") as connection:
        row = connection.execute(
            "SELECT payload, provenance, artifact_hashes FROM formulalm_intakes"
        ).fetchone()
    trace_record = json.loads(row[0])
    provenance = json.loads(row[1])
    artifact_hashes = json.loads(row[2])
    trace = trace_record["trace"]
    assert trace_record["source_response_id"] == payload["id"]
    assert trace["binding"]["response_id"] == payload["id"]
    assert trace["binding"]["public_session_sha256"] == hashlib.sha256(
        session["id"].encode()
    ).hexdigest()
    assert trace["binding"]["project_sha256"] == hashlib.sha256(
        session["project"]["id"].encode()
    ).hexdigest()
    assert trace["binding"]["attempt_evidence_sha256"] == tap["attempt_evidence_sha256"]
    assert [item["status"] for item in trace["decisions"]["provider_attempts"]] == [
        "failed", "succeeded",
    ]
    assert provenance["actor"] == "public-provider-gateway"
    assert provenance["attempt_evidence_sha256"] == tap["attempt_evidence_sha256"]
    assert artifact_hashes and all(value.startswith("sha256:") for value in artifact_hashes)
    serialized_formula = json.dumps([trace_record, provenance, artifact_hashes])
    assert session["id"] not in serialized_formula
    assert session["project"]["id"] not in serialized_formula
    assert cookie not in serialized_formula


def test_public_formula_tap_rejects_secret_without_persisting_trace(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)
    secret = "sk-" + "never-store-public-learning-123456789"

    response = post_response(
        client,
        f"do not learn {secret}",
        key="public-learning-secret",
        learning={
            "consent": "explicit",
            "license": "permitted",
            "retention_class": "training-approved",
            "data_classification": "private",
            "capability": "general.response",
        },
    )

    assert response.status_code == 200
    assert response.json()["learning_tap"]["status"] == "rejected"
    assert response.json()["learning_tap"]["rejection_code"] == "learning_secret_detected"
    with sqlite3.connect(tmp_path / "execution.db") as connection:
        payload, persisted = connection.execute(
            "SELECT payload, payload IS NOT NULL FROM formulalm_intakes"
        ).fetchone()
    assert payload is None
    assert persisted == 0
    assert secret.encode() not in (tmp_path / "execution.db").read_bytes()


def test_formula_boundary_failure_never_turns_verified_public_answer_into_failure(
    tmp_path, monkeypatch,
):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)

    class BrokenBoundary:
        def enqueue_trace(self, **_kwargs):
            raise RuntimeError("learning storage unavailable")

    monkeypatch.setattr(public_responses_api, "get_learning_boundary", lambda: BrokenBoundary())
    response = post_response(client, "still answer", key="public-learning-isolated")

    assert response.status_code == 200
    assert response.json()["output_text"] == "verified:fast"
    assert response.json()["learning_tap"] == {
        **{
            key: response.json()["learning_tap"][key]
            for key in ("content_sha256", "attempt_evidence_sha256")
        },
        "candidate_only": True,
        "async_queue": False,
        "auto_promote": False,
        "request_path_training": False,
        "production_weight_mutation": False,
        "status": "unavailable",
        "rejection_code": "learning_boundary_unavailable",
    }


def test_responses_sse_uses_official_typed_event_names(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)
    response = post_response(client, "stream", key="stream-one", stream=True)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "id: 0\nevent: response.created" in response.text
    assert "event: response.created" in response.text
    assert "event: response.in_progress" in response.text
    assert "event: response.output_text.delta" in response.text
    assert '"delta":"verified:fast"' in response.text
    assert "event: response.reasoning_summary_text.delta" not in response.text
    assert '"stage":"routing"' in response.text
    assert "event: response.kolibri_work_summary.updated" in response.text
    assert "event: response.completed" in response.text
    assert "data: [DONE]" not in response.text
    updates = []
    for block in response.text.split("\n\n"):
        if "event: response.kolibri_work_summary.updated" not in block:
            continue
        data_line = next(line for line in block.splitlines() if line.startswith("data: "))
        updates.append(json.loads(data_line.removeprefix("data: ")))
    assert [item["active_kind"] for item in updates] == ["verdict"]
    assert all(item["summary"]["mode"] == "summary_only" for item in updates)
    assert all(item["summary"]["raw_reasoning_exposed"] is False for item in updates)


def test_responses_sse_replays_only_events_after_last_event_id(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)
    body = {"model": "kolibri", "input": "resume", "stream": True}
    headers = {"Origin": ORIGIN, "Idempotency-Key": "stream-resume"}
    first = client.post("/v1/responses", headers=headers, json=body)
    response_id = next(
        json.loads(line.removeprefix("data: "))["response"]["id"]
        for block in first.text.split("\n\n")
        if "event: response.completed" in block
        for line in block.splitlines()
        if line.startswith("data: ")
    )
    replay = client.post(
        "/v1/responses",
        headers={**headers, "Last-Event-ID": "5"},
        json=body,
    )
    replay_ids = [
        int(line.removeprefix("id: "))
        for line in replay.text.splitlines()
        if line.startswith("id: ")
    ]
    assert replay_ids
    assert min(replay_ids) > 5
    assert "event: response.completed" in replay.text

    get_replay = client.get(
        f"/v1/responses/{response_id}?stream=true&starting_after=5",
    )
    get_replay_ids = [
        int(line.removeprefix("id: "))
        for line in get_replay.text.splitlines()
        if line.startswith("id: ")
    ]
    assert get_replay.status_code == 200
    assert get_replay.headers["content-type"].startswith("text/event-stream")
    assert get_replay_ids == replay_ids
    assert all(sequence > 5 for sequence in get_replay_ids)

    events = client.get(
        f"/v1/responses/{response_id}/events",
        headers={"Accept": "text/event-stream", "Last-Event-ID": "5"},
    )
    event_ids = [
        int(line.removeprefix("id: "))
        for line in events.text.splitlines()
        if line.startswith("id: ")
    ]
    assert event_ids == replay_ids


def test_provider_exhaustion_returns_truthful_safe_public_error(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)

    async def exhausted(**_kwargs):
        raise public_responses_api.ProviderGatewayError({
            "attempts": [
                {"status": "failed", "error_type": "provider_timeout"},
                {"status": "skipped", "error_type": "deadline_exhausted"},
            ],
            "error_type": "provider_timeout",
        })

    public_responses_api.configure_public_response_executor(exhausted)
    response = post_response(client, "try every route", key="provider-exhausted")

    assert response.status_code == 503
    error = response.json()["error"]
    assert error == {
        "type": "provider_unavailable",
        "code": "provider_timeout",
        "message": "The configured model routes reached their execution deadline before one completed.",
        "retryable": True,
        "attempt_summary": {
            "attempted": 2,
            "failed": 1,
            "timed_out": 2,
            "cancelled": 0,
            "skipped": 1,
        },
    }
    assert "could not produce a verified response" not in response.text.lower()


def test_unexpected_execution_failure_is_not_reported_as_provider_exhaustion(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)

    async def broken(**_kwargs):
        raise RuntimeError("private implementation detail")

    public_responses_api.configure_public_response_executor(broken)
    response = post_response(client, "internal", key="internal-failure")

    assert response.status_code == 503
    assert response.json()["error"] == {
        "type": "response_internal_error",
        "code": "response_internal_error",
        "message": "The server encountered an internal execution error before the response completed.",
        "retryable": True,
    }
    assert "private implementation detail" not in response.text
    assert "attempt_summary" not in response.text


def test_response_does_not_manufacture_reasoning_without_provider_summary(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)

    response = post_response(client, "private prompt", key="safe-work-summary")

    assert response.status_code == 200
    payload = response.json()
    compact = json.loads(payload["metadata"]["kolibri_work_summary"])
    assert compact["mode"] == "summary_only"
    assert [item["kind"] for item in compact["items"]] == [
        "plan", "tool", "source", "check", "verdict",
    ]
    assert not any(item["type"] == "reasoning" for item in payload["output"])
    serialized = json.dumps({"metadata": payload["metadata"]})
    assert "private prompt" not in serialized
    assert "selected_provider" not in serialized
    assert "provider_model" not in serialized
    assert "raw_reasoning" not in serialized


def test_requested_reasoning_stream_contains_only_real_provider_summary(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)

    async def reasoning_executor(**kwargs):
        callback = kwargs["stream_callback"]
        callback({"type": "reasoning_summary_delta", "delta": "Проверяю условие. "})
        callback({"type": "reasoning_summary_delta", "delta": "Сверяю результат."})
        text = "Проверенный ответ"
        return {
            "response": text,
            "model": "kolibri",
            "technical": {"provider_routing": {
                "selected_provider": "factory",
                "attempts": [],
                "evidence": _evidence(text),
            }},
        }

    public_responses_api.configure_public_response_executor(reasoning_executor)
    response = post_response(
        client,
        "reasoning",
        key="reasoning-provider-summary",
        stream=True,
        background=True,
        reasoning={"effort": "medium", "summary": "auto"},
    )

    assert response.status_code == 200
    assert "event: response.reasoning_summary_part.added" in response.text
    assert '"delta":"Проверяю условие. "' in response.text
    assert '"delta":"Сверяю результат."' in response.text
    completed = next(
        json.loads(line.removeprefix("data: "))["response"]
        for block in response.text.split("\n\n")
        if "event: response.completed" in block
        for line in block.splitlines()
        if line.startswith("data: ")
    )
    reasoning = next(item for item in completed["output"] if item["type"] == "reasoning")
    assert reasoning["summary"] == [{
        "type": "summary_text",
        "text": "Проверяю условие. Сверяю результат.",
    }]


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
    assert all("timeout_seconds" not in call for call in executor.calls)


def test_background_nonstream_returns_in_progress_then_completes_without_implicit_timeout(
    tmp_path,
):
    app, _ = make_app(tmp_path)
    provider_started = threading.Event()
    release_provider = threading.Event()
    calls: list[dict] = []

    async def delayed_executor(**kwargs):
        calls.append(kwargs)
        provider_started.set()
        released = await asyncio.to_thread(release_provider.wait, 2.0)
        assert released is True
        text = "background response completed"
        return {
            "response": text,
            "model": "kolibri",
            "technical": {"provider_routing": {"evidence": _evidence(text)}},
        }

    public_responses_api.configure_public_response_executor(delayed_executor)
    with TestClient(app) as client:
        issue_session(client)
        accepted = post_response(
            client,
            "continue in background",
            key="background-nonstream",
            background=True,
        )

        assert accepted.status_code == 200
        initial = accepted.json()
        assert initial["status"] == "in_progress"
        assert initial["background"] is True
        assert initial["output"] == []
        assert provider_started.wait(1.0) is True
        assert calls and "timeout_seconds" not in calls[0]

        release_provider.set()
        deadline = time.monotonic() + 2.0
        current = initial
        while time.monotonic() < deadline:
            fetched = client.get(f"/v1/responses/{initial['id']}")
            assert fetched.status_code == 200
            current = fetched.json()
            if current["status"] == "completed":
                break
            time.sleep(0.01)

        assert current["status"] == "completed"
        assert current["output_text"] == "background response completed"


def test_public_chat_timeout_is_bounded_and_configurable(tmp_path, monkeypatch):
    app, executor = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)

    monkeypatch.setenv("KOLIBRI_PUBLIC_RESPONSE_TIMEOUT_SECONDS", "9")
    response = post_response(client, "short answer", key="bounded-chat-timeout")

    assert response.status_code == 200
    assert executor.calls[-1]["timeout_seconds"] == 9.0


def test_public_chat_timeout_is_additive_for_compatibility_executors(tmp_path):
    app, _ = make_app(tmp_path)
    client = TestClient(app)
    issue_session(client)

    async def compatibility_executor(messages, model, execution_mode, response_id):
        del messages, execution_mode, response_id
        text = "compatibility route completed"
        return {
            "response": text,
            "model": model,
            "technical": {"provider_routing": {"evidence": _evidence(text)}},
        }

    public_responses_api.configure_public_response_executor(compatibility_executor)
    response = post_response(client, "short answer", key="compatibility-chat-timeout")

    assert response.status_code == 200
    assert response.json()["output_text"] == "compatibility route completed"


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
            "region": "Москва",
            "normative_basis": {
                "calculation_method": "resource",
                "normative_basis_ref": "TEST-NORMATIVE-BASE-2026",
                "normative_edition": "Тестовая редакция 2026-01-01",
                "price_level_date": "2026-01-01",
                "region": "Москва",
                "index_document_refs": [],
                "tax_scope_ref": "TEST-TAX-SCOPE-2026",
                "contract_scope_ref": "TEST-CONTRACT-SCOPE-2026",
            },
            "lines": [{
                "id": "labor-1",
                "description": "Монтаж",
                "category": "labor",
                "unit": "м2",
                "quantity": "2",
                "unit_price_minor": 15_000,
                "provenance": {
                    "source": "normative",
                    "source_ref": "TEST-PRICE-SOURCE-LABOR",
                    "captured_at": "2026-01-01",
                    "applicable_region": "Москва",
                    "price_level_date": "2026-01-01",
                    "basis_ref": "TEST-BASIS-LABOR",
                    "quantity_source": "project",
                    "quantity_source_ref": "TEST-PROJECT-SHEET-LABOR",
                },
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
