# PR #91 Owner Decision Packet

Date: 2026-07-01

PR: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/91

Branch: `p0/mimo-runner-output-auth-contract-repair-2026-07-01`

Current head: `350544492ce14a12865fb9a04e2abf6f87c87d3f`

Status: open, draft, mergeable, GitHub Actions green.

## What PR #91 Fixes

PR #91 repairs the Agent Host direct MIMO runner contract:

- parses useful JSON-object stdout from MIMO instead of marking it `runner_empty_response`;
- classifies HTTP 401 as runner auth failure;
- classifies HTTP 403 / `illegal_access` as provider or policy access denial;
- preserves runner-specific error types instead of flattening them to generic runtime errors;
- adds focused regression tests for direct MIMO output/auth modes.

## Evidence

- Server implementation task:
  `P0_MIMO_RUNNER_OUTPUT_AND_AUTH_CONTRACT_REPAIR_2026_07_01`
- Implementation commit before cleanup:
  `a32697b62914816abfbd87365c7c1fec588b3262`
- Focused release verifier:
  `P0_PR91_MIMO_RUNNER_FOCUSED_RELEASE_VERIFIER_2026_07_01`
- Focused verifier result:
  exact PR head verified; targeted tests passed:
  `python3 -m pytest -q tests/test_agent_host_direct_mimo.py tests/test_agent_host_telegram_chat.py tests/test_agent_host_image_generation.py`
  -> `9 passed in 2.17s`
- Artifact hygiene repair:
  `P0_PR91_MIMO_RUNNER_ARTIFACT_HYGIENE_REPAIR_2026_07_01`
- Cleanup commit:
  `350544492ce14a12865fb9a04e2abf6f87c87d3f`
- GitHub Actions:
  run `28518947833`, conclusion `SUCCESS`

## Scope After Cleanup

PR #91 currently changes:

- `ops/agent_host.py`
- `tests/test_agent_host_direct_mimo.py`
- `docs/agent/runs/2026-07-01-p0-mimo-runner-output-auth-contract-repair/ACTIONS.md`
- `docs/agent/runs/2026-07-01-p0-mimo-runner-output-auth-contract-repair/NEXT.md`
- `docs/agent/runs/2026-07-01-p0-mimo-runner-output-auth-contract-repair/PLAN.md`
- `docs/agent/runs/2026-07-01-p0-mimo-runner-output-auth-contract-repair/RESULT.md`
- `docs/agent/runs/2026-07-01-p0-mimo-runner-output-auth-contract-repair/TESTS.md`

The earlier top-level `artifacts/` files were removed from the PR branch.

## Known Remaining Risks

- PR #91 is still draft; it has not been merged or deployed.
- qjns is still not available for review tasks because its GitHub credential is missing and MIMO provider access is denied.
- PR #91 fixes live Agent Host behavior only after merge and deployment/restart on target nodes.
- Post-deploy direct MIMO fanout canary has not yet run on the updated Agent Host.

## Owner Options

1. Mark PR #91 ready, merge under release gate, deploy to one canary Agent Host node, then rerun direct MIMO fanout.
2. Keep PR #91 draft and request one more independent review.
3. Split docs from code if a smaller merge is preferred, though current scope is already narrow after artifact cleanup.

## Recommended Decision

Mark PR #91 ready for final review/merge, then deploy it to one canary Agent Host node and run a direct MIMO fanout canary before broad rollout.

## Next Control Plane Task

After owner merge/deploy approval:

`P0_PR91_POST_MERGE_MIMO_RUNNER_CANARY_2026_07_01`

Goal:

- deploy/restart updated Agent Host on one canary node;
- submit direct MIMO success and auth/policy failure probes;
- verify Control Plane completion/failure payloads are correctly classified;
- rerun direct MIMO fanout only after canary passes.
