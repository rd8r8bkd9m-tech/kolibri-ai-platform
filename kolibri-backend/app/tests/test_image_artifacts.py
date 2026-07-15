import base64
import asyncio
import hashlib
import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app import ai_provider, capability_runtime, codex_cli_image_provider, image_artifacts
from app.main import app


_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
_PNG_1X1_EDITED = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


@pytest.fixture(autouse=True)
def reset_image_probe_state(monkeypatch, tmp_path):
    monkeypatch.setattr(image_artifacts, "_last_verified_success", None)
    monkeypatch.setattr(image_artifacts, "_last_verified_monotonic", None)
    monkeypatch.setattr(image_artifacts, "_last_probe_failure", None)
    monkeypatch.setattr(image_artifacts, "_last_verified_provider", None)
    monkeypatch.setattr(image_artifacts, "_last_verified_model", None)
    monkeypatch.setattr(image_artifacts, "_last_verified_release_id", None)
    monkeypatch.setenv("KOLIBRI_RELEASE_ID", "kolibri-image-release-a")
    monkeypatch.setenv("KOLIBRI_CAPABILITY_PROBE_TTL_SECONDS", "25200")
    monkeypatch.setenv("CODEX_CLI_IMAGE_ENABLED", "false")
    monkeypatch.delenv("OPENAI_REST_IMAGE_ROUTING_ENABLED", raising=False)
    monkeypatch.delenv("KOLIBRI_CODEX_IMAGE_WORKER_URL", raising=False)
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path / "artifacts"))


def _sse_payloads(response) -> list[dict]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_image_capability_fails_closed_without_credential(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_IMAGE_ROUTE_HEALTHY", raising=False)

    with TestClient(app) as client:
        response = client.get("/api/v1/capabilities")

    assert response.status_code == 200
    capability = next(
        item for item in response.json()["capabilities"] if item["id"] == "image.generate"
    )
    assert capability["id"] == "image.generate"
    assert capability["status"] == "unavailable"
    assert capability["invocable"] is False
    assert "routes" not in capability
    assert "selected_route_id" not in capability
    assert "policy" not in capability
    assert capability["reason"]["code"] == "route_not_configured"
    assert capability["renderer"]["registered"] is True
    assert capability["renderer"]["id"] == "image"


def test_image_capability_ignores_unverified_health_flag(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-test")
    monkeypatch.setenv("OPENAI_REST_IMAGE_ROUTING_ENABLED", "true")
    monkeypatch.setenv("OPENAI_IMAGE_ROUTE_HEALTHY", "true")
    monkeypatch.setattr(image_artifacts, "_last_verified_success", None)
    monkeypatch.setattr(image_artifacts, "_last_verified_monotonic", None)
    monkeypatch.setattr(image_artifacts, "_last_probe_failure", None)

    capability = image_artifacts.image_capability()

    assert capability["status"] == "partial"
    assert capability["invocable"] is False
    assert capability["route"]["healthy"] is False
    assert capability["source"] == {"type": "configuration"}


@pytest.mark.parametrize(
    "worker_url",
    [
        "http://127.0.0.1:18016",
        "http://127.0.0.1:18017",
        "http://localhost:19000/",
    ],
)
def test_image_route_accepts_release_scoped_loopback_worker_ports(
    monkeypatch,
    worker_url,
):
    monkeypatch.setenv("CODEX_CLI_IMAGE_ENABLED", "false")
    monkeypatch.setenv("KOLIBRI_CODEX_IMAGE_WORKER_URL", worker_url)

    route = image_artifacts._selected_image_route()

    assert route == {
        "configured": True,
        "provider": "codex_cli",
        "model": "codex-cli:account-default",
        "execution": "local_worker",
        "worker_url": worker_url.rstrip("/"),
    }


def test_p6_worker_port_is_reported_as_configured_not_unavailable(monkeypatch):
    monkeypatch.setenv("CODEX_CLI_IMAGE_ENABLED", "false")
    monkeypatch.setenv(
        "KOLIBRI_CODEX_IMAGE_WORKER_URL",
        "http://127.0.0.1:18017",
    )

    capability = image_artifacts.image_capability()

    assert capability["status"] == "partial"
    assert capability["invocable"] is False
    assert capability["route"]["configured"] is True
    assert capability["route"]["provider"] == "codex_cli"


@pytest.mark.parametrize(
    "worker_url",
    [
        "https://127.0.0.1:18017",
        "http://10.99.0.2:18017",
        "http://127.0.0.1",
        "http://127.0.0.1:0",
        "http://127.0.0.1:18017/v1",
        "http://user@127.0.0.1:18017",
        "http://127.0.0.1:18017?redirect=external",
        "http://127.0.0.1:99999",
    ],
)
def test_image_route_rejects_nonlocal_or_ambiguous_worker_urls(
    monkeypatch,
    worker_url,
):
    monkeypatch.setenv("CODEX_CLI_IMAGE_ENABLED", "false")
    monkeypatch.setenv("KOLIBRI_CODEX_IMAGE_WORKER_URL", worker_url)

    route = image_artifacts._selected_image_route()

    assert route == {
        "configured": False,
        "provider": "none",
        "model": "none",
        "execution": "none",
    }


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("сгенерируй цветы", True),
        ("Generate flowers", True),
        ("Нарисуй поле с цветами", True),
        ("Создай изображение букета", True),
        ("Сгенерируй отчёт", False),
        ("Generate code", False),
        ("Создай смету на озеленение", False),
    ],
)
def test_image_intent_routes_visual_subjects_without_hijacking_other_outputs(prompt, expected):
    assert image_artifacts.is_image_generation_request(prompt) is expected


def test_image_generation_persists_and_serves_verified_bytes(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-test")
    monkeypatch.setenv("OPENAI_REST_IMAGE_ROUTING_ENABLED", "true")
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_IMAGE_ROUTE_HEALTHY", raising=False)

    async def upstream(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/images/generations")
        payload = json.loads(request.content)
        assert payload["model"] == "gpt-image-2"
        assert "портрет султана" in payload["prompt"].lower()
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(_PNG_1X1).decode()}]})

    transport = httpx.MockTransport(upstream)
    real_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return real_client(transport=transport, timeout=kwargs.get("timeout"), follow_redirects=True)

    monkeypatch.setattr(image_artifacts.httpx, "AsyncClient", client_factory)

    with TestClient(app) as client:
        assert client.post("/api/v1/shell/bootstrap").status_code == 200
        created = client.post(
            "/api/v1/images/generations",
            json={"prompt": "Создай кинематографичный портрет султана"},
        )
        assert created.status_code == 201
        artifact = created.json()
        content = client.get(artifact["url"])
        download = client.get(artifact["download_url"])
        reopen = client.get(artifact["reopen_url"])
        history = client.get(artifact["history_url"])
        capability = next(
            item
            for item in client.get("/api/v1/capabilities").json()["capabilities"]
            if item["id"] == "image.generate"
        )

    assert artifact["type"] == "image"
    assert artifact["model"] == "kolibri"
    assert artifact["revision"] == 1
    assert artifact["mime_type"] == "image/png"
    assert artifact["size_bytes"] == len(_PNG_1X1)
    assert len(artifact["sha256"]) == 64
    assert artifact["revision_url"] == f"/api/v1/artifacts/{artifact['id']}?revision=1"
    assert artifact["revision_download_url"] == f"/api/v1/artifacts/{artifact['id']}?revision=1&download=true"
    assert artifact["reopen_url"] == f"/api/v1/artifacts/{artifact['id']}/reopen"
    assert artifact["history_url"] == f"/api/v1/artifacts/{artifact['id']}/history"
    assert "b64_json" not in artifact
    assert content.status_code == 200
    assert content.headers["content-type"] == "image/png"
    assert content.content == _PNG_1X1
    assert content.headers["etag"] == f'"{artifact["sha256"]}"'
    assert download.status_code == 200
    assert download.content == _PNG_1X1
    assert "attachment" in download.headers["content-disposition"]
    assert reopen.status_code == 200
    assert reopen.json()["artifact"]["id"] == artifact["id"]
    assert reopen.json()["artifact"]["metadata"] == {
        "prompt": artifact["prompt"],
        "width": 1,
        "height": 1,
    }
    assert reopen.json()["integrity"]["digest"] == artifact["sha256"]
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["id"] == artifact["id"]
    assert capability["status"] == "available"
    assert capability["invocable"] is True
    probe = capability_runtime.capability_invocation_probe("image.generate")
    assert probe.state.value == "succeeded"
    assert probe.provider == "openai"
    assert probe.model == "gpt-image-2"
    assert probe.evidence_id == artifact["id"]

    with TestClient(app) as other_session:
        assert other_session.post("/api/v1/shell/bootstrap").status_code == 200
        denied = other_session.get(artifact["url"])
    assert denied.status_code == 404


def test_image_generation_records_failed_invocation_when_unconfigured(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_REST_IMAGE_ROUTING_ENABLED", raising=False)
    monkeypatch.delenv("KOLIBRI_CODEX_IMAGE_WORKER_URL", raising=False)
    monkeypatch.setenv("CODEX_CLI_IMAGE_ENABLED", "false")

    with pytest.raises(image_artifacts.ImageCapabilityUnavailable):
        asyncio.run(
            image_artifacts.generate_image(
                image_artifacts.ImageGenerationRequest(prompt="сгенерируй цветы"),
            ),
        )

    probe = capability_runtime.capability_invocation_probe("image.generate")
    assert probe.state.value == "failed"
    assert probe.error_code == "image_route_not_configured"


def test_image_generation_returns_verified_artifact_when_evidence_writes_fail(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-test")
    monkeypatch.setenv("OPENAI_REST_IMAGE_ROUTING_ENABLED", "true")
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path))

    async def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(_PNG_1X1).decode()}]})

    transport = httpx.MockTransport(upstream)
    real_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return real_client(transport=transport, timeout=kwargs.get("timeout"), follow_redirects=True)

    def fail_evidence(*args, **kwargs):
        raise OSError("evidence store unavailable")

    monkeypatch.setattr(image_artifacts.httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(image_artifacts, "_write_probe_state", fail_evidence)
    monkeypatch.setattr(capability_runtime, "record_capability_invocation", fail_evidence)

    with TestClient(app) as client:
        assert client.post("/api/v1/shell/bootstrap").status_code == 200
        created = client.post(
            "/api/v1/images/generations",
            json={"prompt": "Создай изображение букета"},
        )
        assert created.status_code == 201
        artifact = created.json()
        content = client.get(artifact["url"])

    assert artifact["type"] == "image"
    assert artifact["sha256"] == hashlib.sha256(_PNG_1X1).hexdigest()
    assert content.status_code == 200
    assert content.content == _PNG_1X1


def test_image_generation_provider_error_is_not_masked_by_evidence_failure(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-test")
    monkeypatch.setenv("OPENAI_REST_IMAGE_ROUTING_ENABLED", "true")

    async def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    transport = httpx.MockTransport(upstream)
    real_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return real_client(transport=transport, timeout=kwargs.get("timeout"), follow_redirects=True)

    def fail_evidence(*args, **kwargs):
        raise OSError("evidence store unavailable")

    monkeypatch.setattr(image_artifacts.httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(image_artifacts, "_write_probe_state", fail_evidence)
    monkeypatch.setattr(capability_runtime, "record_capability_invocation", fail_evidence)

    with pytest.raises(image_artifacts.ImageGenerationFailed, match="provider did not complete"):
        asyncio.run(
            image_artifacts.generate_image(
                image_artifacts.ImageGenerationRequest(prompt="сгенерируй цветы"),
            ),
        )


def test_legacy_unscoped_image_is_quarantined_without_deleting_files(monkeypatch, tmp_path):
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path))
    artifact_id = str(uuid.uuid4())
    filename = f"{artifact_id}.png"
    root = tmp_path / "images"
    root.mkdir(parents=True)
    content_path = root / filename
    metadata_path = root / f"{artifact_id}.json"
    content_path.write_bytes(_PNG_1X1)
    metadata_path.write_text(
        json.dumps(
            {
                "id": artifact_id,
                "type": "image",
                "title": "Legacy image",
                "prompt": "legacy",
                "mime_type": "image/png",
                "size_bytes": len(_PNG_1X1),
                "sha256": hashlib.sha256(_PNG_1X1).hexdigest(),
                "model": "legacy-provider",
                "created_at": "2026-07-01T00:00:00+00:00",
                "url": f"/api/v1/artifacts/images/{artifact_id}",
                "download_url": (
                    f"/api/v1/artifacts/images/{artifact_id}?download=true"
                ),
                "_filename": filename,
                "_width": 1,
                "_height": 1,
            }
        ),
        encoding="utf-8",
    )

    with TestClient(app) as client:
        assert client.post("/api/v1/shell/bootstrap").status_code == 200
        denied = client.get(f"/api/v1/artifacts/images/{artifact_id}")

    assert denied.status_code == 404
    assert denied.json()["detail"] == "Image artifact not found"
    assert content_path.read_bytes() == _PNG_1X1
    assert metadata_path.exists()


def test_openai_api_key_can_reopen_its_image_on_canonical_api_url(monkeypatch, tmp_path):
    api_key = "image-api-owner-key"
    scope_id = f"api-key-sha256:{hashlib.sha256(api_key.encode()).hexdigest()}"
    monkeypatch.setenv("KOLIBRI_PUBLIC_API_KEY_SHA256", hashlib.sha256(api_key.encode()).hexdigest())
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path))
    artifact = image_artifacts._store_image(
        _PNG_1X1,
        prompt="сгенерируй цветы",
        model="gpt-image-2",
        scope_id=scope_id,
    )

    with TestClient(app) as client:
        reopened = client.get(
            artifact["url"],
            headers={"Authorization": f"Bearer {api_key}"},
        )
        denied = client.get(
            artifact["url"],
            headers={"Authorization": "Bearer another-owner-key"},
        )

    assert reopened.status_code == 200
    assert reopened.headers["content-type"] == "image/png"
    assert reopened.content == _PNG_1X1
    assert denied.status_code == 404


def test_image_capability_proof_is_shared_across_process_state(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_CLI_IMAGE_ENABLED", "false")
    monkeypatch.setenv("KOLIBRI_CODEX_IMAGE_WORKER_URL", "http://127.0.0.1:18016")
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path))
    now = image_artifacts.datetime.now(image_artifacts.timezone.utc).isoformat()
    image_artifacts._write_probe_state(
        verified_at=now,
        failure_at=None,
        provider="codex_cli",
        model="codex-cli:account-default",
    )
    monkeypatch.setattr(image_artifacts, "_last_verified_success", None)
    monkeypatch.setattr(image_artifacts, "_last_verified_monotonic", None)
    monkeypatch.setattr(image_artifacts, "_last_verified_provider", None)
    monkeypatch.setattr(image_artifacts, "_last_verified_model", None)

    capability = image_artifacts.image_capability()

    assert capability["status"] == "live"
    assert capability["invocable"] is True
    assert capability["route"]["verified_at"] == now


def test_image_capability_proof_does_not_transfer_to_another_release(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("CODEX_CLI_IMAGE_ENABLED", "false")
    monkeypatch.setenv("KOLIBRI_CODEX_IMAGE_WORKER_URL", "http://127.0.0.1:18016")
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path))
    now = image_artifacts.datetime.now(image_artifacts.timezone.utc).isoformat()
    image_artifacts._write_probe_state(
        verified_at=now,
        failure_at=None,
        provider="codex_cli",
        model="codex-cli:account-default",
    )

    assert image_artifacts.image_capability()["status"] == "live"

    monkeypatch.setenv("KOLIBRI_RELEASE_ID", "kolibri-image-release-b")
    capability = image_artifacts.image_capability()

    assert image_artifacts._read_probe_state() == {}
    assert capability["status"] == "partial"
    assert capability["invocable"] is False


def test_codex_cli_is_primary_image_route_and_materializes_real_bytes(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_CLI_IMAGE_ENABLED", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setattr(
        image_artifacts,
        "_codex_cli_route",
        lambda: {
            "configured": True,
            "provider": "codex_cli",
            "model": "codex-cli:account-default",
        },
    )

    async def fake_cli_image(prompt, *, size, quality, run_id=None):
        assert prompt == "сгенерируй цветы"
        assert size == "1024x1024"
        assert quality == "high"
        assert run_id is None
        return codex_cli_image_provider.CodexCLIImageResult(
            data=_PNG_1X1,
            mime_type="image/png",
            width=1,
            height=1,
            sha256=image_artifacts.hashlib.sha256(_PNG_1X1).hexdigest(),
            model="codex-cli:account-default",
        )

    monkeypatch.setattr(
        codex_cli_image_provider,
        "generate_codex_cli_image",
        fake_cli_image,
    )

    artifact = asyncio.run(
        image_artifacts.generate_image(
            image_artifacts.ImageGenerationRequest(prompt="сгенерируй цветы")
        )
    )
    identity = image_artifacts.image_execution_identity()
    capability = image_artifacts.image_capability()

    assert image_artifacts.verify_image_artifact(artifact) == artifact
    assert identity == {
        "provider": "codex_cli",
        "model": "codex-cli:account-default",
    }
    assert capability["status"] == "live"
    assert capability["invocable"] is True
    assert capability["route"]["provider"] == "codex_cli"


def test_image_edit_reads_verified_source_and_persists_new_revision(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_CLI_IMAGE_ENABLED", "true")
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setattr(
        image_artifacts,
        "_codex_cli_route",
        lambda: {
            "configured": True,
            "provider": "codex_cli",
            "model": "codex-cli:account-default",
        },
    )
    scope_id = "test:image-edit-owner"
    source = image_artifacts._store_image(
        _PNG_1X1,
        prompt="source",
        model="codex-cli:account-default",
        scope_id=scope_id,
    )

    async def fake_edit(prompt, source_image, *, size, quality, run_id=None):
        assert prompt == "Сделай фон тёплым"
        assert source_image == _PNG_1X1
        return codex_cli_image_provider.CodexCLIImageResult(
            data=_PNG_1X1_EDITED,
            mime_type="image/png",
            width=1,
            height=1,
            sha256=image_artifacts.hashlib.sha256(_PNG_1X1_EDITED).hexdigest(),
            model="codex-cli:account-default",
        )

    monkeypatch.setattr(codex_cli_image_provider, "edit_codex_cli_image", fake_edit)
    edited = asyncio.run(
        image_artifacts.edit_image(
            image_artifacts.ImageEditRequest(
                source_artifact_id=source["id"],
                prompt="Сделай фон тёплым",
            ),
            scope_id=scope_id,
        )
    )

    assert edited["id"] != source["id"]
    assert edited["source_artifact_id"] == source["id"]
    assert edited["sha256"] != source["sha256"]
    assert image_artifacts.get_artifact_store().open(edited["id"]).content == _PNG_1X1_EDITED
    assert image_artifacts.verify_image_artifact(edited) == edited
    assert capability_runtime.capability_by_id("image.edit")["status"] == "available"


def test_image_edit_rejects_unchanged_provider_bytes(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_CLI_IMAGE_ENABLED", "true")
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setattr(
        image_artifacts,
        "_codex_cli_route",
        lambda: {
            "configured": True,
            "provider": "codex_cli",
            "model": "codex-cli:account-default",
        },
    )
    scope_id = "test:image-edit-owner"
    source = image_artifacts._store_image(
        _PNG_1X1,
        prompt="source",
        model="codex-cli:account-default",
        scope_id=scope_id,
    )

    async def fake_unchanged_edit(prompt, source_image, *, size, quality, run_id=None):
        return codex_cli_image_provider.CodexCLIImageResult(
            data=source_image,
            mime_type="image/png",
            width=1,
            height=1,
            sha256=image_artifacts.hashlib.sha256(source_image).hexdigest(),
            model="codex-cli:account-default",
        )

    monkeypatch.setattr(codex_cli_image_provider, "edit_codex_cli_image", fake_unchanged_edit)

    with pytest.raises(image_artifacts.ImageGenerationFailed, match="unchanged bytes"):
        asyncio.run(
            image_artifacts.edit_image(
                image_artifacts.ImageEditRequest(
                    source_artifact_id=source["id"],
                    prompt="Сделай фон тёплым",
                ),
                scope_id=scope_id,
            )
        )

    probe = capability_runtime.capability_invocation_probe("image.edit")
    assert probe.state.value == "failed"
    assert probe.error_code == "image_edit_unchanged"


def test_loopback_codex_worker_preserves_backend_sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_CLI_IMAGE_ENABLED", "false")
    monkeypatch.setenv("KOLIBRI_CODEX_IMAGE_WORKER_URL", "http://127.0.0.1:18017")
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path))

    async def upstream(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://127.0.0.1:18017/v1/images/generations"
        payload = json.loads(request.content)
        assert payload["prompt"] == "сгенерируй цветы"
        return httpx.Response(
            200,
            json={
                "model": "codex-cli:account-default",
                "data": [{"b64_json": base64.b64encode(_PNG_1X1).decode()}],
            },
        )

    transport = httpx.MockTransport(upstream)
    real_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return real_client(transport=transport, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(image_artifacts.httpx, "AsyncClient", client_factory)
    artifact = asyncio.run(
        image_artifacts.generate_image(
            image_artifacts.ImageGenerationRequest(prompt="сгенерируй цветы")
        )
    )

    assert image_artifacts.verify_image_artifact(artifact) == artifact
    assert artifact["model"] == "codex-cli:account-default"
    assert image_artifacts.image_execution_identity()["provider"] == "codex_cli"


def test_chat_stream_never_claims_image_success_without_artifact(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_IMAGE_ROUTE_HEALTHY", raising=False)

    with TestClient(app) as client:
        assert client.post("/api/v1/shell/bootstrap").status_code == 200
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "сгенерируй цветы"}]},
            headers={"X-Forwarded-For": "image-unavailable"},
        )
        payloads = _sse_payloads(response)
        response_id = next(
            payload["response"]["id"]
            for payload in payloads
            if payload.get("type") == "response.created"
        )
        replay = client.get(
            f"/api/v1/responses/{response_id}/events?starting_after=0"
        )

    assert response.status_code == 200
    final = payloads[-1]
    assert final["done"] is True
    assert final["status"] == "capability_unavailable"
    assert final["error_code"] == "capability_unavailable"
    assert final["capability"] == "image.generate"
    assert final["recoverable"] is True
    assert final["provider"] == "kolibri"
    assert final["model"] == "kolibri"
    assert final["actions"] == []
    assert "недоступна" in final["content"]
    assert "Изображение создано" not in final["content"]
    assert not any(
        payload.get("work_summary", {}).get("stage") == "artifact_verification"
        for payload in payloads
    )
    replay_payloads = _sse_payloads(replay)
    failure_types = {
        "response.created",
        "response.output_text.delta",
        "response.failed",
    }
    assert [
        payload for payload in payloads if payload.get("type") in failure_types
    ] == [
        payload for payload in replay_payloads if payload.get("type") in failure_types
    ]
    assert [
        payload["delta"]
        for payload in replay_payloads
        if payload.get("type") == "response.output_text.delta"
    ] == [final["content"]]
    assert not any(
        payload.get("type") == "response.artifact.ready"
        for payload in replay_payloads
    )
    assert [
        payload["type"]
        for payload in replay_payloads
        if payload.get("type") in {"response.completed", "response.failed"}
    ] == ["response.failed"]


def test_chat_stream_emits_present_image_only_after_verified_artifact(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-test")
    monkeypatch.setenv("OPENAI_REST_IMAGE_ROUTING_ENABLED", "true")
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setattr(image_artifacts, "_last_verified_success", "2026-07-13T12:00:00+00:00")
    monkeypatch.setattr(image_artifacts, "_last_verified_monotonic", image_artifacts.time.monotonic())
    monkeypatch.setattr(image_artifacts, "_last_verified_provider", "openai")
    monkeypatch.setattr(image_artifacts, "_last_verified_model", "gpt-image-2")
    artifact = image_artifacts._store_image(
        _PNG_1X1,
        prompt="сгенерируй цветы",
        model="gpt-image-2",
    )

    async def fake_generate(request, **_kwargs):
        return artifact

    def fail_evidence(*args, **kwargs):
        raise OSError("evidence ledger unavailable")

    monkeypatch.setattr(image_artifacts, "generate_image", fake_generate)
    monkeypatch.setattr(capability_runtime, "record_capability_invocation", fail_evidence)

    with TestClient(app) as client:
        assert client.post("/api/v1/shell/bootstrap").status_code == 200
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "сгенерируй цветы"}]},
            headers={"X-Forwarded-For": "image-success"},
        )
        payloads = _sse_payloads(response)
        response_id = next(
            payload["response"]["id"]
            for payload in payloads
            if payload.get("type") == "response.created"
        )
        replay = client.get(
            f"/api/v1/responses/{response_id}/events?starting_after=0"
        )

    legacy_payloads = [payload for payload in payloads if not payload.get("type")]
    assert legacy_payloads[-2]["content"].startswith("Изображение создано")
    assert legacy_payloads[-1]["status"] == "ready"
    public_artifact = image_artifacts.public_image_artifact(artifact)
    assert legacy_payloads[-1]["provider"] == "kolibri"
    assert legacy_payloads[-1]["model"] == "kolibri"
    assert legacy_payloads[-1]["actions"] == [
        {"type": "present_image", "label": "Открыть изображение", "data": public_artifact}
    ]
    summaries = [
        payload["work_summary"]
        for payload in payloads
        if isinstance(payload.get("work_summary"), dict)
    ]
    assert [summary["stage"] for summary in summaries] == [
        "accepted",
        "tool_execution",
        "artifact_verification",
    ]
    verification = summaries[-1]
    assert verification["status"] == "completed"
    assert verification["artifact_type"] == "image"
    assert verification["artifact_id"] == artifact["id"]
    assert "reasoning" not in verification
    replay_payloads = _sse_payloads(replay)
    canonical_types = {
        "response.created",
        "response.output_text.delta",
        "response.artifact.ready",
        "response.completed",
    }
    live_canonical = [
        payload for payload in payloads if payload.get("type") in canonical_types
    ]
    replay_canonical = [
        payload for payload in replay_payloads if payload.get("type") in canonical_types
    ]
    assert live_canonical == replay_canonical
    assert [payload["sequence"] for payload in live_canonical] == sorted(
        payload["sequence"] for payload in live_canonical
    )
    assert [
        payload["delta"]
        for payload in replay_payloads
        if payload.get("type") == "response.output_text.delta"
    ] == ["Изображение создано и сохранено в текущем проекте."]
    artifact_ready = [
        payload
        for payload in live_canonical
        if payload.get("type") == "response.artifact.ready"
    ]
    assert len(artifact_ready) == 1
    assert artifact_ready[0]["artifact"] == public_artifact
    assert artifact_ready[0]["artifact"]["model"] == "kolibri"
    assert [
        payload["type"]
        for payload in replay_payloads
        if payload.get("type") in {"response.completed", "response.failed"}
    ] == ["response.completed"]


def test_chat_stream_rejects_action_shaped_metadata_without_bytes(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-test")
    monkeypatch.setenv("OPENAI_REST_IMAGE_ROUTING_ENABLED", "true")
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setattr(image_artifacts, "_last_verified_success", "2026-07-13T12:00:00+00:00")
    monkeypatch.setattr(image_artifacts, "_last_verified_monotonic", image_artifacts.time.monotonic())
    monkeypatch.setattr(image_artifacts, "_last_verified_provider", "openai")
    monkeypatch.setattr(image_artifacts, "_last_verified_model", "gpt-image-2")
    fake_id = "c1c4425b-b4ee-4bb9-83dc-2f78053c4348"

    async def fake_generate(request, **_kwargs):
        return {
            "id": fake_id,
            "type": "image",
            "title": "Сгенерированное изображение",
            "prompt": request.prompt,
            "mime_type": "image/png",
            "size_bytes": len(_PNG_1X1),
            "sha256": "f" * 64,
            "model": "gpt-image-2",
            "created_at": "2026-07-13T12:00:00+00:00",
            "url": f"/api/v1/artifacts/images/{fake_id}",
            "download_url": f"/api/v1/artifacts/images/{fake_id}?download=true",
        }

    monkeypatch.setattr(image_artifacts, "generate_image", fake_generate)

    with TestClient(app) as client:
        assert client.post("/api/v1/shell/bootstrap").status_code == 200
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "сгенерируй цветы"}]},
            headers={"X-Forwarded-For": "image-fake-metadata"},
        )
        payloads = _sse_payloads(response)
        response_id = next(
            payload["response"]["id"]
            for payload in payloads
            if payload.get("type") == "response.created"
        )
        replay = client.get(
            f"/api/v1/responses/{response_id}/events?starting_after=0"
        )

    final = payloads[-1]
    assert final["done"] is True
    assert final["status"] == "failed"
    assert final["error_code"] == "image_artifact_verification_failed"
    assert final["recoverable"] is True
    assert final["actions"] == []
    assert "Изображение создано" not in final["content"]
    assert not any(
        payload.get("type") == "response.artifact.ready"
        for payload in payloads
    )
    replay_payloads = _sse_payloads(replay)
    failure_types = {
        "response.created",
        "response.output_text.delta",
        "response.failed",
    }
    assert [
        payload for payload in payloads if payload.get("type") in failure_types
    ] == [
        payload for payload in replay_payloads if payload.get("type") in failure_types
    ]
    assert [
        payload["delta"]
        for payload in replay_payloads
        if payload.get("type") == "response.output_text.delta"
    ] == [final["content"]]
    assert not any(
        payload.get("type") == "response.artifact.ready"
        for payload in replay_payloads
    )
    assert [
        payload["type"]
        for payload in replay_payloads
        if payload.get("type") in {"response.completed", "response.failed"}
    ] == ["response.failed"]


def test_non_stream_image_unavailable_is_structured_and_never_calls_text_provider(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    async def forbidden_text_provider(*args, **kwargs):
        raise AssertionError("image intent must never reach a text provider")

    monkeypatch.setattr(ai_provider, "chat_completion", forbidden_text_provider)
    with TestClient(app) as client:
        assert client.post("/api/v1/shell/bootstrap").status_code == 200
        response = client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "user", "content": "сгенерируй цветы"}]},
            headers={"X-Forwarded-For": "image-non-stream-unavailable"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "capability_unavailable"
    assert payload["error_code"] == "capability_unavailable"
    assert payload["recoverable"] is True
    assert payload["capability"] == "image.generate"
    assert payload["actions"] == []


def test_internal_provider_boundary_also_blocks_image_intent_from_text_models(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        ai_provider,
        "_get_providers_for_task",
        lambda _task: (_ for _ in ()).throw(AssertionError("text routes must not be selected")),
    )

    async def execute():
        result = await ai_provider.chat_completion([{"role": "user", "content": "сгенерируй цветы"}])
        stream = [
            chunk
            async for chunk in ai_provider.chat_completion_stream(
                [{"role": "user", "content": "сгенерируй цветы"}]
            )
        ]
        return result, stream

    result, stream = asyncio.run(execute())
    assert result["status"] == "capability_unavailable"
    assert result["provider"] == "none"
    assert result["actions"] == []
    assert stream[-1]["status"] == "capability_unavailable"
    assert stream[-1]["error_code"] == "capability_unavailable"
    assert stream[-1]["actions"] == []


def test_responses_image_intent_fails_closed_without_text_provider(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    async def forbidden_text_provider(*args, **kwargs):
        raise AssertionError("image intent must never reach a text provider")

    monkeypatch.setattr(ai_provider, "chat_completion", forbidden_text_provider)
    with TestClient(app) as client:
        assert client.post("/api/v1/shell/bootstrap").status_code == 200
        response = client.post(
            "/api/v1/responses",
            json={"model": "kolibri", "input": "сгенерируй цветы"},
            headers={"X-Forwarded-For": "image-responses-unavailable"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["output"] == []
    assert payload["artifacts"] == []
    assert payload["error"] == {
        "code": "capability_unavailable",
        "recoverable": True,
        "capability": "image.generate",
    }


def test_system_prompt_keeps_kolibri_identity_and_uses_live_catalog(monkeypatch):
    monkeypatch.setattr(
        capability_runtime,
        "capability_snapshot",
        lambda: {
            "capabilities": [
                {"id": "image.generate", "name": "Изображение", "status": "available", "invocable": True},
                {"id": "openai.web_search", "name": "Веб-поиск", "status": "degraded", "invocable": False},
            ]
        },
    )

    prompt = ai_provider._kolibri_system_prompt()

    assert "универсальная AI-операционная система" in prompt
    assert "Никогда не представляйся" in prompt
    assert "Не имитируй выполнение" in prompt
    assert "не раскрывай private reasoning" in prompt
    assert "проверь capability/инструмент" in prompt
    assert "Недоступно в текущем сеансе" in prompt
    assert "без лишнего подтверждения" in prompt
    assert "Изображение" in prompt
    assert "Веб-поиск" not in prompt.split("Подтверждённые доступные возможности", 1)[-1]

    async def execute():
        result = await ai_provider.chat_completion([{"role": "user", "content": "Кто ты и что умеешь?"}])
        stream = [
            chunk
            async for chunk in ai_provider.chat_completion_stream(
                [{"role": "user", "content": "Что ты умеешь?"}]
            )
        ]
        return result, stream

    result, stream = asyncio.run(execute())

    assert result["provider"] == "kolibri_catalog"
    assert result["model"] == "kolibri.capabilities.v1"
    assert result["content"].startswith("Я — Колибри")
    assert "строительн" not in result["content"].lower()
    assert "Изображение" in result["content"]
    assert stream[0]["content"] == result["content"]
    assert stream[-1]["done"] is True
    assert stream[-1]["provider"] == "kolibri_catalog"


def test_custom_specialization_is_composed_with_kolibri_solo_prompt(monkeypatch):
    captured: dict = {}
    provider = {"id": "test", "model": "test-model"}

    monkeypatch.setattr(ai_provider, "_get_providers_for_task", lambda _task: [provider])

    async def fake_call(selected_provider, messages, **_kwargs):
        captured["provider"] = selected_provider
        captured["messages"] = messages
        return {
            "content": "Готовый результат",
            "reasoning": "",
            "actions": [],
            "status": "idle",
            "provider": "test",
            "model": "test-model",
            "speed_ms": 1,
        }

    monkeypatch.setattr(ai_provider, "_call_ai", fake_call)
    result = asyncio.run(
        ai_provider.chat_completion(
            [{"role": "user", "content": "Проверь расчёт"}],
            system="Ты — эксперт по строительным сметам.",
        )
    )

    system_prompt = captured["messages"][0]["content"]
    assert captured["provider"] is provider
    assert result["content"] == "Готовый результат"
    assert "универсальная AI-операционная система" in system_prompt
    assert "Режим автономного универсального исполнителя" in system_prompt
    assert "Ты — эксперт по строительным сметам." in system_prompt
    assert "специализация не отменяет идентичность Колибри" in system_prompt


def _assert_public_payload_has_no_image_topology(payload):
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    for forbidden in (
        "codex_cli",
        "codex-cli",
        "account-default",
        "mimo",
        "deepseek",
        "gpt-image",
    ):
        assert forbidden not in serialized

    def walk(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                if key == "provider":
                    assert nested in {"kolibri", None}
                if key == "model":
                    assert nested in {"kolibri", None}
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(payload)


def test_public_capability_catalog_strips_routes_credentials_and_provider_probe(monkeypatch):
    internal = {
        "schema_version": "kolibri.capabilities.v1",
        "status": "available",
        "as_of": "2026-07-15T00:00:00+00:00",
        "counts": {"available": 1, "degraded": 0, "unavailable": 0},
        "release_id": "p7-test",
        "probe_ttl_seconds": 25200,
        "capabilities": [{
            "id": "image.generate",
            "name": "Изображение",
            "description": "Создание изображения.",
            "kind": "media",
            "catalog_listed": True,
            "status": "available",
            "invocable": True,
            "verified_at": "2026-07-15T00:00:00+00:00",
            "reason": {"code": "live_invocation", "message": "Маршрут подтверждён."},
            "selected_route_id": "codex_cli",
            "policy": {
                "evaluated": True,
                "permitted": True,
                "decision_id": "internal-policy",
            },
            "renderer": {
                "required": True,
                "id": "image",
                "registered": True,
                "healthy": True,
                "evidence_id": "internal-renderer-evidence",
            },
            "routes": [{
                "id": "codex_cli",
                "configured": True,
                "permitted": True,
                "credential": {
                    "source": "home_codex_cli_login",
                    "ready": True,
                },
                "probe": {
                    "state": "succeeded",
                    "fresh": True,
                    "provider": "codex_cli",
                    "model": "codex-cli:account-default",
                },
            }],
        }],
    }
    monkeypatch.setattr(capability_runtime, "capability_snapshot", lambda: internal)

    with TestClient(app) as client:
        response = client.get("/api/v1/capabilities")

    assert response.status_code == 200
    body = response.json()
    capability = body["capabilities"][0]
    assert capability["status"] == "available"
    assert capability["invocable"] is True
    assert capability["permitted"] is True
    assert capability["route"] == {"healthy": True, "status": "available"}
    assert capability["renderer"] == {
        "required": True,
        "id": "image",
        "registered": True,
        "healthy": True,
    }
    assert capability["reason"]["code"] == "live_invocation"
    for forbidden_key in ("routes", "selected_route_id", "policy", "credential", "probe"):
        assert forbidden_key not in capability
    _assert_public_payload_has_no_image_topology(body)
    assert internal["capabilities"][0]["routes"][0]["probe"]["provider"] == "codex_cli"


def test_all_public_image_surfaces_use_kolibri_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-test")
    monkeypatch.setenv("OPENAI_REST_IMAGE_ROUTING_ENABLED", "true")
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path))
    api_key = "koli_test_public_image_topology"
    monkeypatch.setenv(
        "KOLIBRI_PUBLIC_API_KEY_SHA256",
        hashlib.sha256(api_key.encode()).hexdigest(),
    )
    api_headers = {"Authorization": f"Bearer {api_key}"}

    async def upstream(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(("/images/generations", "/images/edits"))
        image_bytes = (
            _PNG_1X1_EDITED
            if request.url.path.endswith("/images/edits")
            else _PNG_1X1
        )
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(image_bytes).decode()}]},
        )

    transport = httpx.MockTransport(upstream)
    real_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return real_client(
            transport=transport,
            timeout=kwargs.get("timeout"),
            follow_redirects=kwargs.get("follow_redirects", False),
        )

    monkeypatch.setattr(image_artifacts.httpx, "AsyncClient", client_factory)

    payloads = []
    with TestClient(app) as client:
        assert client.post("/api/v1/shell/bootstrap").status_code == 200

        generated = client.post(
            "/api/v1/images/generations",
            json={"prompt": "Создай изображение жёлтой канарейки"},
        )
        assert generated.status_code == 201
        generated_artifact = generated.json()
        payloads.append(generated_artifact)

        edited = client.post(
            "/api/v1/images/edits",
            json={
                "source_artifact_id": generated_artifact["id"],
                "prompt": "Сделай фон тёплым",
            },
        )
        assert edited.status_code == 201
        payloads.append(edited.json())

        chat = client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "user", "content": "Создай изображение букета"}]},
            headers={"X-Forwarded-For": "public-image-chat"},
        )
        assert chat.status_code == 200
        payloads.append(chat.json())

        chat_stream = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "Создай изображение поля цветов"}]},
            headers={"X-Forwarded-For": "public-image-chat-stream"},
        )
        assert chat_stream.status_code == 200
        payloads.extend(_sse_payloads(chat_stream))

        responses = client.post(
            "/v1/responses",
            json={"model": "kolibri", "input": "Создай изображение канарейки"},
            headers={**api_headers, "X-Forwarded-For": "public-image-responses"},
        )
        assert responses.status_code == 200
        response_payload = responses.json()
        payloads.append(response_payload)

        reopened = client.get(
            f"/v1/responses/{response_payload['id']}",
            headers=api_headers,
        )
        replay = client.get(
            f"/v1/responses/{response_payload['id']}/events",
            headers=api_headers,
        )
        assert reopened.status_code == 200
        assert replay.status_code == 200
        payloads.append(reopened.json())
        payloads.extend(_sse_payloads(replay))

        streamed_response = client.post(
            "/v1/responses",
            json={
                "model": "kolibri",
                "input": "Создай изображение цветка",
                "stream": True,
            },
            headers={**api_headers, "X-Forwarded-For": "public-image-responses-stream"},
        )
        assert streamed_response.status_code == 200
        streamed_payloads = _sse_payloads(streamed_response)
        payloads.extend(streamed_payloads)
        streamed_response_id = next(
            item["response"]["id"]
            for item in streamed_payloads
            if item.get("type") == "response.created"
        )
        streamed_replay = client.get(
            f"/v1/responses/{streamed_response_id}/events",
            headers=api_headers,
        )
        assert streamed_replay.status_code == 200
        streamed_replay_payloads = _sse_payloads(streamed_replay)
        payloads.extend(streamed_replay_payloads)
        parity_types = {
            "response.created",
            "response.output_text.delta",
            "response.artifact.ready",
            "response.completed",
        }
        live_canonical = [
            item for item in streamed_payloads if item.get("type") in parity_types
        ]
        replay_canonical = [
            item for item in streamed_replay_payloads if item.get("type") in parity_types
        ]
        assert live_canonical == replay_canonical
        assert [item["sequence"] for item in live_canonical] == sorted(
            item["sequence"] for item in live_canonical
        )

        completion = client.post(
            "/v1/chat/completions",
            json={
                "model": "kolibri",
                "messages": [{"role": "user", "content": "Создай изображение сада"}],
            },
            headers={**api_headers, "X-Forwarded-For": "public-image-completion"},
        )
        assert completion.status_code == 200
        payloads.append(completion.json())

        streamed_completion = client.post(
            "/v1/chat/completions",
            json={
                "model": "kolibri",
                "messages": [{"role": "user", "content": "Создай изображение дерева"}],
                "stream": True,
            },
            headers={**api_headers, "X-Forwarded-For": "public-image-completion-stream"},
        )
        assert streamed_completion.status_code == 200
        payloads.extend([
            json.loads(line.removeprefix("data: "))
            for line in streamed_completion.text.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"
        ])

        catalog = client.get("/api/v1/capabilities")
        assert catalog.status_code == 200
        image_capability = next(
            item
            for item in catalog.json()["capabilities"]
            if item["id"] == "image.generate"
        )
        assert image_capability["invocable"] is True
        assert image_capability["permitted"] is True
        assert image_capability["route"]["healthy"] is True
        payloads.append(image_capability)

    for payload in payloads:
        _assert_public_payload_has_no_image_topology(payload)

    image_artifacts_in_payloads = []

    def collect(value):
        if isinstance(value, dict):
            if value.get("type") == "image" and "sha256" in value:
                image_artifacts_in_payloads.append(value)
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)

    collect(payloads)
    assert image_artifacts_in_payloads
    assert all(item["model"] == "kolibri" for item in image_artifacts_in_payloads)
    probe = capability_runtime.capability_invocation_probe("image.generate")
    assert probe.provider == "openai"
    assert probe.model == "gpt-image-2"
