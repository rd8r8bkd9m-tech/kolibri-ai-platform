# KolibriAI Platform Source of Truth

This branch is the active FastAPI/React/Fabric/Superfactory product workspace for KolibriAI Platform.

## Product Direction

KolibriAI Platform is an AI factory control surface: chat, provider routing, factory control, Telegram/Superfactory commands, Fabric API, artifacts, release evidence, and public site delivery.

Calibri V1 is the forward direction. In this branch, Calibri V1 means aligning the active Python/React runtime with the same rules as the Rust foundation:

- API-first control plane;
- one canonical Control Plane on `home`; legacy `main`/`primary` control
  endpoints are not used as fallbacks;
- worker agents through API contracts, not SSH;
- traceable tasks, heartbeats, logs, artifacts, and approvals;
- protected bootstrap, deploy, DNS, and secrets;
- public/private documentation split.

## Branch Role

- Current branch: `p0/codex-sidebar-thread-bootstrap-20260704`.
- Role: active product/runtime branch.
- Related foundation branch: `p0/free-low-cost-model-provider-registry-20260704` in `/Users/kolibri/.codex/worktrees/b56d/kolibri-ai-platform`.

Do not treat the two worktrees as interchangeable. Merge or cherry-pick only after review.

## Canonical Paths

| Area | Path | Role |
| --- | --- | --- |
| Backend API | `backend/` | active FastAPI runtime |
| Frontend | `frontend/` | active React UI |
| Factory control | `ops/factory_control.py` | active Redis-backed control sidecar |
| Control Plane placement | `docs/CONTROL_PLANE_HOME_CANONICAL.md` | canonical Home-only identity and migration rules |
| Agent host | `ops/agent_host.py` | active agent execution contract |
| Telegram/Superfactory | `ops/telegram_superfactory.py`, `docs/telegram-superfactory.md` | owner command layer |
| Fabric API docs | `docs/fabric-api-first-control.md` | current API-first operating doctrine |
| Deployment | `scripts/deploy.sh`, `ops/systemd/` | protected |
| Release evidence | `release/` | branch release state |
| Policy/onboarding | `.kolibri/`, `AGENTS.md` | agent operating rules |

## Do Not Do

- Do not expose `ops/telegram.env` or other secret-like files.
- Do not run uncontrolled bootstrap/deploy.
- Do not change DNS/REG.RU without approval.
- Do not delete generated runtime artifacts unless requested.
- Do not give worker agents SSH.
