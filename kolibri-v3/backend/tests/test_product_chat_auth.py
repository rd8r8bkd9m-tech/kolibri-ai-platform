from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from fastapi.testclient import TestClient

from app.config import Settings
from app.database import connect_database, transaction
from app.main import create_app


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"
DEVICE = {
    "platform": "ios",
    "deviceName": "Auth contract iPhone",
    "appVersion": "1.0.0",
}


def _settings(database_path: Path) -> Settings:
    return replace(
        Settings.for_testing(
            database_url=database_path,
            bootstrap_owner_email=None,
        ),
        direct_model_runtime_enabled=True,
        product_run_poll_seconds=0.05,
    )


def _bearer(access_token: object) -> dict[str, str]:
    assert isinstance(access_token, str)
    return {"Authorization": f"Bearer {access_token}"}


def _mobile_register(
    client: TestClient,
    *,
    email: str,
    device_name: str,
) -> dict[str, object]:
    response = client.post(
        "/v1/mobile/auth/register",
        json={
            "email": email,
            "name": email.split("@", 1)[0],
            "password": PASSWORD,
            "device": {**DEVICE, "deviceName": device_name},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _browser_register(
    client: TestClient,
    *,
    email: str,
) -> dict[str, object]:
    response = client.post(
        "/v1/auth/register",
        headers=ORIGIN,
        json={
            "email": email,
            "name": "Browser User",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _run_payload(suffix: str) -> dict[str, object]:
    return {
        "threadId": f"thread_auth_{suffix}_01",
        "runId": f"run_auth_{suffix}_01",
        "state": None,
        "messages": [
            {
                "id": f"message_auth_{suffix}_01",
                "role": "user",
                "content": "Ответь одним коротким предложением.",
            }
        ],
        "tools": [],
        "context": [],
        "forwardedProps": {
            "agentProfile": "auto",
            "executionMode": "standard",
            "accessMode": "standard",
        },
    }


class _ImmediateDispatcher:
    """Test-only terminalizer after the real Product/Data acceptance commit."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def notify(self) -> None:
        database = connect_database(self.database_path)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with transaction(database, immediate=True):
                rows = database.execute(
                    """
                    SELECT tenant_id, id, thread_id, last_event_sequence
                    FROM chat_runs
                    WHERE status = 'running'
                    ORDER BY created_at, id
                    """
                ).fetchall()
                for run in rows:
                    sequence = int(run["last_event_sequence"]) + 1
                    database.execute(
                        """
                        INSERT INTO chat_run_events (
                            tenant_id, event_id, run_id, sequence, event_type,
                            event_json, created_at
                        ) VALUES (?, ?, ?, ?, 'RUN_FINISHED', ?, ?)
                        """,
                        (
                            str(run["tenant_id"]),
                            f"event_auth_{uuid.uuid4().hex}",
                            str(run["id"]),
                            sequence,
                            json.dumps(
                                {
                                    "type": "RUN_FINISHED",
                                    "threadId": str(run["thread_id"]),
                                    "runId": str(run["id"]),
                                    "outcome": {"type": "success"},
                                },
                                separators=(",", ":"),
                                sort_keys=True,
                            ),
                            now,
                        ),
                    )
                    database.execute(
                        """
                        UPDATE chat_runs
                        SET status = 'succeeded',
                            outcome = 'success',
                            last_event_sequence = ?,
                            heartbeat_at = ?,
                            updated_at = ?,
                            finished_at = ?
                        WHERE tenant_id = ? AND id = ? AND status = 'running'
                        """,
                        (
                            sequence,
                            now,
                            now,
                            now,
                            str(run["tenant_id"]),
                            str(run["id"]),
                        ),
                    )
        finally:
            database.close()


def _event_ids(response_text: str) -> list[int]:
    return [
        int(line.removeprefix("id: "))
        for line in response_text.splitlines()
        if line.startswith("id: ")
    ]


def test_browser_and_native_agui_auth_contracts_remain_isolated(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "product-chat-auth.db"
    app = create_app(_settings(database_path))

    with TestClient(app) as client:
        original_dispatcher = app.state.direct_run_dispatcher
        assert original_dispatcher is not None
        original_dispatcher.close()
        app.state.direct_run_dispatcher = _ImmediateDispatcher(database_path)
        try:
            native = _mobile_register(
                client,
                email="native-a@example.com",
                device_name="Native A",
            )
            other_tenant = _mobile_register(
                client,
                email="native-b@example.com",
                device_name="Native B",
            )
            _browser_register(
                client,
                email="browser@example.com",
            )
            csrf = client.cookies.get("kolibri_v3_csrf")
            assert csrf
            invalid_bearer_send = client.post(
                "/v1/chat/ag-ui",
                headers={
                    **ORIGIN,
                    "Authorization": "Bearer kma_invalid",
                    "X-CSRF-Token": csrf,
                },
                json=_run_payload("invalid"),
            )
            assert invalid_bearer_send.status_code == 401
            assert (
                invalid_bearer_send.json()["code"]
                == "mobile_access_token_invalid"
            )

            native_send = client.post(
                "/v1/chat/ag-ui",
                headers={
                    **_bearer(native["accessToken"]),
                    "Accept": "text/event-stream",
                },
                json=_run_payload("native"),
            )
            assert native_send.status_code == 200, native_send.text
            native_run_id = native_send.headers["x-kolibri-run-id"]
            sent_ids = _event_ids(native_send.text)
            assert sent_ids
            assert sent_ids == sorted(set(sent_ids))

            native_resume = client.get(
                f"/v1/chat/runs/{native_run_id}/events",
                headers={
                    **_bearer(native["accessToken"]),
                    "Last-Event-ID": str(sent_ids[0]),
                    "Accept": "text/event-stream",
                },
            )
            assert native_resume.status_code == 200, native_resume.text
            resumed_ids = _event_ids(native_resume.text)
            assert resumed_ids
            assert all(sequence > sent_ids[0] for sequence in resumed_ids)
            assert native_resume.headers["x-kolibri-run-id"] == native_run_id

            invalid_cursor = client.get(
                f"/v1/chat/runs/{native_run_id}/events",
                headers={
                    **_bearer(native["accessToken"]),
                    "Last-Event-ID": "-1",
                },
            )
            assert invalid_cursor.status_code == 400
            assert invalid_cursor.json()["code"] == "run_cursor_invalid"

            native_cancel = client.post(
                f"/v1/chat/runs/{native_run_id}/cancel",
                headers=_bearer(native["accessToken"]),
            )
            assert native_cancel.status_code == 204

            crossed_resume = client.get(
                f"/v1/chat/runs/{native_run_id}/events",
                headers={
                    **_bearer(other_tenant["accessToken"]),
                    "Last-Event-ID": "0",
                },
            )
            assert crossed_resume.status_code == 404
            assert crossed_resume.json()["code"] == "run_not_found"
            crossed_cancel = client.post(
                f"/v1/chat/runs/{native_run_id}/cancel",
                headers=_bearer(other_tenant["accessToken"]),
            )
            assert crossed_cancel.status_code == 404
            assert crossed_cancel.json()["code"] == "run_not_found"

            rotated_response = client.post(
                "/v1/mobile/auth/refresh",
                json={"refreshToken": native["refreshToken"]},
            )
            assert rotated_response.status_code == 200
            rotated = rotated_response.json()
            assert (
                client.get(
                    f"/v1/chat/runs/{native_run_id}/events",
                    headers=_bearer(native["accessToken"]),
                ).status_code
                == 401
            )
            assert (
                client.get(
                    f"/v1/chat/runs/{native_run_id}/events",
                    headers={
                        **_bearer(rotated["accessToken"]),
                        "Last-Event-ID": str(sent_ids[-1]),
                    },
                ).status_code
                == 200
            )

            replay = client.post(
                "/v1/mobile/auth/refresh",
                json={"refreshToken": native["refreshToken"]},
            )
            assert replay.status_code == 401
            assert replay.json()["code"] == "mobile_refresh_token_reused"
            assert (
                client.get(
                    f"/v1/chat/runs/{native_run_id}/events",
                    headers=_bearer(rotated["accessToken"]),
                ).status_code
                == 401
            )
            revoked_descendant = client.post(
                "/v1/mobile/auth/refresh",
                json={"refreshToken": rotated["refreshToken"]},
            )
            assert revoked_descendant.status_code == 401
            assert (
                revoked_descendant.json()["code"]
                == "mobile_refresh_token_invalid"
            )

            browser_payload = _run_payload("browser")
            browser_without_csrf = client.post(
                "/v1/chat/ag-ui",
                headers=ORIGIN,
                json=browser_payload,
            )
            assert browser_without_csrf.status_code == 403
            assert (
                browser_without_csrf.json()["code"]
                == "csrf_token_required"
            )

            browser_send = client.post(
                "/v1/chat/ag-ui",
                headers={
                    **ORIGIN,
                    "X-CSRF-Token": csrf,
                    "Accept": "text/event-stream",
                },
                json=browser_payload,
            )
            assert browser_send.status_code == 200, browser_send.text
            browser_run_id = browser_send.headers["x-kolibri-run-id"]
            browser_ids = _event_ids(browser_send.text)
            assert browser_ids

            browser_resume = client.get(
                f"/v1/chat/runs/{browser_run_id}/events",
                headers={
                    "Last-Event-ID": str(browser_ids[0]),
                    "Accept": "text/event-stream",
                },
            )
            assert browser_resume.status_code == 200
            assert all(
                sequence > browser_ids[0]
                for sequence in _event_ids(browser_resume.text)
            )

            browser_cancel_without_csrf = client.post(
                f"/v1/chat/runs/{browser_run_id}/cancel",
                headers=ORIGIN,
            )
            assert browser_cancel_without_csrf.status_code == 403
            browser_cancel = client.post(
                f"/v1/chat/runs/{browser_run_id}/cancel",
                headers={**ORIGIN, "X-CSRF-Token": csrf},
            )
            assert browser_cancel.status_code == 204

            browser_logout_without_csrf = client.post(
                "/v1/auth/logout",
                headers=ORIGIN,
            )
            assert browser_logout_without_csrf.status_code == 403
            assert client.get("/v1/session").json()["authenticated"] is True
            browser_logout = client.post(
                "/v1/auth/logout",
                headers={**ORIGIN, "X-CSRF-Token": csrf},
            )
            assert browser_logout.status_code == 200
            assert browser_logout.json() == {
                "authenticated": False,
                "user": None,
            }
            assert client.get("/v1/session").json()["authenticated"] is False
        finally:
            app.state.direct_run_dispatcher = original_dispatcher


def test_native_agui_cors_preflight_is_explicitly_allowlisted(
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path / "product-chat-cors.db"))
    with TestClient(app) as client:
        response = client.options(
            "/v1/chat/ag-ui",
            headers={
                "Origin": "http://testserver",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": (
                    "authorization,content-type,last-event-id"
                ),
            },
        )
        session = client.get(
            "/v1/mobile/auth/session",
            headers={
                "Origin": "http://testserver",
                "Authorization": "Bearer kma_invalid",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "http://testserver"
    )
    allowed_headers = {
        item.strip().casefold()
        for item in response.headers["access-control-allow-headers"].split(",")
    }
    assert {"authorization", "content-type", "last-event-id"} <= allowed_headers
    assert response.headers["access-control-allow-credentials"] == "true"

    exposed_headers = {
        item.strip().casefold()
        for item in session.headers[
            "access-control-expose-headers"
        ].split(",")
    }
    assert {"www-authenticate", "x-kolibri-run-id"} <= exposed_headers
    assert session.headers["www-authenticate"] == "Bearer"
