from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


DEFAULT_INITDATA_MAX_AGE_SECONDS = 300
DEFAULT_SESSION_TTL_SECONDS = 900
SESSION_TOKEN_VERSION = "kma1"

router = APIRouter()


class TelegramMiniAppAuthRequest(BaseModel):
    init_data: str = Field(..., min_length=1, max_length=8192)


class TelegramMiniAppSessionResponse(BaseModel):
    ok: bool
    role: str
    subject: str
    session_token: str
    expires_at: int
    ttl_seconds: int


@dataclass(frozen=True)
class VerifiedTelegramInitData:
    telegram_user_id: int
    auth_date: int
    payload: dict[str, Any]

    @property
    def subject(self) -> str:
        digest = hashlib.sha256(str(self.telegram_user_id).encode("utf-8")).hexdigest()[:16]
        return f"telegram:user:{digest}"


class TelegramMiniAppAuthError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _get_required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise TelegramMiniAppAuthError("server_not_configured")
    return value


def parse_owner_ids(value: str) -> set[int]:
    owner_ids: set[int] = set()
    for raw in value.replace(";", ",").split(","):
        item = raw.strip()
        if not item:
            continue
        try:
            owner_ids.add(int(item))
        except ValueError as exc:
            raise TelegramMiniAppAuthError("server_not_configured") from exc
    return owner_ids


def _telegram_secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()


def _parse_init_data(init_data: str) -> tuple[dict[str, str], str]:
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise TelegramMiniAppAuthError("malformed_init_data") from exc

    parsed: dict[str, str] = {}
    for key, value in pairs:
        if key in parsed:
            raise TelegramMiniAppAuthError("malformed_init_data")
        parsed[key] = value

    supplied_hash = parsed.pop("hash", "")
    if not supplied_hash or not hmac.compare_digest(supplied_hash.lower(), supplied_hash):
        raise TelegramMiniAppAuthError("malformed_init_data")
    if len(supplied_hash) != 64:
        raise TelegramMiniAppAuthError("malformed_init_data")
    try:
        bytes.fromhex(supplied_hash)
    except ValueError as exc:
        raise TelegramMiniAppAuthError("malformed_init_data") from exc

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    if not data_check_string:
        raise TelegramMiniAppAuthError("malformed_init_data")
    return parsed, supplied_hash


def verify_telegram_init_data(
    init_data: str,
    *,
    bot_token: str,
    now: int | None = None,
    max_age_seconds: int = DEFAULT_INITDATA_MAX_AGE_SECONDS,
) -> VerifiedTelegramInitData:
    parsed, supplied_hash = _parse_init_data(init_data)
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    expected_hash = hmac.new(
        _telegram_secret_key(bot_token),
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, supplied_hash):
        raise TelegramMiniAppAuthError("bad_signature")

    try:
        auth_date = int(parsed["auth_date"])
    except (KeyError, ValueError) as exc:
        raise TelegramMiniAppAuthError("malformed_init_data") from exc

    current_time = int(time.time()) if now is None else int(now)
    if auth_date > current_time + 60:
        raise TelegramMiniAppAuthError("stale_init_data")
    if current_time - auth_date > max_age_seconds:
        raise TelegramMiniAppAuthError("stale_init_data")

    try:
        user = json.loads(parsed["user"])
        telegram_user_id = int(user["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TelegramMiniAppAuthError("malformed_init_data") from exc

    return VerifiedTelegramInitData(
        telegram_user_id=telegram_user_id,
        auth_date=auth_date,
        payload={key: value for key, value in parsed.items() if key != "user"},
    )


def map_telegram_role(telegram_user_id: int, owner_ids: set[int]) -> str:
    if telegram_user_id in owner_ids:
        return "owner"
    raise TelegramMiniAppAuthError("unauthorized")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def issue_session_token(
    *,
    subject: str,
    role: str,
    secret: str,
    now: int | None = None,
    ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
) -> tuple[str, int]:
    issued_at = int(time.time()) if now is None else int(now)
    expires_at = issued_at + ttl_seconds
    body = {
        "sub": subject,
        "role": role,
        "iat": issued_at,
        "exp": expires_at,
    }
    payload = _b64url(json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _b64url(
        hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{SESSION_TOKEN_VERSION}.{payload}.{signature}", expires_at


def build_session_response(
    init_data: str,
    *,
    bot_token: str,
    owner_ids: set[int],
    session_secret: str,
    now: int | None = None,
    initdata_max_age_seconds: int = DEFAULT_INITDATA_MAX_AGE_SECONDS,
    session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
) -> TelegramMiniAppSessionResponse:
    verified = verify_telegram_init_data(
        init_data,
        bot_token=bot_token,
        now=now,
        max_age_seconds=initdata_max_age_seconds,
    )
    role = map_telegram_role(verified.telegram_user_id, owner_ids)
    session_token, expires_at = issue_session_token(
        subject=verified.subject,
        role=role,
        secret=session_secret,
        now=now,
        ttl_seconds=session_ttl_seconds,
    )
    return TelegramMiniAppSessionResponse(
        ok=True,
        role=role,
        subject=verified.subject,
        session_token=session_token,
        expires_at=expires_at,
        ttl_seconds=session_ttl_seconds,
    )


def _http_error_for_auth_error(exc: TelegramMiniAppAuthError) -> HTTPException:
    if exc.code == "unauthorized":
        return HTTPException(status_code=403, detail="unauthorized")
    if exc.code == "server_not_configured":
        return HTTPException(status_code=503, detail="server_not_configured")
    return HTTPException(status_code=401, detail=exc.code)


@router.post("/api/v1/auth/telegram-miniapp/session", response_model=TelegramMiniAppSessionResponse)
async def create_telegram_miniapp_session(
    request: TelegramMiniAppAuthRequest,
) -> TelegramMiniAppSessionResponse:
    try:
        bot_token = _get_required_env("TELEGRAM_BOT_TOKEN")
        owner_ids = parse_owner_ids(_get_required_env("TELEGRAM_OWNER_IDS"))
        session_secret = os.environ.get("KOLIBRI_SESSION_SECRET", "").strip() or bot_token
        return build_session_response(
            request.init_data,
            bot_token=bot_token,
            owner_ids=owner_ids,
            session_secret=session_secret,
        )
    except TelegramMiniAppAuthError as exc:
        raise _http_error_for_auth_error(exc) from exc
