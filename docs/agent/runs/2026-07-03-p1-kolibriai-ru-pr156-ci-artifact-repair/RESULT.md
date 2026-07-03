# Result

Status: ready for PR #156 CI rerun.

PR: `#156`

Branch: `codex/kolibriai-ru-turnkey-ai-app-redesign-2026-07-03`

## Summary

The PR #156 CI failure was traced to a frontend/backend status contract regression: the redesigned root frontend no longer referenced `/api/factory/status` or rendered the factory freshness labels required by `tests/test_factory_status.py`.

The repair restores a manual factory status card in `frontend/src/App.jsx`. It preserves the no-eager-startup-call behavior by calling `/api/factory/status` only from the explicit refresh action.

## Changed Files

- `frontend/src/App.jsx`
- `frontend/src/App.css`
- `docs/agent/runs/2026-07-03-p1-kolibriai-ru-pr156-ci-artifact-repair/PLAN.md`
- `docs/agent/runs/2026-07-03-p1-kolibriai-ru-pr156-ci-artifact-repair/ACTIONS.md`
- `docs/agent/runs/2026-07-03-p1-kolibriai-ru-pr156-ci-artifact-repair/TESTS.md`
- `docs/agent/runs/2026-07-03-p1-kolibriai-ru-pr156-ci-artifact-repair/RESULT.md`
- `docs/agent/runs/2026-07-03-p1-kolibriai-ru-pr156-ci-artifact-repair/NEXT.md`

## Verification

- `.venv/bin/python -m pytest tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint -q`: passed, `1 passed`.
- `.venv/bin/python -m pytest -q`: passed, `131 passed, 1 warning`.
- `python3 -m compileall -q backend infra scripts`: passed.
- `PATH=/var/lib/kolibri-agent/tools/node20/node_modules/node/bin:$PATH npm install --package-lock=false` in `frontend`: passed.
- `PATH=/var/lib/kolibri-agent/tools/node20/node_modules/node/bin:$PATH npm run build` in `frontend`: passed.
- `PATH=/var/lib/kolibri-agent/tools/node20/node_modules/node/bin:$PATH npm run lint` in `frontend`: passed.
- `PATH=/var/lib/kolibri-agent/tools/node20/node_modules/node/bin:$PATH npm run test:mobile-layout` in `frontend`: passed.
- `git diff --check`: passed.

## Publish Notes

- The branch is intended to be pushed back to `codex/kolibriai-ru-turnkey-ai-app-redesign-2026-07-03`.
- GitHub Actions should rerun on the updated branch.
- No production deployment or service restart was performed.
