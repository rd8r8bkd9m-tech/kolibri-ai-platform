# Server-kfrm rollout envelope plan

Дата: 2026-06-29  
Роль: `Планировщик rollout server-kfrm`  
Scope: подготовить конкретный Control Plane envelope и безопасный rollout-план
для восстановления `server-kfrm` на основе
`docs/agent-work/server-kfrm-runtime-recovery.md`.

В рамках подготовки этого файла live серверы, Control Plane state, очередь,
leases, drain-флаги, SSH, systemd, deploy, FormulaLM и LLM/model workloads не
трогались.

## Короткий вывод

`server-kfrm` нельзя восстанавливать тяжелой задачей или FormulaLM benchmark.
Безопасный порядок:

1. Снять targeted read-only snapshot Control Plane.
2. Проверить idempotency: не дублировать `KOL-SERVER-KFRM-PROBE-20260629`, если
   она уже live queued/running/completed.
3. Зафиксировать operator decision на controlled runtime recovery window.
4. Восстановить штатный Agent Host через golden bootstrap/rollout path.
5. Дождаться fresh heartbeat именно `server-kfrm`.
6. Дать пройти или подать read-only probe только после idempotency gate.
7. Вернуть узел в рабочий пул только после completed probe с node-local
   artifact.

Важное ограничение: stale `server-kfrm` не может выполнить targeted
Control Plane task на себя, пока Agent Host не восстановит heartbeat и lease
loop. Поэтому Control Plane envelope ниже является orchestration/runbook
envelope для SRE-исполнителя и операторского rollout, а не heavy workload на
`server-kfrm`.

## Предусловия

- Control Plane `/health` отвечает `status=ok`, Redis отвечает, `spool_count`
  не растет.
- Executor card `server-kfrm` существует отдельно от `mesh-server-kfrm`.
- `KOL-SERVER-KFRM-PROBE-20260629` не дублируется и имеет понятный targeted
  state.
- Нет operator approval на FormulaLM/LLM; любые model workloads запрещены.
- Любые live mutations выполняются только после отдельного operator decision:
  `submit`, `drain`, `un-drain`, bootstrap/restart, cancel/retry/requeue.

## Envelope

Envelope материализован в
`ops/envelopes/KOL-SERVER-KFRM-RUNTIME-RECOVERY-20260629.json`. Не submit без
отдельного operator decision.

```json
{
  "task_id": "KOL-SERVER-KFRM-RUNTIME-RECOVERY-20260629",
  "idempotency_key": "server-kfrm:runtime-recovery-rollout:2026-06-29",
  "kind": "generic_implementation",
  "required_capability": "generic_implementation",
  "permission_pack": "full_autonomy",
  "runner": "codex",
  "role_slot": "factory_sre",
  "role_goal": "coordinate a safe Control Plane rollout to recover server-kfrm Agent Host without heavy workloads",
  "goal": "Using docs/agent-work/server-kfrm-runtime-recovery.md and docs/agent-work/server-kfrm-rollout-envelope-plan.md, coordinate the server-kfrm recovery gates. Start with read-only Control Plane snapshot, verify idempotency for KOL-SERVER-KFRM-PROBE-20260629, prepare the exact operator actions for Agent Host bootstrap/rollout, and stop before any live mutation unless explicit operator approval is present in the task context. Do not run FormulaLM, LLM benchmarks, app QA, deploy scripts, SSH product paths, cancel/retry/requeue, or queue surgery. Return a concise status artifact with current gate, blockers, and the next safe operator decision.",
  "acceptance": [
    "Read-only snapshot covers /health, nodes, targeted status for KOL-SERVER-KFRM-PROBE-20260629, targeted collect when terminal/running, and /v1/filesystem when available",
    "Report distinguishes executor server-kfrm from mesh-server-kfrm",
    "Report includes heartbeat_at, heartbeat_age_seconds, fresh, health, draining, active_task, active_task_state, capabilities, lease_owner, lease_until, result_reference, and spool/Redis health",
    "No duplicate submit is performed for KOL-SERVER-KFRM-PROBE-20260629 if the task already exists in queued, leased, running, completed, failed, cancelled, or dead_letter state",
    "No SSH, SCP, direct Redis/spool edits, deploy script, FormulaLM, LLM benchmark, app QA, cancel, retry, drain, un-drain, or bootstrap/restart is performed without explicit operator approval",
    "If server-kfrm is stale, the result states that Control Plane cannot self-heal that node through a targeted lease until Agent Host heartbeat is restored",
    "If operator approval is absent, task exits with blocker artifact and exact next safe decision request",
    "If operator approval is present and recovery is executed, success is claimed only after fresh heartbeat and completed read-only probe leased by server-kfrm with node-local artifact",
    "Result payload contains no secrets, auth files, raw private logs, or owner-facing local artifact paths beyond approved Control Plane references"
  ],
  "verification_commands": [
    "python3 -m json.tool ops/envelopes/KOL-SERVER-KFRM-PROBE-20260629.json >/dev/null",
    "python3 -m compileall -q ops/agent_host.py ops/factory_control.py"
  ],
  "max_retries": 1,
  "create_review_on_complete": true,
  "review_node": "new",
  "source": {
    "kind": "manual_control_plane",
    "requested_by": "server-kfrm-rollout-planner",
    "requested_at": "2026-06-29T00:00:00+03:00",
    "repo": "kolibri-ai-platform",
    "source_docs": [
      "docs/agent-work/server-kfrm-runtime-recovery.md",
      "docs/agent-work/server-kfrm-rollout-envelope-plan.md"
    ]
  }
}
```

## Submission gate

Перед submit оператор должен выполнить только read-only проверки:

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

Submit recovery-orchestration envelope допустим только если:

- `/health` зеленый;
- есть свежий executor, который может взять `generic_implementation` SRE-задачу;
- текущий probe status понятен и не требует duplicate submit;
- оператор явно разрешил orchestration task;
- цель задачи остается recovery gates, а не heavy workload.

Команда будущего submit, не выполненная в рамках этого документа:

```bash
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" \
  submit --file ops/envelopes/KOL-SERVER-KFRM-RUNTIME-RECOVERY-20260629.json
```

## Rollout sequence

### 0. Snapshot

Снять состояние Control Plane и зафиксировать:

- `/health`: `status`, `queue_backend`, Redis, `spool_count`,
  `spool_replayed`;
- node card `server-kfrm`: `fresh`, `health`, `heartbeat_at`,
  `heartbeat_age_seconds`, `draining`, `active_task`,
  `active_task_state`, capabilities, CPU/RAM/disk;
- node card `mesh-server-kfrm`: только как mesh-shadow, не executor evidence;
- targeted task `KOL-SERVER-KFRM-PROBE-20260629`: state, attempt,
  lease owner, lease until, task heartbeat, result/result_reference.

Stop conditions:

- `/health` не `ok`;
- Redis не отвечает или spool растет;
- targeted task не читается;
- обнаружен duplicate probe с тем же смыслом, но другим task id.

### 1. Drain decision

Если оператор планирует bootstrap/restart, безопаснее держать
`server-kfrm` drained во время recovery window, чтобы узел не получил heavy
lease сразу после fresh heartbeat.

Не выполнять автоматически. Будущая команда только после operator decision:

```bash
curl -fsS -X POST "$KOLIBRI_FACTORY_CONTROL_URL/v1/nodes/server-kfrm/drain" \
  -H 'content-type: application/json' \
  -d '{"drain": true}'
```

Если `server-kfrm` уже stale, drain сам по себе не чинит heartbeat. Это только
защитный флаг перед возвратом узла в пул.

### 2. Runtime recovery window

Восстановление Agent Host должно вернуть штатный контракт:

- register: `POST /v1/nodes/register`;
- heartbeat: `POST /v1/nodes/server-kfrm/heartbeat`;
- lease loop через `/v1/tasks/lease`;
- node-local worktrees/artifacts;
- no shared writable root.

Golden bootstrap параметры из recovery runbook:

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

Этот блок не запускать на Mac/control surface. Он допустим только в
operator-approved recovery window на целевой Linux-нode или через утвержденный
deployment channel. В рамках текущей задачи он не выполнялся.

### 3. Fresh heartbeat gate

После bootstrap/restart ждать:

- `server-kfrm.fresh=true`;
- `health=online`;
- `heartbeat_age_seconds <= FACTORY_NODE_STALE_AFTER` или <= 120 секунд при
  default;
- `node_id=server-kfrm`, не новый/ошибочный id;
- capabilities содержат `read_only_probe` и `generic_implementation`;
- `active_task=null` или текущий expected lease.

Если heartbeat не появляется в течение recovery window, оставить node drained,
оформить blocker artifact и не подавать heavy tasks.

### 4. Probe gate

Если `KOL-SERVER-KFRM-PROBE-20260629` уже существует, не submit повторно.
Ждать, пока fresh `server-kfrm` возьмет существующую queued probe.

Если targeted probe отсутствует вообще, отдельное operator decision может
создать его из существующего файла:

```bash
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" \
  submit --file ops/envelopes/KOL-SERVER-KFRM-PROBE-20260629.json
```

Probe success criteria:

- state `completed`;
- `lease_owner` содержит `server-kfrm`;
- result подтверждает `kind=read_only_probe`;
- `result_reference` или artifact path относится к
  `/kolibri/nodes/server-kfrm/...`;
- result не содержит secrets, raw auth, приватные логи или shared-root paths.

### 5. Return-to-pool decision

Только после successful probe оператор может снять drain:

```bash
curl -fsS -X POST "$KOLIBRI_FACTORY_CONTROL_URL/v1/nodes/server-kfrm/drain" \
  -H 'content-type: application/json' \
  -d '{"drain": false}'
```

После этого `server-kfrm` можно использовать для `generic_implementation` и
release QA согласно отдельным app-run/QA envelopes. FormulaLM остается
запрещен до отдельного remote-only preflight и отсутствия P0 release QA
нагрузки.

## Rollback

Остановить rollout и оставить node drained, если:

- fresh heartbeat не появился после bootstrap/restart window;
- node id отличается от `server-kfrm`;
- probe leased другим node;
- probe стал `failed`, `cancelled`, `dead_letter` или завис дольше lease
  window без heartbeat;
- `/health` деградировал, Redis недоступен или spool растет;
- journal/status указывает на auth/secret issue, который нельзя раскрывать;
- disk/RAM недостаточны для node-local artifacts.

Rollback result должен быть blocker artifact с:

- последним safe snapshot time;
- текущим gate;
- sanitized error category;
- next operator decision;
- явным подтверждением, что app QA, FormulaLM и LLM workloads не запускались.

## Forbidden actions

- SSH/SCP как product control path.
- `ops/kolibri-dispatch doctor` для этого recovery, потому что он может
  запускать SSH-проверки.
- Duplicate submit `KOL-SERVER-KFRM-PROBE-20260629`.
- `cancel`, `retry`, `requeue`, direct Redis/spool edits, lease surgery.
- `drain`/`un-drain` без отдельного operator decision.
- `./scripts/deploy.sh main` или другие production deploy scripts.
- FormulaLM, Qwen, Ollama, llama.cpp, vLLM, local Mac benchmark, app QA,
  browser matrix или heavy build до fresh heartbeat и completed probe.

## Validation of this plan

Локально проверены только файлы и синтаксис документационного пакета:

```bash
git status --short
sed -n '1,260p' docs/agent-work/server-kfrm-runtime-recovery.md
sed -n '1,220p' ops/envelopes/KOL-SERVER-KFRM-PROBE-20260629.json
sed -n '1,220p' ops/envelopes/KOL-CODEX-CLI-ROLLOUT-20260629.json
sed -n '280,360p' ops/factory_control.py
sed -n '740,780p' ops/factory_control.py
```

Не выполнялись: SSH, live bootstrap, systemd restart, Control Plane mutations,
`submit`, `cancel`, `retry`, `drain`, direct Redis/spool edits, deploy, QA,
FormulaLM, LLM/model workloads.
