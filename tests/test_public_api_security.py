from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main


def test_public_health_is_sanitized():
    client = TestClient(main.app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "provider_status" not in response.json()
    assert "version" not in response.json()
    assert "database" not in response.json()


def test_public_v1_estimates_are_not_exposed_without_auth(monkeypatch):
    monkeypatch.setenv("KOLIBRI_PRIVATE_API_TOKEN", "test-token")
    client = TestClient(main.app)

    response = client.get("/api/v1/estimates")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_authenticated_v1_estimates_guard_does_not_expose_placeholder_data(monkeypatch):
    monkeypatch.setenv("KOLIBRI_PRIVATE_API_TOKEN", "test-token")
    client = TestClient(main.app)

    response = client.get("/api/v1/estimates", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}


def test_public_factory_status_is_not_fetched_without_auth(monkeypatch):
    monkeypatch.setenv("KOLIBRI_PRIVATE_API_TOKEN", "test-token")
    called = False

    async def fail_if_called():
        nonlocal called
        called = True
        return {"status": "online"}

    monkeypatch.setattr(main, "fetch_factory_status", fail_if_called)
    client = TestClient(main.app)

    response = client.get("/api/factory/status")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
    assert called is False


def test_authenticated_factory_status_degrades_without_gateway_timeout(monkeypatch):
    monkeypatch.setenv("KOLIBRI_PRIVATE_API_TOKEN", "test-token")

    async def fail_control_plane():
        raise TimeoutError("control plane timed out")

    monkeypatch.setattr(main, "fetch_factory_status", fail_control_plane)
    client = TestClient(main.app)

    response = client.get("/api/factory/status", headers={"X-Kolibri-API-Key": "test-token"})

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["control_plane"]["reason"] == "control_plane_api_unreachable"
    assert body["control_plane"]["can_continue_elsewhere"] is True
