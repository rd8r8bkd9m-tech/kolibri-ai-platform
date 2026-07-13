"""Public contracts for durable project and conversation history."""

from datetime import datetime
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
DECIMAL_PATTERN = r"^-?\d+(?:\.\d+)?$"
MAX_MESSAGE_METADATA_BYTES = 300_000


class _StrictMetadataModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PersistedWorkEvent(_StrictMetadataModel):
    stage: str = Field(min_length=1, max_length=80)
    status: Literal["active", "completed", "failed"]
    summary: str = Field(min_length=1, max_length=600)
    provider: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=120)
    artifact_type: str | None = Field(default=None, max_length=40)
    artifact_id: str | None = Field(default=None, max_length=160)


class PersistedEstimatePosition(_StrictMetadataModel):
    code: str = Field(default="", max_length=80)
    name: str = Field(min_length=1, max_length=320)
    unit: str = Field(min_length=1, max_length=40)
    quantity: str = Field(min_length=1, max_length=64, pattern=DECIMAL_PATTERN)
    price: str = Field(min_length=1, max_length=64, pattern=DECIMAL_PATTERN)
    source: str = Field(default="", max_length=1_000)
    comment: str = Field(default="", max_length=1_000)


class PersistedEstimateSection(_StrictMetadataModel):
    title: str = Field(min_length=1, max_length=240)
    positions: list[PersistedEstimatePosition] = Field(default_factory=list, max_length=500)


class PersistedEstimateDraft(_StrictMetadataModel):
    title: str = Field(min_length=1, max_length=160)
    client: str = Field(default="", max_length=240)
    object_name: str = Field(default="", max_length=240)
    region: str = Field(default="", max_length=240)
    currency: str = Field(default="RUB", min_length=1, max_length=8)
    overhead_rate: str = Field(default="0", min_length=1, max_length=64, pattern=DECIMAL_PATTERN)
    vat_rate: str = Field(default="22", min_length=1, max_length=64, pattern=DECIMAL_PATTERN)
    sections: list[PersistedEstimateSection] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def bound_position_count(self):
        if sum(len(section.positions) for section in self.sections) > 2_000:
            raise ValueError("estimate action contains too many positions")
        return self


class PersistedDocumentDraft(_StrictMetadataModel):
    title: str = Field(min_length=1, max_length=160)
    type: str = Field(default="custom", min_length=1, max_length=40)
    client: str = Field(default="", max_length=240)
    project: str = Field(default="", max_length=240)
    content: str = Field(default="", max_length=500_000)
    variables: dict[str, str] = Field(default_factory=dict, max_length=100)
    template: str = Field(default="", max_length=120)

    @field_validator("variables")
    @classmethod
    def bound_variables(cls, value: dict[str, str]) -> dict[str, str]:
        for key, item in value.items():
            if not key or len(key) > 120 or len(item) > 10_000:
                raise ValueError("document variables exceed safe bounds")
        return value


class PersistedImageArtifact(_StrictMetadataModel):
    id: str = Field(pattern=UUID_PATTERN)
    type: Literal["image"]
    title: str = Field(min_length=1, max_length=240)
    prompt: str = Field(min_length=1, max_length=20_000)
    mime_type: Literal["image/png", "image/jpeg", "image/webp"]
    size_bytes: int = Field(gt=0, le=50 * 1024 * 1024)
    sha256: str = Field(pattern=SHA256_PATTERN)
    model: str = Field(min_length=1, max_length=120)
    created_at: str = Field(min_length=1, max_length=64)
    url: str = Field(min_length=1, max_length=240)
    download_url: str = Field(min_length=1, max_length=280)

    @model_validator(mode="after")
    def verify_retrieval_contract(self):
        expected_url = f"/api/v1/artifacts/images/{self.id}"
        if self.url != expected_url or self.download_url != f"{expected_url}?download=true":
            raise ValueError("image artifact retrieval contract is invalid")
        try:
            datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("image artifact timestamp is invalid") from exc
        return self


class PersistedEstimateAction(_StrictMetadataModel):
    type: Literal["create_estimate"]
    label: str = Field(min_length=1, max_length=120)
    data: PersistedEstimateDraft


class PersistedDocumentAction(_StrictMetadataModel):
    type: Literal["create_document"]
    label: str = Field(min_length=1, max_length=120)
    data: PersistedDocumentDraft


class PersistedImageAction(_StrictMetadataModel):
    type: Literal["present_image"]
    label: str = Field(min_length=1, max_length=120)
    data: PersistedImageArtifact


PersistedAction = Annotated[
    PersistedEstimateAction | PersistedDocumentAction | PersistedImageAction,
    Field(discriminator="type"),
]


class PersistedEstimateArtifact(_StrictMetadataModel):
    type: Literal["estimate"]
    id: str = Field(pattern=UUID_PATTERN)
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=160)


class PersistedDocumentArtifact(_StrictMetadataModel):
    type: Literal["document"]
    id: str = Field(pattern=UUID_PATTERN)
    title: str = Field(min_length=1, max_length=160)


PersistedArtifact = Annotated[
    PersistedEstimateArtifact | PersistedDocumentArtifact | PersistedImageArtifact,
    Field(discriminator="type"),
]


class ProjectMessageMetadata(_StrictMetadataModel):
    response_id: str | None = Field(default=None, min_length=1, max_length=160)
    work_events: list[PersistedWorkEvent] = Field(default_factory=list, max_length=128)
    actions: list[PersistedAction] = Field(default_factory=list, max_length=8)
    artifact: PersistedArtifact | None = None

    @model_validator(mode="before")
    @classmethod
    def bound_serialized_size(cls, value: Any):
        encoded = json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
        if len(encoded) > MAX_MESSAGE_METADATA_BYTES:
            raise ValueError("message metadata exceeds safe size limit")
        return value

    @model_validator(mode="after")
    def prevent_duplicate_materialization(self):
        if self.artifact is not None and self.actions:
            raise ValueError("materialized artifact metadata must not retain executable actions")
        return self


class ProjectCreate(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)
    client_request_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("title")
    @classmethod
    def normalize_optional_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    metadata: dict[str, Any] | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    title_source: Literal["default", "message", "manual"]
    status: str
    version: int
    message_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None = None
    deleted_at: datetime | None = None


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
    page: int
    page_size: int


class ProjectMessageCreate(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str = Field(default="", max_length=1_000_000)
    status: Literal["pending", "streaming", "completed", "failed", "cancelled"] = "completed"
    metadata: ProjectMessageMetadata = Field(default_factory=ProjectMessageMetadata)
    client_message_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        return value

    @model_validator(mode="after")
    def validate_placeholder(self):
        if not self.content.strip() and not (
            self.role == "assistant" and self.status in {"pending", "streaming"}
        ):
            raise ValueError("content must not be blank unless this is an assistant placeholder")
        return self


class ProjectMessageUpdate(BaseModel):
    content: str | None = Field(default=None, max_length=1_000_000)
    status: Literal["pending", "streaming", "completed", "failed", "cancelled"] | None = None
    metadata: ProjectMessageMetadata | None = None


class ProjectMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    sequence: int
    version: int
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ProjectMessageListResponse(BaseModel):
    items: list[ProjectMessageResponse]
    total: int
    after: int
    limit: int


class ShellBootstrapResponse(BaseModel):
    session_id: str
    session_type: Literal["anonymous", "authenticated"]
    restored: bool
    expires_at: datetime | None = None
