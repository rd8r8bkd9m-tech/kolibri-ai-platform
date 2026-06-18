use chrono::Utc;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Association {
    pub id: String,
    pub from: String,
    pub to: String,
    pub relation: String,
    pub weight: f32,
    pub confidence: f32,
    pub created_at: u64,
}

impl Association {
    pub fn new(from: &str, to: &str, relation: &str) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            from: from.to_string(),
            to: to.to_string(),
            relation: relation.to_string(),
            weight: 1.0,
            confidence: 0.5,
            created_at: Utc::now().timestamp_millis() as u64,
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

    pub fn matches(&self, entity: &str) -> bool {
        self.from == entity || self.to == entity
    }
}

#[derive(Debug, Default)]
pub struct AssociationGraph {
    pub links: Vec<Association>,
}

impl AssociationGraph {
    pub fn new() -> Self {
        Self { links: Vec::new() }
    }

    pub fn add(&mut self, assoc: Association) {
        self.links.push(assoc);
    }

    pub fn find_by_entity(&self, entity: &str) -> Vec<&Association> {
        self.links.iter().filter(|a| a.matches(entity)).collect()
    }

    pub fn find_by_relation(&self, relation: &str) -> Vec<&Association> {
        self.links.iter().filter(|a| a.relation == relation).collect()
    }

    pub fn strongest(&self, entity: &str) -> Option<&Association> {
        self.find_by_entity(entity)
            .into_iter()
            .max_by(|a, b| a.weight.partial_cmp(&b.weight).unwrap_or(std::cmp::Ordering::Equal))
    }

    pub fn len(&self) -> usize {
        self.links.len()
    }

    pub fn is_empty(&self) -> bool {
        self.links.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_association_creation() {
        let a = Association::new("estimate-1", "client-1", "belongs_to");
        assert_eq!(a.from, "estimate-1");
        assert_eq!(a.to, "client-1");
        assert_eq!(a.relation, "belongs_to");
        assert_eq!(a.weight, 1.0);
    }

    #[test]
    fn test_graph_operations() {
        let mut graph = AssociationGraph::new();
        graph.add(Association::new("task-1", "estimate-1", "created"));
        graph.add(Association::new("task-1", "doc-1", "generated"));
        graph.add(Association::new("estimate-1", "client-1", "belongs_to"));

        assert_eq!(graph.len(), 3);
        assert_eq!(graph.find_by_entity("task-1").len(), 2);
        assert_eq!(graph.find_by_entity("client-1").len(), 1);
        assert_eq!(graph.find_by_relation("created").len(), 1);
    }

    #[test]
    fn test_strongest_link() {
        let mut graph = AssociationGraph::new();
        graph.add(Association::new("a", "b", "weak").with_weight(0.5));
        graph.add(Association::new("a", "c", "strong").with_weight(5.0));

        let strongest = graph.strongest("a").unwrap();
        assert_eq!(strongest.to, "c");
    }
}
