use serde::{Deserialize, Serialize};

pub const PROTOCOL_V1: &str = "v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum CleanupCategory {
    Build,
    Cache,
    Log,
    StoppedContainer,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum OperationKind {
    Cleanup,
    Quarantine,
    Restore,
    Purge,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum RootKind {
    Build,
    Cache,
    Log,
    StoppedContainer,
    ProjectSource,
    ProjectQuarantine,
}

impl RootKind {
    pub fn cleanup_category(self) -> Option<CleanupCategory> {
        match self {
            Self::Build => Some(CleanupCategory::Build),
            Self::Cache => Some(CleanupCategory::Cache),
            Self::Log => Some(CleanupCategory::Log),
            Self::StoppedContainer => Some(CleanupCategory::StoppedContainer),
            Self::ProjectSource | Self::ProjectQuarantine => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum ProtectionScope {
    ActiveRelease,
    CurrentSymlink,
    PrimaryDatabase,
    DurableVolumes,
    AgentRuntimeState,
}

pub const REQUIRED_PROTECTION_SCOPES: [ProtectionScope; 5] = [
    ProtectionScope::ActiveRelease,
    ProtectionScope::CurrentSymlink,
    ProtectionScope::PrimaryDatabase,
    ProtectionScope::DurableVolumes,
    ProtectionScope::AgentRuntimeState,
];

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RequestEnvelope {
    pub protocol_version: String,
    pub request_id: String,
    pub command: Command,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "kebab-case", deny_unknown_fields)]
pub enum Command {
    Inventory {
        node_id: String,
    },
    Preview {
        node_id: String,
        category: Option<CleanupCategory>,
        operation_kind: OperationKind,
        project_id: Option<String>,
        quarantine_id: Option<String>,
    },
    Execute {
        operation_id: String,
        preview_ref: String,
        node_generation: String,
        project_id: Option<String>,
        quarantine_id: Option<String>,
    },
    Status {
        operation_id: String,
    },
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ResponseEnvelope<T: Serialize> {
    pub protocol_version: &'static str,
    pub request_id: String,
    pub ok: bool,
    pub result: T,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ErrorEnvelope<E: Serialize> {
    pub protocol_version: &'static str,
    pub request_id: String,
    pub ok: bool,
    pub error: E,
}

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "kind", content = "data", rename_all = "kebab-case")]
pub enum CommandResult {
    Inventory(InventoryResult),
    Preview(PreviewResult),
    Operation(OperationResult),
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CategoryInventory {
    pub category: CleanupCategory,
    pub reclaimable_bytes: u64,
    pub item_count: u64,
    pub oldest_item_at: Option<u64>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectCandidateView {
    pub project_id: String,
    pub display_name: String,
    pub size_bytes: u64,
    pub last_modified_at: u64,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct QuarantineView {
    pub quarantine_id: String,
    pub project_id: String,
    pub status: QuarantineStatus,
    pub size_bytes: u64,
    pub quarantined_at: u64,
    pub purge_eligible_at: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum QuarantineStatus {
    Retained,
    Restored,
    Purged,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct InventoryResult {
    pub node_id: String,
    pub execute_enabled: bool,
    pub capacity_bytes: u64,
    pub used_bytes: u64,
    pub free_bytes: u64,
    pub scanned_at: u64,
    pub generation: String,
    pub policy_digest: String,
    pub capacity_segments: Vec<CapacitySegment>,
    pub categories: Vec<CategoryInventory>,
    pub project_candidates: Vec<ProjectCandidateView>,
    pub quarantines: Vec<QuarantineView>,
    pub blocked_item_count: u64,
    pub guarded_scopes: Vec<ProtectionScope>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CapacitySegment {
    pub kind: CapacitySegmentKind,
    pub display_name: String,
    pub display_size: String,
    pub capacity_bytes: u64,
    pub read_only: bool,
}

#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum CapacitySegmentKind {
    RootLv,
    VgUnallocated,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PreviewResult {
    pub executor_preview_ref: String,
    pub node_generation: String,
    pub candidate_count: u64,
    pub reclaimable_bytes: u64,
    pub protected_item_count: u64,
    pub guarded_scopes: Vec<ProtectionScope>,
    pub confirmation: &'static str,
    pub expires_at: u64,
    pub replayed: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum OperationStatus {
    Applying,
    Succeeded,
    Failed,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OperationResult {
    pub operation_id: String,
    pub preview_ref: String,
    pub status: OperationStatus,
    pub affected_item_count: u64,
    pub reclaimed_bytes: u64,
    pub protected_item_count: u64,
    pub guarded_scopes: Vec<ProtectionScope>,
    pub node_generation: String,
    pub quarantine_id: Option<String>,
    pub error_code: Option<String>,
    pub created_at: u64,
    pub completed_at: Option<u64>,
    pub replayed: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct CandidateManifest {
    pub root_id: String,
    pub relative_name: String,
    pub size_bytes: u64,
    pub modified_at: u64,
    pub device: u64,
    pub inode: u64,
    pub tree_digest: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct PreviewManifest {
    pub operation_kind: OperationKind,
    pub category: Option<CleanupCategory>,
    pub project_id: Option<String>,
    pub quarantine_id: Option<String>,
    pub candidates: Vec<CandidateManifest>,
    pub protected_item_count: u64,
}

impl OperationKind {
    pub fn confirmation(self) -> &'static str {
        match self {
            Self::Cleanup => "CLEANUP",
            Self::Quarantine => "QUARANTINE",
            Self::Restore => "RESTORE",
            Self::Purge => "PURGE",
        }
    }
}
