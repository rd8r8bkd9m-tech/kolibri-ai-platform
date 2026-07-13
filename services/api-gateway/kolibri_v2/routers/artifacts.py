from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from ..auth import Principal, principal_from_request
from ..errors import APIError

router = APIRouter(tags=["artifacts"])


@router.get("/v1/artifacts")
def list_artifacts(request: Request, project_id: str | None = None, estimate_id: str | None = None, principal: Principal = Depends(principal_from_request)):
    return {"object": "list", "data": request.app.state.store.list_artifacts(principal.session_id, project_id, estimate_id)}


@router.get("/v1/artifacts/{artifact_id}")
def get_artifact(artifact_id: str, request: Request, principal: Principal = Depends(principal_from_request)):
    artifact = request.app.state.store.get_artifact(artifact_id, principal.session_id)
    if not artifact:
        raise APIError("Artifact not found.", 404, code="artifact_not_found")
    return artifact


@router.get("/v1/artifacts/{artifact_id}/content")
def artifact_content(artifact_id: str, request: Request, principal: Principal = Depends(principal_from_request)):
    artifact = request.app.state.store.get_artifact(artifact_id, principal.session_id)
    if not artifact:
        raise APIError("Artifact not found.", 404, code="artifact_not_found")
    path = Path(artifact["storage_path"])
    if not path.exists() or path.stat().st_size != int(artifact["size"]):
        raise APIError("Artifact bytes are unavailable.", 503, "server_error", code="artifact_unavailable")
    return FileResponse(path, media_type=artifact["mime_type"], filename=artifact["name"], headers={"ETag": artifact["sha256"]})
