use chrono::Utc;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MicroWeight {
    pub id: String,
    pub from: String,
    pub to: String,
    pub weight: f32,
    pub confidence: f32,
    pub intuition: f32,
    pub created_at: u64,
    pub updated_at: u64,
    pub use_count: u32,
}

impl MicroWeight {
    pub fn new(from: &str, to: &str, initial_weight: f32) -> Self {
        let now = Utc::now().timestamp_millis() as u64;
        Self {
            id: Uuid::new_v4().to_string(),
            from: from.to_string(),
            to: to.to_string(),
            weight: initial_weight.clamp(-1.0, 1.0),
            confidence: 0.5,
            intuition: 0.0,
            created_at: now,
            updated_at: now,
            use_count: 0,
        }
    }

    pub fn reinforce(&mut self, amount: f32) {
        self.weight = (self.weight + amount).clamp(-1.0, 1.0);
        self.confidence = (self.confidence + 0.05).clamp(0.0, 1.0);
        self.use_count += 1;
        self.updated_at = Utc::now().timestamp_millis() as u64;
    }

    pub fn weaken(&mut self, amount: f32) {
        self.weight = (self.weight - amount).clamp(-1.0, 1.0);
        self.updated_at = Utc::now().timestamp_millis() as u64;
    }

    pub fn auto_decay(&mut self, decay_rate: f32) {
        let age_hours = self.age_hours();
        let decay = (decay_rate * age_hours as f32).min(0.5);
        self.weight = (self.weight * (1.0 - decay)).clamp(-1.0, 1.0);
        self.confidence = (self.confidence * (1.0 - decay * 0.5)).clamp(0.0, 1.0);
    }

    pub fn age_hours(&self) -> f64 {
        let now = Utc::now().timestamp_millis() as u64;
        (now.saturating_sub(self.updated_at)) as f64 / 3_600_000.0
    }

    pub fn is_stale(&self, threshold_hours: f64) -> bool {
        self.age_hours() > threshold_hours
    }

    pub fn is_strong(&self, threshold: f32) -> bool {
        self.weight.abs() >= threshold
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct MicroWeightStore {
    weights: Vec<MicroWeight>,
}

impl MicroWeightStore {
    pub fn new() -> Self {
        Self { weights: Vec::new() }
    }

    pub fn add(&mut self, mw: MicroWeight) {
        self.weights.push(mw);
    }

    pub fn find(&self, from: &str, to: &str) -> Option<&MicroWeight> {
        self.weights.iter().find(|w| w.from == from && w.to == to)
    }

    pub fn find_mut(&mut self, from: &str, to: &str) -> Option<&mut MicroWeight> {
        self.weights.iter_mut().find(|w| w.from == from && w.to == to)
    }

    pub fn get_or_create(&mut self, from: &str, to: &str, default_weight: f32) -> &mut MicroWeight {
        if !self.weights.iter().any(|w| w.from == from && w.to == to) {
            self.weights.push(MicroWeight::new(from, to, default_weight));
        }
        self.weights.iter_mut().find(|w| w.from == from && w.to == to).unwrap()
    }

    pub fn reinforce(&mut self, from: &str, to: &str, amount: f32) {
        let mw = self.get_or_create(from, to, 0.0);
        mw.reinforce(amount);
    }

    pub fn weaken(&mut self, from: &str, to: &str, amount: f32) {
        if let Some(mw) = self.find_mut(from, to) {
            mw.weaken(amount);
        }
    }

    pub fn decay_all(&mut self, decay_rate: f32) {
        for mw in &mut self.weights {
            mw.auto_decay(decay_rate);
        }
    }

    pub fn prune_stale(&mut self, threshold_hours: f64) {
        self.weights.retain(|w| !w.is_stale(threshold_hours));
    }

    pub fn strongest(&self, n: usize) -> Vec<&MicroWeight> {
        let mut sorted: Vec<&MicroWeight> = self.weights.iter().collect();
        sorted.sort_by(|a, b| b.weight.abs().partial_cmp(&a.weight.abs()).unwrap());
        sorted.into_iter().take(n).collect()
    }

    pub fn by_source(&self, from: &str) -> Vec<&MicroWeight> {
        self.weights.iter().filter(|w| w.from == from).collect()
    }

    pub fn by_target(&self, to: &str) -> Vec<&MicroWeight> {
        self.weights.iter().filter(|w| w.to == to).collect()
    }

    pub fn len(&self) -> usize {
        self.weights.len()
    }

    pub fn is_empty(&self) -> bool {
        self.weights.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_micro_weight_creation() {
        let mw = MicroWeight::new("concept_a", "concept_b", 0.5);
        assert_eq!(mw.from, "concept_a");
        assert_eq!(mw.to, "concept_b");
        assert_eq!(mw.weight, 0.5);
        assert_eq!(mw.use_count, 0);
    }

    #[test]
    fn test_reinforce() {
        let mut mw = MicroWeight::new("a", "b", 0.0);
        mw.reinforce(0.3);
        assert!((mw.weight - 0.3).abs() < 0.001);
        assert_eq!(mw.use_count, 1);
        mw.reinforce(0.5);
        assert!((mw.weight - 0.8).abs() < 0.001);
        assert_eq!(mw.use_count, 2);
    }

    #[test]
    fn test_clamp() {
        let mut mw = MicroWeight::new("a", "b", 0.9);
        mw.reinforce(0.5);
        assert_eq!(mw.weight, 1.0); // clamped
    }

    #[test]
    fn test_weaken() {
        let mut mw = MicroWeight::new("a", "b", 0.5);
        mw.weaken(0.3);
        assert!((mw.weight - 0.2).abs() < 0.001);
    }

    #[test]
    fn test_negative_weight() {
        let mw = MicroWeight::new("a", "b", -0.5);
        assert_eq!(mw.weight, -0.5);
    }

    #[test]
    fn test_store_operations() {
        let mut store = MicroWeightStore::new();
        store.add(MicroWeight::new("x", "y", 0.5));
        store.add(MicroWeight::new("y", "z", 0.3));

        assert_eq!(store.len(), 2);
        assert!(store.find("x", "y").is_some());
        assert!(store.find("x", "z").is_none());

        store.reinforce("x", "y", 0.1);
        let mw = store.find("x", "y").unwrap();
        assert!((mw.weight - 0.6).abs() < 0.001);
    }

    #[test]
    fn test_store_strongest() {
        let mut store = MicroWeightStore::new();
        store.add(MicroWeight::new("a", "b", 0.1));
        store.add(MicroWeight::new("c", "d", 0.9));
        store.add(MicroWeight::new("e", "f", 0.5));

        let top = store.strongest(2);
        assert_eq!(top.len(), 2);
        assert_eq!(top[0].weight, 0.9);
    }

    #[test]
    fn test_store_by_source_target() {
        let mut store = MicroWeightStore::new();
        store.add(MicroWeight::new("a", "b", 0.5));
        store.add(MicroWeight::new("a", "c", 0.3));
        store.add(MicroWeight::new("d", "b", 0.7));

        assert_eq!(store.by_source("a").len(), 2);
        assert_eq!(store.by_target("b").len(), 2);
    }

    #[test]
    fn test_prune_stale() {
        let mut store = MicroWeightStore::new();
        let mut stale = MicroWeight::new("a", "b", 0.5);
        stale.updated_at = 0; // very old
        store.add(stale);
        store.add(MicroWeight::new("c", "d", 0.3));

        store.prune_stale(1.0); // remove anything older than 1 hour
        assert_eq!(store.len(), 1);
    }
}
