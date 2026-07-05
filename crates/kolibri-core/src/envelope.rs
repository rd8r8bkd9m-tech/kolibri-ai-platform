use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct TaskSubmitEnvelope {
    pub owner: String,
    pub kind: String,
    pub payload: Value,
    pub sensitivity: String,
}

impl TaskSubmitEnvelope {
    pub fn task_id_hint(&self) -> Option<Uuid> {
        None
    }
}
