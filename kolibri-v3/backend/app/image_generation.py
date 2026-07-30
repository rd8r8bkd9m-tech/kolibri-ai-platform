"""Provider-neutral image generation boundary for Product Chat.

The runtime deliberately has no implicit network fallback.  Production must
inject one reviewed provider implementation into ``create_app``; otherwise an
image request fails closed before a chat success can be recorded.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import threading
from typing import Protocol, Sequence, runtime_checkable


IMAGE_GENERATION_CAPABILITY_ID = "image.generate"
IMAGE_GENERATION_CLARIFICATION = (
    "Опишите, что должно быть на изображении, укажите желаемый стиль, "
    "формат и назначение. После этого я создам изображение."
)

_IMAGE_INTENT = re.compile(
    r"(?iu)\b(?:созда(?:й|йте|ть)|сгенерир(?:уй|уйте|овать)|"
    r"нарис(?:уй|уйте|овать)|сдела(?:й|йте|ть))\b"
    r"[\s\S]{0,80}\b(?:изображени\w*|картин\w*|иллюстраци\w*|"
    r"рендер\w*|постер\w*)\b"
)
_GENERIC_IMAGE_REQUEST = re.compile(
    r"(?iu)(?:по\s+моему\s+описанию|сначала\s+уточни|"
    r"уточни\s+(?:стиль|формат|назначение))"
)
_CAPABILITY_ID = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
_EXECUTION_ID = re.compile(
    r"^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$"
)
_MEDIA_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
MAX_GENERATED_IMAGE_BYTES = 50 * 1024 * 1024


class ImageGenerationError(RuntimeError):
    """Safe provider or validation failure exposed as a failed chat run."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ImageGenerationProviderDescriptor:
    provider_id: str
    provider_version: str
    display_name: str

    def __post_init__(self) -> None:
        if _CAPABILITY_ID.fullmatch(self.provider_id) is None:
            raise ValueError("image provider id is invalid")
        if _VERSION.fullmatch(self.provider_version) is None:
            raise ValueError("image provider version is invalid")
        if not 1 <= len(self.display_name.strip()) <= 120:
            raise ValueError("image provider display name is invalid")


@dataclass(frozen=True, slots=True)
class ImageGenerationRequest:
    tenant_id: str
    project_id: str
    thread_id: str
    run_id: str
    prompt: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not 1 <= len(self.prompt.strip()) <= 8_000:
            raise ValueError("image prompt is invalid")
        if not 8 <= len(self.idempotency_key) <= 200:
            raise ValueError("image idempotency key is invalid")


@dataclass(frozen=True, slots=True)
class ImageGenerationResult:
    content: bytes
    media_type: str
    execution_id: str
    revised_prompt: str | None = None


@runtime_checkable
class ImageGenerationProvider(Protocol):
    @property
    def descriptor(self) -> ImageGenerationProviderDescriptor: ...

    def generate(
        self,
        request: ImageGenerationRequest,
        *,
        cancellation_signal: threading.Event | None = None,
    ) -> ImageGenerationResult: ...


class UnavailableImageGenerationProvider:
    """Default boundary: never invent an image when no provider is wired."""

    @property
    def descriptor(self) -> ImageGenerationProviderDescriptor:
        return ImageGenerationProviderDescriptor(
            provider_id="image.unavailable",
            provider_version="1.0",
            display_name="Генерация изображений",
        )

    def generate(
        self,
        _request: ImageGenerationRequest,
        *,
        cancellation_signal: threading.Event | None = None,
    ) -> ImageGenerationResult:
        if cancellation_signal is not None and cancellation_signal.is_set():
            raise ImageGenerationError(
                "run_cancelled",
                "Задача остановлена пользователем.",
            )
        raise ImageGenerationError(
            "image_generation_unavailable",
            (
                "Генерация изображений пока не подключена. "
                "Суперадминистратору нужно настроить провайдера."
            ),
        )


@dataclass(frozen=True, slots=True)
class ImagePromptResolution:
    action: str
    prompt: str | None


def resolve_image_prompt(
    messages: Sequence[dict[str, str]],
) -> ImagePromptResolution | None:
    """Resolve an explicit image request or one continuation after clarification."""

    if not messages or messages[-1].get("role") != "user":
        return None
    current = " ".join(messages[-1].get("content", "").split())
    if not current:
        return None

    if _IMAGE_INTENT.search(current):
        if (
            len(current) < 36
            or _GENERIC_IMAGE_REQUEST.search(current) is not None
        ):
            return ImagePromptResolution(action="clarify", prompt=None)
        return ImagePromptResolution(action="generate", prompt=current[:8_000])

    if len(messages) >= 3:
        prior_assistant = messages[-2]
        prior_user = messages[-3]
        if (
            prior_assistant.get("role") == "assistant"
            and prior_assistant.get("content") == IMAGE_GENERATION_CLARIFICATION
            and prior_user.get("role") == "user"
            and _IMAGE_INTENT.search(prior_user.get("content", ""))
            and len(current) >= 8
        ):
            return ImagePromptResolution(action="generate", prompt=current[:8_000])
    return None


def _matches_media_signature(content: bytes, media_type: str) -> bool:
    if media_type == "image/png":
        return (
            len(content) >= 24
            and content.startswith(b"\x89PNG\r\n\x1a\n")
            and content[12:16] == b"IHDR"
        )
    if media_type == "image/jpeg":
        return (
            len(content) >= 4
            and content.startswith(b"\xff\xd8\xff")
            and content.endswith(b"\xff\xd9")
        )
    if media_type == "image/webp":
        return (
            len(content) >= 16
            and content.startswith(b"RIFF")
            and content[8:12] == b"WEBP"
        )
    return False


def validate_image_generation_result(
    provider: ImageGenerationProvider,
    result: ImageGenerationResult,
) -> ImageGenerationResult:
    """Validate provider output before bytes can enter durable storage."""

    # Accessing the descriptor validates provider identity/version as well.
    provider.descriptor
    if result.media_type not in _MEDIA_TYPES:
        raise ImageGenerationError(
            "image_generation_invalid",
            "Провайдер вернул неподдерживаемый формат изображения.",
        )
    if (
        not result.content
        or len(result.content) > MAX_GENERATED_IMAGE_BYTES
        or not _matches_media_signature(result.content, result.media_type)
    ):
        raise ImageGenerationError(
            "image_generation_invalid",
            "Провайдер вернул повреждённое изображение.",
        )
    if _EXECUTION_ID.fullmatch(result.execution_id) is None:
        raise ImageGenerationError(
            "image_generation_invalid",
            "Провайдер не вернул проверяемый идентификатор выполнения.",
        )
    revised = result.revised_prompt
    if revised is not None and not 1 <= len(revised.strip()) <= 8_000:
        raise ImageGenerationError(
            "image_generation_invalid",
            "Провайдер вернул некорректное описание изображения.",
        )
    return result
