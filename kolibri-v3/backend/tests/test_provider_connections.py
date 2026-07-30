from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import httpx

from app.config import Settings
from app.database import connect_database
from app.main import create_app
from app.owner_bootstrap import promote_registered_owner
from app.product_run_worker import ProductRunStore
from app.provider_authority import (
    ProviderAuthorityClient,
    ProviderAuthoritySettings,
    decode_and_validate_command,
)
from app.provider_enrollment_worker import ProviderEnrollmentWorker


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"
NONCE = "8c87f2ea-1e95-4b72-a1f5-4836cd76117a"


def _settings(database_path: Path, *, dispatch: bool = True) -> Settings:
    return replace(
        Settings.for_testing(database_url=database_path),
        provider_authority_dispatch_configured=dispatch,
    )


def _register_owner(
    client: TestClient,
    settings: Settings,
) -> dict[str, object]:
    registered = client.post(
        "/v1/auth/register",
        headers=ORIGIN,
        json={
            "email": "owner@example.com",
            "name": "Owner",
            "password": PASSWORD,
        },
    )
    assert registered.status_code == 201
    promote_registered_owner(settings, email="owner@example.com")
    return registered.json()


def _headers(client: TestClient, nonce: str = NONCE) -> dict[str, str]:
    return {
        **ORIGIN,
        "X-CSRF-Token": str(client.cookies.get("kolibri_v3_csrf")),
        "Idempotency-Key": nonce,
    }


def test_owner_creates_secretless_exact_idempotent_intent(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "providers.db"
    settings = _settings(database_path)
    with TestClient(create_app(settings)) as client:
        _register_owner(client, settings)

        assert client.get("/v1/provider-connections").status_code == 200
        without_csrf = client.post(
            "/v1/provider-connections/codex-cli/enrollment-intents",
            headers={**ORIGIN, "Idempotency-Key": NONCE},
        )
        assert without_csrf.status_code == 403
        with_secret_body = client.post(
            "/v1/provider-connections/codex-cli/enrollment-intents",
            headers=_headers(client),
            json={"token": "must-never-enter-product-data"},
        )
        assert with_secret_body.status_code == 400
        assert with_secret_body.json()["code"] == (
            "provider_enrollment_body_forbidden"
        )

        accepted = client.post(
            "/v1/provider-connections/codex-cli/enrollment-intents",
            headers=_headers(client),
        )
        assert accepted.status_code == 202
        assert accepted.json()["provider"]["status"] == "pending"
        replay = client.post(
            "/v1/provider-connections/codex-cli/enrollment-intents",
            headers=_headers(client),
        )
        assert replay.status_code == 202
        assert replay.content == accepted.content

        conflicting_active = client.post(
            "/v1/provider-connections/codex-cli/enrollment-intents",
            headers=_headers(
                client,
                "b0b57ef4-cba0-4878-a347-987d77ed95d6",
            ),
        )
        assert conflicting_active.status_code == 409

    database = sqlite3.connect(database_path)
    database.row_factory = sqlite3.Row
    try:
        intent = database.execute(
            "SELECT * FROM provider_enrollment_intents"
        ).fetchone()
        assert intent is not None
        assert intent["state"] == "queued"
        assert intent["owner_authorization_decision_id"].startswith(
            "decision_"
        )
        assert NONCE not in intent["command_json"]
        assert "must-never-enter-product-data" not in intent["command_json"]
        command = decode_and_validate_command(
            intent["command_json"].encode("utf-8")
        )
        assert (
            command["payload"]["owner_authorization_decision_id"]
            == intent["owner_authorization_decision_id"]
        )
        assert command["payload"]["provider_id"] == "codex-cli"
    finally:
        database.close()


def test_unconfigured_dispatch_records_a_blocked_intent_without_fake_success(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "blocked.db"
    settings = _settings(database_path, dispatch=False)
    with TestClient(create_app(settings)) as client:
        _register_owner(client, settings)
        response = client.post(
            "/v1/provider-connections/mimo-code/enrollment-intents",
            headers=_headers(client),
        )
        assert response.status_code == 202
        assert response.json()["provider"]["status"] == "not_configured"
        listing = client.get("/v1/provider-connections")
        assert listing.json()["authorityConfigured"] is False

    database = sqlite3.connect(database_path)
    try:
        state, code, command_json = database.execute(
            """
            SELECT state, last_error_code, command_json
            FROM provider_enrollment_intents
            """
        ).fetchone()
        assert state == "blocked"
        assert code == "provider_authority_dispatch_not_configured"
        assert json.loads(command_json)["target_owner"] == (
            "provider_execution_authority"
        )
    finally:
        database.close()


def test_worker_sends_exact_body_and_persists_only_sanitized_status(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "worker.db"
    settings = _settings(database_path)
    with TestClient(create_app(settings)) as client:
        _register_owner(client, settings)
        response = client.post(
            "/v1/provider-connections/codex-cli/enrollment-intents",
            headers=_headers(client),
        )
        assert response.status_code == 202

    database = sqlite3.connect(database_path)
    try:
        stored_command = database.execute(
            "SELECT command_json FROM provider_enrollment_intents"
        ).fetchone()[0]
    finally:
        database.close()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.content.decode("utf-8") == stored_command
        assert request.headers["x-kolibri-body-sha256"] == (
            "sha256:" + hashlib.sha256(request.content).hexdigest()
        )
        assert request.headers["x-kolibri-request-nonce"]
        assert request.headers["x-kolibri-request-timestamp"]
        command = json.loads(request.content)
        payload = command["payload"]
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={
                "schema_id": "kolibri.product.provider.enrollment_status",
                "schema_version": "1.0",
                "tenant_id": payload["tenant_id"],
                "intent_id": payload["intent_id"],
                "provider_id": payload["provider_id"],
                "status": "connected",
                "auth_flow_supported": False,
                "last_verified_at": "2026-07-28T12:00:00Z",
                "error": None,
            },
        )

    authority = ProviderAuthorityClient(
        ProviderAuthoritySettings(
            command_url=(
                "http://127.0.0.1:18445"
                "/v1/runtime/product-provider-enrollment-intents"
            ),
            bearer_token="a" * 32,
            identity_hmac_key="b" * 32,
        ),
        transport=httpx.MockTransport(handler),
    )
    worker = ProviderEnrollmentWorker(
        database_url=settings.database_url,
        settings=settings,
        authority=authority,
    )
    assert worker.run_once() is True

    database = sqlite3.connect(database_path)
    try:
        connection = database.execute(
            """
            SELECT status, last_verified_at, last_evidence_hash
            FROM provider_connections
            WHERE provider_id = 'codex-cli'
            """
        ).fetchone()
        assert connection[0] == "connected"
        assert connection[1] == "2026-07-28T12:00:00Z"
        assert connection[2].startswith("sha256:")
        intent = database.execute(
            """
            SELECT state, authority_status, authority_response_hash
            FROM provider_enrollment_intents
            """
        ).fetchone()
        assert intent[0:2] == ("completed", "connected")
        assert intent[2].startswith("sha256:")
        stored = database.execute(
            "SELECT command_json, api_response_json FROM provider_enrollment_intents"
        ).fetchone()
        assert "authorizationUrl" not in stored[0] + stored[1]
        assert "token" not in stored[1].lower()
    finally:
        database.close()


def test_run_evidence_updates_projection_but_infrastructure_is_not_auth_failure(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "run-evidence.db")
    with TestClient(create_app(settings)) as client:
        owner = _register_owner(client, settings)
    database = connect_database(settings.database_url)
    try:
        ProductRunStore._record_provider_execution_projection(
            database,
            tenant_id=str(owner["user"]["tenantId"]),
            profile="mimo-code",
            status="connected",
            now_text="2026-07-28T12:00:00+00:00",
            evidence_hash="sha256:" + ("a" * 64),
        )
        row = database.execute(
            """
            SELECT status, last_evidence_hash
            FROM provider_connections
            WHERE provider_id = 'mimo-code'
            """
        ).fetchone()
        assert tuple(row) == ("connected", "sha256:" + ("a" * 64))
        assert (
            ProductRunStore._is_provider_auth_or_policy_failure(
                "logical_home_unavailable"
            )
            is False
        )
        assert (
            ProductRunStore._is_provider_auth_or_policy_failure(
                "runner_auth_blocked"
            )
            is True
        )
    finally:
        database.close()
