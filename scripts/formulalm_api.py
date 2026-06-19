"""
FormulaLM API — thin HTTP wrapper around Kolibri numeric engine.
Deploy to Home server (10.99.0.1). Exposes /api/v1/generate endpoints
for the main Kolibri backend to consume.

Run: python3 formulalm_api.py
Or via systemd: kolibri-formulalm.service
"""

import os
import sys
import json
import time
import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("formulalm-api")

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn

app = FastAPI(title="FormulaLM API", version="1.0.0")

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        try:
            from service.ai_engine import get_engine as _get_engine
            _engine = _get_engine()
            logger.info("FormulaLM engine loaded")
        except Exception as e:
            logger.error("Failed to load engine: %s", e)
            raise
    return _engine


class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 256
    temperature: float = 0.7


class GenerateResponse(BaseModel):
    text: str
    tokens_generated: int
    duration_ms: float
    model: str = "formulalm"


@app.get("/api/v1/health")
async def health():
    try:
        engine = get_engine()
        has_lm = getattr(engine, "_lm_trained", False)
        return {"status": "ok", "lm_trained": has_lm, "model": "formulalm"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "error", "error": str(e)})


@app.post("/api/v1/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    start = time.time()
    try:
        engine = get_engine()

        if not getattr(engine, "_lm_trained", False):
            return GenerateResponse(
                text="[FormulaLM not trained yet]",
                tokens_generated=0,
                duration_ms=0,
            )

        from service.tokenizer import encode as bpe_encode
        from service.tokenizer import decode as bpe_decode

        tokens = bpe_encode(req.prompt)
        if not tokens:
            tokens = [0]

        generated = []
        current_ids = list(tokens)

        for _ in range(req.max_tokens):
            next_id = engine._lm_predict_next(current_ids, req.temperature)
            if next_id is None or next_id == 0:
                break
            generated.append(next_id)
            current_ids.append(next_id)

        text = bpe_decode(generated) if generated else ""
        duration_ms = (time.time() - start) * 1000

        return GenerateResponse(
            text=text,
            tokens_generated=len(generated),
            duration_ms=round(duration_ms, 1),
        )
    except Exception as e:
        logger.error("generate error: %s", e, exc_info=True)
        duration_ms = (time.time() - start) * 1000
        return GenerateResponse(
            text=f"[Error: {e}]",
            tokens_generated=0,
            duration_ms=round(duration_ms, 1),
        )


@app.post("/api/v1/generate/stream")
async def generate_stream(req: GenerateRequest):
    async def event_stream():
        start = time.time()
        try:
            engine = get_engine()

            if not getattr(engine, "_lm_trained", False):
                yield f"data: {json.dumps({'text': '[FormulaLM not trained yet]'})}\n\n"
                yield "data: [DONE]\n\n"
                return

            from service.tokenizer import encode as bpe_encode, decode as bpe_decode

            tokens = bpe_encode(req.prompt)
            if not tokens:
                tokens = [0]

            generated = []
            current_ids = list(tokens)

            for _ in range(req.max_tokens):
                next_id = engine._lm_predict_next(current_ids, req.temperature)
                if next_id is None or next_id == 0:
                    break
                generated.append(next_id)
                current_ids.append(next_id)

                partial = bpe_decode(generated[-1:]) if generated else ""
                if partial:
                    yield f"data: {json.dumps({'text': partial})}\n\n"
                await asyncio.sleep(0)

            duration_ms = (time.time() - start) * 1000
            yield f"data: {json.dumps({'done': True, 'tokens_generated': len(generated), 'duration_ms': round(duration_ms, 1)})}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error("stream error: %s", e, exc_info=True)
            yield f"data: {json.dumps({'text': f'[Error: {e}]'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    port = int(os.getenv("FORMULALM_PORT", "8004"))
    host = os.getenv("FORMULALM_HOST", "0.0.0.0")
    logger.info("Starting FormulaLM API on %s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")
