use jsonschema::{Draft, Validator};
use kolibri_core::{
    ComputeMode, FormulaLMLearningAdmissionInput, FormulaLMRejectionReason, GateStatus,
    LearningMaterialKind, LicenseDecision, LocalModelEvidence, LocalModelNodeAttestation,
    LocalModelRequirements, PiiConsent, ProhibitedLearningContent,
    evaluate_formulalm_learning_admission, evaluate_local_model_eligibility,
};
use serde_json::Value;
use std::collections::BTreeSet;

fn policy_validator() -> Validator {
    let schema: Value = serde_json::from_str(include_str!(
        "../../../contracts/kolibri-os-v1/model-and-learning-policy.schema.json"
    ))
    .expect("model policy contract is valid JSON");
    jsonschema::options()
        .with_draft(Draft::Draft202012)
        .build(&schema)
        .expect("model policy contract compiles")
}

fn evidence() -> LocalModelEvidence {
    LocalModelEvidence {
        memory_sha256: digest('1'),
        compute_sha256: digest('2'),
        license_sha256: digest('3'),
        disk_sha256: digest('4'),
        runtime_sha256: digest('5'),
        benchmark_sha256: digest('6'),
    }
}

fn digest(character: char) -> String {
    format!("sha256:{}", character.to_string().repeat(64))
}

fn requirements(compute_mode: ComputeMode) -> LocalModelRequirements {
    LocalModelRequirements {
        model_id: "kolibri-local-test".to_string(),
        compute_mode,
        min_memory_bytes: 16_000,
        min_cpu_cores: 8,
        min_gpu_memory_bytes: 12_000,
        min_disk_bytes: 50_000,
    }
}

fn node() -> LocalModelNodeAttestation {
    LocalModelNodeAttestation {
        available_memory_bytes: 32_000,
        available_cpu_cores: 16,
        gpu_available: false,
        available_gpu_memory_bytes: 0,
        available_disk_bytes: 100_000,
        license: LicenseDecision::Permitted,
        runtime_probe_passed: true,
        benchmark_passed: true,
        evidence: evidence(),
    }
}

fn clean_learning_input() -> FormulaLMLearningAdmissionInput {
    FormulaLMLearningAdmissionInput {
        source_material_kinds: BTreeSet::from([
            LearningMaterialKind::ModelOutput,
            LearningMaterialKind::ToolTrace,
            LearningMaterialKind::CodeDiff,
            LearningMaterialKind::TestResult,
            LearningMaterialKind::VerifierVerdict,
        ]),
        license: LicenseDecision::Permitted,
        pii_consent: PiiConsent::NotApplicable,
        prohibited_content: ProhibitedLearningContent {
            foreign_or_proprietary_weights_present: false,
            private_reasoning_present: false,
            secrets_present: false,
            pii_present: false,
            license_negative_trace_present: false,
        },
    }
}

fn assert_contract(value: &Value) {
    if let Err(error) = policy_validator().validate(value) {
        panic!("policy report violates model-and-learning contract: {error}; value={value}");
    }
}

#[test]
fn local_cpu_model_requires_every_gate_and_content_addressed_evidence() {
    let report = evaluate_local_model_eligibility(&requirements(ComputeMode::CpuOnly), &node());
    assert!(report.eligible);
    assert_eq!(report.gates.memory.status, GateStatus::Passed);
    assert_eq!(report.gates.compute.status, GateStatus::Passed);
    assert_eq!(report.gates.license.status, GateStatus::Passed);
    assert_eq!(report.gates.disk.status, GateStatus::Passed);
    assert_eq!(report.gates.runtime.status, GateStatus::Passed);
    assert_eq!(report.gates.benchmark.status, GateStatus::Passed);
    assert_contract(&serde_json::to_value(report).unwrap());
}

#[test]
fn local_model_fails_closed_when_resource_license_runtime_or_benchmark_gate_fails() {
    let mut failed = node();
    failed.available_memory_bytes = 1;
    failed.available_cpu_cores = 1;
    failed.available_disk_bytes = 1;
    failed.license = LicenseDecision::Negative;
    failed.runtime_probe_passed = false;
    failed.benchmark_passed = false;

    let report = evaluate_local_model_eligibility(&requirements(ComputeMode::CpuOnly), &failed);
    assert!(!report.eligible);
    assert_eq!(report.gates.memory.status, GateStatus::Failed);
    assert_eq!(report.gates.compute.status, GateStatus::Failed);
    assert_eq!(report.gates.license.status, GateStatus::Failed);
    assert_eq!(report.gates.disk.status, GateStatus::Failed);
    assert_eq!(report.gates.runtime.status, GateStatus::Failed);
    assert_eq!(report.gates.benchmark.status, GateStatus::Failed);
    assert_contract(&serde_json::to_value(report).unwrap());
}

#[test]
fn gpu_required_model_cannot_pass_on_cpu_only_capacity() {
    let requirements = requirements(ComputeMode::GpuRequired);
    let mut attestation = node();
    let rejected = evaluate_local_model_eligibility(&requirements, &attestation);
    assert!(!rejected.eligible);
    assert_eq!(rejected.gates.compute.status, GateStatus::Failed);

    attestation.gpu_available = true;
    attestation.available_gpu_memory_bytes = requirements.min_gpu_memory_bytes;
    let admitted = evaluate_local_model_eligibility(&requirements, &attestation);
    assert!(admitted.eligible);
    assert_contract(&serde_json::to_value(admitted).unwrap());
}

#[test]
fn a_passed_measurement_without_valid_evidence_is_not_an_eligible_gate() {
    let mut attestation = node();
    attestation.evidence.benchmark_sha256 = "not-content-addressed".to_string();
    let report =
        evaluate_local_model_eligibility(&requirements(ComputeMode::CpuOnly), &attestation);
    assert!(!report.eligible);
    assert_eq!(report.gates.benchmark.status, GateStatus::Failed);
    assert_eq!(
        report.gates.benchmark.reason_code.as_deref(),
        Some("evidence_missing_or_invalid")
    );
    assert_contract(&serde_json::to_value(report).unwrap());
}

#[test]
fn formulalm_accepts_only_declared_permitted_learning_materials() {
    let report = evaluate_formulalm_learning_admission(&clean_learning_input());
    assert!(report.eligible);
    assert!(report.rejection_reasons.is_empty());
    assert_eq!(report.source_material_kinds.len(), 5);
    assert_contract(&serde_json::to_value(report).unwrap());
}

#[test]
fn formulalm_rejects_weights_private_reasoning_secrets_unconsented_pii_and_negative_traces() {
    let mut input = clean_learning_input();
    input.license = LicenseDecision::Negative;
    input.pii_consent = PiiConsent::Denied;
    input.prohibited_content = ProhibitedLearningContent {
        foreign_or_proprietary_weights_present: true,
        private_reasoning_present: true,
        secrets_present: true,
        pii_present: true,
        license_negative_trace_present: true,
    };

    let report = evaluate_formulalm_learning_admission(&input);
    assert!(!report.eligible);
    assert_eq!(
        report.rejection_reasons,
        vec![
            FormulaLMRejectionReason::ForeignOrProprietaryWeights,
            FormulaLMRejectionReason::PrivateReasoning,
            FormulaLMRejectionReason::Secrets,
            FormulaLMRejectionReason::PiiWithoutConsent,
            FormulaLMRejectionReason::LicenseNegativeTrace,
            FormulaLMRejectionReason::LicenseNotPermitted,
        ]
    );
    assert_contract(&serde_json::to_value(report).unwrap());
}

#[test]
fn formulalm_allows_consent_bound_pii_but_never_private_reasoning() {
    let mut input = clean_learning_input();
    input.pii_consent = PiiConsent::Explicit;
    input.prohibited_content.pii_present = true;
    assert!(evaluate_formulalm_learning_admission(&input).eligible);

    input.prohibited_content.private_reasoning_present = true;
    assert!(!evaluate_formulalm_learning_admission(&input).eligible);
}

#[test]
fn json_contract_rejects_fabricated_eligible_claims() {
    let mut local = serde_json::to_value(evaluate_local_model_eligibility(
        &requirements(ComputeMode::CpuOnly),
        &node(),
    ))
    .unwrap();
    local["gates"]["runtime"]["status"] = Value::String("failed".to_string());
    local["gates"]["runtime"]["reason_code"] = Value::String("failed".to_string());
    assert!(policy_validator().validate(&local).is_err());

    let mut learning = serde_json::to_value(evaluate_formulalm_learning_admission(
        &clean_learning_input(),
    ))
    .unwrap();
    learning["prohibited_content"]["private_reasoning_present"] = Value::Bool(true);
    assert!(policy_validator().validate(&learning).is_err());
}
