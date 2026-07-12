use axum::{
    Json, Router,
    extract::{Path, Query, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use chrono::Utc;
use kolibri_core::{
    CompleteRequest, FailRequest, HeartbeatRequest, LeaseRequest, RuntimeTaskState,
    ShadowTaskRuntime, TaskRuntimeError, TaskTraceFixture,
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::env;
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::net::SocketAddr;
use std::path::{Path as FilePath, PathBuf};
use std::process::ExitCode;
use std::sync::{Arc, Mutex};

#[tokio::main]
async fn main() -> ExitCode {
    match run().await {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("kolibri-task-shadow: {error}");
            ExitCode::FAILURE
        }
    }
}

async fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args().skip(1);
    let command = args.next().ok_or(UsageError)?;
    match command.as_str() {
        "replay" => replay_command(args.collect()),
        "serve" => serve_command(args.collect()).await,
        _ => Err(Box::new(UsageError)),
    }
}

fn replay_command(arguments: Vec<String>) -> Result<(), Box<dyn std::error::Error>> {
    let mut args = arguments.into_iter();
    let fixture_path = PathBuf::from(args.next().ok_or(UsageError)?);
    let mut assert_expected = false;
    let mut pretty = false;
    for argument in args {
        match argument.as_str() {
            "--assert-expected" => assert_expected = true,
            "--pretty" => pretty = true,
            _ => return Err(Box::new(UsageError)),
        }
    }

    let fixture_bytes = fs::read(&fixture_path)?;
    let fixture: TaskTraceFixture = serde_json::from_slice(&fixture_bytes)?;
    let summary = if assert_expected {
        fixture.assert_expected()?
    } else {
        fixture.replay()?
    };
    if pretty {
        println!("{}", serde_json::to_string_pretty(&summary)?);
    } else {
        println!("{}", serde_json::to_string(&summary)?);
    }
    Ok(())
}

async fn serve_command(arguments: Vec<String>) -> Result<(), Box<dyn std::error::Error>> {
    let config = ServeConfig::parse(arguments)?;
    if !config.bind.ip().is_loopback() {
        return Err("shadow listener must bind to a loopback address".into());
    }
    let state = AppState::load(config.state_path)?;
    let router = build_router(state);
    let listener = tokio::net::TcpListener::bind(config.bind).await?;
    let address = listener.local_addr()?;
    eprintln!("kolibri-task-shadow listening on {address}; mode=shadow_parity authoritative=false");
    axum::serve(listener, router).await?;
    Ok(())
}

#[derive(Debug)]
struct ServeConfig {
    bind: SocketAddr,
    state_path: PathBuf,
}

impl ServeConfig {
    fn parse(arguments: Vec<String>) -> Result<Self, Box<dyn std::error::Error>> {
        let mut bind = "127.0.0.1:9191".parse::<SocketAddr>()?;
        let mut state_path = None;
        let mut arguments = arguments.into_iter();
        while let Some(argument) = arguments.next() {
            match argument.as_str() {
                "--bind" => bind = arguments.next().ok_or(UsageError)?.parse()?,
                "--state" => state_path = Some(PathBuf::from(arguments.next().ok_or(UsageError)?)),
                _ => return Err(Box::new(UsageError)),
            }
        }
        Ok(Self {
            bind,
            state_path: state_path.ok_or(UsageError)?,
        })
    }
}

#[derive(Clone)]
struct AppState {
    runtime: Arc<Mutex<ShadowTaskRuntime>>,
    state_path: Option<Arc<PathBuf>>,
}

impl AppState {
    fn load(state_path: PathBuf) -> Result<Self, StateError> {
        let runtime = if state_path.exists() {
            let bytes = fs::read(&state_path)?;
            let runtime: ShadowTaskRuntime = serde_json::from_slice(&bytes)?;
            validate_shadow_identity(&runtime)?;
            runtime
        } else {
            ShadowTaskRuntime::default()
        };
        let state = Self {
            runtime: Arc::new(Mutex::new(runtime)),
            state_path: Some(Arc::new(state_path)),
        };
        state.persist()?;
        Ok(state)
    }

    #[cfg(test)]
    fn ephemeral() -> Self {
        Self {
            runtime: Arc::new(Mutex::new(ShadowTaskRuntime::default())),
            state_path: None,
        }
    }

    fn read<T>(&self, reader: impl FnOnce(&ShadowTaskRuntime) -> T) -> Result<T, ApiError> {
        let runtime = self
            .runtime
            .lock()
            .map_err(|_| ApiError::State(StateError::Poisoned))?;
        Ok(reader(&runtime))
    }

    fn mutate<T>(
        &self,
        mutation: impl FnOnce(&mut ShadowTaskRuntime) -> Result<T, TaskRuntimeError>,
    ) -> Result<T, ApiError> {
        let mut runtime = self
            .runtime
            .lock()
            .map_err(|_| ApiError::State(StateError::Poisoned))?;
        let previous = runtime.clone();
        let result = mutation(&mut runtime);
        if let Err(error) = self.persist_runtime(&runtime) {
            *runtime = previous;
            return Err(ApiError::State(error));
        }
        result.map_err(ApiError::Runtime)
    }

    fn persist(&self) -> Result<(), StateError> {
        let runtime = self.runtime.lock().map_err(|_| StateError::Poisoned)?;
        self.persist_runtime(&runtime)
    }

    fn persist_runtime(&self, runtime: &ShadowTaskRuntime) -> Result<(), StateError> {
        let Some(path) = self.state_path.as_deref() else {
            return Ok(());
        };
        persist_runtime(path, runtime)
    }
}

fn build_router(state: AppState) -> Router {
    Router::new()
        .route("/health", get(health))
        .route("/v1/tasks", get(list_tasks).post(create_task))
        .route("/v1/tasks/lease", post(lease_task))
        .route("/v1/tasks/reap-expired", post(reap_expired))
        .route("/v1/tasks/:task_id", get(get_task))
        .route("/v1/tasks/:task_id/heartbeat", post(heartbeat_task))
        .route("/v1/tasks/:task_id/complete", post(complete_task))
        .route("/v1/tasks/:task_id/fail", post(fail_task))
        .route("/v1/tasks/:task_id/events", get(task_events))
        .route("/v1/runtime/summary", get(runtime_summary))
        .fallback(not_found)
        .with_state(state)
}

async fn health() -> Json<Value> {
    Json(json!({
        "status": "ok",
        "service": "kolibri-task-shadow",
        "mode": "shadow_parity",
        "authoritative": false,
        "authority": "python-control-plane",
    }))
}

#[derive(Debug, Default, Deserialize)]
struct TaskListQuery {
    state: Option<RuntimeTaskState>,
    limit: Option<usize>,
    offset: Option<usize>,
}

async fn list_tasks(
    State(state): State<AppState>,
    Query(query): Query<TaskListQuery>,
) -> Result<Json<Value>, ApiError> {
    let limit = query.limit.unwrap_or(100).clamp(1, 250);
    let offset = query.offset.unwrap_or(0);
    state.read(|runtime| {
        let all = runtime.list_tasks(query.state);
        let total_indexed = all.len();
        let tasks: Vec<_> = all.into_iter().skip(offset).take(limit).collect();
        let queue = runtime.queue();
        Json(json!({
            "tasks": tasks,
            "queue": queue.iter().take(250).collect::<Vec<_>>(),
            "pagination": {
                "limit": limit,
                "offset": offset,
                "returned": tasks.len(),
                "total_indexed": total_indexed,
            },
            "queue_total": queue.len(),
            "shadow": {
                "mode": "shadow_parity",
                "authoritative": false,
                "authority": "python-control-plane",
            },
        }))
    })
}

async fn create_task(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(mut envelope): Json<Value>,
) -> Result<(StatusCode, Json<Value>), ApiError> {
    apply_envelope_idempotency(&mut envelope, &headers)?;
    let outcome = state.mutate(|runtime| runtime.create_task(envelope, Utc::now()))?;
    Ok((
        StatusCode::CREATED,
        Json(serde_json::to_value(outcome.task)?),
    ))
}

async fn get_task(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
) -> Result<Json<Value>, ApiError> {
    state.read(|runtime| runtime.task(&task_id))?.map_or_else(
        |error| Err(ApiError::Runtime(error)),
        |task| {
            Ok(Json(
                serde_json::to_value(task).map_err(ApiError::Serialization)?,
            ))
        },
    )
}

async fn lease_task(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(mut request): Json<LeaseRequest>,
) -> Result<Response, ApiError> {
    apply_request_idempotency(&mut request.idempotency_key, &headers)?;
    let task = state.mutate(|runtime| runtime.lease(&request, Utc::now()))?;
    match task {
        Some(task) => Ok((StatusCode::OK, Json(serde_json::to_value(task)?)).into_response()),
        None => Ok(StatusCode::NO_CONTENT.into_response()),
    }
}

async fn heartbeat_task(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
    headers: HeaderMap,
    Json(mut request): Json<HeartbeatRequest>,
) -> Result<Json<Value>, ApiError> {
    apply_request_idempotency(&mut request.idempotency_key, &headers)?;
    let task = state.mutate(|runtime| runtime.heartbeat(&task_id, &request, Utc::now()))?;
    Ok(Json(serde_json::to_value(task)?))
}

async fn complete_task(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
    headers: HeaderMap,
    Json(mut request): Json<CompleteRequest>,
) -> Result<Json<Value>, ApiError> {
    apply_request_idempotency(&mut request.idempotency_key, &headers)?;
    let outcome = state.mutate(|runtime| runtime.complete(&task_id, &request, Utc::now()))?;
    Ok(Json(serde_json::to_value(outcome)?))
}

async fn fail_task(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
    headers: HeaderMap,
    Json(mut request): Json<FailRequest>,
) -> Result<Json<Value>, ApiError> {
    apply_request_idempotency(&mut request.idempotency_key, &headers)?;
    let task = state.mutate(|runtime| runtime.fail(&task_id, &request, Utc::now()))?;
    Ok(Json(serde_json::to_value(task)?))
}

async fn reap_expired(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    let outcome = state.mutate(|runtime| runtime.reap_expired(Utc::now()))?;
    Ok(Json(serde_json::to_value(outcome)?))
}

async fn task_events(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
) -> Result<Json<Value>, ApiError> {
    let events = state
        .read(|runtime| runtime.events(&task_id))?
        .map_err(ApiError::Runtime)?;
    Ok(Json(json!({"task_id": task_id, "events": events})))
}

async fn runtime_summary(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    state.read(|runtime| {
        Json(serde_json::to_value(runtime.summary(Utc::now())).expect("summary serializes"))
    })
}

async fn not_found() -> impl IntoResponse {
    (
        StatusCode::NOT_FOUND,
        Json(json!({"error": "not_found", "service": "kolibri-task-shadow"})),
    )
}

fn apply_envelope_idempotency(envelope: &mut Value, headers: &HeaderMap) -> Result<(), ApiError> {
    let header = idempotency_header(headers)?;
    let object = envelope
        .as_object_mut()
        .ok_or_else(|| ApiError::invalid("task_envelope_must_be_object"))?;
    if let Some(header) = header {
        match object.get("idempotency_key").and_then(Value::as_str) {
            Some(body) if body != header => {
                return Err(ApiError::invalid("idempotency_key_conflict"));
            }
            Some(_) => {}
            None => {
                object.insert(
                    "idempotency_key".to_string(),
                    Value::String(header.to_string()),
                );
            }
        }
    }
    Ok(())
}

fn apply_request_idempotency(
    body: &mut Option<String>,
    headers: &HeaderMap,
) -> Result<(), ApiError> {
    let Some(header) = idempotency_header(headers)? else {
        return Ok(());
    };
    if body.as_deref().is_some_and(|value| value != header) {
        return Err(ApiError::invalid("idempotency_key_conflict"));
    }
    *body = Some(header.to_string());
    Ok(())
}

fn idempotency_header(headers: &HeaderMap) -> Result<Option<&str>, ApiError> {
    headers
        .get("idempotency-key")
        .map(|value| {
            value
                .to_str()
                .map_err(|_| ApiError::invalid("idempotency_key_invalid"))
        })
        .transpose()
}

#[derive(Debug)]
enum ApiError {
    Runtime(TaskRuntimeError),
    State(StateError),
    Serialization(serde_json::Error),
}

impl ApiError {
    fn invalid(reason: &str) -> Self {
        Self::Runtime(TaskRuntimeError::InvalidRequest(reason.to_string()))
    }
}

impl From<serde_json::Error> for ApiError {
    fn from(error: serde_json::Error) -> Self {
        Self::Serialization(error)
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let (status, payload) = match self {
            Self::Runtime(TaskRuntimeError::TaskNotFound(task_id)) => (
                StatusCode::NOT_FOUND,
                json!({"error": "task_not_found", "task_id": task_id}),
            ),
            Self::Runtime(TaskRuntimeError::InvalidRequest(reason)) => {
                (StatusCode::UNPROCESSABLE_ENTITY, json!({"error": reason}))
            }
            Self::Runtime(TaskRuntimeError::IdempotencyConflict {
                key,
                existing_task_id,
            }) => (
                StatusCode::CONFLICT,
                json!({
                    "error": "idempotency_conflict",
                    "idempotency_key": key,
                    "existing_task_id": existing_task_id,
                }),
            ),
            Self::Runtime(TaskRuntimeError::LeaseFenceRejected {
                reason,
                task_id,
                state,
                attempt_id,
                fencing_token,
            }) => (
                StatusCode::CONFLICT,
                json!({
                    "error": "lease_fence_rejected",
                    "reason": reason,
                    "task_id": task_id,
                    "state": state,
                    "attempt_id": attempt_id,
                    "fencing_token": fencing_token,
                }),
            ),
            Self::Runtime(TaskRuntimeError::CompletionVerificationFailed {
                task_id,
                state,
                verifier,
            }) => (
                StatusCode::CONFLICT,
                json!({
                    "error": "completion_verification_failed",
                    "task_id": task_id,
                    "state": state,
                    "verifier": verifier,
                }),
            ),
            Self::Runtime(TaskRuntimeError::AttemptBudgetExhausted(task_id)) => (
                StatusCode::CONFLICT,
                json!({"error": "attempt_budget_exhausted", "task_id": task_id}),
            ),
            Self::Runtime(error) => (
                StatusCode::INTERNAL_SERVER_ERROR,
                json!({"error": error.reason_code()}),
            ),
            Self::State(error) => {
                drop(error);
                (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    json!({"error": "shadow_runtime_state_error"}),
                )
            }
            Self::Serialization(error) => {
                drop(error);
                (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    json!({"error": "shadow_runtime_serialization_error"}),
                )
            }
        };
        (status, Json(payload)).into_response()
    }
}

fn validate_shadow_identity(runtime: &ShadowTaskRuntime) -> Result<(), StateError> {
    if runtime.mode != "shadow_parity"
        || runtime.authoritative
        || runtime.authority != "python-control-plane"
    {
        return Err(StateError::InvalidIdentity);
    }
    Ok(())
}

fn persist_runtime(path: &FilePath, runtime: &ShadowTaskRuntime) -> Result<(), StateError> {
    validate_shadow_identity(runtime)?;
    let parent = path.parent().unwrap_or_else(|| FilePath::new("."));
    fs::create_dir_all(parent)?;
    if fs::symlink_metadata(path).is_ok_and(|metadata| metadata.file_type().is_symlink()) {
        return Err(StateError::UnsafePath(path.to_path_buf()));
    }
    let temp = parent.join(format!(
        ".{}.{}.{}.tmp",
        path.file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("state"),
        std::process::id(),
        uuid::Uuid::new_v4()
    ));
    let result = (|| {
        let mut options = OpenOptions::new();
        options.create_new(true).write(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut file = options.open(&temp)?;
        file.write_all(&serde_json::to_vec(runtime)?)?;
        file.flush()?;
        file.sync_all()?;
        fs::rename(&temp, path)?;
        File::open(parent)?.sync_all()?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result
}

#[derive(Debug, thiserror::Error)]
enum StateError {
    #[error("shadow state I/O failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("shadow state serialization failed: {0}")]
    Serialization(#[from] serde_json::Error),
    #[error("shadow state lock is poisoned")]
    Poisoned,
    #[error("shadow state identity is invalid")]
    InvalidIdentity,
    #[error("shadow state path is unsafe: {0}")]
    UnsafePath(PathBuf),
}

#[derive(Debug)]
struct UsageError;

impl std::fmt::Display for UsageError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(
            "usage: kolibri-task-shadow replay <fixture.json> [--assert-expected] [--pretty]\n       kolibri-task-shadow serve --state <state.json> [--bind 127.0.0.1:9191]",
        )
    }
}

impl std::error::Error for UsageError {}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::{Body, to_bytes};
    use axum::http::Request;
    use tower::ServiceExt;

    async fn request(router: Router, request: Request<Body>) -> (StatusCode, Value) {
        let response = router.oneshot(request).await.unwrap();
        let status = response.status();
        let bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let body = if bytes.is_empty() {
            Value::Null
        } else {
            serde_json::from_slice(&bytes).unwrap()
        };
        (status, body)
    }

    fn json_request(method: &str, uri: &str, key: &str, body: &Value) -> Request<Body> {
        Request::builder()
            .method(method)
            .uri(uri)
            .header("content-type", "application/json")
            .header("idempotency-key", key)
            .body(Body::from(serde_json::to_vec(&body).unwrap()))
            .unwrap()
    }

    #[tokio::test]
    #[allow(clippy::too_many_lines)]
    async fn http_slice_preserves_python_shapes_and_fencing() {
        let router = build_router(AppState::ephemeral());
        let envelope = json!({
            "task_id": "http-shadow",
            "kind": "read_only_probe",
            "required_capability": "read_only_probe",
            "max_attempts": 2,
        });
        let (status, created) = request(
            router.clone(),
            json_request("POST", "/v1/tasks", "http-create", &envelope),
        )
        .await;
        assert_eq!(status, StatusCode::CREATED);
        assert_eq!(created["state"], "queued");
        assert_eq!(created["shadow"]["authoritative"], false);

        let (status, replayed) = request(
            router.clone(),
            json_request("POST", "/v1/tasks", "http-create", &envelope),
        )
        .await;
        assert_eq!(status, StatusCode::CREATED);
        assert_eq!(replayed["task_id"], "http-shadow");

        let (status, leased) = request(
            router.clone(),
            json_request(
                "POST",
                "/v1/tasks/lease",
                "http-lease",
                &json!({
                    "node_id": "worker-a",
                    "agent_id": "agent-a",
                    "capabilities": ["read_only_probe"],
                }),
            ),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(leased["attempt_id"], "http-shadow-attempt-1");
        assert_eq!(leased["fencing_token"], 1);

        let (status, stale) = request(
            router.clone(),
            json_request(
                "POST",
                "/v1/tasks/http-shadow/heartbeat",
                "http-heartbeat-stale",
                &json!({
                    "attempt_id": "http-shadow-attempt-1",
                    "fencing_token": 2,
                    "node_id": "worker-a",
                    "agent_id": "agent-a",
                }),
            ),
        )
        .await;
        assert_eq!(status, StatusCode::CONFLICT);
        assert_eq!(stale["error"], "lease_fence_rejected");
        assert_eq!(stale["reason"], "fencing_token_mismatch");

        let result = json!({
            "status": "completed",
            "task_id": "http-shadow",
            "attempt_id": "http-shadow-attempt-1",
            "node_id": "worker-a",
            "agent_id": "agent-a",
            "fencing_token": 1,
            "output": "verified",
        });
        let completion = json!({
            "attempt_id": "http-shadow-attempt-1",
            "fencing_token": 1,
            "node_id": "worker-a",
            "agent_id": "agent-a",
            "result_reference": "cas://sha256/http-shadow",
            "result": result,
        });
        let (status, completed) = request(
            router.clone(),
            json_request(
                "POST",
                "/v1/tasks/http-shadow/complete",
                "http-complete",
                &completion,
            ),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(completed["task"]["state"], "completed");
        assert_eq!(
            completed["task"]["completion_verifier"]["verdict"],
            "passed"
        );
        let (status, replayed) = request(
            router.clone(),
            json_request(
                "POST",
                "/v1/tasks/http-shadow/complete",
                "http-complete",
                &completion,
            ),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(replayed, completed);

        let (status, events) = request(
            router.clone(),
            Request::builder()
                .uri("/v1/tasks/http-shadow/events")
                .body(Body::empty())
                .unwrap(),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(events["events"].as_array().unwrap().len(), 3);

        let (status, summary) = request(
            router,
            Request::builder()
                .uri("/v1/runtime/summary")
                .body(Body::empty())
                .unwrap(),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(summary["task_total"], 1);
        assert_eq!(summary["task_states"]["completed"], 1);
        assert_eq!(summary["active_lease_total"], 0);
        assert_eq!(summary["authoritative"], false);
    }
}
