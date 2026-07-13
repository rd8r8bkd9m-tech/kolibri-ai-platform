from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from ..auth import Principal, principal_from_request
from ..documents import render_docx, render_json, render_markdown, render_pdf, render_xlsx
from ..errors import APIError
from ..estimates import calculate

router = APIRouter(tags=["estimates"])


class EstimateCreate(BaseModel):
    project_id: str
    title: str = Field(default="Смета проекта", min_length=1, max_length=180)
    client_name: str = ""
    region: str = ""


class EstimatePatch(BaseModel):
    title: str | None = None
    client_name: str | None = None
    region: str | None = None
    overhead_pct: str | float | None = None
    margin_pct: str | float | None = None
    discount_pct: str | float | None = None
    tax_pct: str | float | None = None


class ItemCreate(BaseModel):
    section: str = "Работы"
    name: str = Field(min_length=1)
    unit: str = "шт."
    quantity: str | float = "0"
    unit_price: str | float = "0"
    coefficient: str | float = "1"
    source_id: str | None = None
    position: int = 0


class ItemPatch(BaseModel):
    section: str | None = None
    name: str | None = None
    unit: str | None = None
    quantity: str | float | None = None
    unit_price: str | float | None = None
    coefficient: str | float | None = None
    source_id: str | None = None
    position: int | None = None


class SourceCreate(BaseModel):
    title: str
    url: str
    region: str
    price_date: str
    unit: str
    verification_status: str = "unverified"


class ExportRequest(BaseModel):
    formats: list[str] = Field(default_factory=lambda: ["pdf", "xlsx"])


def _owned(request: Request, estimate_id: str, principal: Principal) -> dict[str, Any]:
    estimate = request.app.state.store.get_estimate(estimate_id, principal.session_id)
    if not estimate:
        raise APIError("Estimate not found.", 404, code="estimate_not_found")
    return calculate(estimate)


def _recalculate(request: Request, estimate_id: str, session_id: str, create_revision: bool = False) -> dict[str, Any]:
    estimate = request.app.state.store.get_estimate(estimate_id, session_id)
    if not estimate:
        raise APIError("Estimate not found.", 404, code="estimate_not_found")
    result = calculate(estimate)
    request.app.state.store.set_estimate_totals(estimate_id, result["status"], result["subtotal"], result["total"])
    if create_revision:
        request.app.state.store.save_revision(estimate_id)
    return calculate(request.app.state.store.get_estimate(estimate_id, session_id) or result)


@router.get("/v1/estimates")
def list_estimates(request: Request, project_id: str | None = None, principal: Principal = Depends(principal_from_request)):
    return {"object": "list", "data": [calculate(e) for e in request.app.state.store.list_estimates(principal.session_id, project_id)]}


@router.post("/v1/estimates")
def create_estimate(payload: EstimateCreate, request: Request, principal: Principal = Depends(principal_from_request)):
    if not request.app.state.store.get_project(payload.project_id, principal.session_id):
        raise APIError("Project not found.", 404, "invalid_request_error", "project_id", "project_not_found")
    return calculate(request.app.state.store.create_estimate(principal.session_id, payload.project_id, payload.title, payload.client_name, payload.region))


@router.get("/v1/estimates/{estimate_id}")
def get_estimate(estimate_id: str, request: Request, principal: Principal = Depends(principal_from_request)):
    return _owned(request, estimate_id, principal)


@router.patch("/v1/estimates/{estimate_id}")
def patch_estimate(
    estimate_id: str,
    payload: EstimatePatch,
    request: Request,
    if_match: str | None = Header(default=None, alias="If-Match"),
    principal: Principal = Depends(principal_from_request),
):
    current = _owned(request, estimate_id, principal)
    if if_match is not None and if_match.strip('"') != str(current["revision"]):
        raise APIError("The estimate has changed. Reload the latest revision.", 409, "conflict_error", "If-Match", "revision_conflict")
    request.app.state.store.update_estimate_fields(estimate_id, principal.session_id, payload.model_dump(exclude_none=True))
    return _recalculate(request, estimate_id, principal.session_id, create_revision=True)


@router.post("/v1/estimates/{estimate_id}/items")
def add_item(estimate_id: str, payload: ItemCreate, request: Request, principal: Principal = Depends(principal_from_request)):
    _owned(request, estimate_id, principal)
    request.app.state.store.add_estimate_item(estimate_id, payload.model_dump())
    return _recalculate(request, estimate_id, principal.session_id, create_revision=True)


@router.patch("/v1/estimates/{estimate_id}/items/{item_id}")
def patch_item(estimate_id: str, item_id: str, payload: ItemPatch, request: Request, principal: Principal = Depends(principal_from_request)):
    _owned(request, estimate_id, principal)
    item = request.app.state.store.update_estimate_item(estimate_id, item_id, payload.model_dump(exclude_none=True))
    if not item:
        raise APIError("Estimate item not found.", 404, code="estimate_item_not_found")
    return _recalculate(request, estimate_id, principal.session_id, create_revision=True)


@router.delete("/v1/estimates/{estimate_id}/items/{item_id}")
def delete_item(estimate_id: str, item_id: str, request: Request, principal: Principal = Depends(principal_from_request)):
    _owned(request, estimate_id, principal)
    request.app.state.store.delete_estimate_item(estimate_id, item_id)
    return _recalculate(request, estimate_id, principal.session_id, create_revision=True)


@router.post("/v1/estimates/{estimate_id}/sources")
def add_source(estimate_id: str, payload: SourceCreate, request: Request, principal: Principal = Depends(principal_from_request)):
    _owned(request, estimate_id, principal)
    if payload.verification_status not in {"unverified", "verified", "rejected"}:
        raise APIError("Invalid source verification status.", 400, "invalid_request_error", "verification_status", "invalid_status")
    source = request.app.state.store.add_source(estimate_id, payload.model_dump())
    return {"source": source, "estimate": _recalculate(request, estimate_id, principal.session_id, create_revision=True)}


@router.get("/v1/estimates/{estimate_id}/revisions")
def revisions(estimate_id: str, request: Request, principal: Principal = Depends(principal_from_request)):
    _owned(request, estimate_id, principal)
    return {"object": "list", "data": request.app.state.store.list_revisions(estimate_id)}


@router.post("/v1/estimates/{estimate_id}/revisions")
def create_revision(estimate_id: str, request: Request, principal: Principal = Depends(principal_from_request)):
    _owned(request, estimate_id, principal)
    return request.app.state.store.save_revision(estimate_id)


@router.post("/v1/estimates/{estimate_id}/exports")
def export_estimate(estimate_id: str, payload: ExportRequest, request: Request, principal: Principal = Depends(principal_from_request)):
    estimate = _recalculate(request, estimate_id, principal.session_id, create_revision=True)
    revision = int(estimate["revision"])
    renderers = {
        "pdf": ("Коммерческое предложение.pdf", "application/pdf", render_pdf),
        "xlsx": ("Смета.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", render_xlsx),
        "docx": ("Коммерческое предложение.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", render_docx),
        "json": ("Смета.json", "application/json", render_json),
        "md": ("Допущения.md", "text/markdown; charset=utf-8", render_markdown),
    }
    artifacts = []
    for fmt in payload.formats:
        if fmt not in renderers:
            raise APIError(f"Unsupported export format: {fmt}", 400, "invalid_request_error", "formats", "unsupported_format")
        name, mime, renderer = renderers[fmt]
        data = renderer(estimate)
        if not data:
            raise APIError(f"The {fmt} renderer returned no bytes.", 500, "server_error", code="empty_artifact")
        artifact = request.app.state.artifacts.materialize(
            session_id=principal.session_id,
            project_id=estimate["project_id"],
            estimate_id=estimate_id,
            revision=revision,
            name=name,
            mime_type=mime,
            data=data,
        )
        artifacts.append(artifact)
    return {"object": "estimate.export", "estimate_id": estimate_id, "revision": revision, "artifacts": artifacts}


@router.get("/v1/estimates/{estimate_id}/artifacts")
def estimate_artifacts(estimate_id: str, request: Request, principal: Principal = Depends(principal_from_request)):
    _owned(request, estimate_id, principal)
    return {"object": "list", "data": request.app.state.store.list_artifacts(principal.session_id, estimate_id=estimate_id)}
