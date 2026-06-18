use chrono::Utc;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PersonalCore {
    pub user_id: String,
    pub core_digits: [u8; 10],
    pub stability: f32,
    pub curiosity: f32,
    pub precision: f32,
    pub creativity: f32,
    pub practical_focus: f32,
    pub memory_weight: f32,
    pub trust_level: f32,
    pub last_updated: u64,
}

impl PersonalCore {
    pub fn new(user_id: &str) -> Self {
        Self {
            user_id: user_id.to_string(),
            core_digits: [5; 10],
            stability: 0.5,
            curiosity: 0.5,
            precision: 0.5,
            creativity: 0.5,
            practical_focus: 0.5,
            memory_weight: 0.5,
            trust_level: 0.5,
            last_updated: Utc::now().timestamp_millis() as u64,
        }
    }

    pub fn update_from_behavior(&mut self, behavior: &BehaviorSignal) {
        let lr = 0.05;

        if behavior.was_precise {
            self.precision = (self.precision + lr).min(1.0);
            self.core_digits[2] = (self.precision * 9.0).round() as u8;
        }
        if behavior.was_creative {
            self.creativity = (self.creativity + lr).min(1.0);
            self.core_digits[3] = (self.creativity * 9.0).round() as u8;
        }
        if behavior.was_practical {
            self.practical_focus = (self.practical_focus + lr).min(1.0);
            self.core_digits[4] = (self.practical_focus * 9.0).round() as u8;
        }
        if behavior.used_memory {
            self.memory_weight = (self.memory_weight + lr).min(1.0);
            self.core_digits[5] = (self.memory_weight * 9.0).round() as u8;
        }
        if behavior.was_success {
            self.trust_level = (self.trust_level + lr * 2.0).min(1.0);
            self.stability = (self.stability + lr).min(1.0);
        } else {
            self.trust_level = (self.trust_level - lr).max(0.0);
        }
        if behavior.explored_new {
            self.curiosity = (self.curiosity + lr).min(1.0);
            self.core_digits[1] = (self.curiosity * 9.0).round() as u8;
        }

        self.last_updated = Utc::now().timestamp_millis() as u64;
    }

    pub fn summary(&self) -> String {
        format!(
            "Core[{}] S:{:.2} C:{:.2} P:{:.2} Cr:{:.2} Pf:{:.2} M:{:.2} T:{:.2}",
            self.user_id,
            self.stability, self.curiosity, self.precision,
            self.creativity, self.practical_focus, self.memory_weight, self.trust_level,
        )
    }

    pub fn digit_string(&self) -> String {
        self.core_digits.iter().map(|d| d.to_string()).collect::<Vec<_>>().join("")
    }
}

#[derive(Debug, Clone)]
pub struct BehaviorSignal {
    pub was_precise: bool,
    pub was_creative: bool,
    pub was_practical: bool,
    pub used_memory: bool,
    pub was_success: bool,
    pub explored_new: bool,
}

impl Default for BehaviorSignal {
    fn default() -> Self {
        Self {
            was_precise: false,
            was_creative: false,
            was_practical: false,
            used_memory: false,
            was_success: true,
            explored_new: false,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_personal_core_creation() {
        let core = PersonalCore::new("user1");
        assert_eq!(core.user_id, "user1");
        assert_eq!(core.core_digits, [5; 10]);
        assert_eq!(core.stability, 0.5);
    }

    #[test]
    fn test_update_from_behavior() {
        let mut core = PersonalCore::new("u1");
        let signal = BehaviorSignal {
            was_precise: true,
            was_creative: true,
            was_practical: true,
            used_memory: true,
            was_success: true,
            explored_new: true,
        };
        core.update_from_behavior(&signal);
        assert!(core.precision > 0.5);
        assert!(core.creativity > 0.5);
        assert!(core.trust_level > 0.5);
        assert!(core.curiosity > 0.5);
    }

    #[test]
    fn test_digit_string() {
        let mut core = PersonalCore::new("u1");
        core.core_digits = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];
        assert_eq!(core.digit_string(), "0123456789");
    }

    #[test]
    fn test_failure_reduces_trust() {
        let mut core = PersonalCore::new("u1");
        let initial = core.trust_level;
        let signal = BehaviorSignal { was_success: false, ..Default::default() };
        core.update_from_behavior(&signal);
        assert!(core.trust_level < initial);
    }
}
