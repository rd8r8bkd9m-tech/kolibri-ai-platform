"""Kolibri AI Unified Pipeline — RAG + Agent + Inference chain.

Routes user requests through the appropriate service chain:
- chat: direct AI inference via existing provider
- rag: RAG search → context-augmented generation
- agent: Agent planning + tool execution
- auto: heuristic intent detection → best route
"""

import asyncio
import time
from typing import Optional, List, Dict, Any
from enum import Enum

import httpx
from pydantic import BaseModel

from config import RAG_SERVICE_URL, AGENT_SERVICE_URL, INFERENCE_SERVICE_URL
from logging_config import get_logger

logger = get_logger("pipeline")


# ── Service endpoints ──────────────────────────────────────────────

RAG_URL = RAG_SERVICE_URL
AGENT_URL = AGENT_SERVICE_URL
INFERENCE_URL = INFERENCE_SERVICE_URL

REQUEST_TIMEOUT = 60.0
MAX_RETRIES = 3
BASE_DELAY = 1.0


# ── Retry helper ──────────────────────────────────────────────────

async def _retry_request(coro_factory, *, retries: int = MAX_RETRIES, base_delay: float = BASE_DELAY):
    """Retry an async callable with exponential backoff.

    coro_factory: a zero-arg callable that returns a fresh coroutine each time.
    Returns the result on success; raises the last exception after exhausting retries.
    """
    last_exc = None
    for attempt in range(retries):
        try:
            return await coro_factory()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout) as exc:
            last_exc = exc
            if attempt < retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    f"Request failed (attempt {attempt + 1}/{retries}), retrying in {delay:.1f}s: {exc}"
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"Request failed after {retries} attempts: {exc}")
    raise last_exc


# ── Models ─────────────────────────────────────────────────────────

class Intent(str, Enum):
    CHAT = "chat"
    RAG = "rag"
    AGENT = "agent"
    AUTO = "auto"


class PipelineRequest(BaseModel):
    message: str
    intent: Optional[Intent] = Intent.AUTO
    conversation: Optional[List[Dict[str, str]]] = None
    top_k: Optional[int] = 5
    max_tokens: Optional[int] = 2048
    temperature: Optional[float] = 0.7
    system_prompt: Optional[str] = None
    stream: Optional[bool] = False


class PipelineResponse(BaseModel):
    response: str
    intent_used: str
    sources: Optional[List[Dict[str, Any]]] = None
    tools_used: Optional[List[Dict[str, Any]]] = None
    model: Optional[str] = None
    latency_ms: int = 0
    pipeline: List[str] = []


# ── Intent detection ───────────────────────────────────────────────

AGENT_KEYWORDS = [
    "выполни", "сделай", "запусти", "вычисли", "посчитай",
    "execute", "run", "calculate", "compute", "deploy",
    "найди файл", "прочитай файл", "создай файл",
    "установи", "настрой", "проверь сервер",
    "скрипт", "команда", "терминал", "shell",
]

RAG_KEYWORDS = [
    "документ", "смета", "расценк", "цена на", "стоимость",
    "какие материалы", "нормы", "снип", "гост", "спец",
    "по документам", "в базе", "найди в документации",
    "согласно", "по данным", "из файла",
]


def detect_intent(message: str) -> Intent:
    """Heuristic intent detection from user message."""
    lower = message.lower()

    agent_score = sum(1 for kw in AGENT_KEYWORDS if kw in lower)
    rag_score = sum(1 for kw in RAG_KEYWORDS if kw in lower)

    if agent_score > rag_score and agent_score > 0:
        return Intent.AGENT
    if rag_score > 0:
        return Intent.RAG
    return Intent.CHAT


# ── Service callers ────────────────────────────────────────────────

async def call_rag_search(query: str, top_k: int = 5) -> Dict[str, Any]:
    """Search RAG engine for relevant documents."""
    async def _do():
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(
                f"{RAG_URL}/rag/search",
                json={"query": query, "top_k": top_k},
            )
            resp.raise_for_status()
            return resp.json()
    return await _retry_request(_do)


async def call_rag_health() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{RAG_URL}/rag/health")
            return resp.status_code == 200
    except Exception:
        return False


async def call_inference_generate(
    prompt: str,
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> Dict[str, Any]:
    """Generate text via Inference service."""
    async def _do():
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(
                f"{INFERENCE_URL}/inference/generate",
                json={
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            resp.raise_for_status()
            return resp.json()
    return await _retry_request(_do)


async def call_inference_health() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{INFERENCE_URL}/inference/health")
            return resp.status_code == 200
    except Exception:
        return False


async def call_agent_chat(
    message: str,
    conversation: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Send message to Agent for planning + tool execution."""
    async def _do():
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(
                f"{AGENT_URL}/agent/chat",
                json={
                    "message": message,
                    "conversation": conversation or [],
                    "stream": False,
                },
            )
            resp.raise_for_status()
            return resp.json()
    return await _retry_request(_do)


async def call_agent_health() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{AGENT_URL}/agent/health")
            return resp.status_code == 200
    except Exception:
        return False


# ── Pipeline chains ────────────────────────────────────────────────

async def chain_rag(
    message: str,
    top_k: int = 5,
    max_tokens: int = 2048,
    temperature: float = 0.7,
    system_prompt: Optional[str] = None,
) -> PipelineResponse:
    """RAG chain: search documents → build context → generate answer."""
    start = time.time()
    pipeline_steps = ["rag_search"]

    rag_result = await call_rag_search(message, top_k)
    sources = rag_result.get("results", [])

    context_parts = [s["content"] for s in sources if s.get("content")]
    context = "\n\n---\n\n".join(context_parts) if context_parts else "No relevant documents found."

    augmented_prompt = (
        f"Context from knowledge base:\n\n{context}\n\n"
        f"---\n\nUser question: {message}\n\n"
        f"Answer based on the context above. If the context doesn't contain relevant information, say so."
    )

    pipeline_steps.append("inference_generate")
    try:
        gen_result = await call_inference_generate(augmented_prompt, max_tokens, temperature)
        answer = gen_result.get("response", "")
        model = gen_result.get("model", "inference")
        if not answer.strip():
            pipeline_steps.append("fallback_direct")
            answer = "Based on the knowledge base:\n\n" + "\n\n".join(
                f"**[{i+1}]** {s['content']}" for i, s in enumerate(sources[:3])
            )
            model = "rag-direct"
    except Exception:
        pipeline_steps.append("fallback_direct")
        answer = "Based on the knowledge base:\n\n" + "\n\n".join(
            f"**[{i+1}]** {s['content']}" for i, s in enumerate(sources[:3])
        )
        model = "rag-direct"

    latency = int((time.time() - start) * 1000)
    return PipelineResponse(
        response=answer,
        intent_used="rag",
        sources=[
            {"content": s["content"], "metadata": s.get("metadata", {}), "distance": s.get("distance")}
            for s in sources
        ],
        model=model,
        latency_ms=latency,
        pipeline=pipeline_steps,
    )


async def chain_agent(
    message: str,
    conversation: Optional[List[Dict[str, str]]] = None,
) -> PipelineResponse:
    """Agent chain: send to agent for planning + tool execution."""
    start = time.time()
    pipeline_steps = ["agent_chat"]

    try:
        result = await call_agent_chat(message, conversation)
        answer = result.get("response", "")
        tools_used = result.get("tools_used", [])
        pipeline_steps.append("agent_complete")
    except Exception as e:
        pipeline_steps.append("agent_fallback")
        answer = f"Agent unavailable: {e}. Falling back to direct response."
        tools_used = []

    latency = int((time.time() - start) * 1000)
    return PipelineResponse(
        response=answer,
        intent_used="agent",
        tools_used=tools_used,
        model="agent",
        latency_ms=latency,
        pipeline=pipeline_steps,
    )


async def chain_rag_agent(
    message: str,
    top_k: int = 5,
    conversation: Optional[List[Dict[str, str]]] = None,
) -> PipelineResponse:
    """Combined chain: RAG search → enrich context → Agent execution."""
    start = time.time()
    pipeline_steps = ["rag_search"]

    rag_result = await call_rag_search(message, top_k)
    sources = rag_result.get("results", [])
    context_parts = [s["content"] for s in sources if s.get("content")]
    context = "\n\n".join(context_parts) if context_parts else ""

    enriched_message = message
    if context:
        enriched_message = f"Context from knowledge base:\n{context}\n\nUser request: {message}"

    pipeline_steps.append("agent_chat")
    try:
        result = await call_agent_chat(enriched_message, conversation)
        answer = result.get("response", "")
        tools_used = result.get("tools_used", [])
        pipeline_steps.append("agent_complete")
    except Exception as e:
        pipeline_steps.append("agent_fallback")
        answer = f"Agent unavailable: {e}. RAG context:\n\n" + "\n\n".join(
            f"- {s['content'][:200]}" for s in sources[:3]
        )
        tools_used = []

    latency = int((time.time() - start) * 1000)
    return PipelineResponse(
        response=answer,
        intent_used="rag+agent",
        sources=[
            {"content": s["content"], "metadata": s.get("metadata", {}), "distance": s.get("distance")}
            for s in sources
        ],
        tools_used=tools_used,
        model="agent",
        latency_ms=latency,
        pipeline=pipeline_steps,
    )


async def chain_chat(
    message: str,
    conversation: Optional[List[Dict[str, str]]] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    system_prompt: Optional[str] = None,
) -> PipelineResponse:
    """Direct chat chain: forward to inference or return placeholder."""
    start = time.time()
    pipeline_steps = ["inference_generate"]

    prompt_parts = []
    if system_prompt:
        prompt_parts.append(system_prompt)
    if conversation:
        for msg in conversation:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            prompt_parts.append(f"{role.capitalize()}: {content}")
    prompt_parts.append(f"User: {message}")
    prompt_parts.append("Assistant:")
    full_prompt = "\n".join(prompt_parts)

    try:
        gen_result = await call_inference_generate(full_prompt, max_tokens, temperature)
        answer = gen_result.get("response", "")
        model = gen_result.get("model", "inference")
        if not answer.strip():
            pipeline_steps.append("fallback")
            answer = f"Inference returned empty response. Model: {model}"
    except Exception as e:
        pipeline_steps.append("fallback")
        answer = f"Inference service unavailable: {e}"
        model = "none"

    latency = int((time.time() - start) * 1000)
    return PipelineResponse(
        response=answer,
        intent_used="chat",
        model=model,
        latency_ms=latency,
        pipeline=pipeline_steps,
    )


# ── Main pipeline entry ───────────────────────────────────────────

async def run_pipeline(req: PipelineRequest) -> PipelineResponse:
    """Main pipeline dispatcher."""
    requested_intent = req.intent or Intent.AUTO
    intent = detect_intent(req.message) if requested_intent == Intent.AUTO else requested_intent

    if intent == Intent.RAG:
        return await chain_rag(
            message=req.message,
            top_k=req.top_k or 5,
            max_tokens=req.max_tokens or 2048,
            temperature=req.temperature or 0.7,
            system_prompt=req.system_prompt,
        )
    elif intent == Intent.AGENT:
        return await chain_agent(
            message=req.message,
            conversation=req.conversation,
        )
    elif requested_intent == Intent.AUTO:
        rag_ok = await call_rag_health()
        agent_ok = await call_agent_health()
        if rag_ok and agent_ok:
            return await chain_rag_agent(
                message=req.message,
                top_k=req.top_k or 5,
                conversation=req.conversation,
            )
        elif rag_ok:
            return await chain_rag(
                message=req.message,
                top_k=req.top_k or 5,
                max_tokens=req.max_tokens or 2048,
                temperature=req.temperature or 0.7,
                system_prompt=req.system_prompt,
            )
        else:
            return await chain_chat(
                message=req.message,
                conversation=req.conversation,
                temperature=req.temperature or 0.7,
                max_tokens=req.max_tokens or 2048,
                system_prompt=req.system_prompt,
            )
    else:
        return await chain_chat(
            message=req.message,
            conversation=req.conversation,
            temperature=req.temperature or 0.7,
            max_tokens=req.max_tokens or 2048,
            system_prompt=req.system_prompt,
        )


# ── Health aggregator ─────────────────────────────────────────────

async def pipeline_health() -> Dict[str, Any]:
    """Check health of all pipeline services."""
    rag_ok, agent_ok, inference_ok = await asyncio.gather(
        call_rag_health(),
        call_agent_health(),
        call_inference_health(),
    )
    return {
        "pipeline": "ok",
        "services": {
            "rag": {"url": RAG_URL, "status": "ok" if rag_ok else "down"},
            "agent": {"url": AGENT_URL, "status": "ok" if agent_ok else "down"},
            "inference": {"url": INFERENCE_URL, "status": "ok" if inference_ok else "down"},
        },
    }
