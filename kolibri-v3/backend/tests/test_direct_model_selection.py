from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import app.direct_model_runtime as direct_model_runtime
import pytest
from app.chat.execution_adapter import PreparedChatExecution
from app.chat.models import AgUiRunInput
from app.chat.service import accept_run
from app.codex_app_server import CodexModel
from app.config import Settings
from app.database import connect_database, transaction
from app.estimate_artifact import (
    GeneratedEstimateProposal,
    canonical_estimate_json,
    estimate_content_hash,
    estimate_document_from_proposal,
)
from app.main import create_app
from app.mimo_developer_runtime import MimoDeveloperResult
from app.product_entitlements import bind_product_entitlements
from app.schemas import AgentProfile, UserRole, UserSession
from fastapi.testclient import TestClient

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"
NOW = "2026-07-29T00:00:00Z"
PROJECT_ID = "project_direct_model_selection_01"
THREAD_ID = "thread_direct_model_selection_01"
MESSAGE_ID = "message_direct_model_selection_01"
RUN_ID = "run_direct_model_selection_01"


def _prepared(
    *,
    profile: str,
    model: str | None = None,
    effort: str | None = None,
    service_tier: str | None = None,
) -> PreparedChatExecution:
    return PreparedChatExecution(
        execution_plane="direct",
        runtime_profile=profile,
        model_id=model,
        reasoning_effort=effort,
        service_tier=service_tier,
    )


def _enable_developer_policy(
    database: sqlite3.Connection,
    identity: UserSession,
) -> None:
    database.execute(
        """
        INSERT INTO platform_authority_grants (
            authority_id, user_id, tenant_id, active, authority_epoch,
            capabilities_json, created_at, updated_at
        ) VALUES (
            'platform_owner', ?, ?, 1, 1,
            '["platform.admin","chat.developer.request","chat.use"]',
            unixepoch(), unixepoch()
        )
        ON CONFLICT(authority_id) DO UPDATE SET
            user_id = excluded.user_id,
            tenant_id = excluded.tenant_id,
            active = 1,
            capabilities_json = excluded.capabilities_json,
            updated_at = unixepoch()
        """,
        (identity.user_id, identity.tenant_id),
    )
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
        UPDATE platform_user_controls
        SET developer_access = 'allow'
        WHERE tenant_id = ? AND user_id = ?
        """,
        (identity.tenant_id, identity.user_id),
    )


def _catalog_model() -> CodexModel:
    return CodexModel(
        id="gpt-test-selected",
        display_name="GPT Test Selected",
        description="Test-only catalog model.",
        supported_reasoning_efforts=(
            ("low", "Fast"),
            ("high", "Thorough"),
        ),
        default_reasoning_effort="low",
        is_default=True,
        supports_personality=False,
        service_tiers=(("priority", "Fast", "1.5x speed, increased usage"),),
        upgrade=None,
    )


class RecordingCodexRuntime:
    def __init__(self) -> None:
        self.catalog_calls = 0
        self.complete_calls: list[dict[str, Any]] = []

    def list_models(self, *, timeout: float) -> tuple[CodexModel, ...]:
        assert timeout > 0
        self.catalog_calls += 1
        return (_catalog_model(),)

    def complete(self, **kwargs: Any) -> str:
        self.complete_calls.append(kwargs)
        return "Ответ выбранной модели."


class RecordingMimoDeveloperRuntime:
    def __init__(self) -> None:
        self.complete_calls: list[dict[str, Any]] = []

    def complete(self, **kwargs: Any) -> MimoDeveloperResult:
        self.complete_calls.append(kwargs)
        kwargs["on_delta"]("MiMo исправил код.")
        return MimoDeveloperResult(
            text="MiMo исправил код.",
            session_id="ses_direct_model_selection_01",
        )


def _settings(database_path: Path) -> Settings:
    return replace(
        Settings.for_testing(database_url=database_path),
        direct_model_runtime_enabled=True,
    )


def _runtime_registry(
    settings: Settings,
    *,
    codex_runtime: object | None = None,
    mimo_runtime: object | None = None,
    mimo_developer_runtime: object | None = None,
):
    return direct_model_runtime._legacy_runtime_registry(
        settings,
        codex_transport=codex_runtime,
        mimo_transport=mimo_runtime,
        mimo_developer_transport=mimo_developer_runtime,
    )


def _registered_user(database_path: Path) -> dict[str, str]:
    with TestClient(create_app(_settings(database_path))) as client:
        response = client.post(
            "/v1/auth/register",
            headers=ORIGIN,
            json={
                "email": "direct-model@example.com",
                "name": "Direct Model",
                "password": PASSWORD,
            },
        )
        assert response.status_code == 201
        return response.json()["user"]


def _seed_run(
    database_path: Path,
    *,
    tenant_id: str,
    user_id: str,
    model: str | None,
    effort: str | None,
    service_tier: str | None = None,
    selected_profile: str = "codex-cli",
    include_execution_context: bool = True,
    execution_mode: str = "standard",
    access_mode: str = "standard",
    prompt: str = "Объясни преимущества модульной архитектуры.",
) -> SimpleNamespace:
    database = connect_database(database_path)
    try:
        with transaction(database, immediate=True):
            database.execute(
                """
                INSERT INTO projects (
                    tenant_id, id, created_by_user_id, title, status,
                    primary_thread_id, created_at, updated_at
                ) VALUES (?, ?, ?, 'Direct model test', 'active', ?, ?, ?)
                """,
                (tenant_id, PROJECT_ID, user_id, THREAD_ID, NOW, NOW),
            )
            database.execute(
                """
                INSERT INTO chat_threads (
                    tenant_id, id, project_id, kind, title, status,
                    message_count, run_count, created_at, updated_at
                ) VALUES (?, ?, ?, 'primary', 'Direct model test', 'regular',
                          1, 1, ?, ?)
                """,
                (tenant_id, THREAD_ID, PROJECT_ID, NOW, NOW),
            )
            database.execute(
                """
                INSERT INTO chat_messages (
                    tenant_id, id, project_id, thread_id, sequence,
                    client_message_id, role, content_text,
                    created_by_user_id, created_at
                ) VALUES (?, ?, ?, ?, 1, 'client_direct_model_message', 'user',
                          ?, ?, ?)
                """,
                (
                    tenant_id,
                    MESSAGE_ID,
                    PROJECT_ID,
                    THREAD_ID,
                    prompt,
                    user_id,
                    NOW,
                ),
            )
            database.execute(
                """
                INSERT INTO chat_runs (
                    tenant_id, id, project_id, thread_id, client_run_id,
                    request_hash, input_message_id, requested_by_user_id,
                    selected_profile, status, last_event_sequence,
                    heartbeat_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'client_direct_model_run', ?, ?, ?,
                          ?, 'running', 1, ?, ?, ?)
                """,
                (
                    tenant_id,
                    RUN_ID,
                    PROJECT_ID,
                    THREAD_ID,
                    "sha256:" + ("a" * 64),
                    MESSAGE_ID,
                    user_id,
                    selected_profile,
                    NOW,
                    NOW,
                    NOW,
                ),
            )
            if include_execution_context:
                if execution_mode == "developer":
                    database.execute(
                        """
                        INSERT INTO platform_authority_grants (
                            authority_id, user_id, tenant_id, active,
                            authority_epoch, capabilities_json,
                            created_at, updated_at
                        ) VALUES (
                            'platform_owner', ?, ?, 1, 1,
                            '["platform.admin","chat.developer.request","chat.use"]',
                            unixepoch(), unixepoch()
                        )
                        """,
                        (user_id, tenant_id),
                    )
                    database.execute(
                        """
                        UPDATE platform_tenant_policies
                        SET developer_access_enabled = 1
                        WHERE tenant_id = ?
                        """,
                        (tenant_id,),
                    )
                    database.execute(
                        """
                        UPDATE platform_user_controls
                        SET developer_access = 'allow'
                        WHERE tenant_id = ? AND user_id = ?
                        """,
                        (tenant_id, user_id),
                    )
                database.execute(
                    """
                    INSERT INTO chat_run_execution_contexts (
                        tenant_id, run_id, execution_mode,
                        platform_authority_epoch, access_mode,
                        authority_role, authority_user_id, workspace_ref,
                        sandbox_profile, approval_policy, approvals_reviewer,
                        model_id, reasoning_effort, service_tier, created_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        tenant_id,
                        RUN_ID,
                        execution_mode,
                        1 if execution_mode == "developer" else None,
                        access_mode,
                        "owner" if execution_mode == "developer" else "user",
                        user_id,
                        "repository" if execution_mode == "developer" else None,
                        (
                            "workspace-write"
                            if access_mode == "auto"
                            else "danger-full-access"
                            if access_mode == "full"
                            else "read-only"
                        ),
                        "on-request" if access_mode == "auto" else "never",
                        "auto_review" if access_mode == "auto" else None,
                        model,
                        effort,
                        service_tier,
                        NOW,
                    ),
                )
    finally:
        database.close()
    return SimpleNamespace(
        tenant_id=tenant_id,
        project_id=PROJECT_ID,
        thread_id=THREAD_ID,
        public_thread_id=THREAD_ID,
        run_id=RUN_ID,
        public_run_id=RUN_ID,
        execution_mode=execution_mode,
    )


def _seed_existing_estimate_slot(
    database_path: Path,
    *,
    tenant_id: str,
    user_id: str,
    project_id: str = PROJECT_ID,
) -> None:
    proposal = GeneratedEstimateProposal.model_validate(
        {
            "title": "Предварительная смета на ремонт ванной комнаты 6 м²",
            "region": "Москва",
            "assumptions": ["Площадь и цены требуют проверки."],
            "rows": [
                {
                    "section": "Демонтаж",
                    "kind": "work",
                    "description": "Демонтаж плитки",
                    "unit": "м²",
                    "quantity": "30",
                    "unitPrice": "500.00",
                    "quantityBasis": "допущение",
                    "priceBasis": "допущение",
                }
            ],
        }
    )
    document = estimate_document_from_proposal(
        proposal,
        now=NOW,
        provider_profile="codex-cli",
        run_id="previous_estimate_run",
    )
    document_json = canonical_estimate_json(document)
    database = connect_database(database_path)
    try:
        with transaction(database, immediate=True):
            database.execute(
                """
                INSERT INTO document_slots (
                    tenant_id, id, project_id, slot_type, version, status,
                    content_json, created_at, updated_at
                ) VALUES (?, 'document_existing_estimate_01', ?, 'estimate',
                          1, 'draft', ?, ?, ?)
                """,
                (tenant_id, project_id, document_json, NOW, NOW),
            )
            database.execute(
                """
                INSERT INTO estimate_versions (
                    tenant_id, id, project_id, document_id, version, status,
                    content_json, content_hash, origin_type, origin_run_id,
                    created_by_user_id, created_at
                ) VALUES (?, 'estimate_version_existing_01', ?,
                          'document_existing_estimate_01', 1, 'draft', ?, ?,
                          'ai_proposal', NULL, ?, ?)
                """,
                (
                    tenant_id,
                    project_id,
                    document_json,
                    estimate_content_hash(document),
                    user_id,
                    NOW,
                ),
            )
    finally:
        database.close()


def test_standard_codex_run_uses_frozen_model_and_effort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "direct-model.db"
    settings = _settings(database_path)
    user = _registered_user(database_path)
    accepted = _seed_run(
        database_path,
        tenant_id=user["tenantId"],
        user_id=user["id"],
        model="gpt-test-selected",
        effort="high",
        service_tier="priority",
    )
    monkeypatch.setattr(
        direct_model_runtime,
        "_connected_profile",
        lambda *_args, **_kwargs: ("codex-cli", user["tenantId"]),
    )
    runtime = RecordingCodexRuntime()

    direct_model_runtime.execute_direct_run(
        settings,
        accepted,
        _runtime_registry(settings, codex_runtime=runtime),
    )

    assert runtime.catalog_calls == 1
    assert len(runtime.complete_calls) == 1
    assert runtime.complete_calls[0]["model"] == "gpt-test-selected"
    assert runtime.complete_calls[0]["effort"] == "high"
    assert runtime.complete_calls[0]["service_tier"] == "priority"
    database = sqlite3.connect(database_path)
    try:
        status, error_code = database.execute(
            "SELECT status, error_code FROM chat_runs WHERE id = ?",
            (RUN_ID,),
        ).fetchone()
    finally:
        database.close()
    assert (status, error_code) == ("succeeded", None)


def test_acceptance_snapshot_is_the_selection_used_by_direct_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "accepted-direct-model.db"
    settings = _settings(database_path)
    user = _registered_user(database_path)
    identity = UserSession(
        user_id=user["id"],
        tenant_id=user["tenantId"],
        role=UserRole.USER,
        preferred_agent_profile=AgentProfile.CODEX_CLI,
        preferred_model_profile=AgentProfile.CODEX_CLI,
        preferred_model="gpt-test-selected",
        preferred_reasoning_effort="high",
        preferred_service_tier="priority",
        email="direct-model@example.com",
        name="Direct Model",
    )
    run_input = AgUiRunInput.model_validate(
        {
            "threadId": "thread_accepted_model_01",
            "runId": "run_accepted_model_01",
            "state": None,
            "messages": [
                {
                    "id": "message_accepted_model_01",
                    "role": "user",
                    "content": "Объясни преимущества модульной архитектуры.",
                }
            ],
            "tools": [],
            "context": [],
            "forwardedProps": {
                "agentProfile": "codex-cli",
                "executionMode": "standard",
            },
        }
    )
    database = connect_database(database_path)
    try:
        accepted = accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=run_input,
            prepared=_prepared(
                profile="codex-cli",
                model="gpt-test-selected",
                effort="high",
                service_tier="priority",
            ),
        )
        frozen = database.execute(
            """
            SELECT model_id, reasoning_effort, service_tier
            FROM chat_run_execution_contexts
            WHERE tenant_id = ? AND run_id = ?
            """,
            (identity.tenant_id, accepted.run_id),
        ).fetchone()
        assert tuple(frozen) == (
            "gpt-test-selected",
            "high",
            "priority",
        )
    finally:
        database.close()
    monkeypatch.setattr(
        direct_model_runtime,
        "_connected_profile",
        lambda *_args, **_kwargs: ("codex-cli", user["tenantId"]),
    )
    runtime = RecordingCodexRuntime()

    direct_model_runtime.execute_direct_run(
        settings,
        accepted,
        _runtime_registry(settings, codex_runtime=runtime),
    )

    assert runtime.complete_calls[0]["model"] == "gpt-test-selected"
    assert runtime.complete_calls[0]["effort"] == "high"
    assert runtime.complete_calls[0]["service_tier"] == "priority"


@pytest.mark.parametrize(
    ("prompt", "execution_mode", "access_mode", "expected_selection"),
    (
        (
            "Составь смету на ремонт помещения площадью 120 м².",
            "standard",
            "standard",
            (None, None, None),
        ),
        (
            "Исправь backend-тесты в репозитории.",
            "developer",
            "full",
            ("gpt-test-selected", "high", "priority"),
        ),
    ),
)
def test_run_acceptance_freezes_only_applicable_model_preferences(
    tmp_path: Path,
    prompt: str,
    execution_mode: str,
    access_mode: str,
    expected_selection: tuple[str | None, str | None, str | None],
) -> None:
    database_path = tmp_path / f"server-owned-{execution_mode}.db"
    settings = replace(
        _settings(database_path),
        direct_model_runtime_enabled=True,
        developer_agent_enabled=True,
        developer_workspace_root=tmp_path,
    )
    user = _registered_user(database_path)
    identity = UserSession(
        user_id=user["id"],
        tenant_id=user["tenantId"],
        role=(UserRole.OWNER if execution_mode == "developer" else UserRole.USER),
        preferred_agent_profile=AgentProfile.CODEX_CLI,
        preferred_model_profile=AgentProfile.CODEX_CLI,
        preferred_model="gpt-test-selected",
        preferred_reasoning_effort="high",
        preferred_service_tier="priority",
        email="direct-model@example.com",
        name="Direct Model",
        is_platform_owner=(execution_mode == "developer"),
        platform_capabilities=(
            (
                "platform.admin",
                "chat.developer.request",
                "chat.use",
            )
            if execution_mode == "developer"
            else ("chat.use",)
        ),
    )
    run_input = AgUiRunInput.model_validate(
        {
            "threadId": f"thread_server_owned_{execution_mode}_01",
            "runId": f"run_server_owned_{execution_mode}_01",
            "state": None,
            "messages": [
                {
                    "id": f"message_server_owned_{execution_mode}_01",
                    "role": "user",
                    "content": prompt,
                }
            ],
            "tools": [],
            "context": [],
            "forwardedProps": {
                "agentProfile": ("codex-cli"),
                "executionMode": execution_mode,
                "accessMode": access_mode,
            },
        }
    )
    database = connect_database(database_path)
    try:
        if execution_mode == "developer":
            _enable_developer_policy(database, identity)
        if "смет" in prompt.casefold():
            database.execute(
                """
                INSERT INTO product_entitlement_grants (
                    tenant_id, user_id, entitlement_code, status,
                    grant_epoch, source, created_at, updated_at
                ) VALUES (
                    ?, ?, 'construction.estimates.use', 'active',
                    1, 'subscription_policy', unixepoch(), unixepoch()
                )
                """,
                (identity.tenant_id, identity.user_id),
            )
            identity = bind_product_entitlements(database, identity)
        accepted = accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=run_input,
            prepared=_prepared(
                profile="codex-cli",
                model=expected_selection[0],
                effort=expected_selection[1],
                service_tier=expected_selection[2],
            ),
        )
        frozen = database.execute(
            """
            SELECT run.selected_profile, context.model_id,
                   context.reasoning_effort, context.service_tier
            FROM chat_run_execution_contexts AS context
            JOIN chat_runs AS run
              ON run.tenant_id = context.tenant_id
             AND run.id = context.run_id
            WHERE context.tenant_id = ? AND context.run_id = ?
            """,
            (identity.tenant_id, accepted.run_id),
        ).fetchone()
        assert str(frozen["selected_profile"]) == "codex-cli"
        assert tuple(frozen)[1:] == expected_selection
    finally:
        database.close()
    if execution_mode == "developer":
        runtime = RecordingCodexRuntime()
        direct_model_runtime.execute_direct_run(
            settings,
            accepted,
            _runtime_registry(settings, codex_runtime=runtime),
        )
        assert len(runtime.complete_calls) == 1
        assert runtime.complete_calls[0]["execution_profile"] == "developer"
        assert runtime.complete_calls[0]["model"] == "gpt-test-selected"
        assert runtime.complete_calls[0]["effort"] == "high"
        assert runtime.complete_calls[0]["service_tier"] == "priority"


def test_developer_mimo_profile_executes_mimo_without_codex_substitution(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "developer-mimo.db"
    settings = replace(
        _settings(database_path),
        direct_model_runtime_enabled=True,
        developer_agent_enabled=True,
        developer_workspace_root=tmp_path,
    )
    user = _registered_user(database_path)
    identity = UserSession(
        user_id=user["id"],
        tenant_id=user["tenantId"],
        role=UserRole.OWNER,
        preferred_agent_profile=AgentProfile.MIMO_CODE,
        preferred_model="gpt-test-selected",
        preferred_reasoning_effort="high",
        preferred_service_tier="priority",
        email="direct-model@example.com",
        name="Direct Model",
        is_platform_owner=True,
        platform_capabilities=(
            "platform.admin",
            "chat.developer.request",
            "chat.use",
        ),
    )
    database = connect_database(database_path)
    try:
        with transaction(database, immediate=True):
            _enable_developer_policy(database, identity)
            database.execute(
                """
                INSERT INTO provider_connections (
                    tenant_id, provider_id, status, auth_flow_supported,
                    authority_observed, last_verified_at, created_at, updated_at
                ) VALUES (?, 'mimo-code', 'connected', 0, 1, ?, ?, ?)
                """,
                (identity.tenant_id, NOW, NOW, NOW),
            )
        accepted = accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=AgUiRunInput.model_validate(
                {
                    "threadId": "thread_developer_mimo_01",
                    "runId": "run_developer_mimo_01",
                    "state": None,
                    "messages": [
                        {
                            "id": "message_developer_mimo_01",
                            "role": "user",
                            "content": "Исправь backend-тесты.",
                        }
                    ],
                    "tools": [],
                    "context": [],
                    "forwardedProps": {
                        "agentProfile": "mimo-code",
                        "executionMode": "developer",
                        "accessMode": "full",
                    },
                }
            ),
            prepared=_prepared(profile="mimo-code"),
        )
        frozen = database.execute(
            """
            SELECT run.selected_profile, context.model_id,
                   context.reasoning_effort, context.service_tier
            FROM chat_runs AS run
            JOIN chat_run_execution_contexts AS context
              ON context.tenant_id = run.tenant_id
             AND context.run_id = run.id
            WHERE run.tenant_id = ? AND run.id = ?
            """,
            (identity.tenant_id, accepted.run_id),
        ).fetchone()
        assert tuple(frozen) == ("mimo-code", None, None, None)
    finally:
        database.close()
    codex_runtime = RecordingCodexRuntime()
    mimo_developer_runtime = RecordingMimoDeveloperRuntime()

    direct_model_runtime.execute_direct_run(
        settings,
        accepted,
        _runtime_registry(
            settings,
            codex_runtime=codex_runtime,
            mimo_developer_runtime=mimo_developer_runtime,
        ),
    )

    assert codex_runtime.catalog_calls == 0
    assert codex_runtime.complete_calls == []
    assert len(mimo_developer_runtime.complete_calls) == 1
    assert mimo_developer_runtime.complete_calls[0]["access_mode"] == "full"
    assert mimo_developer_runtime.complete_calls[0]["workspace_root"] == tmp_path


def test_historical_developer_auto_profile_fails_without_substitution(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "developer-auto-mimo.db"
    settings = replace(
        _settings(database_path),
        direct_model_runtime_enabled=True,
        developer_agent_enabled=True,
        developer_workspace_root=tmp_path,
    )
    user = _registered_user(database_path)
    accepted = _seed_run(
        database_path,
        tenant_id=user["tenantId"],
        user_id=user["id"],
        model=None,
        effort=None,
        selected_profile="auto",
        execution_mode="developer",
        access_mode="auto",
        prompt="Исправь backend-тесты в репозитории.",
    )
    database = connect_database(database_path)
    try:
        with transaction(database, immediate=True):
            database.execute(
                """
                INSERT INTO provider_connections (
                    tenant_id, provider_id, status, auth_flow_supported,
                    authority_observed, last_verified_at, created_at, updated_at
                ) VALUES (?, 'mimo-code', 'connected', 0, 1, ?, ?, ?)
                """,
                (user["tenantId"], NOW, NOW, NOW),
            )
    finally:
        database.close()
    codex_runtime = RecordingCodexRuntime()
    mimo_developer_runtime = RecordingMimoDeveloperRuntime()

    direct_model_runtime.execute_direct_run(
        settings,
        accepted,
        _runtime_registry(
            settings,
            codex_runtime=codex_runtime,
            mimo_developer_runtime=mimo_developer_runtime,
        ),
    )

    assert codex_runtime.catalog_calls == 0
    assert codex_runtime.complete_calls == []
    assert mimo_developer_runtime.complete_calls == []
    database = sqlite3.connect(database_path)
    try:
        status, error_code = database.execute(
            "SELECT status, error_code FROM chat_runs WHERE id = ?",
            (RUN_ID,),
        ).fetchone()
    finally:
        database.close()
    assert status == "failed"
    assert error_code is not None


def test_legacy_developer_access_snapshot_is_locked_not_broadened(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy-developer-access.db"
    settings = _settings(database_path)
    user = _registered_user(database_path)
    accepted = _seed_run(
        database_path,
        tenant_id=user["tenantId"],
        user_id=user["id"],
        model="gpt-test-selected",
        effort="high",
        selected_profile="codex-cli",
        execution_mode="developer",
        access_mode="auto",
        prompt="Исправь backend-тесты в репозитории.",
    )
    database = connect_database(database_path)
    try:
        with transaction(database, immediate=True):
            database.execute(
                """
                UPDATE chat_run_execution_contexts
                SET access_policy_version = 1,
                    approval_policy = 'never',
                    approvals_reviewer = NULL
                WHERE tenant_id = ? AND run_id = ?
                """,
                (user["tenantId"], RUN_ID),
            )
    finally:
        database.close()
    runtime = RecordingCodexRuntime()

    direct_model_runtime.execute_direct_run(
        settings,
        accepted,
        _runtime_registry(settings, codex_runtime=runtime),
    )

    assert runtime.complete_calls == []
    database = sqlite3.connect(database_path)
    try:
        status, error_code = database.execute(
            "SELECT status, error_code FROM chat_runs WHERE id = ?",
            (RUN_ID,),
        ).fetchone()
    finally:
        database.close()
    assert (status, error_code) == (
        "failed",
        "developer_access_policy_legacy_locked",
    )


def test_omitted_legacy_developer_access_is_persisted_locked(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "omitted-legacy-developer.db"
    settings = replace(
        _settings(database_path),
        direct_model_runtime_enabled=True,
        developer_agent_enabled=True,
        developer_workspace_root=tmp_path,
    )
    user = _registered_user(database_path)
    identity = UserSession(
        user_id=user["id"],
        tenant_id=user["tenantId"],
        role=UserRole.OWNER,
        preferred_agent_profile=AgentProfile.CODEX_CLI,
        preferred_model_profile=AgentProfile.CODEX_CLI,
        preferred_model="gpt-test-selected",
        preferred_reasoning_effort="high",
        preferred_service_tier="priority",
        email="direct-model@example.com",
        name="Direct Model",
        is_platform_owner=True,
        platform_capabilities=(
            "platform.admin",
            "chat.developer.request",
            "chat.use",
        ),
    )
    database = connect_database(database_path)
    try:
        _enable_developer_policy(database, identity)
        accepted = accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=AgUiRunInput.model_validate(
                {
                    "threadId": "thread_legacy_omitted_01",
                    "runId": "run_legacy_omitted_01",
                    "state": None,
                    "messages": [
                        {
                            "id": "message_legacy_omitted_01",
                            "role": "user",
                            "content": "Исправь тесты.",
                        }
                    ],
                    "tools": [],
                    "context": [],
                    "forwardedProps": {
                        "agentProfile": "codex-cli",
                        "executionMode": "developer",
                    },
                }
            ),
            prepared=_prepared(
                profile="codex-cli",
                model="gpt-test-selected",
                effort="high",
                service_tier="priority",
            ),
        )
        frozen = database.execute(
            """
            SELECT access_mode, access_policy_version, sandbox_profile,
                   approval_policy, approvals_reviewer
            FROM chat_run_execution_contexts
            WHERE tenant_id = ? AND run_id = ?
            """,
            (identity.tenant_id, accepted.run_id),
        ).fetchone()
        assert tuple(frozen) == (
            "auto",
            1,
            "workspace-write",
            "never",
            None,
        )
    finally:
        database.close()

    direct_model_runtime.execute_direct_run(
        settings,
        accepted,
        _runtime_registry(settings, codex_runtime=RecordingCodexRuntime()),
    )

    database = sqlite3.connect(database_path)
    try:
        status, error_code = database.execute(
            "SELECT status, error_code FROM chat_runs WHERE id = ?",
            (accepted.run_id,),
        ).fetchone()
    finally:
        database.close()
    assert (status, error_code) == (
        "failed",
        "developer_access_policy_legacy_locked",
    )


@pytest.mark.parametrize(
    ("model", "effort", "expected_code"),
    (
        ("gpt-retired", "high", "codex_model_not_supported"),
        (
            "gpt-test-selected",
            "ultra",
            "codex_reasoning_effort_not_supported",
        ),
        (None, "high", "codex_model_selection_invalid"),
        ("gpt-test-selected", None, "codex_model_selection_invalid"),
        (None, None, "codex_model_selection_missing"),
    ),
)
def test_invalid_frozen_codex_selection_fails_without_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    model: str | None,
    effort: str | None,
    expected_code: str,
) -> None:
    database_path = tmp_path / f"{expected_code}.db"
    settings = _settings(database_path)
    user = _registered_user(database_path)
    accepted = _seed_run(
        database_path,
        tenant_id=user["tenantId"],
        user_id=user["id"],
        model=model,
        effort=effort,
    )
    monkeypatch.setattr(
        direct_model_runtime,
        "_connected_profile",
        lambda *_args, **_kwargs: ("codex-cli", user["tenantId"]),
    )
    runtime = RecordingCodexRuntime()

    direct_model_runtime.execute_direct_run(
        settings,
        accepted,
        _runtime_registry(settings, codex_runtime=runtime),
    )

    assert runtime.complete_calls == []
    database = sqlite3.connect(database_path)
    try:
        status, error_code = database.execute(
            "SELECT status, error_code FROM chat_runs WHERE id = ?",
            (RUN_ID,),
        ).fetchone()
    finally:
        database.close()
    assert (status, error_code) == ("failed", expected_code)


def test_unsupported_frozen_service_tier_fails_without_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "unsupported-service-tier.db"
    settings = _settings(database_path)
    user = _registered_user(database_path)
    accepted = _seed_run(
        database_path,
        tenant_id=user["tenantId"],
        user_id=user["id"],
        model="gpt-test-selected",
        effort="high",
        service_tier="burst",
    )
    monkeypatch.setattr(
        direct_model_runtime,
        "_connected_profile",
        lambda *_args, **_kwargs: ("codex-cli", user["tenantId"]),
    )
    runtime = RecordingCodexRuntime()

    direct_model_runtime.execute_direct_run(
        settings,
        accepted,
        _runtime_registry(settings, codex_runtime=runtime),
    )

    assert runtime.complete_calls == []
    database = sqlite3.connect(database_path)
    try:
        status, error_code = database.execute(
            "SELECT status, error_code FROM chat_runs WHERE id = ?",
            (RUN_ID,),
        ).fetchone()
    finally:
        database.close()
    assert (status, error_code) == (
        "failed",
        "codex_service_tier_not_supported",
    )


def test_automatic_profile_uses_server_default_without_a_frozen_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "auto-server-default.db"
    settings = _settings(database_path)
    user = _registered_user(database_path)
    accepted = _seed_run(
        database_path,
        tenant_id=user["tenantId"],
        user_id=user["id"],
        model=None,
        effort=None,
        selected_profile="auto",
    )
    monkeypatch.setattr(
        direct_model_runtime,
        "_connected_profile",
        lambda *_args, **_kwargs: ("codex-cli", user["tenantId"]),
    )
    monkeypatch.setenv("KOLIBRI_V3_CODEX_CHAT_MODEL", "gpt-server-owned")
    monkeypatch.setenv("KOLIBRI_V3_CODEX_CHAT_EFFORT", "low")
    runtime = RecordingCodexRuntime()

    direct_model_runtime.execute_direct_run(
        settings,
        accepted,
        _runtime_registry(settings, codex_runtime=runtime),
    )

    assert runtime.catalog_calls == 0
    assert runtime.complete_calls[0]["model"] == "gpt-server-owned"
    assert runtime.complete_calls[0]["effort"] == "low"
    assert runtime.complete_calls[0]["service_tier"] is None


def test_missing_execution_context_fails_instead_of_using_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "missing-execution-context.db"
    settings = _settings(database_path)
    user = _registered_user(database_path)
    accepted = _seed_run(
        database_path,
        tenant_id=user["tenantId"],
        user_id=user["id"],
        model=None,
        effort=None,
        include_execution_context=False,
    )
    monkeypatch.setattr(
        direct_model_runtime,
        "_connected_profile",
        lambda *_args, **_kwargs: ("codex-cli", user["tenantId"]),
    )
    runtime = RecordingCodexRuntime()

    direct_model_runtime.execute_direct_run(
        settings,
        accepted,
        _runtime_registry(settings, codex_runtime=runtime),
    )

    assert runtime.catalog_calls == 0
    assert runtime.complete_calls == []
    database = sqlite3.connect(database_path)
    try:
        status, error_code = database.execute(
            "SELECT status, error_code FROM chat_runs WHERE id = ?",
            (RUN_ID,),
        ).fetchone()
    finally:
        database.close()
    assert (status, error_code) == ("failed", "direct_run_context_missing")


def test_execution_mode_hint_cannot_override_frozen_context(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "execution-mode-mismatch.db"
    settings = _settings(database_path)
    user = _registered_user(database_path)
    accepted = _seed_run(
        database_path,
        tenant_id=user["tenantId"],
        user_id=user["id"],
        model="gpt-test-selected",
        effort="high",
    )
    accepted.execution_mode = "developer"
    runtime = RecordingCodexRuntime()

    direct_model_runtime.execute_direct_run(
        settings,
        accepted,
        _runtime_registry(settings, codex_runtime=runtime),
    )

    assert runtime.complete_calls == []
    database = sqlite3.connect(database_path)
    try:
        status, error_code = database.execute(
            "SELECT status, error_code FROM chat_runs WHERE id = ?",
            (RUN_ID,),
        ).fetchone()
    finally:
        database.close()
    assert (status, error_code) == (
        "failed",
        "direct_run_context_mismatch",
    )


def test_estimate_uses_the_frozen_accepted_model_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "estimate-server-owned.db"
    settings = _settings(database_path)
    user = _registered_user(database_path)
    accepted = _seed_run(
        database_path,
        tenant_id=user["tenantId"],
        user_id=user["id"],
        model="gpt-test-selected",
        effort="high",
        service_tier="priority",
        prompt=(
            "Составь смету на 358 м² механизированной штукатурки, "
            "слой 15 мм, Татарстан."
        ),
    )
    monkeypatch.setattr(
        direct_model_runtime,
        "_connected_profile",
        lambda *_args, **_kwargs: ("codex-cli", user["tenantId"]),
    )
    monkeypatch.setenv(
        "KOLIBRI_V3_CODEX_ESTIMATE_MODEL",
        "gpt-server-estimate",
    )
    monkeypatch.setenv("KOLIBRI_V3_CODEX_ESTIMATE_EFFORT", "low")
    runtime = RecordingCodexRuntime()

    direct_model_runtime.execute_direct_run(
        settings,
        accepted,
        _runtime_registry(settings, codex_runtime=runtime),
    )

    assert runtime.catalog_calls == 1
    assert len(runtime.complete_calls) == 1
    assert runtime.complete_calls[0]["model"] == "gpt-test-selected"
    assert runtime.complete_calls[0]["effort"] == "high"
    assert runtime.complete_calls[0]["service_tier"] == "priority"


def test_developer_uses_frozen_codex_selection_over_server_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "developer-server-owned.db"
    settings = replace(
        _settings(database_path),
        direct_model_runtime_enabled=True,
        developer_agent_enabled=True,
        developer_workspace_root=tmp_path,
    )
    user = _registered_user(database_path)
    accepted = _seed_run(
        database_path,
        tenant_id=user["tenantId"],
        user_id=user["id"],
        model="gpt-test-selected",
        effort="high",
        service_tier="priority",
        execution_mode="developer",
        access_mode="full",
    )
    monkeypatch.setenv(
        "KOLIBRI_V3_CODEX_DEVELOPER_MODEL",
        "gpt-server-developer",
    )
    monkeypatch.setenv("KOLIBRI_V3_CODEX_DEVELOPER_EFFORT", "medium")
    runtime = RecordingCodexRuntime()

    direct_model_runtime.execute_direct_run(
        settings,
        accepted,
        _runtime_registry(settings, codex_runtime=runtime),
    )

    assert runtime.catalog_calls == 1
    assert len(runtime.complete_calls) == 1
    assert runtime.complete_calls[0]["model"] == "gpt-test-selected"
    assert runtime.complete_calls[0]["effort"] == "high"
    assert runtime.complete_calls[0]["service_tier"] == "priority"
    assert runtime.complete_calls[0]["sandbox"] == "danger-full-access"
    assert runtime.complete_calls[0]["approval_policy"] == "never"
    assert runtime.complete_calls[0]["approvals_reviewer"] is None


def test_developer_auto_access_uses_reviewed_workspace_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "developer-auto-access.db"
    settings = replace(
        _settings(database_path),
        direct_model_runtime_enabled=True,
        developer_agent_enabled=True,
        developer_workspace_root=tmp_path,
    )
    user = _registered_user(database_path)
    accepted = _seed_run(
        database_path,
        tenant_id=user["tenantId"],
        user_id=user["id"],
        model="gpt-test-selected",
        effort="high",
        service_tier="priority",
        execution_mode="developer",
        access_mode="auto",
    )
    runtime = RecordingCodexRuntime()

    direct_model_runtime.execute_direct_run(
        settings,
        accepted,
        _runtime_registry(settings, codex_runtime=runtime),
    )

    assert len(runtime.complete_calls) == 1
    assert runtime.complete_calls[0]["model"] == "gpt-test-selected"
    assert runtime.complete_calls[0]["sandbox"] == "workspace-write"
    assert runtime.complete_calls[0]["approval_policy"] == "on-request"
    assert runtime.complete_calls[0]["approvals_reviewer"] == "auto_review"


def test_tampered_developer_access_context_is_rejected(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "developer-access-tampered.db"
    settings = replace(
        _settings(database_path),
        direct_model_runtime_enabled=True,
        developer_agent_enabled=True,
        developer_workspace_root=tmp_path,
    )
    user = _registered_user(database_path)
    accepted = _seed_run(
        database_path,
        tenant_id=user["tenantId"],
        user_id=user["id"],
        model=None,
        effort=None,
        execution_mode="developer",
        access_mode="full",
    )
    database = sqlite3.connect(database_path)
    try:
        database.execute("PRAGMA ignore_check_constraints = ON")
        database.execute(
            """
            UPDATE chat_run_execution_contexts
            SET access_mode = 'auto'
            WHERE run_id = ?
            """,
            (RUN_ID,),
        )
        database.commit()
    finally:
        database.close()
    runtime = RecordingCodexRuntime()

    direct_model_runtime.execute_direct_run(
        settings,
        accepted,
        _runtime_registry(settings, codex_runtime=runtime),
    )

    assert runtime.complete_calls == []
    database = sqlite3.connect(database_path)
    try:
        status, error_code = database.execute(
            "SELECT status, error_code FROM chat_runs WHERE id = ?",
            (RUN_ID,),
        ).fetchone()
    finally:
        database.close()
    assert (status, error_code) == (
        "failed",
        "developer_access_context_invalid",
    )


def test_greeting_after_existing_estimate_stays_plain_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "greeting-after-estimate.db"
    settings = _settings(database_path)
    user = _registered_user(database_path)
    accepted = _seed_run(
        database_path,
        tenant_id=user["tenantId"],
        user_id=user["id"],
        model="gpt-test-selected",
        effort="low",
        prompt="привет",
    )
    _seed_existing_estimate_slot(
        database_path,
        tenant_id=user["tenantId"],
        user_id=user["id"],
    )
    monkeypatch.setattr(
        direct_model_runtime,
        "_connected_profile",
        lambda *_args, **_kwargs: pytest.fail("model profile must not be used"),
    )
    runtime = RecordingCodexRuntime()

    direct_model_runtime.execute_direct_run(
        settings,
        accepted,
        _runtime_registry(settings, codex_runtime=runtime),
    )

    assert runtime.complete_calls == []
    database = sqlite3.connect(database_path)
    try:
        message = database.execute(
            """
            SELECT content_text, content_json
            FROM chat_messages
            WHERE tenant_id = ? AND run_id = ? AND role = 'assistant'
            """,
            (user["tenantId"], RUN_ID),
        ).fetchone()
        event_types = [
            row[0]
            for row in database.execute(
                """
                SELECT event_type
                FROM chat_run_events
                WHERE tenant_id = ? AND run_id = ?
                ORDER BY sequence
                """,
                (user["tenantId"], RUN_ID),
            ).fetchall()
        ]
    finally:
        database.close()
    assert tuple(message) == ("Привет! Чем могу помочь?", None)
    assert "TOOL_CALL_START" not in event_types
    assert event_types[-1] == "RUN_FINISHED"
