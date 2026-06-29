from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import sqlite3
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def load_billing(
    monkeypatch,
    tmp_path: Path,
    *,
    terminal_key: str = "",
    password: str = "",
    public_url: str = "",
    admin_token: str = "",
):
    monkeypatch.setenv("KOLIBRI_DB_PATH", str(tmp_path / "billing.db"))
    if public_url:
        monkeypatch.setenv("KOLIBRI_PUBLIC_URL", public_url)
    else:
        monkeypatch.delenv("KOLIBRI_PUBLIC_URL", raising=False)
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    if admin_token:
        monkeypatch.setenv("KOLIBRI_BILLING_ADMIN_TOKEN", admin_token)
    else:
        monkeypatch.delenv("KOLIBRI_BILLING_ADMIN_TOKEN", raising=False)

    if terminal_key:
        monkeypatch.setenv("TBANK_TERMINAL_KEY", terminal_key)
    else:
        monkeypatch.delenv("TBANK_TERMINAL_KEY", raising=False)

    if password:
        monkeypatch.setenv("TBANK_PASSWORD", password)
    else:
        monkeypatch.delenv("TBANK_PASSWORD", raising=False)

    if "billing" in sys.modules:
        return importlib.reload(sys.modules["billing"])
    return importlib.import_module("billing")


def signed_payload(billing, payload: dict) -> dict:
    return {**payload, "Token": billing.generate_tbank_token(payload)}


def fetch_subscription(billing, subscription_id: str):
    with sqlite3.connect(str(billing.DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM billing_subscriptions WHERE id = ?",
            (subscription_id,),
        ).fetchone()


def test_tbank_token_generation_uses_sorted_flat_values(tmp_path: Path, monkeypatch):
    billing = load_billing(monkeypatch, tmp_path, terminal_key="TerminalDemo", password="secret")
    payload = {
        "TerminalKey": "TerminalDemo",
        "Amount": 490000,
        "OrderId": "sub_solo_test",
        "Description": "Kolibri AI Solo",
        "Success": True,
        "DATA": {"ignored": "nested"},
        "Receipt": ["ignored"],
        "Optional": None,
        "Token": "ignored-existing-token",
    }

    expected_raw = "490000Kolibri AI Solosub_solo_testsecrettrueTerminalDemo"
    assert billing.generate_tbank_token(payload) == hashlib.sha256(expected_raw.encode("utf-8")).hexdigest()


def test_tbank_token_verification_is_case_insensitive_and_detects_tampering(tmp_path: Path, monkeypatch):
    billing = load_billing(monkeypatch, tmp_path, terminal_key="TerminalDemo", password="secret")
    payload = {
        "TerminalKey": "TerminalDemo",
        "Amount": 1490000,
        "OrderId": "sub_team_test",
        "PaymentId": "987654321",
        "Status": "CONFIRMED",
        "Success": True,
    }
    signed_payload = {**payload, "Token": billing.generate_tbank_token(payload).upper()}

    assert billing.verify_tbank_token(signed_payload)
    assert not billing.verify_tbank_token({**signed_payload, "Amount": 1490001})


def test_checkout_falls_back_to_lead_mode_without_tbank_credentials(tmp_path: Path, monkeypatch):
    billing = load_billing(monkeypatch, tmp_path)

    async def fail_tbank_post(*args, **kwargs):
        raise AssertionError("fallback lead mode must not call T-Bank")

    monkeypatch.setattr(billing, "tbank_post", fail_tbank_post)
    data = billing.CheckoutRequest(
        plan_id="solo",
        email="lead@example.com",
        company="Kolibri",
        name="Alex",
        phone="+79990000000",
    )

    result = asyncio.run(billing.create_checkout(data, request=None))

    assert result == {
        "mode": "lead",
        "provider": "tbank",
        "configured": False,
        "message": "Заявка сохранена. Для оплаты подключите TBANK_TERMINAL_KEY и TBANK_PASSWORD.",
    }
    with sqlite3.connect(str(billing.DB_PATH)) as conn:
        lead = conn.execute(
            """SELECT customer_email, customer_name, company, phone, plan_id, payload_json
               FROM billing_leads"""
        ).fetchone()
        subscription_count = conn.execute("SELECT COUNT(*) FROM billing_subscriptions").fetchone()[0]

    assert lead[:5] == ("lead@example.com", "Alex", "Kolibri", "+79990000000", "solo")
    assert json.loads(lead[5]) == {
        "plan_id": "solo",
        "email": "lead@example.com",
        "company": "Kolibri",
        "name": "Alex",
        "phone": "+79990000000",
        "plan_name": "Solo",
    }
    assert subscription_count == 0


def test_checkout_payment_mode_sends_recurrent_operation_initiator_type(
    tmp_path: Path,
    monkeypatch,
):
    billing = load_billing(
        monkeypatch,
        tmp_path,
        terminal_key="TerminalDemo",
        password="secret",
        public_url="https://kolibri.example",
    )
    calls = []

    async def fake_tbank_post(method, payload):
        calls.append((method, payload))
        return {
            "Success": True,
            "Status": "NEW",
            "PaymentId": "pay_123",
            "PaymentURL": "https://pay.example/123",
        }

    monkeypatch.setattr(billing, "tbank_post", fake_tbank_post)
    data = billing.CheckoutRequest(plan_id="solo", email="buyer@example.com")

    result = asyncio.run(billing.create_checkout(data, request=None))

    assert result["mode"] == "payment"
    assert calls[0][0] == "Init"
    assert calls[0][1]["Recurrent"] == "Y"
    assert calls[0][1]["DATA"] == {"OperationInitiatorType": "1"}


def test_success_notification_rejects_amount_mismatch_before_activation(
    tmp_path: Path,
    monkeypatch,
):
    billing = load_billing(monkeypatch, tmp_path, terminal_key="TerminalDemo", password="secret")
    data = billing.CheckoutRequest(plan_id="solo", email="buyer@example.com")
    subscription_id = billing.create_pending_subscription(
        data,
        billing.PLANS["solo"],
        "sub_solo_amount_check",
        "pay_init",
        "https://pay.example/init",
    )
    payload = signed_payload(
        billing,
        {
            "TerminalKey": "TerminalDemo",
            "OrderId": "sub_solo_amount_check",
            "PaymentId": "pay_confirm",
            "Status": "CONFIRMED",
            "Success": True,
            "Amount": billing.PLANS["solo"].amount_kopeks + 1,
        },
    )

    try:
        billing.process_tbank_notification_payload(payload)
    except billing.HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "Unexpected Amount"
    else:
        raise AssertionError("amount mismatch must not activate subscription")

    assert fetch_subscription(billing, subscription_id)["status"] == "pending_payment"


def test_success_notification_requires_payment_id_before_activation(
    tmp_path: Path,
    monkeypatch,
):
    billing = load_billing(monkeypatch, tmp_path, terminal_key="TerminalDemo", password="secret")
    data = billing.CheckoutRequest(plan_id="solo", email="buyer@example.com")
    subscription_id = billing.create_pending_subscription(
        data,
        billing.PLANS["solo"],
        "sub_solo_missing_payment",
        "pay_init",
        "https://pay.example/init",
    )
    payload = signed_payload(
        billing,
        {
            "TerminalKey": "TerminalDemo",
            "OrderId": "sub_solo_missing_payment",
            "Status": "CONFIRMED",
            "Success": True,
            "Amount": billing.PLANS["solo"].amount_kopeks,
        },
    )

    try:
        billing.process_tbank_notification_payload(payload)
    except billing.HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "Missing PaymentId"
    else:
        raise AssertionError(
            "successful notification without PaymentId must not activate subscription"
        )

    assert fetch_subscription(billing, subscription_id)["status"] == "pending_payment"


def test_duplicate_success_notification_does_not_extend_initial_period_again(
    tmp_path: Path,
    monkeypatch,
):
    billing = load_billing(monkeypatch, tmp_path, terminal_key="TerminalDemo", password="secret")
    data = billing.CheckoutRequest(plan_id="solo", email="buyer@example.com")
    subscription_id = billing.create_pending_subscription(
        data,
        billing.PLANS["solo"],
        "sub_solo_duplicate",
        "pay_init",
        "https://pay.example/init",
    )
    payload = signed_payload(
        billing,
        {
            "TerminalKey": "TerminalDemo",
            "OrderId": "sub_solo_duplicate",
            "PaymentId": "pay_confirm",
            "Status": "CONFIRMED",
            "Success": True,
            "Amount": billing.PLANS["solo"].amount_kopeks,
            "RebillId": "rebill_123",
        },
    )

    assert billing.process_tbank_notification_payload(payload) == "OK"
    with sqlite3.connect(str(billing.DB_PATH)) as conn:
        conn.execute(
            """UPDATE billing_subscriptions
               SET current_period_end = ?, next_charge_at = ?
               WHERE id = ?""",
            (123.0, 123.0, subscription_id),
        )
        conn.commit()

    assert billing.process_tbank_notification_payload(payload) == "OK"

    subscription = fetch_subscription(billing, subscription_id)
    assert subscription["status"] == "active"
    assert subscription["current_period_end"] == 123.0
    assert subscription["next_charge_at"] == 123.0


def test_rebill_init_sends_recurring_operation_initiator_type_and_notification_maps_order(
    tmp_path: Path,
    monkeypatch,
):
    billing = load_billing(monkeypatch, tmp_path, terminal_key="TerminalDemo", password="secret")
    data = billing.CheckoutRequest(plan_id="solo", email="buyer@example.com")
    subscription_id = billing.create_pending_subscription(
        data,
        billing.PLANS["solo"],
        "sub_solo_initial",
        "pay_init",
        "https://pay.example/init",
    )
    initial_payload = signed_payload(
        billing,
        {
            "TerminalKey": "TerminalDemo",
            "OrderId": "sub_solo_initial",
            "PaymentId": "pay_initial",
            "Status": "CONFIRMED",
            "Success": True,
            "Amount": billing.PLANS["solo"].amount_kopeks,
            "RebillId": "rebill_123",
        },
    )
    assert billing.process_tbank_notification_payload(initial_payload) == "OK"
    subscription = fetch_subscription(billing, subscription_id)
    calls = []

    async def fake_tbank_post(method, payload):
        calls.append((method, payload))
        if method == "Init":
            return {"Success": True, "Status": "NEW", "PaymentId": "pay_rebill"}
        return {"Success": True, "Status": "CONFIRMED"}

    monkeypatch.setattr(billing, "tbank_post", fake_tbank_post)
    result = asyncio.run(billing.charge_subscription(subscription))

    assert result["charged"] is True
    assert calls[0][0] == "Init"
    assert calls[0][1]["DATA"] == {"OperationInitiatorType": "R"}
    rebill_order_id = calls[0][1]["OrderId"]
    rebill_payload = signed_payload(
        billing,
        {
            "TerminalKey": "TerminalDemo",
            "OrderId": rebill_order_id,
            "PaymentId": "pay_rebill",
            "Status": "CONFIRMED",
            "Success": True,
            "Amount": billing.PLANS["solo"].amount_kopeks,
        },
    )

    assert billing.process_tbank_notification_payload(rebill_payload) == "OK"
    subscription = fetch_subscription(billing, subscription_id)
    assert subscription["status"] == "active"
    assert subscription["payment_id"] == "pay_rebill"
