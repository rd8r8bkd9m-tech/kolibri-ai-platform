use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CapabilityEvidence {
    pub id: String,
    pub route: bool,
    pub executor: bool,
    pub renderer: bool,
    pub evidence: bool,
    pub roles: BTreeSet<String>,
}

impl CapabilityEvidence {
    pub fn visible_for(&self, role: &str) -> bool {
        self.route && self.executor && self.renderer && self.evidence && self.roles.contains(role)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn capability_requires_all_four_evidence_gates() {
        let mut roles = BTreeSet::new();
        roles.insert("client".to_owned());
        let item = CapabilityEvidence {
            id: "estimates".into(),
            route: true,
            executor: true,
            renderer: true,
            evidence: true,
            roles,
        };
        assert!(item.visible_for("client"));
        assert!(!item.visible_for("owner"));
    }
}
