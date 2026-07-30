from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from .database import get_database, transaction
from .estimate_artifact import (
    canonical_estimate_json,
    estimate_document_with_prices,
    estimate_view,
    load_estimate_slot,
    parse_estimate_document,
    record_estimate_version,
)
from .market_pricing import ObservationSource, record_price_observations
from .pricing_sources import (
    FGIS_PUBLIC_PRICES_URL,
    FGIS_SOURCE_POLICY,
    FGIS_SOURCE_POLICY_VERSION,
    PARSER_VERSION,
    SUPPLIER_SOURCE_POLICY,
    SUPPLIER_SOURCE_POLICY_VERSION,
    FgisMatch,
    FgisPriceAdapter,
    PricingRefreshInput,
    PricingRegionUnresolved,
    PricingSourceError,
    PricingSourceProtocolError,
    PricingSourceUnavailable,
    SupplierOfferInput,
    canonical_json,
    fgis_price_evidence,
    money,
    sha256_json,
    supplier_price_evidence,
)
from .product_access import ConstructionEstimateAccessDependency
from .schemas import UserSession
from .security import require_mutation_auth

router = APIRouter(prefix="/v1/projects", tags=["pricing"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = ConstructionEstimateAccessDependency
MutationAuthDependency = Annotated[None, Depends(require_mutation_auth)]
IdempotencyDependency = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=16, max_length=128),
]
PRICING_COMMAND_LEASE_SECONDS = 60


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _now(database: sqlite3.Connection) -> str:
    return str(
        database.execute(
            "SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
        ).fetchone()[0]
    )


def _request_hash(value: dict[str, Any]) -> str:
    return sha256_json(value)


def _load_slot(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
) -> sqlite3.Row:
    row = load_estimate_slot(
        database,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    if row is None or row["content_json"] is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "estimate_not_found",
            "Смета не найдена.",
        )
    return row


def _claim_command(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    idempotency_key: str,
    request_hash: str,
    command_type: str,
    now: str,
) -> tuple[str, dict[str, Any] | None]:
    existing = database.execute(
        """
        SELECT id, request_hash, status, response_json, created_at
        FROM pricing_commands
        WHERE tenant_id = ? AND idempotency_key = ?
        LIMIT 1
        """,
        (identity.tenant_id, idempotency_key),
    ).fetchone()
    if existing is not None:
        if str(existing["request_hash"]) != request_hash:
            raise _error(
                status.HTTP_409_CONFLICT,
                "idempotency_conflict",
                "Этот ключ уже использован для другой операции.",
            )
        if existing["response_json"] is not None:
            return str(existing["id"]), json.loads(existing["response_json"])
        age_seconds = database.execute(
            """
            SELECT MAX(
                0,
                CAST(strftime('%s', ?) AS INTEGER)
                - CAST(strftime('%s', ?) AS INTEGER)
            )
            """,
            (now, str(existing["created_at"])),
        ).fetchone()[0]
        if (
            existing["status"] == "running"
            and isinstance(age_seconds, int)
            and age_seconds >= PRICING_COMMAND_LEASE_SECONDS
        ):
            database.execute(
                """
                UPDATE pricing_commands
                SET created_at = ?, completed_at = NULL,
                    status = 'running', response_json = NULL
                WHERE tenant_id = ? AND id = ?
                """,
                (now, identity.tenant_id, existing["id"]),
            )
            return str(existing["id"]), None
        raise _error(
            status.HTTP_409_CONFLICT,
            "pricing_command_running",
            "Обновление цен уже выполняется.",
        )
    command_id = f"pricing_command_{uuid.uuid4().hex}"
    database.execute(
        """
        INSERT INTO pricing_commands (
            tenant_id, id, idempotency_key, request_hash, command_type,
            status, response_json, created_by_user_id, created_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, 'running', NULL, ?, ?, NULL)
        """,
        (
            identity.tenant_id,
            command_id,
            idempotency_key,
            request_hash,
            command_type,
            identity.user_id,
            now,
        ),
    )
    return command_id, None


def _finish_command(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    command_id: str,
    result: dict[str, Any],
    now: str,
    failed: bool = False,
) -> None:
    database.execute(
        """
        UPDATE pricing_commands
        SET status = ?, response_json = ?, completed_at = ?
        WHERE tenant_id = ? AND id = ?
        """,
        (
            "failed" if failed else "succeeded",
            canonical_json(result),
            now,
            tenant_id,
            command_id,
        ),
    )


def _adapter(request: Request) -> FgisPriceAdapter:
    if not request.app.state.settings.fgis_pricing_enabled:
        raise PricingSourceUnavailable(
            "Источник ФГИС ЦС не разрешён в этом окружении."
        )
    configured = getattr(request.app.state, "fgis_price_adapter", None)
    if configured is not None:
        return configured
    return FgisPriceAdapter()


def _store_snapshot(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    source_type: str,
    source_uri: str,
    parser_version: str,
    source_policy_version: str,
    source_policy: dict[str, Any],
    observed_at: str,
    fetched_at: str,
    fresh_until: str,
    payload: dict[str, Any],
) -> str:
    payload_hash = sha256_json(payload)
    existing = database.execute(
        """
        SELECT id
        FROM pricing_source_snapshots
        WHERE tenant_id = ? AND source_type = ?
          AND source_uri = ? AND payload_hash = ?
        LIMIT 1
        """,
        (identity.tenant_id, source_type, source_uri, payload_hash),
    ).fetchone()
    if existing is not None:
        return str(existing["id"])
    snapshot_id = f"pricing_snapshot_{uuid.uuid4().hex}"
    database.execute(
        """
        INSERT INTO pricing_source_snapshots (
            tenant_id, id, source_type, source_uri, parser_version,
            observed_at, fetched_at, fresh_until, payload_hash, payload_json,
            created_by_user_id, source_policy_version, source_policy_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            identity.tenant_id,
            snapshot_id,
            source_type,
            source_uri,
            parser_version,
            observed_at,
            fetched_at,
            fresh_until,
            payload_hash,
            canonical_json(payload),
            identity.user_id,
            source_policy_version,
            canonical_json(source_policy),
        ),
    )
    return snapshot_id


def _store_fgis_quote(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    match: FgisMatch,
    now: str,
) -> str:
    snapshot_id = _store_snapshot(
        database,
        identity=identity,
        source_type="fgis_cs",
        source_uri=match.source_uri,
        parser_version=PARSER_VERSION,
        source_policy_version=FGIS_SOURCE_POLICY_VERSION,
        source_policy=dict(FGIS_SOURCE_POLICY),
        observed_at=match.context.price_date.isoformat(),
        fetched_at=match.fetched_at.isoformat(),
        fresh_until=match.context.fresh_until.isoformat(),
        payload=dict(match.payload),
    )
    existing = database.execute(
        """
        SELECT id
        FROM pricing_quotes
        WHERE tenant_id = ? AND snapshot_id = ?
          AND material_code = ? AND region = ? AND period_label = ?
        LIMIT 1
        """,
        (
            identity.tenant_id,
            snapshot_id,
            match.candidate.code,
            match.context.subject_name,
            match.context.period_label,
        ),
    ).fetchone()
    if existing is not None:
        return str(existing["id"])
    quote_id = f"price_quote_{uuid.uuid4().hex}"
    database.execute(
        """
        INSERT INTO pricing_quotes (
            tenant_id, id, snapshot_id, quote_type, binding_status,
            supplier_name, source_reference, region, price_zone,
            period_label, price_date, valid_until, material_code,
            material_name, unit, unit_price_rub, delivery_per_unit_rub,
            landed_unit_price_rub, tax_status, availability,
            lead_time_days, created_at
        ) VALUES (
            ?, ?, ?, 'official_indicative', 'indicative',
            NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '0.00', ?,
            'unknown', 'unknown', NULL, ?
        )
        """,
        (
            identity.tenant_id,
            quote_id,
            snapshot_id,
            match.candidate.code,
            match.context.subject_name,
            match.context.price_zone_name,
            match.context.period_label,
            match.context.price_date.isoformat(),
            match.context.fresh_until.isoformat(),
            match.candidate.code,
            match.candidate.name,
            match.candidate.unit,
            money(match.candidate.unit_price),
            money(match.candidate.unit_price),
            now,
        ),
    )
    return quote_id


def _insert_price_link(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    project_id: str,
    document_id: str,
    estimate_version: int,
    row_id: str,
    quote_id: str,
    applied_price: str,
    now: str,
) -> None:
    database.execute(
        """
        INSERT INTO estimate_price_links (
            tenant_id, id, project_id, document_id, estimate_version,
            row_id, quote_id, applied_unit_price_rub,
            linked_by_user_id, linked_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            identity.tenant_id,
            f"estimate_price_link_{uuid.uuid4().hex}",
            project_id,
            document_id,
            estimate_version,
            row_id,
            quote_id,
            applied_price,
            identity.user_id,
            now,
        ),
    )


def _persist_priced_version(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    project_id: str,
    slot: sqlite3.Row,
    current_document: dict[str, Any],
    evidence_by_row: dict[str, dict[str, Any]],
    quote_ids_by_row: dict[str, str],
    observation_source: ObservationSource,
    now: str,
) -> dict[str, Any]:
    document = estimate_document_with_prices(
        current_document,
        evidence_by_row=evidence_by_row,
        now=now,
    )
    next_version = int(slot["version"]) + 1
    changed = database.execute(
        """
        UPDATE document_slots
        SET version = ?, status = 'draft', content_json = ?, updated_at = ?
        WHERE tenant_id = ? AND id = ? AND version = ?
        """,
        (
            next_version,
            canonical_estimate_json(document),
            now,
            identity.tenant_id,
            slot["id"],
            int(slot["version"]),
        ),
    ).rowcount
    if changed != 1:
        raise _error(
            status.HTTP_409_CONFLICT,
            "estimate_version_conflict",
            "Смета уже изменилась. Повторите обновление цен.",
        )
    record_estimate_version(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
        document_id=str(slot["id"]),
        version=next_version,
        status="draft",
        document=document,
        origin_type="manual_edit",
        origin_run_id=None,
        created_by_user_id=identity.user_id,
        created_at=now,
    )
    record_price_observations(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
        document_id=str(slot["id"]),
        estimate_version=next_version,
        previous_document=current_document,
        document=document,
        source_type=observation_source,
        lifecycle="draft",
        created_by_user_id=identity.user_id,
        observed_at=now,
        quote_ids_by_row=quote_ids_by_row,
    )
    for row_id, quote_id in quote_ids_by_row.items():
        evidence = evidence_by_row[row_id]
        _insert_price_link(
            database,
            identity=identity,
            project_id=project_id,
            document_id=str(slot["id"]),
            estimate_version=next_version,
            row_id=row_id,
            quote_id=quote_id,
            applied_price=str(evidence["landed_unit_price"]),
            now=now,
        )
    database.execute(
        """
        UPDATE projects
        SET updated_at = ?
        WHERE tenant_id = ? AND id = ?
        """,
        (now, identity.tenant_id, project_id),
    )
    return estimate_view(
        project_id=project_id,
        document_id=str(slot["id"]),
        version=next_version,
        status="draft",
        document=document,
    )


@router.post("/{project_id}/estimate/prices/refresh")
async def refresh_estimate_prices(
    project_id: str,
    payload: PricingRefreshInput,
    request: Request,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _auth: MutationAuthDependency,
    idempotency_key: IdempotencyDependency,
) -> dict[str, Any]:
    slot = _load_slot(
        database,
        tenant_id=identity.tenant_id,
        project_id=project_id,
    )
    command_hash = _request_hash(
        {
            "command": "fgis_refresh",
            "project_id": project_id,
            "document_id": str(slot["id"]),
            "version": payload.version,
        }
    )
    claimed_at = _now(database)
    with transaction(database, immediate=True):
        command_id, replay = _claim_command(
            database,
            identity=identity,
            idempotency_key=idempotency_key,
            request_hash=command_hash,
            command_type="fgis_refresh",
            now=claimed_at,
        )
    if replay is not None:
        return replay
    if int(slot["version"]) != payload.version:
        result = {
            "status": "estimate_version_conflict",
            "message": "Смета уже изменилась. Повторите обновление цен.",
        }
        with transaction(database, immediate=True):
            _finish_command(
                database,
                tenant_id=identity.tenant_id,
                command_id=command_id,
                result=result,
                now=_now(database),
                failed=True,
            )
        raise _error(
            status.HTTP_409_CONFLICT,
            "estimate_version_conflict",
            result["message"],
        )

    document = parse_estimate_document(
        slot["content_json"],
        now=str(slot["updated_at"]),
    )
    region = document.get("region")
    if not isinstance(region, str) or not region.strip() or region == "Регион не указан":
        result = {
            "status": "estimate_region_required",
            "message": "Укажите регион сметы перед проверкой цен.",
        }
        with transaction(database, immediate=True):
            _finish_command(
                database,
                tenant_id=identity.tenant_id,
                command_id=command_id,
                result=result,
                now=_now(database),
                failed=True,
            )
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "estimate_region_required",
            result["message"],
        )

    try:
        refreshed = await _adapter(request).refresh_material_rows(
            region=region,
            rows=[
                row
                for row in document.get("rows", [])
                if isinstance(row, dict)
            ],
        )
    except PricingRegionUnresolved as exc:
        result = {
            "status": "region_unresolved",
            "message": str(exc),
            "matchedRows": 0,
            "unmatchedRows": 0,
            "estimate": estimate_view(
                project_id=project_id,
                document_id=str(slot["id"]),
                version=int(slot["version"]),
                status=str(slot["status"]),
                document=document,
            ),
        }
        with transaction(database, immediate=True):
            _finish_command(
                database,
                tenant_id=identity.tenant_id,
                command_id=command_id,
                result=result,
                now=_now(database),
                failed=True,
            )
        return result
    except (PricingSourceUnavailable, PricingSourceProtocolError) as exc:
        result = {
            "status": "source_unavailable",
            "message": str(exc),
            "matchedRows": 0,
            "unmatchedRows": 0,
            "estimate": estimate_view(
                project_id=project_id,
                document_id=str(slot["id"]),
                version=int(slot["version"]),
                status=str(slot["status"]),
                document=document,
            ),
        }
        with transaction(database, immediate=True):
            _finish_command(
                database,
                tenant_id=identity.tenant_id,
                command_id=command_id,
                result=result,
                now=_now(database),
                failed=True,
            )
        return result
    except PricingSourceError as exc:
        result = {
            "status": "source_failed",
            "message": str(exc),
            "matchedRows": 0,
            "unmatchedRows": 0,
        }
        with transaction(database, immediate=True):
            _finish_command(
                database,
                tenant_id=identity.tenant_id,
                command_id=command_id,
                result=result,
                now=_now(database),
                failed=True,
            )
        raise _error(
            status.HTTP_502_BAD_GATEWAY,
            "pricing_source_failed",
            str(exc),
        ) from exc
    except Exception as exc:
        result = {
            "status": "source_failed",
            "message": "Источник цен завершился с внутренней ошибкой.",
            "matchedRows": 0,
            "unmatchedRows": 0,
        }
        with transaction(database, immediate=True):
            _finish_command(
                database,
                tenant_id=identity.tenant_id,
                command_id=command_id,
                result=result,
                now=_now(database),
                failed=True,
            )
        raise _error(
            status.HTTP_502_BAD_GATEWAY,
            "pricing_source_failed",
            result["message"],
        ) from exc

    with transaction(database, immediate=True):
        current_slot = _load_slot(
            database,
            tenant_id=identity.tenant_id,
            project_id=project_id,
        )
        if int(current_slot["version"]) != int(slot["version"]):
            result = {
                "status": "estimate_version_conflict",
                "message": (
                    "Смета изменилась во время проверки цен. "
                    "Повторите обновление."
                ),
            }
            _finish_command(
                database,
                tenant_id=identity.tenant_id,
                command_id=command_id,
                result=result,
                now=_now(database),
                failed=True,
            )
            # This branch only persists the terminal command state. Committing
            # before raising prevents an idempotency key from remaining
            # permanently leased after a mid-flight estimate edit.
            database.commit()
            raise _error(
                status.HTTP_409_CONFLICT,
                "estimate_version_conflict",
                result["message"],
            )
        now = _now(database)
        evidence_by_row: dict[str, dict[str, Any]] = {}
        quote_ids_by_row: dict[str, str] = {}
        stale_rows = 0
        today = date.today()
        for match in refreshed.matches:
            if match.context.fresh_until < today:
                stale_rows += 1
                continue
            quote_id = _store_fgis_quote(
                database,
                identity=identity,
                match=match,
                now=now,
            )
            evidence_by_row[match.row_id] = fgis_price_evidence(
                match,
                quote_id=quote_id,
                today=today,
            )
            quote_ids_by_row[match.row_id] = quote_id
        if evidence_by_row:
            estimate = _persist_priced_version(
                database,
                identity=identity,
                project_id=project_id,
                slot=current_slot,
                current_document=document,
                evidence_by_row=evidence_by_row,
                quote_ids_by_row=quote_ids_by_row,
                observation_source="official_reference",
                now=now,
            )
            result_status = (
                "official_reference"
                if not refreshed.unmatched_row_ids and not stale_rows
                else "partial_official_reference"
            )
            message = (
                f"ФГИС ЦС: найден официальный ориентир для "
                f"{len(evidence_by_row)} позиций; "
                f"без однозначного совпадения — {len(refreshed.unmatched_row_ids)}; "
                f"устаревших — {stale_rows}."
            )
        elif stale_rows:
            estimate = estimate_view(
                project_id=project_id,
                document_id=str(current_slot["id"]),
                version=int(current_slot["version"]),
                status=str(current_slot["status"]),
                document=document,
            )
            result_status = "stale_source"
            message = (
                "Последняя публикация ФГИС ЦС устарела для применения. "
                "Смета не изменена."
            )
        else:
            estimate = estimate_view(
                project_id=project_id,
                document_id=str(current_slot["id"]),
                version=int(current_slot["version"]),
                status=str(current_slot["status"]),
                document=document,
            )
            result_status = "no_matches"
            message = (
                "ФГИС ЦС доступна, но для строк сметы не найдено "
                "однозначных совпадений по материалу и единице."
            )
        result = {
            "status": result_status,
            "message": message,
            "matchedRows": len(evidence_by_row),
            "unmatchedRows": len(refreshed.unmatched_row_ids),
            "staleRows": stale_rows,
            "source": {
                "type": "fgis_cs",
                "label": "ФГИС ЦС",
                "url": FGIS_PUBLIC_PRICES_URL,
                "region": refreshed.context.subject_name,
                "priceZone": refreshed.context.price_zone_name,
                "period": refreshed.context.period_label,
                "priceDate": refreshed.context.price_date.isoformat(),
                "freshUntil": refreshed.context.fresh_until.isoformat(),
                "policyVersion": FGIS_SOURCE_POLICY_VERSION,
            },
            "estimate": estimate,
        }
        _finish_command(
            database,
            tenant_id=identity.tenant_id,
            command_id=command_id,
            result=result,
            now=now,
        )
    return result


@router.post("/{project_id}/estimate/prices/supplier-offers", status_code=201)
def attach_supplier_offer(
    project_id: str,
    payload: SupplierOfferInput,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _auth: MutationAuthDependency,
    idempotency_key: IdempotencyDependency,
) -> dict[str, Any]:
    with transaction(database, immediate=True):
        slot = _load_slot(
            database,
            tenant_id=identity.tenant_id,
            project_id=project_id,
        )
        command_hash = _request_hash(
            {
                "command": "supplier_offer",
                "project_id": project_id,
                "document_id": str(slot["id"]),
                "version": payload.version,
                "payload": payload.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=False,
                ),
            }
        )
        now = _now(database)
        command_id, replay = _claim_command(
            database,
            identity=identity,
            idempotency_key=idempotency_key,
            request_hash=command_hash,
            command_type="supplier_offer",
            now=now,
        )
        if replay is not None:
            return replay
        if int(slot["version"]) != payload.version:
            result = {
                "status": "estimate_version_conflict",
                "message": (
                    "Смета уже изменилась. Обновите её перед добавлением "
                    "предложения."
                ),
            }
            _finish_command(
                database,
                tenant_id=identity.tenant_id,
                command_id=command_id,
                result=result,
                now=now,
                failed=True,
            )
            raise _error(
                status.HTTP_409_CONFLICT,
                "estimate_version_conflict",
                result["message"],
            )
        document = parse_estimate_document(
            slot["content_json"],
            now=str(slot["updated_at"]),
        )
        row = next(
            (
                item
                for item in document.get("rows", [])
                if isinstance(item, dict) and item.get("id") == payload.row_id
            ),
            None,
        )
        if row is None:
            raise _error(
                status.HTTP_404_NOT_FOUND,
                "estimate_row_not_found",
                "Строка сметы не найдена.",
            )
        today = date.today()
        effective_valid_until = payload.valid_until or (
            payload.observed_on
            + (date.resolution * 30)
        )
        if payload.observed_on > today:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "supplier_offer_future",
                "Дата предложения не может быть в будущем.",
            )
        if effective_valid_until < today:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "supplier_offer_stale",
                "Срок действия предложения уже истёк.",
            )
        if payload.availability == "unavailable":
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "supplier_offer_unavailable",
                "Недоступное предложение нельзя применить к смете.",
            )
        raw_payload = payload.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=False,
        )
        snapshot_hash = sha256_json(raw_payload)
        snapshot_id = _store_snapshot(
            database,
            identity=identity,
            source_type="supplier_offer",
            source_uri=str(payload.source_url),
            parser_version="user_attested_supplier_offer_v1",
            source_policy_version=SUPPLIER_SOURCE_POLICY_VERSION,
            source_policy=dict(SUPPLIER_SOURCE_POLICY),
            observed_at=payload.observed_on.isoformat(),
            fetched_at=now,
            fresh_until=effective_valid_until.isoformat(),
            payload=raw_payload,
        )
        quote_id = f"price_quote_{uuid.uuid4().hex}"
        evidence = supplier_price_evidence(
            payload,
            quote_id=quote_id,
            snapshot_hash=snapshot_hash,
            region=str(document.get("region") or "Регион не указан"),
            unit=str(row.get("unit") or ""),
            now=today,
        )
        database.execute(
            """
            INSERT INTO pricing_quotes (
                tenant_id, id, snapshot_id, quote_type, binding_status,
                supplier_name, source_reference, region, price_zone,
                period_label, price_date, valid_until, material_code,
                material_name, unit, unit_price_rub, delivery_per_unit_rub,
                landed_unit_price_rub, tax_status, availability,
                lead_time_days, created_at
            ) VALUES (
                ?, ?, ?, 'supplier_offer', ?, ?, ?, ?, NULL,
                NULL, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                identity.tenant_id,
                quote_id,
                snapshot_id,
                evidence["binding_status"],
                payload.supplier_name,
                payload.quote_reference,
                evidence["region"],
                evidence["price_date"],
                evidence["fresh_until"],
                str(row.get("description") or ""),
                str(row.get("unit") or ""),
                evidence["unit_price"],
                evidence["delivery_per_unit"],
                evidence["landed_unit_price"],
                evidence["tax_status"],
                evidence["availability"],
                evidence["lead_time_days"],
                now,
            ),
        )
        estimate = _persist_priced_version(
            database,
            identity=identity,
            project_id=project_id,
            slot=slot,
            current_document=document,
            evidence_by_row={payload.row_id: evidence},
            quote_ids_by_row={payload.row_id: quote_id},
            observation_source="supplier_offer",
            now=now,
        )
        result = {
            "status": "supplier_offer_attached",
            "message": (
                "Предложение поставщика прикреплено к строке и сохранено "
                "в новой версии сметы."
            ),
            "quoteId": quote_id,
            "estimate": estimate,
        }
        _finish_command(
            database,
            tenant_id=identity.tenant_id,
            command_id=command_id,
            result=result,
            now=now,
        )
        return result
