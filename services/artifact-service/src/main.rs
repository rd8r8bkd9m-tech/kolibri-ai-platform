use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::post,
    Json, Router,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::net::SocketAddr;

#[derive(Debug, Serialize, Deserialize)]
struct ArtifactRequest {
    task_run_id: String,
    artifact_type: String,
    name: String,
    data: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct ArtifactResponse {
    accepted: bool,
    sha256: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct ArtifactErrorResponse {
    accepted: bool,
    error: String,
}

#[tokio::main]
async fn main() {
    let app = Router::new().route("/v1/artifacts", post(register_artifact));
    let addr: SocketAddr = "127.0.0.1:8090".parse().unwrap();
    tracing_subscriber::fmt::init();
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}

async fn register_artifact(Json(payload): Json<ArtifactRequest>) -> Response {
    if let Err(error) = validate_artifact(&payload) {
        return (
            StatusCode::BAD_REQUEST,
            Json(ArtifactErrorResponse {
                accepted: false,
                error,
            }),
        )
            .into_response();
    }

    (
        StatusCode::CREATED,
        Json(ArtifactResponse {
            accepted: true,
            sha256: sha256_label(&payload.data),
        }),
    )
        .into_response()
}

fn validate_artifact(payload: &ArtifactRequest) -> Result<(), String> {
    if payload.task_run_id.trim().is_empty() {
        return Err("task_run_id is required".to_string());
    }
    if payload.artifact_type.trim().is_empty() {
        return Err("artifact_type is required".to_string());
    }
    if payload.name.trim().is_empty() {
        return Err("name is required".to_string());
    }
    Ok(())
}

fn sha256_label(data: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data.as_bytes());
    let digest = hasher.finalize();
    format!("sha256:{digest:x}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hashes_artifact_payload_with_sha256() {
        assert_eq!(
            sha256_label(""),
            "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
        assert_ne!(sha256_label("ok"), "sha256:2");
    }

    #[test]
    fn rejects_artifacts_without_task_run_id() {
        let payload = ArtifactRequest {
            task_run_id: " ".to_string(),
            artifact_type: "test_report".to_string(),
            name: "report.json".to_string(),
            data: "{}".to_string(),
        };

        assert_eq!(
            validate_artifact(&payload),
            Err("task_run_id is required".to_string())
        );
    }
}
