"""Authenticated organization selection and membership administration."""

from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import (
    OrganizationAuditEventDB,
    OrganizationDB,
    OrganizationMembershipDB,
    PublicApiKeyDB,
    UserDB,
)
from app.organization_auth import (
    ACTIVE_STATUS,
    ORGANIZATION_COOKIE_NAME,
    ORGANIZATION_ROLES,
    OrganizationPrincipal,
    record_organization_audit,
    require_org_admin,
)


router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])
_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str | None = Field(default=None, max_length=63)

class CompanyProfileUpdate(BaseModel):
    legal_name: str = Field(default="", max_length=500)
    inn: str = Field(default="", max_length=20)
    kpp: str = Field(default="", max_length=20)
    ogrn: str = Field(default="", max_length=30)
    director_name: str = Field(default="", max_length=300)
    director_title: str = Field(default="", max_length=160)
    legal_address: str = Field(default="", max_length=1_000)
    actual_address: str = Field(default="", max_length=1_000)
    phone: str = Field(default="", max_length=80)
    email: str = Field(default="", max_length=320)
    bank_name: str = Field(default="", max_length=500)
    bik: str = Field(default="", max_length=20)
    checking_account: str = Field(default="", max_length=34)
    correspondent_account: str = Field(default="", max_length=34)


class MembershipInvite(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: str = Field(default="member")


class MembershipRoleChange(BaseModel):
    role: str


def _not_found(code: str = "organization_not_found") -> HTTPException:
    return HTTPException(status_code=404, detail={"code": code})


def _public_organization(
    organization: OrganizationDB,
    membership: OrganizationMembershipDB,
    *,
    selected: bool,
) -> dict:
    settings = organization.settings if isinstance(organization.settings, dict) else {}
    company_profile = settings.get("company_profile")
    return {
        "id": organization.id,
        "name": organization.name,
        "slug": organization.slug,
        "status": organization.status,
        "role": membership.role,
        "membership_status": membership.status,
        "selected": selected,
        "company_profile": company_profile if isinstance(company_profile, dict) else {},
    }


def _public_membership(membership: OrganizationMembershipDB, user: UserDB) -> dict:
    return {
        "id": membership.id,
        "organization_id": membership.organization_id,
        "user": {"id": user.id, "email": user.email, "name": user.name},
        "role": membership.role,
        "status": membership.status,
        "created_at": membership.created_at,
        "updated_at": membership.updated_at,
    }


def _require_path_org(
    organization_id: str,
    principal: OrganizationPrincipal,
) -> None:
    if principal.organization_id != organization_id:
        raise _not_found()


def _normalize_role(role: str) -> str:
    normalized = str(role or "").strip().lower()
    if normalized not in ORGANIZATION_ROLES:
        raise HTTPException(status_code=422, detail={"code": "organization_role_invalid"})
    return normalized


def _assert_can_manage_role(
    principal: OrganizationPrincipal,
    *,
    current_role: str | None,
    requested_role: str | None,
) -> None:
    if principal.organization_role == "owner":
        return
    if current_role in {"owner", "admin"} or requested_role in {"owner", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "organization_owner_required"},
        )


def _assert_not_last_owner(
    db: Session,
    membership: OrganizationMembershipDB,
    *,
    requested_role: str | None,
) -> None:
    if membership.role != "owner" or requested_role == "owner":
        return
    owners = db.query(OrganizationMembershipDB.id).filter(
        OrganizationMembershipDB.organization_id == membership.organization_id,
        OrganizationMembershipDB.role == "owner",
        OrganizationMembershipDB.status == ACTIVE_STATUS,
    ).count()
    if owners <= 1:
        raise HTTPException(status_code=409, detail={"code": "last_owner_required"})


def _revoke_member_created_keys(
    db: Session,
    *,
    organization_id: str,
    user_id: str,
    now: datetime,
) -> int:
    key_ids = select(OrganizationAuditEventDB.target_id).where(
        OrganizationAuditEventDB.organization_id == organization_id,
        OrganizationAuditEventDB.actor_user_id == user_id,
        OrganizationAuditEventDB.action == "api_key.created",
        OrganizationAuditEventDB.target_type == "api_key",
    )
    return db.query(PublicApiKeyDB).filter(
        PublicApiKeyDB.organization_id == organization_id,
        PublicApiKeyDB.id.in_(key_ids),
        PublicApiKeyDB.revoked_at.is_(None),
    ).update({PublicApiKeyDB.revoked_at: now}, synchronize_session=False)


@router.get("")
def list_organizations(
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(OrganizationDB, OrganizationMembershipDB)
        .join(
            OrganizationMembershipDB,
            OrganizationMembershipDB.organization_id == OrganizationDB.id,
        )
        .filter(
            OrganizationMembershipDB.user_id == user.id,
            OrganizationMembershipDB.status == ACTIVE_STATUS,
            OrganizationDB.status == ACTIVE_STATUS,
        )
        .order_by(OrganizationDB.created_at.asc(), OrganizationDB.id.asc())
        .all()
    )
    return {
        "items": [
            _public_organization(
                organization,
                membership,
                selected=organization.id == user.default_organization_id,
            )
            for organization, membership in rows
        ]
    }


@router.post("", status_code=201)
def create_organization(
    data: OrganizationCreate,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail={"code": "organization_name_required"})
    organization_id = str(uuid.uuid4())
    slug = (data.slug or f"org-{organization_id}").strip().lower()
    if not _SLUG.fullmatch(slug):
        raise HTTPException(status_code=422, detail={"code": "organization_slug_invalid"})
    if db.query(OrganizationDB.id).filter(OrganizationDB.slug == slug).first() is not None:
        raise HTTPException(status_code=409, detail={"code": "organization_slug_exists"})
    now = datetime.now(timezone.utc)
    organization = OrganizationDB(
        id=organization_id,
        data_scope_id=f"organization:{organization_id}",
        name=name,
        slug=slug,
        status=ACTIVE_STATUS,
        settings={},
        created_at=now,
        updated_at=now,
    )
    membership = OrganizationMembershipDB(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        user_id=user.id,
        role="owner",
        status=ACTIVE_STATUS,
        created_at=now,
        updated_at=now,
    )
    db.add_all([organization, membership])
    db.flush()
    principal = OrganizationPrincipal(
        user_id=user.id,
        organization_id=organization.id,
        organization_role="owner",
        scope_id=organization.data_scope_id,
        platform_role=str(user.role or "user"),
    )
    record_organization_audit(
        db,
        principal,
        action="organization.created",
        target_type="organization",
        target_id=organization.id,
    )
    db.commit()
    return _public_organization(organization, membership, selected=False)


@router.post("/{organization_id}/select")
def select_organization(
    organization_id: str,
    request: Request,
    response: Response,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(OrganizationDB, OrganizationMembershipDB)
        .join(
            OrganizationMembershipDB,
            OrganizationMembershipDB.organization_id == OrganizationDB.id,
        )
        .filter(
            OrganizationDB.id == organization_id,
            OrganizationDB.status == ACTIVE_STATUS,
            OrganizationMembershipDB.user_id == user.id,
            OrganizationMembershipDB.status == ACTIVE_STATUS,
        )
        .first()
    )
    if row is None:
        raise _not_found()
    organization, membership = row
    user.default_organization_id = organization.id
    principal = OrganizationPrincipal(
        user_id=user.id,
        organization_id=organization.id,
        organization_role=membership.role,
        scope_id=organization.data_scope_id,
        platform_role=str(user.role or "user"),
    )
    record_organization_audit(
        db,
        principal,
        action="organization.selected",
        target_type="organization",
        target_id=organization.id,
    )
    db.commit()
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    response.set_cookie(
        ORGANIZATION_COOKIE_NAME,
        organization.id,
        max_age=30 * 24 * 60 * 60,
        path="/",
        secure=request.url.scheme == "https" or forwarded_proto == "https",
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "private, no-store"
    return _public_organization(organization, membership, selected=True)


@router.patch("/{organization_id}/profile")
def update_company_profile(
    organization_id: str,
    data: CompanyProfileUpdate,
    principal: OrganizationPrincipal = Depends(require_org_admin),
    db: Session = Depends(get_db),
):
    _require_path_org(organization_id, principal)
    organization = db.query(OrganizationDB).filter(
        OrganizationDB.id == organization_id,
        OrganizationDB.status == ACTIVE_STATUS,
    ).with_for_update().first()
    if organization is None:
        raise _not_found()
    settings = dict(organization.settings) if isinstance(organization.settings, dict) else {}
    settings["company_profile"] = {
        key: " ".join(str(value or "").split()).strip()
        for key, value in data.model_dump().items()
    }
    organization.settings = settings
    organization.updated_at = datetime.now(timezone.utc)
    record_organization_audit(
        db,
        principal,
        action="organization.profile_updated",
        target_type="organization",
        target_id=organization.id,
    )
    db.commit()
    membership = db.query(OrganizationMembershipDB).filter(
        OrganizationMembershipDB.organization_id == organization_id,
        OrganizationMembershipDB.user_id == principal.user_id,
        OrganizationMembershipDB.status == ACTIVE_STATUS,
    ).one()
    return _public_organization(organization, membership, selected=True)


@router.get("/{organization_id}/memberships")
def list_memberships(
    organization_id: str,
    principal: OrganizationPrincipal = Depends(require_org_admin),
    db: Session = Depends(get_db),
):
    _require_path_org(organization_id, principal)
    rows = (
        db.query(OrganizationMembershipDB, UserDB)
        .join(UserDB, UserDB.id == OrganizationMembershipDB.user_id)
        .filter(OrganizationMembershipDB.organization_id == organization_id)
        .order_by(OrganizationMembershipDB.created_at.asc())
        .all()
    )
    return {"items": [_public_membership(membership, user) for membership, user in rows]}


@router.post("/{organization_id}/memberships", status_code=201)
def invite_membership(
    organization_id: str,
    data: MembershipInvite,
    principal: OrganizationPrincipal = Depends(require_org_admin),
    db: Session = Depends(get_db),
):
    _require_path_org(organization_id, principal)
    role = _normalize_role(data.role)
    if role == "owner":
        raise HTTPException(status_code=422, detail={"code": "owner_invite_not_supported"})
    _assert_can_manage_role(principal, current_role=None, requested_role=role)
    target = db.query(UserDB).filter(UserDB.email == data.email.strip()).first()
    if target is None or not target.is_active:
        raise _not_found("invitee_not_found")
    membership = db.query(OrganizationMembershipDB).filter(
        OrganizationMembershipDB.organization_id == organization_id,
        OrganizationMembershipDB.user_id == target.id,
    ).first()
    now = datetime.now(timezone.utc)
    if membership is not None and membership.status == ACTIVE_STATUS:
        raise HTTPException(status_code=409, detail={"code": "membership_exists"})
    if membership is None:
        membership = OrganizationMembershipDB(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            user_id=target.id,
            role=role,
            status=ACTIVE_STATUS,
            created_at=now,
            updated_at=now,
        )
        db.add(membership)
    else:
        membership.role = role
        membership.status = ACTIVE_STATUS
        membership.updated_at = now
    record_organization_audit(
        db,
        principal,
        action="membership.invited",
        target_type="membership",
        target_id=membership.id,
        metadata={"user_id": target.id, "role": role},
    )
    db.commit()
    db.refresh(membership)
    return _public_membership(membership, target)


@router.patch("/{organization_id}/memberships/{membership_id}")
def change_membership_role(
    organization_id: str,
    membership_id: str,
    data: MembershipRoleChange,
    principal: OrganizationPrincipal = Depends(require_org_admin),
    db: Session = Depends(get_db),
):
    _require_path_org(organization_id, principal)
    role = _normalize_role(data.role)
    membership = db.query(OrganizationMembershipDB).filter(
        OrganizationMembershipDB.id == membership_id,
        OrganizationMembershipDB.organization_id == organization_id,
    ).with_for_update().first()
    if membership is None:
        raise _not_found("membership_not_found")
    _assert_can_manage_role(
        principal,
        current_role=membership.role,
        requested_role=role,
    )
    _assert_not_last_owner(db, membership, requested_role=role)
    previous_role = membership.role
    membership.role = role
    membership.updated_at = datetime.now(timezone.utc)
    record_organization_audit(
        db,
        principal,
        action="membership.role_changed",
        target_type="membership",
        target_id=membership.id,
        metadata={"from": previous_role, "to": role, "user_id": membership.user_id},
    )
    db.commit()
    user = db.get(UserDB, membership.user_id)
    return _public_membership(membership, user)


@router.post("/{organization_id}/memberships/{membership_id}/suspend")
def suspend_membership(
    organization_id: str,
    membership_id: str,
    principal: OrganizationPrincipal = Depends(require_org_admin),
    db: Session = Depends(get_db),
):
    _require_path_org(organization_id, principal)
    membership = db.query(OrganizationMembershipDB).filter(
        OrganizationMembershipDB.id == membership_id,
        OrganizationMembershipDB.organization_id == organization_id,
    ).with_for_update().first()
    if membership is None:
        raise _not_found("membership_not_found")
    _assert_can_manage_role(
        principal,
        current_role=membership.role,
        requested_role=None,
    )
    if membership.user_id == principal.user_id:
        raise HTTPException(status_code=409, detail={"code": "self_suspend_not_allowed"})
    _assert_not_last_owner(db, membership, requested_role=None)
    now = datetime.now(timezone.utc)
    membership.status = "suspended"
    membership.updated_at = now
    revoked_keys = _revoke_member_created_keys(
        db,
        organization_id=organization_id,
        user_id=membership.user_id,
        now=now,
    )
    record_organization_audit(
        db,
        principal,
        action="membership.suspended",
        target_type="membership",
        target_id=membership.id,
        metadata={"user_id": membership.user_id, "revoked_api_keys": revoked_keys},
    )
    db.commit()
    user = db.get(UserDB, membership.user_id)
    return _public_membership(membership, user)
