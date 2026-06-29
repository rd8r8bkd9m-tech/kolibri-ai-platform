# Deploy readiness gate

Date: 2026-06-29
Scope: read-only app release readiness gate for PR #46, factory health, and PWA
release evidence.

## Purpose

`scripts/deploy_readiness_gate.sh` is a local release gate. It gathers the
minimum facts needed before an app release decision and prints a clear
`GO`/`NO-GO` verdict.

The gate is intentionally read-only. It does not stage, commit, push, start
services, change Control Plane state, run model workloads, or release changes.

## What it checks

- Git worktree status and current branch/head.
- GitHub PR #46 metadata through `gh pr view`.
- GitHub PR #46 checks through `gh pr checks`.
- Factory `/health`.
- Factory compact task summary:
  `/v1/tasks?summary=1&compact=1&limit=20`.
- Product QA task state, default `KOL-PRODUCT-QA-E2E-20260629`.
- `server-kfrm` probe task state, default `KOL-SERVER-KFRM-PROBE-20260629`.
- PWA command documentation in `frontend/package.json`.
- Presence of release evidence docs used by the gate.

## Usage

Run from anywhere inside the repository:

```bash
scripts/deploy_readiness_gate.sh
```

Expected exit codes:

- `0`: `GO`, all gate checks passed.
- `1`: `NO-GO`, at least one release blocker remains.
- `2`: local invocation problem, such as running outside a git repository.

Optional overrides:

```bash
PR_NUMBER=46 \
GH_REPO=rd8r8bkd9m-tech/kolibri-ai-platform \
FACTORY_URL=http://10.99.0.2:9101 \
FACTORY_TASK_ID=KOL-PRODUCT-QA-E2E-20260629 \
KFRM_PROBE_TASK_ID=KOL-SERVER-KFRM-PROBE-20260629 \
scripts/deploy_readiness_gate.sh
```

## PWA commands documented by the gate

The gate verifies that these commands are represented by scripts in
`frontend/package.json`; it does not execute them:

```bash
npm --prefix frontend run lint --if-present
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout --if-present
npm --prefix frontend run preview -- --host 127.0.0.1 --port 4173 --strictPort
```

`build` and `preview` are intentionally not run by the gate because they create
artifacts or start foreground processes. Use their output as separate evidence
before changing release status.

## Current expected verdict

As of the 2026-06-29 release docs, the honest verdict is expected to be
`NO-GO` until PR #46 has green GitHub checks, the PR is out of draft state, live
factory/product QA evidence is complete, and production-like PWA evidence is
attached.

## Safety notes

The script uses only local git reads, GitHub CLI reads, `curl` GET requests,
and JSON parsing of `frontend/package.json`.

If `gh` is unavailable or not authenticated, the PR/CI checks fail closed.
If the factory URL is unavailable, factory health and task checks fail closed.
