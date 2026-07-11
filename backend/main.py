from routes_v1 import router as v1_router
import os
import time
import json
import hashlib
import sqlite3
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any, Literal
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from capability_gateway import CapabilityRequestError, get_capability_gateway
from providers import AIProviderManager, ProviderGatewayError
from tts import TTSEngine
from stt import STTEngine
from websearch import WebSearchEngine
from factory_status import CONTROL_PLANE_URL, fetch_factory_status
from execution_api import require_execution_auth, router as execution_router
from openai_compatibility import router as openai_compatibility_router
from public_responses_api import (
    configure_public_response_executor,
    router as public_responses_router,
)
from public_estimate_api import router as public_estimate_router
from data_paths import DB_PATH
from pipeline import PipelineRequest, run_pipeline, pipeline_health
from public_chat_stream import (
    PublicChatStreamError,
    public_chat_event_stream,
    stream_timeout_seconds,
    verified_public_payload,
)
from vertical_tasks import (
    VerticalTask,
    build_deterministic_estimate_fallback,
    build_vertical_result,
    deterministic_estimate_fallback_text,
    deterministic_estimate_result_text,
    failed_vertical_result,
    prepare_vertical_task,
)

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


async def execute_public_response(**kwargs):
    """Use the same verified provider gateway for the canonical V1 Shell."""

    return await ai_manager.generate(**kwargs)


configure_public_response_executor(execute_public_response)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None
    provider: Optional[str] = None
    execution_mode: Literal["fast", "codex"] = "fast"
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048
    system_prompt: Optional[str] = None
    enable_thinking: Optional[bool] = False
    task: Optional[VerticalTask] = None

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

def get_cache_key(messages: list[dict[str, Any]], model: str, settings: dict[str, Any]) -> str:
    content = json.dumps(
        {"model": model, "messages": messages, "settings": settings},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def validate_public_chat_messages(messages: list[dict[str, Any]]) -> None:
    if not messages or len(messages) > 100:
        raise HTTPException(status_code=422, detail="messages must contain between 1 and 100 items")
    try:
        size = len(json.dumps(messages, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="messages are not JSON serializable") from exc
    if size > 1024 * 1024:
        raise HTTPException(status_code=413, detail="chat input exceeds 1 MiB")

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

cors_origins = [
    origin.strip().rstrip("/")
    for origin in os.environ.get(
        "KOLIBRI_CORS_ORIGINS",
        "https://kolibriai.ru,https://www.kolibriai.ru,http://127.0.0.1:4174,http://localhost:4174",
    ).split(",")
    if origin.strip() and origin.strip() != "*"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Last-Event-ID"],
)


def _is_api_path(path: str) -> bool:
    return path in {"/api", "/v1"} or path.startswith(("/api/", "/v1/"))


def _unknown_api_response() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"detail": "api_route_not_found"},
        headers={"Cache-Control": "no-store"},
    )


def _effective_routes(routes):
    """Yield concrete routes across eager and deferred FastAPI routers."""

    for route in routes:
        candidates = getattr(route, "effective_candidates", None)
        if callable(candidates):
            yield from _effective_routes(candidates())
        else:
            yield route


def _known_api_route_path(path: str) -> bool:
    for route in _effective_routes(app.routes):
        route_path = str(getattr(route, "path", ""))
        route_pattern = getattr(route, "path_regex", None)
        if _is_api_path(route_path) and route_pattern is not None and route_pattern.match(path):
            return True
    return False


@app.middleware("http")
async def prevent_unknown_api_caching(request: Request, call_next):
    if _is_api_path(request.url.path) and not _known_api_route_path(request.url.path):
        return _unknown_api_response()
    response = await call_next(request)
    if response.status_code == 404 and _is_api_path(request.url.path):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
async def health():
    return {"status": "ok", "model": "kolibri"}

@app.get("/api/providers", dependencies=[Depends(require_execution_auth)])
async def list_providers():
    return ai_manager.get_status()

@app.get("/api/models")
async def list_models():
    return {
        "object": "list",
        "models": ["kolibri"],
        "data": [{"id": "kolibri", "object": "model", "owned_by": "kolibri"}],
        "supported_execution_modes": ["fast", "codex"],
    }


@app.get("/v1/models")
async def list_openai_models():
    """Public model catalog; durable execution routes remain authenticated."""
    return {
        "object": "list",
        "data": [{"id": "kolibri", "object": "model", "created": 0, "owned_by": "kolibri-ai-os"}],
        "schema_version": "kolibri.execution.v1",
        "supported_execution_modes": ["fast", "codex"],
    }


@app.get("/v1/capabilities")
async def list_public_capabilities():
    """Expose sanitized capability declarations, never credentials or topology."""
    return get_capability_gateway().envelope()

@app.post("/api/v1/chat")
@app.post("/api/chat")
async def chat(request: ChatRequest, req: Request):
    ip = req.client.host
    if not check_rate_limit(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    model = "kolibri"
    # Provider identity is an internal routing decision.  The compatibility
    # field is accepted for old clients but never grants provider selection.
    provider = None

    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    if request.system_prompt:
        messages.insert(0, {"role": "system", "content": request.system_prompt})
    vertical_calculation = None
    if request.task is not None:
        vertical_instructions, vertical_calculation = prepare_vertical_task(request.task)
        messages.insert(0, {"role": "system", "content": vertical_instructions})
    validate_public_chat_messages(messages)
    cache_key = get_cache_key(messages, model, {
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "enable_thinking": request.enable_thinking,
        "execution_mode": request.execution_mode,
    })
    # The legacy cache stores text only. Typed tasks carry calculation and
    # materialization evidence, so reusing a text-only row would fabricate an
    # incomplete task envelope. Keep typed requests on the verified live path.
    cached = get_cached_response(cache_key) if request.task is None else None
    if cached:
        return {
            "response": cached["response"],
            "model": "kolibri",
            "technical": {"cache": {"hit": True}},
            "cached": True
        }

    try:
        result = await ai_manager.generate(
            messages=messages,
            model=model,
            provider=provider,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            enable_thinking=request.enable_thinking or False,
            execution_mode=request.execution_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderGatewayError as exc:
        fallback_task = (
            build_deterministic_estimate_fallback(
                request.task,
                reason=str(exc.technical.get("error_type") or "provider_unavailable")
                if isinstance(exc.technical, dict)
                else "provider_unavailable",
            )
            if request.task is not None
            else None
        )
        if fallback_task is not None:
            return {
                "response": deterministic_estimate_fallback_text(fallback_task),
                "model": "kolibri",
                "technical": {"provider_routing": exc.technical},
                "task": fallback_task,
                "cached": False,
            }
        content = {
            "error": {"type": "provider_unavailable", "message": "Kolibri could not produce a verified answer"},
            "model": "kolibri",
            "technical": {"provider_routing": exc.technical},
        }
        if request.task is not None:
            content["task"] = failed_vertical_result(request.task, "provider_unavailable")
        return JSONResponse(status_code=503, content=content)

    selected_provider = result["technical"]["provider_routing"].get("selected_provider") or ""
    if request.task is None:
        cache_response(cache_key, result["response"], selected_provider)
        return {**result, "cached": False}
    task_payload = build_vertical_result(request.task, result, vertical_calculation)
    result_type = (task_payload.get("result") or {}).get("type")
    public_response = (
        deterministic_estimate_fallback_text(task_payload)
        if result_type == "estimate_readiness"
        else deterministic_estimate_result_text(task_payload)
        if result_type == "deterministic_estimate"
        else result.get("response", "")
    )
    return {
        **result,
        "response": public_response,
        "task": task_payload,
        "cached": False,
    }


@app.post("/api/v1/ai/chat/stream")
@app.post("/api/v1/chat/stream")
@app.post("/api/chat/stream")
async def stream_public_chat(
    request: ChatRequest,
    req: Request,
    timeout_seconds: float | None = Query(default=None, ge=1, le=300),
):
    """Stream real chat lifecycle events and one verified terminal answer.

    Provider output is not token-streamed by the current gateway, so this
    compatibility route does not manufacture deltas.  It flushes acceptance
    and execution progress immediately, then publishes the complete answer
    only after the existing content-bound verifier contract passes.
    """

    client_ip = req.client.host if req.client else "unknown"
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    messages = [{"role": message.role, "content": message.content} for message in request.messages]
    if request.system_prompt:
        messages.insert(0, {"role": "system", "content": request.system_prompt})
    vertical_calculation = None
    if request.task is not None:
        vertical_instructions, vertical_calculation = prepare_vertical_task(request.task)
        messages.insert(0, {"role": "system", "content": vertical_instructions})
    validate_public_chat_messages(messages)

    async def execute() -> dict[str, Any]:
        try:
            result = await ai_manager.generate(
                messages=messages,
                model="kolibri",
                provider=None,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                enable_thinking=request.enable_thinking or False,
                execution_mode=request.execution_mode,
            )
        except ValueError as exc:
            raise PublicChatStreamError(
                "invalid_request",
                "The public chat request is invalid",
            ) from exc
        except ProviderGatewayError as exc:
            raise PublicChatStreamError(
                "provider_unavailable",
                "Kolibri could not produce a verified answer",
                retryable=True,
            ) from exc

        # Validate before any cache write.  The legacy text-only cache cannot
        # prove a terminal SSE answer, so streams always use the live verified
        # path and cache only the newly evidence-bound plain-chat result.
        verified_public_payload(result)
        if request.task is None:
            selected_provider = result["technical"]["provider_routing"].get("selected_provider") or ""
            cache_key = get_cache_key(messages, "kolibri", {
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "enable_thinking": request.enable_thinking,
                "execution_mode": request.execution_mode,
            })
            cache_response(cache_key, result["response"], selected_provider)
            return {**result, "cached": False}
        return {
            **result,
            "task": build_vertical_result(request.task, result, vertical_calculation),
            "cached": False,
        }

    stream_id = f"stream_{uuid.uuid4().hex}"
    return StreamingResponse(
        public_chat_event_stream(
            stream_id=stream_id,
            execution_mode=request.execution_mode,
            execute=execute,
            timeout_seconds=stream_timeout_seconds(timeout_seconds),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store, no-transform",
            "X-Accel-Buffering": "no",
        },
    )

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    client_ip = websocket.client.host if websocket.client else "unknown"
    try:
        while True:
            data = await websocket.receive_json()
            if not check_rate_limit(client_ip, limit=30, window=60):
                await websocket.send_json({"error": "rate_limit_exceeded"})
                continue
            messages = data.get("messages", [])
            model = "kolibri"

            if not messages:
                await websocket.send_json({"error": "No messages provided"})
                continue
            try:
                validate_public_chat_messages(messages)
            except HTTPException as exc:
                await websocket.send_json({"error": str(exc.detail), "status_code": exc.status_code})
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

@app.post("/api/conversations", dependencies=[Depends(require_execution_auth)])
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

@app.get("/api/conversations", dependencies=[Depends(require_execution_auth)])
async def list_conversations():
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows]

@app.get("/api/conversations/{conv_id}/messages", dependencies=[Depends(require_execution_auth)])
async def get_messages(conv_id: str):
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT role, content, provider, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at", (conv_id,))
    rows = c.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1], "provider": r[2], "created_at": r[3]} for r in rows]

@app.delete("/api/conversations/{conv_id}", dependencies=[Depends(require_execution_auth)])
async def delete_conversation(conv_id: str):
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
    c.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    conn.commit()
    conn.close()
    return {"deleted": True}

@app.post("/api/tts", dependencies=[Depends(require_execution_auth)])
async def text_to_speech(request: TTSRequest):
    result = await tts_engine.synthesize(request.text, request.voice)
    return result

@app.get("/api/tts/voices")
async def list_tts_voices():
    return await tts_engine.list_voices()

@app.post("/api/search", dependencies=[Depends(require_execution_auth)])
async def web_search(request: SearchRequest):
    results = await web_engine.search(request.query, request.num_results)
    return {"results": results}

@app.post("/api/tools", dependencies=[Depends(require_execution_auth)])
async def tool_call(request: ToolCallRequest):
    try:
        return await ai_manager.tool_call(
            message=request.message,
            tools=request.tools or []
        )
    except CapabilityRequestError as exc:
        raise HTTPException(status_code=422, detail=exc.public_detail()) from exc
    except ProviderGatewayError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "error": "Kolibri could not produce a verified tool response",
                "model": "kolibri",
                "technical": {"provider_routing": exc.technical},
            },
        )

@app.post("/api/pipeline", dependencies=[Depends(require_execution_auth)])
async def pipeline_endpoint(request: PipelineRequest, req: Request):
    ip = req.client.host
    if not check_rate_limit(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    result = await run_pipeline(request)
    return result.model_dump()

@app.get("/api/pipeline/health", dependencies=[Depends(require_execution_auth)])
async def pipeline_health_endpoint():
    return await pipeline_health()


@app.get("/api/factory/status")
async def api_factory_status():
    try:
        status = await fetch_factory_status()
        # Same-origin public Shell receives operational aggregates only. Node
        # identities, addresses and per-worker internals remain owner-only.
        return {
            key: value
            for key, value in status.items()
            if key not in {"nodes", "node_list", "servers", "fallback_nodes"}
        }
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
                "control_plane": {
                    "status": "blocked",
                    "reason": "control_plane_api_unreachable",
                    "canonical_url": CONTROL_PLANE_URL,
                    "fail_closed": True,
                    "repair_task": {
                        "kind": "repair_control_plane_api",
                        "action": "restore the canonical Home Control Plane API",
                    },
                    "can_continue_elsewhere": False,
                },
            },
        )


@app.get("/cluster/status", dependencies=[Depends(require_execution_auth)])
async def cluster_status():
    return await api_factory_status()

app.include_router(v1_router)
app.include_router(openai_compatibility_router)
app.include_router(public_responses_router)
app.include_router(public_estimate_router)
app.include_router(execution_router)

frontend_path = Path(
    os.environ.get("KOLIBRI_FRONTEND_DIST", "/opt/kolibri-ai/current/frontend/dist")
)
if frontend_path.exists():
    frontend_root = frontend_path.resolve()
    app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if _is_api_path(f"/{full_path.lstrip('/')}"):
            return _unknown_api_response()
        file_path = (frontend_root / full_path).resolve()
        if file_path.is_relative_to(frontend_root) and file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_root / "index.html"))
