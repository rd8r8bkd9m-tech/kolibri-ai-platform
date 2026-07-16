import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import ai_provider, auth as auth_module, capability_runtime
from app.auth import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models import PublicApiKeyDB, UserDB


@pytest.fixture()
def client(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        with testing_session() as db:
            yield db

    owner_token = "owner-test-token"
    monkeypatch.setenv(
        "KOLIBRI_OWNER_API_ADMIN_TOKEN_SHA256",
        hashlib.sha256(owner_token.encode()).hexdigest(),
    )
    monkeypatch.setenv("KOLIBRI_RELEASE_ID", "kolibri-r17-20260713T1932MSK")
    monkeypatch.setattr(auth_module, "SECRET_KEY", "release-test-jwt-secret-0123456789abcdef")
    monkeypatch.delenv("KOLIBRI_PUBLIC_API_KEY_SHA256", raising=False)
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("KOLIBRI_CAPABILITY_PROBE_FILE", str(tmp_path / "capability-probes.json"))
    with testing_session() as db:
        db.add(UserDB(
            id="user-platform-owner",
            email="owner@example.test",
            name="Platform owner",
            hashed_password="not-used",
            role="owner",
            is_active=True,
        ))
        db.commit()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        owner_session_token = create_access_token({"sub": "user-platform-owner"})
        test_client.owner_headers = {
            "Authorization": "Bearer " + owner_session_token
        }
        test_client.owner_session_token = owner_session_token
        test_client.legacy_owner_headers = {
            "X-Kolibri-Owner-Token": owner_token
        }
        test_client.testing_session = testing_session
        yield test_client
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_release_identity_and_request_id_are_on_success_and_error(client):
    health = client.get("/api/health", headers={"X-Request-ID": "req_owner_probe"})
    assert health.status_code == 200
    assert health.headers["X-Kolibri-Release"] == "kolibri-r17-20260713T1932MSK"
    assert health.headers["X-Request-ID"] == "req_owner_probe"
    assert health.json()["release_id"] == "kolibri-r17-20260713T1932MSK"

    denied = client.get("/v1/models")
    assert denied.status_code == 503
    assert denied.headers["X-Kolibri-Release"] == "kolibri-r17-20260713T1932MSK"
    assert denied.headers["X-Request-ID"].startswith("req_")
    assert denied.json()["error"] == {
        "message": "public_api_not_configured",
        "type": "server_error",
        "code": "public_api_not_configured",
        "request_id": denied.headers["X-Request-ID"],
    }


def test_owner_key_create_use_list_revoke_and_hash_only_persistence(client, monkeypatch):
    async def fake_completion(messages, **kwargs):
        return {
            "content": "Ответ через ключ разработчика.",
            "status": "completed",
            "provider": "test",
        }

    monkeypatch.setattr(ai_provider, "chat_completion", fake_completion)
    created = client.post(
        "/api/v1/developer/api-keys",
        headers=client.owner_headers,
        json={"name": "Release E2E"},
    )
    assert created.status_code == 201
    body = created.json()
    secret = body["secret"]
    assert secret.startswith("koli_live_")
    assert body["secret_shown_once"] is True
    assert body["revoked"] is False
    assert created.headers["Cache-Control"] == "no-store"
    assert created.headers["Pragma"] == "no-cache"
    assert set(body) == {
        "id", "object", "name", "prefix", "created_at", "last_used_at",
        "revoked", "revoked_at", "secret", "secret_shown_once",
    }

    with client.testing_session() as db:
        row = db.query(PublicApiKeyDB).filter(PublicApiKeyDB.id == body["id"]).one()
        assert row.secret_hash == hashlib.sha256(secret.encode()).hexdigest()
        assert secret not in row.secret_hash
        assert row.key_prefix == secret[:14]

    created_capability = next(
        item
        for item in client.get("/api/v1/capabilities").json()["capabilities"]
        if item["id"] == "developer.api_keys"
    )
    assert created_capability["status"] == "available"
    assert created_capability["invocable"] is True

    listed = client.get("/api/v1/developer/api-keys", headers=client.owner_headers)
    assert listed.status_code == 200
    assert listed.headers["Cache-Control"] == "no-store"
    assert listed.json()["object"] == "list"
    assert listed.json()["data"][0]["id"] == body["id"]
    assert "secret" not in listed.json()["data"][0]
    assert "secret_shown_once" not in listed.json()["data"][0]

    bearer = {"Authorization": f"Bearer {secret}"}
    models = client.get("/v1/models", headers=bearer)
    assert models.status_code == 200
    assert [item["id"] for item in models.json()["data"]] == ["kolibri"]
    response = client.post(
        "/v1/responses",
        headers={**bearer, "Idempotency-Key": "developer-release-e2e"},
        json={"model": "kolibri", "input": "Привет"},
    )
    assert response.status_code == 200
    assert response.json()["output_text"] == "Ответ через ключ разработчика."
    proved = next(
        item
        for item in client.get("/api/v1/capabilities").json()["capabilities"]
        if item["id"] == "developer.api_keys"
    )
    assert proved["status"] == "available"
    assert proved["invocable"] is True

    revoked = client.delete(
        f"/api/v1/developer/api-keys/{body['id']}",
        headers=client.owner_headers,
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked"] is True
    assert "secret" not in revoked.json()
    assert revoked.headers["Cache-Control"] == "no-store"
    denied = client.get("/v1/models", headers=bearer)
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "invalid_api_key"


def test_api_key_create_returns_one_time_secret_when_evidence_write_fails(client, monkeypatch):
    def fail_evidence(*args, **kwargs):
        raise OSError("probe ledger unavailable")

    monkeypatch.setattr(capability_runtime, "record_capability_invocation", fail_evidence)

    created = client.post(
        "/api/v1/developer/api-keys",
        headers=client.owner_headers,
        json={"name": "Evidence down"},
    )

    assert created.status_code == 201
    body = created.json()
    assert body["secret"].startswith("koli_live_")
    assert body["secret_shown_once"] is True

    with client.testing_session() as db:
        row = db.query(PublicApiKeyDB).filter(PublicApiKeyDB.id == body["id"]).one()
        assert row.key_prefix == body["secret"][:14]
        assert row.secret_hash == hashlib.sha256(body["secret"].encode()).hexdigest()


def test_api_key_revoke_survives_evidence_write_failure(client, monkeypatch):
    created = client.post(
        "/api/v1/developer/api-keys",
        headers=client.owner_headers,
        json={"name": "Revoke evidence down"},
    )
    assert created.status_code == 201
    key_id = created.json()["id"]

    def fail_evidence(*args, **kwargs):
        raise OSError("probe ledger unavailable")

    monkeypatch.setattr(capability_runtime, "record_capability_invocation", fail_evidence)
    revoked = client.delete(
        f"/api/v1/developer/api-keys/{key_id}",
        headers=client.owner_headers,
    )

    assert revoked.status_code == 200
    assert revoked.json()["revoked"] is True
    with client.testing_session() as db:
        row = db.query(PublicApiKeyDB).filter(PublicApiKeyDB.id == key_id).one()
        assert row.revoked_at is not None


def test_api_key_name_must_remain_nonempty_after_normalisation(client):
    response = client.post(
        "/api/v1/developer/api-keys",
        headers=client.owner_headers,
        json={"name": "   "},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "api_key_name_required"


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("get", "/api/v1/developer/api-keys", None),
        ("post", "/api/v1/developer/api-keys", {"name": "Denied"}),
        ("delete", "/api/v1/developer/api-keys/key_missing", None),
    ],
)
def test_exact_developer_key_routes_require_platform_owner_session(client, method, path, json):
    response = client.request(method, path, json=json)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "request_failed"

    wrong = client.request(
        method,
        path,
        headers={"Authorization": "Bearer invalid-platform-session"},
        json=json,
    )
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "request_failed"


def test_legacy_api_key_admin_route_keeps_separate_machine_credential(client):
    created = client.post(
        "/v1/api-keys",
        headers=client.legacy_owner_headers,
        json={"name": "Legacy automation"},
    )
    assert created.status_code == 201

    browser_session_is_not_a_machine_credential = client.get(
        "/v1/api-keys",
        headers=client.owner_headers,
    )
    assert browser_session_is_not_a_machine_credential.status_code == 401
    assert (
        browser_session_is_not_a_machine_credential.json()["error"]["code"]
        == "owner_authentication_required"
    )


def test_cookie_api_key_mutations_require_exact_same_origin(client):
    client.cookies.set("kolibri_auth", client.owner_session_token)
    denied = client.post(
        "/api/v1/developer/api-keys",
        headers={"Origin": "https://evil.example"},
        json={"name": "CSRF denied"},
    )
    created = client.post(
        "/api/v1/developer/api-keys",
        headers={"Origin": "http://testserver"},
        json={"name": "Browser session"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "csrf_origin_forbidden"
    assert created.status_code == 201

    key_id = created.json()["id"]
    denied_revoke = client.delete(
        f"/api/v1/developer/api-keys/{key_id}",
        headers={"Origin": "https://evil.example"},
    )
    revoked = client.delete(
        f"/api/v1/developer/api-keys/{key_id}",
        headers={"Origin": "http://testserver"},
    )
    assert denied_revoke.status_code == 403
    assert revoked.status_code == 200
    client.cookies.clear()


def test_developer_capability_is_truthful_until_admin_route_is_invocable(client, monkeypatch):
    manifest = client.get("/api/v1/capabilities").json()
    capability = next(
        item for item in manifest["capabilities"] if item["id"] == "developer.api_keys"
    )
    assert capability["status"] == "degraded"
    assert capability["invocable"] is False
    assert capability["reason"]["code"] == "probe_not_run"
    assert capability["renderer"]["required"] is False

    monkeypatch.delenv("KOLIBRI_OWNER_API_ADMIN_TOKEN_SHA256", raising=False)
    unavailable = client.get("/api/v1/capabilities").json()
    capability = next(
        item for item in unavailable["capabilities"] if item["id"] == "developer.api_keys"
    )
    assert capability["status"] == "unavailable"
    assert capability["invocable"] is False
    assert capability["reason"]["code"] == "route_not_configured"
