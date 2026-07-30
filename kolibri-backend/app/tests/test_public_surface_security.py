from fastapi.testclient import TestClient

from app.browser_session import SESSION_COOKIE_NAME
from app.main import app


def test_raw_deepseek_provider_proxy_is_not_publicly_mounted(monkeypatch):
    # Even an explicitly enabled private proxy must not appear on the public
    # product application.  It is deployable only as a separately mounted,
    # server-authenticated surface.
    monkeypatch.setenv("KOLIBRI_DEEPSEEK_PROXY_ENABLED", "true")
    monkeypatch.setenv("KOLIBRI_DEEPSEEK_PROXY_TOKEN", "internal-secret")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "provider-secret")
    with TestClient(app) as client:
        response = client.post(
            "/deepseek/chat/completions",
            headers={"Authorization": "Bearer internal-secret"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 404


def test_cost_bearing_helpers_require_a_project_principal_before_handler():
    endpoints = (
        ("/api/v1/ai/generate-document", {"type": "offer", "context": "demo"}),
        ("/api/v1/ai/suggest", {"query": "demo"}),
        ("/api/v1/search/web", {"query": "demo"}),
        ("/api/v1/pdf/generate", {"title": "demo", "html_content": "demo"}),
        ("/api/v1/pdf/generate-docx", {"title": "demo", "html_content": "demo"}),
    )
    with TestClient(app) as client:
        responses = [client.post(path, json=payload) for path, payload in endpoints]

    assert [response.status_code for response in responses] == [428] * len(endpoints)
    assert all(response.json()["detail"]["code"] == "session_bootstrap_required" for response in responses)


def test_anonymous_session_cookie_mutations_require_exact_same_origin():
    with TestClient(app) as client:
        bootstrap = client.post("/api/v1/shell/bootstrap")
        assert bootstrap.status_code == 200
        assert client.cookies.get(SESSION_COOKIE_NAME)

        client.headers.pop("sec-fetch-site", None)
        missing_origin = client.post("/api/v1/projects", json={"title": "blocked"})
        cross_origin = client.post(
            "/api/v1/projects",
            headers={"Origin": "https://evil.example"},
            json={"title": "blocked"},
        )
        same_origin = client.post(
            "/api/v1/projects",
            headers={"Origin": "http://testserver"},
            json={"title": "allowed"},
        )

    assert missing_origin.status_code == 403
    assert missing_origin.json()["error"]["code"] == "csrf_origin_forbidden"
    assert cross_origin.status_code == 403
    assert same_origin.status_code in {200, 201}
