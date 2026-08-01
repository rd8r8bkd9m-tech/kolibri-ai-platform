from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from app.billing.config import TBankSettings
from app.billing.service import _provider_payload, _target_status
from app.billing.tbank import (
    TBankGateway,
    TBankProtocolError,
    VerifiedNotification,
    make_token,
    verify_notification,
)
from app.config import Settings
from app.database import connect_database, initialize_database, migration_paths
from app.main import create_app
from app.owner_bootstrap import promote_registered_owner
from app.schemas import AgentProfile, UserRole, UserSession
from fastapi.testclient import TestClient


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"
IDEMPOTENCY_KEY = "billing-test-idempotency-0001"


def _register(client: TestClient, *, email: str, name: str) -> dict[str, str]:
    response = client.post(
        "/v1/auth/register",
        headers=ORIGIN,
        json={"email": email, "name": name, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]


def _mutation_headers(client: TestClient, *, key: str = IDEMPOTENCY_KEY) -> dict[str, str]:
    return {
        **ORIGIN,
        "X-CSRF-Token": str(client.cookies.get("kolibri_v3_csrf")),
        "Idempotency-Key": key,
    }


def _seed_plans(database_path: Path) -> None:
    database = connect_database(database_path)
    try:
        now = int(database.execute("SELECT unixepoch()").fetchone()[0])
        database.executemany(
            """
            INSERT INTO billing_plans (
                code, display_name, amount_minor, currency, duration_seconds,
                entitlement_code, receipt_item_name, receipt_tax,
                receipt_payment_method, receipt_payment_object, active,
                revision, created_at, updated_at
            ) VALUES (?, ?, ?, 'RUB', ?, 'construction.estimates.use', ?,
                      'none', 'full_payment', 'service', 1, 1, ?, ?)
            """,
            (
                (
                    "kolibri.pro.monthly",
                    "Kolibri Pro",
                    199_00,
                    30 * 24 * 60 * 60,
                    "Подписка Kolibri Pro",
                    now,
                    now,
                ),
                (
                    "kolibri.team.monthly",
                    "Kolibri Team",
                    499_00,
                    30 * 24 * 60 * 60,
                    "Подписка Kolibri Team",
                    now,
                    now,
                ),
            ),
        )
    finally:
        database.close()


def _signed_notification(
    gateway: TBankGateway,
    *,
    order_id: str,
    status: str,
    payment_id: str = "1234567890",
    amount_minor: int = 199_00,
    success: bool = True,
    error_code: str = "0",
    marker: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "TerminalKey": gateway.settings.terminal_key,
        "OrderId": order_id,
        "Success": success,
        "Status": status,
        "PaymentId": payment_id,
        "ErrorCode": error_code,
        "Amount": amount_minor,
        # Nested data is intentionally ignored by T-Bank token rules and by
        # Kolibri's state authority.
        "Data": {"source": "cards"},
    }
    if marker is not None:
        payload["NotificationType"] = marker
    assert gateway.settings.password is not None
    payload["Token"] = make_token(payload, gateway.settings.password)
    return payload


def test_official_init_token_vector_excludes_nested_receipt_and_data() -> None:
    payload = {
        "TerminalKey": "MerchantTerminalKey",
        "Amount": 19200,
        "OrderId": "00000",
        "Description": "Подарочная карта на 1000 рублей",
        "Receipt": {"Items": [{"Amount": 19200}]},
        "DATA": {"opaque": "value"},
    }
    assert make_token(payload, "11111111111111") == (
        "72dd466f8ace0a37a1f740ce5fb78101712bc0665d91a8108c7c8a0ccd426db2"
    )

    gateway = TBankGateway(TBankSettings.for_testing())
    notification: dict[str, object] = {
        "TerminalKey": gateway.settings.terminal_key,
        "OrderId": "kv3-official-string-shape",
        "Success": "true",
        "Status": "AUTHORIZED",
        "PaymentId": "1234567890",
        "ErrorCode": "0",
        "Amount": "19900",
    }
    assert gateway.settings.password is not None
    notification["Token"] = make_token(
        notification, gateway.settings.password
    )
    assert verify_notification(
        notification, gateway.settings
    ).amount_minor == 19_900


def test_init_response_is_bound_to_terminal_order_and_amount() -> None:
    def wrong_amount(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "Success": True,
                "ErrorCode": "0",
                "TerminalKey": "TestMerchantTerminal",
                "Status": "NEW",
                "PaymentId": "1234567890",
                "OrderId": "kv3-bound-order",
                "Amount": 19_901,
                "PaymentURL": "https://securepayments.tinkoff.ru/session/test",
            },
        )

    gateway = TBankGateway(
        TBankSettings.for_testing(),
        transport=httpx.MockTransport(wrong_amount),
    )
    with pytest.raises(TBankProtocolError, match="amount is mismatched"):
        gateway.init_payment(
            {
                "TerminalKey": "TestMerchantTerminal",
                "OrderId": "kv3-bound-order",
                "Amount": 19_900,
            }
        )


def test_tbank_configuration_fences_real_charges_and_redacts_secret() -> None:
    settings = TBankSettings.for_testing(password="not-visible-in-repr")
    assert "not-visible-in-repr" not in repr(settings)
    assert settings.base_url == "https://rest-api-test.tinkoff.ru/v2"

    with pytest.raises(ValueError, match="credentials are incomplete"):
        TBankSettings.for_testing(password="x" * 21)

    with pytest.raises(ValueError, match="real charges are not confirmed"):
        TBankSettings(
            enabled=True,
            mode="production",
            terminal_key="RealTerminal",
            password="server-secret",
            notification_url="https://example.ru/v1/billing/tbank/notifications",
            return_origin="https://example.ru",
            runtime_environment="production",
        )

    with pytest.raises(ValueError, match="must use HTTPS"):
        TBankSettings(
            enabled=True,
            mode="production",
            terminal_key="RealTerminal",
            password="server-secret",
            notification_url="http://127.0.0.1/notify",
            return_origin="http://127.0.0.1",
            runtime_environment="production",
            production_confirmed=True,
        )

    with pytest.raises(ValueError, match="must use kolibriai.ru"):
        TBankSettings(
            enabled=True,
            mode="production",
            terminal_key="RealTerminal",
            password="server-secret",
            notification_url="https://example.ru/api/v3/billing/tbank/notifications",
            return_origin="https://example.ru",
            runtime_environment="production",
            production_confirmed=True,
        )


def test_required_receipt_uses_approved_minor_units_and_fiscal_fields() -> None:
    gateway = TBankGateway(
        TBankSettings.for_testing(
            receipt_mode="required",
            taxation="usn_income",
        )
    )
    identity = UserSession(
        user_id="user_receipt",
        tenant_id="tenant_receipt",
        role=UserRole.USER,
        preferred_agent_profile=AgentProfile.AUTO,
        email="receipt@example.com",
        name="Receipt customer",
    )
    payload = _provider_payload(
        gateway=gateway,
        identity=identity,
        payment={  # type: ignore[arg-type]
            "id": "payment_intent_0123456789abcdef0123456789abcdef",
            "order_id": "kv3-0123456789abcdef0123456789abcdef",
            "plan_display_name": "Kolibri Pro",
            "amount_minor": 19_900,
            "receipt_item_name": "Подписка Kolibri Pro",
            "receipt_tax": "none",
            "receipt_payment_method": "full_payment",
            "receipt_payment_object": "service",
            "return_surface": "web",
        },
        nonce="a" * 64,
    )
    assert payload["Amount"] == 19_900
    assert payload["Receipt"] == {
        "Email": "receipt@example.com",
        "Taxation": "usn_income",
        "Items": [
            {
                "Name": "Подписка Kolibri Pro",
                "Price": 19_900,
                "Quantity": 1,
                "Amount": 19_900,
                "Tax": "none",
                "PaymentMethod": "full_payment",
                "PaymentObject": "service",
            }
        ],
    }
    assert gateway.settings.password is not None
    without_receipt = {key: value for key, value in payload.items() if key != "Receipt"}
    assert make_token(payload, gateway.settings.password) == make_token(
        without_receipt, gateway.settings.password
    )


@pytest.mark.parametrize("status", ["PARTIAL_REVERSED", "PARTIAL_REFUNDED"])
def test_partial_reversal_is_not_misclassified_as_canceled(status: str) -> None:
    notification = VerifiedNotification(
        terminal_key="TestMerchantTerminal",
        order_id="order",
        payment_id="1",
        status=status,
        success=True,
        error_code="0",
        amount_minor=19900,
        event_digest="a" * 64,
    )
    assert _target_status(notification) == "partially_refunded"


def test_billing_migration_is_append_only_empty_catalog_and_fenced(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "billing-migration.db"
    initialize_database(database_path)
    database = connect_database(database_path)
    try:
        latest = int(migration_paths()[-1].name.split("_", 1)[0])
        assert database.execute("PRAGMA user_version").fetchone()[0] == latest == 47
        assert database.execute("SELECT COUNT(*) FROM billing_plans").fetchone()[0] == 0
        assert database.execute(
            "SELECT code FROM billing_entitlement_catalog WHERE active = 1"
        ).fetchone()[0] == "construction.estimates.use"
        _seed_plans(database_path)
        with pytest.raises(
            sqlite3.IntegrityError,
            match="billing plan update requires next revision",
        ):
            database.execute(
                "UPDATE billing_plans SET amount_minor = amount_minor + 1"
            )
    finally:
        database.close()


def test_hosted_payment_webhook_replay_refund_and_admin_contracts(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "billing-flow.db"
    settings = Settings.for_testing(
        database_url=database_path,
        bootstrap_owner_email="owner@example.com",
    )
    provider_requests: list[dict[str, object]] = []

    def provider(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://rest-api-test.tinkoff.ru/v2/Init"
        body = json.loads(request.content)
        assert isinstance(body, dict)
        provider_requests.append(body)
        unsigned = {key: value for key, value in body.items() if key != "Token"}
        assert body["Token"] == make_token(unsigned, "test-server-password")
        assert "CardData" not in body
        assert body["PayType"] == "O"
        assert "Recurrent" not in body
        assert "CustomerKey" not in body
        assert "RebillId" not in body
        return httpx.Response(
            200,
            json={
                "Success": True,
                "ErrorCode": "0",
                "TerminalKey": "TestMerchantTerminal",
                "Status": "NEW",
                "PaymentId": "1234567890",
                "OrderId": body["OrderId"],
                "Amount": body["Amount"],
                "PaymentURL": "https://securepayments.tinkoff.ru/session/test-only",
            },
        )

    gateway = TBankGateway(
        TBankSettings.for_testing(),
        transport=httpx.MockTransport(provider),
    )
    app = create_app(settings)
    app.state.tbank_gateway = gateway

    with TestClient(app) as customer:
        _seed_plans(database_path)
        public_plans = customer.get("/v1/billing/plans")
        assert public_plans.status_code == 200
        assert public_plans.headers["cache-control"] == "no-store"
        assert [item["code"] for item in public_plans.json()["items"]] == [
            "kolibri.pro.monthly",
            "kolibri.team.monthly",
        ]

        subject = _register(
            customer,
            email="customer@example.com",
            name="Customer",
        )

        no_csrf = customer.post(
            "/v1/billing/payment-intents",
            headers={**ORIGIN, "Idempotency-Key": IDEMPOTENCY_KEY},
            json={"planCode": "kolibri.pro.monthly"},
        )
        assert no_csrf.status_code == 403

        invalid_key = customer.post(
            "/v1/billing/payment-intents",
            headers=_mutation_headers(customer, key="billing key with spaces"),
            json={"planCode": "kolibri.pro.monthly"},
        )
        assert invalid_key.status_code == 422

        initialized = customer.post(
            "/v1/billing/payment-intents",
            headers=_mutation_headers(customer),
            json={
                "planCode": "kolibri.pro.monthly",
                "returnSurface": "pwa",
            },
        )
        assert initialized.status_code == 201, initialized.text
        assert initialized.headers["cache-control"] == "no-store"
        payment = initialized.json()
        assert payment["status"] == "pending"
        assert payment["amountMinor"] == 199_00
        assert payment["currency"] == "RUB"
        assert payment["paymentUrl"].startswith(
            "https://securepayments.tinkoff.ru/"
        )
        assert len(provider_requests) == 1
        assert "Receipt" not in provider_requests[0]

        replay = customer.post(
            "/v1/billing/payment-intents",
            headers=_mutation_headers(customer),
            json={
                "planCode": "kolibri.pro.monthly",
                "returnSurface": "pwa",
            },
        )
        assert replay.status_code == 200
        assert replay.json()["id"] == payment["id"]
        assert len(provider_requests) == 1

        surface_conflict = customer.post(
            "/v1/billing/payment-intents",
            headers=_mutation_headers(customer),
            json={"planCode": "kolibri.pro.monthly"},
        )
        assert surface_conflict.status_code == 409

        conflict = customer.post(
            "/v1/billing/payment-intents",
            headers=_mutation_headers(customer),
            json={
                "planCode": "kolibri.team.monthly",
                "returnSurface": "pwa",
            },
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "billing_idempotency_conflict"

        assert customer.get("/v1/session").json()["user"]["entitlements"] == []

        success_url = str(provider_requests[0]["SuccessURL"])
        parsed_return = urlsplit(success_url)
        return_query = parse_qs(parsed_return.query)
        assert parsed_return.path == (
            f"/api/v3/billing/tbank/return/{payment['id']}"
        )
        assert return_query["returnSurface"] == ["pwa"]
        return_path = f"/v1/billing/tbank/return/{payment['id']}"
        pending_return = customer.get(
            return_path,
            params={
                "nonce": return_query["nonce"][0],
                # A provider landing result is never payment authority.
                "providerResult": "success",
            },
        )
        assert pending_return.status_code == 202
        assert pending_return.headers["cache-control"] == "no-store"
        assert pending_return.json() == {
            "intentId": payment["id"],
            "verifiedStatus": "pending",
            "entitlementActive": False,
        }

        order_id = str(provider_requests[0]["OrderId"])
        invalid = _signed_notification(
            gateway,
            order_id=order_id,
            status="CONFIRMED",
        )
        invalid["Token"] = "0" * 64
        rejected = customer.post(
            "/v1/billing/tbank/notifications",
            json=invalid,
        )
        assert rejected.status_code == 400
        assert rejected.json()["code"] == "billing_notification_signature_invalid"
        assert customer.get("/v1/session").json()["user"]["entitlements"] == []

        wrong_amount = customer.post(
            "/v1/billing/tbank/notifications",
            json=_signed_notification(
                gateway,
                order_id=order_id,
                status="AUTHORIZED",
                amount_minor=199_01,
            ),
        )
        assert wrong_amount.status_code == 409
        assert wrong_amount.json()["code"] == "billing_notification_amount_conflict"

        authorized = customer.post(
            "/v1/billing/tbank/notifications",
            json=_signed_notification(
                gateway,
                order_id=order_id,
                status="AUTHORIZED",
            ),
        )
        assert authorized.status_code == 200
        assert customer.get(
            f"/v1/billing/payment-intents/{payment['id']}"
        ).json()["status"] == "authorized"
        assert customer.get("/v1/session").json()["user"]["entitlements"] == []

        confirmed_payload = _signed_notification(
            gateway,
            order_id=order_id,
            status="CONFIRMED",
        )
        confirmed = customer.post(
            "/v1/billing/tbank/notifications",
            json=confirmed_payload,
        )
        assert confirmed.status_code == 200
        assert confirmed.text == "OK"
        assert customer.get("/v1/session").json()["user"]["entitlements"] == [
            "construction.estimates.use"
        ]

        verified = customer.get(
            return_path,
            params={
                "nonce": return_query["nonce"][0],
                # Even a forged fail hint cannot override verified server state.
                "providerResult": "fail",
            },
        )
        assert verified.status_code == 200
        assert verified.json()["verifiedStatus"] == "succeeded"
        assert verified.json()["entitlementActive"] is True

        late_authorized = customer.post(
            "/v1/billing/tbank/notifications",
            json=_signed_notification(
                gateway,
                order_id=order_id,
                status="AUTHORIZED",
                marker="Payment",
            ),
        )
        assert late_authorized.status_code == 200
        assert customer.get(
            f"/v1/billing/payment-intents/{payment['id']}"
        ).json()["status"] == "succeeded"

        duplicate = customer.post(
            "/v1/billing/tbank/notifications",
            json=confirmed_payload,
        )
        assert duplicate.status_code == 200

        database = connect_database(database_path)
        try:
            assert database.execute(
                "SELECT COUNT(*) FROM billing_subscriptions"
            ).fetchone()[0] == 1
            assert database.execute(
                "SELECT COUNT(*) FROM billing_notification_events"
            ).fetchone()[0] == 3
            database.execute(
                """
                UPDATE billing_subscriptions
                SET current_period_start = unixepoch() - 7200,
                    current_period_end = unixepoch() - 1
                WHERE payment_intent_id = ?
                """,
                (payment["id"],),
            )
        finally:
            database.close()

        # Expired billing periods stop projecting access even before cleanup.
        assert customer.get("/v1/session").json()["user"]["entitlements"] == []
        subscriptions = customer.get("/v1/billing/subscriptions")
        assert subscriptions.headers["cache-control"] == "no-store"
        subscription = subscriptions.json()["items"][0]
        assert subscription["status"] == "expired"

        refunded = customer.post(
            "/v1/billing/tbank/notifications",
            json=_signed_notification(
                gateway,
                order_id=order_id,
                status="REFUNDED",
            ),
        )
        assert refunded.status_code == 200
        final_payment = customer.get(
            f"/v1/billing/payment-intents/{payment['id']}"
        ).json()
        assert final_payment["status"] == "refunded"
        assert customer.get("/v1/session").json()["user"]["entitlements"] == []

    with TestClient(app) as another_tenant:
        _register(
            another_tenant,
            email="other@example.com",
            name="Other tenant",
        )
        assert another_tenant.get("/v1/platform-admin/billing/plans").status_code == 403
        hidden = another_tenant.get(
            f"/v1/billing/payment-intents/{payment['id']}"
        )
        assert hidden.status_code == 404

    with TestClient(app) as owner:
        _register(owner, email="owner@example.com", name="Owner")
        promote_registered_owner(settings, email="owner@example.com")
        config = owner.get("/v1/platform-admin/billing/config")
        assert config.status_code == 200
        assert config.json() == {
            "status": "configured",
            "mode": "test",
            "receiptMode": "disabled",
            "productionConfirmed": False,
        }
        catalog = owner.get("/v1/platform-admin/billing/plans")
        assert catalog.status_code == 200
        assert catalog.headers["cache-control"] == "no-store"
        assert [item["code"] for item in catalog.json()["items"]] == [
            "kolibri.pro.monthly",
            "kolibri.team.monthly",
        ]
        assert catalog.json()["items"][0]["active"] is True
        assert catalog.json()["items"][0]["entitlementActive"] is True
        payments = owner.get("/v1/platform-admin/billing/payments")
        assert payments.status_code == 200
        [admin_payment] = payments.json()["items"]
        assert admin_payment["id"] == payment["id"]
        assert "paymentUrl" not in admin_payment
        assert owner.get("/v1/platform-admin/billing/subscriptions").status_code == 200
        audit = owner.get("/v1/platform-admin/billing/audit")
        assert audit.status_code == 200
        assert any(
            item["action"] == "subscription.activated"
            for item in audit.json()["items"]
        )

    database = connect_database(database_path)
    try:
        row = database.execute(
            """
            SELECT status, source
            FROM product_entitlement_grants
            WHERE tenant_id = ? AND user_id = ?
            """,
            (subject["tenantId"], subject["id"]),
        ).fetchone()
        assert tuple(row) == ("revoked", "subscription_policy")
        terminal_values = database.execute(
            """
            SELECT terminal_fingerprint, request_hash, return_nonce_hash
            FROM billing_payment_intents
            """
        ).fetchone()
        assert all(len(str(value)) in {16, 64} for value in terminal_values)
        assert hashlib.sha256(b"test-server-password").hexdigest() not in {
            str(value) for value in terminal_values
        }
    finally:
        database.close()


@pytest.mark.parametrize(
    ("provider_response", "expected_http", "expected_code", "stored_status"),
    [
        (
            {"Success": False, "ErrorCode": "105", "Status": "REJECTED"},
            402,
            "billing_payment_rejected",
            "failed",
        ),
        (None, 202, None, "unknown"),
    ],
)
def test_failed_or_uncertain_init_is_durable_and_never_auto_retried(
    tmp_path: Path,
    provider_response: dict[str, object] | None,
    expected_http: int,
    expected_code: str | None,
    stored_status: str,
) -> None:
    database_path = tmp_path / f"billing-{stored_status}.db"
    settings = Settings.for_testing(database_url=database_path)
    calls = 0

    def provider(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if provider_response is None:
            raise httpx.ConnectError("test transport unavailable", request=request)
        return httpx.Response(200, json=provider_response)

    gateway = TBankGateway(
        TBankSettings.for_testing(),
        transport=httpx.MockTransport(provider),
    )
    app = create_app(settings)
    app.state.tbank_gateway = gateway
    with TestClient(app) as client:
        _register(client, email="payer@example.com", name="Payer")
        _seed_plans(database_path)
        first = client.post(
            "/v1/billing/payment-intents",
            headers=_mutation_headers(client, key=f"{IDEMPOTENCY_KEY}-{stored_status}"),
            json={"planCode": "kolibri.pro.monthly"},
        )
        assert first.status_code == expected_http
        if expected_code is None:
            assert first.json()["status"] == stored_status
            assert first.json()["paymentUrl"] is None
        else:
            assert first.json()["code"] == expected_code
        assert calls == 1

        replay = client.post(
            "/v1/billing/payment-intents",
            headers=_mutation_headers(client, key=f"{IDEMPOTENCY_KEY}-{stored_status}"),
            json={"planCode": "kolibri.pro.monthly"},
        )
        assert replay.status_code == (202 if stored_status == "unknown" else 200)
        assert replay.json()["status"] == stored_status
        assert replay.json()["paymentUrl"] is None
        assert calls == 1

    database = connect_database(database_path)
    try:
        assert database.execute(
            "SELECT status FROM billing_payment_intents"
        ).fetchone()[0] == stored_status
        action = (
            "payment.init.rejected"
            if stored_status == "failed"
            else "payment.init.uncertain"
        )
        assert database.execute(
            "SELECT COUNT(*) FROM billing_audit_events WHERE action = ?",
            (action,),
        ).fetchone()[0] == 1
    finally:
        database.close()
