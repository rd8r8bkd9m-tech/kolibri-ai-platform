"""Durable generated-image manifests and Product Attachment projections."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import sqlite3
from typing import Annotated, Protocol
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from .attachment_service import (
    AttachmentConflictError,
    AttachmentMetadataError,
    AttachmentRecord,
    AttachmentScopeError,
    persist_attachment_record,
)
from .attachment_store import (
    ATTACHMENT_CONTRACT_MAX_BYTES,
    AttachmentStorageError,
    StoredContent,
    store_content_bytes,
)
from .chat.service import canonical_json, sha256_text, typed_identity_id
from .config import Settings
from .database import get_database
from .identity import require_user
from .image_generation import (
    ImageGenerationProvider,
    ImageGenerationProviderDescriptor,
    ImageGenerationResult,
    validate_image_generation_result,
)
from .product_widgets import ProductWidget
from .schemas import UserSession


router = APIRouter(prefix="/v1/artifacts", tags=["artifacts"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = Annotated[UserSession, Depends(require_user)]
_ARTIFACT_ID = re.compile(
    r"^artifact_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$"
)


class GeneratedImageRun(Protocol):
    tenant_id: str
    project_id: str
    thread_id: str
    run_id: str
    public_run_id: str


class GeneratedImageArtifactError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class PreparedGeneratedImageArtifact:
    artifact_id: str
    artifact_version: int
    attachment_id: str
    filename: str
    media_type: str
    stored: StoredContent
    prompt: str
    revised_prompt: str | None
    provider: ImageGenerationProviderDescriptor
    execution_ref: str


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _extension(media_type: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }[media_type]


def prepare_generated_image_artifact(
    settings: Settings,
    run: GeneratedImageRun,
    *,
    prompt: str,
    provider: ImageGenerationProvider,
    result: ImageGenerationResult,
) -> PreparedGeneratedImageArtifact:
    """Validate and place provider bytes in CAS before the metadata commit."""

    result = validate_image_generation_result(provider, result)
    artifact_id = _new_id("artifact")
    try:
        stored = store_content_bytes(
            settings,
            tenant_id=run.tenant_id,
            content=result.content,
            max_bytes=ATTACHMENT_CONTRACT_MAX_BYTES,
        )
    except AttachmentStorageError as exc:
        raise GeneratedImageArtifactError(
            "artifact_storage_failed",
            "Не удалось надёжно сохранить созданное изображение.",
        ) from exc
    return PreparedGeneratedImageArtifact(
        artifact_id=artifact_id,
        artifact_version=1,
        attachment_id=_new_id("attachment"),
        filename=(
            f"generated-image-{artifact_id.removeprefix('artifact_')[:12]}"
            f"{_extension(result.media_type)}"
        ),
        media_type=result.media_type,
        stored=stored,
        prompt=prompt,
        revised_prompt=result.revised_prompt,
        provider=provider.descriptor,
        execution_ref=result.execution_id,
    )


def _artifact_manifest(
    *,
    run: GeneratedImageRun,
    prepared: PreparedGeneratedImageArtifact,
    user_id: str,
    input_message_id: str,
    input_created_at: str,
    goal_id: str,
    case_id: str,
    created_at: str,
) -> dict[str, object]:
    prompt_hash = sha256_text(prepared.prompt)
    inputs: list[dict[str, object]] = [
        {
            "input_id": _new_id("input"),
            "input_kind": "fact",
            "ref_id": input_message_id,
            "ref_version": 1,
            "content_hash": prompt_hash,
            "role": "user image-generation prompt",
        }
    ]
    if (
        prepared.revised_prompt is not None
        and prepared.revised_prompt.strip() != prepared.prompt.strip()
    ):
        inputs.append(
            {
                "input_id": _new_id("input"),
                "input_kind": "tool_result",
                "ref_id": prepared.execution_ref,
                "ref_version": 1,
                "content_hash": sha256_text(prepared.revised_prompt),
                "role": "provider revised prompt",
            }
        )
    actor_id = typed_identity_id("actor", user_id)
    generator_tool = "tool_image_generation"
    return {
        "schema_id": "kolibri.artifact",
        "schema_version": "1.0",
        "artifact_id": prepared.artifact_id,
        "artifact_version": prepared.artifact_version,
        "tenant_id": typed_identity_id("tenant", run.tenant_id),
        "goal_id": goal_id,
        "case_id": case_id,
        "task_id": None,
        "artifact_type": "image.generated",
        "domain_output": {
            "aggregate_type": "generated_image",
            "aggregate_id": prepared.artifact_id,
            "aggregate_version": prepared.artifact_version,
        },
        "content": {
            "storage_ref": prepared.stored.storage_ref,
            "media_type": prepared.media_type,
            "size_bytes": prepared.stored.size_bytes,
            "content_hash": prepared.stored.content_hash,
            "filename": prepared.filename,
        },
        "contract": {
            "schema_id": "kolibri.generated_image",
            "schema_version": "1.0",
            "renderer_id": "web.image",
            "renderer_version": "1.0",
        },
        "generator": {
            "generator_id": prepared.provider.provider_id,
            "generator_version": prepared.provider.provider_version,
            "execution_ref": prepared.execution_ref,
        },
        "inputs": inputs,
        "provenance": [
            {
                "provenance_id": _new_id("prov"),
                "kind": "user_input",
                "source_ref": input_message_id,
                "recorded_at": input_created_at,
                "effective_at": input_created_at,
                "actor_or_tool_ref": actor_id,
            },
            {
                "provenance_id": _new_id("prov"),
                "kind": "model_generation",
                "source_ref": prepared.execution_ref,
                "recorded_at": created_at,
                "effective_at": None,
                "actor_or_tool_ref": generator_tool,
            },
        ],
        "supersedes": None,
        "created_by": generator_tool,
        "created_at": created_at,
    }


def _projection(
    record: AttachmentRecord,
    prepared: PreparedGeneratedImageArtifact,
) -> dict[str, object]:
    return {
        "$type": "GeneratedImage",
        "schemaId": "kolibri.product.attachment",
        "schemaVersion": "1.0",
        "attachmentId": record.attachment_id,
        "artifactId": record.artifact_id,
        "artifactVersion": record.artifact_version,
        "contentHash": record.content_hash,
        "filename": record.filename,
        "mimeType": record.mime_type,
        "sizeBytes": record.size_bytes,
        "contentPath": record.content_path,
        "status": record.status,
        "providerLabel": prepared.provider.display_name,
        "revisedPrompt": prepared.revised_prompt,
    }


def persist_generated_image_artifact(
    database: sqlite3.Connection,
    run: GeneratedImageRun,
    *,
    prepared: PreparedGeneratedImageArtifact,
    created_at: str,
) -> ProductWidget:
    """Persist attachment + canonical manifest in the caller's transaction."""

    context = database.execute(
        """
        SELECT
            run.requested_by_user_id,
            run.input_message_id,
            message.created_at AS input_created_at,
            runtime.goal_id,
            runtime.case_id
        FROM chat_runs AS run
        JOIN chat_messages AS message
          ON message.tenant_id = run.tenant_id
         AND message.id = run.input_message_id
        JOIN product_project_runtime AS runtime
          ON runtime.tenant_id = run.tenant_id
         AND runtime.project_id = run.project_id
        WHERE run.tenant_id = ?
          AND run.id = ?
          AND run.project_id = ?
          AND run.thread_id = ?
        LIMIT 1
        """,
        (
            run.tenant_id,
            run.run_id,
            run.project_id,
            run.thread_id,
        ),
    ).fetchone()
    if context is None:
        raise GeneratedImageArtifactError(
            "artifact_context_missing",
            "Не найден контекст для сохранения изображения.",
        )
    user_id = str(context["requested_by_user_id"])
    input_message_id = str(context["input_message_id"])
    manifest = _artifact_manifest(
        run=run,
        prepared=prepared,
        user_id=user_id,
        input_message_id=input_message_id,
        input_created_at=str(context["input_created_at"]),
        goal_id=str(context["goal_id"]),
        case_id=str(context["case_id"]),
        created_at=created_at,
    )
    idempotency_key = (
        "generated_image_"
        + hashlib.sha256(
            f"{run.tenant_id}\0{run.run_id}".encode("utf-8", "strict")
        ).hexdigest()
    )
    try:
        record = persist_attachment_record(
            database,
            tenant_id=run.tenant_id,
            user_id=user_id,
            project_id=run.project_id,
            thread_id=run.thread_id,
            filename=prepared.filename,
            mime_type=prepared.media_type,
            stored=prepared.stored,
            idempotency_key=idempotency_key,
            created_at=created_at,
            attachment_id=prepared.attachment_id,
            artifact_id=prepared.artifact_id,
            artifact_version=prepared.artifact_version,
            created_by_user_id=user_id,
        )
        database.execute(
            """
            INSERT INTO artifact_versions (
                tenant_id, artifact_id, artifact_version, attachment_id,
                project_id, thread_id, run_id, input_message_id,
                artifact_type, content_hash, storage_ref, media_type,
                size_bytes, filename, generator_id, generator_version,
                execution_ref, prompt_hash, manifest_json,
                created_by_user_id, created_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, 'image.generated', ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                run.tenant_id,
                prepared.artifact_id,
                prepared.artifact_version,
                prepared.attachment_id,
                run.project_id,
                run.thread_id,
                run.run_id,
                input_message_id,
                prepared.stored.content_hash,
                prepared.stored.storage_ref,
                prepared.media_type,
                prepared.stored.size_bytes,
                prepared.filename,
                prepared.provider.provider_id,
                prepared.provider.provider_version,
                prepared.execution_ref,
                sha256_text(prepared.prompt),
                canonical_json(manifest),
                user_id,
                created_at,
            ),
        )
    except (
        AttachmentConflictError,
        AttachmentMetadataError,
        AttachmentScopeError,
        sqlite3.IntegrityError,
    ) as exc:
        raise GeneratedImageArtifactError(
            "artifact_persistence_failed",
            "Не удалось связать изображение с текущим проектом.",
        ) from exc

    projection = _projection(record, prepared)
    return ProductWidget(
        arguments={"prompt": prepared.prompt},
        fallback_text="Изображение создано и сохранено в проекте.",
        tool_name="generate_image",
        tool_result=projection,
    )


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "artifact_not_found",
            "message": "Артефакт не найден.",
        },
    )


@router.get("/{artifact_id}/versions/{artifact_version}")
def get_artifact_version(
    artifact_id: str,
    artifact_version: int,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, object]:
    if (
        _ARTIFACT_ID.fullmatch(artifact_id) is None
        or isinstance(artifact_version, bool)
        or not 1 <= artifact_version <= 2_147_483_647
    ):
        raise _not_found()
    row = database.execute(
        """
        SELECT manifest_json
        FROM artifact_versions
        WHERE tenant_id = ?
          AND artifact_id = ?
          AND artifact_version = ?
        LIMIT 1
        """,
        (identity.tenant_id, artifact_id, artifact_version),
    ).fetchone()
    if row is None:
        raise _not_found()
    value = json.loads(str(row["manifest_json"]))
    if not isinstance(value, dict):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "artifact_manifest_invalid",
                "message": "Манифест артефакта повреждён.",
            },
        )
    return value


__all__ = [
    "GeneratedImageArtifactError",
    "PreparedGeneratedImageArtifact",
    "persist_generated_image_artifact",
    "prepare_generated_image_artifact",
    "router",
]
