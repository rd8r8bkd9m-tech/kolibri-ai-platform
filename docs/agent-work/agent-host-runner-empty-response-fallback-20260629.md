# Agent Host runner empty response fallback

Дата: 2026-06-29
Статус: выполнено и задеплоено на `main`

## Проблема

В live-задачах фабрики был виден сбой:

- `mimo completed without text response`
- задачи `product_implementation` dispatch-ились как неподдерживаемый kind

Это ломало промышленный конвейер: задача могла получить lease, процесс отработать, но Control Plane видел только общий `runtime_error`, без точной классификации и без удобного retry-контекста.

## Исправление

- Добавлен `RunnerEmptyResponseError`.
- Добавлен `RunnerUnavailableError`.
- Empty AI runner response теперь классифицируется как `runner_empty_response`.
- Missing runner binary классифицируется как `runner_unavailable`.
- Failure `result.json` содержит:
  - `error_type`
  - `log_paths`
  - `stdout_tail`
  - `stderr_tail`
- Для generic implementation добавлен fallback:
  - если `mimo` завершился без parseable text,
  - и на узле есть `codex`,
  - задача автоматически повторяет AI-вызов через `codex exec --json`.
- `product_implementation` теперь мапится на `generic_implementation`.

## Проверки

Локально:

```text
/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_autonomy_contracts.py tests/test_agent_host_telegram_chat.py tests/test_factory_runtime.py tests/test_factory_runtime_queue_contracts.py tests/test_factory_lease_watchdog.py tests/test_telegram_gateway.py tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py
103 passed
```

```text
python3 -m py_compile ops/agent_host.py
git diff --check
passed
```

На сервере `10.99.0.2`:

- `/usr/local/bin/kolibri-agent-host` обновлён.
- `kolibri-agent-host.service` перезапущен.
- `systemctl is-active kolibri-agent-host.service`: `active`.
- Deployed harness подтвердил:
  - `error_type=runner_empty_response`
  - `retry=true`
  - `stdout_tail=true`
  - `stderr_tail=true`
- Deployed runtime mapping:
  - `product_implementation=generic_implementation`
  - `remote_implementation_runner_ready=generic_implementation`
- Node `main`:
  - `health=online`
  - `fresh=true`
  - `agent_id=agent-host-main`

## Файлы

- `ops/agent_host.py`
- `tests/test_factory_autonomy_contracts.py`
- `tests/test_factory_runtime.py`

## Следующий риск

В очереди остаются старые failed/retry задачи, созданные до этого патча. Watchdog/control plane уже умеет переотправлять deliverable failures; следующим шагом стоит добавить отдельный индекс и retry policy для `runner_empty_response` и `unsupported task kind`.

