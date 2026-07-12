"""Session-scoped delivery for verified public image artifacts."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from image_artifacts import ImageArtifactError, get_public_image_artifact_store
from public_responses_api import require_public_response_session


router = APIRouter(tags=["Kolibri Public Image Artifacts V1"])


@router.get("/v1/public/artifacts/{artifact_id}/content")
def get_public_image_artifact(
    artifact_id: str,
    request: Request,
    download: bool = False,
):
    session = require_public_response_session(request)
    try:
        resolved = get_public_image_artifact_store().content(session["id"], artifact_id)
    except ImageArtifactError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    if resolved is None:
        raise HTTPException(status_code=404, detail="image_artifact_not_found")
    artifact, content = resolved
    disposition = "attachment" if download else "inline"
    name = str(artifact.get("name") or "kolibri-image")
    return Response(
        content=content,
        media_type=artifact["media_type"],
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "Cross-Origin-Resource-Policy": "same-origin",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'self'",
            "X-Content-SHA256": artifact["content_sha256"],
            "X-Kolibri-Artifact-Binding": artifact["evidence_binding_sha256"],
            "Content-Disposition": (
                f'{disposition}; filename="kolibri-image"; '
                f"filename*=UTF-8''{quote(name, safe='')}"
            ),
        },
    )
