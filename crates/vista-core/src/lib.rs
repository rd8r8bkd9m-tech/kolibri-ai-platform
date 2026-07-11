use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ChatMessage {
    pub id: String,
    pub kind: String,
    pub text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct WorkspaceState {
    pub session_id: String,
    pub role: String,
    pub active_app: String,
    pub minimized_apps: Vec<String>,
    pub active_estimate_id: Option<String>,
    pub chat: Vec<ChatMessage>,
    pub revision: u64,
}

impl WorkspaceState {
    pub fn new(session_id: impl Into<String>, role: impl Into<String>) -> Self {
        Self {
            session_id: session_id.into(),
            role: role.into(),
            active_app: "home".to_string(),
            minimized_apps: Vec::new(),
            active_estimate_id: None,
            chat: Vec::new(),
            revision: 0,
        }
    }

    pub fn apply(mut self, command: WorkspaceCommand) -> WorkspaceTransition {
        match &command {
            WorkspaceCommand::OpenApp { app_id } | WorkspaceCommand::FocusApp { app_id } => {
                self.active_app = app_id.clone();
                self.minimized_apps.retain(|item| item != app_id);
            }
            WorkspaceCommand::MinimizeApp { app_id } => {
                if !self.minimized_apps.contains(app_id) {
                    self.minimized_apps.push(app_id.clone());
                }
                if self.active_app == *app_id {
                    self.active_app = "home".to_string();
                }
            }
            WorkspaceCommand::CloseApp { app_id } => {
                self.minimized_apps.retain(|item| item != app_id);
                if self.active_app == *app_id {
                    self.active_app = "home".to_string();
                }
            }
            WorkspaceCommand::SetActiveEstimate { estimate_id } => {
                self.active_estimate_id = estimate_id.clone();
            }
            WorkspaceCommand::AppendChat { message } => {
                self.chat.push(message.clone());
                if self.chat.len() > 100 {
                    let remove = self.chat.len() - 100;
                    self.chat.drain(0..remove);
                }
            }
            WorkspaceCommand::Reset => {
                self.active_app = "home".to_string();
                self.minimized_apps.clear();
                self.active_estimate_id = None;
                self.chat.clear();
            }
        }
        self.revision += 1;
        WorkspaceTransition {
            event: WorkspaceEvent {
                revision: self.revision,
                command,
            },
            state: self,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum WorkspaceCommand {
    OpenApp { app_id: String },
    FocusApp { app_id: String },
    MinimizeApp { app_id: String },
    CloseApp { app_id: String },
    SetActiveEstimate { estimate_id: Option<String> },
    AppendChat { message: ChatMessage },
    Reset,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct WorkspaceEvent {
    pub revision: u64,
    pub command: WorkspaceCommand,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct WorkspaceTransition {
    pub state: WorkspaceState,
    pub event: WorkspaceEvent,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn state_kernel_opens_minimizes_and_restores_apps() {
        let state = WorkspaceState::new("session-1", "client_pro");
        let opened = state.apply(WorkspaceCommand::OpenApp { app_id: "estimate".into() });
        assert_eq!(opened.state.active_app, "estimate");
        assert_eq!(opened.state.revision, 1);

        let minimized = opened.state.apply(WorkspaceCommand::MinimizeApp { app_id: "estimate".into() });
        assert_eq!(minimized.state.active_app, "home");
        assert_eq!(minimized.state.minimized_apps, vec!["estimate"]);

        let restored = minimized.state.apply(WorkspaceCommand::FocusApp { app_id: "estimate".into() });
        assert_eq!(restored.state.active_app, "estimate");
        assert!(restored.state.minimized_apps.is_empty());
    }

    #[test]
    fn chat_history_is_bounded() {
        let mut state = WorkspaceState::new("session-1", "client");
        for index in 0..120 {
            state = state.apply(WorkspaceCommand::AppendChat {
                message: ChatMessage { id: index.to_string(), kind: "user".into(), text: "test".into() },
            }).state;
        }
        assert_eq!(state.chat.len(), 100);
        assert_eq!(state.chat.first().unwrap().id, "20");
    }
}
