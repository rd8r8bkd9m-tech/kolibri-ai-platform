import base64
import hashlib

from fastapi.testclient import TestClient

from app import codex_cli_image_provider
from app.codex_image_worker import app


_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_worker_returns_only_verified_bytes(monkeypatch):
    async def fake_generate(prompt, *, size, quality, run_id=None):
        assert prompt == "Полевые цветы"
        return codex_cli_image_provider.CodexCLIImageResult(
            data=_PNG_1X1,
            mime_type="image/png",
            width=1,
            height=1,
            sha256=hashlib.sha256(_PNG_1X1).hexdigest(),
            model="codex-cli:account-default",
        )

    monkeypatch.setattr("app.codex_image_worker.generate_codex_cli_image", fake_generate)
    with TestClient(app) as client:
        response = client.post(
            "/v1/images/generations",
            json={"prompt": "Полевые цветы", "size": "1024x1024", "quality": "high"},
        )

    assert response.status_code == 200
    assert base64.b64decode(response.json()["data"][0]["b64_json"]) == _PNG_1X1
    assert response.json()["model"] == "codex-cli:account-default"


def test_worker_edit_decodes_source_and_returns_only_verified_bytes(monkeypatch):
    async def fake_edit(prompt, source, *, size, quality, run_id=None):
        assert prompt == "Сделай фон тёплым"
        assert source == _PNG_1X1
        assert run_id == "edit-1"
        return codex_cli_image_provider.CodexCLIImageResult(
            data=_PNG_1X1,
            mime_type="image/png",
            width=1,
            height=1,
            sha256=hashlib.sha256(_PNG_1X1).hexdigest(),
            model="codex-cli:account-default",
        )

    monkeypatch.setattr("app.codex_image_worker.edit_codex_cli_image", fake_edit)
    with TestClient(app) as client:
        response = client.post(
            "/v1/images/edits",
            json={
                "prompt": "Сделай фон тёплым",
                "source_b64": base64.b64encode(_PNG_1X1).decode("ascii"),
                "size": "1024x1024",
                "quality": "high",
                "run_id": "edit-1",
            },
        )

    assert response.status_code == 200
    assert base64.b64decode(response.json()["data"][0]["b64_json"]) == _PNG_1X1
