use axum::body::{Body, to_bytes};
use axum::http::{Request, StatusCode};
use estimate_engine::{MAX_REQUEST_BYTES, app};
use serde_json::{Value, json};
use tower::ServiceExt;

fn estimate_input() -> Value {
    json!({
        "title": "Проверка округления",
        "region": "Самарская область",
        "currency": "RUB",
        "overhead_rate": "10",
        "vat_rate": "20",
        "sections": [{
            "title": "Работы",
            "positions": [
                {
                    "code": "A",
                    "name": "Граница половины",
                    "unit": "шт",
                    "quantity": "1",
                    "price": "0.005"
                },
                {
                    "code": "B",
                    "name": "Округление произведения",
                    "unit": "шт",
                    "quantity": "3",
                    "price": "1.005"
                }
            ]
        }]
    })
}

async fn post_json(path: &str, payload: &Value) -> (StatusCode, Value) {
    let response = app()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri(path)
                .header("content-type", "application/json")
                .body(Body::from(
                    serde_json::to_vec(payload).expect("serialize request fixture"),
                ))
                .expect("build request"),
        )
        .await
        .expect("router response");
    let status = response.status();
    let bytes = to_bytes(response.into_body(), MAX_REQUEST_BYTES)
        .await
        .expect("read response body");
    let payload = serde_json::from_slice(&bytes).expect("JSON response body");
    (status, payload)
}

#[tokio::test]
async fn health_exposes_identity_rounding_and_limits() {
    let response = app()
        .oneshot(
            Request::builder()
                .uri("/health")
                .body(Body::empty())
                .expect("build request"),
        )
        .await
        .expect("router response");
    assert_eq!(response.status(), StatusCode::OK);
    let bytes = to_bytes(response.into_body(), MAX_REQUEST_BYTES)
        .await
        .expect("read response body");
    let payload: Value = serde_json::from_slice(&bytes).expect("JSON response body");
    assert_eq!(payload["status"], "ok");
    assert_eq!(payload["schema"], "kolibri.estimate-engine.v1");
    assert_eq!(payload["engine"], "kolibri-estimates");
    assert_eq!(payload["version"], "0.1.0");
    assert_eq!(payload["rounding"], "ROUND_HALF_UP:0.01");
    assert_eq!(payload["limits"]["max_sections"], 100);
    assert_eq!(payload["limits"]["max_positions_per_section"], 500);
    assert_eq!(payload["limits"]["max_total_positions"], 2_000);
}

#[tokio::test]
async fn calculate_uses_rounded_lines_then_overhead_and_vat() {
    let (status, payload) = post_json("/calculate", &estimate_input()).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(
        payload["result"]["sections"][0]["positions"][0]["sum"],
        "0.01"
    );
    assert_eq!(
        payload["result"]["sections"][0]["positions"][1]["sum"],
        "3.02"
    );
    assert_eq!(payload["result"]["sections"][0]["subtotal"], "3.03");
    assert_eq!(payload["result"]["subtotal"], "3.03");
    assert_eq!(payload["result"]["overhead_amount"], "0.30");
    assert_eq!(payload["result"]["vat_amount"], "0.67");
    assert_eq!(payload["result"]["total"], "4.00");
    assert_eq!(payload["input_sha256"].as_str().map(str::len), Some(64));
    assert_eq!(payload["result_sha256"].as_str().map(str::len), Some(64));
}

#[tokio::test]
async fn decimals_must_be_nonnegative_json_strings() {
    let mut numeric = estimate_input();
    numeric["sections"][0]["positions"][0]["quantity"] = json!(1);
    let (status, payload) = post_json("/calculate", &numeric).await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    assert_eq!(payload["error"]["code"], "invalid_request");

    let mut negative = estimate_input();
    negative["sections"][0]["positions"][0]["quantity"] = json!("-1");
    let (status, payload) = post_json("/calculate", &negative).await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    assert_eq!(payload["error"]["code"], "negative_decimal");
    assert_eq!(
        payload["error"]["path"],
        "sections[0].positions[0].quantity"
    );
}

#[tokio::test]
async fn fingerprints_ignore_key_order_and_decimal_spelling_but_include_region() {
    let first = estimate_input();
    let second: Value = serde_json::from_str(
        r#"{
            "sections":[{"positions":[
                {"price":"0.0050","quantity":"1.00","unit":"шт","name":"Граница половины","code":"A"},
                {"price":"1.00500","quantity":"3.0","unit":"шт","name":"Округление произведения","code":"B"}
            ],"title":"Работы"}],
            "vat_rate":"20.00","overhead_rate":"10.0","currency":"RUB",
            "region":"Самарская область","title":"Проверка округления"
        }"#,
    )
    .expect("second JSON fixture");
    let (_, first_hashes) = post_json("/fingerprint", &first).await;
    let (_, second_hashes) = post_json("/fingerprint", &second).await;
    assert_eq!(first_hashes["input_sha256"], second_hashes["input_sha256"]);
    assert_eq!(
        first_hashes["result_sha256"],
        second_hashes["result_sha256"]
    );

    let mut other_region = first;
    other_region["region"] = json!("Республика Татарстан");
    let (_, other_hashes) = post_json("/fingerprint", &other_region).await;
    assert_ne!(first_hashes["input_sha256"], other_hashes["input_sha256"]);
}

#[tokio::test]
async fn verify_accepts_exact_result_and_rejects_tampering() {
    let input = estimate_input();
    let (_, calculation) = post_json("/calculate", &input).await;
    let request = json!({
        "input": input,
        "result": calculation["result"],
        "input_sha256": calculation["input_sha256"],
        "result_sha256": calculation["result_sha256"]
    });
    let (status, verified) = post_json("/verify", &request).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(verified["valid"], true);
    assert_eq!(verified["mismatches"], json!([]));

    let mut tampered = request;
    tampered["result"]["total"] = json!("4.01");
    let (status, rejected) = post_json("/verify", &tampered).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(rejected["valid"], false);
    assert_eq!(rejected["mismatches"], json!(["result_mismatch"]));
    assert_ne!(
        rejected["result_sha256"],
        rejected["provided_result_sha256"]
    );
}

#[tokio::test]
async fn rejects_each_collection_limit() {
    let section = json!({"positions": []});
    let sections = vec![section; 101];
    let (status, payload) = post_json("/calculate", &json!({"sections": sections})).await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    assert_eq!(payload["error"]["code"], "limit_exceeded");
    assert_eq!(payload["error"]["path"], "sections");

    let position = json!({"quantity": "1", "price": "1"});
    let positions = vec![position.clone(); 501];
    let (status, payload) = post_json(
        "/calculate",
        &json!({"sections": [{"positions": positions}]}),
    )
    .await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    assert_eq!(payload["error"]["path"], "sections[0].positions");

    let sections: Vec<Value> = [500_usize, 500, 500, 500, 1]
        .into_iter()
        .map(|count| json!({"positions": vec![position.clone(); count]}))
        .collect();
    let (status, payload) = post_json("/calculate", &json!({"sections": sections})).await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    assert_eq!(payload["error"]["path"], "sections");
    assert!(
        payload["error"]["message"]
            .as_str()
            .is_some_and(|message| message.contains("2000"))
    );
}
