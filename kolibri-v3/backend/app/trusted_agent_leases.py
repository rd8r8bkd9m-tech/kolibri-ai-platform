"""Transactional lease lifecycle for the singleton R1 trusted agent.

The raw claim token is a worker-held capability and is never persisted.
Callers must re-run :func:`fence_trusted_agent_lease` immediately before every
external effect and again before committing an effect result.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import sqlite3
import time
from typing import Any, Literal
import uuid

from .database import transaction


LeaseState = Literal["active", "released", "revoked", "expired"]
TerminalState = Literal["released", "expired"]
OperationKind = Literal[
    "issue",
    "claim_or_renew",
    "terminalize",
    "revoke",
]

_BINDING_ID = re.compile(r"^wsb_[0-9a-f]{32}$")
_PROFILE_ID = re.compile(r"^tap_[0-9a-f]{32}$")
_LEASE_ID = re.compile(r"^tal_[0-9a-f]{32}$")
_OPAQUE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{0,159}$")
_CLAIM_OWNER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{2,159}$")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:~-]{15,159}$")
_CLAIM_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{31,255}$")
_REASON_CODE = re.compile(r"^[a-z][a-z0-9._-]{2,119}$")
_MIN_TTL_SECONDS = 1
_MAX_TTL_SECONDS = 3_600


class TrustedAgentLeaseError(RuntimeError):
    """A stable internal failure contract for worker/control-plane callers."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class TrustedAgentLeaseScope:
    owner_user_id: str
    owner_tenant_id: str
    authority_epoch: int
    profile_id: str
    profile_epoch: int
    workspace_binding_id: str
    workspace_binding_epoch: int
    assignment_ref: str


@dataclass(frozen=True, slots=True)
class TrustedAgentLeaseSnapshot:
    id: str
    state: LeaseState
    assignment_ref: str
    owner_user_id: str
    owner_tenant_id: str
    authority_epoch: int
    profile_id: str
    profile_epoch: int
    workspace_binding_id: str
    workspace_binding_epoch: int
    claim_owner: str | None
    fencing_token: int
    expires_at: int
    terminal_at: int | None
    terminal_reason: str | None
    created_at: int
    updated_at: int


def _error(
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> TrustedAgentLeaseError:
    return TrustedAgentLeaseError(
        code,
        message,
        retryable=retryable,
    )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(
        value.encode("utf-8", "strict")
    ).hexdigest()


def _request_hash(
    operation_kind: OperationKind,
    payload: dict[str, object],
) -> str:
    return _sha256(
        _canonical_json(
            {
                "schema": "kolibri.trusted-agent.lease-operation.v1",
                "operation": operation_kind,
                "payload": payload,
            }
        )
    )


def _now(value: int | None) -> int:
    current = int(time.time()) if value is None else value
    if (
        isinstance(current, bool)
        or not isinstance(current, int)
        or current < 0
    ):
        raise ValueError("now must be a non-negative integer timestamp")
    return current


def _ttl(value: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not _MIN_TTL_SECONDS <= value <= _MAX_TTL_SECONDS
    ):
        raise ValueError(
            "ttl_seconds must be an integer between 1 and 3600"
        )
    return value


def _idempotency_hash(value: str) -> str:
    if not isinstance(value, str) or _IDEMPOTENCY_KEY.fullmatch(value) is None:
        raise ValueError("idempotency_key is invalid")
    return _sha256(value)


def _claim_token_hash(value: str) -> str:
    if not isinstance(value, str) or _CLAIM_TOKEN.fullmatch(value) is None:
        raise ValueError("claim_token is invalid")
    return _sha256(value)


def _claim_owner(value: str) -> str:
    if not isinstance(value, str) or _CLAIM_OWNER.fullmatch(value) is None:
        raise ValueError("claim_owner is invalid")
    return value


def _reason(value: str) -> str:
    if not isinstance(value, str) or _REASON_CODE.fullmatch(value) is None:
        raise ValueError("terminal reason is invalid")
    return value


def _validate_scope(scope: TrustedAgentLeaseScope) -> None:
    if (
        not isinstance(scope, TrustedAgentLeaseScope)
        or not isinstance(scope.owner_user_id, str)
        or _OPAQUE_REF.fullmatch(scope.owner_user_id) is None
        or not isinstance(scope.owner_tenant_id, str)
        or _OPAQUE_REF.fullmatch(scope.owner_tenant_id) is None
        or isinstance(scope.authority_epoch, bool)
        or not isinstance(scope.authority_epoch, int)
        or scope.authority_epoch < 1
        or not isinstance(scope.profile_id, str)
        or _PROFILE_ID.fullmatch(scope.profile_id) is None
        or isinstance(scope.profile_epoch, bool)
        or not isinstance(scope.profile_epoch, int)
        or scope.profile_epoch < 1
        or not isinstance(scope.workspace_binding_id, str)
        or _BINDING_ID.fullmatch(scope.workspace_binding_id) is None
        or isinstance(scope.workspace_binding_epoch, bool)
        or not isinstance(scope.workspace_binding_epoch, int)
        or scope.workspace_binding_epoch < 1
        or not isinstance(scope.assignment_ref, str)
        or _OPAQUE_REF.fullmatch(scope.assignment_ref) is None
    ):
        raise ValueError("trusted-agent lease scope is invalid")


def _scope_payload(scope: TrustedAgentLeaseScope) -> dict[str, object]:
    return {
        "ownerUserId": scope.owner_user_id,
        "ownerTenantId": scope.owner_tenant_id,
        "authorityEpoch": scope.authority_epoch,
        "profileId": scope.profile_id,
        "profileEpoch": scope.profile_epoch,
        "workspaceBindingId": scope.workspace_binding_id,
        "workspaceBindingEpoch": scope.workspace_binding_epoch,
        "assignmentRef": scope.assignment_ref,
    }


def _validate_live_scope(
    database: sqlite3.Connection,
    scope: TrustedAgentLeaseScope,
) -> None:
    row = database.execute(
        """
        SELECT 1
        FROM trusted_agent_profiles AS profile
        JOIN trusted_agent_workspace_bindings AS binding
          ON binding.id = profile.workspace_binding_id
        JOIN platform_authority_grants AS authority
          ON authority.authority_id = profile.authority_id
         AND authority.user_id = profile.owner_user_id
         AND authority.tenant_id = profile.owner_tenant_id
        WHERE profile.id = ?
          AND profile.profile_epoch = ?
          AND profile.owner_user_id = ?
          AND profile.owner_tenant_id = ?
          AND profile.authority_epoch = ?
          AND profile.workspace_binding_id = ?
          AND profile.workspace_binding_epoch = ?
          AND profile.lifecycle_status = 'active'
          AND profile.capabilities_json
                = '["developer.runtime.execute"]'
          AND profile.tool_policy_id = 'developer.full.v1'
          AND profile.access_mode = 'full'
          AND profile.sandbox_profile = 'danger-full-access'
          AND profile.approval_policy = 'never'
          AND profile.approvals_reviewer IS NULL
          AND profile.max_concurrency = 1
          AND binding.id = ?
          AND binding.workspace_epoch = ?
          AND binding.owner_user_id = ?
          AND binding.owner_tenant_id = ?
          AND binding.authority_epoch = ?
          AND binding.lifecycle_status = 'active'
          AND authority.authority_id = 'platform_owner'
          AND authority.authority_epoch = ?
          AND authority.active = 1
          AND EXISTS (
              SELECT 1
              FROM json_each(authority.capabilities_json)
              WHERE value = 'chat.developer.request'
          )
        LIMIT 1
        """,
        (
            scope.profile_id,
            scope.profile_epoch,
            scope.owner_user_id,
            scope.owner_tenant_id,
            scope.authority_epoch,
            scope.workspace_binding_id,
            scope.workspace_binding_epoch,
            scope.workspace_binding_id,
            scope.workspace_binding_epoch,
            scope.owner_user_id,
            scope.owner_tenant_id,
            scope.authority_epoch,
            scope.authority_epoch,
        ),
    ).fetchone()
    if row is None:
        raise _error(
            "trusted_agent_lease_scope_changed",
            "Trusted-agent authority, profile, or workspace changed.",
        )


def _snapshot(row: sqlite3.Row) -> TrustedAgentLeaseSnapshot:
    assignment_ref = row["assignment_ref"]
    if (
        assignment_ref is None
        or _OPAQUE_REF.fullmatch(str(assignment_ref)) is None
    ):
        raise RuntimeError("trusted-agent lease assignment is invalid")
    state = str(row["state"])
    if state not in {"active", "released", "revoked", "expired"}:
        raise RuntimeError("trusted-agent lease state is invalid")
    return TrustedAgentLeaseSnapshot(
        id=str(row["id"]),
        state=state,  # type: ignore[arg-type]
        assignment_ref=str(assignment_ref),
        owner_user_id=str(row["owner_user_id"]),
        owner_tenant_id=str(row["owner_tenant_id"]),
        authority_epoch=int(row["authority_epoch"]),
        profile_id=str(row["profile_id"]),
        profile_epoch=int(row["profile_epoch"]),
        workspace_binding_id=str(row["workspace_binding_id"]),
        workspace_binding_epoch=int(row["workspace_binding_epoch"]),
        claim_owner=(
            None
            if row["claim_owner"] is None
            else str(row["claim_owner"])
        ),
        fencing_token=int(row["fencing_token"]),
        expires_at=int(row["expires_at"]),
        terminal_at=(
            None if row["terminal_at"] is None else int(row["terminal_at"])
        ),
        terminal_reason=(
            None
            if row["terminal_reason"] is None
            else str(row["terminal_reason"])
        ),
        created_at=int(row["created_at"]),
        updated_at=int(row["updated_at"]),
    )


def _snapshot_projection(row: sqlite3.Row) -> dict[str, Any]:
    value = _snapshot(row)
    return {
        "id": value.id,
        "state": value.state,
        "assignmentRef": value.assignment_ref,
        "authorityEpoch": value.authority_epoch,
        "profileId": value.profile_id,
        "profileEpoch": value.profile_epoch,
        "workspaceBindingId": value.workspace_binding_id,
        "workspaceBindingEpoch": value.workspace_binding_epoch,
        "claimOwner": value.claim_owner,
        "claimTokenPresent": row["claim_token_hash"] is not None,
        "fencingToken": value.fencing_token,
        "expiresAt": value.expires_at,
        "terminalAt": value.terminal_at,
        "terminalReason": value.terminal_reason,
        "createdAt": value.created_at,
        "updatedAt": value.updated_at,
    }


def _lease_row(
    database: sqlite3.Connection,
    lease_id: str,
) -> sqlite3.Row:
    if not isinstance(lease_id, str) or _LEASE_ID.fullmatch(lease_id) is None:
        raise ValueError("lease_id is invalid")
    row = database.execute(
        """
        SELECT *
        FROM trusted_agent_workspace_leases
        WHERE id = ?
        LIMIT 1
        """,
        (lease_id,),
    ).fetchone()
    if row is None:
        raise _error(
            "trusted_agent_lease_not_found",
            "Trusted-agent lease was not found.",
        )
    return row


def _exact_lease_row(
    database: sqlite3.Connection,
    *,
    lease_id: str,
    scope: TrustedAgentLeaseScope,
) -> sqlite3.Row:
    row = _lease_row(database, lease_id)
    if (
        str(row["owner_user_id"]) != scope.owner_user_id
        or str(row["owner_tenant_id"]) != scope.owner_tenant_id
        or int(row["authority_epoch"]) != scope.authority_epoch
        or str(row["profile_id"]) != scope.profile_id
        or int(row["profile_epoch"]) != scope.profile_epoch
        or str(row["workspace_binding_id"])
        != scope.workspace_binding_id
        or int(row["workspace_binding_epoch"])
        != scope.workspace_binding_epoch
        or row["assignment_ref"] != scope.assignment_ref
    ):
        raise _error(
            "trusted_agent_lease_scope_mismatch",
            "Trusted-agent lease scope does not match.",
        )
    return row


def _operation_row(
    database: sqlite3.Connection,
    *,
    scope: TrustedAgentLeaseScope,
    operation_kind: OperationKind,
    idempotency_key_hash: str,
    request_hash: str,
) -> sqlite3.Row | None:
    row = database.execute(
        """
        SELECT *
        FROM trusted_agent_lease_operations
        WHERE owner_tenant_id = ?
          AND operation_kind = ?
          AND idempotency_key_hash = ?
        LIMIT 1
        """,
        (
            scope.owner_tenant_id,
            operation_kind,
            idempotency_key_hash,
        ),
    ).fetchone()
    if row is None:
        return None
    if (
        str(row["owner_user_id"]) != scope.owner_user_id
        or str(row["request_hash"]) != request_hash
    ):
        raise _error(
            "trusted_agent_lease_idempotency_conflict",
            "Idempotency key was already used for another lease operation.",
        )
    return row


def _record_operation(
    database: sqlite3.Connection,
    *,
    scope: TrustedAgentLeaseScope,
    lease_row: sqlite3.Row,
    operation_kind: OperationKind,
    idempotency_key_hash: str,
    request_hash: str,
    now: int,
) -> None:
    database.execute(
        """
        INSERT INTO trusted_agent_lease_operations (
            id,
            owner_user_id,
            owner_tenant_id,
            lease_id,
            operation_kind,
            idempotency_key_hash,
            request_hash,
            response_json,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"talop_{uuid.uuid4().hex}",
            scope.owner_user_id,
            scope.owner_tenant_id,
            lease_row["id"],
            operation_kind,
            idempotency_key_hash,
            request_hash,
            _canonical_json(_snapshot_projection(lease_row)),
            now,
        ),
    )


def _replay_lease_row(
    database: sqlite3.Connection,
    *,
    operation_row: sqlite3.Row,
    scope: TrustedAgentLeaseScope,
) -> sqlite3.Row:
    return _exact_lease_row(
        database,
        lease_id=str(operation_row["lease_id"]),
        scope=scope,
    )


def _next_fencing_token(
    database: sqlite3.Connection,
    *,
    workspace_binding_id: str,
) -> int:
    return int(
        database.execute(
            """
            SELECT COALESCE(MAX(fencing_token), 0) + 1
            FROM trusted_agent_workspace_leases
            WHERE workspace_binding_id = ?
            """,
            (workspace_binding_id,),
        ).fetchone()[0]
    )


def _expire_competing_active_lease(
    database: sqlite3.Connection,
    *,
    now: int,
) -> None:
    row = database.execute(
        """
        SELECT *
        FROM trusted_agent_workspace_leases
        WHERE authority_id = 'platform_owner'
          AND state = 'active'
        ORDER BY created_at, id
        LIMIT 1
        """,
    ).fetchone()
    if row is None:
        return
    if int(row["expires_at"]) > now:
        raise _error(
            "trusted_agent_lease_concurrency_conflict",
            "The trusted agent already has an active assignment.",
            retryable=True,
        )
    updated = database.execute(
        """
        UPDATE trusted_agent_workspace_leases
        SET state = 'expired',
            updated_at = ?,
            terminal_at = ?,
            terminal_reason = 'lease_timeout'
        WHERE id = ?
          AND state = 'active'
          AND fencing_token = ?
          AND expires_at <= ?
        """,
        (
            now,
            now,
            row["id"],
            row["fencing_token"],
            now,
        ),
    )
    if updated.rowcount != 1:
        raise _error(
            "trusted_agent_lease_concurrency_conflict",
            "The trusted-agent lease changed concurrently.",
            retryable=True,
        )


def _claim_matches(
    row: sqlite3.Row,
    *,
    claim_owner: str,
    claim_token_hash: str,
) -> bool:
    persisted = row["claim_token_hash"]
    return (
        row["claim_owner"] == claim_owner
        and persisted is not None
        and hmac.compare_digest(str(persisted), claim_token_hash)
    )


def issue_trusted_agent_lease(
    database: sqlite3.Connection,
    *,
    scope: TrustedAgentLeaseScope,
    idempotency_key: str,
    ttl_seconds: int,
    now: int | None = None,
) -> TrustedAgentLeaseSnapshot:
    """Issue one unclaimed lease while preserving R1 maxConcurrency=1."""

    _validate_scope(scope)
    current = _now(now)
    ttl = _ttl(ttl_seconds)
    key_hash = _idempotency_hash(idempotency_key)
    request_hash = _request_hash(
        "issue",
        {**_scope_payload(scope), "ttlSeconds": ttl},
    )
    with transaction(database, immediate=True):
        replay = _operation_row(
            database,
            scope=scope,
            operation_kind="issue",
            idempotency_key_hash=key_hash,
            request_hash=request_hash,
        )
        if replay is not None:
            return _snapshot(
                _replay_lease_row(
                    database,
                    operation_row=replay,
                    scope=scope,
                )
            )
        _validate_live_scope(database, scope)
        existing_assignment = database.execute(
            """
            SELECT id
            FROM trusted_agent_workspace_leases
            WHERE owner_tenant_id = ? AND assignment_ref = ?
            LIMIT 1
            """,
            (scope.owner_tenant_id, scope.assignment_ref),
        ).fetchone()
        if existing_assignment is not None:
            raise _error(
                "trusted_agent_lease_assignment_conflict",
                "Assignment already has a trusted-agent lease.",
            )
        _expire_competing_active_lease(
            database,
            now=current,
        )
        lease_id = f"tal_{uuid.uuid4().hex}"
        fencing_token = _next_fencing_token(
            database,
            workspace_binding_id=scope.workspace_binding_id,
        )
        database.execute(
            """
            INSERT INTO trusted_agent_workspace_leases (
                id,
                authority_id,
                owner_user_id,
                owner_tenant_id,
                authority_epoch,
                profile_id,
                profile_epoch,
                workspace_binding_id,
                workspace_binding_epoch,
                state,
                fencing_token,
                created_at,
                updated_at,
                expires_at,
                assignment_ref,
                claim_owner,
                claim_token_hash,
                last_claimed_at,
                terminal_reason
            ) VALUES (
                ?, 'platform_owner', ?, ?, ?, ?, ?, ?, ?,
                'active', ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL
            )
            """,
            (
                lease_id,
                scope.owner_user_id,
                scope.owner_tenant_id,
                scope.authority_epoch,
                scope.profile_id,
                scope.profile_epoch,
                scope.workspace_binding_id,
                scope.workspace_binding_epoch,
                fencing_token,
                current,
                current,
                current + ttl,
                scope.assignment_ref,
            ),
        )
        row = _exact_lease_row(
            database,
            lease_id=lease_id,
            scope=scope,
        )
        _record_operation(
            database,
            scope=scope,
            lease_row=row,
            operation_kind="issue",
            idempotency_key_hash=key_hash,
            request_hash=request_hash,
            now=current,
        )
        return _snapshot(row)


def claim_or_renew_trusted_agent_lease(
    database: sqlite3.Connection,
    *,
    lease_id: str,
    scope: TrustedAgentLeaseScope,
    claim_owner: str,
    claim_token: str,
    idempotency_key: str,
    ttl_seconds: int,
    now: int | None = None,
) -> TrustedAgentLeaseSnapshot:
    """Claim, renew, or take over an elapsed lease with a monotonic fence."""

    _validate_scope(scope)
    owner = _claim_owner(claim_owner)
    token_hash = _claim_token_hash(claim_token)
    current = _now(now)
    ttl = _ttl(ttl_seconds)
    key_hash = _idempotency_hash(idempotency_key)
    request_hash = _request_hash(
        "claim_or_renew",
        {
            **_scope_payload(scope),
            "leaseId": lease_id,
            "claimOwner": owner,
            "claimTokenHash": token_hash,
            "ttlSeconds": ttl,
        },
    )
    with transaction(database, immediate=True):
        replay = _operation_row(
            database,
            scope=scope,
            operation_kind="claim_or_renew",
            idempotency_key_hash=key_hash,
            request_hash=request_hash,
        )
        if replay is not None:
            row = _replay_lease_row(
                database,
                operation_row=replay,
                scope=scope,
            )
            recorded = json.loads(str(replay["response_json"]))
            if (
                str(row["state"]) != "active"
                or int(row["expires_at"]) <= current
                or not _claim_matches(
                    row,
                    claim_owner=owner,
                    claim_token_hash=token_hash,
                )
                or not isinstance(recorded, dict)
                or recorded.get("fencingToken") != row["fencing_token"]
            ):
                raise _error(
                    "trusted_agent_lease_fenced",
                    "Trusted-agent lease claim was superseded.",
                )
            return _snapshot(row)
        _validate_live_scope(database, scope)
        before = _exact_lease_row(
            database,
            lease_id=lease_id,
            scope=scope,
        )
        if str(before["state"]) != "active":
            raise _error(
                "trusted_agent_lease_terminal",
                "Trusted-agent lease is already terminal.",
            )
        exact_claim = _claim_matches(
            before,
            claim_owner=owner,
            claim_token_hash=token_hash,
        )
        unclaimed = (
            before["claim_owner"] is None
            and before["claim_token_hash"] is None
        )
        elapsed = int(before["expires_at"]) <= current
        if not elapsed and not unclaimed and not exact_claim:
            raise _error(
                "trusted_agent_lease_busy",
                "Trusted-agent lease is held by another claimant.",
                retryable=True,
            )
        fencing_token = int(before["fencing_token"])
        if elapsed:
            fencing_token = _next_fencing_token(
                database,
                workspace_binding_id=scope.workspace_binding_id,
            )
        requested_expiry = current + ttl
        expires_at = (
            max(int(before["expires_at"]), requested_expiry)
            if exact_claim and not elapsed
            else requested_expiry
        )
        updated = database.execute(
            """
            UPDATE trusted_agent_workspace_leases
            SET claim_owner = ?,
                claim_token_hash = ?,
                last_claimed_at = ?,
                fencing_token = ?,
                expires_at = ?,
                updated_at = ?
            WHERE id = ?
              AND state = 'active'
              AND fencing_token = ?
              AND expires_at = ?
            """,
            (
                owner,
                token_hash,
                current,
                fencing_token,
                expires_at,
                current,
                lease_id,
                before["fencing_token"],
                before["expires_at"],
            ),
        )
        if updated.rowcount != 1:
            raise _error(
                "trusted_agent_lease_claim_conflict",
                "Trusted-agent lease changed concurrently.",
                retryable=True,
            )
        row = _exact_lease_row(
            database,
            lease_id=lease_id,
            scope=scope,
        )
        _record_operation(
            database,
            scope=scope,
            lease_row=row,
            operation_kind="claim_or_renew",
            idempotency_key_hash=key_hash,
            request_hash=request_hash,
            now=current,
        )
        return _snapshot(row)


def fence_trusted_agent_lease(
    database: sqlite3.Connection,
    *,
    lease_id: str,
    scope: TrustedAgentLeaseScope,
    claim_owner: str,
    claim_token: str,
    fencing_token: int,
    now: int | None = None,
) -> TrustedAgentLeaseSnapshot:
    """Verify the live scope and exact worker-held capability without writes."""

    _validate_scope(scope)
    owner = _claim_owner(claim_owner)
    token_hash = _claim_token_hash(claim_token)
    current = _now(now)
    if (
        isinstance(fencing_token, bool)
        or not isinstance(fencing_token, int)
        or fencing_token < 1
    ):
        raise ValueError("fencing_token is invalid")
    with transaction(database, immediate=True):
        row = _exact_lease_row(
            database,
            lease_id=lease_id,
            scope=scope,
        )
        if (
            str(row["state"]) != "active"
            or int(row["fencing_token"]) != fencing_token
            or not _claim_matches(
                row,
                claim_owner=owner,
                claim_token_hash=token_hash,
            )
        ):
            raise _error(
                "trusted_agent_lease_fenced",
                "Trusted-agent lease claim was superseded or revoked.",
            )
        if int(row["expires_at"]) <= current:
            raise _error(
                "trusted_agent_lease_expired",
                "Trusted-agent lease claim expired.",
                retryable=True,
            )
        _validate_live_scope(database, scope)
        return _snapshot(row)


def terminalize_trusted_agent_lease(
    database: sqlite3.Connection,
    *,
    lease_id: str,
    scope: TrustedAgentLeaseScope,
    claim_owner: str,
    claim_token: str,
    fencing_token: int,
    terminal_state: TerminalState,
    reason: str,
    idempotency_key: str,
    now: int | None = None,
) -> TrustedAgentLeaseSnapshot:
    """Make a claimed lease terminal under its exact current fence."""

    _validate_scope(scope)
    owner = _claim_owner(claim_owner)
    token_hash = _claim_token_hash(claim_token)
    current = _now(now)
    reason_code = _reason(reason)
    if terminal_state not in {"released", "expired"}:
        raise ValueError("terminal_state is invalid")
    if (
        isinstance(fencing_token, bool)
        or not isinstance(fencing_token, int)
        or fencing_token < 1
    ):
        raise ValueError("fencing_token is invalid")
    key_hash = _idempotency_hash(idempotency_key)
    request_hash = _request_hash(
        "terminalize",
        {
            **_scope_payload(scope),
            "leaseId": lease_id,
            "claimOwner": owner,
            "claimTokenHash": token_hash,
            "fencingToken": fencing_token,
            "terminalState": terminal_state,
            "reason": reason_code,
        },
    )
    with transaction(database, immediate=True):
        replay = _operation_row(
            database,
            scope=scope,
            operation_kind="terminalize",
            idempotency_key_hash=key_hash,
            request_hash=request_hash,
        )
        if replay is not None:
            row = _replay_lease_row(
                database,
                operation_row=replay,
                scope=scope,
            )
            if (
                str(row["state"]) != terminal_state
                or int(row["fencing_token"]) != fencing_token
            ):
                raise _error(
                    "trusted_agent_lease_fenced",
                    "Trusted-agent lease terminalization was superseded.",
                )
            return _snapshot(row)
        row = _exact_lease_row(
            database,
            lease_id=lease_id,
            scope=scope,
        )
        if str(row["state"]) != "active":
            raise _error(
                "trusted_agent_lease_terminal",
                "Trusted-agent lease is already terminal.",
            )
        if (
            int(row["fencing_token"]) != fencing_token
            or not _claim_matches(
                row,
                claim_owner=owner,
                claim_token_hash=token_hash,
            )
        ):
            raise _error(
                "trusted_agent_lease_fenced",
                "Trusted-agent lease claim was superseded.",
            )
        if terminal_state == "released":
            if int(row["expires_at"]) <= current:
                raise _error(
                    "trusted_agent_lease_expired",
                    "Trusted-agent lease claim expired.",
                    retryable=True,
                )
            _validate_live_scope(database, scope)
        elif int(row["expires_at"]) > current:
            raise _error(
                "trusted_agent_lease_not_expired",
                "Trusted-agent lease has not expired.",
            )
        updated = database.execute(
            """
            UPDATE trusted_agent_workspace_leases
            SET state = ?,
                updated_at = ?,
                terminal_at = ?,
                terminal_reason = ?
            WHERE id = ?
              AND state = 'active'
              AND fencing_token = ?
              AND claim_owner = ?
              AND claim_token_hash = ?
            """,
            (
                terminal_state,
                current,
                current,
                reason_code,
                lease_id,
                fencing_token,
                owner,
                token_hash,
            ),
        )
        if updated.rowcount != 1:
            raise _error(
                "trusted_agent_lease_fenced",
                "Trusted-agent lease changed concurrently.",
            )
        terminal = _exact_lease_row(
            database,
            lease_id=lease_id,
            scope=scope,
        )
        _record_operation(
            database,
            scope=scope,
            lease_row=terminal,
            operation_kind="terminalize",
            idempotency_key_hash=key_hash,
            request_hash=request_hash,
            now=current,
        )
        return _snapshot(terminal)


def revoke_trusted_agent_lease(
    database: sqlite3.Connection,
    *,
    lease_id: str,
    scope: TrustedAgentLeaseScope,
    reason: str,
    idempotency_key: str,
    now: int | None = None,
) -> TrustedAgentLeaseSnapshot:
    """Revoke an exact frozen lease even when its live parent epoch changed."""

    _validate_scope(scope)
    current = _now(now)
    reason_code = _reason(reason)
    key_hash = _idempotency_hash(idempotency_key)
    request_hash = _request_hash(
        "revoke",
        {
            **_scope_payload(scope),
            "leaseId": lease_id,
            "reason": reason_code,
        },
    )
    with transaction(database, immediate=True):
        replay = _operation_row(
            database,
            scope=scope,
            operation_kind="revoke",
            idempotency_key_hash=key_hash,
            request_hash=request_hash,
        )
        if replay is not None:
            row = _replay_lease_row(
                database,
                operation_row=replay,
                scope=scope,
            )
            if str(row["state"]) != "revoked":
                raise _error(
                    "trusted_agent_lease_terminal",
                    "Trusted-agent lease ended in another state.",
                )
            return _snapshot(row)
        row = _exact_lease_row(
            database,
            lease_id=lease_id,
            scope=scope,
        )
        if str(row["state"]) != "active":
            raise _error(
                "trusted_agent_lease_terminal",
                "Trusted-agent lease is already terminal.",
            )
        updated = database.execute(
            """
            UPDATE trusted_agent_workspace_leases
            SET state = 'revoked',
                updated_at = ?,
                terminal_at = ?,
                terminal_reason = ?
            WHERE id = ?
              AND state = 'active'
              AND fencing_token = ?
            """,
            (
                current,
                current,
                reason_code,
                lease_id,
                row["fencing_token"],
            ),
        )
        if updated.rowcount != 1:
            raise _error(
                "trusted_agent_lease_fenced",
                "Trusted-agent lease changed concurrently.",
            )
        revoked = _exact_lease_row(
            database,
            lease_id=lease_id,
            scope=scope,
        )
        _record_operation(
            database,
            scope=scope,
            lease_row=revoked,
            operation_kind="revoke",
            idempotency_key_hash=key_hash,
            request_hash=request_hash,
            now=current,
        )
        return _snapshot(revoked)


__all__ = [
    "TrustedAgentLeaseError",
    "TrustedAgentLeaseScope",
    "TrustedAgentLeaseSnapshot",
    "claim_or_renew_trusted_agent_lease",
    "fence_trusted_agent_lease",
    "issue_trusted_agent_lease",
    "revoke_trusted_agent_lease",
    "terminalize_trusted_agent_lease",
]
