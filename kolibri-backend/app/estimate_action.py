"""Typed estimate action contract for conversational estimate requests.

Provider output is treated as an untrusted draft.  This module owns intent
detection, canonical field normalisation and all arithmetic exposed in the
chat action.  A provider cannot promote its own prices to ``source_backed``:
that status is reserved for a future evidence verifier.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any, Iterable, Mapping


MONEY_QUANT = Decimal("0.01")
ESTIMATE_REQUEST_RE = re.compile(
    r"(?:\b(?:состав\w*|подготов\w*|созда\w*|сдела\w*|рассч\w*|посчит\w*)\b.{0,80}\bсмет\w*\b)"
    r"|(?:\bсмет\w*\b.{0,80}\b(?:строит\w*|ремонт\w*|монтаж\w*|работ\w*)\b)",
    re.IGNORECASE | re.DOTALL,
)
AREA_RE = re.compile(r"(?P<area>\d{1,4}(?:[.,]\d{1,2})?)\s*(?:м\s*[²2]|кв\.?\s*м)", re.IGNORECASE)


def latest_user_text(messages: Iterable[Mapping[str, Any]]) -> str:
    for message in reversed(list(messages)):
        if str(message.get("role", "")).lower() == "user":
            return str(message.get("content") or "").strip()
    return ""


def is_estimate_request(messages: Iterable[Mapping[str, Any]]) -> bool:
    return bool(ESTIMATE_REQUEST_RE.search(latest_user_text(messages)))


def ensure_estimate_action(
    messages: Iterable[Mapping[str, Any]], actions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return a canonical estimate action whenever the user requested one."""
    prompt = latest_user_text(messages)
    if not ESTIMATE_REQUEST_RE.search(prompt):
        return actions

    estimate_action = next(
        (action for action in actions if action.get("type") == "create_estimate"),
        None,
    )
    other_actions = [action for action in actions if action.get("type") != "create_estimate"]
    candidate = estimate_action.get("data") if estimate_action else None
    return [build_estimate_action(prompt, candidate), *other_actions]


def build_estimate_action(prompt: str, candidate: Any = None) -> dict[str, Any]:
    """Build a preliminary, editable and deterministically calculated action.

    Prices returned by a language model are kept only as *unverified budget
    assumptions*.  Source fields are deliberately blank until a separate
    evidence collector and verifier attaches dated regional evidence.
    """
    area = _extract_area(prompt)
    location = _extract_location(prompt)
    candidate_data = candidate if isinstance(candidate, Mapping) else {}
    sections = _normalise_sections(candidate_data.get("sections"))
    if not sections or not _has_positive_price(sections):
        sections = _fallback_sections(area)

    title = _clean_text(candidate_data.get("title")) or _default_title(area, location)
    object_name = _clean_text(candidate_data.get("object_name")) or _default_object_name(area)
    region = _clean_text(candidate_data.get("region")) or location
    # The editor contract currently exposes one common tax policy.  Do not let
    # an untrusted model silently override it.  Russia's standard VAT rate is
    # 22% for supplies performed from 2026-01-01 (Federal Law 425-FZ).
    overhead_rate = "0"
    vat_rate = "22"
    totals = _calculate_totals(sections, overhead_rate=overhead_rate, vat_rate=vat_rate)

    data = {
        "title": title,
        "client": _clean_text(candidate_data.get("client")),
        "object_name": object_name,
        "region": region,
        "currency": "RUB",
        "overhead_rate": overhead_rate,
        "vat_rate": vat_rate,
        "sections": sections,
        "estimate_status": "preliminary",
        "pricing_status": "preliminary",
        "price_sources": [],
        "tax_basis": {
            "name": "Федеральный закон от 28.11.2025 № 425-ФЗ",
            "as_of": "2026-01-01",
            "url": "https://www.nalog.gov.ru/rn77/about_fts/about_nalog/16594097/",
        },
        "source_note": (
            "Подтверждённые актуальные региональные источники цен не приложены. "
            "Ставки являются редактируемыми бюджетными предположениями и не должны "
            "использоваться как коммерческое предложение без актуализации."
        ),
        "assumptions": [
            "Площадь принята по запросу пользователя." if area else "Площадь объекта требует уточнения.",
            "Объёмы и ставки являются предварительными бюджетными предположениями.",
            "Итоги рассчитаны backend-движком Decimal, а не языковой моделью.",
        ],
        "questions": [
            "Предоставьте проект, спецификации и конструктивную схему для расчёта объёмов.",
            "Подтвердите комплектацию, материалы, инженерные системы и уровень отделки.",
            "Разрешите сбор датированных цен поставщиков и региональных индексов для статуса source_backed.",
        ],
        "totals": totals,
    }
    return {
        "type": "create_estimate",
        "label": "Открыть предварительную смету",
        "data": data,
    }


def _extract_area(prompt: str) -> Decimal:
    match = AREA_RE.search(prompt)
    if not match:
        return Decimal("100")
    return _decimal(match.group("area"), default=Decimal("100"))


def _extract_location(prompt: str) -> str:
    lowered = prompt.casefold()
    if "лениногорск" in lowered and "татарстан" in lowered:
        return "Лениногорск, Татарстан"
    if "лениногорск" in lowered:
        return "Лениногорск"
    if "татарстан" in lowered:
        return "Татарстан"
    return ""


def _default_title(area: Decimal, location: str) -> str:
    area_text = _plain_decimal(area)
    suffix = f" — {location}" if location else ""
    return f"Предварительная смета: одноэтажный дом {area_text} м²{suffix}"


def _default_object_name(area: Decimal) -> str:
    return f"Одноэтажный дом { _plain_decimal(area) } м²"


def _fallback_sections(area: Decimal) -> list[dict[str, Any]]:
    roof_area = (area * Decimal("1.30")).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    return [
        _section("Подготовка", [
            _position("ПР-01", "Предпроектная подготовка и организация работ", "компл", "1", "250000"),
        ]),
        _section("Фундамент", [
            _position("ФН-01", "Комплекс устройства фундамента", "м²", area, "15000"),
        ]),
        _section("Коробка здания", [
            _position("КР-01", "Несущая коробка и перекрытия, комплект работ и материалов", "м²", area, "30000"),
        ]),
        _section("Кровля", [
            _position("КВ-01", "Кровельная система, комплект работ и материалов", "м²", roof_area, "12000"),
        ]),
        _section("Инженерные системы", [
            _position("ИС-01", "Базовый комплекс инженерных систем", "м²", area, "18000"),
        ]),
        _section("Отделка", [
            _position("ОТ-01", "Базовая внутренняя отделка", "м²", area, "25000"),
        ]),
    ]


def _section(title: str, positions: list[dict[str, str]]) -> dict[str, Any]:
    return {"title": title, "positions": positions}


def _position(
    code: str, name: str, unit: str, quantity: Any, price: Any, comment: str = ""
) -> dict[str, str]:
    quantity_text = _decimal_text(quantity)
    price_text = _decimal_text(price)
    line_total = _money(_decimal(quantity_text) * _decimal(price_text))
    note = comment.strip() or "Бюджетная ставка без подтверждённого актуального источника; требуется актуализация."
    return {
        "code": code,
        "name": name,
        "unit": unit,
        "quantity": quantity_text,
        "price": price_text,
        "sum": line_total,
        "source": "",
        "comment": note,
    }


def _normalise_sections(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sections: list[dict[str, Any]] = []
    for section_index, raw_section in enumerate(value, start=1):
        if not isinstance(raw_section, Mapping):
            continue
        raw_positions = raw_section.get("positions")
        if not isinstance(raw_positions, list):
            continue
        positions: list[dict[str, str]] = []
        for position_index, raw_position in enumerate(raw_positions, start=1):
            if not isinstance(raw_position, Mapping):
                continue
            quantity = _decimal(raw_position.get("quantity"), default=Decimal("0"))
            price = _decimal(raw_position.get("price"), default=Decimal("0"))
            if quantity <= 0 or price < 0:
                continue
            positions.append(_position(
                _clean_text(raw_position.get("code")) or f"AI-{section_index:02d}-{position_index:03d}",
                _clean_text(raw_position.get("name")) or "Позиция",
                _normalise_unit(raw_position.get("unit")),
                quantity,
                price,
                _clean_text(raw_position.get("comment")),
            ))
        if positions:
            sections.append({
                "title": _clean_text(raw_section.get("title")) or f"Раздел {section_index}",
                "positions": positions,
            })
    return sections


def _calculate_totals(
    sections: list[dict[str, Any]], overhead_rate: str, vat_rate: str
) -> dict[str, str]:
    subtotal = sum(
        (
            _decimal(position.get("quantity")) * _decimal(position.get("price"))
            for section in sections
            for position in section.get("positions", [])
        ),
        Decimal("0"),
    )
    subtotal = subtotal.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
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


def _has_positive_price(sections: list[dict[str, Any]]) -> bool:
    return any(
        _decimal(position.get("price")) > 0
        for section in sections
        for position in section.get("positions", [])
    )


def _normalise_unit(value: Any) -> str:
    unit = _clean_text(value)
    aliases = {"м2": "м²", "м^2": "м²", "кв.м": "м²", "комплект": "компл"}
    return aliases.get(unit.casefold(), unit) if unit else "шт"


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


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
