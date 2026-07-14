"""Loopback-only Codex image worker.

The public backend keeps ``NoNewPrivileges=true``.  Codex's own Linux sandbox
needs to create its isolated namespace, so image generation runs in this
separate localhost service with a minimal API and a dedicated systemd policy.
It returns real raster bytes only after the existing strict verifier passes.
"""

from __future__ import annotations

import base64
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.codex_cli_image_provider import (
    CodexCLIImageError,
    codex_cli_image_configuration,
    edit_codex_cli_image,
    generate_codex_cli_image,
)


app = FastAPI(title="Kolibri Codex Image Worker", docs_url=None, redoc_url=None)


class WorkerImageRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=8_000)
    size: Literal["1024x1024", "1024x1536", "1536x1024"] = "1024x1024"
    quality: Literal["low", "medium", "high"] = "high"
    run_id: str | None = Field(default=None, max_length=200)


class WorkerImageEditRequest(WorkerImageRequest):
    source_b64: str = Field(min_length=16, max_length=40_000_000)


@app.get("/health")
async def health() -> dict[str, object]:
    snapshot = codex_cli_image_configuration()
    return {
        "status": "ok" if snapshot.get("configured") else "unavailable",
        "provider": "codex_cli",
        "configured": bool(snapshot.get("configured")),
    }


@app.post("/v1/images/generations")
async def create_image(request: WorkerImageRequest) -> dict[str, object]:
    try:
        result = await generate_codex_cli_image(
            request.prompt,
            size=request.size,
            quality=request.quality,
            run_id=request.run_id,
        )
    except CodexCLIImageError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": getattr(exc, "failure_kind", "codex_cli_image_failed")},
        ) from exc
    return {
        "created": 1,
        "model": result.model,
        "data": [{"b64_json": base64.b64encode(result.data).decode("ascii")}],
    }


@app.post("/v1/images/edits")
async def edit_image(request: WorkerImageEditRequest) -> dict[str, object]:
    try:
        source = base64.b64decode(request.source_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "source_image_invalid_base64"},
        ) from exc
    try:
        result = await edit_codex_cli_image(
            request.prompt,
            source,
            size=request.size,
            quality=request.quality,
            run_id=request.run_id,
        )
    except CodexCLIImageError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": getattr(exc, "failure_kind", "codex_cli_image_failed")},
        ) from exc
    return {
        "created": 1,
        "model": result.model,
        "data": [{"b64_json": base64.b64encode(result.data).decode("ascii")}],
    }
