from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from fastapi import HTTPException
from pydantic import ValidationError

from .config import Settings
from .database import connect_database, transaction
from .estimate_artifact import (
    GeneratedEstimateProposal,
    canonical_estimate_json,
    estimate_document_from_proposal,
    estimate_view,
    estimate_lifecycle_status,
    load_estimate_slot,
    parse_estimate_document,
    record_estimate_version,
)
from .estimate_engine import (
    PlasteringScope,
    ProjectCaseRef,
    calculate_plastering_estimate,
)
from .estimate_engine_router import (
    PlasteringCalculationInput,
    calculate_plastering,
)
from .estimate_intake import PlasteringIntake
from .estimate_document_pack import (
    DocumentPackError,
    RENDERER_VERSION,
    issue_document_pack,
)
from .market_pricing import record_price_observations
from .product_entitlements import (
    CONSTRUCTION_ESTIMATES_ENTITLEMENT,
    ProductEntitlementError,
    require_persisted_product_entitlement,
)
from .reference_price_snapshot import (
    PLASTERING_REFERENCE_PRICE_SNAPSHOT_VERSION,
    plastering_reference_price_assumption,
    plastering_reference_price_quotes,
    verify_plastering_model_price_candidates,
)
from .schemas import AgentProfile, UserRole, UserSession


class WidgetRunLike(Protocol):
    tenant_id: str
    project_id: str
    run_id: str
    public_run_id: str


@dataclass(frozen=True, slots=True)
class ProductWidget:
    arguments: dict[str, Any]
    fallback_text: str
    tool_name: str = "present"
    tool_result: dict[str, Any] | None = None


ESTIMATE_WORDS = re.compile(r"\b(?:смет\w*|estimate)\b", re.IGNORECASE)
IMAGE_GENERATION_WORDS = re.compile(
    r"\b(?:изображ\w*|картин\w*|фотограф\w*|фото|рендер\w*|"
    r"визуализац\w*|иллюстрац\w*)\b",
    re.IGNORECASE,
)
CONSTRUCTION_INTENT_WORDS = re.compile(
    r"""\b(?:
        постро\w*|строительств\w*|возвед\w*|капитальн\w*|
        фундамент\w*|кровл\w*|электр\w*|сантех\w*|кладк\w*|
        отделк\w*|дом\w*|коттедж\w*
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)
ESTIMATE_GENERATION_WORDS = re.compile(
    r"\b(?:состав\w*|подготов\w*|собер\w*|рассчит\w*|сдела\w*|"
    r"созда\w*|сформир\w*|постро\w*|оцен\w*)\b",
    re.IGNORECASE,
)
DETAILED_ESTIMATE_WORDS = re.compile(
    r"\b(?:подробн\w*|детальн\w*|разв[её]рнут\w*|поэлементн\w*|"
    r"ресурсн\w*|максимальн\w*\s+детализац\w*)\b",
    re.IGNORECASE,
)
ESTIMATE_SCOPE_QUANTITY = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*"
    r"(?:м(?:²|³|2|3)|кг|т|шт\.?|пог\.?\s*м)"
    r"(?=\s|[,.;:)]|$)",
    re.IGNORECASE,
)
ESTIMATE_SCOPE_WORDS = re.compile(
    r"\b(?:штукатур\w*|ремонт\w*|демонтаж\w*|стен\w*|пол\w*|"
    r"потол\w*|фасад\w*|кровл\w*|бетон\w*|кладк\w*|плитк\w*|"
    r"работ\w*)\b",
    re.IGNORECASE,
)
ESTIMATE_REVISION_ACTIONS = re.compile(
    r"\b(?:добав\w*|включ\w*|замен\w*|измени\w*|поменя\w*|"
    r"убер\w*|удал\w*|исключ\w*|пересчит\w*|долж\w*)\b",
    re.IGNORECASE,
)
ESTIMATE_REVISION_SCOPE = re.compile(
    r"\b(?:смет\w*|позиц\w*|площад\w*|объ[её]м\w*|фундамент\w*|"
    r"стен\w*|кровл\w*|кры(?:ш|шк)\w*|утепл\w*|окн\w*|двер\w*|"
    r"электр\w*|сантех\w*|отделк\w*|благоустройств\w*|забор\w*|"
    r"отмостк\w*|газон\w*|дорожк\w*|ландшафт\w*|огражд\w*)\b",
    re.IGNORECASE,
)
SOFT_ROOF_WORDS = re.compile(
    r"\b(?:мягк\w*\s+кровл\w*|гибк\w*\s+черепиц\w*)\b",
    re.IGNORECASE,
)
LANDSCAPE_WORDS = re.compile(
    r"\b(?:благоустройств\w*|озелен\w*|ландшафт\w*|отмостк\w*|"
    r"забор\w*|калитк\w*|ворот\w*|газон\w*|дорожк\w*|"
    r"плитк\w*\s+тротуар\w*|ливн\w*\s+(?:канализаци|решётк)\w*|"
    r"дождеприёмник\w*|бордюр\w*)\b",
    re.IGNORECASE,
)
ESTIMATE_AREA_CHANGE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:м²|м2|кв\.?\s*м)"
    r"(?=\s|[,.;:)]|$)",
    re.IGNORECASE,
)
ESTIMATE_ADD_ITEM = re.compile(
    r"\bдобав\w*\s+(?:в\s+смет\w*\s+)?(?:позиц\w*\s+)?(.+)|"
    r"(?:в\s+смет\w*\s+)добав\w*\s+(?:позиц\w*\s+)?(.+)",
    re.IGNORECASE,
)
ESTIMATE_EXPLICIT_PRICE = re.compile(
    r"(?:\bпо\b|\bцен\w*\s*[—:=]?)\s*"
    r"(\d{1,12}(?:[ \u00a0]\d{3})*(?:[.,]\d{1,2})?)\s*(?:₽|руб)",
    re.IGNORECASE,
)
ESTIMATE_EXPLICIT_QUANTITY = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*"
    r"(м²|м³|м2|м3|кг|т|шт\.?|компл\.?|пог\.?\s*м)"
    r"(?=\s|[,.;:)]|$)",
    re.IGNORECASE,
)
TECHNOLOGY_CARD_WORDS = re.compile(r"\b(?:тех(?:нологическ\w*)?\s*карт\w*)\b", re.IGNORECASE)

DOCUMENT_PACK_WORDS = re.compile(
    r"\b(?:pdf|пдф|комплект\w*|пакет\w*|документ\w*|официальн\w*|"
    r"выпуст\w*|сформир\w*|подготов\w*\s+(?:файл\w*|документ\w*|смет\w*))\b",
    re.IGNORECASE,
)
DOCUMENT_INVOICE_WORDS = re.compile(r"\b(?:сч[её]т\w*|инвойс\w*)\b", re.IGNORECASE)


LANDSCAPE_SECTION_TITLE = "Благоустройство"


def _default_landscape_rows(area: Decimal | None) -> list[dict[str, str]]:
    """Return canonical landscaping rows for the given house area."""

    perimeter = (
        (area.sqrt() * 4).quantize(Decimal("0.01"))
        if area is not None and area > 0
        else Decimal("40")
    )
    area_val = area if area is not None and area > 0 else Decimal("89")
    lawn_area = (area_val * 3).quantize(Decimal("0.01"))
    parking_area = Decimal("20")

    return [
        {
            "section": LANDSCAPE_SECTION_TITLE,
            "kind": "work",
            "description": "Подсыпка и планировка участка",
            "unit": "м³",
            "quantity": "25",
            "unitPrice": "800.00",
            "quantityBasis": "Типовая оценка для стандартного участка.",
            "priceBasis": "Фиксированный предварительный прайс Kolibri; проверить по региональным источникам.",
        },
        {
            "section": LANDSCAPE_SECTION_TITLE,
            "kind": "work",
            "description": "Отмостка вокруг дома (бетон + утепление)",
            "unit": "м.п.",
            "quantity": format(perimeter, "f"),
            "unitPrice": "2800.00",
            "quantityBasis": "Периметр дома; уточнить по фактическим размерам.",
            "priceBasis": "Фиксированный предварительный прайс Kolibri; проверить по региональным источникам.",
        },
        {
            "section": LANDSCAPE_SECTION_TITLE,
            "kind": "work",
            "description": "Дворовая площадка / парковочное место (тротуарная плитка)",
            "unit": "м²",
            "quantity": format(parking_area, "f"),
            "unitPrice": "3200.00",
            "quantityBasis": "Типовая площадь парковки; уточнить по планировке участка.",
            "priceBasis": "Фиксированный предварительный прайс Kolibri; проверить по региональным источникам.",
        },
        {
            "section": LANDSCAPE_SECTION_TITLE,
            "kind": "material",
            "description": "Бордюрный камень",
            "unit": "м.п.",
            "quantity": format(parking_area, "f"),
            "unitPrice": "700.00",
            "quantityBasis": "Типовая оценка; уточнить по планировке.",
            "priceBasis": "Фиксированный предварительный прайс Kolibri; проверить по региональным источникам.",
        },
        {
            "section": LANDSCAPE_SECTION_TITLE,
            "kind": "material",
            "description": "Забор из профнастила с воротами и калиткой",
            "unit": "м.п.",
            "quantity": "10",
            "unitPrice": "4500.00",
            "quantityBasis": "Фронтальная часть участка; уточнить по периметру.",
            "priceBasis": "Фиксированный предварительный прайс Kolibri; проверить по региональным источникам.",
        },
        {
            "section": LANDSCAPE_SECTION_TITLE,
            "kind": "service",
            "description": "Ливневая канализация и дождеприёмники",
            "unit": "компл.",
            "quantity": "1",
            "unitPrice": "35000.00",
            "quantityBasis": "Комплект на весь дом; уточнить по проекту.",
            "priceBasis": "Фиксированный предварительный прайс Kolibri; проверить по региональным источникам.",
        },
        {
            "section": LANDSCAPE_SECTION_TITLE,
            "kind": "work",
            "description": "Засев газона (подготовка + семена + удобрения)",
            "unit": "м²",
            "quantity": format(lawn_area, "f"),
            "unitPrice": "250.00",
            "quantityBasis": "Примерная площадь озеленения; уточнить по плану участка.",
            "priceBasis": "Фиксированный предварительный прайс Kolibri; проверить по региональным источникам.",
        },
    ]


def is_estimate_prompt(prompt: str) -> bool:
    # A construction noun alone must not turn an image request (for example,
    # “рендер деревянного дома”) into a paid estimate run. An explicit
    # estimate term remains authoritative, so mixed requests can still ask
    # for both an estimate and a visual asset.
    if ESTIMATE_WORDS.search(prompt) is not None:
        return True
    if IMAGE_GENERATION_WORDS.search(prompt) is not None:
        return False
    return CONSTRUCTION_INTENT_WORDS.search(prompt) is not None


def is_document_pack_prompt(prompt: str) -> bool:
    """Return true only for a construction estimate document-pack request."""

    return is_estimate_prompt(prompt) and DOCUMENT_PACK_WORDS.search(prompt) is not None


def _plain_decimal(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def is_estimate_generation_prompt(prompt: str) -> bool:
    return is_estimate_prompt(prompt) and (
        ESTIMATE_GENERATION_WORDS.search(prompt) is not None
        or TECHNOLOGY_CARD_WORDS.search(prompt) is not None
        or CONSTRUCTION_INTENT_WORDS.search(prompt) is not None
        or (
            ESTIMATE_SCOPE_QUANTITY.search(prompt) is not None
            and ESTIMATE_SCOPE_WORDS.search(prompt) is not None
        )
    )


def is_detailed_estimate_prompt(prompt: str) -> bool:
    """Return whether the user explicitly requests production-level detail."""

    return is_estimate_generation_prompt(prompt) and (
        DETAILED_ESTIMATE_WORDS.search(prompt) is not None
    )


def has_estimate_scope_input(prompt: str) -> bool:
    """Return whether a request contains inputs for a new calculation."""

    return (
        TECHNOLOGY_CARD_WORDS.search(prompt) is not None
        or re.search(
            r"""\b(?:
                дом|коттедж|фундамент|кровл\w*|электр\w*|сантех\w*|
                отделк\w*|фасад\w*
            )\b""",
            prompt,
            flags=re.IGNORECASE | re.VERBOSE,
        )
        is not None
        or (
            ESTIMATE_SCOPE_QUANTITY.search(prompt) is not None
            and ESTIMATE_SCOPE_WORDS.search(prompt) is not None
        )
    )


def is_estimate_revision_prompt(prompt: str) -> bool:
    """Return whether a message intends to mutate the saved estimate."""

    # A full new-calculation request can legitimately contain revision verbs,
    # for example: "Составь смету дома ... включи фасад и кровлю".  The
    # explicit generation verb plus concrete scope is authoritative; without
    # this guard such a request is misrouted to the existing-document editor
    # before the durable generation pipeline can start.
    if (
        ESTIMATE_GENERATION_WORDS.search(prompt) is not None
        and is_estimate_generation_prompt(prompt)
        and has_estimate_scope_input(prompt)
    ):
        return False
    return (
        ESTIMATE_REVISION_ACTIONS.search(prompt) is not None
        and ESTIMATE_REVISION_SCOPE.search(prompt) is not None
    )


def deterministic_estimate_revision_proposal(
    settings: Settings,
    accepted: WidgetRunLike,
    *,
    prompt: str,
) -> GeneratedEstimateProposal | None:
    """Apply supported chat edits to the current estimate as a new proposal.

    The model is deliberately not allowed to invent arithmetic here. Existing
    quantities and rates are retained unless the user explicitly changes a
    supported parameter; the persisted document is recalculated later by the
    decimal estimate engine.
    """

    if not is_estimate_revision_prompt(prompt):
        return None
    database = connect_database(settings.database_url)
    try:
        _require_estimate_run_entitlement(database, accepted)
        slot = load_estimate_slot(
            database,
            tenant_id=accepted.tenant_id,
            project_id=accepted.project_id,
        )
        if slot is None:
            return None
        current = parse_estimate_document(
            slot["content_json"],
            now=str(slot["updated_at"]),
        )
    finally:
        database.close()
    current_rows = current.get("rows")
    if not isinstance(current_rows, list) or not current_rows:
        return None

    rows: list[dict[str, str]] = []
    changed = False
    soft_roof_requested = SOFT_ROOF_WORDS.search(prompt) is not None
    landscape_requested = LANDSCAPE_WORDS.search(prompt) is not None
    area_match = ESTIMATE_AREA_CHANGE.search(prompt)
    current_area_match = ESTIMATE_AREA_CHANGE.search(str(current.get("title") or ""))
    new_area = Decimal(area_match.group(1).replace(",", ".")) if area_match is not None else None
    current_area = (
        Decimal(current_area_match.group(1).replace(",", "."))
        if current_area_match is not None
        else None
    )

    has_landscape_section = False
    for item in current_rows:
        if not isinstance(item, dict):
            continue
        section = str(item.get("section") or "Прочее")
        description = str(item.get("description") or "")
        if section == LANDSCAPE_SECTION_TITLE:
            has_landscape_section = True
        price_basis = str(item.get("price_basis") or "Предыдущая версия сметы")
        new_description = description
        new_price_basis = price_basis
        if (
            soft_roof_requested
            and ("кров" in description.casefold() or "стропил" in description.casefold())
            and "утепл" not in description.casefold()
            and description != "Стропильная система и мягкая кровля"
        ):
            new_description = "Стропильная система и мягкая кровля"
            new_price_basis = (
                "Ставка сохранена из предыдущей версии сметы; "
                "источник цены на мягкую кровлю требует подтверждения."
            )
        quantity = str(item.get("quantity") or "0")
        quantity_basis = str(item.get("quantity_basis") or "Предыдущая версия сметы")
        unit = str(item.get("unit") or "компл.")
        if (
            new_area is not None
            and current_area is not None
            and new_area > 0
            and new_area != current_area
            and unit.casefold() in {"м²", "м³", "м2", "м3", "кг"}
            and "каноническ" in quantity_basis.casefold()
        ):
            scaled = (Decimal(quantity) * new_area / current_area).quantize(Decimal("0.01"))
            quantity = format(scaled, "f").rstrip("0").rstrip(".")
            quantity_basis = re.sub(
                rf"\b{re.escape(_plain_decimal(current_area))}"
                r"\s*м²",
                f"{_plain_decimal(new_area)} м²",
                quantity_basis,
                count=1,
            )
            changed = True
        if new_description != description or new_price_basis != price_basis:
            changed = True
        rows.append(
            {
                "section": section,
                "kind": str(item.get("kind") or "service"),
                "description": new_description,
                "unit": unit,
                "quantity": quantity,
                "unitPrice": str(item.get("unit_price") or "0.00"),
                "quantityBasis": quantity_basis,
                "priceBasis": new_price_basis,
            }
        )

    if landscape_requested and not has_landscape_section:
        area_for_landscape = current_area if current_area is not None else None
        landscape_rows = _default_landscape_rows(area_for_landscape)
        remaining = 24 - len(rows)
        rows.extend(landscape_rows[:remaining])
        changed = True

    add_match = ESTIMATE_ADD_ITEM.search(prompt)
    if (
        add_match is not None
        and not soft_roof_requested
        and not landscape_requested
        and new_area is None
        and len(rows) < 24
    ):
        raw_description = (add_match.group(1) or add_match.group(2) or "").strip(" .,:;")
        if raw_description:
            quantity_match = ESTIMATE_EXPLICIT_QUANTITY.search(raw_description)
            price_match = ESTIMATE_EXPLICIT_PRICE.search(raw_description)
            quantity = (
                quantity_match.group(1).replace(",", ".") if quantity_match is not None else "1"
            )
            unit = (
                quantity_match.group(2).replace("м2", "м²").replace("м3", "м³")
                if quantity_match is not None
                else "компл."
            )
            unit_price = (
                price_match.group(1).replace(" ", "").replace("\u00a0", "").replace(",", ".")
                if price_match is not None
                else "0.00"
            )
            rows.append(
                {
                    "section": "Дополнительные позиции",
                    "kind": "service",
                    "description": raw_description[:300],
                    "unit": unit,
                    "quantity": quantity,
                    "unitPrice": unit_price,
                    "quantityBasis": (
                        "Указано пользователем в сообщении."
                        if quantity_match is not None
                        else "Количество не указано; временно принят 1 комплект."
                    ),
                    "priceBasis": (
                        "Цена указана пользователем в сообщении."
                        if price_match is not None
                        else "Цена не указана; позиция сохранена с нулевой ставкой "
                        "до добавления проверенного источника."
                    ),
                }
            )
            changed = True
    if not changed:
        return None

    assumptions = [str(item) for item in current.get("assumptions", []) if isinstance(item, str)]
    roof_note = (
        "Уточнение пользователя: кровельное покрытие — мягкая кровля. "
        "До подтверждения источника сохранена ставка предыдущей версии."
    )
    if roof_note not in assumptions and soft_roof_requested:
        assumptions.append(roof_note)
    landscape_note = (
        "Уточнение пользователя: добавлен раздел «Благоустройство». "
        "Количество и цены требуют проверки по проекту и региональным источникам."
    )
    if landscape_note not in assumptions and landscape_requested:
        assumptions.append(landscape_note)
    title = str(current.get("title") or "Смета")
    if new_area is not None and current_area is not None and new_area != current_area:
        old_area_text = _plain_decimal(current_area)
        new_area_text = _plain_decimal(new_area)
        title = re.sub(
            rf"\b{re.escape(old_area_text)}\s*м²",
            f"{new_area_text} м²",
            title,
            count=1,
        )
        assumptions = [
            re.sub(
                rf"\b{re.escape(old_area_text)}\s*м²",
                f"{new_area_text} м²",
                assumption,
                count=1,
            )
            for assumption in assumptions
        ]
        assumptions.append(
            f"Уточнение пользователя: площадь изменена с "
            f"{old_area_text} до {new_area_text} м²; зависимые объёмы пересчитаны."
        )
    if add_match is not None and not soft_roof_requested and new_area is None:
        assumptions.append(
            "Добавленная через чат позиция требует проверки количества и "
            "источника цены перед выпуском сметы."
        )
    return GeneratedEstimateProposal.model_validate(
        {
            "title": title,
            "region": str(current.get("region") or "Регион не указан"),
            "assumptions": assumptions[-20:],
            "rows": rows,
        }
    )


def deterministic_house_estimate_proposal(
    prompt: str,
) -> GeneratedEstimateProposal | None:
    """Build the canonical first-pass house BOQ without provider variance."""

    normalized = prompt.casefold()
    if not re.search(r"дом|коттедж|жил\w*\s+дом", normalized):
        return None
    area_match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(?:м²|м2|кв\.?\s*м)",
        normalized,
    )
    if area_match is None:
        return None
    area = Decimal(area_match.group(1).replace(",", "."))
    if area <= 0 or area > 10_000:
        return None
    area_text = _plain_decimal(area)
    region_match = re.search(
        r"(?:\bрегион\s*[—:-]?\s*|\bв\s+)"
        r"([А-ЯЁ][А-Яа-яЁё-]*(?:\s+[А-ЯЁ][А-Яа-яЁё-]*)?)",
        prompt,
    )
    region = region_match.group(1).strip(" .,;:") if region_match else "Регион не указан"
    # Keep the persisted region useful for filtering and price-source lookup.
    # The common request form is "в Москве", while the estimate contract
    # expects a stable region label rather than a grammatical case.
    region = {
        "Москве": "Москва",
        "Москву": "Москва",
        "Москвой": "Москва",
        "Казани": "Казань",
        "Казань": "Казань",
        "Самаре": "Самара",
        "Самару": "Самара",
        "Питере": "Петербург",
        "Петербурге": "Петербург",
    }.get(region, region)
    if region.casefold() in {"питер", "самар", "самары"}:
        region = "Регион не указан"

    def qty(value: Decimal) -> str:
        return format(value.quantize(Decimal("0.01")), "f").rstrip("0").rstrip(".")

    def row(
        section: str, kind: str, description: str, unit: str, quantity: Decimal, unit_price: str
    ) -> dict[str, str]:
        return {
            "section": section,
            "kind": kind,
            "description": description,
            "unit": unit,
            "quantity": qty(quantity),
            "unitPrice": unit_price,
            "quantityBasis": f"Каноническая формула Kolibri для площади {area_text} м²; уточнить по рабочей документации.",
            "priceBasis": "Фиксированный предварительный прайс Kolibri; проверить по региональным источникам перед выпуском.",
        }

    rows = [
        row("Подготовка", "work", "Подготовка строительной площадки", "м²", area, "350.00"),
        row(
            "Земляные работы",
            "work",
            "Разработка грунта под фундамент",
            "м³",
            area * Decimal("0.18"),
            "1800.00",
        ),
        row(
            "Фундамент",
            "material",
            "Фундамент монолитный с материалами",
            "м³",
            area * Decimal("0.16"),
            "12500.00",
        ),
        row("Фундамент", "material", "Армирование фундамента", "кг", area * Decimal(18), "190.00"),
        row(
            "Коробка",
            "material",
            "Стены наружные с кладкой и материалами",
            "м²",
            area * Decimal("1.8"),
            "8500.00",
        ),
        row(
            "Кровля",
            "work",
            "Стропильная система и кровельное покрытие",
            "м²",
            area * Decimal("1.35"),
            "2450.00",
        ),
        row("Кровля", "material", "Утепление кровли", "м²", area * Decimal("1.35"), "1250.00"),
        row("Проёмы", "material", "Окна ПВХ", "шт", Decimal(4), "35000.00"),
        row("Проёмы", "material", "Входная дверь", "шт", Decimal(1), "45000.00"),
        row(
            "Инженерные сети",
            "service",
            "Электромонтажные работы и материалы",
            "м²",
            area,
            "2800.00",
        ),
        row(
            "Инженерные сети",
            "service",
            "Сантехнический комплект",
            "компл.",
            Decimal(1),
            "95000.00",
        ),
        row("Отделка", "work", "Черновая и чистовая внутренняя отделка", "м²", area, "6500.00"),
    ]
    return GeneratedEstimateProposal.model_validate(
        {
            "title": f"Строительство одноэтажного дома {area_text} м²",
            "region": region,
            "assumptions": [
                f"Площадь дома: {area_text} м².",
                "Этажность: один этаж; тип грунта, фундамент, планировка и инженерные вводы требуют подтверждения.",
                "Смета предварительная: фиксированный состав и ставки нужны для повторяемого сравнения сценариев.",
            ],
            "rows": rows,
        }
    )


def deterministic_construction_estimate_proposal(
    prompt: str,
) -> GeneratedEstimateProposal | None:
    """Create a bounded non-plaster preliminary scope for universal briefs.

    This is intentionally a proposal, not a normative estimate.  A request
    with an explicit plastering signal is left to the existing plastering
    technology-card path so the specialized calculation remains intact.
    """

    normalized = prompt.casefold()
    if re.search(r"штукатур", normalized):
        return None
    scope_kind: str | None = None
    if re.search(r"фундамент|основани", normalized):
        scope_kind = "foundation"
    elif re.search(r"кровл|кры[шш]", normalized):
        scope_kind = "roof"
    elif re.search(r"электр", normalized):
        scope_kind = "electrical"
    elif re.search(r"сантех|водоснаб|канализаци", normalized):
        scope_kind = "plumbing"
    elif re.search(r"ремонт|отделк|квартир", normalized):
        scope_kind = "renovation"
    if scope_kind is None:
        return None
    area_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:м²|м2|кв\.?\s*м)", normalized)
    volume_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:м³|м3)", normalized)
    area = Decimal(area_match.group(1).replace(",", ".")) if area_match else None
    volume = Decimal(volume_match.group(1).replace(",", ".")) if volume_match else None
    if area is None and volume is None:
        return None
    measure = area or volume or Decimal("1")
    region_match = re.search(
        r"(?:\bрегион\s*[—:-]?\s*|\bв\s+)([А-ЯЁ][А-Яа-яЁё-]*(?:\s+[А-ЯЁ][А-Яа-яЁё-]*)?)",
        prompt,
    )
    region = region_match.group(1).strip(" .,;:") if region_match else "Регион не указан"
    region = {"Казани": "Казань", "Самаре": "Самара", "Москве": "Москва"}.get(region, region)
    if region.casefold() in {"питер", "самар", "самары"}:
        region = "Регион не указан"

    def row(
        section: str, kind: str, description: str, unit: str, quantity: Decimal, price: str
    ) -> dict[str, str]:
        quantity_text = format(quantity.quantize(Decimal("0.01")), "f").rstrip("0").rstrip(".")
        return {
            "section": section,
            "kind": kind,
            "description": description,
            "unit": unit,
            "quantity": quantity_text,
            "unitPrice": price,
            "quantityBasis": "Предварительная формула по brief; подтвердить рабочей документацией.",
            "priceBasis": "Предварительная гипотеза AI; проверить по поставщикам и региональным наблюдениям.",
        }

    row_sets: dict[str, list[dict[str, str]]] = {
        "foundation": [
            row(
                "Подготовка",
                "work",
                "Разработка грунта под фундамент",
                "м³",
                volume or measure * Decimal("0.18"),
                "1800.00",
            ),
            row(
                "Фундамент", "material", "Бетон для фундамента", "м³", volume or measure, "12500.00"
            ),
            row(
                "Фундамент",
                "material",
                "Арматура для фундамента",
                "кг",
                measure * Decimal("18"),
                "190.00",
            ),
            row(
                "Фундамент",
                "work",
                "Устройство опалубки и бетонирование",
                "м³",
                volume or measure,
                "5200.00",
            ),
        ],
        "roof": [
            row(
                "Кровля",
                "work",
                "Стропильная система и кровельное покрытие",
                "м²",
                measure * Decimal("1.35"),
                "2450.00",
            ),
            row(
                "Кровля", "material", "Утепление кровли", "м²", measure * Decimal("1.35"), "1250.00"
            ),
            row(
                "Кровля",
                "material",
                "Гидроизоляция и доборные элементы",
                "м²",
                measure * Decimal("1.35"),
                "680.00",
            ),
        ],
        "electrical": [
            row(
                "Инженерные сети",
                "service",
                "Монтаж внутренних электрических сетей",
                "м²",
                measure,
                "2800.00",
            ),
            row(
                "Инженерные сети",
                "material",
                "Кабель и модульное оборудование",
                "м²",
                measure,
                "2100.00",
            ),
            row(
                "Инженерные сети",
                "equipment",
                "Измерения и испытания",
                "компл.",
                Decimal("1"),
                "18000.00",
            ),
        ],
        "plumbing": [
            row(
                "Инженерные сети",
                "service",
                "Монтаж водоснабжения и канализации",
                "м²",
                measure,
                "2500.00",
            ),
            row("Инженерные сети", "material", "Трубы и фасонные части", "м²", measure, "1700.00"),
            row(
                "Инженерные сети",
                "service",
                "Гидравлическое испытание",
                "компл.",
                Decimal("1"),
                "9000.00",
            ),
        ],
        "renovation": [
            row("Подготовка", "work", "Подготовка и защита помещений", "м²", measure, "350.00"),
            row("Демонтаж", "work", "Демонтаж существующих покрытий", "м²", measure, "550.00"),
            row("Отделка", "work", "Черновая и чистовая отделка", "м²", measure, "6500.00"),
            row("Инженерные сети", "service", "Электромонтажные работы", "м²", measure, "2800.00"),
            row(
                "Уборка",
                "service",
                "Уборка и вывоз строительных отходов",
                "компл.",
                Decimal("1"),
                "18000.00",
            ),
        ],
    }
    area_text = format(measure, "f").rstrip("0").rstrip(".")
    titles = {
        "foundation": "Предварительная смета фундамента",
        "roof": "Предварительная смета кровли",
        "electrical": "Предварительная смета электромонтажа",
        "plumbing": "Предварительная смета сантехнических работ",
        "renovation": "Предварительная смета ремонта",
    }
    return GeneratedEstimateProposal.model_validate(
        {
            "title": f"{titles[scope_kind]} · {area_text} {('м³' if volume is not None and area is None else 'м²')}",
            "region": region,
            "assumptions": [
                "Состав и цены предварительные; подтверждённые нормативы и коммерческие источники не подставлялись.",
                "Ключевые размеры, технология, спецификации, доступность и логистика требуют уточнения.",
            ],
            "rows": row_sets[scope_kind],
        }
    )


def _require_estimate_run_entitlement(
    database: Any,
    accepted: WidgetRunLike,
) -> str:
    actor = database.execute(
        """
        SELECT requested_by_user_id
        FROM chat_runs
        WHERE tenant_id = ? AND id = ?
        LIMIT 1
        """,
        (accepted.tenant_id, accepted.run_id),
    ).fetchone()
    if actor is None:
        raise RuntimeError("estimate run actor is missing")
    actor_user_id = str(actor["requested_by_user_id"])
    try:
        require_persisted_product_entitlement(
            database,
            tenant_id=accepted.tenant_id,
            user_id=actor_user_id,
            entitlement_code=CONSTRUCTION_ESTIMATES_ENTITLEMENT,
        )
    except ProductEntitlementError as exc:
        raise RuntimeError("estimate product entitlement is unavailable") from exc
    return actor_user_id


def _estimate_widget(
    settings: Settings,
    accepted: WidgetRunLike,
) -> ProductWidget | None:
    database = connect_database(settings.database_url)
    try:
        _require_estimate_run_entitlement(database, accepted)
        slot = load_estimate_slot(
            database,
            tenant_id=accepted.tenant_id,
            project_id=accepted.project_id,
        )
        if slot is None:
            return None
        now = str(slot["updated_at"])
        document = parse_estimate_document(slot["content_json"], now=now)
        if not document["rows"]:
            return None
        view = estimate_view(
            project_id=accepted.project_id,
            document_id=str(slot["id"]),
            version=int(slot["version"]),
            status=str(slot["status"]),
            document=document,
            row_limit=0,
        )
    finally:
        database.close()
    return ProductWidget(
        arguments={"$type": "EstimateEditor", **view},
        fallback_text=(
            f"Открыта редактируемая смета «{view['estimateTitle']}», версия {view['version']}."
        ),
    )


def _estimate_identity_projection(
    rows: object,
) -> tuple[tuple[str, str | None, str | None, str | None], ...]:
    if not isinstance(rows, list):
        raise RuntimeError("generated estimate persistence invariant failed: rows are missing")
    projection: list[tuple[str, str | None, str | None, str | None]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("generated estimate persistence invariant failed: row is invalid")
        row_id = row.get("id")
        if not isinstance(row_id, str) or not row_id:
            raise RuntimeError("generated estimate persistence invariant failed: row id is missing")
        projection.append(
            (
                row_id,
                str(row["operation_id"]) if row.get("operation_id") is not None else None,
                str(row["resource_id"]) if row.get("resource_id") is not None else None,
                str(row["technology_card_version"])
                if row.get("technology_card_version") is not None
                else None,
            )
        )
    return tuple(projection)


def _verified_generated_estimate_view(
    database: Any,
    *,
    accepted: WidgetRunLike,
    proposal: GeneratedEstimateProposal,
    document_id: str,
    estimate_version: int,
    expected_document: dict[str, Any],
) -> dict[str, Any]:
    """Reload and prove that every generated row reached the editor document."""

    expected_rows = expected_document.get("rows")
    expected_projection = _estimate_identity_projection(expected_rows)
    if len(expected_projection) != len(proposal.rows):
        raise RuntimeError(
            "generated estimate persistence invariant failed: proposal row count changed"
        )
    for proposal_row, identity in zip(proposal.rows, expected_projection, strict=True):
        expected_identity = (
            proposal_row.id or identity[0],
            proposal_row.operation_id,
            proposal_row.resource_id,
            proposal_row.technology_card_version,
        )
        if identity != expected_identity:
            raise RuntimeError(
                "generated estimate persistence invariant failed: materialized row identity changed"
            )

    persisted_slot = load_estimate_slot(
        database,
        tenant_id=accepted.tenant_id,
        project_id=accepted.project_id,
    )
    if (
        persisted_slot is None
        or str(persisted_slot["id"]) != document_id
        or int(persisted_slot["version"]) != estimate_version
    ):
        raise RuntimeError(
            "generated estimate persistence invariant failed: editor document version is missing"
        )
    persisted_document = parse_estimate_document(
        persisted_slot["content_json"],
        now=str(persisted_slot["updated_at"]),
    )
    if _estimate_identity_projection(persisted_document.get("rows")) != expected_projection:
        raise RuntimeError(
            "generated estimate persistence invariant failed: editor rows do not match proposal"
        )

    persisted_version = database.execute(
        """
        SELECT status, content_json, created_at
        FROM estimate_versions
        WHERE tenant_id = ? AND project_id = ? AND document_id = ?
          AND version = ?
        LIMIT 1
        """,
        (
            accepted.tenant_id,
            accepted.project_id,
            document_id,
            estimate_version,
        ),
    ).fetchone()
    if persisted_version is None:
        raise RuntimeError(
            "generated estimate persistence invariant failed: immutable version is missing"
        )
    version_document = parse_estimate_document(
        persisted_version["content_json"],
        now=str(persisted_version["created_at"]),
    )
    if _estimate_identity_projection(version_document.get("rows")) != expected_projection:
        raise RuntimeError(
            "generated estimate persistence invariant failed: version rows do not match proposal"
        )

    view = estimate_view(
        project_id=accepted.project_id,
        document_id=document_id,
        version=estimate_version,
        status=str(persisted_slot["status"]),
        document=persisted_document,
        row_limit=0,
    )
    expected_count = len(proposal.rows)
    row_page = view.get("rowPage")
    pricing = view.get("pricing")
    totals = view.get("totals")
    persisted_totals = persisted_document.get("totals")
    if (
        not isinstance(row_page, dict)
        or row_page.get("totalRows") != expected_count
        or not isinstance(pricing, dict)
        or pricing.get("totalRows") != expected_count
        or not isinstance(totals, dict)
        or not isinstance(persisted_totals, dict)
        or totals.get("total") != str(persisted_totals.get("total") or "0.00")
    ):
        raise RuntimeError(
            "generated estimate persistence invariant failed: editor totals do not match proposal"
        )
    return view


def materialize_generated_estimate_widget(
    settings: Settings,
    accepted: WidgetRunLike,
    *,
    proposal: GeneratedEstimateProposal,
    provider_profile: str,
    replace_existing: bool = False,
    generation_metadata: dict[str, str] | None = None,
) -> ProductWidget:
    database = connect_database(settings.database_url)
    try:
        with transaction(database, immediate=True):
            actor_user_id = _require_estimate_run_entitlement(
                database,
                accepted,
            )
            slot = load_estimate_slot(
                database,
                tenant_id=accepted.tenant_id,
                project_id=accepted.project_id,
            )
            if slot is None:
                raise RuntimeError("estimate document slot is missing")

            current = parse_estimate_document(
                slot["content_json"],
                now=str(slot["updated_at"]),
            )
            replay_version = None
            if generation_metadata is not None:
                replay_version = database.execute(
                    """
                    SELECT document_id, version, status, content_json, created_at
                    FROM estimate_versions
                    WHERE tenant_id = ? AND project_id = ?
                      AND origin_type = 'ai_proposal' AND origin_run_id = ?
                    ORDER BY version DESC LIMIT 1
                    """,
                    (
                        accepted.tenant_id,
                        accepted.project_id,
                        accepted.run_id,
                    ),
                ).fetchone()
                if replay_version is not None:
                    replay_document = parse_estimate_document(
                        replay_version["content_json"],
                        now=str(replay_version["created_at"]),
                    )
                    replay_generation = replay_document.get("generation")
                    expected_generation_run = generation_metadata.get("estimate_generation_run_id")
                    expected_rows_hash = generation_metadata.get("expanded_rows_hash")
                    if not (
                        isinstance(replay_generation, dict)
                        and replay_generation.get("estimate_generation_run_id")
                        == expected_generation_run
                        and replay_generation.get("expanded_rows_hash") == expected_rows_hash
                    ):
                        replay_version = None
            if replay_version is not None:
                view = estimate_view(
                    project_id=accepted.project_id,
                    document_id=str(replay_version["document_id"]),
                    version=int(replay_version["version"]),
                    status=str(replay_version["status"]),
                    document=replay_document,
                    row_limit=0,
                )
            elif current["rows"] and not replace_existing:
                view = estimate_view(
                    project_id=accepted.project_id,
                    document_id=str(slot["id"]),
                    version=int(slot["version"]),
                    status=str(slot["status"]),
                    document=current,
                    row_limit=0,
                )
            else:
                now = str(
                    database.execute("SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')").fetchone()[0]
                )
                document = estimate_document_from_proposal(
                    proposal,
                    now=now,
                    provider_profile=provider_profile,
                    run_id=accepted.run_id,
                    generation_metadata=generation_metadata,
                )
                estimate_version = int(slot["version"]) + (1 if current["rows"] else 0)
                lifecycle_status = estimate_lifecycle_status(document, "draft")
                database.execute(
                    """
                    UPDATE document_slots
                    SET version = ?, status = 'draft', estimate_lifecycle_status = ?,
                        content_json = ?, updated_at = ?
                    WHERE tenant_id = ? AND id = ? AND version = ?
                    """,
                    (
                        estimate_version,
                        lifecycle_status,
                        canonical_estimate_json(document),
                        now,
                        accepted.tenant_id,
                        slot["id"],
                        int(slot["version"]),
                    ),
                )
                record_estimate_version(
                    database,
                    tenant_id=accepted.tenant_id,
                    project_id=accepted.project_id,
                    document_id=str(slot["id"]),
                    version=estimate_version,
                    # estimate_versions.status is the persisted document
                    # state; lifecycle_status is a separate derived field.
                    status="draft",
                    document=document,
                    origin_type="ai_proposal",
                    origin_run_id=accepted.run_id,
                    created_by_user_id=actor_user_id,
                    created_at=now,
                )
                # Unknown AI rows are private review candidates. They never
                # enter the approved catalog or market index implicitly. A
                # large estimate may repeat the same resource across many
                # zones, so create one review candidate per normalized
                # resource rather than one database row per estimate line.
                candidate_keys: set[tuple[str, str, str]] = set()
                for generated_row in document.get("rows", []):
                    if not isinstance(generated_row, dict):
                        continue
                    if generated_row.get("catalog_entry_id") is not None:
                        continue
                    candidate_kind = str(generated_row.get("kind") or "service")
                    if candidate_kind in {"overhead", "tax", "contingency"}:
                        continue
                    candidate_key = (
                        " ".join(str(generated_row.get("description") or "").casefold().split()),
                        candidate_kind,
                        " ".join(str(generated_row.get("unit") or "шт.").casefold().split()),
                    )
                    if candidate_key in candidate_keys:
                        continue
                    candidate_keys.add(candidate_key)
                    candidate_id = f"catalog_candidate_{uuid.uuid4().hex}"
                    audit_json = json.dumps(
                        [{"event": "created", "at": now, "actor": actor_user_id}],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    database.execute(
                        """
                        INSERT INTO catalog_candidates (
                            id, tenant_id, project_id, source_type, original_text,
                            proposed_canonical_name, proposed_short_name, kind,
                            proposed_unit, specification_json, aliases_json,
                            category_id, confidence, source_estimate_id,
                            source_estimate_version, source_row_id, status,
                            audit_json, created_at, updated_at
                        ) VALUES (?, ?, ?, 'ai_generated', ?, ?, ?, ?, ?, '{}',
                                  '[]', ?, '0.2', ?, ?, ?, 'proposed', ?, ?, ?)
                        """,
                        (
                            candidate_id,
                            accepted.tenant_id,
                            accepted.project_id,
                            str(generated_row.get("description") or "")[:2_000],
                            str(generated_row.get("description") or "")[:300],
                            str(generated_row.get("description") or "")[:160],
                            candidate_kind,
                            str(generated_row.get("unit") or "шт.")[:32],
                            str(generated_row.get("section") or "Прочее")[:120],
                            str(slot["id"]),
                            estimate_version,
                            str(generated_row.get("id") or "")[:120],
                            audit_json,
                            now,
                            now,
                        ),
                    )
                    database.execute(
                        """
                        INSERT INTO catalog_candidate_events (
                            id, tenant_id, candidate_id, event_type,
                            actor_user_id, payload_json, created_at
                        ) VALUES (?, ?, ?, 'created', ?, ?, ?)
                        """,
                        (
                            f"catalog_candidate_event_{uuid.uuid4().hex}",
                            accepted.tenant_id,
                            candidate_id,
                            actor_user_id,
                            json.dumps(
                                {"sourceType": "ai_generated", "estimateVersion": estimate_version},
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                            now,
                        ),
                    )
                record_price_observations(
                    database,
                    tenant_id=accepted.tenant_id,
                    project_id=accepted.project_id,
                    document_id=str(slot["id"]),
                    estimate_version=estimate_version,
                    previous_document=current if current["rows"] else None,
                    document=document,
                    source_type="ai_preliminary",
                    lifecycle="draft",
                    created_by_user_id=actor_user_id,
                    observed_at=now,
                )
                database.execute(
                    """
                    UPDATE projects
                    SET updated_at = ?
                    WHERE tenant_id = ? AND id = ?
                    """,
                    (now, accepted.tenant_id, accepted.project_id),
                )
                view = _verified_generated_estimate_view(
                    database,
                    accepted=accepted,
                    proposal=proposal,
                    document_id=str(slot["id"]),
                    estimate_version=estimate_version,
                    expected_document=document,
                )
    finally:
        database.close()

    return ProductWidget(
        arguments={"$type": "EstimateEditor", **view},
        fallback_text=(
            f"Подготовлена предварительная смета «{view['estimateTitle']}»: "
            f"{view['pricing']['totalRows']} позиций на {view['totals']['total']} ₽. "
            "Количество и цены с пометкой «предварительная оценка» требуют проверки."
        ),
    )


def materialize_estimate_document_pack_widget(
    settings: Settings,
    accepted: WidgetRunLike,
    *,
    prompt: str,
) -> ProductWidget:
    """Create an immutable document issue and expose its persisted artifacts."""

    explicit_issue = bool(
        re.search(r"\b(?:официальн\w*|выпуст\w*|готов\w*\s+комплект)\b", prompt, re.IGNORECASE)
    )
    mode = "issue" if explicit_issue else "preliminary"
    requested_kinds: tuple[str, ...] = (
        ("pack", "invoice") if DOCUMENT_INVOICE_WORDS.search(prompt) else ("pack",)
    )

    def needs_input(version: int, required: tuple[str, ...], message: str) -> ProductWidget:
        arguments = {
            "$type": "EstimateDocumentPack",
            "schemaId": "kolibri.estimate-document-pack",
            "schemaVersion": "1.0",
            "projectId": accepted.project_id,
            "estimateVersion": version,
            "status": "needs_input",
            "mode": mode,
            "rendererVersion": RENDERER_VERSION,
            "requiredFields": list(required),
            "files": [],
        }
        return ProductWidget(
            arguments=arguments,
            fallback_text=message,
            tool_name="create_estimate_document_pack",
            tool_result={
                "rendered": True,
                "status": "needs_input",
                "requiredFields": list(required),
                "estimateVersion": version,
            },
        )

    database = connect_database(settings.database_url)
    try:
        _require_estimate_run_entitlement(database, accepted)
        slot = load_estimate_slot(
            database,
            tenant_id=accepted.tenant_id,
            project_id=accepted.project_id,
        )
        if slot is None:
            return needs_input(0, ("Сохранённая версия сметы",), "Сначала сохраните смету проекта.")
        version = int(slot["version"])
        current = parse_estimate_document(slot["content_json"], now=str(slot["updated_at"]))
        has_rows = isinstance(current.get("rows"), list) and bool(current["rows"])
    finally:
        database.close()

    # A combined “смета + PDF” request should be useful in one turn for the
    # deterministic construction intents already supported by the chat runtime.
    if not has_rows:
        proposal = deterministic_house_estimate_proposal(
            prompt
        ) or deterministic_construction_estimate_proposal(prompt)
        if proposal is None:
            return needs_input(
                version,
                (
                    "Описание объекта и состав работ",
                    "Основные размеры или объёмы",
                    "Регион объекта",
                ),
                "Для подготовки комплекта укажите объект, объёмы и регион.",
            )
        try:
            materialize_generated_estimate_widget(
                settings,
                accepted,
                proposal=proposal,
                provider_profile="server-document-pack-estimate",
                replace_existing=True,
            )
        except (RuntimeError, ValueError):
            return needs_input(
                version,
                ("Сохранённая версия сметы",),
                "Смету не удалось сохранить перед выпуском комплекта.",
            )
        database = connect_database(settings.database_url)
        try:
            slot = load_estimate_slot(
                database, tenant_id=accepted.tenant_id, project_id=accepted.project_id
            )
            if slot is None:
                return needs_input(
                    version, ("Сохранённая версия сметы",), "Сохранённая версия сметы не найдена."
                )
            version = int(slot["version"])
        finally:
            database.close()

    idempotency_key = f"document-pack-{accepted.run_id}"
    database = connect_database(settings.database_url)
    try:
        try:
            issue = issue_document_pack(
                database,
                settings=settings,
                tenant_id=accepted.tenant_id,
                user_id=accepted.user_id
                if hasattr(accepted, "user_id")
                else _run_actor_user_id(database, accepted),
                project_id=accepted.project_id,
                document_id=str(slot["id"]),
                estimate_version=version,
                requested_kinds=requested_kinds,
                mode=mode,  # type: ignore[arg-type]
                idempotency_key=idempotency_key,
            )
        except DocumentPackError as exc:
            required = tuple(exc.required_fields)
            if exc.code in {
                "estimate_needs_input",
                "stale_prices_block_ready",
                "invoice_required_fields",
                "estimate_not_ready",
            }:
                return needs_input(
                    version, required or ("Подтверждённые цены и реквизиты",), exc.message
                )
            return ProductWidget(
                arguments={
                    "$type": "EstimateDocumentPack",
                    "schemaId": "kolibri.estimate-document-pack",
                    "schemaVersion": "1.0",
                    "projectId": accepted.project_id,
                    "estimateVersion": version,
                    "status": "failed",
                    "mode": mode,
                    "rendererVersion": RENDERER_VERSION,
                    "requiredFields": list(required),
                    "files": [],
                },
                fallback_text=exc.message,
                tool_name="create_estimate_document_pack",
                tool_result={
                    "rendered": True,
                    "status": "failed",
                    "code": exc.code,
                    "requiredFields": list(required),
                },
            )
    finally:
        database.close()

    view = issue.view()
    return ProductWidget(
        arguments={"$type": "EstimateDocumentPack", **view, "mode": mode},
        fallback_text=(
            f"Подготовлен {'официальный' if issue.status == 'issued' else 'предварительный'} комплект сметных документов "
            f"№ {issue.document_number}: PDF, DOCX, XLSX и ZIP доступны для скачивания."
        ),
        tool_name="create_estimate_document_pack",
        tool_result={
            "rendered": True,
            "status": issue.status,
            "issueId": issue.issue_id,
            "documentNumber": issue.document_number,
            "estimateVersion": issue.estimate_version,
            "rendererVersion": issue.renderer_version,
            "files": list(issue.files),
        },
    )


def _run_actor_user_id(database: Any, accepted: WidgetRunLike) -> str:
    row = database.execute(
        "SELECT requested_by_user_id FROM chat_runs WHERE tenant_id = ? AND id = ? LIMIT 1",
        (accepted.tenant_id, accepted.run_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("estimate run actor is missing")
    return str(row["requested_by_user_id"])


def materialize_engine_estimate_widget(
    settings: Settings,
    accepted: WidgetRunLike,
    *,
    intake: PlasteringIntake,
    provider_profile: str,
) -> ProductWidget:
    database = connect_database(settings.database_url)
    try:
        _require_estimate_run_entitlement(database, accepted)
        slot = load_estimate_slot(
            database,
            tenant_id=accepted.tenant_id,
            project_id=accepted.project_id,
        )
        actor = database.execute(
            """
            SELECT runs.requested_by_user_id, runs.input_message_id,
                   users.role, users.preferred_agent_profile,
                   users.email, users.name
            FROM chat_runs AS runs
            JOIN users
              ON users.id = runs.requested_by_user_id
             AND users.tenant_id = runs.tenant_id
            WHERE runs.tenant_id = ? AND runs.id = ?
            LIMIT 1
            """,
            (accepted.tenant_id, accepted.run_id),
        ).fetchone()
        if slot is None or actor is None:
            raise RuntimeError("estimate calculation context is missing")

        scope_value = PlasteringScope(
            wall_area_m2=intake.wall_area_m2,
            average_thickness_mm=intake.average_thickness_mm,
            material=intake.material,
            application_method=intake.application_method,
            waste_percent=intake.waste_percent,
            protection_area_m2=intake.protection_area_m2,
            wall_height_m=intake.wall_height_m,
            beacon_spacing_m=intake.beacon_spacing_m,
            corner_length_m=intake.corner_length_m,
            mesh_area_percent=intake.mesh_area_percent,
            slopes_area_m2=intake.slopes_area_m2,
            plaster_bag_weight_kg=intake.plaster_bag_weight_kg,
            primer_passes=intake.primer_passes,
            waste_removal_trips=intake.waste_removal_trips,
        )
        preflight = calculate_plastering_estimate(
            project_case=ProjectCaseRef(
                tenant_id=accepted.tenant_id,
                project_id=accepted.project_id,
                case_id="case_preflight",
                version=1,
                region=intake.region,
            ),
            scope=scope_value,
            prices=[],
        )
        active_units = {str(item["code"]): str(item["unit"]) for item in preflight["items"]}
        reference_prices = plastering_reference_price_quotes(
            active_units=active_units,
            region=intake.region,
        )
        candidate_checks = verify_plastering_model_price_candidates(
            {
                item.item_code: item.unit_price
                for item in intake.candidate_prices
                if item.item_code in active_units
            }
        )
        calculation_assumptions = list(intake.assumptions)
        reference_assumption = plastering_reference_price_assumption()
        if reference_assumption not in calculation_assumptions:
            calculation_assumptions.append(reference_assumption)
        try:
            payload = PlasteringCalculationInput.model_validate(
                {
                    "expectedEstimateVersion": int(slot["version"]),
                    "region": intake.region,
                    "title": intake.title,
                    "assumptions": calculation_assumptions,
                    "scope": {
                        "wallAreaM2": intake.wall_area_m2,
                        "averageThicknessMm": intake.average_thickness_mm,
                        "material": intake.material,
                        "applicationMethod": intake.application_method,
                        "wastePercent": intake.waste_percent,
                        "protectionAreaM2": intake.protection_area_m2,
                        "wallHeightM": intake.wall_height_m,
                        "beaconSpacingM": intake.beacon_spacing_m,
                        "cornerLengthM": intake.corner_length_m,
                        "meshAreaPercent": intake.mesh_area_percent,
                        "slopesAreaM2": intake.slopes_area_m2,
                        "plasterBagWeightKg": intake.plaster_bag_weight_kg,
                        "primerPasses": intake.primer_passes,
                        "wasteRemovalTrips": intake.waste_removal_trips,
                    },
                    "prices": reference_prices,
                    "terms": {
                        "overheadPercent": "0",
                        "profitPercent": "0",
                        "discountPercent": "0",
                        "taxPercent": "0",
                    },
                    "sourceMessageId": str(actor["input_message_id"]),
                    "sourceRunId": accepted.run_id,
                    "requireReleaseReady": False,
                }
            )
            response = calculate_plastering(
                accepted.project_id,
                payload,
                database,
                UserSession(
                    user_id=str(actor["requested_by_user_id"]),
                    tenant_id=accepted.tenant_id,
                    role=UserRole(str(actor["role"])),
                    preferred_agent_profile=AgentProfile(str(actor["preferred_agent_profile"])),
                    email=str(actor["email"]),
                    name=str(actor["name"]),
                ),
                None,
                f"estimate-chat-{accepted.run_id}",
            )
        except (HTTPException, ValidationError, ValueError) as exc:
            raise RuntimeError("estimate engine persistence failed") from exc
    finally:
        database.close()

    view = response["estimate"]
    validation = response["result"]["validation"]
    return ProductWidget(
        arguments={"$type": "EstimateEditor", **view},
        fallback_text=(
            f"Подготовлены технологическая карта и смета «{view['estimateTitle']}»: "
            f"{len(view['rows'])} позиций на {view['totals']['total']} ₽. "
            + (
                "Ценовые кандидаты требуют независимой проверки перед выпуском."
                if validation["status"] == "blocked"
                else "Цены и расчёт прошли проверку."
            )
        ),
        tool_result={
            "rendered": True,
            "schemaVersion": "1.0",
            "calculationId": response["calculationId"],
            "engineVersion": response["result"]["engineVersion"],
            "rulesVersion": response["result"]["rulesVersion"],
            "priceSnapshotVersion": (PLASTERING_REFERENCE_PRICE_SNAPSHOT_VERSION),
            "candidatePriceCount": len(candidate_checks),
            "candidateWithinRangeCount": sum(
                check["verdict"] == "within_reference_range" for check in candidate_checks
            ),
            "candidateOutlierCount": sum(
                check["verdict"] == "outlier" for check in candidate_checks
            ),
            "candidatePriceChecks": candidate_checks,
            "resultHash": response["result"]["resultHash"],
            "estimateVersion": response["estimateVersion"],
            "technologyStageCount": len(response["result"]["technologyCard"]["stages"]),
            "validationStatus": validation["status"],
            "unverifiedPriceCount": len(validation.get("unverifiedPriceItemCodes", [])),
            "missingPriceCount": len(validation.get("missingPriceItemCodes", [])),
        },
    )


def try_prepare_product_widget(
    settings: Settings,
    accepted: WidgetRunLike,
    *,
    prompt: str,
) -> ProductWidget | None:
    if is_estimate_prompt(prompt):
        return _estimate_widget(settings, accepted)
    return None
