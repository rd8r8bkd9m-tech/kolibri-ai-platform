"""Runtime proof for the estimate and document editor verticals."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai_provider import _capability_self_description
from app.capability_runtime import capability_by_id
from app.database import Base, get_db
from app.main import app
from app.storage import DBStorage


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            bootstrap = test_client.post("/api/v1/shell/bootstrap")
            assert bootstrap.status_code == 200, bootstrap.text
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_verticals_promote_only_after_real_persisted_endpoint_invocation(client):
    assert capability_by_id("estimate.create")["status"] == "degraded"
    assert capability_by_id("document.editor")["status"] == "degraded"

    estimate = client.post(
        "/api/v1/estimates",
        json={"title": "Смета: доказательство capability", "sections": []},
    )
    document = client.post(
        "/api/v1/documents",
        json={"title": "Документ: доказательство capability", "content": "Сохранено"},
    )

    assert estimate.status_code == 201, estimate.text
    assert document.status_code == 201, document.text
    assert client.get(f"/api/v1/estimates/{estimate.json()['id']}").status_code == 200
    assert client.get(f"/api/v1/documents/{document.json()['id']}").status_code == 200
    assert capability_by_id("estimate.create")["status"] == "available"
    assert capability_by_id("document.editor")["status"] == "available"

    self_description = _capability_self_description()
    available_ids = {
        item["id"] for item in self_description["capabilities"]["available"]
    }
    assert {"estimate.create", "document.editor"} <= available_ids


@pytest.mark.parametrize(
    ("capability_id", "method_name", "path", "payload", "private_value"),
    [
        (
            "estimate.create",
            "create_estimate",
            "/api/v1/estimates",
            {"title": "SECRET-ESTIMATE", "sections": []},
            "SECRET-ESTIMATE",
        ),
        (
            "document.editor",
            "create_document",
            "/api/v1/documents",
            {"title": "SECRET-DOCUMENT", "content": "PRIVATE-CONTENT"},
            "SECRET-DOCUMENT",
        ),
    ],
)
def test_vertical_runtime_failure_is_sanitised_and_never_claimed_available(
    monkeypatch,
    client,
    capability_id,
    method_name,
    path,
    payload,
    private_value,
):
    def fail_storage(*_args, **_kwargs):
        raise RuntimeError("secret upstream diagnostic")

    monkeypatch.setattr(DBStorage, method_name, fail_storage)
    with pytest.raises(RuntimeError, match="secret upstream diagnostic"):
        client.post(path, json=payload)

    capability = capability_by_id(capability_id)
    assert capability["status"] == "unavailable"
    assert capability["invocable"] is False
    assert capability["reason"]["code"] == "invocation_failed"

    ledger = Path(os.environ["KOLIBRI_CAPABILITY_PROBE_FILE"])
    stored = ledger.read_text(encoding="utf-8")
    assert private_value not in stored
    assert "PRIVATE-CONTENT" not in stored
    assert "secret upstream diagnostic" not in stored
