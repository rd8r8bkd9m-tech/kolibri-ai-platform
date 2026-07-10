use chrono::{DateTime, Utc};
use kolibri_core::{
    select_resume, BacklogItem, BacklogPriority, BacklogStatus, CapabilityTakeoverStage,
    ChannelBinding, ChannelSurface, Checkpoint, CheckpointStatus, ConsentBasis, DataSensitivity,
    FormulaLMTrace, FormulaTraceError, FormulaTraceKind, LearningCandidate, LearningEligibility,
    LicenseBasis, Project, ProjectStatus, ResumeError, ResumeIndex, ResumeRequest,
    ResumeSelectionReason, SanitizationReport, TrainingRights, Workstream, WorkstreamStatus,
};
use uuid::Uuid;

fn id(value: u128) -> Uuid {
    Uuid::from_u128(value)
}

fn at(seconds: i64) -> DateTime<Utc> {
    DateTime::from_timestamp(seconds, 0).expect("valid fixture timestamp")
}

fn workstream(
    id_value: u128,
    project_id: Uuid,
    status: WorkstreamStatus,
    updated: i64,
) -> Workstream {
    Workstream {
        id: id(id_value),
        project_id,
        name: format!("workstream-{id_value}"),
        goal: "continue safely".into(),
        status,
        active_plan_id: None,
        active_task_id: None,
        version: 1,
        created_at: at(1),
        updated_at: at(updated),
    }
}

fn checkpoint(id_value: u128, project_id: Uuid, workstream_id: Uuid, sequence: u64) -> Checkpoint {
    Checkpoint {
        schema_version: 1,
        trace_id: format!("trace:checkpoint:{id_value}"),
        idempotency_key: format!("checkpoint:{id_value}"),
        id: id(id_value),
        project_id,
        workstream_id,
        sequence,
        status: CheckpointStatus::Open,
        active_plan_id: None,
        active_plan_node_id: None,
        active_task_id: None,
        next_action: "resume next plan node".into(),
        blockers: vec![],
        branch: Some("codex/continuity".into()),
        commit: None,
        dirty_tree_digest: Some("sha256:fixture".into()),
        tests: vec![],
        artifact_ids: vec![],
        context_digest: "sha256:context".into(),
        event_sequence: sequence,
        created_by: "owner".into(),
        created_at: at(sequence as i64),
    }
}

#[test]
fn resume_selection_obeys_explicit_binding_active_checkpoint_backlog_order() {
    let tenant_id = id(1);
    let project_id = id(2);
    let project = Project {
        id: project_id,
        tenant_id,
        name: "Kolibri".into(),
        slug: "kolibri".into(),
        status: ProjectStatus::Active,
        created_by: "owner".into(),
        created_at: at(1),
        updated_at: at(100),
    };
    let explicit = workstream(10, project_id, WorkstreamStatus::Planned, 10);
    let bound = workstream(11, project_id, WorkstreamStatus::Blocked, 20);
    let active = workstream(12, project_id, WorkstreamStatus::Active, 30);
    let checkpointed = workstream(13, project_id, WorkstreamStatus::Planned, 40);
    let backlog_stream = workstream(14, project_id, WorkstreamStatus::Planned, 50);
    let workstreams = vec![
        explicit.clone(),
        bound.clone(),
        active.clone(),
        checkpointed.clone(),
        backlog_stream.clone(),
    ];
    let binding = ChannelBinding {
        id: id(20),
        tenant_id,
        project_id,
        workstream_id: bound.id,
        surface: ChannelSurface::MimoCode,
        external_session_key: "sha256:mimo-session".into(),
        active: true,
        created_at: at(1),
        last_seen_at: at(90),
    };
    let checkpoints = vec![checkpoint(30, project_id, checkpointed.id, 30)];
    let backlog = vec![BacklogItem {
        id: id(40),
        project_id,
        workstream_id: Some(backlog_stream.id),
        title: "next useful task".into(),
        goal: "continue backlog".into(),
        acceptance: vec!["verified".into()],
        dependencies: vec![],
        priority: BacklogPriority::Critical,
        position: 1,
        status: BacklogStatus::Ready,
        created_at: at(1),
        updated_at: at(1),
    }];
    let projects = vec![project];
    let bindings = vec![binding];

    let explicit_selection = select_resume(
        &ResumeRequest {
            tenant_id,
            project_id: None,
            explicit_workstream_id: Some(explicit.id),
            surface: Some(ChannelSurface::MimoCode),
            external_session_key: Some("sha256:mimo-session".into()),
            create_new: false,
        },
        ResumeIndex {
            projects: &projects,
            workstreams: &workstreams,
            bindings: &bindings,
            checkpoints: &checkpoints,
            backlog: &backlog,
        },
    )
    .expect("explicit continuation");
    assert_eq!(
        explicit_selection.reason,
        ResumeSelectionReason::ExplicitWorkstream
    );
    assert_eq!(explicit_selection.workstream_id, Some(explicit.id));

    let bound_selection = select_resume(
        &ResumeRequest {
            tenant_id,
            project_id: None,
            explicit_workstream_id: None,
            surface: Some(ChannelSurface::MimoCode),
            external_session_key: Some("sha256:mimo-session".into()),
            create_new: false,
        },
        ResumeIndex {
            projects: &projects,
            workstreams: &workstreams,
            bindings: &bindings,
            checkpoints: &checkpoints,
            backlog: &backlog,
        },
    )
    .expect("bound continuation");
    assert_eq!(
        bound_selection.reason,
        ResumeSelectionReason::ChannelBinding
    );
    assert_eq!(bound_selection.workstream_id, Some(bound.id));

    let active_selection = select_resume(
        &ResumeRequest {
            tenant_id,
            project_id: None,
            explicit_workstream_id: None,
            surface: None,
            external_session_key: None,
            create_new: false,
        },
        ResumeIndex {
            projects: &projects,
            workstreams: &workstreams,
            bindings: &[],
            checkpoints: &checkpoints,
            backlog: &backlog,
        },
    )
    .expect("active continuation");
    assert_eq!(
        active_selection.reason,
        ResumeSelectionReason::LastActiveWorkstream
    );
    assert_eq!(active_selection.workstream_id, Some(active.id));

    let without_active: Vec<_> = workstreams
        .iter()
        .cloned()
        .map(|mut item| {
            if item.status == WorkstreamStatus::Active {
                item.status = WorkstreamStatus::Completed;
            }
            item
        })
        .collect();
    let checkpoint_selection = select_resume(
        &ResumeRequest {
            tenant_id,
            project_id: None,
            explicit_workstream_id: None,
            surface: None,
            external_session_key: None,
            create_new: false,
        },
        ResumeIndex {
            projects: &projects,
            workstreams: &without_active,
            bindings: &[],
            checkpoints: &checkpoints,
            backlog: &backlog,
        },
    )
    .expect("checkpoint continuation");
    assert_eq!(
        checkpoint_selection.reason,
        ResumeSelectionReason::LatestOpenCheckpoint
    );
    assert_eq!(checkpoint_selection.checkpoint_id, Some(id(30)));

    let backlog_selection = select_resume(
        &ResumeRequest {
            tenant_id,
            project_id: None,
            explicit_workstream_id: None,
            surface: None,
            external_session_key: None,
            create_new: false,
        },
        ResumeIndex {
            projects: &projects,
            workstreams: &without_active,
            bindings: &[],
            checkpoints: &[],
            backlog: &backlog,
        },
    )
    .expect("backlog continuation");
    assert_eq!(
        backlog_selection.reason,
        ResumeSelectionReason::ActionableBacklog
    );
    assert_eq!(backlog_selection.backlog_item_id, Some(id(40)));
}

#[test]
fn resume_never_creates_new_work_without_explicit_flag() {
    let tenant_id = id(1);
    let request = ResumeRequest {
        tenant_id,
        project_id: None,
        explicit_workstream_id: None,
        surface: None,
        external_session_key: None,
        create_new: false,
    };
    assert_eq!(
        select_resume(
            &request,
            ResumeIndex {
                projects: &[],
                workstreams: &[],
                bindings: &[],
                checkpoints: &[],
                backlog: &[],
            }
        ),
        Err(ResumeError::NoContinuation)
    );

    let explicit_new = select_resume(
        &ResumeRequest {
            create_new: true,
            ..request
        },
        ResumeIndex {
            projects: &[],
            workstreams: &[],
            bindings: &[],
            checkpoints: &[],
            backlog: &[],
        },
    )
    .expect("explicit new project");
    assert!(explicit_new.create_new);
    assert_eq!(
        explicit_new.reason,
        ResumeSelectionReason::ExplicitNewProject
    );
}

fn candidate(private_data: bool) -> LearningCandidate {
    LearningCandidate {
        schema_version: 1,
        trace_id: "trace:learning-candidate".into(),
        idempotency_key: "learning-candidate:100".into(),
        id: id(100),
        tenant_id: id(1),
        project_id: id(2),
        workstream_id: Some(id(3)),
        trace_ids: vec![id(4)],
        source_artifact_id: id(5),
        purpose: "governed capability distillation".into(),
        provider_id: Some("teacher".into()),
        training_rights: TrainingRights::AllowedWithTerms,
        consent_basis: ConsentBasis::Explicit,
        license_basis: LicenseBasis::Contractual,
        first_party_source: false,
        sanitization: SanitizationReport {
            completed: true,
            secrets_detected: false,
            pii_detected: false,
            private_data_detected: private_data,
            all_sensitive_removed: true,
            sanitizer_version: "1".into(),
            sanitized_content_hash: "sha256:safe".into(),
        },
        verifier_accepted: true,
        quality_basis_points: 9_000,
        eligibility: LearningEligibility::Pending,
        eligibility_reasons: vec![],
        created_at: at(1),
        evaluated_at: None,
    }
}

#[test]
fn formulalm_tap_forbids_live_mutation_and_excludes_private_training_data() {
    let mut trace = FormulaLMTrace {
        schema_version: 1,
        id: id(200),
        tenant_id: id(1),
        project_id: id(2),
        workstream_id: Some(id(3)),
        task_id: Some(id(4)),
        plan_node_id: Some(id(5)),
        actor_id: Some(id(6)),
        provider_attempt_id: Some(id(7)),
        kind: FormulaTraceKind::Prompt,
        content_hash: "sha256:prompt".into(),
        sanitized_summary: "owner requested an app".into(),
        source_artifact_id: None,
        sensitivity: DataSensitivity::Internal,
        policy_decision_id: Some(id(8)),
        policy_allowed: true,
        credit: vec![],
        async_learning_requested: true,
        live_weight_mutation: false,
        trace_id: "trace-1".into(),
        idempotency_key: "formula-trace:200".into(),
        created_at: at(1),
    };
    assert!(trace.validate().is_ok());
    trace.live_weight_mutation = true;
    assert_eq!(
        trace.validate(),
        Err(FormulaTraceError::LiveWeightMutationForbidden)
    );

    let mut private_candidate = candidate(true);
    assert_eq!(
        private_candidate.evaluate_eligibility(8_000, at(2)),
        LearningEligibility::Excluded
    );
    assert!(private_candidate
        .eligibility_reasons
        .contains(&"private_data_excluded".to_string()));

    let mut safe_candidate = candidate(false);
    assert_eq!(
        safe_candidate.evaluate_eligibility(8_000, at(2)),
        LearningEligibility::Eligible
    );

    assert_eq!(CapabilityTakeoverStage::Shadow.traffic_basis_points(), 0);
    assert_eq!(
        CapabilityTakeoverStage::OnePercent.traffic_basis_points(),
        100
    );
    assert_eq!(
        CapabilityTakeoverStage::TenPercent.traffic_basis_points(),
        1_000
    );
    assert_eq!(
        CapabilityTakeoverStage::FiftyPercent.traffic_basis_points(),
        5_000
    );
    assert_eq!(CapabilityTakeoverStage::Full.traffic_basis_points(), 10_000);
}
