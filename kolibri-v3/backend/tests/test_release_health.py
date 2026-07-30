from __future__ import annotations

from dataclasses import replace
import json
import logging
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.database import connect_database
from app.main import create_app
from app.runtime_readiness import (
    clear_product_worker_heartbeat,
    record_product_worker_heartbeat,
)


RELEASE_ID = "kolibri-v3-0123456789ab-abcdef012345"
RELEASE_COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _settings(database_path: Path, *, environment: str) -> Settings:
    return replace(
        Settings.for_testing(database_url=database_path),
        environment=environment,
        cookie_secure=environment == "production",
        allowed_origins=(
            ("https://kolibriai.test",)
            if environment == "production"
            else ("http://testserver",)
        ),
    )


def test_development_health_is_unversioned_without_release_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KOLIBRI_RELEASE_ID", raising=False)
    monkeypatch.delenv("KOLIBRI_RELEASE_COMMIT", raising=False)
    with TestClient(
        create_app(_settings(tmp_path / "dev.db", environment="development"))
    ) as client:
        response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "kolibri-v3"}
    assert response.headers["X-Kolibri-Release"] == "unversioned"
    assert response.headers["X-Request-ID"].startswith("req_")


def test_liveness_does_not_depend_on_database_or_release_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KOLIBRI_RELEASE_ID", raising=False)
    monkeypatch.delenv("KOLIBRI_RELEASE_COMMIT", raising=False)
    with TestClient(
        create_app(_settings(tmp_path / "live.db", environment="production"))
    ) as client:
        live = client.get("/v1/live")
        ready = client.get("/v1/ready")

    assert live.status_code == 200
    assert live.json() == {
        "status": "ok",
        "service": "kolibri-v3",
        "component": "backend",
    }
    assert ready.status_code == 503
    assert ready.json()["code"] == "release_identity_not_configured"


def test_release_health_reports_exact_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KOLIBRI_RELEASE_ID", RELEASE_ID)
    monkeypatch.setenv("KOLIBRI_RELEASE_COMMIT", RELEASE_COMMIT)
    with TestClient(
        create_app(_settings(tmp_path / "release.db", environment="production"))
    ) as client:
        response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "kolibri-v3",
        "releaseId": RELEASE_ID,
        "releaseCommit": RELEASE_COMMIT,
    }
    assert response.headers["X-Kolibri-Release"] == RELEASE_ID


def test_full_readiness_requires_exact_fresh_product_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "worker-ready.db"
    monkeypatch.setenv("KOLIBRI_RELEASE_ID", RELEASE_ID)
    monkeypatch.setenv("KOLIBRI_RELEASE_COMMIT", RELEASE_COMMIT)
    monkeypatch.setenv("KOLIBRI_V3_REQUIRE_PRODUCT_WORKER", "true")
    monkeypatch.setenv("KOLIBRI_V3_WORKER_HEARTBEAT_TTL_SECONDS", "30")
    settings = _settings(database_path, environment="production")

    with TestClient(create_app(settings)) as client:
        assert client.get("/v1/health").status_code == 200
        missing = client.get("/v1/ready")
        assert missing.status_code == 503
        assert missing.json()["code"] == "product_worker_not_ready"

        record_product_worker_heartbeat(
            settings.database_url,
            instance_id="product-worker-test-01",
        )
        ready = client.get("/v1/ready")
        assert ready.status_code == 200
        assert ready.json()["releaseId"] == RELEASE_ID

        clear_product_worker_heartbeat(
            settings.database_url,
            instance_id="product-worker-test-01",
        )
        stopped = client.get("/v1/ready")
        assert stopped.status_code == 503
        assert stopped.json()["code"] == "product_worker_not_ready"


def test_health_rejects_database_schema_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "schema-drift.db"
    monkeypatch.setenv("KOLIBRI_RELEASE_ID", RELEASE_ID)
    monkeypatch.setenv("KOLIBRI_RELEASE_COMMIT", RELEASE_COMMIT)
    settings = _settings(database_path, environment="production")

    with TestClient(create_app(settings)) as client:
        database = connect_database(settings.database_url)
        try:
            database.execute("PRAGMA user_version = 43")
        finally:
            database.close()

        response = client.get("/v1/health")

    assert response.status_code == 503
    assert response.json()["code"] == "database_not_ready"


def test_http_log_is_structured_and_excludes_query_cookie_and_raw_path_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("KOLIBRI_RELEASE_ID", raising=False)
    monkeypatch.delenv("KOLIBRI_RELEASE_COMMIT", raising=False)
    caplog.set_level(logging.INFO, logger="kolibri.v3.http")
    with TestClient(
        create_app(_settings(tmp_path / "log.db", environment="development"))
    ) as client:
        response = client.get(
            "/v1/live?token=never-log-this",
            headers={"Cookie": "session=never-log-this-cookie"},
        )

    records = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "kolibri.v3.http"
    ]
    assert len(records) == 1
    assert records[0]["event"] == "http_request_complete"
    assert records[0]["route"] == "/v1/live"
    assert records[0]["releaseId"] == "unversioned"
    assert records[0]["requestId"] == response.headers["X-Request-ID"]
    serialized = json.dumps(records[0])
    assert "never-log-this" not in serialized
    assert "cookie" not in serialized.casefold()


@pytest.mark.parametrize(
    ("release_id", "release_commit"),
    (
        (None, None),
        (RELEASE_ID, None),
        (None, RELEASE_COMMIT),
        (" kolibri-v3-invalid", RELEASE_COMMIT),
        (RELEASE_ID, RELEASE_COMMIT.upper()),
    ),
)
def test_production_health_rejects_missing_or_invalid_release_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    release_id: str | None,
    release_commit: str | None,
) -> None:
    if release_id is None:
        monkeypatch.delenv("KOLIBRI_RELEASE_ID", raising=False)
    else:
        monkeypatch.setenv("KOLIBRI_RELEASE_ID", release_id)
    if release_commit is None:
        monkeypatch.delenv("KOLIBRI_RELEASE_COMMIT", raising=False)
    else:
        monkeypatch.setenv("KOLIBRI_RELEASE_COMMIT", release_commit)

    with TestClient(
        create_app(_settings(tmp_path / "invalid.db", environment="production"))
    ) as client:
        response = client.get("/v1/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "service": "kolibri-v3",
        "code": "release_identity_not_configured",
    }
