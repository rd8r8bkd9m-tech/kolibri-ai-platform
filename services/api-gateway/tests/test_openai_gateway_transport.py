from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient


class _StaticAsyncStream(httpx.AsyncByteStream):
    def __init__(self, payload: bytes):
        self.payload = payload

    async def __aiter__(self):
        yield self.payload



def _configured_client(tmp_path: Path, monkeypatch, handler) -> TestClient:
    data = tmp_path / "data"
    developer_key = "sk-" + "kolibri-" + "gateway-test-key"
    monkeypatch.setenv("KOLIBRI_DATA_DIR", str(data))
    monkeypatch.setenv("KOLIBRI_DB_PATH", str(data / "kolibri.db"))
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(data / "artifacts"))
    monkeypatch.setenv("KOLIBRI_SESSION_SECRET", "gateway-test-session")
    monkeypatch.setenv(
        "KOLIBRI_API_KEYS_JSON",
        json.dumps({developer_key: {"role": "developer", "name": "gateway-test"}}),
    )
    monkeypatch.setenv("OPENAI_BASE_URL", "https://provider.example")
    monkeypatch.setenv("OPENAI_API_KEY", "provider-" + "secret-value")
    monkeypatch.setenv("OPENAI_PROJECT", "server-project")
    monkeypatch.setenv("OPENAI_ORGANIZATION", "server-organization")

    from kolibri_v2.routers import openai_compat

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        openai_compat.httpx,
        "AsyncClient",
        lambda timeout=None: original_client(transport=transport, timeout=timeout),
    )
    from kolibri_v2.app import create_app

    test_client = TestClient(create_app())
    test_client.headers["Authorization"] = f"Bearer {developer_key}"
    return test_client


def test_gateway_preserves_method_query_and_body_but_uses_server_provider_scope(tmp_path, monkeypatch):
    observed: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed.update(
            method=request.method,
            url=str(request.url),
            authorization=request.headers.get("authorization"),
            project=request.headers.get("openai-project"),
            organization=request.headers.get("openai-organization"),
            idempotency=request.headers.get("idempotency-key"),
            body=request.content,
        )
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "openai-request-id": "upstream_req_1"},
            json={"object": "list", "data": [{"embedding": [0.1, 0.2]}]},
            request=request,
        )

    client = _configured_client(tmp_path, monkeypatch, handler)
    with client:
        response = client.post(
            "/v1/embeddings?encoding_format=float",
            headers={
                "Authorization": client.headers["Authorization"],
                "OpenAI-Project": "attacker-project",
                "OpenAI-Organization": "attacker-organization",
                "Idempotency-Key": "idem-1",
            },
            json={"model": "text-embedding-3-small", "input": "hello"},
        )
    assert response.status_code == 200, response.text
    assert observed["method"] == "POST"
    assert observed["url"] == "https://provider.example/v1/embeddings?encoding_format=float"
    assert observed["authorization"] == "Bearer provider-secret-value"
    assert observed["project"] == "server-project"
    assert observed["organization"] == "server-organization"
    assert observed["idempotency"] == "idem-1"
    assert json.loads(observed["body"])["input"] == "hello"
    assert response.headers["openai-request-id"] == "upstream_req_1"


def test_gateway_streams_sse_and_preserves_provider_request_id(tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream", "x-request-id": "upstream_stream_1"},
            stream=_StaticAsyncStream(
                b"event: response.output_text.delta\ndata: {\"delta\":\"ok\"}\n\ndata: [DONE]\n\n"
            ),
            request=request,
        )

    client = _configured_client(tmp_path, monkeypatch, handler)
    with client:
        with client.stream(
            "POST",
            "/v1/audio/transcriptions",
            headers={"Authorization": client.headers["Authorization"], "Accept": "text/event-stream"},
            content=b"audio-bytes",
        ) as response:
            payload = b"".join(response.iter_bytes())
    assert response.status_code == 200
    assert response.headers["openai-request-id"] == "upstream_stream_1"
    assert response.headers["x-upstream-request-id"] == "upstream_stream_1"
    assert b"response.output_text.delta" in payload
    assert payload.endswith(b"data: [DONE]\n\n")
