use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EstimateItem {
    pub id: String,
    pub section: String,
    pub name: String,
    pub unit: String,
    pub quantity: f64,
    pub unit_price: f64,
    pub total: f64,
    pub note: String,
}

impl EstimateItem {
    pub fn new(section: &str, name: &str, unit: &str, quantity: f64, unit_price: f64) -> Self {
        Self {
            id: uuid::Uuid::new_v4().to_string()[..8].to_string(),
            section: section.to_string(),
            name: name.to_string(),
            unit: unit.to_string(),
            quantity,
            unit_price,
            total: (quantity * unit_price * 100.0).round() / 100.0,
            note: String::new(),
        }
    }

    pub fn recalculate(&mut self) {
        self.total = (self.quantity * self.unit_price * 100.0).round() / 100.0;
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EstimateTotals {
    pub works: f64,
    pub materials: f64,
    pub delivery: f64,
    pub discount: f64,
    pub grand_total: f64,
}

impl Default for EstimateTotals {
    fn default() -> Self {
        Self { works: 0.0, materials: 0.0, delivery: 0.0, discount: 0.0, grand_total: 0.0 }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClientInfo {
    pub name: String,
    pub phone: String,
    pub address: String,
}

impl Default for ClientInfo {
    fn default() -> Self {
        Self { name: String::new(), phone: String::new(), address: String::new() }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ObjectInfo {
    pub object_type: String,
    pub area: f64,
    pub location: String,
}

impl Default for ObjectInfo {
    fn default() -> Self {
        Self { object_type: String::new(), area: 0.0, location: String::new() }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Estimate {
    pub estimate_id: String,
    pub title: String,
    pub client: ClientInfo,
    pub object: ObjectInfo,
    pub items: Vec<EstimateItem>,
    pub totals: EstimateTotals,
    pub assumptions: Vec<String>,
    pub warnings: Vec<String>,
    pub version: u32,
}

impl Estimate {
    pub fn new(title: &str) -> Self {
        Self {
            estimate_id: uuid::Uuid::new_v4().to_string()[..8].to_string(),
            title: title.to_string(),
            client: ClientInfo::default(),
            object: ObjectInfo::default(),
            items: Vec::new(),
            totals: EstimateTotals::default(),
            assumptions: Vec::new(),
            warnings: Vec::new(),
            version: 1,
        }
    }

    pub fn add_item(&mut self, item: EstimateItem) {
        self.items.push(item);
        self.recalculate();
    }

    pub fn remove_item(&mut self, item_id: &str) -> bool {
        let len_before = self.items.len();
        self.items.retain(|i| i.id != item_id);
        if self.items.len() < len_before {
            self.recalculate();
            true
        } else {
            false
        }
    }

    pub fn recalculate(&mut self) {
        self.totals.works = self.items.iter()
            .filter(|i| i.section.to_lowercase().contains("работ") || i.section.to_lowercase().contains("work"))
            .map(|i| i.total)
            .sum();

        self.totals.materials = self.items.iter()
            .filter(|i| i.section.to_lowercase().contains("материал") || i.section.to_lowercase().contains("mater"))
            .map(|i| i.total)
            .sum();

        let subtotal: f64 = self.items.iter().map(|i| i.total).sum();
        self.totals.grand_total = subtotal + self.totals.delivery - self.totals.discount;
        self.totals.grand_total = (self.totals.grand_total * 100.0).round() / 100.0;
    }

    pub fn item_count(&self) -> usize {
        self.items.len()
    }

    pub fn sections(&self) -> Vec<String> {
        let mut sections: Vec<String> = self.items.iter().map(|i| i.section.clone()).collect();
        sections.sort();
        sections.dedup();
        sections
    }

    pub fn quick_calc_works(area_m2: f64, rate_per_m2: f64) -> f64 {
        (area_m2 * rate_per_m2 * 100.0).round() / 100.0
    }
}

pub struct EstimateEngine;

impl EstimateEngine {
    pub fn create_estimate(title: &str) -> Estimate {
        Estimate::new(title)
    }

    pub fn add_work_item(
        estimate: &mut Estimate,
        name: &str,
        unit: &str,
        quantity: f64,
        unit_price: f64,
    ) {
        estimate.add_item(EstimateItem::new("Работы", name, unit, quantity, unit_price));
    }

    pub fn add_material_item(
        estimate: &mut Estimate,
        name: &str,
        unit: &str,
        quantity: f64,
        unit_price: f64,
    ) {
        estimate.add_item(EstimateItem::new("Материалы", name, unit, quantity, unit_price));
    }

    pub fn to_json(estimate: &Estimate) -> String {
        serde_json::to_string_pretty(estimate).unwrap_or_else(|_| "{}".to_string())
    }

    pub fn from_json(json: &str) -> Result<Estimate, String> {
        serde_json::from_str(json).map_err(|e| e.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_estimate_creation() {
        let est = Estimate::new("Ремонт комнаты");
        assert_eq!(est.title, "Ремонт комнаты");
        assert_eq!(est.item_count(), 0);
        assert_eq!(est.version, 1);
    }

    #[test]
    fn test_add_items_and_recalculate() {
        let mut est = Estimate::new("Test");
        est.add_item(EstimateItem::new("Работы", "Штукатурка", "м2", 50.0, 350.0));
        est.add_item(EstimateItem::new("Материалы", "Шпаклёвка", "кг", 20.0, 80.0));
        assert_eq!(est.item_count(), 2);
        assert_eq!(est.totals.works, 17500.0);
        assert_eq!(est.totals.materials, 1600.0);
        assert_eq!(est.totals.grand_total, 19100.0);
    }

    #[test]
    fn test_remove_item() {
        let mut est = Estimate::new("Test");
        let item = EstimateItem::new("Работы", "Paint", "m2", 10.0, 100.0);
        let id = item.id.clone();
        est.add_item(item);
        assert_eq!(est.item_count(), 1);
        est.remove_item(&id);
        assert_eq!(est.item_count(), 0);
        assert_eq!(est.totals.grand_total, 0.0);
    }

    #[test]
    fn test_quick_calc() {
        let result = Estimate::quick_calc_works(18.0, 3500.0);
        assert_eq!(result, 63000.0);
    }

    #[test]
    fn test_json_roundtrip() {
        let mut est = Estimate::new("JSON Test");
        est.client.name = "Иван".to_string();
        est.add_item(EstimateItem::new("Работы", "Test", "м2", 10.0, 500.0));
        let json = EstimateEngine::to_json(&est);
        let restored = EstimateEngine::from_json(&json).unwrap();
        assert_eq!(restored.title, "JSON Test");
        assert_eq!(restored.client.name, "Иван");
        assert_eq!(restored.item_count(), 1);
    }

    #[test]
    fn test_sections() {
        let mut est = Estimate::new("Test");
        est.add_item(EstimateItem::new("Работы", "A", "м2", 1.0, 1.0));
        est.add_item(EstimateItem::new("Материалы", "B", "кг", 1.0, 1.0));
        est.add_item(EstimateItem::new("Работы", "C", "м2", 1.0, 1.0));
        let sections = est.sections();
        assert_eq!(sections.len(), 2);
    }
}
