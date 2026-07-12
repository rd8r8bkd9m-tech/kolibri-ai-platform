use chrono::{Duration, TimeZone, Utc};
use kolibri_store_postgres::{
    CancelResponseCommand, CreateResponseCommand, IssuePublicSessionCommand,
    PostgresResponseRepository, PublicPrincipal, PublicSessionRepository, ResponseRepository,
    StoreError,
};
use serde_json::json;
use sqlx::postgres::PgPoolOptions;
use uuid::Uuid;

fn test_database_url() -> Option<String> {
    let value = std::env::var("TEST_DATABASE_URL").ok()?;
    assert!(
        value.to_ascii_lowercase().contains("test"),
        "refusing to run PostgreSQL integration test against a URL without 'test'"
    );
    Some(value)
}

#[tokio::test]
#[ignore = "set TEST_DATABASE_URL to an isolated PostgreSQL test database"]
#[allow(clippy::too_many_lines)]
async fn response_creation_is_atomic_replayable_and_conflict_safe() {
    let Some(database_url) = test_database_url() else {
        return;
    };
    let pool = PgPoolOptions::new()
        .max_connections(4)
        .connect(&database_url)
        .await
        .expect("connect to isolated test database");
    let repository = PostgresResponseRepository::new(pool.clone());
    repository.migrate().await.expect("run embedded migrations");

    let suffix = Uuid::new_v4().simple().to_string();
    let occurred_at = Utc
        .with_ymd_and_hms(2026, 7, 12, 12, 0, 0)
        .single()
        .expect("valid timestamp");
    let issued = repository
        .issue_public_session(&IssuePublicSessionCommand {
            origin: "https://kolibriai.ru".to_string(),
            expires_at: occurred_at + Duration::hours(24),
            occurred_at,
        })
        .await
        .expect("issue public session");
    assert!(!issued.credential.is_empty());
    let resolved = repository
        .resolve_public_session(&issued.credential, occurred_at)
        .await
        .expect("resolve public session")
        .expect("active public session");
    assert_eq!(resolved, issued.session);
    let public_principal = PublicPrincipal {
        session_id: issued.session.id.clone(),
        origin: issued.session.origin.clone(),
    };
    assert_eq!(
        repository
            .resolve_public_principal(&public_principal, occurred_at)
            .await
            .expect("resolve exact-origin principal"),
        Some(issued.session.clone())
    );
    assert!(
        repository
            .resolve_public_principal(
                &PublicPrincipal {
                    origin: "https://example.com".to_string(),
                    ..public_principal.clone()
                },
                occurred_at,
            )
            .await
            .expect("reject other origin")
            .is_none()
    );

    let principal_id = public_principal.principal_id().expect("principal id");
    let project_id = issued.session.current_project_id.clone();
    let command = CreateResponseCommand {
        principal_id: principal_id.clone(),
        session_id: Some(issued.session.id.clone()),
        project_id,
        trace_id: format!("test.trace_{suffix}"),
        idempotency_key: format!("test-response-{suffix}"),
        task_type: "chat".to_string(),
        request: json!({"model":"kolibri","input":"Привет"}),
        user_message: "Привет".to_string(),
        actor: "integration-test".to_string(),
        policy_version: "test-v1".to_string(),
        authority_epoch: 1,
        occurred_at,
        idempotency_request_sha256: Some(format!("sha256:{}", "a".repeat(64))),
    };

    let created = repository
        .create_response(&command)
        .await
        .expect("create durable response");
    assert!(created.created);
    assert_eq!(created.response.status, "queued");
    assert_eq!(created.user_message.content, "Привет");
    assert!(created.assistant_message.content.is_empty());
    assert_eq!(created.event.sequence, 1);

    let initial_events = repository
        .list_response_events(&principal_id, &created.response.id, 0, 100)
        .await
        .expect("list response events")
        .expect("owned response");
    assert_eq!(initial_events, vec![created.event.clone()]);

    let replayed = repository
        .create_response(&command)
        .await
        .expect("replay durable response");
    assert!(!replayed.created);
    assert_eq!(replayed.response.id, created.response.id);
    assert_eq!(replayed.assistant_message.id, created.assistant_message.id);
    assert_eq!(replayed.event.id, created.event.id);

    let mut conflicting = command.clone();
    conflicting.request = json!({"model":"kolibri","input":"Другой запрос"});
    conflicting.idempotency_request_sha256 = Some(format!("sha256:{}", "c".repeat(64)));
    assert!(matches!(
        repository.create_response(&conflicting).await,
        Err(StoreError::IdempotencyConflict { .. })
    ));

    let cancel_command = CancelResponseCommand {
        principal_id: principal_id.clone(),
        response_id: created.response.id.clone(),
        idempotency_key: format!("test-cancel-{suffix}"),
        request_sha256: format!("sha256:{}", "b".repeat(64)),
        actor: "integration-test".to_string(),
        policy_version: "test-v1".to_string(),
        authority_epoch: 1,
        occurred_at: occurred_at + Duration::seconds(1),
    };
    let cancelled = repository
        .cancel_response(&cancel_command)
        .await
        .expect("cancel response")
        .expect("owned response");
    assert!(cancelled.changed);
    assert_eq!(cancelled.response.status, "cancelled");
    assert_eq!(
        cancelled.event.as_ref().map(|event| event.sequence),
        Some(2)
    );

    let cancel_replay = repository
        .cancel_response(&cancel_command)
        .await
        .expect("replay cancellation")
        .expect("owned response");
    assert!(!cancel_replay.changed);
    assert_eq!(cancel_replay.response.status, "cancelled");

    let all_events = repository
        .list_response_events(&principal_id, &created.response.id, 0, 100)
        .await
        .expect("list response events")
        .expect("owned response");
    assert_eq!(all_events.len(), 2);
    assert_eq!(all_events[1].event_type, "response.cancelled");

    let raw_credential_total: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM kolibri.public_sessions WHERE credential_sha256 = $1",
    )
    .bind(&issued.credential)
    .fetch_one(&pool)
    .await
    .expect("check that raw credential is not stored");
    assert_eq!(raw_credential_total, 0);

    let response_total: i64 =
        sqlx::query_scalar("SELECT COUNT(*) FROM kolibri.responses WHERE principal_id = $1")
            .bind(&principal_id)
            .fetch_one(&pool)
            .await
            .expect("count responses");
    let message_total: i64 =
        sqlx::query_scalar("SELECT COUNT(*) FROM kolibri.messages WHERE principal_id = $1")
            .bind(&principal_id)
            .fetch_one(&pool)
            .await
            .expect("count messages");
    let event_total: i64 =
        sqlx::query_scalar("SELECT COUNT(*) FROM kolibri.events WHERE data->>'response_id' = $1")
            .bind(&created.response.id)
            .fetch_one(&pool)
            .await
            .expect("count events");
    let outbox_total: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM kolibri.outbox WHERE payload->'data'->>'response_id' = $1",
    )
    .bind(&created.response.id)
    .fetch_one(&pool)
    .await
    .expect("count outbox records");
    assert_eq!(response_total, 1);
    assert_eq!(message_total, 2);
    assert_eq!(event_total, 2);
    assert_eq!(outbox_total, 2);

    sqlx::query("DELETE FROM kolibri.outbox WHERE payload->'data'->>'response_id' = $1")
        .bind(&created.response.id)
        .execute(&pool)
        .await
        .expect("clean outbox fixture");
    sqlx::query("DELETE FROM kolibri.events WHERE data->>'response_id' = $1")
        .bind(&created.response.id)
        .execute(&pool)
        .await
        .expect("clean event fixture");
    sqlx::query("DELETE FROM kolibri.idempotency_records WHERE principal_id = $1")
        .bind(&principal_id)
        .execute(&pool)
        .await
        .expect("clean idempotency fixture");
    sqlx::query("DELETE FROM kolibri.responses WHERE principal_id = $1")
        .bind(&principal_id)
        .execute(&pool)
        .await
        .expect("clean response fixture");
    sqlx::query("DELETE FROM kolibri.event_stream_heads WHERE subject = $1")
        .bind(&created.event.subject)
        .execute(&pool)
        .await
        .expect("clean stream head fixture");
    sqlx::query("DELETE FROM kolibri.public_sessions WHERE id = $1")
        .bind(&issued.session.id)
        .execute(&pool)
        .await
        .expect("clean public session fixture");
}
