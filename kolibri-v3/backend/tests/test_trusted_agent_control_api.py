from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.owner_bootstrap import promote_registered_owner


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"
FINGERPRINT_A = f"sha256:{'a' * 64}"
FINGERPRINT_B = f"sha256:{'b' * 64}"
PROFILE = {
    "displayName": "Primary trusted agent",
    "runtimeProfile": "codex-cli",
    "agentCardId": "codex-cli.primary",
    "agentCardVersion": 1,
}
DEVICE = {
    "platform": "ios",
    "deviceName": "Trusted iPhone",
    "appVersion": "1.0.0",
}


def _register(
    client: TestClient,
    *,
    email: str,
    name: str,
) -> dict[str, object]:
    response = client.post(
        "/v1/auth/register",
        headers=ORIGIN,
        json={
            "email": email,
            "name": name,
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]


def _owner_headers(client: TestClient) -> dict[str, str]:
    return {
        **ORIGIN,
        "X-CSRF-Token": str(client.cookies.get("kolibri_v3_csrf")),
    }


def _promote(
    settings: Settings,
    client: TestClient,
    *,
    email: str,
) -> None:
    promote_registered_owner(settings, email=email)
    session = client.get("/v1/session")
    assert session.status_code == 200
    assert session.json()["user"]["isPlatformOwner"] is True


def _create_binding(
    client: TestClient,
    *,
    headers: dict[str, str],
    fingerprint: str = FINGERPRINT_A,
) -> dict[str, object]:
    response = client.post(
        "/v1/platform-admin/trusted-agents/workspace-bindings",
        headers=headers,
        json={
            "environment": "development",
            "fingerprintToken": fingerprint,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_profile(
    client: TestClient,
    *,
    headers: dict[str, str],
    binding_id: object,
) -> dict[str, object]:
    response = client.post(
        "/v1/platform-admin/trusted-agents/profiles",
        headers=headers,
        json={"workspaceBindingId": binding_id, **PROFILE},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_tenant_owner_role_without_singleton_grant_cannot_read_control_plane(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "role-owner-denied.db"
    settings = Settings.for_testing(
        database_url=database_path,
        bootstrap_owner_email=None,
    )
    with TestClient(create_app(settings)) as client:
        user = _register(
            client,
            email="role-owner@example.com",
            name="Role owner only",
        )
        database = sqlite3.connect(database_path)
        try:
            database.execute(
                "UPDATE users SET role = 'owner' WHERE id = ?",
                (user["id"],),
            )
            database.commit()
        finally:
            database.close()

        denied = client.get(
            "/v1/platform-admin/trusted-agents/workspace-bindings"
        )
        assert denied.status_code == 403
        assert denied.json()["code"] == "owner_required"


def test_mutations_require_csrf_recent_auth_and_never_accept_paths_or_secrets(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "trusted-agent-security.db"
    settings = Settings.for_testing(
        database_url=database_path,
        bootstrap_owner_email=None,
    )
    secret_marker = "raw-secret-marker-must-not-persist"
    path_marker = "/private/srv/kolibri-secret-workspace"
    with TestClient(create_app(settings)) as client:
        owner = _register(
            client,
            email="owner@example.com",
            name="Owner",
        )
        _promote(settings, client, email="owner@example.com")
        headers = _owner_headers(client)

        missing_csrf = client.post(
            "/v1/platform-admin/trusted-agents/workspace-bindings",
            headers=ORIGIN,
            json={
                "environment": "development",
                "fingerprintToken": FINGERPRINT_A,
            },
        )
        assert missing_csrf.status_code == 403
        assert missing_csrf.json()["code"] == "csrf_token_required"

        bad_origin = client.post(
            "/v1/platform-admin/trusted-agents/workspace-bindings",
            headers={
                "Origin": "https://attacker.invalid",
                "X-CSRF-Token": headers["X-CSRF-Token"],
            },
            json={
                "environment": "development",
                "fingerprintToken": FINGERPRINT_A,
            },
        )
        assert bad_origin.status_code == 403

        raw_path = client.post(
            "/v1/platform-admin/trusted-agents/workspace-bindings",
            headers=headers,
            json={
                "environment": "development",
                "fingerprintToken": FINGERPRINT_A,
                "path": path_marker,
            },
        )
        assert raw_path.status_code == 422
        assert path_marker not in raw_path.text

        client_chosen_ref = client.post(
            "/v1/platform-admin/trusted-agents/workspace-bindings",
            headers=headers,
            json={
                "environment": "development",
                "fingerprintToken": FINGERPRINT_A,
                "serverRef": "wsref_client_must_not_choose",
            },
        )
        assert client_chosen_ref.status_code == 422

        raw_credential = client.post(
            "/v1/platform-admin/trusted-agents/workspace-bindings",
            headers=headers,
            json={
                "environment": "development",
                "fingerprintToken": secret_marker,
                "credential": secret_marker,
            },
        )
        assert raw_credential.status_code == 422
        assert secret_marker not in raw_credential.text

        binding = _create_binding(client, headers=headers)
        assert str(binding["id"]).startswith("wsb_")
        assert str(binding["serverRef"]).startswith("wsref_")
        assert "/" not in str(binding["serverRef"])

        unsafe_profile = client.post(
            "/v1/platform-admin/trusted-agents/profiles",
            headers=headers,
            json={
                "workspaceBindingId": binding["id"],
                **PROFILE,
                "displayName": path_marker,
                "apiKey": secret_marker,
            },
        )
        assert unsafe_profile.status_code == 422
        assert secret_marker not in unsafe_profile.text
        assert path_marker not in unsafe_profile.text

        wrong_policy = client.post(
            "/v1/platform-admin/trusted-agents/profiles",
            headers=headers,
            json={
                "workspaceBindingId": binding["id"],
                **PROFILE,
                "maxConcurrency": 2,
                "sandboxProfile": "workspace-write",
            },
        )
        assert wrong_policy.status_code == 422

        database = sqlite3.connect(database_path)
        try:
            database.execute(
                """
                UPDATE sessions
                SET created_at = unixepoch() - 301
                WHERE user_id = ?
                """,
                (owner["id"],),
            )
            database.commit()
        finally:
            database.close()

        # Recent authentication protects durable authority mutations, not
        # bounded owner reads.
        readable = client.get(
            "/v1/platform-admin/trusted-agents/workspace-bindings"
        )
        assert readable.status_code == 200
        stale_auth = client.patch(
            (
                "/v1/platform-admin/trusted-agents/workspace-bindings/"
                f"{binding['id']}"
            ),
            headers=headers,
            json={"revision": binding["revision"], "environment": "staging"},
        )
        assert stale_auth.status_code == 403
        assert (
            stale_auth.json()["code"]
            == "trusted_agent_reauthentication_required"
        )

        audit = client.get(
            "/v1/platform-admin/trusted-agents/audit?limit=100"
        )
        assert audit.status_code == 200
        assert secret_marker not in audit.text
        assert path_marker not in audit.text
        assert audit.json()["items"][0]["after"]["fingerprintConfigured"] is True
        assert "fingerprintToken" not in audit.text

    database = sqlite3.connect(database_path)
    try:
        dump = "\n".join(database.iterdump())
        assert secret_marker not in dump
        assert path_marker not in dump
    finally:
        database.close()


def test_revision_epoch_binding_and_terminal_revoke_are_atomic(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "trusted-agent-lifecycle.db"
    settings = Settings.for_testing(
        database_url=database_path,
        bootstrap_owner_email=None,
    )
    with TestClient(create_app(settings)) as client:
        owner = _register(
            client,
            email="owner-lifecycle@example.com",
            name="Lifecycle owner",
        )
        _promote(
            settings,
            client,
            email="owner-lifecycle@example.com",
        )
        headers = _owner_headers(client)
        binding = _create_binding(client, headers=headers)

        updated_binding_response = client.patch(
            (
                "/v1/platform-admin/trusted-agents/workspace-bindings/"
                f"{binding['id']}"
            ),
            headers=headers,
            json={
                "revision": binding["revision"],
                "environment": "staging",
                "fingerprintToken": FINGERPRINT_B,
            },
        )
        assert updated_binding_response.status_code == 200
        updated_binding = updated_binding_response.json()
        assert updated_binding["revision"] == 2
        assert updated_binding["workspaceEpoch"] == 2

        audit_before_stale = client.get(
            "/v1/platform-admin/trusted-agents/audit?limit=100"
        ).json()["items"]
        stale = client.patch(
            (
                "/v1/platform-admin/trusted-agents/workspace-bindings/"
                f"{binding['id']}"
            ),
            headers=headers,
            json={"revision": 1, "environment": "production"},
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "revision_conflict"
        audit_after_stale = client.get(
            "/v1/platform-admin/trusted-agents/audit?limit=100"
        ).json()["items"]
        assert len(audit_after_stale) == len(audit_before_stale)

        first_profile = _create_profile(
            client,
            headers=headers,
            binding_id=binding["id"],
        )
        assert first_profile["accessMode"] == "full"
        assert first_profile["sandboxProfile"] == "danger-full-access"
        assert first_profile["approvalPolicy"] == "never"
        assert first_profile["maxConcurrency"] == 1

        updated_profile_response = client.patch(
            (
                "/v1/platform-admin/trusted-agents/profiles/"
                f"{first_profile['id']}"
            ),
            headers=headers,
            json={
                "revision": first_profile["revision"],
                "displayName": "Updated trusted agent",
            },
        )
        assert updated_profile_response.status_code == 200
        updated_profile = updated_profile_response.json()
        assert updated_profile["displayName"] == "Updated trusted agent"
        assert updated_profile["revision"] == 2
        assert updated_profile["profileEpoch"] == 2
        stale_profile = client.patch(
            (
                "/v1/platform-admin/trusted-agents/profiles/"
                f"{first_profile['id']}"
            ),
            headers=headers,
            json={
                "revision": first_profile["revision"],
                "displayName": "Must not win",
            },
        )
        assert stale_profile.status_code == 409
        assert stale_profile.json()["code"] == "revision_conflict"

        revoked_profile_response = client.post(
            (
                "/v1/platform-admin/trusted-agents/profiles/"
                f"{first_profile['id']}/revoke"
            ),
            headers=headers,
            json={"revision": updated_profile["revision"]},
        )
        assert revoked_profile_response.status_code == 200
        revoked_profile = revoked_profile_response.json()
        assert revoked_profile["lifecycleStatus"] == "revoked"
        assert revoked_profile["revision"] == 3
        assert revoked_profile["profileEpoch"] == 3

        database = sqlite3.connect(database_path)
        try:
            database.execute(
                """
                UPDATE platform_authority_grants
                SET authority_epoch = authority_epoch + 1,
                    updated_at = unixepoch()
                WHERE authority_id = 'platform_owner'
                """
            )
            database.commit()
        finally:
            database.close()

        stale_binding_profile = client.post(
            "/v1/platform-admin/trusted-agents/profiles",
            headers=headers,
            json={
                "workspaceBindingId": binding["id"],
                **PROFILE,
            },
        )
        assert stale_binding_profile.status_code == 409
        assert (
            stale_binding_profile.json()["code"]
            == "trusted_agent_workspace_authority_stale"
        )

        renewed_binding_response = client.patch(
            (
                "/v1/platform-admin/trusted-agents/workspace-bindings/"
                f"{binding['id']}"
            ),
            headers=headers,
            json={
                "revision": updated_binding["revision"],
                "environment": "production",
            },
        )
        assert renewed_binding_response.status_code == 200
        renewed_binding = renewed_binding_response.json()
        assert renewed_binding["authorityEpoch"] == 2
        assert renewed_binding["workspaceEpoch"] == 3
        assert renewed_binding["revision"] == 3

        second_profile = _create_profile(
            client,
            headers=headers,
            binding_id=binding["id"],
        )
        assert second_profile["authorityEpoch"] == 2
        assert second_profile["workspaceBindingEpoch"] == 3

        now = int(time.time())
        lease_id = f"tal_{'c' * 32}"
        database = sqlite3.connect(database_path)
        try:
            database.execute("PRAGMA foreign_keys = ON")
            database.execute(
                """
                INSERT INTO trusted_agent_workspace_leases (
                    id,
                    authority_id,
                    owner_user_id,
                    owner_tenant_id,
                    authority_epoch,
                    profile_id,
                    profile_epoch,
                    workspace_binding_id,
                    workspace_binding_epoch,
                    state,
                    fencing_token,
                    created_at,
                    updated_at,
                    expires_at,
                    assignment_ref
                ) VALUES (
                    ?, 'platform_owner', ?, ?, 2, ?, 1, ?, 3,
                    'active', 1, ?, ?, ?, 'run_control_revoke_001'
                )
                """,
                (
                    lease_id,
                    owner["id"],
                    owner["tenantId"],
                    second_profile["id"],
                    binding["id"],
                    now,
                    now,
                    now + 60,
                ),
            )
            database.commit()
        finally:
            database.close()

        revoked_binding_response = client.post(
            (
                "/v1/platform-admin/trusted-agents/workspace-bindings/"
                f"{binding['id']}/revoke"
            ),
            headers=headers,
            json={"revision": renewed_binding["revision"]},
        )
        assert revoked_binding_response.status_code == 200
        revoked_binding = revoked_binding_response.json()
        assert revoked_binding["lifecycleStatus"] == "revoked"
        assert revoked_binding["revision"] == 4
        assert revoked_binding["workspaceEpoch"] == 4

        profiles = client.get(
            "/v1/platform-admin/trusted-agents/profiles?limit=100"
        )
        assert profiles.status_code == 200
        second_after = next(
            item
            for item in profiles.json()["items"]
            if item["id"] == second_profile["id"]
        )
        assert second_after["lifecycleStatus"] == "revoked"
        assert second_after["revision"] == 2
        assert second_after["profileEpoch"] == 2

        database = sqlite3.connect(database_path)
        try:
            lease = database.execute(
                """
                SELECT state, terminal_at
                FROM trusted_agent_workspace_leases
                WHERE id = ?
                """,
                (lease_id,),
            ).fetchone()
            assert lease is not None
            assert lease[0] == "revoked"
            assert lease[1] is not None
        finally:
            database.close()

        audit = client.get(
            "/v1/platform-admin/trusted-agents/audit?limit=100"
        )
        assert audit.status_code == 200
        actions = {item["action"] for item in audit.json()["items"]}
        assert {
            "binding.created",
            "binding.updated",
            "binding.revoked",
            "profile.created",
            "profile.updated",
            "profile.revoked",
            "profile.revoked_by_binding",
        } <= actions
        assert (
            client.get(
                "/v1/platform-admin/trusted-agents/audit?limit=101"
            ).status_code
            == 422
        )


def test_fresh_native_bearer_can_mutate_without_browser_csrf(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "trusted-agent-native.db"
    settings = Settings.for_testing(
        database_url=database_path,
        bootstrap_owner_email=None,
    )
    with TestClient(create_app(settings)) as client:
        registered = client.post(
            "/v1/mobile/auth/register",
            json={
                "email": "native-owner@example.com",
                "name": "Native owner",
                "password": PASSWORD,
                "device": DEVICE,
            },
        )
        assert registered.status_code == 201, registered.text
        issued = registered.json()
        promote_registered_owner(
            settings,
            email="native-owner@example.com",
        )
        assert client.cookies.get("kolibri_v3_session") is None
        assert client.cookies.get("kolibri_v3_csrf") is None

        bearer = {
            "Authorization": f"Bearer {issued['accessToken']}",
        }
        created = client.post(
            "/v1/platform-admin/trusted-agents/workspace-bindings",
            headers=bearer,
            json={
                "environment": "production",
                "fingerprintToken": FINGERPRINT_A,
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["environment"] == "production"

        listed = client.get(
            "/v1/platform-admin/trusted-agents/workspace-bindings",
            headers=bearer,
        )
        assert listed.status_code == 200
        assert listed.json()["items"][0]["id"] == created.json()["id"]
