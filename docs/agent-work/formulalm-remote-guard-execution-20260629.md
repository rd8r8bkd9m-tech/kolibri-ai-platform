# FormulaLM remote guard: исполнение

Дата: 2026-06-29
Роль: `Исполнитель FormulaLM remote guard`
Статус: правила переписаны из запрета в исполнимый контракт.

## Что изменено

- `docs/project-policy.md`: FormulaLM теперь описан как цикл
  `preflight -> execute_or_block -> artifacts -> report`.
- `docs/formulalm.md`: главный раздел переписан в исполнимый remote guard.
- `docs/agent-work/formulalm-remote-rd-pack.md`: добавлен state machine для
  remote executor и требование `benchmark_started` или
  `blocked_with_artifact`.
- `ops/envelopes/KOL-FORMULALM-REMOTE-BENCH-6H-20260629.json`: добавлены
  `remote_guard`, `execution_flow` и правило `analysis_only_is_incomplete`.
- `scripts/formulalm_benchmark.py`: guard теперь пишет `preflight.json` до
  model call и `blockers.json`, если запуск происходит на Darwin/macOS.

## Исполнимый контракт

```text
lease_received
  -> preflight_recorded
  -> guard_checked
  -> benchmark_started | blocked_with_artifact
  -> artifacts_written
  -> result_reference_returned
```

Если Linux node готов: агент запускает baseline и FormulaLM на одном dataset,
одной модели, одном runtime и одинаковых настройках.

Если runtime/model/dataset/pricebook отсутствует: агент пишет `blockers.json`
и безопасный next action. Это считается исполнимым результатом, а не
analysis-only.

Если OS равна Darwin/macOS: агент не делает model call, пишет blocker и
останавливается.

## Проверка guard на Mac

Команда не запускала модель и завершилась до model call:

```bash
python3 scripts/formulalm_benchmark.py --out-dir /tmp/kolibri-formulalm-guard-test
```

Результат:

- exit code: `2`;
- создан `/tmp/kolibri-formulalm-guard-test/preflight.json`;
- создан `/tmp/kolibri-formulalm-guard-test/blockers.json`;
- blocker category: `mac_execution_blocked`;
- `platform_system`: `Darwin`.

## Статус 6-часового FormulaLM теста

На момент проверки live Control Plane не содержал task
`KOL-FORMULALM-REMOTE-BENCH-6H-20260629`: `GET /v1/tasks/<id>` вернул `404`.

Значит 6-часовой benchmark нельзя честно объявить выполненным. Текущий
результат: remote guard подготовлен к исполнению и теперь обязан вернуть либо
benchmark artifacts, либо blocker artifacts.

## Серверное состояние

Проверенный fresh generic node:

- `primary-candidate`: online, fresh, capabilities include
  `generic_implementation`.

Текущий blocker для старого target:

- `server-kfrm` не присутствовал в свежем `/v1/nodes` snapshot, поэтому
  six-hour envelope на `server-kfrm` должен ждать восстановления heartbeat или
  быть переназначен отдельным owner-approved envelope.

## Проверки

```bash
python3 -m py_compile scripts/formulalm_benchmark.py
/tmp/kolibri-tbank-agent-py39-venv/bin/python -m pytest -q tests/test_agent_host_telegram_chat.py tests/test_factory_autonomy_contracts.py tests/test_factory_runtime_queue_contracts.py
python3 -m json.tool ops/envelopes/KOL-FORMULALM-REMOTE-BENCH-6H-20260629.json
```

Результаты:

- targeted pytest: `37 passed`;
- JSON envelope валиден;
- Mac guard artifact создаётся до model call.

## Следующее действие

1. Запушить текущие guard changes в GitHub branch.
2. Отправить FormulaLM preflight/benchmark через Control Plane на fresh Linux
   node с `generic_implementation`.
3. Если target node не имеет model runtime, принять `blockers.json` как честный
   результат и назначить отдельную задачу на runtime bootstrap.
