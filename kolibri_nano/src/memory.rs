use crate::traces::Trace;

#[derive(Debug, Default)]
pub struct MemoryEngine {
    pub traces: Vec<Trace>,
}

impl MemoryEngine {
    pub fn new() -> Self {
        Self { traces: Vec::new() }
    }

    pub fn add_trace(&mut self, trace: Trace) -> String {
        let id = trace.id.clone();
        self.traces.push(trace);
        id
    }

    pub fn find_by_type(&self, trace_type: &crate::traces::TraceType) -> Vec<&Trace> {
        self.traces.iter().filter(|t| t.trace_type == *trace_type).collect()
    }

    pub fn find_by_user(&self, user_id: &str) -> Vec<&Trace> {
        self.traces.iter().filter(|t| t.user_id == user_id).collect()
    }

    pub fn find_related(&self, trace_id: &str) -> Vec<&Trace> {
        let ids: Vec<String> = self.traces.iter()
            .find(|t| t.id == trace_id)
            .map(|t| t.links.clone())
            .unwrap_or_default();

        self.traces.iter().filter(|t| ids.contains(&t.id)).collect()
    }

    pub fn top_weighted(&self, user_id: &str, limit: usize) -> Vec<&Trace> {
        let mut traces: Vec<&Trace> = self.find_by_user(user_id);
        traces.sort_by(|a, b| b.weight.partial_cmp(&a.weight).unwrap_or(std::cmp::Ordering::Equal));
        traces.into_iter().take(limit).collect()
    }

    pub fn update_weight(&mut self, trace_id: &str, delta: f32) -> bool {
        if let Some(trace) = self.traces.iter_mut().find(|t| t.id == trace_id) {
            trace.boost(delta);
            true
        } else {
            false
        }
    }

    pub fn decay_all(&mut self, factor: f32) {
        for trace in &mut self.traces {
            trace.decay(factor);
        }
    }

    pub fn count(&self) -> usize {
        self.traces.len()
    }

    pub fn avg_weight(&self, user_id: &str) -> f32 {
        let traces = self.find_by_user(user_id);
        if traces.is_empty() {
            return 0.0;
        }
        let sum: f32 = traces.iter().map(|t| t.weight).sum();
        sum / traces.len() as f32
    }

    pub fn extract_patterns(&self, user_id: &str) -> Vec<Pattern> {
        let traces = self.find_by_user(user_id);
        let mut patterns = Vec::new();

        let mut type_counts: std::collections::HashMap<String, usize> = std::collections::HashMap::new();
        for t in &traces {
            let key = format!("{:?}", t.trace_type);
            *type_counts.entry(key).or_insert(0) += 1;
        }

        for (type_name, count) in &type_counts {
            if *count >= 2 {
                patterns.push(Pattern {
                    id: uuid::Uuid::new_v4().to_string(),
                    name: format!("frequent_{}", type_name.to_lowercase()),
                    trigger: type_name.clone(),
                    action_hint: format!("User frequently creates {} traces", type_name),
                    weight: (*count as f32 / traces.len() as f32).min(1.0),
                    success_count: *count as u32,
                });
            }
        }

        patterns
    }

    pub fn prepare_context_for_llm(&self, user_id: &str, max_items: usize) -> String {
        let top = self.top_weighted(user_id, max_items);
        if top.is_empty() {
            return "No prior context available.".to_string();
        }

        let mut parts = vec!["User context from memory:".to_string()];
        for (i, trace) in top.iter().enumerate() {
            parts.push(format!(
                "{}. [{}] {} (weight: {:.1})",
                i + 1,
                format!("{:?}", trace.trace_type).to_lowercase(),
                trace.content,
                trace.weight,
            ));
        }
        parts.join("\n")
    }
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct Pattern {
    pub id: String,
    pub name: String,
    pub trigger: String,
    pub action_hint: String,
    pub weight: f32,
    pub success_count: u32,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::traces::{Trace, TraceType};

    #[test]
    fn test_add_and_find() {
        let mut mem = MemoryEngine::new();
        let t1 = Trace::new("u1", TraceType::Preference, "Short answers");
        let t2 = Trace::new("u1", TraceType::Task, "Build estimate");
        let t3 = Trace::new("u2", TraceType::Preference, "Detailed");
        let id1 = t1.id.clone();
        mem.add_trace(t1);
        mem.add_trace(t2);
        mem.add_trace(t3);

        assert_eq!(mem.count(), 3);
        assert_eq!(mem.find_by_user("u1").len(), 2);
        assert_eq!(mem.find_by_type(&TraceType::Preference).len(), 2);
        assert!(mem.update_weight(&id1, 1.5));
    }

    #[test]
    fn test_top_weighted() {
        let mut mem = MemoryEngine::new();
        for i in 0..10 {
            mem.add_trace(
                Trace::new("u1", TraceType::Task, &format!("Task {}", i))
                    .with_weight(i as f32),
            );
        }
        let top3 = mem.top_weighted("u1", 3);
        assert_eq!(top3.len(), 3);
        assert_eq!(top3[0].weight, 9.0);
    }

    #[test]
    fn test_prepare_context() {
        let mut mem = MemoryEngine::new();
        mem.add_trace(Trace::new("u1", TraceType::Preference, "Likes tables"));
        mem.add_trace(Trace::new("u1", TraceType::Success, "Estimate done"));
        let ctx = mem.prepare_context_for_llm("u1", 5);
        assert!(ctx.contains("User context"));
        assert!(ctx.contains("Likes tables"));
    }

    #[test]
    fn test_extract_patterns() {
        let mut mem = MemoryEngine::new();
        for _ in 0..3 {
            mem.add_trace(Trace::new("u1", TraceType::Estimate, "Create estimate"));
        }
        mem.add_trace(Trace::new("u1", TraceType::Task, "Other task"));
        let patterns = mem.extract_patterns("u1");
        assert!(!patterns.is_empty());
    }

    #[test]
    fn test_decay_all() {
        let mut mem = MemoryEngine::new();
        mem.add_trace(Trace::new("u1", TraceType::Task, "T1").with_weight(5.0));
        mem.add_trace(Trace::new("u1", TraceType::Task, "T2").with_weight(8.0));
        mem.decay_all(0.5);
        let traces = mem.find_by_user("u1");
        assert_eq!(traces[0].weight, 2.5);
        assert_eq!(traces[1].weight, 4.0);
    }
}
