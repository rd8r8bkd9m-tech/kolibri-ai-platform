from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.database import connect_database, initialize_database
from app.estimate_generation import (
    IdempotencyConflict,
    StateConflict,
    ValidationFailure,
    claim_generation_task,
    complete_generation_task,
    content_hash,
    create_generation_run,
    expand_technology_card,
    fail_generation_task,
    get_generation_run,
    get_latest_generation_run,
    get_latest_project_technology_card_revision,
    persist_expanded_lines,
    plan_generation_sections,
    publish_technology_card_revision,
    reconcile_expanded_estimate,
    register_generation_evidence,
    request_generation_cancel,
    resume_generation_run,
    retry_generation_section,
    save_generation_project_case,
    save_technology_card_revision,
    transition_generation_run,
    validate_project_case,
    validate_technology_card,
)


TENANT_ID = "tenant_estimate_generation"
USER_ID = "user_estimate_generation"
PROJECT_ID = "project_estimate_generation"
NOW = "2026-08-02T10:00:00Z"


def _database(tmp_path: Path, name: str = "generation.db") -> sqlite3.Connection:
    path = tmp_path / name
    initialize_database(path)
    database = connect_database(path)
    database.execute(
        """
        INSERT INTO tenants (id, name, created_at)
        VALUES (?, 'Estimate generation test', 1)
        """,
        (TENANT_ID,),
    )
    database.execute(
        """
        INSERT INTO users (
            id, tenant_id, email_normalized, email, name, role,
            preferred_agent_profile, password_hash, created_at, updated_at
        ) VALUES (?, ?, 'estimate-generation@example.com',
                  'estimate-generation@example.com', 'Estimator', 'owner',
                  'auto', 'test-only', 1, 1)
        """,
        (USER_ID, TENANT_ID),
    )
    database.execute(
        """
        INSERT INTO projects (
            tenant_id, id, created_by_user_id, title, status,
            primary_thread_id, created_at, updated_at
        ) VALUES (?, ?, ?, 'Жилой дом', 'active',
                  'thread_estimate_generation', ?, ?)
        """,
        (TENANT_ID, PROJECT_ID, USER_ID, NOW, NOW),
    )
    return database


def _analysed_project_case() -> dict[str, object]:
    return {
        "analysisStatus": "analysed",
        "region": "Республика Татарстан",
        "currency": "RUB",
        "object": {"name": "Жилой дом", "storeys": 9},
        "facts": {"source": "conversation"},
        "variables": {
            "wall_area": {
                "value": "100",
                "unit": "м²",
                "basis": "Площадь стен из проектного задания.",
            }
        },
        "assumptions": [
            {
                "text": "Работы выполняются в одну смену.",
                "basis": "Условие расчёта заказчика.",
                "impact": "Влияет на срок, но не на объём.",
            }
        ],
        "blockingQuestions": [],
        "exclusions": [],
    }


def _technology_card(evidence: dict[str, str] | None = None) -> dict[str, object]:
    price_ids = evidence or {}
    return {
        "schemaVersion": "2.0",
        "rulesVersion": "universal-test/1.0.0",
        "sections": [
            {
                "sectionKey": "finishing.walls",
                "title": "Отделка стен",
                "wbsPath": "03/03.01/finishing.walls",
                "ordinal": 10,
            }
        ],
        "operations": [
            {
                "operationId": "wall_painting",
                "sectionKey": "finishing.walls",
                "title": "Окраска стен",
                "method": "Подготовить основание и нанести два слоя краски.",
                "unit": "м²",
                "quantityFormula": {"op": "variable", "name": "wall_area"},
                "quantityBasis": "Площадь стен 100 м² из ProjectCase.",
                "predecessors": [],
                "qualityControls": ["Равномерность покрытия"],
                "resources": [
                    {
                        "resourceId": "painting_labor",
                        "kind": "work",
                        "title": "Труд маляра",
                        "unit": "чел.-ч",
                        "quantityFormula": {
                            "op": "multiply",
                            "items": [
                                {"op": "variable", "name": "wall_area"},
                                {"op": "constant", "value": "0.2", "unit": "чел.-ч/м²"},
                            ],
                        },
                        "quantityBasis": "100 м² × 0,2 чел.-ч/м².",
                        "priceEvidenceId": price_ids.get("work"),
                    },
                    {
                        "resourceId": "painting_material",
                        "kind": "material",
                        "title": "Краска интерьерная",
                        "unit": "кг",
                        "quantityFormula": {
                            "op": "multiply",
                            "items": [
                                {"op": "variable", "name": "wall_area"},
                                {"op": "constant", "value": "0.25", "unit": "кг/м²"},
                            ],
                        },
                        "quantityBasis": "100 м² × 0,25 кг/м² с учётом двух слоёв.",
                        "specification": {"finish": "матовая"},
                        "priceEvidenceId": price_ids.get("material"),
                    },
                    {
                        "resourceId": "painting_machine",
                        "kind": "equipment",
                        "title": "Окрасочный аппарат",
                        "unit": "маш.-ч",
                        "quantityFormula": {
                            "op": "multiply",
                            "items": [
                                {"op": "variable", "name": "wall_area"},
                                {
                                    "op": "constant",
                                    "value": "0.01",
                                    "unit": "маш.-ч/м²",
                                },
                            ],
                        },
                        "quantityBasis": "100 м² × 0,01 маш.-ч/м².",
                        "priceEvidenceId": price_ids.get("equipment"),
                    },
                    {
                        "resourceId": "painting_delivery",
                        "kind": "service",
                        "title": "Доставка материалов",
                        "unit": "рейс",
                        "quantityFormula": {"op": "constant", "value": "1", "unit": "рейс"},
                        "quantityBasis": "Один согласованный рейс.",
                        "priceEvidenceId": price_ids.get("service"),
                    },
                    {
                        "resourceId": "painting_overhead",
                        "kind": "overhead",
                        "title": "Накладные расходы",
                        "ratePercent": "10",
                        "baseKinds": ["work", "equipment"],
                        "calculationBasis": "10% от труда и эксплуатации оборудования.",
                    },
                ],
            }
        ],
        "assumptions": [],
        "exclusions": [],
    }


def _create_analysed_run(database: sqlite3.Connection, suffix: str = "base") -> dict[str, object]:
    return create_generation_run(
        database,
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        created_by_user_id=USER_ID,
        project_case=_analysed_project_case(),
        idempotency_key=f"create-generation-{suffix}-0001",
        now=NOW,
    )


def _register_price(
    database: sqlite3.Connection,
    *,
    run_id: str,
    key: str,
    unit: str,
    price: str,
) -> dict[str, object]:
    return register_generation_evidence(
        database,
        tenant_id=TENANT_ID,
        run_id=run_id,
        evidence={
            "evidenceKey": key,
            "kind": "price",
            "sourceType": "supplier_offer",
            "confidenceStatus": "source_backed",
            "confidence": "0.8",
            "sourceTitle": "Коммерческое предложение поставщика",
            "sourceUri": f"https://supplier.example/{key}",
            "sourceReference": f"offer-{key}",
            "region": "Республика Татарстан",
            "unit": unit,
            "unitPrice": price,
            "currency": "RUB",
            "taxTreatment": "included",
            "deliveryTreatment": "included",
            "observedAt": NOW,
            "validUntil": "2026-09-01",
            "snapshot": {"offer": key, "price": price},
        },
        idempotency_key=f"register-evidence-{key}-0001",
        section_key="finishing.walls",
        now=NOW,
    )


def test_project_case_seed_is_durable_then_analysed_version_is_appended(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    try:
        seed = {"analysisStatus": "pending", "conversationSnapshot": {"text": "Дом 9 этажей"}}
        run = create_generation_run(
            database,
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            created_by_user_id=USER_ID,
            project_case=seed,
            idempotency_key="create-seed-generation-0001",
            now=NOW,
        )
        assert run["status"] == "queued"
        assert run["stage"] == "project_case"
        replay = create_generation_run(
            database,
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            created_by_user_id=USER_ID,
            project_case=seed,
            idempotency_key="create-seed-generation-0001",
            now=NOW,
        )
        assert replay["id"] == run["id"]
        with pytest.raises(IdempotencyConflict):
            create_generation_run(
                database,
                tenant_id=TENANT_ID,
                project_id=PROJECT_ID,
                created_by_user_id=USER_ID,
                project_case={**seed, "conversationSnapshot": {"text": "Другое"}},
                idempotency_key="create-seed-generation-0001",
                now=NOW,
            )
        analysed = save_generation_project_case(
            database,
            tenant_id=TENANT_ID,
            run_id=str(run["id"]),
            project_case=_analysed_project_case(),
            idempotency_key="save-analysed-case-0001",
            now="2026-08-02T10:01:00Z",
        )
        assert analysed["version"] == 2
        assert analysed["status"] == "ready"
        loaded = get_generation_run(database, tenant_id=TENANT_ID, run_id=str(run["id"]))
        assert loaded["status"] == "running"
        assert loaded["stage"] == "decomposition"
        assert loaded["projectCase"]["snapshot"]["variables"]["wall_area"]["unit"] == "м²"
        statuses = [
            tuple(row)
            for row in database.execute(
                "SELECT version, status FROM project_cases ORDER BY version"
            )
        ]
        assert statuses == [(1, "superseded"), (2, "ready")]
    finally:
        database.close()


def test_tasks_checkpoint_retry_resume_and_cancel_are_recoverable(tmp_path: Path) -> None:
    database = _database(tmp_path, "tasks.db")
    try:
        run = _create_analysed_run(database, "tasks")
        sections = plan_generation_sections(
            database,
            tenant_id=TENANT_ID,
            run_id=str(run["id"]),
            sections=[
                {
                    "sectionKey": "finishing.walls",
                    "title": "Отделка стен",
                    "wbsPath": "03/03.01",
                    "ordinal": 1,
                }
            ],
            roles=("technologist", "reviewer"),
            idempotency_key="plan-sections-tasks-0001",
            now=NOW,
        )
        assert len(sections[0]["tasks"]) == 2
        unreviewed_revision = save_technology_card_revision(
            database,
            tenant_id=TENANT_ID,
            run_id=str(run["id"]),
            technology_card=_technology_card(),
            idempotency_key="save-unreviewed-card-0001",
            status="accepted",
            now=NOW,
        )
        with pytest.raises(StateConflict, match="every section review"):
            publish_technology_card_revision(
                database,
                tenant_id=TENANT_ID,
                run_id=str(run["id"]),
                revision_id=str(unreviewed_revision["id"]),
                created_by_user_id=USER_ID,
                idempotency_key="publish-unreviewed-card-0001",
                now=NOW,
            )
        first = claim_generation_task(
            database,
            tenant_id=TENANT_ID,
            run_id=str(run["id"]),
            worker_id="worker-a",
            lease_seconds=60,
            now=NOW,
        )
        assert first is not None and first["role"] == "technologist"
        assert (
            claim_generation_task(
                database,
                tenant_id=TENANT_ID,
                run_id=str(run["id"]),
                worker_id="worker-review",
                roles=("reviewer",),
                now=NOW,
            )
            is None
        )
        resumed = resume_generation_run(
            database,
            tenant_id=TENANT_ID,
            run_id=str(run["id"]),
            now="2026-08-02T10:02:00Z",
        )
        assert resumed["status"] == "running"
        reclaimed = claim_generation_task(
            database,
            tenant_id=TENANT_ID,
            run_id=str(run["id"]),
            worker_id="worker-b",
            now="2026-08-02T10:02:01Z",
        )
        assert reclaimed is not None
        assert reclaimed["id"] == first["id"]
        assert reclaimed["attempt"] == 2
        failed = fail_generation_task(
            database,
            tenant_id=TENANT_ID,
            task_id=str(reclaimed["id"]),
            lease_token=str(reclaimed["lease"]["token"]),
            error={"code": "provider_timeout"},
            checkpoint_key="checkpoint-failed-technologist-0001",
            now="2026-08-02T10:02:02Z",
        )
        assert failed["status"] == "failed"
        retried = retry_generation_section(
            database,
            tenant_id=TENANT_ID,
            run_id=str(run["id"]),
            section_key="finishing.walls",
            roles=("technologist", "reviewer"),
            idempotency_key="retry-finishing-walls-0001",
            reason="Повторить только повреждённый раздел.",
            now="2026-08-02T10:03:00Z",
        )
        assert {task["sectionRevision"] for task in retried} == {2}
        retry_replay = retry_generation_section(
            database,
            tenant_id=TENANT_ID,
            run_id=str(run["id"]),
            section_key="finishing.walls",
            roles=("technologist", "reviewer"),
            idempotency_key="retry-finishing-walls-0001",
            reason="Повторить только повреждённый раздел.",
            now="2026-08-02T10:03:00Z",
        )
        assert [task["id"] for task in retry_replay] == [task["id"] for task in retried]
        claimed = claim_generation_task(
            database,
            tenant_id=TENANT_ID,
            run_id=str(run["id"]),
            worker_id="worker-c",
            now="2026-08-02T10:03:01Z",
        )
        assert claimed is not None
        cancelled = request_generation_cancel(
            database,
            tenant_id=TENANT_ID,
            run_id=str(run["id"]),
            idempotency_key="cancel-generation-tasks-0001",
            reason="Пользователь отменил расчёт.",
            now="2026-08-02T10:03:02Z",
        )
        assert cancelled["status"] == "cancelled"
        assert cancelled["cancelRequested"]
        assert (
            claim_generation_task(
                database,
                tenant_id=TENANT_ID,
                run_id=str(run["id"]),
                worker_id="worker-d",
                now="2026-08-02T10:03:03Z",
            )
            is None
        )
        assert (
            resume_generation_run(
                database,
                tenant_id=TENANT_ID,
                run_id=str(run["id"]),
                now="2026-08-02T10:03:04Z",
            )["status"]
            == "cancelled"
        )
    finally:
        database.close()


def test_failed_retryable_task_reuses_identity_until_attempt_limit(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path, "task-attempts.db")
    try:
        run = _create_analysed_run(database, "task-attempts")
        plan_generation_sections(
            database,
            tenant_id=TENANT_ID,
            run_id=str(run["id"]),
            sections=[
                {
                    "sectionKey": "structure.frame",
                    "title": "Монолитный каркас",
                    "wbsPath": "02/structure.frame",
                    "ordinal": 1,
                }
            ],
            roles=("technologist",),
            idempotency_key="plan-task-attempts-0001",
            now=NOW,
        )

        task_ids: list[str] = []
        for attempt in range(1, 4):
            task = claim_generation_task(
                database,
                tenant_id=TENANT_ID,
                run_id=str(run["id"]),
                worker_id=f"worker-{attempt}",
                max_attempts=3,
                now=f"2026-08-02T10:0{attempt}:00Z",
            )
            assert task is not None
            task_ids.append(str(task["id"]))
            assert task["attempt"] == attempt
            failed = fail_generation_task(
                database,
                tenant_id=TENANT_ID,
                task_id=str(task["id"]),
                lease_token=str(task["lease"]["token"]),
                error={
                    "code": "future_runtime_transport_failed",
                    "category": "unavailable",
                    "retryable": True,
                    "attempt": attempt,
                    "maxAttempts": 3,
                },
                checkpoint_key=f"task-attempt-{attempt}-failed",
                retryable=True,
                now=f"2026-08-02T10:0{attempt}:01Z",
            )
            assert failed["status"] == "failed"

        assert len(set(task_ids)) == 1
        assert (
            claim_generation_task(
                database,
                tenant_id=TENANT_ID,
                run_id=str(run["id"]),
                worker_id="worker-exhausted",
                max_attempts=3,
                now="2026-08-02T10:04:00Z",
            )
            is None
        )
        stored = database.execute(
            """
            SELECT section_revision, attempt, status, retryable
            FROM estimate_generation_tasks
            """
        ).fetchone()
        assert tuple(stored) == (1, 3, "failed", 1)
    finally:
        database.close()


def test_nonretryable_task_failure_is_not_reclaimed(tmp_path: Path) -> None:
    database = _database(tmp_path, "task-nonretryable.db")
    try:
        run = _create_analysed_run(database, "task-nonretryable")
        plan_generation_sections(
            database,
            tenant_id=TENANT_ID,
            run_id=str(run["id"]),
            sections=[
                {
                    "sectionKey": "structure.frame",
                    "title": "Монолитный каркас",
                    "wbsPath": "02/structure.frame",
                    "ordinal": 1,
                }
            ],
            roles=("technologist",),
            idempotency_key="plan-task-nonretryable-0001",
            now=NOW,
        )
        task = claim_generation_task(
            database,
            tenant_id=TENANT_ID,
            run_id=str(run["id"]),
            worker_id="worker-auth",
            now="2026-08-02T10:01:00Z",
        )
        assert task is not None
        fail_generation_task(
            database,
            tenant_id=TENANT_ID,
            task_id=str(task["id"]),
            lease_token=str(task["lease"]["token"]),
            error={"code": "runtime_auth_required", "category": "authentication"},
            checkpoint_key="task-auth-failed",
            retryable=False,
            now="2026-08-02T10:01:01Z",
        )

        assert (
            claim_generation_task(
                database,
                tenant_id=TENANT_ID,
                run_id=str(run["id"]),
                worker_id="worker-auth-retry",
                now="2026-08-02T10:02:00Z",
            )
            is None
        )
        durable = get_generation_run(
            database,
            tenant_id=TENANT_ID,
            run_id=str(run["id"]),
            include_details=False,
        )
        assert durable["status"] == "needs_input"
    finally:
        database.close()


def test_evidence_card_expansion_reconciliation_lineage_and_ready_transition(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path, "expansion.db")
    try:
        run = _create_analysed_run(database, "expansion")
        run_id = str(run["id"])
        plan_generation_sections(
            database,
            tenant_id=TENANT_ID,
            run_id=run_id,
            sections=[
                {
                    "sectionKey": "finishing.walls",
                    "title": "Отделка стен",
                    "wbsPath": "03/03.01",
                    "ordinal": 1,
                }
            ],
            roles=("technologist", "reviewer"),
            idempotency_key="plan-expansion-sections-0001",
            now=NOW,
        )
        technologist = claim_generation_task(
            database,
            tenant_id=TENANT_ID,
            run_id=run_id,
            worker_id="technology-worker",
            now=NOW,
        )
        assert technologist is not None
        complete_generation_task(
            database,
            tenant_id=TENANT_ID,
            task_id=str(technologist["id"]),
            lease_token=str(technologist["lease"]["token"]),
            result={"operations": ["wall_painting"]},
            checkpoint_key="checkpoint-technology-complete-0001",
            now="2026-08-02T10:00:10Z",
        )
        reviewer = claim_generation_task(
            database,
            tenant_id=TENANT_ID,
            run_id=run_id,
            worker_id="review-worker",
            now="2026-08-02T10:00:11Z",
        )
        assert reviewer is not None and reviewer["role"] == "reviewer"
        completed_reviewer = complete_generation_task(
            database,
            tenant_id=TENANT_ID,
            task_id=str(reviewer["id"]),
            lease_token=str(reviewer["lease"]["token"]),
            result={"qualityStatus": "passed", "issues": []},
            checkpoint_key="checkpoint-review-complete-0001",
            now="2026-08-02T10:00:12Z",
        )
        assert completed_reviewer["status"] == "succeeded"
        price_ids: dict[str, str] = {}
        for key, unit, price in (
            ("work", "чел.-ч", "800.00"),
            ("material", "кг", "250.00"),
            ("equipment", "маш.-ч", "1500.00"),
            ("service", "рейс", "5000.00"),
        ):
            price_ids[key] = str(
                _register_price(database, run_id=run_id, key=key, unit=unit, price=price)["id"]
            )
        with pytest.raises(ValidationFailure):
            register_generation_evidence(
                database,
                tenant_id=TENANT_ID,
                run_id=run_id,
                evidence={
                    "evidenceKey": "dishonest-ai",
                    "kind": "technical",
                    "sourceType": "ai_candidate",
                    "confidenceStatus": "verified",
                    "confidence": "1",
                    "sourceTitle": "AI",
                    "sourceReference": "memory",
                    "snapshot": {"claim": "unverified"},
                    "verifiedByUserId": USER_ID,
                    "verification": {"method": "none"},
                },
                idempotency_key="dishonest-ai-evidence-0001",
                now=NOW,
            )
        with pytest.raises(ValidationFailure, match="expired"):
            register_generation_evidence(
                database,
                tenant_id=TENANT_ID,
                run_id=run_id,
                evidence={
                    "evidenceKey": "expired-offer",
                    "kind": "price",
                    "sourceType": "supplier_offer",
                    "confidenceStatus": "source_backed",
                    "confidence": "0.8",
                    "sourceTitle": "Старое предложение",
                    "sourceReference": "expired-offer",
                    "region": "Республика Татарстан",
                    "unit": "кг",
                    "unitPrice": "10.00",
                    "currency": "RUB",
                    "observedAt": "2025-01-01T00:00:00Z",
                    "validUntil": "2025-02-01",
                    "snapshot": {"offer": "expired"},
                },
                idempotency_key="expired-price-evidence-0001",
                now=NOW,
            )
        card = _technology_card(price_ids)
        assert validate_project_case(_analysed_project_case()).passed
        card_validation = validate_technology_card(_analysed_project_case(), card)
        assert card_validation.passed, card_validation.as_dict()
        revision = save_technology_card_revision(
            database,
            tenant_id=TENANT_ID,
            run_id=run_id,
            technology_card=card,
            idempotency_key="save-card-revision-0001",
            status="accepted",
            now="2026-08-02T10:01:00Z",
        )
        published = publish_technology_card_revision(
            database,
            tenant_id=TENANT_ID,
            run_id=run_id,
            revision_id=str(revision["id"]),
            created_by_user_id=USER_ID,
            idempotency_key="publish-card-revision-0001",
            now="2026-08-02T10:01:01Z",
        )
        assert published["publishedTechnologyCardId"]
        assert (
            get_latest_project_technology_card_revision(
                database,
                tenant_id=TENANT_ID,
                project_id=PROJECT_ID,
                published_only=True,
            )["id"]
            == revision["id"]
        )
        evidence_list = get_generation_run(database, tenant_id=TENANT_ID, run_id=run_id)["evidence"]
        evidence_by_id = {str(item["id"]): item for item in evidence_list}
        expansion = expand_technology_card(
            _analysed_project_case(),
            card,
            revision_id=str(revision["id"]),
            evidence_by_id=evidence_by_id,
        )
        assert len(expansion.rows) == 5
        assert {row["kind"] for row in expansion.rows} == {
            "work",
            "material",
            "equipment",
            "service",
            "overhead",
        }
        assert all(row["operation_id"] == "wall_painting" for row in expansion.rows)
        assert all(row["technology_card_version"] == revision["id"] for row in expansion.rows)
        assert next(row for row in expansion.rows if row["kind"] == "work")["quantity"] == "20"
        reconciliation = reconcile_expanded_estimate(
            _analysed_project_case(), card, expansion.rows, evidence_by_id=evidence_by_id
        )
        assert reconciliation.passed, reconciliation.as_dict()
        checkpoints = get_generation_run(database, tenant_id=TENANT_ID, run_id=run_id)[
            "checkpoints"
        ]
        review_checkpoint = next(
            item
            for item in checkpoints
            if item["checkpointKey"] == "checkpoint-review-complete-0001"
        )
        lineage = persist_expanded_lines(
            database,
            tenant_id=TENANT_ID,
            run_id=run_id,
            revision_id=str(revision["id"]),
            rows=expansion.rows,
            idempotency_key="persist-expanded-lines-0001",
            producing_task_id=str(reviewer["id"]),
            producing_checkpoint_id=str(review_checkpoint["id"]),
            now="2026-08-02T10:01:02Z",
        )
        assert lineage["rowCount"] == 5
        replay = persist_expanded_lines(
            database,
            tenant_id=TENANT_ID,
            run_id=run_id,
            revision_id=str(revision["id"]),
            rows=expansion.rows,
            idempotency_key="persist-expanded-lines-0001",
            producing_task_id=str(reviewer["id"]),
            producing_checkpoint_id=str(review_checkpoint["id"]),
            now="2026-08-02T10:01:02Z",
        )
        assert replay == lineage
        assert (
            database.execute("SELECT COUNT(*) FROM estimate_generation_lineage").fetchone()[0] == 5
        )

        document_id = "document_estimate_generation"
        document = {"rows": list(expansion.rows), "totals": dict(expansion.totals)}
        database.execute(
            """
            INSERT INTO document_slots (
                tenant_id, id, project_id, slot_type, version, status,
                content_json, created_at, updated_at
            ) VALUES (?, ?, ?, 'estimate', 1, 'ready', ?, ?, ?)
            """,
            (TENANT_ID, document_id, PROJECT_ID, "{}", NOW, NOW),
        )
        database.execute(
            """
            INSERT INTO estimate_versions (
                tenant_id, id, project_id, document_id, version, status,
                content_json, content_hash, origin_type, origin_run_id,
                created_by_user_id, created_at, lifecycle_status
            ) VALUES (?, 'estimate_version_generation', ?, ?, 1, 'ready',
                      ?, ?, 'engine_calculation', NULL, ?, ?, 'ready')
            """,
            (
                TENANT_ID,
                PROJECT_ID,
                document_id,
                "{}",
                content_hash(document),
                USER_ID,
                NOW,
            ),
        )
        ready = transition_generation_run(
            database,
            tenant_id=TENANT_ID,
            run_id=run_id,
            expected_statuses=("running", "review"),
            target_status="ready",
            target_stage="complete",
            quality_report=reconciliation.as_dict(),
            result_document_id=document_id,
            result_version=1,
            now="2026-08-02T10:01:03Z",
        )
        assert ready["status"] == "ready"
        assert ready["qualityStatus"] == "passed"
        assert ready["result"] == {"documentId": document_id, "estimateVersion": 1}
        latest = get_latest_generation_run(database, tenant_id=TENANT_ID, project_id=PROJECT_ID)
        assert latest is not None and latest["id"] == run_id
    finally:
        database.close()


def test_validation_rejects_cycles_unexplained_duplicates_and_unsupported_dimensions() -> None:
    project_case = _analysed_project_case()
    card = _technology_card()
    operations = card["operations"]
    assert isinstance(operations, list)
    operation = operations[0]
    assert isinstance(operation, dict)
    operation["predecessors"] = ["wall_painting"]
    resources = operation["resources"]
    assert isinstance(resources, list)
    duplicate = dict(resources[0])
    duplicate["resourceId"] = "painting_labor_duplicate"
    resources.append(duplicate)
    report = validate_technology_card(project_case, card)
    codes = {issue.code for issue in report.issues}
    assert not report.passed
    assert "predecessor_self_reference" in codes
    assert "operation_cycle" in codes
    assert "resource_duplicate_unexplained" in codes


@pytest.mark.parametrize("unit", ("этаж", "этажа", "этажей", "floor", "floors"))
def test_project_case_accepts_floor_count_as_dimensionless(unit: str) -> None:
    project_case = _analysed_project_case()
    variables = project_case["variables"]
    assert isinstance(variables, dict)
    variables["floor_count"] = {
        "value": "9",
        "unit": unit,
        "basis": "Этажность подтверждена заданием пользователя.",
    }

    report = validate_project_case(project_case)

    assert report.passed, report.as_dict()


@pytest.mark.parametrize(
    "unit",
    (
        "чел.-ч",
        "маш.-ч",
        "п.м.",
        "упак.",
        "рулон",
        "м²",
        "м³",
        "л",
        "кг",
        "т",
        "шт.",
        "компл.",
        "м²/смену",
    ),
)
def test_universal_card_accepts_common_construction_units(unit: str) -> None:
    card = {
        "schemaVersion": "2.0",
        "rulesVersion": "unit-vocabulary/1.0.0",
        "sections": [
            {
                "sectionKey": "unit.test",
                "title": "Проверка единицы",
                "wbsPath": "unit.test",
                "ordinal": 1,
            }
        ],
        "operations": [
            {
                "operationId": "unit_operation",
                "sectionKey": "unit.test",
                "title": "Операция",
                "method": "Контрольная технологическая операция.",
                "unit": unit,
                "quantityFormula": {"op": "constant", "value": "1", "unit": unit},
                "quantityBasis": "Одна единица по проектному заданию.",
                "predecessors": [],
                "qualityControls": ["Контроль количества"],
                "resources": [
                    {
                        "resourceId": "unit_work",
                        "kind": "work",
                        "title": "Контрольная работа",
                        "unit": unit,
                        "quantityFormula": {"op": "constant", "value": "1", "unit": unit},
                        "quantityBasis": "Одна единица по проектному заданию.",
                    }
                ],
            }
        ],
    }
    report = validate_technology_card(_analysed_project_case(), card)
    assert report.passed, report.as_dict()
