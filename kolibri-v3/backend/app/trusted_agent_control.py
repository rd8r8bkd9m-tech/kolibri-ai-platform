"""Owner-only durable authority for the R1 trusted developer agent.

This module owns control-plane mutations.  Product Chat and runtime boundaries
consume the records through ``trusted_agent_execution`` without duplicating
their lifecycle rules here.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import Annotated, Any, Literal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .database import get_database, transaction
from .identity import require_owner
from .platform_authority import (
    PlatformDeveloperAuthorityError,
    require_persisted_platform_developer_authority,
)
from .schemas import UserSession
from .security import require_mutation_auth
from .trusted_agent_contracts import (
    RevisionRevoke,
    TrustedAgentAuditPage,
    TrustedAgentProfileCreate,
    TrustedAgentProfilePage,
    TrustedAgentProfilePatch,
    TrustedAgentProfileView,
    WorkspaceBindingCreate,
    WorkspaceBindingPage,
    WorkspaceBindingPatch,
    WorkspaceBindingView,
)


router = APIRouter(
    prefix="/v1/platform-admin/trusted-agents",
    tags=["platform-admin", "trusted-agents"],
)
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
OwnerDependency = Annotated[UserSession, Depends(require_owner)]
MutationAuthDependency = Annotated[None, Depends(require_mutation_auth)]
PageLimit = Annotated[int, Query(ge=1, le=100)]

_BINDING_ID = re.compile(r"^wsb_[0-9a-f]{32}$")
_PROFILE_ID = re.compile(r"^tap_[0-9a-f]{32}$")
_AUDIT_CURSOR = re.compile(
    r"^(0|[1-9][0-9]{0,19}):(taudit_[0-9a-f]{32})$"
)
_DURABLE_AUTHORITY_REAUTH_SECONDS = 300
_REQUIRED_MUTATION_CAPABILITIES = frozenset(
    {"platform.policy.write", "chat.developer.request"}
)


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _require_recent_durable_authority(actor: UserSession) -> None:
    if not _REQUIRED_MUTATION_CAPABILITIES.issubset(
        actor.platform_capabilities
    ):
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "trusted_agent_authority_required",
            "Trusted-agent authority is required.",
        )
    if (
        not actor.session_id
        or actor.authenticated_at
        < int(time.time()) - _DURABLE_AUTHORITY_REAUTH_SECONDS
    ):
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "trusted_agent_reauthentication_required",
            "Sign in again before changing trusted-agent authority.",
        )


def _persisted_authority_epoch(
    database: sqlite3.Connection,
    *,
    actor: UserSession,
) -> int:
    expected_epoch = actor.platform_authority_epoch
    if expected_epoch is None:
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "trusted_agent_authority_required",
            "Trusted-agent authority is required.",
        )
    try:
        return require_persisted_platform_developer_authority(
            database,
            user_id=actor.user_id,
            tenant_id=actor.tenant_id,
            expected_epoch=expected_epoch,
        )
    except PlatformDeveloperAuthorityError as exc:
        raise _error(
            status.HTTP_409_CONFLICT,
            "trusted_agent_authority_changed",
            "Platform authority changed; reload and try again.",
        ) from exc


def _binding_projection(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "serverRef": str(row["server_ref"]),
        "environment": str(row["environment"]),
        "fingerprintToken": str(row["fingerprint_token"]),
        "authorityEpoch": int(row["authority_epoch"]),
        "lifecycleStatus": str(row["lifecycle_status"]),
        "workspaceEpoch": int(row["workspace_epoch"]),
        "revision": int(row["revision"]),
        "createdAt": int(row["created_at"]),
        "updatedAt": int(row["updated_at"]),
        "revokedAt": (
            None if row["revoked_at"] is None else int(row["revoked_at"])
        ),
    }


def _binding_audit_projection(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "serverRef": str(row["server_ref"]),
        "environment": str(row["environment"]),
        "fingerprintConfigured": True,
        "authorityEpoch": int(row["authority_epoch"]),
        "lifecycleStatus": str(row["lifecycle_status"]),
        "workspaceEpoch": int(row["workspace_epoch"]),
        "revision": int(row["revision"]),
    }


def _capabilities(raw: object) -> list[Literal["developer.runtime.execute"]]:
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("trusted-agent capabilities are invalid") from exc
    if value != ["developer.runtime.execute"]:
        raise RuntimeError("trusted-agent capabilities are invalid")
    return ["developer.runtime.execute"]


def _profile_projection(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "workspaceBindingId": str(row["workspace_binding_id"]),
        "workspaceBindingEpoch": int(row["workspace_binding_epoch"]),
        "displayName": str(row["display_name"]),
        "runtimeProfile": str(row["runtime_profile"]),
        "agentCardId": str(row["agent_card_id"]),
        "agentCardVersion": int(row["agent_card_version"]),
        "capabilities": _capabilities(row["capabilities_json"]),
        "toolPolicyId": str(row["tool_policy_id"]),
        "accessMode": str(row["access_mode"]),
        "sandboxProfile": str(row["sandbox_profile"]),
        "approvalPolicy": str(row["approval_policy"]),
        "approvalsReviewer": row["approvals_reviewer"],
        "maxConcurrency": int(row["max_concurrency"]),
        "authorityEpoch": int(row["authority_epoch"]),
        "lifecycleStatus": str(row["lifecycle_status"]),
        "profileEpoch": int(row["profile_epoch"]),
        "revision": int(row["revision"]),
        "createdAt": int(row["created_at"]),
        "updatedAt": int(row["updated_at"]),
        "revokedAt": (
            None if row["revoked_at"] is None else int(row["revoked_at"])
        ),
    }


def _profile_audit_projection(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "workspaceBindingId": str(row["workspace_binding_id"]),
        "workspaceBindingEpoch": int(row["workspace_binding_epoch"]),
        "runtimeProfile": str(row["runtime_profile"]),
        "agentCardId": str(row["agent_card_id"]),
        "agentCardVersion": int(row["agent_card_version"]),
        "toolPolicyId": str(row["tool_policy_id"]),
        "accessMode": str(row["access_mode"]),
        "sandboxProfile": str(row["sandbox_profile"]),
        "approvalPolicy": str(row["approval_policy"]),
        "maxConcurrency": int(row["max_concurrency"]),
        "authorityEpoch": int(row["authority_epoch"]),
        "lifecycleStatus": str(row["lifecycle_status"]),
        "profileEpoch": int(row["profile_epoch"]),
        "revision": int(row["revision"]),
    }


def _binding_row(
    database: sqlite3.Connection,
    *,
    actor: UserSession,
    binding_id: str,
) -> sqlite3.Row | None:
    return database.execute(
        """
        SELECT *
        FROM trusted_agent_workspace_bindings
        WHERE id = ?
          AND authority_id = 'platform_owner'
          AND owner_user_id = ?
          AND owner_tenant_id = ?
        LIMIT 1
        """,
        (binding_id, actor.user_id, actor.tenant_id),
    ).fetchone()


def _profile_row(
    database: sqlite3.Connection,
    *,
    actor: UserSession,
    profile_id: str,
) -> sqlite3.Row | None:
    return database.execute(
        """
        SELECT *
        FROM trusted_agent_profiles
        WHERE id = ?
          AND authority_id = 'platform_owner'
          AND owner_user_id = ?
          AND owner_tenant_id = ?
        LIMIT 1
        """,
        (profile_id, actor.user_id, actor.tenant_id),
    ).fetchone()


def _require_binding(
    database: sqlite3.Connection,
    *,
    actor: UserSession,
    binding_id: str,
) -> sqlite3.Row:
    row = _binding_row(
        database,
        actor=actor,
        binding_id=binding_id,
    )
    if row is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "trusted_agent_binding_not_found",
            "Workspace binding was not found.",
        )
    return row


def _require_profile(
    database: sqlite3.Connection,
    *,
    actor: UserSession,
    profile_id: str,
) -> sqlite3.Row:
    row = _profile_row(
        database,
        actor=actor,
        profile_id=profile_id,
    )
    if row is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "trusted_agent_profile_not_found",
            "Trusted-agent profile was not found.",
        )
    return row


def _record_audit(
    database: sqlite3.Connection,
    *,
    actor: UserSession,
    authority_epoch: int,
    decision_id: str,
    action: Literal[
        "binding.created",
        "binding.updated",
        "binding.revoked",
        "profile.created",
        "profile.updated",
        "profile.revoked",
        "profile.revoked_by_binding",
    ],
    target_type: Literal["binding", "profile"],
    target_id: str,
    target_revision: int,
    target_epoch: int,
    before: object,
    after: object,
) -> None:
    database.execute(
        """
        INSERT INTO trusted_agent_audit_events (
            id,
            actor_user_id,
            actor_tenant_id,
            authority_epoch,
            authorization_decision_id,
            action,
            target_type,
            target_id,
            target_revision,
            target_epoch,
            before_json,
            after_json,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, unixepoch())
        """,
        (
            f"taudit_{uuid.uuid4().hex}",
            actor.user_id,
            actor.tenant_id,
            authority_epoch,
            decision_id,
            action,
            target_type,
            target_id,
            target_revision,
            target_epoch,
            _canonical_json(before),
            _canonical_json(after),
        ),
    )


def _revoke_active_leases(
    database: sqlite3.Connection,
    *,
    actor: UserSession,
    profile_id: str | None = None,
    binding_id: str | None = None,
) -> int:
    if profile_id is None and binding_id is None:
        raise RuntimeError("a trusted-agent lease scope is required")
    clauses = [
        "owner_user_id = ?",
        "owner_tenant_id = ?",
        "state = 'active'",
    ]
    parameters: list[object] = [actor.user_id, actor.tenant_id]
    if profile_id is not None:
        clauses.append("profile_id = ?")
        parameters.append(profile_id)
    if binding_id is not None:
        clauses.append("workspace_binding_id = ?")
        parameters.append(binding_id)
    return int(
        database.execute(
            f"""
            UPDATE trusted_agent_workspace_leases
            SET state = 'revoked',
                updated_at = unixepoch(),
                terminal_at = unixepoch(),
                terminal_reason = 'authority_changed'
            WHERE {" AND ".join(clauses)}
            """,
            parameters,
        ).rowcount
    )


def _revoke_profiles_for_binding(
    database: sqlite3.Connection,
    *,
    actor: UserSession,
    binding_id: str,
    authority_epoch: int,
    decision_id: str,
) -> None:
    rows = database.execute(
        """
        SELECT *
        FROM trusted_agent_profiles
        WHERE workspace_binding_id = ?
          AND owner_user_id = ?
          AND owner_tenant_id = ?
          AND lifecycle_status = 'active'
        ORDER BY id
        """,
        (binding_id, actor.user_id, actor.tenant_id),
    ).fetchall()
    for before in rows:
        _revoke_active_leases(
            database,
            actor=actor,
            profile_id=str(before["id"]),
            binding_id=binding_id,
        )
        updated = database.execute(
            """
            UPDATE trusted_agent_profiles
            SET authority_epoch = ?,
                lifecycle_status = 'revoked',
                profile_epoch = profile_epoch + 1,
                revision = revision + 1,
                updated_at = unixepoch(),
                revoked_at = unixepoch(),
                revoked_by_user_id = ?
            WHERE id = ?
              AND owner_user_id = ?
              AND owner_tenant_id = ?
              AND lifecycle_status = 'active'
              AND revision = ?
            """,
            (
                authority_epoch,
                actor.user_id,
                before["id"],
                actor.user_id,
                actor.tenant_id,
                before["revision"],
            ),
        )
        if updated.rowcount != 1:
            raise _error(
                status.HTTP_409_CONFLICT,
                "revision_conflict",
                "Trusted-agent authority changed; reload and try again.",
            )
        after = _require_profile(
            database,
            actor=actor,
            profile_id=str(before["id"]),
        )
        _record_audit(
            database,
            actor=actor,
            authority_epoch=authority_epoch,
            decision_id=decision_id,
            action="profile.revoked_by_binding",
            target_type="profile",
            target_id=str(after["id"]),
            target_revision=int(after["revision"]),
            target_epoch=int(after["profile_epoch"]),
            before=_profile_audit_projection(before),
            after=_profile_audit_projection(after),
        )


def _validate_binding_id(binding_id: str) -> None:
    if _BINDING_ID.fullmatch(binding_id) is None:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_trusted_agent_binding_id",
            "Workspace binding ID is invalid.",
        )


def _validate_profile_id(profile_id: str) -> None:
    if _PROFILE_ID.fullmatch(profile_id) is None:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_trusted_agent_profile_id",
            "Trusted-agent profile ID is invalid.",
        )


@router.get(
    "/workspace-bindings",
    response_model=WorkspaceBindingPage,
)
def list_workspace_bindings(
    actor: OwnerDependency,
    database: DatabaseDependency,
    limit: PageLimit = 50,
    cursor: str | None = Query(default=None, max_length=36),
) -> dict[str, Any]:
    if cursor is not None and _BINDING_ID.fullmatch(cursor) is None:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_cursor",
            "Cursor is invalid.",
        )
    rows = database.execute(
        """
        SELECT *
        FROM trusted_agent_workspace_bindings
        WHERE owner_user_id = ?
          AND owner_tenant_id = ?
          AND (? IS NULL OR id > ?)
        ORDER BY id
        LIMIT ?
        """,
        (actor.user_id, actor.tenant_id, cursor, cursor, limit + 1),
    ).fetchall()
    page = rows[:limit]
    return {
        "items": [_binding_projection(row) for row in page],
        "nextCursor": (
            str(page[-1]["id"]) if len(rows) > limit and page else None
        ),
    }


@router.post(
    "/workspace-bindings",
    response_model=WorkspaceBindingView,
    status_code=status.HTTP_201_CREATED,
)
def create_workspace_binding(
    payload: WorkspaceBindingCreate,
    actor: OwnerDependency,
    database: DatabaseDependency,
    _mutation_auth: MutationAuthDependency,
) -> dict[str, Any]:
    _require_recent_durable_authority(actor)
    binding_id = f"wsb_{uuid.uuid4().hex}"
    server_ref = f"wsref_{uuid.uuid4().hex}"
    decision_id = f"decision_{uuid.uuid4().hex}"
    with transaction(database, immediate=True):
        authority_epoch = _persisted_authority_epoch(database, actor=actor)
        existing = database.execute(
            """
            SELECT id
            FROM trusted_agent_workspace_bindings
            WHERE authority_id = 'platform_owner'
              AND lifecycle_status = 'active'
            LIMIT 1
            """
        ).fetchone()
        if existing is not None:
            raise _error(
                status.HTTP_409_CONFLICT,
                "trusted_agent_active_workspace_exists",
                "R1 already has an active workspace binding.",
            )
        database.execute(
            """
            INSERT INTO trusted_agent_workspace_bindings (
                id,
                authority_id,
                owner_user_id,
                owner_tenant_id,
                authority_epoch,
                server_ref,
                environment,
                fingerprint_token,
                lifecycle_status,
                workspace_epoch,
                revision,
                created_at,
                updated_at,
                created_by_user_id
            ) VALUES (
                ?, 'platform_owner', ?, ?, ?, ?, ?, ?, 'active',
                1, 1, unixepoch(), unixepoch(), ?
            )
            """,
            (
                binding_id,
                actor.user_id,
                actor.tenant_id,
                authority_epoch,
                server_ref,
                payload.environment,
                payload.fingerprint_token,
                actor.user_id,
            ),
        )
        row = _require_binding(
            database,
            actor=actor,
            binding_id=binding_id,
        )
        _record_audit(
            database,
            actor=actor,
            authority_epoch=authority_epoch,
            decision_id=decision_id,
            action="binding.created",
            target_type="binding",
            target_id=binding_id,
            target_revision=int(row["revision"]),
            target_epoch=int(row["workspace_epoch"]),
            before={},
            after=_binding_audit_projection(row),
        )
    return _binding_projection(row)


@router.patch(
    "/workspace-bindings/{binding_id}",
    response_model=WorkspaceBindingView,
)
def update_workspace_binding(
    binding_id: str,
    payload: WorkspaceBindingPatch,
    actor: OwnerDependency,
    database: DatabaseDependency,
    _mutation_auth: MutationAuthDependency,
) -> dict[str, Any]:
    _validate_binding_id(binding_id)
    _require_recent_durable_authority(actor)
    decision_id = f"decision_{uuid.uuid4().hex}"
    with transaction(database, immediate=True):
        authority_epoch = _persisted_authority_epoch(database, actor=actor)
        before = _require_binding(
            database,
            actor=actor,
            binding_id=binding_id,
        )
        if (
            str(before["lifecycle_status"]) != "active"
            or int(before["revision"]) != payload.revision
        ):
            raise _error(
                status.HTTP_409_CONFLICT,
                "revision_conflict",
                "Workspace binding changed; reload and try again.",
            )
        _revoke_profiles_for_binding(
            database,
            actor=actor,
            binding_id=binding_id,
            authority_epoch=authority_epoch,
            decision_id=decision_id,
        )
        _revoke_active_leases(
            database,
            actor=actor,
            binding_id=binding_id,
        )
        updated = database.execute(
            """
            UPDATE trusted_agent_workspace_bindings
            SET authority_epoch = ?,
                environment = ?,
                fingerprint_token = ?,
                workspace_epoch = workspace_epoch + 1,
                revision = revision + 1,
                updated_at = unixepoch()
            WHERE id = ?
              AND owner_user_id = ?
              AND owner_tenant_id = ?
              AND lifecycle_status = 'active'
              AND revision = ?
            """,
            (
                authority_epoch,
                (
                    payload.environment
                    if payload.environment is not None
                    else before["environment"]
                ),
                (
                    payload.fingerprint_token
                    if payload.fingerprint_token is not None
                    else before["fingerprint_token"]
                ),
                binding_id,
                actor.user_id,
                actor.tenant_id,
                payload.revision,
            ),
        )
        if updated.rowcount != 1:
            raise _error(
                status.HTTP_409_CONFLICT,
                "revision_conflict",
                "Workspace binding changed; reload and try again.",
            )
        after = _require_binding(
            database,
            actor=actor,
            binding_id=binding_id,
        )
        _record_audit(
            database,
            actor=actor,
            authority_epoch=authority_epoch,
            decision_id=decision_id,
            action="binding.updated",
            target_type="binding",
            target_id=binding_id,
            target_revision=int(after["revision"]),
            target_epoch=int(after["workspace_epoch"]),
            before=_binding_audit_projection(before),
            after=_binding_audit_projection(after),
        )
    return _binding_projection(after)


@router.post(
    "/workspace-bindings/{binding_id}/revoke",
    response_model=WorkspaceBindingView,
)
def revoke_workspace_binding(
    binding_id: str,
    payload: RevisionRevoke,
    actor: OwnerDependency,
    database: DatabaseDependency,
    _mutation_auth: MutationAuthDependency,
) -> dict[str, Any]:
    _validate_binding_id(binding_id)
    _require_recent_durable_authority(actor)
    decision_id = f"decision_{uuid.uuid4().hex}"
    with transaction(database, immediate=True):
        authority_epoch = _persisted_authority_epoch(database, actor=actor)
        before = _require_binding(
            database,
            actor=actor,
            binding_id=binding_id,
        )
        if (
            str(before["lifecycle_status"]) != "active"
            or int(before["revision"]) != payload.revision
        ):
            raise _error(
                status.HTTP_409_CONFLICT,
                "revision_conflict",
                "Workspace binding changed; reload and try again.",
            )
        _revoke_profiles_for_binding(
            database,
            actor=actor,
            binding_id=binding_id,
            authority_epoch=authority_epoch,
            decision_id=decision_id,
        )
        _revoke_active_leases(
            database,
            actor=actor,
            binding_id=binding_id,
        )
        updated = database.execute(
            """
            UPDATE trusted_agent_workspace_bindings
            SET authority_epoch = ?,
                lifecycle_status = 'revoked',
                workspace_epoch = workspace_epoch + 1,
                revision = revision + 1,
                updated_at = unixepoch(),
                revoked_at = unixepoch(),
                revoked_by_user_id = ?
            WHERE id = ?
              AND owner_user_id = ?
              AND owner_tenant_id = ?
              AND lifecycle_status = 'active'
              AND revision = ?
            """,
            (
                authority_epoch,
                actor.user_id,
                binding_id,
                actor.user_id,
                actor.tenant_id,
                payload.revision,
            ),
        )
        if updated.rowcount != 1:
            raise _error(
                status.HTTP_409_CONFLICT,
                "revision_conflict",
                "Workspace binding changed; reload and try again.",
            )
        after = _require_binding(
            database,
            actor=actor,
            binding_id=binding_id,
        )
        _record_audit(
            database,
            actor=actor,
            authority_epoch=authority_epoch,
            decision_id=decision_id,
            action="binding.revoked",
            target_type="binding",
            target_id=binding_id,
            target_revision=int(after["revision"]),
            target_epoch=int(after["workspace_epoch"]),
            before=_binding_audit_projection(before),
            after=_binding_audit_projection(after),
        )
    return _binding_projection(after)


@router.get(
    "/profiles",
    response_model=TrustedAgentProfilePage,
)
def list_trusted_agent_profiles(
    actor: OwnerDependency,
    database: DatabaseDependency,
    limit: PageLimit = 50,
    cursor: str | None = Query(default=None, max_length=36),
) -> dict[str, Any]:
    if cursor is not None and _PROFILE_ID.fullmatch(cursor) is None:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_cursor",
            "Cursor is invalid.",
        )
    rows = database.execute(
        """
        SELECT *
        FROM trusted_agent_profiles
        WHERE owner_user_id = ?
          AND owner_tenant_id = ?
          AND (? IS NULL OR id > ?)
        ORDER BY id
        LIMIT ?
        """,
        (actor.user_id, actor.tenant_id, cursor, cursor, limit + 1),
    ).fetchall()
    page = rows[:limit]
    return {
        "items": [_profile_projection(row) for row in page],
        "nextCursor": (
            str(page[-1]["id"]) if len(rows) > limit and page else None
        ),
    }


@router.post(
    "/profiles",
    response_model=TrustedAgentProfileView,
    status_code=status.HTTP_201_CREATED,
)
def create_trusted_agent_profile(
    payload: TrustedAgentProfileCreate,
    actor: OwnerDependency,
    database: DatabaseDependency,
    _mutation_auth: MutationAuthDependency,
) -> dict[str, Any]:
    _require_recent_durable_authority(actor)
    profile_id = f"tap_{uuid.uuid4().hex}"
    decision_id = f"decision_{uuid.uuid4().hex}"
    with transaction(database, immediate=True):
        authority_epoch = _persisted_authority_epoch(database, actor=actor)
        binding = _require_binding(
            database,
            actor=actor,
            binding_id=payload.workspace_binding_id,
        )
        if str(binding["lifecycle_status"]) != "active":
            raise _error(
                status.HTTP_409_CONFLICT,
                "trusted_agent_workspace_inactive",
                "Workspace binding is not active.",
            )
        if int(binding["authority_epoch"]) != authority_epoch:
            raise _error(
                status.HTTP_409_CONFLICT,
                "trusted_agent_workspace_authority_stale",
                "Workspace authority changed; update the binding first.",
            )
        existing = database.execute(
            """
            SELECT id
            FROM trusted_agent_profiles
            WHERE authority_id = 'platform_owner'
              AND lifecycle_status = 'active'
            LIMIT 1
            """
        ).fetchone()
        if existing is not None:
            raise _error(
                status.HTTP_409_CONFLICT,
                "trusted_agent_active_profile_exists",
                "R1 already has an active trusted-agent profile.",
            )
        database.execute(
            """
            INSERT INTO trusted_agent_profiles (
                id,
                authority_id,
                owner_user_id,
                owner_tenant_id,
                authority_epoch,
                workspace_binding_id,
                workspace_binding_epoch,
                display_name,
                runtime_profile,
                agent_card_id,
                agent_card_version,
                capabilities_json,
                tool_policy_id,
                access_mode,
                sandbox_profile,
                approval_policy,
                approvals_reviewer,
                max_concurrency,
                lifecycle_status,
                profile_epoch,
                revision,
                created_at,
                updated_at,
                created_by_user_id
            ) VALUES (
                ?, 'platform_owner', ?, ?, ?, ?, ?, ?, ?, ?, ?,
                '["developer.runtime.execute"]',
                'developer.full.v1',
                'full',
                'danger-full-access',
                'never',
                NULL,
                1,
                'active',
                1,
                1,
                unixepoch(),
                unixepoch(),
                ?
            )
            """,
            (
                profile_id,
                actor.user_id,
                actor.tenant_id,
                authority_epoch,
                payload.workspace_binding_id,
                binding["workspace_epoch"],
                payload.display_name,
                payload.runtime_profile,
                payload.agent_card_id,
                payload.agent_card_version,
                actor.user_id,
            ),
        )
        row = _require_profile(
            database,
            actor=actor,
            profile_id=profile_id,
        )
        _record_audit(
            database,
            actor=actor,
            authority_epoch=authority_epoch,
            decision_id=decision_id,
            action="profile.created",
            target_type="profile",
            target_id=profile_id,
            target_revision=int(row["revision"]),
            target_epoch=int(row["profile_epoch"]),
            before={},
            after=_profile_audit_projection(row),
        )
    return _profile_projection(row)


@router.patch(
    "/profiles/{profile_id}",
    response_model=TrustedAgentProfileView,
)
def update_trusted_agent_profile(
    profile_id: str,
    payload: TrustedAgentProfilePatch,
    actor: OwnerDependency,
    database: DatabaseDependency,
    _mutation_auth: MutationAuthDependency,
) -> dict[str, Any]:
    _validate_profile_id(profile_id)
    _require_recent_durable_authority(actor)
    decision_id = f"decision_{uuid.uuid4().hex}"
    with transaction(database, immediate=True):
        authority_epoch = _persisted_authority_epoch(database, actor=actor)
        before = _require_profile(
            database,
            actor=actor,
            profile_id=profile_id,
        )
        if (
            str(before["lifecycle_status"]) != "active"
            or int(before["revision"]) != payload.revision
        ):
            raise _error(
                status.HTTP_409_CONFLICT,
                "revision_conflict",
                "Trusted-agent profile changed; reload and try again.",
            )
        binding = _require_binding(
            database,
            actor=actor,
            binding_id=str(before["workspace_binding_id"]),
        )
        if (
            str(binding["lifecycle_status"]) != "active"
            or int(binding["authority_epoch"]) != authority_epoch
            or int(binding["workspace_epoch"])
            != int(before["workspace_binding_epoch"])
        ):
            raise _error(
                status.HTTP_409_CONFLICT,
                "trusted_agent_workspace_authority_stale",
                "Workspace authority changed; replace the profile.",
            )
        _revoke_active_leases(
            database,
            actor=actor,
            profile_id=profile_id,
        )
        updated = database.execute(
            """
            UPDATE trusted_agent_profiles
            SET authority_epoch = ?,
                display_name = ?,
                runtime_profile = ?,
                agent_card_id = ?,
                agent_card_version = ?,
                profile_epoch = profile_epoch + 1,
                revision = revision + 1,
                updated_at = unixepoch()
            WHERE id = ?
              AND owner_user_id = ?
              AND owner_tenant_id = ?
              AND lifecycle_status = 'active'
              AND revision = ?
            """,
            (
                authority_epoch,
                (
                    payload.display_name
                    if payload.display_name is not None
                    else before["display_name"]
                ),
                (
                    payload.runtime_profile
                    if payload.runtime_profile is not None
                    else before["runtime_profile"]
                ),
                (
                    payload.agent_card_id
                    if payload.agent_card_id is not None
                    else before["agent_card_id"]
                ),
                (
                    payload.agent_card_version
                    if payload.agent_card_version is not None
                    else before["agent_card_version"]
                ),
                profile_id,
                actor.user_id,
                actor.tenant_id,
                payload.revision,
            ),
        )
        if updated.rowcount != 1:
            raise _error(
                status.HTTP_409_CONFLICT,
                "revision_conflict",
                "Trusted-agent profile changed; reload and try again.",
            )
        after = _require_profile(
            database,
            actor=actor,
            profile_id=profile_id,
        )
        _record_audit(
            database,
            actor=actor,
            authority_epoch=authority_epoch,
            decision_id=decision_id,
            action="profile.updated",
            target_type="profile",
            target_id=profile_id,
            target_revision=int(after["revision"]),
            target_epoch=int(after["profile_epoch"]),
            before=_profile_audit_projection(before),
            after=_profile_audit_projection(after),
        )
    return _profile_projection(after)


@router.post(
    "/profiles/{profile_id}/revoke",
    response_model=TrustedAgentProfileView,
)
def revoke_trusted_agent_profile(
    profile_id: str,
    payload: RevisionRevoke,
    actor: OwnerDependency,
    database: DatabaseDependency,
    _mutation_auth: MutationAuthDependency,
) -> dict[str, Any]:
    _validate_profile_id(profile_id)
    _require_recent_durable_authority(actor)
    decision_id = f"decision_{uuid.uuid4().hex}"
    with transaction(database, immediate=True):
        authority_epoch = _persisted_authority_epoch(database, actor=actor)
        before = _require_profile(
            database,
            actor=actor,
            profile_id=profile_id,
        )
        if (
            str(before["lifecycle_status"]) != "active"
            or int(before["revision"]) != payload.revision
        ):
            raise _error(
                status.HTTP_409_CONFLICT,
                "revision_conflict",
                "Trusted-agent profile changed; reload and try again.",
            )
        _revoke_active_leases(
            database,
            actor=actor,
            profile_id=profile_id,
        )
        updated = database.execute(
            """
            UPDATE trusted_agent_profiles
            SET authority_epoch = ?,
                lifecycle_status = 'revoked',
                profile_epoch = profile_epoch + 1,
                revision = revision + 1,
                updated_at = unixepoch(),
                revoked_at = unixepoch(),
                revoked_by_user_id = ?
            WHERE id = ?
              AND owner_user_id = ?
              AND owner_tenant_id = ?
              AND lifecycle_status = 'active'
              AND revision = ?
            """,
            (
                authority_epoch,
                actor.user_id,
                profile_id,
                actor.user_id,
                actor.tenant_id,
                payload.revision,
            ),
        )
        if updated.rowcount != 1:
            raise _error(
                status.HTTP_409_CONFLICT,
                "revision_conflict",
                "Trusted-agent profile changed; reload and try again.",
            )
        after = _require_profile(
            database,
            actor=actor,
            profile_id=profile_id,
        )
        _record_audit(
            database,
            actor=actor,
            authority_epoch=authority_epoch,
            decision_id=decision_id,
            action="profile.revoked",
            target_type="profile",
            target_id=profile_id,
            target_revision=int(after["revision"]),
            target_epoch=int(after["profile_epoch"]),
            before=_profile_audit_projection(before),
            after=_profile_audit_projection(after),
        )
    return _profile_projection(after)


@router.get(
    "/audit",
    response_model=TrustedAgentAuditPage,
)
def list_trusted_agent_audit(
    _actor: OwnerDependency,
    database: DatabaseDependency,
    limit: PageLimit = 50,
    cursor: str | None = Query(default=None, max_length=60),
) -> dict[str, Any]:
    cursor_created_at: int | None = None
    cursor_id: str | None = None
    if cursor is not None:
        match = _AUDIT_CURSOR.fullmatch(cursor)
        if match is None:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "invalid_cursor",
                "Cursor is invalid.",
            )
        cursor_created_at = int(match.group(1))
        cursor_id = match.group(2)
    rows = database.execute(
        """
        SELECT *
        FROM trusted_agent_audit_events
        WHERE (
            ? IS NULL
            OR created_at < ?
            OR (created_at = ? AND id < ?)
        )
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (
            cursor_created_at,
            cursor_created_at,
            cursor_created_at,
            cursor_id,
            limit + 1,
        ),
    ).fetchall()
    page = rows[:limit]
    items: list[dict[str, Any]] = []
    for row in page:
        before = json.loads(str(row["before_json"]))
        after = json.loads(str(row["after_json"]))
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise RuntimeError("trusted-agent audit projection is invalid")
        items.append(
            {
                "id": str(row["id"]),
                "action": str(row["action"]),
                "targetType": str(row["target_type"]),
                "targetId": str(row["target_id"]),
                "targetRevision": int(row["target_revision"]),
                "targetEpoch": int(row["target_epoch"]),
                "authorityEpoch": int(row["authority_epoch"]),
                "before": before,
                "after": after,
                "createdAt": int(row["created_at"]),
            }
        )
    next_cursor = (
        f"{int(page[-1]['created_at'])}:{page[-1]['id']}"
        if len(rows) > limit and page
        else None
    )
    return {"items": items, "nextCursor": next_cursor}
