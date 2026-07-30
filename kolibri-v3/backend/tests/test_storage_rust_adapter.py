from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path

import pytest

from app.config import Settings
from app.storage_node_executor import (
    REQUIRED_STORAGE_GUARDS,
    StorageExecuteCommand,
    StorageExecutorError,
    StorageExecutorUnavailable,
    StoragePreviewCommand,
    StorageStatusCommand,
    UnavailableStorageNodeExecutor,
)
from app.storage_node_rust_adapter import (
    EXECUTABLE_PATH,
    HOME_SOCKET_PATH,
    POLICY_PATH,
    RustStorageNodeExecutor,
    StorageExecutorEndpoint,
    build_storage_node_executor,
)


POLICY_DIGEST = "b" * 64


class FakeStorageTransport:
    def __init__(
        self,
        *,
        policy_digest: str = POLICY_DIGEST,
        execute_enabled: bool = True,
        guards: list[str] | None = None,
    ) -> None:
        self.policy_digest = policy_digest
        self.execute_enabled = execute_enabled
        self.guards = (
            list(REQUIRED_STORAGE_GUARDS)
            if guards is None
            else guards
        )
        self.commands: list[dict[str, object]] = []

    def exchange(
        self,
        *,
        socket_path: Path,
        request: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> bytes:
        assert socket_path == HOME_SOCKET_PATH
        assert timeout_seconds == 2.0
        assert max_response_bytes == 262_144
        envelope = json.loads(request.decode("utf-8"))
        assert set(envelope) == {
            "protocolVersion",
            "requestId",
            "command",
        }
        assert envelope["protocolVersion"] == "v1"
        command = envelope["command"]
        assert isinstance(command, dict)
        self.commands.append(command)
        now = int(time.time())
        kind = command["kind"]
        if kind == "inventory":
            result_kind = "inventory"
            data = {
                "nodeId": "home",
                "executeEnabled": self.execute_enabled,
                "capacityBytes": 1_000_000,
                "usedBytes": 700_000,
                "freeBytes": 300_000,
                "scannedAt": now,
                "generation": "home:generation-1",
                "policyDigest": self.policy_digest,
                "capacitySegments": [
                    {
                        "kind": "root-lv",
                        "displayName": "Корневой LV",
                        "displaySize": "210 GiB",
                        "capacityBytes": 225_485_783_040,
                        "readOnly": True,
                    },
                    {
                        "kind": "vg-unallocated",
                        "displayName": "Резерв VG",
                        "displaySize": "19.83 GiB",
                        "capacityBytes": 21_292_300_370,
                        "readOnly": True,
                    },
                ],
                "categories": [
                    {
                        "category": "cache",
                        "reclaimableBytes": 100_000,
                        "itemCount": 10,
                        "oldestItemAt": now - 1_000,
                    }
                ],
                "projectCandidates": [],
                "quarantines": [],
                "blockedItemCount": 0,
                "guardedScopes": self.guards,
            }
        elif kind == "preview":
            result_kind = "preview"
            operation_kind = str(command["operationKind"])
            data = {
                "executorPreviewRef": "spx_preview-1",
                "nodeGeneration": "home:generation-1",
                "candidateCount": 1,
                "reclaimableBytes": 250_000,
                "protectedItemCount": 0,
                "guardedScopes": list(REQUIRED_STORAGE_GUARDS),
                "confirmation": {
                    "cleanup": "CLEANUP",
                    "quarantine": "QUARANTINE",
                    "restore": "RESTORE",
                    "purge": "PURGE",
                }[operation_kind],
                "expiresAt": now + 900,
                "replayed": False,
            }
        else:
            assert kind in {"execute", "status"}
            result_kind = "operation"
            data = {
                "operationId": command["operationId"],
                "previewRef": "spx_preview-1",
                "status": "succeeded",
                "affectedItemCount": 1,
                "reclaimedBytes": 0,
                "protectedItemCount": 0,
                "guardedScopes": list(REQUIRED_STORAGE_GUARDS),
                "nodeGeneration": "home:generation-2",
                "quarantineId": "sqn_" + ("c" * 32),
                "errorCode": None,
                "createdAt": now,
                "completedAt": now,
                "replayed": kind == "status",
            }
        response = {
            "protocolVersion": "v1",
            "requestId": envelope["requestId"],
            "ok": True,
            "result": {"kind": result_kind, "data": data},
        }
        return (
            json.dumps(response, separators=(",", ":")).encode("utf-8")
            + b"\n"
        )


def _endpoint(digest: str = POLICY_DIGEST) -> StorageExecutorEndpoint:
    return StorageExecutorEndpoint(
        node_id="home",
        socket_path=HOME_SOCKET_PATH,
        expected_executable_path=EXECUTABLE_PATH,
        expected_policy_path=POLICY_PATH,
        expected_policy_digest=digest,
    )


def _adapter(transport: FakeStorageTransport) -> RustStorageNodeExecutor:
    return RustStorageNodeExecutor(
        endpoints={"home": _endpoint()},
        transport=transport,
    )


def test_storage_executor_default_is_disabled_and_opt_in_is_exact(
    tmp_path: Path,
) -> None:
    settings = Settings.for_testing(database_url=tmp_path / "default.db")
    assert isinstance(
        build_storage_node_executor(settings),
        UnavailableStorageNodeExecutor,
    )

    with pytest.raises(ValueError, match="requires an exact Home identity"):
        replace(settings, storage_executor_enabled=True)
    with pytest.raises(ValueError, match="Home identity is invalid"):
        replace(
            settings,
            storage_executor_home_socket_path=Path("/tmp/executor.sock"),
            storage_executor_home_executable_path=EXECUTABLE_PATH,
            storage_executor_home_policy_path=POLICY_PATH,
            storage_executor_home_policy_digest=POLICY_DIGEST,
        )
    enabled = replace(
        settings,
        storage_executor_enabled=True,
        storage_executor_home_socket_path=HOME_SOCKET_PATH,
        storage_executor_home_executable_path=EXECUTABLE_PATH,
        storage_executor_home_policy_path=POLICY_PATH,
        storage_executor_home_policy_digest=POLICY_DIGEST,
    )
    assert isinstance(
        build_storage_node_executor(
            enabled,
            transport=FakeStorageTransport(),
        ),
        RustStorageNodeExecutor,
    )


def test_rust_adapter_maps_v1_restore_execute_and_status_without_shell() -> None:
    transport = FakeStorageTransport()
    adapter = _adapter(transport)
    inventory = adapter.inventory("home")
    assert inventory.policy_digest == POLICY_DIGEST
    assert inventory.guarded_scopes == REQUIRED_STORAGE_GUARDS

    quarantine_id = "sqn_" + ("c" * 32)
    preview = adapter.preview(
        StoragePreviewCommand(
            node_id="home",
            category="project-quarantine",
            operation_kind="restore",
            project_id=None,
            quarantine_id=quarantine_id,
            guarded_scopes=REQUIRED_STORAGE_GUARDS,
        )
    )
    assert preview.confirmation == "RESTORE"
    assert transport.commands[-1] == {
        "kind": "preview",
        "nodeId": "home",
        "category": None,
        "operationKind": "restore",
        "projectId": None,
        "quarantineId": quarantine_id,
    }

    operation_id = "sop_" + ("d" * 32)
    executed = adapter.execute(
        StorageExecuteCommand(
            operation_id=operation_id,
            node_id="home",
            category="project-quarantine",
            operation_kind="restore",
            executor_preview_ref="spx_preview-1",
            node_generation="home:generation-1",
            project_id=None,
            quarantine_id=quarantine_id,
            purge_eligible_at=None,
            guarded_scopes=REQUIRED_STORAGE_GUARDS,
        )
    )
    assert executed.operation_id == operation_id
    assert executed.quarantine_id == quarantine_id
    assert transport.commands[-1] == {
        "kind": "execute",
        "operationId": operation_id,
        "previewRef": "spx_preview-1",
        "nodeGeneration": "home:generation-1",
        "projectId": None,
        "quarantineId": quarantine_id,
    }

    status = adapter.status(
        StorageStatusCommand(operation_id=operation_id, node_id="home")
    )
    assert status.replayed is True
    assert [command["kind"] for command in transport.commands[-2:]] == [
        "inventory",
        "status",
    ]
    assert transport.commands[-1] == {
        "kind": "status",
        "operationId": operation_id,
    }


def test_rust_adapter_requires_attested_policy_and_mutation_guards() -> None:
    mismatch = _adapter(FakeStorageTransport(policy_digest="e" * 64))
    with pytest.raises(
        StorageExecutorError,
        match="storage_executor_identity_mismatch",
    ):
        mismatch.inventory("home")

    disabled_transport = FakeStorageTransport(
        execute_enabled=False,
        guards=[],
    )
    disabled = _adapter(disabled_transport)
    with pytest.raises(
        StorageExecutorError,
        match="storage_node_execution_disabled",
    ):
        disabled.preview(
            StoragePreviewCommand(
                node_id="home",
                category="cache",
                operation_kind="cleanup",
                project_id=None,
                quarantine_id=None,
                guarded_scopes=REQUIRED_STORAGE_GUARDS,
            )
        )
    assert [command["kind"] for command in disabled_transport.commands] == [
        "inventory"
    ]

    with pytest.raises(StorageExecutorUnavailable):
        disabled.inventory("primary")
