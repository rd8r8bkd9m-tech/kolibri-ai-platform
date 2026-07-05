use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum KolibriEvent {
    NodeRegistered,
    NodeHeartbeat,
    NodeOffline,
    AgentEnrolled,
    AgentHeartbeat,
    AgentCapabilitiesUpdated,
    AgentStatusChanged,
    TaskCreated,
    TaskAssigned,
    TaskStarted,
    TaskProgress,
    TaskCompleted,
    TaskFailed,
    TaskCancelled,
    CommandStarted,
    CommandStdout,
    CommandStderr,
    CommandCompleted,
    CommandFailed,
    SandboxCreated,
    SandboxDestroyed,
    SandboxViolation,
    ArtifactCreated,
    ArtifactUploaded,
    PolicyEvaluated,
    SecretRequested,
    SecretDenied,
    SecretGranted,
    ModelRequested,
    ModelCompleted,
    ModelFailed,
    AuditRecorded,
}

impl KolibriEvent {
    pub fn as_str(&self) -> &'static str {
        match self {
            KolibriEvent::NodeRegistered => "node.registered",
            KolibriEvent::NodeHeartbeat => "node.heartbeat",
            KolibriEvent::NodeOffline => "node.offline",
            KolibriEvent::AgentEnrolled => "agent.enrolled",
            KolibriEvent::AgentHeartbeat => "agent.heartbeat",
            KolibriEvent::AgentCapabilitiesUpdated => "agent.capabilities.updated",
            KolibriEvent::AgentStatusChanged => "agent.status.changed",
            KolibriEvent::TaskCreated => "task.created",
            KolibriEvent::TaskAssigned => "task.assigned",
            KolibriEvent::TaskStarted => "task.started",
            KolibriEvent::TaskProgress => "task.progress",
            KolibriEvent::TaskCompleted => "task.completed",
            KolibriEvent::TaskFailed => "task.failed",
            KolibriEvent::TaskCancelled => "task.cancelled",
            KolibriEvent::CommandStarted => "command.started",
            KolibriEvent::CommandStdout => "command.stdout",
            KolibriEvent::CommandStderr => "command.stderr",
            KolibriEvent::CommandCompleted => "command.completed",
            KolibriEvent::CommandFailed => "command.failed",
            KolibriEvent::SandboxCreated => "sandbox.created",
            KolibriEvent::SandboxDestroyed => "sandbox.destroyed",
            KolibriEvent::SandboxViolation => "sandbox.violation",
            KolibriEvent::ArtifactCreated => "artifact.created",
            KolibriEvent::ArtifactUploaded => "artifact.uploaded",
            KolibriEvent::PolicyEvaluated => "policy.evaluated",
            KolibriEvent::SecretRequested => "secret.requested",
            KolibriEvent::SecretDenied => "secret.denied",
            KolibriEvent::SecretGranted => "secret.granted",
            KolibriEvent::ModelRequested => "model.requested",
            KolibriEvent::ModelCompleted => "model.completed",
            KolibriEvent::ModelFailed => "model.failed",
            KolibriEvent::AuditRecorded => "audit.recorded",
        }
    }

    pub fn subject(&self) -> &'static str {
        match self {
            KolibriEvent::NodeRegistered
            | KolibriEvent::NodeHeartbeat
            | KolibriEvent::NodeOffline => "kolibri.node",
            KolibriEvent::AgentEnrolled
            | KolibriEvent::AgentHeartbeat
            | KolibriEvent::AgentCapabilitiesUpdated
            | KolibriEvent::AgentStatusChanged => "kolibri.agent",
            KolibriEvent::TaskCreated
            | KolibriEvent::TaskAssigned
            | KolibriEvent::TaskStarted
            | KolibriEvent::TaskProgress
            | KolibriEvent::TaskCompleted
            | KolibriEvent::TaskFailed
            | KolibriEvent::TaskCancelled => "kolibri.task",
            KolibriEvent::CommandStarted
            | KolibriEvent::CommandStdout
            | KolibriEvent::CommandStderr
            | KolibriEvent::CommandCompleted
            | KolibriEvent::CommandFailed => "kolibri.command",
            KolibriEvent::SandboxCreated
            | KolibriEvent::SandboxDestroyed
            | KolibriEvent::SandboxViolation => "kolibri.sandbox",
            KolibriEvent::ArtifactCreated | KolibriEvent::ArtifactUploaded => "kolibri.artifact",
            KolibriEvent::PolicyEvaluated => "kolibri.policy",
            KolibriEvent::SecretRequested
            | KolibriEvent::SecretDenied
            | KolibriEvent::SecretGranted => "kolibri.secret",
            KolibriEvent::ModelRequested
            | KolibriEvent::ModelCompleted
            | KolibriEvent::ModelFailed => "kolibri.model",
            KolibriEvent::AuditRecorded => "kolibri.audit",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventEnvelope {
    pub id: Uuid,
    pub stream: String,
    pub subject: String,
    pub event_type: String,
    pub aggregate_id: Option<Uuid>,
    pub payload_json: Value,
    pub trace_id: Option<String>,
    pub correlation_id: Option<String>,
    pub actor: Option<String>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone)]
pub struct NatsJetStreamConfig {
    pub stream: String,
    pub subject: String,
}

pub fn subject_for(event_type: &str) -> &'static str {
    match event_type {
        e if e.starts_with("node.") => "kolibri.node",
        e if e.starts_with("agent.") => "kolibri.agent",
        e if e.starts_with("task.") => "kolibri.task",
        e if e.starts_with("command.") => "kolibri.command",
        e if e.starts_with("sandbox.") => "kolibri.sandbox",
        e if e.starts_with("artifact.") => "kolibri.artifact",
        e if e.starts_with("policy.") => "kolibri.policy",
        e if e.starts_with("secret.") => "kolibri.secret",
        e if e.starts_with("model.") => "kolibri.model",
        e if e.starts_with("audit.") => "kolibri.audit",
        _ => "kolibri.events",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn events_are_mapped_to_subjects() {
        assert_eq!(subject_for("task.created"), "kolibri.task");
        assert_eq!(subject_for("agent.enrolled"), "kolibri.agent");
        assert_eq!(subject_for("command.failed"), "kolibri.command");
        assert_eq!(subject_for("sandbox.violation"), "kolibri.sandbox");
    }

    #[test]
    fn event_enum_matches_wire_names() {
        assert_eq!(KolibriEvent::TaskCompleted.as_str(), "task.completed");
        assert_eq!(KolibriEvent::ModelFailed.subject(), "kolibri.model");
    }
}
