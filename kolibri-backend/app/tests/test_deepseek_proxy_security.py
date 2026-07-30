from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from proxy import deepseek_proxy


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(deepseek_proxy.router)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def isolated_proxy_environment(monkeypatch):
    for name in (
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "KOLIBRI_DEEPSEEK_PROXY_ENABLED",
        "KOLIBRI_DEEPSEEK_PROXY_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)


def _fail_if_called(**_kwargs):
    raise AssertionError("upstream must not be called before private proxy authorization")


def test_proxy_is_disabled_by_default_before_provider_access(monkeypatch, client):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "provider-secret")
    monkeypatch.setenv("KOLIBRI_DEEPSEEK_PROXY_TOKEN", "internal-secret")
    monkeypatch.setattr(deepseek_proxy, "_request_upstream", _fail_if_called)

    response = client.post(
        "/deepseek/chat/completions",
        headers={"Authorization": "Bearer internal-secret"},
        json={"messages": []},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"


def test_enabled_proxy_fails_closed_without_server_auth_configuration(monkeypatch, client):
    monkeypatch.setenv("KOLIBRI_DEEPSEEK_PROXY_ENABLED", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "provider-secret")
    monkeypatch.setattr(deepseek_proxy, "_request_upstream", _fail_if_called)

    response = client.post("/deepseek/chat/completions", json={"messages": []})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "deepseek_proxy_auth_not_configured"


@pytest.mark.parametrize("authorization", [None, "Bearer wrong", "Basic internal-secret"])
def test_enabled_proxy_rejects_missing_or_invalid_internal_bearer(
    monkeypatch,
    client,
    authorization,
):
    monkeypatch.setenv("KOLIBRI_DEEPSEEK_PROXY_ENABLED", "true")
    monkeypatch.setenv("KOLIBRI_DEEPSEEK_PROXY_TOKEN", "internal-secret")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "provider-secret")
    monkeypatch.setattr(deepseek_proxy, "_request_upstream", _fail_if_called)
    headers = {"Authorization": authorization} if authorization else {}

    response = client.post(
        "/deepseek/chat/completions",
        headers=headers,
        json={"messages": []},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["detail"]["code"] == "deepseek_proxy_unauthorized"


def test_authorized_proxy_substitutes_provider_key_and_forwards_only_allowlisted_path(
    monkeypatch,
    client,
):
    captured: dict = {}

    async def upstream(**kwargs):
        captured.update(kwargs)
        request = httpx.Request(kwargs["method"], kwargs["url"])
        return httpx.Response(
            200,
            request=request,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={"ok": True},
        )

    monkeypatch.setenv("KOLIBRI_DEEPSEEK_PROXY_ENABLED", "true")
    monkeypatch.setenv("KOLIBRI_DEEPSEEK_PROXY_TOKEN", "internal-secret")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "provider-secret")
    monkeypatch.setattr(deepseek_proxy, "_request_upstream", upstream)

    response = client.post(
        "/deepseek/chat/completions?beta=1",
        headers={"Authorization": "Bearer internal-secret"},
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    blocked = client.get(
        "/deepseek/admin/secrets",
        headers={"Authorization": "Bearer internal-secret"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert captured["url"] == "https://api.deepseek.com/chat/completions?beta=1"
    assert captured["headers"]["Authorization"] == "Bearer provider-secret"
    assert "internal-secret" not in str(captured)
    assert response.headers["cache-control"] == "no-store"
    assert blocked.status_code == 404
