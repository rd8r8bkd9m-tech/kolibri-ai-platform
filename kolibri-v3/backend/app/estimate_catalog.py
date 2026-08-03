"""Authority-first catalog, candidate, consent and market-price primitives.

The existing estimate artifact and pricing-source modules remain the owners of
saved estimate versions and source snapshots.  This module adds the missing
reviewable knowledge loop around them.  AI/user input is stored as a private
candidate or observation first; only an explicit reviewer decision and a
valid consent/evidence policy can make data reusable or aggregate-eligible.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Literal, Mapping

import sqlite3
from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .market_pricing import market_item_key, normalized_market_text, percentile
from .schemas import UserRole, UserSession


CATALOG_KINDS = ("work", "material", "equipment", "service")
VISIBILITIES = (
    "project_private",
    "tenant_private",
    "system_curated",
    "market_aggregate",
)
CATALOG_SOURCE_TYPES = (
    "ai_generated",
    "user_manual",
    "estimate_import",
    "supplier_import",
)
OBSERVATION_SOURCES = (
    "ai_preliminary",
    "user_edit",
    "official_reference",
    "supplier_offer",
    "customer_approved",
    "contract_price",
    "paid_invoice",
    "completed_work",
)
POLICY_VERSION = "market-aggregate/1.0.0"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{0,159}$")
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_DECIMAL = re.compile(r"^(?:0|[1-9]\d{0,11})(?:\.\d{1,6})?$")
_MONEY = re.compile(r"^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$")


class CatalogModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


def _bounded_json(value: Mapping[str, Any] | list[Any], *, limit: int = 8_000) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > limit:
        raise ValueError("structured catalog data is too large")
    return encoded


def _json_object(raw: object, default: object) -> object:
    if not isinstance(raw, str):
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_unit(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    # NFKC turns superscript digits into plain digits, including the common
    # Cyrillic spelling "м3"/"м2". Restore the canonical display units after
    # that normalization so catalog and observation lookups share one key.
    normalized = normalized.replace("м2", "м²").replace("м3", "м³")
    normalized = normalized.replace("м^2", "м²").replace("м^3", "м³")
    normalized = normalized.replace("m²", "м²").replace("m³", "м³")
    normalized = normalized.replace("m2", "м²").replace("m3", "м³")
    normalized = normalized.replace("кв.м", "м²").replace("кв м", "м²")
    normalized = normalized.replace("п.м.", "м.п.").replace("пог.м", "м.п.")
    return normalized


def normalize_catalog_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    normalized = normalized.replace("м²", "м2").replace("м³", "м3")
    normalized = normalized.replace("кв. м", "м2").replace("кв м", "м2")
    normalized = re.sub(r"[^0-9a-zа-яё]+", " ", normalized)
    return " ".join(normalized.split())


def _aliases(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:32]:
        if isinstance(item, str) and item.strip():
            text = item.strip()[:160]
            if text not in result:
                result.append(text)
    return result


class CatalogCandidateCreate(CatalogModel):
    original_text: str = Field(min_length=1, max_length=2_000, alias="originalText")
    proposed_canonical_name: str = Field(min_length=1, max_length=300, alias="proposedCanonicalName")
    proposed_short_name: str | None = Field(default=None, max_length=160, alias="proposedShortName")
    kind: Literal["work", "material", "equipment", "service"]
    proposed_unit: str = Field(min_length=1, max_length=32, alias="proposedUnit")
    specification: dict[str, Any] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list, max_length=32)
    category_id: str = Field(default="", max_length=120, alias="categoryId")
    confidence: str = Field(default="0", pattern=r"^(?:0|1|0\.[0-9]{1,6}|1\.0{1,6})$")
    source_type: Literal["ai_generated", "user_manual", "estimate_import", "supplier_import"] = Field(alias="sourceType")
    source_estimate_id: str | None = Field(default=None, alias="sourceEstimateId", max_length=160)
    source_estimate_version: int | None = Field(default=None, ge=1, alias="sourceEstimateVersion")
    source_row_id: str | None = Field(default=None, max_length=120, alias="sourceRowId")

    @field_validator("proposed_unit")
    @classmethod
    def normalize_unit(cls, value: str) -> str:
        return _normalize_unit(value)


class CatalogCandidateReview(CatalogModel):
    action: Literal["approve", "merge", "reject"]
    visibility: Literal["project_private", "tenant_private"] = "project_private"
    merge_target_id: str | None = Field(default=None, alias="mergeTargetId")
    review_note: str | None = Field(default=None, max_length=1_000, alias="reviewNote")


class PriceObservationCreate(CatalogModel):
    row_id: str = Field(min_length=1, max_length=120, alias="rowId")
    description: str = Field(min_length=1, max_length=300)
    kind: Literal["work", "material", "equipment", "service"]
    unit: str = Field(min_length=1, max_length=32)
    observed_unit_price: str = Field(alias="observedUnitPrice", pattern=_MONEY.pattern)
    specification: dict[str, Any] = Field(default_factory=dict)
    country: str = Field(default="RU", min_length=2, max_length=3)
    region: str = Field(min_length=1, max_length=160)
    municipality: str | None = Field(default=None, max_length=160)
    timezone: str | None = Field(default=None, max_length=80)
    quantity_band: str = Field(default="unspecified", max_length=80, alias="quantityBand")
    quantity_min: str | None = Field(default=None, pattern=_DECIMAL.pattern, alias="quantityMin")
    quantity_max: str | None = Field(default=None, pattern=_DECIMAL.pattern, alias="quantityMax")
    tax_treatment: Literal["included", "excluded", "unknown", "not_applicable"] = Field(default="unknown", alias="taxTreatment")
    delivery_treatment: Literal["included", "excluded", "unknown"] = Field(default="unknown", alias="deliveryTreatment")
    source_type: Literal[
        "ai_preliminary", "user_edit", "official_reference", "supplier_offer",
        "customer_approved", "contract_price", "paid_invoice", "completed_work"
    ] = Field(alias="sourceType")
    lifecycle: Literal["draft", "shared", "approved", "contracted"] = "draft"
    evidence_reference_hash: str | None = Field(default=None, alias="evidenceReferenceHash")
    valid_until: str | None = Field(default=None, alias="validUntil", max_length=64)
    confidence: str = Field(default="0", pattern=r"^(?:0|1|0\.[0-9]{1,6}|1\.0{1,6})$")
    consent_id: str | None = Field(default=None, alias="consentId", max_length=160)
    catalog_entry_id: str | None = Field(default=None, alias="catalogEntryId", max_length=160)
    test_data: bool = Field(default=False, alias="testData")

    @field_validator("unit")
    @classmethod
    def normalize_observation_unit(cls, value: str) -> str:
        return _normalize_unit(value)

    @field_validator("evidence_reference_hash")
    @classmethod
    def validate_evidence_hash(cls, value: str | None) -> str | None:
        if value is not None and _HASH.fullmatch(value) is None:
            raise ValueError("evidenceReferenceHash must be sha256")
        return value


class ConsentChange(CatalogModel):
    scope: Literal["market_aggregate", "tenant_statistics"] = "market_aggregate"
    project_id: str | None = Field(default=None, alias="projectId")
    granted: bool
    policy_version: str = Field(default="market-aggregate/1.0.0", alias="policyVersion", max_length=120)
    source: str = Field(default="estimate-editor", max_length=120)


ESTIMATE_TOOL_CONTRACTS: dict[str, dict[str, Any]] = {
    "estimate_scope_draft": {"mutation": False, "maxRows": 200},
    "catalog_search": {"mutation": False, "maxRows": 100},
    "catalog_candidate_create": {"mutation": True, "idempotent": True},
    "technology_card_expand": {"mutation": False, "maxRows": 200},
    "estimate_price_resolve": {"mutation": False, "maxRows": 200},
    "estimate_calculate": {"mutation": True, "idempotent": True},
    "estimate_save_version": {"mutation": True, "idempotent": True, "optimisticVersion": True},
    "estimate_compare_versions": {"mutation": False, "maxRows": 200},
    "estimate_export_prepare": {"mutation": False, "savedVersionOnly": True},
}


def require_project(database: sqlite3.Connection, *, identity: UserSession, project_id: str) -> sqlite3.Row:
    row = database.execute(
        "SELECT id, title FROM projects WHERE tenant_id = ? AND id = ? LIMIT 1",
        (identity.tenant_id, project_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "project_not_found", "message": "Проект не найден."})
    return row


def _visible_entry(database: sqlite3.Connection, *, identity: UserSession, project_id: str, entry_id: str) -> sqlite3.Row | None:
    return database.execute(
        """
        SELECT * FROM catalog_entries
        WHERE id = ? AND review_status = 'approved' AND archived_at IS NULL
          AND (
            visibility = 'system_curated'
            OR (visibility = 'tenant_private' AND tenant_id = ?)
            OR (visibility = 'project_private' AND tenant_id = ? AND project_id = ?)
          )
        LIMIT 1
        """,
        (entry_id, identity.tenant_id, identity.tenant_id, project_id),
    ).fetchone()


def _entry_view(row: sqlite3.Row, *, price: Mapping[str, Any] | None = None) -> dict[str, Any]:
    provenance = _json_object(row["provenance_json"], {})
    return {
        "id": str(row["id"]),
        "tenantId": str(row["tenant_id"]) if row["tenant_id"] is not None else None,
        "projectId": str(row["project_id"]) if row["project_id"] is not None else None,
        "visibility": str(row["visibility"]),
        "kind": str(row["kind"]),
        "canonicalName": str(row["canonical_name"]),
        "shortName": str(row["short_name"]),
        "description": str(row["description"]),
        "categoryId": str(row["category_id"]),
        "canonicalUnit": str(row["canonical_unit"]),
        "specification": _json_object(row["specification_json"], {}),
        "aliases": _json_object(row["aliases_json"], []),
        "regionScope": _json_object(row["region_scope_json"], {}),
        "source": {
            "type": str(provenance.get("sourceType") or "curated"),
            "reference": str(provenance.get("sourceReference") or ""),
        },
        "reviewStatus": str(row["review_status"]),
        "confidence": str(row["confidence"]),
        "version": int(row["version"]),
        "validFrom": row["valid_from"],
        "validUntil": row["valid_until"],
        "priceRange": dict(price) if price is not None else None,
        "createdAt": str(row["created_at"]),
        "updatedAt": str(row["updated_at"]),
    }


def _search_score(query: str, row: sqlite3.Row) -> int:
    if not query:
        return 10
    needle = normalize_catalog_text(query)
    aliases = _aliases(_json_object(row["aliases_json"], []))
    values = [str(row["canonical_name"]), str(row["short_name"]), *aliases]
    normalized = [normalize_catalog_text(value) for value in values]
    if needle in normalized:
        return 1
    if any(value.startswith(needle) for value in normalized):
        return 2
    if any(needle in value for value in normalized):
        return 3
    query_tokens = set(needle.split())
    if query_tokens and any(query_tokens.issubset(set(value.split())) for value in normalized):
        return 4
    return 100


def search_catalog(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    project_id: str,
    query: str | None = None,
    kind: str | None = None,
    category_id: str | None = None,
    region: str | None = None,
    source: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    require_project(database, identity=identity, project_id=project_id)
    predicates = [
        "review_status = 'approved'",
        "archived_at IS NULL",
        "(visibility = 'system_curated' OR (visibility = 'tenant_private' AND tenant_id = ?) OR (visibility = 'project_private' AND tenant_id = ? AND project_id = ?))",
    ]
    params: list[Any] = [identity.tenant_id, identity.tenant_id, project_id]
    if kind:
        if kind not in CATALOG_KINDS:
            raise HTTPException(status_code=422, detail={"code": "catalog_kind_invalid", "message": "Неподдерживаемый вид позиции."})
        predicates.append("kind = ?")
        params.append(kind)
    if category_id:
        predicates.append("category_id = ?")
        params.append(category_id)
    rows = database.execute(
        f"SELECT * FROM catalog_entries WHERE {' AND '.join(predicates)} ORDER BY updated_at DESC LIMIT 500",
        params,
    ).fetchall()
    requested_region = normalize_catalog_text(region or "")
    requested_source = normalize_catalog_text(source or "")
    ranked: list[tuple[int, sqlite3.Row]] = []
    for row in rows:
        score = _search_score(query or "", row)
        if score >= 100 and query:
            continue
        if requested_region:
            scope = _json_object(row["region_scope_json"], {})
            scope_text = normalize_catalog_text(json.dumps(scope, ensure_ascii=False))
            # An empty region scope means "not region-bound" and should remain
            # searchable. A populated scope is narrowed only when it is a
            # tenant/project entry; system-curated seed is global.
            if scope_text not in {"", "{}"} and requested_region not in scope_text and str(row["visibility"]) != "system_curated":
                continue
        if requested_source:
            provenance = _json_object(row["provenance_json"], {})
            if requested_source not in normalize_catalog_text(str(provenance.get("sourceType") or "")):
                continue
        ranked.append((score, row))
    ranked.sort(key=lambda item: (item[0], -int(item[1]["version"]), str(item[1]["canonical_name"])))
    result: list[dict[str, Any]] = []
    for _, row in ranked[:limit]:
        item_key = market_item_key(kind=str(row["kind"]), description=str(row["canonical_name"]), unit=str(row["canonical_unit"]))
        aggregate = database.execute(
            """
            SELECT p25, median, p75, independent_contributor_count,
                   observation_count, freshness, confidence, generated_at
            FROM market_price_aggregates
            WHERE item_key = ? AND unit = ? AND region = ? AND published = 1
            ORDER BY generated_at DESC LIMIT 1
            """,
            (item_key, str(row["canonical_unit"]), region or ""),
        ).fetchone()
        price = None
        if aggregate is not None:
            price = {
                "p25": str(aggregate["p25"]),
                "median": str(aggregate["median"]),
                "p75": str(aggregate["p75"]),
                "independentContributors": int(aggregate["independent_contributor_count"]),
                "observationCount": int(aggregate["observation_count"]),
                "freshness": str(aggregate["freshness"]),
                "confidence": str(aggregate["confidence"]),
                "generatedAt": str(aggregate["generated_at"]),
            }
        result.append(_entry_view(row, price=price))
    return result


def candidate_view(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "projectId": str(row["project_id"]) if row["project_id"] is not None else None,
        "sourceType": str(row["source_type"]),
        "originalText": str(row["original_text"]),
        "proposedCanonicalName": str(row["proposed_canonical_name"]),
        "proposedShortName": str(row["proposed_short_name"]),
        "kind": str(row["kind"]),
        "proposedUnit": str(row["proposed_unit"]),
        "specification": _json_object(row["specification_json"], {}),
        "aliases": _json_object(row["aliases_json"], []),
        "categoryId": str(row["category_id"]),
        "confidence": str(row["confidence"]),
        "status": str(row["status"]),
        "duplicateOfId": row["duplicate_of_id"],
        "mergeTargetId": row["merge_target_id"],
        "reviewNote": row["review_note"],
        "createdAt": str(row["created_at"]),
        "updatedAt": str(row["updated_at"]),
    }


def create_catalog_candidate(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    project_id: str,
    payload: CatalogCandidateCreate,
    now: str | None = None,
) -> tuple[dict[str, Any], bool]:
    require_project(database, identity=identity, project_id=project_id)
    if payload.source_estimate_id:
        source = database.execute(
            """
            SELECT id, version, content_json FROM document_slots
            WHERE tenant_id = ? AND project_id = ? AND id = ?
              AND slot_type = 'estimate' AND content_json IS NOT NULL
            LIMIT 1
            """,
            (identity.tenant_id, project_id, payload.source_estimate_id),
        ).fetchone()
        if source is None or (
            payload.source_estimate_version is not None
            and int(source["version"]) != payload.source_estimate_version
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "catalog_source_estimate_invalid",
                    "message": "Источник кандидата должен быть сохранённой сметой этого проекта.",
                },
            )
    current = now or _utc_now()
    proposed_short = (payload.proposed_short_name or payload.proposed_canonical_name)[:160]
    name_norm = normalize_catalog_text(payload.proposed_canonical_name)
    # SQLite has no application normalizer function. Do the duplicate
    # comparison in Python while keeping the SQL tenant/project scope strict.
    duplicate = None
    visible = search_catalog(
        database,
        identity=identity,
        project_id=project_id,
        kind=payload.kind,
        limit=500,
    )
    for entry in visible:
        if _normalize_unit(str(entry["canonicalUnit"])) == payload.proposed_unit and normalize_catalog_text(str(entry["canonicalName"])) == name_norm:
            duplicate = entry
            break
    candidate_id = f"catalog_candidate_{uuid.uuid4().hex}"
    status_value = "needs_review" if duplicate is not None else "proposed"
    audit = [{"event": "created", "at": current, "actor": identity.user_id}]
    database.execute(
        """
        INSERT INTO catalog_candidates (
            id, tenant_id, project_id, source_type, original_text,
            proposed_canonical_name, proposed_short_name, kind, proposed_unit,
            specification_json, aliases_json, category_id, confidence,
            source_estimate_id, source_estimate_version, source_row_id,
            status, duplicate_of_id, audit_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            candidate_id,
            identity.tenant_id,
            project_id,
            payload.source_type,
            payload.original_text,
            payload.proposed_canonical_name,
            proposed_short,
            payload.kind,
            payload.proposed_unit,
            _bounded_json(payload.specification),
            _bounded_json(_aliases(payload.aliases)),
            payload.category_id,
            payload.confidence,
            payload.source_estimate_id,
            payload.source_estimate_version,
            payload.source_row_id,
            status_value,
            str(duplicate["id"]) if duplicate is not None else None,
            _bounded_json(audit),
            current,
            current,
        ),
    )
    database.execute(
        "INSERT INTO catalog_candidate_events (id, tenant_id, candidate_id, event_type, actor_user_id, payload_json, created_at) VALUES (?, ?, ?, 'created', ?, ?, ?)",
        (f"catalog_candidate_event_{uuid.uuid4().hex}", identity.tenant_id, candidate_id, identity.user_id, _bounded_json({"sourceType": payload.source_type, "duplicateOfId": str(duplicate["id"]) if duplicate else None}), current),
    )
    row = database.execute("SELECT * FROM catalog_candidates WHERE tenant_id = ? AND id = ?", (identity.tenant_id, candidate_id)).fetchone()
    assert row is not None
    return candidate_view(row), duplicate is not None


def review_catalog_candidate(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    project_id: str,
    candidate_id: str,
    payload: CatalogCandidateReview,
    now: str | None = None,
) -> dict[str, Any]:
    require_project(database, identity=identity, project_id=project_id)
    if identity.role != UserRole.OWNER:
        raise HTTPException(status_code=403, detail={"code": "catalog_review_forbidden", "message": "Требуется роль владельца для проверки справочника."})
    row = database.execute(
        "SELECT * FROM catalog_candidates WHERE tenant_id = ? AND id = ? AND project_id = ? LIMIT 1",
        (identity.tenant_id, candidate_id, project_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "catalog_candidate_not_found", "message": "Кандидат справочника не найден."})
    if str(row["status"]) not in {"proposed", "needs_review"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "catalog_candidate_already_reviewed", "message": "Кандидат уже прошёл проверку."},
        )
    current = now or _utc_now()
    # Candidate status values are a domain enum, not the review command names.
    # Keep the API action concise while persisting the lifecycle state accepted
    # by the migration constraint.
    next_status = {
        "approve": "approved",
        "merge": "merged",
        "reject": "rejected",
    }[payload.action]
    entry_id: str | None = None
    if payload.action == "merge":
        if not payload.merge_target_id or _visible_entry(database, identity=identity, project_id=project_id, entry_id=payload.merge_target_id) is None:
            raise HTTPException(status_code=422, detail={"code": "catalog_merge_target_invalid", "message": "Целевая утверждённая позиция не найдена."})
        next_status = "merged"
        entry_id = payload.merge_target_id
    elif payload.action == "approve":
        if payload.visibility == "system_curated":
            raise HTTPException(status_code=422, detail={"code": "catalog_system_approval_forbidden", "message": "ИИ и пользовательские позиции нельзя публиковать как system-curated."})
        entry_id = f"catalog_entry_{uuid.uuid4().hex}"
        database.execute(
            """
            INSERT INTO catalog_entries (
                id, tenant_id, project_id, visibility, kind, canonical_name,
                short_name, description, category_id, canonical_unit,
                specification_json, aliases_json, region_scope_json,
                provenance_json, review_status, confidence, version,
                created_at, updated_at, created_by_user_id, approved_by_user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'approved', ?, 1, ?, ?, ?, ?)
            """,
            (
                entry_id,
                identity.tenant_id,
                project_id if payload.visibility == "project_private" else None,
                payload.visibility,
                str(row["kind"]),
                str(row["proposed_canonical_name"]),
                str(row["proposed_short_name"]),
                str(row["original_text"]),
                str(row["category_id"]),
                str(row["proposed_unit"]),
                str(row["specification_json"]),
                str(row["aliases_json"]),
                "{}",
                _bounded_json({"sourceType": "reviewed_candidate", "sourceReference": candidate_id}),
                str(row["confidence"]),
                current,
                current,
                identity.user_id,
                identity.user_id,
            ),
        )
    audit = list(_json_object(row["audit_json"], [])) if isinstance(_json_object(row["audit_json"], []), list) else []
    audit.append({"event": payload.action, "at": current, "actor": identity.user_id, "entryId": entry_id, "note": payload.review_note})
    database.execute(
        """
        UPDATE catalog_candidates
        SET status = ?, merge_target_id = ?, reviewer_user_id = ?, review_note = ?,
            audit_json = ?, updated_at = ?
        WHERE tenant_id = ? AND id = ?
        """,
        (next_status, entry_id if payload.action == "merge" else None, identity.user_id, payload.review_note, _bounded_json(audit), current, identity.tenant_id, candidate_id),
    )
    event_type = {
        "approve": "reviewed",
        "merge": "merged",
        "reject": "rejected",
    }[payload.action]
    database.execute(
        "INSERT INTO catalog_candidate_events (id, tenant_id, candidate_id, event_type, actor_user_id, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (f"catalog_candidate_event_{uuid.uuid4().hex}", identity.tenant_id, candidate_id, event_type, identity.user_id, _bounded_json({"entryId": entry_id, "note": payload.review_note, "action": payload.action}), current),
    )
    result = database.execute("SELECT * FROM catalog_candidates WHERE tenant_id = ? AND id = ?", (identity.tenant_id, candidate_id)).fetchone()
    assert result is not None
    view = candidate_view(result)
    view["catalogEntryId"] = entry_id
    return view


def list_technology_cards(database: sqlite3.Connection, *, identity: UserSession, project_id: str) -> list[dict[str, Any]]:
    require_project(database, identity=identity, project_id=project_id)
    rows = database.execute(
        """
        SELECT definitions.id, definitions.canonical_name, definitions.purpose,
               versions.id AS version_id, versions.version, versions.rules_version,
               versions.status, versions.applicability_json, versions.inputs_json,
               versions.lines_json, versions.resources_json,
               versions.assumptions_json, versions.exceptions_json
        FROM technology_card_definitions AS definitions
        JOIN technology_card_versions AS versions ON versions.card_id = definitions.id
        WHERE definitions.scope = 'system_curated' AND versions.status = 'approved'
          AND versions.version = (SELECT MAX(v2.version) FROM technology_card_versions AS v2 WHERE v2.card_id = definitions.id AND v2.status = 'approved')
        ORDER BY definitions.canonical_name
        LIMIT 100
        """
    ).fetchall()
    result = []
    for row in rows:
        result.append({
            "id": str(row["id"]),
            "name": str(row["canonical_name"]),
            "purpose": str(row["purpose"]),
            "versionId": str(row["version_id"]),
            "version": int(row["version"]),
            "rulesVersion": str(row["rules_version"]),
            "status": str(row["status"]),
            "applicability": _json_object(row["applicability_json"], {}),
            "inputs": _json_object(row["inputs_json"], []),
            "lines": _json_object(row["lines_json"], []),
            "resources": _json_object(row["resources_json"], []),
            "assumptions": _json_object(row["assumptions_json"], []),
            "exceptions": _json_object(row["exceptions_json"], []),
        })
    return result


def _pseudonym(secret: bytes, *, tenant_id: str, user_id: str) -> str:
    return "contributor:" + hmac.new(secret, f"{tenant_id}:{user_id}".encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def _consent_is_active(database: sqlite3.Connection, *, tenant_id: str, user_id: str, consent_id: str | None, project_id: str, scope: str = "market_aggregate") -> bool:
    if not consent_id:
        return False
    row = database.execute(
        """
        SELECT 1 FROM pricing_consent_grants
        WHERE tenant_id = ? AND id = ? AND user_id = ? AND scope = ? AND status = 'granted'
          AND (project_id IS NULL OR project_id = ?)
        LIMIT 1
        """,
        (tenant_id, consent_id, user_id, scope, project_id),
    ).fetchone()
    return row is not None


def record_catalog_price_observation(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    project_id: str,
    payload: PriceObservationCreate,
    secret: bytes,
    now: str | None = None,
) -> dict[str, Any]:
    require_project(database, identity=identity, project_id=project_id)
    current = now or _utc_now()
    slot = database.execute(
        "SELECT id, version, content_json FROM document_slots WHERE tenant_id = ? AND project_id = ? AND slot_type = 'estimate' LIMIT 1",
        (identity.tenant_id, project_id),
    ).fetchone()
    if slot is None or slot["content_json"] is None:
        # The expression above intentionally keeps this endpoint bound to a
        # saved estimate document; observations without a saved source cannot
        # become market evidence.
        raise HTTPException(status_code=409, detail={"code": "estimate_version_required", "message": "Сначала сохраните версию сметы."})
    try:
        price = Decimal(payload.observed_unit_price)
    except InvalidOperation:
        raise HTTPException(status_code=422, detail={"code": "price_invalid", "message": "Цена должна быть десятичным числом."}) from None
    if price <= 0 or not price.is_finite():
        raise HTTPException(status_code=422, detail={"code": "price_invalid", "message": "Цена должна быть больше нуля."})
    if payload.catalog_entry_id and _visible_entry(database, identity=identity, project_id=project_id, entry_id=payload.catalog_entry_id) is None:
        raise HTTPException(status_code=404, detail={"code": "catalog_entry_not_found", "message": "Позиция справочника не найдена."})
    if payload.source_type in {"supplier_offer", "contract_price", "paid_invoice", "completed_work"} and not payload.evidence_reference_hash:
        raise HTTPException(status_code=422, detail={"code": "evidence_required", "message": "Для подтверждённого источника требуется hash подтверждающего документа."})
    active_consent = _consent_is_active(database, tenant_id=identity.tenant_id, user_id=identity.user_id, consent_id=payload.consent_id, project_id=project_id)
    eligible = (
        payload.source_type not in {"ai_preliminary", "user_edit", "official_reference"}
        and active_consent
        and payload.evidence_reference_hash is not None
        and payload.lifecycle in {"approved", "contracted"}
        and (payload.valid_until is None or payload.valid_until >= current[:10])
        and not payload.test_data
    )
    observation_id = f"price_observation_{uuid.uuid4().hex}"
    item_key = market_item_key(kind=payload.kind, description=payload.description, unit=payload.unit)
    context = {
        "sourceScope": "tenant_private",
        "consentPolicyVersion": POLICY_VERSION,
        "evidenceProvided": payload.evidence_reference_hash is not None,
    }
    database.execute(
        """
        INSERT INTO price_observations (
            tenant_id, id, project_id, document_id, estimate_version, row_id,
            item_key, catalog_entry_id, item_kind, description, normalized_description,
            specification_json, region, country, municipality, timezone, unit,
            quantity_band, quantity_min, quantity_max, observed_unit_price_rub,
            currency, tax_treatment, delivery_treatment, source_type, lifecycle,
            context_json, evidence_reference_hash, observed_at, valid_until,
            confidence, consent_id, contributor_pseudonym, aggregate_eligible,
            test_data, created_by_user_id
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            'RUB', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            identity.tenant_id, observation_id, project_id, str(slot["id"]), int(slot["version"]), payload.row_id,
            item_key, payload.catalog_entry_id, payload.kind, payload.description, normalized_market_text(payload.description),
            _bounded_json(payload.specification), payload.region, payload.country.upper(), payload.municipality, payload.timezone,
            payload.unit, payload.quantity_band, payload.quantity_min, payload.quantity_max, f"{price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}",
            payload.tax_treatment, payload.delivery_treatment, payload.source_type, payload.lifecycle,
            _bounded_json(context), payload.evidence_reference_hash, current, payload.valid_until, payload.confidence,
            payload.consent_id if active_consent else None, _pseudonym(secret, tenant_id=identity.tenant_id, user_id=identity.user_id),
            1 if eligible else 0, 1 if payload.test_data else 0, identity.user_id,
        ),
    )
    return {
        "id": observation_id,
        "itemKey": item_key,
        "aggregateEligible": eligible,
        "quality": "source_backed" if eligible else ("preliminary" if payload.source_type == "ai_preliminary" else "missing"),
        "sourceType": payload.source_type,
        "observedAt": current,
        "validUntil": payload.valid_until,
        "consentApplied": active_consent,
    }


def change_pricing_consent(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    payload: ConsentChange,
    now: str | None = None,
) -> dict[str, Any]:
    current = now or _utc_now()
    if payload.project_id:
        require_project(database, identity=identity, project_id=payload.project_id)
    existing = database.execute(
        """
        SELECT * FROM pricing_consent_grants
        WHERE tenant_id = ? AND user_id = ? AND scope = ?
          AND COALESCE(project_id, '') = COALESCE(?, '') AND status = 'granted'
        ORDER BY granted_at DESC LIMIT 1
        """,
        (identity.tenant_id, identity.user_id, payload.scope, payload.project_id),
    ).fetchone()
    if payload.granted:
        if existing is not None:
            return {"id": str(existing["id"]), "scope": payload.scope, "status": "granted", "policyVersion": str(existing["policy_version"]), "grantedAt": str(existing["granted_at"]), "revokedAt": None}
        consent_id = f"consent_{uuid.uuid4().hex}"
        database.execute(
            "INSERT INTO pricing_consent_grants (id, tenant_id, user_id, project_id, scope, policy_version, status, granted_at, revoked_at, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'granted', ?, NULL, ?, ?, ?)",
            (consent_id, identity.tenant_id, identity.user_id, payload.project_id, payload.scope, payload.policy_version, current, payload.source, current, current),
        )
        event = "granted"
    else:
        if existing is None:
            return {"id": None, "scope": payload.scope, "status": "revoked", "policyVersion": payload.policy_version, "grantedAt": None, "revokedAt": current}
        consent_id = str(existing["id"])
        database.execute("UPDATE pricing_consent_grants SET status = 'revoked', revoked_at = ?, updated_at = ? WHERE tenant_id = ? AND id = ?", (current, current, identity.tenant_id, consent_id))
        event = "revoked"
    database.execute(
        "INSERT INTO pricing_consent_events (id, tenant_id, consent_id, event_type, actor_user_id, policy_version, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (f"consent_event_{uuid.uuid4().hex}", identity.tenant_id, consent_id, event, identity.user_id, payload.policy_version, _bounded_json({"source": payload.source, "projectId": payload.project_id}), current),
    )
    return {"id": consent_id, "scope": payload.scope, "status": "granted" if payload.granted else "revoked", "policyVersion": payload.policy_version, "grantedAt": current if payload.granted else str(existing["granted_at"]), "revokedAt": None if payload.granted else current}


def refresh_market_price_aggregate(
    database: sqlite3.Connection,
    *,
    item_key: str,
    unit: str,
    region: str,
    country: str = "RU",
    municipality: str | None = None,
    quantity_band: str = "unspecified",
    as_of: str | None = None,
    policy_version: str = POLICY_VERSION,
) -> dict[str, Any]:
    current = as_of or _utc_now()
    unit = _normalize_unit(unit)
    policy = database.execute(
        "SELECT minimum_independent_contributors, freshness_days, outlier_method FROM market_pricing_policies WHERE policy_version = ? AND active = 1 LIMIT 1",
        (policy_version,),
    ).fetchone()
    if policy is None:
        raise ValueError("market pricing policy is unavailable")
    cutoff = (datetime.fromisoformat(current.replace("Z", "+00:00")) - timedelta(days=int(policy["freshness_days"]))).isoformat().replace("+00:00", "Z")
    rows = database.execute(
        """
        SELECT po.* FROM price_observations AS po
        JOIN pricing_consent_grants AS consent
          ON consent.tenant_id = po.tenant_id AND consent.id = po.consent_id
         AND consent.status = 'granted' AND consent.scope = 'market_aggregate'
        WHERE po.item_key = ? AND po.unit = ? AND po.region = ? AND po.country = ?
          AND po.quantity_band = ? AND po.aggregate_eligible = 1
          AND po.archived_at IS NULL AND po.test_data = 0
          AND po.observed_at >= ? AND (po.valid_until IS NULL OR po.valid_until >= ?)
          AND po.source_type <> 'ai_preliminary'
        ORDER BY po.observed_at DESC
        """,
        (item_key, unit, region, country.upper(), quantity_band, cutoff, current[:10]),
    ).fetchall()
    # Deduplicate repeated versions/evidence, then keep one observation per
    # pseudonymous contributor so one tenant cannot simulate a cohort.
    dedup: dict[tuple[str, str, str], sqlite3.Row] = {}
    for row in rows:
        key = (str(row["tenant_id"]), str(row["document_id"]), str(row["row_id"]))
        if key not in dedup:
            dedup[key] = row
    by_contributor: dict[str, sqlite3.Row] = {}
    for row in dedup.values():
        contributor = str(row["contributor_pseudonym"])
        if contributor not in by_contributor:
            by_contributor[contributor] = row
    raw_values = [(contributor, Decimal(str(row["observed_unit_price_rub"])), row) for contributor, row in by_contributor.items()]
    raw_values.sort(key=lambda item: item[1])
    values = [item[1] for item in raw_values]
    if len(values) >= 4:
        q1 = percentile(values, Decimal("0.25"))
        q3 = percentile(values, Decimal("0.75"))
        iqr = q3 - q1
        lower, upper = q1 - Decimal("1.5") * iqr, q3 + Decimal("1.5") * iqr
        raw_values = [item for item in raw_values if lower <= item[1] <= upper]
    values = [item[1] for item in raw_values]
    contributor_count = len(values)
    # Repeated versions/evidence of the same source row are one observation in
    # the public cohort. The raw table remains append-only for audit purposes.
    observation_count = len(dedup)
    published = contributor_count >= int(policy["minimum_independent_contributors"])
    generated = current
    if values:
        p25 = percentile(values, Decimal("0.25")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        median = percentile(values, Decimal("0.5")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        p75 = percentile(values, Decimal("0.75")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        p25 = median = p75 = Decimal("0.00")
    confidence = (Decimal(min(1, contributor_count / max(1, int(policy["minimum_independent_contributors"])))) * Decimal("0.9")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    source_composition: dict[str, int] = {}
    for _, _, row in raw_values:
        source = str(row["source_type"])
        source_composition[source] = source_composition.get(source, 0) + 1
    aggregate_id = "market_aggregate_" + hashlib.sha256("|".join((item_key, unit, country.upper(), region, municipality or "", quantity_band, cutoff[:10], current[:10], policy_version)).encode("utf-8")).hexdigest()[:40]
    database.execute(
        """
        INSERT INTO market_price_aggregates (
            id, item_key, unit, country, region, municipality, quantity_band,
            date_window_start, date_window_end, source_composition_json,
            independent_contributor_count, observation_count, p25, median, p75,
            freshness, confidence, calculation_policy_version, generated_at, published
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            source_composition_json = excluded.source_composition_json,
            independent_contributor_count = excluded.independent_contributor_count,
            observation_count = excluded.observation_count,
            p25 = excluded.p25, median = excluded.median, p75 = excluded.p75,
            freshness = excluded.freshness, confidence = excluded.confidence,
            generated_at = excluded.generated_at, published = excluded.published
        """,
        (aggregate_id, item_key, unit, country.upper(), region, municipality, quantity_band, cutoff[:10], current[:10], _bounded_json(source_composition), contributor_count, observation_count, f"{p25:.2f}", f"{median:.2f}", f"{p75:.2f}", "fresh" if published else "stale", f"{confidence:.4f}", policy_version, generated, 1 if published else 0),
    )
    return {
        "id": aggregate_id,
        "itemKey": item_key,
        "unit": unit,
        "country": country.upper(),
        "region": region,
        "municipality": municipality,
        "quantityBand": quantity_band,
        "dateWindow": {"from": cutoff[:10], "to": current[:10]},
        "sourceComposition": source_composition,
        "independentContributors": contributor_count,
        "observationCount": observation_count,
        "p25": f"{p25:.2f}",
        "median": f"{median:.2f}",
        "p75": f"{p75:.2f}",
        "freshness": "fresh" if published else "insufficient_cohort",
        "confidence": f"{confidence:.4f}",
        "calculationPolicyVersion": policy_version,
        "generatedAt": generated,
        "published": published,
        "minimumIndependentContributors": int(policy["minimum_independent_contributors"]),
    }


def get_market_aggregate(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    project_id: str,
    item_key: str,
    unit: str,
    region: str,
    country: str = "RU",
    municipality: str | None = None,
    quantity_band: str = "unspecified",
    refresh: bool = True,
) -> dict[str, Any]:
    require_project(database, identity=identity, project_id=project_id)
    if not _HASH.fullmatch(item_key):
        raise HTTPException(status_code=422, detail={"code": "item_key_invalid", "message": "Ключ позиции имеет неверный формат."})
    if refresh:
        result = refresh_market_price_aggregate(database, item_key=item_key, unit=_normalize_unit(unit), region=region, country=country, municipality=municipality, quantity_band=quantity_band)
    else:
        row = database.execute("SELECT * FROM market_price_aggregates WHERE item_key = ? AND unit = ? AND region = ? AND published = 1 ORDER BY generated_at DESC LIMIT 1", (item_key, _normalize_unit(unit), region)).fetchone()
        if row is None:
            return {"published": False, "reason": "cohort_insufficient", "minimumIndependentContributors": 5}
        result = {"published": True, "itemKey": item_key, "unit": str(row["unit"]), "region": str(row["region"]), "p25": str(row["p25"]), "median": str(row["median"]), "p75": str(row["p75"]), "independentContributors": int(row["independent_contributor_count"]), "observationCount": int(row["observation_count"]), "freshness": str(row["freshness"]), "confidence": str(row["confidence"]), "calculationPolicyVersion": str(row["calculation_policy_version"]), "generatedAt": str(row["generated_at"])}
    # Public/tenant API returns only aggregate statistics. Supplier names,
    # evidence hashes and raw observations are intentionally absent.
    return result
