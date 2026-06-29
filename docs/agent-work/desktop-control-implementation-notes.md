# Desktop Control MVP implementation notes

Дата: 2026-06-29
Агент: Инженер desktop-control MVP

## Контекст

Изучены:

- `docs/desktop-control-app.md`
- `docs/agent-work/desktop-control-app-mvp.md`
- `ops/envelopes/KOL-DESKTOP-CONTROL-APP-MVP-20260629.json`
- текущие Control Plane routes в `ops/factory_control.py`
- текущий backend bridge в `backend/main.py` и `backend/factory_status.py`

В worktree уже есть параллельные изменения в frontend/PWA:

- `frontend/src/App.jsx`
- `frontend/src/App.css`
- `frontend/src/components/AppHeader.jsx`
- `frontend/src/components/chat/ChatComposer.jsx`
- `frontend/src/components/chat/ChatWorkspace.jsx`
- `frontend/src/components/control/ControlFab.jsx`
- `frontend/src/components/control/ControlPanel.jsx`
- `frontend/public/manifest.webmanifest`

Поэтому этот проход не меняет frontend runtime. Web/PWA остаётся главным
приоритетом, а desktop-control MVP фиксируется отдельными контрактами и
следующими diff steps.

## Safe patch в этом проходе

Добавлены отдельные contract files без подключения к runtime routes:

- `backend/desktop_control_contracts.py`
- `tests/test_desktop_control_contracts.py`

Контракты фиксируют:

- owner-facing Control Plane endpoint allowlist;
- worker-only endpoints, которые desktop app не должен вызывать;
- roadmap endpoints, которые можно показывать только как planned/degraded;
- placeholder backend facade routes для будущего `/api/desktop-control/*`;
- обязательные поля task envelope;
- предупреждение для `permission_pack=full_autonomy`;
- базовую redaction функцию для owner-facing summaries.

## Реализационный план

### M1: read-only desktop console

Цель: получить desktop/dev mode без destructive actions.

Будущие файлы:

- `frontend/src/features/desktopControl/controlPlaneClient.js`
- `frontend/src/features/desktopControl/contracts.js`
- `frontend/src/features/desktopControl/useFactorySnapshot.js`
- `frontend/src/features/desktopControl/staleCache.js`
- `frontend/src/features/desktopControl/redaction.js`
- `frontend/src/features/desktopControl/DesktopControlPanel.jsx`
- `frontend/src/features/desktopControl/TaskDetailPanel.jsx`
- `frontend/src/features/desktopControl/AgentFeedPanel.jsx`

Минимальные frontend integration points после стабилизации текущей UI-ветки:

- `frontend/src/components/control/ControlPanel.jsx`: добавить desktop-control tab/section.
- `frontend/src/components/control/ControlFab.jsx`: оставить существующий entry point, не менять UX.
- `frontend/src/components/chat/QuickActions.jsx`: добавить quick actions "статус фабрики", "blockers", "envelope".
- `frontend/src/components/chat/ChatWorkspace.jsx`: отображать command preview и stale/degraded ответы.

Control Plane calls:

- `GET /health` или `GET /v1/health`
- `GET /v1/nodes`
- `GET /v1/tasks?summary=1&compact=1`
- `GET /v1/tasks?state=<state>&limit=<n>`
- `GET /v1/tasks/<task_id>`
- `GET /v1/agent-messages?target=all&limit=<n>`

M1 не должен вызывать:

- `POST /v1/tasks/lease`
- `POST /v1/tasks/<task_id>/heartbeat`
- `POST /v1/tasks/<task_id>/complete`
- `POST /v1/tasks/<task_id>/fail`
- direct SSH или node-local filesystem reads

### M2: controlled actions

Будущие файлы:

- `frontend/src/features/desktopControl/EnvelopeBuilder.jsx`
- `frontend/src/features/desktopControl/ActionPreviewDialog.jsx`
- `frontend/src/features/desktopControl/confirmations.js`
- `frontend/src/features/desktopControl/auditTrail.js`

Actions:

- `POST /v1/tasks`
- `POST /v1/tasks/<task_id>/cancel`
- `POST /v1/tasks/<task_id>/annotate`
- `POST /v1/nodes/<node_id>/drain`
- `POST /v1/agent-messages`

Обязательные gates:

- JSON parse validation before submit.
- Required fields: `task_id`, `kind`, `goal`, `acceptance`, `source`.
- Explicit confirmation for submit/cancel/drain/undrain.
- Warning for `permission_pack=full_autonomy`.
- Draft envelopes stay local and are never auto-submitted after reconnect.

### M3: optional backend facade

Если desktop app не должен ходить напрямую в Control Plane, добавить отдельный
FastAPI router без смешивания с существующим `/api/factory/status`.

Будущие файлы:

- `backend/desktop_control.py`
- `backend/tests/test_desktop_control_api.py`

Future facade routes:

- `GET /api/desktop-control/health`
- `GET /api/desktop-control/nodes`
- `GET /api/desktop-control/tasks`
- `GET /api/desktop-control/tasks/{task_id}`
- `POST /api/desktop-control/tasks`
- `POST /api/desktop-control/tasks/{task_id}/cancel`
- `POST /api/desktop-control/tasks/{task_id}/annotate`
- `POST /api/desktop-control/nodes/{node_id}/drain`
- `GET /api/desktop-control/agent-messages`
- `POST /api/desktop-control/agent-messages`

Router registration point:

- `backend/main.py`: `app.include_router(desktop_control_router)`

Safety requirement before registration:

- pass-through client must use `KOLIBRI_FACTORY_CONTROL_URL`;
- no token values in logs;
- no fallback to SSH;
- return explicit `offline`, `control-plane-degraded`, `unauthorized`,
  `validation-error`, `not-found`, or `server-error` states.

### M4: desktop shell

Recommended runtime: Electron only if new dependencies are acceptable in the
implementation PR. Otherwise keep a documented dev shell first.

Future files if Electron is chosen:

- `frontend/desktop/main.cjs`
- `frontend/desktop/preload.cjs`
- `frontend/desktop/security.md`
- `frontend/package.json`: add `dev:desktop`, `build:desktop`, `package:linux`
- `frontend/vite.config.js`: preserve current web build and add desktop-safe base/env only if needed

Security baseline:

- renderer Node integration disabled;
- context bridge exposes only safe app metadata/settings APIs;
- Control Plane URL comes from `KOLIBRI_CONTROL_URL` or local encrypted profile;
- tokens stored in OS keychain/secret storage, never in source or logs.

### M5: GitHub / CI / Project

Future files:

- `frontend/src/features/desktopControl/githubLinks.js`
- `frontend/src/features/desktopControl/GitHubTrailPanel.jsx`
- `backend/desktop_github.py` only if server-side GitHub auth is chosen.

Behavior:

- show PR/issue URLs from task result payload;
- show CI conclusion if authenticated integration exists;
- otherwise show `Project sync: pending` with exact auth/scope blocker;
- never convert failed CI into success.

## API contract source of truth

Use `backend/desktop_control_contracts.py` as the local contract checklist.
The actual source of runtime truth remains `ops/factory_control.py`.

Current confirmed runtime endpoints in `ops/factory_control.py`:

- `GET /health`
- `GET /v1/health`
- `GET /v1/nodes`
- `POST /v1/nodes/<node_id>/drain`
- `GET /v1/tasks`
- `GET /v1/tasks?summary=1&compact=1`
- `GET /v1/tasks?state=<state>&limit=<n>`
- `GET /v1/tasks/<task_id>`
- `POST /v1/tasks`
- `POST /v1/tasks/<task_id>/cancel`
- `POST /v1/tasks/<task_id>/annotate`
- `GET /v1/agent-messages?target=all&limit=<n>`
- `POST /v1/agent-messages`

Worker-only runtime endpoints:

- `POST /v1/nodes/register`
- `POST /v1/nodes/<node_id>/heartbeat`
- `POST /v1/tasks/lease`
- `POST /v1/tasks/<task_id>/heartbeat`
- `POST /v1/tasks/<task_id>/complete`
- `POST /v1/tasks/<task_id>/fail`

## Verification plan for implementation PR

Required automated checks:

```bash
npm --prefix frontend run lint --if-present
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout --if-present
npm --prefix frontend run build:desktop --if-present
npm --prefix frontend run package:linux --if-present
python3 -m compileall -q backend ops tests
python3 -m pytest backend/tests tests
python3 -m json.tool ops/envelopes/KOL-DESKTOP-CONTROL-APP-MVP-20260629.json >/dev/null
```

Required manual QA evidence:

- Ubuntu version.
- Node and npm versions.
- Screenshot: chat-first first screen.
- Screenshot: Control panel with nodes/tasks.
- Screenshot: Task Composer JSON preview.
- Screenshot or documented simulation: offline/degraded state.
- Package artifact path and checksum if AppImage/deb is built.

## Следующий безопасный diff

1. Add `frontend/src/features/desktopControl/contracts.js` generated from
   `backend/desktop_control_contracts.py` semantics.
2. Add `frontend/src/features/desktopControl/controlPlaneClient.js` with fetch
   wrappers and error mapping only; no UI wiring.
3. Add unit tests for validation/redaction/client URL building if the frontend
   test runner is available.
4. After current UI work lands, wire one read-only Control Panel tab using only
   `GET /v1/health`, `GET /v1/nodes`, and
   `GET /v1/tasks?summary=1&compact=1`.
5. Add destructive action dialogs only after read-only panel is verified on web
   and desktop dev shell.
