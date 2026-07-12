use kolibri_core::{
    TaskShadowError, TaskTraceFixture, canonical_json_sha256, completion_binding_sha256,
};
use serde_json::Value;

const FIXTURE: &str =
    include_str!("../../../contracts/kolibri-os-v1/fixtures/task-lifecycle-parity.json");

fn fixture() -> TaskTraceFixture {
    serde_json::from_str(FIXTURE).expect("shared Python/Rust parity fixture is valid JSON")
}

#[test]
fn rust_shadow_replays_the_shared_python_task_trace() {
    let fixture = fixture();
    let summary = fixture.assert_expected().expect("fixture must match");
    assert!(!summary.authoritative);
    assert_eq!(summary.mode, "shadow_parity");
    assert_eq!(summary.authority, "python-control-plane");
    assert_eq!(summary.attempts_started, 2);
    assert_eq!(summary.rejected_stale_completions, 1);
    assert_eq!(summary.verifier_verdict, "passed");
}

#[test]
fn completion_hash_and_attempt_binding_match_the_python_contract() {
    let fixture = fixture();
    let completion = fixture.events.last().expect("completion event");
    let result = completion.result.as_ref().expect("result");
    let result_hash = canonical_json_sha256(result).expect("result hash");
    assert_eq!(
        result_hash,
        "sha256:b33cca88fa7138e7097a56da0cdeadfb891db3b5162be4eacdcb520e219d5c2a"
    );
    let binding_hash = completion_binding_sha256(
        &fixture.task.task_id,
        completion.attempt_id.as_deref().expect("attempt id"),
        completion.lease_owner.as_deref().expect("lease owner"),
        completion.fencing_token.expect("fencing token"),
        completion
            .result_reference
            .as_deref()
            .expect("result reference"),
        &result_hash,
    )
    .expect("binding hash");
    assert_eq!(
        binding_hash,
        "sha256:c5078bd5078b6dc35b0fea806749374326ee2fa02c0705ae5ce45e7af3da6cb3"
    );
}

#[test]
fn matching_current_completion_cannot_be_recorded_as_stale() {
    let mut fixture = fixture();
    let active = fixture.events[4].clone();
    let rejected = &mut fixture.events[5];
    rejected.attempt_id = active.attempt_id;
    rejected.lease_owner = active.lease_owner;
    rejected.fencing_token = active.fencing_token;
    assert!(matches!(
        fixture.replay(),
        Err(TaskShadowError::MatchingCompletionWasRejected)
    ));
}

#[test]
fn trace_hash_covers_event_payload_and_order() {
    let fixture = fixture();
    let original = fixture.replay().expect("original trace").trace_sha256;
    let mut events: Value = serde_json::to_value(&fixture.events).expect("events");
    events[6]["result"]["output"] = Value::String("tampered".to_string());
    assert_ne!(
        original,
        canonical_json_sha256(&events).expect("tampered trace hash")
    );
}

#[test]
fn completion_requires_the_current_numeric_fencing_token_everywhere() {
    let mut stale_event = fixture();
    stale_event.events[6].fencing_token = Some(1);
    assert!(matches!(
        stale_event.replay(),
        Err(TaskShadowError::FenceRejected("fencing_token_mismatch"))
    ));

    let mut stale_result = fixture();
    stale_result.events[6].result.as_mut().expect("result")["fencing_token"] = Value::from(1_u64);
    assert!(matches!(
        stale_result.replay(),
        Err(TaskShadowError::CompletionFieldMismatch("fencing_token"))
    ));

    let mut stale_verifier = fixture();
    stale_verifier.events[6]
        .verifier
        .as_mut()
        .expect("verifier")
        .fencing_token = 1;
    assert!(matches!(
        stale_verifier.replay(),
        Err(TaskShadowError::InvalidVerifier("fencing_token"))
    ));
}
