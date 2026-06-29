from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from storage_paths import data_path

DB_PATH = Path(os.getenv("KOLIBRI_DB_PATH", str(data_path("kolibri.db"))))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

TBANK_API_URL = os.getenv("TBANK_API_URL", "https://securepay.tinkoff.ru/v2").rstrip("/")
TBANK_TERMINAL_KEY = os.getenv("TBANK_TERMINAL_KEY", "")
TBANK_PASSWORD = os.getenv("TBANK_PASSWORD", "")
PUBLIC_URL = os.getenv("KOLIBRI_PUBLIC_URL", os.getenv("PUBLIC_URL", "")).rstrip("/")
BILLING_ADMIN_TOKEN = os.getenv("KOLIBRI_BILLING_ADMIN_TOKEN", "")

PRIMARY_OPERATION_INITIATOR_TYPE = "1"
RECURRING_OPERATION_INITIATOR_TYPE = "R"
PAID_NOTIFICATION_STATUSES = {"AUTHORIZED", "CONFIRMED", "COMPLETED"}
FAILED_NOTIFICATION_STATUSES = {
    "REJECTED",
    "CANCELED",
    "DEADLINE_EXPIRED",
    "ATTEMPTS_EXPIRED",
    "REVERSED",
    "REFUNDED",
}


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    amount_kopeks: int
    monthly_limit: str
    primary_use: str
    highlights: tuple[str, ...]


PLANS = {
    "solo": Plan(
        id="solo",
        name="Solo",
        amount_kopeks=int(os.getenv("KOLIBRI_PLAN_SOLO_KOPEKS", "490000")),
        monthly_limit="до 30 смет в месяц",
        primary_use="мастер или небольшой подрядчик",
        highlights=("AI-сметы", "КП и счет", "экспорт PDF"),
    ),
    "team": Plan(
        id="team",
        name="Team",
        amount_kopeks=int(os.getenv("KOLIBRI_PLAN_TEAM_KOPEKS", "1490000")),
        monthly_limit="до 150 смет в месяц",
        primary_use="ремонтная бригада или отдел продаж",
        highlights=("документы пакетом", "база знаний", "приоритетная фабрика"),
    ),
    "studio": Plan(
        id="studio",
        name="Studio",
        amount_kopeks=int(os.getenv("KOLIBRI_PLAN_STUDIO_KOPEKS", "3990000")),
        monthly_limit="безлимитный операционный контур",
        primary_use="строительная компания или проектное бюро",
        highlights=("свой шаблон документов", "онбординг команды", "выделенные сценарии"),
    ),
}


router = APIRouter(prefix="/api/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    plan_id: str = Field(min_length=2, max_length=32)
    email: str = Field(min_length=5, max_length=160, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    company: str = Field(default="", max_length=120)
    name: str = Field(default="", max_length=80)
    phone: str = Field(default="", max_length=40)


class ChargeDueRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)


def init_billing_db() -> None:
    with sqlite3.connect(str(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS billing_subscriptions (
                id TEXT PRIMARY KEY,
                customer_email TEXT NOT NULL,
                customer_name TEXT,
                company TEXT,
                phone TEXT,
                plan_id TEXT NOT NULL,
                plan_name TEXT NOT NULL,
                amount_kopeks INTEGER NOT NULL,
                currency TEXT NOT NULL DEFAULT 'RUB',
                status TEXT NOT NULL,
                customer_key TEXT NOT NULL,
                order_id TEXT,
                payment_id TEXT,
                rebill_id TEXT,
                payment_url TEXT,
                current_period_start REAL,
                current_period_end REAL,
                next_charge_at REAL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS billing_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id TEXT,
                order_id TEXT,
                payment_id TEXT,
                event_type TEXT NOT NULL,
                status TEXT,
                payload_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS billing_leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_email TEXT NOT NULL,
                customer_name TEXT,
                company TEXT,
                phone TEXT,
                plan_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )"""
        )
        conn.commit()


init_billing_db()


def tbank_configured() -> bool:
    return bool(TBANK_TERMINAL_KEY and TBANK_PASSWORD)


def money_rub(amount_kopeks: int) -> str:
    rubles = amount_kopeks // 100
    return f"{rubles:,}".replace(",", " ")


def public_base_url(request: Request) -> str:
    if PUBLIC_URL:
        return PUBLIC_URL
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}".rstrip("/")
    return str(request.base_url).rstrip("/")


def _token_value(value: Any) -> Optional[str]:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def generate_tbank_token(payload: dict[str, Any], password: str = TBANK_PASSWORD) -> str:
    values: dict[str, str] = {}
    for key, value in payload.items():
        if key == "Token":
            continue
        token_value = _token_value(value)
        if token_value is not None:
            values[key] = token_value
    values["Password"] = password
    raw = "".join(values[key] for key in sorted(values))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_tbank_token(payload: dict[str, Any]) -> bool:
    token = payload.get("Token")
    if not token or not TBANK_PASSWORD:
        return False
    expected = generate_tbank_token(payload)
    return hmac.compare_digest(str(token).lower(), expected.lower())


def customer_key(email: str) -> str:
    digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:24]
    return f"cust_{digest}"


def new_order_id(plan_id: str) -> str:
    return f"sub_{plan_id}_{uuid.uuid4().hex[:18]}"[:36]


def plan_to_dict(plan: Plan) -> dict[str, Any]:
    return {
        "id": plan.id,
        "name": plan.name,
        "amount_kopeks": plan.amount_kopeks,
        "price_rub": money_rub(plan.amount_kopeks),
        "interval": "month",
        "monthly_limit": plan.monthly_limit,
        "primary_use": plan.primary_use,
        "highlights": list(plan.highlights),
    }


def insert_event(
    *,
    subscription_id: str | None,
    order_id: str | None,
    payment_id: str | None,
    event_type: str,
    status: str | None,
    payload: dict[str, Any],
) -> None:
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            """INSERT INTO billing_events
               (subscription_id, order_id, payment_id, event_type, status, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (subscription_id, order_id, payment_id, event_type, status, json.dumps(payload, ensure_ascii=False), time.time()),
        )
        conn.commit()


def find_subscription_for_order(order_id: str) -> tuple[sqlite3.Row | None, str | None]:
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM billing_subscriptions WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if row:
            return row, "subscription"
        row = conn.execute(
            """SELECT s.*
               FROM billing_subscriptions s
               JOIN billing_events e ON e.subscription_id = s.id
               WHERE e.order_id = ?
               ORDER BY e.created_at DESC, e.id DESC
               LIMIT 1""",
            (order_id,),
        ).fetchone()
        if row:
            return row, "event"
    return None, None


def successful_notification_already_processed(order_id: str, payment_id: str) -> bool:
    with sqlite3.connect(str(DB_PATH)) as conn:
        row = conn.execute(
            """SELECT 1
               FROM billing_events
               WHERE order_id = ?
                 AND payment_id = ?
                 AND event_type = 'tbank_notification'
                 AND status IN ('AUTHORIZED', 'CONFIRMED', 'COMPLETED')
               LIMIT 1""",
            (order_id, payment_id),
        ).fetchone()
    return row is not None


def validate_notification_terminal(payload: dict[str, Any]) -> None:
    terminal_key = str(payload.get("TerminalKey") or "")
    if not terminal_key:
        raise HTTPException(status_code=400, detail="Missing TerminalKey")
    if TBANK_TERMINAL_KEY and terminal_key != TBANK_TERMINAL_KEY:
        raise HTTPException(status_code=400, detail="Unexpected TerminalKey")


def validate_successful_notification(
    payload: dict[str, Any],
    subscription: sqlite3.Row | None,
) -> None:
    if subscription is None:
        raise HTTPException(status_code=400, detail="Unknown OrderId")
    if not str(payload.get("PaymentId") or ""):
        raise HTTPException(status_code=400, detail="Missing PaymentId")
    if payload.get("Amount") is None:
        raise HTTPException(status_code=400, detail="Missing Amount")
    try:
        amount_kopeks = int(str(payload.get("Amount")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Amount") from exc
    if amount_kopeks != int(subscription["amount_kopeks"]):
        raise HTTPException(status_code=400, detail="Unexpected Amount")


def store_lead(data: CheckoutRequest, plan: Plan) -> None:
    payload = data.model_dump()
    payload["plan_name"] = plan.name
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            """INSERT INTO billing_leads
               (customer_email, customer_name, company, phone, plan_id, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                data.email,
                data.name,
                data.company,
                data.phone,
                plan.id,
                json.dumps(payload, ensure_ascii=False),
                time.time(),
            ),
        )
        conn.commit()


def create_pending_subscription(data: CheckoutRequest, plan: Plan, order_id: str, payment_id: str, payment_url: str) -> str:
    subscription_id = f"sub_{uuid.uuid4().hex[:18]}"
    now = time.time()
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            """INSERT INTO billing_subscriptions
               (id, customer_email, customer_name, company, phone, plan_id, plan_name, amount_kopeks,
                status, customer_key, order_id, payment_id, payment_url, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                subscription_id,
                data.email,
                data.name,
                data.company,
                data.phone,
                plan.id,
                plan.name,
                plan.amount_kopeks,
                "pending_payment",
                customer_key(data.email),
                order_id,
                payment_id,
                payment_url,
                now,
                now,
            ),
        )
        conn.commit()
    return subscription_id


def activate_subscription(
    order_id: str,
    payment_id: str,
    rebill_id: str | None,
    status: str,
    payload: dict[str, Any],
    subscription: sqlite3.Row | None = None,
    match_source: str | None = None,
) -> None:
    now = time.time()
    period_end = datetime.now(timezone.utc) + timedelta(days=30)
    already_processed = successful_notification_already_processed(order_id, payment_id)
    if subscription is None:
        subscription, match_source = find_subscription_for_order(order_id)
    subscription_id = subscription["id"] if subscription else None
    should_extend_period = bool(
        subscription_id
        and not already_processed
        and (match_source == "event" or str(subscription["status"]) != "active")
    )
    with sqlite3.connect(str(DB_PATH)) as conn:
        if subscription_id:
            if should_extend_period:
                conn.execute(
                    """UPDATE billing_subscriptions
                       SET status = ?, payment_id = ?, rebill_id = COALESCE(?, rebill_id),
                           current_period_start = ?, current_period_end = ?, next_charge_at = ?,
                           updated_at = ?
                       WHERE id = ?""",
                    (
                        "active",
                        payment_id,
                        rebill_id,
                        now,
                        period_end.timestamp(),
                        period_end.timestamp(),
                        now,
                        subscription_id,
                    ),
                )
            else:
                conn.execute(
                    """UPDATE billing_subscriptions
                       SET status = ?, payment_id = ?, rebill_id = COALESCE(?, rebill_id), updated_at = ?
                       WHERE id = ?""",
                    ("active", payment_id, rebill_id, now, subscription_id),
                )
        conn.commit()
    insert_event(
        subscription_id=subscription_id,
        order_id=order_id,
        payment_id=payment_id,
        event_type="tbank_notification",
        status=status,
        payload=payload,
    )


def update_failed_subscription(order_id: str, payment_id: str | None, status: str, payload: dict[str, Any]) -> None:
    now = time.time()
    subscription, _ = find_subscription_for_order(order_id)
    subscription_id = subscription["id"] if subscription else None
    with sqlite3.connect(str(DB_PATH)) as conn:
        if subscription_id:
            conn.execute(
                """UPDATE billing_subscriptions
                   SET status = ?, payment_id = COALESCE(?, payment_id), updated_at = ?
                   WHERE id = ?""",
                ("past_due" if status == "REJECTED" else "canceled", payment_id, now, subscription_id),
            )
        conn.commit()
    insert_event(
        subscription_id=subscription_id,
        order_id=order_id,
        payment_id=payment_id,
        event_type="tbank_notification",
        status=status,
        payload=payload,
    )


async def tbank_post(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    signed_payload = {**payload, "Token": generate_tbank_token(payload)}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(f"{TBANK_API_URL}/{method}", json=signed_payload)
        response.raise_for_status()
        return response.json()


async def init_tbank_subscription(data: CheckoutRequest, plan: Plan, request: Request) -> dict[str, Any]:
    base_url = public_base_url(request)
    order_id = new_order_id(plan.id)
    payload = {
        "TerminalKey": TBANK_TERMINAL_KEY,
        "Amount": plan.amount_kopeks,
        "OrderId": order_id,
        "Description": f"Kolibri AI {plan.name} на 1 месяц",
        "CustomerKey": customer_key(data.email),
        "Recurrent": "Y",
        "PayType": "O",
        "Language": "ru",
        "DATA": {"OperationInitiatorType": PRIMARY_OPERATION_INITIATOR_TYPE},
        "NotificationURL": f"{base_url}/api/billing/tbank/notification",
        "SuccessURL": f"{base_url}/?payment=success&order={order_id}",
        "FailURL": f"{base_url}/?payment=fail&order={order_id}",
    }
    result = await tbank_post("Init", payload)
    if not result.get("Success"):
        raise HTTPException(status_code=502, detail=result.get("Message") or result.get("Details") or "T-Bank payment init failed")
    payment_url = result.get("PaymentURL") or result.get("PaymentUrl") or result.get("payment_url")
    payment_id = str(result.get("PaymentId") or "")
    if not payment_url or not payment_id:
        raise HTTPException(status_code=502, detail="T-Bank response does not include PaymentURL or PaymentId")
    subscription_id = create_pending_subscription(data, plan, order_id, payment_id, payment_url)
    insert_event(
        subscription_id=subscription_id,
        order_id=order_id,
        payment_id=payment_id,
        event_type="tbank_init",
        status=str(result.get("Status") or "NEW"),
        payload=result,
    )
    return {
        "mode": "payment",
        "provider": "tbank",
        "subscription_id": subscription_id,
        "order_id": order_id,
        "payment_id": payment_id,
        "payment_url": payment_url,
    }


async def charge_subscription(row: sqlite3.Row) -> dict[str, Any]:
    order_id = new_order_id(row["plan_id"])
    init_payload = {
        "TerminalKey": TBANK_TERMINAL_KEY,
        "Amount": int(row["amount_kopeks"]),
        "OrderId": order_id,
        "Description": f"Kolibri AI {row['plan_name']} продление",
        "CustomerKey": row["customer_key"],
        "PayType": "O",
        "DATA": {"OperationInitiatorType": RECURRING_OPERATION_INITIATOR_TYPE},
    }
    init_result = await tbank_post("Init", init_payload)
    payment_id = str(init_result.get("PaymentId") or "")
    if not init_result.get("Success") or not payment_id:
        insert_event(
            subscription_id=row["id"],
            order_id=order_id,
            payment_id=payment_id or None,
            event_type="tbank_rebill_init_failed",
            status=str(init_result.get("Status") or "failed"),
            payload=init_result,
        )
        return {"subscription_id": row["id"], "charged": False, "stage": "init", "response": init_result}

    charge_payload = {
        "TerminalKey": TBANK_TERMINAL_KEY,
        "PaymentId": payment_id,
        "RebillId": row["rebill_id"],
        "SendEmail": True,
        "InfoEmail": row["customer_email"],
    }
    charge_result = await tbank_post("Charge", charge_payload)
    insert_event(
        subscription_id=row["id"],
        order_id=order_id,
        payment_id=payment_id,
        event_type="tbank_charge",
        status=str(charge_result.get("Status") or ""),
        payload=charge_result,
    )
    return {"subscription_id": row["id"], "charged": bool(charge_result.get("Success")), "response": charge_result}


@router.get("/plans")
async def billing_plans():
    return {
        "provider": "tbank",
        "configured": tbank_configured(),
        "plans": [plan_to_dict(plan) for plan in PLANS.values()],
    }


@router.post("/checkout")
async def create_checkout(data: CheckoutRequest, request: Request):
    plan = PLANS.get(data.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Unknown plan")
    if not tbank_configured():
        store_lead(data, plan)
        return {
            "mode": "lead",
            "provider": "tbank",
            "configured": False,
            "message": "Заявка сохранена. Для оплаты подключите TBANK_TERMINAL_KEY и TBANK_PASSWORD.",
        }
    return await init_tbank_subscription(data, plan, request)


def process_tbank_notification_payload(payload: dict[str, Any]) -> str:
    if not verify_tbank_token(payload):
        raise HTTPException(status_code=400, detail="Invalid T-Bank token")

    order_id = str(payload.get("OrderId") or "")
    payment_id = str(payload.get("PaymentId") or "")
    status = str(payload.get("Status") or "")
    rebill_id = payload.get("RebillId")

    if not order_id:
        raise HTTPException(status_code=400, detail="Missing OrderId")

    validate_notification_terminal(payload)

    if status in PAID_NOTIFICATION_STATUSES and str(payload.get("Success", "")).lower() == "true":
        subscription, match_source = find_subscription_for_order(order_id)
        validate_successful_notification(payload, subscription)
        activate_subscription(
            order_id,
            payment_id,
            str(rebill_id) if rebill_id else None,
            status,
            payload,
            subscription=subscription,
            match_source=match_source,
        )
    elif status in FAILED_NOTIFICATION_STATUSES:
        update_failed_subscription(order_id, payment_id or None, status, payload)
    else:
        insert_event(
            subscription_id=None,
            order_id=order_id,
            payment_id=payment_id or None,
            event_type="tbank_notification",
            status=status,
            payload=payload,
        )
    return "OK"


@router.post("/tbank/notification", response_class=PlainTextResponse)
async def tbank_notification(request: Request):
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
    else:
        form = await request.form()
        payload = dict(form)
    return process_tbank_notification_payload(payload)


@router.post("/tbank/charge-due")
async def charge_due_subscriptions(
    data: ChargeDueRequest,
    x_kolibri_billing_token: str | None = Header(default=None),
):
    if not BILLING_ADMIN_TOKEN or x_kolibri_billing_token != BILLING_ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Billing admin token required")
    if not tbank_configured():
        raise HTTPException(status_code=503, detail="T-Bank credentials are not configured")

    now = time.time()
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT * FROM billing_subscriptions
               WHERE status = 'active'
                 AND rebill_id IS NOT NULL
                 AND next_charge_at IS NOT NULL
                 AND next_charge_at <= ?
               ORDER BY next_charge_at ASC
               LIMIT ?""",
            (now, data.limit),
        ).fetchall()

    results = []
    for row in rows:
        results.append(await charge_subscription(row))
    return {"processed": len(results), "results": results}
