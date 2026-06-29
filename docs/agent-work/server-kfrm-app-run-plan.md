# План запуска Kolibri на server-kfrm

Дата: 2026-06-29
Роль: `Инженер запуска на server-kfrm`
Scope: подготовить runbook запуска приложения Kolibri на самом мощном
factory-сервере `server-kfrm` после read-only probe. В рамках подготовки не
выполнялись SSH, запуск моделей, dispatch/lease/drain/cancel/retry и другие
мутации Control Plane.

## Короткий вывод

`server-kfrm` - правильная цель для тяжелого запуска приложения, build, product
QA и будущих FormulaLM workloads, но только после P0 gate:
`KOL-SERVER-KFRM-PROBE-20260629` должен быть leased именно `server-kfrm` и
завершиться через node-local artifacts. Пока probe не completed и heartbeat не
fresh, запуск приложения на `server-kfrm` запрещен.

Текущий код также не дает безопасно запустить полноценный app smoke без
дополнительного решения: `generic_implementation` вызывает `codex` или `mimo`
до `verification_commands`, то есть запускает модельный runner, а отдельного
non-model task kind для app smoke сейчас нет. Для no-model запуска нужен
небольшой Agent Host contract, например `app_smoke`, либо явное разрешение
оператора на `generic_implementation`.

## Источники

- `docs/agent-work/ubuntu-qa-runner-report.md` - снимок Control Plane на
  2026-06-29 07:33 MSK.
- `docs/agent-work/server-capacity-sre-report.md` - capacity/SRE вывод по
  `server-kfrm`, `main`, `new`, `highload` и drained/stale nodes.
- `ops/envelopes/KOL-SERVER-KFRM-PROBE-20260629.json` - P0 read-only probe:
  `target_node=server-kfrm`, `required_capability=read_only_probe`.
- `docs/quickstart.md` и `docs/deployment.md` - команды запуска backend,
  frontend и production checklist.
- `ops/agent_host.py` и `ops/kolibri-dispatch` - фактические runner/dispatcher
  контракты.

## Read-only gate перед запуском

Эти команды читает операторская/control surface. Они не должны брать lease,
отменять задачи, менять drain или запускать workload.

```bash
export KOLIBRI_FACTORY_CONTROL_URL="http://10.99.0.2:9101"

curl -fsS "$KOLIBRI_FACTORY_CONTROL_URL/health"
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" nodes
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" \
  status KOL-SERVER-KFRM-PROBE-20260629 --full
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" \
  collect KOL-SERVER-KFRM-PROBE-20260629
curl -fsS "$KOLIBRI_FACTORY_CONTROL_URL/v1/filesystem"
curl -fsS "$KOLIBRI_FACTORY_CONTROL_URL/v1/agent-messages?target=all&limit=30"
```

Не использовать широкий `GET /v1/tasks` как обязательный gate: по предыдущим
снимкам compact/summary может возвращать большой payload или timeout. Для P0
использовать targeted `GET /v1/tasks/<task_id>` через `status`.

## Readiness criteria

`server-kfrm` считается готовым для app-run только если все условия ниже
одновременно выполнены:

- Control Plane `/health` отвечает `status=ok`, Redis отвечает, `spool_count=0`
  или зафиксирован понятный non-blocking backlog.
- Node card для `server-kfrm`: `health=online`, `fresh=true`,
  `draining=false`, heartbeat age в пределах текущего threshold
  `FACTORY_NODE_STALE_AFTER` или операционного лимита 120 секунд.
- Capabilities включают `read_only_probe` и `generic_implementation`; для
  автономной работы есть `permission_pack=full_autonomy` или эквивалентные
  permissions.
- Нет stale `active_task`; если active task terminal, он не считается busy и
  должен быть очищен штатным heartbeat/Agent Host путем до нового lease.
- `/v1/filesystem` показывает namespace `/kolibri/nodes/server-kfrm` с
  node-local `worktrees` и `artifacts`. Control Plane хранит manifest/result
  references, но не читает node-local файлы.
- `KOL-SERVER-KFRM-PROBE-20260629` имеет state `completed`, был leased
  `server-kfrm`, result содержит `kind=read_only_probe`, `status=completed`,
  `result_path`/`result_reference` под node-local artifacts.
- Probe acceptance подтвержден: без SSH, без секретов, без shared writable root.
- Ubuntu/runtime preflight внутри lease доказывает Linux, Python 3.11+, Node.js
  20+, npm, git, достаточно RAM/disk для `npm ci`, build, backend venv и
  browser artifacts.
- Для полноценного backend+SPA smoke подготовлен app staging path. В текущем
  коде backend hardcodes `/opt/kolibri-ai/data/kolibri.db`, а SPA static path -
  `/opt/kolibri-ai/frontend/dist`; если эти пути недоступны пользователю
  Agent Host, task должен вернуть blocker artifact.

## Порядок запуска после probe

1. Зафиксировать targeted status probe и node readiness через read-only команды
   выше.
2. Проверить, что `KOL-PRODUCT-QA-E2E-20260629` и другие live queued tasks не
   дублируются. Не submit повторно уже live envelopes.
3. Если разрешен model-backed `generic_implementation`, создать отдельный
   app-run envelope на `server-kfrm` с `target_node=server-kfrm`,
   `required_capability=generic_implementation`, коротким goal и явными
   `verification_commands`.
4. Если model runner не разрешен, сначала внедрить отдельный non-model task kind
   для app smoke. Минимальное имя контракта: `app_smoke`. Он должен clone/fetch
   repo, выполнить shell preflight/build/run commands, записать result artifact
   и завершиться без `codex`/`mimo`.
5. Запускать приложение только на loopback (`127.0.0.1`) внутри
   `server-kfrm` lease. Не открывать публичные порты, не менять nginx/systemd,
   не трогать production `main` без отдельного deploy решения.
6. После green app smoke дать priority P0 product QA envelope, затем UI/build
   work. FormulaLM 6h benchmark остается последним и не конкурирует с release
   QA.

## Команды только для удаленной Ubuntu-ноды

Следующий блок не запускать на Mac/control surface. Он должен исполняться
только внутри Control Plane lease на `server-kfrm`, в node-local worktree и с
логами/result artifact.

Preflight:

```bash
set -euxo pipefail

test "$(uname -s)" = "Linux"
uname -a
hostname
id
pwd
git rev-parse --show-toplevel
git rev-parse HEAD
python3 --version
node --version
npm --version
df -h .
free -h || true
```

Build and tests:

```bash
set -euxo pipefail

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt

npm --prefix frontend ci
npm --prefix frontend run lint --if-present
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout --if-present

python3 -m compileall -q backend ops tests
python -m pytest -q \
  backend/tests \
  tests/test_factory_status.py \
  tests/test_factory_runtime_contracts.py \
  tests/test_factory_runtime_queue_contracts.py \
  tests/test_factory_agent_messages.py \
  tests/test_mesh_control_bridge.py
```

Local app smoke on `server-kfrm`, only after staging path readiness is confirmed:

```bash
set -euxo pipefail

install -d /opt/kolibri-ai/data /opt/kolibri-ai/frontend
test -w /opt/kolibri-ai/data
rm -rf /opt/kolibri-ai/frontend/dist
cp -a frontend/dist /opt/kolibri-ai/frontend/dist

. .venv/bin/activate
(cd backend && python -m uvicorn main:app --host 127.0.0.1 --port 8000) \
  > /tmp/kolibri-backend.log 2>&1 &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT

for i in $(seq 1 30); do
  curl -fsS http://127.0.0.1:8000/api/health && break
  sleep 1
done

curl -fsS http://127.0.0.1:8000/api/providers
curl -fsS http://127.0.0.1:8000/
curl -fsS http://127.0.0.1:8000/app
```

Browser evidence, если Playwright доступен на runner:

```bash
npm --prefix frontend run preview -- --host 127.0.0.1 --port 4173 \
  > /tmp/kolibri-frontend-preview.log 2>&1 &
FRONTEND_PID=$!
trap 'kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true' EXIT

for i in $(seq 1 30); do
  curl -fsS http://127.0.0.1:4173 && break
  sleep 1
done

npx --yes playwright install chromium
npx --yes playwright screenshot --viewport-size=1440,1000 \
  http://127.0.0.1:4173/app /tmp/kolibri-server-kfrm-desktop.png
npx --yes playwright screenshot --viewport-size=390,844 \
  http://127.0.0.1:4173/app /tmp/kolibri-server-kfrm-mobile.png
```

## Запрещенные команды и пути

- Любой `ssh server-kfrm`, `scp`, ручной `systemctl`, ручной `nginx`, прямой
  запуск через терминал на сервере.
- Legacy mode `ops/kolibri-dispatch` с option-based SSH arguments. Использовать
  только subcommands `nodes`, `status`, `collect`, `submit` после явного
  решения оператора.
- `./scripts/deploy.sh main` как часть этого runbook: скрипт использует
  SSH/SCP и мутирует production `main`.
- `cancel`, `retry`, `delete`, `drain`, `un-drain`, lease surgery и повторный
  submit live tasks без отдельного operator decision.
- Запуск FormulaLM, Qwen, load tests или долгих model workloads до green
  app-run и product QA.
- Публикация secrets, auth files, локальных путей или полных логов в
  owner-facing channels.

## Допустимые fallback на main

`main` допустим только как малый fresh implementation fallback, не как замена
`server-kfrm` для тяжелого запуска.

Разрешено после operator decision:

- read-only status и public smoke: `curl http://104.253.43.117`,
  `curl http://104.253.43.117/api/providers`, targeted Control Plane reads;
- P0 app/domain diagnosis через уже подготовленный маршрут
  `KOL-P0-APP-QUEUE-UNBLOCK-20260629`, если stale owner task считается
  superseded и задача не live duplicate;
- маленькие repo checks, compile/unit tests и минимальный patch с review на
  `new`, если `main` fresh, non-draining и advertises `implementation`.

Не разрешено на `main` как fallback:

- full product QA, browser matrix, heavy `npm ci`/build loops при нехватке RAM,
  FormulaLM, model benchmarks;
- public deploy/nginx/systemd changes без отдельного deploy gate;
- подмена `server-kfrm` для задач с `required_capability=generic_implementation`
  или target `server-kfrm`.

## Текущие blockers

- По последнему локальному отчету `server-kfrm` stale:
  heartbeat `2026-06-28T20:17:15Z`; fresh heartbeat еще не подтвержден.
- `KOL-SERVER-KFRM-PROBE-20260629` в снимке был queued, не completed; нет
  доказательства lease/result artifact от `server-kfrm`.
- На момент снимка нет fresh non-draining `generic_implementation` runner; P0
  product QA и UI/build tasks могут оставаться queued.
- Broad `/v1/tasks?summary=1&compact=1` ненадежен для operator UX: payload
  может быть большим или timeout, state filters не считать authoritative.
- В текущем `ops/agent_host.py` нет no-model `app_smoke` runner;
  `generic_implementation` запускает `codex` или `mimo`.
- Backend hardcodes `/opt/kolibri-ai/data/kolibri.db`, а frontend static path -
  `/opt/kolibri-ai/frontend/dist`; node-local app smoke требует подготовленного
  writable staging path или патча на env-configurable paths.
- `scripts/deploy.sh` и docs/deployment production commands используют SSH/SCP;
  они не подходят для этого remote-first runbook.
- `primary-candidate` stale/dead-letter context, `qjns` и `uiap` draining; их
  нельзя использовать как скрытый fallback.

## Acceptance для будущего app-run task

App-run task можно считать green, если artifact содержит:

- node id `server-kfrm`, fresh heartbeat timestamp, commit SHA и worktree path;
- результаты preflight Linux/Python/Node/npm/git/disk/RAM;
- `npm --prefix frontend run build` и focused backend/factory tests;
- backend smoke `GET /api/health`, `GET /api/providers`;
- SPA smoke `/` и `/app` через loopback;
- screenshots или явный blocker, если Playwright unavailable;
- список открытых blockers и решение GO / NO-GO / GO WITH EXCEPTION;
- подтверждение: no SSH, no public deploy, no secrets, no model workload unless
  the envelope explicitly allowed model-backed `generic_implementation`.

## Проверки подготовки этого документа

- Прочитаны factory runbook, `docs/factory.md`, `docs/quickstart.md`,
  `docs/deployment.md`, `docs/agent-work/ubuntu-qa-runner-report.md`,
  `docs/agent-work/server-capacity-sre-report.md`.
- Прочитаны `ops/envelopes/KOL-SERVER-KFRM-PROBE-20260629.json`,
  `ops/agent_host.py`, `ops/kolibri-dispatch`,
  `ops/systemd/kolibri-agent-host.env.example`.
- Проверено, что `docs/agent-work/server-kfrm-app-run-plan.md` не существовал
  до создания.
- Не выполнялись SSH, model workloads, `ops/kolibri-dispatch submit`,
  Control Plane mutations или запуск приложения.
