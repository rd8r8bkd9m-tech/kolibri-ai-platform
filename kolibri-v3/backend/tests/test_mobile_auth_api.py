from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


PASSWORD = "correct-horse-battery-staple"
DEVICE = {
    "platform": "ios",
    "deviceName": "Vladislav iPhone",
    "appVersion": "1.0.0",
}


def _settings(database_path: Path) -> Settings:
    return Settings.for_testing(
        database_url=database_path,
        bootstrap_owner_email=None,
    )


def _mobile_register(
    client: TestClient,
    *,
    email: str,
    name: str = "Mobile User",
) -> dict[str, object]:
    response = client.post(
        "/v1/mobile/auth/register",
        json={
            "email": email,
            "name": name,
            "password": PASSWORD,
            "device": DEVICE,
        },
    )
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def _bearer(access_token: object) -> dict[str, str]:
    assert isinstance(access_token, str)
    return {"Authorization": f"Bearer {access_token}"}


def test_mobile_register_uses_bearer_without_browser_cookie_or_csrf(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "mobile-register.db"
    with TestClient(create_app(_settings(database_path))) as client:
        issued = _mobile_register(client, email="mobile@example.com")

        assert issued["tokenType"] == "Bearer"
        assert str(issued["accessToken"]).startswith("kma_")
        assert str(issued["refreshToken"]).startswith("kmr_")
        assert issued["user"]["email"] == "mobile@example.com"
        assert client.cookies.get("kolibri_v3_session") is None
        assert client.cookies.get("kolibri_v3_csrf") is None

        session = client.get(
            "/v1/mobile/auth/session",
            headers=_bearer(issued["accessToken"]),
        )
        assert session.status_code == 200
        assert session.json()["user"]["id"] == issued["user"]["id"]

        updated = client.patch(
            "/v1/profile",
            headers=_bearer(issued["accessToken"]),
            json={"name": "Native Updated"},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Native Updated"

        no_token = client.get("/v1/mobile/auth/session")
        assert no_token.status_code == 401
        assert no_token.json()["code"] == "mobile_access_token_required"

    database = sqlite3.connect(database_path)
    try:
        access_hash = database.execute(
            "SELECT token_hash FROM mobile_access_tokens"
        ).fetchone()[0]
        refresh_hash = database.execute(
            "SELECT token_hash FROM mobile_refresh_tokens"
        ).fetchone()[0]
        assert len(access_hash) == 64
        assert len(refresh_hash) == 64
        assert issued["accessToken"] not in {access_hash, refresh_hash}
        assert issued["refreshToken"] not in {access_hash, refresh_hash}
    finally:
        database.close()


def test_refresh_rotation_revokes_previous_access_and_replay_revokes_family(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "mobile-refresh.db"
    with TestClient(create_app(_settings(database_path))) as client:
        first = _mobile_register(client, email="rotate@example.com")

        refreshed_response = client.post(
            "/v1/mobile/auth/refresh",
            json={"refreshToken": first["refreshToken"]},
        )
        assert refreshed_response.status_code == 200
        refreshed = refreshed_response.json()
        assert refreshed["accessToken"] != first["accessToken"]
        assert refreshed["refreshToken"] != first["refreshToken"]
        assert refreshed["deviceSessionId"] == first["deviceSessionId"]

        stale_access = client.get(
            "/v1/profile",
            headers=_bearer(first["accessToken"]),
        )
        assert stale_access.status_code == 401
        assert stale_access.json()["code"] == "mobile_access_token_invalid"

        current_access = client.get(
            "/v1/profile",
            headers=_bearer(refreshed["accessToken"]),
        )
        assert current_access.status_code == 200

        replay = client.post(
            "/v1/mobile/auth/refresh",
            json={"refreshToken": first["refreshToken"]},
        )
        assert replay.status_code == 401
        assert replay.json()["code"] == "mobile_refresh_token_reused"

        revoked_access = client.get(
            "/v1/profile",
            headers=_bearer(refreshed["accessToken"]),
        )
        assert revoked_access.status_code == 401

        revoked_refresh = client.post(
            "/v1/mobile/auth/refresh",
            json={"refreshToken": refreshed["refreshToken"]},
        )
        assert revoked_refresh.status_code == 401
        assert revoked_refresh.json()["code"] == "mobile_refresh_token_invalid"

    database = sqlite3.connect(database_path)
    try:
        device = database.execute(
            "SELECT revoked_at FROM mobile_device_sessions"
        ).fetchone()
        assert device[0] is not None
        events = {
            row[0]
            for row in database.execute(
                "SELECT event_type FROM mobile_auth_events"
            ).fetchall()
        }
        assert {"device_registered", "token_refreshed", "refresh_replay_detected"} <= events
    finally:
        database.close()


def test_mobile_logout_revokes_only_the_presented_device_session(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "mobile-logout.db"
    app = create_app(_settings(database_path))
    with TestClient(app) as first_client, TestClient(app) as second_client:
        first = _mobile_register(first_client, email="devices@example.com")
        second_response = second_client.post(
            "/v1/mobile/auth/login",
            json={
                "email": "devices@example.com",
                "password": PASSWORD,
                "device": {
                    **DEVICE,
                    "deviceName": "Work iPhone",
                },
            },
        )
        assert second_response.status_code == 200
        second = second_response.json()
        assert second["deviceSessionId"] != first["deviceSessionId"]

        logged_out = first_client.post(
            "/v1/mobile/auth/logout",
            json={"refreshToken": first["refreshToken"]},
        )
        assert logged_out.status_code == 200
        assert logged_out.json() == {"authenticated": False, "user": None}

        assert (
            first_client.get(
                "/v1/profile",
                headers=_bearer(first["accessToken"]),
            ).status_code
            == 401
        )
        assert (
            second_client.get(
                "/v1/profile",
                headers=_bearer(second["accessToken"]),
            ).status_code
            == 200
        )

    database = sqlite3.connect(database_path)
    try:
        rows = database.execute(
            """
            SELECT id, revoked_at
            FROM mobile_device_sessions
            ORDER BY created_at, id
            """
        ).fetchall()
        assert len(rows) == 2
        assert sum(row[1] is not None for row in rows) == 1
    finally:
        database.close()


def test_invalid_authorization_never_falls_back_to_browser_cookie(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "mobile-cookie-confusion.db"
    with TestClient(create_app(_settings(database_path))) as client:
        browser = client.post(
            "/v1/auth/register",
            headers={"Origin": "http://testserver"},
            json={
                "email": "browser@example.com",
                "name": "Browser User",
                "password": PASSWORD,
            },
        )
        assert browser.status_code == 201
        assert client.cookies.get("kolibri_v3_session")

        invalid = {"Authorization": "Bearer kma_invalid"}
        read = client.get("/v1/profile", headers=invalid)
        assert read.status_code == 401
        assert read.json()["code"] == "mobile_access_token_invalid"

        mutation = client.patch(
            "/v1/profile",
            headers=invalid,
            json={"name": "Must Not Change"},
        )
        assert mutation.status_code == 401
        assert mutation.json()["code"] == "mobile_access_token_invalid"
        assert client.get("/v1/profile").json()["name"] == "Browser User"
