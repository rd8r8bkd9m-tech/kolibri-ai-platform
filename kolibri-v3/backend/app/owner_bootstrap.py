from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import dataclass

from .config import Settings
from .database import connect_database, initialize_database, transaction
from .platform_authority import PLATFORM_OWNER_CAPABILITIES
from .product_entitlements import CONSTRUCTION_ESTIMATES_ENTITLEMENT


class OwnerBootstrapError(RuntimeError):
    """The trusted operator bootstrap could not be completed."""


@dataclass(frozen=True, slots=True)
class OwnerBootstrapResult:
    user_id: str
    tenant_id: str
    changed: bool


def _normalize_email(value: str) -> str:
    normalized = value.strip().casefold()
    if not normalized or len(normalized) > 320 or "@" not in normalized:
        raise OwnerBootstrapError("A valid registered email is required.")
    return normalized


def promote_registered_owner(
    settings: Settings,
    *,
    email: str,
) -> OwnerBootstrapResult:
    """Promote one already registered account from the trusted server side.

    This function is deliberately not exposed through HTTP. Possession of a
    public email address must never be enough to acquire platform authority.
    """

    normalized = _normalize_email(email)
    if (
        settings.bootstrap_owner_email is not None
        and normalized != settings.bootstrap_owner_email
    ):
        raise OwnerBootstrapError(
            "Email does not match KOLIBRI_V3_BOOTSTRAP_OWNER_EMAIL."
        )
    if settings.environment == "production" and settings.bootstrap_owner_email is None:
        raise OwnerBootstrapError(
            "KOLIBRI_V3_BOOTSTRAP_OWNER_EMAIL is required in production."
        )

    initialize_database(settings.database_url)
    database = connect_database(settings.database_url)
    try:
        with transaction(database, immediate=True):
            user = database.execute(
                """
                SELECT id, tenant_id, role
                FROM users
                WHERE email_normalized = ?
                LIMIT 1
                """,
                (normalized,),
            ).fetchone()
            if user is None:
                raise OwnerBootstrapError(
                    "Register the account before running owner bootstrap."
                )

            existing = database.execute(
                """
                SELECT user_id, tenant_id
                FROM platform_authority_grants
                WHERE authority_id = 'platform_owner'
                  AND active = 1
                LIMIT 1
                """
            ).fetchone()
            if (
                existing is not None
                and (
                    existing["user_id"] != user["id"]
                    or existing["tenant_id"] != user["tenant_id"]
                )
            ):
                raise OwnerBootstrapError(
                    "A different platform owner is already configured."
                )

            role_changed = user["role"] != "owner"
            grant_changed = existing is None
            if role_changed:
                database.execute(
                    """
                    UPDATE users
                    SET role = 'owner', updated_at = unixepoch()
                    WHERE id = ? AND tenant_id = ?
                    """,
                    (user["id"], user["tenant_id"]),
                )
                database.execute(
                    """
                    INSERT INTO identity_events (
                        id, event_type, actor_user_id, tenant_id,
                        subject_user_id, created_at, metadata_json
                    ) VALUES (?, 'owner_bootstrapped', NULL, ?, ?, unixepoch(), ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        user["tenant_id"],
                        user["id"],
                        json.dumps(
                            {"authority": "trusted_server_operator"},
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                    ),
                )
            if grant_changed:
                database.execute(
                    """
                    INSERT INTO platform_authority_grants (
                        authority_id, user_id, tenant_id, active,
                        authority_epoch, capabilities_json,
                        created_at, updated_at
                    ) VALUES (
                        'platform_owner', ?, ?, 1, 1, ?, unixepoch(), unixepoch()
                    )
                    """,
                    (
                        user["id"],
                        user["tenant_id"],
                        json.dumps(
                            list(PLATFORM_OWNER_CAPABILITIES),
                            separators=(",", ":"),
                        ),
                    ),
                )
                database.execute(
                    """
                    INSERT INTO identity_events (
                        id, event_type, actor_user_id, tenant_id,
                        subject_user_id, created_at, metadata_json
                        ) VALUES (
                            ?, 'owner_bootstrapped', NULL, ?, ?,
                        unixepoch(), ?
                    )
                    """,
                    (
                        str(uuid.uuid4()),
                        user["tenant_id"],
                        user["id"],
                        json.dumps(
                            {
                                "authority": "platform_owner",
                                "authorityEpoch": 1,
                                "source": "trusted_server_operator",
                            },
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                    ),
                )
            product_grant = database.execute(
                """
                INSERT INTO product_entitlement_grants (
                    tenant_id, user_id, entitlement_code, status,
                    grant_epoch, source, created_at, updated_at
                ) VALUES (
                    ?, ?, ?, 'active', 1, 'trusted_server_operator',
                    unixepoch(), unixepoch()
                )
                ON CONFLICT (tenant_id, user_id, entitlement_code)
                DO UPDATE SET
                    status = 'active',
                    grant_epoch = product_entitlement_grants.grant_epoch + 1,
                    source = 'trusted_server_operator',
                    updated_at = unixepoch()
                WHERE product_entitlement_grants.status != 'active'
                """,
                (
                    user["tenant_id"],
                    user["id"],
                    CONSTRUCTION_ESTIMATES_ENTITLEMENT,
                ),
            )
            product_grant_changed = product_grant.rowcount == 1
            changed = role_changed or grant_changed or product_grant_changed
            # The trusted bootstrap also creates an explicit persisted
            # developer policy. Runtime/server gates remain authoritative, so
            # this grants no execution capability by itself.
            tenant_policy_changed = database.execute(
                """
                UPDATE platform_tenant_policies
                SET developer_access_enabled = 1,
                    revision = revision + 1,
                    updated_at = unixepoch(),
                    updated_by_user_id = ?
                WHERE tenant_id = ?
                  AND developer_access_enabled = 0
                """,
                (user["id"], user["tenant_id"]),
            )
            user_policy_changed = database.execute(
                """
                UPDATE platform_user_controls
                SET developer_access = 'allow',
                    revision = revision + 1,
                    updated_at = unixepoch(),
                    updated_by_user_id = ?
                WHERE user_id = ? AND tenant_id = ?
                  AND developer_access != 'allow'
                """,
                (user["id"], user["id"], user["tenant_id"]),
            )
            if (
                tenant_policy_changed.rowcount
                or user_policy_changed.rowcount
                or product_grant_changed
            ):
                database.execute(
                    """
                    INSERT INTO platform_admin_audit_events (
                        id, actor_user_id, actor_tenant_id, action,
                        target_type, target_id, target_tenant_id,
                        before_json, after_json, created_at
                    ) VALUES (
                        ?, ?, ?, 'policy.owner_bootstrap', 'policy', ?, ?,
                        '{}', ?, unixepoch()
                    )
                    """,
                    (
                        f"audit_{uuid.uuid4().hex}",
                        user["id"],
                        user["tenant_id"],
                        user["tenant_id"],
                        user["tenant_id"],
                        json.dumps(
                            {
                                "developerAccessEnabled": True,
                                "userDeveloperAccess": "allow",
                                "productEntitlements": [
                                    CONSTRUCTION_ESTIMATES_ENTITLEMENT
                                ],
                                "source": "trusted_server_operator",
                            },
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                    ),
                )
            return OwnerBootstrapResult(
                user_id=user["id"],
                tenant_id=user["tenant_id"],
                changed=changed,
            )
    finally:
        database.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Promote one registered Kolibri V3 account to platform owner.",
    )
    parser.add_argument(
        "--email",
        help=(
            "Registered account email. Defaults to "
            "KOLIBRI_V3_BOOTSTRAP_OWNER_EMAIL."
        ),
    )
    arguments = parser.parse_args()
    settings = Settings.from_env()
    email = arguments.email or settings.bootstrap_owner_email
    if email is None:
        parser.error(
            "--email or KOLIBRI_V3_BOOTSTRAP_OWNER_EMAIL is required"
        )
    result = promote_registered_owner(settings, email=email)
    print(
        json.dumps(
            {
                "changed": result.changed,
                "tenantId": result.tenant_id,
                "userId": result.user_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
