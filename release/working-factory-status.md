# Working Factory Status

Date: 2026-07-05

## Short Answer

Yes, the factory is being brought to a working release-candidate state.

It is not yet a fully live production factory until the approval-gated publication/deploy steps are completed.

## Working Now

- Source-of-truth policy and onboarding are in place.
- Release-candidate docs and public presentation are in place.
- GitHub Pages side is prepared in the repository.
- Frontend build passes.
- Backend, ops, and scripts compile.
- Full Python test suite passes: `210 passed`.
- Superfactory/Fabric focused contracts pass: `14 passed`.
- Public-file secret scan has no findings.
- Commit checkpoint exists: `f5bea2965 chore(calibri-v1): establish release candidate foundation`.

## Working As Current Local Contracts

- FastAPI backend health/chat/provider/factory status surface.
- Fabric/Superfactory Python sidecar contracts.
- Telegram Mini App task envelope and runner policy contracts.
- Agent host permission/artifact/task behavior covered by existing tests.
- GitHub Pages frontend build path using `frontend/dist` and `frontend/CNAME`.

## Not Yet Production-Live

- Branch has not been pushed by this agent.
- GitHub Pages has not been deployed by this agent.
- `kolibriai.ru` DNS has not been changed.
- `api.kolibriai.ru` backend has not been deployed.
- Production bootstrap has not been run.
- Server/firewall/TLS changes have not been performed.

## Known Gaps Before Full Factory Runtime

- Canonical Calibri V1 endpoints are not all implemented as backend routes yet:
  - `GET /v1/status`
  - `POST /v1/agents/enroll`
  - `POST /v1/tasks/{id}/events`
  - `GET /v1/tasks/{id}/events`
  - `POST /v1/approvals/request`
  - `POST /v1/approvals/{id}/resolve`
- Current Fabric/Superfactory contracts remain the working bridge.
- `api.kolibriai.ru` target server/service/TLS path must be confirmed before deploy.
- `apps/` remains untracked and unclassified.
- `tests/test_kolibri_invention_synthesis.py` remains untracked and unreviewed.

## What Makes It Fully Working

The factory should be considered fully working when these are complete:

1. Current branch is pushed and reviewed.
2. GitHub Pages deployment succeeds.
3. `kolibriai.ru` DNS is approved, changed, propagated, and verified.
4. Backend API target for `api.kolibriai.ru` is approved, deployed, TLS-enabled, and health-checked.
5. Canonical Control Plane endpoint gaps are either implemented or explicitly mapped to tested Fabric equivalents.
6. Worker agents can enroll/heartbeat/receive tasks/register artifacts through API contracts without SSH.
7. Production bootstrap remains controlled and repeatable with rollback.

## Approval Boundary

The next steps that can turn the release candidate into a live factory require explicit `USER_APPROVAL_REQUIRED` approval:

- push current branch;
- run/enable GitHub Pages publication;
- change REG.RU/DNS records;
- deploy backend to `api.kolibriai.ru`;
- run protected bootstrap;
- modify servers/firewall/TLS.
