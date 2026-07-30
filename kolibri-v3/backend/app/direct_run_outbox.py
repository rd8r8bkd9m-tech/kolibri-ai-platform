"""Durable, fenced queue for process-local direct model execution.

Logical Home owns its own command outbox.  Direct execution deliberately uses
this separate queue so a web-process restart cannot lose an accepted run or
silently replay an ambiguous provider effect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import threading
import uuid

from .database import connect_database, transaction


DIRECT_RUN_INTERRUPTED_CODE = "direct_run_interrupted"
DIRECT_RUN_INTERRUPTED_MESSAGE = (
    "Выполнение было остановлено перезапуском сервиса. Повторите запрос."
)
DIRECT_RUN_INTERNAL_ERROR_CODE = "direct_run_internal_error"
DIRECT_RUN_INTERNAL_ERROR_MESSAGE = (
    "Не удалось завершить выполнение. Повторите запрос."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


class DirectRunLeaseError(RuntimeError):
    """The direct executor no longer owns the exact durable run fence."""


@dataclass(frozen=True, slots=True)
class DirectRunClaim:
    tenant_id: str
    project_id: str
    thread_id: str
    public_thread_id: str
    run_id: str
    public_run_id: str
    execution_mode: str
    lease_token: str = field(repr=False)
    fencing_token: int
    execution_plane: str = "direct"
    replayed: bool = False


class DirectRunStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    @staticmethod
    def require_owned_in_transaction(
        database: sqlite3.Connection,
        claim: DirectRunClaim,
        *,
        now_text: str,
    ) -> sqlite3.Row:
        row = database.execute(
            """
            SELECT outbox.*
            FROM direct_run_outbox AS outbox
            JOIN chat_runs AS run
              ON run.tenant_id = outbox.tenant_id
             AND run.id = outbox.run_id
            JOIN chat_run_execution_contexts AS context
              ON context.tenant_id = run.tenant_id
             AND context.run_id = run.id
            WHERE outbox.tenant_id = ?
              AND outbox.run_id = ?
              AND outbox.state = 'leased'
              AND outbox.lease_token = ?
              AND outbox.fencing_token = ?
              AND outbox.lease_until >= ?
              AND run.status = 'running'
              AND context.execution_plane = 'direct'
            LIMIT 1
            """,
            (
                claim.tenant_id,
                claim.run_id,
                claim.lease_token,
                claim.fencing_token,
                now_text,
            ),
        ).fetchone()
        if row is None:
            raise DirectRunLeaseError("direct_run_lease_stale")
        if (
            str(row["public_thread_id"]) != claim.public_thread_id
            or str(row["public_run_id"]) != claim.public_run_id
        ):
            raise DirectRunLeaseError("direct_run_public_binding_changed")
        return row

    def fence(self, claim: DirectRunClaim) -> None:
        database = connect_database(self.database_url)
        try:
            with transaction(database, immediate=True):
                self.require_owned_in_transaction(
                    database,
                    claim,
                    now_text=_iso(),
                )
        finally:
            database.close()

    def claim_next(
        self,
        *,
        worker_id: str,
        lease_seconds: float,
    ) -> DirectRunClaim | None:
        now = _now()
        now_text = _iso(now)
        lease_until = _iso(now + timedelta(seconds=lease_seconds))
        database = connect_database(self.database_url)
        try:
            with transaction(database, immediate=True):
                row = database.execute(
                    """
                    SELECT outbox.*,
                           run.project_id,
                           run.thread_id,
                           context.execution_mode
                    FROM direct_run_outbox AS outbox
                    JOIN chat_runs AS run
                      ON run.tenant_id = outbox.tenant_id
                     AND run.id = outbox.run_id
                    JOIN chat_run_execution_contexts AS context
                      ON context.tenant_id = run.tenant_id
                     AND context.run_id = run.id
                    WHERE outbox.state = 'queued'
                      AND run.status = 'running'
                      AND context.execution_plane = 'direct'
                    ORDER BY outbox.created_at ASC,
                             outbox.tenant_id ASC,
                             outbox.run_id ASC
                    LIMIT 1
                    """
                ).fetchone()
                if row is None:
                    return None
                lease_token = f"direct_lease_{uuid.uuid4().hex}"
                fencing_token = int(row["fencing_token"]) + 1
                updated = database.execute(
                    """
                    UPDATE direct_run_outbox
                    SET state = 'leased',
                        lease_owner = ?,
                        lease_token = ?,
                        lease_until = ?,
                        fencing_token = ?,
                        updated_at = ?
                    WHERE tenant_id = ? AND run_id = ?
                      AND state = 'queued'
                      AND fencing_token = ?
                    """,
                    (
                        worker_id,
                        lease_token,
                        lease_until,
                        fencing_token,
                        now_text,
                        row["tenant_id"],
                        row["run_id"],
                        row["fencing_token"],
                    ),
                )
                if updated.rowcount != 1:
                    return None
                return DirectRunClaim(
                    tenant_id=str(row["tenant_id"]),
                    project_id=str(row["project_id"]),
                    thread_id=str(row["thread_id"]),
                    public_thread_id=str(row["public_thread_id"]),
                    run_id=str(row["run_id"]),
                    public_run_id=str(row["public_run_id"]),
                    execution_mode=str(row["execution_mode"]),
                    lease_token=lease_token,
                    fencing_token=fencing_token,
                )
        finally:
            database.close()

    def renew(
        self,
        claim: DirectRunClaim,
        *,
        lease_seconds: float,
    ) -> bool:
        now = _now()
        now_text = _iso(now)
        database = connect_database(self.database_url)
        try:
            with transaction(database, immediate=True):
                updated = database.execute(
                    """
                    UPDATE direct_run_outbox
                    SET lease_until = ?,
                        updated_at = ?
                    WHERE tenant_id = ? AND run_id = ?
                      AND state = 'leased'
                      AND lease_token = ?
                      AND fencing_token = ?
                      AND lease_until >= ?
                      AND EXISTS (
                          SELECT 1
                          FROM chat_runs AS run
                          WHERE run.tenant_id = direct_run_outbox.tenant_id
                            AND run.id = direct_run_outbox.run_id
                            AND run.status = 'running'
                      )
                    """,
                    (
                        _iso(now + timedelta(seconds=lease_seconds)),
                        now_text,
                        claim.tenant_id,
                        claim.run_id,
                        claim.lease_token,
                        claim.fencing_token,
                        now_text,
                    ),
                )
                return updated.rowcount == 1
        finally:
            database.close()

    def release_unstarted(self, claim: DirectRunClaim) -> None:
        """Return a claim to the queue only before executor submission."""

        database = connect_database(self.database_url)
        try:
            with transaction(database, immediate=True):
                database.execute(
                    """
                    UPDATE direct_run_outbox
                    SET state = 'queued',
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_until = NULL,
                        updated_at = ?
                    WHERE tenant_id = ? AND run_id = ?
                      AND state = 'leased'
                      AND lease_token = ?
                      AND fencing_token = ?
                    """,
                    (
                        _iso(),
                        claim.tenant_id,
                        claim.run_id,
                        claim.lease_token,
                        claim.fencing_token,
                    ),
                )
        finally:
            database.close()

    @staticmethod
    def complete_in_transaction(
        database: sqlite3.Connection,
        claim: DirectRunClaim,
        *,
        now_text: str,
    ) -> None:
        updated = database.execute(
            """
            UPDATE direct_run_outbox
            SET state = 'completed',
                lease_owner = NULL,
                lease_token = NULL,
                lease_until = NULL,
                last_error_code = NULL,
                completed_at = ?,
                updated_at = ?
            WHERE tenant_id = ? AND run_id = ?
              AND state = 'leased'
              AND lease_token = ?
              AND fencing_token = ?
              AND lease_until >= ?
            """,
            (
                now_text,
                now_text,
                claim.tenant_id,
                claim.run_id,
                claim.lease_token,
                claim.fencing_token,
                now_text,
            ),
        )
        if updated.rowcount != 1:
            raise DirectRunLeaseError("direct_run_completion_fenced")

    @staticmethod
    def block_in_transaction(
        database: sqlite3.Connection,
        claim: DirectRunClaim,
        *,
        code: str,
        now_text: str,
    ) -> None:
        updated = database.execute(
            """
            UPDATE direct_run_outbox
            SET state = 'blocked',
                lease_owner = NULL,
                lease_token = NULL,
                lease_until = NULL,
                last_error_code = ?,
                completed_at = ?,
                updated_at = ?
            WHERE tenant_id = ? AND run_id = ?
              AND state = 'leased'
              AND lease_token = ?
              AND fencing_token = ?
              AND lease_until >= ?
            """,
            (
                code[:128],
                now_text,
                now_text,
                claim.tenant_id,
                claim.run_id,
                claim.lease_token,
                claim.fencing_token,
                now_text,
            ),
        )
        if updated.rowcount != 1:
            raise DirectRunLeaseError("direct_run_failure_fenced")

    @staticmethod
    def _insert_run_error(
        database: sqlite3.Connection,
        *,
        tenant_id: str,
        run_id: str,
        code: str,
        message: str,
        now_text: str,
    ) -> bool:
        run = database.execute(
            """
            SELECT last_event_sequence
            FROM chat_runs
            WHERE tenant_id = ? AND id = ? AND status = 'running'
            LIMIT 1
            """,
            (tenant_id, run_id),
        ).fetchone()
        if run is None:
            return False
        sequence = int(run["last_event_sequence"]) + 1
        event = {
            "type": "RUN_ERROR",
            "code": code[:96],
            "message": message[:500],
        }
        database.execute(
            """
            INSERT INTO chat_run_events (
                tenant_id, event_id, run_id, sequence, event_type,
                event_json, created_at
            ) VALUES (?, ?, ?, ?, 'RUN_ERROR', ?, ?)
            """,
            (
                tenant_id,
                f"event_direct_recovery_{uuid.uuid4().hex}",
                run_id,
                sequence,
                json.dumps(
                    event,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ),
                now_text,
            ),
        )
        updated = database.execute(
            """
            UPDATE chat_runs
            SET status = 'failed',
                outcome = 'failure',
                last_event_sequence = ?,
                error_code = ?,
                heartbeat_at = ?,
                updated_at = ?,
                finished_at = ?
            WHERE tenant_id = ? AND id = ? AND status = 'running'
            """,
            (
                sequence,
                code[:96],
                now_text,
                now_text,
                now_text,
                tenant_id,
                run_id,
            ),
        )
        return updated.rowcount == 1

    def fail_claim(
        self,
        claim: DirectRunClaim,
        *,
        code: str = DIRECT_RUN_INTERNAL_ERROR_CODE,
        message: str = DIRECT_RUN_INTERNAL_ERROR_MESSAGE,
    ) -> bool:
        database = connect_database(self.database_url)
        now_text = _iso()
        try:
            with transaction(database, immediate=True):
                self.require_owned_in_transaction(
                    database,
                    claim,
                    now_text=now_text,
                )
                if not self._insert_run_error(
                    database,
                    tenant_id=claim.tenant_id,
                    run_id=claim.run_id,
                    code=code,
                    message=message,
                    now_text=now_text,
                ):
                    return False
                self.block_in_transaction(
                    database,
                    claim,
                    code=code,
                    now_text=now_text,
                )
                return True
        except DirectRunLeaseError:
            return False
        finally:
            database.close()

    def recover(self, *, limit: int = 100) -> int:
        """Fence terminal rows and fail expired ambiguous direct executions."""

        database = connect_database(self.database_url)
        now_text = _iso()
        recovered = 0
        try:
            with transaction(database, immediate=True):
                terminal_rows = database.execute(
                    """
                    SELECT outbox.tenant_id, outbox.run_id, run.status
                    FROM direct_run_outbox AS outbox
                    JOIN chat_runs AS run
                      ON run.tenant_id = outbox.tenant_id
                     AND run.id = outbox.run_id
                    WHERE outbox.state IN ('queued', 'leased')
                      AND run.status <> 'running'
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                for row in terminal_rows:
                    state = (
                        "completed"
                        if str(row["status"]) == "succeeded"
                        else "blocked"
                    )
                    database.execute(
                        """
                        UPDATE direct_run_outbox
                        SET state = ?,
                            lease_owner = NULL,
                            lease_token = NULL,
                            lease_until = NULL,
                            fencing_token = fencing_token + 1,
                            last_error_code = CASE
                                WHEN ? = 'blocked'
                                THEN 'direct_run_already_terminal'
                                ELSE NULL
                            END,
                            completed_at = ?,
                            updated_at = ?
                        WHERE tenant_id = ? AND run_id = ?
                          AND state IN ('queued', 'leased')
                        """,
                        (
                            state,
                            state,
                            now_text,
                            now_text,
                            row["tenant_id"],
                            row["run_id"],
                        ),
                    )
                    recovered += 1

                remaining = max(0, limit - recovered)
                expired = database.execute(
                    """
                    SELECT tenant_id, run_id, lease_token, fencing_token
                    FROM direct_run_outbox
                    WHERE state = 'leased' AND lease_until < ?
                    ORDER BY lease_until ASC, tenant_id ASC, run_id ASC
                    LIMIT ?
                    """,
                    (now_text, remaining),
                ).fetchall()
                for row in expired:
                    terminalized = self._insert_run_error(
                        database,
                        tenant_id=str(row["tenant_id"]),
                        run_id=str(row["run_id"]),
                        code=DIRECT_RUN_INTERRUPTED_CODE,
                        message=DIRECT_RUN_INTERRUPTED_MESSAGE,
                        now_text=now_text,
                    )
                    updated = database.execute(
                        """
                        UPDATE direct_run_outbox
                        SET state = 'blocked',
                            lease_owner = NULL,
                            lease_token = NULL,
                            lease_until = NULL,
                            fencing_token = fencing_token + 1,
                            last_error_code = ?,
                            completed_at = ?,
                            updated_at = ?
                        WHERE tenant_id = ? AND run_id = ?
                          AND state = 'leased'
                          AND lease_token = ?
                          AND fencing_token = ?
                          AND lease_until < ?
                        """,
                        (
                            DIRECT_RUN_INTERRUPTED_CODE,
                            now_text,
                            now_text,
                            row["tenant_id"],
                            row["run_id"],
                            row["lease_token"],
                            row["fencing_token"],
                            now_text,
                        ),
                    )
                    if updated.rowcount == 1:
                        recovered += 1
                    elif terminalized:
                        raise RuntimeError(
                            "direct run recovery lost its durable fence"
                        )
            return recovered
        finally:
            database.close()


class DirectRunLeaseHeartbeat:
    """Keep a healthy direct lease alive and pre-empt on lost ownership."""

    def __init__(
        self,
        store: DirectRunStore,
        claim: DirectRunClaim,
        *,
        lease_seconds: float,
        cancellation_signal: threading.Event,
    ) -> None:
        self.store = store
        self.claim = claim
        self.lease_seconds = lease_seconds
        self.cancellation_signal = cancellation_signal
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"direct-lease-{claim.run_id[-16:]}",
            daemon=True,
        )

    def __enter__(self) -> "DirectRunLeaseHeartbeat":
        self.store.fence(self.claim)
        self._thread.start()
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)

    def _run(self) -> None:
        interval = max(0.25, self.lease_seconds / 3)
        while not self._stop.wait(interval):
            if not self.store.renew(
                self.claim,
                lease_seconds=self.lease_seconds,
            ):
                self.cancellation_signal.set()
                return
