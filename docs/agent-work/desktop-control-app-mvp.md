# Desktop Control App MVP implementation pack

Дата: 2026-06-29  
Роль исполнителя: `desktop_control_app_builder`  
Источник: `docs/desktop-control-app.md`  
Назначение: реализовать MVP desktop-приложения в стиле Codex для полного
операторского контроля фабрики Kolibri через Control Plane, GitHub/CI и
безопасные task envelopes.

## 1. Scope

Сделать review-ready implementation PR для Ubuntu-фабрики. Приложение должно
переиспользовать текущий Kolibri chat-first UX и расширить его desktop control
surface, а не строить отдельную админку.

Обязательные направления:

- desktop shell / desktop mode для существующего React/Vite frontend;
- Control Plane client для health, nodes, tasks, task detail, submit, cancel,
  annotate, drain/undrain, agent messages;
- chat-first Command Center и правый нижний `Control`;
- Task Composer / Envelope Builder;
- Task Detail / Timeline;
- Nodes / Capacity;
- Artifacts / Review;
- GitHub/CI/Project integration или documented authenticated blocker;
- offline/degraded mode;
- Ubuntu QA evidence.

## 2. Жёсткие инварианты

- Не использовать SSH как основной control path.
- Не читать node-local artifacts напрямую из desktop app.
- Не вызывать worker-only lifecycle endpoints (`lease`, task heartbeat,
  `complete`, `fail`) как owner actions.
- Не печатать и не коммитить секреты, `.env`, private keys, cookies, auth
  cache, tokens.
- Не скрывать degraded state и GitHub/Project auth blockers.
- Не менять unrelated функциональность SPA, billing, FormulaLM, estimates или
  factory runtime без необходимости для MVP.
- Не откатывать чужие изменения.

## 3. Recommended implementation shape

Исполнитель должен сначала проверить текущий frontend/backend layout и выбрать
самый маленький production-safe путь. Предпочтительный MVP:

- переиспользовать `frontend` React/Vite приложение;
- добавить desktop shell с изоляцией renderer process, disabled Node access in
  UI, context bridge только для безопасных app APIs;
- оставить web/PWA `/app` работоспособным;
- добавить desktop-specific config через env, например `KOLIBRI_CONTROL_URL`,
  `KOLIBRI_BACKEND_URL`, `KOLIBRI_GITHUB_REPO`;
- если packaging runtime требует новые крупные зависимости, явно описать
  причину в PR и проверить build на Ubuntu.

Если полноценный desktop package невозможен на текущей ноде, PR всё равно
должен дать working dev shell, точный blocker и список недостающих пакетов.

## 4. Functional requirements

### 4.1 Command Center

- app starts in chat-first workspace;
- user can ask for factory status and receive live or explicitly stale facts;
- command preview is shown before submit/cancel/drain;
- messages are in Russian by default;
- errors include next action, not raw traceback.

### 4.2 Control Plane client

Implement typed/small client methods for:

- `GET /health` or `/v1/health`;
- `GET /v1/nodes`;
- `POST /v1/nodes/<node_id>/drain`;
- `GET /v1/tasks?summary=1&compact=1`;
- `GET /v1/tasks?state=<state>&limit=<n>`;
- `GET /v1/tasks/<task_id>`;
- `POST /v1/tasks`;
- `POST /v1/tasks/<task_id>/cancel`;
- `POST /v1/tasks/<task_id>/annotate`;
- `GET /v1/agent-messages?target=all&limit=<n>`;
- `POST /v1/agent-messages`.

All client errors must map to safe UI states: offline, degraded, unauthorized,
not found, validation error, server error.

### 4.3 Task Composer / Envelope Builder

- validate required fields: `task_id`, `kind`, `goal`, `acceptance`, `source`;
- support existing envelope fields from `ops/envelopes/*.json`;
- run JSON parse validation before submit;
- show idempotency key if present;
- show warning for `permission_pack=full_autonomy`;
- keep drafts local and do not auto-submit after reconnect.

### 4.4 Factory dashboard

- show nodes with heartbeat age, draining, active_task, capabilities,
  permissions, machine stats where present;
- show task summary and queue length;
- flag stale heartbeat and stale lease;
- link to task detail from node active_task.

### 4.5 Task detail and review

- show state, attempt, lease_owner, lease_until, heartbeat_at, branch,
  worktree/log references as sanitized technical details;
- show acceptance checklist from envelope;
- show result_reference/result summary;
- show agent messages related to the task where available;
- support cancel and annotate with confirmation.

### 4.6 GitHub/CI/Project

- surface PR/issue URLs from result payloads;
- if authenticated GitHub integration is implemented, show checks and Project
  status fields;
- if auth/scope is unavailable, show `Project sync: pending` with exact reason;
- never mark failed CI as success.

### 4.7 Offline/degraded

- cache last successful factory snapshot with timestamp;
- show stale labels when using cache;
- keep local drafts for envelopes;
- require fresh confirmation before replaying any action after reconnect;
- keep app usable when GitHub is down but Control Plane is up.

## 5. Security requirements

- tokens stored only in OS secret storage or secure local profile;
- log redaction for token-like strings, env file content, private keys,
  cookies, local auth cache;
- destructive actions require typed or explicit confirmation;
- app logs and QA screenshots must not contain secrets;
- GitHub scopes must be minimal and documented;
- owner-facing copied summaries redact local paths unless user asks for
  technical details.

## 6. Ubuntu QA

Run and report on Ubuntu factory node:

```bash
npm --prefix frontend run lint --if-present
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout --if-present
npm --prefix frontend run build:desktop --if-present
npm --prefix frontend run package:linux --if-present
python3 -m compileall -q backend ops tests
python3 -m pytest backend/tests tests
```

Manual evidence expected:

- screenshot of desktop app first screen;
- screenshot of Control Panel with nodes/tasks;
- screenshot of Task Composer preview;
- screenshot of degraded/offline state or documented way to simulate it;
- package artifact path/checksum if AppImage/deb was built;
- exact Ubuntu version, Node version, npm version.

## 7. Acceptance

Implementation is acceptable when:

- app launches on Ubuntu in desktop mode or returns a precise packaging blocker
  with working dev shell;
- current web/PWA frontend still builds;
- Control Plane health/nodes/tasks/task detail are visible;
- valid envelope can be submitted through `/v1/tasks`;
- cancel and drain/undrain work with confirmation;
- degraded/offline/cache behavior is explicit;
- GitHub/CI/Project integration works or reports authenticated blocker;
- tests/build commands and manual screenshots are attached to result;
- no secrets appear in diff, logs, screenshots or result payload.

## 8. Result report format

Return a Russian result with:

- summary;
- changed files;
- implementation notes and chosen desktop runtime;
- verification commands and exact outputs/conclusions;
- Ubuntu QA evidence;
- screenshots/artifact paths;
- blockers;
- security notes;
- follow-up envelopes/issues.

## 9. Suggested follow-ups

- dedicated RBAC/auth hardening task;
- event stream/WebSocket updates for Control Plane;
- filesystem namespace manifest UI after `/v1/filesystem` is implemented;
- signed update channel for desktop builds;
- multi-user operator mode.
