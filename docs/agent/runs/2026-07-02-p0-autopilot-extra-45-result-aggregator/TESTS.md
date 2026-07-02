# Verification

Commands run:

- `git fetch --all --prune`
- `git for-each-ref --format='%(committerdate:iso8601)|%(refname:short)|%(objectname:short)|%(subject)' refs/remotes/origin/agent`
- `git diff --name-status origin/main...<ref>` for the selected 25 refs
- `git show <ref>:<artifact>` for selected `REMOTE_RESULT.json`, `RESULT.md`, `NEXT.md`, and intelligence artifacts

Post-write checks:

- `git diff --check`
- `python3 -m json.tool docs/agent/runs/2026-07-02-p0-autopilot-extra-45-result-aggregator/REMOTE_RESULT.json`

Scope guard:

- Docs-only local changes.
- No secrets printed.
- No destructive git commands.
- No force push.
- No push to `main`.
