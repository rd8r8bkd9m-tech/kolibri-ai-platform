# TESTS

Task: `2026-07-01-p0-fabric-api-pr85-gap-review`
Reviewer: `Алексей — Fabric API Reviewer`
Node: `primary-candidate:agent-host-primary`

Remote review evidence:

- `python3 -m pytest tests/test_fabric_control.py -q` on PR #85: `5 passed`.
- `/tmp/kolibri-p0-fabric-venv/bin/python -m pytest -q` on PR #85: `65 passed, 1 warning`.
- System Python full pytest was blocked by missing local dependencies `pydantic` and `httpx`; this is an environment limitation, not a proven PR regression.
- `git diff --check origin/main...HEAD` on PR #85 failed due documentation EOF whitespace.
- `git grep` showed Prompt #3 canonical endpoints appear mostly in docs, not implementation.
- Exact artifact repair checks: all eight required files exist, JSON artifacts parse, and new artifact whitespace is clean.

Coverage classification:

- Existing PR #85 tests cover narrower `/v1/fabric/*` behavior.
- Missing tests: `/v1/fleet/*`, `/v1/models`, `/v1/responses`, `/v1/chat/completions`, `/v1/agents/*`, `/v1/admin/*`, canonical request/response envelopes, expanded fallback reason taxonomy.
