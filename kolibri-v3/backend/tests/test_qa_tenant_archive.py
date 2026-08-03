from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.qa_tenant_archive import archive_qa_tenant
from app.qa_tenant_fixture import provision_qa_tenant


def test_qa_archive_is_explicit_non_destructive_and_tenant_scoped(tmp_path: Path) -> None:
    database_path = tmp_path / "qa-archive.db"
    app = create_app(Settings.for_testing(database_url=database_path))
    with TestClient(app) as client:
        registered = client.post(
            "/v1/auth/register",
            headers={"Origin": "http://testserver"},
            json={
                "email": "acceptance+qa@example.com",
                "name": "Acceptance QA",
                "password": "correct-horse-battery-staple",
            },
        )
        assert registered.status_code == 201
        tenant_id = registered.json()["user"]["tenantId"]

    database = sqlite3.connect(database_path)
    database.row_factory = sqlite3.Row
    try:
        database.execute(
            "UPDATE tenants SET name = '[QA] Production acceptance' WHERE id = ?",
            (tenant_id,),
        )
        database.commit()
        provisioned = provision_qa_tenant(
            database,
            tenant_id=tenant_id,
            confirmation=f"PREPARE QA TENANT {tenant_id}",
        )
        assert provisioned["mode"] == "qa_only"
        assert database.execute(
            "SELECT source FROM product_entitlement_grants WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()[0] == "trusted_server_operator"
        with pytest.raises(ValueError, match="exact QA tenant archive"):
            archive_qa_tenant(
                database,
                tenant_id=tenant_id,
                confirmation="ARCHIVE",
            )
        result = archive_qa_tenant(
            database,
            tenant_id=tenant_id,
            confirmation=f"ARCHIVE QA TENANT {tenant_id}",
        )
        assert result["mode"] == "archive_only"
        assert result["deletedRows"] == 0
        assert database.execute(
            "SELECT COUNT(*) FROM users WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()[0] == 1
        assert database.execute(
            "SELECT lifecycle_status FROM platform_tenant_policies WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()[0] == "suspended"
        assert database.execute(
            "SELECT access_status FROM platform_user_controls WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()[0] == "blocked"
        assert database.execute(
            "SELECT COUNT(*) FROM sessions WHERE tenant_id = ? AND revoked_at IS NULL",
            (tenant_id,),
        ).fetchone()[0] == 0
    finally:
        database.close()
