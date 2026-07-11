directly to `main`. Product, documentation, and factory-runtime changes should
# KolibriAI Platform

KolibriAI Platform is a self-hosted AI Factory for controlled autonomous software development: tasks, agents, runner policy, artifacts, release evidence, and owner-approved operations in one auditable control surface.

Calibri V1 is the current release-candidate foundation. It is not a production deployment claim. It is a controlled branch state prepared for GitHub review, GitHub Pages publication, and later `kolibriai.ru` DNS/deploy actions after explicit approval.

## Why AI Factory

An agent dashboard usually shows conversations or individual runs. KolibriAI Platform treats AI work as factory production:

- tasks are submitted, routed, leased, reviewed, and completed;
- agents report status through API contracts;
- artifacts and logs are first-class release evidence;
- dangerous actions are blocked until approval;
- public product docs are separated from private operations and secrets.

## Architecture

```text
Owner / Lead Operator
  ↓
Frontend + Telegram / Superfactory entrypoints
  ↓
FastAPI Backend + Fabric API
  ↓
Factory Control / Task State / Runner Policy
  ↓
Agent Hosts and Worker Runtimes
  ↓
Artifacts / Logs / Status / Release Evidence
```

Worker agents must use API contracts. SSH is reserved for owner/lead diagnostics, bootstrap, and emergency recovery; it is not the worker-agent control plane.

## Current Status

- Status: `0.1.0-calibri-v1-transition` release candidate foundation.
- Branch: `p0/codex-sidebar-thread-bootstrap-20260704`.
- Public site target: `kolibriai.ru` planned through GitHub Pages.
- DNS/REG.RU/backend deploy/bootstrap: approval-gated and not performed by this preparation pass.

## Components

| Area | Path | Purpose |
| --- | --- | --- |
| Backend API | `backend/` | FastAPI chat, provider catalog, conversations, TTS/STT, web search, pipeline, factory status. |
| Frontend / Pages site | `frontend/` | React/Vite UI and GitHub Pages build output. |
| Factory control | `ops/factory_control.py` | Redis-backed task queue, leases, node heartbeat, Fabric routes, Superfactory status. |
| Agent host | `ops/agent_host.py` | Agent execution contract, artifact handling, permission checks. |
| Telegram / Superfactory | `ops/telegram_gateway.py`, `ops/telegram_superfactory.py` | Owner command layer, Mini App auth, runner policy. |
| Mesh bridge | `ops/mesh_control_bridge.py` | Local bridge for mesh/factory node operations. |
| Release evidence | `release/` | Manifests, reports, deployment plan, checkpoints. |
| Source of truth | `.kolibri/`, `docs/SOURCE_OF_TRUTH.md` | Agent onboarding and operating policy. |

## Quickstart

Backend:

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm install

# The default review target is derived from the checked-in CNAME. Override it
# only after verifying a different Kolibri API origin.
npm run dev
```

For a locally launched backend, first verify its `/v1/models` response and then
set `VITE_API_PROXY` to that credential-free origin. Vite never assumes that an
arbitrary process on localhost:8000 is Kolibri. See
[`docs/LOCAL_REVIEW_RUNTIME.md`](docs/LOCAL_REVIEW_RUNTIME.md).

Factory control sidecar:

```bash
backend/venv/bin/python ops/factory_control.py --host 127.0.0.1 --port 8765
```

Verification slice used for Phase 2:

```bash
jq empty release/manifest.json .vscode/tasks.json .vscode/settings.json .vscode/extensions.json
backend/venv/bin/python -m pytest -q tests/test_factory_control_superfactory.py tests/test_telegram_superfactory_miniapp.py tests/test_telegram_superfactory_contracts.py
```

## Roadmap

1. Stabilize the Calibri V1 release-candidate documentation and publication hygiene.
2. Preserve current `/v1/fabric/*` contracts while mapping desired `/v1/tasks`, `/v1/agents`, `/v1/artifacts`, and `/v1/approvals` endpoints.
3. Add compatibility tests before endpoint migration.
4. Publish GitHub Pages after approval.
5. Change `kolibriai.ru` DNS and deploy `api.kolibriai.ru` only after explicit approval.

## Security

- Raw secrets are not public docs or release artifacts.
- `ops/telegram.env`, `.env*`, private keys, credentials, logs, and runtime outputs are ignored or protected.
- Destructive bootstrap, production deploy, DNS, REG.RU, firewall, server reboot/reinstall, force push, and data deletion require explicit approval.
- CI includes JSON/YAML validation, secret scanning, and production secret path guard.

## Documentation

- [docs/SOURCE_OF_TRUTH.md](docs/SOURCE_OF_TRUTH.md)
- [docs/CALIBRI_V1_ARCHITECTURE.md](docs/CALIBRI_V1_ARCHITECTURE.md)
- [docs/CONTROL_PLANE_AGENT_MODEL.md](docs/CONTROL_PLANE_AGENT_MODEL.md)
- [docs/API_COMPATIBILITY_MAP.md](docs/API_COMPATIBILITY_MAP.md)
- [docs/GITHUB_PRESENTATION.md](docs/GITHUB_PRESENTATION.md)
- [docs/deployment-github-pages.md](docs/deployment-github-pages.md)
- [release/final-report.md](release/final-report.md)

## Release Status

Current release candidate evidence lives in [release/manifest.json](release/manifest.json), [release/checklist.md](release/checklist.md), and [release/final-report.md](release/final-report.md).

Public site target: `https://kolibriai.ru` after GitHub Pages and DNS approval.
