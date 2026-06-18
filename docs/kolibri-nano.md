# Kolibri Nano — Rust Core

## Обзор

`kolibri_nano` — локальное ядро интеллекта, написанное на Rust.
Содержит 11 модулей: память, следы, ассоциации, уверенность, ядро,
движок смет, персональное ядро, хранилище, микровеса, пайплайн и мышление.

## Структура

```
kolibri_nano/
├── Cargo.toml
└── src/
    ├── lib.rs              # Публичные экспорты
    ├── core_engine.rs      # KolibriCore — главный фасад
    ├── memory.rs           # MemoryEngine — управление следами
    ├── traces.rs           # Trace, TraceType — единицы памяти
    ├── associations.rs     # AssociationGraph — граф связей
    ├── confidence.rs       # ConfidenceScore — оценка уверенности
    ├── estimate_engine.rs  # EstimateEngine — движок смет
    ├── personal_core.rs    # PersonalCore — персональный профиль
    ├── storage.rs          # Storage — файловое хранилище
    ├── micro_weights.rs    # MicroWeight — микровеса связей
    ├── pipeline.rs         # EstimatePipeline — пайплайн смет
    └── thinking.rs         # ThinkingEngine — движок мышления
└── tests/
    └── integration_tests.rs
```

## Сборка

```bash
cd kolibri_nano

# Тесты
cargo test

# Библиотека (lib)
cargo build --release

# C dynamic library (для Python FFI)
cargo build --release
# → target/release/libkolibri_nano.dylib (macOS)
# → target/release/libkolibri_nano.so (Linux)

# Python extension (PyO3)
# Раскомментировать pyo3 в Cargo.toml
# maturin develop --release
```

## Зависимости

```toml
[dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
uuid = { version = "1", features = ["v4", "serde"] }
chrono = "0.4"
thiserror = "1"
anyhow = "1"

[dev-dependencies]
tempfile = "3"
```

Опционально (закомментировано в Cargo.toml):
- `pyo3` — Python bindings
- `axum` + `tokio` — standalone HTTP server
- `wasm-bindgen` — WASM target

## Модули

### 1. traces.rs — Следы (Traces)

Единица памяти. Каждое взаимодействие с пользователем создаёт Trace.

```rust
pub enum TraceType {
    Preference,   // Предпочтения пользователя
    Correction,   // Исправления
    Task,         // Задачи
    Estimate,     // Сметы
    Document,     // Документы
    Code,         // Код
    Behavior,     // Поведение
    Error,        // Ошибки
    Success,      // Успехи
}

pub struct Trace {
    pub id: String,           // UUID
    pub user_id: String,
    pub trace_type: TraceType,
    pub content: String,
    pub weight: f32,          // 0.0 - 10.0
    pub confidence: f32,      // 0.0 - 1.0
    pub created_at: u64,      // Unix ms
    pub links: Vec<String>,   // Связанные ID
}
```

**Builder pattern**:
```rust
let trace = Trace::new("user1", TraceType::Preference, "Короткие ответы")
    .with_weight(3.0)
    .with_confidence(0.8)
    .with_link("task-123");
```

**Методы**: `boost(amount)`, `decay(factor)` — изменение веса.

### 2. memory.rs — Движок памяти

In-memory хранилище следов с поиском и анализом.

```rust
pub struct MemoryEngine {
    pub traces: Vec<Trace>,
}
```

**Методы**:
| Метод | Описание |
|-------|----------|
| `add_trace(trace) -> String` | Добавить след, вернуть ID |
| `find_by_type(type) -> Vec<&Trace>` | Поиск по типу |
| `find_by_user(user_id) -> Vec<&Trace>` | Поиск по пользователю |
| `find_related(trace_id) -> Vec<&Trace>` | Связанные следы |
| `top_weighted(user_id, limit) -> Vec<&Trace>` | Топ по весу |
| `update_weight(trace_id, delta) -> bool` | Изменить вес |
| `decay_all(factor)` | Затухание всех следов |
| `count() -> usize` | Количество |
| `avg_weight(user_id) -> f32` | Средний вес |
| `extract_patterns(user_id) -> Vec<Pattern>` | Извлечение паттернов |
| `prepare_context_for_llm(user_id, max) -> String` | Контекст для LLM |

**Паттерны** (Pattern):
```rust
pub struct Pattern {
    pub id: String,
    pub name: String,
    pub trigger: String,
    pub action_hint: String,
    pub weight: f32,
    pub success_count: u32,
}
```

Извлекаются при частоте >= 2 одного типа.

### 3. associations.rs — Граф ассоциаций

Связи между сущностями (estimate → client, task → document).

```rust
pub struct Association {
    pub id: String,
    pub from: String,
    pub to: String,
    pub relation: String,
    pub weight: f32,
    pub confidence: f32,
    pub created_at: u64,
}

pub struct AssociationGraph {
    pub links: Vec<Association>,
}
```

**Методы графа**:
| Метод | Описание |
|-------|----------|
| `add(assoc)` | Добавить связь |
| `find_by_entity(entity) -> Vec` | Поиск по сущности |
| `find_by_relation(relation) -> Vec` | Поиск по типу связи |
| `strongest(entity) -> Option` | Самая сильная связь |
| `len() -> usize` | Количество |

### 4. confidence.rs — Оценка уверенности

Вычисляет score на основе 4 факторов:

```rust
pub fn calculate_confidence(
    trace_count: usize,      // Количество следов (max impact: 0.2)
    avg_weight: f32,         // Средний вес (max impact: 0.15)
    success_rate: f32,       // Успех (max impact: 0.2)
    pattern_matches: usize,  // Паттерны (max impact: 0.15)
) -> ConfidenceScore
```

Базовый score: 0.5 + факторы. Clamp: 0.0 - 1.0.

### 5. personal_core.rs — Персональное ядро

Профиль пользователя с 7 параметрами и 10-значным digit core.

```rust
pub struct PersonalCore {
    pub user_id: String,
    pub core_digits: [u8; 10],    // 0-9, уникальный отпечаток
    pub stability: f32,           // Стабильность
    pub curiosity: f32,           // Любопытство
    pub precision: f32,           // Точность
    pub creativity: f32,          // Креативность
    pub practical_focus: f32,     // Практичность
    pub memory_weight: f32,       // Использование памяти
    pub trust_level: f32,         // Уровень доверия
    pub last_updated: u64,
}
```

**Обновление через BehaviorSignal**:
```rust
pub struct BehaviorSignal {
    pub was_precise: bool,
    pub was_creative: bool,
    pub was_practical: bool,
    pub used_memory: bool,
    pub was_success: bool,
    pub explored_new: bool,
}
```

Learning rate: 0.05. Каждый сигнал обновляет соответствующий параметр.

### 6. estimate_engine.rs — Движок смет

Создание и управление строительными сметами.

```rust
pub struct Estimate {
    pub estimate_id: String,
    pub title: String,
    pub client: ClientInfo,        // name, phone, address
    pub object: ObjectInfo,        // type, area, location
    pub items: Vec<EstimateItem>,
    pub totals: EstimateTotals,    // works, materials, delivery, discount, grand_total
    pub assumptions: Vec<String>,
    pub warnings: Vec<String>,
    pub version: u32,
}

pub struct EstimateItem {
    pub id: String,
    pub section: String,           // "Работы" | "Материалы"
    pub name: String,
    pub unit: String,              // "м2", "кг", "шт"
    pub quantity: f64,
    pub unit_price: f64,
    pub total: f64,                // auto-calculated
}
```

**API**:
```rust
let mut est = Estimate::new("Ремонт комнаты");
EstimateEngine::add_work_item(&mut est, "Штукатурка", "м2", 50.0, 350.0);
EstimateEngine::add_material_item(&mut est, "Шпаклёвка", "кг", 20.0, 80.0);

est.recalculate();
est.remove_item(&item_id);

let json = EstimateEngine::to_json(&est);
let restored = EstimateEngine::from_json(&json);

let cost = Estimate::quick_calc_works(18.0, 3500.0); // 63000.0
```

### 7. core_engine.rs — KolibriCore (фасад)

Главный entry point, объединяющий все модули.

```rust
pub struct KolibriCore {
    pub user_id: String,
    pub memory: MemoryEngine,
    pub associations: AssociationGraph,
    pub personal_core: PersonalCore,
}
```

**Методы**:
| Метод | Описание |
|-------|----------|
| `new(user_id)` | Создать ядро |
| `add_trace(type, content) -> String` | Добавить след |
| `learn_from_result(task, success, used_memory)` | Обучение из результата |
| `get_confidence() -> ConfidenceScore` | Уверенность |
| `prepare_context_for_llm(max) -> String` | Контекст для LLM |
| `create_estimate(title) -> Estimate` | Создать смету |
| `trace_count() -> usize` | Количество следов |

### 8. storage.rs — Файловое хранилище

Персистентное хранение в JSON-файлах.

```rust
pub struct Storage {
    config: StorageConfig,  // data_dir: PathBuf
}
```

**Директории**: `traces/`, `memory/`, `estimates/`

**Методы**:
| Метод | Описание |
|-------|----------|
| `init()` | Создать директории |
| `save_json(subdir, name, data)` | Сохранить |
| `load_json(subdir, name) -> T` | Загрузить |
| `exists(subdir, name) -> bool` | Проверить |
| `list_files(subdir) -> Vec<String>` | Список файлов |

### 9. micro_weights.rs — Микровеса

Микровеса связей между сущностями с интуитивными коэффициентами.

```rust
pub struct MicroWeight {
    pub from: String,
    pub to: String,
    pub weight: f32,
    pub confidence: f32,
    pub intuition: f32,       // Интуитивный коэффициент
}

pub struct MicroWeightStore {
    weights: Vec<MicroWeight>,
}
```

**Методы**:
| Метод | Описание |
|-------|----------|
| `add(weight)` | Добавить микровес |
| `find(from, to) -> Option` | Найти связь |
| `update(from, to, delta)` | Обновить вес |
| `strongest_for(entity) -> Option` | Самая сильная связь |
| `len() -> usize` | Количество |

### 10. pipeline.rs — Пайплайн смет

Полный пайплайн генерации строительных смет с агентной архитектурой.

```rust
pub struct EstimatePipeline {
    agents: Vec<Box<dyn Agent>>,
}

// Агенты пайплайна:
pub struct ParserAgent;       // Парсинг входных данных
pub struct ClassifierAgent;   // Классификация типа работ
pub struct NormativeAgent;    // Подбор нормативов (ГОСТ/СНиП)
pub struct CalculatorAgent;   // Расчёт стоимостей
pub struct ValidatorAgent;    // Валидация результата
```

**Типы зданий и конструкций**:
```rust
pub enum BuildingType {
    Residential, Commercial, Industrial, ...
}

pub enum StructureType {
    Wall, Floor, Roof, Foundation, ...
}
```

### 11. thinking.rs — Движок мышления

Движок обработки стимулов и генерации мыслей.

```rust
pub struct ThinkingEngine {
    context: Context,
}

pub enum Stimulus {
    Text(String),
    Voice(Vec<f32>),
    File(String),
    Image(String),
    Action(String),
    Sensor(f32),
}

pub struct Context {
    pub user_id: String,
    pub session_id: String,
    pub history: Vec<Thought>,
}

pub struct Thought {
    pub content: String,
    pub confidence: f32,
    pub source: String,
}
```

## Python интеграция

### Вариант 1: PyO3 (рекомендуется)

Раскомментировать в Cargo.toml:
```toml
pyo3 = { version = "0.22", features = ["extension-module"] }
```

Собрать с maturin:
```bash
pip install maturin
maturin develop --release
```

Использование:
```python
import kolibri_nano

core = kolibri_nano.KolibriCore("user1")
core.add_trace("preference", "Короткие ответы")
context = core.prepare_context_for_llm(10)
confidence = core.get_confidence()
```

### Вариант 2: CLI + JSON

Собрать CLI binary и вызывать через subprocess:
```bash
cargo build --release
./target/release/kolibri_nano --user user1 --action add_trace --type preference --content "..."
```

### Вариант 3: FFI

Использовать `cdylib` target для прямых вызовов из C/Python ctypes.

## Тесты

56 тестов (54 unit + 2 integration) покрывают все модули:

```bash
cargo test
# test traces::tests::test_trace_creation ... ok
# test memory::tests::test_add_and_find ... ok
# test associations::tests::test_graph_operations ... ok
# test confidence::tests::test_confidence_high ... ok
# test estimate_engine::tests::test_add_items_and_recalculate ... ok
# test personal_core::tests::test_update_from_behavior ... ok
# test core_engine::tests::test_learn_from_result ... ok
# test storage::tests::test_save_load ... ok
# test micro_weights::tests::test_add_and_find ... ok
# test pipeline::tests::test_parser_agent ... ok
# test thinking::tests::test_stimulus_processing ... ok
# ... и другие
```

Интеграционные тесты: `tests/integration_tests.rs`
- `test_full_workflow` — полный цикл: следы → контекст → смета → JSON
- `test_personal_core_evolution` — эволюция core digits
