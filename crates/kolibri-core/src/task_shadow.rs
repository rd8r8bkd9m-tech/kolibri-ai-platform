//! Deterministic shadow/parity replay for the V1 task lifecycle.
//!
//! Python remains the production task authority. This module deliberately has
//! no network listener and no adapter that can mutate Python state. It consumes
//! immutable traces, applies the same attempt-budget and completion-binding
//! rules, and emits a deterministic summary for parity verification.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use thiserror::Error;

pub const TASK_TRACE_FIXTURE_SCHEMA: &str = "kolibri.task-trace-fixture.v1";
pub const TASK_SHADOW_SUMMARY_SCHEMA: &str = "kolibri.task-shadow-summary.v1";
pub const COMPLETION_BINDING_SCHEMA: &str = "kolibri.task-completion-binding.v1";
pub const COMPLETION_VERIFIER_SCHEMA: &str = "kolibri.control-plane-completion-verifier.v1";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TaskTraceFixture {
    pub schema_version: String,
    pub trace_id: String,
    pub task: ShadowTaskSpec,
    pub events: Vec<ShadowTaskEvent>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub expected_summary: Option<ShadowTaskSummary>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ShadowTaskSpec {
    pub task_id: String,
    pub max_attempts: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ShadowTaskEvent {
    pub sequence: u64,
    #[serde(rename = "type")]
    pub event_type: String,
    pub occurred_at: DateTime<Utc>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub attempt_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub lease_owner: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fencing_token: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub lease_until: Option<DateTime<Utc>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub result_reference: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub result_sha256: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub binding_sha256: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub verifier: Option<ShadowVerifierProof>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub retryable: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ShadowVerifierProof {
    pub schema_version: String,
    pub verifier: String,
    pub independent: bool,
    pub verdict: String,
    pub fencing_token: u64,
    pub result_sha256: String,
    pub binding_sha256: String,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ShadowTaskState {
    Pending,
    Queued,
    Leased,
    Running,
    Completed,
    Failed,
    DeadLetter,
    Cancelled,
}

impl ShadowTaskState {
    const fn terminal(self) -> bool {
        matches!(
            self,
            Self::Completed | Self::Failed | Self::DeadLetter | Self::Cancelled
        )
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ShadowTaskSummary {
    pub schema_version: String,
    pub mode: String,
    pub authoritative: bool,
    pub authority: String,
    pub task_id: String,
    pub trace_id: String,
    pub state: ShadowTaskState,
    pub attempts_started: u32,
    pub max_attempts: u32,
    pub last_attempt_id: Option<String>,
    pub event_count: u64,
    pub last_sequence: u64,
    pub rejected_stale_completions: u32,
    pub result_reference: Option<String>,
    pub result_sha256: Option<String>,
    pub binding_sha256: Option<String>,
    pub completion_fencing_token: Option<u64>,
    pub verifier_verdict: String,
    pub trace_sha256: String,
}

#[derive(Debug, Clone)]
struct ActiveAttempt {
    attempt_id: String,
    lease_owner: String,
    fencing_token: u64,
    lease_until: DateTime<Utc>,
}

#[derive(Debug)]
struct ReplayState {
    state: ShadowTaskState,
    created: bool,
    attempts_started: u32,
    last_fencing_token: u64,
    active: Option<ActiveAttempt>,
    last_attempt_id: Option<String>,
    rejected_stale_completions: u32,
    result_reference: Option<String>,
    result_sha256: Option<String>,
    binding_sha256: Option<String>,
    completion_fencing_token: Option<u64>,
    verifier_verdict: String,
}

impl Default for ReplayState {
    fn default() -> Self {
        Self {
            state: ShadowTaskState::Pending,
            created: false,
            attempts_started: 0,
            last_fencing_token: 0,
            active: None,
            last_attempt_id: None,
            rejected_stale_completions: 0,
            result_reference: None,
            result_sha256: None,
            binding_sha256: None,
            completion_fencing_token: None,
            verifier_verdict: "not_run".to_string(),
        }
    }
}

impl TaskTraceFixture {
    pub fn replay(&self) -> Result<ShadowTaskSummary, TaskShadowError> {
        self.validate_header()?;
        let mut replay = ReplayState::default();

        for (index, event) in self.events.iter().enumerate() {
            let expected_sequence =
                u64::try_from(index).map_err(|_| TaskShadowError::SequenceOverflow)? + 1;
            if event.sequence != expected_sequence {
                return Err(TaskShadowError::Sequence {
                    expected: expected_sequence,
                    actual: event.sequence,
                });
            }
            apply_event(&self.task, event, &mut replay)?;
        }

        let event_count =
            u64::try_from(self.events.len()).map_err(|_| TaskShadowError::SequenceOverflow)?;
        Ok(ShadowTaskSummary {
            schema_version: TASK_SHADOW_SUMMARY_SCHEMA.to_string(),
            mode: "shadow_parity".to_string(),
            authoritative: false,
            authority: "python-control-plane".to_string(),
            task_id: self.task.task_id.clone(),
            trace_id: self.trace_id.clone(),
            state: replay.state,
            attempts_started: replay.attempts_started,
            max_attempts: self.task.max_attempts,
            last_attempt_id: replay.last_attempt_id,
            event_count,
            last_sequence: self.events.last().map_or(0, |event| event.sequence),
            rejected_stale_completions: replay.rejected_stale_completions,
            result_reference: replay.result_reference,
            result_sha256: replay.result_sha256,
            binding_sha256: replay.binding_sha256,
            completion_fencing_token: replay.completion_fencing_token,
            verifier_verdict: replay.verifier_verdict,
            trace_sha256: canonical_json_sha256(&self.events)?,
        })
    }

    pub fn assert_expected(&self) -> Result<ShadowTaskSummary, TaskShadowError> {
        let actual = self.replay()?;
        let expected = self
            .expected_summary
            .as_ref()
            .ok_or(TaskShadowError::MissingExpectedSummary)?;
        if expected != &actual {
            return Err(TaskShadowError::SummaryMismatch {
                expected: serde_json::to_value(expected)?,
                actual: serde_json::to_value(&actual)?,
            });
        }
        Ok(actual)
    }

    fn validate_header(&self) -> Result<(), TaskShadowError> {
        if self.schema_version != TASK_TRACE_FIXTURE_SCHEMA {
            return Err(TaskShadowError::UnsupportedSchema(
                self.schema_version.clone(),
            ));
        }
        if self.trace_id.trim().is_empty() {
            return Err(TaskShadowError::InvalidSpec("trace_id"));
        }
        if self.task.task_id.trim().is_empty() {
            return Err(TaskShadowError::InvalidSpec("task_id"));
        }
        if !(1..=100).contains(&self.task.max_attempts) {
            return Err(TaskShadowError::InvalidSpec("max_attempts"));
        }
        if self.events.is_empty() {
            return Err(TaskShadowError::InvalidSpec("events"));
        }
        Ok(())
    }
}

fn apply_event(
    spec: &ShadowTaskSpec,
    event: &ShadowTaskEvent,
    replay: &mut ReplayState,
) -> Result<(), TaskShadowError> {
    if replay.state.terminal() {
        return Err(TaskShadowError::InvalidTransition {
            event_type: event.event_type.clone(),
            state: replay.state,
        });
    }
    if event.event_type != "task.created" && !replay.created {
        return Err(TaskShadowError::TaskNotCreated);
    }

    match event.event_type.as_str() {
        "task.created" => apply_created(event, replay),
        "task.leased" => apply_leased(spec, event, replay),
        "task.heartbeat" => apply_heartbeat(event, replay),
        "task.lease_expired" => apply_lease_expired(spec, event, replay),
        "task.completion_rejected" => apply_completion_rejected(event, replay),
        "task.completed" => apply_completed(spec, event, replay),
        "task.failed" => apply_failed(spec, event, replay),
        "task.cancelled" => {
            replay.state = ShadowTaskState::Cancelled;
            replay.active = None;
            Ok(())
        }
        _ => Err(TaskShadowError::UnsupportedEvent(event.event_type.clone())),
    }
}

fn apply_created(event: &ShadowTaskEvent, replay: &mut ReplayState) -> Result<(), TaskShadowError> {
    if replay.created || event.sequence != 1 || replay.state != ShadowTaskState::Pending {
        return Err(TaskShadowError::InvalidTransition {
            event_type: event.event_type.clone(),
            state: replay.state,
        });
    }
    replay.created = true;
    replay.state = ShadowTaskState::Queued;
    Ok(())
}

fn apply_leased(
    spec: &ShadowTaskSpec,
    event: &ShadowTaskEvent,
    replay: &mut ReplayState,
) -> Result<(), TaskShadowError> {
    if replay.state != ShadowTaskState::Queued || replay.active.is_some() {
        return Err(TaskShadowError::InvalidTransition {
            event_type: event.event_type.clone(),
            state: replay.state,
        });
    }
    if replay.attempts_started >= spec.max_attempts {
        return Err(TaskShadowError::AttemptBudgetExhausted {
            attempts: replay.attempts_started,
            maximum: spec.max_attempts,
        });
    }

    let attempt_number = replay.attempts_started + 1;
    let attempt_id = required_string(event, "attempt_id", event.attempt_id.as_deref())?;
    let expected_attempt_id = format!("{}-attempt-{attempt_number}", spec.task_id);
    if attempt_id != expected_attempt_id {
        return Err(TaskShadowError::AttemptIdMismatch {
            expected: expected_attempt_id,
            actual: attempt_id.to_string(),
        });
    }
    let lease_owner = required_string(event, "lease_owner", event.lease_owner.as_deref())?;
    validate_lease_owner(lease_owner)?;
    let fencing_token = event
        .fencing_token
        .ok_or_else(|| missing(event, "fencing_token"))?;
    if fencing_token <= replay.last_fencing_token {
        return Err(TaskShadowError::NonMonotonicFence {
            previous: replay.last_fencing_token,
            actual: fencing_token,
        });
    }
    let lease_until = event
        .lease_until
        .ok_or_else(|| missing(event, "lease_until"))?;
    if lease_until <= event.occurred_at {
        return Err(TaskShadowError::InvalidLeaseWindow);
    }

    replay.attempts_started = attempt_number;
    replay.last_fencing_token = fencing_token;
    replay.last_attempt_id = Some(attempt_id.to_string());
    replay.active = Some(ActiveAttempt {
        attempt_id: attempt_id.to_string(),
        lease_owner: lease_owner.to_string(),
        fencing_token,
        lease_until,
    });
    replay.state = ShadowTaskState::Leased;
    Ok(())
}

fn apply_heartbeat(
    event: &ShadowTaskEvent,
    replay: &mut ReplayState,
) -> Result<(), TaskShadowError> {
    if !matches!(
        replay.state,
        ShadowTaskState::Leased | ShadowTaskState::Running
    ) {
        return Err(TaskShadowError::InvalidTransition {
            event_type: event.event_type.clone(),
            state: replay.state,
        });
    }
    let active = require_matching_fence(event, replay)?;
    if event.occurred_at > active.lease_until {
        return Err(TaskShadowError::LeaseAlreadyExpired);
    }
    let lease_until = event
        .lease_until
        .ok_or_else(|| missing(event, "lease_until"))?;
    if lease_until <= event.occurred_at || lease_until < active.lease_until {
        return Err(TaskShadowError::InvalidLeaseWindow);
    }
    replay
        .active
        .as_mut()
        .ok_or(TaskShadowError::MissingActiveAttempt)?
        .lease_until = lease_until;
    replay.state = ShadowTaskState::Running;
    Ok(())
}

fn apply_lease_expired(
    spec: &ShadowTaskSpec,
    event: &ShadowTaskEvent,
    replay: &mut ReplayState,
) -> Result<(), TaskShadowError> {
    let active = require_matching_fence(event, replay)?;
    if event.occurred_at < active.lease_until {
        return Err(TaskShadowError::LeaseNotExpired);
    }
    replay.active = None;
    replay.state = if replay.attempts_started < spec.max_attempts {
        ShadowTaskState::Queued
    } else {
        ShadowTaskState::DeadLetter
    };
    Ok(())
}

fn apply_completion_rejected(
    event: &ShadowTaskEvent,
    replay: &mut ReplayState,
) -> Result<(), TaskShadowError> {
    let active = replay
        .active
        .as_ref()
        .ok_or(TaskShadowError::MissingActiveAttempt)?;
    let actual_reason = fence_rejection_reason(event, active);
    let Some(actual_reason) = actual_reason else {
        return Err(TaskShadowError::MatchingCompletionWasRejected);
    };
    let declared_reason = required_string(event, "reason", event.reason.as_deref())?;
    if declared_reason != actual_reason {
        return Err(TaskShadowError::FenceReasonMismatch {
            expected: actual_reason.to_string(),
            actual: declared_reason.to_string(),
        });
    }
    replay.rejected_stale_completions += 1;
    Ok(())
}

fn apply_completed(
    spec: &ShadowTaskSpec,
    event: &ShadowTaskEvent,
    replay: &mut ReplayState,
) -> Result<(), TaskShadowError> {
    if !matches!(
        replay.state,
        ShadowTaskState::Leased | ShadowTaskState::Running
    ) {
        return Err(TaskShadowError::InvalidTransition {
            event_type: event.event_type.clone(),
            state: replay.state,
        });
    }
    let active = require_matching_fence(event, replay)?;
    let result_reference =
        required_string(event, "result_reference", event.result_reference.as_deref())?;
    let result = event
        .result
        .as_ref()
        .filter(|value| value.as_object().is_some_and(|object| !object.is_empty()))
        .ok_or(TaskShadowError::InvalidCompletionResult)?;
    validate_result_binding(spec, result, &active)?;

    let result_sha256 = canonical_json_sha256(result)?;
    let supplied_result_sha256 =
        required_string(event, "result_sha256", event.result_sha256.as_deref())?;
    if supplied_result_sha256 != result_sha256 {
        return Err(TaskShadowError::HashMismatch("result_sha256"));
    }
    let binding_sha256 = completion_binding_sha256(
        &spec.task_id,
        &active.attempt_id,
        &active.lease_owner,
        active.fencing_token,
        result_reference,
        &result_sha256,
    )?;
    let supplied_binding_sha256 =
        required_string(event, "binding_sha256", event.binding_sha256.as_deref())?;
    if supplied_binding_sha256 != binding_sha256 {
        return Err(TaskShadowError::HashMismatch("binding_sha256"));
    }
    validate_verifier(event, active.fencing_token, &result_sha256, &binding_sha256)?;

    replay.state = ShadowTaskState::Completed;
    replay.active = None;
    replay.result_reference = Some(result_reference.to_string());
    replay.result_sha256 = Some(result_sha256);
    replay.binding_sha256 = Some(binding_sha256);
    replay.completion_fencing_token = Some(active.fencing_token);
    replay.verifier_verdict = "passed".to_string();
    Ok(())
}

fn apply_failed(
    spec: &ShadowTaskSpec,
    event: &ShadowTaskEvent,
    replay: &mut ReplayState,
) -> Result<(), TaskShadowError> {
    require_matching_fence(event, replay)?;
    required_string(event, "reason", event.reason.as_deref())?;
    replay.active = None;
    replay.state =
        if event.retryable.unwrap_or(false) && replay.attempts_started < spec.max_attempts {
            ShadowTaskState::Queued
        } else if replay.attempts_started >= spec.max_attempts {
            ShadowTaskState::DeadLetter
        } else {
            ShadowTaskState::Failed
        };
    Ok(())
}

fn validate_result_binding(
    spec: &ShadowTaskSpec,
    result: &Value,
    active: &ActiveAttempt,
) -> Result<(), TaskShadowError> {
    let object = result
        .as_object()
        .ok_or(TaskShadowError::InvalidCompletionResult)?;
    let status = object
        .get("status")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_ascii_lowercase();
    if !matches!(
        status.as_str(),
        "completed" | "healthy" | "ok" | "passed" | "ready" | "success"
    ) {
        return Err(TaskShadowError::InvalidCompletionStatus(status));
    }
    optional_field_matches(object.get("task_id"), &spec.task_id, "task_id")?;
    optional_field_matches(object.get("attempt_id"), &active.attempt_id, "attempt_id")?;
    let (node_id, agent_id) = active
        .lease_owner
        .split_once(':')
        .ok_or(TaskShadowError::InvalidLeaseOwner)?;
    optional_field_matches(object.get("node_id"), node_id, "node_id")?;
    optional_field_matches(object.get("agent_id"), agent_id, "agent_id")?;
    if object.get("fencing_token").and_then(Value::as_u64) != Some(active.fencing_token) {
        return Err(TaskShadowError::CompletionFieldMismatch("fencing_token"));
    }
    Ok(())
}

fn optional_field_matches(
    value: Option<&Value>,
    expected: &str,
    field: &'static str,
) -> Result<(), TaskShadowError> {
    if let Some(value) = value
        && value.as_str() != Some(expected)
    {
        return Err(TaskShadowError::CompletionFieldMismatch(field));
    }
    Ok(())
}

fn validate_verifier(
    event: &ShadowTaskEvent,
    fencing_token: u64,
    result_sha256: &str,
    binding_sha256: &str,
) -> Result<(), TaskShadowError> {
    let verifier = event
        .verifier
        .as_ref()
        .ok_or(TaskShadowError::MissingVerifier)?;
    if verifier.schema_version != COMPLETION_VERIFIER_SCHEMA {
        return Err(TaskShadowError::InvalidVerifier("schema_version"));
    }
    if verifier.verifier != "control-plane/home" {
        return Err(TaskShadowError::InvalidVerifier("verifier"));
    }
    if !verifier.independent {
        return Err(TaskShadowError::InvalidVerifier("independent"));
    }
    if verifier.verdict != "passed" {
        return Err(TaskShadowError::InvalidVerifier("verdict"));
    }
    if verifier.fencing_token != fencing_token {
        return Err(TaskShadowError::InvalidVerifier("fencing_token"));
    }
    if verifier.result_sha256 != result_sha256 {
        return Err(TaskShadowError::InvalidVerifier("result_sha256"));
    }
    if verifier.binding_sha256 != binding_sha256 {
        return Err(TaskShadowError::InvalidVerifier("binding_sha256"));
    }
    Ok(())
}

fn require_matching_fence(
    event: &ShadowTaskEvent,
    replay: &ReplayState,
) -> Result<ActiveAttempt, TaskShadowError> {
    let active = replay
        .active
        .as_ref()
        .ok_or(TaskShadowError::MissingActiveAttempt)?;
    if let Some(reason) = fence_rejection_reason(event, active) {
        return Err(TaskShadowError::FenceRejected(reason));
    }
    Ok(active.clone())
}

fn fence_rejection_reason(event: &ShadowTaskEvent, active: &ActiveAttempt) -> Option<&'static str> {
    if event.attempt_id.as_deref() != Some(active.attempt_id.as_str()) {
        return Some("attempt_id_mismatch");
    }
    if event.lease_owner.as_deref() != Some(active.lease_owner.as_str()) {
        return Some("lease_owner_mismatch");
    }
    if event.fencing_token != Some(active.fencing_token) {
        return Some("fencing_token_mismatch");
    }
    None
}

fn validate_lease_owner(value: &str) -> Result<(), TaskShadowError> {
    let Some((node_id, agent_id)) = value.split_once(':') else {
        return Err(TaskShadowError::InvalidLeaseOwner);
    };
    if node_id.trim().is_empty() || agent_id.trim().is_empty() {
        return Err(TaskShadowError::InvalidLeaseOwner);
    }
    Ok(())
}

fn required_string<'a>(
    event: &ShadowTaskEvent,
    field: &'static str,
    value: Option<&'a str>,
) -> Result<&'a str, TaskShadowError> {
    value
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| missing(event, field))
}

fn missing(event: &ShadowTaskEvent, field: &'static str) -> TaskShadowError {
    TaskShadowError::MissingField {
        event_type: event.event_type.clone(),
        field,
    }
}

pub fn completion_binding_sha256(
    task_id: &str,
    attempt_id: &str,
    lease_owner: &str,
    fencing_token: u64,
    result_reference: &str,
    result_sha256: &str,
) -> Result<String, TaskShadowError> {
    canonical_json_sha256(&json!({
        "schema_version": COMPLETION_BINDING_SCHEMA,
        "task_id": task_id,
        "attempt_id": attempt_id,
        "lease_owner": lease_owner,
        "fencing_token": fencing_token,
        "result_reference": result_reference,
        "result_sha256": result_sha256,
    }))
}

pub fn canonical_json_sha256<T: Serialize>(value: &T) -> Result<String, TaskShadowError> {
    let value = serde_json::to_value(value)?;
    let mut canonical = String::new();
    write_canonical_json(&value, &mut canonical)?;
    Ok(format!("sha256:{:x}", Sha256::digest(canonical.as_bytes())))
}

fn write_canonical_json(value: &Value, output: &mut String) -> Result<(), TaskShadowError> {
    match value {
        Value::Null => output.push_str("null"),
        Value::Bool(value) => output.push_str(if *value { "true" } else { "false" }),
        Value::Number(value) => output.push_str(&value.to_string()),
        Value::String(value) => output.push_str(&serde_json::to_string(value)?),
        Value::Array(values) => {
            output.push('[');
            for (index, value) in values.iter().enumerate() {
                if index > 0 {
                    output.push(',');
                }
                write_canonical_json(value, output)?;
            }
            output.push(']');
        }
        Value::Object(values) => {
            output.push('{');
            let mut keys = values.keys().collect::<Vec<_>>();
            keys.sort_unstable();
            for (index, key) in keys.into_iter().enumerate() {
                if index > 0 {
                    output.push(',');
                }
                output.push_str(&serde_json::to_string(key)?);
                output.push(':');
                write_canonical_json(&values[key], output)?;
            }
            output.push('}');
        }
    }
    Ok(())
}

#[derive(Debug, Error)]
pub enum TaskShadowError {
    #[error("unsupported task trace schema {0:?}")]
    UnsupportedSchema(String),
    #[error("invalid task trace field {0}")]
    InvalidSpec(&'static str),
    #[error("task trace sequence overflow")]
    SequenceOverflow,
    #[error("expected event sequence {expected}, got {actual}")]
    Sequence { expected: u64, actual: u64 },
    #[error("task lifecycle event arrived before task.created")]
    TaskNotCreated,
    #[error("unsupported task lifecycle event {0:?}")]
    UnsupportedEvent(String),
    #[error("invalid transition {event_type:?} from {state:?}")]
    InvalidTransition {
        event_type: String,
        state: ShadowTaskState,
    },
    #[error("missing {field} for {event_type}")]
    MissingField {
        event_type: String,
        field: &'static str,
    },
    #[error("attempt budget exhausted: {attempts}/{maximum}")]
    AttemptBudgetExhausted { attempts: u32, maximum: u32 },
    #[error("expected attempt id {expected:?}, got {actual:?}")]
    AttemptIdMismatch { expected: String, actual: String },
    #[error("lease_owner must contain non-empty node and agent ids")]
    InvalidLeaseOwner,
    #[error("fencing token did not increase: previous={previous}, actual={actual}")]
    NonMonotonicFence { previous: u64, actual: u64 },
    #[error("lease window is invalid")]
    InvalidLeaseWindow,
    #[error("active lease was already expired when heartbeat arrived")]
    LeaseAlreadyExpired,
    #[error("lease_expired arrived before lease_until")]
    LeaseNotExpired,
    #[error("task has no active attempt")]
    MissingActiveAttempt,
    #[error("lease fence rejected: {0}")]
    FenceRejected(&'static str),
    #[error("a matching current completion was recorded as rejected")]
    MatchingCompletionWasRejected,
    #[error("expected fence rejection reason {expected:?}, got {actual:?}")]
    FenceReasonMismatch { expected: String, actual: String },
    #[error("completion result must be a non-empty JSON object")]
    InvalidCompletionResult,
    #[error("completion status {0:?} is not successful")]
    InvalidCompletionStatus(String),
    #[error("completion field {0} does not match the active attempt")]
    CompletionFieldMismatch(&'static str),
    #[error("completion hash mismatch in {0}")]
    HashMismatch(&'static str),
    #[error("completion verifier is missing")]
    MissingVerifier,
    #[error("completion verifier field {0} is invalid")]
    InvalidVerifier(&'static str),
    #[error("fixture has no expected_summary")]
    MissingExpectedSummary,
    #[error("shadow summary does not match fixture: expected={expected}, actual={actual}")]
    SummaryMismatch { expected: Value, actual: Value },
    #[error(transparent)]
    Json(#[from] serde_json::Error),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn canonical_json_hash_matches_python_sort_keys_contract() {
        let value = json!({"z": 1, "a": {"β": true, "a": [2, 1]}});
        assert_eq!(
            canonical_json_sha256(&value).expect("canonical hash"),
            "sha256:7cb5818be8201c19a4d656680e22052e1646dc755f6c650079c505da80b5d386"
        );
    }
}
