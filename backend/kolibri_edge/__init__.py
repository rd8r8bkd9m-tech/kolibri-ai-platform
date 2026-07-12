"""Kolibri OpenAI-compatible edge gateway.

The package deliberately contains no durable product authority.  Sessions,
responses, events and cancellation are delegated to an injected ``CoreClient``.
"""

from .app import EdgeSettings, create_app
from .core import (
    CoreClient,
    CoreError,
    CoreEvent,
    PublicPrincipal,
    PublicSession,
    PublicSessionIssue,
)
from .http_core import HttpCoreClient
from .runtime import (
    EdgeRuntimeSettings,
    RuntimeConfigurationError,
    create_app_from_env,
    create_runtime_app,
)

__all__ = [
    "CoreClient",
    "CoreError",
    "CoreEvent",
    "EdgeSettings",
    "EdgeRuntimeSettings",
    "HttpCoreClient",
    "PublicPrincipal",
    "PublicSession",
    "PublicSessionIssue",
    "RuntimeConfigurationError",
    "create_app",
    "create_app_from_env",
    "create_runtime_app",
]
