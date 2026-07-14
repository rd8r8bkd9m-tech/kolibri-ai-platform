"""Capability-gated image generation with verified, retrievable artifact bytes.

The public UI may advertise image generation only after the route is both
configured and verified. A direct chat request is still allowed to probe a
configured route; success promotes the in-process capability to ``live`` and
failure is reported honestly without a fake artifact.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.artifact_store import (
    ArtifactIntegrityError,
    ArtifactNotFound,
    ArtifactStoreError,
    ArtifactValidationError,
    _assert_artifact_scope,
    get_artifact_store,
    router as artifact_store_router,
)
from app.image_validation import InvalidImageBytes, inspect_image_bytes
from app.public_scope import authorize_public_scope, resolve_optional_public_scope


router = APIRouter()
router.include_router(artifact_store_router)
logger = logging.getLogger(__name__)

_MAX_IMAGE_BYTES = 25 * 1024 * 1024
_last_verified_success: str | None = None
_last_verified_monotonic: float | None = None
_last_probe_failure: str | None = None
_last_verified_provider: str | None = None
_last_verified_model: str | None = None
_last_verified_release_id: str | None = None


def _runtime_release_id() -> str:
    from app.capability_runtime import capability_release_id

    return capability_release_id()


def _image_probe_ttl_seconds() -> int:
    from app.capability_runtime import capability_probe_ttl_seconds

    return capability_probe_ttl_seconds("OPENAI_IMAGE_PROBE_TTL_SECONDS")


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=8_000)
    size: Literal["1024x1024", "1024x1536", "1536x1024"] = "1024x1024"
    quality: Literal["low", "medium", "high"] = "high"


class ImageEditRequest(BaseModel):
    source_artifact_id: str = Field(min_length=36, max_length=36)
    prompt: str = Field(min_length=3, max_length=8_000)
    size: Literal["1024x1024", "1024x1536", "1536x1024"] = "1024x1024"
    quality: Literal["low", "medium", "high"] = "high"


class ImageCapabilityUnavailable(RuntimeError):
    """No configured, permitted image provider is available."""


class ImageGenerationFailed(RuntimeError):
    """The configured provider did not return a verified image artifact."""


@dataclass(frozen=True)
class _ImageConfig:
    api_key: str
    base_url: str
    model: str
    enabled: bool
    rest_enabled: bool
    codex_worker_url: str


def _config() -> _ImageConfig:
    enabled = os.getenv("KOLIBRI_IMAGE_GENERATION_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    return _ImageConfig(
        api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        base_url=os.getenv("OPENAI_IMAGE_BASE_URL", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/"),
        model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2").strip() or "gpt-image-2",
        enabled=enabled,
        rest_enabled=os.getenv("OPENAI_REST_IMAGE_ROUTING_ENABLED", "").strip().lower()
        in {"1", "true", "yes", "on"},
        codex_worker_url=os.getenv("KOLIBRI_CODEX_IMAGE_WORKER_URL", "").strip().rstrip("/"),
    )


def _codex_cli_route() -> dict[str, Any]:
    try:
        from app.codex_cli_image_provider import codex_cli_image_configuration

        snapshot = codex_cli_image_configuration()
    except Exception:
        snapshot = {}
    configured = bool(snapshot.get("configured"))
    return {
        "configured": configured,
        "provider": "codex_cli",
        "model": f"codex-cli:{snapshot.get('model') or 'account-default'}",
    }


def _selected_image_route() -> dict[str, Any]:
    config = _config()
    if config.enabled and config.codex_worker_url in {
        "http://127.0.0.1:18016",
        "http://localhost:18016",
    }:
        return {
            "configured": True,
            "provider": "codex_cli",
            "model": "codex-cli:account-default",
            "execution": "local_worker",
            "worker_url": config.codex_worker_url,
        }
    codex_route = _codex_cli_route()
    if config.enabled and codex_route["configured"]:
        return {**codex_route, "execution": "direct"}
    rest_configured = bool(config.enabled and config.rest_enabled and config.api_key)
    if rest_configured:
        return {
            "configured": True,
            "provider": "openai",
            "model": config.model,
            "execution": "rest",
        }
    return {
        "configured": False,
        "provider": "none",
        "model": "none",
        "execution": "none",
    }


def image_execution_identity() -> dict[str, str]:
    route = _selected_image_route()
    state = _read_probe_state()
    global_current = _last_verified_release_id == _runtime_release_id()
    return {
        "provider": str(
            state.get("provider")
            or (_last_verified_provider if global_current else None)
            or route["provider"]
        ),
        "model": str(
            state.get("model")
            or (_last_verified_model if global_current else None)
            or route["model"]
        ),
    }


def image_capability() -> dict[str, Any]:
    config = _config()
    route = _selected_image_route()
    configured = bool(config.enabled and route["configured"])
    probe_ttl = _image_probe_ttl_seconds()
    state = _read_probe_state()
    global_current = _last_verified_release_id == _runtime_release_id()
    verified_at = str(
        state.get("verified_at")
        or (_last_verified_success if global_current else None)
        or ""
    ) or None
    failure_at = str(
        state.get("failure_at")
        or (_last_probe_failure if global_current else None)
        or ""
    ) or None
    state_provider = str(
        state.get("provider")
        or (_last_verified_provider if global_current else None)
        or ""
    ) or None
    verified_age: float | None = None
    if verified_at:
        try:
            verified_age = max(
                0.0,
                (datetime.now(timezone.utc) - datetime.fromisoformat(verified_at)).total_seconds(),
            )
        except ValueError:
            verified_age = None
    verified = bool(
        configured
        and verified_at
        and (
            (
                global_current
                and _last_verified_monotonic is not None
                and time.monotonic() - _last_verified_monotonic <= probe_ttl
            )
            or (verified_age is not None and verified_age <= probe_ttl)
        )
        and failure_at is None
        and state_provider == route["provider"]
    )
    if verified:
        status = "live"
        reason = None
    elif configured:
        status = "partial"
        reason = "The configured image route has not yet returned a verified raster artifact."
    else:
        status = "unavailable"
        reason = "No permitted Codex CLI image route is configured."

    return {
        "id": "image.generate",
        "name": "Изображение",
        "description": "Создать изображение и вернуть проверенные байты артефакта.",
        "kind": "media",
        "status": status,
        "availability_reason": reason,
        "invocable": verified,
        "permitted": config.enabled,
        "route": {
            "configured": configured,
            "healthy": verified,
            "status": status,
            "provider": route["provider"],
            "model": route["model"],
            "verified_at": verified_at,
            "last_failure_at": failure_at,
        },
        "renderer": {"available": True, "id": "image", "status": "live"},
        "source": {"type": "live_invocation" if verified else "configuration"},
    }


def capability_catalog() -> dict[str, Any]:
    """Compatibility entry point backed by the canonical runtime registry."""

    from app.capability_runtime import capability_snapshot

    return capability_snapshot()


IMAGE_CAPABILITY_ID = "image.generate"

_GENERATE_VERBS = re.compile(
    r"\b(созда(?:й|йте|ть)|сгенериру(?:й|йте|ть)|нарису(?:й|йте|овать)|"
    r"изобрази(?:ть|те)?|generate|create|draw|illustrate)\b",
    re.IGNORECASE,
)
_DRAW_VERBS = re.compile(
    r"\b(нарису(?:й|йте|овать)|изобрази(?:ть|те)?|draw|illustrate)\b",
    re.IGNORECASE,
)
_GENERIC_IMAGE_GENERATION_VERBS = re.compile(
    r"\b(сгенериру(?:й|йте|ть)|generate)\b",
    re.IGNORECASE,
)
_IMAGE_NOUNS = re.compile(
    r"\b(изображени(?:е|я)|картинк(?:у|а|и)|портрет(?:а|ы)?|иллюстраци(?:ю|я)|логотип(?:а)?|"
    r"фото(?:графи(?:ю|я))?|обложк(?:у|а)|постер(?:а)?|рендер(?:а)?|визуализаци(?:ю|я)|"
    r"image|picture|photo|portrait|illustration|logo|cover|poster|render)\b",
    re.IGNORECASE,
)
_NON_IMAGE_OUTPUT_NOUNS = re.compile(
    r"\b(текст|стать(?:ю|я)|отч[её]т|смет(?:у|а)|документ|договор|акт|письмо|код|скрипт|"
    r"таблиц(?:у|а)|формул(?:у|а)|список|план|презентаци(?:ю|я)|музык(?:у|а)|песн(?:ю|я)|"
    r"аудио|видео|pdf|docx|xlsx|json|sql|text|article|report|estimate|document|contract|"
    r"letter|code|script|table|formula|list|plan|presentation|music|song|audio|video)\b",
    re.IGNORECASE,
)
_VISUAL_SUBJECT_NOUNS = re.compile(
    r"\b(цвет(?:ы|ок|ка|ами)?|букет(?:а)?|растени(?:е|я)|дерев(?:о|ья)|пейзаж(?:а)?|"
    r"персонаж(?:а)?|животн(?:ое|ого|ые)|кот(?:а|ик)?|собак(?:у|а)|машин(?:у|а)|"
    r"интерьер(?:а)?|экстерьер(?:а)?|сцен(?:у|а)|flowers?|bouquet|plants?|trees?|"
    r"landscape|character|animals?|cats?|dogs?|cars?|interior|exterior|scene)\b",
    re.IGNORECASE,
)


def is_image_generation_request(text: str) -> bool:
    normalized = " ".join(text.split())
    if not normalized or not _GENERATE_VERBS.search(normalized):
        return False
    if _IMAGE_NOUNS.search(normalized):
        return True
    if _NON_IMAGE_OUTPUT_NOUNS.search(normalized):
        return False
    if _DRAW_VERBS.search(normalized):
        return True
    # In ordinary Russian and English product language, bare "generate" plus
    # a visual subject means an image request.  This deliberately catches
    # commands such as "сгенерируй цветы" without turning "сгенерируй отчёт"
    # or "generate code" into an image task.
    return bool(
        _GENERIC_IMAGE_GENERATION_VERBS.search(normalized)
        and _VISUAL_SUBJECT_NOUNS.search(normalized)
    )


def _policy_allows_image(policy: dict[str, Any] | None) -> bool:
    if policy is None:
        return True
    allowed = policy.get("allowed_capabilities")
    if not isinstance(allowed, list):
        return False
    permitted_ids = {str(item) for item in allowed if isinstance(item, str)}
    return bool({IMAGE_CAPABILITY_ID, "openai.image_generation"}.intersection(permitted_ids))


def _image_route_is_invocable(policy: dict[str, Any] | None = None) -> bool:
    capability = image_capability()
    return bool(
        capability.get("permitted") is True
        and isinstance(capability.get("route"), dict)
        and capability["route"].get("configured") is True
        and _policy_allows_image(policy)
    )


def _detect_image_type(data: bytes) -> tuple[str, str]:
    try:
        details = inspect_image_bytes(data, max_bytes=_MAX_IMAGE_BYTES)
    except InvalidImageBytes as exc:
        raise ImageGenerationFailed("Provider output is not a supported image artifact.") from exc
    return details.mime_type, details.extension


def _artifact_root() -> Path:
    return Path(os.getenv("KOLIBRI_ARTIFACT_DIR", "./data/artifacts")).expanduser().resolve() / "images"


def _probe_state_path() -> Path:
    return _artifact_root() / ".capability-state.json"


def _read_probe_state() -> dict[str, Any]:
    """Return the cross-process image capability proof.

    Uvicorn workers do not share Python globals.  Persisting only the small,
    sanitised probe verdict keeps `/v1/capabilities` truthful after a request
    is handled by another worker or after a service restart.
    """
    try:
        payload = json.loads(_probe_state_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 2
        or payload.get("release_id") != _runtime_release_id()
    ):
        return {}
    return payload


def _write_probe_state(*, verified_at: str | None, failure_at: str | None, provider: str | None, model: str | None) -> None:
    root = _artifact_root()
    root.mkdir(parents=True, exist_ok=True)
    target = _probe_state_path()
    temporary = root / f".{target.name}.{uuid.uuid4().hex}.tmp"
    payload = {
        "schema_version": 2,
        "release_id": _runtime_release_id(),
        "verified_at": verified_at,
        "failure_at": failure_at,
        "provider": provider,
        "model": model,
    }
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.chmod(temporary, 0o640)
    temporary.replace(target)


def _store_image(
    data: bytes,
    *,
    prompt: str,
    model: str,
    source_artifact_id: str | None = None,
    scope_id: str | None = None,
) -> dict[str, Any]:
    try:
        details = inspect_image_bytes(data, max_bytes=_MAX_IMAGE_BYTES)
    except InvalidImageBytes as exc:
        raise ImageGenerationFailed("Provider output is not a supported image artifact.") from exc
    mime_type, extension = details.mime_type, details.extension
    try:
        stored = get_artifact_store().put_bytes(
            data,
            artifact_type="image",
            mime_type=mime_type,
            filename=f"kolibri-generated{extension}",
            title="Сгенерированное изображение",
            metadata={
                "prompt": prompt,
                "model": model,
                "width": details.width,
                "height": details.height,
                **(
                    {"scope_key": hashlib.sha256(scope_id.encode()).hexdigest()}
                    if scope_id is not None
                    else {}
                ),
                **(
                    {"source_artifact_id": source_artifact_id}
                    if source_artifact_id is not None
                    else {}
                ),
            },
            route_prefix="/api/v1/artifacts/images",
        )
    except ArtifactStoreError as exc:
        raise ImageGenerationFailed("Image artifact could not be persisted.") from exc
    artifact = {
        "id": stored["id"],
        "type": "image",
        "title": "Сгенерированное изображение",
        "prompt": prompt,
        "mime_type": mime_type,
        "size_bytes": len(data),
        "sha256": stored["sha256"],
        "model": model,
        "created_at": stored["created_at"],
        "url": stored["url"],
        "download_url": stored["download_url"],
        **(
            {"source_artifact_id": source_artifact_id}
            if source_artifact_id is not None
            else {}
        ),
    }
    return artifact


def _source_image_bytes(
    artifact_id: str,
    *,
    scope_id: str | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Open and independently verify one existing raster artifact."""

    try:
        normalized_id = str(uuid.UUID(artifact_id))
        store = get_artifact_store()
        _assert_artifact_scope(store.get(normalized_id), scope_id)
        stored = store.open(normalized_id)
    except (ValueError, ArtifactStoreError) as exc:
        raise ImageGenerationFailed("Source image artifact is not retrievable.") from exc
    if stored.manifest.get("type") != "image":
        raise ImageGenerationFailed("Source artifact is not an image.")
    try:
        details = inspect_image_bytes(stored.content, max_bytes=_MAX_IMAGE_BYTES)
    except InvalidImageBytes as exc:
        raise ImageGenerationFailed("Source image bytes failed validation.") from exc
    if (
        stored.manifest.get("mime_type") != details.mime_type
        or stored.manifest.get("size_bytes") != len(stored.content)
        or stored.manifest.get("sha256") != hashlib.sha256(stored.content).hexdigest()
    ):
        raise ImageGenerationFailed("Source image integrity check failed.")
    return stored.content, stored.manifest


def _extract_image_bytes(payload: dict[str, Any]) -> tuple[bytes | None, str | None]:
    data = payload.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise ImageGenerationFailed("Image provider returned no artifact data.")
    item = data[0]
    encoded = item.get("b64_json")
    if isinstance(encoded, str) and encoded:
        try:
            return base64.b64decode(encoded, validate=True), None
        except (ValueError, TypeError) as exc:
            raise ImageGenerationFailed("Image provider returned invalid encoded bytes.") from exc
    url = item.get("url")
    if isinstance(url, str) and url.startswith(("https://", "http://")):
        return None, url
    raise ImageGenerationFailed("Image provider returned neither image bytes nor a retrievable URL.")


async def generate_image(
    request: ImageGenerationRequest,
    *,
    run_id: str | None = None,
    scope_id: str | None = None,
) -> dict[str, Any]:
    global _last_probe_failure, _last_verified_model, _last_verified_monotonic
    global _last_verified_provider, _last_verified_release_id, _last_verified_success
    config = _config()
    route = _selected_image_route()
    if not config.enabled or not route["configured"]:
        raise ImageCapabilityUnavailable("Image generation is not configured.")
    try:
        if route["provider"] == "codex_cli" and route.get("execution") == "direct":
            from app.codex_cli_image_provider import (
                CodexCLIImageError,
                generate_codex_cli_image,
            )

            try:
                cli_result = await generate_codex_cli_image(
                    request.prompt,
                    size=request.size,
                    quality=request.quality,
                    run_id=run_id,
                )
            except CodexCLIImageError as exc:
                logger.warning(
                    "Codex CLI image attempt failed: %s",
                    getattr(exc, "failure_kind", "codex_cli_image_failed"),
                )
                raise ImageGenerationFailed("Codex CLI did not return a verified image file.") from exc
            image_bytes = cli_result.data
            model = cli_result.model
        elif route["provider"] == "codex_cli" and route.get("execution") == "local_worker":
            timeout = httpx.Timeout(600.0, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{route['worker_url']}/v1/images/generations",
                    json={
                        "prompt": request.prompt,
                        "size": request.size,
                        "quality": request.quality,
                        "run_id": run_id,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                image_bytes, image_url = _extract_image_bytes(payload)
                if image_url is not None:
                    raise ImageGenerationFailed("Local image worker returned a remote URL.")
                model = str(payload.get("model") or route["model"])
        else:
            headers = {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": config.model,
                "prompt": request.prompt,
                "size": request.size,
                "quality": request.quality,
                "n": 1,
            }
            timeout = httpx.Timeout(180.0, connect=15.0)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.post(
                    f"{config.base_url}/images/generations", headers=headers, json=body
                )
                response.raise_for_status()
                image_bytes, image_url = _extract_image_bytes(response.json())
                if image_url:
                    download = await client.get(image_url)
                    download.raise_for_status()
                    image_bytes = download.content
            model = config.model
    except ImageGenerationFailed:
        _last_verified_success = None
        _last_verified_monotonic = None
        _last_probe_failure = datetime.now(timezone.utc).isoformat()
        _last_verified_provider = None
        _last_verified_model = None
        _last_verified_release_id = _runtime_release_id()
        _write_probe_state(
            verified_at=None,
            failure_at=_last_probe_failure,
            provider=str(route["provider"]),
            model=str(route["model"]),
        )
        raise
    except (httpx.HTTPError, json.JSONDecodeError, ValueError, TypeError) as exc:
        _last_verified_success = None
        _last_verified_monotonic = None
        _last_probe_failure = datetime.now(timezone.utc).isoformat()
        _last_verified_provider = None
        _last_verified_model = None
        _last_verified_release_id = _runtime_release_id()
        _write_probe_state(
            verified_at=None,
            failure_at=_last_probe_failure,
            provider=str(route["provider"]),
            model=str(route["model"]),
        )
        raise ImageGenerationFailed("The configured image provider did not complete the request.") from exc

    if image_bytes is None:
        _last_verified_success = None
        _last_verified_monotonic = None
        _last_probe_failure = datetime.now(timezone.utc).isoformat()
        _last_verified_provider = None
        _last_verified_model = None
        _last_verified_release_id = _runtime_release_id()
        _write_probe_state(
            verified_at=None,
            failure_at=_last_probe_failure,
            provider=str(route["provider"]),
            model=str(route["model"]),
        )
        raise ImageGenerationFailed("The configured image provider returned no bytes.")
    artifact = _store_image(
        image_bytes,
        prompt=request.prompt,
        model=model,
        scope_id=scope_id,
    )
    _last_verified_success = datetime.now(timezone.utc).isoformat()
    _last_verified_monotonic = time.monotonic()
    _last_probe_failure = None
    _last_verified_provider = str(route["provider"])
    _last_verified_model = model
    _last_verified_release_id = _runtime_release_id()
    _write_probe_state(
        verified_at=_last_verified_success,
        failure_at=None,
        provider=_last_verified_provider,
        model=_last_verified_model,
    )
    return artifact


async def edit_image(
    request: ImageEditRequest,
    *,
    run_id: str | None = None,
    scope_id: str | None = None,
) -> dict[str, Any]:
    """Edit a persisted image through an actual image-capable route.

    The source is opened from immutable CAS and verified before it reaches the
    provider.  The provider output is persisted as a new immutable artifact;
    the source revision is never mutated in place.
    """

    global _last_probe_failure, _last_verified_model, _last_verified_monotonic
    global _last_verified_provider, _last_verified_release_id, _last_verified_success
    source_bytes, source_manifest = _source_image_bytes(
        request.source_artifact_id,
        scope_id=scope_id,
    )
    config = _config()
    route = _selected_image_route()
    if not config.enabled or not route["configured"]:
        raise ImageCapabilityUnavailable("Image editing is not configured.")
    try:
        if route["provider"] == "codex_cli" and route.get("execution") == "direct":
            from app.codex_cli_image_provider import CodexCLIImageError, edit_codex_cli_image

            try:
                result = await edit_codex_cli_image(
                    request.prompt,
                    source_bytes,
                    size=request.size,
                    quality=request.quality,
                    run_id=run_id,
                )
            except CodexCLIImageError as exc:
                raise ImageGenerationFailed(
                    "Codex CLI did not return a verified edited image."
                ) from exc
            image_bytes = result.data
            model = result.model
        elif route["provider"] == "codex_cli" and route.get("execution") == "local_worker":
            timeout = httpx.Timeout(600.0, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{route['worker_url']}/v1/images/edits",
                    json={
                        "prompt": request.prompt,
                        "size": request.size,
                        "quality": request.quality,
                        "run_id": run_id,
                        "source_b64": base64.b64encode(source_bytes).decode("ascii"),
                    },
                )
                response.raise_for_status()
                payload = response.json()
                image_bytes, image_url = _extract_image_bytes(payload)
                if image_url is not None:
                    raise ImageGenerationFailed("Local image worker returned a remote URL.")
                model = str(payload.get("model") or route["model"])
        elif route["provider"] == "openai":
            # The REST route remains opt-in.  Send a multipart edit request;
            # no browser/CLI session credential crosses this boundary.
            headers = {"Authorization": f"Bearer {config.api_key}"}
            files = {
                "image": (
                    str(source_manifest.get("filename") or "source.png"),
                    source_bytes,
                    str(source_manifest.get("mime_type") or "image/png"),
                )
            }
            data = {
                "model": config.model,
                "prompt": request.prompt,
                "size": request.size,
                "quality": request.quality,
                "n": "1",
            }
            timeout = httpx.Timeout(180.0, connect=15.0)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.post(
                    f"{config.base_url}/images/edits",
                    headers=headers,
                    data=data,
                    files=files,
                )
                response.raise_for_status()
                image_bytes, image_url = _extract_image_bytes(response.json())
                if image_url:
                    download = await client.get(image_url)
                    download.raise_for_status()
                    image_bytes = download.content
            model = config.model
        else:  # pragma: no cover - selected route is exhaustive.
            raise ImageCapabilityUnavailable("Image editing is not configured.")
    except ImageCapabilityUnavailable:
        raise
    except ImageGenerationFailed:
        _last_probe_failure = datetime.now(timezone.utc).isoformat()
        _last_verified_release_id = _runtime_release_id()
        from app.capability_runtime import record_capability_invocation

        record_capability_invocation(
            "image.edit",
            succeeded=False,
            error_code="image_edit_failed",
            provider=str(route["provider"]),
            model=str(route["model"]),
        )
        raise
    except (httpx.HTTPError, json.JSONDecodeError, ValueError, TypeError) as exc:
        _last_probe_failure = datetime.now(timezone.utc).isoformat()
        _last_verified_release_id = _runtime_release_id()
        from app.capability_runtime import record_capability_invocation

        record_capability_invocation(
            "image.edit",
            succeeded=False,
            error_code="image_edit_provider_failed",
            provider=str(route["provider"]),
            model=str(route["model"]),
        )
        raise ImageGenerationFailed(
            "The configured image provider did not complete the edit."
        ) from exc

    if image_bytes is None:
        _last_probe_failure = datetime.now(timezone.utc).isoformat()
        _last_verified_release_id = _runtime_release_id()
        from app.capability_runtime import record_capability_invocation

        record_capability_invocation(
            "image.edit",
            succeeded=False,
            error_code="image_edit_no_bytes",
            provider=str(route["provider"]),
            model=str(route["model"]),
        )
        raise ImageGenerationFailed("The configured image provider returned no bytes.")
    artifact = _store_image(
        image_bytes,
        prompt=request.prompt,
        model=model,
        source_artifact_id=str(source_manifest["id"]),
        scope_id=scope_id,
    )
    _last_verified_success = datetime.now(timezone.utc).isoformat()
    _last_verified_monotonic = time.monotonic()
    _last_probe_failure = None
    _last_verified_provider = str(route["provider"])
    _last_verified_model = model
    _last_verified_release_id = _runtime_release_id()
    from app.capability_runtime import record_capability_invocation

    record_capability_invocation(
        "image.edit",
        succeeded=True,
        provider=_last_verified_provider,
        model=model,
        evidence_id=artifact["sha256"],
    )
    return verify_image_artifact(artifact)


def _metadata(artifact_id: str) -> dict[str, Any]:
    try:
        normalized_id = str(uuid.UUID(artifact_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Image artifact not found") from exc
    try:
        stored = get_artifact_store().get(normalized_id)
    except ArtifactNotFound:
        stored = None
    except (ArtifactValidationError, ArtifactIntegrityError) as exc:
        raise HTTPException(status_code=409, detail="Image artifact integrity check failed") from exc
    if stored is not None:
        internal = stored.get("metadata")
        if stored.get("type") != "image" or not isinstance(internal, dict):
            raise HTTPException(status_code=404, detail="Image artifact not found")
        return {
            "id": normalized_id,
            "type": "image",
            "title": stored.get("title") or "Сгенерированное изображение",
            "prompt": internal.get("prompt") or "",
            "mime_type": stored.get("mime_type"),
            "size_bytes": stored.get("size_bytes"),
            "sha256": stored.get("sha256"),
            "model": internal.get("model") or "",
            "created_at": stored.get("created_at"),
            "url": stored.get("url"),
            "download_url": stored.get("download_url"),
            **(
                {"source_artifact_id": internal.get("source_artifact_id")}
                if internal.get("source_artifact_id")
                else {}
            ),
            "_storage": "unified",
            "_revision": stored.get("revision"),
            "_width": internal.get("width"),
            "_height": internal.get("height"),
            "_scope_key": internal.get("scope_key"),
        }

    # Read-only compatibility for controlled migration of images created
    # before the unified CAS was introduced.  Public access remains
    # fail-closed unless an old manifest already carries an owner scope key.
    # New writes never use this flat layout.
    metadata_path = _artifact_root() / f"{normalized_id}.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=404, detail="Image artifact not found") from exc
    if not isinstance(metadata, dict) or metadata.get("id") != normalized_id:
        raise HTTPException(status_code=404, detail="Image artifact not found")
    metadata["_scope_key"] = metadata.pop("scope_key", None)
    metadata["_storage"] = "legacy"
    return metadata


def _legacy_content_path(artifact_id: str, filename: str) -> Path:
    root = _artifact_root().resolve()
    if not filename or filename != Path(filename).name:
        raise ImageGenerationFailed("Image artifact filename is invalid.")
    content_path = (root / filename).resolve(strict=False)
    try:
        content_path.relative_to(root)
    except ValueError as exc:
        raise ImageGenerationFailed("Image artifact filename is invalid.") from exc
    if not filename.startswith(f"{artifact_id}."):
        raise ImageGenerationFailed("Image artifact filename does not match its identifier.")
    return content_path


def verify_image_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """Verify the public contract against the immutable bytes on disk.

    A provider response, action-shaped JSON, or metadata row is not an image
    artifact by itself.  Completion is allowed only after the stored bytes,
    media type, byte length, digest, identifier, and retrieval URLs all agree.
    """
    if not isinstance(artifact, dict):
        raise ImageGenerationFailed("Image artifact metadata is missing.")
    artifact_id = str(artifact.get("id") or "")
    try:
        normalized_id = str(uuid.UUID(artifact_id))
    except ValueError as exc:
        raise ImageGenerationFailed("Image artifact identifier is invalid.") from exc
    expected_url = f"/api/v1/artifacts/images/{normalized_id}"
    expected_download_url = f"{expected_url}?download=true"
    if (
        artifact.get("type") != "image"
        or artifact.get("url") != expected_url
        or artifact.get("download_url") != expected_download_url
    ):
        raise ImageGenerationFailed("Image artifact retrieval contract is invalid.")

    try:
        metadata = _metadata(normalized_id)
    except HTTPException as exc:
        raise ImageGenerationFailed("Image artifact metadata is not retrievable.") from exc
    filename = str(metadata.get("_filename") or "")
    if metadata.get("_storage") == "unified":
        try:
            stored = get_artifact_store().open(
                normalized_id,
                revision=int(metadata.get("_revision") or 1),
            )
        except ArtifactStoreError as exc:
            raise ImageGenerationFailed("Image artifact bytes are not retrievable.") from exc
        content = stored.content
    else:
        content_path = _legacy_content_path(normalized_id, filename)
        try:
            content = content_path.read_bytes()
        except FileNotFoundError as exc:
            raise ImageGenerationFailed("Image artifact bytes are not retrievable.") from exc

    try:
        details = inspect_image_bytes(content, max_bytes=_MAX_IMAGE_BYTES)
    except InvalidImageBytes as exc:
        raise ImageGenerationFailed("Image artifact bytes failed integrity verification.") from exc
    detected_mime, detected_extension = details.mime_type, details.extension
    expected_filename = f"{normalized_id}{detected_extension}"
    digest = hashlib.sha256(content).hexdigest()
    size_bytes = len(content)
    if metadata.get("_storage") != "unified" and filename != expected_filename:
        raise ImageGenerationFailed("Image artifact filename does not match its identifier.")
    for key in ("id", "type", "mime_type", "size_bytes", "sha256", "url", "download_url"):
        if artifact.get(key) != metadata.get(key):
            raise ImageGenerationFailed(f"Image artifact field {key!r} is inconsistent.")
    if (
        detected_mime != artifact.get("mime_type")
        or size_bytes <= 0
        or size_bytes != artifact.get("size_bytes")
        or digest != artifact.get("sha256")
        or not str(artifact.get("mime_type") or "").startswith("image/")
        or (metadata.get("_width") is not None and metadata.get("_width") != details.width)
        or (metadata.get("_height") is not None and metadata.get("_height") != details.height)
    ):
        raise ImageGenerationFailed("Image artifact bytes failed integrity verification.")
    return {key: value for key, value in metadata.items() if not key.startswith("_")}


async def generate_invocable_image(
    request: ImageGenerationRequest,
    *,
    policy: dict[str, Any] | None = None,
    run_id: str | None = None,
    scope_id: str | None = None,
) -> dict[str, Any]:
    """Generate through the proved image route; never fall back to chat."""
    if not _image_route_is_invocable(policy):
        raise ImageCapabilityUnavailable("No configured and policy-permitted image route is invocable.")
    artifact = (
        await generate_image(request, run_id=run_id, scope_id=scope_id)
        if run_id is not None
        else await generate_image(request, scope_id=scope_id)
    )
    return verify_image_artifact(artifact)


@router.get("/api/v1/capabilities")
@router.get("/v1/capabilities", include_in_schema=False)
async def get_capabilities():
    return capability_catalog()


@router.post("/api/v1/images/generations", status_code=201)
@router.post("/v1/images/generations", status_code=201, include_in_schema=False)
async def create_image(
    request: ImageGenerationRequest,
    scope_id: str = Depends(authorize_public_scope),
):
    try:
        return verify_image_artifact(await generate_image(request, scope_id=scope_id))
    except ImageCapabilityUnavailable as exc:
        raise HTTPException(status_code=503, detail="Генерация изображений сейчас не подключена.") from exc
    except ImageGenerationFailed as exc:
        raise HTTPException(status_code=502, detail="Провайдер изображений не вернул проверенный артефакт.") from exc


@router.post("/api/v1/images/edits", status_code=201)
@router.post("/v1/images/edits", status_code=201, include_in_schema=False)
async def create_image_edit(
    request: ImageEditRequest,
    scope_id: str = Depends(authorize_public_scope),
):
    try:
        return await edit_image(request, scope_id=scope_id)
    except ImageCapabilityUnavailable as exc:
        raise HTTPException(status_code=503, detail="Редактирование изображений сейчас не подключено.") from exc
    except ImageGenerationFailed as exc:
        raise HTTPException(status_code=502, detail="Провайдер не вернул проверенный результат редактирования.") from exc


@router.get("/api/v1/artifacts/images/{artifact_id}")
@router.get("/v1/artifacts/images/{artifact_id}", include_in_schema=False)
async def get_image_artifact(
    artifact_id: str,
    download: bool = False,
    scope_id: str | None = Depends(resolve_optional_public_scope),
):
    metadata = _metadata(artifact_id)
    try:
        if metadata.get("_storage") == "unified":
            _assert_artifact_scope(get_artifact_store().get(artifact_id), scope_id)
        else:
            # Preserve old bytes for an explicit migration job, but never
            # expose an unscoped flat-file artifact through the public API.
            _assert_artifact_scope(
                {"metadata": {"scope_key": metadata.get("_scope_key")}},
                scope_id,
            )
    except ArtifactStoreError as exc:
        raise HTTPException(status_code=404, detail="Image artifact not found") from exc
    try:
        verified = verify_image_artifact({key: value for key, value in metadata.items() if not key.startswith("_")})
    except ImageGenerationFailed as exc:
        raise HTTPException(status_code=409, detail="Image artifact integrity check failed") from exc
    if metadata.get("_storage") == "unified":
        try:
            content = get_artifact_store().open(
                verified["id"],
                revision=int(metadata.get("_revision") or 1),
            ).content
        except ArtifactStoreError as exc:
            raise HTTPException(status_code=409, detail="Image artifact integrity check failed") from exc
    else:
        content_path = _legacy_content_path(
            verified["id"], str(metadata.get("_filename", ""))
        )
        content = content_path.read_bytes()
    headers = {"ETag": f'"{verified["sha256"]}"', "Cache-Control": "private, max-age=31536000, immutable"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="kolibri-{artifact_id}.{verified["mime_type"].split("/")[-1]}"'
    return Response(content=content, media_type=verified["mime_type"], headers=headers)
