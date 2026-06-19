"""
FormulaLM API — HTTP wrapper for Kolibri evolutionary model.
Loads trained checkpoints from /srv/kolibri/repo/data/models/.
Falls back to ai_engine if no checkpoint found.

Run: python3 formulalm_api.py
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

BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn

app = FastAPI(title="FormulaLM API", version="2.0.0")

_model = None
_tokenizer = None


def _find_latest_checkpoint():
    models_dir = BACKEND_DIR.parent / "data" / "models"
    checkpoints = sorted(models_dir.glob("formulalm_trained_*.npz"), key=lambda p: p.stat().st_mtime, reverse=True)
    for cp in checkpoints:
        if "_final" in cp.name:
            return cp
    return checkpoints[0] if checkpoints else None


def get_model():
    global _model, _tokenizer
    if _model is not None:
        return _model, _tokenizer

    from service.formula_lm import FormulaLM
    from service.tokenizer import BPETokenizer

    checkpoint = _find_latest_checkpoint()
    if checkpoint:
        logger.info("Loading checkpoint: %s", checkpoint)
        _model = FormulaLM()
        _model.load(checkpoint)
        meta_path = checkpoint.with_suffix(".json")
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            _model.vocab_size = meta.get("vocab_size", _model.vocab_size)
            _model.embed_dim = meta.get("embed_dim", _model.embed_dim)
            logger.info("Model: vocab=%d embed=%d gen=%d fitness=%.4f",
                        _model.vocab_size, _model.embed_dim,
                        meta.get("generation", 0), meta.get("best_fitness", 0))
        _tokenizer = BPETokenizer(vocab_size=_model.vocab_size)
        corpus_dir = BACKEND_DIR.parent / "data" / "full_corpus.txt"
        if corpus_dir.exists():
            texts = [l.strip() for l in corpus_dir.read_text(errors="replace").splitlines() if len(l.strip()) > 20][:2000]
            _tokenizer.train(texts)
            logger.info("Tokenizer trained: vocab=%d", len(_tokenizer))
        return _model, _tokenizer

    logger.warning("No checkpoint found, trying ai_engine fallback")
    try:
        from service.ai_engine import get_engine as _get_engine
        engine = _get_engine()
        if getattr(engine, "_lm_trained", False):
            _model = engine._formula_lm
            _tokenizer = engine._bpe_tokenizer
            logger.info("Loaded from ai_engine")
            return _model, _tokenizer
    except Exception as e:
        logger.error("ai_engine fallback failed: %s", e)

    return None, None


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
    model, tok = get_model()
    if model is None:
        return JSONResponse(status_code=503, content={"status": "error", "error": "No model loaded"})
    return {"status": "ok", "lm_trained": True, "vocab": model.vocab_size, "model": "formulalm"}


@app.post("/api/v1/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    start = time.time()
    try:
        model, tok = get_model()
        if model is None:
            return GenerateResponse(text="[No model loaded]", tokens_generated=0, duration_ms=0)

        tokens = tok.encode(req.prompt) if tok else [0]
        if not tokens:
            tokens = [0]

        generated = []
        current = list(tokens)
        for _ in range(req.max_tokens):
            next_id = model.predict_next(current, req.temperature)
            if next_id is None or next_id == 0:
                break
            generated.append(next_id)
            current.append(next_id)

        text = tok.decode(generated) if tok and generated else ""
        ms = round((time.time() - start) * 1000, 1)
        return GenerateResponse(text=text, tokens_generated=len(generated), duration_ms=ms)
    except Exception as e:
        logger.error("generate error: %s", e, exc_info=True)
        return GenerateResponse(text=f"[Error: {e}]", tokens_generated=0, duration_ms=round((time.time()-start)*1000, 1))


@app.post("/api/v1/generate/stream")
async def generate_stream(req: GenerateRequest):
    async def event_stream():
        start = time.time()
        try:
            model, tok = get_model()
            if model is None:
                yield f"data: {json.dumps({'text': '[No model loaded]'})}\n\n"
                yield "data: [DONE]\n\n"
                return

            tokens = tok.encode(req.prompt) if tok else [0]
            if not tokens:
                tokens = [0]

            generated = []
            current = list(tokens)
            for _ in range(req.max_tokens):
                next_id = model.predict_next(current, req.temperature)
                if next_id is None or next_id == 0:
                    break
                generated.append(next_id)
                current.append(next_id)
                partial = tok.decode([next_id]) if tok else ""
                if partial:
                    yield f"data: {json.dumps({'text': partial})}\n\n"
                await asyncio.sleep(0)

            ms = round((time.time() - start) * 1000, 1)
            yield f"data: {json.dumps({'done': True, 'tokens_generated': len(generated), 'duration_ms': ms})}\n\n"
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
