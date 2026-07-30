"""Hermetic defaults for backend tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture(autouse=True)
def disable_live_estimate_price_collection(monkeypatch, tmp_path):
    """Unit tests never depend on live estimate price collection.

    The official adapter has its own MockTransport contract tests.  Production
    keeps collection enabled by default and the release manifest pins it on.
    """

    monkeypatch.setenv("KOLIBRI_ESTIMATE_FGIS_ENABLED", "false")
    monkeypatch.setenv("KOLIBRI_ESTIMATE_COMMERCIAL_FALLBACK_ENABLED", "false")
    # Runtime proof and artifact tests must never mutate the repository data
    # directory or leak evidence between tests.
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv(
        "KOLIBRI_CAPABILITY_PROBE_FILE",
        str(tmp_path / "runtime" / "capability-probes.json"),
    )
    # The application now rejects the known development JWT secret whenever a
    # release identity is present.  Tests use an explicit non-production key so
    # every TestClient exercises the production startup gate hermetically.
    from app import auth
    monkeypatch.setattr(auth, "SECRET_KEY", "pytest-jwt-secret-0123456789abcdef0123456789")

    # TestClient is a browser stand-in. Real same-origin browser writes carry
    # Fetch Metadata; keep the shared test harness faithful so anonymous-cookie
    # CSRF protection can stay strict in production.
    original_init = TestClient.__init__

    def same_origin_init(self, *args, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("sec-fetch-site", "same-origin")
        kwargs["headers"] = headers
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(TestClient, "__init__", same_origin_init)

    # Public Responses use their own durable SQL tables.  Keep those tables
    # hermetic per test instead of mutating a developer's local kolibri.db.
    from app import response_store
    from app.models import PublicResponseDB, PublicResponseEventDB

    response_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    PublicResponseDB.__table__.create(bind=response_engine)
    PublicResponseEventDB.__table__.create(bind=response_engine)
    testing_session = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=response_engine,
    )
    monkeypatch.setattr(response_store, "SessionLocal", testing_session)
    yield
    response_engine.dispose()
