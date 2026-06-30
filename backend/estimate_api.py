from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from estimate_engine import (
    CANONICAL_ESTIMATE_SCHEMA_VERSION,
    Estimate,
    EstimateSection,
    canonical_hash,
    canonical_json,
    create_estimate_from_prompt,
    estimate_canonical_payload,
    recalculate_estimate,
)

router = APIRouter()

ClaimBasis = Literal["none", "manual", "internal_benchmark", "external_audit"]
RESTRICTED_ACCURACY_CLAIM_PERCENT = Decimal("98.00")
MIN_EXTERNAL_AUDIT_SAMPLE_SIZE = 100


class AccuracyClaim(BaseModel):
    percent: Decimal = Field(..., ge=Decimal("0.00"), le=Decimal("100.00"))
    basis: ClaimBasis = "none"
    sample_size: int = Field(default=0, ge=0)
    evidence_reference: str | None = None

    @model_validator(mode="after")
    def constrain_high_accuracy_claims(self) -> "AccuracyClaim":
        has_external_proof = (
            self.basis == "external_audit"
            and self.sample_size >= MIN_EXTERNAL_AUDIT_SAMPLE_SIZE
            and bool((self.evidence_reference or "").strip())
        )
        if self.percent >= RESTRICTED_ACCURACY_CLAIM_PERCENT and not has_external_proof:
            raise ValueError(
                ">=98% accuracy claims require external_audit basis, "
                "sample_size >= 100, and evidence_reference"
            )
        return self


class EstimateGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=3)
    client_name: str = Field(default="Клиент", min_length=1)
    object_address: str = Field(default="Адрес объекта не указан", min_length=1)
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    claim: AccuracyClaim | None = None

    @field_validator("prompt", "client_name", "object_address", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class EstimateEditPatch(BaseModel):
    title: str | None = None
    client_name: str | None = None
    object_address: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    sections: list[EstimateSection] | None = None
    overhead_rate: Decimal | None = None
    tax_rate: Decimal | None = None

    @field_validator("title", "client_name", "object_address", mode="before")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_optional_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else value


class EstimateEditRequest(BaseModel):
    estimate: Estimate
    expected_canonical_hash: str
    edits: EstimateEditPatch = Field(default_factory=EstimateEditPatch)
    claim: AccuracyClaim | None = None

    @field_validator("expected_canonical_hash")
    @classmethod
    def strip_expected_hash(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


def claim_constraints() -> dict[str, Any]:
    return {
        "deterministic_scope": "recalculation, rounding, canonical JSON, hash, and edit conflict checks",
        "not_a_price_accuracy_warranty": True,
        "restricted_accuracy_claim_min_percent": str(RESTRICTED_ACCURACY_CLAIM_PERCENT),
        "restricted_claim_rule": (
            ">=98% accuracy claims require external_audit basis, "
            "sample_size >= 100, and evidence_reference"
        ),
    }


def contract_descriptor() -> dict[str, Any]:
    return {
        "schema_version": CANONICAL_ESTIMATE_SCHEMA_VERSION,
        "endpoints": {
            "generate": "POST /api/estimates/generate",
            "edit": "POST /api/estimates/edit",
            "contract": "GET /api/estimates/contract",
        },
        "input_schemas": {
            "generate": EstimateGenerateRequest.model_json_schema(),
            "edit": EstimateEditRequest.model_json_schema(),
        },
        "claim_constraints": claim_constraints(),
    }


def estimate_response(estimate: Estimate, **extra: Any) -> dict[str, Any]:
    payload = estimate_canonical_payload(estimate)
    return {
        "estimate": estimate.model_dump(mode="json"),
        "canonical_json": canonical_json(payload),
        "canonical_hash": canonical_hash(payload),
        "contract": {
            "schema_version": CANONICAL_ESTIMATE_SCHEMA_VERSION,
            "claim_constraints": claim_constraints(),
        },
        **extra,
    }


@router.get("/api/estimates/contract")
async def get_estimate_contract() -> dict[str, Any]:
    return contract_descriptor()


@router.post("/api/estimates/generate")
async def generate_estimate(request: EstimateGenerateRequest) -> dict[str, Any]:
    estimate = create_estimate_from_prompt(
        request.prompt,
        client_name=request.client_name,
        object_address=request.object_address,
        currency=request.currency,
    )
    return estimate_response(estimate, edit_applied=False)


@router.post("/api/estimates/edit")
async def edit_estimate(request: EstimateEditRequest) -> dict[str, Any]:
    current = recalculate_estimate(request.estimate)
    current_payload = estimate_canonical_payload(current)
    current_hash = canonical_hash(current_payload)
    if current_hash != request.expected_canonical_hash:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "canonical_hash_conflict",
                "expected_canonical_hash": request.expected_canonical_hash,
                "actual_canonical_hash": current_hash,
            },
        )

    edited = current.model_copy(deep=True)
    for field_name in request.edits.model_fields_set:
        value = getattr(request.edits, field_name)
        if value is not None:
            setattr(edited, field_name, value)
    edited = recalculate_estimate(edited)
    return estimate_response(
        edited,
        previous_canonical_hash=current_hash,
        edit_applied=bool(request.edits.model_fields_set),
    )
