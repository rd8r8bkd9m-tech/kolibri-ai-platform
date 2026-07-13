from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

from conftest import auth_headers, bootstrap

DEVELOPER_KEY = "sk-" + "kolibri-" + "test-developer-key"


def test_openai_style_bearer_key_authenticates_models_and_responses(client):
    assert client.get("/v1/models").status_code == 401
    headers = {"Authorization": f"Bearer {DEVELOPER_KEY}"}
    models = client.get("/v1/models", headers=headers)
    assert models.status_code == 200
    assert models.json()["data"][0]["id"] == "kolibri"
    response = client.post(
        "/v1/responses",
        headers={**headers, "Idempotency-Key": "api-key-response"},
        json={"model": "kolibri", "input": "Привет"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"


def test_provider_gateway_requires_developer_key_and_fails_closed(client):
    client_token, _ = bootstrap(client)
    denied = client.post(
        "/v1/images/generations",
        headers=auth_headers(client_token),
        json={"model": "gpt-image-1", "prompt": "bird"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "insufficient_permissions"

    allowed = client.post(
        "/v1/images/generations",
        headers={"Authorization": f"Bearer {DEVELOPER_KEY}"},
        json={"model": "gpt-image-1", "prompt": "bird"},
    )
    assert allowed.status_code == 503
    assert allowed.json()["error"]["code"] == "upstream_not_configured"


def test_api_key_is_shown_once_can_be_used_and_revoked(client):
    owner_token, _ = bootstrap(client, "owner")
    owner_headers = auth_headers(owner_token)
    created = client.post(
        "/v1/api-keys",
        headers=owner_headers,
        json={"name": "integration", "role": "developer"},
    )
    assert created.status_code == 200, created.text
    payload = created.json()
    raw = payload["key"]
    assert raw.startswith("sk-kolibri-")

    listed = client.get("/v1/api-keys", headers=owner_headers)
    assert listed.status_code == 200
    matching = next(row for row in listed.json()["data"] if row["id"] == payload["id"])
    assert "key" not in matching
    assert matching["key_prefix"] == raw[:18]

    assert client.get("/v1/models", headers={"Authorization": f"Bearer {raw}"}).status_code == 200
    revoked = client.delete(f"/v1/api-keys/{payload['id']}", headers=owner_headers)
    assert revoked.status_code == 200
    invalid = client.get("/v1/models", headers={"Authorization": f"Bearer {raw}"})
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "invalid_api_key"


def test_realtime_requires_authentication_and_accepts_api_key(client):
    with client.websocket_connect("/v1/realtime") as websocket:
        error = websocket.receive_json()
        assert error["type"] == "error"
        assert error["error"]["code"] == "invalid_api_key"
        with pytest.raises(WebSocketDisconnect) as denied:
            websocket.receive_json()
        assert denied.value.code == 4401

    with client.websocket_connect(
        "/v1/realtime",
        headers={"Authorization": f"Bearer {DEVELOPER_KEY}"},
    ) as websocket:
        created = websocket.receive_json()
        assert created["type"] == "session.created"
        websocket.send_json({"type": "response.create"})
        assert websocket.receive_json()["type"] == "session.updated"
        assert websocket.receive_json()["type"] == "response.output_text.delta"
        assert websocket.receive_json()["type"] == "response.done"
