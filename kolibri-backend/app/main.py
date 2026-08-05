"""Kolibri API — FastAPI backend for estimates, documents, PDF, agents, nodes, tasks."""
from dotenv import load_dotenv
from pathlib import Path

env_from_backend = Path(__file__).resolve().parents[1] / ".env"
env_from_repo_root = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(env_from_repo_root)
load_dotenv(env_from_backend)
load_dotenv()

import os
import asyncio
import json
import uuid
import base64
import hashlib
import re
import httpx
from urllib.parse import urlsplit
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Query, Depends, Header, Request, Cookie
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.calculator import (
    Estimate as CalcEstimate, EstimateSection as CalcSection,
    EstimatePosition as CalcPosition, EstimateStatus,
    calculate_estimate, validate_estimate, format_currency,
    estimate_to_dict, export_to_csv, export_to_json,
)
from app.pdf_generator import generate_estimate_pdf, generate_document_pdf
from app.database import engine, SessionLocal, get_db
from app.storage import (
    DBStorage,
    DocumentEstimateNotFound,
    EstimateVersionConflict,
    seed_demo_data_if_enabled,
)
from app.schema_migrations import ensure_database_schema
from app import schemas
from app.control_plane import (
    ControlPlaneUnavailable,
    HomeControlPlaneAdapter,
    unavailable_detail,
)
from app.browser_session import (
    ProjectPrincipal,
    resolve_optional_project_principal,
    resolve_project_principal,
)
from app.project_history import ProjectNotFoundError
from app.auth import (
    get_optional_user,
    require_auth,
    require_operator_user,
    validate_auth_configuration,
)
from app.genkit_flow import planned_task_type
from app.operator_api import is_operator_api_path, safe_cluster_stats, safe_task_page
from app.document_html import DocumentHtmlError, sanitize_document_html


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_auth_configuration()
    if os.getenv("KOLIBRI_PUBLIC_BASE_URL", "").strip():
        from app.project_handoff import validate_project_handoff_configuration
        validate_project_handoff_configuration()
    ensure_database_schema(engine)
    from app.response_store import recover_interrupted_responses

    recover_interrupted_responses()
    db = SessionLocal()
    try:
        seed_demo_data_if_enabled(db)
        from app.owner_provider import bootstrap_owner_connection_from_environment, load_active_connection
        bootstrap_owner_connection_from_environment(db)
        load_active_connection(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="Колибри API",
    description="Backend API for Kolibri AI workspace platform",
    version="3.0.0",
    lifespan=lifespan,
)


def _cors_allowed_origins() -> list[str]:
    defaults = [
        "https://kolibriai.ru",
        "https://www.kolibriai.ru",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    configured = os.getenv("KOLIBRI_CORS_ALLOWED_ORIGINS", "")
    candidates = configured.split(",") if configured.strip() else defaults
    origins: list[str] = []
    for raw in candidates:
        origin = raw.strip().rstrip("/")
        parsed = urlsplit(origin)
        if (
            not origin
            or origin == "*"
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            continue
        if origin not in origins:
            origins.append(origin)
    return origins


_CORS_ALLOWED_ORIGINS = _cors_allowed_origins()
_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
    "script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
    "font-src 'self' data:; connect-src 'self'; frame-src 'self' blob:; "
    "form-action 'self'"
)
_UNSAFE_HTTP_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _canonical_origin(value: str | None) -> str | None:
    raw = str(value or "").strip().rstrip("/")
    parsed = urlsplit(raw)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _local_origin_hosts() -> set[str]:
    return {"localhost", "127.0.0.1", "[::1]", "::1"}


def _same_local_dev_host(origin: str, request_origin: str | None) -> bool:
    try:
        origin_host = urlsplit(origin).hostname or ""
        request_host = urlsplit(request_origin or "").hostname or ""
    except ValueError:
        return False
    allowed_local = _local_origin_hosts()
    return origin_host in allowed_local and request_host in allowed_local


def _cookie_mutation_origin_allowed(request: Request) -> bool:
    """Require an exact browser origin for HttpOnly-cookie mutations.

    Bearer clients are not subject to CSRF because browsers do not attach
    Authorization headers implicitly.  Cookie-authenticated writes must either
    carry an exact Origin or explicit same-origin Fetch Metadata.
    """

    if request.method.upper() not in _UNSAFE_HTTP_METHODS:
        return True
    if not ({"kolibri_auth", "kolibri_session"} & set(request.cookies)):
        return True

    supplied = _canonical_origin(request.headers.get("origin"))
    if supplied is not None:
        allowed: set[str] = set()
        public_origin = _canonical_origin(os.getenv("KOLIBRI_PUBLIC_BASE_URL"))
        if public_origin:
            allowed.add(public_origin)
        allowed.update(_CORS_ALLOWED_ORIGINS)
        request_origin = _canonical_origin(
            f"{request.url.scheme}://{request.headers.get('host', '')}"
        )
        if request_origin:
            allowed.add(request_origin)
        if _same_local_dev_host(supplied, request_origin):
            return True
        return supplied in allowed

    return request.headers.get("sec-fetch-site", "").strip().lower() == "same-origin"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.logging_middleware import (
    ReleaseIdentityMiddleware,
    RequestLoggingMiddleware,
    release_id,
    setup_logging,
)
setup_logging()
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(ReleaseIdentityMiddleware)


@app.middleware("http")
async def keep_operator_responses_private(request: Request, call_next):
    """Operator data and auth errors must never enter shared browser caches."""

    if not _cookie_mutation_origin_allowed(request):
        return JSONResponse(
            status_code=403,
            headers={
                "Cache-Control": "private, no-store",
                "Content-Security-Policy": _CONTENT_SECURITY_POLICY,
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            },
            content={
                "detail": {"code": "csrf_origin_forbidden"},
                "error": {
                    "message": "csrf_origin_forbidden",
                    "type": "invalid_request_error",
                    "code": "csrf_origin_forbidden",
                    "request_id": getattr(request.state, "request_id", None),
                },
                "request_id": getattr(request.state, "request_id", None),
            },
        )
    response = await call_next(request)
    response.headers.setdefault("Content-Security-Policy", _CONTENT_SECURITY_POLICY)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if is_operator_api_path(request.url.path):
        response.headers["Cache-Control"] = "private, no-store"
    return response


@app.exception_handler(StarletteHTTPException)
async def structured_http_error(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if isinstance(detail, dict):
        code = str(detail.get("code") or "request_failed")
        message = str(detail.get("message") or code)
    else:
        code = "request_failed"
        message = str(detail)
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "detail": detail,
            "error": {
                "message": message,
                "type": "invalid_request_error" if exc.status_code < 500 else "server_error",
                "code": code,
                "request_id": request_id,
            },
            "request_id": request_id,
        },
    )


from app.product_errors import (
    ProductChatError,
    product_chat_error_handler,
    product_request_validation_error_handler,
)

app.add_exception_handler(ProductChatError, product_chat_error_handler)
app.add_exception_handler(
    RequestValidationError,
    product_request_validation_error_handler,
)

from app.routers.telegram import router as telegram_router
app.include_router(telegram_router)

from app.image_artifacts import router as image_artifacts_router
app.include_router(image_artifacts_router)

from app.artifact_store import router as artifact_store_router
app.include_router(artifact_store_router)

from app.tool_router import router as tool_router
app.include_router(tool_router)

from app.routers.projects import router as projects_router
app.include_router(projects_router)

from app.routers.product_chat import router as product_chat_router
app.include_router(product_chat_router)

from app.routers.project_documents import router as project_documents_router
app.include_router(project_documents_router)

from app.routers.normative_sources import router as normative_sources_router
app.include_router(normative_sources_router)

from app.routers.organizations import router as organizations_router
app.include_router(organizations_router)

from app.routers.shell import router as shell_router
app.include_router(shell_router)
from app.routers.shell import public_router as shell_public_router
app.include_router(shell_public_router)

from app.routers.openai_compat import router as openai_compat_router
app.include_router(openai_compat_router)

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health", response_model=schemas.HealthResponse)
async def health():
    return {
        "status": "ok",
        "version": "3.0.0",
        "release_id": release_id(),
        "database": "connected",
        "timestamp": datetime.now(timezone.utc),
    }


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _set_auth_cookie(response: Response, token: str) -> None:
    public_url = urlsplit(os.getenv("KOLIBRI_PUBLIC_BASE_URL", ""))
    secure = public_url.scheme == "https" or os.getenv(
        "KOLIBRI_SECURE_COOKIES", ""
    ).strip().lower() in {"1", "true", "yes", "on"}
    response.set_cookie(
        "kolibri_auth",
        token,
        max_age=int(os.getenv("TOKEN_EXPIRE_MINUTES", "1440")) * 60,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )

@app.post("/api/v1/auth/register", status_code=201)
async def register(
    data: schemas.UserRegister,
    response: Response,
    anonymous_cookie: str | None = Cookie(default=None, alias="kolibri_session"),
    db: Session = Depends(get_db),
):
    from app.models import UserDB
    from app.auth import hash_password, create_access_token
    import uuid
    if db.query(UserDB).filter(UserDB.email == data.email).first():
        raise HTTPException(400, "Email already registered")
    user = UserDB(
        id=str(uuid.uuid4()), email=data.email, name=data.name,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.flush()
    from app.organization_auth import ensure_personal_organization
    organization = ensure_personal_organization(db, user)
    from app.project_handoff import (
        AnonymousAdoptionUnsupported,
        adopt_anonymous_project_access,
        adopt_anonymous_roots,
    )
    try:
        adopt_anonymous_roots(
            db,
            anonymous_cookie=anonymous_cookie,
            target_scope_id=organization.data_scope_id,
            target_organization_id=organization.id,
            actor_user_id=user.id,
        )
    except AnonymousAdoptionUnsupported as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": str(exc)},
        ) from exc
    adopt_anonymous_project_access(
        db,
        anonymous_cookie=anonymous_cookie,
        target_scope_id=organization.data_scope_id,
    )
    db.commit()
    token = create_access_token({"sub": user.id})
    _set_auth_cookie(response, token)
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "email": user.email, "name": user.name, "role": user.role}}


@app.post("/api/v1/auth/login")
async def login(
    data: schemas.UserLogin,
    response: Response,
    anonymous_cookie: str | None = Cookie(default=None, alias="kolibri_session"),
    db: Session = Depends(get_db),
):
    from app.models import UserDB
    from app.auth import verify_password, create_access_token
    user = db.query(UserDB).filter(UserDB.email == data.email).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")
    from app.organization_auth import ensure_personal_organization
    organization = ensure_personal_organization(db, user)
    from app.project_handoff import (
        AnonymousAdoptionUnsupported,
        adopt_anonymous_project_access,
        adopt_anonymous_roots,
    )
    try:
        adopt_anonymous_roots(
            db,
            anonymous_cookie=anonymous_cookie,
            target_scope_id=organization.data_scope_id,
            target_organization_id=organization.id,
            actor_user_id=user.id,
        )
    except AnonymousAdoptionUnsupported as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": str(exc)},
        ) from exc
    adopt_anonymous_project_access(
        db,
        anonymous_cookie=anonymous_cookie,
        target_scope_id=organization.data_scope_id,
    )
    db.commit()
    token = create_access_token({"sub": user.id})
    _set_auth_cookie(response, token)
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "email": user.email, "name": user.name, "role": user.role}}


@app.post("/api/v1/auth/password-reset/request", status_code=202)
async def request_password_reset(
    data: schemas.PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Issue a short-lived reset grant without leaking account existence."""

    from app.models import PasswordResetTokenDB, UserDB
    from app.password_reset import (
        PasswordResetDeliveryUnavailable,
        issue_token,
        normalize_email,
        send_password_reset_email,
        smtp_configured,
    )
    from app.rate_limiter import auth_limiter, get_client_ip

    client_ip = get_client_ip(request)
    if not auth_limiter.check(f"password-reset:{client_ip}"):
        raise HTTPException(
            status_code=429,
            detail={
                "code": "password_reset_rate_limited",
                "message": "Слишком много попыток. Повторите через минуту.",
            },
            headers={"Retry-After": "60"},
        )
    if not smtp_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "password_reset_delivery_unavailable",
                "message": "Почтовое восстановление сейчас недоступно.",
            },
        )

    email = normalize_email(data.email)
    user = db.query(UserDB).filter(UserDB.email == email).first()
    if user is not None and user.is_active:
        raw_token, hashed_token, expires_at = issue_token()
        now = datetime.now(timezone.utc)
        db.query(PasswordResetTokenDB).filter(
            PasswordResetTokenDB.user_id == user.id,
            PasswordResetTokenDB.used_at.is_(None),
        ).update({PasswordResetTokenDB.used_at: now})
        grant = PasswordResetTokenDB(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token_hash=hashed_token,
            expires_at=expires_at,
            created_at=now,
        )
        db.add(grant)
        try:
            send_password_reset_email(user.email, raw_token)
        except PasswordResetDeliveryUnavailable:
            db.rollback()
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "password_reset_delivery_failed",
                    "message": "Не удалось отправить письмо. Повторите позже.",
                },
            )
        db.commit()

    return {
        "accepted": True,
        "message": (
            "Если аккаунт существует, письмо со ссылкой уже отправлено."
        ),
    }


@app.post("/api/v1/auth/password-reset/confirm", status_code=204)
async def confirm_password_reset(
    data: schemas.PasswordResetConfirm,
    request: Request,
    db: Session = Depends(get_db),
):
    from app.auth import hash_password
    from app.models import PasswordResetTokenDB, UserDB
    from app.password_reset import token_digest
    from app.rate_limiter import auth_limiter, get_client_ip

    client_ip = get_client_ip(request)
    if not auth_limiter.check(f"password-reset-confirm:{client_ip}"):
        raise HTTPException(
            status_code=429,
            detail={
                "code": "password_reset_rate_limited",
                "message": "Слишком много попыток. Повторите через минуту.",
            },
            headers={"Retry-After": "60"},
        )
    if len(data.new_password) < 8:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "password_too_short",
                "message": "Пароль должен содержать минимум 8 символов.",
            },
        )

    now = datetime.now(timezone.utc)
    grant = db.query(PasswordResetTokenDB).filter(
        PasswordResetTokenDB.token_hash == token_digest(data.token),
        PasswordResetTokenDB.used_at.is_(None),
        PasswordResetTokenDB.expires_at > now,
    ).first()
    if grant is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "password_reset_token_invalid",
                "message": "Ссылка недействительна или уже использована.",
            },
        )
    user = db.query(UserDB).filter(
        UserDB.id == grant.user_id,
        UserDB.is_active.is_(True),
    ).first()
    if user is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "password_reset_token_invalid",
                "message": "Ссылка недействительна или уже использована.",
            },
        )

    user.hashed_password = hash_password(data.new_password)
    db.query(PasswordResetTokenDB).filter(
        PasswordResetTokenDB.user_id == user.id,
        PasswordResetTokenDB.used_at.is_(None),
    ).update({PasswordResetTokenDB.used_at: now})
    db.commit()
    return None


@app.post("/api/v1/auth/logout", status_code=204)
async def logout(response: Response):
    from app.organization_auth import ORGANIZATION_COOKIE_NAME

    response.delete_cookie(
        "kolibri_auth",
        path="/",
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        ORGANIZATION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="strict",
    )
    return None


@app.get("/api/v1/auth/me")
async def get_me_profile(user = Depends(require_auth)):
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}


@app.get("/api/v1/auth/session")
async def get_auth_session(
    response: Response,
    user = Depends(get_optional_user),
):
    """Probe browser identity without turning an anonymous Shell into 401 noise."""

    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    if user is None:
        response.delete_cookie(
            "kolibri_auth",
            path="/",
            httponly=True,
            samesite="strict",
        )
        return {"authenticated": False, "user": None}
    return {
        "authenticated": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
        },
    }


@app.put("/api/v1/auth/me")
async def update_me(
    data: schemas.UserUpdate,
    user = Depends(require_auth),
    db: Session = Depends(get_db),
):
    from app.auth import hash_password, verify_password
    if data.name is not None:
        user.name = data.name
    if data.email is not None:
        user.email = data.email
    if data.new_password is not None:
        if not data.current_password or not verify_password(data.current_password, user.hashed_password):
            raise HTTPException(400, "Current password required")
        user.hashed_password = hash_password(data.new_password)
    db.commit()
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}


# ---------------------------------------------------------------------------
# Estimates
# ---------------------------------------------------------------------------

def _estimate_etag(version: int) -> str:
    return f'"{version}"'


def _parse_if_match(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    token = value.strip()
    if token.startswith("W/"):
        token = token[2:].strip()
    if "," in token or token == "*":
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_if_match", "message": "If-Match must contain one estimate version"},
        )
    if len(token) >= 2 and token[0] == token[-1] == '"':
        token = token[1:-1]
    try:
        version = int(token)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_if_match", "message": "If-Match must be an integer estimate version"},
        ) from exc
    if version < 1:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_if_match", "message": "If-Match version must be positive"},
        )
    return version


def _required_estimate_version(if_match: Optional[str], explicit_version: Optional[int]) -> int:
    header_version = _parse_if_match(if_match)
    if header_version is None and explicit_version is None:
        raise HTTPException(
            status_code=428,
            detail={
                "code": "estimate_version_required",
                "message": "Send If-Match or the current estimate version",
            },
        )
    if header_version is not None and explicit_version is not None and header_version != explicit_version:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "estimate_version_mismatch",
                "message": "If-Match and body/query version must match",
            },
        )
    return header_version if header_version is not None else int(explicit_version)


def _raise_estimate_version_conflict(exc: EstimateVersionConflict) -> None:
    raise HTTPException(
        status_code=409,
        headers={"ETag": _estimate_etag(exc.current_version)},
        detail={
            "code": "estimate_version_conflict",
            "message": "Estimate was changed by another save; reload before retrying",
            "expected_version": exc.expected_version,
            "current_version": exc.current_version,
        },
    ) from exc

@app.get("/api/v1/estimates", response_model=schemas.EstimateListResponse)
async def list_estimates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    search: Optional[str] = None,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    result = storage.list_estimates(status=status, search=search, page=page, page_size=page_size)
    return {"items": result["items"], "total": result["total"], "page": page, "page_size": page_size}


@app.post("/api/v1/estimates", response_model=schemas.EstimateResponse, status_code=201)
async def create_estimate(
    data: schemas.EstimateCreate,
    response: Response,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    try:
        result = storage.create_estimate(data.model_dump())
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "project_not_found",
                "message": "Project is not available for this estimate",
            },
        ) from exc
    except Exception:
        from app.capability_runtime import record_capability_invocation

        record_capability_invocation(
            "estimate.create",
            succeeded=False,
            error_code="estimate_storage_failed",
            provider="estimate-storage",
        )
        raise
    from app.capability_runtime import record_capability_invocation

    record_capability_invocation(
        "estimate.create",
        succeeded=True,
        provider="estimate-storage",
        evidence_id=str(result["id"]),
    )
    response.headers["ETag"] = _estimate_etag(result["version"])
    return result


@app.get("/api/v1/estimates/{est_id}", response_model=schemas.EstimateResponse)
async def get_estimate(
    est_id: str,
    response: Response,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    result = storage.get_estimate(est_id)
    if not result:
        raise HTTPException(404, "Estimate not found")
    response.headers["ETag"] = _estimate_etag(result["version"])
    return result


@app.get(
    "/api/v1/estimates/{est_id}/technology-card",
    response_model=schemas.EstimateTechnologyCardResponse,
)
async def get_estimate_technology_card(
    est_id: str,
    version: Optional[int] = Query(default=None, ge=1),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    """Return the hidden technology/procurement artifact only on explicit request."""

    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    snapshot = (
        storage.get_estimate(est_id)
        if version is None
        else storage.get_estimate_snapshot(est_id, version)
    )
    if not snapshot:
        raise HTTPException(404, "Estimate not found")
    card = snapshot.get("technology_card")
    if not isinstance(card, dict):
        raise HTTPException(404, "Technology card is not available for this estimate")
    return {
        "estimate_id": est_id,
        "version": int(snapshot.get("version") or version or 1),
        "technology_card": card,
        "procurement_report": snapshot.get("procurement_report"),
    }


@app.put("/api/v1/estimates/{est_id}", response_model=schemas.EstimateResponse)
async def update_estimate(
    est_id: str,
    data: schemas.EstimateUpdate,
    response: Response,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    update_data = data.model_dump(exclude_unset=True)
    expected_version = _required_estimate_version(if_match, update_data.pop("version", None))
    if "status" in update_data and update_data["status"] is not None:
        update_data["status"] = update_data["status"].value if hasattr(update_data["status"], "value") else update_data["status"]
    try:
        result = storage.update_estimate(
            est_id,
            update_data,
            expected_version=expected_version,
        )
    except EstimateVersionConflict as exc:
        _raise_estimate_version_conflict(exc)
    if not result:
        raise HTTPException(404, "Estimate not found")
    response.headers["ETag"] = _estimate_etag(result["version"])
    return result


@app.delete("/api/v1/estimates/{est_id}", status_code=204)
async def delete_estimate(
    est_id: str,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    if not storage.delete_estimate(est_id):
        raise HTTPException(404, "Estimate not found")
    return Response(status_code=204)


@app.post("/api/v1/estimates/{est_id}/calculate", response_model=schemas.EstimateResponse)
async def calculate_estimate_endpoint(
    est_id: str,
    response: Response,
    version: Optional[int] = Query(default=None, ge=1),
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    expected_version = _required_estimate_version(if_match, version)
    try:
        result = storage.recalculate_estimate(est_id, expected_version=expected_version)
    except EstimateVersionConflict as exc:
        _raise_estimate_version_conflict(exc)
    if result is None:
        raise HTTPException(404, "Estimate not found")
    response.headers["ETag"] = _estimate_etag(result["version"])
    return result


@app.post(
    "/api/v1/estimates/{est_id}/command",
    response_model=schemas.EstimateCommandResponse,
)
async def apply_estimate_command(
    est_id: str,
    data: schemas.EstimateCommandRequest,
    response: Response,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    """Apply a bounded natural-language edit and persist a new revision."""
    from app.estimate_commands import build_estimate_command_update

    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    current = storage.get_estimate(est_id)
    if current is None:
        raise HTTPException(404, "Estimate not found")
    if current["version"] != data.version:
        _raise_estimate_version_conflict(
            EstimateVersionConflict(
                estimate_id=est_id,
                expected_version=data.version,
                current_version=current["version"],
            )
        )
    try:
        update, operations, message = build_estimate_command_update(
            current,
            data.command,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "estimate_command_invalid", "message": str(exc)},
        ) from exc
    if update is None:
        response.headers["ETag"] = _estimate_etag(current["version"])
        return {
            "applied": False,
            "message": message,
            "operations": [],
            "estimate": current,
        }
    try:
        updated = storage.update_estimate(
            est_id,
            update,
            expected_version=data.version,
        )
    except EstimateVersionConflict as exc:
        _raise_estimate_version_conflict(exc)
    if updated is None:
        raise HTTPException(404, "Estimate not found")
    response.headers["ETag"] = _estimate_etag(updated["version"])
    return {
        "applied": True,
        "message": message,
        "operations": operations,
        "estimate": updated,
    }


@app.post("/api/v1/estimates/{est_id}/duplicate")
async def duplicate_estimate(
    est_id: str,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    result = storage.duplicate_estimate(est_id)
    if not result:
        raise HTTPException(404, "Estimate not found")
    return result


@app.get("/api/v1/work-catalog", response_model=schemas.WorkCatalogListResponse)
async def list_work_catalog(
    search: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    return DBStorage(
        db,
        principal.scope_id,
        principal.organization_id,
    ).list_work_catalog(search=search, page=page, page_size=page_size)


@app.patch("/api/v1/work-catalog/{item_id}", response_model=schemas.WorkCatalogItem)
async def update_work_catalog_price(
    item_id: str,
    data: schemas.WorkCatalogUpdate,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    try:
        result = storage.update_work_catalog_price(item_id, data.latest_price, data.price_source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Work catalog item not found")
    return result


@app.get("/api/v1/clients", response_model=schemas.ClientDirectoryListResponse)
async def list_clients(
    search: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    return DBStorage(
        db,
        principal.scope_id,
        principal.organization_id,
    ).list_clients(search=search, page=page, page_size=page_size)


@app.post("/api/v1/clients", response_model=schemas.ClientDirectoryItem, status_code=201)
async def create_client(
    data: schemas.ClientDirectoryCreate,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    try:
        return DBStorage(db, principal.scope_id, principal.organization_id).create_client(
            data.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.patch("/api/v1/clients/{client_id}", response_model=schemas.ClientDirectoryItem)
async def update_client(
    client_id: str,
    data: schemas.ClientDirectoryUpdate,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    try:
        result = DBStorage(db, principal.scope_id, principal.organization_id).update_client(
            client_id,
            data.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return result


@app.get(
    "/api/v1/construction-objects",
    response_model=schemas.ConstructionObjectDirectoryListResponse,
)
async def list_construction_objects(
    search: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    return DBStorage(
        db,
        principal.scope_id,
        principal.organization_id,
    ).list_construction_objects(search=search, page=page, page_size=page_size)


@app.post(
    "/api/v1/construction-objects",
    response_model=schemas.ConstructionObjectDirectoryItem,
    status_code=201,
)
async def create_construction_object(
    data: schemas.ConstructionObjectDirectoryCreate,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    try:
        return DBStorage(
            db,
            principal.scope_id,
            principal.organization_id,
        ).create_construction_object(data.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.patch(
    "/api/v1/construction-objects/{object_id}",
    response_model=schemas.ConstructionObjectDirectoryItem,
)
async def update_construction_object(
    object_id: str,
    data: schemas.ConstructionObjectDirectoryUpdate,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    try:
        result = DBStorage(
            db,
            principal.scope_id,
            principal.organization_id,
        ).update_construction_object(object_id, data.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Construction object not found")
    return result


@app.get(
    "/api/v1/technology-catalog",
    response_model=schemas.TechnologyCatalogListResponse,
)
async def list_technology_catalog(
    search: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    return DBStorage(
        db,
        principal.scope_id,
        principal.organization_id,
    ).list_technology_catalog(search=search, page=page, page_size=page_size)


@app.post(
    "/api/v1/estimates/{est_id}/catalog",
    response_model=schemas.WorkCatalogListResponse,
)
async def promote_estimate_catalog(
    est_id: str,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    try:
        result = DBStorage(
            db,
            principal.scope_id,
            principal.organization_id,
        ).promote_estimate_to_catalog(est_id)
    except ValueError as exc:
        raise HTTPException(409, "Approve estimate before catalog promotion") from exc
    if result is None:
        raise HTTPException(404, "Estimate not found")
    return result


@app.get(
    "/api/v1/estimates/{est_id}/revisions",
    response_model=schemas.EstimateRevisionListResponse,
)
async def list_estimate_revisions(
    est_id: str,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    result = DBStorage(
        db, principal.scope_id, principal.organization_id
    ).list_estimate_revisions(est_id)
    if result is None:
        raise HTTPException(404, "Estimate not found")
    return result


@app.get(
    "/api/v1/estimates/{est_id}/revisions/{version}",
    response_model=schemas.EstimateRevisionResponse,
)
async def get_estimate_revision(
    est_id: str,
    version: int,
    response: Response,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    result = DBStorage(
        db, principal.scope_id, principal.organization_id
    ).get_estimate_revision(est_id, version)
    if result is None:
        raise HTTPException(404, "Estimate revision not found")
    response.headers["ETag"] = _estimate_etag(result["version"])
    return result


@app.get("/api/v1/estimates/{est_id}/pdf")
async def estimate_pdf(
    est_id: str,
    version: Optional[int] = Query(default=None, ge=1),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    result = storage.get_estimate_snapshot(est_id, version)
    if not result:
        raise HTTPException(404, "Estimate revision not found")
    pdf_bytes = generate_estimate_pdf(result)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={
                        "Content-Disposition": f"inline; filename=estimate_{est_id[:8]}_v{result['version']}.pdf",
                        "Cache-Control": "private, no-store, max-age=0",
                        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'self'",
                        "X-Content-Type-Options": "nosniff",
                        "ETag": _estimate_etag(result["version"]),
                    })


@app.get("/api/v1/estimates/{est_id}/export/{fmt}")
async def export_estimate(
    est_id: str,
    fmt: str,
    version: Optional[int] = Query(default=None, ge=1),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    d = storage.get_estimate_snapshot(est_id, version)
    if not d:
        raise HTTPException(404, "Estimate revision not found")
    sections = []
    for s in d.get("sections", []):
        positions = [
            CalcPosition(id=p["id"], code=p["code"], name=p["name"], unit=p["unit"],
                         quantity=p["quantity"], price=p["price"],
                         source=p.get("source", ""), comment=p.get("comment", ""),
                         sum=p.get("sum", "0"))
            for p in s["positions"]
        ]
        sections.append(CalcSection(id=s["id"], title=s["title"], positions=positions))
    calc = CalcEstimate(
        id=d["id"], title=d["title"], status=EstimateStatus(d.get("status", "draft")),
        sections=sections, overhead_rate=d.get("overhead_rate", "0"),
        vat_rate=d.get("vat_rate", "22"),
    )
    calc = calculate_estimate(calc)
    if fmt == "csv":
        content = export_to_csv(calc)
        return Response(content=content, media_type="text/csv",
                        headers={
                            "Content-Disposition": f"attachment; filename=estimate_{est_id[:8]}_v{d['version']}.csv",
                            "ETag": _estimate_etag(d["version"]),
                        })
    elif fmt == "json":
        return JSONResponse(
            content=d,
            headers={
                "Content-Disposition": f"attachment; filename=estimate_{est_id[:8]}_v{d['version']}.json",
                "ETag": _estimate_etag(d["version"]),
            },
        )
    elif fmt == "xlsx":
        from app.xlsx_export import generate_estimate_xlsx
        xlsx_bytes = generate_estimate_xlsx(d)
        return Response(content=xlsx_bytes,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={
                            "Content-Disposition": f"attachment; filename=estimate_{est_id[:8]}_v{d['version']}.xlsx",
                            "ETag": _estimate_etag(d["version"]),
                        })
    raise HTTPException(400, f"Unsupported format: {fmt}")


@app.get("/api/v1/estimates/{est_id}/workbook")
async def estimate_workbook_preview(
    est_id: str,
    version: Optional[int] = Query(default=None, ge=1),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    estimate = storage.get_estimate_snapshot(est_id, version)
    if not estimate:
        raise HTTPException(404, "Estimate revision not found")

    from app.workbook_preview import WorkbookPreviewError, build_workbook_preview
    from app.xlsx_export import generate_estimate_xlsx

    try:
        preview = build_workbook_preview(generate_estimate_xlsx(estimate))
    except WorkbookPreviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "estimate_id": estimate["id"],
        "version": estimate["version"],
        "title": estimate["title"],
        **preview,
    }


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@app.get("/api/v1/documents")
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: Optional[str] = None,
    db: Session = Depends(get_db),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    result = storage.list_documents(type_=type, page=page, page_size=page_size)
    return {"items": result["items"], "total": result["total"], "page": page, "page_size": page_size}


@app.post("/api/v1/documents", status_code=201)
async def create_document(
    data: schemas.DocumentCreate,
    db: Session = Depends(get_db),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    d = data.model_dump()
    if "type" in d and hasattr(d["type"], "value"):
        d["type"] = d["type"].value
    try:
        d["content"] = sanitize_document_html(d.get("content"))
    except DocumentHtmlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        result = storage.create_document(d)
    except DocumentEstimateNotFound:
        raise HTTPException(404, "Estimate not found") from None
    except Exception:
        from app.capability_runtime import record_capability_invocation

        record_capability_invocation(
            "document.editor",
            succeeded=False,
            error_code="document_storage_failed",
            provider="document-storage",
        )
        raise
    from app.capability_runtime import record_capability_invocation

    record_capability_invocation(
        "document.editor",
        succeeded=True,
        provider="document-storage",
        evidence_id=str(result["id"]),
    )
    return result


@app.get("/api/v1/documents/{doc_id}")
async def get_document(
    doc_id: str,
    db: Session = Depends(get_db),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    result = storage.get_document(doc_id)
    if not result:
        raise HTTPException(404, "Document not found")
    return result


@app.put("/api/v1/documents/{doc_id}")
async def update_document(
    doc_id: str,
    data: schemas.DocumentUpdate,
    db: Session = Depends(get_db),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    update_data = data.model_dump(exclude_unset=True)
    if "type" in update_data and update_data["type"] is not None and hasattr(update_data["type"], "value"):
        update_data["type"] = update_data["type"].value
    if "content" in update_data:
        try:
            update_data["content"] = sanitize_document_html(update_data["content"])
        except DocumentHtmlError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        result = storage.update_document(doc_id, update_data)
    except DocumentEstimateNotFound:
        raise HTTPException(404, "Estimate not found") from None
    if not result:
        raise HTTPException(404, "Document not found")
    return result


@app.delete("/api/v1/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    if not storage.delete_document(doc_id):
        raise HTTPException(404, "Document not found")
    return Response(status_code=204)


@app.get("/api/v1/documents/{doc_id}/pdf")
async def document_pdf(
    doc_id: str,
    db: Session = Depends(get_db),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    result = storage.get_document(doc_id)
    if not result:
        raise HTTPException(404, "Document not found")
    pdf_bytes = generate_document_pdf(result)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={
                        "Content-Disposition": f"inline; filename=document_{doc_id[:8]}.pdf",
                        "Cache-Control": "private, no-store, max-age=0",
                        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'self'",
                        "X-Content-Type-Options": "nosniff",
                    })


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

@app.get("/api/v1/library")
async def list_library(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    item_type: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    items = storage.list_library()

    from app.artifact_store import get_artifact_store

    scope_key = hashlib.sha256(principal.scope_id.encode()).hexdigest()
    for artifact in get_artifact_store().list():
        metadata = artifact.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("scope_key") != scope_key:
            continue
        mime_type = str(artifact.get("mime_type") or "")
        artifact_type = str(artifact.get("type") or "")
        if mime_type == "application/pdf":
            projected_type = "pdf"
        elif mime_type == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ):
            projected_type = "table"
        elif mime_type.startswith(("image/", "audio/", "video/")):
            projected_type = "media"
        elif artifact_type in {"report", "agent_result"} or artifact_type.endswith(".report"):
            projected_type = "report"
        else:
            projected_type = "document"
        artifact_id = str(artifact["id"])
        revision = int(artifact.get("revision") or 1)
        items.append({
            "id": f"artifact:{artifact_id}:v{revision}",
            "title": artifact.get("title") or artifact.get("filename") or "Файл",
            "item_type": projected_type,
            "source_id": artifact_id,
            "source_type": "artifact",
            "status": "ready",
            "client": "",
            "project": "",
            "file_size": int(artifact.get("size_bytes") or 0),
            "mime_type": mime_type,
            "filename": artifact.get("filename") or "artifact",
            "version": revision,
            "open_url": (
                f"/api/v1/artifacts/{artifact_id}/workbook?revision={revision}"
                if projected_type == "table"
                else artifact.get("revision_url") or artifact.get("url")
            ),
            "download_url": (
                artifact.get("revision_download_url")
                or f"/api/v1/artifacts/{artifact_id}?revision={revision}&download=true"
            ),
            "created_at": artifact.get("created_at") or "",
            "updated_at": artifact.get("updated_at") or artifact.get("created_at") or "",
        })

    counts: dict[str, int] = {
        "all": len(items),
        "estimate": 0,
        "document": 0,
        "pdf": 0,
        "table": 0,
        "media": 0,
        "report": 0,
    }
    for item in items:
        projected_type = str(item.get("item_type") or "")
        counts[projected_type] = counts.get(projected_type, 0) + 1

    if item_type:
        items = [item for item in items if item["item_type"] == item_type]
    if search:
        normalized_search = search.casefold()
        items = [
            item for item in items
            if normalized_search in str(item.get("title") or "").casefold()
            or normalized_search in str(item.get("project") or "").casefold()
            or normalized_search in str(item.get("client") or "").casefold()
        ]
    items.sort(
        key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
        reverse=True,
    )
    start = (page - 1) * page_size
    return {
        "items": items[start:start + page_size],
        "total": len(items),
        "page": page,
        "page_size": page_size,
        "counts": counts,
    }


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

@app.get("/api/v1/agents")
async def list_agents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    _operator = Depends(require_operator_user),
):
    try:
        adapter = HomeControlPlaneAdapter.from_environment()
        return await adapter.list_agents(page=page, page_size=page_size, status=status)
    except ControlPlaneUnavailable as exc:
        raise HTTPException(status_code=503, detail=unavailable_detail(exc.reason)) from exc


@app.post("/api/v1/agents", status_code=201)
async def create_agent(
    data: dict,
    _operator = Depends(require_operator_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(
        status_code=405,
        detail="Home Control Plane portal adapter is read-only",
    )


@app.get("/api/v1/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    _operator = Depends(require_operator_user),
    db: Session = Depends(get_db),
):
    try:
        adapter = HomeControlPlaneAdapter.from_environment()
        result = await adapter.get_agent(agent_id)
    except ControlPlaneUnavailable as exc:
        raise HTTPException(status_code=503, detail=unavailable_detail(exc.reason)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Agent Host not found")
    return result


@app.delete("/api/v1/agents/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: str,
    _operator = Depends(require_operator_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(
        status_code=405,
        detail="Home Control Plane portal adapter is read-only",
    )


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

@app.get("/api/v1/nodes")
async def list_nodes(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: Optional[str] = None,
    _operator = Depends(require_operator_user),
):
    try:
        adapter = HomeControlPlaneAdapter.from_environment()
        return await adapter.list_nodes(page=page, page_size=page_size, status=status)
    except ControlPlaneUnavailable as exc:
        raise HTTPException(status_code=503, detail=unavailable_detail(exc.reason)) from exc


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@app.get("/api/v1/tasks")
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    state: Optional[str] = None,
    _operator = Depends(require_operator_user),
):
    try:
        adapter = HomeControlPlaneAdapter.from_environment()
        return safe_task_page(
            await adapter.list_tasks(page=page, page_size=page_size, state=state)
        )
    except ControlPlaneUnavailable as exc:
        raise HTTPException(status_code=503, detail=unavailable_detail(exc.reason)) from exc


def _control_plane_mutation_error(exc: ControlPlaneUnavailable) -> HTTPException:
    status_code = {
        "control_plane_auth_invalid": 401,
        "control_plane_scope_denied": 403,
        "control_plane_resource_not_found": 404,
        "control_plane_conflict": 409,
        "control_plane_request_rejected": 422,
    }.get(exc.reason, 503)
    return HTTPException(status_code=status_code, detail=unavailable_detail(exc.reason))


@app.post("/api/v1/tasks", status_code=201)
async def create_factory_task(
    data: dict,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    operator = Depends(require_operator_user),
):
    objective = str(data.get("objective") or "").strip()
    if not 1 <= len(objective) <= 8000:
        raise HTTPException(status_code=422, detail="objective must contain 1..8000 characters")
    raw_key = str(idempotency_key or data.get("client_request_id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,160}", raw_key):
        raise HTTPException(status_code=422, detail="Idempotency-Key is required")
    principal_ref = hashlib.sha256(str(operator.id).encode("utf-8")).hexdigest()[:16]
    binding = hashlib.sha256(f"{principal_ref}:{raw_key}".encode("utf-8")).hexdigest()
    request_sha256 = hashlib.sha256(json.dumps(
        {"kind": "orchestrator_chat_response", "objective": objective, "public_model": "kolibri"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    envelope = {
        "task_id": f"KOL-PORTAL-{binding[:20].upper()}",
        "idempotency_key": f"portal:{binding}",
        "kind": "orchestrator_chat_response",
        "objective": objective,
        "request_sha256": request_sha256,
        "runner": "codex",
        "required_capability": "runner:codex",
        "max_attempts": 1,
        "source": {
            "kind": "kolibri_provider_gateway",
            "channel": "portal_factory_control",
            "principal_ref": principal_ref,
        },
    }
    try:
        adapter = HomeControlPlaneAdapter.from_environment()
        return await adapter.submit_owner_task(envelope)
    except ControlPlaneUnavailable as exc:
        raise _control_plane_mutation_error(exc) from exc


@app.get("/api/v1/tasks/{task_id}")
async def get_factory_task(
    task_id: str,
    _operator = Depends(require_operator_user),
):
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,160}", task_id):
        raise HTTPException(status_code=422, detail="task id invalid")
    try:
        adapter = HomeControlPlaneAdapter.from_environment()
        return await adapter.get_task_detail(task_id)
    except ControlPlaneUnavailable as exc:
        raise _control_plane_mutation_error(exc) from exc


@app.get("/api/v1/tasks/{task_id}/events")
async def get_factory_task_events(
    task_id: str,
    after_sequence: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    _operator = Depends(require_operator_user),
):
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,160}", task_id):
        raise HTTPException(status_code=422, detail="task id invalid")
    try:
        adapter = HomeControlPlaneAdapter.from_environment()
        return await adapter.list_task_events(
            task_id,
            after_sequence=after_sequence,
            limit=limit,
        )
    except ControlPlaneUnavailable as exc:
        raise _control_plane_mutation_error(exc) from exc


@app.post("/api/v1/tasks/{task_id}/cancel")
async def cancel_factory_task(
    task_id: str,
    data: Optional[dict] = None,
    _operator = Depends(require_operator_user),
):
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,160}", task_id):
        raise HTTPException(status_code=422, detail="task id invalid")
    reason = str((data or {}).get("reason") or "cancelled_by_portal_owner").strip()
    if not 1 <= len(reason) <= 240:
        raise HTTPException(status_code=422, detail="cancel reason invalid")
    try:
        adapter = HomeControlPlaneAdapter.from_environment()
        return await adapter.cancel_task(task_id, reason=reason)
    except ControlPlaneUnavailable as exc:
        raise _control_plane_mutation_error(exc) from exc


# ---------------------------------------------------------------------------
# Control Plane — Cluster stats, agent/node/task actions
# ---------------------------------------------------------------------------

@app.get("/api/v1/cluster/stats")
async def cluster_stats(_operator = Depends(require_operator_user)):
    try:
        adapter = HomeControlPlaneAdapter.from_environment()
        return safe_cluster_stats(await adapter.cluster_stats())
    except ControlPlaneUnavailable as exc:
        raise HTTPException(status_code=503, detail=unavailable_detail(exc.reason)) from exc


@app.get("/api/v1/control/tasks/summary")
async def control_task_summary(_operator = Depends(require_operator_user)):
    try:
        adapter = HomeControlPlaneAdapter.from_environment()
        return await adapter.task_summary()
    except ControlPlaneUnavailable as exc:
        raise HTTPException(status_code=503, detail=unavailable_detail(exc.reason)) from exc


@app.get("/api/v1/control/events")
async def control_events(
    after_cursor: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    _operator = Depends(require_operator_user),
):
    try:
        adapter = HomeControlPlaneAdapter.from_environment()
        return await adapter.list_events(after_cursor=after_cursor, limit=limit)
    except ControlPlaneUnavailable as exc:
        raise HTTPException(status_code=503, detail=unavailable_detail(exc.reason)) from exc


@app.get("/api/v1/control/models")
async def control_models(_operator = Depends(require_operator_user)):
    try:
        adapter = HomeControlPlaneAdapter.from_environment()
        return await adapter.provider_routes()
    except ControlPlaneUnavailable as exc:
        raise HTTPException(status_code=503, detail=unavailable_detail(exc.reason)) from exc


@app.get("/api/v1/control/local-models")
async def control_local_models(_operator = Depends(require_operator_user)):
    try:
        adapter = HomeControlPlaneAdapter.from_environment()
        return await adapter.local_model_admission()
    except ControlPlaneUnavailable as exc:
        raise HTTPException(status_code=503, detail=unavailable_detail(exc.reason)) from exc


@app.get("/api/v1/control/learning")
async def control_learning(_operator = Depends(require_operator_user)):
    try:
        adapter = HomeControlPlaneAdapter.from_environment()
        return await adapter.formulalm_admission()
    except ControlPlaneUnavailable as exc:
        raise HTTPException(status_code=503, detail=unavailable_detail(exc.reason)) from exc


@app.get("/api/v1/analytics")
async def analytics(
    _operator = Depends(require_operator_user),
    db: Session = Depends(get_db),
):
    from app.models import EstimateDB, DocumentDB, AgentDB, TaskDB
    from decimal import Decimal

    estimates = db.query(EstimateDB).all()
    documents = db.query(DocumentDB).all()
    agents = db.query(AgentDB).all()
    tasks = db.query(TaskDB).all()

    # Estimate stats
    total_value = sum(Decimal(e.total or "0") for e in estimates)
    by_status = {}
    for e in estimates:
        by_status[e.status] = by_status.get(e.status, 0) + 1

    # Document stats
    by_type = {}
    for d in documents:
        by_type[d.type] = by_type.get(d.type, 0) + 1

    # Agent stats
    agent_by_status = {}
    for a in agents:
        agent_by_status[a.status] = agent_by_status.get(a.status, 0) + 1

    # Task stats
    task_by_state = {}
    for t in tasks:
        task_by_state[t.state] = task_by_state.get(t.state, 0) + 1

    return {
        "estimates": {
            "total": len(estimates),
            "total_value": str(total_value),
            "by_status": by_status,
        },
        "documents": {
            "total": len(documents),
            "by_type": by_type,
        },
        "agents": {
            "total": len(agents),
            "by_status": agent_by_status,
        },
        "tasks": {
            "total": len(tasks),
            "by_state": task_by_state,
        },
    }


@app.patch("/api/v1/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    data: dict,
    _operator = Depends(require_operator_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(
        status_code=405,
        detail="Home Control Plane portal adapter is read-only",
    )


@app.patch("/api/v1/nodes/{node_id}")
async def update_node(
    node_id: str,
    data: dict,
    _operator = Depends(require_operator_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(
        status_code=405,
        detail="Home Control Plane portal adapter is read-only",
    )


@app.patch("/api/v1/tasks/{task_id}")
async def update_task(
    task_id: str,
    data: dict,
    _operator = Depends(require_operator_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(
        status_code=405,
        detail="Home Control Plane portal adapter is read-only",
    )


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

@app.post("/api/v1/pdf/generate")
async def generate_pdf(
    data: schemas.PDFGenerateRequest,
    request: Request,
    _principal: ProjectPrincipal = Depends(resolve_project_principal),
):
    from app.rate_limiter import api_limiter, check_rate_limit
    await check_rate_limit(request, api_limiter)
    pdf_bytes = generate_document_pdf({"title": data.title, "content": data.html_content})
    b64 = base64.b64encode(pdf_bytes).decode()
    return {"pdf_base64": b64, "filename": f"{data.title}.pdf",
            "page_count": 1, "size_bytes": len(pdf_bytes)}


# ---------------------------------------------------------------------------
# Chat — Kimi K2.6 AI provider
# ---------------------------------------------------------------------------

def _public_legacy_chat_result(value: dict[str, Any]) -> dict[str, Any]:
    """Project one legacy chat result onto the public Kolibri identity.

    The original value remains available to the caller for capability telemetry
    and durable internal provenance. Only the detached HTTP projection loses
    provider routing details.
    """

    result = dict(value)
    for key in ("_provider", "_model", "provider_route", "selected_route_id"):
        result.pop(key, None)
    result["provider"] = "kolibri"
    result["model"] = "kolibri"
    return result


@app.post("/api/v1/chat", response_model=schemas.ChatResponse)
async def chat(
    request: Request,
    data: schemas.ChatRequest,
    principal: ProjectPrincipal | None = Depends(resolve_optional_project_principal),
):
    from app.rate_limiter import check_rate_limit, chat_limiter
    await check_rate_limit(request, chat_limiter)
    if not data.messages:
        raise HTTPException(400, "No messages provided")
    messages = [{"role": m.role, "content": m.content} for m in data.messages]
    from app.project_document_context import project_document_context
    source_context = (
        project_document_context(data.project_id, principal)
        if principal is not None
        else ""
    )
    if source_context:
        messages = [{"role": "system", "content": source_context}, *messages]
    policy = data.policy.model_dump() if data.policy else None
    task_type = await planned_task_type(
        messages,
        policy,
        background=data.background,
    )
    from app.image_artifacts import (
        IMAGE_CAPABILITY_ID,
        ImageCapabilityUnavailable,
        ImageGenerationFailed,
        ImageGenerationRequest,
        generate_invocable_image,
        is_image_generation_request,
        public_image_artifact,
    )
    image_prompt = data.messages[-1].content
    if is_image_generation_request(image_prompt):
        if principal is None:
            raise HTTPException(
                status_code=428,
                detail={"code": "session_bootstrap_required"},
            )
        try:
            internal_artifact = await generate_invocable_image(
                ImageGenerationRequest(prompt=image_prompt),
                policy=policy,
                scope_id=principal.scope_id,
            )
            artifact = public_image_artifact(internal_artifact)
        except ImageCapabilityUnavailable:
            return {
                "content": "",
                "actions": [],
                "status": "capability_unavailable",
                "provider": "kolibri",
                "model": "kolibri",
                "error_code": "capability_unavailable",
                "recoverable": True,
                "capability": IMAGE_CAPABILITY_ID,
            }
        except ImageGenerationFailed:
            return {
                "content": "",
                "actions": [],
                "status": "failed",
                "provider": "kolibri",
                "model": "kolibri",
                "error_code": "image_artifact_verification_failed",
                "recoverable": True,
                "capability": IMAGE_CAPABILITY_ID,
            }
        return {
            "content": "",
            "actions": [{"type": "present_image", "label": "Открыть изображение", "data": artifact}],
            "status": "ready",
            "provider": "kolibri",
            "model": "kolibri",
        }
    from app.estimate_action import is_estimate_request
    from app.truth_policy import resolve_current_information

    # Current regional prices are part of estimate materialisation, where
    # fetched evidence is bound to rows before deterministic calculation.
    # The generic current-information renderer must not consume that request.
    truth_result = (
        None
        if is_estimate_request(messages)
        else await resolve_current_information(messages)
    )
    if truth_result is not None and truth_result.get("status") == "source_backed":
        return _public_legacy_chat_result(truth_result)
    from app.ai_provider import chat_completion
    try:
        result = await chat_completion(
            messages,
            task_type=task_type,
            previous_response_id=data.previous_response_id,
            background=data.background,
            policy=policy,
            idempotency_key=request.headers.get("Idempotency-Key"),
        )
        if str(result.get("status") or "") not in {"error", "failed", "unavailable", "capability_unavailable"}:
            from app.capability_runtime import record_capability_invocation

            record_capability_invocation(
                "chat.responses",
                succeeded=True,
                provider=str(result.get("provider") or "kolibri"),
                model=str(result.get("model") or "kolibri"),
            )
        return _public_legacy_chat_result(result)
    except Exception:
        return {
            "content": "",
            "actions": [],
            "status": "error",
            "provider": "kolibri",
            "model": "kolibri",
            "error_code": "provider_unavailable",
            "recoverable": True,
        }


@app.post("/api/v1/chat/stream")
async def chat_stream(
    request: Request,
    data: schemas.ChatRequest,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
):
    from app.rate_limiter import check_rate_limit, chat_limiter
    await check_rate_limit(request, chat_limiter)
    if not data.messages:
        raise HTTPException(400, "No messages provided")
    messages = [{"role": m.role, "content": m.content} for m in data.messages]
    from app.project_document_context import project_document_context
    source_context = project_document_context(data.project_id, principal)
    if source_context:
        messages = [{"role": "system", "content": source_context}, *messages]
    policy = data.policy.model_dump() if data.policy else None
    task_type = await planned_task_type(
        messages,
        policy,
        background=data.background,
    )
    from app.ai_provider import chat_completion_stream, work_summary_event
    from app.image_artifacts import (
        IMAGE_CAPABILITY_ID,
        ImageCapabilityUnavailable,
        ImageGenerationFailed,
        ImageGenerationRequest,
        generate_invocable_image,
        image_execution_identity,
        is_image_generation_request,
        public_image_artifact,
    )
    from app.estimate_action import is_estimate_request
    from app.truth_policy import requires_current_evidence, resolve_current_information
    from app.routers.openai_compat import (
        _track_background_task,
        begin_public_response,
        record_public_stream_chunk,
        snapshot_public_response_events,
    )
    from app.capability_runtime import try_record_capability_invocation
    image_prompt = data.messages[-1].content
    estimate_request = is_estimate_request(messages)
    public_response_id = begin_public_response(
        messages,
        owner_scope=principal.scope_id,
        organization_id=principal.organization_id,
    )
    nonterminal_response_statuses = {
        "queued",
        "planning",
        "in_progress",
        "running",
        "waiting_for_input",
        "approval_required",
        "verifying",
    }

    def sse(payload: dict[str, Any]) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def canonical_events(chunk: dict) -> list[dict]:
        return record_public_stream_chunk(public_response_id, chunk)

    def live_canonical_events(chunk: dict) -> list[dict]:
        return [
            event
            for event in canonical_events(chunk)
            if event.get("type") in {
                "response.output_text.delta",
                "response.artifact.ready",
                "response.completed",
                "response.failed",
                "response.cancelled",
                "response.status.updated",
                "response.work_summary.updated",
                "response.tool.started",
                "response.tool.completed",
            }
        ]

    def legacy_stream_payload(chunk: dict) -> dict[str, Any] | None:
        payload = dict(chunk)
        payload.pop("work_summary", None)
        payload.pop("tool_event", None)
        payload.pop("response_id", None)
        has_internal_identity = any(
            key in payload for key in ("provider", "model", "_provider", "_model")
        )
        for key in ("_provider", "_model", "provider_route", "selected_route_id"):
            payload.pop(key, None)
        status = str(payload.get("status") or "").strip().lower()
        if payload.get("done") is True and status in nonterminal_response_statuses:
            # A provider may close its upload stream after accepting a durable
            # background response.  Keep that handoff non-terminal for the
            # legacy client and bind it to the public response used for replay.
            payload["done"] = False
            payload["response_id"] = public_response_id
        provider_event = payload.get("provider_event")
        if isinstance(provider_event, dict):
            raw_failure_kind = str(provider_event.get("failure_kind") or "provider_error").lower()
            safe_failure_kind = "".join(
                character if character.isalnum() or character in "._-" else "_"
                for character in raw_failure_kind
            )[:80] or "provider_error"
            payload["provider_event"] = {
                "type": "provider.attempt.failed",
                "failure_kind": safe_failure_kind,
                "will_retry": provider_event.get("will_retry") is True,
            }
        if has_internal_identity:
            payload["provider"] = "kolibri"
            payload["model"] = "kolibri"
        if (
            payload.get("content")
            or payload.get("done") is True
            or isinstance(payload.get("provider_event"), dict)
        ):
            return payload
        return None

    async def event_generator():
        try:
            created_event = next(
                event
                for event in snapshot_public_response_events(public_response_id)
                if event.get("type") == "response.created"
            )
            yield sse(created_event)
            for event in live_canonical_events(
                work_summary_event("accepted", "Запрос принят", status="completed")
            ):
                yield sse(event)
            if estimate_request:
                for event in live_canonical_events(
                    work_summary_event(
                        "estimate_creation",
                        "Формирую смету",
                        status="active",
                    )
                ):
                    yield sse(event)
            if is_image_generation_request(image_prompt):
                for event in live_canonical_events(
                    work_summary_event(
                        "tool_execution",
                        "Создаю изображение",
                        status="active",
                    )
                ):
                    yield sse(event)
                try:
                    internal_artifact = await generate_invocable_image(
                        ImageGenerationRequest(prompt=image_prompt),
                        policy=policy,
                        run_id=public_response_id,
                        scope_id=principal.scope_id,
                    )
                    artifact = public_image_artifact(internal_artifact)
                except ImageCapabilityUnavailable:
                    final = {"content": "", "done": True, "actions": [], "status": "capability_unavailable", "provider": "kolibri", "model": "kolibri", "fallback_used": False, "error_code": "capability_unavailable", "recoverable": True, "capability": IMAGE_CAPABILITY_ID, "response_id": public_response_id}
                    final_events = canonical_events(final)
                    for event in final_events:
                        if event.get("type") in {
                            "response.output_text.delta",
                            "response.failed",
                        }:
                            yield sse(event)
                    legacy = legacy_stream_payload(final)
                    if legacy:
                        yield sse(legacy)
                    return
                except ImageGenerationFailed:
                    final = {"content": "", "done": True, "actions": [], "status": "failed", "provider": "kolibri", "model": "kolibri", "fallback_used": False, "error_code": "image_artifact_verification_failed", "recoverable": True, "capability": IMAGE_CAPABILITY_ID, "response_id": public_response_id}
                    final_events = canonical_events(final)
                    for event in final_events:
                        if event.get("type") in {
                            "response.output_text.delta",
                            "response.failed",
                        }:
                            yield sse(event)
                    legacy = legacy_stream_payload(final)
                    if legacy:
                        yield sse(legacy)
                    return
                image_identity = image_execution_identity()
                for event in live_canonical_events(
                    work_summary_event(
                        "artifact_verification",
                        "Формат, размер и контрольная сумма изображения проверены",
                        status="completed",
                        artifact_type="image",
                        artifact_id=artifact["id"],
                    )
                ):
                    yield sse(event)
                content_chunk = {"content": "", "done": False, "response_id": public_response_id}
                final = {"content": "", "done": True, "actions": [{"type": "present_image", "label": "Открыть изображение", "data": artifact}], "status": "ready", "provider": "kolibri", "model": "kolibri", "fallback_used": False, "response_id": public_response_id}
                content_events = canonical_events(content_chunk)
                final_events = canonical_events(final)
                try_record_capability_invocation(
                    "chat.streaming",
                    succeeded=True,
                    provider=image_identity["provider"],
                    model=str(internal_artifact["model"]),
                    evidence_id=str(artifact["sha256"]),
                )
                content_payload = legacy_stream_payload(content_chunk)
                final_payload = legacy_stream_payload(final)
                if content_payload:
                    yield sse(content_payload)
                for event in (*content_events, *final_events):
                    if event.get("type") in {
                        "response.output_text.delta",
                        "response.artifact.ready",
                        "response.completed",
                    }:
                        yield sse(event)
                if final_payload:
                    yield sse(final_payload)
                return
            # Explicit estimate creation owns its regional price-research
            # subflow; generic web search remains authoritative for pure web
            # questions only.
            current_information = (
                not estimate_request and requires_current_evidence(messages)
            )
            if current_information:
                for event in live_canonical_events(
                    work_summary_event(
                        "source_retrieval",
                        "Выполняю поиск актуальных источников",
                        status="active",
                    )
                ):
                    yield sse(event)
            truth_result = (
                None
                if estimate_request
                else await resolve_current_information(messages)
            )
            if truth_result is not None and truth_result.get("status") == "source_backed":
                truth_provider = str(truth_result.get("provider") or "web_search")
                truth_model = str(truth_result.get("model") or "deterministic-evidence-renderer")
                route_status = "completed" if truth_result.get("status") == "source_backed" else "failed"
                route_summary = (
                    "Проверяемые источники получены"
                    if route_status == "completed"
                    else "Поиск не вернул проверяемых источников"
                )
                for event in live_canonical_events(
                    work_summary_event(
                        "source_retrieval",
                        route_summary,
                        status=route_status,
                    )
                ):
                    yield sse(event)
                if route_status == "completed":
                    for event in live_canonical_events(
                        work_summary_event(
                            "response_received",
                            "Ответ собран из найденных источников",
                            status="completed",
                        )
                    ):
                        yield sse(event)
                final = dict(truth_result)
                content = str(final.pop("content", ""))
                if content:
                    content_chunk = {'content': content, 'done': False, 'response_id': public_response_id}
                    content_events = canonical_events(content_chunk)
                    legacy = legacy_stream_payload(content_chunk)
                    if legacy:
                        yield sse(legacy)
                    for event in content_events:
                        if event.get("type") == "response.output_text.delta":
                            yield sse(event)
                final["content"] = ""
                final["done"] = True
                final["response_id"] = public_response_id
                final_events = canonical_events(final)
                try_record_capability_invocation(
                    "chat.streaming",
                    succeeded=True,
                    provider=truth_provider,
                    model=truth_model,
                )
                for event in final_events:
                    if event.get("type") in {
                        "response.artifact.ready",
                        "response.completed",
                        "response.failed",
                        "response.cancelled",
                    }:
                        yield sse(event)
                legacy = legacy_stream_payload(final)
                if legacy:
                    yield sse(legacy)
                return
            if truth_result is not None:
                for event in live_canonical_events(
                    work_summary_event(
                        "source_retrieval",
                        "Встроенный поиск не вернул проверяемых источников; продолжаю через резервный поиск",
                        status="failed",
                    )
                ):
                    yield sse(event)
            async for chunk in chat_completion_stream(
                messages,
                task_type=task_type,
                previous_response_id=data.previous_response_id,
                background=data.background,
                policy=policy,
                idempotency_key=request.headers.get("Idempotency-Key"),
                run_id=public_response_id,
            ):
                provider_event = chunk.get("provider_event")
                if isinstance(provider_event, dict):
                    will_retry = provider_event.get("will_retry") is True
                    for event in live_canonical_events(
                        work_summary_event(
                            "provider_attempt",
                            "Маршрут недоступен, переключаюсь на следующий" if will_retry else "Доступный маршрут не завершил запрос",
                            status="failed",
                        )
                    ):
                        yield sse(event)
                    legacy = legacy_stream_payload(chunk)
                    if legacy:
                        yield sse(legacy)
                    continue
                appended_events = record_public_stream_chunk(public_response_id, chunk)
                if (
                    chunk.get("done") is True
                    and str(chunk.get("status") or "")
                    not in {
                        "error",
                        "failed",
                        "unavailable",
                        "capability_unavailable",
                        *nonterminal_response_statuses,
                    }
                ):
                    try_record_capability_invocation(
                        "chat.streaming",
                        succeeded=True,
                        provider=str(chunk.get("provider") or "kolibri"),
                        model=str(chunk.get("model") or "kolibri"),
                    )
                    if estimate_request and any(
                        a.get("type") == "create_estimate"
                        for a in (chunk.get("actions") or [])
                    ):
                        for event in live_canonical_events(
                            work_summary_event(
                                "estimate_creation",
                                "Смета готова к открытию",
                                status="completed",
                            )
                        ):
                            yield sse(event)
                for event in appended_events:
                    if event.get("type") in {
                        "response.output_text.delta",
                        "response.artifact.ready",
                        "response.completed",
                        "response.failed",
                        "response.cancelled",
                        "response.work_summary.updated",
                        "response.tool.started",
                        "response.tool.completed",
                        "response.status.updated",
                    }:
                        yield sse(event)
                legacy = legacy_stream_payload(chunk)
                if legacy:
                    yield sse(legacy)
        except Exception:
            try_record_capability_invocation(
                "chat.streaming",
                succeeded=False,
                error_code="provider_stream_failed",
                provider="none",
            )
            final = {"content": "", "done": True, "actions": [], "status": "error", "provider": "kolibri", "model": "kolibri", "fallback_used": True, "error_code": "provider_stream_failed", "response_id": public_response_id}
            final_events = canonical_events(final)
            for event in final_events:
                if event.get("type") in {
                    "response.output_text.delta",
                    "response.failed",
                }:
                    yield sse(event)
            legacy = legacy_stream_payload(final)
            if legacy:
                yield sse(legacy)

    live_events: asyncio.Queue[str | None] = asyncio.Queue()
    live_subscriber = True

    async def run_durable_response() -> None:
        """Drive provider work independently from the browser SSE connection."""

        try:
            async for payload in event_generator():
                if live_subscriber:
                    live_events.put_nowait(payload)
        finally:
            if live_subscriber:
                live_events.put_nowait(None)

    producer = asyncio.create_task(
        run_durable_response(),
        name=f"kolibri-chat-response-{public_response_id}",
    )
    _track_background_task(public_response_id, producer)

    async def durable_event_stream():
        nonlocal live_subscriber
        try:
            while True:
                payload = await live_events.get()
                if payload is None:
                    return
                yield payload
        finally:
            # Disconnecting a browser only removes this subscriber.  The
            # independently tracked producer keeps committing canonical events
            # for /responses/{id}/events replay.
            live_subscriber = False

    return StreamingResponse(
        durable_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/v1/ai/analyze-estimate")
async def ai_analyze_estimate(
    est_id: str,
    db: Session = Depends(get_db),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
):
    from app.ai_provider import analyze_estimate
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    est = storage.get_estimate(est_id)
    if not est:
        raise HTTPException(404, "Estimate not found")
    try:
        return await analyze_estimate(est)
    except Exception:
        return {"content": "Анализ временно не завершён. Повторите запрос.", "actions": [], "status": "error"}


@app.post("/api/v1/ai/generate-document")
async def ai_generate_document(
    data: dict,
    request: Request,
    _principal: ProjectPrincipal = Depends(resolve_project_principal),
):
    from app.rate_limiter import chat_limiter, check_rate_limit
    await check_rate_limit(request, chat_limiter)
    from app.ai_provider import generate_document_content
    doc_type = data.get("type", "custom")
    context = data.get("context", "")
    try:
        return await generate_document_content(doc_type, context)
    except Exception:
        return {"content": "Документ временно не сформирован. Повторите запрос.", "actions": [], "status": "error"}


@app.post("/api/v1/ai/suggest")
async def ai_suggest(
    data: dict,
    request: Request,
    _principal: ProjectPrincipal = Depends(resolve_project_principal),
):
    from app.rate_limiter import chat_limiter, check_rate_limit
    await check_rate_limit(request, chat_limiter)
    from app.ai_provider import suggest_search
    query = data.get("query", "")
    if not query:
        raise HTTPException(400, "Query required")
    try:
        return await suggest_search(query)
    except Exception:
        return {"content": "Подсказки временно не сформированы. Повторите запрос.", "actions": [], "status": "error"}


# ---------------------------------------------------------------------------
# Providers — registry, healthcheck, capabilities
# ---------------------------------------------------------------------------

@app.get("/api/v1/providers")
async def list_providers_endpoint(_operator = Depends(require_operator_user)):
    from app.providers import list_providers
    return list_providers()


def _require_platform_owner(user):
    if str(user.role or "").strip().lower() != "owner":
        raise HTTPException(status_code=403, detail="Owner role required")
    return user


@app.get("/api/v1/providers/connections")
async def list_owner_model_connections(
    operator = Depends(require_operator_user),
    db: Session = Depends(get_db),
):
    from app.models import OwnerModelConnectionDB
    from app.owner_provider import public_connection
    _require_platform_owner(operator)
    rows = db.query(OwnerModelConnectionDB).filter(OwnerModelConnectionDB.owner_user_id == operator.id).order_by(OwnerModelConnectionDB.updated_at.desc()).all()
    return {"items": [public_connection(row) for row in rows]}


@app.post("/api/v1/providers/connections/test")
async def test_owner_model_connection(
    data: dict,
    operator = Depends(require_operator_user),
    db: Session = Depends(get_db),
):
    from app.models import OwnerModelConnectionDB
    from app.owner_provider import decrypt_key, now, probe_connection
    _require_platform_owner(operator)
    api_key = str(data.get("api_key") or "")
    saved = db.query(OwnerModelConnectionDB).filter(
        OwnerModelConnectionDB.id == "owner-primary",
        OwnerModelConnectionDB.owner_user_id == operator.id,
    ).first()
    requested_base = str(data.get("base_url") or "").strip().rstrip("/")
    if not api_key and saved is not None and saved.base_url.rstrip("/") == requested_base:
        api_key = decrypt_key(saved.encrypted_api_key)
    try:
        result = await probe_connection(
            str(data.get("base_url") or ""),
            str(data.get("model") or ""),
            api_key,
        )
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if saved is not None:
        saved.last_status = str(result["status"])
        saved.last_checked_at = now()
        db.commit()
    return result


@app.put("/api/v1/providers/connections/primary")
async def save_owner_model_connection(
    data: dict,
    operator = Depends(require_operator_user),
    db: Session = Depends(get_db),
):
    from app.models import OwnerModelConnectionDB
    from app.owner_provider import activate_runtime, encrypt_key, normalize_api_key, now, public_connection, validate_base_url
    _require_platform_owner(operator)
    name = " ".join(str(data.get("name") or "Модель владельца").split())[:120]
    model = " ".join(str(data.get("model") or "").split())[:200]
    if not model:
        raise HTTPException(status_code=422, detail="Model is required")
    try:
        base_url = validate_base_url(str(data.get("base_url") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    row = db.query(OwnerModelConnectionDB).filter(OwnerModelConnectionDB.id == "owner-primary").first()
    timestamp = now()
    if row is None:
        row = OwnerModelConnectionDB(id="owner-primary", owner_user_id=operator.id, name=name, base_url=base_url, model=model, created_at=timestamp, updated_at=timestamp)
        db.add(row)
    elif row.owner_user_id != operator.id:
        raise HTTPException(status_code=403, detail="Connection belongs to another owner")
    api_key = normalize_api_key(str(data.get("api_key") or ""))
    if row is not None and row.base_url.rstrip("/") != base_url and not api_key and urlsplit(base_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(status_code=422, detail="API key is required when changing provider")
    row.name = name
    row.base_url = base_url
    row.model = model
    row.active = bool(data.get("active", True))
    if api_key:
        row.encrypted_api_key = encrypt_key(api_key)
    row.updated_at = timestamp
    db.commit()
    db.refresh(row)
    activate_runtime(row)
    return public_connection(row)


@app.post("/api/v1/voice/speech")
async def synthesize_voice_speech(
    data: dict,
    request: Request,
    _principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    """Synthesize speech through the owner's encrypted MiMo connection."""
    from app.rate_limiter import chat_limiter, check_rate_limit
    from app.mimo_voice import MimoVoiceError, synthesize_mimo_speech
    from app.models import OwnerModelConnectionDB

    await check_rate_limit(request, chat_limiter)
    connection = db.query(OwnerModelConnectionDB).filter(
        OwnerModelConnectionDB.active.is_(True),
    ).order_by(OwnerModelConnectionDB.updated_at.desc()).first()
    if connection is None:
        raise HTTPException(status_code=409, detail="Сначала подключите MiMo в настройках владельца.")
    try:
        speech = await synthesize_mimo_speech(
            connection,
            text=str(data.get("text") or ""),
            voice=str(data.get("voice") or "mimo_default"),
            style=str(data.get("style") or ""),
        )
    except MimoVoiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return Response(
        content=speech.content,
        media_type=speech.media_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": 'inline; filename="kolibri-voice.mp3"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/v1/providers/{provider_id}")
async def get_provider_endpoint(
    provider_id: str,
    _operator = Depends(require_operator_user),
):
    from app.providers import get_provider
    p = get_provider(provider_id)
    if not p:
        raise HTTPException(404, "Provider not found")
    return {
        "id": p.id, "name": p.name, "base_url": p.base_url,
        "protocol": p.protocol, "official": p.official, "custom_proxy": p.custom_proxy,
        "routing_enabled": p.routing_enabled, "credential_source": p.credential_source,
        "model": p.default_model, "has_key": bool(p.api_key),
        "capabilities": {
            "chat": p.capabilities.chat, "models": p.capabilities.models,
            "streaming": p.capabilities.streaming, "tools": p.capabilities.tools,
            "json_schema": p.capabilities.json_schema, "files": p.capabilities.files,
            "batch": p.capabilities.batch,
        },
    }


@app.post("/api/v1/providers/{provider_id}/healthcheck")
async def healthcheck_provider(
    provider_id: str,
    _operator = Depends(require_operator_user),
):
    from app.healthcheck import probe_provider
    return await probe_provider(provider_id)


@app.post("/api/v1/providers/test-all")
async def test_all_providers(_operator = Depends(require_operator_user)):
    """Run bounded, sanitized server-credential probes for every registered route."""
    import asyncio

    from app.healthcheck import probe_provider
    from app.providers import PROVIDERS

    provider_ids = list(PROVIDERS)
    probe_results = await asyncio.gather(*(probe_provider(provider_id) for provider_id in provider_ids))
    results = dict(zip(provider_ids, probe_results, strict=True))
    return {"status": "completed", "providers": results}


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
@app.get("/api/v1/templates")
async def list_templates():
    from app.templates import list_templates as _list
    return _list()


@app.get("/api/v1/templates/{template_id}")
async def get_template(template_id: str):
    from app.templates import get_template as _get
    t = _get(template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    return t


@app.post("/api/v1/templates/{template_id}/create-document", status_code=201)
async def create_document_from_template(
    template_id: str,
    db: Session = Depends(get_db),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
):
    from app.templates import get_template as _get
    t = _get(template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    return storage.create_document({
        "title": t["title"], "type": t["type"], "content": t["content"],
    })


@app.post("/api/v1/templates/{template_id}/render")
async def render_template_endpoint(
    template_id: str,
    data: dict,
    _principal: ProjectPrincipal = Depends(resolve_project_principal),
):
    from app.templates import get_template as _get, render_template as _render
    t = _get(template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    variables = data.get("variables", {})
    rendered = _render(t["content"], variables)
    return {"title": t["title"], "content": rendered, "variables": t["variables"]}


# ---------------------------------------------------------------------------
# Price Catalog
# ---------------------------------------------------------------------------

@app.get("/api/v1/catalog")
async def list_catalog(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    region: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    from app.models import CatalogItemDB
    q = db.query(CatalogItemDB)
    if category:
        q = q.filter(CatalogItemDB.category == category)
    if region:
        q = q.filter(CatalogItemDB.region == region)
    if search:
        q = q.filter(CatalogItemDB.name.ilike(f"%{search}%"))
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [{"id": i.id, "code": i.code, "name": i.name, "unit": i.unit,
                   "price": i.price, "category": i.category, "region": i.region,
                   "source": i.source} for i in items],
        "total": total, "page": page, "page_size": page_size,
    }


@app.get("/api/v1/catalog/categories")
async def list_catalog_categories(db: Session = Depends(get_db)):
    from app.models import CatalogItemDB
    from sqlalchemy import func
    cats = db.query(CatalogItemDB.category, func.count()).group_by(CatalogItemDB.category).order_by(func.count().desc()).all()
    return [{"category": c, "count": n} for c, n in cats]


@app.get("/api/v1/catalog/stats")
async def catalog_stats(db: Session = Depends(get_db)):
    from app.models import CatalogItemDB
    from sqlalchemy import func
    total = db.query(CatalogItemDB).count()
    regions = db.query(CatalogItemDB.region, func.count()).group_by(CatalogItemDB.region).all()
    cats = db.query(CatalogItemDB.category, func.count()).group_by(CatalogItemDB.category).order_by(func.count().desc()).all()
    return {
        "total": total,
        "regions": len(regions),
        "categories": len(cats),
        "by_region": {r: c for r, c in regions},
        "top_categories": [{"category": c, "count": n} for c, n in cats[:20]],
    }


# ---------------------------------------------------------------------------
# DOCX export
# ---------------------------------------------------------------------------

@app.get("/api/v1/documents/{doc_id}/docx")
async def document_docx(
    doc_id: str,
    db: Session = Depends(get_db),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
):
    storage = DBStorage(db, principal.scope_id, principal.organization_id)
    result = storage.get_document(doc_id)
    if not result:
        raise HTTPException(404, "Document not found")
    from app.docx_export import html_to_docx
    docx_bytes = html_to_docx(result["title"], result["content"])
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename=document_{doc_id[:8]}.docx'},
    )


@app.post("/api/v1/pdf/generate-docx")
async def generate_docx(
    data: schemas.PDFGenerateRequest,
    request: Request,
    _principal: ProjectPrincipal = Depends(resolve_project_principal),
):
    from app.rate_limiter import api_limiter, check_rate_limit
    await check_rate_limit(request, api_limiter)
    from app.docx_export import html_to_docx
    docx_bytes = html_to_docx(data.title, data.html_content)
    import base64
    b64 = base64.b64encode(docx_bytes).decode()
    return {"docx_base64": b64, "filename": f"{data.title}.docx", "size_bytes": len(docx_bytes)}


# ---------------------------------------------------------------------------
# Web Search
# ---------------------------------------------------------------------------

@app.post("/api/v1/search/web")
async def web_search_endpoint(
    data: dict,
    request: Request,
    _principal: ProjectPrincipal = Depends(resolve_project_principal),
):
    from app.rate_limiter import chat_limiter, check_rate_limit
    await check_rate_limit(request, chat_limiter)
    from app.web_search import search_and_summarize
    query = data.get("query", "")
    if not query:
        raise HTTPException(400, "Query required")
    return {"query": query, "results": await search_and_summarize(query)}


# ---------------------------------------------------------------------------
# Deterministic Search
# ---------------------------------------------------------------------------

@app.post("/api/v1/search")
async def search_endpoint(
    data: dict,
    db: Session = Depends(get_db),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
):
    from app.search_engine import SearchEngine
    query = data.get("query", "")
    if not query:
        raise HTTPException(400, "Query required")
    entity_types = data.get("types")
    limit = data.get("limit", 20)
    engine = SearchEngine(db, principal.scope_id)
    return engine.search_with_context(query, entity_types=entity_types, limit=limit)


# ---------------------------------------------------------------------------
# Client Context
# ---------------------------------------------------------------------------


def _raise_legacy_context_retired() -> None:
    """Fail closed instead of trusting a caller-controlled legacy client id.

    The project/session scoped repositories supersede this in-memory context
    API.  Keeping an explicit tombstone preserves a stable migration signal
    without exposing or deleting any legacy context data.
    """

    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_context_retired",
            "message": "Legacy client context is retired; use project-scoped APIs",
        },
        headers={"Cache-Control": "private, no-store"},
    )


@app.get("/api/v1/context/{client_id}")
async def get_context(client_id: str):
    _raise_legacy_context_retired()


@app.post("/api/v1/context/{client_id}")
async def update_context(client_id: str, data: dict):
    _raise_legacy_context_retired()


@app.post("/api/v1/context/{client_id}/estimate")
async def add_estimate_to_context(client_id: str, data: dict):
    _raise_legacy_context_retired()


@app.post("/api/v1/context/{client_id}/document")
async def add_document_to_context(client_id: str, data: dict):
    _raise_legacy_context_retired()


@app.post("/api/v1/context/{client_id}/message")
async def add_message_to_context(client_id: str, data: dict):
    _raise_legacy_context_retired()


@app.get("/api/v1/context/{client_id}/ai-context")
async def get_ai_context(client_id: str):
    _raise_legacy_context_retired()
