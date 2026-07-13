from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..auth import Principal, principal_from_request, require_roles
from ..errors import APIError

router = APIRouter(tags=["api-keys"])


class APIKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: str = "developer"


def _public(row: dict) -> dict:
    return {
        "id": row["id"],
        "object": "api_key",
        "name": row["name"],
        "key_prefix": row["key_prefix"],
        "role": row["role"],
        "created_at": row["created_at"],
        "last_used_at": row.get("last_used_at"),
        "revoked_at": row.get("revoked_at"),
    }


@router.post("/v1/api-keys")
def create_api_key(
    payload: APIKeyCreate,
    request: Request,
    principal: Principal = Depends(principal_from_request),
):
    require_roles(principal, "developer", "owner")
    allowed = {"client", "developer"} if principal.role == "developer" else {"client", "developer", "operator", "owner"}
    if payload.role not in allowed:
        raise APIError(
            f"The role '{payload.role}' cannot be assigned by this principal.",
            403,
            "permission_error",
            "role",
            "role_assignment_denied",
        )
    row, raw = request.app.state.store.create_api_key(
        principal.session_id,
        payload.role,
        payload.name,
    )
    return {**_public(row), "key": raw}


@router.get("/v1/api-keys")
def list_api_keys(request: Request, principal: Principal = Depends(principal_from_request)):
    require_roles(principal, "developer", "owner")
    rows = request.app.state.store.list_api_keys(
        principal.session_id,
        include_all=principal.role == "owner",
    )
    return {"object": "list", "data": [_public(row) for row in rows]}


@router.delete("/v1/api-keys/{key_id}")
def revoke_api_key(
    key_id: str,
    request: Request,
    principal: Principal = Depends(principal_from_request),
):
    require_roles(principal, "developer", "owner")
    row = request.app.state.store.revoke_api_key(
        key_id,
        principal.session_id,
        include_all=principal.role == "owner",
    )
    if not row:
        raise APIError("API key not found.", 404, code="api_key_not_found")
    return {"id": key_id, "object": "api_key.deleted", "deleted": True}
