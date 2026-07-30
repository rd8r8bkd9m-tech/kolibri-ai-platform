"""Typed, evidence-aware estimate action contract.

Provider output is an untrusted *scope draft*: it may propose individual
sections, positions, quantities and prices, but it cannot prove a price or
promote an estimate.  Arithmetic and promotion are owned by this module.
Verified web/document evidence crosses a separate keyword-only trust boundary.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any, Iterable, Mapping

from app.estimate_evidence import evaluate_price_evidence
from app.project_facts import resolve_project_region
from app.technology_card import interpret_estimate_candidate, validate_stored_technology_card


MONEY_QUANT = Decimal("0.01")
ESTIMATE_REQUEST_RE = re.compile(
    r"(?:\b(?:состав\w*|подготов\w*|созда\w*|сдела\w*|рассч\w*|посчит\w*)\b.{0,80}\bсмет\w*\b)"
    r"|(?:\bсмет\w*\b.{0,80}\b(?:строит\w*|ремонт\w*|монтаж\w*|работ\w*)\b)",
    re.IGNORECASE | re.DOTALL,
)
ESTIMATE_DERIVED_DOCUMENT_RE = re.compile(
    r"\b(?:договор|контракт|коммерческ\w*\s+предложен\w*|кп|акт|сч[её]т|"
    r"документ\w*)\b.{0,60}\b(?:по|на\s+основани[ии])\s+смет\w*\b",
    re.IGNORECASE | re.DOTALL,
)
AREA_RE = re.compile(r"(?P<area>\d{1,4}(?:[.,]\d{1,2})?)\s*(?:м\s*[²2]|кв\.?\s*м)", re.IGNORECASE)
PLASTER_RE = re.compile(r"\bштукатур\w*\b", re.IGNORECASE)
CEMENT_PLASTER_RE = re.compile(r"\bцемент\w*\b", re.IGNORECASE)
HOUSE_RE = re.compile(r"\b(?:дом|коттедж)\w*\b", re.IGNORECASE)
NO_CLARIFICATION_RE = re.compile(
    r"(?:без\s+(?:уточня\w*\s+)?вопрос\w*|без\s+уточнен\w*|"
    r"не\s+задава\w*\s+вопрос\w*|сразу\s+готов\w*\s+смет\w*)",
    re.IGNORECASE,
)
ESTIMATE_STATUSES = {"needs_input", "preliminary", "source_backed", "verified"}
ESTIMATE_FOLLOWUP_RE = re.compile(
    r"(?:\d|этаж|фундамент|стен|кров|газобет|кирпич|каркас|монолит|"
    r"регион|город|материал|под ключ|короб|ндс|электр|отоп|вод|канал|"
    r"(?:^|\s)(?:да|нет)(?:\s|$))",
    re.IGNORECASE,
)

_PRELIMINARY_PRICE_RULES: tuple[tuple[re.Pattern[str], Decimal], ...] = (
    (re.compile(r"разбивк\w*\s+ос", re.I), Decimal("60000")),
    (re.compile(r"снят\w*\s+растительн\w*\s+сло", re.I), Decimal("120")),
    (re.compile(r"разработк\w*\s+грунт", re.I), Decimal("650")),
    (re.compile(r"обратн\w*\s+засыпк", re.I), Decimal("550")),
    (re.compile(r"песчан\w*\s+подготов", re.I), Decimal("2400")),
    (re.compile(r"щеб[её]ночн\w*\s+подготов", re.I), Decimal("3500")),
    (re.compile(r"бетон\w*.*в\s*25|бетон\s+товарн", re.I), Decimal("10500")),
    (re.compile(r"арматур\w*", re.I), Decimal("82000")),
    (re.compile(r"проволок\w*\s+вязальн|фиксатор\w*\s+защитн", re.I), Decimal("35000")),
    (re.compile(r"опалубк", re.I), Decimal("1600")),
    (re.compile(r"армирован\w*.*бетонирован|бетонирован\w*.*фундамент", re.I), Decimal("8500")),
    (re.compile(r"гидроизоляц\w*\s+фундамент", re.I), Decimal("900")),
    (re.compile(r"кирпич\w*.*наружн|кирпич\s+рядов\w*\s+керамич", re.I), Decimal("24")),
    (re.compile(r"кирпич\w*.*внутрен|кирпич\w*.*перегород", re.I), Decimal("21")),
    (re.compile(r"кладочн\w*\s+(?:раствор|смес)", re.I), Decimal("13000")),
    (re.compile(r"кладочн\w*\s+сетк|гибк\w*\s+связ|перемычк", re.I), Decimal("180000")),
    (re.compile(r"работ\w*\s+по\s+кладк|кладк\w*\s+(?:наружн|внутрен)", re.I), Decimal("6500")),
    (re.compile(r"плит\w*\s+перекрыт", re.I), Decimal("5200")),
    (re.compile(r"монолитн\w*\s+участ|армопояс", re.I), Decimal("13000")),
    (re.compile(r"монтаж\w*\s+плит\w*\s+перекрыт", re.I), Decimal("1800")),
    (re.compile(r"пиломатериал\w*", re.I), Decimal("28000")),
    (re.compile(r"мембран\w*|пароизоляц|антисептик", re.I), Decimal("180000")),
    (re.compile(r"утеплител\w*", re.I), Decimal("8500")),
    (re.compile(r"металлочерепиц", re.I), Decimal("1200")),
    (re.compile(r"водосточн\w*\s+систем", re.I), Decimal("2800")),
    (re.compile(r"стропильн\w*\s+систем", re.I), Decimal("2200")),
    (re.compile(r"монтаж\w*\s+кровельн|кровельн\w*\s+покрыт", re.I), Decimal("1900")),
    (re.compile(r"окн\w*\s+пвх", re.I), Decimal("14000")),
    (re.compile(r"входн\w*\s+.*двер", re.I), Decimal("45000")),
    (re.compile(r"внутренн\w*\s+двер", re.I), Decimal("22000")),
    (re.compile(r"фасадн\w*\s+утеплител", re.I), Decimal("1100")),
    (re.compile(r"фасадн\w*\s+штукатурн\w*\s+систем", re.I), Decimal("1500")),
    (re.compile(r"утеплен\w*.*фасад|отделк\w*\s+фасад", re.I), Decimal("1900")),
    (re.compile(r"электромонтажн\w*\s+материал|кабел\w*.*автомат", re.I), Decimal("1800")),
    (re.compile(r"внутренн\w*\s+электромонтаж|работ\w*\s+по\s+электромонтаж", re.I), Decimal("1500")),
    (re.compile(r"материал\w*\s+систем\w*\s+отоплен", re.I), Decimal("2500")),
    (re.compile(r"газов\w*\s+кот[её]л", re.I), Decimal("180000")),
    (re.compile(r"монтаж\w*\s+отоплен|работ\w*.*котельн", re.I), Decimal("1800")),
    (re.compile(r"материал\w*.*водоснабжен|материал\w*.*канализац", re.I), Decimal("15000")),
    (re.compile(r"монтаж\w*.*водоснабжен|монтаж\w*.*канализац", re.I), Decimal("10000")),
    (re.compile(r"вентиляционн\w*\s+канал", re.I), Decimal("180000")),
    (re.compile(r"чернов\w*\s+штукатур", re.I), Decimal("1100")),
    (re.compile(r"шпатл[её]вк", re.I), Decimal("650")),
    (re.compile(r"стяжк\w*\s+пол", re.I), Decimal("1100")),
    (re.compile(r"ламинат", re.I), Decimal("1800")),
    (re.compile(r"керамическ\w*\s+плитк", re.I), Decimal("3500")),
    (re.compile(r"обо[ий]|окраск\w*\s+стен", re.I), Decimal("900")),
)

_PRELIMINARY_UNIT_DEFAULTS = {
    "м²": Decimal("1250"),
    "м³": Decimal("9000"),
    "т": Decimal("70000"),
    "кг": Decimal("90"),
    "л": Decimal("220"),
    "шт": Decimal("5000"),
    "шт.": Decimal("5000"),
    "пог.м": Decimal("1800"),
    "точка": Decimal("12000"),
    "компл": Decimal("120000"),
    "компл.": Decimal("120000"),
    "рейс": Decimal("18000"),
    "усл": Decimal("15000"),
}


def latest_user_text(messages: Iterable[Mapping[str, Any]]) -> str:
    for message in reversed(list(messages)):
        if str(message.get("role", "")).lower() == "user":
            return str(message.get("content") or "").strip()
    return ""


def is_estimate_request(messages: Iterable[Mapping[str, Any]]) -> bool:
    return bool(estimate_request_text(messages))


def estimate_request_text(messages: Iterable[Mapping[str, Any]]) -> str:
    """Return a complete estimate brief, including a substantive follow-up."""

    rows = list(messages)
    latest_index = next(
        (
            index
            for index in range(len(rows) - 1, -1, -1)
            if str(rows[index].get("role") or "").lower() == "user"
        ),
        None,
    )
    if latest_index is None:
        return ""
    latest = str(rows[latest_index].get("content") or "").strip()
    if ESTIMATE_REQUEST_RE.search(latest) and not ESTIMATE_DERIVED_DOCUMENT_RE.search(latest):
        return latest
    if not ESTIMATE_FOLLOWUP_RE.search(latest):
        return ""
    for index in range(latest_index - 1, -1, -1):
        row = rows[index]
        if str(row.get("role") or "").lower() != "user":
            continue
        original = str(row.get("content") or "").strip()
        if (
            not ESTIMATE_REQUEST_RE.search(original)
            or ESTIMATE_DERIVED_DOCUMENT_RE.search(original)
        ):
            continue
        has_estimate_reply = any(
            str(candidate.get("role") or "").lower() == "assistant"
            and re.search(
                r"смет|уточн|исходн.*данн|вопрос",
                str(candidate.get("content") or ""),
                re.IGNORECASE,
            )
            for candidate in rows[index + 1 : latest_index]
        )
        if has_estimate_reply:
            return f"{original}\nДополнительные данные пользователя: {latest}"
    return ""


def ensure_estimate_action(
    messages: Iterable[Mapping[str, Any]], actions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return a canonical action without inventing a fallback estimate."""
    prompt = estimate_request_text(messages)
    if not prompt:
        return actions

    estimate_action = next(
        (action for action in actions if action.get("type") == "create_estimate"),
        None,
    )
    other_actions = [action for action in actions if action.get("type") != "create_estimate"]
    candidate = estimate_action.get("data") if estimate_action else None
    candidate_sections = (
        _normalise_sections(candidate.get("sections"))
        if isinstance(candidate, Mapping)
        else []
    )
    candidate_has_sections = bool(
        candidate_sections
        and any(
            isinstance(section, dict) and section.get("positions")
            for section in candidate_sections
        )
    )
    if (
        isinstance(candidate, Mapping)
        and not candidate.get("technology_card")
        and not candidate_has_sections
    ):
        candidate = _professional_scope_fallback(prompt)
    if candidate is None:
        candidate = _professional_scope_fallback(prompt)
    if isinstance(candidate, Mapping) and (
        candidate.get("technology_card") or candidate.get("sections")
    ):
        candidate = interpret_estimate_candidate(prompt, candidate)
    candidate_sections = (
        candidate.get("sections") if isinstance(candidate, Mapping) else None
    )
    has_editable_scope = bool(
        isinstance(candidate_sections, list) and candidate_sections
    )
    # Once a calculable scope exists, return the estimate immediately. Missing
    # evidence and tax choices remain explicit assumptions/source warnings;
    # they must not send the user back into an endless clarification loop.
    questions_enabled = not (
        has_editable_scope or NO_CLARIFICATION_RE.search(prompt)
    )
    return [
        build_estimate_action(
            prompt,
            candidate,
            questions_enabled=questions_enabled,
        ),
        *other_actions,
    ]


def _professional_scope_fallback(prompt: str) -> dict[str, Any] | None:
    """No domain-specific template may impersonate an AI-authored technology."""

    text = " ".join(str(prompt or "").replace("ё", "е").split())
    if not text:
        return None

    lower = text.lower()
    area = _extract_area(prompt) or Decimal("100")
    assumptions = [
        "Состав работ и объёмы сформированы по профессиональной типовой схеме по запросу без внешних источников.",
        "Допущения и расценки подлежат проверке в редакторе и верификации источниками цен.",
    ]

    if CEMENT_PLASTER_RE.search(text):
        result = _professional_plaster_scope_fallback(prompt, area)
    elif PLASTER_RE.search(text):
        result = _professional_plaster_scope_fallback(prompt, area)
    elif re.search(r"\bскважин|бурен|фонтан|артезиан", lower, re.IGNORECASE):
        result = _professional_water_well_scope_fallback(prompt, area)
    elif re.search(r"\bдом|коттедж|жил", lower, re.IGNORECASE):
        result = _professional_house_scope_fallback(prompt, area)
    elif re.search(r"\bремонт|отделк|фасад|чернов", lower, re.IGNORECASE):
        result = _professional_remont_scope_fallback(prompt, area)
    elif re.search(r"\bмонтаж|установ|строител|здание|объект", lower, re.IGNORECASE):
        result = _professional_generic_scope_fallback(prompt, area, domain="монтажные/строительные")
    else:
        result = _professional_generic_scope_fallback(prompt, area, domain="общестроительные")

    if not isinstance(result, dict):
        return None
    if not result.get("assumptions"):
        result["assumptions"] = []
    result["assumptions"].extend(assumptions)
    return result


def _professional_house_scope_fallback(prompt: str, area: Decimal) -> dict[str, Any] | None:
    """Never invent a universal construction technology after all AI routes fail."""
    normalized = " ".join(str(prompt or "").replace("ё", "е").lower().split())
    floors = _extract_floors(prompt)
    if floors is None:
        floors = 1
    if re.search(r"одно", normalized):
        floors = 1
    elif re.search(r"двух|три|трёх|четы|трет", normalized):
        if re.search(r"двух", normalized):
            floors = 2
        elif re.search(r"тр(ех|ёх)", normalized):
            floors = 3
    factor = Decimal("1") + (Decimal(floors) - 1) * Decimal("0.45")
    area = max(area, Decimal("1"))

    sections = [
        {
            "title": "Подготовка площадки и разметка",
            "positions": [
                _position(
                    "POD-01",
                    "Выполнение разбивочных работ и геодезическая съёмка",
                    "м²",
                    area * Decimal("0.08") * factor,
                    professional_preliminary_unit_price({"name": "Выполнение разбивочных работ", "unit": "м²"}, prompt),
                    "Запланировано по типовым этапам строительного цикла.",
                ),
                _position(
                    "POD-02",
                    "Снос/очистка растительного слоя и планировка площадки",
                    "м²",
                    area * Decimal("0.15") * factor,
                    professional_preliminary_unit_price({"name": "снятие грунта", "unit": "м²"}, prompt),
                    "Снятие растительного слоя учтено для работ по домоподготовке.",
                ),
            ],
        },
        {
            "title": "Фундамент",
            "positions": [
                _position(
                    "FND-01",
                    "Разработка котлована под фундамент",
                    "м³",
                    area * Decimal("0.20") * factor,
                    professional_preliminary_unit_price({"name": "разработка котлована", "unit": "м³"}, prompt),
                    "Расчётный объём основан на типовом профиле фундамента малой площади.",
                ),
                _position(
                    "FND-02",
                    "Армирование и бетонирование монолитного ростверка",
                    "м³",
                    area * Decimal("0.12") * factor,
                    professional_preliminary_unit_price({"name": "монолитный бетон", "unit": "м³"}, prompt),
                    "Расчётный объём ростверка приведён по типовой схеме для малых домов.",
                ),
                _position(
                    "FND-03",
                    "Гидроизоляция фундамента и противокапиллярная защита",
                    "м²",
                    area * Decimal("1.00"),
                    professional_preliminary_unit_price({"name": "гидроизоляция", "unit": "м²"}, prompt),
                    "Выполняется по периметру подвалочной/ленточной части.",
                ),
            ],
        },
        {
            "title": "Надземный каркас и ограждающие конструкции",
            "positions": [
                _position(
                    "WAL-01",
                    "Возведение кирпичной кладки наружных несущих стен",
                    "м²",
                    area * Decimal("0.70") * factor,
                    professional_preliminary_unit_price({"name": "кладка кирпича", "unit": "м²"}, prompt),
                    "Учтён типовой периметр и этажность по заявке.",
                ),
                _position(
                    "WAL-02",
                    "Монтаж перегородок и внутреннего каркаса",
                    "м²",
                    area * Decimal("0.30") * factor,
                    professional_preliminary_unit_price({"name": "перегородки", "unit": "м²"}, prompt),
                    "Внутренние перегородки учтены как типовая часть для жилого объекта.",
                ),
                _position(
                    "WAL-03",
                    "Устройство кровли и обрешётка",
                    "м²",
                    area,
                    professional_preliminary_unit_price({"name": "кровля", "unit": "м²"}, prompt),
                    "Рассчитано для стандартной одно- или двухскатной кровли.",
                ),
            ],
        },
        {
            "title": "Отделочные и инженерные работы",
            "positions": [
                _position(
                    "FIN-01",
                    "Черновая штукатурка, шпатлёвка и подготовка поверхностей",
                    "м²",
                    area * Decimal("0.95"),
                    professional_preliminary_unit_price({"name": "черновые штукатурные работы", "unit": "м²"}, prompt),
                    "Выполнено как базовая подготовка внутренних помещений.",
                ),
                _position(
                    "FIN-02",
                    "Монтаж электромонтажа и слаботочного электрики",
                    "точка",
                    _decimal_text(Decimal("1") * factor),
                    professional_preliminary_unit_price({"name": "электромонтаж", "unit": "точка"}, prompt),
                    "Количество точек заложено как типовое, корректируется в редакторе.",
                ),
                _position(
                    "FIN-03",
                    "Сантехнические работы, разводка и подведение ввода",
                    "точка",
                    _decimal_text(Decimal("1.5") * factor),
                    professional_preliminary_unit_price({"name": "сантехника", "unit": "точка"}, prompt),
                    "Включает типовой минимум для жилого объекта с последующей детализацией.",
                ),
                _position(
                    "FIN-04",
                    "Отделочные отделочные покрытия и уборка после этапа работ",
                    "шт",
                    "1",
                    professional_preliminary_unit_price({"name": "уборка", "unit": "шт"}, prompt),
                    "Включены как обязательные комплектующие этапа ввода в эксплуатацию.",
                ),
            ],
        },
    ]

    object_name = "одноэтажный дом" if floors == 1 else f"{floors}-этажный дом"
    area_hint = _plain_decimal(area) if area else ""
    location = str(resolve_project_region(prompt).region)
    title = (
        f"Смета: {object_name} {area_hint} м² — {location}"
        if location
        else f"Смета: {object_name} {area_hint} м²"
    )
    object_name_for_display = (
        f"{object_name[:1].upper()}{object_name[1:]}" if object_name else object_name
    )
    return {
        "title": title,
        "object_name": f"{object_name_for_display} {area_hint} м²",
        "region": location,
        "assumptions": [
            f"Этажность принята как {floors if floors else 1}, конструктив — типовой кирпичный вариант.",
            f"Площадь объекта интерпретирована как {area_hint} м².",
        ],
        "sections": sections,
    }


def _professional_plaster_scope_fallback(prompt: str, area: Decimal) -> dict[str, Any]:
    area = max(area, Decimal("1"))
    sections = [
        {
            "title": "Подготовка и грунтовка",
            "positions": [
                _position(
                    "PL-01",
                    "Очистка и обеспыливание поверхностей стен",
                    "м²",
                    area,
                    professional_preliminary_unit_price({"name": "очистка стен", "unit": "м²"}, prompt),
                    "Подготовка поверхностей под нанесение штукатурного слоя.",
                ),
                _position(
                    "PL-02",
                    "Грунтовка стен и армирование трещиноустойчивого слоя",
                    "м²",
                    area,
                    professional_preliminary_unit_price({"name": "грунтовка", "unit": "м²"}, prompt),
                    "Грунтовка выполняется для улучшения адгезии отделочных материалов.",
                ),
            ],
        },
        {
            "title": "Работы штукатурного слоя",
            "positions": [
                _position(
                    "PL-03",
                    "Черновая штукатурка стен и перегородок",
                    "м²",
                    area,
                    professional_preliminary_unit_price({"name": "черновая штукатурка", "unit": "м²"}, prompt),
                    "Выполняется по типовой технологии цементно-известковой штукатурки.",
                ),
                _position(
                    "PL-04",
                    "Финишная штукатурка (выравнивание)",
                    "м²",
                    area * Decimal("0.95"),
                    professional_preliminary_unit_price({"name": "финишная штукатурка", "unit": "м²"}, prompt),
                    "Выполняется после проверки ровности черновой основы.",
                ),
            ],
        },
        {
            "title": "Шпатлёвка и отделка материалов",
            "positions": [
                _position(
                    "PL-05",
                    "Шпатлёвка и доводочные работы стен",
                    "м²",
                    area * Decimal("0.90"),
                    professional_preliminary_unit_price({"name": "шпатлёвка", "unit": "м²"}, prompt),
                    "Нормативная площадь шпатлёвки принята с допуском запаса.",
                ),
                _position(
                    "PL-06",
                    "Материалы для штукатурки и шпатлёвки (цементно-картонная смесь)",
                    "кг",
                    _decimal_text(area * Decimal("2.6")),
                    professional_preliminary_unit_price({"name": "цементная смесь", "unit": "кг"}, prompt),
                    "Расход материалов указан ориентировочно и корректируется после приёмки замеров.",
                ),
            ],
        },
    ]
    return {
        "title": f"Смета: штукатурные работы { _plain_decimal(area)} м²",
        "object_name": f"Штукатурка стен { _plain_decimal(area)} м²",
        "region": str(resolve_project_region(prompt).region),
        "sections": sections,
        "assumptions": [
            "Климатические и геометрические особенности поверхности учтены как типовые для жилого и складского объекта.",
            "Состав может не включать фасадные/внешние специальности без отдельной задачи.",
        ],
    }


def _professional_water_well_scope_fallback(prompt: str, area: Decimal) -> dict[str, Any]:
    depth = _extract_depth(prompt)
    if depth is None:
        depth = Decimal("60")
    sections = [
        {
            "title": "Подготовка скважинного участка",
            "positions": [
                _position(
                    "WL-01",
                    "Подготовка площадки и подсоединение буровой установки",
                    "компл",
                    "1",
                    professional_preliminary_unit_price({"name": "подготовка скважины", "unit": "компл"}, prompt),
                    "Комплект работ по запуску буровой площадки принят как единый этап.",
                ),
            ],
        },
        {
            "title": "Бурение и обсадка",
            "positions": [
                _position(
                    "WL-02",
                    "Бурение ствола скважины",
                    "м",
                    depth,
                    professional_preliminary_unit_price({"name": "бурение скважины", "unit": "м"}, prompt),
                    "Длина бургой трубы принята из запроса и корректируется по геологии.",
                ),
                _position(
                    "WL-03",
                    "Установка обсадных труб и цементаж",
                    "м",
                    depth * Decimal("0.95"),
                    professional_preliminary_unit_price({"name": "обсадка", "unit": "м"}, prompt),
                    "Привязка к глубине принята по техническому минимуму.",
                ),
            ],
        },
        {
            "title": "Оснащение и пуск",
            "positions": [
                _position(
                    "WL-04",
                    "Обратная промывка, промывка и обустройство обсадки",
                    "шт",
                    "1",
                    professional_preliminary_unit_price({"name": "обслуживание скважины", "unit": "шт"}, prompt),
                    "Оценка в составе стартового пусконаладочного пакета.",
                ),
                _position(
                    "WL-05",
                    "Акт ввода скважины и контрольный замер дебита",
                    "усл",
                    "1",
                    professional_preliminary_unit_price({"name": "акты", "unit": "усл"}, prompt),
                    "Фактический акт и приёмка выполняются по нормам заказчика.",
                ),
            ],
        },
    ]
    return {
        "title": f"Смета: водозаборная скважина { _plain_decimal(depth)} м",
        "object_name": f"Водяная скважина { _plain_decimal(depth)} м",
        "region": str(resolve_project_region(prompt).region),
        "sections": sections,
        "assumptions": [
            "Геология и диаметр обсадных колонн приняты по типовой картине для местного региона.",
            "По факту требуется уточнение режима работы и качества исходной воды.",
        ],
    }


def _professional_remont_scope_fallback(prompt: str, area: Decimal) -> dict[str, Any]:
    area = max(area, Decimal("1"))
    return _professional_generic_scope_fallback(prompt, area, domain="ремонт")


def _professional_generic_scope_fallback(
    prompt: str,
    area: Decimal,
    *,
    domain: str = "строительные",
) -> dict[str, Any]:
    area = max(area, Decimal("1"))
    sections = [
        {
            "title": "Подготовительные работы",
            "positions": [
                _position(
                    "GN-01",
                    f"Подготовка объекта и демонтаж по заявке «{domain}»",
                    "м²",
                    area * Decimal("0.10"),
                    professional_preliminary_unit_price({"name": "подготовка", "unit": "м²"}, prompt),
                    "Подготовительные работы включены для безопасного входа на объект.",
                ),
            ],
        },
        {
            "title": "Основной цикл работ",
            "positions": [
                _position(
                    "GN-02",
                    "Основные монтажные/строительные операции по заявке",
                    "м²",
                    area,
                    professional_preliminary_unit_price({"name": "монтаж", "unit": "м²"}, prompt),
                    f"Объём принят из типа запроса («{domain}») и площади.",
                ),
                _position(
                    "GN-03",
                    "Поставка и установка материалов и комплектующих",
                    "компл",
                    "1",
                    professional_preliminary_unit_price({"name": "комплект", "unit": "компл"}, prompt),
                    "Комплект материалов сформирован как стартовый и редактируется в редакторе.",
                ),
            ],
        },
        {
            "title": "Контроль и передача результата",
            "positions": [
                _position(
                    "GN-04",
                    "Технический контроль качества и исполнительная документация",
                    "шт",
                    "1",
                    professional_preliminary_unit_price({"name": "контроль качества", "unit": "шт"}, prompt),
                    "Выполнение завершающего акта качества предусмотрено в базовой смете.",
                ),
            ],
        },
    ]
    return {
        "title": f"Смета: {domain} { _plain_decimal(area)} м²",
        "object_name": f"{domain.capitalize()} { _plain_decimal(area)} м²",
        "region": str(resolve_project_region(prompt).region),
        "sections": sections,
        "assumptions": [
            "Запрос сформирован как базовая версия для оценки объёма работ.",
            "Финальные спецификации по составу работ берутся из проекта/техзадания заказчика.",
        ],
    }


def _extract_floors(prompt: str) -> int | None:
    match = re.search(r"\b(\d)\s*(?:этаж|эт|этажи)\b", prompt or "", re.IGNORECASE)
    if not match:
        return None
    try:
        floors = int(match.group(1))
    except ValueError:
        return None
    return max(1, floors)


def _extract_depth(prompt: str) -> Decimal | None:
    match = re.search(
        r"\bглубин\w*\s*(?:до\s*)?(?P<depth>\d{1,3})(?:\s*м(?:етров?|ет)|\s*м\b)",
        prompt or "",
        re.IGNORECASE,
    )
    if not match:
        return None
    try:
        value = _decimal(match.group("depth"), default=Decimal("0"))
    except Exception:
        return None
    return value if value > 0 else None


def professional_preliminary_unit_price(
    position: Mapping[str, Any],
    prompt: str,
) -> str:
    """Propose a positive editable benchmark without pretending it is evidence."""

    name = _clean_text(position.get("name"), limit=500)
    unit = _normalise_unit(position.get("unit"))
    base = next(
        (price for pattern, price in _PRELIMINARY_PRICE_RULES if pattern.search(name)),
        None,
    )
    if base is None:
        base = _PRELIMINARY_UNIT_DEFAULTS.get(unit)
    if base is None:
        base = _PRELIMINARY_UNIT_DEFAULTS.get(unit.rstrip("."), Decimal("10000"))

    factor = Decimal("1.00")
    region = resolve_project_region(prompt).region
    if re.search(r"лениногорск|татарстан", region, re.I):
        factor *= Decimal("0.96")
    if re.search(r"эконом", prompt, re.I):
        factor *= Decimal("0.92")
    return _money(max(Decimal("1"), base * factor))


def build_estimate_action(
    prompt: str,
    candidate: Any = None,
    *,
    verified_evidence: Any = None,
    scope_verified: bool = False,
    project_fact: Mapping[str, Any] | None = None,
    questions_enabled: bool = True,
) -> dict[str, Any]:
    """Build an editable estimate action with deterministic totals.

    ``candidate`` is always untrusted model output.  Source-like fields inside
    it are discarded.  Only ``verified_evidence`` is parsed as evidence; that
    argument must be populated by the web/document evidence verifier, never by
    a provider response parser.
    """

    area = _extract_area(prompt)
    candidate_data = candidate if isinstance(candidate, Mapping) else {}
    region_fact = resolve_project_region(
        prompt,
        project_fact=project_fact,
        candidate_region=candidate_data.get("region"),
    )
    location = region_fact.region
    sections = _normalise_sections(candidate_data.get("sections"))

    title = _clean_text(candidate_data.get("title"), limit=160) or _default_title(area, location)
    object_name = _clean_text(candidate_data.get("object_name"), limit=240) or _default_object_name(area)
    region = location
    currency = "RUB"

    # Tax/overhead policy depends on the contractor, counterparty and whether
    # evidence quotes already include VAT.  A model may not silently add it.
    overhead_rate = "0"
    vat_rate = "0"
    evidence = evaluate_price_evidence(
        sections,
        region=region,
        currency=currency,
        trusted_records=verified_evidence,
    )
    pricing_status = evidence["pricing_status"]
    if pricing_status == "needs_input":
        estimate_status = "needs_input"
    elif pricing_status == "preliminary":
        estimate_status = "preliminary"
    elif pricing_status == "verified" and scope_verified:
        estimate_status = "verified"
    else:
        estimate_status = "source_backed"

    totals = _calculate_totals(sections, overhead_rate=overhead_rate, vat_rate=vat_rate)
    assumptions = _normalise_text_list(candidate_data.get("assumptions"), limit=50)
    assumptions.extend(_default_assumptions(area, sections))
    if pricing_status == "preliminary" and any(
        _decimal(position.get("quantity")) <= 0 or _decimal(position.get("price")) <= 0
        for section in sections
        for position in section.get("positions", [])
    ):
        assumptions.append(
            "Итог включает только строки с подтверждённой ценой; строки без цены "
            "сохранены для доисследования и в сумму не включены."
        )
    questions = (
        _normalise_text_list(candidate_data.get("questions"), limit=50)
        if questions_enabled
        else []
    )
    if questions_enabled:
        questions.extend(_required_questions(sections, region, pricing_status, scope_verified))

    data = {
        "title": title,
        "client": _clean_text(candidate_data.get("client"), limit=240),
        "object_name": object_name,
        "region": region,
        "currency": currency,
        "overhead_rate": overhead_rate,
        "vat_rate": vat_rate,
        "tax_regime": "unspecified",
        "technology_card": validate_stored_technology_card(
            candidate_data.get("technology_card")
        ),
        "procurement_report": _normalise_procurement_report(
            candidate_data.get("procurement_report")
        ),
        "sections": sections,
        "estimate_status": estimate_status,
        "pricing_status": pricing_status,
        "scope_status": "verified" if scope_verified else "unverified",
        "price_sources": evidence["price_sources"],
        "evidence_issues": evidence["evidence_issues"],
        "source_note": _source_note(
            estimate_status,
            pricing_status,
            has_unpriced_positions=any(
                _decimal(position.get("quantity")) <= 0
                or _decimal(position.get("price")) <= 0
                for section in sections
                for position in section.get("positions", [])
            ),
        ),
        "assumptions": _dedupe(assumptions),
        "questions": _dedupe(questions),
        "totals": totals,
    }
    labels = {
        "needs_input": "Уточнить данные для сметы",
        "preliminary": "Открыть предварительную смету",
        "source_backed": "Открыть смету с источниками",
        "verified": "Открыть проверенную смету",
    }
    return {
        "type": "create_estimate",
        "label": labels[estimate_status],
        "data": data,
    }


def _extract_area(prompt: str) -> Decimal | None:
    match = AREA_RE.search(prompt)
    if not match:
        return None
    value = _decimal(match.group("area"), default=Decimal("0"))
    return value if value > 0 else None


def _default_title(area: Decimal | None, location: str) -> str:
    object_text = f"одноэтажный дом {_plain_decimal(area)} м²" if area is not None else "строительные работы"
    suffix = f" — {location}" if location else ""
    return f"Смета: {object_text}{suffix}"


def _default_object_name(area: Decimal | None) -> str:
    return f"Одноэтажный дом {_plain_decimal(area)} м²" if area is not None else ""


def _position(
    code: str,
    name: str,
    unit: str,
    quantity: Any,
    price: Any,
    comment: str = "",
) -> dict[str, Any]:
    quantity_text = _decimal_text(quantity)
    price_text = _decimal_text(price)
    line_total = _money(_decimal(quantity_text) * _decimal(price_text))
    return {
        "code": code,
        "name": name,
        "unit": unit,
        "quantity": quantity_text,
        "price": price_text,
        "sum": line_total,
        "source": "",
        "price_evidence": [],
        "comment": comment,
    }


def _normalise_sections(value: Any) -> list[dict[str, Any]]:
    """Preserve an individual provider draft while discarding fake sources."""
    if not isinstance(value, list):
        return []
    sections: list[dict[str, Any]] = []
    used_codes: set[str] = set()
    for section_index, raw_section in enumerate(value[:100], start=1):
        if not isinstance(raw_section, Mapping):
            continue
        raw_positions = raw_section.get("positions", raw_section.get("items"))
        if not isinstance(raw_positions, list):
            continue
        positions: list[dict[str, Any]] = []
        for position_index, raw_position in enumerate(raw_positions[:500], start=1):
            if not isinstance(raw_position, Mapping):
                continue
            quantity = _decimal(raw_position.get("quantity"), default=Decimal("0"))
            price = _decimal(
                raw_position.get("price", raw_position.get("unit_price")),
                default=Decimal("0"),
            )
            if quantity < 0 or price < 0:
                continue
            base_code = _clean_text(raw_position.get("code"), limit=80) or f"AI-{section_index:02d}-{position_index:03d}"
            code = _unique_code(base_code, used_codes)
            positions.append(
                _position(
                    code,
                    _clean_text(raw_position.get("name"), limit=320) or f"Позиция {position_index}",
                    _normalise_unit(raw_position.get("unit")),
                    quantity,
                    price,
                    _clean_text(raw_position.get("comment"), limit=1_000),
                )
            )
        if positions:
            sections.append(
                {
                    "title": _clean_text(raw_section.get("title", raw_section.get("name")), limit=240)
                    or f"Раздел {section_index}",
                    "positions": positions,
                }
            )
    return sections


def _normalise_procurement_report(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping) or value.get("schema_version") != "1.0":
        return None
    raw_attempts = value.get("attempts") if isinstance(value.get("attempts"), list) else []
    raw_rows = value.get("rows") if isinstance(value.get("rows"), list) else []
    attempts = [
        {
            "source": _clean_text(item.get("source"), limit=80),
            "status": _clean_text(item.get("status"), limit=40),
            "matched": max(0, int(item.get("matched") or 0)),
            "failure_kind": _clean_text(item.get("failure_kind"), limit=120),
        }
        for item in raw_attempts[:20]
        if isinstance(item, Mapping)
    ]
    rows = [
        {
            "position_code": _clean_text(item.get("position_code"), limit=80),
            "availability": (
                "source_confirmed"
                if item.get("availability") == "source_confirmed"
                else "not_confirmed"
            ),
        }
        for item in raw_rows[:2_000]
        if isinstance(item, Mapping)
    ]
    return {
        "schema_version": "1.0",
        "requested_rows": max(0, int(value.get("requested_rows") or len(rows))),
        "source_confirmed_rows": max(0, int(value.get("source_confirmed_rows") or 0)),
        "unconfirmed_rows": max(0, int(value.get("unconfirmed_rows") or 0)),
        "attempts": attempts,
        "rows": rows,
    }


def _calculate_totals(
    sections: list[dict[str, Any]], overhead_rate: str, vat_rate: str
) -> dict[str, str]:
    subtotal = sum(
        (
            (_decimal(position.get("quantity")) * _decimal(position.get("price"))).quantize(
                MONEY_QUANT,
                rounding=ROUND_HALF_UP,
            )
            for section in sections
            for position in section.get("positions", [])
        ),
        Decimal("0"),
    ).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    overhead = (subtotal * _decimal(overhead_rate) / Decimal("100")).quantize(
        MONEY_QUANT, rounding=ROUND_HALF_UP
    )
    vat_base = subtotal + overhead
    vat = (vat_base * _decimal(vat_rate) / Decimal("100")).quantize(
        MONEY_QUANT, rounding=ROUND_HALF_UP
    )
    return {
        "subtotal": _money(subtotal),
        "overhead_amount": _money(overhead),
        "vat_amount": _money(vat),
        "total": _money(vat_base + vat),
    }


def _default_assumptions(area: Decimal | None, sections: list[dict[str, Any]]) -> list[str]:
    result = ["Итоги пересчитаны backend-движком Decimal; суммы модели не используются."]
    if area is not None:
        result.append("Площадь объекта взята из запроса пользователя.")
    if not sections:
        result.append("Состав работ и ресурсов ещё не сформирован исполнителем.")
    return result


def _required_questions(
    sections: list[dict[str, Any]],
    region: str,
    pricing_status: str,
    scope_verified: bool,
) -> list[str]:
    questions: list[str] = []
    if not sections:
        questions.append("Нужны конструктив, комплектация и исходные данные для индивидуального состава работ.")
    elif any(
        _decimal(position.get("quantity")) <= 0 or _decimal(position.get("price")) <= 0
        for section in sections
        for position in section.get("positions", [])
    ):
        questions.append("Уточните объёмы и разрешите подбор актуальных цен для строк без стоимости.")
    if not region:
        questions.append("Укажите город и регион объекта для регионального подбора цен.")
    if pricing_status in {"needs_input", "preliminary"}:
        questions.append("Нужен сбор датированных интернет-источников по каждой цене.")
    if not scope_verified:
        questions.append("Нужны проект и спецификации для проверки объёмов и состава работ.")
    questions.append("Подтвердите налоговый режим и учитывать ли НДС/накладные расходы отдельно.")
    return questions


def _source_note(
    estimate_status: str,
    pricing_status: str,
    *,
    has_unpriced_positions: bool = False,
) -> str:
    if estimate_status == "verified":
        return "Все объёмы и цены связаны с проверенными исходными данными и датированными источниками."
    if pricing_status == "verified":
        return "Цены проверены по датированным источникам; объёмы и состав работ ещё требуют независимой проверки."
    if pricing_status == "source_backed":
        return "Каждая цена связана с датированным источником, но независимая проверка ещё не завершена."
    if pricing_status == "preliminary":
        if not has_unpriced_positions:
            return (
                "Все строки рассчитаны и включены в итог по предварительным ценам; "
                "цены без датированного источника требуют проверки перед договором."
            )
        return (
            "Смета неполная: подтверждённые строки включены в итог, а строки без "
            "актуальной цены сохранены с нулём и в сумму не включены."
        )
    return "Готовой сметы нет: требуются индивидуальные позиции, объёмы и подтверждённые цены."


def _normalise_text_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value[:limit] if (text := _clean_text(item, limit=1_000))]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _unique_code(base: str, used: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in used:
        tail = f"-{suffix}"
        candidate = f"{base[: max(1, 80 - len(tail))]}{tail}"
        suffix += 1
    used.add(candidate)
    return candidate


def _normalise_unit(value: Any) -> str:
    unit = _clean_text(value, limit=40)
    aliases = {
        "м2": "м²",
        "м^2": "м²",
        "кв.м": "м²",
        "м3": "м³",
        "м^3": "м³",
        "куб.м": "м³",
        "комплект": "компл",
    }
    return aliases.get(unit.casefold(), unit) if unit else "шт"


def _clean_text(value: Any, *, limit: int | None = None) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text[:limit] if limit is not None else text


def _decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    raw = str(value if value is not None else "").strip().replace(" ", "").replace(",", ".")
    try:
        parsed = Decimal(raw)
        return parsed if parsed.is_finite() else default
    except (InvalidOperation, ValueError):
        return default


def _decimal_text(value: Any, default: str = "0") -> str:
    return _plain_decimal(_decimal(value, default=Decimal(default)))


def _plain_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f") if normalized != normalized.to_integral() else str(normalized.quantize(Decimal("1")))


def _money(value: Decimal) -> str:
    return str(value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))
