# PR #91 MIMO Runner Output/Auth Contract Repair Plan

Task ID: `P0_MIMO_RUNNER_OUTPUT_AND_AUTH_CONTRACT_REPAIR_2026_07_01`

1. Preserve the useful PR #91 release evidence in the canonical run directory.
2. Remove top-level tracked artifacts under `artifacts/P0_MIMO_RUNNER_OUTPUT_AND_AUTH_CONTRACT_REPAIR_2026_07_01/`.
3. Do not keep the broken artifact manifest references to absent `stdout.log` and `stderr.log` files.
4. Keep the product repair scope unchanged: `ops/agent_host.py` and `tests/test_agent_host_direct_mimo.py`.
5. Record the focused verifier evidence for PR #91 head `a32697b62914816abfbd87365c7c1fec588b3262`.
6. Publish the artifact hygiene cleanup to branch `p0/mimo-runner-output-auth-contract-repair-2026-07-01` with a normal non-force push.
