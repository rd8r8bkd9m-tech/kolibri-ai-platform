from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.browser_session import SESSION_COOKIE_NAME, issue_anonymous_session
from app.estimate_evidence import attest_price_evidence
from app.main import app
from app.storage import DBStorage


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        bootstrap = test_client.post("/api/v1/shell/bootstrap")
        assert bootstrap.status_code == 200, bootstrap.text
        yield test_client
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def price_evidence(
    *,
    price: str = "100",
    source_id: str = "fgiscs:item:W-001",
    position_code: str = "W-001",
    content_sha256: str = "a" * 64,
    attested: bool = True,
) -> dict:
    now = datetime.now(timezone.utc)
    record = {
        "position_code": position_code,
        "source_id": source_id,
        "url": f"https://fgiscs.minstroyrf.ru/prices/{position_code}",
        "source_title": f"ФГИС ЦС — ресурс {position_code}",
        "source_type": "official_catalog",
        "region": "Республика Татарстан",
        "observed_at": now.isoformat().replace("+00:00", "Z"),
        "price_date": now.date().isoformat(),
        "unit": "м²",
        "vat_status": "included",
        "quote": f"Цена ресурса {price} руб./м², НДС включён",
        "unit_price": price,
        "currency": "RUB",
        "content_sha256": content_sha256,
        "verification": "verified",
    }
    return attest_price_evidence(record) if attested else record


def estimate_payload(*, price: str = "100", evidence: dict | None = None) -> dict:
    evidence = evidence or price_evidence(price=price)
    return {
        "title": "Смета: одноэтажный дом 100 м² — Лениногорск",
        "client": "Владелец",
        "object_name": "Одноэтажный дом 100 м²",
        "region": "Лениногорск, Республика Татарстан",
        "currency": "RUB",
        "overhead_rate": "10",
        "vat_rate": "22",
        "scope_status": "verified",
        "source_note": "Объём подтверждён ведомостью; цена подтверждена ФГИС ЦС.",
        "assumptions": ["Площадь подготовки стен подтверждена ведомостью объёмов."],
        "questions": [],
        # The action contract deliberately transports the same record at both
        # levels. Persistence must store it once and must not create a false
        # duplicate-source issue.
        "price_sources": [evidence],
        "sections": [
            {
                "title": "Подготовительные работы",
                "positions": [
                    {
                        "code": "W-001",
                        "name": "Подготовка стен",
                        "unit": "м²",
                        "quantity": "2.5",
                        "price": price,
                        "source": "untrusted display label",
                        "price_evidence": [evidence],
                        "comment": "По ведомости объёмов",
                    }
                ],
            }
        ],
    }


def test_truth_and_price_evidence_round_trip_through_crud_revision_and_duplicate(
    client: TestClient,
):
    evidence = price_evidence()
    created_response = client.post(
        "/api/v1/estimates", json=estimate_payload(evidence=evidence)
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    estimate_id = created["id"]

    assert created["status"] == "draft"
    assert created["estimate_status"] == "source_backed"
    assert created["pricing_status"] == "verified"
    assert created["scope_status"] == "unverified"
    assert created["subtotal"] == "250.00"
    assert created["total"] == "335.50"
    assert created["evidence_issues"] == []
    assert created["price_sources"] == [evidence]
    position = created["sections"][0]["positions"][0]
    assert position["price_evidence"] == created["price_sources"]
    assert position["source"] == evidence["url"]

    fetched = client.get(f"/api/v1/estimates/{estimate_id}")
    assert fetched.status_code == 200
    assert fetched.json() == created

    listed = client.get("/api/v1/estimates").json()
    assert listed["items"] == [created]

    revision = client.get(f"/api/v1/estimates/{estimate_id}/revisions/1")
    assert revision.status_code == 200, revision.text
    assert revision.json()["snapshot"] == created
    summary = client.get(f"/api/v1/estimates/{estimate_id}/revisions").json()["items"][0]
    assert summary["status"] == "draft"
    assert summary["estimate_status"] == "source_backed"
    assert summary["pricing_status"] == "verified"

    duplicate_response = client.post(f"/api/v1/estimates/{estimate_id}/duplicate")
    assert duplicate_response.status_code == 200, duplicate_response.text
    duplicate = duplicate_response.json()
    assert duplicate["id"] != estimate_id
    assert duplicate["status"] == "draft"
    assert duplicate["estimate_status"] == "source_backed"
    assert duplicate["pricing_status"] == "verified"
    assert duplicate["scope_status"] == "unverified"
    assert duplicate["price_sources"] == created["price_sources"]
    assert duplicate["sections"][0]["positions"][0]["price_evidence"] == position["price_evidence"]


def test_manual_price_edit_invalidates_evidence_and_requires_later_reverification(
    client: TestClient,
):
    stale_evidence = price_evidence(price="100")
    created = client.post(
        "/api/v1/estimates", json=estimate_payload(evidence=stale_evidence)
    ).json()
    estimate_id = created["id"]

    changed_payload = estimate_payload(price="120", evidence=stale_evidence)
    changed_response = client.put(
        f"/api/v1/estimates/{estimate_id}",
        headers={"If-Match": '"1"'},
        json={
            "scope_status": "verified",
            "price_sources": changed_payload["price_sources"],
            "sections": changed_payload["sections"],
        },
    )
    assert changed_response.status_code == 200, changed_response.text
    changed = changed_response.json()

    assert changed["status"] == "draft"
    assert changed["version"] == 2
    assert changed["pricing_status"] == "preliminary"
    assert changed["estimate_status"] == "preliminary"
    assert changed["scope_status"] == "unverified"
    assert changed["price_sources"] == []
    assert changed["sections"][0]["positions"][0]["source"] == ""
    assert changed["sections"][0]["positions"][0]["price_evidence"] == []
    assert any(issue["code"] == "manual_price_change" for issue in changed["evidence_issues"])
    assert "изменена вручную" in changed["source_note"].casefold()

    first_snapshot = client.get(
        f"/api/v1/estimates/{estimate_id}/revisions/1"
    ).json()["snapshot"]
    second_snapshot = client.get(
        f"/api/v1/estimates/{estimate_id}/revisions/2"
    ).json()["snapshot"]
    assert first_snapshot["pricing_status"] == "verified"
    assert first_snapshot["estimate_status"] == "source_backed"
    assert first_snapshot["price_sources"] == [stale_evidence]
    assert second_snapshot["pricing_status"] == "preliminary"
    assert second_snapshot["price_sources"] == []

    fresh_evidence = price_evidence(price="120", source_id="fgiscs:item:W-001:refresh")
    reverified_payload = estimate_payload(price="120", evidence=fresh_evidence)
    reverified_response = client.put(
        f"/api/v1/estimates/{estimate_id}",
        headers={"If-Match": '"2"'},
        json={
            "scope_status": "verified",
            "source_note": "Объём и обновлённая цена независимо проверены.",
            "price_sources": reverified_payload["price_sources"],
            "sections": reverified_payload["sections"],
        },
    )
    assert reverified_response.status_code == 200, reverified_response.text
    reverified = reverified_response.json()
    assert reverified["version"] == 3
    assert reverified["status"] == "draft"
    assert reverified["pricing_status"] == "verified"
    assert reverified["estimate_status"] == "source_backed"
    assert reverified["scope_status"] == "unverified"
    assert reverified["price_sources"] == [fresh_evidence]
    assert reverified["evidence_issues"] == []
    assert "объёмы и состав работ ещё не подтверждены" in reverified["source_note"]


def test_public_crud_cannot_self_promote_scope_or_unattested_evidence(
    client: TestClient,
):
    forged = price_evidence(attested=False)
    response = client.post(
        "/api/v1/estimates",
        json=estimate_payload(evidence=forged),
    )

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["scope_status"] == "unverified"
    assert created["pricing_status"] == "preliminary"
    assert created["estimate_status"] == "preliminary"
    assert created["price_sources"] == []
    assert created["sections"][0]["positions"][0]["price_evidence"] == []
    assert any(issue["code"] == "untrusted_evidence" for issue in created["evidence_issues"])

    promoted = client.put(
        f"/api/v1/estimates/{created['id']}",
        headers={"If-Match": '"1"'},
        json={"scope_status": "verified"},
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["scope_status"] == "unverified"


def test_estimate_crud_revisions_and_exports_are_isolated_by_browser_session(
    client: TestClient,
):
    owner_token = client.cookies.get(SESSION_COOKIE_NAME)
    assert owner_token
    created_response = client.post("/api/v1/estimates", json=estimate_payload())
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    estimate_id = created["id"]

    other_token, _other_session = issue_anonymous_session()
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE_NAME, other_token)

    listed = client.get("/api/v1/estimates")
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"] == []
    assert listed.json()["total"] == 0

    isolated_requests = [
        client.get(f"/api/v1/estimates/{estimate_id}"),
        client.put(
            f"/api/v1/estimates/{estimate_id}",
            headers={"If-Match": '"1"'},
            json={"title": "cross-session overwrite"},
        ),
        client.delete(f"/api/v1/estimates/{estimate_id}"),
        client.post(
            f"/api/v1/estimates/{estimate_id}/calculate",
            headers={"If-Match": '"1"'},
        ),
        client.post(f"/api/v1/estimates/{estimate_id}/duplicate"),
        client.get(f"/api/v1/estimates/{estimate_id}/revisions"),
        client.get(f"/api/v1/estimates/{estimate_id}/revisions/1"),
        client.get(f"/api/v1/estimates/{estimate_id}/pdf"),
        client.get(f"/api/v1/estimates/{estimate_id}/export/csv"),
        client.get(f"/api/v1/estimates/{estimate_id}/export/json"),
        client.get(f"/api/v1/estimates/{estimate_id}/export/xlsx"),
    ]
    assert [response.status_code for response in isolated_requests] == [404] * len(
        isolated_requests
    )

    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE_NAME, owner_token)
    owner_read = client.get(f"/api/v1/estimates/{estimate_id}")
    assert owner_read.status_code == 200, owner_read.text
    assert owner_read.json() == created


def test_signed_but_mismatched_evidence_zeroes_collector_bound_price(
    client: TestClient,
):
    evidence = price_evidence(price="100")
    response = client.post(
        "/api/v1/estimates",
        json=estimate_payload(price="120", evidence=evidence),
    )

    assert response.status_code == 201, response.text
    created = response.json()
    position = created["sections"][0]["positions"][0]
    assert position["price"] == "0.00"
    assert position["sum"] == "0.00"
    assert position["price_evidence"] == []
    assert created["total"] == "0.00"
    assert created["pricing_status"] == "needs_input"
    assert any(issue["code"] == "price_mismatch" for issue in created["evidence_issues"])


@pytest.mark.parametrize("mutation", ["add", "delete", "reorder"])
def test_layout_changes_downgrade_internally_verified_scope(mutation: str):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = testing_session()
    try:
        first = price_evidence()
        second = price_evidence(
            position_code="W-002",
            source_id="fgiscs:item:W-002",
            content_sha256="b" * 64,
        )
        payload = estimate_payload(evidence=first)
        payload["price_sources"] = [first, second]
        payload["sections"][0]["positions"].append({
            "code": "W-002",
            "name": "Грунтование стен",
            "unit": "м²",
            "quantity": "2.5",
            "price": "100",
            "source": second["url"],
            "price_evidence": [second],
            "comment": "По ведомости объёмов",
        })
        storage = DBStorage(db, scope_id="test:trusted")
        created = storage.create_estimate(payload, trusted_scope=True)
        assert created["scope_status"] == "verified"
        assert created["estimate_status"] == "verified"

        sections = copy.deepcopy(created["sections"])
        positions = sections[0]["positions"]
        if mutation == "add":
            positions.append({
                "code": "W-003",
                "name": "Новая работа",
                "unit": "м²",
                "quantity": "1",
                "price": "0",
                "source": "",
                "price_evidence": [],
                "comment": "",
            })
        elif mutation == "delete":
            positions.pop()
        else:
            positions.reverse()

        updated = storage.update_estimate(
            created["id"],
            {"scope_status": "verified", "sections": sections},
            expected_version=created["version"],
        )

        assert updated is not None
        assert updated["scope_status"] == "unverified"
        assert updated["estimate_status"] != "verified"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_invalid_price_evidence_is_rejected_at_crud_boundary(client: TestClient):
    invalid = price_evidence()
    invalid["provider_payload"] = "must never be persisted"
    response = client.post(
        "/api/v1/estimates",
        json=estimate_payload(evidence=invalid),
    )
    assert response.status_code == 422
    assert "provider_payload" in response.text
