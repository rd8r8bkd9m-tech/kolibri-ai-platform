from __future__ import annotations

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel

from ..auth import sign_session, verify_session
from ..errors import APIError

router = APIRouter(tags=["shell"])


class BootstrapRequest(BaseModel):
    role: str = "client"
    project_title: str | None = None


@router.post("/v1/shell/bootstrap")
def bootstrap(
    payload: BootstrapRequest,
    request: Request,
    response: Response,
    x_kolibri_access_token: str | None = Header(default=None, alias="X-Kolibri-Access-Token"),
):
    settings = request.app.state.settings
    store = request.app.state.store
    origin = request.headers.get("origin")
    if settings.env == "production" and origin and origin not in settings.allowed_origins:
        raise APIError("The request origin is not allowed.", 403, "permission_error", code="origin_not_allowed")

    cookie = request.cookies.get(settings.session_cookie)
    session_id = verify_session(cookie, settings.session_secret) if cookie else None
    session = store.get_session(session_id) if session_id else None
    if not session:
        requested_role = payload.role if payload.role in {"client", "operator", "owner", "developer"} else "client"
        role_tokens = {
            "owner": settings.owner_access_token,
            "operator": settings.operator_access_token,
            "developer": settings.developer_access_token,
        }
        required_token = role_tokens.get(requested_role)
        if requested_role != "client":
            if not required_token or not x_kolibri_access_token or x_kolibri_access_token != required_token:
                raise APIError(
                    f"The role '{requested_role}' requires a privileged access token.",
                    403,
                    "permission_error",
                    "role",
                    "role_escalation_denied",
                )
        session = store.create_session(requested_role)
        session_id = session["id"]
    projects = store.list_projects(session_id)
    project = projects[0] if projects else store.create_project(session_id, payload.project_title or "Первый проект")
    token = sign_session(session_id, settings.session_secret)
    response.set_cookie(
        settings.session_cookie,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.env == "production",
        max_age=60 * 60 * 24 * 30,
        path="/",
    )
    session_payload = {"id": session_id, "role": session["role"]}
    if settings.expose_session_token:
        session_payload["token"] = token
    return {
        "object": "kolibri.shell.bootstrap",
        "session": session_payload,
        "active_project": project,
        "projects": projects or [project],
        "capabilities": request.app.state.capabilities.for_role(session["role"]),
        "model": "kolibri",
        "authority": "home",
    }
