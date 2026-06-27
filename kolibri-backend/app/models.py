"""SQLAlchemy ORM models for Kolibri."""
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, JSON, Boolean, Index
from sqlalchemy.orm import relationship
from app.database import Base


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
    version = Column(Integer, default=1)
    status = Column(String, default="draft")
    title = Column(String, nullable=False)
    client = Column(String, default="")
    object_name = Column(String, default="")
    region = Column(String, default="")
    currency = Column(String, default="RUB")
    overhead_rate = Column(String, default="0")
    vat_rate = Column(String, default="20")
    subtotal = Column(String, default="0")
    overhead_amount = Column(String, default="0")
    vat_amount = Column(String, default="0")
    total = Column(String, default="0")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    sections = relationship("SectionDB", back_populates="estimate", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_estimates_status", "status"),
        Index("ix_estimates_created_at", "created_at"),
    )


class SectionDB(Base):
    __tablename__ = "sections"

    id = Column(String, primary_key=True)
    estimate_id = Column(String, ForeignKey("estimates.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    subtotal = Column(String, default="0")

    estimate = relationship("EstimateDB", back_populates="sections")
    positions = relationship("PositionDB", back_populates="section", cascade="all, delete-orphan")


class PositionDB(Base):
    __tablename__ = "positions"

    id = Column(String, primary_key=True)
    section_id = Column(String, ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    code = Column(String, default="")
    name = Column(String, nullable=False)
    unit = Column(String, default="шт")
    quantity = Column(String, default="0")
    price = Column(String, default="0")
    sum = Column(String, default="0")
    source = Column(String, default="")
    comment = Column(Text, default="")

    section = relationship("SectionDB", back_populates="positions")


class DocumentDB(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True)
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
