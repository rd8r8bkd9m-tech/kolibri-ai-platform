import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/api/v1/context/caller-controlled-id", None),
        ("POST", "/api/v1/context/caller-controlled-id", {"client_name": "Чужой клиент"}),
        ("POST", "/api/v1/context/caller-controlled-id/estimate", {"total": 1}),
        ("POST", "/api/v1/context/caller-controlled-id/document", {"title": "Документ"}),
        ("POST", "/api/v1/context/caller-controlled-id/message", {"content": "Сообщение"}),
        ("GET", "/api/v1/context/caller-controlled-id/ai-context", None),
    ],
)
def test_legacy_context_surface_is_an_explicit_non_cacheable_tombstone(
    method: str,
    path: str,
    payload: dict | None,
):
    with TestClient(app) as client:
        response = client.request(method, path, json=payload)

    assert response.status_code == 410
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["detail"] == {
        "code": "legacy_context_retired",
        "message": "Legacy client context is retired; use project-scoped APIs",
    }
    assert response.json()["error"]["code"] == "legacy_context_retired"
    assert "caller-controlled-id" not in response.text
