from __future__ import annotations

import json
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)


DECIMAL_TEXT = re.compile(r"^(?:0|[1-9]\d{0,11})(?:\.\d{1,6})?$")
DecimalText = Annotated[
    str,
    StringConstraints(pattern=DECIMAL_TEXT.pattern, min_length=1, max_length=32),
]
AssumptionText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=600),
]
PlasterItemCode = Literal[
    "survey",
    "surface_cleaning",
    "protection",
    "primer_application",
    "primer_material",
    "beacon_installation",
    "beacon_profile",
    "corner_installation",
    "corner_profile",
    "mesh_installation",
    "reinforcing_mesh",
    "plaster_application",
    "plaster_mix",
    "water",
    "electricity",
    "plaster_machine",
    "delivery",
    "lifting",
    "slopes",
    "smoothing",
    "quality_control",
    "cleanup",
    "waste_removal",
    "consumables",
]

PLASTERING_SCOPE_POLICY_VERSION = "plastering-scope/2026-07-29.1"


class IntakeModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class CandidatePrice(IntakeModel):
    item_code: PlasterItemCode = Field(alias="itemCode")
    unit_price: DecimalText = Field(alias="unitPrice")


class PlasteringIntake(IntakeModel):
    title: str = Field(min_length=1, max_length=240)
    region: str = Field(min_length=1, max_length=160)
    wall_area_m2: DecimalText = Field(alias="wallAreaM2")
    average_thickness_mm: DecimalText = Field(alias="averageThicknessMm")
    material: Literal["gypsum", "cement"]
    application_method: Literal["mechanized", "manual"] = Field(
        alias="applicationMethod"
    )
    waste_percent: DecimalText = Field(alias="wastePercent")
    protection_area_m2: DecimalText = Field(alias="protectionAreaM2")
    wall_height_m: DecimalText = Field(alias="wallHeightM")
    beacon_spacing_m: DecimalText = Field(alias="beaconSpacingM")
    corner_length_m: DecimalText = Field(alias="cornerLengthM")
    mesh_area_percent: DecimalText = Field(alias="meshAreaPercent")
    slopes_area_m2: DecimalText = Field(alias="slopesAreaM2")
    plaster_bag_weight_kg: DecimalText = Field(alias="plasterBagWeightKg")
    primer_passes: int = Field(alias="primerPasses", ge=1, le=4)
    waste_removal_trips: DecimalText = Field(alias="wasteRemovalTrips")
    assumptions: list[AssumptionText] = Field(min_length=1, max_length=20)
    # Research proposals only. They are independently checked and retained as
    # candidate evidence, but never become calculation prices by themselves.
    candidate_prices: list[CandidatePrice] = Field(
        alias="candidatePrices",
        max_length=24,
    )

    @model_validator(mode="after")
    def unique_price_codes(self) -> "PlasteringIntake":
        codes = [item.item_code for item in self.candidate_prices]
        if len(codes) != len(set(codes)):
            raise ValueError("candidate price item codes must be unique")
        return self


PLASTERING_INTAKE_SCHEMA = PlasteringIntake.model_json_schema(
    by_alias=True,
    mode="validation",
)


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _number(value: str) -> Decimal:
    return Decimal(value.replace(" ", "").replace(",", "."))


def _match_decimal(prompt: str, patterns: tuple[str, ...]) -> Decimal | None:
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match is not None:
            return _number(match.group(1))
    return None


def _main_wall_area(prompt: str) -> Decimal | None:
    return _match_decimal(
        prompt,
        (
            (
                r"(\d[\d ]*(?:[.,]\d+)?)\s*"
                r"(?:м2|м²|кв\.?\s*м)\s+"
                r"(?:механизированн\w*\s+|ручн\w*\s+)?штукатур"
            ),
            (
                r"(?:площад\w*\s+(?:стен\w*\s*)?|стен\w*\s+)"
                r"(\d[\d ]*(?:[.,]\d+)?)\s*(?:м2|м²|кв\.?\s*м)"
            ),
            r"(\d[\d ]*(?:[.,]\d+)?)\s*(?:м2|м²|кв\.?\s*м)",
        ),
    )


def _named_area(prompt: str, stem: str) -> Decimal | None:
    return _match_decimal(
        prompt,
        (
            (
                rf"{stem}\w*[^0-9]{{0,40}}"
                r"(\d[\d ]*(?:[.,]\d+)?)\s*(?:м2|м²|кв\.?\s*м)"
            ),
        ),
    )


def normalize_plastering_intake(
    intake: PlasteringIntake,
    *,
    prompt: str,
) -> PlasteringIntake:
    """Apply one server-owned scope policy regardless of the selected model.

    The model remains responsible for language understanding and candidate
    evidence.  Numeric defaults that affect arithmetic are owned here.  An
    explicitly stated value wins; otherwise the same versioned default is used
    for MiMo, Codex, retries, and separate browser sessions.
    """

    source = prompt.casefold().replace("\u00a0", " ")
    explicit_area = _main_wall_area(source)
    wall_area = explicit_area or Decimal(intake.wall_area_m2)

    explicit_thickness = _match_decimal(
        source,
        (
            (
                r"(?:сло[йя]|толщин\w*)[^0-9]{0,24}"
                r"(\d+(?:[.,]\d+)?)\s*мм"
            ),
            r"(\d+(?:[.,]\d+)?)\s*мм",
        ),
    )
    thickness = explicit_thickness or Decimal("15")

    explicit_waste = _match_decimal(
        source,
        (
            (
                r"(?:запас\w*|отход\w*|потер\w*)[^0-9]{0,24}"
                r"(\d+(?:[.,]\d+)?)\s*%"
            ),
        ),
    )
    waste = explicit_waste or Decimal("10")

    explicit_protection = _named_area(source, r"(?:защит|укрыт)")
    if re.search(r"(?:без\s+защит|защит\w*\s+не\s+треб)", source):
        protection = Decimal("0")
        explicit_protection = protection
    else:
        protection = explicit_protection or (
            wall_area * Decimal("0.25")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    explicit_height = _match_decimal(
        source,
        (
            (
                r"высот\w*[^0-9]{0,24}"
                r"(\d+(?:[.,]\d+)?)\s*(?:м|метр)"
            ),
        ),
    )
    height = explicit_height or Decimal("3")

    explicit_beacon_spacing = _match_decimal(
        source,
        (
            (
                r"шаг\w*\s+маяк\w*[^0-9]{0,24}"
                r"(\d+(?:[.,]\d+)?)\s*(?:м|метр)"
            ),
        ),
    )
    beacon_spacing = explicit_beacon_spacing or Decimal("1.5")

    explicit_corners = _match_decimal(
        source,
        (
            (
                r"(?:длин\w*\s+)?угл\w*[^0-9]{0,24}"
                r"(\d+(?:[.,]\d+)?)\s*(?:м|метр)"
            ),
        ),
    )
    if re.search(r"(?:без\s+угл|угл\w*\s+не\s+учит)", source):
        explicit_corners = Decimal("0")
    corners = explicit_corners or Decimal("0")

    explicit_mesh = _match_decimal(
        source,
        (
            r"сетк\w*[^0-9]{0,32}(\d+(?:[.,]\d+)?)\s*%",
        ),
    )
    if re.search(r"(?:без\s+сетк|сетк\w*\s+не\s+треб)", source):
        explicit_mesh = Decimal("0")
    mesh = explicit_mesh if explicit_mesh is not None else Decimal("10")

    explicit_slopes = _named_area(source, r"откос")
    if re.search(r"(?:без\s+откос|откос\w*\s+не\s+учит)", source):
        explicit_slopes = Decimal("0")
    slopes = explicit_slopes or Decimal("0")

    explicit_bag_weight = _match_decimal(
        source,
        (
            (
                r"(?:меш\w*|фасовк\w*)[^0-9]{0,24}"
                r"(\d+(?:[.,]\d+)?)\s*кг"
            ),
        ),
    )
    bag_weight = explicit_bag_weight or Decimal("30")

    explicit_primer_passes = _match_decimal(
        source,
        (
            (
                r"грунт\w*[^0-9]{0,32}(\d+)\s*"
                r"(?:проход|сло)"
            ),
        ),
    )
    primer_passes = int(explicit_primer_passes or Decimal("1"))

    explicit_waste_trips = _match_decimal(
        source,
        (
            (
                r"вывоз\w*[^0-9]{0,32}(\d+(?:[.,]\d+)?)\s*"
                r"(?:рейс|поезд)"
            ),
        ),
    )
    waste_trips = explicit_waste_trips or Decimal("1")

    material: Literal["gypsum", "cement"]
    if re.search(r"(?:цемент|цпс|цементно-песчан)", source):
        material = "cement"
    elif re.search(r"(?:гипс|гипсов)", source):
        material = "gypsum"
    else:
        material = "gypsum"

    application_method: Literal["mechanized", "manual"]
    if re.search(r"(?:ручн\w*|вручную)", source):
        application_method = "manual"
    elif re.search(r"(?:механиз|машинн\w*\s+нанес)", source):
        application_method = "mechanized"
    else:
        application_method = "mechanized"

    assumptions = [
        (
            f"Расчётные допущения нормализованы серверной политикой "
            f"{PLASTERING_SCOPE_POLICY_VERSION}."
        )
    ]
    default_notes = (
        (
            explicit_thickness is None,
            "Средняя толщина слоя предварительно принята 15 мм.",
        ),
        (
            explicit_waste is None,
            "Технологический запас предварительно принят 10%.",
        ),
        (
            explicit_protection is None,
            "Площадь защиты предварительно принята как 25% площади стен.",
        ),
        (
            explicit_height is None,
            "Высота стен предварительно принята 3 м.",
        ),
        (
            explicit_beacon_spacing is None,
            "Шаг маяков предварительно принят 1,5 м.",
        ),
        (
            explicit_corners is None,
            "Углы не включены до получения их фактической длины.",
        ),
        (
            explicit_mesh is None,
            "Локальное армирование предварительно принято на 10% площади.",
        ),
        (
            explicit_slopes is None,
            "Откосы не включены до получения их фактической площади.",
        ),
        (
            explicit_bag_weight is None,
            "Фасовка штукатурной смеси предварительно принята 30 кг.",
        ),
        (
            explicit_primer_passes is None,
            "Грунтование предварительно принято в один проход.",
        ),
        (
            explicit_waste_trips is None,
            "Вывоз отходов предварительно принят одним рейсом.",
        ),
    )
    assumptions.extend(text for enabled, text in default_notes if enabled)
    if not re.search(r"(?:цемент|цпс|цементно-песчан|гипс)", source):
        assumptions.append(
            "При отсутствии указания принята гипсовая штукатурная смесь."
        )
    if not re.search(r"(?:ручн\w*|вручную|механиз|машинн\w*\s+нанес)", source):
        assumptions.append(
            "При отсутствии указания принят механизированный способ нанесения."
        )

    method_label = (
        "Механизированная" if application_method == "mechanized" else "Ручная"
    )
    material_label = "гипсовая" if material == "gypsum" else "цементная"
    title = (
        f"{method_label} {material_label} штукатурка стен "
        f"{_decimal_text(wall_area)} м²"
    )
    return intake.model_copy(
        update={
            "title": title,
            "wall_area_m2": _decimal_text(wall_area),
            "average_thickness_mm": _decimal_text(thickness),
            "material": material,
            "application_method": application_method,
            "waste_percent": _decimal_text(waste),
            "protection_area_m2": _decimal_text(protection),
            "wall_height_m": _decimal_text(height),
            "beacon_spacing_m": _decimal_text(beacon_spacing),
            "corner_length_m": _decimal_text(corners),
            "mesh_area_percent": _decimal_text(mesh),
            "slopes_area_m2": _decimal_text(slopes),
            "plaster_bag_weight_kg": _decimal_text(bag_weight),
            "primer_passes": primer_passes,
            "waste_removal_trips": _decimal_text(waste_trips),
            "assumptions": assumptions[:20],
        }
    )


def plastering_intake_instructions(
    *,
    today: str,
    runtime_guidance: str = "",
) -> str:
    """Return the bounded intake prompt for the estimate normalizer.

    ``runtime_guidance`` is supplied only by the server-owned, versioned
    runtime-skill registry.  It is intentionally an optional suffix so old
    callers preserve the exact base contract and a user cannot inject a
    filesystem skill or authority instruction into the system prompt.
    """

    instructions = f"""
Ты нормализатор входных данных строительной сметы Kolibri, дата {today}.
Верни только JSON по schema. Не считай количества, итоги, налоги и формулы:
это делает детерминированный Estimate Engine.

Выдели регион, площадь стен, среднюю толщину, материал и способ нанесения.
Явно заполни технологические условия: защита, высота, шаг маяков, углы,
локальная сетка, откосы, вес мешка, число проходов грунта и вывоз. Если факт
не дан, выбери консервативное предварительное допущение и обязательно опиши
его в assumptions. Не маскируй допущение под факт.

candidatePrices — обязательный массив предварительных рыночных гипотез
снабженца в рублях за
каноническую единицу. Не придумывай URL, продавца или официальный источник.
Kolibri независимо сравнит их с региональным snapshot и пометит как
candidate-only; непосредственно в расчёт они не попадут. Если разумного
кандидата нет, верни пустой массив. Используй только itemCode из schema.

Обязательные технологические этапы не удаляй ради короткой сметы: обследование,
очистка, защита, грунт, маяки, углы и сетка по условиям, смесь, работа,
вода/электричество/станция для механизированного способа, доставка, подъём,
откосы по условиям, финиш, контроль, уборка, вывоз и расходники.
""".strip()
    if not runtime_guidance.strip():
        return instructions
    return f"{instructions}\n\nСерверный контекст текущего этапа:\n{runtime_guidance.strip()}"


def parse_plastering_intake(value: str) -> PlasteringIntake:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        raise ValueError("estimate intake is not valid JSON") from None
    try:
        return PlasteringIntake.model_validate(decoded)
    except ValidationError as exc:
        raise ValueError("estimate intake does not match the schema") from exc
