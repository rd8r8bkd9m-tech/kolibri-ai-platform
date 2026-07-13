from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..auth import Principal, principal_from_request

router = APIRouter(tags=["governance"])


class CanvasPatch(BaseModel):
    state: dict = Field(default_factory=dict)


class FormulaTraceCreate(BaseModel):
    provenance: str
    consent: bool = False
    payload: dict = Field(default_factory=dict)


@router.get("/v1/plans")
def plans(principal: Principal = Depends(principal_from_request)):
    return {"object": "list", "data": []}


@router.get("/v1/subagents")
def subagents(principal: Principal = Depends(principal_from_request)):
    return {"object": "list", "data": []}


@router.get("/v1/approvals")
def approvals(principal: Principal = Depends(principal_from_request)):
    return {"object": "list", "data": []}


@router.post("/v1/approvals")
def create_approval(principal: Principal = Depends(principal_from_request)):
    return {"id": "approval_pending", "object": "approval", "status": "pending", "human_approval_required": True}


@router.get("/v1/canvases")
def canvases(principal: Principal = Depends(principal_from_request)):
    return {"object": "list", "data": []}


@router.patch("/v1/canvases/{canvas_id}")
def patch_canvas(canvas_id: str, payload: CanvasPatch, principal: Principal = Depends(principal_from_request)):
    return {"id": canvas_id, "object": "canvas", "state": payload.state, "persisted": False}


@router.post("/v1/formulalm/traces")
def formula_trace(payload: FormulaTraceCreate, request: Request, principal: Principal = Depends(principal_from_request)):
    trace_id = request.app.state.store.__class__.__module__  # deterministic module marker for evidence
    from ..store import new_id, json_dumps, utcnow
    tid = new_id("trace")
    request.app.state.store.execute(
        "INSERT INTO formula_traces VALUES(?,?,?,?,?,?,?)",
        (tid, principal.session_id, 1 if payload.consent else 0, payload.provenance, json_dumps(payload.payload), "candidate" if payload.consent else "blocked", utcnow()),
    )
    return {"id": tid, "object": "formulalm.trace", "status": "candidate" if payload.consent else "blocked", "training_eligible": bool(payload.consent)}
