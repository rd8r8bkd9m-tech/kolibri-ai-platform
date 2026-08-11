"""Fail-closed provisioning for disposable QA acceptance tenants."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from typing import Any

from dotenv import load_dotenv

from .config import Settings
from .database import connect_database, transaction
from .local_provider_authority import (
    LocalProviderAuthorityError,
    install_mimo_key,
    verify_codex_login,
)
from .product_entitlements import CONSTRUCTION_ESTIMATES_ENTITLEMENT


_QA_PROVIDER_IDS = ("codex-cli", "mimo-code")


def provision_qa_tenant(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    confirmation: str,
    provider_id: str | None = None,
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
    provider: dict[str, Any] | None = None
    if provider_id is not None:
        provider = provision_qa_provider_connection(
            database,
            tenant_id=tenant_id,
            provider_id=provider_id,
            settings=Settings.from_env(),
        )
    return {
        "tenantId": tenant_id,
        "userId": user_id,
        "entitlement": CONSTRUCTION_ESTIMATES_ENTITLEMENT,
        "provider": provider,
        "mode": "qa_only",
    }


def provision_qa_provider_connection(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    provider_id: str,
    settings: Settings,
) -> dict[str, Any]:
    """Mark a genuinely verified local provider as connected for one QA tenant.

    Mirrors the owner-only enrollment result for disposable QA tenants: the
    connection row is written only after the local authority really verified
    the credential (Codex CLI login status or a live MiMo key check), so a
    "connected" QA row never papers over an unavailable runtime.
    """

    if provider_id not in _QA_PROVIDER_IDS:
        raise ValueError(f"QA provider must be one of {_QA_PROVIDER_IDS}")
    if provider_id == "codex-cli":
        result = verify_codex_login(settings)
    else:
        api_key = os.getenv("MIMO_API_KEY", "").strip()
        if not api_key:
            raise LocalProviderAuthorityError(
                "mimo_api_key_required",
                "MIMO_API_KEY не задан для QA-подключения MiMo.",
            )
        result = install_mimo_key(settings, api_key, tenant_id=tenant_id)

    now = int(time.time())
    with transaction(database, immediate=True):
        database.execute(
            """
            INSERT INTO provider_connections (
                tenant_id, provider_id, status, auth_flow_supported,
                authority_observed, last_verified_at, last_evidence_hash,
                last_intent_id, last_error_code, created_at, updated_at
            ) VALUES (?, ?, 'connected', 1, 1, ?, ?, NULL, NULL, ?, ?)
            ON CONFLICT(tenant_id, provider_id) DO UPDATE SET
                status = 'connected',
                auth_flow_supported = 1,
                authority_observed = 1,
                last_verified_at = excluded.last_verified_at,
                last_evidence_hash = excluded.last_evidence_hash,
                last_error_code = NULL,
                updated_at = excluded.updated_at
            """,
            (
                tenant_id,
                provider_id,
                result["last_verified_at"],
                result["evidence_hash"],
                now,
                now,
            ),
        )
    return {
        "providerId": provider_id,
        "status": "connected",
        "lastVerifiedAt": result["last_verified_at"],
    }


def main() -> int:
    load_dotenv(".env.local", override=False)
    parser = argparse.ArgumentParser(description="Provision an explicit QA tenant")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument(
        "--provider",
        choices=_QA_PROVIDER_IDS,
        default=None,
        help="Optionally provision a verified local provider connection.",
    )
    arguments = parser.parse_args()
    database = connect_database(Settings.from_env().database_url)
    try:
        result = provision_qa_tenant(
            database,
            tenant_id=arguments.tenant_id,
            confirmation=arguments.confirm,
            provider_id=arguments.provider,
        )
    finally:
        database.close()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
