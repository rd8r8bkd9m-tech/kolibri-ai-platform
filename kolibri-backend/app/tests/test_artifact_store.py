import base64
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import artifact_store
from app.artifact_store import (
    ArtifactConflict,
    ArtifactIntegrityError,
    ArtifactStore,
    ArtifactValidationError,
)
from app.browser_session import SESSION_COOKIE_NAME, validate_anonymous_session
from app.main import app


_PDF_V1 = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
_PDF_V2 = b"%PDF-1.4\n1 0 obj\n<</Title (revision 2)>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _bootstrap_scope_key(client: TestClient) -> str:
    bootstrap = client.post("/api/v1/shell/bootstrap")
    assert bootstrap.status_code == 200
    session = validate_anonymous_session(client.cookies.get(SESSION_COOKIE_NAME))
    assert session is not None
    return hashlib.sha256(session.scope_id.encode()).hexdigest()


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "artifacts")


def test_bytes_manifest_and_metadata_survive_store_restart(store: ArtifactStore):
    created = store.put_bytes(
        _PDF_V1,
        artifact_type="estimate_pdf",
        mime_type="application/pdf",
        filename="Смета дома.pdf",
        title="Смета дома",
        metadata={"estimate_id": "est-1", "source_revision": 7},
    )

    reopened_store = ArtifactStore(store.root)
    persisted = reopened_store.open(created["id"])
    reopen = reopened_store.reopen(created["id"])

    assert persisted.content == _PDF_V1
    assert persisted.manifest["mime_type"] == "application/pdf"
    assert persisted.manifest["size_bytes"] == len(_PDF_V1)
    assert persisted.manifest["sha256"] == hashlib.sha256(_PDF_V1).hexdigest()
    assert persisted.manifest["metadata"] == {"estimate_id": "est-1", "source_revision": 7}
    assert persisted.manifest["revision"] == 1
    assert reopen["revision"] == 1
    assert reopen["content_url"].endswith("?revision=1")
    assert reopen["download_url"].endswith("?revision=1&download=true")
    assert reopen["integrity"] == {
        "algorithm": "sha256",
        "digest": created["sha256"],
    }


def test_history_is_immutable_and_updates_require_compare_and_swap(store: ArtifactStore):
    first = store.put_bytes(
        _PDF_V1,
        artifact_type="estimate_pdf",
        mime_type="application/pdf",
        filename="estimate.pdf",
        metadata={"estimate_revision": 1},
    )
    second = store.put_bytes(
        _PDF_V2,
        artifact_id=first["id"],
        expected_revision=1,
        artifact_type="estimate_pdf",
        mime_type="application/pdf",
        filename="estimate.pdf",
        metadata={"estimate_revision": 2},
    )

    history = store.history(first["id"])

    assert [item["revision"] for item in history] == [1, 2]
    assert history[0]["sha256"] == hashlib.sha256(_PDF_V1).hexdigest()
    assert history[0]["metadata"] == {"estimate_revision": 1}
    assert history[1]["sha256"] == hashlib.sha256(_PDF_V2).hexdigest()
    assert store.open(first["id"], revision=1).content == _PDF_V1
    assert store.open(first["id"], revision=2).content == _PDF_V2
    assert second["revision"] == 2

    with pytest.raises(ArtifactConflict, match="artifact_revision_conflict"):
        store.put_bytes(
            _PDF_V2,
            artifact_id=first["id"],
            expected_revision=1,
            artifact_type="estimate_pdf",
            mime_type="application/pdf",
            filename="estimate.pdf",
        )


def test_identical_content_uses_one_cas_blob(store: ArtifactStore):
    first = store.put_bytes(
        _PDF_V1,
        artifact_type="document",
        mime_type="application/pdf",
        filename="first.pdf",
    )
    second = store.put_bytes(
        _PDF_V1,
        artifact_type="document",
        mime_type="application/pdf",
        filename="second.pdf",
    )

    blobs = [path for path in (store.root / "blobs" / "sha256").rglob("*") if path.is_file()]
    assert first["id"] != second["id"]
    assert first["sha256"] == second["sha256"]
    assert len(blobs) == 1


def test_internal_list_returns_committed_heads_and_filters_type(store: ArtifactStore):
    document = store.put_bytes(
        _PDF_V1,
        artifact_type="document",
        mime_type="application/pdf",
        filename="document.pdf",
        metadata={"project_id": "project-a", "kind": "document"},
    )
    estimate = store.put_bytes(
        _PDF_V2,
        artifact_type="estimate_pdf",
        mime_type="application/pdf",
        filename="estimate.pdf",
        metadata={"project_id": "project-b", "kind": "estimate"},
    )

    all_items = store.list()
    estimates = store.list(artifact_type="estimate_pdf")
    project_b = store.list(metadata={"project_id": "project-b"})

    assert {item["id"] for item in all_items} == {document["id"], estimate["id"]}
    assert [item["id"] for item in estimates] == [estimate["id"]]
    assert [item["id"] for item in project_b] == [estimate["id"]]
    assert all(item["revision"] == 1 for item in all_items)

    with pytest.raises(ArtifactValidationError, match="artifact_list_limit_invalid"):
        store.list(limit=0)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("artifact_id", "../../etc/passwd", "artifact_id_invalid"),
        ("filename", "../../secret.pdf", "artifact_filename_invalid"),
        ("filename", "folder\\secret.pdf", "artifact_filename_invalid"),
        ("route_prefix", "/api/v1/artifacts/../../admin", "artifact_route_prefix_invalid"),
    ],
)
def test_path_traversal_inputs_are_rejected(
    store: ArtifactStore,
    field: str,
    value: str,
    error: str,
):
    arguments = {
        "artifact_type": "document",
        "mime_type": "application/pdf",
        "filename": "safe.pdf",
    }
    arguments[field] = value
    with pytest.raises(ArtifactValidationError, match=error):
        store.put_bytes(_PDF_V1, **arguments)


def test_mime_is_derived_from_bytes_and_false_claims_are_rejected(store: ArtifactStore):
    inferred = store.put_bytes(
        _PDF_V1,
        artifact_type="document",
        filename="estimate.bin",
    )
    assert inferred["mime_type"] == "application/pdf"

    with pytest.raises(ArtifactValidationError, match="artifact_mime_mismatch"):
        store.put_bytes(
            _PDF_V1,
            artifact_type="document",
            mime_type="image/png",
            filename="fake.png",
        )

    with pytest.raises(ArtifactValidationError, match="artifact_json_invalid"):
        store.put_bytes(
            b"not-json",
            artifact_type="data",
            mime_type="application/json",
            filename="fake.json",
        )


def test_corrupted_blob_is_never_served(store: ArtifactStore):
    created = store.put_bytes(
        _PDF_V1,
        artifact_type="document",
        mime_type="application/pdf",
        filename="estimate.pdf",
    )
    blob = store._blob_path(created["sha256"])
    blob.write_bytes(b"tampered")

    with pytest.raises(ArtifactIntegrityError, match="artifact_blob_integrity_failed"):
        store.open(created["id"])
    with pytest.raises(ArtifactIntegrityError, match="artifact_blob_integrity_failed"):
        store.reopen(created["id"])
    with pytest.raises(ArtifactIntegrityError, match="artifact_blob_integrity_failed"):
        store.history(created["id"])


def test_failed_atomic_head_switch_leaves_previous_revision_reopenable(
    store: ArtifactStore,
    monkeypatch: pytest.MonkeyPatch,
):
    first = store.put_bytes(
        _PDF_V1,
        artifact_type="document",
        mime_type="application/pdf",
        filename="estimate.pdf",
    )
    real_replace = artifact_store.os.replace

    def fail_head_switch(source, target):
        if Path(target).name == "head.json":
            raise OSError("simulated head switch failure")
        return real_replace(source, target)

    monkeypatch.setattr(artifact_store.os, "replace", fail_head_switch)
    with pytest.raises(OSError, match="simulated head switch failure"):
        store.put_bytes(
            _PDF_V2,
            artifact_id=first["id"],
            expected_revision=1,
            artifact_type="document",
            mime_type="application/pdf",
            filename="estimate.pdf",
        )

    assert store.get(first["id"])["revision"] == 1
    assert store.open(first["id"]).content == _PDF_V1
    assert [item["revision"] for item in store.history(first["id"])] == [1]


def test_generic_download_reopen_and_history_http_contracts(monkeypatch, tmp_path):
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path / "http-artifacts"))
    with TestClient(app) as client:
        scope_key = _bootstrap_scope_key(client)
        created = artifact_store.get_artifact_store().put_bytes(
            _PDF_V1,
            artifact_type="estimate_pdf",
            mime_type="application/pdf",
            filename="Смета дома.pdf",
            metadata={"estimate_id": "est-http", "scope_key": scope_key},
        )
        content = client.get(created["url"])
        download = client.get(created["download_url"])
        reopen = client.get(created["reopen_url"])
        history = client.get(created["history_url"])

    assert content.status_code == 200
    assert content.content == _PDF_V1
    assert content.headers["content-type"] == "application/pdf"
    assert content.headers["etag"] == f'"{created["sha256"]}"'
    assert content.headers["x-artifact-revision"] == "1"
    assert "content-disposition" not in content.headers
    assert download.status_code == 200
    assert "attachment" in download.headers["content-disposition"]
    assert reopen.status_code == 200
    assert reopen.json()["artifact"]["metadata"] == {
        "estimate_id": "est-http",
        "scope_key": scope_key,
    }
    assert reopen.json()["integrity"]["digest"] == created["sha256"]
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["id"] == created["id"]


def test_public_image_manifests_hide_topology_without_mutating_cas_or_non_image_contracts(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path / "http-artifacts"))
    with TestClient(app) as client:
        scope_key = _bootstrap_scope_key(client)
        store = artifact_store.get_artifact_store()
        private_image_metadata = {
            "prompt": "Жёлтая канарейка",
            "width": 1,
            "height": 1,
            "model": "private-image-model",
            "provider": "private-image-provider",
            "topology": {"node": "private-node", "route": "private-route"},
            "scope_key": scope_key,
        }
        image = store.put_bytes(
            _PNG_1X1,
            artifact_type="image",
            mime_type="image/png",
            filename="canary.png",
            metadata=private_image_metadata,
        )
        image_reopen = client.get(image["reopen_url"])
        image_history = client.get(image["history_url"])

        private_document_metadata = {
            "provider": "document-producer",
            "model": "document-layout-v1",
            "topology": {"page_engine": "a4"},
            "scope_key": scope_key,
        }
        document = store.put_bytes(
            b"Non-image artifact",
            artifact_type="document.txt",
            mime_type="text/plain",
            filename="document.txt",
            metadata=private_document_metadata,
        )
        document_reopen = client.get(document["reopen_url"])
        document_history = client.get(document["history_url"])

    assert image_reopen.status_code == 200
    assert image_history.status_code == 200
    expected_public_metadata = {
        "prompt": "Жёлтая канарейка",
        "width": 1,
        "height": 1,
    }
    assert image_reopen.json()["artifact"]["metadata"] == expected_public_metadata
    assert image_history.json()["items"][0]["metadata"] == expected_public_metadata
    public_image_bytes = str([image_reopen.json(), image_history.json()])
    assert "private-image-model" not in public_image_bytes
    assert "private-image-provider" not in public_image_bytes
    assert "private-node" not in public_image_bytes
    assert store.get(image["id"])["metadata"] == private_image_metadata

    assert document_reopen.status_code == 200
    assert document_history.status_code == 200
    assert document_reopen.json()["artifact"]["metadata"] == private_document_metadata
    assert document_history.json()["items"][0]["metadata"] == private_document_metadata


def test_http_route_hides_invalid_ids_and_rejects_corrupt_bytes(monkeypatch, tmp_path):
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path / "http-artifacts"))
    with TestClient(app) as client:
        scope_key = _bootstrap_scope_key(client)
        store = artifact_store.get_artifact_store()
        created = store.put_bytes(
            _PDF_V1,
            artifact_type="document",
            mime_type="application/pdf",
            filename="estimate.pdf",
            metadata={"scope_key": scope_key},
        )
        store._blob_path(created["sha256"]).write_bytes(b"corrupt")
        traversal = client.get("/api/v1/artifacts/not-a-uuid")
        corrupt = client.get(created["url"])

    assert traversal.status_code == 404
    assert traversal.json()["detail"] == "Artifact not found"
    assert corrupt.status_code == 409
    assert corrupt.json()["detail"] == "Artifact integrity check failed"


def test_http_routes_quarantine_unscoped_manifest_without_deleting_bytes(monkeypatch, tmp_path):
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path / "http-artifacts"))
    store = artifact_store.get_artifact_store()
    created = store.put_bytes(
        _PDF_V1,
        artifact_type="document",
        mime_type="application/pdf",
        filename="legacy-unscoped.pdf",
        metadata={"migration_status": "legacy-unscoped"},
    )

    with TestClient(app) as client:
        _bootstrap_scope_key(client)
        content = client.get(created["url"])
        reopen = client.get(created["reopen_url"])
        history = client.get(created["history_url"])

    assert content.status_code == 404
    assert reopen.status_code == 404
    assert history.status_code == 404
    assert store.open(created["id"]).content == _PDF_V1
    assert store.get(created["id"])["metadata"] == {
        "migration_status": "legacy-unscoped"
    }
