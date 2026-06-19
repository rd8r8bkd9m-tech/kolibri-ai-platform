from fastapi import APIRouter, Request, Depends
from fastapi.responses import StreamingResponse
import json

from auth import get_current_user_optional
from providers import manager

router = APIRouter()

KOLIBRI_SYSTEM_PROMPT = (
    "Ты — Kolibri AI, большая языковая модель. "
    "Отвечай на языке пользователя. Не используй эмодзи."
)

@router.get("/api/v1/ai/models")
async def get_models(user: dict = Depends(get_current_user_optional)):
    return {"models": manager.get_model_catalog(), "system_prompt": KOLIBRI_SYSTEM_PROMPT}

@router.get("/api/v1/model/stats")
async def get_model_stats(user: dict = Depends(get_current_user_optional)):
    catalog = manager.get_model_catalog()
    return {"status": "ok", "models": [m["name"] for m in catalog], "active": catalog[0]["name"] if catalog else "none"}

@router.post("/api/v1/ai/chat")
async def chat(request: Request, user: dict = Depends(get_current_user_optional)):
    try:
        body = await request.json()
    except Exception:
        return {"error": "Invalid JSON"}
    messages = body.get("messages", [])
    if not messages:
        return {"error": "No messages"}
    model = body.get("model", "auto")
    provider = body.get("provider")
    result = await manager.generate(messages=messages, model=model, provider=provider)
    return result

@router.post("/api/v1/ai/chat/stream")
async def chat_stream(request: Request, user: dict = Depends(get_current_user_optional)):
    try:
        body = await request.json()
    except Exception:
        return StreamingResponse(iter(['data: {"error": "Invalid JSON"}\n\n', "data: [DONE]\n\n"]), media_type="text/event-stream")
    messages = body.get("messages", [])
    if not messages:
        return StreamingResponse(iter(['data: {"error": "No messages"}\n\n', "data: [DONE]\n\n"]), media_type="text/event-stream")
    model = body.get("model", "auto")
    provider = body.get("provider")

    async def generate():
        try:
            async for chunk in manager.generate_stream(messages=messages, model=model, provider=provider):
                yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f'data: {{"error": "{e}"}}\n\n'
            yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")

@router.post("/api/v1/ai/imagine")
async def imagine(user: dict = Depends(get_current_user_optional)):
    return {"status": "ok", "message": "Image generation coming soon"}

@router.post("/api/v1/ai/vision/analyze")
async def vision(user: dict = Depends(get_current_user_optional)):
    return {"status": "ok", "message": "Vision analysis coming soon"}

@router.post("/api/v1/ai/demo/learn/text")
async def learn(user: dict = Depends(get_current_user_optional)):
    return {"status": "ok", "message": "Learning coming soon"}

@router.get("/api/v1/ai/quality/benchmark/history")
async def benchmark(user: dict = Depends(get_current_user_optional)):
    return {"history": []}

@router.get("/api/v1/swarm/runtime/status")
async def swarm_status(user: dict = Depends(get_current_user_optional)):
    return {"status": "active", "nodes": 4}

@router.get("/api/v1/ai/training/queue/status")
async def training_status(user: dict = Depends(get_current_user_optional)):
    return {"queue": []}

@router.post("/api/v1/swarm/runtime/start")
async def swarm_start(user: dict = Depends(get_current_user_optional)):
    return {"status": "started"}

@router.post("/api/v1/swarm/runtime/refresh")
async def swarm_refresh(user: dict = Depends(get_current_user_optional)):
    return {"status": "refreshed"}

@router.post("/api/v1/swarm/runtime/run")
async def swarm_run(user: dict = Depends(get_current_user_optional)):
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/ingest/text")
async def ingest_text(user: dict = Depends(get_current_user_optional)):
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/ingest/url")
async def ingest_url(user: dict = Depends(get_current_user_optional)):
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/kpack/export")
async def kpack_export(user: dict = Depends(get_current_user_optional)):
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/kpack/import")
async def kpack_import(user: dict = Depends(get_current_user_optional)):
    return {"status": "ok"}
