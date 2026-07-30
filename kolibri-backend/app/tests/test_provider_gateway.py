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
