from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import time
import uuid
from urllib.parse import urlencode
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .services.auth import (
    SessionPrincipal,
    current_session,
    ensure_role,
    issue_session_token,
    openai_gateway_principal,
    optional_session,
    validate_requested_role,
)
from .services.database import STORE, NotFound, PolicyViolation, now
from .services.policy import can_render_component, resolve_os_turn

VERSION = "2026.07.vista-os-11.1-product-release"
app = FastAPI(title="Vista OS API", version=VERSION)
LOGGER = logging.getLogger("vista.api")


def _cors_origins() -> list[str]:
    raw = os.environ.get("VISTA_ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").strip()
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _production_mode() -> bool:
    return os.environ.get("VISTA_ENV", "local").lower() in {"prod", "production"}


def _dependency_state() -> dict[str, Any]:
    state: dict[str, Any] = {"database": "unknown", "artifacts": "unknown"}
    try:
        with STORE.connect() as connection:
            connection.execute("SELECT 1").fetchone()
            integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
        state["database"] = "ok" if integrity == "ok" else f"integrity:{integrity}"
    except Exception as error:  # pragma: no cover - failure path is runtime-specific
        state["database"] = f"error:{type(error).__name__}"

    try:
        artifact_root = Path(os.environ.get("VISTA_ARTIFACT_ROOT", str(Path(__file__).resolve().parents[2] / "var" / "artifacts")))
        artifact_root.mkdir(parents=True, exist_ok=True)
        probe = artifact_root / f".readiness-{uuid.uuid4().hex}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        state["artifacts"] = "ok"
    except Exception as error:  # pragma: no cover - failure path is runtime-specific
        state["artifacts"] = f"error:{type(error).__name__}"
    return state


@app.middleware("http")
async def vista_http_contract(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or f"vista_{uuid.uuid4().hex}"
    started = time.perf_counter()
    max_body = int(os.environ.get("VISTA_MAX_BODY_BYTES", str(25 * 1024 * 1024)))
    raw_length = request.headers.get("content-length")
    if raw_length and raw_length.isdigit() and int(raw_length) > max_body:
        response = JSONResponse(status_code=413, content={"detail": "request body is too large", "request_id": request_id})
    else:
        try:
            response = await call_next(request)
        except Exception:
            LOGGER.exception("Vista request failed", extra={"request_id": request_id, "path": request.url.path})
            raise

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), payment=(), usb=()"
    response.headers["Server-Timing"] = f"vista;dur={duration_ms}"
    if request.url.path.startswith(("/api", "/v1")):
        response.headers["Cache-Control"] = "no-store"
    if _production_mode():
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if os.environ.get("VISTA_JSON_LOGS", "1") != "0":
        LOGGER.info(json.dumps({
            "event": "http.request",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
        }, ensure_ascii=False))
    return response


def _expected_node_signature(secret: str, method: str, path: str, body: bytes) -> str:
    import hashlib

    message = method.upper().encode("utf-8") + b"\n" + path.encode("utf-8") + b"\n" + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


async def verify_node_request(request: Request) -> None:
    strict_production = os.environ.get("VISTA_ENV", "local").lower() in {"prod", "production"}
    expected_token = os.environ.get("VISTA_NODE_JOIN_TOKEN")
    signing_secret = os.environ.get("VISTA_NODE_SIGNING_SECRET")
    if strict_production and not expected_token:
        raise HTTPException(status_code=503, detail="production node token is not configured")
    if strict_production and not signing_secret:
        raise HTTPException(status_code=503, detail="production node signing secret is not configured")
    if expected_token:
        token = request.headers.get("X-Vista-Node-Token")
        if not token or not hmac.compare_digest(token, expected_token):
            raise HTTPException(status_code=401, detail="invalid node token")
    if signing_secret:
        signature = request.headers.get("X-Vista-Node-Signature")
        body = await request.body()
        expected = _expected_node_signature(signing_secret, request.method, request.url.path, body)
        if not signature or not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=401, detail="invalid node signature")


class ResolveRequest(BaseModel):
    text: str = "сделай смету"
    device: str | None = None


class SessionRequest(BaseModel):
    role: str = "client"
    device: str = "auto"
    plan: str | None = None


class ItemRequest(BaseModel):
    section: str = "Работы"
    name: str = "Новая позиция"
    unit: str = "шт"
    qty: float = Field(default=1, ge=0)
    price: float = Field(default=0, ge=0)
    coef: float = Field(default=1, ge=0)


class LeadRequest(BaseModel):
    name: str = "Новый лид"
    phone: str | None = None
    source: str = "app"
    status: str = "new"
    brief: dict[str, Any] = Field(default_factory=dict)


class ShareRequest(BaseModel):
    ttl_hours: int = Field(default=168, ge=1, le=24 * 365)

class DeveloperKeyRequest(BaseModel):
    name: str = Field(default="Vista OpenAI SDK key", min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: ["openai.proxy"])


def not_found(error: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(error).strip("'"))


def bad_request(error: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


def _all_access(principal: SessionPrincipal) -> bool:
    return principal.role in {"operator", "owner"}


def _require_own_session(session_id: str, principal: SessionPrincipal) -> None:
    if principal.session_id != session_id and principal.role != "owner":
        raise HTTPException(status_code=403, detail="session isolation violation")


@app.get("/api/live")
def live() -> dict[str, Any]:
    return {"status": "ok", "service": "vista-api", "version": VERSION, "time": now()}


@app.get("/api/ready")
def ready() -> Response:
    dependencies = _dependency_state()
    ready_state = all(value == "ok" for value in dependencies.values())
    return JSONResponse(
        status_code=200 if ready_state else 503,
        content={
            "status": "ready" if ready_state else "not_ready",
            "service": "vista-api",
            "version": VERSION,
            "dependencies": dependencies,
            "time": now(),
        },
    )


@app.get("/api/health")
def health() -> dict[str, Any]:
    dependencies = _dependency_state()
    return {
        "status": "ok" if all(value == "ok" for value in dependencies.values()) else "degraded",
        "product": "Vista OS",
        "version": STORE.manifest["version"],
        "api_version": VERSION,
        "dependencies": dependencies,
        "time": now(),
    }


@app.get("/api/os/manifest")
def manifest() -> dict[str, Any]:
    return STORE.manifest


@app.post("/api/os/session")
def create_session(req: SessionRequest, x_vista_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    validate_requested_role(req.role, x_vista_admin_token)
    session = STORE.create_session(req.role, req.device, req.plan)
    return {"session": session, "token": issue_session_token(session)}


@app.get("/api/os/session/{session_id}")
def get_session(session_id: str, principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    _require_own_session(session_id, principal)
    try:
        return STORE.get_session(session_id)
    except NotFound as error:
        raise not_found(error)


@app.patch("/api/os/session/{session_id}")
def patch_session(session_id: str, patch: dict[str, Any], principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    _require_own_session(session_id, principal)
    patch.pop("role", None)
    patch.pop("plan", None)
    try:
        return STORE.update_session(session_id, patch)
    except NotFound as error:
        raise not_found(error)


@app.post("/api/os/resolve")
def resolve(req: ResolveRequest, principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    return resolve_os_turn(principal.role, req.text, req.device or principal.device)


@app.post("/api/workbench/sessions/{session_id}/windows/{component_id}/open")
def open_window(
    session_id: str,
    component_id: str,
    payload: dict[str, Any] | None = None,
    principal: SessionPrincipal = Depends(current_session),
) -> dict[str, Any]:
    _require_own_session(session_id, principal)
    if not can_render_component(principal.role, component_id):
        raise HTTPException(status_code=403, detail="component is not available for this role")
    try:
        return STORE.open_window(session_id, component_id, (payload or {}).get("label"))
    except NotFound as error:
        raise not_found(error)


@app.post("/api/workbench/sessions/{session_id}/windows/{component_id}/close")
def close_window(session_id: str, component_id: str, principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    _require_own_session(session_id, principal)
    try:
        return STORE.close_window(session_id, component_id)
    except NotFound as error:
        raise not_found(error)


@app.get("/api/estimates")
def list_estimates(principal: SessionPrincipal = Depends(current_session)) -> list[dict[str, Any]]:
    return STORE.list_estimates(owner_session_id=principal.session_id, include_all=_all_access(principal))


@app.post("/api/estimates")
def create_estimate(payload: dict[str, Any], principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    return STORE.create_estimate(payload, owner_session_id=principal.session_id)


@app.get("/api/estimates/{estimate_id}")
def get_estimate(estimate_id: str, principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    try:
        return STORE.get_estimate(estimate_id, owner_session_id=principal.session_id, include_all=_all_access(principal))
    except NotFound as error:
        raise not_found(error)


@app.patch("/api/estimates/{estimate_id}")
def update_estimate(estimate_id: str, payload: dict[str, Any], principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    try:
        return STORE.update_estimate(estimate_id, payload, owner_session_id=principal.session_id)
    except NotFound as error:
        raise not_found(error)
    except PolicyViolation as error:
        raise bad_request(error)


@app.post("/api/estimates/{estimate_id}/items")
def add_item(estimate_id: str, item: ItemRequest, principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    try:
        return STORE.add_estimate_item(estimate_id, item.model_dump(), owner_session_id=principal.session_id)
    except NotFound as error:
        raise not_found(error)


@app.patch("/api/estimates/{estimate_id}/items/{item_id}")
def update_item(estimate_id: str, item_id: str, patch: dict[str, Any], principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    try:
        return STORE.update_estimate_item(estimate_id, item_id, patch, owner_session_id=principal.session_id)
    except NotFound as error:
        raise not_found(error)


@app.delete("/api/estimates/{estimate_id}/items/{item_id}")
def delete_item(estimate_id: str, item_id: str, principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    try:
        return STORE.delete_estimate_item(estimate_id, item_id, owner_session_id=principal.session_id)
    except NotFound as error:
        raise not_found(error)


@app.post("/api/estimates/{estimate_id}/versions")
def save_version(estimate_id: str, payload: dict[str, Any] | None = None, principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    try:
        return STORE.save_estimate_version(estimate_id, note=(payload or {}).get("note", "Ручное сохранение"), owner_session_id=principal.session_id)
    except NotFound as error:
        raise not_found(error)


@app.get("/api/estimates/{estimate_id}/versions")
def versions(estimate_id: str, principal: SessionPrincipal = Depends(current_session)) -> list[dict[str, Any]]:
    try:
        return STORE.list_estimate_versions(estimate_id, owner_session_id=principal.session_id)
    except NotFound as error:
        raise not_found(error)


@app.get("/api/estimates/{estimate_id}/proposal")
def proposal(estimate_id: str, principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    try:
        return STORE.proposal(estimate_id, owner_session_id=principal.session_id)
    except NotFound as error:
        raise not_found(error)


@app.post("/api/estimates/{estimate_id}/documents")
def generate_documents(estimate_id: str, principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    try:
        return STORE.generate_estimate_documents(estimate_id, owner_session_id=principal.session_id)
    except NotFound as error:
        raise not_found(error)
    except PolicyViolation as error:
        raise bad_request(error)


@app.get("/api/estimates/{estimate_id}/artifacts")
def estimate_artifacts(estimate_id: str, principal: SessionPrincipal = Depends(current_session)) -> list[dict[str, Any]]:
    try:
        return STORE.get_artifacts(estimate_id, owner_session_id=principal.session_id)
    except NotFound as error:
        raise not_found(error)


@app.get("/api/artifacts/{artifact_id}")
def artifact_payload(artifact_id: str, principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    try:
        return STORE.get_artifact_payload(artifact_id, owner_session_id=principal.session_id, include_all=_all_access(principal))
    except NotFound as error:
        raise not_found(error)


@app.get("/api/artifacts/{artifact_id}/download")
def artifact_download(artifact_id: str, principal: SessionPrincipal = Depends(current_session)) -> Response:
    try:
        artifact = STORE.get_artifact_payload(artifact_id, owner_session_id=principal.session_id, include_all=_all_access(principal))
    except NotFound as error:
        raise not_found(error)
    if artifact.get("file_path"):
        path = Path(artifact["file_path"])
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=410, detail="artifact file is unavailable")
        return FileResponse(path, media_type=artifact["content_type"], filename=artifact["name"])
    return Response(
        content=artifact.get("payload", ""),
        media_type=artifact["content_type"],
        headers={"Content-Disposition": f'attachment; filename="{artifact["name"]}"'},
    )


@app.post("/api/estimates/{estimate_id}/share")
def create_share(estimate_id: str, req: ShareRequest, principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    try:
        return STORE.create_share_link(estimate_id, owner_session_id=principal.session_id, ttl_hours=req.ttl_hours)
    except NotFound as error:
        raise not_found(error)


@app.get("/api/public/share/{token}")
def public_share(token: str) -> dict[str, Any]:
    try:
        return STORE.public_share(token)
    except NotFound as error:
        raise not_found(error)


@app.get("/api/public/share/{token}/artifacts/{artifact_id}/download")
def public_artifact_download(token: str, artifact_id: str) -> Response:
    try:
        artifact = STORE.public_artifact(token, artifact_id)
    except NotFound as error:
        raise not_found(error)
    if artifact.get("file_path"):
        path = Path(artifact["file_path"])
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=410, detail="artifact file is unavailable")
        return FileResponse(path, media_type=artifact["content_type"], filename=artifact["name"])
    return Response(
        content=artifact.get("payload", ""),
        media_type=artifact["content_type"],
        headers={"Content-Disposition": f'attachment; filename="{artifact["name"]}"'},
    )


@app.get("/api/estimates/{estimate_id}/shares")
def estimate_shares(estimate_id: str, principal: SessionPrincipal = Depends(current_session)) -> list[dict[str, Any]]:
    try:
        return STORE.list_share_links(estimate_id, owner_session_id=principal.session_id)
    except NotFound as error:
        raise not_found(error)


@app.delete("/api/estimates/{estimate_id}/shares/{token}")
def revoke_estimate_share(estimate_id: str, token: str, principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    try:
        return STORE.revoke_share_link(estimate_id, token, owner_session_id=principal.session_id)
    except NotFound as error:
        raise not_found(error)


@app.get("/api/leads")
def leads(principal: SessionPrincipal = Depends(current_session)) -> list[dict[str, Any]]:
    ensure_role(principal, "operator", "owner")
    return STORE.list_leads()


@app.post("/api/leads")
def create_lead(req: LeadRequest, principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    return STORE.create_lead(req.model_dump() | {"owner_session_id": principal.session_id})


@app.get("/api/nodes")
def nodes(principal: SessionPrincipal = Depends(current_session)) -> list[dict[str, Any]]:
    ensure_role(principal, "operator", "server_admin", "owner")
    return STORE.list_nodes()


@app.post("/api/nodes/register", dependencies=[Depends(verify_node_request)])
def register_node(payload: dict[str, Any]) -> dict[str, Any]:
    return STORE.register_node(payload)


@app.post("/api/nodes/{node_id}/heartbeat", dependencies=[Depends(verify_node_request)])
def heartbeat_node(node_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return STORE.heartbeat_node(node_id, payload)
    except NotFound as error:
        raise not_found(error)


@app.get("/api/server/metrics")
def metrics(principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    ensure_role(principal, "server_admin", "owner")
    return STORE.server_metrics()


@app.get("/api/server/logs")
def logs(principal: SessionPrincipal = Depends(current_session)) -> list[dict[str, Any]]:
    ensure_role(principal, "server_admin", "owner")
    return STORE.server_logs()


@app.get("/api/factory/tasks")
def factory_tasks(principal: SessionPrincipal = Depends(current_session)) -> list[dict[str, Any]]:
    ensure_role(principal, "operator", "owner")
    return STORE.list_factory_tasks()


@app.post("/api/factory/tasks")
def create_factory_task(payload: dict[str, Any], principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    ensure_role(principal, "operator", "owner")
    return STORE.create_factory_task(payload)


@app.get("/api/factory/tasks/{task_id}")
def get_factory_task(task_id: str, principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    ensure_role(principal, "operator", "owner")
    try:
        return STORE.get_factory_task(task_id)
    except NotFound as error:
        raise not_found(error)


@app.post("/api/factory/tasks/lease", dependencies=[Depends(verify_node_request)])
def lease_factory_task(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return STORE.lease_task(payload)
    except (NotFound, PolicyViolation) as error:
        raise bad_request(error)


@app.post("/api/factory/tasks/{task_id}/lease-heartbeat", dependencies=[Depends(verify_node_request)])
def lease_heartbeat(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return STORE.task_lease_heartbeat(task_id, payload.get("lease_id"))
    except (NotFound, PolicyViolation) as error:
        raise bad_request(error)


@app.post("/api/factory/tasks/{task_id}/complete", dependencies=[Depends(verify_node_request)])
def complete_factory_task(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return STORE.complete_task(task_id, payload)
    except (NotFound, PolicyViolation) as error:
        raise bad_request(error)


@app.post("/api/factory/tasks/{task_id}/fail", dependencies=[Depends(verify_node_request)])
def fail_factory_task(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return STORE.fail_task(task_id, payload)
    except (NotFound, PolicyViolation) as error:
        raise bad_request(error)


@app.get("/api/factory/tasks/{task_id}/artifacts")
def factory_task_artifacts(task_id: str, principal: SessionPrincipal = Depends(current_session)) -> list[dict[str, Any]]:
    ensure_role(principal, "operator", "server_admin", "owner")
    try:
        return STORE.task_artifacts(task_id)
    except NotFound as error:
        raise not_found(error)


@app.get("/api/factory/events")
def factory_events(principal: SessionPrincipal = Depends(current_session)) -> list[dict[str, Any]]:
    ensure_role(principal, "operator", "owner")
    return STORE.factory_events()


@app.post("/api/factory/leases/reap")
def reap_leases(principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    ensure_role(principal, "owner")
    return STORE.reap_expired_leases()


@app.get("/api/fleet/health")
def fleet_health(principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    ensure_role(principal, "operator", "server_admin", "owner")
    return STORE.fleet_health()


@app.post("/api/nodes/{node_id}/drain")
def drain_node(node_id: str, principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    ensure_role(principal, "owner")
    try:
        return STORE.set_node_mode(node_id, "DRAINING")
    except NotFound as error:
        raise not_found(error)


@app.post("/api/nodes/{node_id}/resume")
def resume_node(node_id: str, principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    ensure_role(principal, "owner")
    try:
        return STORE.set_node_mode(node_id, "CONTROLLED_WRITE")
    except NotFound as error:
        raise not_found(error)


@app.get("/api/factory/stats")
def factory_stats(principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    ensure_role(principal, "operator", "owner")
    return STORE.factory_stats()


@app.get("/api/roles")
def roles(principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    ensure_role(principal, "operator", "developer", "owner")
    return STORE.manifest["roles"]


@app.get("/api/audit/events")
def audit_events(principal: SessionPrincipal = Depends(current_session)) -> list[dict[str, Any]]:
    ensure_role(principal, "owner")
    return STORE.audit_events()


@app.get("/api/vista/release/readiness")
def release_readiness(principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    ensure_role(principal, "owner")
    required = {
        "VISTA_SESSION_SECRET": bool(os.environ.get("VISTA_SESSION_SECRET")),
        "VISTA_OWNER_ACCESS_TOKEN": bool(os.environ.get("VISTA_OWNER_ACCESS_TOKEN") or os.environ.get("VISTA_ADMIN_TOKEN")),
        "VISTA_NODE_JOIN_TOKEN": bool(os.environ.get("VISTA_NODE_JOIN_TOKEN")),
        "VISTA_NODE_SIGNING_SECRET": bool(os.environ.get("VISTA_NODE_SIGNING_SECRET")),
        "VISTA_ALLOWED_ORIGINS": bool(os.environ.get("VISTA_ALLOWED_ORIGINS")),
        "VISTA_DB_PATH": bool(os.environ.get("VISTA_DB_PATH")),
    }
    missing = [name for name, configured in required.items() if not configured]
    return {
        "product": "Vista OS",
        "version": STORE.manifest.get("version"),
        "release_candidate": "vista-os-11.1-product-release",
        "production_env_state": "green" if not missing else "needs_configuration",
        "production_missing": missing,
        "required_for_production": required,
        "verified_product_flows": [
            "session_authentication",
            "tenant_estimate_isolation",
            "estimate_crud",
            "real_pdf_xlsx_docx_generation",
            "artifact_sha256",
            "factory_event_ledger",
            "public_share_link",
            "public_document_download",
            "workspace_session_restore",
        ],
    }


@app.get("/api/vista/readiness")
def readiness(principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    ensure_role(principal, "operator", "owner")
    return STORE.readiness()


@app.get("/api/vista/verticals")
def verticals(principal: SessionPrincipal = Depends(current_session)) -> list[dict[str, Any]]:
    return STORE.manifest.get("market_verticals", [])


@app.get("/api/vista/quality/gates")
def gates(principal: SessionPrincipal = Depends(current_session)) -> list[dict[str, Any]]:
    ensure_role(principal, "owner")
    readiness = STORE.readiness()
    return [{"gate": check, "state": "green"} for check in readiness["checks"]]


@app.get("/api/developer/openai-compatibility")
def openai_compatibility(principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    ensure_role(principal, "developer", "owner")
    return {
        "mode": "transparent_upstream_gateway",
        "base_url": "/v1",
        "authentication": "Authorization: Bearer vista_sk_live_...",
        "rest": "all OpenAI /v1 REST paths, methods, multipart bodies and streaming responses are forwarded",
        "realtime": "/v1/realtime accepts Vista API key or signed session token",
        "upstream_required": ["OPENAI_API_KEY"],
        "local_model_emulation": False,
    }


@app.post("/api/developer/keys")
def create_developer_key(
    req: DeveloperKeyRequest,
    principal: SessionPrincipal = Depends(current_session),
) -> dict[str, Any]:
    ensure_role(principal, "developer", "owner")
    try:
        return STORE.create_developer_api_key(principal.session_id, req.name, req.scopes)
    except PolicyViolation as error:
        raise HTTPException(status_code=403, detail=str(error))


@app.get("/api/developer/keys")
def list_developer_keys(principal: SessionPrincipal = Depends(current_session)) -> list[dict[str, Any]]:
    ensure_role(principal, "developer", "owner")
    return STORE.list_developer_api_keys(principal.session_id)


@app.delete("/api/developer/keys/{key_id}")
def revoke_developer_key(key_id: str, principal: SessionPrincipal = Depends(current_session)) -> dict[str, Any]:
    ensure_role(principal, "developer", "owner")
    try:
        return STORE.revoke_developer_api_key(key_id, principal.session_id)
    except NotFound as error:
        raise not_found(error)


# OpenAI-compatible transparent gateway. It preserves the OpenAI REST path and
# streaming response instead of pretending to implement OpenAI model behavior.
_HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade", "content-length", "host"}


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"])
async def openai_gateway(path: str, request: Request, principal: SessionPrincipal = Depends(openai_gateway_principal)) -> Response:
    ensure_role(principal, "developer", "owner")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    if not base_url.endswith("/v1"):
        base_url += "/v1"
    upstream_url = f"{base_url}/{path}"
    if request.url.query:
        upstream_url += f"?{request.url.query}"
    body = await request.body()
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _HOP_BY_HOP and key.lower() != "authorization"
    }
    headers["Authorization"] = f"Bearer {api_key}"
    if os.environ.get("OPENAI_PROJECT"):
        headers["OpenAI-Project"] = os.environ["OPENAI_PROJECT"]
    if os.environ.get("OPENAI_ORGANIZATION"):
        headers["OpenAI-Organization"] = os.environ["OPENAI_ORGANIZATION"]
    timeout = httpx.Timeout(connect=30.0, read=None, write=300.0, pool=30.0)
    client = httpx.AsyncClient(timeout=timeout)
    try:
        upstream = await client.send(
            client.build_request(request.method, upstream_url, headers=headers, content=body),
            stream=True,
        )
    except httpx.RequestError as error:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"OpenAI upstream unavailable: {error.__class__.__name__}") from error
    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in _HOP_BY_HOP
    }

    STORE.audit(
        principal.session_id,
        "openai.proxy",
        path,
        {
            "method": request.method,
            "status": upstream.status_code,
            "request_id": upstream.headers.get("x-request-id") or upstream.headers.get("openai-request-id"),
        },
    )

    async def stream() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(stream(), status_code=upstream.status_code, headers=response_headers, media_type=upstream.headers.get("content-type"))


@app.websocket("/v1/realtime")
async def openai_realtime_gateway(websocket: WebSocket) -> None:
    authorization = websocket.headers.get("authorization")
    token = websocket.query_params.get("api_key") or websocket.query_params.get("session_token")
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        await websocket.close(code=4401)
        return
    try:
        principal = openai_gateway_principal(f"Bearer {token}")
        ensure_role(principal, "developer", "owner")
    except HTTPException:
        await websocket.close(code=4403)
        return
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        await websocket.close(code=4503)
        return
    try:
        import websockets
    except ImportError:
        await websocket.close(code=4511)
        return
    upstream = os.environ.get("OPENAI_REALTIME_URL", "wss://api.openai.com/v1/realtime")
    forwarded_query = [
        (key, value)
        for key, value in websocket.query_params.multi_items()
        if key not in {"api_key", "session_token"}
    ]
    if forwarded_query:
        upstream += "?" + urlencode(forwarded_query)
    realtime_headers = {"Authorization": f"Bearer {api_key}", "OpenAI-Beta": "realtime=v1"}
    if os.environ.get("OPENAI_PROJECT"):
        realtime_headers["OpenAI-Project"] = os.environ["OPENAI_PROJECT"]
    if os.environ.get("OPENAI_ORGANIZATION"):
        realtime_headers["OpenAI-Organization"] = os.environ["OPENAI_ORGANIZATION"]
    await websocket.accept()
    STORE.audit(principal.session_id, "openai.realtime.connect", "realtime", {"query": [key for key, _ in forwarded_query]})
    try:
        async with websockets.connect(upstream, additional_headers=realtime_headers) as remote:
            async def client_to_remote() -> None:
                while True:
                    message = await websocket.receive_text()
                    await remote.send(message)

            async def remote_to_client() -> None:
                async for message in remote:
                    await websocket.send_text(message)

            await asyncio.gather(client_to_remote(), remote_to_client())
    except (WebSocketDisconnect, asyncio.CancelledError):
        return
