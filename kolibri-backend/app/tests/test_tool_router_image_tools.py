"""Real-contract coverage for image tools exposed by the unified router."""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from app import image_artifacts
from app.capability_runtime import capability_by_id
from app.main import app


_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture
def browser_client():
    with TestClient(app) as client:
        bootstrap = client.post("/api/v1/shell/bootstrap")
        assert bootstrap.status_code == 200
        yield client


def _configured_codex_route(monkeypatch):
    monkeypatch.setenv("KOLIBRI_IMAGE_GENERATION_ENABLED", "true")
    monkeypatch.setattr(
        image_artifacts,
        "_codex_cli_route",
        lambda: {
            "configured": True,
            "provider": "codex_cli",
            "model": "codex-cli:account-default",
        },
    )


def test_image_generate_and_edit_flow_through_unified_router(
    monkeypatch,
    browser_client,
):
    _configured_codex_route(monkeypatch)

    async def fake_generate(request, *, run_id=None, scope_id=None):
        assert request.prompt == "Нарисуй цветок"
        assert isinstance(scope_id, str) and scope_id.startswith("anon:")
        return image_artifacts._store_image(
            _PNG_1X1,
            prompt=request.prompt,
            model="codex-cli:account-default",
            scope_id=scope_id,
        )

    async def fake_edit(request, *, run_id=None, scope_id=None):
        source, manifest = image_artifacts._source_image_bytes(
            request.source_artifact_id,
            scope_id=scope_id,
        )
        assert source == _PNG_1X1
        return image_artifacts._store_image(
            _PNG_1X1,
            prompt=request.prompt,
            model="codex-cli:account-default",
            source_artifact_id=str(manifest["id"]),
            scope_id=scope_id,
        )

    monkeypatch.setattr(image_artifacts, "generate_image", fake_generate)
    monkeypatch.setattr(image_artifacts, "edit_image", fake_edit)

    created = browser_client.post(
        "/api/v1/tools/invoke",
        json={
            "tool": "image.generate",
            "arguments": {"prompt": "Нарисуй цветок"},
        },
    )
    assert created.status_code == 200, created.text
    source = created.json()["result"]["artifact"]
    assert browser_client.get(source["download_url"]).content == _PNG_1X1

    edited = browser_client.post(
        "/api/v1/tools/invoke",
        json={
            "tool": "image.edit",
            "arguments": {
                "source_artifact_id": source["id"],
                "prompt": "Сделай фон тёплым",
            },
        },
    )
    assert edited.status_code == 200, edited.text
    revision = edited.json()["result"]["artifact"]
    assert revision["id"] != source["id"]
    assert revision["source_artifact_id"] == source["id"]
    assert browser_client.get(revision["download_url"]).content == _PNG_1X1
    assert capability_by_id("image.edit")["status"] == "available"


def test_image_tool_validation_is_structured(monkeypatch, browser_client):
    _configured_codex_route(monkeypatch)
    response = browser_client.post(
        "/api/v1/tools/invoke",
        json={"tool": "image.edit", "arguments": {"prompt": "Измени"}},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "image_request_invalid",
        "capability": "image.edit",
    }
