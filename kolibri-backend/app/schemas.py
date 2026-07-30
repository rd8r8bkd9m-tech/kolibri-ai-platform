"""Pydantic v2 schemas for Kolibri API."""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal
from datetime import datetime
from enum import Enum

from app.estimate_evidence import PriceEvidenceRecord


class EstimateStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    APPROVED = "approved"
    ARCHIVED = "archived"


class EstimateTruthStatus(str, Enum):
    NEEDS_INPUT = "needs_input"
    PRELIMINARY = "preliminary"
    SOURCE_BACKED = "source_backed"
    VERIFIED = "verified"


class EstimateScopeStatus(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"


class EstimateTaxRegime(str, Enum):
    UNSPECIFIED = "unspecified"
    NPD = "npd"
    USN_EXEMPT = "usn_exempt"
    USN_VAT5 = "usn_vat5"
    USN_VAT7 = "usn_vat7"
    OSNO_VAT22 = "osno_vat22"


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
    price_evidence: List[PriceEvidenceRecord] = Field(default_factory=list, max_length=50)
    comment: str = ""


class PositionResponse(BaseModel):
    id: str
    code: str
    name: str
    unit: str
    quantity: str
    price: str
    sum: str
    source: str = ""
    price_evidence: List[PriceEvidenceRecord] = Field(default_factory=list, max_length=50)
    comment: str = ""


class SectionCreate(BaseModel):
    title: str
    positions: List[PositionCreate] = Field(default_factory=list)


class SectionResponse(BaseModel):
    id: str
    title: str
    subtotal: str
    positions: List[PositionResponse] = Field(default_factory=list)


class EstimateEvidenceIssue(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    position_code: str = Field(default="", max_length=80)
    message: str = Field(min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# Estimate
# ---------------------------------------------------------------------------

class EstimateCreate(BaseModel):
    title: str
    project_id: Optional[str] = Field(default=None, min_length=1, max_length=160)
    client: str = ""
    object_name: str = ""
    region: str = ""
    price_as_of: Optional[str] = None
    currency: str = "RUB"
    overhead_rate: str = "0"
    profit_rate: str = "0"
    contingency_rate: str = "0"
    general_contractor_rate: str = "0"
    discount_rate: str = "0"
    vat_rate: str = "22"
    tax_regime: EstimateTaxRegime = EstimateTaxRegime.UNSPECIFIED
    estimate_status: Optional[EstimateTruthStatus] = None
    pricing_status: Optional[EstimateTruthStatus] = None
    scope_status: EstimateScopeStatus = EstimateScopeStatus.UNVERIFIED
    source_note: str = ""
    assumptions: List[str] = Field(default_factory=list, max_length=100)
    questions: List[str] = Field(default_factory=list, max_length=100)
    price_sources: List[PriceEvidenceRecord] = Field(default_factory=list, max_length=5_000)
    evidence_issues: List[EstimateEvidenceIssue] = Field(default_factory=list, max_length=200)
    technology_card: Optional[dict] = None
    procurement_report: Optional[dict] = None
    sections: List[SectionCreate] = Field(default_factory=list)


class EstimateUpdate(BaseModel):
    version: Optional[int] = Field(default=None, ge=1)
    title: Optional[str] = None
    client: Optional[str] = None
    object_name: Optional[str] = None
    region: Optional[str] = None
    price_as_of: Optional[str] = None
    currency: Optional[str] = None
    overhead_rate: Optional[str] = None
    profit_rate: Optional[str] = None
    contingency_rate: Optional[str] = None
    general_contractor_rate: Optional[str] = None
    discount_rate: Optional[str] = None
    vat_rate: Optional[str] = None
    tax_regime: Optional[EstimateTaxRegime] = None
    status: Optional[EstimateStatus] = None
    estimate_status: Optional[EstimateTruthStatus] = None
    pricing_status: Optional[EstimateTruthStatus] = None
    scope_status: Optional[EstimateScopeStatus] = None
    source_note: Optional[str] = None
    assumptions: Optional[List[str]] = Field(default=None, max_length=100)
    questions: Optional[List[str]] = Field(default=None, max_length=100)
    price_sources: Optional[List[PriceEvidenceRecord]] = Field(default=None, max_length=5_000)
    evidence_issues: Optional[List[EstimateEvidenceIssue]] = Field(default=None, max_length=200)
    technology_card: Optional[dict] = None
    procurement_report: Optional[dict] = None
    sections: Optional[List[SectionCreate]] = None


class EstimateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: Optional[str] = None
    case_id: Optional[str] = None
    version: int
    status: EstimateStatus
    estimate_status: EstimateTruthStatus
    pricing_status: EstimateTruthStatus
    scope_status: EstimateScopeStatus
    source_note: str
    assumptions: List[str] = Field(default_factory=list)
    questions: List[str] = Field(default_factory=list)
    price_sources: List[PriceEvidenceRecord] = Field(default_factory=list)
    evidence_issues: List[EstimateEvidenceIssue] = Field(default_factory=list)
    client_record_id: Optional[str] = None
    object_record_id: Optional[str] = None
    title: str
    client: str
    object_name: str
    region: str
    price_as_of: Optional[str] = None
    currency: str
    overhead_rate: str
    profit_rate: str
    contingency_rate: str
    general_contractor_rate: str
    discount_rate: str
    vat_rate: str
    tax_regime: EstimateTaxRegime
    subtotal: str
    overhead_amount: str
    profit_amount: str
    contingency_amount: str
    general_contractor_amount: str
    discount_amount: str
    vat_amount: str
    total: str
    sections: List[SectionResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class EstimateListResponse(BaseModel):
    items: List[EstimateResponse]
    total: int
    page: int
    page_size: int


class EstimateRevisionSummary(BaseModel):
    id: str
    estimate_id: str
    version: int
    title: str
    status: EstimateStatus
    estimate_status: EstimateTruthStatus
    pricing_status: EstimateTruthStatus
    total: str
    created_at: datetime


class EstimateRevisionResponse(BaseModel):
    id: str
    estimate_id: str
    version: int
    snapshot: EstimateResponse
    created_at: datetime


class EstimateRevisionListResponse(BaseModel):
    items: List[EstimateRevisionSummary]
    total: int


class EstimateTechnologyCardResponse(BaseModel):
    estimate_id: str
    version: int
    technology_card: dict
    procurement_report: Optional[dict] = None


class EstimateCommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=2_000)
    version: int = Field(ge=1)


class EstimateCommandResponse(BaseModel):
    applied: bool
    message: str
    operations: List[dict] = Field(default_factory=list)
    estimate: EstimateResponse


class WorkCatalogItem(BaseModel):
    id: str
    name: str
    unit: str
    category: str
    latest_price: str
    price_source: str = "estimate"
    price_observed_at: Optional[datetime] = None
    usage_count: int
    status: str
    source_estimate_id: Optional[str] = None
    source_version: int
    updated_at: datetime


class WorkCatalogListResponse(BaseModel):
    items: List[WorkCatalogItem]
    total: int
    page: int
    page_size: int


class WorkCatalogUpdate(BaseModel):
    latest_price: str = Field(min_length=1, max_length=40)
    price_source: str = Field(default="manual", min_length=1, max_length=200)


class TechnologyCatalogItem(BaseModel):
    id: str
    content_sha256: str
    title: str
    object_type: str
    card: dict
    usage_count: int
    status: str
    source_estimate_id: Optional[str] = None
    source_version: int
    updated_at: datetime


class TechnologyCatalogListResponse(BaseModel):
    items: List[TechnologyCatalogItem]
    total: int
    page: int
    page_size: int


class ClientDirectoryItem(BaseModel):
    id: str
    name: str
    phone: str = ""
    email: str = ""
    inn: str = ""
    kpp: str = ""
    address: str = ""
    contact_person: str = ""
    source: str
    created_at: datetime
    updated_at: datetime


class ClientDirectoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    phone: str = Field(default="", max_length=80)
    email: str = Field(default="", max_length=320)
    inn: str = Field(default="", max_length=20)
    kpp: str = Field(default="", max_length=20)
    address: str = Field(default="", max_length=1_000)
    contact_person: str = Field(default="", max_length=300)


class ClientDirectoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=500)
    phone: Optional[str] = Field(default=None, max_length=80)
    email: Optional[str] = Field(default=None, max_length=320)
    inn: Optional[str] = Field(default=None, max_length=20)
    kpp: Optional[str] = Field(default=None, max_length=20)
    address: Optional[str] = Field(default=None, max_length=1_000)
    contact_person: Optional[str] = Field(default=None, max_length=300)


class ClientDirectoryListResponse(BaseModel):
    items: List[ClientDirectoryItem]
    total: int
    page: int
    page_size: int


class ConstructionObjectDirectoryItem(BaseModel):
    id: str
    client_id: Optional[str] = None
    name: str
    address: str = ""
    region: str = ""
    source: str
    created_at: datetime
    updated_at: datetime


class ConstructionObjectDirectoryCreate(BaseModel):
    name: str = Field(default="Объект без названия", min_length=1, max_length=500)
    client_id: Optional[str] = None
    address: str = Field(default="", max_length=1_000)
    region: str = Field(default="", max_length=320)


class ConstructionObjectDirectoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=500)
    client_id: Optional[str] = None
    address: Optional[str] = Field(default=None, max_length=1_000)
    region: Optional[str] = Field(default=None, max_length=320)


class ConstructionObjectDirectoryListResponse(BaseModel):
    items: List[ConstructionObjectDirectoryItem]
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
    estimate_id: Optional[str] = None


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    type: Optional[DocumentType] = None
    client: Optional[str] = None
    project: Optional[str] = None
    content: Optional[str] = None
    variables: Optional[dict] = None
    template: Optional[str] = None
    status: Optional[str] = None
    estimate_id: Optional[str] = None


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
    estimate_id: Optional[str] = None
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
    release_id: str
    database: str
    timestamp: datetime


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str = "user"
    content: str


class ChatPolicy(BaseModel):
    mode: Literal["fast", "deep"] = "fast"
    reasoning_effort: Literal["low", "high"] = "low"
    tool_choice: Literal["auto"] = "auto"
    background: bool = False
    allowed_capabilities: List[str] = Field(default_factory=list, max_length=32)


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    context: Optional[str] = None
    project_id: Optional[str] = None
    attachments: List[dict] = Field(default_factory=list, max_length=32)
    previous_response_id: Optional[str] = None
    background: bool = False
    policy: Optional[ChatPolicy] = None


class ChatAction(BaseModel):
    type: str
    label: str
    data: Optional[dict] = None


class ChatSource(BaseModel):
    citation: int
    title: str
    url: str
    snippet: str = ""
    retrieved_at: str


class ChatResponse(BaseModel):
    content: str
    reasoning: str = ""
    actions: List[ChatAction] = Field(default_factory=list)
    status: str = "idle"
    provider: str = ""
    model: str = ""
    speed_ms: int = 0
    fallback_used: bool = False
    error_code: Optional[str] = None
    recoverable: bool = False
    capability: Optional[str] = None
    sources: List[ChatSource] = Field(default_factory=list)
    truth: dict = Field(default_factory=dict)
    response_id: Optional[str] = None
    tool_events: List[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class UserRegister(BaseModel):
    email: str
    name: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
