import base64
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import ai_provider, codex_cli_image_provider, image_artifacts
from app.main import app


_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture(autouse=True)
def reset_image_probe_state(monkeypatch):
    monkeypatch.setattr(image_artifacts, "_last_verified_success", None)
    monkeypatch.setattr(image_artifacts, "_last_verified_monotonic", None)
    monkeypatch.setattr(image_artifacts, "_last_probe_failure", None)
    monkeypatch.setattr(image_artifacts, "_last_verified_provider", None)
    monkeypatch.setattr(image_artifacts, "_last_verified_model", None)
    monkeypatch.setenv("CODEX_CLI_IMAGE_ENABLED", "false")
    monkeypatch.delenv("OPENAI_REST_IMAGE_ROUTING_ENABLED", raising=False)
    monkeypatch.delenv("KOLIBRI_CODEX_IMAGE_WORKER_URL", raising=False)


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
    capability = response.json()["capabilities"][0]
    assert capability["id"] == "image.generate"
    assert capability["status"] == "unavailable"
    assert capability["invocable"] is False
    assert capability["route"]["healthy"] is False
    assert capability["renderer"] == {"available": True, "id": "image", "status": "live"}


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
        created = client.post(
            "/api/v1/images/generations",
            json={"prompt": "Создай кинематографичный портрет султана"},
        )
        assert created.status_code == 201
        artifact = created.json()
        content = client.get(artifact["url"])
        capability = client.get("/api/v1/capabilities").json()["capabilities"][0]

    assert artifact["type"] == "image"
    assert artifact["mime_type"] == "image/png"
    assert artifact["size_bytes"] == len(_PNG_1X1)
    assert len(artifact["sha256"]) == 64
    assert "b64_json" not in artifact
    assert content.status_code == 200
    assert content.headers["content-type"] == "image/png"
    assert content.content == _PNG_1X1
    assert content.headers["etag"] == f'"{artifact["sha256"]}"'
    assert capability["status"] == "live"
    assert capability["invocable"] is True


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


def test_loopback_codex_worker_preserves_backend_sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_CLI_IMAGE_ENABLED", "false")
    monkeypatch.setenv("KOLIBRI_CODEX_IMAGE_WORKER_URL", "http://127.0.0.1:18016")
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path))

    async def upstream(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://127.0.0.1:18016/v1/images/generations"
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
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "сгенерируй цветы"}]},
            headers={"X-Forwarded-For": "image-unavailable"},
        )

    assert response.status_code == 200
    final = _sse_payloads(response)[-1]
    assert final["done"] is True
    assert final["status"] == "capability_unavailable"
    assert final["error_code"] == "capability_unavailable"
    assert final["capability"] == "image.generate"
    assert final["recoverable"] is True
    assert final["provider"] == "none"
    assert final["actions"] == []
    assert "недоступна" in final["content"]
    assert "Изображение создано" not in final["content"]
    assert not any(
        payload.get("work_summary", {}).get("stage") == "artifact_verification"
        for payload in _sse_payloads(response)
    )


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

    monkeypatch.setattr(image_artifacts, "generate_image", fake_generate)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "сгенерируй цветы"}]},
            headers={"X-Forwarded-For": "image-success"},
        )

    payloads = _sse_payloads(response)
    assert payloads[-2]["content"].startswith("Изображение создано")
    assert payloads[-1]["status"] == "ready"
    assert payloads[-1]["provider"] == "openai"
    assert payloads[-1]["model"] == "gpt-image-2"
    assert payloads[-1]["actions"] == [
        {"type": "present_image", "label": "Открыть изображение", "data": artifact}
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
        response = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "сгенерируй цветы"}]},
            headers={"X-Forwarded-For": "image-fake-metadata"},
        )

    final = _sse_payloads(response)[-1]
    assert final["done"] is True
    assert final["status"] == "failed"
    assert final["error_code"] == "image_artifact_verification_failed"
    assert final["recoverable"] is True
    assert final["actions"] == []
    assert "Изображение создано" not in final["content"]


def test_non_stream_image_unavailable_is_structured_and_never_calls_text_provider(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    async def forbidden_text_provider(*args, **kwargs):
        raise AssertionError("image intent must never reach a text provider")

    monkeypatch.setattr(ai_provider, "chat_completion", forbidden_text_provider)
    with TestClient(app) as client:
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
        image_artifacts,
        "capability_catalog",
        lambda: {
            "capabilities": [
                {"id": "image.generate", "name": "Изображение", "status": "live", "invocable": True},
                {"id": "openai.web_search", "name": "Веб-поиск", "status": "unverified", "invocable": False},
            ]
        },
    )

    prompt = ai_provider._kolibri_system_prompt()

    assert "универсальная AI-операционная система" in prompt
    assert "Никогда не представляйся" in prompt
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
    assert result["model"] == "capability-catalog-v1"
    assert result["content"].startswith("Я — Колибри")
    assert "строительн" not in result["content"].lower()
    assert "Изображение" in result["content"]
    assert stream[0]["content"] == result["content"]
    assert stream[-1]["done"] is True
    assert stream[-1]["provider"] == "kolibri_catalog"
