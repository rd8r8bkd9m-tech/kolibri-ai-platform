from __future__ import annotations

import re
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
ESTIMATE_GENERATION_WORDS = re.compile(
    r"\b(?:состав\w*|подготов\w*|собер\w*|рассчит\w*|сдела\w*|"
    r"созда\w*|сформир\w*|постро\w*|оцен\w*)\b",
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
TECHNOLOGY_CARD_WORDS = re.compile(
    r"\b(?:тех(?:нологическ\w*)?\s*карт\w*)\b",
    re.IGNORECASE)


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
    return ESTIMATE_WORDS.search(prompt) is not None


def _plain_decimal(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def is_estimate_generation_prompt(prompt: str) -> bool:
    return is_estimate_prompt(prompt) and (
        ESTIMATE_GENERATION_WORDS.search(prompt) is not None
        or TECHNOLOGY_CARD_WORDS.search(prompt) is not None
        or (
            ESTIMATE_SCOPE_QUANTITY.search(prompt) is not None
            and ESTIMATE_SCOPE_WORDS.search(prompt) is not None
        )
    )


def has_estimate_scope_input(prompt: str) -> bool:
    """Return whether a request contains inputs for a new calculation."""

    return (
        TECHNOLOGY_CARD_WORDS.search(prompt) is not None
        or (
            ESTIMATE_SCOPE_QUANTITY.search(prompt) is not None
            and ESTIMATE_SCOPE_WORDS.search(prompt) is not None
        )
    )


def is_estimate_revision_prompt(prompt: str) -> bool:
    """Return whether a message intends to mutate the saved estimate."""

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
    current_area_match = ESTIMATE_AREA_CHANGE.search(
        str(current.get("title") or "")
    )
    new_area = (
        Decimal(area_match.group(1).replace(",", "."))
        if area_match is not None
        else None
    )
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
            and (
                "кров" in description.casefold()
                or "стропил" in description.casefold()
            )
            and "утепл" not in description.casefold()
            and description != "Стропильная система и мягкая кровля"
        ):
            new_description = "Стропильная система и мягкая кровля"
            new_price_basis = (
                "Ставка сохранена из предыдущей версии сметы; "
                "источник цены на мягкую кровлю требует подтверждения."
            )
        quantity = str(item.get("quantity") or "0")
        quantity_basis = str(
            item.get("quantity_basis") or "Предыдущая версия сметы"
        )
        unit = str(item.get("unit") or "компл.")
        if (
            new_area is not None
            and current_area is not None
            and new_area > 0
            and new_area != current_area
            and unit.casefold() in {"м²", "м³", "м2", "м3", "кг"}
            and "каноническ" in quantity_basis.casefold()
        ):
            scaled = (
                Decimal(quantity) * new_area / current_area
            ).quantize(Decimal("0.01"))
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
        area_for_landscape = (
            current_area if current_area is not None else None
        )
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
        raw_description = (
            (add_match.group(1) or add_match.group(2) or "").strip(" .,:;")
        )
        if raw_description:
            quantity_match = ESTIMATE_EXPLICIT_QUANTITY.search(raw_description)
            price_match = ESTIMATE_EXPLICIT_PRICE.search(raw_description)
            quantity = (
                quantity_match.group(1).replace(",", ".")
                if quantity_match is not None
                else "1"
            )
            unit = (
                quantity_match.group(2).replace("м2", "м²").replace("м3", "м³")
                if quantity_match is not None
                else "компл."
            )
            unit_price = (
                price_match.group(1)
                .replace(" ", "")
                .replace("\u00a0", "")
                .replace(",", ".")
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

    assumptions = [
        str(item)
        for item in current.get("assumptions", [])
        if isinstance(item, str)
    ]
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
    if (
        new_area is not None
        and current_area is not None
        and new_area != current_area
    ):
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
    }.get(region, region)

    def qty(value: Decimal) -> str:
        return format(value.quantize(Decimal("0.01")), "f").rstrip("0").rstrip(".")

    def row(section: str, kind: str, description: str, unit: str, quantity: Decimal, unit_price: str) -> dict[str, str]:
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
        row("Земляные работы", "work", "Разработка грунта под фундамент", "м³", area * Decimal("0.18"), "1800.00"),
        row("Фундамент", "material", "Фундамент монолитный с материалами", "м³", area * Decimal("0.16"), "12500.00"),
        row("Фундамент", "material", "Армирование фундамента", "кг", area * Decimal(18), "190.00"),
        row("Коробка", "material", "Стены наружные с кладкой и материалами", "м²", area * Decimal("1.8"), "8500.00"),
        row("Кровля", "work", "Стропильная система и кровельное покрытие", "м²", area * Decimal("1.35"), "2450.00"),
        row("Кровля", "material", "Утепление кровли", "м²", area * Decimal("1.35"), "1250.00"),
        row("Проёмы", "material", "Окна ПВХ", "шт", Decimal(4), "35000.00"),
        row("Проёмы", "material", "Входная дверь", "шт", Decimal(1), "45000.00"),
        row("Инженерные сети", "service", "Электромонтажные работы и материалы", "м²", area, "2800.00"),
        row("Инженерные сети", "service", "Сантехнический комплект", "компл.", Decimal(1), "95000.00"),
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
        )
    finally:
        database.close()
    return ProductWidget(
        arguments={"$type": "EstimateEditor", **view},
        fallback_text=(
            f"Открыта редактируемая смета «{view['estimateTitle']}», "
            f"версия {view['version']}."
        ),
    )


def materialize_generated_estimate_widget(
    settings: Settings,
    accepted: WidgetRunLike,
    *,
    proposal: GeneratedEstimateProposal,
    provider_profile: str,
    replace_existing: bool = False,
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
            if current["rows"] and not replace_existing:
                view = estimate_view(
                    project_id=accepted.project_id,
                    document_id=str(slot["id"]),
                    version=int(slot["version"]),
                    status=str(slot["status"]),
                    document=current,
                )
            else:
                now = str(
                    database.execute(
                        "SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
                    ).fetchone()[0]
                )
                document = estimate_document_from_proposal(
                    proposal,
                    now=now,
                    provider_profile=provider_profile,
                    run_id=accepted.run_id,
                )
                estimate_version = int(slot["version"]) + (1 if current["rows"] else 0)
                database.execute(
                    """
                    UPDATE document_slots
                    SET version = ?, status = 'draft', content_json = ?, updated_at = ?
                    WHERE tenant_id = ? AND id = ? AND version = ?
                    """,
                    (
                        estimate_version,
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
                    status="draft",
                    document=document,
                    origin_type="ai_proposal",
                    origin_run_id=accepted.run_id,
                    created_by_user_id=actor_user_id,
                    created_at=now,
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
                view = estimate_view(
                    project_id=accepted.project_id,
                    document_id=str(slot["id"]),
                    version=estimate_version,
                    status="draft",
                    document=document,
                )
    finally:
        database.close()

    return ProductWidget(
        arguments={"$type": "EstimateEditor", **view},
        fallback_text=(
            f"Подготовлена предварительная смета «{view['estimateTitle']}»: "
            f"{len(view['rows'])} позиций на {view['totals']['total']} ₽. "
            "Количество и цены с пометкой «допущение» требуют проверки."
        ),
    )


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
        active_units = {
            str(item["code"]): str(item["unit"])
            for item in preflight["items"]
        }
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
                    preferred_agent_profile=AgentProfile(
                        str(actor["preferred_agent_profile"])
                    ),
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
            "priceSnapshotVersion": (
                PLASTERING_REFERENCE_PRICE_SNAPSHOT_VERSION
            ),
            "candidatePriceCount": len(candidate_checks),
            "candidateWithinRangeCount": sum(
                check["verdict"] == "within_reference_range"
                for check in candidate_checks
            ),
            "candidateOutlierCount": sum(
                check["verdict"] == "outlier"
                for check in candidate_checks
            ),
            "candidatePriceChecks": candidate_checks,
            "resultHash": response["result"]["resultHash"],
            "estimateVersion": response["estimateVersion"],
            "technologyStageCount": len(
                response["result"]["technologyCard"]["stages"]
            ),
            "validationStatus": validation["status"],
            "unverifiedPriceCount": len(
                validation.get("unverifiedPriceItemCodes", [])
            ),
            "missingPriceCount": len(
                validation.get("missingPriceItemCodes", [])
            ),
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
