"""Hermetic defaults for backend tests."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture(autouse=True)
def disable_live_estimate_price_collection(monkeypatch, tmp_path):
    """Unit tests never depend on the live FGIS CS portal.

    The official adapter has its own MockTransport contract tests.  Production
    keeps collection enabled by default and the release manifest pins it on.
    """

    monkeypatch.setenv("KOLIBRI_ESTIMATE_FGIS_ENABLED", "false")
    # Runtime proof and artifact tests must never mutate the repository data
    # directory or leak evidence between tests.
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv(
        "KOLIBRI_CAPABILITY_PROBE_FILE",
        str(tmp_path / "runtime" / "capability-probes.json"),
    )

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
