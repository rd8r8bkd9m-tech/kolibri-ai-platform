"""Truthful, read-only platform view of agent task execution.

The projection deliberately excludes chat messages, prompts, command payloads,
lease credentials, filesystem paths, provider evidence, and stored secrets.
It has no mutation or execution endpoints.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import sqlite3
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from .agent_runtime import AgentRuntimeRegistry
from .database import get_database
from .identity import require_user
from .schemas import UserSession


router = APIRouter(
    prefix="/v1/platform-admin/agent-operations",
    tags=["platform-admin-agent-operations"],
)
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = Annotated[UserSession, Depends(require_user)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
TenantFilter = Annotated[
    str | None,
    Query(alias="tenantId", min_length=1, max_length=160),
]
RunStatusFilter = Annotated[
    Literal["running", "succeeded", "failed"] | None,
    Query(alias="status"),
]

_CURSOR_VERSION = 1
_MAX_CURSOR_LENGTH = 2_048
_MAX_RUNTIME_ROWS = 64
_MAX_PROVIDER_ROWS = 100
_SAFE_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")
_SAFE_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")
_SENSITIVE_PREFIXES = (
    "sk-",
    "sk_",
    "ghp_",
    "github_pat_",
    "bearer_",
    "token_",
    "secret_",
    "password_",
)


class PlatformAuditAuthorityError(RuntimeError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "platform_audit_required"
    message = "Platform audit authority is required."

    def __init__(self) -> None:
        super().__init__(self.code)


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def require_platform_audit_authority(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
) -> None:
    """Re-check the exact live singleton grant for every cross-tenant read."""

    authority_epoch = identity.platform_authority_epoch
    if (
        not identity.is_platform_owner
        or authority_epoch is None
        or "platform.audit.read" not in identity.platform_capabilities
    ):
        raise PlatformAuditAuthorityError()
    row = database.execute(
        """
        SELECT 1
        FROM platform_authority_grants AS authority
        WHERE authority.authority_id = 'platform_owner'
          AND authority.user_id = ?
          AND authority.tenant_id = ?
          AND authority.active = 1
          AND authority.authority_epoch = ?
          AND EXISTS (
              SELECT 1
              FROM json_each(authority.capabilities_json)
              WHERE value = 'platform.audit.read'
          )
        LIMIT 1
        """,
        (identity.user_id, identity.tenant_id, authority_epoch),
    ).fetchone()
    if row is None:
        raise PlatformAuditAuthorityError()


def _encode_cursor(row: sqlite3.Row) -> str:
    raw = json.dumps(
        [
            _CURSOR_VERSION,
            str(row["created_at"]),
            str(row["tenant_id"]),
            str(row["id"]),
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> tuple[str, str, str] | None:
    if cursor is None:
        return None
    if (
        not cursor
        or len(cursor) > _MAX_CURSOR_LENGTH
        or not cursor.isascii()
        or re.fullmatch(r"[A-Za-z0-9_-]+", cursor) is None
    ):
        raise _error(400, "invalid_cursor", "The pagination cursor is invalid.")
    try:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.b64decode(
            cursor + padding,
            altchars=b"-_",
            validate=True,
        )
        payload = json.loads(decoded.decode("ascii"))
    except (binascii.Error, UnicodeError, ValueError, TypeError) as exc:
        raise _error(
            400,
            "invalid_cursor",
            "The pagination cursor is invalid.",
        ) from exc
    if (
        not isinstance(payload, list)
        or len(payload) != 4
        or payload[0] != _CURSOR_VERSION
        or any(
            not isinstance(value, str)
            or not value
            or len(value) > 512
            or "\x00" in value
            for value in payload[1:]
        )
    ):
        raise _error(400, "invalid_cursor", "The pagination cursor is invalid.")
    return payload[1], payload[2], payload[3]


def _safe_error(value: object) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    normalized = str(value)
    if (
        _SAFE_ERROR_CODE.fullmatch(normalized)
        and not normalized.casefold().startswith(_SENSITIVE_PREFIXES)
    ):
        return normalized, False
    return None, True


def _safe_model(value: object) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    normalized = str(value)
    if (
        _SAFE_MODEL_ID.fullmatch(normalized)
        and not normalized.casefold().startswith(_SENSITIVE_PREFIXES)
    ):
        return normalized, False
    return None, True


def _run_projection(row: sqlite3.Row) -> dict[str, Any]:
    run_error, run_error_redacted = _safe_error(row["run_error_code"])
    model_id, model_id_redacted = _safe_model(row["model_id"])
    outbox_error, outbox_error_redacted = _safe_error(
        row["outbox_error_code"]
    )
    context = None
    if row["execution_mode"] is not None:
        context = {
            "executionMode": str(row["execution_mode"]),
            "executionPlane": str(row["execution_plane"]),
            "accessMode": str(row["access_mode"]),
            "accessPolicyVersion": int(row["access_policy_version"]),
            "authorityRole": str(row["authority_role"]),
            "workspaceRef": row["workspace_ref"],
            "sandboxProfile": str(row["sandbox_profile"]),
            "approvalPolicy": str(row["approval_policy"]),
            "approvalsReviewer": row["approvals_reviewer"],
            "modelId": model_id,
            "modelIdRedacted": model_id_redacted,
            "reasoningEffort": row["reasoning_effort"],
            "serviceTier": row["service_tier"],
            "platformAuthorityEpoch": row["platform_authority_epoch"],
            "trustedAgentProfileId": row["trusted_agent_profile_id"],
            "trustedAgentProfileEpoch": row["trusted_agent_profile_epoch"],
            "trustedAgentWorkspaceBindingId": (
                row["trusted_agent_workspace_binding_id"]
            ),
            "trustedAgentWorkspaceBindingEpoch": (
                row["trusted_agent_workspace_binding_epoch"]
            ),
            "frozenAt": str(row["context_created_at"]),
        }
    dispatch = None
    if row["outbox_state"] is not None:
        dispatch = {
            "commandKind": str(row["command_kind"]),
            "phase": str(row["outbox_phase"]),
            "state": str(row["outbox_state"]),
            "attempts": int(row["outbox_attempts"]),
            "maxAttempts": int(row["outbox_max_attempts"]),
            "availableAt": str(row["outbox_available_at"]),
            "createdAt": str(row["outbox_created_at"]),
            "updatedAt": str(row["outbox_updated_at"]),
            "completedAt": row["outbox_completed_at"],
            "lastErrorCode": outbox_error,
            "lastErrorRedacted": outbox_error_redacted,
        }
    return {
        "task": {
            "tenantId": str(row["tenant_id"]),
            "runId": str(row["id"]),
            "projectId": str(row["project_id"]),
            "threadId": str(row["thread_id"]),
        },
        "agent": {
            "selectedProfile": str(row["selected_profile"]),
        },
        "status": str(row["status"]),
        "outcome": row["outcome"],
        "lastEventSequence": int(row["last_event_sequence"]),
        "errorCode": run_error,
        "errorRedacted": run_error_redacted,
        "timestamps": {
            "heartbeatAt": str(row["heartbeat_at"]),
            "createdAt": str(row["created_at"]),
            "updatedAt": str(row["updated_at"]),
            "finishedAt": row["finished_at"],
        },
        "frozenPolicy": context,
        "dispatch": dispatch,
    }


def _provider_availability(
    database: sqlite3.Connection,
    *,
    tenant_id: str | None,
) -> tuple[list[dict[str, Any]], bool]:
    rows = database.execute(
        """
        SELECT
            tenant_id, provider_id, status, auth_flow_supported,
            authority_observed, last_verified_at, last_error_code, updated_at
        FROM provider_connections
        WHERE (? IS NULL OR tenant_id = ?)
        ORDER BY tenant_id, provider_id
        LIMIT ?
        """,
        (tenant_id, tenant_id, _MAX_PROVIDER_ROWS + 1),
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows[:_MAX_PROVIDER_ROWS]:
        error_code, error_redacted = _safe_error(row["last_error_code"])
        items.append(
            {
                "tenantId": str(row["tenant_id"]),
                "profileId": str(row["provider_id"]),
                "status": str(row["status"]),
                "authFlowSupported": bool(row["auth_flow_supported"]),
                "authorityObserved": bool(row["authority_observed"]),
                "lastVerifiedAt": row["last_verified_at"],
                "lastErrorCode": error_code,
                "lastErrorRedacted": error_redacted,
                "updatedAt": str(row["updated_at"]),
            }
        )
    return items, len(rows) > _MAX_PROVIDER_ROWS


def _runtime_availability(
    request: Request,
) -> tuple[list[dict[str, Any]], bool]:
    registry = getattr(
        getattr(request.app, "state", None),
        "agent_runtime_registry",
        None,
    )
    if not isinstance(registry, AgentRuntimeRegistry):
        return [], False
    descriptors = registry.descriptors()
    start_errors = registry.start_errors()
    items = [
        {
            "profileId": descriptor.profile_id,
            "runtimeId": descriptor.runtime_id,
            "displayName": descriptor.display_name,
            "registered": True,
            "startupStatus": (
                "start_failed"
                if descriptor.profile_id in start_errors
                else "no_error_recorded"
            ),
            "modes": sorted(descriptor.capabilities.modes),
            "streaming": descriptor.capabilities.streaming,
            "structuredOutput": descriptor.capabilities.structured_output,
            "activityEvents": descriptor.capabilities.activity_events,
            "persistentSessions": descriptor.capabilities.persistent_sessions,
            "modelCatalog": descriptor.capabilities.model_catalog,
        }
        for descriptor in descriptors[:_MAX_RUNTIME_ROWS]
    ]
    return items, len(descriptors) > _MAX_RUNTIME_ROWS


@router.get("")
def list_agent_operations(
    request: Request,
    response: Response,
    database: DatabaseDependency,
    identity: IdentityDependency,
    limit: PageLimit = 50,
    cursor: Annotated[str | None, Query(max_length=_MAX_CURSOR_LENGTH)] = None,
    tenant_id: TenantFilter = None,
    run_status: RunStatusFilter = None,
) -> dict[str, Any]:
    try:
        require_platform_audit_authority(database, identity=identity)
    except PlatformAuditAuthorityError as exc:
        raise _error(exc.status_code, exc.code, exc.message) from exc

    decoded_cursor = _decode_cursor(cursor)
    cursor_created_at = None if decoded_cursor is None else decoded_cursor[0]
    cursor_tenant_id = None if decoded_cursor is None else decoded_cursor[1]
    cursor_run_id = None if decoded_cursor is None else decoded_cursor[2]
    rows = database.execute(
        """
        SELECT
            run.tenant_id,
            run.id,
            run.project_id,
            run.thread_id,
            run.selected_profile,
            run.status,
            run.outcome,
            run.last_event_sequence,
            run.error_code AS run_error_code,
            run.heartbeat_at,
            run.created_at,
            run.updated_at,
            run.finished_at,
            context.execution_mode,
            context.execution_plane,
            context.access_mode,
            context.access_policy_version,
            context.authority_role,
            context.workspace_ref,
            context.sandbox_profile,
            context.approval_policy,
            context.approvals_reviewer,
            context.model_id,
            context.reasoning_effort,
            context.service_tier,
            context.platform_authority_epoch,
            context.trusted_agent_profile_id,
            context.trusted_agent_profile_epoch,
            context.trusted_agent_workspace_binding_id,
            context.trusted_agent_workspace_binding_epoch,
            context.created_at AS context_created_at,
            outbox.command_kind,
            outbox.phase AS outbox_phase,
            outbox.state AS outbox_state,
            outbox.attempts AS outbox_attempts,
            outbox.max_attempts AS outbox_max_attempts,
            outbox.available_at AS outbox_available_at,
            outbox.last_error_code AS outbox_error_code,
            outbox.created_at AS outbox_created_at,
            outbox.updated_at AS outbox_updated_at,
            outbox.completed_at AS outbox_completed_at
        FROM chat_runs AS run
        LEFT JOIN chat_run_execution_contexts AS context
          ON context.tenant_id = run.tenant_id
         AND context.run_id = run.id
        LEFT JOIN product_run_outbox AS outbox
          ON outbox.tenant_id = run.tenant_id
         AND outbox.run_id = run.id
        WHERE (? IS NULL OR run.tenant_id = ?)
          AND (? IS NULL OR run.status = ?)
          AND (
              ? IS NULL
              OR run.created_at < ?
              OR (
                  run.created_at = ?
                  AND run.tenant_id < ?
              )
              OR (
                  run.created_at = ?
                  AND run.tenant_id = ?
                  AND run.id < ?
              )
          )
        ORDER BY run.created_at DESC, run.tenant_id DESC, run.id DESC
        LIMIT ?
        """,
        (
            tenant_id,
            tenant_id,
            run_status,
            run_status,
            cursor_created_at,
            cursor_created_at,
            cursor_created_at,
            cursor_tenant_id,
            cursor_created_at,
            cursor_tenant_id,
            cursor_run_id,
            limit + 1,
        ),
    ).fetchall()
    page = rows[:limit]
    providers, providers_truncated = _provider_availability(
        database,
        tenant_id=tenant_id,
    )
    runtimes, runtimes_truncated = _runtime_availability(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return {
        "items": [_run_projection(row) for row in page],
        "nextCursor": (
            _encode_cursor(page[-1])
            if len(rows) > limit and page
            else None
        ),
        "availability": {
            "providers": providers,
            "providersTruncated": providers_truncated,
            "runtimes": runtimes,
            "runtimesTruncated": runtimes_truncated,
        },
    }
