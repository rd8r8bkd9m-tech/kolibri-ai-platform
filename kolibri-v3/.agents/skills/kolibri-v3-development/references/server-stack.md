# Dev stack operations

## Lifecycle

- The persistent stack runs in a GNU screen session `kolibri-v3-dev` and is
  managed by `scripts/dev-persistent.sh`.
- Commands (from `kolibri-v3/`):
  - `npm run dev:persistent:status` → `screen_session=running` +
    `runtime=ready`, or `screen_session=orphaned` (processes alive, screen
    died) or `stopped`.
  - `npm run dev:persistent:restart` — the only supported way to restart.
  - Logs: attach `screen -r kolibri-v3-dev` or tail
    `var/dev-runtime/screen.log`.
- Components: gateway `127.0.0.1:3103`, backend `127.0.0.1:8002` (uvicorn),
  desktop Next `3104`, Expo web `[::1]:4104` (IPv6 only!), legacy redirect
  `127.0.0.1:3000 → 3103`.

## Rules

- Never run `npm run dev` (or start a second stack) while one is alive: the
  pid guard in `scripts/dev-stack.mjs` (`var/dev-runtime/dev-stack.pid`)
  refuses, and two supervisors fighting for port 8002 cause a backend
  bind-error restart loop and 502s. If a duplicate exists (check
  `ps aux | grep "[d]ev-stack.mjs"`), it must be killed — prefer
  `dev:persistent:restart`, which reaps orphaned stacks via the pid file or the
  port-8002 listener fallback.
- `dev-persistent.sh` self-heals: `start` stops an orphaned/broken session
  first; `stop` reaps an orphaned stack; `status` reports `orphaned` when the
  screen is gone but the stack is healthy.
- Do not run heavy builds (`expo export`) while the stack is live — the CPU
  spike trips the health fence and the stack restarts itself.
- After backend changes, restart via `dev:persistent:restart` and confirm
  `runtime=ready` and all endpoints 200.

## Gateway routing (`scripts/dev-ui-gateway.mjs`)

- UI selection: mobile UA / `client=mobile` / affinity cookie
  `kolibri_ui_client` → Expo (mobile); otherwise → Next (desktop).
- Product API: paths starting `/v1/` or `/api/` are proxied to the backend
  (port `8002`), UI-agnostic. This is what makes same-origin mobile auth work
  from any host (localhost, LAN IP on a phone, production).
- `http://localhost:3000` is redirected to the gateway for legacy bookmarks.

## Health contract

`GET /v1/health` must contain `status:"ok"`, `service:"kolibri-v3"`,
`agentRuntimeContract:"kolibri.agent-runtime@1.1"`, `instanceId`, and
`sourceRoot` equal to the repo path. `runtime_ready` in
`dev-persistent.sh` checks all of these plus `GET /app` → 200.
