# All branches global matrix

## Counts

- local branches: 31.
- remote tracking branches: 70.
- remote-only heads from metadata: 25.
- total matrix rows: 126.
- Mac worktrees: 30.

## Global categories

| Category | Examples | Count/Notes | Action |
|---|---|---|---|
| baseline | `origin/main` | current head `6d0317c5` | use for new clean work |
| giant feature branches | `codex/factory-autonomy-pwa-billing`, `codex/formulalm-rd-integration-20260629` | hundreds of changed files | split |
| Telegram branches | `p0/telegram-miniapp-kolibriai-deploy`, `codex/telegram-*`, `agent/TG-*` | many active/historical | preserve useful artifacts, archive old |
| factory/runtime branches | `factory/*`, `codex/generic-runner-*`, `agent/*runtime*` | active Control Plane evolution | audit with runner-hardening first |
| docs/intelligence branches | `agent/2026-06-30-full-project-scan-for-chatgpt/read-only-scan` | server scan output branch | fetch artifact safely |
| stale local branches | local `main` at `93502e46` | behind current main | do not use as baseline |
| prunable worktree branches | tmp PR/check branches | gitdir missing | clean later only after backup/approval |

## Important branch notes

- `codex/factory-autonomy-pwa-billing`: local and remote heads differ; PR #46 remote head is the GitHub review target.
- `codex/formulalm-rd-integration-20260629`: large branch; should be assessed on server because FormulaLM is remote-only by policy.
- `p0/telegram-miniapp-kolibriai-deploy`: cleaner PR path; good candidate after final human review.
- `agent/2026-06-30-full-project-scan-for-chatgpt/read-only-scan`: exists remotely from the completed server scan; useful for recovering the prior full server digest.

## Required follow-up

Generate a real CSV/JSON branch matrix from a clean mirror after server GitHub auth is fixed. Current matrix is enough to plan next steps, not enough for automated branch cleanup.
