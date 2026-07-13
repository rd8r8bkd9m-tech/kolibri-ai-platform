use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ResponseStatus {
    Queued,
    Planning,
    Running,
    WaitingForInput,
    ApprovalRequired,
    Verifying,
    Completed,
    Failed,
    Cancelled,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ResponseState {
    pub id: String,
    pub project_id: String,
    pub status: ResponseStatus,
    pub output_text: String,
    pub last_sequence: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct AttemptState {
    pub task_id: String,
    pub attempt_id: String,
    pub lease_id: String,
    pub lease_owner: String,
    pub fencing_token: u64,
    pub result_hash: Option<String>,
    pub verifier_binding: Option<String>,
}

impl AttemptState {
    pub fn accepts(&self, lease_id: &str, fencing_token: u64) -> bool {
        self.lease_id == lease_id && self.fencing_token == fencing_token
    }

    pub fn bind_result(&mut self, result: &[u8]) {
        let result_hash = format!("{:x}", Sha256::digest(result));
        let binding = format!(
            "{:x}",
            Sha256::digest(format!("{}:{}:{}:{}", self.task_id, self.attempt_id, self.fencing_token, result_hash))
        );
        self.result_hash = Some(result_hash);
        self.verifier_binding = Some(binding);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stale_fencing_is_rejected() {
        let attempt = AttemptState {
            task_id: "task_1".into(),
            attempt_id: "attempt_1".into(),
            lease_id: "lease_1".into(),
            lease_owner: "node_1".into(),
            fencing_token: 7,
            result_hash: None,
            verifier_binding: None,
        };
        assert!(attempt.accepts("lease_1", 7));
        assert!(!attempt.accepts("lease_1", 6));
        assert!(!attempt.accepts("old", 7));
    }

    #[test]
    fn result_binding_is_deterministic() {
        let mut attempt = AttemptState {
            task_id: "task_1".into(),
            attempt_id: "attempt_1".into(),
            lease_id: "lease_1".into(),
            lease_owner: "node_1".into(),
            fencing_token: 7,
            result_hash: None,
            verifier_binding: None,
        };
        attempt.bind_result(b"result");
        assert!(attempt.result_hash.as_ref().is_some_and(|hash| hash.len() == 64));
        assert!(attempt.verifier_binding.as_ref().is_some_and(|hash| hash.len() == 64));
    }
}
