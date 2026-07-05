use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Serialize, Deserialize)]
struct ModelRequest {
    task_id: String,
    provider: String,
    prompt: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct ModelResponse {
    task_id: String,
    run_id: String,
    provider: String,
    answer: String,
}

#[async_trait]
trait ModelProvider {
    async fn complete(&self, request: &ModelRequest) -> Result<String, String>;
}

struct MockModelProvider;

#[async_trait]
impl ModelProvider for MockModelProvider {
    async fn complete(&self, request: &ModelRequest) -> Result<String, String> {
        Ok(format!(
            "mock-response-for:{}:{}",
            request.provider, request.prompt
        ))
    }
}

#[tokio::main]
async fn main() {
    let provider = MockModelProvider;
    let request = ModelRequest {
        task_id: Uuid::new_v4().to_string(),
        provider: "mock".into(),
        prompt: "Колибри foundation".into(),
    };
    let answer = provider
        .complete(&request)
        .await
        .unwrap_or_else(|error| format!("error:{error}"));
    let response = ModelResponse {
        task_id: request.task_id,
        run_id: Uuid::new_v4().to_string(),
        provider: request.provider,
        answer,
    };
    println!("{}", serde_json::to_string_pretty(&response).unwrap());
}
