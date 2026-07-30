from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.database import connect_database
from app.main import create_app
from app.owner_bootstrap import promote_registered_owner
from app.storage_node_executor import (
    REQUIRED_STORAGE_GUARDS,
    CONFIGURED_HOME_CAPACITY_SEGMENTS,
    StorageCategoryInventory,
    StorageExecuteCommand,
    StorageExecutorError,
    StorageExecutorPreview,
    StorageExecutorResult,
    StorageNodeInventory,
    StoragePreviewCommand,
    StorageProjectCandidate,
    StorageStatusCommand,
)


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"


def _register(client: TestClient, email: str, name: str) -> dict[str, object]:
    response = client.post(
        "/v1/auth/register",
        headers=ORIGIN,
        json={"email": email, "name": name, "password": PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["user"]


def _logout(client: TestClient) -> None:
    csrf = str(client.cookies.get("kolibri_v3_csrf"))
    response = client.post(
        "/v1/auth/logout",
        headers={**ORIGIN, "X-CSRF-Token": csrf},
    )
    assert response.status_code == 200


def _mutation_headers(client: TestClient, key: str) -> dict[str, str]:
    return {
        **ORIGIN,
        "X-CSRF-Token": str(client.cookies.get("kolibri_v3_csrf")),
        "Idempotency-Key": key,
    }


class RecordingStorageExecutor:
    def __init__(self) -> None:
        self.preview_commands: list[StoragePreviewCommand] = []
        self.execute_commands: list[StorageExecuteCommand] = []
        self.status_commands: list[StorageStatusCommand] = []
        self.operation_journal: dict[str, StorageExecutorResult] = {}
        self.protected_preview = False
        self.fail_next_execute = False
        self.unknown_next_execute = False
        self.failed_result_next_execute = False

    def inventory(self, node_id: str) -> StorageNodeInventory:
        return StorageNodeInventory(
            node_id=node_id,
            capacity_bytes=1_000_000,
            used_bytes=700_000,
            free_bytes=300_000,
            scanned_at=1_785_369_600,
            generation=f"{node_id}:generation-1",
            policy_digest="a" * 64,
            blocked_item_count=0,
            execute_enabled=True,
            categories=(
                StorageCategoryInventory(
                    category="build",
                    reclaimable_bytes=20_000,
                    item_count=2,
                    oldest_item_at=1_700_000_000,
                ),
                StorageCategoryInventory(
                    category="cache",
                    reclaimable_bytes=100_000,
                    item_count=10,
                    oldest_item_at=1_700_000_000,
                ),
                StorageCategoryInventory(
                    category="log",
                    reclaimable_bytes=5_000,
                    item_count=5,
                    oldest_item_at=1_700_000_000,
                ),
                StorageCategoryInventory(
                    category="stopped-container",
                    reclaimable_bytes=50_000,
                    item_count=1,
                    oldest_item_at=1_700_000_000,
                ),
            ),
            capacity_segments=(
                CONFIGURED_HOME_CAPACITY_SEGMENTS
                if node_id == "home"
                else ()
            ),
            project_candidates=(
                StorageProjectCandidate(
                    project_id="old-project",
                    display_name="Old project",
                    size_bytes=250_000,
                    last_modified_at=1_700_000_000,
                ),
                StorageProjectCandidate(
                    project_id="authoritative-project",
                    display_name="Authoritative project",
                    size_bytes=900_000,
                    last_modified_at=1_700_000_000,
                ),
            ),
        )

    def preview(
        self,
        command: StoragePreviewCommand,
    ) -> StorageExecutorPreview:
        self.preview_commands.append(command)
        project_operation = command.operation_kind in {
            "quarantine",
            "restore",
            "purge",
        }
        return StorageExecutorPreview(
            executor_preview_ref=f"preview:{len(self.preview_commands)}",
            node_generation=f"{command.node_id}:generation-1",
            candidate_count=1 if project_operation else 10,
            reclaimable_bytes=250_000 if project_operation else 100_000,
            protected_item_count=1 if self.protected_preview else 0,
            guarded_scopes=REQUIRED_STORAGE_GUARDS,
            confirmation={
                "cleanup": "CLEANUP",
                "quarantine": "QUARANTINE",
                "restore": "RESTORE",
                "purge": "PURGE",
            }[command.operation_kind],
            expires_at=int(time.time()) + 900,
            replayed=False,
        )

    def execute(
        self,
        command: StorageExecuteCommand,
    ) -> StorageExecutorResult:
        self.execute_commands.append(command)
        if self.fail_next_execute:
            self.fail_next_execute = False
            raise StorageExecutorError(
                "storage_executor_definitive_failure",
                "definitive test failure",
            )
        now = int(time.time())
        result = StorageExecutorResult(
            operation_id=command.operation_id,
            executor_preview_ref=command.executor_preview_ref,
            status=(
                "failed"
                if self.failed_result_next_execute
                else "succeeded"
            ),
            affected_item_count=(
                0
                if self.failed_result_next_execute
                else (
                    1
                    if command.operation_kind
                    in {"quarantine", "restore", "purge"}
                    else 10
                )
            ),
            reclaimed_bytes=(
                0
                if self.failed_result_next_execute
                or command.operation_kind in {"quarantine", "restore"}
                else (
                    250_000
                    if command.operation_kind == "purge"
                    else 100_000
                )
            ),
            protected_item_count=0,
            guarded_scopes=REQUIRED_STORAGE_GUARDS,
            node_generation=f"{command.node_id}:generation-2",
            quarantine_id=command.quarantine_id,
            error_code=(
                "storage_executor_journaled_failure"
                if self.failed_result_next_execute
                else None
            ),
            created_at=now,
            completed_at=now,
            replayed=False,
        )
        self.failed_result_next_execute = False
        self.operation_journal[command.operation_id] = result
        if self.unknown_next_execute:
            self.unknown_next_execute = False
            raise RuntimeError("ambiguous transport failure")
        return result

    def status(
        self,
        command: StorageStatusCommand,
    ) -> StorageExecutorResult:
        self.status_commands.append(command)
        result = self.operation_journal.get(command.operation_id)
        if result is None:
            raise StorageExecutorError(
                "operation_not_found",
                "test operation was not journaled",
            )
        return StorageExecutorResult(
            operation_id=result.operation_id,
            executor_preview_ref=result.executor_preview_ref,
            status=result.status,
            affected_item_count=result.affected_item_count,
            reclaimed_bytes=result.reclaimed_bytes,
            protected_item_count=result.protected_item_count,
            guarded_scopes=result.guarded_scopes,
            node_generation=result.node_generation,
            quarantine_id=result.quarantine_id,
            error_code=result.error_code,
            created_at=result.created_at,
            completed_at=result.completed_at,
            replayed=True,
        )


def _seed_authoritative_project(
    database_path: Path,
    *,
    owner: dict[str, object],
) -> None:
    database = connect_database(database_path)
    try:
        database.execute(
            """
            INSERT INTO projects (
                tenant_id, id, created_by_user_id, title, status,
                primary_thread_id, created_at, updated_at
            ) VALUES (?, 'authoritative-project', ?, 'Live project', 'active',
                      'thread-authoritative', ?, ?)
            """,
            (
                owner["tenantId"],
                owner["id"],
                "2026-07-30T00:00:00+00:00",
                "2026-07-30T00:00:00+00:00",
            ),
        )
    finally:
        database.close()


def test_storage_default_executor_fails_closed_and_owner_role_is_not_authority(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "storage-default.db"
    settings = Settings.for_testing(database_url=database_path)
    app = create_app(settings)

    with TestClient(app) as client:
        role_owner = _register(
            client,
            "role-owner@example.com",
            "Role owner",
        )
        _logout(client)
        _register(client, "owner@example.com", "Owner")
        promote_registered_owner(settings, email="owner@example.com")

        snapshot = client.get("/v1/platform-admin/storage")
        assert snapshot.status_code == 200
        assert snapshot.headers["cache-control"] == "no-store"
        assert [
            (node["id"], node["executorStatus"])
            for node in snapshot.json()["nodes"]
        ] == [("home", "unavailable"), ("primary", "unavailable")]
        assert all(
            node["protectedScopes"] == list(REQUIRED_STORAGE_GUARDS)
            for node in snapshot.json()["nodes"]
        )
        assert snapshot.json()["nodes"][0]["capacitySegments"] == [
            {
                "kind": "root-lv",
                "displayName": "Корневой LV",
                "displaySize": "210 GiB",
                "capacityBytes": 225_485_783_040,
                "readOnly": True,
            },
            {
                "kind": "vg-unallocated",
                "displayName": "Нераспределённый резерв VG",
                "displaySize": "19.83 GiB",
                "capacityBytes": 21_292_300_370,
                "readOnly": True,
            },
        ]

        unavailable = client.post(
            "/v1/platform-admin/storage/previews",
            headers=_mutation_headers(client, "storage-preview-default-0001"),
            json={
                "nodeId": "home",
                "category": "cache",
                "operationKind": "cleanup",
            },
        )
        assert unavailable.status_code == 503
        assert (
            unavailable.json()["code"]
            == "storage_node_executor_unavailable"
        )

        _logout(client)
        database = connect_database(database_path)
        try:
            database.execute(
                """
                UPDATE users
                SET role = 'owner'
                WHERE id = ? AND tenant_id = ?
                """,
                (role_owner["id"], role_owner["tenantId"]),
            )
        finally:
            database.close()
        login = client.post(
            "/v1/auth/login",
            headers=ORIGIN,
            json={
                "email": "role-owner@example.com",
                "password": PASSWORD,
            },
        )
        assert login.status_code == 200
        denied = client.get("/v1/platform-admin/storage")
        assert denied.status_code == 403
        assert denied.json()["code"] == "owner_required"


def test_storage_mutations_require_csrf_and_recent_owner_auth(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "storage-mutation-security.db"
    settings = Settings.for_testing(database_url=database_path)
    executor = RecordingStorageExecutor()

    with TestClient(
        create_app(settings, storage_node_executor=executor)
    ) as client:
        owner = _register(client, "owner@example.com", "Owner")
        promote_registered_owner(settings, email="owner@example.com")

        missing_csrf = client.post(
            "/v1/platform-admin/storage/previews",
            headers={
                **ORIGIN,
                "Idempotency-Key": "storage-preview-missing-csrf-0001",
            },
            json={
                "nodeId": "home",
                "category": "cache",
                "operationKind": "cleanup",
            },
        )
        assert missing_csrf.status_code == 403
        assert missing_csrf.json()["code"] == "csrf_token_required"
        assert executor.preview_commands == []

        preview = client.post(
            "/v1/platform-admin/storage/previews",
            headers=_mutation_headers(
                client,
                "storage-preview-stale-auth-0001",
            ),
            json={
                "nodeId": "home",
                "category": "cache",
                "operationKind": "cleanup",
            },
        )
        assert preview.status_code == 201

        database = sqlite3.connect(database_path)
        try:
            database.execute(
                """
                UPDATE sessions
                SET created_at = unixepoch() - 301
                WHERE user_id = ?
                """,
                (owner["id"],),
            )
            database.commit()
        finally:
            database.close()

        readable = client.get("/v1/platform-admin/storage")
        assert readable.status_code == 200
        stale_auth = client.post(
            "/v1/platform-admin/storage/operations",
            headers=_mutation_headers(
                client,
                "storage-execute-stale-auth-0001",
            ),
            json={
                "previewId": preview.json()["id"],
                "confirmation": "CLEANUP",
            },
        )
        assert stale_auth.status_code == 403
        assert (
            stale_auth.json()["code"]
            == "storage_reauthentication_required"
        )
        assert executor.execute_commands == []


def test_storage_cleanup_requires_preview_guards_and_is_idempotent(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "storage-cleanup.db"
    settings = Settings.for_testing(database_url=database_path)
    executor = RecordingStorageExecutor()
    app = create_app(settings, storage_node_executor=executor)

    with TestClient(app) as client:
        owner = _register(client, "owner@example.com", "Owner")
        promote_registered_owner(settings, email="owner@example.com")
        _seed_authoritative_project(database_path, owner=owner)

        snapshot = client.get("/v1/platform-admin/storage")
        assert snapshot.status_code == 200
        [home, primary] = snapshot.json()["nodes"]
        assert home["displayName"] == "Home"
        assert primary["displayName"] == "Primary"
        assert home["executorStatus"] == "ready"
        assert home["freeBytes"] == 300_000
        assert [segment["displaySize"] for segment in home["capacitySegments"]] == [
            "210 GiB",
            "19.83 GiB",
        ]
        assert home["capacitySource"] == "live-executor"
        assert [item["projectId"] for item in home["projectCandidates"]] == [
            "old-project"
        ]

        preview_key = "storage-preview-cleanup-0001"
        preview_payload = {
            "nodeId": "home",
            "category": "cache",
            "operationKind": "cleanup",
        }
        preview = client.post(
            "/v1/platform-admin/storage/previews",
            headers=_mutation_headers(client, preview_key),
            json=preview_payload,
        )
        assert preview.status_code == 201
        preview_view = preview.json()
        assert preview_view["candidateCount"] == 10
        assert preview_view["reclaimableBytes"] == 100_000
        assert preview_view["protectedItemCount"] == 0
        assert preview_view["confirmation"] == "CLEANUP"
        assert len(executor.preview_commands) == 1
        assert executor.preview_commands[0].guarded_scopes == (
            REQUIRED_STORAGE_GUARDS
        )

        replay = client.post(
            "/v1/platform-admin/storage/previews",
            headers=_mutation_headers(client, preview_key),
            json=preview_payload,
        )
        assert replay.status_code == 201
        assert replay.json()["id"] == preview_view["id"]
        assert replay.json()["replayed"] is True
        assert len(executor.preview_commands) == 1

        conflict = client.post(
            "/v1/platform-admin/storage/previews",
            headers=_mutation_headers(client, preview_key),
            json={
                "nodeId": "primary",
                "category": "cache",
                "operationKind": "cleanup",
            },
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "storage_idempotency_conflict"

        wrong_confirmation = client.post(
            "/v1/platform-admin/storage/operations",
            headers=_mutation_headers(
                client,
                "storage-execute-cleanup-wrong-0001",
            ),
            json={
                "previewId": preview_view["id"],
                "confirmation": "PURGE",
            },
        )
        assert wrong_confirmation.status_code == 422
        assert (
            wrong_confirmation.json()["code"]
            == "storage_confirmation_invalid"
        )

        execute_key = "storage-execute-cleanup-0001"
        execute_payload = {
            "previewId": preview_view["id"],
            "confirmation": "CLEANUP",
        }
        executed = client.post(
            "/v1/platform-admin/storage/operations",
            headers=_mutation_headers(client, execute_key),
            json=execute_payload,
        )
        assert executed.status_code == 200
        operation = executed.json()
        assert operation["status"] == "succeeded"
        assert operation["affectedItemCount"] == 10
        assert operation["reclaimedBytes"] == 100_000
        assert len(executor.execute_commands) == 1
        assert executor.execute_commands[0].executor_preview_ref == "preview:1"

        replayed = client.post(
            "/v1/platform-admin/storage/operations",
            headers=_mutation_headers(client, execute_key),
            json=execute_payload,
        )
        assert replayed.status_code == 200
        assert replayed.json()["id"] == operation["id"]
        assert replayed.json()["replayed"] is True
        assert len(executor.execute_commands) == 1

        refreshed = client.get("/v1/platform-admin/storage").json()
        assert refreshed["recentOperations"][0]["status"] == "succeeded"
        assert [
            item["action"] for item in refreshed["audit"][:2]
        ] == [
            "storage.operation.succeeded",
            "storage.preview.created",
        ]

        executor.protected_preview = True
        unsafe = client.post(
            "/v1/platform-admin/storage/previews",
            headers=_mutation_headers(client, "storage-preview-unsafe-0001"),
            json={
                "nodeId": "home",
                "category": "log",
                "operationKind": "cleanup",
            },
        )
        assert unsafe.status_code == 502
        assert unsafe.json()["code"] == "storage_node_preview_invalid"


def test_pending_operation_resumes_with_same_idempotency_and_failures_stay_closed(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "storage-pending.db"
    settings = Settings.for_testing(database_url=database_path)
    executor = RecordingStorageExecutor()
    app = create_app(settings, storage_node_executor=executor)

    with TestClient(app) as client:
        _register(client, "owner@example.com", "Owner")
        promote_registered_owner(settings, email="owner@example.com")

        preview = client.post(
            "/v1/platform-admin/storage/previews",
            headers=_mutation_headers(
                client,
                "storage-preview-crash-recovery-0001",
            ),
            json={
                "nodeId": "primary",
                "category": "build",
                "operationKind": "cleanup",
            },
        ).json()
        execute_key = "storage-execute-crash-recovery-0001"
        execute_payload = {
            "previewId": preview["id"],
            "confirmation": "CLEANUP",
        }
        operation_id = "sop_" + ("a" * 32)
        canonical_request = json.dumps(
            execute_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        database = connect_database(database_path)
        try:
            preview_row = database.execute(
                """
                SELECT *
                FROM storage_admin_previews
                WHERE id = ?
                """,
                (preview["id"],),
            ).fetchone()
            assert preview_row is not None
            database.execute(
                """
                INSERT INTO storage_admin_operations (
                    id, preview_id, actor_user_id, actor_tenant_id,
                    authority_epoch, idempotency_key_hash, request_hash,
                    status, created_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, 'pending', unixepoch()
                )
                """,
                (
                    operation_id,
                    preview["id"],
                    preview_row["actor_user_id"],
                    preview_row["actor_tenant_id"],
                    preview_row["authority_epoch"],
                    hashlib.sha256(execute_key.encode()).hexdigest(),
                    hashlib.sha256(canonical_request.encode()).hexdigest(),
                ),
            )
            database.execute(
                """
                UPDATE storage_admin_previews
                SET consumed_at = unixepoch()
                WHERE id = ?
                """,
                (preview["id"],),
            )
            [pending] = database.execute(
                """
                SELECT id, status
                FROM storage_admin_operations
                """
            ).fetchall()
            assert pending["status"] == "pending"
            pending_id = str(pending["id"])
            # Simulate: the executor already saw this durable operation ID,
            # then the process stopped before recording its result.
            executor.execute_commands.append(
                StorageExecuteCommand(
                    operation_id=pending_id,
                    node_id="primary",
                    category="build",
                    operation_kind="cleanup",
                    executor_preview_ref=str(
                        preview_row["executor_preview_ref"]
                    ),
                    node_generation=str(preview_row["node_generation"]),
                    project_id=None,
                    quarantine_id=None,
                    purge_eligible_at=None,
                    guarded_scopes=REQUIRED_STORAGE_GUARDS,
                )
            )
        finally:
            database.close()

        resumed = client.post(
            "/v1/platform-admin/storage/operations",
            headers=_mutation_headers(client, execute_key),
            json=execute_payload,
        )
        assert resumed.status_code == 200
        assert resumed.json()["id"] == pending_id
        assert resumed.json()["status"] == "succeeded"
        assert resumed.json()["replayed"] is True
        assert [
            command.operation_id for command in executor.execute_commands
        ] == [pending_id, pending_id]

        failed_preview = client.post(
            "/v1/platform-admin/storage/previews",
            headers=_mutation_headers(
                client,
                "storage-preview-failed-closed-0001",
            ),
            json={
                "nodeId": "primary",
                "category": "log",
                "operationKind": "cleanup",
            },
        ).json()
        failed_key = "storage-execute-failed-closed-0001"
        failed_payload = {
            "previewId": failed_preview["id"],
            "confirmation": "CLEANUP",
        }
        executor.fail_next_execute = True
        failed = client.post(
            "/v1/platform-admin/storage/operations",
            headers=_mutation_headers(client, failed_key),
            json=failed_payload,
        )
        assert failed.status_code == 200
        assert failed.json()["status"] == "pending"
        assert (
            failed.json()["errorCode"]
            == "storage_executor_definitive_failure"
        )
        execute_count = len(executor.execute_commands)

        status_only = client.post(
            "/v1/platform-admin/storage/operations/reconcile",
            headers={
                **ORIGIN,
                "X-CSRF-Token": str(
                    client.cookies.get("kolibri_v3_csrf")
                ),
            },
            json={"operationId": failed.json()["id"]},
        )
        assert status_only.status_code == 200
        assert status_only.json()["status"] == "pending"
        assert status_only.json()["reconciled"] is True
        assert status_only.json()["errorCode"] == "operation_not_found"
        assert len(executor.execute_commands) == execute_count

        journal_preview = client.post(
            "/v1/platform-admin/storage/previews",
            headers=_mutation_headers(
                client,
                "storage-preview-journal-failed-0001",
            ),
            json={
                "nodeId": "primary",
                "category": "log",
                "operationKind": "cleanup",
            },
        ).json()
        executor.failed_result_next_execute = True
        journal_failed = client.post(
            "/v1/platform-admin/storage/operations",
            headers=_mutation_headers(
                client,
                "storage-execute-journal-failed-0001",
            ),
            json={
                "previewId": journal_preview["id"],
                "confirmation": "CLEANUP",
            },
        )
        assert journal_failed.status_code == 200
        assert journal_failed.json()["status"] == "failed"
        assert (
            journal_failed.json()["errorCode"]
            == "storage_executor_journaled_failure"
        )

        unknown_preview = client.post(
            "/v1/platform-admin/storage/previews",
            headers=_mutation_headers(
                client,
                "storage-preview-outcome-unknown-0001",
            ),
            json={
                "nodeId": "primary",
                "category": "cache",
                "operationKind": "cleanup",
            },
        ).json()
        unknown_key = "storage-execute-outcome-unknown-0001"
        unknown_payload = {
            "previewId": unknown_preview["id"],
            "confirmation": "CLEANUP",
        }
        executor.unknown_next_execute = True
        unknown = client.post(
            "/v1/platform-admin/storage/operations",
            headers=_mutation_headers(client, unknown_key),
            json=unknown_payload,
        )
        assert unknown.status_code == 200
        assert unknown.json()["status"] == "pending"
        assert (
            unknown.json()["errorCode"]
            == "storage_node_outcome_unknown"
        )
        unknown_operation_id = unknown.json()["id"]

        reconciled = client.post(
            "/v1/platform-admin/storage/operations/reconcile",
            headers={
                **ORIGIN,
                "X-CSRF-Token": str(
                    client.cookies.get("kolibri_v3_csrf")
                ),
            },
            json={"operationId": unknown_operation_id},
        )
        assert reconciled.status_code == 200
        assert reconciled.json()["id"] == unknown_operation_id
        assert reconciled.json()["status"] == "succeeded"
        assert reconciled.json()["reconciled"] is True
        assert executor.status_commands[-1].operation_id == (
            unknown_operation_id
        )
        assert [
            command.operation_id
            for command in executor.execute_commands
            if command.operation_id == unknown_operation_id
        ] == [unknown_operation_id]

        database = connect_database(database_path)
        try:
            assert database.execute(
                """
                SELECT COUNT(*)
                FROM storage_admin_audit_events
                WHERE operation_id = ?
                  AND action = 'storage.operation.failed'
                """,
                (unknown_operation_id,),
            ).fetchone()[0] == 0
        finally:
            database.close()


def test_outcome_unknown_restart_with_unavailable_executor_stays_pending(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "storage-restart-unavailable.db"
    settings = Settings.for_testing(database_url=database_path)
    executor = RecordingStorageExecutor()
    execute_key = "storage-execute-restart-unavailable-0001"

    with TestClient(
        create_app(settings, storage_node_executor=executor)
    ) as client:
        _register(client, "owner@example.com", "Owner")
        promote_registered_owner(settings, email="owner@example.com")
        preview = client.post(
            "/v1/platform-admin/storage/previews",
            headers=_mutation_headers(
                client,
                "storage-preview-restart-unavailable-0001",
            ),
            json={
                "nodeId": "primary",
                "category": "cache",
                "operationKind": "cleanup",
            },
        ).json()
        execute_payload = {
            "previewId": preview["id"],
            "confirmation": "CLEANUP",
        }
        executor.unknown_next_execute = True
        unknown = client.post(
            "/v1/platform-admin/storage/operations",
            headers=_mutation_headers(client, execute_key),
            json=execute_payload,
        )
        assert unknown.status_code == 200
        assert unknown.json()["status"] == "pending"
        unknown_operation_id = unknown.json()["id"]

    # A restarted process has no evidence about the prior node-side attempt.
    # Its default unavailable adapter must not turn that ambiguity into a
    # terminal failed record.
    with TestClient(create_app(settings)) as restarted_client:
        login = restarted_client.post(
            "/v1/auth/login",
            headers=ORIGIN,
            json={
                "email": "owner@example.com",
                "password": PASSWORD,
            },
        )
        assert login.status_code == 200
        retried = restarted_client.post(
            "/v1/platform-admin/storage/operations/reconcile",
            headers={
                **ORIGIN,
                "X-CSRF-Token": str(
                    restarted_client.cookies.get("kolibri_v3_csrf")
                ),
            },
            json={"operationId": unknown_operation_id},
        )
        assert retried.status_code == 200
        assert retried.json()["id"] == unknown_operation_id
        assert retried.json()["status"] == "pending"
        assert retried.json()["reconciled"] is True
        assert (
            retried.json()["errorCode"]
            == "storage_node_executor_unavailable"
        )

    database = connect_database(database_path)
    try:
        row = database.execute(
            """
            SELECT status, error_code
            FROM storage_admin_operations
            WHERE id = ?
            """,
            (unknown_operation_id,),
        ).fetchone()
        assert row is not None
        assert row["status"] == "pending"
        assert row["error_code"] == "storage_node_executor_unavailable"
        assert database.execute(
            """
            SELECT COUNT(*)
            FROM storage_admin_audit_events
            WHERE operation_id = ?
              AND action = 'storage.operation.failed'
            """,
            (unknown_operation_id,),
        ).fetchone()[0] == 0
    finally:
        database.close()


def test_storage_preview_is_fenced_by_platform_authority_epoch(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "storage-authority-epoch.db"
    settings = Settings.for_testing(database_url=database_path)
    executor = RecordingStorageExecutor()
    app = create_app(settings, storage_node_executor=executor)

    with TestClient(app) as client:
        _register(client, "owner@example.com", "Owner")
        promote_registered_owner(settings, email="owner@example.com")
        preview = client.post(
            "/v1/platform-admin/storage/previews",
            headers=_mutation_headers(
                client,
                "storage-preview-authority-0001",
            ),
            json={
                "nodeId": "home",
                "category": "cache",
                "operationKind": "cleanup",
            },
        )
        assert preview.status_code == 201

        database = connect_database(database_path)
        try:
            database.execute(
                """
                UPDATE platform_authority_grants
                SET authority_epoch = authority_epoch + 1,
                    updated_at = unixepoch()
                WHERE authority_id = 'platform_owner'
                """
            )
        finally:
            database.close()

        stale = client.post(
            "/v1/platform-admin/storage/operations",
            headers=_mutation_headers(
                client,
                "storage-execute-authority-0001",
            ),
            json={
                "previewId": preview.json()["id"],
                "confirmation": "CLEANUP",
            },
        )
        assert stale.status_code == 409
        assert (
            stale.json()["code"]
            == "storage_preview_authority_changed"
        )
        assert executor.execute_commands == []


def test_project_cleanup_is_two_phase_and_rejects_client_paths(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "storage-quarantine.db"
    settings = Settings.for_testing(database_url=database_path)
    executor = RecordingStorageExecutor()
    app = create_app(settings, storage_node_executor=executor)

    with TestClient(app) as client:
        owner = _register(client, "owner@example.com", "Owner")
        promote_registered_owner(settings, email="owner@example.com")
        _seed_authoritative_project(database_path, owner=owner)

        authoritative = client.post(
            "/v1/platform-admin/storage/previews",
            headers=_mutation_headers(
                client,
                "storage-preview-authoritative-0001",
            ),
            json={
                "nodeId": "home",
                "category": "project-quarantine",
                "operationKind": "quarantine",
                "projectId": "authoritative-project",
            },
        )
        assert authoritative.status_code == 409
        assert (
            authoritative.json()["code"]
            == "authoritative_project_protected"
        )

        for injected in (
            {
                "nodeId": "home",
                "category": "cache",
                "operationKind": "cleanup",
                "path": "/srv/releases/current",
            },
            {
                "nodeId": "home",
                "category": "project-quarantine",
                "operationKind": "quarantine",
                "projectId": "../../current",
            },
            {
                "nodeId": "home",
                "category": "shell",
                "operationKind": "cleanup",
                "command": "rm -rf /",
            },
            {
                "nodeId": "home",
                "category": "project-quarantine",
                "operationKind": "restore",
                "quarantineId": "sqn_" + ("a" * 31) + "g",
            },
        ):
            rejected = client.post(
                "/v1/platform-admin/storage/previews",
                headers=_mutation_headers(
                    client,
                    f"storage-injection-{len(str(injected)):04d}",
                ),
                json=injected,
            )
            assert rejected.status_code == 422
            assert rejected.json()["code"] == "invalid_request"

        invalid_reconcile = client.post(
            "/v1/platform-admin/storage/operations/reconcile",
            headers={
                **ORIGIN,
                "X-CSRF-Token": str(
                    client.cookies.get("kolibri_v3_csrf")
                ),
            },
            json={"operationId": "sop_" + ("a" * 31) + "G"},
        )
        assert invalid_reconcile.status_code == 422
        assert invalid_reconcile.json()["code"] == "invalid_request"
        assert executor.status_commands == []

        quarantine_preview = client.post(
            "/v1/platform-admin/storage/previews",
            headers=_mutation_headers(
                client,
                "storage-preview-quarantine-0001",
            ),
            json={
                "nodeId": "home",
                "category": "project-quarantine",
                "operationKind": "quarantine",
                "projectId": "old-project",
            },
        )
        assert quarantine_preview.status_code == 201
        preview = quarantine_preview.json()
        assert preview["confirmation"] == "QUARANTINE"

        quarantined = client.post(
            "/v1/platform-admin/storage/operations",
            headers=_mutation_headers(
                client,
                "storage-execute-quarantine-0001",
            ),
            json={
                "previewId": preview["id"],
                "confirmation": "QUARANTINE",
            },
        )
        assert quarantined.status_code == 200
        quarantine_operation = quarantined.json()
        assert quarantine_operation["status"] == "succeeded"
        quarantine_id = quarantine_operation["quarantineId"]
        assert quarantine_id.startswith("sqn_")
        assert executor.execute_commands[-1].quarantine_id == quarantine_id
        assert executor.execute_commands[-1].purge_eligible_at is not None

        restore_preview = client.post(
            "/v1/platform-admin/storage/previews",
            headers=_mutation_headers(
                client,
                "storage-preview-restore-ready-0001",
            ),
            json={
                "nodeId": "home",
                "category": "project-quarantine",
                "operationKind": "restore",
                "quarantineId": quarantine_id,
            },
        )
        assert restore_preview.status_code == 201
        assert restore_preview.json()["confirmation"] == "RESTORE"
        restored = client.post(
            "/v1/platform-admin/storage/operations",
            headers=_mutation_headers(
                client,
                "storage-execute-restore-ready-0001",
            ),
            json={
                "previewId": restore_preview.json()["id"],
                "confirmation": "RESTORE",
            },
        )
        assert restored.status_code == 200
        assert restored.json()["status"] == "succeeded"
        assert restored.json()["reclaimedBytes"] == 0
        assert executor.execute_commands[-1].project_id is None
        assert executor.execute_commands[-1].quarantine_id == quarantine_id
        restored_snapshot = client.get(
            "/v1/platform-admin/storage"
        ).json()
        restored_item = next(
            item
            for item in restored_snapshot["nodes"][0]["quarantines"]
            if item["id"] == quarantine_id
        )
        assert restored_item["status"] == "restored"
        assert restored_item["restoredAt"] is not None

        second_quarantine_preview = client.post(
            "/v1/platform-admin/storage/previews",
            headers=_mutation_headers(
                client,
                "storage-preview-quarantine-second-0001",
            ),
            json={
                "nodeId": "home",
                "category": "project-quarantine",
                "operationKind": "quarantine",
                "projectId": "old-project",
            },
        )
        assert second_quarantine_preview.status_code == 201
        second_quarantine = client.post(
            "/v1/platform-admin/storage/operations",
            headers=_mutation_headers(
                client,
                "storage-execute-quarantine-second-0001",
            ),
            json={
                "previewId": second_quarantine_preview.json()["id"],
                "confirmation": "QUARANTINE",
            },
        )
        assert second_quarantine.status_code == 200
        quarantine_id = second_quarantine.json()["quarantineId"]

        before_retention = client.post(
            "/v1/platform-admin/storage/previews",
            headers=_mutation_headers(
                client,
                "storage-preview-purge-early-0001",
            ),
            json={
                "nodeId": "home",
                "category": "project-quarantine",
                "operationKind": "purge",
                "quarantineId": quarantine_id,
            },
        )
        assert before_retention.status_code == 409
        assert (
            before_retention.json()["code"]
            == "quarantine_retention_active"
        )

        database = connect_database(database_path)
        try:
            database.execute(
                """
                UPDATE storage_project_quarantines
                SET purge_eligible_at = unixepoch() - 1
                WHERE id = ?
                """,
                (quarantine_id,),
            )
        finally:
            database.close()

        purge_preview = client.post(
            "/v1/platform-admin/storage/previews",
            headers=_mutation_headers(
                client,
                "storage-preview-purge-ready-0001",
            ),
            json={
                "nodeId": "home",
                "category": "project-quarantine",
                "operationKind": "purge",
                "quarantineId": quarantine_id,
            },
        )
        assert purge_preview.status_code == 201
        assert purge_preview.json()["confirmation"] == "PURGE"

        purged = client.post(
            "/v1/platform-admin/storage/operations",
            headers=_mutation_headers(
                client,
                "storage-execute-purge-ready-0001",
            ),
            json={
                "previewId": purge_preview.json()["id"],
                "confirmation": "PURGE",
            },
        )
        assert purged.status_code == 200
        assert purged.json()["status"] == "succeeded"
        assert purged.json()["reclaimedBytes"] == 250_000
        snapshot = client.get("/v1/platform-admin/storage").json()
        quarantine = next(
            item
            for item in snapshot["nodes"][0]["quarantines"]
            if item["id"] == quarantine_id
        )
        assert quarantine["status"] == "purged"
        assert quarantine["purgedAt"] is not None

        database = sqlite3.connect(database_path)
        try:
            assert database.execute(
                """
                SELECT COUNT(*)
                FROM storage_admin_audit_events
                WHERE action = 'storage.operation.succeeded'
                """
            ).fetchone()[0] == 4
            serialized = "\n".join(
                str(row)
                for row in database.execute(
                    """
                    SELECT details_json
                    FROM storage_admin_audit_events
                    """
                ).fetchall()
            )
            assert "/srv/" not in serialized
            assert "rm -rf" not in serialized
        finally:
            database.close()
