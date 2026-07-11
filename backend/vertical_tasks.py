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
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from artifact_runtime import (
    EstimateSpec,
    deterministic_estimate,
    reject_secret_material,
    validate_structured_value,
)


VERTICAL_TASK_SCHEMA = "kolibri.public-task.v1"
ESTIMATE_FALLBACK_ENGINE = "kolibri.estimate-readiness-gate.v1"
ESTIMATE_FALLBACK_PROOF_SCHEMA = "kolibri.estimate-readiness-proof.v1"
ESTIMATE_READINESS_SCHEMA = "kolibri.estimate-readiness.v1"
ESTIMATE_READINESS_EDITOR_SCHEMA = "kolibri.estimate-input-editor.v1"
MAX_PROVIDER_ESTIMATE_LINES = 32
MAX_PROVIDER_ESTIMATE_RESPONSE_BYTES = 24_576
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class _StrictTask(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _validate_public_structure(value: dict[str, Any], *, label: str) -> dict[str, Any]:
    validate_structured_value(value, label=label)
    reject_secret_material(value, label=label)
    return value


def _validated_provider_source_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("provider source URL must be a credential-free HTTP(S) URL")
    return value


def _validated_price_level(value: str) -> str:
    if re.fullmatch(r"\d{4}-Q[1-4]", value):
        return value
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("provider price-level date must be a real ISO date or quarter") from exc
    return value


class ProviderEstimatePriceProvenance(_StrictTask):
    """Provider assertion about a unit price; never an independent verification."""

    source: Literal["normative", "catalog", "contract", "supplier"]
    source_ref: str = Field(min_length=1, max_length=500)
    source_url: str = Field(
        min_length=8,
        max_length=2_048,
        pattern=r"^https?://[^\s]+$",
    )
    captured_at: str = Field(
        min_length=10,
        max_length=10,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    price_level_date: str = Field(
        min_length=7,
        max_length=20,
        pattern=r"^(?:\d{4}-\d{2}-\d{2}|\d{4}-Q[1-4])$",
    )
    applicable_region: str = Field(min_length=1, max_length=300)
    basis_ref: str = Field(min_length=1, max_length=500)
    assumptions: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("assumptions")
    @classmethod
    def validate_assumptions(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 1_000 for value in values):
            raise ValueError("provider price assumptions must contain 1 to 1000 characters")
        return values

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        return _validated_provider_source_url(value)

    @field_validator("captured_at")
    @classmethod
    def validate_capture_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("provider capture date must be a real ISO date") from exc
        return value

    @field_validator("price_level_date")
    @classmethod
    def validate_price_level(cls, value: str) -> str:
        return _validated_price_level(value)


class ProviderEstimateQuantityProvenance(_StrictTask):
    source: Literal["project", "measurement", "manual"]
    source_ref: str = Field(min_length=1, max_length=500)
    source_url: str | None = Field(
        default=None,
        min_length=8,
        max_length=2_048,
        pattern=r"^https?://[^\s]+$",
    )
    assumptions: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("assumptions")
    @classmethod
    def validate_assumptions(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 1_000 for value in values):
            raise ValueError("provider quantity assumptions must contain 1 to 1000 characters")
        return values

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        return _validated_provider_source_url(value) if value is not None else None


class ProviderEstimateLine(_StrictTask):
    id: str = Field(min_length=2, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,199}$")
    description: str = Field(min_length=1, max_length=1_000)
    category: Literal["labor", "material", "equipment", "service", "other"]
    unit: str = Field(min_length=1, max_length=40)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    unit_price_minor: int = Field(ge=0, le=10**15)
    price_provenance: ProviderEstimatePriceProvenance
    quantity_provenance: ProviderEstimateQuantityProvenance
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    # Accepted only to prove that provider arithmetic is ignored.  Neither
    # value enters EstimateSpec or the deterministic calculation.
    line_total_minor: int | None = Field(default=None, ge=0, le=10**18)
    total_minor: int | None = Field(default=None, ge=0, le=10**18)

    @field_validator("assumptions")
    @classmethod
    def validate_assumptions(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 1_000 for value in values):
            raise ValueError("provider line assumptions must contain 1 to 1000 characters")
        return values


class ProviderEstimateSection(_StrictTask):
    id: str = Field(min_length=2, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,199}$")
    name: str = Field(min_length=1, max_length=200)
    lines: list[ProviderEstimateLine] = Field(min_length=1, max_length=MAX_PROVIDER_ESTIMATE_LINES)


class ProviderEstimateBasis(_StrictTask):
    calculation_method: Literal[
        "resource-index", "resource", "base-index", "contract", "commercial",
    ]
    normative_basis_ref: str = Field(min_length=1, max_length=1_000)
    normative_edition: str = Field(min_length=1, max_length=300)
    price_level_date: str = Field(
        min_length=7,
        max_length=20,
        pattern=r"^(?:\d{4}-\d{2}-\d{2}|\d{4}-Q[1-4])$",
    )
    region: str = Field(min_length=1, max_length=300)
    index_document_refs: list[str] = Field(default_factory=list, max_length=20)
    tax_scope_ref: str = Field(min_length=1, max_length=1_000)
    contract_scope_ref: str = Field(min_length=1, max_length=1_000)
    source_urls: list[str] = Field(min_length=1, max_length=20)
    input_document_refs: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_references(self) -> "ProviderEstimateBasis":
        if any(not value.strip() or len(value) > 1_000 for value in self.index_document_refs):
            raise ValueError("provider index refs must contain 1 to 1000 characters")
        if any(not re.fullmatch(r"https?://[^\s]+", value) or len(value) > 2_048 for value in self.source_urls):
            raise ValueError("provider basis source URLs must be bounded HTTP(S) URLs")
        if any(not value.strip() or len(value) > 1_000 for value in self.input_document_refs):
            raise ValueError("provider input refs must contain 1 to 1000 characters")
        if self.calculation_method in {"resource-index", "base-index"} and not self.index_document_refs:
            raise ValueError("indexed provider estimate requires index document refs")
        return self

    @field_validator("price_level_date")
    @classmethod
    def validate_price_level(cls, value: str) -> str:
        return _validated_price_level(value)

    @field_validator("source_urls")
    @classmethod
    def validate_source_urls(cls, values: list[str]) -> list[str]:
        return [_validated_provider_source_url(value) for value in values]


class ProviderReportedTotals(_StrictTask):
    categories_minor: dict[str, int] = Field(default_factory=dict, max_length=20)
    subtotal_minor: int | None = Field(default=None, ge=0, le=10**18)
    overhead_minor: int | None = Field(default=None, ge=0, le=10**18)
    tax_minor: int | None = Field(default=None, ge=0, le=10**18)
    grand_total_minor: int | None = Field(default=None, ge=0, le=10**18)


class ProviderEstimateDraft(_StrictTask):
    """Strict, source-bearing draft returned by an external provider/API."""

    schema_version: Literal["kolibri.estimate-provider-draft.v1"]
    title: str = Field(min_length=1, max_length=500)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    minor_unit: Literal[0, 2, 3] = 2
    region: str = Field(min_length=1, max_length=300)
    client_name: str | None = Field(default=None, max_length=300)
    object_name: str | None = Field(default=None, max_length=500)
    object_address: str | None = Field(default=None, max_length=1_000)
    source_summary: str = Field(min_length=1, max_length=2_000)
    normative_basis: ProviderEstimateBasis
    sections: list[ProviderEstimateSection] = Field(min_length=1, max_length=32)
    assumptions: list[str] = Field(default_factory=list, max_length=12)
    questions: list[str] = Field(default_factory=list, max_length=12)
    overhead_rate_bps: int = Field(default=0, ge=0, le=10_000)
    tax_rate_bps: int = Field(default=0, ge=0, le=10_000)
    reported_totals: ProviderReportedTotals | None = None
    totals: ProviderReportedTotals | None = None
    grand_total_minor: int | None = Field(default=None, ge=0, le=10**18)

    @model_validator(mode="after")
    def validate_draft(self) -> "ProviderEstimateDraft":
        section_ids = [section.id for section in self.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("provider estimate section ids must be unique")
        lines = [line for section in self.sections for line in section.lines]
        if len(lines) > MAX_PROVIDER_ESTIMATE_LINES:
            raise ValueError(
                f"estimate proposal exceeds {MAX_PROVIDER_ESTIMATE_LINES} consolidated lines"
            )
        line_ids = [line.id for line in lines]
        if len(line_ids) != len(set(line_ids)):
            raise ValueError("provider estimate line ids must be unique")
        for label, values in (("assumption", self.assumptions), ("question", self.questions)):
            if any(not value.strip() or len(value) > 2_000 for value in values):
                raise ValueError(f"provider estimate {label} must contain 1 to 2000 characters")
        return self


def provider_estimate_draft_json_schema() -> dict[str, Any]:
    """Machine-readable provider contract embedded in the gateway prompt."""

    return ProviderEstimateDraft.model_json_schema(mode="validation")


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
                "schema_version": "kolibri.estimate-provider-draft.v1",
                "strict_json_schema": provider_estimate_draft_json_schema(),
                "money_rule": (
                    "Propose quantities and unit_price_minor only. Do not return row totals or totals. "
                    "Any reported line/section/grand totals are ignored. Kolibri recalculates every "
                    "monetary value deterministically after schema and provenance validation."
                ),
                "minor_unit_rule": (
                    "minor_unit is the count of decimal currency digits: use 2 for RUB, "
                    "never the multiplier 100. unit_price_minor for RUB is expressed in kopecks."
                ),
                "source_rule": (
                    "Every line requires separate price_provenance and quantity_provenance. "
                    "Price provenance requires source_ref, HTTP(S) source_url, capture date, "
                    "price-level date/quarter, applicable region, basis_ref and assumptions. "
                    "Quantity provenance requires project/measurement/manual source_ref and "
                    "explicit assumptions. An unsourced draft is invalid and receives no money."
                ),
                "output_rule": "Return one JSON object only, without Markdown fences or commentary.",
                "scope_rule": (
                    "Return sections with at most 32 consolidated lines in total. Group work and "
                    "material by construction phase; do not expand a bill of materials, repeat "
                    "narrative, or add commentary. "
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
    "manual", "assumption", "normative", "catalog", "contract", "supplier", "measurement",
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

_UNIT_ALIASES = {
    "м2": "м²",
    "м^2": "м²",
    "м²": "м²",
    "кв.м": "м²",
    "кв. м": "м²",
    "sqm": "м²",
    "m2": "м²",
    "m²": "м²",
    "м3": "м³",
    "м^3": "м³",
    "м³": "м³",
    "куб.м": "м³",
    "куб. м": "м³",
    "m3": "м³",
    "m³": "м³",
    "м": "м",
    "пог.м": "пог. м",
    "пог. м": "пог. м",
    "м.п.": "пог. м",
    "lm": "пог. м",
    "шт": "шт.",
    "шт.": "шт.",
    "pcs": "шт.",
    "pc": "шт.",
    "компл": "компл.",
    "компл.": "компл.",
    "комплект": "компл.",
    "set": "компл.",
    "кг": "кг",
    "т": "т",
    "л": "л",
    "ч": "ч",
    "час": "ч",
    "день": "дн.",
    "дн": "дн.",
    "дн.": "дн.",
    "смена": "смена",
    "рейс": "рейс",
    "маш.-ч": "маш.-ч",
    "маш.ч": "маш.-ч",
}


def normalize_estimate_unit(value: str) -> str:
    """Normalize common construction units without inventing conversions."""

    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text or len(text) > 40 or any(ord(char) < 32 for char in text):
        raise ValueError("estimate unit is invalid")
    key = text.casefold().replace("ё", "е")
    normalized = _UNIT_ALIASES.get(key, text)
    if not re.fullmatch(r"[A-Za-zА-Яа-я0-9²³.%/()\-–—. ]{1,40}", normalized):
        raise ValueError("estimate unit contains unsupported characters")
    return normalized


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
        if value is None or not (
            isinstance(value.get("title"), str)
            and isinstance(value.get("currency"), str)
            and isinstance(value.get("region"), str)
            and (
                isinstance(value.get("lines"), list)
                or isinstance(value.get("sections"), list)
            )
        ):
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
    """Validate a source-bearing provider draft and build an editable spec.

    The provider contract is strict and section-based.  Provider-supplied line
    and grand totals are accepted only as inert compatibility fields and are
    never copied into :class:`EstimateSpec`; the deterministic engine is the
    sole monetary authority.
    """

    if len(response_text.encode("utf-8")) > MAX_PROVIDER_ESTIMATE_RESPONSE_BYTES:
        raise ValueError(
            f"estimate proposal exceeds {MAX_PROVIDER_ESTIMATE_RESPONSE_BYTES} UTF-8 bytes"
        )
    value = _provider_json_object(response_text)
    draft = ProviderEstimateDraft.model_validate(value)
    normalized_requested_region = re.sub(
        r"\s+", " ", str(requested_region or "").strip().casefold().replace("ё", "е"),
    )
    normalized_draft_region = re.sub(
        r"\s+", " ", draft.region.casefold().replace("ё", "е"),
    )
    if normalized_requested_region and not (
        normalized_requested_region == normalized_draft_region
        or normalized_requested_region in normalized_draft_region
        or normalized_draft_region in normalized_requested_region
    ):
        raise ValueError("provider estimate region does not match requested region")
    normalized_basis_region = re.sub(
        r"\s+", " ", draft.normative_basis.region.casefold().replace("ё", "е"),
    )
    if not (
        normalized_basis_region == normalized_draft_region
        or normalized_basis_region in normalized_draft_region
        or normalized_draft_region in normalized_basis_region
    ):
        raise ValueError("provider estimate basis region does not match estimate region")

    lines: list[dict[str, Any]] = []
    for section in draft.sections:
        for line in section.lines:
            combined_assumptions = list(dict.fromkeys([
                *line.price_provenance.assumptions,
                *line.quantity_provenance.assumptions,
                *line.assumptions,
            ]))
            lines.append({
                "id": line.id,
                "section": section.name,
                "description": line.description,
                "category": line.category,
                "unit": normalize_estimate_unit(line.unit),
                "quantity": line.quantity,
                "unit_price_minor": line.unit_price_minor,
                "provenance": {
                    "source": line.price_provenance.source,
                    "source_ref": line.price_provenance.source_ref,
                    "source_url": line.price_provenance.source_url,
                    "captured_at": line.price_provenance.captured_at,
                    "applicable_region": line.price_provenance.applicable_region,
                    "price_level_date": line.price_provenance.price_level_date,
                    "basis_ref": line.price_provenance.basis_ref,
                    "quantity_source": line.quantity_provenance.source,
                    "quantity_source_ref": line.quantity_provenance.source_ref,
                    "quantity_source_url": line.quantity_provenance.source_url,
                    "assumptions": combined_assumptions,
                    # A provider can assert a source, but only a later policy
                    # verifier may advance this flag.
                    "validation_status": "unverified",
                },
            })
    basis = draft.normative_basis.model_dump(mode="json")
    basis["validation_status"] = "unverified"
    return EstimateSpec.model_validate({
        "title": draft.title,
        "currency": draft.currency,
        "minor_unit": draft.minor_unit,
        "region": draft.region,
        "client_name": draft.client_name,
        "object_name": draft.object_name,
        "object_address": draft.object_address,
        "source_summary": draft.source_summary,
        "normative_basis": basis,
        "assumptions": draft.assumptions,
        "questions": draft.questions,
        "lines": lines,
        "overhead_rate_bps": draft.overhead_rate_bps,
        "tax_rate_bps": draft.tax_rate_bps,
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


def assess_normative_estimate(spec: EstimateSpec) -> dict[str, Any]:
    """Describe source coverage separately from independent verification.

    A draft may be calculated while still preliminary.  ``verified`` is
    reserved for complete inputs whose basis and every line source were
    independently advanced to ``validation_status=verified``.
    """

    coverage_missing: list[str] = []
    validation_missing: list[str] = []
    basis = spec.normative_basis
    if basis is None:
        coverage_missing.extend([
            "normative_basis.calculation_method",
            "normative_basis.normative_basis_ref",
            "normative_basis.normative_edition",
            "normative_basis.price_level_date",
            "normative_basis.region",
            "normative_basis.tax_scope_ref",
            "normative_basis.contract_scope_ref",
            "normative_basis.source_urls",
            "normative_basis.input_document_refs",
        ])
        validation_missing.append("normative_basis.validation_status")
    else:
        if basis.region.casefold() != spec.region.casefold():
            coverage_missing.append("normative_basis.region_matches_estimate")
        if not basis.source_urls:
            coverage_missing.append("normative_basis.source_urls")
        if not basis.input_document_refs:
            coverage_missing.append("normative_basis.input_document_refs")
        if basis.validation_status != "verified":
            validation_missing.append("normative_basis.validation_status")
    for line in spec.lines:
        prefix = f"lines.{line.id}.provenance"
        provenance = line.provenance
        if provenance.source not in {"normative", "catalog", "contract", "supplier"}:
            coverage_missing.append(f"{prefix}.sourced_price")
        if not provenance.source_ref:
            coverage_missing.append(f"{prefix}.source_ref")
        if not provenance.source_url:
            coverage_missing.append(f"{prefix}.source_url")
        if not provenance.captured_at:
            coverage_missing.append(f"{prefix}.captured_at")
        if not provenance.applicable_region:
            coverage_missing.append(f"{prefix}.applicable_region")
        elif provenance.applicable_region.casefold() != spec.region.casefold():
            coverage_missing.append(f"{prefix}.applicable_region_matches_estimate")
        if not provenance.price_level_date:
            coverage_missing.append(f"{prefix}.price_level_date")
        if not provenance.basis_ref:
            coverage_missing.append(f"{prefix}.basis_ref")
        if not provenance.quantity_source:
            coverage_missing.append(f"{prefix}.quantity_source")
        if not provenance.quantity_source_ref:
            coverage_missing.append(f"{prefix}.quantity_source_ref")
        if provenance.validation_status != "verified":
            validation_missing.append(f"{prefix}.validation_status")
    coverage_missing = sorted(set(coverage_missing))
    validation_missing = sorted(set(validation_missing))
    missing = [*coverage_missing, *validation_missing]
    verification_kind = (
        "normative"
        if basis is not None and basis.calculation_method in {"resource-index", "resource", "base-index"}
        else "commercial"
    )
    verified = not missing
    payload = {
        "schema_version": "kolibri.normative-estimate-gate.v1",
        "status": "verified" if verified else "preliminary",
        "verification_kind": verification_kind,
        "monetary_status": "calculated",
        "source_coverage_complete": not coverage_missing,
        "input_complete": bool(basis is not None and basis.input_document_refs) and not coverage_missing,
        "independent_validation_complete": not validation_missing,
        "normative_verified": verified and verification_kind == "normative",
        "commercial_verified": verified and verification_kind == "commercial",
        "missing": missing,
        "coverage_missing": coverage_missing,
        "validation_missing": validation_missing,
        "line_count": len(spec.lines),
        "claim": (
            "verified_estimate" if verified
            else "preliminary_editable_estimate_not_for_contract_without_source_review"
        ),
    }
    return {**payload, "binding_sha256": _canonical_sha256(payload)}


_READINESS_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "id": "project_documents",
        "label": "Проектная документация",
        "fields": ["project_document_set_ref", "design_scope", "specifications_ref"],
        "evidence": "Утверждённый проект, спецификации и состав работ с версиями документов.",
    },
    {
        "id": "site_surveys",
        "label": "Участок и изыскания",
        "fields": ["site_address", "geology_ref", "geodesy_ref", "utility_connection_terms_ref"],
        "evidence": "Адрес участка, инженерно-геологические и геодезические материалы, условия подключений.",
    },
    {
        "id": "quantities",
        "label": "Ведомость объёмов",
        "fields": ["work_quantity_statement_ref", "quantity_source", "quantity_source_ref", "measurement_date"],
        "evidence": "Объёмы из проекта или замеров; для каждой позиции — единица, количество и ссылка на лист/акт.",
    },
    {
        "id": "pricing",
        "label": "Расчётная и ценовая база",
        "fields": [
            "calculation_method", "normative_basis_ref", "normative_edition",
            "price_level_date_or_quarter", "price_region", "index_document_refs",
            "supplier_catalog_contract_refs",
        ],
        "evidence": "Применимая база и редакция, уровень цен, документы индексов либо датированные предложения/договоры.",
    },
    {
        "id": "tax_and_contract",
        "label": "Договорный и налоговый контур",
        "fields": ["contract_scope_ref", "tax_regime", "vat_rate", "tax_basis_ref", "included_excluded_scope"],
        "evidence": "Границы договора, налоговый режим и основание ставки, перечень включённых и исключённых затрат.",
    },
    {
        "id": "technical_scope",
        "label": "Конструктив и инженерные системы",
        "fields": [
            "foundation_solution", "wall_solution", "roof_solution", "openings_spec",
            "mep_scope", "finish_level", "external_networks_scope", "site_works_scope",
        ],
        "evidence": "Принятые проектом решения по фундаменту, коробке, кровле, инженерии, отделке и наружным работам.",
    },
)

_READINESS_SECTIONS = (
    "Подготовка, проектирование и изыскания",
    "Земляные работы и фундамент",
    "Несущие и ограждающие конструкции",
    "Кровля",
    "Окна, наружные двери и фасад",
    "Инженерные системы",
    "Внутренняя отделка",
    "Наружные сети и благоустройство",
    "Логистика, временные и прочие затраты",
)


_READINESS_FIELD_PRESENTATION: dict[str, dict[str, Any]] = {
    "project_document_set_ref": {"label": "Комплект проектной документации", "placeholder": "Ссылка, номер и редакция комплекта"},
    "design_scope": {"label": "Состав проектных решений", "placeholder": "Разделы проекта и стадия документации", "input_type": "textarea"},
    "specifications_ref": {"label": "Спецификации", "placeholder": "Ссылки на ведомости и спецификации"},
    "site_address": {"label": "Адрес участка", "placeholder": "Полный адрес или кадастровый номер"},
    "geology_ref": {"label": "Инженерная геология", "placeholder": "Номер и дата отчёта"},
    "geodesy_ref": {"label": "Инженерная геодезия", "placeholder": "Номер и дата отчёта"},
    "utility_connection_terms_ref": {"label": "Технические условия подключений", "placeholder": "Ссылки на действующие ТУ"},
    "work_quantity_statement_ref": {"label": "Ведомость объёмов работ", "placeholder": "Документ, редакция, листы"},
    "quantity_source": {
        "label": "Источник объёмов", "input_type": "select",
        "options": ["project", "measurement", "manual"],
    },
    "quantity_source_ref": {"label": "Ссылка на источник объёмов", "placeholder": "Лист проекта или акт замеров"},
    "measurement_date": {"label": "Дата замеров", "input_type": "date"},
    "calculation_method": {
        "label": "Метод расчёта", "input_type": "select",
        "options": ["resource-index", "resource", "base-index", "contract", "commercial"],
    },
    "normative_basis_ref": {"label": "Сметно-нормативная база", "placeholder": "Документ и основание применимости"},
    "normative_edition": {"label": "Редакция базы", "placeholder": "Версия или дата редакции"},
    "price_level_date_or_quarter": {"label": "Уровень цен", "placeholder": "Дата или квартал"},
    "price_region": {"label": "Ценовая зона / регион", "placeholder": "Регион применимости расценок"},
    "index_document_refs": {"label": "Документы индексов", "placeholder": "Номера, даты и ссылки", "input_type": "textarea"},
    "supplier_catalog_contract_refs": {"label": "Ценовые подтверждения", "placeholder": "КП, каталоги и договоры с датами", "input_type": "textarea"},
    "contract_scope_ref": {"label": "Границы договора", "placeholder": "Документ и редакция"},
    "tax_regime": {"label": "Налоговый режим", "placeholder": "Режим исполнителя"},
    "vat_rate": {"label": "Ставка НДС", "placeholder": "Ставка или «без НДС»"},
    "tax_basis_ref": {"label": "Основание налогового расчёта", "placeholder": "Документ или реквизиты"},
    "included_excluded_scope": {"label": "Включено / исключено", "placeholder": "Границы стоимости", "input_type": "textarea"},
    "foundation_solution": {"label": "Фундамент", "placeholder": "Решение по проекту", "input_type": "textarea"},
    "wall_solution": {"label": "Стены и перегородки", "placeholder": "Материалы и конструкция", "input_type": "textarea"},
    "roof_solution": {"label": "Кровля", "placeholder": "Конструкция и покрытие", "input_type": "textarea"},
    "openings_spec": {"label": "Окна и двери", "placeholder": "Спецификация проёмов", "input_type": "textarea"},
    "mep_scope": {"label": "Инженерные системы", "placeholder": "ОВ, ВК, ЭОМ и другие разделы", "input_type": "textarea"},
    "finish_level": {"label": "Уровень отделки", "placeholder": "Состав и класс материалов", "input_type": "textarea"},
    "external_networks_scope": {"label": "Наружные сети", "placeholder": "Точки подключения и протяжённость", "input_type": "textarea"},
    "site_works_scope": {"label": "Благоустройство", "placeholder": "Состав работ на участке", "input_type": "textarea"},
}


def _brief_area_fact(brief: str) -> Decimal | None:
    match = _HOUSE_AREA.search(brief)
    if match is None:
        return None
    try:
        area = Decimal(match.group("area").replace(",", "."))
    except InvalidOperation:
        return None
    if area <= 0 or area > Decimal("10000000"):
        return None
    return area.quantize(Decimal("0.01"))


def _estimate_readiness_payload(task: EstimateVerticalTask) -> dict[str, Any] | None:
    brief = str(task.brief or "")
    spec = task.spec
    if not brief and spec is None:
        return None
    normalized = brief.casefold().replace("ё", "е")
    region = task.region or (spec.region if spec is not None else None) or (
        "Республика Татарстан" if "татарстан" in normalized
        else "Регион требует подтверждения"
    )
    locality = "Лениногорск" if "лениногорск" in normalized else None
    area = _brief_area_fact(brief)
    one_storey_house = bool(
        area is not None
        and area >= Decimal("20")
        and area <= Decimal("5000")
        and _is_house_construction_brief(brief)
    )
    known_facts: dict[str, Any] = {
        "object_type": "one_storey_house" if one_storey_house else "unspecified",
        "object_type_label": (
            "Одноэтажный жилой дом"
            if one_storey_house else "Тип объекта требует подтверждения"
        ),
        "region": region,
        "locality": locality,
        "currency": spec.currency if spec is not None else "RUB",
    }
    if one_storey_house:
        known_facts["storeys"] = 1
    if area is not None:
        known_facts["gross_area_m2"] = _display_decimal(area)
    if spec is not None:
        known_facts.update({
            "estimate_title": spec.title,
            "object_name": spec.object_name,
            "object_address": spec.object_address,
        })
    required_inputs = [{**group, "status": "missing"} for group in _READINESS_GROUPS]
    editor_fields = [
        {
            "id": field,
            "group_id": group["id"],
            "label": _READINESS_FIELD_PRESENTATION.get(field, {}).get("label", field.replace("_", " ")),
            "input_type": _READINESS_FIELD_PRESENTATION.get(field, {}).get("input_type", "text"),
            "placeholder": _READINESS_FIELD_PRESENTATION.get(field, {}).get("placeholder", ""),
            **({"options": _READINESS_FIELD_PRESENTATION[field]["options"]} if "options" in _READINESS_FIELD_PRESENTATION.get(field, {}) else {}),
            **({"suggested_value": region} if field == "price_region" and region != "Регион требует подтверждения" else {}),
            "value": None,
            "required": True,
        }
        for group in _READINESS_GROUPS
        for field in group["fields"]
    ]
    return {
        "schema_version": ESTIMATE_READINESS_SCHEMA,
        "title": (
            f"Исходные данные для сметы: одноэтажный дом {_display_decimal(area)} м²"
            if one_storey_house and area is not None
            else f"Исходные данные для сметы: {spec.title}" if spec is not None
            else "Исходные данные для правдивой сметы"
        ),
        "status": "needs_input",
        "normative_verified": False,
        "monetary_status": "not_calculated",
        "known_facts": known_facts,
        "required_inputs": required_inputs,
        "normative_gate": {
            "schema_version": "kolibri.normative-estimate-gate.v1",
            "status": "blocked_missing_inputs",
            "required_basis": [
                "Документ, подтверждающий применимый метод расчёта. Если применяется Методика по приказу Минстроя России № 421/пр, нужна её действующая для даты расчёта редакция.",
                "Применимая сметно-нормативная база/метод расчёта и регион.",
                "Уровень цен на дату или квартал расчёта; индекс не подставляется без документа-источника.",
                "Объёмы по проекту или замерам и цены из ручного ввода, каталога, договора или предложения поставщика со ссылками.",
                "Налоговый и договорный состав затрат с документом-основанием.",
            ],
            "official_references": [
                {
                    "title": "Приказ Минстроя России от 04.08.2020 № 421/пр",
                    "url": "https://publication.pravo.gov.ru/Document/View/0001202009240006",
                },
                {
                    "title": "Минстрой России: ценообразование и индексы",
                    "url": "https://minstroyrf.gov.ru/trades/tsenoobrazovanie/",
                },
            ],
            "source_policy": {
                "price_sources": ["normative", "catalog", "contract", "supplier"],
                "quantity_sources": ["project", "measurement", "manual"],
                "source_ref_required": True,
                "applicable_basis_index_date_required": True,
            },
        },
        "draft_sections": [
            {"id": f"section-{index}", "label": label, "status": "awaiting_scope", "items": []}
            for index, label in enumerate(_READINESS_SECTIONS, 1)
        ],
        "editor": {
            "schema_version": ESTIMATE_READINESS_EDITOR_SCHEMA,
            "state": "needs_input",
            "fields": editor_fields,
        },
    }


def _estimate_readiness_proof(
    *,
    input_facts_sha256: str,
    readiness_sha256: str,
    fallback_reason: str,
    source_mode: str,
    provider_binding: dict[str, Any] | None,
) -> dict[str, Any]:
    proof = {
        "schema_version": ESTIMATE_FALLBACK_PROOF_SCHEMA,
        "engine": ESTIMATE_FALLBACK_ENGINE,
        "mode": "needs_input",
        "input_facts_sha256": input_facts_sha256,
        "readiness_sha256": readiness_sha256,
        "fallback_reason": fallback_reason,
        "source_mode": source_mode,
        "provider_binding": provider_binding,
    }
    return {**proof, "binding_sha256": _canonical_sha256(proof)}


def _build_estimate_readiness_task(
    task: EstimateVerticalTask,
    *,
    reason: str,
    provider_binding: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    readiness = _estimate_readiness_payload(task)
    if readiness is None:
        return None
    reason = str(reason or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{1,80}", reason):
        reason = "provider_unavailable"
    provider_binding = provider_binding if isinstance(provider_binding, dict) else None
    provider_verified = bool(
        provider_binding
        and _SHA256.fullmatch(str(provider_binding.get("output_sha256") or "").lower())
        and _SHA256.fullmatch(str(provider_binding.get("verifier_binding_sha256") or "").lower())
    )
    source_mode = "provider_reviewed" if provider_verified else "local_gate"
    requested = requested_deliverables(task)
    input_facts = {
        **readiness["known_facts"],
        **({
            "request_brief_sha256": hashlib.sha256(task.brief.encode("utf-8")).hexdigest(),
        } if task.brief else {}),
        **({
            "request_spec_sha256": _canonical_sha256(task.spec.model_dump(mode="json")),
        } if task.spec is not None else {}),
        "requested_artifacts": requested,
    }
    proof = _estimate_readiness_proof(
        input_facts_sha256=_canonical_sha256(input_facts),
        readiness_sha256=_canonical_sha256(readiness),
        fallback_reason=reason,
        source_mode=source_mode,
        provider_binding=provider_binding if provider_verified else None,
    )
    return {
        "schema_version": VERTICAL_TASK_SCHEMA,
        "intent": "estimate",
        "status": "incomplete",
        "execution": {
            "status": "completed",
            "model": "kolibri",
            "provider_verified": provider_verified,
            "provider_status": "completed" if provider_verified else "failed",
            "engine_verified": True,
            "engine": ESTIMATE_FALLBACK_ENGINE,
            "engine_binding_sha256": proof["binding_sha256"],
            "fallback_reason": reason,
            **(provider_binding if provider_verified and provider_binding else {}),
        },
        "result": {
            "type": "estimate_readiness",
            "readiness": readiness,
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


def build_deterministic_estimate_fallback(
    task: VerticalTask,
    *,
    reason: str = "provider_unavailable",
) -> dict[str, Any] | None:
    """After provider exhaustion, return a bound input checklist without money."""

    if not isinstance(task, EstimateVerticalTask) or task.spec is not None:
        return None
    return _build_estimate_readiness_task(task, reason=reason)


def verified_deterministic_estimate_fallback(task: dict[str, Any]) -> bool:
    """Recompute readiness hashes and reject any fabricated monetary payload."""

    if task.get("intent") != "estimate" or task.get("schema_version") != VERTICAL_TASK_SCHEMA:
        return False
    execution = task.get("execution") if isinstance(task.get("execution"), dict) else {}
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    proof = result.get("generation") if isinstance(result.get("generation"), dict) else {}
    if not (
        execution.get("status") == "completed"
        and execution.get("model") == "kolibri"
        and execution.get("engine_verified") is True
        and execution.get("engine") == ESTIMATE_FALLBACK_ENGINE
        and proof.get("schema_version") == ESTIMATE_FALLBACK_PROOF_SCHEMA
        and proof.get("engine") == ESTIMATE_FALLBACK_ENGINE
        and proof.get("mode") == "needs_input"
    ):
        return False
    provider_verified = execution.get("provider_verified") is True
    if execution.get("provider_status") != ("completed" if provider_verified else "failed"):
        return False
    source_mode = "provider_reviewed" if provider_verified else "local_gate"
    if proof.get("source_mode") != source_mode:
        return False
    provider_binding = proof.get("provider_binding")
    if provider_verified:
        if not isinstance(provider_binding, dict):
            return False
        if not all(_valid_digest(provider_binding.get(key)) for key in (
            "output_sha256", "verifier_binding_sha256",
        )):
            return False
        if any(execution.get(key) != provider_binding.get(key) for key in (
            "output_sha256", "verifier_binding_sha256",
        )):
            return False
    elif provider_binding is not None:
        return False
    if result.get("type") != "estimate_readiness":
        return False
    readiness = result.get("readiness") if isinstance(result.get("readiness"), dict) else {}
    if not (
        readiness.get("schema_version") == ESTIMATE_READINESS_SCHEMA
        and readiness.get("status") == "needs_input"
        and readiness.get("normative_verified") is False
        and readiness.get("monetary_status") == "not_calculated"
        and "calculation" not in result
        and "estimate" not in result
    ):
        return False
    forbidden_money_keys = {
        "unit_price_minor", "line_total_minor", "totals", "subtotal_minor",
        "grand_total_minor", "tax_minor", "overhead_minor", "amount_minor",
    }
    def contains_money(value: Any) -> bool:
        if isinstance(value, dict):
            return any(str(key).lower() in forbidden_money_keys or contains_money(item) for key, item in value.items())
        if isinstance(value, list):
            return any(contains_money(item) for item in value)
        return False
    if contains_money(readiness):
        return False
    required_inputs = readiness.get("required_inputs")
    if not isinstance(required_inputs, list) or [item.get("id") for item in required_inputs if isinstance(item, dict)] != [
        group["id"] for group in _READINESS_GROUPS
    ]:
        return False
    if any(not isinstance(item, dict) or item.get("status") != "missing" for item in required_inputs):
        return False
    sections = readiness.get("draft_sections")
    if not isinstance(sections, list) or len(sections) != len(_READINESS_SECTIONS):
        return False
    if any(not isinstance(section, dict) or section.get("items") != [] for section in sections):
        return False
    input_facts = proof.get("input_facts") if isinstance(proof.get("input_facts"), dict) else {}
    known_fact_keys = set(readiness.get("known_facts", {}))
    input_fact_keys = set(input_facts)
    source_hash_keys = input_fact_keys - known_fact_keys - {"requested_artifacts"}
    if not source_hash_keys or not source_hash_keys <= {
        "request_brief_sha256", "request_spec_sha256",
    }:
        return False
    if any(not _valid_digest(input_facts.get(key)) for key in source_hash_keys):
        return False
    if input_fact_keys != known_fact_keys | source_hash_keys | {"requested_artifacts"}:
        return False
    if input_facts.get("object_type") == "one_storey_house":
        if input_facts.get("storeys") != 1:
            return False
        try:
            input_area = Decimal(str(input_facts.get("gross_area_m2")))
        except InvalidOperation:
            return False
        if input_area < Decimal("20") or input_area > Decimal("5000"):
            return False
    elif input_facts.get("object_type") != "unspecified":
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
    readiness_sha256 = str(proof.get("readiness_sha256") or "").lower()
    fallback_reason = str(proof.get("fallback_reason") or "")
    if not re.fullmatch(r"[a-z0-9_]{1,80}", fallback_reason):
        return False
    if execution.get("fallback_reason") != fallback_reason:
        return False
    if not all(_valid_digest(value) for value in (input_facts_sha256, readiness_sha256)):
        return False
    if input_facts_sha256 != _canonical_sha256(input_facts):
        return False
    if readiness_sha256 != _canonical_sha256(readiness):
        return False
    expected = _estimate_readiness_proof(
        input_facts_sha256=input_facts_sha256,
        readiness_sha256=readiness_sha256,
        fallback_reason=fallback_reason,
        source_mode=source_mode,
        provider_binding=provider_binding,
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
        "type": "deterministic_estimate_readiness",
        "engine": ESTIMATE_FALLBACK_ENGINE,
        "provider_verified": task["execution"].get("provider_verified") is True,
        "normative_verified": False,
        "readiness_sha256": proof["readiness_sha256"],
        "binding_sha256": proof["binding_sha256"],
    }


def deterministic_estimate_fallback_text(task: dict[str, Any]) -> str:
    if not verified_deterministic_estimate_fallback(task):
        raise ValueError("deterministic estimate fallback verification failed")
    result = task["result"]
    readiness = result["readiness"]
    facts = readiness["known_facts"]
    delivery = task.get("artifact_delivery") if isinstance(task.get("artifact_delivery"), dict) else {}
    pdf_ready = "pdf" in set(delivery.get("delivered") or [])
    fact_summary = [str(facts.get("object_type_label") or "Объект требует подтверждения")]
    if facts.get("gross_area_m2"):
        fact_summary.append(f"{facts['gross_area_m2']} м²")
    if facts.get("region"):
        fact_summary.append(str(facts["region"]))
    if facts.get("locality"):
        fact_summary.append(str(facts["locality"]))
    return (
        f"Зафиксированы исходные данные: {', '.join(fact_summary)}"
        + ". Для правдивой сметы недостаточно проекта, ведомости объёмов, "
        "применимой расчётной и ценовой базы, документов индексов/предложений, "
        "а также налогового и договорного состава затрат. Денежный итог не рассчитан. "
        + ("PDF-чеклист сформирован и привязан к этой проверке." if pdf_ready else "PDF-чеклист пока не материализован.")
    )


def verified_deterministic_estimate_result(task: dict[str, Any]) -> bool:
    """Recompute an editable estimate, its assessment and content bindings."""

    if task.get("intent") != "estimate" or task.get("schema_version") != VERTICAL_TASK_SCHEMA:
        return False
    execution = task.get("execution") if isinstance(task.get("execution"), dict) else {}
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    if (
        execution.get("status") != "completed"
        or execution.get("provider_verified") is not True
        or result.get("type") != "deterministic_estimate"
    ):
        return False
    try:
        spec = EstimateSpec.model_validate(result.get("estimate"))
    except (TypeError, ValueError):
        return False
    calculation = result.get("calculation")
    assessment = result.get("verification")
    if not isinstance(calculation, dict) or not isinstance(assessment, dict):
        return False
    expected_assessment = assess_normative_estimate(spec)
    return bool(
        deterministic_estimate(spec) == calculation
        and assessment == expected_assessment
        and result.get("status") == expected_assessment["status"]
    )


def deterministic_estimate_result_verification(task: dict[str, Any]) -> dict[str, Any]:
    if not verified_deterministic_estimate_result(task):
        raise ValueError("deterministic estimate result verification failed")
    result = task["result"]
    calculation = result["calculation"]
    assessment = result["verification"]
    return {
        "status": "passed",
        "type": "deterministic_estimate_engine",
        "engine": calculation["engine"],
        "provider_verified": True,
        "estimate_status": result["status"],
        "normative_verified": assessment["normative_verified"],
        "commercial_verified": assessment["commercial_verified"],
        "source_coverage_complete": assessment["source_coverage_complete"],
        "calculation_sha256": calculation["calculation_sha256"],
        "assessment_binding_sha256": assessment["binding_sha256"],
    }


def deterministic_estimate_result_text(task: dict[str, Any]) -> str:
    if not verified_deterministic_estimate_result(task):
        raise ValueError("deterministic estimate result verification failed")
    result = task["result"]
    spec = result["estimate"]
    calculation = result["calculation"]
    assessment = result["verification"]
    minor_unit = int(calculation["minor_unit"])
    divisor = Decimal(10) ** minor_unit
    amount = Decimal(calculation["totals"]["grand_total_minor"]) / divisor
    formatted = f"{amount:,.{minor_unit}f}".replace(",", " ").replace(".", ",")
    delivery = task.get("artifact_delivery") if isinstance(task.get("artifact_delivery"), dict) else {}
    pdf_ready = "pdf" in set(delivery.get("delivered") or [])
    status_text = (
        "Проверенная смета"
        if result["status"] == "verified"
        else "Предварительная редактируемая смета"
    )
    truth_note = (
        "Источники и исходные документы прошли контроль."
        if result["status"] == "verified"
        else (
            "Источники указаны, но ещё не прошли независимую проверку; "
            "сумму нельзя выдавать за точную договорную стоимость."
            if assessment["source_coverage_complete"]
            else "В источниках есть пробелы; результат требует проверки и уточнения."
        )
    )
    return (
        f"{status_text} «{spec['title']}» подготовлена. "
        f"Детерминированный итог: {formatted} {spec['currency']}. "
        f"Позиции: {len(spec['lines'])}. {truth_note} "
        + ("Редактор и PDF готовы." if pdf_ready else "Редактор готов; PDF пока не материализован.")
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

    if isinstance(task, EstimateVerticalTask) and estimate_spec is None:
        readiness = _build_estimate_readiness_task(
            task,
            reason=estimate_error or "estimate_proposal_unavailable",
            provider_binding=provider_binding if provider_verified else None,
        )
        if readiness is not None:
            return readiness

    estimate_assessment = (
        assess_normative_estimate(estimate_spec)
        if isinstance(task, EstimateVerticalTask) and estimate_spec is not None
        else None
    )

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
                "status": estimate_assessment["status"] if estimate_assessment else "preliminary",
                "estimate": estimate_spec.model_dump(mode="json"),
                "calculation": calculation,
                "verification": estimate_assessment,
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
            **({"estimate_draft_schema_verified": True} if isinstance(task, EstimateVerticalTask) and task.spec is None and estimate_spec is not None else {}),
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
