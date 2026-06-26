"""Pydantic v2 schemas for Kolibri API."""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime
from enum import Enum


class EstimateStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    APPROVED = "approved"
    ARCHIVED = "archived"


class DocumentType(str, Enum):
    CONTRACT = "contract"
    ACT = "act"
    LETTER = "letter"
    PROPOSAL = "proposal"
    REPORT = "report"
    MEMO = "memo"
    CUSTOM = "custom"


class NodeStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DRAINING = "draining"
    QUARANTINED = "quarantined"
    OFFLINE = "offline"


class TaskState(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    ASSIGNED = "assigned"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Position & Section
# ---------------------------------------------------------------------------

class PositionCreate(BaseModel):
    code: str
    name: str
    unit: str
    quantity: str
    price: str
    source: str = ""
    comment: str = ""


class PositionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    code: str
    name: str
    unit: str
    quantity: str
    price: str
    sum: str = Field(alias="sum_")
    source: str = ""
    comment: str = ""


class SectionCreate(BaseModel):
    title: str
    positions: List[PositionCreate] = []


class SectionResponse(BaseModel):
    id: str
    title: str
    subtotal: str
    positions: List[PositionResponse] = []


# ---------------------------------------------------------------------------
# Estimate
# ---------------------------------------------------------------------------

class EstimateCreate(BaseModel):
    title: str
    client: str = ""
    object_name: str = ""
    region: str = ""
    currency: str = "RUB"
    overhead_rate: str = "0"
    vat_rate: str = "20"
    sections: List[SectionCreate] = []


class EstimateUpdate(BaseModel):
    title: Optional[str] = None
    client: Optional[str] = None
    object_name: Optional[str] = None
    region: Optional[str] = None
    currency: Optional[str] = None
    overhead_rate: Optional[str] = None
    vat_rate: Optional[str] = None
    status: Optional[EstimateStatus] = None
    sections: Optional[List[SectionCreate]] = None


class EstimateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version: int
    status: EstimateStatus
    title: str
    client: str
    object_name: str
    region: str
    currency: str
    overhead_rate: str
    vat_rate: str
    subtotal: str
    overhead_amount: str
    vat_amount: str
    total: str
    sections: List[SectionResponse] = []
    created_at: datetime
    updated_at: datetime


class EstimateListResponse(BaseModel):
    items: List[EstimateResponse]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

class DocumentCreate(BaseModel):
    title: str
    type: DocumentType = DocumentType.CUSTOM
    client: str = ""
    project: str = ""
    content: str = ""
    variables: dict = {}
    template: str = ""


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    type: Optional[DocumentType] = None
    client: Optional[str] = None
    project: Optional[str] = None
    content: Optional[str] = None
    variables: Optional[dict] = None
    template: Optional[str] = None
    status: Optional[str] = None


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    type: DocumentType
    status: str
    client: str
    project: str
    content: str
    variables: dict
    template: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

class LibraryItemType(str, Enum):
    ESTIMATE = "estimate"
    DOCUMENT = "document"
    PDF = "pdf"
    TABLE = "table"
    MEDIA = "media"
    REPORT = "report"
    AGENT_RESULT = "agent_result"


class LibraryItemResponse(BaseModel):
    id: str
    title: str
    item_type: LibraryItemType
    source_id: str
    source_type: str
    status: str
    client: str
    project: str
    file_size: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class AgentResponse(BaseModel):
    id: str
    name: str
    role: str
    status: str
    node_id: Optional[str]
    current_task: Optional[str]
    progress: int
    model: Optional[str]
    capabilities: dict
    cost_accumulated: str
    heartbeat_at: Optional[datetime]


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

class NodeResponse(BaseModel):
    id: str
    name: str
    region: str
    ip_address: str
    status: NodeStatus
    cpu_percent: str
    ram_percent: str
    disk_percent: str
    network_mbps: str
    agent_count: int
    task_count: int
    ping_ms: int
    max_agents: int
    capabilities: dict


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

class TaskResponse(BaseModel):
    id: str
    workflow_id: str
    state: TaskState
    priority: int
    owner_agent_id: Optional[str]
    node_id: Optional[str]
    budget_limit: Optional[str]
    attempts: int
    max_retries: int
    result: Optional[dict]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

class PDFGenerateRequest(BaseModel):
    html_content: str
    title: str = "Документ"


class PDFGenerateResponse(BaseModel):
    pdf_base64: str
    filename: str
    page_count: int
    size_bytes: int


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    timestamp: datetime
