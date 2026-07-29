"""Deterministic estimate calculation for a normalized ProjectCase.

The engine deliberately knows nothing about LLMs, HTTP or persistence.  A
caller supplies a normalized scope, an immutable price snapshot and explicit
commercial terms.  The same inputs and rule version always produce identical
canonical JSON.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from typing import Any, Literal, Mapping, Sequence


ENGINE_VERSION = "kolibri-estimate-engine/1.0.0"
PLASTER_RULES_VERSION = "plastering/1.0.0"
MONEY_QUANTUM = Decimal("0.01")
QUANTITY_QUANTUM = Decimal("0.000001")

EstimateKind = Literal["work", "material", "equipment", "service"]
PlasterMaterial = Literal["gypsum", "cement"]
ApplicationMethod = Literal["mechanized", "manual"]
VatMode = Literal["included", "excluded", "not_applicable", "unknown"]


class EstimateEngineError(ValueError):
    """Base class for deterministic calculation contract failures."""


class FormulaError(EstimateEngineError):
    """Raised for unsafe or dimensionally invalid quantity formulae."""


class MissingPriceError(EstimateEngineError):
    """Raised when release calculation is requested with missing prices."""


def _decimal(value: Decimal | str | int, *, field: str) -> Decimal:
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise EstimateEngineError(f"{field} must be decimal") from None
    if not parsed.is_finite():
        raise EstimateEngineError(f"{field} must be finite")
    return parsed


def _non_negative(value: Decimal | str | int, *, field: str) -> Decimal:
    parsed = _decimal(value, field=field)
    if parsed < 0:
        raise EstimateEngineError(f"{field} cannot be negative")
    return parsed


def _positive(value: Decimal | str | int, *, field: str) -> Decimal:
    parsed = _decimal(value, field=field)
    if parsed <= 0:
        raise EstimateEngineError(f"{field} must be positive")
    return parsed


def _decimal_text(value: Decimal) -> str:
    normalized = format(
        value.quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP),
        "f",
    )
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def _money(value: Decimal) -> str:
    return format(value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP), ".2f")


def _percent(value: Decimal) -> Decimal:
    return value / Decimal("100")


Dimension = tuple[tuple[str, int], ...]


def _dimensions(**values: int) -> Dimension:
    return tuple(sorted((key, value) for key, value in values.items() if value))


def _merge_dimensions(left: Dimension, right: Dimension, sign: int) -> Dimension:
    merged = dict(left)
    for key, power in right:
        merged[key] = merged.get(key, 0) + (power * sign)
        if merged[key] == 0:
            del merged[key]
    return tuple(sorted(merged.items()))


@dataclass(frozen=True, slots=True)
class UnitDefinition:
    symbol: str
    dimensions: Dimension
    to_base: Decimal


UNITS: dict[str, UnitDefinition] = {
    "1": UnitDefinition("1", (), Decimal("1")),
    "m": UnitDefinition("m", _dimensions(length=1), Decimal("1")),
    "mm": UnitDefinition("mm", _dimensions(length=1), Decimal("0.001")),
    "m2": UnitDefinition("m2", _dimensions(length=2), Decimal("1")),
    "kg": UnitDefinition("kg", _dimensions(mass=1), Decimal("1")),
    "t": UnitDefinition("t", _dimensions(mass=1), Decimal("1000")),
    "l": UnitDefinition("l", _dimensions(volume=1), Decimal("0.001")),
    "m3": UnitDefinition("m3", _dimensions(volume=1), Decimal("1")),
    "kWh": UnitDefinition("kWh", _dimensions(energy=1), Decimal("1")),
    "ea": UnitDefinition("ea", _dimensions(item=1), Decimal("1")),
    "bag": UnitDefinition("bag", _dimensions(package=1), Decimal("1")),
    "shift": UnitDefinition("shift", _dimensions(shift=1), Decimal("1")),
    "trip": UnitDefinition("trip", _dimensions(trip=1), Decimal("1")),
    "set": UnitDefinition("set", _dimensions(set=1), Decimal("1")),
    "kg_per_m2": UnitDefinition(
        "kg_per_m2",
        _dimensions(mass=1, length=-2),
        Decimal("1"),
    ),
    "l_per_m2": UnitDefinition(
        "l_per_m2",
        _dimensions(volume=1, length=-2),
        Decimal("0.001"),
    ),
    "l_per_kg": UnitDefinition(
        "l_per_kg",
        _dimensions(volume=1, mass=-1),
        Decimal("0.001"),
    ),
    "kwh_per_m2": UnitDefinition(
        "kwh_per_m2",
        _dimensions(energy=1, length=-2),
        Decimal("1"),
    ),
}


@dataclass(frozen=True, slots=True)
class Quantity:
    base_value: Decimal
    dimensions: Dimension

    @classmethod
    def of(cls, value: Decimal | str | int, unit: str) -> Quantity:
        definition = UNITS.get(unit)
        if definition is None:
            raise FormulaError(f"unsupported unit: {unit}")
        return cls(
            base_value=_decimal(value, field="formula value")
            * definition.to_base,
            dimensions=definition.dimensions,
        )

    def to(self, unit: str) -> Decimal:
        definition = UNITS.get(unit)
        if definition is None:
            raise FormulaError(f"unsupported unit: {unit}")
        if self.dimensions != definition.dimensions:
            raise FormulaError(
                f"dimension mismatch: {self.dimensions!r} cannot convert to {unit}"
            )
        return self.base_value / definition.to_base

    def add(self, other: Quantity) -> Quantity:
        if self.dimensions != other.dimensions:
            raise FormulaError("addition requires equal dimensions")
        return Quantity(self.base_value + other.base_value, self.dimensions)

    def multiply(self, other: Quantity) -> Quantity:
        return Quantity(
            self.base_value * other.base_value,
            _merge_dimensions(self.dimensions, other.dimensions, 1),
        )

    def divide(self, other: Quantity) -> Quantity:
        if other.base_value == 0:
            raise FormulaError("division by zero")
        return Quantity(
            self.base_value / other.base_value,
            _merge_dimensions(self.dimensions, other.dimensions, -1),
        )


Formula = dict[str, Any]


def variable(name: str) -> Formula:
    return {"op": "variable", "name": name}


def constant(value: Decimal | str | int, unit: str = "1") -> Formula:
    return {"op": "constant", "value": _decimal_text(_decimal(value, field="constant")), "unit": unit}


def multiply(*items: Formula) -> Formula:
    if len(items) < 2:
        raise FormulaError("multiply requires at least two operands")
    return {"op": "multiply", "items": list(items)}


def divide(numerator: Formula, denominator: Formula) -> Formula:
    return {"op": "divide", "numerator": numerator, "denominator": denominator}


def ceil_formula(value: Formula) -> Formula:
    return {"op": "ceil", "value": value}


def _formula_quantity(
    expression: Mapping[str, Any],
    variables: Mapping[str, Quantity],
    *,
    depth: int = 0,
) -> Quantity:
    if depth > 24:
        raise FormulaError("formula nesting limit exceeded")
    operation = expression.get("op")
    if operation == "variable":
        name = expression.get("name")
        if not isinstance(name, str) or name not in variables:
            raise FormulaError("formula variable is missing")
        return variables[name]
    if operation == "constant":
        value = expression.get("value")
        unit = expression.get("unit")
        if not isinstance(value, str) or not isinstance(unit, str):
            raise FormulaError("constant formula is invalid")
        return Quantity.of(value, unit)
    if operation == "multiply":
        items = expression.get("items")
        if not isinstance(items, list) or len(items) < 2 or len(items) > 12:
            raise FormulaError("multiply formula is invalid")
        result = Quantity.of("1", "1")
        for item in items:
            if not isinstance(item, dict):
                raise FormulaError("multiply operand is invalid")
            result = result.multiply(
                _formula_quantity(item, variables, depth=depth + 1)
            )
        return result
    if operation == "divide":
        numerator = expression.get("numerator")
        denominator = expression.get("denominator")
        if not isinstance(numerator, dict) or not isinstance(denominator, dict):
            raise FormulaError("divide formula is invalid")
        return _formula_quantity(
            numerator,
            variables,
            depth=depth + 1,
        ).divide(
            _formula_quantity(
                denominator,
                variables,
                depth=depth + 1,
            )
        )
    if operation == "add":
        items = expression.get("items")
        if not isinstance(items, list) or len(items) < 2 or len(items) > 12:
            raise FormulaError("add formula is invalid")
        first, *rest = items
        if not isinstance(first, dict):
            raise FormulaError("add operand is invalid")
        result = _formula_quantity(first, variables, depth=depth + 1)
        for item in rest:
            if not isinstance(item, dict):
                raise FormulaError("add operand is invalid")
            result = result.add(
                _formula_quantity(item, variables, depth=depth + 1)
            )
        return result
    if operation == "ceil":
        value = expression.get("value")
        if not isinstance(value, dict):
            raise FormulaError("ceil formula is invalid")
        quantity = _formula_quantity(value, variables, depth=depth + 1)
        if quantity.dimensions:
            raise FormulaError("ceil requires a dimensionless value")
        return Quantity(
            quantity.base_value.to_integral_value(rounding=ROUND_CEILING),
            (),
        )
    raise FormulaError("formula operation is not allowlisted")


def evaluate_formula(
    expression: Formula,
    variables: Mapping[str, Quantity],
    *,
    target_unit: str,
) -> Decimal:
    value = _formula_quantity(expression, variables).to(target_unit)
    if value < 0:
        raise FormulaError("formula result cannot be negative")
    return value.quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class ProjectCaseRef:
    tenant_id: str
    project_id: str
    case_id: str
    version: int
    region: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                self.tenant_id,
                self.project_id,
                self.case_id,
                self.region,
            )
        ):
            raise EstimateEngineError("ProjectCase identity and region are required")
        if self.version < 1:
            raise EstimateEngineError("ProjectCase version must be positive")


@dataclass(frozen=True, slots=True)
class PlasteringScope:
    wall_area_m2: Decimal
    average_thickness_mm: Decimal
    material: PlasterMaterial
    application_method: ApplicationMethod
    waste_percent: Decimal
    protection_area_m2: Decimal
    wall_height_m: Decimal
    beacon_spacing_m: Decimal
    corner_length_m: Decimal
    mesh_area_percent: Decimal
    slopes_area_m2: Decimal
    plaster_bag_weight_kg: Decimal
    primer_passes: int
    waste_removal_trips: Decimal

    def __post_init__(self) -> None:
        decimal_fields = (
            "wall_area_m2",
            "average_thickness_mm",
            "waste_percent",
            "protection_area_m2",
            "wall_height_m",
            "beacon_spacing_m",
            "corner_length_m",
            "mesh_area_percent",
            "slopes_area_m2",
            "plaster_bag_weight_kg",
            "waste_removal_trips",
        )
        for field in decimal_fields:
            value = _non_negative(getattr(self, field), field=field)
            object.__setattr__(self, field, value)
        for field in (
            "wall_area_m2",
            "average_thickness_mm",
            "wall_height_m",
            "beacon_spacing_m",
            "plaster_bag_weight_kg",
        ):
            if getattr(self, field) <= 0:
                raise EstimateEngineError(f"{field} must be positive")
        if self.material not in {"gypsum", "cement"}:
            raise EstimateEngineError("unsupported plaster material")
        if self.application_method not in {"mechanized", "manual"}:
            raise EstimateEngineError("unsupported application method")
        if not 0 <= self.waste_percent <= 100:
            raise EstimateEngineError("waste_percent must be between 0 and 100")
        if not 0 <= self.mesh_area_percent <= 100:
            raise EstimateEngineError("mesh_area_percent must be between 0 and 100")
        if not 1 <= self.primer_passes <= 4:
            raise EstimateEngineError("primer_passes must be between 1 and 4")


@dataclass(frozen=True, slots=True)
class PriceSource:
    source_id: str
    source_type: Literal[
        "regional_catalog",
        "supplier_offer",
        "organization_price",
        "user_price",
        "ai_candidate",
    ]
    label: str
    reference: str
    url: str
    region: str
    observed_at: str
    valid_until: str | None
    verified: bool

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                self.source_id,
                self.label,
                self.reference,
                self.url,
                self.region,
                self.observed_at,
            )
        ):
            raise EstimateEngineError("price source provenance is incomplete")
        if not self.url.startswith(("https://", "document://")):
            raise EstimateEngineError("price source URL must be HTTPS or document reference")


@dataclass(frozen=True, slots=True)
class PriceQuote:
    item_code: str
    unit: str
    unit_price: Decimal
    currency: str
    vat_mode: VatMode
    confidence: Decimal
    source: PriceSource

    def __post_init__(self) -> None:
        if self.unit not in UNITS:
            raise EstimateEngineError("price unit is unsupported")
        object.__setattr__(
            self,
            "unit_price",
            _non_negative(self.unit_price, field="unit_price"),
        )
        confidence = _non_negative(self.confidence, field="confidence")
        if confidence > 1:
            raise EstimateEngineError("confidence cannot exceed 1")
        object.__setattr__(self, "confidence", confidence)
        if self.currency != "RUB":
            raise EstimateEngineError("only RUB price snapshots are supported")
        if self.vat_mode not in {
            "included",
            "excluded",
            "not_applicable",
            "unknown",
        }:
            raise EstimateEngineError("VAT mode is invalid")


@dataclass(frozen=True, slots=True)
class CommercialTerms:
    overhead_percent: Decimal = Decimal("0")
    profit_percent: Decimal = Decimal("0")
    discount_percent: Decimal = Decimal("0")
    tax_percent: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        for field in (
            "overhead_percent",
            "profit_percent",
            "discount_percent",
            "tax_percent",
        ):
            value = _non_negative(getattr(self, field), field=field)
            if value > 100:
                raise EstimateEngineError(f"{field} cannot exceed 100")
            object.__setattr__(self, field, value)


@dataclass(frozen=True, slots=True)
class TechnologyStage:
    stage_id: str
    order: int
    title: str
    operations: tuple[str, ...]
    resources: tuple[str, ...]
    quality_controls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InclusionDecision:
    item_code: str
    included: bool
    reason: str


@dataclass(frozen=True, slots=True)
class TechnologyCard:
    schema_version: str
    rules_version: str
    stages: tuple[TechnologyStage, ...]
    decisions: tuple[InclusionDecision, ...]

    def as_document(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "rulesVersion": self.rules_version,
            "stages": [asdict(stage) for stage in self.stages],
            "decisions": [asdict(decision) for decision in self.decisions],
        }


@dataclass(frozen=True, slots=True)
class LinePlan:
    code: str
    section: str
    kind: EstimateKind
    title: str
    unit: str
    formula: Formula
    consumption_norm: str | None
    waste_factor: Decimal
    explanation: str


def build_plastering_technology_card(scope: PlasteringScope) -> TechnologyCard:
    mechanized = scope.application_method == "mechanized"
    mesh = scope.mesh_area_percent > 0
    corners = scope.corner_length_m > 0
    slopes = scope.slopes_area_m2 > 0
    stages = (
        TechnologyStage(
            "survey",
            10,
            "Обследование основания",
            (
                "Проверить прочность, влажность, геометрию и совместимость основания.",
                "Зафиксировать дефекты и фактическую среднюю толщину слоя.",
            ),
            ("правило", "лазерный уровень", "влагомер"),
            ("Акт осмотра основания", "Карта перепадов плоскости"),
        ),
        TechnologyStage(
            "protection",
            20,
            "Защита объекта",
            (
                "Закрыть окна, двери, полы и смежные готовые поверхности.",
                "Организовать безопасную рабочую зону и проходы.",
            ),
            ("плёнка", "картон", "малярная лента"),
            ("Защитные покрытия без разрывов",),
        ),
        TechnologyStage(
            "preparation",
            30,
            "Подготовка основания",
            (
                "Удалить пыль, загрязнения и непрочные участки.",
                "Нанести совместимый грунт с выдержкой по техрегламенту.",
            ),
            ("грунт", "щётки", "пылесос"),
            ("Адгезия и равномерность грунтования",),
        ),
        TechnologyStage(
            "guides",
            40,
            "Маяки, углы и усиление",
            (
                "Выставить маяки по проектной плоскости.",
                "Установить угловые профили и усилить примыкания по условиям.",
            ),
            ("маячковый профиль", "перфоуголок", "щелочестойкая сетка"),
            ("Шаг маяков", "Вертикальность углов", "Перехлёст сетки"),
        ),
        TechnologyStage(
            "application",
            50,
            "Приготовление и нанесение",
            (
                (
                    "Подготовить штукатурную станцию, воду и электропитание."
                    if mechanized
                    else "Подготовить раствор и ручной инструмент."
                ),
                "Нанести раствор равномерным слоем и протянуть правилом.",
            ),
            (
                ("штукатурная станция", "вода", "электроэнергия")
                if mechanized
                else ("миксер", "ёмкости", "ручной инструмент")
            ),
            ("Толщина слоя", "Заполнение без пустот", "Срок выработки раствора"),
        ),
        TechnologyStage(
            "finish",
            60,
            "Подрезка и финиш",
            (
                "Подрезать и загладить поверхность после схватывания.",
                "Обработать откосы и примыкания, если они заданы.",
            ),
            ("правило", "трапеция", "шпатели"),
            ("Плоскостность", "Вертикальность", "Качество поверхности"),
        ),
        TechnologyStage(
            "closeout",
            70,
            "Контроль, уборка и сдача",
            (
                "Провести итоговый контроль качества.",
                "Убрать рабочую зону, собрать упаковку и вывезти отходы.",
            ),
            ("контрольный инструмент", "тара для отходов"),
            ("Протокол контроля", "Передача результата заказчику"),
        ),
    )
    decisions = (
        InclusionDecision(
            "protection",
            True,
            "Защита окон, пола и смежных поверхностей обязательна до мокрых работ.",
        ),
        InclusionDecision(
            "beacon_profile",
            True,
            "Выравнивание принято по маякам.",
        ),
        InclusionDecision(
            "corner_profile",
            corners,
            (
                f"Включено по заданной длине внешних углов {scope.corner_length_m} м."
                if corners
                else "Исключено: длина внешних углов равна нулю."
            ),
        ),
        InclusionDecision(
            "reinforcing_mesh",
            mesh,
            (
                f"Локальное армирование задано для {scope.mesh_area_percent}% площади."
                if mesh
                else "Исключено: зоны армирования не заданы."
            ),
        ),
        InclusionDecision(
            "plaster_machine",
            mechanized,
            (
                "Включено для механизированного способа."
                if mechanized
                else "Исключено для ручного способа."
            ),
        ),
        InclusionDecision(
            "utilities",
            mechanized,
            (
                "Вода и электроэнергия включены для штукатурной станции."
                if mechanized
                else "Отдельная эксплуатация станции не требуется."
            ),
        ),
        InclusionDecision(
            "slopes",
            slopes,
            (
                f"Включено по заданной площади откосов {scope.slopes_area_m2} м²."
                if slopes
                else "Исключено: площадь откосов равна нулю."
            ),
        ),
        InclusionDecision(
            "waste_removal",
            scope.waste_removal_trips > 0,
            (
                f"Включено {scope.waste_removal_trips} рейс."
                if scope.waste_removal_trips > 0
                else "Исключено: вывоз выполняет заказчик."
            ),
        ),
    )
    return TechnologyCard(
        schema_version="1.0",
        rules_version=PLASTER_RULES_VERSION,
        stages=stages,
        decisions=decisions,
    )


def _plastering_variables(scope: PlasteringScope) -> dict[str, Quantity]:
    mix_norm = Decimal("8.5") if scope.material == "gypsum" else Decimal("17")
    return {
        "wall_area": Quantity.of(scope.wall_area_m2, "m2"),
        "thickness": Quantity.of(scope.average_thickness_mm, "mm"),
        "reference_thickness": Quantity.of("10", "mm"),
        "waste_factor": Quantity.of(
            Decimal("1") + _percent(scope.waste_percent),
            "1",
        ),
        "protection_area": Quantity.of(scope.protection_area_m2, "m2"),
        "wall_height": Quantity.of(scope.wall_height_m, "m"),
        "beacon_spacing": Quantity.of(scope.beacon_spacing_m, "m"),
        "corner_length": Quantity.of(scope.corner_length_m, "m"),
        "profile_length": Quantity.of("3", "m"),
        "mesh_ratio": Quantity.of(_percent(scope.mesh_area_percent), "1"),
        "slopes_area": Quantity.of(scope.slopes_area_m2, "m2"),
        "mix_norm": Quantity.of(mix_norm, "kg_per_m2"),
        "bag_weight": Quantity.of(scope.plaster_bag_weight_kg, "kg"),
        "primer_norm": Quantity.of("0.15", "l_per_m2"),
        "primer_passes": Quantity.of(scope.primer_passes, "1"),
        "water_norm": Quantity.of(
            "0.55" if scope.material == "gypsum" else "0.22",
            "l_per_kg",
        ),
        "machine_energy_norm": Quantity.of("0.055", "kwh_per_m2"),
        "machine_productivity": Quantity.of("180", "m2"),
        "vehicle_payload": Quantity.of("1500", "kg"),
        "one_each": Quantity.of("1", "ea"),
        "one_bag": Quantity.of("1", "bag"),
        "one_shift": Quantity.of("1", "shift"),
        "one_trip": Quantity.of("1", "trip"),
        "one_set": Quantity.of("1", "set"),
        "waste_removal_trips": Quantity.of(scope.waste_removal_trips, "trip"),
    }


def _plastering_line_plans(scope: PlasteringScope) -> tuple[LinePlan, ...]:
    area = variable("wall_area")
    waste = variable("waste_factor")
    thickness_ratio = divide(
        variable("thickness"),
        variable("reference_thickness"),
    )
    mix_mass = multiply(
        area,
        variable("mix_norm"),
        thickness_ratio,
        waste,
    )
    plaster_title = (
        "Гипсовая штукатурная смесь"
        if scope.material == "gypsum"
        else "Цементная штукатурная смесь"
    )
    application_title = (
        "Механизированное нанесение штукатурки"
        if scope.application_method == "mechanized"
        else "Ручное нанесение штукатурки"
    )
    rows: list[LinePlan] = [
        LinePlan(
            "survey",
            "Подготовка",
            "work",
            "Обследование и карта перепадов основания",
            "m2",
            area,
            None,
            Decimal("1"),
            "Обязательный входной контроль до определения окончательной толщины.",
        ),
        LinePlan(
            "surface_cleaning",
            "Подготовка",
            "work",
            "Очистка и обеспыливание основания",
            "m2",
            area,
            None,
            Decimal("1"),
            "Удаление загрязнений и непрочных участков.",
        ),
        LinePlan(
            "protection",
            "Защита объекта",
            "service",
            "Защита окон, пола и смежных поверхностей",
            "m2",
            variable("protection_area"),
            None,
            Decimal("1"),
            "Площадь защиты поступает из ProjectCase и не выводится из площади стен.",
        ),
        LinePlan(
            "primer_application",
            "Грунтование",
            "work",
            "Нанесение грунта",
            "m2",
            area,
            f"{scope.primer_passes} проход",
            Decimal("1"),
            "Количество проходов задано технологической картой.",
        ),
        LinePlan(
            "primer_material",
            "Грунтование",
            "material",
            "Грунтовка для основания",
            "l",
            multiply(
                area,
                variable("primer_norm"),
                variable("primer_passes"),
                waste,
            ),
            "0.15 л/м² за проход",
            Decimal("1") + _percent(scope.waste_percent),
            "Расход умножается на число проходов и явный запас.",
        ),
        LinePlan(
            "beacon_installation",
            "Маяки и усиление",
            "work",
            "Установка и выверка штукатурных маяков",
            "m2",
            area,
            None,
            Decimal("1"),
            "Выравнивание принято по маякам.",
        ),
        LinePlan(
            "beacon_profile",
            "Маяки и усиление",
            "material",
            "Маячковый профиль 3 м",
            "ea",
            multiply(
                ceil_formula(
                    multiply(
                        divide(
                            divide(area, variable("wall_height")),
                            variable("beacon_spacing"),
                        ),
                        waste,
                    )
                ),
                variable("one_each"),
            ),
            f"шаг {scope.beacon_spacing_m} м",
            Decimal("1") + _percent(scope.waste_percent),
            "Число маяков округляется вверх после применения запаса.",
        ),
    ]
    if scope.corner_length_m > 0:
        rows.extend(
            (
                LinePlan(
                    "corner_installation",
                    "Маяки и усиление",
                    "work",
                    "Установка углового профиля",
                    "m",
                    variable("corner_length"),
                    None,
                    Decimal("1"),
                    "Длина внешних углов задана в ProjectCase.",
                ),
                LinePlan(
                    "corner_profile",
                    "Маяки и усиление",
                    "material",
                    "ПВХ/перфорированный уголок 3 м",
                    "ea",
                    multiply(
                        ceil_formula(
                            multiply(
                                divide(
                                    variable("corner_length"),
                                    variable("profile_length"),
                                ),
                                waste,
                            )
                        ),
                        variable("one_each"),
                    ),
                    "профиль 3 м",
                    Decimal("1") + _percent(scope.waste_percent),
                    "Профиль округляется до целых хлыстов вверх.",
                ),
            )
        )
    if scope.mesh_area_percent > 0:
        mesh_area = multiply(area, variable("mesh_ratio"))
        rows.extend(
            (
                LinePlan(
                    "mesh_installation",
                    "Маяки и усиление",
                    "work",
                    "Локальное армирование сеткой",
                    "m2",
                    mesh_area,
                    f"{scope.mesh_area_percent}% площади",
                    Decimal("1"),
                    "Зоны армирования заданы долей площади стен.",
                ),
                LinePlan(
                    "reinforcing_mesh",
                    "Маяки и усиление",
                    "material",
                    "Щелочестойкая штукатурная сетка",
                    "m2",
                    multiply(mesh_area, waste),
                    f"{scope.mesh_area_percent}% площади",
                    Decimal("1") + _percent(scope.waste_percent),
                    "Материал включает явный запас.",
                ),
            )
        )
    rows.append(
        LinePlan(
            "plaster_application",
            "Нанесение",
            "work",
            application_title,
            "m2",
            area,
            f"слой {scope.average_thickness_mm} мм",
            Decimal("1"),
            "Работа рассчитывается по площади стен; слой влияет на ресурс смеси.",
        )
    )
    rows.append(
        LinePlan(
            "plaster_mix",
            "Нанесение",
            "material",
            plaster_title,
            "bag",
            multiply(
                ceil_formula(divide(mix_mass, variable("bag_weight"))),
                variable("one_bag"),
            ),
            (
                "8.5 кг/м² на 10 мм"
                if scope.material == "gypsum"
                else "17 кг/м² на 10 мм"
            ),
            Decimal("1") + _percent(scope.waste_percent),
            (
                "Масса зависит от площади, толщины и запаса; "
                "результат округляется вверх до целых мешков."
            ),
        )
    )
    if scope.application_method == "mechanized":
        rows.extend(
            (
                LinePlan(
                    "water",
                    "Механизмы и ресурсы",
                    "service",
                    "Технологическая вода",
                    "m3",
                    multiply(mix_mass, variable("water_norm")),
                    (
                        "0.55 л/кг"
                        if scope.material == "gypsum"
                        else "0.22 л/кг"
                    ),
                    Decimal("1"),
                    "Расход воды связан с фактической массой сухой смеси.",
                ),
                LinePlan(
                    "electricity",
                    "Механизмы и ресурсы",
                    "service",
                    "Электроэнергия для штукатурной станции",
                    "kWh",
                    multiply(area, variable("machine_energy_norm")),
                    "0.055 кВт·ч/м²",
                    Decimal("1"),
                    "Норма эксплуатации станции на площадь.",
                ),
                LinePlan(
                    "plaster_machine",
                    "Механизмы и ресурсы",
                    "equipment",
                    "Штукатурная станция",
                    "shift",
                    multiply(
                        ceil_formula(
                            divide(area, variable("machine_productivity"))
                        ),
                        variable("one_shift"),
                    ),
                    "180 м²/смену",
                    Decimal("1"),
                    "Количество смен округляется вверх.",
                ),
            )
        )
    rows.extend(
        (
            LinePlan(
                "delivery",
                "Логистика",
                "service",
                "Доставка материалов",
                "trip",
                multiply(
                    ceil_formula(
                        divide(mix_mass, variable("vehicle_payload"))
                    ),
                    variable("one_trip"),
                ),
                "грузоподъёмность 1500 кг",
                Decimal("1"),
                "Число рейсов связано с массой основного материала.",
            ),
            LinePlan(
                "lifting",
                "Логистика",
                "service",
                "Подъём материалов",
                "t",
                mix_mass,
                None,
                Decimal("1"),
                "Масса основного материала переводится из кг в тонны.",
            ),
        )
    )
    if scope.slopes_area_m2 > 0:
        rows.append(
            LinePlan(
                "slopes",
                "Откосы и примыкания",
                "work",
                "Штукатурка откосов",
                "m2",
                variable("slopes_area"),
                None,
                Decimal("1"),
                "Площадь откосов задана отдельно от площади стен.",
            )
        )
    rows.extend(
        (
            LinePlan(
                "smoothing",
                "Финиш",
                "work",
                "Подрезка и финишное заглаживание",
                "m2",
                area,
                None,
                Decimal("1"),
                "Обязательный этап после схватывания.",
            ),
            LinePlan(
                "quality_control",
                "Контроль",
                "work",
                "Контроль плоскостности и качества",
                "m2",
                area,
                None,
                Decimal("1"),
                "Независимый контроль результата по всей площади.",
            ),
            LinePlan(
                "cleanup",
                "Завершение",
                "work",
                "Уборка рабочей зоны",
                "m2",
                area,
                None,
                Decimal("1"),
                "Сбор упаковки и очистка рабочей зоны.",
            ),
        )
    )
    if scope.waste_removal_trips > 0:
        rows.append(
            LinePlan(
                "waste_removal",
                "Завершение",
                "service",
                "Вывоз строительных отходов",
                "trip",
                variable("waste_removal_trips"),
                None,
                Decimal("1"),
                "Число рейсов задано в ProjectCase.",
            )
        )
    rows.append(
        LinePlan(
            "consumables",
            "Расходные материалы",
            "material",
            "Плёнка, лента, крепёж и мелкие расходники",
            "set",
            variable("one_set"),
            None,
            Decimal("1"),
            "Комплект расходников на расчётный объект.",
        )
    )
    return tuple(rows)


def _source_document(source: PriceSource) -> dict[str, Any]:
    return {
        "sourceId": source.source_id,
        "sourceType": source.source_type,
        "label": source.label,
        "reference": source.reference,
        "url": source.url,
        "region": source.region,
        "observedAt": source.observed_at,
        "validUntil": source.valid_until,
        "verified": source.verified,
    }


def _stable_item_id(code: str) -> str:
    digest = hashlib.sha256(
        f"{PLASTER_RULES_VERSION}:{code}".encode("utf-8")
    ).hexdigest()[:24]
    # The deterministic engine ID is also the stable editor row ID.  Keeping a
    # single identity across calculation, persistence and Canvas prevents a
    # second client-side mapping from becoming a source of split-brain edits.
    return f"row_{digest}"


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def content_hash(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(
        canonical_json(value).encode("utf-8")
    ).hexdigest()


def calculate_plastering_estimate(
    *,
    project_case: ProjectCaseRef,
    scope: PlasteringScope,
    prices: Sequence[PriceQuote],
    terms: CommercialTerms = CommercialTerms(),
    require_complete_prices: bool = False,
) -> dict[str, Any]:
    by_code: dict[str, PriceQuote] = {}
    for quote in prices:
        if quote.source.source_type == "ai_candidate":
            raise EstimateEngineError(
                "AI candidate prices cannot participate in estimate arithmetic"
            )
        if quote.item_code in by_code:
            raise EstimateEngineError(
                f"duplicate price quote for {quote.item_code}"
            )
        if quote.source.region != project_case.region:
            raise EstimateEngineError(
                f"price region mismatch for {quote.item_code}"
            )
        by_code[quote.item_code] = quote

    technology_card = build_plastering_technology_card(scope)
    variables = _plastering_variables(scope)
    line_items: list[dict[str, Any]] = []
    missing_prices: list[str] = []
    unverified_prices: list[str] = []
    direct_cost = Decimal("0")
    for plan in _plastering_line_plans(scope):
        quantity = evaluate_formula(
            plan.formula,
            variables,
            target_unit=plan.unit,
        )
        quote = by_code.get(plan.code)
        if quote is not None and quote.unit != plan.unit:
            raise EstimateEngineError(
                f"price unit mismatch for {plan.code}: "
                f"{quote.unit} != {plan.unit}"
            )
        subtotal: Decimal | None = None
        if quote is None:
            missing_prices.append(plan.code)
        else:
            if not quote.source.verified:
                unverified_prices.append(plan.code)
            subtotal = (quantity * quote.unit_price).quantize(
                MONEY_QUANTUM,
                rounding=ROUND_HALF_UP,
            )
            direct_cost += subtotal
        line_items.append(
            {
                "id": _stable_item_id(plan.code),
                "code": plan.code,
                "section": plan.section,
                "kind": plan.kind,
                "title": plan.title,
                "unit": plan.unit,
                "quantityFormula": plan.formula,
                "normalizedQuantity": _decimal_text(quantity),
                "consumptionNorm": plan.consumption_norm,
                "wasteFactor": _decimal_text(plan.waste_factor),
                "unitPrice": _money(quote.unit_price) if quote else None,
                "currency": quote.currency if quote else "RUB",
                "vatMode": quote.vat_mode if quote else "unknown",
                "source": _source_document(quote.source) if quote else None,
                "observedAt": quote.source.observed_at if quote else None,
                "region": project_case.region,
                "confidence": (
                    _decimal_text(quote.confidence) if quote else "0"
                ),
                "subtotal": _money(subtotal) if subtotal is not None else None,
                "explanation": plan.explanation,
            }
        )
    if require_complete_prices and missing_prices:
        raise MissingPriceError(
            "missing prices: " + ", ".join(sorted(missing_prices))
        )
    if require_complete_prices and unverified_prices:
        raise EstimateEngineError(
            "unverified prices: " + ", ".join(sorted(unverified_prices))
        )

    overhead = (direct_cost * _percent(terms.overhead_percent)).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    before_profit = direct_cost + overhead
    profit = (before_profit * _percent(terms.profit_percent)).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    before_discount = before_profit + profit
    discount = (before_discount * _percent(terms.discount_percent)).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    taxable = before_discount - discount
    tax = (taxable * _percent(terms.tax_percent)).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    total = taxable + tax
    project_case_document = {
        "tenantId": project_case.tenant_id,
        "projectId": project_case.project_id,
        "caseId": project_case.case_id,
        "version": project_case.version,
        "region": project_case.region,
    }
    input_document = {
        "projectCase": project_case_document,
        "scope": {
            key: (
                _decimal_text(value)
                if isinstance(value, Decimal)
                else value
            )
            for key, value in asdict(scope).items()
        },
        "priceSnapshot": [
            {
                "itemCode": quote.item_code,
                "unit": quote.unit,
                "unitPrice": _money(quote.unit_price),
                "currency": quote.currency,
                "vatMode": quote.vat_mode,
                "confidence": _decimal_text(quote.confidence),
                "source": _source_document(quote.source),
            }
            for quote in sorted(prices, key=lambda item: item.item_code)
        ],
        "terms": {
            key: _decimal_text(value)
            for key, value in asdict(terms).items()
        },
        "engineVersion": ENGINE_VERSION,
        "rulesVersion": PLASTER_RULES_VERSION,
    }
    result = {
        "schemaId": "kolibri.estimate_calculation",
        "schemaVersion": "1.0",
        "engineVersion": ENGINE_VERSION,
        "rulesVersion": PLASTER_RULES_VERSION,
        "projectCase": project_case_document,
        "inputHash": content_hash(input_document),
        "technologyCard": technology_card.as_document(),
        "items": line_items,
        "totals": {
            "directCost": _money(direct_cost),
            "overhead": _money(overhead),
            "profit": _money(profit),
            "discount": _money(discount),
            "tax": _money(tax),
            "total": _money(total),
            "complete": not missing_prices,
        },
        "validation": {
            "status": (
                "passed"
                if not missing_prices and not unverified_prices
                else "blocked"
            ),
            "missingPriceItemCodes": sorted(missing_prices),
            **(
                {"unverifiedPriceItemCodes": sorted(unverified_prices)}
                if unverified_prices
                else {}
            ),
        },
        "roundingPolicy": {
            "lineSubtotal": "ROUND_HALF_UP:0.01",
            "commercialComponent": "ROUND_HALF_UP:0.01",
            "total": "sum_of_rounded_components",
        },
    }
    result["resultHash"] = content_hash(result)
    return result
