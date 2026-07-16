from datetime import datetime, timezone

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.database import Base, get_db
from app.models import (
    DocumentDB,
    EstimateDB,
    OrganizationAuditEventDB,
    OrganizationMembershipDB,
    ProjectDB,
    UserDB,
)
from app.organization_auth import (
    ORGANIZATION_HEADER,
    OrganizationPrincipal,
    ensure_personal_organization,
    require_org_admin,
    require_org_member,
    require_org_owner,
)
from app.project_history import ProjectHistoryRepository, ProjectNotFoundError
from app.storage import DBStorage


def _engine_and_sessionmaker():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _add_user(db: Session, user_id: str, *, platform_role: str = "user") -> UserDB:
    user = UserDB(
        id=user_id,
        email=f"{user_id}@example.test",
        name=f"User {user_id}",
        hashed_password="not-used",
        role=platform_role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    ensure_personal_organization(db, user)
    db.commit()
    db.refresh(user)
    return user


def test_personal_organization_provisioning_is_idempotent():
    engine, testing_session = _engine_and_sessionmaker()
    with testing_session() as db:
        user = _add_user(db, "user-1")
        first_id = user.default_organization_id
        ensure_personal_organization(db, user)
        ensure_personal_organization(db, user)
        db.commit()

        assert first_id is not None
        assert db.query(OrganizationMembershipDB).filter_by(
            organization_id=first_id,
            user_id=user.id,
        ).count() == 1
        membership = db.query(OrganizationMembershipDB).filter_by(
            organization_id=first_id,
            user_id=user.id,
        ).one()
        assert (membership.role, membership.status) == ("owner", "active")
        assert db.query(OrganizationAuditEventDB).filter_by(
            organization_id=first_id,
            action="organization.personal_created",
        ).count() == 1
    engine.dispose()


def test_org_roles_are_separate_from_platform_role_and_revocation_is_immediate():
    engine, testing_session = _engine_and_sessionmaker()
    with testing_session() as db:
        platform_owner = _add_user(db, "platform-owner", platform_role="owner")
        company_owner = _add_user(db, "company-owner", platform_role="user")
        company_id = company_owner.default_organization_id
        db.add(
            OrganizationMembershipDB(
                id="membership-platform-owner-company",
                organization_id=company_id,
                user_id=platform_owner.id,
                role="member",
                status="active",
            )
        )
        db.commit()

    api = FastAPI()

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    @api.get("/member")
    def member(principal: OrganizationPrincipal = Depends(require_org_member)):
        return principal

    @api.get("/admin")
    def admin(principal: OrganizationPrincipal = Depends(require_org_admin)):
        return principal

    @api.get("/owner")
    def owner(principal: OrganizationPrincipal = Depends(require_org_owner)):
        return principal

    api.dependency_overrides[get_db] = override_get_db
    platform_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': 'platform-owner'})}",
        ORGANIZATION_HEADER: company_id,
    }
    company_owner_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': 'company-owner'})}",
        ORGANIZATION_HEADER: company_id,
    }

    with TestClient(api) as client:
        member = client.get("/member", headers=platform_headers)
        assert member.status_code == 200
        assert member.json()["platform_role"] == "owner"
        assert member.json()["organization_role"] == "member"
        assert client.get("/admin", headers=platform_headers).status_code == 403
        assert client.get("/owner", headers=platform_headers).status_code == 403

        owner = client.get("/owner", headers=company_owner_headers)
        assert owner.status_code == 200
        assert owner.json()["platform_role"] == "user"
        assert owner.json()["organization_role"] == "owner"

        with testing_session() as db:
            membership = db.query(OrganizationMembershipDB).filter_by(
                organization_id=company_id,
                user_id="platform-owner",
            ).one()
            membership.role = "admin"
            db.commit()
        assert client.get("/admin", headers=platform_headers).status_code == 200
        assert client.get("/owner", headers=platform_headers).status_code == 403

        with testing_session() as db:
            membership = db.query(OrganizationMembershipDB).filter_by(
                organization_id=company_id,
                user_id="platform-owner",
            ).one()
            membership.status = "revoked"
            db.commit()
        revoked = client.get("/member", headers=platform_headers)
        assert revoked.status_code == 403
        assert revoked.json()["detail"]["code"] == "organization_access_denied"

        wrong_org = client.get(
            "/member",
            headers={
                "Authorization": platform_headers["Authorization"],
                ORGANIZATION_HEADER: "organization-not-owned",
            },
        )
        assert wrong_org.status_code == 403
    engine.dispose()


def test_organization_scope_keeps_projects_estimates_and_documents_cross_org_private():
    engine, testing_session = _engine_and_sessionmaker()
    now = datetime.now(timezone.utc)
    with testing_session() as db:
        user_a = _add_user(db, "user-a")
        user_b = _add_user(db, "user-b")
        org_a = db.query(OrganizationMembershipDB).filter_by(
            organization_id=user_a.default_organization_id,
            user_id=user_a.id,
        ).one().organization_id
        org_b = db.query(OrganizationMembershipDB).filter_by(
            organization_id=user_b.default_organization_id,
            user_id=user_b.id,
        ).one().organization_id
        scope_a = f"user:{user_a.id}"
        scope_b = f"user:{user_b.id}"
        db.add_all(
            [
                ProjectDB(
                    id="project-a",
                    scope_id=scope_a,
                    organization_id=org_a,
                    title="Project A",
                    title_source="manual",
                    status="active",
                    version=1,
                    message_count=0,
                    attributes={},
                    created_at=now,
                    updated_at=now,
                ),
                ProjectDB(
                    id="project-b",
                    scope_id=scope_b,
                    organization_id=org_b,
                    title="Project B",
                    title_source="manual",
                    status="active",
                    version=1,
                    message_count=0,
                    attributes={},
                    created_at=now,
                    updated_at=now,
                ),
                EstimateDB(
                    id="estimate-a",
                    scope_id=scope_a,
                    organization_id=org_a,
                    title="Estimate A",
                ),
                EstimateDB(
                    id="estimate-b",
                    scope_id=scope_b,
                    organization_id=org_b,
                    title="Estimate B",
                ),
                DocumentDB(
                    id="document-a",
                    scope_id=scope_a,
                    organization_id=org_a,
                    title="Document A",
                ),
                DocumentDB(
                    id="document-b",
                    scope_id=scope_b,
                    organization_id=org_b,
                    title="Document B",
                ),
            ]
        )
        db.commit()

        storage_a = DBStorage(db, scope_id=scope_a)
        assert storage_a.get_estimate("estimate-a")["title"] == "Estimate A"
        assert storage_a.get_estimate("estimate-b") is None
        assert storage_a.get_document("document-a")["title"] == "Document A"
        assert storage_a.get_document("document-b") is None
        assert ProjectHistoryRepository(db, scope_a).get_project("project-a")["id"] == "project-a"
        with pytest.raises(ProjectNotFoundError):
            ProjectHistoryRepository(db, scope_a).get_project("project-b")
    engine.dispose()
