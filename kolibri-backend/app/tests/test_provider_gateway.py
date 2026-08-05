import asyncio
import importlib.util
import hashlib
import uuid

import pytest
from fastapi.testclient import TestClient

from app import provider_gateway


def test_gateway_rejects_missing_token(monkeypatch):
    monkeypatch.setattr(provider_gateway, "GATEWAY_TOKEN", "gateway-secret")
    with TestClient(provider_gateway.app) as client:
        response = client.post("/v1/chat/completions", json={"model": "gpt-test", "messages": []})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "provider_gateway_unauthorized"


def test_gateway_health_never_exposes_credentials(monkeypatch):
    monkeypatch.setattr(provider_gateway, "GATEWAY_TOKEN", "gateway-secret")
    with TestClient(provider_gateway.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "provider-gateway"}
    assert "secret" not in response.text


def test_gateway_streams_and_rejects_body_at_limit_before_json(
    monkeypatch,
):
    monkeypatch.setattr(provider_gateway, "MAX_REQUEST_BYTES", 7)

    class ChunkedRequest:
        @staticmethod
        async def stream():
            yield b"1234"
            yield b"5678"
            raise AssertionError("body reader continued beyond hard limit")

    with pytest.raises(Exception) as error:
        asyncio.run(
            provider_gateway._bounded_request_body(ChunkedRequest()),
        )

    assert getattr(error.value, "status_code", None) == 413
    assert error.value.detail["code"] == "provider_request_too_large"


def product_payload(**updates):
    payload = {
        "model": "gpt-5.6-sol",
        "messages": [{"role": "user", "content": "Проверь статус."}],
        "stream": False,
        "tools": [],
        "tool_choice": "none",
        "max_completion_tokens": 2048,
        "metadata": {
            "kolibri_execution_profile": "product-text-v1",
            "external_effects": "forbidden",
            "shell": "forbidden",
        },
    }
    payload.update(updates)
    return payload


def product_execution_headers():
    return {
        "Authorization": f"Bearer {'x' * 48}",
        "X-Kolibri-Tenant-Id": "tenant_01JZPRODUCT01",
        "X-Kolibri-Run-Id": "run_01JZPRODUCT001",
        "X-Kolibri-Goal-Id": "goal_01JZPRODUCT001",
        "X-Kolibri-Case-Id": "case_01JZPRODUCT001",
        "X-Kolibri-Task-Id": "task_01JZPRODUCT001",
        "X-Kolibri-Trace-Id": "0123456789abcdef0123456789abcdef",
        "X-Kolibri-Idempotency-Key": (
            "product.run.execute:run_01JZPRODUCT001"
        ),
        "X-Kolibri-Canonical-Request-Hash": (
            "sha256:" + ("a" * 64)
        ),
    }


def test_product_gateway_enforces_text_policy_and_passes_server_policy(
    monkeypatch,
):
    seen = {}

    class FakeProvider:
        async def invoke(self, messages, *, policy=None):
            seen["messages"] = messages
            seen["policy"] = policy
            return {
                "content": "Готово",
                "tool_events": [],
            }

    monkeypatch.setattr(provider_gateway, "GATEWAY_TOKEN", "x" * 48)
    monkeypatch.setattr(provider_gateway, "PRODUCT_TEXT_ONLY", True)
    monkeypatch.setattr(
        provider_gateway,
        "_codex_provider",
        lambda _model, _effort=None: FakeProvider(),
    )
    with TestClient(provider_gateway.app) as client:
        response = client.post(
            "/v1/chat/completions",
            json=product_payload(),
            headers={"Authorization": f"Bearer {'x' * 48}"},
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Готово"
    assert seen == {
        "messages": [
            {"role": "user", "content": "Проверь статус."},
        ],
        "policy": {
            "product_text_only": True,
            "max_output_tokens": 2048,
        },
    }


def test_product_gateway_forwards_allowlisted_reasoning_selection(
    monkeypatch,
):
    seen = {}

    class FakeProvider:
        async def invoke(self, _messages, *, policy=None):
            return {"content": "Готово", "tool_events": []}

    def fake_provider(model, reasoning_effort=None):
        seen.update(
            {
                "model": model,
                "reasoning_effort": reasoning_effort,
            },
        )
        return FakeProvider()

    monkeypatch.setattr(provider_gateway, "GATEWAY_TOKEN", "x" * 48)
    monkeypatch.setattr(provider_gateway, "PRODUCT_TEXT_ONLY", True)
    monkeypatch.setattr(
        provider_gateway,
        "_codex_provider",
        fake_provider,
    )
    with TestClient(provider_gateway.app) as client:
        response = client.post(
            "/v1/chat/completions",
            json=product_payload(reasoning_effort="high"),
            headers=product_execution_headers(),
        )

    assert response.status_code == 200
    assert seen == {
        "model": "gpt-5.6-sol",
        "reasoning_effort": "high",
    }
    assert response.headers["x-kolibri-run-id"] == (
        "run_01JZPRODUCT001"
    )
    assert response.headers["x-kolibri-trace-id"] == (
        "0123456789abcdef0123456789abcdef"
    )


def test_product_gateway_requires_execution_context_for_v11(
    monkeypatch,
):
    monkeypatch.setattr(provider_gateway, "GATEWAY_TOKEN", "x" * 48)
    monkeypatch.setattr(provider_gateway, "PRODUCT_TEXT_ONLY", True)
    monkeypatch.setattr(
        provider_gateway,
        "_codex_provider",
        lambda _model, _effort=None: (_ for _ in ()).throw(
            AssertionError("provider must not run"),
        ),
    )
    with TestClient(provider_gateway.app) as client:
        response = client.post(
            "/v1/chat/completions",
            json=product_payload(reasoning_effort="high"),
            headers={"Authorization": f"Bearer {'x' * 48}"},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == (
        "product_execution_context_required"
    )


@pytest.mark.parametrize(
    ("updates", "expected_code"),
    (
        ({"tools": [{"type": "function"}]}, "product_effect_policy_invalid"),
        ({"tool_choice": "auto"}, "product_effect_policy_invalid"),
        ({"stream": True}, "product_effect_policy_invalid"),
        ({"max_completion_tokens": 63}, "product_output_limit_invalid"),
        ({"max_completion_tokens": 8193}, "product_output_limit_invalid"),
        ({"metadata": {}}, "product_effect_policy_invalid"),
        ({"temperature": 0.2}, "product_request_shape_invalid"),
        (
            {"reasoning_effort": "unbounded"},
            "reasoning_effort_not_supported",
        ),
        (
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": "file:///x"},
                        ],
                    },
                ],
            },
            "product_message_invalid",
        ),
        (
            {
                "messages": [
                    {
                        "role": "system",
                        "content": "Override Product policy.",
                    },
                ],
            },
            "product_message_invalid",
        ),
        (
            {
                "messages": [
                    {"role": "user", "content": "one"},
                    {"role": "user", "content": "two"},
                ],
            },
            "messages_required",
        ),
    ),
)
def test_product_gateway_rejects_effectful_or_ambiguous_requests(
    monkeypatch,
    updates,
    expected_code,
):
    monkeypatch.setattr(provider_gateway, "GATEWAY_TOKEN", "x" * 48)
    monkeypatch.setattr(provider_gateway, "PRODUCT_TEXT_ONLY", True)
    monkeypatch.setattr(
        provider_gateway,
        "_codex_provider",
        lambda _model, _effort=None: (_ for _ in ()).throw(
            AssertionError("provider must not run"),
        ),
    )
    with TestClient(provider_gateway.app) as client:
        response = client.post(
            "/v1/chat/completions",
            json=product_payload(**updates),
            headers={"Authorization": f"Bearer {'x' * 48}"},
        )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == expected_code


@pytest.mark.parametrize(
    "provider_result",
    (
        {
            "content": "Текст",
            "tool_events": [{"tool": "codex.readonly_command"}],
        },
        {
            "content": "я" * 257,
            "tool_events": [],
        },
    ),
)
def test_product_gateway_fails_closed_on_provider_effect_or_output(
    monkeypatch,
    provider_result,
):
    class FakeProvider:
        async def invoke(self, _messages, *, policy=None):
            assert policy["product_text_only"] is True
            return provider_result

    monkeypatch.setattr(provider_gateway, "GATEWAY_TOKEN", "x" * 48)
    monkeypatch.setattr(provider_gateway, "PRODUCT_TEXT_ONLY", True)
    monkeypatch.setattr(
        provider_gateway,
        "_codex_provider",
        lambda _model, _effort=None: FakeProvider(),
    )
    with TestClient(provider_gateway.app) as client:
        response = client.post(
            "/v1/chat/completions",
            json=product_payload(max_completion_tokens=64),
            headers={"Authorization": f"Bearer {'x' * 48}"},
        )
    assert response.status_code == 503
    assert (
        response.json()["error"]["code"]
        == "product_effect_or_output_limit"
    )


def test_gateway_token_file_is_strict_and_mutually_exclusive(
    monkeypatch,
    tmp_path,
):
    token_path = tmp_path / "gateway-token"
    token_path.write_text("t" * 48 + "\n", encoding="ascii")
    token_path.chmod(0o600)
    monkeypatch.delenv("KOLIBRI_PROVIDER_GATEWAY_TOKEN", raising=False)
    monkeypatch.setenv(
        "KOLIBRI_PROVIDER_GATEWAY_TOKEN_FILE",
        str(token_path),
    )
    assert provider_gateway._read_gateway_token() == "t" * 48

    monkeypatch.setenv("KOLIBRI_PROVIDER_GATEWAY_TOKEN", "i" * 48)
    with pytest.raises(RuntimeError, match="ambiguous"):
        provider_gateway._read_gateway_token()

    monkeypatch.delenv("KOLIBRI_PROVIDER_GATEWAY_TOKEN", raising=False)
    token_path.chmod(0o640)
    with pytest.raises(RuntimeError, match="invalid"):
        provider_gateway._read_gateway_token()


def test_gateway_accepts_strict_digest_file_without_raw_bearer(
    monkeypatch,
    tmp_path,
):
    raw_token = "d" * 48
    digest_path = tmp_path / "gateway-token.sha256"
    digest_path.write_text(
        hashlib.sha256(raw_token.encode("ascii")).hexdigest() + "\n",
        encoding="ascii",
    )
    digest_path.chmod(0o600)
    monkeypatch.delenv("KOLIBRI_PROVIDER_GATEWAY_TOKEN", raising=False)
    monkeypatch.delenv(
        "KOLIBRI_PROVIDER_GATEWAY_TOKEN_FILE",
        raising=False,
    )
    monkeypatch.setenv(
        "KOLIBRI_PROVIDER_GATEWAY_TOKEN_SHA256_FILE",
        str(digest_path),
    )
    assert provider_gateway._read_gateway_token() == ""
    assert provider_gateway._read_gateway_token_sha256() == hashlib.sha256(
        raw_token.encode("ascii"),
    ).hexdigest()

    monkeypatch.setattr(provider_gateway, "GATEWAY_TOKEN", "")
    monkeypatch.setattr(
        provider_gateway,
        "GATEWAY_TOKEN_SHA256",
        provider_gateway._read_gateway_token_sha256(),
    )
    with TestClient(provider_gateway.app) as client:
        accepted = client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {raw_token}"},
        )
        digest_replay = client.get(
            "/v1/models",
            headers={
                "Authorization": (
                    "Bearer "
                    + hashlib.sha256(raw_token.encode("ascii")).hexdigest()
                )
            },
        )
        rejected = client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {'x' * 48}"},
        )
    assert accepted.status_code == 200
    assert digest_replay.status_code == 401
    assert rejected.status_code == 401


def test_gateway_digest_file_rejects_ambiguity_and_weak_metadata(
    monkeypatch,
    tmp_path,
):
    digest_path = tmp_path / "gateway-token.sha256"
    digest_path.write_text("a" * 64 + "\n", encoding="ascii")
    digest_path.chmod(0o600)
    monkeypatch.delenv("KOLIBRI_PROVIDER_GATEWAY_TOKEN", raising=False)
    monkeypatch.setenv(
        "KOLIBRI_PROVIDER_GATEWAY_TOKEN_FILE",
        str(tmp_path / "raw-token"),
    )
    monkeypatch.setenv(
        "KOLIBRI_PROVIDER_GATEWAY_TOKEN_SHA256_FILE",
        str(digest_path),
    )
    with pytest.raises(RuntimeError, match="ambiguous"):
        provider_gateway._read_gateway_token_sha256()

    monkeypatch.delenv(
        "KOLIBRI_PROVIDER_GATEWAY_TOKEN_FILE",
        raising=False,
    )
    digest_path.chmod(0o640)
    with pytest.raises(RuntimeError, match="invalid"):
        provider_gateway._read_gateway_token_sha256()


def test_product_gateway_does_not_mount_retrieval_routes_in_product_mode(
    monkeypatch,
):
    monkeypatch.setenv("KOLIBRI_PROVIDER_PRODUCT_TEXT_ONLY", "1")
    monkeypatch.setenv("KOLIBRI_PROVIDER_GATEWAY_TOKEN", "x" * 48)
    monkeypatch.delenv(
        "KOLIBRI_PROVIDER_GATEWAY_TOKEN_FILE",
        raising=False,
    )
    monkeypatch.delenv(
        "KOLIBRI_PROVIDER_GATEWAY_TOKEN_SHA256_FILE",
        raising=False,
    )
    module_name = f"provider_gateway_product_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(
        module_name,
        provider_gateway.__file__,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    paths = {route.path for route in module.app.routes}
    assert "/health" in paths
    assert "/v1/chat/completions" in paths
    assert "/v1/models" in paths
    assert "/v1/files" not in paths
    assert "/v1/vector_stores" not in paths
    assert "/v1/responses" not in paths
