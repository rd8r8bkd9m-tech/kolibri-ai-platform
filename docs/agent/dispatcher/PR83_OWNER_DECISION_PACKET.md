# PR83 Owner Decision Packet

Updated: 2026-07-01T09:12:00Z

Purpose: give the owner a compact release-gate packet for PR #83 without
performing owner-only GitHub actions from the Mac dispatcher.

## Current PR State

- PR: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/83
- Title: `[p0] Harden Agent Host runner contract`
- State: open
- Draft: true
- Mergeable: true
- Base: `main`
- Base SHA: `6d0317c52a9694448ee2c352dc196ce7a27b9487`
- Head branch: `p0/agent-host-runner-contract-hardening-2026-06-30`
- Head SHA: `81daf44dc842dce40d8547275f47b051871a2690`
- Merge ref SHA: `ec509edce3728eb19aa59165c546f21e9e08a753`

## Evidence

GitHub:

- `Kolibri CI` run `28504679530` completed successfully for head
  `81daf44dc842dce40d8547275f47b051871a2690`.
- Job `ci` succeeded through Python compile, pytest, JS/TS checks,
  JSON/YAML validation, secret scan, production secret path guard, and local
  component smoke.
- Combined commit statuses list is empty; GitHub Actions workflow evidence is
  the source for CI status.

Server:

- Node: `primary-candidate`
- Verified worktree:
  `/var/lib/kolibri-agent/worktrees/P0_PR83_REVIEW_DIFF_CONTRACT_EXACT_ARTIFACT_CLEANUP_2026_07_01/P0_PR83_REVIEW_DIFF_CONTRACT_EXACT_ARTIFACT_CLEANUP_2026_07_01-attempt-1/repo`
- Worktree HEAD: `81daf44dc842dce40d8547275f47b051871a2690`
- `python3 -m py_compile ops/agent_host.py tests/test_agent_host_runner_contract.py`: passed
- `python3 -m pytest tests/test_agent_host_runner_contract.py -q`: `29 passed in 36.75s`
- `git diff --check`: passed
- Final git status: clean

Control Plane:

- `P0_PR83_REVIEW_DIFF_CONTRACT_EXACT_ARTIFACT_CLEANUP_2026_07_01`: completed.
- `P0_PR83_FINAL_MERGE_READINESS_VERIFICATION_2026_07_01`: failed with useful artifacts because the production runner still stayed on `main` and missed `PLAN.md`/`ACTIONS.md`.

## Scope

Current PR #83 diff is scoped to Agent Host runner contract hardening:

- `.gitignore`
- `ops/agent_host.py`
- `tests/test_agent_host_runner_contract.py`
- `docs/agent/**` runner contract and run artifacts

No `docs/superfactory/**` files are currently in the PR #83 diff.

## Important Caveats

- PR #83 is still draft.
- PR body text is stale and still references older head/test evidence.
- The current production Agent Host has not yet received the PR #83 fixes; this is why recent read-only/no-push tasks still showed `full_autonomy/git_push`, checkout drift, and brittle exact artifacts.
- Mac dispatcher did not mark ready, approve, merge, push to `main`, or restart services.

## Owner Options

Option A: owner approves release

1. Mark PR #83 ready for review if desired.
2. Merge PR #83 into `main`.
3. Deploy/restart Agent Host on target nodes.
4. Submit `P0_AGENT_HOST_POST_MERGE_CONTRACT_CANARY_2026_07_01`.

Option B: owner wants one more repair before merge

1. Keep PR #83 draft.
2. Dispatch a narrow PR-body/update or verifier-artifact repair task.
3. Re-run current-head CI and deterministic server verification.

## Next Prepared Task

`P0_AGENT_HOST_POST_MERGE_CONTRACT_CANARY_2026_07_01`

Submit only after PR #83 is merged into `main` and Agent Host is deployed/restarted from the merged code.
