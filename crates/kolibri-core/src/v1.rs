use crate::events::{IdentifierError, validate_identifier};
use crate::swarm::{
    ActorMessage, LogicalActor, LogicalActorState, PlanNode, PlanNodeKind, PlatformRequirement,
    SwarmPlan, SwarmScheduler, V1ActorState, V1PlanNodeKind, V1PlanNodeState, V1SwarmPlanState,
};
use crate::wire::{ACTOR_SCHEMA_VERSION, SWARM_PLAN_SCHEMA_VERSION};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use thiserror::Error;

/// Canonical frozen `SwarmPlan` wire DTO from `domain.schema.json`.
///
/// It is intentionally separate from the scheduler's `SwarmPlan`; the latter
/// remains an internal state-machine aggregate with a numeric schema marker.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct V1SwarmPlan {
    pub schema_version: String,
    pub id: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub trace_id: String,
    pub project_id: String,
    pub workstream_id: Option<String>,
    pub objective: String,
    pub state: V1SwarmPlanState,
    pub nodes: Vec<V1PlanNode>,
    pub max_logical_actors: u64,
    pub physical_slot_limits: BTreeMap<String, u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct V1PlanNode {
    pub id: String,
    pub kind: V1PlanNodeKind,
    pub objective: String,
    pub state: V1PlanNodeState,
    pub dependencies: Vec<String>,
    pub acceptance: Vec<String>,
    pub required_capabilities: Vec<String>,
    pub resources: Vec<V1ResourceRequest>,
    pub retry_policy: V1RetryPolicy,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub approval_policy: Option<V1ApprovalPolicy>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub write_scope: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub worktree_required: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reducer_group: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub verifier_gates: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub lease_owner: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub attempt_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub lease_until: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct V1RetryPolicy {
    pub max_attempts: u32,
    pub backoff_seconds: f64,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub retryable_reasons: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct V1ResourceRequest {
    #[serde(rename = "class")]
    pub resource_class: V1ResourceClass,
    pub slots: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub memory_mb: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub timeout_seconds: Option<u64>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
pub enum V1ResourceClass {
    Cpu,
    Memory,
    Model,
    Browser,
    Build,
    AppleBuild,
    Gpu,
    Network,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum V1ApprovalPolicy {
    None,
    Owner,
    Security,
    Financial,
    Production,
}

/// Canonical frozen `LogicalActor` wire DTO from `domain.schema.json`.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct V1LogicalActor {
    pub schema_version: String,
    pub id: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub actor_class: String,
    pub state: V1ActorState,
    pub capabilities: Vec<String>,
    pub mailbox: Vec<V1MailboxMessage>,
    pub checkpoint: Value,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub resource_lease_ids: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct V1MailboxMessage {
    pub id: String,
    pub sequence: u64,
    pub kind: String,
    pub payload: Value,
    pub enqueued_at: DateTime<Utc>,
}

impl V1SwarmPlan {
    pub fn from_plan_definition(
        plan: &SwarmPlan,
        state: V1SwarmPlanState,
        physical_slot_limits: BTreeMap<String, u64>,
    ) -> Result<Self, V1DtoError> {
        let nodes = plan
            .execution_plan
            .nodes
            .iter()
            .map(V1PlanNode::from_plan_definition)
            .collect::<Result<Vec<_>, _>>()?;
        let value = Self {
            schema_version: SWARM_PLAN_SCHEMA_VERSION.to_string(),
            id: plan.id.to_string(),
            created_at: plan.created_at,
            updated_at: plan.created_at,
            trace_id: plan.trace_id.clone(),
            project_id: plan.execution_plan.project_id.to_string(),
            workstream_id: Some(plan.execution_plan.workstream_id.to_string()),
            objective: plan.execution_plan.goal.clone(),
            state,
            nodes,
            max_logical_actors: u64::try_from(plan.requested_logical_actors)
                .map_err(|_| V1DtoError::LogicalActorLimitOutOfRange)?,
            physical_slot_limits,
        };
        value.validate()?;
        Ok(value)
    }

    pub fn from_runtime(
        plan: &SwarmPlan,
        scheduler: &SwarmScheduler,
        physical_slot_limits: BTreeMap<String, u64>,
    ) -> Result<Self, V1DtoError> {
        if scheduler.swarm_plan_id != plan.id {
            return Err(V1DtoError::PlanIdentityMismatch);
        }
        let mut value = Self::from_plan_definition(
            plan,
            V1SwarmPlanState::from(scheduler.plan_state()),
            physical_slot_limits,
        )?;
        value.nodes = plan
            .execution_plan
            .nodes
            .iter()
            .map(|node| {
                let actor = scheduler
                    .actors
                    .get(&node.id)
                    .ok_or(V1DtoError::MissingRuntimeActor(node.id.to_string()))?;
                V1PlanNode::from_runtime(node, actor)
            })
            .collect::<Result<Vec<_>, _>>()?;
        value.updated_at = scheduler
            .actors
            .values()
            .map(|actor| actor.updated_at)
            .max()
            .unwrap_or(plan.created_at);
        value.validate()?;
        Ok(value)
    }

    pub fn validate(&self) -> Result<(), V1DtoError> {
        if self.schema_version != SWARM_PLAN_SCHEMA_VERSION {
            return Err(V1DtoError::InvalidSchemaVersion {
                expected: SWARM_PLAN_SCHEMA_VERSION,
                actual: self.schema_version.clone(),
            });
        }
        validate_named_identifier("id", &self.id)?;
        validate_named_identifier("trace_id", &self.trace_id)?;
        validate_named_identifier("project_id", &self.project_id)?;
        if let Some(workstream_id) = &self.workstream_id {
            validate_named_identifier("workstream_id", workstream_id)?;
        }
        if self.objective.is_empty() {
            return Err(V1DtoError::EmptyField("objective"));
        }
        if self.nodes.is_empty() {
            return Err(V1DtoError::EmptyCollection("nodes"));
        }
        if !(1..=100_000).contains(&self.max_logical_actors) {
            return Err(V1DtoError::LogicalActorLimitOutOfRange);
        }
        for resource in self.physical_slot_limits.keys() {
            if resource.trim().is_empty() {
                return Err(V1DtoError::EmptyField("physical_slot_limits key"));
            }
        }
        let mut node_ids = BTreeSet::new();
        for node in &self.nodes {
            node.validate()?;
            if !node_ids.insert(node.id.as_str()) {
                return Err(V1DtoError::DuplicateIdentifier(node.id.clone()));
            }
        }
        Ok(())
    }
}

impl V1PlanNode {
    pub fn from_plan_definition(node: &PlanNode) -> Result<Self, V1DtoError> {
        let capability = node.capability.trim().to_string();
        let value = Self {
            id: node.id.to_string(),
            kind: V1PlanNodeKind::from(node.kind),
            objective: node.name.clone(),
            state: V1PlanNodeState::from(node.state),
            dependencies: node.dependencies.iter().map(ToString::to_string).collect(),
            acceptance: node
                .acceptance
                .iter()
                .map(|assertion| assertion.expression.clone())
                .collect(),
            required_capabilities: vec![capability],
            resources: vec![V1ResourceRequest {
                resource_class: resource_class_for(node),
                slots: 1,
                memory_mb: Some(node.resource_request.memory_bytes.div_ceil(1024 * 1024)),
                timeout_seconds: Some(node.timeout_seconds),
            }],
            retry_policy: V1RetryPolicy {
                max_attempts: node.max_attempts,
                backoff_seconds: 0.0,
                retryable_reasons: Vec::new(),
            },
            approval_policy: Some(V1ApprovalPolicy::None),
            write_scope: Vec::new(),
            worktree_required: Some(matches!(
                node.kind,
                PlanNodeKind::Worker
                    | PlanNodeKind::Mapper
                    | PlanNodeKind::Tool
                    | PlanNodeKind::Renderer
                    | PlanNodeKind::Publisher
            )),
            reducer_group: None,
            verifier_gates: if node.kind == PlanNodeKind::Verifier {
                node.acceptance
                    .iter()
                    .map(|assertion| assertion.id.clone())
                    .collect()
            } else {
                Vec::new()
            },
            lease_owner: None,
            attempt_id: None,
            lease_until: None,
        };
        value.validate()?;
        Ok(value)
    }

    pub fn from_runtime(node: &PlanNode, actor: &LogicalActor) -> Result<Self, V1DtoError> {
        if actor.plan_node_id != node.id {
            return Err(V1DtoError::PlanNodeIdentityMismatch);
        }
        let mut value = Self::from_plan_definition(node)?;
        value.state = match actor.state {
            LogicalActorState::Pending | LogicalActorState::WaitingDependencies => {
                V1PlanNodeState::Pending
            }
            LogicalActorState::Ready if actor.current_lease.is_some() => V1PlanNodeState::Leased,
            LogicalActorState::Ready => V1PlanNodeState::Ready,
            LogicalActorState::Running => V1PlanNodeState::Running,
            LogicalActorState::Reducing | LogicalActorState::Verifying => V1PlanNodeState::Review,
            LogicalActorState::Completed => V1PlanNodeState::Completed,
            LogicalActorState::Blocked => V1PlanNodeState::Blocked,
            LogicalActorState::Failed => V1PlanNodeState::Dead,
            LogicalActorState::Cancelled => V1PlanNodeState::Cancelled,
        };
        if let Some(lease) = &actor.current_lease {
            value.lease_owner = Some(lease.slot_id.to_string());
            value.attempt_id = Some(lease.id.to_string());
            value.lease_until = Some(lease.expires_at);
        }
        value.validate()?;
        Ok(value)
    }

    pub fn validate(&self) -> Result<(), V1DtoError> {
        validate_named_identifier("node.id", &self.id)?;
        if self.objective.is_empty() {
            return Err(V1DtoError::EmptyField("node.objective"));
        }
        if self.objective.chars().count() > 50_000 {
            return Err(V1DtoError::FieldTooLong("node.objective"));
        }
        validate_unique_identifiers("node.dependencies", &self.dependencies)?;
        if self.acceptance.is_empty() || self.acceptance.iter().any(|value| value.is_empty()) {
            return Err(V1DtoError::EmptyCollection("node.acceptance"));
        }
        validate_unique_strings("node.required_capabilities", &self.required_capabilities)?;
        for resource in &self.resources {
            resource.validate()?;
        }
        self.retry_policy.validate()?;
        if let Some(lease_owner) = &self.lease_owner
            && lease_owner.trim().is_empty()
        {
            return Err(V1DtoError::EmptyField("node.lease_owner"));
        }
        if let Some(attempt_id) = &self.attempt_id
            && attempt_id.trim().is_empty()
        {
            return Err(V1DtoError::EmptyField("node.attempt_id"));
        }
        Ok(())
    }
}

impl V1RetryPolicy {
    pub fn validate(&self) -> Result<(), V1DtoError> {
        if !(1..=100).contains(&self.max_attempts) {
            return Err(V1DtoError::RetryAttemptsOutOfRange);
        }
        if !self.backoff_seconds.is_finite() || self.backoff_seconds < 0.0 {
            return Err(V1DtoError::InvalidBackoff);
        }
        Ok(())
    }
}

impl V1ResourceRequest {
    pub fn validate(&self) -> Result<(), V1DtoError> {
        if self.slots == 0 {
            return Err(V1DtoError::ResourceSlotsMustBePositive);
        }
        if self.timeout_seconds == Some(0) {
            return Err(V1DtoError::ResourceTimeoutMustBePositive);
        }
        Ok(())
    }
}

impl V1LogicalActor {
    pub fn from_scheduler(actor: &LogicalActor) -> Result<Self, V1DtoError> {
        let mailbox = actor
            .mailbox
            .messages
            .iter()
            .map(V1MailboxMessage::from_scheduler)
            .collect::<Result<Vec<_>, _>>()?;
        let mut resource_lease_ids = Vec::new();
        if let Some(lease) = &actor.current_lease {
            resource_lease_ids.push(lease.id.to_string());
        }
        let state = if actor.current_lease.is_some() && actor.state == LogicalActorState::Ready {
            V1ActorState::Leased
        } else {
            V1ActorState::from(actor.state)
        };
        let value = Self {
            schema_version: ACTOR_SCHEMA_VERSION.to_string(),
            id: actor.id.to_string(),
            created_at: actor.created_at,
            updated_at: actor.updated_at,
            actor_class: actor_class(actor.kind),
            state,
            capabilities: vec![actor.capability.clone()],
            mailbox,
            checkpoint: json!({
                "through_sequence": actor.mailbox.checkpoint_sequence,
                "next_sequence": actor.mailbox.next_sequence,
                "pending_sequences": actor.mailbox.replay_from_checkpoint()
                    .into_iter()
                    .map(|message| message.sequence)
                    .collect::<Vec<_>>()
            }),
            resource_lease_ids,
        };
        value.validate()?;
        Ok(value)
    }

    pub fn validate(&self) -> Result<(), V1DtoError> {
        if self.schema_version != ACTOR_SCHEMA_VERSION {
            return Err(V1DtoError::InvalidSchemaVersion {
                expected: ACTOR_SCHEMA_VERSION,
                actual: self.schema_version.clone(),
            });
        }
        validate_named_identifier("actor.id", &self.id)?;
        if self.actor_class.is_empty() {
            return Err(V1DtoError::EmptyField("actor.actor_class"));
        }
        validate_unique_strings("actor.capabilities", &self.capabilities)?;
        if !self.checkpoint.is_object() {
            return Err(V1DtoError::MetadataMustBeObject("actor.checkpoint"));
        }
        validate_unique_identifiers("actor.resource_lease_ids", &self.resource_lease_ids)?;
        let mut sequences = BTreeSet::new();
        for message in &self.mailbox {
            message.validate()?;
            if !sequences.insert(message.sequence) {
                return Err(V1DtoError::DuplicateMailboxSequence(message.sequence));
            }
        }
        Ok(())
    }
}

impl V1MailboxMessage {
    fn from_scheduler(message: &ActorMessage) -> Result<Self, V1DtoError> {
        if !message.payload.is_object() {
            return Err(V1DtoError::MetadataMustBeObject("mailbox.payload"));
        }
        let kind = serde_json::to_value(message.kind)
            .ok()
            .and_then(|value| value.as_str().map(ToOwned::to_owned))
            .ok_or(V1DtoError::InvalidMailboxKind)?;
        Ok(Self {
            id: message.id.to_string(),
            sequence: message.sequence,
            kind,
            payload: message.payload.clone(),
            enqueued_at: message.created_at,
        })
    }

    pub fn validate(&self) -> Result<(), V1DtoError> {
        validate_named_identifier("mailbox.id", &self.id)?;
        if self.sequence == 0 {
            return Err(V1DtoError::MailboxSequenceMustBePositive);
        }
        if !self.payload.is_object() {
            return Err(V1DtoError::MetadataMustBeObject("mailbox.payload"));
        }
        Ok(())
    }
}

fn resource_class_for(node: &PlanNode) -> V1ResourceClass {
    let capability = node.resource_request.capability.to_ascii_lowercase();
    if node.resource_request.platform == PlatformRequirement::MacApple {
        V1ResourceClass::AppleBuild
    } else if node.resource_request.gpu_required {
        V1ResourceClass::Gpu
    } else if capability.contains("browser") {
        V1ResourceClass::Browser
    } else if capability.contains("build") || capability.contains("compile") {
        V1ResourceClass::Build
    } else if capability.contains("model") || capability.contains("llm") {
        V1ResourceClass::Model
    } else if capability.contains("network") {
        V1ResourceClass::Network
    } else if capability.contains("memory") {
        V1ResourceClass::Memory
    } else {
        V1ResourceClass::Cpu
    }
}

fn actor_class(kind: PlanNodeKind) -> String {
    serde_json::to_value(V1PlanNodeKind::from(kind))
        .ok()
        .and_then(|value| value.as_str().map(ToOwned::to_owned))
        .unwrap_or_else(|| "worker".to_string())
}

fn validate_named_identifier(field: &'static str, value: &str) -> Result<(), V1DtoError> {
    validate_identifier(value).map_err(|source| V1DtoError::InvalidIdentifier { field, source })
}

fn validate_unique_identifiers(field: &'static str, values: &[String]) -> Result<(), V1DtoError> {
    let mut unique = BTreeSet::new();
    for value in values {
        validate_named_identifier(field, value)?;
        if !unique.insert(value) {
            return Err(V1DtoError::DuplicateIdentifier(value.clone()));
        }
    }
    Ok(())
}

fn validate_unique_strings(field: &'static str, values: &[String]) -> Result<(), V1DtoError> {
    let mut unique = BTreeSet::new();
    for value in values {
        if !unique.insert(value) {
            return Err(V1DtoError::DuplicateString {
                field,
                value: value.clone(),
            });
        }
    }
    Ok(())
}

#[derive(Debug, Error, Clone, PartialEq)]
pub enum V1DtoError {
    #[error("invalid schema version: expected {expected}, got {actual:?}")]
    InvalidSchemaVersion {
        expected: &'static str,
        actual: String,
    },
    #[error("invalid identifier in {field}: {source}")]
    InvalidIdentifier {
        field: &'static str,
        source: IdentifierError,
    },
    #[error("runtime scheduler belongs to a different swarm plan")]
    PlanIdentityMismatch,
    #[error("runtime actor belongs to a different plan node")]
    PlanNodeIdentityMismatch,
    #[error("runtime scheduler is missing actor {0}")]
    MissingRuntimeActor(String),
    #[error("required field {0} is empty")]
    EmptyField(&'static str),
    #[error("required collection {0} is empty")]
    EmptyCollection(&'static str),
    #[error("field {0} exceeds the frozen schema limit")]
    FieldTooLong(&'static str),
    #[error("duplicate identifier {0:?}")]
    DuplicateIdentifier(String),
    #[error("duplicate value {value:?} in {field}")]
    DuplicateString { field: &'static str, value: String },
    #[error("max_logical_actors must be between 1 and 100000")]
    LogicalActorLimitOutOfRange,
    #[error("retry max_attempts must be between 1 and 100")]
    RetryAttemptsOutOfRange,
    #[error("retry backoff_seconds must be finite and non-negative")]
    InvalidBackoff,
    #[error("resource slots must be positive")]
    ResourceSlotsMustBePositive,
    #[error("resource timeout_seconds must be positive")]
    ResourceTimeoutMustBePositive,
    #[error("{0} must be a JSON object")]
    MetadataMustBeObject(&'static str),
    #[error("mailbox sequence must be positive")]
    MailboxSequenceMustBePositive,
    #[error("duplicate mailbox sequence {0}")]
    DuplicateMailboxSequence(u64),
    #[error("internal mailbox kind cannot be serialized")]
    InvalidMailboxKind,
}
