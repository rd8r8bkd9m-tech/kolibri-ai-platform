"""FastAPI dependencies for server-owned product access."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException

from .identity import require_user
from .product_entitlements import (
    CONSTRUCTION_ESTIMATES_ENTITLEMENT,
    ProductEntitlementError,
    require_product_entitlement,
)
from .schemas import UserSession


def require_construction_estimates(
    identity: Annotated[UserSession, Depends(require_user)],
) -> UserSession:
    try:
        return require_product_entitlement(
            identity,
            CONSTRUCTION_ESTIMATES_ENTITLEMENT,
        )
    except ProductEntitlementError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


ConstructionEstimateAccessDependency = Annotated[
    UserSession,
    Depends(require_construction_estimates),
]
