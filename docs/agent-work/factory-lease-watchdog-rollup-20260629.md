# Factory lease watchdog rollup

Дата: 2026-06-29
Ветка: `codex/factory-autonomy-pwa-billing`

## Цель

Watchdog уже исправляет lease/stuck задачи и отправляет Telegram только при
action/problem. Эта правка добавляет накопительный summary, чтобы видеть не
только последний запуск, но и тренд по requeue/dead-letter/stuck.

## Добавлено

- `summary.json` рядом с watchdog отчетами;
- `latest-summary.md` для быстрого чтения человеком;
- накопительные счетчики:
  - `runs_total`;
  - `runs_ok`;
  - `runs_degraded`;
  - `runs_failed`;
  - `actions_total`;
  - totals по `expired`, `stuck`, `requeued_*`, `dead_lettered_*`;
- `recent_actions` до 20 последних action/problem событий.

## Live deploy evidence

Main server: `root@10.99.0.2`

После deploy и ручного run:

```json
{
  "latest_summary": {
    "status": "ok",
    "redis": "PONG",
    "task_total": 693,
    "lease_index_total": 0,
    "expired": 0,
    "stuck": 0,
    "requeued_expired": 0,
    "requeued_stuck": 0,
    "dead_lettered_expired": 0,
    "dead_lettered_stuck": 0
  },
  "telegram": {
    "status": "skipped",
    "reason": "no_action"
  },
  "rollup": {
    "runs_total": 1,
    "runs_ok": 1,
    "runs_degraded": 0,
    "actions_total": 0
  },
  "files": [
    "latest-summary.md"
  ]
}
```

Файлы на сервере:

```text
/var/lib/kolibri-factory-control/watchdog/summary.json
/var/lib/kolibri-factory-control/watchdog/latest-summary.md
```

## Локальные проверки

```bash
/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_lease_watchdog.py
```

Результат: `8 passed`.

```bash
python3 -m py_compile ops/factory_lease_watchdog.py tests/test_factory_lease_watchdog.py
git diff --check
```

Результат: passed.

## Следующий шаг

Сделать owner-facing dashboard card в Control Panel: показывать `runs_total`,
`actions_total`, последний action и ссылку/путь на `latest-summary.md`.
