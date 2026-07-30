"""Private, fail-closed DeepSeek compatibility proxy.

This router is not mounted by the public Kolibri application.  Deployments
that mount it in a separate, server-side process must opt in explicitly and
authenticate every request with a dedicated internal bearer token.  The
provider credential is read only on the server and is never accepted from or
returned to callers.
"""

from __future__ import annotations

import hmac
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response


router = APIRouter(prefix="/deepseek", tags=["deepseek-private-proxy"])

_DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
_ALLOWED_PATHS = frozenset({"chat/completions", "models"})
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _proxy_enabled() -> bool:
    return os.getenv("KOLIBRI_DEEPSEEK_PROXY_ENABLED", "").strip().lower() in _TRUTHY


def _require_private_proxy_auth(request: Request) -> None:
    """Deny before touching provider configuration or making an outbound call."""

    if not _proxy_enabled():
        # A disabled private surface is intentionally indistinguishable from
        # an unmounted route.
        raise HTTPException(status_code=404, detail={"code": "not_found"})

    expected = os.getenv("KOLIBRI_DEEPSEEK_PROXY_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail={"code": "deepseek_proxy_auth_not_configured"},
        )

    authorization = request.headers.get("authorization", "")
    scheme, separator, supplied = authorization.partition(" ")
    if (
        separator != " "
        or scheme.lower() != "bearer"
        or not supplied
        or not hmac.compare_digest(supplied.encode(), expected.encode())
    ):
        raise HTTPException(
            status_code=401,
            detail={"code": "deepseek_proxy_unauthorized"},
            headers={"WWW-Authenticate": "Bearer"},
        )


async def _request_upstream(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    content: bytes,
) -> httpx.Response:
    timeout = httpx.Timeout(120.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        return await client.request(
            method=method,
            url=url,
            headers=headers,
            content=content,
        )


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST"],
    dependencies=[Depends(_require_private_proxy_auth)],
)
async def proxy(path: str, request: Request) -> Response:
    normalized_path = path.strip("/")
    if normalized_path not in _ALLOWED_PATHS:
        raise HTTPException(status_code=404, detail={"code": "not_found"})

    provider_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not provider_key:
        raise HTTPException(
            status_code=503,
            detail={"code": "deepseek_provider_not_configured"},
        )

    base_url = os.getenv("DEEPSEEK_BASE_URL", _DEFAULT_DEEPSEEK_BASE_URL).rstrip("/")
    query = request.url.query
    upstream_url = f"{base_url}/{normalized_path}"
    if query:
        upstream_url = f"{upstream_url}?{query}"

    upstream = await _request_upstream(
        method=request.method,
        url=upstream_url,
        headers={
            "Authorization": f"Bearer {provider_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        content=await request.body(),
    )
    response_headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json").split(
            ";", 1
        )[0],
        headers=response_headers,
    )
