# Calibri V1 Architecture

This branch is the active FastAPI/React/Fabric/Superfactory implementation branch. Calibri V1 architecture here is a transition architecture: keep the working Python/React runtime stable while aligning it with the Rust-first foundation in the related worktree.

## Current Stack

- Backend: FastAPI in `backend/`.
- Frontend: React/Vite in `frontend/`.
- Factory control: Redis-backed sidecar in `ops/factory_control.py`.
- Agent host: `ops/agent_host.py`.
- Telegram/Superfactory: `ops/telegram_gateway.py`, `ops/telegram_superfactory.py`.
- Fabric API: `/v1/fabric/*` contracts and docs in `docs/fabric-api-first-control.md`.
- Site/Pages: `.github/workflows/pages.yml`, `release/dns-instructions.md`, frontend build.

## Target Direction

- API-first Control Plane.
- Worker agents communicate through API contracts only.
- Tasks, events, artifacts, approvals, and runner policy are explicit contracts.
- Bootstrap, deploy, DNS, firewall, secrets, and production changes are approval-gated.
- Public docs do not contain private server inventory, secret values, or raw operational credentials.

## Related Foundation

The Rust-first foundation reference is in:

```text
/Users/kolibri/.codex/worktrees/b56d/kolibri-ai-platform
```

This branch should not blindly import that worktree. Migrate concepts through focused PRs with tests.
