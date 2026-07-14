from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.browser_session import SESSION_COOKIE_NAME, issue_anonymous_session
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
    with TestClient(app) as test_client:
        bootstrap = test_client.post("/api/v1/shell/bootstrap")
        assert bootstrap.status_code == 200, bootstrap.text
        yield test_client, testing_session
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def estimate_payload() -> dict:
    return {
        "title": "Private estimate",
        "object_name": "Private object",
        "region": "Татарстан",
        "sections": [
            {
                "title": "Works",
                "positions": [
                    {
                        "code": "W-1",
                        "name": "Private work",
                        "unit": "шт",
                        "quantity": "1",
                        "price": "100",
                    }
                ],
            }
        ],
    }


def document_payload(*, estimate_id: str | None = None, title: str = "Private document") -> dict:
    return {
        "title": title,
        "type": "contract",
        "client": "Private client",
        "project": "Private project",
        "content": "<h1>Private document</h1><p>Tenant-only content.</p>",
        "variables": {"private": "value"},
        "template": "",
        "estimate_id": estimate_id,
    }


def test_document_crud_exports_library_and_analysis_are_session_isolated(
    client,
    monkeypatch,
):
    test_client, _session_factory = client
    owner_token = test_client.cookies.get(SESSION_COOKIE_NAME)
    assert owner_token

    estimate = test_client.post("/api/v1/estimates", json=estimate_payload()).json()
    created_response = test_client.post(
        "/api/v1/documents",
        json=document_payload(estimate_id=estimate["id"]),
    )
    assert created_response.status_code == 201, created_response.text
    document = created_response.json()

    owner_library = test_client.get("/api/v1/library")
    assert owner_library.status_code == 200, owner_library.text
    assert {
        (item["item_type"], item["source_id"])
        for item in owner_library.json()["items"]
    } == {("estimate", estimate["id"]), ("document", document["id"])}

    other_token, _other_session = issue_anonymous_session()
    test_client.cookies.clear()
    test_client.cookies.set(SESSION_COOKIE_NAME, other_token)

    listed = test_client.get("/api/v1/documents")
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"] == []
    assert listed.json()["total"] == 0
    assert test_client.get("/api/v1/library").json()["items"] == []
    isolated_search = test_client.post(
        "/api/v1/search",
        json={"query": "Private", "types": ["estimates", "documents", "positions"]},
    )
    assert isolated_search.status_code == 200, isolated_search.text
    assert isolated_search.json()["results"] == []

    isolated_requests = [
        test_client.get(f"/api/v1/documents/{document['id']}"),
        test_client.put(
            f"/api/v1/documents/{document['id']}",
            json={"title": "cross-session overwrite"},
        ),
        test_client.delete(f"/api/v1/documents/{document['id']}"),
        test_client.get(f"/api/v1/documents/{document['id']}/pdf"),
        test_client.get(f"/api/v1/documents/{document['id']}/docx"),
        test_client.post(f"/api/v1/ai/analyze-estimate?est_id={estimate['id']}"),
        test_client.post(
            "/api/v1/documents",
            json=document_payload(estimate_id=estimate["id"], title="foreign link"),
        ),
    ]
    assert [response.status_code for response in isolated_requests] == [404] * len(
        isolated_requests
    )

    other_document = test_client.post(
        "/api/v1/documents",
        json=document_payload(title="Other document"),
    )
    assert other_document.status_code == 201, other_document.text
    other_document_id = other_document.json()["id"]
    other_library = test_client.get("/api/v1/library").json()["items"]
    assert [(item["item_type"], item["source_id"]) for item in other_library] == [
        ("document", other_document_id)
    ]

    test_client.cookies.clear()
    test_client.cookies.set(SESSION_COOKIE_NAME, owner_token)

    owner_read = test_client.get(f"/api/v1/documents/{document['id']}")
    assert owner_read.status_code == 200, owner_read.text
    assert owner_read.json() == document
    assert test_client.get(f"/api/v1/documents/{other_document_id}").status_code == 404
    owner_search = test_client.post(
        "/api/v1/search",
        json={"query": "Private", "types": ["estimates", "documents", "positions"]},
    )
    assert owner_search.status_code == 200, owner_search.text
    assert {
        (item["entity_type"], item["id"])
        for item in owner_search.json()["results"]
    } == {
        ("estimates", estimate["id"]),
        ("documents", document["id"]),
        ("positions", estimate["sections"][0]["positions"][0]["id"]),
    }

    pdf = test_client.get(f"/api/v1/documents/{document['id']}/pdf")
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-")

    docx = test_client.get(f"/api/v1/documents/{document['id']}/docx")
    assert docx.status_code == 200, docx.text
    assert docx.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert docx.content.startswith(b"PK\x03\x04")
    assert len(docx.content) > 1_000
    with zipfile.ZipFile(io.BytesIO(docx.content)) as archive:
        assert archive.testzip() is None
        assert "[Content_Types].xml" in archive.namelist()
        assert "word/document.xml" in archive.namelist()
        assert b"Tenant-only content." in archive.read("word/document.xml")

    async def fake_analyze_estimate(payload: dict) -> dict:
        assert payload["id"] == estimate["id"]
        return {"content": "owner-only analysis", "actions": [], "status": "ok"}

    monkeypatch.setattr("app.ai_provider.analyze_estimate", fake_analyze_estimate)
    analyzed = test_client.post(
        f"/api/v1/ai/analyze-estimate?est_id={estimate['id']}"
    )
    assert analyzed.status_code == 200, analyzed.text
    assert analyzed.json()["content"] == "owner-only analysis"


def test_document_and_library_routes_fail_closed_without_principal(client):
    _owner_client, _session_factory = client
    with TestClient(app) as unbootstrapped:
        requests = [
            unbootstrapped.get("/api/v1/documents"),
            unbootstrapped.post("/api/v1/documents", json=document_payload()),
            unbootstrapped.get("/api/v1/documents/unknown"),
            unbootstrapped.put("/api/v1/documents/unknown", json={"title": "x"}),
            unbootstrapped.delete("/api/v1/documents/unknown"),
            unbootstrapped.get("/api/v1/documents/unknown/pdf"),
            unbootstrapped.get("/api/v1/documents/unknown/docx"),
            unbootstrapped.get("/api/v1/library"),
            unbootstrapped.post("/api/v1/search", json={"query": "private"}),
            unbootstrapped.post("/api/v1/templates/contract/create-document"),
            unbootstrapped.post("/api/v1/ai/analyze-estimate?est_id=unknown"),
        ]
    assert [response.status_code for response in requests] == [428] * len(requests)


def test_document_storage_requires_scope_and_rejects_foreign_estimate_link(client):
    _test_client, session_factory = client
    with session_factory() as db:
        with pytest.raises(RuntimeError, match="document storage requires"):
            DBStorage(db).list_documents()
        with pytest.raises(RuntimeError, match="document storage requires"):
            DBStorage(db).list_library()

        owner = DBStorage(db, scope_id="anon:owner")
        foreign = DBStorage(db, scope_id="anon:foreign")
        estimate = owner.create_estimate(estimate_payload())
        with pytest.raises(RuntimeError, match="linked estimate is not available"):
            foreign.create_document(document_payload(estimate_id=estimate["id"]))


def test_template_documents_are_created_inside_current_scope(client):
    test_client, _session_factory = client
    created = test_client.post("/api/v1/templates/contract/create-document")
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]

    other_token, _other_session = issue_anonymous_session()
    test_client.cookies.clear()
    test_client.cookies.set(SESSION_COOKIE_NAME, other_token)
    assert test_client.get(f"/api/v1/documents/{document_id}").status_code == 404
    assert test_client.get("/api/v1/documents").json()["items"] == []
