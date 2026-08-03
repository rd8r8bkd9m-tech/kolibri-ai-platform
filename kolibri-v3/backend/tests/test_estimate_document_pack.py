from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from pypdf import PdfReader
from fastapi.testclient import TestClient

from app.config import Settings
from app.estimate_document_pack import (
    DocumentPackError,
    build_estimate_document_snapshot,
    money_words,
)
from app.main import create_app
from app.product_widgets import materialize_generated_estimate_widget

from test_estimate_artifact import ORIGIN, _proposal, _seed_project


def _ready_fixture(tmp_path: Path):
    database_path = tmp_path / "estimate-pack.db"
    settings = Settings.for_testing(database_url=database_path)
    client = TestClient(create_app(settings))
    client.__enter__()
    registered = client.post(
        "/v1/auth/register",
        headers=ORIGIN,
        json={
            "email": "document-pack@example.com",
            "name": "Document Pack",
            "password": "correct-horse-battery-staple",
        },
    )
    assert registered.status_code == 201
    user = registered.json()["user"]
    accepted = _seed_project(
        database_path,
        tenant_id=user["tenantId"],
        user_id=user["id"],
    )
    materialize_generated_estimate_widget(
        settings,
        accepted,
        proposal=_proposal(),
        provider_profile="document-pack-test",
    )
    return client, settings, database_path, accepted, user


def test_money_words_has_russian_boundary_forms() -> None:
    assert money_words("0.00") == "Ноль рублей 00 копеек."
    assert money_words("1.01") == "Один рубль 01 копейка."
    assert money_words("2.02") == "Два рубля 02 копейки."
    assert money_words("5.05") == "Пять рублей 05 копеек."
    assert money_words("11.11") == "Одиннадцать рублей 11 копеек."
    assert money_words("1001.00") == "Одна тысяча один рубль 00 копеек."


def test_document_pack_api_persists_real_artifacts_and_replays(tmp_path: Path) -> None:
    client, _settings, _database_path, accepted, _user = _ready_fixture(tmp_path)
    try:
        csrf = str(client.cookies.get("kolibri_v3_csrf"))
        headers = {
            **ORIGIN,
            "X-CSRF-Token": csrf,
            "Idempotency-Key": "document-pack-api-test-0001",
        }
        response = client.post(
            f"/v1/projects/{accepted.project_id}/estimate/document-pack",
            headers=headers,
            json={
                "estimateVersion": 1,
                "requestedKinds": ["pack"],
                "mode": "preliminary",
            },
        )
        assert response.status_code == 201
        issue = response.json()
        assert issue["rendererVersion"] == "official_ru_v1"
        assert issue["status"] == "preliminary"
        assert issue["preview"]["total"] == "15000.00"
        assert issue["preview"]["totalLines"] == 1
        assert issue["preview"]["truncated"] is False
        assert {item["kind"] for item in issue["files"]} == {"pdf", "xlsx", "docx", "zip"}

        replay = client.post(
            f"/v1/projects/{accepted.project_id}/estimate/document-pack",
            headers=headers,
            json={
                "estimateVersion": 1,
                "requestedKinds": ["pack"],
                "mode": "preliminary",
            },
        )
        assert replay.status_code == 201
        assert replay.json()["issueId"] == issue["issueId"]
        assert replay.json()["sourceHash"] == issue["sourceHash"]

        pdf_file = next(item for item in issue["files"] if item["kind"] == "pdf")
        pdf_response = client.get(
            f"/v1/projects/{accepted.project_id}/estimate/document-pack/"
            f"{issue['issueId']}/artifacts/{pdf_file['artifactId']}"
        )
        assert pdf_response.status_code == 200
        assert pdf_response.content.startswith(b"%PDF-")
        assert pdf_response.headers["x-kolibri-content-sha256"] == pdf_file["artifactHash"]

        reader = PdfReader(io.BytesIO(pdf_response.content))
        assert reader.pages
        assert float(reader.pages[0].mediabox.width) < float(reader.pages[0].mediabox.height)
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
        assert "PRELIMINARY" in extracted
        assert "Условия и границы расчёта" in extracted
        forbidden_term = "доп" + "ущ"
        assert forbidden_term not in extracted.casefold()
        assert "/JavaScript" not in str(reader.trailer)

        zip_file = next(item for item in issue["files"] if item["kind"] == "zip")
        zip_response = client.get(
            f"/v1/projects/{accepted.project_id}/estimate/document-pack/"
            f"{issue['issueId']}/artifacts/{zip_file['artifactId']}"
        )
        with zipfile.ZipFile(io.BytesIO(zip_response.content)) as bundle:
            names = set(bundle.namelist())
            assert "manifest.json" in names
            assert any(name.endswith(".pdf") for name in names)
            assert any(name.endswith(".xlsx") for name in names)
            assert any(name.endswith(".docx") for name in names)
            manifest = json.loads(bundle.read("manifest.json"))
            assert manifest["rendererVersion"] == "official_ru_v1"
            assert manifest["sourceHash"] == issue["sourceHash"]
            assert all(item["artifactHash"].startswith("sha256:") for item in manifest["files"])

        legacy = client.get(
            f"/v1/projects/{accepted.project_id}/estimate/export/pdf?version=1&kind=pack"
        )
        assert legacy.status_code == 200
        assert legacy.content == pdf_response.content
    finally:
        client.close()


def test_issue_mode_blocks_preliminary_prices_and_invoice_requires_requisites(tmp_path: Path) -> None:
    client, _settings, _database_path, accepted, _user = _ready_fixture(tmp_path)
    try:
        csrf = str(client.cookies.get("kolibri_v3_csrf"))
        base_headers = {**ORIGIN, "X-CSRF-Token": csrf}
        blocked = client.post(
            f"/v1/projects/{accepted.project_id}/estimate/document-pack",
            headers={**base_headers, "Idempotency-Key": "document-pack-issue-test-0001"},
            json={"estimateVersion": 1, "requestedKinds": ["pack"], "mode": "issue"},
        )
        assert blocked.status_code == 422
        assert blocked.json()["code"] == "stale_prices_block_ready"

        client.put(
            f"/v1/projects/{accepted.project_id}/parties/client",
            headers=base_headers,
            json={
                "displayName": "ООО Заказчик",
                "entityType": "organization",
                "taxId": "7707083893",
                "registrationCode": "770701001",
            },
        )
        client.put(
            f"/v1/projects/{accepted.project_id}/parties/contractor",
            headers=base_headers,
            json={
                "displayName": "ООО Исполнитель",
                "entityType": "organization",
                "taxId": "5001007322",
                "registrationCode": "500101001",
            },
        )
        missing = client.post(
            f"/v1/projects/{accepted.project_id}/estimate/document-pack",
            headers={**base_headers, "Idempotency-Key": "document-pack-invoice-test-0001"},
            json={"estimateVersion": 1, "requestedKinds": ["invoice"], "mode": "preliminary"},
        )
        assert missing.status_code == 422
        assert missing.json()["code"] == "invoice_required_fields"
        assert "БИК" in missing.json()["requiredFields"]

        requisites = {
            "bankName": "АО Банк QA",
            "bankIdentificationCode": "044525225",
            "settlementAccount": "40702810900000000001",
            "correspondentAccount": "30101810400000000225",
            "legalAddress": "Москва, ул. Тестовая, д. 1",
            "basis": "Устав",
        }
        for role, legal_name, tax_id, registration_code in (
            ("client", "ООО Заказчик", "7707083893", "770701001"),
            ("contractor", "ООО Исполнитель", "5001007322", "500101001"),
        ):
            saved = client.post(
                f"/v1/projects/{accepted.project_id}/parties/{role}/requisites",
                headers=base_headers,
                json={
                    **requisites,
                    "legalName": legal_name,
                    "taxId": tax_id,
                    "registrationCode": registration_code,
                },
            )
            assert saved.status_code == 200
        issued = client.post(
            f"/v1/projects/{accepted.project_id}/estimate/document-pack",
            headers={**base_headers, "Idempotency-Key": "document-pack-invoice-test-0002"},
            json={"estimateVersion": 1, "requestedKinds": ["invoice"], "mode": "preliminary"},
        )
        assert issued.status_code == 201
        invoice_file = next(item for item in issued.json()["files"] if item["kind"] == "pdf")
        invoice_pdf = client.get(
            f"/v1/projects/{accepted.project_id}/estimate/document-pack/"
            f"{issued.json()['issueId']}/artifacts/{invoice_file['artifactId']}"
        )
        assert invoice_pdf.status_code == 200
        invoice_reader = PdfReader(io.BytesIO(invoice_pdf.content))
        assert len(invoice_reader.pages) == 1
        assert float(invoice_reader.pages[0].mediabox.width) < float(invoice_reader.pages[0].mediabox.height)
        invoice_text = invoice_reader.pages[0].extract_text() or ""
        assert "БИК" in invoice_text
        assert ("доп" + "ущ") not in invoice_text.casefold()
    finally:
        client.close()


def test_snapshot_is_deterministic_and_scoped(tmp_path: Path) -> None:
    client, settings, database_path, accepted, user = _ready_fixture(tmp_path)
    try:
        import sqlite3

        database = sqlite3.connect(database_path)
        database.row_factory = sqlite3.Row
        try:
            slot = database.execute(
                "SELECT id, version FROM document_slots WHERE tenant_id = ? AND project_id = ?",
                (user["tenantId"], accepted.project_id),
            ).fetchone()
            first = build_estimate_document_snapshot(
                database,
                tenant_id=user["tenantId"],
                project_id=accepted.project_id,
                document_id=str(slot["id"]),
                estimate_version=int(slot["version"]),
                document_number="КП-2026-000099",
                mode="preliminary",
                now="2026-08-02T00:00:00+00:00",
            )
            second = build_estimate_document_snapshot(
                database,
                tenant_id=user["tenantId"],
                project_id=accepted.project_id,
                document_id=str(slot["id"]),
                estimate_version=int(slot["version"]),
                document_number="КП-2026-000099",
                mode="preliminary",
                now="2026-08-02T00:00:00+00:00",
            )
            assert first == second
            assert first["sourceHash"].startswith("sha256:")
            assert len(first["lines"]) == 1
        finally:
            database.close()

        other = client.post(
            "/v1/auth/register",
            headers=ORIGIN,
            json={
                "email": "document-pack-other@example.com",
                "name": "Other",
                "password": "correct-horse-battery-staple",
            },
        )
        assert other.status_code == 201
        response = client.get(f"/v1/projects/{accepted.project_id}/estimate/document-pack")
        assert response.status_code in {403, 404}
    finally:
        client.close()


def test_snapshot_rejects_negative_money() -> None:
    try:
        money_words("-1.00")
    except DocumentPackError as exc:
        assert exc.code == "document_money_invalid"
    else:
        raise AssertionError("negative money must be rejected")
