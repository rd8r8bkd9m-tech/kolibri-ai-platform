from __future__ import annotations

import base64
from dataclasses import replace
import hashlib
import importlib
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.agent_runtime import AgentRuntimeRegistry
from app.attachment_store import resolve_storage_path
from app.config import Settings
from app.image_generation import (
    IMAGE_GENERATION_CLARIFICATION,
    ImageGenerationProviderDescriptor,
    ImageGenerationRequest,
    ImageGenerationResult,
)
from app.main import create_app
from app.provider_execution import _generated_contracts


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"
THREAD_ID = "thread_image_artifact_journey_01"
QUICK_ACTION_PROMPT = (
    "Создай изображение по моему описанию. "
    "Сначала уточни стиль, формат и назначение."
)
IMAGE_PROMPT = (
    "Ночной футуристический город под дождём, кинематографичный стиль, "
    "широкий формат для обложки проекта."
)
EXPLICIT_IMAGE_PROMPT = (
    "Сгенерируй изображение деревянного дома на рассвете, "
    "реалистичный архитектурный рендер для презентации."
)
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0l"
    "EQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
PNG_HASH = f"sha256:{hashlib.sha256(PNG_BYTES).hexdigest()}"


class DeterministicImageProvider:
    def __init__(self, *, content: bytes = PNG_BYTES) -> None:
        self.content = content
        self.calls: list[ImageGenerationRequest] = []

    @property
    def descriptor(self) -> ImageGenerationProviderDescriptor:
        return ImageGenerationProviderDescriptor(
            provider_id="image.fixture",
            provider_version="2026.07",
            display_name="Детерминированный тестовый провайдер",
        )

    def generate(
        self,
        request: ImageGenerationRequest,
        *,
        cancellation_signal: threading.Event | None = None,
    ) -> ImageGenerationResult:
        assert cancellation_signal is not None
        assert not cancellation_signal.is_set()
        self.calls.append(request)
        return ImageGenerationResult(
            content=self.content,
            media_type="image/png",
            execution_id="imageexec_fixture000001",
            revised_prompt=(
                "Ночной футуристический город под дождём, cinematic, 16:9."
            ),
        )


def _settings(database_path: Path) -> Settings:
    return replace(
        Settings.for_testing(
            database_url=database_path,
            bootstrap_owner_email=None,
        ),
        direct_model_runtime_enabled=True,
        product_run_poll_seconds=0.05,
        product_run_idle_seconds=0.05,
    )


def _register(
    client: TestClient,
    *,
    email: str,
) -> tuple[str, str, str]:
    response = client.post(
        "/v1/auth/register",
        headers=ORIGIN,
        json={
            "email": email,
            "name": email.split("@", 1)[0],
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    csrf = client.cookies.get("kolibri_v3_csrf")
    assert isinstance(csrf, str) and csrf
    user = response.json()["user"]
    return csrf, user["tenantId"], user["id"]


def _login(client: TestClient, *, email: str) -> str:
    response = client.post(
        "/v1/auth/login",
        headers=ORIGIN,
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    csrf = client.cookies.get("kolibri_v3_csrf")
    assert isinstance(csrf, str) and csrf
    return csrf


def _run_payload(
    *,
    run_id: str,
    message_id: str,
    prompt: str,
) -> dict[str, object]:
    return {
        "threadId": THREAD_ID,
        "runId": run_id,
        "state": None,
        "messages": [
            {
                "id": message_id,
                "role": "user",
                "content": prompt,
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


def _run(
    client: TestClient,
    *,
    csrf: str,
    run_id: str,
    message_id: str,
    prompt: str,
) -> tuple[str, list[dict[str, Any]]]:
    response = client.post(
        "/v1/chat/ag-ui",
        headers={
            **ORIGIN,
            "X-CSRF-Token": csrf,
            "Accept": "text/event-stream",
        },
        json=_run_payload(
            run_id=run_id,
            message_id=message_id,
            prompt=prompt,
        ),
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    events: list[dict[str, Any]] = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            value = json.loads(line.removeprefix("data: "))
            assert isinstance(value, dict)
            events.append(value)
    return response.headers["x-kolibri-run-id"], events


def _empty_runtime_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_module = importlib.import_module("app.main")
    monkeypatch.setattr(
        main_module,
        "build_agent_runtime_registry",
        lambda *_args, **_kwargs: AgentRuntimeRegistry(),
    )


def test_authenticated_image_journey_persists_cas_artifact_and_isolates_tenant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _empty_runtime_registry(monkeypatch)
    database_path = tmp_path / "image-artifact.db"
    settings = _settings(database_path)
    provider = DeterministicImageProvider()
    app = create_app(settings, image_generation_provider=provider)

    with TestClient(app) as client:
        csrf, tenant_id, user_id = _register(
            client,
            email="image-owner@example.com",
        )
        _, clarification_events = _run(
            client,
            csrf=csrf,
            run_id="run_image_clarification_01",
            message_id="message_image_clarification_01",
            prompt=QUICK_ACTION_PROMPT,
        )
        assert provider.calls == []
        assert [event["type"] for event in clarification_events] == [
            "RUN_STARTED",
            "TEXT_MESSAGE_START",
            "TEXT_MESSAGE_CONTENT",
            "TEXT_MESSAGE_END",
            "RUN_FINISHED",
        ]
        assert (
            clarification_events[2]["delta"]
            == IMAGE_GENERATION_CLARIFICATION
        )

        durable_run_id, events = _run(
            client,
            csrf=csrf,
            run_id="run_image_generation_01",
            message_id="message_image_generation_01",
            prompt=IMAGE_PROMPT,
        )
        assert [event["type"] for event in events] == [
            "RUN_STARTED",
            "TOOL_CALL_START",
            "TOOL_CALL_ARGS",
            "TOOL_CALL_END",
            "TOOL_CALL_RESULT",
            "RUN_FINISHED",
        ]
        assert events[1]["toolCallName"] == "generate_image"
        assert json.loads(events[2]["delta"]) == {"prompt": IMAGE_PROMPT}
        result = json.loads(events[4]["content"])
        assert result == {
            "$type": "GeneratedImage",
            "artifactId": result["artifactId"],
            "artifactVersion": 1,
            "attachmentId": result["attachmentId"],
            "contentHash": PNG_HASH,
            "contentPath": (
                f"/api/product/v1/attachments/"
                f"{result['attachmentId']}/content"
            ),
            "filename": result["filename"],
            "mimeType": "image/png",
            "providerLabel": "Детерминированный тестовый провайдер",
            "revisedPrompt": (
                "Ночной футуристический город под дождём, cinematic, 16:9."
            ),
            "schemaId": "kolibri.product.attachment",
            "schemaVersion": "1.0",
            "sizeBytes": len(PNG_BYTES),
            "status": "available",
        }
        assert events[-1]["outcome"] == {"type": "success"}
        assert len(provider.calls) == 1
        provider_request = provider.calls[0]
        assert provider_request.tenant_id == tenant_id
        assert provider_request.prompt == IMAGE_PROMPT
        assert provider_request.idempotency_key.endswith(durable_run_id)

        content = client.get(
            f"/v1/attachments/{result['attachmentId']}/content"
        )
        assert content.status_code == 200, content.text
        assert content.content == PNG_BYTES
        assert content.headers["content-type"].startswith("image/png")
        assert content.headers["x-kolibri-content-sha256"] == PNG_HASH
        assert content.headers["etag"] == (
            f'"{PNG_HASH.removeprefix("sha256:")}"'
        )

        artifact = client.get(
            (
                f"/v1/artifacts/{result['artifactId']}/versions/"
                f"{result['artifactVersion']}"
            )
        )
        assert artifact.status_code == 200, artifact.text
        manifest = artifact.json()
        validation = _generated_contracts().ContractBoundaryClient(
            "image_artifact_test"
        ).validate_inbound(manifest, "kolibri.artifact")
        assert validation.ok, validation.violations
        assert manifest["tenant_id"].startswith("tenant_")
        assert manifest["artifact_id"] == result["artifactId"]
        assert manifest["artifact_type"] == "image.generated"
        assert manifest["content"] == {
            "content_hash": PNG_HASH,
            "filename": result["filename"],
            "media_type": "image/png",
            "size_bytes": len(PNG_BYTES),
            "storage_ref": manifest["content"]["storage_ref"],
        }
        assert manifest["generator"] == {
            "execution_ref": "imageexec_fixture000001",
            "generator_id": "image.fixture",
            "generator_version": "2026.07",
        }

        durable_messages = client.get(
            f"/v1/chat/threads/{THREAD_ID}/messages"
        )
        assert durable_messages.status_code == 200, durable_messages.text
        messages = durable_messages.json()["messages"]
        stored_tool = messages[-1]["content"][0]
        assert stored_tool["toolName"] == "generate_image"
        assert stored_tool["result"] == result
        serialized_chat = json.dumps(messages, ensure_ascii=False)
        assert base64.b64encode(PNG_BYTES).decode("ascii") not in serialized_chat
        assert "data:image/" not in serialized_chat

        database = sqlite3.connect(database_path)
        database.row_factory = sqlite3.Row
        try:
            attachment_row = database.execute(
                """
                SELECT *
                FROM product_attachments
                WHERE tenant_id = ? AND id = ?
                """,
                (tenant_id, result["attachmentId"]),
            ).fetchone()
            artifact_row = database.execute(
                """
                SELECT *
                FROM artifact_versions
                WHERE tenant_id = ? AND artifact_id = ?
                """,
                (tenant_id, result["artifactId"]),
            ).fetchone()
            assistant_row = database.execute(
                """
                SELECT content_json
                FROM chat_messages
                WHERE tenant_id = ? AND run_id = ? AND role = 'assistant'
                """,
                (tenant_id, durable_run_id),
            ).fetchone()
            attachment_columns = {
                str(row["name"]): str(row["type"])
                for row in database.execute(
                    "PRAGMA table_info(product_attachments)"
                ).fetchall()
            }
            artifact_columns = {
                str(row["name"]): str(row["type"])
                for row in database.execute(
                    "PRAGMA table_info(artifact_versions)"
                ).fetchall()
            }
        finally:
            database.close()

        assert attachment_row is not None
        assert artifact_row is not None
        assert assistant_row is not None
        assert attachment_row["user_id"] == user_id
        assert attachment_row["content_hash"] == PNG_HASH
        assert artifact_row["content_hash"] == PNG_HASH
        assert artifact_row["storage_ref"] == attachment_row["storage_ref"]
        assert all(value.upper() != "BLOB" for value in attachment_columns.values())
        assert all(value.upper() != "BLOB" for value in artifact_columns.values())
        assert (
            base64.b64encode(PNG_BYTES).decode("ascii")
            not in str(assistant_row["content_json"])
        )
        storage_path = resolve_storage_path(
            settings,
            str(attachment_row["storage_ref"]),
        )
        assert storage_path.read_bytes() == PNG_BYTES

    # The bytes and manifest survive a complete application lifespan restart.
    with TestClient(app) as client:
        csrf = _login(client, email="image-owner@example.com")
        recovered = client.get(
            f"/v1/attachments/{result['attachmentId']}/content"
        )
        assert recovered.status_code == 200
        assert recovered.content == PNG_BYTES

        logout = client.post(
            "/v1/auth/logout",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
        )
        assert logout.status_code == 200
        _register(client, email="other-image-tenant@example.com")
        crossed_content = client.get(
            f"/v1/attachments/{result['attachmentId']}/content"
        )
        assert crossed_content.status_code == 404
        crossed_artifact = client.get(
            (
                f"/v1/artifacts/{result['artifactId']}/versions/"
                f"{result['artifactVersion']}"
            )
        )
        assert crossed_artifact.status_code == 404
        crossed_thread = client.get(
            f"/v1/chat/threads/{THREAD_ID}/messages"
        )
        assert crossed_thread.status_code == 404


@pytest.mark.parametrize(
    ("provider", "expected_code"),
    [
        (None, "image_generation_unavailable"),
        (
            DeterministicImageProvider(content=b"not-an-image"),
            "image_generation_invalid",
        ),
    ],
)
def test_image_generation_fails_closed_without_persisting_fake_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider: DeterministicImageProvider | None,
    expected_code: str,
) -> None:
    _empty_runtime_registry(monkeypatch)
    database_path = tmp_path / f"{expected_code}.db"
    settings = _settings(database_path)
    app = create_app(settings, image_generation_provider=provider)

    with TestClient(app) as client:
        csrf, tenant_id, _ = _register(
            client,
            email=f"{expected_code}@example.com",
        )
        durable_run_id, events = _run(
            client,
            csrf=csrf,
            run_id=f"run_{expected_code}_01",
            message_id=f"message_{expected_code}_01",
            prompt=EXPLICIT_IMAGE_PROMPT,
        )
        assert [event["type"] for event in events] == [
            "RUN_STARTED",
            "RUN_ERROR",
        ]
        assert events[-1]["code"] == expected_code
        assert all(event["type"] != "RUN_FINISHED" for event in events)

        database = sqlite3.connect(database_path)
        database.row_factory = sqlite3.Row
        try:
            run = database.execute(
                """
                SELECT status, outcome, error_code, assistant_message_id
                FROM chat_runs
                WHERE tenant_id = ? AND id = ?
                """,
                (tenant_id, durable_run_id),
            ).fetchone()
            attachment_count = database.execute(
                "SELECT COUNT(*) FROM product_attachments"
            ).fetchone()[0]
            artifact_count = database.execute(
                "SELECT COUNT(*) FROM artifact_versions"
            ).fetchone()[0]
        finally:
            database.close()
        assert run is not None
        assert dict(run) == {
            "status": "failed",
            "outcome": "failure",
            "error_code": expected_code,
            "assistant_message_id": None,
        }
        assert attachment_count == 0
        assert artifact_count == 0


def test_home_plane_rejects_image_request_before_accepting_a_fake_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _empty_runtime_registry(monkeypatch)
    database_path = tmp_path / "home-image-unavailable.db"
    settings = replace(
        _settings(database_path),
        direct_model_runtime_enabled=False,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        csrf, _, _ = _register(
            client,
            email="home-image-unavailable@example.com",
        )
        response = client.post(
            "/v1/chat/ag-ui",
            headers={
                **ORIGIN,
                "X-CSRF-Token": csrf,
                "Accept": "text/event-stream",
            },
            json=_run_payload(
                run_id="run_home_image_unavailable_01",
                message_id="message_home_image_unavailable_01",
                prompt=QUICK_ACTION_PROMPT,
            ),
        )
        assert response.status_code == 503
        assert response.json() == {
            "code": "image_generation_unavailable",
            "message": (
                "Генерация изображений не подключена к текущему "
                "контуру выполнения."
            ),
        }

        database = sqlite3.connect(database_path)
        try:
            assert database.execute(
                "SELECT COUNT(*) FROM chat_runs"
            ).fetchone()[0] == 0
            assert database.execute(
                "SELECT COUNT(*) FROM product_attachments"
            ).fetchone()[0] == 0
            assert database.execute(
                "SELECT COUNT(*) FROM artifact_versions"
            ).fetchone()[0] == 0
        finally:
            database.close()
