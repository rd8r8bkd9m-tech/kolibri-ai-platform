"""Typed public vertical-task contracts for the Kolibri Shell.

The public chat surface may ask Kolibri to calculate an estimate, prepare a
document, create a site, or create an application.  This module deliberately
separates a verified provider response from a materialized deliverable:

* monetary totals are produced only by the deterministic estimate engine;
* provider text is an execution result, not proof that a file exists;
* artifact references are returned only when content-bound materialization
  evidence is present; and
* a document/site/app remains ``incomplete`` until every requested deliverable
  has that evidence.

No durable project, artifact, or owner state is mutated here.  Those operations
remain behind the authenticated V1 execution API.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from artifact_runtime import (
    EstimateSpec,
    deterministic_estimate,
    reject_secret_material,
    validate_structured_value,
)


VERTICAL_TASK_SCHEMA = "kolibri.public-task.v1"
ESTIMATE_FALLBACK_ENGINE = "kolibri.estimate-assumption-engine.v1"
ESTIMATE_FALLBACK_PROOF_SCHEMA = "kolibri.estimate-engine-proof.v1"
MAX_PROVIDER_ESTIMATE_LINES = 32
MAX_PROVIDER_ESTIMATE_RESPONSE_BYTES = 24_576
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class _StrictTask(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _validate_public_structure(value: dict[str, Any], *, label: str) -> dict[str, Any]:
    validate_structured_value(value, label=label)
    reject_secret_material(value, label=label)
    return value


class EstimateVerticalTask(_StrictTask):
    intent: Literal["estimate"]
    brief: str | None = Field(default=None, min_length=1, max_length=50_000)
    region: str | None = Field(default=None, min_length=1, max_length=300)
    spec: EstimateSpec | None = None
    requested_artifacts: list[Literal["pdf", "pdf-x", "xlsx", "docx"]] = Field(
        default_factory=list,
        max_length=4,
    )

    @model_validator(mode="after")
    def require_brief_or_spec(self) -> "EstimateVerticalTask":
        if self.brief is None and self.spec is None:
            raise ValueError("estimate task requires brief or spec")
        return self


class DocumentVerticalTask(_StrictTask):
    intent: Literal["document"]
    brief: str = Field(min_length=1, max_length=50_000)
    document_type: Literal[
        "commercial-offer",
        "contract",
        "completion-act",
        "invoice",
        "report",
        "custom",
    ] = "custom"
    format: Literal["pdf", "pdf-x", "xlsx", "docx", "html", "text"] = "pdf"
    content: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_public_structure(value, label="document task content")


class SiteVerticalTask(_StrictTask):
    intent: Literal["site"]
    brief: str = Field(min_length=1, max_length=50_000)
    target: Literal["website", "webapp"] = "website"
    requirements: dict[str, Any] = Field(default_factory=dict)
    requested_artifacts: list[
        Literal["source", "site-preview", "test-report"]
    ] = Field(default_factory=lambda: ["source", "site-preview"], min_length=1, max_length=3)

    @field_validator("requirements")
    @classmethod
    def validate_requirements(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_public_structure(value, label="site task requirements")


class AppVerticalTask(_StrictTask):
    intent: Literal["app"]
    brief: str = Field(min_length=1, max_length=50_000)
    target: Literal["web", "linux", "container", "android", "ios", "macos"] = "web"
    requirements: dict[str, Any] = Field(default_factory=dict)
    requested_artifacts: list[
        Literal["source", "build", "test-report", "app-preview"]
    ] = Field(default_factory=lambda: ["source", "build", "test-report"], min_length=1, max_length=4)

    @field_validator("requirements")
    @classmethod
    def validate_requirements(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_public_structure(value, label="app task requirements")


VerticalTask = Annotated[
    EstimateVerticalTask | DocumentVerticalTask | SiteVerticalTask | AppVerticalTask,
    Field(discriminator="intent"),
]


def requested_deliverables(task: VerticalTask) -> list[str]:
    if isinstance(task, EstimateVerticalTask):
        return list(task.requested_artifacts)
    if isinstance(task, DocumentVerticalTask):
        return [task.format]
    return list(task.requested_artifacts)


def prepare_vertical_task(task: VerticalTask) -> tuple[str, dict[str, Any] | None]:
    """Create provider instructions and an optional deterministic calculation."""

    task_payload = task.model_dump(mode="json")
    calculation: dict[str, Any] | None = None
    if isinstance(task, EstimateVerticalTask):
        if task.spec is not None:
            calculation = deterministic_estimate(task.spec)
            task_payload["authoritative_calculation"] = calculation
        else:
            task_payload["proposal_contract"] = {
                "schema_version": "kolibri.estimate-proposal.v1",
                "required_fields": [
                    "title", "currency", "minor_unit", "region", "source_summary",
                    "lines", "overhead_rate_bps", "tax_rate_bps", "assumptions", "questions",
                ],
                "line_fields": [
                    "id", "section", "description", "category", "unit", "quantity",
                    "unit_price_minor", "provenance",
                ],
                "provenance_sources": [
                    "manual", "assumption", "catalog", "contract", "supplier", "measurement",
                ],
                "money_rule": (
                    "Propose quantities and unit_price_minor only. Do not return row totals or totals. "
                    "Kolibri calculates every monetary value deterministically after validation."
                ),
                "minor_unit_rule": (
                    "minor_unit is the count of decimal currency digits: use 2 for RUB, "
                    "never the multiplier 100. unit_price_minor for RUB is expressed in kopecks."
                ),
                "source_rule": (
                    "Use catalog/contract/supplier/measurement only with an explicit source_ref. "
                    "Otherwise use assumption and say that the price requires verification."
                ),
                "output_rule": "Return one JSON object only, without Markdown fences or commentary.",
                "scope_rule": (
                    "Return at most 32 consolidated lines. Group work and material by construction "
                    "phase; do not expand a bill of materials, repeat narrative, or add commentary. "
                    "Use at most 12 assumptions and 12 questions. Keep the complete JSON response "
                    "under 24576 UTF-8 bytes."
                ),
                "max_lines": MAX_PROVIDER_ESTIMATE_LINES,
                "max_assumptions": 12,
                "max_questions": 12,
                "max_response_bytes": MAX_PROVIDER_ESTIMATE_RESPONSE_BYTES,
            }
    encoded = json.dumps(task_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    instructions = (
        "Kolibri vertical-task contract: process the typed request below and return a useful "
        "customer-facing result. Do not claim that a file, preview, build, or document was "
        "created unless the runtime actually materialized it and emitted content-bound artifact "
        "evidence. For estimates, the embedded deterministic calculation is the only monetary "
        "authority; never replace, recalculate, or invent its totals. Typed request: "
        f"{encoded}"
    )
    return instructions, calculation


_PROVENANCE_SOURCES = {
    "manual", "assumption", "catalog", "contract", "supplier", "measurement",
}
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_MAX_EMBEDDED_JSON_STARTS = 128
_CATEGORIES = {"labor", "material", "equipment", "service", "other"}
_CATEGORY_ALIASES = {
    "work": "labor",
    "works": "labor",
    "labour": "labor",
    "job": "labor",
    "работа": "labor",
    "работы": "labor",
    "materials": "material",
    "материал": "material",
    "материалы": "material",
    "delivery": "service",
    "доставка": "service",
    "services": "service",
    "услуга": "service",
    "услуги": "service",
}


def _normalized_minor_unit(value: Any) -> Any:
    """Accept decimal digits and the common AI multiplier representation."""

    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"[0-9]+", text):
            value = int(text)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in {0, 2, 3}:
            return value
        return {1: 0, 100: 2, 1_000: 3}.get(value, value)
    return value


def _normalized_client_name(value: dict[str, Any]) -> Any:
    client = value.get("client")
    if value.get("client_name") is not None:
        return value.get("client_name")
    if isinstance(client, dict):
        return client.get("name")
    return client if isinstance(client, str) else None


def _normalized_object_field(value: dict[str, Any], field: str) -> Any:
    direct = value.get(f"object_{field}")
    if direct is not None:
        return direct
    object_value = value.get("object")
    if isinstance(object_value, dict):
        return object_value.get(field)
    if field == "name" and isinstance(object_value, str):
        return object_value
    return None


def _unwrapped_estimate_object(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    nested = value.get("estimate")
    return nested if isinstance(nested, dict) else value


def _json_objects_from_text(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return exact and embedded JSON objects from bounded model text.

    Codex normally returns the requested object as its final assistant message,
    but model output can still contain a Markdown fence or a short preamble.
    ``find('{')``/``rfind('}')`` is unsafe here: a second diagnostic object can
    make two otherwise valid objects look like one malformed blob.  Decode
    objects independently, cap the number of candidate starts, and let the
    caller reject ambiguous estimate proposals.
    """

    exact: list[dict[str, Any]] = []
    embedded: list[dict[str, Any]] = []
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = None
    else:
        # A valid JSON array/scalar is still a contract violation.  Do not
        # rescue an object nested inside it as though it were the required
        # top-level proposal object.
        if isinstance(value, dict):
            exact.append(value)
        return exact, embedded

    decoder = json.JSONDecoder()
    offset = 0
    attempted = 0
    while attempted < _MAX_EMBEDDED_JSON_STARTS:
        start = text.find("{", offset)
        if start < 0:
            break
        attempted += 1
        offset = start + 1
        try:
            value, _end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            embedded.append(value)
    return exact, embedded


def _provider_json_object(response_text: str) -> dict[str, Any]:
    text = response_text.strip()
    if not text:
        raise ValueError("estimate proposal is not a JSON object")

    segments = [match.group(1).strip() for match in _JSON_FENCE.finditer(text)]
    segments.append(text)
    exact_objects: list[dict[str, Any]] = []
    embedded_objects: list[dict[str, Any]] = []
    for segment in segments:
        if not segment:
            continue
        exact, embedded = _json_objects_from_text(segment)
        exact_objects.extend(exact)
        embedded_objects.extend(embedded)

    estimate_candidates: dict[str, dict[str, Any]] = {}
    for raw in [*exact_objects, *embedded_objects]:
        value = _unwrapped_estimate_object(raw)
        if value is None or not isinstance(value.get("lines"), list):
            continue
        canonical = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        estimate_candidates.setdefault(canonical, value)
    if len(estimate_candidates) == 1:
        return next(iter(estimate_candidates.values()))
    if len(estimate_candidates) > 1:
        raise ValueError("estimate proposal contains multiple JSON objects")

    # Preserve the strict downstream validation error for a single object that
    # is valid JSON but does not implement the estimate proposal schema.
    fallback_candidates: dict[str, dict[str, Any]] = {}
    for raw in exact_objects or embedded_objects:
        value = _unwrapped_estimate_object(raw)
        if value is None:
            continue
        canonical = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        fallback_candidates.setdefault(canonical, value)
    if len(fallback_candidates) == 1:
        return next(iter(fallback_candidates.values()))
    if len(fallback_candidates) > 1:
        raise ValueError("estimate proposal contains multiple JSON objects")
    raise ValueError("estimate proposal is not a JSON object")


def estimate_spec_from_provider_response(
    response_text: str,
    *,
    requested_region: str | None = None,
) -> EstimateSpec:
    """Normalize a model proposal into the strict editable estimate contract.

    Model-supplied totals are deliberately ignored.  Unknown or unreferenced
    price provenance is downgraded to an explicit assumption.
    """

    if len(response_text.encode("utf-8")) > MAX_PROVIDER_ESTIMATE_RESPONSE_BYTES:
        raise ValueError(
            f"estimate proposal exceeds {MAX_PROVIDER_ESTIMATE_RESPONSE_BYTES} UTF-8 bytes"
        )
    value = _provider_json_object(response_text)
    raw_lines = value.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        raise ValueError("estimate proposal requires at least one line")
    if len(raw_lines) > MAX_PROVIDER_ESTIMATE_LINES:
        raise ValueError(
            f"estimate proposal exceeds {MAX_PROVIDER_ESTIMATE_LINES} consolidated lines"
        )
    lines: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_lines, start=1):
        if not isinstance(raw, dict):
            raise ValueError("estimate proposal lines must be objects")
        raw_provenance_value = raw.get("provenance")
        raw_provenance = (
            raw_provenance_value
            if isinstance(raw_provenance_value, dict)
            else {"source": raw_provenance_value}
            if isinstance(raw_provenance_value, str)
            else {}
        )
        source = str(raw_provenance.get("source") or "assumption").strip().lower()
        source_ref = raw_provenance.get("source_ref")
        if source not in _PROVENANCE_SOURCES:
            source = "assumption"
            source_ref = "Источник не подтверждён; требуется проверка"
        if source in {"catalog", "contract", "supplier", "measurement"} and not source_ref:
            source = "assumption"
            source_ref = "Цена предложена моделью без подтверждённого источника"
        unit_price = raw.get("unit_price_minor")
        if isinstance(unit_price, str):
            compact_price = re.sub(r"[\s_\u00a0\u202f]", "", unit_price)
            if compact_price.isdigit():
                unit_price = int(compact_price)
        if not isinstance(unit_price, int) or isinstance(unit_price, bool):
            raise ValueError("estimate unit_price_minor must be an integer")
        category = str(raw.get("category") or raw.get("type") or "other").strip().lower()
        category = _CATEGORY_ALIASES.get(category, category)
        if category not in _CATEGORIES:
            category = "other"
        line_id = str(raw.get("id") or f"line-{index}").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{1,199}", line_id):
            line_id = f"line-{index}"
        provenance: dict[str, Any] = {"source": source}
        if source_ref:
            provenance["source_ref"] = str(source_ref)[:500]
        captured_at = raw_provenance.get("captured_at")
        if isinstance(captured_at, str) and captured_at.strip():
            provenance["captured_at"] = captured_at.strip()[:80]
        lines.append({
            "id": line_id,
            "section": str(raw.get("section") or "Основные работы")[:200],
            "description": str(raw.get("description") or raw.get("name") or "").strip(),
            "category": category,
            "unit": str(raw.get("unit") or "шт").strip(),
            "quantity": str(raw.get("quantity") or "").replace(",", "."),
            "unit_price_minor": unit_price,
            "provenance": provenance,
        })
    assumptions = value.get("assumptions") if isinstance(value.get("assumptions"), list) else []
    if any(line["provenance"]["source"] == "assumption" for line in lines) and not assumptions:
        assumptions = ["Ориентировочные цены требуют проверки по региону и дате закупки."]
    questions = value.get("questions") if isinstance(value.get("questions"), list) else []
    return EstimateSpec.model_validate({
        "title": str(value.get("title") or "Смета").strip(),
        "currency": str(value.get("currency") or "RUB").strip().upper(),
        "minor_unit": _normalized_minor_unit(value.get("minor_unit", 2)),
        "region": str(value.get("region") or requested_region or "Не указан").strip(),
        "client_name": _normalized_client_name(value),
        "object_name": _normalized_object_field(value, "name"),
        "object_address": _normalized_object_field(value, "address"),
        "source_summary": str(
            value.get("source_summary")
            or "Цены предложены как ориентировочные и требуют проверки"
        ).strip(),
        "assumptions": [str(item).strip() for item in assumptions if str(item).strip()][:12],
        "questions": [str(item).strip() for item in questions if str(item).strip()][:12],
        "lines": lines,
        "overhead_rate_bps": value.get("overhead_rate_bps", 0),
        "tax_rate_bps": value.get("tax_rate_bps", 0),
    })


_HOUSE_AREA = re.compile(
    r"(?<![\d.,])(?P<area>\d{2,4}(?:[.,]\d{1,2})?)\s*"
    r"(?:м\s*(?:²|2)|кв\.?\s*м(?:етр(?:а|ов)?)?)\b",
    re.IGNORECASE,
)


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _house_area_from_brief(brief: str) -> Decimal | None:
    match = _HOUSE_AREA.search(brief)
    if match is None:
        return None
    try:
        area = Decimal(match.group("area").replace(",", "."))
    except InvalidOperation:
        return None
    if area < Decimal("20") or area > Decimal("5000"):
        return None
    return area.quantize(Decimal("0.01"))


def _is_house_construction_brief(brief: str) -> bool:
    normalized = brief.casefold().replace("ё", "е")
    construction = "дом" in normalized and any(
        marker in normalized
        for marker in ("строитель", "постро", "возвед")
    )
    one_storey = (
        "одноэтаж" in normalized
        or bool(re.search(r"\b1\s*[-–—]?\s*этаж", normalized))
        or "один этаж" in normalized
    )
    return construction and one_storey


def _fallback_region(task: EstimateVerticalTask) -> str:
    if task.region:
        return task.region
    brief = str(task.brief or "").casefold().replace("ё", "е")
    if "лениногорск" in brief and "татарстан" in brief:
        return "Республика Татарстан, Лениногорск"
    if "лениногорск" in brief:
        return "Лениногорск"
    if "татарстан" in brief:
        return "Республика Татарстан"
    return "Регион не структурирован; требуется уточнение"


def _display_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f")


def _assumption_house_spec(task: EstimateVerticalTask) -> EstimateSpec | None:
    """Build a bounded editable house estimate when providers are exhausted.

    This is deliberately a coarse local template, not a price book.  Every
    quantity and price is marked as an assumption and the contract explicitly
    excludes normative or supplier provenance.  The narrow recognizer avoids
    pretending that an arbitrary estimate brief can be completed locally.
    """

    brief = str(task.brief or "")
    area = _house_area_from_brief(brief)
    if area is None or not _is_house_construction_brief(brief):
        return None
    region = _fallback_region(task)
    roof_area = (area * Decimal("1.25")).quantize(Decimal("0.01"))
    facade_area = (area * Decimal("1.60")).quantize(Decimal("0.01"))
    earth_volume = (area * Decimal("0.55")).quantize(Decimal("0.01"))
    foundation_volume = (area * Decimal("0.35")).quantize(Decimal("0.01"))
    price_note = (
        "Непроверенное допущение локального укрупнённого шаблона Kolibri; "
        "не является нормативной или коммерческой расценкой"
    )

    # Prices are integer kopecks.  They are intentionally consolidated so the
    # result stays editable and useful without masquerading as a detailed
    # resource estimate or a supplier quotation.
    raw_lines: list[tuple[str, str, str, str, str, Decimal, int]] = [
        ("prep-design", "Подготовка и проектирование", "Эскизный и рабочий проект", "service", "компл.", Decimal("1"), 25_000_000),
        ("prep-survey", "Подготовка и проектирование", "Инженерные изыскания и вынос осей", "service", "компл.", Decimal("1"), 12_000_000),
        ("foundation-earth", "Земляные работы и фундамент", "Разработка и перемещение грунта", "equipment", "м3", earth_volume, 90_000),
        ("foundation-labor", "Земляные работы и фундамент", "Устройство монолитного фундамента — работы", "labor", "м3", foundation_volume, 850_000),
        ("foundation-material", "Земляные работы и фундамент", "Бетон, арматура, опалубка и гидроизоляция", "material", "м3", foundation_volume, 2_800_000),
        ("shell-walls-labor", "Коробка дома", "Возведение наружных стен и перегородок — работы", "labor", "м2", area, 650_000),
        ("shell-walls-material", "Коробка дома", "Материалы наружных стен и перегородок", "material", "м2", area, 1_800_000),
        ("roof-labor", "Кровля", "Устройство стропильной системы и кровли — работы", "labor", "м2", roof_area, 300_000),
        ("roof-material", "Кровля", "Стропильные, изоляционные и кровельные материалы", "material", "м2", roof_area, 900_000),
        ("openings-material", "Окна и двери", "Окна и наружные двери — комплект", "material", "компл.", Decimal("1"), 85_000_000),
        ("openings-labor", "Окна и двери", "Монтаж окон и наружных дверей", "labor", "компл.", Decimal("1"), 18_000_000),
        ("facade-labor", "Фасад", "Утепление и отделка фасада — работы", "labor", "м2", facade_area, 200_000),
        ("facade-material", "Фасад", "Утеплитель и фасадные материалы", "material", "м2", facade_area, 350_000),
        ("electric-labor", "Инженерные системы", "Внутренняя электрика — работы", "labor", "м2", area, 180_000),
        ("electric-material", "Инженерные системы", "Кабель, щитовая автоматика и электроустановочные материалы", "material", "м2", area, 220_000),
        ("plumbing-labor", "Инженерные системы", "Водоснабжение и канализация — работы", "labor", "м2", area, 160_000),
        ("plumbing-material", "Инженерные системы", "Трубы, коллекторы и базовое сантехническое оборудование", "material", "м2", area, 240_000),
        ("heating-equipment", "Инженерные системы", "Отопление и базовая вентиляция — оборудование", "equipment", "компл.", Decimal("1"), 90_000_000),
        ("heating-labor", "Инженерные системы", "Монтаж и пусконаладка отопления", "labor", "компл.", Decimal("1"), 30_000_000),
        ("finish-labor", "Внутренняя отделка", "Базовая внутренняя отделка — работы", "labor", "м2", area, 550_000),
        ("finish-material", "Внутренняя отделка", "Базовые отделочные материалы", "material", "м2", area, 350_000),
        ("logistics-delivery", "Логистика", "Доставка строительных материалов", "service", "компл.", Decimal("1"), 35_000_000),
        ("logistics-waste", "Логистика", "Контейнеры и вывоз строительных отходов", "service", "компл.", Decimal("1"), 12_000_000),
    ]
    lines = [{
        "id": line_id,
        "section": section,
        "description": description,
        "category": category,
        "unit": unit,
        "quantity": _display_decimal(quantity),
        "unit_price_minor": unit_price_minor,
        "provenance": {"source": "assumption", "source_ref": price_note},
    } for line_id, section, description, category, unit, quantity, unit_price_minor in raw_lines]
    return EstimateSpec.model_validate({
        "title": f"Предварительная смета на строительство одноэтажного дома {_display_decimal(area)} м²",
        "currency": "RUB",
        "minor_unit": 2,
        "region": region,
        "object_name": f"Одноэтажный жилой дом {_display_decimal(area)} м²",
        "object_address": region,
        "source_summary": (
            "Локальный укрупнённый резервный шаблон Kolibri. Все цены и объёмы — "
            "непроверенные допущения; перед договором требуется проект, ведомость объёмов, "
            f"геология и коммерческие предложения по региону строительства ({region})."
        ),
        "assumptions": [
            f"Общая площадь дома принята равной {_display_decimal(area)} м², этажность — один этаж.",
            "Схема фундамента, конструкция стен, кровли и инженерии не заданы и приняты укрупнённо.",
            "Площадь кровли принята как 1,25 площади дома, фасада — как 1,60 площади дома.",
            "Цены не получены из ФЕР/ТЕР, поставщиков или договоров и требуют региональной проверки.",
            "Накладные расходы приняты 7%; налоговый режим и НДС в расчёт не включены.",
            "Покупка участка, внешние сети за границей участка, благоустройство, мебель и техника исключены.",
            "Резерв на изменение цен и непредвиденные работы отдельно не включён.",
        ],
        "questions": [
            "Какой фундамент требуется по геологии участка?",
            "Из какого материала должны быть наружные стены?",
            "Какой уровень готовности нужен: тёплый контур, предчистовая или под ключ?",
            "Где находятся точки подключения воды, канализации, электричества и газа?",
            "Нужно ли включить внешние сети, септик/скважину и благоустройство?",
            "Какой налоговый режим подрядчика применять?",
        ],
        "lines": lines,
        "overhead_rate_bps": 700,
        "tax_rate_bps": 0,
    })


def _estimate_engine_proof(
    *,
    input_facts_sha256: str,
    spec_sha256: str,
    calculation_sha256: str,
    fallback_reason: str,
) -> dict[str, Any]:
    proof = {
        "schema_version": ESTIMATE_FALLBACK_PROOF_SCHEMA,
        "engine": ESTIMATE_FALLBACK_ENGINE,
        "mode": "assumption_template",
        "input_facts_sha256": input_facts_sha256,
        "spec_sha256": spec_sha256,
        "calculation_sha256": calculation_sha256,
        "fallback_reason": fallback_reason,
    }
    return {**proof, "binding_sha256": _canonical_sha256(proof)}


def build_deterministic_estimate_fallback(
    task: VerticalTask,
    *,
    reason: str = "provider_unavailable",
) -> dict[str, Any] | None:
    """Return a content-bound local estimate only for a supported estimate.

    The provider gateway must be attempted before this helper is called.  The
    returned envelope does not claim provider verification; it binds the
    narrow assumption engine, bounded extracted input facts, editable
    specification and exact deterministic monetary calculation with
    independent SHA-256 digests.
    """

    if not isinstance(task, EstimateVerticalTask) or task.spec is not None:
        return None
    reason = str(reason or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{1,80}", reason):
        reason = "provider_unavailable"
    spec = _assumption_house_spec(task)
    if spec is None:
        return None
    calculation = deterministic_estimate(spec)
    area = _house_area_from_brief(str(task.brief or ""))
    if area is None:  # defensive: the template builder already requires it
        return None
    input_facts = {
        "object_type": "one_storey_house",
        "storeys": 1,
        "area_m2": _display_decimal(area),
        "region": spec.region,
        "requested_artifacts": requested_deliverables(task),
    }
    input_facts_sha256 = _canonical_sha256(input_facts)
    spec_sha256 = _canonical_sha256(spec.model_dump(mode="json"))
    proof = _estimate_engine_proof(
        input_facts_sha256=input_facts_sha256,
        spec_sha256=spec_sha256,
        calculation_sha256=str(calculation["calculation_sha256"]),
        fallback_reason=reason,
    )
    requested = requested_deliverables(task)
    return {
        "schema_version": VERTICAL_TASK_SCHEMA,
        "intent": "estimate",
        "status": "incomplete" if requested else "completed",
        "execution": {
            "status": "completed",
            "model": "kolibri",
            "provider_verified": False,
            "provider_status": "failed",
            "engine_verified": True,
            "engine": ESTIMATE_FALLBACK_ENGINE,
            "engine_binding_sha256": proof["binding_sha256"],
            "fallback_reason": reason,
        },
        "result": {
            "type": "deterministic_estimate",
            "estimate": spec.model_dump(mode="json"),
            "calculation": calculation,
            "generation": {**proof, "input_facts": input_facts},
        },
        "artifacts": [],
        "artifact_delivery": {
            "required": bool(requested),
            "status": "not_required" if not requested else "not_materialized",
            "requested": requested,
            "delivered": [],
            "missing": requested,
            "count": 0,
        },
    }


def verified_deterministic_estimate_fallback(task: dict[str, Any]) -> bool:
    """Recompute and verify every local fallback binding before persistence."""

    if task.get("intent") != "estimate" or task.get("schema_version") != VERTICAL_TASK_SCHEMA:
        return False
    execution = task.get("execution") if isinstance(task.get("execution"), dict) else {}
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    proof = result.get("generation") if isinstance(result.get("generation"), dict) else {}
    if not (
        execution.get("status") == "completed"
        and execution.get("model") == "kolibri"
        and execution.get("provider_verified") is False
        and execution.get("provider_status") == "failed"
        and execution.get("engine_verified") is True
        and execution.get("engine") == ESTIMATE_FALLBACK_ENGINE
        and proof.get("schema_version") == ESTIMATE_FALLBACK_PROOF_SCHEMA
        and proof.get("engine") == ESTIMATE_FALLBACK_ENGINE
        and proof.get("mode") == "assumption_template"
    ):
        return False
    try:
        spec = EstimateSpec.model_validate(result.get("estimate"))
    except (TypeError, ValueError):
        return False
    if not spec.lines or any(line.provenance.source != "assumption" for line in spec.lines):
        return False
    calculation = result.get("calculation")
    if not isinstance(calculation, dict) or deterministic_estimate(spec) != calculation:
        return False
    input_facts = proof.get("input_facts") if isinstance(proof.get("input_facts"), dict) else {}
    if set(input_facts) != {
        "object_type", "storeys", "area_m2", "region", "requested_artifacts",
    }:
        return False
    if input_facts.get("object_type") != "one_storey_house" or input_facts.get("storeys") != 1:
        return False
    try:
        input_area = Decimal(str(input_facts.get("area_m2")))
    except InvalidOperation:
        return False
    if input_area < Decimal("20") or input_area > Decimal("5000"):
        return False
    if input_facts.get("region") != spec.region:
        return False
    requested_artifacts = input_facts.get("requested_artifacts")
    if not (
        isinstance(requested_artifacts, list)
        and len(requested_artifacts) <= 4
        and all(item in {"pdf", "pdf-x", "xlsx", "docx"} for item in requested_artifacts)
    ):
        return False
    delivery = task.get("artifact_delivery") if isinstance(task.get("artifact_delivery"), dict) else {}
    if delivery.get("requested") != requested_artifacts:
        return False
    input_facts_sha256 = str(proof.get("input_facts_sha256") or "").lower()
    spec_sha256 = str(proof.get("spec_sha256") or "").lower()
    calculation_sha256 = str(proof.get("calculation_sha256") or "").lower()
    fallback_reason = str(proof.get("fallback_reason") or "")
    if not re.fullmatch(r"[a-z0-9_]{1,80}", fallback_reason):
        return False
    if execution.get("fallback_reason") != fallback_reason:
        return False
    if not all(_valid_digest(value) for value in (
        input_facts_sha256, spec_sha256, calculation_sha256,
    )):
        return False
    if input_facts_sha256 != _canonical_sha256(input_facts):
        return False
    if spec_sha256 != _canonical_sha256(spec.model_dump(mode="json")):
        return False
    if calculation_sha256 != calculation.get("calculation_sha256"):
        return False
    expected = _estimate_engine_proof(
        input_facts_sha256=input_facts_sha256,
        spec_sha256=spec_sha256,
        calculation_sha256=calculation_sha256,
        fallback_reason=fallback_reason,
    )
    binding_sha256 = str(proof.get("binding_sha256") or "").lower()
    return bool(
        _valid_digest(binding_sha256)
        and binding_sha256 == expected["binding_sha256"]
        and execution.get("engine_binding_sha256") == binding_sha256
    )


def deterministic_estimate_fallback_verification(task: dict[str, Any]) -> dict[str, Any]:
    if not verified_deterministic_estimate_fallback(task):
        raise ValueError("deterministic estimate fallback verification failed")
    result = task["result"]
    proof = result["generation"]
    return {
        "status": "passed",
        "type": "deterministic_estimate_engine",
        "engine": ESTIMATE_FALLBACK_ENGINE,
        "provider_verified": False,
        "spec_sha256": proof["spec_sha256"],
        "calculation_sha256": proof["calculation_sha256"],
        "binding_sha256": proof["binding_sha256"],
    }


def deterministic_estimate_fallback_text(task: dict[str, Any]) -> str:
    if not verified_deterministic_estimate_fallback(task):
        raise ValueError("deterministic estimate fallback verification failed")
    result = task["result"]
    estimate = result["estimate"]
    calculation = result["calculation"]
    total_minor = int(calculation["totals"]["grand_total_minor"])
    minor_unit = int(calculation["minor_unit"])
    amount = Decimal(total_minor) / (Decimal(10) ** minor_unit)
    formatted = f"{amount:,.{minor_unit}f}".replace(",", " ").replace(".", ",")
    delivery = task.get("artifact_delivery") if isinstance(task.get("artifact_delivery"), dict) else {}
    pdf_ready = "pdf" in set(delivery.get("delivered") or [])
    return (
        f"Подготовлена предварительная редактируемая смета «{estimate['title']}»: "
        f"{len(estimate['lines'])} позиций, ориентировочный итог {formatted} RUB. "
        "Все цены и объёмы отмечены как непроверенные допущения; итог рассчитан "
        "детерминированно, без расчёта суммы моделью. "
        + ("PDF сформирован и привязан к этой версии сметы." if pdf_ready else "PDF пока не материализован.")
    )


def _routing(result: dict[str, Any]) -> dict[str, Any]:
    technical = result.get("technical") if isinstance(result.get("technical"), dict) else {}
    routing = technical.get("provider_routing")
    return routing if isinstance(routing, dict) else {}


def _valid_digest(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value.lower()))


def _verified_provider_binding(
    routing: dict[str, Any], response_text: str,
) -> tuple[bool, dict[str, Any]]:
    evidence = routing.get("evidence") if isinstance(routing.get("evidence"), list) else []
    response_bytes = response_text.encode("utf-8")
    response_sha = hashlib.sha256(response_bytes).hexdigest() if response_text else ""
    provider = next((
        item for item in evidence
        if isinstance(item, dict)
        and item.get("type") == "provider_execution"
        and item.get("exit_code") == 0
        and item.get("output_sha256") == response_sha
        and item.get("output_bytes") == len(response_bytes)
        and len(response_bytes) > 0
    ), None)
    verifier = next((
        item for item in evidence
        if isinstance(item, dict)
        and item.get("type") == "deterministic_verifier"
        and item.get("verdict") == "passed"
        and _valid_digest(item.get("binding_sha256"))
    ), None)
    return bool(provider and verifier), {
        "output_sha256": provider.get("output_sha256") if provider else None,
        "verifier_binding_sha256": verifier.get("binding_sha256") if verifier else None,
    }


def verified_artifact_refs(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only artifact references backed by explicit materialization proof.

    Provider JSONL may mention a path while planning.  A path-like string is not
    an artifact.  The gateway must also provide an ``artifact_materialization``
    evidence record with matching content hash, byte size, deliverable type and
    binding hash before this public API exposes the reference.
    """

    routing = _routing(result)
    response_text = str(result.get("response") or "")
    provider_verified, _ = _verified_provider_binding(routing, response_text)
    if not provider_verified:
        return []
    refs = routing.get("artifact_refs") if isinstance(routing.get("artifact_refs"), list) else []
    evidence = routing.get("evidence") if isinstance(routing.get("evidence"), list) else []
    proofs = [
        item for item in evidence
        if isinstance(item, dict)
        and item.get("type") == "artifact_materialization"
        and item.get("verdict") == "passed"
        and _valid_digest(item.get("reference_sha256"))
        and _valid_digest(item.get("content_sha256"))
        and _valid_digest(item.get("binding_sha256"))
        and isinstance(item.get("size_bytes"), int)
        and item["size_bytes"] >= 0
        and isinstance(item.get("deliverable_type"), str)
        and bool(item["deliverable_type"].strip())
    ]
    verified: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        reference_sha = str(ref.get("reference_sha256") or "").lower()
        content_sha = str(ref.get("content_sha256") or "").lower()
        size_bytes = ref.get("size_bytes")
        if not (_valid_digest(reference_sha) and _valid_digest(content_sha)):
            continue
        if not isinstance(size_bytes, int) or size_bytes < 0:
            continue
        proof = next((
            item for item in proofs
            if str(item.get("reference_sha256") or "").lower() == reference_sha
            and str(item.get("content_sha256") or "").lower() == content_sha
            and item.get("size_bytes") == size_bytes
        ), None)
        if proof is None or reference_sha in seen:
            continue
        seen.add(reference_sha)
        safe_ref = {
            key: ref[key]
            for key in ("kind", "name", "locator", "origin", "media_type")
            if isinstance(ref.get(key), str) and ref.get(key)
        }
        safe_ref.update({
            "reference_sha256": reference_sha,
            "content_sha256": content_sha,
            "size_bytes": size_bytes,
            "deliverable_type": proof["deliverable_type"],
            "evidence_binding_sha256": proof["binding_sha256"],
            "status": "materialized",
        })
        verified.append(safe_ref)
    return verified


def build_vertical_result(
    task: VerticalTask,
    provider_result: dict[str, Any],
    calculation: dict[str, Any] | None,
) -> dict[str, Any]:
    routing = _routing(provider_result)
    response_text = str(provider_result.get("response") or "")
    provider_verified, provider_binding = _verified_provider_binding(routing, response_text)
    artifacts = verified_artifact_refs(provider_result)
    estimate_spec: EstimateSpec | None = task.spec if isinstance(task, EstimateVerticalTask) else None
    estimate_error: str | None = None
    if isinstance(task, EstimateVerticalTask) and estimate_spec is None and provider_verified:
        try:
            estimate_spec = estimate_spec_from_provider_response(
                response_text,
                requested_region=task.region,
            )
            calculation = deterministic_estimate(estimate_spec)
        except (TypeError, ValueError, json.JSONDecodeError):
            estimate_error = "estimate_proposal_invalid"

    requested = requested_deliverables(task)
    delivered = {str(item.get("deliverable_type") or "") for item in artifacts}
    missing = [item for item in requested if item not in delivered]
    artifact_required = bool(requested)
    typed_result_valid = not isinstance(task, EstimateVerticalTask) or (
        estimate_spec is not None and calculation is not None
    )
    execution_status = (
        "completed" if provider_verified and response_text and typed_result_valid else "failed"
    )
    status = (
        "completed"
        if execution_status == "completed" and not missing
        else "incomplete" if execution_status == "completed" else "failed"
    )
    if isinstance(task, EstimateVerticalTask):
        result_payload: dict[str, Any] | None = (
            {
                "type": "deterministic_estimate",
                "estimate": estimate_spec.model_dump(mode="json"),
                "calculation": calculation,
            }
            if typed_result_valid and estimate_spec is not None
            else None
        )
    else:
        result_payload = {
            "type": "verified_provider_response",
            "text": response_text,
        }
    return {
        "schema_version": VERTICAL_TASK_SCHEMA,
        "intent": task.intent,
        "status": status,
        "execution": {
            "status": execution_status,
            "model": "kolibri",
            "provider_verified": provider_verified,
            **({"reason": estimate_error} if estimate_error else {}),
            **provider_binding,
        },
        "result": result_payload,
        "artifacts": artifacts,
        "artifact_delivery": {
            "required": artifact_required,
            "status": (
                "not_required" if not artifact_required
                else "materialized" if not missing
                else "not_materialized"
            ),
            "requested": requested,
            "delivered": sorted(delivered),
            "missing": missing,
            "count": len(artifacts),
        },
    }


def failed_vertical_result(task: VerticalTask, reason: str) -> dict[str, Any]:
    return {
        "schema_version": VERTICAL_TASK_SCHEMA,
        "intent": task.intent,
        "status": "failed",
        "execution": {
            "status": "failed",
            "model": "kolibri",
            "provider_verified": False,
            "reason": reason,
        },
        "result": None,
        "artifacts": [],
        "artifact_delivery": {
            "required": bool(requested_deliverables(task)),
            "status": "not_materialized",
            "requested": requested_deliverables(task),
            "delivered": [],
            "missing": requested_deliverables(task),
            "count": 0,
        },
    }
