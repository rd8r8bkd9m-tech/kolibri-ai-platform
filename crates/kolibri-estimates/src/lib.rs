mod canonical;
mod decimal;
mod engine;
mod error;
mod model;

pub use canonical::{canonical_json_bytes, canonical_sha256};
pub use decimal::MAX_DECIMAL_DIGITS;
pub use engine::{
    Calculation, MAX_POSITIONS_PER_SECTION, MAX_SECTIONS, MAX_TOTAL_POSITIONS, Verification,
    calculate, verify,
};
pub use error::{EstimateError, ValidationIssue};
pub use model::{
    CalculatedPosition, CalculatedSection, EstimateInput, EstimateResult, PositionInput,
    SectionInput, VerifyRequest,
};

pub const SCHEMA_ID: &str = "kolibri.estimate-engine.v1";
pub const ENGINE_ID: &str = "kolibri-estimates";
pub const ENGINE_VERSION: &str = env!("CARGO_PKG_VERSION");
pub const ROUNDING_POLICY: &str = "ROUND_HALF_UP:0.01";
