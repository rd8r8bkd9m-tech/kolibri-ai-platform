"""Durable orchestration primitives for universal construction estimates.

This module owns no HTTP transport and performs no provider calls.  It keeps
the recoverable run journal, immutable ProjectCase/technology snapshots,
source evidence and row lineage while exposing deterministic validation and
expansion functions to the runtime orchestrator.

Run-local technology revisions are proposals.  ``publish_technology_card_revision``
copies an accepted revision into the existing ``technology_cards`` authority;
there is deliberately no second published technology-card store here.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Literal, Mapping, Sequence

from .database import transaction
from .estimate_engine import FormulaError, Quantity, UNITS, UnitDefinition, evaluate_formula


RUN_STATUSES = frozenset(
    {"queued", "running", "needs_input", "review", "ready", "failed", "cancelled"}
)
RUN_STAGES = (
    "project_case",
    "decomposition",
    "technology",
    "research",
    "pricing",
    "expansion",
    "reconciliation",
    "persisting",
    "complete",
)
SECTION_ROLES = (
    "technologist",
    "quantity_engineer",
    "resource_normer",
    "technical_researcher",
    "procurement",
    "logistics",
    "reviewer",
)
TASK_ROLES = frozenset((*SECTION_ROLES, "orchestrator"))
DIRECT_LINE_KINDS = frozenset({"work", "material", "equipment", "service"})
ADJUSTMENT_LINE_KINDS = frozenset({"overhead", "tax", "contingency"})
ESTIMATE_LINE_KINDS = frozenset((*DIRECT_LINE_KINDS, *ADJUSTMENT_LINE_KINDS))
LINE_CONFIDENCE = ("missing", "preliminary", "source_backed", "verified")
EVIDENCE_SOURCE_TYPES = frozenset(
    {
        "user_input",
        "approved_catalog",
        "official_reference",
        "supplier_offer",
        "market_aggregate",
        "ai_candidate",
    }
)
MONEY_QUANTUM = Decimal("0.01")
QUANTITY_QUANTUM = Decimal("0.000001")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{0,159}$")
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_FINAL_RUN_STATUSES = frozenset({"ready", "failed", "cancelled"})
_RUN_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "needs_input", "failed", "cancelled"}),
    "running": frozenset({"needs_input", "review", "ready", "failed", "cancelled"}),
    "needs_input": frozenset({"running", "failed", "cancelled"}),
    "review": frozenset({"running", "needs_input", "ready", "failed", "cancelled"}),
    "ready": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}

_UNIT_ALIASES = {
    "1": "1",
    "%": "1",
    # Storey counts are dimensionless multipliers in ProjectCase formulae.
    # Mapping them to an item/resource dimension would make expressions such
    # as floor area multiplied by floor count dimensionally incorrect.
    "этаж": "1",
    "этажа": "1",
    "этажей": "1",
    "floor": "1",
    "floors": "1",
    "m": "m",
    "м": "m",
    "mm": "mm",
    "мм": "mm",
    "m2": "m2",
    "m²": "m2",
    "м2": "m2",
    "м²": "m2",
    "m3": "m3",
    "m³": "m3",
    "м3": "m3",
    "м³": "m3",
    "kg": "kg",
    "кг": "kg",
    "t": "t",
    "т": "t",
    "l": "l",
    "л": "l",
    "kwh": "kWh",
    "квт·ч": "kWh",
    "квтч": "kWh",
    "ea": "ea",
    "шт": "ea",
    "шт.": "ea",
    "bag": "bag",
    "мешок": "bag",
    "shift": "shift",
    "смена": "shift",
    "trip": "trip",
    "рейс": "trip",
    "set": "set",
    "комплект": "set",
    "компл.": "set",
    "компл": "set",
    "kg_per_m2": "kg_per_m2",
    "кг/м²": "kg_per_m2",
    "l_per_m2": "l_per_m2",
    "л/м²": "l_per_m2",
    "l_per_kg": "l_per_kg",
    "л/кг": "l_per_kg",
    "kwh_per_m2": "kwh_per_m2",
    "квт·ч/м²": "kwh_per_m2",
    "п.м.": "m",
    "п.м": "m",
    "пог.м": "m",
    "м.п.": "m",
    "м.п": "m",
    "labor_h": "labor_h",
    "чел.-ч": "labor_h",
    "чел.ч": "labor_h",
    "чел-ч": "labor_h",
    "человеко-час": "labor_h",
    "machine_h": "machine_h",
    "маш.-ч": "machine_h",
    "маш.ч": "machine_h",
    "маш-ч": "machine_h",
    "машино-час": "machine_h",
    "package": "package",
    "упак.": "package",
    "упак": "package",
    "уп.": "package",
    "упаковка": "package",
    "roll": "roll",
    "рул.": "roll",
    "рулон": "roll",
    "pair": "pair",
    "пара": "pair",
    "day": "day",
    "дн.": "day",
    "день": "day",
    "сут.": "day",
    "month": "month",
    "мес.": "month",
    "m2_per_shift": "m2_per_shift",
    "м²/смену": "m2_per_shift",
    "m3_per_shift": "m3_per_shift",
    "м³/смену": "m3_per_shift",
    "ea_per_shift": "ea_per_shift",
    "шт./смену": "ea_per_shift",
    "h_per_m2": "h_per_m2",
    "чел.-ч/м²": "h_per_m2",
    "machine_h_per_m2": "machine_h_per_m2",
    "маш.-ч/м²": "machine_h_per_m2",
    "m_per_m2": "m_per_m2",
    "м/м²": "m_per_m2",
    "ea_per_m2": "ea_per_m2",
    "шт./м²": "ea_per_m2",
    "kg_per_m3": "kg_per_m3",
    "кг/м³": "kg_per_m3",
}


def _extended_unit(symbol: str, dimensions: Mapping[str, int], factor: str = "1") -> UnitDefinition:
    return UnitDefinition(
        symbol=symbol,
        dimensions=tuple(sorted((name, power) for name, power in dimensions.items() if power)),
        to_base=Decimal(factor),
    )


# Universal cards use common labor, machine and packaging dimensions which
# predate the plastering-only engine vocabulary.  The additions are stable and
# do not alter any existing conversion factor.
UNITS.setdefault("labor_h", _extended_unit("labor_h", {"labor_time": 1}))
UNITS.setdefault("machine_h", _extended_unit("machine_h", {"machine_time": 1}))
UNITS.setdefault("package", _extended_unit("package", {"package": 1}))
UNITS.setdefault("roll", _extended_unit("roll", {"roll": 1}))
UNITS.setdefault("pair", _extended_unit("pair", {"pair": 1}))
UNITS.setdefault("day", _extended_unit("day", {"day": 1}))
UNITS.setdefault("month", _extended_unit("month", {"month": 1}))
UNITS.setdefault("m2_per_shift", _extended_unit("m2_per_shift", {"length": 2, "shift": -1}))
UNITS.setdefault("m3_per_shift", _extended_unit("m3_per_shift", {"volume": 1, "shift": -1}))
UNITS.setdefault("ea_per_shift", _extended_unit("ea_per_shift", {"item": 1, "shift": -1}))
UNITS.setdefault("h_per_m2", _extended_unit("h_per_m2", {"labor_time": 1, "length": -2}))
UNITS.setdefault(
    "machine_h_per_m2",
    _extended_unit("machine_h_per_m2", {"machine_time": 1, "length": -2}),
)
UNITS.setdefault("m_per_m2", _extended_unit("m_per_m2", {"length": -1}))
UNITS.setdefault("ea_per_m2", _extended_unit("ea_per_m2", {"item": 1, "length": -2}))
UNITS.setdefault("kg_per_m3", _extended_unit("kg_per_m3", {"mass": 1, "volume": -1}))


class EstimateGenerationError(ValueError):
    """Base error for deterministic generation or persistence failures."""


class ValidationFailure(EstimateGenerationError):
    """Raised when a ProjectCase, technology card or expansion is invalid."""


class StateConflict(EstimateGenerationError):
    """Raised when an optimistic durable-state transition cannot be applied."""


class IdempotencyConflict(StateConflict):
    """Raised when an idempotency key is reused for different input."""


class NotFound(EstimateGenerationError):
    """Raised when a tenant-scoped durable object does not exist."""


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    path: str
    message: str
    severity: Literal["error", "warning"] = "error"

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass(frozen=True, slots=True)
class ValidationReport:
    status: Literal["passed", "failed", "needs_input"]
    issues: tuple[ValidationIssue, ...]
    metrics: Mapping[str, int]

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def as_dict(self) -> dict[str, Any]:
        errors = sum(issue.severity == "error" for issue in self.issues)
        warnings = sum(issue.severity == "warning" for issue in self.issues)
        return {
            "status": self.status,
            "issues": [issue.as_dict() for issue in self.issues],
            "errors": errors,
            "warnings": warnings,
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True, slots=True)
class ExpansionResult:
    rows: tuple[dict[str, Any], ...]
    totals: Mapping[str, str]
    content_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows": [dict(row) for row in self.rows],
            "totals": dict(self.totals),
            "contentHash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    status: Literal["passed", "failed", "needs_input"]
    issues: tuple[ValidationIssue, ...]
    metrics: Mapping[str, int]
    totals: Mapping[str, str]

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "issues": [issue.as_dict() for issue in self.issues],
            "metrics": dict(self.metrics),
            "totals": dict(self.totals),
        }


def canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValidationFailure("value is not canonical JSON") from exc


def content_hash(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _json(raw: object, default: Any) -> Any:
    if not isinstance(raw, str):
        return default
    try:
        return json.loads(raw)
    except TypeError, ValueError:
        return default


def _now(database: sqlite3.Connection, supplied: str | None = None) -> str:
    if supplied is not None:
        return _parse_time(supplied).isoformat(timespec="seconds").replace("+00:00", "Z")
    return str(database.execute("SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')").fetchone()[0])


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationFailure("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValidationFailure("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _parse_date(value: str, *, field: str) -> date:
    try:
        return date.fromisoformat(value[:10])
    except (TypeError, ValueError) as exc:
        raise ValidationFailure(f"{field} must start with ISO-8601 date") from exc


def _later(value: str, seconds: int) -> str:
    if not 1 <= seconds <= 86_400:
        raise ValidationFailure("lease_seconds must be between 1 and 86400")
    return (
        (_parse_time(value) + timedelta(seconds=seconds))
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _key_hash(value: str) -> str:
    if not isinstance(value, str) or not 16 <= len(value) <= 240:
        raise ValidationFailure("idempotency_key must contain 16..240 characters")
    return hashlib.sha256(value.encode("utf-8", "strict")).hexdigest()


def _request_hash(value: object) -> str:
    return content_hash(value)


def _text(value: object, *, field: str, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationFailure(f"{field} is required")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ValidationFailure(f"{field} exceeds {maximum} characters")
    return normalized


def _identifier(value: object, *, field: str) -> str:
    text = _text(value, field=field, maximum=160)
    if _IDENTIFIER.fullmatch(text) is None:
        raise ValidationFailure(f"{field} is not a stable identifier")
    return text


def _decimal(value: object, *, field: str, non_negative: bool = True) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except InvalidOperation, ValueError:
        raise ValidationFailure(f"{field} must be decimal") from None
    if not parsed.is_finite():
        raise ValidationFailure(f"{field} must be finite")
    if non_negative and parsed < 0:
        raise ValidationFailure(f"{field} cannot be negative")
    return parsed


def _decimal_text(value: Decimal) -> str:
    normalized = format(value.quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def _money(value: Decimal) -> str:
    return format(value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP), ".2f")


def _field(value: Mapping[str, Any], snake: str, camel: str | None = None) -> Any:
    if snake in value:
        return value[snake]
    return value.get(camel or snake)


def _unit(value: object, *, field: str) -> str:
    raw = _text(value, field=field, maximum=32)
    normalized = raw.casefold().replace("^2", "²").replace("^3", "³")
    try:
        return _UNIT_ALIASES[normalized]
    except KeyError:
        if raw in _UNIT_ALIASES.values():
            return raw
        raise ValidationFailure(f"{field} uses unsupported unit: {raw}") from None


def _normalize_formula(expression: object, *, path: str, depth: int = 0) -> dict[str, Any]:
    if depth > 24 or not isinstance(expression, Mapping):
        raise ValidationFailure(f"{path} is not a safe quantity formula")
    operation = expression.get("op")
    if operation == "variable":
        return {"op": "variable", "name": _identifier(expression.get("name"), field=f"{path}.name")}
    if operation == "constant":
        value = _decimal(expression.get("value"), field=f"{path}.value", non_negative=False)
        return {
            "op": "constant",
            "value": _decimal_text(value),
            "unit": _unit(expression.get("unit", "1"), field=f"{path}.unit"),
        }
    if operation in {"multiply", "add"}:
        items = expression.get("items")
        if not isinstance(items, list) or not 2 <= len(items) <= 12:
            raise ValidationFailure(f"{path}.items must contain 2..12 formulae")
        return {
            "op": operation,
            "items": [
                _normalize_formula(item, path=f"{path}.items[{index}]", depth=depth + 1)
                for index, item in enumerate(items)
            ],
        }
    if operation == "divide":
        return {
            "op": "divide",
            "numerator": _normalize_formula(
                expression.get("numerator"), path=f"{path}.numerator", depth=depth + 1
            ),
            "denominator": _normalize_formula(
                expression.get("denominator"), path=f"{path}.denominator", depth=depth + 1
            ),
        }
    if operation == "ceil":
        return {
            "op": "ceil",
            "value": _normalize_formula(
                expression.get("value"), path=f"{path}.value", depth=depth + 1
            ),
        }
    raise ValidationFailure(f"{path}.op is not allowlisted")


def _project_variables(project_case: Mapping[str, Any]) -> dict[str, Quantity]:
    raw_variables = project_case.get("variables")
    if not isinstance(raw_variables, Mapping):
        raise ValidationFailure("project_case.variables must be an object")
    variables: dict[str, Quantity] = {}
    for raw_name, raw_value in raw_variables.items():
        name = _identifier(raw_name, field="project_case.variables key")
        if not isinstance(raw_value, Mapping):
            raise ValidationFailure(f"project_case.variables.{name} must be an object")
        value = _decimal(
            raw_value.get("value"), field=f"project_case.variables.{name}.value", non_negative=False
        )
        unit = _unit(raw_value.get("unit"), field=f"project_case.variables.{name}.unit")
        variables[name] = Quantity.of(value, unit)
    return variables


def _evaluate_quantity(
    formula: object,
    *,
    variables: Mapping[str, Quantity],
    target_unit: object,
    path: str,
) -> tuple[Decimal, dict[str, Any]]:
    normalized = _normalize_formula(formula, path=path)
    unit = _unit(target_unit, field=f"{path}.targetUnit")
    try:
        value = evaluate_formula(normalized, variables, target_unit=unit)
    except FormulaError as exc:
        raise ValidationFailure(f"{path} is dimensionally invalid: {exc}") from exc
    return value, normalized


def validate_project_case(snapshot: Mapping[str, Any]) -> ValidationReport:
    """Validate an analysed ProjectCase without rejecting a pending seed."""

    issues: list[ValidationIssue] = []
    if not isinstance(snapshot, Mapping):
        return ValidationReport(
            status="failed",
            issues=(
                ValidationIssue(
                    "project_case_not_object", "$", "ProjectCase must be a JSON object."
                ),
            ),
            metrics={"variables": 0, "assumptions": 0, "blockingQuestions": 0},
        )
    analysis_status = str(snapshot.get("analysisStatus") or "analysed")
    if analysis_status not in {"pending", "analysed"}:
        issues.append(
            ValidationIssue(
                "analysis_status_invalid",
                "$.analysisStatus",
                "analysisStatus must be pending or analysed.",
            )
        )
    region = str(snapshot.get("region") or "").strip()
    if not region or region == "Регион не указан":
        issues.append(
            ValidationIssue(
                "region_missing", "$.region", "Region must be confirmed before calculation."
            )
        )
    currency = str(snapshot.get("currency") or "RUB").strip()
    if currency != "RUB":
        issues.append(
            ValidationIssue(
                "currency_unsupported", "$.currency", "Only RUB is currently authoritative."
            )
        )
    if analysis_status == "analysed" and not isinstance(snapshot.get("object"), Mapping):
        issues.append(
            ValidationIssue(
                "object_missing",
                "$.object",
                "Analysed ProjectCase should describe the construction object.",
                "warning",
            )
        )
    variables = snapshot.get("variables")
    variable_count = len(variables) if isinstance(variables, Mapping) else 0
    if analysis_status == "analysed" and not isinstance(variables, Mapping):
        issues.append(
            ValidationIssue(
                "variables_missing",
                "$.variables",
                "Analysed ProjectCase must declare dimensioned variables.",
            )
        )
    elif isinstance(variables, Mapping):
        for raw_name, raw_value in variables.items():
            path = f"$.variables.{raw_name}"
            try:
                _identifier(raw_name, field=path)
                if not isinstance(raw_value, Mapping):
                    raise ValidationFailure(f"{path} must be an object")
                _decimal(raw_value.get("value"), field=f"{path}.value", non_negative=False)
                _unit(raw_value.get("unit"), field=f"{path}.unit")
                basis = raw_value.get("basis")
                source = raw_value.get("source")
                if not (
                    isinstance(basis, str)
                    and basis.strip()
                    or isinstance(source, Mapping)
                    and source
                ):
                    raise ValidationFailure(f"{path} must carry basis or source provenance")
            except ValidationFailure as exc:
                issues.append(ValidationIssue("variable_invalid", path, str(exc)))
    assumptions = snapshot.get("assumptions", [])
    if not isinstance(assumptions, list):
        issues.append(
            ValidationIssue("assumptions_invalid", "$.assumptions", "assumptions must be an array.")
        )
        assumptions = []
    for index, assumption in enumerate(assumptions):
        path = f"$.assumptions[{index}]"
        if isinstance(assumption, str) and assumption.strip():
            issues.append(
                ValidationIssue(
                    "assumption_provenance_missing",
                    path,
                    "Assumption is explicit but should declare basis and impact.",
                    "warning",
                )
            )
            continue
        if not isinstance(assumption, Mapping):
            issues.append(
                ValidationIssue("assumption_invalid", path, "Assumption must be text or object.")
            )
            continue
        for field in ("text", "basis", "impact"):
            if not isinstance(assumption.get(field), str) or not str(assumption.get(field)).strip():
                issues.append(
                    ValidationIssue(
                        "assumption_field_missing",
                        f"{path}.{field}",
                        f"Assumption {field} is required.",
                    )
                )
    blocking = snapshot.get("blockingQuestions", [])
    if not isinstance(blocking, list):
        issues.append(
            ValidationIssue(
                "blocking_questions_invalid",
                "$.blockingQuestions",
                "blockingQuestions must be an array.",
            )
        )
        blocking = []
    for index, question in enumerate(blocking):
        if not isinstance(question, (str, Mapping)):
            issues.append(
                ValidationIssue(
                    "blocking_question_invalid",
                    f"$.blockingQuestions[{index}]",
                    "Blocking question must be text or an object.",
                )
            )
    hard_errors = [issue for issue in issues if issue.severity == "error"]
    if analysis_status == "pending":
        status: Literal["passed", "failed", "needs_input"] = "needs_input"
    elif hard_errors or blocking:
        status = "needs_input"
    else:
        status = "passed"
    return ValidationReport(
        status=status,
        issues=tuple(issues),
        metrics={
            "variables": variable_count,
            "assumptions": len(assumptions),
            "blockingQuestions": len(blocking),
        },
    )


def _card_collections(
    technology_card: Mapping[str, Any],
) -> tuple[list[Any], list[Any]]:
    sections = technology_card.get("sections")
    operations = technology_card.get("operations")
    return (
        sections if isinstance(sections, list) else [],
        operations if isinstance(operations, list) else [],
    )


def validate_technology_card(
    project_case: Mapping[str, Any],
    technology_card: Mapping[str, Any],
) -> ValidationReport:
    """Validate graph, formulas, resource atomization and duplicate safety."""

    issues: list[ValidationIssue] = []
    project_report = validate_project_case(project_case)
    if project_report.status != "passed":
        issues.append(
            ValidationIssue(
                "project_case_not_ready",
                "$.projectCase",
                "Technology card cannot pass before ProjectCase is analysed.",
            )
        )
    if not isinstance(technology_card, Mapping):
        return ValidationReport(
            status="failed",
            issues=(
                ValidationIssue(
                    "technology_card_not_object", "$", "Technology card must be an object."
                ),
            ),
            metrics={"sections": 0, "operations": 0, "resources": 0},
        )
    rules_version = technology_card.get("rulesVersion")
    if not isinstance(rules_version, str) or not rules_version.strip():
        issues.append(
            ValidationIssue("rules_version_missing", "$.rulesVersion", "rulesVersion is required.")
        )
    sections, operations = _card_collections(technology_card)
    if not sections:
        issues.append(
            ValidationIssue("sections_missing", "$.sections", "At least one section is required.")
        )
    if not operations:
        issues.append(
            ValidationIssue(
                "operations_missing", "$.operations", "At least one operation is required."
            )
        )

    section_keys: set[str] = set()
    section_paths: dict[str, str] = {}
    for index, raw_section in enumerate(sections):
        path = f"$.sections[{index}]"
        if not isinstance(raw_section, Mapping):
            issues.append(ValidationIssue("section_invalid", path, "Section must be an object."))
            continue
        try:
            key = _identifier(
                _field(raw_section, "section_key", "sectionKey"), field=f"{path}.sectionKey"
            )
            _text(raw_section.get("title"), field=f"{path}.title", maximum=240)
            _text(
                _field(raw_section, "wbs_path", "wbsPath") or key,
                field=f"{path}.wbsPath",
                maximum=500,
            )
        except ValidationFailure as exc:
            issues.append(ValidationIssue("section_invalid", path, str(exc)))
            continue
        if key in section_keys:
            issues.append(
                ValidationIssue(
                    "section_duplicate", f"{path}.sectionKey", f"Duplicate section {key}."
                )
            )
        section_keys.add(key)
        section_paths[key] = path

    try:
        variables = _project_variables(project_case)
    except ValidationFailure as exc:
        variables = {}
        issues.append(ValidationIssue("project_variables_invalid", "$.projectCase", str(exc)))

    operation_ids: set[str] = set()
    predecessors: dict[str, list[str]] = {}
    resource_ids: set[str] = set()
    duplicate_signatures: dict[tuple[str, str, str, str], str] = {}
    resource_count = 0
    operation_paths: dict[str, str] = {}
    for index, raw_operation in enumerate(operations):
        path = f"$.operations[{index}]"
        if not isinstance(raw_operation, Mapping):
            issues.append(
                ValidationIssue("operation_invalid", path, "Operation must be an object.")
            )
            continue
        try:
            operation_id = _identifier(
                _field(raw_operation, "operation_id", "operationId"),
                field=f"{path}.operationId",
            )
            section_key = _identifier(
                _field(raw_operation, "section_key", "sectionKey"),
                field=f"{path}.sectionKey",
            )
            _text(raw_operation.get("title"), field=f"{path}.title", maximum=300)
            _text(raw_operation.get("method"), field=f"{path}.method", maximum=2_000)
            operation_unit = _field(raw_operation, "unit", "unit")
            _text(
                _field(raw_operation, "quantity_basis", "quantityBasis"),
                field=f"{path}.quantityBasis",
                maximum=2_000,
            )
            _evaluate_quantity(
                _field(raw_operation, "quantity_formula", "quantityFormula"),
                variables=variables,
                target_unit=operation_unit,
                path=f"{path}.quantityFormula",
            )
        except ValidationFailure as exc:
            issues.append(ValidationIssue("operation_invalid", path, str(exc)))
            continue
        if operation_id in operation_ids:
            issues.append(
                ValidationIssue(
                    "operation_duplicate",
                    f"{path}.operationId",
                    f"Duplicate operation {operation_id}.",
                )
            )
        operation_ids.add(operation_id)
        operation_paths[operation_id] = path
        if section_key not in section_keys:
            issues.append(
                ValidationIssue(
                    "operation_section_missing",
                    f"{path}.sectionKey",
                    f"Unknown section {section_key}.",
                )
            )
        raw_predecessors = raw_operation.get("predecessors", [])
        if not isinstance(raw_predecessors, list):
            issues.append(
                ValidationIssue(
                    "predecessors_invalid",
                    f"{path}.predecessors",
                    "predecessors must be an array.",
                )
            )
            raw_predecessors = []
        predecessor_ids: list[str] = []
        for predecessor in raw_predecessors:
            try:
                predecessor_ids.append(_identifier(predecessor, field=f"{path}.predecessors"))
            except ValidationFailure as exc:
                issues.append(ValidationIssue("predecessor_invalid", path, str(exc)))
        predecessors[operation_id] = predecessor_ids

        controls = _field(raw_operation, "quality_controls", "qualityControls")
        if not isinstance(controls, list) or not controls:
            issues.append(
                ValidationIssue(
                    "quality_controls_missing",
                    f"{path}.qualityControls",
                    "Every operation must define at least one quality control.",
                )
            )
        evidence_ids = _field(raw_operation, "evidence_ids", "evidenceIds")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            issues.append(
                ValidationIssue(
                    "operation_evidence_missing",
                    f"{path}.evidenceIds",
                    "Operation should link technical or normative evidence.",
                    "warning",
                )
            )
        resources = raw_operation.get("resources")
        if not isinstance(resources, list) or not resources:
            issues.append(
                ValidationIssue(
                    "operation_resources_missing",
                    f"{path}.resources",
                    "Every operation must expand to atomic resources.",
                )
            )
            continue
        direct_work_count = 0
        for resource_index, raw_resource in enumerate(resources):
            resource_count += 1
            resource_path = f"{path}.resources[{resource_index}]"
            if not isinstance(raw_resource, Mapping):
                issues.append(
                    ValidationIssue(
                        "resource_invalid", resource_path, "Resource must be an object."
                    )
                )
                continue
            try:
                resource_id = _identifier(
                    _field(raw_resource, "resource_id", "resourceId"),
                    field=f"{resource_path}.resourceId",
                )
                kind = _text(raw_resource.get("kind"), field=f"{resource_path}.kind", maximum=32)
                if kind not in ESTIMATE_LINE_KINDS:
                    raise ValidationFailure(f"{resource_path}.kind is unsupported")
                title = _text(
                    raw_resource.get("title"), field=f"{resource_path}.title", maximum=300
                )
                if kind in DIRECT_LINE_KINDS:
                    unit = _text(
                        raw_resource.get("unit"), field=f"{resource_path}.unit", maximum=32
                    )
                    _text(
                        _field(raw_resource, "quantity_basis", "quantityBasis"),
                        field=f"{resource_path}.quantityBasis",
                        maximum=2_000,
                    )
                    _evaluate_quantity(
                        _field(raw_resource, "quantity_formula", "quantityFormula"),
                        variables=variables,
                        target_unit=unit,
                        path=f"{resource_path}.quantityFormula",
                    )
                    direct_work_count += kind == "work"
                else:
                    rate = _decimal(
                        _field(raw_resource, "rate_percent", "ratePercent"),
                        field=f"{resource_path}.ratePercent",
                    )
                    if rate > 100:
                        raise ValidationFailure(f"{resource_path}.ratePercent cannot exceed 100")
                    base_kinds = _field(raw_resource, "base_kinds", "baseKinds")
                    if not isinstance(base_kinds, list) or not base_kinds:
                        raise ValidationFailure(f"{resource_path}.baseKinds is required")
                    if any(value not in ESTIMATE_LINE_KINDS for value in base_kinds):
                        raise ValidationFailure(
                            f"{resource_path}.baseKinds contains unsupported kind"
                        )
                    if kind in base_kinds:
                        raise ValidationFailure(f"{resource_path}.baseKinds cannot include itself")
                    _text(
                        _field(raw_resource, "calculation_basis", "calculationBasis"),
                        field=f"{resource_path}.calculationBasis",
                        maximum=2_000,
                    )
            except ValidationFailure as exc:
                issues.append(ValidationIssue("resource_invalid", resource_path, str(exc)))
                continue
            if resource_id in resource_ids:
                issues.append(
                    ValidationIssue(
                        "resource_id_duplicate",
                        f"{resource_path}.resourceId",
                        f"Duplicate resource {resource_id}.",
                    )
                )
            resource_ids.add(resource_id)
            signature = (
                section_key,
                kind,
                " ".join(title.casefold().split()),
                str(raw_resource.get("unit") or ""),
            )
            previous_path = duplicate_signatures.get(signature)
            duplicate_reason = _field(
                raw_resource, "allow_duplicate_reason", "allowDuplicateReason"
            )
            if previous_path is not None and not (
                isinstance(duplicate_reason, str) and duplicate_reason.strip()
            ):
                issues.append(
                    ValidationIssue(
                        "resource_duplicate_unexplained",
                        resource_path,
                        f"Resource duplicates {previous_path} without allowDuplicateReason.",
                    )
                )
            duplicate_signatures[signature] = resource_path
        if direct_work_count == 0:
            issues.append(
                ValidationIssue(
                    "operation_work_missing",
                    f"{path}.resources",
                    "Every technology operation must contain an atomic work line.",
                )
            )

    for operation_id, values in predecessors.items():
        path = operation_paths.get(operation_id, "$.operations")
        for predecessor in values:
            if predecessor == operation_id:
                issues.append(
                    ValidationIssue(
                        "predecessor_self_reference",
                        f"{path}.predecessors",
                        "Operation cannot depend on itself.",
                    )
                )
            elif predecessor not in operation_ids:
                issues.append(
                    ValidationIssue(
                        "predecessor_missing",
                        f"{path}.predecessors",
                        f"Unknown predecessor {predecessor}.",
                    )
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(operation_id: str) -> bool:
        if operation_id in visiting:
            return False
        if operation_id in visited:
            return True
        visiting.add(operation_id)
        for predecessor in predecessors.get(operation_id, []):
            if predecessor in operation_ids and not visit(predecessor):
                return False
        visiting.remove(operation_id)
        visited.add(operation_id)
        return True

    if any(not visit(operation_id) for operation_id in sorted(operation_ids)):
        issues.append(
            ValidationIssue(
                "operation_cycle", "$.operations", "Technology predecessor graph contains a cycle."
            )
        )
    status: Literal["passed", "failed", "needs_input"] = (
        "failed" if any(issue.severity == "error" for issue in issues) else "passed"
    )
    return ValidationReport(
        status=status,
        issues=tuple(issues),
        metrics={
            "sections": len(section_keys),
            "operations": len(operation_ids),
            "resources": resource_count,
        },
    )


def _evidence_field(evidence: Mapping[str, Any], snake: str, camel: str) -> Any:
    return evidence.get(snake) if snake in evidence else evidence.get(camel)


def _price_from_evidence(
    evidence: Mapping[str, Any],
    *,
    evidence_id: str,
    project_region: str,
    resource_unit: str,
) -> tuple[Decimal, str, dict[str, Any]]:
    kind = str(_evidence_field(evidence, "kind", "kind") or "")
    if kind != "price":
        raise ValidationFailure(f"evidence {evidence_id} is not price evidence")
    confidence = str(_evidence_field(evidence, "confidence_status", "confidenceStatus") or "")
    if confidence not in LINE_CONFIDENCE[1:]:
        raise ValidationFailure(f"evidence {evidence_id} confidence is invalid")
    region = str(_evidence_field(evidence, "region", "region") or "").strip()
    if region != project_region:
        raise ValidationFailure(
            f"evidence {evidence_id} region mismatch: {region!r} != {project_region!r}"
        )
    evidence_unit = _unit(
        _evidence_field(evidence, "unit", "unit"), field=f"evidence.{evidence_id}.unit"
    )
    if evidence_unit != _unit(resource_unit, field="resource.unit"):
        raise ValidationFailure(f"evidence {evidence_id} unit does not match resource")
    price = _decimal(
        _evidence_field(evidence, "unit_price", "unitPrice"),
        field=f"evidence.{evidence_id}.unitPrice",
    )
    source_title = str(_evidence_field(evidence, "source_title", "sourceTitle") or "Источник цены")
    source_reference = str(_evidence_field(evidence, "source_reference", "sourceReference") or "")
    observed_at = str(_evidence_field(evidence, "observed_at", "observedAt") or "")
    price_basis = f"{source_title} · {source_reference} · {observed_at} · {confidence}"[:500]
    payload = {
        "evidence_id": evidence_id,
        "source_type": _evidence_field(evidence, "source_type", "sourceType"),
        "source_title": source_title,
        "source_uri": _evidence_field(evidence, "source_uri", "sourceUri"),
        "source_reference": source_reference,
        "snapshot_hash": _evidence_field(evidence, "snapshot_hash", "snapshotHash"),
        "region": region,
        "unit": resource_unit,
        "unit_price": _money(price),
        "observed_at": observed_at,
        "valid_until": _evidence_field(evidence, "valid_until", "validUntil"),
        "tax_treatment": _evidence_field(evidence, "tax_treatment", "taxTreatment"),
        "delivery_treatment": _evidence_field(evidence, "delivery_treatment", "deliveryTreatment"),
        "confidence_status": confidence,
    }
    return price, price_basis, payload


def _stable_row_id(revision_id: str, operation_id: str, resource_id: str) -> str:
    digest = hashlib.sha256(
        f"{revision_id}\x1f{operation_id}\x1f{resource_id}".encode("utf-8", "strict")
    ).hexdigest()[:32]
    return f"row_{digest}"


def expand_technology_card(
    project_case: Mapping[str, Any],
    technology_card: Mapping[str, Any],
    *,
    revision_id: str,
    evidence_by_id: Mapping[str, Mapping[str, Any]],
) -> ExpansionResult:
    """Deterministically expand operations into atomic, linked estimate rows."""

    revision_id = _identifier(revision_id, field="revision_id")
    validation = validate_technology_card(project_case, technology_card)
    if not validation.passed:
        raise ValidationFailure(
            "technology card failed validation: "
            + "; ".join(issue.code for issue in validation.issues if issue.severity == "error")
        )
    variables = _project_variables(project_case)
    project_region = _text(project_case.get("region"), field="project_case.region", maximum=160)
    sections, operations = _card_collections(technology_card)
    section_by_key: dict[str, Mapping[str, Any]] = {}
    for section in sections:
        if isinstance(section, Mapping):
            key = str(_field(section, "section_key", "sectionKey"))
            section_by_key[key] = section

    direct_rows: list[dict[str, Any]] = []
    adjustments: list[tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]] = []
    for operation in operations:
        if not isinstance(operation, Mapping):
            continue
        operation_id = str(_field(operation, "operation_id", "operationId"))
        section_key = str(_field(operation, "section_key", "sectionKey"))
        section = section_by_key[section_key]
        section_title = str(section.get("title"))
        wbs_path = str(_field(section, "wbs_path", "wbsPath") or section_key)
        for resource in operation.get("resources", []):
            if not isinstance(resource, Mapping):
                continue
            kind = str(resource.get("kind"))
            if kind in ADJUSTMENT_LINE_KINDS:
                adjustments.append((operation, section, resource))
                continue
            resource_id = str(_field(resource, "resource_id", "resourceId"))
            quantity, normalized_formula = _evaluate_quantity(
                _field(resource, "quantity_formula", "quantityFormula"),
                variables=variables,
                target_unit=resource.get("unit"),
                path=f"resource.{resource_id}.quantityFormula",
            )
            display_unit = str(resource.get("unit"))
            evidence_id_value = _field(resource, "price_evidence_id", "priceEvidenceId")
            evidence_id = str(evidence_id_value) if evidence_id_value else None
            price = Decimal("0")
            price_basis = "Цена отсутствует; строка требует снабженческого исследования."
            confidence = "missing"
            price_evidence: dict[str, Any] | None = None
            if evidence_id is not None:
                evidence = evidence_by_id.get(evidence_id)
                if evidence is None:
                    raise ValidationFailure(f"price evidence {evidence_id} is not registered")
                price, price_basis, price_evidence = _price_from_evidence(
                    evidence,
                    evidence_id=evidence_id,
                    project_region=project_region,
                    resource_unit=display_unit,
                )
                confidence = str(_evidence_field(evidence, "confidence_status", "confidenceStatus"))
            line_total = (quantity * price).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
            row: dict[str, Any] = {
                "id": _stable_row_id(revision_id, operation_id, resource_id),
                "section": section_title,
                "section_key": section_key,
                "wbs_path": wbs_path,
                "kind": kind,
                "description": str(resource.get("title")),
                "specification": (
                    dict(resource.get("specification"))
                    if isinstance(resource.get("specification"), Mapping)
                    else {}
                ),
                "unit": display_unit,
                "quantity": _decimal_text(quantity),
                "quantity_formula": normalized_formula,
                "quantity_basis": str(_field(resource, "quantity_basis", "quantityBasis"))[:500],
                "unit_price": _money(price),
                "price_basis": price_basis,
                "line_total": _money(line_total),
                "line_confidence": confidence,
                "operation_id": operation_id,
                "resource_id": resource_id,
                "technology_card_revision_id": revision_id,
                # Public EstimateEditor currently calls this linkage a version.
                # It is the immutable run revision ID until publication.
                "technology_card_version": revision_id,
                "evidence_id": evidence_id,
            }
            if price_evidence is not None:
                row["price_evidence"] = price_evidence
            direct_rows.append(row)

    rows = direct_rows
    for operation, section, resource in adjustments:
        operation_id = str(_field(operation, "operation_id", "operationId"))
        resource_id = str(_field(resource, "resource_id", "resourceId"))
        kind = str(resource.get("kind"))
        base_kinds = [str(value) for value in _field(resource, "base_kinds", "baseKinds")]
        rate = _decimal(
            _field(resource, "rate_percent", "ratePercent"),
            field=f"resource.{resource_id}.ratePercent",
        )
        base = sum(
            (
                _decimal(row["line_total"], field=f"row.{row['id']}.line_total")
                for row in rows
                if row["kind"] in base_kinds
            ),
            Decimal("0"),
        )
        amount = (base * rate / Decimal("100")).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        evidence_id_value = _field(resource, "price_evidence_id", "priceEvidenceId")
        evidence_id = str(evidence_id_value) if evidence_id_value else None
        confidence = "preliminary"
        if evidence_id is not None:
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                raise ValidationFailure(f"adjustment evidence {evidence_id} is not registered")
            confidence = str(_evidence_field(evidence, "confidence_status", "confidenceStatus"))
            if confidence not in LINE_CONFIDENCE[1:]:
                raise ValidationFailure(f"adjustment evidence {evidence_id} is invalid")
        calculation_basis = str(_field(resource, "calculation_basis", "calculationBasis"))
        section_key = str(_field(operation, "section_key", "sectionKey"))
        rows.append(
            {
                "id": _stable_row_id(revision_id, operation_id, resource_id),
                "section": str(section.get("title")),
                "section_key": section_key,
                "wbs_path": str(_field(section, "wbs_path", "wbsPath") or section_key),
                "kind": kind,
                "description": str(resource.get("title")),
                "specification": {
                    "ratePercent": _decimal_text(rate),
                    "baseKinds": base_kinds,
                    "baseAmount": _money(base),
                },
                "unit": "компл.",
                "quantity": "1",
                "quantity_formula": {
                    "op": "percentage",
                    "ratePercent": _decimal_text(rate),
                    "baseKinds": base_kinds,
                },
                "quantity_basis": calculation_basis[:500],
                "unit_price": _money(amount),
                "price_basis": f"Детерминированно: {calculation_basis}"[:500],
                "line_total": _money(amount),
                "line_confidence": confidence,
                "operation_id": operation_id,
                "resource_id": resource_id,
                "technology_card_revision_id": revision_id,
                "technology_card_version": revision_id,
                "evidence_id": evidence_id,
            }
        )

    totals_decimal = {
        kind: sum(
            (
                _decimal(row["line_total"], field=f"row.{row['id']}.line_total")
                for row in rows
                if row["kind"] == kind
            ),
            Decimal("0"),
        )
        for kind in ESTIMATE_LINE_KINDS
    }
    total = sum(totals_decimal.values(), Decimal("0"))
    totals = {kind: _money(totals_decimal[kind]) for kind in sorted(ESTIMATE_LINE_KINDS)}
    totals["subtotal"] = _money(total)
    totals["total"] = _money(total)
    result_payload = {"rows": rows, "totals": totals}
    return ExpansionResult(
        rows=tuple(rows), totals=totals, content_hash=content_hash(result_payload)
    )


def reconcile_expanded_estimate(
    project_case: Mapping[str, Any],
    technology_card: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    *,
    evidence_by_id: Mapping[str, Mapping[str, Any]],
) -> ReconciliationReport:
    """Reconcile coverage, lineage, evidence honesty and Decimal totals."""

    issues: list[ValidationIssue] = []
    card_report = validate_technology_card(project_case, technology_card)
    issues.extend(card_report.issues)
    _, operations = _card_collections(technology_card)
    expected: set[tuple[str, str]] = set()
    expected_operations: set[str] = set()
    for operation in operations:
        if not isinstance(operation, Mapping):
            continue
        operation_id = str(_field(operation, "operation_id", "operationId"))
        expected_operations.add(operation_id)
        for resource in operation.get("resources", []):
            if isinstance(resource, Mapping):
                expected.add((operation_id, str(_field(resource, "resource_id", "resourceId"))))
    actual: set[tuple[str, str]] = set()
    row_ids: set[str] = set()
    total = Decimal("0")
    missing_price_count = 0
    covered_operations: set[str] = set()
    confidence_rank = {value: index for index, value in enumerate(LINE_CONFIDENCE)}
    for index, row in enumerate(rows):
        path = f"$.rows[{index}]"
        try:
            row_id = _identifier(row.get("id"), field=f"{path}.id")
            operation_id = _identifier(
                _field(row, "operation_id", "operationId"), field=f"{path}.operationId"
            )
            resource_id = _identifier(
                _field(row, "resource_id", "resourceId"), field=f"{path}.resourceId"
            )
            kind = _text(row.get("kind"), field=f"{path}.kind", maximum=32)
            if kind not in ESTIMATE_LINE_KINDS:
                raise ValidationFailure(f"{path}.kind is unsupported")
            quantity = _decimal(row.get("quantity"), field=f"{path}.quantity")
            price = _decimal(_field(row, "unit_price", "unitPrice"), field=f"{path}.unitPrice")
            line_total = _decimal(_field(row, "line_total", "lineTotal"), field=f"{path}.lineTotal")
            expected_total = (quantity * price).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
            if line_total != expected_total:
                raise ValidationFailure(
                    f"{path}.lineTotal is not quantity × unitPrice ({_money(expected_total)})"
                )
            _text(
                _field(row, "quantity_basis", "quantityBasis"),
                field=f"{path}.quantityBasis",
                maximum=500,
            )
            confidence = str(_field(row, "line_confidence", "lineConfidence") or "missing")
            if confidence not in confidence_rank:
                raise ValidationFailure(f"{path}.lineConfidence is invalid")
        except ValidationFailure as exc:
            issues.append(ValidationIssue("row_invalid", path, str(exc)))
            continue
        if row_id in row_ids:
            issues.append(ValidationIssue("row_id_duplicate", f"{path}.id", f"Duplicate {row_id}."))
        row_ids.add(row_id)
        pair = (operation_id, resource_id)
        if pair in actual:
            issues.append(
                ValidationIssue(
                    "lineage_duplicate",
                    path,
                    f"Duplicate operation/resource linkage {operation_id}/{resource_id}.",
                )
            )
        actual.add(pair)
        covered_operations.add(operation_id)
        if pair not in expected:
            issues.append(
                ValidationIssue(
                    "lineage_unexplained",
                    path,
                    f"Line is not declared by technology card: {operation_id}/{resource_id}.",
                )
            )
        evidence_id_value = _field(row, "evidence_id", "evidenceId")
        evidence_id = str(evidence_id_value) if evidence_id_value else None
        if evidence_id is None:
            if confidence in {"source_backed", "verified"}:
                issues.append(
                    ValidationIssue(
                        "confidence_without_evidence",
                        path,
                        f"{confidence} line must link registered evidence.",
                    )
                )
        else:
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                issues.append(
                    ValidationIssue(
                        "evidence_missing", path, f"Evidence {evidence_id} is not registered."
                    )
                )
            else:
                evidence_confidence = str(
                    _evidence_field(evidence, "confidence_status", "confidenceStatus")
                )
                if confidence_rank.get(confidence, 99) > confidence_rank.get(
                    evidence_confidence, -1
                ):
                    issues.append(
                        ValidationIssue(
                            "confidence_overstated",
                            path,
                            f"Line confidence exceeds evidence {evidence_id}.",
                        )
                    )
        missing_price_count += confidence == "missing"
        total += line_total
    for operation_id, resource_id in sorted(expected - actual):
        issues.append(
            ValidationIssue(
                "resource_not_expanded",
                "$.rows",
                f"Missing row for {operation_id}/{resource_id}.",
            )
        )
    for operation_id in sorted(expected_operations - covered_operations):
        issues.append(
            ValidationIssue(
                "operation_not_covered",
                "$.rows",
                f"Operation {operation_id} has no estimate rows.",
            )
        )
    hard_errors = [issue for issue in issues if issue.severity == "error"]
    if hard_errors:
        status: Literal["passed", "failed", "needs_input"] = "failed"
    elif missing_price_count:
        status = "needs_input"
    else:
        status = "passed"
    return ReconciliationReport(
        status=status,
        issues=tuple(issues),
        metrics={
            "operations": len(expected_operations),
            "expectedRows": len(expected),
            "actualRows": len(rows),
            "missingPrices": missing_price_count,
        },
        totals={"subtotal": _money(total), "total": _money(total)},
    )


def _run_row(database: sqlite3.Connection, *, tenant_id: str, run_id: str) -> sqlite3.Row:
    row = database.execute(
        "SELECT * FROM estimate_generation_runs WHERE tenant_id = ? AND id = ? LIMIT 1",
        (tenant_id, run_id),
    ).fetchone()
    if row is None:
        raise NotFound("estimate generation run not found")
    return row


def _task_row(database: sqlite3.Connection, *, tenant_id: str, task_id: str) -> sqlite3.Row:
    row = database.execute(
        "SELECT * FROM estimate_generation_tasks WHERE tenant_id = ? AND id = ? LIMIT 1",
        (tenant_id, task_id),
    ).fetchone()
    if row is None:
        raise NotFound("estimate generation task not found")
    return row


def _project_case_view(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "version": int(row["version"]),
        "status": str(row["status"]),
        "region": str(row["region"]),
        "snapshot": _json(row["snapshot_json"], {}),
        "contentHash": str(row["content_hash"]),
        "sourceMessageId": row["source_message_id"],
        "createdByUserId": str(row["created_by_user_id"]),
        "createdAt": str(row["created_at"]),
    }


def _run_view(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "tenantId": str(row["tenant_id"]),
        "projectId": str(row["project_id"]),
        "sourceRunId": row["source_run_id"],
        "status": str(row["status"]),
        "stage": str(row["stage"]),
        "qualityStatus": str(row["quality_status"]),
        "progress": {
            "completed": int(row["progress_completed"]),
            "total": int(row["progress_total"]),
        },
        "cancelRequested": bool(row["cancel_requested"]),
        "projectCaseRef": {
            "id": str(row["project_case_id"]),
            "version": int(row["project_case_version"]),
        },
        "qualityReport": _json(row["quality_report_json"], None),
        "result": (
            {
                "documentId": str(row["result_document_id"]),
                "estimateVersion": int(row["result_estimate_version"]),
            }
            if row["result_document_id"] is not None
            else None
        ),
        "lastError": _json(row["last_error_json"], None),
        "createdByUserId": str(row["created_by_user_id"]),
        "createdAt": str(row["created_at"]),
        "updatedAt": str(row["updated_at"]),
        "finishedAt": row["finished_at"],
    }


def _section_view(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "runId": str(row["run_id"]),
        "sectionKey": str(row["section_key"]),
        "title": str(row["title"]),
        "wbsPath": str(row["wbs_path"]),
        "ordinal": int(row["ordinal"]),
        "revision": int(row["revision"]),
        "status": str(row["status"]),
        "progress": {
            "completed": int(row["completed_task_count"]),
            "total": int(row["expected_task_count"]),
        },
        "lastError": _json(row["last_error_json"], None),
        "createdAt": str(row["created_at"]),
        "updatedAt": str(row["updated_at"]),
    }


def _task_view(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "runId": str(row["run_id"]),
        "sectionId": str(row["section_id"]),
        "sectionKey": str(row["section_key"]),
        "sectionRevision": int(row["section_revision"]),
        "taskKey": str(row["task_key"]),
        "role": str(row["role"]),
        "status": str(row["status"]),
        "attempt": int(row["attempt"]),
        "fencingToken": int(row["fencing_token"]),
        "dependsOnRoles": _json(row["depends_on_roles_json"], []),
        "input": _json(row["input_json"], {}),
        "inputHash": str(row["input_hash"]),
        "result": _json(row["result_json"], None),
        "resultHash": row["result_hash"],
        "error": _json(row["error_json"], None),
        "retryable": bool(row["retryable"]),
        "retryOfTaskId": row["retry_of_task_id"],
        "lease": (
            {
                "owner": str(row["lease_owner"]),
                "token": str(row["lease_token"]),
                "until": str(row["lease_until"]),
            }
            if row["lease_owner"] is not None
            else None
        ),
        "createdAt": str(row["created_at"]),
        "updatedAt": str(row["updated_at"]),
        "completedAt": row["completed_at"],
    }


def _checkpoint_view(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "runId": str(row["run_id"]),
        "sectionKey": row["section_key"],
        "taskId": row["task_id"],
        "checkpointKey": str(row["checkpoint_key"]),
        "sequence": int(row["sequence"]),
        "stage": str(row["stage"]),
        "status": str(row["status"]),
        "payload": _json(row["payload_json"], {}),
        "payloadHash": str(row["payload_hash"]),
        "createdAt": str(row["created_at"]),
    }


def _technology_revision_view(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "runId": str(row["run_id"]),
        "projectId": str(row["project_id"]),
        "revision": int(row["revision"]),
        "projectCaseRef": {
            "id": str(row["project_case_id"]),
            "version": int(row["project_case_version"]),
        },
        "previousRevisionId": row["previous_revision_id"],
        "publishedTechnologyCardId": row["published_technology_card_id"],
        "status": str(row["status"]),
        "rulesVersion": str(row["rules_version"]),
        "snapshot": _json(row["snapshot_json"], {}),
        "snapshotHash": str(row["snapshot_hash"]),
        "validation": _json(row["validation_json"], {}),
        "validationHash": str(row["validation_hash"]),
        "createdByUserId": str(row["created_by_user_id"]),
        "createdAt": str(row["created_at"]),
    }


def _evidence_view(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "runId": str(row["run_id"]),
        "sectionKey": row["section_key"],
        "evidenceKey": str(row["evidence_key"]),
        "kind": str(row["kind"]),
        "sourceType": str(row["source_type"]),
        "confidenceStatus": str(row["confidence_status"]),
        "confidence": str(row["confidence"]),
        "sourceTitle": str(row["source_title"]),
        "sourceUri": row["source_uri"],
        "sourceReference": str(row["source_reference"]),
        "region": row["region"],
        "unit": row["unit"],
        "unitPrice": row["unit_price"],
        "currency": row["currency"],
        "taxTreatment": row["tax_treatment"],
        "deliveryTreatment": row["delivery_treatment"],
        "observedAt": row["observed_at"],
        "validUntil": row["valid_until"],
        "snapshot": _json(row["snapshot_json"], {}),
        "snapshotHash": str(row["snapshot_hash"]),
        "verification": _json(row["verification_json"], {}),
        "verifiedByUserId": row["verified_by_user_id"],
        "createdAt": str(row["created_at"]),
    }


def _command_replay(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    operation: str,
    idempotency_key: str,
    request: object,
) -> dict[str, Any] | None:
    key_hash = _key_hash(idempotency_key)
    request_hash = _request_hash(request)
    row = database.execute(
        """
        SELECT request_hash, result_json
        FROM estimate_generation_commands
        WHERE tenant_id = ? AND run_id = ? AND operation = ?
          AND idempotency_key_hash = ?
        LIMIT 1
        """,
        (tenant_id, run_id, operation, key_hash),
    ).fetchone()
    if row is None:
        return None
    if str(row["request_hash"]) != request_hash:
        raise IdempotencyConflict("idempotency key was already used for different input")
    result = _json(row["result_json"], {})
    return result if isinstance(result, dict) else {}


def _store_command(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    operation: str,
    idempotency_key: str,
    request: object,
    result: Mapping[str, Any],
    now: str,
) -> None:
    database.execute(
        """
        INSERT INTO estimate_generation_commands (
            tenant_id, id, run_id, operation, idempotency_key_hash,
            request_hash, result_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tenant_id,
            f"estimate_generation_command_{uuid.uuid4().hex}",
            run_id,
            operation,
            _key_hash(idempotency_key),
            _request_hash(request),
            canonical_json(result),
            now,
        ),
    )


def _case_id(tenant_id: str, project_id: str) -> str:
    digest = hashlib.sha256(f"{tenant_id}:{project_id}".encode("utf-8", "strict")).hexdigest()[:24]
    return f"case_{digest}"


def _project_case_document(
    value: Mapping[str, Any],
    *,
    tenant_id: str,
    project_id: str,
    case_id: str,
    version: int,
) -> dict[str, Any]:
    result = dict(value)
    result.setdefault("schemaId", "kolibri.project_case")
    result.setdefault("schemaVersion", "2.0")
    result.setdefault("analysisStatus", "analysed")
    result.setdefault("currency", "RUB")
    result.setdefault("region", "Регион не указан")
    result["tenantId"] = tenant_id
    result["projectId"] = project_id
    result["caseId"] = case_id
    result["version"] = version
    return result


def create_generation_run(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    created_by_user_id: str,
    project_case: Mapping[str, Any],
    idempotency_key: str,
    source_run_id: str | None = None,
    source_message_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Persist a seed ProjectCase and durable boundary before model planning."""

    if not isinstance(project_case, Mapping):
        raise ValidationFailure("project_case must be an object")
    request = {
        "projectId": project_id,
        "createdByUserId": created_by_user_id,
        "projectCase": dict(project_case),
        "sourceRunId": source_run_id,
        "sourceMessageId": source_message_id,
    }
    key_hash = _key_hash(idempotency_key)
    request_hash = _request_hash(request)
    timestamp = _now(database, now)
    with transaction(database, immediate=True):
        previous = database.execute(
            """
            SELECT * FROM estimate_generation_runs
            WHERE tenant_id = ? AND idempotency_key_hash = ? LIMIT 1
            """,
            (tenant_id, key_hash),
        ).fetchone()
        if previous is not None:
            if str(previous["request_hash"]) != request_hash:
                raise IdempotencyConflict(
                    "generation idempotency key was already used for different input"
                )
            return _run_view(previous)
        project = database.execute(
            "SELECT id FROM projects WHERE tenant_id = ? AND id = ? LIMIT 1",
            (tenant_id, project_id),
        ).fetchone()
        if project is None:
            raise NotFound("project not found")
        case_id = _case_id(tenant_id, project_id)
        case_version = int(
            database.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1 FROM project_cases
                WHERE tenant_id = ? AND project_id = ?
                """,
                (tenant_id, project_id),
            ).fetchone()[0]
        )
        document = _project_case_document(
            project_case,
            tenant_id=tenant_id,
            project_id=project_id,
            case_id=case_id,
            version=case_version,
        )
        report = validate_project_case(document)
        pending = str(document.get("analysisStatus")) == "pending"
        run_status = "queued" if pending else ("running" if report.passed else "needs_input")
        stage = "project_case" if not report.passed else "decomposition"
        database.execute(
            """
            INSERT INTO project_cases (
                tenant_id, id, project_id, version, status, region,
                snapshot_json, content_hash, source_message_id,
                created_by_user_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                case_id,
                project_id,
                case_version,
                "ready" if report.passed else "draft",
                str(document.get("region") or "Регион не указан"),
                canonical_json(document),
                content_hash(document),
                source_message_id,
                created_by_user_id,
                timestamp,
            ),
        )
        run_id = f"run_estimate_generation_{uuid.uuid4().hex}"
        database.execute(
            """
            INSERT INTO estimate_generation_runs (
                tenant_id, id, project_id, source_run_id,
                project_case_id, project_case_version, status, stage,
                idempotency_key_hash, request_hash, created_by_user_id,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                run_id,
                project_id,
                source_run_id,
                case_id,
                case_version,
                run_status,
                stage,
                key_hash,
                request_hash,
                created_by_user_id,
                timestamp,
                timestamp,
            ),
        )
        _append_checkpoint_locked(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            stage=stage,
            status="needs_input" if run_status == "needs_input" else "started",
            payload={"runStatus": run_status, "projectCaseVersion": case_version},
            checkpoint_key="orchestrator:run-created",
            section_key=None,
            task_id=None,
            now=timestamp,
        )
        return _run_view(_run_row(database, tenant_id=tenant_id, run_id=run_id))


def load_generation_project_case(
    database: sqlite3.Connection, *, tenant_id: str, run_id: str
) -> dict[str, Any]:
    run = _run_row(database, tenant_id=tenant_id, run_id=run_id)
    row = database.execute(
        """
        SELECT * FROM project_cases
        WHERE tenant_id = ? AND id = ? AND version = ? LIMIT 1
        """,
        (tenant_id, run["project_case_id"], run["project_case_version"]),
    ).fetchone()
    if row is None:
        raise NotFound("generation ProjectCase not found")
    return _project_case_view(row)


def save_generation_project_case(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    project_case: Mapping[str, Any],
    idempotency_key: str,
    created_by_user_id: str | None = None,
    source_message_id: str | None = None,
    allow_active_revision: bool = False,
    now: str | None = None,
) -> dict[str, Any]:
    """Append an analysed ProjectCase version and atomically repoint the run."""

    if not isinstance(project_case, Mapping):
        raise ValidationFailure("project_case must be an object")
    request = {
        "projectCase": dict(project_case),
        "createdByUserId": created_by_user_id,
        "sourceMessageId": source_message_id,
    }
    timestamp = _now(database, now)
    operation = "project_case.save"
    with transaction(database, immediate=True):
        replay = _command_replay(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request=request,
        )
        if replay is not None:
            row = database.execute(
                """
                SELECT * FROM project_cases
                WHERE tenant_id = ? AND id = ? AND version = ? LIMIT 1
                """,
                (
                    tenant_id,
                    replay.get("projectCaseId"),
                    replay.get("version"),
                ),
            ).fetchone()
            if row is None:
                raise StateConflict("ProjectCase replay target is missing")
            return _project_case_view(row)
        run = _run_row(database, tenant_id=tenant_id, run_id=run_id)
        if str(run["status"]) in _FINAL_RUN_STATUSES:
            raise StateConflict("final generation run cannot accept a new ProjectCase")
        planned_sections = int(
            database.execute(
                """
                SELECT COUNT(*) FROM estimate_generation_sections
                WHERE tenant_id = ? AND run_id = ?
                """,
                (tenant_id, run_id),
            ).fetchone()[0]
        )
        if planned_sections and not allow_active_revision:
            raise StateConflict("ProjectCase is immutable after section planning; start a new run")
        case_id = str(run["project_case_id"])
        version = int(
            database.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1 FROM project_cases
                WHERE tenant_id = ? AND project_id = ?
                """,
                (tenant_id, run["project_id"]),
            ).fetchone()[0]
        )
        document = _project_case_document(
            project_case,
            tenant_id=tenant_id,
            project_id=str(run["project_id"]),
            case_id=case_id,
            version=version,
        )
        report = validate_project_case(document)
        pending = str(document.get("analysisStatus")) == "pending"
        database.execute(
            """
            UPDATE project_cases SET status = 'superseded'
            WHERE tenant_id = ? AND id = ? AND version = ?
              AND status IN ('draft', 'ready')
            """,
            (tenant_id, case_id, run["project_case_version"]),
        )
        actor = created_by_user_id or str(run["created_by_user_id"])
        database.execute(
            """
            INSERT INTO project_cases (
                tenant_id, id, project_id, version, status, region,
                snapshot_json, content_hash, source_message_id,
                created_by_user_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                case_id,
                run["project_id"],
                version,
                "ready" if report.passed else "draft",
                str(document.get("region") or "Регион не указан"),
                canonical_json(document),
                content_hash(document),
                source_message_id,
                actor,
                timestamp,
            ),
        )
        status = "queued" if pending else ("running" if report.passed else "needs_input")
        stage = "decomposition" if report.passed else "project_case"
        database.execute(
            """
            UPDATE estimate_generation_runs
            SET project_case_version = ?, status = ?, stage = ?,
                quality_status = 'pending', quality_report_json = ?,
                last_error_json = NULL, updated_at = ?
            WHERE tenant_id = ? AND id = ?
            """,
            (
                version,
                status,
                stage,
                canonical_json(report.as_dict()),
                timestamp,
                tenant_id,
                run_id,
            ),
        )
        _append_checkpoint_locked(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            stage=stage,
            status="completed" if report.passed else "needs_input",
            payload={
                "runStatus": status,
                "projectCaseVersion": version,
                "validationStatus": report.status,
            },
            checkpoint_key=f"orchestrator:project-case:{version}",
            section_key=None,
            task_id=None,
            now=timestamp,
        )
        result = {"projectCaseId": case_id, "version": version}
        _store_command(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request=request,
            result=result,
            now=timestamp,
        )
        return load_generation_project_case(database, tenant_id=tenant_id, run_id=run_id)


def list_generation_tasks(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    section_key: str | None = None,
    current_only: bool = False,
) -> list[dict[str, Any]]:
    _run_row(database, tenant_id=tenant_id, run_id=run_id)
    predicates = ["tasks.tenant_id = ?", "tasks.run_id = ?"]
    params: list[Any] = [tenant_id, run_id]
    if section_key is not None:
        predicates.append("tasks.section_key = ?")
        params.append(section_key)
    if current_only:
        predicates.append("tasks.section_revision = sections.revision")
    rows = database.execute(
        f"""
        SELECT tasks.*
        FROM estimate_generation_tasks AS tasks
        JOIN estimate_generation_sections AS sections
          ON sections.tenant_id = tasks.tenant_id
         AND sections.run_id = tasks.run_id
         AND sections.id = tasks.section_id
        WHERE {" AND ".join(predicates)}
        ORDER BY sections.ordinal, tasks.section_revision, tasks.created_at, tasks.id
        """,
        params,
    ).fetchall()
    return [_task_view(row) for row in rows]


def list_generation_sections(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    include_tasks: bool = False,
) -> list[dict[str, Any]]:
    _run_row(database, tenant_id=tenant_id, run_id=run_id)
    rows = database.execute(
        """
        SELECT * FROM estimate_generation_sections
        WHERE tenant_id = ? AND run_id = ?
        ORDER BY ordinal, section_key
        """,
        (tenant_id, run_id),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = _section_view(row)
        if include_tasks:
            item["tasks"] = list_generation_tasks(
                database,
                tenant_id=tenant_id,
                run_id=run_id,
                section_key=str(row["section_key"]),
            )
        result.append(item)
    return result


def list_generation_checkpoints(
    database: sqlite3.Connection, *, tenant_id: str, run_id: str
) -> list[dict[str, Any]]:
    _run_row(database, tenant_id=tenant_id, run_id=run_id)
    rows = database.execute(
        """
        SELECT * FROM estimate_generation_checkpoints
        WHERE tenant_id = ? AND run_id = ? ORDER BY sequence
        """,
        (tenant_id, run_id),
    ).fetchall()
    return [_checkpoint_view(row) for row in rows]


def list_generation_evidence(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    section_key: str | None = None,
) -> list[dict[str, Any]]:
    _run_row(database, tenant_id=tenant_id, run_id=run_id)
    if section_key is None:
        rows = database.execute(
            """
            SELECT * FROM estimate_generation_evidence
            WHERE tenant_id = ? AND run_id = ? ORDER BY created_at, id
            """,
            (tenant_id, run_id),
        ).fetchall()
    else:
        rows = database.execute(
            """
            SELECT * FROM estimate_generation_evidence
            WHERE tenant_id = ? AND run_id = ? AND section_key = ?
            ORDER BY created_at, id
            """,
            (tenant_id, run_id, section_key),
        ).fetchall()
    return [_evidence_view(row) for row in rows]


def get_generation_run(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    include_details: bool = True,
) -> dict[str, Any]:
    result = _run_view(_run_row(database, tenant_id=tenant_id, run_id=run_id))
    if not include_details:
        return result
    result["projectCase"] = load_generation_project_case(
        database, tenant_id=tenant_id, run_id=run_id
    )
    result["sections"] = list_generation_sections(
        database, tenant_id=tenant_id, run_id=run_id, include_tasks=True
    )
    result["checkpoints"] = list_generation_checkpoints(
        database, tenant_id=tenant_id, run_id=run_id
    )
    revision = database.execute(
        """
        SELECT * FROM estimate_generation_technology_revisions
        WHERE tenant_id = ? AND run_id = ? ORDER BY revision DESC LIMIT 1
        """,
        (tenant_id, run_id),
    ).fetchone()
    result["latestTechnologyRevision"] = (
        _technology_revision_view(revision) if revision is not None else None
    )
    evidence = list_generation_evidence(database, tenant_id=tenant_id, run_id=run_id)
    result["evidence"] = evidence
    return result


def _normalize_sections(sections: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(sections, Sequence) or isinstance(sections, (str, bytes)) or not sections:
        raise ValidationFailure("sections must be a non-empty array")
    result: list[dict[str, Any]] = []
    keys: set[str] = set()
    for index, section in enumerate(sections):
        if not isinstance(section, Mapping):
            raise ValidationFailure(f"sections[{index}] must be an object")
        key = _identifier(
            _field(section, "section_key", "sectionKey"),
            field=f"sections[{index}].sectionKey",
        )
        if key in keys:
            raise ValidationFailure(f"duplicate section key: {key}")
        keys.add(key)
        result.append(
            {
                "sectionKey": key,
                "title": _text(section.get("title"), field=f"sections[{index}].title", maximum=240),
                "wbsPath": _text(
                    _field(section, "wbs_path", "wbsPath") or key,
                    field=f"sections[{index}].wbsPath",
                    maximum=500,
                ),
                "ordinal": int(section.get("ordinal", index)),
            }
        )
        if result[-1]["ordinal"] < 0:
            raise ValidationFailure(f"sections[{index}].ordinal cannot be negative")
    return sorted(result, key=lambda item: (item["ordinal"], item["sectionKey"]))


def _roles(values: Sequence[str]) -> tuple[str, ...]:
    result = tuple(dict.fromkeys(str(value) for value in values))
    if not result or any(value not in TASK_ROLES for value in result):
        raise ValidationFailure("task roles are empty or unsupported")
    return result


def _task_input(
    run: sqlite3.Row,
    section: Mapping[str, Any],
    *,
    revision: int,
    role: str,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "runId": str(run["id"]),
        "projectId": str(run["project_id"]),
        "projectCaseRef": {
            "id": str(run["project_case_id"]),
            "version": int(run["project_case_version"]),
        },
        "section": dict(section),
        "sectionRevision": revision,
        "role": role,
        "retryReason": reason,
    }


def plan_generation_sections(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    sections: Sequence[Mapping[str, Any]],
    idempotency_key: str,
    roles: Sequence[str] = SECTION_ROLES,
    now: str | None = None,
) -> list[dict[str, Any]]:
    """Persist WBS sections and their independent role tasks exactly once."""

    normalized_sections = _normalize_sections(sections)
    normalized_roles = _roles(roles)
    request = {"sections": normalized_sections, "roles": normalized_roles}
    timestamp = _now(database, now)
    operation = "sections.plan"
    with transaction(database, immediate=True):
        replay = _command_replay(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request=request,
        )
        if replay is not None:
            return list_generation_sections(
                database, tenant_id=tenant_id, run_id=run_id, include_tasks=True
            )
        run = _run_row(database, tenant_id=tenant_id, run_id=run_id)
        if str(run["status"]) not in {"queued", "running"}:
            raise StateConflict("run is not ready for section planning")
        existing = int(
            database.execute(
                """
                SELECT COUNT(*) FROM estimate_generation_sections
                WHERE tenant_id = ? AND run_id = ?
                """,
                (tenant_id, run_id),
            ).fetchone()[0]
        )
        if existing:
            raise StateConflict("sections are already planned; use section retry")
        task_total = 0
        for section in normalized_sections:
            section_id = f"estimate_generation_section_{uuid.uuid4().hex}"
            database.execute(
                """
                INSERT INTO estimate_generation_sections (
                    tenant_id, id, run_id, section_key, title, wbs_path,
                    ordinal, revision, status, expected_task_count,
                    completed_task_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'active', ?, 0, ?, ?)
                """,
                (
                    tenant_id,
                    section_id,
                    run_id,
                    section["sectionKey"],
                    section["title"],
                    section["wbsPath"],
                    section["ordinal"],
                    len(normalized_roles),
                    timestamp,
                    timestamp,
                ),
            )
            dependencies = [role for role in normalized_roles if role != "reviewer"]
            for role in normalized_roles:
                payload = _task_input(run, section, revision=1, role=role)
                database.execute(
                    """
                    INSERT INTO estimate_generation_tasks (
                        tenant_id, id, run_id, section_id, section_key,
                        section_revision, task_key, role, status,
                        depends_on_roles_json, input_json, input_hash,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, 'queued', ?, ?, ?, ?, ?)
                    """,
                    (
                        tenant_id,
                        f"estimate_generation_task_{uuid.uuid4().hex}",
                        run_id,
                        section_id,
                        section["sectionKey"],
                        f"{section['sectionKey']}:r1:{role}",
                        role,
                        canonical_json(dependencies if role == "reviewer" else []),
                        canonical_json(payload),
                        content_hash(payload),
                        timestamp,
                        timestamp,
                    ),
                )
                task_total += 1
        database.execute(
            """
            UPDATE estimate_generation_runs
            SET status = 'running', stage = 'technology',
                progress_completed = 0, progress_total = ?, updated_at = ?
            WHERE tenant_id = ? AND id = ?
            """,
            (task_total, timestamp, tenant_id, run_id),
        )
        _append_checkpoint_locked(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            stage="technology",
            status="completed",
            payload={
                "sectionCount": len(normalized_sections),
                "taskCount": task_total,
            },
            checkpoint_key="orchestrator:sections-planned",
            section_key=None,
            task_id=None,
            now=timestamp,
        )
        _store_command(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request=request,
            result={"sectionCount": len(normalized_sections), "taskCount": task_total},
            now=timestamp,
        )
        return list_generation_sections(
            database, tenant_id=tenant_id, run_id=run_id, include_tasks=True
        )


def _append_checkpoint_locked(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    stage: str,
    status: str,
    payload: Mapping[str, Any],
    checkpoint_key: str,
    section_key: str | None,
    task_id: str | None,
    now: str,
) -> dict[str, Any]:
    if stage not in RUN_STAGES:
        raise ValidationFailure("checkpoint stage is invalid")
    if status not in {"started", "completed", "failed", "needs_input"}:
        raise ValidationFailure("checkpoint status is invalid")
    key = _text(checkpoint_key, field="checkpoint_key", maximum=240)
    payload_document = dict(payload)
    payload_hash = content_hash(payload_document)
    existing = database.execute(
        """
        SELECT * FROM estimate_generation_checkpoints
        WHERE tenant_id = ? AND run_id = ? AND checkpoint_key = ? LIMIT 1
        """,
        (tenant_id, run_id, key),
    ).fetchone()
    if existing is not None:
        if (
            str(existing["payload_hash"]) != payload_hash
            or str(existing["stage"]) != stage
            or str(existing["status"]) != status
            or existing["section_key"] != section_key
            or existing["task_id"] != task_id
        ):
            raise IdempotencyConflict("checkpoint key was reused for different state")
        return _checkpoint_view(existing)
    if section_key is not None:
        section = database.execute(
            """
            SELECT id FROM estimate_generation_sections
            WHERE tenant_id = ? AND run_id = ? AND section_key = ? LIMIT 1
            """,
            (tenant_id, run_id, section_key),
        ).fetchone()
        if section is None:
            raise NotFound("checkpoint section not found")
    if task_id is not None:
        task = _task_row(database, tenant_id=tenant_id, task_id=task_id)
        if str(task["run_id"]) != run_id:
            raise StateConflict("checkpoint task belongs to another run")
    sequence = int(
        database.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) + 1
            FROM estimate_generation_checkpoints
            WHERE tenant_id = ? AND run_id = ?
            """,
            (tenant_id, run_id),
        ).fetchone()[0]
    )
    checkpoint_id = f"estimate_generation_checkpoint_{uuid.uuid4().hex}"
    database.execute(
        """
        INSERT INTO estimate_generation_checkpoints (
            tenant_id, id, run_id, section_key, task_id,
            checkpoint_key, sequence, stage, status, payload_json,
            payload_hash, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tenant_id,
            checkpoint_id,
            run_id,
            section_key,
            task_id,
            key,
            sequence,
            stage,
            status,
            canonical_json(payload_document),
            payload_hash,
            now,
        ),
    )
    row = database.execute(
        """
        SELECT * FROM estimate_generation_checkpoints
        WHERE tenant_id = ? AND id = ? LIMIT 1
        """,
        (tenant_id, checkpoint_id),
    ).fetchone()
    assert row is not None
    event_sequence = int(database.execute(
        """
        SELECT COALESCE(MAX(sequence), 0) + 1
        FROM estimate_generation_events
        WHERE tenant_id = ? AND run_id = ?
        """,
        (tenant_id, run_id),
    ).fetchone()[0])
    role = None
    if task_id is not None:
        task = database.execute(
            "SELECT role FROM estimate_generation_tasks WHERE tenant_id = ? AND id = ?",
            (tenant_id, task_id),
        ).fetchone()
        role = str(task["role"]) if task is not None else None
    database.execute(
        """
        INSERT INTO estimate_generation_events
            (tenant_id, run_id, sequence, event_type, event_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            tenant_id, run_id, event_sequence, "kolibri.estimate.a2a.v1",
            canonical_json({
                "type": "ESTIMATE_A2A_EVENT",
                "eventType": "checkpoint",
                "runId": run_id,
                "sequence": event_sequence,
                "checkpointId": checkpoint_id,
                "checkpointKey": key,
                "stage": stage,
                "status": status,
                "role": role,
                "section": section_key,
                "payload": payload_document,
                "createdAt": now,
            }),
            now,
        ),
    )
    return _checkpoint_view(row)


def append_generation_checkpoint(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    stage: str,
    status: str,
    payload: Mapping[str, Any],
    checkpoint_key: str,
    section_key: str | None = None,
    task_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValidationFailure("checkpoint payload must be an object")
    timestamp = _now(database, now)
    with transaction(database, immediate=True):
        _run_row(database, tenant_id=tenant_id, run_id=run_id)
        return _append_checkpoint_locked(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            stage=stage,
            status=status,
            payload=payload,
            checkpoint_key=checkpoint_key,
            section_key=section_key,
            task_id=task_id,
            now=timestamp,
        )


def _review_passed(result: object) -> bool:
    if not isinstance(result, Mapping):
        return False
    return bool(
        result.get("accepted") is True
        or result.get("qualityStatus") == "passed"
        or result.get("validationStatus") == "passed"
    )


def _recompute_progress(
    database: sqlite3.Connection, *, tenant_id: str, run_id: str, now: str
) -> None:
    sections = database.execute(
        """
        SELECT * FROM estimate_generation_sections
        WHERE tenant_id = ? AND run_id = ? ORDER BY ordinal
        """,
        (tenant_id, run_id),
    ).fetchall()
    total = 0
    completed = 0
    passed_sections = 0
    for section in sections:
        tasks = database.execute(
            """
            SELECT * FROM estimate_generation_tasks
            WHERE tenant_id = ? AND run_id = ? AND section_id = ?
              AND section_revision = ?
            ORDER BY created_at, id
            """,
            (tenant_id, run_id, section["id"], section["revision"]),
        ).fetchall()
        section_total = len(tasks)
        section_completed = sum(
            str(task["status"]) in {"succeeded", "failed", "cancelled", "superseded"}
            for task in tasks
        )
        total += section_total
        completed += section_completed
        statuses = {str(task["status"]) for task in tasks}
        reviewer = next((task for task in tasks if str(task["role"]) == "reviewer"), None)
        if "failed" in statuses:
            section_status = "failed"
        elif "cancelled" in statuses:
            section_status = "cancelled"
        elif section_total and statuses == {"succeeded"}:
            if reviewer is None:
                section_status = "review"
            elif _review_passed(_json(reviewer["result_json"], None)):
                section_status = "passed"
                passed_sections += 1
            else:
                section_status = "review"
        else:
            section_status = "active"
        database.execute(
            """
            UPDATE estimate_generation_sections
            SET status = ?, expected_task_count = ?,
                completed_task_count = ?, updated_at = ?
            WHERE tenant_id = ? AND id = ?
            """,
            (
                section_status,
                section_total,
                section_completed,
                now,
                tenant_id,
                section["id"],
            ),
        )
    all_passed = bool(sections) and passed_sections == len(sections)
    database.execute(
        """
        UPDATE estimate_generation_runs
        SET progress_completed = ?, progress_total = ?,
            status = CASE WHEN ? THEN 'review' ELSE status END,
            stage = CASE WHEN ? THEN 'reconciliation' ELSE stage END,
            updated_at = ?
        WHERE tenant_id = ? AND id = ?
          AND status NOT IN ('ready', 'failed', 'cancelled')
        """,
        (completed, total, int(all_passed), int(all_passed), now, tenant_id, run_id),
    )


def _apply_cancellation(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    reason: Mapping[str, Any],
    now: str,
) -> None:
    database.execute(
        """
        UPDATE estimate_generation_tasks
        SET status = 'cancelled', lease_owner = NULL, lease_token = NULL,
            lease_until = NULL, error_json = ?, updated_at = ?, completed_at = ?
        WHERE tenant_id = ? AND run_id = ?
          AND status IN ('queued', 'leased')
        """,
        (canonical_json(reason), now, now, tenant_id, run_id),
    )
    database.execute(
        """
        UPDATE estimate_generation_sections
        SET status = 'cancelled', updated_at = ?
        WHERE tenant_id = ? AND run_id = ? AND status <> 'passed'
        """,
        (now, tenant_id, run_id),
    )
    database.execute(
        """
        UPDATE estimate_generation_runs
        SET cancel_requested = 1, status = 'cancelled',
            last_error_json = ?, updated_at = ?, finished_at = ?
        WHERE tenant_id = ? AND id = ? AND status <> 'ready'
        """,
        (canonical_json(reason), now, now, tenant_id, run_id),
    )
    _recompute_progress(database, tenant_id=tenant_id, run_id=run_id, now=now)


def request_generation_cancel(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    idempotency_key: str,
    reason: str,
    now: str | None = None,
) -> dict[str, Any]:
    request = {"reason": _text(reason, field="reason", maximum=1_000)}
    timestamp = _now(database, now)
    operation = "run.cancel"
    with transaction(database, immediate=True):
        replay = _command_replay(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request=request,
        )
        if replay is not None:
            return get_generation_run(
                database, tenant_id=tenant_id, run_id=run_id, include_details=False
            )
        run = _run_row(database, tenant_id=tenant_id, run_id=run_id)
        if str(run["status"]) == "ready":
            raise StateConflict("ready generation run cannot be cancelled")
        if str(run["status"]) == "failed":
            raise StateConflict("failed generation run is already terminal")
        if str(run["status"]) != "cancelled":
            _apply_cancellation(
                database,
                tenant_id=tenant_id,
                run_id=run_id,
                reason={"code": "cancelled_by_request", **request},
                now=timestamp,
            )
        _store_command(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request=request,
            result={"status": "cancelled"},
            now=timestamp,
        )
        return get_generation_run(
            database, tenant_id=tenant_id, run_id=run_id, include_details=False
        )


def claim_generation_task(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    worker_id: str,
    roles: Sequence[str] | None = None,
    lease_seconds: int = 300,
    max_attempts: int = 3,
    now: str | None = None,
) -> dict[str, Any] | None:
    worker = _text(worker_id, field="worker_id", maximum=160)
    allowed_roles = _roles(roles) if roles is not None else tuple(TASK_ROLES)
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
        raise ValidationFailure("max_attempts must be an integer")
    if max_attempts < 1 or max_attempts > 100:
        raise ValidationFailure("max_attempts must be between 1 and 100")
    timestamp = _now(database, now)
    lease_until = _later(timestamp, lease_seconds)
    with transaction(database, immediate=True):
        run = _run_row(database, tenant_id=tenant_id, run_id=run_id)
        if bool(run["cancel_requested"]):
            if str(run["status"]) != "cancelled":
                _apply_cancellation(
                    database,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    reason={"code": "cancel_requested"},
                    now=timestamp,
                )
            return None
        if str(run["status"]) in _FINAL_RUN_STATUSES or str(run["status"]) == "needs_input":
            return None
        database.execute(
            """
            UPDATE estimate_generation_tasks
            SET status = 'queued', lease_owner = NULL, lease_token = NULL,
                lease_until = NULL, updated_at = ?
            WHERE tenant_id = ? AND run_id = ? AND status = 'leased'
              AND lease_until <= ?
            """,
            (timestamp, tenant_id, run_id, timestamp),
        )
        placeholders = ",".join("?" for _ in allowed_roles)
        candidates = database.execute(
            f"""
            SELECT tasks.*
            FROM estimate_generation_tasks AS tasks
            JOIN estimate_generation_sections AS sections
              ON sections.tenant_id = tasks.tenant_id
             AND sections.run_id = tasks.run_id
             AND sections.id = tasks.section_id
            WHERE tasks.tenant_id = ? AND tasks.run_id = ?
              AND (
                    tasks.status = 'queued'
                    OR (
                        tasks.status = 'failed'
                        AND tasks.retryable = 1
                        AND tasks.attempt < ?
                    )
              )
              AND tasks.section_revision = sections.revision
              AND sections.status IN ('active', 'review', 'failed')
              AND tasks.role IN ({placeholders})
            ORDER BY sections.ordinal, tasks.created_at, tasks.id
            """,
            [tenant_id, run_id, max_attempts, *allowed_roles],
        ).fetchall()
        selected: sqlite3.Row | None = None
        for candidate in candidates:
            dependencies = _json(candidate["depends_on_roles_json"], [])
            if not isinstance(dependencies, list):
                continue
            satisfied = True
            for role in dependencies:
                dependency = database.execute(
                    """
                    SELECT status FROM estimate_generation_tasks
                    WHERE tenant_id = ? AND run_id = ? AND section_id = ?
                      AND section_revision = ? AND role = ? LIMIT 1
                    """,
                    (
                        tenant_id,
                        run_id,
                        candidate["section_id"],
                        candidate["section_revision"],
                        role,
                    ),
                ).fetchone()
                if dependency is None or str(dependency["status"]) != "succeeded":
                    satisfied = False
                    break
            if satisfied:
                selected = candidate
                break
        if selected is None:
            return None
        lease_token = f"estimate_task_lease_{uuid.uuid4().hex}"
        updated = database.execute(
            """
            UPDATE estimate_generation_tasks
            SET status = 'leased', attempt = attempt + 1,
                fencing_token = fencing_token + 1,
                lease_owner = ?, lease_token = ?, lease_until = ?,
                error_json = NULL, completed_at = NULL, updated_at = ?
            WHERE tenant_id = ? AND id = ?
              AND (
                    status = 'queued'
                    OR (
                        status = 'failed'
                        AND retryable = 1
                        AND attempt < ?
                    )
              )
            """,
            (
                worker,
                lease_token,
                lease_until,
                timestamp,
                tenant_id,
                selected["id"],
                max_attempts,
            ),
        )
        if updated.rowcount != 1:
            raise StateConflict("task was claimed concurrently")
        database.execute(
            """
            UPDATE estimate_generation_runs SET status = 'running', updated_at = ?
            WHERE tenant_id = ? AND id = ? AND status IN ('queued', 'review')
            """,
            (timestamp, tenant_id, run_id),
        )
        claimed = _task_row(
            database,
            tenant_id=tenant_id,
            task_id=str(selected["id"]),
        )
        _append_checkpoint_locked(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            stage=str(run["stage"]),
            status="started",
            payload={
                "attempt": int(claimed["attempt"]),
                "role": str(claimed["role"]),
            },
            checkpoint_key=(
                f"task:{claimed['id']}:attempt-{claimed['attempt']}:started"
            ),
            section_key=str(claimed["section_key"]),
            task_id=str(claimed["id"]),
            now=timestamp,
        )
        return _task_view(claimed)


def complete_generation_task(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    task_id: str,
    lease_token: str,
    result: Mapping[str, Any],
    checkpoint_key: str,
    now: str | None = None,
) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        raise ValidationFailure("task result must be an object")
    result_document = dict(result)
    result_hash = content_hash(result_document)
    timestamp = _now(database, now)
    with transaction(database, immediate=True):
        task = _task_row(database, tenant_id=tenant_id, task_id=task_id)
        run_id = str(task["run_id"])
        checkpoint_payload = {"taskId": task_id, "resultHash": result_hash}
        previous = database.execute(
            """
            SELECT * FROM estimate_generation_checkpoints
            WHERE tenant_id = ? AND run_id = ? AND checkpoint_key = ? LIMIT 1
            """,
            (tenant_id, run_id, checkpoint_key),
        ).fetchone()
        if previous is not None:
            if str(previous["payload_hash"]) != content_hash(checkpoint_payload):
                raise IdempotencyConflict("task completion checkpoint conflicts")
            current = _task_row(database, tenant_id=tenant_id, task_id=task_id)
            if str(current["status"]) != "succeeded" or str(current["result_hash"]) != result_hash:
                raise StateConflict("checkpoint exists without matching task completion")
            return _task_view(current)
        run = _run_row(database, tenant_id=tenant_id, run_id=run_id)
        if bool(run["cancel_requested"]) or str(run["status"]) == "cancelled":
            raise StateConflict("generation run was cancelled")
        if str(task["status"]) != "leased" or str(task["lease_token"]) != lease_token:
            raise StateConflict("task lease is not owned by this completion")
        if _parse_time(str(task["lease_until"])) < _parse_time(timestamp):
            raise StateConflict("task lease expired")
        updated = database.execute(
            """
            UPDATE estimate_generation_tasks
            SET status = 'succeeded', result_json = ?, result_hash = ?,
                error_json = NULL, lease_owner = NULL, lease_token = NULL,
                lease_until = NULL, updated_at = ?, completed_at = ?
            WHERE tenant_id = ? AND id = ? AND status = 'leased'
              AND lease_token = ?
            """,
            (
                canonical_json(result_document),
                result_hash,
                timestamp,
                timestamp,
                tenant_id,
                task_id,
                lease_token,
            ),
        )
        if updated.rowcount != 1:
            raise StateConflict("task completion lost its fencing race")
        _append_checkpoint_locked(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            stage=str(run["stage"]),
            status="completed",
            payload=checkpoint_payload,
            checkpoint_key=checkpoint_key,
            section_key=str(task["section_key"]),
            task_id=task_id,
            now=timestamp,
        )
        _recompute_progress(database, tenant_id=tenant_id, run_id=run_id, now=timestamp)
        return _task_view(_task_row(database, tenant_id=tenant_id, task_id=task_id))


def fail_generation_task(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    task_id: str,
    lease_token: str,
    error: Mapping[str, Any],
    checkpoint_key: str,
    retryable: bool = True,
    now: str | None = None,
) -> dict[str, Any]:
    if not isinstance(error, Mapping) or not error:
        raise ValidationFailure("task error must be a non-empty object")
    error_document = dict(error)
    timestamp = _now(database, now)
    with transaction(database, immediate=True):
        task = _task_row(database, tenant_id=tenant_id, task_id=task_id)
        run_id = str(task["run_id"])
        checkpoint_payload = {
            "taskId": task_id,
            "errorHash": content_hash(error_document),
            "retryable": bool(retryable),
        }
        previous = database.execute(
            """
            SELECT * FROM estimate_generation_checkpoints
            WHERE tenant_id = ? AND run_id = ? AND checkpoint_key = ? LIMIT 1
            """,
            (tenant_id, run_id, checkpoint_key),
        ).fetchone()
        if previous is not None:
            if str(previous["payload_hash"]) != content_hash(checkpoint_payload):
                raise IdempotencyConflict("task failure checkpoint conflicts")
            return _task_view(_task_row(database, tenant_id=tenant_id, task_id=task_id))
        run = _run_row(database, tenant_id=tenant_id, run_id=run_id)
        if bool(run["cancel_requested"]) or str(run["status"]) == "cancelled":
            raise StateConflict("generation run was cancelled")
        if str(task["status"]) != "leased" or str(task["lease_token"]) != lease_token:
            raise StateConflict("task lease is not owned by this failure")
        updated = database.execute(
            """
            UPDATE estimate_generation_tasks
            SET status = 'failed', error_json = ?, retryable = ?,
                lease_owner = NULL, lease_token = NULL, lease_until = NULL,
                updated_at = ?, completed_at = ?
            WHERE tenant_id = ? AND id = ? AND status = 'leased'
              AND lease_token = ?
            """,
            (
                canonical_json(error_document),
                int(retryable),
                timestamp,
                timestamp,
                tenant_id,
                task_id,
                lease_token,
            ),
        )
        if updated.rowcount != 1:
            raise StateConflict("task failure lost its fencing race")
        _append_checkpoint_locked(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            stage=str(run["stage"]),
            status="failed",
            payload=checkpoint_payload,
            checkpoint_key=checkpoint_key,
            section_key=str(task["section_key"]),
            task_id=task_id,
            now=timestamp,
        )
        database.execute(
            """
            UPDATE estimate_generation_sections
            SET status = 'failed', last_error_json = ?, updated_at = ?
            WHERE tenant_id = ? AND id = ?
            """,
            (canonical_json(error_document), timestamp, tenant_id, task["section_id"]),
        )
        if not retryable:
            database.execute(
                """
                UPDATE estimate_generation_runs
                SET status = 'needs_input', last_error_json = ?, updated_at = ?
                WHERE tenant_id = ? AND id = ?
                """,
                (canonical_json(error_document), timestamp, tenant_id, run_id),
            )
        _recompute_progress(database, tenant_id=tenant_id, run_id=run_id, now=timestamp)
        return _task_view(_task_row(database, tenant_id=tenant_id, task_id=task_id))


def retry_generation_section(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    section_key: str,
    roles: Sequence[str],
    idempotency_key: str,
    reason: str,
    now: str | None = None,
) -> list[dict[str, Any]]:
    section_key = _identifier(section_key, field="section_key")
    normalized_roles = _roles(roles)
    reason_text = _text(reason, field="reason", maximum=1_000)
    request = {"sectionKey": section_key, "roles": normalized_roles, "reason": reason_text}
    operation = f"section.retry:{section_key}"
    timestamp = _now(database, now)
    with transaction(database, immediate=True):
        replay = _command_replay(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request=request,
        )
        if replay is not None:
            return list_generation_tasks(
                database,
                tenant_id=tenant_id,
                run_id=run_id,
                section_key=section_key,
                current_only=True,
            )
        run = _run_row(database, tenant_id=tenant_id, run_id=run_id)
        if str(run["status"]) in _FINAL_RUN_STATUSES or bool(run["cancel_requested"]):
            raise StateConflict("final or cancelled run cannot retry a section")
        section = database.execute(
            """
            SELECT * FROM estimate_generation_sections
            WHERE tenant_id = ? AND run_id = ? AND section_key = ? LIMIT 1
            """,
            (tenant_id, run_id, section_key),
        ).fetchone()
        if section is None:
            raise NotFound("generation section not found")
        old_revision = int(section["revision"])
        new_revision = old_revision + 1
        previous_by_role = {
            str(row["role"]): str(row["id"])
            for row in database.execute(
                """
                SELECT id, role FROM estimate_generation_tasks
                WHERE tenant_id = ? AND run_id = ? AND section_id = ?
                  AND section_revision = ?
                ORDER BY created_at DESC
                """,
                (tenant_id, run_id, section["id"], old_revision),
            ).fetchall()
        }
        database.execute(
            """
            UPDATE estimate_generation_tasks
            SET status = 'superseded', lease_owner = NULL, lease_token = NULL,
                lease_until = NULL, updated_at = ?, completed_at = ?
            WHERE tenant_id = ? AND run_id = ? AND section_id = ?
              AND section_revision = ? AND status IN ('queued', 'leased')
            """,
            (timestamp, timestamp, tenant_id, run_id, section["id"], old_revision),
        )
        database.execute(
            """
            UPDATE estimate_generation_sections
            SET revision = ?, status = 'active', expected_task_count = ?,
                completed_task_count = 0, last_error_json = NULL, updated_at = ?
            WHERE tenant_id = ? AND id = ?
            """,
            (new_revision, len(normalized_roles), timestamp, tenant_id, section["id"]),
        )
        section_payload = {
            "sectionKey": section_key,
            "title": str(section["title"]),
            "wbsPath": str(section["wbs_path"]),
            "ordinal": int(section["ordinal"]),
        }
        dependencies = [role for role in normalized_roles if role != "reviewer"]
        for role in normalized_roles:
            payload = _task_input(
                run,
                section_payload,
                revision=new_revision,
                role=role,
                reason=reason_text,
            )
            database.execute(
                """
                INSERT INTO estimate_generation_tasks (
                    tenant_id, id, run_id, section_id, section_key,
                    section_revision, task_key, role, status,
                    depends_on_roles_json, input_json, input_hash,
                    retry_of_task_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    f"estimate_generation_task_{uuid.uuid4().hex}",
                    run_id,
                    section["id"],
                    section_key,
                    new_revision,
                    f"{section_key}:r{new_revision}:{role}",
                    role,
                    canonical_json(dependencies if role == "reviewer" else []),
                    canonical_json(payload),
                    content_hash(payload),
                    previous_by_role.get(role),
                    timestamp,
                    timestamp,
                ),
            )
        database.execute(
            """
            UPDATE estimate_generation_runs
            SET status = 'running', stage = 'technology',
                quality_status = 'pending', quality_report_json = NULL,
                last_error_json = NULL, updated_at = ?
            WHERE tenant_id = ? AND id = ?
            """,
            (timestamp, tenant_id, run_id),
        )
        _recompute_progress(database, tenant_id=tenant_id, run_id=run_id, now=timestamp)
        _store_command(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request=request,
            result={"sectionKey": section_key, "revision": new_revision},
            now=timestamp,
        )
        return list_generation_tasks(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            section_key=section_key,
            current_only=True,
        )


def resume_generation_run(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    now: str | None = None,
) -> dict[str, Any]:
    timestamp = _now(database, now)
    with transaction(database, immediate=True):
        run = _run_row(database, tenant_id=tenant_id, run_id=run_id)
        if bool(run["cancel_requested"]):
            if str(run["status"]) != "cancelled":
                _apply_cancellation(
                    database,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    reason={"code": "cancel_requested"},
                    now=timestamp,
                )
            return get_generation_run(database, tenant_id=tenant_id, run_id=run_id)
        if str(run["status"]) in _FINAL_RUN_STATUSES:
            return get_generation_run(database, tenant_id=tenant_id, run_id=run_id)
        database.execute(
            """
            UPDATE estimate_generation_tasks
            SET status = 'queued', lease_owner = NULL, lease_token = NULL,
                lease_until = NULL, updated_at = ?
            WHERE tenant_id = ? AND run_id = ? AND status = 'leased'
              AND lease_until <= ?
            """,
            (timestamp, tenant_id, run_id, timestamp),
        )
        queued = int(
            database.execute(
                """
                SELECT COUNT(*) FROM estimate_generation_tasks
                WHERE tenant_id = ? AND run_id = ? AND status = 'queued'
                """,
                (tenant_id, run_id),
            ).fetchone()[0]
        )
        if queued and str(run["status"]) != "needs_input":
            database.execute(
                """
                UPDATE estimate_generation_runs
                SET status = 'running', updated_at = ?
                WHERE tenant_id = ? AND id = ?
                """,
                (timestamp, tenant_id, run_id),
            )
        _recompute_progress(database, tenant_id=tenant_id, run_id=run_id, now=timestamp)
        return get_generation_run(database, tenant_id=tenant_id, run_id=run_id)


def register_generation_evidence(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    evidence: Mapping[str, Any],
    idempotency_key: str,
    section_key: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    if not isinstance(evidence, Mapping):
        raise ValidationFailure("evidence must be an object")
    timestamp = _now(database, now)
    evidence_key = _identifier(
        _field(evidence, "evidence_key", "evidenceKey"), field="evidence.evidenceKey"
    )
    kind = _text(evidence.get("kind"), field="evidence.kind", maximum=32)
    if kind not in {"technical", "price"}:
        raise ValidationFailure("evidence.kind is unsupported")
    source_type = _text(
        _field(evidence, "source_type", "sourceType"),
        field="evidence.sourceType",
        maximum=32,
    )
    if source_type not in EVIDENCE_SOURCE_TYPES:
        raise ValidationFailure("evidence.sourceType is unsupported")
    confidence_status = _text(
        _field(evidence, "confidence_status", "confidenceStatus"),
        field="evidence.confidenceStatus",
        maximum=32,
    )
    if confidence_status not in LINE_CONFIDENCE[1:]:
        raise ValidationFailure("evidence.confidenceStatus is unsupported")
    if source_type == "ai_candidate" and confidence_status != "preliminary":
        raise ValidationFailure("AI candidate evidence can only be preliminary")
    confidence = _decimal(evidence.get("confidence", "0"), field="evidence.confidence")
    if confidence > 1:
        raise ValidationFailure("evidence.confidence cannot exceed 1")
    source_title = _text(
        _field(evidence, "source_title", "sourceTitle"),
        field="evidence.sourceTitle",
        maximum=300,
    )
    source_reference = _text(
        _field(evidence, "source_reference", "sourceReference"),
        field="evidence.sourceReference",
        maximum=500,
    )
    source_uri_value = _field(evidence, "source_uri", "sourceUri")
    source_uri = (
        _text(source_uri_value, field="evidence.sourceUri", maximum=2_000)
        if source_uri_value is not None
        else None
    )
    snapshot = evidence.get("snapshot")
    if not isinstance(snapshot, Mapping):
        raise ValidationFailure("evidence.snapshot must be an immutable object")
    snapshot_document = dict(snapshot)
    snapshot_hash = content_hash(snapshot_document)
    verification = evidence.get("verification", {})
    if not isinstance(verification, Mapping):
        raise ValidationFailure("evidence.verification must be an object")
    verified_by = _field(evidence, "verified_by_user_id", "verifiedByUserId")
    if confidence_status == "verified":
        if source_type not in {"user_input", "official_reference", "supplier_offer"}:
            raise ValidationFailure("this evidence source cannot be verified")
        if not isinstance(verified_by, str) or not verified_by or not verification:
            raise ValidationFailure("verified evidence requires verifier and verification")
    elif verified_by is not None:
        raise ValidationFailure("only verified evidence may name a verifier")
    region = _field(evidence, "region", "region")
    unit = _field(evidence, "unit", "unit")
    unit_price = _field(evidence, "unit_price", "unitPrice")
    currency = evidence.get("currency")
    observed_at = _field(evidence, "observed_at", "observedAt")
    if kind == "price":
        region = _text(region, field="evidence.region", maximum=160)
        unit = _text(unit, field="evidence.unit", maximum=32)
        _unit(unit, field="evidence.unit")
        unit_price = _money(_decimal(unit_price, field="evidence.unitPrice"))
        if currency != "RUB":
            raise ValidationFailure("price evidence currency must be RUB")
        observed_at = _text(observed_at, field="evidence.observedAt", maximum=64)
        _parse_time(observed_at)
    else:
        region = str(region).strip() if region is not None else None
        unit = str(unit).strip() if unit is not None else None
        unit_price = str(unit_price).strip() if unit_price is not None else None
        currency = str(currency) if currency is not None else None
        observed_at = str(observed_at) if observed_at is not None else None
    tax_treatment = _field(evidence, "tax_treatment", "taxTreatment")
    delivery_treatment = _field(evidence, "delivery_treatment", "deliveryTreatment")
    if tax_treatment is not None and tax_treatment not in {
        "included",
        "excluded",
        "unknown",
        "not_applicable",
    }:
        raise ValidationFailure("evidence.taxTreatment is invalid")
    if delivery_treatment is not None and delivery_treatment not in {
        "included",
        "excluded",
        "unknown",
    }:
        raise ValidationFailure("evidence.deliveryTreatment is invalid")
    valid_until = _field(evidence, "valid_until", "validUntil")
    if valid_until is not None:
        valid_until = _text(valid_until, field="evidence.validUntil", maximum=64)
        _parse_date(valid_until, field="evidence.validUntil")
    if kind == "price" and confidence_status in {"source_backed", "verified"}:
        if valid_until is None:
            raise ValidationFailure(
                "source-backed price evidence requires validUntil freshness bound"
            )
        if _parse_date(valid_until, field="evidence.validUntil") < _parse_time(timestamp).date():
            raise ValidationFailure("expired price evidence must be registered as preliminary")
        if _parse_time(str(observed_at)) > _parse_time(timestamp):
            raise ValidationFailure("price evidence observedAt cannot be in the future")
    normalized = {
        "evidenceKey": evidence_key,
        "kind": kind,
        "sourceType": source_type,
        "confidenceStatus": confidence_status,
        "confidence": _decimal_text(confidence),
        "sourceTitle": source_title,
        "sourceUri": source_uri,
        "sourceReference": source_reference,
        "region": region,
        "unit": unit,
        "unitPrice": unit_price,
        "currency": currency,
        "taxTreatment": tax_treatment,
        "deliveryTreatment": delivery_treatment,
        "observedAt": observed_at,
        "validUntil": valid_until,
        "snapshot": snapshot_document,
        "verification": dict(verification),
        "verifiedByUserId": verified_by,
        "sectionKey": section_key,
    }
    operation = f"evidence.register:{evidence_key}"
    with transaction(database, immediate=True):
        replay = _command_replay(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request=normalized,
        )
        if replay is not None:
            row = database.execute(
                """
                SELECT * FROM estimate_generation_evidence
                WHERE tenant_id = ? AND run_id = ? AND id = ? LIMIT 1
                """,
                (tenant_id, run_id, replay.get("evidenceId")),
            ).fetchone()
            if row is None:
                raise StateConflict("evidence replay target is missing")
            return _evidence_view(row)
        run = _run_row(database, tenant_id=tenant_id, run_id=run_id)
        if str(run["status"]) in _FINAL_RUN_STATUSES:
            raise StateConflict("final run cannot accept evidence")
        if section_key is not None:
            section = database.execute(
                """
                SELECT id FROM estimate_generation_sections
                WHERE tenant_id = ? AND run_id = ? AND section_key = ? LIMIT 1
                """,
                (tenant_id, run_id, section_key),
            ).fetchone()
            if section is None:
                raise NotFound("evidence section not found")
        evidence_id = f"estimate_generation_evidence_{uuid.uuid4().hex}"
        database.execute(
            """
            INSERT INTO estimate_generation_evidence (
                tenant_id, id, run_id, section_key, evidence_key, kind,
                source_type, confidence_status, confidence, source_title,
                source_uri, source_reference, region, unit, unit_price,
                currency, tax_treatment, delivery_treatment, observed_at,
                valid_until, snapshot_json, snapshot_hash,
                verification_json, verified_by_user_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                evidence_id,
                run_id,
                section_key,
                evidence_key,
                kind,
                source_type,
                confidence_status,
                _decimal_text(confidence),
                source_title,
                source_uri,
                source_reference,
                region,
                unit,
                unit_price,
                currency,
                tax_treatment,
                delivery_treatment,
                observed_at,
                valid_until,
                canonical_json(snapshot_document),
                snapshot_hash,
                canonical_json(dict(verification)),
                verified_by,
                timestamp,
            ),
        )
        database.execute(
            """
            UPDATE estimate_generation_runs SET stage = ?, updated_at = ?
            WHERE tenant_id = ? AND id = ?
            """,
            ("pricing" if kind == "price" else "research", timestamp, tenant_id, run_id),
        )
        _store_command(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request=normalized,
            result={"evidenceId": evidence_id},
            now=timestamp,
        )
        row = database.execute(
            "SELECT * FROM estimate_generation_evidence WHERE tenant_id = ? AND id = ?",
            (tenant_id, evidence_id),
        ).fetchone()
        assert row is not None
        return _evidence_view(row)


def get_latest_technology_card_revision(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    published_only: bool = False,
) -> dict[str, Any] | None:
    _run_row(database, tenant_id=tenant_id, run_id=run_id)
    predicate = "AND published_technology_card_id IS NOT NULL" if published_only else ""
    row = database.execute(
        f"""
        SELECT * FROM estimate_generation_technology_revisions
        WHERE tenant_id = ? AND run_id = ? {predicate}
        ORDER BY revision DESC LIMIT 1
        """,
        (tenant_id, run_id),
    ).fetchone()
    return _technology_revision_view(row) if row is not None else None


def get_latest_project_technology_card_revision(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    published_only: bool = False,
) -> dict[str, Any] | None:
    predicate = "AND revisions.published_technology_card_id IS NOT NULL" if published_only else ""
    row = database.execute(
        f"""
        SELECT revisions.*
        FROM estimate_generation_technology_revisions AS revisions
        WHERE revisions.tenant_id = ? AND revisions.project_id = ? {predicate}
        ORDER BY revisions.created_at DESC, revisions.rowid DESC LIMIT 1
        """,
        (tenant_id, project_id),
    ).fetchone()
    return _technology_revision_view(row) if row is not None else None


def get_latest_generation_run(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    include_details: bool = False,
) -> dict[str, Any] | None:
    row = database.execute(
        """
        SELECT * FROM estimate_generation_runs
        WHERE tenant_id = ? AND project_id = ?
        ORDER BY created_at DESC, rowid DESC LIMIT 1
        """,
        (tenant_id, project_id),
    ).fetchone()
    if row is None:
        return None
    return get_generation_run(
        database,
        tenant_id=tenant_id,
        run_id=str(row["id"]),
        include_details=include_details,
    )


def save_technology_card_revision(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    technology_card: Mapping[str, Any],
    idempotency_key: str,
    status: str = "draft",
    created_by_user_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    if not isinstance(technology_card, Mapping):
        raise ValidationFailure("technology_card must be an object")
    if status not in {"draft", "review", "accepted", "rejected"}:
        raise ValidationFailure("technology revision status is invalid")
    timestamp = _now(database, now)
    operation = "technology_revision.save"
    request = {"technologyCard": dict(technology_card), "status": status}
    with transaction(database, immediate=True):
        replay = _command_replay(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request=request,
        )
        if replay is not None:
            row = database.execute(
                """
                SELECT * FROM estimate_generation_technology_revisions
                WHERE tenant_id = ? AND run_id = ? AND id = ? LIMIT 1
                """,
                (tenant_id, run_id, replay.get("revisionId")),
            ).fetchone()
            if row is None:
                raise StateConflict("technology revision replay target is missing")
            return _technology_revision_view(row)
        run = _run_row(database, tenant_id=tenant_id, run_id=run_id)
        if str(run["status"]) in _FINAL_RUN_STATUSES:
            raise StateConflict("final run cannot accept a technology revision")
        project_case_view = load_generation_project_case(
            database, tenant_id=tenant_id, run_id=run_id
        )
        project_case = project_case_view["snapshot"]
        report = validate_technology_card(project_case, technology_card)
        if status == "accepted" and not report.passed:
            raise ValidationFailure("invalid technology card cannot be accepted")
        revision_number = int(
            database.execute(
                """
                SELECT COALESCE(MAX(revision), 0) + 1
                FROM estimate_generation_technology_revisions
                WHERE tenant_id = ? AND run_id = ?
                """,
                (tenant_id, run_id),
            ).fetchone()[0]
        )
        snapshot = dict(technology_card)
        snapshot.setdefault("schemaVersion", "2.0")
        snapshot["runId"] = run_id
        snapshot["projectCaseRef"] = {
            "id": str(run["project_case_id"]),
            "version": int(run["project_case_version"]),
        }
        snapshot_hash = content_hash(snapshot)
        duplicate = database.execute(
            """
            SELECT * FROM estimate_generation_technology_revisions
            WHERE tenant_id = ? AND run_id = ? AND snapshot_hash = ? LIMIT 1
            """,
            (tenant_id, run_id, snapshot_hash),
        ).fetchone()
        if duplicate is not None:
            result = {"revisionId": str(duplicate["id"]), "revision": int(duplicate["revision"])}
            _store_command(
                database,
                tenant_id=tenant_id,
                run_id=run_id,
                operation=operation,
                idempotency_key=idempotency_key,
                request=request,
                result=result,
                now=timestamp,
            )
            return _technology_revision_view(duplicate)
        previous = database.execute(
            """
            SELECT id FROM estimate_generation_technology_revisions
            WHERE tenant_id = ? AND run_id = ?
            ORDER BY revision DESC LIMIT 1
            """,
            (tenant_id, run_id),
        ).fetchone()
        revision_id = f"technology_card_revision_{uuid.uuid4().hex}"
        actor = created_by_user_id or str(run["created_by_user_id"])
        validation_document = report.as_dict()
        database.execute(
            """
            INSERT INTO estimate_generation_technology_revisions (
                tenant_id, id, run_id, project_id, revision,
                project_case_id, project_case_version, previous_revision_id,
                status, rules_version, snapshot_json, snapshot_hash,
                validation_json, validation_hash, created_by_user_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                revision_id,
                run_id,
                run["project_id"],
                revision_number,
                run["project_case_id"],
                run["project_case_version"],
                previous["id"] if previous is not None else None,
                status,
                _text(snapshot.get("rulesVersion"), field="rulesVersion", maximum=120),
                canonical_json(snapshot),
                snapshot_hash,
                canonical_json(validation_document),
                content_hash(validation_document),
                actor,
                timestamp,
            ),
        )
        if status == "accepted":
            database.execute(
                """
                UPDATE estimate_generation_technology_revisions
                SET status = 'superseded'
                WHERE tenant_id = ? AND run_id = ? AND id <> ?
                  AND status IN ('draft', 'review')
                """,
                (tenant_id, run_id, revision_id),
            )
        database.execute(
            """
            UPDATE estimate_generation_runs
            SET stage = 'technology', status = ?, updated_at = ?
            WHERE tenant_id = ? AND id = ?
            """,
            (
                "review" if status in {"review", "accepted"} else "running",
                timestamp,
                tenant_id,
                run_id,
            ),
        )
        result = {"revisionId": revision_id, "revision": revision_number}
        _store_command(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request=request,
            result=result,
            now=timestamp,
        )
        row = database.execute(
            """
            SELECT * FROM estimate_generation_technology_revisions
            WHERE tenant_id = ? AND id = ?
            """,
            (tenant_id, revision_id),
        ).fetchone()
        assert row is not None
        return _technology_revision_view(row)


def publish_technology_card_revision(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    revision_id: str,
    created_by_user_id: str,
    idempotency_key: str,
    now: str | None = None,
) -> dict[str, Any]:
    request = {"revisionId": revision_id, "createdByUserId": created_by_user_id}
    operation = "technology_revision.publish"
    timestamp = _now(database, now)
    with transaction(database, immediate=True):
        replay = _command_replay(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request=request,
        )
        if replay is not None:
            row = database.execute(
                """
                SELECT * FROM estimate_generation_technology_revisions
                WHERE tenant_id = ? AND run_id = ? AND id = ? LIMIT 1
                """,
                (tenant_id, run_id, revision_id),
            ).fetchone()
            if row is None:
                raise StateConflict("published revision replay target is missing")
            return _technology_revision_view(row)
        run = _run_row(database, tenant_id=tenant_id, run_id=run_id)
        row = database.execute(
            """
            SELECT * FROM estimate_generation_technology_revisions
            WHERE tenant_id = ? AND run_id = ? AND id = ? LIMIT 1
            """,
            (tenant_id, run_id, revision_id),
        ).fetchone()
        if row is None:
            raise NotFound("technology revision not found")
        if row["published_technology_card_id"] is not None:
            return _technology_revision_view(row)
        validation = _json(row["validation_json"], {})
        if str(row["status"]) != "accepted" or validation.get("status") != "passed":
            raise StateConflict("only accepted, valid technology revision can be published")
        section_counts = database.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) AS passed
            FROM estimate_generation_sections
            WHERE tenant_id = ? AND run_id = ?
            """,
            (tenant_id, run_id),
        ).fetchone()
        if section_counts is not None and int(section_counts["total"] or 0) > 0:
            if int(section_counts["passed"] or 0) != int(section_counts["total"]):
                raise StateConflict(
                    "technology card cannot be published before every section review passes"
                )
        published_id = f"technology_card_{uuid.uuid4().hex}"
        base_rules = str(row["rules_version"])
        suffix = f"@generation-r{int(row['revision'])}"
        published_rules = base_rules + suffix
        if len(published_rules) > 120:
            digest = hashlib.sha256(published_rules.encode("utf-8")).hexdigest()[:12]
            published_rules = f"{base_rules[:96]}@{digest}"
        database.execute(
            """
            INSERT INTO technology_cards (
                tenant_id, id, project_id, project_case_id,
                project_case_version, rules_version, status,
                content_json, content_hash, created_by_user_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'ready', ?, ?, ?, ?)
            """,
            (
                tenant_id,
                published_id,
                run["project_id"],
                row["project_case_id"],
                row["project_case_version"],
                published_rules,
                row["snapshot_json"],
                row["snapshot_hash"],
                created_by_user_id,
                timestamp,
            ),
        )
        database.execute(
            """
            UPDATE estimate_generation_technology_revisions
            SET published_technology_card_id = ?
            WHERE tenant_id = ? AND run_id = ? AND id = ?
            """,
            (published_id, tenant_id, run_id, revision_id),
        )
        database.execute(
            """
            UPDATE estimate_generation_runs
            SET status = 'running', stage = 'expansion', updated_at = ?
            WHERE tenant_id = ? AND id = ?
            """,
            (timestamp, tenant_id, run_id),
        )
        _store_command(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request=request,
            result={"publishedTechnologyCardId": published_id},
            now=timestamp,
        )
        updated = database.execute(
            """
            SELECT * FROM estimate_generation_technology_revisions
            WHERE tenant_id = ? AND run_id = ? AND id = ?
            """,
            (tenant_id, run_id, revision_id),
        ).fetchone()
        assert updated is not None
        return _technology_revision_view(updated)


def persist_expanded_lines(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    revision_id: str,
    rows: Sequence[Mapping[str, Any]],
    idempotency_key: str,
    producing_task_id: str | None = None,
    producing_checkpoint_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or not rows:
        raise ValidationFailure("expanded rows must be a non-empty array")
    request = {
        "revisionId": revision_id,
        "rows": [dict(row) for row in rows],
        "producingTaskId": producing_task_id,
        "producingCheckpointId": producing_checkpoint_id,
    }
    operation = f"lines.persist:{revision_id}"
    timestamp = _now(database, now)
    with transaction(database, immediate=True):
        replay = _command_replay(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request=request,
        )
        if replay is not None:
            return replay
        run = _run_row(database, tenant_id=tenant_id, run_id=run_id)
        if str(run["status"]) in _FINAL_RUN_STATUSES:
            raise StateConflict("final run cannot persist expanded lines")
        revision = database.execute(
            """
            SELECT id FROM estimate_generation_technology_revisions
            WHERE tenant_id = ? AND run_id = ? AND id = ? LIMIT 1
            """,
            (tenant_id, run_id, revision_id),
        ).fetchone()
        if revision is None:
            raise NotFound("technology revision not found")
        if producing_task_id is not None:
            task = _task_row(database, tenant_id=tenant_id, task_id=producing_task_id)
            if str(task["run_id"]) != run_id or str(task["status"]) != "succeeded":
                raise StateConflict("producing task must be succeeded in this run")
        if producing_checkpoint_id is not None:
            checkpoint = database.execute(
                """
                SELECT id FROM estimate_generation_checkpoints
                WHERE tenant_id = ? AND run_id = ? AND id = ? LIMIT 1
                """,
                (tenant_id, run_id, producing_checkpoint_id),
            ).fetchone()
            if checkpoint is None:
                raise NotFound("producing checkpoint not found")
        seen: set[str] = set()
        for index, raw_row in enumerate(rows):
            if not isinstance(raw_row, Mapping):
                raise ValidationFailure(f"rows[{index}] must be an object")
            row = dict(raw_row)
            row_id = _identifier(row.get("id"), field=f"rows[{index}].id")
            if row_id in seen:
                raise ValidationFailure(f"duplicate expanded row id: {row_id}")
            seen.add(row_id)
            operation_id = _identifier(
                _field(row, "operation_id", "operationId"),
                field=f"rows[{index}].operationId",
            )
            resource_id = _identifier(
                _field(row, "resource_id", "resourceId"),
                field=f"rows[{index}].resourceId",
            )
            section_key = _identifier(
                _field(row, "section_key", "sectionKey"),
                field=f"rows[{index}].sectionKey",
            )
            linked_revision = str(
                _field(row, "technology_card_revision_id", "technologyCardRevisionId")
                or _field(row, "technology_card_version", "technologyCardVersion")
                or ""
            )
            if linked_revision != revision_id:
                raise ValidationFailure(f"rows[{index}] technology revision mismatch")
            confidence = str(_field(row, "line_confidence", "lineConfidence") or "missing")
            if confidence not in LINE_CONFIDENCE:
                raise ValidationFailure(f"rows[{index}].lineConfidence is invalid")
            evidence_value = _field(row, "evidence_id", "evidenceId")
            evidence_id = str(evidence_value) if evidence_value else None
            if confidence in {"source_backed", "verified"} and evidence_id is None:
                raise ValidationFailure(f"rows[{index}] {confidence} confidence requires evidence")
            if evidence_id is not None:
                evidence = database.execute(
                    """
                    SELECT confidence_status FROM estimate_generation_evidence
                    WHERE tenant_id = ? AND run_id = ? AND id = ? LIMIT 1
                    """,
                    (tenant_id, run_id, evidence_id),
                ).fetchone()
                if evidence is None:
                    raise NotFound(f"rows[{index}] evidence is not registered")
                if LINE_CONFIDENCE.index(confidence) > LINE_CONFIDENCE.index(
                    str(evidence["confidence_status"])
                ):
                    raise ValidationFailure(f"rows[{index}] overstates evidence confidence")
            row_task_id = (
                str(_field(row, "producing_task_id", "producingTaskId"))
                if _field(row, "producing_task_id", "producingTaskId")
                else producing_task_id
            )
            row_checkpoint_id = (
                str(_field(row, "producing_checkpoint_id", "producingCheckpointId"))
                if _field(row, "producing_checkpoint_id", "producingCheckpointId")
                else producing_checkpoint_id
            )
            row_hash = content_hash(row)
            database.execute(
                """
                INSERT INTO estimate_generation_lineage (
                    tenant_id, id, run_id, technology_revision_id,
                    producing_task_id, producing_checkpoint_id, row_id,
                    section_key, operation_id, resource_id, evidence_id,
                    line_confidence, line_snapshot_json, line_snapshot_hash,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    f"estimate_generation_lineage_{uuid.uuid4().hex}",
                    run_id,
                    revision_id,
                    row_task_id,
                    row_checkpoint_id,
                    row_id,
                    section_key,
                    operation_id,
                    resource_id,
                    evidence_id,
                    confidence,
                    canonical_json(row),
                    row_hash,
                    timestamp,
                ),
            )
        database.execute(
            """
            UPDATE estimate_generation_runs
            SET status = 'running', stage = 'reconciliation', updated_at = ?
            WHERE tenant_id = ? AND id = ?
            """,
            (timestamp, tenant_id, run_id),
        )
        result = {
            "runId": run_id,
            "technologyRevisionId": revision_id,
            "rowCount": len(rows),
            "rowsHash": content_hash([dict(row) for row in rows]),
        }
        _store_command(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request=request,
            result=result,
            now=timestamp,
        )
        return result


def transition_generation_run(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    expected_statuses: Sequence[str],
    target_status: str,
    target_stage: str,
    quality_report: Mapping[str, Any] | None = None,
    result_document_id: str | None = None,
    result_version: int | None = None,
    error: Mapping[str, Any] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Apply an idempotent optimistic run transition with final-state gates."""

    if target_status not in RUN_STATUSES:
        raise ValidationFailure("target_status is invalid")
    if target_stage not in RUN_STAGES:
        raise ValidationFailure("target_stage is invalid")
    expected = frozenset(expected_statuses)
    if not expected or not expected <= RUN_STATUSES:
        raise ValidationFailure("expected_statuses are invalid")
    if quality_report is not None and not isinstance(quality_report, Mapping):
        raise ValidationFailure("quality_report must be an object")
    if error is not None and not isinstance(error, Mapping):
        raise ValidationFailure("error must be an object")
    if (result_document_id is None) != (result_version is None):
        raise ValidationFailure("result document and version must be provided together")
    if result_version is not None and result_version < 1:
        raise ValidationFailure("result_version must be positive")
    if target_status == "ready":
        if target_stage != "complete":
            raise ValidationFailure("ready run must be in complete stage")
        if quality_report is None or quality_report.get("status") != "passed":
            raise ValidationFailure("ready run requires a passed quality report")
        if result_document_id is None or result_version is None:
            raise ValidationFailure("ready run requires persisted EstimateVersion linkage")
    timestamp = _now(database, now)
    with transaction(database, immediate=True):
        row = _run_row(database, tenant_id=tenant_id, run_id=run_id)
        current_status = str(row["status"])
        if current_status == target_status:
            if str(row["stage"]) != target_stage:
                raise StateConflict("run already has target status at another stage")
            return _run_view(row)
        if current_status not in expected:
            raise StateConflict(
                f"run status {current_status} is outside expected states {sorted(expected)}"
            )
        if target_status not in _RUN_TRANSITIONS[current_status]:
            raise StateConflict(f"run transition {current_status} -> {target_status} is invalid")
        quality_status = str(row["quality_status"])
        if quality_report is not None:
            quality_status = "passed" if quality_report.get("status") == "passed" else "failed"
        finished_at = timestamp if target_status in _FINAL_RUN_STATUSES else None
        database.execute(
            """
            UPDATE estimate_generation_runs
            SET status = ?, stage = ?, quality_status = ?,
                quality_report_json = ?, result_document_id = ?,
                result_estimate_version = ?, last_error_json = ?,
                updated_at = ?, finished_at = ?
            WHERE tenant_id = ? AND id = ? AND status = ?
            """,
            (
                target_status,
                target_stage,
                quality_status,
                canonical_json(dict(quality_report)) if quality_report is not None else None,
                result_document_id,
                result_version,
                canonical_json(dict(error)) if error is not None else None,
                timestamp,
                finished_at,
                tenant_id,
                run_id,
                current_status,
            ),
        )
        checkpoint_status = {
            "ready": "completed",
            "failed": "failed",
            "cancelled": "failed",
            "needs_input": "needs_input",
        }.get(target_status, "started")
        checkpoint_key = (
            f"orchestrator:terminal:{target_status}"
            if target_status in {"ready", "failed", "cancelled", "needs_input"}
            else (
                "orchestrator:transition:"
                f"{target_status}:{target_stage}:{uuid.uuid4().hex}"
            )
        )
        _append_checkpoint_locked(
            database,
            tenant_id=tenant_id,
            run_id=run_id,
            stage=target_stage,
            status=checkpoint_status,
            payload={"fromStatus": current_status, "toStatus": target_status},
            checkpoint_key=checkpoint_key,
            section_key=None,
            task_id=None,
            now=timestamp,
        )
        return _run_view(_run_row(database, tenant_id=tenant_id, run_id=run_id))
