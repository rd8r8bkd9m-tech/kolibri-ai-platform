"""Owner-only, preview-first storage maintenance for Home and Primary."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from .database import get_database, transaction
from .identity import require_owner
from .schemas import UserSession
from .security import require_mutation_auth
from .storage_admin_contracts import (
    StorageAuditView,
    StorageCleanupCategory,
    StorageNodeId,
    StorageNodeView,
    StorageOperationExecute,
    StorageOperationKind,
    StorageOperationReconcile,
    StorageOperationView,
    StoragePreviewCreate,
    StoragePreviewView,
    StorageSnapshotView,
)
from .storage_node_executor import (
    CONFIGURED_HOME_CAPACITY_SEGMENTS,
    REQUIRED_STORAGE_GUARDS,
    StorageExecuteCommand,
    StorageExecutorError,
    StorageExecutorPreview,
    StorageExecutorResult,
    StorageExecutorUnavailable,
    StorageNodeExecutor,
    StorageNodeInventory,
    StoragePreviewCommand,
    StorageStatusCommand,
)


router = APIRouter(
    prefix="/v1/platform-admin/storage",
    tags=["platform-admin", "storage"],
)
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
OwnerDependency = Annotated[UserSession, Depends(require_owner)]
MutationAuthDependency = Annotated[None, Depends(require_mutation_auth)]
IdempotencyDependency = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$",
    ),
]

_NODE_NAMES: dict[StorageNodeId, Literal["Home", "Primary"]] = {
    "home": "Home",
    "primary": "Primary",
}
_ORDINARY_CATEGORIES = frozenset(
    {"build", "cache", "log", "stopped-container"}
)
_PREVIEW_TTL_SECONDS = 15 * 60
_PROJECT_RETENTION_SECONDS = 7 * 24 * 60 * 60
_RECENT_AUTH_SECONDS = 5 * 60
_MAX_BYTES = 2**63 - 1
_MAX_ITEMS = 1_000_000_000
_SAFE_OPAQUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")
_SAFE_GENERATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SAFE_ERROR = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")
_SAFE_PROJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{2,159}$")
_SAFE_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _request_hash(payload: object) -> str:
    return _digest(_canonical_json(payload))


def _now(database: sqlite3.Connection) -> int:
    return int(database.execute("SELECT unixepoch()").fetchone()[0])


def _executor(request: Request) -> StorageNodeExecutor:
    executor = getattr(
        getattr(request.app, "state", None),
        "storage_node_executor",
        None,
    )
    if executor is None:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "storage_node_executor_unavailable",
            "Для узлов не настроен безопасный исполнитель очистки.",
        )
    return executor


def _require_storage_authority(
    database: sqlite3.Connection,
    *,
    actor: UserSession,
) -> int:
    authority_epoch = actor.platform_authority_epoch
    if (
        not actor.is_platform_owner
        or authority_epoch is None
        or "platform.storage.manage" not in actor.platform_capabilities
    ):
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "platform_storage_authority_required",
            "Требуются полномочия владельца на управление хранилищем.",
        )
    row = database.execute(
        """
        SELECT 1
        FROM platform_authority_grants AS authority
        WHERE authority.authority_id = 'platform_owner'
          AND authority.user_id = ?
          AND authority.tenant_id = ?
          AND authority.active = 1
          AND authority.authority_epoch = ?
          AND EXISTS (
              SELECT 1
              FROM json_each(authority.capabilities_json)
              WHERE value = 'platform.storage.manage'
          )
        LIMIT 1
        """,
        (actor.user_id, actor.tenant_id, authority_epoch),
    ).fetchone()
    if row is None:
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "platform_storage_authority_required",
            "Требуются актуальные полномочия владельца на хранилище.",
        )
    return int(authority_epoch)


def _require_recent_auth(actor: UserSession) -> None:
    if (
        not actor.session_id
        or actor.authenticated_at < int(time.time()) - _RECENT_AUTH_SECONDS
    ):
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "storage_reauthentication_required",
            "Войдите снова перед выполнением очистки.",
        )


def _safe_executor_error(error: StorageExecutorError) -> HTTPException:
    if isinstance(error, StorageExecutorUnavailable):
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            error.code,
            error.message,
        )
    code = (
        error.code
        if _SAFE_ERROR.fullmatch(error.code)
        else "storage_node_executor_rejected"
    )
    return _error(
        status.HTTP_409_CONFLICT,
        code,
        "Исполнитель отклонил операцию. Обновите данные и повторите preview.",
    )


def _safe_error_code(error: BaseException) -> str:
    if isinstance(error, StorageExecutorError) and _SAFE_ERROR.fullmatch(
        error.code
    ):
        return error.code
    return "storage_node_executor_failed"


def _bounded_integer(value: object, *, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > maximum
    ):
        raise ValueError("executor returned an invalid integer")
    return value


def _validate_guards(
    scopes: object,
    *,
    protected_item_count: object,
) -> list[str]:
    if (
        not isinstance(scopes, tuple)
        or len(scopes) != len(REQUIRED_STORAGE_GUARDS)
        or len(set(scopes)) != len(scopes)
        or set(scopes) != set(REQUIRED_STORAGE_GUARDS)
        or protected_item_count != 0
    ):
        raise ValueError("executor did not attest all storage guards")
    return list(REQUIRED_STORAGE_GUARDS)


def _safe_display_name(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.strip()) > 120
        or "/" in value
        or "\\" in value
        or "://" in value
        or value.startswith("~")
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("executor returned an unsafe display name")
    return value.strip()


def _capacity_segments(
    segments: object,
    *,
    node_id: StorageNodeId,
) -> list[dict[str, Any]]:
    if not isinstance(segments, tuple):
        raise ValueError("executor returned invalid capacity segments")
    if node_id == "primary":
        if segments:
            raise ValueError("Primary returned unsupported capacity segments")
        return []
    if (
        len(segments) != 2
        or {segment.kind for segment in segments}
        != {"root-lv", "vg-unallocated"}
    ):
        raise ValueError("Home capacity topology is incomplete")
    values: list[dict[str, Any]] = []
    for segment in segments:
        display_size = _safe_display_name(segment.display_size)
        values.append(
            {
                "kind": segment.kind,
                "displayName": _safe_display_name(segment.display_name),
                "displaySize": display_size,
                "capacityBytes": _bounded_integer(
                    segment.capacity_bytes,
                    maximum=_MAX_BYTES,
                ),
                "readOnly": True,
            }
        )
    return values


def _configured_capacity_segments(
    node_id: StorageNodeId,
) -> list[dict[str, Any]]:
    if node_id != "home":
        return []
    return [
        {
            "kind": segment.kind,
            "displayName": segment.display_name,
            "displaySize": segment.display_size,
            "capacityBytes": segment.capacity_bytes,
            "readOnly": True,
        }
        for segment in CONFIGURED_HOME_CAPACITY_SEGMENTS
    ]


def _validate_inventory(
    inventory: StorageNodeInventory,
    *,
    node_id: StorageNodeId,
) -> dict[str, Any]:
    if not isinstance(inventory, StorageNodeInventory):
        raise ValueError("executor returned an invalid inventory")
    if inventory.node_id != node_id:
        raise ValueError("executor returned inventory for another node")
    if not isinstance(inventory.execute_enabled, bool):
        raise ValueError("executor returned invalid execution availability")
    capacity = _bounded_integer(inventory.capacity_bytes, maximum=_MAX_BYTES)
    used = _bounded_integer(inventory.used_bytes, maximum=_MAX_BYTES)
    free = _bounded_integer(inventory.free_bytes, maximum=_MAX_BYTES)
    scanned_at = _bounded_integer(inventory.scanned_at, maximum=_MAX_BYTES)
    if used > capacity or free > capacity or used + free > capacity:
        raise ValueError("executor returned inconsistent capacity")
    if (
        not isinstance(inventory.generation, str)
        or _SAFE_GENERATION.fullmatch(inventory.generation) is None
        or not isinstance(inventory.policy_digest, str)
        or _SAFE_DIGEST.fullmatch(inventory.policy_digest) is None
    ):
        raise ValueError("executor returned invalid inventory identity")
    blocked_item_count = _bounded_integer(
        inventory.blocked_item_count,
        maximum=_MAX_ITEMS,
    )
    protected_scopes = _validate_guards(
        inventory.guarded_scopes,
        protected_item_count=0,
    )
    capacity_segments = _capacity_segments(
        inventory.capacity_segments,
        node_id=node_id,
    )

    categories: list[dict[str, Any]] = []
    seen_categories: set[str] = set()
    if len(inventory.categories) > 5:
        raise ValueError("executor returned too many categories")
    for item in inventory.categories:
        if (
            item.category
            not in {
                "build",
                "cache",
                "log",
                "stopped-container",
                "project-quarantine",
            }
            or item.category in seen_categories
        ):
            raise ValueError("executor returned an invalid category")
        seen_categories.add(item.category)
        categories.append(
            {
                "category": item.category,
                "reclaimableBytes": _bounded_integer(
                    item.reclaimable_bytes,
                    maximum=_MAX_BYTES,
                ),
                "itemCount": _bounded_integer(
                    item.item_count,
                    maximum=_MAX_ITEMS,
                ),
                "oldestItemAt": (
                    None
                    if item.oldest_item_at is None
                    else _bounded_integer(
                        item.oldest_item_at,
                        maximum=_MAX_BYTES,
                    )
                ),
            }
        )

    if len(inventory.project_candidates) > 100:
        raise ValueError("executor returned too many project candidates")
    projects: list[dict[str, Any]] = []
    seen_projects: set[str] = set()
    for project in inventory.project_candidates:
        if (
            not isinstance(project.project_id, str)
            or _SAFE_PROJECT.fullmatch(project.project_id) is None
            or project.project_id in seen_projects
        ):
            raise ValueError("executor returned an invalid project reference")
        seen_projects.add(project.project_id)
        projects.append(
            {
                "projectId": project.project_id,
                "displayName": _safe_display_name(project.display_name),
                "sizeBytes": _bounded_integer(
                    project.size_bytes,
                    maximum=_MAX_BYTES,
                ),
                "lastModifiedAt": _bounded_integer(
                    project.last_modified_at,
                    maximum=_MAX_BYTES,
                ),
            }
        )
    if len(inventory.quarantines) > 200:
        raise ValueError("executor returned too many quarantines")
    seen_quarantines: set[str] = set()
    for quarantine in inventory.quarantines:
        if (
            not isinstance(quarantine.quarantine_id, str)
            or re.fullmatch(
                r"sqn_[0-9a-f]{32}",
                quarantine.quarantine_id,
            )
            is None
            or quarantine.quarantine_id in seen_quarantines
            or not isinstance(quarantine.project_id, str)
            or _SAFE_PROJECT.fullmatch(quarantine.project_id) is None
            or quarantine.status not in {"retained", "restored", "purged"}
        ):
            raise ValueError("executor returned an invalid quarantine")
        seen_quarantines.add(quarantine.quarantine_id)
        _bounded_integer(quarantine.size_bytes, maximum=_MAX_BYTES)
        quarantined_at = _bounded_integer(
            quarantine.quarantined_at,
            maximum=_MAX_BYTES,
        )
        purge_eligible_at = _bounded_integer(
            quarantine.purge_eligible_at,
            maximum=_MAX_BYTES,
        )
        if purge_eligible_at < quarantined_at:
            raise ValueError("executor returned invalid quarantine retention")
    return {
        "id": node_id,
        "displayName": _NODE_NAMES[node_id],
        "executorStatus": "ready",
        "executeEnabled": inventory.execute_enabled,
        "errorCode": None,
        "capacityBytes": capacity,
        "usedBytes": used,
        "freeBytes": free,
        "scannedAt": scanned_at,
        "generation": inventory.generation,
        "policyDigest": inventory.policy_digest,
        "blockedItemCount": blocked_item_count,
        "capacitySource": "live-executor",
        "capacityObservedAt": scanned_at,
        "categories": categories,
        "capacitySegments": capacity_segments,
        "projectCandidates": projects,
        "protectedScopes": protected_scopes,
    }


def _validate_preview(
    preview: StorageExecutorPreview,
    *,
    operation_kind: StorageOperationKind,
    now: int,
) -> dict[str, Any]:
    if not isinstance(preview, StorageExecutorPreview):
        raise ValueError("executor returned an invalid preview")
    if (
        not isinstance(preview.executor_preview_ref, str)
        or _SAFE_OPAQUE.fullmatch(preview.executor_preview_ref) is None
        or not isinstance(preview.node_generation, str)
        or _SAFE_GENERATION.fullmatch(preview.node_generation) is None
    ):
        raise ValueError("executor returned an unsafe opaque reference")
    candidate_count = _bounded_integer(
        preview.candidate_count,
        maximum=_MAX_ITEMS,
    )
    reclaimable_bytes = _bounded_integer(
        preview.reclaimable_bytes,
        maximum=_MAX_BYTES,
    )
    if (
        operation_kind in {"quarantine", "restore", "purge"}
        and candidate_count != 1
    ):
        raise ValueError("project operations require exactly one candidate")
    expires_at = _bounded_integer(preview.expires_at, maximum=_MAX_BYTES)
    if (
        preview.confirmation != _confirmation(operation_kind)
        or not isinstance(preview.replayed, bool)
        or expires_at < now
        or expires_at > now + _PREVIEW_TTL_SECONDS
    ):
        raise ValueError("executor returned invalid preview metadata")
    protected_scopes = _validate_guards(
        preview.guarded_scopes,
        protected_item_count=preview.protected_item_count,
    )
    return {
        "executorPreviewRef": preview.executor_preview_ref,
        "nodeGeneration": preview.node_generation,
        "candidateCount": candidate_count,
        "reclaimableBytes": reclaimable_bytes,
        "protectedItemCount": 0,
        "protectedScopes": protected_scopes,
        "expiresAt": expires_at,
    }


def _validate_result(
    result: StorageExecutorResult,
    *,
    operation_id: str,
    executor_preview_ref: str,
    expected_quarantine_id: str | None,
    operation_kind: StorageOperationKind,
    preview_count: int,
    preview_bytes: int,
    now: int,
) -> dict[str, Any]:
    if (
        not isinstance(result, StorageExecutorResult)
        or result.operation_id != operation_id
        or result.executor_preview_ref != executor_preview_ref
        or result.status not in {"applying", "succeeded", "failed"}
        or result.quarantine_id != expected_quarantine_id
        or not isinstance(result.replayed, bool)
    ):
        raise ValueError("executor returned an invalid result")
    affected = _bounded_integer(
        result.affected_item_count,
        maximum=_MAX_ITEMS,
    )
    reclaimed = _bounded_integer(
        result.reclaimed_bytes,
        maximum=_MAX_BYTES,
    )
    if affected > preview_count or reclaimed > preview_bytes:
        raise ValueError("executor result exceeds the approved preview")
    if result.status == "succeeded":
        if (
            operation_kind in {"quarantine", "restore", "purge"}
            and affected != 1
        ):
            raise ValueError("project operation result is inconsistent")
        if operation_kind in {"quarantine", "restore"} and reclaimed != 0:
            raise ValueError("project move must not claim reclaimed storage")
    elif affected != 0 or reclaimed != 0:
        raise ValueError("non-terminal result claimed mutation totals")
    if (
        not isinstance(result.node_generation, str)
        or _SAFE_GENERATION.fullmatch(result.node_generation) is None
    ):
        raise ValueError("executor returned an invalid generation")
    protected_scopes = _validate_guards(
        result.guarded_scopes,
        protected_item_count=result.protected_item_count,
    )
    created_at = _bounded_integer(result.created_at, maximum=_MAX_BYTES)
    completed_at = (
        None
        if result.completed_at is None
        else _bounded_integer(result.completed_at, maximum=_MAX_BYTES)
    )
    if created_at > now + _RECENT_AUTH_SECONDS:
        raise ValueError("executor returned a future operation timestamp")
    error_code = result.error_code
    if error_code is not None and (
        not isinstance(error_code, str)
        or _SAFE_ERROR.fullmatch(error_code) is None
    ):
        raise ValueError("executor returned an unsafe error code")
    if result.status == "applying":
        if completed_at is not None:
            raise ValueError("applying operation is already completed")
    elif result.status == "succeeded":
        if (
            completed_at is None
            or completed_at < created_at
            or error_code is not None
        ):
            raise ValueError("succeeded operation metadata is invalid")
    elif (
        completed_at is None
        or completed_at < created_at
        or error_code is None
    ):
        raise ValueError("failed operation metadata is invalid")
    return {
        "status": result.status,
        "affectedItemCount": affected,
        "reclaimedBytes": reclaimed,
        "protectedScopes": protected_scopes,
        "errorCode": error_code,
        "completedAt": completed_at,
    }


def _confirmation(operation_kind: str) -> str:
    return {
        "cleanup": "CLEANUP",
        "quarantine": "QUARANTINE",
        "restore": "RESTORE",
        "purge": "PURGE",
    }[operation_kind]


def _project_is_authoritative(
    database: sqlite3.Connection,
    *,
    project_id: str,
) -> bool:
    return (
        database.execute(
            "SELECT 1 FROM projects WHERE id = ? LIMIT 1",
            (project_id,),
        ).fetchone()
        is not None
    )


def _ensure_quarantine_project_allowed(
    database: sqlite3.Connection,
    *,
    node_id: str,
    project_id: str,
) -> None:
    if _project_is_authoritative(database, project_id=project_id):
        raise _error(
            status.HTTP_409_CONFLICT,
            "authoritative_project_protected",
            "Проект из рабочей базы защищён от файловой очистки.",
        )
    retained = database.execute(
        """
        SELECT 1
        FROM storage_project_quarantines
        WHERE node_id = ? AND project_id = ? AND status = 'retained'
        LIMIT 1
        """,
        (node_id, project_id),
    ).fetchone()
    if retained is not None:
        raise _error(
            status.HTTP_409_CONFLICT,
            "project_already_quarantined",
            "Проект уже находится в карантине.",
        )


def _require_purge_target(
    database: sqlite3.Connection,
    *,
    node_id: str,
    quarantine_id: str,
    now: int,
) -> sqlite3.Row:
    row = database.execute(
        """
        SELECT *
        FROM storage_project_quarantines
        WHERE id = ? AND node_id = ?
        LIMIT 1
        """,
        (quarantine_id, node_id),
    ).fetchone()
    if row is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "quarantine_not_found",
            "Запись карантина не найдена на выбранном узле.",
        )
    if str(row["status"]) != "retained":
        raise _error(
            status.HTTP_409_CONFLICT,
            "quarantine_already_purged",
            "Карантин уже очищен.",
        )
    if int(row["purge_eligible_at"]) > now:
        raise _error(
            status.HTTP_409_CONFLICT,
            "quarantine_retention_active",
            "Срок безопасного хранения карантина ещё не истёк.",
        )
    return row


def _require_restore_target(
    database: sqlite3.Connection,
    *,
    node_id: str,
    quarantine_id: str,
) -> sqlite3.Row:
    row = database.execute(
        """
        SELECT *
        FROM storage_project_quarantines
        WHERE id = ? AND node_id = ?
        LIMIT 1
        """,
        (quarantine_id, node_id),
    ).fetchone()
    if row is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "quarantine_not_found",
            "Запись карантина не найдена на выбранном узле.",
        )
    if str(row["status"]) != "retained":
        raise _error(
            status.HTTP_409_CONFLICT,
            "quarantine_not_retained",
            "Восстановить можно только удерживаемый карантин.",
        )
    if _project_is_authoritative(
        database,
        project_id=str(row["project_id"]),
    ):
        raise _error(
            status.HTTP_409_CONFLICT,
            "authoritative_project_protected",
            "Рабочий проект с таким ID уже существует и защищён.",
        )
    return row


def _preview_row(
    database: sqlite3.Connection,
    *,
    preview_id: str,
    actor: UserSession,
) -> sqlite3.Row | None:
    return database.execute(
        """
        SELECT *
        FROM storage_admin_previews
        WHERE id = ? AND actor_user_id = ? AND actor_tenant_id = ?
        LIMIT 1
        """,
        (preview_id, actor.user_id, actor.tenant_id),
    ).fetchone()


def _preview_projection(
    row: sqlite3.Row,
    *,
    replayed: bool = False,
) -> dict[str, Any]:
    scopes = json.loads(str(row["protected_scopes_json"]))
    if scopes != list(REQUIRED_STORAGE_GUARDS):
        raise RuntimeError("persisted storage preview guards are invalid")
    return {
        "id": str(row["id"]),
        "nodeId": str(row["node_id"]),
        "category": str(row["category"]),
        "operationKind": str(row["operation_kind"]),
        "projectId": row["project_id"],
        "quarantineId": row["quarantine_id"],
        "candidateCount": int(row["candidate_count"]),
        "reclaimableBytes": int(row["reclaimable_bytes"]),
        "protectedItemCount": int(row["protected_item_count"]),
        "protectedScopes": scopes,
        "confirmation": _confirmation(str(row["operation_kind"])),
        "expiresAt": int(row["expires_at"]),
        "createdAt": int(row["created_at"]),
        "replayed": replayed,
    }


def _operation_row(
    database: sqlite3.Connection,
    *,
    operation_id: str,
) -> sqlite3.Row:
    row = database.execute(
        """
        SELECT
            operation.*,
            preview.node_id,
            preview.category,
            preview.operation_kind,
            preview.project_id,
            preview.quarantine_id AS preview_quarantine_id,
            preview.executor_preview_ref,
            preview.node_generation,
            preview.candidate_count,
            preview.reclaimable_bytes
        FROM storage_admin_operations AS operation
        JOIN storage_admin_previews AS preview
          ON preview.id = operation.preview_id
        WHERE operation.id = ?
        LIMIT 1
        """,
        (operation_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("persisted storage operation is missing")
    return row


def _operation_projection(
    row: sqlite3.Row,
    *,
    replayed: bool = False,
    reconciled: bool = False,
) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "previewId": str(row["preview_id"]),
        "nodeId": str(row["node_id"]),
        "category": str(row["category"]),
        "operationKind": str(row["operation_kind"]),
        "status": str(row["status"]),
        "affectedItemCount": int(row["affected_item_count"]),
        "reclaimedBytes": int(row["reclaimed_bytes"]),
        "quarantineId": row["quarantine_id"],
        "errorCode": row["error_code"],
        "createdAt": int(row["created_at"]),
        "completedAt": (
            None if row["completed_at"] is None else int(row["completed_at"])
        ),
        "replayed": replayed,
        "reconciled": reconciled,
    }


def _quarantine_projection(
    row: sqlite3.Row,
    *,
    now: int,
) -> dict[str, Any]:
    persisted = str(row["status"])
    public_status = (
        persisted
        if persisted in {"restored", "purged"}
        else (
            "purge-eligible"
            if int(row["purge_eligible_at"]) <= now
            else "retained"
        )
    )
    return {
        "id": str(row["id"]),
        "nodeId": str(row["node_id"]),
        "projectId": str(row["project_id"]),
        "status": public_status,
        "sizeBytes": int(row["size_bytes"]),
        "quarantinedAt": int(row["quarantined_at"]),
        "purgeEligibleAt": int(row["purge_eligible_at"]),
        "purgedAt": (
            None if row["purged_at"] is None else int(row["purged_at"])
        ),
        "restoredAt": (
            None if row["restored_at"] is None else int(row["restored_at"])
        ),
    }


def _audit_projection(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "action": str(row["action"]),
        "nodeId": str(row["node_id"]),
        "category": str(row["category"]),
        "operationKind": str(row["operation_kind"]),
        "targetRef": str(row["target_ref"]),
        "previewId": str(row["preview_id"]),
        "operationId": row["operation_id"],
        "createdAt": int(row["created_at"]),
    }


def _record_audit(
    database: sqlite3.Connection,
    *,
    actor: UserSession,
    authority_epoch: int,
    action: Literal[
        "storage.preview.created",
        "storage.operation.succeeded",
        "storage.operation.failed",
    ],
    node_id: str,
    category: str,
    operation_kind: str,
    target_ref: str,
    preview_id: str,
    operation_id: str | None,
    details: object,
) -> None:
    database.execute(
        """
        INSERT INTO storage_admin_audit_events (
            id, actor_user_id, actor_tenant_id, authority_epoch,
            action, node_id, category, operation_kind,
            target_ref, preview_id, operation_id, details_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, unixepoch())
        """,
        (
            f"saudit_{uuid.uuid4().hex}",
            actor.user_id,
            actor.tenant_id,
            authority_epoch,
            action,
            node_id,
            category,
            operation_kind,
            target_ref,
            preview_id,
            operation_id,
            _canonical_json(details),
        ),
    )


def _audit_target_ref(
    *,
    category: str,
    operation_kind: str,
    project_id: object,
    quarantine_id: object,
) -> str:
    if operation_kind == "quarantine":
        return str(project_id)
    if operation_kind in {"restore", "purge"}:
        return str(quarantine_id)
    return category


@router.get("", response_model=StorageSnapshotView)
def get_storage_snapshot(
    request: Request,
    actor: OwnerDependency,
    database: DatabaseDependency,
) -> dict[str, Any]:
    _require_storage_authority(database, actor=actor)
    executor = _executor(request)
    now = _now(database)
    quarantine_rows = database.execute(
        """
        SELECT *
        FROM storage_project_quarantines
        ORDER BY quarantined_at DESC, rowid DESC
        LIMIT 200
        """
    ).fetchall()
    quarantines_by_node: dict[str, list[dict[str, Any]]] = {
        "home": [],
        "primary": [],
    }
    for row in quarantine_rows:
        quarantines_by_node[str(row["node_id"])].append(
            _quarantine_projection(row, now=now)
        )

    nodes: list[dict[str, Any]] = []
    for node_id in ("home", "primary"):
        typed_node_id: StorageNodeId = node_id
        try:
            inventory = _validate_inventory(
                executor.inventory(typed_node_id),
                node_id=typed_node_id,
            )
            inventory["projectCandidates"] = [
                project
                for project in inventory["projectCandidates"]
                if not _project_is_authoritative(
                    database,
                    project_id=str(project["projectId"]),
                )
            ]
            inventory["quarantines"] = quarantines_by_node[node_id]
            nodes.append(inventory)
        except StorageExecutorUnavailable as error:
            nodes.append(
                {
                    "id": node_id,
                    "displayName": _NODE_NAMES[typed_node_id],
                    "executorStatus": "unavailable",
                    "executeEnabled": False,
                    "errorCode": error.code,
                    "capacityBytes": None,
                    "usedBytes": None,
                    "freeBytes": None,
                    "scannedAt": None,
                    "generation": None,
                    "policyDigest": None,
                    "blockedItemCount": 0,
                    "capacitySource": "configured-record",
                    "capacityObservedAt": None,
                    "categories": [],
                    "capacitySegments": _configured_capacity_segments(
                        typed_node_id
                    ),
                    "projectCandidates": [],
                    "quarantines": quarantines_by_node[node_id],
                    "protectedScopes": list(REQUIRED_STORAGE_GUARDS),
                }
            )
        except (StorageExecutorError, ValueError):
            nodes.append(
                {
                    "id": node_id,
                    "displayName": _NODE_NAMES[typed_node_id],
                    "executorStatus": "error",
                    "executeEnabled": False,
                    "errorCode": "storage_node_inventory_invalid",
                    "capacityBytes": None,
                    "usedBytes": None,
                    "freeBytes": None,
                    "scannedAt": None,
                    "generation": None,
                    "policyDigest": None,
                    "blockedItemCount": 0,
                    "capacitySource": "configured-record",
                    "capacityObservedAt": None,
                    "categories": [],
                    "capacitySegments": _configured_capacity_segments(
                        typed_node_id
                    ),
                    "projectCandidates": [],
                    "quarantines": quarantines_by_node[node_id],
                    "protectedScopes": list(REQUIRED_STORAGE_GUARDS),
                }
            )
        except Exception:
            nodes.append(
                {
                    "id": node_id,
                    "displayName": _NODE_NAMES[typed_node_id],
                    "executorStatus": "error",
                    "executeEnabled": False,
                    "errorCode": "storage_node_inventory_failed",
                    "capacityBytes": None,
                    "usedBytes": None,
                    "freeBytes": None,
                    "scannedAt": None,
                    "generation": None,
                    "policyDigest": None,
                    "blockedItemCount": 0,
                    "capacitySource": "configured-record",
                    "capacityObservedAt": None,
                    "categories": [],
                    "capacitySegments": _configured_capacity_segments(
                        typed_node_id
                    ),
                    "projectCandidates": [],
                    "quarantines": quarantines_by_node[node_id],
                    "protectedScopes": list(REQUIRED_STORAGE_GUARDS),
                }
            )

    recent_rows = database.execute(
        """
        SELECT
            operation.*,
            preview.node_id,
            preview.category,
            preview.operation_kind
        FROM storage_admin_operations AS operation
        JOIN storage_admin_previews AS preview
          ON preview.id = operation.preview_id
        ORDER BY operation.created_at DESC, operation.rowid DESC
        LIMIT 20
        """
    ).fetchall()
    audit_rows = database.execute(
        """
        SELECT *
        FROM storage_admin_audit_events
        ORDER BY created_at DESC, rowid DESC
        LIMIT 20
        """
    ).fetchall()
    return {
        "nodes": nodes,
        "recentOperations": [
            _operation_projection(row) for row in recent_rows
        ],
        "audit": [_audit_projection(row) for row in audit_rows],
    }


@router.post(
    "/previews",
    response_model=StoragePreviewView,
    status_code=status.HTTP_201_CREATED,
)
def create_storage_preview(
    payload: StoragePreviewCreate,
    request: Request,
    actor: OwnerDependency,
    database: DatabaseDependency,
    idempotency_key: IdempotencyDependency,
    _mutation_auth: MutationAuthDependency,
) -> dict[str, Any]:
    authority_epoch = _require_storage_authority(database, actor=actor)
    request_payload = payload.model_dump(mode="json", by_alias=True)
    request_digest = _request_hash(request_payload)
    key_digest = _digest(idempotency_key)
    existing = database.execute(
        """
        SELECT *
        FROM storage_admin_previews
        WHERE actor_user_id = ?
          AND actor_tenant_id = ?
          AND idempotency_key_hash = ?
        LIMIT 1
        """,
        (actor.user_id, actor.tenant_id, key_digest),
    ).fetchone()
    if existing is not None:
        if str(existing["request_hash"]) != request_digest:
            raise _error(
                status.HTTP_409_CONFLICT,
                "storage_idempotency_conflict",
                "Idempotency-Key уже использован для другого preview.",
            )
        return _preview_projection(existing, replayed=True)

    now = _now(database)
    if payload.operation_kind == "quarantine":
        assert payload.project_id is not None
        _ensure_quarantine_project_allowed(
            database,
            node_id=payload.node_id,
            project_id=payload.project_id,
        )
    elif payload.operation_kind == "restore":
        assert payload.quarantine_id is not None
        _require_restore_target(
            database,
            node_id=payload.node_id,
            quarantine_id=payload.quarantine_id,
        )
    elif payload.operation_kind == "purge":
        assert payload.quarantine_id is not None
        _require_purge_target(
            database,
            node_id=payload.node_id,
            quarantine_id=payload.quarantine_id,
            now=now,
        )

    command = StoragePreviewCommand(
        node_id=payload.node_id,
        category=payload.category,
        operation_kind=payload.operation_kind,
        project_id=payload.project_id,
        quarantine_id=payload.quarantine_id,
        guarded_scopes=REQUIRED_STORAGE_GUARDS,
    )
    executor = _executor(request)
    try:
        live_node = _validate_inventory(
            executor.inventory(payload.node_id),
            node_id=payload.node_id,
        )
        if live_node["executeEnabled"] is not True:
            raise _error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "storage_node_execution_disabled",
                "Узел доступен только для чтения; очистка не подключена.",
            )
        preview = _validate_preview(
            executor.preview(command),
            operation_kind=payload.operation_kind,
            now=now,
        )
    except HTTPException:
        raise
    except StorageExecutorError as error:
        raise _safe_executor_error(error) from error
    except ValueError as error:
        raise _error(
            status.HTTP_502_BAD_GATEWAY,
            "storage_node_preview_invalid",
            "Исполнитель вернул небезопасный результат preview.",
        ) from error
    except Exception as error:
        raise _error(
            status.HTTP_502_BAD_GATEWAY,
            "storage_node_preview_failed",
            "Не удалось выполнить preview на выбранном узле.",
        ) from error

    preview_id = f"spv_{uuid.uuid4().hex}"
    with transaction(database, immediate=True):
        replay = database.execute(
            """
            SELECT *
            FROM storage_admin_previews
            WHERE actor_user_id = ?
              AND actor_tenant_id = ?
              AND idempotency_key_hash = ?
            LIMIT 1
            """,
            (actor.user_id, actor.tenant_id, key_digest),
        ).fetchone()
        if replay is not None:
            if str(replay["request_hash"]) != request_digest:
                raise _error(
                    status.HTTP_409_CONFLICT,
                    "storage_idempotency_conflict",
                    "Idempotency-Key уже использован для другого preview.",
                )
            return _preview_projection(replay, replayed=True)
        authority_epoch = _require_storage_authority(database, actor=actor)
        now = _now(database)
        if int(preview["expiresAt"]) < now:
            raise _error(
                status.HTTP_409_CONFLICT,
                "storage_preview_expired",
                "Preview истёк до сохранения. Выполните новый dry run.",
            )
        if payload.operation_kind == "quarantine":
            assert payload.project_id is not None
            _ensure_quarantine_project_allowed(
                database,
                node_id=payload.node_id,
                project_id=payload.project_id,
            )
        elif payload.operation_kind == "restore":
            assert payload.quarantine_id is not None
            _require_restore_target(
                database,
                node_id=payload.node_id,
                quarantine_id=payload.quarantine_id,
            )
        elif payload.operation_kind == "purge":
            assert payload.quarantine_id is not None
            _require_purge_target(
                database,
                node_id=payload.node_id,
                quarantine_id=payload.quarantine_id,
                now=now,
            )
        database.execute(
            """
            INSERT INTO storage_admin_previews (
                id, actor_user_id, actor_tenant_id, authority_epoch,
                idempotency_key_hash, request_hash, node_id, category,
                operation_kind, project_id, quarantine_id,
                executor_preview_ref, node_generation, candidate_count,
                reclaimable_bytes, protected_item_count,
                protected_scopes_json, expires_at, created_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?
            )
            """,
            (
                preview_id,
                actor.user_id,
                actor.tenant_id,
                authority_epoch,
                key_digest,
                request_digest,
                payload.node_id,
                payload.category,
                payload.operation_kind,
                payload.project_id,
                payload.quarantine_id,
                preview["executorPreviewRef"],
                preview["nodeGeneration"],
                preview["candidateCount"],
                preview["reclaimableBytes"],
                _canonical_json(preview["protectedScopes"]),
                preview["expiresAt"],
                now,
            ),
        )
        _record_audit(
            database,
            actor=actor,
            authority_epoch=authority_epoch,
            action="storage.preview.created",
            node_id=payload.node_id,
            category=payload.category,
            operation_kind=payload.operation_kind,
            target_ref=_audit_target_ref(
                category=payload.category,
                operation_kind=payload.operation_kind,
                project_id=payload.project_id,
                quarantine_id=payload.quarantine_id,
            ),
            preview_id=preview_id,
            operation_id=None,
            details={
                "candidateCount": preview["candidateCount"],
                "reclaimableBytes": preview["reclaimableBytes"],
                "protectedItemCount": 0,
                "expiresAt": preview["expiresAt"],
            },
        )
        row = _preview_row(database, preview_id=preview_id, actor=actor)
        assert row is not None
    return _preview_projection(row)


def _claim_operation(
    database: sqlite3.Connection,
    *,
    actor: UserSession,
    authority_epoch: int,
    preview: sqlite3.Row,
    idempotency_key_hash: str,
    request_hash: str,
) -> sqlite3.Row:
    operation_id = f"sop_{uuid.uuid4().hex}"
    quarantine_id = (
        f"sqn_{uuid.uuid4().hex}"
        if str(preview["operation_kind"]) == "quarantine"
        else (
            str(preview["quarantine_id"])
            if str(preview["operation_kind"]) in {"restore", "purge"}
            else None
        )
    )
    now = _now(database)
    purge_eligible_at = (
        now + _PROJECT_RETENTION_SECONDS
        if str(preview["operation_kind"]) == "quarantine"
        else None
    )
    database.execute(
        """
        INSERT INTO storage_admin_operations (
            id, preview_id, actor_user_id, actor_tenant_id,
            authority_epoch, idempotency_key_hash, request_hash,
            status, quarantine_id, purge_eligible_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
        """,
        (
            operation_id,
            str(preview["id"]),
            actor.user_id,
            actor.tenant_id,
            authority_epoch,
            idempotency_key_hash,
            request_hash,
            quarantine_id,
            purge_eligible_at,
            now,
        ),
    )
    database.execute(
        """
        UPDATE storage_admin_previews
        SET consumed_at = ?
        WHERE id = ? AND consumed_at IS NULL
        """,
        (now, str(preview["id"])),
    )
    return _operation_row(database, operation_id=operation_id)


def _mark_operation_pending(
    database: sqlite3.Connection,
    *,
    operation_id: str,
    error_code: str,
) -> sqlite3.Row:
    with transaction(database, immediate=True):
        database.execute(
            """
            UPDATE storage_admin_operations
            SET error_code = ?
            WHERE id = ? AND status = 'pending'
            """,
            (error_code, operation_id),
        )
    return _operation_row(database, operation_id=operation_id)


def _apply_executor_result(
    database: sqlite3.Connection,
    *,
    actor: UserSession,
    authority_epoch: int,
    operation_id: str,
    result: dict[str, Any],
) -> sqlite3.Row:
    with transaction(database, immediate=True):
        current = _operation_row(database, operation_id=operation_id)
        if str(current["status"]) != "pending":
            return current
        executor_status = str(result["status"])
        if executor_status == "applying":
            database.execute(
                """
                UPDATE storage_admin_operations
                SET error_code = ?
                WHERE id = ? AND status = 'pending'
                """,
                (
                    result["errorCode"]
                    or "storage_node_operation_applying",
                    operation_id,
                ),
            )
            return _operation_row(database, operation_id=operation_id)

        if executor_status == "failed":
            error_code = str(result["errorCode"])
            database.execute(
                """
                UPDATE storage_admin_operations
                SET status = 'failed',
                    error_code = ?,
                    completed_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (error_code, result["completedAt"], operation_id),
            )
            failed = _operation_row(database, operation_id=operation_id)
            _record_audit(
                database,
                actor=actor,
                authority_epoch=authority_epoch,
                action="storage.operation.failed",
                node_id=str(failed["node_id"]),
                category=str(failed["category"]),
                operation_kind=str(failed["operation_kind"]),
                target_ref=_audit_target_ref(
                    category=str(failed["category"]),
                    operation_kind=str(failed["operation_kind"]),
                    project_id=failed["project_id"],
                    quarantine_id=failed["preview_quarantine_id"],
                ),
                preview_id=str(failed["preview_id"]),
                operation_id=operation_id,
                details={"errorCode": error_code},
            )
            return failed

        completed_at = int(result["completedAt"])
        operation_kind = str(current["operation_kind"])
        if operation_kind == "quarantine":
            database.execute(
                """
                INSERT INTO storage_project_quarantines (
                    id, node_id, project_id, status, size_bytes,
                    quarantined_operation_id, quarantined_at,
                    purge_eligible_at
                ) VALUES (?, ?, ?, 'retained', ?, ?, ?, ?)
                """,
                (
                    str(current["quarantine_id"]),
                    str(current["node_id"]),
                    str(current["project_id"]),
                    int(current["reclaimable_bytes"]),
                    operation_id,
                    completed_at,
                    int(current["purge_eligible_at"]),
                ),
            )
        elif operation_kind == "restore":
            updated = database.execute(
                """
                UPDATE storage_project_quarantines
                SET status = 'restored',
                    restored_operation_id = ?,
                    restored_at = ?
                WHERE id = ?
                  AND node_id = ?
                  AND status = 'retained'
                """,
                (
                    operation_id,
                    completed_at,
                    str(current["preview_quarantine_id"]),
                    str(current["node_id"]),
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError(
                    "quarantine changed after executor restore confirmation"
                )
        elif operation_kind == "purge":
            updated = database.execute(
                """
                UPDATE storage_project_quarantines
                SET status = 'purged',
                    purged_operation_id = ?,
                    purged_at = ?
                WHERE id = ?
                  AND node_id = ?
                  AND status = 'retained'
                  AND purge_eligible_at <= ?
                """,
                (
                    operation_id,
                    completed_at,
                    str(current["preview_quarantine_id"]),
                    str(current["node_id"]),
                    completed_at,
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError(
                    "quarantine changed after executor purge confirmation"
                )
        database.execute(
            """
            UPDATE storage_admin_operations
            SET status = 'succeeded',
                affected_item_count = ?,
                reclaimed_bytes = ?,
                error_code = NULL,
                completed_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (
                result["affectedItemCount"],
                result["reclaimedBytes"],
                completed_at,
                operation_id,
            ),
        )
        completed = _operation_row(database, operation_id=operation_id)
        _record_audit(
            database,
            actor=actor,
            authority_epoch=authority_epoch,
            action="storage.operation.succeeded",
            node_id=str(completed["node_id"]),
            category=str(completed["category"]),
            operation_kind=str(completed["operation_kind"]),
            target_ref=_audit_target_ref(
                category=str(completed["category"]),
                operation_kind=str(completed["operation_kind"]),
                project_id=completed["project_id"],
                quarantine_id=completed["preview_quarantine_id"],
            ),
            preview_id=str(completed["preview_id"]),
            operation_id=operation_id,
            details={
                "affectedItemCount": result["affectedItemCount"],
                "reclaimedBytes": result["reclaimedBytes"],
                "protectedItemCount": 0,
            },
        )
    return completed


@router.post("/operations", response_model=StorageOperationView)
def execute_storage_operation(
    payload: StorageOperationExecute,
    request: Request,
    actor: OwnerDependency,
    database: DatabaseDependency,
    idempotency_key: IdempotencyDependency,
    _mutation_auth: MutationAuthDependency,
) -> dict[str, Any]:
    authority_epoch = _require_storage_authority(database, actor=actor)
    _require_recent_auth(actor)
    request_payload = payload.model_dump(mode="json", by_alias=True)
    request_digest = _request_hash(request_payload)
    key_digest = _digest(idempotency_key)
    resumed_pending = False
    with transaction(database, immediate=True):
        authority_epoch = _require_storage_authority(database, actor=actor)
        existing = database.execute(
            """
            SELECT id, request_hash
            FROM storage_admin_operations
            WHERE actor_user_id = ?
              AND actor_tenant_id = ?
              AND idempotency_key_hash = ?
            LIMIT 1
            """,
            (actor.user_id, actor.tenant_id, key_digest),
        ).fetchone()
        if existing is not None:
            if str(existing["request_hash"]) != request_digest:
                raise _error(
                    status.HTTP_409_CONFLICT,
                    "storage_idempotency_conflict",
                    "Idempotency-Key уже использован для другой операции.",
                )
            operation = _operation_row(
                database,
                operation_id=str(existing["id"]),
            )
            if str(operation["status"]) != "pending":
                return _operation_projection(operation, replayed=True)
            preview = _preview_row(
                database,
                preview_id=str(operation["preview_id"]),
                actor=actor,
            )
            if preview is None:
                raise RuntimeError(
                    "pending storage operation lost its preview"
                )
            resumed_pending = True
        else:
            preview = _preview_row(
                database,
                preview_id=payload.preview_id,
                actor=actor,
            )
            if preview is None:
                raise _error(
                    status.HTTP_404_NOT_FOUND,
                    "storage_preview_not_found",
                    "Preview не найден или принадлежит другой сессии владельца.",
                )
            expected_confirmation = _confirmation(
                str(preview["operation_kind"])
            )
            if payload.confirmation != expected_confirmation:
                raise _error(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "storage_confirmation_invalid",
                    (
                        "Для операции требуется подтверждение "
                        f"{expected_confirmation}."
                    ),
                )
            now = _now(database)
            if int(preview["expires_at"]) < now:
                raise _error(
                    status.HTTP_409_CONFLICT,
                    "storage_preview_expired",
                    "Preview истёк. Выполните новый dry run.",
                )
            if int(preview["candidate_count"]) == 0:
                raise _error(
                    status.HTTP_409_CONFLICT,
                    "storage_preview_empty",
                    "Preview не нашёл объектов для очистки.",
                )
            claimed = database.execute(
                """
                SELECT id
                FROM storage_admin_operations
                WHERE preview_id = ?
                LIMIT 1
                """,
                (payload.preview_id,),
            ).fetchone()
            if claimed is not None:
                raise _error(
                    status.HTTP_409_CONFLICT,
                    "storage_preview_consumed",
                    "Preview уже был выполнен. Обновите состояние хранилища.",
                )
            if str(preview["operation_kind"]) == "quarantine":
                _ensure_quarantine_project_allowed(
                    database,
                    node_id=str(preview["node_id"]),
                    project_id=str(preview["project_id"]),
                )
            elif str(preview["operation_kind"]) == "restore":
                _require_restore_target(
                    database,
                    node_id=str(preview["node_id"]),
                    quarantine_id=str(preview["quarantine_id"]),
                )
            elif str(preview["operation_kind"]) == "purge":
                _require_purge_target(
                    database,
                    node_id=str(preview["node_id"]),
                    quarantine_id=str(preview["quarantine_id"]),
                    now=now,
                )
            operation = _claim_operation(
                database,
                actor=actor,
                authority_epoch=authority_epoch,
                preview=preview,
                idempotency_key_hash=key_digest,
                request_hash=request_digest,
            )
        if int(preview["authority_epoch"]) != authority_epoch:
            raise _error(
                status.HTTP_409_CONFLICT,
                "storage_preview_authority_changed",
                "Полномочия изменились после preview. Выполните новый dry run.",
            )

    command = StorageExecuteCommand(
        operation_id=str(operation["id"]),
        node_id=str(operation["node_id"]),
        category=str(operation["category"]),
        operation_kind=str(operation["operation_kind"]),
        executor_preview_ref=str(preview["executor_preview_ref"]),
        node_generation=str(preview["node_generation"]),
        project_id=preview["project_id"],
        quarantine_id=operation["quarantine_id"],
        purge_eligible_at=operation["purge_eligible_at"],
        guarded_scopes=REQUIRED_STORAGE_GUARDS,
    )
    try:
        result = _validate_result(
            _executor(request).execute(command),
            operation_id=str(operation["id"]),
            executor_preview_ref=str(preview["executor_preview_ref"]),
            expected_quarantine_id=operation["quarantine_id"],
            operation_kind=str(operation["operation_kind"]),
            preview_count=int(preview["candidate_count"]),
            preview_bytes=int(preview["reclaimable_bytes"]),
            now=_now(database),
        )
    except StorageExecutorError as error:
        pending = _mark_operation_pending(
            database,
            operation_id=str(operation["id"]),
            error_code=_safe_error_code(error),
        )
        return _operation_projection(pending, replayed=resumed_pending)
    except Exception:
        pending = _mark_operation_pending(
            database,
            operation_id=str(operation["id"]),
            error_code="storage_node_outcome_unknown",
        )
        return _operation_projection(pending, replayed=resumed_pending)

    try:
        completed = _apply_executor_result(
            database,
            operation_id=str(operation["id"]),
            actor=actor,
            authority_epoch=authority_epoch,
            result=result,
        )
    except (RuntimeError, sqlite3.IntegrityError):
        completed = _mark_operation_pending(
            database,
            operation_id=str(operation["id"]),
            error_code="storage_control_plane_reconcile_required",
        )
    return _operation_projection(completed, replayed=resumed_pending)


@router.post(
    "/operations/reconcile",
    response_model=StorageOperationView,
)
def reconcile_storage_operation(
    payload: StorageOperationReconcile,
    request: Request,
    actor: OwnerDependency,
    database: DatabaseDependency,
    _mutation_auth: MutationAuthDependency,
) -> dict[str, Any]:
    """Query the node journal by operation ID without re-executing work."""

    authority_epoch = _require_storage_authority(database, actor=actor)
    with transaction(database, immediate=True):
        owned = database.execute(
            """
            SELECT id
            FROM storage_admin_operations
            WHERE id = ?
              AND actor_user_id = ?
              AND actor_tenant_id = ?
            LIMIT 1
            """,
            (payload.operation_id, actor.user_id, actor.tenant_id),
        ).fetchone()
        if owned is None:
            raise _error(
                status.HTTP_404_NOT_FOUND,
                "storage_operation_not_found",
                "Операция не найдена или принадлежит другому владельцу.",
            )
        operation = _operation_row(
            database,
            operation_id=payload.operation_id,
        )
        if str(operation["status"]) != "pending":
            return _operation_projection(operation, reconciled=True)
        database.execute(
            """
            UPDATE storage_admin_operations
            SET reconcile_attempt_count = reconcile_attempt_count + 1,
                reconcile_attempted_at = unixepoch()
            WHERE id = ? AND status = 'pending'
            """,
            (payload.operation_id,),
        )

    try:
        result = _validate_result(
            _executor(request).status(
                StorageStatusCommand(
                    operation_id=payload.operation_id,
                    node_id=str(operation["node_id"]),
                )
            ),
            operation_id=payload.operation_id,
            executor_preview_ref=str(operation["executor_preview_ref"]),
            expected_quarantine_id=operation["quarantine_id"],
            operation_kind=str(operation["operation_kind"]),
            preview_count=int(operation["candidate_count"]),
            preview_bytes=int(operation["reclaimable_bytes"]),
            now=_now(database),
        )
    except StorageExecutorError as error:
        pending = _mark_operation_pending(
            database,
            operation_id=payload.operation_id,
            error_code=_safe_error_code(error),
        )
        return _operation_projection(pending, reconciled=True)
    except Exception:
        pending = _mark_operation_pending(
            database,
            operation_id=payload.operation_id,
            error_code="storage_node_status_invalid",
        )
        return _operation_projection(pending, reconciled=True)

    try:
        reconciled = _apply_executor_result(
            database,
            actor=actor,
            authority_epoch=authority_epoch,
            operation_id=payload.operation_id,
            result=result,
        )
    except (RuntimeError, sqlite3.IntegrityError):
        reconciled = _mark_operation_pending(
            database,
            operation_id=payload.operation_id,
            error_code="storage_control_plane_reconcile_required",
        )
    return _operation_projection(reconciled, reconciled=True)


__all__ = ["router"]
