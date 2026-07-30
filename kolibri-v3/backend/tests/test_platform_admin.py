from __future__ import annotations

from dataclasses import replace
import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.chat.errors import ChatPolicyError
from app.chat.execution_adapter import PreparedChatExecution
from app.chat.models import AgUiRunInput
from app.chat.service import accept_run
from app.config import Settings
from app.database import connect_database, migration_paths
from app.main import create_app
from app.owner_bootstrap import promote_registered_owner
from app.platform_admin import (
    PlatformPolicyError,
    enforce_chat_access_policy,
)
from app.schemas import AgentProfile, UserRole, UserSession


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"


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


def test_platform_owner_controls_all_tenants_without_exposing_secrets(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "platform-admin.db"
    settings = Settings.for_testing(database_url=database_path)
    app = create_app(settings)

    with TestClient(app) as owner_client:
        regular = _register(
            owner_client,
            "customer@example.com",
            "Customer",
        )
        _logout(owner_client)
        owner = _register(owner_client, "owner@example.com", "Owner")
        promote_registered_owner(settings, email="owner@example.com")
        session = owner_client.get("/v1/session")
        assert session.status_code == 200
        assert session.json()["user"]["isPlatformOwner"] is True
        assert "platform.admin" in session.json()["user"]["capabilities"]
        csrf = str(owner_client.cookies.get("kolibri_v3_csrf"))
        mutation_headers = {**ORIGIN, "X-CSRF-Token": csrf}

        tenants = owner_client.get("/v1/platform-admin/tenants?limit=100")
        assert tenants.status_code == 200
        assert {item["id"] for item in tenants.json()["items"]} == {
            regular["tenantId"],
            owner["tenantId"],
        }
        users = owner_client.get("/v1/platform-admin/users?limit=100")
        assert users.status_code == 200
        serialized = users.text
        assert "password_hash" not in serialized
        assert "token_hash" not in serialized
        assert PASSWORD not in serialized
        customer = next(
            item
            for item in users.json()["items"]
            if item["id"] == regular["id"]
        )

        with TestClient(app) as customer_client:
            logged_in = customer_client.post(
                "/v1/auth/login",
                headers=ORIGIN,
                json={
                    "email": "customer@example.com",
                    "password": PASSWORD,
                },
            )
            assert logged_in.status_code == 200
            assert (
                customer_client.get("/v1/platform-admin/tenants").status_code
                == 403
            )

            blocked = owner_client.patch(
                f"/v1/platform-admin/users/{regular['id']}",
                headers=mutation_headers,
                json={
                    "revision": customer["control"]["revision"],
                    "accessStatus": "blocked",
                    "blockReason": "security review",
                },
            )
            assert blocked.status_code == 200
            assert blocked.json()["control"]["accessStatus"] == "blocked"
            assert (
                customer_client.get("/v1/session").json()["authenticated"]
                is False
            )
            denied_login = customer_client.post(
                "/v1/auth/login",
                headers=ORIGIN,
                json={
                    "email": "customer@example.com",
                    "password": PASSWORD,
                },
            )
            assert denied_login.status_code == 423
            assert denied_login.json()["code"] == "user_blocked"

        owner_tenant = next(
            item
            for item in tenants.json()["items"]
            if item["id"] == owner["tenantId"]
        )
        protected = owner_client.patch(
            f"/v1/platform-admin/tenants/{owner['tenantId']}",
            headers=mutation_headers,
            json={
                "revision": owner_tenant["policy"]["revision"],
                "lifecycleStatus": "suspended",
                "blockReason": "must be rejected",
            },
        )
        assert protected.status_code == 409
        assert protected.json()["code"] == "platform_owner_tenant_protected"

        customer_tenant = next(
            item
            for item in tenants.json()["items"]
            if item["id"] == regular["tenantId"]
        )
        updated = owner_client.patch(
            f"/v1/platform-admin/tenants/{regular['tenantId']}",
            headers=mutation_headers,
            json={
                "revision": customer_tenant["policy"]["revision"],
                "planCode": "pro",
                "monthlyRunLimit": 250,
                "developerAccessEnabled": False,
                "allowedModelIds": ["gpt-5.6-sol"],
                "allowedProviderIds": ["codex-cli"],
            },
        )
        assert updated.status_code == 200
        assert updated.json()["policy"]["planCode"] == "pro"
        assert updated.json()["policy"]["monthlyRunLimit"] == 250
        assert updated.json()["policy"]["allowedModelIds"] == ["gpt-5.6-sol"]

        stale = owner_client.patch(
            f"/v1/platform-admin/tenants/{regular['tenantId']}",
            headers=mutation_headers,
            json={
                "revision": customer_tenant["policy"]["revision"],
                "planCode": "enterprise",
            },
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "revision_conflict"

        audit = owner_client.get("/v1/platform-admin/audit?limit=100")
        assert audit.status_code == 200
        actions = {item["action"] for item in audit.json()["items"]}
        assert actions == {
            "policy.owner_bootstrap",
            "tenant.policy.updated",
            "user.control.updated",
        }
        assert PASSWORD not in audit.text

        tenant_page_one = owner_client.get(
            "/v1/platform-admin/tenants?limit=1"
        ).json()
        tenant_page_two = owner_client.get(
            "/v1/platform-admin/tenants",
            params={"limit": 1, "cursor": tenant_page_one["nextCursor"]},
        ).json()
        assert tenant_page_one["nextCursor"] is not None
        assert {
            tenant_page_one["items"][0]["id"],
            tenant_page_two["items"][0]["id"],
        } == {regular["tenantId"], owner["tenantId"]}

        user_page_one = owner_client.get(
            "/v1/platform-admin/users?limit=1"
        ).json()
        user_page_two = owner_client.get(
            "/v1/platform-admin/users",
            params={"limit": 1, "cursor": user_page_one["nextCursor"]},
        ).json()
        assert user_page_one["items"][0]["id"] != (
            user_page_two["items"][0]["id"]
        )

        audit_page_one = owner_client.get(
            "/v1/platform-admin/audit?limit=1"
        ).json()
        assert ":" in audit_page_one["nextCursor"]
        audit_page_two = owner_client.get(
            "/v1/platform-admin/audit",
            params={"limit": 1, "cursor": audit_page_one["nextCursor"]},
        ).json()
        assert audit_page_one["items"][0]["id"] != (
            audit_page_two["items"][0]["id"]
        )

    database = sqlite3.connect(database_path)
    try:
        latest_version = int(
            migration_paths()[-1].name.split("_", 1)[0]
        )
        assert (
            database.execute("PRAGMA user_version").fetchone()[0]
            == latest_version
        )
        assert (
            database.execute(
                "SELECT COUNT(*) FROM platform_admin_audit_events"
            ).fetchone()[0]
            == 3
        )
    finally:
        database.close()


def test_platform_admin_mutations_require_csrf_and_bounded_unique_ids(
    tmp_path: Path,
) -> None:
    settings = Settings.for_testing(database_url=tmp_path / "admin-csrf.db")
    with TestClient(create_app(settings)) as client:
        owner = _register(client, "owner@example.com", "Owner")
        promote_registered_owner(settings, email="owner@example.com")
        [tenant] = client.get("/v1/platform-admin/tenants").json()["items"]

        no_csrf = client.patch(
            f"/v1/platform-admin/tenants/{owner['tenantId']}",
            headers=ORIGIN,
            json={
                "revision": tenant["policy"]["revision"],
                "planCode": "pro",
            },
        )
        assert no_csrf.status_code == 403

        csrf = str(client.cookies.get("kolibri_v3_csrf"))
        duplicate = client.patch(
            f"/v1/platform-admin/tenants/{owner['tenantId']}",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={
                "revision": tenant["policy"]["revision"],
                "allowedModelIds": ["gpt-5.6-sol", "gpt-5.6-sol"],
            },
        )
        assert duplicate.status_code == 422


def test_legacy_owner_role_does_not_grant_platform_or_developer_authority(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "role-is-not-authority.db"
    settings = replace(
        Settings.for_testing(database_url=database_path),
        direct_model_runtime_enabled=True,
        developer_agent_enabled=True,
        developer_workspace_root=tmp_path,
    )
    with TestClient(create_app(settings)) as client:
        user = _register(client, "role-owner@example.com", "Role owner")
        database = connect_database(database_path)
        try:
            database.execute(
                """
                UPDATE users
                SET role = 'owner'
                WHERE id = ? AND tenant_id = ?
                """,
                (user["id"], user["tenantId"]),
            )
            database.execute(
                """
                UPDATE platform_tenant_policies
                SET developer_access_enabled = 1,
                    allowed_model_ids_json = '["gpt-5.6-sol"]',
                    allowed_provider_ids_json = '["codex-cli"]'
                WHERE tenant_id = ?
                """,
                (user["tenantId"],),
            )
            database.execute(
                """
                UPDATE platform_user_controls
                SET developer_access = 'allow'
                WHERE user_id = ? AND tenant_id = ?
                """,
                (user["id"], user["tenantId"]),
            )
        finally:
            database.close()

        session_user = client.get("/v1/session").json()["user"]
        assert session_user["role"] == "owner"
        assert session_user["isPlatformOwner"] is False
        assert session_user["capabilities"] == ["chat.use"]
        assert client.get("/v1/platform-admin/tenants").status_code == 403

        csrf = str(client.cookies.get("kolibri_v3_csrf"))
        denied = client.post(
            "/v1/chat/ag-ui",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={
                "threadId": "thread_role_owner_01",
                "runId": "run_role_owner_01",
                "state": None,
                "messages": [
                    {
                        "id": "message_role_owner_01",
                        "role": "user",
                        "content": "Проверь репозиторий.",
                    }
                ],
                "tools": [],
                "context": [],
                "forwardedProps": {
                    "agentProfile": "mimo-code",
                    "executionMode": "developer",
                    "accessMode": "auto",
                },
            },
        )
        assert denied.status_code == 403
        assert denied.json()["code"] == "owner_required"


def test_chat_policy_requires_concrete_model_for_model_allowlist(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "model-policy.db"
    settings = Settings.for_testing(database_url=database_path)
    with TestClient(create_app(settings)) as client:
        user = _register(client, "model-policy@example.com", "Model policy")

    database = connect_database(database_path)
    try:
        database.execute(
            """
            UPDATE platform_tenant_policies
            SET allowed_model_ids_json = ?
            WHERE tenant_id = ?
            """,
            (
                json.dumps(["gpt-5.6-sol"], separators=(",", ":")),
                user["tenantId"],
            ),
        )
        identity = UserSession(
            user_id=str(user["id"]),
            tenant_id=str(user["tenantId"]),
            role=UserRole.USER,
            preferred_agent_profile=AgentProfile.AUTO,
            email="model-policy@example.com",
            name="Model policy",
        )
        with pytest.raises(PlatformPolicyError) as error:
            enforce_chat_access_policy(
                database,
                identity=identity,
                execution_mode="standard",
                runtime_profile="mimo-code",
                model_id=None,
            )
        assert error.value.status_code == 422
        assert error.value.code == "concrete_model_required"
    finally:
        database.close()


def test_monthly_run_limit_allows_exact_idempotent_replay(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "quota-replay.db"
    settings = replace(
        Settings.for_testing(database_url=database_path),
        direct_model_runtime_enabled=True,
    )
    with TestClient(create_app(settings)) as client:
        user = _register(client, "quota@example.com", "Quota user")

    identity = UserSession(
        user_id=str(user["id"]),
        tenant_id=str(user["tenantId"]),
        role=UserRole.USER,
        preferred_agent_profile=AgentProfile.AUTO,
        email="quota@example.com",
        name="Quota user",
    )
    run_input = AgUiRunInput.model_validate(
        {
            "threadId": "thread_quota_replay_01",
            "runId": "run_quota_replay_01",
            "state": None,
            "messages": [
                {
                    "id": "message_quota_replay_01",
                    "role": "user",
                    "content": "Ответь кратко.",
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
    prepared = PreparedChatExecution(
        execution_plane="direct",
        runtime_profile="auto",
        model_id=None,
        reasoning_effort=None,
        service_tier=None,
    )
    database = connect_database(database_path)
    try:
        database.execute(
            """
            UPDATE platform_tenant_policies
            SET monthly_run_limit = 1
            WHERE tenant_id = ?
            """,
            (identity.tenant_id,),
        )
        first = accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=run_input,
            prepared=prepared,
        )
        replay = accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=run_input,
            prepared=prepared,
        )
        assert replay.run_id == first.run_id
        assert replay.replayed is True

        changed = run_input.model_copy(
            update={"run_id": "run_quota_replay_02"}
        )
        with pytest.raises(ChatPolicyError) as error:
            accept_run(
                database,
                settings=settings,
                identity=identity,
                run_input=changed,
                prepared=prepared,
            )
        assert error.value.status_code == 429
        assert error.value.code == "monthly_run_limit_reached"
    finally:
        database.close()
