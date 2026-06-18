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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from providers import AIProviderManager, is_estimate_intent
from tts import TTSEngine
from stt import STTEngine
from websearch import WebSearchEngine
from config import DB_PATH, CORS_ORIGINS, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW, FRONTEND_DIR, RAG_SERVICE_URL, AGENT_SERVICE_URL, INFERENCE_SERVICE_URL, CLUSTER_SERVICE_URL
from auth import (
    init_users_table, register_user, login_user, refresh_access_token,
    get_current_user, get_current_user_optional,
    UserRegister, UserLogin, TokenResponse, UserOut,
)
from logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger("main")

START_TIME = time.time()
REQUEST_COUNT = 0
ERROR_COUNT = 0


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        global REQUEST_COUNT, ERROR_COUNT
        REQUEST_COUNT += 1
        start = time.time()
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        try:
            response = await call_next(request)
            duration_ms = (time.time() - start) * 1000
            logger.info(
                f"{method} {path} → {response.status_code} ({duration_ms:.0f}ms)",
                extra={"extra_data": {
                    "method": method,
                    "path": path,
                    "status": response.status_code,
                    "duration_ms": round(duration_ms, 1),
                    "client_ip": client_ip,
                }},
            )
            return response
        except Exception as exc:
            ERROR_COUNT += 1
            duration_ms = (time.time() - start) * 1000
            logger.error(
                f"{method} {path} → ERROR ({duration_ms:.0f}ms): {exc}",
                extra={"extra_data": {
                    "method": method,
                    "path": path,
                    "duration_ms": round(duration_ms, 1),
                    "client_ip": client_ip,
                    "error": str(exc),
                }},
                exc_info=True,
            )
            raise

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
init_users_table()

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
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None
    enable_thinking: Optional[bool] = False
    conversation_id: Optional[str] = None

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

def check_rate_limit(ip: str, limit: int = RATE_LIMIT_REQUESTS, window: int = RATE_LIMIT_WINDOW) -> bool:
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

async def check_rate_limit_async(ip: str, limit: int = RATE_LIMIT_REQUESTS, window: int = RATE_LIMIT_WINDOW) -> bool:
    try:
        from rate_limiter import check_rate_limit_redis
        result = await check_rate_limit_redis(ip, limit, window)
        if result is not None:
            return result
    except Exception:
        pass
    return check_rate_limit(ip, limit, window)

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


import re as _re

def extract_estimate_json(text: str) -> Optional[dict]:
    pattern = r'```json\s*(.*?)\s*```'
    match = _re.search(pattern, text, _re.DOTALL)
    raw = match.group(1).strip() if match else text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find('{')
        if start == -1:
            return None
        depth = 0
        end = -1
        for i, c in enumerate(raw[start:], start):
            if c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end != -1:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                return None
        fixed = raw[start:]
        open_sq = fixed.count('[') - fixed.count(']')
        open_cu = fixed.count('{') - fixed.count('}')
        if open_sq > 0:
            last_arr_close = fixed.rfind(']')
            if last_arr_close != -1:
                insert_pos = last_arr_close + 1
                fixed = fixed[:insert_pos] + ('}' * max(0, open_cu - open_sq)) + fixed[insert_pos:]
                fixed = fixed + ']' * open_sq
            else:
                fixed = fixed + ']' * open_sq + '}' * open_cu
        else:
            fixed = fixed + '}' * max(0, open_cu)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            return None


def normalize_estimate(data: dict) -> dict:
    root = data.get("смета", data)

    raw_sections = root.get("sections", root.get("разделы", []))
    items = []
    for section in raw_sections:
        section_name = section.get("name", section.get("название", ""))
        raw_items = section.get("items", section.get("работы", section.get("позиции", [])))
        for item in raw_items:
            qty = float(item.get("quantity", item.get("кол_во", item.get("кол-во", 0))))
            price = float(item.get("unit_price", item.get("цена", 0)))
            name = item.get("name", item.get("наименование", item.get("наимен", "")))
            unit = item.get("unit", item.get("единица", "м2"))
            items.append({
                "id": item.get("id", f"item_{len(items) + 1}"),
                "section": section_name,
                "name": name,
                "unit": unit,
                "quantity": qty,
                "unit_price": price,
                "total": qty * price,
                "note": item.get("comment", item.get("примечание", "")),
            })

    totals_raw = root.get("totals", root.get("сводная_таблица", {}))
    works = sum(i["total"] for i in items)
    materials = 0
    delivery = float(totals_raw.get("delivery", 0))
    discount = float(totals_raw.get("discount", 0))
    grand_total = float(root.get("итого_к_оплате", totals_raw.get("grand_total", works)))

    client = root.get("client", root.get("клиент", {}))
    if isinstance(client, str):
        client = {"name": client, "phone": None}
    obj = root.get("object", root.get("объект", {}))
    if isinstance(obj, str):
        obj = {"name": obj, "area": root.get("площадь", 0)}

    return {
        "title": root.get("title", root.get("проект", "Смета")),
        "client": client,
        "object": obj,
        "items": items,
        "totals": {
            "works": works,
            "materials": materials,
            "delivery": delivery,
            "discount": discount,
            "grand_total": grand_total,
        },
        "assumptions": root.get("assumptions", root.get("примечания", [])),
        "version": 1,
    }

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Kolibri AI starting up")
    from health_checker import start_health_checker
    checker_task = await start_health_checker()
    yield
    checker_task.cancel()
    logger.info("Kolibri AI shutting down")

app = FastAPI(title="Kolibri AI", version="1.0.0", lifespan=lifespan)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.get("/api/health")
async def health():
    return {"status": "ok", "provider_status": ai_manager.get_status()}

@app.get("/metrics")
async def metrics():
    uptime = time.time() - START_TIME
    return Response(
        content="\n".join([
            f"# HELP kolibri_uptime_seconds Uptime in seconds",
            f"# TYPE kolibri_uptime_seconds gauge",
            f"kolibri_uptime_seconds {uptime:.0f}",
            f"# HELP kolibri_requests_total Total requests",
            f"# TYPE kolibri_requests_total counter",
            f"kolibri_requests_total {REQUEST_COUNT}",
            f"# HELP kolibri_errors_total Total errors",
            f"# TYPE kolibri_errors_total counter",
            f"kolibri_errors_total {ERROR_COUNT}",
        ]),
        media_type="text/plain",
    )

@app.post("/api/auth/register", response_model=TokenResponse)
async def auth_register(data: UserRegister):
    return register_user(data)

@app.post("/api/auth/login", response_model=TokenResponse)
async def auth_login(data: UserLogin):
    return login_user(data)

@app.post("/api/auth/refresh", response_model=TokenResponse)
async def auth_refresh(refresh_token: str):
    return refresh_access_token(refresh_token)

@app.get("/api/auth/me", response_model=UserOut)
async def auth_me(user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT id, username, created_at FROM users WHERE id = ?", (user["id"],))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut(id=row[0], username=row[1], created_at=row[2])

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
async def chat(request: ChatRequest, req: Request, user: dict = Depends(get_current_user_optional)):
    ip = req.client.host
    if not await check_rate_limit_async(ip):
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

    if request.conversation_id:
        user_content = request.messages[-1].content if request.messages else ""
        save_message(request.conversation_id, "user", user_content, None)
        save_message(request.conversation_id, "assistant", result["response"], result.get("provider"))

    raw_json = extract_estimate_json(result["response"])
    if raw_json:
        normalized = normalize_estimate(raw_json)
        canvas = {
            "id": f"canvas_{int(time.time())}",
            "type": "estimate",
            "title": normalized.get("title", "Смета"),
            "data": normalized,
            "status": "ready"
        }
        return {**result, "canvas": canvas, "cached": False}

    return {**result, "cached": False}

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    token = websocket.query_params.get("token")
    user = None
    if token:
        try:
            from auth import decode_token
            payload = decode_token(token)
            if payload.get("type") == "access":
                user = {"id": int(payload["sub"]), "username": payload.get("username")}
        except Exception:
            pass

    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            messages = data.get("messages", [])
            model = data.get("model", "auto")
            conv_id = data.get("conversation_id")

            if not messages:
                await websocket.send_json({"error": "No messages provided"})
                continue

            full_response = ""
            estimate_mode = is_estimate_intent(messages[-1]["content"] if messages else "")
            max_tok = data.get("max_tokens", 16384 if estimate_mode else 2048)
            async for chunk in ai_manager.generate_stream(
                messages=messages,
                model=model,
                temperature=data.get("temperature", 0.3 if estimate_mode else 0.7),
                max_tokens=max_tok,
            ):
                if chunk.get("done"):
                    full_response = chunk.get("response", full_response)
                    msg = {
                        "response": full_response,
                        "provider": chunk.get("provider", "mimo"),
                        "model": chunk.get("model", "mimo-auto"),
                        "done": True,
                    }
                    if estimate_mode:
                        raw_json = extract_estimate_json(full_response)
                        if raw_json:
                            msg["canvas"] = {"type": "estimate", "data": normalize_estimate(raw_json)}
                    await websocket.send_json(msg)
                else:
                    await websocket.send_json({
                        "chunk": chunk.get("chunk", ""),
                        "provider": chunk.get("provider", "mimo"),
                        "streaming": True,
                    })

            if conv_id and full_response:
                user_content = messages[-1]["content"] if messages else ""
                save_message(conv_id, "user", user_content, None)
                save_message(conv_id, "assistant", full_response, "mimo")

    except WebSocketDisconnect:
        pass

@app.post("/api/conversations")
async def create_conversation(request: Request, user: dict = Depends(get_current_user_optional)):
    try:
        body = await request.json()
        title = body.get("title", "New Chat")
    except:
        title = "New Chat"
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
async def list_conversations(user: dict = Depends(get_current_user_optional)):
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows]

@app.get("/api/conversations/{conv_id}/messages")
async def get_messages(conv_id: str, user: dict = Depends(get_current_user_optional)):
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT role, content, provider, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at", (conv_id,))
    rows = c.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1], "provider": r[2], "created_at": r[3]} for r in rows]

@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str, user: dict = Depends(get_current_user_optional)):
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
async def pipeline_endpoint(request: PipelineRequest, req: Request, user: dict = Depends(get_current_user_optional)):
    ip = req.client.host
    if not await check_rate_limit_async(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    result = await run_pipeline(request)
    return result.model_dump()

@app.get("/api/pipeline/health")
async def pipeline_health_endpoint():
    return await pipeline_health()

app.include_router(v1_router)

@app.get("/api/v1/cluster")
async def cluster_health():
    """Aggregate health from all cluster nodes via VPN."""
    from health_checker import get_cached_health
    import json as _json
    config_path = Path(__file__).parent.parent / "infra" / "network" / "config.json"
    try:
        config = _json.loads(config_path.read_text())
    except Exception:
        config = {"servers": {}}

    cached = get_cached_health()
    nodes = {}
    for name, server in config.get("servers", {}).items():
        vpn_ip = server.get("vpn_ip", "")
        cached_entry = cached.get(vpn_ip, {})
        nodes[name] = {
            "ip": vpn_ip,
            "role": server.get("role", "unknown"),
            "status": cached_entry.get("status", "unknown"),
            "latency_ms": cached_entry.get("latency_ms"),
            "last_check": cached_entry.get("last_check"),
            "public_ip": server.get("public_ip", ""),
        }

    online = sum(1 for n in nodes.values() if n["status"] == "ok")
    return {
        "total_nodes": len(nodes),
        "online_nodes": online,
        "nodes": nodes,
    }

@app.post("/api/documents/estimate/pdf")
async def generate_estimate_pdf_endpoint(request: Request, user: dict = Depends(get_current_user_optional)):
    from documents import generate_estimate_pdf
    data = await request.json()
    path = generate_estimate_pdf(data)
    return {"path": path, "filename": Path(path).name}

@app.post("/api/documents/estimate/docx")
async def generate_estimate_docx_endpoint(request: Request, user: dict = Depends(get_current_user_optional)):
    from documents import generate_estimate_docx
    data = await request.json()
    path = generate_estimate_docx(data)
    return {"path": path, "filename": Path(path).name}

@app.post("/api/documents/commercial-offer")
async def generate_kp_endpoint(request: Request, user: dict = Depends(get_current_user_optional)):
    from documents import generate_commercial_offer_pdf
    data = await request.json()
    estimate = data.get("estimate", data)
    company = data.get("company")
    path = generate_commercial_offer_pdf(estimate, company)
    return {"path": path, "filename": Path(path).name}

@app.get("/api/documents")
async def list_documents_endpoint(user: dict = Depends(get_current_user_optional)):
    from documents import list_documents
    return {"documents": list_documents()}

@app.get("/api/documents/file/{filename}")
async def download_document(filename: str, user: dict = Depends(get_current_user_optional)):
    from documents import DOCS_DIR
    file_path = DOCS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path), filename=filename)

PROXY_ROUTES = {
    "/api/knowledge": {"target": RAG_SERVICE_URL, "strip": "/api/knowledge", "add": "/rag/documents"},
    "/api/agent": {"target": AGENT_SERVICE_URL, "strip": "/api/agent", "add": "/agent"},
    "/api/inference": {"target": INFERENCE_SERVICE_URL, "strip": "/api/inference", "add": "/inference"},
    "/cluster": {"target": CLUSTER_SERVICE_URL, "strip": "/cluster", "add": ""},
}

@app.api_route("/{prefix}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_handler(prefix: str, path: str, request: Request, user: dict = Depends(get_current_user_optional)):
    req_path = f"/{prefix}/{path}"
    upstream = None
    matched_prefix = None

    if req_path.startswith("/api/v1/"):
        raise HTTPException(status_code=404, detail="Not found")

    for route_prefix, route_cfg in PROXY_ROUTES.items():
        if req_path.startswith(route_prefix):
            upstream = route_cfg["target"]
            matched_prefix = route_prefix
            add_path = route_cfg.get("add", "")
            break

    if not upstream:
        raise HTTPException(status_code=404, detail="Not found")

    target_url = f"{upstream}{add_path}{req_path[len(matched_prefix):]}"
    logger.debug(f"Proxy {request.method} {req_path} → {target_url}")

    try:
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
    except httpx.ConnectError as exc:
        logger.error(f"Proxy connect error: {req_path} → {target_url}: {exc}")
        raise HTTPException(status_code=502, detail=f"Service unavailable: {upstream}")
    except httpx.TimeoutException as exc:
        logger.error(f"Proxy timeout: {req_path} → {target_url}: {exc}")
        raise HTTPException(status_code=504, detail="Upstream request timed out")
    except httpx.RequestError as exc:
        logger.error(f"Proxy error: {req_path} → {target_url}: {exc}")
        raise HTTPException(status_code=502, detail=f"Proxy error: {exc}")

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers={k: v for k, v in resp.headers.items() if k.lower() not in ("transfer-encoding", "content-encoding", "content-length")},
    )

frontend_path = FRONTEND_DIR
if frontend_path.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = frontend_path / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_path / "index.html"))


