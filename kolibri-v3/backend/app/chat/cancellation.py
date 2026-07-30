"""Durable, user-scoped cancellation for Product Chat runs.

Stopping the browser stream is not a cancellation boundary: Home workers and
direct runtimes can continue after the HTTP client disconnects.  This module
first terminalizes the canonical Product/Data run and fences its outbox claim,
then exposes a process-local signal for runtimes that support pre-emption.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import threading

from ..database import transaction
from ..trusted_agent_leases import (
    TrustedAgentLeaseError,
    TrustedAgentLeaseScope,
    revoke_trusted_agent_lease,
)


RUN_CANCELLED_CODE = "run_cancelled"
RUN_CANCELLED_MESSAGE = "Задача остановлена пользователем."


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class CancelRunResult:
    run_id: str
    cancelled: bool


class ActiveRunCancellationRegistry:
    """Process-local cancellation signals keyed by canonical run identity."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._signals: dict[tuple[str, str], threading.Event] = {}

    def register(self, tenant_id: str, run_id: str) -> threading.Event:
        key = (tenant_id, run_id)
        signal = threading.Event()
        with self._lock:
            previous = self._signals.get(key)
            if previous is not None:
                previous.set()
            self._signals[key] = signal
        return signal

    def unregister(
        self,
        tenant_id: str,
        run_id: str,
        signal: threading.Event,
    ) -> None:
        key = (tenant_id, run_id)
        with self._lock:
            if self._signals.get(key) is signal:
                self._signals.pop(key, None)

    def cancel(self, tenant_id: str, run_id: str) -> bool:
        with self._lock:
            signal = self._signals.get((tenant_id, run_id))
        if signal is None:
            return False
        signal.set()
        return True

    def is_registered(self, tenant_id: str, run_id: str) -> bool:
        with self._lock:
            return (tenant_id, run_id) in self._signals

    def close(self) -> None:
        with self._lock:
            signals = tuple(self._signals.values())
            self._signals.clear()
        for signal in signals:
            signal.set()


def cancel_run(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str,
    run_id: str,
) -> CancelRunResult | None:
    """Terminalize one owned run and fence any outstanding Home worker claim.

    ``None`` deliberately covers both an unknown run and a run owned by
    another user.  Repeating cancellation for an already-terminal owned run is
    idempotent and returns ``cancelled=False``.
    """

    now = _utc_now()
    with transaction(database, immediate=True):
        run = database.execute(
            """
            SELECT run.status,
                   run.last_event_sequence,
                   run.requested_by_user_id,
                   context.execution_mode,
                   context.platform_authority_epoch,
                   context.trusted_agent_profile_id,
                   context.trusted_agent_profile_epoch,
                   context.trusted_agent_workspace_binding_id,
                   context.trusted_agent_workspace_binding_epoch
            FROM chat_runs AS run
            LEFT JOIN chat_run_execution_contexts AS context
              ON context.tenant_id = run.tenant_id
             AND context.run_id = run.id
            WHERE run.tenant_id = ? AND run.id = ?
              AND run.requested_by_user_id = ?
            LIMIT 1
            """,
            (tenant_id, run_id, user_id),
        ).fetchone()
        if run is None:
            return None
        if str(run["status"]) != "running":
            return CancelRunResult(run_id=run_id, cancelled=False)

        sequence = int(run["last_event_sequence"]) + 1
        event = {
            "type": "RUN_ERROR",
            "code": RUN_CANCELLED_CODE,
            "message": RUN_CANCELLED_MESSAGE,
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
                f"event_cancel_{run_id.removeprefix('run_')[:80]}_{sequence}",
                run_id,
                sequence,
                json.dumps(
                    event,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ),
                now,
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
                RUN_CANCELLED_CODE,
                now,
                now,
                now,
                tenant_id,
                run_id,
            ),
        )
        if updated.rowcount != 1:
            return CancelRunResult(run_id=run_id, cancelled=False)

        # A stale leased worker must not be able to commit after cancellation.
        # Advancing its fencing token and clearing ownership makes every
        # already-issued claim fail the worker's exact-token predicate.
        database.execute(
            """
            UPDATE product_run_outbox
            SET state = 'blocked',
                completed_at = ?,
                lease_owner = NULL,
                lease_token = NULL,
                lease_until = NULL,
                fencing_token = fencing_token + 1,
                last_error_code = ?,
                updated_at = ?
            WHERE tenant_id = ? AND run_id = ?
              AND state NOT IN ('blocked', 'completed')
            """,
            (
                now,
                RUN_CANCELLED_CODE,
                now,
                tenant_id,
                run_id,
            ),
        )
        database.execute(
            """
            UPDATE direct_run_outbox
            SET state = 'blocked',
                completed_at = ?,
                lease_owner = NULL,
                lease_token = NULL,
                lease_until = NULL,
                fencing_token = fencing_token + 1,
                last_error_code = ?,
                updated_at = ?
            WHERE tenant_id = ? AND run_id = ?
              AND state NOT IN ('blocked', 'completed')
            """,
            (
                now,
                RUN_CANCELLED_CODE,
                now,
                tenant_id,
                run_id,
            ),
        )
        frozen = (
            run["trusted_agent_profile_id"],
            run["trusted_agent_profile_epoch"],
            run["trusted_agent_workspace_binding_id"],
            run["trusted_agent_workspace_binding_epoch"],
        )
        if (
            str(run["execution_mode"] or "") == "developer"
            and all(value is not None for value in frozen)
        ):
            authority_epoch = run["platform_authority_epoch"]
            if authority_epoch is None:
                raise RuntimeError(
                    "trusted developer cancellation authority is missing"
                )
            scope = TrustedAgentLeaseScope(
                owner_user_id=str(run["requested_by_user_id"]),
                owner_tenant_id=tenant_id,
                authority_epoch=int(authority_epoch),
                profile_id=str(run["trusted_agent_profile_id"]),
                profile_epoch=int(run["trusted_agent_profile_epoch"]),
                workspace_binding_id=str(
                    run["trusted_agent_workspace_binding_id"]
                ),
                workspace_binding_epoch=int(
                    run["trusted_agent_workspace_binding_epoch"]
                ),
                assignment_ref=run_id,
            )
            lease = database.execute(
                """
                SELECT id
                FROM trusted_agent_workspace_leases
                WHERE owner_tenant_id = ?
                  AND assignment_ref = ?
                  AND state = 'active'
                LIMIT 1
                """,
                (tenant_id, run_id),
            ).fetchone()
            if lease is not None:
                digest = hashlib.sha256(
                    f"{tenant_id}\0{run_id}\0run_cancelled".encode(
                        "utf-8",
                        "strict",
                    )
                ).hexdigest()
                try:
                    revoke_trusted_agent_lease(
                        database,
                        lease_id=str(lease["id"]),
                        scope=scope,
                        reason=RUN_CANCELLED_CODE,
                        idempotency_key=f"product.lease-cancel:{digest}",
                    )
                except TrustedAgentLeaseError as exc:
                    raise RuntimeError(exc.code) from exc
        return CancelRunResult(run_id=run_id, cancelled=True)
