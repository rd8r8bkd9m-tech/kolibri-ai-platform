//! `PostgreSQL` authority boundary for the first durable Kolibri response slice.
//!
//! The crate owns transactionality only. Provider execution, HTTP sessions,
//! dispatch and `JetStream` publication remain outside this boundary.

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use kolibri_core::{canonical_json_sha256, validate_identifier};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use sqlx::{PgPool, Postgres, Row, Transaction};
use thiserror::Error;
use url::{Host, Url};
use uuid::Uuid;

const RESPONSE_AUTHORITY_MIGRATION: &str =
    include_str!("../migrations/0001_response_authority.sql");
const PUBLIC_SESSIONS_MIGRATION: &str = include_str!("../migrations/0002_public_sessions.sql");

const RESPONSE_SCOPE: &str = "response.create.v1";
const RESPONSE_SCHEMA: &str = "kolibri.response.v1";
const EVENT_SCHEMA: &str = "kolibri.event.v1";
const EVENT_SOURCE: &str = "control-plane/home";
const EVENT_TYPE: &str = "response.created";
const OUTBOX_TOPIC: &str = "kolibri.response";
const CANCEL_SCOPE: &str = "response.cancel.v1";
const CANCEL_EVENT_TYPE: &str = "response.cancelled";
const PUBLIC_SESSION_SCHEMA: &str = "kolibri.public-session.v1";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PublicSession {
    pub schema_version: String,
    pub id: String,
    pub origin: String,
    pub current_project_id: String,
    pub expires_at: DateTime<Utc>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PublicSessionIssue {
    pub session: PublicSession,
    pub credential: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct IssuePublicSessionCommand {
    pub origin: String,
    pub expires_at: DateTime<Utc>,
    pub occurred_at: DateTime<Utc>,
}

impl IssuePublicSessionCommand {
    /// Validates and normalizes the exact browser origin before persistence.
    ///
    /// # Errors
    ///
    /// Returns [`StoreError::InvalidCommand`] for a non-origin URL or an
    /// expiry outside the bounded public-session lifetime.
    pub fn normalized_origin(&self) -> Result<String, StoreError> {
        let origin = normalize_public_origin(&self.origin)?;
        let lifetime = self.expires_at - self.occurred_at;
        if lifetime <= chrono::Duration::zero() || lifetime > chrono::Duration::days(30) {
            return Err(StoreError::InvalidCommand(
                "public_session_lifetime_invalid".to_string(),
            ));
        }
        Ok(origin)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PublicPrincipal {
    pub session_id: String,
    pub origin: String,
}

impl PublicPrincipal {
    /// Returns the durable principal id derived from the opaque session id.
    ///
    /// # Errors
    ///
    /// Returns [`StoreError::InvalidCommand`] when the session identifier is
    /// outside the frozen identifier contract.
    pub fn principal_id(&self) -> Result<String, StoreError> {
        validate_identifier(&self.session_id)
            .map_err(|error| StoreError::InvalidCommand(format!("session_id:{error}")))?;
        Ok(format!("public.{}", self.session_id))
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CreateResponseCommand {
    pub principal_id: String,
    pub session_id: Option<String>,
    pub project_id: String,
    pub trace_id: String,
    pub idempotency_key: String,
    pub task_type: String,
    pub request: Value,
    pub user_message: String,
    pub actor: String,
    pub policy_version: String,
    pub authority_epoch: i64,
    pub occurred_at: DateTime<Utc>,
    /// Optional externally verified OpenAI-compatible request hash. The
    /// repository persists it as the idempotency binding when present.
    #[serde(default)]
    pub idempotency_request_sha256: Option<String>,
}

impl CreateResponseCommand {
    /// Validates identifiers, bounded text and the structured request payload.
    ///
    /// # Errors
    ///
    /// Returns [`StoreError::InvalidCommand`] when the command cannot cross the
    /// durable authority boundary.
    pub fn validate(&self) -> Result<(), StoreError> {
        validate_identifier(&self.principal_id)
            .map_err(|error| StoreError::InvalidCommand(format!("principal_id:{error}")))?;
        if let Some(session_id) = &self.session_id {
            validate_identifier(session_id)
                .map_err(|error| StoreError::InvalidCommand(format!("session_id:{error}")))?;
        }
        validate_identifier(&self.project_id)
            .map_err(|error| StoreError::InvalidCommand(format!("project_id:{error}")))?;
        validate_identifier(&self.trace_id)
            .map_err(|error| StoreError::InvalidCommand(format!("trace_id:{error}")))?;
        validate_bounded_text(&self.idempotency_key, "idempotency_key", 300)?;
        validate_wire_name(&self.task_type, "task_type")?;
        validate_bounded_text(&self.user_message, "user_message", 200_000)?;
        validate_bounded_text(&self.actor, "actor", 200)?;
        validate_bounded_text(&self.policy_version, "policy_version", 200)?;
        if self.authority_epoch < 1 {
            return Err(StoreError::InvalidCommand(
                "authority_epoch_must_be_positive".to_string(),
            ));
        }
        if !self.request.is_object() {
            return Err(StoreError::InvalidCommand(
                "request_must_be_object".to_string(),
            ));
        }
        if self
            .request
            .get("model")
            .is_some_and(|model| model.as_str() != Some("kolibri"))
        {
            return Err(StoreError::InvalidCommand(
                "public_model_must_be_kolibri".to_string(),
            ));
        }
        if let Some(request_sha256) = &self.idempotency_request_sha256 {
            validate_sha256(request_sha256, "idempotency_request_sha256")?;
        }
        Ok(())
    }

    /// Produces the canonical content hash used by idempotency claims.
    ///
    /// # Errors
    ///
    /// Returns an error when validation or canonical JSON serialization fails.
    pub fn request_sha256(&self) -> Result<String, StoreError> {
        self.validate()?;
        if let Some(request_sha256) = &self.idempotency_request_sha256 {
            return Ok(request_sha256.clone());
        }
        canonical_json_sha256(&json!({
            "schema_version": "kolibri.response-create-command.v1",
            "session_id": self.session_id,
            "project_id": self.project_id,
            "task_type": self.task_type,
            "request": self.request,
            "user_message": self.user_message,
        }))
        .map_err(|error| StoreError::InvalidCommand(error.to_string()))
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CancelResponseCommand {
    pub principal_id: String,
    pub response_id: String,
    pub idempotency_key: String,
    pub request_sha256: String,
    pub actor: String,
    pub policy_version: String,
    pub authority_epoch: i64,
    pub occurred_at: DateTime<Utc>,
}

impl CancelResponseCommand {
    /// Validates a cancellation before it enters the transactional boundary.
    ///
    /// # Errors
    ///
    /// Returns [`StoreError::InvalidCommand`] for invalid identifiers,
    /// hashes, actor metadata, or authority epochs.
    pub fn validate(&self) -> Result<(), StoreError> {
        validate_identifier(&self.principal_id)
            .map_err(|error| StoreError::InvalidCommand(format!("principal_id:{error}")))?;
        validate_identifier(&self.response_id)
            .map_err(|error| StoreError::InvalidCommand(format!("response_id:{error}")))?;
        validate_bounded_text(&self.idempotency_key, "idempotency_key", 300)?;
        validate_sha256(&self.request_sha256, "request_sha256")?;
        validate_bounded_text(&self.actor, "actor", 200)?;
        validate_bounded_text(&self.policy_version, "policy_version", 200)?;
        if self.authority_epoch < 1 {
            return Err(StoreError::InvalidCommand(
                "authority_epoch_must_be_positive".to_string(),
            ));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CancelResponseOutcome {
    pub changed: bool,
    pub response: StoredResponse,
    pub event: Option<StoredEvent>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct StoredResponse {
    pub schema_version: String,
    pub id: String,
    pub principal_id: String,
    pub session_id: Option<String>,
    pub project_id: String,
    pub trace_id: String,
    pub model: String,
    pub task_type: String,
    pub status: String,
    pub request: Value,
    pub request_sha256: String,
    pub output: Value,
    pub output_text: String,
    pub error: Option<Value>,
    pub cancel_requested: bool,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct StoredMessage {
    pub id: String,
    pub principal_id: String,
    pub session_id: Option<String>,
    pub project_id: String,
    pub response_id: String,
    pub role: String,
    pub content: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct StoredEvent {
    pub id: String,
    pub schema_version: String,
    pub event_type: String,
    pub source: String,
    pub subject: String,
    pub trace_id: String,
    pub sequence: i64,
    pub occurred_at: DateTime<Utc>,
    pub data: Value,
    pub provenance: Value,
    pub authority_epoch: i64,
    pub idempotency_key: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl StoredEvent {
    #[must_use]
    pub fn envelope(&self) -> Value {
        json!({
            "schema_version": self.schema_version,
            "id": self.id,
            "type": self.event_type,
            "source": self.source,
            "subject": self.subject,
            "trace_id": self.trace_id,
            "sequence": self.sequence,
            "occurred_at": self.occurred_at,
            "data": self.data,
            "provenance": self.provenance,
            "authority_epoch": self.authority_epoch,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CreateResponseOutcome {
    pub created: bool,
    pub response: StoredResponse,
    pub user_message: StoredMessage,
    pub assistant_message: StoredMessage,
    pub event: StoredEvent,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IdempotencyDecision {
    New,
    Replay,
    Conflict,
}

#[must_use]
pub fn classify_idempotency(
    existing_request_sha256: Option<&str>,
    incoming_request_sha256: &str,
) -> IdempotencyDecision {
    match existing_request_sha256 {
        None => IdempotencyDecision::New,
        Some(existing) if existing == incoming_request_sha256 => IdempotencyDecision::Replay,
        Some(_) => IdempotencyDecision::Conflict,
    }
}

#[async_trait]
pub trait PublicSessionRepository: Send + Sync {
    async fn issue_public_session(
        &self,
        command: &IssuePublicSessionCommand,
    ) -> Result<PublicSessionIssue, StoreError>;

    async fn resolve_public_session(
        &self,
        credential: &str,
        now: DateTime<Utc>,
    ) -> Result<Option<PublicSession>, StoreError>;

    async fn resolve_public_principal(
        &self,
        principal: &PublicPrincipal,
        now: DateTime<Utc>,
    ) -> Result<Option<PublicSession>, StoreError>;
}

#[async_trait]
pub trait ResponseRepository: Send + Sync {
    async fn create_response(
        &self,
        command: &CreateResponseCommand,
    ) -> Result<CreateResponseOutcome, StoreError>;

    async fn get_response(
        &self,
        principal_id: &str,
        response_id: &str,
    ) -> Result<Option<StoredResponse>, StoreError>;

    async fn list_response_events(
        &self,
        principal_id: &str,
        response_id: &str,
        after: i64,
        limit: i64,
    ) -> Result<Option<Vec<StoredEvent>>, StoreError>;

    async fn cancel_response(
        &self,
        command: &CancelResponseCommand,
    ) -> Result<Option<CancelResponseOutcome>, StoreError>;
}

#[derive(Debug, Clone)]
pub struct PostgresResponseRepository {
    pool: PgPool,
}

impl PostgresResponseRepository {
    #[must_use]
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    #[must_use]
    pub fn pool(&self) -> &PgPool {
        &self.pool
    }

    /// Applies the embedded, append-only migrations to the configured pool.
    ///
    /// # Errors
    ///
    /// Returns [`StoreError::Migration`] if `PostgreSQL` rejects a migration.
    pub async fn migrate(&self) -> Result<(), StoreError> {
        let mut transaction = self.pool.begin().await.map_err(StoreError::Migration)?;
        sqlx::raw_sql(RESPONSE_AUTHORITY_MIGRATION)
            .execute(&mut *transaction)
            .await
            .map_err(StoreError::Migration)?;
        sqlx::raw_sql(PUBLIC_SESSIONS_MIGRATION)
            .execute(&mut *transaction)
            .await
            .map_err(StoreError::Migration)?;
        transaction.commit().await.map_err(StoreError::Migration)
    }
}

#[async_trait]
impl PublicSessionRepository for PostgresResponseRepository {
    async fn issue_public_session(
        &self,
        command: &IssuePublicSessionCommand,
    ) -> Result<PublicSessionIssue, StoreError> {
        let origin = command.normalized_origin()?;
        let session_id = prefixed_id("sess");
        let current_project_id = prefixed_id("project_ephemeral");
        let credential = format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple());
        let credential_sha256 = credential_sha256(&credential);

        sqlx::query(
            r"
            INSERT INTO kolibri.public_sessions (
                id, schema_version, credential_sha256, origin,
                current_project_id, expires_at, revoked_at, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, NULL, $7, $7)
            ",
        )
        .bind(&session_id)
        .bind(PUBLIC_SESSION_SCHEMA)
        .bind(&credential_sha256)
        .bind(&origin)
        .bind(&current_project_id)
        .bind(command.expires_at)
        .bind(command.occurred_at)
        .execute(&self.pool)
        .await?;

        Ok(PublicSessionIssue {
            session: PublicSession {
                schema_version: PUBLIC_SESSION_SCHEMA.to_string(),
                id: session_id,
                origin,
                current_project_id,
                expires_at: command.expires_at,
                created_at: command.occurred_at,
                updated_at: command.occurred_at,
            },
            credential,
        })
    }

    async fn resolve_public_session(
        &self,
        credential: &str,
        now: DateTime<Utc>,
    ) -> Result<Option<PublicSession>, StoreError> {
        if !valid_session_credential(credential) {
            return Ok(None);
        }
        let row = sqlx::query(
            r"
            SELECT id, schema_version, origin, current_project_id,
                   expires_at, created_at, updated_at
            FROM kolibri.public_sessions
            WHERE credential_sha256 = $1
              AND revoked_at IS NULL
              AND expires_at > $2
            ",
        )
        .bind(credential_sha256(credential))
        .bind(now)
        .fetch_optional(&self.pool)
        .await?;
        row.map(|row| public_session_from_row(&row)).transpose()
    }

    async fn resolve_public_principal(
        &self,
        principal: &PublicPrincipal,
        now: DateTime<Utc>,
    ) -> Result<Option<PublicSession>, StoreError> {
        validate_identifier(&principal.session_id)
            .map_err(|error| StoreError::InvalidCommand(format!("session_id:{error}")))?;
        let origin = normalize_public_origin(&principal.origin)?;
        let row = sqlx::query(
            r"
            SELECT id, schema_version, origin, current_project_id,
                   expires_at, created_at, updated_at
            FROM kolibri.public_sessions
            WHERE id = $1
              AND origin = $2
              AND revoked_at IS NULL
              AND expires_at > $3
            ",
        )
        .bind(&principal.session_id)
        .bind(origin)
        .bind(now)
        .fetch_optional(&self.pool)
        .await?;
        row.map(|row| public_session_from_row(&row)).transpose()
    }
}

#[async_trait]
impl ResponseRepository for PostgresResponseRepository {
    #[allow(clippy::too_many_lines)]
    async fn create_response(
        &self,
        command: &CreateResponseCommand,
    ) -> Result<CreateResponseOutcome, StoreError> {
        let request_sha256 = command.request_sha256()?;
        let mut transaction = self.pool.begin().await?;

        let claimed = sqlx::query_scalar::<_, String>(
            r"
            INSERT INTO kolibri.idempotency_records (
                principal_id, scope, idempotency_key, request_sha256,
                resource_type, resource_id, replay_json, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, 'response', NULL, NULL, $5, $5)
            ON CONFLICT (principal_id, scope, idempotency_key) DO NOTHING
            RETURNING request_sha256
            ",
        )
        .bind(&command.principal_id)
        .bind(RESPONSE_SCOPE)
        .bind(&command.idempotency_key)
        .bind(&request_sha256)
        .bind(command.occurred_at)
        .fetch_optional(&mut *transaction)
        .await?;

        if claimed.is_none() {
            let existing = sqlx::query(
                r"
                SELECT request_sha256, resource_id
                FROM kolibri.idempotency_records
                WHERE principal_id = $1 AND scope = $2 AND idempotency_key = $3
                FOR SHARE
                ",
            )
            .bind(&command.principal_id)
            .bind(RESPONSE_SCOPE)
            .bind(&command.idempotency_key)
            .fetch_one(&mut *transaction)
            .await?;
            let existing_hash: String = existing.try_get("request_sha256")?;
            let resource_id: Option<String> = existing.try_get("resource_id")?;
            if classify_idempotency(Some(&existing_hash), &request_sha256)
                == IdempotencyDecision::Conflict
            {
                return Err(StoreError::IdempotencyConflict {
                    key: command.idempotency_key.clone(),
                    existing_resource_id: resource_id,
                });
            }
            let response_id = resource_id.ok_or_else(|| {
                StoreError::CorruptState("idempotency_resource_missing".to_string())
            })?;
            let outcome = load_outcome(&mut transaction, &command.principal_id, &response_id)
                .await?
                .ok_or_else(|| {
                    StoreError::CorruptState("idempotency_response_missing".to_string())
                })?;
            transaction.commit().await?;
            return Ok(CreateResponseOutcome {
                created: false,
                ..outcome
            });
        }

        let response_id = prefixed_id("resp");
        let user_message_id = prefixed_id("message_user");
        let assistant_message_id = prefixed_id("message");
        let event_id = prefixed_id("evt");
        let outbox_id = prefixed_id("outbox");
        let subject = format!("response/{response_id}");
        let event_idempotency_key = format!("response.created:{response_id}");

        sqlx::query(
            r"
            INSERT INTO kolibri.responses (
                id, principal_id, session_id, project_id, trace_id, model,
                task_type, status, request_json, request_sha256, output_json,
                output_text, error_json, cancel_requested, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, 'kolibri', $6, 'queued', $7, $8,
                    '[]'::JSONB, '', NULL, FALSE, $9, $9)
            ",
        )
        .bind(&response_id)
        .bind(&command.principal_id)
        .bind(&command.session_id)
        .bind(&command.project_id)
        .bind(&command.trace_id)
        .bind(&command.task_type)
        .bind(&command.request)
        .bind(&request_sha256)
        .bind(command.occurred_at)
        .execute(&mut *transaction)
        .await?;

        insert_message(
            &mut transaction,
            &user_message_id,
            command,
            &response_id,
            "user",
            &command.user_message,
        )
        .await?;
        insert_message(
            &mut transaction,
            &assistant_message_id,
            command,
            &response_id,
            "assistant",
            "",
        )
        .await?;

        let sequence = sqlx::query_scalar::<_, i64>(
            r"
            INSERT INTO kolibri.event_stream_heads (subject, last_sequence, updated_at)
            VALUES ($1, 1, $2)
            ON CONFLICT (subject) DO UPDATE
            SET last_sequence = kolibri.event_stream_heads.last_sequence + 1,
                updated_at = EXCLUDED.updated_at
            RETURNING last_sequence
            ",
        )
        .bind(&subject)
        .bind(command.occurred_at)
        .fetch_one(&mut *transaction)
        .await?;

        let event_data = json!({
            "response_id": response_id,
            "project_id": command.project_id,
            "status": "queued",
            "model": "kolibri",
            "task_type": command.task_type,
            "request_sha256": request_sha256,
        });
        let provenance = json!({
            "actor": command.actor,
            "policy_version": command.policy_version,
        });

        sqlx::query(
            r"
            INSERT INTO kolibri.events (
                id, schema_version, event_type, source, subject, trace_id,
                sequence, occurred_at, data, provenance, authority_epoch,
                idempotency_key, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $8, $8)
            ",
        )
        .bind(&event_id)
        .bind(EVENT_SCHEMA)
        .bind(EVENT_TYPE)
        .bind(EVENT_SOURCE)
        .bind(&subject)
        .bind(&command.trace_id)
        .bind(sequence)
        .bind(command.occurred_at)
        .bind(&event_data)
        .bind(&provenance)
        .bind(command.authority_epoch)
        .bind(&event_idempotency_key)
        .execute(&mut *transaction)
        .await?;

        let event = StoredEvent {
            id: event_id.clone(),
            schema_version: EVENT_SCHEMA.to_string(),
            event_type: EVENT_TYPE.to_string(),
            source: EVENT_SOURCE.to_string(),
            subject,
            trace_id: command.trace_id.clone(),
            sequence,
            occurred_at: command.occurred_at,
            data: event_data,
            provenance,
            authority_epoch: command.authority_epoch,
            idempotency_key: event_idempotency_key,
            created_at: command.occurred_at,
            updated_at: command.occurred_at,
        };
        let event_envelope = event.envelope();

        sqlx::query(
            r"
            INSERT INTO kolibri.outbox (
                id, event_id, topic, payload, state, attempts, available_at,
                created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, 'pending', 0, $5, $5, $5)
            ",
        )
        .bind(&outbox_id)
        .bind(&event_id)
        .bind(OUTBOX_TOPIC)
        .bind(&event_envelope)
        .bind(command.occurred_at)
        .execute(&mut *transaction)
        .await?;

        let replay_json = json!({
            "resource_type": "response",
            "resource_id": response_id,
            "status": "queued",
        });
        let updated = sqlx::query(
            r"
            UPDATE kolibri.idempotency_records
            SET resource_id = $4, replay_json = $5, updated_at = $6
            WHERE principal_id = $1 AND scope = $2 AND idempotency_key = $3
            ",
        )
        .bind(&command.principal_id)
        .bind(RESPONSE_SCOPE)
        .bind(&command.idempotency_key)
        .bind(&response_id)
        .bind(&replay_json)
        .bind(command.occurred_at)
        .execute(&mut *transaction)
        .await?;
        if updated.rows_affected() != 1 {
            return Err(StoreError::CorruptState(
                "idempotency_claim_update_failed".to_string(),
            ));
        }

        let outcome = load_outcome(&mut transaction, &command.principal_id, &response_id)
            .await?
            .ok_or_else(|| StoreError::CorruptState("created_response_missing".to_string()))?;
        transaction.commit().await?;
        Ok(CreateResponseOutcome {
            created: true,
            ..outcome
        })
    }

    async fn get_response(
        &self,
        principal_id: &str,
        response_id: &str,
    ) -> Result<Option<StoredResponse>, StoreError> {
        validate_identifier(principal_id)
            .map_err(|error| StoreError::InvalidCommand(format!("principal_id:{error}")))?;
        validate_identifier(response_id)
            .map_err(|error| StoreError::InvalidCommand(format!("response_id:{error}")))?;
        let row = sqlx::query(
            r"
            SELECT id, principal_id, session_id, project_id, trace_id, model,
                   task_type, status, request_json, request_sha256, output_json,
                   output_text, error_json, cancel_requested, created_at, updated_at
            FROM kolibri.responses
            WHERE principal_id = $1 AND id = $2
            ",
        )
        .bind(principal_id)
        .bind(response_id)
        .fetch_optional(&self.pool)
        .await?;
        row.map(|row| response_from_row(&row)).transpose()
    }

    async fn list_response_events(
        &self,
        principal_id: &str,
        response_id: &str,
        after: i64,
        limit: i64,
    ) -> Result<Option<Vec<StoredEvent>>, StoreError> {
        validate_identifier(principal_id)
            .map_err(|error| StoreError::InvalidCommand(format!("principal_id:{error}")))?;
        validate_identifier(response_id)
            .map_err(|error| StoreError::InvalidCommand(format!("response_id:{error}")))?;
        if after < 0 || !(1..=500).contains(&limit) {
            return Err(StoreError::InvalidCommand(
                "response_event_cursor_invalid".to_string(),
            ));
        }
        let exists = sqlx::query_scalar::<_, bool>(
            r"
            SELECT EXISTS (
                SELECT 1 FROM kolibri.responses
                WHERE principal_id = $1 AND id = $2
            )
            ",
        )
        .bind(principal_id)
        .bind(response_id)
        .fetch_one(&self.pool)
        .await?;
        if !exists {
            return Ok(None);
        }

        let rows = sqlx::query(
            r"
            SELECT id, schema_version, event_type, source, subject, trace_id,
                   sequence, occurred_at, data, provenance, authority_epoch,
                   idempotency_key, created_at, updated_at
            FROM kolibri.events
            WHERE subject = $1 AND sequence > $2
            ORDER BY sequence
            LIMIT $3
            ",
        )
        .bind(format!("response/{response_id}"))
        .bind(after)
        .bind(limit)
        .fetch_all(&self.pool)
        .await?;
        rows.into_iter()
            .map(|row| event_from_row(&row))
            .collect::<Result<Vec<_>, _>>()
            .map(Some)
    }

    #[allow(clippy::too_many_lines)]
    async fn cancel_response(
        &self,
        command: &CancelResponseCommand,
    ) -> Result<Option<CancelResponseOutcome>, StoreError> {
        command.validate()?;
        let mut transaction = self.pool.begin().await?;
        let claimed = sqlx::query_scalar::<_, String>(
            r"
            INSERT INTO kolibri.idempotency_records (
                principal_id, scope, idempotency_key, request_sha256,
                resource_type, resource_id, replay_json, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, 'response', NULL, NULL, $5, $5)
            ON CONFLICT (principal_id, scope, idempotency_key) DO NOTHING
            RETURNING request_sha256
            ",
        )
        .bind(&command.principal_id)
        .bind(CANCEL_SCOPE)
        .bind(&command.idempotency_key)
        .bind(&command.request_sha256)
        .bind(command.occurred_at)
        .fetch_optional(&mut *transaction)
        .await?;

        if claimed.is_none() {
            let existing = sqlx::query(
                r"
                SELECT request_sha256, resource_id
                FROM kolibri.idempotency_records
                WHERE principal_id = $1 AND scope = $2 AND idempotency_key = $3
                FOR SHARE
                ",
            )
            .bind(&command.principal_id)
            .bind(CANCEL_SCOPE)
            .bind(&command.idempotency_key)
            .fetch_one(&mut *transaction)
            .await?;
            let existing_hash: String = existing.try_get("request_sha256")?;
            let resource_id: Option<String> = existing.try_get("resource_id")?;
            if classify_idempotency(Some(&existing_hash), &command.request_sha256)
                == IdempotencyDecision::Conflict
            {
                return Err(StoreError::IdempotencyConflict {
                    key: command.idempotency_key.clone(),
                    existing_resource_id: resource_id,
                });
            }
            let resource_id = resource_id.ok_or_else(|| {
                StoreError::CorruptState("cancel_idempotency_resource_missing".to_string())
            })?;
            if resource_id != command.response_id {
                return Err(StoreError::CorruptState(
                    "cancel_idempotency_resource_mismatch".to_string(),
                ));
            }
            let response = load_response_for_update(
                &mut transaction,
                &command.principal_id,
                &command.response_id,
            )
            .await?
            .ok_or_else(|| {
                StoreError::CorruptState("cancel_idempotency_response_missing".to_string())
            })?;
            transaction.commit().await?;
            return Ok(Some(CancelResponseOutcome {
                changed: false,
                response,
                event: None,
            }));
        }

        let Some(mut response) = load_response_for_update(
            &mut transaction,
            &command.principal_id,
            &command.response_id,
        )
        .await?
        else {
            return Ok(None);
        };

        let changed = !is_terminal_response_status(&response.status);
        let event = if changed {
            sqlx::query(
                r"
                UPDATE kolibri.responses
                SET status = 'cancelled', cancel_requested = TRUE,
                    completed_at = $3, updated_at = $3
                WHERE principal_id = $1 AND id = $2
                ",
            )
            .bind(&command.principal_id)
            .bind(&command.response_id)
            .bind(command.occurred_at)
            .execute(&mut *transaction)
            .await?;

            let subject = format!("response/{}", command.response_id);
            let sequence =
                next_event_sequence(&mut transaction, &subject, command.occurred_at).await?;
            let event = StoredEvent {
                id: prefixed_id("evt"),
                schema_version: EVENT_SCHEMA.to_string(),
                event_type: CANCEL_EVENT_TYPE.to_string(),
                source: EVENT_SOURCE.to_string(),
                subject,
                trace_id: response.trace_id.clone(),
                sequence,
                occurred_at: command.occurred_at,
                data: json!({
                    "id": command.response_id,
                    "response_id": command.response_id,
                    "project_id": response.project_id,
                    "status": "cancelled",
                }),
                provenance: json!({
                    "actor": command.actor,
                    "policy_version": command.policy_version,
                }),
                authority_epoch: command.authority_epoch,
                idempotency_key: format!("response.cancelled:{}", command.response_id),
                created_at: command.occurred_at,
                updated_at: command.occurred_at,
            };
            insert_event_and_outbox(&mut transaction, &event).await?;
            Some(event)
        } else {
            None
        };

        let replay_json = json!({
            "resource_type": "response",
            "resource_id": command.response_id,
            "status": if changed { "cancelled" } else { response.status.as_str() },
        });
        let updated = sqlx::query(
            r"
            UPDATE kolibri.idempotency_records
            SET resource_id = $4, replay_json = $5, updated_at = $6
            WHERE principal_id = $1 AND scope = $2 AND idempotency_key = $3
            ",
        )
        .bind(&command.principal_id)
        .bind(CANCEL_SCOPE)
        .bind(&command.idempotency_key)
        .bind(&command.response_id)
        .bind(&replay_json)
        .bind(command.occurred_at)
        .execute(&mut *transaction)
        .await?;
        if updated.rows_affected() != 1 {
            return Err(StoreError::CorruptState(
                "cancel_idempotency_claim_update_failed".to_string(),
            ));
        }

        if changed {
            response.status = "cancelled".to_string();
            response.cancel_requested = true;
            response.updated_at = command.occurred_at;
        }
        transaction.commit().await?;
        Ok(Some(CancelResponseOutcome {
            changed,
            response,
            event,
        }))
    }
}

async fn load_response_for_update(
    transaction: &mut Transaction<'_, Postgres>,
    principal_id: &str,
    response_id: &str,
) -> Result<Option<StoredResponse>, StoreError> {
    let row = sqlx::query(
        r"
        SELECT id, principal_id, session_id, project_id, trace_id, model,
               task_type, status, request_json, request_sha256, output_json,
               output_text, error_json, cancel_requested, created_at, updated_at
        FROM kolibri.responses
        WHERE principal_id = $1 AND id = $2
        FOR UPDATE
        ",
    )
    .bind(principal_id)
    .bind(response_id)
    .fetch_optional(&mut **transaction)
    .await?;
    row.map(|row| response_from_row(&row)).transpose()
}

async fn next_event_sequence(
    transaction: &mut Transaction<'_, Postgres>,
    subject: &str,
    occurred_at: DateTime<Utc>,
) -> Result<i64, StoreError> {
    sqlx::query_scalar::<_, i64>(
        r"
        INSERT INTO kolibri.event_stream_heads (subject, last_sequence, updated_at)
        VALUES ($1, 1, $2)
        ON CONFLICT (subject) DO UPDATE
        SET last_sequence = kolibri.event_stream_heads.last_sequence + 1,
            updated_at = EXCLUDED.updated_at
        RETURNING last_sequence
        ",
    )
    .bind(subject)
    .bind(occurred_at)
    .fetch_one(&mut **transaction)
    .await
    .map_err(StoreError::Database)
}

async fn insert_event_and_outbox(
    transaction: &mut Transaction<'_, Postgres>,
    event: &StoredEvent,
) -> Result<(), StoreError> {
    sqlx::query(
        r"
        INSERT INTO kolibri.events (
            id, schema_version, event_type, source, subject, trace_id,
            sequence, occurred_at, data, provenance, authority_epoch,
            idempotency_key, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        ",
    )
    .bind(&event.id)
    .bind(&event.schema_version)
    .bind(&event.event_type)
    .bind(&event.source)
    .bind(&event.subject)
    .bind(&event.trace_id)
    .bind(event.sequence)
    .bind(event.occurred_at)
    .bind(&event.data)
    .bind(&event.provenance)
    .bind(event.authority_epoch)
    .bind(&event.idempotency_key)
    .bind(event.created_at)
    .bind(event.updated_at)
    .execute(&mut **transaction)
    .await?;

    sqlx::query(
        r"
        INSERT INTO kolibri.outbox (
            id, event_id, topic, payload, state, attempts, available_at,
            created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, 'pending', 0, $5, $5, $5)
        ",
    )
    .bind(prefixed_id("outbox"))
    .bind(&event.id)
    .bind(OUTBOX_TOPIC)
    .bind(event.envelope())
    .bind(event.occurred_at)
    .execute(&mut **transaction)
    .await?;
    Ok(())
}

async fn insert_message(
    transaction: &mut Transaction<'_, Postgres>,
    message_id: &str,
    command: &CreateResponseCommand,
    response_id: &str,
    role: &str,
    content: &str,
) -> Result<(), StoreError> {
    sqlx::query(
        r"
        INSERT INTO kolibri.messages (
            id, principal_id, session_id, project_id, response_id, role,
            content, deleted_at, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, NULL, $8, $8)
        ",
    )
    .bind(message_id)
    .bind(&command.principal_id)
    .bind(&command.session_id)
    .bind(&command.project_id)
    .bind(response_id)
    .bind(role)
    .bind(content)
    .bind(command.occurred_at)
    .execute(&mut **transaction)
    .await?;
    Ok(())
}

async fn load_outcome(
    transaction: &mut Transaction<'_, Postgres>,
    principal_id: &str,
    response_id: &str,
) -> Result<Option<CreateResponseOutcome>, StoreError> {
    let response_row = sqlx::query(
        r"
        SELECT id, principal_id, session_id, project_id, trace_id, model,
               task_type, status, request_json, request_sha256, output_json,
               output_text, error_json, cancel_requested, created_at, updated_at
        FROM kolibri.responses
        WHERE principal_id = $1 AND id = $2
        ",
    )
    .bind(principal_id)
    .bind(response_id)
    .fetch_optional(&mut **transaction)
    .await?;
    let Some(response_row) = response_row else {
        return Ok(None);
    };
    let response = response_from_row(&response_row)?;

    let message_rows = sqlx::query(
        r"
        SELECT id, principal_id, session_id, project_id, response_id, role,
               content, created_at, updated_at
        FROM kolibri.messages
        WHERE principal_id = $1 AND response_id = $2 AND deleted_at IS NULL
        ORDER BY role DESC
        ",
    )
    .bind(principal_id)
    .bind(response_id)
    .fetch_all(&mut **transaction)
    .await?;
    let mut user_message = None;
    let mut assistant_message = None;
    for row in message_rows {
        let message = message_from_row(&row)?;
        match message.role.as_str() {
            "user" => user_message = Some(message),
            "assistant" => assistant_message = Some(message),
            role => {
                return Err(StoreError::CorruptState(format!(
                    "unexpected_message_role:{role}"
                )));
            }
        }
    }

    let event_row = sqlx::query(
        r"
        SELECT id, schema_version, event_type, source, subject, trace_id,
               sequence, occurred_at, data, provenance, authority_epoch,
               idempotency_key, created_at, updated_at
        FROM kolibri.events
        WHERE subject = $1 AND event_type = 'response.created'
        ORDER BY sequence
        LIMIT 1
        ",
    )
    .bind(format!("response/{response_id}"))
    .fetch_optional(&mut **transaction)
    .await?;

    Ok(Some(CreateResponseOutcome {
        created: false,
        response,
        user_message: user_message
            .ok_or_else(|| StoreError::CorruptState("response_user_message_missing".to_string()))?,
        assistant_message: assistant_message.ok_or_else(|| {
            StoreError::CorruptState("response_assistant_message_missing".to_string())
        })?,
        event: event_row
            .map(|row| event_from_row(&row))
            .transpose()?
            .ok_or_else(|| {
                StoreError::CorruptState("response_created_event_missing".to_string())
            })?,
    }))
}

fn response_from_row(row: &sqlx::postgres::PgRow) -> Result<StoredResponse, StoreError> {
    Ok(StoredResponse {
        schema_version: RESPONSE_SCHEMA.to_string(),
        id: row.try_get("id")?,
        principal_id: row.try_get("principal_id")?,
        session_id: row.try_get("session_id")?,
        project_id: row.try_get("project_id")?,
        trace_id: row.try_get("trace_id")?,
        model: row.try_get("model")?,
        task_type: row.try_get("task_type")?,
        status: row.try_get("status")?,
        request: row.try_get("request_json")?,
        request_sha256: row.try_get("request_sha256")?,
        output: row.try_get("output_json")?,
        output_text: row.try_get("output_text")?,
        error: row.try_get("error_json")?,
        cancel_requested: row.try_get("cancel_requested")?,
        created_at: row.try_get("created_at")?,
        updated_at: row.try_get("updated_at")?,
    })
}

fn message_from_row(row: &sqlx::postgres::PgRow) -> Result<StoredMessage, StoreError> {
    Ok(StoredMessage {
        id: row.try_get("id")?,
        principal_id: row.try_get("principal_id")?,
        session_id: row.try_get("session_id")?,
        project_id: row.try_get("project_id")?,
        response_id: row.try_get("response_id")?,
        role: row.try_get("role")?,
        content: row.try_get("content")?,
        created_at: row.try_get("created_at")?,
        updated_at: row.try_get("updated_at")?,
    })
}

fn event_from_row(row: &sqlx::postgres::PgRow) -> Result<StoredEvent, StoreError> {
    Ok(StoredEvent {
        id: row.try_get("id")?,
        schema_version: row.try_get("schema_version")?,
        event_type: row.try_get("event_type")?,
        source: row.try_get("source")?,
        subject: row.try_get("subject")?,
        trace_id: row.try_get("trace_id")?,
        sequence: row.try_get("sequence")?,
        occurred_at: row.try_get("occurred_at")?,
        data: row.try_get("data")?,
        provenance: row.try_get("provenance")?,
        authority_epoch: row.try_get("authority_epoch")?,
        idempotency_key: row.try_get("idempotency_key")?,
        created_at: row.try_get("created_at")?,
        updated_at: row.try_get("updated_at")?,
    })
}

fn public_session_from_row(row: &sqlx::postgres::PgRow) -> Result<PublicSession, StoreError> {
    Ok(PublicSession {
        schema_version: row.try_get("schema_version")?,
        id: row.try_get("id")?,
        origin: row.try_get("origin")?,
        current_project_id: row.try_get("current_project_id")?,
        expires_at: row.try_get("expires_at")?,
        created_at: row.try_get("created_at")?,
        updated_at: row.try_get("updated_at")?,
    })
}

/// Canonicalizes a browser `Origin` value without accepting paths, userinfo,
/// query strings or fragments.
///
/// # Errors
///
/// Returns [`StoreError::InvalidCommand`] when the value is not an exact HTTP
/// or HTTPS origin.
pub fn normalize_public_origin(value: &str) -> Result<String, StoreError> {
    if value.len() > 2_048 {
        return Err(StoreError::InvalidCommand(
            "public_session_origin_invalid".to_string(),
        ));
    }
    let parsed = Url::parse(value.trim())
        .map_err(|_| StoreError::InvalidCommand("public_session_origin_invalid".to_string()))?;
    if !matches!(parsed.scheme(), "http" | "https")
        || !parsed.username().is_empty()
        || parsed.password().is_some()
        || parsed.path() != "/"
        || parsed.query().is_some()
        || parsed.fragment().is_some()
    {
        return Err(StoreError::InvalidCommand(
            "public_session_origin_invalid".to_string(),
        ));
    }
    let host = match parsed.host() {
        Some(Host::Domain(domain)) => domain.to_string(),
        Some(Host::Ipv4(address)) => address.to_string(),
        Some(Host::Ipv6(address)) => format!("[{address}]"),
        None => {
            return Err(StoreError::InvalidCommand(
                "public_session_origin_invalid".to_string(),
            ));
        }
    };
    let default_port = match parsed.scheme() {
        "http" => 80,
        "https" => 443,
        _ => unreachable!("scheme checked above"),
    };
    let authority = match parsed.port() {
        Some(port) if port != default_port => format!("{host}:{port}"),
        _ => host,
    };
    Ok(format!("{}://{authority}", parsed.scheme()))
}

fn credential_sha256(credential: &str) -> String {
    let digest = Sha256::digest(credential.as_bytes());
    format!("sha256:{digest:x}")
}

fn valid_session_credential(credential: &str) -> bool {
    (20..=256).contains(&credential.len())
        && credential
            .bytes()
            .all(|value| value.is_ascii_alphanumeric() || matches!(value, b'_' | b'-'))
}

fn validate_sha256(value: &str, field: &str) -> Result<(), StoreError> {
    let Some(digest) = value.strip_prefix("sha256:") else {
        return Err(StoreError::InvalidCommand(format!("{field}_invalid")));
    };
    if digest.len() != 64
        || !digest
            .bytes()
            .all(|character| character.is_ascii_digit() || (b'a'..=b'f').contains(&character))
    {
        return Err(StoreError::InvalidCommand(format!("{field}_invalid")));
    }
    Ok(())
}

fn is_terminal_response_status(status: &str) -> bool {
    matches!(status, "completed" | "failed" | "cancelled" | "incomplete")
}

fn prefixed_id(prefix: &str) -> String {
    format!("{prefix}_{}", Uuid::new_v4().simple())
}

fn validate_bounded_text(value: &str, field: &str, maximum: usize) -> Result<(), StoreError> {
    let length = value.chars().count();
    if value.trim().is_empty() || length > maximum {
        return Err(StoreError::InvalidCommand(format!("{field}_invalid")));
    }
    Ok(())
}

fn validate_wire_name(value: &str, field: &str) -> Result<(), StoreError> {
    validate_bounded_text(value, field, 100)?;
    let mut characters = value.chars();
    if !characters
        .next()
        .is_some_and(|value| value.is_ascii_lowercase())
        || !characters.all(|value| {
            value.is_ascii_lowercase() || value.is_ascii_digit() || matches!(value, '_' | '.' | '-')
        })
    {
        return Err(StoreError::InvalidCommand(format!("{field}_invalid")));
    }
    Ok(())
}

#[derive(Debug, Error)]
pub enum StoreError {
    #[error("invalid response command: {0}")]
    InvalidCommand(String),
    #[error("idempotency key {key:?} is already bound to a different request")]
    IdempotencyConflict {
        key: String,
        existing_resource_id: Option<String>,
    },
    #[error("durable response state is corrupt: {0}")]
    CorruptState(String),
    #[error("PostgreSQL response store failed")]
    Database(#[from] sqlx::Error),
    #[error("PostgreSQL migration failed")]
    Migration(#[source] sqlx::Error),
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;

    fn command(request: Value) -> CreateResponseCommand {
        CreateResponseCommand {
            principal_id: "public.session_01".to_string(),
            session_id: Some("session_01".to_string()),
            project_id: "project_01".to_string(),
            trace_id: "trace.response_01".to_string(),
            idempotency_key: "response-key-01".to_string(),
            task_type: "chat".to_string(),
            request,
            user_message: "Привет".to_string(),
            actor: "api-gateway".to_string(),
            policy_version: "v1".to_string(),
            authority_epoch: 1,
            occurred_at: Utc
                .with_ymd_and_hms(2026, 7, 12, 12, 0, 0)
                .single()
                .expect("valid test timestamp"),
            idempotency_request_sha256: None,
        }
    }

    #[test]
    fn request_hash_is_canonical_and_covers_semantic_input() {
        let first = command(json!({"model":"kolibri","input":"Привет","metadata":{"b":2,"a":1}}));
        let second = command(json!({"metadata":{"a":1,"b":2},"input":"Привет","model":"kolibri"}));
        assert_eq!(
            first.request_sha256().unwrap(),
            second.request_sha256().unwrap()
        );

        let changed = command(json!({"model":"kolibri","input":"Другой запрос"}));
        assert_ne!(
            first.request_sha256().unwrap(),
            changed.request_sha256().unwrap()
        );
    }

    #[test]
    fn idempotency_decision_distinguishes_replay_from_conflict() {
        assert_eq!(
            classify_idempotency(None, "sha256:new"),
            IdempotencyDecision::New
        );
        assert_eq!(
            classify_idempotency(Some("sha256:same"), "sha256:same"),
            IdempotencyDecision::Replay
        );
        assert_eq!(
            classify_idempotency(Some("sha256:old"), "sha256:new"),
            IdempotencyDecision::Conflict
        );
    }

    #[test]
    fn command_rejects_unscoped_or_unstructured_input() {
        let mut invalid = command(Value::String("not an object".to_string()));
        assert!(matches!(
            invalid.validate(),
            Err(StoreError::InvalidCommand(_))
        ));
        invalid.request = json!({"model":"kolibri","input":"Привет"});
        invalid.authority_epoch = 0;
        assert!(matches!(
            invalid.validate(),
            Err(StoreError::InvalidCommand(_))
        ));
        invalid.authority_epoch = 1;
        invalid.request = json!({"model":"another-provider","input":"Привет"});
        assert!(matches!(
            invalid.validate(),
            Err(StoreError::InvalidCommand(_))
        ));
    }

    #[test]
    fn migration_contains_atomic_response_evidence_tables_and_constraints() {
        let migration = format!(
            "{}\n{}",
            include_str!("../migrations/0001_response_authority.sql"),
            include_str!("../migrations/0002_public_sessions.sql")
        );
        for required in [
            "kolibri.idempotency_records",
            "kolibri.responses",
            "kolibri.messages",
            "kolibri.event_stream_heads",
            "kolibri.events",
            "kolibri.outbox",
            "messages_one_role_per_response",
            "events_subject_sequence_unique",
            "events_source_idempotency_unique",
            "kolibri.public_sessions",
            "public_sessions_credential_sha256_format",
            "public_sessions_active_expiry_idx",
        ] {
            assert!(
                migration.contains(required),
                "migration is missing {required}"
            );
        }
    }

    #[test]
    fn exact_origin_normalization_is_strict() {
        assert_eq!(
            normalize_public_origin("HTTPS://KOLIBRIAI.RU:443").unwrap(),
            "https://kolibriai.ru"
        );
        assert_eq!(
            normalize_public_origin("http://[::1]:5190").unwrap(),
            "http://[::1]:5190"
        );
        for invalid in [
            "https://kolibriai.ru/app",
            "https://user@kolibriai.ru",
            "https://kolibriai.ru/?query=1",
            "file:///tmp/app",
        ] {
            assert!(matches!(
                normalize_public_origin(invalid),
                Err(StoreError::InvalidCommand(_))
            ));
        }
    }

    #[test]
    fn externally_verified_request_hash_can_bind_idempotency() {
        let mut request = command(json!({"model":"kolibri","input":"Привет"}));
        let edge_hash = format!("sha256:{}", "a".repeat(64));
        request.idempotency_request_sha256 = Some(edge_hash.clone());
        assert_eq!(request.request_sha256().unwrap(), edge_hash);

        request.idempotency_request_sha256 = Some("sha256:not-a-digest".to_string());
        assert!(matches!(
            request.request_sha256(),
            Err(StoreError::InvalidCommand(_))
        ));
    }
}
