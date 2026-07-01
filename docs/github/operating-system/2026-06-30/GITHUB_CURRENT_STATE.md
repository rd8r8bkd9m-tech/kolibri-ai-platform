# GitHub Current State

Snapshot date: 2026-06-30/2026-07-01 session.

## Repository

- Owner/repo: `rd8r8bkd9m-tech/kolibri-ai-platform`
- Visibility: private
- Default branch: `main`
- GitHub Issues: enabled
- GitHub Projects: enabled
- Wiki: disabled
- Current main head: `6d0317c52a9694448ee2c352dc196ce7a27b9487`

## Counts

- Open PRs: 27
- Open issues: 31
- Remote branches: 97
- Earlier global intelligence matrix rows: 126
- Milestones: none found
- Existing labels: 16

## Important Open PRs

| PR | State | Base | Head | Classification |
| --- | --- | --- | --- | --- |
| #85 | draft | `main` | `p0/api-first-full-control-fabric-2026-07-01` | P0 API-first Fabric, CI green, review carefully |
| #84 | draft | `main` | `codex/kolibri-superfactory-master-canvas-2026-07-01` | docs canvas |
| #83 | draft | `main` | `p0/agent-host-runner-contract-hardening-2026-06-30` | P0 runner hardening, central blocker |
| #81 | draft | `main` | `codex/telegram-live-director-primary` | Telegram/director runtime |
| #74 | draft | `codex/factory-autonomy-pwa-billing` | `codex/formulalm-rd-integration-20260629` | FormulaLM research stacked on high-risk PR #46 |
| #61 | ready | `main` | `p0/telegram-miniapp-kolibriai-deploy` | Telegram miniapp deploy fix |
| #46 | draft | `main` | `codex/factory-autonomy-pwa-billing` | split-required, high risk |

## Existing Issue Signals

Known P0 issue topics already exist for queue backlog, uiap/qjns disk exhaustion, stale worker pool, FormulaLM remote-only guard, Control Plane reachability, runtime rollout, docs and design. They are useful but not yet governed by a consistent label/milestone/project taxonomy.

## Missing Governance Files

Before this branch:

- `SECURITY.md`: missing
- `CONTRIBUTING.md`: missing
- `.github/CODEOWNERS`: missing
- `.github/PULL_REQUEST_TEMPLATE.md`: missing
- `.github/ISSUE_TEMPLATE/config.yml`: missing
- release/changelog policy: missing

## CI

Workflow: `.github/workflows/ci.yml`, name `Kolibri CI`.

It currently runs:

- Python compile over `backend`, `infra`, `scripts`;
- pytest discovery;
- frontend build/lint/typecheck/test when configured;
- JSON/YAML validation;
- secret scan;
- production secret path guard;
- local component smoke.

Recent runs are mostly green. Recent known failure: run `28443763496` on branch `codex/kol-home-cluster-20260629-141939-009-main-codex`.

## GitHub Projects

Observed projects:

- `Kolibri AI Platform: фабрика ИИ и продукт на миллиарды`
- `@rd8r8bkd9m-tech's untitled project`

This package proposes the operational board `Kolibri Factory OS`; creating or reconfiguring Projects should be owner-approved because it changes GitHub workspace metadata.
