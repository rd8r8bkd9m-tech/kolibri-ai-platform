from __future__ import annotations

import sqlite3
from pathlib import Path

from app.database import initialize_database, migration_paths


NOW = "2026-07-30T00:00:00+00:00"
DIGEST = "sha256:" + ("a" * 64)


def _create_v32_database(path: Path, *, owner_count: int = 1) -> None:
    database = sqlite3.connect(path, isolation_level=None)
    try:
        database.execute("PRAGMA foreign_keys = ON")
        for migration in migration_paths():
            version = int(migration.name.split("_", 1)[0])
            if version > 32:
                break
            database.executescript(migration.read_text(encoding="utf-8"))

        database.execute(
            """
            INSERT INTO tenants (id, name, created_at)
            VALUES ('tenant-legacy', 'Legacy tenant', 1)
            """
        )
        users = [
            (
                "user-owner",
                "owner@example.com",
                "owner" if owner_count >= 1 else "user",
            ),
            (
                "user-member",
                "member@example.com",
                "owner" if owner_count >= 2 else "user",
            ),
        ]
        database.executemany(
            """
            INSERT INTO users (
                id, tenant_id, email_normalized, email, name, role,
                preferred_agent_profile, password_hash, created_at, updated_at
            ) VALUES (
                ?, 'tenant-legacy', ?, ?, 'Legacy user', ?, 'auto',
                'password-hash', 1, 1
            )
            """,
            [
                (user_id, email, email, role)
                for user_id, email, role in users
            ],
        )
        for suffix in ("direct", "home"):
            project_id = f"project-{suffix}"
            thread_id = f"thread-{suffix}"
            message_id = f"message-{suffix}"
            run_id = f"run-{suffix}"
            database.execute(
                """
                INSERT INTO projects (
                    tenant_id, id, created_by_user_id, title, status,
                    primary_thread_id, created_at, updated_at
                ) VALUES (
                    'tenant-legacy', ?, 'user-owner', ?, 'active', ?, ?, ?
                )
                """,
                (project_id, f"Project {suffix}", thread_id, NOW, NOW),
            )
            database.execute(
                """
                INSERT INTO chat_threads (
                    tenant_id, id, project_id, kind, title, status,
                    message_count, run_count, created_at, updated_at
                ) VALUES (
                    'tenant-legacy', ?, ?, 'primary', ?, 'regular',
                    1, 1, ?, ?
                )
                """,
                (thread_id, project_id, f"Thread {suffix}", NOW, NOW),
            )
            database.execute(
                """
                INSERT INTO chat_messages (
                    tenant_id, id, project_id, thread_id, sequence,
                    client_message_id, role, content_text,
                    created_by_user_id, created_at
                ) VALUES (
                    'tenant-legacy', ?, ?, ?, 1, ?, 'user',
                    'Legacy prompt', 'user-owner', ?
                )
                """,
                (
                    message_id,
                    project_id,
                    thread_id,
                    f"client-message-{suffix}",
                    NOW,
                ),
            )
            database.execute(
                """
                INSERT INTO chat_runs (
                    tenant_id, id, project_id, thread_id, client_run_id,
                    request_hash, input_message_id, requested_by_user_id,
                    selected_profile, status, last_event_sequence,
                    heartbeat_at, created_at, updated_at
                ) VALUES (
                    'tenant-legacy', ?, ?, ?, ?, ?, ?, 'user-owner',
                    'codex-cli', 'running', 1, ?, ?, ?
                )
                """,
                (
                    run_id,
                    project_id,
                    thread_id,
                    f"client-run-{suffix}",
                    DIGEST,
                    message_id,
                    NOW,
                    NOW,
                    NOW,
                ),
            )
            database.execute(
                """
                INSERT INTO chat_run_execution_contexts (
                    tenant_id, run_id, execution_mode, access_mode,
                    authority_role, authority_user_id, workspace_ref,
                    sandbox_profile, approval_policy, approvals_reviewer,
                    model_id, reasoning_effort, service_tier, created_at
                ) VALUES (
                    'tenant-legacy', ?, 'standard', 'standard', 'user',
                    'user-owner', NULL, 'read-only', 'never', NULL,
                    'gpt-5.6-sol', 'high', NULL, ?
                )
                """,
                (run_id, NOW),
            )

        database.execute(
            """
            UPDATE chat_run_execution_contexts
            SET execution_mode = 'developer',
                access_mode = 'full',
                authority_role = 'owner',
                workspace_ref = 'repository',
                sandbox_profile = 'danger-full-access',
                approval_policy = 'never',
                approvals_reviewer = NULL
            WHERE tenant_id = 'tenant-legacy' AND run_id = 'run-direct'
            """
        )
        database.execute(
            """
            INSERT INTO product_run_outbox (
                tenant_id, id, run_id, command_kind, phase, state,
                command_json, command_hash, attempts, max_attempts,
                available_at, fencing_token, created_at, updated_at
            ) VALUES (
                'tenant-legacy', 'outbox-home', 'run-home',
                'product.run.execute', 'run_execute', 'queued', '{}', ?,
                0, 8, ?, 0, ?, ?
            )
            """,
            (DIGEST, NOW, NOW, NOW),
        )
        assert database.execute("PRAGMA user_version").fetchone()[0] == 32
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        database.close()


def test_v33_adopts_single_owner_and_backfills_execution_plane(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy-v32.db"
    _create_v32_database(database_path)

    initialize_database(database_path)

    database = sqlite3.connect(database_path, isolation_level=None)
    try:
        latest_version = int(
            migration_paths()[-1].name.split("_", 1)[0]
        )
        assert (
            database.execute("PRAGMA user_version").fetchone()[0]
            == latest_version
        )
        assert database.execute(
            """
            SELECT authority_id, user_id, tenant_id, active
            FROM platform_authority_grants
            """
        ).fetchall() == [
            ("platform_owner", "user-owner", "tenant-legacy", 1)
        ]
        assert database.execute(
            """
            SELECT tenant_id, user_id, entitlement_code, status,
                   grant_epoch, source
            FROM product_entitlement_grants
            """
        ).fetchall() == [
            (
                "tenant-legacy",
                "user-owner",
                "construction.estimates.use",
                "active",
                1,
                "release_bootstrap",
            )
        ]
        assert database.execute(
            """
            SELECT tenant_id, lifecycle_status, developer_access_enabled,
                   updated_by_user_id
            FROM platform_tenant_policies
            """
        ).fetchall() == [
            ("tenant-legacy", "active", 1, "user-owner")
        ]
        assert database.execute(
            """
            SELECT user_id, access_status, developer_access
            FROM platform_user_controls
            ORDER BY user_id
            """
        ).fetchall() == [
            ("user-member", "active", "inherit"),
            ("user-owner", "active", "allow"),
        ]
        assert database.execute(
            """
            SELECT run_id, execution_plane, platform_authority_epoch
            FROM chat_run_execution_contexts
            ORDER BY run_id
            """
        ).fetchall() == [
            ("run-direct", "direct", 1),
            ("run-home", "home", None),
        ]

        database.execute(
            """
            INSERT INTO tenants (id, name, created_at)
            VALUES ('tenant-new', 'New tenant', 2)
            """
        )
        database.execute(
            """
            INSERT INTO users (
                id, tenant_id, email_normalized, email, name, role,
                preferred_agent_profile, password_hash, created_at, updated_at
            ) VALUES (
                'user-new', 'tenant-new', 'new@example.com',
                'new@example.com', 'New user', 'user', 'auto',
                'password-hash', 2, 2
            )
            """
        )
        assert database.execute(
            """
            SELECT lifecycle_status, developer_access_enabled
            FROM platform_tenant_policies
            WHERE tenant_id = 'tenant-new'
            """
        ).fetchone() == ("active", 0)
        assert database.execute(
            """
            SELECT access_status, developer_access
            FROM platform_user_controls
            WHERE user_id = 'user-new'
            """
        ).fetchone() == ("active", "inherit")
        assert database.execute("PRAGMA integrity_check").fetchall() == [
            ("ok",)
        ]
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        database.close()


def test_v33_refuses_to_guess_between_multiple_legacy_owners(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ambiguous-v32.db"
    _create_v32_database(database_path, owner_count=2)

    initialize_database(database_path)

    database = sqlite3.connect(database_path)
    try:
        assert database.execute(
            "SELECT COUNT(*) FROM platform_authority_grants"
        ).fetchone()[0] == 0
        assert database.execute(
            """
            SELECT developer_access_enabled, updated_by_user_id
            FROM platform_tenant_policies
            WHERE tenant_id = 'tenant-legacy'
            """
        ).fetchone() == (0, None)
        assert database.execute(
            """
            SELECT DISTINCT developer_access
            FROM platform_user_controls
            """
        ).fetchall() == [("inherit",)]
    finally:
        database.close()
