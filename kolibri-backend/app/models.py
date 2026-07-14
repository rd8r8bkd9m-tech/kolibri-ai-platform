"""SQLAlchemy ORM models for Kolibri."""
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.database import Base


LEGACY_ESTIMATE_SCOPE = "legacy:quarantined"
LEGACY_DOCUMENT_SCOPE = "legacy:quarantined"


def _now():
    return datetime.now(timezone.utc)


class UserDB(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)


class EstimateDB(Base):
    __tablename__ = "estimates"

    id = Column(String, primary_key=True)
    # Estimate ownership is bound to the same signed browser/user principal as
    # project history.  The server default is intentionally unreachable by a
    # public principal: legacy or accidentally unscoped rows fail closed.
    scope_id = Column(
        String,
        nullable=False,
        default=LEGACY_ESTIMATE_SCOPE,
        server_default=LEGACY_ESTIMATE_SCOPE,
    )
    version = Column(Integer, nullable=False, default=1)
    status = Column(String, default="draft")
    # ``status`` above is the legacy editor lifecycle.  Truth/pricing status is
    # intentionally separate and can never turn ``draft`` into ``ready``.
    estimate_status = Column(
        String, nullable=False, default="needs_input", server_default="needs_input"
    )
    pricing_status = Column(
        String, nullable=False, default="needs_input", server_default="needs_input"
    )
    scope_status = Column(
        String, nullable=False, default="unverified", server_default="unverified"
    )
    source_note = Column(Text, nullable=False, default="", server_default="")
    assumptions = Column(JSON, nullable=False, default=list, server_default="[]")
    questions = Column(JSON, nullable=False, default=list, server_default="[]")
    price_sources = Column(JSON, nullable=False, default=list, server_default="[]")
    evidence_issues = Column(JSON, nullable=False, default=list, server_default="[]")
    title = Column(String, nullable=False)
    client = Column(String, default="")
    object_name = Column(String, default="")
    region = Column(String, default="")
    currency = Column(String, default="RUB")
    overhead_rate = Column(String, default="0")
    vat_rate = Column(String, default="22")
    subtotal = Column(String, default="0")
    overhead_amount = Column(String, default="0")
    vat_amount = Column(String, default="0")
    total = Column(String, default="0")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    sections = relationship(
        "SectionDB",
        back_populates="estimate",
        cascade="all, delete-orphan",
        order_by="SectionDB.sort_order, SectionDB.id",
    )
    revisions = relationship(
        "EstimateRevisionDB",
        back_populates="estimate",
        cascade="all, delete-orphan",
        order_by="EstimateRevisionDB.version",
    )

    __table_args__ = (
        Index("ix_estimates_status", "status"),
        Index("ix_estimates_created_at", "created_at"),
        Index("ix_estimates_scope_created_at", "scope_id", "created_at"),
        Index("ix_estimates_scope_status", "scope_id", "status"),
    )


class SectionDB(Base):
    __tablename__ = "sections"

    id = Column(String, primary_key=True)
    estimate_id = Column(String, ForeignKey("estimates.id", ondelete="CASCADE"), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    title = Column(String, nullable=False)
    subtotal = Column(String, default="0")

    estimate = relationship("EstimateDB", back_populates="sections")
    positions = relationship(
        "PositionDB",
        back_populates="section",
        cascade="all, delete-orphan",
        order_by="PositionDB.sort_order, PositionDB.id",
    )


class PositionDB(Base):
    __tablename__ = "positions"

    id = Column(String, primary_key=True)
    section_id = Column(String, ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    code = Column(String, default="")
    name = Column(String, nullable=False)
    unit = Column(String, default="шт")
    quantity = Column(String, default="0")
    price = Column(String, default="0")
    sum = Column(String, default="0")
    source = Column(String, default="")
    price_evidence = Column(JSON, nullable=False, default=list, server_default="[]")
    comment = Column(Text, default="")

    section = relationship("SectionDB", back_populates="positions")


class EstimateRevisionDB(Base):
    """Append-only snapshot of a successfully saved estimate version."""

    __tablename__ = "estimate_revisions"

    id = Column(String, primary_key=True)
    estimate_id = Column(
        String,
        ForeignKey("estimates.id", ondelete="CASCADE"),
        nullable=False,
    )
    version = Column(Integer, nullable=False)
    snapshot = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_now)

    estimate = relationship("EstimateDB", back_populates="revisions")

    __table_args__ = (
        UniqueConstraint("estimate_id", "version", name="uq_estimate_revisions_version"),
        Index("ix_estimate_revisions_estimate_version", "estimate_id", "version"),
    )


class DocumentDB(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True)
    # Documents use the same signed browser/user principal boundary as
    # projects and estimates.  Legacy rows are deliberately unreachable until
    # an explicit audited owner migration assigns them to a real scope.
    scope_id = Column(
        String,
        nullable=False,
        default=LEGACY_DOCUMENT_SCOPE,
        server_default=LEGACY_DOCUMENT_SCOPE,
    )
    title = Column(String, nullable=False)
    type = Column(String, default="custom")
    status = Column(String, default="draft")
    client = Column(String, default="")
    project = Column(String, default="")
    content = Column(Text, default="")
    variables = Column(JSON, default=dict)
    template = Column(Text, default="")
    estimate_id = Column(String, ForeignKey("estimates.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_documents_type", "type"),
        Index("ix_documents_status", "status"),
        Index("ix_documents_created_at", "created_at"),
        Index("ix_documents_scope_created_at", "scope_id", "created_at"),
        Index("ix_documents_scope_status", "scope_id", "status"),
    )


class AgentDB(Base):
    __tablename__ = "agents"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    role = Column(String, default="")
    status = Column(String, default="idle")
    node_id = Column(String, nullable=True)
    current_task = Column(String, nullable=True)
    progress = Column(Integer, default=0)
    model = Column(String, nullable=True)
    capabilities = Column(JSON, default=dict)
    cost_accumulated = Column(String, default="0")
    heartbeat_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_agents_status", "status"),
    )


class NodeDB(Base):
    __tablename__ = "nodes"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    region = Column(String, default="")
    ip_address = Column(String, default="")
    status = Column(String, default="healthy")
    cpu_percent = Column(String, default="0")
    ram_percent = Column(String, default="0")
    disk_percent = Column(String, default="0")
    network_mbps = Column(String, default="0")
    agent_count = Column(Integer, default=0)
    task_count = Column(Integer, default=0)
    ping_ms = Column(Integer, default=0)
    max_agents = Column(Integer, default=50)
    capabilities = Column(JSON, default=dict)


class TaskDB(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True)
    workflow_id = Column(String, default="")
    state = Column(String, default="queued")
    priority = Column(Integer, default=1)
    owner_agent_id = Column(String, nullable=True)
    node_id = Column(String, nullable=True)
    budget_limit = Column(String, nullable=True)
    attempts = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_tasks_state", "state"),
        Index("ix_tasks_created_at", "created_at"),
    )


class CatalogItemDB(Base):
    __tablename__ = "price_catalog"

    id = Column(String, primary_key=True)
    code = Column(String, default="")
    name = Column(String, nullable=False)
    unit = Column(String, default="")
    price = Column(String, default="0")
    category = Column(String, default="")
    source = Column(String, default="")
    region = Column(String, default="Россия")
    currency = Column(String, default="RUB")
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_catalog_code", "code"),
        Index("ix_catalog_category", "category"),
        Index("ix_catalog_region", "region"),
    )


class ProjectDB(Base):
    """Durable project/thread metadata.

    ``scope_id`` is deliberately separate from a user foreign key so signed
    anonymous sessions and authenticated principals share one durable public
    contract without sharing data.
    """

    __tablename__ = "projects"

    id = Column(String, primary_key=True)
    scope_id = Column(String, nullable=False)
    title = Column(String, nullable=False, default="Новый проект")
    title_source = Column(String, nullable=False, default="default")
    status = Column(String, nullable=False, default="active")
    version = Column(Integer, nullable=False, default=1)
    message_count = Column(Integer, nullable=False, default=0)
    attributes = Column("metadata", JSON, nullable=False, default=dict)
    idempotency_key = Column(String, nullable=True)
    create_request_hash = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)
    last_message_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    messages = relationship(
        "ProjectMessageDB",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectMessageDB.sequence",
    )

    __table_args__ = (
        UniqueConstraint("scope_id", "idempotency_key", name="uq_projects_scope_idempotency"),
        Index("ix_projects_scope_deleted_updated", "scope_id", "deleted_at", "updated_at"),
        Index("ix_projects_scope_last_message", "scope_id", "last_message_at"),
    )


class ProjectMessageDB(Base):
    """Immutable chat message belonging to a project."""

    __tablename__ = "project_messages"

    id = Column(String, primary_key=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_id = Column(String, nullable=False)
    sequence = Column(Integer, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="completed")
    attributes = Column("metadata", JSON, nullable=False, default=dict)
    idempotency_key = Column(String, nullable=True)
    request_hash = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    project = relationship("ProjectDB", back_populates="messages")
    mutations = relationship(
        "ProjectMessageMutationDB",
        back_populates="message",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("project_id", "sequence", name="uq_project_messages_sequence"),
        UniqueConstraint("project_id", "idempotency_key", name="uq_project_messages_idempotency"),
        Index("ix_project_messages_project_sequence", "project_id", "sequence"),
        Index("ix_project_messages_scope_created", "scope_id", "created_at"),
    )


class ProjectMessageMutationDB(Base):
    """Idempotency ledger for message lifecycle mutations."""

    __tablename__ = "project_message_mutations"

    id = Column(String, primary_key=True)
    message_id = Column(
        String,
        ForeignKey("project_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_id = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=False)
    request_hash = Column(String, nullable=False)
    response_payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_now)

    message = relationship("ProjectMessageDB", back_populates="mutations")

    __table_args__ = (
        UniqueConstraint("message_id", "idempotency_key", name="uq_message_mutations_idempotency"),
        Index("ix_message_mutations_scope_created", "scope_id", "created_at"),
    )


class PublicResponseDB(Base):
    """Durable, owner-scoped OpenAI-compatible response authority."""

    __tablename__ = "public_responses"

    id = Column(String, primary_key=True)
    owner_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=True)
    request_hash = Column(String, nullable=True)
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    events = relationship(
        "PublicResponseEventDB",
        back_populates="response",
        cascade="all, delete-orphan",
        order_by="PublicResponseEventDB.sequence",
    )

    __table_args__ = (
        UniqueConstraint(
            "owner_scope",
            "idempotency_key",
            name="uq_public_responses_scope_idempotency",
        ),
        Index("ix_public_responses_scope_updated", "owner_scope", "updated_at"),
        Index("ix_public_responses_status_updated", "status", "updated_at"),
    )


class PublicResponseEventDB(Base):
    """Immutable ordered event belonging to one durable response."""

    __tablename__ = "public_response_events"

    id = Column(String, primary_key=True)
    response_id = Column(
        String,
        ForeignKey("public_responses.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence = Column(Integer, nullable=False)
    event_type = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_now)

    response = relationship("PublicResponseDB", back_populates="events")

    __table_args__ = (
        UniqueConstraint(
            "response_id",
            "sequence",
            name="uq_public_response_events_sequence",
        ),
        Index("ix_public_response_events_response_sequence", "response_id", "sequence"),
    )


class ProjectAccessDB(Base):
    """Explicit cross-surface access to one project.

    The owner remains ``ProjectDB.scope_id``.  A grant lets a second signed
    principal continue the same project without weakening the default
    cross-scope 404 contract for every other project.
    """

    __tablename__ = "project_access"

    id = Column(String, primary_key=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_id = Column(String, nullable=False)
    permission = Column(String, nullable=False, default="read_write")
    source = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_now)
    revoked_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("project_id", "scope_id", name="uq_project_access_scope"),
        Index("ix_project_access_scope_project", "scope_id", "project_id"),
    )


class ProjectHandoffDB(Base):
    """One-use bearer handoff from Telegram to a signed browser session.

    Only a SHA-256 token digest is stored.  The raw token travels in the URL
    fragment, so it is not sent to nginx or written to access logs.
    """

    __tablename__ = "project_handoffs"

    id = Column(String, primary_key=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_scope_id = Column(String, nullable=False)
    token_hash = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    claimed_by_scope_id = Column(String, nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_project_handoffs_token_hash"),
        UniqueConstraint("idempotency_key", name="uq_project_handoffs_idempotency"),
        Index("ix_project_handoffs_project_expiry", "project_id", "expires_at"),
    )


class TelegramDeliveryEvidenceDB(Base):
    """Latest independently derived Telegram webhook delivery evidence.

    This is deliberately a singleton instead of an append-only copy of every
    Telegram update.  The durable project/message ledger remains the audit log
    for user content; this row records only the minimum non-secret facts needed
    to prove that an update reached the canonical receiver from an official
    Telegram webhook network.
    """

    __tablename__ = "telegram_delivery_evidence"

    id = Column(String, primary_key=True)
    update_id = Column(Integer, nullable=False)
    response_method = Column(String, nullable=False)
    origin_network = Column(String, nullable=False)
    verified_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)


class TelegramUpdateDB(Base):
    """Durable Telegram ingress and outbound state machine.

    The webhook writes this row before acknowledging Telegram.  A separate
    worker owns provider execution and Bot API delivery, so a slow provider can
    never extend webhook latency.  ``update_id`` is the channel idempotency key.
    """

    __tablename__ = "telegram_updates"

    id = Column(String, primary_key=True)
    update_id = Column(Integer, nullable=False)
    chat_id = Column(String, nullable=False)
    message_id = Column(Integer, nullable=False)
    payload_hash = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    state = Column(String, nullable=False, default="queued")
    attempts = Column(Integer, nullable=False, default=0)
    lease_owner = Column(String, nullable=True)
    lease_until = Column(DateTime, nullable=True)
    project_id = Column(String, nullable=True)
    assistant_message_id = Column(String, nullable=True)
    response_id = Column(String, nullable=True)
    acknowledgement_message_id = Column(Integer, nullable=True)
    result_message_id = Column(Integer, nullable=True)
    outbound_state = Column(String, nullable=False, default="pending")
    delivery_method = Column(String, nullable=True)
    last_error_code = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("update_id", name="uq_telegram_updates_update_id"),
        Index("ix_telegram_updates_state_lease", "state", "lease_until", "created_at"),
        Index("ix_telegram_updates_chat_created", "chat_id", "created_at"),
    )


class TelegramBotIdentityDB(Base):
    """Sanitised ``getMe`` evidence for the one canonical bot identity."""

    __tablename__ = "telegram_bot_identity"

    id = Column(String, primary_key=True)
    bot_id = Column(String, nullable=True)
    username = Column(String, nullable=True)
    verified = Column(Boolean, nullable=False, default=False)
    verified_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)


class PublicApiKeyDB(Base):
    """Owner-scoped public API key metadata; plaintext is never persisted."""

    __tablename__ = "public_api_keys"

    id = Column(String, primary_key=True)
    owner_scope = Column(String, nullable=False)
    name = Column(String, nullable=False)
    key_prefix = Column(String, nullable=False)
    secret_hash = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_now)
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("secret_hash", name="uq_public_api_keys_secret_hash"),
        Index("ix_public_api_keys_owner_revoked", "owner_scope", "revoked_at", "created_at"),
    )
