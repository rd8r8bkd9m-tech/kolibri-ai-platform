"""Fail-closed runtime assembly for ``uvicorn kolibri_edge.runtime:create_app_from_env --factory``."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI

from .app import EdgeSettings, create_app
from .http_core import HttpCoreClient


class RuntimeConfigurationError(ValueError):
    """Raised when an explicit edge/Core runtime setting is unsafe or absent."""


@dataclass(frozen=True)
class EdgeRuntimeSettings:
    allowed_origins: tuple[str, ...]
    core_base_url: str
    connect_timeout_seconds: float = 1.0
    read_timeout_seconds: float = 35.0
    sse_wait_seconds: float = 10.0
    force_secure_cookie: bool = False

    def __post_init__(self) -> None:
        if not self.allowed_origins:
            raise RuntimeConfigurationError("KOLIBRI_EDGE_ALLOWED_ORIGINS is required")
        if any(origin.strip() == "*" for origin in self.allowed_origins):
            raise RuntimeConfigurationError("wildcard origins are forbidden")
        try:
            EdgeSettings(allowed_origins=self.allowed_origins)
        except ValueError as exc:
            raise RuntimeConfigurationError("allowed origins are invalid") from exc
        object.__setattr__(
            self, "core_base_url", _loopback_core_url(self.core_base_url)
        )
        _bounded_float("connect timeout", self.connect_timeout_seconds, 0.05, 5.0)
        _bounded_float("read timeout", self.read_timeout_seconds, 1.0, 40.0)
        _bounded_float("SSE wait", self.sse_wait_seconds, 0.05, 30.0)
        if self.read_timeout_seconds < self.sse_wait_seconds + 0.5:
            raise RuntimeConfigurationError("read timeout must exceed SSE wait")

    @classmethod
    def from_env(
        cls, environ: Mapping[str, str] | None = None
    ) -> "EdgeRuntimeSettings":
        source = os.environ if environ is None else environ
        origins_raw = source.get("KOLIBRI_EDGE_ALLOWED_ORIGINS", "")
        origins = tuple(item.strip() for item in origins_raw.split(",") if item.strip())
        core_base_url = source.get("KOLIBRI_RESPONSE_CORE_URL", "").strip()
        if not core_base_url:
            raise RuntimeConfigurationError("KOLIBRI_RESPONSE_CORE_URL is required")
        return cls(
            allowed_origins=origins,
            core_base_url=core_base_url,
            connect_timeout_seconds=_environment_float(
                source,
                "KOLIBRI_CORE_CONNECT_TIMEOUT_SECONDS",
                1.0,
            ),
            read_timeout_seconds=_environment_float(
                source,
                "KOLIBRI_CORE_READ_TIMEOUT_SECONDS",
                35.0,
            ),
            sse_wait_seconds=_environment_float(
                source,
                "KOLIBRI_EDGE_SSE_WAIT_SECONDS",
                10.0,
            ),
            force_secure_cookie=_environment_bool(
                source,
                "KOLIBRI_EDGE_FORCE_SECURE_COOKIE",
                False,
            ),
        )


def create_runtime_app(
    settings: EdgeRuntimeSettings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    timeout = httpx.Timeout(
        connect=settings.connect_timeout_seconds,
        read=settings.read_timeout_seconds,
        write=settings.connect_timeout_seconds,
        pool=settings.connect_timeout_seconds,
    )
    client = httpx.AsyncClient(
        base_url=settings.core_base_url,
        timeout=timeout,
        limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        follow_redirects=False,
        trust_env=False,
        transport=transport,
        headers={"User-Agent": "kolibri-edge/response-core-v1"},
    )
    core = HttpCoreClient(client)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            await client.aclose()

    app = create_app(
        core=core,
        settings=EdgeSettings(
            allowed_origins=settings.allowed_origins,
            force_secure_cookie=settings.force_secure_cookie,
            sse_wait_seconds=settings.sse_wait_seconds,
        ),
        lifespan=lifespan,
    )
    app.state.core_base_url = settings.core_base_url
    app.state.core_transport = "loopback-http"
    return app


def create_app_from_env() -> FastAPI:
    """Uvicorn factory; required settings are read only when invoked."""

    return create_runtime_app(EdgeRuntimeSettings.from_env())


def _loopback_core_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as exc:
        raise RuntimeConfigurationError("Core base URL is invalid") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname is None
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeConfigurationError(
            "Core base URL must be an explicit loopback HTTP origin"
        )
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError as exc:
        raise RuntimeConfigurationError(
            "Core base URL must use a loopback IP literal"
        ) from exc
    if not address.is_loopback:
        raise RuntimeConfigurationError("Core base URL must use a loopback IP literal")
    host = f"[{address}]" if address.version == 6 else str(address)
    return f"http://{host}:{port}"


def _bounded_float(name: str, value: float, minimum: float, maximum: float) -> None:
    if not minimum <= value <= maximum:
        raise RuntimeConfigurationError(f"{name} is outside its bounded range")


def _environment_float(source: Mapping[str, str], name: str, default: float) -> float:
    raw = source.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeConfigurationError(f"{name} must be numeric") from exc


def _environment_bool(source: Mapping[str, str], name: str, default: bool) -> bool:
    raw = source.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true"}:
        return True
    if normalized in {"0", "false"}:
        return False
    raise RuntimeConfigurationError(f"{name} must be true/false or 1/0")
