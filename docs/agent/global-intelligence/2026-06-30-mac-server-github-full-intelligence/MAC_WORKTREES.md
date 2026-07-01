# Mac worktrees

## Count

`git worktree list --porcelain` listed 30 worktrees.

## Important worktrees

| Worktree | Branch/HEAD | Meaning |
|---|---|---|
| `/Users/kolibri/.codex/worktrees/065e/kolibri-ai-platform` | detached `6d0317c5` | current intelligence-pack worktree, aligned with `origin/main` |
| `/Users/kolibri/.codex/worktrees/6ff4/kolibri-ai-platform` | `codex/factory-autonomy-pwa-billing` | large PR #46 local branch |
| `/private/tmp/kolibri-formulalm-integration.7zLn0e` | `codex/formulalm-rd-integration-20260629` | FormulaLM/R&D branch |
| `/Users/kolibri/.codex/worktrees/pr61-kolibri-ai-platform` | `p0/telegram-miniapp-kolibriai-deploy` | PR #61 worktree |
| `/Users/kolibri/Documents/Codex/kolibri-ai-platform` | `codex/factory-ha-spool-20260627` | older main local project worktree |
| `/Users/kolibri/Documents/Codex/worktrees/KOL-FACTORY-MVP-001` | `main` at `93502e46` | stale main worktree |

## Prunable worktrees observed

Some tmp/Codex worktrees are marked prunable because their gitdir target no longer exists. They were not cleaned in this read-only task:

- `/private/tmp/kolibri-github-telegram-check`
- `/private/tmp/kolibri-telegram-image-pr`
- `/private/tmp/kolibri-v3-shell-pr`
- `/Users/kolibri/.codex/worktrees/5486/kolibri-ai-platform`

## Operational rule

Do not checkout branches inside a dirty worktree. For future branch audits or splits, create safe temporary worktrees from clean refs.
