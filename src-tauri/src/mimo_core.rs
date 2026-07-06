use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
pub struct ChatRequest {
    pub server: String,
    pub prompt: String,
}

#[derive(Serialize, Deserialize)]
pub struct ChatResponse {
    pub content: String,
    pub server: String,
}

const MIMO_CLIENTS: &[(&str, &str)] = &[
    ("9fts", "http://10.99.0.5:8001"),
    ("uiap", "http://10.99.0.3:8002"),
    ("qjns", "http://10.99.0.4:8003"),
];

#[tauri::command]
pub async fn chat(server: String, prompt: String) -> Result<ChatResponse, String> {
    let url = MIMO_CLIENTS.iter()
        .find(|(name, _)| *name == server)
        .map(|(_, url)| *url)
        .unwrap_or("http://10.99.0.5:8001");

    let body = serde_json::json!({
        "model": "mimo",
        "messages": [{"role": "user", "content": prompt}]
    });

    let resp = reqwest::Client::new()
        .post(format!("{}/v1/chat/completions", url))
        .json(&body)
        .send()
        .await
        .map_err(|e| e.to_string())?;

    let data: serde_json::Value = resp.json().await.map_err(|e| e.to_string())?;
    let content = data["choices"][0]["message"]["content"]
        .as_str()
        .unwrap_or("No response")
        .to_string();

    Ok(ChatResponse { content, server })
}
