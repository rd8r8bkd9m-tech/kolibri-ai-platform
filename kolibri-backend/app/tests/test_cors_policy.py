from fastapi.testclient import TestClient

from app.main import _CORS_ALLOWED_ORIGINS, app


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/api/v1/shell/bootstrap",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


def test_cors_credentials_are_bound_to_exact_allowed_origin():
    assert "*" not in _CORS_ALLOWED_ORIGINS
    assert "https://kolibriai.ru" in _CORS_ALLOWED_ORIGINS

    with TestClient(app) as client:
        allowed = _preflight(client, "https://kolibriai.ru")
        denied = _preflight(client, "https://evil.example")

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://kolibriai.ru"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in denied.headers
