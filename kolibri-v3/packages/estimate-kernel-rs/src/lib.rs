//! Deterministic, side-effect-free estimate calculation kernel.
//!
//! The kernel accepts only normalized, versioned input. It does not retrieve
//! prices, invent quantities, persist records, render documents, or call an
//! agent. Those responsibilities remain outside this crate.

use rust_decimal::{Decimal, RoundingStrategy};
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::error::Error;
use std::fmt::{self, Display, Formatter};
use std::str::FromStr;

pub const SCHEMA_VERSION: &str = "1.0";
pub const ENGINE_VERSION: &str = "kolibri-estimate-kernel/0.1.0";
pub const MONEY_SCALE: u32 = 2;
pub const QUANTITY_SCALE: u32 = 6;
const MAX_LINES: usize = 10_000;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum KernelError {
    InvalidJson(String),
    InvalidContract { field: String, reason: String },
    ReleaseBlocked { line_ids: Vec<String> },
    Serialization(String),
}

impl Display for KernelError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidJson(reason) => write!(formatter, "invalid_json: {reason}"),
            Self::InvalidContract { field, reason } => {
                write!(formatter, "invalid_contract: {field}: {reason}")
            }
            Self::ReleaseBlocked { line_ids } => {
                write!(
                    formatter,
                    "release_blocked: incomplete price evidence for {}",
                    line_ids.join(",")
                )
            }
            Self::Serialization(reason) => {
                write!(formatter, "serialization_failed: {reason}")
            }
        }
    }
}

impl Error for KernelError {}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CostCategory {
    Work,
    Material,
    Equipment,
    Service,
    Delivery,
    Other,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PriceStatus {
    Missing,
    Preliminary,
    SourceBacked,
    Verified,
}

impl PriceStatus {
    fn participates_in_arithmetic(self) -> bool {
        matches!(self, Self::SourceBacked | Self::Verified)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CalculationRequestV1 {
    pub schema_version: String,
    pub calculation_id: String,
    pub currency: String,
    pub rules_version: String,
    pub release_mode: bool,
    pub lines: Vec<LineInputV1>,
    pub terms: CommercialTermsV1,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct LineInputV1 {
    pub id: String,
    pub category: CostCategory,
    pub title: String,
    pub unit: String,
    pub quantity: String,
    pub unit_price: Option<String>,
    pub price_status: PriceStatus,
    pub source_id: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CommercialTermsV1 {
    pub overhead_percent: String,
    pub profit_percent: String,
    pub discount_percent: String,
    pub tax_percent: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CalculationResultV1 {
    pub schema_version: String,
    pub engine_version: String,
    pub calculation_id: String,
    pub currency: String,
    pub rules_version: String,
    pub rounding_policy: RoundingPolicyV1,
    pub lines: Vec<LineOutputV1>,
    pub totals: TotalsV1,
    pub validation: ValidationV1,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RoundingPolicyV1 {
    pub money_scale: u32,
    pub quantity_scale: u32,
    pub midpoint: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct LineOutputV1 {
    pub id: String,
    pub category: CostCategory,
    pub title: String,
    pub unit: String,
    pub normalized_quantity: String,
    pub unit_price: Option<String>,
    pub subtotal: Option<String>,
    pub price_status: PriceStatus,
    pub source_id: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct TotalsV1 {
    pub by_category: CategoryTotalsV1,
    pub direct_cost: String,
    pub overhead: String,
    pub profit: String,
    pub discount: String,
    pub tax: String,
    pub total: String,
    pub complete: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CategoryTotalsV1 {
    pub work: String,
    pub material: String,
    pub equipment: String,
    pub service: String,
    pub delivery: String,
    pub other: String,
}

impl CategoryTotalsV1 {
    fn from_decimals(values: &CategoryDecimalTotals) -> Self {
        Self {
            work: money_text(values.work),
            material: money_text(values.material),
            equipment: money_text(values.equipment),
            service: money_text(values.service),
            delivery: money_text(values.delivery),
            other: money_text(values.other),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ValidationV1 {
    pub status: ValidationStatus,
    pub missing_price_line_ids: Vec<String>,
    pub preliminary_price_line_ids: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ValidationStatus {
    Passed,
    Blocked,
}

#[derive(Debug, Default)]
struct CategoryDecimalTotals {
    work: Decimal,
    material: Decimal,
    equipment: Decimal,
    service: Decimal,
    delivery: Decimal,
    other: Decimal,
}

impl CategoryDecimalTotals {
    fn add(&mut self, category: CostCategory, value: Decimal) {
        match category {
            CostCategory::Work => self.work += value,
            CostCategory::Material => self.material += value,
            CostCategory::Equipment => self.equipment += value,
            CostCategory::Service => self.service += value,
            CostCategory::Delivery => self.delivery += value,
            CostCategory::Other => self.other += value,
        }
    }
}

fn contract_error(field: impl Into<String>, reason: impl Into<String>) -> KernelError {
    KernelError::InvalidContract {
        field: field.into(),
        reason: reason.into(),
    }
}

fn validate_identifier(value: &str, field: &str) -> Result<(), KernelError> {
    if value.is_empty() || value.len() > 160 {
        return Err(contract_error(field, "must contain 1..160 characters"));
    }
    if !value.bytes().all(|byte| {
        byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.' | b':' | b'/')
    }) {
        return Err(contract_error(field, "contains unsupported characters"));
    }
    Ok(())
}

fn validate_label(value: &str, field: &str, maximum: usize) -> Result<(), KernelError> {
    if value.trim() != value || value.is_empty() || value.chars().count() > maximum {
        return Err(contract_error(
            field,
            format!("must be trimmed and contain 1..{maximum} characters"),
        ));
    }
    Ok(())
}

fn validate_currency(value: &str) -> Result<(), KernelError> {
    if value.len() != 3 || !value.bytes().all(|byte| byte.is_ascii_uppercase()) {
        return Err(contract_error(
            "currency",
            "must be a three-letter uppercase ISO-like code",
        ));
    }
    Ok(())
}

fn parse_non_negative_decimal(value: &str, field: &str) -> Result<Decimal, KernelError> {
    if value.is_empty()
        || value.trim() != value
        || value.starts_with('+')
        || value.contains(['e', 'E', '_', ','])
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || byte == b'.')
        || value.bytes().filter(|byte| *byte == b'.').count() > 1
    {
        return Err(contract_error(
            field,
            "must be a non-negative base-10 decimal string",
        ));
    }
    let parsed = Decimal::from_str(value)
        .map_err(|_| contract_error(field, "is outside supported decimal precision"))?;
    if parsed.is_sign_negative() {
        return Err(contract_error(field, "cannot be negative"));
    }
    Ok(parsed)
}

fn parse_percent(value: &str, field: &str) -> Result<Decimal, KernelError> {
    let parsed = parse_non_negative_decimal(value, field)?;
    if parsed > Decimal::ONE_HUNDRED {
        return Err(contract_error(field, "cannot exceed 100"));
    }
    Ok(parsed)
}

fn rounded(value: Decimal, scale: u32) -> Decimal {
    value.round_dp_with_strategy(scale, RoundingStrategy::MidpointAwayFromZero)
}

fn money_text(value: Decimal) -> String {
    let mut value = rounded(value, MONEY_SCALE);
    value.rescale(MONEY_SCALE);
    value.to_string()
}

fn quantity_text(value: Decimal) -> String {
    rounded(value, QUANTITY_SCALE).normalize().to_string()
}

fn percentage(base: Decimal, percent: Decimal) -> Decimal {
    rounded(base * percent / Decimal::ONE_HUNDRED, MONEY_SCALE)
}

pub fn calculate(request: CalculationRequestV1) -> Result<CalculationResultV1, KernelError> {
    if request.schema_version != SCHEMA_VERSION {
        return Err(contract_error(
            "schemaVersion",
            format!("must equal {SCHEMA_VERSION}"),
        ));
    }
    validate_identifier(&request.calculation_id, "calculationId")?;
    validate_currency(&request.currency)?;
    validate_identifier(&request.rules_version, "rulesVersion")?;
    if request.lines.is_empty() || request.lines.len() > MAX_LINES {
        return Err(contract_error(
            "lines",
            format!("must contain 1..{MAX_LINES} rows"),
        ));
    }

    let overhead_percent = parse_percent(&request.terms.overhead_percent, "terms.overheadPercent")?;
    let profit_percent = parse_percent(&request.terms.profit_percent, "terms.profitPercent")?;
    let discount_percent = parse_percent(&request.terms.discount_percent, "terms.discountPercent")?;
    let tax_percent = parse_percent(&request.terms.tax_percent, "terms.taxPercent")?;

    let mut seen_ids = HashSet::with_capacity(request.lines.len());
    let mut outputs = Vec::with_capacity(request.lines.len());
    let mut categories = CategoryDecimalTotals::default();
    let mut direct_cost = Decimal::ZERO;
    let mut missing_price_line_ids = Vec::new();
    let mut preliminary_price_line_ids = Vec::new();

    for (index, line) in request.lines.into_iter().enumerate() {
        let prefix = format!("lines[{index}]");
        validate_identifier(&line.id, &format!("{prefix}.id"))?;
        if !seen_ids.insert(line.id.clone()) {
            return Err(contract_error(
                format!("{prefix}.id"),
                "must be unique inside one calculation",
            ));
        }
        validate_label(&line.title, &format!("{prefix}.title"), 500)?;
        validate_label(&line.unit, &format!("{prefix}.unit"), 32)?;
        let quantity = parse_non_negative_decimal(&line.quantity, &format!("{prefix}.quantity"))?;

        let (unit_price, subtotal) = if line.price_status.participates_in_arithmetic() {
            let raw_price = line.unit_price.as_deref().ok_or_else(|| {
                contract_error(
                    format!("{prefix}.unitPrice"),
                    "is required for a source-backed or verified line",
                )
            })?;
            let source_id = line.source_id.as_deref().ok_or_else(|| {
                contract_error(
                    format!("{prefix}.sourceId"),
                    "is required for a source-backed or verified line",
                )
            })?;
            validate_identifier(source_id, &format!("{prefix}.sourceId"))?;
            let parsed_price =
                parse_non_negative_decimal(raw_price, &format!("{prefix}.unitPrice"))?;
            let parsed_subtotal = rounded(quantity * parsed_price, MONEY_SCALE);
            direct_cost += parsed_subtotal;
            categories.add(line.category, parsed_subtotal);
            (
                Some(money_text(parsed_price)),
                Some(money_text(parsed_subtotal)),
            )
        } else {
            if line.unit_price.is_some() {
                return Err(contract_error(
                    format!("{prefix}.unitPrice"),
                    "cannot participate when priceStatus is missing or preliminary",
                ));
            }
            if line.source_id.is_some() {
                return Err(contract_error(
                    format!("{prefix}.sourceId"),
                    "cannot be committed when priceStatus is missing or preliminary",
                ));
            }
            match line.price_status {
                PriceStatus::Missing => missing_price_line_ids.push(line.id.clone()),
                PriceStatus::Preliminary => preliminary_price_line_ids.push(line.id.clone()),
                PriceStatus::SourceBacked | PriceStatus::Verified => unreachable!(),
            }
            (None, None)
        };

        outputs.push(LineOutputV1 {
            id: line.id,
            category: line.category,
            title: line.title,
            unit: line.unit,
            normalized_quantity: quantity_text(quantity),
            unit_price,
            subtotal,
            price_status: line.price_status,
            source_id: line.source_id,
        });
    }

    let complete = missing_price_line_ids.is_empty() && preliminary_price_line_ids.is_empty();
    if request.release_mode && !complete {
        let mut blocked = missing_price_line_ids.clone();
        blocked.extend(preliminary_price_line_ids.iter().cloned());
        return Err(KernelError::ReleaseBlocked { line_ids: blocked });
    }

    direct_cost = rounded(direct_cost, MONEY_SCALE);
    let overhead = percentage(direct_cost, overhead_percent);
    let profit = percentage(direct_cost + overhead, profit_percent);
    let discount = percentage(direct_cost + overhead + profit, discount_percent);
    let taxable = direct_cost + overhead + profit - discount;
    let tax = percentage(taxable, tax_percent);
    let total = rounded(taxable + tax, MONEY_SCALE);

    Ok(CalculationResultV1 {
        schema_version: SCHEMA_VERSION.to_owned(),
        engine_version: ENGINE_VERSION.to_owned(),
        calculation_id: request.calculation_id,
        currency: request.currency,
        rules_version: request.rules_version,
        rounding_policy: RoundingPolicyV1 {
            money_scale: MONEY_SCALE,
            quantity_scale: QUANTITY_SCALE,
            midpoint: "away_from_zero".to_owned(),
        },
        lines: outputs,
        totals: TotalsV1 {
            by_category: CategoryTotalsV1::from_decimals(&categories),
            direct_cost: money_text(direct_cost),
            overhead: money_text(overhead),
            profit: money_text(profit),
            discount: money_text(discount),
            tax: money_text(tax),
            total: money_text(total),
            complete,
        },
        validation: ValidationV1 {
            status: if complete {
                ValidationStatus::Passed
            } else {
                ValidationStatus::Blocked
            },
            missing_price_line_ids,
            preliminary_price_line_ids,
        },
    })
}

pub fn calculate_json(input: &str) -> Result<String, KernelError> {
    let request: CalculationRequestV1 =
        serde_json::from_str(input).map_err(|error| KernelError::InvalidJson(error.to_string()))?;
    let result = calculate(request)?;
    serde_json::to_string(&result).map_err(|error| KernelError::Serialization(error.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request() -> CalculationRequestV1 {
        CalculationRequestV1 {
            schema_version: SCHEMA_VERSION.to_owned(),
            calculation_id: "calc_unit_001".to_owned(),
            currency: "RUB".to_owned(),
            rules_version: "commercial-total/1.0.0".to_owned(),
            release_mode: true,
            lines: vec![LineInputV1 {
                id: "line_work_001".to_owned(),
                category: CostCategory::Work,
                title: "Работы".to_owned(),
                unit: "m2".to_owned(),
                quantity: "1".to_owned(),
                unit_price: Some("1.005".to_owned()),
                price_status: PriceStatus::Verified,
                source_id: Some("source_001".to_owned()),
            }],
            terms: CommercialTermsV1 {
                overhead_percent: "0".to_owned(),
                profit_percent: "0".to_owned(),
                discount_percent: "0".to_owned(),
                tax_percent: "0".to_owned(),
            },
        }
    }

    #[test]
    fn money_uses_midpoint_away_from_zero() {
        let result = calculate(request()).expect("calculation should pass");
        assert_eq!(result.lines[0].subtotal.as_deref(), Some("1.01"));
        assert_eq!(result.totals.total, "1.01");
    }

    #[test]
    fn duplicate_line_ids_are_rejected() {
        let mut value = request();
        value.lines.push(value.lines[0].clone());
        let error = calculate(value).expect_err("duplicate must fail");
        assert!(error.to_string().contains("must be unique"));
    }

    #[test]
    fn preliminary_price_cannot_enter_arithmetic() {
        let mut value = request();
        value.lines[0].price_status = PriceStatus::Preliminary;
        let error = calculate(value).expect_err("preliminary price must fail");
        assert!(
            error
                .to_string()
                .contains("cannot participate when priceStatus")
        );
    }

    #[test]
    fn incomplete_release_is_blocked() {
        let mut value = request();
        value.lines[0].price_status = PriceStatus::Missing;
        value.lines[0].unit_price = None;
        value.lines[0].source_id = None;
        let error = calculate(value).expect_err("release must be blocked");
        assert!(matches!(error, KernelError::ReleaseBlocked { .. }));
    }

    #[test]
    fn unknown_json_fields_are_rejected() {
        let input = r#"{
          "schemaVersion":"1.0",
          "calculationId":"calc_001",
          "currency":"RUB",
          "rulesVersion":"rules/1.0.0",
          "releaseMode":true,
          "lines":[],
          "terms":{
            "overheadPercent":"0",
            "profitPercent":"0",
            "discountPercent":"0",
            "taxPercent":"0"
          },
          "unexpected":true
        }"#;
        let error = calculate_json(input).expect_err("unknown field must fail");
        assert!(matches!(error, KernelError::InvalidJson(_)));
    }
}
