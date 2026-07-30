from __future__ import annotations

import fcntl
import os
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi import Request

from .config import Settings

_MIGRATIONS_DIRECTORY = Path(__file__).resolve().parents[1] / "migrations"


def migration_paths() -> tuple[Path, ...]:
    paths = tuple(sorted(_MIGRATIONS_DIRECTORY.glob("[0-9][0-9][0-9]_*.sql")))
    if not paths:
        raise RuntimeError("Kolibri V3 database migrations are missing")
    return paths


def database_path(database_url_or_path: str | Path) -> Path | str:
    if isinstance(database_url_or_path, Path):
        return database_url_or_path

    value = database_url_or_path.strip()
    if value == "sqlite:///:memory:":
        return ":memory:"
    if not value.startswith("sqlite:///"):
        raise ValueError("only sqlite:/// database URLs are supported")
    raw_path = value.removeprefix("sqlite:///")
    if not raw_path or raw_path.startswith("file:"):
        raise ValueError("SQLite database path is invalid")
    return Path(raw_path)


def connect_database(
    database_url_or_path: str | Path | None = None,
) -> sqlite3.Connection:
    """Open a raw SQLite connection owned and closed by the caller."""

    if database_url_or_path is None:
        database_url_or_path = Settings.from_env().database_url
    path = database_path(database_url_or_path)
    if isinstance(path, Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        filename = str(path)
    else:
        filename = path

    connection = sqlite3.connect(
        filename,
        timeout=5.0,
        isolation_level=None,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    if filename != ":memory:":
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
    return connection


@contextmanager
def _migration_lock(
    database_url_or_path: str | Path,
) -> Iterator[None]:
    path = database_path(database_url_or_path)
    if not isinstance(path, Path):
        yield
        return
    lock_path = path.resolve().parent / f".{path.name}.migration.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        lock_path,
        os.O_CREAT | os.O_RDWR,
        0o600,
    )
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def initialize_database(database_url_or_path: str | Path) -> None:
    with _migration_lock(database_url_or_path):
        connection = connect_database(database_url_or_path)
        try:
            migrations = migration_paths()
            current_version = int(
                connection.execute("PRAGMA user_version").fetchone()[0]
            )
            latest_version = int(migrations[-1].name.split("_", 1)[0])
            if current_version > latest_version:
                raise RuntimeError(
                    "Kolibri V3 database schema is newer than this runtime"
                )
            for migration_path in migrations:
                migration_version = int(
                    migration_path.name.split("_", 1)[0]
                )
                if migration_version <= current_version:
                    continue
                connection.executescript(
                    migration_path.read_text(encoding="utf-8")
                )
                applied_version = int(
                    connection.execute("PRAGMA user_version").fetchone()[0]
                )
                if applied_version != migration_version:
                    raise RuntimeError(
                        "Kolibri V3 migration did not set its schema version"
                    )
                current_version = applied_version
        finally:
            connection.close()


@contextmanager
def transaction(
    connection: sqlite3.Connection,
    *,
    immediate: bool = False,
) -> Iterator[sqlite3.Connection]:
    """Run a transaction, using a savepoint when called from another slice."""

    if connection.in_transaction:
        savepoint = f"kolibri_{uuid.uuid4().hex}"
        connection.execute(f"SAVEPOINT {savepoint}")
        try:
            yield connection
        except BaseException:
            connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            connection.execute(f"RELEASE SAVEPOINT {savepoint}")
            raise
        else:
            connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        return

    connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield connection
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()


def get_database(request: Request) -> Iterator[sqlite3.Connection]:
    settings: Settings = request.app.state.settings
    connection = connect_database(settings.database_url)
    try:
        yield connection
    finally:
        connection.close()


# A descriptive alias for callers that treat the request connection as a session.
get_session = get_database
