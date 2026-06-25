from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from directive_compiler import DEFAULT_ROOT, DirectiveStore


def store() -> DirectiveStore:
    root = Path(os.environ.get("KOLIBRI_FACTORY_ROOT", str(DEFAULT_ROOT)))
    return DirectiveStore(root=root)


app = FastAPI(title="Kolibri Directive Compiler", version="0.1.0")


class DirectiveCreate(BaseModel):
    raw_text: str
    source: str = "api"
    owner_id: str = "project-owner"
    directive_id: str | None = None


class SupersedeRequest(BaseModel):
    replacement_id: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "kolibri-directive-compiler"}


@app.post("/v1/directives")
def create_directive(payload: DirectiveCreate) -> dict:
    try:
        meta = store().submit_directive(payload.raw_text, payload.source, payload.owner_id, payload.directive_id)
        return {"status": "accepted", "directive": meta}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/v1/directives")
def list_directives() -> dict:
    return {"directives": store().list_directives()}


@app.get("/v1/directives/{directive_id}")
def get_directive(directive_id: str) -> dict:
    try:
        return store().get_directive(directive_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="directive not found") from exc


@app.post("/v1/directives/{directive_id}/compile")
def compile_directive(directive_id: str) -> dict:
    try:
        return store().compile_directive(directive_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="directive not found") from exc


@app.post("/v1/directives/{directive_id}/activate")
def activate_directive(directive_id: str) -> dict:
    try:
        return store().activate_directive(directive_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="directive not found") from exc


@app.post("/v1/directives/{directive_id}/pause")
def pause_directive(directive_id: str) -> dict:
    try:
        return store().pause_directive(directive_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="directive not found") from exc


@app.post("/v1/directives/{directive_id}/supersede")
def supersede_directive(directive_id: str, payload: SupersedeRequest) -> dict:
    try:
        return store().supersede_directive(directive_id, payload.replacement_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="directive not found") from exc


@app.get("/v1/directives/{directive_id}/evidence")
def directive_evidence(directive_id: str) -> dict:
    try:
        return store().evidence(directive_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="directive not found") from exc
