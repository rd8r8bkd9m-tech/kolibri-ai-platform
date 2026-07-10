use chrono::{DateTime, Utc};
use kolibri_core::{
    ExecutionPlan, PlanNode, PlanNodeKind, PlanNodeState, PlanValidationError, PlatformRequirement,
    ResourceRequest, SwarmPlan, SwarmPlanError,
};
use serde_json::json;
use uuid::Uuid;

fn at(seconds: i64) -> DateTime<Utc> {
    DateTime::from_timestamp(seconds, 0).expect("valid fixture timestamp")
}

fn node(plan_id: Uuid, id: Uuid, dependencies: Vec<Uuid>, kind: PlanNodeKind) -> PlanNode {
    PlanNode {
        id,
        plan_id,
        name: format!("{kind:?}"),
        kind,
        state: PlanNodeState::Pending,
        dependencies,
        capability: "build_app".into(),
        input_schema: json!({"type":"object"}),
        output_schema: json!({"type":"object"}),
        acceptance: vec![],
        resource_request: ResourceRequest {
            platform: PlatformRequirement::Any,
            capability: "build_app".into(),
            cpu_millis: 100,
            memory_bytes: 1024,
            disk_bytes: 1024,
            gpu_required: false,
        },
        sandbox_profile: "default-deny".into(),
        max_attempts: 2,
        timeout_seconds: 60,
        critical_path_weight: 1,
    }
}

fn plan(nodes: Vec<PlanNode>, plan_id: Uuid) -> ExecutionPlan {
    ExecutionPlan {
        schema_version: 1,
        trace_id: "trace:dag".into(),
        idempotency_key: "plan:dag".into(),
        id: plan_id,
        project_id: Uuid::new_v4(),
        workstream_id: Uuid::new_v4(),
        version: 1,
        goal: "validate the execution DAG before scheduling".into(),
        nodes,
        created_by: "owner-api".into(),
        created_at: at(1),
    }
}

#[test]
fn execution_plan_rejects_duplicate_unknown_self_and_cyclic_dependencies() {
    let plan_id = Uuid::new_v4();
    let first_id = Uuid::new_v4();
    let second_id = Uuid::new_v4();

    let duplicate = plan(
        vec![
            node(plan_id, first_id, vec![], PlanNodeKind::Worker),
            node(plan_id, first_id, vec![], PlanNodeKind::Worker),
        ],
        plan_id,
    );
    assert_eq!(
        duplicate.validate_dag(),
        Err(PlanValidationError::DuplicateNodeId(first_id))
    );

    let unknown_id = Uuid::new_v4();
    let unknown = plan(
        vec![node(
            plan_id,
            first_id,
            vec![unknown_id],
            PlanNodeKind::Worker,
        )],
        plan_id,
    );
    assert_eq!(
        unknown.validate_dag(),
        Err(PlanValidationError::UnknownDependency {
            node_id: first_id,
            dependency_id: unknown_id,
        })
    );

    let self_dependent = plan(
        vec![node(
            plan_id,
            first_id,
            vec![first_id],
            PlanNodeKind::Worker,
        )],
        plan_id,
    );
    assert_eq!(
        self_dependent.validate_dag(),
        Err(PlanValidationError::SelfDependency(first_id))
    );

    let cyclic = plan(
        vec![
            node(plan_id, first_id, vec![second_id], PlanNodeKind::Worker),
            node(plan_id, second_id, vec![first_id], PlanNodeKind::Worker),
        ],
        plan_id,
    );
    assert!(matches!(
        cyclic.validate_dag(),
        Err(PlanValidationError::Cycle(remaining)) if remaining.len() == 2
    ));
}

#[test]
fn execution_plan_rejects_invalid_attempt_timeout_and_plan_identity() {
    let plan_id = Uuid::new_v4();
    let node_id = Uuid::new_v4();
    let mut invalid_attempt = node(plan_id, node_id, vec![], PlanNodeKind::Worker);
    invalid_attempt.max_attempts = 0;
    assert_eq!(
        plan(vec![invalid_attempt], plan_id).validate_dag(),
        Err(PlanValidationError::InvalidMaxAttempts(node_id))
    );

    let mut invalid_timeout = node(plan_id, node_id, vec![], PlanNodeKind::Worker);
    invalid_timeout.timeout_seconds = 0;
    assert_eq!(
        plan(vec![invalid_timeout], plan_id).validate_dag(),
        Err(PlanValidationError::InvalidTimeout(node_id))
    );

    let actual_plan_id = Uuid::new_v4();
    let mismatched = node(actual_plan_id, node_id, vec![], PlanNodeKind::Worker);
    assert_eq!(
        plan(vec![mismatched], plan_id).validate_dag(),
        Err(PlanValidationError::PlanIdMismatch {
            node_id,
            expected: plan_id,
            actual: actual_plan_id,
        })
    );
}

#[test]
fn swarm_plan_requires_a_declared_verifier() {
    let plan_id = Uuid::new_v4();
    let worker = node(plan_id, Uuid::new_v4(), vec![], PlanNodeKind::Worker);
    let execution_plan = plan(vec![worker], plan_id);
    let swarm = SwarmPlan {
        schema_version: 1,
        trace_id: execution_plan.trace_id.clone(),
        idempotency_key: "swarm:missing-verifier".into(),
        id: Uuid::new_v4(),
        requested_logical_actors: execution_plan.nodes.len(),
        max_physical_slots: 1,
        external_planner_provider: None,
        formula_tap_required: true,
        reducer_node_ids: vec![],
        verifier_node_ids: vec![],
        created_at: at(1),
        execution_plan,
    };
    assert_eq!(swarm.validate(), Err(SwarmPlanError::MissingVerifier));
}

#[test]
fn execution_and_swarm_plans_require_idempotent_trace_metadata() {
    let plan_id = Uuid::new_v4();
    let worker_id = Uuid::new_v4();
    let verifier_id = Uuid::new_v4();
    let mut execution = plan(
        vec![
            node(plan_id, worker_id, vec![], PlanNodeKind::Worker),
            node(
                plan_id,
                verifier_id,
                vec![worker_id],
                PlanNodeKind::Verifier,
            ),
        ],
        plan_id,
    );
    execution.trace_id.clear();
    assert_eq!(
        execution.validate_dag(),
        Err(PlanValidationError::MissingTraceId)
    );
    execution.trace_id = "trace:metadata".into();
    execution.idempotency_key.clear();
    assert_eq!(
        execution.validate_dag(),
        Err(PlanValidationError::MissingIdempotencyKey)
    );

    execution.idempotency_key = "plan:metadata".into();
    let mut swarm = SwarmPlan {
        schema_version: 1,
        trace_id: "trace:metadata".into(),
        idempotency_key: "swarm:metadata".into(),
        id: Uuid::new_v4(),
        requested_logical_actors: execution.nodes.len(),
        max_physical_slots: 1,
        external_planner_provider: None,
        formula_tap_required: true,
        reducer_node_ids: vec![],
        verifier_node_ids: vec![verifier_id],
        created_at: at(1),
        execution_plan: execution,
    };
    swarm.trace_id.clear();
    assert_eq!(swarm.validate(), Err(SwarmPlanError::MissingTraceId));
    swarm.trace_id = "trace:other".into();
    assert!(matches!(
        swarm.validate(),
        Err(SwarmPlanError::TraceIdMismatch { .. })
    ));
}

#[test]
fn every_execution_branch_must_end_at_a_declared_verifier() {
    let plan_id = Uuid::new_v4();
    let worker_id = Uuid::new_v4();
    let verifier_id = Uuid::new_v4();
    let execution = plan(
        vec![
            node(plan_id, worker_id, vec![], PlanNodeKind::Worker),
            node(plan_id, verifier_id, vec![], PlanNodeKind::Verifier),
        ],
        plan_id,
    );
    let disconnected = SwarmPlan {
        schema_version: 1,
        trace_id: execution.trace_id.clone(),
        idempotency_key: "swarm:disconnected-verifier".into(),
        id: Uuid::new_v4(),
        requested_logical_actors: execution.nodes.len(),
        max_physical_slots: 1,
        external_planner_provider: None,
        formula_tap_required: true,
        reducer_node_ids: vec![],
        verifier_node_ids: vec![verifier_id],
        created_at: at(1),
        execution_plan: execution,
    };
    assert_eq!(
        disconnected.validate(),
        Err(SwarmPlanError::UnverifiedTerminalNode(worker_id))
    );

    let plan_id = Uuid::new_v4();
    let verifier_id = Uuid::new_v4();
    let post_verifier_worker_id = Uuid::new_v4();
    let execution = plan(
        vec![
            node(plan_id, verifier_id, vec![], PlanNodeKind::Verifier),
            node(
                plan_id,
                post_verifier_worker_id,
                vec![verifier_id],
                PlanNodeKind::Worker,
            ),
        ],
        plan_id,
    );
    let post_verifier_work = SwarmPlan {
        schema_version: 1,
        trace_id: execution.trace_id.clone(),
        idempotency_key: "swarm:post-verifier-work".into(),
        id: Uuid::new_v4(),
        requested_logical_actors: execution.nodes.len(),
        max_physical_slots: 1,
        external_planner_provider: None,
        formula_tap_required: true,
        reducer_node_ids: vec![],
        verifier_node_ids: vec![verifier_id],
        created_at: at(1),
        execution_plan: execution,
    };
    assert_eq!(
        post_verifier_work.validate(),
        Err(SwarmPlanError::UnverifiedTerminalNode(
            post_verifier_worker_id
        ))
    );
}
