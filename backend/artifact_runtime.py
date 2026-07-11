"""Typed, side-effect-free contracts for Kolibri artifact runtimes.

The HTTP compatibility layer persists these declarations and dispatch intent;
it does not start browsers, containers, document renderers, builds, or network
requests in the request handler.  Runtime adapters must independently enforce
the recorded isolation and SSRF policy before reporting evidence.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal
from urllib.parse import SplitResult, urlsplit, urlunsplit

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_STRUCTURED_BYTES = 128 * 1024
MAX_STRUCTURED_DEPTH = 10
MAX_STRUCTURED_ITEMS = 2_000
MONEY_ENGINE = "kolibri.decimal-minor-unit.v1"
NETWORK_POLICY_VERSION = "kolibri.public-network.v1"

_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,199}$")
_SCHEDULE = re.compile(r"^[A-Za-z0-9*/?,#LW\-\s]{5,200}$")
_EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_.-]{0,199}$")
_FORBIDDEN_RUNTIME_KEYS = {
    "argv",
    "bash",
    "cmd",
    "command",
    "cwd",
    "environment",
    "exec",
    "executable",
    "powershell",
    "script",
    "shell",
    "subprocess",
}
_SECRET_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "cookie",
    "credentials",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "secret_key",
    "session_cookie",
    "token",
    "webhook_secret",
}
_METADATA_HOSTS = {
    "169.254.169.254",
    "metadata",
    "metadata.aws.internal",
    "metadata.google.internal",
    "metadata.google.internal.",
    "metadata.oraclecloud.com",
}
_PRIVATE_SUFFIXES = (
    ".internal",
    ".intranet",
    ".lan",
    ".local",
    ".localhost",
    ".home.arpa",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ScopedMutation(StrictModel):
    idempotency_key: str = Field(min_length=1, max_length=300)
    project_id: str | None = Field(default=None, min_length=3, max_length=200)
    workstream_id: str | None = Field(default=None, min_length=3, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_structured_value(value, label="metadata")
        return value


class RuntimeCancel(StrictModel):
    idempotency_key: str = Field(min_length=1, max_length=300)
    reason: str = Field(default="cancelled_by_client", min_length=1, max_length=500)


class ArtifactLinkInput(StrictModel):
    artifact_id: str = Field(min_length=3, max_length=200)
    relation: Literal[
        "source",
        "input",
        "output",
        "evidence",
        "canvas-node",
        "estimate",
        "document",
        "build",
        "preview",
    ] = "input"
    expected_kind: str | None = Field(default=None, min_length=1, max_length=80)


class CanvasPosition(StrictModel):
    x: float
    y: float


class CanvasNodeCreate(StrictModel):
    id: str = Field(min_length=3, max_length=200)
    renderer: Literal[
        "website",
        "webapp",
        "browser",
        "pdf",
        "pdf-x",
        "xlsx",
        "docx",
        "estimate",
        "image",
        "audio",
        "video",
        "code",
        "diff",
        "build",
        "test-report",
        "terminal-log",
        "plan",
        "automation",
    ]
    artifact_id: str = Field(min_length=3, max_length=200)
    artifact_kind: str | None = Field(default=None, min_length=1, max_length=80)
    position: CanvasPosition
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _SAFE_IDENTIFIER.fullmatch(value):
            raise ValueError("canvas node id has invalid characters")
        return value

    @field_validator("settings")
    @classmethod
    def validate_settings(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_structured_value(value, label="canvas settings")
        reject_runtime_instructions(value, label="canvas settings")
        return value


class CanvasEdgeCreate(StrictModel):
    id: str = Field(min_length=3, max_length=200)
    source: str = Field(min_length=3, max_length=200)
    target: str = Field(min_length=3, max_length=200)
    kind: str = Field(default="flow", min_length=1, max_length=80)

    @field_validator("id", "source", "target")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _SAFE_IDENTIFIER.fullmatch(value):
            raise ValueError("canvas edge identifiers have invalid characters")
        return value


class CanvasCreate(ScopedMutation):
    project_id: str = Field(min_length=3, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    nodes: list[CanvasNodeCreate] = Field(default_factory=list, max_length=500)
    edges: list[CanvasEdgeCreate] = Field(default_factory=list, max_length=2_000)

    @model_validator(mode="after")
    def validate_graph(self) -> "CanvasCreate":
        node_ids = [node.id for node in self.nodes]
        edge_ids = [edge.id for edge in self.edges]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("canvas node ids must be unique")
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("canvas edge ids must be unique")
        unknown = sorted(
            {endpoint for edge in self.edges for endpoint in (edge.source, edge.target)}
            - set(node_ids)
        )
        if unknown:
            raise ValueError(f"canvas edges reference unknown nodes: {unknown}")
        return self


class NetworkRuntimePolicy(StrictModel):
    allowed_origins: list[str] = Field(default_factory=list, max_length=64)
    max_redirects: int = Field(default=5, ge=0, le=10)
    downloads: Literal["deny"] = "deny"


class PreviewCreate(ScopedMutation):
    source_artifact: ArtifactLinkInput | None = None
    entry_url: str | None = Field(default=None, min_length=8, max_length=2_048)
    isolation_profile: Literal["ephemeral-container"] = "ephemeral-container"
    network: NetworkRuntimePolicy = Field(default_factory=NetworkRuntimePolicy)
    expires_in_seconds: int = Field(default=3_600, ge=60, le=86_400)

    @model_validator(mode="after")
    def require_source(self) -> "PreviewCreate":
        if self.source_artifact is None and self.entry_url is None:
            raise ValueError("preview requires source_artifact or entry_url")
        return self


class BrowserViewport(StrictModel):
    width: int = Field(default=1_280, ge=320, le=7_680)
    height: int = Field(default=720, ge=240, le=4_320)
    device_scale_factor: Decimal = Field(default=Decimal("1"), ge=Decimal("0.25"), le=Decimal("4"))


class BrowserSessionCreate(ScopedMutation):
    start_url: str = Field(min_length=8, max_length=2_048)
    allowed_origins: list[str] = Field(default_factory=list, max_length=64)
    viewport: BrowserViewport = Field(default_factory=BrowserViewport)
    locale: str = Field(default="ru-RU", pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$")
    credential_binding_id: str | None = Field(default=None, min_length=3, max_length=200)
    isolation_profile: Literal["ephemeral-browser-profile"] = "ephemeral-browser-profile"


class EstimatePriceProvenance(StrictModel):
    source: Literal[
        "manual",
        "assumption",
        "normative",
        "catalog",
        "contract",
        "supplier",
        "measurement",
    ] = "manual"
    source_ref: str | None = Field(default=None, min_length=1, max_length=500)
    source_url: str | None = Field(
        default=None,
        min_length=8,
        max_length=2_048,
        pattern=r"^https?://[^\s]+$",
    )
    captured_at: str | None = Field(default=None, max_length=80)
    applicable_region: str | None = Field(default=None, min_length=1, max_length=300)
    price_level_date: str | None = Field(default=None, min_length=1, max_length=80)
    basis_ref: str | None = Field(default=None, min_length=1, max_length=500)
    quantity_source: Literal["project", "measurement", "manual"] | None = None
    quantity_source_ref: str | None = Field(default=None, min_length=1, max_length=500)
    quantity_source_url: str | None = Field(
        default=None,
        min_length=8,
        max_length=2_048,
        pattern=r"^https?://[^\s]+$",
    )
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    validation_status: Literal["unverified", "verified"] = "unverified"

    @model_validator(mode="after")
    def validate_assumptions(self) -> "EstimatePriceProvenance":
        if any(not value.strip() or len(value) > 1_000 for value in self.assumptions):
            raise ValueError("estimate provenance assumptions must contain 1 to 1000 characters")
        return self


class EstimateNormativeBasis(StrictModel):
    calculation_method: Literal[
        "resource-index",
        "resource",
        "base-index",
        "contract",
        "commercial",
    ]
    normative_basis_ref: str = Field(min_length=1, max_length=1_000)
    normative_edition: str = Field(min_length=1, max_length=300)
    price_level_date: str = Field(min_length=1, max_length=80)
    region: str = Field(min_length=1, max_length=300)
    index_document_refs: list[str] = Field(default_factory=list, max_length=20)
    tax_scope_ref: str = Field(min_length=1, max_length=1_000)
    contract_scope_ref: str = Field(min_length=1, max_length=1_000)
    source_urls: list[str] = Field(default_factory=list, max_length=20)
    input_document_refs: list[str] = Field(default_factory=list, max_length=100)
    validation_status: Literal["unverified", "verified"] = "unverified"

    @model_validator(mode="after")
    def validate_refs(self) -> "EstimateNormativeBasis":
        if any(not value.strip() or len(value) > 1_000 for value in self.index_document_refs):
            raise ValueError("estimate index document refs must contain 1 to 1000 characters")
        if any(not value.strip() or len(value) > 2_048 or not re.fullmatch(r"https?://[^\s]+", value) for value in self.source_urls):
            raise ValueError("estimate source URLs must be bounded HTTP(S) URLs")
        if any(not value.strip() or len(value) > 1_000 for value in self.input_document_refs):
            raise ValueError("estimate input document refs must contain 1 to 1000 characters")
        if self.calculation_method in {"resource-index", "base-index"} and not self.index_document_refs:
            raise ValueError("indexed estimate method requires index document refs")
        return self


class EstimateLineCreate(StrictModel):
    id: str = Field(min_length=3, max_length=200)
    section: str = Field(default="Основные работы", min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1_000)
    category: Literal["labor", "material", "equipment", "service", "other"] = "other"
    unit: str = Field(default="unit", min_length=1, max_length=40)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    unit_price_minor: int = Field(ge=0, le=10**15)
    provenance: EstimatePriceProvenance = Field(default_factory=EstimatePriceProvenance)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _SAFE_IDENTIFIER.fullmatch(value):
            raise ValueError("estimate line id has invalid characters")
        return value


class EstimateSpec(StrictModel):
    title: str = Field(min_length=1, max_length=500)
    currency: str = Field(default="RUB", pattern=r"^[A-Z]{3}$")
    minor_unit: Literal[0, 2, 3] = 2
    region: str = Field(default="Не указан", min_length=1, max_length=300)
    client_name: str | None = Field(default=None, max_length=300)
    object_name: str | None = Field(default=None, max_length=500)
    object_address: str | None = Field(default=None, max_length=1_000)
    source_summary: str = Field(
        default="Цены требуют проверки перед коммерческим использованием",
        min_length=1,
        max_length=2_000,
    )
    normative_basis: EstimateNormativeBasis | None = None
    assumptions: list[str] = Field(default_factory=list, max_length=100)
    questions: list[str] = Field(default_factory=list, max_length=100)
    lines: list[EstimateLineCreate] = Field(min_length=1, max_length=2_000)
    overhead_rate_bps: int = Field(default=0, ge=0, le=10_000)
    tax_rate_bps: int = Field(default=0, ge=0, le=10_000)

    @model_validator(mode="after")
    def validate_lines(self) -> "EstimateSpec":
        line_ids = [line.id for line in self.lines]
        if len(line_ids) != len(set(line_ids)):
            raise ValueError("estimate line ids must be unique")
        for label, values in (("assumption", self.assumptions), ("question", self.questions)):
            if any(not value.strip() or len(value) > 2_000 for value in values):
                raise ValueError(f"estimate {label} must contain 1 to 2000 characters")
        return self


class EstimateCreate(ScopedMutation, EstimateSpec):
    artifact_links: list[ArtifactLinkInput] = Field(default_factory=list, max_length=100)


class DocumentCreate(ScopedMutation):
    title: str = Field(min_length=1, max_length=500)
    document_type: Literal[
        "commercial-offer",
        "contract",
        "completion-act",
        "invoice",
        "report",
        "estimate",
        "custom",
    ]
    format: Literal["pdf", "pdf-x", "xlsx", "docx", "html", "text"]
    estimate_id: str | None = Field(default=None, min_length=3, max_length=200)
    artifact_links: list[ArtifactLinkInput] = Field(default_factory=list, max_length=100)
    content: dict[str, Any] = Field(default_factory=dict)
    locale: str = Field(default="ru-RU", pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$")
    template_id: str | None = Field(default=None, min_length=3, max_length=200)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_structured_value(value, label="document content")
        reject_runtime_instructions(value, label="document content")
        return value

    @model_validator(mode="after")
    def require_source(self) -> "DocumentCreate":
        if self.estimate_id is None and not self.artifact_links and not self.content:
            raise ValueError("document requires estimate_id, artifact_links, or content")
        return self


class BuildCreate(ScopedMutation):
    name: str = Field(min_length=1, max_length=300)
    target: Literal["web", "linux", "container", "android", "ios", "macos"]
    source_artifact: ArtifactLinkInput
    source_ref: str | None = Field(default=None, min_length=1, max_length=300)
    configuration: Literal["debug", "release"] = "release"
    checks: list[
        Literal["compile", "unit-tests", "integration-tests", "browser-qa", "security", "signing"]
    ] = Field(default_factory=lambda: ["compile", "unit-tests"], max_length=20)
    requires_signing: bool = False

    @field_validator("source_ref")
    @classmethod
    def validate_source_ref(cls, value: str | None) -> str | None:
        if value and ("\x00" in value or "\n" in value or "\r" in value):
            raise ValueError("source_ref contains control characters")
        return value

    @model_validator(mode="after")
    def validate_target(self) -> "BuildCreate":
        if self.requires_signing and self.target not in {"ios", "macos", "android", "container"}:
            raise ValueError("signing is not supported for this target")
        return self


class RetryPolicy(StrictModel):
    max_attempts: int = Field(default=3, ge=1, le=20)
    backoff_seconds: Decimal = Field(default=Decimal("1"), ge=0, le=3_600)
    max_backoff_seconds: Decimal = Field(default=Decimal("60"), ge=0, le=86_400)
    jitter: bool = True

    @model_validator(mode="after")
    def validate_backoff(self) -> "RetryPolicy":
        if self.max_backoff_seconds < self.backoff_seconds:
            raise ValueError("max_backoff_seconds must be >= backoff_seconds")
        return self


class AutomationTrigger(StrictModel):
    kind: Literal["manual", "schedule", "webhook", "event", "file"]
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("config")
    @classmethod
    def validate_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_structured_value(value, label="automation trigger config")
        reject_secret_material(value, label="automation trigger config")
        reject_runtime_instructions(value, label="automation trigger config")
        return value

    @model_validator(mode="after")
    def validate_kind_config(self) -> "AutomationTrigger":
        if self.kind == "schedule":
            expression = self.config.get("expression")
            if not isinstance(expression, str) or not _SCHEDULE.fullmatch(expression):
                raise ValueError("schedule trigger requires a safe cron expression")
        elif self.kind == "event":
            event_type = self.config.get("event_type")
            if not isinstance(event_type, str) or not _EVENT_TYPE.fullmatch(event_type):
                raise ValueError("event trigger requires event_type")
        elif self.kind == "webhook" and not self.config.get("credential_ref"):
            raise ValueError("webhook trigger requires credential_ref, not a raw secret")
        elif self.kind == "file":
            if not self.config.get("artifact_kind") and not self.config.get("event_type"):
                raise ValueError("file trigger requires artifact_kind or event_type")
            if any(key in self.config for key in ("path", "directory", "mount")):
                raise ValueError("file triggers use artifact events, not host filesystem paths")
        return self


class AutomationStep(StrictModel):
    id: str = Field(min_length=3, max_length=200)
    kind: Literal["model", "api", "browser", "document", "factory-task", "condition", "parallel", "approval"]
    config: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list, max_length=100)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    approval: Literal["inherit", "owner", "none"] = "inherit"

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _SAFE_IDENTIFIER.fullmatch(value):
            raise ValueError("automation step id has invalid characters")
        return value

    @field_validator("config")
    @classmethod
    def validate_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_structured_value(value, label="automation step config")
        reject_secret_material(value, label="automation step config")
        reject_runtime_instructions(value, label="automation step config")
        return value


class AutomationSpec(StrictModel):
    name: str = Field(min_length=1, max_length=300)
    version: Literal[1] = 1
    enabled: bool = False
    trigger: AutomationTrigger
    steps: list[AutomationStep] = Field(min_length=1, max_length=500)
    approval_policy: Literal["none", "owner", "per-side-effect"] = "owner"

    @model_validator(mode="after")
    def validate_graph(self) -> "AutomationSpec":
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("automation step ids must be unique")
        known = set(step_ids)
        unknown = sorted({item for step in self.steps for item in step.depends_on} - known)
        if unknown:
            raise ValueError(f"automation steps have unknown dependencies: {unknown}")
        if any(step.id in step.depends_on for step in self.steps):
            raise ValueError("automation step cannot depend on itself")
        _topological_order(self.steps)
        return self


class AutomationCreate(ScopedMutation, AutomationSpec):
    pass


class AutomationValidate(AutomationSpec):
    project_id: str | None = Field(default=None, min_length=3, max_length=200)
    workstream_id: str | None = Field(default=None, min_length=3, max_length=200)


def validate_structured_value(value: Any, *, label: str) -> None:
    count = 0

    def walk(item: Any, depth: int) -> None:
        nonlocal count
        count += 1
        if count > MAX_STRUCTURED_ITEMS:
            raise ValueError(f"{label} contains too many values")
        if depth > MAX_STRUCTURED_DEPTH:
            raise ValueError(f"{label} is nested too deeply")
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ValueError(f"{label} keys must be strings")
                walk(child, depth + 1)
        elif isinstance(item, (list, tuple)):
            for child in item:
                walk(child, depth + 1)
        elif not isinstance(item, (str, int, float, bool, type(None), Decimal)):
            raise ValueError(f"{label} contains an unsupported value")

    walk(value, 0)
    encoded = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_STRUCTURED_BYTES:
        raise ValueError(f"{label} exceeds {MAX_STRUCTURED_BYTES} bytes")


def _normalized_key(value: Any) -> str:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(value).strip())
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _is_secret_key(value: Any) -> bool:
    normalized = _normalized_key(value)
    return normalized in _SECRET_KEYS or normalized.endswith(
        (
            "_access_token",
            "_api_key",
            "_authorization",
            "_client_secret",
            "_cookie",
            "_password",
            "_private_key",
            "_refresh_token",
            "_secret",
            "_session_cookie",
            "_token",
            "_webhook_secret",
        )
    )


def _walk_keys(value: Any, path: tuple[str, ...] = ()):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = _normalized_key(key)
            current = (*path, normalized)
            yield current, child
            yield from _walk_keys(child, current)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from _walk_keys(child, (*path, str(index)))


def reject_secret_material(value: Any, *, label: str) -> None:
    forbidden = [".".join(path) for path, _ in _walk_keys(value) if _is_secret_key(path[-1])]
    if forbidden:
        raise ValueError(f"{label} must use credential_ref instead of secret fields: {sorted(forbidden)}")


def reject_runtime_instructions(value: Any, *, label: str) -> None:
    forbidden = [".".join(path) for path, _ in _walk_keys(value) if path[-1] in _FORBIDDEN_RUNTIME_KEYS]
    if forbidden:
        raise ValueError(f"{label} cannot contain shell/process instructions: {sorted(forbidden)}")


def _normalize_hostname(raw_hostname: str) -> str:
    if any(character in raw_hostname for character in ("%", "\\", "\x00", "\r", "\n", "\t", " ")):
        raise HTTPException(status_code=422, detail="URL hostname contains forbidden characters")
    hostname = raw_hostname.rstrip(".").lower()
    if not hostname:
        raise HTTPException(status_code=422, detail="URL hostname is required")
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise HTTPException(status_code=422, detail="URL hostname is invalid") from exc
    if len(hostname) > 253:
        raise HTTPException(status_code=422, detail="URL hostname is too long")
    return hostname


def validate_public_http_url(value: str) -> dict[str, Any]:
    """Perform pure static URL checks and return the mandatory runtime policy.

    Domain names are never declared safe based on syntax alone.  The execution
    adapter must resolve them immediately before use and before every redirect,
    reject any non-global address, pin the public result set for the navigation,
    and fail on resolution changes.  This is the DNS-rebinding boundary.
    """

    if len(value) > 2_048 or any(character in value for character in ("\x00", "\r", "\n", "\t", "\\")):
        raise HTTPException(status_code=422, detail="URL contains forbidden characters")
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise HTTPException(status_code=422, detail="only http and https URLs are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise HTTPException(status_code=422, detail="URL userinfo is forbidden")
    if parsed.fragment:
        parsed = SplitResult(parsed.scheme, parsed.netloc, parsed.path, parsed.query, "")
    raw_hostname = parsed.hostname
    if raw_hostname is None:
        raise HTTPException(status_code=422, detail="URL hostname is required")
    hostname = _normalize_hostname(raw_hostname)
    if hostname in _METADATA_HOSTS or hostname == "localhost" or hostname.endswith(_PRIVATE_SUFFIXES):
        raise HTTPException(status_code=422, detail="private or metadata hostname is forbidden")
    try:
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="URL port is invalid") from exc
    if port is not None and not 1 <= port <= 65_535:
        raise HTTPException(status_code=422, detail="URL port is invalid")

    literal_ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None
    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        if not literal_ip.is_global:
            raise HTTPException(status_code=422, detail="non-public IP address is forbidden")
        dns_status = "literal_public_ip"
    else:
        # Reject legacy/ambiguous numeric forms (integer, octal, or shortened
        # IPv4).  They are interpreted differently by URL clients and DNS.
        if all(character in "0123456789.xabcdef" for character in hostname):
            raise HTTPException(status_code=422, detail="ambiguous numeric hostname is forbidden")
        labels = hostname.split(".")
        if len(labels) < 2 or any(not _HOST_LABEL.fullmatch(label) for label in labels):
            raise HTTPException(status_code=422, detail="public DNS hostname is required")
        dns_status = "required_at_execution"

    normalized_netloc = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None:
        normalized_netloc += f":{port}"
    normalized = urlunsplit((parsed.scheme.lower(), normalized_netloc, parsed.path or "/", parsed.query, ""))
    return {
        "normalized_url": normalized,
        "hostname": hostname,
        "static_validation": "passed",
        "dns_verification": dns_status,
        "policy": {
            "version": NETWORK_POLICY_VERSION,
            "allowed_schemes": ["http", "https"],
            "deny_loopback_link_local_private_reserved_metadata": True,
            "resolve_immediately_before_navigation": True,
            "require_every_resolved_address_global": True,
            "pin_resolution_for_navigation": True,
            "revalidate_before_each_redirect": True,
            "fail_on_resolution_change": True,
        },
    }


def validate_origin(value: str) -> dict[str, Any]:
    validated = validate_public_http_url(value)
    parsed = urlsplit(validated["normalized_url"])
    origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    return {**validated, "normalized_origin": origin}


def deterministic_estimate(spec: EstimateSpec) -> dict[str, Any]:
    one = Decimal("1")
    line_results: list[dict[str, Any]] = []
    subtotal_minor = 0
    category_totals: dict[str, int] = {}
    for line in spec.lines:
        line_total = int((line.quantity * Decimal(line.unit_price_minor)).quantize(one, rounding=ROUND_HALF_UP))
        subtotal_minor += line_total
        category_totals[line.category] = category_totals.get(line.category, 0) + line_total
        line_results.append({
            "id": line.id,
            "section": line.section,
            "description": line.description,
            "category": line.category,
            "unit": line.unit,
            "quantity": format(line.quantity, "f"),
            "unit_price_minor": line.unit_price_minor,
            "line_total_minor": line_total,
            "provenance": line.provenance.model_dump(mode="json"),
        })
    overhead_minor = int(
        (Decimal(subtotal_minor) * Decimal(spec.overhead_rate_bps) / Decimal(10_000)).quantize(
            one, rounding=ROUND_HALF_UP
        )
    )
    taxable_minor = subtotal_minor + overhead_minor
    tax_minor = int(
        (Decimal(taxable_minor) * Decimal(spec.tax_rate_bps) / Decimal(10_000)).quantize(
            one, rounding=ROUND_HALF_UP
        )
    )
    grand_total_minor = taxable_minor + tax_minor
    calculation = {
        "engine": MONEY_ENGINE,
        "currency": spec.currency,
        "minor_unit": spec.minor_unit,
        "rounding": "ROUND_HALF_UP",
        "rate_denominator": 10_000,
        "overhead_rate_bps": spec.overhead_rate_bps,
        "tax_rate_bps": spec.tax_rate_bps,
        "lines": line_results,
        "totals": {
            "categories_minor": dict(sorted(category_totals.items())),
            "subtotal_minor": subtotal_minor,
            "overhead_minor": overhead_minor,
            "taxable_minor": taxable_minor,
            "tax_minor": tax_minor,
            "grand_total_minor": grand_total_minor,
        },
        "money_authority": "deterministic_calculator",
        "llm_calculates_money": False,
    }
    fingerprint_payload = json.dumps(
        calculation, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    calculation["calculation_sha256"] = hashlib.sha256(fingerprint_payload).hexdigest()
    return calculation


def _is_side_effect_step(step: AutomationStep) -> bool:
    if step.kind == "api":
        return str(step.config.get("method", "GET")).upper() not in {"GET", "HEAD", "OPTIONS"}
    if step.kind == "browser":
        return str(step.config.get("action", "navigate")) not in {"navigate", "inspect", "screenshot", "extract"}
    return step.kind in {"document", "factory-task"}


def _topological_order(steps: list[AutomationStep]) -> list[str]:
    dependencies = {step.id: set(step.depends_on) for step in steps}
    ready = sorted(step_id for step_id, deps in dependencies.items() if not deps)
    order: list[str] = []
    while ready:
        step_id = ready.pop(0)
        order.append(step_id)
        for candidate, deps in dependencies.items():
            if step_id in deps:
                deps.remove(step_id)
                if not deps and candidate not in order and candidate not in ready:
                    ready.append(candidate)
                    ready.sort()
    if len(order) != len(steps):
        raise ValueError("automation dependencies contain a cycle")
    return order


def validate_automation(spec: AutomationSpec) -> dict[str, Any]:
    url_policies: list[dict[str, Any]] = []
    for step in spec.steps:
        if step.kind in {"api", "browser"}:
            url_value = step.config.get("url")
            if not isinstance(url_value, str):
                raise HTTPException(status_code=422, detail=f"automation step {step.id} requires url")
            url_policies.append({"step_id": step.id, **validate_public_http_url(url_value)})
        if step.kind == "api":
            method = str(step.config.get("method", "GET")).upper()
            if method not in {"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"}:
                raise HTTPException(status_code=422, detail=f"automation step {step.id} has unsupported HTTP method")
        if step.kind == "browser":
            action = str(step.config.get("action", "navigate"))
            if action not in {"navigate", "inspect", "screenshot", "extract", "click", "type", "submit"}:
                raise HTTPException(status_code=422, detail=f"automation step {step.id} has unsupported browser action")
    side_effect_ids = [step.id for step in spec.steps if _is_side_effect_step(step)]
    if side_effect_ids and spec.approval_policy == "none":
        raise HTTPException(
            status_code=422,
            detail={"approval_required_for_side_effect_steps": side_effect_ids},
        )
    if spec.approval_policy == "per-side-effect":
        unapproved = [
            step.id for step in spec.steps if step.id in side_effect_ids and step.approval == "none"
        ]
        if unapproved:
            raise HTTPException(
                status_code=422,
                detail={"per_side_effect_approval_cannot_be_disabled": unapproved},
            )
    return {
        "valid": True,
        "dry_run": True,
        "executed": False,
        "version": spec.version,
        "trigger_kind": spec.trigger.kind,
        "topological_order": _topological_order(spec.steps),
        "side_effect_step_ids": side_effect_ids,
        "approval_policy": spec.approval_policy,
        "approval_gate_count": len(side_effect_ids) if spec.approval_policy == "per-side-effect" else int(bool(side_effect_ids)),
        "url_policies": url_policies,
    }


def validate_runtime_urls(primary_url: str, allowed_origins: list[str]) -> dict[str, Any]:
    primary = validate_public_http_url(primary_url)
    origins = [validate_origin(origin) for origin in allowed_origins]
    return {
        "primary": primary,
        "allowed_origins": origins,
        "runtime_dns_verification_required": any(
            item["dns_verification"] == "required_at_execution" for item in [primary, *origins]
        ),
    }
