"""Backend E2E contracts for the canonical registry and unified tool router."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import ai_provider, capability_runtime, web_search
from app import tool_router
from app.capability_runtime import capability_by_id, capability_snapshot
from app.main import app


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("KOLIBRI_CAPABILITY_PROBE_FILE", str(tmp_path / "capability-probes.json"))
    monkeypatch.setenv("KOLIBRI_RELEASE_ID", "kolibri-test-release-a")
    monkeypatch.setenv("KOLIBRI_CAPABILITY_PROBE_TTL_SECONDS", "25200")
    monkeypatch.delenv("KOLIBRI_DISABLED_CAPABILITIES", raising=False)


@pytest.fixture
def browser_client():
    with TestClient(app) as client:
        bootstrap = client.post("/api/v1/shell/bootstrap")
        assert bootstrap.status_code == 200
        yield client


def _invoke(client: TestClient, tool: str, arguments: dict):
    return client.post("/api/v1/tools/invoke", json={"tool": tool, "arguments": arguments})


def _estimate() -> dict:
    return {
        "title": "Смета: дом 100 м² — Лениногорск",
        "currency": "RUB",
        "version": 1,
        "region": "Лениногорск, Республика Татарстан",
        "sections": [
            {
                "title": "Подготовительные работы",
                "subtotal": "1000.00",
                "positions": [
                    {
                        "code": "",
                        "name": "Разбивка осей",
                        "unit": "компл.",
                        "quantity": "1",
                        "price": "1000.00",
                        "sum": "1000.00",
                    }
                ],
            }
        ],
        "subtotal": "1000.00",
        "overhead_rate": "0",
        "overhead_amount": "0.00",
        "vat_rate": "0",
        "vat_amount": "0.00",
        "total": "1000.00",
    }


def test_catalog_has_only_canonical_statuses_and_concrete_reasons(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    snapshot = capability_snapshot()

    assert snapshot["schema_version"] == "kolibri.capabilities.v1"
    assert snapshot["capabilities"]
    assert {item["status"] for item in snapshot["capabilities"]} <= {
        "available",
        "degraded",
        "unavailable",
    }
    assert all(item["reason"]["code"] and item["reason"]["message"] for item in snapshot["capabilities"])
    unsupported = {"automation.run"}
    by_id = {item["id"]: item for item in snapshot["capabilities"]}
    assert all(by_id[item]["status"] == "unavailable" for item in unsupported)
    assert all(by_id[item]["invocable"] is False for item in unsupported)


def test_capability_proof_is_release_bound_and_uses_campaign_safe_ttl(
    monkeypatch,
    tmp_path,
):
    probe_path = tmp_path / "capability-probes.json"
    capability_runtime.record_capability_invocation(
        "web.search",
        succeeded=True,
        provider="verified-search",
        evidence_id="artifact:release-a",
    )

    first = capability_by_id("web.search")
    first_probe = capability_runtime.capability_invocation_probe("web.search")
    ledger = json.loads(probe_path.read_text(encoding="utf-8"))

    assert first["status"] == "available"
    assert first_probe.ttl_seconds == 25200
    assert ledger["schema_version"] == "kolibri.capability-probes.v2"
    assert ledger["release_id"] == "kolibri-test-release-a"
    assert ledger["probes"]["web.search"]["release_id"] == "kolibri-test-release-a"

    monkeypatch.setenv("KOLIBRI_RELEASE_ID", "kolibri-test-release-b")
    inherited = capability_by_id("web.search")

    assert inherited["status"] == "degraded"
    assert inherited["invocable"] is False
    assert inherited["reason"]["code"] == "probe_not_run"

    capability_runtime.record_capability_invocation(
        "web.search",
        succeeded=True,
        provider="verified-search",
        evidence_id="artifact:release-b",
    )
    refreshed = capability_by_id("web.search")
    rewritten = json.loads(probe_path.read_text(encoding="utf-8"))

    assert refreshed["status"] == "available"
    assert rewritten["release_id"] == "kolibri-test-release-b"
    assert rewritten["probes"]["web.search"]["evidence_id"] == "artifact:release-b"


def test_default_capability_ledgers_are_isolated_per_release(monkeypatch, tmp_path):
    artifact_root = tmp_path / "shared-artifacts"
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(artifact_root))
    monkeypatch.delenv("KOLIBRI_CAPABILITY_PROBE_FILE", raising=False)

    monkeypatch.setenv("KOLIBRI_RELEASE_ID", "kolibri-release-a")
    capability_runtime.record_capability_invocation(
        "web.search",
        succeeded=True,
        provider="verified-search",
        evidence_id="artifact:release-a",
    )
    path_a = artifact_root / "runtime" / "capability-probes" / "kolibri-release-a.json"

    monkeypatch.setenv("KOLIBRI_RELEASE_ID", "kolibri-release-b")
    capability_runtime.record_capability_invocation(
        "web.search",
        succeeded=True,
        provider="verified-search",
        evidence_id="artifact:release-b",
    )
    path_b = artifact_root / "runtime" / "capability-probes" / "kolibri-release-b.json"

    assert json.loads(path_a.read_text(encoding="utf-8"))["probes"]["web.search"]["evidence_id"] == "artifact:release-a"
    assert json.loads(path_b.read_text(encoding="utf-8"))["probes"]["web.search"]["evidence_id"] == "artifact:release-b"

    monkeypatch.setenv("KOLIBRI_RELEASE_ID", "kolibri-release-a")
    assert capability_runtime.capability_invocation_probe("web.search").evidence_id == "artifact:release-a"
    monkeypatch.setenv("KOLIBRI_RELEASE_ID", "kolibri-release-b")
    assert capability_runtime.capability_invocation_probe("web.search").evidence_id == "artifact:release-b"


def test_in_memory_provider_proof_does_not_transfer_between_releases(monkeypatch):
    provider = {
        "id": "release-bound-provider",
        "model": "test-model",
        "key": "configured",
        "url": "https://provider.invalid/v1/responses",
        "credential_source": "server_env",
        "routable": True,
    }
    ai_provider._record_provider_success(provider)

    assert ai_provider.provider_route_snapshot(provider)["status"] == "live"

    monkeypatch.setenv("KOLIBRI_RELEASE_ID", "kolibri-test-release-b")

    snapshot = ai_provider.provider_route_snapshot(provider)
    assert snapshot["status"] == "unverified"
    assert snapshot["verified_at"] is None


def test_unimplemented_tool_fails_without_chat_fallback(browser_client):
    response = _invoke(
        browser_client,
        "automation.run",
        {"workflow_id": "missing"},
    )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "capability_unavailable"
    assert detail["capability"] == "automation.run"
    assert "artifact" not in response.text.casefold()
    assert "готов" not in response.text.casefold()


def test_web_search_promotes_only_after_verified_http_sources(monkeypatch, browser_client):
    async def real_transport_boundary(query: str, num_results: int = 5):
        assert query == "цены на бетон Татарстан 2026"
        assert num_results == 3
        return [
            {"title": "Официальный источник", "snippet": "Данные", "url": "https://example.test/source"},
            {"title": "Неверная схема", "snippet": "Не источник", "url": "javascript:alert(1)"},
        ]

    monkeypatch.setattr(web_search, "web_search", real_transport_boundary)
    before = capability_by_id("web.search")
    assert before["status"] == "degraded"
    response = _invoke(
        browser_client,
        "web.search",
        {"query": "цены на бетон Татарстан 2026", "limit": 3},
    )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["total"] == 1
    assert result["sources"][0]["url"] == "https://example.test/source"
    assert capability_by_id("web.search")["status"] == "available"


def test_pdf_docx_xlsx_pptx_are_persisted_downloadable_and_reopenable(browser_client):
    cases = [
        (
            "document.pdf",
            {"title": "Проверенный отчёт", "content": "<p>Содержимое</p>"},
            "application/pdf",
            b"%PDF-",
        ),
        (
            "document.docx",
            {"title": "Проверенный документ", "content": "<p>Содержимое</p>"},
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            b"PK\x03\x04",
        ),
        (
            "document.xlsx",
            {"estimate": _estimate()},
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            b"PK\x03\x04",
        ),
        (
            "document.pptx",
            {
                "title": "Проверенная презентация",
                "slides": [
                    {"title": "Итоги", "bullets": ["Первый пункт", "Второй пункт"]},
                    {"title": "План", "content": "Следующий шаг"},
                ],
            },
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            b"PK\x03\x04",
        ),
    ]

    for tool, arguments, mime_type, magic in cases:
        created = _invoke(browser_client, tool, arguments)
        assert created.status_code == 200, created.text
        artifact = created.json()["result"]
        content = browser_client.get(artifact["download_url"])
        reopened = browser_client.get(artifact["reopen_url"])
        history = browser_client.get(artifact["history_url"])

        assert content.status_code == 200
        assert content.headers["content-type"] == mime_type
        assert content.content.startswith(magic)
        assert hashlib.sha256(content.content).hexdigest() == artifact["sha256"]
        assert artifact["size_bytes"] == len(content.content)
        assert reopened.status_code == 200
        assert reopened.json()["integrity"]["digest"] == artifact["sha256"]
        assert history.status_code == 200
        assert history.json()["items"][0]["sha256"] == artifact["sha256"]
        assert capability_by_id(tool)["status"] == "available"

    docx = _invoke(
        browser_client,
        "document.docx",
        {"title": "ZIP validation", "content": "<p>text</p>"},
    ).json()["result"]
    with zipfile.ZipFile(io.BytesIO(browser_client.get(docx["url"]).content)) as archive:
        assert "word/document.xml" in archive.namelist()

    pptx = _invoke(
        browser_client,
        "document.pptx",
        {
            "title": "ZIP validation",
            "slides": [{"title": "Slide", "content": "text"}],
        },
    ).json()["result"]
    with zipfile.ZipFile(io.BytesIO(browser_client.get(pptx["url"]).content)) as archive:
        assert archive.testzip() is None
        assert "ppt/presentation.xml" in archive.namelist()
        assert "ppt/slides/slide1.xml" in archive.namelist()
        assert "ppt/slides/_rels/slide1.xml.rels" in archive.namelist()


def test_tool_artifact_bytes_reopen_and_history_are_session_scoped(browser_client):
    created = _invoke(
        browser_client,
        "document.pdf",
        {"title": "Приватный отчёт", "content": "Только текущий проект"},
    )
    assert created.status_code == 200, created.text
    artifact = created.json()["result"]

    with TestClient(app) as other_client:
        assert other_client.post("/api/v1/shell/bootstrap").status_code == 200
        content = other_client.get(artifact["url"])
        reopen = other_client.get(artifact["reopen_url"])
        history = other_client.get(artifact["history_url"])

    assert content.status_code == 404
    assert reopen.status_code == 404
    assert history.status_code == 404


def test_invalid_client_payload_does_not_erase_last_successful_capability_proof(
    browser_client,
):
    created = _invoke(
        browser_client,
        "document.pptx",
        {
            "title": "Рабочая презентация",
            "slides": [{"title": "Итог", "content": "Проверено"}],
        },
    )
    assert created.status_code == 200, created.text
    assert capability_by_id("document.pptx")["status"] == "available"

    invalid = _invoke(
        browser_client,
        "document.pptx",
        {"title": "Некорректная презентация", "slides": []},
    )

    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "pptx_source_invalid"
    assert capability_by_id("document.pptx")["status"] == "available"


def test_pdf_text_layer_is_analyzed_and_scanned_pdf_is_explicit(monkeypatch, browser_client):
    created = _invoke(
        browser_client,
        "document.pdf",
        {"title": "Searchable", "content": "<p>Kolibri searchable PDF evidence</p>"},
    )
    assert created.status_code == 200, created.text
    pdf_bytes = browser_client.get(created.json()["result"]["download_url"]).content
    uploaded = browser_client.post(
        "/api/v1/files",
        files={"file": ("searchable.pdf", pdf_bytes, "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    analyzed = browser_client.post(
        f"/api/v1/files/{uploaded.json()['artifact']['id']}/analyze"
    )
    assert analyzed.status_code == 201, analyzed.text
    assert "Kolibri searchable PDF evidence" in analyzed.json()["analysis"]["text"]

    from reportlab.pdfgen.canvas import Canvas

    blank_buffer = io.BytesIO()
    canvas = Canvas(blank_buffer)
    canvas.showPage()
    canvas.save()
    blank = browser_client.post(
        "/api/v1/files",
        files={"file": ("scan.pdf", blank_buffer.getvalue(), "application/pdf")},
    )
    scanned = browser_client.post(
        f"/api/v1/files/{blank.json()['artifact']['id']}/analyze"
    )
    assert scanned.status_code == 422
    assert scanned.json()["detail"] == {
        "code": "pdf_scanned_or_no_text",
        "mime_type": "application/pdf",
        "ocr_supported": False,
    }

    monkeypatch.setattr(tool_router.shutil, "which", lambda _binary: None)
    unavailable = browser_client.post(
        f"/api/v1/files/{uploaded.json()['artifact']['id']}/analyze"
    )
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"]["code"] == "pdf_text_extractor_unavailable"
    assert unavailable.json()["detail"]["retryable"] is True


def test_file_upload_analyze_and_search_are_scope_backed(browser_client):
    uploaded = browser_client.post(
        "/api/v1/files",
        files={"file": ("requirements.txt", "Rust Axum и PostgreSQL\n", "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    source = uploaded.json()["artifact"]
    assert source["mime_type"] == "text/plain"
    assert len(source["metadata"]["scope_key"]) == 64
    assert "anon:" not in json.dumps(source["metadata"])

    analyzed = browser_client.post(f"/api/v1/files/{source['id']}/analyze")
    assert analyzed.status_code == 201, analyzed.text
    assert "PostgreSQL" in analyzed.json()["analysis"]["text"]
    analysis_artifact = analyzed.json()["artifact"]
    analysis_bytes = browser_client.get(analysis_artifact["url"]).content
    assert json.loads(analysis_bytes)["source_sha256"] == source["sha256"]

    found = browser_client.get("/api/v1/files/search", params={"q": "postgresql"})
    assert found.status_code == 200, found.text
    assert found.json()["total"] >= 1
    assert any(item["artifact"]["id"] == source["id"] for item in found.json()["items"])
    assert capability_by_id("file.upload")["status"] == "available"
    assert capability_by_id("file.analyze")["status"] == "available"
    assert capability_by_id("file.search")["status"] == "available"


def test_generated_docx_is_analyzable_but_zip_bomb_is_rejected_before_parser(
    browser_client,
):
    generated = _invoke(
        browser_client,
        "document.docx",
        {"title": "Безопасный DOCX", "content": "<p>Проверяемый текст документа</p>"},
    )
    assert generated.status_code == 200, generated.text
    safe_bytes = browser_client.get(generated.json()["result"]["download_url"]).content
    uploaded = browser_client.post(
        "/api/v1/files",
        files={
            "file": (
                "safe.docx",
                safe_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    analyzed = browser_client.post(
        f"/api/v1/files/{uploaded.json()['artifact']['id']}/analyze"
    )
    assert analyzed.status_code == 201, analyzed.text
    assert "Проверяемый текст документа" in analyzed.json()["analysis"]["text"]

    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'/>",
        )
        archive.writestr(
            "word/document.xml",
            b"A" * (tool_router._MAX_ARCHIVE_ENTRY_BYTES + 1),
        )
    bomb_upload = browser_client.post(
        "/api/v1/files",
        files={
            "file": (
                "bomb.docx",
                bomb.getvalue(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert bomb_upload.status_code == 201, bomb_upload.text
    rejected = browser_client.post(
        f"/api/v1/files/{bomb_upload.json()['artifact']['id']}/analyze"
    )

    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "file_archive_safety_limit_exceeded"


@pytest.mark.parametrize(
    ("mime_type", "required_part"),
    [
        (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "word/document.xml",
        ),
        (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xl/workbook.xml",
        ),
    ],
)
def test_docx_and_xlsx_extreme_compression_is_rejected_by_preflight(
    mime_type,
    required_part,
):
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'/>",
        )
        archive.writestr(required_part, b"A" * (2 * 1024 * 1024))

    with zipfile.ZipFile(io.BytesIO(bomb.getvalue())) as archive:
        compressed = sum(entry.compress_size for entry in archive.infolist())
        uncompressed = sum(entry.file_size for entry in archive.infolist())
    assert uncompressed > compressed * tool_router._MAX_ARCHIVE_COMPRESSION_RATIO

    with pytest.raises(
        tool_router.ArtifactValidationError,
        match="file_archive_safety_limit_exceeded",
    ):
        tool_router._validate_ooxml_archive(bomb.getvalue(), mime_type)


def test_ooxml_entry_count_limit_is_checked_without_extracting_members(monkeypatch):
    monkeypatch.setattr(tool_router, "_MAX_ARCHIVE_ENTRIES", 2)
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/worksheets/sheet1.xml", "<worksheet/>")

    with pytest.raises(
        tool_router.ArtifactValidationError,
        match="file_archive_safety_limit_exceeded",
    ):
        tool_router._validate_ooxml_archive(
            archive_bytes.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


def test_self_description_is_derived_from_registry(monkeypatch, browser_client):
    unavailable = ai_provider._capability_self_description()
    assert "Сейчас недоступно" in unavailable["content"]
    not_yet_live = {
        item["id"]
        for group in ("degraded", "unavailable")
        for item in unavailable["capabilities"][group]
    }
    assert "site.create" in not_yet_live

    created = _invoke(
        browser_client,
        "document.pdf",
        {"title": "Capability proof", "content": "<p>proof</p>"},
    )
    assert created.status_code == 200
    available = ai_provider._capability_self_description()
    assert "PDF" in available["content"]
    assert "document.pdf" in {
        item["id"] for item in available["capabilities"]["available"]
    }


def test_file_analysis_rejects_unsupported_format_without_success_claim(browser_client):
    uploaded = browser_client.post(
        "/api/v1/files",
        files={"file": ("binary.bin", b"\x00\x01\x02", "application/octet-stream")},
    )
    assert uploaded.status_code == 201
    artifact_id = uploaded.json()["artifact"]["id"]

    response = browser_client.post(f"/api/v1/files/{artifact_id}/analyze")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "file_format_not_analyzable"
    capability = capability_by_id("file.analyze")
    assert capability["status"] == "degraded"
    assert capability["invocable"] is False
    assert capability["reason"]["code"] == "probe_not_run"


@pytest.mark.parametrize(
    ("path", "capability"),
    [
        ("/api/v1/integrations/connect", "integration.connect"),
        ("/api/v1/automations/run", "automation.run"),
    ],
)
def test_integration_and_automation_are_owner_gated_without_fake_success(
    monkeypatch,
    browser_client,
    path,
    capability,
):
    owner_token = "runtime-owner-token"
    monkeypatch.setenv(
        "KOLIBRI_OWNER_API_ADMIN_TOKEN_SHA256",
        hashlib.sha256(owner_token.encode()).hexdigest(),
    )
    denied = browser_client.post(path, json={})
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "owner_authentication_required"

    gated = browser_client.post(
        path,
        headers={"X-Kolibri-Owner-Token": owner_token},
        json={},
    )
    assert gated.status_code == 503
    assert gated.json()["detail"]["capability"] == capability
    assert gated.json()["detail"]["code"] == "capability_unavailable"
