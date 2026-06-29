# Server-kfrm blocker summary

Дата: 2026-06-29
Агент: `Документовод server-kfrm blocker`
Назначение: короткая owner-facing сводка для Telegram/GitHub.
Scope: только документация; код, очередь и Control Plane не менялись.

## Короткий статус

`server-kfrm` пока заблокирован для app-run/QA: probe стоит в очереди, lease
не выдан, результата нет.

- Canonical status: `queued`
- Blocker: `no lease / no result`
- Task: `KOL-SERVER-KFRM-PROBE-20260629`
- Current state: `queued`
- Lease: отсутствует (`lease_owner=null`, `lease_until=null`)
- Result: отсутствует (`result=null`, `result_reference=null`)

Пока нет lease именно на `server-kfrm` и completed-result от read-only probe,
нельзя считать сервер готовым к запуску приложения, QA или тяжелых workloads.

## Telegram summary

```text
server-kfrm: задача пока в очереди. Lease нет, результата нет, поэтому запуск
приложения/QA/нагрузок не начинаем. Следующий безопасный шаг - только read-only
проверка Control Plane и ожидание свежего heartbeat/lease.
```

Отправлять повторно только при meaningful state change или no-progress таймеру,
не чаще одного раза в 30 минут.

## GitHub status packet

```text
status: queued
summary: server-kfrm probe is queued; no lease and no result yet.
task_id: KOL-SERVER-KFRM-PROBE-20260629
report_file: docs/agent-work/server-kfrm-blocker-summary.md
telegram_summary: server-kfrm в очереди; lease и результата нет, запуск не начинаем.
next_step: снять targeted read-only status через Control Plane и ждать lease/completed.
project_sync: pending
next_report_at: on state change or after 30 minutes without progress
```

## Следующий безопасный шаг

1. Снять только read-only snapshot Control Plane: `/health`, `nodes`, targeted
   `status KOL-SERVER-KFRM-PROBE-20260629 --full`, targeted `collect`.
2. Подтвердить, что executor `server-kfrm` имеет fresh heartbeat и не draining.
3. Ждать перехода probe в lease/running/completed без ручного вмешательства.
4. Если probe завершится успешно, отдельно запросить operator decision перед
   app-run/QA. Если появится failed/dead_letter/lease не тем node - оформить
   blocker, не чинить очередь вручную.

## Запреты

- Не выполнять SSH/SCP на `server-kfrm`.
- Не делать duplicate submit probe и не запускать app-run/QA/model workloads.
- Не делать `cancel`, `retry`, `requeue`, `drain`, `un-drain` или lease surgery.
- Не редактировать Redis/spool/Control Plane state вручную.
- Не считать `mesh-server-kfrm` executor-прогрессом для probe.
- Не публиковать в Telegram raw logs, локальные пути, секреты, task/node
  детали сверх уже согласованной диагностики.
- Не трогать код в рамках этой документационной задачи.

## Источники

- `docs/agent-work/server-kfrm-queue-watch.md`
- `docs/agent-work/server-kfrm-app-run-plan.md`
- `docs/agent-work/github-telegram-status-ops.md`
- `docs/agent-work/control-plane-queue-unblock-report.md`
