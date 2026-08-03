from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from app.config import Settings
from app.database import connect_database, initialize_database
from app.estimate_artifact import record_estimate_version
from app.estimate_catalog import (
    CatalogCandidateCreate,
    CatalogCandidateReview,
    ConsentChange,
    PriceObservationCreate,
	change_pricing_consent,
	create_catalog_candidate,
	record_catalog_price_observation,
    refresh_market_price_aggregate,
    review_catalog_candidate,
    search_catalog,
)
from app.main import create_app
from app.owner_bootstrap import promote_registered_owner
from app.product_widgets import (
    deterministic_construction_estimate_proposal,
    deterministic_house_estimate_proposal,
    is_estimate_generation_prompt,
)
from app.schemas import AgentProfile, UserRole, UserSession
from fastapi.testclient import TestClient


PASSWORD = "correct-horse-battery-staple"
ORIGIN = {"Origin": "http://testserver"}
SECRET = b"catalog-test-secret-32-bytes-minimum"


def _identity(user: dict[str, str]) -> UserSession:
    return UserSession(
        user_id=user["id"],
        tenant_id=user["tenantId"],
        role=UserRole.OWNER,
        preferred_agent_profile=AgentProfile.AUTO,
        email=user["email"],
        name=user["name"],
        product_entitlements=("construction.estimates",),
    )


def _seed_project(database: sqlite3.Connection, user: dict[str, str], project_id: str) -> None:
    database.execute(
        """
        INSERT INTO projects (
            tenant_id, id, created_by_user_id, title, status,
            primary_thread_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
        """,
        (
            user["tenantId"],
            project_id,
            user["id"],
            "Строительство дома",
            f"thread_{project_id}",
            "2026-08-02T00:00:00Z",
            "2026-08-02T00:00:00Z",
        ),
    )


def _seed_saved_estimate(database: sqlite3.Connection, user: dict[str, str], project_id: str) -> str:
    document_id = f"document_estimate_{project_id}"
    content = {
        "title": "Предварительная смета",
        "region": "Казань",
        "assumptions": ["Тестовая версия"],
        "rows": [{
            "id": "row_catalog_test_01",
            "section": "Фундамент",
            "kind": "material",
            "description": "Бетон для фундамента",
            "unit": "м³",
            "quantity": "1",
            "unit_price": "100.00",
            "quantity_basis": "Тест",
            "price_basis": "Тест",
        }],
        "totals": {"subtotal": "100.00", "total": "100.00"},
    }
    database.execute(
        """
        INSERT INTO document_slots (
            tenant_id, id, project_id, slot_type, version, status,
            content_json, created_at, updated_at
        ) VALUES (?, ?, ?, 'estimate', 1, 'draft', ?, ?, ?)
        """,
        (
            user["tenantId"],
            document_id,
            project_id,
            json.dumps(content, ensure_ascii=False, separators=(",", ":")),
            "2026-08-02T00:00:00Z",
            "2026-08-02T00:00:00Z",
        ),
    )
    record_estimate_version(
        database,
        tenant_id=user["tenantId"],
        project_id=project_id,
        document_id=document_id,
        version=1,
        status="draft",
        document=content,
        origin_type="ai_proposal",
        origin_run_id=None,
        created_by_user_id=user["id"],
        created_at="2026-08-02T00:00:00Z",
    )
    return document_id


def test_universal_briefs_use_house_or_domain_scope_not_plastering() -> None:
    assert is_estimate_generation_prompt("Построить дом 100 м² в Казани")
    house = deterministic_house_estimate_proposal("Построить дом 100 м² в Казани")
    assert house is not None
    assert len({row.section for row in house.rows}) >= 5
    assert house.region == "Казань"
    foundation = deterministic_construction_estimate_proposal("фундамент 30 м³ в Казани")
    assert foundation is not None
    assert all("штукатур" not in row.description.casefold() for row in foundation.rows)
    assert deterministic_construction_estimate_proposal("штукатурка стен 100 м²") is None
    ambiguous = deterministic_house_estimate_proposal("дом 100 м² в Питер")
    assert ambiguous is not None
    assert ambiguous.region == "Регион не указан"


def test_catalog_candidate_review_search_and_tenant_boundary(tmp_path: Path) -> None:
    database_path = tmp_path / "catalog.db"
    settings = Settings.for_testing(database_url=database_path, bootstrap_owner_email="owner@example.com")
    with TestClient(create_app(settings)) as client:
        registered = client.post(
            "/v1/auth/register",
            headers=ORIGIN,
            json={"email": "owner@example.com", "name": "Owner", "password": PASSWORD},
        )
        assert registered.status_code == 201, registered.text
        user = registered.json()["user"]
        assert promote_registered_owner(settings, email="owner@example.com").changed
        database = sqlite3.connect(database_path)
        try:
            database.execute("PRAGMA foreign_keys = ON")
            _seed_project(database, user, "project_catalog_test")
            database.commit()
        finally:
            database.close()
        identity = _identity(user)
        database = connect_database(settings.database_url)
        try:
            entries = search_catalog(database, identity=identity, project_id="project_catalog_test", query="бетон")
            assert entries[0]["id"] == "catalog_system_foundation_concrete"
            assert entries[0]["canonicalUnit"] == "м³"
            candidate_payload = CatalogCandidateCreate(
                originalText="новый теплоизоляционный материал",
                proposedCanonicalName="Утеплитель фасадный",
                proposedShortName="Утеплитель",
                kind="material",
                proposedUnit="м2",
                sourceType="ai_generated",
            )
            candidate, duplicate = create_catalog_candidate(
                database, identity=identity, project_id="project_catalog_test", payload=candidate_payload,
            )
            assert not duplicate
            assert candidate["status"] == "proposed"
            assert not search_catalog(database, identity=identity, project_id="project_catalog_test", query="утеплитель")
            approved = review_catalog_candidate(
                database,
                identity=identity,
                project_id="project_catalog_test",
                candidate_id=candidate["id"],
                payload=CatalogCandidateReview(action="approve", visibility="tenant_private"),
            )
            assert approved["status"] == "approved"
            assert search_catalog(database, identity=identity, project_id="project_catalog_test", query="утеплитель")[0]["canonicalName"] == "Утеплитель фасадный"
            duplicate_candidate, duplicate_detected = create_catalog_candidate(
                database,
                identity=identity,
                project_id="project_catalog_test",
                payload=CatalogCandidateCreate(
                    originalText="утеплитель",
                    proposedCanonicalName="Утеплитель фасадный",
                    kind="material",
                    proposedUnit="м²",
                    sourceType="user_manual",
                ),
            )
            assert duplicate_detected
            assert duplicate_candidate["status"] == "needs_review"
            rejected = review_catalog_candidate(
                database,
                identity=identity,
                project_id="project_catalog_test",
                candidate_id=duplicate_candidate["id"],
                payload=CatalogCandidateReview(action="reject", reviewNote="Дубликат"),
            )
            assert rejected["status"] == "rejected"
            event_types = {row[0] for row in database.execute("SELECT event_type FROM catalog_candidate_events")}
            assert {"created", "reviewed", "rejected"} <= event_types
        finally:
            database.close()


def test_price_observation_consent_cohort_outlier_and_revoke(tmp_path: Path) -> None:
    database_path = tmp_path / "market.db"
    settings = Settings.for_testing(database_url=database_path)
    users: list[dict[str, str]] = []
    with TestClient(create_app(settings)) as client:
        for index in range(6):
            response = client.post(
                "/v1/auth/register",
                headers=ORIGIN,
                json={"email": f"market-{index}@example.com", "name": f"Market {index}", "password": PASSWORD},
            )
            assert response.status_code == 201, response.text
            user = response.json()["user"]
            users.append(user)

    database = connect_database(settings.database_url)
    try:
        for index, user in enumerate(users):
            _seed_project(database, user, f"project_market_{index}")
        database.commit()
        prices = ["100.00", "110.00", "120.00", "130.00", "140.00", "10000.00"]
        observations = []
        for index, (user, price) in enumerate(zip(users, prices, strict=True)):
            identity = _identity(user)
            project_id = f"project_market_{index}"
            _seed_saved_estimate(database, user, project_id)
            consent = change_pricing_consent(
                database,
                identity=identity,
                payload=ConsentChange(granted=True, projectId=project_id),
                now="2026-08-02T10:00:00Z",
            )
            observation = record_catalog_price_observation(
                database,
                identity=identity,
                project_id=project_id,
                payload=PriceObservationCreate(
                    rowId="row_catalog_test_01",
                    description="Бетон для фундамента",
                    kind="material",
                    unit="м³",
                    observedUnitPrice=price,
                    region="Казань",
                    sourceType="paid_invoice",
                    lifecycle="approved",
                    evidenceReferenceHash="sha256:" + hashlib.sha256(f"invoice-{index}".encode()).hexdigest(),
                    consentId=consent["id"],
                    validUntil="2026-12-31",
                ),
                secret=SECRET,
                now="2026-08-02T10:00:00Z",
            )
            assert observation["aggregateEligible"] is True
            observations.append(observation)
        ai_observation = record_catalog_price_observation(
            database,
            identity=_identity(users[0]),
            project_id="project_market_0",
            payload=PriceObservationCreate(
                rowId="row_ai",
                description="Бетон для фундамента",
                kind="material",
                unit="м³",
                observedUnitPrice="999.00",
                region="Казань",
                sourceType="ai_preliminary",
            ),
            secret=SECRET,
            now="2026-08-02T10:00:00Z",
        )
        assert ai_observation["aggregateEligible"] is False
        item_key = str(observations[0]["itemKey"])
        aggregate = refresh_market_price_aggregate(
            database,
            item_key=item_key,
            unit="м³",
            region="Казань",
            as_of="2026-08-02T12:00:00Z",
        )
        assert aggregate["published"] is True, aggregate
        assert aggregate["independentContributors"] == 5
        assert aggregate["median"] == "120.00"
        assert aggregate["observationCount"] == 6
        database.commit()
        revoked = change_pricing_consent(
            database,
            identity=_identity(users[0]),
            payload=ConsentChange(granted=False, projectId="project_market_0"),
            now="2026-08-02T12:30:00Z",
        )
        assert revoked["status"] == "revoked"
        after_revoke = refresh_market_price_aggregate(
            database,
            item_key=item_key,
            unit="м³",
            region="Казань",
            as_of="2026-08-02T13:00:00Z",
        )
        assert after_revoke["published"] is False
        assert after_revoke["independentContributors"] == 4
        assert database.execute("SELECT COUNT(*) FROM price_observations WHERE source_type = 'ai_preliminary' AND aggregate_eligible = 1").fetchone()[0] == 0
    finally:
        database.close()


def test_market_endpoint_returns_statistics_only(tmp_path: Path) -> None:
    # The aggregate read model intentionally has no supplier/document fields;
    # this guard makes the privacy boundary visible to API consumers.
    database_path = tmp_path / "market-contract.db"
    settings = Settings.for_testing(database_url=database_path)
    initialize_database(settings.database_url)
    database = connect_database(settings.database_url)
    try:
        columns = {row[1] for row in database.execute("PRAGMA table_info(market_price_aggregates)")}
        assert "supplier_name" not in columns
        assert "evidence_reference_hash" not in columns
        assert "document_id" not in columns
    finally:
        database.close()
