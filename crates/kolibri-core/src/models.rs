use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Node {
    pub id: Uuid,
    pub name: String,
    pub hostname: String,
    pub ip: String,
    pub region: String,
    pub status: String,
    pub capabilities: Vec<String>,
    pub last_seen_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Agent {
    pub id: Uuid,
    pub node_id: Uuid,
    pub name: String,
    pub kind: String,
    pub status: String,
    pub version: String,
    pub capabilities: Vec<String>,
    pub current_task_id: Option<Uuid>,
    pub last_heartbeat_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Task {
    pub id: Uuid,
    pub project_id: Option<Uuid>,
    pub title: String,
    pub description: String,
    pub status: String,
    pub priority: String,
    pub created_by: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TaskRun {
    pub id: Uuid,
    pub task_id: Uuid,
    pub agent_id: Uuid,
    pub node_id: Uuid,
    pub status: String,
    pub started_at: Option<DateTime<Utc>>,
    pub finished_at: Option<DateTime<Utc>>,
    pub exit_code: Option<i32>,
    pub error_summary: Option<String>,
    pub artifact_ids: Vec<Uuid>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CommandRun {
    pub id: Uuid,
    pub task_run_id: Uuid,
    pub command: String,
    pub cwd: Option<String>,
    pub sandbox_profile: String,
    pub status: String,
    pub exit_code: Option<i32>,
    pub stdout_ref: Option<String>,
    pub stderr_ref: Option<String>,
    pub started_at: Option<DateTime<Utc>>,
    pub finished_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Artifact {
    pub id: Uuid,
    pub task_run_id: Option<Uuid>,
    pub task_id: Option<Uuid>,
    pub artifact_type: String,
    pub name: String,
    pub path: String,
    pub sha256: String,
    pub size_bytes: Option<u64>,
    pub metadata_json: Value,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PolicyDecision {
    pub id: Uuid,
    pub task_id: Option<Uuid>,
    pub action: String,
    pub reason: String,
    pub approved: bool,
    pub approver: Option<String>,
    pub trace_id: String,
    pub created_at: DateTime<Utc>,
}

#[derive(Clone, Serialize, Deserialize, PartialEq)]
pub struct SecretRef {
    pub provider: String,
    pub path: String,
    pub version: Option<String>,
    pub scope: String,
}

impl std::fmt::Debug for SecretRef {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("SecretRef")
            .field("provider", &self.provider)
            .field("path", &"***".to_string())
            .field("version", &self.version)
            .field("scope", &self.scope)
            .finish()
    }
}

#[derive(Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SecretValue(String);

impl SecretValue {
    pub fn new(value: impl Into<String>) -> Self {
        Self(value.into())
    }

    pub fn expose(self) -> String {
        self.0
    }
}

impl std::fmt::Display for SecretValue {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "***")
    }
}

impl std::fmt::Debug for SecretValue {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "SecretValue(\"***\")")
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SandboxProfile {
    pub name: String,
    pub command_allowlist: Vec<String>,
    pub network_allowlist: Vec<String>,
    pub timeout_ms: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ModelProvider {
    pub id: String,
    pub base_url: Option<String>,
    pub auth_env: Option<String>,
    pub models: Vec<String>,
    pub free_api: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ModelRun {
    pub id: Uuid,
    pub task_id: Option<Uuid>,
    pub provider: String,
    pub model: String,
    pub input_tokens: Option<i32>,
    pub output_tokens: Option<i32>,
    pub cost_estimate: Option<f64>,
    pub latency_ms: Option<i64>,
    pub finish_reason: Option<String>,
    pub trace_id: String,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Error, Serialize, Deserialize)]
pub enum DomainError {
    #[error("validation failed: {0}")]
    ValidationError(String),
    #[error("not found: {0}")]
    NotFound(String),
    #[error("conflict: {0}")]
    Conflict(String),
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use serde_json::json;
    use uuid::Uuid;

    #[test]
    fn secret_ref_does_not_leak_path_in_debug() {
        let secret = SecretRef {
            provider: "vault".into(),
            path: "prod/mysql/password".into(),
            version: None,
            scope: "api".into(),
        };
        let debug = format!("{:?}", secret);
        assert!(debug.contains("***"));
        assert!(!debug.contains("prod/mysql/password"));
    }

    #[test]
    fn task_and_artifact_roundtrip_json() {
        let task = Task {
            id: Uuid::new_v4(),
            project_id: Some(Uuid::new_v4()),
            title: "build".into(),
            description: "foundation smoke".into(),
            status: "scheduled".into(),
            priority: "low".into(),
            created_by: "system".into(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
        };
        let json = serde_json::to_string(&task).unwrap();
        let decoded: Task = serde_json::from_str(&json).unwrap();
        assert_eq!(task.id, decoded.id);
    }

    #[test]
    fn event_payload_is_json_compatible() {
        let run = ModelRun {
            id: Uuid::new_v4(),
            task_id: Some(Uuid::new_v4()),
            provider: "mock".into(),
            model: "tiny".into(),
            input_tokens: Some(12),
            output_tokens: Some(3),
            cost_estimate: Some(0.00001),
            latency_ms: Some(20),
            finish_reason: Some("stop".into()),
            trace_id: "t1".into(),
            created_at: Utc::now(),
        };

        let raw = serde_json::to_value(&run).unwrap();
        assert_eq!(raw["provider"], json!("mock"));
    }
}
