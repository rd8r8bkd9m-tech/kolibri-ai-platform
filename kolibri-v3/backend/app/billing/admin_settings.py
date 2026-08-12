"""Admin-managed T-Bank terminal settings (test/demo only).

The canonical production boundary stays env-only: this module deliberately
rejects ``mode=production`` and never returns a secret. Test and demo
terminals can be entered from the platform admin panel, encrypted with the
same AES-256-GCM vault as platform model keys.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from typing import Any, Literal

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config import Settings
from ..database import transaction
from ..local_provider_authority import (
    LocalProviderAuthorityError,
    ensure_local_provider_master_key,
)
from .config import TBankSettings
from .service import BillingError, _now


AdminMode = Literal["test", "demo"]
ReceiptMode = Literal["disabled", "required"]

_AAD_PREFIX = b"kolibri-v3-billing-tbank-v1\0"


def _encrypt_secret(settings: Settings, secret: str, *, field: str) -> bytes:
    master_key = ensure_local_provider_master_key(settings)
    nonce = os.urandom(12)
    aad = _AAD_PREFIX + field.encode("utf-8", "strict")
    ciphertext = AESGCM(master_key).encrypt(
        nonce,
        secret.encode("utf-8", "strict"),
        aad,
    )
    return nonce + ciphertext


def _decrypt_secret(
    settings: Settings,
    encrypted: bytes,
    *,
    field: str,
) -> str:
    if len(encrypted) < 13:
        raise LocalProviderAuthorityError(
            "billing_settings_key_invalid",
            "Зашифрованный ключ терминала имеет неверный формат.",
        )
    master_key = ensure_local_provider_master_key(settings)
    nonce = encrypted[:12]
    ciphertext = encrypted[12:]
    aad = _AAD_PREFIX + field.encode("utf-8", "strict")
    try:
        plaintext = AESGCM(master_key).decrypt(nonce, ciphertext, aad)
    except InvalidTag:
        raise LocalProviderAuthorityError(
            "billing_settings_key_invalid",
            "Не удалось расшифровать ключ терминала.",
        ) from None
    return plaintext.decode("utf-8", "strict")


def _redact(value: str) -> str:
    if len(value) <= 8:
        return f"{value[:2]}…{value[-1:] if value else ''}"
    return f"{value[:4]}…{value[-4:]}"


def tbank_admin_settings_view(
    database: sqlite3.Connection,
    settings: Settings,
    *,
    env_settings: TBankSettings | None,
) -> dict[str, Any]:
    """Redacted config view; never includes a terminal secret."""

    row = database.execute(
        """
        SELECT enabled, mode, notification_url, return_origin,
               receipt_mode, taxation, terminal_fingerprint, verify_ssl,
               updated_at
        FROM billing_provider_settings
        WHERE provider = 'tbank'
        LIMIT 1
        """
    ).fetchone()
    if env_settings is not None and env_settings.enabled:
        return {
            "status": "configured",
            "source": "env",
            "mode": env_settings.mode,
            "receiptMode": env_settings.receipt_mode,
            "productionConfirmed": env_settings.production_confirmed,
            "verifySsl": env_settings.verify_ssl,
            "terminalFingerprint": _redact(env_settings.terminal_fingerprint),
            "updatedAt": None,
        }
    if row is None or not int(row["enabled"]):
        return {
            "status": "disabled",
            "source": "none",
            "mode": None,
            "receiptMode": None,
            "productionConfirmed": False,
            "verifySsl": True,
            "terminalFingerprint": None,
            "updatedAt": None,
        }
    try:
        candidate = load_admin_tbank_settings(database, settings)
        status = "configured" if candidate is not None else "invalid"
        mode = str(row["mode"])
    except (ValueError, LocalProviderAuthorityError):
        status = "invalid"
        mode = str(row["mode"])
    return {
        "status": status,
        "source": "admin",
        "mode": mode,
        "receiptMode": str(row["receipt_mode"]),
        "productionConfirmed": False,
        "verifySsl": bool(int(row["verify_ssl"])),
        "terminalFingerprint": (
            _redact(str(row["terminal_fingerprint"]))
            if row["terminal_fingerprint"]
            else None
        ),
        "updatedAt": int(row["updated_at"]),
    }


def _tbank_settings_from_row(
    database: sqlite3.Connection,
    settings: Settings,
    row: sqlite3.Row,
) -> TBankSettings | None:
    if not int(row["enabled"]):
        return None
    if row["terminal_key_encrypted"] is None or row["password_encrypted"] is None:
        return None
    terminal_key = _decrypt_secret(
        settings,
        bytes(row["terminal_key_encrypted"]),
        field="terminal_key",
    )
    password = _decrypt_secret(
        settings,
        bytes(row["password_encrypted"]),
        field="password",
    )
    return TBankSettings(
        enabled=True,
        mode=str(row["mode"]),  # type: ignore[arg-type]
        terminal_key=terminal_key,
        password=password,
        notification_url=str(row["notification_url"]),
        return_origin=str(row["return_origin"]),
        receipt_mode=str(row["receipt_mode"]),  # type: ignore[arg-type]
        taxation=(
            str(row["taxation"]) if row["taxation"] is not None else None
        ),
        timeout_seconds=10.0,
        verify_ssl=bool(int(row["verify_ssl"])),
        production_confirmed=False,
        runtime_environment=settings.environment,
    )


def load_admin_tbank_settings(
    database: sqlite3.Connection,
    settings: Settings,
) -> TBankSettings | None:
    row = database.execute(
        """
        SELECT * FROM billing_provider_settings
        WHERE provider = 'tbank'
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    return _tbank_settings_from_row(database, settings, row)


def save_admin_tbank_settings(
    database: sqlite3.Connection,
    *,
    settings: Settings,
    owner_user_id: str,
    enabled: bool,
    mode: AdminMode,
    terminal_key: str | None,
    password: str | None,
    notification_url: str | None,
    return_origin: str | None,
    receipt_mode: ReceiptMode,
    taxation: str | None,
    verify_ssl: bool,
) -> dict[str, Any]:
    """Persist admin-managed test/demo terminal settings, encrypted."""

    now = _now(database)
    if not enabled:
        with transaction(database, immediate=True):
            database.execute(
                """
                INSERT INTO billing_provider_settings (
                    provider, enabled, mode, terminal_key_encrypted,
                    password_encrypted, notification_url, return_origin,
                    receipt_mode, taxation, terminal_fingerprint,
                    verify_ssl, updated_at, updated_by_user_id
                ) VALUES ('tbank', 0, ?, NULL, NULL, NULL, NULL,
                          'disabled', NULL, '', ?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    enabled = 0,
                    terminal_key_encrypted = NULL,
                    password_encrypted = NULL,
                    notification_url = NULL,
                    return_origin = NULL,
                    receipt_mode = 'disabled',
                    taxation = NULL,
                    terminal_fingerprint = '',
                    verify_ssl = 1,
                    updated_at = excluded.updated_at,
                    updated_by_user_id = excluded.updated_by_user_id
                """,
                (mode, 1, now, owner_user_id),
            )
        return tbank_admin_settings_view(
            database,
            settings,
            env_settings=None,
        )

    terminal_key = (terminal_key or "").strip()
    password = (password or "").strip()
    notification_url = (notification_url or "").strip() or None
    return_origin = (return_origin or "").strip() or None
    taxation = (taxation or "").strip() or None
    if not terminal_key or not password:
        raise BillingError(
            422,
            "billing_settings_credentials_required",
            "Для включения оплаты нужны TerminalKey и Password терминала.",
        )
    if mode == "production":
        raise BillingError(
            422,
            "billing_settings_production_forbidden",
            "Рабочий терминал включается только через переменные окружения.",
        )
    try:
        TBankSettings(
            enabled=True,
            mode=mode,
            terminal_key=terminal_key,
            password=password,
            notification_url=notification_url,
            return_origin=return_origin,
            receipt_mode=receipt_mode,
            taxation=taxation,
            timeout_seconds=10.0,
            verify_ssl=verify_ssl,
            production_confirmed=False,
            runtime_environment=settings.environment,
        )
    except ValueError as exc:
        raise BillingError(
            422,
            "billing_settings_invalid",
            "Параметры терминала не прошли проверку: " + str(exc),
        ) from exc

    terminal_fingerprint = hashlib.sha256(
        terminal_key.encode("utf-8")
    ).hexdigest()[:16]
    encrypted_key = _encrypt_secret(
        settings,
        terminal_key,
        field="terminal_key",
    )
    encrypted_password = _encrypt_secret(
        settings,
        password,
        field="password",
    )
    with transaction(database, immediate=True):
        database.execute(
            """
            INSERT INTO billing_provider_settings (
                provider, enabled, mode, terminal_key_encrypted,
                password_encrypted, notification_url, return_origin,
                receipt_mode, taxation, terminal_fingerprint, verify_ssl,
                updated_at, updated_by_user_id
            ) VALUES ('tbank', 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider) DO UPDATE SET
                enabled = 1,
                mode = excluded.mode,
                terminal_key_encrypted = excluded.terminal_key_encrypted,
                password_encrypted = excluded.password_encrypted,
                notification_url = excluded.notification_url,
                return_origin = excluded.return_origin,
                receipt_mode = excluded.receipt_mode,
                taxation = excluded.taxation,
                terminal_fingerprint = excluded.terminal_fingerprint,
                verify_ssl = excluded.verify_ssl,
                updated_at = excluded.updated_at,
                updated_by_user_id = excluded.updated_by_user_id
            """,
            (
                mode,
                encrypted_key,
                encrypted_password,
                notification_url,
                return_origin,
                receipt_mode,
                taxation,
                terminal_fingerprint,
                1 if verify_ssl else 0,
                now,
                owner_user_id,
            ),
        )
    return tbank_admin_settings_view(
        database,
        settings,
        env_settings=None,
    )
