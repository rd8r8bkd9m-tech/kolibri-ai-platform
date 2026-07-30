use serde::Serialize;
use thiserror::Error;

pub type Result<T> = std::result::Result<T, ExecutorError>;

#[derive(Debug, Error)]
pub enum ExecutorError {
    #[error("{code}")]
    Rejected {
        code: &'static str,
        message: &'static str,
    },
    #[error("{code}")]
    Incomplete {
        code: &'static str,
        message: &'static str,
    },
    #[error("storage executor internal error")]
    Internal(#[source] Box<dyn std::error::Error + Send + Sync>),
}

impl ExecutorError {
    pub fn rejected(code: &'static str, message: &'static str) -> Self {
        Self::Rejected { code, message }
    }

    pub fn incomplete(code: &'static str, message: &'static str) -> Self {
        Self::Incomplete { code, message }
    }

    pub fn internal(error: impl std::error::Error + Send + Sync + 'static) -> Self {
        Self::Internal(Box::new(error))
    }

    pub fn code(&self) -> &'static str {
        match self {
            Self::Rejected { code, .. } | Self::Incomplete { code, .. } => code,
            Self::Internal(_) => "storage_executor_internal",
        }
    }

    pub fn safe_message(&self) -> &'static str {
        match self {
            Self::Rejected { message, .. } | Self::Incomplete { message, .. } => message,
            Self::Internal(_) => "The storage executor failed closed.",
        }
    }

    pub fn retryable(&self) -> bool {
        matches!(self, Self::Incomplete { .. })
    }
}

impl From<rusqlite::Error> for ExecutorError {
    fn from(value: rusqlite::Error) -> Self {
        Self::internal(value)
    }
}

impl From<std::io::Error> for ExecutorError {
    fn from(value: std::io::Error) -> Self {
        Self::internal(value)
    }
}

impl From<serde_json::Error> for ExecutorError {
    fn from(value: serde_json::Error) -> Self {
        Self::internal(value)
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ErrorBody {
    pub code: &'static str,
    pub message: &'static str,
    pub retryable: bool,
}

impl From<&ExecutorError> for ErrorBody {
    fn from(value: &ExecutorError) -> Self {
        Self {
            code: value.code(),
            message: value.safe_message(),
            retryable: value.retryable(),
        }
    }
}
