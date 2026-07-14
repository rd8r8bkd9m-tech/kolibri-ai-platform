"""Truthful, dynamic capability registry for Kolibri.

The registry deliberately separates a static capability *catalog* from runtime
evidence.  A catalog entry, a configured credential, or a renderer import does
not by itself prove that a capability works.  ``available`` is emitted only
when all hard gates pass and at least one permitted route has a fresh,
successful invocation probe.

The module is transport-agnostic.  API routers may consume :meth:`snapshot`
and :meth:`self_description`, but endpoint wiring does not belong here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Any, TypeAlias


class Availability(StrEnum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ProbeState(StrEnum):
    NEVER = "never"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CapabilityNotInvocable(RuntimeError):
    """Raised when a caller attempts a capability without an available verdict."""

    def __init__(self, capability_id: str, *, status: str, reason_code: str) -> None:
        self.capability_id = capability_id
        self.status = status
        self.reason_code = reason_code
        super().__init__(f"{capability_id}:{status}:{reason_code}")


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    """Static product metadata; never execution evidence."""

    id: str
    name: str
    description: str
    kind: str
    renderer_required: bool = True
    catalog_listed: bool = True

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("capability id must not be empty")
        if not self.name.strip():
            raise ValueError("capability name must not be empty")


@dataclass(frozen=True, slots=True)
class PolicyEvidence:
    """Result of an actual policy decision for the current scope."""

    evaluated: bool
    permitted: bool
    decision_id: str | None = None
    checked_at: datetime | None = None
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class RendererEvidence:
    """Renderer registration and its optional runtime health result."""

    renderer_id: str | None
    registered: bool
    healthy: bool | None
    checked_at: datetime | None = None
    evidence_id: str | None = None


@dataclass(frozen=True, slots=True)
class CredentialEvidence:
    """Sanitised credential evidence; secret material is never stored here."""

    required: bool
    present: bool
    source: str
    source_permitted: bool = True
    checked_at: datetime | None = None
    evidence_id: str | None = None
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class InvocationProbe:
    """A bounded invocation result for one concrete execution route."""

    state: ProbeState = ProbeState.NEVER
    checked_at: datetime | None = None
    ttl_seconds: int = 900
    evidence_id: str | None = None
    error_code: str | None = None
    provider: str | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, ProbeState):
            object.__setattr__(self, "state", ProbeState(self.state))
        if self.ttl_seconds <= 0:
            raise ValueError("probe ttl_seconds must be positive")
        if self.state is ProbeState.NEVER and self.checked_at is not None:
            raise ValueError("a never-run probe cannot have checked_at")
        if self.state is not ProbeState.NEVER and self.checked_at is None:
            raise ValueError("a completed probe requires checked_at")


@dataclass(frozen=True, slots=True)
class RouteEvidence:
    route_id: str
    configured: bool
    permitted: bool
    credential: CredentialEvidence
    probe: InvocationProbe = field(default_factory=InvocationProbe)

    def __post_init__(self) -> None:
        if not self.route_id.strip():
            raise ValueError("route id must not be empty")


@dataclass(frozen=True, slots=True)
class CapabilityEvidence:
    policy: PolicyEvidence
    renderer: RendererEvidence | None
    routes: tuple[RouteEvidence, ...]


EvidenceProvider: TypeAlias = Callable[[], CapabilityEvidence]


_REASON_MESSAGES_RU: dict[str, str] = {
    "live_invocation": "Есть свежий успешный вызов разрешённого маршрута.",
    "policy_not_evaluated": "Политика доступа для возможности не проверена.",
    "policy_denied": "Политика текущего сеанса запрещает эту возможность.",
    "renderer_missing": "Интерфейс результата не зарегистрирован.",
    "renderer_unhealthy": "Интерфейс результата не прошёл проверку работоспособности.",
    "renderer_health_unverified": "Работоспособность интерфейса результата ещё не подтверждена.",
    "route_missing": "Нет зарегистрированного маршрута исполнения.",
    "route_not_configured": "Маршрут исполнения не настроен.",
    "route_not_permitted": "Маршрут исполнения запрещён политикой.",
    "credential_missing": "Для разрешённого маршрута отсутствует требуемая авторизация.",
    "credential_source_forbidden": "Источник авторизации запрещён политикой.",
    "probe_not_run": "Маршрут настроен, но реальный вызов ещё не проверен.",
    "probe_stale": "Последнее доказательство вызова устарело.",
    "invocation_failed": "Все проверенные маршруты завершили реальный вызов ошибкой.",
    "evidence_provider_failed": "Не удалось безопасно получить runtime-доказательства.",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return _as_utc(value).isoformat() if value is not None else None


def _probe_is_fresh(probe: InvocationProbe, now: datetime) -> bool:
    if probe.checked_at is None:
        return False
    age = (_as_utc(now) - _as_utc(probe.checked_at)).total_seconds()
    return 0 <= age <= probe.ttl_seconds


def _reason(code: str) -> dict[str, str]:
    return {"code": code, "message": _REASON_MESSAGES_RU[code]}


def _route_payload(route: RouteEvidence, now: datetime) -> dict[str, Any]:
    probe_fresh = _probe_is_fresh(route.probe, now)
    credential_ready = (
        (not route.credential.required or route.credential.present)
        and route.credential.source_permitted
    )
    return {
        "id": route.route_id,
        "configured": route.configured,
        "permitted": route.permitted,
        "credential": {
            "required": route.credential.required,
            "present": route.credential.present,
            "source": route.credential.source,
            "source_permitted": route.credential.source_permitted,
            "ready": credential_ready,
            "checked_at": _iso(route.credential.checked_at),
            "evidence_id": route.credential.evidence_id,
            "reason_code": route.credential.reason_code,
        },
        "probe": {
            "state": route.probe.state.value,
            "fresh": probe_fresh,
            "checked_at": _iso(route.probe.checked_at),
            "ttl_seconds": route.probe.ttl_seconds,
            "evidence_id": route.probe.evidence_id,
            "error_code": route.probe.error_code,
            "provider": route.probe.provider,
            "model": route.probe.model,
        },
    }


def evaluate_capability(
    spec: CapabilitySpec,
    evidence: CapabilityEvidence,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Derive a fail-closed capability verdict from concrete evidence."""

    observed_at = _as_utc(now or _utc_now())
    routes = tuple(evidence.routes)
    route_payloads = [_route_payload(route, observed_at) for route in routes]

    status: Availability
    reason_code: str
    verified_at: datetime | None = None
    selected_route_id: str | None = None

    if not evidence.policy.evaluated:
        status, reason_code = Availability.UNAVAILABLE, "policy_not_evaluated"
    elif not evidence.policy.permitted:
        status, reason_code = Availability.UNAVAILABLE, "policy_denied"
    elif spec.renderer_required and (
        evidence.renderer is None or not evidence.renderer.registered
    ):
        status, reason_code = Availability.UNAVAILABLE, "renderer_missing"
    elif spec.renderer_required and evidence.renderer and evidence.renderer.healthy is False:
        status, reason_code = Availability.UNAVAILABLE, "renderer_unhealthy"
    elif not routes:
        status, reason_code = Availability.UNAVAILABLE, "route_missing"
    else:
        eligible: list[RouteEvidence] = []
        hard_reason_codes: list[str] = []
        for route in routes:
            if not route.configured:
                hard_reason_codes.append("route_not_configured")
                continue
            if not route.permitted:
                hard_reason_codes.append("route_not_permitted")
                continue
            if not route.credential.source_permitted:
                hard_reason_codes.append("credential_source_forbidden")
                continue
            if route.credential.required and not route.credential.present:
                hard_reason_codes.append("credential_missing")
                continue
            eligible.append(route)

        live_routes = [
            route
            for route in eligible
            if route.probe.state is ProbeState.SUCCEEDED
            and _probe_is_fresh(route.probe, observed_at)
        ]
        if live_routes:
            selected = max(
                live_routes,
                key=lambda route: _as_utc(route.probe.checked_at)  # type: ignore[arg-type]
            )
            selected_route_id = selected.route_id
            verified_at = selected.probe.checked_at
            if spec.renderer_required and evidence.renderer and evidence.renderer.healthy is None:
                status, reason_code = Availability.DEGRADED, "renderer_health_unverified"
            else:
                status, reason_code = Availability.AVAILABLE, "live_invocation"
        elif not eligible:
            status = Availability.UNAVAILABLE
            reason_code = hard_reason_codes[0] if hard_reason_codes else "route_missing"
        else:
            probes = [route.probe for route in eligible]
            if any(probe.state is ProbeState.NEVER for probe in probes):
                status, reason_code = Availability.DEGRADED, "probe_not_run"
            elif any(not _probe_is_fresh(probe, observed_at) for probe in probes):
                status, reason_code = Availability.DEGRADED, "probe_stale"
            else:
                status, reason_code = Availability.UNAVAILABLE, "invocation_failed"

    renderer = evidence.renderer
    return {
        "id": spec.id,
        "name": spec.name,
        "description": spec.description,
        "kind": spec.kind,
        "catalog_listed": spec.catalog_listed,
        "status": status.value,
        "invocable": status is Availability.AVAILABLE,
        "reason": _reason(reason_code),
        "verified_at": _iso(verified_at),
        "selected_route_id": selected_route_id,
        "policy": {
            "evaluated": evidence.policy.evaluated,
            "permitted": evidence.policy.permitted,
            "decision_id": evidence.policy.decision_id,
            "checked_at": _iso(evidence.policy.checked_at),
            "reason_code": evidence.policy.reason_code,
        },
        "renderer": {
            "required": spec.renderer_required,
            "id": renderer.renderer_id if renderer else None,
            "registered": renderer.registered if renderer else False,
            "healthy": renderer.healthy if renderer else None,
            "checked_at": _iso(renderer.checked_at) if renderer else None,
            "evidence_id": renderer.evidence_id if renderer else None,
        },
        "routes": route_payloads,
        "source": {
            "type": "live_invocation"
            if status is Availability.AVAILABLE
            else "runtime_evidence",
        },
    }


@dataclass(frozen=True, slots=True)
class _Registration:
    spec: CapabilitySpec
    evidence_provider: EvidenceProvider


class CapabilityRegistry:
    """Thread-safe registry whose evidence providers are evaluated per read."""

    schema_version = "kolibri.capabilities.v1"

    def __init__(self) -> None:
        self._registrations: dict[str, _Registration] = {}
        self._invocation_overrides: dict[tuple[str, str], InvocationProbe] = {}
        self._lock = RLock()

    def register(self, spec: CapabilitySpec, evidence_provider: EvidenceProvider) -> None:
        if not callable(evidence_provider):
            raise TypeError("evidence_provider must be callable")
        with self._lock:
            if spec.id in self._registrations:
                raise ValueError(f"capability already registered: {spec.id}")
            self._registrations[spec.id] = _Registration(spec, evidence_provider)

    def unregister(self, capability_id: str) -> None:
        with self._lock:
            self._registrations.pop(capability_id, None)
            self._invocation_overrides = {
                key: probe
                for key, probe in self._invocation_overrides.items()
                if key[0] != capability_id
            }

    def record_invocation(
        self,
        capability_id: str,
        route_id: str,
        *,
        succeeded: bool,
        checked_at: datetime | None = None,
        ttl_seconds: int = 900,
        evidence_id: str | None = None,
        error_code: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        """Record a sanitised real invocation result for a registered route.

        This method never accepts provider output or credentials.  Callers
        should persist durable probe evidence elsewhere and pass only its
        opaque ``evidence_id`` here.
        """

        observed_at = _as_utc(checked_at or _utc_now())
        with self._lock:
            registration = self._registrations.get(capability_id)
            if registration is None:
                raise KeyError(f"unknown capability: {capability_id}")
            try:
                route_ids = {route.route_id for route in registration.evidence_provider().routes}
            except Exception as exc:
                raise KeyError(f"runtime evidence unavailable for capability: {capability_id}") from exc
            if route_id not in route_ids:
                raise KeyError(f"unknown route for {capability_id}: {route_id}")
            self._invocation_overrides[(capability_id, route_id)] = InvocationProbe(
                state=ProbeState.SUCCEEDED if succeeded else ProbeState.FAILED,
                checked_at=observed_at,
                ttl_seconds=ttl_seconds,
                evidence_id=evidence_id,
                error_code=None if succeeded else (error_code or "invocation_failed"),
                provider=provider,
                model=model,
            )

    def clear_invocation(self, capability_id: str, route_id: str) -> None:
        """Remove an in-process probe override, primarily for runtime reset/tests."""

        with self._lock:
            self._invocation_overrides.pop((capability_id, route_id), None)

    def _apply_invocation_overrides(
        self,
        capability_id: str,
        evidence: CapabilityEvidence,
    ) -> CapabilityEvidence:
        with self._lock:
            overrides = {
                route_id: probe
                for (registered_id, route_id), probe in self._invocation_overrides.items()
                if registered_id == capability_id
            }
        if not overrides:
            return evidence
        routes = tuple(
            replace(route, probe=overrides.get(route.route_id, route.probe))
            for route in evidence.routes
        )
        return replace(evidence, routes=routes)

    def _evaluate_registration(
        self,
        registration: _Registration,
        observed_at: datetime,
    ) -> dict[str, Any]:
        try:
            evidence = registration.evidence_provider()
            if not isinstance(evidence, CapabilityEvidence):
                raise TypeError("invalid evidence provider result")
            evidence = self._apply_invocation_overrides(registration.spec.id, evidence)
            return evaluate_capability(registration.spec, evidence, now=observed_at)
        except Exception as exc:  # fail closed and never leak exception text
            return {
                "id": registration.spec.id,
                "name": registration.spec.name,
                "description": registration.spec.description,
                "kind": registration.spec.kind,
                "catalog_listed": registration.spec.catalog_listed,
                "status": Availability.UNAVAILABLE.value,
                "invocable": False,
                "reason": _reason("evidence_provider_failed"),
                "verified_at": None,
                "selected_route_id": None,
                "policy": {"evaluated": False, "permitted": False},
                "renderer": {
                    "required": registration.spec.renderer_required,
                    "id": None,
                    "registered": False,
                    "healthy": None,
                },
                "routes": [],
                "source": {"type": "runtime_evidence"},
                "error_type": type(exc).__name__,
            }

    def get(self, capability_id: str, *, now: datetime | None = None) -> dict[str, Any] | None:
        """Return the current derived verdict, or ``None`` for an unknown id."""

        observed_at = _as_utc(now or _utc_now())
        with self._lock:
            registration = self._registrations.get(capability_id)
        if registration is None:
            return None
        return self._evaluate_registration(registration, observed_at)

    def assert_invocable(
        self,
        capability_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Return an available verdict or raise a structured fail-closed error."""

        capability = self.get(capability_id, now=now)
        if capability is None:
            raise KeyError(f"unknown capability: {capability_id}")
        if capability.get("invocable") is not True:
            reason = capability.get("reason")
            reason_code = str(reason.get("code")) if isinstance(reason, Mapping) else "unavailable"
            raise CapabilityNotInvocable(
                capability_id,
                status=str(capability.get("status") or Availability.UNAVAILABLE.value),
                reason_code=reason_code,
            )
        return capability

    def snapshot(self, *, now: datetime | None = None) -> dict[str, Any]:
        observed_at = _as_utc(now or _utc_now())
        with self._lock:
            registrations = tuple(self._registrations.values())

        capabilities: list[dict[str, Any]] = []
        for registration in registrations:
            result = self._evaluate_registration(registration, observed_at)
            capabilities.append(result)

        capabilities.sort(key=lambda item: (item["kind"], item["name"], item["id"]))
        counts = {
            status.value: sum(item["status"] == status.value for item in capabilities)
            for status in Availability
        }
        if capabilities and counts[Availability.AVAILABLE.value] == len(capabilities):
            overall = Availability.AVAILABLE
        elif counts[Availability.AVAILABLE.value] or counts[Availability.DEGRADED.value]:
            overall = Availability.DEGRADED
        else:
            overall = Availability.UNAVAILABLE
        return {
            "schema_version": self.schema_version,
            "status": overall.value,
            "as_of": observed_at.isoformat(),
            "counts": counts,
            "capabilities": capabilities,
        }

    def self_description(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Return safe dynamic data for a ``Что ты умеешь?`` response."""

        return capability_self_description(self.snapshot(now=now))


def capability_self_description(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Build user-facing and machine-readable capability response data.

    Only capabilities whose derived verdict is ``available`` are phrased as
    things Kolibri can currently do.  Degraded and unavailable entries remain
    visible as honest runtime state, never as promises.
    """

    raw_capabilities = snapshot.get("capabilities")
    capabilities = [
        dict(item)
        for item in raw_capabilities
        if isinstance(raw_capabilities, list) and isinstance(item, Mapping)
    ] if isinstance(raw_capabilities, list) else []
    grouped = {
        status.value: [item for item in capabilities if item.get("status") == status.value]
        for status in Availability
    }

    available_names = [str(item.get("name") or item.get("id")) for item in grouped["available"]]
    degraded_names = [str(item.get("name") or item.get("id")) for item in grouped["degraded"]]
    unavailable_names = [str(item.get("name") or item.get("id")) for item in grouped["unavailable"]]

    parts = ["Я — Колибри, единая AI-операционная система."]
    if available_names:
        parts.append("Сейчас подтверждено, что я могу: " + ", ".join(available_names) + ".")
    else:
        parts.append("Сейчас нет возможностей с подтверждённым успешным вызовом.")
    if degraded_names:
        parts.append("Ограниченно доступно, требуется повторная проверка: " + ", ".join(degraded_names) + ".")
    if unavailable_names:
        parts.append("Сейчас недоступно: " + ", ".join(unavailable_names) + ".")

    return {
        "schema_version": "kolibri.capability-response.v1",
        "intent": "capability_self_description",
        "identity": {"id": "kolibri", "name": "Колибри"},
        "content": " ".join(parts),
        "status": snapshot.get("status", Availability.UNAVAILABLE.value),
        "as_of": snapshot.get("as_of"),
        "capabilities": grouped,
    }


# Canonical process-local registry.  Composition code registers evidence
# providers during application startup; routers only read/assert/record through
# the functions below.  Durable evidence remains owned by the caller's data
# plane rather than by this in-memory index.
runtime_registry = CapabilityRegistry()


def register_capability(spec: CapabilitySpec, evidence_provider: EvidenceProvider) -> None:
    runtime_registry.register(spec, evidence_provider)


def get_capability(
    capability_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    return runtime_registry.get(capability_id, now=now)


def assert_invocable(
    capability_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    return runtime_registry.assert_invocable(capability_id, now=now)


def record_invocation(
    capability_id: str,
    route_id: str,
    *,
    succeeded: bool,
    checked_at: datetime | None = None,
    ttl_seconds: int = 900,
    evidence_id: str | None = None,
    error_code: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> None:
    runtime_registry.record_invocation(
        capability_id,
        route_id,
        succeeded=succeeded,
        checked_at=checked_at,
        ttl_seconds=ttl_seconds,
        evidence_id=evidence_id,
        error_code=error_code,
        provider=provider,
        model=model,
    )


__all__ = [
    "Availability",
    "CapabilityEvidence",
    "CapabilityNotInvocable",
    "CapabilityRegistry",
    "CapabilitySpec",
    "CredentialEvidence",
    "InvocationProbe",
    "PolicyEvidence",
    "ProbeState",
    "RendererEvidence",
    "RouteEvidence",
    "assert_invocable",
    "capability_self_description",
    "evaluate_capability",
    "get_capability",
    "record_invocation",
    "register_capability",
    "runtime_registry",
]
