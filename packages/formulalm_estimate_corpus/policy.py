"""Declared rights, privacy, and source gates for local candidate records.

Passing these gates validates the record's structured declarations.  It does
not constitute independent legal review or authorize model training.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from urllib.parse import urlparse


ALLOWED_ACCESS_CLASSES = frozenset(
    {"open_data", "public_official", "user_provided"}
)
ALLOWED_RIGHTS_BASES = frozenset(
    {"open_license", "public_official_record", "user_consent"}
)
REQUIRED_ALLOWED_USES = frozenset(
    {"formula_lm_estimate_training", "formula_lm_estimate_evaluation"}
)
FORBIDDEN_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "authorization",
        "chain_of_thought",
        "cookie",
        "cookies",
        "credential",
        "credentials",
        "email",
        "full_name",
        "password",
        "passport_number",
        "personal_email",
        "phone",
        "phone_number",
        "private_key",
        "prompt",
        "reasoning",
        "refresh_token",
        "secret",
        "secrets",
        "session_token",
        "snils",
        "system_prompt",
        "token",
    }
)
SECRET_VALUE_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*\b", re.IGNORECASE),
)
PII_VALUE_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"(?<!\d)(?:\+7|8)[\s()-]*\d{3}[\s()-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)"),
    re.compile(r"(?<!\d)\d{3}-\d{3}-\d{3}[ -]\d{2}(?!\d)"),
    re.compile(r"(?<!\d)\d{4}\s+\d{6}(?!\d)"),
)


class CorpusPolicyError(ValueError):
    """Raised when an input record is not eligible for corpus ingestion."""


def _is_https(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _walk_sensitive(value: object, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized_key = str(key).strip().lower().replace("-", "_")
            child_path = f"{path}.{key}"
            if normalized_key in FORBIDDEN_KEYS:
                errors.append(f"forbidden field {child_path}")
            errors.extend(_walk_sensitive(nested, child_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, nested in enumerate(value):
            errors.extend(_walk_sensitive(nested, f"{path}[{index}]"))
    elif isinstance(value, str):
        for pattern in SECRET_VALUE_PATTERNS:
            if pattern.search(value):
                errors.append(f"secret-like value at {path}")
                break
        for pattern in PII_VALUE_PATTERNS:
            if pattern.search(value):
                errors.append(f"PII-like value at {path}")
                break
    return errors


def validate_policy(record: Mapping[str, object]) -> None:
    """Reject records without explicit rights, provenance, and privacy gates."""

    errors = _walk_sensitive(record)
    source = record.get("source")
    rights = record.get("rights")
    privacy = record.get("privacy")

    if not isinstance(source, Mapping):
        errors.append("source must be an object")
        source = {}
    if not isinstance(rights, Mapping):
        errors.append("rights must be an object")
        rights = {}
    if not isinstance(privacy, Mapping):
        errors.append("privacy must be an object")
        privacy = {}

    access_class = source.get("access_class")
    basis = rights.get("basis")
    if access_class not in ALLOWED_ACCESS_CLASSES:
        errors.append(
            "source.access_class must be open_data, public_official, or user_provided"
        )
    if basis not in ALLOWED_RIGHTS_BASES:
        errors.append(
            "rights.basis must be open_license, public_official_record, or user_consent"
        )
    if rights.get("training_allowed") is not True:
        errors.append("rights.training_allowed must be explicitly true")

    allowed_uses = rights.get("allowed_uses")
    if not isinstance(allowed_uses, list):
        errors.append("rights.allowed_uses must be a list")
    elif not REQUIRED_ALLOWED_USES.issubset(set(allowed_uses)):
        errors.append("rights.allowed_uses is missing FormulaLM training/evaluation grants")

    if privacy.get("contains_pii") is not False:
        errors.append("privacy.contains_pii must be explicitly false")
    if privacy.get("contains_secrets") is not False:
        errors.append("privacy.contains_secrets must be explicitly false")
    if privacy.get("private_reasoning_included") is not False:
        errors.append("privacy.private_reasoning_included must be explicitly false")

    source_uri = source.get("source_uri")
    if access_class in {"open_data", "public_official"} and not _is_https(source_uri):
        errors.append("public/open source.source_uri must be an HTTPS URL")
    if access_class == "user_provided" and not (
        isinstance(source_uri, str) and source_uri.startswith("user-consent://")
    ):
        errors.append("user-provided source_uri must use user-consent://")

    if basis == "open_license":
        if access_class != "open_data":
            errors.append("open_license requires source.access_class=open_data")
        if not rights.get("license_id"):
            errors.append("open_license requires rights.license_id")
        if not _is_https(rights.get("license_url")):
            errors.append("open_license requires an HTTPS rights.license_url")
    elif basis == "public_official_record":
        if access_class != "public_official":
            errors.append(
                "public_official_record requires source.access_class=public_official"
            )
        if not rights.get("rights_review_id"):
            errors.append("public official data requires rights.rights_review_id")
        if not _is_https(rights.get("terms_url")):
            errors.append("public official data requires an HTTPS rights.terms_url")
    elif basis == "user_consent":
        if access_class != "user_provided":
            errors.append("user_consent requires source.access_class=user_provided")
        if not rights.get("consent_id") or not rights.get("consented_at"):
            errors.append("user_consent requires consent_id and consented_at")

    if errors:
        raise CorpusPolicyError("; ".join(sorted(set(errors))))
