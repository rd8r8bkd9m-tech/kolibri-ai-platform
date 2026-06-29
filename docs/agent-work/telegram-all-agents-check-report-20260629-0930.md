# Отчет после проверки всех агентов фабрики

Дата: 2026-06-29 09:30 MSK

## Краткий вывод

Фабрика уже не просто наблюдается: `home` доказал полный remote execution path
через Control Plane:

```text
Control Plane -> lease -> Agent Host home -> Git SSH clone -> Codex exec ->
artifact file -> checks -> commit -> push -> waiting_review
```

Но фабрика еще не работает на 80% мощности: из 35 node cards только 6 были
online/fresh в live-снимке, 29 stale, 3 draining. Очередь: 65 queued, active 0.

## Control Plane

- `/health`: `status=ok`
- Redis: `PONG`
- Queue backend: `redis`
- Очередь: 65 queued
- Active tasks в compact snapshot: 0

## Узлы и агенты

Live-снимок `/v1/nodes`:

- Всего node cards: 35
- Online/fresh: 6
- Stale: 29
- Draining: 3
- Non-draining online узлы:
  - `home` / `plastilin`
  - `main` / `kolibri-main-api`
  - `new` / `kolibri-worker-backup`
- Draining online узлы:
  - `home-live`
  - `qjns`
  - `uiap`

`home` теперь имеет:

- capabilities: `generic_implementation`, `implementation`,
  `remote_implementation_runner_ready`, `review`, `read_only_probe`
- permissions: `ai_runner`, `git_push`, `github_review`, `network`,
  `read_repo`, `run_tests`, `shell`, `spawn_subagents`, `write_artifacts`,
  `write_worktree`

## Проверенные задачи

### `home` read-only probe

- Task: `KOL-HOME-READONLY-RUNTIME-PROBE-20260629`
- State: `completed`
- Lease owner: `home:agent-host-home`
- Result reference:
  `/var/lib/kolibri-agent/artifacts/KOL-HOME-READONLY-RUNTIME-PROBE-20260629/KOL-HOME-READONLY-RUNTIME-PROBE-20260629-attempt-1/result.json`

### `home` generic implementation smoke

- Task: `KOL-HOME-GENERIC-RUNTIME-SMOKE-RERUN3-20260629`
- State: `waiting_review`
- Lease owner: `home:agent-host-home`
- Runner: `codex`
- Branch:
  `agent/KOL-HOME-GENERIC-RUNTIME-SMOKE-RERUN3-20260629/runtime-smoke`
- Remote branch commit:
  `63953f483f52461832ad803a2341c385ac89f590`
- Pushed branch confirmed by `git ls-remote`.
- Checks inside remote task:
  - `python3 -m compileall -q ops tests`: passed
  - `git diff --check`: passed
  - `git diff --cached --check`: passed
  - `codex login status >/dev/null 2>&1`: passed
  - `git ls-remote --exit-code origin HEAD >/dev/null`: passed

Important nuance: Control Plane result currently shows `changed_files=[]`,
`commit=null`, `pushed=false`, but the Codex runner response and direct remote
branch check prove the commit and push. This is a Control Plane result parsing
gap to fix next.

### `main` P0 app verify

- Task: `KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629`
- State: `waiting_review`
- Lease owner: `main:agent-host-main`
- Runner: `codex`
- Commit: `0e7dc0011063740375ce21153aa72abaca197c2b`
- Pushed: true
- Changed files:
  - `frontend/src/App.jsx`
  - `tests/test_factory_status.py`
  - `docs/agent-work/p0-app-queue-unblock-verify-result.md`

### Still queued / blocked

- `KOL-P0-APP-VERIFY-REVIEW-20260629`: still `queued`
- `KOL-SERVER-KFRM-HEARTBEAT-RECOVERY-20260629`: old failed attempt from before
  `home` runtime/auth was fixed
- `server-kfrm`: still stale

## Что было починено на `home`

1. Обновлен Agent Host runtime до версии с `generic_implementation` и
   `RUNTIME_KIND_COMPAT`.
2. Исправлены systemd capabilities: добавлены `generic_implementation`,
   `implementation`, `remote_implementation_runner_ready`, `review`.
3. Добавлен Git SSH deploy access; `git ls-remote` по SSH проходит.
4. Добавлен `KOLIBRI_REPO_URL=git@github.com:rd8r8bkd9m-tech/kolibri-ai-platform.git`.
5. Перенесен Codex auth/config; `codex exec` smoke вернул `CODEX_AUTH_OK`.
6. Добавлена instrumentation в Agent Host:
   - `task_leased`
   - `task_run_dispatch`
   - agent-messages теперь показывают lease/start/completion события.

## Почему это похоже на распределенную нейросистему

Узлы не общаются как люди в чате. Они передают структурированные события:

- `task_leased`
- `task_started`
- `task_completed`
- `task_failed`
- `result_reference`
- `branch`
- `commit`
- `checks`

Эти события идут через Control Plane и `/v1/agent-messages`, а артефакты лежат
на node-local путях. Это правильная форма общего brain: не разговор, а
структурированные сигналы, факты, результаты и ссылки на доказательства.

## Главные следующие P0

1. Fix Control Plane result parsing: извлекать commit/pushed/changed_files из
   Codex final text или требовать structured result file от runner.
2. Перезапустить/переотправить review task для P0 app verify, чтобы он был
   взят `home` или `main`.
3. Развернуть такой же Git/Codex/runtime parity на остальных fresh
   non-draining узлах.
4. Восстановить `server-kfrm` только после fresh heartbeat + read-only probe.
5. Снизить очередь старых несовместимых task kinds или добавить compatibility
   mapping для `product_implementation`, `runtime_repair`, `deep_research`.

## Итог

Проверка всех агентов выполнена. Один полноценный remote execution node (`home`)
доказан end-to-end. `main` также доказал P0 app verify. До 80% фабрики еще не
дошли: нужен пул минимум из 6 fresh non-draining implementation nodes с
одинаковым Git/Codex/runtime профилем.
