"""Canonical payment, subscription and entitlement transitions for billing."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from ..database import transaction
from ..schemas import AgentProfile, UserRole, UserSession
from .tbank import (
    TBankGateway,
    TBankProtocolError,
    TBankTransportError,
    VerifiedNotification,
)


_RENEWAL_LEAD_SECONDS = 86_400  # charge up to 24 hours before period end
_RENEWAL_MAX_ATTEMPTS = 5


class BillingError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class PaymentCreation:
    payment: dict[str, Any]
    created: bool


@dataclass(frozen=True, slots=True)
class NotificationOutcome:
    payment_intent_id: str
    status: str
    outcome: str


_PENDING_PROVIDER_STATUSES = frozenset(
    {
        "NEW",
        "FORM_SHOWED",
        "PREAUTHORIZING",
        "AUTHORIZING",
        "CHECKING",
        "3DS_CHECKING",
        "CONFIRMING",
    }
)
_FAILED_PROVIDER_STATUSES = frozenset(
    {"REJECTED", "AUTH_FAIL", "DEADLINE_EXPIRED"}
)
_CANCELED_PROVIDER_STATUSES = frozenset(
    {"CANCELED", "REVERSED"}
)
_SUCCESS_PROVIDER_STATUSES = frozenset({"AUTHORIZED", "CONFIRMED"})
_REFUND_PROVIDER_STATUSES = frozenset(
    {
        "REFUNDING",
        "PARTIAL_REVERSED",
        "PARTIAL_REFUNDED",
        "REFUNDED",
    }
)


def _now(database: sqlite3.Connection) -> int:
    return int(database.execute("SELECT unixepoch()").fetchone()[0])


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _audit(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str | None,
    actor_type: str,
    action: str,
    payment_intent_id: str | None,
    details: dict[str, object],
    now: int,
) -> None:
    database.execute(
        """
        INSERT INTO billing_audit_events (
            id, tenant_id, user_id, actor_type, action,
            payment_intent_id, details_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"billing_audit_{uuid.uuid4().hex}",
            tenant_id,
            user_id,
            actor_type,
            action,
            payment_intent_id,
            _canonical_json(details),
            now,
        ),
    )


def _request_hash(
    *,
    tenant_id: str,
    user_id: str,
    plan_code: str,
    return_surface: str,
) -> str:
    encoded = _canonical_json(
        {
            "planCode": plan_code,
            "returnSurface": return_surface,
            "tenantId": tenant_id,
            "userId": user_id,
        }
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _recurring_customer_key(identity: UserSession) -> str:
    """Stable per-user provider customer key (1..64 of [A-Za-z0-9._-])."""

    digest = hashlib.sha256(
        f"{identity.tenant_id}:{identity.user_id}".encode("utf-8")
    ).hexdigest()
    return f"kv3-{digest[:40]}"


def _return_nonce(gateway: TBankGateway, intent_id: str) -> str:
    password = gateway.settings.password
    if password is None:
        raise BillingError(503, "billing_not_configured", "Оплата пока недоступна.")
    return hmac.new(
        password.encode("utf-8"),
        f"kolibri-v3:return:{intent_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _return_url(
    gateway: TBankGateway,
    *,
    intent_id: str,
    nonce: str,
    provider_result: str,
    return_surface: str,
) -> str:
    origin = gateway.settings.return_origin
    if origin is None:
        raise BillingError(503, "billing_not_configured", "Оплата пока недоступна.")
    query_values = {"nonce": nonce, "providerResult": provider_result}
    if return_surface == "pwa":
        query_values["returnSurface"] = "pwa"
    query = urlencode(query_values)
    return f"{origin}/api/v3/billing/tbank/return/{intent_id}?{query}"


def _payment_view(row: sqlite3.Row, *, include_payment_url: bool) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": str(row["id"]),
        "tenantId": str(row["tenant_id"]),
        "userId": str(row["user_id"]),
        "planCode": str(row["plan_code"]),
        "planName": str(row["plan_display_name"]),
        "amountMinor": int(row["amount_minor"]),
        "currency": str(row["currency"]),
        "status": str(row["status"]),
        "provider": str(row["provider"]),
        "providerEnvironment": str(row["provider_environment"]),
        "providerStatus": (
            str(row["provider_status"])
            if row["provider_status"] is not None
            else None
        ),
        "createdAt": int(row["created_at"]),
        "updatedAt": int(row["updated_at"]),
        "paidAt": (
            int(row["paid_at"]) if row["paid_at"] is not None else None
        ),
    }
    if include_payment_url:
        value["paymentUrl"] = (
            str(row["payment_url"])
            if row["payment_url"] is not None
            else None
        )
    return value


def plan_views(database: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = database.execute(
        """
        SELECT plan.code, plan.display_name, plan.amount_minor, plan.currency,
               plan.duration_seconds, plan.entitlement_code, plan.revision
        FROM billing_plans AS plan
        JOIN billing_entitlement_catalog AS entitlement
          ON entitlement.code = plan.entitlement_code
         AND entitlement.active = 1
        WHERE plan.active = 1
        ORDER BY plan.amount_minor, plan.code
        """
    ).fetchall()
    return [
        {
            "code": str(row["code"]),
            "name": str(row["display_name"]),
            "amountMinor": int(row["amount_minor"]),
            "currency": str(row["currency"]),
            "durationSeconds": int(row["duration_seconds"]),
            "entitlement": str(row["entitlement_code"]),
            "revision": int(row["revision"]),
        }
        for row in rows
    ]


def admin_plan_views(database: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return the complete server-owned catalog for the platform owner.

    The public catalog intentionally hides inactive and unapproved rows.  The
    owner view needs those rows to explain why checkout is unavailable and to
    audit a revision before an operator publishes it.  It never includes a
    provider secret or a payment URL, and it remains read-only: commercial
    terms are changed through an append-only, reviewed operation.
    """

    rows = database.execute(
        """
        SELECT
            plan.code,
            plan.display_name,
            plan.amount_minor,
            plan.currency,
            plan.duration_seconds,
            plan.entitlement_code,
            entitlement.active AS entitlement_active,
            plan.receipt_item_name,
            plan.receipt_tax,
            plan.receipt_payment_method,
            plan.receipt_payment_object,
            plan.active,
            plan.revision,
            plan.created_at,
            plan.updated_at
        FROM billing_plans AS plan
        JOIN billing_entitlement_catalog AS entitlement
          ON entitlement.code = plan.entitlement_code
        ORDER BY plan.code, plan.revision DESC
        LIMIT 100
        """
    ).fetchall()
    return [
        {
            "code": str(row["code"]),
            "name": str(row["display_name"]),
            "amountMinor": int(row["amount_minor"]),
            "currency": str(row["currency"]),
            "durationSeconds": int(row["duration_seconds"]),
            "entitlement": str(row["entitlement_code"]),
            "entitlementActive": bool(row["entitlement_active"]),
            "receiptItemName": str(row["receipt_item_name"]),
            "receiptTax": str(row["receipt_tax"]),
            "receiptPaymentMethod": str(row["receipt_payment_method"]),
            "receiptPaymentObject": str(row["receipt_payment_object"]),
            "active": bool(row["active"]),
            "revision": int(row["revision"]),
            "createdAt": int(row["created_at"]),
            "updatedAt": int(row["updated_at"]),
        }
        for row in rows
    ]


def _load_payment_by_subject(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str,
    intent_id: str,
) -> sqlite3.Row:
    row = database.execute(
        """
        SELECT *
        FROM billing_payment_intents
        WHERE tenant_id = ? AND user_id = ? AND id = ?
        LIMIT 1
        """,
        (tenant_id, user_id, intent_id),
    ).fetchone()
    if row is None:
        raise BillingError(404, "billing_payment_not_found", "Платёж не найден.")
    return row


def payment_view(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    intent_id: str,
) -> dict[str, Any]:
    return _payment_view(
        _load_payment_by_subject(
            database,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            intent_id=intent_id,
        ),
        include_payment_url=True,
    )


def user_payment_views(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Read-only payment history for the signed-in subject.

    The list never carries a hosted payment URL: a stale URL must not be
    reused after the intent changed state. The current checkout draft already
    has its own bounded recovery path on the client.
    """

    rows = database.execute(
        """
        SELECT * FROM billing_payment_intents
        WHERE tenant_id = ? AND user_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (tenant_id, user_id, limit),
    ).fetchall()
    return [_payment_view(row, include_payment_url=False) for row in rows]


def _provider_payload(
    *,
    gateway: TBankGateway,
    identity: UserSession,
    payment: sqlite3.Row,
    nonce: str,
    customer_key: str | None = None,
    rebill_id: str | None = None,
) -> dict[str, object]:
    terminal_key = gateway.settings.terminal_key
    notification_url = gateway.settings.notification_url
    if terminal_key is None or notification_url is None:
        raise BillingError(503, "billing_not_configured", "Оплата пока недоступна.")
    payload: dict[str, object] = {
        "TerminalKey": terminal_key,
        "Amount": int(payment["amount_minor"]),
        "OrderId": str(payment["order_id"]),
        "Description": f"Тариф Kolibri: {payment['plan_display_name']}"[:140],
        "NotificationURL": notification_url,
        "SuccessURL": _return_url(
            gateway,
            intent_id=str(payment["id"]),
            nonce=nonce,
            provider_result="success",
            return_surface=str(payment["return_surface"]),
        ),
        "FailURL": _return_url(
            gateway,
            intent_id=str(payment["id"]),
            nonce=nonce,
            provider_result="fail",
            return_surface=str(payment["return_surface"]),
        ),
        "PayType": "O",
        "Language": "ru",
    }
    if rebill_id is not None:
        if customer_key is None:
            raise BillingError(
                503,
                "billing_recurring_not_configured",
                "Автопродление пока недоступно.",
            )
        if len(identity.email) > 64:
            raise BillingError(
                422,
                "billing_receipt_contact_invalid",
                "Email слишком длинный для автоплатежа.",
            )
        payload["Recurrent"] = "Y"
        payload["CustomerKey"] = customer_key
        payload["RebillId"] = rebill_id
        payload["DATA"] = {"Email": identity.email}
    elif customer_key is not None or gateway.settings.recurring_enabled:
        if len(identity.email) > 64:
            raise BillingError(
                422,
                "billing_receipt_contact_invalid",
                "Email слишком длинный для автоплатежа.",
            )
        payload["Recurrent"] = "Y"
        payload["CustomerKey"] = customer_key or _recurring_customer_key(identity)
        payload["DATA"] = {"Email": identity.email}
    if gateway.settings.receipt_mode == "required":
        if len(identity.email) > 64:
            raise BillingError(
                422,
                "billing_receipt_contact_invalid",
                "Email слишком длинный для кассового чека.",
            )
        taxation = gateway.settings.taxation
        if taxation is None:
            raise BillingError(
                503,
                "billing_receipt_not_configured",
                "Кассовый чек пока не настроен.",
            )
        payload["Receipt"] = {
            "Email": identity.email,
            "Taxation": taxation,
            "Items": [
                {
                    "Name": str(payment["receipt_item_name"]),
                    "Price": int(payment["amount_minor"]),
                    "Quantity": 1,
                    "Amount": int(payment["amount_minor"]),
                    "Tax": str(payment["receipt_tax"]),
                    "PaymentMethod": str(payment["receipt_payment_method"]),
                    "PaymentObject": str(payment["receipt_payment_object"]),
                }
            ],
        }
    return payload


def create_payment(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    plan_code: str,
    return_surface: str,
    idempotency_key: str,
    gateway: TBankGateway,
    kind: str = "initial",
    recurrent_parent_id: str | None = None,
    rebill_id: str | None = None,
    customer_key: str | None = None,
) -> PaymentCreation:
    if kind not in {"initial", "recurrent"}:
        raise BillingError(422, "billing_kind_invalid", "Тип платежа невалиден.")
    if kind == "recurrent" and (
        recurrent_parent_id is None or rebill_id is None or customer_key is None
    ):
        raise BillingError(
            422,
            "billing_recurring_credentials_missing",
            "Реквизиты автоплатежа отсутствуют.",
        )
    if kind == "initial" and customer_key is None:
        customer_key = (
            _recurring_customer_key(identity)
            if gateway.settings.recurring_enabled
            else None
        )
    if gateway.settings.receipt_mode == "required" and len(identity.email) > 64:
        raise BillingError(
            422,
            "billing_receipt_contact_invalid",
            "Email слишком длинный для кассового чека.",
        )
    request_hash = _request_hash(
        tenant_id=identity.tenant_id,
        user_id=identity.user_id,
        plan_code=plan_code,
        return_surface=return_surface,
    )
    created = False
    with transaction(database, immediate=True):
        existing = database.execute(
            """
            SELECT *
            FROM billing_payment_intents
            WHERE tenant_id = ? AND user_id = ? AND idempotency_key = ?
            LIMIT 1
            """,
            (identity.tenant_id, identity.user_id, idempotency_key),
        ).fetchone()
        if existing is not None:
            if not hmac.compare_digest(str(existing["request_hash"]), request_hash):
                raise BillingError(
                    409,
                    "billing_idempotency_conflict",
                    "Этот ключ уже использован для другой оплаты.",
                )
            return PaymentCreation(
                payment=_payment_view(existing, include_payment_url=True),
                created=False,
            )

        plan = database.execute(
            """
            SELECT plan.*
            FROM billing_plans AS plan
            JOIN billing_entitlement_catalog AS entitlement
              ON entitlement.code = plan.entitlement_code
             AND entitlement.active = 1
            WHERE plan.code = ? AND plan.active = 1
            LIMIT 1
            """,
            (plan_code,),
        ).fetchone()
        if plan is None:
            raise BillingError(404, "billing_plan_not_found", "Тариф не найден.")

        intent_id = f"payment_intent_{uuid.uuid4().hex}"
        # The provider order is a pure, stable projection of the durable
        # intent. Replays therefore cannot accidentally create a second
        # provider order for the same accepted idempotency key.
        order_id = f"kv3-{intent_id.removeprefix('payment_intent_')}"
        nonce = _return_nonce(gateway, intent_id)
        nonce_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
        now = _now(database)
        database.execute(
            """
            INSERT INTO billing_payment_intents (
                id, tenant_id, user_id, plan_code, plan_revision,
                plan_display_name, entitlement_code, duration_seconds,
                receipt_item_name, receipt_tax, receipt_payment_method,
                receipt_payment_object, amount_minor, currency, provider,
                provider_environment, terminal_fingerprint, order_id,
                return_surface,
                provider_payment_id, payment_url, idempotency_key,
                request_hash, return_nonce_hash, status, provider_status,
                provider_error_code, version, created_at, updated_at,
                initialized_at, kind, recurrent_parent_id, rebill_id,
                customer_key
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'tbank',
                ?, ?, ?, ?, NULL, NULL, ?, ?, ?, 'initializing', NULL,
                NULL, 1, ?, ?, NULL, ?, ?, ?, ?
            )
            """,
            (
                intent_id,
                identity.tenant_id,
                identity.user_id,
                str(plan["code"]),
                int(plan["revision"]),
                str(plan["display_name"]),
                str(plan["entitlement_code"]),
                int(plan["duration_seconds"]),
                str(plan["receipt_item_name"]),
                str(plan["receipt_tax"]),
                str(plan["receipt_payment_method"]),
                str(plan["receipt_payment_object"]),
                int(plan["amount_minor"]),
                str(plan["currency"]),
                gateway.settings.mode,
                gateway.settings.terminal_fingerprint,
                order_id,
                return_surface,
                idempotency_key,
                request_hash,
                nonce_hash,
                now,
                now,
                kind,
                recurrent_parent_id,
                rebill_id,
                customer_key,
            ),
        )
        _audit(
            database,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            actor_type="user",
            action="payment.intent.created",
            payment_intent_id=intent_id,
            details={
                "amountMinor": int(plan["amount_minor"]),
                "currency": str(plan["currency"]),
                "planCode": str(plan["code"]),
                "providerEnvironment": gateway.settings.mode,
                "returnSurface": return_surface,
            },
            now=now,
        )
        payment = database.execute(
            "SELECT * FROM billing_payment_intents WHERE id = ?",
            (intent_id,),
        ).fetchone()
        assert payment is not None
        created = True

    nonce = _return_nonce(gateway, str(payment["id"]))
    try:
        result = gateway.init_payment(
            _provider_payload(
                gateway=gateway,
                identity=identity,
                payment=payment,
                nonce=nonce,
                customer_key=customer_key,
                rebill_id=rebill_id,
            )
        )
    except BillingError:
        raise
    except (TBankTransportError, TBankProtocolError):
        with transaction(database, immediate=True):
            current = database.execute(
                "SELECT * FROM billing_payment_intents WHERE id = ?",
                (payment["id"],),
            ).fetchone()
            assert current is not None
            now = _now(database)
            if str(current["status"]) == "initializing":
                database.execute(
                    """
                    UPDATE billing_payment_intents
                    SET status = 'unknown', version = version + 1,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, payment["id"]),
                )
            _audit(
                database,
                tenant_id=identity.tenant_id,
                user_id=identity.user_id,
                actor_type="system",
                action="payment.init.uncertain",
                payment_intent_id=str(payment["id"]),
                details={"providerEnvironment": gateway.settings.mode},
                now=now,
            )
            current = database.execute(
                "SELECT * FROM billing_payment_intents WHERE id = ?",
                (payment["id"],),
            ).fetchone()
            assert current is not None
            if str(current["status"]) in {
                "succeeded",
                "partially_refunded",
                "refunded",
            }:
                return PaymentCreation(
                    payment=_payment_view(current, include_payment_url=True),
                    created=created,
                )
            return PaymentCreation(
                payment=_payment_view(current, include_payment_url=True),
                created=created,
            )

    if not result.success:
        with transaction(database, immediate=True):
            current = database.execute(
                "SELECT * FROM billing_payment_intents WHERE id = ?",
                (payment["id"],),
            ).fetchone()
            assert current is not None
            now = _now(database)
            if str(current["status"]) in {"initializing", "unknown", "pending"}:
                database.execute(
                    """
                    UPDATE billing_payment_intents
                    SET provider_payment_id = COALESCE(provider_payment_id, ?),
                        status = 'failed', provider_status = ?,
                        provider_error_code = ?, version = version + 1,
                        updated_at = ?, initialized_at = ?
                    WHERE id = ?
                    """,
                    (
                        result.payment_id,
                        result.status,
                        result.error_code,
                        now,
                        now,
                        payment["id"],
                    ),
                )
            _audit(
                database,
                tenant_id=identity.tenant_id,
                user_id=identity.user_id,
                actor_type="tbank",
                action="payment.init.rejected",
                payment_intent_id=str(payment["id"]),
                details={"errorCode": result.error_code},
                now=now,
            )
        raise BillingError(
            402,
            "billing_payment_rejected",
            "Банк отклонил создание оплаты.",
        )

    with transaction(database, immediate=True):
        current = database.execute(
            "SELECT * FROM billing_payment_intents WHERE id = ?",
            (payment["id"],),
        ).fetchone()
        assert current is not None
        now = _now(database)
        if result.payment_id is None or result.payment_url is None:
            raise BillingError(
                502,
                "billing_provider_protocol_error",
                "Ответ банка не удалось проверить.",
            )
        bound_payment_id = current["provider_payment_id"]
        if bound_payment_id is not None and not hmac.compare_digest(
            str(bound_payment_id), result.payment_id
        ):
            raise BillingError(
                502,
                "billing_provider_binding_conflict",
                "Ответ банка не соответствует созданной оплате.",
            )
        current_status = str(current["status"])
        next_status = (
            "pending" if current_status in {"initializing", "unknown"} else current_status
        )
        next_provider_status = (
            result.status
            if current_status in {"initializing", "unknown", "pending", "authorized"}
            else current["provider_status"]
        )
        database.execute(
            """
            UPDATE billing_payment_intents
            SET provider_payment_id = COALESCE(provider_payment_id, ?),
                payment_url = COALESCE(payment_url, ?),
                rebill_id = COALESCE(rebill_id, ?),
                customer_key = COALESCE(customer_key, ?),
                status = ?, provider_status = ?, provider_error_code = '0',
                version = version + 1, updated_at = ?, initialized_at = ?
            WHERE id = ?
            """,
            (
                result.payment_id,
                result.payment_url,
                result.rebill_id,
                customer_key,
                next_status,
                next_provider_status,
                now,
                now,
                payment["id"],
            ),
        )
        _audit(
            database,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            actor_type="tbank",
            action="payment.init.accepted",
            payment_intent_id=str(payment["id"]),
            details={"providerStatus": result.status or "NEW"},
            now=now,
        )
        final_row = database.execute(
            "SELECT * FROM billing_payment_intents WHERE id = ?",
            (payment["id"],),
        ).fetchone()
        assert final_row is not None
        return PaymentCreation(
            payment=_payment_view(final_row, include_payment_url=True),
            created=created,
        )


def _target_status(provider_status: str) -> str | None:
    provider_status = provider_status.upper()
    if provider_status in _PENDING_PROVIDER_STATUSES:
        return "pending"
    if provider_status == "AUTHORIZED":
        return "authorized"
    if provider_status == "CONFIRMED":
        return "succeeded"
    if provider_status in _FAILED_PROVIDER_STATUSES:
        return "failed"
    if provider_status in _CANCELED_PROVIDER_STATUSES:
        return "canceled"
    # T-Bank uses PARTIAL_REVERSED for a partial cancellation of an
    # AUTHORIZED payment and PARTIAL_REFUNDED for a partial refund of a
    # CONFIRMED payment. Both are financial reversals, not a canceled order:
    # preserving the partial state keeps the subscription grant alive until
    # the operator receives a full REFUNDED event (or another subscription
    # covers the same entitlement).
    if provider_status == "REFUNDING":
        return "succeeded"
    if provider_status in {"PARTIAL_REVERSED", "PARTIAL_REFUNDED"}:
        return "partially_refunded"
    if provider_status == "REFUNDED":
        return "refunded"
    return None


def _transition_allowed(
    *,
    current: str,
    target: str,
    stored_provider_status: str | None,
    incoming_provider_status: str,
) -> bool:
    if current == "refunded":
        return False
    if current == "partially_refunded":
        return target == "refunded"
    if current == "succeeded":
        return target in {"partially_refunded", "refunded"} or (
            target == "succeeded" and stored_provider_status != incoming_provider_status
        )
    if current == "canceled":
        return target in {"partially_refunded", "refunded"}
    if target == "canceled":
        return current in {
            "initializing",
            "pending",
            "unknown",
            "authorized",
            "failed",
        }
    if target == "succeeded":
        return current not in {"canceled", "partially_refunded", "refunded"}
    if target in {"partially_refunded", "refunded"}:
        return True
    if current == target and stored_provider_status == incoming_provider_status:
        return False
    if current == "authorized" and target == "pending":
        return False
    return current not in {"succeeded", "partially_refunded", "refunded"}


def _ensure_grant_active(
    database: sqlite3.Connection,
    *,
    payment: sqlite3.Row,
    now: int,
) -> None:
    """Activate the entitlement grant for a paid intent (idempotent)."""

    grant = database.execute(
        """
        SELECT status, source
        FROM product_entitlement_grants
        WHERE tenant_id = ? AND user_id = ? AND entitlement_code = ?
        LIMIT 1
        """,
        (
            payment["tenant_id"],
            payment["user_id"],
            payment["entitlement_code"],
        ),
    ).fetchone()
    if grant is None:
        database.execute(
            """
            INSERT INTO product_entitlement_grants (
                tenant_id, user_id, entitlement_code, status, grant_epoch,
                source, created_at, updated_at
            ) VALUES (?, ?, ?, 'active', 1, 'subscription_policy', ?, ?)
            """,
            (
                payment["tenant_id"],
                payment["user_id"],
                payment["entitlement_code"],
                now,
                now,
            ),
        )
    elif str(grant["status"]) == "revoked":
        database.execute(
            """
            UPDATE product_entitlement_grants
            SET status = 'active', grant_epoch = grant_epoch + 1,
                source = 'subscription_policy', updated_at = ?
            WHERE tenant_id = ? AND user_id = ? AND entitlement_code = ?
            """,
            (
                now,
                payment["tenant_id"],
                payment["user_id"],
                payment["entitlement_code"],
            ),
        )


def _activate_subscription(
    database: sqlite3.Connection,
    *,
    payment: sqlite3.Row,
    now: int,
) -> None:
    if str(payment["kind"]) == "recurrent" and payment["recurrent_parent_id"]:
        parent = database.execute(
            """
            SELECT * FROM billing_subscriptions
            WHERE payment_intent_id = ?
            LIMIT 1
            """,
            (payment["recurrent_parent_id"],),
        ).fetchone()
        if parent is not None:
            period_start = max(now, int(parent["current_period_end"]))
            period_end = period_start + int(payment["duration_seconds"])
            database.execute(
                """
                UPDATE billing_subscriptions
                SET status = 'active',
                    current_period_start = ?,
                    current_period_end = ?,
                    rebill_id = COALESCE(?, rebill_id),
                    customer_key = COALESCE(?, customer_key),
                    provider_payment_id = ?,
                    renewal_attempts = 0,
                    last_renewal_intent_id = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    period_start,
                    period_end,
                    payment["rebill_id"],
                    payment["customer_key"],
                    payment["provider_payment_id"],
                    payment["id"],
                    now,
                    parent["id"],
                ),
            )
            _ensure_grant_active(database, payment=payment, now=now)
            _audit(
                database,
                tenant_id=str(payment["tenant_id"]),
                user_id=str(payment["user_id"]),
                actor_type="tbank",
                action="subscription.renewed",
                payment_intent_id=str(payment["id"]),
                details={
                    "entitlement": str(payment["entitlement_code"]),
                    "periodStart": period_start,
                    "periodEnd": period_end,
                    "planCode": str(payment["plan_code"]),
                },
                now=now,
            )
            return
    existing = database.execute(
        """
        SELECT id FROM billing_subscriptions
        WHERE payment_intent_id = ?
        LIMIT 1
        """,
        (payment["id"],),
    ).fetchone()
    if existing is not None:
        return
    policy = database.execute(
        """
        SELECT plan_code FROM platform_tenant_policies
        WHERE tenant_id = ?
        LIMIT 1
        """,
        (payment["tenant_id"],),
    ).fetchone()
    if policy is None:
        raise RuntimeError("billing tenant policy is unavailable")
    latest_period = database.execute(
        """
        SELECT MAX(current_period_end)
        FROM billing_subscriptions
        WHERE tenant_id = ? AND user_id = ? AND status = 'active'
        """,
        (payment["tenant_id"], payment["user_id"]),
    ).fetchone()[0]
    period_start = max(now, int(latest_period)) if latest_period is not None else now
    period_end = period_start + int(payment["duration_seconds"])
    database.execute(
        """
        INSERT INTO billing_subscriptions (
            id, tenant_id, user_id, plan_code, entitlement_code,
            payment_intent_id, status, previous_tenant_plan_code,
            current_period_start, current_period_end, created_at, updated_at,
            auto_renew, rebill_id, customer_key, provider_payment_id
        ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """,
        (
            f"subscription_{uuid.uuid4().hex}",
            payment["tenant_id"],
            payment["user_id"],
            payment["plan_code"],
            payment["entitlement_code"],
            payment["id"],
            str(policy["plan_code"]),
            period_start,
            period_end,
            now,
            now,
            payment["rebill_id"],
            payment["customer_key"],
            payment["provider_payment_id"],
        ),
    )
    _ensure_grant_active(database, payment=payment, now=now)
    database.execute(
        """
        UPDATE platform_tenant_policies
        SET plan_code = ?, revision = revision + 1,
            updated_at = ?, updated_by_user_id = ?
        WHERE tenant_id = ?
        """,
        (
            payment["plan_code"],
            now,
            payment["user_id"],
            payment["tenant_id"],
        ),
    )
    _audit(
        database,
        tenant_id=str(payment["tenant_id"]),
        user_id=str(payment["user_id"]),
        actor_type="tbank",
        action="subscription.activated",
        payment_intent_id=str(payment["id"]),
        details={
            "entitlement": str(payment["entitlement_code"]),
            "periodEnd": period_end,
            "planCode": str(payment["plan_code"]),
        },
        now=now,
    )


def _refund_subscription(
    database: sqlite3.Connection,
    *,
    payment: sqlite3.Row,
    now: int,
) -> None:
    # A renewal intent does not own the subscription row: the row is bound to
    # the original (parent) intent. Match either the charged intent or its
    # recurrent parent so a REFUNDED renewal actually closes the access.
    intent_ids = [str(payment["id"])]
    if str(payment["kind"]) == "recurrent" and payment["recurrent_parent_id"]:
        intent_ids.append(str(payment["recurrent_parent_id"]))
    placeholders = ",".join("?" for _ in intent_ids)
    subscription = database.execute(
        f"""
        SELECT * FROM billing_subscriptions
        WHERE payment_intent_id IN ({placeholders})
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        intent_ids,
    ).fetchone()
    if subscription is None or str(subscription["status"]) == "refunded":
        return
    database.execute(
        """
        UPDATE billing_subscriptions
        SET status = 'refunded', updated_at = ?
        WHERE id = ?
        """,
        (now, subscription["id"]),
    )
    another = database.execute(
        """
        SELECT 1
        FROM billing_subscriptions
        WHERE tenant_id = ? AND user_id = ? AND entitlement_code = ?
          AND id != ? AND status = 'active' AND current_period_end > ?
        LIMIT 1
        """,
        (
            subscription["tenant_id"],
            subscription["user_id"],
            subscription["entitlement_code"],
            subscription["id"],
            now,
        ),
    ).fetchone()
    if another is None:
        database.execute(
            """
            UPDATE product_entitlement_grants
            SET status = 'revoked', grant_epoch = grant_epoch + 1,
                updated_at = ?
            WHERE tenant_id = ? AND user_id = ? AND entitlement_code = ?
              AND status = 'active' AND source = 'subscription_policy'
            """,
            (
                now,
                subscription["tenant_id"],
                subscription["user_id"],
                subscription["entitlement_code"],
            ),
        )
        database.execute(
            """
            UPDATE platform_tenant_policies
            SET plan_code = ?, revision = revision + 1,
                updated_at = ?, updated_by_user_id = ?
            WHERE tenant_id = ? AND plan_code = ?
            """,
            (
                subscription["previous_tenant_plan_code"],
                now,
                subscription["user_id"],
                subscription["tenant_id"],
                subscription["plan_code"],
            ),
        )
    _audit(
        database,
        tenant_id=str(subscription["tenant_id"]),
        user_id=str(subscription["user_id"]),
        actor_type="tbank",
        action="subscription.refunded",
        payment_intent_id=str(payment["id"]),
        details={"entitlementRevoked": another is None},
        now=now,
    )


def _record_renewal_failure(
    database: sqlite3.Connection,
    *,
    payment: sqlite3.Row,
    now: int,
) -> None:
    """Track a rejected recurrent charge and disable auto-renew after N tries."""

    parent_id = payment["recurrent_parent_id"]
    if not parent_id:
        return
    subscription = database.execute(
        """
        SELECT * FROM billing_subscriptions
        WHERE payment_intent_id = ? AND status = 'active'
        LIMIT 1
        """,
        (parent_id,),
    ).fetchone()
    if subscription is None:
        return
    attempts = int(subscription["renewal_attempts"]) + 1
    disable = attempts >= _RENEWAL_MAX_ATTEMPTS
    database.execute(
        """
        UPDATE billing_subscriptions
        SET renewal_attempts = ?, auto_renew = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            attempts,
            0 if disable else int(subscription["auto_renew"]),
            now,
            subscription["id"],
        ),
    )
    _audit(
        database,
        tenant_id=str(payment["tenant_id"]),
        user_id=str(payment["user_id"]),
        actor_type="tbank",
        action="subscription.renewal.failed",
        payment_intent_id=str(payment["id"]),
        details={
            "attempts": attempts,
            "autoRenewDisabled": disable,
            "providerStatus": str(payment["provider_status"]),
        },
        now=now,
    )


def _apply_verified_provider_state(
    database: sqlite3.Connection,
    *,
    payment: sqlite3.Row,
    provider_payment_id: str,
    provider_status: str,
    success: bool,
    error_code: str,
    amount_minor: int,
    expected_terminal_fingerprint: str,
) -> tuple[str, bool]:
    """Apply one signature-verified provider state transition.

    Returns ``(outcome, applied)``. The caller keeps the operation inside the
    same immediate transaction and persists its own event/audit trail, so a
    webhook and a GetState reconciliation share exactly one state authority.
    """

    if not hmac.compare_digest(
        str(payment["terminal_fingerprint"]),
        expected_terminal_fingerprint,
    ):
        raise BillingError(
            409,
            "billing_notification_terminal_conflict",
            "Уведомление относится к другому терминалу.",
        )
    if int(payment["amount_minor"]) != amount_minor:
        raise BillingError(
            409,
            "billing_notification_amount_conflict",
            "Сумма уведомления не совпадает с заказом.",
        )
    existing_payment_id = payment["provider_payment_id"]
    if existing_payment_id is not None and not hmac.compare_digest(
        str(existing_payment_id), provider_payment_id
    ):
        raise BillingError(
            409,
            "billing_notification_payment_conflict",
            "Идентификатор уведомления не совпадает с заказом.",
        )

    normalized_status = provider_status.upper()
    target = _target_status(normalized_status)
    now = _now(database)
    if target is None:
        return "ignored_unknown_status", False
    success_required = normalized_status in (
        _SUCCESS_PROVIDER_STATUSES | _REFUND_PROVIDER_STATUSES
    )
    if success_required and (not success or error_code != "0"):
        raise BillingError(
            409,
            "billing_notification_result_conflict",
            "Статус уведомления не согласован с результатом.",
        )
    allowed = _transition_allowed(
        current=str(payment["status"]),
        target=target,
        stored_provider_status=(
            str(payment["provider_status"])
            if payment["provider_status"] is not None
            else None
        ),
        incoming_provider_status=normalized_status,
    )
    if not allowed:
        return "ignored_out_of_order", False

    database.execute(
        """
        UPDATE billing_payment_intents
        SET provider_payment_id = COALESCE(provider_payment_id, ?),
            status = ?, provider_status = ?, provider_error_code = ?,
            paid_at = CASE
                WHEN ? = 'succeeded' AND ? = 'CONFIRMED'
                    THEN COALESCE(paid_at, ?)
                ELSE paid_at
            END,
            version = version + 1, updated_at = ?
        WHERE id = ?
        """,
        (
            provider_payment_id,
            target,
            normalized_status,
            error_code,
            target,
            normalized_status,
            now,
            now,
            payment["id"],
        ),
    )
    payment = database.execute(
        "SELECT * FROM billing_payment_intents WHERE id = ?",
        (payment["id"],),
    ).fetchone()
    assert payment is not None
    if target == "succeeded" and normalized_status == "CONFIRMED":
        _activate_subscription(database, payment=payment, now=now)
    elif target == "refunded":
        _refund_subscription(database, payment=payment, now=now)
    elif str(payment["kind"]) == "recurrent" and target in {"failed", "canceled"}:
        _record_renewal_failure(database, payment=payment, now=now)
    return "applied", True


def _apply_getstate_result(
    database: sqlite3.Connection,
    *,
    payment: sqlite3.Row,
    state: Any,
    gateway: TBankGateway,
) -> tuple[str, bool]:
    """Bind one GetState response and apply it through the shared authority."""

    if state.order_id is not None and not hmac.compare_digest(
        state.order_id, str(payment["order_id"])
    ):
        raise BillingError(
            409,
            "billing_state_order_conflict",
            "Статус банка относится к другому заказу.",
        )
    if (
        state.amount_minor is not None
        and state.amount_minor != int(payment["amount_minor"])
    ):
        raise BillingError(
            409,
            "billing_state_amount_conflict",
            "Сумма статуса банка не совпадает с заказом.",
        )
    if state.status is None:
        return "ignored_unknown_status", False
    return _apply_verified_provider_state(
        database,
        payment=payment,
        provider_payment_id=str(payment["provider_payment_id"]),
        provider_status=state.status,
        success=state.success,
        error_code=state.error_code,
        amount_minor=state.amount_minor or int(payment["amount_minor"]),
        expected_terminal_fingerprint=gateway.settings.terminal_fingerprint,
    )


def apply_notification(
    database: sqlite3.Connection,
    *,
    notification: VerifiedNotification,
    gateway: TBankGateway,
) -> NotificationOutcome:
    with transaction(database, immediate=True):
        duplicate = database.execute(
            """
            SELECT payment_intent_id, outcome
            FROM billing_notification_events
            WHERE event_digest = ?
            LIMIT 1
            """,
            (notification.event_digest,),
        ).fetchone()
        if duplicate is not None:
            payment = database.execute(
                "SELECT status FROM billing_payment_intents WHERE id = ?",
                (duplicate["payment_intent_id"],),
            ).fetchone()
            return NotificationOutcome(
                payment_intent_id=str(duplicate["payment_intent_id"]),
                status=str(payment["status"]) if payment is not None else "unknown",
                outcome="ignored_duplicate",
            )

        payment = database.execute(
            """
            SELECT * FROM billing_payment_intents
            WHERE provider = 'tbank' AND order_id = ?
            LIMIT 1
            """,
            (notification.order_id,),
        ).fetchone()
        if payment is None:
            raise BillingError(
                404,
                "billing_notification_order_not_found",
                "Платёж для уведомления не найден.",
            )

        # The digest already prevents exact replays; this second key ignores
        # retries whose payload changed an unsigned/extra signed field while
        # still representing the same already-applied provider event.
        applied_duplicate = database.execute(
            """
            SELECT 1
            FROM billing_notification_events
            WHERE payment_intent_id = ?
              AND provider_payment_id = ?
              AND provider_status = ?
              AND outcome = 'applied'
            LIMIT 1
            """,
            (payment["id"], notification.payment_id, notification.status),
        ).fetchone()
        if applied_duplicate is not None:
            current = database.execute(
                "SELECT status FROM billing_payment_intents WHERE id = ?",
                (payment["id"],),
            ).fetchone()
            assert current is not None
            return NotificationOutcome(
                payment_intent_id=str(payment["id"]),
                status=str(current["status"]),
                outcome="ignored_duplicate",
            )

        outcome, _applied = _apply_verified_provider_state(
            database,
            payment=payment,
            provider_payment_id=notification.payment_id,
            provider_status=notification.status,
            success=notification.success,
            error_code=notification.error_code,
            amount_minor=notification.amount_minor,
            expected_terminal_fingerprint=gateway.settings.terminal_fingerprint,
        )
        now = _now(database)
        database.execute(
            """
            INSERT INTO billing_notification_events (
                id, event_digest, payment_intent_id, provider_payment_id,
                provider_status, outcome, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"billing_event_{uuid.uuid4().hex}",
                notification.event_digest,
                payment["id"],
                notification.payment_id,
                notification.status,
                outcome,
                now,
            ),
        )
        _audit(
            database,
            tenant_id=str(payment["tenant_id"]),
            user_id=str(payment["user_id"]),
            actor_type="tbank",
            action=f"payment.notification.{outcome}",
            payment_intent_id=str(payment["id"]),
            details={"providerStatus": notification.status},
            now=now,
        )
        current = database.execute(
            "SELECT status FROM billing_payment_intents WHERE id = ?",
            (payment["id"],),
        ).fetchone()
        assert current is not None
        return NotificationOutcome(
            payment_intent_id=str(payment["id"]),
            status=str(current["status"]),
            outcome=outcome,
        )


def verified_return(
    database: sqlite3.Connection,
    *,
    intent_id: str,
    nonce: str,
) -> tuple[dict[str, Any], int]:
    row = database.execute(
        """
        SELECT payment.id, payment.status,
               EXISTS (
                   SELECT 1 FROM billing_subscriptions AS subscription
                   WHERE subscription.payment_intent_id = payment.id
                     AND subscription.status = 'active'
                     AND subscription.current_period_start <= unixepoch()
                     AND subscription.current_period_end > unixepoch()
               ) AS entitlement_active
        FROM billing_payment_intents AS payment
        WHERE payment.id = ?
        LIMIT 1
        """,
        (intent_id,),
    ).fetchone()
    if row is None:
        raise BillingError(404, "billing_return_not_found", "Платёж не найден.")
    nonce_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    stored = database.execute(
        """
        SELECT return_nonce_hash FROM billing_payment_intents WHERE id = ?
        """,
        (intent_id,),
    ).fetchone()
    assert stored is not None
    if not hmac.compare_digest(str(stored["return_nonce_hash"]), nonce_hash):
        raise BillingError(404, "billing_return_not_found", "Платёж не найден.")
    payment_status = str(row["status"])
    terminal = payment_status in {
        "succeeded",
        "failed",
        "canceled",
        "partially_refunded",
        "refunded",
    }
    return (
        {
            "intentId": str(row["id"]),
            "verifiedStatus": payment_status,
            "entitlementActive": bool(row["entitlement_active"]),
        },
        200 if terminal else 202,
    )


_RECONCILABLE_STATUSES = frozenset(
    {"initializing", "pending", "unknown", "authorized"}
)


@dataclass(frozen=True, slots=True)
class ReconcileSummary:
    scanned: int
    reconciled: int
    failed: int


def reconcile_payments(
    database: sqlite3.Connection,
    *,
    gateway: TBankGateway,
    limit: int = 50,
) -> ReconcileSummary:
    """Restore intent state from the provider when a webhook was missed.

    GetState is only queried for intents that already have a provider
    PaymentId and are not terminal locally. Every provider response is bound
    to the stored terminal, amount, order and payment id before a transition
    is applied through the same state authority as webhooks.
    """

    rows = database.execute(
        """
        SELECT * FROM billing_payment_intents
        WHERE provider = 'tbank'
          AND provider_payment_id IS NOT NULL
          AND status IN ('initializing', 'pending', 'unknown', 'authorized')
        ORDER BY updated_at ASC, id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    summary = ReconcileSummary(scanned=len(rows), reconciled=0, failed=0)

    def bumped(*, failed: int = 0, reconciled: int = 0) -> ReconcileSummary:
        return ReconcileSummary(
            scanned=summary.scanned,
            reconciled=summary.reconciled + reconciled,
            failed=summary.failed + failed,
        )

    for payment in rows:
        try:
            state = gateway.get_state(str(payment["provider_payment_id"]))
        except (TBankTransportError, TBankProtocolError):
            # Transient provider outage: leave the intent for the next run.
            summary = bumped(failed=1)
            continue
        if state.status is None:
            summary = bumped(failed=1)
            continue

        with transaction(database, immediate=True):
            current = database.execute(
                "SELECT * FROM billing_payment_intents WHERE id = ?",
                (payment["id"],),
            ).fetchone()
            assert current is not None
            if str(current["status"]) not in _RECONCILABLE_STATUSES:
                continue
            try:
                outcome, applied = _apply_getstate_result(
                    database,
                    payment=current,
                    state=state,
                    gateway=gateway,
                )
            except BillingError:
                _audit(
                    database,
                    tenant_id=str(payment["tenant_id"]),
                    user_id=str(payment["user_id"]),
                    actor_type="system",
                    action="payment.reconcile.conflict",
                    payment_intent_id=str(payment["id"]),
                    details={
                        "providerStatus": state.status,
                        "reason": "state_conflict",
                    },
                    now=_now(database),
                )
                summary = bumped(failed=1)
                continue
            _audit(
                database,
                tenant_id=str(payment["tenant_id"]),
                user_id=str(payment["user_id"]),
                actor_type="system",
                action=(
                    "payment.reconcile.applied"
                    if applied
                    else "payment.reconcile.unchanged"
                ),
                payment_intent_id=str(payment["id"]),
                details={
                    "providerStatus": state.status,
                    "outcome": outcome,
                },
                now=_now(database),
            )
        if applied:
            summary = bumped(reconciled=1)
    return summary


def refresh_payment_state(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    intent_id: str,
    gateway: TBankGateway,
) -> dict[str, Any]:
    """Ask the provider for the current state of the subject's own intent.

    This is the client-side fallback for a blocked or missed return redirect:
    the app polls this endpoint after payment, and the backend verifies the
    provider response against the stored terminal, order, amount and payment
    id before applying the same state authority as webhooks.
    """

    payment = _load_payment_by_subject(
        database,
        tenant_id=identity.tenant_id,
        user_id=identity.user_id,
        intent_id=intent_id,
    )
    if str(payment["status"]) in {
        "succeeded",
        "failed",
        "canceled",
        "partially_refunded",
        "refunded",
    } or payment["provider_payment_id"] is None:
        return _payment_view(payment, include_payment_url=True)
    try:
        state = gateway.get_state(str(payment["provider_payment_id"]))
    except (TBankTransportError, TBankProtocolError) as exc:
        raise BillingError(
            502,
            "billing_state_unavailable",
            "Банк временно недоступен. Повторите проверку через несколько секунд.",
        ) from exc
    with transaction(database, immediate=True):
        current = database.execute(
            "SELECT * FROM billing_payment_intents WHERE id = ?",
            (payment["id"],),
        ).fetchone()
        assert current is not None
        if str(current["status"]) in {
            "succeeded",
            "failed",
            "canceled",
            "partially_refunded",
            "refunded",
        }:
            return _payment_view(current, include_payment_url=True)
        outcome, applied = _apply_getstate_result(
            database,
            payment=current,
            state=state,
            gateway=gateway,
        )
        _audit(
            database,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            actor_type="user",
            action=(
                "payment.state.refreshed"
                if applied
                else "payment.state.unchanged"
            ),
            payment_intent_id=intent_id,
            details={
                "providerStatus": state.status,
                "outcome": outcome,
            },
            now=_now(database),
        )
        final = database.execute(
            "SELECT * FROM billing_payment_intents WHERE id = ?",
            (payment["id"],),
        ).fetchone()
        assert final is not None
        return _payment_view(final, include_payment_url=True)


def refund_payment(
    database: sqlite3.Connection,
    *,
    intent_id: str,
    gateway: TBankGateway,
) -> dict[str, Any]:
    """Full provider refund of a confirmed payment, owner-initiated only."""

    with transaction(database, immediate=True):
        payment = database.execute(
            "SELECT * FROM billing_payment_intents WHERE id = ?",
            (intent_id,),
        ).fetchone()
        if payment is None:
            raise BillingError(
                404,
                "billing_refund_not_found",
                "Платёж для возврата не найден.",
            )
        status = str(payment["status"])
        if status == "refunded":
            raise BillingError(
                409,
                "billing_refund_already_refunded",
                "Возврат по этому платежу уже выполнен.",
            )
        if status not in {"succeeded", "partially_refunded"}:
            raise BillingError(
                409,
                "billing_refund_state_invalid",
                "Возврат возможен только для подтверждённого платежа.",
            )
        if payment["provider_payment_id"] is None:
            raise BillingError(
                409,
                "billing_refund_unavailable",
                "У платежа нет подтверждённого идентификатора банка.",
            )
        provider_payment_id = str(payment["provider_payment_id"])
        amount_minor = int(payment["amount_minor"])

    try:
        result = gateway.refund_payment(provider_payment_id, amount_minor)
    except (TBankTransportError, TBankProtocolError) as exc:
        _audit(
            database,
            tenant_id=str(payment["tenant_id"]),
            user_id=str(payment["user_id"]),
            actor_type="platform_owner",
            action="payment.refund.failed",
            payment_intent_id=intent_id,
            details={"reason": "provider_unavailable"},
            now=_now(database),
        )
        raise BillingError(
            502,
            "billing_refund_unavailable",
            "Банк не подтвердил возврат. Повторите позже.",
        ) from exc

    if not result.success:
        _audit(
            database,
            tenant_id=str(payment["tenant_id"]),
            user_id=str(payment["user_id"]),
            actor_type="platform_owner",
            action="payment.refund.rejected",
            payment_intent_id=intent_id,
            details={"providerErrorCode": result.error_code},
            now=_now(database),
        )
        raise BillingError(
            409,
            "billing_refund_rejected",
            "Банк отклонил возврат.",
        )

    with transaction(database, immediate=True):
        current = database.execute(
            "SELECT * FROM billing_payment_intents WHERE id = ?",
            (intent_id,),
        ).fetchone()
        assert current is not None
        if str(current["status"]) not in {"succeeded", "partially_refunded"}:
            # A concurrent webhook already finalised the payment; the refund
            # itself succeeded and the returned view reflects the final state.
            return _payment_view(current, include_payment_url=False)
        now = _now(database)
        assert result.status is not None
        if result.status == "REFUNDED":
            database.execute(
                """
                UPDATE billing_payment_intents
                SET status = 'refunded', provider_status = ?,
                    provider_error_code = '0', version = version + 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (result.status, now, intent_id),
            )
            updated = database.execute(
                "SELECT * FROM billing_payment_intents WHERE id = ?",
                (intent_id,),
            ).fetchone()
            assert updated is not None
            _refund_subscription(database, payment=updated, now=now)
            _audit(
                database,
                tenant_id=str(payment["tenant_id"]),
                user_id=str(payment["user_id"]),
                actor_type="platform_owner",
                action="payment.refund.completed",
                payment_intent_id=intent_id,
                details={"providerStatus": result.status},
                now=now,
            )
        else:
            next_status = (
                "partially_refunded"
                if result.status == "PARTIAL_REFUNDED"
                else "succeeded"
            )
            database.execute(
                """
                UPDATE billing_payment_intents
                SET status = ?, provider_status = ?,
                    provider_error_code = '0', version = version + 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (next_status, result.status, now, intent_id),
            )
            _audit(
                database,
                tenant_id=str(payment["tenant_id"]),
                user_id=str(payment["user_id"]),
                actor_type="platform_owner",
                action="payment.refund.initiated",
                payment_intent_id=intent_id,
                details={"providerStatus": result.status},
                now=now,
            )
        final = database.execute(
            "SELECT * FROM billing_payment_intents WHERE id = ?",
            (intent_id,),
        ).fetchone()
        assert final is not None
        return _payment_view(final, include_payment_url=False)


def subscription_views(
    database: sqlite3.Connection,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    values: list[object] = []
    if tenant_id is not None:
        clauses.append("tenant_id = ?")
        values.append(tenant_id)
    if user_id is not None:
        clauses.append("user_id = ?")
        values.append(user_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = database.execute(
        f"""
        SELECT * FROM billing_subscriptions
        {where}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (*values, limit),
    ).fetchall()
    now = _now(database)
    return [_subscription_view(row, now=now) for row in rows]


def _subscription_view(
    row: sqlite3.Row,
    *,
    now: int,
) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "tenantId": str(row["tenant_id"]),
        "userId": str(row["user_id"]),
        "planCode": str(row["plan_code"]),
        "entitlement": str(row["entitlement_code"]),
        "paymentIntentId": str(row["payment_intent_id"]),
        "status": (
            "expired"
            if str(row["status"]) == "active"
            and int(row["current_period_end"]) <= now
            else str(row["status"])
        ),
        "currentPeriodStart": int(row["current_period_start"]),
        "currentPeriodEnd": int(row["current_period_end"]),
        "autoRenew": bool(int(row["auto_renew"])),
        "renewalAttempts": int(row["renewal_attempts"]),
        "nextRenewalAt": int(row["current_period_end"]),
        "rebillConfigured": bool(row["rebill_id"] is not None),
        "lastRenewalIntentId": (
            str(row["last_renewal_intent_id"])
            if row["last_renewal_intent_id"] is not None
            else None
        ),
        "createdAt": int(row["created_at"]),
        "updatedAt": int(row["updated_at"]),
    }


def admin_payment_views(
    database: sqlite3.Connection,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    rows = database.execute(
        """
        SELECT * FROM billing_payment_intents
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [_payment_view(row, include_payment_url=False) for row in rows]


def admin_audit_views(
    database: sqlite3.Connection,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    rows = database.execute(
        """
        SELECT id, tenant_id, user_id, actor_type, action,
               payment_intent_id, details_json, created_at
        FROM billing_audit_events
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "tenantId": str(row["tenant_id"]),
            "userId": str(row["user_id"]) if row["user_id"] is not None else None,
            "actorType": str(row["actor_type"]),
            "action": str(row["action"]),
            "paymentIntentId": (
                str(row["payment_intent_id"])
                if row["payment_intent_id"] is not None
                else None
            ),
            "details": json.loads(str(row["details_json"])),
            "createdAt": int(row["created_at"]),
        }
        for row in rows
    ]


def _renewal_idempotency_key(subscription_id: str, period_end: int) -> str:
    """Stable idempotency key for one renewal period of one subscription."""

    return f"renewal:{subscription_id}:{period_end}"


@dataclass(frozen=True, slots=True)
class RenewalRunSummary:
    scanned: int
    attempted: int
    created: int
    already_in_flight: int
    failed: int
    disabled: int


def subscriptions_due_for_renewal(
    database: sqlite3.Connection,
    *,
    now: int | None = None,
    lead_seconds: int = _RENEWAL_LEAD_SECONDS,
    max_attempts: int = _RENEWAL_MAX_ATTEMPTS,
    limit: int = 50,
) -> list[sqlite3.Row]:
    """Active auto-renew subscriptions that are ready for a RebillId charge."""

    if now is None:
        now = _now(database)
    return database.execute(
        """
        SELECT *
        FROM billing_subscriptions
        WHERE auto_renew = 1
          AND status = 'active'
          AND rebill_id IS NOT NULL
          AND customer_key IS NOT NULL
          AND current_period_end <= ?
          AND renewal_attempts < ?
          AND NOT EXISTS (
              SELECT 1
              FROM billing_payment_intents AS renewal
              WHERE renewal.kind = 'recurrent'
                AND renewal.recurrent_parent_id =
                    billing_subscriptions.payment_intent_id
                AND renewal.status IN (
                    'initializing', 'unknown', 'pending', 'authorized'
                )
          )
        ORDER BY current_period_end ASC
        LIMIT ?
        """,
        (now + lead_seconds, max_attempts, limit),
    ).fetchall()


def _increment_renewal_attempts(
    database: sqlite3.Connection,
    *,
    subscription_id: str,
    now: int,
    max_attempts: int,
) -> bool:
    """Increment failed-renewal attempts; returns True when auto-renew stops."""

    with transaction(database, immediate=True):
        current = database.execute(
            "SELECT * FROM billing_subscriptions WHERE id = ?",
            (subscription_id,),
        ).fetchone()
        if current is None:
            return False
        attempts = int(current["renewal_attempts"]) + 1
        disable = attempts >= max_attempts
        database.execute(
            """
            UPDATE billing_subscriptions
            SET renewal_attempts = ?, auto_renew = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                attempts,
                0 if disable else int(current["auto_renew"]),
                now,
                current["id"],
            ),
        )
        _audit(
            database,
            tenant_id=str(current["tenant_id"]),
            user_id=str(current["user_id"]),
            actor_type="tbank",
            action="subscription.renewal.rejected",
            payment_intent_id=None,
            details={
                "attempts": attempts,
                "autoRenewDisabled": disable,
            },
            now=now,
        )
        return disable


def run_due_renewals(
    database: sqlite3.Connection,
    *,
    gateway: TBankGateway,
    now: int | None = None,
    lead_seconds: int = _RENEWAL_LEAD_SECONDS,
    max_attempts: int = _RENEWAL_MAX_ATTEMPTS,
    limit: int = 50,
) -> RenewalRunSummary:
    """Charge every due RebillId subscription once, durably and idempotently."""

    if now is None:
        now = _now(database)
    due = subscriptions_due_for_renewal(
        database,
        now=now,
        lead_seconds=lead_seconds,
        max_attempts=max_attempts,
        limit=limit,
    )
    summary = RenewalRunSummary(
        scanned=len(due),
        attempted=0,
        created=0,
        already_in_flight=0,
        failed=0,
        disabled=0,
    )

    def bumped(
        *,
        attempted: int = 0,
        created: int = 0,
        already_in_flight: int = 0,
        failed: int = 0,
        disabled: int = 0,
    ) -> RenewalRunSummary:
        return RenewalRunSummary(
            scanned=summary.scanned,
            attempted=summary.attempted + attempted,
            created=summary.created + created,
            already_in_flight=summary.already_in_flight + already_in_flight,
            failed=summary.failed + failed,
            disabled=summary.disabled + disabled,
        )

    for subscription in due:
        user = database.execute(
            "SELECT email, name FROM users WHERE id = ? AND tenant_id = ?",
            (subscription["user_id"], subscription["tenant_id"]),
        ).fetchone()
        if user is None:
            continue
        identity = UserSession(
            user_id=str(subscription["user_id"]),
            tenant_id=str(subscription["tenant_id"]),
            role=UserRole.USER,
            preferred_agent_profile=AgentProfile.AUTO,
            email=str(user["email"]),
            name=str(user["name"]),
        )
        try:
            creation = create_payment(
                database,
                identity=identity,
                plan_code=str(subscription["plan_code"]),
                # RebillId charges never redirect the customer; the surface is
                # only used to shape return URLs and must match the DB CHECK.
                return_surface="pwa",
                idempotency_key=_renewal_idempotency_key(
                    str(subscription["id"]),
                    int(subscription["current_period_end"]),
                ),
                gateway=gateway,
                kind="recurrent",
                recurrent_parent_id=str(subscription["payment_intent_id"]),
                rebill_id=str(subscription["rebill_id"]),
                customer_key=str(subscription["customer_key"]),
            )
        except BillingError:
            summary = bumped(attempted=1, failed=1)
            if _increment_renewal_attempts(
                database,
                subscription_id=str(subscription["id"]),
                now=now,
                max_attempts=max_attempts,
            ):
                summary = RenewalRunSummary(
                    scanned=summary.scanned,
                    attempted=summary.attempted,
                    created=summary.created,
                    already_in_flight=summary.already_in_flight,
                    failed=summary.failed,
                    disabled=summary.disabled + 1,
                )
            continue
        if not creation.created:
            existing_status = str(creation.payment["status"])
            if existing_status in {"failed", "canceled"}:
                summary = bumped(attempted=1, failed=1)
                if _increment_renewal_attempts(
                    database,
                    subscription_id=str(subscription["id"]),
                    now=now,
                    max_attempts=max_attempts,
                ):
                    summary = RenewalRunSummary(
                        scanned=summary.scanned,
                        attempted=summary.attempted,
                        created=summary.created,
                        already_in_flight=summary.already_in_flight,
                        failed=summary.failed,
                        disabled=summary.disabled + 1,
                    )
            else:
                summary = bumped(already_in_flight=1)
            continue
        summary = bumped(attempted=1, created=1)
        with transaction(database, immediate=True):
            database.execute(
                """
                UPDATE billing_subscriptions
                SET last_renewal_intent_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (creation.payment["id"], _now(database), subscription["id"]),
            )
            _audit(
                database,
                tenant_id=str(subscription["tenant_id"]),
                user_id=str(subscription["user_id"]),
                actor_type="tbank",
                action="subscription.renewal.intent_created",
                payment_intent_id=str(creation.payment["id"]),
                details={
                    "planCode": str(subscription["plan_code"]),
                    "amountMinor": int(creation.payment["amountMinor"]),
                },
                now=now,
            )
    return summary


def set_subscription_auto_renew(
    database: sqlite3.Connection,
    *,
    subscription_id: str,
    tenant_id: str,
    user_id: str,
    enabled: bool,
) -> dict[str, Any]:
    """Toggle RebillId auto-renew for a user-owned active subscription."""

    now = _now(database)
    with transaction(database, immediate=True):
        row = database.execute(
            """
            SELECT * FROM billing_subscriptions
            WHERE id = ? AND tenant_id = ? AND user_id = ?
            LIMIT 1
            """,
            (subscription_id, tenant_id, user_id),
        ).fetchone()
        if row is None:
            raise BillingError(
                404,
                "billing_subscription_not_found",
                "Подписка не найдена.",
            )
        if str(row["status"]) != "active":
            raise BillingError(
                409,
                "billing_subscription_not_active",
                "Автопродление доступно только для активной подписки.",
            )
        if enabled and row["rebill_id"] is None:
            raise BillingError(
                409,
                "billing_renewal_unavailable",
                "Автопродление недоступно для этой подписки.",
            )
        database.execute(
            """
            UPDATE billing_subscriptions
            SET auto_renew = ?, updated_at = ?
            WHERE id = ?
            """,
            (1 if enabled else 0, now, row["id"]),
        )
        _audit(
            database,
            tenant_id=tenant_id,
            user_id=user_id,
            actor_type="user",
            action="subscription.auto_renew.updated",
            payment_intent_id=str(row["payment_intent_id"]),
            details={"enabled": enabled},
            now=now,
        )
        refreshed = database.execute(
            "SELECT * FROM billing_subscriptions WHERE id = ?",
            (row["id"],),
        ).fetchone()
        assert refreshed is not None
        return _subscription_view(refreshed, now=now)
