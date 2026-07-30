"""Standalone durable V3 Product Chat dispatcher.

This process is the only V3 component that has Logical Home transport
credentials.  It leases an immutable outbox command, initializes the
authoritative Goal/ProjectCase at Home, then repeatedly submits the same
byte-for-byte run command until Home reports a terminal result.
"""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import math
import os
import secrets
import signal
import socket
import sqlite3
import threading
import uuid
from typing import Any, Literal, Mapping

from .chat.service import (
    canonical_command_hash,
    canonical_json,
    new_id,
    sha256_text,
    typed_identity_id,
)
from .config import Settings
from .database import connect_database, initialize_database, transaction
from .home_runtime import (
    HomeProductGoalClient,
    HomeProductRunClient,
    HomeRuntimeResponse,
    ProductRunExecutionError,
    ProductRunExecutionSettings,
)
from .platform_admin import (
    PlatformPolicyError,
    enforce_background_execution_policy,
)
from .platform_authority import (
    PlatformDeveloperAuthorityError,
    require_persisted_platform_developer_authority,
)
from .runtime_readiness import (
    clear_product_worker_heartbeat,
    record_product_worker_heartbeat,
)
from .trusted_agent_execution import (
    TrustedAgentExecutionError,
    validate_frozen_trusted_agent_execution_binding,
)
from .trusted_agent_leases import (
    TrustedAgentLeaseError,
    TrustedAgentLeaseScope,
    claim_or_renew_trusted_agent_lease,
    fence_trusted_agent_lease,
    issue_trusted_agent_lease,
    revoke_trusted_agent_lease,
    terminalize_trusted_agent_lease,
)


LOGGER = logging.getLogger("kolibri.v3.product_run_worker")
_RUN_PATH = "/v1/runtime/product-text-runs"
_GOAL_PATH = "/v1/runtime/product-goal-initializations"
_TERMINAL_EVENT_TYPES = frozenset({"RUN_FINISHED", "RUN_ERROR"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).astimezone(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class OutboxClaim:
    tenant_id: str
    outbox_id: str
    run_id: str
    command_kind: str
    phase: str
    command_json: str
    command_hash: str
    attempts: int
    max_attempts: int
    lease_token: str
    fencing_token: int


@dataclass(frozen=True, slots=True)
class TrustedAgentWorkerClaim:
    """Worker-held Galileo capability; the raw token must never be persisted."""

    lease_id: str
    scope: TrustedAgentLeaseScope
    claim_owner: str
    claim_token: str = field(repr=False)
    fencing_token: int
    expires_at: int


class StaleLeaseError(RuntimeError):
    pass


class TrustedAgentLeaseDeferred(RuntimeError):
    """The singleton trusted agent is busy and the outbox must be deferred."""

    def __init__(self, code: str, *, retry_at: int) -> None:
        super().__init__(code)
        self.code = code
        self.retry_at = retry_at


def _decode_command(command_json: str) -> dict[str, Any]:
    try:
        value = json.loads(command_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ProductRunExecutionError(
            "stored_command_invalid",
            retryable=False,
        ) from exc
    if not isinstance(value, dict):
        raise ProductRunExecutionError(
            "stored_command_invalid",
            retryable=False,
        )
    if sha256_text(command_json) == "":
        raise AssertionError("unreachable")
    return value


def _response_body(response: HomeRuntimeResponse) -> str:
    # home_runtime already decoded strict UTF-8 and validated the exact body.
    return response.body_text


def _is_developer_effect(command_json: str) -> bool:
    """Classify the immutable command without interpreting runtime identity."""

    try:
        command = json.loads(command_json)
    except (TypeError, json.JSONDecodeError):
        return False
    if not isinstance(command, dict):
        return False
    payload = command.get("payload")
    return (
        (
            command.get("payload_schema_id"),
            command.get("payload_schema_version"),
        )
        in {
            ("kolibri.product.run.execute.v1_2.command", "1.2"),
            ("kolibri.product.run.execute.v1_3.command", "1.3"),
        }
        and isinstance(payload, dict)
        and payload.get("execution_mode") == "developer"
    )


def _runtime_profile_from_status(status: Mapping[str, Any]) -> str:
    """Read the versioned field without rewriting the stored Home response."""

    field_name = (
        "runtime_profile"
        if status.get("schema_id")
        == "kolibri.product.run.execution_status.v1_1"
        and status.get("schema_version") == "1.1"
        else "profile"
    )
    value = status.get(field_name)
    if not isinstance(value, str) or not value:
        raise ProductRunExecutionError(
            "home_runtime_profile_missing",
            retryable=False,
        )
    return value


def _claim_user_id(claim: OutboxClaim) -> str | None:
    command = _decode_command(claim.command_json)
    identity = command.get("identity")
    if not isinstance(identity, Mapping):
        raise ProductRunExecutionError(
            "stored_command_identity_invalid",
            retryable=False,
        )
    user_id = identity.get("user_id")
    if user_id is None:
        return None
    if not isinstance(user_id, str) or not user_id:
        raise ProductRunExecutionError(
            "stored_command_identity_invalid",
            retryable=False,
        )
    return user_id


def _enforce_claim_policy(
    database: sqlite3.Connection,
    claim: OutboxClaim,
) -> None:
    run = database.execute(
        """
        SELECT run.requested_by_user_id,
               run.selected_profile,
               context.execution_mode,
               context.platform_authority_epoch,
               context.access_mode,
               context.sandbox_profile,
               context.approval_policy,
               context.approvals_reviewer,
               context.trusted_agent_profile_id,
               context.trusted_agent_profile_epoch,
               context.trusted_agent_workspace_binding_id,
               context.trusted_agent_workspace_binding_epoch
        FROM chat_runs AS run
        LEFT JOIN chat_run_execution_contexts AS context
          ON context.tenant_id = run.tenant_id
         AND context.run_id = run.id
        WHERE run.tenant_id = ? AND run.id = ?
        LIMIT 1
        """,
        (claim.tenant_id, claim.run_id),
    ).fetchone()
    if run is None:
        raise ProductRunExecutionError(
            "chat_run_missing",
            retryable=False,
        )
    local_user_id = str(run["requested_by_user_id"])
    if typed_identity_id("user", local_user_id) != _claim_user_id(claim):
        raise ProductRunExecutionError(
            "stored_command_identity_invalid",
            retryable=False,
        )
    developer_execution = (
        str(run["execution_mode"] or "standard") == "developer"
    )
    if developer_execution:
        frozen_epoch = run["platform_authority_epoch"]
        if frozen_epoch is None:
            raise ProductRunExecutionError(
                "owner_required",
                retryable=False,
            )
        try:
            require_persisted_platform_developer_authority(
                database,
                user_id=local_user_id,
                tenant_id=claim.tenant_id,
                expected_epoch=int(frozen_epoch),
            )
        except PlatformDeveloperAuthorityError as exc:
            raise ProductRunExecutionError(
                exc.code,
                retryable=False,
            ) from exc
        try:
            validate_frozen_trusted_agent_execution_binding(
                database,
                tenant_id=claim.tenant_id,
                user_id=local_user_id,
                authority_epoch=int(frozen_epoch),
                runtime_profile=str(run["selected_profile"]),
                access_mode=str(run["access_mode"]),
                sandbox_profile=str(run["sandbox_profile"]),
                approval_policy=str(run["approval_policy"]),
                approvals_reviewer=(
                    None
                    if run["approvals_reviewer"] is None
                    else str(run["approvals_reviewer"])
                ),
                profile_id=run["trusted_agent_profile_id"],
                profile_epoch=run["trusted_agent_profile_epoch"],
                workspace_binding_id=(
                    run["trusted_agent_workspace_binding_id"]
                ),
                workspace_binding_epoch=(
                    run["trusted_agent_workspace_binding_epoch"]
                ),
            )
        except TrustedAgentExecutionError as exc:
            raise ProductRunExecutionError(
                exc.code,
                retryable=False,
            ) from exc
    try:
        enforce_background_execution_policy(
            database,
            tenant_id=claim.tenant_id,
            user_id=local_user_id,
            require_developer_access=developer_execution,
        )
    except PlatformPolicyError as exc:
        raise ProductRunExecutionError(
            exc.code,
            retryable=False,
        ) from exc


class ProductRunStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    @staticmethod
    def _trusted_agent_scope_for_claim(
        database: sqlite3.Connection,
        claim: OutboxClaim,
    ) -> TrustedAgentLeaseScope | None:
        """Derive Galileo scope only from persisted run authority and identity."""

        command = _decode_command(claim.command_json)
        payload = command.get("payload")
        if not isinstance(payload, Mapping):
            raise ProductRunExecutionError(
                "stored_command_invalid",
                retryable=False,
            )
        if payload.get("execution_mode") != "developer":
            return None

        row = database.execute(
            """
            SELECT run.requested_by_user_id,
                   run.selected_profile,
                   context.execution_mode,
                   context.platform_authority_epoch,
                   context.access_mode,
                   context.sandbox_profile,
                   context.approval_policy,
                   context.approvals_reviewer,
                   context.trusted_agent_profile_id,
                   context.trusted_agent_profile_epoch,
                   context.trusted_agent_workspace_binding_id,
                   context.trusted_agent_workspace_binding_epoch
            FROM chat_runs AS run
            LEFT JOIN chat_run_execution_contexts AS context
              ON context.tenant_id = run.tenant_id
             AND context.run_id = run.id
            WHERE run.tenant_id = ? AND run.id = ?
            LIMIT 1
            """,
            (claim.tenant_id, claim.run_id),
        ).fetchone()
        if row is None:
            raise ProductRunExecutionError(
                "chat_run_missing",
                retryable=False,
            )
        if str(row["execution_mode"] or "") != "developer":
            raise ProductRunExecutionError(
                "developer_execution_context_invalid",
                retryable=False,
            )

        schema = (
            command.get("payload_schema_id"),
            command.get("payload_schema_version"),
        )
        fields = (
            "trusted_agent_profile_id",
            "trusted_agent_profile_epoch",
            "trusted_agent_workspace_binding_id",
            "trusted_agent_workspace_binding_epoch",
        )
        persisted = tuple(row[field_name] for field_name in fields)
        bound = all(value is not None for value in persisted)
        partial = any(value is not None for value in persisted) and not bound
        if partial:
            raise ProductRunExecutionError(
                "trusted_agent_execution_binding_invalid",
                retryable=False,
            )
        if schema == (
            "kolibri.product.run.execute.v1_2.command",
            "1.2",
        ):
            if bound:
                raise ProductRunExecutionError(
                    "trusted_agent_command_downgrade",
                    retryable=False,
                )
            # Only historical, fully unbound v1.2 commands may drain.
            return None
        if schema != (
            "kolibri.product.run.execute.v1_3.command",
            "1.3",
        ):
            raise ProductRunExecutionError(
                "trusted_agent_command_version_invalid",
                retryable=False,
            )
        if not bound:
            raise ProductRunExecutionError(
                "trusted_agent_execution_binding_invalid",
                retryable=False,
            )

        expected_payload = {
            "tenant_id": typed_identity_id("tenant", claim.tenant_id),
            "run_id": claim.run_id,
            "runtime_profile": str(row["selected_profile"]),
            "access_mode": str(row["access_mode"]),
            "sandbox": str(row["sandbox_profile"]),
            "approval_policy": str(row["approval_policy"]),
            "reviewer": (
                None
                if row["approvals_reviewer"] is None
                else str(row["approvals_reviewer"])
            ),
            **{
                field_name: row[field_name]
                for field_name in fields
            },
        }
        if any(
            payload.get(field_name) != expected
            for field_name, expected in expected_payload.items()
        ):
            raise ProductRunExecutionError(
                "trusted_agent_command_binding_mismatch",
                retryable=False,
            )
        authority_epoch = row["platform_authority_epoch"]
        if authority_epoch is None:
            raise ProductRunExecutionError(
                "owner_required",
                retryable=False,
            )
        return TrustedAgentLeaseScope(
            owner_user_id=str(row["requested_by_user_id"]),
            owner_tenant_id=claim.tenant_id,
            authority_epoch=int(authority_epoch),
            profile_id=str(row["trusted_agent_profile_id"]),
            profile_epoch=int(row["trusted_agent_profile_epoch"]),
            workspace_binding_id=str(
                row["trusted_agent_workspace_binding_id"]
            ),
            workspace_binding_epoch=int(
                row["trusted_agent_workspace_binding_epoch"]
            ),
            assignment_ref=claim.run_id,
        )

    @staticmethod
    def _trusted_operation_key(
        operation: str,
        *parts: object,
    ) -> str:
        digest = hashlib.sha256(
            canonical_json(
                {
                    "operation": operation,
                    "parts": [str(part) for part in parts],
                }
            ).encode("utf-8", "strict")
        ).hexdigest()
        return f"product.{operation}:{digest}"

    @staticmethod
    def _trusted_claim_owner(worker_id: str) -> str:
        digest = hashlib.sha256(
            worker_id.encode("utf-8", "strict")
        ).hexdigest()
        return f"product-worker-{digest[:32]}"

    @staticmethod
    def _trusted_error(exc: TrustedAgentLeaseError) -> ProductRunExecutionError:
        return ProductRunExecutionError(
            exc.code,
            retryable=exc.retryable,
        )

    def acquire_trusted_agent_lease(
        self,
        claim: OutboxClaim,
        *,
        worker_id: str,
        ttl_seconds: int,
        previous: TrustedAgentWorkerClaim | None = None,
    ) -> TrustedAgentWorkerClaim | None:
        """Issue and claim the singleton trusted agent for one v1.3 run."""

        database = connect_database(self.database_url)
        now_text = _iso()
        now_epoch = int(_now().timestamp())
        try:
            with transaction(database, immediate=True):
                self._owned_outbox(database, claim, now_text=now_text)
                _enforce_claim_policy(database, claim)
                scope = self._trusted_agent_scope_for_claim(database, claim)
                if scope is None:
                    if previous is not None:
                        raise ProductRunExecutionError(
                            "trusted_agent_command_downgrade",
                            retryable=False,
                        )
                    return None
                if previous is not None and previous.scope != scope:
                    raise ProductRunExecutionError(
                        "trusted_agent_lease_scope_mismatch",
                        retryable=False,
                    )

                existing = database.execute(
                    """
                    SELECT id, state, expires_at
                    FROM trusted_agent_workspace_leases
                    WHERE owner_tenant_id = ? AND assignment_ref = ?
                    LIMIT 1
                    """,
                    (scope.owner_tenant_id, scope.assignment_ref),
                ).fetchone()
                if existing is None:
                    try:
                        issued = issue_trusted_agent_lease(
                            database,
                            scope=scope,
                            idempotency_key=self._trusted_operation_key(
                                "lease-issue",
                                scope.owner_tenant_id,
                                scope.assignment_ref,
                            ),
                            ttl_seconds=ttl_seconds,
                            now=now_epoch,
                        )
                    except TrustedAgentLeaseError as exc:
                        if exc.code == (
                            "trusted_agent_lease_assignment_conflict"
                        ):
                            existing = database.execute(
                                """
                                SELECT id, state, expires_at
                                FROM trusted_agent_workspace_leases
                                WHERE owner_tenant_id = ?
                                  AND assignment_ref = ?
                                LIMIT 1
                                """,
                                (
                                    scope.owner_tenant_id,
                                    scope.assignment_ref,
                                ),
                            ).fetchone()
                            if existing is None:
                                raise self._trusted_error(exc) from exc
                        elif exc.retryable:
                            competing = database.execute(
                                """
                                SELECT expires_at
                                FROM trusted_agent_workspace_leases
                                WHERE authority_id = 'platform_owner'
                                  AND state = 'active'
                                ORDER BY expires_at, id
                                LIMIT 1
                                """
                            ).fetchone()
                            retry_at = (
                                int(competing["expires_at"]) + 1
                                if competing is not None
                                else now_epoch + 1
                            )
                            raise TrustedAgentLeaseDeferred(
                                exc.code,
                                retry_at=retry_at,
                            ) from exc
                        else:
                            raise self._trusted_error(exc) from exc
                    else:
                        existing = {
                            "id": issued.id,
                            "state": issued.state,
                            "expires_at": issued.expires_at,
                        }

                assert existing is not None
                if str(existing["state"]) != "active":
                    raise ProductRunExecutionError(
                        "trusted_agent_lease_terminal",
                        retryable=False,
                    )
                claim_owner = self._trusted_claim_owner(worker_id)
                claim_token = (
                    previous.claim_token
                    if previous is not None
                    else f"talcap_{secrets.token_urlsafe(32)}"
                )
                lease_id = str(existing["id"])
                try:
                    leased = claim_or_renew_trusted_agent_lease(
                        database,
                        lease_id=lease_id,
                        scope=scope,
                        claim_owner=claim_owner,
                        claim_token=claim_token,
                        idempotency_key=self._trusted_operation_key(
                            "lease-claim",
                            scope.owner_tenant_id,
                            scope.assignment_ref,
                            claim.fencing_token,
                        ),
                        ttl_seconds=ttl_seconds,
                        now=now_epoch,
                    )
                except TrustedAgentLeaseError as exc:
                    if exc.retryable:
                        raise TrustedAgentLeaseDeferred(
                            exc.code,
                            retry_at=max(
                                now_epoch + 1,
                                int(existing["expires_at"]) + 1,
                            ),
                        ) from exc
                    raise self._trusted_error(exc) from exc
                return TrustedAgentWorkerClaim(
                    lease_id=leased.id,
                    scope=scope,
                    claim_owner=claim_owner,
                    claim_token=claim_token,
                    fencing_token=leased.fencing_token,
                    expires_at=leased.expires_at,
                )
        finally:
            database.close()

    @staticmethod
    def _fence_trusted_agent_in_transaction(
        database: sqlite3.Connection,
        claim: OutboxClaim,
        trusted_claim: TrustedAgentWorkerClaim | None,
    ) -> None:
        scope = ProductRunStore._trusted_agent_scope_for_claim(
            database,
            claim,
        )
        if scope is None:
            if trusted_claim is not None:
                raise ProductRunExecutionError(
                    "trusted_agent_command_downgrade",
                    retryable=False,
                )
            return
        if trusted_claim is None or trusted_claim.scope != scope:
            raise ProductRunExecutionError(
                "trusted_agent_lease_required",
                retryable=False,
            )
        try:
            fence_trusted_agent_lease(
                database,
                lease_id=trusted_claim.lease_id,
                scope=scope,
                claim_owner=trusted_claim.claim_owner,
                claim_token=trusted_claim.claim_token,
                fencing_token=trusted_claim.fencing_token,
            )
        except TrustedAgentLeaseError as exc:
            raise ProductRunStore._trusted_error(exc) from exc

    def fence_external_effect(
        self,
        claim: OutboxClaim,
        trusted_claim: TrustedAgentWorkerClaim | None,
    ) -> None:
        """Fence the exact outbox and Galileo capability immediately pre-I/O."""

        database = connect_database(self.database_url)
        now_text = _iso()
        try:
            with transaction(database, immediate=True):
                self._owned_outbox(database, claim, now_text=now_text)
                _enforce_claim_policy(database, claim)
                self._fence_trusted_agent_in_transaction(
                    database,
                    claim,
                    trusted_claim,
                )
        finally:
            database.close()

    @staticmethod
    def _terminalize_trusted_agent_in_transaction(
        database: sqlite3.Connection,
        trusted_claim: TrustedAgentWorkerClaim | None,
        *,
        terminal_state: Literal["released", "expired"],
        reason: str,
    ) -> None:
        if trusted_claim is None:
            return
        try:
            terminalize_trusted_agent_lease(
                database,
                lease_id=trusted_claim.lease_id,
                scope=trusted_claim.scope,
                claim_owner=trusted_claim.claim_owner,
                claim_token=trusted_claim.claim_token,
                fencing_token=trusted_claim.fencing_token,
                terminal_state=terminal_state,
                reason=reason,
                idempotency_key=ProductRunStore._trusted_operation_key(
                    "lease-terminal",
                    trusted_claim.scope.owner_tenant_id,
                    trusted_claim.scope.assignment_ref,
                    trusted_claim.fencing_token,
                    terminal_state,
                    reason,
                ),
            )
        except TrustedAgentLeaseError as exc:
            raise ProductRunStore._trusted_error(exc) from exc

    @staticmethod
    def _revoke_trusted_agent_in_transaction(
        database: sqlite3.Connection,
        trusted_claim: TrustedAgentWorkerClaim | None,
        *,
        reason: str,
    ) -> None:
        if trusted_claim is None:
            return
        persisted = database.execute(
            """
            SELECT state
            FROM trusted_agent_workspace_leases
            WHERE id = ?
              AND owner_tenant_id = ?
              AND assignment_ref = ?
            LIMIT 1
            """,
            (
                trusted_claim.lease_id,
                trusted_claim.scope.owner_tenant_id,
                trusted_claim.scope.assignment_ref,
            ),
        ).fetchone()
        if persisted is not None and str(persisted["state"]) == "revoked":
            # Administrative/profile revocation already established the fence.
            return
        try:
            revoke_trusted_agent_lease(
                database,
                lease_id=trusted_claim.lease_id,
                scope=trusted_claim.scope,
                reason=reason,
                idempotency_key=ProductRunStore._trusted_operation_key(
                    "lease-revoke",
                    trusted_claim.scope.owner_tenant_id,
                    trusted_claim.scope.assignment_ref,
                    reason,
                ),
            )
        except TrustedAgentLeaseError as exc:
            raise ProductRunStore._trusted_error(exc) from exc

    @staticmethod
    def _revoke_scope_lease_in_transaction(
        database: sqlite3.Connection,
        scope: TrustedAgentLeaseScope,
        *,
        reason: str,
    ) -> None:
        row = database.execute(
            """
            SELECT id, state
            FROM trusted_agent_workspace_leases
            WHERE owner_tenant_id = ? AND assignment_ref = ?
            LIMIT 1
            """,
            (scope.owner_tenant_id, scope.assignment_ref),
        ).fetchone()
        if row is None or str(row["state"]) != "active":
            return
        try:
            revoke_trusted_agent_lease(
                database,
                lease_id=str(row["id"]),
                scope=scope,
                reason=reason,
                idempotency_key=ProductRunStore._trusted_operation_key(
                    "lease-revoke",
                    scope.owner_tenant_id,
                    scope.assignment_ref,
                    reason,
                ),
            )
        except TrustedAgentLeaseError as exc:
            raise ProductRunStore._trusted_error(exc) from exc

    def defer_trusted_agent_lease(
        self,
        claim: OutboxClaim,
        deferred: TrustedAgentLeaseDeferred,
    ) -> None:
        """Release only the outbox claim; do not consume a delivery attempt."""

        database = connect_database(self.database_url)
        now = _now()
        now_text = _iso(now)
        retry_at = datetime.fromtimestamp(
            max(deferred.retry_at, int(now.timestamp()) + 1),
            tz=timezone.utc,
        )
        try:
            with transaction(database, immediate=True):
                self._owned_outbox(database, claim, now_text=now_text)
                _enforce_claim_policy(database, claim)
                updated = database.execute(
                    """
                    UPDATE product_run_outbox
                    SET state = 'polling',
                        available_at = ?,
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_until = NULL,
                        last_error_code = ?,
                        updated_at = ?
                    WHERE tenant_id = ? AND id = ?
                      AND lease_token = ? AND fencing_token = ?
                    """,
                    (
                        _iso(retry_at),
                        deferred.code[:128],
                        now_text,
                        claim.tenant_id,
                        claim.outbox_id,
                        claim.lease_token,
                        claim.fencing_token,
                    ),
                )
                if updated.rowcount != 1:
                    raise StaleLeaseError()
        finally:
            database.close()

    def claim_next(
        self,
        *,
        worker_id: str,
        lease_seconds: float,
    ) -> OutboxClaim | None:
        database = connect_database(self.database_url)
        now = _now()
        now_text = _iso(now)
        lease_until = _iso(now + timedelta(seconds=lease_seconds))
        try:
            with transaction(database, immediate=True):
                row = database.execute(
                    """
                    SELECT *
                    FROM product_run_outbox
                    WHERE (
                        state IN ('queued', 'polling', 'retry')
                        AND available_at <= ?
                        AND (lease_until IS NULL OR lease_until < ?)
                    ) OR (
                        state = 'leased'
                        AND lease_until < ?
                    )
                    ORDER BY available_at ASC, created_at ASC, tenant_id ASC, id ASC
                    LIMIT 1
                    """,
                    (now_text, now_text, now_text),
                ).fetchone()
                if row is None:
                    return None
                token = f"lease_{uuid.uuid4().hex}"
                fencing_token = int(row["fencing_token"]) + 1
                updated = database.execute(
                    """
                    UPDATE product_run_outbox
                    SET state = 'leased',
                        lease_owner = ?,
                        lease_token = ?,
                        lease_until = ?,
                        fencing_token = ?,
                        updated_at = ?
                    WHERE tenant_id = ? AND id = ?
                      AND fencing_token = ?
                      AND (
                        (
                            state IN ('queued', 'polling', 'retry')
                            AND available_at <= ?
                            AND (lease_until IS NULL OR lease_until < ?)
                        )
                        OR (state = 'leased' AND lease_until < ?)
                      )
                    """,
                    (
                        worker_id,
                        token,
                        lease_until,
                        fencing_token,
                        now_text,
                        row["tenant_id"],
                        row["id"],
                        row["fencing_token"],
                        now_text,
                        now_text,
                        now_text,
                    ),
                )
                if updated.rowcount != 1:
                    return None
                return OutboxClaim(
                    tenant_id=str(row["tenant_id"]),
                    outbox_id=str(row["id"]),
                    run_id=str(row["run_id"]),
                    command_kind=str(row["command_kind"]),
                    phase=str(row["phase"]),
                    command_json=str(row["command_json"]),
                    command_hash=str(row["command_hash"]),
                    attempts=int(row["attempts"]),
                    max_attempts=int(row["max_attempts"]),
                    lease_token=token,
                    fencing_token=fencing_token,
                )
        finally:
            database.close()

    @staticmethod
    def _owned_outbox(
        database: sqlite3.Connection,
        claim: OutboxClaim,
        *,
        now_text: str,
    ) -> sqlite3.Row:
        row = database.execute(
            """
            SELECT *
            FROM product_run_outbox
            WHERE tenant_id = ? AND id = ?
              AND run_id = ?
              AND state = 'leased'
              AND lease_token = ?
              AND fencing_token = ?
              AND lease_until >= ?
            LIMIT 1
            """,
            (
                claim.tenant_id,
                claim.outbox_id,
                claim.run_id,
                claim.lease_token,
                claim.fencing_token,
                now_text,
            ),
        ).fetchone()
        if row is None:
            raise StaleLeaseError()
        if (
            str(row["command_json"]) != claim.command_json
            or str(row["command_hash"]) != claim.command_hash
            or sha256_text(claim.command_json) != claim.command_hash
        ):
            raise ProductRunExecutionError(
                "stored_command_hash_mismatch",
                retryable=False,
            )
        return row

    @staticmethod
    def _upsert_exchange_request(
        database: sqlite3.Connection,
        claim: OutboxClaim,
        *,
        phase: str,
        path: str,
        now_text: str,
    ) -> sqlite3.Row:
        database.execute(
            """
            INSERT INTO product_runtime_exchanges (
                tenant_id, id, run_id, phase, request_method, path,
                request_json, request_hash, response_status, response_json,
                response_hash, execution_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'POST', ?, ?, ?, NULL, NULL, NULL, NULL, ?, ?)
            ON CONFLICT(tenant_id, run_id, phase) DO NOTHING
            """,
            (
                claim.tenant_id,
                new_id("exchange"),
                claim.run_id,
                phase,
                path,
                claim.command_json,
                claim.command_hash,
                now_text,
                now_text,
            ),
        )
        exchange = database.execute(
            """
            SELECT *
            FROM product_runtime_exchanges
            WHERE tenant_id = ? AND run_id = ? AND phase = ?
            LIMIT 1
            """,
            (claim.tenant_id, claim.run_id, phase),
        ).fetchone()
        if (
            exchange is None
            or str(exchange["request_json"]) != claim.command_json
            or str(exchange["request_hash"]) != claim.command_hash
            or str(exchange["path"]) != path
        ):
            raise ProductRunExecutionError(
                "runtime_exchange_conflict",
                retryable=False,
            )
        return exchange

    def prepare_delivery(
        self,
        claim: OutboxClaim,
        *,
        phase: str,
        path: str,
    ) -> None:
        database = connect_database(self.database_url)
        now_text = _iso()
        try:
            with transaction(database, immediate=True):
                self._owned_outbox(database, claim, now_text=now_text)
                _enforce_claim_policy(database, claim)
                self._upsert_exchange_request(
                    database,
                    claim,
                    phase=phase,
                    path=path,
                    now_text=now_text,
                )
        finally:
            database.close()

    @staticmethod
    def _store_exchange_response(
        database: sqlite3.Connection,
        claim: OutboxClaim,
        *,
        phase: str,
        response: HomeRuntimeResponse,
        execution_id: str | None,
        now_text: str,
    ) -> None:
        body = _response_body(response)
        updated = database.execute(
            """
            UPDATE product_runtime_exchanges
            SET response_status = ?,
                response_json = ?,
                response_hash = ?,
                execution_id = ?,
                updated_at = ?
            WHERE tenant_id = ? AND run_id = ? AND phase = ?
              AND request_json = ? AND request_hash = ?
            """,
            (
                response.http_status,
                body,
                sha256_text(body),
                execution_id,
                now_text,
                claim.tenant_id,
                claim.run_id,
                phase,
                claim.command_json,
                claim.command_hash,
            ),
        )
        if updated.rowcount != 1:
            raise ProductRunExecutionError(
                "runtime_exchange_missing",
                retryable=False,
            )

    @staticmethod
    def _append_event(
        database: sqlite3.Connection,
        *,
        tenant_id: str,
        run_id: str,
        sequence: int,
        event: Mapping[str, Any],
        now_text: str,
    ) -> None:
        database.execute(
            """
            INSERT INTO chat_run_events (
                tenant_id, event_id, run_id, sequence, event_type,
                event_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                new_id("event"),
                run_id,
                sequence,
                str(event["type"]),
                canonical_json(event),
                now_text,
            ),
        )

    @staticmethod
    def _record_provider_execution_projection(
        database: sqlite3.Connection,
        *,
        tenant_id: str,
        profile: str,
        status: str,
        now_text: str,
        evidence_hash: str | None = None,
        error_code: str | None = None,
    ) -> None:
        if profile not in {"mimo-code", "codex-cli"}:
            return
        if status == "connected":
            database.execute(
                """
                INSERT INTO provider_connections (
                    tenant_id, provider_id, status, auth_flow_supported,
                    authority_observed, last_verified_at,
                    last_evidence_hash, last_intent_id,
                    last_error_code, created_at, updated_at
                ) VALUES (
                    ?, ?, 'connected', 0, 1, ?, ?, NULL, NULL, ?, ?
                )
                ON CONFLICT(tenant_id, provider_id) DO UPDATE SET
                    status = 'connected',
                    authority_observed = 1,
                    last_verified_at = excluded.last_verified_at,
                    last_evidence_hash = excluded.last_evidence_hash,
                    last_error_code = NULL,
                    updated_at = excluded.updated_at
                """,
                (
                    tenant_id,
                    profile,
                    now_text,
                    evidence_hash,
                    now_text,
                    now_text,
                ),
            )
            return
        if status == "error" and error_code is not None:
            database.execute(
                """
                INSERT INTO provider_connections (
                    tenant_id, provider_id, status, auth_flow_supported,
                    authority_observed, last_verified_at,
                    last_evidence_hash, last_intent_id,
                    last_error_code, created_at, updated_at
                ) VALUES (
                    ?, ?, 'error', 0, 1, NULL, NULL, NULL, ?, ?, ?
                )
                ON CONFLICT(tenant_id, provider_id) DO UPDATE SET
                    status = 'error',
                    authority_observed = 1,
                    last_verified_at = NULL,
                    last_evidence_hash = NULL,
                    last_error_code = excluded.last_error_code,
                    updated_at = excluded.updated_at
                """,
                (
                    tenant_id,
                    profile,
                    error_code[:128],
                    now_text,
                    now_text,
                ),
            )

    @staticmethod
    def _is_provider_auth_or_policy_failure(code: str) -> bool:
        normalized = code.strip().lower()
        return (
            normalized
            in {
                "runner_auth_blocked",
                "provider_authentication_failed",
                "provider_authorization_failed",
                "provider_credentials_invalid",
                "provider_policy_denied",
                "codex_login_required",
                "mimo_auth_required",
            }
            or normalized.startswith("provider_auth_")
            or normalized.startswith("provider_policy_")
            or normalized.endswith("_auth_blocked")
        )

    @staticmethod
    def _fresh_run_command(
        *,
        initialize_command: Mapping[str, Any],
        runtime_profile: str,
        case_id: str,
        deadline_seconds: int,
        now: datetime,
        execution_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        source_payload = initialize_command["payload"]
        run_id = str(source_payload["run_id"])
        input_message_id = str(source_payload["input_message_id"])
        goal_id = str(source_payload["goal_id"])
        is_developer = (
            execution_context is not None
            and execution_context.get("execution_mode") == "developer"
        )
        if is_developer:
            authority = initialize_command.get("identity", {}).get(
                "authority",
                {},
            )
            if (
                execution_context.get("authority_role") != "owner"
                or not all(
                    isinstance(execution_context.get(field_name), str)
                    and bool(str(execution_context[field_name]).strip())
                    for field_name in (
                        "workspace_ref",
                        "access_mode",
                        "sandbox_profile",
                        "approval_policy",
                    )
                )
                or not isinstance(authority, Mapping)
                or "product.developer.run.execute.request"
                not in authority.get("capabilities", ())
            ):
                raise ProductRunExecutionError(
                    "developer_execution_context_invalid",
                    retryable=False,
                )
        trusted_binding_fields = (
            "trusted_agent_profile_id",
            "trusted_agent_profile_epoch",
            "trusted_agent_workspace_binding_id",
            "trusted_agent_workspace_binding_epoch",
        )
        trusted_binding_values = (
            tuple(
                execution_context.get(field_name)
                for field_name in trusted_binding_fields
            )
            if execution_context is not None
            else (None, None, None, None)
        )
        trusted_bound = all(
            value is not None for value in trusted_binding_values
        )
        if any(
            value is not None for value in trusted_binding_values
        ) and not trusted_bound:
            raise ProductRunExecutionError(
                "trusted_agent_execution_binding_invalid",
                retryable=False,
            )
        payload_schema_id = (
            (
                "kolibri.product.run.execute.v1_3.command"
                if trusted_bound
                else "kolibri.product.run.execute.v1_2.command"
            )
            if is_developer
            else "kolibri.product.run.execute.v1_1.command"
        )
        payload_schema_version = (
            ("1.3" if trusted_bound else "1.2")
            if is_developer
            else "1.1"
        )
        command = {
            "schema_id": "kolibri.command",
            "schema_version": "1.0",
            "message_id": new_id("cmd"),
            "command_name": "product.run.execute",
            "payload_schema_id": payload_schema_id,
            "payload_schema_version": payload_schema_version,
            "issued_at": _iso(now),
            "deadline_at": _iso(
                now + timedelta(seconds=deadline_seconds)
            ),
            "target_owner": "logical_home_control_plane",
            "identity": copy.deepcopy(initialize_command["identity"]),
            "trace": {
                "trace_id": uuid.uuid4().hex,
                "span_id": uuid.uuid4().hex[:16],
                "parent_span_id": None,
                "correlation_id": run_id,
                "causation_id": input_message_id,
            },
            "idempotency": {
                "key": f"product.run.execute:{run_id}",
                "scope": "aggregate",
                "scope_id": run_id,
                "canonical_request_hash": "sha256:" + ("0" * 64),
            },
            "payload": {
                "schema_id": payload_schema_id,
                "schema_version": payload_schema_version,
                "tenant_id": source_payload["tenant_id"],
                "project_id": source_payload["project_id"],
                "thread_id": source_payload["thread_id"],
                "run_id": run_id,
                "input_message_id": input_message_id,
                "case_id": case_id,
                "goal_id": goal_id,
                "prompt": source_payload["prompt"],
                "prompt_hash": source_payload["prompt_hash"],
            },
        }
        if is_developer:
            command["payload"].update(
                {
                    "execution_mode": "developer",
                    "runtime_profile": runtime_profile,
                    "model": execution_context.get("model_id"),
                    "reasoning_effort": execution_context.get(
                        "reasoning_effort"
                    ),
                    "service_tier": execution_context.get("service_tier"),
                    "workspace_ref": execution_context.get("workspace_ref"),
                    "access_mode": execution_context.get("access_mode"),
                    "sandbox": execution_context.get("sandbox_profile"),
                    "approval_policy": execution_context.get(
                        "approval_policy"
                    ),
                    "reviewer": execution_context.get("approvals_reviewer"),
                    "requester_role": execution_context.get(
                        "authority_role"
                    ),
                }
            )
            if trusted_bound:
                command["payload"].update(
                    {
                        field_name: execution_context[field_name]
                        for field_name in trusted_binding_fields
                    }
                )
        else:
            if execution_context is None:
                raise ProductRunExecutionError(
                    "run_execution_context_missing",
                    retryable=False,
                )
            if execution_context.get("service_tier") is not None:
                raise ProductRunExecutionError(
                    "home_service_tier_unsupported",
                    retryable=False,
                )
            model = execution_context.get("model_id")
            effort = execution_context.get("reasoning_effort")
            if (model is None) != (effort is None):
                raise ProductRunExecutionError(
                    "home_model_selection_incomplete",
                    retryable=False,
                )
            command["payload"].update(
                {
                    "preferred_agent_profile": runtime_profile,
                    "preferred_model": model,
                    "preferred_reasoning_effort": effort,
                }
            )
        command["identity"]["subject_refs"] = {
            "goal_id": goal_id,
            "case_id": case_id,
            "task_id": None,
        }
        command["idempotency"]["canonical_request_hash"] = (
            canonical_command_hash(command)
        )
        return command

    def apply_goal_initialized(
        self,
        claim: OutboxClaim,
        response: HomeRuntimeResponse,
        *,
        deadline_seconds: int,
    ) -> None:
        status = response.value
        command = _decode_command(claim.command_json)
        payload = command["payload"]
        if (
            status.get("run_id") != claim.run_id
            or status.get("goal_id") != payload.get("goal_id")
            or status.get("case_id") != f"case_{payload.get('goal_id')}"
        ):
            raise ProductRunExecutionError(
                "goal_initialization_binding_invalid",
                retryable=False,
            )
        database = connect_database(self.database_url)
        now = _now()
        now_text = _iso(now)
        try:
            with transaction(database, immediate=True):
                self._owned_outbox(database, claim, now_text=now_text)
                _enforce_claim_policy(database, claim)
                if status.get("status") == "failed":
                    error = status["error"]
                    self._store_exchange_response(
                        database,
                        claim,
                        phase="goal_initialize",
                        response=response,
                        execution_id=None,
                        now_text=now_text,
                    )
                    database.execute(
                        """
                        UPDATE product_project_runtime
                        SET goal_state = 'failed',
                            goal_error_code = ?,
                            updated_at = ?
                        WHERE tenant_id = ? AND project_id = ?
                        """,
                        (
                            str(error["code"])[:128],
                            now_text,
                            claim.tenant_id,
                            payload["project_id"],
                        ),
                    )
                    self._finish_error_in_transaction(
                        database,
                        claim,
                        code=str(error["code"]),
                        safe_message=str(error["safe_message"]),
                        now_text=now_text,
                    )
                    return
                if status.get("status") != "initialized":
                    raise ProductRunExecutionError(
                        "goal_initialization_status_invalid",
                        retryable=False,
                    )
                run = database.execute(
                    """
                    SELECT run.selected_profile,
                           context.execution_mode,
                           context.authority_role,
                           context.workspace_ref,
                           context.access_mode,
                           context.sandbox_profile,
                           context.approval_policy,
                           context.approvals_reviewer,
                           context.model_id,
                           context.reasoning_effort,
                           context.service_tier,
                           context.trusted_agent_profile_id,
                           context.trusted_agent_profile_epoch,
                           context.trusted_agent_workspace_binding_id,
                           context.trusted_agent_workspace_binding_epoch
                    FROM chat_runs AS run
                    LEFT JOIN chat_run_execution_contexts AS context
                      ON context.tenant_id = run.tenant_id
                     AND context.run_id = run.id
                    WHERE run.tenant_id = ? AND run.id = ?
                    LIMIT 1
                    """,
                    (claim.tenant_id, claim.run_id),
                ).fetchone()
                if run is None:
                    raise ProductRunExecutionError(
                        "chat_run_missing",
                        retryable=False,
                    )
                run_command = self._fresh_run_command(
                    initialize_command=command,
                    runtime_profile=str(run["selected_profile"]),
                    case_id=str(status["case_id"]),
                    deadline_seconds=deadline_seconds,
                    now=now,
                    execution_context=dict(run),
                )
                run_command_json = canonical_json(run_command)
                self._store_exchange_response(
                    database,
                    claim,
                    phase="goal_initialize",
                    response=response,
                    execution_id=None,
                    now_text=now_text,
                )
                database.execute(
                    """
                    UPDATE product_project_runtime
                    SET goal_state = 'initialized',
                        goal_error_code = NULL,
                        goal_id = ?,
                        case_id = ?,
                        updated_at = ?
                    WHERE tenant_id = ? AND project_id = ?
                    """,
                    (
                        status["goal_id"],
                        status["case_id"],
                        now_text,
                        claim.tenant_id,
                        payload["project_id"],
                    ),
                )
                updated = database.execute(
                    """
                    UPDATE product_run_outbox
                    SET command_kind = 'product.run.execute',
                        phase = 'run_execute',
                        state = 'queued',
                        command_json = ?,
                        command_hash = ?,
                        max_attempts = CASE
                            WHEN ? = 'developer' THEN 1
                            ELSE max_attempts
                        END,
                        attempts = CASE
                            WHEN ? = 'developer' THEN 0
                            ELSE attempts
                        END,
                        available_at = ?,
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_until = NULL,
                        last_error_code = NULL,
                        updated_at = ?
                    WHERE tenant_id = ? AND id = ?
                      AND lease_token = ? AND fencing_token = ?
                    """,
                    (
                        run_command_json,
                        sha256_text(run_command_json),
                        run["execution_mode"],
                        run["execution_mode"],
                        now_text,
                        now_text,
                        claim.tenant_id,
                        claim.outbox_id,
                        claim.lease_token,
                        claim.fencing_token,
                    ),
                )
                if updated.rowcount != 1:
                    raise StaleLeaseError()
        finally:
            database.close()

    def apply_run_status(
        self,
        claim: OutboxClaim,
        response: HomeRuntimeResponse,
        *,
        poll_seconds: float,
        trusted_claim: TrustedAgentWorkerClaim | None = None,
    ) -> str:
        status = response.value
        state = str(status["status"])
        runtime_profile = _runtime_profile_from_status(status)
        database = connect_database(self.database_url)
        now = _now()
        now_text = _iso(now)
        try:
            with transaction(database, immediate=True):
                self._owned_outbox(database, claim, now_text=now_text)
                _enforce_claim_policy(database, claim)
                self._fence_trusted_agent_in_transaction(
                    database,
                    claim,
                    trusted_claim,
                )
                existing_runtime = database.execute(
                    """
                    SELECT execution_id, resolved_profile
                    FROM product_run_runtime
                    WHERE tenant_id = ? AND run_id = ?
                    LIMIT 1
                    """,
                    (claim.tenant_id, claim.run_id),
                ).fetchone()
                if existing_runtime is not None:
                    if (
                        existing_runtime["execution_id"] is not None
                        and str(existing_runtime["execution_id"])
                        != str(status["execution_id"])
                    ) or (
                        existing_runtime["resolved_profile"] is not None
                        and str(existing_runtime["resolved_profile"])
                        != runtime_profile
                    ):
                        raise ProductRunExecutionError(
                            "home_execution_binding_changed",
                            retryable=False,
                        )
                database.execute(
                    """
                    INSERT INTO product_run_runtime (
                        tenant_id, run_id, execution_id, resolved_profile,
                        verification_status, result_hash, evidence_json,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tenant_id, run_id) DO UPDATE SET
                        execution_id = excluded.execution_id,
                        resolved_profile = excluded.resolved_profile,
                        verification_status = excluded.verification_status,
                        result_hash = excluded.result_hash,
                        evidence_json = excluded.evidence_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        claim.tenant_id,
                        claim.run_id,
                        status["execution_id"],
                        runtime_profile,
                        status["verification_status"],
                        status["result_hash"],
                        (
                            canonical_json(status["evidence"])
                            if status["evidence"] is not None
                            else None
                        ),
                        now_text,
                        now_text,
                    ),
                )
                self._store_exchange_response(
                    database,
                    claim,
                    phase="run_execute",
                    response=response,
                    execution_id=str(status["execution_id"]),
                    now_text=now_text,
                )
                if state in {"accepted", "running"}:
                    database.execute(
                        """
                        UPDATE product_run_outbox
                        SET state = 'polling',
                            available_at = ?,
                            lease_owner = NULL,
                            lease_token = NULL,
                            lease_until = NULL,
                            updated_at = ?
                        WHERE tenant_id = ? AND id = ?
                          AND lease_token = ? AND fencing_token = ?
                        """,
                        (
                            _iso(now + timedelta(seconds=poll_seconds)),
                            now_text,
                            claim.tenant_id,
                            claim.outbox_id,
                            claim.lease_token,
                            claim.fencing_token,
                        ),
                    )
                    database.execute(
                        """
                        UPDATE chat_runs
                        SET heartbeat_at = ?, updated_at = ?
                        WHERE tenant_id = ? AND id = ?
                        """,
                        (now_text, now_text, claim.tenant_id, claim.run_id),
                    )
                    return state
                if state == "failed":
                    error = status["error"]
                    error_code = str(error["code"])
                    self._terminalize_trusted_agent_in_transaction(
                        database,
                        trusted_claim,
                        terminal_state="released",
                        reason="run_failed",
                    )
                    if self._is_provider_auth_or_policy_failure(error_code):
                        self._record_provider_execution_projection(
                            database,
                            tenant_id=claim.tenant_id,
                            profile=runtime_profile,
                            status="error",
                            now_text=now_text,
                            error_code=error_code,
                        )
                    self._finish_error_in_transaction(
                        database,
                        claim,
                        code=error_code,
                        safe_message=str(error["safe_message"]),
                        now_text=now_text,
                    )
                    return "failed"

                result_text = str(status["result_text"])
                evidence = status["evidence"]
                self._terminalize_trusted_agent_in_transaction(
                    database,
                    trusted_claim,
                    terminal_state="released",
                    reason="run_succeeded",
                )
                provider_evidence_hash = (
                    str(evidence["content_hash"])
                    if isinstance(evidence, dict)
                    and isinstance(evidence.get("content_hash"), str)
                    else str(status["result_hash"])
                )
                self._record_provider_execution_projection(
                    database,
                    tenant_id=claim.tenant_id,
                    profile=runtime_profile,
                    status="connected",
                    now_text=now_text,
                    evidence_hash=provider_evidence_hash,
                )
                run = database.execute(
                    """
                    SELECT project_id, thread_id, client_run_id,
                           last_event_sequence
                    FROM chat_runs
                    WHERE tenant_id = ? AND id = ?
                    LIMIT 1
                    """,
                    (claim.tenant_id, claim.run_id),
                ).fetchone()
                if run is None:
                    raise ProductRunExecutionError(
                        "chat_run_missing",
                        retryable=False,
                    )
                public_thread = database.execute(
                    """
                    SELECT client_thread_id
                    FROM chat_client_threads
                    WHERE tenant_id = ? AND thread_id = ?
                    LIMIT 1
                    """,
                    (claim.tenant_id, run["thread_id"]),
                ).fetchone()
                public_thread_id = (
                    str(public_thread["client_thread_id"])
                    if public_thread is not None
                    else str(run["thread_id"])
                )
                sequence_row = database.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0) AS value
                    FROM chat_messages
                    WHERE tenant_id = ? AND thread_id = ?
                    """,
                    (claim.tenant_id, run["thread_id"]),
                ).fetchone()
                message_id = new_id("message")
                database.execute(
                    """
                    INSERT INTO chat_messages (
                        tenant_id, id, project_id, thread_id, sequence,
                        client_message_id, run_id, role, content_text,
                        created_by_user_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, NULL, ?, 'assistant', ?, NULL, ?)
                    """,
                    (
                        claim.tenant_id,
                        message_id,
                        run["project_id"],
                        run["thread_id"],
                        int(sequence_row["value"]) + 1,
                        claim.run_id,
                        result_text,
                        now_text,
                    ),
                )
                first = int(run["last_event_sequence"]) + 1
                events = (
                    {
                        "type": "TEXT_MESSAGE_START",
                        "messageId": message_id,
                        "role": "assistant",
                    },
                    {
                        "type": "TEXT_MESSAGE_CONTENT",
                        "messageId": message_id,
                        "delta": result_text,
                    },
                    {
                        "type": "TEXT_MESSAGE_END",
                        "messageId": message_id,
                    },
                    {
                        "type": "RUN_FINISHED",
                        "threadId": public_thread_id,
                        "runId": str(run["client_run_id"]),
                        "outcome": {"type": "success"},
                    },
                )
                for offset, event in enumerate(events):
                    self._append_event(
                        database,
                        tenant_id=claim.tenant_id,
                        run_id=claim.run_id,
                        sequence=first + offset,
                        event=event,
                        now_text=now_text,
                    )
                database.execute(
                    """
                    UPDATE chat_runs
                    SET assistant_message_id = ?,
                        status = 'succeeded',
                        outcome = 'success',
                        last_event_sequence = ?,
                        error_code = NULL,
                        heartbeat_at = ?,
                        updated_at = ?,
                        finished_at = ?
                    WHERE tenant_id = ? AND id = ?
                    """,
                    (
                        message_id,
                        first + len(events) - 1,
                        now_text,
                        now_text,
                        now_text,
                        claim.tenant_id,
                        claim.run_id,
                    ),
                )
                database.execute(
                    """
                    UPDATE chat_threads
                    SET message_count = message_count + 1,
                        last_message_at = ?,
                        updated_at = ?
                    WHERE tenant_id = ? AND id = ?
                    """,
                    (
                        now_text,
                        now_text,
                        claim.tenant_id,
                        run["thread_id"],
                    ),
                )
                database.execute(
                    """
                    UPDATE product_run_outbox
                    SET state = 'completed',
                        completed_at = ?,
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_until = NULL,
                        last_error_code = NULL,
                        updated_at = ?
                    WHERE tenant_id = ? AND id = ?
                      AND lease_token = ? AND fencing_token = ?
                    """,
                    (
                        now_text,
                        now_text,
                        claim.tenant_id,
                        claim.outbox_id,
                        claim.lease_token,
                        claim.fencing_token,
                    ),
                )
                return "succeeded"
        finally:
            database.close()

    def _finish_error_in_transaction(
        self,
        database: sqlite3.Connection,
        claim: OutboxClaim,
        *,
        code: str,
        safe_message: str,
        now_text: str,
    ) -> None:
        code = code[:96] if code else "product_run_failed"
        safe_message = (
            safe_message[:500]
            if safe_message
            else "Не удалось завершить запрос. Повторите попытку."
        )
        run = database.execute(
            """
            SELECT last_event_sequence
            FROM chat_runs
            WHERE tenant_id = ? AND id = ?
            LIMIT 1
            """,
            (claim.tenant_id, claim.run_id),
        ).fetchone()
        if run is None:
            raise ProductRunExecutionError(
                "chat_run_missing",
                retryable=False,
            )
        sequence = int(run["last_event_sequence"]) + 1
        self._append_event(
            database,
            tenant_id=claim.tenant_id,
            run_id=claim.run_id,
            sequence=sequence,
            event={
                "type": "RUN_ERROR",
                "message": safe_message,
                "code": code,
            },
            now_text=now_text,
        )
        database.execute(
            """
            UPDATE chat_runs
            SET status = 'failed',
                outcome = 'failure',
                last_event_sequence = ?,
                error_code = ?,
                heartbeat_at = ?,
                updated_at = ?,
                finished_at = ?
            WHERE tenant_id = ? AND id = ?
            """,
            (
                sequence,
                code,
                now_text,
                now_text,
                now_text,
                claim.tenant_id,
                claim.run_id,
            ),
        )
        database.execute(
            """
            UPDATE product_run_outbox
            SET state = 'blocked',
                attempts = MIN(max_attempts, attempts + 1),
                completed_at = ?,
                lease_owner = NULL,
                lease_token = NULL,
                lease_until = NULL,
                last_error_code = ?,
                updated_at = ?
            WHERE tenant_id = ? AND id = ?
              AND lease_token = ? AND fencing_token = ?
            """,
            (
                now_text,
                code,
                now_text,
                claim.tenant_id,
                claim.outbox_id,
                claim.lease_token,
                claim.fencing_token,
            ),
        )

    def record_failure(
        self,
        claim: OutboxClaim,
        failure: ProductRunExecutionError,
        *,
        retry_base_seconds: float,
        retry_max_seconds: float,
        trusted_claim: TrustedAgentWorkerClaim | None = None,
    ) -> str:
        database = connect_database(self.database_url)
        now = _now()
        now_text = _iso(now)
        try:
            with transaction(database, immediate=True):
                self._owned_outbox(database, claim, now_text=now_text)
                try:
                    scope = self._trusted_agent_scope_for_claim(
                        database,
                        claim,
                    )
                except ProductRunExecutionError:
                    # A malformed/downgraded command cannot have passed lease
                    # acquisition, so preserve the original delivery failure.
                    scope = None
                if trusted_claim is not None:
                    if scope is not None and trusted_claim.scope != scope:
                        raise ProductRunExecutionError(
                            "trusted_agent_lease_scope_mismatch",
                            retryable=False,
                        )
                    self._revoke_trusted_agent_in_transaction(
                        database,
                        trusted_claim,
                        reason="delivery_failure",
                    )
                elif scope is not None:
                    self._revoke_scope_lease_in_transaction(
                        database,
                        scope,
                        reason="delivery_failure",
                    )
                try:
                    _enforce_claim_policy(database, claim)
                except ProductRunExecutionError as policy_failure:
                    self._finish_error_in_transaction(
                        database,
                        claim,
                        code=policy_failure.code,
                        safe_message=(
                            "Выполнение остановлено текущей политикой "
                            "доступа."
                        ),
                        now_text=now_text,
                    )
                    return "failed"
                next_attempt = claim.attempts + 1
                if (
                    failure.retryable
                    and not _is_developer_effect(claim.command_json)
                    and next_attempt < claim.max_attempts
                ):
                    delay = min(
                        retry_max_seconds,
                        retry_base_seconds * (2 ** min(next_attempt - 1, 12)),
                    )
                    database.execute(
                        """
                        UPDATE product_run_outbox
                        SET state = 'retry',
                            attempts = ?,
                            available_at = ?,
                            lease_owner = NULL,
                            lease_token = NULL,
                            lease_until = NULL,
                            last_error_code = ?,
                            updated_at = ?
                        WHERE tenant_id = ? AND id = ?
                          AND lease_token = ? AND fencing_token = ?
                        """,
                        (
                            next_attempt,
                            _iso(now + timedelta(seconds=delay)),
                            failure.code[:128],
                            now_text,
                            claim.tenant_id,
                            claim.outbox_id,
                            claim.lease_token,
                            claim.fencing_token,
                        ),
                    )
                    return "retry"
                public_code = (
                    "logical_home_unavailable"
                    if failure.infrastructure_outage or failure.retryable
                    else failure.code
                )
                self._finish_error_in_transaction(
                    database,
                    claim,
                    code=public_code,
                    safe_message=(
                        "Сервис выполнения временно недоступен. "
                        "Запрос сохранён; повторите его позже."
                        if failure.retryable or failure.infrastructure_outage
                        else "Не удалось безопасно выполнить запрос."
                    ),
                    now_text=now_text,
                )
                return "failed"
        finally:
            database.close()


class ProductRunWorker:
    def __init__(
        self,
        *,
        settings: Settings,
        transport_settings: ProductRunExecutionSettings,
        worker_id: str | None = None,
    ) -> None:
        self.settings = settings
        self.transport_settings = transport_settings
        self.store = ProductRunStore(settings.database_url)
        self.goal_client = HomeProductGoalClient(transport_settings)
        self.run_client = HomeProductRunClient(transport_settings)
        self.worker_id = worker_id or (
            f"v3-product-{socket.gethostname()}-{os.getpid()}-"
            f"{uuid.uuid4().hex[:8]}"
        )
        self._trusted_claims: dict[str, TrustedAgentWorkerClaim] = {}

    def run_once(self) -> bool:
        claim = self.store.claim_next(
            worker_id=self.worker_id,
            lease_seconds=self.settings.product_run_lease_seconds,
        )
        if claim is None:
            return False
        trusted_claim = self._trusted_claims.get(claim.run_id)
        try:
            if claim.phase == "goal_required":
                self.store.prepare_delivery(
                    claim,
                    phase="goal_initialize",
                    path=_GOAL_PATH,
                )
                self.store.fence_external_effect(claim, None)
                response = self.goal_client.execute_with_metadata(
                    claim.command_json
                )
                self.store.apply_goal_initialized(
                    claim,
                    response,
                    deadline_seconds=(
                        self.settings.product_run_command_deadline_seconds
                    ),
                )
                return True

            trusted_claim = self.store.acquire_trusted_agent_lease(
                claim,
                worker_id=self.worker_id,
                ttl_seconds=max(
                    1,
                    math.ceil(self.settings.product_run_lease_seconds),
                ),
                previous=trusted_claim,
            )
            if trusted_claim is None:
                self._trusted_claims.pop(claim.run_id, None)
            else:
                self._trusted_claims[claim.run_id] = trusted_claim
            runtime = connect_database(self.settings.database_url)
            try:
                binding = runtime.execute(
                    """
                    SELECT execution_id, resolved_profile
                    FROM product_run_runtime
                    WHERE tenant_id = ? AND run_id = ?
                    LIMIT 1
                    """,
                    (claim.tenant_id, claim.run_id),
                ).fetchone()
            finally:
                runtime.close()
            self.store.prepare_delivery(
                claim,
                phase="run_execute",
                path=_RUN_PATH,
            )
            self.store.fence_external_effect(claim, trusted_claim)
            response = self.run_client.execute_with_metadata(
                claim.command_json,
                expected_execution_id=(
                    str(binding["execution_id"])
                    if binding is not None
                    and binding["execution_id"] is not None
                    else None
                ),
                expected_profile=(
                    str(binding["resolved_profile"])
                    if binding is not None
                    and binding["resolved_profile"] is not None
                    else None
                ),
            )
            outcome = self.store.apply_run_status(
                claim,
                response,
                poll_seconds=self.settings.product_run_poll_seconds,
                trusted_claim=trusted_claim,
            )
            if outcome not in {"accepted", "running"}:
                self._trusted_claims.pop(claim.run_id, None)
        except TrustedAgentLeaseDeferred as deferred:
            self._trusted_claims.pop(claim.run_id, None)
            try:
                self.store.defer_trusted_agent_lease(claim, deferred)
            except StaleLeaseError:
                LOGGER.info(
                    "trusted-agent defer ignored after lease superseded "
                    "run_id=%s",
                    claim.run_id,
                )
        except StaleLeaseError:
            self._trusted_claims.pop(claim.run_id, None)
            LOGGER.info("stale lease ignored run_id=%s", claim.run_id)
        except ProductRunExecutionError as failure:
            try:
                outcome = self.store.record_failure(
                    claim,
                    failure,
                    retry_base_seconds=(
                        self.settings.product_run_retry_base_seconds
                    ),
                    retry_max_seconds=(
                        self.settings.product_run_retry_max_seconds
                    ),
                    trusted_claim=trusted_claim,
                )
                self._trusted_claims.pop(claim.run_id, None)
                LOGGER.warning(
                    "delivery classified run_id=%s code=%s outcome=%s",
                    claim.run_id,
                    failure.code,
                    outcome,
                )
            except StaleLeaseError:
                self._trusted_claims.pop(claim.run_id, None)
                LOGGER.info(
                    "failure ignored after lease superseded run_id=%s",
                    claim.run_id,
                )
        return True

    def run_forever(self, stop: threading.Event) -> None:
        try:
            while not stop.is_set():
                record_product_worker_heartbeat(
                    self.settings.database_url,
                    instance_id=self.worker_id,
                )
                if not self.run_once():
                    stop.wait(self.settings.product_run_idle_seconds)
        finally:
            clear_product_worker_heartbeat(
                self.settings.database_url,
                instance_id=self.worker_id,
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dispatch V3 Product Chat runs through Logical Home."
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser


def main() -> int:
    args = _parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = Settings.from_env()
    settings.require_product_authority_grant()
    initialize_database(settings.database_url)
    worker = ProductRunWorker(
        settings=settings,
        transport_settings=ProductRunExecutionSettings.from_env(),
    )
    if args.once:
        worker.run_once()
        return 0

    stop = threading.Event()

    def request_stop(_signum, _frame) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    worker.run_forever(stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
