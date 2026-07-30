"""Standalone durable dispatcher for secretless provider enrollment intents."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
import time
import uuid

from .chat.service import typed_identity_id
from .config import Settings
from .database import connect_database, initialize_database, transaction
from .provider_authority import (
    ProviderAuthorityClient,
    ProviderAuthorityError,
    ProviderAuthoritySettings,
)
from .platform_admin import (
    PlatformPolicyError,
    enforce_background_execution_policy,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(value: str) -> str:
    return (
        "sha256:"
        + hashlib.sha256(value.encode("utf-8", "strict")).hexdigest()
    )


@dataclass(frozen=True, slots=True)
class EnrollmentLease:
    tenant_id: str
    intent_id: str
    provider_id: str
    command_json: str
    command_hash: str
    attempts: int
    max_attempts: int
    lease_token: str
    fencing_token: int


class ProviderEnrollmentWorker:
    def __init__(
        self,
        *,
        database_url: str,
        settings: Settings,
        authority: ProviderAuthorityClient,
        worker_id: str | None = None,
    ) -> None:
        self.database_url = database_url
        self.settings = settings
        self.authority = authority
        self.worker_id = worker_id or f"provider-worker-{uuid.uuid4().hex}"

    def _claim(self) -> EnrollmentLease | None:
        database = connect_database(self.database_url)
        try:
            now = _utc_now()
            lease_until = (
                datetime.now(timezone.utc)
                + timedelta(
                    seconds=self.settings.provider_enrollment_lease_seconds
                )
            ).isoformat()
            with transaction(database, immediate=True):
                exhausted_rows = database.execute(
                    """
                    SELECT tenant_id, id, provider_id
                    FROM provider_enrollment_intents
                    WHERE state = 'leased'
                      AND lease_until <= ?
                      AND attempts >= max_attempts
                    """,
                    (now,),
                ).fetchall()
                for exhausted in exhausted_rows:
                    database.execute(
                        """
                        UPDATE provider_enrollment_intents
                        SET state = 'blocked',
                            lease_owner = NULL,
                            lease_token = NULL,
                            lease_until = NULL,
                            last_error_code = 'provider_enrollment_lease_exhausted',
                            updated_at = ?,
                            completed_at = ?
                        WHERE tenant_id = ?
                          AND id = ?
                          AND state = 'leased'
                          AND lease_until <= ?
                          AND attempts >= max_attempts
                        """,
                        (
                            now,
                            now,
                            exhausted["tenant_id"],
                            exhausted["id"],
                            now,
                        ),
                    )
                    database.execute(
                        """
                        UPDATE provider_connections
                        SET status = 'error',
                            last_error_code = 'provider_enrollment_lease_exhausted',
                            updated_at = ?
                        WHERE tenant_id = ?
                          AND provider_id = ?
                          AND status <> 'connected'
                        """,
                        (
                            now,
                            exhausted["tenant_id"],
                            exhausted["provider_id"],
                        ),
                    )
                row = database.execute(
                    """
                    SELECT *
                    FROM provider_enrollment_intents
                    WHERE attempts < max_attempts
                      AND (
                        (
                          state IN ('queued', 'retry')
                          AND available_at <= ?
                        )
                        OR (
                          state = 'leased'
                          AND lease_until <= ?
                        )
                      )
                    ORDER BY available_at, created_at, tenant_id, id
                    LIMIT 1
                    """,
                    (now, now),
                ).fetchone()
                if row is None:
                    return None
                lease_token = uuid.uuid4().hex
                fencing_token = int(row["fencing_token"]) + 1
                attempts = int(row["attempts"]) + 1
                updated = database.execute(
                    """
                    UPDATE provider_enrollment_intents
                    SET state = 'leased',
                        attempts = ?,
                        lease_owner = ?,
                        lease_token = ?,
                        lease_until = ?,
                        fencing_token = ?,
                        updated_at = ?
                    WHERE tenant_id = ?
                      AND id = ?
                      AND fencing_token = ?
                      AND state = ?
                    """,
                    (
                        attempts,
                        self.worker_id,
                        lease_token,
                        lease_until,
                        fencing_token,
                        now,
                        row["tenant_id"],
                        row["id"],
                        row["fencing_token"],
                        row["state"],
                    ),
                )
                if updated.rowcount != 1:
                    return None
                return EnrollmentLease(
                    tenant_id=str(row["tenant_id"]),
                    intent_id=str(row["id"]),
                    provider_id=str(row["provider_id"]),
                    command_json=str(row["command_json"]),
                    command_hash=str(row["command_hash"]),
                    attempts=attempts,
                    max_attempts=int(row["max_attempts"]),
                    lease_token=lease_token,
                    fencing_token=fencing_token,
                )
        finally:
            database.close()

    def _policy_error(self, lease: EnrollmentLease) -> str | None:
        database = connect_database(self.database_url)
        try:
            row = database.execute(
                """
                SELECT requested_by_user_id
                FROM provider_enrollment_intents
                WHERE tenant_id = ? AND id = ?
                LIMIT 1
                """,
                (lease.tenant_id, lease.intent_id),
            ).fetchone()
            if row is None:
                return "provider_enrollment_intent_missing"
            user_id = str(row["requested_by_user_id"])
            command_user_id: str | None = None
            try:
                command = json.loads(lease.command_json)
            except (TypeError, json.JSONDecodeError):
                command = None
            if isinstance(command, dict):
                identity = command.get("identity")
                if isinstance(identity, dict) and isinstance(
                    identity.get("user_id"),
                    str,
                ):
                    command_user_id = str(identity["user_id"])
            if (
                command_user_id is None
                or command_user_id
                != typed_identity_id("user", user_id)
            ):
                return "stored_command_identity_invalid"
            try:
                enforce_background_execution_policy(
                    database,
                    tenant_id=lease.tenant_id,
                    user_id=user_id,
                )
            except PlatformPolicyError as exc:
                return exc.code
            return None
        finally:
            database.close()

    @staticmethod
    def _guard(
        database: sqlite3.Connection,
        lease: EnrollmentLease,
    ) -> bool:
        return (
            database.execute(
                """
                SELECT 1
                FROM provider_enrollment_intents
                WHERE tenant_id = ?
                  AND id = ?
                  AND state = 'leased'
                  AND lease_token = ?
                  AND fencing_token = ?
                """,
                (
                    lease.tenant_id,
                    lease.intent_id,
                    lease.lease_token,
                    lease.fencing_token,
                ),
            ).fetchone()
            is not None
        )

    def _complete(
        self,
        lease: EnrollmentLease,
        *,
        response_status: str,
        auth_flow_supported: bool,
        last_verified_at: str | None,
        response_hash: str,
        error_code: str | None,
    ) -> None:
        connection_status = {
            "connected": "connected",
            "failed": "error",
        }[response_status]
        database = connect_database(self.database_url)
        try:
            now = _utc_now()
            with transaction(database, immediate=True):
                if not self._guard(database, lease):
                    return
                database.execute(
                    """
                    UPDATE provider_connections
                    SET status = ?,
                        auth_flow_supported = ?,
                        authority_observed = 1,
                        last_verified_at = ?,
                        last_evidence_hash = ?,
                        last_intent_id = ?,
                        last_error_code = ?,
                        updated_at = ?
                    WHERE tenant_id = ? AND provider_id = ?
                    """,
                    (
                        connection_status,
                        int(auth_flow_supported),
                        last_verified_at,
                        (
                            response_hash
                            if response_status == "connected"
                            else None
                        ),
                        lease.intent_id,
                        error_code,
                        now,
                        lease.tenant_id,
                        lease.provider_id,
                    ),
                )
                database.execute(
                    """
                    UPDATE provider_enrollment_intents
                    SET state = 'completed',
                        authority_status = ?,
                        authority_response_hash = ?,
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_until = NULL,
                        last_error_code = ?,
                        updated_at = ?,
                        completed_at = ?
                    WHERE tenant_id = ?
                      AND id = ?
                      AND state = 'leased'
                      AND lease_token = ?
                      AND fencing_token = ?
                    """,
                    (
                        response_status,
                        response_hash,
                        error_code,
                        now,
                        now,
                        lease.tenant_id,
                        lease.intent_id,
                        lease.lease_token,
                        lease.fencing_token,
                    ),
                )
        finally:
            database.close()

    def _fail(
        self,
        lease: EnrollmentLease,
        error: ProviderAuthorityError,
    ) -> None:
        exhausted = lease.attempts >= lease.max_attempts
        terminal = not error.retryable or exhausted
        database = connect_database(self.database_url)
        try:
            now_dt = datetime.now(timezone.utc)
            now = now_dt.isoformat()
            retry_delay = min(
                self.settings.provider_enrollment_retry_max_seconds,
                self.settings.provider_enrollment_retry_base_seconds
                * (2 ** max(0, lease.attempts - 1)),
            )
            available_at = (
                now_dt + timedelta(seconds=retry_delay)
            ).isoformat()
            with transaction(database, immediate=True):
                if not self._guard(database, lease):
                    return
                if terminal:
                    missing_endpoint = (
                        error.code == "provider_authority_http_404"
                    )
                    database.execute(
                        """
                        UPDATE provider_connections
                        SET status = ?,
                            auth_flow_supported = 0,
                            last_verified_at = NULL,
                            last_evidence_hash = NULL,
                            last_intent_id = ?,
                            last_error_code = ?,
                            updated_at = ?
                        WHERE tenant_id = ?
                          AND provider_id = ?
                          AND status <> 'connected'
                        """,
                        (
                            (
                                "not_configured"
                                if missing_endpoint
                                else "error"
                            ),
                            lease.intent_id,
                            error.code,
                            now,
                            lease.tenant_id,
                            lease.provider_id,
                        ),
                    )
                database.execute(
                    """
                    UPDATE provider_enrollment_intents
                    SET state = ?,
                        available_at = ?,
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_until = NULL,
                        last_error_code = ?,
                        updated_at = ?,
                        completed_at = ?
                    WHERE tenant_id = ?
                      AND id = ?
                      AND state = 'leased'
                      AND lease_token = ?
                      AND fencing_token = ?
                    """,
                    (
                        "blocked" if terminal else "retry",
                        available_at,
                        error.code,
                        now,
                        now if terminal else None,
                        lease.tenant_id,
                        lease.intent_id,
                        lease.lease_token,
                        lease.fencing_token,
                    ),
                )
        finally:
            database.close()

    def run_once(self) -> bool:
        lease = self._claim()
        if lease is None:
            return False
        if _sha256_text(lease.command_json) != lease.command_hash:
            self._fail(
                lease,
                ProviderAuthorityError(
                    "provider_enrollment_command_hash_mismatch",
                    retryable=False,
                ),
            )
            return True
        policy_error = self._policy_error(lease)
        if policy_error is not None:
            self._fail(
                lease,
                ProviderAuthorityError(policy_error, retryable=False),
            )
            return True
        try:
            response = self.authority.submit(lease.command_json)
        except ProviderAuthorityError as error:
            self._fail(lease, error)
            return True

        # A suspension can race an already-started authority call. Do not
        # project that response as connected after policy has changed.
        policy_error = self._policy_error(lease)
        if policy_error is not None:
            self._fail(
                lease,
                ProviderAuthorityError(policy_error, retryable=False),
            )
            return True

        value = response.value
        error_value = value.get("error")
        error_code = (
            str(error_value["code"])
            if isinstance(error_value, dict)
            else None
        )
        self._complete(
            lease,
            response_status=str(value["status"]),
            auth_flow_supported=bool(value["auth_flow_supported"]),
            last_verified_at=(
                str(value["last_verified_at"])
                if value["last_verified_at"] is not None
                else None
            ),
            response_hash=response.response_hash,
            error_code=error_code,
        )
        return True

    def run_forever(self) -> None:
        while True:
            if not self.run_once():
                time.sleep(self.settings.provider_enrollment_idle_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dispatch V3 provider enrollment intents"
    )
    parser.add_argument("--once", action="store_true")
    arguments = parser.parse_args()

    settings = Settings.from_env()
    authority_settings = ProviderAuthoritySettings.from_env()
    initialize_database(settings.database_url)
    worker = ProviderEnrollmentWorker(
        database_url=settings.database_url,
        settings=settings,
        authority=ProviderAuthorityClient(authority_settings),
    )
    if arguments.once:
        worker.run_once()
    else:
        worker.run_forever()


if __name__ == "__main__":
    main()
