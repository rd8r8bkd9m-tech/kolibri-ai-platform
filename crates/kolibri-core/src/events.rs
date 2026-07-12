use crate::wire::{V1_SCHEMA_VERSION, event_schema_version, v1_schema_version};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Deserializer, Serialize, de};
use serde_json::Value;
use std::collections::BTreeMap;
use thiserror::Error;
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
    ProjectCreated,
    WorkstreamUpdated,
    CheckpointCreated,
    PlanCreated,
    SwarmPlanCreated,
    ActorReady,
    ActorLeased,
    ActorLeaseRenewed,
    ActorLeaseExpired,
    ActorRequeued,
    ActorCompleted,
    ActorFailed,
    VerifierApproved,
    VerifierRejected,
    MailboxMessageEnqueued,
    MailboxMessageAcknowledged,
    MailboxCheckpointed,
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
    ProviderAttemptStarted,
    ProviderAttemptSucceeded,
    ProviderAttemptFailed,
    FormulaTraceCaptured,
    LearningCandidateCreated,
    LearningCandidateEligible,
    LearningCandidateExcluded,
    ArtifactRendered,
    PreviewStarted,
    PreviewReady,
    PreviewStopped,
    BrowserSessionStarted,
    BrowserSessionCompleted,
    AutomationTriggered,
    AutomationCompleted,
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
            KolibriEvent::ProjectCreated => "project.created",
            KolibriEvent::WorkstreamUpdated => "workstream.updated",
            KolibriEvent::CheckpointCreated => "checkpoint.created",
            KolibriEvent::PlanCreated => "plan.created",
            KolibriEvent::SwarmPlanCreated => "swarm.plan.created",
            KolibriEvent::ActorReady => "actor.ready",
            KolibriEvent::ActorLeased => "actor.leased",
            KolibriEvent::ActorLeaseRenewed => "actor.lease.renewed",
            KolibriEvent::ActorLeaseExpired => "actor.lease.expired",
            KolibriEvent::ActorRequeued => "actor.requeued",
            KolibriEvent::ActorCompleted => "actor.completed",
            KolibriEvent::ActorFailed => "actor.failed",
            KolibriEvent::VerifierApproved => "verifier.approved",
            KolibriEvent::VerifierRejected => "verifier.rejected",
            KolibriEvent::MailboxMessageEnqueued => "mailbox.message.enqueued",
            KolibriEvent::MailboxMessageAcknowledged => "mailbox.message.acknowledged",
            KolibriEvent::MailboxCheckpointed => "mailbox.checkpointed",
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
            KolibriEvent::ProviderAttemptStarted => "provider.attempt.started",
            KolibriEvent::ProviderAttemptSucceeded => "provider.attempt.succeeded",
            KolibriEvent::ProviderAttemptFailed => "provider.attempt.failed",
            KolibriEvent::FormulaTraceCaptured => "formulalm.trace.captured",
            KolibriEvent::LearningCandidateCreated => "learning.candidate.created",
            KolibriEvent::LearningCandidateEligible => "learning.candidate.eligible",
            KolibriEvent::LearningCandidateExcluded => "learning.candidate.excluded",
            KolibriEvent::ArtifactRendered => "artifact.rendered",
            KolibriEvent::PreviewStarted => "preview.started",
            KolibriEvent::PreviewReady => "preview.ready",
            KolibriEvent::PreviewStopped => "preview.stopped",
            KolibriEvent::BrowserSessionStarted => "browser.session.started",
            KolibriEvent::BrowserSessionCompleted => "browser.session.completed",
            KolibriEvent::AutomationTriggered => "automation.triggered",
            KolibriEvent::AutomationCompleted => "automation.completed",
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
            KolibriEvent::ProjectCreated => "kolibri.project",
            KolibriEvent::WorkstreamUpdated => "kolibri.workstream",
            KolibriEvent::CheckpointCreated => "kolibri.checkpoint",
            KolibriEvent::PlanCreated | KolibriEvent::SwarmPlanCreated => "kolibri.plan",
            KolibriEvent::ActorReady
            | KolibriEvent::ActorLeased
            | KolibriEvent::ActorLeaseRenewed
            | KolibriEvent::ActorLeaseExpired
            | KolibriEvent::ActorRequeued
            | KolibriEvent::ActorCompleted
            | KolibriEvent::ActorFailed => "kolibri.actor",
            KolibriEvent::VerifierApproved | KolibriEvent::VerifierRejected => "kolibri.verifier",
            KolibriEvent::MailboxMessageEnqueued
            | KolibriEvent::MailboxMessageAcknowledged
            | KolibriEvent::MailboxCheckpointed => "kolibri.mailbox",
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
            KolibriEvent::ArtifactCreated
            | KolibriEvent::ArtifactUploaded
            | KolibriEvent::ArtifactRendered => "kolibri.artifact",
            KolibriEvent::PolicyEvaluated => "kolibri.policy",
            KolibriEvent::SecretRequested
            | KolibriEvent::SecretDenied
            | KolibriEvent::SecretGranted => "kolibri.secret",
            KolibriEvent::ModelRequested
            | KolibriEvent::ModelCompleted
            | KolibriEvent::ModelFailed => "kolibri.model",
            KolibriEvent::ProviderAttemptStarted
            | KolibriEvent::ProviderAttemptSucceeded
            | KolibriEvent::ProviderAttemptFailed => "kolibri.provider",
            KolibriEvent::FormulaTraceCaptured => "kolibri.formulalm",
            KolibriEvent::LearningCandidateCreated
            | KolibriEvent::LearningCandidateEligible
            | KolibriEvent::LearningCandidateExcluded => "kolibri.learning",
            KolibriEvent::PreviewStarted
            | KolibriEvent::PreviewReady
            | KolibriEvent::PreviewStopped => "kolibri.preview",
            KolibriEvent::BrowserSessionStarted | KolibriEvent::BrowserSessionCompleted => {
                "kolibri.browser"
            }
            KolibriEvent::AutomationTriggered | KolibriEvent::AutomationCompleted => {
                "kolibri.automation"
            }
            KolibriEvent::AuditRecorded => "kolibri.audit",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub struct EventProvenance {
    #[serde(default)]
    pub actor: String,
    #[serde(default)]
    pub policy_version: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub node_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub attempt_id: Option<String>,
    #[serde(default, flatten)]
    pub extensions: BTreeMap<String, Value>,
}

impl EventProvenance {
    pub fn v1(actor: impl Into<String>, policy_version: impl Into<String>) -> Self {
        Self {
            actor: actor.into(),
            policy_version: policy_version.into(),
            ..Self::default()
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "snake_case")]
pub enum EventAuthorityStatus {
    #[default]
    Uncommitted,
    Authoritative,
    UntrustedMigration,
}

/// Authority is evidence, not a caller-controlled permission bit.
///
/// `authoritative` records are trusted only after
/// [`crate::event_store::DurableHomeEventStore`] verifies their HMAC. A JSON
/// document which merely contains this object is never an authoritative
/// append by itself.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct EventAuthority {
    #[serde(default)]
    pub status: EventAuthorityStatus,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub node_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub authenticated_at: Option<DateTime<Utc>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub evidence: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub draft_sha256: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub previous_record_hmac_sha256: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub record_hmac_sha256: Option<String>,
}

/// An event request before the authoritative Home append path allocates its
/// sequence, source and integrity evidence.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct EventDraft {
    pub event_type: String,
    pub subject: String,
    pub trace_id: String,
    pub payload_json: Value,
    pub provenance: EventProvenance,
    pub occurred_at: DateTime<Utc>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub aggregate_id: Option<Uuid>,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub idempotency_key: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub correlation_id: Option<String>,
}

impl EventDraft {
    pub fn new(
        event_type: impl Into<String>,
        subject: impl Into<String>,
        trace_id: impl Into<String>,
        payload_json: Value,
        provenance: EventProvenance,
        occurred_at: DateTime<Utc>,
    ) -> Self {
        Self {
            event_type: event_type.into(),
            subject: subject.into(),
            trace_id: trace_id.into(),
            payload_json,
            provenance,
            occurred_at,
            aggregate_id: None,
            idempotency_key: String::new(),
            correlation_id: None,
        }
    }

    pub fn for_event(
        event: KolibriEvent,
        aggregate_id: Option<Uuid>,
        actor: impl Into<String>,
    ) -> Self {
        let subject = aggregate_id.map_or_else(
            || event.subject().to_string(),
            |id| {
                let family = event.as_str().split('.').next().unwrap_or("event");
                format!("{family}/{id}")
            },
        );
        let id = Uuid::new_v4();
        Self {
            event_type: event.as_str().to_string(),
            subject,
            trace_id: format!("trace:{id}"),
            payload_json: Value::Object(Default::default()),
            provenance: EventProvenance::v1(actor, "v1"),
            occurred_at: Utc::now(),
            aggregate_id,
            idempotency_key: format!("event:{id}"),
            correlation_id: None,
        }
    }

    pub fn validate(&self) -> Result<(), EventEnvelopeError> {
        if self.idempotency_key.trim().is_empty() {
            return Err(EventEnvelopeError::MissingIdempotencyKey);
        }
        validate_event_fields(
            &self.event_type,
            &self.subject,
            &self.trace_id,
            &self.payload_json,
            &self.provenance,
        )
    }
}

/// Durable V1 event envelope.
///
/// Transport details (`stream`) and retry metadata stay optional extensions;
/// the canonical fields serialize with the frozen Kolibri OS names.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct EventEnvelope {
    #[serde(serialize_with = "event_schema_version::serialize")]
    pub schema_version: u32,
    pub id: Uuid,
    #[serde(rename = "type")]
    pub event_type: String,
    pub source: String,
    pub subject: String,
    pub trace_id: String,
    pub sequence: u64,
    pub occurred_at: DateTime<Utc>,
    #[serde(rename = "data")]
    pub payload_json: Value,
    pub provenance: EventProvenance,
    #[serde(default)]
    pub authority: EventAuthority,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub stream: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub aggregate_id: Option<Uuid>,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub idempotency_key: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub correlation_id: Option<String>,
}

#[derive(Debug, Deserialize)]
struct EventEnvelopeInput {
    #[serde(
        default = "v1_schema_version",
        deserialize_with = "event_schema_version::deserialize"
    )]
    schema_version: u32,
    id: Uuid,
    #[serde(rename = "type", alias = "event_type")]
    event_type: String,
    #[serde(default)]
    source: String,
    subject: String,
    #[serde(default)]
    trace_id: Option<String>,
    #[serde(default)]
    sequence: Option<u64>,
    #[serde(default)]
    occurred_at: Option<DateTime<Utc>>,
    #[serde(rename = "data", alias = "payload_json", default = "empty_event_data")]
    payload_json: Value,
    #[serde(default)]
    provenance: Option<EventProvenance>,
    #[serde(default)]
    created_at: Option<DateTime<Utc>>,
    #[serde(default)]
    updated_at: Option<DateTime<Utc>>,
    #[serde(default)]
    stream: String,
    #[serde(default)]
    aggregate_id: Option<Uuid>,
    #[serde(default)]
    idempotency_key: String,
    #[serde(default)]
    correlation_id: Option<String>,
    #[serde(default)]
    actor: Option<String>,
    #[serde(default)]
    authority: Option<EventAuthority>,
}

fn empty_event_data() -> Value {
    Value::Object(Default::default())
}

impl<'de> Deserialize<'de> for EventEnvelope {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let input = EventEnvelopeInput::deserialize(deserializer)?;
        let occurred_at = input
            .occurred_at
            .or(input.created_at)
            .ok_or_else(|| de::Error::missing_field("occurred_at"))?;
        let created_at = input.created_at.unwrap_or(occurred_at);
        let updated_at = input.updated_at.unwrap_or(created_at);
        let source = if input.source.trim().is_empty() {
            if input.stream.trim().is_empty() {
                "legacy-event-producer".to_string()
            } else {
                input.stream.clone()
            }
        } else {
            input.source
        };
        let provenance = input.provenance.unwrap_or_else(|| {
            EventProvenance::v1(
                input.actor.as_deref().unwrap_or(source.as_str()),
                "legacy-v1",
            )
        });
        let sequence = input.sequence.unwrap_or(0);
        let authority = if input.sequence.is_none() {
            EventAuthority {
                status: EventAuthorityStatus::UntrustedMigration,
                evidence: Some("legacy_missing_sequence".to_string()),
                ..EventAuthority::default()
            }
        } else {
            input.authority.unwrap_or_default()
        };

        Ok(Self {
            schema_version: input.schema_version,
            id: input.id,
            event_type: input.event_type,
            source,
            subject: input.subject,
            trace_id: input.trace_id.unwrap_or_default(),
            sequence,
            occurred_at,
            payload_json: input.payload_json,
            provenance,
            authority,
            created_at,
            updated_at,
            stream: input.stream,
            aggregate_id: input.aggregate_id,
            idempotency_key: input.idempotency_key,
            correlation_id: input.correlation_id,
        })
    }
}

impl EventEnvelope {
    pub(crate) fn from_authoritative_draft(
        draft: EventDraft,
        sequence: u64,
        node_id: String,
        authenticated_at: DateTime<Utc>,
        draft_sha256: String,
        previous_record_hmac_sha256: Option<String>,
    ) -> Self {
        let id = Uuid::new_v4();
        let event_type = draft.event_type;
        Self {
            schema_version: V1_SCHEMA_VERSION,
            id,
            stream: subject_for(&event_type).to_string(),
            event_type,
            source: "control-plane/home".to_string(),
            subject: draft.subject,
            trace_id: draft.trace_id,
            sequence,
            occurred_at: draft.occurred_at,
            payload_json: draft.payload_json,
            provenance: EventProvenance {
                node_id: Some(node_id.clone()),
                ..draft.provenance
            },
            authority: EventAuthority {
                status: EventAuthorityStatus::Authoritative,
                node_id: Some(node_id),
                authenticated_at: Some(authenticated_at),
                evidence: Some("authenticated_home_append_v1".to_string()),
                draft_sha256: Some(draft_sha256),
                previous_record_hmac_sha256,
                record_hmac_sha256: None,
            },
            created_at: draft.occurred_at,
            updated_at: authenticated_at,
            aggregate_id: draft.aggregate_id,
            idempotency_key: draft.idempotency_key,
            correlation_id: draft.correlation_id,
        }
    }

    pub fn validate_contract(&self) -> Result<(), EventEnvelopeError> {
        if self.schema_version != V1_SCHEMA_VERSION {
            return Err(EventEnvelopeError::UnsupportedSchemaVersion(
                self.schema_version,
            ));
        }
        validate_identifier(&self.id.to_string()).map_err(EventEnvelopeError::InvalidId)?;
        if self.source.trim().is_empty() {
            return Err(EventEnvelopeError::MissingSource);
        }
        if self.sequence == 0 {
            return Err(EventEnvelopeError::InvalidSequence);
        }
        validate_event_fields(
            &self.event_type,
            &self.subject,
            &self.trace_id,
            &self.payload_json,
            &self.provenance,
        )
    }

    pub fn validate_migration_evidence(&self) -> Result<(), EventEnvelopeError> {
        if self.sequence != 0
            || self.authority.status != EventAuthorityStatus::UntrustedMigration
            || self.authority.evidence.as_deref() != Some("legacy_missing_sequence")
        {
            return Err(EventEnvelopeError::InvalidMigrationEvidence);
        }
        validate_event_fields(
            &self.event_type,
            &self.subject,
            &self.trace_id,
            &self.payload_json,
            &self.provenance,
        )
    }

    pub fn is_authoritative_claim(&self) -> bool {
        self.authority.status == EventAuthorityStatus::Authoritative
    }

    pub(crate) fn set_record_hmac_sha256(&mut self, signature: String) {
        self.authority.record_hmac_sha256 = Some(signature);
    }

    pub(crate) fn clear_record_hmac_sha256(&mut self) {
        self.authority.record_hmac_sha256 = None;
    }
}

fn validate_event_fields(
    event_type: &str,
    subject: &str,
    trace_id: &str,
    payload_json: &Value,
    provenance: &EventProvenance,
) -> Result<(), EventEnvelopeError> {
    if !valid_event_type(event_type) {
        return Err(EventEnvelopeError::InvalidEventType(event_type.to_string()));
    }
    if subject.trim().is_empty() {
        return Err(EventEnvelopeError::MissingSubject);
    }
    validate_identifier(trace_id).map_err(EventEnvelopeError::InvalidTraceId)?;
    if !payload_json.is_object() {
        return Err(EventEnvelopeError::DataMustBeObject);
    }
    if provenance.actor.trim().is_empty() {
        return Err(EventEnvelopeError::MissingProvenanceActor);
    }
    if provenance.policy_version.trim().is_empty() {
        return Err(EventEnvelopeError::MissingPolicyVersion);
    }
    for reserved in [
        "actor",
        "policy_version",
        "provider",
        "model",
        "node_id",
        "attempt_id",
    ] {
        if provenance.extensions.contains_key(reserved) {
            return Err(EventEnvelopeError::ReservedProvenanceExtension(
                reserved.to_string(),
            ));
        }
    }
    Ok(())
}

pub fn validate_identifier(identifier: &str) -> Result<(), IdentifierError> {
    let length = identifier.chars().count();
    if !(3..=200).contains(&length) {
        return Err(IdentifierError::InvalidLength(length));
    }
    let mut characters = identifier.chars();
    if !characters.next().is_some_and(|c| c.is_ascii_alphanumeric()) {
        return Err(IdentifierError::InvalidFirstCharacter);
    }
    if !characters.all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | ':' | '-')) {
        return Err(IdentifierError::InvalidCharacter);
    }
    Ok(())
}

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum IdentifierError {
    #[error("identifier length must be between 3 and 200 characters, got {0}")]
    InvalidLength(usize),
    #[error("identifier must start with an ASCII letter or digit")]
    InvalidFirstCharacter,
    #[error("identifier contains a character outside [A-Za-z0-9._:-]")]
    InvalidCharacter,
}

fn valid_event_type(event_type: &str) -> bool {
    let mut characters = event_type.chars();
    event_type.len() >= 2
        && matches!(characters.next(), Some(first) if first.is_ascii_lowercase())
        && characters.all(|character| {
            character.is_ascii_lowercase()
                || character.is_ascii_digit()
                || matches!(character, '_' | '.' | '-')
        })
}

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum EventEnvelopeError {
    #[error("unsupported event schema version: {0}")]
    UnsupportedSchemaVersion(u32),
    #[error("invalid event type: {0}")]
    InvalidEventType(String),
    #[error("invalid event id: {0}")]
    InvalidId(IdentifierError),
    #[error("event envelope requires source")]
    MissingSource,
    #[error("event envelope requires subject")]
    MissingSubject,
    #[error("invalid event trace_id: {0}")]
    InvalidTraceId(IdentifierError),
    #[error("event envelope sequence must be at least 1")]
    InvalidSequence,
    #[error("event envelope data must be an object")]
    DataMustBeObject,
    #[error("event provenance requires actor")]
    MissingProvenanceActor,
    #[error("event provenance requires policy_version")]
    MissingPolicyVersion,
    #[error("event provenance extension collides with reserved field {0:?}")]
    ReservedProvenanceExtension(String),
    #[error("event append requires a non-empty idempotency key")]
    MissingIdempotencyKey,
    #[error("legacy migration evidence is not explicitly marked untrusted")]
    InvalidMigrationEvidence,
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
        e if e.starts_with("project.") => "kolibri.project",
        e if e.starts_with("workstream.") => "kolibri.workstream",
        e if e.starts_with("checkpoint.") => "kolibri.checkpoint",
        e if e.starts_with("plan.") || e.starts_with("swarm.") => "kolibri.plan",
        e if e.starts_with("actor.") => "kolibri.actor",
        e if e.starts_with("verifier.") => "kolibri.verifier",
        e if e.starts_with("mailbox.") => "kolibri.mailbox",
        e if e.starts_with("task.") => "kolibri.task",
        e if e.starts_with("command.") => "kolibri.command",
        e if e.starts_with("sandbox.") => "kolibri.sandbox",
        e if e.starts_with("artifact.") => "kolibri.artifact",
        e if e.starts_with("policy.") => "kolibri.policy",
        e if e.starts_with("secret.") => "kolibri.secret",
        e if e.starts_with("model.") => "kolibri.model",
        e if e.starts_with("provider.") => "kolibri.provider",
        e if e.starts_with("formulalm.") => "kolibri.formulalm",
        e if e.starts_with("learning.") => "kolibri.learning",
        e if e.starts_with("preview.") => "kolibri.preview",
        e if e.starts_with("browser.") => "kolibri.browser",
        e if e.starts_with("automation.") => "kolibri.automation",
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
        assert_eq!(
            KolibriEvent::ActorLeaseExpired.as_str(),
            "actor.lease.expired"
        );
        assert_eq!(KolibriEvent::VerifierApproved.subject(), "kolibri.verifier");
        assert_eq!(
            KolibriEvent::MailboxCheckpointed.subject(),
            "kolibri.mailbox"
        );
    }
}
