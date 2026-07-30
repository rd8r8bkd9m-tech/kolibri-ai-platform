"""Versioned, fail-closed AF_UNIX adapter for the Rust storage executor.

The adapter never starts a process, reads a policy file, opens SSH, or invokes
a shell. Executable and policy paths are expected identity metadata; the only
active transport is one bounded request over a configured Unix socket.
"""

from __future__ import annotations

import json
import re
import socket
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from .storage_admin_contracts import StorageNodeId
from .storage_node_executor import (
    REQUIRED_STORAGE_GUARDS,
    StorageCapacitySegment,
    StorageCategoryInventory,
    StorageExecuteCommand,
    StorageExecutorError,
    StorageExecutorPreview,
    StorageExecutorResult,
    StorageExecutorUnavailable,
    StorageNodeExecutor,
    StorageNodeInventory,
    StorageNodeQuarantine,
    StoragePreviewCommand,
    StorageProjectCandidate,
    StorageStatusCommand,
    UnavailableStorageNodeExecutor,
)


PROTOCOL_VERSION = "v1"
HOME_SOCKET_PATH = Path("/run/kolibri-storage-executor/executor.sock")
EXECUTABLE_PATH = Path("/usr/local/libexec/kolibri-storage-executor")
POLICY_PATH = Path("/etc/kolibri-storage-executor/policy.json")
_SAFE_ERROR = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")
_SAFE_OPAQUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")
_SAFE_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SAFE_OPERATION = re.compile(r"^sop_[0-9a-f]{32}$")
_SAFE_QUARANTINE = re.compile(r"^sqn_[0-9a-f]{32}$")
_SAFE_PROJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{2,159}$")
_MAX_INTEGER = 2**63 - 1


@dataclass(frozen=True, slots=True)
class StorageExecutorEndpoint:
    node_id: StorageNodeId
    socket_path: Path
    expected_executable_path: Path
    expected_policy_path: Path
    expected_policy_digest: str

    def __post_init__(self) -> None:
        if (
            self.node_id != "home"
            or self.socket_path != HOME_SOCKET_PATH
            or self.expected_executable_path != EXECUTABLE_PATH
            or self.expected_policy_path != POLICY_PATH
            or _SAFE_DIGEST.fullmatch(self.expected_policy_digest) is None
        ):
            raise ValueError("storage executor endpoint identity is invalid")


class StorageWireTransport(Protocol):
    def exchange(
        self,
        *,
        socket_path: Path,
        request: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> bytes:
        """Return exactly one newline-terminated response."""


class UnixSocketStorageTransport:
    """One request per AF_UNIX connection with bounded response framing."""

    def exchange(
        self,
        *,
        socket_path: Path,
        request: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> bytes:
        response = bytearray()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(timeout_seconds)
                client.connect(str(socket_path))
                client.sendall(request)
                client.shutdown(socket.SHUT_WR)
                while True:
                    chunk = client.recv(min(16_384, max_response_bytes + 1))
                    if not chunk:
                        break
                    response.extend(chunk)
                    if len(response) > max_response_bytes:
                        raise StorageExecutorError(
                            "storage_executor_response_too_large",
                            "Storage executor response exceeded its bound.",
                        )
                    newline = response.find(b"\n")
                    if newline >= 0:
                        if newline != len(response) - 1:
                            raise StorageExecutorError(
                                "storage_executor_framing_invalid",
                                "Storage executor returned trailing bytes.",
                            )
                        return bytes(response)
        except StorageExecutorError:
            raise
        except (OSError, TimeoutError) as error:
            raise StorageExecutorError(
                "storage_node_transport_unavailable",
                "Storage executor Unix socket is unavailable.",
                retryable=True,
            ) from error
        raise StorageExecutorError(
            "storage_executor_framing_invalid",
            "Storage executor response was not newline terminated.",
        )


def _record(value: object, keys: set[str]) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or any(not isinstance(key, str) for key in value)
        or set(value) != keys
    ):
        raise ValueError("storage executor returned an invalid object")
    return cast(dict[str, Any], value)


def _text(
    value: object,
    *,
    maximum: int,
    pattern: re.Pattern[str] | None = None,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
        or (pattern is not None and pattern.fullmatch(value) is None)
    ):
        raise ValueError("storage executor returned invalid text")
    return value


def _integer(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > _MAX_INTEGER
    ):
        raise ValueError("storage executor returned invalid integer")
    return value


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("storage executor returned invalid boolean")
    return value


def _nullable_text(
    value: object,
    *,
    maximum: int,
    pattern: re.Pattern[str],
) -> str | None:
    if value is None:
        return None
    return _text(value, maximum=maximum, pattern=pattern)


def _scopes(value: object) -> tuple[str, ...]:
    allowed = set(REQUIRED_STORAGE_GUARDS)
    if (
        not isinstance(value, list)
        or len(value) > len(REQUIRED_STORAGE_GUARDS)
        or any(not isinstance(item, str) or item not in allowed for item in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError("storage executor returned invalid guard scopes")
    return tuple(value)


class RustStorageNodeExecutor:
    """Strict protocol-v1 adapter for configured local executor endpoints."""

    def __init__(
        self,
        *,
        endpoints: dict[StorageNodeId, StorageExecutorEndpoint],
        transport: StorageWireTransport | None = None,
        protocol_version: str = PROTOCOL_VERSION,
        timeout_seconds: float = 2.0,
        max_request_bytes: int = 65_536,
        max_response_bytes: int = 262_144,
    ) -> None:
        if (
            protocol_version != PROTOCOL_VERSION
            or set(endpoints) != {"home"}
            or endpoints["home"].node_id != "home"
            or not 0.1 <= timeout_seconds <= 10
            or not 1_024 <= max_request_bytes <= 65_536
            or not 1_024 <= max_response_bytes <= 262_144
        ):
            raise ValueError("storage executor adapter configuration is invalid")
        self._endpoints = dict(endpoints)
        self._transport = transport or UnixSocketStorageTransport()
        self._protocol_version = protocol_version
        self._timeout_seconds = timeout_seconds
        self._max_request_bytes = max_request_bytes
        self._max_response_bytes = max_response_bytes

    def _endpoint(self, node_id: StorageNodeId) -> StorageExecutorEndpoint:
        endpoint = self._endpoints.get(node_id)
        if endpoint is None:
            # Primary's final mTLS transport is deliberately not represented as
            # available by this local-socket adapter.
            raise StorageExecutorUnavailable()
        return endpoint

    def _request(
        self,
        node_id: StorageNodeId,
        command: dict[str, object],
        *,
        expected_kind: str,
    ) -> dict[str, Any]:
        endpoint = self._endpoint(node_id)
        request_id = f"sar_{uuid.uuid4().hex}"
        envelope = {
            "protocolVersion": self._protocol_version,
            "requestId": request_id,
            "command": command,
        }
        encoded = json.dumps(
            envelope,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if not encoded or len(encoded) > self._max_request_bytes:
            raise StorageExecutorError(
                "storage_executor_request_too_large",
                "Storage executor request exceeded its bound.",
            )
        raw = self._transport.exchange(
            socket_path=endpoint.socket_path,
            request=encoded,
            timeout_seconds=self._timeout_seconds,
            max_response_bytes=self._max_response_bytes,
        )
        if (
            not isinstance(raw, bytes)
            or not raw.endswith(b"\n")
            or len(raw) > self._max_response_bytes
            or b"\n" in raw[:-1]
        ):
            raise StorageExecutorError(
                "storage_executor_framing_invalid",
                "Storage executor returned invalid framing.",
            )
        try:
            decoded = json.loads(raw[:-1].decode("utf-8"))
            base = _record(
                decoded,
                (
                    {"protocolVersion", "requestId", "ok", "result"}
                    if isinstance(decoded, dict) and decoded.get("ok") is True
                    else {"protocolVersion", "requestId", "ok", "error"}
                ),
            )
            if (
                base["protocolVersion"] != self._protocol_version
                or base["requestId"] != request_id
                or not isinstance(base["ok"], bool)
            ):
                raise ValueError("response identity mismatch")
            if base["ok"] is False:
                error = _record(
                    base["error"],
                    {"code", "message", "retryable"},
                )
                raise StorageExecutorError(
                    _text(error["code"], maximum=128, pattern=_SAFE_ERROR),
                    _text(error["message"], maximum=500),
                    retryable=_boolean(error["retryable"]),
                )
            result = _record(base["result"], {"kind", "data"})
            if result["kind"] != expected_kind:
                raise ValueError("response kind mismatch")
            if not isinstance(result["data"], dict):
                raise ValueError("response data is invalid")
            return cast(dict[str, Any], result["data"])
        except StorageExecutorError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise StorageExecutorError(
                "storage_executor_protocol_invalid",
                "Storage executor returned an invalid protocol response.",
            ) from error

    def _inventory(self, node_id: StorageNodeId) -> StorageNodeInventory:
        data = _record(
            self._request(
                node_id,
                {"kind": "inventory", "nodeId": node_id},
                expected_kind="inventory",
            ),
            {
                "nodeId",
                "executeEnabled",
                "capacityBytes",
                "usedBytes",
                "freeBytes",
                "scannedAt",
                "generation",
                "policyDigest",
                "capacitySegments",
                "categories",
                "projectCandidates",
                "quarantines",
                "blockedItemCount",
                "guardedScopes",
            },
        )
        endpoint = self._endpoint(node_id)
        policy_digest = _text(
            data["policyDigest"],
            maximum=64,
            pattern=_SAFE_DIGEST,
        )
        if data["nodeId"] != node_id or policy_digest != (
            endpoint.expected_policy_digest
        ):
            raise StorageExecutorError(
                "storage_executor_identity_mismatch",
                "Storage executor identity attestation did not match.",
            )

        raw_segments = data["capacitySegments"]
        raw_categories = data["categories"]
        raw_projects = data["projectCandidates"]
        raw_quarantines = data["quarantines"]
        if (
            not isinstance(raw_segments, list)
            or len(raw_segments) > 2
            or not isinstance(raw_categories, list)
            or len(raw_categories) > 5
            or not isinstance(raw_projects, list)
            or len(raw_projects) > 100
            or not isinstance(raw_quarantines, list)
            or len(raw_quarantines) > 200
        ):
            raise StorageExecutorError(
                "storage_executor_protocol_invalid",
                "Storage executor inventory exceeded its bounds.",
            )
        try:
            segments: list[StorageCapacitySegment] = []
            for raw in raw_segments:
                item = _record(
                    raw,
                    {
                        "kind",
                        "displayName",
                        "displaySize",
                        "capacityBytes",
                        "readOnly",
                    },
                )
                if (
                    item["kind"] not in {"root-lv", "vg-unallocated"}
                    or _boolean(item["readOnly"]) is not True
                ):
                    raise ValueError("invalid capacity segment")
                segments.append(
                    StorageCapacitySegment(
                        kind=item["kind"],
                        display_name=_text(
                            item["displayName"],
                            maximum=120,
                        ),
                        display_size=_text(
                            item["displaySize"],
                            maximum=32,
                        ),
                        capacity_bytes=_integer(item["capacityBytes"]),
                    )
                )
            categories: list[StorageCategoryInventory] = []
            for raw in raw_categories:
                item = _record(
                    raw,
                    {
                        "category",
                        "reclaimableBytes",
                        "itemCount",
                        "oldestItemAt",
                    },
                )
                if item["category"] not in {
                    "build",
                    "cache",
                    "log",
                    "stopped-container",
                }:
                    raise ValueError("invalid cleanup category")
                categories.append(
                    StorageCategoryInventory(
                        category=item["category"],
                        reclaimable_bytes=_integer(
                            item["reclaimableBytes"]
                        ),
                        item_count=_integer(item["itemCount"]),
                        oldest_item_at=(
                            None
                            if item["oldestItemAt"] is None
                            else _integer(item["oldestItemAt"])
                        ),
                    )
                )
            projects: list[StorageProjectCandidate] = []
            for raw in raw_projects:
                item = _record(
                    raw,
                    {
                        "projectId",
                        "displayName",
                        "sizeBytes",
                        "lastModifiedAt",
                    },
                )
                projects.append(
                    StorageProjectCandidate(
                        project_id=_text(
                            item["projectId"],
                            maximum=160,
                            pattern=_SAFE_PROJECT,
                        ),
                        display_name=_text(
                            item["displayName"],
                            maximum=120,
                        ),
                        size_bytes=_integer(item["sizeBytes"]),
                        last_modified_at=_integer(item["lastModifiedAt"]),
                    )
                )
            quarantines: list[StorageNodeQuarantine] = []
            for raw in raw_quarantines:
                item = _record(
                    raw,
                    {
                        "quarantineId",
                        "projectId",
                        "status",
                        "sizeBytes",
                        "quarantinedAt",
                        "purgeEligibleAt",
                    },
                )
                if item["status"] not in {"retained", "restored", "purged"}:
                    raise ValueError("invalid quarantine status")
                quarantines.append(
                    StorageNodeQuarantine(
                        quarantine_id=_text(
                            item["quarantineId"],
                            maximum=36,
                            pattern=_SAFE_QUARANTINE,
                        ),
                        project_id=_text(
                            item["projectId"],
                            maximum=160,
                            pattern=_SAFE_PROJECT,
                        ),
                        status=item["status"],
                        size_bytes=_integer(item["sizeBytes"]),
                        quarantined_at=_integer(item["quarantinedAt"]),
                        purge_eligible_at=_integer(
                            item["purgeEligibleAt"]
                        ),
                    )
                )
            return StorageNodeInventory(
                node_id=node_id,
                execute_enabled=_boolean(data["executeEnabled"]),
                capacity_bytes=_integer(data["capacityBytes"]),
                used_bytes=_integer(data["usedBytes"]),
                free_bytes=_integer(data["freeBytes"]),
                scanned_at=_integer(data["scannedAt"]),
                generation=_text(
                    data["generation"],
                    maximum=128,
                    pattern=_SAFE_OPAQUE,
                ),
                policy_digest=policy_digest,
                blocked_item_count=_integer(data["blockedItemCount"]),
                capacity_segments=tuple(segments),
                categories=tuple(categories),
                project_candidates=tuple(projects),
                quarantines=tuple(quarantines),
                guarded_scopes=cast(Any, _scopes(data["guardedScopes"])),
            )
        except ValueError as error:
            raise StorageExecutorError(
                "storage_executor_protocol_invalid",
                "Storage executor returned invalid inventory data.",
            ) from error

    def _attest_mutation(self, node_id: StorageNodeId) -> None:
        inventory = self._inventory(node_id)
        if (
            not inventory.execute_enabled
            or inventory.guarded_scopes != REQUIRED_STORAGE_GUARDS
        ):
            raise StorageExecutorError(
                "storage_node_execution_disabled",
                "Storage executor mutation evidence is incomplete.",
            )

    def inventory(self, node_id: StorageNodeId) -> StorageNodeInventory:
        return self._inventory(node_id)

    def preview(
        self,
        command: StoragePreviewCommand,
    ) -> StorageExecutorPreview:
        self._attest_mutation(command.node_id)
        data = _record(
            self._request(
                command.node_id,
                {
                    "kind": "preview",
                    "nodeId": command.node_id,
                    "category": (
                        command.category
                        if command.operation_kind == "cleanup"
                        else None
                    ),
                    "operationKind": command.operation_kind,
                    "projectId": command.project_id,
                    "quarantineId": command.quarantine_id,
                },
                expected_kind="preview",
            ),
            {
                "executorPreviewRef",
                "nodeGeneration",
                "candidateCount",
                "reclaimableBytes",
                "protectedItemCount",
                "guardedScopes",
                "confirmation",
                "expiresAt",
                "replayed",
            },
        )
        try:
            if data["confirmation"] not in {
                "CLEANUP",
                "QUARANTINE",
                "RESTORE",
                "PURGE",
            }:
                raise ValueError("invalid confirmation")
            return StorageExecutorPreview(
                executor_preview_ref=_text(
                    data["executorPreviewRef"],
                    maximum=192,
                    pattern=_SAFE_OPAQUE,
                ),
                node_generation=_text(
                    data["nodeGeneration"],
                    maximum=128,
                    pattern=_SAFE_OPAQUE,
                ),
                candidate_count=_integer(data["candidateCount"]),
                reclaimable_bytes=_integer(data["reclaimableBytes"]),
                protected_item_count=_integer(
                    data["protectedItemCount"]
                ),
                guarded_scopes=cast(Any, _scopes(data["guardedScopes"])),
                confirmation=data["confirmation"],
                expires_at=_integer(data["expiresAt"]),
                replayed=_boolean(data["replayed"]),
            )
        except ValueError as error:
            raise StorageExecutorError(
                "storage_executor_protocol_invalid",
                "Storage executor returned invalid preview data.",
            ) from error

    def _operation_result(self, data: dict[str, Any]) -> StorageExecutorResult:
        item = _record(
            data,
            {
                "operationId",
                "previewRef",
                "status",
                "affectedItemCount",
                "reclaimedBytes",
                "protectedItemCount",
                "guardedScopes",
                "nodeGeneration",
                "quarantineId",
                "errorCode",
                "createdAt",
                "completedAt",
                "replayed",
            },
        )
        try:
            if item["status"] not in {"applying", "succeeded", "failed"}:
                raise ValueError("invalid operation status")
            return StorageExecutorResult(
                operation_id=_text(
                    item["operationId"],
                    maximum=36,
                    pattern=_SAFE_OPERATION,
                ),
                executor_preview_ref=_text(
                    item["previewRef"],
                    maximum=192,
                    pattern=_SAFE_OPAQUE,
                ),
                status=item["status"],
                affected_item_count=_integer(item["affectedItemCount"]),
                reclaimed_bytes=_integer(item["reclaimedBytes"]),
                protected_item_count=_integer(
                    item["protectedItemCount"]
                ),
                guarded_scopes=cast(Any, _scopes(item["guardedScopes"])),
                node_generation=_text(
                    item["nodeGeneration"],
                    maximum=128,
                    pattern=_SAFE_OPAQUE,
                ),
                quarantine_id=_nullable_text(
                    item["quarantineId"],
                    maximum=36,
                    pattern=_SAFE_QUARANTINE,
                ),
                error_code=_nullable_text(
                    item["errorCode"],
                    maximum=128,
                    pattern=_SAFE_ERROR,
                ),
                created_at=_integer(item["createdAt"]),
                completed_at=(
                    None
                    if item["completedAt"] is None
                    else _integer(item["completedAt"])
                ),
                replayed=_boolean(item["replayed"]),
            )
        except ValueError as error:
            raise StorageExecutorError(
                "storage_executor_protocol_invalid",
                "Storage executor returned invalid operation data.",
            ) from error

    def execute(
        self,
        command: StorageExecuteCommand,
    ) -> StorageExecutorResult:
        self._attest_mutation(command.node_id)
        return self._operation_result(
            self._request(
                command.node_id,
                {
                    "kind": "execute",
                    "operationId": command.operation_id,
                    "previewRef": command.executor_preview_ref,
                    "nodeGeneration": command.node_generation,
                    "projectId": command.project_id,
                    "quarantineId": command.quarantine_id,
                },
                expected_kind="operation",
            )
        )

    def status(
        self,
        command: StorageStatusCommand,
    ) -> StorageExecutorResult:
        # Status is non-mutating. It still performs a signed-inventory identity
        # attestation, but remains available when current execution is disabled.
        self._inventory(command.node_id)
        return self._operation_result(
            self._request(
                command.node_id,
                {"kind": "status", "operationId": command.operation_id},
                expected_kind="operation",
            )
        )


def build_storage_node_executor(
    settings: Any,
    *,
    transport: StorageWireTransport | None = None,
) -> StorageNodeExecutor:
    if settings.storage_executor_enabled is not True:
        return UnavailableStorageNodeExecutor()
    endpoint = StorageExecutorEndpoint(
        node_id="home",
        socket_path=settings.storage_executor_home_socket_path,
        expected_executable_path=(
            settings.storage_executor_home_executable_path
        ),
        expected_policy_path=settings.storage_executor_home_policy_path,
        expected_policy_digest=(
            settings.storage_executor_home_policy_digest
        ),
    )
    return RustStorageNodeExecutor(
        endpoints={"home": endpoint},
        transport=transport,
        protocol_version=settings.storage_executor_protocol_version,
        timeout_seconds=settings.storage_executor_timeout_seconds,
        max_request_bytes=settings.storage_executor_max_request_bytes,
        max_response_bytes=settings.storage_executor_max_response_bytes,
    )


__all__ = [
    "EXECUTABLE_PATH",
    "HOME_SOCKET_PATH",
    "POLICY_PATH",
    "PROTOCOL_VERSION",
    "RustStorageNodeExecutor",
    "StorageExecutorEndpoint",
    "StorageWireTransport",
    "UnixSocketStorageTransport",
    "build_storage_node_executor",
]
