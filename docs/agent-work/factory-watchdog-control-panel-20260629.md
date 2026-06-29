# Factory watchdog in Control Panel

Дата: 2026-06-29
Ветка: `codex/factory-autonomy-pwa-billing`

## Цель

Сделать lease/stuck watchdog видимым владельцу в обычном Control Panel, а не
только в файлах на сервере. Это связывает автономное лечение фабрики с
owner-facing статусом приложения.

## Изменения

- `backend/factory_status.py` читает:
  - `/var/lib/kolibri-factory-control/watchdog/summary.json`;
  - `/var/lib/kolibri-factory-control/watchdog/latest.json`.
- `/api/factory/status` теперь возвращает `watchdog`:
  - `available`;
  - `latest_summary`;
  - `telegram`;
  - `rollup.runs_total`;
  - `rollup.actions_total`;
  - totals по `expired`, `stuck`, `requeued_*`, `dead_lettered_*`.
- `frontend/src/lib/factoryStatus.js` добавляет `getWatchdogSummary`.
- `frontend/src/components/control/ClusterPanel.jsx` показывает блок
  `Автолечение leases` и compact stats: Runs, Actions, Expired, Stuck,
  Requeue, Dead.

## Live deploy evidence

Public API:

```json
{
  "status": "online",
  "watchdog_available": true,
  "runs_total": 2,
  "actions_total": 0,
  "latest_status": "ok",
  "telegram": {
    "status": "skipped",
    "reason": "no_action"
  }
}
```

Public frontend:

```text
/assets/index-CPWSCO3M.js
/assets/index-CGBAlW_W.css
```

Bundle contains owner-facing text:

```text
Автолечение leases
```

## Локальные проверки

```bash
/tmp/kolibri-p0-venv/bin/python -m pytest -q \
  tests/test_factory_status.py \
  backend/tests/test_factory_status_fast_health.py
```

Результат: `10 passed`.

```bash
npm --prefix frontend run build
python3 -m py_compile backend/factory_status.py tests/test_factory_status.py
git diff --check
```

Результат: passed. Frontend build прошел с обычным Vite chunk-size warning.

## Следующий шаг

Добавить отдельный owner-facing drilldown для watchdog recent actions: список
последних requeue/dead-letter событий с task id, lease owner и причиной.
