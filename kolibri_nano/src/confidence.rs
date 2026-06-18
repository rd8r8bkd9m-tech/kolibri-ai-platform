use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfidenceScore {
    pub value: f32,
    pub factors: Vec<ConfidenceFactor>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfidenceFactor {
    pub name: String,
    pub impact: f32,
    pub description: String,
}

pub fn calculate_confidence(
    trace_count: usize,
    avg_weight: f32,
    success_rate: f32,
    pattern_matches: usize,
) -> ConfidenceScore {
    let mut factors = Vec::new();
    let mut score: f32 = 0.5;

    let trace_factor = (trace_count as f32 / 10.0).min(1.0) * 0.2;
    factors.push(ConfidenceFactor {
        name: "trace_volume".into(),
        impact: trace_factor,
        description: format!("{} traces found", trace_count),
    });
    score += trace_factor;

    let weight_factor = (avg_weight / 10.0).min(1.0) * 0.15;
    factors.push(ConfidenceFactor {
        name: "avg_weight".into(),
        impact: weight_factor,
        description: format!("Average weight {:.2}", avg_weight),
    });
    score += weight_factor;

    let success_factor = success_rate.clamp(0.0, 1.0) * 0.2;
    factors.push(ConfidenceFactor {
        name: "success_rate".into(),
        impact: success_factor,
        description: format!("Success rate {:.0}%", success_rate * 100.0),
    });
    score += success_factor;

    let pattern_factor = (pattern_matches as f32 / 5.0).min(1.0) * 0.15;
    factors.push(ConfidenceFactor {
        name: "pattern_match".into(),
        impact: pattern_factor,
        description: format!("{} patterns matched", pattern_matches),
    });
    score += pattern_factor;

    ConfidenceScore {
        value: score.clamp(0.0, 1.0),
        factors,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_confidence_no_data() {
        let score = calculate_confidence(0, 0.0, 0.0, 0);
        assert_eq!(score.value, 0.5);
    }

    #[test]
    fn test_confidence_high() {
        let score = calculate_confidence(20, 8.0, 0.9, 10);
        assert!(score.value > 0.85);
        assert_eq!(score.factors.len(), 4);
    }

    #[test]
    fn test_confidence_clamped() {
        let score = calculate_confidence(1000, 100.0, 2.0, 1000);
        assert!(score.value <= 1.0);
    }
}
