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


def test_business_document_pack_has_required_documents():
    estimate = create_estimate_from_prompt("Ремонт квартиры 20 м2")
    document = create_business_document(estimate, DocumentType.commercial_offer, contractor_name="Колибри")
    pack = create_document_pack(estimate)
    assert document.client_name == estimate.client_name
    assert document.total == str(estimate.totals.grand_total)
    assert {item.document_type for item in pack} == {DocumentType.commercial_offer, DocumentType.contract, DocumentType.completion_act, DocumentType.invoice}


def test_contract_is_a_standalone_legal_structure_with_estimate_as_attachment():
    estimate = create_estimate_from_prompt("Строительство дома 100 м2", client_name="Иванов И.И.")
    document = create_business_document(estimate, DocumentType.contract, contractor_name="ООО Подрядчик")
    headings = [section["title"] for section in document.body_sections]
    body = " ".join(section["text"] for section in document.body_sections)
    assert len(document.body_sections) >= 14
    assert any("Предмет" in heading for heading in headings)
    assert any("Сдача и приёмка" in heading for heading in headings)
    assert any("Реквизиты и подписи" in heading for heading in headings)
    assert estimate.estimate_id in body
    assert document.attachments[0].endswith(estimate.estimate_id)
    assert document.document_standard == "ГОСТ Р 7.0.97-2025"
    assert document.legal_review_required is True


def test_commercial_offer_has_business_document_sections():
    estimate = create_estimate_from_prompt("Ремонт офиса 50 м2", client_name="Заказчик")
    document = create_business_document(estimate, DocumentType.commercial_offer, contractor_name="ООО Подрядчик")
    headings = {section["title"] for section in document.body_sections}
    assert {"О предложении", "Состав предложения", "Основные позиции", "Стоимость", "Допущения и исключения", "Реквизиты и подпись"} <= headings
    assert next(section for section in document.body_sections if section["title"] == "Основные позиции")["rows"]
    assert document.attachments == [f"Приложение № 1 — Смета № {estimate.estimate_id}"]


def test_pdf_generation_supports_cyrillic_documents(tmp_path: Path):
    estimate = create_estimate_from_prompt("Смета на санузел 8 м2", client_name="Тестовый клиент")
    estimate_path = generate_estimate_pdf(estimate, tmp_path / "smeta.pdf")
    document = create_business_document(estimate, DocumentType.contract)
    document_path = generate_business_document_pdf(document, tmp_path / "contract.pdf")
    for path in (estimate_path, document_path):
        data = path.read_bytes()
        assert data.startswith(b"%PDF")
        assert len(data) > 1500
