# Result

Status: implementation complete; PR branch pending push.

What now works:

- README no longer presents the July 1 PR #85 release-gate state as current public status.
- Site UI copy is prepared to show fresh heartbeat capacity separately from online node count.
- Factory status ledger records the latest July 2 main/freshness facts and the public API verification blocker.

Blocked:

- External verification of `https://kolibriai.ru/api/factory/status` is blocked from this node by TLS hostname mismatch and HTTP 400 when forced through with `-k`.

Artifact paths:

- `docs/agent/runs/P0_EXEC_MAIN_README_SITE_FRESHNESS_PR_2026_07_02/PLAN.md`
- `docs/agent/runs/P0_EXEC_MAIN_README_SITE_FRESHNESS_PR_2026_07_02/ACTIONS.md`
- `docs/agent/runs/P0_EXEC_MAIN_README_SITE_FRESHNESS_PR_2026_07_02/TESTS.md`
- `docs/agent/runs/P0_EXEC_MAIN_README_SITE_FRESHNESS_PR_2026_07_02/RESULT.md`
- `docs/agent/runs/P0_EXEC_MAIN_README_SITE_FRESHNESS_PR_2026_07_02/NEXT.md`

Tests:

- `git diff --check`: passed.
- `python3 -m compileall -q backend ops scripts`: passed.
- `.venv/bin/python -m pytest -q`: `131 passed, 1 warning`.
- `npm --prefix frontend run test:mobile-layout`: passed.
- `npm --prefix frontend run build`: blocked by Node `v18.19.1`; Vite requires
  Node `20.19+` or `22.12+`.
- Public HTML route with valid TLS: blocked by certificate hostname mismatch.
- Public HTML route with `-k`: `200 text/html`.
- Public factory status route with valid TLS: blocked by certificate hostname
  mismatch.
- Public factory status route with `-k`: HTTP 400.

Branch:

- `agent/P0_EXEC_MAIN_README_SITE_FRESHNESS_PR_2026_07_02/generic`
