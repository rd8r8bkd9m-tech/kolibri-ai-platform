import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import ai_provider, auth as auth_module, response_store
from app.auth import create_access_token
from app.browser_session import issue_anonymous_session
from app.database import Base, get_db
from app.main import app
from app.models import (
    DocumentDB,
    EstimateDB,
    OrganizationAuditEventDB,
    OrganizationMembershipDB,
    ProjectDB,
    ProjectMessageDB,
    PublicApiKeyDB,
    PublicResponseDB,
    UserDB,
)
from app.organization_auth import ensure_personal_organization
from app.project_handoff import AnonymousAdoptionUnsupported, adopt_anonymous_roots


@pytest.fixture()
def organization_client(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        with testing_session() as db:
            yield db

    owner_token = "legacy-owner-token"
    monkeypatch.setenv(
        "KOLIBRI_OWNER_API_ADMIN_TOKEN_SHA256",
        hashlib.sha256(owner_token.encode()).hexdigest(),
    )
    monkeypatch.delenv("KOLIBRI_PUBLIC_API_KEY_SHA256", raising=False)
    monkeypatch.setattr(
        auth_module,
        "SECRET_KEY",
        "organization-integration-jwt-secret-0123456789abcdef",
    )
    with testing_session() as db:
        users = []
        for user_id in ("org-owner", "org-member"):
            user = UserDB(
                id=user_id,
                email=f"{user_id}@example.test",
                name=user_id,
                hashed_password="not-used",
                role="user",
                is_active=True,
            )
            db.add(user)
            db.flush()
            ensure_personal_organization(db, user)
            users.append(user)
        db.commit()
        personal_ids = {user.id: user.default_organization_id for user in users}

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        client.testing_session = testing_session
        client.owner_auth = {
            "Authorization": f"Bearer {create_access_token({'sub': 'org-owner'})}"
        }
        client.member_auth = {
            "Authorization": f"Bearer {create_access_token({'sub': 'org-member'})}"
        }
        client.personal_ids = personal_ids
        client.legacy_owner_headers = {"X-Kolibri-Owner-Token": owner_token}
        yield client
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _create_company(client: TestClient) -> str:
    created = client.post(
        "/api/v1/organizations",
        headers=client.owner_auth,
        json={"name": "Строй Контур", "slug": "stroy-kontur"},
    )
    assert created.status_code == 201
    return created.json()["id"]


def test_selected_org_cookie_binds_new_roots_and_wrong_selected_org_is_404(
    organization_client,
):
    client = organization_client
    company_id = _create_company(client)
    selected = client.post(
        f"/api/v1/organizations/{company_id}/select",
        headers=client.owner_auth,
    )
    assert selected.status_code == 200
    set_cookie = selected.headers["set-cookie"].lower()
    assert "kolibri_organization=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie

    project = client.post(
        "/api/v1/projects",
        headers=client.owner_auth,
        json={"title": "Компания"},
    )
    estimate = client.post(
        "/api/v1/estimates",
        headers=client.owner_auth,
        json={"title": "Смета компании"},
    )
    document = client.post(
        "/api/v1/documents",
        headers=client.owner_auth,
        json={"title": "Документ компании"},
    )
    assert (project.status_code, estimate.status_code, document.status_code) == (201, 201, 201)

    with client.testing_session() as db:
        company = db.get(ProjectDB, project.json()["id"])
        estimate_row = db.get(EstimateDB, estimate.json()["id"])
        document_row = db.get(DocumentDB, document.json()["id"])
        assert company.organization_id == company_id
        assert estimate_row.organization_id == company_id
        assert document_row.organization_id == company_id
        assert company.scope_id == estimate_row.scope_id == document_row.scope_id
        company_scope = company.scope_id
        assert company_scope == f"organization:{company_id}"

    wrong_org_headers = {
        **client.owner_auth,
        "X-Kolibri-Organization": client.personal_ids["org-owner"],
    }
    assert client.get(
        f"/api/v1/projects/{project.json()['id']}", headers=wrong_org_headers
    ).status_code == 404
    assert client.get(
        f"/api/v1/estimates/{estimate.json()['id']}", headers=wrong_org_headers
    ).status_code == 404
    assert client.get(
        f"/api/v1/documents/{document.json()['id']}", headers=wrong_org_headers
    ).status_code == 404


def test_membership_suspend_revokes_jwt_org_access_and_creator_api_keys(
    organization_client,
    monkeypatch,
):
    client = organization_client
    company_id = _create_company(client)
    owner_headers = {
        **client.owner_auth,
        "X-Kolibri-Organization": company_id,
    }
    invited = client.post(
        f"/api/v1/organizations/{company_id}/memberships",
        headers=owner_headers,
        json={"email": "org-member@example.test", "role": "member"},
    )
    assert invited.status_code == 201
    membership_id = invited.json()["id"]
    promoted = client.patch(
        f"/api/v1/organizations/{company_id}/memberships/{membership_id}",
        headers=owner_headers,
        json={"role": "admin"},
    )
    assert promoted.status_code == 200

    member_headers = {
        **client.member_auth,
        "X-Kolibri-Organization": company_id,
    }
    created_key = client.post(
        "/api/v1/developer/api-keys",
        headers=member_headers,
        json={"name": "Member automation"},
    )
    assert created_key.status_code == 201
    key = created_key.json()
    bearer = {"Authorization": f"Bearer {key['secret']}"}
    assert client.get("/v1/models", headers=bearer).status_code == 200
    async def fake_completion(messages, **kwargs):
        return {"content": "org response", "status": "completed", "provider": "test"}

    monkeypatch.setattr(ai_provider, "chat_completion", fake_completion)
    response = client.post(
        "/v1/responses",
        headers=bearer,
        json={"model": "kolibri", "input": "ping"},
    )
    assert response.status_code == 200
    with response_store.SessionLocal() as response_db:
        response_row = response_db.get(PublicResponseDB, response.json()["id"])
        assert response_row.organization_id == company_id
        assert response_row.owner_scope == f"organization:{company_id}"

    suspended = client.post(
        f"/api/v1/organizations/{company_id}/memberships/{membership_id}/suspend",
        headers=owner_headers,
    )
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "suspended"
    assert client.get("/api/v1/projects", headers=member_headers).status_code == 403
    denied_key = client.get("/v1/models", headers=bearer)
    assert denied_key.status_code == 401
    assert denied_key.json()["error"]["code"] == "invalid_api_key"

    with client.testing_session() as db:
        key_row = db.get(PublicApiKeyDB, key["id"])
        assert key_row.organization_id == company_id
        assert key_row.owner_scope == f"organization:{company_id}"
        assert key_row.revoked_at is not None
        assert db.query(OrganizationAuditEventDB).filter_by(
            organization_id=company_id,
            action="membership.suspended",
        ).count() == 1


def test_legacy_platform_api_keys_remain_outside_org_lists(organization_client):
    client = organization_client
    company_id = _create_company(client)
    company_headers = {
        **client.owner_auth,
        "X-Kolibri-Organization": company_id,
    }
    company_key = client.post(
        "/api/v1/developer/api-keys",
        headers=company_headers,
        json={"name": "Company key"},
    ).json()
    legacy_key = client.post(
        "/v1/api-keys",
        headers=client.legacy_owner_headers,
        json={"name": "Platform key"},
    )
    assert legacy_key.status_code == 201
    browser_ids = {
        item["id"]
        for item in client.get(
            "/api/v1/developer/api-keys", headers=company_headers
        ).json()["data"]
    }
    legacy_ids = {
        item["id"]
        for item in client.get(
            "/v1/api-keys", headers=client.legacy_owner_headers
        ).json()["data"]
    }
    assert company_key["id"] in browser_ids
    assert legacy_key.json()["id"] not in browser_ids
    assert legacy_key.json()["id"] in legacy_ids
    assert company_key["id"] not in legacy_ids


def test_anonymous_root_adoption_is_atomic_and_cas_fails_closed():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    testing_session = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(bind=engine)
    token, anonymous = issue_anonymous_session(sid="a" * 48)
    with testing_session() as db:
        user = UserDB(
            id="adoption-user",
            email="adoption@example.test",
            name="Adoption",
            hashed_password="unused",
            role="user",
            is_active=True,
        )
        db.add(user)
        db.flush()
        organization = ensure_personal_organization(db, user)
        db.add_all([
            ProjectDB(id="adopt-project", scope_id=anonymous.scope_id, title="P"),
            EstimateDB(id="adopt-estimate", scope_id=anonymous.scope_id, title="E"),
            DocumentDB(id="adopt-document", scope_id=anonymous.scope_id, title="D"),
            PublicResponseDB(
                id="adopt-response",
                owner_scope=anonymous.scope_id,
                status="completed",
                payload={},
            ),
        ])
        db.flush()
        counts = adopt_anonymous_roots(
            db,
            anonymous_cookie=token,
            target_scope_id=organization.data_scope_id,
            target_organization_id=organization.id,
            actor_user_id=user.id,
        )
        db.commit()
        assert counts == {"projects": 1, "estimates": 1, "documents": 1, "responses": 1}
        assert db.get(ProjectDB, "adopt-project").organization_id == organization.id
        assert db.get(PublicResponseDB, "adopt-response").owner_scope == organization.data_scope_id

        blocked_project = ProjectDB(
            id="blocked-project",
            scope_id=anonymous.scope_id,
            title="CAS",
        )
        db.add(blocked_project)
        db.flush()
        db.add(ProjectMessageDB(
            id="blocked-message",
            project_id=blocked_project.id,
            scope_id=anonymous.scope_id,
            sequence=1,
            role="assistant",
            content="file",
            status="completed",
            attributes={"artifact_id": "cas-bound-file"},
        ))
        db.commit()
        with pytest.raises(AnonymousAdoptionUnsupported):
            adopt_anonymous_roots(
                db,
                anonymous_cookie=token,
                target_scope_id=organization.data_scope_id,
                target_organization_id=organization.id,
                actor_user_id=user.id,
            )
        db.rollback()
        assert db.get(ProjectDB, "blocked-project").scope_id == anonymous.scope_id
    engine.dispose()
