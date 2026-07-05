use async_trait::async_trait;
use kolibri_core::events::EventEnvelope;
use kolibri_core::models::{SecretRef, SecretValue};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum SecretsError {
    #[error("secret not found for provider={provider} path={path}")]
    NotFound { provider: String, path: String },
    #[error("provider not configured: {0}")]
    ProviderUnavailable(String),
    #[error("env secret missing: {0}")]
    EnvMissing(String),
}

#[async_trait]
pub trait SecretProvider: Send + Sync {
    async fn resolve(&self, secret: &SecretRef) -> Result<SecretValue, SecretsError>;
}

pub struct EnvSecretProvider;

#[async_trait]
impl SecretProvider for EnvSecretProvider {
    async fn resolve(&self, secret: &SecretRef) -> Result<SecretValue, SecretsError> {
        let var_name = secret
            .path
            .replace("secrets/", "")
            .replace('/', "_")
            .to_uppercase();
        match std::env::var(&var_name) {
            Ok(value) => Ok(SecretValue::new(value)),
            Err(_) => Err(SecretsError::EnvMissing(var_name)),
        }
    }
}

pub fn make_requested_event(task_id: Option<&str>, secret: &SecretRef) -> EventEnvelope {
    EventEnvelope {
        id: uuid::Uuid::new_v4(),
        stream: "kolibri.secret".into(),
        subject: "secret.requested".into(),
        event_type: "secret.requested".into(),
        aggregate_id: None,
        payload_json: serde_json::json!({
            "task_id": task_id,
            "provider": secret.provider,
            "path": secret.path,
            "scope": secret.scope,
        }),
        trace_id: None,
        correlation_id: None,
        actor: Some("policy-engine".into()),
        created_at: chrono::Utc::now(),
    }
}

pub fn make_granted_event(task_id: Option<&str>, secret: &SecretRef) -> EventEnvelope {
    EventEnvelope {
        id: uuid::Uuid::new_v4(),
        stream: "kolibri.secret".into(),
        subject: "secret.granted".into(),
        event_type: "secret.granted".into(),
        aggregate_id: None,
        payload_json: serde_json::json!({
            "task_id": task_id,
            "provider": secret.provider,
            "path": secret.path,
            "scope": secret.scope,
        }),
        trace_id: None,
        correlation_id: None,
        actor: Some("policy-engine".into()),
        created_at: chrono::Utc::now(),
    }
}

pub fn make_denied_event(task_id: Option<&str>, secret: &SecretRef, reason: &str) -> EventEnvelope {
    EventEnvelope {
        id: uuid::Uuid::new_v4(),
        stream: "kolibri.secret".into(),
        subject: "secret.denied".into(),
        event_type: "secret.denied".into(),
        aggregate_id: None,
        payload_json: serde_json::json!({
            "task_id": task_id,
            "provider": secret.provider,
            "path": secret.path,
            "scope": secret.scope,
            "reason": reason,
        }),
        trace_id: None,
        correlation_id: None,
        actor: Some("policy-engine".into()),
        created_at: chrono::Utc::now(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn secret_debug_does_not_expose_value() {
        let value = SecretValue::new("top-secret");
        assert!(format!("{:?}", value).contains("***"));
        assert_eq!(format!("{}", value), "***");
        assert_eq!(value.expose(), "top-secret");
    }

    #[tokio::test]
    async fn env_secret_provider_reads_variable() {
        std::env::set_var("TEST_SECRET", "alpha");
        let ref_ = SecretRef {
            provider: "env".into(),
            path: "TEST_SECRET".into(),
            version: None,
            scope: "local".into(),
        };
        let value = EnvSecretProvider.resolve(&ref_).await.unwrap();
        assert_eq!(value.expose(), "alpha");
    }

    #[test]
    fn secret_events_do_not_contain_raw_values() {
        let ref_ = SecretRef {
            provider: "vault".into(),
            path: "projects/alpha/db".into(),
            version: None,
            scope: "prod".into(),
        };
        let event = make_requested_event(Some("task-1"), &ref_);
        let raw = serde_json::to_string(&event).unwrap();
        assert!(!raw.contains("top-secret"));
        assert!(raw.contains("projects/alpha/db"));
    }
}
