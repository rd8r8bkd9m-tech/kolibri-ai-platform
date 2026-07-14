"""Deterministic normalization and learning-view projection."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .policy import CorpusPolicyError, validate_policy


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
MONEY_QUANT = Decimal("0.01")


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_value(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def normalize_text(value: object, *, field: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise CorpusPolicyError(f"{field} must be a string")
    normalized = " ".join(unicodedata.normalize("NFKC", value).split())
    if not normalized and not allow_empty:
        raise CorpusPolicyError(f"{field} must not be empty")
    return normalized


def normalize_id(value: object, *, field: str) -> str:
    normalized = normalize_text(value, field=field)
    if not IDENTIFIER_RE.fullmatch(normalized):
        raise CorpusPolicyError(f"{field} has an invalid identifier format")
    return normalized


def normalize_decimal(
    value: object,
    *,
    field: str,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
) -> str:
    if isinstance(value, bool) or value is None:
        raise CorpusPolicyError(f"{field} must be a decimal string or number")
    raw = str(value).strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        parsed = Decimal(raw)
    except InvalidOperation as exc:
        raise CorpusPolicyError(f"{field} is not a valid decimal") from exc
    if not parsed.is_finite():
        raise CorpusPolicyError(f"{field} must be finite")
    if minimum is not None and parsed < minimum:
        raise CorpusPolicyError(f"{field} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        raise CorpusPolicyError(f"{field} must be <= {maximum}")
    rendered = format(parsed.normalize(), "f")
    return "0" if rendered in {"-0", ""} else rendered


def _require_sha256(value: object, *, field: str) -> str:
    normalized = normalize_text(value, field=field).lower()
    if not SHA256_RE.fullmatch(normalized):
        raise CorpusPolicyError(f"{field} must be a lowercase SHA-256 hex digest")
    return normalized


def _normalize_string_list(value: object, *, field: str) -> list[str]:
    if not isinstance(value, list):
        raise CorpusPolicyError(f"{field} must be a list")
    normalized = [normalize_text(item, field=f"{field}[]") for item in value]
    return sorted(set(normalized))


def _normalize_timestamp(value: object, *, field: str) -> str:
    normalized = normalize_text(value, field=field)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CorpusPolicyError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise CorpusPolicyError(f"{field} must include a timezone")
    return normalized


def _normalize_date(value: object, *, field: str) -> str:
    normalized = normalize_text(value, field=field)
    try:
        date.fromisoformat(normalized)
    except ValueError as exc:
        raise CorpusPolicyError(f"{field} must be an ISO-8601 date") from exc
    return normalized


def _normalize_line(raw: object, index: int) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise CorpusPolicyError(f"estimate.lines[{index}] must be an object")
    field = f"estimate.lines[{index}]"
    quantity = normalize_decimal(raw.get("quantity"), field=f"{field}.quantity", minimum=Decimal("0"))
    unit_price = normalize_decimal(raw.get("unit_price"), field=f"{field}.unit_price", minimum=Decimal("0"))
    line_total = normalize_decimal(raw.get("line_total"), field=f"{field}.line_total", minimum=Decimal("0"))
    calculated = (Decimal(quantity) * Decimal(unit_price)).quantize(
        MONEY_QUANT, rounding=ROUND_HALF_UP
    )
    supplied = Decimal(line_total).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    if supplied != calculated:
        raise CorpusPolicyError(
            f"{field}.line_total fails Decimal boundary: expected {calculated}, got {supplied}"
        )
    code_value = raw.get("code")
    code = (
        normalize_text(code_value, field=f"{field}.code")
        if code_value not in (None, "")
        else None
    )
    evidence_ids = _normalize_string_list(
        raw.get("evidence_ids"), field=f"{field}.evidence_ids"
    )
    if not evidence_ids:
        raise CorpusPolicyError(f"{field}.evidence_ids must not be empty")
    return {
        "line_id": normalize_id(raw.get("line_id"), field=f"{field}.line_id"),
        "section": normalize_text(raw.get("section"), field=f"{field}.section"),
        "code": code,
        "name": normalize_text(raw.get("name"), field=f"{field}.name"),
        "unit": normalize_text(raw.get("unit"), field=f"{field}.unit"),
        "quantity": quantity,
        "unit_price": unit_price,
        "line_total": format(supplied, "f"),
        "currency": "RUB",
        "evidence_ids": evidence_ids,
    }


def normalize_record(raw: object) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise CorpusPolicyError("record must be a JSON object")
    validate_policy(raw)

    source = raw.get("source")
    rights = raw.get("rights")
    privacy = raw.get("privacy")
    provenance = raw.get("provenance")
    geography = raw.get("geography")
    period = raw.get("period")
    estimate = raw.get("estimate")
    quality = raw.get("quality")
    for field_name, value in (
        ("source", source),
        ("rights", rights),
        ("privacy", privacy),
        ("provenance", provenance),
        ("geography", geography),
        ("period", period),
        ("estimate", estimate),
        ("quality", quality),
    ):
        if not isinstance(value, Mapping):
            raise CorpusPolicyError(f"{field_name} must be an object")

    lines_raw = estimate.get("lines")
    if not isinstance(lines_raw, list) or not lines_raw:
        raise CorpusPolicyError("estimate.lines must be a non-empty list")
    lines = [_normalize_line(line, index) for index, line in enumerate(lines_raw)]
    line_ids = [line["line_id"] for line in lines]
    if len(line_ids) != len(set(line_ids)):
        raise CorpusPolicyError("estimate.lines contains duplicate line_id values")

    status = normalize_text(estimate.get("status"), field="estimate.status")
    if status not in {"preliminary", "source_backed", "verified"}:
        raise CorpusPolicyError("estimate.status is invalid")
    year_raw = period.get("year")
    quarter_raw = period.get("quarter")
    if not isinstance(year_raw, int) or isinstance(year_raw, bool) or year_raw < 2000:
        raise CorpusPolicyError("period.year must be an integer >= 2000")
    if quarter_raw not in {1, 2, 3, 4}:
        raise CorpusPolicyError("period.quarter must be 1..4")

    normalized_rights: dict[str, object] = {
        "basis": rights.get("basis"),
        "training_allowed": True,
        "allowed_uses": _normalize_string_list(
            rights.get("allowed_uses"), field="rights.allowed_uses"
        ),
        "verified_at": _normalize_timestamp(
            rights.get("verified_at"), field="rights.verified_at"
        ),
    }
    for key in (
        "license_id",
        "license_url",
        "rights_review_id",
        "terms_url",
        "consent_id",
        "consented_at",
    ):
        if rights.get(key) not in (None, ""):
            normalizer = _normalize_timestamp if key == "consented_at" else normalize_text
            normalized_rights[key] = normalizer(rights.get(key), field=f"rights.{key}")

    normalized: dict[str, object] = {
        "schema_version": "1.0.0",
        "record_id": normalize_id(raw.get("record_id"), field="record_id"),
        "project_id": normalize_id(raw.get("project_id"), field="project_id"),
        "source_group_id": normalize_id(
            raw.get("source_group_id"), field="source_group_id"
        ),
        "document_id": normalize_id(raw.get("document_id"), field="document_id"),
        "locale": "ru-RU",
        "source": {
            "source_id": normalize_id(source.get("source_id"), field="source.source_id"),
            "source_type": normalize_text(
                source.get("source_type"), field="source.source_type"
            ),
            "owner": normalize_text(source.get("owner"), field="source.owner"),
            "source_uri": normalize_text(
                source.get("source_uri"), field="source.source_uri"
            ),
            "access_class": source.get("access_class"),
            "retrieved_at": _normalize_timestamp(
                source.get("retrieved_at"), field="source.retrieved_at"
            ),
            "snapshot_sha256": _require_sha256(
                source.get("snapshot_sha256"), field="source.snapshot_sha256"
            ),
        },
        "rights": normalized_rights,
        "privacy": {
            "contains_pii": False,
            "contains_secrets": False,
            "private_reasoning_included": False,
        },
        "provenance": {
            "document_sha256": _require_sha256(
                provenance.get("document_sha256"),
                field="provenance.document_sha256",
            ),
            "extractor_name": normalize_text(
                provenance.get("extractor_name"), field="provenance.extractor_name"
            ),
            "extractor_version": normalize_text(
                provenance.get("extractor_version"),
                field="provenance.extractor_version",
            ),
            "extracted_at": _normalize_timestamp(
                provenance.get("extracted_at"), field="provenance.extracted_at"
            ),
            "lineage_sha256": sorted(
                {
                    _require_sha256(value, field="provenance.lineage_sha256[]")
                    for value in provenance.get("lineage_sha256", [])
                }
            ),
        },
        "geography": {
            "country_code": "RU",
            "region_code": normalize_text(
                geography.get("region_code"), field="geography.region_code"
            ),
            "region_name": normalize_text(
                geography.get("region_name"), field="geography.region_name"
            ),
            "municipality": normalize_text(
                geography.get("municipality", ""),
                field="geography.municipality",
                allow_empty=True,
            ),
        },
        "period": {
            "year": year_raw,
            "quarter": quarter_raw,
            "price_basis_date": _normalize_date(
                period.get("price_basis_date"), field="period.price_basis_date"
            ),
        },
        "estimate": {
            "title": normalize_text(estimate.get("title"), field="estimate.title"),
            "object_type": normalize_text(
                estimate.get("object_type"), field="estimate.object_type"
            ),
            "status": status,
            "scope_summary": normalize_text(
                estimate.get("scope_summary"), field="estimate.scope_summary"
            ),
            "assumptions": _normalize_string_list(
                estimate.get("assumptions", []), field="estimate.assumptions"
            ),
            "lines": lines,
        },
        "quality": {
            "human_reviewed": quality.get("human_reviewed") is True,
            "verifier_status": normalize_text(
                quality.get("verifier_status"), field="quality.verifier_status"
            ),
            "source_coverage": normalize_decimal(
                quality.get("source_coverage"),
                field="quality.source_coverage",
                minimum=Decimal("0"),
                maximum=Decimal("1"),
            ),
        },
    }
    if normalized["quality"]["verifier_status"] not in {"pass", "partial"}:
        raise CorpusPolicyError("quality.verifier_status must be pass or partial")

    normalized["rights_hash"] = sha256_value(normalized["rights"])
    normalized["provenance_hash"] = sha256_value(normalized["provenance"])
    semantic_payload = {
        "geography": normalized["geography"],
        "period": normalized["period"],
        "estimate": normalized["estimate"],
    }
    normalized["dedup_sha256"] = sha256_value(semantic_payload)
    normalized["record_sha256"] = sha256_value(normalized)
    return normalized


def learning_view(record: Mapping[str, object]) -> dict[str, object]:
    """Create the only trainer-facing projection.

    Quantities, unit prices, totals, tax, and computed summary amounts are
    intentionally absent.  They remain deterministic Decimal-engine inputs and
    evaluation references, never learning targets.
    """

    estimate = record["estimate"]
    lines = estimate["lines"]
    return {
        "schema_version": "1.0.0",
        "record_id": record["record_id"],
        "project_id": record["project_id"],
        "source_group_id": record["source_group_id"],
        "record_sha256": record["record_sha256"],
        "rights_hash": record["rights_hash"],
        "provenance_hash": record["provenance_hash"],
        "task": "russian_construction_estimate_structure",
        "context": {
            "locale": record["locale"],
            "geography": record["geography"],
            "period": record["period"],
            "object_type": estimate["object_type"],
            "status": estimate["status"],
            "scope_summary": estimate["scope_summary"],
            "assumptions": estimate["assumptions"],
        },
        "target_structure": [
            {
                "section": line["section"],
                "code": line["code"],
                "name": line["name"],
                "unit": line["unit"],
                "evidence_required": True,
            }
            for line in lines
        ],
        "calculator_boundary": {
            "engine": "deterministic_decimal",
            "excluded_fields": [
                "quantity",
                "unit_price",
                "line_total",
                "subtotal",
                "tax",
                "grand_total",
            ],
        },
    }


def decimal_eval_rows(record: Mapping[str, object]) -> list[dict[str, object]]:
    return [
        {
            "record_id": record["record_id"],
            "record_sha256": record["record_sha256"],
            "line_id": line["line_id"],
            "quantity": line["quantity"],
            "unit_price": line["unit_price"],
            "expected_line_total": line["line_total"],
            "rounding": "ROUND_HALF_UP:0.01",
            "training_eligible": False,
        }
        for line in record["estimate"]["lines"]
    ]
