from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from app.database import connect_database, initialize_database, migration_paths
from app.runtime_readiness import (
    clear_product_worker_heartbeat,
    product_worker_is_ready,
    record_product_worker_heartbeat,
)


RELEASE_ID = "kolibri-v3-0123456789ab-abcdef012345"
RELEASE_COMMIT = "0123456789abcdef0123456789abcdef01234567"


def test_migration_044_adds_strict_release_bound_worker_heartbeat(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "worker-v43.db"
    database = sqlite3.connect(database_path)
    try:
        for migration in migration_paths():
            version = int(migration.name.split("_", 1)[0])
            if version > 43:
                break
            database.executescript(migration.read_text(encoding="utf-8"))
        assert database.execute("PRAGMA user_version").fetchone()[0] == 43
    finally:
        database.close()

    initialize_database(database_path)
    migrated = connect_database(database_path)
    try:
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == 44
        columns = {
            str(row["name"])
            for row in migrated.execute(
                "PRAGMA table_info(runtime_worker_heartbeats)"
            ).fetchall()
        }
        assert columns == {
            "worker_kind",
            "instance_id",
            "release_id",
            "release_commit",
            "process_id",
            "started_at",
            "heartbeat_at",
        }
        with pytest.raises(sqlite3.IntegrityError):
            migrated.execute(
                """
                INSERT INTO runtime_worker_heartbeats (
                    worker_kind, instance_id, release_id, release_commit,
                    process_id, started_at, heartbeat_at
                ) VALUES ('unknown', 'worker-test-01', ?, ?, 1, 1, 1)
                """,
                (RELEASE_ID, RELEASE_COMMIT),
            )
    finally:
        migrated.close()


def test_worker_heartbeat_is_exact_fresh_and_instance_fenced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "worker.db"
    initialize_database(database_path)
    monkeypatch.setenv("KOLIBRI_RELEASE_ID", RELEASE_ID)
    monkeypatch.setenv("KOLIBRI_RELEASE_COMMIT", RELEASE_COMMIT)

    record_product_worker_heartbeat(
        database_path,
        instance_id="product-worker-test-01",
    )
    database = connect_database(database_path)
    try:
        database.execute(
            """
            UPDATE runtime_worker_heartbeats
            SET heartbeat_at = unixepoch()
            WHERE worker_kind = 'product-run'
            """
        )
        assert product_worker_is_ready(
            database,
            release_id=RELEASE_ID,
            release_commit=RELEASE_COMMIT,
            max_age_seconds=30,
        )
        assert not product_worker_is_ready(
            database,
            release_id="kolibri-v3-aaaaaaaaaaaa-bbbbbbbbbbbb",
            release_commit=RELEASE_COMMIT,
            max_age_seconds=30,
        )
        database.execute(
            """
            UPDATE runtime_worker_heartbeats
            SET started_at = unixepoch() - 31,
                heartbeat_at = unixepoch() - 31
            WHERE worker_kind = 'product-run'
            """
        )
        assert not product_worker_is_ready(
            database,
            release_id=RELEASE_ID,
            release_commit=RELEASE_COMMIT,
            max_age_seconds=30,
        )
    finally:
        database.close()

    clear_product_worker_heartbeat(
        database_path,
        instance_id="replacement-worker-test-02",
    )
    retained = connect_database(database_path)
    try:
        assert (
            retained.execute(
                "SELECT COUNT(*) FROM runtime_worker_heartbeats"
            ).fetchone()[0]
            == 1
        )
    finally:
        retained.close()

    clear_product_worker_heartbeat(
        database_path,
        instance_id="product-worker-test-01",
    )
    cleared = connect_database(database_path)
    try:
        assert (
            cleared.execute(
                "SELECT COUNT(*) FROM runtime_worker_heartbeats"
            ).fetchone()[0]
            == 0
        )
    finally:
        cleared.close()
