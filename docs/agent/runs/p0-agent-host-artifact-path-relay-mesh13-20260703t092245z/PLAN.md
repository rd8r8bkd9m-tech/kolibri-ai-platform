# Plan

1. Bootstrap the assigned mesh-13 worktree from the local canonical repository because the assigned repo directory was empty/non-git.
2. Preserve only the useful prior code and test changes from the mesh-10 worktree:
   - `ops/agent_host.py`
   - `tests/test_agent_host_runner_contract.py`
3. Avoid carrying forward the misplaced root-level run documents from the prior attempt.
4. Create this run's required artifacts under `docs/agent/runs/p0-agent-host-artifact-path-relay-mesh13-20260703t092245z/`.
5. Run focused syntax and regression checks, then commit and push a non-main branch.
