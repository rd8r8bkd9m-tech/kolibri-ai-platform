# Branch Policy

## Naming

- `p0/<topic>-YYYY-MM-DD`
- `p1/<topic>-YYYY-MM-DD`
- `docs/<topic>`
- `fix/<topic>`
- `feature/<topic>`
- `agent/<task-id>/<topic>`
- `research/<topic>`

## Rules

- `main` is protected by policy even if technical branch protection is blocked by plan limits.
- No direct push to `main`.
- No force push.
- No giant mixed PRs.
- No dirty runtime repo as merge source without preserved diff.
- Stale branches must be classified before archive.
- Branch deletion only after merged, archived and owner approved.

## Stacked Branches

Branches based on non-main branches must declare the dependency chain in their PR body. Example: PR #74 is stacked on PR #46 and therefore cannot be merged independently into `main`.

## Runtime Branches

Server runtime branches are not authoritative until their diffs are captured, redacted, tested and pushed to GitHub.
