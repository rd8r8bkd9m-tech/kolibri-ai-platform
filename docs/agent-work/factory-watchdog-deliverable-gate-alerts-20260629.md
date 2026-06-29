# Factory Watchdog Deliverable Gate Alerts — отчет

Дата: 2026-06-29
Ответственный: Codex
Статус: deployed

## Цель

Сделать фабрику самореагирующей: если Control Plane отклоняет фиктивный `completed` из-за отсутствия `diff/checks`, watchdog должен увидеть это и отправить owner-facing уведомление, но не спамить одним и тем же событием каждые 5 минут.

## Что изменено

- `ops/factory_lease_watchdog.py`
  - Watchdog теперь читает `GET /v1/tasks/failures?error_type=deliverable_gate_failed`.
  - В `summary` добавлены:
    - `deliverable_gate_status`
    - `deliverable_gate_failed`
    - `deliverable_gate_recent`
    - `deliverable_gate_new`
    - `deliverable_gate_new_task_ids`
  - `should_notify()` реагирует на `deliverable_gate_new > 0`.
  - Rollup хранит `deliverable_gate_seen_task_ids`, чтобы не отправлять повторные Telegram уведомления по старым task ids.
  - `actions_total` учитывает только новые gate failures, а не один и тот же persistent total.

## Live evidence

Первый ручной запуск после деплоя:

```json
{
  "deliverable_gate_failed": 1,
  "deliverable_gate_new": 1,
  "telegram": {
    "status": "sent",
    "chat_id": 6608299207,
    "parts": 4
  }
}
```

Второй запуск сразу после первого:

```json
{
  "deliverable_gate_failed": 1,
  "deliverable_gate_new": 0,
  "telegram": {
    "status": "skipped",
    "reason": "no_action"
  }
}
```

Это подтверждает, что новый gate failure уведомляет владельца один раз, а затем не спамит.

## Проверки

- `/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_lease_watchdog.py tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py tests/test_factory_runtime_queue_contracts.py`
- `python3 -m py_compile ops/factory_lease_watchdog.py tests/test_factory_lease_watchdog.py`
- `git diff --check`

Результат: `41 passed`.

## Деплой

- Развернуто: `/usr/local/bin/kolibri-factory-lease-watchdog`
- Timer: `kolibri-factory-lease-watchdog.timer=active`
- Последний отчет: `/var/lib/kolibri-factory-control/watchdog/latest.json`

## Следующий шаг

Следующий слой автоматизации — создавать retry-задачу для `deliverable_gate_failed` с усиленными acceptance criteria и ссылкой на исходный result/log artifact.
