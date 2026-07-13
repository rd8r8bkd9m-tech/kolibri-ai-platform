from __future__ import annotations

import hashlib
import socket
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile
from pydantic import BaseModel, Field

from ..auth import Principal, principal_from_request, require_node
from ..errors import APIError

router = APIRouter(tags=["runtime"])


class NodeRegistration(BaseModel):
    node_id: str
    hostname: str = Field(default_factory=socket.gethostname)
    capabilities: list[str] = Field(default_factory=list)


class NodeHeartbeat(BaseModel):
    status: str = "online"
    capabilities: list[str] = Field(default_factory=list)
    active_attempts: list[str] = Field(default_factory=list)


class TaskCreate(BaseModel):
    project_id: str | None = None
    kind: str = "health_probe"
    title: str = "Kolibri task"
    input: dict[str, Any] = Field(default_factory=dict)
    required_capabilities: list[str] = Field(default_factory=list)
    required_artifacts: list[str] = Field(default_factory=lambda: ["RESULT.md"])
    max_attempts: int = Field(default=3, ge=1, le=20)


class LeaseRequest(BaseModel):
    node_id: str
    capabilities: list[str] = Field(default_factory=list)
    lease_seconds: int = Field(default=60, ge=10, le=900)


class LeaseHeartbeat(BaseModel):
    node_id: str
    lease_id: str
    fencing_token: int
    lease_seconds: int = Field(default=60, ge=10, le=900)


class TaskComplete(BaseModel):
    node_id: str
    lease_id: str
    fencing_token: int
    result: dict[str, Any] = Field(default_factory=dict)


class TaskFail(BaseModel):
    reason: str


@router.get("/v1/capabilities")
def capabilities(request: Request, principal: Principal = Depends(principal_from_request)):
    return {"object": "list", "data": request.app.state.capabilities.for_role(principal.role)}


@router.get("/v1/tools")
def tools(request: Request, principal: Principal = Depends(principal_from_request)):
    mapping = {
        "chat": ["responses"],
        "history": ["projects"],
        "estimates": ["estimate_editor", "estimate_export"],
        "documents": ["document_preview"],
        "files": ["artifact_download"],
        "factory": ["task_submit", "runtime_summary"],
    }
    available = request.app.state.capabilities.for_role(principal.role)
    data = []
    for capability in available:
        for tool in mapping.get(capability["id"], []):
            data.append({"id": tool, "object": "tool", "capability": capability["id"], "available": True})
    return {"object": "list", "data": data}


@router.get("/v1/runtime/summary")
def runtime_summary(request: Request, principal: Principal = Depends(principal_from_request)):
    tasks = request.app.state.store.list_tasks(); nodes = request.app.state.store.list_nodes()
    state_counts: dict[str, int] = {}
    for task in tasks: state_counts[task["status"]] = state_counts.get(task["status"], 0) + 1
    return {
        "object": "runtime.summary",
        "authority": "home",
        "availability": "live",
        "nodes": len(nodes),
        "tasks": state_counts,
        "capabilities": request.app.state.capabilities.for_role(principal.role),
    }


@router.get("/v1/runtime/dags")
def runtime_dags(request: Request, principal: Principal = Depends(principal_from_request)):
    return {"object": "list", "data": []}


@router.get("/v1/runtime/actors")
def runtime_actors(request: Request, principal: Principal = Depends(principal_from_request)):
    nodes = request.app.state.store.list_nodes()
    return {"object": "list", "data": [{"id": f"actor:{node['id']}", "node_id": node["id"], "state": "idle"} for node in nodes]}


@router.get("/v1/providers/health")
def providers_health(request: Request, principal: Principal = Depends(principal_from_request)):
    configured = bool(request.app.state.settings.openai_api_key and request.app.state.settings.openai_base_url)
    return {"object": "provider.health", "data": [{"id": "openai", "availability": "live" if configured else "unavailable", "source": "configuration"}]}


@router.post("/v1/nodes/register")
def register_node(payload: NodeRegistration, request: Request, x_kolibri_node_token: str | None = Header(default=None)):
    require_node(request, x_kolibri_node_token)
    return request.app.state.store.upsert_node(payload.node_id, payload.hostname, payload.capabilities)


@router.post("/v1/nodes/{node_id}/heartbeat")
def heartbeat_node(node_id: str, payload: NodeHeartbeat, request: Request, x_kolibri_node_token: str | None = Header(default=None)):
    require_node(request, x_kolibri_node_token)
    current = request.app.state.store.get_node(node_id)
    if not current:
        raise APIError("Node not registered.", 404, code="node_not_found")
    return request.app.state.store.upsert_node(node_id, current["hostname"], payload.capabilities or current["capabilities"], payload.status)


@router.get("/v1/fleet/nodes")
def fleet_nodes(request: Request, principal: Principal = Depends(principal_from_request)):
    if principal.role not in {"operator", "owner"}:
        raise APIError("Insufficient permissions.", 403, "permission_error", code="forbidden")
    return {"object": "list", "data": request.app.state.store.list_nodes()}


@router.post("/v1/tasks")
def create_task(payload: TaskCreate, request: Request, principal: Principal = Depends(principal_from_request)):
    if principal.role not in {"operator", "owner", "developer"}:
        raise APIError("Insufficient permissions.", 403, "permission_error", code="forbidden")
    return request.app.state.store.create_task(payload.model_dump(), principal.session_id)


@router.get("/v1/tasks")
def list_tasks(request: Request, principal: Principal = Depends(principal_from_request)):
    if principal.role not in {"operator", "owner", "developer"}:
        raise APIError("Insufficient permissions.", 403, "permission_error", code="forbidden")
    return {"object": "list", "data": request.app.state.store.list_tasks()}


@router.get("/v1/tasks/{task_id}")
def get_task(task_id: str, request: Request, principal: Principal = Depends(principal_from_request)):
    task = request.app.state.store.get_task(task_id)
    if not task:
        raise APIError("Task not found.", 404, code="task_not_found")
    return task


@router.post("/v1/tasks/lease")
def lease_task(payload: LeaseRequest, request: Request, x_kolibri_node_token: str | None = Header(default=None)):
    require_node(request, x_kolibri_node_token)
    node = request.app.state.store.get_node(payload.node_id)
    if not node or node.get("draining"):
        return {"object": "task.lease", "task": None, "reason": "node_unavailable"}
    task = request.app.state.store.lease_task(payload.node_id, payload.capabilities, payload.lease_seconds)
    return {"object": "task.lease", "task": task}


@router.post("/v1/tasks/{task_id}/heartbeat")
def task_heartbeat(task_id: str, payload: LeaseHeartbeat, request: Request, x_kolibri_node_token: str | None = Header(default=None)):
    require_node(request, x_kolibri_node_token)
    try:
        return request.app.state.store.heartbeat_task(task_id, payload.node_id, payload.lease_id, payload.fencing_token, payload.lease_seconds)
    except ValueError:
        raise APIError("The lease is stale or owned by another attempt.", 409, "conflict_error", code="stale_lease")


@router.post("/v1/tasks/{task_id}/artifacts")
async def upload_task_artifact(
    task_id: str,
    request: Request,
    node_id: str = Form(...),
    lease_id: str = Form(...),
    fencing_token: int = Form(...),
    file: UploadFile = File(...),
    x_kolibri_node_token: str | None = Header(default=None),
):
    require_node(request, x_kolibri_node_token)
    task = request.app.state.store.get_task(task_id)
    if not task or task["lease_owner"] != node_id or task["lease_id"] != lease_id or int(task["fencing_token"]) != int(fencing_token):
        raise APIError("The lease is stale or owned by another attempt.", 409, "conflict_error", code="stale_lease")
    data = await file.read()
    if not data:
        raise APIError("Artifact bytes are empty.", 400, "invalid_request_error", "file", "empty_artifact")
    artifact = request.app.state.artifacts.materialize(
        session_id=task.get("session_id") or "system",
        project_id=task.get("project_id"),
        task_id=task_id,
        name=file.filename or "artifact.bin",
        mime_type=file.content_type or "application/octet-stream",
        data=data,
    )
    request.app.state.store.append_task_event(task_id, "artifact.written", {"artifact_id": artifact["id"], "name": artifact["name"], "sha256": artifact["sha256"], "size": artifact["size"]})
    return artifact


@router.post("/v1/tasks/{task_id}/complete")
def complete_task(task_id: str, payload: TaskComplete, request: Request, x_kolibri_node_token: str | None = Header(default=None)):
    require_node(request, x_kolibri_node_token)
    try:
        return request.app.state.store.complete_task(task_id, payload.node_id, payload.lease_id, payload.fencing_token, payload.result)
    except ValueError as exc:
        code = str(exc).split(":",1)[0]
        status = 409 if code == "stale_lease" else 422
        raise APIError(str(exc), status, "conflict_error" if status == 409 else "invalid_request_error", code=code)


@router.post("/v1/tasks/{task_id}/fail")
def fail_task(task_id: str, payload: TaskFail, request: Request, x_kolibri_node_token: str | None = Header(default=None)):
    require_node(request, x_kolibri_node_token)
    try:
        return request.app.state.store.fail_task(task_id, payload.reason)
    except KeyError:
        raise APIError("Task not found.", 404, code="task_not_found")


@router.get("/v1/tasks/{task_id}/events")
def task_events(task_id: str, request: Request, principal: Principal = Depends(principal_from_request)):
    if not request.app.state.store.get_task(task_id):
        raise APIError("Task not found.", 404, code="task_not_found")
    return {"object": "list", "data": request.app.state.store.list_task_events(task_id)}
