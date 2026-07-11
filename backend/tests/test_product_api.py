from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("VISTA_ENV", "local")
os.environ.setdefault("VISTA_OWNER_ACCESS_TOKEN", "vista-local-owner")
os.environ.setdefault("VISTA_SESSION_SECRET", "test-session-secret")

from backend.app.main import app
from backend.app.services.database import STORE

client = TestClient(app)


def session(role="client_pro"):
    headers = {"X-Vista-Admin-Token": "vista-local-owner"} if role not in {"client", "client_pro"} else {}
    response = client.post("/api/os/session", json={"role": role, "device": "desktop"}, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    return data["session"], {"Authorization": f"Bearer {data['token']}"}


def create_estimate(headers, name="Квартира 72 м²"):
    response = client.post(
        "/api/estimates",
        headers=headers,
        json={
            "city": "Москва",
            "client": {"name": "Иван Петров", "phone": "+79990000000"},
            "project": {"name": name, "area": 72, "address": "Москва"},
            "assumptions": ["Объёмы уточняются после замера"],
            "items": [
                {"section": "Демонтаж", "name": "Снятие покрытий", "unit": "м²", "qty": 72, "price": 350, "coef": 1},
                {"section": "Стены", "name": "Шпатлёвка и грунт", "unit": "м²", "qty": 180, "price": 420, "coef": 1},
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_liveness_readiness_and_security_headers():
    response = client.get("/api/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    ready = client.get("/api/ready")
    assert ready.status_code == 200
    assert ready.json()["dependencies"] == {"database": "ok", "artifacts": "ok"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers.get("x-request-id")


def test_privileged_role_requires_owner_token():
    denied = client.post("/api/os/session", json={"role": "owner", "device": "desktop"})
    assert denied.status_code == 403
    owner, headers = session("owner")
    assert owner["role"] == "owner"
    assert client.get("/api/audit/events", headers=headers).status_code == 200


def test_estimate_crud_calculation_and_versions():
    _, headers = session()
    estimate = create_estimate(headers)
    assert estimate["summary"]["subtotal"] == 100800
    item = estimate["items"][0]
    updated = client.patch(
        f"/api/estimates/{estimate['id']}/items/{item['id']}",
        headers=headers,
        json={"qty": 80, "price": 400},
    )
    assert updated.status_code == 200
    assert updated.json()["summary"]["subtotal"] == 107600
    added = client.post(
        f"/api/estimates/{estimate['id']}/items",
        headers=headers,
        json={"section": "Пол", "name": "Укладка ламината", "unit": "м²", "qty": 72, "price": 487, "coef": 1},
    )
    assert added.status_code == 200
    assert len(added.json()["items"]) == 3
    version = client.post(f"/api/estimates/{estimate['id']}/versions", headers=headers, json={"note": "Проверенная версия"})
    assert version.status_code == 200
    versions = client.get(f"/api/estimates/{estimate['id']}/versions", headers=headers).json()
    assert versions[0]["note"] == "Проверенная версия"



def test_estimate_cost_settings_and_status_lifecycle():
    _, headers = session()
    estimate = create_estimate(headers, "Настраиваемый объект")
    response = client.patch(
        f"/api/estimates/{estimate['id']}",
        headers=headers,
        json={
            "status": "review",
            "project": {
                "overhead_percent": 10,
                "margin_percent": 20,
                "discount_percent": 5,
                "vat_percent": 20,
            },
        },
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["status"] == "review"
    assert updated["project"]["overhead_percent"] == 10
    assert updated["summary"] == {
        "subtotal": 100800,
        "overhead": 10080,
        "margin": 22176,
        "discount": 6653,
        "tax": 25281,
        "total": 151684,
        "overhead_percent": 10.0,
        "margin_percent": 20.0,
        "discount_percent": 5.0,
        "vat_percent": 20.0,
    }

    invalid = client.patch(
        f"/api/estimates/{estimate['id']}",
        headers=headers,
        json={"status": "invented"},
    )
    assert invalid.status_code == 400
    assert "unsupported estimate status" in invalid.json()["detail"]

def test_session_isolation_for_estimates():
    first, first_headers = session()
    second, second_headers = session()
    estimate = create_estimate(first_headers, "Изолированный объект")
    assert client.get(f"/api/estimates/{estimate['id']}", headers=first_headers).status_code == 200
    assert client.get(f"/api/estimates/{estimate['id']}", headers=second_headers).status_code == 404
    second_list = client.get("/api/estimates", headers=second_headers)
    assert second_list.status_code == 200
    assert all(item["id"] != estimate["id"] for item in second_list.json())
    assert first["id"] != second["id"]


def test_document_generation_creates_real_verified_files():
    _, headers = session()
    estimate = create_estimate(headers, "Документный объект")
    response = client.post(f"/api/estimates/{estimate['id']}/documents", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["task"]["state"] == "completed"
    by_kind = {item["kind"]: item for item in data["artifacts"]}
    assert {"proposal_pdf", "estimate_xlsx", "proposal_docx", "estimate_json", "assumptions_md"} <= set(by_kind)
    signatures = {
        "proposal_pdf": b"%PDF",
        "estimate_xlsx": b"PK",
        "proposal_docx": b"PK",
    }
    for kind, signature in signatures.items():
        artifact = by_kind[kind]
        download = client.get(f"/api/artifacts/{artifact['id']}/download", headers=headers)
        assert download.status_code == 200
        assert download.content.startswith(signature)
        assert hashlib.sha256(download.content).hexdigest() == artifact["sha256"]
        assert len(download.content) == artifact["size_bytes"]
    events = client.get("/api/factory/events", headers=session("owner")[1]).json()
    task_events = [event["event"] for event in events if event["task_id"] == data["task"]["id"]]
    assert "artifact.written" in task_events
    assert "verifier.checked" in task_events
    assert "task.completed" in task_events


def test_public_share_contains_only_client_projection():
    _, headers = session()
    estimate = create_estimate(headers, "Публичное предложение")
    client.post(f"/api/estimates/{estimate['id']}/documents", headers=headers)
    share = client.post(f"/api/estimates/{estimate['id']}/share", headers=headers, json={"ttl_hours": 24})
    assert share.status_code == 200
    public = client.get(f"/api/public/share/{share.json()['token']}")
    assert public.status_code == 200
    payload = public.json()
    assert payload["estimate"]["project"]["name"] == "Публичное предложение"
    assert "owner_session_id" not in payload["estimate"]
    assert all(item["visibility"] == "client" for item in payload["artifacts"])


def test_role_capabilities_protect_admin_functions():
    _, client_headers = session("client_pro")
    assert client.get("/api/server/metrics", headers=client_headers).status_code == 403
    assert client.get("/api/factory/tasks", headers=client_headers).status_code == 403
    _, admin_headers = session("server_admin")
    assert client.get("/api/server/metrics", headers=admin_headers).status_code == 200
    _, owner_headers = session("owner")
    assert client.get("/api/fleet/health", headers=owner_headers).status_code == 200


def test_factory_node_lease_artifact_verifier_flow():
    _, owner_headers = session("owner")
    node = client.post("/api/nodes/register", json={
        "node_id": "pytest-worker", "hostname": "pytest-worker", "role": "worker", "mode": "CONTROLLED_WRITE",
        "capabilities": ["health.probe"], "workers_total": 1, "metrics": {"cpu": 1, "ram": 2, "disk": 3},
    })
    assert node.status_code == 200
    task = client.post("/api/factory/tasks", headers=owner_headers, json={
        "title": "Runtime proof", "kind": "health_probe", "required_capabilities": ["health.probe"], "required_artifacts": ["RESULT.md"],
    }).json()
    lease = client.post("/api/factory/tasks/lease", json={"node_id": "pytest-worker"}).json()
    assert lease["task"]["id"] == task["id"]
    completed = client.post(f"/api/factory/tasks/{task['id']}/complete", json={
        "lease_id": lease["lease"]["id"], "node_id": "pytest-worker",
        "artifacts": [{"name": "RESULT.md", "content_type": "text/markdown", "payload": "# Vista worker result\nOK"}],
    })
    assert completed.status_code == 200, completed.text
    assert completed.json()["state"] == "completed"
    artifacts = client.get(f"/api/factory/tasks/{task['id']}/artifacts", headers=owner_headers).json()
    assert artifacts[0]["sha256"] == hashlib.sha256(b"# Vista worker result\nOK").hexdigest()


def test_developer_key_and_openai_gateway_contract():
    _, headers = session("developer")
    info = client.get("/api/developer/openai-compatibility", headers=headers)
    assert info.status_code == 200
    assert info.json()["base_url"] == "/v1"
    created = client.post("/api/developer/keys", headers=headers, json={"name": "Test SDK", "scopes": ["openai.proxy"]})
    assert created.status_code == 200
    assert created.json()["key"].startswith("vista_sk_")
    keys = client.get("/api/developer/keys", headers=headers).json()
    assert any(item["id"] == created.json()["id"] for item in keys)


def test_request_body_limit(monkeypatch):
    monkeypatch.setenv("VISTA_MAX_BODY_BYTES", "32")
    response = client.post("/api/os/session", content=b"x" * 64, headers={"Content-Length": "64"})
    assert response.status_code == 413
    assert response.json()["request_id"]


def test_public_share_download_and_revoke():
    _, headers = session()
    estimate = create_estimate(headers, "Клиентский пакет")
    generated = client.post(f"/api/estimates/{estimate['id']}/documents", headers=headers).json()
    pdf = next(item for item in generated["artifacts"] if item["kind"] == "proposal_pdf")
    share = client.post(f"/api/estimates/{estimate['id']}/share", headers=headers, json={"ttl_hours": 24}).json()

    listed = client.get(f"/api/estimates/{estimate['id']}/shares", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["token"] == share["token"]

    public = client.get(f"/api/public/share/{share['token']}")
    assert public.status_code == 200
    public_pdf = next(item for item in public.json()["artifacts"] if item["id"] == pdf["id"])
    assert public_pdf["public_download_path"].endswith(f"/{pdf['id']}/download")

    downloaded = client.get(f"/api/public/share/{share['token']}/artifacts/{pdf['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b"%PDF")
    assert hashlib.sha256(downloaded.content).hexdigest() == pdf["sha256"]

    revoked = client.delete(f"/api/estimates/{estimate['id']}/shares/{share['token']}", headers=headers)
    assert revoked.status_code == 200
    assert client.get(f"/api/public/share/{share['token']}").status_code == 404
    assert client.get(f"/api/public/share/{share['token']}/artifacts/{pdf['id']}/download").status_code == 404


def test_workspace_session_state_is_persisted_and_isolated():
    first, first_headers = session()
    second, second_headers = session()
    estimate = create_estimate(first_headers, "Восстанавливаемый объект")
    patch = client.patch(
        f"/api/os/session/{first['id']}",
        headers=first_headers,
        json={
            "active_estimate_id": estimate["id"],
            "windows": [{"component_id": "estimate"}],
            "chat": [{"id": "m1", "kind": "user", "text": "открой смету"}],
        },
    )
    assert patch.status_code == 200
    restored = client.get(f"/api/os/session/{first['id']}", headers=first_headers).json()
    assert restored["active_estimate_id"] == estimate["id"]
    assert restored["windows"] == [{"component_id": "estimate"}]
    assert restored["chat"][0]["text"] == "открой смету"
    assert client.get(f"/api/os/session/{first['id']}", headers=second_headers).status_code == 403
