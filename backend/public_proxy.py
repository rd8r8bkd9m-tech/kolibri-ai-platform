"""Public compatibility API for the Kolibri web frontend.

This lightweight gateway keeps `/api` and `/ws` stable for static frontends
even when the underlying node exposes a different internal API version.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware


UPSTREAM = "http://104.253.43.117"
CHAT_UPSTREAMS = [
    item.strip().rstrip("/")
    for item in os.environ.get(
        "KOLIBRI_CHAT_UPSTREAMS",
        "http://104.253.43.117",
    ).split(",")
    if item.strip()
]
CHAT_UPSTREAM_TIMEOUT_SECONDS = float(os.environ.get("KOLIBRI_CHAT_UPSTREAM_TIMEOUT_SECONDS", "6"))
DATA_DIR = Path("/srv/kolibri/repo/data")
CONVERSATIONS_PATH = DATA_DIR / "public_proxy_conversations.json"
PROJECT_DIR = Path(os.environ.get("KOLIBRI_PROJECT_ROOT", "/srv/kolibri/repo"))
MIMO_BIN = os.environ.get("KOLIBRI_MIMO_BIN", "/usr/local/bin/mimo")
MIMO_MODEL = os.environ.get("KOLIBRI_MIMO_MODEL", "mimo/mimo-auto")
MIMO_TIMEOUT_SECONDS = int(os.environ.get("KOLIBRI_MIMO_TIMEOUT_SECONDS", "120"))

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
    return upstream_base_json(UPSTREAM, path, payload, timeout)


def upstream_base_json(
    base_url: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 45,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"error": str(exc)}


def cluster_chat(message: str, provider: str | None) -> dict[str, Any] | None:
    payload = {"messages": [{"role": "user", "content": message}], "provider": provider or "mimo"}
    errors = []
    for base_url in CHAT_UPSTREAMS:
        path = "/api/v1/ai/kolibri-only/chat" if provider in {"formulalm", "local", "kolibri"} else "/api/chat"
        body = {"message": message} if path.startswith("/api/v1/") else payload
        result = upstream_base_json(base_url, path, body, timeout=CHAT_UPSTREAM_TIMEOUT_SECONDS)
        if isinstance(result.get("response"), str) and result["response"].strip():
            normalized = normalize_chat_result(result)
            normalized["provider"] = result.get("provider") or provider or normalized.get("provider") or "mimo"
            normalized["upstream_url"] = base_url
            return normalized
        errors.append({"upstream": base_url, "error": result.get("error") or result.get("detail") or "empty_response"})
    return {"response": "", "provider": "proxy", "model": "cluster-failover", "cached": False, "errors": errors}


def latest_user_message(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return str(messages[-1].get("content") or "") if messages else ""


def message_from_payload(body: dict[str, Any]) -> str:
    direct = body.get("message")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    messages = body.get("messages")
    if isinstance(messages, list):
        normalized_messages = [item for item in messages if isinstance(item, dict)]
        return latest_user_message(normalized_messages).strip()
    return ""


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


def result_from_text(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        return data
    marker_start = text.find("```json")
    if marker_start == -1:
        marker_start = text.find("```")
    if marker_start == -1:
        return None
    block_start = text.find("{", marker_start)
    block_end = text.rfind("}")
    if block_start == -1 or block_end <= block_start:
        return None
    try:
        data = json.loads(text[block_start : block_end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def extract_mimo_text(stdout: str, stderr: str) -> str:
    candidates: list[str] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        part = event.get("part")
        if isinstance(part, dict) and part.get("type") == "text":
            text = str(part.get("text") or "")
            structured = result_from_text(text)
            if structured and isinstance(structured.get("response"), str):
                candidates.append(structured["response"])
            elif structured and isinstance(structured.get("summary"), str):
                candidates.append(structured["summary"])
            elif text.strip():
                candidates.append(text.strip())
        elif isinstance(event.get("text"), str):
            candidates.append(event["text"].strip())
        elif isinstance(event.get("response"), str):
            candidates.append(event["response"].strip())
    if candidates:
        return candidates[-1]
    text = (stdout or stderr).strip()
    structured = result_from_text(text)
    if structured and isinstance(structured.get("response"), str):
        return structured["response"]
    return text[:4000]


def mimo_chat(message: str) -> dict[str, Any]:
    if not message.strip():
        return {"response": "Напишите сообщение.", "provider": "mimo", "model": MIMO_MODEL, "cached": False}
    prompt = (
        "Ты публичный AI-ассистент Колибри. Отвечай кратко, полезно и на русском языке, "
        "если пользователь не попросил иначе. Не упоминай внутренние ключи, серверы или скрытые файлы.\n\n"
        f"Пользователь: {message}\n"
        "Ответ:"
    )
    try:
        proc = subprocess.Popen(
            [
                MIMO_BIN,
                "run",
                "--format",
                "json",
                "--dir",
                str(PROJECT_DIR),
                "--model",
                MIMO_MODEL,
                prompt,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        stdout, stderr = proc.communicate(timeout=MIMO_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            pass
        return {
            "response": "MiMo не успел ответить за отведенное время. Повторите запрос или выберите локальную модель.",
            "provider": "mimo",
            "model": MIMO_MODEL,
            "cached": False,
            "error": "mimo_timeout",
        }
    except FileNotFoundError:
        return {
            "response": "MiMo CLI не найден на сервере. Переключитесь на локальную модель.",
            "provider": "mimo",
            "model": MIMO_MODEL,
            "cached": False,
            "error": "mimo_not_found",
        }
    response = extract_mimo_text(stdout, stderr)
    if proc.returncode != 0 and not response:
        response = "MiMo временно недоступен. Переключитесь на локальную модель или повторите позже."
    return {
        "response": response,
        "provider": "mimo",
        "model": MIMO_MODEL,
        "cached": False,
        "returncode": proc.returncode,
    }


def local_chat(message: str) -> dict[str, Any]:
    result = cluster_chat(message, "formulalm")
    if result and result.get("response"):
        result["provider"] = "formulalm"
        return result
    return result or {
        "response": "Main backend временно недоступен.",
        "provider": "formulalm",
        "model": "main-backend",
        "cached": False,
        "error": "main_unreachable",
    }


async def route_chat(provider: str | None, message: str) -> dict[str, Any]:
    if provider in {"formulalm", "local", "kolibri"}:
        return await asyncio.to_thread(local_chat, message)
    clustered = await asyncio.to_thread(cluster_chat, message, provider or "mimo")
    if clustered and clustered.get("response"):
        clustered["provider"] = clustered.get("provider") or "mimo"
        return clustered
    return clustered or {
        "response": "Backend-кластер временно недоступен. Запрос не передан в локальный MiMo CLI, чтобы не блокировать сайт.",
        "provider": "cluster",
        "model": "cluster-failover",
        "cached": False,
        "error": "all_chat_upstreams_failed",
    }


@app.get("/health")
@app.get("/api/health")
def health() -> dict[str, Any]:
    upstream = upstream_json("/api/v1/health/live", timeout=3)
    return {"status": "ok", "proxy": "public", "upstream": upstream}


@app.get("/cluster/status")
@app.get("/api/cluster/status")
def cluster_status() -> dict[str, Any]:
    upstream = upstream_json("/cluster/status", timeout=5)
    if not upstream.get("error") and isinstance(upstream, dict):
        return upstream
    return {
        "status": "degraded",
        "total_nodes": 2,
        "online_nodes": 1,
        "free_ram_gb": 0,
        "avg_cpu_percent": 0,
        "queue_size": 0,
        "nodes": {
            "main": {
                "status": "online",
                "role": "api-gateway",
                "ip": "10.99.0.2",
                "cpu": 0,
                "ram": "unknown",
            },
            "home": {
                "status": "degraded",
                "role": "edge-proxy",
                "ip": "10.99.0.1",
                "cpu": 0,
                "ram": "unknown",
            },
        },
        "upstream": upstream,
    }


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
    try:
        body = await request.json()
    except Exception:
        body = {}
    body = body if isinstance(body, dict) else {}
    message = message_from_payload(body)
    provider = body.get("provider")
    normalized = await route_chat(provider, message)

    conversation_id = body.get("conversation_id")
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
            try:
                body = await websocket.receive_json()
            except Exception:
                await websocket.send_json({
                    "response": "Некорректный WebSocket payload: ожидается JSON.",
                    "provider": "proxy",
                    "model": "kolibri-public-proxy",
                    "done": True,
                    "error": "invalid_json",
                })
                continue
            body = body if isinstance(body, dict) else {}
            message = message_from_payload(body)
            provider = body.get("provider")
            normalized = await route_chat(provider, message)
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
