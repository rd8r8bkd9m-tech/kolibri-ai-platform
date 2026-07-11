"""Versioned Kolibri AI OS execution compatibility API.

This Python module is a transitional compatibility layer.  Its contracts are
designed to survive a later move of the authoritative scheduler to the Rust
core: records are versioned, JSON serializable and persisted in SQLite rather
than represented by Python worker processes.
"""

from __future__ import annotations

import json
import hashlib
import hmac
import os
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from artifact_runtime import (
    ArtifactLinkInput,
    AutomationCreate,
    AutomationValidate,
    BrowserSessionCreate,
    BuildCreate,
    CanvasCreate,
    DocumentCreate,
    EstimateCreate,
    EstimateSpec,
    PreviewCreate,
    RuntimeCancel,
    deterministic_estimate,
    validate_automation,
    validate_origin,
    validate_runtime_urls,
)
from capability_gateway import CapabilityRequestError, get_capability_gateway
from data_paths import DB_PATH
from formulalm_boundary import (
    FormulaLMBoundary,
    FormulaLMConflictError,
    FormulaLMNotFoundError,
    FormulaLMPolicyError,
    scan_learning_payload,
)
from provider_gateway import deterministic_verifier_evidence, get_provider_gateway
from response_tool_gateway import ResponseToolExecution, execute_response_tools
from web_search_gateway import WebSearchError, WebSearchUnavailable
from vertical_tasks import (
    VerticalTask,
    build_vertical_result,
    failed_vertical_result,
    prepare_vertical_task,
)


API_VERSION = "kolibri.execution.v1"
DEFAULT_LOGICAL_ACTORS = 1000
TERMINAL_RESPONSE_STATUSES = {"completed", "failed", "cancelled", "incomplete"}
ACTIVE_WORKSTREAM_STATUSES = {"planned", "active", "blocked"}
ACTIVE_BACKLOG_STATES = {"backlog", "ready", "running", "blocked"}
TASK_TRANSITIONS = {
    "pending": {"ready", "cancelled"},
    "ready": {"queued", "blocked", "cancelled"},
    "queued": {"leased", "blocked", "cancelled"},
    "leased": {"running", "queued", "failed", "cancelled"},
    "running": {"completed", "failed", "blocked", "cancelled"},
    "blocked": {"ready", "failed", "cancelled"},
    "failed": {"ready"},
    "completed": set(),
    "cancelled": set(),
}
SENSITIVE_KEYS = {
    "access_token", "api_key", "apikey", "authorization", "bot_token", "client_secret",
    "cookie", "credential", "credentials", "jwt", "passwd", "password", "private_key",
    "refresh_token", "secret", "secret_key", "session_cookie", "ssh_key", "token",
    "webhook_secret", "aws_secret_access_key",
}
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"\b(?:sk|ghp|github_pat|xox[baprs])-[A-Za-z0-9_-]{12,}\b", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE),
    re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"[?&](?:access_token|api[_-]?key|auth|key|password|secret|sig|signature|token)=[^&#\s]+", re.IGNORECASE),
    re.compile(r"\b(?:access_token|api[_-]?key|authorization|password|secret|token)\s*[:=]\s*[^\s,;&]+", re.IGNORECASE),
)


def _configured_execution_key_hashes() -> frozenset[str]:
    """Load API credentials without retaining their cleartext value.

    The compatibility API is fail-closed when no credential is configured.
    Runtime deployments may provide one key or a comma-delimited rotation
    window.  The cleartext values are never written to SQLite or logs.
    """

    values: list[str] = []
    for name in ("KOLIBRI_API_KEY", "KOLIBRI_OWNER_API_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            values.append(value)
    values.extend(
        value.strip()
        for value in os.environ.get("KOLIBRI_API_KEYS", "").split(",")
        if value.strip()
    )
    return frozenset(hashlib.sha256(value.encode("utf-8")).hexdigest() for value in values)


_EXECUTION_KEY_HASHES = _configured_execution_key_hashes()


def configure_execution_auth(tokens: list[str] | tuple[str, ...]) -> None:
    """Install an in-memory credential set for an embedding or test harness."""

    global _EXECUTION_KEY_HASHES
    _EXECUTION_KEY_HASHES = frozenset(
        hashlib.sha256(str(token).encode("utf-8")).hexdigest()
        for token in tokens
        if str(token)
    )


def require_execution_auth(request: Request) -> str:
    """Require an OpenAI-style bearer credential for durable execution data."""

    if not _EXECUTION_KEY_HASHES:
        raise HTTPException(status_code=503, detail="execution_api_auth_not_configured")
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail="execution_api_auth_required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    candidate = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()
    if not any(hmac.compare_digest(candidate, expected) for expected in _EXECUTION_KEY_HASHES):
        raise HTTPException(
            status_code=401,
            detail="execution_api_auth_invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return f"api-key:{candidate[:16]}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _normalized_key(value: Any) -> str:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(value).strip())
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _is_sensitive_key(value: Any) -> bool:
    normalized = _normalized_key(value)
    return normalized in SENSITIVE_KEYS or normalized.endswith(
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
            "_ssh_key",
            "_token",
            "_webhook_secret",
        )
    )


def sanitize_learning_value(value: Any, key: str | None = None) -> Any:
    """Remove credentials and token-like material before durable storage."""
    if key is not None and _is_sensitive_key(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): sanitize_learning_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_learning_value(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_learning_value(item) for item in value]
    if isinstance(value, str):
        sanitized = value
        for pattern in SENSITIVE_VALUE_PATTERNS:
            sanitized = pattern.sub("[REDACTED]", sanitized)
        return sanitized
    return value


def sanitize_learning_payload(value: Any) -> tuple[Any, dict[str, Any]]:
    report: dict[str, Any] = {
        "schema_version": "kolibri.learning.sanitization.v1",
        "redacted_fields": 0,
        "redacted_field_paths": [],
        "redacted_value_patterns": 0,
        "secret_material_persisted": False,
    }

    def walk(item: Any, key: str | None = None, path: tuple[str, ...] = ()) -> Any:
        if key is not None and _is_sensitive_key(key):
            report["redacted_fields"] += 1
            report["redacted_field_paths"].append(".".join((*path, str(key))))
            return "[REDACTED]"
        if isinstance(item, dict):
            return {str(k): walk(v, str(k), path) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [walk(child, path=(*path, str(index))) for index, child in enumerate(item)]
        if isinstance(item, str):
            sanitized = item
            for pattern in SENSITIVE_VALUE_PATTERNS:
                sanitized, count = pattern.subn("[REDACTED]", sanitized)
                report["redacted_value_patterns"] += count
            return sanitized
        return item

    return walk(value), report


class IdempotentCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=300)


class ProjectCreate(IdempotentCreate):
    name: str = Field(min_length=1, max_length=200)
    objective: str = Field(default="", max_length=20_000)
    binding: str | None = Field(default=None, max_length=300)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkstreamCreate(IdempotentCreate):
    name: str = Field(min_length=1, max_length=200)
    objective: str = Field(default="", max_length=20_000)
    status: Literal["planned", "active", "blocked", "completed", "cancelled"] = "active"
    binding: str | None = Field(default=None, max_length=300)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BacklogItemCreate(IdempotentCreate):
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=50_000)
    priority: Literal["critical", "high", "normal", "low", "background"] = "normal"
    state: Literal["backlog", "ready", "running", "blocked", "done", "cancelled"] = "backlog"
    acceptance: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CheckpointCreate(IdempotentCreate):
    label: str = Field(min_length=1, max_length=300)
    summary: str = Field(default="", max_length=50_000)
    state: dict[str, Any] = Field(default_factory=dict)
    next_actions: list[str] = Field(default_factory=list)


class ResumeRequest(BaseModel):
    project_id: str | None = None
    binding: str | None = None
    workstream_id: str | None = None
    checkpoint_id: str | None = None
    create_new: bool = False
    idempotency_key: str | None = None
    project_name: str = "Kolibri Project"
    workstream_name: str = "Primary Workstream"


class ResponseTechnicalOptions(BaseModel):
    # Accepted only for wire compatibility. Public clients never control the
    # internal provider/model route; server policy owns provider selection.
    provider_preferences: list[str] = Field(default_factory=list, deprecated=True)


class ResponseLearningPolicy(BaseModel):
    """Explicit data-use policy for the FormulaLM trace tap.

    Omitted/unknown policy is audit-recorded as rejected and never enters the
    learning queue.  This is intentionally independent from inference.
    """

    consent: Literal["explicit", "contractual", "public-permitted", "denied", "unknown"] = "unknown"
    license: Literal["permitted", "restricted", "negative", "unknown"] = "unknown"
    retention_class: Literal["ephemeral", "project", "training-approved", "legal-hold"] = "project"
    data_classification: Literal["public", "internal", "private"] = "private"
    capability: str = Field(default="general.response", min_length=1, max_length=300)
    source_uri: str | None = Field(default=None, max_length=2_000)


class ResponseCreate(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=300)
    model: Literal["kolibri"] = "kolibri"
    input: str | list[dict[str, Any]]
    stream: bool = False
    previous_response_id: str | None = None
    execution_mode: Literal["fast", "codex"] = "fast"
    task: VerticalTask | None = None
    project_id: str | None = None
    workstream_id: str | None = None
    instructions: str | None = None
    tools: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    technical: ResponseTechnicalOptions = Field(default_factory=ResponseTechnicalOptions)
    learning: ResponseLearningPolicy = Field(default_factory=ResponseLearningPolicy)


class ChatCompletionCreate(BaseModel):
    model: Literal["kolibri"] = "kolibri"
    messages: list[dict[str, Any]] = Field(min_length=1, max_length=200)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    stream: bool = False
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=200_000)
    user: str | None = Field(default=None, max_length=300)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=300)
    learning: ResponseLearningPolicy = Field(default_factory=ResponseLearningPolicy)


class ProviderAttempt(BaseModel):
    attempt: int = Field(ge=1)
    provider: str
    model: str
    status: Literal["scheduled", "running", "succeeded", "failed", "blocked", "skipped"]
    reason: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class ProviderAttemptCreate(IdempotentCreate):
    provider: str
    model: str
    status: Literal["scheduled", "running", "succeeded", "failed", "blocked", "skipped"]
    reason: str | None = Field(default=None, max_length=2_000)
    started_at: str | None = None
    completed_at: str | None = None


class CanvasNode(BaseModel):
    id: str
    kind: str
    x: float = 0
    y: float = 0
    data: dict[str, Any] = Field(default_factory=dict)


class CanvasEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: str = "flow"


class CanvasArtifact(BaseModel):
    schema_version: str = "kolibri.canvas.v1"
    title: str
    nodes: list[CanvasNode] = Field(default_factory=list)
    edges: list[CanvasEdge] = Field(default_factory=list)


class PreviewArtifact(BaseModel):
    schema_version: str = "kolibri.preview.v1"
    url: str
    status: Literal["pending", "ready", "degraded", "failed", "expired"] = "pending"
    health_url: str | None = None
    expires_at: str | None = None


class AutomationArtifact(BaseModel):
    schema_version: str = "kolibri.automation.v1"
    name: str
    trigger: dict[str, Any]
    action: dict[str, Any]
    enabled: bool = False
    approval: Literal["auto", "owner-gated", "explicit"] = "owner-gated"


class FileArtifact(BaseModel):
    schema_version: str = "kolibri.file.v1"
    name: str
    media_type: str = "application/octet-stream"
    uri: str
    sha256: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)


class ArtifactCreateBase(IdempotentCreate):
    response_id: str | None = None
    project_id: str | None = None
    workstream_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FileArtifactCreate(ArtifactCreateBase):
    kind: Literal["file"]
    payload: FileArtifact


class CanvasArtifactCreate(ArtifactCreateBase):
    kind: Literal["canvas"]
    payload: CanvasArtifact


class PreviewArtifactCreate(ArtifactCreateBase):
    kind: Literal["preview"]
    payload: PreviewArtifact


class AutomationArtifactCreate(ArtifactCreateBase):
    kind: Literal["automation"]
    payload: AutomationArtifact


ArtifactCreate = Annotated[
    FileArtifactCreate | CanvasArtifactCreate | PreviewArtifactCreate | AutomationArtifactCreate,
    Field(discriminator="kind"),
]


class LearningCandidateCreate(IdempotentCreate):
    source_response_id: str | None = None
    source_trace_id: str | None = None
    capability: str | None = None
    artifact_hashes: list[str] = Field(default_factory=list)
    kind: Literal["episodic", "semantic", "procedural", "preference", "eval"]
    summary: str = Field(min_length=1, max_length=50_000)
    examples: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    consent: Literal["explicit", "contractual", "public-permitted", "denied", "unknown"]
    license: Literal["permitted", "restricted", "negative", "unknown"]
    retention_class: Literal["ephemeral", "project", "training-approved", "legal-hold"] = "project"
    quality_verdict: Literal["pending"] = "pending"
    credit_assignment: dict[str, Any] = Field(default_factory=dict)
    data_classification: Literal["public", "internal", "private"]
    source_uri: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_learning_contract(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        consent = normalized.get("consent")
        if isinstance(consent, bool):
            normalized["consent"] = "explicit" if consent else "denied"
        license_map = {
            "owned": "permitted",
            "permissive": "permitted",
            "public-domain": "permitted",
            "consented-private": "permitted",
            "prohibited": "negative",
            "incompatible": "negative",
        }
        normalized["license"] = license_map.get(normalized.get("license"), normalized.get("license"))
        normalized.setdefault("source_trace_id", normalized.get("source_response_id"))
        normalized.setdefault("capability", normalized.get("kind"))
        return normalized

    @model_validator(mode="after")
    def validate_canonical_learning_contract(self) -> "LearningCandidateCreate":
        if not self.source_response_id and not self.source_trace_id:
            raise ValueError("source_trace_id is required")
        if not self.source_trace_id:
            self.source_trace_id = self.source_response_id
        if not self.capability or not self.capability.strip():
            self.capability = self.kind
        for digest in self.artifact_hashes:
            if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
                raise ValueError("artifact_hashes must contain canonical sha256 digests")
        return self


class LearningQueueProcess(BaseModel):
    worker_id: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=10, ge=1, le=100)


class LearningPromotionTransition(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=300)
    to_status: Literal[
        "training", "evaluating", "canary-1", "canary-10", "canary-50",
        "production", "rejected", "rolled-back",
    ]
    reason: str | None = Field(default=None, max_length=2_000)
    evidence: dict[str, Any] = Field(default_factory=dict)


class LogicalActorEnsure(BaseModel):
    count: int = Field(default=DEFAULT_LOGICAL_ACTORS, ge=1, le=100_000)
    actor_class: str = "general"


class EventCreate(IdempotentCreate):
    event_type: str = Field(min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)


class PlanCreate(IdempotentCreate):
    project_id: str
    workstream_id: str | None = None
    goal: str = Field(min_length=1, max_length=50_000)
    resource_slot_limit: int = Field(default=16, ge=1, le=256)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanTaskCreate(IdempotentCreate):
    title: str = Field(min_length=1, max_length=500)
    kind: str = Field(default="generic", max_length=200)
    dependencies: list[str] = Field(default_factory=list)
    resource_slots: int = Field(default=1, ge=1, le=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskTransition(BaseModel):
    to_state: Literal["pending", "ready", "queued", "leased", "running", "blocked", "completed", "failed", "cancelled"]
    idempotency_key: str = Field(min_length=1, max_length=300)
    reason: str | None = Field(default=None, max_length=2_000)
    attempt_id: str | None = Field(default=None, min_length=8, max_length=200)
    lease_owner: str | None = Field(default=None, min_length=1, max_length=300)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    verifier: dict[str, Any] | None = None


class ExecutionStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self._lock, self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS execution_records (
                    record_type TEXT NOT NULL,
                    record_id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_execution_records_type_parent
                    ON execution_records(record_type, parent_id, created_at);
                CREATE TABLE IF NOT EXISTS logical_actors (
                    actor_id TEXT PRIMARY KEY,
                    actor_class TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_response_id TEXT,
                    capabilities TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS execution_idempotency (
                    scope TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(scope, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS execution_events (
                    event_id TEXT PRIMARY KEY,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(aggregate_type, aggregate_id, sequence),
                    UNIQUE(aggregate_type, aggregate_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS execution_outbox (
                    outbox_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE,
                    topic TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    published_at TEXT
                );
                """
            )

    @staticmethod
    def request_hash(payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _record_payload(record_type: str, record_id: str, status: str, payload: dict[str, Any], now: str) -> dict[str, Any]:
        item = {
            "schema_version": API_VERSION,
            "id": record_id,
            "object": record_type,
            "created_at": payload.get("created_at") or now,
            "updated_at": now,
            **payload,
        }
        item["status"] = status
        item["updated_at"] = now
        return item

    def _insert_event(
        self,
        conn: sqlite3.Connection,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        idempotency_key: str,
        payload: dict[str, Any],
        now: str,
    ) -> dict[str, Any]:
        existing = conn.execute(
            """SELECT * FROM execution_events
               WHERE aggregate_type = ? AND aggregate_id = ? AND idempotency_key = ?""",
            (aggregate_type, aggregate_id, idempotency_key),
        ).fetchone()
        if existing:
            existing_event = self._event_row(existing)
            if existing_event["event_type"] != event_type or existing_event["payload"] != sanitize_learning_value(payload):
                raise HTTPException(status_code=409, detail="event idempotency key reused with different payload")
            return existing_event
        sequence = int(conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM execution_events WHERE aggregate_type = ? AND aggregate_id = ?",
            (aggregate_type, aggregate_id),
        ).fetchone()[0])
        event_id = new_id("event")
        event = {
            "schema_version": API_VERSION,
            "id": event_id,
            "object": "event",
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "sequence": sequence,
            "event_type": event_type,
            "idempotency_key": idempotency_key,
            "payload": sanitize_learning_value(payload),
            "created_at": now,
        }
        encoded = json.dumps(event["payload"], ensure_ascii=False, sort_keys=True)
        conn.execute(
            """INSERT INTO execution_events
               (event_id, aggregate_type, aggregate_id, sequence, event_type, idempotency_key, payload, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, aggregate_type, aggregate_id, sequence, event_type, idempotency_key, encoded, now),
        )
        conn.execute(
            """INSERT INTO execution_outbox(outbox_id, event_id, topic, payload, status, created_at)
               VALUES (?, ?, ?, ?, 'pending', ?)""",
            (new_id("outbox"), event_id, f"{aggregate_type}.{event_type}", json.dumps(event, ensure_ascii=False, sort_keys=True), now),
        )
        return event

    @staticmethod
    def _event_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "schema_version": API_VERSION,
            "id": row["event_id"],
            "object": "event",
            "aggregate_type": row["aggregate_type"],
            "aggregate_id": row["aggregate_id"],
            "sequence": row["sequence"],
            "event_type": row["event_type"],
            "idempotency_key": row["idempotency_key"],
            "payload": json.loads(row["payload"]),
            "created_at": row["created_at"],
        }

    def create_idempotent(
        self,
        record_type: str,
        record_id: str,
        status: str,
        payload: dict[str, Any],
        idempotency_key: str,
        parent_id: str | None = None,
        scope: str | None = None,
    ) -> dict[str, Any]:
        scope = scope or record_type
        request_payload = {key: value for key, value in payload.items() if key != "created_at"}
        request_hash = self.request_hash(request_payload)
        now = utc_now()
        with self._lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT record_id, request_hash FROM execution_idempotency WHERE scope = ? AND idempotency_key = ?",
                (scope, idempotency_key),
            ).fetchone()
            if existing:
                if existing["request_hash"] != request_hash:
                    raise HTTPException(status_code=409, detail="idempotency key reused with different payload")
                row = conn.execute("SELECT payload FROM execution_records WHERE record_id = ?", (existing["record_id"],)).fetchone()
                return json.loads(row["payload"])
            item = self._record_payload(record_type, record_id, status, payload, now)
            conn.execute(
                """INSERT INTO execution_records(record_type, record_id, parent_id, status, created_at, updated_at, payload)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (record_type, record_id, parent_id, status, item["created_at"], now, json.dumps(item, ensure_ascii=False, sort_keys=True)),
            )
            conn.execute(
                "INSERT INTO execution_idempotency(scope, idempotency_key, record_id, request_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (scope, idempotency_key, record_id, request_hash, now),
            )
            self._insert_event(conn, record_type, record_id, f"{record_type}.created", f"create:{idempotency_key}", {"status": status}, now)
            return item

    def resolve_idempotent(self, scope: str, idempotency_key: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        request_hash = self.request_hash({key: value for key, value in payload.items() if key != "created_at"})
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT record_id, request_hash FROM execution_idempotency WHERE scope = ? AND idempotency_key = ?",
                (scope, idempotency_key),
            ).fetchone()
            if not existing:
                return None
            if existing["request_hash"] != request_hash:
                raise HTTPException(status_code=409, detail="idempotency key reused with different payload")
            row = conn.execute("SELECT payload FROM execution_records WHERE record_id = ?", (existing["record_id"],)).fetchone()
        return json.loads(row["payload"])

    def put(self, record_type: str, record_id: str, status: str, payload: dict[str, Any], parent_id: str | None = None) -> dict[str, Any]:
        now = utc_now()
        item = self._record_payload(record_type, record_id, status, payload, now)
        with self._lock, self.connect() as conn:
            conn.execute(
                """INSERT INTO execution_records(record_type, record_id, parent_id, status, created_at, updated_at, payload)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(record_id) DO UPDATE SET
                     parent_id=excluded.parent_id, status=excluded.status,
                     updated_at=excluded.updated_at, payload=excluded.payload""",
                (record_type, record_id, parent_id, status, item["created_at"], now, json.dumps(item, ensure_ascii=False, sort_keys=True)),
            )
        return item

    def transition_idempotent(
        self,
        record_type: str,
        record_id: str,
        *,
        to_status: str,
        allowed_from: set[str],
        event_type: str,
        idempotency_key: str,
        reason: str,
    ) -> dict[str, Any]:
        """Atomically persist a state change, event, and pending outbox item."""

        event_key = f"transition:{idempotency_key}"
        event_payload = sanitize_learning_value({"to_status": to_status, "reason": reason})
        with self._lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT payload FROM execution_records WHERE record_id = ? AND record_type = ?",
                (record_id, record_type),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"{record_type} not found")
            record = json.loads(row["payload"])
            existing_event = conn.execute(
                """SELECT * FROM execution_events
                   WHERE aggregate_type = ? AND aggregate_id = ? AND idempotency_key = ?""",
                (record_type, record_id, event_key),
            ).fetchone()
            if existing_event:
                existing = self._event_row(existing_event)
                if existing["event_type"] != event_type or existing["payload"] != event_payload:
                    raise HTTPException(status_code=409, detail="transition idempotency key reused with different payload")
                return record
            current = str(record.get("status", ""))
            if current == to_status:
                return record
            if current not in allowed_from:
                raise HTTPException(status_code=409, detail=f"illegal {record_type} transition: {current} -> {to_status}")
            now = utc_now()
            record["status"] = to_status
            record["updated_at"] = now
            record["transition_reason"] = sanitize_learning_value(reason)
            conn.execute(
                "UPDATE execution_records SET status = ?, updated_at = ?, payload = ? WHERE record_id = ?",
                (to_status, now, json.dumps(record, ensure_ascii=False, sort_keys=True), record_id),
            )
            self._insert_event(
                conn,
                record_type,
                record_id,
                event_type,
                event_key,
                event_payload,
                now,
            )
            return record

    def get(self, record_id: str, record_type: str | None = None) -> dict[str, Any] | None:
        query = "SELECT payload FROM execution_records WHERE record_id = ?"
        params: list[Any] = [record_id]
        if record_type:
            query += " AND record_type = ?"
            params.append(record_type)
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
        return json.loads(row["payload"]) if row else None

    def list(self, record_type: str, parent_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT payload FROM execution_records WHERE record_type = ?"
        params: list[Any] = [record_type]
        if parent_id is not None:
            query += " AND parent_id = ?"
            params.append(parent_id)
        query += " ORDER BY created_at, record_id"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def find_latest(self, record_type: str, *, parent_id: str | None = None, statuses: set[str] | None = None, binding: str | None = None) -> dict[str, Any] | None:
        items = self.list(record_type, parent_id)
        candidates = [
            item for item in items
            if (not statuses or item.get("status") in statuses)
            and (binding is None or item.get("binding") == binding)
        ]
        return max(candidates, key=lambda item: (item.get("updated_at", ""), item["id"])) if candidates else None

    def append_event(self, aggregate_type: str, aggregate_id: str, body: EventCreate) -> dict[str, Any]:
        with self._lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return self._insert_event(
                conn, aggregate_type, aggregate_id, body.event_type,
                body.idempotency_key, body.payload, utc_now(),
            )

    def list_events(self, aggregate_type: str, aggregate_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT * FROM execution_events WHERE aggregate_type = ? AND aggregate_id = ?
                   ORDER BY sequence""",
                (aggregate_type, aggregate_id),
            ).fetchall()
        return [self._event_row(row) for row in rows]

    def find_event(self, aggregate_type: str, aggregate_id: str, idempotency_key: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT * FROM execution_events
                   WHERE aggregate_type = ? AND aggregate_id = ? AND idempotency_key = ?""",
                (aggregate_type, aggregate_id, idempotency_key),
            ).fetchone()
        return self._event_row(row) if row else None

    @staticmethod
    def _validated_completion_evidence(
        task: dict[str, Any], body: TaskTransition,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not body.evidence or not isinstance(body.verifier, dict):
            raise HTTPException(status_code=409, detail="task completion requires evidence and verifier")
        verifier = sanitize_learning_value(body.verifier)
        if verifier.get("verdict") != "passed":
            raise HTTPException(status_code=409, detail="task completion verifier did not pass")
        if verifier.get("attempt_id") not in {None, body.attempt_id}:
            raise HTTPException(status_code=409, detail="task completion verifier attempt mismatch")
        evidence: list[dict[str, Any]] = []
        content_bound = False
        for raw_item in body.evidence:
            if not isinstance(raw_item, dict):
                raise HTTPException(status_code=422, detail="task evidence must be objects")
            item = sanitize_learning_value(raw_item)
            digest = str(item.get("sha256") or item.get("output_sha256") or "").lower()
            if re.fullmatch(r"[0-9a-f]{64}", digest):
                content_bound = True
            evidence.append(item)
        if not content_bound:
            raise HTTPException(status_code=409, detail="task completion evidence is not content-bound")
        verifier_digest = str(verifier.get("evidence_sha256") or "").lower()
        if verifier_digest and not re.fullmatch(r"[0-9a-f]{64}", verifier_digest):
            raise HTTPException(status_code=422, detail="task verifier evidence digest is invalid")
        return evidence, verifier

    def transition_task(self, task_id: str, body: TaskTransition) -> dict[str, Any]:
        with self._lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT parent_id, payload FROM execution_records WHERE record_id = ? AND record_type = 'task'",
                (task_id,),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="task not found")
            task = json.loads(row["payload"])
            current = str(task["status"])
            if current == body.to_state:
                if body.attempt_id and body.attempt_id != task.get("attempt_id"):
                    raise HTTPException(status_code=409, detail="task transition attempt mismatch")
                if body.lease_owner and body.lease_owner != task.get("lease_owner"):
                    raise HTTPException(status_code=409, detail="task transition lease owner mismatch")
                return task
            if body.to_state not in TASK_TRANSITIONS.get(current, set()):
                raise HTTPException(status_code=409, detail=f"illegal task transition: {current} -> {body.to_state}")
            active_attempt_states = {"leased", "running", "completed"}
            if body.to_state in active_attempt_states:
                if not body.attempt_id or not body.lease_owner:
                    raise HTTPException(status_code=409, detail="task transition requires fenced attempt and lease owner")
                if current == "queued":
                    if body.to_state != "leased":
                        raise HTTPException(status_code=409, detail="task must be leased before execution")
                    task["attempt_id"] = body.attempt_id
                    task["lease_owner"] = body.lease_owner
                elif (
                    task.get("attempt_id") != body.attempt_id
                    or task.get("lease_owner") != body.lease_owner
                ):
                    raise HTTPException(status_code=409, detail="task transition rejected by lease fence")
            elif current in {"leased", "running"} and body.to_state in {"queued", "failed", "blocked", "cancelled"}:
                if (
                    not body.attempt_id
                    or not body.lease_owner
                    or task.get("attempt_id") != body.attempt_id
                    or task.get("lease_owner") != body.lease_owner
                ):
                    raise HTTPException(status_code=409, detail="task transition rejected by lease fence")

            evidence: list[dict[str, Any]] = []
            verifier: dict[str, Any] | None = None
            if body.to_state == "completed":
                evidence, verifier = self._validated_completion_evidence(task, body)
            now = utc_now()
            task["status"] = body.to_state
            task["updated_at"] = now
            task["transition_reason"] = sanitize_learning_value(body.reason)
            if body.to_state == "completed":
                task["evidence"] = evidence
                task["verifier"] = verifier
                task["completed_attempt_id"] = body.attempt_id
            elif body.to_state == "queued" and current in {"leased", "failed", "blocked"}:
                task["attempt_id"] = None
                task["lease_owner"] = None
                task["evidence"] = []
                task["verifier"] = None
            conn.execute(
                "UPDATE execution_records SET status = ?, updated_at = ?, payload = ? WHERE record_id = ?",
                (body.to_state, now, json.dumps(task, ensure_ascii=False, sort_keys=True), task_id),
            )
            self._insert_event(
                conn, "task", task_id, "task.transitioned", body.idempotency_key,
                {
                    "from_state": current,
                    "to_state": body.to_state,
                    "reason": sanitize_learning_value(body.reason),
                    "attempt_id": body.attempt_id,
                    "lease_owner": body.lease_owner,
                    "evidence_count": len(evidence),
                    "verifier_verdict": verifier.get("verdict") if verifier else None,
                },
                now,
            )
            return task

    def ensure_logical_actors(self, count: int = DEFAULT_LOGICAL_ACTORS, actor_class: str = "general") -> int:
        now = utc_now()
        with self._lock, self.connect() as conn:
            existing = int(conn.execute("SELECT COUNT(*) FROM logical_actors").fetchone()[0])
            rows = [
                (
                    f"logical-actor-{index:06d}", actor_class, "idle", None,
                    json.dumps(["task.execute"], separators=(",", ":")), now, now,
                )
                for index in range(existing + 1, count + 1)
            ]
            if rows:
                conn.executemany(
                    "INSERT OR IGNORE INTO logical_actors VALUES (?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
            return int(conn.execute("SELECT COUNT(*) FROM logical_actors").fetchone()[0])

    def actor_summary(self) -> dict[str, Any]:
        with self.connect() as conn:
            total = int(conn.execute("SELECT COUNT(*) FROM logical_actors").fetchone()[0])
            state_rows = conn.execute("SELECT status, COUNT(*) AS count FROM logical_actors GROUP BY status").fetchall()
        return {
            "logical_actors": total,
            "actors_by_status": {row["status"]: row["count"] for row in state_rows},
            "os_processes_spawned": 0,
            "representation": "durable_state_records",
        }


_store: ExecutionStore | None = None
_learning_boundary: FormulaLMBoundary | None = None


def configure_execution_store(path: str | Path) -> ExecutionStore:
    global _store, _learning_boundary
    _store = ExecutionStore(path)
    _learning_boundary = FormulaLMBoundary(path)
    return _store


def get_store() -> ExecutionStore:
    global _store
    if _store is None:
        path = os.environ.get("KOLIBRI_EXECUTION_DB_PATH", str(DB_PATH))
        _store = ExecutionStore(path)
    return _store


def get_learning_boundary() -> FormulaLMBoundary:
    global _learning_boundary
    store = get_store()
    if _learning_boundary is None or _learning_boundary.db_path != store.db_path:
        _learning_boundary = FormulaLMBoundary(store.db_path)
    return _learning_boundary


def learning_http_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, FormulaLMNotFoundError):
        return HTTPException(status_code=404, detail=exc.code)
    if isinstance(exc, FormulaLMConflictError):
        return HTTPException(status_code=409, detail=exc.code)
    if isinstance(exc, FormulaLMPolicyError):
        return HTTPException(status_code=422, detail=exc.code)
    return HTTPException(status_code=500, detail="learning_boundary_internal_error")


def require_record(record_id: str, record_type: str | None = None) -> dict[str, Any]:
    record = get_store().get(record_id, record_type)
    if record is None:
        raise HTTPException(status_code=404, detail=f"{record_type or 'record'} not found")
    return record


def create_body(body: IdempotentCreate) -> dict[str, Any]:
    return body.model_dump(mode="json", exclude={"idempotency_key"})


def runtime_create_body(body: BaseModel) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = body.model_dump(mode="json", exclude={"idempotency_key"})
    sanitized, report = sanitize_learning_payload(raw)
    return sanitized, report


def record_parent(payload: dict[str, Any]) -> str | None:
    return payload.get("workstream_id") or payload.get("project_id")


def list_runtime_records(
    record_type: str,
    *,
    project_id: str | None = None,
    workstream_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    data = get_store().list(record_type)
    if project_id is not None:
        data = [item for item in data if item.get("project_id") == project_id]
    if workstream_id is not None:
        data = [item for item in data if item.get("workstream_id") == workstream_id]
    if status is not None:
        data = [item for item in data if item.get("status") == status]
    return {"object": "list", "data": data, "schema_version": API_VERSION}


def runtime_status(record: dict[str, Any]) -> dict[str, Any]:
    status = str(record.get("status", "unknown"))
    return {
        "schema_version": API_VERSION,
        "id": record["id"],
        "object": f"{record['object']}.status",
        "status": status,
        "terminal": status in {"cancelled", "failed", "expired", "calculated"},
        "runtime": record.get("runtime"),
        "updated_at": record["updated_at"],
    }


def resolve_artifact_link(link: ArtifactLinkInput, *, project_id: str | None = None) -> dict[str, Any]:
    artifact = require_record(link.artifact_id, "artifact")
    artifact_project_id = artifact.get("project_id")
    if project_id and artifact_project_id and artifact_project_id != project_id:
        raise HTTPException(status_code=409, detail="artifact belongs to another project")
    actual_kind = str(artifact.get("kind") or "unknown")
    if link.expected_kind and actual_kind != link.expected_kind:
        raise HTTPException(
            status_code=409,
            detail={
                "artifact_kind_mismatch": {
                    "artifact_id": artifact["id"],
                    "expected": link.expected_kind,
                    "actual": actual_kind,
                }
            },
        )
    artifact_payload = artifact.get("payload") if isinstance(artifact.get("payload"), dict) else {}
    return {
        "schema_version": "kolibri.artifact-link.v1",
        "artifact_id": artifact["id"],
        "relation": link.relation,
        "kind": actual_kind,
        "media_type": artifact_payload.get("media_type"),
        "state": artifact.get("status"),
        "immutable_reference": True,
    }


def validate_runtime_scope(project_id: str | None, workstream_id: str | None) -> None:
    require_project_workstream(project_id, workstream_id)


def cancel_runtime_record(record_type: str, record_id: str, body: RuntimeCancel) -> dict[str, Any]:
    return get_store().transition_idempotent(
        record_type,
        record_id,
        to_status="cancelled",
        allowed_from={"queued", "degraded", "pending"},
        event_type=f"{record_type}.cancelled",
        idempotency_key=body.idempotency_key,
        reason=body.reason,
    )


def require_project_workstream(project_id: str | None, workstream_id: str | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    project = require_record(project_id, "project") if project_id else None
    workstream = require_record(workstream_id, "workstream") if workstream_id else None
    if workstream:
        bound_project_id = workstream.get("project_id")
        if project_id and bound_project_id != project_id:
            raise HTTPException(status_code=409, detail="workstream does not belong to project")
        if not project:
            project = require_record(bound_project_id, "project")
    return project, workstream


router = APIRouter(
    tags=["Kolibri Execution V1"],
    dependencies=[Depends(require_execution_auth)],
)


@router.post("/v1/projects", status_code=201)
def create_project(body: ProjectCreate) -> dict[str, Any]:
    project_id = new_id("project")
    return get_store().create_idempotent(
        "project", project_id, "active", create_body(body), body.idempotency_key,
        scope="projects",
    )


@router.get("/v1/projects")
def list_projects() -> dict[str, Any]:
    return {"object": "list", "data": get_store().list("project"), "schema_version": API_VERSION}


@router.get("/v1/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    return require_record(project_id, "project")


@router.post("/v1/projects/{project_id}/workstreams", status_code=201)
def create_workstream(project_id: str, body: WorkstreamCreate) -> dict[str, Any]:
    require_record(project_id, "project")
    workstream_id = new_id("workstream")
    payload = {**create_body(body), "project_id": project_id}
    return get_store().create_idempotent(
        "workstream", workstream_id, body.status, payload, body.idempotency_key,
        parent_id=project_id, scope=f"project:{project_id}:workstreams",
    )


@router.get("/v1/projects/{project_id}/workstreams")
def list_workstreams(project_id: str) -> dict[str, Any]:
    require_record(project_id, "project")
    return {"object": "list", "data": get_store().list("workstream", project_id), "schema_version": API_VERSION}


@router.get("/v1/workstreams/{workstream_id}")
def get_workstream(workstream_id: str) -> dict[str, Any]:
    return require_record(workstream_id, "workstream")


@router.post("/v1/workstreams/{workstream_id}/backlog", status_code=201)
def create_backlog_item(workstream_id: str, body: BacklogItemCreate) -> dict[str, Any]:
    workstream = require_record(workstream_id, "workstream")
    item_id = new_id("backlog")
    payload = {**create_body(body), "project_id": workstream["project_id"], "workstream_id": workstream_id}
    return get_store().create_idempotent(
        "backlog_item", item_id, body.state, payload, body.idempotency_key,
        parent_id=workstream_id, scope=f"workstream:{workstream_id}:backlog",
    )


@router.get("/v1/workstreams/{workstream_id}/backlog")
def list_backlog(workstream_id: str) -> dict[str, Any]:
    require_record(workstream_id, "workstream")
    return {"object": "list", "data": get_store().list("backlog_item", workstream_id), "schema_version": API_VERSION}


@router.get("/v1/backlog/{item_id}")
def get_backlog_item(item_id: str) -> dict[str, Any]:
    return require_record(item_id, "backlog_item")


@router.post("/v1/workstreams/{workstream_id}/checkpoints", status_code=201)
def create_checkpoint(workstream_id: str, body: CheckpointCreate) -> dict[str, Any]:
    workstream = require_record(workstream_id, "workstream")
    checkpoint_id = new_id("checkpoint")
    payload = {**create_body(body), "project_id": workstream["project_id"], "workstream_id": workstream_id}
    return get_store().create_idempotent(
        "checkpoint", checkpoint_id, "recorded", payload, body.idempotency_key,
        parent_id=workstream_id, scope=f"workstream:{workstream_id}:checkpoints",
    )


@router.get("/v1/workstreams/{workstream_id}/checkpoints")
def list_checkpoints(workstream_id: str) -> dict[str, Any]:
    require_record(workstream_id, "workstream")
    return {"object": "list", "data": get_store().list("checkpoint", workstream_id), "schema_version": API_VERSION}


@router.get("/v1/checkpoints/{checkpoint_id}")
def get_checkpoint(checkpoint_id: str) -> dict[str, Any]:
    return require_record(checkpoint_id, "checkpoint")


def continuity_packet(project_id: str, workstream_id: str | None = None, checkpoint_id: str | None = None) -> dict[str, Any]:
    project = require_record(project_id, "project")
    workstreams = get_store().list("workstream", project_id)
    if workstream_id:
        workstreams = [item for item in workstreams if item["id"] == workstream_id]
        if not workstreams:
            raise HTTPException(status_code=404, detail="workstream not found in project")
    streams = []
    for stream in workstreams:
        checkpoints = get_store().list("checkpoint", stream["id"])
        if checkpoint_id:
            checkpoints = [item for item in checkpoints if item["id"] == checkpoint_id]
            if not checkpoints:
                raise HTTPException(status_code=404, detail="checkpoint not found in workstream")
        streams.append({
            **stream,
            "backlog": get_store().list("backlog_item", stream["id"]),
            "checkpoints": checkpoints,
        })
    return {
        "schema_version": API_VERSION,
        "object": "resume_packet",
        "project": project,
        "workstreams": streams,
        "resume_at": utc_now(),
    }


@router.get("/v1/projects/{project_id}/continuity")
def get_continuity(project_id: str) -> dict[str, Any]:
    return continuity_packet(project_id)


@router.post("/v1/resume")
def resume(body: ResumeRequest) -> dict[str, Any]:
    store = get_store()
    project_created = False
    workstream_created = False
    project = store.get(body.project_id, "project") if body.project_id else None
    if body.project_id and not project:
        raise HTTPException(status_code=404, detail="project not found")
    if not project:
        project = store.find_latest("project", statuses={"active"}, binding=body.binding)
    if not project:
        if not body.create_new:
            raise HTTPException(status_code=404, detail="no resumable project; set create_new=true to create one")
        if not body.idempotency_key:
            raise HTTPException(status_code=422, detail="idempotency_key is required when create_new=true")
        project = store.create_idempotent(
            "project", new_id("project"), "active",
            {"name": body.project_name, "objective": "", "binding": body.binding, "metadata": {}},
            body.idempotency_key, scope="resume:project",
        )
        project_created = True

    workstream = store.get(body.workstream_id, "workstream") if body.workstream_id else None
    if workstream and workstream.get("project_id") != project["id"]:
        raise HTTPException(status_code=409, detail="workstream does not belong to selected project")
    if body.workstream_id and not workstream:
        raise HTTPException(status_code=404, detail="workstream not found")
    if not workstream:
        workstream = store.find_latest(
            "workstream", parent_id=project["id"], statuses=ACTIVE_WORKSTREAM_STATUSES,
            binding=body.binding,
        )
    if not workstream and body.create_new:
        assert body.idempotency_key
        workstream = store.create_idempotent(
            "workstream", new_id("workstream"), "active",
            {"name": body.workstream_name, "objective": "", "binding": body.binding, "metadata": {}, "project_id": project["id"]},
            body.idempotency_key, parent_id=project["id"], scope=f"resume:{project['id']}:workstream",
        )
        workstream_created = True
    if not workstream:
        raise HTTPException(status_code=404, detail="no active workstream; set create_new=true to create one")

    checkpoint = require_record(body.checkpoint_id, "checkpoint") if body.checkpoint_id else store.find_latest("checkpoint", parent_id=workstream["id"])
    if checkpoint and checkpoint.get("workstream_id") != workstream["id"]:
        raise HTTPException(status_code=409, detail="checkpoint does not belong to selected workstream")
    backlog = store.find_latest("backlog_item", parent_id=workstream["id"], statuses=ACTIVE_BACKLOG_STATES)
    packet = continuity_packet(project["id"], workstream["id"], checkpoint["id"] if checkpoint else None)
    packet["selected"] = {"project": project, "workstream": workstream, "checkpoint": checkpoint, "backlog_item": backlog}
    packet["created_new"] = {"project": project_created, "workstream": workstream_created}
    return packet


MODEL_CATALOG = [
    {
        "id": "kolibri", "object": "model", "created": 0, "owned_by": "kolibri-ai-os",
    },
]


@router.get("/v1/models")
def list_models() -> dict[str, Any]:
    return {"object": "list", "data": MODEL_CATALOG, "schema_version": API_VERSION}


@router.get("/v1/models/{model_id}")
def get_model(model_id: str) -> dict[str, Any]:
    model = next((item for item in MODEL_CATALOG if item["id"] == model_id), None)
    if model is None:
        raise HTTPException(status_code=404, detail="model not found")
    return {**model, "schema_version": API_VERSION}


def response_provider_route(body: ResponseCreate) -> dict[str, Any]:
    del body
    return {
        "routing_control": "server_policy_only",
        "attempts": [],
        "fallback_policy": "next_eligible_provider_after_classified_failure",
    }


@router.get("/v1/capabilities")
def list_capabilities(refresh: bool = False) -> dict[str, Any]:
    return get_capability_gateway().envelope(refresh=refresh)


@router.get("/v1/tools")
def list_tools(refresh: bool = False) -> dict[str, Any]:
    return get_capability_gateway().envelope(tools_only=True, refresh=refresh)


@router.post("/v1/responses", status_code=201)
def create_response(body: ResponseCreate, request: Request) -> dict[str, Any]:
    principal = require_execution_auth(request)
    require_project_workstream(body.project_id, body.workstream_id)
    if body.previous_response_id:
        previous = require_record(body.previous_response_id, "response")
        if body.project_id and previous.get("project_id") != body.project_id:
            raise HTTPException(status_code=409, detail="previous response belongs to another project")
        if body.workstream_id and previous.get("workstream_id") != body.workstream_id:
            raise HTTPException(status_code=409, detail="previous response belongs to another workstream")
    idempotency_key = (
        body.idempotency_key
        or request.headers.get("Idempotency-Key")
        or new_id("request")
    )
    if len(idempotency_key) > 300 or not idempotency_key.strip():
        raise HTTPException(status_code=422, detail="invalid idempotency key")
    capability_gateway = get_capability_gateway()
    try:
        requested_tools = capability_gateway.validate_requested_tools(body.tools)
    except CapabilityRequestError as exc:
        raise HTTPException(status_code=422, detail=exc.public_detail()) from exc
    public_tool_bindings = capability_gateway.public_bindings(requested_tools)
    provider_instructions = body.instructions
    vertical_calculation: dict[str, Any] | None = None
    if body.task is not None:
        vertical_instructions, vertical_calculation = prepare_vertical_task(body.task)
        provider_instructions = "\n\n".join(
            part for part in (body.instructions, vertical_instructions) if part
        )
    planned_skills = capability_gateway.plan_skills({
        "input": body.input, "instructions": provider_instructions,
    })
    public_skill_plan = capability_gateway.public_bindings(planned_skills)
    response_id = new_id("resp")
    payload = {
        "model": "kolibri",
        "input": body.input,
        "instructions": body.instructions,
        "created_at": int(time.time()),
        "incomplete_details": None,
        "max_output_tokens": None,
        "parallel_tool_calls": True,
        "previous_response_id": body.previous_response_id,
        "reasoning": {"effort": None, "summary": None},
        "store": True,
        "text": {"format": {"type": "text"}},
        "tool_choice": "auto",
        "usage": None,
        "execution_mode": body.execution_mode,
        "tools": public_tool_bindings,
        "metadata": sanitize_learning_value(body.metadata),
        "project_id": body.project_id,
        "workstream_id": body.workstream_id,
        "output": [],
        "technical": {
            "provider_routing": response_provider_route(body),
            "capability_bindings": public_tool_bindings,
            "skill_plan": public_skill_plan,
            "learning_policy": sanitize_learning_value(body.learning.model_dump(mode="json")),
        },
        "error": None,
    }
    queued = get_store().create_idempotent(
        "response", response_id, "queued", payload, idempotency_key,
        parent_id=body.workstream_id or body.project_id, scope="responses",
    )
    if queued["id"] != response_id:
        return queued
    get_store().append_event("response", response_id, EventCreate(
        idempotency_key=f"gateway-start:{idempotency_key}",
        event_type="response.provider_gateway_started",
        payload={"model": "kolibri"},
    ))
    tool_execution = ResponseToolExecution(
        provider_tools=requested_tools,
        provider_instructions=provider_instructions,
        tool_calls=[], evidence=[], citations=[], attempts=[], formulalm_taps=[],
    )
    tool_gateway_error_code: str | None = None
    tool_gateway_failure_attempts: list[dict[str, Any]] = []
    try:
        tool_execution = execute_response_tools(
            input_value=body.input,
            instructions=provider_instructions,
            response_id=response_id,
            principal=principal,
            requested_tools=requested_tools,
            raw_tools=body.tools,
            project_id=body.project_id,
            workstream_id=body.workstream_id,
        )
        if tool_execution.tool_calls:
            get_store().append_event("response", response_id, EventCreate(
                idempotency_key=f"tool-gateway:{idempotency_key}",
                event_type="response.tool_gateway_completed",
                payload={
                    "tool_ids": sorted(str(item.get("capability_id") or "") for item in tool_execution.tool_calls),
                    "citation_count": len(tool_execution.citations),
                    "attempts": tool_execution.attempts,
                },
            ))
        gateway = get_provider_gateway()
        optional_gateway_args: dict[str, Any] = {
            "requested_tools": tool_execution.provider_tools,
            "planned_skills": planned_skills,
            "execution_mode": body.execution_mode,
        }
        while True:
            try:
                gateway_result = gateway.generate(
                    body.input, tool_execution.provider_instructions, response_id,
                    **optional_gateway_args,
                )
                break
            except TypeError as exc:
                match = re.search(
                    r"got an unexpected keyword argument ['\"]"
                    r"(requested_tools|planned_skills|execution_mode)['\"]$",
                    str(exc),
                )
                unsupported = match.group(1) if match else None
                if unsupported not in optional_gateway_args:
                    raise
                # Never silently discard an explicitly requested tool merely
                # because a transitional gateway has an obsolete signature.
                if unsupported == "requested_tools" and tool_execution.provider_tools:
                    raise
                optional_gateway_args.pop(unsupported)
        technical = dict(gateway_result.technical)
        status = str(gateway_result.status)
        text = str(gateway_result.text or "")
    except WebSearchError as exc:
        tool_gateway_error_code = exc.code
        attempts = exc.attempts if isinstance(exc, WebSearchUnavailable) else []
        tool_gateway_failure_attempts = attempts
        technical = {
            "attempts": [], "evidence": [], "error_type": exc.code,
            "tool_gateway": {"status": "failed", "error_type": exc.code, "attempts": attempts},
        }
        get_store().append_event("response", response_id, EventCreate(
            idempotency_key=f"tool-gateway-failed:{idempotency_key}",
            event_type="response.tool_gateway_failed",
            payload={"tool_id": "tool:web_search", "error_type": exc.code, "attempts": attempts},
        ))
        status = "failed"
        text = ""
    except Exception:
        technical = {"attempts": [], "evidence": [], "error_type": "provider_gateway_internal_error"}
        status = "failed"
        text = ""
    evidence = technical.get("evidence") if isinstance(technical.get("evidence"), list) else []
    provider_evidence = next((
        item for item in evidence
        if isinstance(item, dict) and item.get("type") == "provider_execution"
    ), None)
    provider_tool_calls = technical.get("tool_calls") if isinstance(technical.get("tool_calls"), list) else []
    tool_calls = [*tool_execution.tool_calls, *provider_tool_calls]
    verifier_evidence = deterministic_verifier_evidence(
        text, provider_evidence, requested_tools, tool_calls,
    )
    technical["verifier_evidence"] = verifier_evidence
    technical["tool_calls"] = tool_calls
    technical["tool_gateway"] = {
        "status": "completed" if tool_execution.tool_calls else ("failed" if tool_gateway_error_code else "not_requested"),
        "attempts": tool_execution.attempts or tool_gateway_failure_attempts,
        "citation_count": len(tool_execution.citations),
        "formulalm_taps": tool_execution.formulalm_taps,
        **({"error_type": tool_gateway_error_code} if tool_gateway_error_code else {}),
    }
    technical["evidence"] = (
        ([provider_evidence] if provider_evidence else [])
        + tool_execution.evidence
        + [verifier_evidence]
    )
    technical["capability_bindings"] = public_tool_bindings
    technical, technical_sanitization = sanitize_learning_payload(technical)
    technical["sanitization_report"] = technical_sanitization
    evidence = technical["evidence"]
    if (
        status == "completed" and text and provider_evidence
        and verifier_evidence.get("verdict") == "passed"
    ):
        queued["output"] = [{
            "id": new_id("msg"),
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        }]
        queued["output_text"] = text
        queued["citations"] = tool_execution.citations
        queued["error"] = None
        final_status = "completed"
    else:
        queued["output"] = []
        error_code = tool_gateway_error_code or (
            "tool_verification_failed"
            if requested_tools and verifier_evidence.get("verdict") != "passed"
            else "provider_unavailable"
        )
        queued["error"] = {"code": error_code, "message": "Kolibri could not produce a verified response"}
        queued["citations"] = []
        final_status = "failed"
    if body.task is not None:
        provider_result = {
            "response": text if final_status == "completed" else "",
            "model": "kolibri",
            "technical": {"provider_routing": technical},
        }
        queued["task"] = (
            build_vertical_result(body.task, provider_result, vertical_calculation)
            if final_status == "completed"
            else failed_vertical_result(body.task, tool_gateway_error_code or "provider_unavailable")
        )
    _, tap_report = sanitize_learning_payload({"input": body.input, "instructions": body.instructions})
    tap_hash = hashlib.sha256(json.dumps(
        sanitize_learning_value({"input": body.input, "instructions": body.instructions}),
        ensure_ascii=False, sort_keys=True,
    ).encode("utf-8")).hexdigest()
    learning_policy = body.learning.model_dump(mode="json")
    learning_artifact_hashes: list[str] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        digest = str(item.get("output_sha256") or item.get("sha256") or "").lower()
        if re.fullmatch(r"[a-f0-9]{64}", digest):
            learning_artifact_hashes.append(f"sha256:{digest}")
    learning_trace = {
        "request": {
            "input": body.input,
            "instructions": body.instructions,
            "tools": public_tool_bindings,
        },
        "response": {
            "status": final_status,
            "output_text": text if final_status == "completed" else "",
        },
        "decisions": {
            "attempts": technical.get("attempts", []),
            "selected_provider": technical.get("selected_provider"),
            "fallback_used": technical.get("fallback_used"),
            "tool_gateway": {
                "attempts": tool_execution.attempts or tool_gateway_failure_attempts,
                "formulalm_taps": tool_execution.formulalm_taps,
            },
        },
        "verifier": verifier_evidence,
    }
    learning_quality = {
        "response_status": final_status,
        "quality_verdict": "passed" if final_status == "completed" else "failed",
        "verifier_verdict": verifier_evidence.get("verdict"),
        "credit_assignment": {
            "provider_execution": 1.0 if provider_evidence and final_status == "completed" else 0.0,
            "web_search_tool": 1.0 if tool_execution.tool_calls and final_status == "completed" else 0.0,
            "verifier": 1.0 if verifier_evidence.get("verdict") == "passed" else 0.0,
        },
    }
    try:
        learning_intake = get_learning_boundary().enqueue_trace(
            idempotency_key=f"trace:{idempotency_key}",
            source_trace_id=response_id,
            source_response_id=response_id,
            capability=learning_policy["capability"],
            trace=learning_trace,
            provenance={
                "actor": "provider-gateway",
                "principal": "authn:" + hashlib.sha256(principal.encode("utf-8")).hexdigest()[:16],
                "policy_version": "kolibri.formulalm-policy.v1",
                "response_id": response_id,
                "source_uri": learning_policy.get("source_uri"),
            },
            policy=learning_policy,
            quality=learning_quality,
            artifact_hashes=learning_artifact_hashes,
        )
        learning_tap = {
            "status": learning_intake["status"],
            "intake_id": learning_intake["id"],
            "candidate_id": learning_intake.get("candidate_id"),
            "rejection_code": learning_intake.get("rejection_code"),
            "content_sha256": tap_hash,
            "sanitization_report": learning_intake["sanitization"],
            "async_queue": learning_intake["status"] == "queued",
            "auto_promote": False,
            "request_path_training": False,
            "production_weight_mutation": False,
        }
    except (FormulaLMPolicyError, FormulaLMConflictError) as exc:
        # Learning is isolated from inference. A normalized fail-closed tap is
        # durable in the response, while no training or candidate mutation runs.
        learning_tap = {
            "status": "rejected",
            "intake_id": None,
            "candidate_id": None,
            "rejection_code": exc.code,
            "content_sha256": tap_hash,
            "sanitization_report": tap_report,
            "async_queue": False,
            "auto_promote": False,
            "request_path_training": False,
            "production_weight_mutation": False,
        }
    except Exception:
        learning_tap = {
            "status": "unavailable",
            "intake_id": None,
            "candidate_id": None,
            "rejection_code": "learning_boundary_unavailable",
            "content_sha256": tap_hash,
            "sanitization_report": tap_report,
            "async_queue": False,
            "auto_promote": False,
            "request_path_training": False,
            "production_weight_mutation": False,
        }
    queued["technical"] = {
        "provider_routing": technical,
        "learning_tap": learning_tap,
    }
    updated = get_store().put(
        "response", response_id, final_status, queued,
        parent_id=body.workstream_id or body.project_id,
    )
    get_store().append_event("response", response_id, EventCreate(
        idempotency_key=f"gateway-finish:{idempotency_key}",
        event_type="response.completed" if final_status == "completed" else "response.failed",
        payload={
            "status": final_status,
            "evidence_count": len(evidence),
            "tool_call_count": len(tool_calls),
            "citation_count": len(tool_execution.citations),
        },
    ))
    return updated


@router.post("/v1/chat/completions")
def create_chat_completion(body: ChatCompletionCreate, request: Request):
    """OpenAI-compatible facade backed by the exact same Kolibri response path."""

    response = create_response(
        ResponseCreate(
            idempotency_key=body.idempotency_key,
            model="kolibri",
            input=body.messages,
            tools=body.tools,
            metadata={
                "compatibility_api": "chat.completions",
                "user": body.user,
                "temperature": body.temperature,
                "max_tokens": body.max_tokens,
            },
            learning=body.learning,
        ),
        request,
    )
    if response.get("status") != "completed" or not response.get("output_text"):
        raise HTTPException(
            status_code=503,
            detail={
                "type": "provider_unavailable",
                "message": "Kolibri could not produce a verified completion",
                "response_id": response.get("id"),
            },
        )
    completion_id = f"chatcmpl-{str(response['id']).removeprefix('resp_')}"
    created = int(time.time())
    text = str(response["output_text"])
    payload = {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": "kolibri",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": None,
    }
    if not body.stream:
        return payload

    def event_stream():
        chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": "kolibri",
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": text},
                "finish_reason": None,
            }],
        }
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        final_chunk = {
            **chunk,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/v1/responses")
def list_responses() -> dict[str, Any]:
    return {"object": "list", "data": get_store().list("response"), "schema_version": API_VERSION}


@router.get("/v1/responses/{response_id}")
def get_response(response_id: str) -> dict[str, Any]:
    return require_record(response_id, "response")


@router.post("/v1/responses/{response_id}/cancel")
def cancel_response(response_id: str) -> dict[str, Any]:
    response = require_record(response_id, "response")
    if response["status"] in TERMINAL_RESPONSE_STATUSES:
        return response
    response["cancelled_at"] = utc_now()
    updated = get_store().put("response", response_id, "cancelled", response, parent_id=response.get("workstream_id") or response.get("project_id"))
    get_store().append_event("response", response_id, EventCreate(
        idempotency_key=f"cancel:{response_id}", event_type="response.cancelled", payload={"status": "cancelled"},
    ))
    return updated


@router.post("/v1/responses/{response_id}/provider-attempts", status_code=201)
def append_provider_attempt(response_id: str, body: ProviderAttemptCreate) -> dict[str, Any]:
    response = require_record(response_id, "response")
    event_key = f"provider-attempt:{body.idempotency_key}"
    existing_event = get_store().find_event("response", response_id, event_key)
    if existing_event:
        requested = create_body(body)
        comparable = {key: existing_event["payload"].get(key) for key in requested}
        requested["reason"] = sanitize_learning_value(requested.get("reason"))
        if comparable != requested:
            raise HTTPException(status_code=409, detail="provider attempt idempotency key reused with different payload")
        return {
            "response_id": response_id,
            "provider_attempt": existing_event["payload"],
            "technical": response["technical"],
        }
    technical = response.setdefault("technical", {})
    routing = technical.setdefault("provider_routing", {})
    attempts = routing.setdefault("attempts", [])
    attempt = ProviderAttempt(
        attempt=len(attempts) + 1,
        **create_body(body),
    ).model_dump(mode="json")
    attempt["reason"] = sanitize_learning_value(attempt.get("reason"))
    attempts.append(attempt)
    if body.status in {"running", "succeeded"}:
        routing["selected_provider"] = body.provider
    routing["fallback_candidates"] = [
        provider for provider in routing.get("fallback_candidates", []) if provider != body.provider
    ]
    updated = get_store().put(
        "response", response_id, response["status"], response,
        parent_id=response.get("workstream_id") or response.get("project_id"),
    )
    get_store().append_event("response", response_id, EventCreate(
        idempotency_key=event_key,
        event_type="response.provider_attempted", payload=attempt,
    ))
    return {"response_id": response_id, "provider_attempt": attempt, "technical": updated["technical"]}


@router.post("/v1/responses/{response_id}/events", status_code=201)
def append_response_event(response_id: str, body: EventCreate) -> dict[str, Any]:
    require_record(response_id, "response")
    return get_store().append_event("response", response_id, body)


@router.get("/v1/responses/{response_id}/events")
def list_response_events(response_id: str, request: Request):
    require_record(response_id, "response")
    if "text/event-stream" not in request.headers.get("accept", ""):
        return {
            "object": "list",
            "data": get_store().list_events("response", response_id),
            "schema_version": API_VERSION,
        }

    try:
        after_sequence = max(0, int(request.headers.get("Last-Event-ID", "0")))
    except ValueError:
        after_sequence = 0
    max_seconds = min(60, max(1, int(os.environ.get("KOLIBRI_SSE_MAX_SECONDS", "30"))))

    def event_stream():
        cursor = after_sequence
        started = time.monotonic()
        last_heartbeat = started
        while time.monotonic() - started < max_seconds:
            events = get_store().list_events("response", response_id)
            fresh = [event for event in events if int(event.get("sequence", 0)) > cursor]
            for event in fresh:
                cursor = int(event["sequence"])
                payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                yield f"id: {cursor}\nevent: {event['event_type']}\ndata: {payload}\n\n"
            response = require_record(response_id, "response")
            if response.get("status") in TERMINAL_RESPONSE_STATUSES:
                yield f"event: done\ndata: {json.dumps({'response_id': response_id, 'status': response['status']})}\n\n"
                return
            now = time.monotonic()
            if now - last_heartbeat >= 10:
                yield ": keep-alive\n\n"
                last_heartbeat = now
            time.sleep(0.25)
        yield f"event: timeout\ndata: {json.dumps({'response_id': response_id, 'retry': True})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/v1/plans", status_code=201)
def create_plan(body: PlanCreate) -> dict[str, Any]:
    require_project_workstream(body.project_id, body.workstream_id)
    plan_id = new_id("plan")
    payload = {**create_body(body), "tasks": 0, "allocated_resource_slots": 0, "os_processes_spawned": 0}
    return get_store().create_idempotent(
        "plan", plan_id, "planned", payload, body.idempotency_key,
        parent_id=body.workstream_id or body.project_id, scope="plans",
    )


@router.get("/v1/plans")
def list_plans() -> dict[str, Any]:
    return {"object": "list", "data": get_store().list("plan"), "schema_version": API_VERSION}


@router.get("/v1/plans/{plan_id}")
def get_plan(plan_id: str) -> dict[str, Any]:
    plan = require_record(plan_id, "plan")
    tasks = get_store().list("task", plan_id)
    return {
        **plan,
        "tasks": tasks,
        "dag": {
            "nodes": [task["id"] for task in tasks],
            "edges": [
                {"source": dependency, "target": task["id"]}
                for task in tasks for dependency in task.get("dependencies", [])
            ],
        },
    }


@router.post("/v1/plans/{plan_id}/tasks", status_code=201)
def create_plan_task(plan_id: str, body: PlanTaskCreate) -> dict[str, Any]:
    plan = require_record(plan_id, "plan")
    tasks = get_store().list("task", plan_id)
    payload = {
        **create_body(body),
        "plan_id": plan_id,
        "project_id": plan["project_id"],
        "workstream_id": plan.get("workstream_id"),
        "execution_representation": "durable_state_record",
        "os_processes_spawned": 0,
        "attempt_id": None,
        "lease_owner": None,
        "evidence": [],
        "verifier": None,
    }
    existing = get_store().resolve_idempotent(f"plan:{plan_id}:tasks", body.idempotency_key, payload)
    if existing:
        return existing
    task_ids = {task["id"] for task in tasks}
    unknown = sorted(set(body.dependencies) - task_ids)
    if unknown:
        raise HTTPException(status_code=422, detail={"unknown_dependencies": unknown})
    allocated = sum(int(task.get("resource_slots", 0)) for task in tasks)
    if allocated + body.resource_slots > int(plan["resource_slot_limit"]):
        raise HTTPException(status_code=409, detail="plan resource_slot_limit exceeded")
    task_id = new_id("task")
    task = get_store().create_idempotent(
        "task", task_id, "pending", payload, body.idempotency_key,
        parent_id=plan_id, scope=f"plan:{plan_id}:tasks",
    )
    current_tasks = get_store().list("task", plan_id)
    plan["tasks"] = len(current_tasks)
    plan["allocated_resource_slots"] = sum(int(item.get("resource_slots", 0)) for item in current_tasks)
    get_store().put("plan", plan_id, plan["status"], plan, parent_id=plan.get("workstream_id") or plan.get("project_id"))
    return task


@router.get("/v1/plans/{plan_id}/tasks")
def list_plan_tasks(plan_id: str) -> dict[str, Any]:
    require_record(plan_id, "plan")
    return {"object": "list", "data": get_store().list("task", plan_id), "schema_version": API_VERSION}


@router.get("/v1/tasks/{task_id}")
def get_execution_task(task_id: str) -> dict[str, Any]:
    return require_record(task_id, "task")


@router.post("/v1/tasks/{task_id}/transition")
def transition_execution_task(task_id: str, body: TaskTransition) -> dict[str, Any]:
    return get_store().transition_task(task_id, body)


@router.post("/v1/tasks/{task_id}/events", status_code=201)
def append_task_event(task_id: str, body: EventCreate) -> dict[str, Any]:
    require_record(task_id, "task")
    return get_store().append_event("task", task_id, body)


@router.get("/v1/tasks/{task_id}/events")
def list_task_events(task_id: str) -> dict[str, Any]:
    require_record(task_id, "task")
    return {"object": "list", "data": get_store().list_events("task", task_id), "schema_version": API_VERSION}


@router.post("/v1/runtime/actors/ensure")
def ensure_actors(body: LogicalActorEnsure) -> dict[str, Any]:
    total = get_store().ensure_logical_actors(body.count, body.actor_class)
    return {"schema_version": API_VERSION, "status": "ready", "logical_actors": total}


@router.get("/v1/runtime/swarm")
@router.get("/v1/swarm/runtime/status")
def runtime_swarm_summary() -> dict[str, Any]:
    get_store().ensure_logical_actors(DEFAULT_LOGICAL_ACTORS)
    summary = get_store().actor_summary()
    responses = get_store().list("response")
    summary.update({
        "schema_version": API_VERSION,
        "object": "swarm_runtime_summary",
        "status": "active",
        "responses_by_status": {
            status: sum(1 for item in responses if item["status"] == status)
            for status in sorted({item["status"] for item in responses})
        },
    })
    return summary


@router.post("/v1/artifacts", status_code=201)
def create_artifact(body: ArtifactCreate) -> dict[str, Any]:
    if body.response_id:
        response = require_record(body.response_id, "response")
        if body.project_id and response.get("project_id") != body.project_id:
            raise HTTPException(status_code=409, detail="artifact project does not match response project")
        if body.workstream_id and response.get("workstream_id") != body.workstream_id:
            raise HTTPException(status_code=409, detail="artifact workstream does not match response workstream")
    require_project_workstream(body.project_id, body.workstream_id)
    artifact_id = new_id("artifact")
    payload = {
        **create_body(body),
        "metadata": sanitize_learning_value(body.metadata),
    }
    return get_store().create_idempotent(
        "artifact", artifact_id, "registered", payload, body.idempotency_key,
        parent_id=body.response_id or body.workstream_id or body.project_id,
        scope=f"artifacts:{body.response_id or body.workstream_id or body.project_id or 'global'}",
    )


@router.get("/v1/artifacts")
def list_artifacts() -> dict[str, Any]:
    return {"object": "list", "data": get_store().list("artifact"), "schema_version": API_VERSION}


@router.get("/v1/artifacts/{artifact_id}")
def get_artifact(artifact_id: str) -> dict[str, Any]:
    return require_record(artifact_id, "artifact")


def _payload_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _canvas_declaration(body: CanvasCreate) -> dict[str, Any]:
    validate_runtime_scope(body.project_id, body.workstream_id)
    payload, sanitization = runtime_create_body(body)
    resolved_links = []
    for node in body.nodes:
        resolved_links.append(resolve_artifact_link(
            ArtifactLinkInput(
                artifact_id=node.artifact_id,
                relation="canvas-node",
                expected_kind=node.artifact_kind,
            ),
            project_id=body.project_id,
        ))
    validation = {
        "valid": True,
        "node_count": len(body.nodes),
        "edge_count": len(body.edges),
        "artifact_links_resolved": len(resolved_links),
        "executed": False,
    }
    payload.update({
        "schema_version": "kolibri.canvas.v1",
        "artifact_links": resolved_links,
        "validation": validation,
        "sanitization_report": sanitization,
        "definition_sha256": _payload_sha256({"nodes": payload["nodes"], "edges": payload["edges"]}),
    })
    return payload


@router.post("/v1/canvases/validate")
def validate_canvas(body: CanvasCreate) -> dict[str, Any]:
    payload = _canvas_declaration(body)
    return {
        "schema_version": "kolibri.canvas-validation.v1",
        "valid": True,
        "dry_run": True,
        "executed": False,
        "validation": payload["validation"],
        "definition_sha256": payload["definition_sha256"],
    }


@router.post("/v1/canvases", status_code=201)
def create_canvas(body: CanvasCreate) -> dict[str, Any]:
    payload = _canvas_declaration(body)
    return get_store().create_idempotent(
        "canvas",
        new_id("canvas"),
        "active",
        payload,
        body.idempotency_key,
        parent_id=record_parent(payload),
        scope=f"canvases:{body.project_id}",
    )


@router.get("/v1/canvases")
def list_canvases(
    project_id: str | None = None,
    workstream_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    return list_runtime_records(
        "canvas", project_id=project_id, workstream_id=workstream_id, status=status
    )


@router.get("/v1/canvases/{canvas_id}")
def get_canvas(canvas_id: str) -> dict[str, Any]:
    return require_record(canvas_id, "canvas")


@router.get("/v1/canvases/{canvas_id}/status")
def get_canvas_status(canvas_id: str) -> dict[str, Any]:
    return runtime_status(require_record(canvas_id, "canvas"))


def _preview_declaration(body: PreviewCreate) -> dict[str, Any]:
    validate_runtime_scope(body.project_id, body.workstream_id)
    payload, sanitization = runtime_create_body(body)
    artifact_links: list[dict[str, Any]] = []
    if body.source_artifact:
        artifact_links.append(resolve_artifact_link(body.source_artifact, project_id=body.project_id))
    if body.entry_url:
        network_validation = validate_runtime_urls(body.entry_url, body.network.allowed_origins)
    else:
        network_validation = {
            "primary": None,
            "allowed_origins": [validate_origin(origin) for origin in body.network.allowed_origins],
            "runtime_dns_verification_required": bool(body.network.allowed_origins),
        }
    payload.update({
        "schema_version": "kolibri.preview.v1",
        "artifact_links": artifact_links,
        "network_validation": network_validation,
        "sanitization_report": sanitization,
        "runtime": {
            "adapter_status": "unverified",
            "execution_started": False,
            "reason": "preview_runtime_adapter_unverified",
            "isolation": {
                "profile": "ephemeral-container",
                "host_mounts": "deny",
                "main_application_credentials": "never_inherited",
                "cookies": "empty_ephemeral_jar",
                "network_default": "deny",
                "dns_policy": "resolve_and_pin_public_addresses_at_execution",
                "max_redirects": body.network.max_redirects,
            },
        },
    })
    return payload


@router.post("/v1/previews/validate")
def validate_preview(body: PreviewCreate) -> dict[str, Any]:
    payload = _preview_declaration(body)
    return {
        "schema_version": "kolibri.preview-validation.v1",
        "valid": True,
        "dry_run": True,
        "executed": False,
        "network_validation": payload["network_validation"],
        "runtime": payload["runtime"],
    }


@router.post("/v1/previews", status_code=202)
def create_preview(body: PreviewCreate) -> dict[str, Any]:
    payload = _preview_declaration(body)
    return get_store().create_idempotent(
        "preview",
        new_id("preview"),
        "queued",
        payload,
        body.idempotency_key,
        parent_id=record_parent(payload),
        scope=f"previews:{record_parent(payload) or 'global'}",
    )


@router.get("/v1/previews")
def list_previews(
    project_id: str | None = None,
    workstream_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    return list_runtime_records(
        "preview", project_id=project_id, workstream_id=workstream_id, status=status
    )


@router.get("/v1/previews/{preview_id}")
def get_preview(preview_id: str) -> dict[str, Any]:
    return require_record(preview_id, "preview")


@router.get("/v1/previews/{preview_id}/status")
def get_preview_status(preview_id: str) -> dict[str, Any]:
    return runtime_status(require_record(preview_id, "preview"))


@router.post("/v1/previews/{preview_id}/cancel")
def cancel_preview(preview_id: str, body: RuntimeCancel) -> dict[str, Any]:
    return cancel_runtime_record("preview", preview_id, body)


def _browser_session_declaration(body: BrowserSessionCreate) -> dict[str, Any]:
    validate_runtime_scope(body.project_id, body.workstream_id)
    payload, sanitization = runtime_create_body(body)
    network_validation = validate_runtime_urls(body.start_url, body.allowed_origins)
    payload.update({
        "schema_version": "kolibri.browser-session.v1",
        "network_validation": network_validation,
        "sanitization_report": sanitization,
        "runtime": {
            "adapter_status": "unverified",
            "execution_started": False,
            "reason": "browser_runtime_adapter_unverified",
            "isolation": {
                "profile": "ephemeral-browser-profile",
                "main_application_credentials": "never_inherited",
                "cookies": "empty_ephemeral_jar",
                "host_filesystem": "deny",
                "downloads": "deny",
                "network_default": "deny",
                "dns_policy": "resolve_and_pin_public_addresses_at_execution",
            },
        },
    })
    return payload


@router.post("/v1/browser-sessions/validate")
def validate_browser_session(body: BrowserSessionCreate) -> dict[str, Any]:
    payload = _browser_session_declaration(body)
    return {
        "schema_version": "kolibri.browser-session-validation.v1",
        "valid": True,
        "dry_run": True,
        "executed": False,
        "network_validation": payload["network_validation"],
        "runtime": payload["runtime"],
    }


@router.post("/v1/browser-sessions", status_code=202)
def create_browser_session(body: BrowserSessionCreate) -> dict[str, Any]:
    payload = _browser_session_declaration(body)
    return get_store().create_idempotent(
        "browser_session",
        new_id("browser"),
        "queued",
        payload,
        body.idempotency_key,
        parent_id=record_parent(payload),
        scope=f"browser-sessions:{record_parent(payload) or 'global'}",
    )


@router.get("/v1/browser-sessions")
def list_browser_sessions(
    project_id: str | None = None,
    workstream_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    return list_runtime_records(
        "browser_session", project_id=project_id, workstream_id=workstream_id, status=status
    )


@router.get("/v1/browser-sessions/{session_id}")
def get_browser_session(session_id: str) -> dict[str, Any]:
    return require_record(session_id, "browser_session")


@router.get("/v1/browser-sessions/{session_id}/status")
def get_browser_session_status(session_id: str) -> dict[str, Any]:
    return runtime_status(require_record(session_id, "browser_session"))


@router.post("/v1/browser-sessions/{session_id}/cancel")
def cancel_browser_session(session_id: str, body: RuntimeCancel) -> dict[str, Any]:
    return cancel_runtime_record("browser_session", session_id, body)


def _estimate_declaration(body: EstimateCreate) -> dict[str, Any]:
    validate_runtime_scope(body.project_id, body.workstream_id)
    payload, sanitization = runtime_create_body(body)
    artifact_links = [
        resolve_artifact_link(link, project_id=body.project_id) for link in body.artifact_links
    ]
    calculation = deterministic_estimate(body)
    payload.update({
        "schema_version": "kolibri.estimate.v1",
        "artifact_links": artifact_links,
        "calculation": calculation,
        "sanitization_report": sanitization,
    })
    return payload


@router.post("/v1/estimates/validate")
def validate_estimate(body: EstimateSpec) -> dict[str, Any]:
    calculation = deterministic_estimate(body)
    return {
        "schema_version": "kolibri.estimate-validation.v1",
        "valid": True,
        "dry_run": True,
        "executed": False,
        "calculation": calculation,
    }


@router.post("/v1/estimates", status_code=202)
def create_estimate(body: EstimateCreate) -> dict[str, Any]:
    payload = _estimate_declaration(body)
    return get_store().create_idempotent(
        "estimate",
        new_id("estimate"),
        "calculated",
        payload,
        body.idempotency_key,
        parent_id=record_parent(payload),
        scope=f"estimates:{record_parent(payload) or 'global'}",
    )


@router.get("/v1/estimates")
def list_estimates(
    project_id: str | None = None,
    workstream_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    return list_runtime_records(
        "estimate", project_id=project_id, workstream_id=workstream_id, status=status
    )


@router.get("/v1/estimates/{estimate_id}")
def get_estimate(estimate_id: str) -> dict[str, Any]:
    return require_record(estimate_id, "estimate")


@router.get("/v1/estimates/{estimate_id}/status")
def get_estimate_status(estimate_id: str) -> dict[str, Any]:
    return runtime_status(require_record(estimate_id, "estimate"))


def _document_declaration(body: DocumentCreate) -> dict[str, Any]:
    validate_runtime_scope(body.project_id, body.workstream_id)
    payload, sanitization = runtime_create_body(body)
    links = [resolve_artifact_link(link, project_id=body.project_id) for link in body.artifact_links]
    estimate_snapshot = None
    if body.estimate_id:
        estimate = require_record(body.estimate_id, "estimate")
        if body.project_id and estimate.get("project_id") and estimate["project_id"] != body.project_id:
            raise HTTPException(status_code=409, detail="estimate belongs to another project")
        estimate_snapshot = {
            "estimate_id": estimate["id"],
            "calculation_sha256": estimate["calculation"]["calculation_sha256"],
            "currency": estimate["calculation"]["currency"],
            "minor_unit": estimate["calculation"]["minor_unit"],
            "totals": estimate["calculation"]["totals"],
            "money_authority": estimate["calculation"]["money_authority"],
        }
    payload.update({
        "schema_version": "kolibri.document.v1",
        "artifact_links": links,
        "estimate_snapshot": estimate_snapshot,
        "sanitization_report": sanitization,
        "runtime": {
            "adapter_status": "unverified",
            "execution_started": False,
            "reason": "document_renderer_adapter_unverified",
            "requested_format": body.format,
            "artifact_required_for_completion": True,
        },
    })
    return payload


@router.post("/v1/documents/validate")
def validate_document(body: DocumentCreate) -> dict[str, Any]:
    payload = _document_declaration(body)
    return {
        "schema_version": "kolibri.document-validation.v1",
        "valid": True,
        "dry_run": True,
        "executed": False,
        "estimate_snapshot": payload["estimate_snapshot"],
        "runtime": payload["runtime"],
    }


@router.post("/v1/documents", status_code=202)
def create_document(body: DocumentCreate) -> dict[str, Any]:
    payload = _document_declaration(body)
    return get_store().create_idempotent(
        "document",
        new_id("document"),
        "queued",
        payload,
        body.idempotency_key,
        parent_id=record_parent(payload),
        scope=f"documents:{record_parent(payload) or 'global'}",
    )


@router.get("/v1/documents")
def list_documents(
    project_id: str | None = None,
    workstream_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    return list_runtime_records(
        "document", project_id=project_id, workstream_id=workstream_id, status=status
    )


@router.get("/v1/documents/{document_id}")
def get_document(document_id: str) -> dict[str, Any]:
    return require_record(document_id, "document")


@router.get("/v1/documents/{document_id}/status")
def get_document_status(document_id: str) -> dict[str, Any]:
    return runtime_status(require_record(document_id, "document"))


@router.post("/v1/documents/{document_id}/cancel")
def cancel_document(document_id: str, body: RuntimeCancel) -> dict[str, Any]:
    return cancel_runtime_record("document", document_id, body)


def _build_declaration(body: BuildCreate) -> dict[str, Any]:
    validate_runtime_scope(body.project_id, body.workstream_id)
    payload, sanitization = runtime_create_body(body)
    source_link = resolve_artifact_link(body.source_artifact, project_id=body.project_id)
    resource_class = "apple-build" if body.target in {"ios", "macos"} else "build"
    payload.update({
        "schema_version": "kolibri.build.v1",
        "artifact_links": [source_link],
        "sanitization_report": sanitization,
        "runtime": {
            "adapter_status": "unverified",
            "execution_started": False,
            "reason": "build_runner_adapter_unverified",
            "resource_class": resource_class,
            "arbitrary_command_allowed": False,
            "artifact_and_verifier_required_for_completion": True,
        },
    })
    return payload


@router.post("/v1/builds/validate")
def validate_build(body: BuildCreate) -> dict[str, Any]:
    payload = _build_declaration(body)
    return {
        "schema_version": "kolibri.build-validation.v1",
        "valid": True,
        "dry_run": True,
        "executed": False,
        "artifact_links": payload["artifact_links"],
        "runtime": payload["runtime"],
    }


@router.post("/v1/builds", status_code=202)
def create_build(body: BuildCreate) -> dict[str, Any]:
    payload = _build_declaration(body)
    return get_store().create_idempotent(
        "build",
        new_id("build"),
        "queued",
        payload,
        body.idempotency_key,
        parent_id=record_parent(payload),
        scope=f"builds:{record_parent(payload) or 'global'}",
    )


@router.get("/v1/builds")
def list_builds(
    project_id: str | None = None,
    workstream_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    return list_runtime_records(
        "build", project_id=project_id, workstream_id=workstream_id, status=status
    )


@router.get("/v1/builds/{build_id}")
def get_build(build_id: str) -> dict[str, Any]:
    return require_record(build_id, "build")


@router.get("/v1/builds/{build_id}/status")
def get_build_status(build_id: str) -> dict[str, Any]:
    return runtime_status(require_record(build_id, "build"))


@router.post("/v1/builds/{build_id}/cancel")
def cancel_build(build_id: str, body: RuntimeCancel) -> dict[str, Any]:
    return cancel_runtime_record("build", build_id, body)


def _automation_declaration(body: AutomationCreate | AutomationValidate) -> dict[str, Any]:
    validate_runtime_scope(body.project_id, body.workstream_id)
    payload, sanitization = runtime_create_body(body)
    validation = validate_automation(body)
    definition = {
        "name": payload["name"],
        "version": payload["version"],
        "enabled": payload["enabled"],
        "trigger": payload["trigger"],
        "steps": payload["steps"],
        "approval_policy": payload["approval_policy"],
    }
    definition_sha256 = _payload_sha256(definition)
    payload.update({
        "schema_version": "kolibri.automation.v1",
        "validation": validation,
        "sanitization_report": sanitization,
        "definition_sha256": definition_sha256,
        "version_history": [{"version": 1, "definition_sha256": definition_sha256}],
        "runtime": {
            "scheduler_adapter_status": "unverified",
            "execution_started": False,
            "reason": "automation_scheduler_adapter_unverified" if body.enabled else "automation_disabled",
            "enabled_intent": body.enabled,
            "approval_enforced": body.approval_policy != "none",
        },
    })
    return payload


@router.post("/v1/automations/validate")
def validate_automation_dry_run(body: AutomationValidate) -> dict[str, Any]:
    payload = _automation_declaration(body)
    return {
        "schema_version": "kolibri.automation-validation.v1",
        **payload["validation"],
        "definition_sha256": payload["definition_sha256"],
        "runtime": payload["runtime"],
    }


@router.post("/v1/automations", status_code=201)
def create_automation(body: AutomationCreate) -> dict[str, Any]:
    payload = _automation_declaration(body)
    status = "degraded" if body.enabled else "inactive"
    return get_store().create_idempotent(
        "automation",
        new_id("automation"),
        status,
        payload,
        body.idempotency_key,
        parent_id=record_parent(payload),
        scope=f"automations:{record_parent(payload) or 'global'}",
    )


@router.get("/v1/automations")
def list_automations(
    project_id: str | None = None,
    workstream_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    return list_runtime_records(
        "automation", project_id=project_id, workstream_id=workstream_id, status=status
    )


@router.get("/v1/automations/{automation_id}")
def get_automation(automation_id: str) -> dict[str, Any]:
    return require_record(automation_id, "automation")


@router.get("/v1/automations/{automation_id}/status")
def get_automation_status(automation_id: str) -> dict[str, Any]:
    return runtime_status(require_record(automation_id, "automation"))


@router.post("/v1/learning/candidates", status_code=201)
def create_learning_candidate(body: LearningCandidateCreate) -> dict[str, Any]:
    if body.source_response_id:
        require_record(body.source_response_id, "response")
    if body.license == "negative":
        raise HTTPException(status_code=422, detail="learning candidate license forbids use")
    if body.consent == "denied":
        raise HTTPException(status_code=422, detail="learning candidate consent forbids use")
    if body.consent not in {"explicit", "contractual", "public-permitted"}:
        raise HTTPException(status_code=422, detail="learning candidate consent is required")
    if body.data_classification == "private" and body.consent not in {"explicit", "contractual"}:
        raise HTTPException(status_code=422, detail="private learning candidate requires consent")
    candidate_id = new_id("learning")
    sanitized, sanitization_report = sanitize_learning_payload(create_body(body))
    strict_scan = scan_learning_payload(sanitized)
    if strict_scan.report["pii_findings"]:
        raise HTTPException(status_code=422, detail="learning candidate PII forbids use")
    sanitized.update({
        "schema_version": "kolibri.learning-candidate.v1",
        "candidate_id": candidate_id,
        "promotion_status": "candidate",
        "requires_eval": True,
        "auto_promote": False,
        "request_path_training": False,
        "production_weight_mutation": False,
        "training_eligible": (
            body.consent in {"explicit", "contractual", "public-permitted"}
            and body.license == "permitted"
            and body.retention_class == "training-approved"
        ),
        "sanitization": {
            "status": "passed",
            "redacted_fields": sorted(set(sanitization_report["redacted_field_paths"])),
            "scanner_version": sanitization_report["schema_version"],
            "reason": None,
        },
        "sanitization_report": sanitization_report,
    })
    return get_store().create_idempotent(
        "learning_candidate", candidate_id, "sanitized", sanitized, body.idempotency_key,
        parent_id=body.source_response_id or body.source_trace_id,
        scope=f"learning:{body.source_response_id or body.source_trace_id}",
    )


@router.get("/v1/learning/candidates")
def list_learning_candidates() -> dict[str, Any]:
    compatibility = get_store().list("learning_candidate")
    durable = get_learning_boundary().list_candidates()
    return {
        "object": "list",
        "data": [*compatibility, *durable],
        "schema_version": API_VERSION,
    }


@router.get("/v1/learning/intakes")
def list_learning_intakes(status: str | None = None) -> dict[str, Any]:
    try:
        data = get_learning_boundary().list_intakes(status=status)
    except (FormulaLMPolicyError, FormulaLMConflictError, FormulaLMNotFoundError) as exc:
        raise learning_http_exception(exc) from exc
    return {"object": "list", "data": data, "schema_version": API_VERSION}


@router.get("/v1/learning/intakes/{intake_id}")
def get_learning_intake(intake_id: str) -> dict[str, Any]:
    try:
        return get_learning_boundary().get_intake(intake_id)
    except (FormulaLMPolicyError, FormulaLMConflictError, FormulaLMNotFoundError) as exc:
        raise learning_http_exception(exc) from exc


@router.post("/v1/learning/queue/process")
def process_learning_queue(body: LearningQueueProcess) -> dict[str, Any]:
    """Worker entrypoint; never invoked by the synchronous response handler."""

    try:
        return get_learning_boundary().process_pending(
            worker_id=body.worker_id,
            limit=body.limit,
        )
    except (FormulaLMPolicyError, FormulaLMConflictError, FormulaLMNotFoundError) as exc:
        raise learning_http_exception(exc) from exc


@router.get("/v1/learning/status")
def learning_plane_status() -> dict[str, Any]:
    compatibility_candidates = get_store().list("learning_candidate")
    durable_candidates = get_learning_boundary().list_candidates()
    candidates = [*compatibility_candidates, *durable_candidates]
    by_promotion_status: dict[str, int] = {}
    training_eligible = 0
    for record in candidates:
        promotion_status = str(record.get("promotion_status") or "candidate")
        by_promotion_status[promotion_status] = by_promotion_status.get(promotion_status, 0) + 1
        if record.get("training_eligible") is True:
            training_eligible += 1
    boundary_status = get_learning_boundary().status()
    return {
        "schema_version": "kolibri.learning-plane-status.v1",
        "mode": "candidate-only",
        "candidate_count": len(candidates),
        "training_eligible_count": training_eligible,
        "by_promotion_status": by_promotion_status,
        "intakes_by_status": boundary_status["intakes_by_status"],
        "pending_outbox": boundary_status["pending_outbox"],
        "request_path_training": False,
        "production_weight_mutation": False,
        "auto_promote": False,
        "next_gate": "asynchronous trainer plus independent eval council is required",
    }


@router.get("/v1/learning/candidates/{candidate_id}")
def get_learning_candidate(candidate_id: str) -> dict[str, Any]:
    compatibility = get_store().get(candidate_id, "learning_candidate")
    if compatibility is not None:
        return compatibility
    try:
        return get_learning_boundary().get_candidate(candidate_id)
    except FormulaLMNotFoundError as exc:
        raise learning_http_exception(exc) from exc


@router.post("/v1/learning/candidates/{candidate_id}/transitions")
def transition_learning_candidate(
    candidate_id: str,
    body: LearningPromotionTransition,
    principal: str = Depends(require_execution_auth),
) -> dict[str, Any]:
    try:
        return get_learning_boundary().transition_candidate(
            candidate_id=candidate_id,
            idempotency_key=body.idempotency_key,
            to_status=body.to_status,
            principal=principal,
            evidence=body.evidence,
            reason=body.reason,
        )
    except (FormulaLMPolicyError, FormulaLMConflictError, FormulaLMNotFoundError) as exc:
        raise learning_http_exception(exc) from exc


@router.get("/v1/learning/candidates/{candidate_id}/transitions")
def list_learning_candidate_transitions(candidate_id: str) -> dict[str, Any]:
    try:
        data = get_learning_boundary().list_transition_events(candidate_id)
    except (FormulaLMPolicyError, FormulaLMConflictError, FormulaLMNotFoundError) as exc:
        raise learning_http_exception(exc) from exc
    return {"object": "list", "data": data, "schema_version": API_VERSION}
