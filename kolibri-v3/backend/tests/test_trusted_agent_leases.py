from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import sqlite3
from pathlib import Path
import threading

import pytest

from app.database import (
    connect_database,
    initialize_database,
    migration_paths,
)
from app.trusted_agent_leases import (
    TrustedAgentLeaseError,
    TrustedAgentLeaseScope,
    claim_or_renew_trusted_agent_lease,
    fence_trusted_agent_lease,
    issue_trusted_agent_lease,
    revoke_trusted_agent_lease,
    terminalize_trusted_agent_lease,
)


OWNER_ID = "user_lease_owner"
TENANT_ID = "tenant_lease_owner"
PROFILE_ID = f"tap_{'a' * 32}"
BINDING_ID = f"wsb_{'b' * 32}"
CLAIM_TOKEN_A = f"claim_a_{'c' * 48}"
CLAIM_TOKEN_B = f"claim_b_{'d' * 48}"
CAPABILITIES = json.dumps(
    [
        "platform.admin",
        "platform.audit.read",
        "platform.policy.write",
        "platform.sessions.revoke",
        "chat.developer.request",
        "chat.use",
    ],
    separators=(",", ":"),
)


def _apply_through(database_path: Path, maximum_version: int) -> None:
    database = sqlite3.connect(database_path, isolation_level=None)
    try:
        current_version = int(
            database.execute("PRAGMA user_version").fetchone()[0]
        )
        for migration in migration_paths():
            version = int(migration.name.split("_", 1)[0])
            if version > maximum_version:
                break
            if version <= current_version:
                continue
            database.executescript(migration.read_text(encoding="utf-8"))
    finally:
        database.close()


def _seed_scope_rows(
    database: sqlite3.Connection,
) -> TrustedAgentLeaseScope:
    database.execute(
        "INSERT INTO tenants (id, name, created_at) VALUES (?, ?, 1)",
        (TENANT_ID, "Lease tenant"),
    )
    database.execute(
        """
        INSERT INTO users (
            id,
            tenant_id,
            email_normalized,
            email,
            name,
            role,
            preferred_agent_profile,
            password_hash,
            created_at,
            updated_at
        ) VALUES (
            ?, ?, 'lease-owner@example.com', 'lease-owner@example.com',
            'Lease owner', 'owner', 'auto', 'test-password-hash', 1, 1
        )
        """,
        (OWNER_ID, TENANT_ID),
    )
    database.execute(
        """
        INSERT INTO platform_authority_grants (
            authority_id,
            user_id,
            tenant_id,
            active,
            authority_epoch,
            capabilities_json,
            created_at,
            updated_at
        ) VALUES ('platform_owner', ?, ?, 1, 1, ?, 1, 1)
        """,
        (OWNER_ID, TENANT_ID, CAPABILITIES),
    )
    database.execute(
        """
        INSERT INTO trusted_agent_workspace_bindings (
            id,
            authority_id,
            owner_user_id,
            owner_tenant_id,
            authority_epoch,
            server_ref,
            environment,
            fingerprint_token,
            lifecycle_status,
            workspace_epoch,
            revision,
            created_at,
            updated_at,
            created_by_user_id
        ) VALUES (
            ?, 'platform_owner', ?, ?, 1, ?, 'development', ?,
            'active', 1, 1, 1, 1, ?
        )
        """,
        (
            BINDING_ID,
            OWNER_ID,
            TENANT_ID,
            f"wsref_{'c' * 32}",
            f"sha256:{'d' * 64}",
            OWNER_ID,
        ),
    )
    database.execute(
        """
        INSERT INTO trusted_agent_profiles (
            id,
            authority_id,
            owner_user_id,
            owner_tenant_id,
            authority_epoch,
            workspace_binding_id,
            workspace_binding_epoch,
            display_name,
            runtime_profile,
            agent_card_id,
            agent_card_version,
            capabilities_json,
            tool_policy_id,
            access_mode,
            sandbox_profile,
            approval_policy,
            approvals_reviewer,
            max_concurrency,
            lifecycle_status,
            profile_epoch,
            revision,
            created_at,
            updated_at,
            created_by_user_id
        ) VALUES (
            ?, 'platform_owner', ?, ?, 1, ?, 1,
            'Lease trusted agent', 'codex-cli', 'codex-cli.primary', 1,
            '["developer.runtime.execute"]', 'developer.full.v1',
            'full', 'danger-full-access', 'never', NULL, 1,
            'active', 1, 1, 1, 1, ?
        )
        """,
        (PROFILE_ID, OWNER_ID, TENANT_ID, BINDING_ID, OWNER_ID),
    )
    return TrustedAgentLeaseScope(
        owner_user_id=OWNER_ID,
        owner_tenant_id=TENANT_ID,
        authority_epoch=1,
        profile_id=PROFILE_ID,
        profile_epoch=1,
        workspace_binding_id=BINDING_ID,
        workspace_binding_epoch=1,
        assignment_ref="run_assignment_primary",
    )


def _database_and_scope(
    database_path: Path,
) -> tuple[sqlite3.Connection, TrustedAgentLeaseScope]:
    initialize_database(database_path)
    database = connect_database(database_path)
    return database, _seed_scope_rows(database)


def test_migration_037_adds_hashed_claim_and_append_only_operations(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "lease-v36.db"
    _apply_through(database_path, 36)
    database = connect_database(database_path)
    try:
        scope = _seed_scope_rows(database)
        legacy_id = f"tal_{'e' * 32}"
        database.execute(
            """
            INSERT INTO trusted_agent_workspace_leases (
                id,
                authority_id,
                owner_user_id,
                owner_tenant_id,
                authority_epoch,
                profile_id,
                profile_epoch,
                workspace_binding_id,
                workspace_binding_epoch,
                state,
                fencing_token,
                created_at,
                updated_at,
                expires_at
            ) VALUES (
                ?, 'platform_owner', ?, ?, 1, ?, 1, ?, 1,
                'active', 1, 10, 10, 20
            )
            """,
            (
                legacy_id,
                scope.owner_user_id,
                scope.owner_tenant_id,
                scope.profile_id,
                scope.workspace_binding_id,
            ),
        )
    finally:
        database.close()

    _apply_through(database_path, 37)
    database = connect_database(database_path)
    try:
        assert database.execute("PRAGMA user_version").fetchone()[0] == 37
        columns = {
            row["name"]
            for row in database.execute(
                "PRAGMA table_info(trusted_agent_workspace_leases)"
            )
        }
        assert {
            "assignment_ref",
            "claim_owner",
            "claim_token_hash",
            "last_claimed_at",
            "terminal_reason",
        } <= columns
        assert (
            database.execute(
                """
                SELECT COUNT(*)
                FROM sqlite_master
                WHERE type = 'index'
                  AND name = 'uq_r1_single_active_trusted_agent_lease'
                """
            ).fetchone()[0]
            == 1
        )
        assert (
            database.execute(
                """
                SELECT strict
                FROM pragma_table_list
                WHERE name = 'trusted_agent_lease_operations'
                """
            ).fetchone()[0]
            == 1
        )
        # Existing v36 leases remain readable and can be safely drained.
        assert (
            database.execute(
                """
                SELECT assignment_ref
                FROM trusted_agent_workspace_leases
                WHERE id = ?
                """,
                (legacy_id,),
            ).fetchone()[0]
            is None
        )
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                """
                UPDATE trusted_agent_workspace_leases
                SET assignment_ref = '/srv/private/workspace'
                WHERE id = ?
                """,
                (legacy_id,),
            )

        database.execute(
            """
            UPDATE trusted_agent_workspace_leases
            SET state = 'revoked',
                terminal_at = 20,
                updated_at = 20,
                terminal_reason = 'migration_cleanup'
            WHERE id = ?
            """,
            (legacy_id,),
        )
        operation_id = f"talop_{'f' * 32}"
        database.execute(
            """
            INSERT INTO trusted_agent_lease_operations (
                id,
                owner_user_id,
                owner_tenant_id,
                lease_id,
                operation_kind,
                idempotency_key_hash,
                request_hash,
                response_json,
                created_at
            ) VALUES (
                ?, ?, ?, ?, 'revoke', ?, ?, '{}', 20
            )
            """,
            (
                operation_id,
                scope.owner_user_id,
                scope.owner_tenant_id,
                legacy_id,
                f"sha256:{'1' * 64}",
                f"sha256:{'2' * 64}",
            ),
        )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            database.execute(
                """
                UPDATE trusted_agent_lease_operations
                SET response_json = '{"changed":true}'
                WHERE id = ?
                """,
                (operation_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            database.execute(
                "DELETE FROM trusted_agent_lease_operations WHERE id = ?",
                (operation_id,),
            )
        assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        database.close()


def test_issue_claim_renew_fence_and_terminalize_are_exactly_idempotent(
    tmp_path: Path,
) -> None:
    database, scope = _database_and_scope(tmp_path / "lease-lifecycle.db")
    try:
        with pytest.raises(ValueError, match="now"):
            issue_trusted_agent_lease(
                database,
                scope=scope,
                idempotency_key="issue-invalid-time-0001",
                ttl_seconds=30,
                now=100.5,  # type: ignore[arg-type]
            )
        issued = issue_trusted_agent_lease(
            database,
            scope=scope,
            idempotency_key="issue-primary-00000001",
            ttl_seconds=30,
            now=100,
        )
        replayed_issue = issue_trusted_agent_lease(
            database,
            scope=scope,
            idempotency_key="issue-primary-00000001",
            ttl_seconds=30,
            now=105,
        )
        assert replayed_issue.id == issued.id
        assert issued.state == "active"
        assert issued.claim_owner is None
        assert issued.fencing_token == 1
        assert issued.expires_at == 130
        with pytest.raises(
            TrustedAgentLeaseError,
            match="Idempotency",
        ) as idempotency_conflict:
            issue_trusted_agent_lease(
                database,
                scope=scope,
                idempotency_key="issue-primary-00000001",
                ttl_seconds=31,
                now=105,
            )
        assert (
            idempotency_conflict.value.code
            == "trusted_agent_lease_idempotency_conflict"
        )

        competing_scope = replace(
            scope,
            assignment_ref="run_assignment_competing",
        )
        with pytest.raises(TrustedAgentLeaseError) as concurrency_conflict:
            issue_trusted_agent_lease(
                database,
                scope=competing_scope,
                idempotency_key="issue-competing-000001",
                ttl_seconds=30,
                now=101,
            )
        assert (
            concurrency_conflict.value.code
            == "trusted_agent_lease_concurrency_conflict"
        )
        assert concurrency_conflict.value.retryable is True

        claimed = claim_or_renew_trusted_agent_lease(
            database,
            lease_id=issued.id,
            scope=scope,
            claim_owner="worker-primary",
            claim_token=CLAIM_TOKEN_A,
            idempotency_key="claim-primary-00000001",
            ttl_seconds=30,
            now=101,
        )
        assert claimed.claim_owner == "worker-primary"
        assert claimed.fencing_token == 1
        assert claimed.expires_at == 131
        replayed_claim = claim_or_renew_trusted_agent_lease(
            database,
            lease_id=issued.id,
            scope=scope,
            claim_owner="worker-primary",
            claim_token=CLAIM_TOKEN_A,
            idempotency_key="claim-primary-00000001",
            ttl_seconds=30,
            now=102,
        )
        assert replayed_claim.expires_at == 131

        renewed = claim_or_renew_trusted_agent_lease(
            database,
            lease_id=issued.id,
            scope=scope,
            claim_owner="worker-primary",
            claim_token=CLAIM_TOKEN_A,
            idempotency_key="renew-primary-00000001",
            ttl_seconds=30,
            now=110,
        )
        assert renewed.fencing_token == 1
        assert renewed.expires_at == 140
        fenced = fence_trusted_agent_lease(
            database,
            lease_id=issued.id,
            scope=scope,
            claim_owner="worker-primary",
            claim_token=CLAIM_TOKEN_A,
            fencing_token=renewed.fencing_token,
            now=120,
        )
        assert fenced.id == issued.id
        with pytest.raises(TrustedAgentLeaseError) as wrong_token:
            fence_trusted_agent_lease(
                database,
                lease_id=issued.id,
                scope=scope,
                claim_owner="worker-primary",
                claim_token=CLAIM_TOKEN_B,
                fencing_token=renewed.fencing_token,
                now=120,
            )
        assert wrong_token.value.code == "trusted_agent_lease_fenced"

        released = terminalize_trusted_agent_lease(
            database,
            lease_id=issued.id,
            scope=scope,
            claim_owner="worker-primary",
            claim_token=CLAIM_TOKEN_A,
            fencing_token=renewed.fencing_token,
            terminal_state="released",
            reason="run_completed",
            idempotency_key="terminal-primary-00001",
            now=120,
        )
        replayed_release = terminalize_trusted_agent_lease(
            database,
            lease_id=issued.id,
            scope=scope,
            claim_owner="worker-primary",
            claim_token=CLAIM_TOKEN_A,
            fencing_token=renewed.fencing_token,
            terminal_state="released",
            reason="run_completed",
            idempotency_key="terminal-primary-00001",
            now=121,
        )
        assert released.state == "released"
        assert replayed_release == released
        with pytest.raises(TrustedAgentLeaseError) as terminal_fence:
            fence_trusted_agent_lease(
                database,
                lease_id=issued.id,
                scope=scope,
                claim_owner="worker-primary",
                claim_token=CLAIM_TOKEN_A,
                fencing_token=renewed.fencing_token,
                now=121,
            )
        assert terminal_fence.value.code == "trusted_agent_lease_fenced"

        next_lease = issue_trusted_agent_lease(
            database,
            scope=competing_scope,
            idempotency_key="issue-competing-000002",
            ttl_seconds=30,
            now=121,
        )
        assert next_lease.fencing_token == 2
        assert (
            database.execute(
                """
                SELECT COUNT(*)
                FROM trusted_agent_workspace_leases
                WHERE state = 'active'
                """
            ).fetchone()[0]
            == 1
        )
        assert (
            database.execute(
                "SELECT COUNT(*) FROM trusted_agent_lease_operations"
            ).fetchone()[0]
            == 5
        )
        dump = "\n".join(database.iterdump())
        assert CLAIM_TOKEN_A not in dump
        assert "issue-primary-00000001" not in dump
    finally:
        database.close()


def test_elapsed_takeover_increments_fence_and_revoke_survives_epoch_change(
    tmp_path: Path,
) -> None:
    database, scope = _database_and_scope(tmp_path / "lease-takeover.db")
    try:
        issued = issue_trusted_agent_lease(
            database,
            scope=scope,
            idempotency_key="issue-takeover-000001",
            ttl_seconds=5,
            now=100,
        )
        first_claim = claim_or_renew_trusted_agent_lease(
            database,
            lease_id=issued.id,
            scope=scope,
            claim_owner="worker-first",
            claim_token=CLAIM_TOKEN_A,
            idempotency_key="claim-takeover-000001",
            ttl_seconds=5,
            now=100,
        )
        with pytest.raises(TrustedAgentLeaseError) as busy:
            claim_or_renew_trusted_agent_lease(
                database,
                lease_id=issued.id,
                scope=scope,
                claim_owner="worker-second",
                claim_token=CLAIM_TOKEN_B,
                idempotency_key="claim-takeover-000002",
                ttl_seconds=5,
                now=104,
            )
        assert busy.value.code == "trusted_agent_lease_busy"

        takeover = claim_or_renew_trusted_agent_lease(
            database,
            lease_id=issued.id,
            scope=scope,
            claim_owner="worker-second",
            claim_token=CLAIM_TOKEN_B,
            idempotency_key="claim-takeover-000003",
            ttl_seconds=10,
            now=106,
        )
        assert first_claim.fencing_token == 1
        assert takeover.fencing_token == 2
        with pytest.raises(TrustedAgentLeaseError) as old_fence:
            fence_trusted_agent_lease(
                database,
                lease_id=issued.id,
                scope=scope,
                claim_owner="worker-first",
                claim_token=CLAIM_TOKEN_A,
                fencing_token=first_claim.fencing_token,
                now=107,
            )
        assert old_fence.value.code == "trusted_agent_lease_fenced"
        with pytest.raises(TrustedAgentLeaseError) as old_replay:
            claim_or_renew_trusted_agent_lease(
                database,
                lease_id=issued.id,
                scope=scope,
                claim_owner="worker-first",
                claim_token=CLAIM_TOKEN_A,
                idempotency_key="claim-takeover-000001",
                ttl_seconds=5,
                now=107,
            )
        assert old_replay.value.code == "trusted_agent_lease_fenced"
        assert (
            fence_trusted_agent_lease(
                database,
                lease_id=issued.id,
                scope=scope,
                claim_owner="worker-second",
                claim_token=CLAIM_TOKEN_B,
                fencing_token=takeover.fencing_token,
                now=107,
            ).fencing_token
            == 2
        )

        database.execute(
            """
            UPDATE trusted_agent_profiles
            SET profile_epoch = 2,
                revision = 2,
                updated_at = 108
            WHERE id = ?
            """,
            (scope.profile_id,),
        )
        with pytest.raises(TrustedAgentLeaseError) as stale_scope:
            fence_trusted_agent_lease(
                database,
                lease_id=issued.id,
                scope=scope,
                claim_owner="worker-second",
                claim_token=CLAIM_TOKEN_B,
                fencing_token=takeover.fencing_token,
                now=108,
            )
        assert (
            stale_scope.value.code
            == "trusted_agent_lease_scope_changed"
        )

        revoked = revoke_trusted_agent_lease(
            database,
            lease_id=issued.id,
            scope=scope,
            reason="profile_epoch_changed",
            idempotency_key="revoke-takeover-00001",
            now=108,
        )
        replayed_revoke = revoke_trusted_agent_lease(
            database,
            lease_id=issued.id,
            scope=scope,
            reason="profile_epoch_changed",
            idempotency_key="revoke-takeover-00001",
            now=109,
        )
        assert revoked.state == "revoked"
        assert replayed_revoke == revoked
        with pytest.raises(TrustedAgentLeaseError) as stale_issue:
            issue_trusted_agent_lease(
                database,
                scope=replace(
                    scope,
                    assignment_ref="run_assignment_stale",
                ),
                idempotency_key="issue-stale-scope-0001",
                ttl_seconds=10,
                now=109,
            )
        assert stale_issue.value.code == "trusted_agent_lease_scope_changed"

        current_scope = replace(
            scope,
            profile_epoch=2,
            assignment_ref="run_assignment_expiring",
        )
        expiring = issue_trusted_agent_lease(
            database,
            scope=current_scope,
            idempotency_key="issue-expiring-0000001",
            ttl_seconds=5,
            now=110,
        )
        expiring_claim = claim_or_renew_trusted_agent_lease(
            database,
            lease_id=expiring.id,
            scope=current_scope,
            claim_owner="worker-expiring",
            claim_token=CLAIM_TOKEN_A,
            idempotency_key="claim-expiring-0000001",
            ttl_seconds=5,
            now=110,
        )
        expired = terminalize_trusted_agent_lease(
            database,
            lease_id=expiring.id,
            scope=current_scope,
            claim_owner="worker-expiring",
            claim_token=CLAIM_TOKEN_A,
            fencing_token=expiring_claim.fencing_token,
            terminal_state="expired",
            reason="lease_timeout",
            idempotency_key="terminal-expiring-0001",
            now=115,
        )
        assert expired.state == "expired"
        assert expired.terminal_reason == "lease_timeout"
    finally:
        database.close()


def test_issue_expires_abandoned_capacity_and_concurrent_issue_stays_single(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "lease-concurrency.db"
    database, scope = _database_and_scope(database_path)
    try:
        abandoned = issue_trusted_agent_lease(
            database,
            scope=scope,
            idempotency_key="issue-abandoned-000001",
            ttl_seconds=5,
            now=100,
        )
        replacement_scope = replace(
            scope,
            assignment_ref="run_assignment_replacement",
        )
        replacement = issue_trusted_agent_lease(
            database,
            scope=replacement_scope,
            idempotency_key="issue-replacement-0001",
            ttl_seconds=10,
            now=106,
        )
        abandoned_state = database.execute(
            """
            SELECT state, terminal_reason
            FROM trusted_agent_workspace_leases
            WHERE id = ?
            """,
            (abandoned.id,),
        ).fetchone()
        assert tuple(abandoned_state) == ("expired", "lease_timeout")
        assert replacement.fencing_token == 2
        terminalize_trusted_agent_lease(
            database,
            lease_id=replacement.id,
            scope=replacement_scope,
            claim_owner="worker-replacement",
            claim_token=CLAIM_TOKEN_A,
            fencing_token=claim_or_renew_trusted_agent_lease(
                database,
                lease_id=replacement.id,
                scope=replacement_scope,
                claim_owner="worker-replacement",
                claim_token=CLAIM_TOKEN_A,
                idempotency_key="claim-replacement-00001",
                ttl_seconds=10,
                now=106,
            ).fencing_token,
            terminal_state="released",
            reason="run_completed",
            idempotency_key="terminal-replacement-01",
            now=107,
        )
    finally:
        database.close()

    barrier = threading.Barrier(2)
    scopes = (
        replace(scope, assignment_ref="run_concurrent_a"),
        replace(scope, assignment_ref="run_concurrent_b"),
    )

    def issue(index: int) -> tuple[str, str]:
        connection = connect_database(database_path)
        try:
            barrier.wait(timeout=5)
            try:
                value = issue_trusted_agent_lease(
                    connection,
                    scope=scopes[index],
                    idempotency_key=f"issue-concurrent-{index:08d}",
                    ttl_seconds=30,
                    now=200,
                )
            except TrustedAgentLeaseError as error:
                return ("error", error.code)
            return ("issued", value.id)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(issue, (0, 1)))
    assert sum(result[0] == "issued" for result in results) == 1
    assert {
        result[1]
        for result in results
        if result[0] == "error"
    } == {"trusted_agent_lease_concurrency_conflict"}

    database = connect_database(database_path)
    try:
        assert (
            database.execute(
                """
                SELECT COUNT(*)
                FROM trusted_agent_workspace_leases
                WHERE state = 'active'
                """
            ).fetchone()[0]
            == 1
        )
    finally:
        database.close()
