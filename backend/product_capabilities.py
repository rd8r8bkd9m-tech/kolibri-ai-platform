"""Fail-closed product capability projection for the Kolibri Shell.

Installed skills, a configured provider, or a frontend catalog entry are not
proof that a customer-facing capability works.  A capability is public only
when all three release facts are true at the same time:

* the concrete backend route is invocable;
* a provider route has recent verified-completion health;
* every renderer required by the result is wired in this release.

The public projection contains available capabilities only.  Operator-facing
diagnostics keep the individual gates and stable reason codes, but never
provider credentials, topology, prompts, or raw errors.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "kolibri.product-capabilities.v1"
HEALTH_MAX_AGE_SECONDS = 300.0


@dataclass(frozen=True)
class ProductCapability:
    id: str
    label: str
    category: str
    surface: str
    method: str
    path: str
    route_enabled: bool
    provider_scope: str
    renderers: tuple[str, ...]
    required_tools: tuple[str, ...] = ()


# This is deliberately conservative.  ``chat`` and the estimate/PDF surfaces
# below have concrete React consumers in the current Shell.  Registry-only
# entries such as image, DOCX, XLSX and web preview are not considered renderers
# until their actual interactive components and browser tests exist.
RELEASE_RENDERERS: Mapping[str, bool] = {
    "chat": True,
    "estimate_editor": True,
    "pdf_viewer": True,
    "image_canvas": True,
    "document_editor": False,
    "spreadsheet_editor": False,
    "code_workspace": False,
    "web_preview": False,
    "app_preview": False,
}


PRODUCT_CAPABILITIES: tuple[ProductCapability, ...] = (
    ProductCapability(
        "question_answering", "Ответы и объяснения", "conversation", "core",
        "POST", "/v1/responses", True, "general", ("chat",),
    ),
    ProductCapability(
        "web_research", "Поиск и исследование", "research", "core",
        "POST", "/v1/responses", True, "general", ("chat",),
        ("tool:web_search",),
    ),
    ProductCapability(
        "writing", "Тексты и редактирование", "content", "core",
        "POST", "/v1/responses", True, "general", ("chat",),
    ),
    ProductCapability(
        "translation", "Перевод", "content", "core",
        "POST", "/v1/responses", True, "general", ("chat",),
    ),
    ProductCapability(
        "code_assistance", "Помощь с кодом", "code", "core",
        "POST", "/v1/responses", True, "general", ("chat",),
    ),
    ProductCapability(
        "image", "Изображение", "media", "tool",
        "POST", "/v1/responses", True, "image_generation", ("image_canvas",),
        ("tool:image_generation",),
    ),
    ProductCapability(
        "document", "Документ", "documents", "tool",
        "POST", "/v1/responses", True, "general", ("document_editor", "pdf_viewer"),
    ),
    ProductCapability(
        "spreadsheet", "Таблица XLSX", "documents", "capability",
        "POST", "/v1/responses", False, "general", ("spreadsheet_editor",),
    ),
    ProductCapability(
        "estimate", "Смета", "construction", "tool",
        "POST", "/v1/responses", True, "general", ("estimate_editor", "pdf_viewer"),
        ("tool:web_search",),
    ),
    ProductCapability(
        "site", "Сайт", "software", "tool",
        "POST", "/v1/responses", False, "code", ("code_workspace", "web_preview"),
    ),
    ProductCapability(
        "app", "Приложение", "software", "tool",
        "POST", "/v1/responses", False, "code", ("code_workspace", "app_preview"),
    ),
)


_IMAGE_NOUNS = (
    r"(?:изображени(?:е|я|й)|картин(?:ку|ка|ки)|иллюстраци(?:ю|я|и)|"
    r"портрет(?:а|ы|ов)?|фото(?:графи(?:ю|я|и))?|image|picture|illustration|portrait|photo)"
)
_IMAGE_ACTIONS = r"(?:сгенериру(?:й|йте)|созда(?:й|йте)|нарису(?:й|йте)|сдела(?:й|йте)|generate|create|draw|make)"
_IMAGE_REQUEST = re.compile(
    rf"(?:{_IMAGE_ACTIONS}.{{0,80}}{_IMAGE_NOUNS}|{_IMAGE_NOUNS}.{{0,80}}{_IMAGE_ACTIONS})",
    re.IGNORECASE | re.DOTALL,
)
_IMAGE_TEXT_ONLY_REQUEST = re.compile(
    r"(?:созда(?:й|йте)|напиш(?:и|ите)|generate|write).{0,40}"
    r"(?:промпт|prompt|описани(?:е|я)|description)",
    re.IGNORECASE | re.DOTALL,
)


def requested_materialized_capability(input_value: Any) -> str | None:
    """Recognize only high-confidence materialized-result requests.

    A generic mention of an image is not enough.  The explicit action+noun
    shape prevents ordinary Q&A about images from being blocked.
    """

    if isinstance(input_value, str):
        text = input_value
    elif isinstance(input_value, list):
        text = ""
        for item in reversed(input_value):
            if not isinstance(item, dict) or item.get("role") != "user":
                continue
            content = item.get("content")
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = " ".join(
                    str(part.get("text") or "")
                    for part in content
                    if isinstance(part, dict)
                )
            break
    else:
        return None
    bounded = text[:20_000]
    if _IMAGE_TEXT_ONLY_REQUEST.search(bounded):
        return None
    return "image" if _IMAGE_REQUEST.search(bounded) else None


def route_inventory(routes: Iterable[Any]) -> frozenset[tuple[str, str]]:
    facts: set[tuple[str, str]] = set()
    for route in routes:
        candidates = getattr(route, "effective_candidates", None)
        if callable(candidates):
            facts.update(route_inventory(candidates()))
            continue
        path = str(getattr(route, "path", ""))
        for method in getattr(route, "methods", ()) or ():
            facts.add((str(method).upper(), path))
    return frozenset(facts)


def _tool_statuses(capability_envelope: Mapping[str, Any] | None) -> dict[str, bool]:
    data = capability_envelope.get("data") if isinstance(capability_envelope, Mapping) else []
    result: dict[str, bool] = {}
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, Mapping):
            continue
        capability_id = str(item.get("id") or "")
        if not capability_id:
            continue
        result[capability_id] = (
            item.get("status") == "available"
            and item.get("invocable") is True
            and item.get("kind") == "tool"
        )
    return result


def verified_provider_health(gateway: Any, *, now: float | None = None) -> dict[str, bool]:
    """Return only recent, verified provider completion facts.

    A gateway may expose the small public ``verified_product_health`` contract.
    The current factory gateway also retains sanitized circuit-breaker records;
    those records are accepted only when their status is ``healthy`` and their
    TTL/observation time is still current.  Binary discovery and configured
    endpoints are intentionally ignored.
    """

    explicit = getattr(gateway, "verified_product_health", None)
    if callable(explicit):
        try:
            value = explicit()
        except Exception:
            value = None
        if isinstance(value, Mapping):
            return {
                str(key): item is True
                for key, item in value.items()
                if str(key) in {"general", "code", "image_generation"}
            }

    current_monotonic = time.monotonic() if now is None else float(now)
    healthy = False
    local = getattr(gateway, "_factory_local_health", None)
    if isinstance(local, Mapping):
        healthy = any(
            isinstance(record, Mapping)
            and record.get("status") == "healthy"
            and float(record.get("expires_monotonic") or 0.0) > current_monotonic
            for record in local.values()
        )

    # The factory's bounded cache contains already-sanitized Home health
    # records.  Accept it only while the cache itself is recent.
    cache = getattr(gateway, "_factory_health_cache", None)
    if not healthy and isinstance(cache, Mapping):
        for cached in cache.values():
            if not isinstance(cached, tuple) or len(cached) != 2:
                continue
            checked_at, records = cached
            try:
                fresh = current_monotonic - float(checked_at) <= HEALTH_MAX_AGE_SECONDS
            except (TypeError, ValueError):
                fresh = False
            if fresh and isinstance(records, Mapping) and any(
                isinstance(record, Mapping) and record.get("status") == "healthy"
                for record in records.values()
            ):
                healthy = True
                break

    image_health = False
    image_probe = getattr(gateway, "verified_image_generation_health", None)
    if callable(image_probe):
        try:
            image_health = image_probe() is True
        except Exception:
            image_health = False
    return {
        "general": healthy,
        "code": healthy,
        # Image generation needs its own verified artifact completion; a
        # healthy text route must never promote it.
        "image_generation": image_health,
    }


def build_product_capability_matrix(
    *,
    routes: Iterable[Any] | Iterable[tuple[str, str]],
    capability_envelope: Mapping[str, Any] | None,
    provider_health: Mapping[str, bool],
    renderers: Mapping[str, bool] = RELEASE_RENDERERS,
    built_in_tools: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    route_items = tuple(routes)
    route_facts = (
        frozenset((str(method).upper(), str(path)) for method, path in route_items)
        if all(isinstance(item, tuple) and len(item) == 2 for item in route_items)
        else route_inventory(route_items)
    )
    tools = _tool_statuses(capability_envelope)
    tools.update({
        str(tool_id): enabled is True
        for tool_id, enabled in (built_in_tools or {}).items()
    })
    records: list[dict[str, Any]] = []
    for spec in PRODUCT_CAPABILITIES:
        route_exists = (spec.method, spec.path) in route_facts
        invocable = spec.route_enabled and route_exists
        route_healthy = provider_health.get(spec.provider_scope) is True
        required_tools = {
            tool_id: tools.get(tool_id) is True for tool_id in spec.required_tools
        }
        renderer_facts = {
            renderer_id: renderers.get(renderer_id) is True
            for renderer_id in spec.renderers
        }
        renderer_ready = bool(renderer_facts) and all(renderer_facts.values())
        tools_ready = all(required_tools.values())
        available = invocable and route_healthy and renderer_ready and tools_ready
        reasons: list[str] = []
        if not spec.route_enabled:
            reasons.append("capability_route_not_enabled")
        elif not route_exists:
            reasons.append("backend_route_missing")
        if not route_healthy:
            reasons.append("provider_health_unverified")
        if not tools_ready:
            reasons.append("required_tool_unavailable")
        if not renderer_ready:
            reasons.append("renderer_not_ready")
        records.append({
            "id": spec.id,
            "object": "product.capability",
            "label": spec.label,
            "category": spec.category,
            "surface": spec.surface,
            "status": "available" if available else "unavailable",
            "available": available,
            "gates": {
                "invocable": invocable,
                "route_healthy": route_healthy,
                "renderer_ready": renderer_ready,
                "required_tools_ready": tools_ready,
            },
            "reason_codes": reasons,
            "evidence": {
                "route": {"method": spec.method, "path": spec.path, "present": route_exists},
                "provider_scope": spec.provider_scope,
                "renderers": renderer_facts,
                "required_tools": required_tools,
            },
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "object": "list",
        "status": "available" if any(item["available"] for item in records) else "unavailable",
        "data": records,
        "summary": {
            "total": len(records),
            "available": sum(item["available"] for item in records),
            "unavailable": sum(not item["available"] for item in records),
        },
    }


def public_capability_projection(matrix: Mapping[str, Any]) -> dict[str, Any]:
    """Strip all unavailable entries and diagnostic reasons from public UI."""

    records = []
    for item in matrix.get("data", []) if isinstance(matrix, Mapping) else []:
        if not isinstance(item, Mapping) or item.get("available") is not True:
            continue
        records.append({
            "id": str(item.get("id") or ""),
            "object": "product.capability",
            "label": str(item.get("label") or ""),
            "category": str(item.get("category") or ""),
            "surface": str(item.get("surface") or ""),
            "status": "available",
            "available": True,
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "object": "list",
        "status": "available" if records else "unavailable",
        "data": records,
        "summary": {"available": len(records)},
    }
