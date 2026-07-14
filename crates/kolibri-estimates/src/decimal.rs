use crate::EstimateError;
use num_bigint::BigInt;
use num_traits::Zero;

pub const MAX_DECIMAL_DIGITS: usize = 4_096;

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct Decimal {
    coefficient: BigInt,
    scale: u32,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct Money {
    cents: BigInt,
}

impl Decimal {
    pub(crate) fn parse(raw: &str, path: &str) -> Result<Self, EstimateError> {
        if raw.starts_with('-') {
            return Err(EstimateError::new(
                path,
                "negative_decimal",
                "decimal values must be nonnegative",
            ));
        }
        if raw.is_empty() {
            return Err(invalid_decimal(path));
        }

        let mut parts = raw.split('.');
        let integer = parts.next().unwrap_or_default();
        let fractional = parts.next();
        if parts.next().is_some()
            || integer.is_empty()
            || !integer.bytes().all(|byte| byte.is_ascii_digit())
            || fractional.is_some_and(|value| {
                value.is_empty() || !value.bytes().all(|byte| byte.is_ascii_digit())
            })
        {
            return Err(invalid_decimal(path));
        }

        let fractional = fractional.unwrap_or_default();
        let digit_count = integer.len().saturating_add(fractional.len());
        if digit_count > MAX_DECIMAL_DIGITS {
            return Err(EstimateError::new(
                path,
                "decimal_too_long",
                format!("decimal values may contain at most {MAX_DECIMAL_DIGITS} digits"),
            ));
        }

        let trailing_zeroes = fractional
            .bytes()
            .rev()
            .take_while(|byte| *byte == b'0')
            .count();
        let normalized_fractional_len = fractional.len() - trailing_zeroes;
        let mut digits = String::with_capacity(integer.len() + normalized_fractional_len);
        digits.push_str(integer);
        digits.push_str(&fractional[..normalized_fractional_len]);
        let significant_digits = digits.trim_start_matches('0');
        let coefficient = if significant_digits.is_empty() {
            BigInt::zero()
        } else {
            BigInt::parse_bytes(significant_digits.as_bytes(), 10)
                .ok_or_else(|| invalid_decimal(path))?
        };
        let scale = u32::try_from(normalized_fractional_len).map_err(|_| {
            EstimateError::new(path, "decimal_too_long", "decimal scale is too large")
        })?;

        Ok(Self { coefficient, scale })
    }

    pub(crate) fn multiply(&self, other: &Self) -> Result<Self, EstimateError> {
        let scale = self.scale.checked_add(other.scale).ok_or_else(|| {
            EstimateError::new(
                "$",
                "arithmetic_overflow",
                "decimal scale overflowed during multiplication",
            )
        })?;
        Ok(Self {
            coefficient: &self.coefficient * &other.coefficient,
            scale,
        })
    }

    pub(crate) fn round_money(&self) -> Money {
        if self.scale <= 2 {
            let factor = power_of_ten(2 - self.scale);
            return Money {
                cents: &self.coefficient * factor,
            };
        }

        let divisor = power_of_ten(self.scale - 2);
        let mut quotient = &self.coefficient / &divisor;
        let remainder = &self.coefficient % &divisor;
        if remainder * 2 >= divisor {
            quotient += 1;
        }
        Money { cents: quotient }
    }

    pub(crate) fn to_plain_string(&self) -> String {
        if self.coefficient.is_zero() {
            return "0".to_owned();
        }

        let digits = self.coefficient.to_str_radix(10);
        if self.scale == 0 {
            return digits;
        }

        let scale = usize::try_from(self.scale).unwrap_or(usize::MAX);
        if digits.len() > scale {
            let split = digits.len() - scale;
            format!("{}.{}", &digits[..split], &digits[split..])
        } else {
            let zeroes = "0".repeat(scale - digits.len());
            format!("0.{zeroes}{digits}")
        }
    }
}

impl Money {
    pub(crate) fn zero() -> Self {
        Self {
            cents: BigInt::zero(),
        }
    }

    pub(crate) fn add(&self, other: &Self) -> Self {
        Self {
            cents: &self.cents + &other.cents,
        }
    }

    pub(crate) fn add_assign(&mut self, other: &Self) {
        self.cents += &other.cents;
    }

    pub(crate) fn percentage(&self, rate: &Decimal) -> Result<Self, EstimateError> {
        let scale = rate.scale.checked_add(4).ok_or_else(|| {
            EstimateError::new(
                "$",
                "arithmetic_overflow",
                "decimal scale overflowed during percentage calculation",
            )
        })?;
        Ok(Decimal {
            coefficient: &self.cents * &rate.coefficient,
            scale,
        }
        .round_money())
    }

    pub(crate) fn to_fixed_string(&self) -> String {
        let digits = self.cents.to_str_radix(10);
        match digits.len() {
            0 => "0.00".to_owned(),
            1 => format!("0.0{digits}"),
            2 => format!("0.{digits}"),
            length => format!("{}.{}", &digits[..length - 2], &digits[length - 2..]),
        }
    }
}

fn invalid_decimal(path: &str) -> EstimateError {
    EstimateError::new(
        path,
        "invalid_decimal",
        "expected a plain nonnegative decimal string",
    )
}

fn power_of_ten(exponent: u32) -> BigInt {
    BigInt::from(10_u8).pow(exponent)
}

#[cfg(test)]
mod tests {
    use super::Decimal;

    #[test]
    fn half_up_boundary_rounds_away_from_zero() {
        let value = Decimal::parse("0.005", "value").expect("valid decimal fixture");
        assert_eq!(value.round_money().to_fixed_string(), "0.01");
    }

    #[test]
    fn normalization_is_plain_and_semantic() {
        let value = Decimal::parse("00012.34000", "value").expect("valid decimal fixture");
        assert_eq!(value.to_plain_string(), "12.34");
    }

    #[test]
    fn rejects_signs_exponents_whitespace_and_comma() {
        for raw in ["-0", "+1", "1e2", " 1", "1 ", "1,5", ".5", "1."] {
            assert!(Decimal::parse(raw, "value").is_err(), "accepted {raw:?}");
        }
    }
}
