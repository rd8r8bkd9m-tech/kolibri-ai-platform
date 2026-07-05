# Repository Cleanup Plan

Cleanup is documentation-first and non-destructive.

## Already Protected

- `ops/*.env`
- `ops/*.private.md`
- `.env.*` except `.env.example`
- `logs/`
- `output/`
- `server.pid`
- `frontend/storybook-static/`
- `frontend/test-results/`
- `*.secret`
- `*.key`

## Do Not Delete Yet

- `apps/`
- `.factory/`
- `.codex-runtime/`
- `output/`
- `logs/`
- `tests/test_kolibri_invention_synthesis.py`

These may contain active work or evidence. Archive/delete only after owner approval.

## Next Cleanup Step

Classify untracked `apps/` content into: source, generated, obsolete, private, or release evidence.
