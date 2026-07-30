"""Narrow adapter boundary for storage maintenance on Home and Primary.

This module intentionally has no SSH, shell, Docker, or filesystem
implementation. Deployments must inject a purpose-built executor. The default
adapter fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from .storage_admin_contracts import (
    StorageCleanupCategory,
    StorageNodeId,
    StorageOperationKind,
    StorageProtectionScope,
)


REQUIRED_STORAGE_GUARDS: tuple[StorageProtectionScope, ...] = (
    "active-release",
    "current-symlink",
    "primary-database",
    "durable-volumes",
    "agent-runtime-state",
)

class StorageExecutorError(RuntimeError):
    """A safe protocol/transport error, never a terminal operation result."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.retryable = retryable


class StorageExecutorUnavailable(StorageExecutorError):
    def __init__(self) -> None:
        super().__init__(
            "storage_node_executor_unavailable",
            "Для этого узла не настроен безопасный исполнитель очистки.",
        )


@dataclass(frozen=True, slots=True)
class StorageCategoryInventory:
    category: StorageCleanupCategory
    reclaimable_bytes: int
    item_count: int
    oldest_item_at: int | None = None


@dataclass(frozen=True, slots=True)
class StorageProjectCandidate:
    project_id: str
    display_name: str
    size_bytes: int
    last_modified_at: int


@dataclass(frozen=True, slots=True)
class StorageNodeQuarantine:
    quarantine_id: str
    project_id: str
    status: Literal["retained", "restored", "purged"]
    size_bytes: int
    quarantined_at: int
    purge_eligible_at: int


@dataclass(frozen=True, slots=True)
class StorageCapacitySegment:
    kind: Literal["root-lv", "vg-unallocated"]
    display_name: str
    display_size: str
    capacity_bytes: int


CONFIGURED_HOME_CAPACITY_SEGMENTS: tuple[StorageCapacitySegment, ...] = (
    StorageCapacitySegment(
        kind="root-lv",
        display_name="Корневой LV",
        display_size="210 GiB",
        capacity_bytes=225_485_783_040,
    ),
    StorageCapacitySegment(
        kind="vg-unallocated",
        display_name="Нераспределённый резерв VG",
        display_size="19.83 GiB",
        capacity_bytes=21_292_300_370,
    ),
)


@dataclass(frozen=True, slots=True)
class StorageNodeInventory:
    node_id: StorageNodeId
    capacity_bytes: int
    used_bytes: int
    free_bytes: int
    scanned_at: int
    generation: str
    policy_digest: str
    blocked_item_count: int
    categories: tuple[StorageCategoryInventory, ...]
    execute_enabled: bool = False
    capacity_segments: tuple[StorageCapacitySegment, ...] = ()
    project_candidates: tuple[StorageProjectCandidate, ...] = ()
    quarantines: tuple[StorageNodeQuarantine, ...] = ()
    guarded_scopes: tuple[StorageProtectionScope, ...] = REQUIRED_STORAGE_GUARDS


@dataclass(frozen=True, slots=True)
class StoragePreviewCommand:
    node_id: StorageNodeId
    category: StorageCleanupCategory
    operation_kind: StorageOperationKind
    project_id: str | None
    quarantine_id: str | None
    guarded_scopes: tuple[StorageProtectionScope, ...]


@dataclass(frozen=True, slots=True)
class StorageExecutorPreview:
    executor_preview_ref: str
    node_generation: str
    candidate_count: int
    reclaimable_bytes: int
    protected_item_count: int
    guarded_scopes: tuple[StorageProtectionScope, ...]
    confirmation: Literal["CLEANUP", "QUARANTINE", "RESTORE", "PURGE"]
    expires_at: int
    replayed: bool


@dataclass(frozen=True, slots=True)
class StorageExecuteCommand:
    operation_id: str
    node_id: StorageNodeId
    category: StorageCleanupCategory
    operation_kind: StorageOperationKind
    executor_preview_ref: str
    node_generation: str
    project_id: str | None
    quarantine_id: str | None
    purge_eligible_at: int | None
    guarded_scopes: tuple[StorageProtectionScope, ...]


@dataclass(frozen=True, slots=True)
class StorageExecutorResult:
    operation_id: str
    executor_preview_ref: str
    status: Literal["applying", "succeeded", "failed"]
    affected_item_count: int
    reclaimed_bytes: int
    protected_item_count: int
    guarded_scopes: tuple[StorageProtectionScope, ...]
    node_generation: str
    quarantine_id: str | None
    error_code: str | None
    created_at: int
    completed_at: int | None
    replayed: bool


@dataclass(frozen=True, slots=True)
class StorageStatusCommand:
    operation_id: str
    node_id: StorageNodeId


class StorageNodeExecutor(Protocol):
    def inventory(self, node_id: StorageNodeId) -> StorageNodeInventory:
        """Read allowlisted reclaimable categories without mutating the node."""

    def preview(self, command: StoragePreviewCommand) -> StorageExecutorPreview:
        """Perform a non-mutating dry run and return an opaque preview ref."""

    def execute(self, command: StorageExecuteCommand) -> StorageExecutorResult:
        """Execute an already-previewed operation idempotently by operation ID."""

    def status(self, command: StorageStatusCommand) -> StorageExecutorResult:
        """Read the durable node journal without executing an operation."""


class UnavailableStorageNodeExecutor:
    """Fail-closed default used until a deployment injects an executor."""

    def inventory(self, _node_id: StorageNodeId) -> StorageNodeInventory:
        raise StorageExecutorUnavailable()

    def preview(
        self,
        _command: StoragePreviewCommand,
    ) -> StorageExecutorPreview:
        raise StorageExecutorUnavailable()

    def execute(
        self,
        _command: StorageExecuteCommand,
    ) -> StorageExecutorResult:
        raise StorageExecutorUnavailable()

    def status(
        self,
        _command: StorageStatusCommand,
    ) -> StorageExecutorResult:
        raise StorageExecutorUnavailable()


__all__ = [
    "CONFIGURED_HOME_CAPACITY_SEGMENTS",
    "REQUIRED_STORAGE_GUARDS",
    "StorageCapacitySegment",
    "StorageCategoryInventory",
    "StorageExecuteCommand",
    "StorageExecutorError",
    "StorageExecutorPreview",
    "StorageExecutorResult",
    "StorageExecutorUnavailable",
    "StorageNodeExecutor",
    "StorageNodeInventory",
    "StorageNodeQuarantine",
    "StoragePreviewCommand",
    "StorageProjectCandidate",
    "StorageStatusCommand",
    "UnavailableStorageNodeExecutor",
]
