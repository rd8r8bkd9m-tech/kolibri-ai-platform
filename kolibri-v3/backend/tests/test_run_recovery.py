from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import time
from typing import Any, Callable

from fastapi.testclient import TestClient
import pytest

from app.agent_runtime import (
    AgentRuntimeCapabilities,
    AgentRuntimeDescriptor,
    AgentRuntimeRegistry,
    AgentRuntimeRequest,
    AgentRuntimeResult,
    DelegatingAgentRuntime,
)
from app.chat.cancellation import (
    ActiveRunCancellationRegistry,
    cancel_run,
)
from app.chat.execution_adapter import (
    DirectRunDispatcher,
    PreparedChatExecution,
)
from app.chat.models import AgUiRunInput
from app.chat.service import AcceptedRun, accept_run
from app.config import Settings
from app.database import connect_database, initialize_database, migration_paths
from app.direct_model_runtime import _finish_success
from app.direct_run_outbox import (
    DIRECT_RUN_INTERRUPTED_CODE,
    DirectRunLeaseError,
    DirectRunStore,
)
from app.home_runtime import HomeRuntimeResponse
from app.main import create_app
import app.main as main_module
from app.product_run_worker import ProductRunStore, StaleLeaseError
from app.schemas import AgentProfile, UserRole, UserSession


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"
RUNTIME_PROFILE = "recovery-test-runtime"


def _run_input(
    *,
    thread_id: str,
    run_id: str,
    message_id: str,
    prompt: str,
) -> AgUiRunInput:
    return AgUiRunInput.model_validate(
        {
            "threadId": thread_id,
            "runId": run_id,
            "state": None,
            "messages": [
                {
                    "id": message_id,
                    "role": "user",
                    "content": prompt,
                }
            ],
            "tools": [],
            "context": [],
            "forwardedProps": {
                "agentProfile": "auto",
                "executionMode": "standard",
                "accessMode": "standard",
            },
        }
    )


def _register(settings: Settings, *, email: str) -> UserSession:
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/v1/auth/register",
            headers=ORIGIN,
            json={
                "email": email,
                "name": "Recovery User",
                "password": PASSWORD,
            },
        )
        assert response.status_code == 201
        user = response.json()["user"]
    return UserSession(
        user_id=user["id"],
        tenant_id=user["tenantId"],
        role=UserRole.USER,
        preferred_agent_profile=AgentProfile.AUTO,
        email=user["email"],
        name=user["name"],
        platform_capabilities=("chat.use",),
    )


def _accept(
    settings: Settings,
    identity: UserSession,
    *,
    execution_plane: str,
    run_id: str,
    thread_id: str = "thread_recovery_01",
    message_id: str = "message_recovery_01",
) -> AcceptedRun:
    run_input = _run_input(
        thread_id=thread_id,
        run_id=run_id,
        message_id=message_id,
        prompt="Проанализируй уникальный контекст перезапуска сервиса.",
    )
    database = connect_database(settings.database_url)
    try:
        return accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=run_input,
            prepared=PreparedChatExecution(
                execution_plane=execution_plane,
                runtime_profile="auto",
                model_id=None,
                reasoning_effort=None,
                service_tier=None,
            ),
        )
    finally:
        database.close()


def _connect_runtime(settings: Settings, tenant_id: str) -> None:
    now = "2026-07-30T12:00:00+00:00"
    database = connect_database(settings.database_url)
    try:
        database.execute(
            """
            INSERT INTO provider_connections (
                tenant_id, provider_id, status, auth_flow_supported,
                authority_observed, last_verified_at, last_evidence_hash,
                last_intent_id, last_error_code, created_at, updated_at
            ) VALUES (
                ?, ?, 'connected', 0, 1, ?, NULL, NULL, NULL, ?, ?
            )
            """,
            (tenant_id, RUNTIME_PROFILE, now, now, now),
        )
    finally:
        database.close()


class _WarmRuntime:
    def __init__(self) -> None:
        self.start_calls = 0
        self.close_calls = 0
        self.requests: list[AgentRuntimeRequest] = []

    @property
    def descriptor(self) -> AgentRuntimeDescriptor:
        return AgentRuntimeDescriptor(
            profile_id=RUNTIME_PROFILE,
            runtime_id="recovery-test-engine",
            display_name="Recovery Test Runtime",
            capabilities=AgentRuntimeCapabilities(
                modes=frozenset({"chat"}),
                streaming=False,
                structured_output=False,
                activity_events=False,
                persistent_sessions=True,
            ),
        )

    @property
    def model_catalog_backend(self) -> None:
        return None

    def start(self) -> None:
        self.start_calls += 1

    def close(self) -> None:
        self.close_calls += 1

    def execute(self, request: AgentRuntimeRequest) -> AgentRuntimeResult:
        self.requests.append(request)
        return AgentRuntimeResult(
            text=f"Восстановленный ответ {len(self.requests)}.",
            session_id="session_recovery_test",
        )


def _registry(runtime: _WarmRuntime) -> AgentRuntimeRegistry:
    registry = AgentRuntimeRegistry()
    registry.register(
        DelegatingAgentRuntime(
            descriptor=runtime.descriptor,
            execute=runtime.execute,
            start=runtime.start,
            close=runtime.close,
        )
    )
    return registry


def _wait_until(
    predicate: Callable[[], bool],
    *,
    timeout: float = 5.0,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("timed out waiting for durable run state")


def _run_status(settings: Settings, accepted: AcceptedRun) -> str:
    database = connect_database(settings.database_url)
    try:
        row = database.execute(
            """
            SELECT status
            FROM chat_runs
            WHERE tenant_id = ? AND id = ?
            """,
            (accepted.tenant_id, accepted.run_id),
        ).fetchone()
        assert row is not None
        return str(row["status"])
    finally:
        database.close()


def test_queued_direct_run_is_executed_by_a_restarted_dispatcher(
    tmp_path: Path,
) -> None:
    base = Settings.for_testing(database_url=tmp_path / "direct-restart.db")
    identity = _register(base, email="direct-restart@example.com")
    settings = replace(base, direct_model_runtime_enabled=True)
    _connect_runtime(settings, identity.tenant_id)
    accepted = _accept(
        settings,
        identity,
        execution_plane="direct",
        run_id="run_direct_restart_01",
    )

    runtime = _WarmRuntime()
    registry = _registry(runtime)
    registry.start_all()
    executor = ThreadPoolExecutor(max_workers=1)
    cancellations = ActiveRunCancellationRegistry()
    dispatcher = DirectRunDispatcher(
        settings=settings,
        executor=executor,
        runtime_registry=registry,
        cancellations=cancellations,
        max_inflight=1,
        worker_id="direct-worker-after-restart",
    )
    try:
        dispatcher.start()
        dispatcher.notify()
        _wait_until(lambda: _run_status(settings, accepted) == "succeeded")
    finally:
        dispatcher.close()
        cancellations.close()
        executor.shutdown(wait=True, cancel_futures=True)
        registry.close_all()

    assert runtime.start_calls == 1
    assert runtime.close_calls == 1
    assert len(runtime.requests) == 1
    database = connect_database(settings.database_url)
    try:
        outbox = database.execute(
            """
            SELECT state, lease_owner, lease_token, lease_until
            FROM direct_run_outbox
            WHERE tenant_id = ? AND run_id = ?
            """,
            (accepted.tenant_id, accepted.run_id),
        ).fetchone()
        messages = database.execute(
            """
            SELECT COUNT(*)
            FROM chat_messages
            WHERE tenant_id = ? AND run_id = ? AND role = 'assistant'
            """,
            (accepted.tenant_id, accepted.run_id),
        ).fetchone()[0]
    finally:
        database.close()
    assert dict(outbox) == {
        "state": "completed",
        "lease_owner": None,
        "lease_token": None,
        "lease_until": None,
    }
    assert messages == 1


def test_expired_direct_lease_fails_closed_without_duplicate_commit(
    tmp_path: Path,
) -> None:
    base = Settings.for_testing(database_url=tmp_path / "direct-expired.db")
    identity = _register(base, email="direct-expired@example.com")
    settings = replace(base, direct_model_runtime_enabled=True)
    accepted = _accept(
        settings,
        identity,
        execution_plane="direct",
        run_id="run_direct_expired_01",
    )
    store = DirectRunStore(settings.database_url)
    stale_claim = store.claim_next(
        worker_id="direct-worker-before-restart",
        lease_seconds=30,
    )
    assert stale_claim is not None

    database = connect_database(settings.database_url)
    try:
        database.execute(
            """
            UPDATE direct_run_outbox
            SET lease_until = '1970-01-01T00:00:00+00:00'
            WHERE tenant_id = ? AND run_id = ?
            """,
            (stale_claim.tenant_id, stale_claim.run_id),
        )
    finally:
        database.close()

    assert store.recover() == 1
    with pytest.raises(DirectRunLeaseError):
        store.fence(stale_claim)
    _finish_success(settings, stale_claim, "Поздний дублирующий ответ.")

    database = connect_database(settings.database_url)
    try:
        run = database.execute(
            """
            SELECT status, error_code
            FROM chat_runs
            WHERE tenant_id = ? AND id = ?
            """,
            (accepted.tenant_id, accepted.run_id),
        ).fetchone()
        outbox = database.execute(
            """
            SELECT state, fencing_token, last_error_code
            FROM direct_run_outbox
            WHERE tenant_id = ? AND run_id = ?
            """,
            (accepted.tenant_id, accepted.run_id),
        ).fetchone()
        assistant_count = database.execute(
            """
            SELECT COUNT(*)
            FROM chat_messages
            WHERE tenant_id = ? AND run_id = ? AND role = 'assistant'
            """,
            (accepted.tenant_id, accepted.run_id),
        ).fetchone()[0]
    finally:
        database.close()
    assert tuple(run) == ("failed", DIRECT_RUN_INTERRUPTED_CODE)
    assert tuple(outbox) == (
        "blocked",
        stale_claim.fencing_token + 1,
        DIRECT_RUN_INTERRUPTED_CODE,
    )
    assert assistant_count == 0


def test_migration_38_backfills_running_direct_as_expired_lease(
    tmp_path: Path,
) -> None:
    base = Settings.for_testing(database_url=tmp_path / "migration-39.db")
    identity = _register(base, email="migration-39@example.com")
    settings = replace(base, direct_model_runtime_enabled=True)
    accepted = _accept(
        settings,
        identity,
        execution_plane="direct",
        run_id="run_migration_39_01",
    )

    database = connect_database(settings.database_url)
    try:
        database.execute("DROP TABLE direct_run_outbox")
        database.execute("DROP TABLE runtime_worker_heartbeats")
        database.execute("PRAGMA user_version = 38")
    finally:
        database.close()
    initialize_database(settings.database_url)

    database = connect_database(settings.database_url)
    try:
        version = database.execute("PRAGMA user_version").fetchone()[0]
        migrated = database.execute(
            """
            SELECT state, lease_owner, lease_token, lease_until,
                   public_thread_id, public_run_id
            FROM direct_run_outbox
            WHERE tenant_id = ? AND run_id = ?
            """,
            (accepted.tenant_id, accepted.run_id),
        ).fetchone()
    finally:
        database.close()
    assert version == int(migration_paths()[-1].name.split("_", 1)[0])
    assert dict(migrated) == {
        "state": "leased",
        "lease_owner": "migration-recovery",
        "lease_token": "lease_migration_recovery",
        "lease_until": "1970-01-01T00:00:00+00:00",
        "public_thread_id": accepted.public_thread_id,
        "public_run_id": accepted.public_run_id,
    }
    assert DirectRunStore(settings.database_url).recover() == 1
    assert _run_status(settings, accepted) == "failed"


def test_direct_cancel_fences_claim_and_late_commit(
    tmp_path: Path,
) -> None:
    base = Settings.for_testing(database_url=tmp_path / "direct-cancel.db")
    identity = _register(base, email="direct-cancel@example.com")
    settings = replace(base, direct_model_runtime_enabled=True)
    accepted = _accept(
        settings,
        identity,
        execution_plane="direct",
        run_id="run_direct_cancel_01",
    )
    store = DirectRunStore(settings.database_url)
    stale_claim = store.claim_next(
        worker_id="direct-worker-cancelled",
        lease_seconds=30,
    )
    assert stale_claim is not None

    database = connect_database(settings.database_url)
    try:
        result = cancel_run(
            database,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            run_id=accepted.run_id,
        )
        assert result is not None and result.cancelled
    finally:
        database.close()
    with pytest.raises(DirectRunLeaseError):
        store.fence(stale_claim)
    _finish_success(settings, stale_claim, "Ответ после отмены.")

    database = connect_database(settings.database_url)
    try:
        outbox = database.execute(
            """
            SELECT state, fencing_token, last_error_code
            FROM direct_run_outbox
            WHERE tenant_id = ? AND run_id = ?
            """,
            (accepted.tenant_id, accepted.run_id),
        ).fetchone()
        assistant_count = database.execute(
            """
            SELECT COUNT(*)
            FROM chat_messages
            WHERE tenant_id = ? AND run_id = ? AND role = 'assistant'
            """,
            (accepted.tenant_id, accepted.run_id),
        ).fetchone()[0]
    finally:
        database.close()
    assert tuple(outbox) == (
        "blocked",
        stale_claim.fencing_token + 1,
        "run_cancelled",
    )
    assert assistant_count == 0


def _goal_response(claim: Any) -> HomeRuntimeResponse:
    command = json.loads(claim.command_json)
    goal_id = str(command["payload"]["goal_id"])
    value = {
        "schema_id": "kolibri.product.goal.initialization_status",
        "schema_version": "1.0",
        "run_id": claim.run_id,
        "goal_id": goal_id,
        "case_id": f"case_{goal_id}",
        "status": "initialized",
        "goal_version": 1,
        "case_version": 1,
        "error": None,
    }
    return HomeRuntimeResponse(
        http_status=201,
        body_text=json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        value=value,
    )


def _success_response(claim: Any) -> HomeRuntimeResponse:
    command = json.loads(claim.command_json)
    value = {
        "schema_id": "kolibri.product.run.execution_status.v1_1",
        "schema_version": "1.1",
        "run_id": claim.run_id,
        "status": "succeeded",
        "runtime_profile": command["payload"]["preferred_agent_profile"],
        "execution_id": "execution_home_restart_01",
        "verification_status": "not_applicable",
        "result_text": "Home восстановил выполнение.",
        "result_hash": "sha256:" + ("a" * 64),
        "evidence": None,
        "error": None,
    }
    return HomeRuntimeResponse(
        http_status=200,
        body_text=json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        value=value,
    )


def test_home_outbox_reclaims_after_restart_and_fences_old_commit(
    tmp_path: Path,
) -> None:
    settings = Settings.for_testing(database_url=tmp_path / "home-restart.db")
    identity = _register(settings, email="home-restart@example.com")
    accepted = _accept(
        settings,
        identity,
        execution_plane="home",
        run_id="run_home_restart_01",
    )
    store = ProductRunStore(settings.database_url)

    goal_claim = store.claim_next(
        worker_id="home-goal-worker",
        lease_seconds=30,
    )
    assert goal_claim is not None and goal_claim.phase == "goal_required"
    store.prepare_delivery(
        goal_claim,
        phase="goal_initialize",
        path="/v1/runtime/product-goal-initializations",
    )
    store.apply_goal_initialized(
        goal_claim,
        _goal_response(goal_claim),
        deadline_seconds=settings.product_run_command_deadline_seconds,
    )

    stale_claim = store.claim_next(
        worker_id="home-worker-before-restart",
        lease_seconds=30,
    )
    assert stale_claim is not None and stale_claim.phase == "run_execute"
    store.prepare_delivery(
        stale_claim,
        phase="run_execute",
        path="/v1/runtime/product-text-runs",
    )
    database = connect_database(settings.database_url)
    try:
        database.execute(
            """
            UPDATE product_run_outbox
            SET lease_until = '1970-01-01T00:00:00+00:00'
            WHERE tenant_id = ? AND id = ?
            """,
            (stale_claim.tenant_id, stale_claim.outbox_id),
        )
    finally:
        database.close()

    recovered_claim = store.claim_next(
        worker_id="home-worker-after-restart",
        lease_seconds=30,
    )
    assert recovered_claim is not None
    assert recovered_claim.fencing_token > stale_claim.fencing_token
    store.prepare_delivery(
        recovered_claim,
        phase="run_execute",
        path="/v1/runtime/product-text-runs",
    )
    response = _success_response(recovered_claim)
    assert store.apply_run_status(
        recovered_claim,
        response,
        poll_seconds=0.1,
    ) == "succeeded"
    with pytest.raises(StaleLeaseError):
        store.apply_run_status(
            stale_claim,
            response,
            poll_seconds=0.1,
        )

    database = connect_database(settings.database_url)
    try:
        run = database.execute(
            """
            SELECT status
            FROM chat_runs
            WHERE tenant_id = ? AND id = ?
            """,
            (accepted.tenant_id, accepted.run_id),
        ).fetchone()
        outbox = database.execute(
            """
            SELECT state
            FROM product_run_outbox
            WHERE tenant_id = ? AND run_id = ?
            """,
            (accepted.tenant_id, accepted.run_id),
        ).fetchone()
        assistant_count = database.execute(
            """
            SELECT COUNT(*)
            FROM chat_messages
            WHERE tenant_id = ? AND run_id = ? AND role = 'assistant'
            """,
            (accepted.tenant_id, accepted.run_id),
        ).fetchone()[0]
    finally:
        database.close()
    assert run["status"] == "succeeded"
    assert outbox["state"] == "completed"
    assert assistant_count == 1


def test_two_messages_share_one_warm_runtime_lifespan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _WarmRuntime()
    registry = _registry(runtime)
    builds = 0

    def build_registry(*_args: Any, **_kwargs: Any) -> AgentRuntimeRegistry:
        nonlocal builds
        builds += 1
        return registry

    monkeypatch.setattr(
        main_module,
        "build_agent_runtime_registry",
        build_registry,
    )
    settings = replace(
        Settings.for_testing(database_url=tmp_path / "warm-runtime.db"),
        direct_model_runtime_enabled=True,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        registered = client.post(
            "/v1/auth/register",
            headers=ORIGIN,
            json={
                "email": "warm-runtime@example.com",
                "name": "Warm Runtime",
                "password": PASSWORD,
            },
        )
        assert registered.status_code == 201
        user = registered.json()["user"]
        _connect_runtime(settings, user["tenantId"])
        csrf = client.cookies.get("kolibri_v3_csrf")
        assert csrf

        for index in (1, 2):
            response = client.post(
                "/v1/chat/ag-ui",
                headers={
                    **ORIGIN,
                    "X-CSRF-Token": csrf,
                },
                json=_run_input(
                    thread_id="thread_warm_runtime_01",
                    run_id=f"run_warm_runtime_0{index}",
                    message_id=f"message_warm_runtime_0{index}",
                    prompt=(
                        "Сопоставь два независимых аспекта архитектуры "
                        f"для проверки тёплого runtime, итерация {index}."
                    ),
                ).model_dump(mode="json", by_alias=True),
            )
            assert response.status_code == 200
            assert "RUN_FINISHED" in response.text
            canonical_run_id = response.headers["X-Kolibri-Run-Id"]
            _wait_until(
                lambda: not app.state.run_cancellations.is_registered(
                    user["tenantId"],
                    canonical_run_id,
                )
            )

        assert builds == 1
        assert runtime.start_calls == 1
        assert len(runtime.requests) == 2

    assert runtime.close_calls == 1
