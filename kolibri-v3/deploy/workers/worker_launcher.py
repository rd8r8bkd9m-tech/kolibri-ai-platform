#!/usr/bin/env python3
"""Fail-closed launcher for the canonical Kolibri V3 background workers.

The launcher intentionally owns only process-level concerns:

* verify that every worker points at the backend's canonical SQLite database;
* validate the worker-specific production configuration before dispatch;
* hold a non-blocking singleton lock for the lifetime of the worker; and
* expose only an allowlisted module/argument combination.

Durable command ownership remains in the database leases implemented by the
worker modules.  The local lock prevents an accidental duplicate systemd unit
on the same V3 host; it is not presented as a distributed lock.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import tempfile
from typing import NoReturn


EX_DATAERR = 65
EX_CONFIG = 78
EX_TEMPFAIL = 75
_SAFE_CODE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.:-]{0,127}$")
_RELEASE_ID = re.compile(r"^kolibri-v3-[0-9a-f]{12}-[0-9a-f]{12}$")
_RELEASE_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_WORKER_COMMANDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "product-run": ("app.product_run_worker", ()),
    "provider-enrollment": ("app.provider_enrollment_worker", ()),
    # Deliberately no --apply variant. Mutation is blocked until the
    # reconciliation job has a durable, database-backed ownership fence.
    "estimate-audit": ("app.estimate_reconciliation", ()),
}
_WORKER_CREDENTIALS: dict[str, tuple[tuple[str, str], ...]] = {
    "product-run": (
        (
            "KOLIBRI_V3_HOME_PRODUCT_COMMAND_TOKEN_FILE",
            "home-product-command-token",
        ),
        (
            "KOLIBRI_V3_HOME_PRODUCT_IDENTITY_HMAC_KEY_FILE",
            "home-product-identity-hmac-key",
        ),
    ),
    "provider-enrollment": (
        (
            "KOLIBRI_V3_PROVIDER_AUTHORITY_COMMAND_TOKEN_FILE",
            "provider-authority-command-token",
        ),
        (
            "KOLIBRI_V3_PROVIDER_AUTHORITY_IDENTITY_HMAC_KEY_FILE",
            "provider-authority-identity-hmac-key",
        ),
    ),
}


class WorkerConfigurationError(RuntimeError):
    """A public-safe configuration failure."""


class WorkerOwnershipError(RuntimeError):
    """Another process already owns this worker role."""


def _safe_private_directory(raw_path: str, *, code: str) -> Path:
    path = Path(raw_path)
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError:
        raise WorkerConfigurationError(code) from None
    if (
        not path.is_absolute()
        or path.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or resolved != path
        or metadata.st_uid not in {0, os.geteuid()}
        or metadata.st_mode & 0o027
    ):
        raise WorkerConfigurationError(code)
    return path


def materialize_systemd_credentials(worker_kind: str) -> None:
    """Copy systemd's 0440 credentials into the private RuntimeDirectory.

    systemd intentionally exposes loaded credentials as root-owned read-only
    files. Application secret readers require service-owned mode 0600 files,
    so the worker performs one bounded, atomic copy before configuration
    validation. No credential is persisted outside the ephemeral runtime
    directory.
    """

    try:
        credentials = _WORKER_CREDENTIALS[worker_kind]
    except KeyError:
        raise WorkerConfigurationError(
            "worker_credentials_not_applicable"
        ) from None
    source_root = _safe_private_directory(
        _required_environment("CREDENTIALS_DIRECTORY"),
        code="systemd_credentials_directory_invalid",
    )
    target_root = _safe_private_directory(
        _required_environment("KOLIBRI_WORKER_CREDENTIAL_DIRECTORY"),
        code="worker_credentials_directory_invalid",
    )
    if target_root.stat().st_uid != os.geteuid():
        raise WorkerConfigurationError(
            "worker_credentials_directory_invalid"
        )

    for environment_name, credential_name in credentials:
        source_path = source_root / credential_name
        expected_target = target_root / credential_name
        if os.getenv(environment_name, "") != os.fspath(expected_target):
            raise WorkerConfigurationError(
                "worker_credential_target_invalid"
            )
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            source_descriptor = os.open(source_path, flags)
        except OSError:
            raise WorkerConfigurationError(
                "systemd_credential_unavailable"
            ) from None
        try:
            source_metadata = os.fstat(source_descriptor)
            source_root_metadata = source_root.stat()
            if (
                not stat.S_ISREG(source_metadata.st_mode)
                or source_metadata.st_uid != source_root_metadata.st_uid
                or stat.S_IMODE(source_metadata.st_mode) != 0o440
                or not 16 <= source_metadata.st_size <= 64 * 1024
            ):
                raise WorkerConfigurationError(
                    "systemd_credential_invalid"
                )
            value = os.read(source_descriptor, 64 * 1024 + 1)
            if len(value) != source_metadata.st_size:
                raise WorkerConfigurationError(
                    "systemd_credential_invalid"
                )
        finally:
            os.close(source_descriptor)

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{credential_name}.",
            dir=target_root,
        )
        temporary_path = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            written = 0
            while written < len(value):
                written += os.write(descriptor, value[written:])
            os.fsync(descriptor)
            metadata = os.fstat(descriptor)
            if (
                metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                raise WorkerConfigurationError(
                    "worker_credential_copy_invalid"
                )
            os.close(descriptor)
            descriptor = -1
            os.replace(temporary_path, expected_target)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            temporary_path.unlink(missing_ok=True)


def _required_environment(name: str) -> str:
    value = os.getenv(name, "")
    if (
        not value
        or value != value.strip()
        or any(character in value for character in "\r\n\0")
    ):
        raise WorkerConfigurationError(f"{name.lower()}_missing")
    return value


def _database_path(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise WorkerConfigurationError("database_url_not_sqlite")
    raw_path = database_url.removeprefix("sqlite:///")
    path = Path(raw_path)
    if not path.is_absolute():
        raise WorkerConfigurationError("database_path_not_absolute")
    return path


def validate_release_identity() -> tuple[str, str]:
    """Require the exact immutable release identity shared by all processes."""

    release_id = _required_environment("KOLIBRI_RELEASE_ID")
    release_commit = _required_environment("KOLIBRI_RELEASE_COMMIT")
    if _RELEASE_ID.fullmatch(release_id) is None:
        raise WorkerConfigurationError("release_id_invalid")
    if _RELEASE_COMMIT.fullmatch(release_commit) is None:
        raise WorkerConfigurationError("release_commit_invalid")
    return release_id, release_commit


def validate_canonical_database() -> Path:
    """Validate the exact backend DB without creating or modifying it."""

    if os.getenv("KOLIBRI_V3_ENV") != "production":
        raise WorkerConfigurationError("production_environment_required")

    database_url = _required_environment("KOLIBRI_V3_DATABASE_URL")
    expected_url = _required_environment(
        "KOLIBRI_WORKER_EXPECTED_DATABASE_URL"
    )
    if database_url != expected_url:
        raise WorkerConfigurationError("database_url_not_canonical")

    database_path = _database_path(database_url)
    try:
        metadata = database_path.lstat()
        parent_metadata = database_path.parent.lstat()
    except OSError:
        raise WorkerConfigurationError("canonical_database_missing") from None
    if (
        database_path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or database_path.parent.is_symlink()
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or database_path.resolve(strict=True) != database_path
        or database_path.parent.resolve(strict=True) != database_path.parent
    ):
        raise WorkerConfigurationError("canonical_database_unsafe")
    if metadata.st_uid != os.geteuid():
        raise WorkerConfigurationError("canonical_database_owner_invalid")
    if metadata.st_mode & 0o077 or parent_metadata.st_mode & 0o002:
        raise WorkerConfigurationError(
            "canonical_database_permissions_invalid"
        )
    if not os.access(database_path, os.R_OK | os.W_OK):
        raise WorkerConfigurationError("canonical_database_not_writable")
    if not os.access(database_path.parent, os.W_OK | os.X_OK):
        raise WorkerConfigurationError(
            "canonical_database_directory_not_writable"
        )
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{database_path}{suffix}")
        try:
            sidecar_metadata = sidecar.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            raise WorkerConfigurationError(
                "canonical_database_sidecar_unsafe"
            ) from None
        if (
            sidecar.is_symlink()
            or not stat.S_ISREG(sidecar_metadata.st_mode)
            or sidecar_metadata.st_uid != os.geteuid()
            or sidecar_metadata.st_mode & 0o077
        ):
            raise WorkerConfigurationError(
                "canonical_database_sidecar_unsafe"
            )
    return database_path


def _runtime_error_code(error: BaseException) -> str:
    candidate = getattr(error, "code", "")
    if isinstance(candidate, str) and _SAFE_CODE.fullmatch(candidate):
        return candidate
    name = error.__class__.__name__
    if _SAFE_CODE.fullmatch(name):
        return name
    return "runtime_configuration_invalid"


def validate_runtime_configuration(worker_kind: str) -> None:
    """Reuse application validators without logging secret values."""

    backend_directory = Path.cwd()
    if not (backend_directory / "app" / "config.py").is_file():
        raise WorkerConfigurationError("backend_working_directory_invalid")
    sys.path.insert(0, str(backend_directory))

    try:
        from app.config import Settings

        settings = Settings.from_env()
        if worker_kind == "product-run":
            from app.home_runtime import ProductRunExecutionSettings

            settings.require_product_authority_grant()
            ProductRunExecutionSettings.from_env()
        elif worker_kind == "provider-enrollment":
            from app.provider_authority import ProviderAuthoritySettings

            if not settings.provider_authority_dispatch_configured:
                raise WorkerConfigurationError(
                    "provider_authority_dispatch_not_configured"
                )
            authority_settings = ProviderAuthoritySettings.from_env()
            if (
                settings.provider_enrollment_lease_seconds
                < authority_settings.request_timeout_seconds + 1
            ):
                raise WorkerConfigurationError(
                    "provider_authority_lease_too_short"
                )
        elif worker_kind != "estimate-audit":
            raise WorkerConfigurationError("worker_kind_invalid")
    except WorkerConfigurationError:
        raise
    except Exception as error:
        raise WorkerConfigurationError(
            _runtime_error_code(error)
        ) from None


def runtime_audit(
    database_path: Path,
    *,
    now: datetime | None = None,
    stale_after_seconds: int | None = None,
) -> dict[str, object]:
    """Return bounded, identifier-free diagnostics from the canonical DB."""

    if stale_after_seconds is None:
        raw_threshold = os.getenv(
            "KOLIBRI_WORKER_STALE_RUN_SECONDS",
            "3600",
        )
        try:
            stale_after_seconds = int(raw_threshold)
        except ValueError:
            raise WorkerConfigurationError(
                "stale_run_threshold_invalid"
            ) from None
    if not 60 <= stale_after_seconds <= 24 * 60 * 60:
        raise WorkerConfigurationError("stale_run_threshold_invalid")

    audit_now = now or datetime.now(timezone.utc)
    if audit_now.tzinfo is None:
        raise WorkerConfigurationError("audit_time_requires_timezone")
    cutoff = (
        audit_now.astimezone(timezone.utc)
        - timedelta(seconds=stale_after_seconds)
    ).isoformat()
    uri = f"{database_path.as_uri()}?mode=ro"
    try:
        database = sqlite3.connect(uri, uri=True, timeout=5)
    except sqlite3.Error:
        raise WorkerConfigurationError(
            "canonical_database_read_failed"
        ) from None
    database.row_factory = sqlite3.Row
    try:
        required_tables = {
            "chat_runs",
            "chat_run_execution_contexts",
            "product_run_outbox",
        }
        present_tables = {
            str(row["name"])
            for row in database.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name IN (
                      'chat_runs',
                      'chat_run_execution_contexts',
                      'product_run_outbox'
                  )
                """
            ).fetchall()
        }
        if present_tables != required_tables:
            raise WorkerConfigurationError(
                "runtime_audit_schema_missing"
            )

        stale_rows = database.execute(
            """
            SELECT
                COALESCE(context.execution_mode, 'standard')
                    AS execution_mode,
                COALESCE(outbox.state, 'missing') AS outbox_state,
                runs.heartbeat_at
            FROM chat_runs AS runs
            LEFT JOIN chat_run_execution_contexts AS context
              ON context.tenant_id = runs.tenant_id
             AND context.run_id = runs.id
            LEFT JOIN product_run_outbox AS outbox
              ON outbox.tenant_id = runs.tenant_id
             AND outbox.run_id = runs.id
            WHERE runs.status = 'running'
              AND (
                  julianday(runs.heartbeat_at) IS NULL
                  OR julianday(runs.heartbeat_at) < julianday(?)
              )
            ORDER BY runs.heartbeat_at, runs.tenant_id, runs.id
            """,
            (cutoff,),
        ).fetchall()
        blocked_outbox = int(
            database.execute(
                """
                SELECT COUNT(*)
                FROM product_run_outbox
                WHERE state = 'blocked'
                """
            ).fetchone()[0]
        )
    except sqlite3.Error:
        raise WorkerConfigurationError(
            "runtime_audit_query_failed"
        ) from None
    finally:
        database.close()

    by_mode: dict[str, int] = {}
    by_outbox_state: dict[str, int] = {}
    oldest_heartbeat_at: str | None = None
    for row in stale_rows:
        mode = str(row["execution_mode"])
        outbox_state = str(row["outbox_state"])
        by_mode[mode] = by_mode.get(mode, 0) + 1
        by_outbox_state[outbox_state] = (
            by_outbox_state.get(outbox_state, 0) + 1
        )
        heartbeat = str(row["heartbeat_at"])
        if oldest_heartbeat_at is None or heartbeat < oldest_heartbeat_at:
            oldest_heartbeat_at = heartbeat

    stale_total = len(stale_rows)
    return {
        "schema_id": "kolibri.v3.worker_runtime_audit.v1",
        "schema_version": "1.0",
        "checked_at": audit_now.astimezone(timezone.utc).isoformat(),
        "stale_after_seconds": stale_after_seconds,
        "stale_running": {
            "total": stale_total,
            "by_execution_mode": dict(sorted(by_mode.items())),
            "by_outbox_state": dict(sorted(by_outbox_state.items())),
            "oldest_heartbeat_at": oldest_heartbeat_at,
        },
        "blocked_product_outbox": blocked_outbox,
        "gate": "blocked" if stale_total else "pass",
    }


def run_reconciliation_audit(database_path: Path) -> int:
    """Run the existing estimate dry-run plus the runtime consistency gate."""

    try:
        from app.estimate_reconciliation import (
            reconcile_ai_candidate_estimates,
        )
    except Exception as error:
        raise WorkerConfigurationError(
            _runtime_error_code(error)
        ) from None

    uri = f"{database_path.as_uri()}?mode=ro"
    database = sqlite3.connect(
        uri,
        uri=True,
        timeout=5,
        isolation_level=None,
    )
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys = ON")
    database.execute("PRAGMA busy_timeout = 5000")
    try:
        estimate_results = reconcile_ai_candidate_estimates(
            database,
            apply=False,
        )
    finally:
        database.close()
    runtime_result = runtime_audit(database_path)
    print(
        json.dumps(
            {
                "schema_id": "kolibri.v3.reconciliation_audit.v1",
                "schema_version": "1.0",
                "runtime": runtime_result,
                "estimate_repairs": [
                    asdict(result) for result in estimate_results
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    stale = runtime_result["stale_running"]
    if not isinstance(stale, dict):
        raise WorkerConfigurationError("runtime_audit_result_invalid")
    return EX_DATAERR if int(stale["total"]) else 0


def acquire_owner_lock() -> int:
    """Acquire and retain the systemd RuntimeDirectory singleton lock."""

    lock_path = Path(_required_environment("KOLIBRI_WORKER_LOCK_PATH"))
    if not lock_path.is_absolute():
        raise WorkerConfigurationError("worker_lock_path_not_absolute")
    try:
        parent_metadata = lock_path.parent.lstat()
    except OSError:
        raise WorkerConfigurationError(
            "worker_lock_directory_missing"
        ) from None
    if (
        lock_path.parent.is_symlink()
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.geteuid()
        or parent_metadata.st_mode & 0o022
    ):
        raise WorkerConfigurationError("worker_lock_directory_unsafe")

    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError:
        raise WorkerConfigurationError("worker_lock_open_failed") from None
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_mode & 0o077
        ):
            raise WorkerConfigurationError("worker_lock_file_unsafe")
        try:
            fcntl.flock(
                descriptor,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            raise WorkerOwnershipError("worker_role_already_owned") from None
        os.set_inheritable(descriptor, True)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def worker_command(worker_kind: str) -> tuple[str, ...]:
    try:
        module, arguments = _WORKER_COMMANDS[worker_kind]
    except KeyError:
        raise WorkerConfigurationError("worker_kind_invalid") from None
    return (sys.executable, "-m", module, *arguments)


def _exec_worker(worker_kind: str) -> NoReturn:
    # Keep this descriptor reachable until exec. It is intentionally inherited
    # so the kernel releases ownership only when the worker process exits.
    owner_descriptor = acquire_owner_lock()
    if owner_descriptor < 0:
        raise AssertionError("unreachable")
    command = worker_command(worker_kind)
    os.execvpe(command[0], command, os.environ.copy())
    raise AssertionError("unreachable")


def run_worker(worker_kind: str, database_path: Path) -> int:
    if worker_kind == "estimate-audit":
        owner_descriptor = acquire_owner_lock()
        if owner_descriptor < 0:
            raise AssertionError("unreachable")
        return run_reconciliation_audit(database_path)
    _exec_worker(worker_kind)
    raise AssertionError("unreachable")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch one allowlisted Kolibri V3 worker."
    )
    parser.add_argument("worker_kind", choices=tuple(_WORKER_COMMANDS))
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate production configuration without taking ownership.",
    )
    parser.add_argument(
        "--materialize-credentials",
        action="store_true",
        help="Copy systemd credentials into the private RuntimeDirectory.",
    )
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        if arguments.materialize_credentials:
            if arguments.check:
                raise WorkerConfigurationError(
                    "worker_launcher_mode_conflict"
                )
            materialize_systemd_credentials(arguments.worker_kind)
            return 0
        database_path = validate_canonical_database()
        validate_release_identity()
        validate_runtime_configuration(arguments.worker_kind)
        if arguments.check:
            return 0
        return run_worker(arguments.worker_kind, database_path)
    except WorkerOwnershipError as error:
        print(f"worker_start_refused={error}", file=sys.stderr)
        return EX_TEMPFAIL
    except WorkerConfigurationError as error:
        print(f"worker_config_error={error}", file=sys.stderr)
        return EX_CONFIG
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
