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


def load_billing(monkeypatch, tmp_path: Path, *, terminal_key: str = "", password: str = ""):
    monkeypatch.setenv("KOLIBRI_DB_PATH", str(tmp_path / "billing.db"))
    monkeypatch.delenv("KOLIBRI_PUBLIC_URL", raising=False)
    monkeypatch.delenv("PUBLIC_URL", raising=False)

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
