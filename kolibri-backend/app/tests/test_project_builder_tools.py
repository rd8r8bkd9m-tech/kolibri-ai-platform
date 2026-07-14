"""E2E contracts for provider-backed site/application artifacts."""

from __future__ import annotations

import hashlib
import json
import zipfile
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app import ai_provider, project_builder, tool_router
from app.artifact_store import get_artifact_store
from app.capability_runtime import capability_by_id
from app.main import app


@pytest.fixture(autouse=True)
def isolated_project_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("KOLIBRI_CAPABILITY_PROBE_FILE", str(tmp_path / "capability-probes.json"))
    monkeypatch.delenv("KOLIBRI_DISABLED_CAPABILITIES", raising=False)

    def configured_provider_route(provider: dict):
        provider_id = str(provider.get("id") or "provider")
        configured = provider_id == "codex_cli"
        return {
            "id": provider_id,
            "model": "provider-test-model" if configured else str(provider.get("model") or ""),
            "configured": configured,
            "routable": configured,
            "status": "unverified" if configured else "unavailable",
            "verified_at": None,
            "failure_kind": None,
            "credential_source": "test-provider-boundary" if configured else "none",
        }

    monkeypatch.setattr(ai_provider, "provider_route_snapshot", configured_provider_route)


@pytest.fixture
def browser_client():
    with TestClient(app) as client:
        bootstrap = client.post("/api/v1/shell/bootstrap")
        assert bootstrap.status_code == 200
        yield client


def _provider_payload(title: str = "Проверенный проект") -> str:
    return json.dumps(
        {
            "title": title,
            "files": [
                {
                    "path": "index.html",
                    "content": (
                        "<!doctype html><html><head><link rel=\"stylesheet\" href=\"styles.css\">"
                        "</head><body><main id=\"app\">Kolibri proof</main>"
                        "<script src=\"app.js\"></script></body></html>"
                    ),
                },
                {"path": "styles.css", "content": "body{font:16px sans-serif}"},
                {"path": "app.js", "content": "document.body.dataset.ready='true';"},
            ],
        },
        ensure_ascii=False,
    )


@pytest.mark.parametrize("capability_id", ["site.create", "app.create"])
def test_project_e2e_provider_zip_cas_download_reopen_and_preview(
    monkeypatch,
    browser_client,
    capability_id,
):
    calls: list[tuple[str, str]] = []

    async def provider_transport_boundary(capability: str, prompt: str):
        calls.append((capability, prompt))
        return {
            "content": _provider_payload(),
            "provider": "verified-provider-boundary",
            "model": "project-model-v1",
            "status": "ready",
        }

    monkeypatch.setattr(project_builder, "invoke_project_provider", provider_transport_boundary)
    before = capability_by_id(capability_id)
    assert before["status"] == "degraded"
    assert before["invocable"] is False

    response = browser_client.post(
        "/api/v1/tools/invoke",
        json={"tool": capability_id, "arguments": {"prompt": "Создай рабочий проект"}},
    )

    assert response.status_code == 200, response.text
    assert calls == [(capability_id, "Создай рабочий проект")]
    result = response.json()["result"]
    artifact = result["artifact"]
    assert artifact["mime_type"] == "application/zip"
    assert artifact["type"] == ("site.bundle" if capability_id == "site.create" else "app.bundle")
    assert result["provider"] == "verified-provider-boundary"
    assert result["model"] == "project-model-v1"

    downloaded = browser_client.get(artifact["download_url"])
    reopened = browser_client.get(artifact["reopen_url"])
    history = browser_client.get(artifact["history_url"])
    preview = browser_client.get(result["preview_url"])
    stylesheet = browser_client.get(result["preview_url"].replace("index.html", "styles.css"))
    script = browser_client.get(result["preview_url"].replace("index.html", "app.js"))

    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b"PK\x03\x04")
    assert hashlib.sha256(downloaded.content).hexdigest() == artifact["sha256"]
    assert artifact["size_bytes"] == len(downloaded.content)
    with zipfile.ZipFile(BytesIO(downloaded.content)) as archive:
        assert archive.namelist() == [
            "kolibri-project.json",
            "app.js",
            "index.html",
            "styles.css",
        ]
        assert b"Kolibri proof" in archive.read("index.html")
    assert reopened.status_code == 200
    assert reopened.json()["integrity"]["digest"] == artifact["sha256"]
    assert reopened.json()["preview_url"].startswith(
        f"/api/v1/previews/{artifact['id']}/s/"
    )
    assert browser_client.get(reopened.json()["preview_url"]).status_code == 200
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["sha256"] == artifact["sha256"]
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("text/html")
    assert "sandbox allow-scripts" in preview.headers["content-security-policy"]
    assert "connect-src 'none'" in preview.headers["content-security-policy"]
    assert preview.headers["cross-origin-resource-policy"] == "cross-origin"
    assert preview.headers["cache-control"] == "private, no-store"
    assert b"Kolibri proof" in preview.content
    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert stylesheet.headers["cross-origin-resource-policy"] == "cross-origin"
    assert script.status_code == 200
    assert script.headers["content-type"].startswith("text/javascript")
    assert script.headers["cross-origin-resource-policy"] == "cross-origin"
    assert capability_by_id(capability_id)["status"] == "available"
    assert capability_by_id(capability_id)["invocable"] is True

    # ZIP construction is canonical for identical validated project content.
    payload = project_builder.parse_project_payload(_provider_payload())
    assert project_builder.deterministic_project_zip(payload, capability_id) == downloaded.content


def test_preview_is_project_scope_enforced(monkeypatch, browser_client):
    async def provider_transport_boundary(_capability: str, _prompt: str):
        return {
            "content": _provider_payload("Tenant scoped site"),
            "provider": "verified-provider-boundary",
            "model": "project-model-v1",
        }

    monkeypatch.setattr(project_builder, "invoke_project_provider", provider_transport_boundary)
    created = browser_client.post(
        "/api/v1/tools/invoke",
        json={"tool": "site.create", "arguments": {"prompt": "Создай сайт"}},
    )
    assert created.status_code == 200
    preview_url = created.json()["result"]["preview_url"]
    parts = preview_url.split("/")
    artifact_id = parts[4]
    assert parts[5] == "s"
    assert parts[-1] == "index.html"

    with TestClient(app) as other_client:
        assert other_client.post("/api/v1/shell/bootstrap").status_code == 200
        denied = other_client.get(f"/api/v1/previews/{artifact_id}/index.html")
    assert denied.status_code == 404
    assert denied.json()["detail"]["code"] == "preview_not_found"

    token = parts[6]
    tampered = f"{token[:-1]}{'A' if token[-1] != 'A' else 'B'}"
    tampered_response = browser_client.get(
        f"/api/v1/previews/{artifact_id}/s/{tampered}/index.html"
    )
    assert tampered_response.status_code == 404

    manifest = get_artifact_store().get(artifact_id)
    expired = tool_router._preview_token(
        artifact_id,
        manifest["metadata"]["scope_key"],
        expires_at=1,
    )
    expired_response = browser_client.get(
        f"/api/v1/previews/{artifact_id}/s/{expired}/index.html"
    )
    assert expired_response.status_code == 404

    other_artifact = browser_client.post(
        "/api/v1/tools/invoke",
        json={"tool": "site.create", "arguments": {"prompt": "Создай другой сайт"}},
    ).json()["result"]["artifact"]["id"]
    cross_project = browser_client.get(
        f"/api/v1/previews/{other_artifact}/s/{token}/index.html"
    )
    assert cross_project.status_code == 404


@pytest.mark.parametrize(
    ("provider_output", "reason_code"),
    [
        ("Готово. Вот ваш сайт.", "provider_project_output_not_json"),
        ("```json\n{}\n```", "provider_project_output_not_json"),
        (
            json.dumps(
                {
                    "title": "Traversal",
                    "files": [
                        {"path": "index.html", "content": "<h1>safe</h1>"},
                        {"path": "../secrets.txt", "content": "steal"},
                    ],
                }
            ),
            "provider_project_path_invalid",
        ),
        (
            json.dumps(
                {
                    "title": "Server executable",
                    "files": [
                        {"path": "index.html", "content": "<h1>safe</h1>"},
                        {"path": "run.py", "content": "print('unsafe')"},
                    ],
                }
            ),
            "provider_project_file_type_forbidden",
        ),
    ],
)
def test_provider_prose_and_unsafe_projects_are_rejected_without_artifact(
    monkeypatch,
    browser_client,
    provider_output,
    reason_code,
):
    async def provider_transport_boundary(_capability: str, _prompt: str):
        return {
            "content": provider_output,
            "provider": "provider-boundary",
            "model": "project-model-v1",
        }

    monkeypatch.setattr(project_builder, "invoke_project_provider", provider_transport_boundary)
    response = browser_client.post(
        "/api/v1/tools/invoke",
        json={"tool": "site.create", "arguments": {"prompt": "Создай сайт"}},
    )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == reason_code
    assert get_artifact_store().list() == []
    assert capability_by_id("site.create")["status"] == "unavailable"


def test_project_parser_requires_exact_schema_and_index():
    with pytest.raises(project_builder.ProjectBuildError) as extra:
        project_builder.parse_project_payload(
            json.dumps({"title": "x", "files": [], "success": True})
        )
    assert extra.value.code == "provider_project_schema_invalid"

    with pytest.raises(project_builder.ProjectBuildError) as missing:
        project_builder.parse_project_payload(
            json.dumps(
                {
                    "title": "x",
                    "files": [{"path": "main.js", "content": "console.log(1)"}],
                }
            )
        )
    assert missing.value.code == "provider_project_index_missing"
