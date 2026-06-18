use crate::associations::AssociationGraph;
use crate::confidence::{self, ConfidenceScore};
use crate::estimate_engine::{Estimate, EstimateEngine};
use crate::memory::MemoryEngine;
use crate::personal_core::{BehaviorSignal, PersonalCore};
use crate::traces::{Trace, TraceType};

pub struct KolibriCore {
    pub user_id: String,
    pub memory: MemoryEngine,
    pub associations: AssociationGraph,
    pub personal_core: PersonalCore,
}

impl KolibriCore {
    pub fn new(user_id: &str) -> Self {
        Self {
            user_id: user_id.to_string(),
            memory: MemoryEngine::new(),
            associations: AssociationGraph::new(),
            personal_core: PersonalCore::new(user_id),
        }
    }

    pub fn add_trace(&mut self, trace_type: TraceType, content: &str) -> String {
        let trace = Trace::new(&self.user_id, trace_type, content);
        self.memory.add_trace(trace.clone());
        trace.id
    }

    pub fn learn_from_result(&mut self, task_description: &str, was_success: bool, used_memory: bool) {
        let trace_type = if was_success { TraceType::Success } else { TraceType::Error };
        self.add_trace(trace_type, task_description);

        let signal = BehaviorSignal {
            was_success,
            used_memory,
            was_practical: true,
            was_precise: was_success,
            ..Default::default()
        };
        self.personal_core.update_from_behavior(&signal);
    }

    pub fn get_confidence(&self) -> ConfidenceScore {
        let user_traces = self.memory.find_by_user(&self.user_id);
        let count = user_traces.len();
        let avg = self.memory.avg_weight(&self.user_id);
        let success_count = user_traces.iter().filter(|t| t.trace_type == TraceType::Success).count();
        let success_rate = if count > 0 { success_count as f32 / count as f32 } else { 0.0 };
        let patterns = self.memory.extract_patterns(&self.user_id);
        confidence::calculate_confidence(count, avg, success_rate, patterns.len())
    }

    pub fn prepare_context_for_llm(&self, max_items: usize) -> String {
        let mut context = self.memory.prepare_context_for_llm(&self.user_id, max_items);
        context.push_str(&format!("\n\n{}", self.personal_core.summary()));
        context
    }

    pub fn create_estimate(&self, title: &str) -> Estimate {
        EstimateEngine::create_estimate(title)
    }

    pub fn trace_count(&self) -> usize {
        self.memory.find_by_user(&self.user_id).len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_core_creation() {
        let core = KolibriCore::new("user1");
        assert_eq!(core.user_id, "user1");
        assert_eq!(core.trace_count(), 0);
    }

    #[test]
    fn test_add_trace_and_context() {
        let mut core = KolibriCore::new("u1");
        core.add_trace(TraceType::Preference, "Likes short answers");
        core.add_trace(TraceType::Task, "Built estimate for room 18m2");
        assert_eq!(core.trace_count(), 2);

        let ctx = core.prepare_context_for_llm(5);
        assert!(ctx.contains("Likes short answers"));
        assert!(ctx.contains("Core[u1]"));
    }

    #[test]
    fn test_learn_from_result() {
        let mut core = KolibriCore::new("u1");
        core.learn_from_result("Created estimate", true, true);
        core.learn_from_result("Failed export", false, false);

        assert_eq!(core.trace_count(), 2);
        let conf = core.get_confidence();
        assert!(conf.value > 0.0);
    }

    #[test]
    fn test_estimate_via_core() {
        let core = KolibriCore::new("u1");
        let est = core.create_estimate("Room repair");
        assert_eq!(est.title, "Room repair");
        assert_eq!(est.item_count(), 0);
    }
}
