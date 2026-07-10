use kolibri_core::events::{subject_for as core_subject_for, EventDraft, KolibriEvent};
use serde::{Deserialize, Serialize};

pub use kolibri_core::event_store::{
    DurableHomeEventStore, EventStoreError, HomeAppendCredential, HomeAuthorityConfig,
    VerifiedEventEnvelope,
};
pub use kolibri_core::events::subject_for as event_subject_for;
pub use kolibri_core::events::EventEnvelope;

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

pub fn new_event_draft(
    event: KolibriEvent,
    aggregate_id: Option<uuid::Uuid>,
    actor: Option<String>,
) -> EventDraft {
    EventDraft::for_event(
        event,
        aggregate_id,
        actor.unwrap_or_else(|| "kolibri-events".to_string()),
    )
}

pub fn with_payload<T: Serialize>(
    mut draft: EventDraft,
    payload: &T,
) -> Result<EventDraft, serde_json::Error> {
    draft.payload_json = serde_json::to_value(payload)?;
    Ok(draft)
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
        None => false,
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
        "project.created" => KolibriEvent::ProjectCreated,
        "workstream.updated" => KolibriEvent::WorkstreamUpdated,
        "checkpoint.created" => KolibriEvent::CheckpointCreated,
        "plan.created" => KolibriEvent::PlanCreated,
        "swarm.plan.created" => KolibriEvent::SwarmPlanCreated,
        "actor.ready" => KolibriEvent::ActorReady,
        "actor.leased" => KolibriEvent::ActorLeased,
        "actor.lease.renewed" => KolibriEvent::ActorLeaseRenewed,
        "actor.lease.expired" => KolibriEvent::ActorLeaseExpired,
        "actor.requeued" => KolibriEvent::ActorRequeued,
        "actor.completed" => KolibriEvent::ActorCompleted,
        "actor.failed" => KolibriEvent::ActorFailed,
        "verifier.approved" => KolibriEvent::VerifierApproved,
        "verifier.rejected" => KolibriEvent::VerifierRejected,
        "mailbox.message.enqueued" => KolibriEvent::MailboxMessageEnqueued,
        "mailbox.message.acknowledged" => KolibriEvent::MailboxMessageAcknowledged,
        "mailbox.checkpointed" => KolibriEvent::MailboxCheckpointed,
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
        "provider.attempt.started" => KolibriEvent::ProviderAttemptStarted,
        "provider.attempt.succeeded" => KolibriEvent::ProviderAttemptSucceeded,
        "provider.attempt.failed" => KolibriEvent::ProviderAttemptFailed,
        "formulalm.trace.captured" => KolibriEvent::FormulaTraceCaptured,
        "learning.candidate.created" => KolibriEvent::LearningCandidateCreated,
        "learning.candidate.eligible" => KolibriEvent::LearningCandidateEligible,
        "learning.candidate.excluded" => KolibriEvent::LearningCandidateExcluded,
        "artifact.rendered" => KolibriEvent::ArtifactRendered,
        "preview.started" => KolibriEvent::PreviewStarted,
        "preview.ready" => KolibriEvent::PreviewReady,
        "preview.stopped" => KolibriEvent::PreviewStopped,
        "browser.session.started" => KolibriEvent::BrowserSessionStarted,
        "browser.session.completed" => KolibriEvent::BrowserSessionCompleted,
        "automation.triggered" => KolibriEvent::AutomationTriggered,
        "automation.completed" => KolibriEvent::AutomationCompleted,
        "audit.recorded" => KolibriEvent::AuditRecorded,
        _ => return Err(KolibriEventParseError(event_type.to_string())),
    };
    Ok(as_type)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn draft_has_no_fabricated_authority_or_sequence() {
        let draft = new_event_draft(KolibriEvent::TaskCreated, None, Some("test".into()));
        assert!(draft.subject.starts_with("kolibri."));
        assert!(!draft.idempotency_key.is_empty());
        assert_eq!(draft.event_type, "task.created");
        assert!(validate_trace_id(Some(draft.trace_id.as_str())));
        assert_eq!(draft.provenance.actor, "test");
        let wire = serde_json::to_value(&draft).unwrap();
        assert!(wire.get("source").is_none());
        assert!(wire.get("sequence").is_none());
        draft.validate().expect("valid event draft");
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

        let actor = parse_wire_event("actor.leased").expect("actor event");
        assert_eq!(actor.subject(), "kolibri.actor");
        let expired = parse_wire_event("actor.lease.expired").expect("lease expiry event");
        assert_eq!(expired.subject(), "kolibri.actor");
        let verifier = parse_wire_event("verifier.approved").expect("verifier event");
        assert_eq!(verifier.subject(), "kolibri.verifier");
        let mailbox = parse_wire_event("mailbox.checkpointed").expect("mailbox event");
        assert_eq!(mailbox.subject(), "kolibri.mailbox");
        let learning = parse_wire_event("learning.candidate.eligible").expect("learning event");
        assert_eq!(learning.subject(), "kolibri.learning");
        assert_eq!(
            event_subject_for("provider.attempt.failed"),
            "kolibri.provider"
        );
    }
}
