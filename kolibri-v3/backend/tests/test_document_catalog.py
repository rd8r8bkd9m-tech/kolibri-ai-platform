from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.config import Settings
from app.main import create_app
from app.owner_bootstrap import promote_registered_owner
from fastapi.testclient import TestClient

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"


def _register(client: TestClient, *, email: str, name: str) -> dict[str, str]:
    response = client.post(
        "/v1/auth/register",
        headers=ORIGIN,
        json={"email": email, "name": name, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]


def _seed_project(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str,
    project_id: str,
    project_name: str,
) -> None:
    database.execute(
        """
        INSERT INTO projects (
            tenant_id, id, created_by_user_id, title, status,
            primary_thread_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
        """,
        (
            tenant_id,
            project_id,
            user_id,
            project_name,
            f"thread_{tenant_id[-12:]}_{project_id[-8:]}",
            "2026-08-01T09:00:00Z",
            "2026-08-01T09:00:00Z",
        ),
    )


def _seed_slot(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    document_id: str,
    slot_type: str,
    version: int,
    status: str,
    content: object | None,
    updated_at: str,
) -> None:
    database.execute(
        """
        INSERT INTO document_slots (
            tenant_id, id, project_id, slot_type, version, status,
            content_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, '2026-08-01T09:00:00Z', ?)
        """,
        (
            tenant_id,
            document_id,
            project_id,
            slot_type,
            version,
            status,
            (
                json.dumps(content, ensure_ascii=False, separators=(",", ":"))
                if content is not None
                else None
            ),
            updated_at,
        ),
    )


def test_catalog_lists_every_non_empty_slot_and_stays_tenant_scoped(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "document-catalog.db"
    settings = Settings.for_testing(
        database_url=database_path,
        bootstrap_owner_email="catalog-owner@example.com",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        foreign = _register(
            client,
            email="foreign-catalog@example.com",
            name="Foreign catalog user",
        )
        owner = _register(
            client,
            email="catalog-owner@example.com",
            name="Catalog owner",
        )
        promoted = promote_registered_owner(
            settings,
            email="catalog-owner@example.com",
        )
        assert promoted.changed is True

        project_id = "project_catalog_scope_01"
        empty_project_id = "project_catalog_empty_01"
        database = sqlite3.connect(database_path)
        try:
            database.execute("PRAGMA foreign_keys = ON")
            _seed_project(
                database,
                tenant_id=owner["tenantId"],
                user_id=owner["id"],
                project_id=project_id,
                project_name="Проект владельца",
            )
            _seed_project(
                database,
                tenant_id=owner["tenantId"],
                user_id=owner["id"],
                project_id=empty_project_id,
                project_name="Пустой проект",
            )
            _seed_project(
                database,
                tenant_id=foreign["tenantId"],
                user_id=foreign["id"],
                project_id=project_id,
                project_name="Чужой проект",
            )

            slots = [
                (
                    "document_catalog_source_01",
                    "source-data",
                    2,
                    "ready",
                    {"title": "ТЗ и результаты обмеров", "sections": [1, 2]},
                    "2026-08-01T13:04:00Z",
                ),
                (
                    "document_catalog_estimate_01",
                    "estimate",
                    3,
                    "draft",
                    {
                        "title": "Предварительная смета",
                        "rows": [{"description": "Подготовка"}],
                        "totals": {"total": "125000.00"},
                    },
                    "2026-08-01T13:03:00Z",
                ),
                (
                    "document_catalog_proposal_01",
                    "commercial-proposal",
                    4,
                    "stale",
                    {"title": "КП на ремонт квартиры"},
                    "2026-08-01T13:02:00Z",
                ),
                (
                    "document_catalog_contract_01",
                    "contract",
                    5,
                    "revoked",
                    {"title": ["not", "a", "string"]},
                    "2026-08-01T13:01:00Z",
                ),
            ]
            for (
                document_id,
                slot_type,
                version,
                status,
                content,
                updated_at,
            ) in slots:
                _seed_slot(
                    database,
                    tenant_id=owner["tenantId"],
                    project_id=project_id,
                    document_id=document_id,
                    slot_type=slot_type,
                    version=version,
                    status=status,
                    content=content,
                    updated_at=updated_at,
                )

            _seed_slot(
                database,
                tenant_id=owner["tenantId"],
                project_id=empty_project_id,
                document_id="document_catalog_empty_01",
                slot_type="source-data",
                version=1,
                status="empty",
                content={"title": "Не показывать"},
                updated_at="2026-08-01T13:06:00Z",
            )
            _seed_slot(
                database,
                tenant_id=owner["tenantId"],
                project_id=empty_project_id,
                document_id="document_catalog_null_01",
                slot_type="contract",
                version=1,
                status="draft",
                content=None,
                updated_at="2026-08-01T13:05:00Z",
            )
            _seed_slot(
                database,
                tenant_id=foreign["tenantId"],
                project_id=project_id,
                document_id="document_catalog_foreign_01",
                slot_type="source-data",
                version=9,
                status="ready",
                content={"title": "Чужие исходные данные"},
                updated_at="2026-08-01T13:07:00Z",
            )
            database.commit()
        finally:
            database.close()

        response = client.get("/v1/documents")
        assert response.status_code == 200, response.text
        assert response.json()["documents"] == [
            {
                "id": "document_catalog_source_01",
                "projectId": project_id,
                "projectName": "Проект владельца",
                "slotType": "source-data",
                "category": "documents",
                "kind": "document",
                "name": "ТЗ и результаты обмеров",
                "status": "ready",
                "version": 2,
                "updatedAt": "2026-08-01T13:04:00Z",
                "editable": False,
            },
            {
                "id": "document_catalog_estimate_01",
                "projectId": project_id,
                "projectName": "Проект владельца",
                "slotType": "estimate",
                "category": "estimates",
                "kind": "estimate",
                "name": "Предварительная смета",
                "status": "draft",
                "version": 3,
                "updatedAt": "2026-08-01T13:03:00Z",
                "editable": True,
                "rowCount": 1,
                "total": "125000.00",
                "currency": "RUB",
            },
            {
                "id": "document_catalog_proposal_01",
                "projectId": project_id,
                "projectName": "Проект владельца",
                "slotType": "commercial-proposal",
                "category": "documents",
                "kind": "document",
                "name": "КП на ремонт квартиры",
                "status": "stale",
                "version": 4,
                "updatedAt": "2026-08-01T13:02:00Z",
                "editable": False,
            },
            {
                "id": "document_catalog_contract_01",
                "projectId": project_id,
                "projectName": "Проект владельца",
                "slotType": "contract",
                "category": "contracts",
                "kind": "contract",
                "name": "Договор",
                "status": "revoked",
                "version": 5,
                "updatedAt": "2026-08-01T13:01:00Z",
                "editable": False,
            },
        ]


def test_document_catalog_requires_the_construction_product_access(
    tmp_path: Path,
) -> None:
    settings = Settings.for_testing(database_url=tmp_path / "catalog-auth.db")
    with TestClient(create_app(settings)) as client:
        registered = _register(
            client,
            email="catalog-member@example.com",
            name="Catalog member",
        )
        assert registered["entitlements"] == []
        denied = client.get("/v1/documents")
        assert denied.status_code == 403
        assert denied.json()["code"] == "product_entitlement_required"
