"""Server-derived singleton platform authority.

Tenant roles are display/backward-compatibility data. Cross-tenant authority
is granted only by the singleton row created through trusted bootstrap.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import replace

from .product_entitlements import bind_product_entitlements
from .schemas import UserSession

_CAPABILITY = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")
PLATFORM_OWNER_CAPABILITIES = (
    "platform.admin",
    "platform.audit.read",
    "platform.policy.write",
    "platform.sessions.revoke",
    "platform.storage.manage",
    "chat.developer.request",
    "chat.use",
)


class PlatformDeveloperAuthorityError(RuntimeError):
    status_code = 403
    code = "owner_required"
    message = "Owner access is required for developer agent mode."

    def __init__(self) -> None:
        super().__init__(self.code)


def _validated_capabilities(raw: object) -> tuple[str, ...] | None:
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError):
        return None
    if (
        not isinstance(value, list)
        or not value
        or len(value) > 32
        or any(
            not isinstance(item, str)
            or _CAPABILITY.fullmatch(item) is None
            for item in value
        )
        or len(set(value)) != len(value)
        or "platform.admin" not in value
    ):
        return None
    return tuple(value)


def require_platform_developer_authority(identity: UserSession) -> None:
    """Authorize the owner-only developer operator mode without policy oracles."""

    if (
        not identity.is_platform_owner
        or "chat.developer.request"
        not in identity.platform_capabilities
    ):
        raise PlatformDeveloperAuthorityError()


def require_persisted_platform_developer_authority(
    database: sqlite3.Connection,
    *,
    user_id: str,
    tenant_id: str,
    expected_epoch: int | None = None,
) -> int:
    """Re-check the live singleton grant at an external execution boundary."""

    row = database.execute(
        """
        SELECT authority_epoch, capabilities_json
        FROM platform_authority_grants
        WHERE authority_id = 'platform_owner'
          AND user_id = ?
          AND tenant_id = ?
          AND active = 1
        LIMIT 1
        """,
        (user_id, tenant_id),
    ).fetchone()
    capabilities = (
        None if row is None else _validated_capabilities(row["capabilities_json"])
    )
    if capabilities is None or "chat.developer.request" not in capabilities:
        raise PlatformDeveloperAuthorityError()
    epoch = int(row["authority_epoch"])
    if expected_epoch is not None and epoch != expected_epoch:
        raise PlatformDeveloperAuthorityError()
    return epoch


def bind_platform_authority(
    database: sqlite3.Connection,
    identity: UserSession,
) -> UserSession:
    row = database.execute(
        """
        SELECT authority_epoch, capabilities_json
        FROM platform_authority_grants
        WHERE authority_id = 'platform_owner'
          AND user_id = ?
          AND tenant_id = ?
          AND active = 1
        LIMIT 1
        """,
        (identity.user_id, identity.tenant_id),
    ).fetchone()
    if row is None:
        return bind_product_entitlements(
            database,
            replace(
                identity,
                is_platform_owner=False,
                platform_capabilities=("chat.use",),
                platform_authority_epoch=None,
            ),
        )
    capabilities = _validated_capabilities(row["capabilities_json"])
    if capabilities is None:
        # Corrupt authority data must never broaden access.
        return bind_product_entitlements(
            database,
            replace(
                identity,
                is_platform_owner=False,
                platform_capabilities=("chat.use",),
                platform_authority_epoch=None,
            ),
        )
    return bind_product_entitlements(
        database,
        replace(
            identity,
            is_platform_owner=True,
            platform_capabilities=capabilities,
            platform_authority_epoch=int(row["authority_epoch"]),
        ),
    )
