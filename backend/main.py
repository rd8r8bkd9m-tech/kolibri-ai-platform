from routes_v1 import router as v1_router
import os
import time
import json
import hashlib
import sqlite3
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from providers import AIProviderManager
from tts import TTSEngine
from stt import STTEngine
from websearch import WebSearchEngine
from factory_status import fetch_factory_status

DATA_DIR = Path(os.environ.get("KOLIBRI_DATA_DIR") or (Path(__file__).resolve().parents[1] / "data"))
DB_PATH = DATA_DIR / "kolibri.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS cache (
        key TEXT PRIMARY KEY,
        response TEXT,
        provider TEXT,
        created_at REAL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        title TEXT,
        created_at REAL,
        updated_at REAL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT,
        role TEXT,
        content TEXT,
        provider TEXT,
        created_at REAL,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS rate_limits (
        ip TEXT,
        timestamp REAL,
        PRIMARY KEY (ip, timestamp)
    )""")
    conn.commit()
    conn.close()

init_db()

ai_manager = AIProviderManager()
tts_engine = TTSEngine()
stt_engine = STTEngine()
web_engine = WebSearchEngine()

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048
    system_prompt: Optional[str] = None
    enable_thinking: Optional[bool] = False

class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = "en-US-AriaNeural"

class STTRequest(BaseModel):
    pass

class SearchRequest(BaseModel):
    query: str
    num_results: Optional[int] = 5

class ToolCallRequest(BaseModel):
    message: str
    tools: Optional[List[Dict[str, Any]]] = None

def get_cache_key(messages: list, model: str) -> str:
    content = json.dumps([{"role": m.role, "content": m.content} for m in messages], sort_keys=True)
    return hashlib.sha256(f"{model}:{content}".encode()).hexdigest()

def check_rate_limit(ip: str, limit: int = 60, window: int = 60) -> bool:
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    now = time.time()
    c.execute("DELETE FROM rate_limits WHERE timestamp < ?", (now - window,))
    c.execute("SELECT COUNT(*) FROM rate_limits WHERE ip = ?", (ip,))
    count = c.fetchone()[0]
    if count >= limit:
        conn.close()
        return False
    c.execute("INSERT INTO rate_limits (ip, timestamp) VALUES (?, ?)", (ip, now))
    conn.commit()
    conn.close()
    return True

def cache_response(key: str, response: str, provider: str):
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO cache (key, response, provider, created_at) VALUES (?, ?, ?, ?)",
              (key, response, provider, time.time()))
    conn.commit()
    conn.close()

def get_cached_response(key: str) -> Optional[dict]:
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT response, provider FROM cache WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"response": row[0], "provider": row[1]}
    return None

def save_message(conversation_id: str, role: str, content: str, provider: str = None):
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    msg_id = int(time.time() * 1000)
    c.execute("INSERT INTO messages (id, conversation_id, role, content, provider, created_at) VALUES (?, ?, ?, ?, ?, ?)",
              (msg_id, conversation_id, role, content, provider, time.time()))
    c.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (time.time(), conversation_id))
    conn.commit()
    conn.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="Kolibri AI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health():
    return {"status": "ok", "provider_status": ai_manager.get_status()}

@app.get("/api/providers")
async def list_providers():
    return ai_manager.get_status()

@app.get("/api/models")
async def list_models():
    return {
        "models": ai_manager.get_model_catalog(),
        "system_prompt": ai_manager.get_system_prompt(),
    }

@app.post("/api/chat")
async def chat(request: ChatRequest, req: Request):
    ip = req.client.host
    if not check_rate_limit(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    model = request.model or "auto"
    provider = request.provider

    cache_key = get_cache_key(request.messages, model)
    cached = get_cached_response(cache_key)
    if cached:
        return {
            "response": cached["response"],
            "provider": cached["provider"],
            "cached": True
        }

    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    if request.system_prompt:
        messages.insert(0, {"role": "system", "content": request.system_prompt})

    result = await ai_manager.generate(
        messages=messages,
        model=model,
        provider=provider,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        enable_thinking=request.enable_thinking or False,
    )

    cache_response(cache_key, result["response"], result["provider"])
    return {**result, "cached": False}

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            messages = data.get("messages", [])
            model = data.get("model", "auto")

            if not messages:
                await websocket.send_json({"error": "No messages provided"})
                continue

            result = await ai_manager.generate(
                messages=messages,
                model=model,
                temperature=data.get("temperature", 0.7),
                max_tokens=data.get("max_tokens", 2048),
                enable_thinking=data.get("enable_thinking", False),
            )
            await websocket.send_json(result)
    except WebSocketDisconnect:
        pass

@app.post("/api/conversations")
async def create_conversation(title: str = "New Chat"):
    conv_id = f"conv_{int(time.time() * 1000)}"
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    now = time.time()
    c.execute("INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
              (conv_id, title, now, now))
    conn.commit()
    conn.close()
    return {"id": conv_id, "title": title}

@app.get("/api/conversations")
async def list_conversations():
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows]

@app.get("/api/conversations/{conv_id}/messages")
async def get_messages(conv_id: str):
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT role, content, provider, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at", (conv_id,))
    rows = c.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1], "provider": r[2], "created_at": r[3]} for r in rows]

@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
    c.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    conn.commit()
    conn.close()
    return {"deleted": True}

@app.post("/api/tts")
async def text_to_speech(request: TTSRequest):
    result = await tts_engine.synthesize(request.text, request.voice)
    return result

@app.get("/api/tts/voices")
async def list_tts_voices():
    return await tts_engine.list_voices()

@app.post("/api/search")
async def web_search(request: SearchRequest):
    results = await web_engine.search(request.query, request.num_results)
    return {"results": results}

@app.post("/api/tools")
async def tool_call(request: ToolCallRequest):
    result = await ai_manager.tool_call(
        message=request.message,
        tools=request.tools or []
    )
    return result



from pipeline import PipelineRequest, run_pipeline, pipeline_health

@app.post("/api/pipeline")
async def pipeline_endpoint(request: PipelineRequest, req: Request):
    ip = req.client.host
    if not check_rate_limit(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    result = await run_pipeline(request)
    return result.model_dump()

@app.get("/api/pipeline/health")
async def pipeline_health_endpoint():
    return await pipeline_health()


@app.get("/api/factory/status")
async def api_factory_status():
    try:
        return await fetch_factory_status()
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "source": "control-plane",
                "error": str(exc),
                "total_nodes": 0,
                "online_nodes": 0,
                "free_ram_gb": 0,
                "total_ram_gb": 0,
                "avg_cpu_percent": 0,
                "queue_size": 0,
                "nodes": {},
                "node_list": [],
                "control_plane": {"status": "unavailable"},
            },
        )


@app.get("/cluster/status")
async def cluster_status():
    return await api_factory_status()

app.include_router(v1_router)

PROXY_ROUTES = {
    "/api/knowledge": {"target": "http://10.99.0.3:8002", "strip": "/api/knowledge", "add": "/rag"},
    "/api/agent": {"target": "http://10.99.0.4:8003", "strip": "/api/agent", "add": "/agent"},
    "/api/inference": {"target": "http://10.99.0.5:8001", "strip": "/api/inference", "add": "/inference"},
    "/cluster": {"target": "http://127.0.0.1:9001", "strip": "/cluster", "add": ""},
}

@app.api_route("/{prefix}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_handler(prefix: str, path: str, request: Request):
    req_path = f"/{prefix}/{path}"
    if req_path.startswith("/assets/"):
        frontend_root = resolve_frontend_path()
        if frontend_root:
            asset_path = frontend_root / req_path.lstrip("/")
            if asset_path.exists() and asset_path.is_file():
                return FileResponse(str(asset_path))
    upstream = None
    matched_prefix = None

    for route_prefix, route_cfg in PROXY_ROUTES.items():
        if req_path.startswith(route_prefix):
            upstream = route_cfg["target"]
            matched_prefix = route_prefix
            add_path = route_cfg.get("add", "")
            break
        if req_path.startswith(route_prefix):
            break

    # Skip v1 routes - they are handled by specific handlers
    if req_path.startswith("/api/v1/"):
        raise HTTPException(status_code=404, detail="Not found")
    
    if not upstream:
        raise HTTPException(status_code=404, detail="Not found")

    target_url = f"{upstream}{add_path}{req_path[len(matched_prefix):]}"

    async with httpx.AsyncClient(timeout=120.0) as client:
        body = await request.body()
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "transfer-encoding")}
        resp = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            params=dict(request.query_params),
        )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers={k: v for k, v in resp.headers.items() if k.lower() not in ("transfer-encoding", "content-encoding", "content-length")},
    )

def resolve_frontend_path() -> Path | None:
    candidates: list[Path] = []
    explicit = os.environ.get("KOLIBRI_FRONTEND_DIST")
    if explicit:
        candidates.append(Path(explicit))
    candidates.extend([
        Path("/opt/kolibri-ai/frontend/dist"),
        Path(__file__).resolve().parents[1] / "frontend" / "dist",
    ])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


frontend_path = resolve_frontend_path()
if frontend_path and frontend_path.exists():
    assets_path = frontend_path / "assets"
    if assets_path.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = frontend_path / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_path / "index.html"))
