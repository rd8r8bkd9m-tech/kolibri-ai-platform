from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app.agent_runtime_session_cache import (
    AgentRuntimeSessionCache,
    AgentRuntimeSessionScope,
    canonical_history_hash,
    stable_hash,
)
from app.database import connect_database, initialize_database, migration_paths


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "session-cache.db"
    initialize_database(path)
    database = connect_database(path)
    try:
        database.execute(
            "INSERT INTO tenants (id, name, created_at) VALUES (?, ?, ?)",
            ("tenant-a", "Tenant A", 1),
        )
        for user_id in ("user-a", "user-b"):
            database.execute(
                """
                INSERT INTO users (
                    id, tenant_id, email_normalized, email, name, role,
                    preferred_agent_profile, password_hash, created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, 'user', 'codex-cli', ?, 1, 1)
                """,
                (
                    user_id,
                    "tenant-a",
                    f"{user_id}@example.test",
                    f"{user_id}@example.test",
                    user_id,
                    "hash",
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
                "tenant-a",
                "project-a",
                "user-a",
                "Project A",
                "thread-a",
                "2026-08-01T00:00:00+00:00",
                "2026-08-01T00:00:00+00:00",
            ),
        )
        database.execute(
            """
            INSERT INTO chat_threads (
                tenant_id, id, project_id, kind, title, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, 'primary', ?, 'regular', ?, ?)
            """,
            (
                "tenant-a",
                "thread-a",
                "project-a",
                "Thread A",
                "2026-08-01T00:00:00+00:00",
                "2026-08-01T00:00:00+00:00",
            ),
        )
    finally:
        database.close()
    return path


def _scope() -> AgentRuntimeSessionScope:
    return AgentRuntimeSessionScope(
        tenant_id="tenant-a",
        user_id="user-a",
        project_id="project-a",
        product_thread_id="thread-a",
        credential_tenant_id="tenant-a",
        runtime_profile="codex-cli",
        runtime_id="codex-app-server",
        runtime_mode="chat",
        execution_profile="chat",
        workspace_fingerprint=stable_hash({"root": "/runtime"}),
        model_id="gpt-5.6-sol",
        reasoning_effort="high",
        service_tier="default",
        sandbox_profile="read-only",
        approval_policy="never",
        approvals_reviewer="",
        instructions_hash=stable_hash("instructions-v1"),
        output_schema_hash=stable_hash(None),
    )


def test_migration_045_creates_strict_non_authoritative_cache(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    database = connect_database(path)
    try:
        latest = int(migration_paths()[-1].name.split("_", 1)[0])
        assert database.execute("PRAGMA user_version").fetchone()[0] == latest
        table = database.execute(
            """
            SELECT strict
            FROM pragma_table_list
            WHERE name = 'agent_runtime_session_cache'
            """
        ).fetchone()
        assert table is not None
        assert table["strict"] == 1
        foreign_tables = {
            str(row["table"])
            for row in database.execute(
                "PRAGMA foreign_key_list(agent_runtime_session_cache)"
            ).fetchall()
        }
        assert foreign_tables == {
            "tenants",
            "users",
            "projects",
            "chat_threads",
        }
    finally:
        database.close()


def test_cache_is_full_scope_bound_and_evicts_by_compared_provider_id(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    cache = AgentRuntimeSessionCache(f"sqlite:///{path}")
    scope = _scope()
    history_v1 = canonical_history_hash((("user", "one"),))
    cache.store(
        scope,
        provider_thread_id="provider-thread-1",
        history_hash=history_v1,
    )

    entry = cache.lookup(scope)
    assert entry is not None
    assert entry.provider_thread_id == "provider-thread-1"
    assert entry.canonical_history_hash == history_v1
    assert cache.lookup(replace(scope, user_id="user-b")) is None
    assert cache.lookup(replace(scope, reasoning_effort="medium")) is None
    assert cache.lookup(replace(scope, service_tier="priority")) is None

    history_v2 = canonical_history_hash(
        (("user", "one"), ("assistant", "two"))
    )
    cache.store(
        scope,
        provider_thread_id="provider-thread-2",
        history_hash=history_v2,
    )
    assert not cache.evict_if_matches(
        scope,
        provider_thread_id="provider-thread-1",
    )
    current = cache.lookup(scope)
    assert current is not None
    assert current.provider_thread_id == "provider-thread-2"
    assert cache.evict_if_matches(
        scope,
        provider_thread_id="provider-thread-2",
    )
    assert cache.lookup(scope) is None
