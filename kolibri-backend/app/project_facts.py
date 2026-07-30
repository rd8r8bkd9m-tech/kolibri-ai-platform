"""Deterministic project facts extracted before estimate price research.

Provider output may enrich a project draft, but it must not override a region
that the user stated in the current request.  A previously persisted project
fact is used only when the current request does not name another region.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal, Mapping


ProjectFactSource = Literal["user_request", "project_fact", "provider_draft", "missing"]


@dataclass(frozen=True, slots=True)
class ProjectRegionFact:
    region: str
    source: ProjectFactSource


_LOCATION_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bказан(?:ь|и|ью|е)\b", re.IGNORECASE),
        "Казань, Республика Татарстан",
    ),
    (
        re.compile(r"\bлениногорск\w*\b(?:(?![.!?\n]).){0,80}\bтатарстан\w*\b", re.IGNORECASE),
        "Лениногорск, Татарстан",
    ),
    (
        re.compile(r"\bтатарстан\w*\b(?:(?![.!?\n]).){0,80}\bлениногорск\w*\b", re.IGNORECASE),
        "Лениногорск, Татарстан",
    ),
    (re.compile(r"\bсамарск\w*\s+област\w*\b", re.IGNORECASE), "Самарская область"),
    (re.compile(r"\bсамар(?:а|е|у|ой|ы)\b", re.IGNORECASE), "Самарская область"),
    (re.compile(r"\bмоскв(?:а|е|у|ой|ы)\b", re.IGNORECASE), "Москва"),
    (re.compile(r"\bлениногорск\w*\b", re.IGNORECASE), "Лениногорск"),
    (re.compile(r"\b(?:республик\w*\s+)?татарстан\w*\b", re.IGNORECASE), "Татарстан"),
)

_ADMIN_REGION_RE = re.compile(
    r"\b(?P<region>"
    r"(?:республик(?:а|е|и|у|ой)\s+[а-яё-]+(?:\s+[а-яё-]+){0,2})"
    r"|(?:[а-яё-]+(?:\s+[а-яё-]+){0,1}\s+област(?:ь|и|ью))"
    r"|(?:[а-яё-]+\s+кра(?:й|е|я|ем))"
    r"|(?:[а-яё-]+(?:\s+[а-яё-]+){0,2}\s+автономн\w*\s+округ\w*)"
    r")\b",
    re.IGNORECASE,
)


def resolve_project_region(
    prompt: str,
    *,
    project_fact: Mapping[str, Any] | None = None,
    candidate_region: Any = "",
) -> ProjectRegionFact:
    """Resolve the region used by collectors and evidence verification.

    Precedence is deliberate: a region in the current request wins over an
    older project fact and over untrusted provider output.  This prevents a
    stale Татарстан draft from routing a new Москва request to the wrong price
    zone.  Provider output remains a final fallback for legacy callers that
    already materialized a structured project fact before entering this API.
    """

    requested = extract_request_region(prompt)
    if requested:
        return ProjectRegionFact(requested, "user_request")

    persisted = _clean_region(project_fact.get("region")) if isinstance(project_fact, Mapping) else ""
    if persisted:
        return ProjectRegionFact(persisted, "project_fact")

    candidate = _clean_region(candidate_region)
    if candidate:
        return ProjectRegionFact(candidate, "provider_draft")

    return ProjectRegionFact("", "missing")


def extract_request_region(prompt: str) -> str:
    """Extract an explicitly named Russian region without a default region.

    Common city inflections are normalized where the mapping is unambiguous.
    Other explicitly written federal subjects are preserved verbatim; a
    provider or persisted ProjectFact can supply a richer municipality value
    only when the request itself did not name a region.
    """

    text = " ".join(str(prompt or "").split()).strip()
    if not text:
        return ""
    for pattern, canonical in _LOCATION_RULES:
        if pattern.search(text):
            return canonical
    match = _ADMIN_REGION_RE.search(text)
    return _clean_region(match.group("region")) if match else ""


def _clean_region(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()[:240]
