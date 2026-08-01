"""Server-authoritative capability projection for every Product Chat client.

The model provider is deliberately not the source of truth for product tools.
Providers receive the same semantic runtime contract, while this module tells
web, native and admin clients which server-owned capabilities are actually
available for the authenticated tenant.  A capability is never advertised
merely because a button exists in a client.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Request
from typing_extensions import Annotated

from .agent_runtime import (
    ESTIMATES_EXPORT_CAPABILITY_ID,
    ESTIMATES_WORKSPACE_CAPABILITY_ID,
    FILES_ATTACH_CAPABILITY_ID,
    LIVE_WEB_SEARCH_CAPABILITY_ID,
    WEATHER_CURRENT_CAPABILITY_ID,
    AgentRuntimeRegistry,
)
from .database import get_database
from .identity import require_user
from .image_generation import (
    IMAGE_GENERATION_CAPABILITY_ID,
    ImageGenerationProvider,
)
from .schemas import UserSession


CAPABILITY_MANIFEST_SCHEMA_ID = "kolibri.product.capability-manifest"
CAPABILITY_MANIFEST_SCHEMA_VERSION = "1.0"
DEVELOPER_RUNTIME_CAPABILITY_ID = "developer.runtime.execute"

router = APIRouter(prefix="/v1/capabilities", tags=["capabilities"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = Annotated[UserSession, Depends(require_user)]


def _connected_runtime_capabilities(
    database: sqlite3.Connection,
    registry: AgentRuntimeRegistry | None,
    *,
    tenant_id: str,
) -> tuple[set[str], list[dict[str, Any]]]:
    """Return only capabilities from registered, tenant-connected runtimes."""

    if registry is None:
        return set(), []
    start_errors = registry.start_errors()
    connected = {
        str(row["provider_id"])
        for row in database.execute(
            """
            SELECT provider_id
            FROM provider_connections
            WHERE tenant_id = ? AND status = 'connected'
            """,
            (tenant_id,),
        ).fetchall()
    }
    runtime_capabilities: set[str] = set()
    runtimes: list[dict[str, Any]] = []
    for descriptor in registry.descriptors():
        is_connected = (
            descriptor.profile_id in connected
            and descriptor.profile_id not in start_errors
        )
        if is_connected:
            runtime_capabilities.update(descriptor.capabilities.capability_ids)
        runtimes.append(
            {
                "profileId": descriptor.profile_id,
                "runtimeId": descriptor.runtime_id,
                "displayName": descriptor.display_name,
                "connected": is_connected,
                "startError": start_errors.get(descriptor.profile_id),
                "modes": sorted(descriptor.capabilities.modes),
                "capabilityIds": sorted(descriptor.capabilities.capability_ids),
            }
        )
    return runtime_capabilities, runtimes


def _capability(
    capability_id: str,
    *,
    display_name: str,
    available: bool,
    reason: str | None = None,
    source: str = "server",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": capability_id,
        "displayName": display_name,
        "available": available,
        "source": source,
    }
    if reason is not None:
        payload["reason"] = reason
    return payload


def build_capability_manifest(
    request: Request,
    database: sqlite3.Connection,
    identity: UserSession,
) -> dict[str, Any]:
    """Build a bounded capability snapshot for one authenticated tenant."""

    registry = getattr(getattr(request.app, "state", None), "agent_runtime_registry", None)
    if not isinstance(registry, AgentRuntimeRegistry):
        registry = None
    runtime_capabilities, runtimes = _connected_runtime_capabilities(
        database,
        registry,
        tenant_id=identity.tenant_id,
    )

    image_provider = registry.capability(IMAGE_GENERATION_CAPABILITY_ID) if registry else None
    image_available = isinstance(image_provider, ImageGenerationProvider)
    if image_available:
        image_available = image_provider.descriptor.provider_id != "image.unavailable"

    construction_enabled = (
        ESTIMATES_WORKSPACE_CAPABILITY_ID in identity.product_capabilities
    )
    developer_enabled = bool(
        identity.is_platform_owner
        and registry is not None
        and any("developer" in item.capabilities.modes for item in registry.descriptors())
    )
    capabilities = [
        _capability(
            LIVE_WEB_SEARCH_CAPABILITY_ID,
            display_name="Живой веб-поиск",
            available=LIVE_WEB_SEARCH_CAPABILITY_ID in runtime_capabilities,
            reason=(
                None
                if LIVE_WEB_SEARCH_CAPABILITY_ID in runtime_capabilities
                else "Подключите runtime с разрешённым веб-поиском."
            ),
            source="runtime",
        ),
        _capability(
            WEATHER_CURRENT_CAPABILITY_ID,
            display_name="Текущая погода",
            available=True,
            source="server",
        ),
        _capability(
            FILES_ATTACH_CAPABILITY_ID,
            display_name="Файлы и вложения",
            available=True,
            source="server",
        ),
        _capability(
            IMAGE_GENERATION_CAPABILITY_ID,
            display_name="Генерация изображений",
            available=image_available,
            reason=(
                None
                if image_available
                else "Провайдер генерации изображений не настроен."
            ),
            source="server",
        ),
        _capability(
            ESTIMATES_WORKSPACE_CAPABILITY_ID,
            display_name="Интерактивные сметы",
            available=construction_enabled,
            reason=(
                None
                if construction_enabled
                else "Для этого vertical pack нужен активный доступ организации."
            ),
            source="entitlement",
        ),
        _capability(
            ESTIMATES_EXPORT_CAPABILITY_ID,
            display_name="Экспорт документов сметы",
            available=construction_enabled,
            reason=(
                None
                if construction_enabled
                else "Для этого vertical pack нужен активный доступ организации."
            ),
            source="entitlement",
        ),
    ]
    if identity.is_platform_owner:
        capabilities.append(
            _capability(
                DEVELOPER_RUNTIME_CAPABILITY_ID,
                display_name="Режим разработки",
                available=developer_enabled,
                reason=(
                    None
                    if developer_enabled
                    else "Trusted developer runtime не подключён."
                ),
                source="owner-policy",
            )
        )

    return {
        "schemaId": CAPABILITY_MANIFEST_SCHEMA_ID,
        "schemaVersion": CAPABILITY_MANIFEST_SCHEMA_VERSION,
        "capabilities": capabilities,
        "runtimes": runtimes,
    }


@router.get("")
def capability_manifest(
    request: Request,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, Any]:
    return build_capability_manifest(request, database, identity)
