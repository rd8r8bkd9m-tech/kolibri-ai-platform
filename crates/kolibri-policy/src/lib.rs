use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum PolicyDecision {
    Allow,
    Deny,
    RequireHumanApproval,
    RequireStrongerSandbox,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyInput {
    pub actor: String,
    pub action: String,
    pub resource: String,
    pub command: Option<String>,
    pub is_sensitive: bool,
    pub environment: serde_json::Value,
    pub allow_hosts: Vec<String>,
    pub requested_capabilities: Vec<String>,
    pub is_root_request: bool,
    pub requested_shell: bool,
    pub pty_requested: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PolicyAuditEvent {
    pub task_id: Option<Uuid>,
    pub actor: String,
    pub action: String,
    pub decision: PolicyDecision,
    pub reason: String,
    pub trace_id: String,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, thiserror::Error)]
pub enum PolicyError {
    #[error("policy denied action: {0}")]
    Denied(String),
    #[error("policy requires human approval: {0}")]
    NeedApproval(String),
}

#[derive(Debug, Default)]
pub struct PolicyRequestContext {
    pub allowed_hosts: HashSet<String>,
    pub disallow_shell_by_default: bool,
}

pub fn evaluate_policy(input: &PolicyInput) -> Result<PolicyDecision, PolicyError> {
    if input.resource.starts_with("model.") && input.is_sensitive {
        return Err(PolicyError::NeedApproval(
            "Sensitive model tasks require explicit approval".into(),
        ));
    }
    if input.is_root_request {
        return Err(PolicyError::Denied("root execution is forbidden".into()));
    }
    if input.requested_shell && input.requested_command_is_forbidden() {
        return Err(PolicyError::Denied(
            "requested shell command is unsafe".into(),
        ));
    }
    if input.requested_shell && input.allow_hosts.is_empty() {
        return Err(PolicyError::NeedApproval(
            "shell execution requires approved host allowlist".into(),
        ));
    }
    if input.pty_requested {
        return Err(PolicyError::NeedApproval(
            "PTY session requires approval in MVP".into(),
        ));
    }
    if input.is_sensitive
        && !input
            .requested_capabilities
            .iter()
            .any(|c| c == "sensitive_ok")
    {
        return Err(PolicyError::NeedApproval(
            "sensitive task requires approval".into(),
        ));
    }
    if input.disallow_shell_policy_active() {
        return Err(PolicyError::Denied(
            "shell execution blocked by default policy".into(),
        ));
    }
    Ok(PolicyDecision::Allow)
}

impl PolicyInput {
    fn disallow_shell_policy_active(&self) -> bool {
        self.requested_shell && self.disallow_shell_by_default()
    }

    fn disallow_shell_by_default(&self) -> bool {
        self.requested_shell && self.action == "shell.execute" && self.command.is_none()
    }

    pub fn to_audit_event(
        &self,
        decision: PolicyDecision,
        reason: impl Into<String>,
    ) -> PolicyAuditEvent {
        PolicyAuditEvent {
            task_id: None,
            actor: self.actor.clone(),
            action: self.action.clone(),
            decision,
            reason: reason.into(),
            trace_id: self
                .environment
                .get("trace_id")
                .and_then(|value| value.as_str())
                .unwrap_or("")
                .to_string(),
            created_at: Utc::now(),
        }
    }

    fn requested_command_is_forbidden(&self) -> bool {
        self.command
            .as_deref()
            .map(|cmd| {
                let lowered = cmd.to_lowercase();
                lowered.contains("rm -rf /")
                    || lowered.contains("sudo")
                    || lowered.contains("dd if=")
                    || lowered.contains("> /etc")
            })
            .unwrap_or(false)
    }
}

pub fn to_audit_json(event: &PolicyAuditEvent) -> serde_json::Value {
    serde_json::to_value(event).expect("policy audit event must serialize")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unsafe_command_is_denied() {
        let input = PolicyInput {
            actor: "agent-1".into(),
            action: "shell.execute".into(),
            resource: "task.001".into(),
            command: Some("rm -rf /".into()),
            is_sensitive: false,
            environment: serde_json::json!({}),
            allow_hosts: vec![],
            requested_capabilities: vec![],
            is_root_request: false,
            requested_shell: true,
            pty_requested: false,
        };
        let decision = evaluate_policy(&input);
        assert!(matches!(decision, Err(PolicyError::Denied(_))));
    }

    #[test]
    fn production_like_action_requires_approval() {
        let input = PolicyInput {
            actor: "owner".into(),
            action: "deploy.production".into(),
            resource: "task.001".into(),
            command: Some("systemctl restart app".into()),
            is_sensitive: true,
            environment: serde_json::json!({"trace_id":"t-1"}),
            allow_hosts: vec!["internal.kolibri.local".into()],
            requested_capabilities: vec![],
            is_root_request: false,
            requested_shell: false,
            pty_requested: false,
        };
        let decision = evaluate_policy(&input);
        assert!(matches!(decision, Err(PolicyError::NeedApproval(_))));
        if let Err(PolicyError::NeedApproval(reason)) = decision {
            let event = input.to_audit_event(PolicyDecision::RequireHumanApproval, reason);
            assert_eq!(event.action, "deploy.production");
            assert!(!event.reason.is_empty());
        } else {
            panic!("expected approval")
        }
    }

    #[test]
    fn allow_safe_command_with_host_and_capability() {
        let input = PolicyInput {
            actor: "agent-1".into(),
            action: "terminal.command".into(),
            resource: "task.demo".into(),
            command: Some("echo hello".into()),
            is_sensitive: false,
            environment: serde_json::json!({"trace_id":"t-2"}),
            allow_hosts: vec!["internal.kolibri.local".into()],
            requested_capabilities: vec!["safe_shell".into()],
            is_root_request: false,
            requested_shell: true,
            pty_requested: false,
        };
        let decision = evaluate_policy(&input);
        assert!(decision.is_ok());
        assert!(matches!(decision.unwrap(), PolicyDecision::Allow));
    }
}
