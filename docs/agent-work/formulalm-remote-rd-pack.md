# FormulaLM Remote R&D Pack

Дата: 2026-06-29  
Роль: `formulalm_researcher`  
Статус: remote-only исследовательский пакет, без локального запуска моделей

## 1. Назначение

Этот документ задает воспроизводимый пакет FormulaLM R&D для Kolibri AI
Platform: гипотезы, метрики, remote benchmark protocol, тестовый dataset,
blocker policy и шаблон GitHub-отчета.

FormulaLM здесь означает внутренний подход Kolibri: формульный
детерминированный слой поверх LLM. В первом эксперименте веса модели не
изменяются. Baseline и FormulaLM используют один и тот же remote runtime и одну
и ту же базовую модель; отличается только режим:

- baseline: модель сама возвращает JSON сметы и итог;
- FormulaLM: модель извлекает переменные, а deterministic kernel пересчитывает
  строки, налоги, накладные и итог.

Главное правило: FormulaLM/Qwen/QW 2.5/model benchmark запускается только на
удаленном Linux factory node через Control Plane. Mac является поверхностью
управления, чтения и редактирования документов.

Remote guard является исполнимым контрактом, а не только запретом. Каждый
исполнитель обязан пройти состояние `preflight_recorded`, затем выбрать ровно
одну ветку: `benchmark_started` или `blocked_with_artifact`.

## 2. Remote-only инварианты

- Все задачи входят через `POST /v1/tasks` или
  `ops/kolibri-dispatch submit --file <envelope.json>`.
- Исполнитель получает lease через `/v1/tasks/lease` и работает в node-local
  worktree/artifacts.
- Control Plane хранит состояние, leases и result references; он не должен
  читать node-local файлы как общий writable root disk.
- Эксперимент обязан сначала записать preflight: OS, hostname, node id, runtime,
  model id, disk/RAM и artifact directory.
- Если OS равна Darwin, задача завершается blocker artifact и не запускает
  benchmark.
- Если runtime/model/cases недоступны, результаты не придумываются; задача
  возвращает blocker artifact.
- Raw logs не публикуются без проверки на секреты, приватные пути и данные
  клиентов.

## 2.1 Исполнимый remote guard

Агент FormulaLM обязан выполнить следующий автомат:

| State | Action | Output | Next |
| --- | --- | --- | --- |
| `lease_received` | Проверить task id, node id, artifact dir | stdout + heartbeat | `preflight_recorded` |
| `preflight_recorded` | Записать `preflight.json` до model call | `preflight.json` | `guard_checked` |
| `guard_checked` | Проверить OS/runtime/model/dataset/pricebook | decision log | `benchmark_started` или `blocked_with_artifact` |
| `blocked_with_artifact` | Записать `blockers.json` и безопасный next action | `blockers.json` | `report_returned` |
| `benchmark_started` | Запустить baseline и FormulaLM на одинаковых settings | raw local artifact logs | `artifacts_written` |
| `artifacts_written` | Записать JSON/Markdown summary | `formulalm-benchmark.json`, `formulalm-benchmark.md` | `report_returned` |
| `report_returned` | Вернуть result reference в Control Plane | result JSON | done |

Запрещено оставлять задачу только в состоянии analysis. Если benchmark не
может стартовать, результатом является blocker artifact. Если может стартовать,
результатом является benchmark artifact.

## 3. Research hypotheses

### H1. JSON validity

FormulaLM повышает долю валидного JSON по сравнению с baseline на одинаковых
запросах и одинаковой модели.

Decision rule:

- доказано: `formulalm.valid_json_rate - baseline.valid_json_rate >= 0.05`;
- не доказано: разница меньше `0.05`;
- blocked: менее 30 успешных записей на режим или runtime errors выше 10%.

### H2. Exact total accuracy

FormulaLM повышает долю точных итогов сметы, потому что итог считается
детерминированным kernel, а не свободной генерацией модели.

Decision rule:

- доказано: `formulalm.exact_total_rate >= 0.98` и
  `formulalm.exact_total_rate - baseline.exact_total_rate >= 0.10`;
- не доказано: FormulaLM ниже 0.98 или uplift ниже 0.10;
- blocked: pricebook/kernel version не совпадает с ожидаемым
  `kolibri-ru-2026q2-v1`.

### H3. Reproducibility

FormulaLM снижает разброс результатов на повторных одинаковых prompts.

Decision rule:

- доказано: `formulalm.unique_output_hashes_per_case <= 2` и ниже baseline
  минимум на 50%;
- не доказано: разброс сопоставим с baseline;
- blocked: repeat count меньше 5 на case.

### H4. Formula consistency

FormulaLM лучше соблюдает инварианты расчета:

- `line_total = quantity * labor_unit_price + quantity * material_unit_price`;
- `subtotal = labor + materials`;
- `overhead = subtotal * overhead_rate`;
- `tax = (subtotal + overhead) * tax_rate`;
- `grand_total = subtotal + overhead + tax`.

Decision rule:

- доказано: `formulalm.formula_consistency_rate >= 0.99`;
- не доказано: ниже 0.99;
- blocked: audit trail отсутствует или не содержит формулы.

### H5. Operator usefulness

FormulaLM снижает количество ручных исправлений для сметного workflow.

Decision rule:

- доказано: `manual_fix_count` ниже baseline минимум на 30% на QA review;
- не доказано: меньше 30% improvement;
- blocked: нет независимого review artifact.

## 4. Metrics

Минимальный JSON summary должен содержать:

| Metric | Type | Formula | Target |
| --- | --- | --- | --- |
| `valid_json_rate` | float 0..1 | valid JSON outputs / total attempts | FormulaLM +5 pp vs baseline |
| `exact_total_rate` | float 0..1 | outputs with exact expected grand total / total attempts | FormulaLM >= 0.98 |
| `formula_consistency_rate` | float 0..1 | records passing formula audit / records | FormulaLM >= 0.99 |
| `unique_output_hashes` | int | unique hashes by mode | FormulaLM lower than baseline |
| `unique_output_hashes_per_case` | object | unique hashes grouped by case id | FormulaLM <= 2 per case |
| `parse_error_rate` | float 0..1 | parse errors / attempts | FormulaLM lower than baseline |
| `runtime_error_rate` | float 0..1 | runtime errors / attempts | <= 0.10 |
| `latency_p50_ms` | int | median generation latency | report only |
| `latency_p95_ms` | int | p95 generation latency | report only |
| `tokens_or_chars_per_second` | float | throughput from runtime if available | report only |
| `manual_fix_count` | int | QA-marked required corrections | FormulaLM -30% vs baseline |
| `blocked_reason_count` | object | blocker category counts | report all |

Required dimensions:

- `mode`: `baseline` or `formulalm`;
- `case_id`;
- `iteration`;
- `model_id`;
- `runtime`;
- `runtime_version`;
- `pricebook_version`;
- `node_id`;
- `task_id`;
- `started_at`;
- `finished_at`.

## 5. Remote benchmark protocol

### 5.1 Control Plane pre-check

Перед отправкой benchmark task оператор проверяет только Control Plane:

- `/health` отвечает `status=ok`;
- `/v1/nodes` содержит целевой Linux node с heartbeat freshness в пределах
  политики lease;
- node capabilities включают runtime для `generic_implementation` или
  специализированный runner для FormulaLM;
- нет активного P0 incident по Control Plane/Agent Host;
- нет дублирующей running-задачи для того же `task_id`.

### 5.2 Task envelope policy

Envelope должен явно содержать:

- `task_id`;
- `kind`;
- `required_capability`;
- `target_node`;
- `role_slot: formulalm_researcher`;
- `goal` с запретом запуска на Mac;
- `acceptance`;
- `source.rule: remote-only`.

Envelope не должен содержать секреты, raw tokens, приватные ключи, SSH-команды
или локальные пути Mac.

### 5.3 Remote executor steps

Эти шаги выполняются только lease-владельцем на remote node:

1. Записать preflight artifact:
   - `uname`;
   - `platform.system`;
   - hostname;
   - node id;
   - task id;
   - available RAM/disk;
   - runtime type and version;
   - model id;
   - repo commit;
   - artifact directory.
2. Если OS равна Darwin, завершить задачу blocker artifact.
3. Проверить доступность model runtime: Ollama, llama.cpp, vLLM или другой
   документированный remote endpoint.
4. Проверить наличие Qwen/QW 2.5-compatible model.
5. Проверить, что dataset доступен как JSONL artifact или встроенный fallback.
6. Выполнить baseline и FormulaLM modes на одном dataset, одной модели и
   одинаковых generation settings.
7. Записать `formulalm-benchmark.json`, `formulalm-benchmark.md`,
   `preflight.json`, `blockers.json` и, при наличии QA, `manual-review.md`.
8. Вернуть result reference в Control Plane task.

### 5.4 Benchmark duration

Рекомендуемые режимы:

- smoke: 5 cases x 2 repeats, только чтобы проверить runtime;
- pilot: 20 cases x 5 repeats;
- six-hour: 6 часов или максимальная безопасная длительность lease policy;
- nightly: только после успешного six-hour и отдельного owner approval.

Текущий первый remote benchmark: `KOL-FORMULALM-REMOTE-BENCH-6H-20260629`,
целевой node `server-kfrm` после подтверждения heartbeat/runtime.

### 5.5 Acceptance criteria

Задача считается completed только если:

- нет запуска на macOS;
- preflight artifact записан до benchmark;
- dataset version указан;
- baseline и FormulaLM сравниваются на одном dataset;
- report разделяет proven, inconclusive и blocked;
- artifacts содержат JSON и Markdown;
- blocker cases не превращены в synthetic success.

## 6. Dataset

Dataset version: `formulalm-estimate-ru-2026q2-v1`  
Pricebook: `kolibri-ru-2026q2-v1`  
Domain: Russian construction estimates  
Format: JSONL, one object per line

Обязательные поля:

- `id`;
- `prompt`;
- `client_name`;
- `expected.region`;
- `expected.area_m2`;
- `expected.work_type`;
- `expected.pricebook_version`;
- `expected.formulas`;
- `tags`.

### 6.1 JSONL seed dataset

```jsonl
{"id":"plaster-tatarstan-100","prompt":"100 м2 штукатурки в Татарстане","client_name":"Иван","expected":{"region":"Республика Татарстан","area_m2":"100.00","work_type":"plastering","pricebook_version":"kolibri-ru-2026q2-v1","formulas":["line_total = quantity * labor_unit_price + quantity * material_unit_price","subtotal = labor + materials","grand_total = subtotal + overhead + tax"]},"tags":["plaster","tatarstan","simple-area"]}
{"id":"plaster-tatarstan-42","prompt":"42 м2 штукатурки в Татарстане","client_name":"Алия","expected":{"region":"Республика Татарстан","area_m2":"42.00","work_type":"plastering","pricebook_version":"kolibri-ru-2026q2-v1","formulas":["line_total = quantity * labor_unit_price + quantity * material_unit_price","subtotal = labor + materials","grand_total = subtotal + overhead + tax"]},"tags":["plaster","tatarstan","decimal-sensitive"]}
{"id":"kitchen-12","prompt":"Нужна смета на ремонт кухни 12 м2 в Татарстане","client_name":"Иван","expected":{"region":"Республика Татарстан","area_m2":"12.00","work_type":"kitchen_repair","pricebook_version":"kolibri-ru-2026q2-v1","formulas":["line_total = quantity * labor_unit_price + quantity * material_unit_price","subtotal = labor + materials","grand_total = subtotal + overhead + tax"]},"tags":["kitchen","tatarstan","renovation"]}
{"id":"bathroom-8","prompt":"Смета на санузел 8 м2 в Татарстане","client_name":"Тестовый клиент","expected":{"region":"Республика Татарстан","area_m2":"8.00","work_type":"bathroom_repair","pricebook_version":"kolibri-ru-2026q2-v1","formulas":["line_total = quantity * labor_unit_price + quantity * material_unit_price","subtotal = labor + materials","grand_total = subtotal + overhead + tax"]},"tags":["bathroom","tatarstan","wet-zone"]}
{"id":"flat-20","prompt":"Ремонт квартиры 20 м2 в Татарстане","client_name":"Клиент","expected":{"region":"Республика Татарстан","area_m2":"20.00","work_type":"flat_repair","pricebook_version":"kolibri-ru-2026q2-v1","formulas":["line_total = quantity * labor_unit_price + quantity * material_unit_price","subtotal = labor + materials","grand_total = subtotal + overhead + tax"]},"tags":["flat","tatarstan","fallback"]}
{"id":"plaster-moscow-35","prompt":"35 м2 штукатурки в Москве, нужна смета с материалами","client_name":"ООО Север","expected":{"region":"Москва","area_m2":"35.00","work_type":"plastering","pricebook_version":"kolibri-ru-2026q2-v1","formulas":["regional labor/material coefficients apply","line_total = quantity * labor_unit_price + quantity * material_unit_price","grand_total = subtotal + overhead + tax"]},"tags":["plaster","moscow","region-coeff"]}
{"id":"plaster-spb-27-5","prompt":"Посчитай штукатурку стен 27,5 м2 в Санкт-Петербурге","client_name":"Мария","expected":{"region":"Санкт-Петербург","area_m2":"27.50","work_type":"plastering","pricebook_version":"kolibri-ru-2026q2-v1","formulas":["decimal comma is accepted","regional labor/material coefficients apply","grand_total = subtotal + overhead + tax"]},"tags":["plaster","spb","decimal-comma"]}
{"id":"flat-no-region-18","prompt":"Сделай смету на ремонт квартиры 18 м2","client_name":"Без региона","expected":{"region":"Россия","area_m2":"18.00","work_type":"flat_repair","pricebook_version":"kolibri-ru-2026q2-v1","formulas":["default region profile applies","grand_total = subtotal + overhead + tax"]},"tags":["flat","default-region"]}
{"id":"kitchen-text-area","prompt":"Кухня двенадцать квадратных метров, Татарстан, нужен предварительный расчет","client_name":"Наталья","expected":{"region":"Республика Татарстан","area_m2":"20.00","work_type":"kitchen_repair","pricebook_version":"kolibri-ru-2026q2-v1","formulas":["fallback area applies if numeric area is absent","grand_total = subtotal + overhead + tax"]},"tags":["kitchen","text-number","fallback-area"]}
{"id":"plaster-m2-symbol","prompt":"Штукатурка 64 м², Республика Татарстан","client_name":"Рустам","expected":{"region":"Республика Татарстан","area_m2":"64.00","work_type":"plastering","pricebook_version":"kolibri-ru-2026q2-v1","formulas":["m² symbol is accepted","grand_total = subtotal + overhead + tax"]},"tags":["plaster","unicode-unit"]}
{"id":"bathroom-moscow-6","prompt":"Санузел 6 кв. м Москва под ключ","client_name":"Анна","expected":{"region":"Москва","area_m2":"6.00","work_type":"bathroom_repair","pricebook_version":"kolibri-ru-2026q2-v1","formulas":["regional labor/material coefficients apply","grand_total = subtotal + overhead + tax"]},"tags":["bathroom","moscow","unit-variant"]}
{"id":"plaster-large-250","prompt":"250 м2 штукатурных работ в Татарстане для коммерческого объекта","client_name":"ООО Казань Ремонт","expected":{"region":"Республика Татарстан","area_m2":"250.00","work_type":"plastering","pricebook_version":"kolibri-ru-2026q2-v1","formulas":["large quantity should not break totals","grand_total = subtotal + overhead + tax"]},"tags":["plaster","large-area","commercial"]}
```

### 6.2 Dataset expansion rules

- Добавлять cases только с deterministic expected fields.
- Не включать персональные данные реальных клиентов.
- Каждый новый регион должен иметь явную policy: supported coefficient,
  fallback to Russia или blocker.
- Не смешивать изменение dataset и изменение benchmark runner в одном proof.
- Версионировать dataset при изменении expected semantics.

## 7. Blocker policy

Blocker artifact обязателен, если benchmark не может честно выполниться.

### 7.1 P0 blockers

P0 означает stop immediately, no benchmark:

- OS is Darwin/macOS;
- Control Plane lease отсутствует или задача запущена вне lease;
- отсутствует artifact directory;
- runtime/model credentials требуются, но отсутствуют;
- обнаружен секрет в logs или payload;
- benchmark пишет результаты в shared writable root вместо task artifact dir.

### 7.2 P1 blockers

P1 означает benchmark не запускать до исправления:

- нет Qwen/QW 2.5-compatible model или remote endpoint;
- runtime не отвечает health check;
- disk/RAM ниже минимального порога node policy;
- dataset поврежден или содержит invalid JSONL;
- pricebook version отличается от `kolibri-ru-2026q2-v1`;
- Control Plane показывает stale heartbeat целевого node.

### 7.3 P2 blockers

P2 означает smoke можно завершить, но proof нельзя объявлять:

- latency метрики недоступны;
- QA manual review отсутствует;
- часть cases skipped без явной причины;
- repeat count ниже protocol target;
- версия runtime не записана.

### 7.4 Blocker artifact schema

```json
{
  "task_id": "KOL-FORMULALM-REMOTE-BENCH-6H-20260629",
  "node_id": "server-kfrm",
  "status": "blocked",
  "severity": "P1",
  "category": "missing_model_runtime",
  "message": "Qwen/QW 2.5-compatible runtime is not available on the remote node.",
  "first_seen_at": "2026-06-29T00:00:00Z",
  "preflight": {
    "os": "Linux",
    "runtime": null,
    "model_id": null,
    "artifact_dir": "/kolibri/nodes/server-kfrm/artifacts/<task_id>"
  },
  "safe_next_action": "Install or configure remote runtime, then requeue through Control Plane.",
  "mac_execution": "not_attempted"
}
```

## 8. GitHub report template

Use this as a GitHub issue, PR comment or project update after the remote task
finishes.

```markdown
# FormulaLM Remote Benchmark Report

Task: `<task_id>`  
Node: `<node_id>`  
Control Plane state: `<queued|leased|running|completed|failed|blocked>`  
Dataset: `formulalm-estimate-ru-2026q2-v1`  
Pricebook: `kolibri-ru-2026q2-v1`  
Model/runtime: `<model_id>` / `<runtime_version>`  
Started: `<started_at>`  
Finished: `<finished_at>`  
Artifact reference: `<result_reference>`

## Executive Summary

- Verdict: `<proven|not_proven|blocked|inconclusive>`
- FormulaLM exact total rate: `<value>`
- Baseline exact total rate: `<value>`
- FormulaLM valid JSON rate: `<value>`
- Baseline valid JSON rate: `<value>`
- Main blocker/risk: `<none|summary>`

## Evidence

| Metric | Baseline | FormulaLM | Delta |
| --- | ---: | ---: | ---: |
| valid_json_rate | `<value>` | `<value>` | `<value>` |
| exact_total_rate | `<value>` | `<value>` | `<value>` |
| formula_consistency_rate | `<value>` | `<value>` | `<value>` |
| unique_output_hashes | `<value>` | `<value>` | `<value>` |
| parse_error_rate | `<value>` | `<value>` | `<value>` |
| runtime_error_rate | `<value>` | `<value>` | `<value>` |
| latency_p95_ms | `<value>` | `<value>` | `<value>` |

## Dataset Coverage

- Cases total: `<n>`
- Repeats per case: `<n>`
- Regions: `<regions>`
- Skipped cases: `<n and reasons>`

## Blockers

- `<severity>` `<category>`: `<message>`

## Interpretation

FormulaLM is evaluated as a deterministic overlay/kernel on top of the same
remote base model. This report does not claim model-weight improvement. It only
claims whether the overlay improved validity, reproducibility and exact estimate
totals on the controlled dataset.

## Decision

- `<ship next experiment|fix blockers|expand dataset|do not proceed>`

## Follow-up Tasks

- `<task 1>`
- `<task 2>`
- `<task 3>`
```

## 9. Control Plane task envelope template

Use this payload through Control Plane only. It is intentionally written as a
template so the operator can choose `target_node`, `duration` and exact model
without committing a new repository file.

```json
{
  "task_id": "KOL-FORMULALM-REMOTE-BENCH-PILOT-20260629",
  "kind": "generic_implementation",
  "required_capability": "generic_implementation",
  "permission_pack": "full_autonomy",
  "runner": "codex",
  "target_node": "server-kfrm",
  "goal": "Run a remote-only FormulaLM benchmark pilot on a Linux factory node. Do not run model experiments on the owner's Mac. First write preflight artifacts proving the node is not Darwin and recording runtime/model/disk/RAM/artifact directory. Compare baseline Qwen/QW 2.5-compatible output against FormulaLM deterministic overlay/kernel on dataset formulalm-estimate-ru-2026q2-v1. Return formulalm-benchmark.json, formulalm-benchmark.md, preflight.json, blockers.json if any, and a GitHub-ready report. If prerequisites are missing, do not fake results; complete or fail with a blocker artifact.",
  "role_slot": "formulalm_researcher",
  "role_goal": "prove or falsify FormulaLM improvement with remote-only reproducible benchmarks",
  "remote_guard": {
    "mode": "execute_preflight_then_run_or_block",
    "required_outputs": [
      "preflight.json",
      "formulalm-benchmark.json or blockers.json",
      "formulalm-benchmark.md or blocker report"
    ],
    "darwin_action": "write blockers.json and stop before model call",
    "linux_action": "run benchmark if runtime/model/dataset/pricebook checks pass"
  },
  "acceptance": [
    "No experiment runs on macOS or the owner's Mac",
    "Remote preflight artifact is recorded before benchmark execution",
    "Dataset version and pricebook version are recorded",
    "Baseline and FormulaLM use the same remote model/runtime/settings",
    "Artifacts include formulalm-benchmark.json and formulalm-benchmark.md",
    "Report clearly separates proven improvements from inconclusive or blocked results"
  ],
  "verification_commands": [
    "uname -a",
    "python3 -m compileall -q scripts/formulalm_benchmark.py backend/estimate_engine.py"
  ],
  "max_retries": 1,
  "source": {
    "kind": "manual_control_plane",
    "requested_by": "owner",
    "requested_at": "2026-06-29T00:00:00+03:00",
    "rule": "remote-only; Mac is control/editing surface only"
  }
}
```

## 10. Remote Control Plane commands

These commands are for Control Plane only. They do not start a local benchmark
and do not run a model on Mac.

```bash
export KOLIBRI_FACTORY_CONTROL_URL="http://10.99.0.2:9101"
```

```bash
curl -fsS "$KOLIBRI_FACTORY_CONTROL_URL/health"
```

```bash
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" nodes
```

```bash
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" status --limit 50
```

Submit the existing six-hour remote benchmark envelope:

```bash
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" submit --file ops/envelopes/KOL-FORMULALM-REMOTE-BENCH-6H-20260629.json
```

Poll the remote task:

```bash
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" status KOL-FORMULALM-REMOTE-BENCH-6H-20260629
```

Collect the remote result reference:

```bash
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" collect KOL-FORMULALM-REMOTE-BENCH-6H-20260629
```

Cancel only if the task is unsafe, duplicated or violating remote-only policy:

```bash
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" cancel KOL-FORMULALM-REMOTE-BENCH-6H-20260629 --reason "remote-only policy or runtime blocker"
```

## 11. Completion checklist

- [ ] Control Plane health checked.
- [ ] Target node heartbeat checked.
- [ ] Task submitted through Control Plane.
- [ ] Remote preflight artifact exists.
- [ ] macOS execution explicitly absent.
- [ ] Dataset version recorded.
- [ ] Baseline and FormulaLM use same model/runtime/settings.
- [ ] JSON and Markdown artifacts returned.
- [ ] Blockers are recorded instead of synthetic success.
- [ ] GitHub report posted with verdict and next actions.
