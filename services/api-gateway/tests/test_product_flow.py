from __future__ import annotations

import hashlib

from conftest import auth_headers, bootstrap


def test_bootstrap_response_and_reload_do_not_duplicate_assistant(client):
    token, project_id = bootstrap(client)
    headers = auth_headers(token)
    created = client.post(
        "/v1/responses",
        headers={**headers, "Idempotency-Key": "estimate-1"},
        json={"model": "kolibri", "project_id": project_id, "input": "Сделай смету на ремонт квартиры 72 м² в Москве"},
    )
    assert created.status_code == 200, created.text
    response = created.json()
    assert response["status"] == "completed"
    assert response["model"] == "kolibri"
    replay = client.post(
        "/v1/responses",
        headers={**headers, "Idempotency-Key": "estimate-1"},
        json={"model": "kolibri", "project_id": project_id, "input": "Сделай смету на ремонт квартиры 72 м² в Москве"},
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == response["id"]
    messages = client.get(f"/v1/projects/{project_id}/messages", headers=headers).json()["data"]
    assistant = [message for message in messages if message["role"] == "assistant"]
    assert len(assistant) == 1
    assert assistant[0]["content"]


def test_estimate_is_preliminary_then_verified_and_exports_real_bytes(client):
    token, project_id = bootstrap(client)
    headers = auth_headers(token)
    estimate = client.post(
        "/v1/estimates",
        headers=headers,
        json={"project_id": project_id, "title": "Смета: квартира 72 м² — Москва", "client_name": "Иван", "region": "Москва"},
    ).json()
    assert estimate["status"] == "needs_input"
    estimate = client.post(
        f"/v1/estimates/{estimate['id']}/items",
        headers=headers,
        json={"section": "Стены", "name": "Шпатлёвка и грунт", "unit": "м²", "quantity": "180", "unit_price": "420"},
    ).json()
    assert estimate["status"] == "preliminary"
    assert estimate["total"] == "75600.00"
    source_payload = {
        "title": "Прайс поставщика",
        "url": "https://example.com/price",
        "region": "Москва",
        "price_date": "2026-07-01",
        "unit": "м²",
        "verification_status": "verified",
    }
    source = client.post(f"/v1/estimates/{estimate['id']}/sources", headers=headers, json=source_payload).json()["source"]
    item_id = estimate["items"][0]["id"]
    estimate = client.patch(
        f"/v1/estimates/{estimate['id']}/items/{item_id}",
        headers=headers,
        json={"source_id": source["id"]},
    ).json()
    assert estimate["status"] == "verified"
    exported = client.post(
        f"/v1/estimates/{estimate['id']}/exports",
        headers=headers,
        json={"formats": ["pdf", "xlsx", "docx", "json", "md"]},
    )
    assert exported.status_code == 200, exported.text
    artifacts = exported.json()["artifacts"]
    assert {artifact["mime_type"].split(";")[0] for artifact in artifacts} >= {"application/pdf", "application/json", "text/markdown"}
    pdf = next(artifact for artifact in artifacts if artifact["mime_type"] == "application/pdf")
    content = client.get(f"/v1/artifacts/{pdf['id']}/content", headers=headers)
    assert content.status_code == 200
    assert content.content.startswith(b"%PDF-")
    assert hashlib.sha256(content.content).hexdigest() == pdf["sha256"]


def test_client_isolation_and_project_soft_delete_restore(client):
    token_a, project_a = bootstrap(client)
    client.cookies.clear()
    token_b, _ = bootstrap(client)
    headers_a, headers_b = auth_headers(token_a), auth_headers(token_b)
    estimate = client.post("/v1/estimates", headers=headers_a, json={"project_id": project_a, "title": "Private"}).json()
    assert client.get(f"/v1/estimates/{estimate['id']}", headers=headers_b).status_code == 404
    deleted = client.delete(f"/v1/projects/{project_a}", headers=headers_a)
    assert deleted.status_code == 200
    assert all(project["id"] != project_a for project in client.get("/v1/projects", headers=headers_a).json()["data"])
    restored = client.post(f"/v1/projects/{project_a}/restore", headers=headers_a)
    assert restored.status_code == 200
    assert restored.json()["deleted_at"] is None


def test_public_bootstrap_cannot_escalate_role(client):
    denied = client.post("/v1/shell/bootstrap", json={"role": "owner"})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "role_escalation_denied"
    allowed = client.post(
        "/v1/shell/bootstrap",
        headers={"X-Kolibri-Access-Token": "owner-secret"},
        json={"role": "owner"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["session"]["role"] == "owner"


def test_existing_client_cookie_cannot_be_upgraded(client):
    initial = client.post("/v1/shell/bootstrap", json={"role": "client"})
    assert initial.status_code == 200
    session_id = initial.json()["session"]["id"]
    attempted = client.post(
        "/v1/shell/bootstrap",
        headers={"X-Kolibri-Access-Token": "owner-secret"},
        json={"role": "owner"},
    )
    assert attempted.status_code == 200
    assert attempted.json()["session"]["id"] == session_id
    assert attempted.json()["session"]["role"] == "client"
