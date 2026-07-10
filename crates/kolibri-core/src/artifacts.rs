use crate::models::Artifact;
use crate::wire::v1_schema_version;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ArtifactKind {
    WebsiteBundle,
    WebAppBundle,
    PreviewSnapshot,
    PreviewRecording,
    Pdf,
    PdfX,
    Xlsx,
    Docx,
    Image,
    Audio,
    Video,
    CodeSnapshot,
    DiffPatch,
    GitCommit,
    GitPullRequest,
    TerminalTranscript,
    Log,
    TestReport,
    EstimateJson,
    EstimateXlsx,
    EstimatePdf,
    EstimateAudit,
    Manifest,
    Provenance,
    Canvas,
}

/// Adds tenant, lineage, storage, and provenance fields without changing the legacy Artifact API.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ArtifactRecord {
    pub artifact: Artifact,
    #[serde(default = "v1_schema_version")]
    pub schema_version: u32,
    #[serde(default)]
    pub trace_id: String,
    #[serde(default)]
    pub idempotency_key: String,
    pub tenant_id: Uuid,
    pub project_id: Uuid,
    pub workstream_id: Option<Uuid>,
    pub execution_id: Option<Uuid>,
    pub kind: ArtifactKind,
    pub mime_type: String,
    pub storage_ref: String,
    pub sensitivity: String,
    pub retention_class: String,
    pub provenance_json: Value,
    pub lineage: Vec<Uuid>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CanvasKind {
    Document,
    Dashboard,
    Website,
    WebApp,
    Diagram,
    Estimate,
    Presentation,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CanvasArtifact {
    pub id: Uuid,
    pub artifact_id: Uuid,
    #[serde(default = "v1_schema_version")]
    pub schema_version: u32,
    #[serde(default)]
    pub trace_id: String,
    #[serde(default)]
    pub idempotency_key: String,
    pub kind: CanvasKind,
    pub document_tree: Value,
    pub data_bindings: Value,
    pub asset_artifact_ids: Vec<Uuid>,
    pub render_hints: Value,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PluginSignature {
    pub algorithm: String,
    pub signer: String,
    pub checksum_sha256: String,
    pub signature: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RendererPlugin {
    pub id: String,
    pub version: String,
    pub input_kinds: Vec<CanvasKind>,
    pub output_artifact_kinds: Vec<ArtifactKind>,
    pub output_mime_types: Vec<String>,
    pub sandbox_profile: String,
    pub deterministic: bool,
    pub signature: PluginSignature,
    pub enabled: bool,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum PreviewRuntimeKind {
    StaticWebsite,
    WebApp,
    Container,
    IosSimulator,
    MacosApp,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum PreviewRuntimeStatus {
    Requested,
    Starting,
    Ready,
    Stopped,
    Expired,
    Failed,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RuntimeQuota {
    pub cpu_millis: u32,
    pub memory_bytes: u64,
    pub disk_bytes: u64,
    pub max_seconds: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PreviewRuntime {
    #[serde(default = "v1_schema_version")]
    pub schema_version: u32,
    #[serde(default)]
    pub trace_id: String,
    #[serde(default)]
    pub idempotency_key: String,
    pub id: Uuid,
    pub project_id: Uuid,
    pub workstream_id: Uuid,
    pub source_artifact_id: Uuid,
    pub runtime_kind: PreviewRuntimeKind,
    pub status: PreviewRuntimeStatus,
    pub sandbox_profile: String,
    pub quota: RuntimeQuota,
    pub preview_url: Option<String>,
    pub stream_id: Option<String>,
    pub evidence_artifact_ids: Vec<Uuid>,
    pub created_at: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum BrowserSessionStatus {
    Requested,
    Starting,
    Ready,
    Running,
    Completed,
    Expired,
    Failed,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct BrowserNetworkPolicy {
    pub allowed_origins: Vec<String>,
    pub allowed_hosts: Vec<String>,
    pub deny_private_networks: bool,
    pub downloads_enabled: bool,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum BrowserActionKind {
    Navigate,
    Click,
    Type,
    Screenshot,
    Assert,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BrowserAction {
    pub id: Uuid,
    pub sequence: u64,
    pub kind: BrowserActionKind,
    pub input: Value,
    pub result: Option<Value>,
    pub evidence_artifact_id: Option<Uuid>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BrowserSession {
    #[serde(default = "v1_schema_version")]
    pub schema_version: u32,
    #[serde(default)]
    pub trace_id: String,
    #[serde(default)]
    pub idempotency_key: String,
    pub id: Uuid,
    pub preview_runtime_id: Uuid,
    pub status: BrowserSessionStatus,
    pub sandbox_profile: String,
    pub network_policy: BrowserNetworkPolicy,
    pub stream_id: Option<String>,
    pub actions: Vec<BrowserAction>,
    pub evidence_artifact_ids: Vec<Uuid>,
    pub created_at: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum WorkflowTriggerKind {
    Manual,
    Schedule,
    Event,
    Webhook,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WorkflowTrigger {
    pub kind: WorkflowTriggerKind,
    pub configuration: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WorkflowStep {
    pub id: Uuid,
    pub capability: String,
    pub dependencies: Vec<Uuid>,
    pub input_mapping: Value,
    pub output_mapping: Value,
    pub approval_required: bool,
    pub max_attempts: u32,
    pub idempotency_key_template: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AutomationWorkflow {
    #[serde(default = "v1_schema_version")]
    pub schema_version: u32,
    #[serde(default)]
    pub trace_id: String,
    #[serde(default)]
    pub idempotency_key: String,
    pub id: Uuid,
    pub tenant_id: Uuid,
    pub project_id: Uuid,
    pub workstream_id: Option<Uuid>,
    pub name: String,
    pub version: u64,
    pub enabled: bool,
    pub triggers: Vec<WorkflowTrigger>,
    pub steps: Vec<WorkflowStep>,
    pub created_by: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}
