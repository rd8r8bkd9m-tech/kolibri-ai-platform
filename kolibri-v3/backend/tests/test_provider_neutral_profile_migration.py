from __future__ import annotations

from pathlib import Path
import shutil
import sqlite3

import pytest

from app.database import initialize_database, migration_paths


LATEST_SCHEMA_VERSION = int(migration_paths()[-1].name.split("_", 1)[0])


def _create_v27_database(path: Path) -> None:
    database = sqlite3.connect(path, isolation_level=None)
    try:
        for migration in migration_paths():
            if int(migration.name[:3]) > 27:
                break
            database.executescript(migration.read_text(encoding="utf-8"))
        digest = "sha256:" + ("a" * 64)
        database.executescript(
            f"""
            PRAGMA foreign_keys = ON;
            BEGIN IMMEDIATE;
            INSERT INTO tenants (id, name, created_at)
            VALUES ('tenant-old', 'Old tenant', 1);
            INSERT INTO users (
                id, tenant_id, email_normalized, email, name, role,
                preferred_agent_profile, password_hash, created_at, updated_at,
                preferred_model, preferred_reasoning_effort,
                preferred_service_tier
            ) VALUES (
                'user-old', 'tenant-old', 'old@example.com',
                'old@example.com', 'Old user', 'owner', 'mimo-code',
                'password-hash', 1, 2, 'gpt-5.6-sol', 'ultra', 'priority'
            );
            INSERT INTO users (
                id, tenant_id, email_normalized, email, name, role,
                preferred_agent_profile, password_hash, created_at, updated_at,
                preferred_model
            ) VALUES (
                'user-ambiguous', 'tenant-old', 'ambiguous@example.com',
                'ambiguous@example.com', 'Ambiguous user', 'user', 'auto',
                'password-hash', 1, 2, 'ambiguous model'
            );
            INSERT INTO sessions (
                id, token_hash, user_id, tenant_id, created_at, expires_at
            ) VALUES (
                'session-old', '{'b' * 64}', 'user-old', 'tenant-old', 1, 10
            );
            INSERT INTO projects (
                tenant_id, id, created_by_user_id, title, status,
                primary_thread_id, created_at, updated_at
            ) VALUES (
                'tenant-old', 'project-old', 'user-old', 'Old project',
                'active', 'thread-old', 'now', 'now'
            );
            INSERT INTO chat_threads (
                tenant_id, id, project_id, title, created_at, updated_at
            ) VALUES (
                'tenant-old', 'thread-old', 'project-old', 'Old thread',
                'now', 'now'
            );
            INSERT INTO chat_messages (
                tenant_id, id, project_id, thread_id, sequence,
                client_message_id, role, content_text, created_by_user_id,
                created_at
            ) VALUES (
                'tenant-old', 'message-old', 'project-old', 'thread-old', 1,
                'client-message-old', 'user', 'Old message', 'user-old', 'now'
            );
            INSERT INTO chat_runs (
                tenant_id, id, project_id, thread_id, client_run_id,
                request_hash, input_message_id, requested_by_user_id,
                selected_profile, status, outcome, heartbeat_at, created_at,
                updated_at, finished_at
            ) VALUES (
                'tenant-old', 'run-old', 'project-old', 'thread-old',
                'client-run-old', '{digest}', 'message-old', 'user-old',
                'codex-cli', 'succeeded', 'success', 'now', 'now', 'now', 'now'
            );
            INSERT INTO product_run_runtime (
                tenant_id, run_id, execution_id, resolved_profile,
                verification_status, result_hash, evidence_json,
                created_at, updated_at
            ) VALUES (
                'tenant-old', 'run-old', 'execution-old', 'mimo-code',
                'verified', '{digest}', '{{}}', 'now', 'now'
            );
            INSERT INTO provider_connections (
                tenant_id, provider_id, status, auth_flow_supported,
                authority_observed, last_verified_at, last_evidence_hash,
                last_intent_id, created_at, updated_at
            ) VALUES (
                'tenant-old', 'codex-cli', 'connected', 1, 1, 'now',
                '{digest}', 'intent-old', 'now', 'now'
            );
            INSERT INTO provider_enrollment_intents (
                tenant_id, id, provider_id, requested_by_user_id,
                owner_authorization_decision_id, idempotency_key_hash,
                request_hash, command_json, command_hash, api_response_json,
                state, attempts, max_attempts, available_at, fencing_token,
                last_error_code, created_at, updated_at, completed_at
            ) VALUES (
                'tenant-old', 'intent-old', 'codex-cli', 'user-old',
                'decision_old_owner', '{'c' * 64}', '{digest}', '{{}}',
                '{digest}', '{{}}', 'blocked', 0, 8, 'now', 0,
                'authority_unavailable', 'now', 'now', 'now'
            );
            COMMIT;
            """
        )
        assert database.execute("PRAGMA user_version").fetchone()[0] == 27
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        database.close()


def test_v28_upgrades_a_v27_copy_without_data_or_fk_loss(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source-v27.db"
    upgraded = tmp_path / "upgraded-v28.db"
    _create_v27_database(source)
    shutil.copy2(source, upgraded)

    initialize_database(upgraded)

    database = sqlite3.connect(upgraded, isolation_level=None)
    database.execute("PRAGMA foreign_keys = ON")
    try:
        assert (
            database.execute("PRAGMA user_version").fetchone()[0]
            == LATEST_SCHEMA_VERSION
        )
        assert database.execute("PRAGMA integrity_check").fetchall() == [
            ("ok",)
        ]
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
        assert database.execute(
            """
            SELECT preferred_agent_profile, preferred_model,
                   preferred_reasoning_effort, preferred_service_tier
            FROM users
            WHERE tenant_id = 'tenant-old' AND id = 'user-old'
            """
        ).fetchone() == (
            "mimo-code",
            None,
            None,
            None,
        )
        assert database.execute(
            """
            SELECT runtime_profile, model_id, reasoning_effort, service_tier
            FROM user_model_preferences
            WHERE tenant_id = 'tenant-old' AND user_id = 'user-old'
            """
        ).fetchall() == [
            ("codex-cli", "gpt-5.6-sol", "ultra", "priority")
        ]
        assert database.execute(
            """
            SELECT COUNT(*)
            FROM user_model_preferences
            WHERE tenant_id = 'tenant-old' AND user_id = 'user-ambiguous'
            """
        ).fetchone()[0] == 0
        assert database.execute(
            "SELECT selected_profile FROM chat_runs WHERE id = 'run-old'"
        ).fetchone()[0] == "codex-cli"
        assert database.execute(
            """
            SELECT resolved_profile
            FROM product_run_runtime
            WHERE run_id = 'run-old'
            """
        ).fetchone()[0] == "mimo-code"
        assert database.execute(
            """
            SELECT provider_id, status
            FROM provider_connections
            WHERE provider_id = 'codex-cli'
            """
        ).fetchone() == ("codex-cli", "connected")
        assert database.execute(
            """
            SELECT provider_id, state
            FROM provider_enrollment_intents
            WHERE id = 'intent-old'
            """
        ).fetchone() == ("codex-cli", "blocked")
        assert {
            row[0]
            for row in database.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'index'
                  AND name IN (
                      'ix_chat_runs_tenant_thread_created',
                      'ix_chat_runs_tenant_status_heartbeat',
                      'uq_product_run_runtime_execution',
                      'ix_provider_connections_tenant_status',
                      'uq_provider_enrollment_active',
                      'ix_provider_enrollment_claim',
                      'ix_provider_enrollment_tenant_provider'
                  )
                """
            )
        } == {
            "ix_chat_runs_tenant_thread_created",
            "ix_chat_runs_tenant_status_heartbeat",
            "uq_product_run_runtime_execution",
            "ix_provider_connections_tenant_status",
            "uq_provider_enrollment_active",
            "ix_provider_enrollment_claim",
            "ix_provider_enrollment_tenant_provider",
        }

        database.execute(
            """
            UPDATE users
            SET preferred_agent_profile = 'acme-agent'
            WHERE tenant_id = 'tenant-old' AND id = 'user-old'
            """
        )
        database.execute(
            """
            UPDATE chat_runs
            SET selected_profile = 'acme-agent'
            WHERE tenant_id = 'tenant-old' AND id = 'run-old'
            """
        )
        database.execute(
            """
            UPDATE product_run_runtime
            SET resolved_profile = 'acme-agent'
            WHERE tenant_id = 'tenant-old' AND run_id = 'run-old'
            """
        )
        database.execute(
            """
            INSERT INTO provider_connections (
                tenant_id, provider_id, status, created_at, updated_at
            ) VALUES (
                'tenant-old', 'acme-agent', 'not_configured', 'now', 'now'
            )
            """
        )
        database.execute(
            """
            INSERT INTO user_model_preferences (
                tenant_id, user_id, runtime_profile, model_id,
                reasoning_effort, service_tier, updated_at
            ) VALUES (
                'tenant-old', 'user-old', 'acme-agent', 'acme-reasoner',
                'high', 'priority', 3
            )
            """
        )
        database.execute(
            """
            INSERT INTO provider_enrollment_intents (
                tenant_id, id, provider_id, requested_by_user_id,
                owner_authorization_decision_id, idempotency_key_hash,
                request_hash, command_json, command_hash, api_response_json,
                state, attempts, max_attempts, available_at, fencing_token,
                last_error_code, created_at, updated_at, completed_at
            ) VALUES (
                'tenant-old', 'intent-acme', 'acme-agent', 'user-old',
                'decision_acme_owner',
                'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
                'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                '{}',
                'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                '{}', 'blocked', 0, 8, 'now', 0,
                'authority_unavailable', 'now', 'now', 'now'
            )
            """
        )
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                """
                UPDATE users
                SET preferred_agent_profile = 'Invalid Profile'
                WHERE tenant_id = 'tenant-old' AND id = 'user-old'
                """
            )
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        database.close()
