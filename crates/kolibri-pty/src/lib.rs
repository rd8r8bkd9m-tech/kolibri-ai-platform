use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PtySession {
    pub pty_session_id: Uuid,
    pub task_id: Uuid,
    pub agent_id: Uuid,
    pub node_id: Uuid,
    pub actor: String,
    pub status: PtySessionStatus,
    pub created_at: DateTime<Utc>,
    pub closed_at: Option<DateTime<Utc>>,
    pub approval_id: Option<Uuid>,
    pub sandbox_profile: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum PtySessionStatus {
    Requested,
    Approved,
    Opened,
    Closed,
    Denied,
}

impl PtySession {
    pub fn request(
        task_id: Uuid,
        agent_id: Uuid,
        node_id: Uuid,
        actor: String,
        sandbox_profile: String,
    ) -> Self {
        Self {
            pty_session_id: Uuid::new_v4(),
            task_id,
            agent_id,
            node_id,
            actor,
            status: PtySessionStatus::Requested,
            created_at: Utc::now(),
            closed_at: None,
            approval_id: None,
            sandbox_profile,
        }
    }

    pub fn approve(&mut self, approval_id: Uuid) {
        self.approval_id = Some(approval_id);
        self.status = PtySessionStatus::Approved;
    }

    pub fn open(&mut self) {
        if matches!(self.status, PtySessionStatus::Approved) {
            self.status = PtySessionStatus::Opened;
        }
    }

    pub fn deny(&mut self, reason: &str) {
        let _ = reason;
        self.status = PtySessionStatus::Denied;
        self.closed_at = Some(Utc::now());
    }

    pub fn close(&mut self) {
        self.status = PtySessionStatus::Closed;
        self.closed_at = Some(Utc::now());
    }
}

pub enum MockTerminalFrame {
    Output(String),
    Exit(i32),
}

pub fn create_mock_terminal_stream(task_id: Uuid, agent_id: Uuid, node_id: Uuid) -> PtySession {
    PtySession::request(
        task_id,
        agent_id,
        node_id,
        "system".into(),
        "local-mock-shell".into(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pty_lifecycle_stays_safe() {
        let mut session = PtySession::request(
            Uuid::new_v4(),
            Uuid::new_v4(),
            Uuid::new_v4(),
            "owner".into(),
            "mock".into(),
        );
        assert_eq!(session.status, PtySessionStatus::Requested);
        session.approve(Uuid::new_v4());
        assert_eq!(session.status, PtySessionStatus::Approved);
        session.open();
        assert_eq!(session.status, PtySessionStatus::Opened);
        session.close();
        assert_eq!(session.status, PtySessionStatus::Closed);
        assert!(session.closed_at.is_some());
    }
}
