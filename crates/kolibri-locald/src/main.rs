use std::collections::{HashMap, VecDeque};
use std::net::SocketAddr;
use std::path::PathBuf;
use std::process::Stdio;
use std::time::Duration;

use axum::{
    extract::{Path as AxumPath, Query, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use chrono::{DateTime, Utc};
use clap::Parser;
use kolibri_core::{policy::requires_approval, TaskEnvelope, TaskEvent, TaskStatus};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tokio::{net::TcpListener, time::sleep};
use tokio::{
    process::Command,
    sync::{broadcast, RwLock},
    time::timeout,
};
use tracing::{info, warn};
use uuid::Uuid;

#[derive(Parser, Debug)]
#[command(name = "kolibri-locald")]
#[command(about = "Kolibri Control Station local daemon")]
struct Cli {
    #[arg(long, env = "KOLIBRI_CONFIG")]
    config: Option<PathBuf>,
    #[arg(long, default_value_t = false)]
    doctor: bool,
    #[arg(long, default_value_t = false)]
    init: bool,
    #[arg(long, default_value_t = false)]
    reset_dev: bool,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct DaemonConfig {
    bind_host: String,
    bind_port: u16,
    node_id: String,
    node_role: String,
    local_endpoint: String,
    data_dir: PathBuf,
    terminal_timeout_seconds: u64,
    terminal_max_output_bytes: usize,
    lease_stale_seconds: i64,
    allowed_terminal_commands: Vec<String>,
    terminal_requires_approval: bool,
    terminal_default_user: String,
}

impl Default for DaemonConfig {
    fn default() -> Self {
        Self {
            bind_host: "127.0.0.1".to_string(),
            bind_port: 3101,
            node_id: "node-locald-01".to_string(),
            node_role: "local-control".to_string(),
            local_endpoint: "127.0.0.1:3101".to_string(),
            data_dir: PathBuf::from("/tmp/kolibri-ai"),
            terminal_timeout_seconds: 12,
            terminal_max_output_bytes: 65_536,
            lease_stale_seconds: 90,
            allowed_terminal_commands: vec![
                "help".to_string(),
                "status".to_string(),
                "nodes".to_string(),
                "tasks".to_string(),
                "ls".to_string(),
                "pwd".to_string(),
                "date".to_string(),
                "whoami".to_string(),
            ],
            terminal_requires_approval: true,
            terminal_default_user: "operator".to_string(),
        }
    }
}

impl DaemonConfig {
    fn merge_env(mut self) -> Self {
        if let Ok(v) = std::env::var("KOLIBRI_NODE_ID") {
            self.node_id = v;
        }
        if let Ok(v) = std::env::var("KOLIBRI_NODE_ROLE") {
            self.node_role = v;
        }
        if let Ok(v) = std::env::var("KOLIBRI_LOCAL_ENDPOINT") {
            self.local_endpoint = v;
        }
        if let Ok(v) = std::env::var("KOLIBRI_DATA_DIR") {
            self.data_dir = PathBuf::from(v);
        }
        if let Ok(v) = std::env::var("KOLIBRI_LOCALD_STALE_HEARTBEAT_SECONDS") {
            if let Ok(parsed) = v.parse::<i64>() {
                self.lease_stale_seconds = parsed;
            }
        }
        if let Ok(v) = std::env::var("KOLIBRI_LOCALD_TERMINAL_TIMEOUT_SECONDS") {
            if let Ok(parsed) = v.parse::<u64>() {
                self.terminal_timeout_seconds = parsed;
            }
        }
        if let Ok(v) = std::env::var("KOLIBRI_LOCALD_TERMINAL_MAX_OUTPUT_BYTES") {
            if let Ok(parsed) = v.parse::<usize>() {
                self.terminal_max_output_bytes = parsed;
            }
        }
        self
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct NodeRecord {
    id: String,
    name: String,
    hostname: String,
    ip: String,
    region: String,
    status: String,
    endpoint: String,
    capabilities: Vec<String>,
    last_seen_at: DateTime<Utc>,
    created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize)]
struct AgentRecord {
    id: String,
    node_id: String,
    name: String,
    kind: String,
    status: String,
    version: String,
    capabilities: Vec<String>,
    current_task_id: Option<Uuid>,
    last_heartbeat_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct TerminalCommand {
    command: String,
    actor: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct TerminalRunResult {
    command: String,
    exit_code: i32,
    stdout: String,
    stderr: String,
    started_at: DateTime<Utc>,
    finished_at: DateTime<Utc>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct TerminalSessionRecord {
    id: Uuid,
    task_id: Option<Uuid>,
    agent_id: Option<String>,
    node_id: Option<String>,
    actor: String,
    status: String,
    created_at: DateTime<Utc>,
    last_activity_at: DateTime<Utc>,
    command_count: usize,
    runs: Vec<TerminalRunResult>,
    policy_approved: bool,
    approval_id: Option<String>,
}

#[derive(Debug, Clone)]
struct TaskRuntime {
    envelope: TaskEnvelope,
    events: Vec<TaskEvent>,
    heartbeat_at: Option<DateTime<Utc>>,
    output: Option<Value>,
    artifacts: Vec<String>,
}

#[derive(Debug, Clone)]
struct PlaneEvent {
    seq: u64,
    event_type: String,
    task_id: Option<Uuid>,
    agent_id: Option<String>,
    node_id: Option<String>,
    severity: String,
    detail: String,
    trace_id: String,
    occurred_at: DateTime<Utc>,
}

#[derive(Debug)]
struct ControlPlaneState {
    nodes: HashMap<String, NodeRecord>,
    agents: HashMap<String, AgentRecord>,
    tasks: HashMap<Uuid, TaskRuntime>,
    task_queue: VecDeque<Uuid>,
    terminal_sessions: HashMap<Uuid, TerminalSessionRecord>,
    events: Vec<PlaneEvent>,
    task_counter: u64,
    event_counter: u64,
}

impl ControlPlaneState {
    fn new() -> Self {
        Self {
            nodes: HashMap::new(),
            agents: HashMap::new(),
            tasks: HashMap::new(),
            task_queue: VecDeque::new(),
            terminal_sessions: HashMap::new(),
            events: Vec::new(),
            task_counter: 0,
            event_counter: 0,
        }
    }

    fn enqueue_if_schedulable(&mut self, task_id: Uuid) {
        if !self.task_queue.contains(&task_id) {
            let Some(task) = self.tasks.get(&task_id) else {
                return;
            };
            if matches!(task.envelope.status, TaskStatus::Scheduled) {
                self.task_queue.push_back(task_id);
            }
        }
    }

    fn task_next_scheduled_from_queue(&mut self) -> Option<Uuid> {
        while let Some(task_id) = self.task_queue.pop_front() {
            let now_scheduled = self.tasks.get(&task_id).is_some_and(|t| {
                t.envelope.status == TaskStatus::Scheduled && t.envelope.worker_id.is_none()
            });
            if now_scheduled {
                return Some(task_id);
            }
        }
        None
    }

    fn queue_remove(&mut self, task_id: &Uuid) {
        self.task_queue.retain(|id| id != task_id);
    }

    fn next_routable_agent(
        &self,
        required_capability: Option<String>,
        preferred_node_id: Option<String>,
    ) -> Option<String> {
        let mut candidates = self
            .agents
            .values()
            .filter(|agent| agent.status == "online" && agent.current_task_id.is_none())
            .filter(|agent| {
                required_capability
                    .as_ref()
                    .is_none_or(|required| agent.capabilities.iter().any(|item| item == required))
            })
            .collect::<Vec<_>>();

        if let Some(node_id) = preferred_node_id {
            if let Some(found) = candidates.iter().find(|agent| agent.node_id == node_id) {
                return Some(found.id.clone());
            }
        }
        candidates.sort_by_key(|a| a.current_task_id.is_none());
        candidates.first().map(|agent| agent.id.clone())
    }

    fn push_event(
        &mut self,
        event_type: impl Into<String>,
        task_id: Option<Uuid>,
        agent_id: Option<String>,
        node_id: Option<String>,
        detail: impl Into<String>,
        trace_id: impl Into<String>,
    ) {
        self.event_counter = self.event_counter.saturating_add(1);
        let event = PlaneEvent {
            seq: self.event_counter,
            event_type: event_type.into(),
            task_id,
            agent_id,
            node_id,
            severity: "info".to_string(),
            detail: detail.into(),
            trace_id: trace_id.into(),
            occurred_at: Utc::now(),
        };
        self.events.push(event);
        if self.events.len() > 2048 {
            let extra = self.events.len() - 2048;
            self.events.drain(0..extra);
        }
    }
}

#[derive(Clone)]
struct AppState {
    cfg: DaemonConfig,
    store: std::sync::Arc<RwLock<ControlPlaneState>>,
    event_tx: broadcast::Sender<Value>,
}

#[derive(Debug, Serialize)]
struct ApiError {
    code: String,
    detail: String,
}

#[derive(Debug, Deserialize)]
struct TaskSubmitRequest {
    #[serde(default)]
    task_id: Option<Uuid>,
    owner: String,
    kind: String,
    #[serde(default)]
    payload: Value,
    #[serde(default = "default_public")]
    sensitivity: String,
    #[serde(default)]
    policy: Option<Value>,
    #[serde(default)]
    preferred_node: Option<String>,
    #[serde(default)]
    required_capability: Option<String>,
}

#[derive(Debug, Deserialize)]
struct TaskLeaseRequest {
    #[serde(default)]
    task_id: Option<Uuid>,
    #[serde(default)]
    agent_id: Option<String>,
    #[serde(default)]
    required_capability: Option<String>,
}

#[derive(Debug, Deserialize)]
struct TaskHeartbeatRequest {
    #[serde(default)]
    agent_id: Option<String>,
}

#[derive(Debug, Deserialize)]
struct TaskResultRequest {
    #[serde(default)]
    message: Option<String>,
    #[serde(default)]
    output: Option<Value>,
    #[serde(default)]
    artifact_ids: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct TaskApprovalRequest {
    #[serde(default)]
    approver: String,
    #[serde(default)]
    comment: Option<String>,
}

#[derive(Debug, Deserialize)]
struct AgentEnrollRequest {
    id: Option<String>,
    node_id: String,
    name: String,
    kind: String,
    version: String,
    #[serde(default)]
    capabilities: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct AgentHeartbeat {
    id: String,
    node_id: String,
    #[serde(default)]
    status: String,
    #[serde(default)]
    current_task_id: Option<Uuid>,
    #[serde(default)]
    capabilities: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct RouteRequest {
    #[serde(default)]
    task_id: Option<Uuid>,
    #[serde(default)]
    required_capability: Option<String>,
    #[serde(default)]
    preferred_node_id: Option<String>,
}

#[derive(Debug, Deserialize)]
struct TerminalCreateRequest {
    #[serde(default)]
    task_id: Option<Uuid>,
    #[serde(default)]
    agent_id: Option<String>,
    #[serde(default)]
    node_id: Option<String>,
    #[serde(default)]
    actor: Option<String>,
    #[serde(default)]
    approval_id: Option<String>,
}

#[derive(Debug, Deserialize)]
struct TaskArtifactsRequest {
    #[serde(default)]
    artifact_ids: Vec<String>,
}

#[derive(Debug, Serialize)]
struct EnvelopeResponse {
    task_id: Uuid,
    status: TaskStatus,
    task: TaskEnvelope,
    events: Vec<TaskEvent>,
}

fn default_public() -> String {
    "public".to_string()
}

fn invalid_input(detail: impl Into<String>) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(ApiError {
            code: "invalid_request".to_string(),
            detail: detail.into(),
        }),
    )
        .into_response()
}

fn not_found(detail: impl Into<String>) -> Response {
    (
        StatusCode::NOT_FOUND,
        Json(ApiError {
            code: "not_found".to_string(),
            detail: detail.into(),
        }),
    )
        .into_response()
}

fn conflict(detail: impl Into<String>) -> Response {
    (
        StatusCode::CONFLICT,
        Json(ApiError {
            code: "conflict".to_string(),
            detail: detail.into(),
        }),
    )
        .into_response()
}

fn forbidden(detail: impl Into<String>) -> Response {
    (
        StatusCode::FORBIDDEN,
        Json(ApiError {
            code: "forbidden".to_string(),
            detail: detail.into(),
        }),
    )
        .into_response()
}

fn extract_trace_id(headers: &HeaderMap) -> String {
    headers
        .get("x-trace-id")
        .and_then(|v| v.to_str().ok())
        .map(ToString::to_string)
        .unwrap_or_else(|| Uuid::new_v4().to_string())
}

#[allow(dead_code)]
fn task_state_for_health(status: &TaskStatus) -> &'static str {
    match status {
        TaskStatus::Submitted
        | TaskStatus::Validated
        | TaskStatus::Scheduled
        | TaskStatus::WaitingApproval => "queued",
        TaskStatus::Running | TaskStatus::PostCheck => "leased",
        TaskStatus::Completed | TaskStatus::Audited => "completed",
        TaskStatus::Failed => "failed",
        TaskStatus::Canceled | TaskStatus::Blocked => "blocked",
    }
}

fn should_allow_command(cfg: &DaemonConfig, command: &str) -> bool {
    let command = command.trim();
    if command.is_empty() {
        return false;
    }
    cfg.allowed_terminal_commands
        .iter()
        .any(|allowed| command == allowed || command.starts_with(allowed.as_str()))
}

fn normalize_slice_for_output(value: String, max_len: usize) -> String {
    if value.len() > max_len {
        let truncated: String = value.chars().take((max_len / 2).max(1)).collect();
        format!("{truncated}...")
    } else {
        value
    }
}

async fn task_event_publisher(tx: broadcast::Sender<Value>, mut rx: broadcast::Receiver<Value>) {
    let mut backlog: VecDeque<String> = VecDeque::new();
    loop {
        match rx.recv().await {
            Ok(event) => {
                if let Ok(text) = serde_json::to_string(&event) {
                    backlog.push_back(text);
                    while backlog.len() > 256 {
                        backlog.pop_front();
                    }
                }
            }
            Err(err) => {
                warn!(error = %err, "event bus channel closed");
                break;
            }
        }
    }
    let _ = tx;
    let _ = backlog;
}

async fn list_nodes(State(state): State<AppState>) -> Json<Value> {
    let store = state.store.read().await;
    let mut nodes: Vec<NodeRecord> = store.nodes.values().cloned().collect();
    if nodes.is_empty() {
        nodes.push(NodeRecord {
            id: state.cfg.node_id.clone(),
            name: state.cfg.node_id.clone(),
            hostname: state.cfg.node_id.clone(),
            ip: "127.0.0.1".to_string(),
            region: "local".to_string(),
            status: "online".to_string(),
            endpoint: state.cfg.local_endpoint.clone(),
            capabilities: vec!["control-plane".to_string(), "task-routing".to_string()],
            last_seen_at: Utc::now(),
            created_at: Utc::now(),
        });
    }
    Json(json!({
      "nodes": nodes,
      "total": store.nodes.len(),
      "generated_at": Utc::now(),
    }))
}

#[allow(dead_code)]
async fn list_nodes_with_state(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> impl IntoResponse {
    let _ = extract_trace_id(&headers);
    list_nodes(State(state)).await
}

async fn list_agents(State(state): State<AppState>) -> Json<Value> {
    let store = state.store.read().await;
    let mut agents = Vec::new();
    for agent in store.agents.values() {
        agents.push(agent);
    }
    Json(json!({
      "agents": agents,
      "total": agents.len(),
      "generated_at": Utc::now(),
    }))
}

async fn list_tasks(State(state): State<AppState>) -> Json<Value> {
    let store = state.store.read().await;
    let tasks: Vec<Value> = store
        .tasks
        .values()
        .map(|item| {
            json!({
              "task_id": item.envelope.task_id,
              "kind": item.envelope.kind,
              "status": format!("{:?}", item.envelope.status),
              "sensitivity": item.envelope.sensitivity,
              "requires_approval": item.envelope.requires_approval,
              "worker_id": item.envelope.worker_id,
              "updated_at": item.envelope.updated_at,
            })
        })
        .collect();
    Json(json!({"tasks": tasks, "total": tasks.len()}))
}

async fn route_task(
    State(state): State<AppState>,
    Query(req): Query<RouteRequest>,
    headers: HeaderMap,
) -> impl IntoResponse {
    let _ = extract_trace_id(&headers);
    let mut store = state.store.write().await;
    let task_id = req.task_id;
    let required_capability = req.required_capability.clone();
    if let Some(task_id) = task_id {
        let task_opt = store.tasks.get(&task_id);
        let Some(task) = task_opt else {
            return not_found(format!("Task {task_id} not found"));
        };
        if task.envelope.status != TaskStatus::Scheduled {
            return conflict("task is not scheduled");
        }
    }

    let selected_agent =
        store.next_routable_agent(required_capability.clone(), req.preferred_node_id);
    if selected_agent.is_none() {
        return not_found("no routable agents");
    }

    let required_capability =
        required_capability.map(|value| format!("route selected with {:?}", value));
    let trace_id = extract_trace_id(&headers);
    let required_capability = if let Some(v) = required_capability {
        v
    } else {
        "route selected".to_string()
    };
    store.push_event(
        "route.selected",
        req.task_id,
        selected_agent.clone(),
        None,
        required_capability,
        trace_id,
    );
    Json(json!({ "agent_id": selected_agent, "state": "routable" })).into_response()
}

#[allow(dead_code)]
async fn factory_status(State(state): State<AppState>) -> Json<Value> {
    let store = state.store.read().await;
    let mut by_state: HashMap<&str, usize> = HashMap::new();
    for task in store.tasks.values() {
        let key = task_state_for_health(&task.envelope.status);
        *by_state.entry(key).or_insert(0) += 1;
    }

    let running = by_state.get("leased").copied().unwrap_or(0);
    let queued = by_state.get("queued").copied().unwrap_or(0);

    Json(json!({
      "status": "online",
      "tick": store.task_counter,
      "mode": "strict_local",
      "nodes_total": store.nodes.len().max(1),
      "nodes_online": store.nodes.values().filter(|node| node.status == "online").count(),
      "agents_total": store.agents.len(),
      "agents_online": store.agents.values().filter(|agent| agent.status == "online").count(),
      "tasks": {
        "queued": queued,
        "running": running,
        "total": store.tasks.len(),
      },
      "lease_backlog": store.task_queue.len(),
      "generated_at": Utc::now(),
    }))
}

async fn health(State(state): State<AppState>) -> Json<Value> {
    Json(json!({
      "status": "ok",
      "service": "kolibri-locald",
      "version": state.cfg.bind_port.to_string(),
      "time": Utc::now(),
    }))
}

async fn metadata(State(state): State<AppState>) -> Json<Value> {
    let sample = TaskEnvelope::new(
        "local-core",
        "metadata.ping",
        json!({ "capability": "tasks,events,lease,approval,heartbeat,route,terminal,nodes,agents" }),
        "public",
    );
    Json(json!({
      "service": "kolibri-locald",
      "version": "0.2.0",
      "host": state.cfg.local_endpoint,
      "sample_task": sample.task_id,
      "node_id": state.cfg.node_id,
    }))
}

async fn submit_task(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(mut req): Json<TaskSubmitRequest>,
) -> impl IntoResponse {
    if req.owner.trim().is_empty() || req.kind.trim().is_empty() {
        return invalid_input("owner and kind are required");
    }
    let trace_id = extract_trace_id(&headers);
    let mut store = state.store.write().await;

    let task_id = req.task_id.take().unwrap_or_else(Uuid::new_v4);
    if let Some(task) = store.tasks.get(&task_id) {
        return (
            StatusCode::OK,
            Json(EnvelopeResponse {
                task_id,
                status: task.envelope.status,
                task: task.envelope.clone(),
                events: task.events.clone(),
            }),
        )
            .into_response();
    }

    let preferred_node = req.preferred_node.clone();
    let required_capability = req.required_capability.clone();
    let mut policy = req.policy.unwrap_or_else(|| json!({}));
    if let Some(required_capability) = required_capability {
        if let Some(policy_map) = policy.as_object_mut() {
            policy_map.insert(
                "required_capability".to_string(),
                json!(required_capability.clone()),
            );
        }
    }
    let task_kind = req.kind.clone();
    let requires_approval = requires_approval(&task_kind, &req.sensitivity, &policy);
    let mut envelope =
        TaskEnvelope::new(req.owner, task_kind.clone(), req.payload, req.sensitivity);
    envelope.task_id = task_id;
    envelope.policy = policy;
    envelope.requires_approval = requires_approval;
    envelope.trace_id = trace_id.clone();
    envelope.run_id = task_id.to_string();
    envelope.policy_id = "default".to_string();
    envelope.transition_to(TaskStatus::Validated);
    if !requires_approval {
        envelope.transition_to(TaskStatus::Scheduled);
    } else {
        envelope.transition_to(TaskStatus::WaitingApproval);
    }

    let mut runtime = TaskRuntime {
        envelope,
        events: Vec::new(),
        heartbeat_at: None,
        output: None,
        artifacts: Vec::new(),
    };
    runtime.events.push(TaskEvent {
        sequence: 1,
        task_id,
        name: "task.created".to_string(),
        status: runtime.envelope.status,
        detail: format!("task {} submitted", task_kind),
        trace_id: runtime.envelope.trace_id.clone(),
        occurred_at: Utc::now(),
    });

    if !requires_approval {
        runtime.events.push(TaskEvent {
            sequence: 2,
            task_id,
            name: "task.scheduled".to_string(),
            status: TaskStatus::Scheduled,
            detail: "task scheduled for assignment".to_string(),
            trace_id: runtime.envelope.trace_id.clone(),
            occurred_at: Utc::now(),
        });
    } else {
        runtime.events.push(TaskEvent {
            sequence: 2,
            task_id,
            name: "task.waiting_approval".to_string(),
            status: TaskStatus::WaitingApproval,
            detail: "task waiting explicit approval".to_string(),
            trace_id: runtime.envelope.trace_id.clone(),
            occurred_at: Utc::now(),
        });
    }

    store.tasks.insert(task_id, runtime);
    if !requires_approval {
        store.enqueue_if_schedulable(task_id);
    }
    store.task_counter = store.task_counter.saturating_add(1);
    store.push_event(
        if requires_approval {
            "task.submitted.waiting_approval"
        } else {
            "task.submitted.scheduled"
        },
        Some(task_id),
        preferred_node,
        None,
        "task created",
        trace_id.clone(),
    );

    let tx_payload = json!({
        "event_type": "task.submit",
        "task_id": task_id,
        "trace_id": trace_id,
        "require_approval": requires_approval,
        "timestamp": Utc::now(),
    });
    let _ = state.event_tx.send(tx_payload);
    let task = store.tasks.get(&task_id).expect("task exists");
    let response = EnvelopeResponse {
        task_id,
        status: task.envelope.status,
        task: task.envelope.clone(),
        events: task.events.clone(),
    };
    (StatusCode::CREATED, Json(response)).into_response()
}

async fn get_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<Uuid>,
) -> impl IntoResponse {
    let store = state.store.read().await;
    match store.tasks.get(&task_id) {
        Some(task) => (
            StatusCode::OK,
            Json(EnvelopeResponse {
                task_id,
                status: task.envelope.status,
                task: task.envelope.clone(),
                events: task.events.clone(),
            }),
        )
            .into_response(),
        None => not_found(format!("Task {task_id} not found")),
    }
}

async fn get_task_artifacts(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<Uuid>,
) -> impl IntoResponse {
    let store = state.store.read().await;
    match store.tasks.get(&task_id) {
        Some(task) => {
            Json(json!({ "task_id": task_id, "artifacts": task.artifacts })).into_response()
        }
        None => not_found(format!("Task {task_id} not found")),
    }
}

async fn post_task_artifacts(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<Uuid>,
    Json(req): Json<TaskArtifactsRequest>,
) -> impl IntoResponse {
    let mut store = state.store.write().await;
    let Some(task) = store.tasks.get_mut(&task_id) else {
        return not_found(format!("Task {task_id} not found"));
    };
    let trace_id = task.envelope.trace_id.clone();
    for artifact in req.artifact_ids {
        if !task.artifacts.contains(&artifact) {
            task.artifacts.push(artifact.clone());
            task.events.push(TaskEvent {
                sequence: task.events.len() as u64 + 1,
                task_id,
                name: "task.artifact.attached".to_string(),
                status: task.envelope.status,
                detail: artifact,
                trace_id: task.envelope.trace_id.clone(),
                occurred_at: Utc::now(),
            });
        }
    }
    let artifacts = task.artifacts.clone();
    let _ = task;
    store.push_event(
        "task.artifact.attached",
        Some(task_id),
        None,
        None,
        "task artifacts updated",
        trace_id,
    );
    (
        StatusCode::OK,
        Json(json!({ "task_id": task_id, "artifacts": artifacts })),
    )
        .into_response()
}

async fn lease_task(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<TaskLeaseRequest>,
) -> impl IntoResponse {
    let mut store = state.store.write().await;
    let preferred_agent = req.agent_id.clone();
    let required_capability = req.required_capability.clone();
    let task_id = if let Some(task_id) = req.task_id {
        task_id
    } else {
        let candidate = store
            .task_queue
            .front()
            .copied()
            .or_else(|| store.task_next_scheduled_from_queue());
        if candidate.is_none() {
            return not_found("No task available for leasing");
        }
        candidate.expect("available task")
    };

    let agent_id = if let Some(agent_id) = preferred_agent {
        Some(agent_id)
    } else {
        store.next_routable_agent(required_capability, None)
    };
    let Some(agent_id) = agent_id else {
        return not_found("No routable agents");
    };

    let trace_id = extract_trace_id(&headers);
    let mut agent_node: Option<String> = None;
    let response_task = {
        let Some(task) = store.tasks.get_mut(&task_id) else {
            return not_found(format!("Task {task_id} not found"));
        };
        if task.envelope.status != TaskStatus::Scheduled {
            return conflict("task is not scheduled");
        }
        if task.envelope.worker_id.is_some() {
            return conflict("task already leased");
        }

        task.envelope.worker_id = Some(agent_id.clone());
        task.envelope.transition_to(TaskStatus::Running);
        task.heartbeat_at = Some(Utc::now());
        task.events.push(TaskEvent {
            sequence: task.events.len() as u64 + 1,
            task_id,
            name: "task.assigned".to_string(),
            status: TaskStatus::Running,
            detail: format!("leased by {agent_id}"),
            trace_id: task.envelope.trace_id.clone(),
            occurred_at: Utc::now(),
        });

        EnvelopeResponse {
            task_id,
            status: task.envelope.status,
            task: task.envelope.clone(),
            events: task.events.clone(),
        }
    };
    if let Some(agent) = store.agents.get_mut(&agent_id) {
        agent.current_task_id = Some(task_id);
        agent.status = "busy".to_string();
        agent.last_heartbeat_at = Some(Utc::now());
        agent_node = Some(agent.node_id.clone());
    }
    store.queue_remove(&task_id);
    store.push_event(
        "task.assigned",
        Some(task_id),
        Some(agent_id.clone()),
        agent_node,
        "leased with lease_task".to_string(),
        trace_id,
    );

    let _ = state.event_tx.send(json!({
        "event_type": "task.assigned",
        "task_id": task_id,
        "agent_id": agent_id,
        "timestamp": Utc::now(),
    }));

    (StatusCode::OK, Json(response_task)).into_response()
}

async fn assign_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<Uuid>,
    Json(req): Json<TaskLeaseRequest>,
) -> impl IntoResponse {
    let payload = Json(TaskLeaseRequest {
        task_id: Some(task_id),
        agent_id: req.agent_id,
        required_capability: req.required_capability,
    });
    lease_task(State(state), HeaderMap::new(), payload).await
}

async fn heartbeat_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<Uuid>,
    Json(req): Json<TaskHeartbeatRequest>,
) -> impl IntoResponse {
    let mut store = state.store.write().await;
    let agent_id = req.agent_id.clone();
    let (heartbeat_at, status, trace_id) = {
        let Some(task) = store.tasks.get_mut(&task_id) else {
            return not_found(format!("Task {task_id} not found"));
        };
        task.heartbeat_at = Some(Utc::now());
        if let Some(agent_id) = agent_id.as_deref() {
            task.envelope.worker_id = Some(agent_id.to_string());
        }
        task.envelope.updated_at = Utc::now();
        task.events.push(TaskEvent {
            sequence: task.events.len() as u64 + 1,
            task_id,
            name: "task.heartbeat".to_string(),
            status: task.envelope.status,
            detail: "heartbeat".to_string(),
            trace_id: task.envelope.trace_id.clone(),
            occurred_at: Utc::now(),
        });
        (
            task.heartbeat_at,
            task.envelope.status,
            task.envelope.trace_id.clone(),
        )
    };
    if let Some(agent_id) = agent_id.as_deref() {
        if let Some(agent) = store.agents.get_mut(agent_id) {
            agent.last_heartbeat_at = Some(Utc::now());
            if agent.status != "online" {
                agent.status = "online".to_string();
            }
        }
    }
    store.push_event(
        "task.heartbeat",
        Some(task_id),
        agent_id,
        None,
        "heartbeat".to_string(),
        trace_id,
    );
    (
        StatusCode::OK,
        Json(json!({
          "task_id": task_id,
          "status": status,
          "heartbeat_at": heartbeat_at,
        })),
    )
        .into_response()
}

async fn complete_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<Uuid>,
    Json(req): Json<TaskResultRequest>,
) -> impl IntoResponse {
    let mut store = state.store.write().await;
    let message = req
        .message
        .clone()
        .unwrap_or_else(|| "completed".to_string());
    let output = req.output;
    let artifact_ids = req.artifact_ids;
    let (response, agent_id, trace_id) = {
        let Some(task) = store.tasks.get_mut(&task_id) else {
            return not_found(format!("Task {task_id} not found"));
        };
        if !matches!(task.envelope.status, TaskStatus::Running) {
            return conflict("Task is not running");
        }
        task.envelope.transition_to(TaskStatus::PostCheck);
        task.output = output;
        task.envelope.transition_to(TaskStatus::Completed);
        task.envelope.transition_to(TaskStatus::Audited);
        for artifact in artifact_ids {
            if !task.artifacts.contains(&artifact) {
                task.artifacts.push(artifact);
            }
        }
        task.events.push(TaskEvent {
            sequence: task.events.len() as u64 + 1,
            task_id,
            name: "task.completed".to_string(),
            status: task.envelope.status,
            detail: message.clone(),
            trace_id: task.envelope.trace_id.clone(),
            occurred_at: Utc::now(),
        });
        let response = EnvelopeResponse {
            task_id,
            status: task.envelope.status,
            task: task.envelope.clone(),
            events: task.events.clone(),
        };
        (
            response,
            task.envelope.worker_id.clone(),
            task.envelope.trace_id.clone(),
        )
    };
    if let Some(agent_id) = agent_id.as_deref() {
        if let Some(agent) = store.agents.get_mut(agent_id) {
            agent.current_task_id = None;
            agent.status = "online".to_string();
        }
    }
    store.queue_remove(&task_id);
    store.push_event(
        "task.completed",
        Some(task_id),
        agent_id,
        None,
        message,
        trace_id,
    );
    (StatusCode::OK, Json(response)).into_response()
}

async fn fail_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<Uuid>,
    Json(req): Json<TaskResultRequest>,
) -> impl IntoResponse {
    let mut store = state.store.write().await;
    let message = req.message.clone().unwrap_or_else(|| "failed".to_string());
    let output = req.output;
    let artifact_ids = req.artifact_ids;
    let (response, agent_id, trace_id) = {
        let Some(task) = store.tasks.get_mut(&task_id) else {
            return not_found(format!("Task {task_id} not found"));
        };
        if !matches!(
            task.envelope.status,
            TaskStatus::Running | TaskStatus::PostCheck
        ) {
            return conflict("Task is not in a fail-ready state");
        }
        task.envelope.transition_to(TaskStatus::Failed);
        task.output = output;
        task.envelope.transition_to(TaskStatus::Audited);
        for artifact in artifact_ids {
            if !task.artifacts.contains(&artifact) {
                task.artifacts.push(artifact);
            }
        }
        task.events.push(TaskEvent {
            sequence: task.events.len() as u64 + 1,
            task_id,
            name: "task.failed".to_string(),
            status: TaskStatus::Failed,
            detail: message.clone(),
            trace_id: task.envelope.trace_id.clone(),
            occurred_at: Utc::now(),
        });
        let response = EnvelopeResponse {
            task_id,
            status: task.envelope.status,
            task: task.envelope.clone(),
            events: task.events.clone(),
        };
        (
            response,
            task.envelope.worker_id.clone(),
            task.envelope.trace_id.clone(),
        )
    };
    if let Some(agent_id) = agent_id.as_deref() {
        if let Some(agent) = store.agents.get_mut(agent_id) {
            agent.current_task_id = None;
            agent.status = "online".to_string();
        }
    }
    store.queue_remove(&task_id);
    store.push_event(
        "task.failed",
        Some(task_id),
        agent_id,
        None,
        "task failed",
        trace_id,
    );
    (StatusCode::OK, Json(response)).into_response()
}

async fn cancel_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<Uuid>,
) -> impl IntoResponse {
    let mut store = state.store.write().await;
    let (response, agent_id, trace_id) = {
        let Some(task) = store.tasks.get_mut(&task_id) else {
            return not_found(format!("Task {task_id} not found"));
        };
        match task.envelope.status {
            TaskStatus::Completed
            | TaskStatus::Audited
            | TaskStatus::Failed
            | TaskStatus::Canceled => {
                return conflict("Task not cancellable");
            }
            _ => {}
        }
        task.envelope.transition_to(TaskStatus::Canceled);
        task.envelope.updated_at = Utc::now();
        task.events.push(TaskEvent {
            sequence: task.events.len() as u64 + 1,
            task_id,
            name: "task.canceled".to_string(),
            status: TaskStatus::Canceled,
            detail: "task was canceled by operator".to_string(),
            trace_id: task.envelope.trace_id.clone(),
            occurred_at: Utc::now(),
        });
        let response = EnvelopeResponse {
            task_id,
            status: task.envelope.status,
            task: task.envelope.clone(),
            events: task.events.clone(),
        };
        (
            response,
            task.envelope.worker_id.clone(),
            task.envelope.trace_id.clone(),
        )
    };
    if let Some(agent_id) = agent_id.as_deref() {
        if let Some(agent) = store.agents.get_mut(agent_id) {
            agent.current_task_id = None;
            agent.status = "online".to_string();
        }
    }
    store.queue_remove(&task_id);
    store.push_event(
        "task.canceled",
        Some(task_id),
        agent_id,
        None,
        "canceled by operator",
        trace_id,
    );
    (StatusCode::OK, Json(response)).into_response()
}

async fn approve_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<Uuid>,
    Json(req): Json<TaskApprovalRequest>,
) -> impl IntoResponse {
    let mut store = state.store.write().await;
    let comment = req
        .comment
        .clone()
        .unwrap_or_else(|| "approved".to_string());
    let response = {
        let Some(task) = store.tasks.get_mut(&task_id) else {
            return not_found(format!("Task {task_id} not found"));
        };
        if task.envelope.status != TaskStatus::WaitingApproval {
            return conflict("Task is not waiting for approval");
        }
        task.envelope.transition_to(TaskStatus::Validated);
        task.envelope.transition_to(TaskStatus::Scheduled);
        task.envelope.requires_approval = false;
        task.envelope.trust.approver = Some(req.approver);
        task.envelope.updated_at = Utc::now();
        task.events.push(TaskEvent {
            sequence: task.events.len() as u64 + 1,
            task_id,
            name: "task.approved".to_string(),
            status: TaskStatus::Scheduled,
            detail: comment,
            trace_id: task.envelope.trace_id.clone(),
            occurred_at: Utc::now(),
        });
        EnvelopeResponse {
            task_id,
            status: task.envelope.status,
            task: task.envelope.clone(),
            events: task.events.clone(),
        }
    };
    store.enqueue_if_schedulable(task_id);
    (StatusCode::OK, Json(response)).into_response()
}

async fn reject_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<Uuid>,
    Json(req): Json<TaskApprovalRequest>,
) -> impl IntoResponse {
    let mut store = state.store.write().await;
    let comment = req
        .comment
        .clone()
        .unwrap_or_else(|| "rejected".to_string());
    let (response, agent_id, trace_id) = {
        let Some(task) = store.tasks.get_mut(&task_id) else {
            return not_found(format!("Task {task_id} not found"));
        };
        if task.envelope.status != TaskStatus::WaitingApproval {
            return conflict("Task is not waiting for approval");
        }
        task.envelope.transition_to(TaskStatus::Blocked);
        task.envelope.trust.approver = Some(req.approver);
        task.envelope.updated_at = Utc::now();
        task.events.push(TaskEvent {
            sequence: task.events.len() as u64 + 1,
            task_id,
            name: "task.rejected".to_string(),
            status: TaskStatus::Blocked,
            detail: comment,
            trace_id: task.envelope.trace_id.clone(),
            occurred_at: Utc::now(),
        });
        let response = EnvelopeResponse {
            task_id,
            status: task.envelope.status,
            task: task.envelope.clone(),
            events: task.events.clone(),
        };
        (
            response,
            task.envelope.worker_id.clone(),
            task.envelope.trace_id.clone(),
        )
    };
    if let Some(agent_id) = agent_id.as_deref() {
        if let Some(agent) = store.agents.get_mut(agent_id) {
            agent.current_task_id = None;
            agent.status = "online".to_string();
        }
    }
    store.queue_remove(&task_id);
    store.push_event(
        "task.rejected",
        Some(task_id),
        agent_id,
        None,
        "task rejected",
        trace_id,
    );
    (StatusCode::OK, Json(response)).into_response()
}

async fn task_summary(State(state): State<AppState>) -> Json<Value> {
    let store = state.store.read().await;
    let mut counts: HashMap<&str, usize> = HashMap::new();
    for task in store.tasks.values() {
        let key = format!("{:?}", task.envelope.status).to_lowercase();
        *counts
            .entry(Box::leak(key.clone().into_boxed_str()))
            .or_insert(0) += 1;
    }
    Json(json!({
      "service": "kolibri-locald",
      "version": "0.2.0",
      "total": store.tasks.len(),
      "queue_depth": store.task_queue.len(),
      "queue_backend": "memory",
      "lease_backend": "memory",
      "by_status": counts,
      "queued": store.tasks.values().filter(|task| {
          matches!(task.envelope.status, TaskStatus::Scheduled | TaskStatus::Validated | TaskStatus::Submitted)
      }).count(),
      "running": store.tasks.values().filter(|task| {
          matches!(task.envelope.status, TaskStatus::Running | TaskStatus::PostCheck)
      }).count(),
    }))
}

async fn queue_diagnostics(State(state): State<AppState>) -> Json<Value> {
    let store = state.store.read().await;
    let mut stale: Vec<Value> = Vec::new();
    let mut leased = 0;
    for task in store.tasks.values() {
        if matches!(
            task.envelope.status,
            TaskStatus::Running | TaskStatus::PostCheck
        ) {
            leased += 1;
            if let Some(heartbeat_at) = task.heartbeat_at {
                if is_stale_heartbeat(heartbeat_at, state.cfg.lease_stale_seconds) {
                    stale.push(json!({
                      "task_id": task.envelope.task_id,
                      "worker_id": task.envelope.worker_id,
                      "heartbeat_at": heartbeat_at,
                    }));
                }
            }
        }
    }
    let stale_count = stale.len();
    Json(json!({
      "state": "ok",
      "queued_total": store.task_queue.len(),
      "active_total": leased,
      "stale_leases": stale,
      "stale_leases_total": stale_count,
      "queue_health": if stale_count == 0 { "ok" } else { "degraded" },
    }))
}

async fn events_feed(
    State(state): State<AppState>,
    Query(query): Query<HashMap<String, String>>,
) -> Json<Value> {
    let limit = query
        .get("limit")
        .and_then(|raw| raw.parse::<usize>().ok())
        .unwrap_or(200)
        .min(1000);
    let event_type_filter = query.get("type").cloned();
    let task_id_filter = query
        .get("task_id")
        .and_then(|raw| Uuid::parse_str(raw).ok());

    let store = state.store.read().await;
    let mut events: Vec<Value> = store
        .events
        .iter()
        .rev()
        .filter(|event| match (&event_type_filter, &task_id_filter) {
            (Some(t), Some(task_id)) => event.event_type == *t && event.task_id == Some(*task_id),
            (Some(t), None) => event.event_type == *t,
            (None, Some(task_id)) => event.task_id == Some(*task_id),
            (None, None) => true,
        })
        .take(limit)
        .map(|event| {
            json!({
                "seq": event.seq,
                "type": event.event_type,
                "severity": event.severity,
                "task_id": event.task_id,
                "agent_id": event.agent_id,
                "node_id": event.node_id,
                "trace_id": event.trace_id,
                "detail": event.detail,
                "occurred_at": event.occurred_at,
            })
        })
        .collect();
    events.reverse();
    Json(json!({ "events": events, "total": events.len() }))
}

async fn enroll_agent(
    State(state): State<AppState>,
    Json(req): Json<AgentEnrollRequest>,
) -> impl IntoResponse {
    if req.name.trim().is_empty() || req.node_id.trim().is_empty() {
        return invalid_input("agent name and node_id are required");
    }
    let name = req.name.clone();
    let kind = req.kind.clone();
    let version = req.version.clone();
    let desired_id = req.id;
    let node_id = req.node_id;
    let mut capabilities = req.capabilities;
    let mut store = state.store.write().await;

    if store.nodes.contains_key(&node_id) {
        let node_name = store.nodes.get(&node_id).map(|node| node.id.clone());
        let id = desired_id.unwrap_or_else(|| {
            format!(
                "{}-{}",
                node_id,
                Uuid::new_v4()
                    .to_string()
                    .split('-')
                    .next()
                    .unwrap_or("agent")
            )
        });
        if store.agents.contains_key(&id) {
            return conflict("agent already exists");
        }
        let now = Utc::now();
        let agent = AgentRecord {
            id: id.clone(),
            node_id: node_id.clone(),
            name: name.clone(),
            kind: kind.clone(),
            status: "online".to_string(),
            version: version.clone(),
            capabilities: std::mem::take(&mut capabilities),
            current_task_id: None,
            last_heartbeat_at: Some(now),
        };
        let node_id_for_event = node_name.unwrap_or_else(|| node_id.clone());
        store.agents.insert(id.clone(), agent);
        store.push_event(
            "agent.enrolled",
            None,
            Some(id.clone()),
            Some(node_id_for_event),
            format!("agent enrolled on node {}", node_id),
            Uuid::new_v4().to_string(),
        );
        return (
            StatusCode::CREATED,
            Json(json!({ "id": id, "status": "enrolled" })),
        )
            .into_response();
    }
    if node_id == state.cfg.node_id {
        let id = desired_id.unwrap_or_else(|| format!("agent-{}", Uuid::new_v4()));
        if store.agents.contains_key(&id) {
            return conflict("agent already exists");
        }
        let now = Utc::now();
        let agent = AgentRecord {
            id: id.clone(),
            node_id,
            name,
            kind,
            status: "online".to_string(),
            version,
            capabilities: std::mem::take(&mut capabilities),
            current_task_id: None,
            last_heartbeat_at: Some(now),
        };
        store.agents.insert(id.clone(), agent);
        store.push_event(
            "agent.enrolled",
            None,
            Some(id.clone()),
            Some(state.cfg.node_id.clone()),
            "agent enrolled on local node",
            Uuid::new_v4().to_string(),
        );
        return (
            StatusCode::CREATED,
            Json(json!({ "id": id, "status": "enrolled" })),
        )
            .into_response();
    }
    not_found("Node not found")
}

async fn heartbeat_agent(
    State(state): State<AppState>,
    Json(req): Json<AgentHeartbeat>,
) -> impl IntoResponse {
    let mut store = state.store.write().await;
    let Some(agent) = store.agents.get_mut(&req.id) else {
        return not_found("Agent not found");
    };
    agent.last_heartbeat_at = Some(Utc::now());
    agent.status = if req.status.is_empty() {
        "online".to_string()
    } else {
        req.status
    };
    if !req.capabilities.is_empty() {
        agent.capabilities = req.capabilities;
    }
    agent.current_task_id = req.current_task_id;
    agent.node_id = req.node_id;
    let event_agent_id = agent.id.clone();
    let event_node_id = agent.node_id.clone();
    let status = agent.status.clone();
    store.push_event(
        "agent.heartbeat",
        None,
        Some(event_agent_id),
        Some(event_node_id),
        "agent heartbeat",
        Uuid::new_v4().to_string(),
    );
    Json(json!({
      "agent_id": req.id,
      "status": status,
      "updated_at": Utc::now(),
    }))
    .into_response()
}

async fn list_terminal_sessions(State(state): State<AppState>) -> Json<Value> {
    let store = state.store.read().await;
    let mut sessions = Vec::new();
    for session in store.terminal_sessions.values() {
        sessions.push(json!({
            "id": session.id,
            "status": session.status,
            "actor": session.actor,
            "task_id": session.task_id,
            "node_id": session.node_id,
            "agent_id": session.agent_id,
            "commands": session.command_count,
        }));
    }
    Json(json!({ "sessions": sessions, "total": sessions.len() }))
}

async fn get_terminal_session(
    State(state): State<AppState>,
    AxumPath(session_id): AxumPath<Uuid>,
) -> impl IntoResponse {
    let store = state.store.read().await;
    match store.terminal_sessions.get(&session_id) {
        Some(session) => Json(json!({ "session": session, "runs": session.runs })).into_response(),
        None => not_found("Session not found"),
    }
}

async fn create_terminal_session(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<TerminalCreateRequest>,
) -> impl IntoResponse {
    if state.cfg.terminal_requires_approval && req.task_id.is_none() {
        return forbidden("Terminal requires bound task_id in approval policy");
    }
    let mut store = state.store.write().await;
    let session_id = Uuid::new_v4();
    let actor = req
        .actor
        .unwrap_or_else(|| state.cfg.terminal_default_user.clone());
    let trace_id = extract_trace_id(&headers);
    let task_id = req.task_id;
    let agent_id = req.agent_id;
    let node_id = req.node_id;
    let approval_id = req.approval_id;
    let session = TerminalSessionRecord {
        id: session_id,
        task_id,
        agent_id,
        node_id,
        actor,
        status: "open".to_string(),
        created_at: Utc::now(),
        last_activity_at: Utc::now(),
        command_count: 0,
        runs: Vec::new(),
        policy_approved: !state.cfg.terminal_requires_approval,
        approval_id,
    };
    if !session.policy_approved {
        if let Some(task_id) = session.task_id {
            if let Some(task) = store.tasks.get(&task_id) {
                if task.envelope.status == TaskStatus::Completed {
                    return forbidden("Cannot open terminal for completed task");
                }
            } else {
                return not_found("Task for terminal session not found");
            }
        }
    }
    let event_task_id = session.task_id;
    let event_agent_id = session.agent_id.clone();
    let event_node_id = session.node_id.clone();
    store.terminal_sessions.insert(session_id, session);
    store.push_event(
        "terminal.opened",
        event_task_id,
        event_agent_id,
        event_node_id,
        format!("trace={} actor={}", trace_id, "terminal-open"),
        trace_id,
    );
    Json(json!({
      "session_id": session_id,
      "status": "open",
    }))
    .into_response()
}

async fn execute_terminal_command(
    State(state): State<AppState>,
    AxumPath(session_id): AxumPath<Uuid>,
    Json(req): Json<TerminalCommand>,
) -> impl IntoResponse {
    let mut store = state.store.write().await;
    let now = Utc::now();
    let command = req.command.clone();
    let timeout_limit = Duration::from_secs(state.cfg.terminal_timeout_seconds.max(1));
    let max_output = state.cfg.terminal_max_output_bytes;

    let (task_id, session_agent_id, session_node_id, approval_id) = {
        let Some(session) = store.terminal_sessions.get_mut(&session_id) else {
            return not_found("Session not found");
        };
        if session.status != "open" {
            return conflict("Session is not open");
        }
        if !session.policy_approved && command.contains("rm") {
            return forbidden("Terminal policy denies destructive command");
        }
        if !should_allow_command(&state.cfg, &command) {
            return forbidden("Command is out of sandbox allowlist");
        }
        session.command_count += 1;
        session.last_activity_at = Utc::now();
        (
            session.task_id,
            session.agent_id.clone(),
            session.node_id.clone(),
            session.approval_id.clone(),
        )
    };

    let child_result = timeout(timeout_limit, async {
        let child = Command::new("sh")
            .arg("-lc")
            .arg(&command)
            .current_dir(state.cfg.data_dir.as_path())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()?;
        let output = child.wait_with_output().await?;
        Ok::<_, std::io::Error>((
            output.status.code().unwrap_or(-1),
            output.stdout,
            output.stderr,
        ))
    })
    .await;

    let (exit_code, stdout, stderr) = match child_result {
        Ok(Ok((code, out, err))) => {
            let stdout =
                normalize_slice_for_output(String::from_utf8_lossy(&out).to_string(), max_output);
            let stderr =
                normalize_slice_for_output(String::from_utf8_lossy(&err).to_string(), max_output);
            (code, stdout, stderr)
        }
        Ok(Err(err)) => (1, String::new(), err.to_string()),
        Err(_) => (1, String::new(), "command timeout".to_string()),
    };

    let finish = Utc::now();
    let run = TerminalRunResult {
        command,
        exit_code,
        stdout,
        stderr,
        started_at: now,
        finished_at: finish,
    };
    {
        let Some(session) = store.terminal_sessions.get_mut(&session_id) else {
            return not_found("Session no longer exists");
        };
        session.runs.push(run.clone());
    }

    if let Some(task_id) = task_id {
        if let Some(task) = store.tasks.get_mut(&task_id) {
            task.output = Some(json!({
              "last_terminal_session": session_id,
              "command": run.command,
              "exit_code": run.exit_code,
            }));
        }
    }

    let run_for_event = run.clone();
    store.push_event(
        "terminal.command",
        task_id,
        session_agent_id,
        session_node_id,
        format!("command_id={}", session_id),
        approval_id.unwrap_or_else(|| Uuid::new_v4().to_string()),
    );
    Json(json!({
      "session_id": session_id,
      "status": "ok",
      "result": run_for_event,
    }))
    .into_response()
}

async fn close_terminal_session(
    State(state): State<AppState>,
    AxumPath(session_id): AxumPath<Uuid>,
) -> impl IntoResponse {
    let mut store = state.store.write().await;
    let Some(session) = store.terminal_sessions.get_mut(&session_id) else {
        return not_found("Session not found");
    };
    session.status = "closed".to_string();
    let session_task_id = session.task_id;
    let session_agent_id = session.agent_id.clone();
    let session_node_id = session.node_id.clone();
    let session_approval_id = session.approval_id.clone();
    store.push_event(
        "terminal.closed",
        session_task_id,
        session_agent_id,
        session_node_id,
        "session closed".to_string(),
        session_approval_id.unwrap_or_else(|| Uuid::new_v4().to_string()),
    );
    Json(json!({ "session_id": session_id, "status": "closed" })).into_response()
}

async fn upsert_node(
    State(state): State<AppState>,
    Json(node): Json<NodeRecord>,
) -> impl IntoResponse {
    let mut store = state.store.write().await;
    let node_id = node.id.clone();
    store.nodes.insert(node_id.clone(), node);
    store.push_event(
        "node.upserted",
        None,
        None,
        Some(node_id.clone()),
        "node upserted",
        Uuid::new_v4().to_string(),
    );
    (
        StatusCode::CREATED,
        Json(json!({ "node_id": node_id, "status": "upserted" })),
    )
        .into_response()
}

async fn fleet_capabilities(State(state): State<AppState>) -> Json<Value> {
    let store = state.store.read().await;
    let mut caps: HashMap<String, usize> = HashMap::new();
    for agent in store.agents.values() {
        for cap in &agent.capabilities {
            *caps.entry(cap.clone()).or_insert(0) += 1;
        }
    }
    let mut node_caps: HashMap<String, usize> = HashMap::new();
    for node in store.nodes.values() {
        for cap in &node.capabilities {
            *node_caps.entry(cap.clone()).or_insert(0) += 1;
        }
    }
    Json(json!({
      "node_count": store.nodes.len(),
      "agent_count": store.agents.len(),
      "agent_capabilities": caps,
      "node_capabilities": node_caps,
      "default_endpoint": state.cfg.local_endpoint,
    }))
}

fn is_stale_heartbeat(heartbeat_at: DateTime<Utc>, stale_after_seconds: i64) -> bool {
    let now = Utc::now();
    now.signed_duration_since(heartbeat_at).num_seconds() > stale_after_seconds
}

async fn stale_mark_task(state: AppState) {
    loop {
        let stale_items: Vec<(Uuid, Option<String>, String)> = {
            let mut store = state.store.write().await;
            let stale_seconds = state.cfg.lease_stale_seconds.max(30);
            let mut stale_items = Vec::new();
            for task in store.tasks.values_mut() {
                if let Some(heartbeat_at) = task.heartbeat_at {
                    if task.envelope.status != TaskStatus::Running {
                        continue;
                    }
                    if !is_stale_heartbeat(heartbeat_at, stale_seconds) {
                        continue;
                    }
                    task.envelope.transition_to(TaskStatus::Failed);
                    task.events.push(TaskEvent {
                        sequence: task.events.len() as u64 + 1,
                        task_id: task.envelope.task_id,
                        name: "task.heartbeat_stale".to_string(),
                        status: TaskStatus::Failed,
                        detail: "heartbeat stale; auto failed".to_string(),
                        trace_id: task.envelope.trace_id.clone(),
                        occurred_at: Utc::now(),
                    });
                    stale_items.push((
                        task.envelope.task_id,
                        task.envelope.worker_id.clone(),
                        task.envelope.trace_id.clone(),
                    ));
                }
            }
            stale_items
        };

        if !stale_items.is_empty() {
            let mut store = state.store.write().await;
            for (task_id, agent_id, trace_id) in stale_items {
                if let Some(agent_id) = agent_id.as_deref() {
                    if let Some(agent) = store.agents.get_mut(agent_id) {
                        agent.current_task_id = None;
                        agent.status = "online".to_string();
                    }
                }
                let _ = state.event_tx.send(json!({
                    "event_type": "task.failed",
                    "task_id": task_id,
                    "reason": "heartbeat_timeout",
                    "timestamp": Utc::now(),
                }));
                store.push_event(
                    "task.failed",
                    Some(task_id),
                    agent_id,
                    None,
                    "heartbeat timeout",
                    trace_id,
                );
                store.queue_remove(&task_id);
            }
        }
        sleep(Duration::from_secs(
            (state.cfg.lease_stale_seconds / 2).max(15) as u64,
        ))
        .await;
    }
}

async fn doctor(cfg: &DaemonConfig) -> Result<(), String> {
    let data_dir = &cfg.data_dir;
    if !data_dir.exists() {
        return Err(format!("data_dir missing: {}", data_dir.display()));
    }
    let _ = tempfile::TempDir::new_in(data_dir).map_err(|err| err.to_string())?;
    Ok(())
}

async fn apply_init(cfg: &DaemonConfig) -> Result<(), String> {
    if !cfg.data_dir.exists() {
        tokio::fs::create_dir_all(&cfg.data_dir)
            .await
            .map_err(|err| err.to_string())?;
    }
    Ok(())
}

async fn apply_reset_dev(cfg: &DaemonConfig) -> Result<(), String> {
    if cfg.data_dir.exists() {
        tokio::fs::remove_dir_all(&cfg.data_dir)
            .await
            .map_err(|err| err.to_string())?;
    }
    apply_init(cfg).await?;
    Ok(())
}

fn parse_config(path: PathBuf) -> Result<DaemonConfig, String> {
    let raw = std::fs::read_to_string(path).map_err(|err| err.to_string())?;
    let parsed = toml::from_str::<DaemonConfig>(&raw).map_err(|err| err.to_string())?;
    Ok(parsed.merge_env())
}

fn load_config(cli: &Cli) -> DaemonConfig {
    let cfg = if let Some(path) = &cli.config {
        parse_config(path.clone()).unwrap_or_default()
    } else {
        DaemonConfig::default()
    };
    cfg.merge_env()
}

#[allow(dead_code)]
fn is_v1_task_path(path: &str) -> bool {
    path.starts_with("/v1/tasks")
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();
    let mut cfg = load_config(&cli);
    if cfg.data_dir.as_os_str().is_empty() {
        cfg.data_dir = PathBuf::from("/tmp/kolibri-ai");
    }
    tokio::fs::create_dir_all(&cfg.data_dir)
        .await
        .map_err(|err| format!("failed to create data dir: {err}"))?;

    tracing_subscriber::fmt::init();

    if cli.init {
        apply_init(&cfg).await?;
        println!("kolibri-locald init ok: {}", cfg.data_dir.display());
        return Ok(());
    }
    if cli.reset_dev {
        apply_reset_dev(&cfg).await?;
        println!("kolibri-locald reset-dev ok: {}", cfg.data_dir.display());
        return Ok(());
    }
    if cli.doctor {
        if let Err(err) = doctor(&cfg).await {
            eprintln!("doctor failed: {err}");
            return Err(err.into());
        }
        println!("doctor: ok");
        return Ok(());
    }

    let (event_tx, event_rx) = broadcast::channel(2048);
    let state = AppState {
        cfg: cfg.clone(),
        store: std::sync::Arc::new(RwLock::new(ControlPlaneState::new())),
        event_tx: event_tx.clone(),
    };
    let state_for_worker = state.clone();
    tokio::spawn(async move {
        stale_mark_task(state_for_worker).await;
    });
    tokio::spawn(task_event_publisher(
        event_tx.clone(),
        event_rx.resubscribe(),
    ));

    let routes = Router::new()
        .route("/health", get(health))
        .route("/v1/health", get(health))
        .route("/v1/status", get(metadata))
        .route("/v1/metadata", get(metadata))
        .route("/v1/fleet/nodes", get(list_nodes))
        .route("/v1/nodes", get(list_nodes))
        .route("/v1/agents", get(list_agents))
        .route("/v1/agents/enroll", post(enroll_agent))
        .route("/v1/agents/heartbeat", post(heartbeat_agent))
        .route("/v1/fleet/route", get(route_task))
        .route("/v1/fleet/registry", get(list_nodes))
        .route("/v1/fleet/capabilities", get(fleet_capabilities))
        .route("/v1/tasks", get(list_tasks))
        .route("/v1/tasks", post(submit_task))
        .route("/v1/tasks/:task_id", get(get_task))
        .route("/v1/tasks/:task_id/artifacts", get(get_task_artifacts))
        .route("/v1/tasks/:task_id/artifacts", post(post_task_artifacts))
        .route("/v1/tasks/:task_id/assign", post(assign_task))
        .route("/v1/tasks/:task_id/heartbeat", post(heartbeat_task))
        .route("/v1/tasks/:task_id/complete", post(complete_task))
        .route("/v1/tasks/:task_id/fail", post(fail_task))
        .route("/v1/tasks/:task_id/approve", post(approve_task))
        .route("/v1/tasks/:task_id/reject", post(reject_task))
        .route("/v1/tasks/:task_id/cancel", post(cancel_task))
        .route("/v1/tasks/lease", post(lease_task))
        .route("/v1/tasks/summary", get(task_summary))
        .route("/v1/tasks/queue/diagnostics", get(queue_diagnostics))
        .route("/v1/events", get(events_feed))
        .route("/v1/terminal/sessions", post(create_terminal_session))
        .route("/v1/terminal/sessions", get(list_terminal_sessions))
        .route(
            "/v1/terminal/sessions/{session_id}",
            get(get_terminal_session),
        )
        .route(
            "/v1/terminal/sessions/{session_id}/commands",
            post(execute_terminal_command),
        )
        .route(
            "/v1/terminal/sessions/{session_id}/close",
            post(close_terminal_session),
        )
        .route("/v1/nodes/upsert", post(upsert_node))
        .route("/tasks", get(list_tasks))
        .route("/tasks", post(submit_task))
        .route("/tasks/:task_id", get(get_task))
        .route("/tasks/:task_id/artifacts", post(post_task_artifacts))
        .route("/tasks/:task_id/artifacts", get(get_task_artifacts))
        .route("/tasks/:task_id/assign", post(assign_task))
        .route("/tasks/:task_id/heartbeat", post(heartbeat_task))
        .route("/tasks/:task_id/complete", post(complete_task))
        .route("/tasks/:task_id/fail", post(fail_task))
        .route("/tasks/:task_id/approve", post(approve_task))
        .route("/tasks/:task_id/reject", post(reject_task))
        .route("/tasks/:task_id/cancel", post(cancel_task))
        .route("/tasks/lease", post(lease_task))
        .route("/tasks/summary", get(task_summary))
        .route("/tasks/queue/diagnostics", get(queue_diagnostics))
        .route("/nodes", get(list_nodes))
        .route("/agents", get(list_agents))
        .with_state(state);

    let addr = SocketAddr::from((
        cfg.bind_host
            .parse::<std::net::IpAddr>()
            .unwrap_or_else(|_| "127.0.0.1".parse().expect("valid")),
        cfg.bind_port,
    ));

    info!(%addr, version="0.2.0", "kolibri-locald listening");
    let listener = TcpListener::bind(addr).await?;
    axum::serve(listener, routes).await?;
    Ok(())
}
