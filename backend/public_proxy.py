"""Public compatibility API for the Kolibri web frontend.

This lightweight gateway keeps `/api` and `/ws` stable for static frontends
even when the underlying node exposes a different internal API version.
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware


UPSTREAM = "http://127.0.0.1:8001"
DATA_DIR = Path("/srv/kolibri/repo/data")
CONVERSATIONS_PATH = DATA_DIR / "public_proxy_conversations.json"

app = FastAPI(title="Kolibri Public Proxy", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://kolibriai.ru", "https://www.kolibriai.ru", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_store() -> dict[str, Any]:
    try:
        return json.loads(CONVERSATIONS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"conversations": {}, "messages": {}}


def save_store(store: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONVERSATIONS_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def upstream_json(path: str, payload: dict[str, Any] | None = None, timeout: int = 45) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{UPSTREAM}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"error": str(exc)}


def latest_user_message(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return str(messages[-1].get("content") or "") if messages else ""


def normalize_chat_result(result: dict[str, Any]) -> dict[str, Any]:
    if "response" in result:
        return {
            "response": result.get("response") or "",
            "provider": "kolibri",
            "model": result.get("model") or result.get("method") or "kolibri-public-proxy",
            "cached": False,
            "upstream": {k: v for k, v in result.items() if k not in {"response"}},
        }
    return {
        "response": "Backend временно недоступен. Запрос принят публичным proxy, повторите через несколько секунд.",
        "provider": "proxy",
        "model": "kolibri-public-proxy",
        "cached": False,
        "error": result.get("error", "unknown_upstream_error"),
    }


@app.get("/health")
@app.get("/api/health")
def health() -> dict[str, Any]:
    upstream = upstream_json("/api/v1/health/live", timeout=3)
    return {"status": "ok", "proxy": "public", "upstream": upstream}


@app.get("/api/providers")
def providers() -> list[dict[str, Any]]:
    return [
        {"name": "mimo", "available": True, "status": "online"},
        {"name": "formulalm", "available": True, "status": "online"},
        {"name": "openai", "available": False, "status": "offline"},
        {"name": "anthropic", "available": False, "status": "offline"},
    ]


@app.get("/api/models")
def models() -> dict[str, Any]:
    upstream = upstream_json("/api/v1/ai/models", timeout=5)
    return {"models": upstream.get("models", []), "upstream": upstream}


@app.post("/api/chat")
async def chat(request: Request) -> dict[str, Any]:
    body = await request.json()
    messages = body.get("messages") if isinstance(body, dict) else []
    message = latest_user_message(messages if isinstance(messages, list) else [])
    result = await asyncio.to_thread(upstream_json, "/api/v1/ai/chat", {"message": message}, 60)
    normalized = normalize_chat_result(result)

    conversation_id = body.get("conversation_id") if isinstance(body, dict) else None
    if conversation_id:
        store = load_store()
        store.setdefault("messages", {}).setdefault(conversation_id, []).extend(
            [
                {"role": "user", "content": message, "provider": None, "created_at": time.time()},
                {
                    "role": "assistant",
                    "content": normalized["response"],
                    "provider": normalized["provider"],
                    "created_at": time.time(),
                },
            ]
        )
        if conversation_id in store.get("conversations", {}):
            store["conversations"][conversation_id]["updated_at"] = time.time()
        save_store(store)
    return normalized


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            body = await websocket.receive_json()
            messages = body.get("messages", []) if isinstance(body, dict) else []
            message = latest_user_message(messages if isinstance(messages, list) else [])
            result = await asyncio.to_thread(upstream_json, "/api/v1/ai/chat", {"message": message}, 60)
            normalized = normalize_chat_result(result)
            await websocket.send_json(
                {
                    "response": normalized["response"],
                    "provider": normalized["provider"],
                    "model": normalized["model"],
                    "done": True,
                }
            )
    except WebSocketDisconnect:
        return


@app.post("/api/conversations")
async def create_conversation(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        body = {}
    now = time.time()
    conversation_id = f"conv_{int(now * 1000)}"
    store = load_store()
    store.setdefault("conversations", {})[conversation_id] = {
        "id": conversation_id,
        "title": body.get("title") or "New Chat",
        "created_at": now,
        "updated_at": now,
    }
    store.setdefault("messages", {})[conversation_id] = []
    save_store(store)
    return store["conversations"][conversation_id]


@app.get("/api/conversations")
def list_conversations() -> list[dict[str, Any]]:
    store = load_store()
    conversations = list(store.get("conversations", {}).values())
    return sorted(conversations, key=lambda item: item.get("updated_at", 0), reverse=True)


@app.get("/api/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: str) -> list[dict[str, Any]]:
    return load_store().get("messages", {}).get(conversation_id, [])


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict[str, bool]:
    store = load_store()
    store.get("conversations", {}).pop(conversation_id, None)
    store.get("messages", {}).pop(conversation_id, None)
    save_store(store)
    return {"deleted": True}
