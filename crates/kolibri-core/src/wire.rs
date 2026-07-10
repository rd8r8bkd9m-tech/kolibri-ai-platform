use serde::{Deserialize, Serialize};
use thiserror::Error;

pub const V1_SCHEMA_VERSION: u32 = 1;

pub const fn v1_schema_version() -> u32 {
    V1_SCHEMA_VERSION
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct WireMetadata {
    #[serde(default = "v1_schema_version")]
    pub schema_version: u32,
    #[serde(default)]
    pub trace_id: String,
    #[serde(default)]
    pub idempotency_key: String,
}

impl WireMetadata {
    pub fn v1(trace_id: impl Into<String>, idempotency_key: impl Into<String>) -> Self {
        Self {
            schema_version: V1_SCHEMA_VERSION,
            trace_id: trace_id.into(),
            idempotency_key: idempotency_key.into(),
        }
    }

    pub fn validate(&self) -> Result<(), WireMetadataError> {
        if self.schema_version != V1_SCHEMA_VERSION {
            return Err(WireMetadataError::UnsupportedSchemaVersion(
                self.schema_version,
            ));
        }
        if self.trace_id.trim().is_empty() {
            return Err(WireMetadataError::MissingTraceId);
        }
        if self.idempotency_key.trim().is_empty() {
            return Err(WireMetadataError::MissingIdempotencyKey);
        }
        Ok(())
    }
}

impl Default for WireMetadata {
    fn default() -> Self {
        Self {
            schema_version: V1_SCHEMA_VERSION,
            trace_id: String::new(),
            idempotency_key: String::new(),
        }
    }
}

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum WireMetadataError {
    #[error("unsupported wire schema version: {0}")]
    UnsupportedSchemaVersion(u32),
    #[error("wire record requires a trace id")]
    MissingTraceId,
    #[error("wire record requires an idempotency key")]
    MissingIdempotencyKey,
}
