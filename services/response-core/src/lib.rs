//! Internal PostgreSQL-backed response authority for the Kolibri edge.
//!
//! This crate intentionally exposes only loopback RPC construction. Provider
//! execution and public HTTP policy remain outside this service.

use axum::{
    Json, Router,
    extract::State,
    extract::rejection::JsonRejection,
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
};
use chrono::{DateTime, Duration, Utc};
use kolibri_core::canonical_json_sha256;
use kolibri_store_postgres::{
    CancelResponseCommand, CreateResponseCommand, IssuePublicSessionCommand,
    PostgresResponseRepository, PublicPrincipal, PublicSession, PublicSessionRepository,
    ResponseRepository, StoreError, StoredEvent, StoredResponse,
};
use serde::Deserialize;
use serde_json::{Value, json};
use sqlx::PgPool;
use std::{net::SocketAddr, time::Duration as StdDuration};
use tokio::time::{Instant, sleep};
use uuid::Uuid;

const INTERNAL_ACTOR: &str = "response-core";
const POLICY_VERSION: &str = "kolibri.response-core.v1";

#[derive(Debug, Clone)]
pub struct CoreSettings {
    pub public_session_ttl: Duration,
    pub authority_epoch: i64,
    pub event_poll_interval: StdDuration,
}

impl Default for CoreSettings {
    fn default() -> Self {
        Self {
            public_session_ttl: Duration::hours(24),
            authority_epoch: 1,
            event_poll_interval: StdDuration::from_millis(100),
        }
    }
}

impl CoreSettings {
    /// Validates bounded service settings.
    ///
    /// # Errors
    ///
    /// Returns [`ConfigurationError`] when the session lifetime, authority
    /// epoch or request-local event polling interval is unsafe.
    pub fn validate(&self) -> Result<(), ConfigurationError> {
        if self.public_session_ttl <= Duration::zero()
            || self.public_session_ttl > Duration::days(30)
        {
            return Err(ConfigurationError::InvalidSessionTtl);
        }
        if self.authority_epoch < 1 {
            return Err(ConfigurationError::InvalidAuthorityEpoch);
        }
        if self.event_poll_interval < StdDuration::from_millis(25)
            || self.event_poll_interval > StdDuration::from_secs(1)
        {
            return Err(ConfigurationError::InvalidEventPollInterval);
        }
        Ok(())
    }
}

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum ConfigurationError {
    #[error("public session TTL must be between 1 second and 30 days")]
    InvalidSessionTtl,
    #[error("authority epoch must be positive")]
    InvalidAuthorityEpoch,
    #[error("event poll interval must be between 25 ms and 1 second")]
    InvalidEventPollInterval,
    #[error("response-core bind address is invalid")]
    InvalidBindAddress,
    #[error("response core must bind to a loopback address")]
    ExternalBindForbidden,
}

/// Parses the internal listener address and rejects every external bind.
///
/// # Errors
///
/// Returns [`ConfigurationError::InvalidBindAddress`] for malformed input or
/// [`ConfigurationError::ExternalBindForbidden`] for a non-loopback address.
pub fn parse_loopback_bind(value: Option<&str>) -> Result<SocketAddr, ConfigurationError> {
    let address = value
        .unwrap_or("127.0.0.1:9202")
        .parse::<SocketAddr>()
        .map_err(|_| ConfigurationError::InvalidBindAddress)?;
    if !address.ip().is_loopback() {
        return Err(ConfigurationError::ExternalBindForbidden);
    }
    Ok(address)
}

#[derive(Clone)]
struct AppState {
    repository: PostgresResponseRepository,
    settings: CoreSettings,
}

/// Builds the internal RPC router around an explicit `PostgreSQL` pool.
///
/// # Errors
///
/// Returns [`ConfigurationError`] for unsafe settings. This function does not
/// run migrations or bind a network listener.
pub fn build_router(pool: PgPool, settings: CoreSettings) -> Result<Router, ConfigurationError> {
    settings.validate()?;
    let state = AppState {
        repository: PostgresResponseRepository::new(pool),
        settings,
    };
    Ok(Router::new()
        .route("/health", get(health))
        .route("/internal/v1/public-sessions", post(issue_public_session))
        .route(
            "/internal/v1/public-sessions/resolve",
            post(resolve_public_session),
        )
        .route("/internal/v1/responses", post(create_response))
        .route("/internal/v1/responses/get", post(get_response))
        .route("/internal/v1/responses/events", post(list_response_events))
        .route("/internal/v1/responses/cancel", post(cancel_response))
        .fallback(not_found)
        .with_state(state))
}

async fn health(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    sqlx::query_scalar::<_, i32>("SELECT 1")
        .fetch_one(state.repository.pool())
        .await
        .map_err(StoreError::Database)?;
    Ok(Json(json!({
        "status": "ok",
        "service": "kolibri-response-core",
        "authority": "control-plane/home",
        "persistence": "postgresql",
        "model": "kolibri",
    })))
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct IssuePublicSessionRequest {
    origin: String,
}

async fn issue_public_session(
    State(state): State<AppState>,
    payload: Result<Json<IssuePublicSessionRequest>, JsonRejection>,
) -> Result<Json<Value>, ApiError> {
    let request = parse_json(payload)?;
    let now = Utc::now();
    let issue = state
        .repository
        .issue_public_session(&IssuePublicSessionCommand {
            origin: request.origin,
            expires_at: now + state.settings.public_session_ttl,
            occurred_at: now,
        })
        .await?;
    Ok(Json(json!({
        "session": public_session_json(&issue.session),
        "credential": issue.credential,
    })))
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ResolvePublicSessionRequest {
    credential: String,
}

async fn resolve_public_session(
    State(state): State<AppState>,
    payload: Result<Json<ResolvePublicSessionRequest>, JsonRejection>,
) -> Result<Json<Value>, ApiError> {
    let request = parse_json(payload)?;
    let session = state
        .repository
        .resolve_public_session(&request.credential, Utc::now())
        .await?
        .ok_or_else(ApiError::public_session_required)?;
    Ok(Json(public_session_json(&session)))
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct RpcPrincipal {
    session_id: String,
    origin: String,
}

impl From<RpcPrincipal> for PublicPrincipal {
    fn from(value: RpcPrincipal) -> Self {
        Self {
            session_id: value.session_id,
            origin: value.origin,
        }
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CreateResponseRequest {
    principal: RpcPrincipal,
    request: Value,
    idempotency_key: String,
    request_sha256: String,
}

async fn create_response(
    State(state): State<AppState>,
    payload: Result<Json<CreateResponseRequest>, JsonRejection>,
) -> Result<(StatusCode, Json<Value>), ApiError> {
    let request = parse_json(payload)?;
    validate_idempotency_key(&request.idempotency_key)?;
    verify_edge_request_hash(
        "POST",
        "/v1/responses",
        &request.request,
        &request.request_sha256,
    )?;
    let (principal, session) = authorize_principal(&state, request.principal).await?;
    let principal_id = principal.principal_id()?;
    let project_id = response_project_id(&request.request, &session)?;
    let user_message = response_input_text(&request.request)?;
    let task_type = response_task_type(&request.request)?;
    let outcome = state
        .repository
        .create_response(&CreateResponseCommand {
            principal_id,
            session_id: Some(principal.session_id),
            project_id,
            trace_id: prefixed_id("trace"),
            idempotency_key: request.idempotency_key,
            task_type,
            request: request.request,
            user_message,
            actor: INTERNAL_ACTOR.to_string(),
            policy_version: POLICY_VERSION.to_string(),
            authority_epoch: state.settings.authority_epoch,
            occurred_at: Utc::now(),
            idempotency_request_sha256: Some(format!("sha256:{}", request.request_sha256)),
        })
        .await?;
    let status = if outcome.created {
        StatusCode::CREATED
    } else {
        StatusCode::OK
    };
    Ok((status, Json(stored_response_json(&outcome.response))))
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ResponseLookupRequest {
    principal: RpcPrincipal,
    response_id: String,
}

async fn get_response(
    State(state): State<AppState>,
    payload: Result<Json<ResponseLookupRequest>, JsonRejection>,
) -> Result<Json<Value>, ApiError> {
    let request = parse_json(payload)?;
    let (principal, _) = authorize_principal(&state, request.principal).await?;
    let response = state
        .repository
        .get_response(&principal.principal_id()?, &request.response_id)
        .await?
        .ok_or_else(ApiError::response_not_found)?;
    Ok(Json(stored_response_json(&response)))
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ResponseEventsRequest {
    principal: RpcPrincipal,
    response_id: String,
    #[serde(default)]
    after: i64,
    #[serde(default = "default_event_limit")]
    limit: i64,
    #[serde(default)]
    wait_seconds: f64,
}

const fn default_event_limit() -> i64 {
    100
}

async fn list_response_events(
    State(state): State<AppState>,
    payload: Result<Json<ResponseEventsRequest>, JsonRejection>,
) -> Result<Json<Value>, ApiError> {
    let request = parse_json(payload)?;
    if request.after < 0
        || !(1..=500).contains(&request.limit)
        || !request.wait_seconds.is_finite()
        || !(0.0..=30.0).contains(&request.wait_seconds)
    {
        return Err(ApiError::invalid_request("response_event_cursor_invalid"));
    }
    let (principal, _) = authorize_principal(&state, request.principal).await?;
    let principal_id = principal.principal_id()?;
    let deadline = Instant::now() + StdDuration::from_secs_f64(request.wait_seconds);
    loop {
        let events = state
            .repository
            .list_response_events(
                &principal_id,
                &request.response_id,
                request.after,
                request.limit,
            )
            .await?
            .ok_or_else(ApiError::response_not_found)?;
        if !events.is_empty() || request.wait_seconds == 0.0 || Instant::now() >= deadline {
            return Ok(Json(events_json(&request.response_id, &events)));
        }
        let remaining = deadline.saturating_duration_since(Instant::now());
        sleep(state.settings.event_poll_interval.min(remaining)).await;
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CancelResponseRequest {
    principal: RpcPrincipal,
    response_id: String,
    idempotency_key: String,
    request_sha256: String,
}

async fn cancel_response(
    State(state): State<AppState>,
    payload: Result<Json<CancelResponseRequest>, JsonRejection>,
) -> Result<Json<Value>, ApiError> {
    let request = parse_json(payload)?;
    validate_idempotency_key(&request.idempotency_key)?;
    let path = format!("/v1/responses/{}/cancel", request.response_id);
    verify_edge_request_hash("POST", &path, &json!({}), &request.request_sha256)?;
    let (principal, _) = authorize_principal(&state, request.principal).await?;
    let response = state
        .repository
        .cancel_response(&CancelResponseCommand {
            principal_id: principal.principal_id()?,
            response_id: request.response_id,
            idempotency_key: request.idempotency_key,
            request_sha256: format!("sha256:{}", request.request_sha256),
            actor: INTERNAL_ACTOR.to_string(),
            policy_version: POLICY_VERSION.to_string(),
            authority_epoch: state.settings.authority_epoch,
            occurred_at: Utc::now(),
        })
        .await?
        .ok_or_else(ApiError::response_not_found)?;
    Ok(Json(stored_response_json(&response.response)))
}

async fn authorize_principal(
    state: &AppState,
    principal: RpcPrincipal,
) -> Result<(PublicPrincipal, PublicSession), ApiError> {
    let principal = PublicPrincipal::from(principal);
    let session = state
        .repository
        .resolve_public_principal(&principal, Utc::now())
        .await?
        .ok_or_else(ApiError::public_session_required)?;
    Ok((principal, session))
}

fn response_project_id(request: &Value, session: &PublicSession) -> Result<String, ApiError> {
    let requested = request.get("project_id").and_then(Value::as_str);
    if requested.is_some_and(|value| value != session.current_project_id) {
        return Err(ApiError::new(
            StatusCode::FORBIDDEN,
            "project_scope_violation",
            "The public session cannot access this project.",
            false,
        ));
    }
    Ok(session.current_project_id.clone())
}

fn response_input_text(request: &Value) -> Result<String, ApiError> {
    let input = request
        .get("input")
        .ok_or_else(|| ApiError::invalid_request("response_input_required"))?;
    let mut pieces = Vec::new();
    collect_input_text(input, &mut pieces);
    let text = pieces.join("\n");
    if text.trim().is_empty() || text.chars().count() > 200_000 {
        return Err(ApiError::invalid_request("response_input_invalid"));
    }
    Ok(text)
}

fn collect_input_text(value: &Value, pieces: &mut Vec<String>) {
    match value {
        Value::String(text) if !text.trim().is_empty() => pieces.push(text.clone()),
        Value::Array(values) => {
            for value in values {
                collect_input_text(value, pieces);
            }
        }
        Value::Object(object) => {
            if object
                .get("role")
                .and_then(Value::as_str)
                .is_some_and(|role| role != "user")
            {
                return;
            }
            if let Some(text) = object.get("text").and_then(Value::as_str) {
                if !text.trim().is_empty() {
                    pieces.push(text.to_string());
                }
            } else if let Some(content) = object.get("content") {
                collect_input_text(content, pieces);
            }
        }
        _ => {}
    }
}

fn response_task_type(request: &Value) -> Result<String, ApiError> {
    let value = request
        .get("task_type")
        .and_then(Value::as_str)
        .unwrap_or("chat");
    let mut characters = value.chars();
    if value.len() > 100
        || !characters
            .next()
            .is_some_and(|character| character.is_ascii_lowercase())
        || !characters.all(|character| {
            character.is_ascii_lowercase()
                || character.is_ascii_digit()
                || matches!(character, '_' | '.' | '-')
        })
    {
        return Err(ApiError::invalid_request("response_task_type_invalid"));
    }
    Ok(value.to_string())
}

fn verify_edge_request_hash(
    method: &str,
    path: &str,
    body: &Value,
    supplied: &str,
) -> Result<(), ApiError> {
    if supplied.len() != 64
        || !supplied
            .bytes()
            .all(|character| character.is_ascii_digit() || (b'a'..=b'f').contains(&character))
    {
        return Err(ApiError::invalid_request("request_sha256_invalid"));
    }
    let expected = canonical_json_sha256(&json!({
        "method": method.to_ascii_uppercase(),
        "path": path,
        "body": body,
    }))
    .map_err(|_| ApiError::invalid_request("request_body_not_canonicalizable"))?;
    if expected.strip_prefix("sha256:") != Some(supplied) {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "request_sha256_mismatch",
            "The request hash does not match the canonical request.",
            false,
        ));
    }
    Ok(())
}

fn validate_idempotency_key(value: &str) -> Result<(), ApiError> {
    if !(8..=200).contains(&value.len())
        || !value.bytes().enumerate().all(|(index, character)| {
            character.is_ascii_alphanumeric()
                || (index > 0 && matches!(character, b'.' | b'_' | b':' | b'/' | b'-'))
        })
    {
        return Err(ApiError::invalid_request("invalid_idempotency_key"));
    }
    Ok(())
}

fn parse_json<T>(payload: Result<Json<T>, JsonRejection>) -> Result<T, ApiError> {
    payload
        .map(|Json(value)| value)
        .map_err(|_| ApiError::invalid_request("invalid_json_body"))
}

fn public_session_json(session: &PublicSession) -> Value {
    json!({
        "id": session.id,
        "origin": session.origin,
        "expires_at": timestamp_unix(session.expires_at),
        "current_project_id": session.current_project_id,
    })
}

fn stored_response_json(response: &StoredResponse) -> Value {
    json!({
        "id": response.id,
        "object": "response",
        "created_at": timestamp_unix(response.created_at),
        "status": response.status,
        "model": "kolibri",
        "project_id": response.project_id,
        "output": response.output,
        "output_text": response.output_text,
        "task": {"type": response.task_type},
        "error": response.error,
    })
}

fn events_json(response_id: &str, events: &[StoredEvent]) -> Value {
    json!({
        "object": "list",
        "response_id": response_id,
        "data": events.iter().map(|event| json!({
            "sequence": event.sequence,
            "event_type": event.event_type,
            "payload": event.data,
        })).collect::<Vec<_>>(),
    })
}

fn timestamp_unix(value: DateTime<Utc>) -> i64 {
    value.timestamp()
}

fn prefixed_id(prefix: &str) -> String {
    format!("{prefix}_{}", Uuid::new_v4().simple())
}

async fn not_found() -> ApiError {
    ApiError::new(
        StatusCode::NOT_FOUND,
        "internal_route_not_found",
        "Internal Core route not found.",
        false,
    )
}

#[derive(Debug)]
struct ApiError {
    status: StatusCode,
    code: &'static str,
    message: &'static str,
    retryable: bool,
}

impl ApiError {
    const fn new(
        status: StatusCode,
        code: &'static str,
        message: &'static str,
        retryable: bool,
    ) -> Self {
        Self {
            status,
            code,
            message,
            retryable,
        }
    }

    const fn invalid_request(code: &'static str) -> Self {
        Self::new(
            StatusCode::BAD_REQUEST,
            code,
            "The internal Core request is invalid.",
            false,
        )
    }

    const fn public_session_required() -> Self {
        Self::new(
            StatusCode::UNAUTHORIZED,
            "public_session_required_or_expired",
            "Create a new public session.",
            false,
        )
    }

    const fn response_not_found() -> Self {
        Self::new(
            StatusCode::NOT_FOUND,
            "response_not_found",
            "Response not found for this public session.",
            false,
        )
    }
}

impl From<StoreError> for ApiError {
    fn from(error: StoreError) -> Self {
        match error {
            StoreError::InvalidCommand(_) => Self::invalid_request("core_contract_invalid"),
            StoreError::IdempotencyConflict { .. } => Self::new(
                StatusCode::CONFLICT,
                "idempotency_conflict",
                "The idempotency key is bound to another request.",
                false,
            ),
            StoreError::CorruptState(_) => Self::new(
                StatusCode::INTERNAL_SERVER_ERROR,
                "core_state_corrupt",
                "The durable Core state is inconsistent.",
                false,
            ),
            StoreError::Database(_) | StoreError::Migration(_) => Self::new(
                StatusCode::SERVICE_UNAVAILABLE,
                "core_store_unavailable",
                "The durable Core store is unavailable.",
                true,
            ),
        }
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (
            self.status,
            Json(json!({
                "error": {
                    "type": "core_error",
                    "code": self.code,
                    "message": self.message,
                    "retryable": self.retryable,
                }
            })),
        )
            .into_response()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{body::Body, http::Request};
    use http_body_util::BodyExt;
    use sqlx::postgres::PgPoolOptions;
    use tower::ServiceExt;

    #[test]
    fn settings_reject_unbounded_values() {
        assert_eq!(
            CoreSettings {
                public_session_ttl: Duration::zero(),
                ..CoreSettings::default()
            }
            .validate(),
            Err(ConfigurationError::InvalidSessionTtl)
        );
        assert_eq!(
            CoreSettings {
                authority_epoch: 0,
                ..CoreSettings::default()
            }
            .validate(),
            Err(ConfigurationError::InvalidAuthorityEpoch)
        );
    }

    #[test]
    fn listener_is_loopback_only_by_contract() {
        assert_eq!(
            parse_loopback_bind(None).unwrap(),
            "127.0.0.1:9202".parse::<SocketAddr>().unwrap()
        );
        assert!(parse_loopback_bind(Some("[::1]:9202")).is_ok());
        assert_eq!(
            parse_loopback_bind(Some("0.0.0.0:9202")),
            Err(ConfigurationError::ExternalBindForbidden)
        );
        assert_eq!(
            parse_loopback_bind(Some("not-an-address")),
            Err(ConfigurationError::InvalidBindAddress)
        );
    }

    #[test]
    fn edge_request_hash_matches_frozen_python_algorithm() {
        let body = json!({
            "model": "kolibri",
            "input": "Привет",
            "metadata": {"b": 2, "a": 1},
        });
        let digest = canonical_json_sha256(&json!({
            "method": "POST",
            "path": "/v1/responses",
            "body": body,
        }))
        .expect("canonical digest");
        let digest = digest.trim_start_matches("sha256:");
        assert!(verify_edge_request_hash("POST", "/v1/responses", &body, digest).is_ok());
        assert!(verify_edge_request_hash("POST", "/v1/responses", &body, &"0".repeat(64)).is_err());
    }

    #[test]
    fn input_text_supports_openai_string_and_message_parts() {
        assert_eq!(
            response_input_text(&json!({"input":"Привет"})).unwrap(),
            "Привет"
        );
        assert_eq!(
            response_input_text(&json!({
                "input": [{
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Первая"},
                        {"type": "input_text", "text": "Вторая"}
                    ]
                }]
            }))
            .unwrap(),
            "Первая\nВторая"
        );
    }

    #[test]
    fn idempotency_key_matches_edge_contract() {
        assert!(validate_idempotency_key("request-1234").is_ok());
        assert!(validate_idempotency_key("short").is_err());
        assert!(validate_idempotency_key("bad key with spaces").is_err());
    }

    #[test]
    fn public_origin_is_shared_with_postgres_boundary() {
        assert_eq!(
            kolibri_store_postgres::normalize_public_origin("https://KOLIBRIAI.RU:443").unwrap(),
            "https://kolibriai.ru"
        );
    }

    #[tokio::test]
    async fn malformed_json_uses_structured_core_error() {
        let pool = PgPoolOptions::new()
            .connect_lazy("postgresql://test:test@127.0.0.1/test_kolibri")
            .expect("lazy test pool");
        let router = build_router(pool, CoreSettings::default()).expect("router");
        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/internal/v1/public-sessions")
                    .header("content-type", "application/json")
                    .body(Body::from("{"))
                    .expect("request"),
            )
            .await
            .expect("response");
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let bytes = response
            .into_body()
            .collect()
            .await
            .expect("body")
            .to_bytes();
        let body: Value = serde_json::from_slice(&bytes).expect("structured JSON");
        assert_eq!(body["error"]["code"], "invalid_json_body");
        assert_eq!(body["error"]["type"], "core_error");
    }
}
