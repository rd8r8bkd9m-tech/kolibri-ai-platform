use kolibri_estimates::{EstimateInput, VerifyRequest, calculate, verify};
use serde_json::{Value, json};

fn parse_input(value: Value) -> EstimateInput {
    serde_json::from_value(value).expect("valid estimate fixture")
}

#[test]
fn rounds_each_line_half_up_before_subtotal() {
    let calculation = calculate(parse_input(json!({
        "overhead_rate": "0",
        "vat_rate": "0",
        "sections": [{
            "positions": [
                {"quantity": "1", "price": "0.005"},
                {"quantity": "3", "price": "1.005"}
            ]
        }]
    })))
    .expect("calculation succeeds");

    assert_eq!(calculation.result.sections[0].positions[0].sum, "0.01");
    assert_eq!(calculation.result.sections[0].positions[1].sum, "3.02");
    assert_eq!(calculation.result.sections[0].subtotal, "3.03");
    assert_eq!(calculation.result.subtotal, "3.03");
    assert_eq!(calculation.result.total, "3.03");
}

#[test]
fn applies_overhead_then_vat_with_independent_half_up_rounding() {
    let calculation = calculate(parse_input(json!({
        "overhead_rate": "10",
        "vat_rate": "20",
        "sections": [{"positions": [
            {"quantity": "1", "price": "3.03"}
        ]}]
    })))
    .expect("calculation succeeds");

    assert_eq!(calculation.result.subtotal, "3.03");
    assert_eq!(calculation.result.overhead_amount, "0.30");
    assert_eq!(calculation.result.vat_amount, "0.67");
    assert_eq!(calculation.result.total, "4.00");
}

#[test]
fn supports_values_far_beyond_fixed_width_integers() {
    let huge = "9".repeat(200);
    let calculation = calculate(parse_input(json!({
        "sections": [{"positions": [
            {"quantity": huge, "price": "1"}
        ]}]
    })))
    .expect("BigInt calculation succeeds");

    assert_eq!(
        calculation.result.subtotal,
        format!("{}.00", "9".repeat(200))
    );
    assert_eq!(calculation.result.total, format!("{}.00", "9".repeat(200)));
}

#[test]
fn rejects_negative_invalid_and_overlong_decimals_with_paths() {
    for (raw, expected_code) in [
        ("-0", "negative_decimal"),
        ("NaN", "invalid_decimal"),
        ("1e3", "invalid_decimal"),
        ("1,5", "invalid_decimal"),
    ] {
        let error = calculate(parse_input(json!({
            "sections": [{"positions": [
                {"quantity": raw, "price": "1"}
            ]}]
        })))
        .expect_err("invalid decimal must be rejected");
        assert_eq!(error.issue().code, expected_code);
        assert_eq!(error.issue().path, "sections[0].positions[0].quantity");
    }

    let overlong = "1".repeat(4_097);
    let error = calculate(parse_input(json!({
        "sections": [{"positions": [
            {"quantity": "1", "price": overlong}
        ]}]
    })))
    .expect_err("overlong decimal must be rejected");
    assert_eq!(error.issue().code, "decimal_too_long");
    assert_eq!(error.issue().path, "sections[0].positions[0].price");
}

#[test]
fn canonical_hashes_are_semantic_and_region_sensitive() {
    let first = calculate(parse_input(json!({
        "region": "Удмуртская Республика",
        "overhead_rate": "01.00",
        "sections": [{"positions": [
            {"quantity": "03.0", "price": "1.00500"}
        ]}]
    })))
    .expect("first calculation");
    let same = calculate(parse_input(json!({
        "sections": [{"positions": [
            {"price": "1.005", "quantity": "3"}
        ]}],
        "overhead_rate": "1",
        "region": "Удмуртская Республика"
    })))
    .expect("second calculation");
    assert_eq!(first.input_sha256, same.input_sha256);
    assert_eq!(first.result_sha256, same.result_sha256);

    let other_region = calculate(parse_input(json!({
        "region": "Республика Татарстан",
        "overhead_rate": "1",
        "sections": [{"positions": [
            {"quantity": "3", "price": "1.005"}
        ]}]
    })))
    .expect("other-region calculation");
    assert_ne!(first.input_sha256, other_region.input_sha256);
}

#[test]
fn verification_recalculates_instead_of_trusting_totals() {
    let input = parse_input(json!({
        "sections": [{"positions": [
            {"quantity": "3", "price": "1.005"}
        ]}]
    }));
    let calculation = calculate(input.clone()).expect("calculation succeeds");
    let exact = verify(VerifyRequest {
        input: input.clone(),
        result: calculation.result.clone(),
        input_sha256: Some(calculation.input_sha256.clone()),
        result_sha256: Some(calculation.result_sha256.clone()),
    })
    .expect("verification succeeds");
    assert!(exact.valid);
    assert!(exact.mismatches.is_empty());

    let mut tampered = calculation.result;
    tampered.total = "0.00".to_owned();
    let rejected = verify(VerifyRequest {
        input,
        result: tampered,
        input_sha256: None,
        result_sha256: None,
    })
    .expect("verification completes");
    assert!(!rejected.valid);
    assert_eq!(rejected.mismatches, ["result_mismatch"]);
}
