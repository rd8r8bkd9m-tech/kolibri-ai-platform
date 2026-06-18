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
    from providers import manager
    return {"models": manager.get_model_catalog(), "system_prompt": KOLIBRI_SYSTEM_PROMPT}

@router.get("/api/v1/model/stats")
async def get_model_stats():
    from providers import manager
    catalog = manager.get_model_catalog()
    return {"status": "ok", "models": [m["name"] for m in catalog], "active": catalog[0]["name"] if catalog else "none"}

@router.post("/api/v1/ai/chat")
async def chat(request: Request):
    from providers import manager
    body = await request.json()
    messages = body.get("messages", [])
    model = body.get("model", "auto")
    provider = body.get("provider")
    result = await manager.generate(messages=messages, model=model, provider=provider)
    return result

@router.post("/api/v1/ai/chat/stream")
async def chat_stream(request: Request):
    from providers import manager
    body = await request.json()
    messages = body.get("messages", [])
    model = body.get("model", "auto")
    provider = body.get("provider")

    async def generate():
        async for chunk in manager.generate_stream(messages=messages, model=model, provider=provider):
            yield f"data: {json.dumps(chunk)}\n\n"
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
