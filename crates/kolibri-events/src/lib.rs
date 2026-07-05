use chrono::Utc;
use kolibri_core::events::{
    subject_for as core_subject_for, EventEnvelope as CoreEventEnvelope, KolibriEvent,
};
use serde::{Deserialize, Serialize};

pub use kolibri_core::events::subject_for as event_subject_for;

pub const KOLIBRI_STREAM_TASKS: &str = "KOLIBRI_TASKS";
pub const KOLIBRI_STREAM_EVENTS: &str = "KOLIBRI_EVENTS";
pub const KOLIBRI_STREAM_AUDIT: &str = "KOLIBRI_AUDIT";
pub const KOLIBRI_STREAM_LOGS: &str = "KOLIBRI_LOGS";

#[derive(Debug, Serialize, Deserialize, Clone, Copy, PartialEq, Eq)]
pub enum Stream {
    Events,
    Tasks,
    Audit,
    Logs,
}

impl Stream {
    pub fn nats_stream(self) -> &'static str {
        match self {
            Stream::Events => KOLIBRI_STREAM_EVENTS,
            Stream::Tasks => KOLIBRI_STREAM_TASKS,
            Stream::Audit => KOLIBRI_STREAM_AUDIT,
            Stream::Logs => KOLIBRI_STREAM_LOGS,
        }
    }
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct EventEnvelope {
    #[serde(flatten)]
    pub inner: CoreEventEnvelope,
}

impl EventEnvelope {
    pub fn new(
        event: KolibriEvent,
        aggregate_id: Option<uuid::Uuid>,
        actor: Option<String>,
    ) -> Self {
        Self {
            inner: CoreEventEnvelope {
                id: uuid::Uuid::new_v4(),
                stream: "kolibri-events".to_string(),
                subject: event.subject().to_string(),
                event_type: event.as_str().to_string(),
                aggregate_id,
                payload_json: serde_json::json!({}),
                trace_id: None,
                correlation_id: None,
                actor,
                created_at: Utc::now(),
            },
        }
    }

    pub fn with_payload<T: Serialize>(mut self, payload: &T) -> Result<Self, serde_json::Error> {
        self.inner.payload_json = serde_json::to_value(payload)?;
        Ok(self)
    }

    pub fn set_trace(mut self, trace_id: impl Into<String>) -> Self {
        self.inner.trace_id = Some(trace_id.into());
        self
    }

    pub fn set_correlation(mut self, correlation_id: impl Into<String>) -> Self {
        self.inner.correlation_id = Some(correlation_id.into());
        self
    }

    pub fn subject(&self) -> &str {
        &self.inner.subject
    }
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
pub struct EventTypeValidation {
    pub event_type: String,
    pub stream: String,
}

impl EventTypeValidation {
    pub fn validate(event_type: impl AsRef<str>) -> Result<Self, EventTypeError> {
        let event_type = event_type.as_ref();
        if event_type.is_empty() {
            return Err(EventTypeError::EmptyEventType);
        }
        if event_type.contains(' ') || !event_type.contains('.') {
            return Err(EventTypeError::InvalidFormat(event_type.to_string()));
        }
        Ok(Self {
            event_type: event_type.to_string(),
            stream: core_subject_for(event_type).to_string(),
        })
    }
}

#[derive(Debug, thiserror::Error)]
pub enum EventTypeError {
    #[error("event_type cannot be empty")]
    EmptyEventType,
    #[error("invalid event_type: {0}")]
    InvalidFormat(String),
}

pub fn validate_trace_id(trace_id: Option<&str>) -> bool {
    match trace_id {
        Some(value) => !value.trim().is_empty(),
        None => true,
    }
}

#[derive(Debug, Serialize, Deserialize)]
pub struct KolibriEventParseError(pub String);

pub fn parse_wire_event(
    event_type: impl AsRef<str>,
) -> Result<KolibriEvent, KolibriEventParseError> {
    let event_type = event_type.as_ref();
    let as_type = match event_type {
        "node.registered" => KolibriEvent::NodeRegistered,
        "node.heartbeat" => KolibriEvent::NodeHeartbeat,
        "node.offline" => KolibriEvent::NodeOffline,
        "agent.enrolled" => KolibriEvent::AgentEnrolled,
        "agent.heartbeat" => KolibriEvent::AgentHeartbeat,
        "agent.capabilities.updated" => KolibriEvent::AgentCapabilitiesUpdated,
        "agent.status.changed" => KolibriEvent::AgentStatusChanged,
        "task.created" => KolibriEvent::TaskCreated,
        "task.assigned" => KolibriEvent::TaskAssigned,
        "task.started" => KolibriEvent::TaskStarted,
        "task.progress" => KolibriEvent::TaskProgress,
        "task.completed" => KolibriEvent::TaskCompleted,
        "task.failed" => KolibriEvent::TaskFailed,
        "task.cancelled" => KolibriEvent::TaskCancelled,
        "command.started" => KolibriEvent::CommandStarted,
        "command.stdout" => KolibriEvent::CommandStdout,
        "command.stderr" => KolibriEvent::CommandStderr,
        "command.completed" => KolibriEvent::CommandCompleted,
        "command.failed" => KolibriEvent::CommandFailed,
        "sandbox.created" => KolibriEvent::SandboxCreated,
        "sandbox.destroyed" => KolibriEvent::SandboxDestroyed,
        "sandbox.violation" => KolibriEvent::SandboxViolation,
        "artifact.created" => KolibriEvent::ArtifactCreated,
        "artifact.uploaded" => KolibriEvent::ArtifactUploaded,
        "policy.evaluated" => KolibriEvent::PolicyEvaluated,
        "secret.requested" => KolibriEvent::SecretRequested,
        "secret.denied" => KolibriEvent::SecretDenied,
        "secret.granted" => KolibriEvent::SecretGranted,
        "model.requested" => KolibriEvent::ModelRequested,
        "model.completed" => KolibriEvent::ModelCompleted,
        "model.failed" => KolibriEvent::ModelFailed,
        "audit.recorded" => KolibriEvent::AuditRecorded,
        _ => return Err(KolibriEventParseError(event_type.to_string())),
    };
    Ok(as_type)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn envelope_has_subject_prefix() {
        let envelope = EventEnvelope::new(KolibriEvent::TaskCreated, None, Some("test".into()))
            .set_trace("trace-01");
        assert!(envelope.subject().starts_with("kolibri."));
        assert_eq!(envelope.inner.event_type, "task.created");
        assert!(validate_trace_id(envelope.inner.trace_id.as_deref()));
    }

    #[test]
    fn validation_enforces_wire_rules() {
        assert!(EventTypeValidation::validate("task.created").is_ok());
        assert!(EventTypeValidation::validate("").is_err());
        assert!(EventTypeValidation::validate("bad format").is_err());
        assert!(EventTypeValidation::validate("taskcreated").is_err());
    }

    #[test]
    fn parse_known_wire_names() {
        let parsed = parse_wire_event("task.completed").expect("parsed");
        assert_eq!(parsed.as_str(), "task.completed");
        assert_eq!(parsed.subject(), "kolibri.task");
    }
}
