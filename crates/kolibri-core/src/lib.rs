use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::fmt;
use uuid::Uuid;

pub mod artifacts;
pub mod continuity;
pub mod envelope;
pub mod events;
pub mod learning;
pub mod models;
pub mod policy;
pub mod swarm;
pub mod wire;

pub use crate::artifacts::*;
pub use crate::continuity::*;
pub use crate::events::{subject_for, EventEnvelope, KolibriEvent};
pub use crate::learning::*;
pub use crate::models::{
    Artifact, CommandRun, ModelRun, PolicyDecision, SecretRef, SecretValue, Task, TaskRun,
};
pub use crate::swarm::*;
pub use crate::wire::*;

#[derive(Debug, Serialize, Deserialize, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TaskStatus {
    Submitted,
    Validated,
    Scheduled,
    Running,
    PostCheck,
    WaitingApproval,
    Canceled,
    Completed,
    Failed,
    Blocked,
    Audited,
}

#[derive(Debug, Serialize, Deserialize, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TaskStateTransition {
    Submit,
    Validate,
    Schedule,
    Start,
    PostCheck,
    RequireApproval,
    Approve,
    Reject,
    Complete,
    Fail,
    Block,
    Audit,
}

#[derive(Debug, Serialize, Deserialize, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TaskResult {
    Unknown,
    Approved,
    Rejected,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq, Default)]
pub struct TrustMetadata {
    pub trace_id: String,
    pub run_id: String,
    pub policy_id: String,
    pub approver: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct TaskEnvelope {
    pub task_id: Uuid,
    pub owner: String,
    pub kind: String,
    pub status: TaskStatus,
    pub payload: serde_json::Value,
    pub policy: serde_json::Value,
    pub sensitivity: String,
    pub requires_approval: bool,
    pub worker_id: Option<String>,
    pub trace_id: String,
    pub run_id: String,
    pub policy_id: String,
    pub trust: TrustMetadata,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl TaskEnvelope {
    pub fn new(
        owner: impl Into<String>,
        kind: impl Into<String>,
        payload: serde_json::Value,
        sensitivity: impl Into<String>,
    ) -> Self {
        let now = Utc::now();
        Self {
            task_id: Uuid::new_v4(),
            owner: owner.into(),
            kind: kind.into(),
            status: TaskStatus::Submitted,
            payload,
            policy: serde_json::json!({}),
            sensitivity: sensitivity.into(),
            requires_approval: false,
            worker_id: None,
            trace_id: String::new(),
            run_id: String::new(),
            policy_id: String::new(),
            trust: TrustMetadata::default(),
            created_at: now,
            updated_at: now,
        }
    }

    pub fn transition_to(&mut self, status: TaskStatus) {
        self.status = status;
        self.updated_at = Utc::now();
    }
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct HealthSnapshot {
    pub service: String,
    pub version: String,
    pub status: String,
    pub updated_at: DateTime<Utc>,
}

impl HealthSnapshot {
    pub fn ok(service: impl Into<String>, version: impl Into<String>) -> Self {
        Self {
            service: service.into(),
            version: version.into(),
            status: "ok".to_string(),
            updated_at: Utc::now(),
        }
    }
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ControlError {
    pub code: String,
    pub detail: String,
}

impl fmt::Display for ControlError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for ControlError {}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct TaskEvent {
    pub sequence: u64,
    pub task_id: Uuid,
    pub name: String,
    pub status: TaskStatus,
    pub detail: String,
    pub trace_id: String,
    pub occurred_at: DateTime<Utc>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct AuditRecord {
    pub task_id: Uuid,
    pub trace_id: String,
    pub run_id: String,
    pub event: String,
    pub actor: String,
    pub detail: String,
    pub created_at: DateTime<Utc>,
}
