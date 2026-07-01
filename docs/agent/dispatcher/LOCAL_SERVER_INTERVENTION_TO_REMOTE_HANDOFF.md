# Local/Server Intervention To Remote Handoff

Date: 2026-07-01

Owner correction: the Mac agent must act as a thin dispatcher, not as the main executor. During the live factory pult incident, the Mac dispatcher performed direct server diagnostics and started a server-side frontend deploy attempt. This is recorded as non-authoritative and handed off to a remote agent.

## Incident

- Symptom: `https://kolibriai.ru/?telegram=1` rendered the old general Kolibri workspace instead of the factory pult.
- API status: `https://kolibriai.ru/api/factory/status` returned `200 application/json`.
- Root cause found: Home nginx proxies `/` to `http://78.17.4.108:5174`; that upstream is Docker container `kolibrifin-dev-web` on `primary-candidate`, serving stale static assets from `/srv/kolibri/kimi-agent-kolibrifin/Kimi_Agent_Deployment_v13`.
- `origin/main` already contains the factory UI markers `/api/factory/status`, `Фабрика Колибри`, and `Сеть Kolibri`.

## Manual Attempt

- System Node on `primary-candidate` is `v18.19.1`; Vite 8 requires Node `20.19+`, so the first build failed before production mutation.
- Existing Docker image `node:20-alpine` built the frontend successfully and `npm run test:mobile-layout` passed.
- A backup was created:
  `/srv/kolibri/kimi-agent-kolibrifin/backups/Kimi_Agent_Deployment_v13-before-factory-pult-20260701T104520Z.tgz`
- The built `dist` was copied into:
  `/srv/kolibri/kimi-agent-kolibrifin/Kimi_Agent_Deployment_v13`
- The ad hoc smoke harness exited `22`, likely because it checked JS and CSS in one loop and overwrote JS success flags with CSS failure flags.

## Handoff

Remote task:
`P0_FACTORY_PULT_REMOTE_AGENT_TAKEOVER_2026_07_01`

Envelope:
`docs/agent/dispatcher/envelopes/P0_FACTORY_PULT_REMOTE_AGENT_TAKEOVER_2026_07_01.json`

Required remote outcome:
- independently verify current live pult;
- confirm if healthy;
- rollback using the backup if broken;
- complete safe repair only if still stale;
- produce exact `PLAN.md`, `ACTIONS.md`, `TESTS.md`, `RESULT.md`, `NEXT.md`.

Mac must not continue product/server implementation by hand for this incident.
