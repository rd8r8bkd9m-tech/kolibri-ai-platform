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
