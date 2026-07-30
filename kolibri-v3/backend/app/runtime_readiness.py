"""Release-bound worker heartbeat contract for production readiness."""

from __future__ import annotations

import os
from pathlib import Path
import re
import time

from .database import connect_database, transaction


PRODUCT_WORKER_KIND = "product-run"
_INSTANCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,159}$")
_RELEASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RELEASE_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class RuntimeReadinessError(RuntimeError):
    """A bounded configuration or persistence failure."""


def _release_identity() -> tuple[str, str]:
    release_id = os.getenv("KOLIBRI_RELEASE_ID", "")
    release_commit = os.getenv("KOLIBRI_RELEASE_COMMIT", "")
    if (
        _RELEASE_ID_PATTERN.fullmatch(release_id) is None
        or _RELEASE_COMMIT_PATTERN.fullmatch(release_commit) is None
    ):
        raise RuntimeReadinessError("release_identity_invalid")
    return release_id, release_commit


def record_product_worker_heartbeat(
    database_url: str | Path,
    *,
    instance_id: str,
    now: int | None = None,
) -> None:
    """Publish one exact-release heartbeat without exposing credentials."""

    if _INSTANCE_PATTERN.fullmatch(instance_id) is None:
        raise RuntimeReadinessError("worker_instance_invalid")
    release_id, release_commit = _release_identity()
    observed_at = int(time.time()) if now is None else now
    if observed_at < 0:
        raise RuntimeReadinessError("worker_time_invalid")
    process_id = os.getpid()
    database = connect_database(database_url)
    try:
        with transaction(database, immediate=True):
            database.execute(
                """
                INSERT INTO runtime_worker_heartbeats (
                    worker_kind, instance_id, release_id, release_commit,
                    process_id, started_at, heartbeat_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(worker_kind) DO UPDATE SET
                    instance_id = excluded.instance_id,
                    release_id = excluded.release_id,
                    release_commit = excluded.release_commit,
                    process_id = excluded.process_id,
                    started_at = CASE
                        WHEN runtime_worker_heartbeats.instance_id
                             = excluded.instance_id
                        THEN runtime_worker_heartbeats.started_at
                        ELSE excluded.started_at
                    END,
                    heartbeat_at = excluded.heartbeat_at
                """,
                (
                    PRODUCT_WORKER_KIND,
                    instance_id,
                    release_id,
                    release_commit,
                    process_id,
                    observed_at,
                    observed_at,
                ),
            )
    finally:
        database.close()


def clear_product_worker_heartbeat(
    database_url: str | Path,
    *,
    instance_id: str,
) -> None:
    """Remove only this worker's row during graceful shutdown."""

    if _INSTANCE_PATTERN.fullmatch(instance_id) is None:
        raise RuntimeReadinessError("worker_instance_invalid")
    database = connect_database(database_url)
    try:
        with transaction(database, immediate=True):
            database.execute(
                """
                DELETE FROM runtime_worker_heartbeats
                WHERE worker_kind = ? AND instance_id = ?
                """,
                (PRODUCT_WORKER_KIND, instance_id),
            )
    finally:
        database.close()


def product_worker_is_ready(
    database,
    *,
    release_id: str,
    release_commit: str,
    max_age_seconds: int,
) -> bool:
    """Require a fresh heartbeat from the exact active release."""

    if not 2 <= max_age_seconds <= 300:
        return False
    row = database.execute(
        """
        SELECT 1
        FROM runtime_worker_heartbeats
        WHERE worker_kind = ?
          AND release_id = ?
          AND release_commit = ?
          AND heartbeat_at >= unixepoch() - ?
          AND heartbeat_at <= unixepoch() + 5
        LIMIT 1
        """,
        (
            PRODUCT_WORKER_KIND,
            release_id,
            release_commit,
            max_age_seconds,
        ),
    ).fetchone()
    return row is not None


__all__ = [
    "PRODUCT_WORKER_KIND",
    "RuntimeReadinessError",
    "clear_product_worker_heartbeat",
    "product_worker_is_ready",
    "record_product_worker_heartbeat",
]
