"""Strict public contracts for owner-managed node storage maintenance."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from .schemas import APIModel


StorageNodeId = Literal["home", "primary"]
StorageCleanupCategory = Literal[
    "build",
    "cache",
    "log",
    "stopped-container",
    "project-quarantine",
]
StorageOperationKind = Literal["cleanup", "quarantine", "restore", "purge"]
StorageProtectionScope = Literal[
    "active-release",
    "current-symlink",
    "primary-database",
    "durable-volumes",
    "agent-runtime-state",
]
StorageExecutorStatus = Literal["ready", "unavailable", "error"]
StorageOperationStatus = Literal["pending", "succeeded", "failed"]
StorageConfirmation = Literal["CLEANUP", "QUARANTINE", "RESTORE", "PURGE"]

ProjectRef = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=160,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._~-]{2,159}$",
    ),
]
QuarantineId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"^sqn_[0-9a-f]{32}$",
    ),
]
StoragePreviewId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"^spv_[0-9a-f]{32}$",
    ),
]
StorageOperationId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"^sop_[0-9a-f]{32}$",
    ),
]


class StoragePreviewCreate(APIModel):
    node_id: StorageNodeId = Field(alias="nodeId")
    category: StorageCleanupCategory
    operation_kind: StorageOperationKind = Field(alias="operationKind")
    project_id: ProjectRef | None = Field(default=None, alias="projectId")
    quarantine_id: QuarantineId | None = Field(
        default=None,
        alias="quarantineId",
    )

    @model_validator(mode="after")
    def validate_shape(self) -> "StoragePreviewCreate":
        ordinary = {"build", "cache", "log", "stopped-container"}
        if self.operation_kind == "cleanup":
            if (
                self.category not in ordinary
                or self.project_id is not None
                or self.quarantine_id is not None
            ):
                raise ValueError("cleanup accepts only a cleanup category")
        elif self.operation_kind == "quarantine":
            if (
                self.category != "project-quarantine"
                or self.project_id is None
                or self.quarantine_id is not None
            ):
                raise ValueError("quarantine requires one project ID")
        elif self.operation_kind in {"restore", "purge"} and (
            self.category != "project-quarantine"
            or self.quarantine_id is None
            or self.project_id is not None
        ):
            raise ValueError(
                f"{self.operation_kind} requires one quarantine ID"
            )
        return self


class StorageOperationExecute(APIModel):
    preview_id: StoragePreviewId = Field(alias="previewId")
    confirmation: StorageConfirmation


class StorageOperationReconcile(APIModel):
    operation_id: StorageOperationId = Field(alias="operationId")


class StorageCategoryView(APIModel):
    category: StorageCleanupCategory
    reclaimable_bytes: Annotated[int, Field(ge=0, le=2**63 - 1)] = Field(
        alias="reclaimableBytes",
    )
    item_count: Annotated[int, Field(ge=0, le=1_000_000_000)] = Field(
        alias="itemCount",
    )
    oldest_item_at: Annotated[int, Field(ge=0)] | None = Field(
        default=None,
        alias="oldestItemAt",
    )


class StorageProjectCandidateView(APIModel):
    project_id: ProjectRef = Field(alias="projectId")
    display_name: Annotated[str, Field(min_length=1, max_length=120)] = Field(
        alias="displayName",
    )
    size_bytes: Annotated[int, Field(ge=0, le=2**63 - 1)] = Field(
        alias="sizeBytes",
    )
    last_modified_at: Annotated[int, Field(ge=0)] = Field(
        alias="lastModifiedAt",
    )


class StorageCapacitySegmentView(APIModel):
    kind: Literal["root-lv", "vg-unallocated"]
    display_name: str = Field(alias="displayName")
    display_size: Annotated[str, Field(min_length=1, max_length=32)] = Field(
        alias="displaySize",
    )
    capacity_bytes: Annotated[int, Field(ge=0, le=2**63 - 1)] = Field(
        alias="capacityBytes",
    )
    read_only: Literal[True] = Field(alias="readOnly")


class StorageQuarantineView(APIModel):
    id: QuarantineId
    node_id: StorageNodeId = Field(alias="nodeId")
    project_id: ProjectRef = Field(alias="projectId")
    status: Literal["retained", "purge-eligible", "restored", "purged"]
    size_bytes: Annotated[int, Field(ge=0, le=2**63 - 1)] = Field(
        alias="sizeBytes",
    )
    quarantined_at: Annotated[int, Field(ge=0)] = Field(
        alias="quarantinedAt",
    )
    purge_eligible_at: Annotated[int, Field(ge=0)] = Field(
        alias="purgeEligibleAt",
    )
    purged_at: Annotated[int, Field(ge=0)] | None = Field(
        default=None,
        alias="purgedAt",
    )
    restored_at: Annotated[int, Field(ge=0)] | None = Field(
        default=None,
        alias="restoredAt",
    )


class StorageNodeView(APIModel):
    id: StorageNodeId
    display_name: Literal["Home", "Primary"] = Field(alias="displayName")
    executor_status: StorageExecutorStatus = Field(alias="executorStatus")
    execute_enabled: bool = Field(alias="executeEnabled")
    error_code: str | None = Field(default=None, alias="errorCode")
    capacity_bytes: Annotated[int, Field(ge=0, le=2**63 - 1)] | None = Field(
        default=None,
        alias="capacityBytes",
    )
    used_bytes: Annotated[int, Field(ge=0, le=2**63 - 1)] | None = Field(
        default=None,
        alias="usedBytes",
    )
    free_bytes: Annotated[int, Field(ge=0, le=2**63 - 1)] | None = Field(
        default=None,
        alias="freeBytes",
    )
    scanned_at: Annotated[int, Field(ge=0)] | None = Field(
        default=None,
        alias="scannedAt",
    )
    generation: str | None = None
    policy_digest: str | None = Field(default=None, alias="policyDigest")
    blocked_item_count: Annotated[
        int,
        Field(ge=0, le=1_000_000_000),
    ] = Field(alias="blockedItemCount")
    capacity_source: Literal["live-executor", "configured-record"] = Field(
        alias="capacitySource",
    )
    capacity_observed_at: Annotated[int, Field(ge=0)] | None = Field(
        default=None,
        alias="capacityObservedAt",
    )
    categories: list[StorageCategoryView]
    capacity_segments: list[StorageCapacitySegmentView] = Field(
        alias="capacitySegments",
    )
    project_candidates: list[StorageProjectCandidateView] = Field(
        alias="projectCandidates",
    )
    quarantines: list[StorageQuarantineView]
    protected_scopes: list[StorageProtectionScope] = Field(
        alias="protectedScopes",
    )


class StoragePreviewView(APIModel):
    id: StoragePreviewId
    node_id: StorageNodeId = Field(alias="nodeId")
    category: StorageCleanupCategory
    operation_kind: StorageOperationKind = Field(alias="operationKind")
    project_id: ProjectRef | None = Field(default=None, alias="projectId")
    quarantine_id: QuarantineId | None = Field(
        default=None,
        alias="quarantineId",
    )
    candidate_count: Annotated[int, Field(ge=0, le=1_000_000_000)] = Field(
        alias="candidateCount",
    )
    reclaimable_bytes: Annotated[int, Field(ge=0, le=2**63 - 1)] = Field(
        alias="reclaimableBytes",
    )
    protected_item_count: Literal[0] = Field(alias="protectedItemCount")
    protected_scopes: list[StorageProtectionScope] = Field(
        alias="protectedScopes",
    )
    confirmation: StorageConfirmation
    expires_at: Annotated[int, Field(ge=0)] = Field(alias="expiresAt")
    created_at: Annotated[int, Field(ge=0)] = Field(alias="createdAt")
    replayed: bool = False


class StorageOperationView(APIModel):
    id: StorageOperationId
    preview_id: StoragePreviewId = Field(alias="previewId")
    node_id: StorageNodeId = Field(alias="nodeId")
    category: StorageCleanupCategory
    operation_kind: StorageOperationKind = Field(alias="operationKind")
    status: StorageOperationStatus
    affected_item_count: Annotated[
        int,
        Field(ge=0, le=1_000_000_000),
    ] = Field(alias="affectedItemCount")
    reclaimed_bytes: Annotated[int, Field(ge=0, le=2**63 - 1)] = Field(
        alias="reclaimedBytes",
    )
    quarantine_id: QuarantineId | None = Field(
        default=None,
        alias="quarantineId",
    )
    error_code: str | None = Field(default=None, alias="errorCode")
    created_at: Annotated[int, Field(ge=0)] = Field(alias="createdAt")
    completed_at: Annotated[int, Field(ge=0)] | None = Field(
        default=None,
        alias="completedAt",
    )
    replayed: bool = False
    reconciled: bool = False


class StorageAuditView(APIModel):
    id: Annotated[
        str,
        StringConstraints(pattern=r"^saudit_[0-9a-f]{32}$"),
    ]
    action: Literal[
        "storage.preview.created",
        "storage.operation.succeeded",
        "storage.operation.failed",
    ]
    node_id: StorageNodeId = Field(alias="nodeId")
    category: StorageCleanupCategory
    operation_kind: StorageOperationKind = Field(alias="operationKind")
    target_ref: str = Field(alias="targetRef")
    preview_id: StoragePreviewId = Field(alias="previewId")
    operation_id: StorageOperationId | None = Field(
        default=None,
        alias="operationId",
    )
    created_at: Annotated[int, Field(ge=0)] = Field(alias="createdAt")


class StorageSnapshotView(APIModel):
    nodes: list[StorageNodeView]
    recent_operations: list[StorageOperationView] = Field(
        alias="recentOperations",
    )
    audit: list[StorageAuditView]
