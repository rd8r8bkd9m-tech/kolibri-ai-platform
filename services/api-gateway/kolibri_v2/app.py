from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .artifact_service import ArtifactService
from .capabilities import CapabilityRegistry
from .config import Settings
from .engine import DeterministicEngine
from .errors import APIError, api_error_handler, validation_error_handler
from .store import Store
from .routers import api_keys, artifacts, estimates, governance, openai_compat, projects, responses, runtime, shell


@asynccontextmanager
async def lifespan(app: FastAPI):
    await app.state.engine.reconcile()
    yield


def create_app() -> FastAPI:
    settings = Settings.load()
    store = Store(settings.db_path)
    for raw_key, role, name in settings.bootstrap_api_keys:
        store.seed_api_key(raw_key, role, name)
    app = FastAPI(title="Kolibri AI OS V2.1", version="2.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.capabilities = CapabilityRegistry()
    app.state.artifacts = ArtifactService(settings, store)
    app.state.engine = DeterministicEngine(store)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    @app.middleware("http")
    async def request_metadata(request: Request, call_next):
        started = time.perf_counter()
        request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex}"
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["Server-Timing"] = f"app;dur={(time.perf_counter()-started)*1000:.1f}"
        if request.url.path.startswith(("/v1", "/api")):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.get("/health")
    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "kolibri-v2-api", "authority": "home"}

    @app.get("/ready")
    @app.get("/api/ready")
    def ready():
        store.fetchone("SELECT 1 AS ok")
        return {"status": "ready", "database": "ok", "artifact_store": "ok"}

    @app.exception_handler(404)
    async def not_found(request: Request, _):
        if request.url.path.startswith(("/v1", "/api")):
            return JSONResponse(status_code=404, content={"error": {"message": f"The resource '{request.url.path}' does not exist.", "type": "invalid_request_error", "param": None, "code": "resource_not_found"}})
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    for router in [shell.router, api_keys.router, projects.router, responses.router, estimates.router, artifacts.router, governance.router, runtime.router]:
        app.include_router(router)
    # Always include generic provider gateway last so native Kolibri routes win.
    app.include_router(openai_compat.router)
    return app


app = create_app()
