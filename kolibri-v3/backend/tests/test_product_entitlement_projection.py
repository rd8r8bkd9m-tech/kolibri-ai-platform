from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from app.config import Settings
from app.main import create_app
from app.owner_bootstrap import promote_registered_owner
from app.product_entitlements import (
    CONSTRUCTION_ESTIMATES_CAPABILITY,
    CONSTRUCTION_ESTIMATES_ENTITLEMENT,
)
from fastapi.testclient import TestClient

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"
DEVICE = {
    "platform": "ios",
    "deviceName": "Entitlement test iPhone",
    "appVersion": "1.0.0",
}


def _settings(database_path: Path) -> Settings:
    return Settings.for_testing(
        database_url=database_path,
        bootstrap_owner_email="owner@example.com",
    )


def _register(
    client: TestClient,
    *,
    email: str,
    name: str,
) -> dict[str, object]:
    response = client.post(
        "/v1/auth/register",
        headers=ORIGIN,
        json={
            "email": email,
            "name": name,
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]


def test_projection_is_deny_by_default_and_owner_bootstrap_is_server_owned(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "product-entitlements.db"
    settings = _settings(database_path)
    app = create_app(settings)

    with TestClient(app) as browser:
        owner = _register(
            browser,
            email="owner@example.com",
            name="Owner",
        )
        before = browser.get("/v1/session").json()["user"]
        assert before["capabilities"] == ["chat.use"]
        assert before["entitlements"] == []

        promoted = promote_registered_owner(
            settings,
            email="owner@example.com",
        )
        assert promoted.changed is True

        projected = browser.get("/v1/session")
        assert projected.status_code == 200
        subject = projected.json()["user"]
        assert subject["id"] == owner["id"]
        assert CONSTRUCTION_ESTIMATES_CAPABILITY in subject["capabilities"]
        assert subject["entitlements"] == [
            CONSTRUCTION_ESTIMATES_ENTITLEMENT
        ]

    with TestClient(app) as native:
        issued = native.post(
            "/v1/mobile/auth/login",
            json={
                "email": "owner@example.com",
                "password": PASSWORD,
                "device": DEVICE,
                # Client-controlled claims are not part of the input contract.
                "capabilities": ["platform.admin"],
                "entitlements": ["construction.estimates.use"],
            },
        )
        assert issued.status_code == 422

        issued = native.post(
            "/v1/mobile/auth/login",
            json={
                "email": "owner@example.com",
                "password": PASSWORD,
                "device": DEVICE,
            },
        )
        assert issued.status_code == 200
        token_view = issued.json()
        mobile_user = token_view["user"]
        assert CONSTRUCTION_ESTIMATES_CAPABILITY in mobile_user["capabilities"]
        assert mobile_user["entitlements"] == [
            CONSTRUCTION_ESTIMATES_ENTITLEMENT
        ]
        assert mobile_user["capabilities"] == subject["capabilities"]
        assert mobile_user["entitlements"] == subject["entitlements"]

        refreshed = native.post(
            "/v1/mobile/auth/refresh",
            json={"refreshToken": token_view["refreshToken"]},
        )
        assert refreshed.status_code == 200
        refreshed_view = refreshed.json()
        assert (
            refreshed_view["user"]["capabilities"]
            == subject["capabilities"]
        )
        assert refreshed_view["user"]["entitlements"] == subject["entitlements"]

        bearer_session = native.get(
            "/v1/mobile/auth/session",
            headers={
                "Authorization": (
                    f"Bearer {refreshed_view['accessToken']}"
                )
            },
        )
        assert bearer_session.status_code == 200
        assert (
            bearer_session.json()["user"]["capabilities"]
            == subject["capabilities"]
        )
        assert (
            bearer_session.json()["user"]["entitlements"]
            == subject["entitlements"]
        )

        ordinary = native.post(
            "/v1/mobile/auth/register",
            json={
                "email": "member@example.com",
                "name": "Ordinary member",
                "password": PASSWORD,
                "device": {
                    **DEVICE,
                    "deviceName": "Member iPhone",
                },
            },
        )
        assert ordinary.status_code == 201
        assert ordinary.json()["user"]["capabilities"] == ["chat.use"]
        assert ordinary.json()["user"]["entitlements"] == []

    database = sqlite3.connect(database_path)
    try:
        row = database.execute(
            """
            SELECT tenant_id, user_id, entitlement_code, status,
                   grant_epoch, source
            FROM product_entitlement_grants
            """
        ).fetchone()
        assert row == (
            owner["tenantId"],
            owner["id"],
            CONSTRUCTION_ESTIMATES_ENTITLEMENT,
            "active",
            1,
            "trusted_server_operator",
        )
    finally:
        database.close()


def test_projection_is_exactly_tenant_user_scoped_and_revocation_is_live(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "product-entitlement-scope.db"
    settings = _settings(database_path)
    app = create_app(settings)

    with TestClient(app) as client:
        owner = _register(
            client,
            email="owner@example.com",
            name="Owner",
        )
        promote_registered_owner(settings, email="owner@example.com")

        database = sqlite3.connect(database_path)
        try:
            database.execute(
                """
                UPDATE product_entitlement_grants
                SET status = 'revoked',
                    grant_epoch = grant_epoch + 1,
                    updated_at = unixepoch()
                WHERE tenant_id = ? AND user_id = ?
                  AND entitlement_code = ?
                """,
                (
                    owner["tenantId"],
                    owner["id"],
                    CONSTRUCTION_ESTIMATES_ENTITLEMENT,
                ),
            )
            database.commit()
        finally:
            database.close()

        revoked = client.get("/v1/session").json()["user"]
        assert CONSTRUCTION_ESTIMATES_CAPABILITY not in revoked["capabilities"]
        assert revoked["entitlements"] == []

        # Trusted server bootstrap can explicitly re-grant with the next epoch.
        promoted = promote_registered_owner(
            settings,
            email="owner@example.com",
        )
        assert promoted.changed is True
        restored = client.get("/v1/session").json()["user"]
        assert CONSTRUCTION_ESTIMATES_CAPABILITY in restored["capabilities"]
        assert restored["entitlements"] == [
            CONSTRUCTION_ESTIMATES_ENTITLEMENT
        ]

    database = sqlite3.connect(database_path)
    try:
        grant = database.execute(
            """
            SELECT status, grant_epoch, source
            FROM product_entitlement_grants
            """
        ).fetchone()
        assert grant == ("active", 3, "trusted_server_operator")

        with pytest.raises(
            sqlite3.IntegrityError,
            match="product entitlement update requires next epoch",
        ):
            database.execute(
                """
                UPDATE product_entitlement_grants
                SET status = 'revoked'
                """
            )
        with pytest.raises(
            sqlite3.IntegrityError,
            match="product entitlement scope is immutable",
        ):
            database.execute(
                """
                UPDATE product_entitlement_grants
                SET user_id = 'user_other',
                    grant_epoch = grant_epoch + 1
                """
            )
    finally:
        database.close()


def test_platform_owner_can_grant_and_revoke_customer_entitlement_live(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "product-entitlement-control.db"
    settings = _settings(database_path)
    app = create_app(settings)

    with TestClient(app) as client:
        _register(client, email="owner@example.com", name="Owner")
        promote_registered_owner(settings, email="owner@example.com")
        csrf = str(client.cookies.get("kolibri_v3_csrf"))
        owner_headers = {**ORIGIN, "X-CSRF-Token": csrf}

        registered = client.post(
            "/v1/mobile/auth/register",
            json={
                "email": "customer@example.com",
                "name": "Customer",
                "password": PASSWORD,
                "device": {
                    **DEVICE,
                    "deviceName": "Customer iPhone",
                },
            },
        )
        assert registered.status_code == 201
        customer = registered.json()
        customer_id = customer["user"]["id"]
        customer_bearer = {
            "Authorization": f"Bearer {customer['accessToken']}"
        }

        denied = client.get("/v1/documents", headers=customer_bearer)
        assert denied.status_code == 403
        assert denied.json()["code"] == "product_entitlement_required"

        entitlement_url = (
            f"/v1/platform-admin/users/{customer_id}/entitlements/"
            f"{CONSTRUCTION_ESTIMATES_ENTITLEMENT}"
        )
        unassigned = client.get(entitlement_url)
        assert unassigned.status_code == 200
        assert unassigned.json()["status"] == "unassigned"
        assert unassigned.json()["grantEpoch"] == 0

        arbitrary = client.get(
            (
                f"/v1/platform-admin/users/{customer_id}/entitlements/"
                "construction.estimates.admin"
            )
        )
        assert arbitrary.status_code == 404
        assert arbitrary.json()["code"] == "product_entitlement_not_found"

        self_grant = client.patch(
            entitlement_url,
            headers=customer_bearer,
            json={"expectedEpoch": 0, "status": "active"},
        )
        assert self_grant.status_code == 403
        assert self_grant.json()["code"] == "owner_required"

        granted = client.patch(
            entitlement_url,
            headers=owner_headers,
            json={"expectedEpoch": 0, "status": "active"},
        )
        assert granted.status_code == 200
        assert granted.json()["changed"] is True
        assert granted.json()["status"] == "active"
        assert granted.json()["grantEpoch"] == 1
        assert granted.json()["source"] == "platform_admin"

        projected = client.get(
            "/v1/mobile/auth/session",
            headers=customer_bearer,
        )
        assert projected.status_code == 200
        assert projected.json()["user"]["entitlements"] == [
            CONSTRUCTION_ESTIMATES_ENTITLEMENT
        ]
        assert CONSTRUCTION_ESTIMATES_CAPABILITY in (
            projected.json()["user"]["capabilities"]
        )
        assert client.get(
            "/v1/documents",
            headers=customer_bearer,
        ).status_code == 200

        stale = client.patch(
            entitlement_url,
            headers=owner_headers,
            json={"expectedEpoch": 0, "status": "revoked"},
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "product_entitlement_epoch_conflict"

        revoked = client.patch(
            entitlement_url,
            headers=owner_headers,
            json={"expectedEpoch": 1, "status": "revoked"},
        )
        assert revoked.status_code == 200
        assert revoked.json()["status"] == "revoked"
        assert revoked.json()["grantEpoch"] == 2
        denied_again = client.get("/v1/documents", headers=customer_bearer)
        assert denied_again.status_code == 403
        assert denied_again.json()["code"] == "product_entitlement_required"

        restored = client.patch(
            entitlement_url,
            headers=owner_headers,
            json={"expectedEpoch": 2, "status": "active"},
        )
        assert restored.status_code == 200
        assert restored.json()["grantEpoch"] == 3
        assert client.get(
            "/v1/documents",
            headers=customer_bearer,
        ).status_code == 200

        audit = client.get("/v1/platform-admin/audit?limit=100")
        actions = [
            item["action"]
            for item in audit.json()["items"]
            if item["targetId"] == customer_id
        ]
        assert sorted(actions) == [
            "user.product_entitlement.granted",
            "user.product_entitlement.granted",
            "user.product_entitlement.revoked",
        ]
