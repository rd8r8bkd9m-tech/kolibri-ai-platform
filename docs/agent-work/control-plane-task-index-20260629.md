# Control Plane task state index

Дата: 2026-06-29
Ветка: `codex/factory-autonomy-pwa-billing`
Цель: убрать P0-долг, из-за которого `/v1/tasks?state=...`, reaper и
GitHub gate зависели от полного scan всех задач.

## Исправлено

- `ops/factory_control.py` поддерживает Redis-индексы:
  - `task_state:<state>` для быстрых выборок по состоянию;
  - `task_active_ids` для активной витрины;
  - lease-state выборку для reaper: `leased`, `running`, `review`.
- `save_task()` обновляет state-index при каждом изменении state.
- Добавлен lazy-safe rebuild: старые задачи можно проиндексировать через
  `POST /v1/tasks/rebuild-indexes`.
- Rebuild оптимизирован через пакетный `MGET` и групповые `SADD`, чтобы не
  открывать Redis-соединение на каждую задачу.
- `GET /v1/tasks?state=<state>&limit=<n>&offset=<n>` возвращает данные из
  state-index и отдает метаданные `source=state_index`.
- `ops/kolibri-dispatch` получил команды:
  - `status --state ... --limit ... --offset ... --full`;
  - `rebuild-indexes`;
  - `reap-expired` продолжает работать через ограниченный lease-index.

## Live deploy evidence

Main server: `root@10.99.0.2`
Service: `kolibri-factory-control.service`

Команды:

```bash
scp ops/factory_control.py root@10.99.0.2:/usr/local/bin/kolibri-factory-control
scp ops/kolibri-dispatch root@10.99.0.2:/usr/local/bin/kolibri-dispatch
systemctl restart kolibri-factory-control.service
/usr/local/bin/kolibri-dispatch rebuild-indexes --control-url http://10.99.0.2:9101 --timeout 20
```

Результат rebuild:

```json
{
  "indexed": 689,
  "missing": 0,
  "states": {
    "cancelled": 20,
    "completed": 407,
    "dead_letter": 24,
    "failed": 147,
    "queued": 65,
    "running": 1,
    "waiting_review": 25
  }
}
```

State-filtered live check:

```json
{
  "source": "state_index",
  "candidate_total": 25,
  "tasks_scanned": 25,
  "tasks_matched": 25,
  "tasks_returned": 5,
  "tasks_truncated": true
}
```

Reaper live check:

```json
{
  "task_total": 689,
  "lease_index_total": 1,
  "checked": 1,
  "expired": 0,
  "scan_truncated": false
}
```

GitHub gate dry-run:

```json
{
  "checked": 20,
  "existing_total": 17,
  "created_total": 0,
  "skipped_total": 3
}
```

## Локальные проверки

```bash
/tmp/kolibri-p0-venv/bin/python -m pytest -q \
  tests/test_factory_runtime_queue_contracts.py \
  tests/test_factory_runtime.py \
  tests/test_github_pr_gate.py
```

Результат: `19 passed`.

```bash
python3 -m py_compile ops/factory_control.py ops/kolibri-dispatch ops/github_pr_gate.py
git diff --check
```

Результат: passed.

## Остаток

Полный автономный контур еще должен создать ready-mode для GitHub gate:
после dry-run можно запускать недостающие PR creation задачи пакетами, но уже
без риска таймаута на получении `waiting_review` списка.
