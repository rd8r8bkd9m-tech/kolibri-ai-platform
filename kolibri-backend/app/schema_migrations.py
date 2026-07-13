"""Fail-closed adoption of legacy ``create_all`` databases into Alembic."""

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
}


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
    if problems:
        raise SchemaAdoptionError("unversioned database is not the verified Kolibri baseline; " + "; ".join(problems))


def ensure_database_schema(engine: Engine) -> str:
    """Adopt a verified legacy schema and advance it to the single Alembic head.

    The caller runs ``Base.metadata.create_all`` first. This preserves the old
    non-destructive bootstrap behaviour for new databases while ensuring that
    an existing same-name but incompatible schema fails before it is stamped.
    """

    with engine.begin() as connection:
        config = _config(connection)
        context = MigrationContext.configure(connection)
        current = context.get_current_revision()
        if current is None:
            _verify_unversioned_baseline(connection)
            command.stamp(config, "001_initial")
        command.upgrade(config, "head")

        expected = ScriptDirectory.from_config(config).get_current_head()
        actual = MigrationContext.configure(connection).get_current_revision()
        inspector = sa.inspect(connection)
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
        if (
            actual != expected
            or "version" not in columns
            or not telegram_expected.issubset(telegram_columns)
            or not telegram_update_expected.issubset(telegram_update_columns)
            or not public_api_key_expected.issubset(public_api_key_columns)
        ):
            raise SchemaAdoptionError(
                f"database migration verification failed: revision={actual!r}, expected={expected!r}, "
                f"project_messages.version={'present' if 'version' in columns else 'missing'}, "
                "telegram_delivery_evidence="
                f"{'present' if telegram_expected.issubset(telegram_columns) else 'missing'}, "
                "telegram_updates="
                f"{'present' if telegram_update_expected.issubset(telegram_update_columns) else 'missing'}, "
                "public_api_keys="
                f"{'present' if public_api_key_expected.issubset(public_api_key_columns) else 'missing'}"
            )
        return str(actual)
