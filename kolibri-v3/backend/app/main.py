from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .agent_operations import router as agent_operations_router
from .agent_runtime import AgentRuntimeRegistry
from .attachments import router as attachments_router
from .config import Settings
from .chat.cancellation import ActiveRunCancellationRegistry
from .chat.execution_adapter import DirectRunDispatcher
from .chat.router import router as chat_router
from .database import connect_database, initialize_database, migration_paths
from .direct_model_runtime import build_agent_runtime_registry
from .document_catalog import router as document_catalog_router
from .identity import router as identity_router
from .image_generation import (
    IMAGE_GENERATION_CAPABILITY_ID,
    ImageGenerationProvider,
    UnavailableImageGenerationProvider,
)
from .estimate_engine_router import router as estimate_engine_router
from .generated_image_artifacts import router as generated_artifacts_router
from .local_provider_authority import ensure_local_provider_master_key
from .market_catalog_router import router as market_catalog_router
from .model_catalog import router as model_catalog_router
from .normative_router import router as normative_router
from .platform_admin import router as platform_admin_router
from .provider_connections import router as provider_connections_router
from .provider_execution import (
    ProviderExecutionSecurity,
    ProviderExecutionService,
    router as provider_execution_router,
)
from .runtime_readiness import product_worker_is_ready
from .project_artifacts import router as project_artifacts_router
from .project_context import router as project_context_router
from .pricing_router import router as pricing_router
from .storage_admin import router as storage_admin_router
from .storage_node_executor import (
    StorageNodeExecutor,
)
from .storage_node_rust_adapter import build_storage_node_executor
from .trusted_agent_control import router as trusted_agent_control_router


NO_STORE_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
}
_RELEASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RELEASE_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_HTTP_LOGGER = logging.getLogger("kolibri.v3.http")


def _release_identity_from_environment() -> tuple[dict[str, str] | None, bool]:
    raw_release_id = os.getenv("KOLIBRI_RELEASE_ID", "")
    raw_release_commit = os.getenv("KOLIBRI_RELEASE_COMMIT", "")
    if not raw_release_id and not raw_release_commit:
        return None, True
    release_id = raw_release_id.strip()
    release_commit = raw_release_commit.strip()
    if (
        release_id != raw_release_id
        or release_commit != raw_release_commit
        or _RELEASE_ID_PATTERN.fullmatch(release_id) is None
        or _RELEASE_COMMIT_PATTERN.fullmatch(release_commit) is None
    ):
        return None, False
    return {
        "releaseId": release_id,
        "releaseCommit": release_commit,
    }, True


def _public_release_id() -> str:
    release_identity, valid = _release_identity_from_environment()
    if not valid or release_identity is None:
        return "unversioned"
    return release_identity["releaseId"]


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


def create_app(
    settings: Settings | None = None,
    *,
    image_generation_provider: ImageGenerationProvider | None = None,
    storage_node_executor: StorageNodeExecutor | None = None,
) -> FastAPI:
    configured = settings or Settings.from_env()
    configured_image_provider = (
        image_generation_provider or UnavailableImageGenerationProvider()
    )
    configured_storage_executor = (
        storage_node_executor
        if storage_node_executor is not None
        else build_storage_node_executor(configured)
    )
    # Validate the injected identity/version at composition time, not after a
    # user has already received an accepted AG-UI run.
    configured_image_provider.descriptor

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        initialize_database(configured.database_url)
        if configured.environment == "development":
            ensure_local_provider_master_key(configured)
        app.state.settings = configured
        app.state.storage_node_executor = configured_storage_executor
        app.state.run_cancellations = ActiveRunCancellationRegistry()
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
        agent_runtimes.register_capability(
            IMAGE_GENERATION_CAPABILITY_ID,
            configured_image_provider,
        )
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
        direct_model_executor = (
            ThreadPoolExecutor(max_workers=2, thread_name_prefix="kolibri-model")
            if configured.direct_model_runtime_enabled
            else None
        )
        app.state.direct_model_executor = direct_model_executor
        direct_run_dispatcher = (
            DirectRunDispatcher(
                settings=configured,
                executor=direct_model_executor,
                runtime_registry=agent_runtimes,
                cancellations=app.state.run_cancellations,
            )
            if direct_model_executor is not None
            else None
        )
        app.state.direct_run_dispatcher = direct_run_dispatcher
        app.state.image_generation_provider = configured_image_provider
        if direct_run_dispatcher is not None:
            direct_run_dispatcher.start()
        try:
            yield
        finally:
            if direct_run_dispatcher is not None:
                direct_run_dispatcher.close()
            app.state.run_cancellations.close()
            if direct_model_executor is not None:
                direct_model_executor.shutdown(
                    wait=False,
                    cancel_futures=True,
                )
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
    app.state.storage_node_executor = configured_storage_executor
    app.state.run_cancellations = ActiveRunCancellationRegistry()
    app.state.direct_model_executor = None
    app.state.direct_run_dispatcher = None
    app.state.image_generation_provider = configured_image_provider
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(configured.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "Last-Event-ID",
            "Origin",
            "X-CSRF-Token",
            "X-Kolibri-Filename",
            "X-Kolibri-Project-Id",
            "X-Kolibri-Thread-Id",
        ],
        expose_headers=[
            "Location",
            "WWW-Authenticate",
            "X-Kolibri-Content-SHA256",
            "X-Kolibri-Run-Id",
        ],
        max_age=600,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        request_id = f"req_{uuid.uuid4().hex}"
        started = time.monotonic()
        response = None
        response_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        try:
            response = await call_next(request)
            response_status = response.status_code
        finally:
            route = request.scope.get("route")
            route_template = getattr(route, "path", None)
            if not isinstance(route_template, str) or len(route_template) > 256:
                route_template = "unmatched"
            method = request.method
            if not re.fullmatch(r"[A-Z]{3,16}", method):
                method = "UNKNOWN"
            _HTTP_LOGGER.info(
                json.dumps(
                    {
                        "durationMs": round(
                            (time.monotonic() - started) * 1000,
                            3,
                        ),
                        "event": "http_request_complete",
                        "method": method,
                        "releaseId": _public_release_id(),
                        "requestId": request_id,
                        "route": route_template,
                        "status": response_status,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
        if response is None:
            raise RuntimeError("request completed without a response")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Kolibri-Release", _public_release_id())
        response.headers.setdefault("X-Request-ID", request_id)
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

    @app.get("/v1/live", include_in_schema=False)
    def liveness() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "kolibri-v3",
            "component": "backend",
        }

    @app.get(
        "/v1/health",
        include_in_schema=False,
        response_model=None,
    )
    def health() -> dict[str, str] | JSONResponse:
        try:
            connection = connect_database(configured.database_url)
            try:
                schema_version = int(
                    connection.execute("PRAGMA user_version").fetchone()[0]
                )
            finally:
                connection.close()
            latest_schema = int(
                migration_paths()[-1].name.split("_", 1)[0]
            )
            if schema_version != latest_schema:
                raise RuntimeError("database schema is not current")
        except Exception:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "unavailable",
                    "service": "kolibri-v3",
                    "code": "database_not_ready",
                },
                headers=NO_STORE_HEADERS,
            )
        release_identity, release_identity_valid = (
            _release_identity_from_environment()
        )
        if (
            not release_identity_valid
            or (
                configured.environment == "production"
                and release_identity is None
            )
        ):
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "unavailable",
                    "service": "kolibri-v3",
                    "code": "release_identity_not_configured",
                },
                headers=NO_STORE_HEADERS,
            )
        payload = {"status": "ok", "service": "kolibri-v3"}
        if release_identity is not None:
            payload.update(release_identity)
        if configured.environment == "development":
            dev_instance_id = os.getenv(
                "KOLIBRI_V3_DEV_INSTANCE_ID",
                "",
            ).strip()
            if dev_instance_id:
                payload["instanceId"] = dev_instance_id
        return payload

    @app.get(
        "/v1/ready",
        include_in_schema=False,
        response_model=None,
    )
    def readiness(request: Request) -> dict[str, str] | JSONResponse:
        base = health()
        if isinstance(base, JSONResponse):
            return base

        raw_worker_required = os.getenv(
            "KOLIBRI_V3_REQUIRE_PRODUCT_WORKER",
            "false",
        ).strip().lower()
        if raw_worker_required not in {
            "0",
            "1",
            "false",
            "true",
        }:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "unavailable",
                    "service": "kolibri-v3",
                    "code": "runtime_boundary_not_configured",
                },
                headers=NO_STORE_HEADERS,
            )
        product_worker_required = raw_worker_required in {"1", "true"}

        if configured.direct_model_runtime_enabled:
            registry = request.app.state.agent_runtime_registry
            chat_profiles = {
                descriptor.profile_id
                for descriptor in registry.descriptors()
                if "chat" in descriptor.capabilities.modes
            }
            start_errors = registry.start_errors()
            if not chat_profiles or chat_profiles.issubset(start_errors):
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={
                        "status": "unavailable",
                        "service": "kolibri-v3",
                        "code": "direct_runtime_not_ready",
                    },
                    headers=NO_STORE_HEADERS,
                )

        if product_worker_required:
            release_identity, valid = _release_identity_from_environment()
            try:
                heartbeat_ttl = int(
                    os.getenv(
                        "KOLIBRI_V3_WORKER_HEARTBEAT_TTL_SECONDS",
                        "30",
                    )
                )
            except ValueError:
                heartbeat_ttl = 0
            worker_ready = False
            if valid and release_identity is not None:
                connection = connect_database(configured.database_url)
                try:
                    worker_ready = product_worker_is_ready(
                        connection,
                        release_id=release_identity["releaseId"],
                        release_commit=release_identity["releaseCommit"],
                        max_age_seconds=heartbeat_ttl,
                    )
                finally:
                    connection.close()
            if not worker_ready:
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={
                        "status": "unavailable",
                        "service": "kolibri-v3",
                        "code": "product_worker_not_ready",
                    },
                    headers=NO_STORE_HEADERS,
                )
        return base

    app.include_router(identity_router)
    app.include_router(attachments_router)
    app.include_router(generated_artifacts_router)
    app.include_router(chat_router)
    app.include_router(provider_connections_router)
    app.include_router(provider_execution_router)
    app.include_router(model_catalog_router)
    app.include_router(platform_admin_router)
    app.include_router(trusted_agent_control_router)
    app.include_router(agent_operations_router)
    app.include_router(storage_admin_router)
    app.include_router(project_artifacts_router)
    app.include_router(estimate_engine_router)
    app.include_router(project_context_router)
    app.include_router(document_catalog_router)
    app.include_router(pricing_router)
    app.include_router(market_catalog_router)
    app.include_router(normative_router)
    return app


app = create_app()
