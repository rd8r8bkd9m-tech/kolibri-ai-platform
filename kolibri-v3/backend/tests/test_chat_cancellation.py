from __future__ import annotations

import json
from pathlib import Path

from fastapi import Request
from fastapi.testclient import TestClient

from app.chat.cancellation import (
    ActiveRunCancellationRegistry,
    cancel_run,
)
from app.chat.execution_adapter import prepare_chat_execution
from app.chat.models import AgUiRunInput
from app.chat.service import accept_run
from app.config import Settings
from app.database import connect_database
from app.main import create_app
from app.schemas import AgentProfile, UserRole, UserSession


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"


def _run_input() -> AgUiRunInput:
    return AgUiRunInput.model_validate(
        {
            "threadId": "thread_cancel_contract_01",
            "runId": "run_cancel_contract_01",
            "state": None,
            "messages": [
                {
                    "id": "message_cancel_contract_01",
                    "role": "user",
                    "content": "Выполни долгую задачу, которую можно остановить.",
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
    )


def test_active_run_cancellation_registry_is_exact_and_idempotent() -> None:
    registry = ActiveRunCancellationRegistry()
    first = registry.register("tenant-a", "run-a")
    replacement = registry.register("tenant-a", "run-a")

    assert first.is_set()
    assert not replacement.is_set()
    assert not registry.cancel("tenant-a", "run-other")
    assert registry.cancel("tenant-a", "run-a")
    assert replacement.is_set()

    registry.unregister("tenant-a", "run-a", first)
    assert registry.cancel("tenant-a", "run-a")
    registry.unregister("tenant-a", "run-a", replacement)
    assert not registry.cancel("tenant-a", "run-a")


def test_cancel_endpoint_terminalizes_owned_run_and_fences_outbox(
    tmp_path: Path,
) -> None:
    settings = Settings.for_testing(database_url=tmp_path / "cancel.db")
    app = create_app(settings)
    with TestClient(app) as client:
        registered = client.post(
            "/v1/auth/register",
            headers=ORIGIN,
            json={
                "email": "cancel@example.com",
                "name": "Cancel User",
                "password": PASSWORD,
            },
        )
        assert registered.status_code == 201
        user = registered.json()["user"]
        csrf = client.cookies.get("kolibri_v3_csrf")
        assert csrf

        identity = UserSession(
            user_id=user["id"],
            tenant_id=user["tenantId"],
            role=UserRole.USER,
            preferred_agent_profile=AgentProfile.AUTO,
            email=user["email"],
            name=user["name"],
            platform_capabilities=("chat.use",),
        )
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/v1/chat/ag-ui",
                "headers": [],
                "app": app,
            }
        )
        database = connect_database(settings.database_url)
        try:
            run_input = _run_input()
            prepared = prepare_chat_execution(
                request,
                database,
                settings=settings,
                identity=identity,
                run_input=run_input,
            )
            accepted = accept_run(
                database,
                settings=settings,
                identity=identity,
                run_input=run_input,
                prepared=prepared,
            )
            database.execute(
                """
                UPDATE product_run_outbox
                SET state = 'leased',
                    lease_owner = 'worker-a',
                    lease_token = 'lease-a',
                    lease_until = '2099-01-01T00:00:00+00:00',
                    fencing_token = 7
                WHERE tenant_id = ? AND run_id = ?
                """,
                (identity.tenant_id, accepted.run_id),
            )
            database.commit()
        finally:
            database.close()

        response = client.post(
            f"/v1/chat/runs/{accepted.run_id}/cancel",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
        )
        assert response.status_code == 204

        database = connect_database(settings.database_url)
        try:
            run = database.execute(
                """
                SELECT status, outcome, error_code, last_event_sequence
                FROM chat_runs
                WHERE tenant_id = ? AND id = ?
                """,
                (identity.tenant_id, accepted.run_id),
            ).fetchone()
            assert run is not None
            assert dict(run) == {
                "status": "failed",
                "outcome": "failure",
                "error_code": "run_cancelled",
                "last_event_sequence": 2,
            }

            outbox = database.execute(
                """
                SELECT state, lease_owner, lease_token, lease_until,
                       fencing_token, last_error_code
                FROM product_run_outbox
                WHERE tenant_id = ? AND run_id = ?
                """,
                (identity.tenant_id, accepted.run_id),
            ).fetchone()
            assert outbox is not None
            assert dict(outbox) == {
                "state": "blocked",
                "lease_owner": None,
                "lease_token": None,
                "lease_until": None,
                "fencing_token": 8,
                "last_error_code": "run_cancelled",
            }

            event = database.execute(
                """
                SELECT event_type, event_json
                FROM chat_run_events
                WHERE tenant_id = ? AND run_id = ? AND sequence = 2
                """,
                (identity.tenant_id, accepted.run_id),
            ).fetchone()
            assert event is not None
            assert event["event_type"] == "RUN_ERROR"
            assert json.loads(event["event_json"]) == {
                "type": "RUN_ERROR",
                "code": "run_cancelled",
                "message": "Задача остановлена пользователем.",
            }

            assert (
                cancel_run(
                    database,
                    tenant_id=identity.tenant_id,
                    user_id="another-user",
                    run_id=accepted.run_id,
                )
                is None
            )
        finally:
            database.close()

        replay = client.post(
            f"/v1/chat/runs/{accepted.run_id}/cancel",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
        )
        assert replay.status_code == 204

        database = connect_database(settings.database_url)
        try:
            event_count = database.execute(
                """
                SELECT COUNT(*)
                FROM chat_run_events
                WHERE tenant_id = ? AND run_id = ?
                  AND event_type = 'RUN_ERROR'
                """,
                (identity.tenant_id, accepted.run_id),
            ).fetchone()[0]
            assert event_count == 1
        finally:
            database.close()
