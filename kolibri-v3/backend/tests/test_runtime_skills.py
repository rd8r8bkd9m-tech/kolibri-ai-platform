from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import app.direct_model_runtime as direct_model_runtime
import app.runtime_skills as runtime_skills_module
import pytest
from app.chat.execution_adapter import PreparedChatExecution
from app.chat.models import AgUiRunInput
from app.chat.service import accept_run
from app.config import Settings
from app.database import (
    connect_database,
    initialize_database,
    migration_paths,
    transaction,
)
from app.estimate_engine_router import (
    PlasteringCalculationInput,
    _project_snapshot,
)
from app.estimate_intake import (
    PlasteringIntake,
    plastering_intake_instructions,
)
from app.main import create_app
from app.product_entitlements import bind_product_entitlements
from app.runtime_skills import (
    RuntimeSkillError,
    RuntimeSkillPlan,
    estimate_runtime_skill_plan,
    load_runtime_skill_plan,
    persist_runtime_skill_plan,
    skill_plan_evidence,
)
from app.schemas import AgentProfile, UserRole, UserSession
from fastapi.testclient import TestClient

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"
NOW = "2026-07-29T00:00:00Z"
PROJECT_ID = "project_runtime_skill_01"
THREAD_ID = "thread_runtime_skill_01"
MESSAGE_ID = "message_runtime_skill_01"
RUN_ID = "run_runtime_skill_01"


def _runtime_registry(
    settings: Settings,
    *,
    codex_runtime: object | None = None,
    mimo_runtime: object | None = None,
):
    return direct_model_runtime._legacy_runtime_registry(
        settings,
        codex_transport=codex_runtime,
        mimo_transport=mimo_runtime,
        mimo_developer_transport=None,
)

LATEST_SCHEMA_VERSION = int(migration_paths()[-1].name.split("_", 1)[0])


def _register(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/v1/auth/register",
        headers=ORIGIN,
        json={
            "email": "runtime-skills@example.com",
            "name": "Runtime Skills",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201
    return response.json()["user"]


def _seed_estimate_run(
    database_path: Path,
    *,
    tenant_id: str,
    user_id: str,
) -> None:
    database = connect_database(database_path)
    try:
        with transaction(database, immediate=True):
            database.execute(
                """
                INSERT INTO projects (
                    tenant_id, id, created_by_user_id, title, status,
                    primary_thread_id, created_at, updated_at
                ) VALUES (?, ?, ?, 'Штукатурка 358 м²', 'active', ?, ?, ?)
                """,
                (tenant_id, PROJECT_ID, user_id, THREAD_ID, NOW, NOW),
            )
            database.execute(
                """
                INSERT INTO chat_threads (
                    tenant_id, id, project_id, kind, title, status,
                    message_count, run_count, created_at, updated_at
                ) VALUES (?, ?, ?, 'primary', 'Штукатурка 358 м²', 'regular',
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
                    ) VALUES (?, ?, ?, ?, 1, 'client_runtime_skill_01', 'user',
                              ?, ?, ?)
                    """,
                (
                    tenant_id,
                    MESSAGE_ID,
                    PROJECT_ID,
                    THREAD_ID,
                    (
                        "Составь смету на 358 м² механизированной "
                        "штукатурки, слой 15 мм, Татарстан."
                    ),
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
                ) VALUES (?, ?, ?, ?, 'client_run_runtime_skill_01', ?, ?, ?,
                          'codex-cli', 'running', 1, ?, ?, ?)
                """,
                (
                    tenant_id,
                    RUN_ID,
                    PROJECT_ID,
                    THREAD_ID,
                    "sha256:" + ("a" * 64),
                    MESSAGE_ID,
                    user_id,
                    NOW,
                    NOW,
                    NOW,
                ),
            )
            database.execute(
                """
                INSERT INTO chat_run_execution_contexts (
                    tenant_id, run_id, execution_mode, access_mode,
                    authority_role, authority_user_id, workspace_ref,
                    sandbox_profile, approval_policy, approvals_reviewer,
                    model_id, reasoning_effort, service_tier, created_at
                ) VALUES (
                    ?, ?, 'standard', 'standard', 'user', ?, NULL,
                    'read-only', 'never', NULL, NULL, NULL, NULL, ?
                )
                """,
                (tenant_id, RUN_ID, user_id, NOW),
            )
    finally:
        database.close()


def _snapshot_payload() -> PlasteringCalculationInput:
    return PlasteringCalculationInput.model_validate(
        {
            "expectedEstimateVersion": 1,
            "region": "Республика Татарстан",
            "title": "Смета штукатурки 358 м²",
            "assumptions": ["Высота стен предварительно принята 3 м."],
            "scope": {
                "wallAreaM2": "358",
                "averageThicknessMm": "15",
                "material": "gypsum",
                "applicationMethod": "mechanized",
                "wastePercent": "10",
                "protectionAreaM2": "358",
                "wallHeightM": "3",
                "beaconSpacingM": "1.5",
                "cornerLengthM": "0",
                "meshAreaPercent": "10",
                "slopesAreaM2": "0",
                "plasterBagWeightKg": "30",
                "primerPasses": 1,
                "wasteRemovalTrips": "1",
            },
            "prices": [],
            "sourceMessageId": MESSAGE_ID,
            "sourceRunId": RUN_ID,
        }
    )


def _complete_intake() -> PlasteringIntake:
    return PlasteringIntake.model_validate(
        {
            "title": "Смета штукатурки 358 м²",
            "region": "Республика Татарстан",
            "wallAreaM2": "358",
            "averageThicknessMm": "15",
            "material": "gypsum",
            "applicationMethod": "mechanized",
            "wastePercent": "10",
            "protectionAreaM2": "358",
            "wallHeightM": "3",
            "beaconSpacingM": "1.5",
            "cornerLengthM": "0",
            "meshAreaPercent": "10",
            "slopesAreaM2": "0",
            "plasterBagWeightKg": "30",
            "primerPasses": 1,
            "wasteRemovalTrips": "1",
            "assumptions": ["Высота стен принята равной 3 м."],
            "candidatePrices": [],
        }
    )


def test_estimate_runtime_skill_plan_is_deterministic_and_bounded() -> None:
    first = estimate_runtime_skill_plan()
    second = estimate_runtime_skill_plan()

    assert first.content_hash == second.content_hash
    assert [item.stage for item in first.uses] == [
        "project_case_analysis",
        "technology_card_build",
        "technology_card_build",
        "price_candidates_verify",
        "estimate_engine_calculate",
        "estimate_verification",
    ]
    guidance = first.guidance_for_stage("project_case_analysis")
    assert "факты и допущения" in guidance
    assert "не выполняй расчёт" in guidance
    assert ".agents/skills" not in guidance
    assert "api_key" not in guidance.casefold()


def test_runtime_skill_migration_upgrades_a_v21_database(tmp_path: Path) -> None:
    database_path = tmp_path / "runtime-skills-upgrade.db"
    database = connect_database(database_path)
    try:
        for migration_path in migration_paths():
            version = int(migration_path.name.split("_", 1)[0])
            if version <= 21:
                database.executescript(migration_path.read_text(encoding="utf-8"))
        assert database.execute("PRAGMA user_version").fetchone()[0] == 21
    finally:
        database.close()

    initialize_database(database_path)

    database = connect_database(database_path)
    try:
        assert (
            database.execute("PRAGMA user_version").fetchone()[0]
            == LATEST_SCHEMA_VERSION
        )
        assert (
            database.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                "AND name = 'chat_run_skill_contexts'"
            ).fetchone()
            is not None
        )
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        database.close()


def test_runtime_skill_context_is_immutable_and_tamper_evident(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "runtime-skills.db"
    settings = Settings.for_testing(database_url=database_path)
    with TestClient(create_app(settings)) as client:
        user = _register(client)
        _seed_estimate_run(
            database_path,
            tenant_id=user["tenantId"],
            user_id=user["id"],
        )

    plan = estimate_runtime_skill_plan()
    database = connect_database(database_path)
    try:
        with transaction(database, immediate=True):
            persist_runtime_skill_plan(
                database,
                tenant_id=user["tenantId"],
                run_id=RUN_ID,
                plan=plan,
                created_at=NOW,
            )
            # Same run and same reviewed plan are an idempotent replay.
            persist_runtime_skill_plan(
                database,
                tenant_id=user["tenantId"],
                run_id=RUN_ID,
                plan=plan,
                created_at=NOW,
            )

        assert database.execute(
            "SELECT COUNT(*) FROM chat_run_skill_contexts"
        ).fetchone()[0] == len(plan.uses)
        assert (
            load_runtime_skill_plan(
                database,
                tenant_id=user["tenantId"],
                run_id=RUN_ID,
            ).content_hash
            == plan.content_hash
        )
        assert (
            load_runtime_skill_plan(
                database,
                tenant_id="tenant_other_runtime_skill_01",
                run_id=RUN_ID,
            )
            is None
        )

        # Updating the default plan must not reinterpret an accepted run.
        upgraded_default = RuntimeSkillPlan(
            uses=plan.uses,
            registry_version="kolibri-runtime-skills/2026-07-30.1",
        )
        monkeypatch.setattr(
            runtime_skills_module,
            "_CURRENT_ESTIMATE_SKILL_PLAN",
            upgraded_default,
        )
        assert estimate_runtime_skill_plan().content_hash == (
            upgraded_default.content_hash
        )
        assert (
            load_runtime_skill_plan(
                database,
                tenant_id=user["tenantId"],
                run_id=RUN_ID,
            ).content_hash
            == plan.content_hash
        )

        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                "DELETE FROM chat_runs WHERE tenant_id = ? AND id = ?",
                (user["tenantId"], RUN_ID),
            )

        context_id = database.execute(
            """
            SELECT id
            FROM chat_run_skill_contexts
            WHERE tenant_id = ? AND run_id = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (user["tenantId"], RUN_ID),
        ).fetchone()["id"]
        database.execute(
            """
            UPDATE chat_run_skill_contexts
            SET instruction_hash = ?
            WHERE tenant_id = ? AND id = ?
            """,
            ("sha256:" + ("0" * 64), user["tenantId"], context_id),
        )
        with pytest.raises(RuntimeSkillError, match="inconsistent"):
            load_runtime_skill_plan(
                database,
                tenant_id=user["tenantId"],
                run_id=RUN_ID,
            )
    finally:
        database.close()


def test_estimate_run_acceptance_freezes_server_owned_skill_plan(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "runtime-skills-acceptance.db"
    settings = replace(
        Settings.for_testing(database_url=database_path),
        direct_model_runtime_enabled=True,
    )
    with TestClient(create_app(settings)) as client:
        user = _register(client)

    run_input = AgUiRunInput.model_validate(
        {
            "threadId": "thread_runtime_accept_01",
            "runId": "run_runtime_accept_01",
            "state": None,
            "messages": [
                {
                    "id": "message_runtime_accept_01",
                    "role": "user",
                    "content": (
                        "Составь смету на 358 м² механизированной "
                        "штукатурки, слой 15 мм, Татарстан."
                    ),
                }
            ],
            "tools": [],
            "context": [],
            "forwardedProps": {"agentProfile": "codex-cli"},
        }
    )
    identity = UserSession(
        user_id=user["id"],
        tenant_id=user["tenantId"],
        role=UserRole.USER,
        preferred_agent_profile=AgentProfile.CODEX_CLI,
        email="runtime-skills@example.com",
        name="Runtime Skills",
    )
    database = connect_database(database_path)
    try:
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
            prepared=PreparedChatExecution(
                execution_plane="direct",
                runtime_profile="codex-cli",
                model_id=None,
                reasoning_effort=None,
                service_tier=None,
            ),
        )
        persisted = load_runtime_skill_plan(
            database,
            tenant_id=identity.tenant_id,
            run_id=accepted.run_id,
        )
        assert persisted is not None
        assert persisted.content_hash == estimate_runtime_skill_plan().content_hash
        assert database.execute(
            "SELECT COUNT(*) FROM chat_run_skill_contexts WHERE run_id = ?",
            (accepted.run_id,),
        ).fetchone()[0] == len(persisted.uses)
    finally:
        database.close()


def test_project_case_snapshot_keeps_runtime_skill_provenance(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "runtime-skills-snapshot.db"
    settings = Settings.for_testing(database_url=database_path)
    with TestClient(create_app(settings)) as client:
        user = _register(client)
        _seed_estimate_run(
            database_path,
            tenant_id=user["tenantId"],
            user_id=user["id"],
        )

    plan = estimate_runtime_skill_plan()
    database = connect_database(database_path)
    try:
        with transaction(database, immediate=True):
            persist_runtime_skill_plan(
                database,
                tenant_id=user["tenantId"],
                run_id=RUN_ID,
                plan=plan,
                created_at=NOW,
            )
            # A retry of the same input message can legitimately create a
            # second run.  Its existence must not replace the exact run that
            # produced this ProjectCase snapshot.
            database.execute(
                """
                INSERT INTO chat_runs (
                    tenant_id, id, project_id, thread_id, client_run_id,
                    request_hash, input_message_id, requested_by_user_id,
                    selected_profile, status, last_event_sequence,
                    heartbeat_at, created_at, updated_at
                ) VALUES (?, 'run_runtime_skill_02', ?, ?,
                          'client_run_runtime_skill_02', ?, ?, ?,
                          'codex-cli', 'running', 1, ?, ?, ?)
                """,
                (
                    user["tenantId"],
                    PROJECT_ID,
                    THREAD_ID,
                    "sha256:" + ("b" * 64),
                    MESSAGE_ID,
                    user["id"],
                    NOW,
                    NOW,
                    NOW,
                ),
            )
            snapshot = _project_snapshot(
                database,
                identity=UserSession(
                    user_id=user["id"],
                    tenant_id=user["tenantId"],
                    role=UserRole.USER,
                    preferred_agent_profile=AgentProfile.CODEX_CLI,
                    email="runtime-skills@example.com",
                    name="Runtime Skills",
                ),
                project_id=PROJECT_ID,
                case_id="case_runtime_skill_01",
                case_version=1,
                payload=_snapshot_payload(),
            )

        assert snapshot["runtimeSkillPlan"] == skill_plan_evidence(plan)
        assert snapshot["sourceRunId"] == RUN_ID
        assert "guidance" not in str(snapshot["runtimeSkillPlan"])
    finally:
        database.close()


def test_failed_engine_materialization_closes_every_started_tool_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "runtime-skills-tool-stage.db"
    settings = Settings.for_testing(database_url=database_path)
    with TestClient(create_app(settings)) as client:
        user = _register(client)
        _seed_estimate_run(
            database_path,
            tenant_id=user["tenantId"],
            user_id=user["id"],
        )

    plan = estimate_runtime_skill_plan()
    database = connect_database(database_path)
    try:
        with transaction(database, immediate=True):
            persist_runtime_skill_plan(
                database,
                tenant_id=user["tenantId"],
                run_id=RUN_ID,
                plan=plan,
                created_at=NOW,
            )
    finally:
        database.close()

    captured: dict[str, str] = {}

    def intake_stub(*_args: object, **kwargs: object) -> PlasteringIntake:
        guidance = kwargs.get("runtime_guidance")
        assert isinstance(guidance, str)
        captured["guidance"] = guidance
        return _complete_intake()

    def persistence_failure(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("simulated estimate persistence failure")

    monkeypatch.setattr(
        direct_model_runtime,
        "_connected_profile",
        lambda *_args, **_kwargs: ("codex-cli", user["tenantId"]),
    )
    monkeypatch.setattr(
        direct_model_runtime,
        "_codex_plastering_intake",
        intake_stub,
    )
    monkeypatch.setattr(
        direct_model_runtime,
        "materialize_engine_estimate_widget",
        persistence_failure,
    )

    accepted = SimpleNamespace(
        tenant_id=user["tenantId"],
        project_id=PROJECT_ID,
        thread_id=THREAD_ID,
        public_thread_id=THREAD_ID,
        run_id=RUN_ID,
        public_run_id=RUN_ID,
    )
    direct_model_runtime.execute_direct_run(
        settings,
        accepted,
        _runtime_registry(settings, codex_runtime=object()),
    )

    database = connect_database(database_path)
    try:
        events = [
            json.loads(str(row["event_json"]))
            for row in database.execute(
                """
                SELECT event_json
                FROM chat_run_events
                WHERE tenant_id = ? AND run_id = ?
                ORDER BY sequence ASC
                """,
                (user["tenantId"], RUN_ID),
            ).fetchall()
        ]
        started = {
            str(event["toolCallId"]): str(event["toolCallName"])
            for event in events
            if event["type"] == "TOOL_CALL_START"
        }
        finished = {
            str(event["toolCallId"])
            for event in events
            if event["type"] == "TOOL_CALL_RESULT"
        }
        assert started
        assert set(started).issubset(finished)
        technology_id = next(
            tool_id
            for tool_id, tool_name in started.items()
            if tool_name == "technology_card_build"
        )
        technology_result = next(
            event
            for event in events
            if event["type"] == "TOOL_CALL_RESULT"
            and event["toolCallId"] == technology_id
        )
        assert json.loads(technology_result["content"]) == {
            "errorCode": "estimate_persistence_failed",
            "status": "failed",
        }
        run = database.execute(
            """
            SELECT status, error_code
            FROM chat_runs
            WHERE tenant_id = ? AND id = ?
            """,
            (user["tenantId"], RUN_ID),
        ).fetchone()
        assert dict(run) == {
            "status": "failed",
            "error_code": "estimate_persistence_failed",
        }
    finally:
        database.close()

    assert "kolibri-supply-pricing" in captured["guidance"]
    assert "kolibri-estimate-domain" in captured["guidance"]


def test_codex_and_mimo_receive_the_same_reviewed_runtime_guidance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = estimate_runtime_skill_plan()
    expected_guidance = "\n\n".join(
        guidance
        for guidance in (
            plan.guidance_for_stage("project_case_analysis"),
            plan.guidance_for_stage("technology_card_build"),
            plan.guidance_for_stage("price_candidates_verify"),
            plan.guidance_for_stage("estimate_engine_calculate"),
            plan.guidance_for_stage("estimate_verification"),
        )
        if guidance
    )
    captured: dict[str, str] = {}

    def codex_stub(*_args: object, **kwargs: object) -> PlasteringIntake:
        captured["codex-cli"] = str(kwargs["runtime_guidance"])
        return _complete_intake()

    def mimo_stub(*_args: object, **kwargs: object) -> PlasteringIntake:
        captured["mimo-code"] = str(kwargs["runtime_guidance"])
        return _complete_intake()

    def persistence_failure(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("stop after provider guidance capture")

    monkeypatch.setattr(
        direct_model_runtime,
        "_connected_profile",
        lambda _database, _accepted, requested: (requested, _accepted.tenant_id),
    )
    monkeypatch.setattr(
        direct_model_runtime,
        "_codex_plastering_intake",
        codex_stub,
    )
    monkeypatch.setattr(
        direct_model_runtime,
        "_mimo_plastering_intake",
        mimo_stub,
    )
    monkeypatch.setattr(
        direct_model_runtime,
        "materialize_engine_estimate_widget",
        persistence_failure,
    )

    for profile in ("codex-cli", "mimo-code"):
        database_path = tmp_path / f"runtime-skills-{profile}.db"
        settings = Settings.for_testing(database_url=database_path)
        with TestClient(create_app(settings)) as client:
            user = _register(client)
            _seed_estimate_run(
                database_path,
                tenant_id=user["tenantId"],
                user_id=user["id"],
            )
        database = connect_database(database_path)
        try:
            with transaction(database, immediate=True):
                database.execute(
                    """
                    UPDATE chat_runs
                    SET selected_profile = ?
                    WHERE tenant_id = ? AND id = ?
                    """,
                    (profile, user["tenantId"], RUN_ID),
                )
                persist_runtime_skill_plan(
                    database,
                    tenant_id=user["tenantId"],
                    run_id=RUN_ID,
                    plan=plan,
                    created_at=NOW,
                )
        finally:
            database.close()

        direct_model_runtime.execute_direct_run(
            settings,
            SimpleNamespace(
                tenant_id=user["tenantId"],
                project_id=PROJECT_ID,
                thread_id=THREAD_ID,
                public_thread_id=THREAD_ID,
                run_id=RUN_ID,
                public_run_id=RUN_ID,
            ),
            _runtime_registry(
                settings,
                codex_runtime=object(),
                mimo_runtime=object(),
            ),
        )

    assert captured == {
        "codex-cli": expected_guidance,
        "mimo-code": expected_guidance,
    }


def test_intake_prompt_accepts_only_server_resolved_runtime_guidance() -> None:
    plan = estimate_runtime_skill_plan()
    guidance = plan.guidance_for_stage("project_case_analysis")

    prompt = plastering_intake_instructions(
        today="2026-07-29",
        runtime_guidance=guidance,
    )

    assert prompt.endswith(guidance)
    assert "Серверный контекст текущего этапа" in prompt
    assert "Estimate Engine" in prompt
