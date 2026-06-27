"""DeepSeek local proxy — forwards to api.deepseek.com with key injection."""
import os
import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/deepseek", tags=["deepseek-proxy"])

DEEPSEEK_BASE = "https://api.deepseek.com"
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(path: str, request: Request):
    if not DEEPSEEK_KEY:
        return Response(content='{"error":"No DEEPSEEK_API_KEY configured"}', status_code=500, media_type="application/json")

    url = f"{DEEPSEEK_BASE}/{path}"
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    body = await request.body()

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.request(method=request.method, url=url, headers=headers, content=body)

    return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type", "application/json"))


@router.get("/models")
async def models():
    if not DEEPSEEK_KEY:
        return {"error": "No DEEPSEEK_API_KEY"}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{DEEPSEEK_BASE}/models", headers={"Authorization": f"Bearer {DEEPSEEK_KEY}"})
    return resp.json()
