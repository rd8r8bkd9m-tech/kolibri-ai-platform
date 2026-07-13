"""Signed anonymous browser-session bootstrap for the public Shell."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.auth import ALGORITHM, SECRET_KEY, security
from app.database import get_db
from app.models import UserDB


SESSION_COOKIE_NAME = "kolibri_session"
SESSION_TTL_SECONDS = int(os.getenv("KOLIBRI_SESSION_TTL_SECONDS", str(30 * 24 * 60 * 60)))
SESSION_VERSION = 1

_configured_secret = os.getenv("KOLIBRI_SESSION_SECRET") or os.getenv("JWT_SECRET_KEY") or SECRET_KEY
_SESSION_SIGNING_KEY = _configured_secret.encode("utf-8")


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


@dataclass(frozen=True)
class AnonymousSession:
    sid: str
    issued_at: int
    expires_at: int

    @property
    def scope_id(self) -> str:
        return f"anon:{self.sid}"

    @property
    def public_id(self) -> str:
        return hashlib.sha256(self.sid.encode("ascii")).hexdigest()[:32]


@dataclass(frozen=True)
class ProjectPrincipal:
    scope_id: str
    kind: str
    public_id: str


def issue_anonymous_session(*, sid: str | None = None, now: int | None = None) -> tuple[str, AnonymousSession]:
    issued_at = int(now if now is not None else time.time())
    session = AnonymousSession(
        sid=sid or secrets.token_urlsafe(32),
        issued_at=issued_at,
        expires_at=issued_at + SESSION_TTL_SECONDS,
    )
    payload = json.dumps(
        {"v": SESSION_VERSION, "sid": session.sid, "iat": session.issued_at, "exp": session.expires_at},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = _b64encode(payload)
    signature = _b64encode(hmac.new(_SESSION_SIGNING_KEY, encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}", session


def validate_anonymous_session(token: str | None, *, now: int | None = None) -> AnonymousSession | None:
    if not token or len(token) > 2048:
        return None
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = _b64encode(
            hmac.new(_SESSION_SIGNING_KEY, encoded.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        payload = json.loads(_b64decode(encoded))
        current = int(now if now is not None else time.time())
        if payload.get("v") != SESSION_VERSION:
            return None
        sid = payload.get("sid")
        issued_at = int(payload.get("iat"))
        expires_at = int(payload.get("exp"))
        if not isinstance(sid, str) or len(sid) < 40 or len(sid) > 128:
            return None
        if issued_at > current + 60 or expires_at <= current or expires_at <= issued_at:
            return None
        return AnonymousSession(sid=sid, issued_at=issued_at, expires_at=expires_at)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> UserDB | None:
    """Resolve a bearer user without turning public bootstrap into 401/403."""

    if credentials is None:
        return None
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        return None
    return db.query(UserDB).filter(UserDB.id == user_id, UserDB.is_active.is_(True)).first()


def resolve_project_principal(
    anonymous_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    user: UserDB | None = Depends(_optional_user),
) -> ProjectPrincipal:
    if user is not None:
        return ProjectPrincipal(scope_id=f"user:{user.id}", kind="authenticated", public_id=user.id)
    anonymous = validate_anonymous_session(anonymous_cookie)
    if anonymous is not None:
        return ProjectPrincipal(
            scope_id=anonymous.scope_id,
            kind="anonymous",
            public_id=anonymous.public_id,
        )
    raise HTTPException(
        status_code=428,
        detail={
            "code": "session_bootstrap_required",
            "message": "Call POST /api/v1/shell/bootstrap before using project history",
        },
    )


def bootstrap_browser_session(
    request: Request,
    response: Response,
    anonymous_cookie: str | None,
    user: UserDB | None,
) -> dict:
    if user is not None:
        return {
            "session_id": user.id,
            "session_type": "authenticated",
            "restored": True,
            "expires_at": None,
        }

    existing = validate_anonymous_session(anonymous_cookie)
    restored = existing is not None
    if existing is None:
        token, session = issue_anonymous_session()
    else:
        token, session = anonymous_cookie, existing

    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    secure = request.url.scheme == "https" or forwarded_proto == "https"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=max(0, session.expires_at - int(time.time())),
        expires=datetime.fromtimestamp(session.expires_at, tz=timezone.utc),
        path="/",
        secure=secure,
        httponly=True,
        samesite="lax",
    )
    return {
        "session_id": session.public_id,
        "session_type": "anonymous",
        "restored": restored,
        "expires_at": datetime.fromtimestamp(session.expires_at, tz=timezone.utc),
    }
