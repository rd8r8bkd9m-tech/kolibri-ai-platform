from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.database import initialize_database, migration_paths


LATEST_SCHEMA_VERSION = int(migration_paths()[-1].name.split("_", 1)[0])


def _create_v31_database_without_mobile_tables(path: Path) -> None:
    database = sqlite3.connect(path, isolation_level=None)
    try:
        for migration_path in migration_paths():
            version = int(migration_path.name.split("_", 1)[0])
            if version > 29:
                break
            database.executescript(migration_path.read_text(encoding="utf-8"))
        database.execute("PRAGMA user_version = 31")
    finally:
        database.close()


def test_mobile_auth_migration_upgrades_the_deployed_v31_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "deployed-v31.db"
    _create_v31_database_without_mobile_tables(database_path)

    initialize_database(database_path)

    database = sqlite3.connect(database_path)
    try:
        assert (
            database.execute("PRAGMA user_version").fetchone()[0]
            == LATEST_SCHEMA_VERSION
        )
        assert {
            row[0]
            for row in database.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name LIKE 'mobile_%'
                """
            )
        } == {
            "mobile_access_tokens",
            "mobile_auth_events",
            "mobile_device_sessions",
            "mobile_refresh_tokens",
        }
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        database.close()


def test_runtime_refuses_a_database_from_a_newer_release(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "future.db"
    database = sqlite3.connect(database_path)
    try:
        database.execute(
            f"PRAGMA user_version = {LATEST_SCHEMA_VERSION + 1}"
        )
    finally:
        database.close()

    with pytest.raises(
        RuntimeError,
        match="database schema is newer than this runtime",
    ):
        initialize_database(database_path)
