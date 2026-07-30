"""Fail-closed development database migration and owner preflight."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import Settings
from .database import (
    connect_database,
    database_path,
    initialize_database,
    migration_paths,
)


REQUIRED_OWNER_CAPABILITIES = frozenset(
    {
        "platform.admin",
        "chat.developer.request",
        "chat.use",
    }
)


def prepare_development_database(
    settings: Settings,
    *,
    expected_database: Path,
    expected_owner_email: str | None = None,
) -> tuple[int, int, int]:
    """Migrate and verify the one canonical development database."""

    if settings.environment != "development":
        raise RuntimeError("Development preflight refuses a non-development runtime")
    configured_path = database_path(settings.database_url)
    if not isinstance(configured_path, Path):
        raise RuntimeError("Development preflight requires a file database")
    actual_database = configured_path.resolve()
    expected = expected_database.resolve()
    if actual_database != expected:
        raise RuntimeError(
            f"Wrong V3 database: expected {expected}, got {actual_database}"
        )

    initialize_database(settings.database_url)
    latest_version = int(migration_paths()[-1].name.split("_", 1)[0])
    database = connect_database(settings.database_url)
    try:
        current_version = int(
            database.execute("PRAGMA user_version").fetchone()[0]
        )
        if current_version != latest_version:
            raise RuntimeError(
                "V3 database did not reach the latest migration"
            )
        user_count = int(
            database.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        )
        owner_rows = database.execute(
            """
            SELECT
                grant_row.capabilities_json,
                user_row.email_normalized,
                user_row.password_hash,
                user_control.access_status,
                tenant_policy.lifecycle_status
            FROM platform_authority_grants AS grant_row
            JOIN users AS user_row
              ON user_row.id = grant_row.user_id
             AND user_row.tenant_id = grant_row.tenant_id
            LEFT JOIN platform_user_controls AS user_control
              ON user_control.user_id = user_row.id
             AND user_control.tenant_id = user_row.tenant_id
            LEFT JOIN platform_tenant_policies AS tenant_policy
              ON tenant_policy.tenant_id = user_row.tenant_id
            WHERE grant_row.authority_id = 'platform_owner'
              AND grant_row.active = 1
              AND user_row.role = 'owner'
            """
        ).fetchall()
        owner_count = len(owner_rows)
        if user_count > 0 and owner_count != 1:
            raise RuntimeError(
                "Existing V3 database must have exactly one active platform owner"
            )
        if owner_count == 1:
            owner = owner_rows[0]
            normalized_expected_owner = (
                expected_owner_email.strip().casefold()
                if expected_owner_email is not None
                else None
            )
            if (
                normalized_expected_owner is not None
                and str(owner["email_normalized"]).casefold()
                != normalized_expected_owner
            ):
                raise RuntimeError(
                    "Canonical V3 platform owner email does not match"
                )
            password_hash = owner["password_hash"]
            if (
                not isinstance(password_hash, str)
                or not password_hash.startswith("scrypt-v1$")
                or len(password_hash.split("$")) != 6
            ):
                raise RuntimeError(
                    "Platform owner password credential is invalid"
                )
            if owner["access_status"] != "active":
                raise RuntimeError(
                    "Platform owner account access is not active"
                )
            if owner["lifecycle_status"] != "active":
                raise RuntimeError(
                    "Platform owner tenant access is not active"
                )
            try:
                raw_capabilities = json.loads(
                    str(owner["capabilities_json"])
                )
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    "Platform owner capabilities are invalid"
                ) from exc
            if (
                not isinstance(raw_capabilities, list)
                or not all(
                    isinstance(capability, str)
                    for capability in raw_capabilities
                )
            ):
                raise RuntimeError(
                    "Platform owner capabilities are invalid"
                )
            capabilities = frozenset(raw_capabilities)
            missing = REQUIRED_OWNER_CAPABILITIES - capabilities
            if missing:
                raise RuntimeError(
                    "Platform owner is missing required development capabilities"
                )
        return current_version, user_count, owner_count
    finally:
        database.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--expected-database",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--expected-owner-email",
        required=True,
    )
    arguments = parser.parse_args()
    version, user_count, owner_count = prepare_development_database(
        Settings.from_env(),
        expected_database=arguments.expected_database,
        expected_owner_email=arguments.expected_owner_email,
    )
    print(
        "Kolibri V3 preflight: "
        f"schema={version} users={user_count} platform_owner={owner_count}"
    )


if __name__ == "__main__":
    main()
