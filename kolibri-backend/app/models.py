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
    default_organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=_now)


class PasswordResetTokenDB(Base):
    """Single-use password reset grant.

    Only the SHA-256 digest is persisted.  The raw bearer token exists solely
    in the recovery URL delivered to the account email address.
    """

    __tablename__ = "password_reset_tokens"

    id = Column(String, primary_key=True)
    user_id = Column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now)

    __table_args__ = (
        Index(
            "ix_password_reset_tokens_user_active",
            "user_id",
            "used_at",
            "expires_at",
        ),
    )


class OrganizationDB(Base):
    """Tenant boundary with an immutable storage scope.

    ``data_scope_id`` deliberately retains the existing ``user:<id>`` scope
    for personal organizations.  Organization membership and platform roles
    are separate authorization domains.
    """

    __tablename__ = "organizations"

    id = Column(String, primary_key=True)
    data_scope_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active", server_default="active")
    settings = Column(JSON, nullable=False, default=dict, server_default="{}")
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("data_scope_id", name="uq_organizations_data_scope_id"),
        UniqueConstraint("slug", name="uq_organizations_slug"),
        Index("ix_organizations_status", "status"),
    )


class OrganizationMembershipDB(Base):
    """An active user's role inside one organization."""

    __tablename__ = "organization_memberships"

    id = Column(String, primary_key=True)
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(String, nullable=False, default="member", server_default="member")
    status = Column(String, nullable=False, default="active", server_default="active")
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_organization_memberships_org_user",
        ),
        Index(
            "ix_organization_memberships_user_status",
            "user_id",
            "status",
        ),
        Index(
            "ix_organization_memberships_org_status",
            "organization_id",
            "status",
        ),
    )


class OrganizationAuditEventDB(Base):
    """Append-only organization administration audit event."""

    __tablename__ = "organization_audit_events"

    id = Column(String, primary_key=True)
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_user_id = Column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action = Column(String, nullable=False)
    target_type = Column(String, nullable=True)
    target_id = Column(String, nullable=True)
    request_id = Column(String, nullable=True)
    attributes = Column("metadata", JSON, nullable=False, default=dict, server_default="{}")
    created_at = Column(DateTime, nullable=False, default=_now)

    __table_args__ = (
        Index(
            "ix_organization_audit_events_org_created",
            "organization_id",
            "created_at",
        ),
        Index("ix_organization_audit_events_actor", "actor_user_id"),
    )


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
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    client_record_id = Column(
        String,
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
    )
    object_record_id = Column(
        String,
        ForeignKey("construction_objects.id", ondelete="SET NULL"),
        nullable=True,
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
    technology_card = Column(JSON, nullable=True)
    procurement_report = Column(JSON, nullable=True)
    price_sources = Column(JSON, nullable=False, default=list, server_default="[]")
    evidence_issues = Column(JSON, nullable=False, default=list, server_default="[]")
    title = Column(String, nullable=False)
    client = Column(String, default="")
    object_name = Column(String, default="")
    region = Column(String, default="")
    price_as_of = Column(String, nullable=True)
    currency = Column(String, default="RUB")
    overhead_rate = Column(String, default="0")
    profit_rate = Column(String, nullable=False, default="0", server_default="0")
    contingency_rate = Column(String, nullable=False, default="0", server_default="0")
    general_contractor_rate = Column(String, nullable=False, default="0", server_default="0")
    discount_rate = Column(String, nullable=False, default="0", server_default="0")
    vat_rate = Column(String, default="22")
    tax_regime = Column(String, nullable=False, default="unspecified", server_default="unspecified")
    subtotal = Column(String, default="0")
    overhead_amount = Column(String, default="0")
    profit_amount = Column(String, nullable=False, default="0", server_default="0")
    contingency_amount = Column(String, nullable=False, default="0", server_default="0")
    general_contractor_amount = Column(String, nullable=False, default="0", server_default="0")
    discount_amount = Column(String, nullable=False, default="0", server_default="0")
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
        Index("ix_estimates_project_updated", "project_id", "updated_at"),
        Index("ix_estimates_scope_created_at", "scope_id", "created_at"),
        Index("ix_estimates_scope_status", "scope_id", "status"),
        Index("ix_estimates_organization_created", "organization_id", "created_at"),
        Index("ix_estimates_scope_client", "scope_id", "client_record_id"),
        Index("ix_estimates_scope_object", "scope_id", "object_record_id"),
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


class WorkCatalogDB(Base):
    """Tenant-scoped reusable work line promoted from approved estimates."""

    __tablename__ = "work_catalog"

    id = Column(String, primary_key=True)
    scope_id = Column(String, nullable=False)
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    normalized_key = Column(String, nullable=False)
    name = Column(String, nullable=False)
    unit = Column(String, nullable=False, default="шт", server_default="шт")
    category = Column(String, nullable=False, default="", server_default="")
    latest_price = Column(String, nullable=False, default="0", server_default="0")
    price_source = Column(String, nullable=False, default="estimate", server_default="estimate")
    price_observed_at = Column(DateTime, nullable=True)
    usage_count = Column(Integer, nullable=False, default=1, server_default="1")
    status = Column(String, nullable=False, default="approved", server_default="approved")
    source_estimate_id = Column(String, ForeignKey("estimates.id", ondelete="SET NULL"), nullable=True)
    source_version = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("scope_id", "normalized_key", "unit", name="uq_work_catalog_scope_key_unit"),
        Index("ix_work_catalog_scope_updated", "scope_id", "updated_at"),
        Index("ix_work_catalog_organization_status", "organization_id", "status"),
    )


class OwnerModelConnectionDB(Base):
    """Encrypted owner-managed OpenAI-compatible chat route."""

    __tablename__ = "owner_model_connections"

    id = Column(String, primary_key=True)
    owner_user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    model = Column(String, nullable=False)
    encrypted_api_key = Column(String, nullable=False, default="", server_default="")
    active = Column(Boolean, nullable=False, default=True, server_default="1")
    last_status = Column(String, nullable=False, default="untested", server_default="untested")
    last_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)


class TechnologyCatalogDB(Base):
    """Tenant-scoped approved technology card with immutable source lineage."""

    __tablename__ = "technology_catalog"

    id = Column(String, primary_key=True)
    scope_id = Column(String, nullable=False)
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    content_sha256 = Column(String, nullable=False)
    title = Column(String, nullable=False)
    object_type = Column(String, nullable=False, default="", server_default="")
    card = Column(JSON, nullable=False)
    usage_count = Column(Integer, nullable=False, default=1, server_default="1")
    status = Column(String, nullable=False, default="approved", server_default="approved")
    source_estimate_id = Column(String, ForeignKey("estimates.id", ondelete="SET NULL"), nullable=True)
    source_version = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("scope_id", "content_sha256", name="uq_technology_catalog_scope_hash"),
        Index("ix_technology_catalog_scope_updated", "scope_id", "updated_at"),
        Index("ix_technology_catalog_organization_status", "organization_id", "status"),
    )


class ClientDB(Base):
    """Tenant-scoped client created from an estimate/chat brief."""

    __tablename__ = "clients"

    id = Column(String, primary_key=True)
    scope_id = Column(String, nullable=False)
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    normalized_key = Column(String, nullable=False)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False, default="", server_default="")
    email = Column(String, nullable=False, default="", server_default="")
    inn = Column(String, nullable=False, default="", server_default="")
    kpp = Column(String, nullable=False, default="", server_default="")
    address = Column(String, nullable=False, default="", server_default="")
    contact_person = Column(String, nullable=False, default="", server_default="")
    source = Column(
        String,
        nullable=False,
        default="chat_estimate",
        server_default="chat_estimate",
    )
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("scope_id", "normalized_key", name="uq_clients_scope_key"),
        Index("ix_clients_scope_updated", "scope_id", "updated_at"),
        Index("ix_clients_organization_updated", "organization_id", "updated_at"),
    )


class ConstructionObjectDB(Base):
    """Tenant-scoped construction object linked to a client and estimates."""

    __tablename__ = "construction_objects"

    id = Column(String, primary_key=True)
    scope_id = Column(String, nullable=False)
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    client_id = Column(
        String,
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
    )
    normalized_key = Column(String, nullable=False)
    name = Column(String, nullable=False)
    address = Column(String, nullable=False, default="", server_default="")
    region = Column(String, nullable=False, default="", server_default="")
    source = Column(
        String,
        nullable=False,
        default="chat_estimate",
        server_default="chat_estimate",
    )
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint(
            "scope_id",
            "normalized_key",
            name="uq_construction_objects_scope_key",
        ),
        Index("ix_construction_objects_scope_updated", "scope_id", "updated_at"),
        Index("ix_construction_objects_organization_updated", "organization_id", "updated_at"),
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
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
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
        Index("ix_documents_organization_created", "organization_id", "created_at"),
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
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    title = Column(String, nullable=False, default="Новый проект")
    title_source = Column(String, nullable=False, default="default")
    status = Column(String, nullable=False, default="active")
    version = Column(Integer, nullable=False, default=1)
    message_count = Column(Integer, nullable=False, default=0)
    run_count = Column(Integer, nullable=False, default=0, server_default="0")
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
        Index("ix_projects_organization_updated", "organization_id", "updated_at"),
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


class ProductRunDB(Base):
    """Canonical Product Chat run owned by Product/Data Authority."""

    __tablename__ = "product_runs"

    id = Column(String, primary_key=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_id = Column(String, nullable=False)
    tenant_id = Column(String, nullable=False)
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    run_sequence = Column(Integer, nullable=False)
    input_message_id = Column(
        String,
        ForeignKey("project_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    retry_of_run_id = Column(String, nullable=True)
    resume_of_run_id = Column(String, nullable=True)
    case_id = Column(String, nullable=False)
    goal_id = Column(String, nullable=True)
    home_task_id = Column(String, nullable=True)
    lifecycle = Column(String, nullable=False, default="accepted", server_default="accepted")
    outcome = Column(String, nullable=True)
    last_event_sequence = Column(Integer, nullable=False, default=0, server_default="0")
    last_event_id = Column(String, nullable=True)
    active_interrupt_ids = Column(JSON, nullable=False, default=list, server_default="[]")
    version = Column(Integer, nullable=False, default=1, server_default="1")
    created_by = Column(String, nullable=False)
    preferred_agent_profile = Column(String, nullable=False, default="auto", server_default="auto")
    client_run_id = Column(String, nullable=True)
    idempotency_key = Column(String, nullable=False)
    request_hash = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)
    finished_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("project_id", "run_sequence", name="uq_product_runs_sequence"),
        UniqueConstraint("project_id", "idempotency_key", name="uq_product_runs_idempotency"),
        Index("ix_product_runs_scope_updated", "scope_id", "updated_at"),
        Index("ix_product_runs_thread_sequence", "project_id", "run_sequence"),
        Index("ix_product_runs_lifecycle_updated", "lifecycle", "updated_at"),
    )


class ProductRunEventDB(Base):
    """Immutable ordered Product Run event record."""

    __tablename__ = "product_run_events"

    id = Column(String, primary_key=True)
    run_id = Column(
        String,
        ForeignKey("product_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence = Column(Integer, nullable=False)
    event_type = Column(String, nullable=False)
    record = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_product_run_events_sequence"),
        Index("ix_product_run_events_run_sequence", "run_id", "sequence"),
    )


class ProductRunInterruptDB(Base):
    """Persisted Product interrupt; the public contract remains immutable by version."""

    __tablename__ = "product_run_interrupts"

    id = Column(String, primary_key=True)
    run_id = Column(
        String,
        ForeignKey("product_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_id = Column(String, nullable=False)
    state = Column(String, nullable=False)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    record = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_product_run_interrupts_run_state", "run_id", "state"),
        Index("ix_product_run_interrupts_scope_updated", "scope_id", "updated_at"),
    )


class ProductRunOutboxDB(Base):
    """Durable owner-local dispatch job containing a versioned Home command."""

    __tablename__ = "product_run_outbox"

    id = Column(String, primary_key=True)
    run_id = Column(
        String,
        ForeignKey("product_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    scope_id = Column(String, nullable=False)
    state = Column(String, nullable=False, default="queued", server_default="queued")
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    max_attempts = Column(Integer, nullable=False, default=3, server_default="3")
    lease_owner = Column(String, nullable=True)
    lease_until = Column(DateTime, nullable=True)
    available_at = Column(DateTime, nullable=False, default=_now)
    command_envelope = Column(JSON, nullable=False)
    last_error_code = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_product_run_outbox_state_available", "state", "available_at"),
        Index("ix_product_run_outbox_scope_updated", "scope_id", "updated_at"),
    )


class ProductRunBudgetDB(Base):
    """Atomic UTC-day execution budget owned by Product/Data Authority."""

    __tablename__ = "product_run_budgets"

    id = Column(String, primary_key=True)
    scope_id = Column(String, nullable=False)
    bucket_date = Column(String, nullable=False)
    max_runs = Column(Integer, nullable=False)
    reserved_runs = Column(Integer, nullable=False, default=0, server_default="0")
    succeeded_runs = Column(Integer, nullable=False, default=0, server_default="0")
    failed_runs = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint(
            "scope_id",
            "bucket_date",
            name="uq_product_run_budgets_scope_bucket",
        ),
        Index(
            "ix_product_run_budgets_scope_bucket",
            "scope_id",
            "bucket_date",
        ),
    )


class ProductRunBudgetReservationDB(Base):
    """One durable quota reservation bound exactly to one Product run."""

    __tablename__ = "product_run_budget_reservations"

    id = Column(String, primary_key=True)
    run_id = Column(
        String,
        ForeignKey("product_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    budget_id = Column(
        String,
        ForeignKey("product_run_budgets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    scope_id = Column(String, nullable=False)
    preferred_agent_profile = Column(String, nullable=False)
    state = Column(String, nullable=False, default="reserved", server_default="reserved")
    created_at = Column(DateTime, nullable=False, default=_now)
    finished_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index(
            "ix_product_run_budget_reservations_budget_state",
            "budget_id",
            "state",
        ),
        Index(
            "ix_product_run_budget_reservations_scope_created",
            "scope_id",
            "created_at",
        ),
    )


class PublicResponseDB(Base):
    """Durable, owner-scoped OpenAI-compatible response authority."""

    __tablename__ = "public_responses"

    id = Column(String, primary_key=True)
    owner_scope = Column(String, nullable=False)
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
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
        Index(
            "ix_public_responses_organization_updated",
            "organization_id",
            "updated_at",
        ),
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
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    name = Column(String, nullable=False)
    key_prefix = Column(String, nullable=False)
    secret_hash = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_now)
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("secret_hash", name="uq_public_api_keys_secret_hash"),
        Index("ix_public_api_keys_owner_revoked", "owner_scope", "revoked_at", "created_at"),
        Index(
            "ix_public_api_keys_organization_revoked",
            "organization_id",
            "revoked_at",
            "created_at",
        ),
    )


class ProjectSourceDocumentDB(Base):
    """Immutable source-file registration inside one tenant-owned project."""

    __tablename__ = "project_source_documents"

    id = Column(String, primary_key=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_id = Column(String, nullable=False)
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    artifact_id = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String, nullable=False)
    document_kind = Column(String, nullable=False, default="project_document")
    status = Column(String, nullable=False, default="queued")
    ingestion_version = Column(Integer, nullable=False, default=1)
    provider_file_id = Column(String, nullable=True)
    vector_store_id = Column(String, nullable=True)
    error_code = Column(String, nullable=True)
    attributes = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "sha256",
            name="uq_project_source_documents_project_sha256",
        ),
        Index(
            "ix_project_source_documents_scope_project_updated",
            "scope_id",
            "project_id",
            "updated_at",
        ),
        Index(
            "ix_project_source_documents_status_updated",
            "status",
            "updated_at",
        ),
    )


class NormativeSourceDB(Base):
    """Tenant-scoped normative source registry with required legal provenance."""

    __tablename__ = "normative_sources"

    id = Column(String, primary_key=True)
    scope_id = Column(String, nullable=False)
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    authority = Column(String, nullable=False)
    licence = Column(String, nullable=False)
    jurisdiction = Column(String, nullable=False)
    source_kind = Column(String, nullable=False, default="regulation")
    corpus_tier = Column(String, nullable=False, default="official")
    title = Column(String, nullable=False, default="Нормативный источник")
    effective_from = Column(DateTime, nullable=False)
    effective_until = Column(DateTime, nullable=False)
    checksum = Column(String, nullable=False)
    checksum_algorithm = Column(String, nullable=False, default="sha256")
    source_url = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")
    attributes = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_normative_sources_scope_tier", "scope_id", "corpus_tier"),
        Index("ix_normative_sources_scope_jurisdiction", "scope_id", "jurisdiction"),
        Index("ix_normative_sources_scope_updated", "scope_id", "updated_at"),
    )


class NormativeSourceSnapshotDB(Base):
    """Immutable raw snapshot and parser output for a normative source version."""

    __tablename__ = "normative_source_snapshots"

    id = Column(String, primary_key=True)
    source_id = Column(
        String,
        ForeignKey("normative_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_id = Column(String, nullable=False)
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    ingestion_version = Column(Integer, nullable=False)
    parser_version = Column(String, nullable=False, default="text_lines_v1")
    state = Column(String, nullable=False, default="ready")
    idempotency_key = Column(String, nullable=False)
    raw_artifact_id = Column(String, nullable=False)
    raw_artifact_revision = Column(Integer, nullable=False, default=1)
    raw_checksum = Column(String, nullable=False)
    chunk_count = Column(Integer, nullable=False, default=0)
    error_code = Column(String, nullable=True)
    attributes = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint(
            "scope_id",
            "source_id",
            "ingestion_version",
            name="uq_normative_source_snapshots_scope_source_version",
        ),
        UniqueConstraint(
            "scope_id",
            "source_id",
            "parser_version",
            "raw_checksum",
            name="uq_normative_source_snapshots_scope_source_parser_checksum",
        ),
        UniqueConstraint(
            "scope_id",
            "idempotency_key",
            name="uq_normative_source_snapshots_scope_idempotency",
        ),
        Index(
            "ix_normative_source_snapshots_scope_source",
            "scope_id",
            "source_id",
            "created_at",
        ),
    )

class NormativeSourceClaimDB(Base):
    """Tenant-scoped claim backed by explicit normative citations."""

    __tablename__ = "normative_source_claims"

    id = Column(String, primary_key=True)
    scope_id = Column(String, nullable=False)
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_id = Column(
        String,
        ForeignKey("normative_sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    claim_status = Column(
        String,
        nullable=False,
        default="review_required",
        server_default="review_required",
    )
    confidence = Column(Float, nullable=False)
    claim_text = Column(Text, nullable=False)
    rationale = Column(Text, nullable=True)
    metadata_payload = Column("metadata", JSON, nullable=False, default=dict, server_default="{}")
    citations = Column("citations", JSON, nullable=False, default=list, server_default="[]")
    requires_review = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_normative_source_claims_scope_status", "scope_id", "claim_status", "created_at"),
        Index("ix_normative_source_claims_scope_source", "scope_id", "source_id", "created_at"),
        Index("ix_normative_source_claims_scope_created", "scope_id", "created_at"),
    )

class NormativeSourceChunkDB(Base):
    """Parsed chunk with immutable parser coordinates and content digest."""

    __tablename__ = "normative_source_chunks"

    id = Column(String, primary_key=True)
    snapshot_id = Column(
        String,
        ForeignKey("normative_source_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id = Column(
        String,
        ForeignKey("normative_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_id = Column(String, nullable=False)
    ingestion_version = Column(Integer, nullable=False)
    parser_version = Column(String, nullable=False)
    ordinal = Column(Integer, nullable=False)
    line_start = Column(Integer, nullable=False)
    line_end = Column(Integer, nullable=False)
    char_start = Column(Integer, nullable=False)
    char_end = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    content_sha256 = Column(String, nullable=False)
    attributes = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "ordinal",
            name="uq_normative_source_chunks_snapshot_ordinal",
        ),
        Index(
            "ix_normative_source_chunks_scope_source_version",
            "scope_id",
            "source_id",
            "ingestion_version",
        ),
    )


class ProjectKnowledgeBaseDB(Base):
    """One retrieval boundary per project; never shared by a global env list."""

    __tablename__ = "project_knowledge_bases"

    id = Column(String, primary_key=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_id = Column(String, nullable=False)
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider = Column(String, nullable=False, default="openai")
    vector_store_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending")
    error_code = Column(String, nullable=True)
    last_indexed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("project_id", name="uq_project_knowledge_bases_project"),
        UniqueConstraint(
            "scope_id",
            "vector_store_id",
            name="uq_project_knowledge_bases_scope_vector_store",
        ),
        Index(
            "ix_project_knowledge_bases_scope_status",
            "scope_id",
            "status",
        ),
    )


class DocumentIngestionJobDB(Base):
    """Idempotent, leaseable document-ingestion queue record."""

    __tablename__ = "document_ingestion_jobs"

    id = Column(String, primary_key=True)
    document_id = Column(
        String,
        ForeignKey("project_source_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_id = Column(String, nullable=False)
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    state = Column(String, nullable=False, default="queued")
    stage = Column(String, nullable=False, default="validate")
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
    idempotency_key = Column(String, nullable=False)
    lease_owner = Column(String, nullable=True)
    lease_until = Column(DateTime, nullable=True)
    error_code = Column(String, nullable=True)
    result = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "scope_id",
            "idempotency_key",
            name="uq_document_ingestion_jobs_scope_idempotency",
        ),
        Index(
            "ix_document_ingestion_jobs_state_lease_created",
            "state",
            "lease_until",
            "created_at",
        ),
        Index(
            "ix_document_ingestion_jobs_project_created",
            "project_id",
            "created_at",
        ),
    )


class DocumentChunkDB(Base):
    """Locally traceable source fragment with page/sheet/cell provenance."""

    __tablename__ = "document_chunks"

    id = Column(String, primary_key=True)
    document_id = Column(
        String,
        ForeignKey("project_source_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_id = Column(String, nullable=False)
    ordinal = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=True)
    sheet_name = Column(String, nullable=True)
    cell_range = Column(String, nullable=True)
    content = Column(Text, nullable=False)
    content_sha256 = Column(String, nullable=False)
    attributes = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "ordinal",
            name="uq_document_chunks_document_ordinal",
        ),
        Index(
            "ix_document_chunks_scope_project_document",
            "scope_id",
            "project_id",
            "document_id",
        ),
    )
