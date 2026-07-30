from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.chat.errors import ChatRuntimeUnavailableError
from app.chat.models import AgUiRunInput
from app.chat.execution_adapter import PreparedChatExecution
from app.chat.service import accept_run
from app.config import (
    Settings,
    _parse_capabilities,
)
from app.database import connect_database
from app.home_runtime import (
    HomeRuntimeResponse,
    ProductRunExecutionError,
    _validate_product_command,
    validate_product_execution_status,
)
from app.main import create_app
from app.owner_bootstrap import promote_registered_owner
from app.product_run_worker import ProductRunStore
from app.schemas import AgentProfile, UserRole, UserSession


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"


def _settings(database_path: Path, workspace: Path) -> Settings:
    return replace(
        Settings.for_testing(database_url=database_path),
        direct_model_runtime_enabled=True,
        developer_agent_enabled=True,
        developer_workspace_root=workspace,
    )


def _home_settings(database_path: Path) -> Settings:
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
                "email": "owner@example.com",
                "name": "Owner",
                "password": PASSWORD,
            },
        )
        assert registered.status_code == 201
        user = registered.json()["user"]
        promote_registered_owner(settings, email="owner@example.com")
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


def _run_input(
    *,
    run_id: str,
    messages: list[dict[str, str]],
    execution_mode: str,
    access_mode: str,
    agent_profile: str | None = None,
) -> AgUiRunInput:
    return AgUiRunInput.model_validate(
        {
            "threadId": "thread_developer_product_01",
            "runId": run_id,
            "state": None,
            "messages": messages,
            "tools": [],
            "context": [],
            "forwardedProps": {
                "agentProfile": (
                    agent_profile
                    or (
                        "mimo-code"
                        if execution_mode == "developer"
                        else "auto"
                    )
                ),
                "executionMode": execution_mode,
                "accessMode": access_mode,
            },
        }
    )


def _prepared(
    settings: Settings,
    run_input: AgUiRunInput,
) -> PreparedChatExecution:
    return PreparedChatExecution(
        execution_plane=(
            "direct" if settings.direct_model_runtime_enabled else "home"
        ),
        runtime_profile=(
            run_input.forwarded_props.agent_profile or "auto"
        ),
        model_id=None,
        reasoning_effort=None,
        service_tier=None,
    )


def _accept_existing_project_developer_run(
    *,
    settings: Settings,
    identity: UserSession,
) -> tuple[str, str]:
    first_message = {
        "id": "message_standard_seed_01",
        "role": "user",
        "content": "Создай обычный проект.",
    }
    developer_message = {
        "id": "message_developer_product_01",
        "role": "user",
        "content": "Проверь репозиторий.",
    }
    database = connect_database(settings.database_url)
    try:
        accepted_standard = accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=(standard_input := _run_input(
                run_id="run_standard_seed_01",
                messages=[first_message],
                execution_mode="standard",
                access_mode="standard",
            )),
            prepared=_prepared(settings, standard_input),
        )
    finally:
        database.close()

    if not settings.direct_model_runtime_enabled:
        _complete_goal_initialization(
            settings=settings,
            expected_run_id=accepted_standard.run_id,
        )
        database = connect_database(settings.database_url)
        try:
            database.execute(
                """
                UPDATE product_run_outbox
                SET state = 'completed',
                    completed_at = updated_at
                WHERE tenant_id = ? AND run_id = ?
                """,
                (identity.tenant_id, accepted_standard.run_id),
            )
        finally:
            database.close()

    database = connect_database(settings.database_url)
    try:
        accepted_developer = accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=(developer_input := _run_input(
                run_id="run_developer_product_01",
                messages=[first_message, developer_message],
                execution_mode="developer",
                access_mode="full",
            )),
            prepared=_prepared(settings, developer_input),
        )
    finally:
        database.close()
    return accepted_standard.run_id, accepted_developer.run_id


def _complete_goal_initialization(
    *,
    settings: Settings,
    expected_run_id: str,
) -> None:
    store = ProductRunStore(settings.database_url)
    claim = store.claim_next(worker_id="worker_goal_test", lease_seconds=30)
    assert claim is not None
    assert claim.run_id == expected_run_id
    assert claim.phase == "goal_required"
    store.prepare_delivery(
        claim,
        phase="goal_initialize",
        path="/v1/runtime/product-goal-initializations",
    )
    command = json.loads(claim.command_json)
    goal_id = str(command["payload"]["goal_id"])
    status = {
        "schema_id": "kolibri.product.goal.initialization_status",
        "schema_version": "1.0",
        "run_id": expected_run_id,
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
    store.apply_goal_initialized(
        claim,
        HomeRuntimeResponse(http_status=201, body_text=body, value=status),
        deadline_seconds=settings.product_run_command_deadline_seconds,
    )


def test_development_capability_default_is_not_a_production_default() -> None:
    development = _parse_capabilities(
        None,
        include_developer_default=True,
    )
    production = _parse_capabilities(
        None,
        include_developer_default=False,
    )

    assert "product.developer.run.execute.request" in development
    assert "product.developer.run.execute.request" not in production


def test_explicit_production_capability_routes_without_local_adapter(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "production-developer-outbox.db"
    test_settings = Settings.for_testing(database_url=database_path)
    identity = _owner(test_settings)
    settings = replace(
        test_settings,
        environment="production",
        allowed_origins=("https://app.example.test",),
        cookie_secure=True,
        direct_model_runtime_enabled=False,
        developer_agent_enabled=False,
        developer_workspace_root=None,
    )

    database = connect_database(settings.database_url)
    try:
        accepted = accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=(run_input := _run_input(
                run_id="run_production_developer_01",
                messages=[
                    {
                        "id": "message_production_developer_01",
                        "role": "user",
                        "content": "Проверь production-репозиторий.",
                    }
                ],
                execution_mode="developer",
                access_mode="auto",
            )),
            prepared=_prepared(settings, run_input),
        )
        row = database.execute(
            """
            SELECT command_kind, phase, state
            FROM product_run_outbox
            WHERE tenant_id = ? AND run_id = ?
            """,
            (identity.tenant_id, accepted.run_id),
        ).fetchone()
    finally:
        database.close()

    assert row is not None
    assert tuple(row) == (
        "product.goal.initialize",
        "goal_required",
        "queued",
    )


def test_production_developer_run_fails_closed_without_capability(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "production-developer-denied.db"
    test_settings = Settings.for_testing(database_url=database_path)
    identity = _owner(test_settings)
    settings = replace(
        test_settings,
        environment="production",
        allowed_origins=("https://app.example.test",),
        cookie_secure=True,
        product_authority_capabilities=_parse_capabilities(
            None,
            include_developer_default=False,
        ),
        direct_model_runtime_enabled=False,
        developer_agent_enabled=False,
        developer_workspace_root=None,
    )

    database = connect_database(settings.database_url)
    try:
        with pytest.raises(ChatRuntimeUnavailableError):
            accept_run(
                database,
                settings=settings,
                identity=identity,
                run_input=(run_input := _run_input(
                    run_id="run_production_developer_denied_01",
                    messages=[
                        {
                            "id": "message_production_developer_denied_01",
                            "role": "user",
                            "content": "Запусти developer runtime.",
                        }
                    ],
                    execution_mode="developer",
                    access_mode="auto",
                )),
                prepared=_prepared(settings, run_input),
            )
        assert database.execute(
            "SELECT COUNT(*) FROM chat_runs"
        ).fetchone()[0] == 0
    finally:
        database.close()


def test_home_plane_developer_run_uses_v1_2_outbox(
    tmp_path: Path,
) -> None:
    settings = _home_settings(tmp_path / "developer-outbox.db")
    identity = _owner(settings)
    standard_run_id, developer_run_id = (
        _accept_existing_project_developer_run(
            settings=settings,
            identity=identity,
        )
    )
    database = connect_database(settings.database_url)
    try:
        assert database.execute(
            """
            SELECT COUNT(*)
            FROM product_run_outbox
            WHERE run_id = ? AND state = 'completed'
            """,
            (standard_run_id,),
        ).fetchone()[0] == 1
        row = database.execute(
            """
            SELECT command_json, max_attempts, state
            FROM product_run_outbox
            WHERE tenant_id = ? AND run_id = ?
            """,
            (identity.tenant_id, developer_run_id),
        ).fetchone()
        context = database.execute(
            """
            SELECT execution_mode, authority_role, workspace_ref, access_mode,
                   sandbox_profile, approval_policy, approvals_reviewer,
                   model_id, reasoning_effort, service_tier
            FROM chat_run_execution_contexts
            WHERE tenant_id = ? AND run_id = ?
            """,
            (identity.tenant_id, developer_run_id),
        ).fetchone()
    finally:
        database.close()

    assert row is not None
    assert (row["max_attempts"], row["state"]) == (1, "queued")
    command = json.loads(str(row["command_json"]))
    _validate_product_command(command)
    assert command["payload_schema_id"] == (
        "kolibri.product.run.execute.v1_2.command"
    )
    assert command["payload"]["execution_mode"] == "developer"
    assert command["payload"]["requester_role"] == "owner"
    assert command["payload"]["runtime_profile"] == "mimo-code"
    assert command["payload"]["model"] is None
    assert command["payload"]["reasoning_effort"] is None
    assert command["payload"]["service_tier"] is None
    assert command["payload"]["workspace_ref"] == context["workspace_ref"]
    assert command["payload"]["access_mode"] == context["access_mode"]
    assert command["payload"]["sandbox"] == context["sandbox_profile"]
    assert (
        command["payload"]["approval_policy"]
        == context["approval_policy"]
    )
    assert command["payload"]["reviewer"] == context["approvals_reviewer"]
    assert "product.developer.run.execute.request" in (
        command["identity"]["authority"]["capabilities"]
    )


def test_goal_initialization_promotes_developer_run_to_v1_2_once(
    tmp_path: Path,
) -> None:
    settings = _home_settings(tmp_path / "developer-goal.db")
    identity = _owner(settings)
    database = connect_database(settings.database_url)
    try:
        accepted = accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=(run_input := _run_input(
                run_id="run_developer_goal_01",
                messages=[
                    {
                        "id": "message_developer_goal_01",
                        "role": "user",
                        "content": "Проверь новый репозиторий.",
                    }
                ],
                execution_mode="developer",
                access_mode="auto",
            )),
            prepared=_prepared(settings, run_input),
        )
        runtime = database.execute(
            """
            SELECT goal_id
            FROM product_project_runtime
            WHERE tenant_id = ? AND project_id = ?
            """,
            (identity.tenant_id, accepted.project_id),
        ).fetchone()
    finally:
        database.close()

    store = ProductRunStore(settings.database_url)
    claim = store.claim_next(worker_id="worker_test", lease_seconds=30)
    assert claim is not None
    assert claim.phase == "goal_required"
    assert claim.max_attempts == settings.product_run_max_attempts
    store.prepare_delivery(
        claim,
        phase="goal_initialize",
        path="/v1/runtime/product-goal-initializations",
    )
    database = connect_database(settings.database_url)
    try:
        database.execute(
            """
            UPDATE product_run_outbox
            SET attempts = 2
            WHERE tenant_id = ? AND id = ?
            """,
            (claim.tenant_id, claim.outbox_id),
        )
    finally:
        database.close()
    goal_id = str(runtime["goal_id"])
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
    store.apply_goal_initialized(
        claim,
        HomeRuntimeResponse(http_status=201, body_text=body, value=status),
        deadline_seconds=settings.product_run_command_deadline_seconds,
    )

    database = connect_database(settings.database_url)
    try:
        row = database.execute(
            """
            SELECT phase, state, attempts, max_attempts, command_json
            FROM product_run_outbox
            WHERE tenant_id = ? AND run_id = ?
            """,
            (identity.tenant_id, accepted.run_id),
        ).fetchone()
    finally:
        database.close()
    assert tuple(row)[:4] == ("run_execute", "queued", 0, 1)
    command = json.loads(str(row["command_json"]))
    _validate_product_command(command)
    assert command["payload_schema_id"] == (
        "kolibri.product.run.execute.v1_2.command"
    )


def test_ambiguous_developer_failure_is_never_retried(
    tmp_path: Path,
) -> None:
    settings = _home_settings(tmp_path / "developer-no-retry.db")
    identity = _owner(settings)
    _, developer_run_id = _accept_existing_project_developer_run(
        settings=settings,
        identity=identity,
    )
    store = ProductRunStore(settings.database_url)
    claim = store.claim_next(worker_id="worker_test", lease_seconds=30)
    assert claim is not None
    assert claim.run_id == developer_run_id

    outcome = store.record_failure(
        claim,
        ProductRunExecutionError(
            "home_transport_timeout",
            retryable=True,
            infrastructure_outage=True,
        ),
        retry_base_seconds=0.1,
        retry_max_seconds=1.0,
    )

    assert outcome == "failed"
    database = connect_database(settings.database_url)
    try:
        row = database.execute(
            """
            SELECT state, attempts, max_attempts, last_error_code
            FROM product_run_outbox
            WHERE tenant_id = ? AND run_id = ?
            """,
            (identity.tenant_id, developer_run_id),
        ).fetchone()
    finally:
        database.close()
    assert tuple(row) == (
        "blocked",
        1,
        1,
        "logical_home_unavailable",
    )


def test_product_worker_persists_opaque_runtime_profile_status(
    tmp_path: Path,
) -> None:
    settings = _home_settings(tmp_path / "developer-status.db")
    identity = _owner(settings)
    _, developer_run_id = _accept_existing_project_developer_run(
        settings=settings,
        identity=identity,
    )
    store = ProductRunStore(settings.database_url)
    claim = store.claim_next(worker_id="worker_test", lease_seconds=30)
    assert claim is not None
    store.prepare_delivery(
        claim,
        phase="run_execute",
        path="/v1/runtime/product-text-runs",
    )
    command = json.loads(claim.command_json)
    status = {
        "schema_id": "kolibri.product.run.execution_status.v1_1",
        "schema_version": "1.1",
        "run_id": developer_run_id,
        "status": "accepted",
        "runtime_profile": command["payload"]["runtime_profile"],
        "execution_id": "execution_developer_status_01",
        "verification_status": "not_applicable",
        "result_text": None,
        "result_hash": None,
        "evidence": None,
        "error": None,
    }
    validated = validate_product_execution_status(status, command)
    body = json.dumps(
        status,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    outcome = store.apply_run_status(
        claim,
        HomeRuntimeResponse(
            http_status=202,
            body_text=body,
            value=validated,
        ),
        poll_seconds=0.1,
    )

    assert outcome == "accepted"
    database = connect_database(settings.database_url)
    try:
        runtime = database.execute(
            """
            SELECT resolved_profile
            FROM product_run_runtime
            WHERE tenant_id = ? AND run_id = ?
            """,
            (identity.tenant_id, developer_run_id),
        ).fetchone()
        outbox = database.execute(
            """
            SELECT state
            FROM product_run_outbox
            WHERE tenant_id = ? AND run_id = ?
            """,
            (identity.tenant_id, developer_run_id),
        ).fetchone()
    finally:
        database.close()
    assert runtime["resolved_profile"] == status["runtime_profile"]
    assert outbox["state"] == "polling"


def test_developer_worker_rechecks_live_authority_at_both_boundaries(
    tmp_path: Path,
) -> None:
    settings = _home_settings(tmp_path / "developer-authority-recheck.db")
    identity = _owner(settings)
    _, developer_run_id = _accept_existing_project_developer_run(
        settings=settings,
        identity=identity,
    )
    store = ProductRunStore(settings.database_url)
    claim = store.claim_next(worker_id="worker_authority", lease_seconds=30)
    assert claim is not None
    assert claim.run_id == developer_run_id

    database = connect_database(settings.database_url)
    try:
        database.execute(
            """
            UPDATE platform_tenant_policies
            SET developer_access_enabled = 0
            WHERE tenant_id = ?
            """,
            (identity.tenant_id,),
        )
    finally:
        database.close()
    with pytest.raises(ProductRunExecutionError) as policy_dispatch_denied:
        store.prepare_delivery(
            claim,
            phase="run_execute",
            path="/v1/runtime/product-text-runs",
        )
    assert policy_dispatch_denied.value.code == "developer_access_disabled"

    database = connect_database(settings.database_url)
    try:
        database.execute(
            """
            UPDATE platform_tenant_policies
            SET developer_access_enabled = 1
            WHERE tenant_id = ?
            """,
            (identity.tenant_id,),
        )
        database.execute(
            """
            UPDATE platform_authority_grants
            SET active = 0
            WHERE authority_id = 'platform_owner'
            """
        )
    finally:
        database.close()
    with pytest.raises(ProductRunExecutionError) as dispatch_denied:
        store.prepare_delivery(
            claim,
            phase="run_execute",
            path="/v1/runtime/product-text-runs",
        )
    assert dispatch_denied.value.code == "owner_required"

    database = connect_database(settings.database_url)
    try:
        database.execute(
            """
            UPDATE platform_authority_grants
            SET active = 1
            WHERE authority_id = 'platform_owner'
            """
        )
    finally:
        database.close()
    store.prepare_delivery(
        claim,
        phase="run_execute",
        path="/v1/runtime/product-text-runs",
    )
    command = json.loads(claim.command_json)
    status = {
        "schema_id": "kolibri.product.run.execution_status.v1_1",
        "schema_version": "1.1",
        "run_id": developer_run_id,
        "status": "accepted",
        "runtime_profile": command["payload"]["runtime_profile"],
        "execution_id": "execution_authority_recheck_01",
        "verification_status": "not_applicable",
        "result_text": None,
        "result_hash": None,
        "evidence": None,
        "error": None,
    }
    response = HomeRuntimeResponse(
        http_status=202,
        body_text=json.dumps(
            status,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        value=validate_product_execution_status(status, command),
    )
    database = connect_database(settings.database_url)
    try:
        database.execute(
            """
            UPDATE platform_user_controls
            SET developer_access = 'deny'
            WHERE tenant_id = ? AND user_id = ?
            """,
            (identity.tenant_id, identity.user_id),
        )
    finally:
        database.close()
    with pytest.raises(ProductRunExecutionError) as policy_commit_denied:
        store.apply_run_status(claim, response, poll_seconds=0.1)
    assert policy_commit_denied.value.code == "developer_access_disabled"

    database = connect_database(settings.database_url)
    try:
        database.execute(
            """
            UPDATE platform_user_controls
            SET developer_access = 'allow'
            WHERE tenant_id = ? AND user_id = ?
            """,
            (identity.tenant_id, identity.user_id),
        )
        database.execute(
            """
            UPDATE platform_authority_grants
            SET authority_epoch = authority_epoch + 1
            WHERE authority_id = 'platform_owner'
            """
        )
    finally:
        database.close()
    with pytest.raises(ProductRunExecutionError) as commit_denied:
        store.apply_run_status(claim, response, poll_seconds=0.1)
    assert commit_denied.value.code == "owner_required"

    database = connect_database(settings.database_url)
    try:
        assert database.execute(
            """
            SELECT COUNT(*)
            FROM product_run_runtime
            WHERE tenant_id = ? AND run_id = ?
            """,
            (identity.tenant_id, developer_run_id),
        ).fetchone()[0] == 0
        assert database.execute(
            """
            SELECT response_status
            FROM product_runtime_exchanges
            WHERE tenant_id = ? AND run_id = ? AND phase = 'run_execute'
            """,
            (identity.tenant_id, developer_run_id),
        ).fetchone()[0] is None
    finally:
        database.close()
