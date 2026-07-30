"""Safe natural-language mutations for the estimate editor.

The language model may suggest a command, but this module is the only layer
allowed to translate that command into persisted estimate fields.  Every
operation is typed, bounded and applied to the current immutable revision.
"""
from __future__ import annotations

import copy
import re
from decimal import Decimal, InvalidOperation


_RATE_PATTERNS = {
    "overhead_rate": r"накладн\w*(?:\s+расход\w*)?",
    "profit_rate": r"(?:сметн\w*\s+)?прибыл\w*",
    "contingency_rate": r"(?:резерв\w*|непредвиденн\w*(?:\s+расход\w*)?)",
    "general_contractor_rate": r"генподрядн\w*(?:\s+(?:услуг\w*|расход\w*))?",
    "discount_rate": r"скидк\w*",
    "vat_rate": r"ндс",
}
_RATE_LABELS = {
    "overhead_rate": "накладные расходы",
    "profit_rate": "сметная прибыль",
    "contingency_rate": "резерв",
    "general_contractor_rate": "генподрядные услуги",
    "discount_rate": "скидка",
    "vat_rate": "НДС",
}
_NUMBER = r"(\d{1,3}(?:[.,]\d{1,4})?)"


def _decimal_text(value: str, *, maximum: Decimal | None = None) -> str:
    try:
        parsed = Decimal(value.replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Некорректное числовое значение") from exc
    if not parsed.is_finite() or parsed < 0 or (maximum is not None and parsed > maximum):
        raise ValueError("Числовое значение выходит за допустимые границы")
    return format(parsed.normalize(), "f")


def _clean_fragment(value: str) -> str:
    return value.strip().strip('"«»').strip().rstrip(".,;:")[:300]


def _position_matches(sections: list[dict], fragment: str) -> list[tuple[int, int]]:
    needle = fragment.casefold()
    matches: list[tuple[int, int]] = []
    for section_index, section in enumerate(sections):
        for position_index, position in enumerate(section.get("positions") or []):
            haystacks = (
                str(position.get("name") or "").casefold(),
                str(position.get("code") or "").casefold(),
            )
            if any(needle and needle in value for value in haystacks):
                matches.append((section_index, position_index))
    return matches


def build_estimate_command_update(
    estimate: dict,
    command: str,
) -> tuple[dict | None, list[dict], str]:
    """Return a validated update payload and an auditable operation list."""

    text = " ".join(command.split()).strip()
    if not text:
        raise ValueError("Команда не может быть пустой")
    if len(text) > 2_000:
        raise ValueError("Команда слишком длинная")

    update: dict = {}
    operations: list[dict] = []

    # Tax presets are authoritative for VAT; explicit VAT later in the same
    # command may override only when the regime is left unspecified.
    lowered = text.casefold()
    tax_regime: tuple[str, str] | None = None
    if re.search(r"\b(?:самозанят\w*|нпд)\b", lowered):
        tax_regime = ("npd", "0")
    elif re.search(r"\bусн\b", lowered) and re.search(r"\b7\s*%", lowered):
        tax_regime = ("usn_vat7", "7")
    elif re.search(r"\bусн\b", lowered) and re.search(r"\b5\s*%", lowered):
        tax_regime = ("usn_vat5", "5")
    elif re.search(r"\bусн\b", lowered) and re.search(r"без\s+ндс|освобожд", lowered):
        tax_regime = ("usn_exempt", "0")
    elif re.search(r"\bосно\b", lowered):
        tax_regime = ("osno_vat22", "22")
    if tax_regime:
        update["tax_regime"], update["vat_rate"] = tax_regime
        operations.append({"type": "set_tax_regime", "value": tax_regime[0]})

    for field, label_pattern in _RATE_PATTERNS.items():
        match = re.search(
            rf"(?:{label_pattern})\s*(?:до|на|=|:)??\s*{_NUMBER}\s*%?",
            lowered,
        )
        if not match:
            continue
        value = _decimal_text(match.group(1), maximum=Decimal("999"))
        if field == "vat_rate" and tax_regime and tax_regime[0] != "unspecified":
            continue
        update[field] = value
        operations.append({"type": "set_rate", "field": field, "value": value})

    sections = copy.deepcopy(estimate.get("sections") or [])
    sections_changed = False

    rename_match = re.search(
        r"переимен\w+\s+(?:позици\w*\s+)?[\"«]?(.+?)[\"»]?\s+(?:в|на)\s+[\"«]?(.+?)[\"»]?(?:$|[.;])",
        text,
        re.IGNORECASE,
    )
    if rename_match:
        old_name = _clean_fragment(rename_match.group(1))
        new_name = _clean_fragment(rename_match.group(2))
        matches = _position_matches(sections, old_name)
        if len(matches) != 1:
            raise ValueError(
                "Для переименования укажите уникальный фрагмент наименования позиции"
            )
        section_index, position_index = matches[0]
        previous = sections[section_index]["positions"][position_index]["name"]
        sections[section_index]["positions"][position_index]["name"] = new_name
        sections_changed = True
        operations.append(
            {"type": "rename_position", "from": previous, "to": new_name}
        )

    delete_match = re.search(
        r"удал\w+\s+(?:позици\w*\s+)?[\"«]?(.+?)[\"»]?(?:$|[.;])",
        text,
        re.IGNORECASE,
    )
    if delete_match:
        fragment = _clean_fragment(delete_match.group(1))
        matches = _position_matches(sections, fragment)
        if len(matches) != 1:
            raise ValueError("Для удаления укажите уникальный фрагмент позиции")
        section_index, position_index = matches[0]
        removed = sections[section_index]["positions"].pop(position_index)
        sections_changed = True
        operations.append({"type": "delete_position", "name": removed.get("name", "")})

    value_match = re.search(
        rf"(?:измени|установи|поставь)\s+(количество|цену)\s+(?:позици\w*\s+)?[\"«]?(.+?)[\"»]?\s+(?:на|=)\s*{_NUMBER}",
        text,
        re.IGNORECASE,
    )
    if value_match:
        field = "quantity" if value_match.group(1).casefold().startswith("кол") else "price"
        fragment = _clean_fragment(value_match.group(2))
        value = _decimal_text(value_match.group(3))
        matches = _position_matches(sections, fragment)
        if len(matches) != 1:
            raise ValueError("Для изменения укажите уникальный фрагмент позиции")
        section_index, position_index = matches[0]
        position = sections[section_index]["positions"][position_index]
        position[field] = value
        sections_changed = True
        operations.append(
            {"type": "set_position_value", "name": position.get("name", ""), "field": field, "value": value}
        )

    if re.search(r"\bутверд\w*\s+(?:эту\s+)?смет\w*", lowered):
        update["status"] = "approved"
        operations.append({"type": "approve_estimate"})

    if sections_changed:
        update["sections"] = [
            {
                "title": section.get("title") or "Раздел",
                "positions": [
                    {
                        "code": position.get("code") or "",
                        "name": position.get("name") or "",
                        "unit": position.get("unit") or "шт",
                        "quantity": position.get("quantity") or "0",
                        "price": position.get("price") or "0",
                        "source": position.get("source") or "",
                        "price_evidence": position.get("price_evidence") or [],
                        "comment": position.get("comment") or "",
                    }
                    for position in section.get("positions") or []
                ],
            }
            for section in sections
        ]

    if not operations:
        return None, [], (
            "Я не нашёл безопасного изменения. Можно написать, например: "
            "«накладные 12%, прибыль 8%, НДС 22%», «удали позицию Доставка» "
            "или «переименуй Черновые работы в Подготовительные работы»."
        )

    labels: list[str] = []
    for operation in operations:
        if operation["type"] == "set_rate":
            labels.append(f"{_RATE_LABELS[operation['field']]} {operation['value']}%")
        elif operation["type"] == "set_tax_regime":
            labels.append("налоговый режим")
        elif operation["type"] == "rename_position":
            labels.append("наименование позиции")
        elif operation["type"] == "delete_position":
            labels.append("удаление позиции")
        elif operation["type"] == "set_position_value":
            labels.append("значение позиции")
        elif operation["type"] == "approve_estimate":
            labels.append("утверждение сметы")
    return update, operations, "Применено: " + ", ".join(labels) + "."
