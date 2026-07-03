# Plan

Task id: `P0_REMOTE_OBSERVER_SWEEPERS_AND_AUTOMATION_TODAY_2026_07_02_REMOTE_RETRY_2026_07_02`

Closeout id: `P0_OBSERVER_ARTIFACT_CONTRACT_CLOSEOUT_20260703T1857Z`

Objective:

Close the artifact contract mismatch that blocked the P0 remote observer work by
publishing the exact original required outputs under the original required path:

`docs/agent/runs/2026-07-02-p0-remote-observer-sweepers-and-automation-today/`

Required output set:

1. `PLAN.md`
2. `ACTIONS.md`
3. `TESTS.md`
4. `RESULT.md`
5. `NEXT.md`
6. `DEPLOY_PLAN.md`
7. `ROLLBACK.md`

Execution plan:

1. Read the rejected remote task result and identify the required artifact list.
2. Create the exact missing required output files in the original required path.
3. Keep the change documentation-only and owner-safe.
4. Verify every required output is present and non-empty.
5. Run repository-safe doc checks.
6. Commit, push, and open a PR for the closeout branch.

Guardrails:

- Do not modify product code, tests, CI, secrets, service units, or runtime
  configuration.
- Do not restart services.
- Do not call Telegram APIs.
- Do not push to `main`.
- Do not merge, approve, mark ready, close, or force-push any PR.
