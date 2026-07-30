from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import HTTPException
from pydantic import ValidationError

from .config import Settings
from .database import connect_database, transaction
from .estimate_artifact import (
    GeneratedEstimateProposal,
    canonical_estimate_json,
    estimate_document_from_proposal,
    estimate_view,
    load_estimate_slot,
    parse_estimate_document,
    record_estimate_version,
)
from .estimate_engine import (
    PlasteringScope,
    ProjectCaseRef,
    calculate_plastering_estimate,
)
from .estimate_engine_router import (
    PlasteringCalculationInput,
    calculate_plastering,
)
from .estimate_intake import PlasteringIntake
from .market_pricing import record_price_observations
from .product_entitlements import (
    CONSTRUCTION_ESTIMATES_ENTITLEMENT,
    ProductEntitlementError,
    require_persisted_product_entitlement,
)
from .reference_price_snapshot import (
    PLASTERING_REFERENCE_PRICE_SNAPSHOT_VERSION,
    plastering_reference_price_assumption,
    plastering_reference_price_quotes,
    verify_plastering_model_price_candidates,
)
from .schemas import AgentProfile, UserRole, UserSession


class WidgetRunLike(Protocol):
    tenant_id: str
    project_id: str
    run_id: str
    public_run_id: str


@dataclass(frozen=True, slots=True)
class ProductWidget:
    arguments: dict[str, Any]
    fallback_text: str
    tool_name: str = "present"
    tool_result: dict[str, Any] | None = None


ESTIMATE_WORDS = re.compile(r"\b(?:смет\w*|estimate)\b", re.IGNORECASE)
ESTIMATE_GENERATION_WORDS = re.compile(
    r"\b(?:состав\w*|подготов\w*|собер\w*|рассчит\w*|сдела\w*|"
    r"созда\w*|сформир\w*|постро\w*|оцен\w*)\b",
    re.IGNORECASE,
)
ESTIMATE_SCOPE_QUANTITY = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*"
    r"(?:м(?:²|³|2|3)|кг|т|шт\.?|пог\.?\s*м)"
    r"(?=\s|[,.;:)]|$)",
    re.IGNORECASE,
)
ESTIMATE_SCOPE_WORDS = re.compile(
    r"\b(?:штукатур\w*|ремонт\w*|демонтаж\w*|стен\w*|пол\w*|"
    r"потол\w*|фасад\w*|кровл\w*|бетон\w*|кладк\w*|плитк\w*|"
    r"работ\w*)\b",
    re.IGNORECASE,
)
TECHNOLOGY_CARD_WORDS = re.compile(
    r"\b(?:тех(?:нологическ\w*)?\s*карт\w*)\b",
    re.IGNORECASE,
)


def is_estimate_prompt(prompt: str) -> bool:
    return ESTIMATE_WORDS.search(prompt) is not None


def is_estimate_generation_prompt(prompt: str) -> bool:
    return is_estimate_prompt(prompt) and (
        ESTIMATE_GENERATION_WORDS.search(prompt) is not None
        or TECHNOLOGY_CARD_WORDS.search(prompt) is not None
        or (
            ESTIMATE_SCOPE_QUANTITY.search(prompt) is not None
            and ESTIMATE_SCOPE_WORDS.search(prompt) is not None
        )
    )


def _require_estimate_run_entitlement(
    database: Any,
    accepted: WidgetRunLike,
) -> str:
    actor = database.execute(
        """
        SELECT requested_by_user_id
        FROM chat_runs
        WHERE tenant_id = ? AND id = ?
        LIMIT 1
        """,
        (accepted.tenant_id, accepted.run_id),
    ).fetchone()
    if actor is None:
        raise RuntimeError("estimate run actor is missing")
    actor_user_id = str(actor["requested_by_user_id"])
    try:
        require_persisted_product_entitlement(
            database,
            tenant_id=accepted.tenant_id,
            user_id=actor_user_id,
            entitlement_code=CONSTRUCTION_ESTIMATES_ENTITLEMENT,
        )
    except ProductEntitlementError as exc:
        raise RuntimeError("estimate product entitlement is unavailable") from exc
    return actor_user_id


def _estimate_widget(
    settings: Settings,
    accepted: WidgetRunLike,
) -> ProductWidget | None:
    database = connect_database(settings.database_url)
    try:
        _require_estimate_run_entitlement(database, accepted)
        slot = load_estimate_slot(
            database,
            tenant_id=accepted.tenant_id,
            project_id=accepted.project_id,
        )
        if slot is None:
            return None
        now = str(slot["updated_at"])
        document = parse_estimate_document(slot["content_json"], now=now)
        if not document["rows"]:
            return None
        view = estimate_view(
            project_id=accepted.project_id,
            document_id=str(slot["id"]),
            version=int(slot["version"]),
            status=str(slot["status"]),
            document=document,
        )
    finally:
        database.close()
    return ProductWidget(
        arguments={"$type": "EstimateEditor", **view},
        fallback_text=(
            f"Открыта редактируемая смета «{view['estimateTitle']}», "
            f"версия {view['version']}."
        ),
    )


def materialize_generated_estimate_widget(
    settings: Settings,
    accepted: WidgetRunLike,
    *,
    proposal: GeneratedEstimateProposal,
    provider_profile: str,
) -> ProductWidget:
    database = connect_database(settings.database_url)
    try:
        with transaction(database, immediate=True):
            actor_user_id = _require_estimate_run_entitlement(
                database,
                accepted,
            )
            slot = load_estimate_slot(
                database,
                tenant_id=accepted.tenant_id,
                project_id=accepted.project_id,
            )
            if slot is None:
                raise RuntimeError("estimate document slot is missing")

            current = parse_estimate_document(
                slot["content_json"],
                now=str(slot["updated_at"]),
            )
            if current["rows"]:
                view = estimate_view(
                    project_id=accepted.project_id,
                    document_id=str(slot["id"]),
                    version=int(slot["version"]),
                    status=str(slot["status"]),
                    document=current,
                )
            else:
                now = str(
                    database.execute(
                        "SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
                    ).fetchone()[0]
                )
                document = estimate_document_from_proposal(
                    proposal,
                    now=now,
                    provider_profile=provider_profile,
                    run_id=accepted.run_id,
                )
                database.execute(
                    """
                    UPDATE document_slots
                    SET status = 'draft', content_json = ?, updated_at = ?
                    WHERE tenant_id = ? AND id = ? AND version = ?
                    """,
                    (
                        canonical_estimate_json(document),
                        now,
                        accepted.tenant_id,
                        slot["id"],
                        int(slot["version"]),
                    ),
                )
                record_estimate_version(
                    database,
                    tenant_id=accepted.tenant_id,
                    project_id=accepted.project_id,
                    document_id=str(slot["id"]),
                    version=int(slot["version"]),
                    status="draft",
                    document=document,
                    origin_type="ai_proposal",
                    origin_run_id=accepted.run_id,
                    created_by_user_id=actor_user_id,
                    created_at=now,
                )
                record_price_observations(
                    database,
                    tenant_id=accepted.tenant_id,
                    project_id=accepted.project_id,
                    document_id=str(slot["id"]),
                    estimate_version=int(slot["version"]),
                    previous_document=None,
                    document=document,
                    source_type="ai_preliminary",
                    lifecycle="draft",
                    created_by_user_id=actor_user_id,
                    observed_at=now,
                )
                database.execute(
                    """
                    UPDATE projects
                    SET updated_at = ?
                    WHERE tenant_id = ? AND id = ?
                    """,
                    (now, accepted.tenant_id, accepted.project_id),
                )
                view = estimate_view(
                    project_id=accepted.project_id,
                    document_id=str(slot["id"]),
                    version=int(slot["version"]),
                    status="draft",
                    document=document,
                )
    finally:
        database.close()

    return ProductWidget(
        arguments={"$type": "EstimateEditor", **view},
        fallback_text=(
            f"Подготовлена предварительная смета «{view['estimateTitle']}»: "
            f"{len(view['rows'])} позиций на {view['totals']['total']} ₽. "
            "Количество и цены с пометкой «допущение» требуют проверки."
        ),
    )


def materialize_engine_estimate_widget(
    settings: Settings,
    accepted: WidgetRunLike,
    *,
    intake: PlasteringIntake,
    provider_profile: str,
) -> ProductWidget:
    database = connect_database(settings.database_url)
    try:
        _require_estimate_run_entitlement(database, accepted)
        slot = load_estimate_slot(
            database,
            tenant_id=accepted.tenant_id,
            project_id=accepted.project_id,
        )
        actor = database.execute(
            """
            SELECT runs.requested_by_user_id, runs.input_message_id,
                   users.role, users.preferred_agent_profile,
                   users.email, users.name
            FROM chat_runs AS runs
            JOIN users
              ON users.id = runs.requested_by_user_id
             AND users.tenant_id = runs.tenant_id
            WHERE runs.tenant_id = ? AND runs.id = ?
            LIMIT 1
            """,
            (accepted.tenant_id, accepted.run_id),
        ).fetchone()
        if slot is None or actor is None:
            raise RuntimeError("estimate calculation context is missing")

        scope_value = PlasteringScope(
            wall_area_m2=intake.wall_area_m2,
            average_thickness_mm=intake.average_thickness_mm,
            material=intake.material,
            application_method=intake.application_method,
            waste_percent=intake.waste_percent,
            protection_area_m2=intake.protection_area_m2,
            wall_height_m=intake.wall_height_m,
            beacon_spacing_m=intake.beacon_spacing_m,
            corner_length_m=intake.corner_length_m,
            mesh_area_percent=intake.mesh_area_percent,
            slopes_area_m2=intake.slopes_area_m2,
            plaster_bag_weight_kg=intake.plaster_bag_weight_kg,
            primer_passes=intake.primer_passes,
            waste_removal_trips=intake.waste_removal_trips,
        )
        preflight = calculate_plastering_estimate(
            project_case=ProjectCaseRef(
                tenant_id=accepted.tenant_id,
                project_id=accepted.project_id,
                case_id="case_preflight",
                version=1,
                region=intake.region,
            ),
            scope=scope_value,
            prices=[],
        )
        active_units = {
            str(item["code"]): str(item["unit"])
            for item in preflight["items"]
        }
        reference_prices = plastering_reference_price_quotes(
            active_units=active_units,
            region=intake.region,
        )
        candidate_checks = verify_plastering_model_price_candidates(
            {
                item.item_code: item.unit_price
                for item in intake.candidate_prices
                if item.item_code in active_units
            }
        )
        calculation_assumptions = list(intake.assumptions)
        reference_assumption = plastering_reference_price_assumption()
        if reference_assumption not in calculation_assumptions:
            calculation_assumptions.append(reference_assumption)
        try:
            payload = PlasteringCalculationInput.model_validate(
                {
                    "expectedEstimateVersion": int(slot["version"]),
                    "region": intake.region,
                    "title": intake.title,
                    "assumptions": calculation_assumptions,
                    "scope": {
                        "wallAreaM2": intake.wall_area_m2,
                        "averageThicknessMm": intake.average_thickness_mm,
                        "material": intake.material,
                        "applicationMethod": intake.application_method,
                        "wastePercent": intake.waste_percent,
                        "protectionAreaM2": intake.protection_area_m2,
                        "wallHeightM": intake.wall_height_m,
                        "beaconSpacingM": intake.beacon_spacing_m,
                        "cornerLengthM": intake.corner_length_m,
                        "meshAreaPercent": intake.mesh_area_percent,
                        "slopesAreaM2": intake.slopes_area_m2,
                        "plasterBagWeightKg": intake.plaster_bag_weight_kg,
                        "primerPasses": intake.primer_passes,
                        "wasteRemovalTrips": intake.waste_removal_trips,
                    },
                    "prices": reference_prices,
                    "terms": {
                        "overheadPercent": "0",
                        "profitPercent": "0",
                        "discountPercent": "0",
                        "taxPercent": "0",
                    },
                    "sourceMessageId": str(actor["input_message_id"]),
                    "sourceRunId": accepted.run_id,
                    "requireReleaseReady": False,
                }
            )
            response = calculate_plastering(
                accepted.project_id,
                payload,
                database,
                UserSession(
                    user_id=str(actor["requested_by_user_id"]),
                    tenant_id=accepted.tenant_id,
                    role=UserRole(str(actor["role"])),
                    preferred_agent_profile=AgentProfile(
                        str(actor["preferred_agent_profile"])
                    ),
                    email=str(actor["email"]),
                    name=str(actor["name"]),
                ),
                None,
                f"estimate-chat-{accepted.run_id}",
            )
        except (HTTPException, ValidationError, ValueError) as exc:
            raise RuntimeError("estimate engine persistence failed") from exc
    finally:
        database.close()

    view = response["estimate"]
    validation = response["result"]["validation"]
    return ProductWidget(
        arguments={"$type": "EstimateEditor", **view},
        fallback_text=(
            f"Подготовлены технологическая карта и смета «{view['estimateTitle']}»: "
            f"{len(view['rows'])} позиций на {view['totals']['total']} ₽. "
            + (
                "Ценовые кандидаты требуют независимой проверки перед выпуском."
                if validation["status"] == "blocked"
                else "Цены и расчёт прошли проверку."
            )
        ),
        tool_result={
            "rendered": True,
            "schemaVersion": "1.0",
            "calculationId": response["calculationId"],
            "engineVersion": response["result"]["engineVersion"],
            "rulesVersion": response["result"]["rulesVersion"],
            "priceSnapshotVersion": (
                PLASTERING_REFERENCE_PRICE_SNAPSHOT_VERSION
            ),
            "candidatePriceCount": len(candidate_checks),
            "candidateWithinRangeCount": sum(
                check["verdict"] == "within_reference_range"
                for check in candidate_checks
            ),
            "candidateOutlierCount": sum(
                check["verdict"] == "outlier"
                for check in candidate_checks
            ),
            "candidatePriceChecks": candidate_checks,
            "resultHash": response["result"]["resultHash"],
            "estimateVersion": response["estimateVersion"],
            "technologyStageCount": len(
                response["result"]["technologyCard"]["stages"]
            ),
            "validationStatus": validation["status"],
            "unverifiedPriceCount": len(
                validation.get("unverifiedPriceItemCodes", [])
            ),
            "missingPriceCount": len(
                validation.get("missingPriceItemCodes", [])
            ),
        },
    )


def try_prepare_product_widget(
    settings: Settings,
    accepted: WidgetRunLike,
    *,
    prompt: str,
) -> ProductWidget | None:
    if is_estimate_prompt(prompt):
        return _estimate_widget(settings, accepted)
    return None
