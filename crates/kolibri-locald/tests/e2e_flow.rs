use std::{
    process::{Child, Command, Stdio},
    time::Duration,
};

use reqwest::{Client, StatusCode};
use serde_json::{json, Value};
use tempfile::TempDir;
use tokio::time::sleep;

struct LocaldProcess {
    child: Child,
    _dir: TempDir,
}

impl Drop for LocaldProcess {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

async fn spawn_locald(port: u16) -> (LocaldProcess, String) {
    let dir = tempfile::tempdir().expect("tempdir");
    let config_path = dir.path().join("locald.toml");
    let data_dir = dir.path().join("data");
    std::fs::write(
        &config_path,
        format!(
            r#"
bind_host = "127.0.0.1"
bind_port = {port}
node_id = "node-locald-01"
node_role = "local-control"
local_endpoint = "127.0.0.1:{port}"
data_dir = "{}"
terminal_timeout_seconds = 3
terminal_max_output_bytes = 4096
lease_stale_seconds = 30
allowed_terminal_commands = ["status", "tasks", "pwd"]
terminal_requires_approval = true
terminal_default_user = "tester"
"#,
            data_dir.display()
        ),
    )
    .expect("write config");

    let binary = env!("CARGO_BIN_EXE_kolibri-locald");
    let child = Command::new(binary)
        .arg("--config")
        .arg(config_path)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .expect("spawn locald");

    let base_url = format!("http://127.0.0.1:{port}");
    let client = Client::new();
    for _ in 0..50 {
        if let Ok(response) = client.get(format!("{base_url}/health")).send().await {
            if response.status().is_success() {
                return (LocaldProcess { child, _dir: dir }, base_url);
            }
        }
        sleep(Duration::from_millis(100)).await;
    }
    panic!("locald did not become healthy");
}

#[tokio::test]
async fn locald_runs_foundation_task_flow_and_keeps_terminal_gated() {
    let (_process, base_url) = spawn_locald(39101).await;
    let client = Client::new();

    let health: Value = client
        .get(format!("{base_url}/health"))
        .send()
        .await
        .expect("health request")
        .json()
        .await
        .expect("health json");
    assert_eq!(health["status"], "ok");

    let enroll = client
        .post(format!("{base_url}/v1/agents/enroll"))
        .json(&json!({
            "id": "agent-demo-01",
            "node_id": "node-locald-01",
            "name": "demo-agent",
            "kind": "vps",
            "version": "0.1.0-test",
            "capabilities": ["demo.safe"]
        }))
        .send()
        .await
        .expect("enroll request");
    assert_eq!(enroll.status(), StatusCode::CREATED);

    let heartbeat = client
        .post(format!("{base_url}/v1/agents/heartbeat"))
        .json(&json!({
            "id": "agent-demo-01",
            "node_id": "node-locald-01",
            "status": "online",
            "capabilities": ["demo.safe"]
        }))
        .send()
        .await
        .expect("heartbeat request");
    assert!(heartbeat.status().is_success());

    let submitted: Value = client
        .post(format!("{base_url}/v1/tasks"))
        .header("x-trace-id", "trace-e2e-locald")
        .json(&json!({
            "owner": "qa",
            "kind": "demo.safe",
            "payload": {"command": "status"},
            "sensitivity": "public",
            "required_capability": "demo.safe"
        }))
        .send()
        .await
        .expect("submit request")
        .json()
        .await
        .expect("submit json");
    assert_eq!(submitted["status"], "scheduled");
    let task_id = submitted["task_id"].as_str().expect("task id");

    let leased: Value = client
        .post(format!("{base_url}/v1/tasks/lease"))
        .json(&json!({
            "agent_id": "agent-demo-01",
            "required_capability": "demo.safe"
        }))
        .send()
        .await
        .expect("lease request")
        .json()
        .await
        .expect("lease json");
    assert_eq!(leased["status"], "running");
    assert_eq!(leased["task"]["worker_id"], "agent-demo-01");

    let completed: Value = client
        .post(format!("{base_url}/v1/tasks/{task_id}/complete"))
        .json(&json!({
            "message": "demo task completed through sandbox mock",
            "output": {"stdout": "ok"},
            "artifact_ids": ["artifact-sha256-demo"]
        }))
        .send()
        .await
        .expect("complete request")
        .json()
        .await
        .expect("complete json");
    assert_eq!(completed["status"], "audited");

    let artifacts: Value = client
        .get(format!("{base_url}/v1/tasks/{task_id}/artifacts"))
        .send()
        .await
        .expect("artifacts request")
        .json()
        .await
        .expect("artifacts json");
    assert_eq!(artifacts["artifacts"][0], "artifact-sha256-demo");

    let terminal_denied = client
        .post(format!("{base_url}/v1/terminal/sessions"))
        .json(&json!({
            "actor": "qa"
        }))
        .send()
        .await
        .expect("terminal request");
    assert_eq!(terminal_denied.status(), StatusCode::FORBIDDEN);
}
