use chrono::{DateTime, Utc};
use kolibri_core::{
    AcceptanceAssertion, ExecutionPlan, LeaseOutcome, LogicalActorState, PlanExecutionState,
    PlanNode, PlanNodeKind, PlanNodeState, PlatformRequirement, ResourceCapacity, ResourceRequest,
    ResourceSlot, SchedulerError, SlotPlatform, SwarmPlan, SwarmScheduler,
};
use serde_json::json;
use std::collections::BTreeSet;
use uuid::Uuid;

fn at(seconds: i64) -> DateTime<Utc> {
    DateTime::from_timestamp(seconds, 0).expect("valid fixture timestamp")
}

fn plan_node(
    plan_id: Uuid,
    kind: PlanNodeKind,
    dependencies: Vec<Uuid>,
    critical_path_weight: u32,
) -> PlanNode {
    PlanNode {
        id: Uuid::new_v4(),
        plan_id,
        name: format!("{kind:?}"),
        kind,
        state: if dependencies.is_empty() {
            PlanNodeState::Ready
        } else {
            PlanNodeState::WaitingDependencies
        },
        dependencies,
        capability: "build_app".into(),
        input_schema: json!({"type":"object"}),
        output_schema: json!({"type":"object"}),
        acceptance: vec![AcceptanceAssertion {
            id: "evidence".into(),
            assertion_type: "artifact_exists".into(),
            expression: "result.manifest".into(),
            evidence_artifact_type: Some("manifest".into()),
        }],
        resource_request: ResourceRequest {
            platform: PlatformRequirement::Ubuntu,
            capability: "build_app".into(),
            cpu_millis: 250,
            memory_bytes: 64 * 1024 * 1024,
            disk_bytes: 16 * 1024 * 1024,
            gpu_required: false,
        },
        sandbox_profile: "worktree-default-deny".into(),
        max_attempts: 2,
        timeout_seconds: 300,
        critical_path_weight,
    }
}

fn slot() -> ResourceSlot {
    ResourceSlot {
        id: Uuid::new_v4(),
        node_id: "ubuntu-worker".into(),
        platform: SlotPlatform::Ubuntu,
        capabilities: vec!["build_app".into()],
        capacity: ResourceCapacity {
            cpu_millis: 1_000,
            memory_bytes: 512 * 1024 * 1024,
            disk_bytes: 1024 * 1024 * 1024,
            gpu_available: false,
        },
        active_lease: None,
        enabled: true,
    }
}

#[test]
fn one_thousand_logical_actors_use_bounded_slots_without_duplicate_claims() {
    let execution_plan_id = Uuid::new_v4();
    let mut nodes = Vec::with_capacity(1_000);
    for _ in 0..998 {
        nodes.push(plan_node(
            execution_plan_id,
            PlanNodeKind::Mapper,
            vec![],
            10,
        ));
    }
    let mapper_ids: Vec<_> = nodes.iter().map(|node| node.id).collect();
    let reducer = plan_node(execution_plan_id, PlanNodeKind::Reducer, mapper_ids, 100);
    let reducer_id = reducer.id;
    nodes.push(reducer);
    let verifier = plan_node(
        execution_plan_id,
        PlanNodeKind::Verifier,
        vec![reducer_id],
        200,
    );
    let verifier_id = verifier.id;
    nodes.push(verifier);

    let execution_plan = ExecutionPlan {
        schema_version: 1,
        trace_id: "trace:1000-actors".into(),
        idempotency_key: "plan:1000-actors".into(),
        id: execution_plan_id,
        project_id: Uuid::new_v4(),
        workstream_id: Uuid::new_v4(),
        version: 1,
        goal: "build app using 1000 durable logical actors".into(),
        nodes,
        created_by: "owner-api".into(),
        created_at: at(1),
    };
    let swarm_plan = SwarmPlan {
        schema_version: 1,
        trace_id: "trace:1000-actors".into(),
        idempotency_key: "swarm:1000-actors".into(),
        id: Uuid::new_v4(),
        execution_plan,
        requested_logical_actors: 1_000,
        max_physical_slots: 8,
        external_planner_provider: Some("mimo-auto-2.5".into()),
        formula_tap_required: true,
        reducer_node_ids: vec![reducer_id],
        verifier_node_ids: vec![verifier_id],
        created_at: at(1),
    };
    let actors = swarm_plan.materialize_actors();
    assert_eq!(actors.len(), 1_000);
    swarm_plan.validate().expect("valid swarm plan");
    assert!(matches!(
        SwarmScheduler::from_plan(&swarm_plan, (0..9).map(|_| slot()).collect(), 60),
        Err(SchedulerError::TooManySlots {
            configured: 9,
            maximum: 8
        })
    ));
    let slots: Vec<_> = (0..8).map(|_| slot()).collect();
    let slot_ids: Vec<_> = slots.iter().map(|slot| slot.id).collect();
    let mut scheduler =
        SwarmScheduler::from_plan(&swarm_plan, slots, 60).expect("valid scheduler state");

    let initial = scheduler.snapshot();
    assert_eq!(initial.logical_actor_count, 1_000);
    assert_eq!(initial.physical_slot_count, 8);
    assert_eq!(initial.spawned_actor_processes, 0);
    assert_eq!(initial.ready_actor_count, 998);

    let mut claimed_actor_ids = BTreeSet::new();
    let mut clock = 10;
    while scheduler
        .actors
        .values()
        .filter(|actor| actor.kind == PlanNodeKind::Mapper)
        .any(|actor| actor.state != LogicalActorState::Completed)
    {
        let mut batch = Vec::new();
        for slot_id in &slot_ids {
            if let Some(lease) = scheduler
                .claim_next(*slot_id, at(clock))
                .expect("claim succeeds")
            {
                assert!(claimed_actor_ids.insert(lease.actor_id));
                batch.push(lease);
            }
        }
        assert!(scheduler.snapshot().active_actor_count <= 8);
        assert!(scheduler.snapshot().occupied_slot_count <= 8);
        assert!(!batch.is_empty());
        for lease in batch {
            scheduler
                .finish_lease(
                    lease.id,
                    lease.fencing_token,
                    LeaseOutcome::Completed,
                    at(clock + 1),
                )
                .expect("complete lease");
        }
        clock += 2;
    }

    let reducer_lease = scheduler
        .claim_next(slot_ids[0], at(clock))
        .expect("reducer claim")
        .expect("reducer ready");
    assert_eq!(reducer_lease.actor_id, reducer_id);
    assert_eq!(
        scheduler.actors[&reducer_id].state,
        LogicalActorState::Reducing
    );
    assert!(claimed_actor_ids.insert(reducer_lease.actor_id));
    scheduler
        .finish_lease(
            reducer_lease.id,
            reducer_lease.fencing_token,
            LeaseOutcome::Completed,
            at(clock + 1),
        )
        .expect("reducer complete");
    assert_eq!(scheduler.plan_state(), PlanExecutionState::Verifying);

    let verifier_lease = scheduler
        .claim_next(slot_ids[0], at(clock + 2))
        .expect("verifier claim")
        .expect("verifier ready");
    assert_eq!(verifier_lease.actor_id, verifier_id);
    assert_eq!(
        scheduler.actors[&verifier_id].state,
        LogicalActorState::Verifying
    );
    assert!(claimed_actor_ids.insert(verifier_lease.actor_id));

    assert!(scheduler.claim_next(slot_ids[0], at(clock + 2)).is_err());
    scheduler
        .finish_lease(
            verifier_lease.id,
            verifier_lease.fencing_token,
            LeaseOutcome::VerifierApproved,
            at(clock + 3),
        )
        .expect("verifier complete");

    let final_snapshot = scheduler.snapshot();
    assert_eq!(claimed_actor_ids.len(), 1_000);
    assert_eq!(final_snapshot.terminal_actor_count, 1_000);
    assert_eq!(final_snapshot.occupied_slot_count, 0);
    assert_eq!(final_snapshot.spawned_actor_processes, 0);
    assert_eq!(final_snapshot.plan_state, PlanExecutionState::Completed);
}

#[test]
fn apple_work_never_leases_to_an_ubuntu_slot() {
    let plan_id = Uuid::new_v4();
    let mut node = plan_node(plan_id, PlanNodeKind::Worker, vec![], 1);
    node.resource_request.platform = PlatformRequirement::MacApple;
    let actor = kolibri_core::LogicalActor::from_plan_node(Uuid::new_v4(), &node);
    let ubuntu_slot = slot();
    let ubuntu_slot_id = ubuntu_slot.id;
    let mut scheduler = SwarmScheduler::new(Uuid::new_v4(), vec![actor], vec![ubuntu_slot], 60)
        .expect("valid scheduler");
    assert!(scheduler
        .claim_next(ubuntu_slot_id, at(1))
        .expect("claim query")
        .is_none());
}
