use chrono::{TimeZone, Utc};
use jsonschema::{Draft, Validator};
use kolibri_core::{
    AcceptanceAssertion, DurableHomeEventStore, EventAuthorityStatus, EventDraft, EventEnvelope,
    EventProvenance, ExecutionPlan, HomeAppendCredential, HomeAuthorityConfig, LogicalActor,
    LogicalActorState, PlanNode, PlanNodeKind, PlanNodeState, PlatformRequirement,
    ResourceCapacity, ResourceRequest, ResourceSlot, SlotPlatform, SwarmPlan, SwarmScheduler,
    V1ActorState, V1ApprovalPolicy, V1LogicalActor, V1PlanNodeKind, V1PlanNodeState,
    V1ResourceClass, V1SchedulerProjection, V1SwarmPlan, V1SwarmPlanState,
};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;
use uuid::Uuid;

const FROZEN_SCHEMA_SHA256: &str =
    "9469bf876a4a0624ece720d602a435af4836a3fb3d20a1d22851b5161e4ca8d9";
const TOKEN: &[u8] = b"0123456789abcdef0123456789abcdef";

fn at(seconds: i64) -> chrono::DateTime<Utc> {
    Utc.timestamp_opt(1_783_641_600 + seconds, 0)
        .single()
        .expect("valid timestamp")
}

fn schema_validator() -> Validator {
    let source = include_str!("fixtures/domain.schema.json");
    assert_eq!(
        format!("{:x}", Sha256::digest(source.as_bytes())),
        FROZEN_SCHEMA_SHA256
    );
    let schema: Value = serde_json::from_str(source).expect("frozen schema is JSON");
    jsonschema::options()
        .with_draft(Draft::Draft202012)
        .build(&schema)
        .expect("frozen schema compiles")
}

#[test]
fn home_control_plane_machine_schema_compiles_as_draft_2020_12() {
    let source = include_str!("../../../contracts/kolibri-os-v1/control-plane.schema.json");
    let schema: Value = serde_json::from_str(source).expect("control-plane schema is JSON");
    jsonschema::options()
        .with_draft(Draft::Draft202012)
        .build(&schema)
        .expect("control-plane schema compiles");
    assert_eq!(schema["x-kolibri-authority"], "control-plane/home");
}

fn assert_matches_frozen_schema(value: &Value) {
    let validator = schema_validator();
    if let Err(error) = validator.validate(value) {
        panic!("serialized DTO does not match frozen domain.schema.json: {error}; value={value}");
    }
}

fn test_directory() -> PathBuf {
    std::env::temp_dir().join(format!("kolibri-v1-contract-{}", Uuid::new_v4()))
}

fn plan_node(plan_id: Uuid, node_id: Uuid, kind: PlanNodeKind) -> PlanNode {
    PlanNode {
        id: node_id,
        plan_id,
        name: "verify the frozen V1 contract".to_string(),
        kind,
        state: PlanNodeState::Ready,
        dependencies: Vec::new(),
        capability: "rust-build".to_string(),
        input_schema: json!({}),
        output_schema: json!({}),
        acceptance: vec![AcceptanceAssertion {
            id: "accept-1".to_string(),
            assertion_type: "test".to_string(),
            expression: "cargo test --workspace".to_string(),
            evidence_artifact_type: Some("test-report".to_string()),
        }],
        resource_request: ResourceRequest {
            platform: PlatformRequirement::Any,
            capability: "rust-build".to_string(),
            cpu_millis: 500,
            memory_bytes: 512 * 1024 * 1024,
            disk_bytes: 1024 * 1024 * 1024,
            gpu_required: false,
        },
        sandbox_profile: "build".to_string(),
        max_attempts: 2,
        timeout_seconds: 300,
        critical_path_weight: 1,
    }
}

fn internal_plan() -> SwarmPlan {
    let execution_plan_id = Uuid::parse_str("44444444-4444-4444-8444-444444444444").unwrap();
    let node_id = Uuid::parse_str("55555555-5555-4555-8555-555555555555").unwrap();
    SwarmPlan {
        schema_version: 1,
        trace_id: "trace:plan-001".to_string(),
        idempotency_key: "swarm:create:1".to_string(),
        id: Uuid::parse_str("88888888-8888-4888-8888-888888888888").unwrap(),
        execution_plan: ExecutionPlan {
            schema_version: 1,
            trace_id: "trace:plan-001".to_string(),
            idempotency_key: "plan:create:1".to_string(),
            id: execution_plan_id,
            project_id: Uuid::parse_str("66666666-6666-4666-8666-666666666666").unwrap(),
            workstream_id: Uuid::parse_str("77777777-7777-4777-8777-777777777777").unwrap(),
            version: 1,
            goal: "prove field-by-field wire compatibility".to_string(),
            nodes: vec![plan_node(
                execution_plan_id,
                node_id,
                PlanNodeKind::Verifier,
            )],
            created_by: "planner".to_string(),
            created_at: at(1),
        },
        requested_logical_actors: 1,
        max_physical_slots: 1,
        external_planner_provider: None,
        formula_tap_required: true,
        reducer_node_ids: Vec::new(),
        verifier_node_ids: vec![node_id],
        created_at: at(2),
    }
}

#[test]
fn copied_schema_fixture_is_checksum_pinned() {
    let source = include_bytes!("fixtures/domain.schema.json");
    assert_eq!(
        format!("{:x}", Sha256::digest(source)),
        FROZEN_SCHEMA_SHA256
    );
    assert_eq!(
        include_str!("fixtures/domain.schema.sha256").trim(),
        FROZEN_SCHEMA_SHA256
    );
}

#[test]
fn authoritative_event_is_allocated_persisted_and_schema_validated() {
    let directory = test_directory();
    let authority = HomeAuthorityConfig::new("home-control-plane", TOKEN).unwrap();
    let store = DurableHomeEventStore::open(&directory, authority).unwrap();
    let mut draft = EventDraft::new(
        "provider.attempt.failed",
        "response:resp-001",
        "trace:001",
        json!({"reason":"timeout"}),
        EventProvenance::v1("gateway", "v1"),
        at(0),
    );
    draft.idempotency_key = "response:resp-001:provider-attempt-1".to_string();
    let event = store
        .append(draft, &HomeAppendCredential::new(TOKEN))
        .unwrap();
    assert_eq!(event.source(), "control-plane/home");
    assert_eq!(event.sequence(), 1);
    assert_eq!(
        event.envelope().authority.status,
        EventAuthorityStatus::Authoritative
    );
    assert_eq!(
        event.envelope().provenance.node_id.as_deref(),
        Some("home-control-plane")
    );
    let wire = serde_json::to_value(&event).unwrap();
    assert_eq!(wire["schema_version"], "kolibri.event.v1");
    assert_eq!(wire["type"], "provider.attempt.failed");
    assert_eq!(wire["data"], json!({"reason":"timeout"}));
    assert_matches_frozen_schema(&wire);
    assert_eq!(store.read_verified().unwrap(), vec![event]);
    fs::remove_dir_all(directory).unwrap();
}

#[test]
fn legacy_missing_sequence_is_untrusted_migration_evidence_not_authority() {
    let legacy = json!({
        "schema_version": 1,
        "id": "22222222-2222-4222-8222-222222222222",
        "stream": "kolibri-events",
        "subject": "kolibri.task",
        "event_type": "task.created",
        "aggregate_id": null,
        "payload_json": {"task_id":"task-legacy"},
        "trace_id": "trace:legacy",
        "idempotency_key": "event:legacy",
        "correlation_id": null,
        "actor": "legacy-control-plane",
        "created_at": "2026-07-10T00:00:00Z"
    });
    let event: EventEnvelope = serde_json::from_value(legacy).unwrap();
    assert_eq!(
        event.sequence, 0,
        "missing sequence is never fabricated as one"
    );
    assert_eq!(
        event.authority.status,
        EventAuthorityStatus::UntrustedMigration
    );
    assert!(event.validate_contract().is_err());
    event.validate_migration_evidence().unwrap();
    assert!(!event.is_authoritative_claim());
    assert!(
        schema_validator()
            .validate(&serde_json::to_value(event).unwrap())
            .is_err()
    );
}

#[test]
fn swarm_plan_uses_a_separate_field_exact_v1_dto() {
    let plan = internal_plan();
    let internal_wire = serde_json::to_value(&plan).unwrap();
    assert_eq!(internal_wire["schema_version"], 1);
    assert!(internal_wire.get("execution_plan").is_some());

    let mut limits = BTreeMap::new();
    limits.insert("build".to_string(), 21);
    let dto = V1SwarmPlan::from_plan_definition(&plan, V1SwarmPlanState::Queued, limits).unwrap();
    let wire = serde_json::to_value(&dto).unwrap();
    assert_eq!(wire["schema_version"], "kolibri.swarm-plan.v1");
    assert_eq!(wire["objective"], "prove field-by-field wire compatibility");
    assert_eq!(wire["nodes"][0]["kind"], "verifier");
    assert_eq!(wire["nodes"][0]["resources"][0]["class"], "build");
    assert_eq!(wire["nodes"][0]["retry_policy"]["max_attempts"], 2);
    assert_matches_frozen_schema(&wire);
}

#[test]
fn logical_actor_dto_contains_array_mailbox_checkpoint_capabilities_and_class() {
    let plan = internal_plan();
    let mut actor = LogicalActor::from_plan_node_at(plan.id, &plan.execution_plan.nodes[0], at(3));
    actor
        .mailbox
        .enqueue_once(
            actor.id,
            kolibri_core::ActorMessageKind::Input,
            json!({"artifact_id":"artifact-001"}),
            "trace:actor-001",
            "mailbox:actor-001:1",
            at(4),
        )
        .unwrap();
    let internal_wire = serde_json::to_value(&actor).unwrap();
    assert!(internal_wire.get("schema_version").is_none());
    assert!(internal_wire["mailbox"].is_object());

    let dto = V1LogicalActor::from_scheduler(&actor).unwrap();
    let wire = serde_json::to_value(&dto).unwrap();
    assert_eq!(wire["schema_version"], "kolibri.actor.v1");
    assert_eq!(wire["actor_class"], "verifier");
    assert_eq!(wire["capabilities"], json!(["rust-build"]));
    assert!(wire["mailbox"].is_array());
    assert_eq!(wire["mailbox"][0]["sequence"], 1);
    assert!(wire["checkpoint"].is_object());
    assert_matches_frozen_schema(&wire);

    let worker_plan_id = Uuid::new_v4();
    let worker_node = plan_node(worker_plan_id, Uuid::new_v4(), PlanNodeKind::Worker);
    let worker_actor = LogicalActor::from_plan_node_at(Uuid::new_v4(), &worker_node, at(5));
    let slot = ResourceSlot {
        id: Uuid::new_v4(),
        node_id: "ubuntu-worker".to_string(),
        platform: SlotPlatform::Ubuntu,
        capabilities: vec!["rust-build".to_string()],
        capacity: ResourceCapacity {
            cpu_millis: 1_000,
            memory_bytes: 1024 * 1024 * 1024,
            disk_bytes: 1024 * 1024 * 1024,
            gpu_available: false,
        },
        active_lease: None,
        enabled: true,
    };
    let slot_id = slot.id;
    let actor_id = worker_actor.id;
    let mut scheduler =
        SwarmScheduler::new(Uuid::new_v4(), vec![worker_actor], vec![slot], 60).unwrap();
    scheduler.claim_next(slot_id, at(6)).unwrap().unwrap();
    let running = V1LogicalActor::from_scheduler(&scheduler.actors[&actor_id]).unwrap();
    assert_eq!(running.state, V1ActorState::Running);
}

#[test]
fn runtime_plan_projection_comes_from_leases_and_scheduler_state() {
    let plan = internal_plan();
    let slot = ResourceSlot {
        id: Uuid::new_v4(),
        node_id: "ubuntu-verifier".to_string(),
        platform: SlotPlatform::Ubuntu,
        capabilities: vec!["rust-build".to_string()],
        capacity: ResourceCapacity {
            cpu_millis: 1_000,
            memory_bytes: 1024 * 1024 * 1024,
            disk_bytes: 1024 * 1024 * 1024,
            gpu_available: false,
        },
        active_lease: None,
        enabled: true,
    };
    let slot_id = slot.id;
    let mut scheduler = SwarmScheduler::from_plan(&plan, vec![slot], 60).unwrap();
    let lease = scheduler.claim_next(slot_id, at(7)).unwrap().unwrap();
    let mut limits = BTreeMap::new();
    limits.insert("build".to_string(), 1);
    let runtime = V1SwarmPlan::from_runtime(&plan, &scheduler, limits).unwrap();
    assert_eq!(runtime.state, V1SwarmPlanState::Verifying);
    assert_eq!(runtime.nodes[0].state, V1PlanNodeState::Review);
    assert_eq!(
        runtime.nodes[0].attempt_id.as_deref(),
        Some(lease.id.to_string().as_str())
    );
    assert_eq!(
        runtime.nodes[0].lease_owner.as_deref(),
        Some(slot_id.to_string().as_str())
    );
    assert_matches_frozen_schema(&serde_json::to_value(runtime).unwrap());
}

#[test]
fn every_frozen_state_and_kind_is_serializable_and_schema_accepted() {
    let plan = internal_plan();
    let mut limits = BTreeMap::new();
    limits.insert("cpu".to_string(), 21);
    let base = V1SwarmPlan::from_plan_definition(&plan, V1SwarmPlanState::Draft, limits).unwrap();
    let plan_states = [
        V1SwarmPlanState::Draft,
        V1SwarmPlanState::Queued,
        V1SwarmPlanState::Running,
        V1SwarmPlanState::Verifying,
        V1SwarmPlanState::Completed,
        V1SwarmPlanState::Failed,
        V1SwarmPlanState::Cancelled,
    ];
    for state in plan_states {
        let _projection = state.scheduler_projection();
        let mut dto = base.clone();
        dto.state = state;
        assert_matches_frozen_schema(&serde_json::to_value(dto).unwrap());
    }

    let kinds = [
        V1PlanNodeKind::Planner,
        V1PlanNodeKind::Worker,
        V1PlanNodeKind::Reducer,
        V1PlanNodeKind::Verifier,
        V1PlanNodeKind::Approval,
        V1PlanNodeKind::Release,
    ];
    let node_states = [
        V1PlanNodeState::Pending,
        V1PlanNodeState::Ready,
        V1PlanNodeState::Leased,
        V1PlanNodeState::Running,
        V1PlanNodeState::Review,
        V1PlanNodeState::Retry,
        V1PlanNodeState::Blocked,
        V1PlanNodeState::Completed,
        V1PlanNodeState::Dead,
        V1PlanNodeState::Cancelled,
    ];
    for (index, kind) in kinds.into_iter().enumerate() {
        let _projection = kind.scheduler_projection();
        let mut dto = base.clone();
        dto.nodes[0].kind = kind;
        dto.nodes[0].state = node_states[index];
        assert_matches_frozen_schema(&serde_json::to_value(dto).unwrap());
    }
    for state in node_states {
        let _projection = state.scheduler_projection();
        let mut dto = base.clone();
        dto.nodes[0].state = state;
        assert_matches_frozen_schema(&serde_json::to_value(dto).unwrap());
    }

    let actor_states = [
        V1ActorState::Idle,
        V1ActorState::Runnable,
        V1ActorState::Leased,
        V1ActorState::Running,
        V1ActorState::Checkpointing,
        V1ActorState::Waiting,
        V1ActorState::Failed,
        V1ActorState::Stopped,
    ];
    let actor = LogicalActor::from_plan_node_at(plan.id, &plan.execution_plan.nodes[0], at(3));
    let base_actor = V1LogicalActor::from_scheduler(&actor).unwrap();
    for state in actor_states {
        let _projection = state.scheduler_projection();
        let mut dto = base_actor.clone();
        dto.state = state;
        assert_matches_frozen_schema(&serde_json::to_value(dto).unwrap());
    }

    assert!(matches!(
        V1PlanNodeKind::Approval.scheduler_projection(),
        V1SchedulerProjection::Unsupported { .. }
    ));
    assert!(matches!(
        V1PlanNodeState::Leased.scheduler_projection(),
        V1SchedulerProjection::Transitional { .. }
    ));
    assert!(matches!(
        V1ActorState::Checkpointing.scheduler_projection(),
        V1SchedulerProjection::Transitional { .. }
    ));
    assert!(matches!(
        V1SwarmPlanState::Queued.scheduler_projection(),
        V1SchedulerProjection::Unsupported { .. }
    ));
}

#[test]
fn all_frozen_resource_and_approval_enums_serialize_exactly() {
    let resources = [
        (V1ResourceClass::Cpu, "cpu"),
        (V1ResourceClass::Memory, "memory"),
        (V1ResourceClass::Model, "model"),
        (V1ResourceClass::Browser, "browser"),
        (V1ResourceClass::Build, "build"),
        (V1ResourceClass::AppleBuild, "apple-build"),
        (V1ResourceClass::Gpu, "gpu"),
        (V1ResourceClass::Network, "network"),
    ];
    for (value, expected) in resources {
        assert_eq!(serde_json::to_value(value).unwrap(), expected);
    }
    assert_eq!(
        serde_json::to_value(V1ApprovalPolicy::None).unwrap(),
        "none"
    );
    assert_eq!(
        serde_json::to_value(V1ApprovalPolicy::Owner).unwrap(),
        "owner"
    );
    assert_eq!(
        serde_json::to_value(V1ApprovalPolicy::Security).unwrap(),
        "security"
    );
    assert_eq!(
        serde_json::to_value(V1ApprovalPolicy::Financial).unwrap(),
        "financial"
    );
    assert_eq!(
        serde_json::to_value(V1ApprovalPolicy::Production).unwrap(),
        "production"
    );
}

#[test]
fn identifier_pattern_and_length_are_enforced_before_serialized_boundary() {
    let plan = internal_plan();
    let mut limits = BTreeMap::new();
    limits.insert("cpu".to_string(), 1);
    let mut dto =
        V1SwarmPlan::from_plan_definition(&plan, V1SwarmPlanState::Queued, limits).unwrap();
    dto.trace_id = "bad/id".to_string();
    assert!(dto.validate().is_err());
    assert!(
        schema_validator()
            .validate(&serde_json::to_value(dto).unwrap())
            .is_err()
    );

    assert_eq!(
        V1PlanNodeState::from(PlanNodeState::Verifying),
        V1PlanNodeState::Review
    );
    assert_eq!(
        V1ActorState::from(LogicalActorState::Reducing),
        V1ActorState::Running
    );
}
