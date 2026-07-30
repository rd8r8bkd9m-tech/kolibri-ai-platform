from __future__ import annotations

import importlib.util
from pathlib import Path
import sqlite3
import sys


BACKEND = Path(__file__).parents[3]
SCRIPT = Path(__file__).parents[1] / "kolibri_p7_migrate.py"
SPEC = importlib.util.spec_from_file_location("kolibri_p7_migrate", SCRIPT)
assert SPEC and SPEC.loader
migrate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = migrate
SPEC.loader.exec_module(migrate)


def test_migration_helper_reaches_exact_012_head_and_checks_integrity(tmp_path: Path, monkeypatch):
    monkeypatch.syspath_prepend(str(BACKEND))
    from app.database import Base
    from app import models  # noqa: F401
    from sqlalchemy import create_engine

    database = tmp_path / "candidate.db"
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    engine.dispose()

    result = migrate.migrate(database)

    assert result["status"] == "migrated_verified"
    assert result["schema_head"] == "012_estimate_tax_regime"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "012_estimate_tax_regime",
        )
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
