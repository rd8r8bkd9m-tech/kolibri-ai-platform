from __future__ import annotations

import hashlib
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from artifact_runtime import EstimateSpec, deterministic_estimate
from estimate_artifacts import EstimateArtifactStore
from public_responses_api import PublicResponseStore
from sqlite_lifecycle import closing_sqlite_transaction


class _TrackedConnection(sqlite3.Connection):
    opened = 0
    closed = 0
    live = 0
    peak_live = 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lifecycle_closed = False
        type(self).opened += 1
        type(self).live += 1
        type(self).peak_live = max(type(self).peak_live, type(self).live)

    def close(self) -> None:
        if not self._lifecycle_closed:
            self._lifecycle_closed = True
            type(self).closed += 1
            type(self).live -= 1
        super().close()

    @classmethod
    def reset(cls) -> None:
        cls.opened = 0
        cls.closed = 0
        cls.live = 0
        cls.peak_live = 0


@pytest.fixture
def tracked_sqlite(monkeypatch: pytest.MonkeyPatch):
    original_connect = sqlite3.connect
    _TrackedConnection.reset()

    def connect(*args, **kwargs):
        kwargs["factory"] = _TrackedConnection
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect)
    return _TrackedConnection


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _estimate_spec() -> EstimateSpec:
    return EstimateSpec.model_validate(
        {
            "title": "Тестовая смета жизненного цикла SQLite",
            "currency": "RUB",
            "minor_unit": 2,
            "region": "Республика Татарстан",
            "client_name": "Тестовый заказчик",
            "object_name": "Одноэтажный дом",
            "source_summary": "Тестовые данные; не коммерческое предложение",
            "assumptions": ["Цена используется только для regression-теста."],
            "questions": [],
            "lines": [
                {
                    "id": "labor-1",
                    "section": "Подготовка",
                    "description": "Разметка участка",
                    "category": "labor",
                    "unit": "компл.",
                    "quantity": "1",
                    "unit_price_minor": 100_000,
                    "provenance": {
                        "source": "assumption",
                        "source_ref": "Тестовая цена",
                    },
                }
            ],
            "overhead_rate_bps": 0,
            "tax_rate_bps": 0,
        }
    )


def test_closing_sqlite_transaction_commits_rolls_back_and_closes(
    tmp_path: Path,
    tracked_sqlite: type[_TrackedConnection],
) -> None:
    db_path = tmp_path / "transaction.db"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(db_path)

    with closing_sqlite_transaction(connect) as connection:
        connection.execute("CREATE TABLE values_under_test(value TEXT NOT NULL)")
        connection.execute("INSERT INTO values_under_test(value) VALUES ('committed')")

    with pytest.raises(RuntimeError, match="rollback sentinel"):
        with closing_sqlite_transaction(connect) as connection:
            connection.execute("INSERT INTO values_under_test(value) VALUES ('rolled-back')")
            raise RuntimeError("rollback sentinel")

    with closing_sqlite_transaction(connect) as connection:
        values = [row[0] for row in connection.execute("SELECT value FROM values_under_test")]

    assert values == ["committed"]
    assert tracked_sqlite.live == 0
    assert tracked_sqlite.opened == tracked_sqlite.closed == 3


def test_public_project_and_estimate_stores_do_not_accumulate_connections(
    tmp_path: Path,
    tracked_sqlite: type[_TrackedConnection],
) -> None:
    db_path = tmp_path / "kolibri.db"
    public_store = PublicResponseStore(db_path)
    estimate_store = EstimateArtifactStore(db_path, tmp_path / "estimate-artifacts")
    assert tracked_sqlite.live == 0

    session, token = public_store.issue("http://testserver", ttl_seconds=900)
    project_id = "project_connection_lifecycle"
    project_request_sha = _sha("project_connection_lifecycle")
    project, created = public_store.create_project(
        session,
        project_id=project_id,
        idempotency_key="project-connection-lifecycle",
        request_sha256=project_request_sha,
        title="Проверка соединений",
        metadata={"test": True},
    )
    assert created is True
    assert project["id"] == project_id

    spec = _estimate_spec()
    calculation = deterministic_estimate(spec)
    estimate = estimate_store.persist(
        session=session,
        response_id="response_connection_lifecycle",
        spec=spec,
        calculation=calculation,
        estimate_id=None,
        base_version=None,
        materialize_pdf=True,
    )
    artifact_id = estimate["artifacts"][0]["id"]
    assert tracked_sqlite.live == 0

    opened_before_sync = tracked_sqlite.opened
    for _ in range(40):
        assert public_store.resolve(token) is not None
        assert public_store.list_projects(session["id"])
        assert public_store.get_project(session["id"], project_id) is not None
        assert public_store.list_messages(session["id"], project_id) == []
        repeated, repeated_created = public_store.create_project(
            session,
            project_id=project_id,
            idempotency_key="project-connection-lifecycle",
            request_sha256=project_request_sha,
            title="Проверка соединений",
            metadata={"test": True},
        )
        assert repeated_created is False
        assert repeated["id"] == project_id

        current = estimate_store.get_estimate(session["id"], estimate["id"])
        assert current is not None
        assert estimate_store.list_versions(session["id"], estimate["id"])
        artifact = estimate_store.artifact_content(session["id"], artifact_id)
        assert artifact is not None

        # Every API-style operation has returned, so no short-lived database
        # descriptor may remain owned by either compatibility store.
        assert tracked_sqlite.live == 0

    assert tracked_sqlite.opened > opened_before_sync + 100
    assert tracked_sqlite.opened == tracked_sqlite.closed
    assert tracked_sqlite.peak_live == 1
