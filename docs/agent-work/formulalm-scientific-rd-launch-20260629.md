# Запуск научной разработки FormulaLM

Дата: 2026-06-29 16:16 MSK

## Решение

Создано новое исполнимое задание для удаленного агента:

- Task ID: `KOL-FORMULALM-SCIENTIFIC-RD-20260629`
- Роль: `Исследователь FormulaLM`
- Target node: `primary-candidate`
- Причина выбора узла: среди свежих canonical node это единственный узел с
  `generic_implementation`, `full_autonomy`, 8 CPU и запасом RAM около 12 GB.
- Envelope:
  `ops/envelopes/KOL-FORMULALM-SCIENTIFIC-RD-20260629.json`

## Что агент обязан исполнить

1. Получить lease через Control Plane.
2. Записать `preflight.json` до любого model call.
3. Остановиться с `blockers.json`, если узел оказался Darwin/macOS или если
   runtime/model/dataset недоступны.
4. Если runtime готов, запустить научную программу:
   - smoke benchmark: 5 cases x 2 repeats;
   - pilot benchmark: 20 cases x 5 repeats или доступный dataset;
   - six-hour benchmark: только когда lease/runtime безопасны.
5. Доработать benchmark harness, если метрики H1-H5 не покрыты:
   `unique_output_hashes_per_case`, `parse_error_rate`,
   `runtime_error_rate`, `formula_consistency_rate`, `latency p50/p95`,
   `blocked_reason_count`.
6. Сохранить артефакты в
   `docs/agent-work/formulalm-scientific-rd-20260629/`.
7. Создать итоговый отчет
   `docs/agent-work/formulalm-scientific-rd-20260629.md`.
8. Закоммитить и запушить ветку агента.

## Remote-only guard

Mac используется только как поверхность управления, редактирования envelope и
проверки Control Plane. FormulaLM/Qwen/QW 2.5/model benchmark на Mac запрещен.

Если агент не может стартовать benchmark, он обязан вернуть blocker artifact,
а не аналитический текст без результата.

## Текущий статус перед отправкой

- Control Plane: `http://10.99.0.2:9101`
- Registered canonical nodes: 21
- Fresh canonical nodes: 20
- Fresh canonical generic implementation nodes: 1
- Queue before submission: 2 queued read-only tasks, active tasks: 0

## Проверка локального пакета

Локально не запускались модельные эксперименты. Разрешенная проверка:

```bash
python3 -m py_compile scripts/formulalm_benchmark.py ops/kolibri-dispatch
```

Результат: passed.
