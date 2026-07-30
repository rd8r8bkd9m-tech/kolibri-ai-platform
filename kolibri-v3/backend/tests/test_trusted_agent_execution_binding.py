from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.chat.errors import ChatPolicyError
from app.chat.cancellation import cancel_run
from app.chat.execution_adapter import PreparedChatExecution
from app.chat.models import AgUiRunInput
from app.chat.service import accept_run
from app.config import Settings
from app.database import connect_database
from app.home_runtime import HomeRuntimeResponse, ProductRunExecutionError
from app.main import create_app
from app.owner_bootstrap import promote_registered_owner
from app.product_run_worker import (
    ProductRunStore,
    StaleLeaseError,
)
from app.schemas import AgentProfile, UserRole, UserSession


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"
OWNER_EMAIL = "owner@example.com"
PROFILE_ID = "tap_" + ("a" * 32)
BINDING_ID = "wsb_" + ("b" * 32)


def _settings(database_path: Path) -> Settings:
    return replace(
        Settings.for_testing(database_url=database_path),
        direct_model_runtime_enabled=False,
        developer_agent_enabled=False,
        developer_workspace_root=None,
    )


def _owner(settings: Settings) -> UserSession:
    with TestClient(create_app(settings)) as client:
        registered = client.post(
            "/v1/auth/register",
            headers=ORIGIN,
            json={
                "email": OWNER_EMAIL,
                "name": "Trusted Owner",
                "password": PASSWORD,
            },
        )
        assert registered.status_code == 201
        user = registered.json()["user"]
        promote_registered_owner(
            settings,
            email=OWNER_EMAIL,
        )
    return UserSession(
        user_id=user["id"],
        tenant_id=user["tenantId"],
        role=UserRole.OWNER,
        preferred_agent_profile=AgentProfile.AUTO,
        preferred_model=None,
        preferred_reasoning_effort=None,
        preferred_service_tier=None,
        email=user["email"],
        name=user["name"],
        is_platform_owner=True,
        platform_capabilities=(
            "platform.admin",
            "chat.developer.request",
            "chat.use",
        ),
    )


def _create_trusted_profile(
    settings: Settings,
    identity: UserSession,
    *,
    runtime_profile: str = "mimo-code",
) -> None:
    database = connect_database(settings.database_url)
    try:
        authority = database.execute(
            """
            SELECT authority_epoch
            FROM platform_authority_grants
            WHERE authority_id = 'platform_owner'
              AND user_id = ? AND tenant_id = ?
              AND active = 1
            """,
            (identity.user_id, identity.tenant_id),
        ).fetchone()
        assert authority is not None
        authority_epoch = int(authority["authority_epoch"])
        database.execute(
            """
            INSERT INTO trusted_agent_workspace_bindings (
                id, authority_id, owner_user_id, owner_tenant_id,
                authority_epoch, server_ref, environment,
                fingerprint_token, lifecycle_status, workspace_epoch,
                revision, created_at, updated_at, created_by_user_id
            ) VALUES (
                ?, 'platform_owner', ?, ?, ?,
                ?, 'development', ?, 'active', 1, 1,
                unixepoch(), unixepoch(), ?
            )
            """,
            (
                BINDING_ID,
                identity.user_id,
                identity.tenant_id,
                authority_epoch,
                "wsref_" + ("c" * 32),
                "sha256:" + ("d" * 64),
                identity.user_id,
            ),
        )
        database.execute(
            """
            INSERT INTO trusted_agent_profiles (
                id, authority_id, owner_user_id, owner_tenant_id,
                authority_epoch, workspace_binding_id,
                workspace_binding_epoch, display_name, runtime_profile,
                agent_card_id, agent_card_version, capabilities_json,
                tool_policy_id, access_mode, sandbox_profile,
                approval_policy, approvals_reviewer, max_concurrency,
                lifecycle_status, profile_epoch, revision,
                created_at, updated_at, created_by_user_id
            ) VALUES (
                ?, 'platform_owner', ?, ?, ?, ?, 1,
                'Owner developer agent', ?, 'owner-developer', 1,
                '["developer.runtime.execute"]', 'developer.full.v1',
                'full', 'danger-full-access', 'never', NULL, 1,
                'active', 1, 1, unixepoch(), unixepoch(), ?
            )
            """,
            (
                PROFILE_ID,
                identity.user_id,
                identity.tenant_id,
                authority_epoch,
                BINDING_ID,
                runtime_profile,
                identity.user_id,
            ),
        )
    finally:
        database.close()


def _run_input(
    *,
    run_id: str,
    runtime_profile: str = "mimo-code",
    access_mode: str = "full",
) -> AgUiRunInput:
    return AgUiRunInput.model_validate(
        {
            "threadId": f"thread_{run_id}",
            "runId": run_id,
            "state": None,
            "messages": [
                {
                    "id": f"message_{run_id}",
                    "role": "user",
                    "content": "Проверь репозиторий и выполни задачу.",
                }
            ],
            "tools": [],
            "context": [],
            "forwardedProps": {
                "agentProfile": runtime_profile,
                "executionMode": "developer",
                "accessMode": access_mode,
            },
        }
    )


def _prepared(run_input: AgUiRunInput) -> PreparedChatExecution:
    return PreparedChatExecution(
        execution_plane="home",
        runtime_profile=str(run_input.forwarded_props.agent_profile),
        model_id=None,
        reasoning_effort=None,
        service_tier=None,
    )


def _claim_promoted_v13_run(
    *,
    settings: Settings,
    identity: UserSession,
    client_run_id: str,
) -> tuple[ProductRunStore, object]:
    run_input = _run_input(run_id=client_run_id)
    database = connect_database(settings.database_url)
    try:
        accepted = accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=run_input,
            prepared=_prepared(run_input),
        )
    finally:
        database.close()

    store = ProductRunStore(settings.database_url)
    goal_claim = store.claim_next(
        worker_id="trusted-goal-worker",
        lease_seconds=30,
    )
    assert goal_claim is not None
    assert goal_claim.run_id == accepted.run_id
    command = json.loads(goal_claim.command_json)
    goal_id = str(command["payload"]["goal_id"])
    status = {
        "schema_id": "kolibri.product.goal.initialization_status",
        "schema_version": "1.0",
        "run_id": accepted.run_id,
        "goal_id": goal_id,
        "case_id": f"case_{goal_id}",
        "status": "initialized",
        "goal_version": 1,
        "case_version": 1,
        "error": None,
    }
    body = json.dumps(
        status,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    store.prepare_delivery(
        goal_claim,
        phase="goal_initialize",
        path="/v1/runtime/product-goal-initializations",
    )
    store.apply_goal_initialized(
        goal_claim,
        HomeRuntimeResponse(
            http_status=201,
            body_text=body,
            value=status,
        ),
        deadline_seconds=settings.product_run_command_deadline_seconds,
    )
    run_claim = store.claim_next(
        worker_id="trusted-run-worker",
        lease_seconds=30,
    )
    assert run_claim is not None
    assert run_claim.run_id == accepted.run_id
    promoted = json.loads(run_claim.command_json)
    assert promoted["payload_schema_version"] == "1.3"
    return store, run_claim


def test_active_trusted_profile_is_frozen_with_full_never_policy(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "trusted-binding.db")
    identity = _owner(settings)
    _create_trusted_profile(settings, identity)
    run_input = _run_input(run_id="run_trusted_binding_01")

    database = connect_database(settings.database_url)
    try:
        accepted = accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=run_input,
            prepared=_prepared(run_input),
        )
        context = database.execute(
            """
            SELECT access_mode, sandbox_profile, approval_policy,
                   approvals_reviewer, trusted_agent_profile_id,
                   trusted_agent_profile_epoch,
                   trusted_agent_workspace_binding_id,
                   trusted_agent_workspace_binding_epoch
            FROM chat_run_execution_contexts
            WHERE tenant_id = ? AND run_id = ?
            """,
            (identity.tenant_id, accepted.run_id),
        ).fetchone()
    finally:
        database.close()

    assert context is not None
    assert tuple(context) == (
        "full",
        "danger-full-access",
        "never",
        None,
        PROFILE_ID,
        1,
        BINDING_ID,
        1,
    )


def test_goal_promotion_keeps_trusted_run_on_v1_3(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "trusted-worker-v13.db")
    identity = _owner(settings)
    _create_trusted_profile(settings, identity)
    run_input = _run_input(run_id="run_trusted_worker_v13_01")

    database = connect_database(settings.database_url)
    try:
        accepted = accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=run_input,
            prepared=_prepared(run_input),
        )
        context = database.execute(
            """
            SELECT *
            FROM chat_run_execution_contexts
            WHERE tenant_id = ? AND run_id = ?
            """,
            (identity.tenant_id, accepted.run_id),
        ).fetchone()
    finally:
        database.close()
    assert context is not None

    store = ProductRunStore(settings.database_url)
    claim = store.claim_next(
        worker_id="trusted-v13-worker",
        lease_seconds=30,
    )
    assert claim is not None
    promoted = store._fresh_run_command(
        initialize_command=json.loads(claim.command_json),
        runtime_profile="mimo-code",
        case_id="case_trusted_worker_v13_01",
        deadline_seconds=60,
        now=datetime.now(timezone.utc),
        execution_context=dict(context),
    )

    assert promoted["payload_schema_id"] == (
        "kolibri.product.run.execute.v1_3.command"
    )
    assert promoted["payload_schema_version"] == "1.3"
    assert {
        field_name: promoted["payload"][field_name]
        for field_name in (
            "trusted_agent_profile_id",
            "trusted_agent_profile_epoch",
            "trusted_agent_workspace_binding_id",
            "trusted_agent_workspace_binding_epoch",
        )
    } == {
        "trusted_agent_profile_id": PROFILE_ID,
        "trusted_agent_profile_epoch": 1,
        "trusted_agent_workspace_binding_id": BINDING_ID,
        "trusted_agent_workspace_binding_epoch": 1,
    }

    partial_context = dict(context)
    partial_context["trusted_agent_workspace_binding_epoch"] = None
    with pytest.raises(ProductRunExecutionError) as captured:
        store._fresh_run_command(
            initialize_command=json.loads(claim.command_json),
            runtime_profile="mimo-code",
            case_id="case_trusted_worker_v13_01",
            deadline_seconds=60,
            now=datetime.now(timezone.utc),
            execution_context=partial_context,
        )
    assert (
        captured.value.code
        == "trusted_agent_execution_binding_invalid"
    )


def test_active_profile_rejects_a_different_runtime_or_access_policy(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "trusted-mismatch.db")
    identity = _owner(settings)
    _create_trusted_profile(settings, identity)
    run_input = _run_input(
        run_id="run_trusted_mismatch_01",
        runtime_profile="codex-cli",
    )

    database = connect_database(settings.database_url)
    try:
        with pytest.raises(ChatPolicyError) as captured:
            accept_run(
                database,
                settings=settings,
                identity=identity,
                run_input=run_input,
                prepared=_prepared(run_input),
            )
        assert (
            captured.value.code
            == "trusted_agent_profile_selection_mismatch"
        )
        assert database.execute(
            "SELECT COUNT(*) FROM chat_runs"
        ).fetchone()[0] == 0
    finally:
        database.close()


def test_profile_revocation_blocks_worker_before_home_delivery(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "trusted-revoked.db")
    identity = _owner(settings)
    _create_trusted_profile(settings, identity)
    run_input = _run_input(run_id="run_trusted_revoked_01")
    database = connect_database(settings.database_url)
    try:
        accepted = accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=run_input,
            prepared=_prepared(run_input),
        )
    finally:
        database.close()

    store = ProductRunStore(settings.database_url)
    claim = store.claim_next(
        worker_id="trusted-binding-worker",
        lease_seconds=30,
    )
    assert claim is not None
    assert claim.run_id == accepted.run_id

    database = connect_database(settings.database_url)
    try:
        database.execute(
            """
            UPDATE trusted_agent_profiles
            SET lifecycle_status = 'revoked',
                profile_epoch = profile_epoch + 1,
                revision = revision + 1,
                updated_at = unixepoch(),
                revoked_at = unixepoch(),
                revoked_by_user_id = ?
            WHERE id = ?
            """,
            (identity.user_id, PROFILE_ID),
        )
    finally:
        database.close()

    with pytest.raises(ProductRunExecutionError) as captured:
        store.prepare_delivery(
            claim,
            phase="goal_initialize",
            path="/v1/runtime/product-goal-initializations",
        )
    assert captured.value.code == "trusted_agent_profile_changed"


def test_developer_runs_without_a_configured_profile_remain_compatible(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "trusted-legacy.db")
    identity = _owner(settings)
    run_input = _run_input(run_id="run_trusted_legacy_01")

    database = connect_database(settings.database_url)
    try:
        accepted = accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=run_input,
            prepared=_prepared(run_input),
        )
        context = database.execute(
            """
            SELECT trusted_agent_profile_id,
                   trusted_agent_profile_epoch,
                   trusted_agent_workspace_binding_id,
                   trusted_agent_workspace_binding_epoch
            FROM chat_run_execution_contexts
            WHERE tenant_id = ? AND run_id = ?
            """,
            (identity.tenant_id, accepted.run_id),
        ).fetchone()
    finally:
        database.close()

    assert context is not None
    assert tuple(context) == (None, None, None, None)


def test_bound_v13_lease_is_worker_only_idempotent_and_terminalized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path / "trusted-worker-lease.db")
    identity = _owner(settings)
    _create_trusted_profile(settings, identity)
    store, claim = _claim_promoted_v13_run(
        settings=settings,
        identity=identity,
        client_run_id="run_trusted_worker_lease_01",
    )
    monkeypatch.setattr(
        "app.product_run_worker.secrets.token_urlsafe",
        lambda _size: "-" + ("opaque" * 8),
    )

    lease = store.acquire_trusted_agent_lease(
        claim,
        worker_id="trusted-runtime-worker",
        ttl_seconds=30,
    )
    assert lease is not None
    assert lease.claim_token.startswith("talcap_-")
    replay = store.acquire_trusted_agent_lease(
        claim,
        worker_id="trusted-runtime-worker",
        ttl_seconds=30,
        previous=lease,
    )
    assert replay == lease
    assert lease.claim_token not in repr(lease)
    store.prepare_delivery(
        claim,
        phase="run_execute",
        path="/v1/runtime/product-text-runs",
    )
    store.fence_external_effect(claim, lease)

    command = json.loads(claim.command_json)
    status = {
        "schema_id": "kolibri.product.run.execution_status.v1_1",
        "schema_version": "1.1",
        "run_id": claim.run_id,
        "status": "succeeded",
        "runtime_profile": command["payload"]["runtime_profile"],
        "execution_id": "execution_trusted_worker_lease_01",
        "verification_status": "not_applicable",
        "result_text": "Готово.",
        "result_hash": "sha256:" + ("e" * 64),
        "evidence": None,
        "error": None,
    }
    outcome = store.apply_run_status(
        claim,
        HomeRuntimeResponse(
            http_status=200,
            body_text=json.dumps(
                status,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            value=status,
        ),
        poll_seconds=0.1,
        trusted_claim=lease,
    )
    assert outcome == "succeeded"

    database = connect_database(settings.database_url)
    try:
        persisted = database.execute(
            """
            SELECT state, assignment_ref, claim_token_hash, terminal_reason
            FROM trusted_agent_workspace_leases
            WHERE owner_tenant_id = ? AND assignment_ref = ?
            """,
            (identity.tenant_id, claim.run_id),
        ).fetchone()
        serialized = "\n".join(
            str(value)
            for value in database.execute(
                """
                SELECT response_json
                FROM trusted_agent_lease_operations
                WHERE owner_tenant_id = ?
                """,
                (identity.tenant_id,),
            ).fetchall()
        )
    finally:
        database.close()
    assert tuple(persisted)[:2] == ("released", claim.run_id)
    assert persisted["claim_token_hash"] != lease.claim_token
    assert persisted["terminal_reason"] == "run_succeeded"
    assert lease.claim_token not in serialized


def test_elapsed_worker_recovers_with_new_fence_and_stale_capability_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path / "trusted-worker-recovery.db")
    identity = _owner(settings)
    _create_trusted_profile(settings, identity)
    store, first_claim = _claim_promoted_v13_run(
        settings=settings,
        identity=identity,
        client_run_id="run_trusted_worker_recovery_01",
    )
    first_lease = store.acquire_trusted_agent_lease(
        first_claim,
        worker_id="trusted-worker-before-restart",
        ttl_seconds=30,
    )
    assert first_lease is not None

    database = connect_database(settings.database_url)
    try:
        database.execute(
            """
            UPDATE trusted_agent_workspace_leases
            SET expires_at = created_at + 1
            WHERE id = ?
            """,
            (first_lease.lease_id,),
        )
        future_epoch = int(
            database.execute(
                """
                SELECT expires_at + 1
                FROM trusted_agent_workspace_leases
                WHERE id = ?
                """,
                (first_lease.lease_id,),
            ).fetchone()[0]
        )
        database.execute(
            """
            UPDATE product_run_outbox
            SET lease_until = '1970-01-01T00:00:00+00:00'
            WHERE tenant_id = ? AND id = ?
            """,
            (first_claim.tenant_id, first_claim.outbox_id),
        )
    finally:
        database.close()
    monkeypatch.setattr(
        "app.product_run_worker._now",
        lambda: datetime.fromtimestamp(future_epoch, timezone.utc),
    )

    recovered_claim = store.claim_next(
        worker_id="trusted-worker-after-restart",
        lease_seconds=30,
    )
    assert recovered_claim is not None
    recovered_lease = store.acquire_trusted_agent_lease(
        recovered_claim,
        worker_id="trusted-worker-after-restart",
        ttl_seconds=30,
    )
    assert recovered_lease is not None
    assert recovered_lease.lease_id == first_lease.lease_id
    assert recovered_lease.fencing_token > first_lease.fencing_token

    with pytest.raises(ProductRunExecutionError) as stale:
        store.fence_external_effect(recovered_claim, first_lease)
    assert stale.value.code == "trusted_agent_lease_fenced"
    store.fence_external_effect(recovered_claim, recovered_lease)


def test_cancellation_revokes_bound_lease_and_fences_stale_commit(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "trusted-worker-cancel.db")
    identity = _owner(settings)
    _create_trusted_profile(settings, identity)
    store, claim = _claim_promoted_v13_run(
        settings=settings,
        identity=identity,
        client_run_id="run_trusted_worker_cancel_01",
    )
    lease = store.acquire_trusted_agent_lease(
        claim,
        worker_id="trusted-worker-cancel",
        ttl_seconds=30,
    )
    assert lease is not None

    database = connect_database(settings.database_url)
    try:
        cancelled = cancel_run(
            database,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            run_id=claim.run_id,
        )
        persisted = database.execute(
            """
            SELECT state, terminal_reason
            FROM trusted_agent_workspace_leases
            WHERE id = ?
            """,
            (lease.lease_id,),
        ).fetchone()
    finally:
        database.close()
    assert cancelled is not None and cancelled.cancelled
    assert tuple(persisted) == ("revoked", "run_cancelled")

    command = json.loads(claim.command_json)
    status = {
        "schema_id": "kolibri.product.run.execution_status.v1_1",
        "schema_version": "1.1",
        "run_id": claim.run_id,
        "status": "accepted",
        "runtime_profile": command["payload"]["runtime_profile"],
        "execution_id": "execution_trusted_worker_cancel_01",
        "verification_status": "not_applicable",
        "result_text": None,
        "result_hash": None,
        "evidence": None,
        "error": None,
    }
    with pytest.raises(StaleLeaseError):
        store.apply_run_status(
            claim,
            HomeRuntimeResponse(
                http_status=202,
                body_text=json.dumps(status),
                value=status,
            ),
            poll_seconds=0.1,
            trusted_claim=lease,
        )


def test_administrative_revocation_is_terminal_without_worker_crash(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "trusted-worker-admin-revoke.db")
    identity = _owner(settings)
    _create_trusted_profile(settings, identity)
    store, claim = _claim_promoted_v13_run(
        settings=settings,
        identity=identity,
        client_run_id="run_trusted_worker_admin_revoke_01",
    )
    lease = store.acquire_trusted_agent_lease(
        claim,
        worker_id="trusted-worker-admin-revoke",
        ttl_seconds=30,
    )
    assert lease is not None

    database = connect_database(settings.database_url)
    try:
        database.execute(
            """
            UPDATE trusted_agent_workspace_leases
            SET state = 'revoked',
                terminal_at = unixepoch(),
                terminal_reason = 'authority_changed',
                updated_at = unixepoch()
            WHERE id = ? AND state = 'active'
            """,
            (lease.lease_id,),
        )
        database.execute(
            """
            UPDATE trusted_agent_profiles
            SET lifecycle_status = 'revoked',
                profile_epoch = profile_epoch + 1,
                revision = revision + 1,
                revoked_at = unixepoch(),
                revoked_by_user_id = ?,
                updated_at = unixepoch()
            WHERE id = ?
            """,
            (identity.user_id, PROFILE_ID),
        )
    finally:
        database.close()

    with pytest.raises(ProductRunExecutionError) as captured:
        store.fence_external_effect(claim, lease)
    assert captured.value.code == "trusted_agent_profile_changed"
    outcome = store.record_failure(
        claim,
        captured.value,
        retry_base_seconds=0.1,
        retry_max_seconds=1.0,
        trusted_claim=lease,
    )
    assert outcome == "failed"

    database = connect_database(settings.database_url)
    try:
        row = database.execute(
            """
            SELECT state, last_error_code
            FROM product_run_outbox
            WHERE tenant_id = ? AND run_id = ?
            """,
            (identity.tenant_id, claim.run_id),
        ).fetchone()
    finally:
        database.close()
    assert tuple(row) == ("blocked", "trusted_agent_profile_changed")


def test_bound_run_never_drains_through_v12_downgrade(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "trusted-worker-downgrade.db")
    identity = _owner(settings)
    _create_trusted_profile(settings, identity)
    store, claim = _claim_promoted_v13_run(
        settings=settings,
        identity=identity,
        client_run_id="run_trusted_worker_downgrade_01",
    )
    command = json.loads(claim.command_json)
    command["payload_schema_id"] = (
        "kolibri.product.run.execute.v1_2.command"
    )
    command["payload_schema_version"] = "1.2"
    command["payload"]["schema_id"] = (
        "kolibri.product.run.execute.v1_2.command"
    )
    command["payload"]["schema_version"] = "1.2"
    for field_name in (
        "trusted_agent_profile_id",
        "trusted_agent_profile_epoch",
        "trusted_agent_workspace_binding_id",
        "trusted_agent_workspace_binding_epoch",
    ):
        command["payload"].pop(field_name)
    from app.chat.service import canonical_command_hash, canonical_json

    command["idempotency"]["canonical_request_hash"] = (
        "sha256:" + ("0" * 64)
    )
    command["idempotency"]["canonical_request_hash"] = (
        canonical_command_hash(command)
    )
    command_json = canonical_json(command)
    from app.chat.service import sha256_text

    database = connect_database(settings.database_url)
    try:
        database.execute(
            """
            UPDATE product_run_outbox
            SET command_json = ?, command_hash = ?
            WHERE tenant_id = ? AND id = ?
            """,
            (
                command_json,
                sha256_text(command_json),
                claim.tenant_id,
                claim.outbox_id,
            ),
        )
    finally:
        database.close()
    downgraded = replace(
        claim,
        command_json=command_json,
        command_hash=sha256_text(command_json),
    )
    with pytest.raises(ProductRunExecutionError) as captured:
        store.acquire_trusted_agent_lease(
            downgraded,
            worker_id="trusted-worker-downgrade",
            ttl_seconds=30,
        )
    assert captured.value.code == "trusted_agent_command_downgrade"
