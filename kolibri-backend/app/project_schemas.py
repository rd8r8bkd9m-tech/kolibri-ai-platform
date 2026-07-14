"""Public contracts for durable project and conversation history."""

from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.estimate_evidence import PriceEvidenceRecord


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
    sum: str = Field(min_length=1, max_length=64, pattern=DECIMAL_PATTERN)
    source: str = Field(default="", max_length=1_000)
    price_evidence: list[PriceEvidenceRecord] = Field(default_factory=list, max_length=50)
    comment: str = Field(default="", max_length=1_000)

    @model_validator(mode="after")
    def require_deterministic_sum_and_trusted_source(self):
        expected = (_metadata_decimal(self.quantity) * _metadata_decimal(self.price)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if _metadata_decimal(self.sum) != expected:
            raise ValueError("estimate position sum is not deterministic")
        expected_sources = {record.url for record in self.price_evidence}
        if self.source and self.source not in expected_sources:
            raise ValueError("estimate position source is not backed by price evidence")
        return self


class PersistedEstimateSection(_StrictMetadataModel):
    title: str = Field(min_length=1, max_length=240)
    positions: list[PersistedEstimatePosition] = Field(default_factory=list, max_length=500)


class PersistedEstimateTotals(_StrictMetadataModel):
    subtotal: str = Field(min_length=1, max_length=64, pattern=DECIMAL_PATTERN)
    overhead_amount: str = Field(min_length=1, max_length=64, pattern=DECIMAL_PATTERN)
    vat_amount: str = Field(min_length=1, max_length=64, pattern=DECIMAL_PATTERN)
    total: str = Field(min_length=1, max_length=64, pattern=DECIMAL_PATTERN)


class PersistedEvidenceIssue(_StrictMetadataModel):
    code: str = Field(min_length=1, max_length=80)
    position_code: str = Field(default="", max_length=80)
    message: str = Field(min_length=1, max_length=500)


class PersistedEstimateDraft(_StrictMetadataModel):
    title: str = Field(min_length=1, max_length=160)
    client: str = Field(default="", max_length=240)
    object_name: str = Field(default="", max_length=240)
    region: str = Field(default="", max_length=240)
    currency: str = Field(default="RUB", min_length=1, max_length=8)
    overhead_rate: str = Field(default="0", min_length=1, max_length=64, pattern=DECIMAL_PATTERN)
    vat_rate: str = Field(default="0", min_length=1, max_length=64, pattern=DECIMAL_PATTERN)
    sections: list[PersistedEstimateSection] = Field(default_factory=list, max_length=100)
    estimate_status: Literal["needs_input", "preliminary", "source_backed", "verified"]
    pricing_status: Literal["needs_input", "preliminary", "source_backed", "verified"]
    scope_status: Literal["unverified", "verified"] = "unverified"
    price_sources: list[PriceEvidenceRecord] = Field(default_factory=list, max_length=5_000)
    evidence_issues: list[PersistedEvidenceIssue] = Field(default_factory=list, max_length=200)
    source_note: str = Field(default="", max_length=2_000)
    assumptions: list[str] = Field(default_factory=list, max_length=100)
    questions: list[str] = Field(default_factory=list, max_length=100)
    totals: PersistedEstimateTotals

    @model_validator(mode="after")
    def bound_position_count(self):
        positions = [position for section in self.sections for position in section.positions]
        if len(positions) > 2_000:
            raise ValueError("estimate action contains too many positions")
        subtotal = sum(
            (
                (_metadata_decimal(position.quantity) * _metadata_decimal(position.price)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                for position in positions
            ),
            Decimal("0"),
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        overhead = (subtotal * _metadata_decimal(self.overhead_rate) / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        vat = ((subtotal + overhead) * _metadata_decimal(self.vat_rate) / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        expected = (subtotal, overhead, vat, subtotal + overhead + vat)
        actual = tuple(
            _metadata_decimal(value)
            for value in (
                self.totals.subtotal,
                self.totals.overhead_amount,
                self.totals.vat_amount,
                self.totals.total,
            )
        )
        if actual != expected:
            raise ValueError("estimate totals are not deterministic")

        flattened = [record for position in positions for record in position.price_evidence]
        flattened_keys = {(record.position_code, record.source_id, record.content_sha256) for record in flattened}
        top_level_keys = {
            (record.position_code, record.source_id, record.content_sha256)
            for record in self.price_sources
        }
        if flattened_keys != top_level_keys:
            raise ValueError("price_sources must exactly match position evidence")
        positive = [position for position in positions if _metadata_decimal(position.quantity) > 0 and _metadata_decimal(position.price) > 0]
        complete = bool(positive) and len(positive) == len(positions)
        # Project-message actions are public/browser-submitted metadata.  A
        # 64-hex attestation is only opaque input here: this contract cannot
        # establish that it came from the trusted collector.  Keep evidence
        # intact for the later estimate materialization endpoint, where its
        # HMAC is actually verified, but never persist a promoted display
        # status in an executable action.  Promoted truth is represented only
        # by a server-derived persisted artifact reference.
        safe_status = "preliminary" if complete else "needs_input"
        self.pricing_status = safe_status
        self.estimate_status = safe_status
        self.scope_status = "unverified"
        return self


def _metadata_decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid estimate decimal") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError("estimate decimal must be finite and non-negative")
    return parsed


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

    @model_validator(mode="after")
    def normalize_untrusted_label(self):
        self.label = (
            "Уточнить данные для сметы"
            if self.data.estimate_status == "needs_input"
            else "Открыть предварительную смету"
        )
        return self


class PersistedDocumentAction(_StrictMetadataModel):
    type: Literal["create_document"]
    label: str = Field(min_length=1, max_length=120)
    data: PersistedDocumentDraft


class PersistedImageAction(_StrictMetadataModel):
    type: Literal["present_image"]
    label: str = Field(min_length=1, max_length=120)
    data: PersistedImageArtifact


class PersistedFileArtifactMetadata(_StrictMetadataModel):
    scope_key: str = Field(pattern=SHA256_PATTERN)
    producer_capability: Literal[
        "document.pdf",
        "document.docx",
        "document.xlsx",
        "document.pptx",
        "site.create",
        "app.create",
    ]
    slide_count: int | None = Field(default=None, ge=1, le=10_000)
    entrypoint: Literal["index.html"] | None = None
    file_count: int | None = Field(default=None, ge=1, le=100_000)
    provider: str | None = Field(default=None, min_length=1, max_length=80)
    model: str | None = Field(default=None, min_length=1, max_length=120)


class PersistedFileArtifact(_StrictMetadataModel):
    id: str = Field(pattern=UUID_PATTERN)
    type: Literal[
        "document.pdf",
        "document.docx",
        "document.xlsx",
        "document.pptx",
        "site.bundle",
        "app.bundle",
    ]
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=240)
    filename: str = Field(min_length=1, max_length=240)
    mime_type: str = Field(min_length=1, max_length=160)
    size_bytes: int = Field(gt=0, le=100 * 1024 * 1024)
    sha256: str = Field(pattern=SHA256_PATTERN)
    created_at: str = Field(min_length=1, max_length=64)
    updated_at: str = Field(min_length=1, max_length=64)
    metadata: PersistedFileArtifactMetadata
    url: str = Field(min_length=1, max_length=240)
    download_url: str = Field(min_length=1, max_length=280)
    revision_url: str = Field(min_length=1, max_length=280)
    revision_download_url: str = Field(min_length=1, max_length=320)
    reopen_url: str = Field(min_length=1, max_length=280)
    history_url: str = Field(min_length=1, max_length=280)

    @model_validator(mode="after")
    def verify_canonical_manifest_contract(self):
        expected = {
            "document.pdf": ("application/pdf", ".pdf", "document.pdf"),
            "document.docx": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".docx",
                "document.docx",
            ),
            "document.xlsx": (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".xlsx",
                "document.xlsx",
            ),
            "document.pptx": (
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                ".pptx",
                "document.pptx",
            ),
            "site.bundle": ("application/zip", ".zip", "site.create"),
            "app.bundle": ("application/zip", ".zip", "app.create"),
        }[self.type]
        mime_type, extension, producer = expected
        if self.mime_type != mime_type or not self.filename.lower().endswith(extension):
            raise ValueError("file artifact media contract is invalid")
        if self.metadata.producer_capability != producer:
            raise ValueError("file artifact producer contract is invalid")
        canonical = f"/api/v1/artifacts/{self.id}"
        revision_url = f"{canonical}?revision={self.revision}"
        if (
            self.url != canonical
            or self.download_url != f"{canonical}?download=true"
            or self.revision_url != revision_url
            or self.revision_download_url != f"{revision_url}&download=true"
            or self.reopen_url != f"{canonical}/reopen"
            or self.history_url != f"{canonical}/history"
        ):
            raise ValueError("file artifact retrieval contract is invalid")
        for timestamp in (self.created_at, self.updated_at):
            try:
                datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("file artifact timestamp is invalid") from exc
        return self


class PersistedFileAction(_StrictMetadataModel):
    type: Literal["present_artifact"]
    label: str = Field(min_length=1, max_length=120)
    data: PersistedFileArtifact


PersistedAction = Annotated[
    PersistedEstimateAction | PersistedDocumentAction | PersistedImageAction | PersistedFileAction,
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


class PersistedFileArtifactReference(_StrictMetadataModel):
    type: Literal["file"]
    value: PersistedFileArtifact


PersistedArtifact = Annotated[
    PersistedEstimateArtifact
    | PersistedDocumentArtifact
    | PersistedImageArtifact
    | PersistedFileArtifactReference,
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


class ProjectHandoffClaim(BaseModel):
    token: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]{43}$")


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
