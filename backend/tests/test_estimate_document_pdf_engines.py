from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from document_engine import DocumentType, create_business_document, create_document_pack
from estimate_engine import (
    Estimate,
    EstimateItem,
    EstimateSection,
    create_estimate_from_prompt,
    estimate_canonical_hash,
    estimate_canonical_json,
    normalize_estimate_payload,
    recalculate_estimate,
)
from main import app
from pdf_engine import generate_business_document_pdf, generate_estimate_pdf


def test_estimate_recalculation_is_deterministic_and_audited():
    estimate = Estimate(
        title="Смета на тестовый ремонт",
        client_name="Владелец",
        sections=[EstimateSection(title="Работы", items=[EstimateItem(name="Штукатурка стен", unit="м2", quantity=Decimal("10"), labor_unit_price=Decimal("500"), material_unit_price=Decimal("120")), EstimateItem(name="Покраска", unit="м2", quantity=Decimal("10"), labor_unit_price=Decimal("300"), material_unit_price=Decimal("80"))])],
        overhead_rate=Decimal("10"),
        tax_rate=Decimal("0"),
    )
    calculated = recalculate_estimate(estimate)
    assert calculated.totals.labor == Decimal("8000.00")
    assert calculated.totals.materials == Decimal("2000.00")
    assert calculated.totals.overhead == Decimal("1000.00")
    assert calculated.totals.grand_total == Decimal("11000.00")
    assert calculated.calculation_audit[-1]["kind"] == "totals"
    assert len(calculated.calculation_audit[-1]["fingerprint"]) == 64


def test_prompt_estimate_and_payload_normalization():
    estimate = create_estimate_from_prompt("Нужна смета на ремонт кухни 12 м2", client_name="Иван")
    repeated = create_estimate_from_prompt("Нужна смета на ремонт кухни 12 м2", client_name="Иван")
    assert estimate.client_name == "Иван"
    assert "кух" in estimate.title.lower()
    assert estimate.totals.grand_total > Decimal("0")
    assert estimate.estimate_id == repeated.estimate_id
    assert estimate_canonical_hash(estimate) == estimate_canonical_hash(repeated)
    normalized = normalize_estimate_payload(estimate.model_dump(mode="json"))
    assert normalized.totals.grand_total == estimate.totals.grand_total
    assert estimate_canonical_hash(normalized) == estimate_canonical_hash(estimate)
    assert "captured_at" not in estimate_canonical_json(estimate)


def test_business_document_pack_has_required_documents():
    estimate = create_estimate_from_prompt("Ремонт квартиры 20 м2")
    document = create_business_document(estimate, DocumentType.commercial_offer, contractor_name="Колибри")
    pack = create_document_pack(estimate)
    assert document.client_name == estimate.client_name
    assert document.total == str(estimate.totals.grand_total)
    assert {item.document_type for item in pack} == {DocumentType.commercial_offer, DocumentType.contract, DocumentType.completion_act, DocumentType.invoice}


def test_pdf_generation_supports_cyrillic_documents(tmp_path: Path):
    estimate = create_estimate_from_prompt("Смета на санузел 8 м2", client_name="Тестовый клиент")
    estimate_path = generate_estimate_pdf(estimate, tmp_path / "smeta.pdf")
    document = create_business_document(estimate, DocumentType.contract)
    document_path = generate_business_document_pdf(document, tmp_path / "contract.pdf")
    for path in (estimate_path, document_path):
        data = path.read_bytes()
        assert data.startswith(b"%PDF")
        assert len(data) > 1500


def test_estimate_api_generate_edit_and_conflict_contract():
    client = TestClient(app)
    contract = client.get("/api/estimates/contract")
    assert contract.status_code == 200
    assert contract.json()["claim_constraints"]["not_a_price_accuracy_warranty"] is True

    generated = client.post(
        "/api/estimates/generate",
        json={"prompt": "Нужна смета на ремонт кухни 12 м2", "client_name": "Иван"},
    )
    assert generated.status_code == 200
    generated_body = generated.json()
    assert generated_body["canonical_hash"].startswith("sha256:")
    assert generated_body["canonical_json"].startswith("{")

    edited = client.post(
        "/api/estimates/edit",
        json={
            "estimate": generated_body["estimate"],
            "expected_canonical_hash": generated_body["canonical_hash"],
            "edits": {"overhead_rate": "12.00"},
        },
    )
    assert edited.status_code == 200
    edited_body = edited.json()
    assert edited_body["previous_canonical_hash"] == generated_body["canonical_hash"]
    assert edited_body["canonical_hash"] != generated_body["canonical_hash"]
    assert edited_body["edit_applied"] is True

    conflict = client.post(
        "/api/estimates/edit",
        json={
            "estimate": generated_body["estimate"],
            "expected_canonical_hash": "sha256:deadbeef",
            "edits": {"overhead_rate": "15.00"},
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["error"] == "canonical_hash_conflict"


def test_estimate_api_rejects_unsupported_98_percent_claim():
    client = TestClient(app)
    response = client.post(
        "/api/estimates/generate",
        json={
            "prompt": "Смета на ремонт квартиры 20 м2",
            "claim": {"percent": "98.50", "basis": "manual"},
        },
    )
    assert response.status_code == 422
