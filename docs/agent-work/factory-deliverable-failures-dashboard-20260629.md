# Factory Deliverable Failures Dashboard — отчет

Дата: 2026-06-29
Ответственный: Codex
Статус: deployed

## Цель

Сделать видимыми для владельца случаи, когда агент пытается закрыть инженерную задачу без `diff`, `checks` и проверяемого результата. После предыдущего hard gate эти события больше не должны прятаться в Redis/логах.

## Что изменено

- `ops/factory_control.py`
  - Добавлен индекс `task_error_type:<error_type>`.
  - `save_task()` обновляет индекс ошибок вместе со state index.
  - `rebuild_task_indexes()` перестраивает error-type индексы.
  - Добавлен быстрый endpoint `GET /v1/tasks/failures?error_type=deliverable_gate_failed&limit=...`.
  - `compact_task()` теперь отдает `error`, `error_type`, `result_reference` без тяжелых `result`/`envelope`.

- `backend/factory_status.py`
  - Добавлен `factory_failures` в `/api/factory/status`.
  - Backend берет failures отдельным быстрым запросом к `/v1/tasks/failures`, чтобы тяжелая общая выборка задач не скрывала gate failures.

- `frontend/src/lib/factoryStatus.js`
  - Добавлен `getFactoryFailureSummary(status)`.

- `frontend/src/components/control/ClusterPanel.jsx`
  - Добавлен блок `Контроль deliverables`.
  - Показывает количество `deliverable_gate_failed`, общий failed count и последние task ids.

- `frontend/src/App.css`
  - Добавлены стили для списка последних deliverable gate failures.

## Live evidence

Публичный API:

```json
{
  "deliverable_gate_failed": 1,
  "failed_total": 1,
  "needs_attention": true,
  "deliverable_gate_recent": [
    {
      "task_id": "KOL-GATE-SMOKE-20260629081046",
      "state": "failed",
      "kind": "generic_implementation",
      "error": "deliverable_gate_failed:missing_code_delta,missing_checks"
    }
  ]
}
```

Control Plane:

```text
GET /v1/tasks/failures?error_type=deliverable_gate_failed&limit=5
returned=1
total=1
```

## Проверки

- `/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py tests/test_factory_runtime_queue_contracts.py tests/test_factory_runtime.py tests/test_factory_autonomy_contracts.py`
- `/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py`
- `npm --prefix frontend run build`
- `python3 -m py_compile backend/factory_status.py ops/factory_control.py tests/test_factory_status.py tests/test_factory_runtime_queue_contracts.py`
- `git diff --check`

Результат основного набора: `42 passed`.

## Деплой

- Control Plane: `/usr/local/bin/kolibri-factory-control`, `kolibri-factory-control.service=active`
- Backend: `/opt/kolibri-ai/backend/factory_status.py`, `kolibri-ai.service=active`
- Frontend: `/opt/kolibri-public/frontend-dist/release-20260629T081522Z-deliverable-summary`
- Public URL: `http://104.253.43.117`

## Следующий шаг

Добавить автоматическое правило в watchdog: если `deliverable_gate_failed` появился, отправлять owner-facing Telegram уведомление и создавать retry-задачу с усиленными acceptance criteria.
