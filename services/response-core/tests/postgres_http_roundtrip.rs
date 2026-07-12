use axum::{
    Router,
    body::Body,
    http::{Request, StatusCode},
};
use http_body_util::BodyExt;
use kolibri_core::canonical_json_sha256;
use kolibri_response_core::{CoreSettings, build_router};
use kolibri_store_postgres::PostgresResponseRepository;
use serde_json::{Value, json};
use sqlx::postgres::PgPoolOptions;
use tower::ServiceExt;

fn test_database_url() -> Option<String> {
    let value = std::env::var("TEST_DATABASE_URL").ok()?;
    assert!(
        value.to_ascii_lowercase().contains("test"),
        "refusing to run PostgreSQL roundtrip against a URL without 'test'"
    );
    Some(value)
}

fn edge_request_hash(method: &str, path: &str, body: &Value) -> String {
    canonical_json_sha256(&json!({
        "method": method,
        "path": path,
        "body": body,
    }))
    .expect("canonical edge request hash")
    .trim_start_matches("sha256:")
    .to_string()
}

async fn post_json(router: &Router, path: &str, body: Value) -> (StatusCode, Value) {
    let response = router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri(path)
                .header("content-type", "application/json")
                .body(Body::from(body.to_string()))
                .expect("request"),
        )
        .await
        .expect("response");
    let status = response.status();
    let bytes = response
        .into_body()
        .collect()
        .await
        .expect("response body")
        .to_bytes();
    let value = serde_json::from_slice(&bytes).expect("JSON response");
    (status, value)
}

#[tokio::test]
#[ignore = "set TEST_DATABASE_URL to an isolated PostgreSQL test database"]
#[allow(clippy::too_many_lines)]
async fn core_client_rpc_roundtrip_is_durable_and_session_scoped() {
    let Some(database_url) = test_database_url() else {
        return;
    };
    let pool = PgPoolOptions::new()
        .max_connections(8)
        .connect(&database_url)
        .await
        .expect("connect to isolated test database");
    let repository = PostgresResponseRepository::new(pool.clone());
    repository.migrate().await.expect("run embedded migrations");
    let router = build_router(pool.clone(), CoreSettings::default()).expect("build router");

    let (status, issue) = post_json(
        &router,
        "/internal/v1/public-sessions",
        json!({"origin":"https://kolibriai.ru"}),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    let credential = issue["credential"]
        .as_str()
        .expect("issued credential")
        .to_string();
    let session_id = issue["session"]["id"]
        .as_str()
        .expect("session id")
        .to_string();
    let project_id = issue["session"]["current_project_id"]
        .as_str()
        .expect("project id")
        .to_string();
    let principal = json!({
        "session_id": session_id,
        "origin": "https://kolibriai.ru",
    });

    let (status, resolved) = post_json(
        &router,
        "/internal/v1/public-sessions/resolve",
        json!({"credential":credential}),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(resolved["id"], issue["session"]["id"]);

    let public_request = json!({
        "model": "kolibri",
        "input": "Привет",
        "project_id": project_id,
        "stream": false,
    });
    let create_hash = edge_request_hash("POST", "/v1/responses", &public_request);
    let create_rpc = json!({
        "principal": principal,
        "request": public_request,
        "idempotency_key": "roundtrip-create-0001",
        "request_sha256": create_hash,
    });
    let (status, created) = post_json(&router, "/internal/v1/responses", create_rpc.clone()).await;
    assert_eq!(status, StatusCode::CREATED);
    assert_eq!(created["model"], "kolibri");
    assert_eq!(created["status"], "queued");
    let response_id = created["id"].as_str().expect("response id").to_string();

    let (status, replayed) = post_json(&router, "/internal/v1/responses", create_rpc).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(replayed["id"], response_id);

    let lookup_rpc = json!({
        "principal": principal,
        "response_id": response_id,
    });
    let (status, fetched) =
        post_json(&router, "/internal/v1/responses/get", lookup_rpc.clone()).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(fetched["id"], response_id);

    let (status, events) = post_json(
        &router,
        "/internal/v1/responses/events",
        json!({
            "principal": principal,
            "response_id": response_id,
            "after": 0,
            "limit": 100,
            "wait_seconds": 0,
        }),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(events["data"].as_array().map(Vec::len), Some(1));
    assert_eq!(events["data"][0]["event_type"], "response.created");

    let cancel_path = format!("/v1/responses/{response_id}/cancel");
    let cancel_hash = edge_request_hash("POST", &cancel_path, &json!({}));
    let cancel_rpc = json!({
        "principal": principal,
        "response_id": response_id,
        "idempotency_key": "roundtrip-cancel-0001",
        "request_sha256": cancel_hash,
    });
    let (status, cancelled) =
        post_json(&router, "/internal/v1/responses/cancel", cancel_rpc.clone()).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(cancelled["status"], "cancelled");
    let (status, cancel_replay) =
        post_json(&router, "/internal/v1/responses/cancel", cancel_rpc).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(cancel_replay["status"], "cancelled");

    let raw_credential_total: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM kolibri.public_sessions WHERE credential_sha256 = $1",
    )
    .bind(&credential)
    .fetch_one(&pool)
    .await
    .expect("raw credential lookup");
    assert_eq!(raw_credential_total, 0);

    sqlx::query("DELETE FROM kolibri.outbox WHERE payload->'data'->>'response_id' = $1")
        .bind(&response_id)
        .execute(&pool)
        .await
        .expect("clean outbox");
    sqlx::query("DELETE FROM kolibri.events WHERE data->>'response_id' = $1")
        .bind(&response_id)
        .execute(&pool)
        .await
        .expect("clean events");
    sqlx::query("DELETE FROM kolibri.idempotency_records WHERE resource_id = $1")
        .bind(&response_id)
        .execute(&pool)
        .await
        .expect("clean idempotency records");
    sqlx::query("DELETE FROM kolibri.responses WHERE id = $1")
        .bind(&response_id)
        .execute(&pool)
        .await
        .expect("clean response");
    sqlx::query("DELETE FROM kolibri.event_stream_heads WHERE subject = $1")
        .bind(format!("response/{response_id}"))
        .execute(&pool)
        .await
        .expect("clean event head");
    sqlx::query("DELETE FROM kolibri.public_sessions WHERE id = $1")
        .bind(&session_id)
        .execute(&pool)
        .await
        .expect("clean public session");
}
