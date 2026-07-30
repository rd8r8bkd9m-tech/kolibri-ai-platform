#!/usr/bin/env python3
"""Atomic SQLite backup, restore, and read/write recovery rehearsal."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import os
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, NoReturn


COPY_CHUNK_BYTES = 1024 * 1024
MINIMUM_HEADROOM_BYTES = 64 * 1024 * 1024
PROBE_TABLE = "__kolibri_database_recovery_probe"
RELEASE_ID_PATTERN = re.compile(
    r"^kolibri-v3-[0-9a-f]{12}-[0-9a-f]{12}$"
)


class RecoveryError(RuntimeError):
    """Bounded recovery failure without database contents."""


@dataclass(frozen=True)
class DatabaseIdentity:
    device: int
    inode: int


@dataclass(frozen=True)
class Verification:
    schema_version: int
    table_count: int


def fail(code: str) -> NoReturn:
    raise RecoveryError(code)


def canonical_regular_file(path: Path) -> tuple[Path, DatabaseIdentity]:
    if not path.is_absolute():
        fail("database_path_not_absolute")
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError:
        fail("database_unreadable")
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or resolved != path
    ):
        fail("database_path_unsafe")
    return resolved, DatabaseIdentity(metadata.st_dev, metadata.st_ino)


def canonical_private_directory(path: Path) -> Path:
    if not path.is_absolute():
        fail("directory_path_not_absolute")
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError:
        fail("directory_unavailable")
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or resolved != path
        or metadata.st_mode & 0o022
    ):
        fail("directory_path_unsafe")
    return resolved


def validate_new_output(path: Path) -> tuple[Path, Path]:
    if not path.is_absolute():
        fail("output_path_not_absolute")
    if os.path.lexists(path):
        fail("output_already_exists")
    parent = canonical_private_directory(path.parent)
    if parent / path.name != path or path.name in {"", ".", ".."}:
        fail("output_path_unsafe")
    return path, parent


def assert_identity(path: Path, expected: DatabaseIdentity) -> None:
    try:
        metadata = path.lstat()
    except OSError:
        fail("database_changed_during_backup")
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_dev != expected.device
        or metadata.st_ino != expected.inode
    ):
        fail("database_changed_during_backup")


def sqlite_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"{path.as_uri()}?mode=ro",
        uri=True,
        timeout=30,
    )
    connection.row_factory = sqlite3.Row
    return connection


def verify_database(
    path: Path,
    *,
    expected_version: int | None,
    write_probe: bool,
) -> Verification:
    database, _identity = canonical_regular_file(path)
    connection = (
        sqlite3.connect(database, timeout=30)
        if write_probe
        else sqlite_read_only(database)
    )
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        integrity_rows = [
            str(row[0])
            for row in connection.execute("PRAGMA integrity_check").fetchall()
        ]
        if integrity_rows != ["ok"]:
            fail("integrity_check_failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            fail("foreign_key_check_failed")
        schema_version = int(
            connection.execute("PRAGMA user_version").fetchone()[0]
        )
        if expected_version is not None and schema_version != expected_version:
            fail("schema_version_mismatch")
        table_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                """
            ).fetchone()[0]
        )
        if write_probe:
            existing = connection.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table' AND name = ?
                """,
                (PROBE_TABLE,),
            ).fetchone()
            if existing is not None:
                fail("write_probe_name_conflict")
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    f"""
                    CREATE TABLE {PROBE_TABLE} (
                        id INTEGER PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    f"INSERT INTO {PROBE_TABLE}(value) VALUES (?)",
                    ("recovery-ok",),
                )
                value = connection.execute(
                    f"SELECT value FROM {PROBE_TABLE} WHERE id = 1"
                ).fetchone()
                if value is None or str(value[0]) != "recovery-ok":
                    fail("write_probe_failed")
            finally:
                connection.rollback()
            if connection.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table' AND name = ?
                """,
                (PROBE_TABLE,),
            ).fetchone() is not None:
                fail("write_probe_rollback_failed")
        return Verification(
            schema_version=schema_version,
            table_count=table_count,
        )
    finally:
        connection.close()


def fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_temporary(temporary: Path, output: Path, parent: Path) -> None:
    try:
        os.link(temporary, output)
    except FileExistsError:
        fail("output_already_exists")
    except OSError:
        fail("output_publish_failed")
    os.chmod(output, 0o600)
    fsync_directory(parent)
    temporary.unlink(missing_ok=True)


def require_capacity(directory: Path, required_bytes: int) -> None:
    free_bytes = shutil.disk_usage(directory).free
    if free_bytes < required_bytes + MINIMUM_HEADROOM_BYTES:
        fail("insufficient_disk")


def online_backup(source_path: Path, output_path: Path) -> Verification:
    source, source_identity = canonical_regular_file(source_path)
    output, parent = validate_new_output(output_path)
    require_capacity(parent, source.stat().st_size)
    descriptor, raw_temporary = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=parent,
    )
    os.close(descriptor)
    temporary = Path(raw_temporary)
    os.chmod(temporary, 0o600)
    try:
        source_connection = sqlite_read_only(source)
        destination_connection = sqlite3.connect(temporary, timeout=30)
        try:
            source_connection.backup(destination_connection)
            destination_connection.execute("PRAGMA journal_mode = DELETE")
            destination_connection.commit()
        finally:
            destination_connection.close()
            source_connection.close()
        assert_identity(source, source_identity)
        verification = verify_database(
            temporary,
            expected_version=None,
            write_probe=False,
        )
        fsync_file(temporary)
        publish_temporary(temporary, output, parent)
        return verification
    finally:
        temporary.unlink(missing_ok=True)


def copy_stream(source: BinaryIO, destination: BinaryIO) -> None:
    for chunk in iter(lambda: source.read(COPY_CHUNK_BYTES), b""):
        destination.write(chunk)


def atomic_restore(backup_path: Path, output_path: Path) -> None:
    backup, backup_identity = canonical_regular_file(backup_path)
    output, parent = validate_new_output(output_path)
    require_capacity(parent, backup.stat().st_size)
    descriptor, raw_temporary = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=parent,
    )
    temporary = Path(raw_temporary)
    try:
        os.chmod(temporary, 0o600)
        with backup.open("rb") as source, os.fdopen(descriptor, "wb") as target:
            copy_stream(source, target)
            target.flush()
            os.fsync(target.fileno())
        assert_identity(backup, backup_identity)
        publish_temporary(temporary, output, parent)
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(COPY_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_command(arguments: argparse.Namespace) -> None:
    verification = online_backup(arguments.source, arguments.output)
    print("database_backup=ok")
    print(f"database_schema_version={verification.schema_version}")
    print(f"database_table_count={verification.table_count}")
    print(f"database_sha256={sha256_file(arguments.output)}")


def scheduled_backup_command(arguments: argparse.Namespace) -> None:
    backup_root = canonical_private_directory(arguments.backup_root)
    if RELEASE_ID_PATTERN.fullmatch(arguments.release_id) is None:
        fail("release_id_invalid")
    now_epoch = (
        int(datetime.now(timezone.utc).timestamp())
        if arguments.now_epoch is None
        else arguments.now_epoch
    )
    if now_epoch < 0:
        fail("backup_time_invalid")
    observed_at = datetime.fromtimestamp(now_epoch, timezone.utc)
    scheduled_root = backup_root / "scheduled"
    day_root = scheduled_root / observed_at.strftime("%Y-%m-%d")
    for directory in (scheduled_root, day_root):
        try:
            directory.mkdir(mode=0o700)
            fsync_directory(directory.parent)
        except FileExistsError:
            pass
        canonical_private_directory(directory)
    output = day_root / (
        "kolibri-v3-"
        f"{observed_at.strftime('%Y%m%dT%H%M%SZ')}.db"
    )
    verification = online_backup(arguments.source, output)
    print("database_scheduled_backup=ok")
    print(f"database_schema_version={verification.schema_version}")
    print(f"database_table_count={verification.table_count}")
    print(f"database_sha256={sha256_file(output)}")
    print(f"release_id={arguments.release_id}")


def verify_command(arguments: argparse.Namespace) -> None:
    verification = verify_database(
        arguments.database,
        expected_version=arguments.expected_version,
        write_probe=arguments.write_probe,
    )
    print("database_verify=ok")
    print(f"database_schema_version={verification.schema_version}")
    print(f"database_table_count={verification.table_count}")
    print(f"database_sha256={sha256_file(arguments.database)}")


def rehearse_command(arguments: argparse.Namespace) -> None:
    source, _identity = canonical_regular_file(arguments.source)
    work_dir = canonical_private_directory(arguments.work_dir)
    require_capacity(work_dir, source.stat().st_size * 2)
    backup = work_dir / "kolibri-v3.backup.db"
    restored = work_dir / "kolibri-v3.restored.db"
    online_backup(source, backup)
    backup_verification = verify_database(
        backup,
        expected_version=arguments.expected_version,
        write_probe=False,
    )
    backup_digest = sha256_file(backup)
    atomic_restore(backup, restored)
    restored_digest = sha256_file(restored)
    if restored_digest != backup_digest:
        fail("restored_snapshot_digest_mismatch")
    restored_verification = verify_database(
        restored,
        expected_version=arguments.expected_version,
        write_probe=True,
    )
    if restored_verification != backup_verification:
        fail("restored_database_shape_mismatch")
    print("database_rehearsal=ok")
    print(f"database_schema_version={restored_verification.schema_version}")
    print(f"database_table_count={restored_verification.table_count}")
    print(f"database_snapshot_sha256={backup_digest}")
    print("database_write_probe=rolled_back")


def parser() -> argparse.ArgumentParser:
    command_parser = argparse.ArgumentParser(
        description="Kolibri V3 SQLite backup and recovery rehearsal",
    )
    commands = command_parser.add_subparsers(dest="command", required=True)

    backup_parser = commands.add_parser("backup")
    backup_parser.add_argument("--source", type=Path, required=True)
    backup_parser.add_argument("--output", type=Path, required=True)
    backup_parser.set_defaults(handler=backup_command)

    scheduled_parser = commands.add_parser("scheduled-backup")
    scheduled_parser.add_argument("--source", type=Path, required=True)
    scheduled_parser.add_argument("--backup-root", type=Path, required=True)
    scheduled_parser.add_argument("--release-id", required=True)
    scheduled_parser.add_argument("--now-epoch", type=int)
    scheduled_parser.set_defaults(handler=scheduled_backup_command)

    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--database", type=Path, required=True)
    verify_parser.add_argument("--expected-version", type=int)
    verify_parser.add_argument("--write-probe", action="store_true")
    verify_parser.set_defaults(handler=verify_command)

    rehearse_parser = commands.add_parser("rehearse")
    rehearse_parser.add_argument("--source", type=Path, required=True)
    rehearse_parser.add_argument("--work-dir", type=Path, required=True)
    rehearse_parser.add_argument(
        "--expected-version",
        type=int,
        required=True,
    )
    rehearse_parser.set_defaults(handler=rehearse_command)
    return command_parser


def main() -> None:
    arguments = parser().parse_args()
    if getattr(arguments, "expected_version", 0) is not None and getattr(
        arguments,
        "expected_version",
        0,
    ) < 0:
        fail("expected_version_invalid")
    arguments.handler(arguments)


if __name__ == "__main__":
    try:
        main()
    except RecoveryError as error:
        print(f"database_recovery_error={error}", file=sys.stderr)
        raise SystemExit(3) from None
    except (OSError, sqlite3.Error):
        print("database_recovery_error=database_operation_failed", file=sys.stderr)
        raise SystemExit(3) from None
