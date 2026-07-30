from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent_runtime import (
    AgentRuntimeCapabilities,
    AgentRuntimeDescriptor,
    AgentRuntimeResult,
    DelegatingAgentRuntime,
)
from app.config import Settings
from app.database import connect_database, initialize_database, migration_paths
from app.main import create_app
from app.owner_bootstrap import promote_registered_owner


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"
DIGEST = "sha256:" + ("a" * 64)
SECRET_PROMPT = "SUPER_SECRET_PROMPT"
SECRET_TOKEN = "sk-live-do-not-leak"
PRIVATE_PATH = "/srv/private/owner-repository"


def _register(client: TestClient, email: str, name: str) -> dict[str, object]:
    response = client.post(
        "/v1/auth/register",
        headers=ORIGIN,
        json={"email": email, "name": name, "password": PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["user"]


def _logout(client: TestClient) -> None:
    csrf = str(client.cookies.get("kolibri_v3_csrf"))
    response = client.post(
        "/v1/auth/logout",
        headers={**ORIGIN, "X-CSRF-Token": csrf},
    )
    assert response.status_code == 200


def _seed_run(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str,
    suffix: str,
    run_id: str,
    created_at: str,
    status: str = "running",
    with_context: bool = False,
    with_outbox: bool = False,
    unsafe_values: bool = False,
) -> None:
    project_id = f"project-{suffix}"
    thread_id = f"thread-{suffix}"
    message_id = f"message-{suffix}"
    database.execute(
        """
        INSERT INTO projects (
            tenant_id, id, created_by_user_id, title, status,
            primary_thread_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
        """,
        (
            tenant_id,
            project_id,
            user_id,
            f"Project {suffix}",
            thread_id,
            created_at,
            created_at,
        ),
    )
    database.execute(
        """
        INSERT INTO chat_threads (
            tenant_id, id, project_id, kind, title, status,
            message_count, run_count, created_at, updated_at
        ) VALUES (?, ?, ?, 'primary', ?, 'regular', 1, 1, ?, ?)
        """,
        (
            tenant_id,
            thread_id,
            project_id,
            f"Thread {suffix}",
            created_at,
            created_at,
        ),
    )
    database.execute(
        """
        INSERT INTO chat_messages (
            tenant_id, id, project_id, thread_id, sequence,
            client_message_id, role, content_text,
            created_by_user_id, created_at
        ) VALUES (?, ?, ?, ?, 1, ?, 'user', ?, ?, ?)
        """,
        (
            tenant_id,
            message_id,
            project_id,
            thread_id,
            f"client-message-{suffix}",
            SECRET_PROMPT if unsafe_values else "Ordinary prompt",
            user_id,
            created_at,
        ),
    )
    database.execute(
        """
        INSERT INTO chat_runs (
            tenant_id, id, project_id, thread_id, client_run_id,
            request_hash, input_message_id, requested_by_user_id,
            selected_profile, status, last_event_sequence, error_code,
            heartbeat_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'codex-cli', ?, 3, ?, ?, ?, ?)
        """,
        (
            tenant_id,
            run_id,
            project_id,
            thread_id,
            f"client-run-{suffix}",
            DIGEST,
            message_id,
            user_id,
            status,
            SECRET_TOKEN if unsafe_values else None,
            created_at,
            created_at,
            created_at,
        ),
    )
    if with_context:
        database.execute(
            """
            INSERT INTO chat_run_execution_contexts (
                tenant_id, run_id, execution_mode, execution_plane,
                platform_authority_epoch, access_mode, access_policy_version,
                authority_role, authority_user_id, workspace_ref,
                sandbox_profile, approval_policy, approvals_reviewer,
                model_id, reasoning_effort, service_tier, created_at
            ) VALUES (
                ?, ?, 'developer', 'home', 1, 'full', 2, 'owner', ?,
                'repository', 'danger-full-access', 'never', NULL, ?,
                'high', 'priority', ?
            )
            """,
            (
                tenant_id,
                run_id,
                user_id,
                f"{PRIVATE_PATH}/model" if unsafe_values else "gpt-5.6-sol",
                created_at,
            ),
        )
    if with_outbox:
        database.execute(
            """
            INSERT INTO product_run_outbox (
                tenant_id, id, run_id, command_kind, phase, state,
                command_json, command_hash, attempts, max_attempts,
                available_at, fencing_token, last_error_code,
                created_at, updated_at
            ) VALUES (
                ?, ?, ?, 'product.run.execute', 'run_execute', 'retry',
                ?, ?, 2, 8, ?, 0, ?, ?, ?
            )
            """,
            (
                tenant_id,
                f"outbox-{suffix}",
                run_id,
                json.dumps(
                    {
                        "prompt": SECRET_PROMPT,
                        "credential": SECRET_TOKEN,
                        "workspaceRoot": PRIVATE_PATH,
                        "command": "rm -rf hidden",
                    }
                ),
                DIGEST,
                created_at,
                SECRET_TOKEN,
                created_at,
                created_at,
            ),
        )


def _register_runtime(client: TestClient) -> None:
    runtime = DelegatingAgentRuntime(
        descriptor=AgentRuntimeDescriptor(
            profile_id="ops-runtime",
            runtime_id="ops-runtime-process",
            display_name="Operations runtime",
            capabilities=AgentRuntimeCapabilities(
                modes=frozenset({"chat", "developer"}),
                streaming=True,
                structured_output=False,
                activity_events=True,
                persistent_sessions=True,
            ),
        ),
        execute=lambda _request: AgentRuntimeResult(text="unused"),
    )
    client.app.state.agent_runtime_registry.register(runtime)


def test_agent_operations_is_owner_capability_gated_paginated_and_redacted(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "agent-operations.db"
    settings = Settings.for_testing(database_url=database_path)
    app = create_app(settings)

    with TestClient(app) as owner_client:
        customer = _register(
            owner_client,
            "customer@example.com",
            "Customer",
        )
        _logout(owner_client)
        role_owner = _register(
            owner_client,
            "tenant-owner@example.com",
            "Tenant owner",
        )
        _logout(owner_client)
        owner = _register(owner_client, "owner@example.com", "Owner")
        promote_registered_owner(settings, email="owner@example.com")
        _register_runtime(owner_client)

        database = connect_database(database_path)
        try:
            database.execute(
                """
                UPDATE users
                SET role = 'owner'
                WHERE id = ? AND tenant_id = ?
                """,
                (role_owner["id"], role_owner["tenantId"]),
            )
            _seed_run(
                database,
                tenant_id=str(owner["tenantId"]),
                user_id=str(owner["id"]),
                suffix="owner-shared",
                run_id="run-shared",
                created_at="2026-07-30T12:00:00+00:00",
                with_context=True,
                with_outbox=True,
                unsafe_values=True,
            )
            _seed_run(
                database,
                tenant_id=str(customer["tenantId"]),
                user_id=str(customer["id"]),
                suffix="customer-shared",
                run_id="run-shared",
                created_at="2026-07-30T12:00:00+00:00",
                status="succeeded",
            )
            _seed_run(
                database,
                tenant_id=str(customer["tenantId"]),
                user_id=str(customer["id"]),
                suffix="customer-optional",
                run_id="run-optional",
                created_at="2026-07-30T11:59:00+00:00",
            )
            database.execute(
                """
                INSERT INTO provider_connections (
                    tenant_id, provider_id, status, auth_flow_supported,
                    authority_observed, last_error_code, created_at, updated_at
                ) VALUES (?, 'codex-cli', 'error', 1, 0, ?, ?, ?)
                """,
                (
                    owner["tenantId"],
                    SECRET_TOKEN,
                    "2026-07-30T12:00:00+00:00",
                    "2026-07-30T12:00:00+00:00",
                ),
            )
        finally:
            database.close()

        page_cursor = None
        seen: set[tuple[str, str]] = set()
        pages: list[dict[str, object]] = []
        while True:
            response = owner_client.get(
                "/v1/platform-admin/agent-operations",
                params={
                    "limit": 1,
                    **({"cursor": page_cursor} if page_cursor else {}),
                },
            )
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            payload = response.json()
            pages.append(payload)
            [item] = payload["items"]
            key = (item["task"]["tenantId"], item["task"]["runId"])
            assert key not in seen
            seen.add(key)
            page_cursor = payload["nextCursor"]
            if page_cursor is None:
                break

        assert seen == {
            (str(owner["tenantId"]), "run-shared"),
            (str(customer["tenantId"]), "run-shared"),
            (str(customer["tenantId"]), "run-optional"),
        }
        all_items = [
            item
            for page in pages
            for item in page["items"]
        ]
        optional = next(
            item for item in all_items if item["task"]["runId"] == "run-optional"
        )
        assert optional["frozenPolicy"] is None
        assert optional["dispatch"] is None

        unsafe = next(
            item
            for item in all_items
            if item["task"]["tenantId"] == owner["tenantId"]
        )
        assert unsafe["errorCode"] is None
        assert unsafe["errorRedacted"] is True
        assert unsafe["frozenPolicy"]["modelId"] is None
        assert unsafe["frozenPolicy"]["modelIdRedacted"] is True
        assert unsafe["frozenPolicy"]["executionPlane"] == "home"
        assert unsafe["frozenPolicy"]["trustedAgentProfileId"] is None
        assert unsafe["frozenPolicy"]["trustedAgentProfileEpoch"] is None
        assert (
            unsafe["frozenPolicy"]["trustedAgentWorkspaceBindingId"] is None
        )
        assert (
            unsafe["frozenPolicy"]["trustedAgentWorkspaceBindingEpoch"]
            is None
        )
        assert unsafe["dispatch"]["state"] == "retry"
        assert unsafe["dispatch"]["lastErrorCode"] is None
        assert unsafe["dispatch"]["lastErrorRedacted"] is True

        first_payload = pages[0]
        assert first_payload["availability"]["runtimes"] == [
            {
                "profileId": "ops-runtime",
                "runtimeId": "ops-runtime-process",
                "displayName": "Operations runtime",
                "registered": True,
                "startupStatus": "no_error_recorded",
                "modes": ["chat", "developer"],
                "streaming": True,
                "structuredOutput": False,
                "activityEvents": True,
                "persistentSessions": True,
                "modelCatalog": False,
            }
        ]
        [provider] = first_payload["availability"]["providers"]
        assert provider["status"] == "error"
        assert provider["lastErrorCode"] is None
        assert provider["lastErrorRedacted"] is True

        serialized = json.dumps(pages, ensure_ascii=False)
        for forbidden in (
            SECRET_PROMPT,
            SECRET_TOKEN,
            PRIVATE_PATH,
            "rm -rf",
            "command_json",
            "request_hash",
            "lease_token",
        ):
            assert forbidden not in serialized

        isolated = owner_client.get(
            "/v1/platform-admin/agent-operations",
            params={"tenantId": customer["tenantId"], "limit": 100},
        )
        assert isolated.status_code == 200
        assert {
            item["task"]["tenantId"]
            for item in isolated.json()["items"]
        } == {customer["tenantId"]}
        assert {
            provider["tenantId"]
            for provider in isolated.json()["availability"]["providers"]
        } == set()

        succeeded = owner_client.get(
            "/v1/platform-admin/agent-operations",
            params={"status": "succeeded"},
        )
        assert succeeded.status_code == 200
        assert [item["status"] for item in succeeded.json()["items"]] == [
            "succeeded"
        ]

        invalid_cursor = owner_client.get(
            "/v1/platform-admin/agent-operations",
            params={"cursor": "not+base64"},
        )
        assert invalid_cursor.status_code == 400
        assert invalid_cursor.json()["code"] == "invalid_cursor"

        with TestClient(app) as role_owner_client:
            login = role_owner_client.post(
                "/v1/auth/login",
                headers=ORIGIN,
                json={
                    "email": "tenant-owner@example.com",
                    "password": PASSWORD,
                },
            )
            assert login.status_code == 200
            session = role_owner_client.get("/v1/session").json()["user"]
            assert session["role"] == "owner"
            assert session["isPlatformOwner"] is False
            denied = role_owner_client.get(
                "/v1/platform-admin/agent-operations"
            )
            assert denied.status_code == 403
            assert denied.json()["code"] == "platform_audit_required"

        database = connect_database(database_path)
        try:
            database.execute(
                """
                UPDATE platform_authority_grants
                SET capabilities_json = json_remove(
                    capabilities_json,
                    (
                        SELECT fullkey
                        FROM json_tree(capabilities_json)
                        WHERE value = 'platform.audit.read'
                        LIMIT 1
                    )
                )
                WHERE authority_id = 'platform_owner'
                """
            )
        finally:
            database.close()
        denied_without_capability = owner_client.get(
            "/v1/platform-admin/agent-operations"
        )
        assert denied_without_capability.status_code == 403
        assert (
            denied_without_capability.json()["code"]
            == "platform_audit_required"
        )


def test_migration_035_upgrades_an_existing_platform_grant_once(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "platform-audit-upgrade.db"
    database = sqlite3.connect(database_path, isolation_level=None)
    try:
        database.execute("PRAGMA foreign_keys = ON")
        for migration in migration_paths():
            version = int(migration.name.split("_", 1)[0])
            if version > 34:
                break
            database.executescript(migration.read_text(encoding="utf-8"))
        database.execute(
            """
            INSERT INTO tenants (id, name, created_at)
            VALUES ('tenant-owner', 'Owner tenant', 1)
            """
        )
        database.execute(
            """
            INSERT INTO users (
                id, tenant_id, email_normalized, email, name, role,
                preferred_agent_profile, password_hash, created_at, updated_at
            ) VALUES (
                'user-owner', 'tenant-owner', 'owner@example.com',
                'owner@example.com', 'Owner', 'owner', 'auto',
                'password-hash', 1, 1
            )
            """
        )
        database.execute(
            """
            INSERT INTO platform_authority_grants (
                authority_id, user_id, tenant_id, active, authority_epoch,
                capabilities_json, created_at, updated_at
            ) VALUES (
                'platform_owner', 'user-owner', 'tenant-owner', 1, 1,
                '["platform.admin","chat.use"]', 1, 1
            )
            """
        )
        # Pause at the exact predecessor; this is not a "latest" assertion.
        assert database.execute("PRAGMA user_version").fetchone()[0] == 34
    finally:
        database.close()

    initialize_database(database_path)
    database = sqlite3.connect(database_path)
    try:
        [capabilities_json] = database.execute(
            """
            SELECT capabilities_json
            FROM platform_authority_grants
            WHERE authority_id = 'platform_owner'
            """
        ).fetchone()
        capabilities = json.loads(capabilities_json)
        assert capabilities.count("platform.audit.read") == 1
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
        assert database.execute("PRAGMA user_version").fetchone()[0] >= 35
    finally:
        database.close()
