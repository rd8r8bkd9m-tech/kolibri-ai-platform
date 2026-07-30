"""Atomic public Shell bootstrap."""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, Request, Response

from app.browser_session import (
    SESSION_COOKIE_NAME,
    bootstrap_browser_session,
)
from app.auth import get_optional_user
from app.models import UserDB
from app.project_schemas import ShellBootstrapResponse


router = APIRouter(prefix="/api/v1/shell", tags=["shell"])
public_router = APIRouter(tags=["shell", "public-session"])


@router.post("/bootstrap", response_model=ShellBootstrapResponse)
def bootstrap_shell(
    request: Request,
    response: Response,
    anonymous_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    user: UserDB | None = Depends(get_optional_user),
):
    return bootstrap_browser_session(request, response, anonymous_cookie, user)


def _public_session_payload(session):
    now = datetime.now(timezone.utc).isoformat()
    session_id = str(session["session_id"])
    return {
        "id": session_id,
        "object": "public.session",
        "active": True,
        "project": {
            "id": "project_ephemeral_default",
            "object": "project.ephemeral",
            "created_at": now,
            "updated_at": now,
        },
        "model": os.getenv("MIMO_MODEL", "mimo-auto"),
    }


@public_router.get("/v1/public/session")
@public_router.post("/v1/public/session")
def public_session(
    request: Request,
    response: Response,
    anonymous_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    user: UserDB | None = Depends(get_optional_user),
):
    session = bootstrap_browser_session(request, response, anonymous_cookie, user)
    return _public_session_payload(session)
