use kolibri_nano::*;
use kolibri_nano::traces::TraceType;
use kolibri_nano::estimate_engine::EstimateEngine;

#[test]
fn test_full_workflow() {
    let mut core = KolibriCore::new("user1");

    core.add_trace(TraceType::Preference, "Prefers tables in responses");
    core.add_trace(TraceType::Estimate, "Created room estimate 18m2");
    core.learn_from_result("Estimate saved successfully", true, true);

    let ctx = core.prepare_context_for_llm(10);
    assert!(ctx.contains("Prefers tables"));

    let conf = core.get_confidence();
    assert!(conf.value > 0.5);

    let mut est = core.create_estimate("Repair room 18m2");
    EstimateEngine::add_work_item(&mut est, "Plaster walls", "m2", 50.0, 350.0);
    EstimateEngine::add_work_item(&mut est, "Paint ceiling", "m2", 18.0, 250.0);
    EstimateEngine::add_material_item(&mut est, "Plaster mix 25kg", "bag", 4.0, 450.0);

    assert_eq!(est.item_count(), 3);
    assert!(est.totals.grand_total > 0.0);

    let json = EstimateEngine::to_json(&est);
    assert!(json.contains("Repair room 18m2"));
    let restored = EstimateEngine::from_json(&json).unwrap();
    assert_eq!(restored.item_count(), 3);
}

#[test]
fn test_personal_core_evolution() {
    let mut core = KolibriCore::new("test_user");
    let initial_digits = core.personal_core.digit_string();

    for _ in 0..5 {
        core.learn_from_result("Precise estimate created", true, true);
    }
    assert!(core.personal_core.precision > 0.5);
    assert!(core.personal_core.trust_level > 0.5);
    assert_ne!(core.personal_core.digit_string(), initial_digits);
}
