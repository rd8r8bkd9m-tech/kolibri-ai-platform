from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from .database import get_database, transaction
from .estimate_catalog import (
    CATALOG_KINDS,
    ESTIMATE_TOOL_CONTRACTS,
    POLICY_VERSION,
    CatalogCandidateCreate,
    CatalogCandidateReview,
    ConsentChange,
    PriceObservationCreate,
    _utc_now,
    candidate_view,
    change_pricing_consent,
    create_catalog_candidate,
    get_market_aggregate,
    list_technology_cards,
    record_catalog_price_observation,
    require_project,
    review_catalog_candidate,
    search_catalog,
    _visible_entry,
)
from .market_pricing import market_item_key
from .product_access import ConstructionEstimateAccessDependency
from .security import require_mutation_auth

router = APIRouter(prefix="/v1/projects", tags=["estimate-catalog"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = ConstructionEstimateAccessDependency
MutationAuthDependency = Annotated[None, Depends(require_mutation_auth)]
IdempotencyHeader = Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)]


def _error(code: str, message: str, status_code: int = 422) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _request_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _idempotency_key(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str,
    operation: str,
    provided: str | None,
    payload: Any,
) -> tuple[str, dict[str, Any] | None]:
    key = provided.strip() if provided else f"generated-{uuid.uuid4().hex}"
    if len(key) < 8 or len(key) > 128:
        raise _error("idempotency_key_invalid", "Idempotency-Key имеет неверную длину.")
    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
    request_hash = _request_hash(payload)
    row = database.execute(
        "SELECT request_hash, result_type, result_id FROM api_command_idempotency WHERE tenant_id = ? AND operation = ? AND key_hash = ? LIMIT 1",
        (tenant_id, operation, key_hash),
    ).fetchone()
    if row is None:
        return key_hash, None
    if str(row["request_hash"]) != request_hash:
        raise _error("idempotency_conflict", "Этот ключ уже использован для другой операции.", status.HTTP_409_CONFLICT)
    return key_hash, {"resultType": str(row["result_type"]), "resultId": str(row["result_id"])}


def _store_idempotency(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str,
    operation: str,
    key_hash: str,
    payload: Any,
    result_type: str,
    result_id: str,
    now: str,
) -> None:
    database.execute(
        """
        INSERT INTO api_command_idempotency (
            tenant_id, operation, key_hash, request_hash, result_type,
            result_id, created_by_user_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (tenant_id, operation, key_hash, _request_hash(payload), result_type, result_id, user_id, now),
    )


@router.get("/{project_id}/estimate/catalog")
def catalog_search(
    project_id: str,
    database: DatabaseDependency,
    identity: IdentityDependency,
    query: Annotated[str | None, Query(max_length=160)] = None,
    kind: Annotated[str | None, Query()] = None,
    category_id: Annotated[str | None, Query(alias="categoryId", max_length=120)] = None,
    region: Annotated[str | None, Query(max_length=160)] = None,
    source: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, Any]:
    if kind is not None and kind not in CATALOG_KINDS:
        raise _error("catalog_kind_invalid", "Неподдерживаемый вид позиции.")
    entries = search_catalog(
        database,
        identity=identity,
        project_id=project_id,
        query=query,
        kind=kind,
        category_id=category_id,
        region=region,
        source=source,
        limit=limit,
    )
    return {
        "projectId": project_id,
        "query": query or "",
        "filters": {"kind": kind, "categoryId": category_id, "region": region, "source": source},
        "entries": entries,
        "count": len(entries),
        "scope": ["system_curated", "tenant_private", "project_private"],
    }


@router.get("/{project_id}/estimate/catalog/candidates")
def list_candidates(
    project_id: str,
    database: DatabaseDependency,
    identity: IdentityDependency,
    candidate_status: Annotated[str | None, Query(alias="status", max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, Any]:
    require_project(database, identity=identity, project_id=project_id)
    predicates = ["tenant_id = ?", "project_id = ?"]
    params: list[Any] = [identity.tenant_id, project_id]
    if candidate_status:
        predicates.append("status = ?")
        params.append(candidate_status)
    params.append(limit)
    rows = database.execute(
        f"SELECT * FROM catalog_candidates WHERE {' AND '.join(predicates)} ORDER BY updated_at DESC, id DESC LIMIT ?",
        params,
    ).fetchall()
    return {"projectId": project_id, "candidates": [candidate_view(row) for row in rows]}


@router.post("/{project_id}/estimate/catalog/candidates", status_code=201)
def create_candidate(
    project_id: str,
    payload: CatalogCandidateCreate,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _auth: MutationAuthDependency,
    idempotency_key: IdempotencyHeader = None,
) -> dict[str, Any]:
    with transaction(database, immediate=True):
        key_hash, replay = _idempotency_key(
            database,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            operation="estimate.catalog.candidate.create",
            provided=idempotency_key,
            payload={"projectId": project_id, **payload.model_dump(by_alias=True, mode="json")},
        )
        if replay is not None:
            row = database.execute("SELECT * FROM catalog_candidates WHERE tenant_id = ? AND id = ? LIMIT 1", (identity.tenant_id, replay["resultId"])).fetchone()
            if row is None:
                raise _error("idempotency_result_missing", "Результат идемпотентной операции недоступен.", status.HTTP_409_CONFLICT)
            return {"candidate": candidate_view(row), "replayed": True}
        result, duplicate = create_catalog_candidate(database, identity=identity, project_id=project_id, payload=payload)
        _store_idempotency(database, tenant_id=identity.tenant_id, user_id=identity.user_id, operation="estimate.catalog.candidate.create", key_hash=key_hash, payload={"projectId": project_id, **payload.model_dump(by_alias=True, mode="json")}, result_type="catalog_candidate", result_id=str(result["id"]), now=_utc_now())
    return {"candidate": result, "duplicateDetected": duplicate, "replayed": False}


@router.post("/{project_id}/estimate/catalog/candidates/{candidate_id}/review")
def review_candidate(
    project_id: str,
    candidate_id: str,
    payload: CatalogCandidateReview,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _auth: MutationAuthDependency,
    idempotency_key: IdempotencyHeader = None,
) -> dict[str, Any]:
    with transaction(database, immediate=True):
        request_payload = {"projectId": project_id, "candidateId": candidate_id, **payload.model_dump(by_alias=True, mode="json")}
        key_hash, replay = _idempotency_key(database, tenant_id=identity.tenant_id, user_id=identity.user_id, operation="estimate.catalog.candidate.review", provided=idempotency_key, payload=request_payload)
        if replay is not None:
            row = database.execute("SELECT * FROM catalog_candidates WHERE tenant_id = ? AND id = ? LIMIT 1", (identity.tenant_id, candidate_id)).fetchone()
            if row is None:
                raise _error("idempotency_result_missing", "Результат идемпотентной операции недоступен.", status.HTTP_409_CONFLICT)
            return {"candidate": candidate_view(row), "replayed": True}
        result = review_catalog_candidate(database, identity=identity, project_id=project_id, candidate_id=candidate_id, payload=payload)
        _store_idempotency(database, tenant_id=identity.tenant_id, user_id=identity.user_id, operation="estimate.catalog.candidate.review", key_hash=key_hash, payload=request_payload, result_type="catalog_candidate", result_id=candidate_id, now=_utc_now())
    return {"candidate": result, "replayed": False}


@router.get("/{project_id}/estimate/technology-cards")
def technology_cards(
    project_id: str,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, Any]:
    return {"projectId": project_id, "cards": list_technology_cards(database, identity=identity, project_id=project_id)}


@router.get("/{project_id}/estimate/tools")
def estimate_tools(
    project_id: str,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, Any]:
    require_project(database, identity=identity, project_id=project_id)
    return {"projectId": project_id, "contracts": ESTIMATE_TOOL_CONTRACTS}


@router.post("/{project_id}/estimate/price-observations", status_code=201)
def create_price_observation(
    project_id: str,
    payload: PriceObservationCreate,
    request: Request,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _auth: MutationAuthDependency,
    idempotency_key: IdempotencyHeader = None,
) -> dict[str, Any]:
    request_payload = {"projectId": project_id, **payload.model_dump(by_alias=True, mode="json")}
    with transaction(database, immediate=True):
        key_hash, replay = _idempotency_key(database, tenant_id=identity.tenant_id, user_id=identity.user_id, operation="estimate.price_observation.create", provided=idempotency_key, payload=request_payload)
        if replay is not None:
            row = database.execute("SELECT id, aggregate_eligible, source_type, observed_at, valid_until, consent_id FROM price_observations WHERE tenant_id = ? AND id = ? LIMIT 1", (identity.tenant_id, replay["resultId"])).fetchone()
            if row is None:
                raise _error("idempotency_result_missing", "Результат идемпотентной операции недоступен.", status.HTTP_409_CONFLICT)
            return {"observation": {"id": str(row["id"]), "aggregateEligible": bool(row["aggregate_eligible"]), "sourceType": str(row["source_type"]), "observedAt": str(row["observed_at"]), "validUntil": row["valid_until"], "consentApplied": row["consent_id"] is not None}, "replayed": True}
        settings = request.app.state.settings
        result = record_catalog_price_observation(database, identity=identity, project_id=project_id, payload=payload, secret=settings.csrf_secret)
        _store_idempotency(database, tenant_id=identity.tenant_id, user_id=identity.user_id, operation="estimate.price_observation.create", key_hash=key_hash, payload=request_payload, result_type="price_observation", result_id=str(result["id"]), now=_utc_now())
    return {"observation": result, "replayed": False}


@router.get("/{project_id}/estimate/consent")
def get_consent(
    project_id: str,
    database: DatabaseDependency,
    identity: IdentityDependency,
    scope: str = "market_aggregate",
) -> dict[str, Any]:
    require_project(database, identity=identity, project_id=project_id)
    row = database.execute(
        "SELECT id, policy_version, status, granted_at, revoked_at, source FROM pricing_consent_grants WHERE tenant_id = ? AND user_id = ? AND scope = ? AND (project_id IS NULL OR project_id = ?) ORDER BY updated_at DESC LIMIT 1",
        (identity.tenant_id, identity.user_id, scope, project_id),
    ).fetchone()
    if row is None:
        return {"projectId": project_id, "scope": scope, "status": "not_granted", "policyVersion": POLICY_VERSION}
    return {"projectId": project_id, "scope": scope, "status": str(row["status"]), "id": str(row["id"]), "policyVersion": str(row["policy_version"]), "grantedAt": row["granted_at"], "revokedAt": row["revoked_at"], "source": str(row["source"])}


@router.post("/{project_id}/estimate/consent")
def change_consent(
    project_id: str,
    payload: ConsentChange,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _auth: MutationAuthDependency,
    idempotency_key: IdempotencyHeader = None,
) -> dict[str, Any]:
    request_payload = {"projectId": project_id, **payload.model_dump(by_alias=True, mode="json")}
    with transaction(database, immediate=True):
        key_hash, replay = _idempotency_key(database, tenant_id=identity.tenant_id, user_id=identity.user_id, operation="estimate.pricing_consent.change", provided=idempotency_key, payload=request_payload)
        if replay is not None:
            row = database.execute("SELECT id, scope, status, policy_version, granted_at, revoked_at FROM pricing_consent_grants WHERE tenant_id = ? AND id = ? LIMIT 1", (identity.tenant_id, replay["resultId"])).fetchone()
            if row is None:
                raise _error("idempotency_result_missing", "Результат идемпотентной операции недоступен.", status.HTTP_409_CONFLICT)
            return {"consent": {"id": str(row["id"]), "scope": str(row["scope"]), "status": str(row["status"]), "policyVersion": str(row["policy_version"]), "grantedAt": row["granted_at"], "revokedAt": row["revoked_at"]}, "replayed": True}
        result = change_pricing_consent(database, identity=identity, payload=payload.model_copy(update={"project_id": project_id}), now=_utc_now())
        if result.get("id"):
            _store_idempotency(database, tenant_id=identity.tenant_id, user_id=identity.user_id, operation="estimate.pricing_consent.change", key_hash=key_hash, payload=request_payload, result_type="pricing_consent", result_id=str(result["id"]), now=_utc_now())
    return {"consent": result, "replayed": False}


@router.get("/{project_id}/estimate/market-prices")
def market_prices(
    project_id: str,
    database: DatabaseDependency,
    identity: IdentityDependency,
    item_key: str | None = Query(default=None, alias="itemKey"),
    catalog_entry_id: str | None = Query(default=None, alias="catalogEntryId"),
    unit: str | None = Query(default=None, max_length=32),
    region: str = Query(min_length=1, max_length=160),
    country: str = Query(default="RU", min_length=2, max_length=3),
    municipality: str | None = Query(default=None, max_length=160),
    quantity_band: str = Query(default="unspecified", alias="quantityBand", max_length=80),
    refresh: bool = True,
) -> dict[str, Any]:
    require_project(database, identity=identity, project_id=project_id)
    if catalog_entry_id:
        entry = _visible_entry(
            database,
            identity=identity,
            project_id=project_id,
            entry_id=catalog_entry_id,
        )
        if entry is None:
            raise _error("catalog_entry_not_found", "Позиция справочника не найдена.", status.HTTP_404_NOT_FOUND)
        if item_key is None:
            item_key = market_item_key(kind=str(entry["kind"]), description=str(entry["canonical_name"]), unit=str(entry["canonical_unit"]))
        unit = unit or str(entry["canonical_unit"])
    if not item_key or not unit:
        raise _error("market_price_key_required", "Укажите catalogEntryId либо itemKey и unit.")
    result = get_market_aggregate(database, identity=identity, project_id=project_id, item_key=item_key, unit=unit, region=region, country=country, municipality=municipality, quantity_band=quantity_band, refresh=refresh)
    return {"projectId": project_id, "aggregate": result}
