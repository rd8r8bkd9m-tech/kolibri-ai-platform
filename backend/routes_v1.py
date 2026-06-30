from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
import json
from pydantic import BaseModel, Field

from estimate_engine import (
    ESTIMATE_CLAIM_CONSTRAINTS,
    ESTIMATE_CONTRACT_SCHEMA_VERSION,
    Estimate,
    EstimateClaimConstraints,
    calculation_hash,
    canonical_estimate_hash,
    canonical_estimate_json,
    create_estimate_from_prompt,
    normalize_estimate_payload,
    recalculate_estimate,
)

router = APIRouter()

KOLIBRI_SYSTEM_PROMPT = (
    "Ты — Kolibri AI, большая языковая модель. " +
    "Отвечай на языке пользователя. Не используй эмодзи."
)


class EstimateGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    client_name: str = "Клиент"
    object_address: str | None = None
    currency: str | None = None
    overhead_rate: Decimal | None = Field(default=None, ge=Decimal("0.00"))
    tax_rate: Decimal | None = Field(default=None, ge=Decimal("0.00"))


class EstimateEditRequest(BaseModel):
    estimate: Estimate
    base_canonical_hash: str | None = Field(default=None, min_length=64, max_length=64)


class EstimateEditLineage(BaseModel):
    base_canonical_hash: str | None = None
    hash_changed: bool | None = None


class EstimateContractResponse(BaseModel):
    schema_version: str
    estimate: Estimate
    canonical_json: str
    canonical_hash: str
    calculation_hash: str
    claim_constraints: EstimateClaimConstraints
    edit: EstimateEditLineage | None = None


def _contract_response(estimate: Estimate, *, base_canonical_hash: str | None = None) -> EstimateContractResponse:
    normalized = recalculate_estimate(estimate)
    current_hash = canonical_estimate_hash(normalized)
    edit = None
    if base_canonical_hash is not None:
        edit = EstimateEditLineage(base_canonical_hash=base_canonical_hash, hash_changed=base_canonical_hash != current_hash)
    return EstimateContractResponse(
        schema_version=ESTIMATE_CONTRACT_SCHEMA_VERSION,
        estimate=normalized,
        canonical_json=canonical_estimate_json(normalized),
        canonical_hash=current_hash,
        calculation_hash=calculation_hash(normalized),
        claim_constraints=ESTIMATE_CLAIM_CONSTRAINTS.model_copy(deep=True),
        edit=edit,
    )

@router.get("/api/v1/ai/models")
async def get_models():
    return {"models": [{"name": "mimo-auto", "description": "Auto mode"}], "system_prompt": KOLIBRI_SYSTEM_PROMPT}

@router.get("/api/v1/model/stats")
async def get_model_stats():
    return {"status": "ok", "models": ["mimo-auto"], "active": "mimo-auto"}


@router.get("/api/v1/estimates/contract")
async def estimate_contract():
    return {
        "schema_version": ESTIMATE_CONTRACT_SCHEMA_VERSION,
        "generate_request_schema": EstimateGenerateRequest.model_json_schema(),
        "edit_request_schema": EstimateEditRequest.model_json_schema(),
        "response_schema": EstimateContractResponse.model_json_schema(),
        "claim_constraints": ESTIMATE_CLAIM_CONSTRAINTS.model_dump(mode="json"),
        "canonical_hash": {
            "algorithm": "sha256",
            "json": "UTF-8, sort_keys=true, separators=(',', ':'), ensure_ascii=false",
            "volatile_fields_excluded": [
                "estimate.created_at",
                "estimate.updated_at",
                "estimate.sections[].items[].provenance.captured_at",
                "estimate.calculation_audit[].calculated_at",
            ],
        },
    }


@router.post("/api/v1/estimates/generate", response_model=EstimateContractResponse)
async def generate_estimate(request: EstimateGenerateRequest):
    estimate = create_estimate_from_prompt(request.prompt, client_name=request.client_name)
    if request.object_address is not None:
        estimate.object_address = request.object_address
    if request.currency is not None:
        estimate.currency = request.currency
    if request.overhead_rate is not None:
        estimate.overhead_rate = request.overhead_rate
    if request.tax_rate is not None:
        estimate.tax_rate = request.tax_rate
    return _contract_response(estimate)


@router.post("/api/v1/estimates/recalculate", response_model=EstimateContractResponse)
async def recalculate_edited_estimate(request: EstimateEditRequest):
    estimate = normalize_estimate_payload(request.estimate.model_dump(mode="json"))
    return _contract_response(estimate, base_canonical_hash=request.base_canonical_hash)

@router.post("/api/v1/ai/chat")
async def chat(request: Request):
    from providers import AIProviderManager
    manager = AIProviderManager()
    body = await request.json()
    messages = body.get("messages", [])
    result = await manager.generate(messages=messages, provider="mimo")
    return result

@router.post("/api/v1/ai/chat/stream")
async def chat_stream(request: Request):
    from providers import AIProviderManager
    manager = AIProviderManager()
    body = await request.json()
    messages = body.get("messages", [])
    result = await manager.generate(messages=messages, provider="mimo")
    async def generate():
        yield f"data: {json.dumps(result)}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")

@router.post("/api/v1/ai/imagine")
async def imagine():
    return {"status": "ok", "message": "Image generation coming soon"}

@router.post("/api/v1/ai/vision/analyze")
async def vision():
    return {"status": "ok", "message": "Vision analysis coming soon"}

@router.post("/api/v1/ai/demo/learn/text")
async def learn():
    return {"status": "ok", "message": "Learning coming soon"}

@router.get("/api/v1/ai/quality/benchmark/history")
async def benchmark():
    return {"history": []}

@router.get("/api/v1/swarm/runtime/status")
async def swarm_status():
    return {"status": "active", "nodes": 4}

@router.get("/api/v1/ai/training/queue/status")
async def training_status():
    return {"queue": []}

@router.post("/api/v1/swarm/runtime/start")
async def swarm_start():
    return {"status": "started"}

@router.post("/api/v1/swarm/runtime/refresh")
async def swarm_refresh():
    return {"status": "refreshed"}

@router.post("/api/v1/swarm/runtime/run")
async def swarm_run():
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/ingest/text")
async def ingest_text():
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/ingest/url")
async def ingest_url():
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/kpack/export")
async def kpack_export():
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/kpack/import")
async def kpack_import():
    return {"status": "ok"}
