use chrono::Utc;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum TraceType {
    Preference,
    Correction,
    Task,
    Estimate,
    Document,
    Code,
    Behavior,
    Error,
    Success,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum Emotion {
    Neutral,
    Happy,
    Curious,
    Frustrated,
    Confused,
    Satisfied,
    Surprised,
}

impl Default for Emotion {
    fn default() -> Self { Emotion::Neutral }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum ColorMark {
    Green,
    Yellow,
    Red,
}

impl Default for ColorMark {
    fn default() -> Self { ColorMark::Green }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum Privacy {
    Local,
    Anonymized,
    Shareable,
}

impl Default for Privacy {
    fn default() -> Self { Privacy::Local }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Trace {
    pub id: String,
    pub user_id: String,
    pub trace_type: TraceType,
    pub content: String,
    pub weight: f32,
    pub confidence: f32,
    pub intuition: f32,
    pub emotion: Emotion,
    pub color_mark: ColorMark,
    pub privacy: Privacy,
    pub signature: String,
    pub created_at: u64,
    pub links: Vec<String>,
}

impl Trace {
    pub fn new(user_id: &str, trace_type: TraceType, content: &str) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            user_id: user_id.to_string(),
            trace_type,
            content: content.to_string(),
            weight: 1.0,
            confidence: 0.5,
            intuition: 0.0,
            emotion: Emotion::Neutral,
            color_mark: ColorMark::Green,
            privacy: Privacy::Local,
            signature: String::new(),
            created_at: Utc::now().timestamp_millis() as u64,
            links: Vec::new(),
        }
    }

    pub fn with_weight(mut self, weight: f32) -> Self {
        self.weight = weight.clamp(0.0, 10.0);
        self
    }

    pub fn with_confidence(mut self, confidence: f32) -> Self {
        self.confidence = confidence.clamp(0.0, 1.0);
        self
    }

    pub fn with_intuition(mut self, intuition: f32) -> Self {
        self.intuition = intuition.clamp(0.0, 1.0);
        self
    }

    pub fn with_emotion(mut self, emotion: Emotion) -> Self {
        self.emotion = emotion;
        self
    }

    pub fn with_color_mark(mut self, mark: ColorMark) -> Self {
        self.color_mark = mark;
        self
    }

    pub fn with_privacy(mut self, privacy: Privacy) -> Self {
        self.privacy = privacy;
        self
    }

    pub fn with_link(mut self, link: &str) -> Self {
        self.links.push(link.to_string());
        self
    }

    pub fn with_signature(mut self, sig: &str) -> Self {
        self.signature = sig.to_string();
        self
    }

    pub fn boost(&mut self, amount: f32) {
        self.weight = (self.weight + amount).clamp(0.0, 10.0);
    }

    pub fn decay(&mut self, factor: f32) {
        self.weight = (self.weight * factor).clamp(0.0, 10.0);
    }

    pub fn age_hours(&self) -> f64 {
        let now = Utc::now().timestamp_millis() as u64;
        (now.saturating_sub(self.created_at)) as f64 / 3_600_000.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_trace_creation() {
        let trace = Trace::new("user1", TraceType::Preference, "Prefers short answers");
        assert_eq!(trace.user_id, "user1");
        assert_eq!(trace.trace_type, TraceType::Preference);
        assert_eq!(trace.content, "Prefers short answers");
        assert_eq!(trace.weight, 1.0);
        assert_eq!(trace.confidence, 0.5);
        assert_eq!(trace.intuition, 0.0);
        assert_eq!(trace.emotion, Emotion::Neutral);
        assert_eq!(trace.color_mark, ColorMark::Green);
        assert_eq!(trace.privacy, Privacy::Local);
        assert!(!trace.id.is_empty());
    }

    #[test]
    fn test_trace_builder() {
        let trace = Trace::new("u1", TraceType::Task, "Build estimate")
            .with_weight(3.0)
            .with_confidence(0.8)
            .with_intuition(0.6)
            .with_emotion(Emotion::Curious)
            .with_color_mark(ColorMark::Yellow)
            .with_privacy(Privacy::Anonymized)
            .with_link("task-123")
            .with_signature("abc123");
        assert_eq!(trace.weight, 3.0);
        assert_eq!(trace.confidence, 0.8);
        assert_eq!(trace.intuition, 0.6);
        assert_eq!(trace.emotion, Emotion::Curious);
        assert_eq!(trace.color_mark, ColorMark::Yellow);
        assert_eq!(trace.privacy, Privacy::Anonymized);
        assert_eq!(trace.links.len(), 1);
        assert_eq!(trace.signature, "abc123");
    }

    #[test]
    fn test_trace_boost_decay() {
        let mut trace = Trace::new("u1", TraceType::Success, "Done");
        trace.boost(2.0);
        assert_eq!(trace.weight, 3.0);
        trace.boost(20.0);
        assert_eq!(trace.weight, 10.0);
        trace.decay(0.5);
        assert_eq!(trace.weight, 5.0);
    }

    #[test]
    fn test_trace_age() {
        let trace = Trace::new("u1", TraceType::Task, "Test");
        assert!(trace.age_hours() < 0.01); // just created
    }
}
