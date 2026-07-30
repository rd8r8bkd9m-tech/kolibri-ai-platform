# Local V3 runtime restart and superadmin session

Captured: 2026-07-30 17:28 MSK

Candidate state: dirty development tree on `codex/v3-home-deploy`.

This is local integration evidence. It does not claim an immutable release
candidate, a deployment or any production change.

## Canonical startup contract

- `npm run dev` starts `scripts/dev-stack.mjs`.
- The supervisor starts the backend only through `scripts/dev-backend.sh`.
- The backend is pinned to the canonical V3 database
  `var/kolibri-v3.db`.
- Before Uvicorn opens its port, `dev_preflight` runs database migrations,
  verifies the latest schema, and fails closed when the selected database or
  authority state is invalid.
- When users exist, preflight requires exactly one active
  `platform_owner` and checks the owner capabilities `platform.admin`,
  `chat.developer.request` and `chat.use`.
- QA/auth contamination environment variables are removed by the canonical
  launcher.
- The supervisor assigns a fresh opaque launch identity and the web process
  starts only after `/v1/health` returns HTTP 200 from that exact backend
  process with service identity `kolibri-v3`. A stale process on port 8002
  cannot satisfy this gate.
- If the backend exits after startup, the supervisor fences and restarts the
  web process; it cannot resume until the canonical backend again satisfies
  the launch-bound health gate.

## Alternate launch paths

The V3 runtime contract is now durable in `kolibri-v3/AGENTS.md` and the
repository development guide. The contract requires:

- `npm run dev` from the V3 root for a complete local launch;
- the V3-owned `backend/venv`, never a parent project interpreter;
- `scripts/dev-backend.sh` as the only backend child of the supervisor;
- migrations and the exact platform-owner preflight before port `8002`;
- launch-bound backend health before the frontend is allowed to start.

The previous `npm run dev:web` shortcut now exits with code `2` and directs the
operator to `npm run dev`. This removes a path that could connect the frontend
to an old or unrelated process already listening on port `8002`. The deleted
static V3 systemd/Nginx release files remain absent, and portable release tests
reject them if a future commit restores an alternate release lane.

## Observed restart

The complete stack was stopped and started through the canonical command.
Preflight reported:

```text
schema=43 users=7 platform_owner=1
```

The launcher required the configured canonical owner
`montodays@ya.ru`. That exact account maps to the unique active
`platform_owner` grant, contains the three required capabilities, retains a
valid `scrypt-v1` credential, and has non-revoked, non-expired sessions in the
same canonical database. Integrity was `ok`, foreign-key violations were zero,
and no login throttle row existed. No password, hash or session token was
printed, changed or reset.

Runtime probes then returned:

```text
GET /v1/health -> 200 {"status":"ok","service":"kolibri-v3","instanceId":"<launch-bound>"}
GET /app       -> 200
```

The existing browser session survived the restart. The account surface showed
`Суперадминистратор`; no login form or runtime error appeared, and the browser
console was empty.

The running backend child (`PID 4500`) was then terminated independently while the
supervisor remained alive. The supervisor observed `SIGTERM`, fenced and
stopped the web child, launched only `scripts/dev-backend.sh`, repeated:

```text
schema=43 users=7 platform_owner=1
```

then started backend `PID 4717` and a new web child only after launch-bound
health passed. `/v1/live`, `/v1/health`, `/api/live` and `/api/health` all
recovered. A fresh DOM snapshot contained exactly one
`Суперадминистратор` label and one active chat composer; the browser console
contained no warnings or errors. The database, owner binding and authenticated
session were unchanged. This directly covers an unexpected backend stop, not
only a complete stack restart.

## Real chat proof

From the retained authenticated session, the prompt:

```text
Ответь одним словом: работает
```

returned:

```text
работает
```

The request completed through `/api/agui` with HTTP 200 in 7.12 seconds.

## Current local gates

- Focused backend migration/owner/release-health regression: `14 passed`.
- Focused web launcher/release-health/observability regression: `22/22`.
- Complete backend baseline: `265 passed`.
- Complete web baseline: `122/122`.
- Portable release contracts: `14/14`.
- TypeScript typecheck: passed.
- Production web build: passed.

These gates prove the local restart contract and current development
integration only. Production was not restarted, migrated or deployed.

## 18:46 MSK follow-up: migration and owner-login regression

After a report that the stack had again started without migrations and the
superadmin login was unavailable, the live process was checked from the
operating system rather than inferred from the UI:

- backend PID `32539` had the V3 root as its real working directory and used
  `sqlite:///./var/kolibri-v3.db`;
- the canonical database reported schema `44/44`, `quick_check=ok`, exactly one
  active `platform_owner` for `montodays@ya.ru`, active account and tenant
  policy, no owner login throttle and six non-expired owner sessions;
- the Next.js login proxy reached the V3 `/v1/auth/login` endpoint and
  preserved its bounded error contract.

The backend child was terminated twice while the supervisor remained alive.
Both recoveries fenced the frontend and printed, before Uvicorn bound port
`8002`:

```text
Kolibri V3 preflight: schema=44 users=7 platform_owner=1
```

The final children were backend PID `38028` and frontend PID `38044`;
`/v1/health` and `/app` both returned HTTP 200.

An isolated identity test then exposed an import-order defect: importing
`app.chat.execution_adapter` caused `chat.__init__` to eagerly import the
router while `direct_model_runtime` was only partially initialized. The
package initializer no longer imports the router; application composition
continues to import `app.chat.router` explicitly. Verification after the fix:

```text
identity API                         15 passed
chat/image/weather focused tests    10 passed
dev startup contract                 4 passed
preflight/config/release health     19 passed
```

No owner password, password hash, session token or production state was read
out, reset or changed. A real password submission still requires the owner to
enter that secret in the local login form; the server-side migration, account,
throttle and login-route gates are green.

## 19:19 MSK follow-up: terminal-independent development runtime

The canonical supervisor previously remained a child of the active Codex
terminal. That protected backend-child recovery, but stopping the terminal
stopped the entire local product and made a later manual command vulnerable to
selecting a stale backend.

`scripts/dev-persistent.sh` now owns a detached `kolibri-v3-dev` GNU screen
session. It starts only `npm run dev`; it does not invoke Uvicorn, Next.js or a
legacy launcher directly. Readiness requires both an exact V3 development
instance ID and `/app` HTTP 200. `launchd` remains intentionally unused because
the source tree is inside macOS's protected `Documents` directory.

The previous terminal stack was stopped cleanly and the detached runtime
printed before opening the backend port:

```text
[dev:stack] Kolibri V3 source=.../kolibri-v3 database=var/kolibri-v3.db
Kolibri V3 preflight: schema=44 users=7 platform_owner=1
Kolibri V3 dev backend: .../kolibri-v3/var/kolibri-v3.db (127.0.0.1:8002)
```

Backend PID `51307` was then terminated while the screen-owned supervisor
remained alive. The supervisor fenced and replaced the frontend, repeated the
same schema/owner preflight and started backend PID `51684`; frontend PID
`51317` was replaced by PID `51822`.

Final live checks:

```text
screen_session=running
runtime=ready
database quick_check=ok
schema=44
blocked owner throttles=0
active owner sessions=6
backend=200
frontend_health=200
app=200
```

The exact owner throttle row was cleared before the restart so previous failed
login attempts cannot block the next real owner submission. The owner password,
credential hash and six active sessions were not changed. Startup contract
tests pass `5/5`; focused preflight, configuration and identity tests pass
`23/23`.
