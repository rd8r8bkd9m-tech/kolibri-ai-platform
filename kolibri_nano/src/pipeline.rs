use serde::{Deserialize, Serialize};
use crate::estimate_engine::{Estimate, EstimateItem, EstimateEngine};

// ─── Building & Structure Types ───

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub enum BuildingType {
    #[default]
    Unknown,
    Warehouse,      // склад
    Office,         // офис
    Residential,    // жилой дом
    Hospital,       // больница
    School,         // школа
    Shop,           // магазин
    Factory,        // завод
    Garage,         // гараж
    Bathhouse,      // баня
    Cafe,           // кафе
    Warehouse2,     // ангар
    Warehouse3,     // цех
    Warehouse4,     // подвал
    Warehouse5,     // мансарда
    Warehouse6,     // пристройка
    Warehouse7,     // теплица
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub enum StructureType {
    #[default]
    Unknown,
    MetalFrame,     // металлокаркас
    Concrete,       // бетон
    Brick,          // кирпич
    Wood,           // дерево
    Block,          // блок
    Monolith,       // монолит
    Frame,          // каркас
    Combined,       // комбинированный
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum WorkCategory {
    Preparatory,    // подготовительные
    Earthwork,      // земляные
    Foundation,     // фундамент
    Concrete,       // бетонные
    Metal,          // металлоконструкции
    Walls,          // стены
    Roofing,        // кровля
    Flooring,       // полы
    Finishing,      // отделка
    Engineering,    // инженерные
    Landscaping,    // благоустройство
    Demolition,     // демонтаж
}

// ─── Parsed Construction Params ───

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ConstructionParams {
    pub building_type: BuildingType,
    pub structure_type: StructureType,
    pub work_types: Vec<WorkCategory>,
    pub length: Option<f64>,
    pub width: Option<f64>,
    pub height: Option<f64>,
    pub area: Option<f64>,
    pub volume: Option<f64>,
    pub floors: Option<u32>,
    pub materials: Vec<String>,
    pub location: Option<String>,
    pub climate_zone: Option<u32>,
    pub ground_conditions: Option<String>,
    pub seismicity: Option<f64>,
}

// ─── GESN Normative ───

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Normative {
    pub code: String,
    pub name: String,
    pub unit: String,
    pub labor_cost: f64,
    pub material_cost: f64,
    pub machine_cost: f64,
    pub total_cost: f64,
    pub labor_hours: f64,
    pub labor_days: f64,
    pub description: String,
    pub typical_use: String,
    pub keywords: Vec<String>,
}

// ─── Validation Report ───

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ValidationReport {
    pub is_valid: bool,
    pub errors: Vec<ValidationIssue>,
    pub warnings: Vec<ValidationIssue>,
    pub score: f64,
    pub checks: Vec<CheckResult>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ValidationIssue {
    pub check: String,
    pub message: String,
    pub severity: Severity,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Severity {
    Error,
    Warning,
    Info,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CheckResult {
    pub name: String,
    pub passed: bool,
    pub message: String,
}

// ─── Pipeline Result ───

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipelineResult {
    pub estimate: Estimate,
    pub params: ConstructionParams,
    pub validation: ValidationReport,
    pub match_rate: f64,
    pub agent_traces: Vec<AgentTrace>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentTrace {
    pub agent: String,
    pub action: String,
    pub duration_ms: u64,
    pub output_summary: String,
}

// ─── 1. ParserAgent ───

pub struct ParserAgent;

impl ParserAgent {
    pub fn parse(text: &str) -> ConstructionParams {
        let lower = text.to_lowercase();
        let mut params = ConstructionParams::default();

        // Building type detection
        params.building_type = if lower.contains("склад") || lower.contains("warehouse") {
            BuildingType::Warehouse
        } else if lower.contains("офис") || lower.contains("office") {
            BuildingType::Office
        } else if lower.contains("жилой") || lower.contains("дом") || lower.contains("квартира") {
            BuildingType::Residential
        } else if lower.contains("больниц") || lower.contains("hospital") {
            BuildingType::Hospital
        } else if lower.contains("школ") || lower.contains("school") {
            BuildingType::School
        } else if lower.contains("магазин") || lower.contains("shop") || lower.contains("торгов") {
            BuildingType::Shop
        } else if lower.contains("завод") || lower.contains("фабрик") || lower.contains("цех") {
            BuildingType::Factory
        } else if lower.contains("гараж") || lower.contains("garage") {
            BuildingType::Garage
        } else if lower.contains("баня") || lower.contains("саун") {
            BuildingType::Bathhouse
        } else if lower.contains("кафе") || lower.contains("ресторан") {
            BuildingType::Cafe
        } else if lower.contains("ангар") {
            BuildingType::Warehouse2
        } else if lower.contains("подвал") {
            BuildingType::Warehouse4
        } else if lower.contains("мансард") {
            BuildingType::Warehouse5
        } else if lower.contains("пристрой") {
            BuildingType::Warehouse6
        } else if lower.contains("теплиц") {
            BuildingType::Warehouse7
        } else {
            BuildingType::Unknown
        };

        // Structure type detection — find earliest match in text
        let structure_candidates: Vec<(&str, StructureType)> = vec![
            ("металлокаркас", StructureType::MetalFrame),
            ("metal frame", StructureType::MetalFrame),
            ("железобетон", StructureType::Concrete),
            ("монолит", StructureType::Monolith),
            ("monolith", StructureType::Monolith),
            ("кирпич", StructureType::Brick),
            ("brick", StructureType::Brick),
            ("газобетон", StructureType::Block),
            ("пеноблок", StructureType::Block),
            ("блок", StructureType::Block),
            ("брус", StructureType::Wood),
            ("дерев", StructureType::Wood),
            ("wood", StructureType::Wood),
            ("бетон", StructureType::Concrete),
            ("комбинир", StructureType::Combined),
            ("combined", StructureType::Combined),
            ("каркас", StructureType::Frame),
            ("frame", StructureType::Frame),
        ];
        params.structure_type = structure_candidates
            .iter()
            .filter_map(|(kw, st)| lower.find(kw).map(|pos| (pos, st.clone())))
            .min_by_key(|(pos, _)| *pos)
            .map(|(_, st)| st)
            .unwrap_or_default();

        // Work types detection
        let work_keywords = vec![
            (WorkCategory::Preparatory, vec!["подготов", "демонтаж", "снос", "очистк"]),
            (WorkCategory::Earthwork, vec!["землян", "копать", "котлован", "траншея", "планиров"]),
            (WorkCategory::Foundation, vec!["фундамент", "основани", "свай"]),
            (WorkCategory::Concrete, vec!["бетон", "залив", "арматур", "опалуб"]),
            (WorkCategory::Metal, vec!["металл", "сварк", "балк", "ферм"]),
            (WorkCategory::Walls, vec!["стен", "кладк", "перегород", "кирпич"]),
            (WorkCategory::Roofing, vec!["кровл", "крыш", "чердак", "утеплен"]),
            (WorkCategory::Flooring, vec!["пол", "стяжк", "наливн", "плит"]),
            (WorkCategory::Finishing, vec!["отдел", "штукатур", "шпаклев", "покрас", "обоев"]),
            (WorkCategory::Engineering, vec!["электр", "водопров", "канализац", "отоплен", "вентиляц", "сантех"]),
            (WorkCategory::Landscaping, vec!["благоустр", "забор", "дорож", "озелен"]),
            (WorkCategory::Demolition, vec!["демонтаж", "снос", "разбор"]),
        ];

        for (category, keywords) in work_keywords {
            if keywords.iter().any(|kw| lower.contains(kw)) {
                params.work_types.push(category);
            }
        }

        // Dimensions extraction
        params.area = Self::extract_number(&lower, &["площад", "м2", "м²", "кв.м", "кв м"]);
        params.volume = Self::extract_number(&lower, &["объем", "объём", "м3", "м³"]);
        params.length = Self::extract_number(&lower, &["длин", "length"]);
        params.width = Self::extract_number(&lower, &["ширина", "width"]);
        params.height = Self::extract_number(&lower, &["высот", "height"]);

        // Floors
        if let Some(f) = Self::extract_number(&lower, &["этаж", "floor"]) {
            params.floors = Some(f as u32);
        }

        // Materials detection
        let material_keywords = vec![
            "кирпич", "бетон", "дерево", "брус", "блок", "газобетон",
            "пеноблок", "металл", "профнастил", "шифер", "черепиц",
            "минвата", "пенопласт", "гипсокартон", "плитк",
        ];
        for mat in material_keywords {
            if lower.contains(mat) {
                params.materials.push(mat.to_string());
            }
        }

        // Location
        if let Some(loc) = Self::extract_location(&lower) {
            params.location = Some(loc);
        }

        params
    }

    fn extract_number(text: &str, keywords: &[&str]) -> Option<f64> {
        for keyword in keywords {
            if let Some(pos) = text.find(keyword) {
                let before = &text[..pos];
                // Look for number before keyword (scan backwards)
                let num_str: String = before.trim_end().chars().rev().take_while(|c| c.is_ascii_digit() || *c == '.' || *c == ',').collect();
                let num_str: String = num_str.chars().rev().collect();
                if !num_str.is_empty() {
                    if let Ok(num) = num_str.replace(',', ".").parse::<f64>() {
                        if num > 0.0 {
                            return Some(num);
                        }
                    }
                }
                // Look for number after keyword
                let after = &text[pos + keyword.len()..];
                let num_str: String = after.trim_start().chars().take_while(|c| c.is_ascii_digit() || *c == '.' || *c == ',').collect();
                if !num_str.is_empty() {
                    if let Ok(num) = num_str.replace(',', ".").parse::<f64>() {
                        if num > 0.0 {
                            return Some(num);
                        }
                    }
                }
            }
        }
        None
    }

    fn extract_location(text: &str) -> Option<String> {
        let location_markers = vec!["город", "г.", "поселок", "пос.", "село", "деревня", "ул.", "улица"];
        for marker in location_markers {
            if let Some(pos) = text.find(marker) {
                let rest = &text[pos..];
                let loc: String = rest.chars().take(50).collect();
                return Some(loc.trim().to_string());
            }
        }
        None
    }
}

// ─── 2. ClassifierAgent ───

pub struct ClassifierAgent;

impl ClassifierAgent {
    pub fn classify(params: &ConstructionParams) -> Vec<(WorkCategory, Vec<&'static str>)> {
        let mut result = Vec::new();

        // Always include preparatory if demolition needed
        if params.work_types.contains(&WorkCategory::Demolition) || params.work_types.contains(&WorkCategory::Preparatory) {
            result.push((WorkCategory::Preparatory, vec![
                "GESN-01-001", "GESN-01-002", "GESN-01-003",
            ]));
        }

        // Earthwork
        if params.work_types.contains(&WorkCategory::Earthwork) {
            result.push((WorkCategory::Earthwork, vec![
                "GESN-02-001", "GESN-02-002", "GESN-02-003",
            ]));
        }

        // Foundation
        if params.work_types.contains(&WorkCategory::Foundation) || params.building_type != BuildingType::Unknown {
            result.push((WorkCategory::Foundation, vec![
                "GESN-03-001", "GESN-03-002", "GESN-03-003",
            ]));
        }

        // Concrete
        if params.work_types.contains(&WorkCategory::Concrete) {
            result.push((WorkCategory::Concrete, vec![
                "GESN-04-001", "GESN-04-002", "GESN-04-003",
            ]));
        }

        // Metal
        if params.work_types.contains(&WorkCategory::Metal) || params.structure_type == StructureType::MetalFrame {
            result.push((WorkCategory::Metal, vec![
                "GESN-05-001", "GESN-05-002",
            ]));
        }

        // Walls
        if params.work_types.contains(&WorkCategory::Walls) {
            result.push((WorkCategory::Walls, vec![
                "GESN-06-001", "GESN-06-002", "GESN-06-003",
            ]));
        }

        // Roofing
        if params.work_types.contains(&WorkCategory::Roofing) {
            result.push((WorkCategory::Roofing, vec![
                "GESN-07-001", "GESN-07-002",
            ]));
        }

        // Flooring
        if params.work_types.contains(&WorkCategory::Flooring) {
            result.push((WorkCategory::Flooring, vec![
                "GESN-08-001", "GESN-08-002", "GESN-08-003",
            ]));
        }

        // Finishing
        if params.work_types.contains(&WorkCategory::Finishing) {
            result.push((WorkCategory::Finishing, vec![
                "GESN-09-001", "GESN-09-002", "GESN-09-003", "GESN-09-004",
            ]));
        }

        // Engineering
        if params.work_types.contains(&WorkCategory::Engineering) {
            result.push((WorkCategory::Engineering, vec![
                "GESN-10-001", "GESN-10-002", "GESN-10-003",
            ]));
        }

        // Landscaping
        if params.work_types.contains(&WorkCategory::Landscaping) {
            result.push((WorkCategory::Landscaping, vec![
                "GESN-11-001", "GESN-11-002",
            ]));
        }

        // Default: if no work types detected, add finishing basics
        if result.is_empty() {
            result.push((WorkCategory::Finishing, vec![
                "GESN-09-001", "GESN-09-002", "GESN-09-003",
            ]));
        }

        result
    }
}

// ─── 3. NormativeAgent ───

pub struct NormativeAgent;

impl NormativeAgent {
    pub fn match_normatives(
        categories: &[(WorkCategory, Vec<&str>)],
        seed_normatives: &[Normative],
    ) -> (Vec<Normative>, f64) {
        let mut matched = Vec::new();
        let mut total_codes = 0;
        let mut matched_codes = 0;

        for (_category, codes) in categories {
            for code in codes {
                total_codes += 1;

                // Tier 1: exact code match
                if let Some(norm) = seed_normatives.iter().find(|n| n.code == *code) {
                    matched.push(norm.clone());
                    matched_codes += 1;
                    continue;
                }

                // Tier 2: keyword search
                let code_prefix = code.split('-').take(2).collect::<Vec<_>>().join("-");
                if let Some(norm) = seed_normatives.iter().find(|n| n.code.starts_with(&code_prefix)) {
                    matched.push(norm.clone());
                    matched_codes += 1;
                    continue;
                }

                // Tier 3: fuzzy name match (simplified)
                let code_num: String = code.chars().filter(|c| c.is_ascii_digit()).collect();
                if let Some(norm) = seed_normatives.iter().find(|n| {
                    let n_num: String = n.code.chars().filter(|c| c.is_ascii_digit()).collect();
                    n_num == code_num
                }) {
                    matched.push(norm.clone());
                    matched_codes += 1;
                }
            }
        }

        let match_rate = if total_codes > 0 {
            matched_codes as f64 / total_codes as f64
        } else {
            0.0
        };

        (matched, match_rate)
    }
}

// ─── 4. CalculatorAgent ───

pub struct CalculatorAgent;

impl CalculatorAgent {
    pub fn calculate(
        params: &ConstructionParams,
        normatives: &[Normative],
    ) -> Vec<EstimateItem> {
        let area = params.area.unwrap_or(100.0);
        let volume = params.volume.unwrap_or(area * 3.0); // default height 3m
        let floors = params.floors.unwrap_or(1) as f64;

        let mut items = Vec::new();

        for norm in normatives {
            let quantity = Self::estimate_quantity(norm, area, volume, floors);
            let item = EstimateItem::new(
                &Self::category_from_code(&norm.code),
                &norm.name,
                &norm.unit,
                quantity,
                norm.total_cost,
            );
            items.push(item);
        }

        // Add overhead and profit
        let works_total: f64 = items.iter().map(|i| i.total).sum();
        let overhead = works_total * 0.15; // 15% overhead
        let profit = (works_total + overhead) * 0.10; // 10% profit

        items.push(EstimateItem::new(
            "Накладные расходы",
            "Накладные расходы (15%)",
            "%",
            15.0,
            overhead / 15.0 * 100.0,
        ));

        items.push(EstimateItem::new(
            "Сметная прибыль",
            "Сметная прибыль (10%)",
            "%",
            10.0,
            profit / 10.0 * 100.0,
        ));

        items
    }

    fn estimate_quantity(norm: &Normative, area: f64, volume: f64, floors: f64) -> f64 {
        let code = norm.code.to_lowercase();

        // Heuristic coefficients based on work type
        if code.contains("01") || code.contains("02") {
            // Earthwork/excavation: 0.15 of volume
            (volume * 0.15 * 100.0).round() / 100.0
        } else if code.contains("03") {
            // Foundation: 0.06 of area
            (area * 0.06 * 100.0).round() / 100.0
        } else if code.contains("04") {
            // Concrete: 0.08 of area
            (area * 0.08 * 100.0).round() / 100.0
        } else if code.contains("05") {
            // Metal: 0.025 tons/m2
            (area * 0.025 * 100.0).round() / 100.0
        } else if code.contains("06") {
            // Walls: area * floors
            (area * floors * 0.5 * 100.0).round() / 100.0
        } else if code.contains("07") {
            // Roofing: area
            area
        } else if code.contains("08") {
            // Flooring: area
            area
        } else if code.contains("09") {
            // Finishing: 2.8x area for plaster, 3x for paint
            if norm.name.to_lowercase().contains("штукатур") || norm.name.to_lowercase().contains("пласт") {
                (area * 2.8 * 100.0).round() / 100.0
            } else if norm.name.to_lowercase().contains("крас") {
                (area * 3.0 * 100.0).round() / 100.0
            } else {
                area
            }
        } else if code.contains("10") {
            // Engineering: 0.3 of area per system
            (area * 0.3 * 100.0).round() / 100.0
        } else {
            area
        }
    }

    fn category_from_code(code: &str) -> String {
        let s = if code.contains("01") { "Подготовительные работы" }
        else if code.contains("02") { "Земляные работы" }
        else if code.contains("03") { "Фундамент" }
        else if code.contains("04") { "Бетонные работы" }
        else if code.contains("05") { "Металлоконструкции" }
        else if code.contains("06") { "Стены" }
        else if code.contains("07") { "Кровля" }
        else if code.contains("08") { "Полы" }
        else if code.contains("09") { "Отделочные работы" }
        else if code.contains("10") { "Инженерные системы" }
        else if code.contains("11") { "Благоустройство" }
        else { "Прочее" };
        s.to_string()
    }
}

// ─── 5. ValidatorAgent ───

pub struct ValidatorAgent;

impl ValidatorAgent {
    pub fn validate(
        estimate: &Estimate,
        params: &ConstructionParams,
    ) -> ValidationReport {
        let mut checks = Vec::new();
        let mut errors = Vec::new();
        let mut warnings = Vec::new();

        // Check 1: Critical works presence
        let has_critical = estimate.items.iter().any(|i|
            i.section.contains("Фундамент") || i.section.contains("Стены") || i.section.contains("Кровля")
        );
        checks.push(CheckResult {
            name: "Наличие критических работ".to_string(),
            passed: has_critical,
            message: if has_critical {
                "Фундамент, стены и кровля присутствуют".to_string()
            } else {
                "Отсутствуют критические работы (фундамент, стены, кровля)".to_string()
            },
        });
        if !has_critical {
            warnings.push(ValidationIssue {
                check: "critical_works".to_string(),
                message: "Отсутствуют критические работы".to_string(),
                severity: Severity::Warning,
            });
        }

        // Check 2: Price reasonableness (cost/m2 bounds)
        if let Some(area) = params.area {
            if area > 0.0 {
                let cost_per_m2 = estimate.totals.grand_total / area;
                let reasonable = cost_per_m2 > 500.0 && cost_per_m2 < 100000.0;
                checks.push(CheckResult {
                    name: "Разумность цены за м2".to_string(),
                    passed: reasonable,
                    message: format!("{:.0} руб/м2", cost_per_m2),
                });
                if !reasonable {
                    warnings.push(ValidationIssue {
                        check: "price_reasonableness".to_string(),
                        message: format!("Неразумная цена: {:.0} руб/м2", cost_per_m2),
                        severity: Severity::Warning,
                    });
                }
            }
        }

        // Check 3: Quantity anomalies
        let has_anomaly = estimate.items.iter().any(|i| i.quantity <= 0.0 || i.quantity > 100000.0);
        checks.push(CheckResult {
            name: "Аномалии количеств".to_string(),
            passed: !has_anomaly,
            message: if has_anomaly {
                "Обнаружены нулевые или слишком большие количества".to_string()
            } else {
                "Количества в норме".to_string()
            },
        });
        if has_anomaly {
            errors.push(ValidationIssue {
                check: "quantity_anomaly".to_string(),
                message: "Аномальные количества".to_string(),
                severity: Severity::Error,
            });
        }

        // Check 4: Cost structure ratios
        let total = estimate.totals.grand_total;
        if total > 0.0 {
            let works_ratio = estimate.totals.works / total;
            let reasonable_ratio = works_ratio > 0.15 && works_ratio < 0.65;
            checks.push(CheckResult {
                name: "Структура затрат".to_string(),
                passed: reasonable_ratio,
                message: format!("Доля работ: {:.0}%", works_ratio * 100.0),
            });
            if !reasonable_ratio {
                warnings.push(ValidationIssue {
                    check: "cost_structure".to_string(),
                    message: format!("Доля работ {:.0}% вне нормы (15-65%)", works_ratio * 100.0),
                    severity: Severity::Warning,
                });
            }
        }

        // Check 5: Labor consistency
        let has_items = !estimate.items.is_empty();
        checks.push(CheckResult {
            name: "Трудозатраты".to_string(),
            passed: has_items,
            message: if has_items {
                format!("{} позиций в смете", estimate.items.len())
            } else {
                "Смета пуста".to_string()
            },
        });

        // Check 6: Completeness
        let section_count = estimate.sections().len();
        let complete = section_count >= 2;
        checks.push(CheckResult {
            name: "Полнота сметы".to_string(),
            passed: complete,
            message: format!("{} разделов", section_count),
        });
        if !complete {
            warnings.push(ValidationIssue {
                check: "completeness".to_string(),
                message: "Менее 2 разделов — смета неполная".to_string(),
                severity: Severity::Warning,
            });
        }

        let passed_count = checks.iter().filter(|c| c.passed).count();
        let score = passed_count as f64 / checks.len() as f64 * 100.0;

        ValidationReport {
            is_valid: errors.is_empty(),
            errors,
            warnings,
            score,
            checks,
        }
    }
}

// ─── Pipeline Orchestrator ───

pub struct EstimatePipeline;

impl EstimatePipeline {
    pub fn run(
        text: &str,
        seed_normatives: &[Normative],
    ) -> PipelineResult {
        let mut traces = Vec::new();
        let _start = std::time::Instant::now();

        // Step 1: Parse
        let t1 = std::time::Instant::now();
        let params = ParserAgent::parse(text);
        traces.push(AgentTrace {
            agent: "ParserAgent".to_string(),
            action: "parse".to_string(),
            duration_ms: t1.elapsed().as_millis() as u64,
            output_summary: format!(
                "building={:?}, structure={:?}, area={:?}, work_types={}",
                params.building_type, params.structure_type, params.area, params.work_types.len()
            ),
        });

        // Step 2: Classify
        let t2 = std::time::Instant::now();
        let categories = ClassifierAgent::classify(&params);
        traces.push(AgentTrace {
            agent: "ClassifierAgent".to_string(),
            action: "classify".to_string(),
            duration_ms: t2.elapsed().as_millis() as u64,
            output_summary: format!("{} categories", categories.len()),
        });

        // Step 3: Match normatives
        let t3 = std::time::Instant::now();
        let (normatives, match_rate) = NormativeAgent::match_normatives(&categories, seed_normatives);
        traces.push(AgentTrace {
            agent: "NormativeAgent".to_string(),
            action: "match".to_string(),
            duration_ms: t3.elapsed().as_millis() as u64,
            output_summary: format!("{} matched, rate={:.0}%", normatives.len(), match_rate * 100.0),
        });

        // Step 4: Calculate
        let t4 = std::time::Instant::now();
        let items = CalculatorAgent::calculate(&params, &normatives);
        traces.push(AgentTrace {
            agent: "CalculatorAgent".to_string(),
            action: "calculate".to_string(),
            duration_ms: t4.elapsed().as_millis() as u64,
            output_summary: format!("{} items", items.len()),
        });

        // Build estimate
        let mut estimate = EstimateEngine::create_estimate(&format!(
            "Смета: {:?} ({:.0} м2)",
            params.building_type,
            params.area.unwrap_or(0.0)
        ));
        for item in items {
            estimate.add_item(item);
        }

        // Step 5: Validate
        let t5 = std::time::Instant::now();
        let validation = ValidatorAgent::validate(&estimate, &params);
        traces.push(AgentTrace {
            agent: "ValidatorAgent".to_string(),
            action: "validate".to_string(),
            duration_ms: t5.elapsed().as_millis() as u64,
            output_summary: format!("score={:.0}%, valid={}", validation.score, validation.is_valid),
        });

        PipelineResult {
            estimate,
            params,
            validation,
            match_rate,
            agent_traces: traces,
        }
    }
}

// ─── Default Seed Normatives ───

pub fn default_seed_normatives() -> Vec<Normative> {
    vec![
        Normative {
            code: "GESN-01-001".to_string(),
            name: "Подготовительные работы".to_string(),
            unit: "м2".to_string(),
            labor_cost: 120.0,
            material_cost: 30.0,
            machine_cost: 50.0,
            total_cost: 200.0,
            labor_hours: 0.5,
            labor_days: 0.06,
            description: "Подготовка строительной площадки".to_string(),
            typical_use: "Любые строительные работы".to_string(),
            keywords: vec!["подготовка", "площадка", "разметка"].iter().map(|s| s.to_string()).collect(),
        },
        Normative {
            code: "GESN-02-001".to_string(),
            name: "Разработка грунта экскаватором".to_string(),
            unit: "м3".to_string(),
            labor_cost: 80.0,
            material_cost: 0.0,
            machine_cost: 250.0,
            total_cost: 330.0,
            labor_hours: 0.2,
            labor_days: 0.025,
            description: "Разработка грунта в котловане".to_string(),
            typical_use: "Земляные работы".to_string(),
            keywords: vec!["земляные", "котлован", "экскаватор"].iter().map(|s| s.to_string()).collect(),
        },
        Normative {
            code: "GESN-03-001".to_string(),
            name: "Устройство фундамента из монолитного бетона".to_string(),
            unit: "м3".to_string(),
            labor_cost: 1500.0,
            material_cost: 3500.0,
            machine_cost: 800.0,
            total_cost: 5800.0,
            labor_hours: 4.0,
            labor_days: 0.5,
            description: "Заливка монолитного фундамента".to_string(),
            typical_use: "Фундаментные работы".to_string(),
            keywords: vec!["фундамент", "бетон", "монолит"].iter().map(|s| s.to_string()).collect(),
        },
        Normative {
            code: "GESN-04-001".to_string(),
            name: "Бетонирование конструкций".to_string(),
            unit: "м3".to_string(),
            labor_cost: 1200.0,
            material_cost: 3000.0,
            machine_cost: 600.0,
            total_cost: 4800.0,
            labor_hours: 3.0,
            labor_days: 0.375,
            description: "Бетонирование стен, перекрытий".to_string(),
            typical_use: "Бетонные работы".to_string(),
            keywords: vec!["бетон", "заливка", "арматура"].iter().map(|s| s.to_string()).collect(),
        },
        Normative {
            code: "GESN-05-001".to_string(),
            name: "Монтаж металлоконструкций".to_string(),
            unit: "т".to_string(),
            labor_cost: 8000.0,
            material_cost: 15000.0,
            machine_cost: 3000.0,
            total_cost: 26000.0,
            labor_hours: 12.0,
            labor_days: 1.5,
            description: "Монтаж стальных конструкций".to_string(),
            typical_use: "Металлоконструкции".to_string(),
            keywords: vec!["металл", "монтаж", "сварка"].iter().map(|s| s.to_string()).collect(),
        },
        Normative {
            code: "GESN-06-001".to_string(),
            name: "Кладка стен из кирпича".to_string(),
            unit: "м2".to_string(),
            labor_cost: 800.0,
            material_cost: 1200.0,
            machine_cost: 100.0,
            total_cost: 2100.0,
            labor_hours: 2.0,
            labor_days: 0.25,
            description: "Кладка наружных стен в 1 кирпич".to_string(),
            typical_use: "Стены".to_string(),
            keywords: vec!["кирпич", "кладка", "стена"].iter().map(|s| s.to_string()).collect(),
        },
        Normative {
            code: "GESN-06-002".to_string(),
            name: "Кладка стен из газобетонных блоков".to_string(),
            unit: "м2".to_string(),
            labor_cost: 600.0,
            material_cost: 800.0,
            machine_cost: 80.0,
            total_cost: 1480.0,
            labor_hours: 1.5,
            labor_days: 0.19,
            description: "Кладка из газобетона D500".to_string(),
            typical_use: "Стены".to_string(),
            keywords: vec!["газобетон", "блок", "кладка"].iter().map(|s| s.to_string()).collect(),
        },
        Normative {
            code: "GESN-07-001".to_string(),
            name: "Устройство кровли из металлочерепицы".to_string(),
            unit: "м2".to_string(),
            labor_cost: 400.0,
            material_cost: 600.0,
            machine_cost: 50.0,
            total_cost: 1050.0,
            labor_hours: 0.8,
            labor_days: 0.1,
            description: "Монтаж металлочерепицы по обрешётке".to_string(),
            typical_use: "Кровля".to_string(),
            keywords: vec!["кровля", "черепица", "крыша"].iter().map(|s| s.to_string()).collect(),
        },
        Normative {
            code: "GESN-08-001".to_string(),
            name: "Устройство цементно-песчаной стяжки".to_string(),
            unit: "м2".to_string(),
            labor_cost: 350.0,
            material_cost: 250.0,
            machine_cost: 30.0,
            total_cost: 630.0,
            labor_hours: 0.6,
            labor_days: 0.075,
            description: "Стяжка пола толщиной 50мм".to_string(),
            typical_use: "Полы".to_string(),
            keywords: vec!["стяжка", "пол", "цемент"].iter().map(|s| s.to_string()).collect(),
        },
        Normative {
            code: "GESN-08-002".to_string(),
            name: "Устройство наливного пола".to_string(),
            unit: "м2".to_string(),
            labor_cost: 300.0,
            material_cost: 400.0,
            machine_cost: 20.0,
            total_cost: 720.0,
            labor_hours: 0.4,
            labor_days: 0.05,
            description: "Наливной пол толщиной 5мм".to_string(),
            typical_use: "Полы".to_string(),
            keywords: vec!["наливной", "пол", "ровнитель"].iter().map(|s| s.to_string()).collect(),
        },
        Normative {
            code: "GESN-09-001".to_string(),
            name: "Штукатурка стен механизированным способом".to_string(),
            unit: "м2".to_string(),
            labor_cost: 350.0,
            material_cost: 200.0,
            machine_cost: 150.0,
            total_cost: 700.0,
            labor_hours: 0.5,
            labor_days: 0.06,
            description: "Механизированная штукатурка гипсовой смесью 18мм".to_string(),
            typical_use: "Отделка".to_string(),
            keywords: vec!["штукатурка", "механизированная", "гипс"].iter().map(|s| s.to_string()).collect(),
        },
        Normative {
            code: "GESN-09-002".to_string(),
            name: "Шпаклёвка стен".to_string(),
            unit: "м2".to_string(),
            labor_cost: 200.0,
            material_cost: 100.0,
            machine_cost: 0.0,
            total_cost: 300.0,
            labor_hours: 0.4,
            labor_days: 0.05,
            description: "Шпаклёвка в 2 слоя".to_string(),
            typical_use: "Отделка".to_string(),
            keywords: vec!["шпаклёвка", "шпаклевка", "выравнивание"].iter().map(|s| s.to_string()).collect(),
        },
        Normative {
            code: "GESN-09-003".to_string(),
            name: "Покраска стен".to_string(),
            unit: "м2".to_string(),
            labor_cost: 150.0,
            material_cost: 100.0,
            machine_cost: 0.0,
            total_cost: 250.0,
            labor_hours: 0.3,
            labor_days: 0.04,
            description: "Покраска в 2 слоя".to_string(),
            typical_use: "Отделка".to_string(),
            keywords: vec!["покраска", "краска", "малярные"].iter().map(|s| s.to_string()).collect(),
        },
        Normative {
            code: "GESN-09-004".to_string(),
            name: "Укладка керамической плитки".to_string(),
            unit: "м2".to_string(),
            labor_cost: 800.0,
            material_cost: 600.0,
            machine_cost: 50.0,
            total_cost: 1450.0,
            labor_hours: 1.5,
            labor_days: 0.19,
            description: "Укладка настенной плитки".to_string(),
            typical_use: "Отделка".to_string(),
            keywords: vec!["плитка", "керамическая", "облицовка"].iter().map(|s| s.to_string()).collect(),
        },
        Normative {
            code: "GESN-10-001".to_string(),
            name: "Монтаж электропроводки".to_string(),
            unit: "м2".to_string(),
            labor_cost: 400.0,
            material_cost: 300.0,
            machine_cost: 50.0,
            total_cost: 750.0,
            labor_hours: 0.8,
            labor_days: 0.1,
            description: "Скрытая электропроводка".to_string(),
            typical_use: "Инженерные системы".to_string(),
            keywords: vec!["электрика", "проводка", "розетки"].iter().map(|s| s.to_string()).collect(),
        },
        Normative {
            code: "GESN-10-002".to_string(),
            name: "Монтаж водопровода".to_string(),
            unit: "м.п.".to_string(),
            labor_cost: 500.0,
            material_cost: 400.0,
            machine_cost: 30.0,
            total_cost: 930.0,
            labor_hours: 0.6,
            labor_days: 0.075,
            description: "Монтаж водопроводных труб".to_string(),
            typical_use: "Инженерные системы".to_string(),
            keywords: vec!["водопровод", "трубы", "сантехника"].iter().map(|s| s.to_string()).collect(),
        },
        Normative {
            code: "GESN-11-001".to_string(),
            name: "Устройство отмостки".to_string(),
            unit: "м2".to_string(),
            labor_cost: 500.0,
            material_cost: 400.0,
            machine_cost: 100.0,
            total_cost: 1000.0,
            labor_hours: 1.0,
            labor_days: 0.125,
            description: "Отмостка из бетона шириной 1м".to_string(),
            typical_use: "Благоустройство".to_string(),
            keywords: vec!["отмостка", "благоустройство", "водоотвод"].iter().map(|s| s.to_string()).collect(),
        },
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parser_detects_building_type() {
        let params = ParserAgent::parse("Нужна смета на ремонт склада площадью 200 м2");
        assert_eq!(params.building_type, BuildingType::Warehouse);
        assert_eq!(params.area, Some(200.0));
    }

    #[test]
    fn test_parser_detects_work_types() {
        let params = ParserAgent::parse("Штукатурка стен и покраска пола в жилом доме");
        assert!(params.work_types.contains(&WorkCategory::Finishing));
        assert!(params.work_types.contains(&WorkCategory::Flooring));
    }

    #[test]
    fn test_parser_detects_structure() {
        let params = ParserAgent::parse("Кирпичный дом с бетонным фундаментом");
        assert_eq!(params.structure_type, StructureType::Brick);
    }

    #[test]
    fn test_classifier_produces_categories() {
        let params = ConstructionParams {
            building_type: BuildingType::Residential,
            work_types: vec![WorkCategory::Finishing, WorkCategory::Foundation],
            ..Default::default()
        };
        let cats = ClassifierAgent::classify(&params);
        assert!(cats.len() >= 2);
    }

    #[test]
    fn test_normative_matching() {
        let seeds = default_seed_normatives();
        let cats = vec![(WorkCategory::Finishing, vec!["GESN-09-001"])];
        let (matched, rate) = NormativeAgent::match_normatives(&cats, &seeds);
        assert_eq!(matched.len(), 1);
        assert!(rate > 0.0);
    }

    #[test]
    fn test_calculator_produces_items() {
        let params = ConstructionParams {
            area: Some(100.0),
            ..Default::default()
        };
        let norms = vec![
            Normative {
                code: "GESN-09-001".to_string(),
                name: "Штукатурка".to_string(),
                unit: "м2".to_string(),
                labor_cost: 350.0,
                material_cost: 200.0,
                machine_cost: 150.0,
                total_cost: 700.0,
                labor_hours: 0.5,
                labor_days: 0.06,
                description: "".to_string(),
                typical_use: "".to_string(),
                keywords: vec![],
            },
        ];
        let items = CalculatorAgent::calculate(&params, &norms);
        assert!(items.len() >= 3); // work + overhead + profit
    }

    #[test]
    fn test_validator_passes() {
        let mut est = Estimate::new("Test");
        est.add_item(EstimateItem::new("Фундамент", "Test", "м3", 10.0, 1000.0));
        est.add_item(EstimateItem::new("Стены", "Test", "м2", 50.0, 500.0));
        est.add_item(EstimateItem::new("Кровля", "Test", "м2", 50.0, 300.0));

        let params = ConstructionParams {
            area: Some(50.0),
            ..Default::default()
        };
        let report = ValidatorAgent::validate(&est, &params);
        assert!(report.is_valid);
        assert!(report.score >= 50.0);
    }

    #[test]
    fn test_full_pipeline() {
        let seeds = default_seed_normatives();
        let result = EstimatePipeline::run(
            "Нужна смета на штукатурку стен в жилом доме 100 м2",
            &seeds,
        );
        assert!(result.estimate.item_count() > 0);
        assert!(result.match_rate >= 0.0);
        assert!(result.agent_traces.len() == 5);
    }
}
