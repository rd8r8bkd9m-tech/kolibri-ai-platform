"""Thin HTTP contracts for the canonical billing domain."""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import Field

from ..database import get_database
from ..identity import require_owner, require_user
from ..schemas import APIModel, UserSession
from ..security import require_mutation_auth
from .config import TBankSettings
from .service import (
    BillingError,
    admin_audit_views,
    admin_plan_views,
    admin_payment_views,
    apply_notification,
    create_payment,
    payment_view,
    plan_views,
    subscription_views,
    verified_return,
)
from .tbank import (
    TBankGateway,
    TBankProtocolError,
    TBankSignatureError,
    verify_notification,
)


router = APIRouter(tags=["billing"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = Annotated[UserSession, Depends(require_user)]
OwnerDependency = Annotated[UserSession, Depends(require_owner)]
MutationDependency = Annotated[None, Depends(require_mutation_auth)]
IdempotencyDependency = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]{16,128}$",
    ),
]
_INTENT_ID = re.compile(r"^payment_intent_[0-9a-f]{32}$")
_MAX_NOTIFICATION_BYTES = 65_536


PaymentStatus = Literal[
    "initializing",
    "pending",
    "unknown",
    "authorized",
    "succeeded",
    "failed",
    "canceled",
    "partially_refunded",
    "refunded",
]


class BillingPlanView(APIModel):
    code: str
    name: str
    amount_minor: int = Field(alias="amountMinor")
    currency: Literal["RUB"]
    duration_seconds: int = Field(alias="durationSeconds")
    entitlement: str
    revision: int


class BillingPlanListView(APIModel):
    items: list[BillingPlanView]


class BillingAdminPlanView(APIModel):
    code: str
    name: str
    amount_minor: int = Field(alias="amountMinor")
    currency: Literal["RUB"]
    duration_seconds: int = Field(alias="durationSeconds")
    entitlement: str
    entitlement_active: bool = Field(alias="entitlementActive")
    receipt_item_name: str = Field(alias="receiptItemName")
    receipt_tax: str = Field(alias="receiptTax")
    receipt_payment_method: str = Field(alias="receiptPaymentMethod")
    receipt_payment_object: str = Field(alias="receiptPaymentObject")
    active: bool
    revision: int
    created_at: int = Field(alias="createdAt")
    updated_at: int = Field(alias="updatedAt")


class BillingAdminPlanListView(APIModel):
    items: list[BillingAdminPlanView]


class CreatePaymentRequest(APIModel):
    plan_code: str = Field(
        alias="planCode",
        min_length=1,
        max_length=48,
        pattern=r"^[a-z0-9][a-z0-9._-]{0,47}$",
    )
    return_surface: Literal["web", "pwa"] = Field(
        default="web",
        alias="returnSurface",
    )


class PaymentIntentView(APIModel):
    id: str
    tenant_id: str = Field(alias="tenantId")
    user_id: str = Field(alias="userId")
    plan_code: str = Field(alias="planCode")
    plan_name: str = Field(alias="planName")
    amount_minor: int = Field(alias="amountMinor")
    currency: Literal["RUB"]
    status: PaymentStatus
    provider: Literal["tbank"]
    provider_environment: Literal["test", "demo", "production"] = Field(
        alias="providerEnvironment"
    )
    provider_status: str | None = Field(alias="providerStatus")
    payment_url: str | None = Field(default=None, alias="paymentUrl")
    created_at: int = Field(alias="createdAt")
    updated_at: int = Field(alias="updatedAt")


class PaymentIntentAdminView(PaymentIntentView):
    payment_url: None = Field(default=None, alias="paymentUrl", exclude=True)


class SubscriptionView(APIModel):
    id: str
    tenant_id: str = Field(alias="tenantId")
    user_id: str = Field(alias="userId")
    plan_code: str = Field(alias="planCode")
    entitlement: str
    payment_intent_id: str = Field(alias="paymentIntentId")
    status: Literal["active", "refunded", "canceled", "expired"]
    current_period_start: int = Field(alias="currentPeriodStart")
    current_period_end: int = Field(alias="currentPeriodEnd")
    created_at: int = Field(alias="createdAt")
    updated_at: int = Field(alias="updatedAt")


class SubscriptionListView(APIModel):
    items: list[SubscriptionView]


class AdminPaymentListView(APIModel):
    items: list[PaymentIntentAdminView]


class BillingAuditView(APIModel):
    id: str
    tenant_id: str = Field(alias="tenantId")
    user_id: str | None = Field(alias="userId")
    actor_type: str = Field(alias="actorType")
    action: str
    payment_intent_id: str | None = Field(alias="paymentIntentId")
    details: dict[str, Any]
    created_at: int = Field(alias="createdAt")


class BillingAuditListView(APIModel):
    items: list[BillingAuditView]


class BillingReturnView(APIModel):
    intent_id: str = Field(alias="intentId")
    verified_status: PaymentStatus = Field(alias="verifiedStatus")
    entitlement_active: bool = Field(alias="entitlementActive")


class BillingConfigView(APIModel):
    status: Literal["disabled", "configured", "invalid"]
    mode: Literal["off", "test", "demo", "production"] | None
    receipt_mode: Literal["disabled", "required"] | None = Field(
        alias="receiptMode"
    )
    production_confirmed: bool = Field(alias="productionConfirmed")


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _error(error: BillingError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    )


def _gateway(request: Request) -> TBankGateway:
    override = getattr(request.app.state, "tbank_gateway", None)
    if isinstance(override, TBankGateway):
        return override
    try:
        settings = TBankSettings.from_env(
            runtime_environment=request.app.state.settings.environment
        )
    except ValueError as exc:
        raise _error(
            BillingError(
                503,
                "billing_configuration_invalid",
                "Настройки оплаты требуют проверки оператором.",
            )
        ) from exc
    if not settings.enabled:
        raise _error(
            BillingError(503, "billing_disabled", "Оплата пока не подключена.")
        )
    return TBankGateway(settings)


def _validated_intent_id(intent_id: str) -> str:
    if _INTENT_ID.fullmatch(intent_id) is None:
        raise _error(
            BillingError(404, "billing_payment_not_found", "Платёж не найден.")
        )
    return intent_id


def _no_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


async def _notification_json(request: Request) -> dict[str, object]:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
    if content_type != "application/json":
        raise _error(
            BillingError(
                415,
                "billing_notification_media_type_invalid",
                "Формат уведомления не поддерживается.",
            )
        )
    raw_length = request.headers.get("content-length")
    if raw_length is not None:
        try:
            declared_length = int(raw_length)
        except ValueError as exc:
            raise _error(
                BillingError(400, "billing_notification_invalid", "Уведомление некорректно.")
            ) from exc
        if declared_length < 2 or declared_length > _MAX_NOTIFICATION_BYTES:
            raise _error(
                BillingError(413, "billing_notification_too_large", "Уведомление слишком большое.")
            )
    body_buffer = bytearray()
    async for chunk in request.stream():
        if len(body_buffer) + len(chunk) > _MAX_NOTIFICATION_BYTES:
            raise _error(
                BillingError(
                    413,
                    "billing_notification_too_large",
                    "Уведомление слишком большое.",
                )
            )
        body_buffer.extend(chunk)
    body = bytes(body_buffer)
    if not body:
        raise _error(
            BillingError(413, "billing_notification_too_large", "Уведомление слишком большое.")
        )
    try:
        value = json.loads(body, object_pairs_hook=_no_duplicate_object)
    except (UnicodeError, ValueError) as exc:
        raise _error(
            BillingError(400, "billing_notification_invalid", "Уведомление некорректно.")
        ) from exc
    if not isinstance(value, dict) or len(value) > 64:
        raise _error(
            BillingError(400, "billing_notification_invalid", "Уведомление некорректно.")
        )
    return value


@router.get("/v1/billing/plans", response_model=BillingPlanListView)
def list_billing_plans(
    database: DatabaseDependency,
    response: Response,
) -> dict[str, object]:
    _no_store(response)
    return {"items": plan_views(database)}


@router.post(
    "/v1/billing/payment-intents",
    response_model=PaymentIntentView,
    status_code=201,
)
def initialize_payment(
    payload: CreatePaymentRequest,
    request: Request,
    response: Response,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _mutation: MutationDependency,
    idempotency_key: IdempotencyDependency,
) -> dict[str, Any]:
    _no_store(response)
    try:
        creation = create_payment(
            database,
            identity=identity,
            plan_code=payload.plan_code,
            return_surface=payload.return_surface,
            idempotency_key=idempotency_key,
            gateway=_gateway(request),
        )
        response.status_code = (
            202
            if creation.payment["status"] in {"initializing", "unknown"}
            else 201
            if creation.created
            else 200
        )
        return creation.payment
    except BillingError as exc:
        raise _error(exc) from exc


@router.get(
    "/v1/billing/payment-intents/{intent_id}",
    response_model=PaymentIntentView,
)
def get_payment(
    intent_id: str,
    response: Response,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, Any]:
    _no_store(response)
    try:
        return payment_view(
            database,
            identity=identity,
            intent_id=_validated_intent_id(intent_id),
        )
    except BillingError as exc:
        raise _error(exc) from exc


@router.get("/v1/billing/subscriptions", response_model=SubscriptionListView)
def get_subscriptions(
    response: Response,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, object]:
    _no_store(response)
    return {
        "items": subscription_views(
            database,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
        )
    }


@router.post(
    "/v1/billing/tbank/notifications",
    response_class=PlainTextResponse,
    include_in_schema=False,
)
async def tbank_notification(
    request: Request,
    database: DatabaseDependency,
) -> PlainTextResponse:
    gateway = _gateway(request)
    payload = await _notification_json(request)
    try:
        notification = verify_notification(payload, gateway.settings)
        apply_notification(database, notification=notification, gateway=gateway)
    except TBankSignatureError as exc:
        raise _error(
            BillingError(
                400,
                "billing_notification_signature_invalid",
                "Подпись уведомления недействительна.",
            )
        ) from exc
    except TBankProtocolError as exc:
        raise _error(
            BillingError(
                400,
                "billing_notification_invalid",
                "Уведомление некорректно.",
            )
        ) from exc
    except BillingError as exc:
        raise _error(exc) from exc
    return PlainTextResponse("OK", status_code=200)


@router.get(
    "/v1/billing/tbank/return/{intent_id}",
    response_model=BillingReturnView,
    include_in_schema=False,
)
def tbank_return(
    intent_id: str,
    nonce: Annotated[str, Query(min_length=64, max_length=64)],
    provider_result: Annotated[
        Literal["success", "fail"], Query(alias="providerResult")
    ],
    database: DatabaseDependency,
) -> JSONResponse:
    # provider_result is intentionally not used for authorization or state.
    # It is accepted only because the hosted form needs distinct landing URLs.
    del provider_result
    try:
        payload, status_code = verified_return(
            database,
            intent_id=_validated_intent_id(intent_id),
            nonce=nonce,
        )
    except BillingError as exc:
        raise _error(exc) from exc
    return JSONResponse(
        content=payload,
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/v1/platform-admin/billing/config",
    response_model=BillingConfigView,
)
def billing_configuration(
    request: Request,
    response: Response,
    _owner: OwnerDependency,
) -> dict[str, object]:
    _no_store(response)
    override = getattr(request.app.state, "tbank_gateway", None)
    if isinstance(override, TBankGateway):
        settings = override.settings
    else:
        try:
            settings = TBankSettings.from_env(
                runtime_environment=request.app.state.settings.environment
            )
        except ValueError:
            return {
                "status": "invalid",
                "mode": None,
                "receiptMode": None,
                "productionConfirmed": False,
            }
    return {
        "status": "configured" if settings.enabled else "disabled",
        "mode": settings.mode,
        "receiptMode": settings.receipt_mode,
        "productionConfirmed": settings.production_confirmed,
    }


@router.get(
    "/v1/platform-admin/billing/plans",
    response_model=BillingAdminPlanListView,
)
def admin_billing_plans(
    response: Response,
    database: DatabaseDependency,
    _owner: OwnerDependency,
) -> dict[str, object]:
    """Expose the complete catalog to the owner without enabling mutations."""

    _no_store(response)
    return {"items": admin_plan_views(database)}


@router.get(
    "/v1/platform-admin/billing/payments",
    response_model=AdminPaymentListView,
)
def admin_payments(
    response: Response,
    database: DatabaseDependency,
    _owner: OwnerDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
    _no_store(response)
    return {"items": admin_payment_views(database, limit=limit)}


@router.get(
    "/v1/platform-admin/billing/subscriptions",
    response_model=SubscriptionListView,
)
def admin_subscriptions(
    response: Response,
    database: DatabaseDependency,
    _owner: OwnerDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
    _no_store(response)
    return {"items": subscription_views(database, limit=limit)}


@router.get(
    "/v1/platform-admin/billing/audit",
    response_model=BillingAuditListView,
)
def admin_billing_audit(
    response: Response,
    database: DatabaseDependency,
    _owner: OwnerDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
    _no_store(response)
    return {"items": admin_audit_views(database, limit=limit)}
