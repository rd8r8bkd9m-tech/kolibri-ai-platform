use axum::{
    extract::Path,
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::net::SocketAddr;
use tokio::net::TcpListener;

#[derive(Debug, Serialize, Deserialize)]
struct Health {
    status: &'static str,
    service: &'static str,
}

#[derive(Debug, Serialize, Deserialize)]
struct Item {
    id: &'static str,
}

#[derive(Debug, Serialize, Deserialize)]
struct IdParam {
    id: String,
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();
    let app = Router::new()
        .route("/health", get(health))
        .route("/v1/nodes", get(list_nodes).post(create_node))
        .route("/v1/agents", get(list_agents).post(enroll_agent))
        .route("/v1/tasks", get(list_tasks).post(create_task))
        .route("/v1/tasks/:id/assign", post(assign_task))
        .route("/v1/tasks/:id/cancel", post(cancel_task))
        .route("/v1/events", get(list_events));

    let addr: SocketAddr = "127.0.0.1:8080".parse().unwrap();
    tracing::info!("control-plane listening on {addr}");
    let listener = TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}

async fn health() -> impl IntoResponse {
    (
        StatusCode::OK,
        Json(Health {
            status: "ok",
            service: "control-plane",
        }),
    )
}

async fn list_nodes() -> impl IntoResponse {
    Json(json!({"nodes": []}))
}

async fn create_node() -> impl IntoResponse {
    (
        StatusCode::CREATED,
        Json(Item {
            id: "node-placeholder",
        }),
    )
}

async fn list_agents() -> impl IntoResponse {
    Json(json!({"agents": []}))
}

async fn enroll_agent() -> impl IntoResponse {
    (
        StatusCode::CREATED,
        Json(json!({"agent_id":"agent-placeholder","status":"enrolled"})),
    )
}

async fn list_tasks() -> impl IntoResponse {
    Json(json!({"tasks": []}))
}

async fn create_task() -> impl IntoResponse {
    (
        StatusCode::CREATED,
        Json(Item {
            id: "task-placeholder",
        }),
    )
}

async fn assign_task(Path(IdParam { id }): Path<IdParam>) -> impl IntoResponse {
    Json(json!({"task_id":id,"assigned_to":"agent-placeholder","status":"assigned"}))
}

async fn cancel_task(Path(IdParam { id }): Path<IdParam>) -> impl IntoResponse {
    Json(json!({"task_id":id,"status":"cancelled"}))
}

async fn list_events() -> impl IntoResponse {
    Json(json!({"events": []}))
}
