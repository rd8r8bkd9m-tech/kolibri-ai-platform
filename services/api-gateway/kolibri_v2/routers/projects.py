from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..auth import Principal, principal_from_request
from ..errors import APIError

router = APIRouter(tags=["projects"])


class ProjectCreate(BaseModel):
    title: str = Field(default="Новый проект", min_length=1, max_length=160)


class ProjectPatch(BaseModel):
    title: str = Field(min_length=1, max_length=160)


class MessageCreate(BaseModel):
    role: str = "user"
    content: str = Field(min_length=1)


@router.get("/v1/projects")
def list_projects(request: Request, principal: Principal = Depends(principal_from_request)):
    return {"object": "list", "data": request.app.state.store.list_projects(principal.session_id)}


@router.post("/v1/projects")
def create_project(payload: ProjectCreate, request: Request, principal: Principal = Depends(principal_from_request)):
    return request.app.state.store.create_project(principal.session_id, payload.title)


@router.get("/v1/projects/{project_id}")
def get_project(project_id: str, request: Request, principal: Principal = Depends(principal_from_request)):
    project = request.app.state.store.get_project(project_id, principal.session_id)
    if not project or project.get("deleted_at"):
        raise APIError("Project not found.", 404, "invalid_request_error", "project_id", "project_not_found")
    return project


@router.patch("/v1/projects/{project_id}")
def patch_project(project_id: str, payload: ProjectPatch, request: Request, principal: Principal = Depends(principal_from_request)):
    project = request.app.state.store.update_project(project_id, principal.session_id, payload.title)
    if not project:
        raise APIError("Project not found.", 404, code="project_not_found")
    return project


@router.delete("/v1/projects/{project_id}")
def delete_project(project_id: str, request: Request, principal: Principal = Depends(principal_from_request)):
    if not request.app.state.store.get_project(project_id, principal.session_id):
        raise APIError("Project not found.", 404, code="project_not_found")
    request.app.state.store.soft_delete_project(project_id, principal.session_id)
    return {"id": project_id, "object": "project.deleted", "deleted": True}


@router.post("/v1/projects/{project_id}/restore")
def restore_project(project_id: str, request: Request, principal: Principal = Depends(principal_from_request)):
    project = request.app.state.store.restore_project(project_id, principal.session_id)
    if not project:
        raise APIError("Project not found.", 404, code="project_not_found")
    return project


@router.get("/v1/projects/{project_id}/messages")
def list_messages(project_id: str, request: Request, principal: Principal = Depends(principal_from_request)):
    if not request.app.state.store.get_project(project_id, principal.session_id):
        raise APIError("Project not found.", 404, code="project_not_found")
    return {"object": "list", "data": request.app.state.store.list_messages(project_id)}


@router.post("/v1/projects/{project_id}/messages")
def add_message(project_id: str, payload: MessageCreate, request: Request, principal: Principal = Depends(principal_from_request)):
    if not request.app.state.store.get_project(project_id, principal.session_id):
        raise APIError("Project not found.", 404, code="project_not_found")
    if payload.role not in {"user", "assistant", "system"}:
        raise APIError("Unsupported message role.", 400, "invalid_request_error", "role", "invalid_role")
    return request.app.state.store.add_message(project_id, payload.role, payload.content)
