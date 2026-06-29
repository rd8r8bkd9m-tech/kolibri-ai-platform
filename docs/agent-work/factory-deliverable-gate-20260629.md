# Factory Deliverable Gate — отчет

Дата: 2026-06-29
Ответственный: Codex
Статус: deployed

## Цель

Закрыть системный долг control plane: автономная исполнительская задача не должна становиться `completed`, если агент не оставил проверяемый результат разработки.

## Что изменено

- В `ops/factory_control.py` добавлен gate для автономных инженерных задач:
  - `owner_remote_task`
  - `generic_implementation`
  - совместимый `remote_implementation_runner_ready`
- Для таких задач completion теперь требует:
  - `result_reference`
  - code delta: `changed_files` или `commit` или `pull_request_url`/`pr_url`
  - `checks`
- Если evidence нет, `/v1/tasks/<task_id>/complete` возвращает `422`, задача переводится в `failed`, а в `attempt_history` пишется `failed_deliverable_gate`.
- `telegram-chat:*` исключен из инженерного gate, чтобы живой диалог владельца не ломался.

## Live smoke

Control node: `10.99.0.2`

Команды:

```bash
curl -fsS http://10.99.0.2:9101/v1/health
POST /v1/tasks/KOL-GATE-SMOKE-.../complete
```

Результат:

```text
HTTP_CODE=422
error=deliverable_gate_failed
detail=deliverable_gate_failed:missing_code_delta,missing_checks
task.state=failed
attempt_history[-1].status=failed_deliverable_gate
```

## Тесты

- `python3 -m py_compile ops/factory_control.py tests/test_factory_runtime_queue_contracts.py`
- `/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_runtime_queue_contracts.py tests/test_factory_runtime.py tests/test_factory_autonomy_contracts.py`
- `/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_runtime_queue_contracts.py tests/test_factory_runtime.py tests/test_factory_autonomy_contracts.py tests/test_telegram_gateway.py`
- `git diff --check`

Результат расширенного набора: `69 passed`.

## Деплой

- Развернуто на control node: `/usr/local/bin/kolibri-factory-control`
- Сервис перезапущен: `kolibri-factory-control.service`
- Статус после перезапуска: `active (running)`
- Health: `status=ok`, `redis=PONG`

## Следующий шаг

Следующий полезный слой — вынести этот gate в owner-facing dashboard/API summary: показывать количество `deliverable_gate_failed`, последние задачи и ссылки на их result/log artifacts.
