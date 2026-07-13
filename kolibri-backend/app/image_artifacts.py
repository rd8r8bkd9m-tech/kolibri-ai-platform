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
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.image_validation import InvalidImageBytes, inspect_image_bytes


router = APIRouter()

_MAX_IMAGE_BYTES = 25 * 1024 * 1024
_last_verified_success: str | None = None
_last_verified_monotonic: float | None = None
_last_probe_failure: str | None = None
_last_verified_provider: str | None = None
_last_verified_model: str | None = None


class ImageGenerationRequest(BaseModel):
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
    codex_route = _codex_cli_route()
    if config.enabled and codex_route["configured"]:
        return codex_route
    rest_configured = bool(config.enabled and config.rest_enabled and config.api_key)
    if rest_configured:
        return {
            "configured": True,
            "provider": "openai",
            "model": config.model,
        }
    return {
        "configured": False,
        "provider": "none",
        "model": "none",
    }


def image_execution_identity() -> dict[str, str]:
    route = _selected_image_route()
    return {
        "provider": _last_verified_provider or str(route["provider"]),
        "model": _last_verified_model or str(route["model"]),
    }


def image_capability() -> dict[str, Any]:
    config = _config()
    route = _selected_image_route()
    configured = bool(config.enabled and route["configured"])
    probe_ttl = max(1, int(os.getenv("OPENAI_IMAGE_PROBE_TTL_SECONDS", "900")))
    verified = bool(
        configured
        and _last_verified_success
        and _last_verified_monotonic is not None
        and time.monotonic() - _last_verified_monotonic <= probe_ttl
        and _last_probe_failure is None
        and _last_verified_provider == route["provider"]
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
            "verified_at": _last_verified_success,
            "last_failure_at": _last_probe_failure,
        },
        "renderer": {"available": True, "id": "image", "status": "live"},
        "source": {"type": "live_invocation" if verified else "configuration"},
    }


def capability_catalog() -> dict[str, Any]:
    from app.openai_responses import responses_capability_manifest
    from app.routers.openai_compat import (
        developer_api_keys_capability,
        developer_response_capabilities,
    )

    capability = image_capability()
    responses_manifest = responses_capability_manifest()
    capabilities = [capability, *responses_manifest["capabilities"]]
    developer_capability = developer_api_keys_capability()
    if developer_capability is not None:
        capabilities.append(developer_capability)
    capabilities.extend(developer_response_capabilities())
    if any(item["status"] == "live" for item in capabilities):
        status = "live"
    elif any(item["status"] in {"partial", "unverified"} for item in capabilities):
        status = "partial"
    else:
        status = "unavailable"
    return {
        "schema_version": "2026-07-13",
        "status": status,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "capabilities": capabilities,
    }


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


def _store_image(data: bytes, *, prompt: str, model: str) -> dict[str, Any]:
    try:
        details = inspect_image_bytes(data, max_bytes=_MAX_IMAGE_BYTES)
    except InvalidImageBytes as exc:
        raise ImageGenerationFailed("Provider output is not a supported image artifact.") from exc
    mime_type, extension = details.mime_type, details.extension
    digest = hashlib.sha256(data).hexdigest()
    artifact_id = str(uuid.uuid4())
    root = _artifact_root()
    root.mkdir(parents=True, exist_ok=True)
    content_path = root / f"{artifact_id}{extension}"
    metadata_path = root / f"{artifact_id}.json"
    temporary_path = root / f".{artifact_id}.tmp"
    temporary_path.write_bytes(data)
    os.chmod(temporary_path, 0o640)
    temporary_path.replace(content_path)
    created_at = datetime.now(timezone.utc).isoformat()
    artifact = {
        "id": artifact_id,
        "type": "image",
        "title": "Сгенерированное изображение",
        "prompt": prompt,
        "mime_type": mime_type,
        "size_bytes": len(data),
        "sha256": digest,
        "model": model,
        "created_at": created_at,
        "url": f"/api/v1/artifacts/images/{artifact_id}",
        "download_url": f"/api/v1/artifacts/images/{artifact_id}?download=true",
        "_filename": content_path.name,
        "_width": details.width,
        "_height": details.height,
    }
    metadata_path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    os.chmod(metadata_path, 0o640)
    return {key: value for key, value in artifact.items() if not key.startswith("_")}


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
) -> dict[str, Any]:
    global _last_probe_failure, _last_verified_model, _last_verified_monotonic
    global _last_verified_provider, _last_verified_success
    config = _config()
    route = _selected_image_route()
    if not config.enabled or not route["configured"]:
        raise ImageCapabilityUnavailable("Image generation is not configured.")
    try:
        if route["provider"] == "codex_cli":
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
                raise ImageGenerationFailed("Codex CLI did not return a verified image file.") from exc
            image_bytes = cli_result.data
            model = cli_result.model
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
        raise
    except (httpx.HTTPError, json.JSONDecodeError, ValueError, TypeError) as exc:
        _last_verified_success = None
        _last_verified_monotonic = None
        _last_probe_failure = datetime.now(timezone.utc).isoformat()
        _last_verified_provider = None
        _last_verified_model = None
        raise ImageGenerationFailed("The configured image provider did not complete the request.") from exc

    if image_bytes is None:
        _last_verified_success = None
        _last_verified_monotonic = None
        _last_probe_failure = datetime.now(timezone.utc).isoformat()
        _last_verified_provider = None
        _last_verified_model = None
        raise ImageGenerationFailed("The configured image provider returned no bytes.")
    artifact = _store_image(image_bytes, prompt=request.prompt, model=model)
    _last_verified_success = datetime.now(timezone.utc).isoformat()
    _last_verified_monotonic = time.monotonic()
    _last_probe_failure = None
    _last_verified_provider = str(route["provider"])
    _last_verified_model = model
    return artifact


def _metadata(artifact_id: str) -> dict[str, Any]:
    try:
        normalized_id = str(uuid.UUID(artifact_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Image artifact not found") from exc
    metadata_path = _artifact_root() / f"{normalized_id}.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=404, detail="Image artifact not found") from exc
    if not isinstance(metadata, dict) or metadata.get("id") != normalized_id:
        raise HTTPException(status_code=404, detail="Image artifact not found")
    return metadata


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
    content_path = _artifact_root() / filename
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
    if filename != expected_filename:
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
) -> dict[str, Any]:
    """Generate through the proved image route; never fall back to chat."""
    if not _image_route_is_invocable(policy):
        raise ImageCapabilityUnavailable("No configured and policy-permitted image route is invocable.")
    artifact = (
        await generate_image(request, run_id=run_id)
        if run_id is not None
        else await generate_image(request)
    )
    return verify_image_artifact(artifact)


@router.get("/api/v1/capabilities")
@router.get("/v1/capabilities", include_in_schema=False)
async def get_capabilities():
    return capability_catalog()


@router.post("/api/v1/images/generations", status_code=201)
@router.post("/v1/images/generations", status_code=201, include_in_schema=False)
async def create_image(request: ImageGenerationRequest):
    try:
        return verify_image_artifact(await generate_image(request))
    except ImageCapabilityUnavailable as exc:
        raise HTTPException(status_code=503, detail="Генерация изображений сейчас не подключена.") from exc
    except ImageGenerationFailed as exc:
        raise HTTPException(status_code=502, detail="Провайдер изображений не вернул проверенный артефакт.") from exc


@router.get("/api/v1/artifacts/images/{artifact_id}")
@router.get("/v1/artifacts/images/{artifact_id}", include_in_schema=False)
async def get_image_artifact(artifact_id: str, download: bool = False):
    metadata = _metadata(artifact_id)
    try:
        verified = verify_image_artifact({key: value for key, value in metadata.items() if not key.startswith("_")})
    except ImageGenerationFailed as exc:
        raise HTTPException(status_code=409, detail="Image artifact integrity check failed") from exc
    content_path = _artifact_root() / str(metadata.get("_filename", ""))
    content = content_path.read_bytes()
    headers = {"ETag": f'"{verified["sha256"]}"', "Cache-Control": "private, max-age=31536000, immutable"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="kolibri-{artifact_id}.{verified["mime_type"].split("/")[-1]}"'
    return Response(content=content, media_type=verified["mime_type"], headers=headers)
