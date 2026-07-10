use chrono::{DateTime, Utc};
use kolibri_core::{
    ExecutionPlan, LeaseExpiryAction, LeaseOutcome, LogicalActor, LogicalActorState,
    PlanExecutionState, PlanNode, PlanNodeKind, PlanNodeState, PlatformRequirement,
    ResourceCapacity, ResourceRequest, ResourceSlot, SchedulerError, SlotPlatform, SwarmPlan,
    SwarmScheduler,
};
use serde_json::json;
use uuid::Uuid;

fn at(seconds: i64) -> DateTime<Utc> {
    DateTime::from_timestamp(seconds, 0).expect("valid fixture timestamp")
}

fn node(
    plan_id: Uuid,
    id: Uuid,
    kind: PlanNodeKind,
    dependencies: Vec<Uuid>,
    max_attempts: u32,
    timeout_seconds: u64,
) -> PlanNode {
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
            platform: PlatformRequirement::Ubuntu,
            capability: "build_app".into(),
            cpu_millis: 100,
            memory_bytes: 1024,
            disk_bytes: 1024,
            gpu_required: false,
        },
        sandbox_profile: "worktree-default-deny".into(),
        max_attempts,
        timeout_seconds,
        critical_path_weight: 1,
    }
}

fn slot(id: Uuid) -> ResourceSlot {
    ResourceSlot {
        id,
        node_id: format!("worker-{id}"),
        platform: SlotPlatform::Ubuntu,
        capabilities: vec!["build_app".into()],
        capacity: ResourceCapacity {
            cpu_millis: 1_000,
            memory_bytes: 1024 * 1024,
            disk_bytes: 1024 * 1024,
            gpu_available: false,
        },
        active_lease: None,
        enabled: true,
    }
}

fn one_actor_scheduler(
    max_attempts: u32,
    timeout_seconds: u64,
    lease_seconds: i64,
) -> (SwarmScheduler, Uuid, Uuid, Uuid) {
    let plan_id = Uuid::new_v4();
    let actor_id = Uuid::new_v4();
    let actor = LogicalActor::from_plan_node(
        Uuid::new_v4(),
        &node(
            plan_id,
            actor_id,
            PlanNodeKind::Worker,
            vec![],
            max_attempts,
            timeout_seconds,
        ),
    );
    let first_slot_id = Uuid::from_u128(10);
    let second_slot_id = Uuid::from_u128(20);
    let scheduler = SwarmScheduler::new(
        Uuid::new_v4(),
        vec![actor],
        vec![slot(first_slot_id), slot(second_slot_id)],
        lease_seconds,
    )
    .expect("valid scheduler");
    (scheduler, actor_id, first_slot_id, second_slot_id)
}

#[test]
fn worker_loss_is_requeued_within_sixty_seconds_and_late_completion_is_fenced() {
    let (mut scheduler, actor_id, first_slot_id, second_slot_id) = one_actor_scheduler(2, 300, 60);
    let first = scheduler
        .claim_next(first_slot_id, at(0))
        .expect("claim succeeds")
        .expect("actor available");
    assert_eq!(first.expires_at, at(60));

    let expired = scheduler.expire_and_requeue(at(60));
    assert_eq!(expired.len(), 1);
    assert_eq!(expired[0].action, LeaseExpiryAction::Requeued);
    assert_eq!(expired[0].actor_id, actor_id);
    assert_eq!(scheduler.actors[&actor_id].state, LogicalActorState::Ready);
    assert_eq!(scheduler.snapshot().occupied_slot_count, 0);
    assert_eq!(
        scheduler.finish_lease(
            first.id,
            first.fencing_token,
            LeaseOutcome::Completed,
            at(60),
        ),
        Err(SchedulerError::StaleLease(first.id))
    );

    let replacement = scheduler
        .claim_next(second_slot_id, at(60))
        .expect("replacement claim succeeds")
        .expect("actor was requeued at the lease boundary");
    assert_eq!(replacement.actor_id, actor_id);
    assert!(replacement.fencing_token > first.fencing_token);
    assert_eq!(
        scheduler.finish_lease(
            replacement.id,
            first.fencing_token,
            LeaseOutcome::Completed,
            at(61),
        ),
        Err(SchedulerError::LeaseFenceMismatch {
            lease_id: replacement.id,
            expected: replacement.fencing_token,
            actual: first.fencing_token,
        })
    );
    scheduler
        .finish_lease(
            replacement.id,
            replacement.fencing_token,
            LeaseOutcome::Completed,
            at(61),
        )
        .expect("current fenced lease completes");
}

#[test]
fn lease_expiry_results_are_deterministically_ordered_by_slot_id() {
    let plan_id = Uuid::new_v4();
    let swarm_id = Uuid::new_v4();
    let actors = [Uuid::from_u128(1), Uuid::from_u128(2)]
        .into_iter()
        .map(|actor_id| {
            LogicalActor::from_plan_node(
                swarm_id,
                &node(plan_id, actor_id, PlanNodeKind::Worker, vec![], 2, 300),
            )
        })
        .collect();
    let low_slot_id = Uuid::from_u128(10);
    let high_slot_id = Uuid::from_u128(20);
    let mut scheduler = SwarmScheduler::new(
        swarm_id,
        actors,
        vec![slot(high_slot_id), slot(low_slot_id)],
        60,
    )
    .expect("valid scheduler");
    scheduler
        .claim_next(high_slot_id, at(0))
        .expect("first claim")
        .expect("first actor");
    scheduler
        .claim_next(low_slot_id, at(0))
        .expect("second claim")
        .expect("second actor");
    let expired = scheduler.expire_and_requeue(at(60));
    assert_eq!(
        expired
            .into_iter()
            .map(|item| item.slot_id)
            .collect::<Vec<_>>(),
        vec![low_slot_id, high_slot_id]
    );
}

#[test]
fn heartbeat_renews_only_until_actor_timeout_deadline() {
    let (mut scheduler, _actor_id, first_slot_id, _second_slot_id) = one_actor_scheduler(3, 90, 60);
    let lease = scheduler
        .claim_next(first_slot_id, at(0))
        .expect("claim succeeds")
        .expect("actor available");
    assert_eq!(lease.deadline_at, at(90));
    assert_eq!(lease.expires_at, at(60));
    let renewed = scheduler
        .renew_lease(lease.id, lease.fencing_token, at(50))
        .expect("heartbeat accepted");
    assert_eq!(renewed.heartbeat_at, at(50));
    assert_eq!(renewed.expires_at, at(90));
    assert_eq!(
        scheduler.renew_lease(lease.id, lease.fencing_token, at(90)),
        Err(SchedulerError::LeaseExpired(lease.id))
    );
}

#[test]
fn retry_and_timeout_stop_after_the_declared_attempt_budget() {
    let (mut retry_scheduler, actor_id, first_slot_id, _second_slot_id) =
        one_actor_scheduler(2, 300, 60);
    let first = retry_scheduler
        .claim_next(first_slot_id, at(0))
        .expect("claim succeeds")
        .expect("first attempt");
    retry_scheduler
        .finish_lease(first.id, first.fencing_token, LeaseOutcome::Retry, at(1))
        .expect("first retry is allowed");
    let second = retry_scheduler
        .claim_next(first_slot_id, at(2))
        .expect("claim succeeds")
        .expect("second attempt");
    retry_scheduler
        .finish_lease(second.id, second.fencing_token, LeaseOutcome::Retry, at(3))
        .expect("retry outcome is recorded");
    assert_eq!(
        retry_scheduler.actors[&actor_id].state,
        LogicalActorState::Failed
    );
    assert!(retry_scheduler.actors[&actor_id]
        .terminal_reason
        .as_deref()
        .is_some_and(|reason| reason.contains("attempt_budget_exhausted:2/2")));
    assert!(retry_scheduler
        .claim_next(first_slot_id, at(4))
        .expect("claim query succeeds")
        .is_none());

    let (mut timeout_scheduler, timeout_actor_id, timeout_slot_id, _) =
        one_actor_scheduler(1, 300, 60);
    timeout_scheduler
        .claim_next(timeout_slot_id, at(0))
        .expect("claim succeeds")
        .expect("only attempt");
    let expired = timeout_scheduler.expire_and_requeue(at(60));
    assert_eq!(expired[0].action, LeaseExpiryAction::Failed);
    assert_eq!(
        timeout_scheduler.actors[&timeout_actor_id].state,
        LogicalActorState::Failed
    );
}

fn verifier_plan() -> (SwarmPlan, Uuid, Uuid, Uuid) {
    let plan_id = Uuid::new_v4();
    let worker_id = Uuid::new_v4();
    let reducer_id = Uuid::new_v4();
    let verifier_id = Uuid::new_v4();
    let execution_plan = ExecutionPlan {
        schema_version: 1,
        trace_id: "trace:verifier-gate".into(),
        idempotency_key: "plan:verifier-gate".into(),
        id: plan_id,
        project_id: Uuid::new_v4(),
        workstream_id: Uuid::new_v4(),
        version: 1,
        goal: "complete only after verifier approval".into(),
        nodes: vec![
            node(plan_id, worker_id, PlanNodeKind::Worker, vec![], 1, 60),
            node(
                plan_id,
                reducer_id,
                PlanNodeKind::Reducer,
                vec![worker_id],
                1,
                60,
            ),
            node(
                plan_id,
                verifier_id,
                PlanNodeKind::Verifier,
                vec![reducer_id],
                1,
                60,
            ),
        ],
        created_by: "owner-api".into(),
        created_at: at(0),
    };
    (
        SwarmPlan {
            schema_version: 1,
            trace_id: "trace:verifier-gate".into(),
            idempotency_key: "swarm:verifier-gate".into(),
            id: Uuid::new_v4(),
            requested_logical_actors: 3,
            max_physical_slots: 1,
            external_planner_provider: None,
            formula_tap_required: true,
            reducer_node_ids: vec![reducer_id],
            verifier_node_ids: vec![verifier_id],
            created_at: at(0),
            execution_plan,
        },
        worker_id,
        reducer_id,
        verifier_id,
    )
}

#[test]
fn verifier_verdict_is_required_for_final_plan_completion() {
    let (plan, worker_id, reducer_id, verifier_id) = verifier_plan();
    let slot_id = Uuid::new_v4();
    let mut scheduler =
        SwarmScheduler::from_plan(&plan, vec![slot(slot_id)], 60).expect("valid verifier plan");

    let worker = scheduler
        .claim_next(slot_id, at(0))
        .expect("worker claim")
        .expect("worker ready");
    assert_eq!(worker.actor_id, worker_id);
    scheduler
        .finish_lease(
            worker.id,
            worker.fencing_token,
            LeaseOutcome::Completed,
            at(1),
        )
        .expect("worker completes");
    let reducer = scheduler
        .claim_next(slot_id, at(2))
        .expect("reducer claim")
        .expect("reducer ready");
    assert_eq!(reducer.actor_id, reducer_id);
    scheduler
        .finish_lease(
            reducer.id,
            reducer.fencing_token,
            LeaseOutcome::Completed,
            at(3),
        )
        .expect("reducer completes");
    assert_eq!(scheduler.plan_state(), PlanExecutionState::Verifying);

    let verifier = scheduler
        .claim_next(slot_id, at(4))
        .expect("verifier claim")
        .expect("verifier ready");
    assert_eq!(verifier.actor_id, verifier_id);
    assert_eq!(
        scheduler.finish_lease(
            verifier.id,
            verifier.fencing_token,
            LeaseOutcome::Completed,
            at(5),
        ),
        Err(SchedulerError::VerifierVerdictRequired(verifier.id))
    );
    assert_eq!(scheduler.plan_state(), PlanExecutionState::Verifying);
    assert_eq!(scheduler.snapshot().occupied_slot_count, 1);
    scheduler
        .finish_lease(
            verifier.id,
            verifier.fencing_token,
            LeaseOutcome::VerifierApproved,
            at(5),
        )
        .expect("explicit verifier approval completes the plan");
    assert_eq!(scheduler.plan_state(), PlanExecutionState::Completed);
}

#[test]
fn failed_dependency_blocks_all_downstream_nodes_with_a_reason() {
    let (plan, worker_id, reducer_id, verifier_id) = verifier_plan();
    let slot_id = Uuid::new_v4();
    let mut scheduler =
        SwarmScheduler::from_plan(&plan, vec![slot(slot_id)], 60).expect("valid verifier plan");
    let worker = scheduler
        .claim_next(slot_id, at(0))
        .expect("worker claim")
        .expect("worker ready");
    scheduler
        .finish_lease(worker.id, worker.fencing_token, LeaseOutcome::Failed, at(1))
        .expect("failure recorded");

    assert_eq!(
        scheduler.actors[&worker_id].state,
        LogicalActorState::Failed
    );
    assert_eq!(
        scheduler.actors[&reducer_id].state,
        LogicalActorState::Blocked
    );
    assert_eq!(
        scheduler.actors[&verifier_id].state,
        LogicalActorState::Blocked
    );
    assert!(scheduler.actors[&reducer_id]
        .terminal_reason
        .as_deref()
        .is_some_and(|reason| reason.contains(&worker_id.to_string())));
    assert!(scheduler.actors[&verifier_id]
        .terminal_reason
        .as_deref()
        .is_some_and(|reason| reason.contains(&reducer_id.to_string())));
    assert_eq!(scheduler.plan_state(), PlanExecutionState::Failed);
}
