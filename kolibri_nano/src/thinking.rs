use serde::{Deserialize, Serialize};
use crate::traces::Trace;
use crate::micro_weights::MicroWeightStore;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum StimulusType {
    Text,
    Voice,
    File,
    Image,
    Action,
    Sensor,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Stimulus {
    pub stimulus_type: StimulusType,
    pub content: String,
    pub metadata: Vec<(String, String)>,
}

impl Stimulus {
    pub fn text(content: &str) -> Self {
        Self {
            stimulus_type: StimulusType::Text,
            content: content.to_string(),
            metadata: Vec::new(),
        }
    }

    pub fn with_meta(mut self, key: &str, value: &str) -> Self {
        self.metadata.push((key.to_string(), value.to_string()));
        self
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Context {
    pub user_id: String,
    pub recent_traces: Vec<String>,
    pub active_topics: Vec<String>,
    pub emotional_state: String,
    pub session_focus: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Resonance {
    pub primary_response: String,
    pub confidence: f32,
    pub matched_patterns: Vec<String>,
    pub emotional_tone: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Pulsation {
    pub selected_traces: Vec<String>,
    pub relevance_scores: Vec<f32>,
    pub associations: Vec<(String, String)>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Interference {
    pub combined_patterns: Vec<String>,
    pub new_insights: Vec<String>,
    pub conflicts: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Thought {
    pub output: String,
    pub confidence: f32,
    pub action_hint: String,
    pub canvas_blocks: Vec<String>,
    pub memory_updates: Vec<String>,
    pub trace_refs: Vec<String>,
}

pub struct ThinkingEngine;

impl ThinkingEngine {
    /// O = f(I(P(R(S, C))))
    pub fn think(
        stimulus: &Stimulus,
        context: &Context,
        traces: &[Trace],
        micro_weights: &MicroWeightStore,
    ) -> Thought {
        // R = local resonance
        let resonance = Self::resonance(stimulus, context, traces);

        // P = pulsation (select relevant traces)
        let pulsation = Self::pulsation(&resonance, traces, micro_weights);

        // I = interference (combine patterns)
        let interference = Self::interference(&pulsation);

        // O = output
        Self::produce_output(&stimulus, &context, &resonance, &interference)
    }

    /// R — Local resonance: Nano's primary response to stimulus + context
    fn resonance(stimulus: &Stimulus, _context: &Context, traces: &[Trace]) -> Resonance {
        let content_lower = stimulus.content.to_lowercase();

        // Find traces that resonate with stimulus
        let matched: Vec<&Trace> = traces.iter()
            .filter(|t| {
                let trace_lower = t.content.to_lowercase();
                content_lower.split_whitespace().any(|word| word.len() > 3 && trace_lower.contains(word))
            })
            .collect();

        let confidence = if matched.is_empty() {
            0.1
        } else {
            let avg: f32 = matched.iter().map(|t| t.confidence).sum::<f32>() / matched.len() as f32;
            avg.clamp(0.0, 1.0)
        };

        let matched_patterns: Vec<String> = matched.iter()
            .map(|t| t.content.clone())
            .take(5)
            .collect();

        // Detect emotional tone from stimulus
        let emotional_tone = if content_lower.contains("ошибк") || content_lower.contains("не работа") {
            "frustrated"
        } else if content_lower.contains("отлично") || content_lower.contains("спасибо") {
            "satisfied"
        } else if content_lower.contains("?") || content_lower.contains("как") || content_lower.contains("что") {
            "curious"
        } else {
            "neutral"
        }.to_string();

        // Primary response: synthesize from matched traces
        let primary_response = if matched.is_empty() {
            format!("Новый стимул: '{}'. Нет релевантных следов.", stimulus.content)
        } else {
            let top = matched.iter().max_by(|a, b| a.weight.partial_cmp(&b.weight).unwrap()).unwrap();
            format!("Резонанс с '{}' (confidence={:.2})", top.content, top.confidence)
        };

        Resonance {
            primary_response,
            confidence,
            matched_patterns,
            emotional_tone,
        }
    }

    /// P — Pulsation: select relevant traces, patterns, associations
    fn pulsation(
        resonance: &Resonance,
        traces: &[Trace],
        micro_weights: &MicroWeightStore,
    ) -> Pulsation {
        let mut selected = Vec::new();
        let mut scores = Vec::new();
        let mut associations = Vec::new();

        // Select traces by relevance to resonance patterns
        for trace in traces {
            let relevance = resonance.matched_patterns.iter()
                .filter(|p| trace.content.to_lowercase().contains(&p.to_lowercase()))
                .count() as f32;

            if relevance > 0.0 {
                let score = (relevance * trace.weight * trace.confidence).clamp(0.0, 1.0);
                selected.push(trace.id.clone());
                scores.push(score);
            }
        }

        // Find micro-weight associations for top traces
        for trace_id in selected.iter().take(3) {
            let related = micro_weights.by_source(trace_id);
            for mw in related {
                if mw.weight > 0.3 {
                    associations.push((mw.from.clone(), mw.to.clone()));
                }
            }
        }

        Pulsation {
            selected_traces: selected,
            relevance_scores: scores,
            associations,
        }
    }

    /// I — Interference: combine responses into new semantic pattern
    fn interference(pulsation: &Pulsation) -> Interference {
        let combined = pulsation.selected_traces.clone();

        // Generate insights from associations
        let insights: Vec<String> = pulsation.associations.iter()
            .map(|(from, to)| format!("Ассоциация: {} → {}", from, to))
            .collect();

        // Detect conflicts (low relevance among selected)
        let conflicts: Vec<String> = pulsation.relevance_scores.iter()
            .enumerate()
            .filter(|(_, score)| **score < 0.3)
            .map(|(i, _)| format!("Слабая связь: trace[{}]", i))
            .collect();

        Interference {
            combined_patterns: combined,
            new_insights: insights,
            conflicts,
        }
    }

    /// O — Output: produce response, action, canvas, memory updates
    fn produce_output(
        _stimulus: &Stimulus,
        context: &Context,
        resonance: &Resonance,
        interference: &Interference,
    ) -> Thought {
        let confidence = resonance.confidence;

        // Determine action hint
        let action_hint = if confidence > 0.7 {
            "respond_with_context"
        } else if confidence > 0.3 {
            "ask_clarification"
        } else {
            "explore_new_domain"
        }.to_string();

        // Generate output
        let output = if !interference.new_insights.is_empty() {
            format!(
                "{} | Инсайты: {} | Контекст: {}",
                resonance.primary_response,
                interference.new_insights.join("; "),
                context.session_focus
            )
        } else {
            resonance.primary_response.clone()
        };

        // Canvas blocks from patterns
        let canvas_blocks: Vec<String> = interference.combined_patterns.iter().take(3).cloned().collect();

        // Memory updates
        let memory_updates = if resonance.confidence < 0.3 {
            vec!["new_domain_detected".to_string()]
        } else {
            vec![]
        };

        Thought {
            output,
            confidence,
            action_hint,
            canvas_blocks,
            memory_updates,
            trace_refs: interference.combined_patterns.clone(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::traces::TraceType;

    fn sample_traces() -> Vec<Trace> {
        vec![
            Trace::new("u1", TraceType::Task, "Штукатурка стен 100 м2")
                .with_confidence(0.8)
                .with_weight(3.0),
            Trace::new("u1", TraceType::Estimate, "Смета на ремонт квартиры")
                .with_confidence(0.9)
                .with_weight(5.0),
            Trace::new("u1", TraceType::Preference, "Пользователь предпочитает подробные ответы")
                .with_confidence(0.6)
                .with_weight(2.0),
        ]
    }

    #[test]
    fn test_thinking_formula_basic() {
        let stimulus = Stimulus::text("Нужна смета на штукатурку");
        let context = Context {
            user_id: "u1".to_string(),
            session_focus: "estimates".to_string(),
            ..Default::default()
        };
        let traces = sample_traces();
        let mw = MicroWeightStore::new();

        let thought = ThinkingEngine::think(&stimulus, &context, &traces, &mw);
        assert!(!thought.output.is_empty());
        assert!(thought.confidence > 0.0);
    }

    #[test]
    fn test_resonance_finds_matching() {
        let stimulus = Stimulus::text("Штукатурка стен");
        let context = Context::default();
        let traces = sample_traces();

        let resonance = ThinkingEngine::resonance(&stimulus, &context, &traces);
        assert!(resonance.confidence > 0.0);
        assert!(!resonance.matched_patterns.is_empty());
    }

    #[test]
    fn test_resonance_no_match() {
        let stimulus = Stimulus::text("Квантовая физика");
        let context = Context::default();
        let traces = sample_traces();

        let resonance = ThinkingEngine::resonance(&stimulus, &context, &traces);
        assert!(resonance.confidence < 0.5);
    }

    #[test]
    fn test_emotional_tone_detection() {
        let traces = vec![];
        let ctx = Context::default();

        let s1 = Stimulus::text("Ошибка в смете");
        let r1 = ThinkingEngine::resonance(&s1, &ctx, &traces);
        assert_eq!(r1.emotional_tone, "frustrated");

        let s2 = Stimulus::text("Отлично, спасибо!");
        let r2 = ThinkingEngine::resonance(&s2, &ctx, &traces);
        assert_eq!(r2.emotional_tone, "satisfied");

        let s3 = Stimulus::text("Как сделать расчёт?");
        let r3 = ThinkingEngine::resonance(&s3, &ctx, &traces);
        assert_eq!(r3.emotional_tone, "curious");
    }

    #[test]
    fn test_confidence_levels() {
        let traces = sample_traces();
        let mw = MicroWeightStore::new();

        // High confidence: matching stimulus
        let thought1 = ThinkingEngine::think(
            &Stimulus::text("Штукатурка стен"),
            &Context { user_id: "u1".to_string(), ..Default::default() },
            &traces, &mw,
        );

        // Low confidence: unknown domain
        let thought2 = ThinkingEngine::think(
            &Stimulus::text("Квантовая физика"),
            &Context { user_id: "u1".to_string(), ..Default::default() },
            &traces, &mw,
        );

        assert!(thought1.confidence > thought2.confidence);
    }

    #[test]
    fn test_stimulus_types() {
        let s1 = Stimulus::text("test");
        assert!(matches!(s1.stimulus_type, StimulusType::Text));

        let s2 = Stimulus {
            stimulus_type: StimulusType::Voice,
            content: "audio data".to_string(),
            metadata: vec![],
        };
        assert!(matches!(s2.stimulus_type, StimulusType::Voice));
    }
}
