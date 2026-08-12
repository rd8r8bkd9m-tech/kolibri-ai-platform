from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from app.billing.config import TBankSettings
from app.billing.service import (
    _provider_payload,
    _target_status,
    run_due_renewals,
)
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

    with pytest.raises(ValueError, match="TLS verification"):
        TBankSettings(
            enabled=True,
            mode="production",
            terminal_key="RealTerminal",
            password="server-secret",
            notification_url="https://kolibriai.ru/api/v3/billing/tbank/notifications",
            return_origin="https://kolibriai.ru",
            timeout_seconds=5,
            verify_ssl=False,
            runtime_environment="production",
            production_confirmed=True,
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


@pytest.mark.parametrize(
    (
        "mode",
        "terminal_key",
        "runtime_environment",
        "production_confirmed",
        "notification_url",
        "return_origin",
        "expected_host",
    ),
    [
        (
            "test",
            "TestMerchantTerminal",
            "test",
            False,
            "http://localhost/v1/billing/tbank/notifications",
            "http://localhost",
            "rest-api-test.tinkoff.ru",
        ),
        (
            "demo",
            "DemoMerchantDEMO",
            "test",
            False,
            "http://localhost/v1/billing/tbank/notifications",
            "http://localhost",
            "securepay.tinkoff.ru",
        ),
        (
            "production",
            "ProdMerchantTerminal",
            "production",
            True,
            "https://kolibriai.ru/api/v3/billing/tbank/notifications",
            "https://kolibriai.ru",
            "securepay.tinkoff.ru",
        ),
    ],
)
def test_init_payment_url_is_issued_for_supported_tbank_modes(
    mode: str,
    terminal_key: str,
    runtime_environment: str,
    production_confirmed: bool,
    notification_url: str,
    return_origin: str,
    expected_host: str,
) -> None:
    settings = TBankSettings.for_testing(
        mode=mode,  # type: ignore[arg-type]
        terminal_key=terminal_key,
        runtime_environment=runtime_environment,  # type: ignore[arg-type]
        production_confirmed=production_confirmed,
        notification_url=notification_url,
        return_origin=return_origin,
    )
    requested_urls: list[str] = []

    def provider(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        request_body = json.loads(request.content)
        assert request_body["TerminalKey"] == terminal_key
        assert request_body["Amount"] == 19900
        return httpx.Response(
            200,
            json={
                "Success": True,
                "ErrorCode": "0",
                "TerminalKey": terminal_key,
                "Status": "NEW",
                "PaymentId": "1234567890",
                "OrderId": request_body["OrderId"],
                "Amount": request_body["Amount"],
                "PaymentURL": "https://securepayments.tinkoff.ru/session/mode-smoke",
            },
        )

    gateway = TBankGateway(
        settings,
        transport=httpx.MockTransport(provider),
    )
    result = gateway.init_payment(
        {
            "TerminalKey": terminal_key,
            "Amount": 19900,
            "OrderId": "tv3-payment-url-smoke",
        }
    )
    assert result.success is True
    assert result.payment_url == "https://securepayments.tinkoff.ru/session/mode-smoke"
    assert requested_urls == [f"{settings.base_url}/Init"]
    assert expected_host in requested_urls[0]


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
    assert _target_status(notification.status) == "partially_refunded"


def test_billing_migration_is_append_only_empty_catalog_and_fenced(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "billing-migration.db"
    initialize_database(database_path)
    database = connect_database(database_path)
    try:
        latest = int(migration_paths()[-1].name.split("_", 1)[0])
        assert database.execute("PRAGMA user_version").fetchone()[0] == latest
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
        TBankSettings.for_testing(recurring_enabled=False),
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
            # A retry with a changed extra signed field is still the same
            # already applied provider event and must not create a second
            # notification row or duplicate audit effect.
            assert database.execute(
                "SELECT COUNT(*) FROM billing_notification_events"
            ).fetchone()[0] == 2
            assert database.execute(
                """
                SELECT COUNT(*) FROM billing_audit_events
                WHERE action = 'payment.notification.applied'
                """
            ).fetchone()[0] == 2
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
        config_body = config.json()
        assert config_body["status"] == "configured"
        assert config_body["source"] == "env"
        assert config_body["mode"] == "test"
        assert config_body["receiptMode"] == "disabled"
        assert config_body["productionConfirmed"] is False
        assert config_body["verifySsl"] is True
        assert config_body["terminalFingerprint"].endswith("…")
        assert config_body["updatedAt"] is None
        assert "password" not in config_body
        assert "terminalKey" not in config_body
        assert config_body == {
            "status": "configured",
            "source": "env",
            "mode": "test",
            "receiptMode": "disabled",
            "productionConfirmed": False,
            "verifySsl": True,
            "terminalFingerprint": config_body["terminalFingerprint"],
            "updatedAt": None,
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


def test_recurring_rebill_extends_subscription(tmp_path: Path) -> None:
    database_path = tmp_path / "recurring-cycle.db"
    settings = Settings.for_testing(database_url=database_path)
    provider_requests: list[dict[str, object]] = []

    def provider(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://rest-api-test.tinkoff.ru/v2/Init"
        body = json.loads(request.content)
        provider_requests.append(body)
        response: dict[str, object] = {
            "Success": True,
            "ErrorCode": "0",
            "TerminalKey": "TestMerchantTerminal",
            "Status": "NEW",
            "PaymentId": f"payment-{len(provider_requests)}",
            "OrderId": body["OrderId"],
            "Amount": body["Amount"],
            "PaymentURL": "https://securepayments.tinkoff.ru/session/recurring-test",
        }
        if body.get("Recurrent") == "Y":
            response["RebillId"] = "test-rebill-0001"
        return httpx.Response(200, json=response)

    gateway = TBankGateway(
        TBankSettings.for_testing(recurring_enabled=True),
        transport=httpx.MockTransport(provider),
    )
    app = create_app(settings)
    app.state.tbank_gateway = gateway
    with TestClient(app) as client:
        _seed_plans(database_path)
        _register(client, email="recurring@example.com", name="Recurring")
        initialized = client.post(
            "/v1/billing/payment-intents",
            headers=_mutation_headers(client, key=f"{IDEMPOTENCY_KEY}-recurring"),
            json={"planCode": "kolibri.pro.monthly"},
        )
        assert initialized.status_code == 201, initialized.text
        initial = initialized.json()
        assert provider_requests[0]["Recurrent"] == "Y"
        assert str(provider_requests[0]["CustomerKey"]).startswith("kv3-")
        order_id = str(provider_requests[0]["OrderId"])
        confirmed = client.post(
            "/v1/billing/tbank/notifications",
            json=_signed_notification(
                gateway,
                order_id=order_id,
                status="CONFIRMED",
                payment_id="payment-1",
            ),
        )
        assert confirmed.status_code == 200
        subscriptions = client.get("/v1/billing/subscriptions").json()["items"]
        assert len(subscriptions) == 1
        subscription = subscriptions[0]
        assert subscription["status"] == "active"
        assert subscription["autoRenew"] is True
        assert subscription["rebillConfigured"] is True
        assert subscription["renewalAttempts"] == 0

        database = connect_database(database_path)
        try:
            database.execute(
                """
                UPDATE billing_subscriptions
                SET current_period_start = unixepoch() - 7200,
                    current_period_end = unixepoch() - 1
                """
            )
            summary = run_due_renewals(database, gateway=gateway)
            assert summary.scanned == 1
            assert summary.created == 1
            assert summary.failed == 0
            recurrent = database.execute(
                "SELECT * FROM billing_payment_intents WHERE kind = 'recurrent'"
            ).fetchone()
            assert recurrent is not None
            assert recurrent["recurrent_parent_id"] == initial["id"]
            assert recurrent["rebill_id"] == "test-rebill-0001"
            assert provider_requests[1]["Recurrent"] == "Y"
            assert provider_requests[1]["RebillId"] == "test-rebill-0001"
            recurrent_order = str(recurrent["order_id"])
            recurrent_id = str(recurrent["id"])
            subscription_id = str(
                database.execute(
                    "SELECT id FROM billing_subscriptions"
                ).fetchone()[0]
            )
            before_end = int(
                database.execute(
                    "SELECT current_period_end FROM billing_subscriptions"
                ).fetchone()[0]
            )
        finally:
            database.close()

        renewed = client.post(
            "/v1/billing/tbank/notifications",
            json=_signed_notification(
                gateway,
                order_id=recurrent_order,
                status="CONFIRMED",
                payment_id="payment-2",
            ),
        )
        assert renewed.status_code == 200
        subscriptions_response = client.get("/v1/billing/subscriptions")
        assert subscriptions_response.status_code == 200, subscriptions_response.text
        subscriptions = subscriptions_response.json()["items"]
        assert [item["id"] for item in subscriptions] == [subscription_id]
        assert subscriptions[0]["status"] == "active"
        assert subscriptions[0]["renewalAttempts"] == 0
        assert client.get("/v1/session").json()["user"]["entitlements"] == [
            "construction.estimates.use"
        ]

    database = connect_database(database_path)
    try:
        row = database.execute(
            "SELECT * FROM billing_subscriptions WHERE id = ?",
            (subscription_id,),
        ).fetchone()
        # The renewal extends from max(now, old period end). Under a loaded
        # test runner several wall-clock seconds may elapse between the
        # snapshot and the CONFIRMED notification, so assert the full renewal
        # window rather than an exact second.
        assert (
            before_end + 30 * 24 * 60 * 60
            <= row["current_period_end"]
            <= before_end + 30 * 24 * 60 * 60 + 5
        )
        assert row["last_renewal_intent_id"] == recurrent_id
        assert row["provider_payment_id"] == "payment-2"
        assert database.execute(
            "SELECT COUNT(*) FROM billing_subscriptions"
        ).fetchone()[0] == 1
        assert database.execute(
            "SELECT COUNT(*) FROM billing_audit_events "
            "WHERE action = 'subscription.renewed'"
        ).fetchone()[0] == 1
    finally:
        database.close()


def test_renewal_rejections_disable_auto_renew_after_max_attempts(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "recurring-reject.db"
    settings = Settings.for_testing(database_url=database_path)
    accepted_requests = 0
    rejected_requests = 0

    def accepted_provider(request: httpx.Request) -> httpx.Response:
        nonlocal accepted_requests
        accepted_requests += 1
        body = json.loads(request.content)
        response: dict[str, object] = {
            "Success": True,
            "ErrorCode": "0",
            "TerminalKey": "TestMerchantTerminal",
            "Status": "NEW",
            "PaymentId": "payment-1",
            "OrderId": body["OrderId"],
            "Amount": body["Amount"],
            "PaymentURL": "https://securepayments.tinkoff.ru/session/recurring-test",
        }
        if body.get("Recurrent") == "Y":
            response["RebillId"] = "test-rebill-reject"
        return httpx.Response(200, json=response)

    accepted_gateway = TBankGateway(
        TBankSettings.for_testing(recurring_enabled=True),
        transport=httpx.MockTransport(accepted_provider),
    )
    app = create_app(settings)
    app.state.tbank_gateway = accepted_gateway
    with TestClient(app) as client:
        _seed_plans(database_path)
        _register(client, email="reject@example.com", name="Reject")
        initialized = client.post(
            "/v1/billing/payment-intents",
            headers=_mutation_headers(client, key=f"{IDEMPOTENCY_KEY}-reject"),
            json={"planCode": "kolibri.pro.monthly"},
        )
        assert initialized.status_code == 201, initialized.text

    # The initial order id is not directly exposed by the client response, so
    # re-read it from the durable intent row instead of guessing.
    database = connect_database(database_path)
    try:
        initial = database.execute(
            "SELECT * FROM billing_payment_intents "
            "WHERE kind = 'initial'"
        ).fetchone()
        assert initial is not None
        order_id = str(initial["order_id"])
    finally:
        database.close()

    with TestClient(app) as client:
        confirmed = client.post(
            "/v1/billing/tbank/notifications",
            json=_signed_notification(
                accepted_gateway,
                order_id=order_id,
                status="CONFIRMED",
                payment_id="payment-1",
            ),
        )
        assert confirmed.status_code == 200

    database = connect_database(database_path)
    try:
        database.execute(
            """
            UPDATE billing_subscriptions
            SET current_period_start = unixepoch() - 7200,
                current_period_end = unixepoch() - 1
            """
        )
        subscription_id = str(
            database.execute(
                "SELECT id FROM billing_subscriptions"
            ).fetchone()[0]
        )
    finally:
        database.close()

    def rejecting_provider(request: httpx.Request) -> httpx.Response:
        nonlocal rejected_requests
        rejected_requests += 1
        return httpx.Response(
            200,
            json={
                "Success": False,
                "ErrorCode": "105",
                "Status": "REJECTED",
            },
        )

    rejected_gateway = TBankGateway(
        TBankSettings.for_testing(recurring_enabled=True),
        transport=httpx.MockTransport(rejecting_provider),
    )
    database = connect_database(database_path)
    try:
        for step in range(1, 6):
            summary = run_due_renewals(database, gateway=rejected_gateway)
            assert summary.attempted == 1
            assert summary.failed == 1
            row = database.execute(
                "SELECT * FROM billing_subscriptions WHERE id = ?",
                (subscription_id,),
            ).fetchone()
            assert row["renewal_attempts"] == step
            assert row["auto_renew"] == (0 if step == 5 else 1)
        assert rejected_requests == 1
        assert database.execute(
            "SELECT status FROM billing_subscriptions WHERE id = ?",
            (subscription_id,),
        ).fetchone()[0] == "active"
        assert database.execute(
            "SELECT COUNT(*) FROM billing_audit_events "
            "WHERE action = 'subscription.renewal.rejected'"
        ).fetchone()[0] == 5
    finally:
        database.close()


def test_auto_renew_toggle_and_admin_renewals_run(tmp_path: Path) -> None:
    database_path = tmp_path / "recurring-toggle.db"
    settings = Settings.for_testing(
        database_url=database_path,
        bootstrap_owner_email="owner@example.com",
    )
    provider_requests: list[dict[str, object]] = []

    def provider(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        provider_requests.append(body)
        response: dict[str, object] = {
            "Success": True,
            "ErrorCode": "0",
            "TerminalKey": "TestMerchantTerminal",
            "Status": "NEW",
            "PaymentId": "payment-1",
            "OrderId": body["OrderId"],
            "Amount": body["Amount"],
            "PaymentURL": "https://securepayments.tinkoff.ru/session/recurring-test",
        }
        if body.get("Recurrent") == "Y":
            response["RebillId"] = "test-rebill-toggle"
        return httpx.Response(200, json=response)

    gateway = TBankGateway(
        TBankSettings.for_testing(recurring_enabled=True),
        transport=httpx.MockTransport(provider),
    )
    app = create_app(settings)
    app.state.tbank_gateway = gateway
    with TestClient(app) as client:
        _seed_plans(database_path)
        _register(client, email="toggle@example.com", name="Toggle")
        initialized = client.post(
            "/v1/billing/payment-intents",
            headers=_mutation_headers(client, key=f"{IDEMPOTENCY_KEY}-toggle"),
            json={"planCode": "kolibri.pro.monthly"},
        )
        assert initialized.status_code == 201, initialized.text
        confirmed = client.post(
            "/v1/billing/tbank/notifications",
            json=_signed_notification(
                gateway,
                order_id=str(provider_requests[0]["OrderId"]),
                status="CONFIRMED",
                payment_id="payment-1",
            ),
        )
        assert confirmed.status_code == 200
        subscription = client.get("/v1/billing/subscriptions").json()["items"][0]
        assert subscription["autoRenew"] is True
        assert subscription["rebillConfigured"] is True

        toggled = client.post(
            f"/v1/billing/subscriptions/{subscription['id']}/auto-renew",
            headers=_mutation_headers(client, key=f"{IDEMPOTENCY_KEY}-toggle-off"),
            json={"enabled": False},
        )
        assert toggled.status_code == 200
        assert toggled.json()["autoRenew"] is False
        assert toggled.json()["id"] == subscription["id"]

        no_csrf = client.post(
            f"/v1/billing/subscriptions/{subscription['id']}/auto-renew",
            headers=ORIGIN,
            json={"enabled": True},
        )
        assert no_csrf.status_code == 403

        not_owner = client.post(
            "/v1/platform-admin/billing/renewals/run",
            headers=_mutation_headers(client, key=f"{IDEMPOTENCY_KEY}-not-owner"),
            json={},
        )
        assert not_owner.status_code == 403

    with TestClient(app) as owner:
        _register(owner, email="owner@example.com", name="Owner")
        promote_registered_owner(settings, email="owner@example.com")
        run = owner.post(
            "/v1/platform-admin/billing/renewals/run",
            headers=_mutation_headers(owner, key=f"{IDEMPOTENCY_KEY}-owner-run"),
            json={},
        )
        assert run.status_code == 200
        assert run.json() == {
            "scanned": 0,
            "attempted": 0,
            "created": 0,
            "alreadyInFlight": 0,
            "failed": 0,
            "disabled": 0,
        }


def test_reconcile_getstate_owner_refund_and_payment_history(
    tmp_path: Path,
) -> None:
    """A missed webhook is recovered via GetState and owner refund closes it."""

    database_path = tmp_path / "reconcile-refund.db"
    settings = Settings.for_testing(
        database_url=database_path,
        bootstrap_owner_email="owner@example.com",
    )
    provider_requests: list[dict[str, object]] = []
    known_order_id: dict[str, str] = {}

    def provider(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert isinstance(body, dict)
        provider_requests.append(body)
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "Init":
            order_id = str(body["OrderId"])
            known_order_id["order"] = order_id
            return httpx.Response(
                200,
                json={
                    "Success": True,
                    "ErrorCode": "0",
                    "TerminalKey": "TestMerchantTerminal",
                    "Status": "NEW",
                    "PaymentId": "reconcile-pay-1",
                    "OrderId": order_id,
                    "Amount": body["Amount"],
                    "PaymentURL": (
                        "https://securepayments.tinkoff.ru/session/reconcile"
                    ),
                },
            )
        if method == "GetState":
            return httpx.Response(
                200,
                json={
                    "Success": True,
                    "ErrorCode": "0",
                    "TerminalKey": "TestMerchantTerminal",
                    "Status": "CONFIRMED",
                    "PaymentId": "reconcile-pay-1",
                    "OrderId": known_order_id.get("order", "kv3-missing"),
                    "Amount": 199_00,
                },
            )
        if method == "Refund":
            return httpx.Response(
                200,
                json={
                    "Success": True,
                    "ErrorCode": "0",
                    "TerminalKey": "TestMerchantTerminal",
                    "Status": "REFUNDED",
                    "PaymentId": "reconcile-pay-1",
                    "OrderId": known_order_id.get("order", "kv3-missing"),
                    "Amount": body["Amount"],
                },
            )
        raise AssertionError(f"unexpected provider method: {method}")

    gateway = TBankGateway(
        TBankSettings.for_testing(recurring_enabled=False),
        transport=httpx.MockTransport(provider),
    )
    app = create_app(settings)
    app.state.tbank_gateway = gateway

    with TestClient(app) as customer:
        _seed_plans(database_path)
        subject = _register(
            customer,
            email="reconcile@example.com",
            name="Reconcile",
        )
        initialized = customer.post(
            "/v1/billing/payment-intents",
            headers=_mutation_headers(customer, key=f"{IDEMPOTENCY_KEY}-reconcile"),
            json={"planCode": "kolibri.pro.monthly"},
        )
        assert initialized.status_code == 201, initialized.text
        payment = initialized.json()
        assert payment["status"] == "pending"
        assert payment["paidAt"] is None

        # A user-facing history endpoint is scoped to the subject and never
        # exposes a hosted payment URL.
        history = customer.get("/v1/billing/payments")
        assert history.status_code == 200
        assert len(history.json()["items"]) == 1
        assert history.json()["items"][0]["id"] == payment["id"]
        assert "paymentUrl" not in history.json()["items"][0]

        # Refund of a non-confirmed payment must be rejected before any
        # provider call.
        assert len(provider_requests) == 1

    with TestClient(app) as other:
        _register(other, email="other-reconcile@example.com", name="Other")
        hidden = other.get("/v1/billing/payments")
        assert hidden.status_code == 200
        assert hidden.json()["items"] == []

    with TestClient(app) as owner:
        _register(owner, email="owner@example.com", name="Owner")
        promote_registered_owner(settings, email="owner@example.com")

        early_refund = owner.post(
            f"/v1/platform-admin/billing/payments/{payment['id']}/refund",
            headers=_mutation_headers(owner, key=f"{IDEMPOTENCY_KEY}-early-refund"),
            json={},
        )
        assert early_refund.status_code == 409
        assert early_refund.json()["code"] == "billing_refund_state_invalid"

        reconcile = owner.post(
            "/v1/platform-admin/billing/reconcile",
            headers=_mutation_headers(owner, key=f"{IDEMPOTENCY_KEY}-reconcile-run"),
            json={},
        )
        assert reconcile.status_code == 200, reconcile.text
        assert reconcile.json() == {"scanned": 1, "reconciled": 1, "failed": 0}

        # Owner admin payments list is the correct redacted read model.
        admin_payments = owner.get("/v1/platform-admin/billing/payments")
        assert admin_payments.status_code == 200
        [admin_payment] = admin_payments.json()["items"]
        assert admin_payment["status"] == "succeeded"
        assert admin_payment["paidAt"] is not None
        assert "paymentUrl" not in admin_payment

        refund = owner.post(
            f"/v1/platform-admin/billing/payments/{payment['id']}/refund",
            headers=_mutation_headers(owner, key=f"{IDEMPOTENCY_KEY}-refund"),
            json={},
        )
        assert refund.status_code == 200, refund.text
        assert refund.json()["status"] == "refunded"
        assert refund.json()["providerStatus"] == "REFUNDED"

        duplicate_refund = owner.post(
            f"/v1/platform-admin/billing/payments/{payment['id']}/refund",
            headers=_mutation_headers(owner, key=f"{IDEMPOTENCY_KEY}-refund-again"),
            json={},
        )
        assert duplicate_refund.status_code == 409
        assert duplicate_refund.json()["code"] == "billing_refund_already_refunded"

    database = connect_database(database_path)
    try:
        grant = database.execute(
            """
            SELECT status, source
            FROM product_entitlement_grants
            WHERE tenant_id = ? AND user_id = ?
            """,
            (subject["tenantId"], subject["id"]),
        ).fetchone()
        assert tuple(grant) == ("revoked", "subscription_policy")
        assert database.execute(
            "SELECT COUNT(*) FROM billing_audit_events "
            "WHERE action IN ('payment.reconcile.applied', "
            "'payment.refund.completed')"
        ).fetchone()[0] == 2
    finally:
        database.close()


def test_refunded_renewal_revokes_the_parent_subscription(
    tmp_path: Path,
) -> None:
    """A REFUNDED renewal notification closes the subscription it extended."""

    database_path = tmp_path / "renewal-refund.db"
    settings = Settings.for_testing(database_url=database_path)
    provider_requests: list[dict[str, object]] = []

    def provider(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert isinstance(body, dict)
        provider_requests.append(body)
        return httpx.Response(
            200,
            json={
                "Success": True,
                "ErrorCode": "0",
                "TerminalKey": "TestMerchantTerminal",
                "Status": "NEW",
                "PaymentId": f"payment-{len(provider_requests)}",
                "OrderId": body["OrderId"],
                "Amount": body["Amount"],
                "PaymentURL": (
                    "https://securepayments.tinkoff.ru/session/renewal-refund"
                ),
                **(
                    {"RebillId": "test-rebill-refund"}
                    if body.get("Recurrent") == "Y"
                    else {}
                ),
            },
        )

    gateway = TBankGateway(
        TBankSettings.for_testing(recurring_enabled=True),
        transport=httpx.MockTransport(provider),
    )
    app = create_app(settings)
    app.state.tbank_gateway = gateway
    with TestClient(app) as client:
        _seed_plans(database_path)
        subject = _register(
            client,
            email="renewal-refund@example.com",
            name="Renewal Refund",
        )
        initialized = client.post(
            "/v1/billing/payment-intents",
            headers=_mutation_headers(
                client,
                key=f"{IDEMPOTENCY_KEY}-renewal-refund",
            ),
            json={"planCode": "kolibri.pro.monthly"},
        )
        assert initialized.status_code == 201, initialized.text
        initial_order = str(provider_requests[0]["OrderId"])
        assert client.post(
            "/v1/billing/tbank/notifications",
            json=_signed_notification(
                gateway,
                order_id=initial_order,
                status="CONFIRMED",
                payment_id="payment-1",
            ),
        ).status_code == 200

        database = connect_database(database_path)
        try:
            database.execute(
                """
                UPDATE billing_subscriptions
                SET current_period_start = unixepoch() - 7200,
                    current_period_end = unixepoch() - 1
                """
            )
            summary = run_due_renewals(database, gateway=gateway)
            assert summary.created == 1
            recurrent = database.execute(
                "SELECT * FROM billing_payment_intents WHERE kind = 'recurrent'"
            ).fetchone()
            assert recurrent is not None
            renewal_order = str(recurrent["order_id"])
            subscription_id = str(
                database.execute(
                    "SELECT id FROM billing_subscriptions"
                ).fetchone()[0]
            )
        finally:
            database.close()

        renewed = client.post(
            "/v1/billing/tbank/notifications",
            json=_signed_notification(
                gateway,
                order_id=renewal_order,
                status="CONFIRMED",
                payment_id="payment-2",
            ),
        )
        assert renewed.status_code == 200
        assert client.get("/v1/session").json()["user"]["entitlements"] == [
            "construction.estimates.use"
        ]

        refunded = client.post(
            "/v1/billing/tbank/notifications",
            json=_signed_notification(
                gateway,
                order_id=renewal_order,
                status="REFUNDED",
                payment_id="payment-2",
            ),
        )
        assert refunded.status_code == 200
        subscriptions = client.get("/v1/billing/subscriptions").json()["items"]
        assert [item["id"] for item in subscriptions] == [subscription_id]
        assert subscriptions[0]["status"] == "refunded"
        assert client.get("/v1/session").json()["user"]["entitlements"] == []

    database = connect_database(database_path)
    try:
        grant = database.execute(
            """
            SELECT status, source
            FROM product_entitlement_grants
            WHERE tenant_id = ? AND user_id = ?
            """,
            (subject["tenantId"], subject["id"]),
        ).fetchone()
        assert tuple(grant) == ("revoked", "subscription_policy")
        assert database.execute(
            """
            SELECT COUNT(*) FROM billing_audit_events
            WHERE action = 'subscription.refunded'
            """
        ).fetchone()[0] == 1
    finally:
        database.close()


def test_confirmed_renewal_reactivates_refunded_parent_subscription(
    tmp_path: Path,
) -> None:
    """A CONFIRMED renewal must restore access even if the parent was refunded
    while the renewal was already in flight (out-of-order webhooks)."""

    database_path = tmp_path / "renewal-reactivating.db"
    settings = Settings.for_testing(database_url=database_path)
    provider_requests: list[dict[str, object]] = []

    def provider(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert isinstance(body, dict)
        provider_requests.append(body)
        return httpx.Response(
            200,
            json={
                "Success": True,
                "ErrorCode": "0",
                "TerminalKey": "TestMerchantTerminal",
                "Status": "NEW",
                "PaymentId": f"payment-{len(provider_requests)}",
                "OrderId": body["OrderId"],
                "Amount": body["Amount"],
                "PaymentURL": (
                    "https://securepayments.tinkoff.ru/session/renewal-reactivating"
                ),
                **(
                    {"RebillId": "test-rebill-reactivating"}
                    if body.get("Recurrent") == "Y"
                    else {}
                ),
            },
        )

    gateway = TBankGateway(
        TBankSettings.for_testing(recurring_enabled=True),
        transport=httpx.MockTransport(provider),
    )
    app = create_app(settings)
    app.state.tbank_gateway = gateway
    with TestClient(app) as client:
        _seed_plans(database_path)
        subject = _register(
            client,
            email="renewal-reactivating@example.com",
            name="Renewal Reactivating",
        )
        initialized = client.post(
            "/v1/billing/payment-intents",
            headers=_mutation_headers(
                client,
                key=f"{IDEMPOTENCY_KEY}-reactivating",
            ),
            json={"planCode": "kolibri.pro.monthly"},
        )
        assert initialized.status_code == 201, initialized.text
        initial_order = str(provider_requests[0]["OrderId"])
        assert client.post(
            "/v1/billing/tbank/notifications",
            json=_signed_notification(
                gateway,
                order_id=initial_order,
                status="CONFIRMED",
                payment_id="payment-1",
            ),
        ).status_code == 200

        database = connect_database(database_path)
        try:
            database.execute(
                """
                UPDATE billing_subscriptions
                SET current_period_start = unixepoch() - 7200,
                    current_period_end = unixepoch() - 1
                """
            )
            summary = run_due_renewals(database, gateway=gateway)
            assert summary.created == 1
            recurrent = database.execute(
                "SELECT * FROM billing_payment_intents WHERE kind = 'recurrent'"
            ).fetchone()
            assert recurrent is not None
            renewal_order = str(recurrent["order_id"])
            subscription_id = str(
                database.execute(
                    "SELECT id FROM billing_subscriptions"
                ).fetchone()[0]
            )
        finally:
            database.close()

        # The parent charge is refunded while the renewal is still in flight.
        assert client.post(
            "/v1/billing/tbank/notifications",
            json=_signed_notification(
                gateway,
                order_id=initial_order,
                status="REFUNDED",
                payment_id="payment-1",
            ),
        ).status_code == 200
        subscriptions = client.get("/v1/billing/subscriptions").json()["items"]
        assert subscriptions[0]["status"] == "refunded"
        assert client.get("/v1/session").json()["user"]["entitlements"] == []

        # The renewal CONFIRMED arrives after the parent refund and must
        # restore the paid period rather than be swallowed.
        assert client.post(
            "/v1/billing/tbank/notifications",
            json=_signed_notification(
                gateway,
                order_id=renewal_order,
                status="CONFIRMED",
                payment_id="payment-2",
            ),
        ).status_code == 200
        subscriptions = client.get("/v1/billing/subscriptions").json()["items"]
        assert subscriptions[0]["id"] == subscription_id
        assert subscriptions[0]["status"] == "active"
        assert client.get("/v1/session").json()["user"]["entitlements"] == [
            "construction.estimates.use"
        ]

    database = connect_database(database_path)
    try:
        row = database.execute(
            "SELECT status FROM product_entitlement_grants "
            "WHERE tenant_id = ? AND user_id = ?",
            (subject["tenantId"], subject["id"]),
        ).fetchone()
        assert row["status"] == "active"
    finally:
        database.close()


def test_admin_billing_config_save_redact_disable_and_production_fence(
    tmp_path: Path,
) -> None:
    """Terminal settings are admin-managed, encrypted, and never production."""

    database_path = tmp_path / "admin-billing-config.db"
    settings = Settings.for_testing(
        database_url=database_path,
        bootstrap_owner_email="owner@example.com",
    )
    settings = replace(settings, local_provider_vault_read_enabled=True)
    master_key_path = database_path.parent / ".kolibri-v3-provider-master-key"
    master_key_path.write_bytes(os.urandom(32))
    os.chmod(master_key_path, 0o600)
    app = create_app(settings)
    with TestClient(app) as owner:
        _register(owner, email="owner@example.com", name="Owner")
        promote_registered_owner(settings, email="owner@example.com")

        initial = owner.get("/v1/platform-admin/billing/config")
        assert initial.status_code == 200
        assert initial.json()["status"] == "disabled"
        assert initial.json()["source"] == "none"

        production = owner.put(
            "/v1/platform-admin/billing/config",
            headers=_mutation_headers(owner, key=f"{IDEMPOTENCY_KEY}-prod-fence"),
            json={
                "enabled": True,
                "mode": "production",
                "terminalKey": "ProductionTerminal",
                "password": "production-password",
                "notificationUrl": "https://kolibriai.ru/api/v3/billing/tbank/notifications",
                "returnOrigin": "https://kolibriai.ru",
            },
        )
        assert production.status_code == 422
        assert production.json()["code"] in {
            "invalid_request",
            "billing_settings_production_forbidden",
        }

        missing = owner.put(
            "/v1/platform-admin/billing/config",
            headers=_mutation_headers(owner, key=f"{IDEMPOTENCY_KEY}-missing-keys"),
            json={
                "enabled": True,
                "mode": "demo",
                "terminalKey": "",
                "password": "",
                "notificationUrl": "http://localhost/v1/billing/tbank/notifications",
                "returnOrigin": "http://localhost",
            },
        )
        assert missing.status_code == 422
        assert missing.json()["code"] == "billing_settings_credentials_required"

        saved = owner.put(
            "/v1/platform-admin/billing/config",
            headers=_mutation_headers(owner, key=f"{IDEMPOTENCY_KEY}-save"),
            json={
                "enabled": True,
                "mode": "demo",
                "terminalKey": "DemoTerminalDEMO",
                "password": "demo-secret-123",
                "notificationUrl": "http://localhost/v1/billing/tbank/notifications",
                "returnOrigin": "http://localhost",
            },
        )
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["status"] == "configured"
        assert body["source"] == "admin"
        assert body["mode"] == "demo"
        assert body["receiptMode"] == "disabled"
        assert body["productionConfirmed"] is False
        assert body["terminalFingerprint"] is not None
        assert "password" not in body
        assert "terminalKey" not in body
        assert body["updatedAt"] is not None

        again = owner.put(
            "/v1/platform-admin/billing/config",
            headers=_mutation_headers(owner, key=f"{IDEMPOTENCY_KEY}-disable"),
            json={"enabled": False, "mode": "demo"},
        )
        assert again.status_code == 200
        assert again.json()["status"] == "disabled"
        assert again.json()["source"] == "none"

        # Re-enable and verify the encrypted payload never stores plaintext.
        owner.put(
            "/v1/platform-admin/billing/config",
            headers=_mutation_headers(owner, key=f"{IDEMPOTENCY_KEY}-re-enable"),
            json={
                "enabled": True,
                "mode": "demo",
                "terminalKey": "DemoTerminalDEMO",
                "password": "demo-secret-123",
                "notificationUrl": "http://localhost/v1/billing/tbank/notifications",
                "returnOrigin": "http://localhost",
            },
        )

    database = connect_database(database_path)
    try:
        row = database.execute(
            "SELECT enabled, terminal_key_encrypted, password_encrypted "
            "FROM billing_provider_settings WHERE provider = 'tbank'"
        ).fetchone()
        assert row is not None
        assert row["enabled"] == 1
        assert row["terminal_key_encrypted"] is not None
        assert row["password_encrypted"] is not None
    finally:
        database.close()

    database = connect_database(database_path)
    try:
        row = database.execute(
            "SELECT terminal_key_encrypted, password_encrypted "
            "FROM billing_provider_settings WHERE provider = 'tbank'"
        ).fetchone()
        assert row is not None
        for encrypted in (row["terminal_key_encrypted"], row["password_encrypted"]):
            assert encrypted is not None
            assert len(encrypted) > 13
            assert b"DemoTerminalDEMO" not in bytes(encrypted)
            assert b"demo-secret-123" not in bytes(encrypted)
    finally:
        database.close()
