from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.database import migration_paths
from app.storage_node_executor import REQUIRED_STORAGE_GUARDS


MIGRATION_043 = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "043_storage_admin_restore_reconcile.sql"
)


def _apply_through(database: sqlite3.Connection, version: int) -> None:
    for migration in migration_paths():
        migration_version = int(migration.name.split("_", 1)[0])
        if migration_version > version:
            break
        database.executescript(migration.read_text(encoding="utf-8"))


def test_migration_043_preserves_v42_rows_and_rebuilds_exact_storage_ids(
    tmp_path: Path,
) -> None:
    database = sqlite3.connect(tmp_path / "storage-v42.db")
    database.row_factory = sqlite3.Row
    try:
        _apply_through(database, 42)
        database.execute("PRAGMA foreign_keys = ON")
        database.execute(
            """
            INSERT INTO tenants (id, name, created_at)
            VALUES ('tenant_storage_migration', 'Storage migration', 1)
            """
        )
        database.execute(
            """
            INSERT INTO users (
                id, tenant_id, email_normalized, email, name, role,
                password_hash, created_at, updated_at
            ) VALUES (
                'user_storage_migration', 'tenant_storage_migration',
                'storage-migration@example.com',
                'storage-migration@example.com',
                'Storage migration', 'owner', 'not-a-real-hash', 1, 1
            )
            """
        )
        preview_id = "spv_" + ("a" * 32)
        operation_id = "sop_" + ("b" * 32)
        quarantine_id = "sqn_" + ("c" * 32)
        audit_id = "saudit_" + ("d" * 32)
        database.execute(
            """
            INSERT INTO storage_admin_previews (
                id, actor_user_id, actor_tenant_id, authority_epoch,
                idempotency_key_hash, request_hash, node_id, category,
                operation_kind, project_id, quarantine_id,
                executor_preview_ref, node_generation, candidate_count,
                reclaimable_bytes, protected_item_count,
                protected_scopes_json, expires_at, consumed_at, created_at
            ) VALUES (
                ?, 'user_storage_migration', 'tenant_storage_migration', 1,
                ?, ?, 'home', 'project-quarantine', 'quarantine',
                'legacy-project', NULL, 'spx_v42', 'home:generation-v42',
                1, 250000, 0, ?, 1900000900, 1900000000, 1900000000
            )
            """,
            (
                preview_id,
                "1" * 64,
                "2" * 64,
                json.dumps(list(REQUIRED_STORAGE_GUARDS)),
            ),
        )
        database.execute(
            """
            INSERT INTO storage_admin_operations (
                id, preview_id, actor_user_id, actor_tenant_id,
                authority_epoch, idempotency_key_hash, request_hash,
                status, affected_item_count, reclaimed_bytes,
                quarantine_id, purge_eligible_at, error_code,
                created_at, completed_at
            ) VALUES (
                ?, ?, 'user_storage_migration', 'tenant_storage_migration',
                1, ?, ?, 'succeeded', 1, 0, ?, 1900604800, NULL,
                1900000000, 1900000001
            )
            """,
            (
                operation_id,
                preview_id,
                "3" * 64,
                "4" * 64,
                quarantine_id,
            ),
        )
        database.execute(
            """
            INSERT INTO storage_project_quarantines (
                id, node_id, project_id, status, size_bytes,
                quarantined_operation_id, quarantined_at,
                purge_eligible_at, purged_operation_id, purged_at
            ) VALUES (
                ?, 'home', 'legacy-project', 'retained', 250000,
                ?, 1900000001, 1900604800, NULL, NULL
            )
            """,
            (quarantine_id, operation_id),
        )
        database.execute(
            """
            INSERT INTO storage_admin_audit_events (
                id, actor_user_id, actor_tenant_id, authority_epoch,
                action, node_id, category, operation_kind, target_ref,
                preview_id, operation_id, details_json, created_at
            ) VALUES (
                ?, 'user_storage_migration', 'tenant_storage_migration', 1,
                'storage.operation.succeeded', 'home',
                'project-quarantine', 'quarantine', 'legacy-project',
                ?, ?, '{}', 1900000001
            )
            """,
            (audit_id, preview_id, operation_id),
        )
        database.commit()

        database.executescript(MIGRATION_043.read_text(encoding="utf-8"))

        assert database.execute("PRAGMA user_version").fetchone()[0] == 43
        assert database.execute(
            "SELECT reconcile_attempt_count FROM storage_admin_operations"
        ).fetchone()[0] == 0
        quarantine = database.execute(
            """
            SELECT id, status, restored_operation_id, restored_at
            FROM storage_project_quarantines
            """
        ).fetchone()
        assert dict(quarantine) == {
            "id": quarantine_id,
            "status": "retained",
            "restored_operation_id": None,
            "restored_at": None,
        }
        assert database.execute(
            "PRAGMA foreign_key_check"
        ).fetchall() == []

        for table, valid_id, invalid_id in (
            (
                "storage_admin_previews",
                preview_id,
                "spv_" + ("a" * 31) + "g",
            ),
            (
                "storage_admin_operations",
                operation_id,
                "sop_" + ("b" * 31) + "B",
            ),
            (
                "storage_project_quarantines",
                quarantine_id,
                "sqn_" + ("c" * 31) + "*",
            ),
            (
                "storage_admin_audit_events",
                audit_id,
                "saudit_" + ("d" * 31) + "z",
            ),
        ):
            with pytest.raises(sqlite3.IntegrityError):
                database.execute(
                    f"UPDATE {table} SET id = ? WHERE id = ?",
                    (invalid_id, valid_id),
                )
    finally:
        database.close()
