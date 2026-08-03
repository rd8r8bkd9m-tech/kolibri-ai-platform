"""Fail-closed archival for explicitly marked QA tenants.

This command never deletes rows. It revokes sessions and makes a QA tenant
inert only when both the tenant name and every user email prove test scope.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from typing import Any

from .config import Settings
from .database import connect_database, transaction


def archive_qa_tenant(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    confirmation: str,
) -> dict[str, Any]:
    expected = f"ARCHIVE QA TENANT {tenant_id}"
    if confirmation != expected:
        raise ValueError("exact QA tenant archive confirmation is required")
    tenant = database.execute(
        "SELECT name FROM tenants WHERE id = ? LIMIT 1",
        (tenant_id,),
    ).fetchone()
    if tenant is None or not str(tenant["name"]).startswith(("[QA] ", "QA ")):
        raise ValueError("tenant is not explicitly marked as QA")
    users = database.execute(
        "SELECT id, email_normalized FROM users WHERE tenant_id = ?",
        (tenant_id,),
    ).fetchall()
    if not users or any(
        not str(row["email_normalized"]).endswith(
            ("@example.test", ".invalid", "+qa@example.com")
        )
        for row in users
    ):
        raise ValueError("QA tenant contains a non-test email address")
    authority = database.execute(
        """
        SELECT 1 FROM platform_authority_grants
        WHERE tenant_id = ? AND active = 1
        LIMIT 1
        """,
        (tenant_id,),
    ).fetchone()
    if authority is not None:
        raise ValueError("platform authority tenants cannot be archived as QA")

    now = int(time.time())
    with transaction(database, immediate=True):
        policy = database.execute(
            """
            UPDATE platform_tenant_policies
            SET lifecycle_status = 'suspended',
                block_reason = 'qa_acceptance_archived',
                revision = revision + 1,
                updated_at = ?
            WHERE tenant_id = ? AND lifecycle_status = 'active'
            """,
            (now, tenant_id),
        ).rowcount
        controls = database.execute(
            """
            UPDATE platform_user_controls
            SET access_status = 'blocked',
                block_reason = 'qa_acceptance_archived',
                revision = revision + 1,
                updated_at = ?
            WHERE tenant_id = ? AND access_status = 'active'
            """,
            (now, tenant_id),
        ).rowcount
        sessions = database.execute(
            """
            UPDATE sessions SET revoked_at = ?
            WHERE tenant_id = ? AND revoked_at IS NULL
            """,
            (now, tenant_id),
        ).rowcount
        projects = database.execute(
            "UPDATE projects SET status = 'archived', updated_at = ? WHERE tenant_id = ? AND status = 'active'",
            (str(now), tenant_id),
        ).rowcount
        threads = database.execute(
            "UPDATE chat_threads SET status = 'archived', updated_at = ? WHERE tenant_id = ? AND status = 'regular'",
            (str(now), tenant_id),
        ).rowcount
    return {
        "tenantId": tenant_id,
        "mode": "archive_only",
        "deletedRows": 0,
        "tenantPoliciesSuspended": policy,
        "usersBlocked": controls,
        "sessionsRevoked": sessions,
        "projectsArchived": projects,
        "threadsArchived": threads,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive an explicit QA tenant")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--confirm", required=True)
    arguments = parser.parse_args()
    database = connect_database(Settings.from_env().database_url)
    try:
        result = archive_qa_tenant(
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
