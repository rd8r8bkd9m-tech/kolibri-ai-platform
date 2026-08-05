"""Universal technology-card contract for AI-authored estimates.

The card is domain-neutral: the same schema can describe plastering, a private
house, a water well, an oil-field installation or software/instrumentation
work.  A model chooses the technology; the server validates provenance,
lineage and arithmetic, then derives estimate rows from the card.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


DECIMAL_PATTERN = r"^\d+(?:\.\d+)?$"
MEASUREMENT_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:"
    r"м\s*[²³23]|кв\.?\s*м|мм|см|км|м|кг|т|л|шт\.?|компл\.?|"
    r"бар|мпа|квт|в|а|час\w*|дн\w*|смен\w*)\b",
    re.I,
)


class TechnologyCardError(ValueError):
    """Provider draft failed the universal technology-first contract."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TechnologyFact(StrictModel):
    quote: str = Field(min_length=1, max_length=2_000)
    meaning: str = Field(min_length=1, max_length=2_000)


class TechnologyResource(BaseModel):
    model_config = ConfigDict(extra="allow")
    kind: Literal["work", "material", "equipment", "service"]
    code: str = Field(default="", max_length=80)
    name: str = Field(min_length=1, max_length=320)
    unit: str = Field(min_length=1, max_length=40)
    quantity: str = Field(pattern=DECIMAL_PATTERN, max_length=64)
    price: str = Field(pattern=DECIMAL_PATTERN, max_length=64)
    quantity_basis: str = Field(default="", max_length=1_000)
    procurement_query: str = Field(default="", max_length=1_000)

    @model_validator(mode="after")
    def positive_quantity_and_price(self):
        if _decimal(self.quantity) <= 0:
            raise ValueError("technology resource quantity must be positive")
        if _decimal(self.price) < 0:
            raise ValueError("technology resource price proposal cannot be negative")
        return self


class TechnologyOperation(StrictModel):
    sequence: int = Field(ge=1, le=10_000)
    name: str = Field(min_length=1, max_length=320)
    method: str = Field(min_length=1, max_length=4_000)
    prerequisites: list[str] = Field(default_factory=list, max_length=100)
    quality_checks: list[str] = Field(default_factory=list, max_length=100)
    safety_controls: list[str] = Field(default_factory=list, max_length=100)
    resources: list[TechnologyResource] = Field(default_factory=list, max_length=500)


class TechnologyStage(StrictModel):
    sequence: int = Field(ge=1, le=10_000)
    name: str = Field(min_length=1, max_length=320)
    result: str = Field(min_length=1, max_length=2_000)
    operations: list[TechnologyOperation] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_operation_sequence(self):
        values = [operation.sequence for operation in self.operations]
        if len(values) != len(set(values)):
            raise ValueError("technology operation sequence must be unique within a stage")
        self.operations.sort(key=lambda item: item.sequence)
        return self


class TechnologyCard(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    title: str = Field(min_length=1, max_length=320)
    object_type: str = Field(min_length=1, max_length=320)
    scope: str = Field(min_length=1, max_length=4_000)
    user_facts: list[TechnologyFact] = Field(default_factory=list, max_length=100)
    assumptions: list[str] = Field(default_factory=list, max_length=200)
    exclusions: list[str] = Field(default_factory=list, max_length=200)
    stages: list[TechnologyStage] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_stage_sequence(self):
        values = [stage.sequence for stage in self.stages]
        if len(values) != len(set(values)):
            raise ValueError("technology stage sequence must be unique")
        self.stages.sort(key=lambda item: item.sequence)
        return self


def prepare_estimate_candidate(
    prompt: str,
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the provider card and derive every estimate row from it."""

    raw_card = candidate.get("technology_card")
    try:
        card = TechnologyCard.model_validate(raw_card)
    except (ValidationError, TypeError) as exc:
        raise TechnologyCardError("technology_card_invalid") from exc
    _verify_user_fact_provenance(prompt, card)

    sections: list[dict[str, Any]] = []
    used_codes: set[str] = set()
    for stage_index, stage in enumerate(card.stages, start=1):
        positions: list[dict[str, str]] = []
        for operation_index, operation in enumerate(stage.operations, start=1):
            for resource_index, resource in enumerate(operation.resources, start=1):
                base_code = resource.code.strip() or (
                    f"TC-{stage_index:03d}-{operation_index:03d}-{resource_index:03d}"
                )
                code = _unique_code(base_code, used_codes)
                comment_parts = [
                    f"Тип: {_kind_label(resource.kind)}.",
                    f"Операция: {operation.name}.",
                    f"Основание количества: {resource.quantity_basis}.",
                ]
                if resource.procurement_query.strip():
                    comment_parts.append(
                        f"Задание снабженцу: {resource.procurement_query.strip()}."
                    )
                positions.append(
                    {
                        "code": code,
                        "name": resource.name.strip(),
                        "unit": resource.unit.strip(),
                        "quantity": resource.quantity,
                        "price": resource.price,
                        "comment": " ".join(comment_parts),
                    }
                )
        sections.append(
            {
                "title": f"{stage.sequence:02d}. {stage.name}",
                "positions": positions,
            }
        )

    assumptions = _text_list(candidate.get("assumptions"))
    assumptions.extend(card.assumptions)
    assumptions.append(
        "Состав строк выведен из типизированной технологической карты; "
        "цены без подтверждённого источника остаются предварительными."
    )
    if card.exclusions:
        assumptions.append("Не включено: " + "; ".join(card.exclusions))

    normalized_card = card.model_dump(mode="json")
    normalized_card["content_sha256"] = technology_card_sha256(normalized_card)
    return {
        "title": str(candidate.get("title") or card.title).strip(),
        "object_name": str(candidate.get("object_name") or card.object_type).strip(),
        "region": str(candidate.get("region") or "").strip(),
        "client": str(candidate.get("client") or "").strip(),
        "questions": [],
        "assumptions": assumptions,
        "technology_card": normalized_card,
        "sections": sections,
    }


def interpret_estimate_candidate(
    prompt: str,
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """Interpret either a native card or a finished editable Solo estimate.

    Codex may already return a complete estimate instead of the native card.
    In that case Kolibri preserves every row and builds a domain-neutral card
    from section/position lineage; it does not substitute a house/plaster/etc.
    template or rewrite the professional result.
    """

    if isinstance(candidate.get("technology_card"), Mapping):
        return prepare_estimate_candidate(prompt, candidate)
    sections = candidate.get("sections")
    if not isinstance(sections, list) or not sections:
        raise TechnologyCardError("technology_card_or_estimate_sections_required")
    card_stages: list[dict[str, Any]] = []
    for stage_index, raw_section in enumerate(sections, start=1):
        if not isinstance(raw_section, Mapping):
            continue
        raw_positions = raw_section.get("positions", raw_section.get("items"))
        if not isinstance(raw_positions, list) or not raw_positions:
            continue
        resources: list[dict[str, Any]] = []
        for raw_position in raw_positions:
            if not isinstance(raw_position, Mapping):
                continue
            name = " ".join(str(raw_position.get("name") or "").split()).strip()
            unit = " ".join(str(raw_position.get("unit") or "").split()).strip()
            quantity = _positive_decimal_text(raw_position.get("quantity"))
            price = _nonnegative_decimal_text(
                raw_position.get("price", raw_position.get("unit_price"))
            )
            if not name or not unit or quantity is None or price is None:
                continue
            comment = " ".join(str(raw_position.get("comment") or "").split()).strip()
            resources.append(
                {
                    "kind": _infer_resource_kind(
                        f"{raw_section.get('title', '')} {name}"
                    ),
                    "code": " ".join(str(raw_position.get("code") or "").split())[:80],
                    "name": name[:320],
                    "unit": unit[:40],
                    "quantity": quantity,
                    "price": price,
                    "quantity_basis": (
                        comment[:1_000]
                        or "Количество принято из готовой профессиональной сметы исполнителя."
                    ),
                    "procurement_query": (
                        f"Проверить наличие, единицу, региональную цену и НДС: {name}"
                    )[:1_000],
                }
            )
        if not resources:
            continue
        stage_name = " ".join(str(raw_section.get("title") or f"Раздел {stage_index}").split())
        card_stages.append(
            {
                "sequence": stage_index,
                "name": stage_name[:320],
                "result": f"Результат раздела «{stage_name[:240]}» выполнен и предъявлен к приёмке.",
                "operations": [{
                    "sequence": 1,
                    "name": stage_name[:320],
                    "method": (
                        "Технологическая последовательность и ресурсы приняты из готовой "
                        "профессиональной сметы AI-исполнителя; уточняются по проекту/ППР."
                    ),
                    "prerequisites": ["Подтверждены исходные данные и доступность фронта работ"],
                    "quality_checks": ["Проверены объёмы, единицы и результат раздела"],
                    "safety_controls": ["Применяются меры охраны труда по фактическому виду работ"],
                    "resources": resources,
                }],
            }
        )
    if not card_stages:
        raise TechnologyCardError("estimate_sections_have_no_interpretable_rows")
    prompt_quote = " ".join(str(prompt or "").split()).strip()[:2_000]
    interpreted = dict(candidate)
    interpreted["technology_card"] = {
        "schema_version": "1.0",
        "title": str(candidate.get("title") or "Технологическая карта сметы")[:320],
        "object_type": str(candidate.get("object_name") or candidate.get("title") or "Объект работ")[:320],
        "scope": "Состав и последовательность работ интерпретированы из готовой сметы AI-исполнителя.",
        "user_facts": [{
            "quote": prompt_quote,
            "meaning": "Полный исходный запрос является обязательным заданием для сметы.",
        }],
        "assumptions": _text_list(candidate.get("assumptions")),
        "exclusions": [],
        "stages": card_stages,
    }
    return prepare_estimate_candidate(prompt, interpreted)


def validate_stored_technology_card(value: Any) -> dict[str, Any] | None:
    """Validate a card crossing the CRUD boundary and preserve its hash."""

    if value in (None, {}):
        return None
    if not isinstance(value, Mapping):
        raise TechnologyCardError("technology_card_invalid")
    raw = dict(value)
    claimed_hash = str(raw.pop("content_sha256", "")).strip()
    try:
        card = TechnologyCard.model_validate(raw)
    except ValidationError as exc:
        raise TechnologyCardError("technology_card_invalid") from exc
    normalized = card.model_dump(mode="json")
    digest = technology_card_sha256(normalized)
    if claimed_hash and claimed_hash != digest:
        raise TechnologyCardError("technology_card_hash_mismatch")
    normalized["content_sha256"] = digest
    return normalized


def technology_card_sha256(value: Mapping[str, Any]) -> str:
    canonical = dict(value)
    canonical.pop("content_sha256", None)
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _verify_user_fact_provenance(prompt: str, card: TechnologyCard) -> None:
    normalized_prompt = _normalize(prompt)
    if not normalized_prompt:
        raise TechnologyCardError("technology_card_missing_prompt")
    quotes = [_normalize(fact.quote) for fact in card.user_facts]
    if any(not quote or quote not in normalized_prompt for quote in quotes):
        raise TechnologyCardError("technology_card_fact_quote_not_in_request")
    card_text = _normalize(json.dumps(card.model_dump(mode="json"), ensure_ascii=False))
    missing_measurements = [
        measurement
        for measurement in {_normalize(match.group(0)) for match in MEASUREMENT_RE.finditer(prompt)}
        if measurement not in card_text
    ]
    if missing_measurements:
        raise TechnologyCardError("technology_card_measurement_omitted")


def _unique_code(base: str, used: set[str]) -> str:
    clean = " ".join(str(base).split()).strip()[:80] or "TC"
    candidate = clean
    suffix = 2
    while candidate in used:
        marker = f"-{suffix}"
        candidate = f"{clean[:80-len(marker)]}{marker}"
        suffix += 1
    used.add(candidate)
    return candidate


def _kind_label(kind: str) -> str:
    return {
        "work": "работа",
        "material": "материал",
        "equipment": "машины/оборудование",
        "service": "услуга",
    }.get(kind, kind)


def _infer_resource_kind(text: str) -> str:
    normalized = _normalize(text)
    if re.search(r"\b(?:материал|смесь|бетон|кирпич|блок|труб|кабел|арматур|краск|крепеж)\w*\b", normalized):
        return "material"
    if re.search(r"\b(?:машин|механизм|кран|экскаватор|буров|аренд|оборудован)\w*\b", normalized):
        return "equipment"
    if re.search(r"\b(?:достав|вывоз|проект|изыскан|лаборатор|испытан|услуг)\w*\b", normalized):
        return "service"
    return "work"


def _positive_decimal_text(value: Any) -> str | None:
    text = str(value if value is not None else "").replace(" ", "").replace(",", ".")
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return text if parsed.is_finite() and parsed > 0 else None


def _nonnegative_decimal_text(value: Any) -> str | None:
    text = str(value if value is not None else "0").replace(" ", "").replace(",", ".")
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return text if parsed.is_finite() and parsed >= 0 else None


def _decimal(value: str) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid technology decimal") from exc
    if not result.is_finite():
        raise ValueError("technology decimal must be finite")
    return result


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("ё", "е").split())


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [" ".join(str(item).split()).strip()[:2_000] for item in value if str(item).strip()]
