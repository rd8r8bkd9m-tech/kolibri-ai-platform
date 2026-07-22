"""Bounded task-specialisation registry for the public Kolibri assistant.

The ChatGPT/Codex skills used to maintain Kolibri are not copied wholesale into
customer prompts.  This module exposes only the small, customer-safe contract
needed for the current request.  Operator and infrastructure guidance is kept
out of the public model context by construction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Any


@dataclass(frozen=True)
class SkillContract:
    id: str
    instruction: str


_ESTIMATE_INTENT = re.compile(
    r"(?:смет|расцен|ведомост\w*\s+объ[её]м|стоимост\w*\s+(?:работ|ремонт|строит))",
    re.IGNORECASE,
)
_ESTIMATE_DOCUMENT_INTENT = re.compile(
    r"(?:коммерческ\w*\s+предложен|акт\w*\s+(?:выполн|при[её]м)|сч[её]т\w*\s+на\s+оплат|"
    r"приложен\w*\s+к\s+договор|экспорт\w*\s+(?:pdf|docx|xlsx)|(?:pdf|docx|xlsx)\b)",
    re.IGNORECASE,
)
_LEGAL_INTENT = re.compile(
    r"(?:договор|претензи|ответ\w*\s+на\s+претензи|юридическ|правов\w*\s+риск|"
    r"ответственност|неустойк|расторжен|конфиденциальност|персональн\w*\s+данн)",
    re.IGNORECASE,
)
_PRODUCT_DESIGN_INTENT = re.compile(
    r"(?:интерфейс|ux\b|ui\b|веб[- ]?приложен|мобильн\w*\s+(?:экран|верси)|"
    r"лендинг|дашборд|сайт|макет)",
    re.IGNORECASE,
)


CONSTRUCTION_ESTIMATES = SkillContract(
    "construction-estimates-ru",
    """Сметное дело (Россия): сначала извлеки объект, регион, объёмы, единицы,
сроки и исключения. Разделяй работы, материалы и услуги/оборудование. Любое
допущение называй допущением. Для каждой текущей цены нужны источник,
наблюдаемая дата, регион, единица, НДС и свежесть. Не выдумывай нормативный код
или официальную расценку. При недостатке данных используй needs_input или
preliminary, а не обещай проверенную точность.""",
)

ESTIMATE_BUILDER = SkillContract(
    "estimate-builder",
    """AI предлагает только редактируемый состав сметы. Сохраняй разделы,
позиции, типы, комментарии, допущения и вопросы. Не доверяй итогам модели:
деньги пересчитывает backend Decimal-движок. Цены без принятого доказательства
равны нулю. Не подменяй неисправимый ответ шаблонной сметой. Документ допустим
только из сохранённой рассчитанной ревизии.""",
)

ESTIMATE_DOCUMENTS = SkillContract(
    "estimate-documents",
    """Документы по смете: используй только сохранённую рассчитанную ревизию.
Согласуй номер, дату, клиента, объект, вид документа и реквизиты. Суммы документа
должны совпадать с backend-пересчётом. Не заявляй PDF/DOCX/XLSX созданным без
реального файла, bytes/hash и успешной проверки отображения кириллицы, таблиц,
итогов и разрывов страниц.""",
)

LEGAL_DOCUMENTS = SkillContract(
    "legal-documents-ru",
    """Российские юридические документы: пиши консервативно и отделяй правовой
риск, коммерческий риск и отсутствующие факты. Проверяй стороны, предмет,
оплату, приёмку, ответственность, расторжение, конфиденциальность, персональные
данные, споры и приложения. Сохраняй переданные имена, даты, суммы и реквизиты.
Не выдавай помощь в подготовке документа за заключение лицензированного юриста.""",
)

WORD_DOCUMENTS = SkillContract(
    "word-docs",
    """Для Word-документа важны профессиональная структура, единые стили,
таблицы и пагинация. Файл считается готовым только после фактической генерации
и визуальной проверки; черновой текст в чате не называй готовым DOCX.""",
)

PRODUCT_DESIGN = SkillContract(
    "webapp-product-design",
    """Для интерфейса проектируй законченный пользовательский сценарий в
существующем продукте и стиле: loading, empty, error, disabled, focus, mobile и
desktop. Не обещай сайт или приложение без реально доступной capability и
созданного проверенного артефакта.""",
)


def latest_user_text(messages: Iterable[Mapping[str, Any]]) -> str:
    for message in reversed(list(messages)):
        if str(message.get("role") or "").lower() == "user":
            return str(message.get("content") or "").strip()
    return ""


def public_skill_ids(messages: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    """Select only customer-safe skills for the current request."""
    text = latest_user_text(messages)
    selected: list[SkillContract] = []
    if _ESTIMATE_INTENT.search(text):
        selected.extend((CONSTRUCTION_ESTIMATES, ESTIMATE_BUILDER))
    if _ESTIMATE_DOCUMENT_INTENT.search(text):
        selected.extend((ESTIMATE_DOCUMENTS, WORD_DOCUMENTS))
    if _LEGAL_INTENT.search(text):
        selected.append(LEGAL_DOCUMENTS)
        if _ESTIMATE_INTENT.search(text) or _ESTIMATE_DOCUMENT_INTENT.search(text):
            selected.append(ESTIMATE_DOCUMENTS)
    if _PRODUCT_DESIGN_INTENT.search(text):
        selected.append(PRODUCT_DESIGN)
    return tuple(dict.fromkeys(skill.id for skill in selected))


def public_specialization_for_messages(
    messages: Iterable[Mapping[str, Any]],
) -> str | None:
    """Return a compact specialisation without operator-only instructions."""
    ids = public_skill_ids(messages)
    if not ids:
        return None
    contracts = {
        contract.id: contract
        for contract in (
            CONSTRUCTION_ESTIMATES,
            ESTIMATE_BUILDER,
            ESTIMATE_DOCUMENTS,
            LEGAL_DOCUMENTS,
            WORD_DOCUMENTS,
            PRODUCT_DESIGN,
        )
    }
    body = "\n\n".join(contracts[skill_id].instruction for skill_id in ids)
    return f"Активные профессиональные контракты: {', '.join(ids)}.\n\n{body}"

