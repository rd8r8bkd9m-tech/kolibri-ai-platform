# Отчет по фабрике Kolibri

Дата: 2026-06-29 09:00 MSK

## Краткий статус

Фабрика работает частично, но не на 80% мощности.

Control Plane живой: `/health` возвращает `status=ok`, Redis отвечает `PONG`.
Очередь живая, но перегружена: в compact-срезе `73` задачи в очереди и `0` активных задач.

## Что реально выполнено

1. P0-задача приложения `KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629` дошла до `waiting_review`.
   Фактическое выполнение завершено, `error_type=null`, executor `main:agent-host-main`.

2. Создана и отправлена в фабрику review-задача:
   `KOL-P0-APP-VERIFY-REVIEW-20260629`.
   Статус после submit: `queued`.

3. Создана и отправлена задача восстановления `server-kfrm`:
   `KOL-SERVER-KFRM-HEARTBEAT-RECOVERY-20260629`.
   Задача была взята узлом `home`, но упала с ошибкой:
   `unsupported task kind: generic_implementation`.

4. Подтвержден блокер `server-kfrm`: основной `server-kfrm` и `mesh-server-kfrm` stale, задача recovery без lease/result до отдельного восстановления runtime.

5. Манифест `ops/agent1000_manifest.json` переведен ближе к машинному формату:
   добавлены `no_mac_experiments`, `safety_limits`, `batches`, `task_templates`, `blocker_rules`.

## Активные исполнители и результаты

- Сборщик результата P0: завершен, создал JSON/Markdown отчет.
- Интегратор результата P0: завершен, создал review/integration план.
- Оператор CI PR #46: завершен, подтвердил зеленые CI на head `4fd32d3d`.
- Сборщик server-kfrm: завершен, подтвердил `not_ready`.
- Инженер heartbeat recovery: завершен, создал envelope для восстановления `server-kfrm`.
- Инженер rollout queue-kind compat: завершен, создал rollout checklist.

## Главный P0-блокер

На узлах разные версии Agent Host.

`main` уже умеет `generic_implementation`, а `home` свежий и способен брать задачу, но его runtime не поддерживает этот kind.
Из-за этого задания попадают в Control Plane, lease может выдаваться, но выполнение падает.

Следующее машинное действие:

```bash
deploy updated ops/agent_host.py to every fresh execution node
restart kolibri-agent-host.service
verify generic_implementation smoke task on home/main
re-submit KOL-SERVER-KFRM-HEARTBEAT-RECOVERY-20260629 after runtime parity
```

## Проверки

Выполнено локально как контрольный пульт, без сборки приложения на Mac:

```bash
git diff --check
python3 -m json.tool <machine-json-files>
bash -n scripts/deploy_readiness_gate.sh scripts/server_kfrm_submission_guard.sh
python3 -m py_compile ops/factory_control.py ops/agent_host.py tests/test_factory_runtime_queue_contracts.py
/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_runtime_queue_contracts.py tests/test_factory_agent_messages.py
```

Результат pytest:

```text
9 passed in 0.46s
```

## Вывод

Фабрика не стоит: задачи создаются, P0-проверка приложения выполнена и переведена в review.
Но фабрика еще не на 80%, потому что worker runtime не выровнен на всех свежих узлах.
Главная следующая работа: rollout Agent Host compatibility patch на fresh execution nodes и повторный submit recovery/server review задач.
