"""Strict, fail-closed price evidence for construction estimates.

Language-model output is never evidence.  Callers may pass records to this
module only after a web/document collector has fetched the source bytes and a
verifier has bound those bytes to a position code.  This module validates the
public evidence contract, rejects mismatches and decides the strongest pricing
status that can be shown to a user.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import os
import re
from typing import Any, Literal, Mapping
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


DECIMAL_PATTERN = r"^\d+(?:\.\d+)?$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
ATTESTATION_PATTERN = r"^[0-9a-f]{64}$"
MAX_PRICE_AGE = timedelta(days=120)
DEV_SECRET = "kolibri-dev-secret-change-in-production"
SOURCE_TYPES = Literal[
    "official_index",
    "official_catalog",
    "government_procurement",
    "supplier_quote",
    "supplier_catalog",
    "marketplace",
    "user_document",
]
VAT_STATUSES = Literal["included", "excluded", "not_applicable", "unknown"]
VERIFICATION_STATUSES = Literal["source_backed", "verified"]


class PriceEvidenceRecord(BaseModel):
    """Immutable evidence attached by the trusted price-research boundary."""

    model_config = ConfigDict(extra="forbid")

    position_code: str = Field(min_length=1, max_length=80)
    source_id: str = Field(min_length=1, max_length=160)
    url: str = Field(min_length=1, max_length=2_000)
    source_title: str = Field(min_length=1, max_length=500)
    source_type: SOURCE_TYPES
    region: str = Field(min_length=1, max_length=240)
    project_region: str | None = Field(default=None, min_length=1, max_length=240)
    observed_at: str = Field(min_length=1, max_length=64)
    price_date: str = Field(min_length=10, max_length=10)
    unit: str = Field(min_length=1, max_length=40)
    vat_status: VAT_STATUSES
    quote: str = Field(min_length=1, max_length=500)
    unit_price: str = Field(min_length=1, max_length=64, pattern=DECIMAL_PATTERN)
    currency: Literal["RUB"] = "RUB"
    content_sha256: str = Field(pattern=SHA256_PATTERN)
    verification: VERIFICATION_STATUSES
    attestation: str | None = Field(default=None, pattern=ATTESTATION_PATTERN)

    @field_validator(
        "position_code",
        "source_id",
        "source_title",
        "region",
        "unit",
        "quote",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split()).strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("url")
    @classmethod
    def validate_public_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("evidence URL must be an absolute HTTP(S) URL without credentials or fragment")
        return value

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("observed_at must be ISO-8601") from exc
        if parsed.tzinfo is None:
            raise ValueError("observed_at must include a timezone")
        if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("observed_at must not be in the future")
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @field_validator("price_date")
    @classmethod
    def validate_price_date(cls, value: str) -> str:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("price_date must be ISO-8601 date") from exc
        if parsed > datetime.now(timezone.utc).date():
            raise ValueError("price_date must not be in the future")
        return parsed.isoformat()

    @field_validator("unit_price")
    @classmethod
    def validate_unit_price(cls, value: str) -> str:
        parsed = _decimal(value)
        if parsed <= 0:
            raise ValueError("unit_price must be positive")
        return _decimal_text(parsed)

    @model_validator(mode="after")
    def verified_record_requires_known_vat(self):
        if self.verification == "verified" and self.vat_status == "unknown":
            raise ValueError("verified evidence requires a known VAT basis")
        return self


def attest_price_evidence(value: Mapping[str, Any] | PriceEvidenceRecord) -> dict[str, Any]:
    """Return a server-attested evidence record safe to cross public CRUD.

    Evidence is carried through the browser before it is persisted.  A syntax-
    valid URL/hash supplied by that browser is not proof that the collector
    fetched anything, so the trusted collector signs the normalized record.
    Public clients can replay a valid price record, but cannot mint or alter it.
    """

    record = (
        value
        if isinstance(value, PriceEvidenceRecord)
        else PriceEvidenceRecord.model_validate(value)
    )
    payload = record.model_dump(mode="json", exclude={"attestation"})
    payload["attestation"] = hmac.new(
        _evidence_signing_key(),
        _canonical_evidence(payload),
        hashlib.sha256,
    ).hexdigest()
    return PriceEvidenceRecord.model_validate(payload).model_dump(mode="json")


def evidence_attestation_is_valid(record: PriceEvidenceRecord) -> bool:
    """Verify that a record was emitted by a trusted server-side collector."""

    if not record.attestation:
        return False
    payload = record.model_dump(mode="json", exclude={"attestation"})
    expected = hmac.new(
        _evidence_signing_key(),
        _canonical_evidence(payload),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(record.attestation, expected)


def evaluate_price_evidence(
    sections: list[dict[str, Any]],
    *,
    region: str,
    currency: str,
    trusted_records: Any,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Attach trusted records and derive pricing status.

    Invalid, stale, unbound or mismatching records never contribute to status.
    The returned issues are deliberately bounded and contain no fetched source
    bytes or provider payloads.
    """

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    records, issues = _parse_records(trusted_records)
    positions: dict[str, dict[str, Any]] = {}
    ordered_positions: list[dict[str, Any]] = []
    for section in sections:
        for position in section.get("positions", []):
            code = str(position.get("code") or "").strip()
            position["price_evidence"] = []
            position["source"] = ""
            ordered_positions.append(position)
            if code and code not in positions:
                positions[code] = position

    accepted: list[dict[str, Any]] = []
    seen_sources: set[tuple[str, str]] = set()
    for record in records:
        if not evidence_attestation_is_valid(record):
            issues.append(_issue("untrusted_evidence", record.position_code))
            continue
        position = positions.get(record.position_code)
        if position is None:
            issues.append(_issue("unbound_position", record.position_code))
            continue
        if _normalise_unit(record.unit) != _normalise_unit(position.get("unit")):
            issues.append(_issue("unit_mismatch", record.position_code))
            continue
        if record.currency != currency:
            issues.append(_issue("currency_mismatch", record.position_code))
            continue
        if record.project_region and _canonical_region(record.project_region) != _canonical_region(region):
            issues.append(_issue("project_region_mismatch", record.position_code))
            continue
        if not _regions_compatible(region, record.region):
            issues.append(_issue("region_mismatch", record.position_code))
            continue
        if _decimal(record.unit_price) != _decimal(position.get("price")):
            issues.append(_issue("price_mismatch", record.position_code))
            continue
        price_date = date.fromisoformat(record.price_date)
        if current.date() - price_date > MAX_PRICE_AGE:
            issues.append(_issue("stale_price", record.position_code))
            continue
        identity = (record.position_code, record.source_id)
        if identity in seen_sources:
            issues.append(_issue("duplicate_source", record.position_code))
            continue
        seen_sources.add(identity)
        public_record = record.model_dump(mode="json")
        position["price_evidence"].append(public_record)
        if not position["source"]:
            position["source"] = record.url
        accepted.append(public_record)

    priced_positions = [
        position
        for position in ordered_positions
        if _decimal(position.get("quantity")) > 0 and _decimal(position.get("price")) > 0
    ]
    incomplete_positions = [
        position
        for position in ordered_positions
        if _decimal(position.get("quantity")) <= 0 or _decimal(position.get("price")) <= 0
    ]
    needs_input = not ordered_positions or bool(incomplete_positions)
    if needs_input:
        pricing_status = "needs_input"
    elif not priced_positions or not all(position["price_evidence"] for position in priced_positions):
        pricing_status = "preliminary"
    elif all(
        any(record["verification"] == "verified" for record in position["price_evidence"])
        for position in priced_positions
    ):
        pricing_status = "verified"
    else:
        pricing_status = "source_backed"

    return {
        "pricing_status": pricing_status,
        "price_sources": accepted,
        "evidence_issues": issues[:200],
        "needs_input": needs_input,
    }


def _parse_records(value: Any) -> tuple[list[PriceEvidenceRecord], list[dict[str, str]]]:
    if value is None:
        return [], []
    if not isinstance(value, list):
        return [], [_issue("invalid_evidence_collection", "")]
    records: list[PriceEvidenceRecord] = []
    issues: list[dict[str, str]] = []
    for raw in value[:5_000]:
        try:
            records.append(PriceEvidenceRecord.model_validate(raw))
        except ValidationError:
            position_code = str(raw.get("position_code") or "")[:80] if isinstance(raw, Mapping) else ""
            issues.append(_issue("invalid_evidence", position_code))
    if len(value) > 5_000:
        issues.append(_issue("evidence_limit_exceeded", ""))
    return records, issues


def _issue(code: str, position_code: str) -> dict[str, str]:
    return {
        "code": code,
        "position_code": position_code,
        "message": "Источник цены отклонён строгой проверкой." if position_code else "Набор источников цен отклонён строгой проверкой.",
    }


def _canonical_evidence(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _evidence_signing_key() -> bytes:
    configured = (
        os.getenv("KOLIBRI_EVIDENCE_SIGNING_KEY")
        or os.getenv("KOLIBRI_SESSION_SECRET")
        or os.getenv("JWT_SECRET_KEY")
    )
    release_id = os.getenv("KOLIBRI_RELEASE_ID", "unversioned").strip()
    if configured:
        key = configured.encode("utf-8")
        if len(key) < 32:
            raise RuntimeError("estimate_evidence_signing_key_too_short")
        if configured == DEV_SECRET and release_id not in {"", "unversioned"}:
            raise RuntimeError("estimate_evidence_signing_key_not_configured")
        return key
    # Keep local development deterministic while production inherits the same
    # mandatory secret already used for signed browser sessions/JWTs.
    from app.auth import SECRET_KEY

    if release_id not in {"", "unversioned"} or SECRET_KEY == DEV_SECRET:
        # A versioned release must never mint evidence with the public local-
        # development fallback.  Local unversioned tests configure no release
        # identity and remain deterministic below.
        if release_id not in {"", "unversioned"}:
            raise RuntimeError("estimate_evidence_signing_key_not_configured")
    return SECRET_KEY.encode("utf-8")


def _regions_compatible(estimate_region: str, evidence_region: str) -> bool:
    left = _region_tokens(estimate_region)
    right = _region_tokens(evidence_region)
    return bool(left and right and (left <= right or right <= left or bool(left & right)))


def _canonical_region(value: str) -> str:
    return " ".join(str(value).split()).strip().casefold()


def _region_tokens(value: str) -> set[str]:
    stop = {"республика", "область", "край", "город", "г", "рф", "россия"}
    return {
        token
        for token in re.findall(r"[a-zа-яё0-9]+", str(value).casefold())
        if len(token) > 1 and token not in stop
    }


def _normalise_unit(value: Any) -> str:
    unit = " ".join(str(value or "").split()).strip().casefold()
    aliases = {
        "м2": "м²",
        "м^2": "м²",
        "кв.м": "м²",
        "м3": "м³",
        "м^3": "м³",
        "куб.м": "м³",
        "комплект": "компл",
    }
    return aliases.get(unit, unit)


def _decimal(value: Any) -> Decimal:
    raw = str(value if value is not None else "").strip().replace(" ", "").replace(",", ".")
    try:
        parsed = Decimal(raw)
        return parsed if parsed.is_finite() else Decimal("0")
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f") if normalized != normalized.to_integral() else str(normalized.quantize(Decimal("1")))
