# PR and CI report

## Summary

- Open PRs: 25.
- Main CI workflow: `Kolibri CI`.
- Recent CI is mostly green.
- At least one recent branch run failed: `codex/kol-home-cluster-20260629-141939-009-main-codex`.

## Key PRs

| PR | State | Base | Head | CI/Merge | Risk |
|---:|---|---|---|---|---|
| #46 | draft | `main` | `codex/factory-autonomy-pwa-billing` | CI success, clean | very high, too broad |
| #61 | ready | `main` | `p0/telegram-miniapp-kolibriai-deploy` | CI success, clean | medium |
| #74 | draft | `codex/factory-autonomy-pwa-billing` | `codex/formulalm-rd-integration-20260629` | CI success, clean | high |
| #81 | draft | `main` | `codex/telegram-live-director-primary` | CI success, clean | medium |
| #60 | ready | `codex/factory-autonomy-pwa-billing` | runtime smoke branch | CI success, clean | medium |
| #36 | ready | `main` | Kimi integration | CI success | medium |
| #29 | ready | `main` | generic runner in Agent Host | CI success | high importance |

## PR #46 decomposition target

Split into:

1. Frontend/PWA shell.
2. Billing scaffold.
3. Factory autonomy contracts and generic runner.
4. Deterministic estimates.
5. FormulaLM remote-only harness.
6. Documentation-only artifacts.

## CI failure to inspect later

Run `28443763496` failed on branch `codex/kol-home-cluster-20260629-141939-009-main-codex`. It is not the top blocker unless it blocks a merge target, but should be inspected before relying on that branch.
