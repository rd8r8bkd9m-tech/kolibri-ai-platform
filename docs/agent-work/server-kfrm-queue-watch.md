# Наблюдение очереди server-kfrm

Дата: 2026-06-29
Роль: `Наблюдатель очереди server-kfrm`
Scope: read-only наблюдение за probe `KOL-SERVER-KFRM-PROBE-20260629`.
Control Plane не мутировать: без SSH, без `submit`, `cancel`, `retry`,
`drain`, ручного lease surgery, deploy и запуска workloads.

## Текущий статус

Live read-only снимок снят через Control Plane `http://10.99.0.2:9101`:

- `/health` на `2026-06-29T04:52:27Z` (`2026-06-29 07:52:27 MSK`):
  `status=ok`, `queue_backend=redis`, `redis=PONG`, `spool_count=0`,
  `spool_replayed=0`.
- Probe `KOL-SERVER-KFRM-PROBE-20260629`: `state=queued`, `attempt=0`,
  `lease_owner=null`, `lease_until=null`, `heartbeat_at=null`,
  `result=null`, `result_reference=null`.
- Probe создан `2026-06-29T03:01:40Z` (`06:01:40 MSK`) и с тех пор не
  получил lease.
- Envelope probe корректный для gate: `kind=read_only_probe`,
  `required_capability=read_only_probe`, `target_node=server-kfrm`,
  `max_retries=1`.
- Executor card `server-kfrm`: `health=online`, `draining=false`,
  `active_task=null`, capabilities включают `generic_implementation`,
  `read_only_probe`, `mesh_node`; ресурсы примерно 8 CPU, 27 GB available RAM,
  150 GB free disk.
- Heartbeat executor `server-kfrm`: `2026-06-28T20:17:15.661022Z`
  (`2026-06-28 23:17:15 MSK`), то есть примерно 8 часов 35 минут до
  health-снимка. Для watcher это stale, несмотря на `health=online`.
- `mesh-server-kfrm` не считать executor-прогрессом: это mesh-shadow node с
  capability `mesh`, без runner-capabilities и без node-local artifacts для
  probe.

Вывод: probe пока не движется. Узел по карточке существует и не draining, но
реальный executor heartbeat stale, поэтому запускать тяжелые задачи или
следующие app-run steps нельзя.

## Что считать прогрессом

Минимальный прогресс:

- В свежем `nodes`-снимке у executor `server-kfrm`, а не у
  `mesh-server-kfrm`, обновился `heartbeat_at` после текущего watcher-снимка и
  heartbeat age стал в пределах 120 секунд или действующего
  `FACTORY_NODE_STALE_AFTER`.
- `server-kfrm` остается `draining=false`, `active_task=null` или показывает
  именно этот probe как активный lease.
- Targeted status probe меняется с `queued` на leased/running:
  `lease_owner` указывает на agent host `server-kfrm`,
  `lease_until` находится в будущем, появляется `attempt_id` или fresh
  `heartbeat_at`.

Успешный прогресс:

- Probe переходит в `completed`.
- Result подтверждает `kind=read_only_probe` и успешное завершение.
- `result_reference` или result path указывает на node-local artifacts под
  namespace `/kolibri/nodes/server-kfrm/artifacts`.
- Acceptance закрыт: lease был именно на `server-kfrm`, без SSH, без секретов,
  без shared writable root.

Не считать прогрессом:

- Обновление только `mesh-server-kfrm`.
- Любое изменение общей длины очереди без изменения targeted status probe.
- Broad `status`/`GET /v1/tasks` со странными counts: в локальных отчетах
  `summary`, `compact`, `limit` и `state` уже давали misleading результаты.
- Lease не на `server-kfrm`, retarget probe на другой node или ручной submit
  дубликата.

## Когда писать Владиславу в Telegram

Отправлять короткий Telegram-отчет только при meaningful state change или по
таймеру no-progress, чтобы не шуметь.

Сразу отправить зеленый отчет:

- probe стал `completed`;
- результат содержит node-local artifact от `server-kfrm`;
- fresh heartbeat `server-kfrm` подтвержден после завершения probe;
- следующий gate можно формулировать как "server-kfrm готов к app-run/QA
  только после отдельного operator decision".

Сразу отправить желтый отчет:

- `server-kfrm` heartbeat восстановился, но probe еще `queued`;
- probe получил lease/running на `server-kfrm`, но результата еще нет;
- probe держит lease дольше ожидаемого lease window или heartbeat task
  перестал обновляться.

Сразу отправить красный отчет:

- `/health` не `ok`, Redis не `PONG`, Control Plane недоступен или
  `spool_count` начал расти без объяснения;
- probe перешел в `failed`, `dead_letter`, `cancelled` или leased не тем node;
- `server-kfrm` ушел в `draining=true`, получил другой stale `active_task` или
  исчез из `/v1/nodes`;
- кто-то мутировал очередь вручную: duplicate submit, cancel/retry/drain,
  lease surgery.

No-progress отчет:

- если после первого live-снимка нет изменений 30 минут, отправить один
  спокойный статус: "Control Plane ok, probe still queued, server-kfrm heartbeat
  stale, действий не предпринимал";
- дальше повторять не чаще одного раза в 30 минут, пока нет state change;
- если watcher останавливается без green/red исхода, отправить финальный
  no-progress summary с последним временем `/health` и targeted status.

Owner-facing формулировка должна быть без лишних внутренних путей и логов.
Task id и node id можно указывать здесь, потому что операторский запрос явно
просит следить именно за `KOL-SERVER-KFRM-PROBE-20260629` и `server-kfrm`.

Шаблон Telegram-сообщения:

```text
server-kfrm watch: Control Plane ok на <MSK time>. Probe <state>.
server-kfrm heartbeat: <fresh/stale, timestamp>. Lease: <none/server-kfrm/other>.
Действий не предпринимал: без SSH, submit/cancel/retry/drain.
Следующий шаг: <ждем heartbeat/probe running/probe completed/operator decision>.
```

## Безопасные status-команды

Эти команды read-only и допустимы для watcher:

```bash
export KOLIBRI_FACTORY_CONTROL_URL="http://10.99.0.2:9101"

curl -fsS --max-time 20 "$KOLIBRI_FACTORY_CONTROL_URL/health"

ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" \
  nodes

ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" \
  status KOL-SERVER-KFRM-PROBE-20260629 --full

ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" \
  collect KOL-SERVER-KFRM-PROBE-20260629

curl -fsS --max-time 20 \
  "$KOLIBRI_FACTORY_CONTROL_URL/v1/tasks/KOL-SERVER-KFRM-PROBE-20260629"
```

Операционно безопасны, но не обязательны для частого polling:

```bash
curl -fsS --max-time 20 "$KOLIBRI_FACTORY_CONTROL_URL/v1/filesystem"
curl -fsS --max-time 20 \
  "$KOLIBRI_FACTORY_CONTROL_URL/v1/agent-messages?target=all&limit=30"
```

Осторожно:

- `ops/kolibri-dispatch status` без task id делает broad `GET /v1/tasks`; это
  read-only, но payload может быть большим, counts могут быть misleading.
- `ops/kolibri-dispatch status --state queued|running|waiting_review` тоже
  read-only, но локальные отчеты показывали, что state filters сейчас не
  authoritative для counts.
- `ops/kolibri-dispatch doctor` не использовать для этого watch: команда
  запускает SSH-проверки node hostnames.

Запрещено:

```bash
ops/kolibri-dispatch submit --file ops/envelopes/KOL-SERVER-KFRM-PROBE-20260629.json
ops/kolibri-dispatch cancel KOL-SERVER-KFRM-PROBE-20260629
ops/kolibri-dispatch drain server-kfrm --enable
ops/kolibri-dispatch drain server-kfrm --disable
ssh server-kfrm
scp ...
```

Также запрещены любые retry/requeue/drain/un-drain через другие CLI, API,
админки или прямое редактирование Redis/spool.

## Watch-петля

1. Снять `/health`; если не `ok`, отправить красный отчет и не делать
   дальнейших действий.
2. Снять `nodes`; выписать только executor `server-kfrm` и игнорировать
   `mesh-server-kfrm` как runner.
3. Снять targeted `status KOL-SERVER-KFRM-PROBE-20260629 --full`.
4. Если state terminal или running/leased, дополнительно снять targeted
   `collect KOL-SERVER-KFRM-PROBE-20260629`.
5. Сравнить с предыдущим watcher-снимком: heartbeat freshness, state,
   lease_owner, lease_until, result_reference.
6. Отправить Telegram только по правилам выше.

Рекомендуемый интервал polling: 60 секунд во время активного ожидания. Если
нет изменений 10 минут, можно перейти на 5 минут. No-progress Telegram не чаще
одного раза в 30 минут.

## Проверки подготовки

- Прочитан Kolibri Factory Admin skill и factory runbook.
- Прочитаны `ops/kolibri-dispatch`,
  `ops/envelopes/KOL-SERVER-KFRM-PROBE-20260629.json`,
  `docs/agent-work/server-kfrm-app-run-plan.md`,
  `docs/agent-work/control-plane-queue-unblock-report.md`.
- Выполнены только read-only live checks: `/health`, `nodes`, targeted
  `status`, targeted `collect`.
- Не выполнялись SSH, `doctor`, `submit`, `cancel`, `retry`, `drain`, deploy,
  model workloads или broad queue mutation.
