from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import Settings
from app.database import migration_paths
from app.main import create_app
from app.normative_corpus import FetchedNormative
from app.owner_bootstrap import promote_registered_owner
from fastapi.testclient import TestClient

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"
LATEST_SCHEMA_VERSION = int(migration_paths()[-1].name.split("_", 1)[0])


class FixtureFetcher:
    def __init__(self, content: str) -> None:
        self.content = content.encode("utf-8")
        self.calls = 0

    def fetch(
        self,
        _database: sqlite3.Connection,
        *,
        url: str,
    ) -> FetchedNormative:
        self.calls += 1
        return FetchedNormative(
            content=self.content,
            media_type="text/plain",
            final_url=url,
            etag='"fixture-v1"',
            last_modified="Wed, 29 Jul 2026 00:00:00 GMT",
        )


def _settings(database_path: Path) -> Settings:
    return Settings.for_testing(
        database_url=database_path,
        bootstrap_owner_email="owner@example.com",
    )


def _register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/v1/auth/register",
        headers=ORIGIN,
        json={
            "email": email,
            "name": email.split("@", 1)[0],
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201
    return response.json()["user"]


def _headers(client: TestClient) -> dict[str, str]:
    csrf = client.cookies.get("kolibri_v3_csrf")
    assert csrf
    return {**ORIGIN, "X-CSRF-Token": csrf}


def _import_payload() -> dict[str, object]:
    return {
        "code": "СП 999.1325800.2026",
        "title": "Правила тестового производства штукатурных работ",
        "documentKind": "sp",
        "editionLabel": "2026, редакция 1",
        "jurisdiction": "RU",
        "authority": "Минстрой России",
        "authorityUrl": "https://minstroyrf.gov.ru",
        "sourceUrl": "https://minstroyrf.gov.ru/docs/test-sp-999.txt",
        "officialPublicationUrl": (
            "https://minstroyrf.gov.ru/docs/test-sp-999.txt"
        ),
        "effectiveFrom": "2026-01-01",
        "publishedOn": "2025-12-01",
        "applicability": {
            "workTypes": ["plastering"],
            "objectTypes": ["building"],
        },
        "metadata": {"fixture": True},
    }


def test_normative_corpus_import_search_versioning_and_tenant_read(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "normatives.db"
    settings = _settings(database_path)
    app = create_app(settings)
    fixture = FixtureFetcher(
        """
        1 Область применения
        Настоящий свод правил применяется к штукатурным работам.
        5.4 Подготовка основания
        Основание должно быть очищено. До нанесения состава выполняют
        грунтование, устанавливают маяки и защищают смежные поверхности.
        """
    )
    app.state.normative_fetcher = fixture
    with TestClient(app) as owner_client:
        owner = _register(owner_client, "owner@example.com")
        promote_registered_owner(settings, email="owner@example.com")

        imported = owner_client.post(
            "/v1/normatives/import-url",
            headers=_headers(owner_client),
            json=_import_payload(),
        )
        assert imported.status_code == 201, imported.text
        imported_body = imported.json()
        assert imported_body["status"] == "candidate"
        assert imported_body["duplicate"] is False
        assert imported_body["sectionCount"] >= 1
        edition_id = imported_body["editionId"]

        before_approval = owner_client.get(
            "/v1/normatives/search",
            params={"q": "грунтование маяки", "asOf": "2026-07-29"},
        )
        assert before_approval.status_code == 200
        assert before_approval.json()["results"] == []

        approved = owner_client.post(
            f"/v1/normatives/editions/{edition_id}/status",
            headers=_headers(owner_client),
            json={
                "status": "effective",
                "verificationNote": "Сверено с официальной публикацией.",
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "effective"

        found = owner_client.get(
            "/v1/normatives/search",
            params={"q": "грунтование маяки", "asOf": "2026-07-29"},
        )
        assert found.status_code == 200, found.text
        result = found.json()["results"][0]
        assert result["documentCode"] == "СП 999.1325800.2026"
        assert result["editionLabel"] == "2026, редакция 1"
        assert result["locator"].startswith("block:")
        assert "грунтование" in result["excerpt"]
        assert result["rawSha256"].startswith("sha256:")
        assert result["sectionSha256"].startswith("sha256:")
        assert result["sourceUrl"].startswith("https://minstroyrf.gov.ru/")
        assert result["status"] == "effective"

        before_effective_date = owner_client.get(
            "/v1/normatives/search",
            params={"q": "грунтование", "asOf": "2025-12-31"},
        )
        assert before_effective_date.status_code == 200
        assert before_effective_date.json()["results"] == []

        duplicate = owner_client.post(
            "/v1/normatives/import-url",
            headers=_headers(owner_client),
            json=_import_payload(),
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["duplicate"] is True
        assert duplicate.json()["editionId"] == edition_id

        listed = owner_client.get(
            "/v1/normatives/documents/СП 999.1325800.2026/editions"
        )
        assert listed.status_code == 200
        assert len(listed.json()["editions"]) == 1
        assert "rawContent" not in listed.text

        with TestClient(app) as other_tenant:
            reader = _register(other_tenant, "reader@example.com")
            denied_corpus = other_tenant.get(
                "/v1/normatives/search",
                params={"q": "подготовка основания", "asOf": "2026-07-29"},
            )
            assert denied_corpus.status_code == 403
            assert (
                denied_corpus.json()["code"]
                == "product_entitlement_required"
            )
            granted = owner_client.patch(
                (
                    f"/v1/platform-admin/users/{reader['id']}/entitlements/"
                    "construction.estimates.use"
                ),
                headers=_headers(owner_client),
                json={"expectedEpoch": 0, "status": "active"},
            )
            assert granted.status_code == 200, granted.text
            assert granted.json()["source"] == "platform_admin"
            shared_corpus = other_tenant.get(
                "/v1/normatives/search",
                params={"q": "подготовка основания", "asOf": "2026-07-29"},
            )
            assert shared_corpus.status_code == 200
            assert len(shared_corpus.json()["results"]) == 1
            forbidden = other_tenant.post(
                "/v1/normatives/import-url",
                headers=_headers(other_tenant),
                json=_import_payload(),
            )
            assert forbidden.status_code == 403
            assert forbidden.json()["code"] == "owner_required"

    database = sqlite3.connect(database_path)
    try:
        assert (
            database.execute("PRAGMA user_version").fetchone()[0]
            == LATEST_SCHEMA_VERSION
        )
        assert database.execute(
            "SELECT COUNT(*) FROM normative_editions"
        ).fetchone()[0] == 1
        assert database.execute(
            "SELECT COUNT(*) FROM normative_sections_fts"
        ).fetchone()[0] >= 1
        assert database.execute(
            "SELECT COUNT(*) FROM normative_audit_events"
        ).fetchone()[0] == 2
        raw_content = database.execute(
            "SELECT raw_content FROM normative_editions"
        ).fetchone()[0]
        assert isinstance(raw_content, bytes)
        assert len(raw_content) > 100
        assert owner["tenantId"] != ""
    finally:
        database.close()


def test_normative_import_rejects_unapproved_source_and_regular_user(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "normative-security.db"
    settings = _settings(database_path)
    app = create_app(settings)
    app.state.normative_fetcher = FixtureFetcher("Официальный тестовый текст")
    with TestClient(app) as client:
        _register(client, "owner@example.com")
        promote_registered_owner(settings, email="owner@example.com")

        payload = _import_payload()
        payload["sourceUrl"] = "https://example.com/fake-sp.pdf"
        rejected = client.post(
            "/v1/normatives/import-url",
            headers=_headers(client),
            json=payload,
        )
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "normative_import_rejected"

        database = sqlite3.connect(database_path)
        try:
            assert database.execute(
                "SELECT COUNT(*) FROM normative_editions"
            ).fetchone()[0] == 0
        finally:
            database.close()
