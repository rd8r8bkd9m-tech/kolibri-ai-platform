"""Fail-closed provisioning for disposable QA acceptance tenants."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from typing import Any

from .config import Settings
from .database import connect_database, transaction
from .product_entitlements import CONSTRUCTION_ESTIMATES_ENTITLEMENT


def provision_qa_tenant(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    confirmation: str,
) -> dict[str, Any]:
    if confirmation != f"PREPARE QA TENANT {tenant_id}":
        raise ValueError("exact QA tenant preparation confirmation is required")
    tenant = database.execute(
        "SELECT name FROM tenants WHERE id = ? LIMIT 1", (tenant_id,)
    ).fetchone()
    if tenant is None or not str(tenant["name"]).startswith(("[QA] ", "QA ")):
        raise ValueError("tenant is not explicitly marked as QA")
    users = database.execute(
        "SELECT id, email_normalized FROM users WHERE tenant_id = ?", (tenant_id,)
    ).fetchall()
    if len(users) != 1 or not str(users[0]["email_normalized"]).endswith(
        ("@example.test", ".invalid", "+qa@example.com")
    ):
        raise ValueError("QA tenant must contain exactly one test-only user")
    authority = database.execute(
        "SELECT 1 FROM platform_authority_grants WHERE tenant_id = ? AND active = 1 LIMIT 1",
        (tenant_id,),
    ).fetchone()
    if authority is not None:
        raise ValueError("platform authority tenants cannot be provisioned as QA")

    now = int(time.time())
    user_id = str(users[0]["id"])
    with transaction(database, immediate=True):
        database.execute(
            """
            INSERT INTO product_entitlement_grants (
                tenant_id, user_id, entitlement_code, status,
                grant_epoch, source, created_at, updated_at
            ) VALUES (?, ?, ?, 'active', 1, 'trusted_server_operator', ?, ?)
            ON CONFLICT (tenant_id, user_id, entitlement_code) DO UPDATE SET
                status = 'active',
                grant_epoch = product_entitlement_grants.grant_epoch + 1,
                source = 'trusted_server_operator',
                updated_at = excluded.updated_at
            """,
            (tenant_id, user_id, CONSTRUCTION_ESTIMATES_ENTITLEMENT, now, now),
        )
    return {
        "tenantId": tenant_id,
        "userId": user_id,
        "entitlement": CONSTRUCTION_ESTIMATES_ENTITLEMENT,
        "mode": "qa_only",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision an explicit QA tenant")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--confirm", required=True)
    arguments = parser.parse_args()
    database = connect_database(Settings.from_env().database_url)
    try:
        result = provision_qa_tenant(
            database,
            tenant_id=arguments.tenant_id,
            confirmation=arguments.confirm,
        )
    finally:
        database.close()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
