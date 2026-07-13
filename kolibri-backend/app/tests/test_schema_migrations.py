from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from app import models as _models  # noqa: F401 - register all metadata for isolated runs
from app.database import Base
from app.schema_migrations import SchemaAdoptionError, ensure_database_schema


def legacy_engine(path: Path):
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE estimate_revisions")
        connection.exec_driver_sql("ALTER TABLE positions DROP COLUMN sort_order")
        connection.exec_driver_sql("ALTER TABLE sections DROP COLUMN sort_order")
        connection.exec_driver_sql("ALTER TABLE project_messages DROP COLUMN version")
        connection.execute(sa.text(
            "INSERT INTO estimates "
            "(id, version, status, title, client, object_name, region, currency, overhead_rate, "
            "vat_rate, subtotal, overhead_amount, vat_amount, total, created_at, updated_at) "
            "VALUES ('estimate_1', 4, 'draft', 'Legacy estimate', '', '', '', 'RUB', '0', "
            "'22', '100.00', '0.00', '22.00', '122.00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
        connection.execute(sa.text(
            "INSERT INTO sections (id, estimate_id, title, subtotal) "
            "VALUES ('section_1', 'estimate_1', 'Works', '100.00')"
        ))
        connection.execute(sa.text(
            "INSERT INTO positions "
            "(id, section_id, code, name, unit, quantity, price, sum, source, comment) "
            "VALUES ('position_1', 'section_1', 'W-1', 'Work', 'шт', '2', '50', "
            "'100.00', '', '')"
        ))
        connection.execute(sa.text(
            "INSERT INTO projects "
            "(id, scope_id, title, title_source, status, version, message_count, metadata, created_at, updated_at) "
            "VALUES ('project_1', 'anon:test', 'Legacy', 'manual', 'active', 1, 1, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
        connection.execute(sa.text(
            "INSERT INTO project_messages "
            "(id, project_id, scope_id, sequence, role, content, status, metadata, created_at, updated_at) "
            "VALUES ('message_1', 'project_1', 'anon:test', 1, 'assistant', 'Legacy answer', 'completed', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
    return engine


def test_unversioned_create_all_database_is_adopted_and_backfilled(tmp_path: Path):
    engine = legacy_engine(tmp_path / "legacy.db")

    revision = ensure_database_schema(engine)

    with engine.connect() as connection:
        assert revision == "005_estimate_revisions"
        assert MigrationContext.configure(connection).get_current_revision() == "005_estimate_revisions"
        columns = {column["name"] for column in sa.inspect(connection).get_columns("project_messages")}
        assert "version" in columns
        telegram_columns = {
            column["name"]
            for column in sa.inspect(connection).get_columns("telegram_delivery_evidence")
        }
        assert telegram_columns == {
            "id", "update_id", "response_method", "origin_network", "verified_at", "updated_at",
        }
        assert {
            "id", "update_id", "chat_id", "message_id", "payload_hash", "payload", "state",
            "attempts", "lease_owner", "lease_until", "project_id", "assistant_message_id",
            "response_id", "acknowledgement_message_id", "result_message_id", "outbound_state",
            "delivery_method", "last_error_code", "created_at", "updated_at", "completed_at",
        } == {
            column["name"]
            for column in sa.inspect(connection).get_columns("telegram_updates")
        }
        assert {
            "id", "owner_scope", "name", "key_prefix", "secret_hash", "created_at",
            "last_used_at", "revoked_at",
        } == {
            column["name"]
            for column in sa.inspect(connection).get_columns("public_api_keys")
        }
        assert "sort_order" in {
            column["name"] for column in sa.inspect(connection).get_columns("sections")
        }
        assert "sort_order" in {
            column["name"] for column in sa.inspect(connection).get_columns("positions")
        }
        assert {
            "id", "estimate_id", "version", "snapshot", "created_at",
        } == {
            column["name"]
            for column in sa.inspect(connection).get_columns("estimate_revisions")
        }
        backfilled = connection.execute(sa.text(
            "SELECT version, snapshot FROM estimate_revisions WHERE estimate_id = 'estimate_1'"
        )).mappings().one()
        assert backfilled["version"] == 4
        snapshot = backfilled["snapshot"]
        if isinstance(snapshot, str):
            import json
            snapshot = json.loads(snapshot)
        assert snapshot["total"] == "122.00"
        assert snapshot["sections"][0]["positions"][0]["sum"] == "100.00"
        assert connection.execute(sa.text(
            "SELECT version FROM project_messages WHERE id = 'message_1'"
        )).scalar_one() == 1
    engine.dispose()


def test_unversioned_unknown_schema_fails_before_stamp(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'unknown.db'}")
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE foreign_runtime (id VARCHAR PRIMARY KEY)")

    with pytest.raises(SchemaAdoptionError, match="unexpected tables: foreign_runtime"):
        ensure_database_schema(engine)

    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() is None
    engine.dispose()
