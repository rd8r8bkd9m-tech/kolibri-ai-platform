# Server-kfrm runtime recovery

Дата: 2026-06-29  
Роль: `Восстановитель server-kfrm`  
Scope: runbook для безопасного восстановления `server-kfrm` как Agent Host
runtime. В рамках подготовки этого документа live серверы, Control Plane state,
очередь, leases, drain-флаги, SSH и model workloads не трогались.

## Короткий вывод

`server-kfrm` нельзя считать готовым executor только по `health=online`.
Control Plane вычисляет freshness по `heartbeat_at`: если heartbeat старше
`FACTORY_NODE_STALE_AFTER` (кодовой default: 120 секунд), node получает
`fresh=false`, а отображаемый `health` становится `stale`.

Последний зафиксированный в связанных отчетах executor heartbeat:
`2026-06-28T20:17:15.661022Z` (`2026-06-28 23:17:15 MSK`). На live-снимке
`2026-06-29T04:52:27Z` (`2026-06-29 07:52:27 MSK`) age был около 8 часов
35 минут, поэтому `server-kfrm` stale, даже если карточка узла содержала
`health=online`, `draining=false`, `active_task=null`, 8 CPU, около 27 GB RAM,
150 GB disk и capabilities `generic_implementation`, `read_only_probe`,
`mesh_node`.

Вернуть node в fresh можно только восстановив штатный Agent Host так, чтобы он:

- зарегистрировался через `POST /v1/nodes/register`;
- начал регулярно слать `POST /v1/nodes/server-kfrm/heartbeat`;
- прошел targeted `read_only_probe` именно на executor `server-kfrm`;
- вернул node-local artifact/result через Control Plane, без SSH как product
  path и без shared writable root.

`mesh-server-kfrm` не является доказательством восстановления executor:
это mesh-shadow presence, а не Agent Host с node-local worktree/artifacts.

## Почему node stale

Фактический контракт в `ops/factory_control.py`:

- `heartbeat_age_seconds()` считает возраст `heartbeat_at`;
- `decorate_node()` выставляет `fresh = age is not None and age <= NODE_STALE_AFTER`;
- если `fresh=false`, отображаемый `health` принудительно становится `stale`;
- register/heartbeat endpoint обновляет `heartbeat_at` серверным `utc_now()`.

Значит stale может возникнуть при любом из этих сценариев:

- `kolibri-agent-host.service` на `server-kfrm` остановлен, падает или завис;
- Agent Host не может достучаться до `KOLIBRI_FACTORY_CONTROL_URLS`;
- runtime/env после обновлений не совпадает с текущим контрактом
  `ops/agent_host.py`;
- node id в env отличается от ожидаемого `server-kfrm`, и heartbeat идет в
  другую карточку;
- процесс жив, но не выполняет heartbeat loop из-за ошибки в lease/task path;
- сеть/route до `http://10.99.0.2:9101` недоступны с node.

До read-only probe это не различается достоверно. Поэтому recovery начинается
со снимка Control Plane, а не с heavy workload.

## Read-only проверки перед любым восстановлением

Эти команды безопасны как диагностика. Они не должны менять очередь, leases,
drain или live runtime:

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

curl -fsS --max-time 20 "$KOLIBRI_FACTORY_CONTROL_URL/v1/filesystem"
```

Проверить в ответах:

- `/health`: `status=ok`, Redis отвечает, spool не растет;
- executor card именно `server-kfrm`, не `mesh-server-kfrm`;
- `heartbeat_at`, `heartbeat_age_seconds`, `fresh`, `health`, `draining`;
- `active_task` и `active_task_state`, особенно terminal/stale задачи;
- capabilities включают `read_only_probe` и `generic_implementation`;
- probe `KOL-SERVER-KFRM-PROBE-20260629` не был duplicated и не leased другой
  node;
- `result_reference` появляется только после completed probe.

Не использовать для этого recovery:

```bash
ops/kolibri-dispatch doctor
ops/kolibri-dispatch submit --file ops/envelopes/KOL-SERVER-KFRM-PROBE-20260629.json
ops/kolibri-dispatch cancel KOL-SERVER-KFRM-PROBE-20260629
ops/kolibri-dispatch drain server-kfrm --enable
ops/kolibri-dispatch drain server-kfrm --disable
ssh server-kfrm
scp ...
```

`doctor` нежелателен здесь, потому что может уходить в SSH-проверки. Повторный
`submit` запрещен, если probe уже live queued/running.

## Безопасное обновление Agent Host

Штатный путь восстановления для существующего или нового node - golden
bootstrap из репозитория. Он устанавливает `/usr/local/bin/kolibri-agent-host`,
systemd unit `kolibri-agent-host.service`, env
`/etc/kolibri-agent-host.env`, node-local roots и делает controlled restart с
jitter.

Операторский canary порядок:

1. Снять read-only snapshot из предыдущего раздела.
2. Если нужно массовое восстановление, сначала оставить/включить drain для
   кандидатов в rollout, чтобы свежий после рестарта узел не схватил heavy
   lease до probe. Для этой документационной задачи drain не менялся.
3. На самом `server-kfrm` применить bootstrap из проверенного checkout:

```bash
KOLIBRI_NODE_ID=server-kfrm \
KOLIBRI_FACTORY_CONTROL_URLS=http://10.99.0.2:9101 \
KOLIBRI_AGENT_CAPABILITIES=read_only_probe,generic_implementation,review,image_generation,mesh_node,permission:* \
KOLIBRI_AGENT_PERMISSIONS='*' \
KOLIBRI_AGENT_PERMISSION_PACKS=full_autonomy \
KOLIBRI_MAX_INFLIGHT=1 \
KOLIBRI_HEARTBEAT_INTERVAL=10 \
KOLIBRI_LEASE_REFRESH=20 \
KOLIBRI_BOOTSTRAP_RESTART_JITTER=60 \
sudo -E ops/bootstrap_factory_node.sh
```

4. Проверить на node только service health, без запуска workload:

```bash
systemctl status --no-pager kolibri-agent-host.service
journalctl -u kolibri-agent-host.service -n 100 --no-pager
```

5. С Control Plane стороны дождаться fresh heartbeat:

```bash
curl -fsS --max-time 20 "$KOLIBRI_FACTORY_CONTROL_URL/v1/nodes"
```

6. Только после fresh heartbeat разрешить существующему
   `KOL-SERVER-KFRM-PROBE-20260629` получить lease. Если probe еще не создан,
   submit должен быть отдельным operator decision с idempotency check.
7. Считать recovery успешным только после completed read-only probe с lease
   owner `server-kfrm` и node-local artifact/result.

Если runtime нужно обновить через очередь, а не руками на сервере, использовать
отдельный rollout envelope вроде `KOL-CODEX-CLI-ROLLOUT-20260629`, но только
после fresh heartbeat/probe gate. Ручной SSH не должен становиться постоянным
product control path.

## Fresh criteria

`server-kfrm` возвращен в рабочий пул, если одновременно выполнено:

- latest `/v1/nodes` показывает executor `server-kfrm`;
- `fresh=true`;
- `heartbeat_age_seconds <= FACTORY_NODE_STALE_AFTER` или <= 120 секунд при
  default;
- `health=online`;
- `draining=false` после явного operator decision;
- `active_task=null` или `active_task` соответствует текущему non-terminal
  lease;
- capabilities включают `read_only_probe` и `generic_implementation`;
- `KOL-SERVER-KFRM-PROBE-20260629` completed с `lease_owner=server-kfrm`;
- result не содержит секретов, приватных логов, raw auth или shared-root paths;
- artifact namespace относится к `/kolibri/nodes/server-kfrm/...`.

До выполнения этих условий нельзя запускать на `server-kfrm` product QA,
build/UI rollout, `generic_implementation` backlog или FormulaLM benchmark.

## Как не запустить FormulaLM/LLM на Mac

Guardrail простой: Mac/control машина не является compute target для model
workloads. На Mac можно только читать репозиторий, готовить envelopes и делать
read-only Control Plane checks.

Запрещено на Mac:

- `python3 scripts/formulalm_benchmark.py`;
- Ollama/llama.cpp/vLLM/Qwen local benchmark;
- любые 6h model workloads;
- запуск task logic напрямую вместо Control Plane lease;
- перенос node-local artifact reads на owner Mac.

Разрешено на Mac:

- редактировать docs/envelopes;
- проверять, что `scripts/formulalm_benchmark.py` содержит remote-only guard;
- смотреть `ops/envelopes/KOL-FORMULALM-REMOTE-BENCH-6H-20260629.json`;
- выполнять `python3 -m compileall` для измененных Python файлов, если они
  менялись;
- выполнять read-only HTTP/CLI checks Control Plane.

FormulaLM можно запускать только после:

1. `server-kfrm` fresh;
2. completed read-only probe;
3. нет ожидающей P0 release QA нагрузки;
4. task leased именно remote Linux node;
5. preflight artifact доказывает OS не Darwin, hostname/node id/task id,
   runtime/model id, disk/RAM и artifact directory.

Если remote prerequisites отсутствуют, task должен вернуть blocker artifact, а
не запускаться локально.

## Rollback и остановка

Остановить recovery и зафиксировать blocker, если:

- `/health` не `ok`, Redis не отвечает или spool растет;
- fresh heartbeat не появляется после bootstrap/restart window;
- node id после bootstrap отличается от `server-kfrm`;
- probe leased не тем node;
- probe ушел в `failed`, `dead_letter`, `cancelled` или висит дольше lease
  window без task heartbeat;
- journal показывает auth/secret issue, который нельзя раскрывать в owner
  channels;
- disk/RAM недостаточны для node-local artifacts.

Rollback path: вернуть предыдущую версию `kolibri-agent-host` штатным package /
git rollout способом, оставить node drained до successful read-only probe,
оформить blocker artifact и не подавать heavy tasks.

## Проверки этого документа

В рамках этой задачи выполнены только локальные read-only проверки репозитория:

```bash
git status --short
sed -n '1,260p' /Users/kolibri/.codex/skills/kolibri-factory-admin/SKILL.md
sed -n '1,260p' /Users/kolibri/.codex/skills/kolibri-factory-admin/references/runbook.md
rg -n "stale|fresh|heartbeat|agent_host|bootstrap|rollout|FormulaLM|LLM|server-kfrm|kfrm" .
rg --files docs ops tests | sort
sed -n '1,240p' docs/agent-work/server-kfrm-blocker-summary.md
sed -n '1,260p' docs/agent-work/server-kfrm-queue-watch.md
sed -n '1,260p' docs/agent-work/factory-runtime-rollout.md
sed -n '1,180p' docs/agent-work/server-capacity-sre-report.md
sed -n '130,180p' ops/factory_control.py
sed -n '680,735p' ops/factory_control.py
sed -n '1,260p' ops/agent_host.py
sed -n '1,260p' ops/bootstrap_factory_node.sh
sed -n '1,180p' ops/systemd/kolibri-agent-host.service
sed -n '1,180p' ops/systemd/kolibri-agent-host.env.example
```

Не выполнялись: SSH, live bootstrap, systemd restart, Control Plane mutations,
`submit`, `cancel`, `retry`, `drain`, direct Redis/spool edits, deploy, QA,
FormulaLM, LLM/model workloads.

## Связанные артефакты

- `docs/agent-work/server-kfrm-queue-watch.md`
- `docs/agent-work/server-kfrm-blocker-summary.md`
- `docs/agent-work/server-capacity-sre-report.md`
- `docs/agent-work/factory-runtime-rollout.md`
- `docs/agent-work/server-kfrm-app-run-plan.md`
- `ops/envelopes/KOL-SERVER-KFRM-PROBE-20260629.json`
- `ops/envelopes/KOL-FORMULALM-REMOTE-BENCH-6H-20260629.json`
- `ops/bootstrap_factory_node.sh`
- `ops/agent_host.py`
- `ops/systemd/kolibri-agent-host.service`
