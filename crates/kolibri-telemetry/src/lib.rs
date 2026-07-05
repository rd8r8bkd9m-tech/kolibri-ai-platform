use std::collections::HashMap;

use tracing::Span;

pub const REQUIRED_SPAN_NAMES: [&str; 10] = [
    "kolibri.locald.request",
    "kolibri.agent.heartbeat",
    "kolibri.agent.task.execute",
    "kolibri.scheduler.assign",
    "kolibri.control_plane.task.create",
    "kolibri.sandbox.execute",
    "kolibri.policy.evaluate",
    "kolibri.secret.resolve",
    "kolibri.model.request",
    "kolibri.artifact.upload",
];

#[derive(Clone, Debug)]
pub struct TelemetryContext {
    pub trace_id: String,
    pub span_id: String,
}

pub fn required_fields() -> Vec<&'static str> {
    vec![
        "trace_id",
        "span_id",
        "task_id",
        "task_run_id",
        "agent_id",
        "node_id",
        "actor",
        "event_type",
        "policy_decision",
        "sandbox_profile",
        "model_provider",
    ]
}

pub fn init(service: &str, json: bool) {
    let env_filter = std::env::var("RUST_LOG").unwrap_or_else(|_| format!("{}=info", service));
    let filter = tracing_subscriber::EnvFilter::new(env_filter);

    if json {
        tracing_subscriber::fmt()
            .json()
            .with_env_filter(filter)
            .init();
    } else {
        tracing_subscriber::fmt()
            .with_env_filter(filter)
            .compact()
            .init();
    }
}

pub fn telemetry_span(name: &str, fields: &[(&str, String)]) -> Span {
    let span = tracing::span!(tracing::Level::INFO, "kolibri.operation", operation = %name);
    for (key, value) in fields {
        let value = value.as_str();
        span.record(*key, value);
    }
    span
}

pub fn attach_common_labels(
    task_id: Option<&str>,
    task_run_id: Option<&str>,
    agent_id: Option<&str>,
    node_id: Option<&str>,
    actor: Option<&str>,
) -> HashMap<String, String> {
    let mut labels = HashMap::new();
    if let Some(id) = task_id {
        labels.insert("task_id".into(), id.to_string());
    }
    if let Some(id) = task_run_id {
        labels.insert("task_run_id".into(), id.to_string());
    }
    if let Some(id) = agent_id {
        labels.insert("agent_id".into(), id.to_string());
    }
    if let Some(id) = node_id {
        labels.insert("node_id".into(), id.to_string());
    }
    if let Some(id) = actor {
        labels.insert("actor".into(), id.to_string());
    }
    labels
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn telemetry_lists_required_fields() {
        let fields = required_fields();
        assert!(fields.iter().any(|f| *f == "trace_id"));
        assert!(fields.iter().any(|f| *f == "task_run_id"));
    }

    #[test]
    fn attach_common_labels_builds_map() {
        let map = attach_common_labels(
            Some("task-1"),
            Some("run-1"),
            Some("agent-1"),
            None,
            Some("owner"),
        );
        assert_eq!(map.get("task_id"), Some(&"task-1".to_string()));
        assert_eq!(map.get("task_run_id"), Some(&"run-1".to_string()));
        assert_eq!(map.get("actor"), Some(&"owner".to_string()));
    }
}
