"""Atomic public Shell bootstrap."""

from fastapi import APIRouter, Cookie, Depends, Request, Response

from app.browser_session import (
    SESSION_COOKIE_NAME,
    _optional_user,
    bootstrap_browser_session,
)
from app.models import UserDB
from app.project_schemas import ShellBootstrapResponse


router = APIRouter(prefix="/api/v1/shell", tags=["shell"])


@router.post("/bootstrap", response_model=ShellBootstrapResponse)
def bootstrap_shell(
    request: Request,
    response: Response,
    anonymous_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    user: UserDB | None = Depends(_optional_user),
):
    return bootstrap_browser_session(request, response, anonymous_cookie, user)
