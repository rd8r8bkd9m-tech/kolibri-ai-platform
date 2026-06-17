from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
import json

router = APIRouter()

KOLIBRI_SYSTEM_PROMPT = (
    "Ты — Kolibri AI, большая языковая модель. " +
    "Отвечай на языке пользователя. Не используй эмодзи."
)

@router.get("/api/v1/ai/models")
async def get_models():
    return {"models": [{"name": "mimo-auto", "description": "Auto mode"}], "system_prompt": KOLIBRI_SYSTEM_PROMPT}

@router.get("/api/v1/model/stats")
async def get_model_stats():
    return {"status": "ok", "models": ["mimo-auto"], "active": "mimo-auto"}

@router.post("/api/v1/ai/chat")
async def chat(request: Request):
    from providers import AIProviderManager
    manager = AIProviderManager()
    body = await request.json()
    messages = body.get("messages", [])
    result = await manager.generate(messages=messages, provider="mimo")
    return result

@router.post("/api/v1/ai/chat/stream")
async def chat_stream(request: Request):
    from providers import AIProviderManager
    manager = AIProviderManager()
    body = await request.json()
    messages = body.get("messages", [])
    result = await manager.generate(messages=messages, provider="mimo")
    async def generate():
        yield f"data: {json.dumps(result)}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")

@router.post("/api/v1/ai/imagine")
async def imagine():
    return {"status": "ok", "message": "Image generation coming soon"}

@router.post("/api/v1/ai/vision/analyze")
async def vision():
    return {"status": "ok", "message": "Vision analysis coming soon"}

@router.post("/api/v1/ai/demo/learn/text")
async def learn():
    return {"status": "ok", "message": "Learning coming soon"}

@router.get("/api/v1/ai/quality/benchmark/history")
async def benchmark():
    return {"history": []}

@router.get("/api/v1/swarm/runtime/status")
async def swarm_status():
    return {"status": "active", "nodes": 4}

@router.get("/api/v1/ai/training/queue/status")
async def training_status():
    return {"queue": []}

@router.post("/api/v1/swarm/runtime/start")
async def swarm_start():
    return {"status": "started"}

@router.post("/api/v1/swarm/runtime/refresh")
async def swarm_refresh():
    return {"status": "refreshed"}

@router.post("/api/v1/swarm/runtime/run")
async def swarm_run():
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/ingest/text")
async def ingest_text():
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/ingest/url")
async def ingest_url():
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/kpack/export")
async def kpack_export():
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/kpack/import")
async def kpack_import():
    return {"status": "ok"}
