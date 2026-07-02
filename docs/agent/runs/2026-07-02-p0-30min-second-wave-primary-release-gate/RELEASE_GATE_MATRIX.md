# Release Gate Matrix

Task id: `P0_30MIN_SECOND_WAVE_PRIMARY_RELEASE_GATE_2026_07_02`

Decision: `blocked_for_p0_exit`

Summary: checked-in runtime contracts and live primary Factory Control routes
passed, but the 30-minute freshness gate did not pass. The live fleet response
contains 42 node cards; only 11 have heartbeat timestamps within 30 minutes and
31 are older than 30 minutes.

| Gate | Evidence | Result |
| --- | --- | --- |
| Branch aligned with `origin/main` | `HEAD == origin/main == f7ac32c70406432a52752ca45d87e35d9f1facd3` | pass |
| Focused runtime tests | `122 passed in 36.36s` | pass |
| Runtime import/preflight | `factory_control_runtime_preflight=ok` | pass |
| Python compile smoke | key runtime modules compiled | pass |
| Whitespace check | `git diff --check` clean | pass |
| Frontend mobile layout guard | `mobile layout guard passed` | pass |
| Frontend build | `vite: not found` because dependencies are not installed | blocked_env |
| Broad Python suite | missing `pydantic` and `httpx` in node Python env | blocked_env |
| Factory Control live routes | six primary routes returned HTTP 200 | pass |
| Factory Control service | `active/running`, PID `3588876` | pass |
| Telegram Gateway service | `active/running`, PID `3676235`; no Bot API call made | pass_observed |
| 30-minute fleet freshness | 11 fresh, 31 stale, 42 total | fail |

P0 exit blocker:

- `B1`: Fleet freshness is below the release threshold for a 30-minute primary
  wave. The API still reports stale node cards as `health=online`, and this
  wave observed `31/42` nodes with heartbeat age greater than 30 minutes.

Residual environment blockers:

- `E1`: The local Python environment lacks `pydantic` and `httpx`, so broad
  test collection cannot be used as a release signal on this node.
- `E2`: The frontend dependency tree is absent, so `npm --prefix frontend run
  build` cannot verify Vite output in this worktree.
- `E3`: `frontend/package.json` does not define a generic `test` script; the
  available mobile layout guard was run directly.

Safety:

- No live mutation occurred.
- No Telegram Bot API call occurred.
- No service restart occurred.
- No secrets were printed.
