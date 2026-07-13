from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from fastapi import Cookie, Header, Request

from .config import Settings
from .errors import APIError


@dataclass(frozen=True)
class Principal:
    session_id: str
    role: str = "client"
    auth_type: str = "session"
    api_key_id: str | None = None


def sign_session(session_id: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), session_id.encode(), hashlib.sha256).hexdigest()
    return f"{session_id}.{digest}"


def verify_session(token: str, secret: str) -> str | None:
    try:
        session_id, supplied = token.rsplit(".", 1)
    except ValueError:
        return None
    expected = hmac.new(secret.encode(), session_id.encode(), hashlib.sha256).hexdigest()
    return session_id if hmac.compare_digest(supplied, expected) else None


def principal_from_token(app: Any, token: str | None) -> Principal | None:
    if not token:
        return None
    settings: Settings = app.state.settings
    store = app.state.store

    session_id = verify_session(token, settings.session_secret)
    if session_id:
        row = store.get_session(session_id)
        if row:
            return Principal(session_id=session_id, role=row["role"], auth_type="session")

    key = store.authenticate_api_key(token)
    if key:
        return Principal(
            session_id=key["session_id"],
            role=key["role"],
            auth_type="api_key",
            api_key_id=key["id"],
        )
    return None


async def principal_from_request(
    request: Request,
    authorization: str | None = Header(default=None),
    x_kolibri_session: str | None = Header(default=None),
    kolibri_session: str | None = Cookie(default=None),
) -> Principal:
    token = x_kolibri_session or kolibri_session
    bearer = False
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        bearer = True
    if not token:
        raise APIError(
            "A session or bearer token is required.",
            401,
            "authentication_error",
            code="missing_authentication",
        )
    principal = principal_from_token(request.app, token)
    if not principal:
        code = "invalid_api_key" if bearer and token.startswith("sk-") else "invalid_session"
        message = "The supplied API key is invalid." if code == "invalid_api_key" else "The supplied session token is invalid."
        raise APIError(message, 401, "authentication_error", code=code)
    request.state.session_id = principal.session_id
    request.state.principal = principal
    return principal


def require_roles(principal: Principal, *roles: str) -> None:
    if principal.role not in set(roles):
        raise APIError(
            "This API key or session is not permitted to perform the requested operation.",
            403,
            "permission_error",
            code="insufficient_permissions",
        )


def require_node(request: Request, token: str | None) -> None:
    expected = request.app.state.settings.node_join_token
    if expected and not token:
        raise APIError("Node authentication is required.", 401, "authentication_error", code="node_auth_required")
    if expected and not hmac.compare_digest(expected, token or ""):
        raise APIError("Invalid node token.", 401, "authentication_error", code="invalid_node_token")
