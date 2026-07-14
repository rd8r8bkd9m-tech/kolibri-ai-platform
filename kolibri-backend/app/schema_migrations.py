"""Fail-closed adoption of legacy ``create_all`` databases into Alembic."""

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine


class SchemaAdoptionError(RuntimeError):
    """Raised before mutation when an unversioned schema is not a known baseline."""


BASELINE_COLUMNS: dict[str, set[str]] = {
    "estimates": {"id", "title", "status", "created_at", "updated_at"},
    "sections": {"id", "estimate_id", "title", "subtotal"},
    "positions": {"id", "section_id", "name", "quantity", "price", "sum"},
    "documents": {"id", "title", "type", "status", "content", "created_at", "updated_at"},
    "agents": {"id", "name", "status"},
    "nodes": {"id", "name", "status"},
    "tasks": {"id", "state", "created_at", "updated_at"},
}

ALLOWED_UNVERSIONED_TABLES = set(BASELINE_COLUMNS) | {
    "users",
    "price_catalog",
    "projects",
    "project_messages",
    "project_message_mutations",
    "telegram_delivery_evidence",
    "telegram_updates",
    "telegram_bot_identity",
    "public_api_keys",
    "estimate_revisions",
    "project_access",
    "project_handoffs",
    "public_responses",
    "public_response_events",
}

_PROJECT_ACCESS_NULLABLE = {
    "id": False,
    "project_id": False,
    "scope_id": False,
    "permission": False,
    "source": False,
    "created_at": False,
    "revoked_at": True,
}
_PROJECT_HANDOFF_NULLABLE = {
    "id": False,
    "project_id": False,
    "source_scope_id": False,
    "token_hash": False,
    "idempotency_key": False,
    "expires_at": False,
    "claimed_by_scope_id": True,
    "claimed_at": True,
    "created_at": False,
}


@contextmanager
def _sqlite_migration_lock(engine: Engine):
    """Serialize schema creation and Alembic updates for one SQLite file."""

    database = engine.url.database
    if engine.dialect.name != "sqlite" or not database or database == ":memory:":
        yield
        return

    database_path = Path(database).expanduser()
    if not database_path.is_absolute():
        database_path = (Path.cwd() / database_path).resolve()
    lock_path = Path(f"{database_path}.schema.lock")
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _table_contract_issues(
    inspector,
    table: str,
    *,
    nullable: dict[str, bool],
    unique: set[tuple[str, ...]],
) -> list[str]:
    columns = {column["name"]: column for column in inspector.get_columns(table)}
    issues: list[str] = []
    missing = sorted(set(nullable) - set(columns))
    if missing:
        issues.append(f"missing columns: {', '.join(missing)}")

    nullable_mismatches = sorted(
        name
        for name, expected in nullable.items()
        if name in columns and bool(columns[name].get("nullable")) is not expected
    )
    if nullable_mismatches:
        issues.append(f"nullable mismatch: {', '.join(nullable_mismatches)}")

    primary_key = tuple(
        inspector.get_pk_constraint(table).get("constrained_columns") or []
    )
    if primary_key != ("id",):
        issues.append("primary key must be (id)")

    actual_unique = {
        tuple(constraint.get("column_names") or [])
        for constraint in inspector.get_unique_constraints(table)
    }
    missing_unique = sorted(unique - actual_unique)
    if missing_unique:
        issues.append(
            "missing unique constraints: "
            + ", ".join(
                "(" + ", ".join(column_names) + ")"
                for column_names in missing_unique
            )
        )

    project_foreign_key = any(
        tuple(foreign_key.get("constrained_columns") or []) == ("project_id",)
        and foreign_key.get("referred_table") == "projects"
        and tuple(foreign_key.get("referred_columns") or []) == ("id",)
        and str((foreign_key.get("options") or {}).get("ondelete") or "").upper()
        == "CASCADE"
        for foreign_key in inspector.get_foreign_keys(table)
    )
    if not project_foreign_key:
        issues.append("project_id foreign key must reference projects.id ON DELETE CASCADE")
    return issues


def _config(connection) -> Config:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "app" / "migrations"))
    config.attributes["connection"] = connection
    return config


def _verify_unversioned_baseline(connection) -> None:
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    unknown = sorted(tables - ALLOWED_UNVERSIONED_TABLES)
    missing_tables = sorted(set(BASELINE_COLUMNS) - tables)
    problems: list[str] = []
    if unknown:
        problems.append(f"unexpected tables: {', '.join(unknown)}")
    if missing_tables:
        problems.append(f"missing baseline tables: {', '.join(missing_tables)}")
    for table, required in BASELINE_COLUMNS.items():
        if table not in tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        missing = sorted(required - columns)
        primary_key = set(inspector.get_pk_constraint(table).get("constrained_columns") or [])
        if missing:
            problems.append(f"{table} missing columns: {', '.join(missing)}")
        if "id" not in primary_key:
            problems.append(f"{table} does not have id as a primary key")
    contract_tables = (
        (
            "project_access",
            _PROJECT_ACCESS_NULLABLE,
            {("project_id", "scope_id")},
        ),
        (
            "project_handoffs",
            _PROJECT_HANDOFF_NULLABLE,
            {("token_hash",), ("idempotency_key",)},
        ),
    )
    for table, nullable, unique in contract_tables:
        if table not in tables:
            continue
        issues = _table_contract_issues(
            inspector,
            table,
            nullable=nullable,
            unique=unique,
        )
        if issues:
            problems.append(f"{table} contract: {'; '.join(issues)}")
    if problems:
        raise SchemaAdoptionError("unversioned database is not the verified Kolibri baseline; " + "; ".join(problems))


def _verify_versioned_baseline(connection) -> None:
    """Reject loss of revision-001 tables before running later migrations."""

    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    problems: list[str] = []
    missing_tables = sorted(set(BASELINE_COLUMNS) - tables)
    if missing_tables:
        problems.append(f"missing baseline tables: {', '.join(missing_tables)}")
    for table, required in BASELINE_COLUMNS.items():
        if table not in tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        missing = sorted(required - columns)
        primary_key = set(inspector.get_pk_constraint(table).get("constrained_columns") or [])
        if missing:
            problems.append(f"{table} missing columns: {', '.join(missing)}")
        if "id" not in primary_key:
            problems.append(f"{table} does not have id as a primary key")
    if problems:
        raise SchemaAdoptionError(
            "versioned database is missing its immutable baseline; " + "; ".join(problems)
        )


def ensure_database_schema(engine: Engine) -> str:
    """Create/adopt the schema and advance it to the single Alembic head.

    SQLite creation and migration share one file lock so the API and Telegram
    worker cannot race each other during release startup.
    """

    from app import models as _models  # noqa: F401 - register complete metadata
    from app.database import Base

    with _sqlite_migration_lock(engine):
        with engine.connect() as connection:
            existing_tables = set(sa.inspect(connection).get_table_names())
        if not existing_tables:
            Base.metadata.create_all(bind=engine)
        return _ensure_database_schema(engine)


def _ensure_database_schema(engine: Engine) -> str:
    """Run adoption and Alembic verification while the caller holds any lock."""

    with engine.begin() as connection:
        config = _config(connection)
        context = MigrationContext.configure(connection)
        current = context.get_current_revision()
        if current is None:
            _verify_unversioned_baseline(connection)
            command.stamp(config, "001_initial")
        else:
            _verify_versioned_baseline(connection)
        command.upgrade(config, "head")

        expected = ScriptDirectory.from_config(config).get_current_head()
        actual = MigrationContext.configure(connection).get_current_revision()
        inspector = sa.inspect(connection)
        tables = set(inspector.get_table_names())
        missing_required_tables = sorted(ALLOWED_UNVERSIONED_TABLES - tables)
        columns = {column["name"] for column in inspector.get_columns("project_messages")}
        telegram_columns = {
            column["name"]
            for column in inspector.get_columns("telegram_delivery_evidence")
        }
        telegram_expected = {
            "id", "update_id", "response_method", "origin_network", "verified_at", "updated_at",
        }
        telegram_update_columns = {
            column["name"]
            for column in inspector.get_columns("telegram_updates")
        }
        telegram_update_expected = {
            "id", "update_id", "chat_id", "message_id", "payload_hash", "payload",
            "state", "attempts", "lease_owner", "lease_until", "project_id",
            "assistant_message_id", "response_id", "acknowledgement_message_id",
            "result_message_id", "outbound_state", "delivery_method", "last_error_code",
            "created_at", "updated_at", "completed_at",
        }
        public_api_key_columns = {
            column["name"]
            for column in inspector.get_columns("public_api_keys")
        }
        public_api_key_expected = {
            "id", "owner_scope", "name", "key_prefix", "secret_hash",
            "created_at", "last_used_at", "revoked_at",
        }
        public_response_columns = {
            column["name"] for column in inspector.get_columns("public_responses")
        }
        public_response_expected = {
            "id", "owner_scope", "status", "idempotency_key", "request_hash",
            "payload", "created_at", "updated_at",
        }
        public_response_unique = {
            tuple(constraint.get("column_names") or [])
            for constraint in inspector.get_unique_constraints("public_responses")
        }
        public_response_event_columns = {
            column["name"] for column in inspector.get_columns("public_response_events")
        }
        public_response_event_expected = {
            "id", "response_id", "sequence", "event_type", "payload", "created_at",
        }
        public_response_event_unique = {
            tuple(constraint.get("column_names") or [])
            for constraint in inspector.get_unique_constraints("public_response_events")
        }
        section_columns = {
            column["name"] for column in inspector.get_columns("sections")
        }
        position_columns = {
            column["name"] for column in inspector.get_columns("positions")
        }
        estimate_columns = {
            column["name"] for column in inspector.get_columns("estimates")
        }
        estimate_column_contract = {
            column["name"]: column for column in inspector.get_columns("estimates")
        }
        estimate_truth_expected = {
            "scope_id", "estimate_status", "pricing_status", "scope_status", "source_note",
            "assumptions", "questions", "price_sources", "evidence_issues",
        }
        estimate_revision_columns = {
            column["name"] for column in inspector.get_columns("estimate_revisions")
        }
        estimate_revision_expected = {
            "id", "estimate_id", "version", "snapshot", "created_at",
        }
        estimate_revision_unique = {
            tuple(constraint.get("column_names") or [])
            for constraint in inspector.get_unique_constraints("estimate_revisions")
        }
        document_columns = {
            column["name"] for column in inspector.get_columns("documents")
        }
        document_column_contract = {
            column["name"]: column for column in inspector.get_columns("documents")
        }
        document_expected = {"scope_id", "estimate_id"}
        project_access_issues = _table_contract_issues(
            inspector,
            "project_access",
            nullable=_PROJECT_ACCESS_NULLABLE,
            unique={("project_id", "scope_id")},
        )
        project_handoff_issues = _table_contract_issues(
            inspector,
            "project_handoffs",
            nullable=_PROJECT_HANDOFF_NULLABLE,
            unique={("token_hash",), ("idempotency_key",)},
        )
        if (
            actual != expected
            or missing_required_tables
            or "version" not in columns
            or not telegram_expected.issubset(telegram_columns)
            or not telegram_update_expected.issubset(telegram_update_columns)
            or not public_api_key_expected.issubset(public_api_key_columns)
            or not public_response_expected.issubset(public_response_columns)
            or ("owner_scope", "idempotency_key") not in public_response_unique
            or not public_response_event_expected.issubset(public_response_event_columns)
            or ("response_id", "sequence") not in public_response_event_unique
            or "sort_order" not in section_columns
            or "sort_order" not in position_columns
            or "price_evidence" not in position_columns
            or not estimate_truth_expected.issubset(estimate_columns)
            or bool(estimate_column_contract.get("scope_id", {}).get("nullable", True))
            or not estimate_revision_expected.issubset(estimate_revision_columns)
            or ("estimate_id", "version") not in estimate_revision_unique
            or not document_expected.issubset(document_columns)
            or bool(document_column_contract.get("scope_id", {}).get("nullable", True))
            or project_access_issues
            or project_handoff_issues
        ):
            raise SchemaAdoptionError(
                f"database migration verification failed: revision={actual!r}, expected={expected!r}, "
                "required_tables="
                f"{'present' if not missing_required_tables else 'missing: ' + ', '.join(missing_required_tables)}, "
                f"project_messages.version={'present' if 'version' in columns else 'missing'}, "
                "telegram_delivery_evidence="
                f"{'present' if telegram_expected.issubset(telegram_columns) else 'missing'}, "
                "telegram_updates="
                f"{'present' if telegram_update_expected.issubset(telegram_update_columns) else 'missing'}, "
                "public_api_keys="
                f"{'present' if public_api_key_expected.issubset(public_api_key_columns) else 'missing'}, "
                "durable_responses="
                f"{'present' if public_response_expected.issubset(public_response_columns) and ('owner_scope', 'idempotency_key') in public_response_unique and public_response_event_expected.issubset(public_response_event_columns) and ('response_id', 'sequence') in public_response_event_unique else 'missing'}, "
                "estimate_ordering="
                f"{'present' if 'sort_order' in section_columns and 'sort_order' in position_columns else 'missing'}, "
                "estimate_truth="
                f"{'present' if estimate_truth_expected.issubset(estimate_columns) and 'price_evidence' in position_columns and not bool(estimate_column_contract.get('scope_id', {}).get('nullable', True)) else 'missing'}, "
                "estimate_revisions="
                f"{'present' if estimate_revision_expected.issubset(estimate_revision_columns) and ('estimate_id', 'version') in estimate_revision_unique else 'missing'}, "
                "document_scope="
                f"{'present' if document_expected.issubset(document_columns) and not bool(document_column_contract.get('scope_id', {}).get('nullable', True)) else 'missing'}, "
                "project_access="
                f"{'present' if not project_access_issues else 'invalid: ' + '; '.join(project_access_issues)}, "
                "project_handoffs="
                f"{'present' if not project_handoff_issues else 'invalid: ' + '; '.join(project_handoff_issues)}"
            )
        return str(actual)
