//! Fail-closed admission policy for local model runtimes and FormulaLM data.
//!
//! This module evaluates already captured, content-addressed probe evidence. It
//! does not install a model, inspect provider internals, train weights or grant
//! runtime authority by itself.

use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

pub const LOCAL_MODEL_ELIGIBILITY_SCHEMA: &str = "kolibri.local-model-eligibility.v1";
pub const FORMULALM_ADMISSION_SCHEMA: &str = "kolibri.formulalm-admission.v1";

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ComputeMode {
    CpuOnly,
    CpuOrGpu,
    GpuRequired,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum LicenseDecision {
    Permitted,
    Restricted,
    Negative,
    Unknown,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum GateStatus {
    Passed,
    Failed,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct LocalModelRequirements {
    pub model_id: String,
    pub compute_mode: ComputeMode,
    pub min_memory_bytes: u64,
    pub min_cpu_cores: u16,
    pub min_gpu_memory_bytes: u64,
    pub min_disk_bytes: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct LocalModelNodeAttestation {
    pub available_memory_bytes: u64,
    pub available_cpu_cores: u16,
    pub gpu_available: bool,
    pub available_gpu_memory_bytes: u64,
    pub available_disk_bytes: u64,
    pub license: LicenseDecision,
    pub runtime_probe_passed: bool,
    pub benchmark_passed: bool,
    pub evidence: LocalModelEvidence,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct LocalModelEvidence {
    pub memory_sha256: String,
    pub compute_sha256: String,
    pub license_sha256: String,
    pub disk_sha256: String,
    pub runtime_sha256: String,
    pub benchmark_sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct GateAssessment {
    pub status: GateStatus,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub evidence_sha256: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason_code: Option<String>,
}

impl GateAssessment {
    fn from_check(check_passed: bool, evidence: &str, reason_code: &str) -> Self {
        if !valid_sha256(evidence) {
            return Self {
                status: GateStatus::Failed,
                evidence_sha256: None,
                reason_code: Some("evidence_missing_or_invalid".to_string()),
            };
        }
        if check_passed {
            Self {
                status: GateStatus::Passed,
                evidence_sha256: Some(evidence.to_string()),
                reason_code: None,
            }
        } else {
            Self {
                status: GateStatus::Failed,
                evidence_sha256: Some(evidence.to_string()),
                reason_code: Some(reason_code.to_string()),
            }
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct LocalModelGateReport {
    pub memory: GateAssessment,
    pub compute: GateAssessment,
    pub license: GateAssessment,
    pub disk: GateAssessment,
    pub runtime: GateAssessment,
    pub benchmark: GateAssessment,
}

impl LocalModelGateReport {
    fn all_passed(&self) -> bool {
        [
            &self.memory,
            &self.compute,
            &self.license,
            &self.disk,
            &self.runtime,
            &self.benchmark,
        ]
        .into_iter()
        .all(|gate| gate.status == GateStatus::Passed)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct LocalModelEligibilityReport {
    pub schema_version: String,
    pub model_id: String,
    pub compute_mode: ComputeMode,
    pub eligible: bool,
    pub gates: LocalModelGateReport,
}

pub fn evaluate_local_model_eligibility(
    requirements: &LocalModelRequirements,
    node: &LocalModelNodeAttestation,
) -> LocalModelEligibilityReport {
    let cpu_passed = node.available_cpu_cores >= requirements.min_cpu_cores;
    let gpu_passed =
        node.gpu_available && node.available_gpu_memory_bytes >= requirements.min_gpu_memory_bytes;
    let compute_passed = match requirements.compute_mode {
        ComputeMode::CpuOnly => cpu_passed,
        ComputeMode::CpuOrGpu => cpu_passed || gpu_passed,
        ComputeMode::GpuRequired => gpu_passed,
    };

    let gates = LocalModelGateReport {
        memory: GateAssessment::from_check(
            node.available_memory_bytes >= requirements.min_memory_bytes,
            &node.evidence.memory_sha256,
            "memory_below_requirement",
        ),
        compute: GateAssessment::from_check(
            compute_passed,
            &node.evidence.compute_sha256,
            "compute_below_requirement",
        ),
        license: GateAssessment::from_check(
            node.license == LicenseDecision::Permitted,
            &node.evidence.license_sha256,
            "license_not_permitted",
        ),
        disk: GateAssessment::from_check(
            node.available_disk_bytes >= requirements.min_disk_bytes,
            &node.evidence.disk_sha256,
            "disk_below_requirement",
        ),
        runtime: GateAssessment::from_check(
            node.runtime_probe_passed,
            &node.evidence.runtime_sha256,
            "runtime_probe_failed",
        ),
        benchmark: GateAssessment::from_check(
            node.benchmark_passed,
            &node.evidence.benchmark_sha256,
            "benchmark_failed",
        ),
    };

    LocalModelEligibilityReport {
        schema_version: LOCAL_MODEL_ELIGIBILITY_SCHEMA.to_string(),
        model_id: requirements.model_id.clone(),
        compute_mode: requirements.compute_mode,
        eligible: !requirements.model_id.trim().is_empty() && gates.all_passed(),
        gates,
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub enum LearningMaterialKind {
    ModelOutput,
    ToolTrace,
    CodeDiff,
    TestResult,
    VerifierVerdict,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
pub enum PiiConsent {
    Explicit,
    Contractual,
    PublicPermitted,
    Denied,
    Unknown,
    NotApplicable,
}

impl PiiConsent {
    const fn permits_pii(self) -> bool {
        matches!(
            self,
            Self::Explicit | Self::Contractual | Self::PublicPermitted
        )
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ProhibitedLearningContent {
    pub foreign_or_proprietary_weights_present: bool,
    pub private_reasoning_present: bool,
    pub secrets_present: bool,
    pub pii_present: bool,
    pub license_negative_trace_present: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FormulaLMLearningAdmissionInput {
    pub source_material_kinds: BTreeSet<LearningMaterialKind>,
    pub license: LicenseDecision,
    pub pii_consent: PiiConsent,
    pub prohibited_content: ProhibitedLearningContent,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum FormulaLMRejectionReason {
    MissingPermittedMaterial,
    ForeignOrProprietaryWeights,
    PrivateReasoning,
    Secrets,
    PiiWithoutConsent,
    LicenseNegativeTrace,
    LicenseNotPermitted,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FormulaLMLearningAdmissionReport {
    pub schema_version: String,
    pub eligible: bool,
    pub source_material_kinds: BTreeSet<LearningMaterialKind>,
    pub license: LicenseDecision,
    pub pii_consent: PiiConsent,
    pub prohibited_content: ProhibitedLearningContent,
    pub rejection_reasons: Vec<FormulaLMRejectionReason>,
}

pub fn evaluate_formulalm_learning_admission(
    input: &FormulaLMLearningAdmissionInput,
) -> FormulaLMLearningAdmissionReport {
    let mut rejection_reasons = Vec::new();
    if input.source_material_kinds.is_empty() {
        rejection_reasons.push(FormulaLMRejectionReason::MissingPermittedMaterial);
    }
    if input
        .prohibited_content
        .foreign_or_proprietary_weights_present
    {
        rejection_reasons.push(FormulaLMRejectionReason::ForeignOrProprietaryWeights);
    }
    if input.prohibited_content.private_reasoning_present {
        rejection_reasons.push(FormulaLMRejectionReason::PrivateReasoning);
    }
    if input.prohibited_content.secrets_present {
        rejection_reasons.push(FormulaLMRejectionReason::Secrets);
    }
    if input.prohibited_content.pii_present && !input.pii_consent.permits_pii() {
        rejection_reasons.push(FormulaLMRejectionReason::PiiWithoutConsent);
    }
    if input.prohibited_content.license_negative_trace_present {
        rejection_reasons.push(FormulaLMRejectionReason::LicenseNegativeTrace);
    }
    if input.license != LicenseDecision::Permitted {
        rejection_reasons.push(FormulaLMRejectionReason::LicenseNotPermitted);
    }

    FormulaLMLearningAdmissionReport {
        schema_version: FORMULALM_ADMISSION_SCHEMA.to_string(),
        eligible: rejection_reasons.is_empty(),
        source_material_kinds: input.source_material_kinds.clone(),
        license: input.license,
        pii_consent: input.pii_consent,
        prohibited_content: input.prohibited_content.clone(),
        rejection_reasons,
    }
}

fn valid_sha256(value: &str) -> bool {
    value.strip_prefix("sha256:").is_some_and(|digest| {
        digest.len() == 64
            && digest
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    })
}
