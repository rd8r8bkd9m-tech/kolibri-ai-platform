use crate::wire::v1_schema_version;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use thiserror::Error;
use uuid::Uuid;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum FormulaTraceKind {
    Prompt,
    Plan,
    ToolCall,
    ProviderResponse,
    Diff,
    Test,
    Error,
    Verdict,
    Artifact,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DataSensitivity {
    Public,
    Internal,
    Private,
    Confidential,
    Secret,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CreditShare {
    pub contributor: String,
    pub basis_points: u16,
    pub basis: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FormulaLMTrace {
    #[serde(default = "v1_schema_version")]
    pub schema_version: u32,
    pub id: Uuid,
    pub tenant_id: Uuid,
    pub project_id: Uuid,
    pub workstream_id: Option<Uuid>,
    pub task_id: Option<Uuid>,
    pub plan_node_id: Option<Uuid>,
    pub actor_id: Option<Uuid>,
    pub provider_attempt_id: Option<Uuid>,
    pub kind: FormulaTraceKind,
    pub content_hash: String,
    pub sanitized_summary: String,
    pub source_artifact_id: Option<Uuid>,
    pub sensitivity: DataSensitivity,
    pub policy_decision_id: Option<Uuid>,
    pub policy_allowed: bool,
    pub credit: Vec<CreditShare>,
    pub async_learning_requested: bool,
    /// Must remain false. Model changes are produced only by governed offline batches.
    pub live_weight_mutation: bool,
    pub trace_id: String,
    #[serde(default)]
    pub idempotency_key: String,
    pub created_at: DateTime<Utc>,
}

impl FormulaLMTrace {
    pub fn validate(&self) -> Result<(), FormulaTraceError> {
        if self.content_hash.trim().is_empty() {
            return Err(FormulaTraceError::MissingContentHash);
        }
        if self.live_weight_mutation {
            return Err(FormulaTraceError::LiveWeightMutationForbidden);
        }
        let credit_total: u32 = self
            .credit
            .iter()
            .map(|share| u32::from(share.basis_points))
            .sum();
        if credit_total > 10_000 {
            return Err(FormulaTraceError::InvalidCreditTotal(credit_total));
        }
        Ok(())
    }
}

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum FormulaTraceError {
    #[error("FormulaLM trace requires a content hash")]
    MissingContentHash,
    #[error("unstable live weight mutation is forbidden")]
    LiveWeightMutationForbidden,
    #[error("credit basis points exceed 10000: {0}")]
    InvalidCreditTotal(u32),
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ModelUpdateMode {
    GovernedBatchOnly,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FormulaTapPolicy {
    pub synchronous_provenance_gate: bool,
    pub synchronous_policy_gate: bool,
    pub synchronous_credit_gate: bool,
    pub asynchronous_learning_batch: bool,
    pub model_update_mode: ModelUpdateMode,
}

impl Default for FormulaTapPolicy {
    fn default() -> Self {
        Self {
            synchronous_provenance_gate: true,
            synchronous_policy_gate: true,
            synchronous_credit_gate: true,
            asynchronous_learning_batch: true,
            model_update_mode: ModelUpdateMode::GovernedBatchOnly,
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TrainingRights {
    Prohibited,
    Unknown,
    AllowedWithTerms,
    FirstPartyOnly,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ConsentBasis {
    Missing,
    Explicit,
    TenantPolicy,
    PublicLicense,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum LicenseBasis {
    Unknown,
    Owned,
    Permissive,
    Contractual,
    Restricted,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SanitizationReport {
    pub completed: bool,
    pub secrets_detected: bool,
    pub pii_detected: bool,
    pub private_data_detected: bool,
    pub all_sensitive_removed: bool,
    pub sanitizer_version: String,
    pub sanitized_content_hash: String,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum LearningEligibility {
    Pending,
    Eligible,
    Quarantined,
    Excluded,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct LearningCandidate {
    #[serde(default = "v1_schema_version")]
    pub schema_version: u32,
    #[serde(default)]
    pub trace_id: String,
    #[serde(default)]
    pub idempotency_key: String,
    pub id: Uuid,
    pub tenant_id: Uuid,
    pub project_id: Uuid,
    pub workstream_id: Option<Uuid>,
    pub trace_ids: Vec<Uuid>,
    pub source_artifact_id: Uuid,
    pub purpose: String,
    pub provider_id: Option<String>,
    pub training_rights: TrainingRights,
    pub consent_basis: ConsentBasis,
    pub license_basis: LicenseBasis,
    pub first_party_source: bool,
    pub sanitization: SanitizationReport,
    pub verifier_accepted: bool,
    pub quality_basis_points: u16,
    pub eligibility: LearningEligibility,
    pub eligibility_reasons: Vec<String>,
    pub created_at: DateTime<Utc>,
    pub evaluated_at: Option<DateTime<Utc>>,
}

impl LearningCandidate {
    pub fn evaluate_eligibility(
        &mut self,
        minimum_quality_basis_points: u16,
        evaluated_at: DateTime<Utc>,
    ) -> LearningEligibility {
        let mut excluded = Vec::new();
        let mut quarantine = Vec::new();

        if self.sanitization.private_data_detected {
            excluded.push("private_data_excluded".to_string());
        }
        if (self.sanitization.secrets_detected || self.sanitization.pii_detected)
            && !self.sanitization.all_sensitive_removed
        {
            excluded.push("sensitive_data_not_fully_removed".to_string());
        }
        if !self.sanitization.completed
            || self.sanitization.sanitized_content_hash.trim().is_empty()
        {
            quarantine.push("sanitization_incomplete".to_string());
        }
        match self.training_rights {
            TrainingRights::Prohibited => excluded.push("provider_training_prohibited".to_string()),
            TrainingRights::Unknown => quarantine.push("training_rights_unknown".to_string()),
            TrainingRights::FirstPartyOnly if !self.first_party_source => {
                excluded.push("first_party_training_only".to_string())
            }
            TrainingRights::AllowedWithTerms | TrainingRights::FirstPartyOnly => {}
        }
        match self.consent_basis {
            ConsentBasis::Missing => excluded.push("training_consent_missing".to_string()),
            ConsentBasis::Explicit | ConsentBasis::TenantPolicy | ConsentBasis::PublicLicense => {}
        }
        match self.license_basis {
            LicenseBasis::Restricted => excluded.push("license_restricts_training".to_string()),
            LicenseBasis::Unknown => quarantine.push("license_basis_unknown".to_string()),
            LicenseBasis::Owned | LicenseBasis::Permissive | LicenseBasis::Contractual => {}
        }
        if !self.verifier_accepted {
            quarantine.push("verifier_not_accepted".to_string());
        }
        if self.quality_basis_points < minimum_quality_basis_points {
            quarantine.push("quality_below_threshold".to_string());
        }

        self.eligibility = if !excluded.is_empty() {
            LearningEligibility::Excluded
        } else if !quarantine.is_empty() {
            LearningEligibility::Quarantined
        } else {
            LearningEligibility::Eligible
        };
        excluded.extend(quarantine);
        self.eligibility_reasons = excluded;
        self.evaluated_at = Some(evaluated_at);
        self.eligibility
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct DistillationBatch {
    pub id: Uuid,
    pub capability: String,
    pub candidate_ids: Vec<Uuid>,
    pub dataset_version: String,
    pub policy_version: String,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CapabilityTakeoverStage {
    Shadow,
    OnePercent,
    TenPercent,
    FiftyPercent,
    Full,
}

impl CapabilityTakeoverStage {
    pub fn traffic_basis_points(self) -> u16 {
        match self {
            Self::Shadow => 0,
            Self::OnePercent => 100,
            Self::TenPercent => 1_000,
            Self::FiftyPercent => 5_000,
            Self::Full => 10_000,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ShadowPredictionEvaluation {
    pub id: Uuid,
    pub capability: String,
    pub teacher_provider_attempt_id: Uuid,
    pub internal_prediction_artifact_id: Uuid,
    pub teacher_result_artifact_id: Uuid,
    pub evaluator_verdict_artifact_id: Uuid,
    pub quality_basis_points: u16,
    pub passed: bool,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CapabilityTakeover {
    pub capability: String,
    pub stage: CapabilityTakeoverStage,
    pub evaluation_id: Uuid,
    pub external_fallback_required: bool,
    pub promoted_at: DateTime<Utc>,
}
