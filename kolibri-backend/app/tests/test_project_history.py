import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.artifact_store import get_artifact_store
from app.browser_session import SESSION_COOKIE_NAME, validate_anonymous_session
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        bootstrap = test_client.post("/api/v1/shell/bootstrap")
        assert bootstrap.status_code == 200
        yield test_client
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_create_append_and_reload_project_history(client: TestClient):
    created = client.post("/api/v1/projects", json={})
    assert created.status_code == 201
    project = created.json()
    assert project["title"] == "Новый проект"
    assert project["title_source"] == "default"
    assert project["message_count"] == 0

    user = client.post(
        f"/api/v1/projects/{project['id']}/messages",
        json={"role": "user", "content": "Составь смету на строительство одноэтажного дома 100 м² в Лениногорске"},
    )
    assert user.status_code == 201
    assert user.json()["sequence"] == 1

    assistant = client.post(
        f"/api/v1/projects/{project['id']}/messages",
        json={"role": "assistant", "content": "Начинаю расчёт сметы."},
    )
    assert assistant.status_code == 201
    assert assistant.json()["sequence"] == 2

    reloaded_project = client.get(f"/api/v1/projects/{project['id']}")
    assert reloaded_project.status_code == 200
    reloaded = reloaded_project.json()
    assert reloaded["title"] == "Составь смету на строительство одноэтажного дома 100 м² в Лениногорске"
    assert reloaded["title_source"] == "message"
    assert reloaded["message_count"] == 2
    assert reloaded["last_message_at"] is not None

    messages = client.get(f"/api/v1/projects/{project['id']}/messages")
    assert messages.status_code == 200
    payload = messages.json()
    assert payload["total"] == 2
    assert [item["role"] for item in payload["items"]] == ["user", "assistant"]
    assert [item["sequence"] for item in payload["items"]] == [1, 2]

    projects = client.get("/api/v1/projects")
    assert projects.status_code == 200
    assert projects.json()["items"][0]["id"] == project["id"]


def test_project_soft_delete_restore_and_message_recovery(client: TestClient):
    project = client.post("/api/v1/projects", json={"title": "Рабочий чат"}).json()
    client.post(
        f"/api/v1/projects/{project['id']}/messages",
        json={"role": "user", "content": "Сохрани этот диалог"},
    )

    deleted = client.delete(f"/api/v1/projects/{project['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert deleted.json()["deleted_at"] is not None
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404
    assert client.get(f"/api/v1/projects/{project['id']}/messages").status_code == 404
    assert client.get("/api/v1/projects").json()["total"] == 0

    deleted_list = client.get("/api/v1/projects?include_deleted=true").json()
    assert deleted_list["total"] == 1
    assert deleted_list["items"][0]["status"] == "deleted"

    restored = client.post(f"/api/v1/projects/{project['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
    assert restored.json()["deleted_at"] is None
    assert client.get(f"/api/v1/projects/{project['id']}/messages").json()["total"] == 1

    # Restore is idempotent and does not bump the version twice.
    version = restored.json()["version"]
    restored_again = client.post(f"/api/v1/projects/{project['id']}/restore")
    assert restored_again.status_code == 200
    assert restored_again.json()["version"] == version


def test_manual_title_is_not_replaced_by_first_message(client: TestClient):
    project = client.post("/api/v1/projects", json={"title": "Дом в Татарстане"}).json()
    assert project["title_source"] == "manual"

    client.post(
        f"/api/v1/projects/{project['id']}/messages",
        json={"role": "user", "content": "Это первое сообщение с другим названием"},
    )
    reloaded = client.get(f"/api/v1/projects/{project['id']}").json()
    assert reloaded["title"] == "Дом в Татарстане"
    assert reloaded["title_source"] == "manual"

    updated = client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"title": "Смета: дом 100 м²", "metadata": {"vertical": "estimate"}},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Смета: дом 100 м²"
    assert updated.json()["metadata"] == {"vertical": "estimate"}


def test_project_and_message_idempotency(client: TestClient):
    headers = {"Idempotency-Key": "create-project-1"}
    first = client.post("/api/v1/projects", json={"title": "Один проект"}, headers=headers)
    repeated = client.post("/api/v1/projects", json={"title": "Один проект"}, headers=headers)
    conflict = client.post("/api/v1/projects", json={"title": "Другой проект"}, headers=headers)

    assert first.status_code == 201
    assert repeated.status_code == 200
    assert repeated.json()["id"] == first.json()["id"]
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"

    project_id = first.json()["id"]
    message_headers = {"Idempotency-Key": "message-1"}
    message_data = {"role": "user", "content": "Привет"}
    message = client.post(
        f"/api/v1/projects/{project_id}/messages",
        json=message_data,
        headers=message_headers,
    )
    message_repeat = client.post(
        f"/api/v1/projects/{project_id}/messages",
        json=message_data,
        headers=message_headers,
    )
    message_conflict = client.post(
        f"/api/v1/projects/{project_id}/messages",
        json={"role": "user", "content": "Другой текст"},
        headers=message_headers,
    )

    assert message.status_code == 201
    assert message_repeat.status_code == 200
    assert message_repeat.json()["id"] == message.json()["id"]
    assert message_conflict.status_code == 409
    assert client.get(f"/api/v1/projects/{project_id}/messages").json()["total"] == 1


def test_missing_and_cross_scope_projects_are_404(client: TestClient):
    assert client.get("/api/v1/projects/missing").status_code == 404
    assert client.post("/api/v1/projects/missing/messages", json={"role": "user", "content": "x"}).status_code == 404
    assert client.post("/api/v1/projects/missing/restore").status_code == 404

    project = client.post("/api/v1/projects", json={"title": "Изолированный проект"}).json()
    with TestClient(app) as another_browser:
        bootstrap = another_browser.post("/api/v1/shell/bootstrap")
        assert bootstrap.status_code == 200
        assert another_browser.get(
            f"/api/v1/projects/{project['id']}",
            headers={"X-Kolibri-Session": "forged-scope"},
        ).status_code == 404
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 200


def test_message_reload_cursor_is_stable(client: TestClient):
    project = client.post("/api/v1/projects", json={}).json()
    for content in ("one", "two", "three"):
        client.post(
            f"/api/v1/projects/{project['id']}/messages",
            json={"role": "user", "content": content},
        )

    response = client.get(f"/api/v1/projects/{project['id']}/messages?after=1&limit=1")
    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert [(item["sequence"], item["content"]) for item in response.json()["items"]] == [(2, "two")]


def test_shell_bootstrap_creates_and_restores_signed_http_only_session(client: TestClient):
    first = client.post("/api/v1/shell/bootstrap")
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["session_type"] == "anonymous"
    assert first_payload["restored"] is True
    assert len(first_payload["session_id"]) == 32
    assert "kolibri_session" not in first_payload

    set_cookie = first.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/" in set_cookie

    second = client.post("/api/v1/shell/bootstrap")
    assert second.status_code == 200
    assert second.json()["restored"] is True
    assert second.json()["session_id"] == first_payload["session_id"]

    secure = client.post("/api/v1/shell/bootstrap", headers={"X-Forwarded-Proto": "https"})
    assert secure.status_code == 200
    assert "Secure" in secure.headers["set-cookie"]


def test_bootstrap_replaces_tampered_cookie_and_invalid_bearer_without_auth_errors(client: TestClient):
    client.cookies.clear()
    client.cookies.set("kolibri_session", "tampered.value", domain="testserver.local", path="/")
    response = client.post(
        "/api/v1/shell/bootstrap",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 200
    assert response.status_code not in {401, 403}
    assert response.json()["session_type"] == "anonymous"
    assert response.json()["restored"] is False
    signed_cookie = client.cookies.get("kolibri_session")
    assert signed_cookie != "tampered.value"
    assert len(signed_cookie) > 100


def test_missing_or_forged_session_never_becomes_shared_scope(client: TestClient):
    project = client.post("/api/v1/projects", json={"title": "Private"}).json()

    with TestClient(app) as unbootstrapped:
        missing = unbootstrapped.get("/api/v1/projects")
        assert missing.status_code == 428
        assert missing.json()["detail"]["code"] == "session_bootstrap_required"

        unbootstrapped.cookies.set("kolibri_session", "forged.payload")
        forged = unbootstrapped.get(f"/api/v1/projects/{project['id']}")
        assert forged.status_code == 428
        assert forged.status_code not in {401, 403}

        recovered = unbootstrapped.post("/api/v1/shell/bootstrap")
        assert recovered.status_code == 200
        assert recovered.json()["restored"] is False
        assert unbootstrapped.get(f"/api/v1/projects/{project['id']}").status_code == 404


def test_authenticated_principal_overrides_anonymous_cookie(client: TestClient):
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "history@example.test", "name": "History Owner", "password": "secure-password"},
    )
    assert registered.status_code == 201
    token = registered.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    assert client.cookies.get("kolibri_auth")

    project = client.post("/api/v1/projects", json={"title": "Authenticated"}, headers=auth)
    assert project.status_code == 201
    project_id = project.json()["id"]
    client.cookies.delete("kolibri_auth")
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 404
    assert client.get(f"/api/v1/projects/{project_id}", headers=auth).status_code == 200

    bootstrap = client.post("/api/v1/shell/bootstrap", headers=auth)
    assert bootstrap.status_code == 200
    assert bootstrap.json()["session_type"] == "authenticated"
    assert bootstrap.json()["session_id"] == registered.json()["user"]["id"]


def test_assistant_placeholder_streams_and_finalizes_without_duplicate_rows(client: TestClient):
    project = client.post("/api/v1/projects", json={}).json()
    placeholder = client.post(
        f"/api/v1/projects/{project['id']}/messages",
        json={"role": "assistant", "content": "", "status": "pending"},
        headers={"Idempotency-Key": "assistant-placeholder"},
    )
    assert placeholder.status_code == 201
    message_id = placeholder.json()["id"]
    assert placeholder.json()["version"] == 1

    streaming = client.patch(
        f"/api/v1/projects/{project['id']}/messages/{message_id}",
        json={"content": "Начинаю", "status": "streaming"},
        headers={"Idempotency-Key": "assistant-stream-1"},
    )
    assert streaming.status_code == 200
    assert streaming.json()["status"] == "streaming"
    assert streaming.json()["version"] == 2

    completed = client.patch(
        f"/api/v1/projects/{project['id']}/messages/{message_id}",
        json={"content": "Готовый проверенный ответ", "status": "completed"},
        headers={"Idempotency-Key": "assistant-final-1"},
    )
    repeated = client.patch(
        f"/api/v1/projects/{project['id']}/messages/{message_id}",
        json={"content": "Готовый проверенный ответ", "status": "completed"},
        headers={"Idempotency-Key": "assistant-final-1"},
    )
    assert completed.status_code == 200
    assert repeated.status_code == 200
    assert completed.json() == repeated.json()
    assert completed.json()["version"] == 3

    messages = client.get(f"/api/v1/projects/{project['id']}/messages").json()
    assert messages["total"] == 1
    assert messages["items"][0]["id"] == message_id
    assert messages["items"][0]["content"] == "Готовый проверенный ответ"


def test_send_stream_and_reload_keeps_exactly_one_assistant_placeholder(client: TestClient):
    project = client.post(
        "/api/v1/projects",
        json={"client_request_id": "send-stream-reload-project"},
        headers={"Idempotency-Key": "project:send-stream-reload"},
    ).json()
    user = client.post(
        f"/api/v1/projects/{project['id']}/messages",
        json={
            "role": "user",
            "content": "привет",
            "status": "completed",
            "client_message_id": "send-stream-user",
        },
        headers={"Idempotency-Key": "message:send-stream-user"},
    )
    assert user.status_code == 201

    placeholder_payload = {
        "role": "assistant",
        "content": "",
        "status": "pending",
        "client_message_id": "send-stream-assistant",
    }
    placeholder = client.post(
        f"/api/v1/projects/{project['id']}/messages",
        json=placeholder_payload,
        headers={"Idempotency-Key": "message:send-stream-assistant"},
    )
    repeated_placeholder = client.post(
        f"/api/v1/projects/{project['id']}/messages",
        json=placeholder_payload,
        headers={"Idempotency-Key": "message:send-stream-assistant"},
    )
    assert placeholder.status_code == 201
    assert repeated_placeholder.status_code == 200
    assert repeated_placeholder.json()["id"] == placeholder.json()["id"]

    message_id = placeholder.json()["id"]
    assert client.patch(
        f"/api/v1/projects/{project['id']}/messages/{message_id}",
        json={"content": "При", "status": "streaming", "metadata": {"response_id": "resp_kolibri_1"}},
        headers={"Idempotency-Key": "assistant:stream:1"},
    ).status_code == 200
    assert client.patch(
        f"/api/v1/projects/{project['id']}/messages/{message_id}",
        json={"content": "Привет!", "status": "completed", "metadata": {"response_id": "resp_kolibri_1"}},
        headers={"Idempotency-Key": "assistant:completed:1"},
    ).status_code == 200

    reloaded = client.get(f"/api/v1/projects/{project['id']}/messages").json()["items"]
    assert [item["role"] for item in reloaded] == ["user", "assistant"]
    assistants = [item for item in reloaded if item["role"] == "assistant"]
    assert len(assistants) == 1
    assert assistants[0]["id"] == message_id
    assert assistants[0]["status"] == "completed"
    assert assistants[0]["content"] == "Привет!"


def test_verified_artifact_metadata_survives_reload_without_duplicate_assistant(client: TestClient):
    project = client.post("/api/v1/projects", json={}).json()
    placeholder = client.post(
        f"/api/v1/projects/{project['id']}/messages",
        json={"role": "assistant", "content": "", "status": "pending"},
        headers={"Idempotency-Key": "artifact-assistant-placeholder"},
    ).json()
    artifact_id = "11111111-1111-4111-8111-111111111111"
    artifact = {
        "id": artifact_id,
        "type": "image",
        "revision": 1,
        "title": "Цветы",
        "prompt": "Букет полевых цветов",
        "mime_type": "image/png",
        "size_bytes": 2048,
        "sha256": "a" * 64,
        "model": "gpt-image-1",
        "created_at": "2026-07-13T13:00:00Z",
        "updated_at": "2026-07-13T13:00:01Z",
        "url": f"/api/v1/artifacts/images/{artifact_id}",
        "download_url": f"/api/v1/artifacts/images/{artifact_id}?download=true",
        "revision_url": f"/api/v1/artifacts/{artifact_id}?revision=1",
        "revision_download_url": f"/api/v1/artifacts/{artifact_id}?revision=1&download=true",
        "reopen_url": f"/api/v1/artifacts/{artifact_id}/reopen",
        "history_url": f"/api/v1/artifacts/{artifact_id}/history",
    }
    completed = client.patch(
        f"/api/v1/projects/{project['id']}/messages/{placeholder['id']}",
        json={
            "content": "Изображение готово.",
            "status": "completed",
            "metadata": {
                "response_id": "resp_kolibri_image_1",
                "work_events": [{
                    "stage": "artifact_verification",
                    "status": "completed",
                    "summary": "Файл проверен",
                    "artifact_type": "image",
                    "artifact_id": artifact_id,
                }],
                "artifact": artifact,
            },
        },
        headers={"Idempotency-Key": "artifact-assistant-complete"},
    )
    assert completed.status_code == 200

    reloaded = client.get(f"/api/v1/projects/{project['id']}/messages").json()["items"]
    assistants = [item for item in reloaded if item["role"] == "assistant"]
    assert len(assistants) == 1
    assert assistants[0]["id"] == placeholder["id"]
    assert assistants[0]["status"] == "completed"
    assert assistants[0]["metadata"]["artifact"]["url"] == artifact["url"]
    assert assistants[0]["metadata"]["artifact"]["reopen_url"] == artifact["reopen_url"]
    assert assistants[0]["metadata"]["artifact"]["sha256"] == artifact["sha256"]


def test_verified_file_action_and_artifact_survive_reload_with_scoped_cas_bytes(
    client: TestClient,
):
    session = validate_anonymous_session(client.cookies.get(SESSION_COOKIE_NAME))
    assert session is not None
    artifact = get_artifact_store().put_bytes(
        b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n",
        artifact_type="document.pdf",
        mime_type="application/pdf",
        filename="real-document.pdf",
        title="Реальный документ",
        metadata={
            "scope_key": hashlib.sha256(session.scope_id.encode()).hexdigest(),
            "producer_capability": "document.pdf",
        },
    )
    public_artifact = {
        key: value
        for key, value in artifact.items()
        if key not in {"schema_version", "_blob"}
    }
    project = client.post("/api/v1/projects", json={}).json()
    action = {
        "type": "present_artifact",
        "label": "Открыть PDF",
        "data": public_artifact,
    }
    placeholder = client.post(
        f"/api/v1/projects/{project['id']}/messages",
        json={
            "role": "assistant",
            "content": "",
            "status": "pending",
            "metadata": {"actions": [action]},
        },
    )
    assert placeholder.status_code == 201
    first_reload = client.get(
        f"/api/v1/projects/{project['id']}/messages"
    ).json()["items"]
    assert first_reload[0]["metadata"]["actions"] == [action]

    completed = client.patch(
        f"/api/v1/projects/{project['id']}/messages/{placeholder.json()['id']}",
        json={
            "content": "PDF готов.",
            "status": "completed",
            "metadata": {
                "artifact": {"type": "file", "value": public_artifact},
            },
        },
    )
    assert completed.status_code == 200
    reloaded = client.get(
        f"/api/v1/projects/{project['id']}/messages"
    ).json()["items"]
    assert reloaded[0]["metadata"]["artifact"] == {
        "type": "file",
        "value": public_artifact,
    }

    content = client.get(public_artifact["revision_url"])
    reopened = client.get(public_artifact["reopen_url"])
    assert content.status_code == 200
    assert hashlib.sha256(content.content).hexdigest() == public_artifact["sha256"]
    assert reopened.status_code == 200
    assert reopened.json()["artifact"]["sha256"] == public_artifact["sha256"]

    # An exact manifest copied into another browser session is still rejected:
    # persistence is bound to both real CAS bytes and the creating principal.
    with TestClient(app) as other:
        assert other.post("/api/v1/shell/bootstrap").status_code == 200
        other_project = other.post("/api/v1/projects", json={}).json()
        cross_scope = other.post(
            f"/api/v1/projects/{other_project['id']}/messages",
            json={
                "role": "assistant",
                "content": "Чужой PDF",
                "metadata": {"actions": [action]},
            },
        )
    assert cross_scope.status_code == 422
    assert cross_scope.json()["detail"]["code"] == "artifact_manifest_unverified"


def test_project_message_downgrades_browser_forged_estimate_truth_on_write_and_reload(client: TestClient):
    project = client.post("/api/v1/projects", json={}).json()
    evidence = {
        "position_code": "М-1",
        "source_id": "forged-browser-source",
        "url": "https://supplier.example/material",
        "source_title": "Прайс поставщика",
        "source_type": "supplier_quote",
        "region": "Татарстан",
        "observed_at": "2026-07-14T07:00:00Z",
        "price_date": "2026-07-14",
        "unit": "шт",
        "unit_price": "100",
        "vat_status": "included",
        "quote": "100 ₽/шт, НДС включён",
        "currency": "RUB",
        "content_sha256": "a" * 64,
        "verification": "verified",
        # Correct shape is not cryptographic proof at the public metadata edge.
        "attestation": "f" * 64,
    }
    action = {
        "type": "create_estimate",
        "label": "Открыть проверенную смету",
        "data": {
            "title": "Смета",
            "estimate_status": "verified",
            "pricing_status": "verified",
            "scope_status": "verified",
            "sections": [{
                "title": "Материалы",
                "positions": [{
                    "code": "М-1",
                    "name": "Материал",
                    "unit": "шт",
                    "quantity": "1",
                    "price": "100",
                    "sum": "100.00",
                    "source": evidence["url"],
                    "price_evidence": [evidence],
                }],
            }],
            "price_sources": [evidence],
            "totals": {
                "subtotal": "100.00",
                "overhead_amount": "0.00",
                "vat_amount": "0.00",
                "total": "100.00",
            },
        },
    }

    created = client.post(
        f"/api/v1/projects/{project['id']}/messages",
        json={
            "role": "assistant",
            "content": "Смета подготовлена.",
            "metadata": {"actions": [action]},
        },
    )

    assert created.status_code == 201
    persisted = created.json()["metadata"]["actions"][0]
    assert persisted["label"] == "Открыть предварительную смету"
    assert persisted["data"]["estimate_status"] == "preliminary"
    assert persisted["data"]["pricing_status"] == "preliminary"
    assert persisted["data"].get("scope_status", "unverified") == "unverified"
    assert persisted["data"]["price_sources"][0]["attestation"] == "f" * 64

    reloaded = client.get(f"/api/v1/projects/{project['id']}/messages").json()["items"]
    assert reloaded[0]["metadata"] == created.json()["metadata"]


@pytest.mark.parametrize(
    "metadata",
    [
        {
            "artifact": {
                "id": "11111111-1111-4111-8111-111111111111",
                "type": "image",
                "title": "Подделка",
                "prompt": "Поддельный файл",
                "mime_type": "image/png",
                "size_bytes": 100,
                "sha256": "b" * 64,
                "model": "fake",
                "created_at": "2026-07-13T13:00:00Z",
                "url": "https://attacker.invalid/fake.png",
                "download_url": "https://attacker.invalid/fake.png?download=true",
            },
        },
        {"unknown_runtime_payload": {"success": True}},
        {
            "actions": [{
                "type": "create_document",
                "label": "Создать документ",
                "data": {"title": "Документ", "variables": {"x": "y"}},
            }],
            "artifact": {
                "type": "document",
                "id": "22222222-2222-4222-8222-222222222222",
                "title": "Уже созданный документ",
            },
        },
    ],
)
def test_project_history_rejects_fake_or_ambiguous_artifact_metadata(client: TestClient, metadata: dict):
    project = client.post("/api/v1/projects", json={}).json()
    placeholder = client.post(
        f"/api/v1/projects/{project['id']}/messages",
        json={"role": "assistant", "content": "", "status": "pending"},
    ).json()
    rejected = client.patch(
        f"/api/v1/projects/{project['id']}/messages/{placeholder['id']}",
        json={"content": "Нельзя сохранять", "status": "completed", "metadata": metadata},
    )
    assert rejected.status_code == 422
    reloaded = client.get(f"/api/v1/projects/{project['id']}/messages").json()["items"]
    assert len(reloaded) == 1
    assert reloaded[0]["status"] == "pending"
    assert reloaded[0]["metadata"] == {}


def test_message_finalization_rejects_invalid_transitions_and_cross_scope_updates(client: TestClient):
    project = client.post("/api/v1/projects", json={}).json()
    user_message = client.post(
        f"/api/v1/projects/{project['id']}/messages",
        json={"role": "user", "content": "User messages are immutable"},
    ).json()
    immutable = client.patch(
        f"/api/v1/projects/{project['id']}/messages/{user_message['id']}",
        json={"content": "Changed"},
    )
    assert immutable.status_code == 409
    assert immutable.json()["detail"]["code"] == "invalid_message_transition"

    assistant = client.post(
        f"/api/v1/projects/{project['id']}/messages",
        json={"role": "assistant", "content": "Done", "status": "completed"},
    ).json()
    invalid = client.patch(
        f"/api/v1/projects/{project['id']}/messages/{assistant['id']}",
        json={"status": "streaming"},
    )
    assert invalid.status_code == 409

    with TestClient(app) as another_browser:
        another_browser.post("/api/v1/shell/bootstrap")
        cross_scope = another_browser.patch(
            f"/api/v1/projects/{project['id']}/messages/{assistant['id']}",
            json={"status": "completed"},
        )
        assert cross_scope.status_code == 404


def test_message_update_idempotency_conflict_is_detected(client: TestClient):
    project = client.post("/api/v1/projects", json={}).json()
    assistant = client.post(
        f"/api/v1/projects/{project['id']}/messages",
        json={"role": "assistant", "content": "", "status": "pending"},
    ).json()
    url = f"/api/v1/projects/{project['id']}/messages/{assistant['id']}"
    headers = {"Idempotency-Key": "same-update-key"}
    assert client.patch(url, json={"content": "A", "status": "streaming"}, headers=headers).status_code == 200
    conflict = client.patch(url, json={"content": "B", "status": "streaming"}, headers=headers)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"


def test_empty_completed_assistant_placeholder_is_rejected(client: TestClient):
    project = client.post("/api/v1/projects", json={}).json()
    placeholder = client.post(
        f"/api/v1/projects/{project['id']}/messages",
        json={"role": "assistant", "content": "", "status": "pending"},
    ).json()
    completed = client.patch(
        f"/api/v1/projects/{project['id']}/messages/{placeholder['id']}",
        json={"status": "completed"},
    )
    assert completed.status_code == 409
    assert completed.json()["detail"]["code"] == "invalid_message_transition"
