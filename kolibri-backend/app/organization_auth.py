"""Organization tenancy principals and fail-closed role dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_optional_user
from app.database import get_db
from app.models import (
    OrganizationAuditEventDB,
    OrganizationDB,
    OrganizationMembershipDB,
    UserDB,
)


ORGANIZATION_HEADER = "X-Kolibri-Organization"
ORGANIZATION_COOKIE_NAME = "kolibri_organization"
ACTIVE_STATUS = "active"
ORGANIZATION_ROLES = frozenset({"owner", "admin", "member"})
ORGANIZATION_ADMIN_ROLES = frozenset({"owner", "admin"})
PERSONAL_ORGANIZATION_NAMESPACE = uuid.UUID("5f19d5ea-4b88-4a17-9a7c-7bfdf11c3a49")
PERSONAL_MEMBERSHIP_NAMESPACE = uuid.UUID("c47a242e-807d-4e87-b030-f9266175ed42")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _personal_id(namespace: uuid.UUID, user_id: str) -> str:
    return str(uuid.uuid5(namespace, user_id))


@dataclass(frozen=True)
class OrganizationPrincipal:
    """A freshly verified company principal for one request."""

    user_id: str
    organization_id: str
    organization_role: str
    scope_id: str
    platform_role: str


def ensure_personal_organization(db: Session, user: UserDB) -> OrganizationDB:
    """Idempotently provision one personal organization for a persisted user.

    The stable ``user:<id>`` scope is intentional: existing resource ownership
    and CAS bindings continue to work while organization-aware routes are
    adopted incrementally.
    """

    db.flush()
    data_scope_id = f"user:{user.id}"
    organization = (
        db.query(OrganizationDB)
        .filter(OrganizationDB.data_scope_id == data_scope_id)
        .first()
    )
    created = organization is None
    if organization is None:
        organization_id = _personal_id(PERSONAL_ORGANIZATION_NAMESPACE, user.id)
        organization = OrganizationDB(
            id=organization_id,
            data_scope_id=data_scope_id,
            name=f"{str(user.name).strip()} — личная организация",
            slug=f"personal-{organization_id}",
            status=ACTIVE_STATUS,
            settings={},
        )
        db.add(organization)
        db.flush()

    membership = (
        db.query(OrganizationMembershipDB)
        .filter(
            OrganizationMembershipDB.organization_id == organization.id,
            OrganizationMembershipDB.user_id == user.id,
        )
        .first()
    )
    if membership is None:
        db.add(
            OrganizationMembershipDB(
                id=_personal_id(PERSONAL_MEMBERSHIP_NAMESPACE, user.id),
                organization_id=organization.id,
                user_id=user.id,
                role="owner",
                status=ACTIVE_STATUS,
            )
        )

    if not user.default_organization_id:
        user.default_organization_id = organization.id

    if created:
        db.add(
            OrganizationAuditEventDB(
                id=str(uuid.uuid4()),
                organization_id=organization.id,
                actor_user_id=user.id,
                action="organization.personal_created",
                target_type="organization",
                target_id=organization.id,
                attributes={"data_scope_id": data_scope_id},
            )
        )
    return organization


def record_organization_audit(
    db: Session,
    principal: OrganizationPrincipal,
    *,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    request_id: str | None = None,
    metadata: dict | None = None,
) -> OrganizationAuditEventDB:
    """Append an organization-scoped event without committing the caller's unit of work."""

    event = OrganizationAuditEventDB(
        id=str(uuid.uuid4()),
        organization_id=principal.organization_id,
        actor_user_id=principal.user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        request_id=request_id,
        attributes=dict(metadata or {}),
        created_at=_now(),
    )
    db.add(event)
    return event


def _resolve_for_user(
    db: Session,
    user: UserDB,
    *,
    selected_organization_id: str | None,
    organization_cookie: str | None,
) -> OrganizationPrincipal:
    organization_id = (
        selected_organization_id
        or organization_cookie
        or user.default_organization_id
    )
    if not organization_id or len(organization_id) > 128:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "organization_access_denied"},
        )

    row = (
        db.query(OrganizationMembershipDB, OrganizationDB)
        .join(
            OrganizationDB,
            OrganizationDB.id == OrganizationMembershipDB.organization_id,
        )
        .filter(
            OrganizationMembershipDB.organization_id == organization_id,
            OrganizationMembershipDB.user_id == user.id,
            OrganizationMembershipDB.status == ACTIVE_STATUS,
            OrganizationDB.status == ACTIVE_STATUS,
        )
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "organization_access_denied"},
        )
    membership, organization = row
    role = str(membership.role or "").strip().lower()
    if role not in ORGANIZATION_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "organization_role_invalid"},
        )
    return OrganizationPrincipal(
        user_id=user.id,
        organization_id=organization.id,
        organization_role=role,
        scope_id=organization.data_scope_id,
        platform_role=str(user.role or "user").strip().lower(),
    )


def resolve_optional_organization_principal(
    selected_organization_id: str | None = Header(
        default=None,
        alias=ORGANIZATION_HEADER,
    ),
    organization_cookie: str | None = Cookie(
        default=None,
        alias=ORGANIZATION_COOKIE_NAME,
    ),
    user: UserDB | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> OrganizationPrincipal | None:
    if user is None:
        return None
    return _resolve_for_user(
        db,
        user,
        selected_organization_id=selected_organization_id,
        organization_cookie=organization_cookie,
    )


def resolve_organization_principal(
    selected_organization_id: str | None = Header(
        default=None,
        alias=ORGANIZATION_HEADER,
    ),
    organization_cookie: str | None = Cookie(
        default=None,
        alias=ORGANIZATION_COOKIE_NAME,
    ),
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationPrincipal:
    """Resolve and recheck active user, organization and membership from SQL.

    No role is trusted from a JWT or selection cookie.  A revoked membership
    is denied on the next request even while both credentials remain valid.
    """

    return _resolve_for_user(
        db,
        user,
        selected_organization_id=selected_organization_id,
        organization_cookie=organization_cookie,
    )


def require_org_member(
    principal: OrganizationPrincipal = Depends(resolve_organization_principal),
) -> OrganizationPrincipal:
    return principal


def require_org_admin(
    principal: OrganizationPrincipal = Depends(resolve_organization_principal),
) -> OrganizationPrincipal:
    if principal.organization_role not in ORGANIZATION_ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "organization_admin_required"},
        )
    return principal


def require_org_owner(
    principal: OrganizationPrincipal = Depends(resolve_organization_principal),
) -> OrganizationPrincipal:
    if principal.organization_role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "organization_owner_required"},
        )
    return principal


__all__ = [
    "ORGANIZATION_HEADER",
    "ORGANIZATION_COOKIE_NAME",
    "OrganizationPrincipal",
    "ensure_personal_organization",
    "record_organization_audit",
    "require_org_admin",
    "require_org_member",
    "require_org_owner",
    "resolve_optional_organization_principal",
    "resolve_organization_principal",
]
