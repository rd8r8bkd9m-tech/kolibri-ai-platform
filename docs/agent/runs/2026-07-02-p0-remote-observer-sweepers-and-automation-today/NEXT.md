# NEXT: P0 Remote Observer Sweepers and Automation Today

## Recommended Next State

Mark `P0_OBSERVER_ARTIFACT_CONTRACT_CLOSEOUT_20260703T1857Z` as unblocked after verifying the pushed commit contains the seven required files at the exact original paths.

## Follow-Up

1. Gate verifier should check the exact path:
   `docs/agent/runs/2026-07-02-p0-remote-observer-sweepers-and-automation-today/`
2. Required artifact list should be treated as closed when these files are present and non-empty:
   `PLAN.md`, `ACTIONS.md`, `TESTS.md`, `RESULT.md`, `NEXT.md`, `DEPLOY_PLAN.md`, `ROLLBACK.md`.
3. If runtime observer sweeper validation is still needed, dispatch it as a separate remote runtime task with its own run directory and required outputs.

## Do Not Repeat

Do not substitute a retry-specific directory or a similarly named run path for this task. The closeout contract is path-sensitive.
