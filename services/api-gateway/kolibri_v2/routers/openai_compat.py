from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, StreamingResponse

from ..auth import Principal, principal_from_request, require_roles
from ..errors import APIError

router = APIRouter(tags=["openai-compatibility"])

SUPPORTED_PREFIXES = {
    "audio", "videos", "images", "embeddings", "evals", "fine_tuning", "graders",
    "batches", "files", "uploads", "moderations", "vector_stores", "chatkit",
    "containers", "skills", "assistants", "threads", "completions", "organization",
    "realtime", "webhooks",
}


def _base_url(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.rstrip("/")
    return value if value.endswith("/v1") else value + "/v1"


@router.api_route(
    "/v1/{resource_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def proxy_openai(resource_path: str, request: Request, principal: Principal = Depends(principal_from_request)):
    prefix = resource_path.split("/", 1)[0]
    if prefix not in SUPPORTED_PREFIXES:
        raise APIError(f"The resource '/v1/{resource_path}' does not exist.", 404, "invalid_request_error", code="resource_not_found")
    if prefix == "organization":
        require_roles(principal, "owner")
    else:
        require_roles(principal, "developer", "owner")
    settings = request.app.state.settings
    base = _base_url(settings.openai_base_url)
    if not base or not settings.openai_api_key:
        raise APIError(
            f"The OpenAI-compatible resource '/v1/{resource_path}' is not configured on this deployment.",
            503,
            "server_error",
            code="upstream_not_configured",
        )
    body = await request.body()
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": request.headers.get("content-type", "application/json"),
        "Accept": request.headers.get("accept", "*/*"),
    }
    for name in ["idempotency-key", "openai-beta"]:
        if request.headers.get(name):
            headers[name] = request.headers[name]
    if settings.openai_organization:
        headers["OpenAI-Organization"] = settings.openai_organization
    if settings.openai_project:
        headers["OpenAI-Project"] = settings.openai_project
    url = f"{base}/{resource_path}"
    client = httpx.AsyncClient(timeout=None)
    upstream = await client.send(
        client.build_request(request.method, url, params=request.query_params, headers=headers, content=body),
        stream=True,
    )
    response_headers = {
        name: value
        for name, value in upstream.headers.items()
        if name.lower() in {"content-type", "content-disposition"}
    }
    upstream_request_id = upstream.headers.get("openai-request-id") or upstream.headers.get("x-request-id")
    if upstream_request_id:
        response_headers["OpenAI-Request-ID"] = upstream_request_id
        response_headers["X-Upstream-Request-ID"] = upstream_request_id
    if "text/event-stream" in upstream.headers.get("content-type", "") or request.headers.get("accept") == "text/event-stream":
        async def iterator():
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                await upstream.aclose(); await client.aclose()
        return StreamingResponse(iterator(), status_code=upstream.status_code, headers=response_headers, media_type=upstream.headers.get("content-type"))
    data = await upstream.aread(); await upstream.aclose(); await client.aclose()
    return Response(data, status_code=upstream.status_code, headers=response_headers, media_type=upstream.headers.get("content-type"))
