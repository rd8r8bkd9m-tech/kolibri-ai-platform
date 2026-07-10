use crate::wire::{v1_schema_version, V1_SCHEMA_VERSION};
use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use thiserror::Error;
use uuid::Uuid;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum PlanNodeKind {
    Planner,
    Worker,
    Mapper,
    Reducer,
    Verifier,
    Tool,
    Renderer,
    Publisher,
}

/// Explicit projection from a complete public V1 state into the narrower
/// scheduler state machine. Transitional projections are never silent: the
/// caller must decide whether the documented information loss is acceptable.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum V1SchedulerProjection<T> {
    Exact(T),
    Transitional { nearest: T, reason: &'static str },
    Unsupported { reason: &'static str },
}

/// Public plan-node kinds frozen by `domain.schema.json`.
///
/// This is intentionally separate from [`PlanNodeKind`]: mapper/tool/renderer
/// roles remain scheduler details and are lowered to `worker` only at the V1
/// compatibility boundary.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum V1PlanNodeKind {
    Planner,
    Worker,
    Reducer,
    Verifier,
    Approval,
    Release,
}

impl From<PlanNodeKind> for V1PlanNodeKind {
    fn from(value: PlanNodeKind) -> Self {
        match value {
            PlanNodeKind::Planner => Self::Planner,
            PlanNodeKind::Worker
            | PlanNodeKind::Mapper
            | PlanNodeKind::Tool
            | PlanNodeKind::Renderer => Self::Worker,
            PlanNodeKind::Reducer => Self::Reducer,
            PlanNodeKind::Verifier => Self::Verifier,
            PlanNodeKind::Publisher => Self::Release,
        }
    }
}

impl V1PlanNodeKind {
    pub fn scheduler_projection(self) -> V1SchedulerProjection<PlanNodeKind> {
        match self {
            Self::Planner => V1SchedulerProjection::Exact(PlanNodeKind::Planner),
            Self::Worker => V1SchedulerProjection::Transitional {
                nearest: PlanNodeKind::Worker,
                reason: "V1 worker collapses worker, mapper, tool and renderer scheduler kinds",
            },
            Self::Reducer => V1SchedulerProjection::Exact(PlanNodeKind::Reducer),
            Self::Verifier => V1SchedulerProjection::Exact(PlanNodeKind::Verifier),
            Self::Release => V1SchedulerProjection::Exact(PlanNodeKind::Publisher),
            Self::Approval => V1SchedulerProjection::Unsupported {
                reason: "approval is enforced by policy and has no standalone scheduler kind",
            },
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum PlanNodeState {
    Pending,
    WaitingDependencies,
    Ready,
    Running,
    Reducing,
    Verifying,
    Completed,
    Blocked,
    Failed,
    Cancelled,
}

/// Public plan-node states frozen by `domain.schema.json`.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum V1PlanNodeState {
    Pending,
    Ready,
    Leased,
    Running,
    Review,
    Retry,
    Blocked,
    Completed,
    Dead,
    Cancelled,
}

impl From<PlanNodeState> for V1PlanNodeState {
    fn from(value: PlanNodeState) -> Self {
        match value {
            PlanNodeState::Pending | PlanNodeState::WaitingDependencies => Self::Pending,
            PlanNodeState::Ready => Self::Ready,
            PlanNodeState::Running => Self::Running,
            PlanNodeState::Reducing | PlanNodeState::Verifying => Self::Review,
            PlanNodeState::Completed => Self::Completed,
            PlanNodeState::Blocked => Self::Blocked,
            PlanNodeState::Failed => Self::Dead,
            PlanNodeState::Cancelled => Self::Cancelled,
        }
    }
}

impl V1PlanNodeState {
    pub fn scheduler_projection(self) -> V1SchedulerProjection<PlanNodeState> {
        match self {
            Self::Pending => V1SchedulerProjection::Transitional {
                nearest: PlanNodeState::Pending,
                reason: "V1 pending collapses pending and waiting-dependencies scheduler states",
            },
            Self::Ready => V1SchedulerProjection::Exact(PlanNodeState::Ready),
            Self::Running => V1SchedulerProjection::Exact(PlanNodeState::Running),
            Self::Review => V1SchedulerProjection::Transitional {
                nearest: PlanNodeState::Verifying,
                reason: "V1 review collapses reducing and verifying scheduler states",
            },
            Self::Blocked => V1SchedulerProjection::Exact(PlanNodeState::Blocked),
            Self::Completed => V1SchedulerProjection::Exact(PlanNodeState::Completed),
            Self::Dead => V1SchedulerProjection::Exact(PlanNodeState::Failed),
            Self::Cancelled => V1SchedulerProjection::Exact(PlanNodeState::Cancelled),
            Self::Leased => V1SchedulerProjection::Transitional {
                nearest: PlanNodeState::Running,
                reason: "lease ownership is represented by ActorLease, not PlanNodeState",
            },
            Self::Retry => V1SchedulerProjection::Transitional {
                nearest: PlanNodeState::Ready,
                reason: "retry budget and attempt are represented outside PlanNodeState",
            },
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum PlatformRequirement {
    Any,
    Ubuntu,
    MacApple,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct AcceptanceAssertion {
    pub id: String,
    pub assertion_type: String,
    pub expression: String,
    pub evidence_artifact_type: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ResourceRequest {
    pub platform: PlatformRequirement,
    pub capability: String,
    pub cpu_millis: u32,
    pub memory_bytes: u64,
    pub disk_bytes: u64,
    pub gpu_required: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PlanNode {
    pub id: Uuid,
    pub plan_id: Uuid,
    pub name: String,
    pub kind: PlanNodeKind,
    pub state: PlanNodeState,
    pub dependencies: Vec<Uuid>,
    pub capability: String,
    pub input_schema: Value,
    pub output_schema: Value,
    pub acceptance: Vec<AcceptanceAssertion>,
    pub resource_request: ResourceRequest,
    pub sandbox_profile: String,
    pub max_attempts: u32,
    pub timeout_seconds: u64,
    pub critical_path_weight: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ExecutionPlan {
    #[serde(default = "v1_schema_version")]
    pub schema_version: u32,
    #[serde(default)]
    pub trace_id: String,
    #[serde(default)]
    pub idempotency_key: String,
    pub id: Uuid,
    pub project_id: Uuid,
    pub workstream_id: Uuid,
    pub version: u64,
    pub goal: String,
    pub nodes: Vec<PlanNode>,
    pub created_by: String,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SwarmPlan {
    #[serde(default = "v1_schema_version")]
    pub schema_version: u32,
    #[serde(default)]
    pub trace_id: String,
    #[serde(default)]
    pub idempotency_key: String,
    pub id: Uuid,
    pub execution_plan: ExecutionPlan,
    pub requested_logical_actors: usize,
    pub max_physical_slots: usize,
    pub external_planner_provider: Option<String>,
    pub formula_tap_required: bool,
    pub reducer_node_ids: Vec<Uuid>,
    pub verifier_node_ids: Vec<Uuid>,
    pub created_at: DateTime<Utc>,
}

impl ExecutionPlan {
    pub fn validate_dag(&self) -> Result<(), PlanValidationError> {
        if self.schema_version != V1_SCHEMA_VERSION {
            return Err(PlanValidationError::UnsupportedSchemaVersion(
                self.schema_version,
            ));
        }
        if self.trace_id.trim().is_empty() {
            return Err(PlanValidationError::MissingTraceId);
        }
        if self.idempotency_key.trim().is_empty() {
            return Err(PlanValidationError::MissingIdempotencyKey);
        }

        let mut node_ids = BTreeSet::new();
        for node in &self.nodes {
            if !node_ids.insert(node.id) {
                return Err(PlanValidationError::DuplicateNodeId(node.id));
            }
            if node.plan_id != self.id {
                return Err(PlanValidationError::PlanIdMismatch {
                    node_id: node.id,
                    expected: self.id,
                    actual: node.plan_id,
                });
            }
            if node.max_attempts == 0 {
                return Err(PlanValidationError::InvalidMaxAttempts(node.id));
            }
            if node.timeout_seconds == 0 {
                return Err(PlanValidationError::InvalidTimeout(node.id));
            }
        }

        let mut indegree = BTreeMap::new();
        let mut dependents: BTreeMap<Uuid, Vec<Uuid>> = BTreeMap::new();
        for node in &self.nodes {
            let mut unique_dependencies = BTreeSet::new();
            for dependency in &node.dependencies {
                if *dependency == node.id {
                    return Err(PlanValidationError::SelfDependency(node.id));
                }
                if !node_ids.contains(dependency) {
                    return Err(PlanValidationError::UnknownDependency {
                        node_id: node.id,
                        dependency_id: *dependency,
                    });
                }
                if !unique_dependencies.insert(*dependency) {
                    return Err(PlanValidationError::DuplicateDependency {
                        node_id: node.id,
                        dependency_id: *dependency,
                    });
                }
                dependents.entry(*dependency).or_default().push(node.id);
            }
            indegree.insert(node.id, unique_dependencies.len());
        }

        let mut ready: BTreeSet<Uuid> = indegree
            .iter()
            .filter_map(|(node_id, count)| (*count == 0).then_some(*node_id))
            .collect();
        let mut visited = 0;
        while let Some(node_id) = ready.pop_first() {
            visited += 1;
            for dependent_id in dependents.get(&node_id).into_iter().flatten() {
                let count = indegree
                    .get_mut(dependent_id)
                    .expect("validated dependent must have an indegree");
                *count -= 1;
                if *count == 0 {
                    ready.insert(*dependent_id);
                }
            }
        }

        if visited != self.nodes.len() {
            let remaining = indegree
                .into_iter()
                .filter_map(|(node_id, count)| (count > 0).then_some(node_id))
                .collect();
            return Err(PlanValidationError::Cycle(remaining));
        }
        Ok(())
    }
}

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum PlanValidationError {
    #[error("unsupported execution plan schema version: {0}")]
    UnsupportedSchemaVersion(u32),
    #[error("execution plan requires a trace id")]
    MissingTraceId,
    #[error("execution plan requires an idempotency key")]
    MissingIdempotencyKey,
    #[error("duplicate plan node id: {0}")]
    DuplicateNodeId(Uuid),
    #[error("plan node {node_id} references plan {actual}, expected {expected}")]
    PlanIdMismatch {
        node_id: Uuid,
        expected: Uuid,
        actual: Uuid,
    },
    #[error("plan node cannot depend on itself: {0}")]
    SelfDependency(Uuid),
    #[error("plan node {node_id} references unknown dependency {dependency_id}")]
    UnknownDependency { node_id: Uuid, dependency_id: Uuid },
    #[error("plan node {node_id} repeats dependency {dependency_id}")]
    DuplicateDependency { node_id: Uuid, dependency_id: Uuid },
    #[error("plan contains a dependency cycle involving: {0:?}")]
    Cycle(Vec<Uuid>),
    #[error("plan node requires max_attempts greater than zero: {0}")]
    InvalidMaxAttempts(Uuid),
    #[error("plan node requires timeout_seconds greater than zero: {0}")]
    InvalidTimeout(Uuid),
}

impl SwarmPlan {
    pub fn validate(&self) -> Result<(), SwarmPlanError> {
        if self.schema_version != V1_SCHEMA_VERSION {
            return Err(SwarmPlanError::UnsupportedSchemaVersion(
                self.schema_version,
            ));
        }
        if self.trace_id.trim().is_empty() {
            return Err(SwarmPlanError::MissingTraceId);
        }
        if self.idempotency_key.trim().is_empty() {
            return Err(SwarmPlanError::MissingIdempotencyKey);
        }
        self.execution_plan.validate_dag()?;
        if self.trace_id != self.execution_plan.trace_id {
            return Err(SwarmPlanError::TraceIdMismatch {
                swarm_trace_id: self.trace_id.clone(),
                execution_trace_id: self.execution_plan.trace_id.clone(),
            });
        }
        if self.requested_logical_actors != self.execution_plan.nodes.len() {
            return Err(SwarmPlanError::ActorCountMismatch {
                requested: self.requested_logical_actors,
                nodes: self.execution_plan.nodes.len(),
            });
        }
        if self.max_physical_slots == 0 {
            return Err(SwarmPlanError::NoPhysicalSlots);
        }
        if !self.formula_tap_required {
            return Err(SwarmPlanError::FormulaTapRequired);
        }
        if self.verifier_node_ids.is_empty() {
            return Err(SwarmPlanError::MissingVerifier);
        }
        for reducer_id in &self.reducer_node_ids {
            if !self
                .execution_plan
                .nodes
                .iter()
                .any(|node| node.id == *reducer_id && node.kind == PlanNodeKind::Reducer)
            {
                return Err(SwarmPlanError::InvalidReducer(*reducer_id));
            }
        }
        let mut declared_verifiers = BTreeSet::new();
        for verifier_id in &self.verifier_node_ids {
            if !declared_verifiers.insert(*verifier_id) {
                return Err(SwarmPlanError::DuplicateVerifier(*verifier_id));
            }
            if !self
                .execution_plan
                .nodes
                .iter()
                .any(|node| node.id == *verifier_id && node.kind == PlanNodeKind::Verifier)
            {
                return Err(SwarmPlanError::InvalidVerifier(*verifier_id));
            }
        }
        for node in &self.execution_plan.nodes {
            if node.kind == PlanNodeKind::Verifier && !declared_verifiers.contains(&node.id) {
                return Err(SwarmPlanError::UndeclaredVerifier(node.id));
            }
        }

        // Every path through the execution DAG must terminate at a declared verifier.
        // Otherwise a disconnected output branch (or work scheduled after the last verifier)
        // could complete after all verifier verdicts and incorrectly make the plan terminal.
        let mut nodes_with_dependents = BTreeSet::new();
        for node in &self.execution_plan.nodes {
            nodes_with_dependents.extend(node.dependencies.iter().copied());
        }
        for node in &self.execution_plan.nodes {
            if !nodes_with_dependents.contains(&node.id)
                && (node.kind != PlanNodeKind::Verifier || !declared_verifiers.contains(&node.id))
            {
                return Err(SwarmPlanError::UnverifiedTerminalNode(node.id));
            }
        }
        Ok(())
    }

    pub fn materialize_actors(&self) -> Vec<LogicalActor> {
        self.execution_plan
            .nodes
            .iter()
            .map(|node| LogicalActor::from_plan_node_at(self.id, node, self.created_at))
            .collect()
    }
}

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum SwarmPlanError {
    #[error("unsupported swarm plan schema version: {0}")]
    UnsupportedSchemaVersion(u32),
    #[error("swarm plan requires a trace id")]
    MissingTraceId,
    #[error("swarm plan requires an idempotency key")]
    MissingIdempotencyKey,
    #[error(
        "swarm trace id {swarm_trace_id:?} does not match execution trace id {execution_trace_id:?}"
    )]
    TraceIdMismatch {
        swarm_trace_id: String,
        execution_trace_id: String,
    },
    #[error("invalid execution plan: {0}")]
    InvalidExecutionPlan(#[from] PlanValidationError),
    #[error("logical actor count mismatch: requested {requested}, plan nodes {nodes}")]
    ActorCountMismatch { requested: usize, nodes: usize },
    #[error("swarm plan requires at least one bounded physical slot")]
    NoPhysicalSlots,
    #[error("FormulaLM tap is mandatory for every swarm plan")]
    FormulaTapRequired,
    #[error("swarm plan requires at least one verifier node")]
    MissingVerifier,
    #[error("reducer id does not reference a reducer node: {0}")]
    InvalidReducer(Uuid),
    #[error("verifier id does not reference a verifier node: {0}")]
    InvalidVerifier(Uuid),
    #[error("verifier id is declared more than once: {0}")]
    DuplicateVerifier(Uuid),
    #[error("verifier node is not declared in verifier_node_ids: {0}")]
    UndeclaredVerifier(Uuid),
    #[error("execution branch terminates without a declared verifier: {0}")]
    UnverifiedTerminalNode(Uuid),
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum LogicalActorState {
    Pending,
    WaitingDependencies,
    Ready,
    Running,
    Reducing,
    Verifying,
    Completed,
    Blocked,
    Failed,
    Cancelled,
}

/// Public logical-actor states frozen by `domain.schema.json`.
/// Scheduler-only reducer/verifier phases remain represented internally.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum V1ActorState {
    Idle,
    Runnable,
    Leased,
    Running,
    Checkpointing,
    Waiting,
    Failed,
    Stopped,
}

impl From<LogicalActorState> for V1ActorState {
    fn from(value: LogicalActorState) -> Self {
        match value {
            LogicalActorState::Pending => Self::Idle,
            LogicalActorState::WaitingDependencies | LogicalActorState::Blocked => Self::Waiting,
            LogicalActorState::Ready => Self::Runnable,
            LogicalActorState::Running
            | LogicalActorState::Reducing
            | LogicalActorState::Verifying => Self::Running,
            LogicalActorState::Failed => Self::Failed,
            LogicalActorState::Completed | LogicalActorState::Cancelled => Self::Stopped,
        }
    }
}

impl V1ActorState {
    pub fn scheduler_projection(self) -> V1SchedulerProjection<LogicalActorState> {
        match self {
            Self::Idle => V1SchedulerProjection::Exact(LogicalActorState::Pending),
            Self::Runnable => V1SchedulerProjection::Exact(LogicalActorState::Ready),
            Self::Running => V1SchedulerProjection::Transitional {
                nearest: LogicalActorState::Running,
                reason: "V1 running collapses running, reducing and verifying actor states",
            },
            Self::Waiting => V1SchedulerProjection::Transitional {
                nearest: LogicalActorState::WaitingDependencies,
                reason: "V1 waiting collapses dependency waiting and blocked actor states",
            },
            Self::Failed => V1SchedulerProjection::Exact(LogicalActorState::Failed),
            Self::Leased => V1SchedulerProjection::Transitional {
                nearest: LogicalActorState::Running,
                reason: "lease ownership is represented by current_lease",
            },
            Self::Checkpointing => V1SchedulerProjection::Transitional {
                nearest: LogicalActorState::Running,
                reason: "checkpointing is represented by mailbox checkpoint state",
            },
            Self::Stopped => V1SchedulerProjection::Transitional {
                nearest: LogicalActorState::Cancelled,
                reason: "V1 stopped does not distinguish completed from cancelled",
            },
        }
    }
}

impl LogicalActorState {
    pub fn is_terminal(self) -> bool {
        matches!(
            self,
            Self::Completed | Self::Blocked | Self::Failed | Self::Cancelled
        )
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ActorMessageKind {
    Input,
    Progress,
    PartialResult,
    DependencyCompleted,
    Cancel,
    Retry,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ActorMessage {
    #[serde(default = "v1_schema_version")]
    pub schema_version: u32,
    pub id: Uuid,
    pub actor_id: Uuid,
    pub kind: ActorMessageKind,
    pub sequence: u64,
    pub payload: Value,
    pub trace_id: String,
    #[serde(default)]
    pub idempotency_key: String,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub struct ActorMailbox {
    pub next_sequence: u64,
    pub checkpoint_sequence: u64,
    pub acked_sequences: BTreeSet<u64>,
    pub dedupe_keys: BTreeMap<String, MailboxDedupeEntry>,
    pub messages: Vec<ActorMessage>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct MailboxDedupeEntry {
    pub message_id: Uuid,
    pub sequence: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum MailboxEnqueue {
    Enqueued { message_id: Uuid, sequence: u64 },
    Duplicate { message_id: Uuid, sequence: u64 },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum MailboxAck {
    Advanced { through_sequence: u64 },
    RecordedOutOfOrder { sequence: u64 },
    AlreadyAcked { sequence: u64 },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct MailboxCheckpoint {
    #[serde(default = "v1_schema_version")]
    pub schema_version: u32,
    pub trace_id: String,
    pub idempotency_key: String,
    pub through_sequence: u64,
    pub pending_sequences: Vec<u64>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum MailboxError {
    #[error("mailbox enqueue requires a trace id")]
    MissingTraceId,
    #[error("mailbox enqueue requires an idempotency key")]
    MissingIdempotencyKey,
    #[error("mailbox sequence does not exist: {0}")]
    UnknownSequence(u64),
}

impl ActorMailbox {
    pub fn push(
        &mut self,
        actor_id: Uuid,
        kind: ActorMessageKind,
        payload: Value,
        trace_id: impl Into<String>,
        created_at: DateTime<Utc>,
    ) -> Uuid {
        let idempotency_key = format!("mailbox:{}", Uuid::new_v4());
        match self
            .enqueue_once(
                actor_id,
                kind,
                payload,
                trace_id,
                idempotency_key,
                created_at,
            )
            .expect("generated mailbox metadata must be valid")
        {
            MailboxEnqueue::Enqueued { message_id, .. }
            | MailboxEnqueue::Duplicate { message_id, .. } => message_id,
        }
    }

    pub fn enqueue_once(
        &mut self,
        actor_id: Uuid,
        kind: ActorMessageKind,
        payload: Value,
        trace_id: impl Into<String>,
        idempotency_key: impl Into<String>,
        created_at: DateTime<Utc>,
    ) -> Result<MailboxEnqueue, MailboxError> {
        let trace_id = trace_id.into();
        let idempotency_key = idempotency_key.into();
        if trace_id.trim().is_empty() {
            return Err(MailboxError::MissingTraceId);
        }
        if idempotency_key.trim().is_empty() {
            return Err(MailboxError::MissingIdempotencyKey);
        }
        if let Some(existing) = self.dedupe_keys.get(&idempotency_key) {
            return Ok(MailboxEnqueue::Duplicate {
                message_id: existing.message_id,
                sequence: existing.sequence,
            });
        }

        let message_id = Uuid::new_v4();
        self.next_sequence += 1;
        let sequence = self.next_sequence;
        self.messages.push(ActorMessage {
            schema_version: V1_SCHEMA_VERSION,
            id: message_id,
            actor_id,
            kind,
            sequence,
            payload,
            trace_id,
            idempotency_key: idempotency_key.clone(),
            created_at,
        });
        self.dedupe_keys.insert(
            idempotency_key,
            MailboxDedupeEntry {
                message_id,
                sequence,
            },
        );
        Ok(MailboxEnqueue::Enqueued {
            message_id,
            sequence,
        })
    }

    pub fn dequeue(&self) -> Option<&ActorMessage> {
        self.messages.iter().find(|message| {
            message.sequence > self.checkpoint_sequence
                && !self.acked_sequences.contains(&message.sequence)
        })
    }

    pub fn ack(&mut self, sequence: u64) -> Result<MailboxAck, MailboxError> {
        if sequence <= self.checkpoint_sequence || self.acked_sequences.contains(&sequence) {
            return Ok(MailboxAck::AlreadyAcked { sequence });
        }
        if !self
            .messages
            .iter()
            .any(|message| message.sequence == sequence)
        {
            return Err(MailboxError::UnknownSequence(sequence));
        }
        self.acked_sequences.insert(sequence);
        if sequence != self.checkpoint_sequence + 1 {
            return Ok(MailboxAck::RecordedOutOfOrder { sequence });
        }

        while self.acked_sequences.remove(&(self.checkpoint_sequence + 1)) {
            self.checkpoint_sequence += 1;
        }
        Ok(MailboxAck::Advanced {
            through_sequence: self.checkpoint_sequence,
        })
    }

    pub fn replay_from_checkpoint(&self) -> Vec<&ActorMessage> {
        self.messages
            .iter()
            .filter(|message| {
                message.sequence > self.checkpoint_sequence
                    && !self.acked_sequences.contains(&message.sequence)
            })
            .collect()
    }

    pub fn checkpoint(
        &self,
        trace_id: impl Into<String>,
        idempotency_key: impl Into<String>,
        created_at: DateTime<Utc>,
    ) -> Result<MailboxCheckpoint, MailboxError> {
        let trace_id = trace_id.into();
        let idempotency_key = idempotency_key.into();
        if trace_id.trim().is_empty() {
            return Err(MailboxError::MissingTraceId);
        }
        if idempotency_key.trim().is_empty() {
            return Err(MailboxError::MissingIdempotencyKey);
        }
        Ok(MailboxCheckpoint {
            schema_version: V1_SCHEMA_VERSION,
            trace_id,
            idempotency_key,
            through_sequence: self.checkpoint_sequence,
            pending_sequences: self
                .replay_from_checkpoint()
                .into_iter()
                .map(|message| message.sequence)
                .collect(),
            created_at,
        })
    }

    pub fn compact_through_checkpoint(&mut self) -> usize {
        let previous = self.messages.len();
        self.messages
            .retain(|message| message.sequence > self.checkpoint_sequence);
        previous - self.messages.len()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct LogicalActor {
    pub id: Uuid,
    pub swarm_plan_id: Uuid,
    pub plan_node_id: Uuid,
    pub kind: PlanNodeKind,
    pub state: LogicalActorState,
    pub dependencies: Vec<Uuid>,
    pub capability: String,
    pub resource_request: ResourceRequest,
    pub critical_path_weight: u32,
    pub max_attempts: u32,
    pub timeout_seconds: u64,
    pub attempt: u32,
    pub lease_generation: u64,
    pub idempotency_key: String,
    pub terminal_reason: Option<String>,
    pub verifier_outcome: Option<VerifierOutcome>,
    pub mailbox: ActorMailbox,
    pub current_lease: Option<ActorLease>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl LogicalActor {
    pub fn from_plan_node(swarm_plan_id: Uuid, node: &PlanNode) -> Self {
        Self::from_plan_node_at(swarm_plan_id, node, Utc::now())
    }

    pub fn from_plan_node_at(
        swarm_plan_id: Uuid,
        node: &PlanNode,
        created_at: DateTime<Utc>,
    ) -> Self {
        let state = if node.dependencies.is_empty() {
            LogicalActorState::Ready
        } else {
            LogicalActorState::WaitingDependencies
        };
        Self {
            id: node.id,
            swarm_plan_id,
            plan_node_id: node.id,
            kind: node.kind,
            state,
            dependencies: node.dependencies.clone(),
            capability: node.capability.clone(),
            resource_request: node.resource_request.clone(),
            critical_path_weight: node.critical_path_weight,
            max_attempts: node.max_attempts,
            timeout_seconds: node.timeout_seconds,
            attempt: 0,
            lease_generation: 0,
            idempotency_key: format!("swarm:{swarm_plan_id}:node:{}", node.id),
            terminal_reason: None,
            verifier_outcome: None,
            mailbox: ActorMailbox::default(),
            current_lease: None,
            created_at,
            updated_at: created_at,
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SlotPlatform {
    Ubuntu,
    MacApple,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ResourceCapacity {
    pub cpu_millis: u32,
    pub memory_bytes: u64,
    pub disk_bytes: u64,
    pub gpu_available: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ResourceSlot {
    pub id: Uuid,
    pub node_id: String,
    pub platform: SlotPlatform,
    pub capabilities: Vec<String>,
    pub capacity: ResourceCapacity,
    pub active_lease: Option<ActorLease>,
    pub enabled: bool,
}

impl ResourceSlot {
    fn accepts(&self, actor: &LogicalActor) -> bool {
        let platform_ok = match actor.resource_request.platform {
            PlatformRequirement::Any => true,
            PlatformRequirement::Ubuntu => self.platform == SlotPlatform::Ubuntu,
            PlatformRequirement::MacApple => self.platform == SlotPlatform::MacApple,
        };
        platform_ok
            && self.enabled
            && self.active_lease.is_none()
            && self.capabilities.contains(&actor.capability)
            && actor.resource_request.cpu_millis <= self.capacity.cpu_millis
            && actor.resource_request.memory_bytes <= self.capacity.memory_bytes
            && actor.resource_request.disk_bytes <= self.capacity.disk_bytes
            && (!actor.resource_request.gpu_required || self.capacity.gpu_available)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ActorLease {
    #[serde(default = "v1_schema_version")]
    pub schema_version: u32,
    pub id: Uuid,
    pub actor_id: Uuid,
    pub slot_id: Uuid,
    pub attempt: u32,
    pub fencing_token: u64,
    #[serde(default)]
    pub trace_id: String,
    #[serde(default)]
    pub idempotency_key: String,
    pub acquired_at: DateTime<Utc>,
    pub heartbeat_at: DateTime<Utc>,
    pub deadline_at: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum VerifierOutcome {
    Approved,
    Rejected,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum LeaseOutcome {
    Completed,
    VerifierApproved,
    VerifierRejected,
    Blocked,
    Failed,
    Cancelled,
    Retry,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ProviderAttemptStatus {
    Planned,
    Running,
    Succeeded,
    RejectedByVerifier,
    Failed,
    SkippedByPolicy,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ProviderAttempt {
    #[serde(default = "v1_schema_version")]
    pub schema_version: u32,
    pub id: Uuid,
    pub actor_id: Uuid,
    pub route_index: u32,
    pub provider_id: String,
    pub model_id: String,
    pub adapter_version: String,
    pub capability: String,
    pub status: ProviderAttemptStatus,
    pub request_hash: String,
    pub response_artifact_id: Option<Uuid>,
    pub provenance_artifact_id: Option<Uuid>,
    pub policy_decision_id: Option<Uuid>,
    pub fallback_from_attempt_id: Option<Uuid>,
    pub external_teacher: bool,
    pub data_policy: String,
    pub training_rights_snapshot: String,
    pub verified: bool,
    pub latency_ms: Option<u64>,
    pub input_tokens: Option<u64>,
    pub output_tokens: Option<u64>,
    pub cost_microunits: Option<u64>,
    pub failure_code: Option<String>,
    pub trace_id: String,
    #[serde(default)]
    pub idempotency_key: String,
    pub started_at: Option<DateTime<Utc>>,
    pub finished_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SchedulerSnapshot {
    pub plan_state: PlanExecutionState,
    pub logical_actor_count: usize,
    pub ready_actor_count: usize,
    pub active_actor_count: usize,
    pub terminal_actor_count: usize,
    pub physical_slot_count: usize,
    pub occupied_slot_count: usize,
    /// This reference scheduler records state only and never spawns one process per actor.
    pub spawned_actor_processes: usize,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum PlanExecutionState {
    Running,
    Reducing,
    Verifying,
    Completed,
    Blocked,
    Failed,
}

/// Public SwarmPlan states frozen by `domain.schema.json`.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum V1SwarmPlanState {
    Draft,
    Queued,
    Running,
    Verifying,
    Completed,
    Failed,
    Cancelled,
}

impl From<PlanExecutionState> for V1SwarmPlanState {
    fn from(value: PlanExecutionState) -> Self {
        match value {
            PlanExecutionState::Running => Self::Running,
            PlanExecutionState::Reducing | PlanExecutionState::Verifying => Self::Verifying,
            PlanExecutionState::Completed => Self::Completed,
            PlanExecutionState::Blocked | PlanExecutionState::Failed => Self::Failed,
        }
    }
}

impl V1SwarmPlanState {
    pub fn scheduler_projection(self) -> V1SchedulerProjection<PlanExecutionState> {
        match self {
            Self::Running => V1SchedulerProjection::Exact(PlanExecutionState::Running),
            Self::Verifying => V1SchedulerProjection::Transitional {
                nearest: PlanExecutionState::Verifying,
                reason: "V1 verifying collapses reducing and verifying scheduler phases",
            },
            Self::Completed => V1SchedulerProjection::Exact(PlanExecutionState::Completed),
            Self::Failed => V1SchedulerProjection::Transitional {
                nearest: PlanExecutionState::Failed,
                reason: "V1 failed collapses blocked and failed scheduler terminal states",
            },
            Self::Draft => V1SchedulerProjection::Unsupported {
                reason: "draft plans are not materialized in the scheduler",
            },
            Self::Queued => V1SchedulerProjection::Unsupported {
                reason: "queue ownership is represented by the dispatch layer",
            },
            Self::Cancelled => V1SchedulerProjection::Unsupported {
                reason: "the scheduler terminal aggregate has no distinct cancelled state",
            },
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum LeaseExpiryAction {
    Requeued,
    Failed,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct LeaseExpiry {
    pub lease_id: Uuid,
    pub actor_id: Uuid,
    pub slot_id: Uuid,
    pub fencing_token: u64,
    pub action: LeaseExpiryAction,
    pub expired_at: DateTime<Utc>,
}

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum SchedulerError {
    #[error("duplicate logical actor id: {0}")]
    DuplicateActor(Uuid),
    #[error("duplicate resource slot id: {0}")]
    DuplicateSlot(Uuid),
    #[error("unknown resource slot: {0}")]
    UnknownSlot(Uuid),
    #[error("resource slot is already occupied: {0}")]
    SlotOccupied(Uuid),
    #[error("unknown or stale actor lease: {0}")]
    StaleLease(Uuid),
    #[error(
        "actor lease fencing token mismatch for {lease_id}: expected {expected}, got {actual}"
    )]
    LeaseFenceMismatch {
        lease_id: Uuid,
        expected: u64,
        actual: u64,
    },
    #[error("actor lease expired: {0}")]
    LeaseExpired(Uuid),
    #[error("verifier lease {0} requires an explicit approved or rejected outcome")]
    VerifierVerdictRequired(Uuid),
    #[error("non-verifier lease {0} cannot report a verifier outcome")]
    UnexpectedVerifierVerdict(Uuid),
    #[error("invalid swarm plan: {0}")]
    InvalidPlan(String),
    #[error("physical slot count {configured} exceeds plan maximum {maximum}")]
    TooManySlots { configured: usize, maximum: usize },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SwarmScheduler {
    pub swarm_plan_id: Uuid,
    pub actors: BTreeMap<Uuid, LogicalActor>,
    pub slots: BTreeMap<Uuid, ResourceSlot>,
    pub lease_seconds: i64,
}

impl SwarmScheduler {
    pub fn from_plan(
        plan: &SwarmPlan,
        slots: Vec<ResourceSlot>,
        lease_seconds: i64,
    ) -> Result<Self, SchedulerError> {
        plan.validate()
            .map_err(|error| SchedulerError::InvalidPlan(error.to_string()))?;
        if slots.len() > plan.max_physical_slots {
            return Err(SchedulerError::TooManySlots {
                configured: slots.len(),
                maximum: plan.max_physical_slots,
            });
        }
        Self::new(plan.id, plan.materialize_actors(), slots, lease_seconds)
    }

    pub fn new(
        swarm_plan_id: Uuid,
        actors: Vec<LogicalActor>,
        slots: Vec<ResourceSlot>,
        lease_seconds: i64,
    ) -> Result<Self, SchedulerError> {
        let mut actor_map = BTreeMap::new();
        for actor in actors {
            let actor_id = actor.id;
            if actor_map.insert(actor_id, actor).is_some() {
                return Err(SchedulerError::DuplicateActor(actor_id));
            }
        }
        let mut slot_map = BTreeMap::new();
        for slot in slots {
            let slot_id = slot.id;
            if slot_map.insert(slot_id, slot).is_some() {
                return Err(SchedulerError::DuplicateSlot(slot_id));
            }
        }
        let mut scheduler = Self {
            swarm_plan_id,
            actors: actor_map,
            slots: slot_map,
            lease_seconds: lease_seconds.max(1),
        };
        scheduler.refresh_ready();
        Ok(scheduler)
    }

    pub fn refresh_ready(&mut self) {
        loop {
            let states: BTreeMap<Uuid, LogicalActorState> = self
                .actors
                .iter()
                .map(|(actor_id, actor)| (*actor_id, actor.state))
                .collect();
            let mut updates = Vec::new();
            for actor in self.actors.values() {
                if !matches!(
                    actor.state,
                    LogicalActorState::Pending
                        | LogicalActorState::WaitingDependencies
                        | LogicalActorState::Ready
                ) {
                    continue;
                }

                if actor.attempt >= actor.max_attempts {
                    updates.push((
                        actor.id,
                        LogicalActorState::Failed,
                        Some(format!(
                            "attempt_budget_exhausted:{}/{}",
                            actor.attempt, actor.max_attempts
                        )),
                    ));
                    continue;
                }

                let failed_dependency = actor.dependencies.iter().find_map(|dependency_id| {
                    match states.get(dependency_id) {
                        None => Some((*dependency_id, "missing".to_string())),
                        Some(
                            state @ (LogicalActorState::Blocked
                            | LogicalActorState::Failed
                            | LogicalActorState::Cancelled),
                        ) => Some((*dependency_id, format!("{state:?}").to_lowercase())),
                        _ => None,
                    }
                });
                let (next_state, reason) = if let Some((dependency_id, state)) = failed_dependency {
                    (
                        LogicalActorState::Blocked,
                        Some(format!("dependency_failed:{dependency_id}:{state}")),
                    )
                } else if actor.dependencies.iter().all(|dependency_id| {
                    states.get(dependency_id) == Some(&LogicalActorState::Completed)
                }) {
                    (LogicalActorState::Ready, None)
                } else {
                    (LogicalActorState::WaitingDependencies, None)
                };
                if actor.state != next_state || actor.terminal_reason != reason {
                    updates.push((actor.id, next_state, reason));
                }
            }

            if updates.is_empty() {
                break;
            }
            let mut propagated_terminal_state = false;
            for (actor_id, state, reason) in updates {
                let actor = self
                    .actors
                    .get_mut(&actor_id)
                    .expect("refresh target must exist");
                propagated_terminal_state |= state.is_terminal() && actor.state != state;
                actor.state = state;
                actor.terminal_reason = reason;
            }
            if !propagated_terminal_state {
                break;
            }
        }
    }

    /// Claims the highest critical-path compatible actor. Any compatible node pool may steal it.
    pub fn claim_next(
        &mut self,
        slot_id: Uuid,
        now: DateTime<Utc>,
    ) -> Result<Option<ActorLease>, SchedulerError> {
        self.expire_and_requeue(now);
        self.refresh_ready();
        let slot = self
            .slots
            .get(&slot_id)
            .ok_or(SchedulerError::UnknownSlot(slot_id))?;
        if slot.active_lease.is_some() {
            return Err(SchedulerError::SlotOccupied(slot_id));
        }

        let actor_id = self
            .actors
            .values()
            .filter(|actor| {
                actor.state == LogicalActorState::Ready
                    && actor.attempt < actor.max_attempts
                    && slot.accepts(actor)
            })
            .max_by(|left, right| {
                left.critical_path_weight
                    .cmp(&right.critical_path_weight)
                    .then_with(|| right.id.cmp(&left.id))
            })
            .map(|actor| actor.id);

        let Some(actor_id) = actor_id else {
            return Ok(None);
        };
        let actor = self
            .actors
            .get_mut(&actor_id)
            .expect("selected actor must exist");
        actor.attempt += 1;
        actor.lease_generation += 1;
        actor.terminal_reason = None;
        actor.state = match actor.kind {
            PlanNodeKind::Reducer => LogicalActorState::Reducing,
            PlanNodeKind::Verifier => LogicalActorState::Verifying,
            _ => LogicalActorState::Running,
        };
        actor.updated_at = now;
        let lease_id = Uuid::new_v4();
        let timeout_seconds = i64::try_from(actor.timeout_seconds).unwrap_or(i64::MAX);
        let deadline_at = now
            .checked_add_signed(Duration::seconds(timeout_seconds))
            .unwrap_or(DateTime::<Utc>::MAX_UTC);
        let lease_window_at = now
            .checked_add_signed(Duration::seconds(self.lease_seconds))
            .unwrap_or(DateTime::<Utc>::MAX_UTC);
        let expires_at = deadline_at.min(lease_window_at);
        let lease = ActorLease {
            schema_version: V1_SCHEMA_VERSION,
            id: lease_id,
            actor_id,
            slot_id,
            attempt: actor.attempt,
            fencing_token: actor.lease_generation,
            trace_id: format!("swarm:{}:actor:{actor_id}", self.swarm_plan_id),
            idempotency_key: format!(
                "lease:{}:{}:{}",
                self.swarm_plan_id, actor_id, actor.lease_generation
            ),
            acquired_at: now,
            heartbeat_at: now,
            deadline_at,
            expires_at,
        };
        actor.current_lease = Some(lease.clone());
        self.slots
            .get_mut(&slot_id)
            .expect("validated slot must exist")
            .active_lease = Some(lease.clone());
        Ok(Some(lease))
    }

    pub fn renew_lease(
        &mut self,
        lease_id: Uuid,
        fencing_token: u64,
        now: DateTime<Utc>,
    ) -> Result<ActorLease, SchedulerError> {
        let (slot_id, mut lease) = self.active_lease(lease_id)?;
        Self::validate_lease_fence(&lease, fencing_token)?;
        if lease.expires_at <= now {
            return Err(SchedulerError::LeaseExpired(lease_id));
        }

        lease.heartbeat_at = now;
        let renewed_until = now
            .checked_add_signed(Duration::seconds(self.lease_seconds))
            .unwrap_or(DateTime::<Utc>::MAX_UTC);
        lease.expires_at = lease.deadline_at.min(renewed_until);
        let actor = self
            .actors
            .get_mut(&lease.actor_id)
            .ok_or(SchedulerError::StaleLease(lease_id))?;
        let actor_lease = actor
            .current_lease
            .as_ref()
            .ok_or(SchedulerError::StaleLease(lease_id))?;
        if actor_lease.id != lease_id {
            return Err(SchedulerError::StaleLease(lease_id));
        }
        Self::validate_lease_fence(actor_lease, fencing_token)?;
        actor.current_lease = Some(lease.clone());
        actor.updated_at = now;
        self.slots
            .get_mut(&slot_id)
            .expect("active lease slot must exist")
            .active_lease = Some(lease.clone());
        Ok(lease)
    }

    pub fn finish_lease(
        &mut self,
        lease_id: Uuid,
        fencing_token: u64,
        outcome: LeaseOutcome,
        now: DateTime<Utc>,
    ) -> Result<(), SchedulerError> {
        let (slot_id, lease) = self.active_lease(lease_id)?;
        Self::validate_lease_fence(&lease, fencing_token)?;
        if lease.expires_at <= now {
            return Err(SchedulerError::LeaseExpired(lease_id));
        }

        let actor = self
            .actors
            .get_mut(&lease.actor_id)
            .ok_or(SchedulerError::StaleLease(lease_id))?;
        let actor_lease = actor
            .current_lease
            .as_ref()
            .ok_or(SchedulerError::StaleLease(lease_id))?;
        if actor_lease.id != lease_id {
            return Err(SchedulerError::StaleLease(lease_id));
        }
        Self::validate_lease_fence(actor_lease, fencing_token)?;

        let is_verifier = actor.kind == PlanNodeKind::Verifier;
        if is_verifier && outcome == LeaseOutcome::Completed {
            return Err(SchedulerError::VerifierVerdictRequired(lease_id));
        }
        if !is_verifier
            && matches!(
                outcome,
                LeaseOutcome::VerifierApproved | LeaseOutcome::VerifierRejected
            )
        {
            return Err(SchedulerError::UnexpectedVerifierVerdict(lease_id));
        }

        actor.current_lease = None;
        match outcome {
            LeaseOutcome::Completed => {
                actor.state = LogicalActorState::Completed;
                actor.terminal_reason = None;
            }
            LeaseOutcome::VerifierApproved => {
                actor.state = LogicalActorState::Completed;
                actor.verifier_outcome = Some(VerifierOutcome::Approved);
                actor.terminal_reason = None;
            }
            LeaseOutcome::VerifierRejected => {
                actor.state = LogicalActorState::Blocked;
                actor.verifier_outcome = Some(VerifierOutcome::Rejected);
                actor.terminal_reason = Some("verifier_rejected".to_string());
            }
            LeaseOutcome::Blocked => {
                actor.state = LogicalActorState::Blocked;
                actor.terminal_reason = Some("lease_reported_blocked".to_string());
            }
            LeaseOutcome::Failed => {
                actor.state = LogicalActorState::Failed;
                actor.terminal_reason = Some("lease_reported_failed".to_string());
            }
            LeaseOutcome::Cancelled => {
                actor.state = LogicalActorState::Cancelled;
                actor.terminal_reason = Some("lease_cancelled".to_string());
            }
            LeaseOutcome::Retry if actor.attempt < actor.max_attempts => {
                actor.state = LogicalActorState::Ready;
                actor.terminal_reason = None;
            }
            LeaseOutcome::Retry => {
                actor.state = LogicalActorState::Failed;
                actor.terminal_reason = Some(format!(
                    "attempt_budget_exhausted:{}/{}",
                    actor.attempt, actor.max_attempts
                ));
            }
        }
        actor.updated_at = now;
        self.slots
            .get_mut(&slot_id)
            .expect("lease slot must exist")
            .active_lease = None;
        self.refresh_ready();
        Ok(())
    }

    pub fn expire_and_requeue(&mut self, now: DateTime<Utc>) -> Vec<LeaseExpiry> {
        let expired: Vec<_> = self
            .slots
            .iter()
            .filter_map(|(slot_id, slot)| {
                slot.active_lease
                    .as_ref()
                    .filter(|lease| lease.expires_at <= now)
                    .cloned()
                    .map(|lease| (*slot_id, lease))
            })
            .collect();
        let mut results = Vec::with_capacity(expired.len());
        for (slot_id, lease) in expired {
            let actor = self
                .actors
                .get_mut(&lease.actor_id)
                .expect("leased actor must exist");
            let current_matches = actor.current_lease.as_ref().is_some_and(|current| {
                current.id == lease.id && current.fencing_token == lease.fencing_token
            });
            if !current_matches {
                self.slots
                    .get_mut(&slot_id)
                    .expect("expired lease slot must exist")
                    .active_lease = None;
                continue;
            }

            actor.current_lease = None;
            actor.updated_at = now;
            let action = if actor.attempt < actor.max_attempts {
                actor.state = LogicalActorState::Ready;
                actor.terminal_reason = None;
                LeaseExpiryAction::Requeued
            } else {
                actor.state = LogicalActorState::Failed;
                actor.terminal_reason = Some(format!(
                    "attempt_budget_exhausted_after_timeout:{}/{}",
                    actor.attempt, actor.max_attempts
                ));
                LeaseExpiryAction::Failed
            };
            self.slots
                .get_mut(&slot_id)
                .expect("expired lease slot must exist")
                .active_lease = None;
            results.push(LeaseExpiry {
                lease_id: lease.id,
                actor_id: lease.actor_id,
                slot_id,
                fencing_token: lease.fencing_token,
                action,
                expired_at: now,
            });
        }
        self.refresh_ready();
        results
    }

    pub fn plan_state(&self) -> PlanExecutionState {
        if self
            .actors
            .values()
            .any(|actor| actor.state == LogicalActorState::Failed)
        {
            return PlanExecutionState::Failed;
        }
        if self.actors.values().any(|actor| {
            matches!(
                actor.state,
                LogicalActorState::Blocked | LogicalActorState::Cancelled
            )
        }) {
            return PlanExecutionState::Blocked;
        }

        let verifiers: Vec<_> = self
            .actors
            .values()
            .filter(|actor| actor.kind == PlanNodeKind::Verifier)
            .collect();
        if !verifiers.is_empty()
            && self
                .actors
                .values()
                .all(|actor| actor.state == LogicalActorState::Completed)
            && verifiers
                .iter()
                .all(|actor| actor.verifier_outcome == Some(VerifierOutcome::Approved))
        {
            return PlanExecutionState::Completed;
        }

        let non_verifiers_completed = self
            .actors
            .values()
            .filter(|actor| actor.kind != PlanNodeKind::Verifier)
            .all(|actor| actor.state == LogicalActorState::Completed);
        if non_verifiers_completed
            || verifiers.iter().any(|actor| {
                matches!(
                    actor.state,
                    LogicalActorState::Ready
                        | LogicalActorState::Running
                        | LogicalActorState::Verifying
                        | LogicalActorState::Completed
                )
            })
        {
            return PlanExecutionState::Verifying;
        }
        if self.actors.values().any(|actor| {
            actor.kind == PlanNodeKind::Reducer
                && matches!(
                    actor.state,
                    LogicalActorState::Ready | LogicalActorState::Reducing
                )
        }) {
            return PlanExecutionState::Reducing;
        }
        PlanExecutionState::Running
    }

    fn active_lease(&self, lease_id: Uuid) -> Result<(Uuid, ActorLease), SchedulerError> {
        self.slots
            .iter()
            .find_map(|(slot_id, slot)| {
                slot.active_lease
                    .as_ref()
                    .filter(|lease| lease.id == lease_id)
                    .cloned()
                    .map(|lease| (*slot_id, lease))
            })
            .ok_or(SchedulerError::StaleLease(lease_id))
    }

    fn validate_lease_fence(lease: &ActorLease, fencing_token: u64) -> Result<(), SchedulerError> {
        if lease.fencing_token != fencing_token {
            return Err(SchedulerError::LeaseFenceMismatch {
                lease_id: lease.id,
                expected: lease.fencing_token,
                actual: fencing_token,
            });
        }
        Ok(())
    }

    pub fn snapshot(&self) -> SchedulerSnapshot {
        SchedulerSnapshot {
            plan_state: self.plan_state(),
            logical_actor_count: self.actors.len(),
            ready_actor_count: self
                .actors
                .values()
                .filter(|actor| actor.state == LogicalActorState::Ready)
                .count(),
            active_actor_count: self
                .actors
                .values()
                .filter(|actor| {
                    matches!(
                        actor.state,
                        LogicalActorState::Running
                            | LogicalActorState::Reducing
                            | LogicalActorState::Verifying
                    )
                })
                .count(),
            terminal_actor_count: self
                .actors
                .values()
                .filter(|actor| actor.state.is_terminal())
                .count(),
            physical_slot_count: self.slots.len(),
            occupied_slot_count: self
                .slots
                .values()
                .filter(|slot| slot.active_lease.is_some())
                .count(),
            spawned_actor_processes: 0,
        }
    }
}
