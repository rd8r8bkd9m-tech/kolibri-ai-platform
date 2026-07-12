//! Executable, non-authoritative Rust shadow of the Python task API.
//!
//! This is deliberately a separate state authority. It never connects to the
//! Python Control Plane or Redis and every projection identifies itself as a
//! shadow. The goal is to exercise the frozen task, attempt, lease, event and
//! verifier contracts before an owner-approved cutover.

use crate::task_shadow::{canonical_json_sha256, completion_binding_sha256};
use chrono::{DateTime, SecondsFormat, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use std::collections::{BTreeMap, VecDeque};
use thiserror::Error;
use uuid::Uuid;

pub const TASK_RUNTIME_SCHEMA: &str = "kolibri.task-runtime-shadow.v1";
pub const TASK_EVENT_SCHEMA: &str = "kolibri.task-event.v1";
pub const RUNTIME_SUMMARY_SCHEMA: &str = "kolibri.runtime-summary.v1";
pub const LEASE_FENCING_SCHEMA: &str = "kolibri.lease-fencing.v1";
pub const COMPLETION_EVIDENCE_SCHEMA: &str = "kolibri.task-completion-evidence.v1";
pub const RUNTIME_COMPLETION_VERIFIER_SCHEMA: &str = "kolibri.control-plane-completion-verifier.v1";
pub const DEFAULT_LEASE_SECONDS: i64 = 60;
const DEFAULT_MAX_ATTEMPTS: u32 = 2;
const MAX_ATTEMPTS: u32 = 100;
const SUCCESS_STATUSES: &[&str] = &["completed", "healthy", "ok", "passed", "ready", "success"];

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub enum RuntimeTaskState {
    Queued,
    Leased,
    Running,
    Completed,
    Failed,
    DeadLetter,
    Cancelled,
}

impl RuntimeTaskState {
    #[must_use]
    pub const fn is_terminal(self) -> bool {
        matches!(
            self,
            Self::Completed | Self::Failed | Self::DeadLetter | Self::Cancelled
        )
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RuntimeTask {
    pub task_id: String,
    pub idempotency_key: String,
    pub kind: String,
    pub state: RuntimeTaskState,
    pub attempt: u32,
    pub max_attempts: u32,
    pub attempt_id: Option<String>,
    pub lease_fencing_schema: String,
    pub fencing_token: u64,
    pub lease_owner: Option<String>,
    pub lease_until: Option<i64>,
    pub heartbeat_at: Option<String>,
    pub result_reference: Option<String>,
    pub result: Option<Value>,
    pub completion_evidence: Option<Value>,
    pub completion_verifier: Option<Value>,
    pub error_type: Option<String>,
    pub error: Option<String>,
    pub created_at: String,
    pub updated_at: String,
    pub envelope: Value,
    pub shadow: ShadowIdentity,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ShadowIdentity {
    pub mode: String,
    pub authoritative: bool,
    pub authority: String,
}

impl Default for ShadowIdentity {
    fn default() -> Self {
        Self {
            mode: "shadow_parity".to_string(),
            authoritative: false,
            authority: "python-control-plane".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RuntimeTaskEvent {
    pub schema_version: String,
    pub id: String,
    pub task_id: String,
    pub sequence: u64,
    #[serde(rename = "type")]
    pub event_type: String,
    pub occurred_at: String,
    pub idempotency_key: String,
    pub payload: Value,
    pub shadow: ShadowIdentity,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RuntimeSummary {
    pub schema_version: String,
    pub mode: String,
    pub authoritative: bool,
    pub authority: String,
    pub observed_at: String,
    pub task_total: usize,
    pub task_states: BTreeMap<String, usize>,
    pub queue_total: usize,
    pub attempt_total: u64,
    pub active_lease_total: usize,
    pub event_total: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
struct IdempotencyClaim {
    request_sha256: String,
    task_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
struct MutationClaim {
    request_sha256: String,
    response: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShadowTaskRuntime {
    pub schema_version: String,
    pub mode: String,
    pub authoritative: bool,
    pub authority: String,
    tasks: BTreeMap<String, RuntimeTask>,
    queue: VecDeque<String>,
    events: BTreeMap<String, Vec<RuntimeTaskEvent>>,
    idempotency: BTreeMap<String, IdempotencyClaim>,
    mutations: BTreeMap<String, MutationClaim>,
}

impl Default for ShadowTaskRuntime {
    fn default() -> Self {
        Self {
            schema_version: TASK_RUNTIME_SCHEMA.to_string(),
            mode: "shadow_parity".to_string(),
            authoritative: false,
            authority: "python-control-plane".to_string(),
            tasks: BTreeMap::new(),
            queue: VecDeque::new(),
            events: BTreeMap::new(),
            idempotency: BTreeMap::new(),
            mutations: BTreeMap::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CreateTaskOutcome {
    pub task: RuntimeTask,
    pub created: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct LeaseRequest {
    pub node_id: String,
    #[serde(default)]
    pub agent_id: Option<String>,
    #[serde(default)]
    pub capabilities: Vec<String>,
    #[serde(default)]
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HeartbeatRequest {
    pub attempt_id: String,
    pub fencing_token: u64,
    pub node_id: String,
    pub agent_id: String,
    #[serde(default)]
    pub state: Option<RuntimeTaskState>,
    #[serde(default)]
    pub progress: Option<Value>,
    #[serde(default)]
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CompleteRequest {
    pub attempt_id: String,
    pub fencing_token: u64,
    pub node_id: String,
    pub agent_id: String,
    pub result_reference: String,
    pub result: Value,
    #[serde(default)]
    pub result_sha256: Option<String>,
    #[serde(default)]
    pub binding_sha256: Option<String>,
    #[serde(default)]
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CompleteOutcome {
    pub task: RuntimeTask,
    pub review_task: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FailRequest {
    pub attempt_id: String,
    pub fencing_token: u64,
    pub node_id: String,
    pub agent_id: String,
    #[serde(default = "default_error_type")]
    pub error_type: String,
    #[serde(default)]
    pub error: String,
    #[serde(default = "default_retry")]
    pub retry: bool,
    #[serde(default)]
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ReapOutcome {
    pub requeued: Vec<String>,
    pub dead_lettered: Vec<String>,
}

impl ShadowTaskRuntime {
    pub fn create_task(
        &mut self,
        envelope: Value,
        now: DateTime<Utc>,
    ) -> Result<CreateTaskOutcome, TaskRuntimeError> {
        let object = envelope.as_object().ok_or_else(|| {
            TaskRuntimeError::InvalidRequest("task_envelope_must_be_object".into())
        })?;
        let task_id = optional_string(object, "task_id")?.map_or_else(
            || format!("KOL-TASK-{}", &Uuid::new_v4().simple().to_string()[..12]),
            str::to_owned,
        );
        validate_nonempty(&task_id, "task_id")?;
        let idempotency_key = optional_string(object, "idempotency_key")?
            .unwrap_or(task_id.as_str())
            .to_string();
        validate_nonempty(&idempotency_key, "idempotency_key")?;
        let request_sha256 = canonical_json_sha256(&envelope)
            .map_err(|error| TaskRuntimeError::InvalidRequest(error.to_string()))?;

        if let Some(existing) = self.idempotency.get(&idempotency_key) {
            if existing.request_sha256 != request_sha256 {
                return Err(TaskRuntimeError::IdempotencyConflict {
                    key: idempotency_key,
                    existing_task_id: existing.task_id.clone(),
                });
            }
            let task =
                self.tasks.get(&existing.task_id).cloned().ok_or_else(|| {
                    TaskRuntimeError::CorruptState("idempotency_task_missing".into())
                })?;
            return Ok(CreateTaskOutcome {
                task,
                created: false,
            });
        }
        if self.tasks.contains_key(&task_id) {
            return Err(TaskRuntimeError::InvalidRequest(
                "task_id_already_exists".into(),
            ));
        }

        let max_attempts = canonical_max_attempts(object)?;
        let kind = optional_string(object, "kind")?
            .unwrap_or("read_only_probe")
            .to_string();
        let timestamp = timestamp(now);
        let task = RuntimeTask {
            task_id: task_id.clone(),
            idempotency_key: idempotency_key.clone(),
            kind,
            state: RuntimeTaskState::Queued,
            attempt: 0,
            max_attempts,
            attempt_id: None,
            lease_fencing_schema: LEASE_FENCING_SCHEMA.to_string(),
            fencing_token: 0,
            lease_owner: None,
            lease_until: None,
            heartbeat_at: None,
            result_reference: None,
            result: None,
            completion_evidence: None,
            completion_verifier: None,
            error_type: None,
            error: None,
            created_at: timestamp.clone(),
            updated_at: timestamp,
            envelope,
            shadow: ShadowIdentity::default(),
        };
        self.tasks.insert(task_id.clone(), task.clone());
        self.queue.push_back(task_id.clone());
        self.idempotency.insert(
            idempotency_key.clone(),
            IdempotencyClaim {
                request_sha256,
                task_id: task_id.clone(),
            },
        );
        self.append_event(
            &task_id,
            "task.created",
            format!("create:{idempotency_key}"),
            json!({"state": "queued", "max_attempts": max_attempts}),
            now,
        )?;
        Ok(CreateTaskOutcome {
            task,
            created: true,
        })
    }

    #[must_use]
    pub fn list_tasks(&self, state: Option<RuntimeTaskState>) -> Vec<RuntimeTask> {
        self.tasks
            .values()
            .filter(|task| state.is_none_or(|wanted| task.state == wanted))
            .cloned()
            .collect()
    }

    #[must_use]
    pub fn queue(&self) -> Vec<String> {
        self.queue.iter().cloned().collect()
    }

    pub fn task(&self, task_id: &str) -> Result<RuntimeTask, TaskRuntimeError> {
        self.tasks
            .get(task_id)
            .cloned()
            .ok_or_else(|| TaskRuntimeError::TaskNotFound(task_id.to_string()))
    }

    pub fn lease(
        &mut self,
        request: &LeaseRequest,
        now: DateTime<Utc>,
    ) -> Result<Option<RuntimeTask>, TaskRuntimeError> {
        validate_nonempty(&request.node_id, "node_id")?;
        let agent_id = request.agent_id.as_deref().unwrap_or(&request.node_id);
        validate_nonempty(agent_id, "agent_id")?;
        let request_value = serde_json::to_value(request)?;
        if let Some(response) =
            self.replay_mutation("lease", request.idempotency_key.as_deref(), &request_value)?
        {
            return serde_json::from_value(response).map_err(TaskRuntimeError::Serialization);
        }
        self.reap_expired(now)?;

        let selected = self.queue.iter().position(|task_id| {
            self.tasks
                .get(task_id)
                .is_some_and(|task| task_compatible(task, request))
        });
        let Some(position) = selected else {
            self.record_mutation(
                "lease",
                request.idempotency_key.as_deref(),
                &request_value,
                &Value::Null,
            )?;
            return Ok(None);
        };
        let task_id = self
            .queue
            .remove(position)
            .ok_or_else(|| TaskRuntimeError::CorruptState("queue_position_missing".into()))?;
        let task = self
            .tasks
            .get_mut(&task_id)
            .ok_or_else(|| TaskRuntimeError::CorruptState("queued_task_missing".into()))?;
        if task.attempt >= task.max_attempts {
            task.state = RuntimeTaskState::DeadLetter;
            return Err(TaskRuntimeError::AttemptBudgetExhausted(task_id));
        }
        task.attempt += 1;
        task.fencing_token = task
            .fencing_token
            .checked_add(1)
            .ok_or_else(|| TaskRuntimeError::CorruptState("fencing_token_overflow".into()))?;
        task.attempt_id = Some(format!("{}-attempt-{}", task.task_id, task.attempt));
        task.lease_owner = Some(format!("{}:{agent_id}", request.node_id));
        task.lease_until = Some(now.timestamp() + DEFAULT_LEASE_SECONDS);
        task.heartbeat_at = Some(timestamp(now));
        task.updated_at = timestamp(now);
        task.state = RuntimeTaskState::Leased;
        let leased = task.clone();
        self.append_event(
            &task_id,
            "task.leased",
            mutation_event_key("lease", request.idempotency_key.as_deref()),
            json!({
                "attempt_id": leased.attempt_id,
                "lease_owner": leased.lease_owner,
                "fencing_token": leased.fencing_token,
                "lease_until": leased.lease_until,
            }),
            now,
        )?;
        let response = serde_json::to_value(&leased)?;
        self.record_mutation(
            "lease",
            request.idempotency_key.as_deref(),
            &request_value,
            &response,
        )?;
        Ok(Some(leased))
    }

    pub fn heartbeat(
        &mut self,
        task_id: &str,
        request: &HeartbeatRequest,
        now: DateTime<Utc>,
    ) -> Result<RuntimeTask, TaskRuntimeError> {
        let request_value = serde_json::to_value(request)?;
        let scope = format!("heartbeat:{task_id}");
        if let Some(response) =
            self.replay_mutation(&scope, request.idempotency_key.as_deref(), &request_value)?
        {
            return serde_json::from_value(response).map_err(TaskRuntimeError::Serialization);
        }
        let task = self.task(task_id)?;
        validate_fence(
            &task,
            &request.attempt_id,
            request.fencing_token,
            &request.node_id,
            &request.agent_id,
        )?;
        if task.state.is_terminal() {
            return Ok(task);
        }
        let task = self
            .tasks
            .get_mut(task_id)
            .ok_or_else(|| TaskRuntimeError::TaskNotFound(task_id.to_string()))?;
        task.state = request.state.unwrap_or(RuntimeTaskState::Running);
        task.lease_until = Some(now.timestamp() + DEFAULT_LEASE_SECONDS);
        task.heartbeat_at = Some(timestamp(now));
        task.updated_at = timestamp(now);
        let updated = task.clone();
        self.append_event(
            task_id,
            "task.heartbeat",
            mutation_event_key(&scope, request.idempotency_key.as_deref()),
            json!({
                "attempt_id": request.attempt_id,
                "lease_owner": updated.lease_owner,
                "fencing_token": request.fencing_token,
                "lease_until": updated.lease_until,
                "state": updated.state,
                "progress": request.progress,
            }),
            now,
        )?;
        let response = serde_json::to_value(&updated)?;
        self.record_mutation(
            &scope,
            request.idempotency_key.as_deref(),
            &request_value,
            &response,
        )?;
        Ok(updated)
    }

    pub fn complete(
        &mut self,
        task_id: &str,
        request: &CompleteRequest,
        now: DateTime<Utc>,
    ) -> Result<CompleteOutcome, TaskRuntimeError> {
        let request_value = serde_json::to_value(request)?;
        let scope = format!("complete:{task_id}");
        if let Some(response) =
            self.replay_mutation(&scope, request.idempotency_key.as_deref(), &request_value)?
        {
            return serde_json::from_value(response).map_err(TaskRuntimeError::Serialization);
        }
        let task = self.task(task_id)?;
        if let Err(error) = validate_fence(
            &task,
            &request.attempt_id,
            request.fencing_token,
            &request.node_id,
            &request.agent_id,
        ) {
            self.append_event(
                task_id,
                "task.completion_rejected",
                mutation_event_key(&scope, request.idempotency_key.as_deref()),
                json!({"reason": error.reason_code(), "attempt_id": request.attempt_id, "fencing_token": request.fencing_token}),
                now,
            )?;
            return Err(error);
        }
        if task.state.is_terminal() {
            return Ok(CompleteOutcome {
                task,
                review_task: None,
            });
        }
        let (evidence, verifier, failed_checks) = completion_proof(&task, request, now)?;
        {
            let stored = self
                .tasks
                .get_mut(task_id)
                .ok_or_else(|| TaskRuntimeError::TaskNotFound(task_id.to_string()))?;
            stored.completion_evidence = Some(evidence);
            stored.completion_verifier = Some(verifier.clone());
            stored.updated_at = timestamp(now);
            if !failed_checks.is_empty() {
                stored.error_type = Some("completion_verification_failed".to_string());
                stored.error = Some(failed_checks.join(","));
            }
        }
        if !failed_checks.is_empty() {
            self.append_event(
                task_id,
                "task.completion_verification_failed",
                mutation_event_key(&scope, request.idempotency_key.as_deref()),
                json!({"failed_checks": failed_checks, "verifier": verifier}),
                now,
            )?;
            return Err(TaskRuntimeError::CompletionVerificationFailed {
                task_id: task_id.to_string(),
                state: task.state,
                verifier,
            });
        }
        let stored = self
            .tasks
            .get_mut(task_id)
            .ok_or_else(|| TaskRuntimeError::TaskNotFound(task_id.to_string()))?;
        stored.state = RuntimeTaskState::Completed;
        stored.result = Some(request.result.clone());
        stored.result_reference = Some(request.result_reference.clone());
        stored.lease_until = None;
        stored.error_type = None;
        stored.error = None;
        stored.updated_at = timestamp(now);
        let completed = stored.clone();
        self.append_event(
            task_id,
            "task.completed",
            mutation_event_key(&scope, request.idempotency_key.as_deref()),
            json!({
                "attempt_id": request.attempt_id,
                "lease_owner": completed.lease_owner,
                "fencing_token": request.fencing_token,
                "result_reference": request.result_reference,
                "completion_evidence": completed.completion_evidence,
                "completion_verifier": completed.completion_verifier,
            }),
            now,
        )?;
        let outcome = CompleteOutcome {
            task: completed,
            review_task: None,
        };
        let response = serde_json::to_value(&outcome)?;
        self.record_mutation(
            &scope,
            request.idempotency_key.as_deref(),
            &request_value,
            &response,
        )?;
        Ok(outcome)
    }

    pub fn fail(
        &mut self,
        task_id: &str,
        request: &FailRequest,
        now: DateTime<Utc>,
    ) -> Result<RuntimeTask, TaskRuntimeError> {
        let request_value = serde_json::to_value(request)?;
        let scope = format!("fail:{task_id}");
        if let Some(response) =
            self.replay_mutation(&scope, request.idempotency_key.as_deref(), &request_value)?
        {
            return serde_json::from_value(response).map_err(TaskRuntimeError::Serialization);
        }
        let task = self.task(task_id)?;
        validate_fence(
            &task,
            &request.attempt_id,
            request.fencing_token,
            &request.node_id,
            &request.agent_id,
        )?;
        if task.state.is_terminal() {
            return Ok(task);
        }
        let task = self
            .tasks
            .get_mut(task_id)
            .ok_or_else(|| TaskRuntimeError::TaskNotFound(task_id.to_string()))?;
        task.error_type = Some(request.error_type.clone());
        task.error = Some(request.error.clone());
        task.lease_owner = None;
        task.lease_until = None;
        task.updated_at = timestamp(now);
        if request.retry && task.attempt < task.max_attempts {
            task.state = RuntimeTaskState::Queued;
            self.queue.push_back(task_id.to_string());
        } else {
            task.state = RuntimeTaskState::Failed;
        }
        let failed = task.clone();
        self.append_event(
            task_id,
            "task.failed",
            mutation_event_key(&scope, request.idempotency_key.as_deref()),
            json!({
                "attempt_id": request.attempt_id,
                "fencing_token": request.fencing_token,
                "error_type": request.error_type,
                "error": request.error,
                "retry": request.retry,
                "state": failed.state,
            }),
            now,
        )?;
        let response = serde_json::to_value(&failed)?;
        self.record_mutation(
            &scope,
            request.idempotency_key.as_deref(),
            &request_value,
            &response,
        )?;
        Ok(failed)
    }

    pub fn reap_expired(&mut self, now: DateTime<Utc>) -> Result<ReapOutcome, TaskRuntimeError> {
        let mut expired: Vec<String> = self
            .tasks
            .values()
            .filter(|task| {
                matches!(
                    task.state,
                    RuntimeTaskState::Leased | RuntimeTaskState::Running
                ) && task
                    .lease_until
                    .is_some_and(|until| until <= now.timestamp())
            })
            .map(|task| task.task_id.clone())
            .collect();
        expired.sort();
        let mut outcome = ReapOutcome {
            requeued: Vec::new(),
            dead_lettered: Vec::new(),
        };
        for task_id in expired {
            let task = self
                .tasks
                .get_mut(&task_id)
                .ok_or_else(|| TaskRuntimeError::CorruptState("expired_task_missing".into()))?;
            let attempt_id = task.attempt_id.clone();
            let lease_owner = task.lease_owner.clone();
            let fencing_token = task.fencing_token;
            task.lease_owner = None;
            task.lease_until = None;
            task.updated_at = timestamp(now);
            if task.attempt < task.max_attempts {
                task.state = RuntimeTaskState::Queued;
                self.queue.push_back(task_id.clone());
                outcome.requeued.push(task_id.clone());
            } else {
                task.state = RuntimeTaskState::DeadLetter;
                outcome.dead_lettered.push(task_id.clone());
            }
            let state = task.state;
            self.append_event(
                &task_id,
                "task.lease_expired",
                format!("lease-expired:{task_id}:{fencing_token}"),
                json!({
                    "attempt_id": attempt_id,
                    "lease_owner": lease_owner,
                    "fencing_token": fencing_token,
                    "state": state,
                }),
                now,
            )?;
        }
        Ok(outcome)
    }

    pub fn events(&self, task_id: &str) -> Result<Vec<RuntimeTaskEvent>, TaskRuntimeError> {
        if !self.tasks.contains_key(task_id) {
            return Err(TaskRuntimeError::TaskNotFound(task_id.to_string()));
        }
        Ok(self.events.get(task_id).cloned().unwrap_or_default())
    }

    #[must_use]
    pub fn summary(&self, now: DateTime<Utc>) -> RuntimeSummary {
        let mut task_states = BTreeMap::new();
        for task in self.tasks.values() {
            let key = serde_json::to_value(task.state)
                .ok()
                .and_then(|value| value.as_str().map(str::to_string))
                .unwrap_or_else(|| "unknown".to_string());
            *task_states.entry(key).or_insert(0) += 1;
        }
        RuntimeSummary {
            schema_version: RUNTIME_SUMMARY_SCHEMA.to_string(),
            mode: self.mode.clone(),
            authoritative: self.authoritative,
            authority: self.authority.clone(),
            observed_at: timestamp(now),
            task_total: self.tasks.len(),
            task_states,
            queue_total: self.queue.len(),
            attempt_total: self
                .tasks
                .values()
                .map(|task| u64::from(task.attempt))
                .sum(),
            active_lease_total: self
                .tasks
                .values()
                .filter(|task| {
                    matches!(
                        task.state,
                        RuntimeTaskState::Leased | RuntimeTaskState::Running
                    )
                })
                .count(),
            event_total: self.events.values().map(Vec::len).sum(),
        }
    }

    fn append_event(
        &mut self,
        task_id: &str,
        event_type: &str,
        idempotency_key: String,
        payload: Value,
        now: DateTime<Utc>,
    ) -> Result<RuntimeTaskEvent, TaskRuntimeError> {
        let events = self.events.entry(task_id.to_string()).or_default();
        if let Some(existing) = events
            .iter()
            .find(|event| event.idempotency_key == idempotency_key)
        {
            if existing.payload == payload && existing.event_type == event_type {
                return Ok(existing.clone());
            }
            return Err(TaskRuntimeError::IdempotencyConflict {
                key: idempotency_key,
                existing_task_id: task_id.to_string(),
            });
        }
        let sequence = u64::try_from(events.len())
            .map_err(|_| TaskRuntimeError::CorruptState("event_sequence_overflow".into()))?
            .checked_add(1)
            .ok_or_else(|| TaskRuntimeError::CorruptState("event_sequence_overflow".into()))?;
        let id_material = json!({
            "task_id": task_id,
            "sequence": sequence,
            "idempotency_key": idempotency_key,
            "payload": payload,
        });
        let digest = canonical_json_sha256(&id_material)
            .map_err(|error| TaskRuntimeError::InvalidRequest(error.to_string()))?;
        let event = RuntimeTaskEvent {
            schema_version: TASK_EVENT_SCHEMA.to_string(),
            id: format!(
                "evt_{}",
                digest
                    .trim_start_matches("sha256:")
                    .chars()
                    .take(24)
                    .collect::<String>()
            ),
            task_id: task_id.to_string(),
            sequence,
            event_type: event_type.to_string(),
            occurred_at: timestamp(now),
            idempotency_key,
            payload,
            shadow: ShadowIdentity::default(),
        };
        events.push(event.clone());
        Ok(event)
    }

    fn replay_mutation(
        &self,
        scope: &str,
        idempotency_key: Option<&str>,
        request: &Value,
    ) -> Result<Option<Value>, TaskRuntimeError> {
        let Some(key) = normalized_idempotency_key(idempotency_key)? else {
            return Ok(None);
        };
        let claim_key = format!("{scope}:{key}");
        let Some(claim) = self.mutations.get(&claim_key) else {
            return Ok(None);
        };
        let request_sha256 = canonical_json_sha256(request)
            .map_err(|error| TaskRuntimeError::InvalidRequest(error.to_string()))?;
        if claim.request_sha256 != request_sha256 {
            return Err(TaskRuntimeError::IdempotencyConflict {
                key: key.to_string(),
                existing_task_id: scope.to_string(),
            });
        }
        Ok(Some(claim.response.clone()))
    }

    fn record_mutation(
        &mut self,
        scope: &str,
        idempotency_key: Option<&str>,
        request: &Value,
        response: &Value,
    ) -> Result<(), TaskRuntimeError> {
        let Some(key) = normalized_idempotency_key(idempotency_key)? else {
            return Ok(());
        };
        let claim_key = format!("{scope}:{key}");
        let request_sha256 = canonical_json_sha256(request)
            .map_err(|error| TaskRuntimeError::InvalidRequest(error.to_string()))?;
        if let Some(existing) = self.mutations.get(&claim_key) {
            if existing.request_sha256 != request_sha256 {
                return Err(TaskRuntimeError::IdempotencyConflict {
                    key: key.to_string(),
                    existing_task_id: scope.to_string(),
                });
            }
            return Ok(());
        }
        self.mutations.insert(
            claim_key,
            MutationClaim {
                request_sha256,
                response: response.clone(),
            },
        );
        Ok(())
    }
}

fn task_compatible(task: &RuntimeTask, request: &LeaseRequest) -> bool {
    if task.state != RuntimeTaskState::Queued || task.attempt >= task.max_attempts {
        return false;
    }
    let Some(envelope) = task.envelope.as_object() else {
        return false;
    };
    let target = envelope
        .get("target_node")
        .or_else(|| envelope.get("required_node"))
        .and_then(Value::as_str);
    if target.is_some_and(|target| target != request.node_id) {
        return false;
    }
    let required = envelope.get("required_capability").and_then(Value::as_str);
    required.is_none_or(|required| request.capabilities.iter().any(|item| item == required))
}

fn completion_proof(
    task: &RuntimeTask,
    request: &CompleteRequest,
    now: DateTime<Utc>,
) -> Result<(Value, Value, Vec<String>), TaskRuntimeError> {
    let result = request.result.as_object();
    let result_sha256 = canonical_json_sha256(&request.result)
        .map_err(|error| TaskRuntimeError::InvalidRequest(error.to_string()))?;
    let binding_sha256 = completion_binding_sha256(
        &task.task_id,
        task.attempt_id.as_deref().unwrap_or_default(),
        task.lease_owner.as_deref().unwrap_or_default(),
        task.fencing_token,
        request.result_reference.trim(),
        &result_sha256,
    )
    .map_err(|error| TaskRuntimeError::InvalidRequest(error.to_string()))?;
    let status = result
        .and_then(|object| object.get("status"))
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_ascii_lowercase();
    let mut checks = BTreeMap::new();
    checks.insert("task", !task.task_id.is_empty());
    checks.insert("result", result.is_some_and(|object| !object.is_empty()));
    checks.insert(
        "attempt",
        result_field_matches(result, "attempt_id", task.attempt_id.as_deref()),
    );
    checks.insert(
        "node",
        result_field_matches(result, "node_id", Some(&request.node_id)),
    );
    checks.insert(
        "agent",
        result_field_matches(result, "agent_id", Some(&request.agent_id)),
    );
    checks.insert("status", SUCCESS_STATUSES.contains(&status.as_str()));
    checks.insert(
        "result_reference",
        !request.result_reference.trim().is_empty()
            && result_path_matches(result, &request.result_reference),
    );
    checks.insert(
        "result_sha256",
        request
            .result_sha256
            .as_deref()
            .is_none_or(|value| value == result_sha256),
    );
    checks.insert(
        "binding_sha256",
        request
            .binding_sha256
            .as_deref()
            .is_none_or(|value| value == binding_sha256),
    );
    checks.insert(
        "fencing_token",
        result
            .and_then(|object| object.get("fencing_token"))
            .and_then(Value::as_u64)
            == Some(task.fencing_token),
    );
    let failed_checks: Vec<String> = checks
        .iter()
        .filter(|(_, passed)| !**passed)
        .map(|(name, _)| (*name).to_string())
        .collect();
    let evidence = json!({
        "schema_version": COMPLETION_EVIDENCE_SCHEMA,
        "task_id": task.task_id,
        "attempt_id": task.attempt_id,
        "lease_owner": task.lease_owner,
        "node_id": request.node_id,
        "agent_id": request.agent_id,
        "fencing_token": task.fencing_token,
        "result_reference": request.result_reference,
        "result_sha256": result_sha256,
        "binding_sha256": binding_sha256,
    });
    let verifier = json!({
        "schema_version": RUNTIME_COMPLETION_VERIFIER_SCHEMA,
        "verifier": "control-plane/home",
        "independent": true,
        "verdict": if failed_checks.is_empty() { "passed" } else { "failed" },
        "checked_at": timestamp(now),
        "task_id": task.task_id,
        "attempt_id": task.attempt_id,
        "lease_owner": task.lease_owner,
        "node_id": request.node_id,
        "agent_id": request.agent_id,
        "fencing_token": task.fencing_token,
        "result_reference": request.result_reference,
        "result_sha256": result_sha256,
        "binding_sha256": binding_sha256,
        "checks": checks,
        "failed_checks": failed_checks,
    });
    let failed_checks = verifier["failed_checks"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .map(str::to_string)
        .collect();
    Ok((evidence, verifier, failed_checks))
}

fn result_field_matches(
    result: Option<&Map<String, Value>>,
    field: &str,
    expected: Option<&str>,
) -> bool {
    let Some(expected) = expected else {
        return false;
    };
    result
        .and_then(|object| object.get(field))
        .is_none_or(|value| value.as_str() == Some(expected))
}

fn result_path_matches(result: Option<&Map<String, Value>>, reference: &str) -> bool {
    result
        .and_then(|object| object.get("result_path"))
        .is_none_or(|value| value.as_str() == Some(reference))
}

fn validate_fence(
    task: &RuntimeTask,
    attempt_id: &str,
    fencing_token: u64,
    node_id: &str,
    agent_id: &str,
) -> Result<(), TaskRuntimeError> {
    let reason = if task.lease_fencing_schema != LEASE_FENCING_SCHEMA {
        Some("lease_fencing_schema_invalid")
    } else if attempt_id.is_empty() {
        Some("attempt_id_missing")
    } else if task.attempt_id.as_deref() != Some(attempt_id) {
        Some("attempt_id_mismatch")
    } else if fencing_token == 0 {
        Some("fencing_token_missing")
    } else if task.fencing_token != fencing_token {
        Some("fencing_token_mismatch")
    } else {
        let (expected_node, expected_agent) = task
            .lease_owner
            .as_deref()
            .and_then(|owner| owner.split_once(':'))
            .unwrap_or(("", ""));
        if expected_node != node_id {
            Some("lease_node_mismatch")
        } else if expected_agent != agent_id {
            Some("lease_agent_mismatch")
        } else {
            None
        }
    };
    match reason {
        None => Ok(()),
        Some(reason) => Err(TaskRuntimeError::LeaseFenceRejected {
            reason: reason.to_string(),
            task_id: task.task_id.clone(),
            state: task.state,
            attempt_id: task.attempt_id.clone(),
            fencing_token: task.fencing_token,
        }),
    }
}

fn canonical_max_attempts(object: &Map<String, Value>) -> Result<u32, TaskRuntimeError> {
    let raw_attempts = optional_u32(object, "max_attempts")?;
    let raw_retries = optional_u32(object, "max_retries")?;
    let legacy_attempts = raw_retries.and_then(|value| value.checked_add(1));
    if raw_retries.is_some() && legacy_attempts.is_none() {
        return Err(TaskRuntimeError::InvalidRequest(
            "max_retries_out_of_range".into(),
        ));
    }
    let attempts = raw_attempts
        .or(legacy_attempts)
        .unwrap_or(DEFAULT_MAX_ATTEMPTS);
    if raw_attempts.is_some() && legacy_attempts.is_some() && raw_attempts != legacy_attempts {
        return Err(TaskRuntimeError::InvalidRequest(
            "attempt_budget_fields_conflict".into(),
        ));
    }
    if !(1..=MAX_ATTEMPTS).contains(&attempts) {
        return Err(TaskRuntimeError::InvalidRequest(
            "max_attempts_out_of_range".into(),
        ));
    }
    Ok(attempts)
}

fn optional_string<'a>(
    object: &'a Map<String, Value>,
    field: &str,
) -> Result<Option<&'a str>, TaskRuntimeError> {
    match object.get(field) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(value)) => Ok(Some(value)),
        Some(_) => Err(TaskRuntimeError::InvalidRequest(format!(
            "{field}_must_be_string"
        ))),
    }
}

fn optional_u32(object: &Map<String, Value>, field: &str) -> Result<Option<u32>, TaskRuntimeError> {
    match object.get(field) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::Number(value)) => value
            .as_u64()
            .and_then(|number| u32::try_from(number).ok())
            .map(Some)
            .ok_or_else(|| TaskRuntimeError::InvalidRequest(format!("{field}_must_be_an_integer"))),
        Some(_) => Err(TaskRuntimeError::InvalidRequest(format!(
            "{field}_must_be_an_integer"
        ))),
    }
}

fn validate_nonempty(value: &str, field: &str) -> Result<(), TaskRuntimeError> {
    if value.trim().is_empty() || value.len() > 300 {
        return Err(TaskRuntimeError::InvalidRequest(format!("{field}_invalid")));
    }
    Ok(())
}

fn normalized_idempotency_key(value: Option<&str>) -> Result<Option<&str>, TaskRuntimeError> {
    match value {
        None => Ok(None),
        Some(value) => {
            validate_nonempty(value, "idempotency_key")?;
            Ok(Some(value))
        }
    }
}

fn mutation_event_key(scope: &str, idempotency_key: Option<&str>) -> String {
    idempotency_key.map_or_else(
        || format!("{scope}:{}", Uuid::new_v4()),
        |key| format!("{scope}:{key}"),
    )
}

fn timestamp(value: DateTime<Utc>) -> String {
    value.to_rfc3339_opts(SecondsFormat::Micros, true)
}

fn default_error_type() -> String {
    "runtime_error".to_string()
}

const fn default_retry() -> bool {
    true
}

#[derive(Debug, Error)]
pub enum TaskRuntimeError {
    #[error("task not found: {0}")]
    TaskNotFound(String),
    #[error("invalid task request: {0}")]
    InvalidRequest(String),
    #[error("idempotency key {key:?} conflicts with task {existing_task_id:?}")]
    IdempotencyConflict {
        key: String,
        existing_task_id: String,
    },
    #[error("lease fence rejected: {reason}")]
    LeaseFenceRejected {
        reason: String,
        task_id: String,
        state: RuntimeTaskState,
        attempt_id: Option<String>,
        fencing_token: u64,
    },
    #[error("completion verification failed for task {task_id}")]
    CompletionVerificationFailed {
        task_id: String,
        state: RuntimeTaskState,
        verifier: Value,
    },
    #[error("attempt budget exhausted for task {0}")]
    AttemptBudgetExhausted(String),
    #[error("shadow runtime state is corrupt: {0}")]
    CorruptState(String),
    #[error("shadow runtime serialization failed: {0}")]
    Serialization(#[from] serde_json::Error),
}

impl TaskRuntimeError {
    #[must_use]
    pub fn reason_code(&self) -> &str {
        match self {
            Self::LeaseFenceRejected { reason, .. } => reason,
            Self::TaskNotFound(_) => "task_not_found",
            Self::InvalidRequest(_) => "invalid_request",
            Self::IdempotencyConflict { .. } => "idempotency_conflict",
            Self::CompletionVerificationFailed { .. } => "completion_verification_failed",
            Self::AttemptBudgetExhausted(_) => "attempt_budget_exhausted",
            Self::CorruptState(_) => "corrupt_state",
            Self::Serialization(_) => "serialization_failed",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;

    fn instant(second: i64) -> DateTime<Utc> {
        Utc.timestamp_opt(1_752_192_000 + second, 0)
            .single()
            .expect("valid fixture timestamp")
    }

    fn lease_request(node: &str, agent: &str, key: &str) -> LeaseRequest {
        LeaseRequest {
            node_id: node.to_string(),
            agent_id: Some(agent.to_string()),
            capabilities: vec!["read_only_probe".to_string()],
            idempotency_key: Some(key.to_string()),
        }
    }

    #[test]
    fn task_lifecycle_is_idempotent_fenced_and_truth_gated() {
        let mut runtime = ShadowTaskRuntime::default();
        let envelope = json!({
            "task_id": "task-parity",
            "idempotency_key": "create-task-parity",
            "kind": "read_only_probe",
            "required_capability": "read_only_probe",
            "max_attempts": 2,
        });
        let created = runtime.create_task(envelope.clone(), instant(0)).unwrap();
        assert!(created.created);
        let replayed = runtime.create_task(envelope, instant(1)).unwrap();
        assert!(!replayed.created);
        assert_eq!(runtime.events("task-parity").unwrap().len(), 1);

        let first = runtime
            .lease(&lease_request("worker-a", "agent-a", "lease-1"), instant(1))
            .unwrap()
            .unwrap();
        assert_eq!(first.attempt_id.as_deref(), Some("task-parity-attempt-1"));
        assert_eq!(first.fencing_token, 1);
        let replayed_first = runtime
            .lease(&lease_request("worker-a", "agent-a", "lease-1"), instant(2))
            .unwrap()
            .unwrap();
        assert_eq!(replayed_first.attempt_id, first.attempt_id);
        assert_eq!(runtime.events("task-parity").unwrap().len(), 2);

        let heartbeat = HeartbeatRequest {
            attempt_id: first.attempt_id.clone().unwrap(),
            fencing_token: 1,
            node_id: "worker-a".to_string(),
            agent_id: "agent-a".to_string(),
            state: None,
            progress: None,
            idempotency_key: Some("heartbeat-1".to_string()),
        };
        let running = runtime
            .heartbeat("task-parity", &heartbeat, instant(10))
            .unwrap();
        assert_eq!(running.state, RuntimeTaskState::Running);
        let reap = runtime.reap_expired(instant(71)).unwrap();
        assert_eq!(reap.requeued, vec!["task-parity"]);

        let second = runtime
            .lease(
                &lease_request("worker-b", "agent-b", "lease-2"),
                instant(72),
            )
            .unwrap()
            .unwrap();
        assert_eq!(second.attempt_id.as_deref(), Some("task-parity-attempt-2"));
        assert_eq!(second.fencing_token, 2);

        let stale = CompleteRequest {
            attempt_id: "task-parity-attempt-1".to_string(),
            fencing_token: 1,
            node_id: "worker-a".to_string(),
            agent_id: "agent-a".to_string(),
            result_reference: "cas://stale".to_string(),
            result: json!({"status": "completed", "fencing_token": 1}),
            result_sha256: None,
            binding_sha256: None,
            idempotency_key: Some("stale-complete".to_string()),
        };
        assert!(matches!(
            runtime.complete("task-parity", &stale, instant(73)),
            Err(TaskRuntimeError::LeaseFenceRejected { ref reason, .. }) if reason == "attempt_id_mismatch"
        ));

        let result = json!({
            "status": "completed",
            "task_id": "task-parity",
            "attempt_id": "task-parity-attempt-2",
            "node_id": "worker-b",
            "agent_id": "agent-b",
            "fencing_token": 2,
            "output": "verified Rust shadow result",
        });
        let request = CompleteRequest {
            attempt_id: second.attempt_id.clone().unwrap(),
            fencing_token: 2,
            node_id: "worker-b".to_string(),
            agent_id: "agent-b".to_string(),
            result_reference: "cas://sha256/rust-shadow-result".to_string(),
            result,
            result_sha256: None,
            binding_sha256: None,
            idempotency_key: Some("complete-2".to_string()),
        };
        let completed = runtime
            .complete("task-parity", &request, instant(75))
            .unwrap();
        assert_eq!(completed.task.state, RuntimeTaskState::Completed);
        assert_eq!(
            completed.task.completion_verifier.as_ref().unwrap()["verdict"],
            "passed"
        );
        let replayed = runtime
            .complete("task-parity", &request, instant(80))
            .unwrap();
        assert_eq!(replayed, completed);
        assert_eq!(runtime.summary(instant(80)).attempt_total, 2);
        assert_eq!(runtime.summary(instant(80)).active_lease_total, 0);
    }

    #[test]
    fn completion_without_content_bound_evidence_never_becomes_completed() {
        let mut runtime = ShadowTaskRuntime::default();
        runtime
            .create_task(
                json!({"task_id": "truth-gate", "idempotency_key": "truth-create"}),
                instant(0),
            )
            .unwrap();
        let leased = runtime
            .lease(&lease_request("worker", "agent", "truth-lease"), instant(1))
            .unwrap()
            .unwrap();
        let rejected = CompleteRequest {
            attempt_id: leased.attempt_id.unwrap(),
            fencing_token: leased.fencing_token,
            node_id: "worker".to_string(),
            agent_id: "agent".to_string(),
            result_reference: String::new(),
            result: json!({"status": "completed"}),
            result_sha256: None,
            binding_sha256: None,
            idempotency_key: Some("truth-complete".to_string()),
        };
        assert!(matches!(
            runtime.complete("truth-gate", &rejected, instant(2)),
            Err(TaskRuntimeError::CompletionVerificationFailed { .. })
        ));
        assert_eq!(
            runtime.task("truth-gate").unwrap().state,
            RuntimeTaskState::Leased
        );
    }

    #[test]
    fn task_creation_rejects_idempotency_conflicts_and_legacy_budget_conflicts() {
        let mut runtime = ShadowTaskRuntime::default();
        runtime
            .create_task(
                json!({"task_id": "one", "idempotency_key": "same", "max_retries": 1}),
                instant(0),
            )
            .unwrap();
        assert!(matches!(
            runtime.create_task(
                json!({"task_id": "two", "idempotency_key": "same", "max_retries": 1}),
                instant(0)
            ),
            Err(TaskRuntimeError::IdempotencyConflict { .. })
        ));
        assert!(matches!(
            runtime.create_task(
                json!({"task_id": "bad", "idempotency_key": "bad", "max_attempts": 3, "max_retries": 1}),
                instant(0)
            ),
            Err(TaskRuntimeError::InvalidRequest(ref reason)) if reason == "attempt_budget_fields_conflict"
        ));
    }
}
