from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .database import get_database, transaction
from .estimate_artifact import (
    EstimateRowInput,
    canonical_estimate_json,
    estimate_view,
    load_estimate_slot,
    normalize_estimate_document,
    parse_estimate_document,
    record_estimate_version,
)
from .estimate_engine import (
    ENGINE_VERSION,
    PLASTER_RULES_VERSION,
    CommercialTerms,
    EstimateEngineError,
    PlasteringScope,
    PriceQuote,
    PriceSource,
    ProjectCaseRef,
    calculate_plastering_estimate,
    canonical_json,
    content_hash,
)
from .product_access import ConstructionEstimateAccessDependency
from .runtime_skills import (
    RuntimeSkillError,
    load_runtime_skill_plan,
    skill_plan_evidence,
)
from .schemas import UserSession
from .security import require_mutation_auth

router = APIRouter(prefix="/v1/projects", tags=["estimate-engine"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = ConstructionEstimateAccessDependency
MutationAuthDependency = Annotated[None, Depends(require_mutation_auth)]
IdempotencyDependency = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=16, max_length=128),
]
DECIMAL_TEXT = re.compile(r"^(?:0|[1-9]\d{0,11})(?:\.\d{1,6})?$")
PROJECT_ID = re.compile(r"^project_[A-Za-z0-9._~-]{8,96}$")
RUN_ID = re.compile(r"^run_[A-Za-z0-9._~-]{8,96}$")


class ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


DecimalText = Annotated[
    str,
    StringConstraints(pattern=DECIMAL_TEXT.pattern, min_length=1, max_length=32),
]
NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
]


class PlasteringScopeInput(ContractModel):
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


class PriceSourceInput(ContractModel):
    source_id: NonEmptyText = Field(alias="sourceId")
    source_type: Literal[
        "regional_catalog",
        "supplier_offer",
        "organization_price",
        "user_price",
        "ai_candidate",
    ] = Field(alias="sourceType")
    label: NonEmptyText
    reference: NonEmptyText
    url: str = Field(min_length=9, max_length=2048)
    region: str = Field(min_length=1, max_length=160)
    observed_at: str = Field(alias="observedAt", min_length=10, max_length=64)
    valid_until: str | None = Field(
        default=None,
        alias="validUntil",
        min_length=10,
        max_length=32,
    )
    verified: bool


class PriceQuoteInput(ContractModel):
    item_code: str = Field(alias="itemCode", min_length=1, max_length=120)
    unit: str = Field(min_length=1, max_length=32)
    unit_price: DecimalText = Field(alias="unitPrice")
    currency: Literal["RUB"] = "RUB"
    vat_mode: Literal[
        "included",
        "excluded",
        "not_applicable",
        "unknown",
    ] = Field(alias="vatMode")
    confidence: DecimalText
    source: PriceSourceInput


class CommercialTermsInput(ContractModel):
    overhead_percent: DecimalText = Field(
        default="0",
        alias="overheadPercent",
    )
    profit_percent: DecimalText = Field(default="0", alias="profitPercent")
    discount_percent: DecimalText = Field(
        default="0",
        alias="discountPercent",
    )
    tax_percent: DecimalText = Field(default="0", alias="taxPercent")


class PlasteringCalculationInput(ContractModel):
    expected_estimate_version: int = Field(
        alias="expectedEstimateVersion",
        ge=1,
    )
    region: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=240)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    scope: PlasteringScopeInput
    prices: list[PriceQuoteInput] = Field(max_length=200)
    terms: CommercialTermsInput = Field(default_factory=CommercialTermsInput)
    source_message_id: str | None = Field(
        default=None,
        alias="sourceMessageId",
        pattern=r"^message_[A-Za-z0-9._~-]{8,96}$",
    )
    source_run_id: str | None = Field(
        default=None,
        alias="sourceRunId",
        pattern=RUN_ID.pattern,
    )
    require_release_ready: bool = Field(
        default=False,
        alias="requireReleaseReady",
    )


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


def _request_hash(payload: PlasteringCalculationInput) -> str:
    return content_hash(payload.model_dump(by_alias=True, mode="json"))


def _key_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "strict")).hexdigest()


def _case_id(database: sqlite3.Connection, tenant_id: str, project_id: str) -> str:
    runtime = database.execute(
        """
        SELECT case_id
        FROM product_project_runtime
        WHERE tenant_id = ? AND project_id = ?
        LIMIT 1
        """,
        (tenant_id, project_id),
    ).fetchone()
    if runtime is not None and str(runtime["case_id"]).strip():
        return str(runtime["case_id"])
    digest = hashlib.sha256(
        f"{tenant_id}:{project_id}".encode("utf-8", "strict")
    ).hexdigest()[:24]
    return f"case_{digest}"


def _source(value: PriceSourceInput) -> PriceSource:
    return PriceSource(
        source_id=value.source_id,
        source_type=value.source_type,
        label=value.label,
        reference=value.reference,
        url=value.url,
        region=value.region,
        observed_at=value.observed_at,
        valid_until=value.valid_until,
        verified=value.verified,
    )


def _scope(value: PlasteringScopeInput) -> PlasteringScope:
    return PlasteringScope(
        wall_area_m2=Decimal(value.wall_area_m2),
        average_thickness_mm=Decimal(value.average_thickness_mm),
        material=value.material,
        application_method=value.application_method,
        waste_percent=Decimal(value.waste_percent),
        protection_area_m2=Decimal(value.protection_area_m2),
        wall_height_m=Decimal(value.wall_height_m),
        beacon_spacing_m=Decimal(value.beacon_spacing_m),
        corner_length_m=Decimal(value.corner_length_m),
        mesh_area_percent=Decimal(value.mesh_area_percent),
        slopes_area_m2=Decimal(value.slopes_area_m2),
        plaster_bag_weight_kg=Decimal(value.plaster_bag_weight_kg),
        primer_passes=value.primer_passes,
        waste_removal_trips=Decimal(value.waste_removal_trips),
    )


def _terms(value: CommercialTermsInput) -> CommercialTerms:
    return CommercialTerms(
        overhead_percent=Decimal(value.overhead_percent),
        profit_percent=Decimal(value.profit_percent),
        discount_percent=Decimal(value.discount_percent),
        tax_percent=Decimal(value.tax_percent),
    )


def _quotes(values: list[PriceQuoteInput]) -> list[PriceQuote]:
    return [
        PriceQuote(
            item_code=value.item_code,
            unit=value.unit,
            unit_price=Decimal(value.unit_price),
            currency=value.currency,
            vat_mode=value.vat_mode,
            confidence=Decimal(value.confidence),
            source=_source(value.source),
        )
        for value in values
    ]


def _project_snapshot(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    project_id: str,
    case_id: str,
    case_version: int,
    payload: PlasteringCalculationInput,
) -> dict[str, Any]:
    project = database.execute(
        """
        SELECT title, status, primary_thread_id
        FROM projects
        WHERE tenant_id = ? AND id = ?
        LIMIT 1
        """,
        (identity.tenant_id, project_id),
    ).fetchone()
    if project is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "project_not_found",
            "Проект не найден.",
        )
    construction_object = database.execute(
        """
        SELECT id, name, name_source
        FROM construction_objects
        WHERE tenant_id = ? AND project_id = ?
        LIMIT 1
        """,
        (identity.tenant_id, project_id),
    ).fetchone()
    runtime_skill_evidence: dict[str, object] | None = None
    source_run_id: str | None = None
    if payload.source_run_id is not None and payload.source_message_id is None:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "source_run_invalid",
            "Исходный запуск требует исходное сообщение проекта.",
        )
    if payload.source_message_id is not None:
        source_message = database.execute(
            """
            SELECT 1
            FROM chat_messages
            WHERE tenant_id = ? AND project_id = ? AND id = ?
            LIMIT 1
            """,
            (
                identity.tenant_id,
                project_id,
                payload.source_message_id,
            ),
        ).fetchone()
        if source_message is None:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "source_message_invalid",
                "Исходное сообщение не относится к проекту.",
            )
        if payload.source_run_id is not None:
            run = database.execute(
                """
                SELECT id, input_message_id
                FROM chat_runs
                WHERE tenant_id = ? AND project_id = ? AND id = ?
                LIMIT 1
                """,
                (
                    identity.tenant_id,
                    project_id,
                    payload.source_run_id,
                ),
            ).fetchone()
            if (
                run is None
                or str(run["input_message_id"]) != payload.source_message_id
            ):
                raise _error(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "source_run_invalid",
                    "Исходный запуск не относится к сообщению проекта.",
                )
        else:
            # The public calculate endpoint can be called outside the chat.
            # Do not guess provenance when a user intentionally reuses the
            # same message in several runs; product chat always supplies the
            # exact sourceRunId below.
            matching_runs = database.execute(
                """
                SELECT id, input_message_id
                FROM chat_runs
                WHERE tenant_id = ?
                  AND project_id = ?
                  AND input_message_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 2
                """,
                (
                    identity.tenant_id,
                    project_id,
                    payload.source_message_id,
                ),
            ).fetchall()
            run = matching_runs[0] if len(matching_runs) == 1 else None
        if run is not None:
            source_run_id = str(run["id"])
            try:
                skill_plan = load_runtime_skill_plan(
                    database,
                    tenant_id=identity.tenant_id,
                    run_id=source_run_id,
                )
            except RuntimeSkillError as exc:
                raise _error(
                    status.HTTP_409_CONFLICT,
                    "runtime_skill_context_invalid",
                    "Контекст навыков сметного запуска повреждён.",
                ) from exc
            if skill_plan is not None:
                runtime_skill_evidence = skill_plan_evidence(skill_plan)
    return {
        "schemaId": "kolibri.project_case",
        "schemaVersion": "1.0",
        "tenantId": identity.tenant_id,
        "projectId": project_id,
        "caseId": case_id,
        "version": case_version,
        "region": payload.region,
        "project": {
            "title": str(project["title"]),
            "status": str(project["status"]),
            "primaryThreadId": str(project["primary_thread_id"]),
        },
        "object": (
            {
                "id": str(construction_object["id"]),
                "name": str(construction_object["name"]),
                "nameSource": str(construction_object["name_source"]),
            }
            if construction_object is not None
            else None
        ),
        "scope": payload.scope.model_dump(by_alias=True, mode="json"),
        "priceSnapshot": [
            quote.model_dump(by_alias=True, mode="json")
            for quote in sorted(payload.prices, key=lambda item: item.item_code)
        ],
        "commercialTerms": payload.terms.model_dump(
            by_alias=True,
            mode="json",
        ),
        "assumptions": payload.assumptions,
        "sourceMessageId": payload.source_message_id,
        "sourceRunId": source_run_id,
        "runtimeSkillPlan": runtime_skill_evidence,
    }


_UNIT_LABELS = {
    "m": "м",
    "m2": "м²",
    "kg": "кг",
    "t": "т",
    "l": "л",
    "m3": "м³",
    "kWh": "кВт·ч",
    "ea": "шт.",
    "bag": "мешок",
    "shift": "смена",
    "trip": "рейс",
    "set": "комплект",
}


def _estimate_document(
    *,
    payload: PlasteringCalculationInput,
    result: dict[str, Any],
    calculation_id: str,
    now: str,
) -> dict[str, Any]:
    rows: list[EstimateRowInput] = []
    price_provenance: dict[str, dict[str, Any]] = {}
    for item in result["items"]:
        source = item["source"]
        price_basis = "Цена отсутствует; выпуск документов заблокирован."
        if isinstance(source, dict):
            price_basis = (
                f"{source['label']} · {source['region']} · "
                f"{source['observedAt']} · НДС: {item['vatMode']}"
            )[:500]
            price_provenance[str(item["id"])] = {
                **{
                    key: value
                    for key, value in source.items()
                    if key != "url"
                },
                "sourceUrl": source["url"],
                "itemCode": item["code"],
                "unitPrice": item["unitPrice"],
                "currency": item["currency"],
                "vatMode": item["vatMode"],
                "confidence": item["confidence"],
            }
        rows.append(
            EstimateRowInput(
                id=str(item["id"]),
                section=str(item["section"]),
                kind=str(item["kind"]),
                description=str(item["title"]),
                unit=_UNIT_LABELS.get(str(item["unit"]), str(item["unit"])),
                quantity=str(item["normalizedQuantity"]),
                unitPrice=str(item["unitPrice"] or "0.00"),
                quantityBasis=(
                    f"{item['explanation']} Формула: "
                    f"{canonical_json(item['quantityFormula'])}"
                )[:500],
                priceBasis=price_basis,
            )
        )
    document = normalize_estimate_document(
        title=payload.title,
        currency="RUB",
        rows=rows,
        now=now,
        region=payload.region,
        assumptions=(
            payload.assumptions
            + [
                decision["reason"]
                for decision in result["technologyCard"]["decisions"]
            ]
        )[:20],
        generation={
            "provider_profile": "estimate-engine",
            "run_id": calculation_id,
        },
        pricing_checked_at=now,
    )
    missing = set(result["validation"]["missingPriceItemCodes"])
    unverified = set(result["validation"].get("unverifiedPriceItemCodes", []))
    sourced = len(rows) - len(missing) - len(unverified)
    document["pricing"] = {
        "status": (
            "sourced"
            if not missing and not unverified
            else ("partially_sourced" if sourced else "unpriced")
        ),
        "sourced_rows": sourced,
        "stale_rows": 0,
        "total_rows": len(rows),
        "last_checked_at": now,
    }
    for row in document["rows"]:
        provenance = price_provenance.get(str(row["id"]))
        if provenance is not None:
            row["engine_price_provenance"] = provenance
    document["calculation"] = {
        "id": calculation_id,
        "engineVersion": result["engineVersion"],
        "rulesVersion": result["rulesVersion"],
        "inputHash": result["inputHash"],
        "resultHash": result["resultHash"],
        "status": result["validation"]["status"],
    }
    return document


def _response_for_calculation(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    calculation_id: str,
    replayed: bool,
) -> dict[str, Any]:
    row = database.execute(
        """
        SELECT calculations.project_id, calculations.project_case_id,
               calculations.project_case_version,
               calculations.technology_card_id,
               calculations.document_id, calculations.estimate_version,
               calculations.result_json, versions.status AS estimate_status,
               versions.content_json AS estimate_json,
               versions.created_at AS estimate_created_at
        FROM estimate_calculations AS calculations
        LEFT JOIN estimate_versions AS versions
          ON versions.tenant_id = calculations.tenant_id
         AND versions.document_id = calculations.document_id
         AND versions.version = calculations.estimate_version
        WHERE calculations.tenant_id = ? AND calculations.id = ?
        LIMIT 1
        """,
        (tenant_id, calculation_id),
    ).fetchone()
    if row is None:
        raise _error(
            status.HTTP_409_CONFLICT,
            "idempotency_result_missing",
            "Результат повторной команды недоступен.",
        )
    result = json.loads(str(row["result_json"]))
    document = parse_estimate_document(
        row["estimate_json"],
        now=str(row["estimate_created_at"] or ""),
    )
    return {
        "calculationId": calculation_id,
        "projectCaseId": str(row["project_case_id"]),
        "projectCaseVersion": int(row["project_case_version"]),
        "technologyCardId": str(row["technology_card_id"]),
        "estimateVersion": int(row["estimate_version"]),
        "replayed": replayed,
        "result": result,
        "estimate": estimate_view(
            project_id=str(row["project_id"]),
            document_id=str(row["document_id"]),
            version=int(row["estimate_version"]),
            status=str(row["estimate_status"]),
            document=document,
        ),
    }


@router.post(
    "/{project_id}/estimate/calculations/plastering",
    status_code=status.HTTP_201_CREATED,
)
def calculate_plastering(
    project_id: str,
    payload: PlasteringCalculationInput,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _auth: MutationAuthDependency,
    idempotency_key: IdempotencyDependency,
) -> dict[str, Any]:
    if not PROJECT_ID.fullmatch(project_id):
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "project_not_found",
            "Проект не найден.",
        )
    operation = f"estimate.calculate.plastering:{project_id}"
    request_hash = _request_hash(payload)
    key_hash = _key_hash(idempotency_key)
    with transaction(database, immediate=True):
        previous = database.execute(
            """
            SELECT request_hash, result_id
            FROM api_command_idempotency
            WHERE tenant_id = ? AND operation = ? AND key_hash = ?
            LIMIT 1
            """,
            (identity.tenant_id, operation, key_hash),
        ).fetchone()
        if previous is not None:
            if str(previous["request_hash"]) != request_hash:
                raise _error(
                    status.HTTP_409_CONFLICT,
                    "idempotency_conflict",
                    "Этот ключ уже использован для другого входа.",
                )
            return _response_for_calculation(
                database,
                tenant_id=identity.tenant_id,
                calculation_id=str(previous["result_id"]),
                replayed=True,
            )

        slot = load_estimate_slot(
            database,
            tenant_id=identity.tenant_id,
            project_id=project_id,
        )
        if slot is None:
            raise _error(
                status.HTTP_404_NOT_FOUND,
                "estimate_not_found",
                "Смета проекта не найдена.",
            )
        if int(slot["version"]) != payload.expected_estimate_version:
            raise _error(
                status.HTTP_409_CONFLICT,
                "estimate_version_conflict",
                "Смета уже изменилась. Обновите данные перед расчётом.",
            )
        case_id = _case_id(database, identity.tenant_id, project_id)
        case_version = int(
            database.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1
                FROM project_cases
                WHERE tenant_id = ? AND project_id = ?
                """,
                (identity.tenant_id, project_id),
            ).fetchone()[0]
        )
        snapshot = _project_snapshot(
            database,
            identity=identity,
            project_id=project_id,
            case_id=case_id,
            case_version=case_version,
            payload=payload,
        )
        calculation_id = f"calculation_{uuid.uuid4().hex}"
        technology_card_id = f"technology_card_{uuid.uuid4().hex}"
        try:
            result = calculate_plastering_estimate(
                project_case=ProjectCaseRef(
                    tenant_id=identity.tenant_id,
                    project_id=project_id,
                    case_id=case_id,
                    version=case_version,
                    region=payload.region,
                ),
                scope=_scope(payload.scope),
                prices=_quotes(payload.prices),
                terms=_terms(payload.terms),
                require_complete_prices=payload.require_release_ready,
            )
        except EstimateEngineError as exc:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "estimate_calculation_invalid",
                str(exc),
            ) from exc
        now = _now(database)
        technology_card = result["technologyCard"]
        database.execute(
            """
            INSERT INTO project_cases (
                tenant_id, id, project_id, version, status, region,
                snapshot_json, content_hash, source_message_id,
                created_by_user_id, created_at
            ) VALUES (?, ?, ?, ?, 'ready', ?, ?, ?, ?, ?, ?)
            """,
            (
                identity.tenant_id,
                case_id,
                project_id,
                case_version,
                payload.region,
                canonical_json(snapshot),
                content_hash(snapshot),
                payload.source_message_id,
                identity.user_id,
                now,
            ),
        )
        database.execute(
            """
            INSERT INTO technology_cards (
                tenant_id, id, project_id, project_case_id,
                project_case_version, rules_version, status,
                content_json, content_hash, created_by_user_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'ready', ?, ?, ?, ?)
            """,
            (
                identity.tenant_id,
                technology_card_id,
                project_id,
                case_id,
                case_version,
                PLASTER_RULES_VERSION,
                canonical_json(technology_card),
                content_hash(technology_card),
                identity.user_id,
                now,
            ),
        )
        current = parse_estimate_document(
            slot["content_json"],
            now=str(slot["updated_at"]),
        )
        estimate_version = (
            int(slot["version"]) + 1
            if current["rows"]
            else int(slot["version"])
        )
        document = _estimate_document(
            payload=payload,
            result=result,
            calculation_id=calculation_id,
            now=now,
        )
        updated = database.execute(
            """
            UPDATE document_slots
            SET version = ?, status = 'draft', content_json = ?, updated_at = ?
            WHERE tenant_id = ? AND id = ? AND version = ?
            """,
            (
                estimate_version,
                canonical_estimate_json(document),
                now,
                identity.tenant_id,
                slot["id"],
                payload.expected_estimate_version,
            ),
        )
        if updated.rowcount != 1:
            raise _error(
                status.HTTP_409_CONFLICT,
                "estimate_version_conflict",
                "Смета уже изменилась. Обновите данные перед расчётом.",
            )
        record_estimate_version(
            database,
            tenant_id=identity.tenant_id,
            project_id=project_id,
            document_id=str(slot["id"]),
            version=estimate_version,
            status="draft",
            document=document,
            origin_type="engine_calculation",
            origin_run_id=(
                str(snapshot["sourceRunId"])
                if snapshot["sourceRunId"] is not None
                else None
            ),
            created_by_user_id=identity.user_id,
            created_at=now,
        )
        database.execute(
            """
            INSERT INTO estimate_calculations (
                tenant_id, id, project_id, project_case_id,
                project_case_version, technology_card_id, document_id,
                estimate_version, engine_version, rules_version, status,
                input_hash, result_hash, result_json,
                created_by_user_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity.tenant_id,
                calculation_id,
                project_id,
                case_id,
                case_version,
                technology_card_id,
                slot["id"],
                estimate_version,
                ENGINE_VERSION,
                PLASTER_RULES_VERSION,
                (
                    "complete"
                    if result["validation"]["status"] == "passed"
                    else "blocked"
                ),
                result["inputHash"],
                result["resultHash"],
                canonical_json(result),
                identity.user_id,
                now,
            ),
        )
        database.execute(
            """
            INSERT INTO api_command_idempotency (
                tenant_id, operation, key_hash, request_hash,
                result_type, result_id, created_by_user_id, created_at
            ) VALUES (?, ?, ?, ?, 'estimate_calculation', ?, ?, ?)
            """,
            (
                identity.tenant_id,
                operation,
                key_hash,
                request_hash,
                calculation_id,
                identity.user_id,
                now,
            ),
        )
        database.execute(
            """
            INSERT INTO audit_events (
                tenant_id, id, actor_user_id, action, subject_type,
                subject_id, project_id, metadata_json, created_at
            ) VALUES (?, ?, ?, 'estimate.calculated',
                      'estimate_calculation', ?, ?, ?, ?)
            """,
            (
                identity.tenant_id,
                f"audit_{uuid.uuid4().hex}",
                identity.user_id,
                calculation_id,
                project_id,
                canonical_json(
                    {
                        "projectCaseId": case_id,
                        "projectCaseVersion": case_version,
                        "estimateVersion": estimate_version,
                        "inputHash": result["inputHash"],
                        "resultHash": result["resultHash"],
                        "validationStatus": result["validation"]["status"],
                    }
                ),
                now,
            ),
        )
        database.execute(
            """
            UPDATE projects
            SET updated_at = ?
            WHERE tenant_id = ? AND id = ?
            """,
            (now, identity.tenant_id, project_id),
        )
        response = _response_for_calculation(
            database,
            tenant_id=identity.tenant_id,
            calculation_id=calculation_id,
            replayed=False,
        )
    return response
