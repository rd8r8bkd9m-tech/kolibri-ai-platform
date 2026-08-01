"""Non-authoritative durable mappings for provider runtime sessions.

Kolibri chat messages remain the only conversation authority. This cache binds
a provider thread to the complete execution/isolation scope and to the exact
canonical product-history head that the provider has observed.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from typing import Protocol, Sequence

from .database import connect_database, transaction


_SCOPE_FIELD_NAMES = (
    "tenant_id",
    "user_id",
    "project_id",
    "product_thread_id",
    "credential_tenant_id",
    "runtime_profile",
    "runtime_id",
    "runtime_mode",
    "execution_profile",
    "workspace_fingerprint",
    "model_id",
    "reasoning_effort",
    "service_tier",
    "sandbox_profile",
    "approval_policy",
    "approvals_reviewer",
    "instructions_hash",
    "output_schema_hash",
)


class AgentRuntimeSessionCacheError(RuntimeError):
    """The optional acceleration cache could not be read or updated."""


def stable_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def canonical_history_hash(
    messages: Sequence[tuple[str, str]],
) -> str:
    return stable_hash(
        {
            "schema": "kolibri.agent-runtime-history.v1",
            "messages": [
                {"role": role, "content": content}
                for role, content in messages
            ],
        }
    )


@dataclass(frozen=True, slots=True)
class AgentRuntimeSessionScope:
    tenant_id: str
    user_id: str
    project_id: str
    product_thread_id: str
    credential_tenant_id: str
    runtime_profile: str
    runtime_id: str
    runtime_mode: str
    execution_profile: str
    workspace_fingerprint: str
    model_id: str
    reasoning_effort: str
    service_tier: str
    sandbox_profile: str
    approval_policy: str
    approvals_reviewer: str
    instructions_hash: str
    output_schema_hash: str

    def __post_init__(self) -> None:
        if tuple(field.name for field in fields(self)) != _SCOPE_FIELD_NAMES:
            raise AssertionError("runtime session scope fields are incomplete")
        for name in _SCOPE_FIELD_NAMES:
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) > 4_096 or "\x00" in value:
                raise ValueError(f"{name} is invalid")
        for name in (
            "tenant_id",
            "user_id",
            "project_id",
            "product_thread_id",
            "credential_tenant_id",
            "runtime_profile",
            "runtime_id",
            "runtime_mode",
            "execution_profile",
            "workspace_fingerprint",
            "sandbox_profile",
            "approval_policy",
            "instructions_hash",
            "output_schema_hash",
        ):
            if not getattr(self, name):
                raise ValueError(f"{name} is required")

    @property
    def scope_key(self) -> str:
        return stable_hash(
            {
                name: getattr(self, name)
                for name in _SCOPE_FIELD_NAMES
            }
        )

    def database_values(self) -> dict[str, str]:
        return {
            name: getattr(self, name)
            for name in _SCOPE_FIELD_NAMES
        }


@dataclass(frozen=True, slots=True)
class AgentRuntimeSessionEntry:
    scope: AgentRuntimeSessionScope
    provider_thread_id: str
    canonical_history_hash: str


class AgentRuntimeSessionCacheProtocol(Protocol):
    def lookup(
        self,
        scope: AgentRuntimeSessionScope,
    ) -> AgentRuntimeSessionEntry | None: ...

    def store(
        self,
        scope: AgentRuntimeSessionScope,
        *,
        provider_thread_id: str,
        history_hash: str,
    ) -> None: ...

    def evict_if_matches(
        self,
        scope: AgentRuntimeSessionScope,
        *,
        provider_thread_id: str,
    ) -> bool: ...


class AgentRuntimeSessionCache:
    """SQLite-backed compare-and-delete provider session cache."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def lookup(
        self,
        scope: AgentRuntimeSessionScope,
    ) -> AgentRuntimeSessionEntry | None:
        database = connect_database(self._database_url)
        try:
            row = database.execute(
                """
                SELECT *
                FROM agent_runtime_session_cache
                WHERE scope_key = ?
                """,
                (scope.scope_key,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise AgentRuntimeSessionCacheError(
                "runtime session cache lookup failed"
            ) from exc
        finally:
            database.close()
        if row is None:
            return None
        stored_scope = AgentRuntimeSessionScope(
            **{
                name: str(row[name])
                for name in _SCOPE_FIELD_NAMES
            }
        )
        if stored_scope != scope:
            raise AgentRuntimeSessionCacheError(
                "runtime session cache scope hash collision"
            )
        return AgentRuntimeSessionEntry(
            scope=stored_scope,
            provider_thread_id=str(row["provider_thread_id"]),
            canonical_history_hash=str(row["canonical_history_hash"]),
        )

    def store(
        self,
        scope: AgentRuntimeSessionScope,
        *,
        provider_thread_id: str,
        history_hash: str,
    ) -> None:
        self._validate_binding(provider_thread_id, history_hash)
        now = datetime.now(timezone.utc).isoformat()
        values = {
            "scope_key": scope.scope_key,
            **scope.database_values(),
            "provider_thread_id": provider_thread_id,
            "canonical_history_hash": history_hash,
            "created_at": now,
            "updated_at": now,
        }
        database = connect_database(self._database_url)
        try:
            with transaction(database, immediate=True):
                cursor = database.execute(
                    f"""
                    INSERT INTO agent_runtime_session_cache (
                        scope_key,
                        {", ".join(_SCOPE_FIELD_NAMES)},
                        provider_thread_id,
                        canonical_history_hash,
                        created_at,
                        updated_at
                    ) VALUES (
                        :scope_key,
                        {", ".join(f":{name}" for name in _SCOPE_FIELD_NAMES)},
                        :provider_thread_id,
                        :canonical_history_hash,
                        :created_at,
                        :updated_at
                    )
                    ON CONFLICT(scope_key) DO UPDATE SET
                        provider_thread_id = excluded.provider_thread_id,
                        canonical_history_hash = excluded.canonical_history_hash,
                        updated_at = excluded.updated_at
                    WHERE {" AND ".join(
                        f"agent_runtime_session_cache.{name} = excluded.{name}"
                        for name in _SCOPE_FIELD_NAMES
                    )}
                    """,
                    values,
                )
                if cursor.rowcount != 1:
                    raise AgentRuntimeSessionCacheError(
                        "runtime session cache scope hash collision"
                    )
        except AgentRuntimeSessionCacheError:
            raise
        except sqlite3.Error as exc:
            raise AgentRuntimeSessionCacheError(
                "runtime session cache update failed"
            ) from exc
        finally:
            database.close()

    def evict_if_matches(
        self,
        scope: AgentRuntimeSessionScope,
        *,
        provider_thread_id: str,
    ) -> bool:
        self._validate_provider_thread_id(provider_thread_id)
        values = {
            "scope_key": scope.scope_key,
            "provider_thread_id": provider_thread_id,
            **scope.database_values(),
        }
        database = connect_database(self._database_url)
        try:
            with transaction(database, immediate=True):
                cursor = database.execute(
                    f"""
                    DELETE FROM agent_runtime_session_cache
                    WHERE scope_key = :scope_key
                      AND provider_thread_id = :provider_thread_id
                      AND {" AND ".join(
                          f"{name} = :{name}"
                          for name in _SCOPE_FIELD_NAMES
                      )}
                    """,
                    values,
                )
                return cursor.rowcount == 1
        except sqlite3.Error as exc:
            raise AgentRuntimeSessionCacheError(
                "runtime session cache eviction failed"
            ) from exc
        finally:
            database.close()

    @staticmethod
    def _validate_provider_thread_id(provider_thread_id: str) -> None:
        if (
            not provider_thread_id
            or len(provider_thread_id) > 512
            or "\x00" in provider_thread_id
        ):
            raise ValueError("provider_thread_id is invalid")

    @classmethod
    def _validate_binding(
        cls,
        provider_thread_id: str,
        history_hash: str,
    ) -> None:
        cls._validate_provider_thread_id(provider_thread_id)
        if (
            len(history_hash) != 71
            or not history_hash.startswith("sha256:")
            or any(character not in "0123456789abcdef" for character in history_hash[7:])
        ):
            raise ValueError("canonical history hash is invalid")
