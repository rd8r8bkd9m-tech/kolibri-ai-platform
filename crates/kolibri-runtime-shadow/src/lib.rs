use kolibri_core::{ResponseState, ResponseStatus};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ShadowProjection {
    pub response_id: String,
    pub state: String,
    pub sequence: u64,
}

pub fn project(response: &ResponseState) -> ShadowProjection {
    ShadowProjection {
        response_id: response.id.clone(),
        state: match response.status {
            ResponseStatus::Queued => "queued",
            ResponseStatus::Planning => "planning",
            ResponseStatus::Running => "running",
            ResponseStatus::WaitingForInput => "waiting_for_input",
            ResponseStatus::ApprovalRequired => "approval_required",
            ResponseStatus::Verifying => "verifying",
            ResponseStatus::Completed => "completed",
            ResponseStatus::Failed => "failed",
            ResponseStatus::Cancelled => "cancelled",
        }
        .to_owned(),
        sequence: response.last_sequence,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn projection_matches_python_contract() {
        let response = ResponseState {
            id: "resp_1".into(),
            project_id: "proj_1".into(),
            status: ResponseStatus::Verifying,
            output_text: String::new(),
            last_sequence: 9,
        };
        assert_eq!(project(&response), ShadowProjection { response_id: "resp_1".into(), state: "verifying".into(), sequence: 9 });
    }
}
