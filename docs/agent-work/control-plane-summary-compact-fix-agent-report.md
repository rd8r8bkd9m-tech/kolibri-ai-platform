# Control Plane summary compact fix agent report

Дата: 2026-06-29
Роль: Control Plane API engineer
Статус: локально исправлено, без деплоя

## Симптом

`GET /v1/tasks?summary=1&compact=1&limit=10` мог вернуть `500`, если в
операционном срезе задач встречалась запись с `envelope: null` или другим
не-объектным envelope. Минимальное воспроизведение через `Handler.do_GET`
до фикса возвращало:

```text
500 control_plane_error "'NoneType' object has no attribute 'get'"
```

## Исправление

- `compact_task()` теперь безопасно трактует не-dict `envelope` как пустой
  объект, поэтому compact response не падает на неровной старой записи.
- Unfiltered `summary+compact` переведён на operational fast path через
  `operational_task_sample(limit=..., compact=True)`, чтобы использовать тот же
  `queue_prefix + active_task_ids + MGET` контракт, что и обычный быстрый
  `/v1/tasks`.
- `summary_scope` для этого пути теперь `queue_active_index`.

## Тесты

Добавлено/обновлено покрытие в
`tests/test_factory_runtime_queue_contracts.py`:

- compact summary использует operational fast path и включает active tasks;
- endpoint-level regression для
  `/v1/tasks?summary=1&compact=1&limit=10` с `envelope: null` возвращает `200`,
  а не `500`;
- существующий compact listing тест адаптирован под `load_tasks`/fast path.

## Проверки

```bash
python3 - <<'PY'
# one-off Handler.do_GET harness for /v1/tasks?summary=1&compact=1&limit=10
# with a BAD-ENVELOPE task
PY
```

Результат: `200`, task compact payload содержит `target_node: null`.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile \
  ops/factory_control.py tests/test_factory_runtime_queue_contracts.py
```

Результат: passed.

```bash
python3 -m venv /tmp/kolibri-control-plane-pytest-venv
/tmp/kolibri-control-plane-pytest-venv/bin/python -m pip install -q pytest
PYTHONDONTWRITEBYTECODE=1 /tmp/kolibri-control-plane-pytest-venv/bin/python \
  -m pytest -q tests/test_factory_runtime_queue_contracts.py
```

Результат: `24 passed in 0.73s`.

## Ограничения

- Деплой не выполнялся.
- Локальный `127.0.0.1:9101` не был запущен, поэтому live curl не применялся.
- В рабочем дереве присутствовали чужие изменения вне этой задачи; они не
  откатывались.
