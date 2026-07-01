# GitHub state report

## Repository

- repo: `rd8r8bkd9m-tech/kolibri-ai-platform`.
- visibility: private.
- default branch: `main`.
- local access: GitHub CLI authenticated on Mac through `/opt/homebrew/bin/gh`.
- permission: admin-level access observed.
- branch protection API for private repo returned a plan/visibility limitation response rather than useful protection data.

Secrets, tokens and credential values were not printed.

## PR state

- open PRs: 25.
- important PRs:
  - #46 draft: `codex/factory-autonomy-pwa-billing`, huge mixed branch, CI green, must split.
  - #61 ready: `p0/telegram-miniapp-kolibriai-deploy`, CI green, clean merge state.
  - #74 draft: FormulaLM branch into factory autonomy branch, CI green.
  - #81 draft: live Telegram dialog, CI green.
  - #60 ready: runtime smoke result capture into factory autonomy branch, CI green.
  - #36 ready: Kimi integration, CI green.
  - #29 ready: generic runner in Agent Host, CI green.

## Issues/P0

Important P0/project issues observed:

- #82: factory queue backlog with qjns clone auth failures and task index drift.
- #79: main stale active task and uiap disk exhaustion.
- #76: uiap node out of disk reserve and mesh-uiap stale.
- #69: factory queue blocked by missing target nodes.
- #66: factory queue starved by stale worker pool.
- #64: backlog largely unschedulable against live node set.
- #63: FormulaLM remote-only benchmark guard not enforceable.
- #62: dispatchable queue not leased by online workers.
- #59: queued backlog unschedulable.
- #58: block local FormulaLM benchmark paths.
- #57: automation context cannot reach Control Plane.
- #55: stale active_task after lease/dead_letter.
- #54: Desktop control app MVP.
- #53: secondary Control Plane node freshness degraded.
- #52: runtime rollout and server agents.

## CI

- workflow: `Kolibri CI`.
- workflow active: yes.
- recent runs: mostly successful.
- one recent failure observed:
  - run id: `28443763496`.
  - branch: `codex/kol-home-cluster-20260629-141939-009-main-codex`.
  - head: `aa350dd5...`.
  - conclusion: failure.

## GitHub blockers

- GitHub CLI not in default PATH on Mac.
- Server runtime repos fail noninteractive HTTPS GitHub operations.
- Branch protection details unavailable through current GitHub plan/visibility API response.
