# Git Checkpoint

Status: prepared for controlled staging; commit should happen only after final staged secret/path checks.

## Recommended Commit Message

```bash
git commit -m "chore(calibri-v1): establish release candidate foundation"
```

## Stage Only These Groups

- `.gitignore`
- `.kolibri/`
- `.github/ISSUE_TEMPLATE/`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.vscode/`
- `AGENTS.md`
- `VERSION`
- `README.md`
- `docs/` files created/updated for Calibri V1 release candidate
- `ops/README.md`
- `ops/SERVER_INVENTORY.private.example.md`
- `ops/BOOTSTRAP_NOTES.private.example.md`
- `release/` files created/updated for Phase 1/2

## Do Not Stage

- `ops/telegram.env`
- `.env` or `.env.*`
- `logs/`
- `output/`
- `server.pid`
- `frontend/storybook-static/`
- `frontend/test-results/`
- private keys/tokens/secrets/credentials
- `apps/` until classified
- `tests/test_kolibri_invention_synthesis.py` until reviewed

## Pre-Commit Checks

```bash
git status --short
git diff --cached --stat
git diff --cached --name-only | grep -E '(^\.env|ops/telegram\.env|\.pem$|\.key$|\.secret$|secrets/|credentials/)' && exit 1 || true
```
