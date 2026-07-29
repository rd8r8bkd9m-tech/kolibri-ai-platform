from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .agent_runtime import AgentRuntimeRegistry
from .config import Settings
from .chat.router import router as chat_router
from .database import connect_database, initialize_database
from .direct_model_runtime import build_agent_runtime_registry
from .document_catalog import router as document_catalog_router
from .identity import router as identity_router
from .estimate_engine_router import router as estimate_engine_router
from .local_provider_authority import ensure_local_provider_master_key
from .market_catalog_router import router as market_catalog_router
from .model_catalog import router as model_catalog_router
from .normative_router import router as normative_router
from .provider_connections import router as provider_connections_router
from .provider_execution import (
    ProviderExecutionSecurity,
    ProviderExecutionService,
    router as provider_execution_router,
)
from .project_artifacts import router as project_artifacts_router
from .project_context import router as project_context_router
from .pricing_router import router as pricing_router


NO_STORE_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
}


def _public_error(
    status_code: int,
    *,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    response_headers = {**NO_STORE_HEADERS, **(headers or {})}
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message},
        headers=response_headers,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        initialize_database(configured.database_url)
        if configured.environment == "development":
            ensure_local_provider_master_key(configured)
        app.state.settings = configured
        agent_runtimes = AgentRuntimeRegistry()
        if (
            configured.direct_model_runtime_enabled
            or configured.provider_execution_enabled
        ):
            database_path = Path(configured.database_url.removeprefix("sqlite:///"))
            if not database_path.is_absolute():
                database_path = (Path.cwd() / database_path).resolve()
            agent_runtimes = build_agent_runtime_registry(
                configured,
                runtime_root=database_path.parent / "agent-runtimes",
            )
            agent_runtimes.start_all()
        app.state.agent_runtime_registry = agent_runtimes
        app.state.provider_execution_security = None
        app.state.provider_execution_service = None
        if configured.provider_execution_enabled:
            app.state.provider_execution_security = (
                ProviderExecutionSecurity.from_settings(configured)
            )
            app.state.provider_execution_service = ProviderExecutionService(
                settings=configured,
                runtime_registry=agent_runtimes,
            )
        app.state.direct_model_executor = (
            ThreadPoolExecutor(max_workers=2, thread_name_prefix="kolibri-model")
            if configured.direct_model_runtime_enabled
            else None
        )
        try:
            yield
        finally:
            executor = app.state.direct_model_executor
            if executor is not None:
                executor.shutdown(wait=False, cancel_futures=True)
            agent_runtimes.close_all()

    app = FastAPI(
        title="Kolibri V3",
        version="1.0.0",
        docs_url=None if configured.environment == "production" else "/docs",
        redoc_url=None,
        openapi_url=(
            None if configured.environment == "production" else "/openapi.json"
        ),
        lifespan=lifespan,
    )
    app.state.settings = configured
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(configured.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Content-Type",
            "Idempotency-Key",
            "Origin",
            "X-CSRF-Token",
        ],
        max_age=600,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if request.url.path.startswith("/v1/"):
            response.headers.setdefault("Cache-Control", "no-store")
            response.headers.setdefault("Pragma", "no-cache")
        return response

    @app.exception_handler(HTTPException)
    async def http_error(
        _request: Request,
        error: HTTPException,
    ) -> JSONResponse:
        if isinstance(error.detail, dict):
            raw_code = error.detail.get("code")
            raw_message = error.detail.get("message")
            if isinstance(raw_code, str) and isinstance(raw_message, str):
                return _public_error(
                    error.status_code,
                    code=raw_code,
                    message=raw_message,
                    headers=error.headers,
                )
        return _public_error(
            error.status_code,
            code=f"http_{error.status_code}",
            message="Request could not be completed.",
            headers=error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        _request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        return _public_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="invalid_request",
            message="Request fields are invalid.",
        )

    @app.get("/v1/health", include_in_schema=False)
    def health() -> dict[str, str]:
        connection = connect_database(configured.database_url)
        try:
            connection.execute("SELECT 1").fetchone()
        finally:
            connection.close()
        return {"status": "ok", "service": "kolibri-v3"}

    app.include_router(identity_router)
    app.include_router(chat_router)
    app.include_router(provider_connections_router)
    app.include_router(provider_execution_router)
    app.include_router(model_catalog_router)
    app.include_router(project_artifacts_router)
    app.include_router(estimate_engine_router)
    app.include_router(project_context_router)
    app.include_router(document_catalog_router)
    app.include_router(pricing_router)
    app.include_router(market_catalog_router)
    app.include_router(normative_router)
    return app


app = create_app()
