"""Canonical owner scope for browser and OpenAI-compatible public requests.

Artifacts and durable responses must use the same principal derivation.  A
browser request is bound to its signed Shell session; an OpenAI-compatible
request is bound to the exact API key that authenticated it.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import os

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.browser_session import ProjectPrincipal, resolve_optional_project_principal
from app.database import get_db
from app.models import PublicApiKeyDB


def _configured_key_hashes() -> list[str]:
    return [
        item.strip().lower()
        for item in os.getenv("KOLIBRI_PUBLIC_API_KEY_SHA256", "").split(",")
        if item.strip()
    ]


def _api_key_scope(
    request: Request,
    db: Session,
    *,
    required: bool,
    touch: bool,
) -> str | None:
    configured = _configured_key_hashes()
    database_configured = db.query(PublicApiKeyDB.id).first() is not None
    if not configured and not database_configured:
        if required:
            raise HTTPException(status_code=503, detail={"code": "public_api_not_configured"})
        return None

    authorization = request.headers.get("Authorization", "")
    token = authorization[7:] if authorization.startswith("Bearer ") else ""
    if not token:
        if required:
            raise HTTPException(status_code=401, detail={"code": "invalid_api_key"})
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    env_match = any(hmac.compare_digest(digest, expected) for expected in configured)
    key = db.query(PublicApiKeyDB).filter(PublicApiKeyDB.secret_hash == digest).first()
    database_match = bool(
        key is not None
        and key.revoked_at is None
        and hmac.compare_digest(str(key.secret_hash), digest)
    )
    if not env_match and not database_match:
        if required:
            raise HTTPException(status_code=401, detail={"code": "invalid_api_key"})
        return None

    if database_match:
        if touch:
            key.last_used_at = datetime.now(timezone.utc)
            db.commit()
            from app.capability_runtime import record_capability_invocation

            record_capability_invocation(
                "developer.api_keys",
                succeeded=True,
                provider="kolibri-api-key-auth",
                evidence_id=str(key.id),
            )
        return f"api-key:{key.id}"
    return f"api-key-sha256:{digest}"


async def authorize_public_scope(
    request: Request,
    db: Session = Depends(get_db),
    browser_principal: ProjectPrincipal | None = Depends(resolve_optional_project_principal),
) -> str:
    """Require and return the canonical owner scope for one public request."""

    if request.url.path.startswith("/api/v1/"):
        if browser_principal is None:
            raise HTTPException(
                status_code=428,
                detail={
                    "code": "session_bootstrap_required",
                    "message": "Call POST /api/v1/shell/bootstrap before using this endpoint",
                },
            )
        scope = browser_principal.scope_id
    else:
        scope = _api_key_scope(request, db, required=True, touch=True)
        assert scope is not None
    request.state.kolibri_response_scope = scope
    return scope


async def resolve_optional_public_scope(
    request: Request,
    db: Session = Depends(get_db),
    browser_principal: ProjectPrincipal | None = Depends(resolve_optional_project_principal),
) -> str | None:
    """Resolve artifact scope without turning an unknown artifact into auth leakage."""

    if browser_principal is not None:
        return browser_principal.scope_id
    # Artifact URLs are canonicalised under /api/v1 even when the producer
    # was an OpenAI-compatible /v1 request.  A valid Bearer key must therefore
    # be accepted on those retrieval URLs as the same owner scope.
    if request.headers.get("Authorization", "").startswith("Bearer "):
        return _api_key_scope(request, db, required=False, touch=False)
    if request.url.path.startswith("/api/v1/"):
        return None
    return _api_key_scope(request, db, required=False, touch=False)
