from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Annotated, Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


DECIMAL_TEXT = re.compile(r"^(?:0|[1-9]\d{0,11})(?:\.\d{1,6})?$")
MONEY_TEXT = re.compile(r"^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$")
ROW_ID = re.compile(r"^row_[A-Za-z0-9._~-]{8,96}$")
MONEY_QUANTUM = Decimal("0.01")
EstimateLineKind = Literal[
    "work",
    "material",
    "equipment",
    "service",
    "overhead",
    "tax",
    "contingency",
]
PriceSourceType = Literal["fgis_cs", "supplier_offer"]
EstimateLifecycleStatus = Literal[
    "draft", "needs_input", "calculating", "ready", "failed"
]
ESTIMATE_LIFECYCLE_STATUSES = frozenset(
    {"draft", "needs_input", "calculating", "ready", "failed"}
)


class EstimateModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


ShortText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
]
BasisText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


class GeneratedQuantityFormula(EstimateModel):
    op: Literal["variable", "constant", "multiply", "add", "divide", "ceil"]
    name: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._~-]{0,159}$",
    )
    value: str | GeneratedQuantityFormula | None = None
    unit: str | None = Field(default=None, max_length=32)
    items: list[GeneratedQuantityFormula] = Field(
        default_factory=list,
        max_length=12,
    )
    numerator: GeneratedQuantityFormula | None = None
    denominator: GeneratedQuantityFormula | None = None

    @model_validator(mode="after")
    def validate_formula_shape(self) -> "GeneratedQuantityFormula":
        if self.op == "variable" and self.name is not None:
            return self
        if (
            self.op == "constant"
            and isinstance(self.value, str)
            and DECIMAL_TEXT.fullmatch(self.value) is not None
            and self.unit
        ):
            return self
        if self.op in {"multiply", "add"} and 2 <= len(self.items) <= 12:
            return self
        if self.op == "divide" and self.numerator and self.denominator:
            return self
        if self.op == "ceil" and isinstance(self.value, GeneratedQuantityFormula):
            return self
        raise ValueError(f"invalid {self.op} quantity formula")


class GeneratedProjectVariable(EstimateModel):
    value: str = Field(pattern=DECIMAL_TEXT.pattern)
    unit: str = Field(min_length=1, max_length=32)
    basis: BasisText


class GeneratedEstimateRow(EstimateModel):
    id: str | None = Field(default=None, pattern=ROW_ID.pattern)
    section: str = Field(min_length=1, max_length=120)
    kind: EstimateLineKind
    description: ShortText
    unit: str = Field(min_length=1, max_length=32)
    quantity: str = Field(pattern=DECIMAL_TEXT.pattern)
    unit_price: str = Field(alias="unitPrice", pattern=MONEY_TEXT.pattern)
    quantity_basis: BasisText = Field(alias="quantityBasis")
    price_basis: BasisText = Field(alias="priceBasis")
    wbs_path: str | None = Field(default=None, alias="wbsPath", max_length=500)
    specification: str | None = Field(default=None, max_length=500)
    quantity_formula: str | None = Field(
        default=None,
        alias="quantityFormula",
        max_length=500,
    )
    technology_card_version: str | None = Field(
        default=None,
        alias="technologyCardVersion",
        max_length=160,
    )
    operation_id: str | None = Field(default=None, alias="operationId", max_length=160)
    resource_id: str | None = Field(default=None, alias="resourceId", max_length=160)
    evidence_id: str | None = Field(default=None, alias="evidenceId", max_length=160)
    line_confidence: Literal["missing", "preliminary", "source_backed", "verified"] = Field(
        default="preliminary",
        alias="lineConfidence",
    )


class GeneratedEstimateProposal(EstimateModel):
    title: str = Field(min_length=1, max_length=240)
    region: str = Field(min_length=1, max_length=160)
    assumptions: list[ShortText] = Field(min_length=1, max_length=20)
    rows: list[GeneratedEstimateRow] = Field(min_length=1)


class GeneratedEstimatePlan(EstimateModel):
    title: str = Field(min_length=1, max_length=240)
    region: str = Field(min_length=1, max_length=160)
    currency: Literal["RUB"] = "RUB"
    object_type: str = Field(default="Не определён", alias="objectType", max_length=200)
    purpose: str = Field(default="Не определено", max_length=300)
    assumptions: list[ShortText] = Field(min_length=1, max_length=20)
    sections: list[str] = Field(min_length=1)
    facts: list[ShortText] = Field(default_factory=list)
    variables: dict[str, GeneratedProjectVariable] = Field(default_factory=dict)
    scope_exclusions: list[ShortText] = Field(default_factory=list, alias="scopeExclusions")
    zones: list[ShortText] = Field(default_factory=list)
    systems: list[ShortText] = Field(default_factory=list)
    quality_requirements: list[ShortText] = Field(
        default_factory=list,
        alias="qualityRequirements",
    )
    schedule_constraints: list[ShortText] = Field(
        default_factory=list,
        alias="scheduleConstraints",
    )
    commercial_terms: list[ShortText] = Field(
        default_factory=list,
        alias="commercialTerms",
    )
    blocking_questions: list[ShortText] = Field(
        default_factory=list,
        alias="blockingQuestions",
    )


class GeneratedSourceEvidence(EstimateModel):
    source_type: Literal[
        "user_provided",
        "approved_catalog",
        "official_reference",
        "supplier_offer",
        "market_aggregate",
        "ai_preliminary",
        "missing",
    ] = Field(alias="sourceType")
    source_reference: str = Field(alias="sourceReference", min_length=1, max_length=300)
    source_url: str | None = Field(default=None, alias="sourceUrl", max_length=2_000)
    observed_at: str | None = Field(default=None, alias="observedAt", max_length=64)
    region: str = Field(min_length=1, max_length=160)
    unit: str = Field(min_length=1, max_length=32)
    vat_treatment: Literal["included", "excluded", "not_specified", "not_applicable"] = Field(
        alias="vatTreatment"
    )
    delivery_included: bool = Field(alias="deliveryIncluded")
    valid_until: str | None = Field(default=None, alias="validUntil", max_length=64)
    snapshot_hash: str | None = Field(
        default=None,
        alias="snapshotHash",
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    confidence: Literal["missing", "preliminary", "source_backed", "verified"]


class GeneratedTechnologyResource(EstimateModel):
    resource_id: str = Field(
        alias="resourceId",
        pattern=r"^resource_[A-Za-z0-9._~-]{4,96}$",
    )
    kind: EstimateLineKind
    description: ShortText
    specification: str = Field(default="", max_length=500)
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    quantity: str | None = Field(default=None, pattern=DECIMAL_TEXT.pattern)
    quantity_formula: GeneratedQuantityFormula | None = Field(
        default=None,
        alias="quantityFormula",
    )
    input_provenance: list[ShortText] = Field(
        default_factory=list,
        alias="inputProvenance",
    )
    quantity_basis: BasisText = Field(alias="quantityBasis")
    proposed_unit_price: str = Field(
        default="0.00",
        alias="proposedUnitPrice",
        pattern=MONEY_TEXT.pattern,
    )
    price_basis: BasisText = Field(alias="priceBasis")
    price_evidence_id: str | None = Field(
        default=None,
        alias="priceEvidenceId",
        max_length=160,
    )
    waste_percent: str = Field(default="0", alias="wastePercent", pattern=DECIMAL_TEXT.pattern)
    rate_percent: str | None = Field(
        default=None,
        alias="ratePercent",
        pattern=DECIMAL_TEXT.pattern,
    )
    base_kinds: list[EstimateLineKind] = Field(
        default_factory=list,
        alias="baseKinds",
    )
    calculation_basis: str = Field(
        default="",
        alias="calculationBasis",
        max_length=500,
    )

    @model_validator(mode="after")
    def validate_resource_shape(self) -> "GeneratedTechnologyResource":
        if self.kind in {"work", "material", "equipment", "service"}:
            if self.unit is None or self.quantity_formula is None:
                raise ValueError("direct resource requires unit and quantityFormula")
            return self
        if (
            self.rate_percent is None
            or not self.base_kinds
            or not self.calculation_basis
        ):
            raise ValueError(
                "adjustment resource requires ratePercent, baseKinds and calculationBasis"
            )
        return self


class GeneratedTechnologyOperation(EstimateModel):
    operation_id: str = Field(
        alias="operationId",
        pattern=r"^operation_[A-Za-z0-9._~-]{4,96}$",
    )
    wbs_code: str = Field(alias="wbsCode", min_length=1, max_length=80)
    section: str = Field(min_length=1, max_length=120)
    zone: str = Field(min_length=1, max_length=120)
    system: str = Field(min_length=1, max_length=120)
    sequence: int = Field(ge=1)
    name: ShortText
    method: BasisText
    unit: str = Field(default="компл.", min_length=1, max_length=32)
    quantity_formula: GeneratedQuantityFormula = Field(alias="quantityFormula")
    quantity_inputs: list[ShortText] = Field(
        default_factory=list,
        alias="quantityInputs",
    )
    predecessors: list[str] = Field(default_factory=list)
    resources: list[GeneratedTechnologyResource] = Field(min_length=1)
    quality_checks: list[ShortText] = Field(default_factory=list, alias="qualityChecks")
    assumptions: list[ShortText] = Field(default_factory=list)
    technical_sources: list[GeneratedSourceEvidence] = Field(
        default_factory=list,
        alias="technicalSources",
    )


class GeneratedEstimateSection(EstimateModel):
    section: str = Field(min_length=1, max_length=120)
    operations: list[GeneratedTechnologyOperation] = Field(min_length=1)
    assumptions: list[ShortText] = Field(default_factory=list)


class GeneratedPriceCandidate(EstimateModel):
    resource_id: str = Field(
        alias="resourceId",
        pattern=r"^resource_[A-Za-z0-9._~-]{4,96}$",
    )
    unit_price: str = Field(alias="unitPrice", pattern=MONEY_TEXT.pattern)
    evidence: GeneratedSourceEvidence


class GeneratedPriceSection(EstimateModel):
    section: str = Field(min_length=1, max_length=120)
    candidates: list[GeneratedPriceCandidate]


class GeneratedReviewIssue(EstimateModel):
    severity: Literal["error", "warning"]
    code: str = Field(min_length=3, max_length=96)
    operation_id: str | None = Field(default=None, alias="operationId", max_length=160)
    resource_id: str | None = Field(default=None, alias="resourceId", max_length=160)
    message: BasisText


class GeneratedEstimateReview(EstimateModel):
    passed: bool
    issues: list[GeneratedReviewIssue]


class EstimateRowInput(EstimateModel):
    id: str = Field(pattern=r"^row_[A-Za-z0-9._~-]{8,96}$")
    section: str = Field(min_length=1, max_length=120)
    kind: EstimateLineKind
    description: ShortText
    unit: str = Field(min_length=1, max_length=32)
    quantity: str = Field(pattern=DECIMAL_TEXT.pattern)
    unit_price: str = Field(alias="unitPrice", pattern=MONEY_TEXT.pattern)
    quantity_basis: BasisText = Field(alias="quantityBasis")
    price_basis: BasisText = Field(alias="priceBasis")
    wbs_path: str | None = Field(default=None, alias="wbsPath", max_length=500)
    specification: str | None = Field(default=None, max_length=500)
    quantity_formula: str | None = Field(
        default=None,
        alias="quantityFormula",
        max_length=500,
    )
    catalog_entry_id: str | None = Field(default=None, alias="catalogEntryId", max_length=160)
    catalog_entry_version: int | None = Field(default=None, alias="catalogEntryVersion", ge=1)
    technology_card_version: str | None = Field(default=None, alias="technologyCardVersion", max_length=160)
    operation_id: str | None = Field(default=None, alias="operationId", max_length=160)
    resource_id: str | None = Field(default=None, alias="resourceId", max_length=160)
    evidence_id: str | None = Field(default=None, alias="evidenceId", max_length=160)
    price_observation_id: str | None = Field(default=None, alias="priceObservationId", max_length=160)
    market_aggregate_id: str | None = Field(default=None, alias="marketAggregateId", max_length=160)
    line_confidence: Literal["missing", "preliminary", "source_backed", "verified"] = Field(
        default="missing", alias="lineConfidence"
    )


class EstimatePatch(EstimateModel):
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=240)
    currency: Literal["RUB"]
    rows: list[EstimateRowInput]


class EstimateRowPageRequest(EstimateModel):
    offset: int = Field(ge=0)
    limit: int = Field(ge=0, le=100)


class EstimateRowsPatch(EstimateModel):
    version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    upsert_rows: list[EstimateRowInput] = Field(
        default_factory=list,
        alias="upsertRows",
        max_length=200,
    )
    delete_row_ids: list[str] = Field(
        default_factory=list,
        alias="deleteRowIds",
        max_length=200,
    )
    return_page: EstimateRowPageRequest = Field(alias="returnPage")

    @model_validator(mode="after")
    def validate_mutations(self) -> "EstimateRowsPatch":
        if self.title is None and not self.upsert_rows and not self.delete_row_ids:
            raise ValueError("estimate row mutation is empty")
        upsert_ids = [row.id for row in self.upsert_rows]
        if len(upsert_ids) != len(set(upsert_ids)):
            raise ValueError("upsert row IDs must be unique")
        delete_ids = list(self.delete_row_ids)
        if any(ROW_ID.fullmatch(row_id) is None for row_id in delete_ids):
            raise ValueError("delete row ID is invalid")
        if len(delete_ids) != len(set(delete_ids)):
            raise ValueError("delete row IDs must be unique")
        if set(upsert_ids).intersection(delete_ids):
            raise ValueError("a row cannot be upserted and deleted together")
        return self


ESTIMATE_PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "minLength": 1, "maxLength": 240},
        "region": {"type": "string", "minLength": 1, "maxLength": 160},
        "assumptions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "items": {"type": "string", "minLength": 1, "maxLength": 300},
        },
        "rows": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "section": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 120,
                    },
                    "kind": {
                        "type": "string",
                        "enum": [
                            "work",
                            "material",
                            "equipment",
                            "service",
                            "overhead",
                            "tax",
                            "contingency",
                        ],
                    },
                    "description": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 300,
                    },
                    "unit": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 32,
                    },
                    "quantity": {
                        "type": "string",
                        "pattern": DECIMAL_TEXT.pattern,
                    },
                    "unitPrice": {
                        "type": "string",
                        "pattern": MONEY_TEXT.pattern,
                    },
                    "quantityBasis": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 500,
                    },
                    "priceBasis": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 500,
                    },
                },
                "required": [
                    "section",
                    "kind",
                    "description",
                    "unit",
                    "quantity",
                    "unitPrice",
                    "quantityBasis",
                    "priceBasis",
                ],
            },
        },
    },
    "required": ["title", "region", "assumptions", "rows"],
}

ESTIMATE_PLAN_SCHEMA: dict[str, Any] = GeneratedEstimatePlan.model_json_schema(
    by_alias=True,
    mode="validation",
)
ESTIMATE_SECTION_SCHEMA: dict[str, Any] = GeneratedEstimateSection.model_json_schema(
    by_alias=True,
    mode="validation",
)
ESTIMATE_PRICE_SECTION_SCHEMA: dict[str, Any] = GeneratedPriceSection.model_json_schema(
    by_alias=True,
    mode="validation",
)
ESTIMATE_REVIEW_SCHEMA: dict[str, Any] = GeneratedEstimateReview.model_json_schema(
    by_alias=True,
    mode="validation",
)


def estimate_proposal_instructions(*, today: str) -> str:
    return f"""
Ты формируешь предварительный редактируемый черновик сметы для Kolibri.
Верни только JSON по переданной schema.

Правила:
- Преврати последний запрос пользователя в подробную смету. Не подгоняй её
  под фиксированное число строк: добавь столько позиций, сколько требуется
  для полного и проверяемого описания заявленного состава работ.
- Каждая материально отличающаяся операция или ресурс должна быть отдельной
  строкой. Не объединяй работу с материалом в одной позиции.
- Разделяй работы, материалы, оборудование и услуги по kind и группируй их
  в понятные технологические section.
- Когда применимо, отдельно учитывай подготовку и защиту, демонтаж, черновые
  и чистовые операции, инженерные сети, пусконаладку, доставку, подъём,
  аренду техники и инструмента, вывоз и утилизацию отходов.
- Не добавляй строки ради количества и не дублируй позиции. Накладные расходы,
  налоги и резерв не скрывай внутри цен: при отсутствии правил расчёта укажи
  их как недостающие условия в assumptions.
- Не вычисляй итоги: сервер Kolibri выполнит всю арифметику Decimal.
- Не выдавай цену за проверенный рыночный факт. Если пользователь не дал цену,
  поставь разумную предварительную оценку в рублях и явно напиши в priceBasis:
  "Предварительная оценка AI на {today}; проверить по прайсам поставщиков".
- В quantityBasis укажи, что взято из запроса, что рассчитано из него и что
  является условием расчёта. Не скрывай выведенные площади, запасы и коэффициенты.
- В assumptions перечисли все недостающие исходные данные и границы расчёта.
  Черновик должен быть полезным уже сейчас, а не пустым.
- region заполни регионом пользователя либо строкой "Регион не указан".
- Используй только неотрицательные decimal-строки с точкой: "6", "12.5",
  "3500.00". Не добавляй markdown и пояснения вне JSON.
""".strip()


def estimate_plan_instructions() -> str:
    return """
Ты планируешь полную ресурсную смету строительного объекта Kolibri.
Верни только JSON по переданной schema.

Сформируй sections как полный набор неперекрывающихся самостоятельных
верхнеуровневых секционных контуров. Каждый запрошенный вид работ должен
относиться ровно к одному контуру. Не выдавай одновременно родительский
раздел и входящие в него дочерние WBS-узлы: выбери либо общий контур, либо
набор самостоятельных дочерних контуров, но не оба уровня сразу. Sections —
это границы параллельной работы секционных агентов, а не полное дерево WBS.
Детальную декомпозицию на этапы, этажи, зоны, операции, подоперации и ресурсы
выполняют секционные агенты. Этаж или зона становится отдельным section только
когда это самостоятельный технологический контур, не покрытый другим section.

Не ограничивай количество sections и не объединяй разные самостоятельные
конструктивы или инженерные системы ради краткости. Не задавай и не
подразумевай максимумы для operations, resources или строк будущей сметы.
Для многоэтажного объекта учти подготовку, земляные работы, конструктив,
ограждающие конструкции, фасады, кровлю, внутренние работы, все инженерные
системы, вертикальный транспорт, наружные сети, благоустройство, временные
работы, испытания, пусконаладку, исполнительную документацию и логистику,
когда они относятся к запросу. Не создавай дублирующие разделы и не теряй
состав работ ради укрупнения контуров.

Одновременно сформируй ProjectCase: в facts перечисли только подтверждённые
входные данные, в assumptions — явные условия расчёта, в scopeExclusions —
явные исключения, в zones и systems — фактическую структуру объекта. Не
выдумывай отсутствующие проектные данные и не рассчитывай стоимость. Заполни
objectType, purpose, qualityRequirements, scheduleConstraints и
commercialTerms, когда они известны. Неблокирующие пробелы переноси в
assumptions. В blockingQuestions включай только вопросы, без ответа на которые
невозможно получить даже честный предварительный расчёт. Все числовые входы,
которые понадобятся формулам, вынеси в variables под стабильными латинскими
именами; для каждого укажи decimal value, совместимую unit и проверяемый basis.
""".strip()


def estimate_section_instructions(
    *,
    today: str,
    section: str,
    role: str = "technologist",
) -> str:
    role_focus = {
        "technologist": (
            "Сосредоточься на технологической последовательности, методах, "
            "predecessors и контрольных операциях."
        ),
        "quantity_engineer": (
            "Сосредоточься на воспроизводимых формулах количества, входных "
            "величинах, размерностях, зонах и provenance каждого объёма."
        ),
        "resource_normative": (
            "Сосредоточься на полном составе труда, материалов, механизмов и "
            "услуг, нормах расхода, отходах и запасах; не выдумывай нормативы."
        ),
        "technical_research": (
            "Проведи живое исследование применимых технических источников и "
            "сохрани проверяемые URL/идентификаторы, даты и применимость."
        ),
        "logistics": (
            "Сосредоточься на машинах, временных работах, доставке, разгрузке, "
            "подъёме, хранении, вывозе и утилизации."
        ),
    }.get(role, "Сформируй полную проверяемую технологическую карту.")
    return f"""
Ты технолог и инженер объёмов Kolibri. Построй технологическую карту одного
раздела строительного объекта: «{section}».
Верни только JSON по переданной schema.

Твоя специализированная роль: {role}. {role_focus}

Создай исчерпывающую последовательность operations без ограничения количества.
Для каждой операции задай стабильный operationId, WBS-код, зону, систему,
метод, predecessors, контроль качества и все необходимые resources. Работу,
материалы, оборудование и услуги представь разными ресурсами. Учитывай
подготовку, защиту, отходы, механизмы, доставку, подъём, вывоз, испытания и
пусконаладку, когда они технологически нужны. Не создавай дубли и элементы
ради количества.

Каждый resourceId должен быть уникален в разделе. Количество и коэффициенты
объясни в quantityFormula, quantityInputs, inputProvenance и quantityBasis.
quantityFormula — не строка и не готовое вычисленное число, а безопасное AST:
variable {{op,name}}, constant {{op,value,unit}}, multiply/add {{op,items}},
divide {{op,numerator,denominator}} или ceil {{op,value}}. Используй только
variables из ProjectCase и размерностно совместимые единицы. Такую же формулу
задай самой operation.
Для overhead/tax/contingency дополнительно укажи ratePercent, baseKinds и
calculationBasis; не включай их неявно в цены других строк.
proposedUnitPrice является только кандидатом: если
проверенной цены нет, поставь честную предварительную цену либо 0.00 и укажи
это в priceBasis. Не называй цену проверенной и не вычисляй итоги.

Техническое утверждение включай в technicalSources только при наличии
проверяемого URL/идентификатора, даты, региона и применимости. Не выдумывай
нормативы, поставщиков или ссылки. Сегодня {today}. Используй decimal-строки
с точкой и не добавляй Markdown.
""".strip()


def estimate_price_section_instructions(*, today: str, section: str) -> str:
    return f"""
Ты снабженец и исследователь цен Kolibri для раздела «{section}».
Верни только JSON по переданной schema.

Исследуй переданный дедуплицированный список ресурсов. Для каждого resourceId
верни ровно один price candidate. Приоритет: данные пользователя, approved
catalog, официальный источник, датированное предложение поставщика, допустимый
market aggregate. Для меняющихся цен используй живой поиск. Search snippet и
память модели источником не являются.

Evidence обязательно фиксирует sourceType, sourceReference, sourceUrl (когда
источник вебовый), observedAt, region, исходную unit, НДС, доставку, срок
действия/snapshot hash и confidence. Если проверяемого источника нет, не
выдумывай его: используй sourceType=ai_preliminary или missing, confidence=
preliminary/missing и явно укажи это в sourceReference. Сегодня {today}.
Не рассчитывай итоги и не добавляй Markdown.
""".strip()


def estimate_review_instructions(*, section: str) -> str:
    return f"""
Ты независимый проверяющий технологической карты и ресурсной сметы Kolibri для
раздела «{section}». Верни только JSON по переданной schema.

Проверь полноту технологии, predecessors, покрытие операций работами,
материалами, оборудованием и услугами, единицы, quantityBasis, дубли,
необъяснённые ресурсы, источники, регион/дату/НДС/доставку и ценовые выбросы.
Не исправляй данные молча и не присваивай authoritative статус: перечисли
issues с точными operationId/resourceId. passed=true допустим только когда нет
ошибок; warnings перечисляй отдельно. Не добавляй Markdown.
""".strip()


def parse_generated_estimate(text: str) -> GeneratedEstimateProposal:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError("estimate proposal is not valid JSON") from None
    return GeneratedEstimateProposal.model_validate(value)


def parse_generated_estimate_plan(text: str) -> GeneratedEstimatePlan:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError("estimate plan is not valid JSON") from None
    return GeneratedEstimatePlan.model_validate(value)


def _repair_estimate_section(value: dict[str, Any]) -> dict[str, Any]:
    """Fix common AI output issues before validation."""
    # Ensure section name exists
    if not value.get("section"):
        value["section"] = "Untitled Section"

    # Ensure operations list exists and has at least one item
    operations = value.get("operations", [])
    if not operations:
        raise ValueError("estimate section has no operations")

    for i, op in enumerate(operations):
        # Fix operationId pattern
        oid = op.get("operationId", "")
        if not oid or not re.match(r"^operation_[A-Za-z0-9._~-]{4,96}$", oid):
            op["operationId"] = f"operation_{uuid.uuid4().hex[:16]}"

        # Fix required string fields
        for field in ("wbsCode", "section", "zone", "system"):
            if not op.get(field):
                op[field] = op.get("section") or value.get("section") or "default"

        # Ensure sequence
        if not isinstance(op.get("sequence"), int) or op["sequence"] < 1:
            op["sequence"] = i + 1

        # Ensure name
        if not op.get("name"):
            op["name"] = f"Operation {i + 1}"

        # Ensure method
        if not op.get("method"):
            op["method"] = "Standard construction method"

        # Ensure unit
        if not op.get("unit"):
            op["unit"] = "компл."

        # Fix quantityFormula - provide a default constant only if missing/null
        qf = op.get("quantityFormula")
        if qf is None:
            op["quantityFormula"] = {
                "op": "constant",
                "value": "1.00",
                "unit": "компл.",
            }
        elif isinstance(qf, str):
            # Reject free-form strings - let validation catch it
            pass

        # Fix resources - ensure at least one
        resources = op.get("resources", [])
        if not resources:
            resources = [{
                "resourceId": f"resource_{uuid.uuid4().hex[:12]}",
                "kind": "work",
                "description": op.get("name", f"Resource {i + 1}"),
                "quantityBasis": "Estimated",
                "proposedUnitPrice": "0.00",
                "priceBasis": "preliminary",
            }]
        for j, res in enumerate(resources):
            rid = res.get("resourceId", "")
            if not rid or not re.match(r"^resource_[A-Za-z0-9._~-]{4,96}$", rid):
                res["resourceId"] = f"resource_{uuid.uuid4().hex[:12]}"
            if not res.get("kind"):
                res["kind"] = "work"
            if not res.get("description"):
                res["description"] = f"Resource {j + 1}"
            if not res.get("quantityBasis"):
                res["quantityBasis"] = "Estimated"
            if not res.get("proposedUnitPrice"):
                res["proposedUnitPrice"] = "0.00"
            if not res.get("priceBasis"):
                res["priceBasis"] = "preliminary"
        op["resources"] = resources

    value["operations"] = operations
    return value


def parse_generated_estimate_section(text: str) -> GeneratedEstimateSection:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError("estimate section is not valid JSON") from None
    value = _repair_estimate_section(value)
    return GeneratedEstimateSection.model_validate(value)


def parse_generated_price_section(text: str) -> GeneratedPriceSection:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError("estimate price section is not valid JSON") from None
    return GeneratedPriceSection.model_validate(value)


def parse_generated_estimate_review(text: str) -> GeneratedEstimateReview:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError("estimate review is not valid JSON") from None
    return GeneratedEstimateReview.model_validate(value)


def _money(value: Decimal) -> str:
    return format(value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP), ".2f")


def _quantity(value: str) -> str:
    normalized = format(Decimal(value), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def canonical_estimate_json(document: dict[str, Any]) -> str:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def estimate_content_hash(document: dict[str, Any]) -> str:
    payload = canonical_estimate_json(document).encode("utf-8", "strict")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def empty_estimate_document(now: str) -> dict[str, Any]:
    return {
        "schema_id": "kolibri.estimate_draft",
        "schema_version": "1.4",
        "title": "Черновик сметы",
        "currency": "RUB",
        "region": None,
        "assumptions": [],
        "calculation_conditions": [],
        "scope_exclusions": [],
        "commercial_terms": {},
        "generation": None,
        "rows": [],
        "pricing": {
            "status": "unpriced",
            "sourced_rows": 0,
            "stale_rows": 0,
            "total_rows": 0,
            "last_checked_at": None,
        },
        "totals": {"subtotal": "0.00", "total": "0.00"},
        "updated_at": now,
    }


def estimate_required_fields(document: Mapping[str, Any]) -> list[str]:
    required: list[str] = []
    rows = document.get("rows")
    region = document.get("region")
    if not isinstance(region, str) or not region.strip() or region == "Регион не указан":
        required.append("Регион объекта")
    if not isinstance(rows, list) or not rows:
        required.extend(
            [
                "Описание объекта и состав работ",
                "Основные размеры или объёмы",
            ]
        )
        return required
    if all(str(row.get("quantity") or "0") in {"0", "0.0", "0.00"} for row in rows if isinstance(row, dict)):
        required.append("Объёмы работ")
    if all(str(row.get("unit_price") or "0") in {"0", "0.0", "0.00"} for row in rows if isinstance(row, dict)):
        required.append("Цены или разрешение на предварительную AI-оценку")
    return required


def estimate_lifecycle_status(
    document: Mapping[str, Any],
    persisted_status: str | None,
) -> EstimateLifecycleStatus:
    required = estimate_required_fields(document)
    if persisted_status == "failed" or persisted_status == "revoked":
        return "failed"
    if persisted_status == "calculating":
        return "calculating"
    if required:
        return "needs_input"
    if persisted_status == "ready":
        return "ready"
    return "draft"


def _price_basis_from_evidence(evidence: Mapping[str, Any]) -> str:
    source_type = evidence.get("source_type")
    if source_type == "fgis_cs":
        tax_label = {
            "included": "НДС включён",
            "excluded": "без НДС",
            "unknown": "НДС не указан",
        }.get(str(evidence.get("tax_status")), "НДС не указан")
        return (
            f"ФГИС ЦС · {evidence.get('period') or 'период не указан'} · "
            f"{evidence.get('price_zone') or evidence.get('region') or 'регион не указан'} · "
            f"{evidence.get('source_reference') or 'код не указан'} · "
            f"справочная цена, логистика отдельно не рассчитана · {tax_label}"
        )[:500]
    if source_type == "supplier_offer":
        tax_label = {
            "included": "НДС включён",
            "excluded": "без НДС",
            "unknown": "НДС не указан",
        }.get(str(evidence.get("tax_status")), "НДС не указан")
        return (
            f"Предложение {evidence.get('source_label') or 'поставщика'} · "
            f"{evidence.get('source_reference') or 'без номера'} · "
            f"от {evidence.get('price_date') or 'дата не указана'} · {tax_label}"
        )[:500]
    raise ValueError("unsupported price evidence source")


def _normalized_price_evidence(
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    source_type = str(evidence.get("source_type") or "")
    if source_type not in {"fgis_cs", "supplier_offer"}:
        raise ValueError("unsupported price evidence source")
    required_text = (
        "source_label",
        "source_url",
        "source_reference",
        "snapshot_hash",
        "quote_id",
        "region",
        "price_date",
        "retrieved_at",
        "fresh_until",
        "freshness_basis",
        "tax_status",
        "price_scope",
        "unit_price",
        "delivery_per_unit",
        "landed_unit_price",
        "landed_cost_status",
        "binding_status",
        "availability",
    )
    normalized = {key: evidence.get(key) for key in evidence}
    if source_type == "fgis_cs":
        normalized.setdefault("freshness_basis", "kolibri_policy_window")
        normalized.setdefault("price_scope", "official_reference")
        normalized.setdefault("landed_cost_status", "not_calculated")
    else:
        normalized.setdefault("freshness_basis", "supplier_valid_until")
        normalized.setdefault("price_scope", "landed")
        normalized.setdefault("landed_cost_status", "calculated")
    if any(
        not isinstance(normalized.get(key), str)
        or not str(normalized[key]).strip()
        for key in required_text
    ):
        raise ValueError("price evidence is incomplete")
    for money_field in ("unit_price", "delivery_per_unit", "landed_unit_price"):
        value = str(normalized[money_field])
        if MONEY_TEXT.fullmatch(value) is None:
            raise ValueError("price evidence money is invalid")
        normalized[money_field] = _money(Decimal(value))
    snapshot_hash = str(normalized["snapshot_hash"])
    if (
        len(snapshot_hash) != 71
        or not snapshot_hash.startswith("sha256:")
        or any(
            character not in "0123456789abcdef"
            for character in snapshot_hash[7:]
        )
    ):
        raise ValueError("price evidence snapshot hash is invalid")
    normalized["source_type"] = source_type
    if normalized["freshness_basis"] not in {
        "kolibri_policy_window",
        "supplier_valid_until",
    }:
        raise ValueError("price evidence freshness basis is invalid")
    if normalized["price_scope"] not in {"official_reference", "landed"}:
        raise ValueError("price evidence scope is invalid")
    if normalized["landed_cost_status"] not in {
        "not_calculated",
        "calculated",
    }:
        raise ValueError("price evidence landed cost status is invalid")
    normalized["status"] = (
        "stale"
        if date.fromisoformat(str(normalized["fresh_until"])) < date.today()
        else "current"
    )
    normalized.setdefault("material_code", None)
    normalized.setdefault("material_name", None)
    normalized.setdefault("price_zone", None)
    normalized.setdefault("period", None)
    normalized.setdefault("lead_time_days", None)
    normalized.setdefault("source_distance_price", None)
    normalized.setdefault("source_procurement_storage_percent", None)
    return normalized


def _pricing_summary(
    rows: list[dict[str, Any]],
    *,
    last_checked_at: str | None,
) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    for row in rows:
        if (
            row.get("evidence_id") is not None
            and row.get("line_confidence") in {"source_backed", "verified"}
        ):
            evidence.append({"status": "current"})
            continue
        legacy = row.get("price_evidence")
        if isinstance(legacy, dict):
            evidence.append(legacy)
            continue
        engine = row.get("engine_price_provenance")
        if not isinstance(engine, dict) or engine.get("verified") is not True:
            continue
        engine_status = "current"
        valid_until = engine.get("validUntil")
        checked_date = (
            last_checked_at[:10]
            if isinstance(last_checked_at, str) and len(last_checked_at) >= 10
            else None
        )
        if (
            isinstance(valid_until, str)
            and checked_date is not None
            and valid_until < checked_date
        ):
            engine_status = "stale"
        evidence.append({"status": engine_status})
    stale_rows = sum(1 for item in evidence if item.get("status") == "stale")
    current_rows = len(evidence) - stale_rows
    if stale_rows:
        status = "stale"
    elif current_rows == 0:
        status = "unpriced"
    elif current_rows == len(rows):
        status = "sourced"
    else:
        status = "partially_sourced"
    return {
        "status": status,
        "sourced_rows": current_rows,
        "stale_rows": stale_rows,
        "total_rows": len(rows),
        "last_checked_at": last_checked_at,
    }


def normalize_estimate_document(
    *,
    title: str,
    currency: str,
    rows: list[EstimateRowInput],
    now: str,
    region: str | None = None,
    assumptions: list[str] | None = None,
    calculation_conditions: list[str] | None = None,
    scope_exclusions: list[str] | None = None,
    commercial_terms: Mapping[str, Any] | None = None,
    generation: dict[str, str] | None = None,
    price_evidence_by_row: Mapping[str, Mapping[str, Any]] | None = None,
    pricing_checked_at: str | None = None,
) -> dict[str, Any]:
    if currency != "RUB":
        raise ValueError("unsupported estimate currency")
    normalized_rows: list[dict[str, str]] = []
    subtotal = Decimal("0")
    seen_ids: set[str] = set()
    trusted_evidence = price_evidence_by_row or {}
    for row in rows:
        if row.id in seen_ids:
            raise ValueError("estimate row IDs must be unique")
        seen_ids.add(row.id)
        try:
            quantity = Decimal(row.quantity)
            unit_price = Decimal(row.unit_price)
        except InvalidOperation:
            raise ValueError("estimate values must be decimal strings") from None
        if quantity < 0 or unit_price < 0:
            raise ValueError("estimate values cannot be negative")
        line_total = (quantity * unit_price).quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        subtotal += line_total
        normalized_row: dict[str, Any] = {
            "id": row.id,
            "section": row.section,
            "kind": row.kind,
            "description": row.description,
            "unit": row.unit,
            "quantity": _quantity(row.quantity),
            "unit_price": _money(unit_price),
            "line_total": _money(line_total),
            "quantity_basis": row.quantity_basis,
            "price_basis": row.price_basis,
        }
        for key, value in (
            ("wbs_path", row.wbs_path),
            ("specification", row.specification),
            ("quantity_formula", row.quantity_formula),
            ("catalog_entry_id", row.catalog_entry_id),
            ("catalog_entry_version", row.catalog_entry_version),
            ("technology_card_version", row.technology_card_version),
            ("operation_id", row.operation_id),
            ("resource_id", row.resource_id),
            ("evidence_id", row.evidence_id),
            ("price_observation_id", row.price_observation_id),
            ("market_aggregate_id", row.market_aggregate_id),
            ("line_confidence", row.line_confidence),
        ):
            if value is not None:
                normalized_row[key] = value
        evidence = trusted_evidence.get(row.id)
        if evidence is not None:
            normalized_evidence = _normalized_price_evidence(evidence)
            if normalized_evidence["landed_unit_price"] != _money(unit_price):
                raise ValueError("price evidence does not match applied unit price")
            normalized_row["price_basis"] = _price_basis_from_evidence(
                normalized_evidence
            )
            normalized_row["price_evidence"] = normalized_evidence
        normalized_rows.append(normalized_row)
    total = subtotal.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    return {
        "schema_id": "kolibri.estimate_draft",
        "schema_version": "1.4",
        "title": title,
        "currency": currency,
        "region": region,
        "assumptions": list(assumptions or []),
        "calculation_conditions": list(
            calculation_conditions if calculation_conditions is not None else (assumptions or [])
        ),
        "scope_exclusions": list(scope_exclusions or []),
        "commercial_terms": dict(commercial_terms or {}),
        "generation": generation,
        "rows": normalized_rows,
        "pricing": _pricing_summary(
            normalized_rows,
            last_checked_at=pricing_checked_at,
        ),
        "totals": {
            "subtotal": _money(subtotal),
            "total": _money(total),
        },
        "updated_at": now,
    }


def estimate_document_from_proposal(
    proposal: GeneratedEstimateProposal,
    *,
    now: str,
    provider_profile: str,
    run_id: str,
    generation_metadata: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    rows = [
        EstimateRowInput(
            id=row.id or f"row_{uuid.uuid4().hex}",
            section=row.section,
            kind=row.kind,
            description=row.description,
            unit=row.unit,
            quantity=row.quantity,
            unitPrice=row.unit_price,
            quantityBasis=row.quantity_basis,
            priceBasis=row.price_basis,
            wbsPath=row.wbs_path,
            specification=row.specification,
            quantityFormula=row.quantity_formula,
            technologyCardVersion=row.technology_card_version,
            operationId=row.operation_id,
            resourceId=row.resource_id,
            evidenceId=row.evidence_id,
            lineConfidence=row.line_confidence,
        )
        for row in proposal.rows
    ]
    document = normalize_estimate_document(
        title=proposal.title,
        currency="RUB",
        rows=rows,
        now=now,
        region=proposal.region,
        assumptions=proposal.assumptions,
        calculation_conditions=proposal.assumptions,
        generation={
            "provider_profile": provider_profile,
            "run_id": run_id,
            **dict(generation_metadata or {}),
        },
    )
    # Bind known AI rows to the reviewed system catalog without treating the
    # generated price as verified. Unknown rows remain candidate-only.
    known_catalog = (
        ("подготов", "catalog_system_site_preparation"),
        ("разработк\u0020грунта", "catalog_system_site_preparation"),
        ("фундамент монолит", "catalog_system_foundation_concrete"),
        ("армат", "catalog_system_rebar"),
        ("стен", "catalog_system_wall_masonry"),
        ("кладк", "catalog_system_wall_masonry"),
        ("кровел", "catalog_system_roof"),
        ("стропиль", "catalog_system_roof"),
        ("электромонтаж", "catalog_system_electrical"),
        ("сантех", "catalog_system_plumbing"),
    )
    for row in document.get("rows", []):
        if not isinstance(row, dict):
            continue
        description = str(row.get("description") or "").casefold()
        for needle, entry_id in known_catalog:
            if needle in description:
                row["catalog_entry_id"] = entry_id
                row["catalog_entry_version"] = 1
                break
        row.setdefault("line_confidence", "preliminary")
    return document


def parse_estimate_document(raw: object, *, now: str) -> dict[str, Any]:
    if not isinstance(raw, str):
        return empty_estimate_document(now)
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return empty_estimate_document(now)
    if (
        not isinstance(value, dict)
        or value.get("schema_id") != "kolibri.estimate_draft"
        or value.get("schema_version") not in {"1.0", "1.1", "1.2", "1.3", "1.4"}
        or not isinstance(value.get("title"), str)
        or value.get("currency") != "RUB"
        or not isinstance(value.get("rows"), list)
        or not isinstance(value.get("totals"), dict)
    ):
        return empty_estimate_document(now)
    value["schema_version"] = "1.4"
    value.setdefault("region", None)
    value.setdefault("assumptions", [])
    value.setdefault("calculation_conditions", value.get("assumptions", []))
    value.setdefault("scope_exclusions", [])
    value.setdefault("commercial_terms", {})
    value.setdefault("generation", None)
    existing_pricing = value.get("pricing")
    for row in value["rows"]:
        if not isinstance(row, dict):
            continue
        row.setdefault("section", "Прочее")
        row.setdefault("kind", "service")
        row.setdefault("quantity_basis", "Введено вручную")
        row.setdefault("price_basis", "Введено вручную")
        evidence = row.get("price_evidence")
        if isinstance(evidence, dict):
            try:
                row["price_evidence"] = _normalized_price_evidence(evidence)
            except (TypeError, ValueError):
                row.pop("price_evidence", None)
    value["pricing"] = _pricing_summary(
        [
            row
            for row in value["rows"]
            if isinstance(row, dict)
        ],
        last_checked_at=(
            str(existing_pricing.get("last_checked_at"))
            if isinstance(existing_pricing, dict)
            and isinstance(existing_pricing.get("last_checked_at"), str)
            else None
        ),
    )
    return value


def estimate_document_with_prices(
    document: Mapping[str, Any],
    *,
    evidence_by_row: Mapping[str, Mapping[str, Any]],
    now: str,
) -> dict[str, Any]:
    existing_rows = document.get("rows")
    if not isinstance(existing_rows, list):
        raise ValueError("estimate rows are missing")
    row_inputs: list[EstimateRowInput] = []
    retained_evidence: dict[str, Mapping[str, Any]] = {}
    for raw_row in existing_rows:
        if not isinstance(raw_row, dict):
            continue
        row_id = str(raw_row.get("id") or "")
        evidence = evidence_by_row.get(row_id)
        unit_price = (
            str(evidence.get("landed_unit_price"))
            if evidence is not None
            else str(raw_row.get("unit_price") or "0.00")
        )
        row_inputs.append(
            EstimateRowInput(
                id=row_id,
                section=str(raw_row.get("section") or "Прочее"),
                kind=str(raw_row.get("kind") or "service"),
                description=str(raw_row.get("description") or ""),
                unit=str(raw_row.get("unit") or ""),
                quantity=str(raw_row.get("quantity") or "0"),
                unitPrice=unit_price,
                quantityBasis=str(
                    raw_row.get("quantity_basis") or "Введено вручную"
                ),
                priceBasis=str(
                    raw_row.get("price_basis") or "Введено вручную"
                ),
                wbsPath=(
                    str(raw_row["wbs_path"])
                    if raw_row.get("wbs_path") is not None
                    else None
                ),
                specification=(
                    str(raw_row["specification"])
                    if raw_row.get("specification") is not None
                    else None
                ),
                quantityFormula=(
                    str(raw_row["quantity_formula"])
                    if raw_row.get("quantity_formula") is not None
                    else None
                ),
                catalogEntryId=(
                    str(raw_row["catalog_entry_id"])
                    if raw_row.get("catalog_entry_id") is not None
                    else None
                ),
                catalogEntryVersion=(
                    int(raw_row["catalog_entry_version"])
                    if raw_row.get("catalog_entry_version") is not None
                    else None
                ),
                technologyCardVersion=(
                    str(raw_row["technology_card_version"])
                    if raw_row.get("technology_card_version") is not None
                    else None
                ),
                operationId=(
                    str(raw_row["operation_id"])
                    if raw_row.get("operation_id") is not None
                    else None
                ),
                resourceId=(
                    str(raw_row["resource_id"])
                    if raw_row.get("resource_id") is not None
                    else None
                ),
                evidenceId=(
                    str(raw_row["evidence_id"])
                    if raw_row.get("evidence_id") is not None
                    else None
                ),
                priceObservationId=(
                    str(raw_row["price_observation_id"])
                    if raw_row.get("price_observation_id") is not None
                    else None
                ),
                marketAggregateId=(
                    str(raw_row["market_aggregate_id"])
                    if raw_row.get("market_aggregate_id") is not None
                    else None
                ),
                lineConfidence=str(raw_row.get("line_confidence") or "missing"),
            )
        )
        if evidence is not None:
            retained_evidence[row_id] = evidence
        elif isinstance(raw_row.get("price_evidence"), dict):
            retained_evidence[row_id] = raw_row["price_evidence"]
    return normalize_estimate_document(
        title=str(document.get("title") or "Черновик сметы"),
        currency="RUB",
        rows=row_inputs,
        now=now,
        region=(
            str(document["region"])
            if isinstance(document.get("region"), str)
            else None
        ),
        assumptions=[
            str(item)
            for item in document.get("assumptions", [])
            if isinstance(item, str)
        ],
        calculation_conditions=[
            str(item)
            for item in document.get(
                "calculation_conditions", document.get("assumptions", [])
            )
            if isinstance(item, str)
        ],
        scope_exclusions=[
            str(item)
            for item in document.get("scope_exclusions", [])
            if isinstance(item, str)
        ],
        commercial_terms=(
            document.get("commercial_terms")
            if isinstance(document.get("commercial_terms"), dict)
            else None
        ),
        generation=(
            {
                "provider_profile": str(
                    document["generation"].get("provider_profile") or ""
                ),
                "run_id": str(document["generation"].get("run_id") or ""),
            }
            if isinstance(document.get("generation"), dict)
            else None
        ),
        price_evidence_by_row=retained_evidence,
        pricing_checked_at=now,
    )


def estimate_view(
    *,
    project_id: str,
    document_id: str,
    version: int,
    status: str,
    document: dict[str, Any],
    row_offset: int = 0,
    row_limit: int | None = None,
) -> dict[str, Any]:
    rows = document.get("rows")
    totals = document.get("totals")
    generation = document.get("generation")
    required_fields = estimate_required_fields(document)
    lifecycle_status = estimate_lifecycle_status(document, status)
    all_rows = rows if isinstance(rows, list) else []
    safe_offset = max(0, row_offset)
    safe_limit = (
        max(0, row_limit)
        if row_limit is not None
        else max(0, len(all_rows) - safe_offset)
    )
    page_rows = all_rows[safe_offset : safe_offset + safe_limit]
    return {
        "schemaId": "kolibri.estimate_draft",
        "schemaVersion": "1.4",
        "projectId": project_id,
        "documentId": document_id,
        "version": version,
        "status": lifecycle_status,
        "requiredFields": required_fields,
        "estimateTitle": str(document.get("title") or "Черновик сметы"),
        "currency": "RUB",
        "estimateRegion": (
            str(document["region"])
            if isinstance(document.get("region"), str)
            else None
        ),
        "assumptions": [
            str(item)
            for item in document.get("assumptions", [])
            if isinstance(item, str)
        ][:20],
        "calculationConditions": [
            str(item)
            for item in document.get(
                "calculation_conditions", document.get("assumptions", [])
            )
            if isinstance(item, str)
        ][:20],
        "scopeExclusions": [
            str(item)
            for item in document.get("scope_exclusions", [])
            if isinstance(item, str)
        ][:20],
        "commercialTerms": (
            document.get("commercial_terms")
            if isinstance(document.get("commercial_terms"), dict)
            else {}
        ),
        "generation": (
            {
                "providerProfile": str(generation.get("provider_profile") or ""),
                "runId": str(generation.get("run_id") or ""),
                **{
                    api_key: generation[source_key]
                    for api_key, source_key in (
                        ("estimateGenerationRunId", "estimate_generation_run_id"),
                        ("technologyCardRevisionId", "technology_card_revision_id"),
                        ("technologyCardHash", "technology_card_hash"),
                        ("qualityStatus", "quality_status"),
                    )
                    if isinstance(generation.get(source_key), str)
                    and generation[source_key]
                },
            }
            if isinstance(generation, dict)
            else None
        ),
        "rows": [
            {
                "id": str(row.get("id")),
                "section": str(row.get("section") or "Прочее"),
                "kind": str(row.get("kind") or "service"),
                "description": str(row.get("description")),
                "unit": str(row.get("unit")),
                "quantity": str(row.get("quantity")),
                "unitPrice": str(row.get("unit_price")),
                "lineTotal": str(row.get("line_total")),
                "quantityBasis": str(
                    row.get("quantity_basis") or "Введено вручную"
                ),
                "priceBasis": str(row.get("price_basis") or "Введено вручную"),
                **{
                    api_key: value
                    for api_key, value in (
                        ("wbsPath", row.get("wbs_path")),
                        ("specification", row.get("specification")),
                        ("quantityFormula", row.get("quantity_formula")),
                        ("catalogEntryId", row.get("catalog_entry_id")),
                        ("catalogEntryVersion", row.get("catalog_entry_version")),
                        ("technologyCardVersion", row.get("technology_card_version")),
                        ("operationId", row.get("operation_id")),
                        ("resourceId", row.get("resource_id")),
                        ("evidenceId", row.get("evidence_id")),
                        ("priceObservationId", row.get("price_observation_id")),
                        ("marketAggregateId", row.get("market_aggregate_id")),
                    )
                    if value is not None
                },
                "lineConfidence": row.get("line_confidence", "missing"),
                "priceEvidence": (
                    {
                        "status": str(row["price_evidence"]["status"]),
                        "sourceType": str(row["price_evidence"]["source_type"]),
                        "sourceLabel": str(row["price_evidence"]["source_label"]),
                        "sourceUrl": str(row["price_evidence"]["source_url"]),
                        "sourceReference": str(
                            row["price_evidence"]["source_reference"]
                        ),
                        "snapshotHash": str(
                            row["price_evidence"]["snapshot_hash"]
                        ),
                        "quoteId": str(row["price_evidence"]["quote_id"]),
                        "materialCode": row["price_evidence"].get("material_code"),
                        "materialName": row["price_evidence"].get("material_name"),
                        "region": str(row["price_evidence"]["region"]),
                        "priceZone": row["price_evidence"].get("price_zone"),
                        "period": row["price_evidence"].get("period"),
                        "priceDate": str(row["price_evidence"]["price_date"]),
                        "retrievedAt": str(row["price_evidence"]["retrieved_at"]),
                        "freshUntil": str(row["price_evidence"]["fresh_until"]),
                        "freshnessBasis": str(
                            row["price_evidence"]["freshness_basis"]
                        ),
                        "taxStatus": str(row["price_evidence"]["tax_status"]),
                        "priceScope": str(row["price_evidence"]["price_scope"]),
                        "unitPrice": str(row["price_evidence"]["unit_price"]),
                        "deliveryPerUnit": str(
                            row["price_evidence"]["delivery_per_unit"]
                        ),
                        "landedUnitPrice": str(
                            row["price_evidence"]["landed_unit_price"]
                        ),
                        "landedCostStatus": str(
                            row["price_evidence"]["landed_cost_status"]
                        ),
                        "sourceDistancePrice": row["price_evidence"].get(
                            "source_distance_price"
                        ),
                        "sourceProcurementStoragePercent": row[
                            "price_evidence"
                        ].get("source_procurement_storage_percent"),
                        "bindingStatus": str(
                            row["price_evidence"]["binding_status"]
                        ),
                        "availability": str(
                            row["price_evidence"]["availability"]
                        ),
                        "leadTimeDays": row["price_evidence"].get(
                            "lead_time_days"
                        ),
                    }
                    if isinstance(row.get("price_evidence"), dict)
                    else None
                ),
                **(
                    {
                        "enginePriceProvenance": {
                            **{
                                key: value
                                for key, value in row[
                                    "engine_price_provenance"
                                ].items()
                                if key != "url"
                            },
                            "sourceUrl": row[
                                "engine_price_provenance"
                            ].get("sourceUrl")
                            or row["engine_price_provenance"].get("url"),
                        }
                    }
                    if isinstance(row.get("engine_price_provenance"), dict)
                    else {}
                ),
            }
            for row in page_rows
            if isinstance(row, dict)
        ],
        "rowPage": {
            "offset": safe_offset,
            "limit": safe_limit,
            "totalRows": len(all_rows),
            "hasMore": safe_offset + len(page_rows) < len(all_rows),
        },
        "pricing": {
            "status": str(
                document.get("pricing", {}).get("status") or "unpriced"
            ),
            "sourcedRows": int(
                document.get("pricing", {}).get("sourced_rows") or 0
            ),
            "staleRows": int(
                document.get("pricing", {}).get("stale_rows") or 0
            ),
            "totalRows": int(
                document.get("pricing", {}).get("total_rows") or 0
            ),
            "lastCheckedAt": document.get("pricing", {}).get(
                "last_checked_at"
            ),
        },
        "totals": {
            "subtotal": str(totals.get("subtotal") or "0.00"),
            "total": str(totals.get("total") or "0.00"),
        }
        if isinstance(totals, dict)
        else {"subtotal": "0.00", "total": "0.00"},
        "updatedAt": str(document.get("updated_at") or ""),
    }


def record_estimate_version(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    document_id: str,
    version: int,
    status: str,
    document: dict[str, Any],
    origin_type: Literal["ai_proposal", "manual_edit", "engine_calculation"],
    origin_run_id: str | None,
    created_by_user_id: str,
    created_at: str,
) -> None:
    database.execute(
        """
        INSERT INTO estimate_versions (
            tenant_id, id, project_id, document_id, version, status,
            lifecycle_status,
            content_json, content_hash, origin_type, origin_run_id,
            created_by_user_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tenant_id,
            f"estimate_version_{uuid.uuid4().hex}",
            project_id,
            document_id,
            version,
            status,
            estimate_lifecycle_status(document, status),
            canonical_estimate_json(document),
            estimate_content_hash(document),
            origin_type,
            origin_run_id,
            created_by_user_id,
            created_at,
        ),
    )


def load_estimate_slot(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
) -> sqlite3.Row | None:
    return database.execute(
        """
        SELECT id, version,
               COALESCE(estimate_lifecycle_status, status) AS status,
               content_json, updated_at
        FROM document_slots
        WHERE tenant_id = ? AND project_id = ? AND slot_type = 'estimate'
        LIMIT 1
        """,
        (tenant_id, project_id),
    ).fetchone()
