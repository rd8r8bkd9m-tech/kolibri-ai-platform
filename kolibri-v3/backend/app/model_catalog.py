"""Provider-neutral, tenant-aware model and runtime profile catalog."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from typing_extensions import Annotated

from .agent_runtime import AgentRuntimeDescriptor, AgentRuntimeRegistry
from .database import get_database
from .identity import require_user
from .schemas import AgentProfile, UserSession


router = APIRouter(prefix="/v1/models", tags=["models"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = Annotated[UserSession, Depends(require_user)]

_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_OPTION_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


@dataclass(frozen=True, slots=True)
class ModelCatalogEntry:
    id: str
    profile: AgentProfile
    display_name: str
    description: str
    available: bool
    supported_reasoning_efforts: tuple[tuple[str, str], ...] = ()
    default_reasoning_effort: str | None = None
    service_tiers: tuple[tuple[str, str, str], ...] = ()
    is_default: bool = False
    upgrade: str | None = None
    selection_supported: bool = True

    def as_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "profile": self.profile.value,
            "displayName": self.display_name,
            "description": self.description,
            "available": self.available,
            "supportedReasoningEfforts": [
                {
                    "id": effort_id,
                    "description": description,
                }
                for effort_id, description in self.supported_reasoning_efforts
            ],
            "defaultReasoningEffort": self.default_reasoning_effort,
            "serviceTiers": [
                {
                    "id": tier_id,
                    "name": name,
                    "description": description,
                }
                for tier_id, name, description in self.service_tiers
            ],
            "isDefault": self.is_default,
            "upgrade": self.upgrade,
            "selectionSupported": self.selection_supported,
        }


@dataclass(frozen=True, slots=True)
class ProfileCatalogEntry:
    id: AgentProfile
    runtime_id: str
    display_name: str
    available: bool
    model_catalog_available: bool
    model_selection_supported: bool
    modes: tuple[str, ...]

    def as_payload(self) -> dict[str, Any]:
        return {
            "id": self.id.value,
            "runtimeId": self.runtime_id,
            "displayName": self.display_name,
            "available": self.available,
            "modelCatalogAvailable": self.model_catalog_available,
            "modelSelectionSupported": self.model_selection_supported,
            "modes": list(self.modes),
        }


@dataclass(frozen=True, slots=True)
class ModelCatalogSnapshot:
    models: tuple[ModelCatalogEntry, ...]
    profiles: tuple[ProfileCatalogEntry, ...]

    def profile(self, profile_id: str) -> ProfileCatalogEntry | None:
        return next(
            (
                profile
                for profile in self.profiles
                if profile.id.value == profile_id
            ),
            None,
        )


def _provider_statuses(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
) -> dict[str, str]:
    rows = database.execute(
        """
        SELECT provider_id, status
        FROM provider_connections
        WHERE tenant_id = ?
        """,
        (tenant_id,),
    ).fetchall()
    return {
        str(row["provider_id"]): str(row["status"])
        for row in rows
    }


def _runtime_registry(request: Request) -> AgentRuntimeRegistry | None:
    registry = getattr(
        getattr(request.app, "state", None),
        "agent_runtime_registry",
        None,
    )
    return registry if isinstance(registry, AgentRuntimeRegistry) else None


def _field(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _bounded_text(
    value: object,
    *,
    field: str,
    maximum: int,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    normalized = value.strip()
    if (not normalized and not allow_empty) or len(normalized) > maximum:
        raise ValueError(f"{field} is invalid")
    return normalized


def _reasoning_efforts(value: object) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("supported reasoning efforts are invalid")
    efforts: list[tuple[str, str]] = []
    for raw in value:
        if isinstance(raw, Mapping):
            effort_id = raw.get("id")
            description = raw.get("description", "")
        elif isinstance(raw, (list, tuple)) and len(raw) == 2:
            effort_id, description = raw
        else:
            raise ValueError("supported reasoning effort is invalid")
        normalized_id = _bounded_text(
            effort_id,
            field="reasoning effort",
            maximum=32,
        )
        if not _OPTION_ID.fullmatch(normalized_id):
            raise ValueError("reasoning effort is invalid")
        efforts.append(
            (
                normalized_id,
                _bounded_text(
                    description,
                    field="reasoning effort description",
                    maximum=240,
                    allow_empty=True,
                ),
            )
        )
    if len({effort_id for effort_id, _description in efforts}) != len(efforts):
        raise ValueError("reasoning effort IDs must be unique")
    return tuple(efforts)


def _service_tiers(value: object) -> tuple[tuple[str, str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("service tiers are invalid")
    tiers: list[tuple[str, str, str]] = []
    for raw in value:
        if isinstance(raw, Mapping):
            tier_id = raw.get("id")
            name = raw.get("name")
            description = raw.get("description", "")
        elif isinstance(raw, (list, tuple)) and len(raw) == 3:
            tier_id, name, description = raw
        else:
            raise ValueError("service tier is invalid")
        normalized_id = _bounded_text(
            tier_id,
            field="service tier",
            maximum=32,
        )
        if not _OPTION_ID.fullmatch(normalized_id):
            raise ValueError("service tier is invalid")
        tiers.append(
            (
                normalized_id,
                _bounded_text(name, field="service tier name", maximum=80),
                _bounded_text(
                    description,
                    field="service tier description",
                    maximum=240,
                    allow_empty=True,
                ),
            )
        )
    if len({tier_id for tier_id, _name, _description in tiers}) != len(tiers):
        raise ValueError("service tier IDs must be unique")
    return tuple(tiers)


def _model_entry(
    raw: object,
    *,
    profile: AgentProfile,
    available: bool,
) -> ModelCatalogEntry:
    model_id = _bounded_text(_field(raw, "id"), field="model id", maximum=120)
    if not _MODEL_ID.fullmatch(model_id):
        raise ValueError("model id is invalid")
    efforts = _reasoning_efforts(
        _field(raw, "supported_reasoning_efforts", ())
    )
    default_effort_value = _field(raw, "default_reasoning_effort")
    default_effort = (
        None
        if default_effort_value is None
        else _bounded_text(
            default_effort_value,
            field="default reasoning effort",
            maximum=32,
        )
    )
    if default_effort is not None and default_effort not in {
        effort_id for effort_id, _description in efforts
    }:
        raise ValueError("default reasoning effort is not advertised")
    upgrade_value = _field(raw, "upgrade")
    upgrade = (
        None
        if upgrade_value is None
        else _bounded_text(upgrade_value, field="model upgrade", maximum=120)
    )
    return ModelCatalogEntry(
        id=model_id,
        profile=profile,
        display_name=_bounded_text(
            _field(raw, "display_name"),
            field="model display name",
            maximum=120,
        ),
        description=_bounded_text(
            _field(raw, "description", ""),
            field="model description",
            maximum=1_000,
            allow_empty=True,
        ),
        available=available,
        supported_reasoning_efforts=efforts,
        default_reasoning_effort=default_effort,
        service_tiers=_service_tiers(_field(raw, "service_tiers", ())),
        is_default=bool(_field(raw, "is_default", False)),
        upgrade=upgrade,
    )


def _profile_models(
    registry: AgentRuntimeRegistry,
    descriptor: AgentRuntimeDescriptor,
    *,
    available: bool,
) -> tuple[tuple[ModelCatalogEntry, ...], bool]:
    profile = AgentProfile(descriptor.profile_id)
    runtime = registry.require(descriptor.profile_id)
    if not descriptor.capabilities.model_catalog:
        return (
            (
                ModelCatalogEntry(
                    id=descriptor.profile_id,
                    profile=profile,
                    display_name=descriptor.display_name,
                    description=(
                        "Модель выбирается зарегистрированным runtime-профилем."
                    ),
                    available=available,
                    is_default=True,
                    selection_supported=False,
                ),
            ),
            True,
        )

    backend = runtime.model_catalog_backend
    list_models = getattr(backend, "list_models", None)
    if backend is None or not callable(list_models):
        return (), False
    try:
        advertised = tuple(list_models(timeout=10.0))
        entries = tuple(
            _model_entry(
                raw,
                profile=profile,
                available=available,
            )
            for raw in advertised
        )
    except Exception:
        # Runtime catalogs are untrusted execution-plane input. An invalid or
        # unavailable catalog fails closed and is never replaced by another
        # provider's models.
        return (), False
    if not entries or len({entry.id for entry in entries}) != len(entries):
        return (), False
    return entries, True


def _load_snapshot(
    request: Request,
    database: sqlite3.Connection,
    *,
    tenant_id: str,
) -> ModelCatalogSnapshot:
    statuses = _provider_statuses(database, tenant_id=tenant_id)
    registry = _runtime_registry(request)
    models: list[ModelCatalogEntry] = [
        ModelCatalogEntry(
            id="auto",
            profile=AgentProfile.AUTO,
            display_name="Авто",
            description="Kolibri выберет доступный runtime для задачи.",
            available=True,
            is_default=True,
            selection_supported=False,
        )
    ]
    profiles: list[ProfileCatalogEntry] = []
    if registry is None:
        return ModelCatalogSnapshot(models=tuple(models), profiles=())

    for descriptor in registry.descriptors():
        available = statuses.get(descriptor.profile_id) == "connected"
        profile_models, catalog_available = _profile_models(
            registry,
            descriptor,
            available=available,
        )
        models.extend(profile_models)
        profiles.append(
            ProfileCatalogEntry(
                id=AgentProfile(descriptor.profile_id),
                runtime_id=descriptor.runtime_id,
                display_name=descriptor.display_name,
                available=available,
                model_catalog_available=catalog_available,
                model_selection_supported=(
                    descriptor.capabilities.model_catalog
                ),
                modes=tuple(sorted(descriptor.capabilities.modes)),
            )
        )
    return ModelCatalogSnapshot(
        models=tuple(models),
        profiles=tuple(profiles),
    )


def load_model_catalog(
    request: Request,
    database: sqlite3.Connection,
    *,
    tenant_id: str,
) -> tuple[tuple[ModelCatalogEntry, ...], bool]:
    """Return models and the legacy Codex catalog availability projection."""

    snapshot = _load_snapshot(request, database, tenant_id=tenant_id)
    legacy_profile = snapshot.profile(AgentProfile.CODEX_CLI.value)
    return (
        snapshot.models,
        (
            legacy_profile.model_catalog_available
            if legacy_profile is not None
            else False
        ),
    )


def validate_profile_selection(
    request: Request,
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    profile: AgentProfile,
) -> ProfileCatalogEntry | None:
    """Validate that a runtime profile is registered and currently usable.

    Automatic routing is owned by Logical Home and therefore does not require
    an execution-plane descriptor. Every concrete profile must be present in
    the live runtime registry, expose a usable catalog contract, and have an
    exact tenant-qualified provider connection. No alternate runtime is used
    when any of those conditions fails.
    """

    profile_id = AgentProfile(profile).value
    if profile_id == AgentProfile.AUTO.value:
        return None
    snapshot = _load_snapshot(request, database, tenant_id=tenant_id)
    selected = snapshot.profile(profile_id)
    if selected is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "agent_profile_not_registered",
                "message": "Выбранный runtime-профиль не зарегистрирован.",
            },
        )
    if not selected.model_catalog_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "model_catalog_unavailable",
                "message": (
                    "Каталог выбранного runtime сейчас недоступен. "
                    "Повторите запрос позже."
                ),
            },
        )
    if not selected.available:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "model_provider_not_connected",
                "message": (
                    "Сначала подключите runtime в разделе "
                    "«Модели и подключения»."
                ),
            },
        )
    return selected


def validate_model_selection(
    request: Request,
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    profile: AgentProfile,
    model: str | None,
    reasoning_effort: str | None,
    service_tier: str | None = None,
) -> ModelCatalogEntry:
    snapshot = _load_snapshot(request, database, tenant_id=tenant_id)
    profile_id = AgentProfile(profile).value
    profile_catalog = (
        None
        if profile_id == AgentProfile.AUTO.value
        else snapshot.profile(profile_id)
    )
    if profile_catalog is None and profile_id != AgentProfile.AUTO.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "agent_profile_not_registered",
                "message": "Выбранный runtime-профиль не зарегистрирован.",
            },
        )
    selected = next(
        (
            entry
            for entry in snapshot.models
            if entry.profile.value == profile_id and entry.id == model
        ),
        None,
    )
    if selected is None:
        if (
            profile_catalog is not None
            and not profile_catalog.model_catalog_available
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "model_catalog_unavailable",
                    "message": (
                        "Каталог выбранного runtime сейчас недоступен. "
                        "Повторите запрос позже."
                    ),
                },
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "model_not_supported",
                "message": "Выбранная модель не поддерживается.",
            },
        )
    if not selected.available:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "model_provider_not_connected",
                "message": (
                    "Сначала подключите runtime в разделе "
                    "«Модели и подключения»."
                ),
            },
        )
    supported_efforts = {
        effort_id
        for effort_id, _description in selected.supported_reasoning_efforts
    }
    if supported_efforts:
        if reasoning_effort not in supported_efforts:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "reasoning_effort_not_supported",
                    "message": (
                        "Выбранный уровень рассуждений недоступен для модели."
                    ),
                },
            )
    elif reasoning_effort is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "reasoning_effort_not_supported",
                "message": "Эта модель не поддерживает настройку рассуждений.",
            },
        )
    supported_service_tiers = {
        tier_id
        for tier_id, _name, _description in selected.service_tiers
    }
    if service_tier is not None and service_tier not in supported_service_tiers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "service_tier_not_supported",
                "message": "Выбранная скорость недоступна для этой модели.",
            },
        )
    return selected


@router.get("/catalog")
def get_model_catalog(
    request: Request,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, Any]:
    snapshot = _load_snapshot(
        request,
        database,
        tenant_id=identity.tenant_id,
    )
    legacy_profile = snapshot.profile(AgentProfile.CODEX_CLI.value)
    legacy_default = next(
        (
            entry
            for entry in snapshot.models
            if entry.profile is AgentProfile.CODEX_CLI and entry.is_default
        ),
        None,
    )
    return {
        "models": [entry.as_payload() for entry in snapshot.models],
        "profiles": [profile.as_payload() for profile in snapshot.profiles],
        # Compatibility fields remain until the current web client migrates to
        # the profile descriptors above. They are projections, not routing
        # inputs, and never create or substitute a runtime.
        "codexCatalogAvailable": (
            legacy_profile.model_catalog_available
            if legacy_profile is not None
            else False
        ),
        "configuredCodexModel": (
            legacy_default.id if legacy_default is not None else None
        ),
        "configuredCodexEffort": (
            legacy_default.default_reasoning_effort
            if legacy_default is not None
            else None
        ),
    }
