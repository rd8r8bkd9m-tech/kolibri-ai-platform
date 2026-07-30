from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.database import initialize_database, migration_paths


OWNER_CAPABILITIES = json.dumps(
    [
        "platform.admin",
        "platform.policy.write",
        "platform.sessions.revoke",
        "chat.developer.request",
        "chat.use",
    ],
    separators=(",", ":"),
)


def _apply_through(database_path: Path, maximum_version: int) -> None:
    database = sqlite3.connect(database_path, isolation_level=None)
    try:
        database.execute("PRAGMA foreign_keys = ON")
        current_version = int(
            database.execute("PRAGMA user_version").fetchone()[0]
        )
        for migration_path in migration_paths():
            version = int(migration_path.name.split("_", 1)[0])
            if version > maximum_version:
                break
            if version <= current_version:
                continue
            database.executescript(
                migration_path.read_text(encoding="utf-8")
            )
    finally:
        database.close()


def _insert_owner(database: sqlite3.Connection) -> None:
    database.execute(
        "INSERT INTO tenants (id, name, created_at) VALUES (?, ?, ?)",
        ("tenant_owner", "Owner tenant", 100),
    )
    database.execute(
        """
        INSERT INTO users (
            id,
            tenant_id,
            email_normalized,
            email,
            name,
            role,
            preferred_agent_profile,
            password_hash,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, 'owner', 'auto', ?, ?, ?)
        """,
        (
            "user_owner",
            "tenant_owner",
            "owner@example.com",
            "owner@example.com",
            "Owner",
            "test-password-hash",
            100,
            100,
        ),
    )


def _insert_authority(database: sqlite3.Connection) -> None:
    database.execute(
        """
        INSERT INTO platform_authority_grants (
            authority_id,
            user_id,
            tenant_id,
            active,
            authority_epoch,
            capabilities_json,
            created_at,
            updated_at
        ) VALUES (
            'platform_owner', ?, ?, 1, 1, ?, ?, ?
        )
        """,
        (
            "user_owner",
            "tenant_owner",
            OWNER_CAPABILITIES,
            100,
            100,
        ),
    )


def test_migration_034_upgrades_v33_without_adopting_legacy_workspace(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "trusted-agent-v33.db"
    _apply_through(database_path, 32)
    database = sqlite3.connect(database_path, isolation_level=None)
    try:
        database.execute("PRAGMA foreign_keys = ON")
        _insert_owner(database)
    finally:
        database.close()
    _apply_through(database_path, 33)

    database = sqlite3.connect(database_path)
    try:
        assert database.execute("PRAGMA user_version").fetchone()[0] == 33
        assert (
            database.execute(
                "SELECT COUNT(*) FROM platform_authority_grants"
            ).fetchone()[0]
            == 1
        )
    finally:
        database.close()

    _apply_through(database_path, 34)

    database = sqlite3.connect(database_path)
    try:
        assert database.execute("PRAGMA user_version").fetchone()[0] == 34
        strict_tables = dict(
            database.execute(
                """
                SELECT name, strict
                FROM pragma_table_list
                WHERE name IN (
                    'trusted_agent_workspace_bindings',
                    'trusted_agent_profiles',
                    'trusted_agent_workspace_leases',
                    'trusted_agent_audit_events'
                )
                """
            )
        )
        assert strict_tables == {
            "trusted_agent_workspace_bindings": 1,
            "trusted_agent_profiles": 1,
            "trusted_agent_workspace_leases": 1,
            "trusted_agent_audit_events": 1,
        }
        # Even an unambiguous legacy owner is not enough to infer a physical
        # workspace. The Provider Execution Authority must bind it explicitly.
        assert (
            database.execute(
                "SELECT COUNT(*) FROM trusted_agent_workspace_bindings"
            ).fetchone()[0]
            == 0
        )
        assert (
            database.execute(
                "SELECT COUNT(*) FROM trusted_agent_profiles"
            ).fetchone()[0]
            == 0
        )
        assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        database.close()

    initialize_database(database_path)
    database = sqlite3.connect(database_path)
    try:
        latest_version = int(migration_paths()[-1].name.split("_", 1)[0])
        assert (
            database.execute("PRAGMA user_version").fetchone()[0]
            == latest_version
        )
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        database.close()


def test_migration_034_enforces_r1_uniqueness_leases_and_append_only_audit(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "trusted-agent-constraints.db"
    initialize_database(database_path)
    database = sqlite3.connect(database_path, isolation_level=None)
    try:
        database.execute("PRAGMA foreign_keys = ON")
        _insert_owner(database)
        _insert_authority(database)
        binding_id = f"wsb_{'a' * 32}"
        profile_id = f"tap_{'b' * 32}"
        database.execute(
            """
            INSERT INTO trusted_agent_workspace_bindings (
                id,
                authority_id,
                owner_user_id,
                owner_tenant_id,
                authority_epoch,
                server_ref,
                environment,
                fingerprint_token,
                lifecycle_status,
                workspace_epoch,
                revision,
                created_at,
                updated_at,
                created_by_user_id
            ) VALUES (
                ?, 'platform_owner', 'user_owner', 'tenant_owner', 1, ?,
                'development', ?, 'active', 1, 1, 100, 100, 'user_owner'
            )
            """,
            (
                binding_id,
                f"wsref_{'c' * 32}",
                f"sha256:{'d' * 64}",
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                """
                INSERT INTO trusted_agent_workspace_bindings (
                    id,
                    authority_id,
                    owner_user_id,
                    owner_tenant_id,
                    authority_epoch,
                    server_ref,
                    environment,
                    fingerprint_token,
                    lifecycle_status,
                    workspace_epoch,
                    revision,
                    created_at,
                    updated_at,
                    created_by_user_id
                ) VALUES (
                    ?, 'platform_owner', 'user_owner', 'tenant_owner', 1, ?,
                    'staging', ?, 'active', 1, 1, 100, 100, 'user_owner'
                )
                """,
                (
                    f"wsb_{'e' * 32}",
                    f"wsref_{'f' * 32}",
                    f"sha256:{'1' * 64}",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                """
                UPDATE trusted_agent_workspace_bindings
                SET server_ref = '/srv/private/workspace'
                WHERE id = ?
                """,
                (binding_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                """
                UPDATE trusted_agent_workspace_bindings
                SET fingerprint_token = 'raw-secret'
                WHERE id = ?
                """,
                (binding_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                """
                UPDATE trusted_agent_workspace_bindings
                SET authority_epoch = 2,
                    workspace_epoch = 2,
                    revision = 2
                WHERE id = ?
                """,
                (binding_id,),
            )

        database.execute(
            """
            INSERT INTO trusted_agent_profiles (
                id,
                authority_id,
                owner_user_id,
                owner_tenant_id,
                authority_epoch,
                workspace_binding_id,
                workspace_binding_epoch,
                display_name,
                runtime_profile,
                agent_card_id,
                agent_card_version,
                created_at,
                updated_at,
                created_by_user_id
            ) VALUES (
                ?, 'platform_owner', 'user_owner', 'tenant_owner', 1,
                ?, 1, 'Primary trusted agent', 'codex-cli',
                'codex-cli.primary', 1, 100, 100, 'user_owner'
            )
            """,
            (profile_id, binding_id),
        )
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                """
                INSERT INTO trusted_agent_profiles (
                    id,
                    authority_id,
                    owner_user_id,
                    owner_tenant_id,
                    authority_epoch,
                    workspace_binding_id,
                    workspace_binding_epoch,
                    display_name,
                    runtime_profile,
                    agent_card_id,
                    agent_card_version,
                    created_at,
                    updated_at,
                    created_by_user_id
                ) VALUES (
                    ?, 'platform_owner', 'user_owner', 'tenant_owner', 1,
                    ?, 1, 'Second trusted agent', 'codex-cli',
                    'codex-cli.secondary', 1, 100, 100, 'user_owner'
                )
                """,
                (f"tap_{'2' * 32}", binding_id),
            )
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                """
                UPDATE trusted_agent_profiles
                SET max_concurrency = 2
                WHERE id = ?
                """,
                (profile_id,),
            )

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
                ?, 'platform_owner', 'user_owner', 'tenant_owner', 1,
                ?, 1, ?, 1, 'active', 1, 100, 100, 200,
                'assignment_migration_primary'
            )
            """,
            (f"tal_{'3' * 32}", profile_id, binding_id),
        )
        with pytest.raises(sqlite3.IntegrityError):
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
                    ?, 'platform_owner', 'user_owner', 'tenant_owner', 1,
                    ?, 1, ?, 1, 'active', 2, 100, 100, 200,
                    'assignment_migration_second'
                )
                """,
                (f"tal_{'4' * 32}", profile_id, binding_id),
            )

        audit_id = f"taudit_{'5' * 32}"
        database.execute(
            """
            INSERT INTO trusted_agent_audit_events (
                id,
                actor_user_id,
                actor_tenant_id,
                authority_epoch,
                authorization_decision_id,
                action,
                target_type,
                target_id,
                target_revision,
                target_epoch,
                before_json,
                after_json,
                created_at
            ) VALUES (
                ?, 'user_owner', 'tenant_owner', 1, ?,
                'profile.created', 'profile', ?, 1, 1, '{}', '{}', 100
            )
            """,
            (audit_id, f"decision_{'6' * 32}", profile_id),
        )
        with pytest.raises(
            sqlite3.IntegrityError,
            match="append-only",
        ):
            database.execute(
                """
                UPDATE trusted_agent_audit_events
                SET after_json = '{"changed":true}'
                WHERE id = ?
                """,
                (audit_id,),
            )
        with pytest.raises(
            sqlite3.IntegrityError,
            match="append-only",
        ):
            database.execute(
                "DELETE FROM trusted_agent_audit_events WHERE id = ?",
                (audit_id,),
            )
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        database.close()
