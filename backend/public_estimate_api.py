"""Session-scoped read API for editable estimates and immutable PDFs."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from estimate_artifacts import EstimateArtifactError, get_estimate_artifact_store
from execution_api import get_learning_boundary
from formulalm_boundary import FormulaLMConflictError, FormulaLMPolicyError
from public_responses_api import require_public_response_session


router = APIRouter(tags=["Kolibri Public Estimate Artifacts V1"])


class EstimateReviewFeedback(BaseModel):
    """Explicit reviewer signal; never a production-weight mutation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["accept", "reject", "correct"]
    base_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=4_000)
    corrections: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=300)

    @model_validator(mode="after")
    def validate_feedback(self) -> "EstimateReviewFeedback":
        if self.action in {"reject", "correct"} and not (self.reason or self.corrections):
            raise ValueError("reject/correct feedback requires a reason or corrections")
        encoded = json.dumps(self.corrections, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 64 * 1024:
            raise ValueError("estimate corrections exceed 64 KiB")
        return self


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@router.get("/v1/public/estimates/{estimate_id}")
def get_public_estimate(estimate_id: str, request: Request):
    session = require_public_response_session(request)
    estimate = get_estimate_artifact_store().get_estimate(session["id"], estimate_id)
    if estimate is None:
        raise HTTPException(status_code=404, detail="estimate_not_found")
    return estimate


@router.get("/v1/public/estimates/{estimate_id}/versions")
def list_public_estimate_versions(estimate_id: str, request: Request):
    session = require_public_response_session(request)
    versions = get_estimate_artifact_store().list_versions(session["id"], estimate_id)
    if versions is None:
        raise HTTPException(status_code=404, detail="estimate_not_found")
    return {
        "object": "list",
        "data": versions,
        "has_more": False,
    }


@router.post("/v1/public/estimates/{estimate_id}/feedback")
def review_public_estimate(
    estimate_id: str,
    body: EstimateReviewFeedback,
    request: Request,
):
    """Queue a sanitized correction/accept/reject trace for FormulaLM.

    The review is version-bound and session-scoped.  FormulaLM's scanner owns
    secret/PII removal, the request path creates no model candidate, and no
    production weights are modified synchronously.
    """

    session = require_public_response_session(request)
    estimate = get_estimate_artifact_store().get_estimate(session["id"], estimate_id)
    if estimate is None:
        raise HTTPException(status_code=404, detail="estimate_not_found")
    if estimate["version"] != body.base_version:
        raise HTTPException(status_code=409, detail="estimate_version_conflict")
    session_sha = _sha256(str(session["id"]))
    feedback_id = f"estimate-feedback:{estimate_id}:v{body.base_version}:{body.idempotency_key}"
    trace = {
        "schema_version": "kolibri.estimate-review-feedback.v1",
        "estimate": {
            "estimate_id": estimate_id,
            "version": estimate["version"],
            "spec_sha256": estimate["spec_sha256"],
            "calculation_sha256": estimate["calculation_sha256"],
        },
        "review": {
            "action": body.action,
            "reason": body.reason,
            "corrections": body.corrections,
        },
        "safety": {
            "candidate_only": True,
            "request_path_training": False,
            "production_weight_mutation": False,
        },
    }
    artifact_hashes = {
        f"sha256:{estimate['spec_sha256']}",
        f"sha256:{estimate['calculation_sha256']}",
        *(
            f"sha256:{artifact['content_sha256']}"
            for artifact in estimate.get("artifacts", [])
            if isinstance(artifact, dict) and artifact.get("content_sha256")
        ),
    }
    try:
        intake = get_learning_boundary().enqueue_trace(
            idempotency_key=body.idempotency_key,
            source_trace_id=feedback_id,
            source_response_id=estimate["response_id"],
            capability="estimate.review-correction",
            trace=trace,
            provenance={
                "actor": "public-estimate-reviewer",
                "principal": f"public-session:{session_sha[:16]}",
                "policy_version": "kolibri.formulalm-estimate-feedback-policy.v1",
                "response_id": estimate["response_id"],
            },
            policy={
                "consent": "explicit",
                "license": "permitted",
                "retention_class": "training-approved",
                "data_classification": "internal",
                "capability": "estimate.review-correction",
                "source_uri": None,
            },
            quality={
                "response_status": "completed",
                "quality_verdict": "passed",
                "verifier_verdict": "passed",
                "review_action": body.action,
                "credit_assignment": {
                    "provider_draft": 1.0 if body.action == "accept" else 0.0,
                    "review_correction": 1.0 if body.action in {"reject", "correct"} else 0.0,
                },
            },
            artifact_hashes=sorted(artifact_hashes),
        )
    except FormulaLMConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from None
    except FormulaLMPolicyError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from None
    except Exception:
        raise HTTPException(status_code=503, detail="learning_boundary_unavailable") from None
    return {
        "schema_version": "kolibri.estimate-review-feedback-receipt.v1",
        "estimate_id": estimate_id,
        "estimate_version": estimate["version"],
        "action": body.action,
        "status": intake["status"],
        "rejection_code": intake.get("rejection_code"),
        "sanitization": intake["sanitization"],
        "candidate_only": True,
        "async_queue": intake["status"] == "queued",
        "production_weight_mutation": False,
    }


@router.get("/v1/public/estimate-artifacts/{artifact_id}/content")
def get_public_estimate_artifact(
    artifact_id: str,
    request: Request,
    download: bool = False,
):
    session = require_public_response_session(request)
    try:
        resolved = get_estimate_artifact_store().artifact_content(session["id"], artifact_id)
    except EstimateArtifactError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    if resolved is None:
        raise HTTPException(status_code=404, detail="estimate_artifact_not_found")
    artifact, content = resolved
    disposition = "attachment" if download else "inline"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "Cross-Origin-Resource-Policy": "same-origin",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "SAMEORIGIN",
            "Content-Security-Policy": "frame-ancestors 'self'",
            "X-Content-SHA256": artifact["content_sha256"],
            "X-Kolibri-Artifact-Binding": artifact["evidence_binding_sha256"],
            "Content-Disposition": f'{disposition}; filename="{artifact["name"]}"',
        },
    )
