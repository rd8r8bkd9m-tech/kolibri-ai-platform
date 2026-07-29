from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import dataclass

from .config import Settings
from .database import connect_database, initialize_database, transaction


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
                SELECT id, tenant_id
                FROM users
                WHERE role = 'owner'
                LIMIT 1
                """
            ).fetchone()
            if existing is not None and existing["id"] != user["id"]:
                raise OwnerBootstrapError(
                    "A different platform owner is already configured."
                )

            changed = user["role"] != "owner"
            if changed:
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
