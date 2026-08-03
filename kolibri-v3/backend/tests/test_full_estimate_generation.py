from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import app.direct_model_runtime as runtime_module
from app.agent_runtime import (
    AgentModelSelection,
    AgentRuntimeError,
    AgentRuntimeRequest,
    AgentRuntimeResult,
)
from app.config import Settings
from app.database import connect_database, initialize_database
from app.estimate_artifact import parse_generated_estimate_section


class SectionTransportFixture:
    """Exercises section aggregation only; it is not semantic estimate QA."""

    def __init__(
        self,
        *,
        invalid_plan_attempts: int = 0,
        invalid_project_case_attempts: int = 0,
        transient_role_failures: int = 0,
    ) -> None:
        self.requests: list[AgentRuntimeRequest] = []
        self.sections_by_hash: dict[str, tuple[str, list[dict[str, object]]]] = {}
        self.invalid_plan_attempts = invalid_plan_attempts
        self.invalid_project_case_attempts = invalid_project_case_attempts
        self.transient_role_failures = transient_role_failures
        self.plan_attempt_count = 0
        self.role_failure_count = 0

    @staticmethod
    def _section_from_request(request: AgentRuntimeRequest) -> str:
        candidates = [
            request.messages[-1].content if request.messages else "",
            request.initial_prompt or "",
            request.instructions or "",
        ]
        for value in candidates:
            if "«" in value and "»" in value:
                return value.split("«", 1)[1].split("»", 1)[0]
        raise AssertionError("estimate role request must identify its section")

    def execute(self, request: AgentRuntimeRequest) -> AgentRuntimeResult:
        self.requests.append(request)
        if request.execution_profile == "estimate-plan":
            self.plan_attempt_count += 1
            if self.plan_attempt_count <= self.invalid_plan_attempts:
                return AgentRuntimeResult(text="{not valid JSON")
            return AgentRuntimeResult(
                text=json.dumps(
                    {
                        "title": "Полная смета девятиэтажного дома",
                        "region": "Казань",
                        "assumptions": ["Проектные объёмы требуют подтверждения."],
                        "sections": [f"Раздел {index + 1}" for index in range(10)],
                        "variables": {
                            "FLOOR_COUNT": {
                                "value": "9",
                                "unit": (
                                    "неподдерживаемая-единица"
                                    if self.plan_attempt_count
                                    <= self.invalid_project_case_attempts
                                    else "1"
                                ),
                                "basis": "Девять этажей указаны пользователем.",
                            }
                        },
                    },
                    ensure_ascii=False,
                )
            )
        profile = request.execution_profile
        section_hash = profile.rsplit(":", 1)[-1]
        if profile.startswith("estimate-pricing:"):
            section, resources = self.sections_by_hash[section_hash]
            return AgentRuntimeResult(
                text=json.dumps(
                    {
                        "section": section,
                        "candidates": [
                            {
                                "resourceId": resource["resourceId"],
                                "unitPrice": resource["proposedUnitPrice"],
                                "evidence": {
                                    "sourceType": "ai_preliminary",
                                    "sourceReference": (
                                        "Fixture preliminary price; no external source."
                                    ),
                                    "sourceUrl": None,
                                    "observedAt": "2026-08-02T00:00:00Z",
                                    "region": "Казань",
                                    "unit": resource["unit"],
                                    "vatTreatment": "not_specified",
                                    "deliveryIncluded": False,
                                    "validUntil": None,
                                    "snapshotHash": None,
                                    "confidence": "preliminary",
                                },
                            }
                            for resource in resources
                        ],
                    },
                    ensure_ascii=False,
                )
            )
        if profile.startswith("estimate-review:"):
            return AgentRuntimeResult(
                text=json.dumps({"passed": True, "issues": []})
            )
        assert profile.startswith("estimate-role:")
        if self.role_failure_count < self.transient_role_failures:
            self.role_failure_count += 1
            raise AgentRuntimeError(
                "future_runtime_transport_failed",
                "Временный сбой фиктивного будущего runtime.",
                category="unavailable",
                retryable=True,
            )
        section = self._section_from_request(request)
        section_index = int(section.rsplit(" ", 1)[-1])
        resources = [
            {
                "resourceId": f"resource_fixture_{section_index}_{index + 1}",
                "kind": "work" if index % 2 == 0 else "material",
                "description": f"{section}, ресурсная позиция {index + 1}",
                "unit": "шт.",
                "quantity": "1",
                "quantityFormula": {
                    "op": "constant",
                    "value": "1",
                    "unit": "шт.",
                },
                "quantityBasis": (
                    "Проектное количество; подтвердить ведомостью объёмов."
                ),
                "proposedUnitPrice": "100.00",
                "priceBasis": (
                    "Предварительная оценка AI; проверить источник."
                ),
            }
            for index in range(100)
        ]
        self.sections_by_hash[section_hash] = (section, resources)
        return AgentRuntimeResult(
            text=json.dumps(
                {
                    "section": section,
                    "operations": [
                        {
                            "operationId": f"operation_fixture_{section_index}",
                            "wbsCode": str(section_index),
                            "section": section,
                            "zone": "Объект",
                            "system": section,
                            "sequence": 1,
                            "name": f"Комплекс операций: {section}",
                            "method": "Последовательная тестовая операция.",
                            "unit": "компл.",
                            "quantityFormula": {
                                "op": "constant",
                                "value": "1",
                                "unit": "компл.",
                            },
                            "resources": resources,
                            "qualityChecks": ["Контроль транспортного fixture."],
                        }
                    ],
                },
                ensure_ascii=False,
            )
        )


def _seed_generation_project(database_path: Path) -> None:
    initialize_database(database_path)
    database = connect_database(database_path)
    try:
        database.execute(
            "INSERT INTO tenants (id, name, created_at) VALUES (?, ?, ?)",
            ("tenant_full_estimate", "Full estimate fixture", 1),
        )
        database.execute(
            """
            INSERT INTO users (
                id, tenant_id, email_normalized, email, name, role,
                preferred_agent_profile, password_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'owner', 'auto', 'test-only', 1, 1)
            """,
            (
                "user_full_estimate",
                "tenant_full_estimate",
                "full-estimate@example.com",
                "full-estimate@example.com",
                "Full estimate fixture",
            ),
        )
        database.execute(
            """
            INSERT INTO projects (
                tenant_id, id, created_by_user_id, title, status,
                primary_thread_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                "tenant_full_estimate",
                "project_full_estimate",
                "user_full_estimate",
                "Полная тестовая смета",
                "thread_full_estimate",
                "2026-08-02T00:00:00Z",
                "2026-08-02T00:00:00Z",
            ),
        )
        database.execute(
            """
            INSERT INTO chat_threads (
                tenant_id, id, project_id, kind, title, status,
                message_count, run_count, last_message_at, created_at, updated_at
            ) VALUES (?, ?, ?, 'primary', ?, 'regular', 1, 1, ?, ?, ?)
            """,
            (
                "tenant_full_estimate",
                "thread_full_estimate",
                "project_full_estimate",
                "Полная тестовая смета",
                "2026-08-02T00:00:00Z",
                "2026-08-02T00:00:00Z",
                "2026-08-02T00:00:00Z",
            ),
        )
        database.execute(
            """
            INSERT INTO chat_messages (
                tenant_id, id, project_id, thread_id, sequence,
                client_message_id, run_id, role, content_text,
                created_by_user_id, created_at
            ) VALUES (?, ?, ?, ?, 1, ?, ?, 'user', ?, ?, ?)
            """,
            (
                "tenant_full_estimate",
                "message_full_estimate",
                "project_full_estimate",
                "thread_full_estimate",
                "client_message_full_estimate",
                "run_full_estimate",
                "Составь полную смету девятиэтажного дома в Казани.",
                "user_full_estimate",
                "2026-08-02T00:00:00Z",
            ),
        )
        database.execute(
            """
            INSERT INTO chat_runs (
                tenant_id, id, project_id, thread_id, client_run_id,
                request_hash, input_message_id, requested_by_user_id,
                selected_profile, status, last_event_sequence,
                heartbeat_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'codex-cli', 'running', 0, ?, ?, ?)
            """,
            (
                "tenant_full_estimate",
                "run_full_estimate",
                "project_full_estimate",
                "thread_full_estimate",
                "client_run_full_estimate",
                "sha256:" + ("a" * 64),
                "message_full_estimate",
                "user_full_estimate",
                "2026-08-02T00:00:00Z",
                "2026-08-02T00:00:00Z",
                "2026-08-02T00:00:00Z",
            ),
        )
        database.commit()
    finally:
        database.close()


def test_section_contract_rejects_free_form_quantity_formula() -> None:
    runtime = SectionTransportFixture()
    result = runtime.execute(  # type: ignore[arg-type]
        SimpleNamespace(
            execution_profile="estimate-role:technologist:fixturehash",
            messages=[SimpleNamespace(content="Раздел «Раздел 1»")],
            initial_prompt="",
            instructions="",
        )
    )
    payload = json.loads(result.text)
    payload["operations"][0]["quantityFormula"] = "1 комплект"

    with pytest.raises(ValidationError):
        parse_generated_estimate_section(json.dumps(payload, ensure_ascii=False))


def test_hierarchical_wbs_plan_uses_non_overlapping_root_sections() -> None:
    plan = runtime_module.GeneratedEstimatePlan.model_validate(
        {
            "title": "Иерархическая смета",
            "region": "Казань",
            "assumptions": ["Предварительный расчёт."],
            "sections": [
                "1. Подготовительные работы",
                "1.1. Ограждение площадки",
                "1.1.1. Монтаж стоек",
                "2. Фундаменты",
                "2.1. Фундаментная плита",
                "Ненумерованный самостоятельный раздел",
            ],
        }
    )

    sections = runtime_module._estimate_sections(plan)

    assert [section["title"] for section in sections] == [
        "1. Подготовительные работы",
        "2. Фундаменты",
        "Ненумерованный самостоятельный раздел",
    ]


def test_explicit_unknowns_as_assumptions_clear_nonblocking_questions() -> None:
    plan = runtime_module.GeneratedEstimatePlan.model_validate(
        {
            "title": "Предварительная смета",
            "region": "Казань",
            "assumptions": ["Площадь объекта задана пользователем."],
            "blockingQuestions": [
                "Тип кровли",
                "Грузоподъёмность лифтов",
            ],
            "sections": ["Кровля", "Лифты"],
        }
    )

    normalized = runtime_module._apply_estimate_assumption_policy(
        plan,
        prompt=(
            "Неизвестные исходные данные явно пометь как допущения и продолжай "
            "предварительный расчёт."
        ),
    )

    assert normalized.blocking_questions == []
    assumption_text = " ".join(normalized.assumptions)
    assert "Тип кровли" in assumption_text
    assert "Грузоподъёмность лифтов" in assumption_text


def test_first_house_request_continues_with_explicit_assumptions() -> None:
    plan = runtime_module.GeneratedEstimatePlan.model_validate(
        {
            "title": "Кирпичный дом 38 м²",
            "region": "Регион не указан",
            "assumptions": ["Площадь дома — 38 м²."],
            "blockingQuestions": ["Регион строительства", "Тип кровли"],
            "sections": ["Фундамент", "Стены", "Кровля"],
        }
    )

    normalized = runtime_module._apply_estimate_assumption_policy(
        plan,
        prompt="Хочу построить кирпичный дом 38 м²",
    )

    assert normalized.blocking_questions == []
    assert "Регион строительства" in " ".join(normalized.assumptions)


def test_explicit_no_assumptions_preserves_blocking_questions() -> None:
    plan = runtime_module.GeneratedEstimatePlan.model_validate(
        {
            "title": "Точная смета",
            "region": "Казань",
            "assumptions": ["Только подтверждённые данные."],
            "blockingQuestions": ["Тип кровли"],
            "sections": ["Кровля"],
        }
    )

    normalized = runtime_module._apply_estimate_assumption_policy(
        plan,
        prompt="Составь смету без допущений; неизвестные данные запроси.",
    )

    assert normalized.blocking_questions == ["Тип кровли"]


def test_fixture_section_transport_has_no_total_row_cap(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        runtime_module,
        "_start_tool_stage",
        lambda *_args, **_kwargs: "tool_call_test",
    )
    monkeypatch.setattr(
        runtime_module,
        "_finish_tool_stage",
        lambda *_args, **_kwargs: None,
    )
    runtime = SectionTransportFixture()
    database_path = tmp_path / "full-estimate-generation.db"
    _seed_generation_project(database_path)
    accepted = SimpleNamespace(
        tenant_id="tenant_full_estimate",
        project_id="project_full_estimate",
        thread_id="thread_full_estimate",
        run_id="run_full_estimate",
        public_run_id="run_full_estimate",
    )

    proposal = runtime_module._generate_full_estimate_proposal(
        Settings.for_testing(database_url=database_path),
        accepted,
        runtime=runtime,  # type: ignore[arg-type]
        messages=[
            {
                "role": "user",
                "content": "Составь полную смету девятиэтажного дома в Казани.",
            }
        ],
        user_id="user_full_estimate",
        credential_tenant_id="tenant_full_estimate",
        selection=AgentModelSelection(),
        cancellation_signal=None,
    )

    assert len(proposal.rows) == 1_000
    assert len(runtime.requests) == 71
    assert runtime.requests[0].execution_profile == "estimate-plan"
    assert sum(
        request.execution_profile.startswith("estimate-role:")
        for request in runtime.requests
    ) == 50
    assert sum(
        request.execution_profile.startswith("estimate-pricing:")
        for request in runtime.requests
    ) == 10
    assert sum(
        request.execution_profile.startswith("estimate-review:")
        for request in runtime.requests
    ) == 10


def test_invalid_estimate_plan_is_retried_before_generation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        runtime_module,
        "_start_tool_stage",
        lambda *_args, **_kwargs: "tool_call_test",
    )
    tool_results: list[dict[str, object]] = []
    monkeypatch.setattr(
        runtime_module,
        "_finish_tool_stage",
        lambda *_args, **kwargs: tool_results.append(dict(kwargs["result"])),
    )
    runtime = SectionTransportFixture(invalid_plan_attempts=1)
    database_path = tmp_path / "estimate-plan-retry.db"
    _seed_generation_project(database_path)
    accepted = SimpleNamespace(
        tenant_id="tenant_full_estimate",
        project_id="project_full_estimate",
        thread_id="thread_full_estimate",
        run_id="run_full_estimate",
        public_run_id="run_full_estimate",
    )

    result = runtime_module._generate_full_estimate_proposal(
        Settings.for_testing(database_url=database_path),
        accepted,
        runtime=runtime,  # type: ignore[arg-type]
        messages=[
            {
                "role": "user",
                "content": "Составь полную смету девятиэтажного дома в Казани.",
            }
        ],
        user_id="user_full_estimate",
        credential_tenant_id="tenant_full_estimate",
        selection=AgentModelSelection(),
        cancellation_signal=None,
    )

    assert len(result.rows) == 1_000
    assert runtime.plan_attempt_count == 2
    assert "Предыдущий ответ не прошёл" in runtime.requests[1].instructions
    assert {
        "status": "complete",
        "sectionCount": 10,
        "attemptCount": 2,
    } in tool_results


def test_invalid_project_case_is_repaired_before_it_is_persisted(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        runtime_module,
        "_start_tool_stage",
        lambda *_args, **_kwargs: "tool_call_test",
    )
    monkeypatch.setattr(
        runtime_module,
        "_finish_tool_stage",
        lambda *_args, **_kwargs: None,
    )
    runtime = SectionTransportFixture(invalid_project_case_attempts=1)
    database_path = tmp_path / "estimate-project-case-repair.db"
    _seed_generation_project(database_path)
    accepted = SimpleNamespace(
        tenant_id="tenant_full_estimate",
        project_id="project_full_estimate",
        thread_id="thread_full_estimate",
        run_id="run_full_estimate",
        public_run_id="run_full_estimate",
    )

    result = runtime_module._generate_full_estimate_proposal(
        Settings.for_testing(database_url=database_path),
        accepted,
        runtime=runtime,  # type: ignore[arg-type]
        messages=[
            {
                "role": "user",
                "content": "Составь полную смету девятиэтажного дома в Казани.",
            }
        ],
        user_id="user_full_estimate",
        credential_tenant_id="tenant_full_estimate",
        selection=AgentModelSelection(),
        cancellation_signal=None,
    )

    assert len(result.rows) == 1_000
    assert runtime.plan_attempt_count == 2
    assert "неподдерживаемая-единица" in runtime.requests[1].instructions
    database = connect_database(database_path)
    try:
        cases = database.execute(
            """
            SELECT status, snapshot_json
            FROM project_cases
            ORDER BY version
            """
        ).fetchall()
    finally:
        database.close()
    assert len(cases) == 2
    assert cases[-1]["status"] == "ready"
    assert (
        json.loads(cases[-1]["snapshot_json"])["variables"]["FLOOR_COUNT"]["unit"]
        == "1"
    )


def test_transient_agent_failure_retries_only_the_same_durable_task(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        runtime_module,
        "_start_tool_stage",
        lambda *_args, **_kwargs: "tool_call_test",
    )
    monkeypatch.setattr(
        runtime_module,
        "_finish_tool_stage",
        lambda *_args, **_kwargs: None,
    )
    runtime = SectionTransportFixture(transient_role_failures=1)
    database_path = tmp_path / "estimate-task-retry.db"
    _seed_generation_project(database_path)
    accepted = SimpleNamespace(
        tenant_id="tenant_full_estimate",
        project_id="project_full_estimate",
        thread_id="thread_full_estimate",
        run_id="run_full_estimate",
        public_run_id="run_full_estimate",
    )

    result = runtime_module._generate_full_estimate_proposal(
        Settings.for_testing(database_url=database_path),
        accepted,
        runtime=runtime,  # type: ignore[arg-type]
        messages=[
            {
                "role": "user",
                "content": "Составь полную смету девятиэтажного дома в Казани.",
            }
        ],
        user_id="user_full_estimate",
        credential_tenant_id="tenant_full_estimate",
        selection=AgentModelSelection(),
        cancellation_signal=None,
    )

    assert len(result.rows) == 1_000
    assert runtime.role_failure_count == 1
    assert sum(
        request.execution_profile.startswith("estimate-role:")
        for request in runtime.requests
    ) == 51
    database = connect_database(database_path)
    try:
        retried = database.execute(
            """
            SELECT id, section_revision, attempt, status
            FROM estimate_generation_tasks
            WHERE attempt > 1
            """
        ).fetchall()
        task_count = database.execute(
            "SELECT COUNT(*) FROM estimate_generation_tasks"
        ).fetchone()[0]
    finally:
        database.close()
    assert len(retried) == 1
    assert retried[0]["section_revision"] == 1
    assert retried[0]["attempt"] == 2
    assert retried[0]["status"] == "succeeded"
    assert task_count == 70


def test_exhausted_estimate_plan_retries_mark_durable_run_failed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        runtime_module,
        "_start_tool_stage",
        lambda *_args, **_kwargs: "tool_call_test",
    )
    tool_results: list[dict[str, object]] = []
    monkeypatch.setattr(
        runtime_module,
        "_finish_tool_stage",
        lambda *_args, **kwargs: tool_results.append(dict(kwargs["result"])),
    )
    runtime = SectionTransportFixture(invalid_plan_attempts=3)
    database_path = tmp_path / "estimate-plan-failed.db"
    _seed_generation_project(database_path)
    accepted = SimpleNamespace(
        tenant_id="tenant_full_estimate",
        project_id="project_full_estimate",
        thread_id="thread_full_estimate",
        run_id="run_full_estimate",
        public_run_id="run_full_estimate",
    )

    with pytest.raises(ValueError, match="not valid JSON"):
        runtime_module._generate_full_estimate_proposal(
            Settings.for_testing(database_url=database_path),
            accepted,
            runtime=runtime,  # type: ignore[arg-type]
            messages=[
                {
                    "role": "user",
                    "content": "Составь полную смету девятиэтажного дома в Казани.",
                }
            ],
            user_id="user_full_estimate",
            credential_tenant_id="tenant_full_estimate",
            selection=AgentModelSelection(),
            cancellation_signal=None,
        )

    database = connect_database(database_path)
    try:
        run = database.execute(
            """
            SELECT status, stage, quality_report_json, last_error_json
            FROM estimate_generation_runs
            """
        ).fetchone()
    finally:
        database.close()
    assert run is not None
    assert run["status"] == "failed"
    assert run["stage"] == "project_case"
    assert json.loads(run["quality_report_json"]) == {
        "attemptCount": 3,
        "errorCode": "estimate_plan_invalid",
        "stage": "project_case",
        "status": "failed",
    }
    assert json.loads(run["last_error_json"])["code"] == "estimate_plan_invalid"
    assert tool_results == [
        {
            "status": "failed",
            "errorCode": "estimate_plan_invalid",
            "attemptCount": 3,
        }
    ]
