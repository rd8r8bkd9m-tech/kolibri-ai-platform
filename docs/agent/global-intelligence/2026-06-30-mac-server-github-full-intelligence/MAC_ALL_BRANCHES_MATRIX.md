# Mac branches matrix

## Counts

- local branches: 31.
- remote tracking branches: 70.
- remote-only heads from global metadata: 25.
- total global matrix rows: 126.

## Current branch context

Current worktree is detached at `6d0317c5`, aligned with current `origin/main`.

Local `main` branch exists in another worktree and is stale at `93502e46`, behind `origin/main`. Do not use that worktree as the source of truth without update/rebase in a clean worktree.

## High-priority branches

| Branch | Scope | Status | Risk | Recommendation |
|---|---|---:|---:|---|
| `origin/main` | current baseline | current | medium | use as base for new small branches |
| `codex/factory-autonomy-pwa-billing` | PWA, billing, autonomy, estimates, FormulaLM harness | huge PR #46 | high | split before merge |
| `codex/formulalm-rd-integration-20260629` | FormulaLM/scientific R&D | large | high | remote-only review and split |
| `p0/telegram-miniapp-kolibriai-deploy` | Telegram miniapp/director | PR #61 green | medium | review/deploy carefully |
| `codex/factory-ha-spool-20260627` | factory HA/spool | active local worktree | high | audit and rebase |
| `codex/telegram-live-director-primary` | Telegram live dialog | PR #81 draft green | medium | inspect before undraft |
| `codex/generic-runner-minimal-contract` | runner contracts | remote | high | compare with next P0 runner hardening |
| `factory/kol-live-factory-status-ui-20260626-050716` | factory status UI | remote/local history | medium | preserve useful UI changes |

## Branch categories

- Merge candidates: PR #61, PR #81 after review, small green runner/Telegram PRs.
- Split candidates: PR #46, FormulaLM branch, factory autonomy branch.
- Audit/archive candidates: old `agent/TG-*`, old factory smoke branches, prunable temp worktrees.
- Unsafe direct checkout candidates: any branch while current worktree is dirty with generated docs. Use safe worktree instead.

## Notes

The mirror clone attempt hung/timed out, so the matrix is based on local refs, remote tracking refs, GitHub/PR metadata and remembered remote-only heads. This is enough for planning, but a future runner should produce a machine-readable CSV from a clean mirror once server GitHub auth is fixed.
