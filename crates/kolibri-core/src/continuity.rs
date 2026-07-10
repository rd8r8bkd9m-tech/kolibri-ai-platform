use crate::wire::v1_schema_version;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use thiserror::Error;
use uuid::Uuid;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ProjectStatus {
    Active,
    Paused,
    Archived,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Project {
    pub id: Uuid,
    pub tenant_id: Uuid,
    pub name: String,
    pub slug: String,
    pub status: ProjectStatus,
    pub created_by: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum WorkstreamStatus {
    Planned,
    Active,
    Blocked,
    Completed,
    Archived,
}

impl WorkstreamStatus {
    pub fn can_resume_automatically(self) -> bool {
        matches!(self, Self::Planned | Self::Active | Self::Blocked)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Workstream {
    pub id: Uuid,
    pub project_id: Uuid,
    pub name: String,
    pub goal: String,
    pub status: WorkstreamStatus,
    pub active_plan_id: Option<Uuid>,
    pub active_task_id: Option<Uuid>,
    pub version: u64,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum BacklogStatus {
    Proposed,
    Ready,
    InProgress,
    Blocked,
    Completed,
    Cancelled,
}

impl BacklogStatus {
    pub fn is_actionable(self) -> bool {
        matches!(self, Self::Ready | Self::InProgress)
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum BacklogPriority {
    Critical,
    High,
    Normal,
    Low,
    Background,
}

impl BacklogPriority {
    fn rank(self) -> u8 {
        match self {
            Self::Critical => 0,
            Self::High => 1,
            Self::Normal => 2,
            Self::Low => 3,
            Self::Background => 4,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct BacklogItem {
    pub id: Uuid,
    pub project_id: Uuid,
    pub workstream_id: Option<Uuid>,
    pub title: String,
    pub goal: String,
    pub acceptance: Vec<String>,
    pub dependencies: Vec<Uuid>,
    pub priority: BacklogPriority,
    pub position: u64,
    pub status: BacklogStatus,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Decision {
    pub id: Uuid,
    pub project_id: Uuid,
    pub workstream_id: Option<Uuid>,
    pub question: String,
    pub decision: String,
    pub rationale: String,
    pub actor: String,
    pub supersedes: Option<Uuid>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ChannelSurface {
    Api,
    Web,
    MimoChat,
    MimoCode,
    Codex,
    Telegram,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ChannelBinding {
    pub id: Uuid,
    pub tenant_id: Uuid,
    pub project_id: Uuid,
    pub workstream_id: Uuid,
    pub surface: ChannelSurface,
    /// A stable hash or provider-issued opaque id. Raw cookies and credentials are forbidden.
    pub external_session_key: String,
    pub active: bool,
    pub created_at: DateTime<Utc>,
    pub last_seen_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CheckpointStatus {
    Open,
    Superseded,
    Completed,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ContinuationBlocker {
    pub code: String,
    pub detail: String,
    pub owner_action: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TestEvidence {
    pub command: String,
    pub status: String,
    pub artifact_id: Option<Uuid>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Checkpoint {
    #[serde(default = "v1_schema_version")]
    pub schema_version: u32,
    #[serde(default)]
    pub trace_id: String,
    #[serde(default)]
    pub idempotency_key: String,
    pub id: Uuid,
    pub project_id: Uuid,
    pub workstream_id: Uuid,
    pub sequence: u64,
    pub status: CheckpointStatus,
    pub active_plan_id: Option<Uuid>,
    pub active_plan_node_id: Option<Uuid>,
    pub active_task_id: Option<Uuid>,
    pub next_action: String,
    pub blockers: Vec<ContinuationBlocker>,
    pub branch: Option<String>,
    pub commit: Option<String>,
    pub dirty_tree_digest: Option<String>,
    pub tests: Vec<TestEvidence>,
    pub artifact_ids: Vec<Uuid>,
    pub context_digest: String,
    pub event_sequence: u64,
    pub created_by: String,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ContextPack {
    #[serde(default = "v1_schema_version")]
    pub schema_version: u32,
    #[serde(default)]
    pub trace_id: String,
    #[serde(default)]
    pub idempotency_key: String,
    pub project: Project,
    pub workstream: Option<Workstream>,
    pub checkpoint: Option<Checkpoint>,
    pub backlog: Vec<BacklogItem>,
    pub decisions: Vec<Decision>,
    pub generated_at: DateTime<Utc>,
    pub event_sequence: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ResumeRequest {
    pub tenant_id: Uuid,
    pub project_id: Option<Uuid>,
    pub explicit_workstream_id: Option<Uuid>,
    pub surface: Option<ChannelSurface>,
    pub external_session_key: Option<String>,
    pub create_new: bool,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ResumeSelectionReason {
    ExplicitWorkstream,
    ChannelBinding,
    LastActiveWorkstream,
    LatestOpenCheckpoint,
    ActionableBacklog,
    ExplicitNewProject,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ResumeSelection {
    pub reason: ResumeSelectionReason,
    pub project_id: Option<Uuid>,
    pub workstream_id: Option<Uuid>,
    pub checkpoint_id: Option<Uuid>,
    pub backlog_item_id: Option<Uuid>,
    pub create_new: bool,
}

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum ResumeError {
    #[error("explicit workstream is not visible in the requested tenant/project scope")]
    ExplicitWorkstreamNotFound,
    #[error("no resumable work exists; creating a new project requires create_new=true")]
    NoContinuation,
}

pub struct ResumeIndex<'a> {
    pub projects: &'a [Project],
    pub workstreams: &'a [Workstream],
    pub bindings: &'a [ChannelBinding],
    pub checkpoints: &'a [Checkpoint],
    pub backlog: &'a [BacklogItem],
}

fn latest_checkpoint_for(workstream_id: Uuid, checkpoints: &[Checkpoint]) -> Option<&Checkpoint> {
    checkpoints
        .iter()
        .filter(|checkpoint| {
            checkpoint.workstream_id == workstream_id && checkpoint.status == CheckpointStatus::Open
        })
        .max_by(|left, right| {
            left.sequence
                .cmp(&right.sequence)
                .then_with(|| left.created_at.cmp(&right.created_at))
                .then_with(|| right.id.cmp(&left.id))
        })
}

fn selection_for_workstream(
    reason: ResumeSelectionReason,
    workstream: &Workstream,
    checkpoints: &[Checkpoint],
) -> ResumeSelection {
    ResumeSelection {
        reason,
        project_id: Some(workstream.project_id),
        workstream_id: Some(workstream.id),
        checkpoint_id: latest_checkpoint_for(workstream.id, checkpoints).map(|item| item.id),
        backlog_item_id: None,
        create_new: false,
    }
}

/// Selects a continuation with stable ordering and without relying on provider session memory.
pub fn select_resume(
    request: &ResumeRequest,
    index: ResumeIndex<'_>,
) -> Result<ResumeSelection, ResumeError> {
    let visible_project = |project_id: Uuid| {
        index.projects.iter().any(|project| {
            project.id == project_id
                && project.tenant_id == request.tenant_id
                && project.status != ProjectStatus::Archived
                && request
                    .project_id
                    .is_none_or(|requested| requested == project.id)
        })
    };

    if let Some(explicit_id) = request.explicit_workstream_id {
        let workstream = index
            .workstreams
            .iter()
            .find(|item| {
                item.id == explicit_id
                    && item.status != WorkstreamStatus::Archived
                    && visible_project(item.project_id)
            })
            .ok_or(ResumeError::ExplicitWorkstreamNotFound)?;
        return Ok(selection_for_workstream(
            ResumeSelectionReason::ExplicitWorkstream,
            workstream,
            index.checkpoints,
        ));
    }

    if let (Some(surface), Some(external_session_key)) =
        (request.surface, request.external_session_key.as_deref())
    {
        if let Some(binding) = index
            .bindings
            .iter()
            .filter(|binding| {
                binding.active
                    && binding.tenant_id == request.tenant_id
                    && binding.surface == surface
                    && binding.external_session_key == external_session_key
                    && visible_project(binding.project_id)
            })
            .max_by(|left, right| {
                left.last_seen_at
                    .cmp(&right.last_seen_at)
                    .then_with(|| right.id.cmp(&left.id))
            })
        {
            if let Some(workstream) = index.workstreams.iter().find(|item| {
                item.id == binding.workstream_id && item.status != WorkstreamStatus::Archived
            }) {
                return Ok(selection_for_workstream(
                    ResumeSelectionReason::ChannelBinding,
                    workstream,
                    index.checkpoints,
                ));
            }
        }
    }

    if let Some(workstream) = index
        .workstreams
        .iter()
        .filter(|item| item.status == WorkstreamStatus::Active && visible_project(item.project_id))
        .max_by(|left, right| {
            left.updated_at
                .cmp(&right.updated_at)
                .then_with(|| right.id.cmp(&left.id))
        })
    {
        return Ok(selection_for_workstream(
            ResumeSelectionReason::LastActiveWorkstream,
            workstream,
            index.checkpoints,
        ));
    }

    if let Some(checkpoint) = index
        .checkpoints
        .iter()
        .filter(|checkpoint| {
            checkpoint.status == CheckpointStatus::Open
                && index.workstreams.iter().any(|workstream| {
                    workstream.id == checkpoint.workstream_id
                        && workstream.status.can_resume_automatically()
                        && visible_project(workstream.project_id)
                })
        })
        .max_by(|left, right| {
            left.event_sequence
                .cmp(&right.event_sequence)
                .then_with(|| left.sequence.cmp(&right.sequence))
                .then_with(|| left.created_at.cmp(&right.created_at))
                .then_with(|| right.id.cmp(&left.id))
        })
    {
        return Ok(ResumeSelection {
            reason: ResumeSelectionReason::LatestOpenCheckpoint,
            project_id: Some(checkpoint.project_id),
            workstream_id: Some(checkpoint.workstream_id),
            checkpoint_id: Some(checkpoint.id),
            backlog_item_id: None,
            create_new: false,
        });
    }

    if let Some(item) = index
        .backlog
        .iter()
        .filter(|item| item.status.is_actionable() && visible_project(item.project_id))
        .min_by(|left, right| {
            left.priority
                .rank()
                .cmp(&right.priority.rank())
                .then_with(|| left.position.cmp(&right.position))
                .then_with(|| left.created_at.cmp(&right.created_at))
                .then_with(|| left.id.cmp(&right.id))
        })
    {
        return Ok(ResumeSelection {
            reason: ResumeSelectionReason::ActionableBacklog,
            project_id: Some(item.project_id),
            workstream_id: item.workstream_id,
            checkpoint_id: item
                .workstream_id
                .and_then(|id| latest_checkpoint_for(id, index.checkpoints))
                .map(|checkpoint| checkpoint.id),
            backlog_item_id: Some(item.id),
            create_new: false,
        });
    }

    if request.create_new {
        return Ok(ResumeSelection {
            reason: ResumeSelectionReason::ExplicitNewProject,
            project_id: request.project_id,
            workstream_id: None,
            checkpoint_id: None,
            backlog_item_id: None,
            create_new: true,
        });
    }

    Err(ResumeError::NoContinuation)
}
