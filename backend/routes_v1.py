from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from factory_status import fetch_factory_status

router = APIRouter()

KOLIBRI_SYSTEM_PROMPT = (
    "Ты — Kolibri AI, большая языковая модель. " +
    "Отвечай на языке пользователя. Не используй эмодзи."
)

@router.get("/api/v1/ai/models")
async def get_models():
    return {"models": [{"name": "kolibri", "description": "Kolibri AI"}], "system_prompt": KOLIBRI_SYSTEM_PROMPT}

@router.get("/api/v1/model/stats")
async def get_model_stats():
    return {"status": "ok", "models": ["kolibri"], "active": "kolibri"}

@router.post("/api/v1/ai/chat")
async def chat(request: Request):
    from providers import AIProviderManager
    manager = AIProviderManager()
    body = await request.json()
    messages = body.get("messages", [])
    result = await manager.generate(messages=messages, model="kolibri")
    return result

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
    try:
        snapshot = await fetch_factory_status()
    except Exception:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "source": "control-plane/home",
                "reason": "canonical_home_control_plane_unavailable",
            },
        )
    return {
        "status": snapshot.get("status", "degraded"),
        "source": "control-plane/home",
        "nodes": snapshot.get("total_nodes", 0),
        "online_nodes": snapshot.get("online_nodes", 0),
        "fresh_nodes": snapshot.get("fresh_nodes", 0),
        "degraded_nodes": snapshot.get("degraded_nodes", 0),
        "stale_nodes": snapshot.get("stale_nodes", 0),
        "queue_size": snapshot.get("queue_size", 0),
    }

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
