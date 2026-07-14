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


MONEY_QUANT = Decimal("0.01")
ESTIMATE_REQUEST_RE = re.compile(
    r"(?:\b(?:состав\w*|подготов\w*|созда\w*|сдела\w*|рассч\w*|посчит\w*)\b.{0,80}\bсмет\w*\b)"
    r"|(?:\bсмет\w*\b.{0,80}\b(?:строит\w*|ремонт\w*|монтаж\w*|работ\w*)\b)",
    re.IGNORECASE | re.DOTALL,
)
AREA_RE = re.compile(r"(?P<area>\d{1,4}(?:[.,]\d{1,2})?)\s*(?:м\s*[²2]|кв\.?\s*м)", re.IGNORECASE)
ESTIMATE_STATUSES = {"needs_input", "preliminary", "source_backed", "verified"}


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
    """Return a canonical action without inventing a fallback estimate."""
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


def build_estimate_action(
    prompt: str,
    candidate: Any = None,
    *,
    verified_evidence: Any = None,
    scope_verified: bool = False,
    project_fact: Mapping[str, Any] | None = None,
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
    questions = _normalise_text_list(candidate_data.get("questions"), limit=50)
    questions.extend(_required_questions(sections, region, pricing_status, scope_verified))

    data = {
        "title": title,
        "client": _clean_text(candidate_data.get("client"), limit=240),
        "object_name": object_name,
        "region": region,
        "currency": currency,
        "overhead_rate": overhead_rate,
        "vat_rate": vat_rate,
        "sections": sections,
        "estimate_status": estimate_status,
        "pricing_status": pricing_status,
        "scope_status": "verified" if scope_verified else "unverified",
        "price_sources": evidence["price_sources"],
        "evidence_issues": evidence["evidence_issues"],
        "source_note": _source_note(estimate_status, pricing_status),
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


def _source_note(estimate_status: str, pricing_status: str) -> str:
    if estimate_status == "verified":
        return "Все объёмы и цены связаны с проверенными исходными данными и датированными источниками."
    if pricing_status == "verified":
        return "Цены проверены по датированным источникам; объёмы и состав работ ещё требуют независимой проверки."
    if pricing_status == "source_backed":
        return "Каждая цена связана с датированным источником, но независимая проверка ещё не завершена."
    if pricing_status == "preliminary":
        return "Часть или все цены пока не имеют подходящих актуальных региональных источников."
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
