"""Session-scoped read API for editable estimates and immutable PDFs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from estimate_artifacts import EstimateArtifactError, get_estimate_artifact_store
from public_responses_api import require_public_response_session


router = APIRouter(tags=["Kolibri Public Estimate Artifacts V1"])


@router.get("/v1/public/estimates/{estimate_id}")
def get_public_estimate(estimate_id: str, request: Request):
    session = require_public_response_session(request)
    estimate = get_estimate_artifact_store().get_estimate(session["id"], estimate_id)
    if estimate is None:
        raise HTTPException(status_code=404, detail="estimate_not_found")
    return estimate


@router.get("/v1/public/estimates/{estimate_id}/versions")
def list_public_estimate_versions(estimate_id: str, request: Request):
    session = require_public_response_session(request)
    versions = get_estimate_artifact_store().list_versions(session["id"], estimate_id)
    if versions is None:
        raise HTTPException(status_code=404, detail="estimate_not_found")
    return {
        "object": "list",
        "data": versions,
        "has_more": False,
    }


@router.get("/v1/public/estimate-artifacts/{artifact_id}/content")
def get_public_estimate_artifact(
    artifact_id: str,
    request: Request,
    download: bool = False,
):
    session = require_public_response_session(request)
    try:
        resolved = get_estimate_artifact_store().artifact_content(session["id"], artifact_id)
    except EstimateArtifactError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    if resolved is None:
        raise HTTPException(status_code=404, detail="estimate_artifact_not_found")
    artifact, content = resolved
    disposition = "attachment" if download else "inline"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "Cross-Origin-Resource-Policy": "same-origin",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "SAMEORIGIN",
            "Content-Security-Policy": "frame-ancestors 'self'",
            "X-Content-SHA256": artifact["content_sha256"],
            "X-Kolibri-Artifact-Binding": artifact["evidence_binding_sha256"],
            "Content-Disposition": f'{disposition}; filename="{artifact["name"]}"',
        },
    )
