# P0-контракт детерминированных смет Kolibri

Роль: Методолог детерминированных смет.

Назначение документа: зафиксировать минимальный продуктовый и технический
контракт, при котором одинаковый запрос, например `100 м2 штукатурки в
Татарстане`, дает одинаковую смету при одинаковых версиях входных данных,
прайсбука, регионального профиля, коэффициентов и расчетных правил.

Этот контракт дополняет `docs/agent-work/deterministic-estimates-methodology.md`
и опирается на текущее поведение `backend/estimate_engine.py` и тестов в
`backend/tests/test_estimate_document_pdf_engines.py`.

## 1. P0-граница

P0 не обещает "угадать рынок" и не обещает 98-99% точности без эталонного
набора. P0 обязан доказать три более узких свойства:

1. **Воспроизводимость:** одинаковый canonical request + одинаковые версии
   данных дают байтово одинаковый canonical estimate JSON.
2. **Арифметическая власть движка:** все суммы считаются кодом, а не LLM,
   PDF или пользовательским интерфейсом.
3. **Проверяемое происхождение:** в ответе и audit trail видны input hash,
   pricebook version, региональный профиль, коэффициенты, правила, формулы и
   источники цен.

Точность 98-99% допускается только как измеренная метрика на замороженном
benchmark dataset с опубликованными numerator/denominator, датой прогона и
версиями артефактов. Если benchmark не запущен, статус формулируется как
`not_proven_yet`, а не как обещание.

## 2. Что уже есть в текущем движке

`backend/estimate_engine.py` уже содержит P0-ядро для демонстрационного
детерминированного расчета:

- фиксированная версия прайсбука: `kolibri-ru-2026q2-v1`;
- фиксированный deterministic timestamp:
  `2026-06-29T00:00:00+00:00`;
- региональные профили с коэффициентами работ и материалов;
- canonical text normalization;
- `input_hash` через stable JSON fingerprint;
- deterministic estimate id: `EST-` + первые 10 символов `input_hash`;
- пересчет строк, subtotal, overhead, tax и grand total через `Decimal`;
- audit fingerprint для итогов;
- golden test для `100 м2 штукатурки в Татарстане`.

Текущий golden result:

- `estimate_id`: `EST-A1B5B0B498`;
- `region`: `Республика Татарстан`;
- `pricebook_version`: `kolibri-ru-2026q2-v1`;
- `labor`: `106500.00`;
- `materials`: `44000.00`;
- `grand_total`: `161035.00`;
- `deterministic`: `true`.

Текущие P0-разрывы, которые надо закрыть контрактом/API:

- регион хранится как label, но нужен стабильный `region_code`, например
  `RU-TA`;
- нет отдельного `rules_version`, `region_profile_version`,
  `coefficients_version`, `engine_version`, `canonicalizer_version`;
- прайсбук фактически зашит в код, но для продукта нужен immutable manifest с
  hash;
- строки не имеют стабильных `item_id`, `type`, `pricebook_item_id`,
  `price_source` в формате методологии;
- нет API для canonicalize, calculate, validate, manifests, revisions и
  benchmark runs.

## 3. Инвариант одинакового результата

Одинаковый результат гарантируется только если совпадают все поля
determinism envelope:

```json
{
  "contract_version": "deterministic-estimates-p0-v1",
  "canonical_request_hash": "sha256:...",
  "pricebook_version": "kolibri-ru-2026q2-v1",
  "pricebook_hash": "sha256:...",
  "region_code": "RU-TA",
  "region_profile_version": "ru-ta-2026q2-v1",
  "region_profile_hash": "sha256:...",
  "coefficients_version": "ru-ta-coefficients-2026q2-v1",
  "rules_version": "kolibri-estimate-rules-2026q2-v1",
  "rules_hash": "sha256:...",
  "engine_version": "git:<commit-sha>",
  "canonicalizer_version": "kolibri-canonicalizer-v1",
  "currency": "RUB",
  "rounding": "Decimal ROUND_HALF_UP / 2 places"
}
```

Если любое поле envelope отличается, система может вернуть другой результат.
Это не regression, пока новая ревизия явно показывает отличившуюся версию.

## 4. Обязательные входные данные

P0 API может принимать свободный текст, но расчетное ядро должно получать
канонический запрос.

Минимальный `EstimateCanonicalRequestV1`:

```json
{
  "raw_input": "100 м2 штукатурки в Татарстане",
  "client": {
    "name": "Иван"
  },
  "object": {
    "address": null,
    "area": {
      "value": "100.00",
      "unit": "m2",
      "source": "parsed_from_prompt"
    }
  },
  "scope": [
    {
      "work_type": "plastering",
      "quantity": "100.00",
      "unit": "m2",
      "quality_level": "standard"
    }
  ],
  "region": {
    "code": "RU-TA",
    "label": "Республика Татарстан",
    "city_zone": null
  },
  "materials_policy": "contractor_supplied",
  "calculation_date": "2026-06-29",
  "currency": "RUB",
  "pricebook_version": "kolibri-ru-2026q2-v1",
  "rules_version": "kolibri-estimate-rules-2026q2-v1",
  "overrides": []
}
```

Обязательные поля для автосчета:

- `scope[].work_type`;
- `scope[].quantity`;
- `scope[].unit`;
- `region.code`;
- `currency`;
- `pricebook_version`;
- `rules_version`;
- `quality_level` или явно принятое default-значение;
- `materials_policy`;
- `calculation_date`.

Если нет количества, региона, единицы, work type или версии прайсбука, система
не должна молча достраивать финальную смету. Правильный P0-ответ:
`status = needs_input`, список `questions`, черновик без публикации.

## 5. Канонизация

Canonical request строится до расчета и должен быть сохранен вместе со сметой.

Правила P0:

- текст: trim, lower, `ё -> е`, повторные пробелы в один пробел;
- числа: `Decimal`, строковое представление с двумя знаками;
- единицы: внешний API использует `m2`, `m3`, `lm`, `pcs`, `set`, `hour`,
  `day`, `trip`; текущие `м2` в engine допустимы только как внутренний
  adapter до миграции;
- регион: `Татарстан`, `Республика Татарстан`, адрес в Татарстане -> `RU-TA`;
- списки scope и overrides сортируются стабильным ключом, если порядок не
  несет смысла;
- hash считается по canonical JSON с `sort_keys=true`.

В P0 в hash должны входить как минимум:

- normalized prompt или structured scope;
- client identity field, если он влияет на output;
- region code;
- area/quantity;
- unit;
- quality level;
- materials policy;
- pricebook version;
- rules version;
- region profile version;
- coefficients version.

## 6. Прайсбук и датасет цен

Прайсбук не должен быть "текущей таблицей"; это immutable dataset.

Минимальный `PricebookManifestV1`:

```json
{
  "pricebook_version": "kolibri-ru-2026q2-v1",
  "pricebook_hash": "sha256:...",
  "status": "published",
  "valid_from": "2026-04-01",
  "valid_to": "2026-06-30",
  "currency": "RUB",
  "regions": ["RU-TA"],
  "source_policy": "internal_demo_pricebook|verified_supplier|user_uploaded",
  "created_at": "2026-06-29T00:00:00+00:00"
}
```

Минимальная строка прайсбука:

```json
{
  "pricebook_item_id": "pb-ru-ta-plaster-gypsum-20mm-v1",
  "type": "work_material_bundle",
  "work_type": "plastering",
  "name": "Штукатурка стен гипсовой смесью до 20 мм",
  "unit": "m2",
  "labor_unit_price": "620.00",
  "material_unit_price": "285.00",
  "min_price": "0.00",
  "max_price": "0.00",
  "quality_level": "standard",
  "region_code": "RU-TA",
  "valid_from": "2026-04-01",
  "status": "published"
}
```

Для текущего P0 можно сгенерировать manifest из hard-coded цен
`backend/estimate_engine.py`, но API должен возвращать hash этого manifest.
Изменение любой цены создает новую `pricebook_version` или новый manifest hash.
Старая смета при пересчете на старой версии не должна менять totals.

## 7. Регион, коэффициенты и правила

Региональный профиль для Татарстана должен быть отдельным версионированным
артефактом:

```json
{
  "region_code": "RU-TA",
  "label": "Республика Татарстан",
  "region_profile_version": "ru-ta-2026q2-v1",
  "coefficients_version": "ru-ta-coefficients-2026q2-v1",
  "currency": "RUB",
  "coefficients": {
    "labor_coeff": "1.00",
    "material_coeff": "1.00",
    "delivery_coeff": "1.00"
  }
}
```

Правила применения:

- коэффициент применяется только если есть опубликованное правило и условие во
  входных данных;
- default-коэффициент `1.00` также фиксируется в audit trail;
- городские зоны, этажность, лифт, удаленность, сезонность и вывоз мусора не
  подмешиваются скрыто: нет входного условия -> нет коэффициента или есть
  вопрос пользователю;
- overhead и tax являются правилами расчета, а не частью unit price.

Для текущего golden case:

- `region_code`: должен быть `RU-TA`;
- `labor_coeff`: `1.00`;
- `material_coeff`: `1.00`;
- `overhead_rate`: `7.00`;
- `tax_rate`: `0.00`.

## 8. Расчетный контракт ответа

Минимальный `EstimateCalculationResponseV1`:

```json
{
  "status": "calculated",
  "estimate_id": "EST-A1B5B0B498",
  "input_hash": "sha256:...",
  "deterministic": true,
  "versions": {
    "pricebook_version": "kolibri-ru-2026q2-v1",
    "region_profile_version": "ru-ta-2026q2-v1",
    "coefficients_version": "ru-ta-coefficients-2026q2-v1",
    "rules_version": "kolibri-estimate-rules-2026q2-v1",
    "engine_version": "git:<commit-sha>"
  },
  "region": {
    "code": "RU-TA",
    "label": "Республика Татарстан"
  },
  "sections": [],
  "totals": {
    "labor": "106500.00",
    "materials": "44000.00",
    "subtotal": "150500.00",
    "overhead": "10535.00",
    "tax": "0.00",
    "grand_total": "161035.00"
  },
  "questions": [],
  "assumptions": [],
  "qa_status": "draft",
  "audit": []
}
```

Audit для каждой строки должен отвечать на вопросы:

- откуда взялась работа;
- откуда взялось количество;
- какая позиция прайсбука выбрана;
- какие коэффициенты применены;
- какая формула дала итог;
- кто и когда сделал override, если он есть.

## 9. Нужные API

P0 API лучше держать тонкими: HTTP слой не считает сам, а вызывает одно
расчетное ядро.

### `POST /api/estimates/canonicalize`

Вход: raw prompt или structured draft.

Выход:

- canonical request;
- `canonical_request_hash`;
- `questions`;
- `warnings`;
- `status`: `ready|needs_input`.

### `POST /api/estimates/calculate`

Вход:

- canonical request;
- determinism envelope или ссылки на версии.

Выход:

- calculated estimate JSON;
- totals;
- audit;
- validation result.

Идемпотентность:

- одинаковый request body должен возвращать тот же estimate JSON;
- допустим `Idempotency-Key`, но детерминизм не должен зависеть только от него.

### `POST /api/estimates/recalculate`

Вход: existing estimate revision + overrides.

Выход: новая calculated revision. Старые ревизии immutable.

### `POST /api/estimates/validate`

Проверяет:

- обязательные поля;
- canonical units;
- totals;
- price source;
- pricebook references;
- outliers;
- duplicate semantic rows;
- QA gate.

### `GET /api/pricebooks/{pricebook_version}/manifest`

Возвращает manifest, hash, статус публикации, valid range и список регионов.

### `GET /api/regions/{region_code}/profile`

Возвращает региональный профиль, coefficients manifest и hash.

### `GET /api/estimates/{estimate_id}/revisions`

Возвращает immutable revisions с version envelope и audit trail.

### `POST /api/estimates/{estimate_id}/publish`

Разрешает публикацию только если:

- validation passed;
- `qa_status` допустим для типа документа;
- нет critical questions;
- все версии зафиксированы.

### `POST /api/estimate-benchmarks/runs`

Запускает benchmark по frozen dataset. Возвращает фактические метрики, а не
маркетинговый claim.

## 10. Как тестировать 98-99% честно

Разделить тесты на три группы.

**A. Determinism tests**

Это unit/contract tests. Они должны давать 100% или падать.

- одинаковый canonical request -> одинаковый JSON;
- одинаковый prompt golden case -> одинаковые `estimate_id`, `input_hash`,
  totals, timestamps и audit fingerprint;
- изменение `pricebook_version` или `rules_version` меняет envelope и не
  перезаписывает старую ревизию;
- `normalize_estimate_payload` пересчитывает totals и не принимает чужие итоги.

**B. Arithmetic tests**

Это точность расчетов, не предметная полнота.

- `line_total = quantity * labor_unit_price + quantity * material_unit_price`;
- `subtotal = labor + materials`;
- `overhead = subtotal * overhead_rate / 100`;
- `tax = (subtotal + overhead) * tax_rate / 100`;
- `grand_total = subtotal + overhead + tax`;
- округление через Decimal ROUND_HALF_UP / 2 places.

Порог P0: `arithmetic_accuracy = 100%` на deterministic unit tests и
`>= 99.9%` на benchmark строках. Для критических арифметических ошибок
`qa_escape_rate = 0`.

**C. Subject accuracy benchmark**

Это единственное место, где можно говорить про 98-99%.

Benchmark должен быть frozen:

- `dataset_version`;
- список кейсов;
- expected canonical scope;
- expected pricebook matches;
- expected formulas;
- expected QA outcome;
- region/profile/pricebook/rules versions;
- дата и commit прогона.

Метрики публикуются только в форме:

- `scope_recall = matched_expected_scope_items / expected_scope_items`;
- `scope_precision = confirmed_output_scope_items / output_scope_items`;
- `pricebook_match_accuracy = correct_matches / eligible_matches`;
- `reproducibility_rate = identical_replays / total_replays`;
- `arithmetic_accuracy = correct_arithmetic_cells / arithmetic_cells`;
- `qa_escape_rate = critical_errors_not_blocked / critical_errors`.

Формулировка результата:

- хорошо: `на dataset tatarstan-estimates-2026q2-v1: scope_recall 98.4%
  (123/125), pricebook_match_accuracy 98.8% (84/85)`;
- нельзя: `система всегда делает сметы с точностью 99%`;
- нельзя: `98%` на одном golden case;
- нельзя смешивать missing-input cases с full-input cases без отдельной метки.

## 11. Маленький безопасный тестовый контракт

Код сейчас менять не нужно. Если добавлять тест отдельным PR, самый безопасный
контракт:

Файл:

- `backend/tests/test_estimate_p0_contract.py`

Точные проверки:

1. `create_estimate_from_prompt("100 м2 штукатурки в Татарстане",
   client_name="Иван")` дважды возвращает одинаковый
   `model_dump(mode="json")`.
2. `estimate_id == "EST-A1B5B0B498"`.
3. `region == "Республика Татарстан"`.
4. `pricebook_version == "kolibri-ru-2026q2-v1"`.
5. `created_at == updated_at == "2026-06-29T00:00:00+00:00"`.
6. `totals.labor == Decimal("106500.00")`.
7. `totals.materials == Decimal("44000.00")`.
8. `totals.subtotal == Decimal("150500.00")`.
9. `totals.overhead == Decimal("10535.00")`.
10. `totals.tax == Decimal("0.00")`.
11. `totals.grand_total == Decimal("161035.00")`.
12. Последний audit item содержит `pricebook_version` и `input_hash`.
13. Все строки имеют `provenance.source == "kolibri_pricebook"`.
14. Все `provenance.captured_at` равны deterministic timestamp.
15. Все строковые `line_total` в audit равны сумме labor/material totals.

Можно не создавать fixture JSON на первом шаге: существующий test уже близок к
этому контракту. Fixture имеет смысл, когда появится stable external schema с
`region_code`, `rules_version`, `pricebook_hash` и `pricebook_item_id`.

## 12. Definition of Done для P0

P0 считается выполненным, когда:

- есть canonical request schema;
- есть immutable pricebook manifest с hash;
- есть region profile manifest для `RU-TA`;
- есть rules/coefficients versions;
- расчетный API возвращает determinism envelope;
- golden case `100 м2 штукатурки в Татарстане` стабилен;
- validation API блокирует missing input и missing price source;
- publish API не выпускает коммерческий документ без QA gate;
- benchmark API умеет честно вернуть `not_proven_yet`, если dataset или прогон
  отсутствуют;
- документация не заявляет 98-99% без dataset-backed metrics.

