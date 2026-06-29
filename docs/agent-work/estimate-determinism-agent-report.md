# Проверка deterministic estimate requirement

Дата проверки: 2026-06-29.
Роль: методолог смет.
Кейс: `100 м2 штукатурки в Татарстане`.

Ограничения исполнения:

- тяжелые LLM, FormulaLM и модельные эксперименты не запускались;
- Mac не использовался для модельных экспериментов;
- проверка выполнена по коду, документации и легкому прямому contract check
  расчетного ядра;
- изменены только requested report и estimate-related test.

## 1. Короткий вывод

Текущий демонстрационный estimate kernel уже удовлетворяет узкому P0-требованию
детерминированности для golden case `100 м2 штукатурки в Татарстане`: два
одинаковых вызова `create_estimate_from_prompt(..., client_name="Иван")`
возвращают одинаковый `model_dump(mode="json")`, фиксированный `estimate_id`,
одинаковые totals, timestamps, pricebook version и audit fingerprint.

Это подтверждает воспроизводимость и арифметическую власть расчетного движка,
но не доказывает предметную точность 98-99%. Такая точность остается
benchmark-целью и требует frozen dataset, эталонных ответов, версии прайсбука,
версии правил и опубликованных numerator/denominator по метрикам.

## 2. Что найдено

Проверены estimate-related источники:

- `backend/estimate_engine.py`;
- `backend/tests/test_estimate_document_pdf_engines.py`;
- `docs/agent-work/deterministic-estimates-methodology.md`;
- `docs/agent-work/deterministic-estimates-p0-contract.md`;
- `docs/agent-work/deterministic-estimates-methodologist-report.md`;
- `docs/API-RU.md`;
- `docs/agent-work/product-qa-pack.md`;
- `scripts/formulalm_benchmark.py` только статически, без запуска benchmark.

Ключевые факты по коду:

- `PRICEBOOK_VERSION = "kolibri-ru-2026q2-v1"`;
- deterministic timestamp: `2026-06-29T00:00:00+00:00`;
- регион `Татарстан` нормализуется в `Республика Татарстан`;
- коэффициенты Татарстана: `labor_coeff = 1.00`,
  `material_coeff = 1.00`;
- `input_hash` считается по canonical JSON с `sort_keys=True`;
- `estimate_id = "EST-" + первые 10 символов input_hash`;
- суммы пересчитываются через `Decimal` и `ROUND_HALF_UP`;
- overhead для generated estimate: `7.00%`;
- tax: `0.00%`.

## 3. Golden-case контракт v1

Вход:

```json
{
  "prompt": "100 м2 штукатурки в Татарстане",
  "client_name": "Иван",
  "quality_level": "standard",
  "pricebook_version": "kolibri-ru-2026q2-v1"
}
```

Ожидаемый deterministic envelope текущего движка:

```json
{
  "estimate_id": "EST-A1B5B0B498",
  "title": "Смета на штукатурные работы",
  "region": "Республика Татарстан",
  "currency": "RUB",
  "pricebook_version": "kolibri-ru-2026q2-v1",
  "deterministic": true,
  "created_at": "2026-06-29T00:00:00+00:00",
  "updated_at": "2026-06-29T00:00:00+00:00",
  "overhead_rate": "7.00",
  "tax_rate": "0.00"
}
```

Ожидаемые строки:

| Раздел | Позиция | Кол-во | Работа/м2 | Материал/м2 | Работа итог | Материал итог | Строка |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Подготовка основания | Грунтование стен под штукатурку | 100.00 | 95.00 | 38.00 | 9500.00 | 3800.00 | 13300.00 |
| Подготовка основания | Установка штукатурных маяков | 100.00 | 140.00 | 42.00 | 14000.00 | 4200.00 | 18200.00 |
| Штукатурные работы | Штукатурка стен гипсовой смесью до 20 мм | 100.00 | 620.00 | 285.00 | 62000.00 | 28500.00 | 90500.00 |
| Штукатурные работы | Финишное выравнивание под шпаклевание | 100.00 | 210.00 | 75.00 | 21000.00 | 7500.00 | 28500.00 |

Ожидаемые totals:

```json
{
  "labor": "106500.00",
  "materials": "44000.00",
  "subtotal": "150500.00",
  "overhead": "10535.00",
  "tax": "0.00",
  "grand_total": "161035.00"
}
```

Audit/provenance требования:

- каждая строка имеет `provenance.source = "kolibri_pricebook"`;
- каждая строка имеет `provenance.captured_at =
  "2026-06-29T00:00:00+00:00"`;
- последняя audit-запись имеет `kind = "totals"`;
- последняя audit-запись содержит `input_hash`, `pricebook_version`,
  `calculated_at` и 64-символьный `fingerprint`;
- `line_total` в audit равен `labor_total + material_total`.

## 4. Что добавлено

В `backend/tests/test_estimate_document_pdf_engines.py` усилен существующий
тест `test_prompt_estimate_is_stable_for_same_plastering_scope_in_tatarstan`.
Теперь он фиксирует не только равенство двух JSON и основные totals, но и:

- deterministic timestamps;
- subtotal, overhead и tax;
- точный порядок четырех строк;
- источник цен `kolibri_pricebook`;
- audit line total формулу;
- `pricebook_version`, `calculated_at` и fingerprint в totals audit;
- deterministic `captured_at` у provenance всех строк.

## 5. Проверка после изменений

Полный pytest-прогон файла не выполнен в текущем локальном окружении:

- `/Applications/Xcode.app/.../python3`: нет `pytest`;
- `/Users/kolibri/.venv/bin/python`: нет `pytest`;
- `/opt/homebrew/bin/python3.12`: нет `pytest`, а для полного файла также
  отсутствует `reportlab`, нужный PDF-тестам.

Чтобы не устанавливать зависимости и не превращать проверку в эксперимент на
Mac, выполнен легкий прямой contract check только расчетного ядра через
`/opt/homebrew/bin/python3.12`. Результат:

```text
golden estimate contract passed
```

Этот check подтвердил те же assertions, которые добавлены в golden unit test:
идентичность двух JSON, `EST-A1B5B0B498`, Татарстан, pricebook version,
timestamps, totals, audit rows, provenance и audit fingerprint.

## 6. Методологические разрывы P0

Golden case достаточен как smoke/contract для воспроизводимости текущего
демо-ядра, но продуктовый P0 еще не закрыт полностью:

1. В response нет стабильного `region_code = "RU-TA"`; сейчас хранится label.
2. Нет полного determinism envelope: `rules_version`,
   `region_profile_version`, `coefficients_version`, `canonicalizer_version`,
   `engine_version`, `pricebook_hash`, `rules_hash`.
3. Прайсбук зашит в код, а не вынесен в immutable manifest с hash и статусом
   публикации.
4. Строкам не хватает `item_id`, `type`, `pricebook_item_id`,
   `quantity_source`, `formula`, `price_source` в целевой методологической
   схеме.
5. `PriceProvenance.confidence = 0.98` нельзя трактовать как доказанную
   точность сметы; это не benchmark metric.
6. HTTP endpoints `/api/estimates/*` описаны как целевая граница, но не
   являются текущей реализованной публичной поверхностью.

## 7. Разрешенный claim

Можно говорить:

> Golden case `100 м2 штукатурки в Татарстане` воспроизводим в текущем
> deterministic estimate unit test при версии прайсбука
> `kolibri-ru-2026q2-v1`: `EST-A1B5B0B498`, labor `106500.00`, materials
> `44000.00`, grand total `161035.00`.

Нельзя говорить без benchmark:

- "сметы точны на 98-99%";
- "цены соответствуют рынку Татарстана";
- "LLM гарантирует правильную смету";
- "один golden case доказывает предметную точность".

## 8. Рекомендация

Следующий безопасный шаг: вынести текущий hard-coded прайсбук Татарстана в
`PricebookManifestV1`, добавить `region_code = "RU-TA"` и version/hash fields в
расчетный response, а затем сделать отдельный contract test на immutable
manifest. До этого golden case нужно считать корректным P0-smoke, но не полной
продуктовой гарантией.
