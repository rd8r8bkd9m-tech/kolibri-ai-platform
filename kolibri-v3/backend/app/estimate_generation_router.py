"""Bounded HTTP read and control surface for durable estimate generation."""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .chat.events import SSE_HEADERS, encode_heartbeat, encode_sse
from .config import Settings
from .database import connect_database, get_database
from .estimate_generation import (
    IdempotencyConflict,
    NotFound,
    StateConflict,
    ValidationFailure,
    get_generation_run,
    get_latest_generation_run,
    get_latest_project_technology_card_revision,
    request_generation_cancel,
)
from .product_access import ConstructionEstimateAccessDependency
from .security import require_mutation_auth


router = APIRouter(prefix="/v1/projects", tags=["estimate-generation"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = ConstructionEstimateAccessDependency
MutationAuthDependency = Annotated[None, Depends(require_mutation_auth)]
IdempotencyKeyDependency = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9._~-]+$",
    ),
]

PROJECT_ID_PATTERN = r"^project_[A-Za-z0-9._~-]{8,96}$"
RUN_ID_PATTERN = r"^run_estimate_generation_[0-9a-f]{32}$"
SUMMARY_SCHEMA_VERSION = "1.0"
RECENT_ACTIVITY_LIMIT = 12
AG_UI_PROTOCOL_VERSION = "0.0.57"
ACTIVITY_TYPE = "kolibri.estimate.a2a.v1"
_TERMINAL_RUN_STATUSES = frozenset({"ready", "needs_input", "failed", "cancelled"})

_ACTIVITY_ACTORS = {
    "orchestrator": "Оркестратор",
    "technologist": "Технолог",
    "quantity_engineer": "Инженер объёмов",
    "resource_normer": "Нормировщик",
    "technical_researcher": "Исследователь",
    "procurement": "Снабженец",
    "logistics": "Логистика",
    "reviewer": "Проверяющий",
}


class CancelGenerationRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    reason: str = Field(min_length=1, max_length=1_000)


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _not_found() -> HTTPException:
    return _error(
        status.HTTP_404_NOT_FOUND,
        "estimate_generation_not_found",
        "Запуск формирования сметы не найден.",
    )


def _require_project(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
) -> None:
    if re.fullmatch(PROJECT_ID_PATTERN, project_id) is None:
        raise _not_found()
    row = database.execute(
        "SELECT 1 FROM projects WHERE tenant_id = ? AND id = ? LIMIT 1",
        (tenant_id, project_id),
    ).fetchone()
    if row is None:
        raise _not_found()


def _run_for_project(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
) -> dict[str, Any]:
    if re.fullmatch(RUN_ID_PATTERN, run_id) is None:
        raise _not_found()
    try:
        run = get_generation_run(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            include_details=False,
        )
    except NotFound as exc:
        raise _not_found() from exc
    if run.get("projectId") != project_id:
        raise _not_found()
    return run


def _status_counts(
    database: sqlite3.Connection,
    *,
    table: str,
    tenant_id: str,
    run_id: str,
) -> dict[str, object]:
    if table not in {"estimate_generation_sections", "estimate_generation_tasks"}:
        raise RuntimeError("estimate generation progress table is not allowlisted")
    rows = database.execute(
        f"""
        SELECT status, COUNT(*) AS item_count
        FROM {table}
        WHERE tenant_id = ? AND run_id = ?
        GROUP BY status
        ORDER BY status
        """,
        (tenant_id, run_id),
    ).fetchall()
    by_status = {str(row["status"]): int(row["item_count"]) for row in rows}
    return {"total": sum(by_status.values()), "byStatus": by_status}


def _bounded_last_error(value: object) -> dict[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    result: dict[str, str] = {}
    for key in ("code", "message"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            result[key] = candidate.strip()[:500]
    return result or None


def _quality_summary(value: object) -> dict[str, int] | None:
    if not isinstance(value, Mapping):
        return None
    result: dict[str, int] = {}
    for key in ("errors", "warnings"):
        candidate = value.get(key)
        if (
            isinstance(candidate, int)
            and not isinstance(candidate, bool)
            and candidate >= 0
        ):
            result[key] = candidate
    return result or None


def _json_object(value: object) -> dict[str, Any]:
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _task_activity_message(
    *,
    role: str,
    status: str,
    section: str,
    attempt: int,
    retryable: bool,
    result: Mapping[str, Any],
) -> tuple[str, str]:
    actor = _ACTIVITY_ACTORS.get(role, "Оркестратор")
    if status == "leased":
        handoff = {
            "procurement": "получил перечень ресурсов и проверяет цены, НДС и доставку",
            "reviewer": "получил техкарту и evidence для независимой проверки",
        }.get(role, "получил раздел от оркестратора и начал работу")
        return "working", f"{actor} {handoff}: «{section}» (попытка {attempt})."
    if status == "failed":
        action = "вернул задачу на повтор" if retryable else "зафиксировал блокирующую ошибку"
        return "failed", f"{actor} {action} по разделу «{section}» (попытка {attempt})."
    if status in {"cancelled", "superseded"}:
        return "failed", f"Задача роли «{actor}» по разделу «{section}» остановлена новой ревизией."

    if role == "reviewer":
        review = result.get("review")
        review_value = review if isinstance(review, Mapping) else {}
        issues = review_value.get("issues")
        issue_count = len(issues) if isinstance(issues, list) else 0
        accepted = result.get("accepted") is True or review_value.get("passed") is True
        if accepted:
            return "completed", f"Проверяющий принял раздел «{section}»; блокирующих замечаний нет."
        return (
            "revision_required",
            f"Проверяющий вернул раздел «{section}» на доработку: {issue_count} замечаний.",
        )
    if role == "procurement":
        price_section = result.get("priceSection")
        price_value = price_section if isinstance(price_section, Mapping) else {}
        candidates = price_value.get("candidates")
        count = len(candidates) if isinstance(candidates, list) else 0
        return "completed", f"Снабженец передал {count} ценовых кандидатов по разделу «{section}»."

    operations = result.get("operations")
    operation_values = operations if isinstance(operations, list) else []
    operation_count = len(operation_values)
    if role == "technologist":
        message = f"Технолог передал последовательность из {operation_count} операций по разделу «{section}»."
    elif role == "quantity_engineer":
        message = f"Инженер объёмов передал формулы для {operation_count} операций раздела «{section}»."
    elif role == "resource_normer":
        resource_count = sum(
            len(operation.get("resources", []))
            for operation in operation_values
            if isinstance(operation, Mapping) and isinstance(operation.get("resources"), list)
        )
        message = f"Нормировщик передал {resource_count} ресурсов по разделу «{section}»."
    elif role == "technical_researcher":
        source_count = sum(
            len(operation.get("technicalSources", []))
            for operation in operation_values
            if isinstance(operation, Mapping)
            and isinstance(operation.get("technicalSources"), list)
        )
        message = f"Исследователь передал {source_count} технических источников по разделу «{section}»."
    elif role == "logistics":
        message = f"Логистика передала механизацию и ограничения для {operation_count} операций раздела «{section}»."
    else:
        message = f"{actor} завершил задачу по разделу «{section}»."
    return "completed", message


def _recent_activity(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
) -> list[dict[str, object]]:
    orchestrator_row = database.execute(
        """
        SELECT id, status, payload_json, created_at
        FROM estimate_generation_checkpoints
        WHERE tenant_id = ? AND run_id = ?
          AND checkpoint_key = 'orchestrator:sections-planned'
        ORDER BY sequence DESC LIMIT 1
        """,
        (tenant_id, run_id),
    ).fetchone()
    rows = database.execute(
        """
        SELECT tasks.id, tasks.role, tasks.status, tasks.attempt,
               tasks.retryable, tasks.result_json, tasks.updated_at,
               sections.title AS section_title
        FROM estimate_generation_tasks AS tasks
        JOIN estimate_generation_sections AS sections
          ON sections.tenant_id = tasks.tenant_id
         AND sections.run_id = tasks.run_id
         AND sections.id = tasks.section_id
        WHERE tasks.tenant_id = ? AND tasks.run_id = ?
          AND tasks.status <> 'queued'
        ORDER BY tasks.updated_at DESC, tasks.id DESC
        LIMIT ?
        """,
        (tenant_id, run_id, RECENT_ACTIVITY_LIMIT),
    ).fetchall()
    activity: list[dict[str, object]] = []
    if orchestrator_row is not None and not rows:
        payload = _json_object(orchestrator_row["payload_json"])
        section_count = payload.get("sectionCount")
        task_count = payload.get("taskCount")
        activity.append(
            {
                "id": f"{orchestrator_row['id']}:{orchestrator_row['status']}",
                "actor": _ACTIVITY_ACTORS["orchestrator"],
                "role": "orchestrator",
                "section": "Вся смета",
                "status": "completed",
                "message": (
                    "Оркестратор сохранил план: "
                    f"{section_count} разделов, {task_count} назначений."
                )[:500],
                "createdAt": str(orchestrator_row["created_at"]),
            }
        )
    for row in reversed(rows):
        role = str(row["role"])
        task_status = str(row["status"])
        status, message = _task_activity_message(
            role=role,
            status=task_status,
            section=str(row["section_title"]),
            attempt=max(1, int(row["attempt"])),
            retryable=bool(row["retryable"]),
            result=_json_object(row["result_json"]),
        )
        activity.append(
            {
                "id": f"{row['id']}:{task_status}:{row['attempt']}",
                "actor": _ACTIVITY_ACTORS[role],
                "role": role,
                "section": str(row["section_title"]),
                "status": status,
                "message": message[:500],
                "createdAt": str(row["updated_at"]),
            }
        )
    activity.sort(key=lambda item: (str(item["createdAt"]), str(item["id"])))
    return activity[-RECENT_ACTIVITY_LIMIT:]


def _generation_run_summary(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run: Mapping[str, Any],
) -> dict[str, object]:
    run_id = str(run["id"])
    section_progress = _status_counts(
        database,
        table="estimate_generation_sections",
        tenant_id=tenant_id,
        run_id=run_id,
    )
    task_progress = _status_counts(
        database,
        table="estimate_generation_tasks",
        tenant_id=tenant_id,
        run_id=run_id,
    )
    return {
        "id": run_id,
        "projectId": str(run["projectId"]),
        "sourceRunId": run.get("sourceRunId"),
        "status": str(run["status"]),
        "stage": str(run["stage"]),
        "qualityStatus": str(run["qualityStatus"]),
        "quality": _quality_summary(run.get("qualityReport")),
        "progress": dict(run["progress"]),
        "sectionProgress": section_progress,
        "taskProgress": task_progress,
        "recentActivity": _recent_activity(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
        ),
        "cancelRequested": bool(run["cancelRequested"]),
        "projectCaseRef": dict(run["projectCaseRef"]),
        "result": run.get("result"),
        "lastError": _bounded_last_error(run.get("lastError")),
        "createdAt": str(run["createdAt"]),
        "updatedAt": str(run["updatedAt"]),
        "finishedAt": run.get("finishedAt"),
    }


def _summary_response(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    run: Mapping[str, Any] | None,
) -> dict[str, object]:
    return {
        "schemaVersion": SUMMARY_SCHEMA_VERSION,
        "projectId": project_id,
        "generationRun": (
            _generation_run_summary(database, tenant_id=tenant_id, run=run)
            if run is not None
            else None
        ),
    }


@router.get("/{project_id}/estimate/generation")
def latest_generation_summary(
    project_id: str,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, object]:
    _require_project(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
    )
    run = get_latest_generation_run(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
        include_details=False,
    )
    return _summary_response(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
        run=run,
    )


# Keep this static path before the dynamic run path below. The full technology
# snapshot is intentionally absent from summaries and returned only here.
@router.get("/{project_id}/estimate/generation/technology-card/latest")
def latest_technology_card_revision(
    project_id: str,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, object]:
    _require_project(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
    )
    revision = get_latest_project_technology_card_revision(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
        published_only=False,
    )
    if revision is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "technology_card_revision_not_found",
            "Технологическая карта для проекта ещё не сформирована.",
        )
    validation = revision.get("validation")
    validation_status = (
        validation.get("status") if isinstance(validation, Mapping) else None
    )
    return {
        "schemaVersion": SUMMARY_SCHEMA_VERSION,
        "projectId": project_id,
        "technologyCardRevision": {
            "id": str(revision["id"]),
            "runId": str(revision["runId"]),
            "version": int(revision["revision"]),
            "status": str(revision["status"]),
            "rulesVersion": str(revision["rulesVersion"]),
            "projectCaseRef": dict(revision["projectCaseRef"]),
            "previousRevisionId": revision.get("previousRevisionId"),
            "publishedTechnologyCardId": revision.get("publishedTechnologyCardId"),
            "snapshot": revision["snapshot"],
            "contentHash": str(revision["snapshotHash"]),
            "validationStatus": validation_status,
            "validationHash": str(revision["validationHash"]),
            "createdAt": str(revision["createdAt"]),
        },
    }


@router.get("/{project_id}/estimate/generation/{run_id}")
def generation_run_summary(
    project_id: str,
    run_id: str,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, object]:
    _require_project(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
    )
    run = _run_for_project(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
        run_id=run_id,
    )
    return _summary_response(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
        run=run,
    )


def _generation_event_cursor(request: Request) -> int:
    raw = request.headers.get("last-event-id") or request.query_params.get("after")
    if raw is None:
        return 0
    if not raw.isascii() or not raw.isdecimal() or len(raw) > 20:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "estimate_event_cursor_invalid",
            "Курсор событий сметы недействителен.",
        )
    return int(raw)


async def _stream_generation_events(
    *, settings: Settings, tenant_id: str, run_id: str, start_after: int
) -> object:
    cursor = start_after
    while True:
        database = connect_database(settings.database_url)
        try:
            rows = database.execute(
                """
                SELECT sequence, event_json
                FROM estimate_generation_events
                WHERE tenant_id = ? AND run_id = ? AND sequence > ?
                ORDER BY sequence ASC LIMIT 100
                """,
                (tenant_id, run_id, cursor),
            ).fetchall()
            run = database.execute(
                "SELECT status FROM estimate_generation_runs WHERE tenant_id = ? AND id = ?",
                (tenant_id, run_id),
            ).fetchone()
        finally:
            database.close()
        if rows:
            for row in rows:
                event = json.loads(str(row["event_json"]))
                event["sequence"] = int(row["sequence"])
                cursor = int(row["sequence"])
                yield encode_sse(event)
            if run is None or str(run["status"]) in _TERMINAL_RUN_STATUSES:
                return
            continue
        if run is None or str(run["status"]) in _TERMINAL_RUN_STATUSES:
            return
        yield encode_heartbeat()
        await asyncio.sleep(settings.product_run_poll_seconds)


@router.get("/{project_id}/estimate/generation/{run_id}/events")
def generation_events(
    project_id: str,
    run_id: str,
    request: Request,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> StreamingResponse:
    _require_project(database, tenant_id=identity.tenant_id, project_id=project_id)
    _run_for_project(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
        run_id=run_id,
    )
    settings: Settings = request.app.state.settings
    return StreamingResponse(
        _stream_generation_events(
            settings=settings,
            tenant_id=identity.tenant_id,
            run_id=run_id,
            start_after=_generation_event_cursor(request),
        ),
        media_type="text/event-stream",
        headers={**SSE_HEADERS, "X-Kolibri-Estimate-Run-Id": run_id},
    )


@router.post("/{project_id}/estimate/generation/{run_id}/cancel")
def cancel_generation_run(
    project_id: str,
    run_id: str,
    payload: CancelGenerationRequest,
    idempotency_key: IdempotencyKeyDependency,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _mutation_auth: MutationAuthDependency,
) -> dict[str, object]:
    _require_project(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
    )
    _run_for_project(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
        run_id=run_id,
    )
    try:
        run = request_generation_cancel(
            database,
            tenant_id=identity.tenant_id,
            run_id=run_id,
            idempotency_key=idempotency_key,
            reason=payload.reason,
        )
    except NotFound as exc:
        raise _not_found() from exc
    except IdempotencyConflict as exc:
        raise _error(
            status.HTTP_409_CONFLICT,
            "idempotency_conflict",
            "Этот ключ уже использован для другого запроса отмены.",
        ) from exc
    except StateConflict as exc:
        raise _error(
            status.HTTP_409_CONFLICT,
            "estimate_generation_conflict",
            "Состояние запуска изменилось. Обновите данные и повторите действие.",
        ) from exc
    except ValidationFailure as exc:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "estimate_generation_invalid",
            "Запрос управления запуском содержит недопустимые данные.",
        ) from exc
    if run.get("projectId") != project_id:
        raise _not_found()
    return _summary_response(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
        run=run,
    )
