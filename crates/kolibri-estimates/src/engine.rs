use crate::EstimateError;
use crate::canonical_sha256;
use crate::decimal::{Decimal, Money};
use crate::model::{
    CalculatedPosition, CalculatedSection, EstimateInput, EstimateResult, PositionInput,
    SectionInput, VerifyRequest,
};

pub const MAX_SECTIONS: usize = 100;
pub const MAX_POSITIONS_PER_SECTION: usize = 500;
pub const MAX_TOTAL_POSITIONS: usize = 2_000;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Calculation {
    pub normalized_input: EstimateInput,
    pub result: EstimateResult,
    pub input_sha256: String,
    pub result_sha256: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Verification {
    pub valid: bool,
    pub mismatches: Vec<String>,
    pub input_sha256: String,
    pub result_sha256: String,
    pub provided_result_sha256: String,
}

pub fn calculate(input: EstimateInput) -> Result<Calculation, EstimateError> {
    validate_shape(&input)?;

    let overhead_rate = Decimal::parse(&input.overhead_rate, "overhead_rate")?;
    let vat_rate = Decimal::parse(&input.vat_rate, "vat_rate")?;

    let EstimateInput {
        id,
        title,
        client,
        object_name,
        region,
        currency,
        overhead_rate: _,
        vat_rate: _,
        sections,
        assumptions,
        questions,
    } = input;

    let mut normalized_sections = Vec::with_capacity(sections.len());
    let mut calculated_sections = Vec::with_capacity(sections.len());
    let mut subtotal = Money::zero();

    for (section_index, section) in sections.into_iter().enumerate() {
        let SectionInput {
            id: section_id,
            title: section_title,
            positions,
        } = section;
        let mut normalized_positions = Vec::with_capacity(positions.len());
        let mut calculated_positions = Vec::with_capacity(positions.len());
        let mut section_subtotal = Money::zero();

        for (position_index, position) in positions.into_iter().enumerate() {
            let PositionInput {
                id: position_id,
                code,
                name,
                unit,
                quantity,
                price,
                source,
                comment,
            } = position;
            let quantity_path =
                format!("sections[{section_index}].positions[{position_index}].quantity");
            let price_path = format!("sections[{section_index}].positions[{position_index}].price");
            let quantity = Decimal::parse(&quantity, &quantity_path)?;
            let price = Decimal::parse(&price, &price_path)?;
            let line_sum = quantity.multiply(&price)?.round_money();
            section_subtotal.add_assign(&line_sum);

            let normalized_quantity = quantity.to_plain_string();
            let normalized_price = price.to_plain_string();
            normalized_positions.push(PositionInput {
                id: position_id.clone(),
                code: code.clone(),
                name: name.clone(),
                unit: unit.clone(),
                quantity: normalized_quantity.clone(),
                price: normalized_price.clone(),
                source: source.clone(),
                comment: comment.clone(),
            });
            calculated_positions.push(CalculatedPosition {
                id: position_id,
                code,
                name,
                unit,
                quantity: normalized_quantity,
                price: normalized_price,
                sum: line_sum.to_fixed_string(),
                source,
                comment,
            });
        }

        subtotal.add_assign(&section_subtotal);
        normalized_sections.push(SectionInput {
            id: section_id.clone(),
            title: section_title.clone(),
            positions: normalized_positions,
        });
        calculated_sections.push(CalculatedSection {
            id: section_id,
            title: section_title,
            positions: calculated_positions,
            subtotal: section_subtotal.to_fixed_string(),
        });
    }

    let overhead_amount = subtotal.percentage(&overhead_rate)?;
    let vat_base = subtotal.add(&overhead_amount);
    let vat_amount = vat_base.percentage(&vat_rate)?;
    let total = vat_base.add(&vat_amount);
    let normalized_overhead_rate = overhead_rate.to_plain_string();
    let normalized_vat_rate = vat_rate.to_plain_string();

    let normalized_input = EstimateInput {
        id: id.clone(),
        title: title.clone(),
        client: client.clone(),
        object_name: object_name.clone(),
        region: region.clone(),
        currency: currency.clone(),
        overhead_rate: normalized_overhead_rate.clone(),
        vat_rate: normalized_vat_rate.clone(),
        sections: normalized_sections,
        assumptions: assumptions.clone(),
        questions: questions.clone(),
    };
    let result = EstimateResult {
        id,
        title,
        client,
        object_name,
        region,
        currency,
        overhead_rate: normalized_overhead_rate,
        vat_rate: normalized_vat_rate,
        sections: calculated_sections,
        assumptions,
        questions,
        subtotal: subtotal.to_fixed_string(),
        overhead_amount: overhead_amount.to_fixed_string(),
        vat_amount: vat_amount.to_fixed_string(),
        total: total.to_fixed_string(),
    };
    let input_sha256 = canonical_sha256(&normalized_input)?;
    let result_sha256 = canonical_sha256(&result)?;

    Ok(Calculation {
        normalized_input,
        result,
        input_sha256,
        result_sha256,
    })
}

pub fn verify(request: VerifyRequest) -> Result<Verification, EstimateError> {
    let VerifyRequest {
        input,
        result,
        input_sha256,
        result_sha256,
    } = request;
    let calculation = calculate(input)?;
    let provided_result_sha256 = canonical_sha256(&result)?;
    let mut mismatches = Vec::new();

    if result != calculation.result {
        mismatches.push("result_mismatch".to_owned());
    }
    if input_sha256
        .as_ref()
        .is_some_and(|digest| digest != &calculation.input_sha256)
    {
        mismatches.push("input_sha256_mismatch".to_owned());
    }
    if result_sha256
        .as_ref()
        .is_some_and(|digest| digest != &calculation.result_sha256)
    {
        mismatches.push("result_sha256_mismatch".to_owned());
    }

    Ok(Verification {
        valid: mismatches.is_empty(),
        mismatches,
        input_sha256: calculation.input_sha256,
        result_sha256: calculation.result_sha256,
        provided_result_sha256,
    })
}

fn validate_shape(input: &EstimateInput) -> Result<(), EstimateError> {
    if input.sections.len() > MAX_SECTIONS {
        return Err(EstimateError::new(
            "sections",
            "limit_exceeded",
            format!("at most {MAX_SECTIONS} sections are allowed"),
        ));
    }

    let mut total_positions = 0_usize;
    for (section_index, section) in input.sections.iter().enumerate() {
        if section.positions.len() > MAX_POSITIONS_PER_SECTION {
            return Err(EstimateError::new(
                format!("sections[{section_index}].positions"),
                "limit_exceeded",
                format!("at most {MAX_POSITIONS_PER_SECTION} positions per section are allowed"),
            ));
        }
        total_positions = total_positions.saturating_add(section.positions.len());
        if total_positions > MAX_TOTAL_POSITIONS {
            return Err(EstimateError::new(
                "sections",
                "limit_exceeded",
                format!("at most {MAX_TOTAL_POSITIONS} positions in total are allowed"),
            ));
        }
    }
    Ok(())
}
