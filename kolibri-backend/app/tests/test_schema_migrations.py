import os
from pathlib import Path
import subprocess
import sys
import textwrap
import time

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


def replace_handoff_tables_with_malformed_contract(engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE project_handoffs")
        connection.exec_driver_sql("DROP TABLE project_access")
        connection.exec_driver_sql(
            "CREATE TABLE project_access ("
            "id VARCHAR, project_id VARCHAR, scope_id VARCHAR NOT NULL, "
            "permission VARCHAR NOT NULL, source VARCHAR NOT NULL, "
            "created_at DATETIME NOT NULL, revoked_at DATETIME, "
            "UNIQUE(project_id, scope_id))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE project_handoffs ("
            "id VARCHAR, project_id VARCHAR, source_scope_id VARCHAR NOT NULL, "
            "token_hash VARCHAR NOT NULL UNIQUE, idempotency_key VARCHAR NOT NULL UNIQUE, "
            "expires_at DATETIME NOT NULL, claimed_by_scope_id VARCHAR, "
            "claimed_at DATETIME, created_at DATETIME NOT NULL)"
        )


def test_unversioned_create_all_database_is_adopted_and_backfilled(tmp_path: Path):
    engine = legacy_engine(tmp_path / "legacy.db")

    revision = ensure_database_schema(engine)

    with engine.connect() as connection:
        assert revision == "006_project_handoffs"
        assert MigrationContext.configure(connection).get_current_revision() == "006_project_handoffs"
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
        assert {
            "id", "project_id", "scope_id", "permission", "source", "created_at", "revoked_at",
        } == {
            column["name"]
            for column in sa.inspect(connection).get_columns("project_access")
        }
        assert {
            "id", "project_id", "source_scope_id", "token_hash", "idempotency_key",
            "expires_at", "claimed_by_scope_id", "claimed_at", "created_at",
        } == {
            column["name"]
            for column in sa.inspect(connection).get_columns("project_handoffs")
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


def test_unversioned_handoff_tables_require_pk_fk_and_nullability_before_stamp(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'malformed-unversioned.db'}")
    Base.metadata.create_all(bind=engine)
    replace_handoff_tables_with_malformed_contract(engine)

    with pytest.raises(SchemaAdoptionError, match="project_access contract"):
        ensure_database_schema(engine)

    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() is None
    engine.dispose()


def test_revision_005_rejects_malformed_handoff_tables_before_upgrade(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'malformed-versioned.db'}")
    Base.metadata.create_all(bind=engine)
    replace_handoff_tables_with_malformed_contract(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO alembic_version(version_num) VALUES ('005_estimate_revisions')"
        )

    with pytest.raises(RuntimeError, match="existing project_access table is incompatible"):
        ensure_database_schema(engine)

    with engine.connect() as connection:
        assert (
            MigrationContext.configure(connection).get_current_revision()
            == "005_estimate_revisions"
        )
    engine.dispose()


def test_nonempty_database_never_recreates_a_missing_table(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'missing-table.db'}")
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE tasks")

    with pytest.raises(SchemaAdoptionError, match="missing baseline tables: tasks"):
        ensure_database_schema(engine)

    with engine.connect() as connection:
        assert "tasks" not in sa.inspect(connection).get_table_names()
        assert MigrationContext.configure(connection).get_current_revision() is None
    engine.dispose()


def test_versioned_database_rejects_missing_baseline_before_upgrade(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'versioned-missing-table.db'}")
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE tasks")
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO alembic_version(version_num) VALUES ('005_estimate_revisions')"
        )

    with pytest.raises(SchemaAdoptionError, match="missing baseline tables: tasks"):
        ensure_database_schema(engine)

    with engine.connect() as connection:
        assert "tasks" not in sa.inspect(connection).get_table_names()
        assert (
            MigrationContext.configure(connection).get_current_revision()
            == "005_estimate_revisions"
        )
    engine.dispose()


def test_sqlite_schema_creation_waits_for_cross_process_lock(tmp_path: Path):
    database_path = tmp_path / "concurrent.db"
    ready_path = tmp_path / "lock-ready"
    release_path = tmp_path / "lock-release"
    attempt_path = tmp_path / "migration-attempt"
    backend_root = Path(__file__).resolve().parents[2]
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{database_path}",
        "PYTHONDONTWRITEBYTECODE": "1",
        "LOCK_READY_PATH": str(ready_path),
        "LOCK_RELEASE_PATH": str(release_path),
        "MIGRATION_ATTEMPT_PATH": str(attempt_path),
    }
    holder_code = textwrap.dedent(
        """
        import os
        from pathlib import Path
        import time

        from app.database import engine
        from app.schema_migrations import _sqlite_migration_lock

        ready = Path(os.environ["LOCK_READY_PATH"])
        release = Path(os.environ["LOCK_RELEASE_PATH"])
        with _sqlite_migration_lock(engine):
            ready.touch()
            deadline = time.monotonic() + 20
            while not release.exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError("migration lock test release timed out")
                time.sleep(0.01)
        """
    )
    runner_code = textwrap.dedent(
        """
        import os
        from pathlib import Path

        from app import models as _models
        from app.database import engine
        from app.schema_migrations import ensure_database_schema

        Path(os.environ["MIGRATION_ATTEMPT_PATH"]).touch()
        print(ensure_database_schema(engine), flush=True)
        """
    )

    holder = subprocess.Popen(
        [sys.executable, "-c", holder_code],
        cwd=backend_root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    runner = None
    try:
        deadline = time.monotonic() + 10
        while not ready_path.exists():
            if holder.poll() is not None:
                _stdout, stderr = holder.communicate()
                pytest.fail(f"lock holder exited before readiness: {stderr}")
            if time.monotonic() >= deadline:
                pytest.fail("lock holder did not become ready")
            time.sleep(0.01)

        runner = subprocess.Popen(
            [sys.executable, "-c", runner_code],
            cwd=backend_root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 10
        while not attempt_path.exists():
            if runner.poll() is not None:
                _stdout, stderr = runner.communicate()
                pytest.fail(f"migration runner exited before attempting lock: {stderr}")
            if time.monotonic() >= deadline:
                pytest.fail("migration runner did not attempt schema creation")
            time.sleep(0.01)

        time.sleep(0.25)
        assert runner.poll() is None
        assert not database_path.exists()

        release_path.touch()
        runner_stdout, runner_stderr = runner.communicate(timeout=30)
        holder_stdout, holder_stderr = holder.communicate(timeout=30)
        assert holder.returncode == 0, holder_stderr or holder_stdout
        assert runner.returncode == 0, runner_stderr or runner_stdout
        assert runner_stdout.strip().endswith("006_project_handoffs")
    finally:
        release_path.touch(exist_ok=True)
        for process in (runner, holder):
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
