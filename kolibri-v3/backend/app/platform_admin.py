"""Platform-owner control plane and persisted product access policy."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field, model_validator

from .database import get_database, transaction
from .identity import require_owner
from .platform_authority import (
    PlatformDeveloperAuthorityError,
    require_platform_developer_authority,
)
from .product_entitlements import CONSTRUCTION_ESTIMATES_ENTITLEMENT
from .schemas import APIModel, ModelId, UserSession
from .security import require_mutation_auth

router = APIRouter(prefix="/v1/platform-admin", tags=["platform-admin"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
OwnerDependency = Annotated[UserSession, Depends(require_owner)]
MutationAuthDependency = Annotated[None, Depends(require_mutation_auth)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{0,159}$")
_MODEL_POLICY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_PROVIDER_POLICY_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
_PLAN_CODE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,47}$")
_AUDIT_CURSOR = re.compile(r"^(0|[1-9][0-9]{0,19}):([A-Za-z0-9._~-]{1,160})$")


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


def _json_ids(
    raw: object,
    *,
    pattern: re.Pattern[str],
) -> frozenset[str] | None:
    if raw is None:
        return None
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("persisted platform policy is invalid") from exc
    if (
        not isinstance(value, list)
        or len(value) > 256
        or any(
            not isinstance(item, str)
            or pattern.fullmatch(item) is None
            for item in value
        )
        or len(set(value)) != len(value)
    ):
        raise RuntimeError("persisted platform policy is invalid")
    return frozenset(value)


@dataclass(frozen=True, slots=True)
class ChatAccessPolicy:
    allowed_model_ids: frozenset[str] | None
    allowed_provider_ids: frozenset[str] | None


class PlatformPolicyError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message


def enforce_identity_access(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
) -> None:
    """Fail closed for suspended tenants and blocked users.

    The one platform owner remains able to enter the control plane and repair
    policy. Product/developer access for the owner is still checked separately
    by :func:`enforce_chat_access_policy`.
    """

    if identity.is_platform_owner:
        return
    row = database.execute(
        """
        SELECT tenant.lifecycle_status, user_control.access_status
        FROM platform_tenant_policies AS tenant
        JOIN platform_user_controls AS user_control
          ON user_control.tenant_id = tenant.tenant_id
         AND user_control.user_id = ?
        WHERE tenant.tenant_id = ?
        LIMIT 1
        """,
        (identity.user_id, identity.tenant_id),
    ).fetchone()
    if row is None:
        raise PlatformPolicyError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "platform_policy_unavailable",
            "Политика доступа рабочего пространства не настроена.",
        )
    if str(row["lifecycle_status"]) != "active":
        raise PlatformPolicyError(
            status.HTTP_423_LOCKED,
            "tenant_suspended",
            "Рабочее пространство приостановлено.",
        )
    if str(row["access_status"]) != "active":
        raise PlatformPolicyError(
            status.HTTP_423_LOCKED,
            "user_blocked",
            "Доступ пользователя заблокирован.",
        )


def enforce_chat_access_policy(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    execution_mode: str,
    runtime_profile: str,
    model_id: str | None,
    enforce_run_limit: bool = True,
) -> ChatAccessPolicy:
    """Authorize one exact chat selection from persisted platform policy."""

    if execution_mode == "developer":
        try:
            require_platform_developer_authority(identity)
        except PlatformDeveloperAuthorityError as exc:
            raise PlatformPolicyError(
                exc.status_code,
                exc.code,
                exc.message,
            ) from exc

    row = database.execute(
        """
        SELECT
            tenant.lifecycle_status,
            tenant.developer_access_enabled,
            tenant.allowed_model_ids_json,
            tenant.allowed_provider_ids_json,
            user_control.access_status,
            user_control.developer_access
        FROM platform_tenant_policies AS tenant
        JOIN platform_user_controls AS user_control
          ON user_control.tenant_id = tenant.tenant_id
         AND user_control.user_id = ?
        WHERE tenant.tenant_id = ?
        LIMIT 1
        """,
        (identity.user_id, identity.tenant_id),
    ).fetchone()
    if row is None:
        raise PlatformPolicyError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "platform_policy_unavailable",
            "Политика доступа рабочего пространства не настроена.",
        )
    if str(row["lifecycle_status"]) != "active":
        raise PlatformPolicyError(
            status.HTTP_423_LOCKED,
            "tenant_suspended",
            "Рабочее пространство приостановлено.",
        )
    if str(row["access_status"]) != "active":
        raise PlatformPolicyError(
            status.HTTP_423_LOCKED,
            "user_blocked",
            "Доступ пользователя заблокирован.",
        )

    allowed_models = _json_ids(
        row["allowed_model_ids_json"],
        pattern=_MODEL_POLICY_ID,
    )
    allowed_providers = _json_ids(
        row["allowed_provider_ids_json"],
        pattern=_PROVIDER_POLICY_ID,
    )
    if (
        allowed_providers is not None
        and runtime_profile == "auto"
    ):
        raise PlatformPolicyError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "concrete_runtime_profile_required",
            (
                "Политика провайдеров требует выбрать конкретный runtime; "
                "автоматический выбор недоступен."
            ),
        )
    if (
        allowed_providers is not None
        and runtime_profile not in allowed_providers
    ):
        raise PlatformPolicyError(
            status.HTTP_403_FORBIDDEN,
            "runtime_profile_not_allowed",
            "Выбранный runtime запрещён политикой рабочего пространства.",
        )
    if allowed_models is not None:
        if model_id is None:
            raise PlatformPolicyError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "concrete_model_required",
                (
                    "Политика моделей требует выбрать конкретную модель; "
                    "runtime default недоступен."
                ),
            )
        if model_id not in allowed_models:
            raise PlatformPolicyError(
                status.HTTP_403_FORBIDDEN,
                "model_not_allowed",
                "Выбранная модель запрещена политикой рабочего пространства.",
            )
    if execution_mode == "developer":
        developer_access = str(row["developer_access"])
        if (
            not bool(row["developer_access_enabled"])
            or developer_access == "deny"
            or developer_access not in {"inherit", "allow"}
        ):
            raise PlatformPolicyError(
                status.HTTP_403_FORBIDDEN,
                "developer_access_disabled",
                "Developer-режим выключен политикой платформы.",
            )
    if not enforce_run_limit:
        return ChatAccessPolicy(
            allowed_model_ids=allowed_models,
            allowed_provider_ids=allowed_providers,
        )
    limit_row = database.execute(
        """
        SELECT monthly_run_limit
        FROM platform_tenant_policies
        WHERE tenant_id = ?
        """,
        (identity.tenant_id,),
    ).fetchone()
    monthly_limit = (
        None if limit_row is None else limit_row["monthly_run_limit"]
    )
    if monthly_limit is not None:
        month_start = database.execute(
            "SELECT strftime('%Y-%m-01T00:00:00+00:00', 'now')"
        ).fetchone()[0]
        used = int(
            database.execute(
                """
                SELECT COUNT(*)
                FROM chat_runs
                WHERE tenant_id = ? AND created_at >= ?
                """,
                (identity.tenant_id, month_start),
            ).fetchone()[0]
        )
        if used >= int(monthly_limit):
            raise PlatformPolicyError(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "monthly_run_limit_reached",
                "Месячный лимит запусков исчерпан.",
            )
    return ChatAccessPolicy(
        allowed_model_ids=allowed_models,
        allowed_provider_ids=allowed_providers,
    )


def enforce_background_execution_policy(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str | None = None,
    require_developer_access: bool = False,
) -> None:
    """Fail closed before and after a worker crosses an external boundary."""

    tenant = database.execute(
        """
        SELECT lifecycle_status, developer_access_enabled
        FROM platform_tenant_policies
        WHERE tenant_id = ?
        LIMIT 1
        """,
        (tenant_id,),
    ).fetchone()
    if tenant is None:
        raise PlatformPolicyError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "platform_policy_unavailable",
            "Политика доступа рабочего пространства не настроена.",
        )
    if str(tenant["lifecycle_status"]) != "active":
        raise PlatformPolicyError(
            status.HTTP_423_LOCKED,
            "tenant_suspended",
            "Рабочее пространство приостановлено.",
        )
    if (
        require_developer_access
        and not bool(tenant["developer_access_enabled"])
    ):
        raise PlatformPolicyError(
            status.HTTP_403_FORBIDDEN,
            "developer_access_disabled",
            "Developer-режим выключен политикой платформы.",
        )
    if user_id is None:
        return
    user = database.execute(
        """
        SELECT access_status, developer_access
        FROM platform_user_controls
        WHERE tenant_id = ? AND user_id = ?
        LIMIT 1
        """,
        (tenant_id, user_id),
    ).fetchone()
    if user is None:
        raise PlatformPolicyError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "platform_policy_unavailable",
            "Политика доступа пользователя не настроена.",
        )
    if str(user["access_status"]) != "active":
        raise PlatformPolicyError(
            status.HTTP_423_LOCKED,
            "user_blocked",
            "Доступ пользователя заблокирован.",
        )
    if (
        require_developer_access
        and str(user["developer_access"]) == "deny"
    ):
        raise PlatformPolicyError(
            status.HTTP_403_FORBIDDEN,
            "developer_access_disabled",
            "Developer-режим выключен политикой платформы.",
        )


class TenantPolicyPatch(APIModel):
    revision: Annotated[int, Field(ge=1)]
    lifecycle_status: Literal["active", "suspended"] | None = Field(
        default=None,
        alias="lifecycleStatus",
    )
    plan_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=48,
        alias="planCode",
    )
    user_limit: int | None = Field(
        default=None,
        ge=1,
        le=1_000_000,
        alias="userLimit",
    )
    monthly_run_limit: int | None = Field(
        default=None,
        ge=0,
        le=1_000_000_000,
        alias="monthlyRunLimit",
    )
    developer_access_enabled: bool | None = Field(
        default=None,
        alias="developerAccessEnabled",
    )
    allowed_model_ids: list[ModelId] | None = Field(
        default=None,
        max_length=256,
        alias="allowedModelIds",
    )
    allowed_provider_ids: list[str] | None = Field(
        default=None,
        max_length=256,
        alias="allowedProviderIds",
    )
    block_reason: str | None = Field(
        default=None,
        max_length=500,
        alias="blockReason",
    )

    @model_validator(mode="after")
    def validate_patch(self) -> "TenantPolicyPatch":
        mutable = self.model_fields_set - {"revision"}
        if not mutable:
            raise ValueError("at least one policy field is required")
        if self.plan_code is not None and _PLAN_CODE.fullmatch(self.plan_code) is None:
            raise ValueError("plan code is invalid")
        if self.allowed_model_ids is not None and len(set(self.allowed_model_ids)) != len(
            self.allowed_model_ids
        ):
            raise ValueError("model IDs must be unique")
        if self.allowed_provider_ids is not None:
            if (
                len(set(self.allowed_provider_ids))
                != len(self.allowed_provider_ids)
                or any(
                    _PROVIDER_POLICY_ID.fullmatch(item) is None
                    for item in self.allowed_provider_ids
                )
            ):
                raise ValueError("provider IDs are invalid")
        if (
            self.lifecycle_status == "suspended"
            and not (self.block_reason or "").strip()
        ):
            raise ValueError("suspension reason is required")
        return self


class UserControlPatch(APIModel):
    revision: Annotated[int, Field(ge=1)]
    access_status: Literal["active", "blocked"] | None = Field(
        default=None,
        alias="accessStatus",
    )
    developer_access: Literal["inherit", "allow", "deny"] | None = Field(
        default=None,
        alias="developerAccess",
    )
    block_reason: str | None = Field(
        default=None,
        max_length=500,
        alias="blockReason",
    )

    @model_validator(mode="after")
    def validate_patch(self) -> "UserControlPatch":
        if not (self.model_fields_set - {"revision"}):
            raise ValueError("at least one control field is required")
        if (
            self.access_status == "blocked"
            and not (self.block_reason or "").strip()
        ):
            raise ValueError("block reason is required")
        return self


class ProductEntitlementPatch(APIModel):
    expected_epoch: Annotated[
        int,
        Field(ge=0, le=2_147_483_647, alias="expectedEpoch"),
    ]
    status: Literal["active", "revoked"]


def _tenant_projection(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": str(row["name"]),
        "createdAt": int(row["created_at"]),
        "userCount": int(row["user_count"]),
        "activeSessionCount": int(row["active_session_count"]),
        "policy": {
            "lifecycleStatus": str(row["lifecycle_status"]),
            "planCode": str(row["plan_code"]),
            "userLimit": row["user_limit"],
            "monthlyRunLimit": row["monthly_run_limit"],
            "developerAccessEnabled": bool(row["developer_access_enabled"]),
            "allowedModelIds": (
                None
                if row["allowed_model_ids_json"] is None
                else sorted(
                    _json_ids(
                        row["allowed_model_ids_json"],
                        pattern=_MODEL_POLICY_ID,
                    )
                    or ()
                )
            ),
            "allowedProviderIds": (
                None
                if row["allowed_provider_ids_json"] is None
                else sorted(
                    _json_ids(
                        row["allowed_provider_ids_json"],
                        pattern=_PROVIDER_POLICY_ID,
                    )
                    or ()
                )
            ),
            "blockReason": row["block_reason"],
            "revision": int(row["revision"]),
            "updatedAt": int(row["updated_at"]),
        },
    }


def _tenant_row(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
) -> sqlite3.Row | None:
    return database.execute(
        """
        SELECT
            tenant.id,
            tenant.name,
            tenant.created_at,
            policy.lifecycle_status,
            policy.plan_code,
            policy.user_limit,
            policy.monthly_run_limit,
            policy.developer_access_enabled,
            policy.allowed_model_ids_json,
            policy.allowed_provider_ids_json,
            policy.block_reason,
            policy.revision,
            policy.updated_at,
            (
                SELECT COUNT(*)
                FROM users
                WHERE users.tenant_id = tenant.id
            ) AS user_count,
            (
                SELECT COUNT(*)
                FROM sessions
                WHERE sessions.tenant_id = tenant.id
                  AND sessions.revoked_at IS NULL
                  AND sessions.expires_at > unixepoch()
            ) + (
                SELECT COUNT(*)
                FROM mobile_device_sessions
                WHERE mobile_device_sessions.tenant_id = tenant.id
                  AND mobile_device_sessions.revoked_at IS NULL
                  AND mobile_device_sessions.expires_at > unixepoch()
            ) AS active_session_count
        FROM tenants AS tenant
        JOIN platform_tenant_policies AS policy
          ON policy.tenant_id = tenant.id
        WHERE tenant.id = ?
        LIMIT 1
        """,
        (tenant_id,),
    ).fetchone()


def _user_projection(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "tenantId": str(row["tenant_id"]),
        "email": str(row["email"]),
        "name": str(row["name"]),
        "role": str(row["role"]),
        "isPlatformOwner": bool(row["is_platform_owner"]),
        "createdAt": int(row["created_at"]),
        "updatedAt": int(row["updated_at"]),
        "activeSessionCount": int(row["active_session_count"]),
        "control": {
            "accessStatus": str(row["access_status"]),
            "developerAccess": str(row["developer_access"]),
            "blockReason": row["block_reason"],
            "revision": int(row["revision"]),
            "updatedAt": int(row["control_updated_at"]),
        },
    }


def _user_row(
    database: sqlite3.Connection,
    *,
    user_id: str,
) -> sqlite3.Row | None:
    return database.execute(
        """
        SELECT
            users.id,
            users.tenant_id,
            users.email,
            users.name,
            users.role,
            users.created_at,
            users.updated_at,
            control.access_status,
            control.developer_access,
            control.block_reason,
            control.revision,
            control.updated_at AS control_updated_at,
            EXISTS (
                SELECT 1
                FROM platform_authority_grants AS authority
                WHERE authority.authority_id = 'platform_owner'
                  AND authority.user_id = users.id
                  AND authority.tenant_id = users.tenant_id
                  AND authority.active = 1
            ) AS is_platform_owner,
            (
                SELECT COUNT(*)
                FROM sessions
                WHERE sessions.user_id = users.id
                  AND sessions.tenant_id = users.tenant_id
                  AND sessions.revoked_at IS NULL
                  AND sessions.expires_at > unixepoch()
            ) + (
                SELECT COUNT(*)
                FROM mobile_device_sessions
                WHERE mobile_device_sessions.user_id = users.id
                  AND mobile_device_sessions.tenant_id = users.tenant_id
                  AND mobile_device_sessions.revoked_at IS NULL
                  AND mobile_device_sessions.expires_at > unixepoch()
            ) AS active_session_count
        FROM users
        JOIN platform_user_controls AS control
          ON control.user_id = users.id
         AND control.tenant_id = users.tenant_id
        WHERE users.id = ?
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()


def _product_entitlement_row(
    database: sqlite3.Connection,
    *,
    user_id: str,
    entitlement_code: str,
) -> sqlite3.Row | None:
    return database.execute(
        """
        SELECT
            users.id AS user_id,
            users.tenant_id,
            grant.status,
            grant.grant_epoch,
            grant.source,
            grant.created_at,
            grant.updated_at
        FROM users
        LEFT JOIN product_entitlement_grants AS grant
          ON grant.user_id = users.id
         AND grant.tenant_id = users.tenant_id
         AND grant.entitlement_code = ?
        WHERE users.id = ?
        LIMIT 1
        """,
        (entitlement_code, user_id),
    ).fetchone()


def _product_entitlement_projection(
    row: sqlite3.Row,
    *,
    entitlement_code: str,
) -> dict[str, Any]:
    assigned = row["grant_epoch"] is not None
    return {
        "userId": str(row["user_id"]),
        "tenantId": str(row["tenant_id"]),
        "entitlement": entitlement_code,
        "status": str(row["status"]) if assigned else "unassigned",
        "grantEpoch": int(row["grant_epoch"]) if assigned else 0,
        "source": str(row["source"]) if assigned else None,
        "createdAt": int(row["created_at"]) if assigned else None,
        "updatedAt": int(row["updated_at"]) if assigned else None,
    }


def _validate_product_entitlement_code(entitlement_code: str) -> None:
    if entitlement_code != CONSTRUCTION_ESTIMATES_ENTITLEMENT:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "product_entitlement_not_found",
            "Продуктовый доступ не найден.",
        )


def _record_audit(
    database: sqlite3.Connection,
    *,
    actor: UserSession,
    action: str,
    target_type: Literal["tenant", "user", "sessions", "policy"],
    target_id: str,
    target_tenant_id: str,
    before: object,
    after: object,
) -> None:
    database.execute(
        """
        INSERT INTO platform_admin_audit_events (
            id, actor_user_id, actor_tenant_id, action, target_type,
            target_id, target_tenant_id, before_json, after_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, unixepoch())
        """,
        (
            f"audit_{uuid.uuid4().hex}",
            actor.user_id,
            actor.tenant_id,
            action,
            target_type,
            target_id,
            target_tenant_id,
            _canonical_json(before),
            _canonical_json(after),
        ),
    )


def _revoke_sessions(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str | None = None,
) -> int:
    now = database.execute("SELECT unixepoch()").fetchone()[0]
    filter_sql = " AND user_id = ?" if user_id is not None else ""
    parameters: list[object] = [now, tenant_id]
    if user_id is not None:
        parameters.append(user_id)
    revoked = database.execute(
        f"""
        UPDATE sessions
        SET revoked_at = ?
        WHERE tenant_id = ?
          {filter_sql}
          AND revoked_at IS NULL
        """,
        parameters,
    ).rowcount
    # Migration 032 is a required predecessor of this module. Revoke both
    # access and refresh credentials through their owning device session.
    device_rows = database.execute(
        f"""
        SELECT id
        FROM mobile_device_sessions
        WHERE tenant_id = ?
          {"AND user_id = ?" if user_id is not None else ""}
          AND revoked_at IS NULL
        """,
        ([tenant_id, user_id] if user_id is not None else [tenant_id]),
    ).fetchall()
    device_ids = [str(row["id"]) for row in device_rows]
    for device_id in device_ids:
        database.execute(
            """
            UPDATE mobile_device_sessions
            SET revoked_at = ?
            WHERE id = ? AND revoked_at IS NULL
            """,
            (now, device_id),
        )
        database.execute(
            """
            UPDATE mobile_access_tokens
            SET revoked_at = ?
            WHERE device_session_id = ? AND revoked_at IS NULL
            """,
            (now, device_id),
        )
        database.execute(
            """
            UPDATE mobile_refresh_tokens
            SET revoked_at = ?
            WHERE device_session_id = ? AND revoked_at IS NULL
            """,
            (now, device_id),
        )
    return int(revoked) + len(device_ids)


@router.get("/tenants")
def list_tenants(
    _owner: OwnerDependency,
    database: DatabaseDependency,
    limit: PageLimit = 50,
    cursor: str | None = Query(default=None, max_length=160),
) -> dict[str, Any]:
    if cursor is not None and _SAFE_ID.fullmatch(cursor) is None:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_cursor", "Cursor is invalid.")
    rows = database.execute(
        """
        SELECT
            tenant.id,
            tenant.name,
            tenant.created_at,
            policy.lifecycle_status,
            policy.plan_code,
            policy.user_limit,
            policy.monthly_run_limit,
            policy.developer_access_enabled,
            policy.allowed_model_ids_json,
            policy.allowed_provider_ids_json,
            policy.block_reason,
            policy.revision,
            policy.updated_at,
            (SELECT COUNT(*) FROM users WHERE tenant_id = tenant.id) AS user_count,
            (
                SELECT COUNT(*)
                FROM sessions
                WHERE tenant_id = tenant.id
                  AND revoked_at IS NULL
                  AND expires_at > unixepoch()
            ) + (
                SELECT COUNT(*)
                FROM mobile_device_sessions
                WHERE tenant_id = tenant.id
                  AND revoked_at IS NULL
                  AND expires_at > unixepoch()
            ) AS active_session_count
        FROM tenants AS tenant
        JOIN platform_tenant_policies AS policy
          ON policy.tenant_id = tenant.id
        WHERE (? IS NULL OR tenant.id > ?)
        ORDER BY tenant.id ASC
        LIMIT ?
        """,
        (cursor, cursor, limit + 1),
    ).fetchall()
    page = rows[:limit]
    return {
        "items": [_tenant_projection(row) for row in page],
        "nextCursor": str(page[-1]["id"]) if len(rows) > limit else None,
    }


@router.get("/users")
def list_users(
    _owner: OwnerDependency,
    database: DatabaseDependency,
    limit: PageLimit = 50,
    cursor: str | None = Query(default=None, max_length=160),
    tenant_id: str | None = Query(default=None, alias="tenantId", max_length=160),
) -> dict[str, Any]:
    for value in (cursor, tenant_id):
        if value is not None and _SAFE_ID.fullmatch(value) is None:
            raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_cursor", "Filter is invalid.")
    rows = database.execute(
        """
        SELECT
            users.id,
            users.tenant_id,
            users.email,
            users.name,
            users.role,
            users.created_at,
            users.updated_at,
            control.access_status,
            control.developer_access,
            control.block_reason,
            control.revision,
            control.updated_at AS control_updated_at,
            EXISTS (
                SELECT 1
                FROM platform_authority_grants AS authority
                WHERE authority.authority_id = 'platform_owner'
                  AND authority.user_id = users.id
                  AND authority.tenant_id = users.tenant_id
                  AND authority.active = 1
            ) AS is_platform_owner,
            (
                SELECT COUNT(*)
                FROM sessions
                WHERE sessions.user_id = users.id
                  AND sessions.tenant_id = users.tenant_id
                  AND sessions.revoked_at IS NULL
                  AND sessions.expires_at > unixepoch()
            ) + (
                SELECT COUNT(*)
                FROM mobile_device_sessions
                WHERE mobile_device_sessions.user_id = users.id
                  AND mobile_device_sessions.tenant_id = users.tenant_id
                  AND mobile_device_sessions.revoked_at IS NULL
                  AND mobile_device_sessions.expires_at > unixepoch()
            ) AS active_session_count
        FROM users
        JOIN platform_user_controls AS control
          ON control.user_id = users.id
         AND control.tenant_id = users.tenant_id
        WHERE (? IS NULL OR users.tenant_id = ?)
          AND (? IS NULL OR users.id > ?)
        ORDER BY users.id ASC
        LIMIT ?
        """,
        (tenant_id, tenant_id, cursor, cursor, limit + 1),
    ).fetchall()
    page = rows[:limit]
    return {
        "items": [_user_projection(row) for row in page],
        "nextCursor": str(page[-1]["id"]) if len(rows) > limit else None,
    }


@router.patch("/tenants/{tenant_id}")
def update_tenant_policy(
    tenant_id: str,
    payload: TenantPolicyPatch,
    owner: OwnerDependency,
    database: DatabaseDependency,
    _auth: MutationAuthDependency,
) -> dict[str, Any]:
    if _SAFE_ID.fullmatch(tenant_id) is None:
        raise _error(status.HTTP_404_NOT_FOUND, "tenant_not_found", "Tenant was not found.")
    with transaction(database, immediate=True):
        before_row = _tenant_row(database, tenant_id=tenant_id)
        if before_row is None:
            raise _error(status.HTTP_404_NOT_FOUND, "tenant_not_found", "Tenant was not found.")
        if (
            tenant_id == owner.tenant_id
            and payload.lifecycle_status == "suspended"
        ):
            raise _error(
                status.HTTP_409_CONFLICT,
                "platform_owner_tenant_protected",
                "Рабочее пространство владельца платформы нельзя приостановить.",
            )
        before = _tenant_projection(before_row)
        fields: dict[str, object] = {}
        aliases = {
            "lifecycle_status": "lifecycle_status",
            "plan_code": "plan_code",
            "user_limit": "user_limit",
            "monthly_run_limit": "monthly_run_limit",
            "developer_access_enabled": "developer_access_enabled",
            "allowed_model_ids": "allowed_model_ids_json",
            "allowed_provider_ids": "allowed_provider_ids_json",
            "block_reason": "block_reason",
        }
        for model_field, column in aliases.items():
            if model_field not in payload.model_fields_set:
                continue
            value = getattr(payload, model_field)
            if model_field in {"allowed_model_ids", "allowed_provider_ids"}:
                value = None if value is None else _canonical_json(value)
            elif model_field == "developer_access_enabled":
                value = int(bool(value))
            elif model_field == "block_reason" and isinstance(value, str):
                value = value.strip() or None
            fields[column] = value
        assignments = ", ".join(f"{column} = ?" for column in fields)
        values = [*fields.values(), owner.user_id, tenant_id, payload.revision]
        changed = database.execute(
            f"""
            UPDATE platform_tenant_policies
            SET {assignments},
                revision = revision + 1,
                updated_at = unixepoch(),
                updated_by_user_id = ?
            WHERE tenant_id = ? AND revision = ?
            """,
            values,
        )
        if changed.rowcount != 1:
            raise _error(
                status.HTTP_409_CONFLICT,
                "revision_conflict",
                "Политика уже изменена. Обновите данные.",
            )
        if payload.lifecycle_status == "suspended":
            _revoke_sessions(database, tenant_id=tenant_id)
        after_row = _tenant_row(database, tenant_id=tenant_id)
        assert after_row is not None
        after = _tenant_projection(after_row)
        _record_audit(
            database,
            actor=owner,
            action="tenant.policy.updated",
            target_type="tenant",
            target_id=tenant_id,
            target_tenant_id=tenant_id,
            before=before,
            after=after,
        )
    return after


@router.patch("/users/{user_id}")
def update_user_control(
    user_id: str,
    payload: UserControlPatch,
    owner: OwnerDependency,
    database: DatabaseDependency,
    _auth: MutationAuthDependency,
) -> dict[str, Any]:
    if _SAFE_ID.fullmatch(user_id) is None:
        raise _error(status.HTTP_404_NOT_FOUND, "user_not_found", "User was not found.")
    with transaction(database, immediate=True):
        before_row = _user_row(database, user_id=user_id)
        if before_row is None:
            raise _error(status.HTTP_404_NOT_FOUND, "user_not_found", "User was not found.")
        if bool(before_row["is_platform_owner"]):
            raise _error(
                status.HTTP_409_CONFLICT,
                "platform_owner_protected",
                "Владельца платформы нельзя заблокировать через HTTP.",
            )
        before = _user_projection(before_row)
        fields: dict[str, object] = {}
        for model_field, column in (
            ("access_status", "access_status"),
            ("developer_access", "developer_access"),
            ("block_reason", "block_reason"),
        ):
            if model_field not in payload.model_fields_set:
                continue
            value = getattr(payload, model_field)
            if model_field == "block_reason" and isinstance(value, str):
                value = value.strip() or None
            fields[column] = value
        assignments = ", ".join(f"{column} = ?" for column in fields)
        changed = database.execute(
            f"""
            UPDATE platform_user_controls
            SET {assignments},
                revision = revision + 1,
                updated_at = unixepoch(),
                updated_by_user_id = ?
            WHERE user_id = ? AND tenant_id = ? AND revision = ?
            """,
            (
                *fields.values(),
                owner.user_id,
                user_id,
                str(before_row["tenant_id"]),
                payload.revision,
            ),
        )
        if changed.rowcount != 1:
            raise _error(
                status.HTTP_409_CONFLICT,
                "revision_conflict",
                "Настройки пользователя уже изменены. Обновите данные.",
            )
        if payload.access_status == "blocked":
            _revoke_sessions(
                database,
                tenant_id=str(before_row["tenant_id"]),
                user_id=user_id,
            )
        after_row = _user_row(database, user_id=user_id)
        assert after_row is not None
        after = _user_projection(after_row)
        _record_audit(
            database,
            actor=owner,
            action="user.control.updated",
            target_type="user",
            target_id=user_id,
            target_tenant_id=str(before_row["tenant_id"]),
            before=before,
            after=after,
        )
    return after


@router.get("/users/{user_id}/entitlements/{entitlement_code}")
def get_user_product_entitlement(
    user_id: str,
    entitlement_code: str,
    _owner: OwnerDependency,
    database: DatabaseDependency,
) -> dict[str, Any]:
    if _SAFE_ID.fullmatch(user_id) is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "user_not_found",
            "User was not found.",
        )
    _validate_product_entitlement_code(entitlement_code)
    row = _product_entitlement_row(
        database,
        user_id=user_id,
        entitlement_code=entitlement_code,
    )
    if row is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "user_not_found",
            "User was not found.",
        )
    return _product_entitlement_projection(
        row,
        entitlement_code=entitlement_code,
    )


@router.patch("/users/{user_id}/entitlements/{entitlement_code}")
def update_user_product_entitlement(
    user_id: str,
    entitlement_code: str,
    payload: ProductEntitlementPatch,
    owner: OwnerDependency,
    database: DatabaseDependency,
    _auth: MutationAuthDependency,
) -> dict[str, Any]:
    if _SAFE_ID.fullmatch(user_id) is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "user_not_found",
            "User was not found.",
        )
    _validate_product_entitlement_code(entitlement_code)
    with transaction(database, immediate=True):
        before_row = _product_entitlement_row(
            database,
            user_id=user_id,
            entitlement_code=entitlement_code,
        )
        if before_row is None:
            raise _error(
                status.HTTP_404_NOT_FOUND,
                "user_not_found",
                "User was not found.",
            )
        before = _product_entitlement_projection(
            before_row,
            entitlement_code=entitlement_code,
        )
        current_epoch = int(before["grantEpoch"])
        if payload.expected_epoch != current_epoch:
            raise _error(
                status.HTTP_409_CONFLICT,
                "product_entitlement_epoch_conflict",
                "Продуктовый доступ уже изменён. Обновите данные.",
            )

        changed = str(before["status"]) != payload.status
        if changed and current_epoch == 0:
            database.execute(
                """
                INSERT INTO product_entitlement_grants (
                    tenant_id, user_id, entitlement_code, status,
                    grant_epoch, source, created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, 1, 'platform_admin',
                    unixepoch(), unixepoch()
                )
                """,
                (
                    str(before["tenantId"]),
                    user_id,
                    entitlement_code,
                    payload.status,
                ),
            )
        elif changed:
            updated = database.execute(
                """
                UPDATE product_entitlement_grants
                SET status = ?,
                    grant_epoch = grant_epoch + 1,
                    source = 'platform_admin',
                    updated_at = unixepoch()
                WHERE tenant_id = ?
                  AND user_id = ?
                  AND entitlement_code = ?
                  AND grant_epoch = ?
                """,
                (
                    payload.status,
                    str(before["tenantId"]),
                    user_id,
                    entitlement_code,
                    current_epoch,
                ),
            )
            if updated.rowcount != 1:
                raise _error(
                    status.HTTP_409_CONFLICT,
                    "product_entitlement_epoch_conflict",
                    "Продуктовый доступ уже изменён. Обновите данные.",
                )

        after_row = _product_entitlement_row(
            database,
            user_id=user_id,
            entitlement_code=entitlement_code,
        )
        assert after_row is not None
        after = _product_entitlement_projection(
            after_row,
            entitlement_code=entitlement_code,
        )
        if changed:
            _record_audit(
                database,
                actor=owner,
                action=(
                    "user.product_entitlement.granted"
                    if payload.status == "active"
                    else "user.product_entitlement.revoked"
                ),
                target_type="user",
                target_id=user_id,
                target_tenant_id=str(before["tenantId"]),
                before=before,
                after=after,
            )
    return {**after, "changed": changed}


@router.post("/users/{user_id}/sessions/revoke")
def revoke_user_sessions(
    user_id: str,
    owner: OwnerDependency,
    database: DatabaseDependency,
    _auth: MutationAuthDependency,
) -> dict[str, Any]:
    if _SAFE_ID.fullmatch(user_id) is None:
        raise _error(status.HTTP_404_NOT_FOUND, "user_not_found", "User was not found.")
    with transaction(database, immediate=True):
        target = _user_row(database, user_id=user_id)
        if target is None:
            raise _error(status.HTTP_404_NOT_FOUND, "user_not_found", "User was not found.")
        if bool(target["is_platform_owner"]):
            raise _error(
                status.HTTP_409_CONFLICT,
                "platform_owner_protected",
                "Сессии владельца платформы нельзя отозвать через HTTP.",
            )
        count = _revoke_sessions(
            database,
            tenant_id=str(target["tenant_id"]),
            user_id=user_id,
        )
        _record_audit(
            database,
            actor=owner,
            action="user.sessions.revoked",
            target_type="sessions",
            target_id=user_id,
            target_tenant_id=str(target["tenant_id"]),
            before={"activeSessionCount": int(target["active_session_count"])},
            after={"revokedSessionCount": count},
        )
    return {"userId": user_id, "revokedSessionCount": count}


@router.get("/audit")
def list_audit_events(
    _owner: OwnerDependency,
    database: DatabaseDependency,
    limit: PageLimit = 50,
    cursor: str | None = Query(default=None, max_length=192),
) -> dict[str, Any]:
    created_before: int | None = None
    id_before: str | None = None
    if cursor is not None:
        match = _AUDIT_CURSOR.fullmatch(cursor)
        if match is None:
            raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_cursor", "Cursor is invalid.")
        created_before = int(match.group(1))
        id_before = match.group(2)
    rows = database.execute(
        """
        SELECT *
        FROM platform_admin_audit_events
        WHERE (
            ? IS NULL
            OR created_at < ?
            OR (created_at = ? AND id < ?)
        )
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (
            created_before,
            created_before,
            created_before,
            id_before,
            limit + 1,
        ),
    ).fetchall()
    page = rows[:limit]
    items = [
        {
            "id": str(row["id"]),
            "actorUserId": str(row["actor_user_id"]),
            "action": str(row["action"]),
            "targetType": str(row["target_type"]),
            "targetId": str(row["target_id"]),
            "targetTenantId": str(row["target_tenant_id"]),
            "before": json.loads(str(row["before_json"])),
            "after": json.loads(str(row["after_json"])),
            "createdAt": int(row["created_at"]),
        }
        for row in page
    ]
    next_cursor = (
        f"{int(page[-1]['created_at'])}:{str(page[-1]['id'])}"
        if len(rows) > limit
        else None
    )
    return {"items": items, "nextCursor": next_cursor}
