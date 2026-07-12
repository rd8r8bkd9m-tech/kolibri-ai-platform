from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from kolibri_edge import (  # noqa: E402
    CoreClient,
    CoreError,
    EdgeRuntimeSettings,
    HttpCoreClient,
    PublicPrincipal,
    RuntimeConfigurationError,
    create_runtime_app,
)


ORIGIN = "https://kolibriai.ru"
CORE_URL = "http://127.0.0.1:9202"
CREDENTIAL = "session_credential_abcdefghijklmnopqrstuvwxyz"
SESSION_ID = "sess_1234567890abcdef"
PROJECT_ID = "project_ephemeral_1234567890abcdef"
RESPONSE_ID = "resp_1234567890abcdef"
REQUEST_SHA256 = "a" * 64


def session_payload() -> dict[str, Any]:
    return {
        "id": SESSION_ID,
        "origin": ORIGIN,
        "expires_at": int(time.time()) + 3600,
        "current_project_id": PROJECT_ID,
    }


def response_payload(status: str = "queued") -> dict[str, Any]:
    return {
        "id": RESPONSE_ID,
        "object": "response",
        "model": "kolibri",
        "status": status,
        "created_at": 1,
        "project_id": PROJECT_ID,
        "output": [
            {
                "type": "message",
                "content": "safe",
                "provider_token": "must-not-leak",
                "private_reasoning": "must-not-leak",
            }
        ],
        "output_text": "safe",
        "metadata": {
            "visible": True,
            "technical": {"stderr": "must-not-leak"},
        },
        "provider": "must-not-leak",
        "analysis": "must-not-leak",
    }


def run(coroutine):
    return asyncio.run(coroutine)


def test_http_core_maps_every_core_client_method_and_contains_credential() -> None:
    requests: list[tuple[str, dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append((request.url.path, payload))
        if request.url.path == "/internal/v1/public-sessions":
            return httpx.Response(
                200,
                json={"session": session_payload(), "credential": CREDENTIAL},
            )
        if request.url.path == "/internal/v1/public-sessions/resolve":
            return httpx.Response(200, json=session_payload())
        if request.url.path == "/internal/v1/responses":
            return httpx.Response(201, json=response_payload())
        if request.url.path == "/internal/v1/responses/get":
            return httpx.Response(200, json=response_payload())
        if request.url.path == "/internal/v1/responses/events":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "response_id": RESPONSE_ID,
                    "data": [
                        {
                            "sequence": payload["after"] + 1,
                            "event_type": "response.work_summary.updated",
                            "payload": {
                                "id": RESPONSE_ID,
                                "summary": {
                                    "stage": "Проверяю",
                                    "credential": "must-not-leak",
                                },
                                "provider": "must-not-leak",
                                "analysis": "must-not-leak",
                            },
                        }
                    ],
                },
            )
        if request.url.path == "/internal/v1/responses/cancel":
            return httpx.Response(200, json=response_payload("cancelled"))
        raise AssertionError(f"unexpected path {request.url.path}")

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url=CORE_URL,
            transport=httpx.MockTransport(handler),
            trust_env=False,
        ) as client:
            core = HttpCoreClient(client)
            assert isinstance(core, CoreClient)
            issue = await core.create_public_session(ORIGIN)
            assert issue.credential == CREDENTIAL
            session = await core.resolve_public_session(CREDENTIAL)
            assert session is not None and session.id == SESSION_ID
            principal = PublicPrincipal(session_id=SESSION_ID, origin=ORIGIN)
            created = await core.create_response(
                principal,
                {"model": "kolibri", "input": "Привет"},
                idempotency_key="request-create-0001",
                request_sha256=REQUEST_SHA256,
            )
            fetched = await core.get_response(principal, RESPONSE_ID)
            events = await core.list_response_events(
                principal,
                RESPONSE_ID,
                after=0,
                limit=100,
            )
            waited = await core.wait_response_events(
                principal,
                RESPONSE_ID,
                after=1,
                timeout_seconds=2.5,
            )
            cancelled = await core.cancel_response(
                principal,
                RESPONSE_ID,
                idempotency_key="request-cancel-0001",
                request_sha256=REQUEST_SHA256,
            )

            assert fetched is not None and cancelled is not None
            assert cancelled["status"] == "cancelled"
            for value in [created, fetched, events[0].payload, waited[0].payload]:
                serialized = json.dumps(value, ensure_ascii=False)
                assert "must-not-leak" not in serialized
                assert "provider" not in serialized
                assert "private_reasoning" not in serialized

    run(scenario())

    assert all(path.startswith("/internal/v1/") for path, _ in requests)
    credential_requests = [
        path
        for path, payload in requests
        if CREDENTIAL in json.dumps(payload, ensure_ascii=False)
    ]
    assert credential_requests == ["/internal/v1/public-sessions/resolve"]
    event_requests = [payload for path, payload in requests if path.endswith("/events")]
    assert [payload["wait_seconds"] for payload in event_requests] == [0.0, 2.5]
    assert event_requests[0]["limit"] == 100
    assert event_requests[1]["limit"] == 200


def test_http_core_translates_missing_conflict_protocol_and_timeout_errors() -> None:
    principal = PublicPrincipal(session_id=SESSION_ID, origin=ORIGIN)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if request.url.path == "/internal/v1/public-sessions/resolve":
            return httpx.Response(
                401,
                json={
                    "error": {
                        "code": "public_session_required_or_expired",
                        "message": "expired",
                        "retryable": False,
                    }
                },
            )
        if request.url.path in {
            "/internal/v1/responses/get",
            "/internal/v1/responses/cancel",
        }:
            return httpx.Response(
                404,
                json={
                    "error": {
                        "code": "response_not_found",
                        "message": "missing",
                        "retryable": False,
                    }
                },
            )
        if payload.get("idempotency_key") == "request-conflict-0001":
            return httpx.Response(
                409,
                json={
                    "error": {
                        "code": "idempotency_conflict",
                        "message": "conflict",
                        "retryable": False,
                    }
                },
            )
        return httpx.Response(
            200, content=b"[]", headers={"content-type": "application/json"}
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url=CORE_URL,
            transport=httpx.MockTransport(handler),
            trust_env=False,
        ) as client:
            core = HttpCoreClient(client)
            assert await core.resolve_public_session(CREDENTIAL) is None
            assert await core.get_response(principal, RESPONSE_ID) is None
            assert (
                await core.cancel_response(
                    principal,
                    RESPONSE_ID,
                    idempotency_key="request-cancel-0001",
                    request_sha256=REQUEST_SHA256,
                )
                is None
            )
            with pytest.raises(CoreError) as conflict:
                await core.create_response(
                    principal,
                    {"model": "kolibri", "input": "Привет"},
                    idempotency_key="request-conflict-0001",
                    request_sha256=REQUEST_SHA256,
                )
            assert conflict.value.code == "idempotency_conflict"
            assert conflict.value.status_code == 409

            with pytest.raises(CoreError) as malformed:
                await core.create_response(
                    principal,
                    {"model": "kolibri", "input": "Привет"},
                    idempotency_key="request-malformed-0001",
                    request_sha256=REQUEST_SHA256,
                )
            assert malformed.value.code == "core_protocol_invalid"
            assert malformed.value.status_code == 502

    run(scenario())

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("bounded timeout", request=request)

    async def timeout_scenario() -> None:
        async with httpx.AsyncClient(
            base_url=CORE_URL,
            transport=httpx.MockTransport(timeout_handler),
            trust_env=False,
        ) as client:
            core = HttpCoreClient(client)
            with pytest.raises(CoreError) as timeout:
                await core.create_public_session(ORIGIN)
            assert timeout.value.code == "core_read_timeout"
            assert timeout.value.status_code == 504
            assert timeout.value.retryable is True

    run(timeout_scenario())


def test_runtime_settings_fail_closed_and_factory_bootstraps_without_credential_leak() -> (
    None
):
    with pytest.raises(RuntimeConfigurationError):
        EdgeRuntimeSettings.from_env({})
    with pytest.raises(RuntimeConfigurationError):
        EdgeRuntimeSettings.from_env(
            {
                "KOLIBRI_EDGE_ALLOWED_ORIGINS": "*",
                "KOLIBRI_RESPONSE_CORE_URL": CORE_URL,
            }
        )
    with pytest.raises(RuntimeConfigurationError):
        EdgeRuntimeSettings.from_env(
            {
                "KOLIBRI_EDGE_ALLOWED_ORIGINS": ORIGIN,
                "KOLIBRI_RESPONSE_CORE_URL": "http://10.99.0.1:9202",
            }
        )

    external_client = httpx.AsyncClient(
        base_url="http://10.99.0.1:9202", trust_env=False
    )
    with pytest.raises(ValueError):
        HttpCoreClient(external_client)
    run(external_client.aclose())

    unbounded_client = httpx.AsyncClient(
        base_url=CORE_URL,
        timeout=httpx.Timeout(None),
        trust_env=False,
    )
    with pytest.raises(ValueError):
        HttpCoreClient(unbounded_client)
    run(unbounded_client.aclose())

    settings = EdgeRuntimeSettings.from_env(
        {
            "KOLIBRI_EDGE_ALLOWED_ORIGINS": f"{ORIGIN},http://127.0.0.1:5190",
            "KOLIBRI_RESPONSE_CORE_URL": CORE_URL,
            "KOLIBRI_CORE_CONNECT_TIMEOUT_SECONDS": "0.5",
            "KOLIBRI_CORE_READ_TIMEOUT_SECONDS": "12",
            "KOLIBRI_EDGE_SSE_WAIT_SECONDS": "10",
        }
    )
    assert settings.allowed_origins == (ORIGIN, "http://127.0.0.1:5190")
    assert settings.core_base_url == CORE_URL

    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/internal/v1/public-sessions":
            return httpx.Response(
                200,
                json={"session": session_payload(), "credential": CREDENTIAL},
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    app = create_runtime_app(settings, transport=httpx.MockTransport(handler))
    with TestClient(app, base_url=ORIGIN) as client:
        response = client.post("/v1/shell/bootstrap", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    assert response.json()["id"] == SESSION_ID
    assert CREDENTIAL not in response.text
    assert "httponly" in response.headers["set-cookie"].lower()
    assert paths == ["/internal/v1/public-sessions"]


def test_http_adapter_source_has_no_authority_provider_or_secret_logging() -> None:
    source = "\n".join(
        (BACKEND / "kolibri_edge" / name).read_text(encoding="utf-8")
        for name in ["http_core.py", "runtime.py"]
    )
    for forbidden in [
        "import sqlite3",
        "threading.Thread",
        "daemon=True",
        "logging.",
        "print(",
        "provider execution",
    ]:
        assert forbidden not in source
