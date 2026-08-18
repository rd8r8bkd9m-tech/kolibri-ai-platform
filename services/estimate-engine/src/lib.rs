use axum::extract::{DefaultBodyLimit, rejection::JsonRejection};
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use kolibri_estimates::{
    ENGINE_ID, ENGINE_VERSION, EstimateError, EstimateInput, MAX_DECIMAL_DIGITS,
    MAX_POSITIONS_PER_SECTION, MAX_SECTIONS, MAX_TOTAL_POSITIONS, ROUNDING_POLICY, SCHEMA_ID,
    ValidationIssue, VerifyRequest, calculate, verify,
};
use serde::Serialize;

pub const MAX_REQUEST_BYTES: usize = 1_048_576;

#[derive(Clone, Copy, Debug, Serialize)]
struct EngineMetadata {
    schema: &'static str,
    engine: &'static str,
    version: &'static str,
    rounding: &'static str,
}

#[derive(Debug, Serialize)]
struct HealthResponse {
    #[serde(flatten)]
    metadata: EngineMetadata,
    status: &'static str,
    limits: LimitsResponse,
}

#[derive(Debug, Serialize)]
struct LimitsResponse {
    max_sections: usize,
    max_positions_per_section: usize,
    max_total_positions: usize,
    max_decimal_digits: usize,
    max_request_bytes: usize,
}

#[derive(Debug, Serialize)]
struct CalculateResponse {
    #[serde(flatten)]
    metadata: EngineMetadata,
    input_sha256: String,
    result_sha256: String,
    result: kolibri_estimates::EstimateResult,
}

#[derive(Debug, Serialize)]
struct FingerprintResponse {
    #[serde(flatten)]
    metadata: EngineMetadata,
    input_sha256: String,
    result_sha256: String,
}

#[derive(Debug, Serialize)]
struct VerifyResponse {
    #[serde(flatten)]
    metadata: EngineMetadata,
    valid: bool,
    mismatches: Vec<String>,
    input_sha256: String,
    result_sha256: String,
    provided_result_sha256: String,
}

#[derive(Debug, Serialize)]
struct ErrorResponse {
    #[serde(flatten)]
    metadata: EngineMetadata,
    error: ValidationIssue,
}

#[derive(Debug)]
struct ApiError {
    status: StatusCode,
    issue: ValidationIssue,
}

pub fn app() -> Router {
    Router::new()
        .route("/health", get(health))
        .route("/calculate", post(calculate_endpoint))
        .route("/verify", post(verify_endpoint))
        .route("/fingerprint", post(fingerprint_endpoint))
        .layer(DefaultBodyLimit::max(MAX_REQUEST_BYTES))
}

async fn health() -> Json<HealthResponse> {
    Json(HealthResponse {
        metadata: metadata(),
        status: "ok",
        limits: LimitsResponse {
            max_sections: MAX_SECTIONS,
            max_positions_per_section: MAX_POSITIONS_PER_SECTION,
            max_total_positions: MAX_TOTAL_POSITIONS,
            max_decimal_digits: MAX_DECIMAL_DIGITS,
            max_request_bytes: MAX_REQUEST_BYTES,
        },
    })
}

async fn calculate_endpoint(
    payload: Result<Json<EstimateInput>, JsonRejection>,
) -> Result<Json<CalculateResponse>, ApiError> {
    let Json(input) = payload.map_err(ApiError::from_json_rejection)?;
    let calculation = calculate(input).map_err(ApiError::from)?;
    Ok(Json(CalculateResponse {
        metadata: metadata(),
        input_sha256: calculation.input_sha256,
        result_sha256: calculation.result_sha256,
        result: calculation.result,
    }))
}

async fn fingerprint_endpoint(
    payload: Result<Json<EstimateInput>, JsonRejection>,
) -> Result<Json<FingerprintResponse>, ApiError> {
    let Json(input) = payload.map_err(ApiError::from_json_rejection)?;
    let calculation = calculate(input).map_err(ApiError::from)?;
    Ok(Json(FingerprintResponse {
        metadata: metadata(),
        input_sha256: calculation.input_sha256,
        result_sha256: calculation.result_sha256,
    }))
}

async fn verify_endpoint(
    payload: Result<Json<VerifyRequest>, JsonRejection>,
) -> Result<Json<VerifyResponse>, ApiError> {
    let Json(request) = payload.map_err(ApiError::from_json_rejection)?;
    let verification = verify(request).map_err(ApiError::from)?;
    Ok(Json(VerifyResponse {
        metadata: metadata(),
        valid: verification.valid,
        mismatches: verification.mismatches,
        input_sha256: verification.input_sha256,
        result_sha256: verification.result_sha256,
        provided_result_sha256: verification.provided_result_sha256,
    }))
}

const fn metadata() -> EngineMetadata {
    EngineMetadata {
        schema: SCHEMA_ID,
        engine: ENGINE_ID,
        version: ENGINE_VERSION,
        rounding: ROUNDING_POLICY,
    }
}

impl ApiError {
    fn from_json_rejection(rejection: JsonRejection) -> Self {
        let status = rejection.status();
        let (code, message) = match status {
            StatusCode::UNSUPPORTED_MEDIA_TYPE => (
                "unsupported_media_type",
                "request content type must be application/json",
            ),
            StatusCode::PAYLOAD_TOO_LARGE => (
                "payload_too_large",
                "request body exceeds the configured size limit",
            ),
            StatusCode::UNPROCESSABLE_ENTITY => (
                "invalid_request",
                "request does not match the estimate JSON schema",
            ),
            _ => ("invalid_json", "request body is not valid JSON"),
        };
        Self {
            status,
            issue: ValidationIssue {
                path: "$".to_owned(),
                code: code.to_owned(),
                message: message.to_owned(),
            },
        }
    }
}

impl From<EstimateError> for ApiError {
    fn from(error: EstimateError) -> Self {
        Self {
            status: StatusCode::UNPROCESSABLE_ENTITY,
            issue: error.into_issue(),
        }
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (
            self.status,
            Json(ErrorResponse {
                metadata: metadata(),
                error: self.issue,
            }),
        )
            .into_response()
    }
}
