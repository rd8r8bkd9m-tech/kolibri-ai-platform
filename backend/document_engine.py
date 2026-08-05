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
    attachments: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    legal_review_required: bool = True
    document_standard: str = "ГОСТ Р 7.0.97-2025"
    created_at: str = Field(default_factory=utc_now)


def _contract_sections(estimate: Estimate, contractor_name: str) -> list[dict[str, str]]:
    total = f"{estimate.totals.grand_total} {estimate.currency}"
    return [
        {"title": "1. Предмет договора", "text": (
            f"Подрядчик ({contractor_name}) обязуется выполнить строительные работы на объекте «{estimate.object_address}» "
            f"в составе, объёме и с требованиями, установленными настоящим договором, технической документацией и "
            f"Сметой № {estimate.estimate_id} (Приложение № 1), а Заказчик обязуется создать необходимые условия, "
            "принять результат и оплатить его. Статус сторон и полномочия подписантов: Требуется заполнить."
        )},
        {"title": "2. Документы и приложения", "text": (
            "Неотъемлемые части договора: Смета; техническое задание или ведомость работ; календарный план; форма акта. "
            "Сторона, предоставляющая техническую документацию, её состав и срок передачи: Требуется заполнить."
        )},
        {"title": "3. Сроки и этапы", "text": (
            "Дата начала, дата окончания, этапы и последствия задержки исходных данных или доступа на объект: Требуется заполнить."
        )},
        {"title": "4. Цена договора и расчёты", "text": (
            f"Цена по Смете № {estimate.estimate_id} составляет {total}. Вид цены (твёрдая/приблизительная), режим НДС, "
            "аванс, поэтапные платежи, удержания и срок окончательного расчёта: Требуется заполнить."
        )},
        {"title": "5. Права и обязанности сторон", "text": (
            "Заказчик обеспечивает доступ и передаёт согласованные исходные данные. Подрядчик выполняет согласованный объём, "
            "соблюдает требования безопасности и своевременно уведомляет о препятствиях. Конкретные обязанности: Требуется проверить."
        )},
        {"title": "6. Материалы и оборудование", "text": (
            "Кто закупает, принимает, хранит и несёт риск по материалам; требования к подтверждающим документам и аналогам: Требуется заполнить."
        )},
        {"title": "7. Изменения и дополнительные работы", "text": (
            "Дополнительные работы и увеличение цены выполняются после письменного согласования состава, стоимости и влияния на сроки. "
            "Порядок и срок ответа Заказчика на уведомление Подрядчика: Требуется заполнить."
        )},
        {"title": "8. Сдача и приёмка", "text": (
            "Готовность этапа подтверждается уведомлением Подрядчика. Результат оформляется двусторонним актом; срок осмотра, "
            "мотивированного отказа и устранения замечаний: Требуется заполнить."
        )},
        {"title": "9. Качество и гарантия", "text": (
            "Требования к качеству, применимые технические документы, гарантийный срок, исключения и порядок предъявления требований: Требуется заполнить."
        )},
        {"title": "10. Ответственность сторон", "text": (
            "Основания и пределы ответственности, неустойка, возмещение убытков и ответственность за сохранность объекта: Требуется согласовать."
        )},
        {"title": "11. Непреодолимая сила", "text": (
            "Срок уведомления, подтверждение обстоятельств и последствия их продолжительности: Требуется заполнить."
        )},
        {"title": "12. Изменение, расторжение и споры", "text": (
            "Основания одностороннего отказа, порядок расчётов при прекращении, претензионный порядок и подсудность: Требуется согласовать."
        )},
        {"title": "13. Юридически значимые сообщения", "text": (
            "Допустимые адреса, электронные каналы, момент доставки и обязанность сообщать об изменении реквизитов: Требуется заполнить."
        )},
        {"title": "14. Реквизиты и подписи сторон", "text": (
            f"Заказчик: {estimate.client_name}; реквизиты и подпись: Требуется заполнить. Подрядчик: {contractor_name}; "
            "реквизиты и подпись: Требуется заполнить."
        )},
    ]


def _commercial_offer_sections(estimate: Estimate, contractor_name: str) -> list[dict[str, Any]]:
    estimate_rows = []
    for section in estimate.sections:
        for item in section.items:
            estimate_rows.append({
                "section": section.title,
                "item": item.name,
                "unit": item.unit,
                "quantity": str(item.quantity),
                "total": str(item.line_total()),
            })
    return [
        {"title": "О предложении", "text": (
            f"{contractor_name} предлагает выполнить работы по объекту «{estimate.object_address}» для {estimate.client_name}. "
            "Номер, дата, адресат и контактное лицо: Требуется заполнить."
        )},
        {"title": "Состав предложения", "text": (
            f"Состав, единицы, объёмы и цены приведены в Смете № {estimate.estimate_id}, являющейся приложением к предложению."
        )},
        {"title": "Основные позиции", "text": "Стоимость по позициям исходной сметы.", "rows": estimate_rows},
        {"title": "Стоимость", "text": (
            f"Общая стоимость: {estimate.totals.grand_total} {estimate.currency}. Режим НДС, включённые расходы и порядок оплаты: Требуется заполнить."
        )},
        {"title": "Сроки и организация работ", "text": (
            "Срок начала, продолжительность, этапность, требования к доступу и исходным данным: Требуется заполнить."
        )},
        {"title": "Допущения и исключения", "text": (
            "Границы работ, материалы Заказчика, доставка, вывоз, скрытые работы и основания пересмотра цены: Требуется проверить."
        )},
        {"title": "Гарантия и следующий шаг", "text": (
            "Гарантийные условия, срок действия предложения и порядок перехода к договору: Требуется заполнить."
        )},
        {"title": "Реквизиты и подпись", "text": (
            f"Отправитель: {contractor_name}. Реквизиты, должность, ФИО и подпись уполномоченного лица: Требуется заполнить."
        )},
    ]


def create_business_document(estimate: Estimate, document_type: DocumentType | str = DocumentType.commercial_offer, *, contractor_name: str = "Колибри") -> BusinessDocument:
    if isinstance(document_type, str):
        document_type = DocumentType(document_type)
    estimate = recalculate_estimate(estimate)
    label = DOCUMENT_TYPE_LABELS[document_type]
    if document_type == DocumentType.contract:
        sections = _contract_sections(estimate, contractor_name)
        attachments = [
            f"Приложение № 1 — Смета № {estimate.estimate_id}",
            "Приложение № 2 — Техническое задание или ведомость работ",
            "Приложение № 3 — Календарный план",
            "Приложение № 4 — Форма акта сдачи-приёмки",
        ]
        missing_fields = [
            "статус и полные реквизиты сторон", "полномочия подписантов", "сроки и этапы",
            "вид цены, НДС и порядок оплаты", "порядок приёмки", "гарантийный срок",
            "ответственность, расторжение и подсудность",
        ]
    elif document_type == DocumentType.commercial_offer:
        sections = _commercial_offer_sections(estimate, contractor_name)
        attachments = [f"Приложение № 1 — Смета № {estimate.estimate_id}"]
        missing_fields = ["номер и дата", "адресат", "НДС и порядок оплаты", "срок выполнения", "срок действия предложения", "реквизиты отправителя"]
    else:
        sections = [
            {"title": "Основание", "text": f"Документ сформирован по Смете № {estimate.estimate_id}: {estimate.title}."},
            {"title": "Стоимость", "text": f"Сумма: {estimate.totals.grand_total} {estimate.currency}."},
            {"title": "Проверка", "text": "Состав, статус выполнения, реквизиты и подписи сторон требуют подтверждения перед подписанием."},
        ]
        attachments = [f"Смета № {estimate.estimate_id}"]
        missing_fields = ["реквизиты сторон", "дата", "основание", "подписи"]
    return BusinessDocument(
        document_type=document_type,
        title=f"{label}: {estimate.title}",
        client_name=estimate.client_name,
        contractor_name=contractor_name,
        estimate_id=estimate.estimate_id,
        currency=estimate.currency,
        total=str(estimate.totals.grand_total),
        body_sections=sections,
        attachments=attachments,
        missing_fields=missing_fields,
    )


def create_document_pack(estimate: Estimate, *, contractor_name: str = "Колибри") -> list[BusinessDocument]:
    return [create_business_document(estimate, doc_type, contractor_name=contractor_name) for doc_type in (DocumentType.commercial_offer, DocumentType.contract, DocumentType.completion_act, DocumentType.invoice)]
