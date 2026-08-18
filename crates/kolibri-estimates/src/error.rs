use serde::Serialize;
use std::fmt;

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ValidationIssue {
    pub path: String,
    pub code: String,
    pub message: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EstimateError {
    issue: ValidationIssue,
}

impl EstimateError {
    pub(crate) fn new(
        path: impl Into<String>,
        code: impl Into<String>,
        message: impl Into<String>,
    ) -> Self {
        Self {
            issue: ValidationIssue {
                path: path.into(),
                code: code.into(),
                message: message.into(),
            },
        }
    }

    pub(crate) fn canonical(message: impl Into<String>) -> Self {
        Self::new("$", "canonical_json_failed", message)
    }

    #[must_use]
    pub fn issue(&self) -> &ValidationIssue {
        &self.issue
    }

    #[must_use]
    pub fn into_issue(self) -> ValidationIssue {
        self.issue
    }
}

impl fmt::Display for EstimateError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "{} ({}): {}",
            self.issue.path, self.issue.code, self.issue.message
        )
    }
}

impl std::error::Error for EstimateError {}
