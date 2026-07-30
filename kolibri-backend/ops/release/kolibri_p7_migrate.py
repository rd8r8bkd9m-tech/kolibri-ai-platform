#!/usr/bin/env python3
"""Migrate one drained P7 SQLite copy and prove the exact schema head."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3


EXPECTED_HEAD = "012_estimate_tax_regime"


class MigrationGateError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def migrate(database: Path, expected_head: str = EXPECTED_HEAD) -> dict[str, object]:
    database = database.expanduser().resolve(strict=True)
    if not database.is_file() or database.is_symlink():
        raise MigrationGateError("candidate_database_invalid")

    # Import from the extracted, signature-bound backend whose working
    # directory is set by the executor.  No mutable system package owns the
    # migration chain.
    from sqlalchemy import create_engine, text
    from app.schema_migrations import ensure_database_schema

    engine = create_engine(f"sqlite:///{database}")
    try:
        actual = ensure_database_schema(engine)
        if actual != expected_head:
            raise MigrationGateError("candidate_schema_head_mismatch")
        with engine.connect() as connection:
            quick = connection.execute(text("PRAGMA quick_check")).scalar_one()
            foreign_keys = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if quick != "ok" or foreign_keys or revision != expected_head:
            raise MigrationGateError("candidate_database_integrity_failed")
    finally:
        engine.dispose()

    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        quick = connection.execute("PRAGMA quick_check").fetchone()
        if quick != ("ok",):
            raise MigrationGateError("candidate_database_integrity_failed")
    return {
        "status": "migrated_verified",
        "schema_head": expected_head,
        "database_sha256": sha256_file(database),
        "size_bytes": database.stat().st_size,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--expected-head", default=EXPECTED_HEAD)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = migrate(Path(args.database), args.expected_head)
    except (MigrationGateError, OSError, sqlite3.Error) as exc:
        reason = str(exc) if isinstance(exc, MigrationGateError) else "candidate_migration_failed"
        print(json.dumps({"status": "failed", "reason": reason}, sort_keys=True))
        return 1
    except Exception:
        # The root executor suppresses subprocess output, but the helper is
        # also safe when invoked manually: never emit a traceback containing
        # filesystem or database context across this release boundary.
        print(json.dumps({"status": "failed", "reason": "candidate_migration_failed"}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
