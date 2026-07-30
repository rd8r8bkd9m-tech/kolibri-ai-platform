use kolibri_estimate_kernel::{CalculationResultV1, calculate_json};

#[test]
fn shared_golden_contract_is_byte_stable() {
    let input =
        include_str!("../../../contracts/v1/estimates/examples/valid-calculation-request.json");
    let expected =
        include_str!("../../../contracts/v1/estimates/examples/valid-calculation-result.json");

    let actual_json = calculate_json(input).expect("golden calculation should pass");
    let actual: CalculationResultV1 =
        serde_json::from_str(&actual_json).expect("kernel output must parse");
    let expected: CalculationResultV1 =
        serde_json::from_str(expected).expect("golden output must parse");

    assert_eq!(actual, expected);
    assert_eq!(
        serde_json::to_string(&actual).expect("actual must serialize"),
        serde_json::to_string(&expected).expect("expected must serialize")
    );
}
