from __future__ import annotations

import sqlite3
from pathlib import Path

from app.database import initialize_database, migration_paths


LATEST_SCHEMA_VERSION = int(migration_paths()[-1].name.split("_", 1)[0])


def _create_deployed_v26_database(database_path: Path) -> None:
    database = sqlite3.connect(database_path, isolation_level=None)
    try:
        for migration in migration_paths():
            if int(migration.name[:3]) > 26:
                break
            database.executescript(migration.read_text(encoding="utf-8"))
        database.executescript(
            """
            PRAGMA foreign_keys = ON;
            INSERT INTO tenants (id, name, created_at)
            VALUES ('tenant', 'Tenant', 1);
            INSERT INTO users (
                id, tenant_id, email_normalized, email, name, role,
                preferred_agent_profile, password_hash, created_at, updated_at
            ) VALUES
                (
                    'owner', 'tenant', 'owner@example.com',
                    'owner@example.com', 'Owner', 'owner', 'codex-cli',
                    'hash', 1, 1
                ),
                (
                    'user', 'tenant', 'user@example.com',
                    'user@example.com', 'User', 'user', 'codex-cli',
                    'hash', 1, 1
                );
            INSERT INTO projects (
                tenant_id, id, created_by_user_id, title, status,
                primary_thread_id, created_at, updated_at
            ) VALUES (
                'tenant', 'project', 'owner', 'Project', 'active',
                'thread', 'now', 'now'
            );
            INSERT INTO chat_threads (
                tenant_id, id, project_id, title, created_at, updated_at
            ) VALUES (
                'tenant', 'thread', 'project', 'Thread', 'now', 'now'
            );
            INSERT INTO chat_messages (
                tenant_id, id, project_id, thread_id, sequence,
                client_message_id, role, content_text, created_by_user_id,
                created_at
            ) VALUES
                (
                    'tenant', 'message-standard', 'project', 'thread', 1,
                    'client-message-standard', 'user', 'standard',
                    'user', 'now'
                ),
                (
                    'tenant', 'message-auto', 'project', 'thread', 2,
                    'client-message-auto', 'user', 'auto', 'owner', 'now'
                ),
                (
                    'tenant', 'message-full', 'project', 'thread', 3,
                    'client-message-full', 'user', 'full', 'owner', 'now'
                );
            INSERT INTO chat_runs (
                tenant_id, id, project_id, thread_id, client_run_id,
                request_hash, input_message_id, requested_by_user_id,
                selected_profile, status, heartbeat_at, created_at, updated_at
            ) VALUES
                (
                    'tenant', 'run-standard', 'project', 'thread',
                    'client-run-standard', 'sha256:a', 'message-standard',
                    'user', 'codex-cli', 'running', 'now', 'now', 'now'
                ),
                (
                    'tenant', 'run-auto', 'project', 'thread',
                    'client-run-auto', 'sha256:b', 'message-auto',
                    'owner', 'codex-cli', 'running', 'now', 'now', 'now'
                ),
                (
                    'tenant', 'run-full', 'project', 'thread',
                    'client-run-full', 'sha256:c', 'message-full',
                    'owner', 'codex-cli', 'running', 'now', 'now', 'now'
                );
            INSERT INTO chat_run_execution_contexts (
                tenant_id, run_id, execution_mode, access_mode,
                access_policy_version, authority_role, authority_user_id,
                workspace_ref, sandbox_profile, approval_policy,
                approvals_reviewer, model_id, reasoning_effort, service_tier,
                created_at
            ) VALUES
                (
                    'tenant', 'run-standard', 'standard', 'standard', 2,
                    'user', 'user', NULL, 'read-only', 'never', NULL,
                    NULL, NULL, NULL, 'now'
                ),
                (
                    'tenant', 'run-auto', 'developer', 'auto', 2,
                    'owner', 'owner', 'repository', 'workspace-write',
                    'on-request', 'auto_review', NULL, NULL, NULL, 'now'
                ),
                (
                    'tenant', 'run-full', 'developer', 'full', 2,
                    'owner', 'owner', 'repository', 'danger-full-access',
                    'never', NULL, NULL, NULL, 'priority', 'now'
                );

            PRAGMA foreign_keys = OFF;
            BEGIN IMMEDIATE;
            CREATE TABLE chat_run_execution_contexts_deployed (
                tenant_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                execution_mode TEXT NOT NULL,
                access_mode TEXT NOT NULL,
                authority_role TEXT NOT NULL,
                authority_user_id TEXT NOT NULL,
                workspace_ref TEXT,
                sandbox_profile TEXT NOT NULL,
                approval_policy TEXT NOT NULL,
                approvals_reviewer TEXT,
                model_id TEXT,
                reasoning_effort TEXT,
                service_tier TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, run_id),
                FOREIGN KEY (tenant_id, run_id)
                    REFERENCES chat_runs (tenant_id, id),
                FOREIGN KEY (authority_user_id, tenant_id)
                    REFERENCES users (id, tenant_id)
            );
            INSERT INTO chat_run_execution_contexts_deployed (
                tenant_id, run_id, execution_mode, access_mode,
                authority_role, authority_user_id, workspace_ref,
                sandbox_profile, approval_policy, approvals_reviewer,
                model_id, reasoning_effort, service_tier, created_at
            )
            SELECT
                tenant_id, run_id, execution_mode, access_mode,
                authority_role, authority_user_id, workspace_ref,
                sandbox_profile, approval_policy, approvals_reviewer,
                model_id, reasoning_effort, service_tier, created_at
            FROM chat_run_execution_contexts;
            DROP TABLE chat_run_execution_contexts;
            ALTER TABLE chat_run_execution_contexts_deployed
                RENAME TO chat_run_execution_contexts;
            PRAGMA user_version = 26;
            COMMIT;
            PRAGMA foreign_keys = ON;
            """
        )
    finally:
        database.close()


def test_v27_repairs_the_deployed_v26_shape_without_data_loss(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "deployed-v26.db"
    _create_deployed_v26_database(database_path)

    initialize_database(database_path)

    database = sqlite3.connect(database_path)
    try:
        assert (
            database.execute("PRAGMA user_version").fetchone()[0]
            == LATEST_SCHEMA_VERSION
        )
        assert "access_policy_version" in {
            str(row[1])
            for row in database.execute(
                "PRAGMA table_info(chat_run_execution_contexts)"
            )
        }
        assert database.execute(
            """
            SELECT run_id, access_policy_version
            FROM chat_run_execution_contexts
            ORDER BY run_id
            """
        ).fetchall() == [
            ("run-auto", 2),
            ("run-full", 2),
            ("run-standard", 2),
        ]
        assert database.execute(
            "PRAGMA foreign_key_check"
        ).fetchall() == []
    finally:
        database.close()


def test_v27_is_compatible_with_a_fresh_v26_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "fresh.db"

    initialize_database(database_path)

    database = sqlite3.connect(database_path)
    try:
        assert (
            database.execute("PRAGMA user_version").fetchone()[0]
            == LATEST_SCHEMA_VERSION
        )
        assert "access_policy_version" in {
            str(row[1])
            for row in database.execute(
                "PRAGMA table_info(chat_run_execution_contexts)"
            )
        }
        assert database.execute(
            "PRAGMA foreign_key_check"
        ).fetchall() == []
    finally:
        database.close()
