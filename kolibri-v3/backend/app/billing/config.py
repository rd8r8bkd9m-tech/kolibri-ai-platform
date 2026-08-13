"""Server-only T-Bank acquiring configuration.

No credential from this module is projected into a browser contract, persisted
in SQLite, or included in an exception message. Production is an explicit
three-part gate: the Kolibri runtime must be production, billing must be
enabled, and the real-charge acknowledgement must be set by the operator.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit


TBankMode = Literal["off", "test", "demo", "production"]
ReceiptMode = Literal["disabled", "required"]

_MODE_BASE_URLS: dict[str, str] = {
    # Current primary documentation calls this the test environment and
    # requires a non-DEMO merchant terminal plus an IP allowlist.
    "test": "https://rest-api-test.tinkoff.ru/v2",
    # T-Bank's dashboard test cases use a DEMO terminal against this endpoint.
    "demo": "https://securepay.tinkoff.ru/v2",
    "production": "https://securepay.tinkoff.ru/v2",
}
_TAXATIONS = frozenset(
    {"osn", "usn_income", "usn_income_outcome", "esn", "patent"}
)
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_PRODUCTION_NOTIFICATION_URL = (
    "https://kolibriai.ru/api/v3/billing/tbank/notifications"
)
_PRODUCTION_RETURN_ORIGIN = "https://kolibriai.ru"


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("T-Bank boolean configuration is invalid")


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _validated_url(value: str, *, origin_only: bool, production: bool) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or (origin_only and (parsed.path not in {"", "/"} or parsed.query))
        or (not origin_only and parsed.query)
    ):
        raise ValueError("T-Bank callback URL is invalid")
    if production and parsed.scheme != "https":
        raise ValueError("T-Bank production callback URLs must use HTTPS")
    if parsed.scheme == "http" and parsed.hostname not in _LOOPBACK_HOSTS:
        raise ValueError("plain HTTP T-Bank callback URLs must be loopback")
    if origin_only:
        host = parsed.hostname
        if ":" in host:
            host = f"[{host}]"
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        return f"{parsed.scheme}://{host}"
    return value.rstrip("/")


@dataclass(frozen=True, slots=True)
class TBankSettings:
    enabled: bool = False
    mode: TBankMode = "off"
    terminal_key: str | None = field(default=None, repr=False)
    password: str | None = field(default=None, repr=False)
    notification_url: str | None = None
    return_origin: str | None = None
    receipt_mode: ReceiptMode = "disabled"
    taxation: str | None = None
    timeout_seconds: float = 10.0
    verify_ssl: bool = True
    production_confirmed: bool = False
    runtime_environment: str = "development"
    # Recurring is strictly opt-in: T-Bank test case #1 (successful payment)
    # fails when Init carries Recurrent=Y, so the default must never enable
    # the flag unless an operator explicitly turns it on.
    recurring_enabled: bool = False

    def __post_init__(self) -> None:
        runtime_environment = self.runtime_environment.strip().lower()
        if runtime_environment not in {"development", "test", "production"}:
            raise ValueError("Kolibri runtime environment is invalid")
        object.__setattr__(self, "runtime_environment", runtime_environment)

        if self.mode not in {"off", "test", "demo", "production"}:
            raise ValueError("T-Bank mode is invalid")
        if not self.enabled:
            if self.mode != "off":
                raise ValueError("disabled T-Bank billing must use off mode")
            return
        if self.mode == "off":
            raise ValueError("enabled T-Bank billing requires a terminal mode")

        terminal_key = _optional(self.terminal_key)
        password = _optional(self.password)
        if (
            terminal_key is None
            or len(terminal_key) > 64
            or password is None
            or len(password) > 20
        ):
            raise ValueError("T-Bank server credentials are incomplete")
        object.__setattr__(self, "terminal_key", terminal_key)
        object.__setattr__(self, "password", password)

        if self.mode == "demo" and not terminal_key.upper().endswith("DEMO"):
            raise ValueError("T-Bank demo mode requires a DEMO terminal")
        if self.mode == "test" and terminal_key.upper().endswith("DEMO"):
            raise ValueError("T-Bank test environment requires a non-DEMO terminal")
        if self.mode == "production":
            if terminal_key.upper().endswith("DEMO"):
                raise ValueError("T-Bank production cannot use a DEMO terminal")
            if runtime_environment != "production" or not self.production_confirmed:
                raise ValueError("T-Bank production real charges are not confirmed")

        if runtime_environment == "production" and not self.verify_ssl:
            raise ValueError("T-Bank production requires TLS verification")

        if self.notification_url is None or self.return_origin is None:
            raise ValueError("T-Bank callback URLs are required")
        production = self.mode == "production"
        object.__setattr__(
            self,
            "notification_url",
            _validated_url(
                self.notification_url,
                origin_only=False,
                production=production,
            ),
        )
        object.__setattr__(
            self,
            "return_origin",
            _validated_url(
                self.return_origin,
                origin_only=True,
                production=production,
            ),
        )
        if production and (
            self.notification_url != _PRODUCTION_NOTIFICATION_URL
            or self.return_origin != _PRODUCTION_RETURN_ORIGIN
        ):
            raise ValueError("T-Bank production callbacks must use kolibriai.ru")

        if self.receipt_mode not in {"disabled", "required"}:
            raise ValueError("T-Bank receipt mode is invalid")
        taxation = _optional(self.taxation)
        if self.receipt_mode == "required" and taxation not in _TAXATIONS:
            raise ValueError("T-Bank receipt taxation is required")
        if self.receipt_mode == "disabled" and taxation is not None:
            raise ValueError("T-Bank taxation requires receipt mode")
        object.__setattr__(self, "taxation", taxation)

        if not 1.0 <= self.timeout_seconds <= 30.0:
            raise ValueError("T-Bank timeout must be between 1 and 30 seconds")

    @property
    def base_url(self) -> str:
        if not self.enabled or self.mode == "off":
            raise RuntimeError("T-Bank billing is disabled")
        return _MODE_BASE_URLS[self.mode]

    @property
    def terminal_fingerprint(self) -> str:
        if self.terminal_key is None:
            raise RuntimeError("T-Bank terminal is unavailable")
        return hashlib.sha256(self.terminal_key.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def from_env(cls, *, runtime_environment: str) -> "TBankSettings":
        enabled = _parse_bool(os.getenv("KOLIBRI_V3_TBANK_ENABLED"))
        mode = os.getenv(
            "KOLIBRI_V3_TBANK_MODE",
            "off" if not enabled else "test",
        ).strip().lower()
        try:
            timeout = float(os.getenv("KOLIBRI_V3_TBANK_TIMEOUT_SECONDS", "10"))
        except ValueError as exc:
            raise ValueError("T-Bank timeout configuration is invalid") from exc
        return cls(
            enabled=enabled,
            mode=mode,  # type: ignore[arg-type]
            terminal_key=os.getenv("KOLIBRI_V3_TBANK_TERMINAL_KEY"),
            password=os.getenv("KOLIBRI_V3_TBANK_PASSWORD"),
            notification_url=_optional(
                os.getenv("KOLIBRI_V3_TBANK_NOTIFICATION_URL")
            ),
            return_origin=_optional(
                os.getenv("KOLIBRI_V3_TBANK_RETURN_ORIGIN")
            ),
            receipt_mode=os.getenv(
                "KOLIBRI_V3_TBANK_RECEIPT_MODE", "disabled"
            ).strip().lower(),  # type: ignore[arg-type]
            taxation=_optional(os.getenv("KOLIBRI_V3_TBANK_TAXATION")),
            timeout_seconds=timeout,
            verify_ssl=_parse_bool(os.getenv("KOLIBRI_V3_TBANK_VERIFY_SSL"), default=True),
            production_confirmed=_parse_bool(
                os.getenv("KOLIBRI_V3_TBANK_PRODUCTION_CONFIRMED")
            ),
            recurring_enabled=_parse_bool(
                os.getenv("KOLIBRI_V3_TBANK_RECURRING_ENABLED"),
                default=False,
            ),
            runtime_environment=runtime_environment,
        )

    @classmethod
    def for_testing(
        cls,
        *,
        terminal_key: str = "TestMerchantTerminal",
        password: str = "test-server-password",
        mode: TBankMode = "test",
        receipt_mode: ReceiptMode = "disabled",
        taxation: str | None = None,
        notification_url: str = "http://localhost/v1/billing/tbank/notifications",
        return_origin: str = "http://localhost",
        runtime_environment: Literal["development", "test", "production"] = "test",
        production_confirmed: bool = False,
        verify_ssl: bool = True,
        recurring_enabled: bool = False,
    ) -> "TBankSettings":
        return cls(
            enabled=True,
            mode=mode,
            terminal_key=terminal_key,
            password=password,
            notification_url=notification_url,
            return_origin=return_origin,
            receipt_mode=receipt_mode,
            taxation=taxation,
            timeout_seconds=5,
            runtime_environment=runtime_environment,
            production_confirmed=production_confirmed,
            verify_ssl=verify_ssl,
            recurring_enabled=recurring_enabled,
        )
