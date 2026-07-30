from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient
import pytest

from app.attachment_store import (
    ATTACHMENT_CONTRACT_MAX_BYTES,
    USER_ATTACHMENT_MAX_BYTES,
    AttachmentTooLargeError,
    resolve_storage_path,
    store_content_chunks,
)
from app.agent_runtime import AgentRuntimeRegistry
from app.chat.execution_adapter import PreparedChatExecution
from app.chat.models import AgUiRunInput
from app.chat.service import accept_run
from app.config import Settings
from app.database import connect_database, transaction
from app.identity import require_user
from app.main import create_app
from app.provider_execution import _generated_contracts
from app.schemas import AgentProfile, UserRole, UserSession


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"
PROJECT_ID = "project_attachment_scope_01"
THREAD_ID = "thread_attachment_scope_01"
CSV_BYTES = "позиция,количество\nКабель,12\n".encode()


def _settings(database_path: Path) -> Settings:
    return replace(
        Settings.for_testing(
            database_url=database_path,
            bootstrap_owner_email=None,
        ),
        direct_model_runtime_enabled=True,
        product_run_poll_seconds=0.05,
    )


def _register(
    client: TestClient,
    *,
    email: str = "attachment-owner@example.com",
) -> tuple[str, dict[str, object]]:
    response = client.post(
        "/v1/auth/register",
        headers=ORIGIN,
        json={
            "email": email,
            "name": "Attachment Owner",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    csrf = client.cookies.get("kolibri_v3_csrf")
    assert isinstance(csrf, str) and csrf
    user = response.json()["user"]
    assert isinstance(user, dict)
    return csrf, user


def _mobile_login(client: TestClient, *, email: str) -> str:
    response = client.post(
        "/v1/mobile/auth/login",
        json={
            "email": email,
            "password": PASSWORD,
            "device": {
                "platform": "ios",
                "deviceName": "Attachment iPhone",
                "appVersion": "1.0.0",
            },
        },
    )
    assert response.status_code == 200, response.text
    token = response.json()["accessToken"]
    assert isinstance(token, str) and token
    return token


def _seed_scope(
    database_path: Path,
    *,
    tenant_id: str,
    user_id: str,
) -> None:
    database = connect_database(database_path)
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        with transaction(database, immediate=True):
            database.execute(
                """
                INSERT INTO projects (
                    tenant_id, id, created_by_user_id, title, status,
                    primary_thread_id, created_at, updated_at
                ) VALUES (?, ?, ?, 'Attachment scope', 'active', ?, ?, ?)
                """,
                (
                    tenant_id,
                    PROJECT_ID,
                    user_id,
                    THREAD_ID,
                    created_at,
                    created_at,
                ),
            )
            database.execute(
                """
                INSERT INTO chat_threads (
                    tenant_id, id, project_id, kind, title, status,
                    message_count, run_count, last_message_at,
                    created_at, updated_at
                ) VALUES (
                    ?, ?, ?, 'primary', 'Attachment scope', 'regular',
                    0, 0, NULL, ?, ?
                )
                """,
                (
                    tenant_id,
                    THREAD_ID,
                    PROJECT_ID,
                    created_at,
                    created_at,
                ),
            )
    finally:
        database.close()


def _upload_headers(
    csrf: str | None,
    *,
    attachment_id: str,
    filename: str = "данные.csv",
    mime_type: str = "text/csv",
    project_id: str = PROJECT_ID,
    thread_id: str = THREAD_ID,
) -> dict[str, str]:
    headers = {
        **ORIGIN,
        "Content-Type": mime_type,
        "Idempotency-Key": attachment_id,
        "X-Kolibri-Filename": quote(filename, safe=""),
        "X-Kolibri-Project-Id": project_id,
        "X-Kolibri-Thread-Id": thread_id,
    }
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    return headers


def _identity(user: dict[str, object]) -> UserSession:
    return UserSession(
        user_id=str(user["id"]),
        tenant_id=str(user["tenantId"]),
        role=UserRole.USER,
        preferred_agent_profile=AgentProfile.AUTO,
        email=str(user["email"]),
        name=str(user["name"]),
    )


def _run_input(
    attachment: dict[str, object],
    *,
    run_id: str = "run_attachment_send_01",
    message_id: str = "message_attachment_send_01",
) -> AgUiRunInput:
    return AgUiRunInput.model_validate(
        {
            "threadId": THREAD_ID,
            "runId": run_id,
            "state": None,
            "messages": [
                {
                    "id": message_id,
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Проанализируй приложенную таблицу.",
                        },
                        {
                            "type": "document",
                            "source": {
                                "type": "url",
                                "value": attachment["content_path"],
                                "mimeType": attachment["mime_type"],
                            },
                            "metadata": {
                                "filename": attachment["filename"],
                            },
                        },
                    ],
                }
            ],
            "tools": [],
            "context": [],
            "forwardedProps": {
                "agentProfile": "auto",
                "executionMode": "standard",
                "accessMode": "standard",
            },
        }
    )


def _public_run_payload(
    *,
    thread_id: str,
    run_id: str,
    message_id: str,
    content: str | list[dict[str, object]],
) -> dict[str, object]:
    return {
        "threadId": thread_id,
        "runId": run_id,
        "state": None,
        "messages": [
            {
                "id": message_id,
                "role": "user",
                "content": content,
            }
        ],
        "tools": [],
        "context": [],
        "forwardedProps": {
            "agentProfile": "auto",
            "executionMode": "standard",
            "accessMode": "standard",
        },
    }


def test_browser_upload_is_streamed_idempotent_and_durable_in_chat(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "attachment-browser.db"
    settings = _settings(database_path)
    app = create_app(settings)

    with TestClient(app) as client:
        # Keep the direct execution plane for acceptance, but do not let a
        # model worker race the durable acceptance assertions below.
        dispatcher = app.state.direct_run_dispatcher
        assert dispatcher is not None
        dispatcher.close()
        app.state.direct_run_dispatcher = None

        csrf, user = _register(client)
        tenant_id = str(user["tenantId"])
        user_id = str(user["id"])
        _seed_scope(
            database_path,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        capability = client.get(
            "/v1/attachments/capabilities",
            params={"projectId": PROJECT_ID, "threadId": THREAD_ID},
        )
        assert capability.status_code == 200, capability.text
        assert capability.json() == {
            "schemaId": "kolibri.product.attachment-capabilities",
            "schemaVersion": "1.0",
            "enabled": True,
            "projectId": PROJECT_ID,
            "threadId": THREAD_ID,
            "canonicalThreadId": THREAD_ID,
            "accept": capability.json()["accept"],
            "maxSizeBytes": USER_ATTACHMENT_MAX_BYTES,
            "maxAttachmentsPerMessage": 10,
        }
        assert "text/csv" in capability.json()["accept"]
        assert "image/svg+xml" not in capability.json()["accept"]

        attachment_id = "attachment_browsercsv000001"
        no_csrf = client.post(
            "/v1/attachments",
            headers=_upload_headers(
                None,
                attachment_id=attachment_id,
            ),
            content=CSV_BYTES,
        )
        assert no_csrf.status_code == 403
        assert no_csrf.json()["code"] == "csrf_token_required"

        uploaded = client.post(
            "/v1/attachments",
            headers=_upload_headers(
                csrf,
                attachment_id=attachment_id,
            ),
            content=CSV_BYTES,
        )
        assert uploaded.status_code == 201, uploaded.text
        attachment = uploaded.json()
        content_hash = f"sha256:{hashlib.sha256(CSV_BYTES).hexdigest()}"
        assert attachment["attachment_id"] == attachment_id
        assert attachment["project_id"] == PROJECT_ID
        assert attachment["content_hash"] == content_hash
        assert attachment["size_bytes"] == len(CSV_BYTES)
        assert attachment["content_path"] == (
            f"/api/product/v1/attachments/{attachment_id}/content"
        )
        assert uploaded.headers["location"] == attachment["content_path"]
        assert uploaded.headers["x-kolibri-content-sha256"] == content_hash
        validation = _generated_contracts().ContractBoundaryClient(
            "attachment_journey_test"
        ).validate_inbound(
            attachment,
            "kolibri.product.attachment",
        )
        assert validation.ok, validation.violations

        replay = client.post(
            "/v1/attachments",
            headers=_upload_headers(
                csrf,
                attachment_id=attachment_id,
            ),
            content=CSV_BYTES,
        )
        assert replay.status_code == 200, replay.text
        assert replay.json() == attachment

        conflict = client.post(
            "/v1/attachments",
            headers=_upload_headers(
                csrf,
                attachment_id=attachment_id,
            ),
            content=CSV_BYTES + b"changed",
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "attachment_idempotency_conflict"

        retrieved = client.get(
            attachment["content_path"].removeprefix("/api/product")
        )
        assert retrieved.status_code == 200, retrieved.text
        assert retrieved.content == CSV_BYTES
        assert retrieved.headers["content-type"].startswith("text/csv")
        assert retrieved.headers["x-kolibri-content-sha256"] == content_hash

        database = connect_database(database_path)
        try:
            row = database.execute(
                """
                SELECT storage_ref, typeof(storage_ref) AS storage_type,
                       content_hash, size_bytes
                FROM product_attachments
                WHERE tenant_id = ? AND id = ?
                """,
                (tenant_id, attachment_id),
            ).fetchone()
            assert row is not None
            assert row["storage_type"] == "text"
            assert row["content_hash"] == content_hash
            assert row["size_bytes"] == len(CSV_BYTES)
            stored_path = resolve_storage_path(settings, str(row["storage_ref"]))
            assert stored_path.read_bytes() == CSV_BYTES

            run_input = _run_input(attachment)
            accepted = accept_run(
                database,
                settings=settings,
                identity=_identity(user),
                run_input=run_input,
                prepared=PreparedChatExecution(
                    execution_plane="direct",
                    runtime_profile="auto",
                    model_id=None,
                    reasoning_effort=None,
                    service_tier=None,
                ),
            )
            assert accepted.replayed is False
            exact_replay = accept_run(
                database,
                settings=settings,
                identity=_identity(user),
                run_input=run_input,
                prepared=PreparedChatExecution(
                    execution_plane="direct",
                    runtime_profile="auto",
                    model_id=None,
                    reasoning_effort=None,
                    service_tier=None,
                ),
            )
            assert exact_replay.run_id == accepted.run_id
            assert exact_replay.replayed is True

            message = database.execute(
                """
                SELECT id, content_text, COALESCE(content_json, '') AS content_json
                FROM chat_messages
                WHERE tenant_id = ? AND thread_id = ? AND role = 'user'
                """,
                (tenant_id, THREAD_ID),
            ).fetchone()
            assert message is not None
            assert message["content_text"] == (
                "Проанализируй приложенную таблицу."
            )
            assert CSV_BYTES not in str(message["content_text"]).encode()
            assert CSV_BYTES not in str(message["content_json"]).encode()
            reference = database.execute(
                """
                SELECT attachment_id, artifact_id, artifact_version,
                       content_hash, filename, mime_type, size_bytes
                FROM chat_message_attachment_refs
                WHERE tenant_id = ? AND message_id = ?
                """,
                (tenant_id, str(message["id"])),
            ).fetchone()
            assert reference is not None
            assert reference["attachment_id"] == attachment_id
            assert reference["artifact_id"] == attachment["artifact_id"]
            assert reference["artifact_version"] == 1
            assert reference["content_hash"] == content_hash
            assert reference["size_bytes"] == len(CSV_BYTES)
            assert database.execute(
                """
                SELECT COUNT(*)
                FROM chat_message_attachment_refs
                WHERE tenant_id = ? AND message_id = ?
                """,
                (tenant_id, str(message["id"])),
            ).fetchone()[0] == 1
        finally:
            database.close()

        history = client.get(f"/v1/chat/threads/{THREAD_ID}/messages")
        assert history.status_code == 200, history.text
        content = history.json()["messages"][0]["content"]
        assert content == [
            {
                "type": "text",
                "text": "Проанализируй приложенную таблицу.",
            },
            {
                "type": "document",
                "source": {
                    "type": "url",
                    "value": attachment["content_path"],
                    "mimeType": "text/csv",
                },
                "metadata": {"filename": "данные.csv"},
            },
        ]


def test_upload_rejects_unsupported_spoofed_and_oversize_content(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "attachment-rejections.db"
    settings = _settings(database_path)
    app = create_app(settings)
    with TestClient(app) as client:
        csrf, user = _register(client)
        _seed_scope(
            database_path,
            tenant_id=str(user["tenantId"]),
            user_id=str(user["id"]),
        )

        unsupported = client.post(
            "/v1/attachments",
            headers=_upload_headers(
                csrf,
                attachment_id="attachment_unsupported0001",
                filename="active.svg",
                mime_type="image/svg+xml",
            ),
            content=b"<svg onload='alert(1)'/>",
        )
        assert unsupported.status_code == 415
        assert unsupported.json()["code"] == "attachment_unsupported"

        spoofed = client.post(
            "/v1/attachments",
            headers=_upload_headers(
                csrf,
                attachment_id="attachment_spoofedpng0001",
                filename="spoofed.png",
                mime_type="image/png",
            ),
            content=b"not a png",
        )
        assert spoofed.status_code == 415
        assert spoofed.json()["code"] == "attachment_content_mismatch"

        oversize_headers = _upload_headers(
            csrf,
            attachment_id="attachment_oversized0001",
        )
        oversize_headers["Content-Length"] = str(
            USER_ATTACHMENT_MAX_BYTES + 1
        )
        oversize = client.post(
            "/v1/attachments",
            headers=oversize_headers,
            content=b"x",
        )
        assert oversize.status_code == 413
        assert oversize.json()["code"] == "attachment_too_large"

        tamper_id = "attachment_tampercheck0001"
        original = b"integrity-check"
        tamper_upload = client.post(
            "/v1/attachments",
            headers=_upload_headers(
                csrf,
                attachment_id=tamper_id,
                filename="integrity.txt",
                mime_type="text/plain",
            ),
            content=original,
        )
        assert tamper_upload.status_code == 201, tamper_upload.text
        database = connect_database(database_path)
        try:
            storage_ref = database.execute(
                """
                SELECT storage_ref
                FROM product_attachments
                WHERE tenant_id = ? AND id = ?
                """,
                (str(user["tenantId"]), tamper_id),
            ).fetchone()[0]
        finally:
            database.close()
        storage_path = resolve_storage_path(settings, str(storage_ref))
        storage_path.write_bytes(b"X" * len(original))
        tampered = client.get(f"/v1/attachments/{tamper_id}/content")
        assert tampered.status_code == 410
        assert tampered.json()["code"] == "attachment_content_missing"

    assert USER_ATTACHMENT_MAX_BYTES < ATTACHMENT_CONTRACT_MAX_BYTES
    chunks = (
        b"x" * 64 * 1024
        for _ in range((USER_ATTACHMENT_MAX_BYTES // (64 * 1024)) + 1)
    )
    with pytest.raises(AttachmentTooLargeError):
        store_content_chunks(
            settings,
            tenant_id="tenant_stream_limit_test",
            chunks=chunks,
            max_bytes=USER_ATTACHMENT_MAX_BYTES,
        )
    temp_root = settings.attachment_storage_root / ".tmp"
    assert not temp_root.exists() or not any(temp_root.iterdir())


def test_native_bearer_and_retrieval_scope_are_enforced(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "attachment-native.db"
    settings = _settings(database_path)
    app = create_app(settings)
    with TestClient(app) as client:
        _csrf, user = _register(
            client,
            email="native-attachment@example.com",
        )
        tenant_id = str(user["tenantId"])
        user_id = str(user["id"])
        _seed_scope(
            database_path,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        access_token = _mobile_login(
            client,
            email="native-attachment@example.com",
        )
        bearer_headers = {
            **_upload_headers(
                None,
                attachment_id="attachment_nativecsv00001",
                filename="native.csv",
            ),
            "Authorization": f"Bearer {access_token}",
        }
        bearer_headers.pop("Origin")

        uploaded = client.post(
            "/v1/attachments",
            headers=bearer_headers,
            content=CSV_BYTES,
        )
        assert uploaded.status_code == 201, uploaded.text
        attachment = uploaded.json()
        native_content_path = attachment["content_path"].removeprefix(
            "/api/product"
        )
        native_read = client.get(
            native_content_path,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert native_read.status_code == 200
        assert native_read.content == CSV_BYTES

        other_user = UserSession(
            user_id="user_same_tenant_intruder01",
            tenant_id=tenant_id,
            role=UserRole.USER,
            preferred_agent_profile=AgentProfile.AUTO,
            email="intruder@example.com",
            name="Intruder",
        )
        app.dependency_overrides[require_user] = lambda: other_user
        try:
            same_tenant_other_user = client.get(native_content_path)
        finally:
            app.dependency_overrides.pop(require_user, None)
        assert same_tenant_other_user.status_code == 404
        assert (
            same_tenant_other_user.json()["code"]
            == "attachment_not_found"
        )

        other_tenant = UserSession(
            user_id="user_other_tenant_intruder01",
            tenant_id="tenant_other_attachment_scope01",
            role=UserRole.USER,
            preferred_agent_profile=AgentProfile.AUTO,
            email="other-tenant@example.com",
            name="Other tenant",
        )
        app.dependency_overrides[require_user] = lambda: other_tenant
        try:
            crossed_tenant = client.get(native_content_path)
        finally:
            app.dependency_overrides.pop(require_user, None)
        assert crossed_tenant.status_code == 404
        assert crossed_tenant.json()["code"] == "attachment_not_found"


def test_public_attachment_journey_uses_only_authenticated_http_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Release journey: create scope, upload, send, recover, and isolate."""

    main_module = importlib.import_module("app.main")
    monkeypatch.setattr(
        main_module,
        "build_agent_runtime_registry",
        lambda *_args, **_kwargs: AgentRuntimeRegistry(),
    )
    database_path = tmp_path / "attachment-public-journey.db"
    app = create_app(_settings(database_path))
    public_thread_id = "thread_attachment_public_01"

    with TestClient(app) as client:
        csrf, _user = _register(
            client,
            email="attachment-public@example.com",
        )
        bootstrap = client.post(
            "/v1/chat/ag-ui",
            headers={
                **ORIGIN,
                "X-CSRF-Token": csrf,
                "Accept": "text/event-stream",
            },
            json=_public_run_payload(
                thread_id=public_thread_id,
                run_id="run_attachment_bootstrap_01",
                message_id="message_attachment_bootstrap_01",
                content=(
                    "Создай изображение по моему описанию. "
                    "Сначала уточни стиль, формат и назначение."
                ),
            ),
        )
        assert bootstrap.status_code == 200, bootstrap.text
        assert '"type":"RUN_FINISHED"' in bootstrap.text

        threads = client.get("/v1/chat/threads")
        assert threads.status_code == 200, threads.text
        thread = next(
            item
            for item in threads.json()["threads"]
            if item["id"] == public_thread_id
        )
        project_id = thread["projectId"]
        assert isinstance(project_id, str) and project_id.startswith(
            "project_"
        )

        capability = client.get(
            "/v1/attachments/capabilities",
            params={
                "projectId": project_id,
                "threadId": public_thread_id,
            },
        )
        assert capability.status_code == 200, capability.text
        assert capability.json()["enabled"] is True

        attachment_id = "attachment_publicjourney01"
        upload = client.post(
            "/v1/attachments",
            headers=_upload_headers(
                csrf,
                attachment_id=attachment_id,
                project_id=project_id,
                thread_id=public_thread_id,
            ),
            content=CSV_BYTES,
        )
        assert upload.status_code == 201, upload.text
        attachment = upload.json()

        send = client.post(
            "/v1/chat/ag-ui",
            headers={
                **ORIGIN,
                "X-CSRF-Token": csrf,
                "Accept": "text/event-stream",
            },
            json=_public_run_payload(
                thread_id=public_thread_id,
                run_id="run_attachment_public_send_01",
                message_id="message_attachment_public_send_01",
                content=[
                    {
                        "type": "text",
                        "text": "Проанализируй приложенный файл.",
                    },
                    {
                        "type": "document",
                        "source": {
                            "type": "url",
                            "value": attachment["content_path"],
                            "mimeType": attachment["mime_type"],
                        },
                        "metadata": {
                            "filename": attachment["filename"],
                        },
                    },
                ],
            ),
        )
        assert send.status_code == 200, send.text
        # No provider is connected in this deterministic test. The run must
        # expose a real terminal error while preserving the accepted message.
        assert '"type":"RUN_ERROR"' in send.text
        assert '"type":"RUN_FINISHED"' not in send.text

        history = client.get(
            f"/v1/chat/threads/{public_thread_id}/messages"
        )
        assert history.status_code == 200, history.text
        sent_message = next(
            message
            for message in history.json()["messages"]
            if message["id"] == "message_attachment_public_send_01"
        )
        assert sent_message["content"][-1] == {
            "type": "document",
            "source": {
                "type": "url",
                "value": attachment["content_path"],
                "mimeType": "text/csv",
            },
            "metadata": {"filename": "данные.csv"},
        }
        assert CSV_BYTES.decode() not in json.dumps(
            history.json(),
            ensure_ascii=False,
        )

        native_token = _mobile_login(
            client,
            email="attachment-public@example.com",
        )
        backend_content_path = attachment["content_path"].removeprefix(
            "/api/product"
        )
        native_read = client.get(
            backend_content_path,
            headers={"Authorization": f"Bearer {native_token}"},
        )
        assert native_read.status_code == 200
        assert native_read.content == CSV_BYTES

        logged_out = client.post(
            "/v1/auth/logout",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
        )
        assert logged_out.status_code == 200
        anonymous = client.get(backend_content_path)
        assert anonymous.status_code == 401

        _register(
            client,
            email="attachment-crossed@example.com",
        )
        crossed_tenant = client.get(backend_content_path)
        assert crossed_tenant.status_code == 404
