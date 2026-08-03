from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.database import connect_database
from app.estimate_generation import (
    append_generation_checkpoint,
    canonical_json,
    content_hash,
    create_generation_run,
    plan_generation_sections,
    save_technology_card_revision,
)
from app.main import create_app


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"
TASK_BLOB = "task_result_must_not_leak_" * 4_000
CHECKPOINT_BLOB = "checkpoint-payload-must-not-leak-" * 4_000


def _register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/v1/auth/register",
        headers=ORIGIN,
        json={
            "email": email,
            "name": email.split("@", 1)[0],
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201
    return response.json()["user"]


def _grant_estimate_access(
    database_path: Path,
    *,
    tenant_id: str,
    user_id: str,
) -> None:
    database = sqlite3.connect(database_path)
    try:
        database.execute("PRAGMA foreign_keys = ON")
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
            (tenant_id, user_id),
        )
        database.commit()
    finally:
        database.close()


def _seed_project(
    database_path: Path,
    *,
    tenant_id: str,
    user_id: str,
    suffix: str,
) -> str:
    _grant_estimate_access(
        database_path,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    project_id = f"project_generation_{suffix}"
    now = "2026-08-02T00:00:00Z"
    database = sqlite3.connect(database_path)
    try:
        database.execute("PRAGMA foreign_keys = ON")
        database.execute(
            """
            INSERT INTO projects (
                tenant_id, id, created_by_user_id, title, status,
                primary_thread_id, created_at, updated_at
            ) VALUES (?, ?, ?, 'Промышленная смета', 'active', ?, ?, ?)
            """,
            (
                tenant_id,
                project_id,
                user_id,
                f"thread_generation_{suffix}",
                now,
                now,
            ),
        )
        database.commit()
    finally:
        database.close()
    return project_id


def _project_case() -> dict[str, object]:
    return {
        "schemaId": "kolibri.project_case",
        "schemaVersion": "2.0",
        "analysisStatus": "analysed",
        "region": "Москва",
        "currency": "RUB",
        "variables": {
            "wall_area": {
                "value": "100",
                "unit": "m2",
                "basis": "Подтверждено ведомостью объёмов работ.",
            }
        },
        "assumptions": [],
        "blockingQuestions": [],
    }


def _technology_card() -> dict[str, object]:
    return {
        "schemaId": "kolibri.technology_card_revision",
        "schemaVersion": "1.0",
        "rulesVersion": "generation-api-test-v1",
        "marker": "technology-snapshot-explicit-only",
        "sections": [
            {
                "sectionKey": "walls",
                "title": "Стены",
                "wbsPath": "01/Стены",
            }
        ],
        "operations": [
            {
                "operationId": "op_surface_preparation",
                "sectionKey": "walls",
                "title": "Подготовка поверхности",
                "method": "Очистить и обеспылить основание перед нанесением состава.",
                "unit": "m2",
                "quantityFormula": {"op": "variable", "name": "wall_area"},
                "quantityBasis": "Площадь стены по ProjectCase.",
                "predecessors": [],
                "qualityControls": ["Основание чистое и сухое."],
                "resources": [
                    {
                        "resourceId": "res_surface_preparation_work",
                        "kind": "work",
                        "title": "Подготовка поверхности стен",
                        "unit": "m2",
                        "quantityFormula": {
                            "op": "variable",
                            "name": "wall_area",
                        },
                        "quantityBasis": "Площадь стены по ProjectCase.",
                    }
                ],
            }
        ],
    }


def _seed_generation_run(
    database_path: Path,
    *,
    tenant_id: str,
    project_id: str,
    user_id: str,
    with_large_details: bool = False,
) -> str:
    database = connect_database(database_path)
    try:
        run = create_generation_run(
            database,
            tenant_id=tenant_id,
            project_id=project_id,
            created_by_user_id=user_id,
            project_case=_project_case(),
            idempotency_key=f"generation-create-{project_id}",
            now="2026-08-02T00:01:00Z",
        )
        run_id = str(run["id"])
        plan_generation_sections(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            sections=[
                {
                    "sectionKey": "walls",
                    "title": "Стены",
                    "wbsPath": "01/Стены",
                    "ordinal": 0,
                }
            ],
            roles=("technologist", "reviewer"),
            idempotency_key=f"generation-sections-{project_id}",
            now="2026-08-02T00:02:00Z",
        )

        save_technology_card_revision(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            technology_card=_technology_card(),
            idempotency_key=f"generation-technology-{project_id}",
            status="accepted",
            created_by_user_id=user_id,
            now="2026-08-02T00:03:00Z",
        )

        if with_large_details:
            task = database.execute(
                """
                SELECT id FROM estimate_generation_tasks
                WHERE tenant_id = ? AND run_id = ?
                ORDER BY id LIMIT 1
                """,
                (tenant_id, run_id),
            ).fetchone()
            assert task is not None
            task_result = {"blob": TASK_BLOB}
            database.execute(
                """
                UPDATE estimate_generation_tasks
                SET result_json = ?, result_hash = ?
                WHERE tenant_id = ? AND id = ?
                """,
                (
                    canonical_json(task_result),
                    content_hash(task_result),
                    tenant_id,
                    task["id"],
                ),
            )
            append_generation_checkpoint(
                database,
                tenant_id=tenant_id,
                run_id=run_id,
                stage="technology",
                status="completed",
                payload={"blob": CHECKPOINT_BLOB},
                checkpoint_key="generation-api-large-checkpoint",
                now="2026-08-02T00:04:00Z",
            )
        return run_id
    finally:
        database.close()


def _mutation_headers(client: TestClient, key: str) -> dict[str, str]:
    csrf = client.cookies.get("kolibri_v3_csrf")
    assert csrf
    return {
        **ORIGIN,
        "X-CSRF-Token": csrf,
        "Idempotency-Key": key,
    }


def test_generation_summary_is_bounded_and_card_snapshot_is_explicit(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "estimate-generation-summary.db"
    settings = Settings.for_testing(database_url=database_path)
    with TestClient(create_app(settings)) as client:
        user = _register(client, "generation-summary@example.com")
        project_id = _seed_project(
            database_path,
            tenant_id=user["tenantId"],
            user_id=user["id"],
            suffix="summary_01",
        )

        empty = client.get(f"/v1/projects/{project_id}/estimate/generation")
        assert empty.status_code == 200
        assert empty.json()["generationRun"] is None

        run_id = _seed_generation_run(
            database_path,
            tenant_id=user["tenantId"],
            project_id=project_id,
            user_id=user["id"],
            with_large_details=True,
        )

        latest = client.get(f"/v1/projects/{project_id}/estimate/generation")
        assert latest.status_code == 200
        value = latest.json()
        run = value["generationRun"]
        assert run["id"] == run_id
        assert run["sectionProgress"] == {
            "total": 1,
            "byStatus": {"active": 1},
        }
        assert run["taskProgress"] == {
            "total": 2,
            "byStatus": {"queued": 2},
        }
        assert len(run["recentActivity"]) == 1
        assert run["recentActivity"][0]["role"] == "orchestrator"
        assert run["recentActivity"][0]["actor"] == "Оркестратор"
        for forbidden in (
            "sections",
            "tasks",
            "checkpoints",
            "evidence",
            "latestTechnologyRevision",
        ):
            assert forbidden not in run
        assert TASK_BLOB.encode() not in latest.content
        assert CHECKPOINT_BLOB.encode() not in latest.content
        assert b"technology-snapshot-explicit-only" not in latest.content
        assert len(latest.content) < 10_000

        selected = client.get(
            f"/v1/projects/{project_id}/estimate/generation/{run_id}"
        )
        assert selected.status_code == 200
        assert selected.json()["generationRun"] == run

        card = client.get(
            f"/v1/projects/{project_id}/estimate/generation/technology-card/latest"
        )
        assert card.status_code == 200
        revision = card.json()["technologyCardRevision"]
        assert revision["runId"] == run_id
        assert revision["version"] == 1
        assert revision["snapshot"]["marker"] == (
            "technology-snapshot-explicit-only"
        )
        assert revision["contentHash"].startswith("sha256:")
        assert revision["validationStatus"] == "passed"


def test_generation_summary_exposes_real_bounded_a2a_activity(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "estimate-generation-activity.db"
    settings = Settings.for_testing(database_url=database_path)
    with TestClient(create_app(settings)) as client:
        user = _register(client, "generation-activity@example.com")
        project_id = _seed_project(
            database_path,
            tenant_id=user["tenantId"],
            user_id=user["id"],
            suffix="activity_01",
        )
        run_id = _seed_generation_run(
            database_path,
            tenant_id=user["tenantId"],
            project_id=project_id,
            user_id=user["id"],
        )
        database = connect_database(database_path)
        try:
            tasks = database.execute(
                """
                SELECT id, role FROM estimate_generation_tasks
                WHERE tenant_id = ? AND run_id = ? ORDER BY role
                """,
                (user["tenantId"], run_id),
            ).fetchall()
            by_role = {str(task["role"]): str(task["id"]) for task in tasks}
            database.execute(
                """
                UPDATE estimate_generation_tasks
                SET status = 'leased', attempt = 1,
                    lease_owner = 'activity-worker', lease_token = 'activity-token',
                    lease_until = '2026-08-02T01:00:00Z',
                    updated_at = '2026-08-02T00:04:00Z'
                WHERE tenant_id = ? AND id = ?
                """,
                (user["tenantId"], by_role["technologist"]),
            )
            review_result = {
                "accepted": False,
                "review": {
                    "passed": False,
                    "issues": [
                        {"code": "missing-source"},
                        {"code": "unit-check"},
                    ],
                },
            }
            database.execute(
                """
                UPDATE estimate_generation_tasks
                SET status = 'succeeded', attempt = 1,
                    result_json = ?, result_hash = ?, completed_at = ?, updated_at = ?
                WHERE tenant_id = ? AND id = ?
                """,
                (
                    canonical_json(review_result),
                    content_hash(review_result),
                    "2026-08-02T00:05:00Z",
                    "2026-08-02T00:05:00Z",
                    user["tenantId"],
                    by_role["reviewer"],
                ),
            )
            database.commit()
        finally:
            database.close()

        response = client.get(
            f"/v1/projects/{project_id}/estimate/generation/{run_id}"
        )
        assert response.status_code == 200
        activity = response.json()["generationRun"]["recentActivity"]
        assert len(activity) == 2
        assert [item["role"] for item in activity] == [
            "technologist",
            "reviewer",
        ]
        assert activity[0]["status"] == "working"
        assert activity[1]["status"] == "revision_required"
        assert "2 замечаний" in activity[1]["message"]
        assert all(
            set(item) == {
                "id",
                "actor",
                "role",
                "section",
                "status",
                "message",
                "createdAt",
            }
            for item in activity
        )
        assert len(response.content) < 10_000


def test_generation_cancel_requires_mutation_auth_and_is_idempotent(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "estimate-generation-cancel.db"
    settings = Settings.for_testing(database_url=database_path)
    with TestClient(create_app(settings)) as client:
        user = _register(client, "generation-cancel@example.com")
        project_id = _seed_project(
            database_path,
            tenant_id=user["tenantId"],
            user_id=user["id"],
            suffix="cancel_01",
        )
        run_id = _seed_generation_run(
            database_path,
            tenant_id=user["tenantId"],
            project_id=project_id,
            user_id=user["id"],
        )
        url = f"/v1/projects/{project_id}/estimate/generation/{run_id}/cancel"
        idempotency_key = "generation-cancel-api-key-0001"

        unauthenticated_mutation = client.post(
            url,
            headers={"Idempotency-Key": idempotency_key},
            json={"reason": "Пользователь остановил расчёт."},
        )
        assert unauthenticated_mutation.status_code == 403

        before = client.get(
            f"/v1/projects/{project_id}/estimate/generation/{run_id}"
        )
        assert before.status_code == 200
        assert before.json()["generationRun"]["status"] == "review"

        cancelled = client.post(
            url,
            headers=_mutation_headers(client, idempotency_key),
            json={"reason": "Пользователь остановил расчёт."},
        )
        assert cancelled.status_code == 200
        run = cancelled.json()["generationRun"]
        assert run["status"] == "cancelled"
        assert run["cancelRequested"] is True
        assert run["sectionProgress"]["byStatus"] == {"cancelled": 1}
        assert run["taskProgress"]["byStatus"] == {"cancelled": 2}

        replay = client.post(
            url,
            headers=_mutation_headers(client, idempotency_key),
            json={"reason": "Пользователь остановил расчёт."},
        )
        assert replay.status_code == 200
        assert replay.json() == cancelled.json()

        conflict = client.post(
            url,
            headers=_mutation_headers(client, idempotency_key),
            json={"reason": "Другая причина остановки."},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "idempotency_conflict"


def test_generation_api_hides_cross_tenant_project_and_requires_entitlement(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "estimate-generation-tenant.db"
    settings = Settings.for_testing(database_url=database_path)
    with TestClient(create_app(settings)) as owner_client:
        owner = _register(owner_client, "generation-owner@example.com")
        project_id = _seed_project(
            database_path,
            tenant_id=owner["tenantId"],
            user_id=owner["id"],
            suffix="tenant_01",
        )
        run_id = _seed_generation_run(
            database_path,
            tenant_id=owner["tenantId"],
            project_id=project_id,
            user_id=owner["id"],
        )

    with TestClient(create_app(settings)) as outsider_client:
        outsider = _register(outsider_client, "generation-outsider@example.com")
        _grant_estimate_access(
            database_path,
            tenant_id=outsider["tenantId"],
            user_id=outsider["id"],
        )
        latest = outsider_client.get(
            f"/v1/projects/{project_id}/estimate/generation"
        )
        assert latest.status_code == 404
        assert latest.json()["code"] == "estimate_generation_not_found"

        selected = outsider_client.get(
            f"/v1/projects/{project_id}/estimate/generation/{run_id}"
        )
        assert selected.status_code == 404

        card = outsider_client.get(
            f"/v1/projects/{project_id}/estimate/generation/technology-card/latest"
        )
        assert card.status_code == 404

        cancellation = outsider_client.post(
            f"/v1/projects/{project_id}/estimate/generation/{run_id}/cancel",
            headers=_mutation_headers(
                outsider_client,
                "generation-cross-tenant-cancel-0001",
            ),
            json={"reason": "Попытка отмены чужого запуска."},
        )
        assert cancellation.status_code == 404

    database = connect_database(database_path)
    try:
        row = database.execute(
            """
            SELECT status, cancel_requested
            FROM estimate_generation_runs
            WHERE tenant_id = ? AND id = ?
            """,
            (owner["tenantId"], run_id),
        ).fetchone()
        assert row is not None
        assert row["status"] == "review"
        assert row["cancel_requested"] == 0
    finally:
        database.close()

    with TestClient(create_app(settings)) as unentitled_client:
        _register(unentitled_client, "generation-unentitled@example.com")
        denied = unentitled_client.get(
            f"/v1/projects/{project_id}/estimate/generation"
        )
        assert denied.status_code == 403
        assert denied.json()["code"] == "product_entitlement_required"
