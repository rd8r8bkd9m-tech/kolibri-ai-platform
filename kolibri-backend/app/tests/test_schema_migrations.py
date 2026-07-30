import os
from io import StringIO
from pathlib import Path
import subprocess
import sys
import textwrap
import time

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.runtime.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models as _models  # noqa: F401 - register all metadata for isolated runs
from app.database import Base
from app.schema_migrations import SchemaAdoptionError, _config, ensure_database_schema
from app.storage import DBStorage


def test_estimate_truth_json_defaults_compile_for_sqlite_and_postgresql():
    for dialect_name in ("sqlite", "postgresql"):
        output = StringIO()
        context = MigrationContext.configure(
            dialect_name=dialect_name,
            opts={"as_sql": True, "output_buffer": output},
        )
        operations = Operations(context)
        operations.add_column(
            "estimates",
            sa.Column(
                "assumptions",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            ),
        )
        statement = output.getvalue()
        assert "assumptions JSON" in statement
        assert "DEFAULT '[]'" in statement
        assert "NOT NULL" in statement


def test_fresh_alembic_chain_creates_scoped_documents_and_estimate_relation(
    tmp_path: Path,
):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh-alembic.db'}")
    with engine.begin() as connection:
        command.upgrade(_config(connection), "head")
        inspector = sa.inspect(connection)
        document_columns = {
            column["name"]: column for column in inspector.get_columns("documents")
        }
        assert MigrationContext.configure(connection).get_current_revision() == (
            "025_normative_source_claims"
        )
        assert {"scope_id", "estimate_id", "organization_id"}.issubset(document_columns)
        assert document_columns["scope_id"]["nullable"] is False
        estimate_columns = {
            column["name"] for column in inspector.get_columns("estimates")
        }
        assert {
            "technology_card",
            "procurement_report",
            "client_record_id",
            "object_record_id",
        }.issubset(estimate_columns)
        assert {
            "technology_catalog",
            "clients",
            "construction_objects",
            "owner_model_connections",
            "project_source_documents",
            "project_knowledge_bases",
            "document_ingestion_jobs",
            "document_chunks",
            "normative_sources",
            "normative_source_snapshots",
            "normative_source_chunks",
            "normative_source_claims",
            "password_reset_tokens",
        }.issubset(inspector.get_table_names())
        work_catalog_columns = {
            column["name"] for column in inspector.get_columns("work_catalog")
        }
        assert {"price_source", "price_observed_at"}.issubset(work_catalog_columns)
        estimate_foreign_keys = inspector.get_foreign_keys("estimates")
        assert any(
            tuple(foreign_key.get("constrained_columns") or [])
            == ("client_record_id",)
            and foreign_key.get("referred_table") == "clients"
            for foreign_key in estimate_foreign_keys
        )
        assert any(
            tuple(foreign_key.get("constrained_columns") or [])
            == ("object_record_id",)
            and foreign_key.get("referred_table") == "construction_objects"
            for foreign_key in estimate_foreign_keys
        )
        assert {
            "ix_estimates_scope_client",
            "ix_estimates_scope_object",
        }.issubset({index["name"] for index in inspector.get_indexes("estimates")})
        assert any(
            tuple(foreign_key.get("constrained_columns") or []) == ("estimate_id",)
            and foreign_key.get("referred_table") == "estimates"
            and tuple(foreign_key.get("referred_columns") or []) == ("id",)
            and str((foreign_key.get("options") or {}).get("ondelete") or "").upper()
            == "SET NULL"
            for foreign_key in inspector.get_foreign_keys("documents")
        )
        assert {
            "ix_documents_scope_created_at",
            "ix_documents_scope_status",
            "ix_documents_organization_created",
        }.issubset({index["name"] for index in inspector.get_indexes("documents")})
        assert {
            "organizations",
            "organization_memberships",
            "organization_audit_events",
            "users",
            "clients",
            "construction_objects",
        }.issubset(inspector.get_table_names())
    engine.dispose()


def test_revision_011_backfills_personal_org_without_claiming_other_scopes(
    tmp_path: Path,
):
    engine = create_engine(f"sqlite:///{tmp_path / 'organization-backfill.db'}")
    with engine.begin() as connection:
        command.upgrade(_config(connection), "010_durable_responses")
        connection.exec_driver_sql(
            "CREATE TABLE users ("
            "id VARCHAR PRIMARY KEY, email VARCHAR NOT NULL UNIQUE, name VARCHAR NOT NULL, "
            "hashed_password VARCHAR NOT NULL, role VARCHAR, is_active BOOLEAN, created_at DATETIME)"
        )
        connection.execute(sa.text(
            "INSERT INTO users "
            "(id, email, name, hashed_password, role, is_active, created_at) VALUES "
            "('user-1', 'owner@example.test', 'Иван', 'hash', 'user', 1, CURRENT_TIMESTAMP)"
        ))
        connection.execute(sa.text(
            "INSERT INTO projects "
            "(id, scope_id, title, title_source, status, version, message_count, metadata, "
            "created_at, updated_at) VALUES "
            "('project-user', 'user:user-1', 'User project', 'manual', 'active', 1, 0, '{}', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
            "('project-anon', 'anon:private', 'Anon project', 'manual', 'active', 1, 0, '{}', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
        connection.execute(sa.text(
            "INSERT INTO estimates (id, scope_id, title, vat_rate, created_at, updated_at) VALUES "
            "('estimate-user', 'user:user-1', 'User estimate', '0', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
        connection.execute(sa.text(
            "INSERT INTO documents (id, scope_id, title, created_at, updated_at) VALUES "
            "('document-user', 'user:user-1', 'User document', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
        connection.execute(sa.text(
            "INSERT INTO public_responses "
            "(id, owner_scope, status, payload, created_at, updated_at) VALUES "
            "('response-user', 'user:user-1', 'completed', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
        connection.execute(sa.text(
            "INSERT INTO public_api_keys "
            "(id, owner_scope, name, key_prefix, secret_hash, created_at) VALUES "
            "('key-user', 'user:user-1', 'User key', 'kol_user', 'hash-user', CURRENT_TIMESTAMP), "
            "('key-legacy', 'owner', 'Legacy key', 'kol_owner', 'hash-owner', CURRENT_TIMESTAMP)"
        ))
        command.upgrade(_config(connection), "head")

        organization = connection.execute(sa.text(
            "SELECT id, data_scope_id FROM organizations"
        )).mappings().one()
        assert organization["data_scope_id"] == "user:user-1"
        organization_id = organization["id"]
        assert connection.execute(sa.text(
            "SELECT default_organization_id FROM users WHERE id = 'user-1'"
        )).scalar_one() == organization_id
        assert connection.execute(sa.text(
            "SELECT role, status FROM organization_memberships "
            "WHERE organization_id = :organization_id AND user_id = 'user-1'"
        ).bindparams(organization_id=organization_id)).one() == ("owner", "active")

        for table, resource_id in (
            ("projects", "project-user"),
            ("estimates", "estimate-user"),
            ("documents", "document-user"),
            ("public_responses", "response-user"),
            ("public_api_keys", "key-user"),
        ):
            assert connection.execute(sa.text(
                f"SELECT organization_id FROM {table} WHERE id = :resource_id"
            ).bindparams(resource_id=resource_id)).scalar_one() == organization_id
        assert connection.execute(sa.text(
            "SELECT organization_id FROM projects WHERE id = 'project-anon'"
        )).scalar_one() is None
        assert connection.execute(sa.text(
            "SELECT organization_id FROM public_api_keys WHERE id = 'key-legacy'"
        )).scalar_one() is None
        assert connection.execute(sa.text(
            "SELECT COUNT(*) FROM organization_audit_events "
            "WHERE action = 'organization.personal_backfilled'"
        )).scalar_one() == 1
    # Revision 001 predates the global catalog table; normal startup creates
    # the complete model baseline before Alembic verification.
    _models.CatalogItemDB.__table__.create(bind=engine)
    assert ensure_database_schema(engine) == "025_normative_source_claims"
    engine.dispose()


def legacy_engine(path: Path):
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP INDEX ix_estimates_scope_created_at")
        connection.exec_driver_sql("DROP INDEX ix_estimates_scope_status")
        connection.exec_driver_sql("DROP INDEX ix_estimates_scope_client")
        connection.exec_driver_sql("DROP INDEX ix_estimates_scope_object")
        connection.exec_driver_sql("ALTER TABLE estimates DROP COLUMN scope_id")
        connection.exec_driver_sql("DROP INDEX ix_documents_scope_created_at")
        connection.exec_driver_sql("DROP INDEX ix_documents_scope_status")
        connection.exec_driver_sql("ALTER TABLE documents DROP COLUMN scope_id")
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
            "INSERT INTO documents "
            "(id, title, type, status, client, project, content, variables, template, "
            "estimate_id, created_at, updated_at) "
            "VALUES ('document_1', 'Legacy document', 'contract', 'draft', '', '', "
            "'private legacy content', '{}', '', 'estimate_1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
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
        assert revision == "025_normative_source_claims"
        assert MigrationContext.configure(connection).get_current_revision() == "025_normative_source_claims"
        assert "tax_regime" in {
            column["name"] for column in sa.inspect(connection).get_columns("estimates")
        }
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
            "last_used_at", "revoked_at", "organization_id",
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
            "scope_id", "estimate_status", "pricing_status", "scope_status", "source_note",
            "assumptions", "questions", "price_sources", "evidence_issues",
            "client_record_id", "object_record_id",
        }.issubset({
            column["name"] for column in sa.inspect(connection).get_columns("estimates")
        })
        assert {"clients", "construction_objects"}.issubset(
            sa.inspect(connection).get_table_names()
        )
        scope_column = next(
            column
            for column in sa.inspect(connection).get_columns("estimates")
            if column["name"] == "scope_id"
        )
        assert scope_column["nullable"] is False
        assert connection.execute(sa.text(
            "SELECT scope_id FROM estimates WHERE id = 'estimate_1'"
        )).scalar_one() == "legacy:quarantined"
        document_columns = {
            column["name"] for column in sa.inspect(connection).get_columns("documents")
        }
        assert {"scope_id", "estimate_id"}.issubset(document_columns)
        document_scope_column = next(
            column
            for column in sa.inspect(connection).get_columns("documents")
            if column["name"] == "scope_id"
        )
        assert document_scope_column["nullable"] is False
        assert connection.execute(sa.text(
            "SELECT scope_id FROM documents WHERE id = 'document_1'"
        )).scalar_one() == "legacy:quarantined"
        assert "price_evidence" in {
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
            "SELECT version, snapshot FROM estimate_revisions "
            "WHERE estimate_id = 'estimate_1' AND version = 4"
        )).mappings().one()
        assert backfilled["version"] == 4
        snapshot = backfilled["snapshot"]
        if isinstance(snapshot, str):
            import json
            snapshot = json.loads(snapshot)
        assert snapshot["total"] == "122.00"
        assert snapshot["sections"][0]["positions"][0]["sum"] == "100.00"
        assert snapshot["estimate_status"] == "preliminary"
        assert snapshot["pricing_status"] == "preliminary"
        assert snapshot["scope_status"] == "unverified"
        assert snapshot["price_sources"] == []
        assert snapshot["sections"][0]["positions"][0]["price_evidence"] == []
        assert connection.execute(sa.text(
            "SELECT version FROM project_messages WHERE id = 'message_1'"
        )).scalar_one() == 1
    with Session(engine) as session:
        assert DBStorage(session, scope_id="anon:other-session").get_estimate(
            "estimate_1"
        ) is None
        assert DBStorage(session, scope_id="anon:other-session").get_document(
            "document_1"
        ) is None
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
        assert runner_stdout.strip().endswith("025_normative_source_claims")
    finally:
        release_path.touch(exist_ok=True)
        for process in (runner, holder):
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
