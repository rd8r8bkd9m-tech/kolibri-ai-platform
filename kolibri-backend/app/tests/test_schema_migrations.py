from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from app.database import Base
from app.schema_migrations import SchemaAdoptionError, ensure_database_schema


def legacy_engine(path: Path):
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE project_messages DROP COLUMN version")
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
        assert revision == "003_telegram_delivery_evidence"
        assert MigrationContext.configure(connection).get_current_revision() == "003_telegram_delivery_evidence"
        columns = {column["name"] for column in sa.inspect(connection).get_columns("project_messages")}
        assert "version" in columns
        telegram_columns = {
            column["name"]
            for column in sa.inspect(connection).get_columns("telegram_delivery_evidence")
        }
        assert telegram_columns == {
            "id", "update_id", "response_method", "origin_network", "verified_at", "updated_at",
        }
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
