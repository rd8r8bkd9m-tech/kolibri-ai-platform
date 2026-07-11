from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import public_responses_api  # noqa: E402


def test_valid_v1_cookie_survives_stale_legacy_duplicate(tmp_path):
    store = public_responses_api.configure_public_response_store(tmp_path / "public.db")
    public_responses_api.configure_public_response_origins(["http://testserver"])
    stale, stale_token = store.issue("http://testserver", ttl_seconds=900)
    valid, valid_token = store.issue("http://testserver", ttl_seconds=900)
    store.expire_session_for_test(stale["id"])

    app = FastAPI()
    app.include_router(public_responses_api.router)
    client = TestClient(app)

    # Browsers order a more specific /v1 cookie before an older / cookie. A
    # mapping parser keeps only one duplicate name and can therefore let the
    # stale legacy value shadow the valid current session.
    cookie = (
        f"{public_responses_api.COOKIE_NAME}={valid_token}; "
        f"{public_responses_api.COOKIE_NAME}={stale_token}"
    )
    response = client.get("/v1/public/session", headers={"Cookie": cookie})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["id"] == valid["id"]
