from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import execution_api  # noqa: E402
import openai_compatibility  # noqa: E402
import public_responses_api  # noqa: E402


ORIGIN = "http://testserver"
AUTH = {"Authorization": "Bearer owner-key"}


def _app(tmp_path: Path) -> FastAPI:
    execution_api.configure_execution_store(tmp_path / "execution.db")
    execution_api.configure_execution_auth(["owner-key"])
    public_responses_api.configure_public_response_store(tmp_path / "public.db")
    public_responses_api.configure_public_response_origins([ORIGIN])
    app = FastAPI()
    app.include_router(openai_compatibility.router)
    app.include_router(public_responses_api.router)
    app.include_router(execution_api.router)
    return app


def _put_owner_response(response_id: str, input_value):
    return execution_api.get_store().put(
        "response",
        response_id,
        "completed",
        {
            "model": "kolibri",
            "input": input_value,
            "output": [],
            "error": None,
        },
    )


def test_discovery_is_an_explicit_allowlist_and_labels_extensions(tmp_path):
    client = TestClient(_app(tmp_path))

    response = client.get("/v1/kolibri/openai-compatibility")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["routing_policy"] == {
        "mode": "explicit_allowlist",
        "wildcard_v1_proxy": False,
        "organization_proxy": False,
        "admin_proxy": False,
        "proxied_paths": [],
        "explicitly_not_proxied": ["/v1/organization/*", "/v1/admin/*"],
        "unlisted_openai_operations": "unavailable_404",
    }
    by_operation = {item["operation"]: item for item in payload["operations"]}
    assert by_operation["responses.input_items.list"]["available"] is True
    assert by_operation["kolibri.responses.list"]["conformance"] == "kolibri_extension"
    assert by_operation["kolibri.realtime.probe"]["conformance"] == "kolibri_boundary"
    assert by_operation["realtime.connect"]["available"] is False
    response_features = by_operation["responses.create"]["features"]
    assert "reasoning_summary_opt_in" in response_features
    assert "public_session_background_execution" in response_features
    assert "public_session_resumable_sse_sequence_number" in response_features
    assert "raw_reasoning" not in " ".join(response_features)
    assert payload["reference"]["reasoning_summaries"].endswith("#reasoning-summaries")
    assert payload["reference"]["background_streaming"].endswith(
        "#streaming-a-background-response"
    )
    assert client.get("/v1/organization/admin_api_keys").status_code == 404
    assert client.get("/v1/admin/users").status_code == 404


def test_realtime_http_and_websocket_boundaries_never_claim_a_session(tmp_path):
    client = TestClient(_app(tmp_path))

    probe = client.get("/v1/realtime")
    assert probe.status_code == 501
    assert probe.json()["error"]["code"] == "realtime_unavailable"
    assert probe.json()["available"] is False
    assert probe.json()["surface"] == "/v1/realtime"
    assert probe.json()["supported_alternative"]["path"] == "/v1/responses"

    with client.websocket_connect("/v1/realtime") as websocket:
        event = websocket.receive_json()
        assert event["type"] == "error"
        assert event["error"]["code"] == "realtime_unavailable"
        assert "session" not in event
        with pytest.raises(WebSocketDisconnect) as closed:
            websocket.receive_json()
        assert closed.value.code == 1013

    for path in (
        "/v1/realtime",
        "/v1/realtime/client_secrets",
        "/v1/realtime/sessions",
        "/v1/realtime/transcription_sessions",
        "/v1/realtime/calls",
        "/v1/realtime/translations/client_secrets",
    ):
        response = client.post(path, content=b"not parsed by unavailable boundary")
        assert response.status_code == 501, (path, response.text)
        assert response.headers["content-type"].startswith("application/json")
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["error"]["code"] == "realtime_unavailable"
        assert response.json()["surface"] == path
        assert response.json()["transport"] == "http"
        assert response.json()["available"] is False
        assert "session" not in response.json()


def test_public_background_response_resumes_from_starting_after_cursor(tmp_path):
    client = TestClient(_app(tmp_path))
    issued = client.post("/v1/public/session", headers={"Origin": ORIGIN})
    assert issued.status_code == 200
    token = client.cookies.get(public_responses_api.COOKIE_NAME)
    session = public_responses_api._STORE.resolve(token)
    assert session is not None

    body = execution_api.ResponseCreate.model_validate({
        "model": "kolibri",
        "input": "continue in background",
        "stream": True,
        "background": True,
        "reasoning": {"effort": "medium", "summary": "auto"},
    })
    response_id = "resp_background_resume"
    initial = public_responses_api._response_shell(
        response_id,
        body,
        session["project_id"],
        status="in_progress",
    )
    context = [{"role": "user", "content": "continue in background"}]
    public_responses_api._STORE.begin_response(
        session,
        response_id=response_id,
        idempotency_key="background-resume",
        request_sha256=hashlib.sha256(b"background-resume").hexdigest(),
        payload=initial,
        context=context,
    )
    public_responses_api._STORE.append_response_event(
        session["id"], response_id, "response.created",
        {"type": "response.created", "response": initial},
    )
    public_responses_api._STORE.append_response_event(
        session["id"], response_id, "response.reasoning_summary_text.delta",
        {
            "type": "response.reasoning_summary_text.delta",
            "item_id": "rs_background_resume",
            "output_index": 0,
            "summary_index": 0,
            "delta": "Проверяю данные.",
        },
    )
    public_responses_api._STORE.append_response_event(
        session["id"], response_id, "response.output_text.delta",
        {
            "type": "response.output_text.delta",
            "item_id": "msg_background_resume",
            "output_index": 1,
            "content_index": 0,
            "delta": "Готово",
        },
    )
    completed = {
        **initial,
        "status": "completed",
        "completed_at": initial["created_at"] + 1,
        "output": [],
    }
    public_responses_api._STORE.finish_response(
        session["id"], response_id, completed, context, http_status=200,
    )
    public_responses_api._STORE.append_response_event(
        session["id"], response_id, "response.completed",
        {"type": "response.completed", "response": completed},
    )

    resumed = client.get(
        f"/v1/responses/{response_id}",
        params={"stream": "true", "starting_after": 1},
    )

    assert resumed.status_code == 200
    assert resumed.headers["content-type"].startswith("text/event-stream")
    assert "id: 0\n" not in resumed.text
    assert "id: 1\n" not in resumed.text
    assert "id: 2\nevent: response.output_text.delta" in resumed.text
    assert "id: 3\nevent: response.completed" in resumed.text
    assert "Проверяю данные" not in resumed.text


def test_owner_response_input_items_are_stable_and_paginated(tmp_path):
    client = TestClient(_app(tmp_path))
    response_id = "resp_owner_input_items"
    _put_owner_response(response_id, [
        {"role": "developer", "content": "Use only recorded facts."},
        {"role": "user", "content": [
            {"type": "input_text", "text": "first"},
            {"type": "input_image", "image_url": "https://example.invalid/image.png"},
        ]},
        {"role": "user", "content": "last"},
    ])

    first = client.get(
        f"/v1/responses/{response_id}/input_items",
        headers=AUTH,
        params={"order": "asc", "limit": 2},
    )

    assert first.status_code == 200
    page = first.json()
    assert page["object"] == "list"
    assert page["has_more"] is True
    assert [item["role"] for item in page["data"]] == ["developer", "user"]
    assert page["data"][0]["content"] == [
        {"type": "input_text", "text": "Use only recorded facts."}
    ]
    assert page["data"][1]["content"][1]["type"] == "input_image"
    assert page["first_id"] == page["data"][0]["id"]
    assert page["last_id"] == page["data"][-1]["id"]

    second = client.get(
        f"/v1/responses/{response_id}/input_items",
        headers=AUTH,
        params={"order": "asc", "limit": 2, "after": page["last_id"]},
    )
    assert second.status_code == 200
    assert second.json()["has_more"] is False
    assert second.json()["data"][0]["content"][0]["text"] == "last"

    repeated = client.get(
        f"/v1/responses/{response_id}/input_items",
        headers=AUTH,
        params={"order": "asc", "limit": 2},
    ).json()
    assert [item["id"] for item in repeated["data"]] == [
        item["id"] for item in page["data"]
    ]

    descending = client.get(
        f"/v1/responses/{response_id}/input_items",
        headers=AUTH,
    ).json()
    assert descending["data"][0]["content"][0]["text"] == "last"


def test_public_input_items_use_current_request_only_and_are_session_scoped(tmp_path):
    client = TestClient(_app(tmp_path))
    issued = client.post("/v1/public/session", headers={"Origin": ORIGIN})
    assert issued.status_code == 200
    token = client.cookies.get(public_responses_api.COOKIE_NAME)
    assert token
    session = public_responses_api._STORE.resolve(token)
    assert session is not None

    response_id = "resp_public_input_items"
    current_input = [{"role": "user", "content": "private prompt"}]
    public_responses_api._STORE.begin_response(
        session,
        response_id=response_id,
        idempotency_key="public-input-items",
        request_sha256=hashlib.sha256(b"public-input-items").hexdigest(),
        payload={
            "id": response_id,
            "object": "response",
            "status": "in_progress",
            "model": "kolibri",
            "output": [],
        },
        context=current_input,
    )
    # Provider context may later include previous turns and instructions.  The
    # input-items endpoint must retain the exact request input recorded above.
    public_responses_api._STORE.finish_response(
        session["id"],
        response_id,
        {
            "id": response_id,
            "object": "response",
            "status": "completed",
            "model": "kolibri",
            "output": [],
        },
        [
            {"role": "system", "content": "provider-only instruction"},
            {"role": "user", "content": "old context"},
            *current_input,
        ],
        http_status=200,
    )

    response = client.get(f"/v1/responses/{response_id}/input_items")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["data"][0]["content"][0]["text"] == "private prompt"
    assert "provider-only instruction" not in response.text
    assert "old context" not in response.text

    other = TestClient(client.app)
    assert other.post("/v1/public/session", headers={"Origin": ORIGIN}).status_code == 200
    assert other.get(f"/v1/responses/{response_id}/input_items").status_code == 404


def test_input_items_validate_bounds_and_cursor(tmp_path):
    client = TestClient(_app(tmp_path))
    response_id = "resp_input_validation"
    _put_owner_response(response_id, "hello")

    assert client.get(
        f"/v1/responses/{response_id}/input_items",
        headers=AUTH,
        params={"limit": 0},
    ).status_code == 422
    assert client.get(
        f"/v1/responses/{response_id}/input_items",
        headers=AUTH,
        params={"after": "msg_missing"},
    ).status_code == 400
