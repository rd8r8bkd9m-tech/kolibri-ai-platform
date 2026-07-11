from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Header, HTTPException


@dataclass(frozen=True)
class SessionPrincipal:
    session_id: str
    role: str
    plan: str
    device: str = "auto"
    source: str = "session"
    scopes: tuple[str, ...] = ()


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _secret() -> bytes:
    value = os.environ.get("VISTA_SESSION_SECRET")
    if not value:
        if os.environ.get("VISTA_ENV", "local").lower() in {"prod", "production"}:
            raise HTTPException(status_code=503, detail="VISTA_SESSION_SECRET is not configured")
        value = "vista-local-session-secret-change-before-production"
    return value.encode("utf-8")


def issue_session_token(session: dict[str, Any], ttl_seconds: int | None = None) -> str:
    ttl = ttl_seconds or int(os.environ.get("VISTA_SESSION_TTL_SECONDS", str(7 * 24 * 3600)))
    payload = {
        "sid": session["id"],
        "role": session["role"],
        "plan": session["plan"],
        "device": session.get("device", "auto"),
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl,
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signature = hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"vista_session_{encoded}.{signature}"


def _verify_session_token(token: str) -> SessionPrincipal:
    if not token.startswith("vista_session_"):
        raise HTTPException(status_code=401, detail="invalid Vista session token")
    try:
        encoded, signature = token[len("vista_session_"):].rsplit(".", 1)
        expected = hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        payload = json.loads(_b64decode(encoded))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise HTTPException(status_code=401, detail="Vista session expired")
        return SessionPrincipal(
            session_id=str(payload["sid"]),
            role=str(payload["role"]),
            plan=str(payload.get("plan") or "basic_estimates"),
            device=str(payload.get("device") or "auto"),
            source="session",
        )
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=401, detail="invalid Vista session token") from error


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authorization: Bearer token is required")
    return authorization.split(" ", 1)[1].strip()


def current_session(authorization: str | None = Header(default=None)) -> SessionPrincipal:
    return _verify_session_token(_bearer(authorization))


def optional_session(authorization: str | None = Header(default=None)) -> SessionPrincipal | None:
    if not authorization:
        return None
    return current_session(authorization)


def ensure_role(principal: SessionPrincipal, *roles: str) -> SessionPrincipal:
    if principal.role not in roles:
        raise HTTPException(status_code=403, detail="this function is not available for the current role")
    return principal


def validate_requested_role(role: str, supplied_token: str | None) -> None:
    public_roles = {"client", "client_pro"}
    if role in public_roles:
        return
    allowed_roles = {"operator", "server_admin", "developer", "owner"}
    if role not in allowed_roles:
        raise HTTPException(status_code=400, detail="unknown Vista role")
    expected = os.environ.get("VISTA_OWNER_ACCESS_TOKEN") or os.environ.get("VISTA_ADMIN_TOKEN")
    if not expected:
        if os.environ.get("VISTA_ENV", "local").lower() in {"prod", "production"}:
            raise HTTPException(status_code=503, detail="VISTA_OWNER_ACCESS_TOKEN is not configured")
        expected = "vista-local-owner"
    if not supplied_token or not hmac.compare_digest(supplied_token, expected):
        raise HTTPException(status_code=403, detail="privileged Vista role requires owner access token")


def openai_gateway_principal(authorization: str | None = Header(default=None)) -> SessionPrincipal:
    token = _bearer(authorization)
    if token.startswith("vista_session_"):
        return _verify_session_token(token)
    if token.startswith("vista_sk_"):
        from .database import STORE, NotFound, PolicyViolation

        try:
            key = STORE.authenticate_developer_api_key(token)
        except (NotFound, PolicyViolation) as error:
            raise HTTPException(status_code=401, detail="invalid Vista API key") from error
        session = key["session"]
        return SessionPrincipal(
            session_id=session["id"],
            role=session["role"],
            plan=session["plan"],
            device="api",
            source="developer_key",
            scopes=tuple(key.get("scopes", [])),
        )
    raise HTTPException(status_code=401, detail="invalid Vista/OpenAI-compatible token")
