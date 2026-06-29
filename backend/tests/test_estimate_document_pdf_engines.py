from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from document_engine import DocumentType, create_business_document, create_document_pack
from estimate_engine import Estimate, EstimateItem, EstimateSection, create_estimate_from_prompt, normalize_estimate_payload, recalculate_estimate
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
    assert estimate.client_name == "Иван"
    assert "кух" in estimate.title.lower()
    assert estimate.totals.grand_total > Decimal("0")
    normalized = normalize_estimate_payload(estimate.model_dump(mode="json"))
    assert normalized.totals.grand_total == estimate.totals.grand_total


def test_prompt_estimate_is_stable_for_same_plastering_scope_in_tatarstan():
    prompt = "100 м2 штукатурки в Татарстане"

    first = create_estimate_from_prompt(prompt, client_name="Иван")
    second = create_estimate_from_prompt(prompt, client_name="Иван")

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.estimate_id == "EST-A1B5B0B498"
    assert first.region == "Республика Татарстан"
    assert first.pricebook_version == "kolibri-ru-2026q2-v1"
    assert first.deterministic is True
    assert first.created_at == "2026-06-29T00:00:00+00:00"
    assert first.updated_at == "2026-06-29T00:00:00+00:00"
    assert first.totals.labor == Decimal("106500.00")
    assert first.totals.materials == Decimal("44000.00")
    assert first.totals.subtotal == Decimal("150500.00")
    assert first.totals.overhead == Decimal("10535.00")
    assert first.totals.tax == Decimal("0.00")
    assert first.totals.grand_total == Decimal("161035.00")
    audit_rows = [entry for entry in first.calculation_audit if entry.get("kind") != "totals"]
    assert [entry["item"] for entry in audit_rows] == [
        "Грунтование стен под штукатурку",
        "Установка штукатурных маяков",
        "Штукатурка стен гипсовой смесью до 20 мм",
        "Финишное выравнивание под шпаклевание",
    ]
    assert all(entry["source"] == "kolibri_pricebook" for entry in audit_rows)
    for entry in audit_rows:
        assert Decimal(entry["line_total"]) == Decimal(entry["labor_total"]) + Decimal(entry["material_total"])

    totals_audit = first.calculation_audit[-1]
    assert totals_audit["input_hash"] == first.input_hash
    assert totals_audit["pricebook_version"] == "kolibri-ru-2026q2-v1"
    assert totals_audit["calculated_at"] == "2026-06-29T00:00:00+00:00"
    assert len(totals_audit["fingerprint"]) == 64

    for section in first.sections:
        for item in section.items:
            assert item.provenance.source == "kolibri_pricebook"
            assert item.provenance.captured_at == "2026-06-29T00:00:00+00:00"


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
