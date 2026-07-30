"""Deny-by-default, server-owned product entitlement projection."""

from __future__ import annotations

import sqlite3
from dataclasses import replace

from .schemas import UserSession

CONSTRUCTION_ESTIMATES_ENTITLEMENT = "construction.estimates.use"
CONSTRUCTION_ESTIMATES_CAPABILITY = "construction.estimates.workspace"

_CAPABILITIES_BY_ENTITLEMENT: dict[str, tuple[str, ...]] = {
    CONSTRUCTION_ESTIMATES_ENTITLEMENT: (
        CONSTRUCTION_ESTIMATES_CAPABILITY,
    ),
}


class ProductEntitlementError(RuntimeError):
    status_code = 403
    code = "product_entitlement_required"
    message = "Для этой функции требуется доступ к продукту."

    def __init__(self, entitlement_code: str) -> None:
        super().__init__(self.code)
        self.entitlement_code = entitlement_code


def require_product_entitlement(
    identity: UserSession,
    entitlement_code: str,
) -> UserSession:
    """Authorize one compiled product entitlement from the live projection."""

    if (
        entitlement_code not in _CAPABILITIES_BY_ENTITLEMENT
        or entitlement_code not in identity.product_entitlements
    ):
        raise ProductEntitlementError(entitlement_code)
    return identity


def require_persisted_product_entitlement(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str,
    entitlement_code: str,
    expected_epoch: int | None = None,
) -> int:
    """Re-check one grant at a delayed or external execution boundary."""

    if entitlement_code not in _CAPABILITIES_BY_ENTITLEMENT:
        raise ProductEntitlementError(entitlement_code)
    row = database.execute(
        """
        SELECT grant_epoch
        FROM product_entitlement_grants
        WHERE tenant_id = ?
          AND user_id = ?
          AND entitlement_code = ?
          AND status = 'active'
        LIMIT 1
        """,
        (tenant_id, user_id, entitlement_code),
    ).fetchone()
    if row is None:
        raise ProductEntitlementError(entitlement_code)
    epoch = int(row["grant_epoch"])
    if expected_epoch is not None and epoch != expected_epoch:
        raise ProductEntitlementError(entitlement_code)
    return epoch


def bind_product_entitlements(
    database: sqlite3.Connection,
    identity: UserSession,
) -> UserSession:
    """Project persisted grants for the exact authenticated tenant/user.

    Client fields, account role labels and tenant identifiers supplied by a
    request never participate in this decision. Unknown persisted codes cannot
    broaden access because only the compiled allowlist is projected.
    """

    rows = database.execute(
        """
        SELECT entitlement_code, grant_epoch
        FROM product_entitlement_grants
        WHERE tenant_id = ?
          AND user_id = ?
          AND status = 'active'
        ORDER BY entitlement_code
        """,
        (identity.tenant_id, identity.user_id),
    ).fetchall()

    entitlements: list[str] = []
    capabilities: list[str] = []
    epoch: int | None = None
    for row in rows:
        entitlement = str(row["entitlement_code"])
        mapped = _CAPABILITIES_BY_ENTITLEMENT.get(entitlement)
        if mapped is None:
            continue
        entitlements.append(entitlement)
        capabilities.extend(mapped)
        row_epoch = int(row["grant_epoch"])
        epoch = row_epoch if epoch is None else max(epoch, row_epoch)

    return replace(
        identity,
        product_capabilities=tuple(dict.fromkeys(capabilities)),
        product_entitlements=tuple(dict.fromkeys(entitlements)),
        product_entitlement_epoch=epoch,
    )
