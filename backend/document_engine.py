from __future__ import annotations

import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from estimate_engine import Estimate, recalculate_estimate, utc_now


class DocumentType(str, Enum):
    commercial_offer = "commercial_offer"
    contract = "contract"
    completion_act = "completion_act"
    invoice = "invoice"


DOCUMENT_TYPE_LABELS = {
    DocumentType.commercial_offer: "Коммерческое предложение",
    DocumentType.contract: "Договор подряда",
    DocumentType.completion_act: "Акт выполненных работ",
    DocumentType.invoice: "Счёт на оплату",
}


class BusinessDocument(BaseModel):
    document_id: str = Field(default_factory=lambda: f"DOC-{uuid.uuid4().hex[:10].upper()}")
    document_type: DocumentType
    title: str
    client_name: str
    contractor_name: str = "Колибри"
    estimate_id: str
    currency: str = "RUB"
    total: str
    body_sections: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)


def create_business_document(estimate: Estimate, document_type: DocumentType | str = DocumentType.commercial_offer, *, contractor_name: str = "Колибри") -> BusinessDocument:
    if isinstance(document_type, str):
        document_type = DocumentType(document_type)
    estimate = recalculate_estimate(estimate)
    label = DOCUMENT_TYPE_LABELS[document_type]
    sections = [
        {"title": "Предмет", "text": f"{contractor_name} подготовил документ по смете {estimate.estimate_id}: {estimate.title}."},
        {"title": "Стоимость", "text": f"Итоговая стоимость работ и материалов: {estimate.totals.grand_total} {estimate.currency}."},
        {"title": "Аудит расчёта", "text": "Расчёт выполнен детерминированным калькулятором Колибри и может быть воспроизведён по строкам сметы."},
    ]
    return BusinessDocument(document_type=document_type, title=f"{label}: {estimate.title}", client_name=estimate.client_name, contractor_name=contractor_name, estimate_id=estimate.estimate_id, currency=estimate.currency, total=str(estimate.totals.grand_total), body_sections=sections)


def create_document_pack(estimate: Estimate, *, contractor_name: str = "Колибри") -> list[BusinessDocument]:
    return [create_business_document(estimate, doc_type, contractor_name=contractor_name) for doc_type in (DocumentType.commercial_offer, DocumentType.contract, DocumentType.completion_act, DocumentType.invoice)]
