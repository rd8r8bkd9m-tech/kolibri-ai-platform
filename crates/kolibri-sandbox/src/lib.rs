use async_trait::async_trait;
use std::{collections::HashSet, time::Duration};
use thiserror::Error;

use kolibri_core::models::CommandRun;
use tokio::process::Command;
use uuid::Uuid;

#[derive(Debug, Clone)]
pub struct SandboxSpec {
    pub task_id: Uuid,
    pub agent_id: Uuid,
    pub node_id: Uuid,
    pub allowlisted_commands: Vec<String>,
    pub allow_network: bool,
    pub allow_secrets: bool,
    pub allow_root: bool,
    pub max_duration_ms: u64,
}

#[derive(Debug, Clone)]
pub struct SandboxHandle {
    pub id: Uuid,
    pub task_id: Uuid,
    pub agent_id: Uuid,
    pub node_id: Uuid,
}

#[derive(Debug, Clone)]
pub struct CommandSpec {
    pub command: String,
    pub args: Vec<String>,
    pub cwd: Option<String>,
    pub timeout_ms: u64,
    pub allow_network: bool,
}

#[derive(Debug, Clone)]
pub struct CommandResult {
    pub exit_code: i32,
    pub stdout: String,
    pub stderr: String,
}

#[async_trait]
pub trait SandboxBackend: Send + Sync {
    async fn prepare(&self, spec: &SandboxSpec) -> Result<SandboxHandle, SandboxError>;
    async fn execute(
        &self,
        handle: &SandboxHandle,
        command: &CommandSpec,
    ) -> Result<CommandResult, SandboxError>;
    async fn destroy(&self, handle: SandboxHandle) -> Result<(), SandboxError>;
}

#[derive(Debug, Error)]
pub enum SandboxError {
    #[error("policy denied command: {0}")]
    Denied(String),
    #[error("execution failed: {0}")]
    ExecFailed(String),
    #[error("timeout")]
    Timeout,
}

pub struct MockSandboxBackend;

#[async_trait]
impl SandboxBackend for MockSandboxBackend {
    async fn prepare(&self, spec: &SandboxSpec) -> Result<SandboxHandle, SandboxError> {
        Ok(SandboxHandle {
            id: Uuid::new_v4(),
            task_id: spec.task_id,
            agent_id: spec.agent_id,
            node_id: spec.node_id,
        })
    }

    async fn execute(
        &self,
        handle: &SandboxHandle,
        command: &CommandSpec,
    ) -> Result<CommandResult, SandboxError> {
        let command_echo = format!(
            "mock:{}:{}:{}",
            handle.id,
            command.command,
            command.args.join(" ")
        );
        Ok(CommandResult {
            exit_code: 0,
            stdout: command_echo,
            stderr: String::new(),
        })
    }

    async fn destroy(&self, _handle: SandboxHandle) -> Result<(), SandboxError> {
        Ok(())
    }
}

pub struct LocalProcessSandboxBackend {
    pub default_timeout_ms: u64,
    pub command_allowlist: HashSet<String>,
    pub network_enabled: bool,
    pub secrets_enabled: bool,
}

impl Default for LocalProcessSandboxBackend {
    fn default() -> Self {
        Self {
            default_timeout_ms: 8_000,
            command_allowlist: ["echo", "ls", "pwd", "true", "uname"]
                .into_iter()
                .map(ToString::to_string)
                .collect(),
            network_enabled: false,
            secrets_enabled: false,
        }
    }
}

#[async_trait]
impl SandboxBackend for LocalProcessSandboxBackend {
    async fn prepare(&self, spec: &SandboxSpec) -> Result<SandboxHandle, SandboxError> {
        if !self.network_enabled && spec.allow_network {
            return Err(SandboxError::Denied("network is disabled".into()));
        }
        if !self.secrets_enabled && !spec.allow_secrets {
            // secrets are off by default to keep v1 safe
        }
        if spec.allow_root {
            return Err(SandboxError::Denied("root execution denied".into()));
        }
        Ok(SandboxHandle {
            id: Uuid::new_v4(),
            task_id: spec.task_id,
            agent_id: spec.agent_id,
            node_id: spec.node_id,
        })
    }

    async fn execute(
        &self,
        _handle: &SandboxHandle,
        command: &CommandSpec,
    ) -> Result<CommandResult, SandboxError> {
        if !self.command_allowlist.contains(&command.command) {
            return Err(SandboxError::Denied("command not allowlisted".into()));
        }
        if command.allow_network && !self.network_enabled {
            return Err(SandboxError::Denied("network denied".into()));
        }
        let timeout = Duration::from_millis(command.timeout_ms.max(1));
        let mut child = Command::new(&command.command);
        if !command.args.is_empty() {
            child.args(&command.args);
        }
        if let Some(cwd) = &command.cwd {
            child.current_dir(cwd);
        }
        let child = child
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()
            .map_err(|err| SandboxError::ExecFailed(err.to_string()))?;
        let output = tokio::time::timeout(timeout, child.wait_with_output())
            .await
            .map_err(|_| SandboxError::Timeout)?
            .map_err(|err| SandboxError::ExecFailed(err.to_string()))?;
        let _ = output.status.code().unwrap_or(0);
        Ok(CommandResult {
            exit_code: output.status.code().unwrap_or(-1),
            stdout: String::from_utf8_lossy(&output.stdout).to_string(),
            stderr: String::from_utf8_lossy(&output.stderr).to_string(),
        })
    }

    async fn destroy(&self, _handle: SandboxHandle) -> Result<(), SandboxError> {
        Ok(())
    }
}

pub trait CommandRunExt {
    fn to_result_trace_payload(&self) -> CommandRunTrace;
}

impl CommandRunExt for CommandRun {
    fn to_result_trace_payload(&self) -> CommandRunTrace {
        CommandRunTrace {
            command: self.command.clone(),
            exit_code: self.exit_code,
            trace_id: self.task_run_id.to_string(),
            started_at: self.started_at,
            finished_at: self.finished_at,
        }
    }
}

#[derive(Debug)]
pub struct CommandRunTrace {
    pub command: String,
    pub exit_code: Option<i32>,
    pub trace_id: String,
    pub started_at: Option<chrono::DateTime<chrono::Utc>>,
    pub finished_at: Option<chrono::DateTime<chrono::Utc>>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio;

    #[tokio::test]
    async fn local_sandbox_denies_unknown_command() {
        let backend = LocalProcessSandboxBackend::default();
        let spec = SandboxSpec {
            task_id: Uuid::new_v4(),
            agent_id: Uuid::new_v4(),
            node_id: Uuid::new_v4(),
            allowlisted_commands: vec!["echo".into()],
            allow_network: false,
            allow_secrets: false,
            allow_root: false,
            max_duration_ms: 4_000,
        };
        let handle = backend.prepare(&spec).await.unwrap();
        let command = CommandSpec {
            command: "rm".into(),
            args: vec![],
            cwd: None,
            timeout_ms: 1_000,
            allow_network: false,
        };
        let result = backend.execute(&handle, &command).await;
        assert!(matches!(result, Err(SandboxError::Denied(_))));
    }

    #[tokio::test]
    async fn mock_sandbox_runs_demo_command() {
        let backend = MockSandboxBackend;
        let spec = SandboxSpec {
            task_id: Uuid::new_v4(),
            agent_id: Uuid::new_v4(),
            node_id: Uuid::new_v4(),
            allowlisted_commands: vec!["any".into()],
            allow_network: false,
            allow_secrets: false,
            allow_root: false,
            max_duration_ms: 1_000,
        };
        let handle = backend.prepare(&spec).await.unwrap();
        let cmd = CommandSpec {
            command: "demo".into(),
            args: vec!["ping".into()],
            cwd: None,
            timeout_ms: 500,
            allow_network: false,
        };
        let out = backend.execute(&handle, &cmd).await.unwrap();
        assert_eq!(out.exit_code, 0);
        assert!(out.stdout.contains("mock"));
    }

    #[tokio::test]
    async fn command_timeout_hard_fail() {
        let backend = LocalProcessSandboxBackend {
            default_timeout_ms: 100,
            command_allowlist: ["sleep"].into_iter().map(ToString::to_string).collect(),
            network_enabled: false,
            secrets_enabled: false,
        };
        let spec = SandboxSpec {
            task_id: Uuid::new_v4(),
            agent_id: Uuid::new_v4(),
            node_id: Uuid::new_v4(),
            allowlisted_commands: vec!["sleep".into()],
            allow_network: false,
            allow_secrets: false,
            allow_root: false,
            max_duration_ms: 100,
        };
        let handle = backend.prepare(&spec).await.unwrap();
        let cmd = CommandSpec {
            command: "sleep".into(),
            args: vec!["2".into()],
            cwd: None,
            timeout_ms: 100,
            allow_network: false,
        };
        let outcome = backend.execute(&handle, &cmd).await;
        assert!(matches!(outcome, Err(SandboxError::Timeout)));
    }
}
