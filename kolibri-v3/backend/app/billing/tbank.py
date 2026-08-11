"""Minimal, bounded adapter for the official T-Bank acquiring v2 protocol."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit

import httpx

from .config import TBankSettings


_TOKEN = re.compile(r"^[0-9a-f]{64}$")
_PAYMENT_ID = re.compile(r"^[A-Za-z0-9._-]{1,20}$")
_PAYMENT_HOST_SUFFIXES = (".tinkoff.ru", ".tbank.ru")
_MAX_RESPONSE_BYTES = 65_536


class TBankError(RuntimeError):
    """Safe base error; messages never contain a request, secret, or response."""


class TBankTransportError(TBankError):
    pass


class TBankProtocolError(TBankError):
    pass


class TBankSignatureError(TBankError):
    pass


def _scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return value
    raise TBankSignatureError("T-Bank signed field type is invalid")


def signed_top_level_fields(payload: Mapping[str, object]) -> dict[str, str]:
    """Return the exact root-level fields participating in a v2 token.

    T-Bank explicitly excludes ``Token``, nulls and nested objects/arrays from
    token canonicalization. Keeping this function shared by request signing,
    webhook verification and event digests prevents subtly different rules.
    """

    fields: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not key or len(key) > 128:
            raise TBankSignatureError("T-Bank signed field name is invalid")
        if key == "Token" or value is None or isinstance(value, (dict, list)):
            continue
        fields[key] = _scalar(value)
    return fields


def make_token(payload: Mapping[str, object], password: str) -> str:
    fields = signed_top_level_fields(payload)
    fields["Password"] = password
    canonical = "".join(fields[key] for key in sorted(fields))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class VerifiedNotification:
    terminal_key: str
    order_id: str
    payment_id: str
    status: str
    success: bool
    error_code: str
    amount_minor: int
    event_digest: str


def verify_notification(
    payload: Mapping[str, object],
    settings: TBankSettings,
) -> VerifiedNotification:
    token = payload.get("Token")
    if not isinstance(token, str) or _TOKEN.fullmatch(token.lower()) is None:
        raise TBankSignatureError("T-Bank notification token is invalid")
    if settings.password is None or settings.terminal_key is None:
        raise TBankSignatureError("T-Bank notification verifier is unavailable")
    expected = make_token(payload, settings.password)
    if not hmac.compare_digest(token.lower(), expected):
        raise TBankSignatureError("T-Bank notification signature is invalid")

    terminal_key = payload.get("TerminalKey")
    if not isinstance(terminal_key, str) or not hmac.compare_digest(
        terminal_key, settings.terminal_key
    ):
        raise TBankSignatureError("T-Bank notification terminal is invalid")

    order_id = payload.get("OrderId")
    payment_id_raw = payload.get("PaymentId")
    provider_status = payload.get("Status")
    error_code_raw = payload.get("ErrorCode")
    amount_minor = payload.get("Amount")
    success_raw = payload.get("Success")
    payment_id = (
        str(payment_id_raw)
        if isinstance(payment_id_raw, int) and not isinstance(payment_id_raw, bool)
        else payment_id_raw
    )
    error_code = (
        str(error_code_raw)
        if isinstance(error_code_raw, int) and not isinstance(error_code_raw, bool)
        else error_code_raw
    )
    if (
        not isinstance(order_id, str)
        or not 1 <= len(order_id) <= 50
        or not isinstance(payment_id, str)
        or _PAYMENT_ID.fullmatch(payment_id) is None
        or not isinstance(provider_status, str)
        or not 1 <= len(provider_status) <= 48
        or not isinstance(error_code, str)
        or len(error_code) > 32
    ):
        raise TBankProtocolError("T-Bank notification fields are invalid")
    amount_minor = _minor_amount(amount_minor, required=True)
    assert amount_minor is not None
    if isinstance(success_raw, bool):
        success = success_raw
    elif success_raw in {"true", "false"}:
        success = success_raw == "true"
    else:
        raise TBankProtocolError("T-Bank notification success field is invalid")

    canonical_fields = signed_top_level_fields(payload)
    digest_source = json.dumps(
        canonical_fields,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return VerifiedNotification(
        terminal_key=terminal_key,
        order_id=order_id,
        payment_id=payment_id,
        status=provider_status.upper(),
        success=success,
        error_code=error_code,
        amount_minor=amount_minor,
        event_digest=hashlib.sha256(digest_source.encode("utf-8")).hexdigest(),
    )


@dataclass(frozen=True, slots=True)
class TBankInitResult:
    success: bool
    error_code: str
    status: str | None
    payment_id: str | None
    payment_url: str | None
    rebill_id: str | None = None


@dataclass(frozen=True, slots=True)
class TBankStateResult:
    success: bool
    error_code: str
    status: str | None
    payment_id: str
    order_id: str | None
    amount_minor: int | None


def _provider_string(
    value: object,
    *,
    maximum: int,
    required: bool = False,
) -> str | None:
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value) or len(value) > maximum:
        raise TBankProtocolError("T-Bank response field is invalid")
    return value


def _provider_success(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value in {"true", "false"}:
        return value == "true"
    raise TBankProtocolError("T-Bank response success field is invalid")


def _minor_amount(value: object, *, required: bool = False) -> int | None:
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        value = int(value)
    if value is None and not required:
        return None
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 1 <= value <= 9_999_999_999
    ):
        raise TBankProtocolError("T-Bank amount is invalid")
    return value


def _validated_payment_url(value: object) -> str:
    if not isinstance(value, str) or not 12 <= len(value) <= 2048:
        raise TBankProtocolError("T-Bank payment URL is invalid")
    parsed = urlsplit(value)
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not any(hostname.endswith(suffix) for suffix in _PAYMENT_HOST_SUFFIXES)
    ):
        raise TBankProtocolError("T-Bank payment URL is invalid")
    return value


class TBankGateway:
    """One bounded HTTPS request per operation; no automatic financial retry."""

    def __init__(
        self,
        settings: TBankSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not settings.enabled:
            raise ValueError("T-Bank gateway requires enabled settings")
        self.settings = settings
        self._transport = transport

    def _post(self, method: str, payload: Mapping[str, object]) -> dict[str, Any]:
        if self.settings.terminal_key is None or self.settings.password is None:
            raise TBankProtocolError("T-Bank gateway credentials are unavailable")
        body = dict(payload)
        if body.get("TerminalKey") != self.settings.terminal_key or "Token" in body:
            raise TBankProtocolError("T-Bank request authority is invalid")
        body["Token"] = make_token(body, self.settings.password)
        try:
            with httpx.Client(
                timeout=httpx.Timeout(self.settings.timeout_seconds),
                transport=self._transport,
                follow_redirects=False,
                trust_env=False,
                verify=self.settings.verify_ssl,
            ) as client:
                response = client.post(
                    f"{self.settings.base_url}/{method}",
                    json=body,
                    headers={"Accept": "application/json"},
                )
        except (httpx.HTTPError, OSError) as exc:
            raise TBankTransportError("T-Bank transport is unavailable") from exc
        if response.status_code != 200:
            raise TBankTransportError("T-Bank transport returned an error")
        content = response.content
        if not content or len(content) > _MAX_RESPONSE_BYTES:
            raise TBankProtocolError("T-Bank response size is invalid")
        try:
            decoded = json.loads(content)
        except (UnicodeError, ValueError) as exc:
            raise TBankProtocolError("T-Bank response is not valid JSON") from exc
        if not isinstance(decoded, dict) or len(decoded) > 64:
            raise TBankProtocolError("T-Bank response shape is invalid")
        return decoded

    def init_payment(self, payload: Mapping[str, object]) -> TBankInitResult:
        response = self._post("Init", payload)
        expected_order_id = _provider_string(
            payload.get("OrderId"), maximum=50, required=True
        )
        expected_amount = _minor_amount(payload.get("Amount"), required=True)
        assert expected_order_id is not None and expected_amount is not None
        success = _provider_success(response.get("Success"))
        error_code = _provider_string(
            response.get("ErrorCode"), maximum=32, required=True
        )
        assert error_code is not None
        status = _provider_string(response.get("Status"), maximum=48)
        payment_id = _provider_string(response.get("PaymentId"), maximum=20)
        rebill_id = _provider_string(response.get("RebillId"), maximum=64)
        terminal_key = _provider_string(response.get("TerminalKey"), maximum=64)
        order_id = _provider_string(response.get("OrderId"), maximum=50)
        amount_minor = _minor_amount(response.get("Amount"))
        if payment_id is not None and _PAYMENT_ID.fullmatch(payment_id) is None:
            raise TBankProtocolError("T-Bank payment identifier is invalid")
        if terminal_key is not None and not hmac.compare_digest(
            terminal_key, self.settings.terminal_key or ""
        ):
            raise TBankProtocolError("T-Bank Init terminal is mismatched")
        if order_id is not None and not hmac.compare_digest(
            order_id, expected_order_id
        ):
            raise TBankProtocolError("T-Bank Init order is mismatched")
        if amount_minor is not None and amount_minor != expected_amount:
            raise TBankProtocolError("T-Bank Init amount is mismatched")
        if not success:
            return TBankInitResult(
                success=False,
                error_code=error_code,
                status=status.upper() if status else None,
                payment_id=payment_id,
                payment_url=None,
                rebill_id=rebill_id,
            )
        if (
            error_code != "0"
            or payment_id is None
            or terminal_key is None
            or order_id is None
            or amount_minor is None
        ):
            raise TBankProtocolError("T-Bank successful response is inconsistent")
        payment_url = _validated_payment_url(response.get("PaymentURL"))
        return TBankInitResult(
            success=True,
            error_code=error_code,
            status=status.upper() if status else "NEW",
            payment_id=payment_id,
            payment_url=payment_url,
            rebill_id=rebill_id,
        )

    def get_state(self, payment_id: str) -> TBankStateResult:
        if _PAYMENT_ID.fullmatch(payment_id) is None:
            raise TBankProtocolError("T-Bank payment identifier is invalid")
        assert self.settings.terminal_key is not None
        response = self._post(
            "GetState",
            {
                "TerminalKey": self.settings.terminal_key,
                "PaymentId": payment_id,
            },
        )
        success = _provider_success(response.get("Success"))
        error_code = _provider_string(
            response.get("ErrorCode"), maximum=32, required=True
        )
        response_payment_id = _provider_string(
            response.get("PaymentId"), maximum=20, required=True
        )
        assert error_code is not None and response_payment_id is not None
        if not hmac.compare_digest(response_payment_id, payment_id):
            raise TBankProtocolError("T-Bank state response is mismatched")
        status = _provider_string(response.get("Status"), maximum=48)
        order_id = _provider_string(response.get("OrderId"), maximum=50)
        raw_amount = response.get("Amount")
        if raw_amount is not None and (
            not isinstance(raw_amount, int)
            or isinstance(raw_amount, bool)
            or not 1 <= raw_amount <= 9_999_999_999
        ):
            raise TBankProtocolError("T-Bank state amount is invalid")
        return TBankStateResult(
            success=success,
            error_code=error_code,
            status=status.upper() if status else None,
            payment_id=payment_id,
            order_id=order_id,
            amount_minor=raw_amount,
        )
