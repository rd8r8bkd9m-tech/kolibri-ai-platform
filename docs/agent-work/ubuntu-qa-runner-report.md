# Ubuntu QA runner report

Дата: 2026-06-29 07:33 MSK  
Роль: `ubuntu_qa_runner_coordinator`  
Scope: подготовить план запуска build/test/product QA на Ubuntu factory nodes
через Control Plane. Долгие тесты, cancel/retry/delete/drain не запускались.

## Executive summary

- Control Plane `http://10.99.0.2:9101` жив: `GET /health` вернул
  `status=ok`, `redis=PONG`, `spool_count=0` на
  `2026-06-29T04:32:07Z`.
- Для доступности runner нельзя полагаться только на поле `health=online`:
  часть нод имеет heartbeat старше 4-8 часов. Ниже freshness посчитан вручную
  от времени `/health`.
- Control Plane не отдает `os_release`; Ubuntu/Linux нужно подтверждать внутри
  lease через `uname -a` и `test "$(uname -s)" != "Darwin"`.
- Свежие non-draining Ubuntu/control runners сейчас:
  `home` (`read_only_probe`, coordinator), `main` (`implementation`, `review`,
  `read_only_probe`) и `new` (`review`, `generic_review`, `read_only_probe`).
- Свежий QA-capable runner `qjns` есть, но `draining=true`, мало RAM и около
  6 GB свободного диска. Я его не трогал.
- Свежего non-draining runner с `generic_implementation` на момент снимка нет.
  Поэтому уже созданные live задачи `KOL-PRODUCT-QA-E2E-20260629` и
  `KOL-PREMIUM-LANDING-UI-20260629` остаются queued и, вероятно, ждут оживления
  `server-kfrm`/`highload`/`agent-*` или обновления профиля fresh runner.
- `server-kfrm` подходит по размеру для тяжелого Ubuntu bench/QA, но heartbeat
  старый (`2026-06-28T20:17:15Z`). Сначала нужен короткий probe, уже созданный
  как `KOL-SERVER-KFRM-PROBE-20260629`.

## Live Control Plane reads

Read-only команды, которые были выполнены:

```bash
curl -fsS --max-time 10 http://10.99.0.2:9101/health
curl -fsS --max-time 15 http://10.99.0.2:9101/v1/nodes
curl -fsS --max-time 15 http://10.99.0.2:9101/v1/filesystem
curl -fsS --max-time 20 'http://10.99.0.2:9101/v1/tasks?summary=1&compact=1&limit=300'
```

Notes:

- `/v1/tasks?summary=1&compact=1&limit=300` timed out after 20 seconds with no
  bytes.
- A narrower `/v1/tasks?summary=1&compact=1&limit=20` returned a very large full
  payload, so for operations prefer targeted `GET /v1/tasks/<task_id>`.
- `/v1/filesystem` confirms the unified namespace pattern
  `/kolibri/nodes/<node_id>` with node-local `worktrees` and `artifacts`.

## Runner availability

Freshness threshold for "available now": heartbeat age <= 120 seconds,
`draining=false`, and enough disk for build/test artifacts.
OS is inferred from the Agent Host/runtime profile and must be proven by the
task preflight before claiming Ubuntu QA evidence.

| Node | Hostname | Fresh | Draining | CPU/RAM/Disk | Capabilities | Use now |
| --- | --- | --- | --- | --- | --- | --- |
| `home` | `plastilin` | yes | false | 6 CPU, 12.5 GB avail RAM, 23.2 GB free | `coordinator`, `orchestrator`, `read_only_probe` | Control/read-only preflight only |
| `main` | `kolibri-main-api` | yes | false | 1 CPU, 768 MB avail RAM, 9.7 GB free | `implementation`, `review`, `read_only_probe` | Small targeted implementation/review, not full product QA |
| `new` | `kolibri-worker-backup` | yes | false | 2 CPU, 5.8 GB avail RAM, 51.4 GB free | `review`, `generic_review`, `read_only_probe` | Review/read-only QA, not `generic_implementation` |
| `qjns` | `kolibri-tools-executor` | yes | true | 1 CPU, 0.7 GB avail RAM, 6.0 GB free | `implementation`, `review`, `qa` | Do not schedule while drained |
| `uiap` | `kolibri-rag-knowledge` | yes | true | 2 CPU, low RAM, 0 GB free | `research`, `security`, `rag` | Do not schedule |
| `server-kfrm` | `server-kfrm` | no | false | 8 CPU, 27 GB avail RAM, 150 GB free | `generic_implementation`, `read_only_probe` | Best target after heartbeat recovers |
| `highload` | `kolibri-ci-build-highload` | no | false | 1 CPU, 3.3 GB avail RAM, 23.3 GB free | `generic_implementation`, `read_only_probe` | Stale; recover before use |
| `primary-candidate` | `kolibri` | no | false | 8 CPU, 10.8 GB avail RAM, 80 GB free | `generic_implementation`, `review` | Stale/active dead-letter context; avoid for QA |

Mesh shadow nodes such as `mesh-server-kfrm` are not QA runners; they expose mesh
presence only and have no node-local worktree/artifact roots.

## QA/test envelopes

Live task status checked by `GET /v1/tasks/<task_id>`.

| Envelope | Live status | Target | Capability | Priority | Notes |
| --- | --- | --- | --- | --- | --- |
| `KOL-SERVER-KFRM-PROBE-20260629` | queued | `server-kfrm` | `read_only_probe` | P0 | First gate before any 6h or heavy Ubuntu work |
| `KOL-PRODUCT-QA-E2E-20260629` | queued | any | `generic_implementation` | P0 | Main product QA envelope; already submitted, do not resubmit |
| `KOL-PREMIUM-LANDING-UI-20260629` | queued | any | `generic_implementation` | P1 | Build/UI implementation before final QA |
| `KOL-DESKTOP-CONTROL-APP-MVP-20260629` | not live | any | `generic_implementation` | P1 | Ubuntu desktop/product QA candidate; submit only after runner capacity is fresh |
| `KOL-CODEX-CLI-ROLLOUT-20260629` | not live | any | `generic_implementation` | P1 | Runtime readiness task, useful before broad QA rollout |
| `KOL-FORMULALM-REMOTE-BENCH-6H-20260629` | not live | `server-kfrm` | `generic_implementation` | P2 | Long remote-only benchmark; submit last |
| `KOL-FORMULALM-RD-20260629` | not live | any | `generic_implementation` | P2 | Research/report, not product release QA |
| `KOL-META-MIMO-ORCHESTRATOR-20260629` | queued | `server-kfrm` | `generic_implementation` | hold | Competes with server-kfrm capacity |
| `KOL-META-MIMO-ORCHESTRATOR-PRIMARY-20260629` | dead_letter | `primary-candidate` | `generic_implementation` | hold | `lease_expired`; do not retry from this role |

Other live queued implementation envelopes (`KOL-DOCS-STEWARD`,
`KOL-GITHUB-PROJECT-OPS`, `KOL-LIVING-BIRD-RD`, `KOL-SUBAGENT-POOL-SUPERVISOR`)
also need `generic_implementation` and may compete with QA runner capacity.

## Recommended dispatch order

1. P0: wait for or recover `server-kfrm`, then let
   `KOL-SERVER-KFRM-PROBE-20260629` lease/complete. This proves large Ubuntu
   runner path without starting a long test.
2. P0: run `KOL-PRODUCT-QA-E2E-20260629` after at least one fresh non-draining
   `generic_implementation` Ubuntu runner exists.
3. P1: run/finish `KOL-PREMIUM-LANDING-UI-20260629`, then rerun product QA if
   it changes release-facing UI.
4. P1: submit `KOL-CODEX-CLI-ROLLOUT-20260629` only if runners need CLI/auth
   normalization before more work.
5. P1: submit `KOL-DESKTOP-CONTROL-APP-MVP-20260629` after product QA capacity
   is stable.
6. P2: submit `KOL-FORMULALM-REMOTE-BENCH-6H-20260629` only after the probe
   passes and no release QA is waiting for `server-kfrm`.

## Operator commands

Use these from the control surface. They are safe read-only unless marked
`submit`.

```bash
export KOLIBRI_FACTORY_CONTROL_URL="http://10.99.0.2:9101"

# Read-only health and runner preflight.
curl -fsS "$KOLIBRI_FACTORY_CONTROL_URL/health"
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" nodes
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" status KOL-SERVER-KFRM-PROBE-20260629 --full
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" status KOL-PRODUCT-QA-E2E-20260629 --full

# Watch recent agent feed without touching leases.
curl -fsS "$KOLIBRI_FACTORY_CONTROL_URL/v1/agent-messages?target=all&limit=30"
```

Submit commands, only after confirming the task is not already live:

```bash
export KOLIBRI_FACTORY_CONTROL_URL="http://10.99.0.2:9101"

# Already live on 2026-06-29 07:33 MSK; do not resubmit unless task was removed by operator policy.
# ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" submit --file ops/envelopes/KOL-PRODUCT-QA-E2E-20260629.json

# Submit if runner runtime needs Codex normalization.
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" submit --file ops/envelopes/KOL-CODEX-CLI-ROLLOUT-20260629.json

# Submit after product QA runner capacity is stable.
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" submit --file ops/envelopes/KOL-DESKTOP-CONTROL-APP-MVP-20260629.json

# Submit last; this is a long remote-only benchmark.
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" submit --file ops/envelopes/KOL-FORMULALM-REMOTE-BENCH-6H-20260629.json
```

## Commands expected inside Ubuntu QA lease

These commands are for the Ubuntu factory task result, not for the Mac control
machine:

```bash
set -euxo pipefail

uname -a
test "$(uname -s)" != "Darwin"
python3 --version
node --version || true
npm --version || true
git rev-parse --show-toplevel
git rev-parse HEAD

npm --prefix frontend ci
npm --prefix frontend run lint --if-present
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout --if-present

python3 -m compileall -q backend ops tests
python3 -m pytest backend/tests tests
```

Focused release gates if full pytest is too slow for a first Ubuntu pass:

```bash
python3 -m pytest -q \
  backend/tests/test_billing.py \
  backend/tests/test_estimate_document_pdf_engines.py \
  tests/test_factory_status.py \
  tests/test_factory_runtime_contracts.py \
  tests/test_factory_runtime_queue_contracts.py \
  tests/test_factory_agent_messages.py \
  tests/test_mesh_control_bridge.py
```

Browser/mobile evidence should run on Ubuntu after `npm --prefix frontend run
build`; if Playwright is available on the runner:

```bash
npm --prefix frontend run preview -- --host 127.0.0.1 --port 4173
npx --yes playwright install chromium
npx --yes playwright screenshot --viewport-size=1440,1000 http://127.0.0.1:4173 /tmp/kolibri-desktop.png
npx --yes playwright screenshot --viewport-size=390,844 http://127.0.0.1:4173 /tmp/kolibri-mobile.png
```

## Blockers and decisions

- Do not run product QA on Mac. Mac can only read Control Plane and edit/report.
- Do not resubmit `KOL-PRODUCT-QA-E2E-20260629`; it is already live queued.
- Do not submit the 6h FormulaLM benchmark until `server-kfrm` heartbeat is
  fresh and the read-only probe has completed.
- Do not rely on broad `/v1/tasks` list for operator UX until compact summary is
  verified; use targeted task status to avoid huge payloads and owner-chat data.
- If the next owner action is urgent release QA, the practical blocker is
  runner capacity: no fresh non-draining `generic_implementation` node was
  visible in Control Plane at the snapshot time.
