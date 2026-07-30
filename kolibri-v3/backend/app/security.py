from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import sqlite3
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from .config import Settings, normalize_origin
from .database import get_database
from .mobile_auth import MobileAuthFailure, require_bearer_session

_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64
_PASSWORD_SCHEME = "scrypt-v1"
_CSRF_CONTEXT = b"kolibri-v3-csrf-v1\0"


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if not encoded or len(encoded) > 1_024:
        raise ValueError("password length is outside the accepted range")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        encoded,
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return (
        f"{_PASSWORD_SCHEME}${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}"
        f"${_b64encode(salt)}${_b64encode(digest)}"
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        scheme, raw_n, raw_r, raw_p, raw_salt, raw_digest = encoded_hash.split("$")
        n, r, p = int(raw_n), int(raw_r), int(raw_p)
        if (
            scheme != _PASSWORD_SCHEME
            or n != _SCRYPT_N
            or r != _SCRYPT_R
            or p != _SCRYPT_P
        ):
            return False
        expected = _b64decode(raw_digest)
        salt = _b64decode(raw_salt)
        if len(salt) != 16 or len(expected) != _SCRYPT_DKLEN:
            return False
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
        )
        return hmac.compare_digest(candidate, expected)
    except (UnicodeError, ValueError, TypeError):
        return False


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def csrf_token_for_session(token: str, settings: Settings) -> str:
    digest = hmac.new(
        settings.csrf_secret,
        _CSRF_CONTEXT + token.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def require_same_origin(request: Request) -> str:
    """Reject browser mutations unless their Origin is explicitly allowlisted."""

    raw_origin = request.headers.get("origin")
    if not raw_origin or len(raw_origin) > 2_048:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="allowed Origin header required",
        )
    try:
        origin = normalize_origin(raw_origin)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="origin is not allowed",
        ) from exc
    settings: Settings = request.app.state.settings
    if origin not in settings.allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="origin is not allowed",
        )
    return origin


def require_csrf(
    request: Request,
    _origin: Annotated[str, Depends(require_same_origin)],
) -> None:
    """Validate a double-submit token bound to the opaque session cookie."""

    settings: Settings = request.app.state.settings
    session_token = request.cookies.get(settings.session_cookie_name)
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    header_token = request.headers.get("x-csrf-token")
    if (
        not session_token
        or not cookie_token
        or not header_token
        or len(session_token) > 512
        or len(cookie_token) > 512
        or len(header_token) > 512
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "csrf_token_required",
                "message": "Обновите страницу и повторите подключение.",
            },
        )

    expected = csrf_token_for_session(session_token, settings)
    if not (
        hmac.compare_digest(cookie_token, header_token)
        and hmac.compare_digest(header_token, expected)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "csrf_token_stale",
                "message": "Сессия защиты устарела. Обновите страницу и повторите подключение.",
            },
        )


def require_mutation_auth(
    request: Request,
    database: Annotated[sqlite3.Connection, Depends(get_database)],
) -> None:
    """Accept a validated native bearer or the browser origin+CSRF boundary."""

    if request.headers.get("authorization") is not None:
        try:
            identity_row = require_bearer_session(request, database)
        except MobileAuthFailure as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, "message": error.message},
                headers={"WWW-Authenticate": "Bearer"},
            ) from error
        if identity_row is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "mobile_access_token_invalid",
                    "message": "The access token is invalid or expired.",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        return

    origin = require_same_origin(request)
    require_csrf(request, origin)
