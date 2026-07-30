from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import sqlite3
from pathlib import Path

from app.chat.models import AgUiRunInput, canonical_run_payload
from app.chat.service import canonical_json, request_hash, sha256_text
from app.database import initialize_database, migration_paths


LATEST_SCHEMA_VERSION = int(migration_paths()[-1].name.split("_", 1)[0])


MIGRATION = (
    Path(__file__).parents[1]
    / "migrations"
    / "026_service_tier_and_access_mode.sql"
)


def test_v26_migrates_legacy_developer_access_modes_atomically(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy-v25.db"
    database = sqlite3.connect(database_path, isolation_level=None)
    try:
        database.executescript(
            """
            CREATE TABLE users (
                id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                preferred_model TEXT,
                preferred_reasoning_effort TEXT,
                PRIMARY KEY (id, tenant_id)
            );
            CREATE TABLE chat_runs (
                tenant_id TEXT NOT NULL,
                id TEXT NOT NULL,
                PRIMARY KEY (tenant_id, id)
            );
            CREATE TABLE chat_run_execution_contexts (
                tenant_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                execution_mode TEXT NOT NULL,
                authority_role TEXT NOT NULL,
                authority_user_id TEXT NOT NULL,
                workspace_ref TEXT,
                sandbox_profile TEXT NOT NULL,
                approval_policy TEXT NOT NULL,
                model_id TEXT,
                reasoning_effort TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, run_id)
            );
            INSERT INTO users (id, tenant_id)
            VALUES ('owner', 'tenant'), ('user', 'tenant');
            INSERT INTO chat_runs (tenant_id, id)
            VALUES
                ('tenant', 'run-standard'),
                ('tenant', 'run-auto'),
                ('tenant', 'run-full');
            INSERT INTO chat_run_execution_contexts (
                tenant_id, run_id, execution_mode, authority_role,
                authority_user_id, workspace_ref, sandbox_profile,
                approval_policy, model_id, reasoning_effort, created_at
            ) VALUES
                (
                    'tenant', 'run-standard', 'standard', 'user', 'user',
                    NULL, 'read-only', 'never', 'gpt-standard', 'low', 'now'
                ),
                (
                    'tenant', 'run-auto', 'developer', 'owner', 'owner',
                    'repository', 'workspace-write', 'never',
                    'gpt-auto', 'high', 'now'
                ),
                (
                    'tenant', 'run-full', 'developer', 'owner', 'owner',
                    'repository', 'danger-full-access', 'never',
                    'gpt-full', 'ultra', 'now'
                );
            PRAGMA user_version = 25;
            """
        )

        database.executescript(MIGRATION.read_text(encoding="utf-8"))

        assert database.execute("PRAGMA user_version").fetchone()[0] == 26
        assert [
            tuple(row)
            for row in database.execute(
                """
                SELECT run_id, execution_mode, access_mode,
                       access_policy_version, sandbox_profile,
                       approval_policy, approvals_reviewer, service_tier
                FROM chat_run_execution_contexts
                ORDER BY run_id
                """
            ).fetchall()
        ] == [
            (
                "run-auto",
                "developer",
                "auto",
                1,
                "workspace-write",
                "never",
                None,
                None,
            ),
            (
                "run-full",
                "developer",
                "full",
                2,
                "danger-full-access",
                "never",
                None,
                None,
            ),
            (
                "run-standard",
                "standard",
                "standard",
                2,
                "read-only",
                "never",
                None,
                None,
            ),
        ]
        assert database.execute(
            "PRAGMA foreign_key_check"
        ).fetchall() == []
        user_columns = {
            str(row[1])
            for row in database.execute("PRAGMA table_info(users)")
        }
        assert "preferred_service_tier" in user_columns
    finally:
        database.close()


def test_v26_startup_is_serialized_across_concurrent_initializers(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "concurrent-v25.db"
    database = sqlite3.connect(database_path, isolation_level=None)
    try:
        for migration_path in migration_paths():
            version = int(migration_path.name.split("_", 1)[0])
            if version > 25:
                break
            database.executescript(
                migration_path.read_text(encoding="utf-8")
            )
    finally:
        database.close()

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(initialize_database, database_path)
            for _index in range(8)
        ]
        for future in futures:
            future.result()

    database = sqlite3.connect(database_path)
    try:
        assert (
            database.execute("PRAGMA user_version").fetchone()[0]
            == LATEST_SCHEMA_VERSION
        )
        assert {
            str(row[1])
            for row in database.execute("PRAGMA table_info(users)")
        }.issuperset({"preferred_service_tier"})
        assert database.execute(
            "PRAGMA foreign_key_check"
        ).fetchall() == []
    finally:
        database.close()


def test_omitted_access_mode_keeps_v1_hash_and_legacy_developer_policy() -> None:
    raw = {
        "threadId": "thread_legacy_access_01",
        "runId": "run_legacy_access_01",
        "state": None,
        "messages": [
            {
                "id": "message_legacy_access_01",
                "role": "user",
                "content": "Исправь тесты.",
            }
        ],
        "tools": [],
        "context": [],
        "forwardedProps": {
            "agentProfile": "codex-cli",
            "executionMode": "developer",
        },
    }
    parsed = AgUiRunInput.model_validate(raw)

    assert parsed.forwarded_props.access_mode == "auto"
    assert canonical_run_payload(parsed) == raw
    assert request_hash(parsed) == sha256_text(canonical_json(raw))

    explicit = AgUiRunInput.model_validate(
        {
            **raw,
            "forwardedProps": {
                **raw["forwardedProps"],
                "accessMode": "auto",
            },
        }
    )
    assert canonical_run_payload(explicit) != raw
    assert request_hash(explicit) != request_hash(parsed)
