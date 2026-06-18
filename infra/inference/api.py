"""
Kolibri AI — Inference Service (9FTS Server)

Provides LLM inference via llama.cpp (GGUF models).
Endpoints:
  POST /inference/generate  — text generation (streaming SSE optional)
  POST /inference/chat      — chat completion (messages format)
  GET  /inference/models    — list loaded models
  GET  /inference/health    — health check with model status
  POST /inference/embeddings — generate text embeddings
  POST /inference/models/load   — load a model
  POST /inference/models/unload — unload a model
"""

import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

# ── Config ──────────────────────────────────────────────────────────

MODEL_DIR = os.environ.get("KOLIBRI_MODEL_DIR", "/opt/kolibri-ai/models")
DEFAULT_MODEL = os.environ.get(
    "KOLIBRI_DEFAULT_MODEL",
    "TinyLlama-1.1B-Chat-v1.0.Q4_K_M.gguf",
)
HOST = os.environ.get("KOLIBRI_INFERENCE_HOST", "0.0.0.0")
PORT = int(os.environ.get("KOLIBRI_INFERENCE_PORT", "8001"))
N_GPU_LAYERS = int(os.environ.get("KOLIBRI_N_GPU_LAYERS", "0"))
N_CTX = int(os.environ.get("KOLIBRI_N_CTX", "2048"))
N_THREADS = int(os.environ.get("KOLIBRI_N_THREADS", "4"))

# ── Model Manager ───────────────────────────────────────────────────

loaded_models: Dict[str, Any] = {}
model_lock = asyncio.Lock()
executor = ThreadPoolExecutor(max_workers=2)

KOLIBRI_SYSTEM_PROMPT = (
    "Ты — Kolibri AI, большая языковая модель. "
    "Отвечай на языке пользователя. Не используй эмодзи."
)


def _load_model_sync(model_path: str, model_id: str, n_ctx: int = N_CTX):
    from llama_cpp import Llama
    llm = Llama(
        model_path=model_path,
        n_ctx=n_ctx,
        n_threads=N_THREADS,
        n_gpu_layers=N_GPU_LAYERS,
        verbose=False,
    )
    loaded_models[model_id] = {
        "llm": llm,
        "path": model_path,
        "loaded_at": time.time(),
        "n_ctx": n_ctx,
        "n_gpu_layers": N_GPU_LAYERS,
    }
    return llm


def _unload_model_sync(model_id: str):
    if model_id in loaded_models:
        del loaded_models[model_id]


def _get_model(model_id: Optional[str] = None):
    mid = model_id or DEFAULT_MODEL
    if mid not in loaded_models:
        raise HTTPException(404, f"Model '{mid}' not loaded. Load it first via POST /inference/models/load")
    return loaded_models[mid]["llm"]


# ── Request / Response schemas ──────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    repeat_penalty: float = 1.1
    stop: Optional[List[str]] = None
    stream: bool = False


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    repeat_penalty: float = 1.1
    stop: Optional[List[str]] = None
    stream: bool = False


class EmbeddingsRequest(BaseModel):
    input: str
    model: Optional[str] = None


class LoadModelRequest(BaseModel):
    model_id: str
    model_path: Optional[str] = None
    n_ctx: int = N_CTX


# ── Helpers ─────────────────────────────────────────────────────────

def _build_prompt_from_messages(messages: List[ChatMessage]) -> str:
    parts = []
    for msg in messages:
        role = msg.role
        if role == "system":
            parts.append(f"System: {msg.content}")
        elif role == "user":
            parts.append(f"User: {msg.content}")
        elif role == "assistant":
            parts.append(f"Assistant: {msg.content}")
    parts.append("Assistant:")
    return "\n".join(parts)


async def _generate_sync(llm, params: dict) -> dict:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, lambda: llm.create_completion(**params))
    return result


async def _embed_sync(llm, text: str) -> list:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, lambda: llm.embed(text))
    return result


# ── App lifecycle ───────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    default_path = os.path.join(MODEL_DIR, DEFAULT_MODEL)
    if os.path.exists(default_path):
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                executor,
                _load_model_sync,
                default_path,
                DEFAULT_MODEL,
            )
            print(f"[inference] Loaded default model: {DEFAULT_MODEL}")
        except Exception as e:
            print(f"[inference] Warning: could not load default model: {e}")
    else:
        print(f"[inference] Default model not found at {default_path}, skipping auto-load")
    yield
    executor.shutdown(wait=False)


app = FastAPI(title="Kolibri Inference", version="1.0", lifespan=lifespan)


# ── Health ──────────────────────────────────────────────────────────

@app.get("/inference/health")
async def health():
    model_list = []
    for mid, info in loaded_models.items():
        model_list.append({
            "model_id": mid,
            "path": info["path"],
            "loaded_at": info["loaded_at"],
            "n_ctx": info["n_ctx"],
        })
    return {
        "status": "ok",
        "loaded_models": len(loaded_models),
        "models": model_list,
        "default_model": DEFAULT_MODEL,
        "model_dir": MODEL_DIR,
    }


# ── List models ─────────────────────────────────────────────────────

@app.get("/inference/models")
async def list_models():
    available = []
    if os.path.isdir(MODEL_DIR):
        for f in sorted(os.listdir(MODEL_DIR)):
            if f.endswith(".gguf"):
                path = os.path.join(MODEL_DIR, f)
                available.append({
                    "id": f,
                    "path": path,
                    "size_mb": round(os.path.getsize(path) / (1024 * 1024), 1),
                    "loaded": f in loaded_models,
                })

    loaded = []
    for mid, info in loaded_models.items():
        loaded.append({
            "id": mid,
            "path": info["path"],
            "loaded_at": info["loaded_at"],
            "n_ctx": info["n_ctx"],
        })

    return {
        "default_model": DEFAULT_MODEL,
        "available": available,
        "loaded": loaded,
    }


# ── Load / Unload model ────────────────────────────────────────────

@app.post("/inference/models/load")
async def load_model(req: LoadModelRequest):
    model_path = req.model_path or os.path.join(MODEL_DIR, req.model_id)
    if not os.path.exists(model_path):
        raise HTTPException(404, f"Model file not found: {model_path}")
    async with model_lock:
        if req.model_id in loaded_models:
            return {"status": "already_loaded", "model_id": req.model_id}
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            executor,
            _load_model_sync,
            model_path,
            req.model_id,
            req.n_ctx,
        )
    return {"status": "loaded", "model_id": req.model_id}


@app.post("/inference/models/unload")
async def unload_model(model_id: str):
    async with model_lock:
        if model_id not in loaded_models:
            raise HTTPException(404, f"Model '{model_id}' not loaded")
        _unload_model_sync(model_id)
    return {"status": "unloaded", "model_id": model_id}


# ── Generate ────────────────────────────────────────────────────────

@app.post("/inference/generate")
async def generate(req: GenerateRequest):
    llm = _get_model(req.model)
    model_id = req.model or DEFAULT_MODEL

    params = {
        "prompt": req.prompt,
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
        "top_p": req.top_p,
        "top_k": req.top_k,
        "repeat_penalty": req.repeat_penalty,
        "stop": req.stop,
        "echo": False,
    }

    if req.stream:
        async def event_generator():
            loop = asyncio.get_event_loop()

            def stream_gen():
                return llm.create_completion(**params, stream=True)

            gen = await loop.run_in_executor(executor, stream_gen)
            full_text = ""
            for chunk in gen:
                text = chunk["choices"][0]["text"]
                full_text += text
                yield {"event": "token", "data": json.dumps({"token": text, "model": model_id})}
            yield {"event": "done", "data": json.dumps({"response": full_text, "model": model_id})}

        return EventSourceResponse(event_generator())

    result = await _generate_sync(llm, params)
    text = result["choices"][0]["text"]
    return {"response": text, "model": model_id}


# ── Chat ────────────────────────────────────────────────────────────

@app.post("/inference/chat")
async def chat(req: ChatRequest):
    llm = _get_model(req.model)
    model_id = req.model or DEFAULT_MODEL

    prompt = _build_prompt_from_messages(req.messages)

    params = {
        "prompt": prompt,
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
        "top_p": req.top_p,
        "top_k": req.top_k,
        "repeat_penalty": req.repeat_penalty,
        "stop": req.stop or ["User:", "System:"],
        "echo": False,
    }

    if req.stream:
        async def event_generator():
            loop = asyncio.get_event_loop()

            def stream_gen():
                return llm.create_completion(**params, stream=True)

            gen = await loop.run_in_executor(executor, stream_gen)
            full_text = ""
            for chunk in gen:
                text = chunk["choices"][0]["text"]
                full_text += text
                yield {"event": "token", "data": json.dumps({"token": text, "model": model_id})}
            yield {"event": "done", "data": json.dumps({"response": full_text.strip(), "model": model_id})}

        return EventSourceResponse(event_generator())

    result = await _generate_sync(llm, params)
    text = result["choices"][0]["text"].strip()
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
    }


# ── Embeddings ──────────────────────────────────────────────────────

@app.post("/inference/embeddings")
async def embeddings(req: EmbeddingsRequest):
    llm = _get_model(req.model)
    model_id = req.model or DEFAULT_MODEL

    loop = asyncio.get_event_loop()
    embedding = await loop.run_in_executor(executor, lambda: llm.embed(req.input))

    return {
        "object": "list",
        "data": [
            {
                "object": "embedding",
                "index": 0,
                "embedding": embedding,
            }
        ],
        "model": model_id,
        "usage": {"prompt_tokens": len(req.input.split()), "total_tokens": len(req.input.split())},
    }


# ── Entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"[inference] Starting Kolibri Inference on {HOST}:{PORT}")
    print(f"[inference] Model dir: {MODEL_DIR}")
    print(f"[inference] Default model: {DEFAULT_MODEL}")
    print(f"[inference] GPU layers: {N_GPU_LAYERS}, CTX: {N_CTX}, Threads: {N_THREADS}")
    uvicorn.run(app, host=HOST, port=PORT)
